"""Parse CLI arguments."""

from __future__ import annotations

from argparse import ArgumentParser
from os import getenv
from pathlib import Path

from home_assistant_config_validator.utils.const import REPO_PATH

AUTOFIX: bool = getenv("AUTOFIX", "0") == "1"
HA_CONFIG: Path = REPO_PATH / "configuration.yaml"
PCH_CONFIG: Path = REPO_PATH / "config_validator.yml"
VALIDATE_ALL_PACKAGES: bool = getenv("VALIDATE_ALL_PACKAGES", "0") == "1"


def parse_arguments() -> None:
    """Parse arguments for the configuration validator."""
    global AUTOFIX, HA_CONFIG, PCH_CONFIG, VALIDATE_ALL_PACKAGES  # noqa: PLW0603

    parser = ArgumentParser(description="Custom Component Parser")

    parser.add_argument(
        "-f",
        "--fix",
        action="store_true",
        help="Automatically fix applicable values.",
        default=AUTOFIX,
    )

    parser.add_argument(
        "-c",
        "--ha-config-path",
        type=Path,
        required=False,
        help="Path to Home Assistant configuration.yaml",
        default=HA_CONFIG,
    )

    parser.add_argument(
        "-p",
        "--pch-config-path",
        type=Path,
        required=False,
        help="Path to custom validations configuration file.",
        default=PCH_CONFIG,
    )
    parser.add_argument(
        "-a",
        "--validate-all",
        action="store_true",
        help="Validate all packages (requires exactly one configuration per package).",
        default=VALIDATE_ALL_PACKAGES,
    )

    args, _ = parser.parse_known_args()

    AUTOFIX = args.fix
    HA_CONFIG = args.ha_config_path
    PCH_CONFIG = args.pch_config_path
    VALIDATE_ALL_PACKAGES = args.validate_all


__all__ = [
    "AUTOFIX",
    "HA_CONFIG",
    "PCH_CONFIG",
    "VALIDATE_ALL_PACKAGES",
    "parse_arguments",
]
