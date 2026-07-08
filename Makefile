VENV_DIR := venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip
REQUIREMENTS_FILE := backend/requirements.txt
APP_ENTRYPOINT := backend/services/document_logic.py
DATABASE_FILE := storage_database/documents_pool/catalogo_archivos.db
SEED_DIR := storage_database/seeds
SEED_GENERATOR := $(SEED_DIR)/generate_orden_opciones_sql.py
SEED_SQL_FILE := $(SEED_DIR)/orden_opciones_seed.sql

.PHONY: venv install run seed apply-seed setup clean

venv:
	python3 -m venv $(VENV_DIR)

install: venv
	$(PIP) install -r $(REQUIREMENTS_FILE)

run:
	$(PYTHON) $(APP_ENTRYPOINT)

seed:
	$(PYTHON) $(SEED_GENERATOR)

apply-seed:
	sqlite3 $(DATABASE_FILE) < $(SEED_SQL_FILE)

setup: install apply-seed

clean:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
