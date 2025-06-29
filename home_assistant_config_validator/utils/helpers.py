"""Helper functions for the Home Assistant Config Validator."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Literal

from . import const
from .exception import (
    FixableConfigurationError,
    InvalidConfigurationError,
)

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = getLogger(__name__)


def fmt_str(
    v: object,
    /,
    *fmt_opts: Literal["bold", "italic", "red", "green", "amber", "blue", "cyan"],
) -> str:
    s = str(v)
    codes = {
        "bold": "\033[1m",
        "italic": "\033[3m",
        "red": "\033[31m",
        "green": "\033[32m",
        "amber": "\033[33m",
        "blue": "\033[34m",
        "cyan": "\033[36m",
        "reset": "\033[0m",
    }

    for fmt_opt in fmt_opts:
        s = f"{codes[fmt_opt]}{s!s}"

    if s.endswith(codes["reset"]):
        return s

    return f"{s}{codes['reset']}"


def format_output(
    data: dict[str, dict[Path, list[InvalidConfigurationError]]],
) -> str:
    """Format output for better readability.

    Args:
        data (dict | list): Data to format
        _indent (int, optional): Current indentation level. Defaults to 0.

    Returns:
        str: Formatted output; sort of YAML, sort of not

    Raises:
        TypeError: If `data` is not a dict or list
    """
    fixable_indicator = f"[{fmt_str('*', 'cyan')}]"

    output_lines = []
    issue_count = {
        "fixed": 0,
        "fixable": 0,
        "total": 0,
    }
    name_pad = 0

    for pkg_name, issues in data.items():
        if not issues:
            continue

        package_lines = []

        for path, issue_list in issues.items():
            for exc in issue_list:
                if exc.fixed:
                    issue_count["fixed"] += 1
                    issue_count["total"] += 1
                    continue

                exc_typ = type(exc).__name__.removesuffix("Error")

                if isinstance(exc, FixableConfigurationError):
                    issue_count["fixable"] += 1
                    exc_typ = f"{fmt_str(exc_typ, 'amber', 'bold')} {fixable_indicator}"
                else:
                    exc_typ = fmt_str(exc_typ, "red", "bold")

                issue_line = " ".join(
                    (
                        fmt_str(path.relative_to(const.REPO_PATH), "bold")
                        + fmt_str(":", "cyan"),
                        exc_typ,
                        exc.fmt_msg,
                    ),
                )

                package_lines.append((pkg_name, issue_line))
                issue_count["total"] += 1

        if package_lines:
            name_pad = max(
                name_pad,
                len(pkg_name) + 1,
            )
            output_lines.extend(package_lines)

    summary_line = fmt_str(
        " ".join(
            (
                "Found",
                fmt_str(
                    str(issue_count["total"]),
                    (
                        "amber"
                        if (issue_count["total"] - issue_count["fixed"]) < 10  # noqa: PLR2004
                        else "red"
                    ),
                ),
                "issues",
            ),
        ),
        "bold",
    )

    if issue_count["fixed"]:
        summary_line += f", fixed {fmt_str(issue_count['fixed'], 'bold', 'green')} 🎉"

    if issue_count["fixable"]:
        summary_line += f"\n{fixable_indicator} {fmt_str(issue_count['fixable'], 'bold', 'green')} fixable with the `--fix` option"  # noqa: E501

    return "\n" + (
        "\n".join(
            f"{fmt_str(f'{pkg_name:<{name_pad}}', 'bold', 'italic', 'blue')} {issue_line}"
            for pkg_name, issue_line in output_lines
        )
        + f"\n\n{summary_line}\n"
    )


__all__ = ["format_output"]
