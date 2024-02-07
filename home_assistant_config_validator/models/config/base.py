"""Configuration classes for the Home Assistant Config Validator."""

from __future__ import annotations

from abc import ABC
from collections import defaultdict
from functools import lru_cache
from json import loads
from logging import getLogger
from re import escape, sub
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML
from wg_utilities.functions.json import JSONObj
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.utils import UserPCHConfigurationError, const

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


def replace_non_alphanumeric(
    string: str,
    ignore_chars: str = "",
    *,
    replace_with: str = "_",
) -> str:
    """Convert a string to be alphanumeric and snake_case (by default).

    Leading/trailing underscores are removed, and double (or more) underscores are
    replaced with a single underscore. Ignores values within `string` that are also in
    `ignore_strings`.

    Characters other than underscores can be replaced with a different character by
    passing `replace_with`.

    Args:
        string (str): The string to convert
        ignore_chars (str, optional): Other characters to ignore. Defaults to None.
        replace_with (str, optional): The character to replace non-alphanumeric characters
            with. Defaults to "_".

    Returns:
        str: The converted string
    """
    return (
        # The outer sub replaces double (or more) `replace_with` with a single `replace_with`
        sub(
            rf"{escape(replace_with)}{{2,}}",
            replace_with,
            # The inner sub replaces non-alphanumeric characters with `replace_with`
            sub(rf"[^a-zA-Z0-9{escape(ignore_chars)}]", replace_with, string),
        )
        .strip(replace_with)
        .casefold()
    )


class Config(BaseModel, ABC):
    """Base class for configuration classes."""

    CONFIGURATION_TYPE: ClassVar[const.ConfigurationType]
    package: Package

    INSTANCES: ClassVar[defaultdict[const.ConfigurationType, dict[Package, Self]]] = (
        defaultdict(dict)
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    @classmethod
    def get_for_package(cls, package: Package, /) -> Self:
        """Get the user's configuration for a given package."""
        if (pkg := cls.INSTANCES[cls.CONFIGURATION_TYPE].get(package)) is not None:
            return pkg  # type: ignore[return-value]

        package_config = (
            _load_user_pch_configuration()
            .get(package.pkg_name, {})
            .get(cls.CONFIGURATION_TYPE)
        )

        if package_config is not None and not isinstance(package_config, dict):
            raise TypeError(type(package_config))

        if (
            cls.CONFIGURATION_TYPE == const.ConfigurationType.VALIDATION
            and const.VALIDATE_ALL_PACKAGES
            and package_config is None
        ):
            raise UserPCHConfigurationError(
                cls.CONFIGURATION_TYPE,
                package.pkg_name,
                "not found",
            )

        return cls(package=package, **(package_config or {}))


@lru_cache
def _load_user_pch_configuration() -> dict[str, dict[const.ConfigurationType, JSONObj]]:
    if not const.PCH_CONFIG.exists():
        LOGGER.warning(
            "No user PCH configuration found at %s",
            const.PCH_CONFIG,
        )
        return {}

    if not const.PCH_CONFIG.is_file():
        raise FileNotFoundError(const.PCH_CONFIG)

    if const.PCH_CONFIG.suffix == ".json":
        return loads(const.PCH_CONFIG.read_text())["packages"]  # type: ignore[no-any-return]

    if const.PCH_CONFIG.suffix in (".yaml", ".yml"):
        return YAML(typ="safe").load(const.PCH_CONFIG.read_text())["packages"]  # type: ignore[no-any-return]

    raise ValueError(const.PCH_CONFIG.suffix)
