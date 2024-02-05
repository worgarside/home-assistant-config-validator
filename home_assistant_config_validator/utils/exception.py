"""Exceptions for the home_assistant_config_validator package."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from home_assistant_config_validator.utils import const


class ConfigurationError(Exception):
    """Raised when a configuration error is detected."""


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
            f"{configuration_type} configuration error for package {package}: {message}",
        )


class HomeAssistantConfigurationError(ConfigurationError):
    """Raised when a Home Assistant configuration error is detected."""


class FileContentError(HomeAssistantConfigurationError):
    """Raised when the content of a file is invalid."""

    def __init__(self, file: Path, message: str | None = None) -> None:
        """Initialize the error."""
        msg = f"Invalid content in file {file}"

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
        msg = f"expected {expected_type}, got {type(content)}"

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

    def __init__(self, message: str) -> None:
        """Initialize the error."""
        super().__init__(message)

        if not hasattr(self, "fmt_msg"):
            self.fmt_msg = message


class UnusedFileError(InvalidConfigurationError):
    """Raised when a file is not used."""

    def __init__(self, file: Path) -> None:
        """Initialize the error."""
        super().__init__(f"File not used: {file}")

        self.fmt_msg = file.as_posix()


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
        if isinstance(value, list):
            types = ", ".join(type(v).__name__ for v in value)
        else:
            types = type(value).__name__

        super().__init__(
            f"{field} has invalid type {types}, expected {expected_type!s}",
        )


class InvalidFieldValueError(InvalidConfigurationError):
    """Raised when a field has an invalid value."""

    def __init__(self, field: str, value: Any, message: str) -> None:
        """Initialize the error."""
        super().__init__(f"{field} has invalid value {value!r}: {message}")

        self.fmt_msg = message


class ShouldBeHardcodedError(InvalidConfigurationError):
    """Raised when a field should be hardcoded but isn't."""

    def __init__(self, field: str, value: Any, hardcoded_value: Any) -> None:
        """Initialize the error."""
        super().__init__(
            f"`{field}: {value!s}` should be hardcoded as {hardcoded_value!r}",
        )


class ShouldBeEqualError(InvalidConfigurationError):
    """Raised when a field should match another field but doesn't."""

    def __init__(self, *, f1: str, f2: str, v1: Any, v2: Any) -> None:
        """Initialize the error."""
        v1_str = re.sub(r"\s+", " ", str(v1)).strip()
        v2_str = re.sub(r"\s+", " ", str(v2)).strip()

        super().__init__(f'`{f1}: "{v1_str}"` should match `{f2}: "{v2_str}"`')


class ShouldExistError(InvalidConfigurationError):
    """Raised when a field should exist but doesn't."""

    def __init__(self, field: str, exc: JsonPathNotFoundError) -> None:
        """Initialize the error."""
        super().__init__(f"`{field}` should exist but doesn't: {exc.path}")

        self.fmt_msg = exc.fmt_msg


class ShouldMatchFileNameError(InvalidConfigurationError):
    """Raised when a field should match the file name but doesn't."""

    def __init__(self, field: str, value: Any, fmt_value: str) -> None:
        """Initialize the error."""
        super().__init__(
            f"`{field}: {value!s}` ({fmt_value=}) should match file name",
        )


class ShouldMatchFilePathError(InvalidConfigurationError):
    """Raised when a field should match the file path but doesn't."""

    def __init__(self, field: str, value: Any, expected_value: str) -> None:
        """Initialize the error."""
        super().__init__(
            f"`{field}: {(value or 'null')!s}` should match file path: `{expected_value!s}`",
        )


__all__ = [
    "ConfigurationError",
    "UserPCHConfigurationError",
    "HomeAssistantConfigurationError",
    "FileContentError",
    "FileContentTypeError",
    "EntityDefinitionError",
    "PackageNotFoundError",
    "PackageDefinitionError",
]
