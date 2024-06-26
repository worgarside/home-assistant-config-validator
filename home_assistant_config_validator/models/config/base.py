"""Configuration classes for the Home Assistant Config Validator."""

from __future__ import annotations

from abc import ABC
from collections import defaultdict
from functools import lru_cache
from json import loads
from logging import getLogger
from re import escape, sub
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML

from home_assistant_config_validator.models import Package  # noqa: TCH001
from home_assistant_config_validator.utils import args, const, exc

if TYPE_CHECKING:
    from collections.abc import Iterable

LOGGER = getLogger(__name__)


def replace_non_alphanumeric(
    string: str,
    ignore_chars: Iterable[str] = "",
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
    if not isinstance(ignore_chars, str):
        ignore_chars = "".join(ignore_chars)

    # Replaces non-alphanumeric characters with `replace_with`
    formatted = sub(rf"[^a-zA-Z0-9{escape(ignore_chars)}]", replace_with, escape(string))

    if replace_with:
        # Replaces double (or more) `replace_with` with a single `replace_with`
        formatted = sub(
            rf"{escape(replace_with)}{{2,}}",
            replace_with,
            formatted,
        )

    if replace_with != " ":
        # Replace double (or more) spaces with a single space
        formatted = sub(r"\s{2,}", " ", formatted)

    return formatted.casefold().strip(replace_with)


class Config(BaseModel, ABC):
    """Base class for configuration classes."""

    CONFIGURATION_TYPE: ClassVar[const.ConfigurationType]
    package: Package

    INSTANCES: ClassVar[defaultdict[const.ConfigurationType, dict[Package, Self]]] = (
        defaultdict(dict)
    )

    GLOBAL_CONFIG: ClassVar[BaseModel]
    _GLOBAL_CONFIG_CLASS: ClassVar[type[BaseModel]]

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    @classmethod
    def get_for_package(cls, package: Package, /) -> Self:
        """Get the user's configuration for a given package."""
        if (pkg := cls.INSTANCES[cls.CONFIGURATION_TYPE].get(package)) is not None:
            return pkg  # type: ignore[return-value]

        try:
            package_config = (
                cls.user_configuration()
                .get("packages", {})
                .get(package.pkg_name, {})
                .get(cls.CONFIGURATION_TYPE)
            )
        except Exception as err:
            raise exc.UserPCHConfigurationError(
                cls.CONFIGURATION_TYPE,
                package.pkg_name,
                repr(err),
            ) from err

        if not hasattr(cls, "GLOBAL_CONFIG"):
            cls.GLOBAL_CONFIG = cls._GLOBAL_CONFIG_CLASS.model_validate(
                cls.user_configuration().get(cls.CONFIGURATION_TYPE.lower(), {}),
            )

        if (
            cls.CONFIGURATION_TYPE == const.ConfigurationType.VALIDATION
            and args.VALIDATE_ALL_PACKAGES
            and package_config is None
        ):
            raise exc.UserPCHConfigurationError(
                cls.CONFIGURATION_TYPE,
                package.pkg_name,
                "not found",
            )

        return cls(package=package, **(package_config or {}))

    @staticmethod
    @lru_cache
    def user_configuration() -> (
        dict[str, dict[str, dict[const.ConfigurationType, dict[str, object]]]]
    ):
        """Return the user's PCH configuration."""
        if not args.PCH_CONFIG.exists():
            LOGGER.warning(
                "No user PCH configuration found at %s",
                args.PCH_CONFIG,
            )
            return {}

        if not args.PCH_CONFIG.is_file():
            raise FileNotFoundError(args.PCH_CONFIG)

        if args.PCH_CONFIG.suffix == ".json":
            return loads(args.PCH_CONFIG.read_text())  # type: ignore[no-any-return]

        if args.PCH_CONFIG.suffix in (".yaml", ".yml"):
            return YAML(typ="safe").load(args.PCH_CONFIG)  # type: ignore[no-any-return]

        raise ValueError(args.PCH_CONFIG.suffix)
