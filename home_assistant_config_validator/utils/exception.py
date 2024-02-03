"""Exceptions for the home_assistant_config_validator package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from home_assistant_config_validator.utils.const import ConfigurationType


class ConfigurationError(Exception):
    """Raised when a configuration error is detected."""


class UserPCHConfigurationError(ConfigurationError):
    """Raised when a error in the pre-commit hook's configuration is detected."""

    def __init__(
        self,
        configuration_type: ConfigurationType,
        package: str,
        message: str,
    ) -> None:
        """Initialize the error."""
        super().__init__(
            f"{configuration_type.value} configuration error for package {package}: {message}",
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
