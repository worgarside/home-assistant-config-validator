"""Validate Home Assistant configurations."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.models.config import (
    ValidationConfig,
)
from home_assistant_config_validator.utils import (
    InvalidConfigurationError,
    args,
    format_output,
)


def main() -> None:
    """Validate all entities."""
    args.parse_arguments()

    all_issues: dict[str, dict[Path, list[InvalidConfigurationError]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for pkg in Package.get_packages():
        if not pkg.entity_generators__:
            continue

        validator = ValidationConfig.get_for_package(pkg)

        all_issues[pkg.pkg_name].update(validator.validate_package())

    if not all_issues:
        sys.exit(0)

    print(format_output(all_issues), file=sys.stderr)

    sys.exit(1)


if __name__ == "__main__":
    main()
