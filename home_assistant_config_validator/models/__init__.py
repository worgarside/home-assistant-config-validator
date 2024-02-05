from __future__ import annotations

from typing import Annotated

from jsonpath_ng import JSONPath, parse  # type: ignore[import-untyped]
from jsonpath_ng.exceptions import JsonPathParserError  # type: ignore[import-untyped]
from pydantic import AfterValidator

from home_assistant_config_validator.utils import UserPCHConfigurationError, const

from .package import Package
from .readme_entity import ReadmeEntity


def _validate_json_path(path: str, /) -> JSONPath:
    """Validate a JSONPath string."""
    try:
        parse(path)
    except JsonPathParserError:
        raise UserPCHConfigurationError(
            const.ConfigurationType.VALIDATION,
            "unknown",
            f"Invalid JSONPath: {path}",
        ) from None

    return path


JSONPathStr = Annotated[str, AfterValidator(_validate_json_path)]

__all__ = [
    "Package",
    "ReadmeEntity",
    "JSONPathStr",
]
