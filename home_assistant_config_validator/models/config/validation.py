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
from home_assistant_config_validator.utils.exception import UserPCHConfigurationError

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

    issues: dict[Path, list[InvalidConfigurationError]] = field(default_factory=dict)

    def _validate_should_be_equal(self, entity_yaml: JSONObj, /) -> None:
        for field_name_1, field_name_2 in self.should_be_equal:
            try:
                if (field_value_1 := get_json_value(entity_yaml, field_name_1)) != (
                    field_value_2 := get_json_value(entity_yaml, field_name_2)
                ):
                    self.issues[self.entity_file(entity_yaml)].append(
                        ShouldBeEqualError(
                            f1=field_name_1,
                            v1=field_value_1,
                            f2=field_name_2,
                            v2=field_value_2,
                        ),
                    )
            except JsonPathNotFoundError as exc:
                self.issues[self.entity_file(entity_yaml)].append(exc)

    def _validate_should_be_hardcoded(self, entity_yaml: JSONObj, /) -> None:
        for sbh_field, hardcoded_value in self.should_be_hardcoded.items():
            if (
                field_value := get_json_value(entity_yaml, sbh_field)
            ) != hardcoded_value:
                self.issues[self.entity_file(entity_yaml)].append(
                    ShouldBeHardcodedError(
                        sbh_field,
                        field_value,
                        hardcoded_value,
                    ),
                )

    def _validate_should_exist(self, entity_yaml: JSONObj, /) -> None:
        for se_field in self.should_exist:
            try:
                get_json_value(entity_yaml, se_field)
            except JsonPathNotFoundError as exc:
                self.issues[self.entity_file(entity_yaml)].append(exc)

    def _validate_should_match_filename(self, entity_yaml: JSONObj, /) -> None:
        """Validate that certain fields match the file name."""
        for smfn_field in self.should_match_filename:
            try:
                if (
                    fmt_value := replace_non_alphanumeric(
                        field_value := get_json_value(
                            entity_yaml,
                            smfn_field,
                            valid_type=str,
                        ),
                    )
                ) != self.entity_file(entity_yaml).with_suffix("").name.lower():
                    self.issues[self.entity_file(entity_yaml)].append(
                        ShouldMatchFileNameError(smfn_field, field_value, fmt_value),
                    )
            except JsonPathNotFoundError:
                # Some entity types (e.g. sensor.systemmonitor) don't have certain fields
                # (e.g. name). If it's required, it'll get picked up in the other checks.
                continue

    def _validate_should_match_filepath(self, entity_yaml: JSONObj, /) -> None:
        for smfp_config in self.should_match_filepath:
            remove_sensor_prefix = smfp_config.get("remove_sensor_prefix", False)

            if smfp_config.get("include_domain_dir", False):
                # TODO move this to validator
                if remove_sensor_prefix:
                    raise UserPCHConfigurationError(
                        self.CONFIGURATION_TYPE,
                        self.package.pkg_name,
                        "include_domain_dir and remove_sensor_prefix are mutually exclusive",
                    )

                filepath_parts = (
                    self.entity_file(entity_yaml)
                    .with_suffix("")
                    .relative_to(const.ENTITIES_DIR)
                    .parts
                )
            else:
                filepath_parts = (
                    self.entity_file(entity_yaml)
                    .with_suffix("")
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
                self.issues[self.entity_file(entity_yaml)].append(
                    ShouldMatchFilePathError(
                        smfp_config["field"],
                        actual_value,
                        expected_value,
                    ),
                )

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

            self.issues[self.entity_file(entity_yaml)] = check_known_entity_usages(
                entity_yaml,
                entity_keys=("entity_id", "service"),
            )

            self._validate_should_be_equal(entity_yaml)
            self._validate_should_exist(entity_yaml)
            self._validate_should_match_filename(entity_yaml)
            self._validate_should_match_filepath(entity_yaml)
            self._validate_should_be_hardcoded(entity_yaml)

    @staticmethod
    def entity_file(entity_yaml: JSONObj, /) -> Path:
        """Get the file path for the entity."""
        if not isinstance(entity_yaml["__file__"], Path):
            entity_yaml["__file__"] = Path(str(entity_yaml["__file__"]))

        return cast(Path, entity_yaml["__file__"])
