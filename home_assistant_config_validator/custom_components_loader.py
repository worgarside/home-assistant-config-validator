"""Loader for custom components."""
# mypy: disable-error-code="import"
from __future__ import annotations

import re
import sys
from importlib import import_module
from logging import getLogger
from pathlib import Path
from types import ModuleType

from git import Repo  # type: ignore[attr-defined]
from voluptuous import Schema
from wg_utilities.functions import force_mkdir
from wg_utilities.loggers import add_stream_handler

CC_REPO_CACHE_DIR = force_mkdir(Path(__file__).parent / "custom_components_cache")


EXPECTED_IMPORT_ERROR_PATTERN = re.compile(
    r"^No module named (?:'|\")([a-z_]+[a-z0-9_-]*)(?:'|\")$",
    flags=re.IGNORECASE,
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


def import_custom_components(
    cc_configs: dict[str, dict[str, str]]
) -> dict[str, dict[str, ModuleType | Schema]]:
    """Download and import custom components for schema imports.

    Args:
        cc_configs (dict[str, dict[str, str]]): Custom component configurations

    Returns:
        dict[str, dict[str, ModuleType | Schema]]: Imported custom component modules
    """
    component_modules: dict[str, dict[str, ModuleType | Schema]] = {}
    default_cc_dir = Path.cwd() / "custom_components"

    if not (gitignore := CC_REPO_CACHE_DIR / ".gitignore").is_file():
        LOGGER.debug(
            "Creating %r",
            gitignore.as_posix(),
        )
        gitignore.write_text("*\n!.gitignore\n")

    for component_name, cc_config in cc_configs.items():
        repo_name = cc_config["repoUrl"].split("/")[-1]

        if not (repo_path := CC_REPO_CACHE_DIR / repo_name).is_dir():
            LOGGER.debug(
                "Downloading %r to %r",
                cc_config["repoUrl"],
                repo_path.as_posix(),
            )
            Repo.clone_from(cc_config["repoUrl"], repo_path)

        cc_path = repo_path / "custom_components"

        if not (cc_path / component_name).exists():
            LOGGER.warning(
                "Expected component %s directory in %s, got %r. Adding full directory"
                " to `sys.path`",
                component_name,
                cc_path.as_posix(),
                list(cc_path.iterdir()),
            )
            sys.path.append(str(cc_path))
            continue

        if (default_cc_dir / component_name).exists():
            LOGGER.debug(
                "Custom component %r already exists in %r, skipping",
                component_name,
                default_cc_dir.as_posix(),
            )
            sys.path.append(str(default_cc_dir / component_name))
        else:
            LOGGER.debug(
                "Custom component %r does not exist in %r, adding local cache path to"
                " `sys.path`",
                component_name,
                default_cc_dir.as_posix(),
            )
            sys.path.append(str(cc_path))

        *package_path, schema_var_name = cc_config["importPath"].split(".")

        component_modules[component_name] = {
            "package": (package := import_module(".".join(package_path))),
            "schema_var": getattr(package, schema_var_name),
        }

    return component_modules


__all__ = ["import_custom_components"]
