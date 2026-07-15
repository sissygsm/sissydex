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
RECONCILE_SCRIPT := storage_database/reconciliar_pool.py

.PHONY: all venv install run watch seed apply-seed setup update dockerize clean

# NUNCA invocar "make .PHONY" directamente: al ser un target valido, make lo
# toma como el objetivo pedido y construye TODOS sus prerequisitos en orden
# (venv, install, run, watch, seed, apply-seed, setup, update, dockerize,
# clean) - incluyendo "run", que arranca el servidor Flask en foreground y
# nunca retorna. Este es el motivo por el que "all" existe como default goal
# explicito: usa "make" a secas (o "make all"), nunca "make .PHONY".
.DEFAULT_GOAL := all

# Idempotente: converge siempre al mismo estado (venv creado, dependencias
# instaladas, BD sincronizada con el CSV de orden_opciones actual) sin
# importar cuantas veces se ejecute ni el estado previo. No incluye "run"
# (bloquea la terminal) ni "dockerize"/"clean" (no son parte del estado base).
all: install apply-seed

venv:
	python3 -m venv $(VENV_DIR)

install: venv
	$(PIP) install -r $(REQUIREMENTS_FILE)

run:
	-kill -9 $$(lsof -t -i:5000) 2>/dev/null
	FLASK_DEBUG=1 $(PYTHON) $(APP_ENTRYPOINT)

watch:
	$(PYTHON) $(WATCHER_SCRIPT)

seed:
	$(PYTHON) $(SEED_GENERATOR)

# Depende de "seed" a proposito: aplicar un seed.sql desactualizado respecto
# al CSV rompe la coherencia csv -> sql -> BD. Con esta dependencia,
# "apply-seed" SIEMPRE regenera el .sql desde el CSV actual antes de
# cargarlo, sin importar si se invoca via "all", "setup" o directamente.
apply-seed: seed
	$(PYTHON) -c "import sqlite3; sqlite3.connect('$(DATABASE_FILE)').executescript(open('$(SEED_SQL_FILE)').read())"

setup: install apply-seed

update:
	$(PYTHON) $(RECONCILE_SCRIPT)

dockerize:
	docker compose up -d
	docker compose ps

clean:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	docker compose down
