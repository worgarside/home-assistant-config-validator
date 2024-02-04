"""Configuration for how to document each Package."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from home_assistant_config_validator.utils import Entity, const, parse_jsonpath

from .base import Config


class DocumentationConfig(Config):
    """Dataclass for a package's documentation configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.DOCUMENTATION]] = (
        const.ConfigurationType.DOCUMENTATION
    )

    description: str | None = Field(default=None)
    name: str = Field(default="name")
    id: str = Field(default="id")

    extra: list[str] = Field(default_factory=list)

    def get_description(self, entity: Entity, /) -> Any:
        """Return the description of the entity."""
        if self.description and (
            match := parse_jsonpath(self.description).find(entity)
        ):
            return match[0].value

        return "*No description provided*"

    def get_id(self, entity: Entity, /, *, default: Any = None) -> Any:
        """Return the ID of the entity."""
        if self.id and (match := parse_jsonpath(self.id).find(entity)):
            return match[0].value

        return default

    def get_name(self, entity: Entity, /, *, default: Any = None) -> Any:
        """Return the name of the entity."""
        if self.name and (match := parse_jsonpath(self.name).find(entity)):
            return match[0].value

        return default
