"""Configuration for how to parse each Package's content."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Literal

from wg_utilities.functions.json import JSONObj

from home_assistant_config_validator.utils import const

from .base import Config


@dataclass
class ParserConfig(Config):
    """Dataclass for a domain's parser configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.PARSER]] = (
        const.ConfigurationType.PARSER
    )

    package_name: str

    top_level_keys: list[str] = field(default_factory=list)

    def parse(self, __obj: JSONObj, /) -> JSONObj:
        """Parse a JSON object."""
        if self.top_level_keys:
            __file__ = __obj.pop("__file__", None)

            if (
                len(__obj) == 1
                and (only_key := next(iter(__obj.keys()))) in self.top_level_keys
            ):
                new_obj: JSONObj = __obj.pop(only_key)  # type: ignore[assignment]
            else:
                new_obj = __obj

            if __file__:
                new_obj["__file__"] = __file__

            return new_obj

        return __obj


__all__ = ["ParserConfig"]
