"""Configuration classes for the Home Assistant Config Validator."""

from __future__ import annotations

from abc import ABC
from functools import lru_cache
from json import loads
from logging import getLogger
from re import escape, sub
from typing import ClassVar, Self

from wg_utilities.functions.json import JSONObj
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.utils import UserPCHConfigurationError, const

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

    CONFIGURATION_TYPE: ClassVar[const.ConfigurationType]
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

        if (
            cls.__name__ == "ValidationConfig"
            and const.VALIDATE_ALL_PACKAGES
            and not package_config
        ):
            raise UserPCHConfigurationError(
                cls.CONFIGURATION_TYPE,
                package_name,
                "not found",
            )

        package_config["package_name"] = package_name

        return cls(**package_config)


@lru_cache
def _load_user_pch_configuration() -> dict[str, dict[const.ConfigurationType, JSONObj]]:
    return loads(const.PCH_CONFIG.read_text())["packages"]  # type: ignore[no-any-return]
