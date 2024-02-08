"""Constants for the configuration validator."""

from __future__ import annotations

import re
from argparse import ArgumentParser
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Final
from uuid import uuid4

REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd().absolute().as_posix()))

# Args

parser = ArgumentParser(description="Custom Component Parser")

parser.add_argument(
    "-p",
    "--pch-config-path",
    type=Path,
    required=False,
    help="Path to custom validations configuration file.",
    default=REPO_PATH / "config_validator.yml",
)

parser.add_argument(
    "-a",
    "--validate-all",
    action="store_true",
    help="Validate all packages (requires exactly one configuration per package).",
    default=getenv("VALIDATE_ALL_PACKAGES", "0") == "1",
)

parser.add_argument(
    "-c",
    "--ha-config-path",
    type=Path,
    required=False,
    help="Path to Home Assistant configuration.yaml",
    default=REPO_PATH / "configuration.yaml",
)

parser.add_argument(
    "-f",
    "--fix",
    action="store_true",
    help="Automatically fix applicable values.",
    default=getenv("AUTOFIX", "0") == "1",
)

args, _ = parser.parse_known_args()


PCH_CONFIG: Path = args.pch_config_path
VALIDATE_ALL_PACKAGES: bool = args.validate_all
HA_CONFIG: Path = args.ha_config_path
AUTOFIX: bool = args.fix

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
    "PCH_CONFIG",
    "VALIDATE_ALL_PACKAGES",
    "HA_CONFIG",
    "ENTITIES_DIR",
    "PACKAGES_DIR",
    "LOVELACE_DIR",
    "LOVELACE_ROOT_FILE",
    "NULL_PATH",
    "ConfigurationType",
    "INEQUAL",
]
