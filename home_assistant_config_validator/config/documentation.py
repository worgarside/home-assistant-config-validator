"""Configuration for how to document each Package."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from home_assistant_config_validator.utils import const

from .base import Config
from .validation import ValidationConfig


@dataclass
class DocumentationConfig(Config):
    """Dataclass for a domain's documentation configuration."""

    CONFIGURATION_TYPE: ClassVar[Literal[const.ConfigurationType.DOCUMENTATION]] = (
        const.ConfigurationType.DOCUMENTATION
    )

    package_name: str

    description: str | None = field(default=None)
    name: str = field(default="name")
    id: str = field(default="id")

    extra: list[str] = field(default_factory=list)

    @property
    def validated_fields(self) -> list[str]:
        """Return a list of all fields that should be validated."""
        validator = ValidationConfig.get_for_package(self.package_name)

        fields = (
            set(validator.should_exist)
            | set(validator.should_match_filename)
            | set(validator.should_be_hardcoded.keys())
            | {smfpi["field"] for smfpi in validator.should_match_filepath}
        )

        for pair in validator.should_be_equal:
            fields.update(pair)

        return sorted(fields)

    def __iter__(self) -> Generator[str, None, None]:
        """Iterate over all fields that should be documented."""
        yield from self.validated_fields
        yield from self.extra
