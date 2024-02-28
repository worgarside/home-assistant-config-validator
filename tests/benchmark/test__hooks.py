"""Benchmark the pre-commit hooks."""

from __future__ import annotations

import pytest

from home_assistant_config_validator.readme_generator import main as readme_generator
from home_assistant_config_validator.validate_entities import main as validate_entities
from home_assistant_config_validator.validate_lovelace import main as validate_lovelace


@pytest.mark.usefixtures("clean_repo")
@pytest.mark.benchmark()
def test_readme_generator() -> None:
    """Benchmark the `readme-generator` hook."""
    readme_generator()


@pytest.mark.usefixtures("clean_repo")
@pytest.mark.benchmark()
def test_validate_entities() -> None:
    """Benchmark the `validate-entities` hook."""
    validate_entities()


@pytest.mark.usefixtures("clean_repo")
@pytest.mark.benchmark()
def test_validate_lovelace() -> None:
    """Benchmark the `validate-lovelace` hook."""
    validate_lovelace()
