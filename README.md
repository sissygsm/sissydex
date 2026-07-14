# SissyDex

Sistema de gestión documental (DMS) chico, hecho con Flask + JS vanilla. Los
usuarios marcan una combinación de checkboxes agrupados por categoría y
suben/buscan archivos etiquetados con esa combinación exacta.

## Arquitectura

No hay un `app.py` con la lógica real pese a lo que sugiere el árbol de
archivos: `backend/app.py` solo hace
`from services.document_logic import app; app.run(...)`. Todo el backend
-creación de la app Flask, rutas y la clase de negocio `LogicaNegocioArchivos`-
vive en `backend/services/document_logic.py`.

Ese archivo calcula `PROJECT_ROOT` subiendo tres niveles desde su propia
ubicación, y a partir de ahí deriva `frontend/templates`, `frontend/style`
(montado en `/static`), `frontend/client_logic` y
`storage_database/documents_pool/` (BD SQLite + archivos subidos). Por eso
`frontend/` y `storage_database/` tienen que existir como directorios
hermanos de `backend/` para que la app funcione -algo a tener en cuenta si
armás una imagen de Docker con contexto de build distinto al repo entero-.

## Árbol de archivos (real)

```
sissydex/
├── backend/
│   ├── app.py                     # Entry point: solo llama a app.run()
│   ├── config.py                  # Vacío por ahora
│   ├── Dockerfile                 # Build desde la raíz del repo (ver docker-compose.yml)
│   ├── requirements.txt
│   └── services/
│       └── document_logic.py      # App Flask, rutas y lógica de negocio
│
├── frontend/
│   ├── client_logic/
│   │   └── app.js                 # Único script, sin build step ni framework
│   ├── style/
│   │   └── style.css
│   └── templates/
│       └── index.html
│
├── storage_database/
│   ├── documents_pool/            # BD SQLite + archivos subidos (no versionado)
│   ├── seeds/
│   │   ├── orden_opciones.csv           # Fuente de verdad del orden de categorías/opciones
│   │   ├── generate_orden_opciones_sql.py
│   │   └── orden_opciones_seed.sql      # Generado a partir del CSV (make seed)
│   ├── watcher.py                 # Proceso opcional: borra filas huérfanas cada 2s (make watch)
│   └── reconciliar_pool.py        # Reconciliación en un solo paso disco <-> BD (make update)
│
├── docker-compose.yml
├── .dockerignore
├── Makefile
└── venv/                          # Entorno virtual local (no versionado)
```

## Comandos (Makefile)

Todo corre a través de `venv/` local, salvo los targets de Docker:

```bash
make install      # crea venv/ e instala backend/requirements.txt
make setup        # install + apply-seed
make run          # corre la app Flask (puerto 5000, debug=True)
make watch        # corre storage_database/watcher.py en primer plano
make update       # reconcilia storage_database/documents_pool/ contra la tabla `archivos`
                   # (borra archivos en disco sin fila en BD, y filas sin archivo en disco)
make seed         # regenera orden_opciones_seed.sql a partir de orden_opciones.csv
make apply-seed   # carga orden_opciones_seed.sql en la BD SQLite
make dockerize    # docker compose up -d && docker compose ps
make clean        # borra venv/, __pycache__ y baja los contenedores (docker compose down)
```

No hay test suite, linter ni formatter configurados en este repo.

## Docker

La app es un único proceso Flask que sirve HTML, CSS y JS desde el mismo
origen (rutas `/static/...`), así que se dockeriza como **un solo
contenedor** -no hace falta nginx ni un contenedor de frontend aparte-.

```bash
make dockerize          # o: docker compose up -d
```

Esto expone el puerto `5000` y monta `storage_database/documents_pool/` como
volumen, para que la base de datos y los archivos subidos persistan entre
reinicios del contenedor. `backend/Dockerfile` se construye con contexto en
la raíz del repo (`docker-compose.yml` fija `context: .`) para poder copiar
`backend/`, `frontend/` y `storage_database/` juntos, tal como los espera
`PROJECT_ROOT` en tiempo de ejecución.

## Modelo de datos

- `archivos`: archivos subidos — `id` (PK), `nombre_original` (nombre físico
  en disco, con el hash antepuesto: `{hash}{nombre_original_del_usuario}`),
  `combinacion_opciones` (ids de opción ordenados y unidos por coma, ej.
  `"a,c,o"`), `hash_calculado_hex`.
- `orden_opciones`: orden persistente del drag-and-drop — `(categoria,
  opcion_id)` como PK, `posicion_y`. Las categorías son dinámicas (las filas
  que existan en esta tabla); el HTML necesita un
  `<div id="col-{categoria}">` por cada una.

El hash de cada archivo se calcula con `PK XOR xxhash32(opciones)` y se
recalcula -renombrando también el archivo físico- cada vez que se sube un
archivo nuevo o se le cambia su combinación de opciones desde la UI.
