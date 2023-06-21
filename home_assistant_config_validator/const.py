"""Constants for the configuration validator."""


from __future__ import annotations

import re
from argparse import ArgumentParser
from json import loads
from pathlib import Path

# Args
REPO_PATH = Path().cwd()

parser = ArgumentParser(description="Custom Component Parser")

parser.add_argument(
    "-c",
    "--config-path",
    type=Path,
    required=False,
    help="Path to custom validations configuration file.",
    default=REPO_PATH / "config_validator.json",
)

args, _ = parser.parse_known_args()

CUSTOM_VALIDATIONS = loads(args.config_path.read_text())["customValidators"]

ENTITIES_DIR = REPO_PATH / "entities"
INTEGRATIONS_DIR = REPO_PATH / "integrations"

SCRIPT_NAMES = [
    f"script.{script_file.stem}"
    for script_file in (ENTITIES_DIR / "script").rglob("*.yaml")
]

SCRIPT_NAME_PATTERN = re.compile(r"^script\.[a-z0-9_-]+$", flags=re.IGNORECASE)

SCRIPT_SERVICES = [
    "script.reload",
    "script.toggle",
    "script.turn_off",
    "script.turn_on",
]

__all__ = [
    "CUSTOM_VALIDATIONS",
    "ENTITIES_DIR",
    "INTEGRATIONS_DIR",
    "REPO_PATH",
    "SCRIPT_NAME_PATTERN",
    "SCRIPT_NAMES",
    "SCRIPT_SERVICES",
]
