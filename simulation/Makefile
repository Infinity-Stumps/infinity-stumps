# Infinity Stumps — developer tasks.
# Run `make help` for the list.

.DEFAULT_GOAL := help
PYTHON ?= python3

.PHONY: help install test cov lint format typecheck check sims clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Create venv deps and install the package (editable) with dev extras
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

test:  ## Run the test suite
	pytest

cov:  ## Run tests with a coverage report
	pytest --cov=infinity_stumps --cov-report=term-missing

lint:  ## Lint with ruff
	ruff check .

format:  ## Auto-format with ruff
	ruff format .
	ruff check --fix .

typecheck:  ## Static type check with mypy
	mypy

check: lint typecheck test  ## Full pre-push gate: lint + typecheck + test

sims:  ## Regenerate all simulation output PNGs
	$(PYTHON) sims/run_all.py

clean:  ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
