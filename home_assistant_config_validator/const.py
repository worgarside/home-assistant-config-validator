"""Constants for the configuration validator."""


from __future__ import annotations

import re
from argparse import ArgumentParser
from json import loads
from pathlib import Path
from typing import TypedDict

from yaml import safe_load

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


class KnownEntityType(TypedDict):
    """Known entity type."""

    names: list[str]
    name_pattern: re.Pattern[str]


KNOWN_ENTITIES: dict[str, KnownEntityType] = {
    domain: {
        "names": [
            f"{domain}.{entity_file.stem}"
            for entity_file in (ENTITIES_DIR / domain).rglob("*.yaml")
        ],
        "name_pattern": re.compile(rf"^{domain}\.[a-z0-9_-]+$", flags=re.IGNORECASE),
    }
    for domain in (
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "script",
        "var",
    )
}

# Special case
KNOWN_ENTITIES["automation"] = {
    "names": [
        "automation." + safe_load(automation_file.read_text()).get("id", "")
        for automation_file in (ENTITIES_DIR / "automation").rglob("*.yaml")
    ],
    "name_pattern": re.compile(r"^automation\.[a-z0-9_-]+$", flags=re.IGNORECASE),
}

__all__ = [
    "CUSTOM_VALIDATIONS",
    "ENTITIES_DIR",
    "INTEGRATIONS_DIR",
    "REPO_PATH",
    "KNOWN_ENTITIES",
]
