"""Configuration for how to validate each Package."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from jsonpath_ng import JSONPath, parse  # type: ignore[import-untyped]
from jsonpath_ng.exceptions import JsonPathParserError  # type: ignore[import-untyped]
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.utils import (
    Entity,
    InvalidConfigurationError,
    JsonPathNotFoundError,
    ShouldBeEqualError,
    ShouldBeHardcodedError,
    ShouldExistError,
    ShouldMatchFileNameError,
    ShouldMatchFilePathError,
    UserPCHConfigurationError,
    check_known_entity_usages,
    const,
    get_json_value,
)

from .base import Config, replace_non_alphanumeric


class ShouldMatchFilepathItem(BaseModel):
    """Type definition for a single item in the `should_match_filepath` list."""

    separator: str
    prefix: str = ""
    ignore_chars: str = ""
    include_domain_dir: bool = False
    remove_sensor_prefix: bool = False

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        """Validate the configuration for a `should_match_filepath` item."""
        if self.include_domain_dir and self.remove_sensor_prefix:
            raise UserPCHConfigurationError(
                const.ConfigurationType.VALIDATION,
                "unknown",
                "include_domain_dir and remove_sensor_prefix are mutually exclusive",
            )

        return self


def validate_json_path(path: str, /) -> JSONPath:
    """Validate a JSONPath string."""
    try:
        parse(path)
    except JsonPathParserError:
        raise UserPCHConfigurationError(
            const.ConfigurationType.VALIDATION,
            "unknown",
            f"Invalid JSONPath: {path}",
        ) from None

    return path


JSONPathStr = Annotated[str, AfterValidator(validate_json_path)]


class ValidationConfig(Config):
    """Dataclass for a package's validator configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.VALIDATION]] = (
        const.ConfigurationType.VALIDATION
    )

    package: Package

    should_be_equal: list[tuple[JSONPathStr, ...]] = Field(default_factory=list)
    should_be_hardcoded: dict[JSONPathStr, object] = Field(default_factory=dict)
    should_exist: list[JSONPathStr] = Field(default_factory=list)
    should_match_filename: list[JSONPathStr] = Field(default_factory=list)
    should_match_filepath: dict[JSONPathStr, ShouldMatchFilepathItem] = Field(
        default_factory=dict,
    )

    issues: dict[Path, list[InvalidConfigurationError]] = Field(default_factory=dict)

    def _validate_should_be_equal(self, entity_yaml: Entity, /) -> None:
        for field_name_1, field_name_2 in self.should_be_equal:
            try:
                if (field_value_1 := get_json_value(entity_yaml, field_name_1)) != (
                    field_value_2 := get_json_value(entity_yaml, field_name_2)
                ):
                    self.issues[entity_yaml.file__].append(
                        ShouldBeEqualError(
                            f1=field_name_1,
                            v1=field_value_1,
                            f2=field_name_2,
                            v2=field_value_2,
                        ),
                    )
            except JsonPathNotFoundError as exc:
                self.issues[entity_yaml.file__].append(exc)

    def _validate_should_be_hardcoded(self, entity_yaml: Entity, /) -> None:
        for sbh_field, hardcoded_value in self.should_be_hardcoded.items():
            if (
                field_value := get_json_value(entity_yaml, sbh_field)
            ) != hardcoded_value:
                self.issues[entity_yaml.file__].append(
                    ShouldBeHardcodedError(
                        sbh_field,
                        field_value,
                        hardcoded_value,
                    ),
                )

    def _validate_should_exist(self, entity_yaml: Entity, /) -> None:
        for se_field in self.should_exist:
            try:
                get_json_value(entity_yaml, se_field)
            except JsonPathNotFoundError as exc:
                self.issues[entity_yaml.file__].append(ShouldExistError(se_field, exc))

    def _validate_should_match_filename(self, entity_yaml: Entity, /) -> None:
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
                ) != entity_yaml.file__.with_suffix("").name.lower():
                    self.issues[entity_yaml.file__].append(
                        ShouldMatchFileNameError(smfn_field, field_value, fmt_value),
                    )
            except JsonPathNotFoundError:
                # Some entity types (e.g. sensor.systemmonitor) don't have certain fields
                # (e.g. name). If it's required, it'll get picked up in the other checks.
                continue

    def _validate_should_match_filepath(self, entity_yaml: Entity, /) -> None:
        for field_path, smfp_config in self.should_match_filepath.items():
            if smfp_config.include_domain_dir:
                filepath_parts = (
                    entity_yaml.file__.with_suffix("")
                    .relative_to(const.ENTITIES_DIR)
                    .parts
                )
            else:
                filepath_parts = (
                    entity_yaml.file__.with_suffix("")
                    .relative_to(const.ENTITIES_DIR / self.package.name)
                    .parts
                )

            if smfp_config.remove_sensor_prefix and filepath_parts[0] in (
                "binary_sensor",
                "sensor",
            ):
                filepath_parts = filepath_parts[1:]

            expected_value = smfp_config.prefix + smfp_config.separator.join(
                filepath_parts,
            )

            if smfp_config.separator == " ":
                expected_value = expected_value.replace("_", " ")

            try:
                actual_value = replace_non_alphanumeric(
                    get_json_value(entity_yaml, field_path, valid_type=str),
                    ignore_chars=smfp_config.separator.replace(" ", ""),
                )
            except InvalidConfigurationError:
                self.issues[entity_yaml.file__].append(
                    ShouldMatchFilePathError(
                        field_path,
                        None,
                        expected_value,
                    ),
                )
            else:
                if smfp_config.separator == " ":
                    actual_value = actual_value.replace("_", " ")

                if expected_value != actual_value:
                    self.issues[entity_yaml.file__].append(
                        ShouldMatchFilePathError(
                            field_path,
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
        for entity_yaml in self.package.entities:

            self.issues[entity_yaml.file__] = check_known_entity_usages(
                entity_yaml.model_dump(),
                entity_keys=("entity_id", "service"),
            )

            self._validate_should_be_equal(entity_yaml)
            self._validate_should_exist(entity_yaml)
            self._validate_should_match_filename(entity_yaml)
            self._validate_should_match_filepath(entity_yaml)
            self._validate_should_be_hardcoded(entity_yaml)
