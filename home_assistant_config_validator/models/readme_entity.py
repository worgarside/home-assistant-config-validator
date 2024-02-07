"""Models for the README entities."""

from __future__ import annotations

import re
from collections.abc import Generator
from dataclasses import dataclass
from functools import cached_property
from json import dumps
from pathlib import Path
from typing import Any

from home_assistant_config_validator.models.config import DocumentationConfig
from home_assistant_config_validator.utils import Entity, Secret, const
from home_assistant_config_validator.utils.helpers import get_json_value

from .package import Package


@dataclass
class ReadmeEntity:
    """A single entity to be used in the README."""

    entity: Entity
    package: Package

    @classmethod
    def get_for_package(
        cls,
        package: Package,
        /,
    ) -> Generator[ReadmeEntity, None, None]:
        """Generate a list of ReadmeEntity instances."""
        for entity_genr in package.entity_generators:
            for entity in entity_genr:
                yield cls(entity=entity, package=package)

    @staticmethod
    def markdown_format(
        __v: Any,
        /,
        *,
        target_url: str | None = None,
        code: bool = False,
        block_quote: bool = False,
    ) -> str:
        """Format a string for markdown."""
        if isinstance(__v, (dict, list, bool)):
            __v = dumps(__v, indent=2)
            code = True

        if code or (isinstance(__v, str) and const.ENTITY_ID_PATTERN.fullmatch(__v)):
            typ = type(__v)
            __v = str(__v).strip(" `")

            __v = f"\n```{typ.__name__}\n{__v}\n```" if "\n" in __v else f"`{__v}`"

        if target_url:
            __v = f"[{__v}]({target_url})"

        if block_quote:
            __v = f"> {__v}"

        return str(__v)

    @property
    def entity_id(self) -> str:
        """Estimate the entity ID."""
        e_id = self.docs_config.get_id(self.entity, default=self.entity.file__)

        return f"{self.package.name}.{e_id.stem if isinstance(e_id, Path) else e_id}"

    @property
    def description(self) -> Generator[str, None, None]:
        """Generate the description for the entity."""
        if self.docs_config.description is None:
            # No description expected
            return

        for line in str(self.docs_config.get_description(self.entity)).splitlines():
            yield self.markdown_format(line, block_quote=True)

    @cached_property
    def docs_config(self) -> DocumentationConfig:
        """Get the documentation configuration for the package."""
        return DocumentationConfig.get_for_package(self.package)

    @property
    def fields(self) -> Generator[str, None, None]:
        """Generate the fields for the entity."""
        for field in self.docs_config.extra:
            key = re.sub(
                r"(^|\s)ID(\s|$)",
                r"\1ID\2",
                field.split(".")[-1].replace("_", " ").title(),
                flags=re.IGNORECASE,
            )

            if not (val := get_json_value(self.entity, field, default=None)):
                yield f"- {key}:"
                continue

            if isinstance(val, Secret):
                val = val.resolve()

            if key.casefold() == "icon":
                url = f"https://pictogrammers.com/library/mdi/icon/{str(val).removeprefix('mdi:')}/"
                val = self.markdown_format(
                    val,
                    target_url=url,
                    code=True,
                )

            val = self.markdown_format(
                val,
                code=(key.endswith("ID") or key.casefold() == "command"),
            )

            yield f"- {key}: {val!s}"
        yield f"  File: {self.file}"

    @property
    def file(self) -> str:
        """Get the file path for the entity."""
        if path := self.entity.get("file__"):
            path = Path(str(path))
            return self.markdown_format(
                path.relative_to(const.ENTITIES_DIR),
                target_url=str(path.relative_to(const.REPO_PATH)),
                code=True,
            )

        return ""

    @property
    def header(self) -> str:
        """Generate the header for the entity."""
        header = str(self.docs_config.get_name(self.entity, default=self.entity_id))

        html_tag = "code" if set(header) & {"_", "/"} else "strong"

        return f"<details><summary><{html_tag}>{header}</{html_tag}></summary>"

    @property
    def markdown_lines(self) -> Generator[str, None, None]:
        """Generate the markdown for the entity."""
        yield self.header

        if f">{self.entity_id}<" not in self.header:
            yield f"**Entity ID: {self.markdown_format(self.entity_id, code=True)}**"

        yield from self.description
        yield from self.fields
        yield "</details>"
