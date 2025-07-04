"""Exceptions for the home_assistant_config_validator package."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

from . import const

if TYPE_CHECKING:
    from pathlib import Path

    from jinja2 import TemplateError


class ConfigurationError(Exception):
    """Raised when a configuration error is detected."""


class FileIOError(IOError):
    """Raised when a file I/O error is detected."""

    def __init__(self, file_path: Path, operation: str) -> None:
        super().__init__(
            f"{operation} failed for file: {file_path.relative_to(const.REPO_PATH)}",
        )
        self.file_path = file_path
        self.operation = operation


class UserPCHConfigurationError(ConfigurationError):
    """Raised when a error in the pre-commit hook's configuration is detected."""

    def __init__(
        self,
        configuration_type: const.ConfigurationType,
        package: str,
        message: str,
    ) -> None:
        """Initialize the error."""
        super().__init__(
            f"{configuration_type} configuration error for package `{package}`: {message}",
        )


class HomeAssistantConfigurationError(ConfigurationError):
    """Raised when a Home Assistant configuration error is detected."""


class FileContentError(HomeAssistantConfigurationError):
    """Raised when the content of a file is invalid."""

    def __init__(self, file: Path, message: str | None = None) -> None:
        """Initialize the error."""
        msg = f"Invalid content in file {file.relative_to(const.REPO_PATH)}"

        if message:
            msg += f": {message}"

        super().__init__(msg)


class FileContentTypeError(FileContentError):
    """Raised when the content of a file is invalid."""

    def __init__(
        self,
        file: Path,
        content: Any,
        expected_type: type,
        key: str | None = None,
    ) -> None:
        """Initialize the error."""
        msg = f"expected {expected_type.__name__!r}, got {type(content).__name__!r}"

        if key:
            msg += f" for key {key}"

        super().__init__(file, msg)


class EntityDefinitionError(FileContentError):
    """Raised when an entity definition is invalid."""

    def __init__(self, file: Path, entity: str) -> None:
        """Initialize the error."""
        super().__init__(
            file,
            f"entity definition invalid: {entity}",
        )


class PackageNotFoundError(HomeAssistantConfigurationError):
    """Raised when a package is not found."""


class PackageDefinitionError(FileContentError):
    """Raised when a package definition is invalid."""

    def __init__(self, file: Path, message: str) -> None:
        """Initialize the error."""
        super().__init__(file, f"package definition invalid: {message}")


class InvalidConfigurationError(HomeAssistantConfigurationError):
    """Raised when a configuration is invalid."""

    fmt_msg: str
    SUPPRESSION_COMMENT: ClassVar[str]

    def __init__(self, message: str) -> None:
        """Initialize the error."""
        super().__init__(message)

        if not hasattr(self, "fmt_msg"):
            self.fmt_msg = message

        self.fixed = False

    def __init_subclass__(cls) -> None:
        cls.SUPPRESSION_COMMENT = cls.__name__.removesuffix("Error").lower()
        return super().__init_subclass__()


class FixableConfigurationError(InvalidConfigurationError):
    """Raised when a configuration is invalid - but can be auto-fixed."""

    def __init__(
        self,
        message: str,
        *,
        json_path_str: str,
        expected_value: object,
    ) -> None:
        """Initialize the error."""
        super().__init__(message)

        self.json_path_str = json_path_str
        self.expected_value = expected_value


class UnusedFileError(InvalidConfigurationError):
    """Raised when a file is not used."""

    def __init__(self, file: Path) -> None:
        """Initialize the error."""
        super().__init__(f"File not used: {file.relative_to(const.REPO_PATH)}")

        self.fmt_msg = file.relative_to(const.REPO_PATH).as_posix()


class NotFoundError(InvalidConfigurationError):
    """Raised when something isn't found."""


class DeclutteringTemplateNotFoundError(NotFoundError):
    """Raised when a decluttering template is not found."""

    def __init__(self, template: str) -> None:
        """Initialize the error."""
        super().__init__(f"Decluttering template not found: {template!r}")

        self.fmt_msg = template


class JsonPathNotFoundError(NotFoundError):
    """Raised when a JSON path is not found."""

    def __init__(self, path: str) -> None:
        """Initialize the error."""
        self.path = path
        super().__init__(f"JSON path not found but should be defined: {path!r}")

        self.fmt_msg = path


class InvalidFieldTypeError(InvalidConfigurationError):
    """Raised when a field has an invalid type."""

    def __init__(
        self,
        field: str,
        value: Any,
        expected_type: type | tuple[type, ...],
    ) -> None:
        """Initialize the error."""
        types = (
            ", ".join(type(v).__name__ for v in value)
            if isinstance(value, list)
            else type(value).__name__
        )

        super().__init__(
            f"{field} has invalid type {types}, expected {expected_type!s}",
        )


