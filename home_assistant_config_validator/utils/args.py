"""Parse CLI arguments."""

from __future__ import annotations

from argparse import ArgumentParser
from logging import Logger, getLevelNamesMapping
from os import getenv
from pathlib import Path
from typing import Literal

from home_assistant_config_validator.utils.const import EXT, REPO_PATH

AUTOFIX: bool = getenv("AUTOFIX", "0") == "1"
HA_CONFIG: Path = REPO_PATH.joinpath("configuration").with_suffix(EXT)
LOG_LEVEL: Literal[10, 20, 30, 40, 50] = getLevelNamesMapping()[  # type: ignore[assignment]
    getenv("LOG_LEVEL", "WARNING").upper()
]
PCH_CONFIG: Path = REPO_PATH / "config_validator.yml"
VALIDATE_ALL_PACKAGES: bool = getenv("VALIDATE_ALL_PACKAGES", "0") == "1"


def parse_arguments() -> None:
    """Parse arguments for the configuration validator."""
    global AUTOFIX, HA_CONFIG, LOG_LEVEL, PCH_CONFIG, VALIDATE_ALL_PACKAGES  # noqa: PLW0603

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
        help="Path to Home Assistant configuration YAML",
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

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity level. Use -v for INFO and -vv for DEBUG.",
    )

    args, _ = parser.parse_known_args()

    AUTOFIX = args.fix
    HA_CONFIG = args.ha_config_path
    PCH_CONFIG = args.pch_config_path
    VALIDATE_ALL_PACKAGES = args.validate_all

    if args.verbose == 1:
        LOG_LEVEL = 20
    elif args.verbose > 1:
        LOG_LEVEL = 10

    for k, v in Logger.manager.loggerDict.items():
        if k.startswith("home_assistant_config_validator") and isinstance(v, Logger):
            v.setLevel(LOG_LEVEL)


__all__ = [
    "AUTOFIX",
    "HA_CONFIG",
    "PCH_CONFIG",
    "VALIDATE_ALL_PACKAGES",
    "parse_arguments",
]
