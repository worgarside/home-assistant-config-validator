"""Configuration for how to validate each Package."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.utils import (
    Entity,
    InvalidConfigurationError,
    JsonPathNotFoundError,
    JSONPathStr,
    ShouldBeEqualError,
    ShouldBeHardcodedError,
    ShouldExistError,
    ShouldMatchFileNameError,
    ShouldMatchFilePathError,
    check_known_entity_usages,
    const,
    get_json_value,
)

from .base import Config, replace_non_alphanumeric


class Case(StrEnum):
    """Enum for the different cases."""

    SNAKE = "snake"
    KEBAB = "kebab"
    PASCAL = "pascal"
    CAMEL = "camel"


class ShouldMatchFilepathItem(BaseModel):
    """Type definition for a single item in the `should_match_filepath` list."""

    case: Case | None = None
    separator: str
    prefix: str = ""
    ignore_chars: str = ""
    remove_package_path: bool | None = Field(
        None,
        description="Explicitly remove the package path from the file path for validation. The "
        "behaviour varies depending on the number of tags in the file: if true, the expected "
        "value will be relative to the path of the tag which the entity belongs; if false, the "
        "expected value will be relative to the entities directory; if null, the expected value "
        "will be relative to the highest common ancestor of the tag paths. Fioles with a single "
        "tag will exhibit the same behaviour for `True` and `None`.",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    def get_expected_value(self, file: Path, /, package: Package) -> str:
        """Get the expected formatted filepath value for the given file."""
        if self.remove_package_path is True:
            relative_to = package.get_tag_path(file)
        elif self.remove_package_path is False:
            relative_to = const.ENTITIES_DIR
        else:
            relative_to = package.tag_paths_highest_common_ancestor

        parts = list(file.with_suffix("").relative_to(relative_to).parts)

        if self.case == Case.SNAKE:
            parts = [replace_non_alphanumeric(p) for p in parts]
        elif self.case == Case.KEBAB:
            parts = [replace_non_alphanumeric(p, replace_with="-") for p in parts]
        elif self.case is not None:  # Pascal or Camel
            parts = [
                "".join(
                    word.capitalize() for word in replace_non_alphanumeric(p).split("_")
                )
                for p in parts
            ]

            if self.case == Case.CAMEL:
                parts[0] = parts[0].lower()

        expected_value = self.prefix + self.separator.join(parts)

        if self.separator == " ":
            expected_value = expected_value.replace("_", " ")

        return expected_value

    def is_correct_case(self, string: str, /) -> bool:
        """Check if any given string is in the correct case."""
        if self.case is None:
            return True

        if self.case == Case.SNAKE:
            return (string.islower() or string.isdigit()) and all(
                c.isalpha() or c.isdigit() or c == "_" for c in string
            )

        if self.case == Case.KEBAB:
            return (string.islower() or string.isdigit()) and all(
                c.isalpha() or c.isdigit() or c == "-" for c in string
            )

        if self.case == Case.PASCAL:
            return (string[0].isupper() or string.isdigit()) and all(
                c.isalpha() or c.isdigit() for c in string
            )

        if self.case == Case.CAMEL:
            return (string[0].islower() or string.isdigit()) and all(
                c.isalpha() or c.isdigit() for c in string
            )

        raise ValueError(self.case)


class ValidationConfig(Config):
    """Dataclass for a package's validator configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.VALIDATION]] = (
        const.ConfigurationType.VALIDATION
    )

    package: Package

    should_be_equal: list[tuple[JSONPathStr, JSONPathStr]] = Field(default_factory=list)
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

    def _validate_should_match_filepath(
        self,
        entity_yaml: Entity,
        /,
    ) -> None:
        for field_path, config in self.should_match_filepath.items():
            expected_value = config.get_expected_value(entity_yaml.file__, self.package)

            try:
                actual_value = replace_non_alphanumeric(
                    get_json_value(entity_yaml, field_path, valid_type=str),
                    ignore_chars=config.separator.replace(" ", ""),
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
                if config.separator == " ":
                    actual_value = actual_value.replace("_", " ")

                if expected_value != actual_value or (
                    config.case
                    and not all(
                        config.is_correct_case(part)
                        for part in actual_value.split(config.separator)
                    )
                ):
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
