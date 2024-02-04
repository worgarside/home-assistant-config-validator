"""Configuration for how to document each Package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from wg_utilities.functions.json import JSONObj

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.utils import const
from home_assistant_config_validator.utils import parse_jsonpath

from .base import Config


@dataclass
class DocumentationConfig(Config):
    """Dataclass for a package's documentation configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.DOCUMENTATION]] = (
        const.ConfigurationType.DOCUMENTATION
    )

    package: Package

    description: str | None = field(default=None)
    name: str = field(default="name")
    id: str = field(default="id")

    extra: list[str] = field(default_factory=list)

    def get_description(self, entity: JSONObj, /) -> Any:
        """Return the description of the entity."""
        if self.description and (
            match := parse_jsonpath(self.description).find(entity)
        ):
            return match[0].value

        return "*No description provided*"

    def get_id(self, entity: JSONObj, /, *, default: Any = None) -> Any:
        """Return the ID of the entity."""
        if self.id and (match := parse_jsonpath(self.id).find(entity)):
            return match[0].value

        return default

    def get_name(self, entity: JSONObj, /, *, default: Any = None) -> Any:
        """Return the name of the entity."""
        if self.name and (match := parse_jsonpath(self.name).find(entity)):
            return match[0].value

        return default
