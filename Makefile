.PHONY: help install test syntax dry-run-czl dry-run-dujiaojing check clean

PYTHON ?= python3
CONFIG ?= config.example.json

help:
	@printf '%s\n' 'vps-monitor commands:'
	@printf '%s\n' '  make install          Install package in editable mode'
	@printf '%s\n' '  make syntax           Compile Python files'
	@printf '%s\n' '  make test             Run pytest'
	@printf '%s\n' '  make check            Run syntax + tests + secret-shape scan'
	@printf '%s\n' '  make dry-run-czl      Preview czl.net output'
	@printf '%s\n' '  make dry-run-dujiaojing Preview dujiaojing output'
	@printf '%s\n' '  make clean            Remove local caches'

install:
	$(PYTHON) -m pip install -e . pytest

syntax:
	$(PYTHON) -m py_compile $$(find vpsmon tests -name '*.py' | sort)

test:
	$(PYTHON) -m pytest -q

check: syntax test
	@! git ls-files | grep -E '(^|/)(\.env$$|config\.json$$|config\.production\.json$$|.*\.sqlite3$$|.*\.log$$)'
	@! git grep -nE 'ghp_|github_pat_|[0-9]{6,}:[A-Za-z0-9_-]{20,}' -- . ':!Makefile' ':!docs/RELEASE_CHECKLIST.md'

dry-run-czl:
	$(PYTHON) -m vpsmon.cli --config $(CONFIG) --source czl --notify-first-run --dry-run

dry-run-dujiaojing:
	$(PYTHON) -m vpsmon.cli --config $(CONFIG) --source dujiaojing --notify-first-run --dry-run

clean:
	rm -rf .pytest_cache .coverage htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
