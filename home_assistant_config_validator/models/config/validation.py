"""Configuration for how to validate each Package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, TypedDict, cast

from wg_utilities.functions.json import JSONObj, JSONVal

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.utils import (
    InvalidConfigurationError,
    JsonPathNotFoundError,
    ShouldBeEqualError,
    ShouldBeHardcodedError,
    ShouldMatchFileNameError,
    ShouldMatchFilePathError,
    check_known_entity_usages,
    const,
    get_json_value,
)

from .base import Config, replace_non_alphanumeric
from .parser import ParserConfig


class ShouldMatchFilepathItem(TypedDict):
    """Type definition for a single item in the `should_match_filepath` list."""

    field: str
    separator: str
    prefix: str
    ignore_chars: str
    include_domain_dir: bool
    remove_sensor_prefix: bool


@dataclass
class ValidationConfig(Config):
    """Dataclass for a package's validator configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.VALIDATION]] = (
        const.ConfigurationType.VALIDATION
    )

    package: Package

    should_be_equal: list[tuple[str, ...]] = field(default_factory=list)
    should_be_hardcoded: dict[str, JSONVal] = field(default_factory=dict)
    should_exist: list[str] = field(default_factory=list)
    should_match_filename: list[str] = field(default_factory=list)
    should_match_filepath: list[ShouldMatchFilepathItem] = field(
        default_factory=list,
    )

    _package_issues: dict[str, list[InvalidConfigurationError]] = field(
        default_factory=dict,
    )

    def _validate_should_be_equal(
        self,
        entity_yaml: JSONObj,
        /,
        *,
        issues: list[InvalidConfigurationError],
    ) -> None:
        for field_name_1, field_name_2 in self.should_be_equal:
            try:
                if (field_value_1 := get_json_value(entity_yaml, field_name_1)) != (
                    field_value_2 := get_json_value(entity_yaml, field_name_2)
                ):
                    issues.append(
                        ShouldBeEqualError(
                            f1=field_name_1,
                            v1=field_value_1,
                            f2=field_name_2,
                            v2=field_value_2,
                        ),
                    )
            except JsonPathNotFoundError as exc:
                issues.append(exc)

    def _validate_should_be_hardcoded(
        self,
        entity_yaml: JSONObj,
        /,
        *,
        issues: list[InvalidConfigurationError],
    ) -> None:
        for sbh_field, hardcoded_value in self.should_be_hardcoded.items():
            if (field_value := entity_yaml.get(sbh_field)) != hardcoded_value:
                issues.append(
                    ShouldBeHardcodedError(
                        sbh_field,
                        field_value,
                        hardcoded_value,
                    ),
                )

    def _validate_should_exist(
        self,
        entity_yaml: JSONObj,
        /,
        *,
        issues: list[InvalidConfigurationError],
    ) -> None:
        for se_field in self.should_exist:
            try:
                get_json_value(entity_yaml, se_field)
            except JsonPathNotFoundError as exc:
                issues.append(exc)

    def _validate_should_match_filename(
        self,
        entity_yaml: JSONObj,
        /,
        *,
        file_path: Path,
        issues: list[InvalidConfigurationError],
    ) -> None:
        """Validate that certain fields match the file name."""
        for smfn_field in self.should_match_filename:
            # Some entity types (e.g. sensor.systemmonitor) don't have certain fields
            # (e.g. name). If it's required, it'll get picked up in the other checks.
            if smfn_field not in entity_yaml:
                continue

            if (
                fmt_value := replace_non_alphanumeric(
                    field_value := str(entity_yaml.get(smfn_field) or ""),
                )
            ) != file_path.with_suffix("").name.lower():
                issues.append(
                    ShouldMatchFileNameError(smfn_field, field_value, fmt_value),
                )

    def _validate_should_match_filepath(
        self,
        entity_yaml: JSONObj,
        /,
        *,
        file_path: Path,
        issues: list[InvalidConfigurationError],
    ) -> None:
        for smfp_config in self.should_match_filepath:
            remove_sensor_prefix = smfp_config.get("remove_sensor_prefix", False)

            if smfp_config.get("include_domain_dir", False):
                if remove_sensor_prefix:
                    raise ValueError(  # noqa: TRY003
                        "include_domain_dir and remove_sensor_prefix are mutually"
                        " exclusive",
                    )

                filepath_parts = (
                    file_path.with_suffix("").relative_to(const.ENTITIES_DIR).parts
                )
            else:
                filepath_parts = (
                    file_path.with_suffix("")
                    .relative_to(const.ENTITIES_DIR / self.package.name)
                    .parts
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
                get_json_value(entity_yaml, smfp_config["field"]),
                ignore_chars=sep.replace(" ", ""),
            )

            if sep == " ":
                actual_value = actual_value.replace("_", " ")
                expected_value = expected_value.replace("_", " ")

            if expected_value != actual_value:
                issues.append(
                    ShouldMatchFilePathError(
                        smfp_config["field"],
                        actual_value,
                        expected_value,
                    ),
                )

    def run_custom_validations(
        self,
        *,
        file_path: Path,
        entity_yaml: JSONObj,
    ) -> list[InvalidConfigurationError]:
        # pylint: disable=too-many-locals,too-many-branches
        """Run all validations on the given entity.

        Args:
            file_path (Path): The entity's file path
            entity_yaml (JSONObj): The entity's YAML

        Returns:
            list[Exception]: A list of exceptions raised during validation
        """
        custom_issues: list[InvalidConfigurationError] = []

        self._validate_should_be_equal(entity_yaml, issues=custom_issues)
        self._validate_should_exist(entity_yaml, issues=custom_issues)
        self._validate_should_match_filename(
            entity_yaml,
            file_path=file_path,
            issues=custom_issues,
        )
        self._validate_should_match_filepath(
            entity_yaml,
            file_path=file_path,
            issues=custom_issues,
        )
        self._validate_should_be_hardcoded(entity_yaml, issues=custom_issues)

        return custom_issues

    def validate_package(self) -> None:
        """Validate a package's YAML files.

        Each file is validated against Home Assistant's schema for that package, and
        against the package's validator configuration. Custom validation is done by
        evaluating the JSON configuration adjacent to this module and applying each
        validation rule to the entity.

        Invalid files are added to the `self._package_issues` dict, with the file path
        as the key and a list of exceptions as the value.
        """
        parser = ParserConfig.get_for_package(self.package)

        for entity in self.package.entities:
            entity_yaml = parser.parse(entity)
            entity_file = cast(Path, entity_yaml["__file__"])

            file_issues: list[InvalidConfigurationError] = self.run_custom_validations(
                file_path=entity_file,
                entity_yaml=entity_yaml,
            )

            file_issues.extend(
                check_known_entity_usages(
                    entity_yaml,
                    entity_keys=("entity_id", "service"),
                ),
            )

            if file_issues:
                self._package_issues[
                    entity_file.relative_to(const.ENTITIES_DIR).as_posix()
                ] = file_issues

    @property
    def package_issues(self) -> dict[str, list[InvalidConfigurationError]]:
        """Return a list of all issues found in the package."""
        return self._package_issues
