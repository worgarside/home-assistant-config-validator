"""Generate a markdown file of all entities."""

from __future__ import annotations

import re
from functools import lru_cache
from logging import getLogger
from typing import TYPE_CHECKING, Final, Self

from home_assistant_config_validator.models import Package, ReadmeEntity
from home_assistant_config_validator.utils import args, const

if TYPE_CHECKING:
    from collections.abc import Iterable
    from io import TextIOWrapper
    from pathlib import Path
    from types import TracebackType

LOGGER = getLogger(__name__)


NEWLINE: Final = "\n"


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
    def is_bold(cls, line: str | None) -> bool:
        """Check if a line is bold."""
        return bool(line and line.startswith("**") and line.endswith("**"))

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
                # As should bold lines, headings and HTML
                or self.is_bold(self.previous_line)
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

    def __enter__(self) -> Self:
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
            markdown_lines: list[str] = []
            entity_count = 0
            for e in ReadmeEntity.get_for_package(pkg):
                markdown_lines.extend(e.markdown_lines)
                entity_count += 1

            if not markdown_lines:
                continue

            readme.write_line(f"## {pkg.name.replace('_', ' ').title()}")

            readme.write_line(
                f"<details><summary><h3>Entities ({entity_count})</h3></summary>",
            )
            readme.write_lines(markdown_lines)
            readme.write_line("</details>")


if __name__ == "__main__":
    args.parse_arguments()
    main()
