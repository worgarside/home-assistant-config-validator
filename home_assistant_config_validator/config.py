"""Configuration classes for the Home Assistant Config Validator."""

from __future__ import annotations

from abc import ABC
from collections.abc import Generator
from dataclasses import dataclass, field
from functools import lru_cache
from json import loads
from logging import getLogger
from pathlib import Path
from re import escape, sub
from typing import ClassVar, Literal, Self, TypedDict

from wg_utilities.functions.json import JSONArr, JSONObj, JSONVal
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.const import (
    ENTITIES_DIR,
    PCH_CONFIG,
    REPO_PATH,
    VALIDATE_ALL_PACKAGES,
    ConfigurationType,
    check_known_entity_usages,
)
from home_assistant_config_validator.exception import UserPCHConfigurationError
from home_assistant_config_validator.ha_yaml_loader import load_yaml

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


def replace_non_alphanumeric(string: str, ignore_chars: str = "") -> str:
    """Convert a string to be alphanumeric and snake_case.

    Leading/trailing underscores are removed, and double (or more) underscores are
    replaced with a single underscore. Ignores values within `string` that are also in
    `ignore_strings`.

    Args:
        string (str): The string to convert
        ignore_chars (str, optional): Other characters to ignore. Defaults to None.

    Returns:
        str: The converted string
    """
    return (
        sub(r"_{2,}", "_", sub(rf"[^a-zA-Z0-9{escape(ignore_chars)}]", "_", string))
        .lower()
        .strip("_")
    )


class Config(ABC):
    """Base class for configuration classes."""

    CONFIGURATION_TYPE: ClassVar[ConfigurationType]
    package_name: str

    @classmethod
    def get_for_package(cls, package_name: str, /) -> Self:
        """Get the user's configuration for a given domain."""
        package_config = (
            _load_user_pch_configuration()
            .get(package_name, {})
            .get(cls.CONFIGURATION_TYPE, {})
        )

        if not isinstance(package_config, dict):
            raise TypeError(type(package_config))

        if cls is ValidationConfig and VALIDATE_ALL_PACKAGES and not package_config:
            raise UserPCHConfigurationError(
                cls.CONFIGURATION_TYPE,
                package_name,
                "not found",
            )

        package_config["package_name"] = package_name

        return cls(**package_config)


class ShouldMatchFilepathItem(TypedDict):
    """Type definition for a single item in the `should_match_filepath` list."""

    field: str
    separator: str
    prefix: str
    ignore_chars: str
    include_domain_dir: bool
    remove_sensor_prefix: bool


