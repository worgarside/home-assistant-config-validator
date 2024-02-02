"""Validate Home Assistant configurations."""

from __future__ import annotations

import sys

from home_assistant_config_validator.config import ValidationConfig
from home_assistant_config_validator.const import ENTITIES_DIR, format_output


def main() -> None:
    """Validate all entities."""
    all_issues: dict[str, dict[str, list[Exception]]] = {}

    for domain_dir in sorted(ENTITIES_DIR.iterdir()):
        if not domain_dir.is_dir():
            continue

        v_config = ValidationConfig.get_for_package(domain_dir.name)

        v_config.validate_domain()

        if v_config.package_issues:
            all_issues[domain_dir.name] = v_config.package_issues

    if not all_issues:
        sys.exit(0)

    sys.exit(format_output(all_issues))


if __name__ == "__main__":
    main()
