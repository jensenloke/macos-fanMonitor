VENV := ./.venv
PY   := $(VENV)/bin/python

.PHONY: help run once test docs docs-build clean

help:
	@echo "make run         launch the TUI"
	@echo "make once        print one snapshot frame and exit"
	@echo "make test        headless TUI smoke test"
	@echo "make docs        serve docs at http://127.0.0.1:8000"
	@echo "make docs-build  strict build (what CI runs)"
	@echo "make clean       remove build artifacts"

run:
	@./fm

once:
	@./fm --once

test:
	@$(PY) smoke_test.py

docs:
	@$(VENV)/bin/mkdocs serve

docs-build:
	@$(VENV)/bin/mkdocs build --strict

clean:
	rm -rf site
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
