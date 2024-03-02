"""Benchmark the pre-commit hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_codspeed.plugin import BenchmarkFixture  # type: ignore[import-untyped]


@pytest.mark.usefixtures("clean_repo")
def test_readme_generator(benchmark: BenchmarkFixture) -> None:
    """Benchmark the `readme-generator` hook."""
    from home_assistant_config_validator.readme_generator import main

    benchmark(main)


@pytest.mark.usefixtures("clean_repo")
def test_validate_entities(benchmark: BenchmarkFixture) -> None:
    """Benchmark the `validate-entities` hook."""
    from home_assistant_config_validator.validate_entities import main

    benchmark(main)


@pytest.mark.usefixtures("clean_repo")
def test_validate_lovelace(benchmark: BenchmarkFixture) -> None:
    """Benchmark the `validate-lovelace` hook."""
    from home_assistant_config_validator.validate_lovelace import main

    benchmark(main)
