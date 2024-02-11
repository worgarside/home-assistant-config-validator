"""Constants for the configuration validator."""

from __future__ import annotations

import re
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Final, Literal
from uuid import uuid4

REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd()))

EXT: Final[Literal[".yaml"]] = ".yaml"
GLOB_PATTERN: Final[str] = f"*{EXT}"

ENTITIES_DIR: Final[Path] = REPO_PATH / "entities"
PACKAGES_DIR: Final[Path] = REPO_PATH / "integrations"
LOVELACE_DIR: Final[Path] = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE: Final[Path] = REPO_PATH.joinpath("ui-lovelace").with_suffix(EXT)

NULL_PATH: Final[Path] = Path("/dev/null")

SNAKE_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
ENTITY_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
    flags=re.IGNORECASE,
)


class ConfigurationType(StrEnum):
    """Enum for the different types of configurations."""

    DOCUMENTATION = "documentation"
    VALIDATION = "validation"


class Inequal:
    def __eq__(self, _: object) -> bool:
        return False

    def __ne__(self, _: object) -> bool:
        return True

    def __hash__(self) -> int:
        return uuid4().int


INEQUAL = Inequal()

COMMON_SERVICES = (
    "decrement",
    "increment",
    "pause",
    "play",
    "reload",
    "select_option",
    "set_datetime",
    "set_level",
    "set_options",
    "set_value",
    "set_value",
    "start",
    "stop",
    "toggle",
    "turn_off",
    "turn_on",
)

YAML_ONLY_PACKAGES: Final[tuple[str, ...]] = (
    "automation",
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "script",
    "shell_command",
    "var",
)

__all__ = [
    "ENTITIES_DIR",
    "PACKAGES_DIR",
    "LOVELACE_DIR",
    "LOVELACE_ROOT_FILE",
    "NULL_PATH",
    "ConfigurationType",
    "INEQUAL",
    "COMMON_SERVICES",
    "YAML_ONLY_PACKAGES",
]
