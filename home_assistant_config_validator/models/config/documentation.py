"""Configuration for how to document each Package."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from home_assistant_config_validator.utils import (
    Entity,
    JSONPathStr,
    const,
    parse_jsonpath,
)
from home_assistant_config_validator.utils.exception import FileContentError

from .base import Config


class DocumentationConfig(Config):
    """Dataclass for a package's documentation configuration."""

    CONFIGURATION_TYPE: ClassVar[
        Literal[const.ConfigurationType.DOCUMENTATION]
    ] = const.ConfigurationType.DOCUMENTATION

    description: str | None = Field(default=None)
    name: str = Field(default="name")
    id: str = Field(default="id")

    extra: list[JSONPathStr] = Field(default_factory=list)

    def get_description(self, entity: Entity, /) -> str:
        """Return the description of the entity."""
        if self.description and (match := parse_jsonpath(self.description).find(entity)):
            return str(match[0].value)

        return "*No description provided*"

    def get_id(self, entity: Entity, /, *, prefix_domain: bool = False) -> str:
        """Return the ID of the entity."""
        if self.id == "__file__":
            id_ = entity.file__.stem
        elif match := parse_jsonpath(self.id).find(entity):
            id_ = str(match[0].value)
        else:
            raise FileContentError(
                entity.file__,
                f"ID `{self.id}` not found in entity",
            )

        if prefix_domain:
            return f"{self.package.name}.{id_}"

        return id_

    def get_name(self, entity: Entity, /, *, default: str | None = None) -> str | None:
        """Return the name of the entity."""
        if self.name and (match := parse_jsonpath(self.name).find(entity)):
            return str(match[0].value)

        return default
