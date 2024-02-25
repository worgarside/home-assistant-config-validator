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
LOVELACE_ARCHIVE_DIR: Final[Path] = LOVELACE_DIR / "archive"

NULL_PATH: Final[Path] = Path("/dev/null")

SNAKE_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
ENTITY_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
    flags=re.IGNORECASE,
)


COMMON_SERVICES: Final[tuple[str, ...]] = (
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

JINJA_FILTERS: Final[tuple[str, ...]] = (
    "round",
    "multiply",
    "log",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "atan2",
    "sqrt",
    "as_datetime",
    "as_timedelta",
    "as_timestamp",
    "as_local",
    "timestamp_custom",
    "timestamp_local",
    "timestamp_utc",
    "to_json",
    "from_json",
    "is_defined",
    "average",
    "random",
    "base64_encode",
    "base64_decode",
    "ordinal",
    "regex_match",
    "regex_replace",
    "regex_search",
    "regex_findall",
    "regex_findall_index",
    "bitwise_and",
    "bitwise_or",
    "pack",
    "unpack",
    "ord",
    "is_number",
    "float",
    "int",
    "slugify",
    "iif",
    "bool",
    "version",
    "contains",
)

JINJA_TESTS: Final[tuple[str, ...]] = (
    "is_number",
    "match",
    "search",
    "contains",
    "list",
)

JINJA_VARS: Final[set[str]] = {
    "as_timestamp",
    "device_attr",
    "device_id",
    "distance",
    "float",
    "has_value",
    "iif",
    "is_number",
    "is_state",
    "is_state_attr",
    "max",
    "min",
    "now",
    "repeat",
    "state_attr",
    "states",
    "this",
    "timedelta",
    "today_at",
    "trigger",
    "utcnow",
    "value_json",
    "wait",
}

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
    "LOVELACE_ARCHIVE_DIR",
    "JINJA_VARS",
]
