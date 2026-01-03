.PHONY: help lint format ci

PYTHON ?= python3

help:
	@echo "Available targets:"
	@echo "  lint    - run linters (black)"
	@echo "  format  - autoformat code (ruff format)"
	@echo "  ci      - lint + test"

lint:
	$(PYTHON) -m black --check src

format:
	$(PYTHON) -m ruff check src

ci: lint test
