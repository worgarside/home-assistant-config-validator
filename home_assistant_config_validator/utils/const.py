"""Constants for the configuration validator."""

from __future__ import annotations

import re
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Any, Final, Literal
from uuid import uuid4

from wg_utilities.functions.json import TargetProcessorFunc

REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd()))

EXT: Final[Literal[".yaml"]] = ".yaml"
GLOB_PATTERN: Final[str] = f"*{EXT}"

ENTITIES_DIR: Final[Path] = REPO_PATH / "entities"
PACKAGES_DIR: Final[Path] = REPO_PATH / "integrations"
LOVELACE_DIR: Final[Path] = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE: Final[Path] = REPO_PATH.joinpath("ui-lovelace").with_suffix(EXT)
LOVELACE_ARCHIVE_DIR: Final[Path] = LOVELACE_DIR / "archive"

NULL_PATH: Final[Path] = Path("/dev/null")

SNAKE_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
ENTITY_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
    flags=re.IGNORECASE,
)


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


def create_entity_id_check_callback(
    entity_ids: set[tuple[str, str]],
) -> TargetProcessorFunc[str]:
    """Create a callback to identify entity IDs.

    Intended as a wg_utilities.function.json.TargetProcessorFunc instance.
    """

    def _cb(value: str, dict_key: str | None = None, **_: Any) -> str:
        if (
            ENTITY_ID_PATTERN.fullmatch(value)
            and value.split(".")[0] in YAML_ONLY_PACKAGES
            and value.split(".")[1] not in COMMON_SERVICES
        ):
            entity_ids.add((dict_key or "", value))

        return value

    return _cb


INEQUAL = Inequal()

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
    "create_entity_id_check_callback",
    "LOVELACE_ARCHIVE_DIR",
]
