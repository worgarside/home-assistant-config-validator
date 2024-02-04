"""Constants for the configuration validator."""

from __future__ import annotations

from argparse import ArgumentParser
from enum import StrEnum
from os import getenv
from pathlib import Path
from typing import Final

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

args, _ = parser.parse_known_args()


PCH_CONFIG: Path = args.pch_config_path
VALIDATE_ALL_PACKAGES: bool = args.validate_all
HA_CONFIG: Path = args.ha_config_path

ENTITIES_DIR: Final[Path] = REPO_PATH / "entities"
PACKAGES_DIR: Final[Path] = REPO_PATH / "integrations"
LOVELACE_DIR: Final[Path] = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE: Final[Path] = REPO_PATH / "ui-lovelace.yaml"

NULL_PATH: Final[Path] = Path("/dev/null")


class ConfigurationType(StrEnum):
    """Enum for the different types of configurations."""

    DOCUMENTATION = "documentation"
    VALIDATION = "validation"


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
]
