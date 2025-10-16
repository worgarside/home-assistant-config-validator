"""Constants for the configuration validator."""

from __future__ import annotations

import re
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Final
from uuid import uuid4

EXIT_1: Final[bool] = getenv("EXIT_1", "1") == "1"

REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd()))

EXT: Final = ".yaml"
GLOB_PATTERN: Final[str] = f"*{EXT}"

ENTITIES_DIR: Final[Path] = REPO_PATH / "entities"
PACKAGES_DIR: Final[Path] = REPO_PATH / "integrations"
LOVELACE_DIR: Final[Path] = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE: Final[Path] = REPO_PATH.joinpath("ui-lovelace").with_suffix(EXT)
LOVELACE_ARCHIVE_DIR: Final[Path] = LOVELACE_DIR / "archive"

NULL_PATH: Final[Path] = Path("/dev/null")

SNAKE_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
ENTITY_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)$",
    flags=re.IGNORECASE,
)


COMMON_SERVICES: Final[dict[str, set[str]]] = {
    "decrement": {"input_number"},
    "increment": {"input_number"},
    "pause": {"media_player"},
    "play": {"media_player"},
    "reload": {"automation", "script", "scene", "group"},
    "select_option": {"input_select"},
    "set_datetime": {"input_datetime"},
    "set_level": {"light", "cover"},
    "set_options": {"input_select"},
    "set": {"var"},
    "set_value": {"input_number", "input_text"},
    "start": {"script", "automation"},
    "stop": {"script", "automation"},
    "toggle": {"cover", "input_boolean", "light", "switch", "media_player"},
    "turn_off": {
        "automation",
        "input_boolean",
        "light",
        "switch",
        "media_player",
        "cover",
        "script",
        "scene",
        "group",
    },
    "turn_on": {
        "automation",
        "input_boolean",
        "light",
        "switch",
        "media_player",
        "cover",
        "script",
        "scene",
        "group",
    },
}

JINJA_ENTITY_CONSUMERS: Final[set[str]] = {
    "device_attr",
    "device_id",
    "has_value",
    "is_state",
    "is_state_attr",
    "state_attr",
    "states",
    "area_entities",
    "expand",
}


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
    "abs",
    "expand",
)

JINJA_TESTS: Final[tuple[str, ...]] = (
    "is_number",
    "match",
    "search",
    "contains",
    "list",
)

JINJA_VARS: Final[set[str]] = (
    JINJA_ENTITY_CONSUMERS
    | set(JINJA_FILTERS)
    | {
        "as_timestamp",
        "distance",
        "float",
        "iif",
        "is_number",
        "max",
        "min",
        "now",
        "null",
        "repeat",
        "this",
        "timedelta",
        "today_at",
        "trigger",
        "utcnow",
        "value_json",
        "wait",
        "area_entities",
        "expand",
        "abs",
        "label_entities",
        "slugify",
    }
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
    "COMMON_SERVICES",
    "ENTITIES_DIR",
    "INEQUAL",
    "JINJA_VARS",
    "LOVELACE_ARCHIVE_DIR",
    "LOVELACE_DIR",
    "LOVELACE_ROOT_FILE",
    "NULL_PATH",
    "PACKAGES_DIR",
    "ConfigurationType",
]
