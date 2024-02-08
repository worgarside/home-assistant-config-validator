"""Constants for the configuration validator."""

from __future__ import annotations

import re
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Final
from uuid import uuid4

REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd()))

ENTITIES_DIR: Final[Path] = REPO_PATH / "entities"
PACKAGES_DIR: Final[Path] = REPO_PATH / "integrations"
LOVELACE_DIR: Final[Path] = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE: Final[Path] = REPO_PATH / "ui-lovelace.yaml"

NULL_PATH: Final[Path] = Path("/dev/null")

ENTITY_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z_]+\.?[a-z_]+$")


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
]
