"""Configuration for how to validate each Package."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from enum import StrEnum
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import Any, ClassVar, Literal

from jinja2 import Environment, TemplateError, meta
from jinja2.defaults import (
    BLOCK_START_STRING,
    COMMENT_START_STRING,
    VARIABLE_START_STRING,
)
from pydantic import BaseModel, ConfigDict, Field
from wg_utilities.helpers.mixin.instance_cache import CacheIdNotFoundError
from wg_utilities.helpers.processor import JProc

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.utils import (
    Entity,
    InvalidConfigurationError,
    InvalidDependencyError,
    InvalidTemplateError,
    InvalidTemplateVarError,
    JsonPathNotFoundError,
    JSONPathStr,
    ShouldBeEqualError,
    ShouldBeHardcodedError,
    ShouldExistError,
    ShouldMatchFileNameError,
    ShouldMatchFilePathError,
    args,
    const,
    get_json_value,
)

from .base import Config, replace_non_alphanumeric
from .documentation import DocumentationConfig

LOGGER = getLogger(__name__)


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
        description="Explicitly remove the package path from the file path for validation. "
        "The behaviour varies depending on the number of tags in the file: if true, the "
        "expected value will be relative to the path of the tag which the entity belongs; if "
        "false, the expected value will be relative to the entities directory; if null, the "
        "expected value will be relative to the highest common ancestor of the tag paths. "
        "Files with a single tag will exhibit the same behaviour for `True` and `None`.",
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
                "".join(word.capitalize() for word in replace_non_alphanumeric(p).split("_"))
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
        if self.case is None or not string:
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


@lru_cache
def _get_variable_setter_pattern(__var: str) -> re.Pattern[str]:
    r"""Create a regex pattern to match a Jinja2 variable setter.

    Example:
        >>> _get_variable_setter_pattern("var")
        Pattern(r'{{% set var = ')  # but with flexible whitespace
    """
    return re.compile(rf"{{%\s*set\s*{re.escape(__var)}\s*=.+")


@JProc.callback(allow_mutation=False)
def _jinja_template_validator(
    _value_: str,
    _loc_: str,
    entity: Entity,
    issues: list[InvalidConfigurationError],
    package_name: str,
) -> None:
    """Validate Jinja2 template syntax and variable usage."""
    try:
        template = ValidationConfig.JINJA_ENV.parse(_value_)
    except TemplateError as exc:
        issues.append(
            InvalidTemplateError(exc, loc=_loc_),
        )
        return

    try:
        undeclared_variables = meta.find_undeclared_variables(template) - const.JINJA_VARS
    except TemplateError as exc:
        issues.append(InvalidTemplateError(exc, loc=_loc_))
        return

    if not undeclared_variables:
        return

    try:
        jproc = JProc.from_cache("find_template_variables")
    except CacheIdNotFoundError:
        jproc = JProc(
            {
                dict: JProc.cb(
                    _remove_declared_variables,
                    lambda _, loc: loc == "variables",
                ),
                str: JProc.cb(
                    _remove_response_variables,
                    lambda _, loc: loc == "response_variable",
                ),
            },
            identifier="find_template_variables",
            process_pydantic_extra_fields=True,
        )

    # Process the mnodel to get variables (including response variables)
    jproc.process_model(
        entity,
        undeclared_variables=undeclared_variables,
    )

    # Special case for script input fields (arguments)
    if package_name == "script":
        with suppress(AttributeError):  # not all scripts have fields
            undeclared_variables -= set(entity.fields.keys())  # type: ignore[attr-defined]

    # Discount any suppressed vars
    if undeclared_variables and (
        suppressed := entity.suppressions__.get(_loc_, {}).get(
            InvalidTemplateVarError.SUPPRESSION_COMMENT,
        )
    ):
        undeclared_variables -= suppressed

    # jinja2 won't detect variables declared within templates, so find them with regex
    for var in undeclared_variables:
        if _get_variable_setter_pattern(var).search(_value_):
            continue

        issues.append(
            InvalidTemplateVarError(
                undeclared_var=var,
                loc=_loc_,
            ),
        )


@JProc.callback(allow_mutation=False)
def _remove_response_variables(
    _value_: str,
    undeclared_variables: set[str],
) -> None:
    """Discount response variables declared within the entity.

    https://www.home-assistant.io/docs/scripts#stopping-a-script-sequence
    """
    with suppress(KeyError):
        undeclared_variables.remove(_value_)


@JProc.callback(allow_mutation=False)
def _remove_declared_variables(
    _value_: dict[str, str],
    undeclared_variables: set[str],
) -> None:
    """Discount variable declared explicitly within the entity.

    https://www.home-assistant.io/docs/scripts#variables
    """
    undeclared_variables -= set(_value_.keys())


class ValidationConfig(Config):
    """Dataclass for a package's validator configuration."""

    CONFIGURATION_TYPE: ClassVar[
        Literal[const.ConfigurationType.VALIDATION]
    ] = const.ConfigurationType.VALIDATION

    KNOWN_ENTITY_IDS: ClassVar[tuple[str, ...]]

    JINJA_ENV: ClassVar[Environment] = Environment(
        autoescape=True,
        extensions=["jinja2.ext.loopcontrols"],
    )

    package: Package

    should_be_equal: list[tuple[JSONPathStr, JSONPathStr]] = Field(default_factory=list)
    should_be_hardcoded: dict[JSONPathStr, object] = Field(default_factory=dict)
    should_exist: list[JSONPathStr] = Field(default_factory=list)
    should_match_filename: list[JSONPathStr] = Field(default_factory=list)
    should_match_filepath: dict[JSONPathStr, ShouldMatchFilepathItem] = Field(
        default_factory=dict,
    )
    invalid_template_variables: bool = True

    issues: dict[Path, list[InvalidConfigurationError]] = Field(
        default_factory=lambda: defaultdict(list),
    )

    def model_post_init(self, *_: Any, **__: Any) -> None:
        """Post-initialisation steps for the model."""
        if not hasattr(ValidationConfig, "KNOWN_ENTITY_IDS"):
            for jf in const.JINJA_FILTERS:
                # Not actually running the templates, so the filter function is immaterial
                ValidationConfig.JINJA_ENV.filters.setdefault(jf, lambda _: None)

            for jt in const.JINJA_TESTS:
                ValidationConfig.JINJA_ENV.tests.setdefault(jt, lambda _: None)

            # This needs to be last - `KNOWN_ENTITY_IDS` is the flag for "this has been done"
            ValidationConfig.KNOWN_ENTITY_IDS = tuple(
                DocumentationConfig.get_for_package(pkg).get_id(
                    entity,
                    prefix_domain=True,
                )
                for pkg in Package.get_packages()
                for entity in pkg.entities
            )

    def _validate_jinja2_templates(self, entity: Entity, /) -> None:
        """Validate that any Jinja2 Templates have valid syntax."""
        try:
            jproc = JProc.from_cache("template_validation")
        except CacheIdNotFoundError:
            jproc = JProc(
                {
                    str: JProc.cb(
                        _jinja_template_validator,
                        lambda item, **_: (
                            VARIABLE_START_STRING in item
                            or BLOCK_START_STRING in item
                            or COMMENT_START_STRING in item
                        ),
                    ),
                },
                identifier="template_validation",
                process_pydantic_extra_fields=True,
            )

        jproc.process_model(
            entity,
            entity=entity,
            issues=self.issues[entity.file__],
            package_name=self.package.name,
        )

    def _validate_known_entity_ids(self, entity: Entity, /) -> None:
        """Validate that the Entity doesn't consume any unknown entities."""
        if InvalidDependencyError.SUPPRESSION_COMMENT in entity.suppressions__.get(
            "*",
            (),
        ):
            return

        entity_id = None

        for key, dep in entity.entity_dependencies:
            if (
                dep in self.KNOWN_ENTITY_IDS
                or InvalidDependencyError.SUPPRESSION_COMMENT
                in entity.suppressions__.get(
                    key,
                    (),
                )
            ):
                continue

            if entity_id is None:
                entity_id = DocumentationConfig.get_for_package(self.package).get_id(
                    entity,
                    prefix_domain=True,
                )

            self.issues[entity.file__].append(InvalidDependencyError(entity_id, dep))

    def _validate_should_be_equal(self, entity_yaml: Entity, /) -> None:
        for json_path_str_1, json_path_str_2 in self.should_be_equal:
            try:
                if (
                    value_1 := get_json_value(
                        entity_yaml,
                        json_path_str_1,
                        default=const.INEQUAL,
                    )
                ) != (
                    value_2 := get_json_value(
                        entity_yaml,
                        json_path_str_2,
                        default=const.INEQUAL,
                    )
                ):
                    self.issues[entity_yaml.file__].append(
                        ShouldBeEqualError(
                            f1=json_path_str_1,
                            v1=value_1,
                            f2=json_path_str_2,
                            v2=value_2,
                        ),
                    )
            except JsonPathNotFoundError as exc:
                self.issues[entity_yaml.file__].append(exc)

    def _validate_should_be_hardcoded(self, entity_yaml: Entity, /) -> None:
        for json_path_str, hardcoded_value in self.should_be_hardcoded.items():
            if (
                field_value := get_json_value(
                    entity_yaml,
                    json_path_str,
                    default=const.INEQUAL,
                )
            ) != hardcoded_value and (
                ShouldBeHardcodedError.SUPPRESSION_COMMENT
                not in entity_yaml.suppressions__.get(json_path_str.split(".")[-1], ())
            ):
                self.issues[entity_yaml.file__].append(
                    ShouldBeHardcodedError(
                        json_path_str,
                        field_value,
                        hardcoded_value,
                    ),
                )

    def _validate_should_exist(self, entity_yaml: Entity, /) -> None:
        suppressed = entity_yaml.suppressions__.get("*", {}).get("shouldexist", ())

        for json_path_str in self.should_exist:
            if json_path_str.split(".")[-1] in suppressed:
                continue

            try:
                get_json_value(entity_yaml, json_path_str)
            except JsonPathNotFoundError as exc:
                self.issues[entity_yaml.file__].append(
                    ShouldExistError(json_path_str, exc),
                )

    def _validate_should_match_filename(self, entity_yaml: Entity, /) -> None:
        """Validate that certain fields match the file name."""
        if ShouldMatchFileNameError.SUPPRESSION_COMMENT in entity_yaml.suppressions__.get(
            "*",
            (),
        ):
            return

        for json_path_str in self.should_match_filename:
            if ShouldMatchFileNameError.SUPPRESSION_COMMENT in entity_yaml.suppressions__.get(
                json_path_str.split(".")[-1],
                (),
            ):
                continue
            try:
                if (
                    fmt_value := replace_non_alphanumeric(
                        field_value := get_json_value(
                            entity_yaml,
                            json_path_str,
                            valid_type=str,
                        ),
                    )
                ) != entity_yaml.file__.with_suffix("").name.lower():
                    self.issues[entity_yaml.file__].append(
                        ShouldMatchFileNameError(json_path_str, field_value, fmt_value),
                    )
            except JsonPathNotFoundError:
                # Some entity types (e.g. sensor.systemmonitor) don't have certain fields
                # (e.g. name). If it's required, it'll get picked up in the other checks.
                continue

    def _validate_should_match_filepath(self, entity_yaml: Entity, /) -> None:
        if ShouldMatchFilePathError.SUPPRESSION_COMMENT in entity_yaml.suppressions__.get(
            "*",
            (),
        ):
            return

        for json_path_str, config in self.should_match_filepath.items():
            if ShouldMatchFilePathError.SUPPRESSION_COMMENT in entity_yaml.suppressions__.get(
                json_path_str.split(".")[-1],
                (),
            ):
                continue

            expected_value = config.get_expected_value(entity_yaml.file__, self.package)

            try:
                actual_value = get_json_value(
                    entity_yaml,
                    json_path_str,
                    valid_type=str,
                ).lower()
            except InvalidConfigurationError:
                self.issues[entity_yaml.file__].append(
                    ShouldMatchFilePathError(
                        json_path_str,
                        None,
                        expected_value,
                    ),
                )
            else:
                ignore_chars = [config.separator]

                if config.case == Case.KEBAB:
                    ignore_chars.append("-")
                elif config.case == Case.SNAKE:
                    ignore_chars.append("_")

                normalised_value = replace_non_alphanumeric(
                    actual_value,
                    ignore_chars=ignore_chars,
                    replace_with="",
                )

                if expected_value != normalised_value or (
                    config.case
                    and not all(
                        config.is_correct_case(part)
                        for part in normalised_value.split(config.separator)
                    )
                ):
                    self.issues[entity_yaml.file__].append(
                        ShouldMatchFilePathError(
                            json_path_str,
                            actual_value,
                            expected_value,
                        ),
                    )

    def validate_package(self) -> dict[Path, list[InvalidConfigurationError]]:
        """Validate a package's YAML files.

        Each file is validated against Home Assistant's schema for that package, and
        against the package's validator configuration. Custom validation is done by
        evaluating the JSON configuration adjacent to this module and applying each
        validation rule to the entity.

        Invalid files are added to the `self.issues` dict, with the file path
        as the key and a list of exceptions as the value.
        """
        self.issues = defaultdict(list)

        for entity in self.package.entities:
            for validator in self.validators:
                validator(entity)

            if args.AUTOFIX and self.issues[entity.file__]:
                entity.autofix_file_issues(self.issues[entity.file__])

        return self.issues

    @property
    def validators(self) -> list[Callable[[Entity], None]]:
        """Get the validation functions for the package."""
        v = [
            self._validate_known_entity_ids,
            self._validate_should_be_equal,
            self._validate_should_be_hardcoded,
            self._validate_should_exist,
            self._validate_should_match_filename,
            self._validate_should_match_filepath,
        ]

        if self.invalid_template_variables:
            v.append(self._validate_jinja2_templates)

        return v
