VENV_DIR := venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip
REQUIREMENTS_FILE := backend/requirements.txt
APP_ENTRYPOINT := backend/services/document_logic.py
DATABASE_FILE := storage_database/documents_pool/catalogo_archivos.db
SEED_DIR := storage_database/seeds
SEED_GENERATOR := $(SEED_DIR)/generate_orden_opciones_sql.py
SEED_SQL_FILE := $(SEED_DIR)/orden_opciones_seed.sql
WATCHER_SCRIPT := storage_database/watcher.py

.PHONY: venv install run watch seed apply-seed setup clean

venv:
	python3 -m venv $(VENV_DIR)

install: venv
	$(PIP) install -r $(REQUIREMENTS_FILE)

run:
	-kill -9 $$(lsof -t -i:5000) 2>/dev/null
	$(PYTHON) $(APP_ENTRYPOINT)

watch:
	$(PYTHON) $(WATCHER_SCRIPT)

seed:
	$(PYTHON) $(SEED_GENERATOR)

apply-seed:
	$(PYTHON) -c "import sqlite3; sqlite3.connect('$(DATABASE_FILE)').executescript(open('$(SEED_SQL_FILE)').read())"

setup: install apply-seed

clean:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
