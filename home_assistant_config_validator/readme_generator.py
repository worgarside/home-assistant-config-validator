"""Generate a markdown file of all entities."""

from __future__ import annotations

import re
from collections.abc import Generator
from dataclasses import dataclass, field
from functools import cached_property
from logging import getLogger
from pathlib import Path
from typing import Any, ClassVar, Self, cast

from wg_utilities.functions.json import JSONObj, process_json_object
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.config import DocumentationConfig, ParserConfig
from home_assistant_config_validator.const import (
    ENTITIES_DIR,
    HA_CONFIG,
    NULL_PATH,
    PACKAGES_DIR,
    REPO_PATH,
)
from home_assistant_config_validator.exception import (
    EntityDefinitionError,
    PackageDefinitionError,
    PackageNotFoundError,
)
from home_assistant_config_validator.ha_yaml_loader import (
    IncludeDirNamed,
    Secret,
    Tag,
    TagWithPath,
    load_yaml,
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


@dataclass
class Package:
    """A package of entities.

    https://www.home-assistant.io/docs/configuration/packages
    """

    INSTANCES: ClassVar[dict[str, Self]] = {}

    name: str
    entities: list[JSONObj] = field(default_factory=list)

    def __post_init__(self: Self) -> None:
        """Add the instance to the instances dict."""
        if (instance := self.INSTANCES.get(self.name)) is None:
            self.INSTANCES[self.name] = self
        elif instance != self:
            raise PackageDefinitionError(
                PACKAGES_DIR.joinpath(self.name),
                "Can't have multiple packages with same name",
            )

    @classmethod
    def by_name(cls, name: str, /, *, allow_creation: bool = True) -> Package:
        """Get or create a package by its name."""
        if (self := cls.INSTANCES.get(name)) is not None:
            return self

        if (
            allow_creation
            and PACKAGES_DIR.joinpath(name).with_suffix(".yaml").is_file()
        ):
            return cls.parse_file(PACKAGES_DIR.joinpath(name).with_suffix(".yaml"))

        raise PackageNotFoundError(PACKAGES_DIR.joinpath(name))

    @classmethod
    def parse_file(cls, file: Path) -> Package:
        """Parse a file from the packages directory."""
        # TODO add check that the file is in the integs dir

        package_config: JSONObj = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=JSONObj,
        )

        if len(package_config) == 1:
            name = str(next(iter(package_config)))
        elif len(key_set := {str(k).split()[0] for k in package_config}) == 1:
            name = key_set.pop()

            LOGGER.warning(
                "Found package in file %s with split keys, combined into: %r",
                file.relative_to(REPO_PATH),
                name,
            )
        else:
            raise PackageDefinitionError(file, f"invalid split keys {key_set!r}")

        entities: list[JSONObj] = []

        def _add_to_entities_and_resolve(
            value: TagWithPath[Any, Any],
            **_: Any,
        ) -> Any:
            entities.extend(value.entities)
            return value.resolve(resolve_tags=False)

        process_json_object(
            package_config,
            target_type=TagWithPath,
            target_processor_func=_add_to_entities_and_resolve,
            pass_on_fail=False,
            log_op_func_failures=False,
        )

        if (pkg := cls.INSTANCES.get(name)) is None:
            return cls(name=name, entities=entities)

        pkg.entities.extend(entities)

        return pkg

    @cached_property
    def docs(self) -> DocumentationConfig:
        """Get the user's documentation config for the package."""
        return DocumentationConfig.get_for_package(self.name)

    @cached_property
    def parser(self) -> ParserConfig:
        """Get the user's parser config for the package."""
        return ParserConfig.get_for_package(self.name)

    @property
    def all_entities(self) -> Generator[JSONObj, None, None]:
        """Combine all entities from all files and return a single list."""
        for v in self.entities:
            if isinstance(v, list):
                yield from v
            elif isinstance(v, Tag) and v.RESOLVES_TO is list:
                yield from v.resolve(v.file, resolve_tags=True)
            elif isinstance(v, dict):
                yield v
            elif v is not None:
                raise EntityDefinitionError(NULL_PATH, str(v))

    @cached_property
    def readme_entities(self) -> Generator[ReadmeEntity, None, None]:
        """Generate a list of ReadmeEntity instances."""
        yield from (ReadmeEntity(self, self.parser.parse(e)) for e in self.all_entities)

    @property
    def readme_section(self) -> str:
        """Generate the section for the package in the README."""
        title = f"## {self.name.replace('_', ' ').title()}"

        if not (readme_entities := list(self.readme_entities)):
            return f"\n{title}\n\n### [No Entities]"

        readme = (
            title
            + f"\n\n<details><summary><h3>Entities ({len(readme_entities)})</h3></summary>"
        )

        for entity in readme_entities:
            readme += f"\n\n{entity.markdown}"

        return readme + "\n</details>"


