# vps-monitor Makefile
# 统一入口: make test / lint / install / clean / format

.PHONY: help test lint format install clean run status check

PYTHON ?= python3
PIP ?= pip3

help:  ## Show this help
	@grep -E "^[a-zA-Z_-]+:.*?## .*$$" $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

test:  ## Run all tests
	$(PYTHON) tests/test_monitor_smoke.py
	$(PYTHON) tests/test_state_diff.py
	$(PYTHON) tests/test_compare_logic.py

lint:  ## Run ruff linter
	$(PYTHON) -m ruff check monitor.py vpsmonctl scripts/ tests/ || true

format:  ## Auto-format with ruff
	$(PYTHON) -m ruff format monitor.py vpsmonctl scripts/ tests/

install:  ## Install dependencies
	$(PIP) install -r requirements.txt
	$(PIP) install -e .  # 装了之后 vpsmonctl 全局可调

install-dev:  ## Install with dev dependencies
	$(PIP) install -e ".[dev]"

clean:  ## Clean pyc + cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/ .ruff_cache/

run:  ## Run monitor once (foreground, requires .env)
	cd /opt/vps-monitor && sudo -E $(PYTHON) monitor.py --once

status:  ## Check service status
	vpsmonctl status

check:  ## Check current matches
	vpsmonctl check

deploy:  ## Deploy to /opt/vps-monitor (interactive)
	sudo bash scripts/install.sh