class InvalidFieldValueError(InvalidConfigurationError):
    """Raised when a field has an invalid value."""

    def __init__(self, field: str, value: Any, message: str) -> None:
        """Initialize the error."""
        super().__init__(f"{field} has invalid value {value!r}: {message}")

        self.fmt_msg = message


class InvalidEntityConsumedError(InvalidConfigurationError):
    """Raised when an entity has an invalid dependency."""

    def __init__(self, key: str, dependency: str) -> None:
        """Initialize the error."""
        super().__init__(f"{key!r} consumes `{dependency}`")


class ShouldBeHardcodedError(FixableConfigurationError):
    """Raised when a field should be hardcoded but isn't."""

    def __init__(self, json_path_str: str, value: Any, hardcoded_value: Any) -> None:
        """Initialize the error."""
        super().__init__(
            f"`{json_path_str}: {value!s}` should be hardcoded as {hardcoded_value!r}",
            json_path_str=json_path_str,
            expected_value=hardcoded_value,
        )


class ShouldBeEqualError(InvalidConfigurationError):
    """Raised when a field should match another field but doesn't."""

    def __init__(self, *, f1: str, f2: str, v1: Any, v2: Any) -> None:
        """Initialize the error."""
        v1_str = re.sub(r"\s+", " ", str(v1)).strip()
        v2_str = re.sub(r"\s+", " ", str(v2)).strip()

        super().__init__(f"{f1} `{v1_str}` should match {f2}: `{v2_str}`")


class ShouldExistError(InvalidConfigurationError):
    """Raised when a field should exist but doesn't."""

    def __init__(self, field: str, exc: JsonPathNotFoundError) -> None:
        """Initialize the error."""
        super().__init__(f"`{field}` should exist but doesn't: {exc.path}")

        self.fmt_msg = f"`{exc.path}`"


class ShouldMatchFileNameError(InvalidConfigurationError):
    """Raised when a field should match the file name but doesn't."""

    def __init__(self, json_path_str: str, value: Any, fmt_value: str) -> None:
        """Initialize the error."""
        super().__init__(
            f"{json_path_str} `{value!s}` ({fmt_value=}) should match file name",
        )


class ShouldMatchFilePathError(FixableConfigurationError):
    """Raised when a field should match the file path but doesn't."""

    def __init__(self, json_path_str: str, value: Any, expected_value: str) -> None:
        """Initialize the error."""
        super().__init__(
            f"{json_path_str} `{value!s}` != `{expected_value!s}`",
            json_path_str=json_path_str,
            expected_value=expected_value,
        )


class InvalidTemplateError(InvalidConfigurationError):
    """Raised when a Jinja template is invalid."""

    def __init__(
        self,
        jinja_exc: TemplateError,
        loc: int | str,
    ) -> None:
        super().__init__(str(jinja_exc))

        self.fmt_msg = (
            f"{(jinja_exc.message or 'Invalid template').rstrip('.')} for field `{loc}`"
        )


class InvalidTemplateVarError(InvalidConfigurationError):
    """Raised when a Jinja template has invalid/undeclared variable."""

    def __init__(self, *, undeclared_var: str, loc: int | str) -> None:
        super().__init__(f"Undeclared variable `{undeclared_var}` in field `{loc}`")


class UnexpectedScriptFieldError(InvalidConfigurationError):
    """Raised when a script is called with an unexpected field."""

    def __init__(self, script_id: str, field: str) -> None:
        """Initialize the error."""
        super().__init__(
            f"Unexpected field `{field}` for {script_id!r}",
        )


class MissingScriptFieldError(InvalidConfigurationError):
    """Raised when a script call is missing a required field."""

    def __init__(self, script_id: str, field: str) -> None:
        """Initialize the error."""
        super().__init__(
            f"Missing required field `{field}` for {script_id!r}",
        )


class SelectorIsRequiredError(InvalidConfigurationError):
    """Raised when a selector is required but not found."""

    def __init__(self, script_name: str, selector: str) -> None:
        """Initialize the error."""
        super().__init__(f"Selector missing for field `{selector}` in `script.{script_name}`")


__all__ = [
    "ConfigurationError",
    "EntityDefinitionError",
    "FileContentError",
    "FileContentTypeError",
    "HomeAssistantConfigurationError",
    "InvalidEntityConsumedError",
    "InvalidTemplateError",
    "InvalidTemplateVarError",
    "MissingScriptFieldError",
    "PackageDefinitionError",
    "PackageNotFoundError",
    "UnexpectedScriptFieldError",
    "UserPCHConfigurationError",
]