@dataclass
class ParserConfig(Config):
    """Dataclass for a domain's parser configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[ConfigurationType.PARSER]] = (
        ConfigurationType.PARSER
    )

    package_name: str

    top_level_keys: list[str] = field(default_factory=list)

    def parse(self, __obj: JSONObj, /) -> JSONObj:
        """Parse a JSON object."""
        if self.top_level_keys:
            __file__ = __obj.pop("__file__", None)

            if (
                len(__obj) == 1
                and (only_key := next(iter(__obj.keys()))) in self.top_level_keys
            ):
                new_obj: JSONObj = __obj.pop(only_key)  # type: ignore[assignment]
            else:
                new_obj = __obj

            if __file__:
                new_obj["__file__"] = __file__

            return new_obj

        return __obj


@dataclass
class ValidationConfig(Config):
    """Dataclass for a domain's validator configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[ConfigurationType.VALIDATION]] = (
        ConfigurationType.VALIDATION
    )

    package_name: str

    should_match_filename: list[str] = field(default_factory=list)
    should_match_filepath: list[ShouldMatchFilepathItem] = field(
        default_factory=list,
    )
    should_be_equal: list[tuple[str, ...]] = field(default_factory=list)
    should_exist: list[str] = field(default_factory=list)
    should_be_hardcoded: dict[str, JSONVal] = field(default_factory=dict)

    _package_issues: dict[str, list[Exception]] = field(default_factory=dict)

    def run_custom_validations(  # noqa: PLR0912
        self,
        *,
        domain_dir_path: Path,
        file_path: Path,
        entity_yaml: JSONObj,
    ) -> list[Exception]:
        # pylint: disable=too-many-locals,too-many-branches
        """Run all validations on the given entity.

        Args:
            domain_dir_path (Path): The domain's directory path
            file_path (Path): The entity's file path
            entity_yaml (JSONObj): The entity's YAML

        Returns:
            list[Exception]: A list of exceptions raised during validation
        """
        custom_issues: list[Exception] = []

        for smfn_field in self.should_match_filename:
            # Some entity types (e.g. sensor.systemmonitor) don't have certain fields
            # (e.g. name). If it's required, it'll get picked up in the other checks.
            if smfn_field not in entity_yaml:
                continue

            if (
                fmt_value := replace_non_alphanumeric(
                    field_value := entity_yaml.get(  # type: ignore[arg-type]
                        smfn_field,
                        "",
                    ),
                )
            ) != file_path.with_suffix("").name.lower():
                custom_issues.append(
                    ValueError(
                        f"`{smfn_field}: {field_value!s}` ({fmt_value=}) should match"
                        " file name",
                    ),
                )

        for field_name_1, field_name_2 in self.should_be_equal:
            if (field_value_1 := entity_yaml.get(field_name_1)) != (
                field_value_2 := entity_yaml.get(field_name_2)
            ):
                custom_issues.append(
                    ValueError(
                        f"`{field_name_1}: {field_value_1!s}` should match"
                        f" `{field_name_2}: {field_value_2!s}`",
                    ),
                )

        for smfp_config in self.should_match_filepath:
            remove_sensor_prefix = smfp_config.get("remove_sensor_prefix", False)

            if smfp_config.get("include_domain_dir", False):
                if remove_sensor_prefix:
                    raise ValueError(  # noqa: TRY003
                        "include_domain_dir and remove_sensor_prefix are mutually"
                        " exclusive",
                    )

                filepath_parts = (
                    file_path.with_suffix("").relative_to(domain_dir_path.parent).parts
                )
            else:
                filepath_parts = (
                    file_path.with_suffix("").relative_to(domain_dir_path).parts
                )

            if remove_sensor_prefix and filepath_parts[0] in (
                "binary_sensor",
                "sensor",
            ):
                filepath_parts = filepath_parts[1:]

            expected_value = smfp_config.get("prefix", "") + (
                sep := smfp_config["separator"]
            ).join(filepath_parts)

            actual_value = replace_non_alphanumeric(
                entity_yaml.get(smfp_config["field"], ""),  # type: ignore[arg-type]
                ignore_chars=sep.replace(" ", ""),
            )

            if sep == " ":
                actual_value = actual_value.replace("_", " ")
                expected_value = expected_value.replace("_", " ")

            if expected_value != actual_value:
                custom_issues.append(
                    ValueError(
                        f"`{smfp_config['field']}: {(actual_value or 'null')!s}`"
                        f" should match file path: `{expected_value!s}`",
                    ),
                )

        for se_field in self.should_exist:
            if se_field not in entity_yaml:
                custom_issues.append(ValueError(f"`{se_field}` should be defined"))

        for sbh_field, hardcoded_value in self.should_be_hardcoded.items():
            if (field_value := entity_yaml.get(sbh_field)) != hardcoded_value:
                custom_issues.append(
                    ValueError(
                        f"`{sbh_field}: {field_value!s}` should be hardcoded as"
                        f" {hardcoded_value!r}",
                    ),
                )

        return custom_issues

    def validate_domain(self) -> None:
        """Validate a domain's YAML files.

        Each file is validated against Home Assistant's schema for that domain, and
        against the domain's validator configuration. Custom validation is done by
        evaluating the JSON configuration adjacent to this module and applying each
        validation rule to the entity.

        Invalid files are added to the `self._domain_issues` dict, with the file path
        as the key and a list of exceptions as the value.
        """
        domain_dir_path = ENTITIES_DIR / self.package_name

        if not domain_dir_path.is_dir():
            self._package_issues["root"] = [
                ValueError(
                    f"Directory {domain_dir_path.relative_to(REPO_PATH)} does not exist",
                ),
            ]

        parser = ParserConfig.get_for_package(self.package_name)

        for file in domain_dir_path.rglob("*.yaml"):
            entity_yaml: JSONObj | JSONArr = parser.parse(
                load_yaml(file, resolve_tags=False),
            )

            file_issues: list[Exception] = self.run_custom_validations(
                domain_dir_path=domain_dir_path,
                file_path=file,
                entity_yaml=entity_yaml,  # type: ignore[arg-type]
            )

            file_issues.extend(
                check_known_entity_usages(
                    entity_yaml,
                    entity_keys=("entity_id", "service"),
                ),
            )

            if file_issues:
                self._package_issues[file.relative_to(REPO_PATH).as_posix()] = (
                    file_issues
                )

    @property
    def package_issues(self) -> dict[str, list[Exception]]:
        """Return a list of all issues found in the domain.

        Returns:
            dict[str, list[Exception]]: A list of all issues found in the domain
        """
        return self._package_issues


@dataclass
class DocumentationConfig(Config):
    """Dataclass for a domain's documentation configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[ConfigurationType.DOCUMENTATION]] = (
        ConfigurationType.DOCUMENTATION
    )

    package_name: str

    description: str | None = field(default=None)
    name: str = field(default="name")
    id: str = field(default="id")

    extra: list[str] = field(default_factory=list)

    @property
    def validated_fields(self) -> list[str]:
        """Return a list of all fields that should be validated."""
        validator = ValidationConfig.get_for_package(self.package_name)

        fields = (
            set(validator.should_exist)
            | set(validator.should_match_filename)
            | set(validator.should_be_hardcoded.keys())
            | {smfpi["field"] for smfpi in validator.should_match_filepath}
        )

        for pair in validator.should_be_equal:
            fields.update(pair)

        return sorted(fields)

    def __iter__(self) -> Generator[str, None, None]:
        """Iterate over all fields that should be documented."""
        yield from self.validated_fields
        yield from self.extra


@lru_cache
def _load_user_pch_configuration() -> dict[str, dict[ConfigurationType, JSONObj]]:
    return loads(PCH_CONFIG.read_text())["packages"]  # type: ignore[no-any-return]


__all__ = ["Config", "ParserConfig", "ValidationConfig", "DocumentationConfig"]
