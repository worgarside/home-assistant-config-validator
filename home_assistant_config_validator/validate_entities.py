"""Validate Home Assistant configurations."""

from __future__ import annotations

import sys
from pathlib import Path

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.models.config import ValidationConfig
from home_assistant_config_validator.utils import (
    InvalidConfigurationError,
    format_output,
)


def main() -> None:
    """Validate all entities."""
    all_issues: dict[str, dict[Path, list[InvalidConfigurationError]]] = {}

    for pkg in Package.get_packages():
        if not pkg.entity_generators:
            continue

        validator = ValidationConfig.get_for_package(pkg)

        validator.validate_package()

        if validator.issues:
            all_issues[pkg.pkg_name] = validator.issues

    if not all_issues:
        sys.exit(0)

    sys.exit(format_output(all_issues))


if __name__ == "__main__":
    main()
