"""Validate Home Assistant configurations."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.models.config import (
    ValidationConfig,
)
from home_assistant_config_validator.utils import (
    InvalidConfigurationError,
    args,
    format_output,
)
from home_assistant_config_validator.utils.const import EXIT_1

if TYPE_CHECKING:
    from pathlib import Path


def main() -> bool:
    """Validate all entities."""
    all_issues: dict[str, dict[Path, list[InvalidConfigurationError]]] = {}

    for pkg in Package.get_packages():
        if not pkg.entity_generators__:
            continue

        all_issues[pkg.pkg_name] = ValidationConfig.get_for_package(pkg).validate_package()

    if any(all_issues.values()):
        print(format_output(all_issues), file=sys.stderr)

        return EXIT_1

    return False


if __name__ == "__main__":
    args.parse_arguments()
    sys.exit(main())