@dataclass
class ReadmeEntity:
    """A single entity to be used in the README."""

    package: Package

    entity: JSONObj

    @staticmethod
    def markdown_format(
        __value: str,
        /,
        *,
        target_url: str | None = None,
        code: bool = False,
        block_quote: bool = False,
    ) -> str:
        """Format a string for markdown."""
        __value = __value.strip(" `")

        if code or re.fullmatch(r"^[a-z_]+\.?[a-z_]+$", __value):
            __value = f"`{__value or ' '}`"

        if target_url:
            __value = f"[{__value}]({target_url})"

        if block_quote:
            __value = f"> {__value}"

        return __value

    @property
    def entity_id(self) -> str:
        """Estimate the entity ID."""
        e_id = self.entity.get(self.package.docs.id, self.entity["__file__"])

        if isinstance(e_id, Path):
            e_id = e_id.stem

        return f"{self.package.name}.{e_id}"

    @property
    def description(self) -> str:
        """Generate the description for the entity."""
        if self.package.docs.description is None:
            return ""

        return "\n".join(
            self.markdown_format(line, block_quote=True)
            for line in str(
                self.entity.get(
                    self.package.docs.description,
                    "*No description provided*",
                ),
            ).splitlines()
        )

    @property
    def fields(self) -> Generator[str, None, None]:
        """Generate the fields for the entity."""
        yield ""
        yield f"- File: {self.file}"

        for f in self.package.docs:
            key = re.sub(
                r"(^|\s)ID(\s|$)",
                r"\1ID\2",
                f.replace("_", " ").title(),
                flags=re.IGNORECASE,
            )

            if not (val := self.entity.get(f)):
                yield f"- {key}:"
                continue

            if isinstance(val, Secret):
                val = val.resolve(resolve_tags=True)

            if key.casefold() == "icon":
                url = f"https://pictogrammers.com/library/mdi/icon/{str(val).removeprefix('mdi:')}/"
                val = self.markdown_format(
                    str(val),
                    target_url=url,
                    code=True,
                )
            elif key.endswith("ID") or key.casefold() == "command":
                val = self.markdown_format(str(val), code=True)

            yield f"- {key}: {val!s}"

        yield ""
        yield ""

    @property
    def file(self) -> str:
        """Get the file path for the entity."""
        if path := self.entity.get("__file__"):
            path = Path(str(path))
            return self.markdown_format(
                str(path.relative_to(ENTITIES_DIR)),
                target_url=str(path.relative_to(REPO_PATH)),
                code=True,
            )

        return ""

    @property
    def header(self) -> str:
        """Generate the header for the entity."""
        header = str(self.entity.get(self.package.docs.name, self.entity_id))

        html_tag = "code" if set(header) & {"_", "/"} else "strong"

        return f"<details><summary><{html_tag}>{header}</{html_tag}></summary>\n"

    @property
    def markdown(self) -> str:
        """Generate the markdown for the entity."""
        lines = [self.header]

        if f">{self.entity_id}<" not in self.header:
            lines.append(
                f"  ##### Entity ID: {self.markdown_format(self.entity_id, code=True)}",
            )

        lines.append(self.description)
        lines.extend(self.fields)
        lines.append("</details>")

        return "\n".join(lines)


def main() -> None:
    """Generate the README for the packages."""
    configuration_yaml = load_yaml(
        HA_CONFIG,
        resolve_tags=False,
        validate_content_type=JSONObj,
    )

    packages_tag = cast(
        IncludeDirNamed,
        configuration_yaml["homeassistant"]["packages"],  # type: ignore[call-overload,index]
    )

    readme = "# Packages"

    for pkg_file in sorted(packages_tag.absolute_path.glob("*.yaml")):
        readme += f"\n\n{Package.by_name(pkg_file.stem).readme_section}"

    PACKAGES_DIR.joinpath("README.md").write_text(readme)

    LOGGER.info("README.md generated in %s", PACKAGES_DIR)


if __name__ == "__main__":
    main()
