"""Generate a markdown file of all entities."""

from __future__ import annotations

import re
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from io import TextIOWrapper
from logging import getLogger
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar, Final, Literal, Self

from wg_utilities.functions.json import JSONObj, process_json_object
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.config import DocumentationConfig, ParserConfig
from home_assistant_config_validator.utils import (
    PackageDefinitionError,
    PackageNotFoundError,
    Secret,
    TagWithPath,
    const,
    load_yaml,
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)

NEWLINE: Final[Literal["\n"]] = "\n"


@dataclass
class Package:
    """A package of entities.

    https://www.home-assistant.io/docs/configuration/packages
    """

    INSTANCES: ClassVar[dict[str, Self]] = {}

    pkg_name: str
    name: str
    entities: list[JSONObj] = field(default_factory=list)

    def __post_init__(self: Self) -> None:
        """Add the instance to the instances dict."""
        if (instance := self.INSTANCES.get(self.pkg_name)) is None:
            self.INSTANCES[self.pkg_name] = self
        elif instance != self:
            raise PackageDefinitionError(
                const.PACKAGES_DIR.joinpath(self.pkg_name),
                f"Can't have multiple packages with same name ({self.pkg_name})",
            )

    @classmethod
    def get_packages(cls) -> Generator[Package, None, None]:
        """Generate all packages."""
        for pkg_file in sorted(const.PACKAGES_DIR.glob("*.yaml")):
            yield cls.by_name(pkg_file.stem)

    @classmethod
    def by_name(cls, name: str, /, *, allow_creation: bool = True) -> Package:
        """Get or create a package by its name."""
        if (self := cls.INSTANCES.get(name)) is not None:
            return self

        if (
            allow_creation
            and const.PACKAGES_DIR.joinpath(name).with_suffix(".yaml").is_file()
        ):
            return cls.parse_file(
                const.PACKAGES_DIR.joinpath(name).with_suffix(".yaml"),
            )

        raise PackageNotFoundError(const.PACKAGES_DIR.joinpath(name))

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
                file.relative_to(const.REPO_PATH),
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

        if (pkg := cls.INSTANCES.get(file.stem)) is None:
            return cls(pkg_name=file.stem, name=name, entities=entities)

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

    @cached_property
    def readme_entities(self) -> Generator[ReadmeEntity, None, None]:
        """Generate a list of ReadmeEntity instances."""
        yield from (ReadmeEntity(self, self.parser.parse(e)) for e in self.entities)

    @property
    def readme_lines(self) -> Generator[str, None, None]:
        """Generate the section for the package in the README."""
        yield f"## {self.name.replace('_', ' ').title()}"

        if not self.entities:
            yield "### [No Entities]"
            return

        yield f"<details><summary><h3>Entities ({len(self.entities)})</h3></summary>"

        for entity in self.readme_entities:
            yield from entity.markdown_lines

        yield "</details>"


@dataclass
class ReadmeEntity:
    """A single entity to be used in the README."""

    package: Package

    entity: JSONObj

    @staticmethod
    def markdown_format(
        __value: Any,
        /,
        *,
        target_url: str | None = None,
        code: bool = False,
        block_quote: bool = False,
    ) -> str:
        """Format a string for markdown."""
        __value = (
            str(__value).lower()
            if isinstance(__value, bool)
            else str(__value).strip(" `")
        )

        if code or re.fullmatch(r"^[a-z_]+\.?[a-z_]+$", __value):
            __value = f"`{__value or ' '}`"

        if target_url:
            __value = f"[{__value}]({target_url})"

        if block_quote:
            __value = f"> {__value}"

        return str(__value)

    @property
    def entity_id(self) -> str:
        """Estimate the entity ID."""
        e_id = self.entity.get(self.package.docs.id, self.entity["__file__"])

        if isinstance(e_id, Path):
            e_id = e_id.stem

        return f"{self.package.name}.{e_id}"

    @property
    def description(self) -> Generator[str, None, None]:
        """Generate the description for the entity."""
        if self.package.docs.description is None:
            return

        for line in str(
            self.entity.get(
                self.package.docs.description,
                "*No description provided*",
            ),
        ).splitlines():
            yield self.markdown_format(line, block_quote=True)

    @property
    def fields(self) -> Generator[str, None, None]:
        """Generate the fields for the entity."""
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
                val = val.resolve()

            if key.casefold() == "icon":
                url = f"https://pictogrammers.com/library/mdi/icon/{str(val).removeprefix('mdi:')}/"
                val = self.markdown_format(
                    val,
                    target_url=url,
                    code=True,
                )
            elif (
                key.endswith("ID")
                or key.casefold() == "command"
                or isinstance(val, bool)
            ):
                val = self.markdown_format(val, code=True)

            yield f"- {key}: {val!s}"

    @property
    def file(self) -> str:
        """Get the file path for the entity."""
        if path := self.entity.get("__file__"):
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
        header = str(self.entity.get(self.package.docs.name, self.entity_id))

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


class Readme:
    """A context manager for writing the README."""

    PATH: Final[Path] = const.PACKAGES_DIR.joinpath("README.md")

    HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#+\s")
    LIST_ITEM_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*-\s")

    _fout: TextIOWrapper

    def __init__(self) -> None:
        """Initialize the previous line attribute."""
        self.previous_line: str | None = None

    @classmethod
    @lru_cache(maxsize=12)
    def is_heading(cls, line: str | None) -> bool:
        """Check if a line is a heading."""
        return bool(line and cls.HEADING_PATTERN.match(line))

    @classmethod
    @lru_cache(maxsize=12)
    def is_html(cls, line: str | None) -> bool:
        """Check if a line is (wrapped in) an HTML tag."""
        return bool(line and line.startswith("<") and line.endswith(">"))

    @classmethod
    @lru_cache(maxsize=12)
    def is_list_item(cls, line: str | None) -> bool:
        """Check if a line is a list item."""
        return bool(line and cls.LIST_ITEM_PATTERN.match(line))

    def write_line(self, line: str) -> None:
        """Write a line to the file."""
        if line != NEWLINE:
            line = line.strip()

            if self.previous_line is not None and (
                # Lists should be surrounded by newlines
                (self.is_list_item(line) != self.is_list_item(self.previous_line))
                # As should headings and HTML
                or self.is_heading(self.previous_line)
                or self.is_html(self.previous_line)
            ):
                self.write_line(NEWLINE)

        self._fout.write(line)
        if line != NEWLINE:
            self._fout.write(NEWLINE)

        self.previous_line = line

    def write_lines(self, lines: Iterable[str]) -> None:
        """Write multiple lines to the file."""
        for line in lines:
            self.write_line(line)

    def __enter__(self) -> Readme:
        """Open the file for writing."""
        self._fout = self.PATH.open("w", encoding="utf-8")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the file."""
        self._fout.close()

        if exc_type is not None:
            LOGGER.error(
                "Error occurred while writing README",
                exc_info=(exc_type, exc_value, traceback),  # type: ignore[arg-type]
            )
        else:
            LOGGER.info("README generated at %s", self.PATH)


def main() -> None:
    """Generate the README for the packages."""
    with Readme() as readme:
        readme.write_line("# Packages")

        for pkg in Package.get_packages():
            readme.write_lines(pkg.readme_lines)


if __name__ == "__main__":
    main()
