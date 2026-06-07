PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: init run clean

init:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run:
	@if [ ! -x "$(PY)" ]; then \
		echo "[INFO] Virtualenv not found, running 'make init' first..."; \
		$(MAKE) init; \
	fi
	$(PY) app.py

clean:
	rm -rf $(VENV) __pycache__
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +

