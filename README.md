# SissyDex

Sistema de gestión documental (DMS) chico, hecho con Flask + JS vanilla. Los
usuarios marcan una combinación de checkboxes agrupados por categoría y
suben/buscan archivos etiquetados con esa combinación exacta.

## Arquitectura

La app Flask y las rutas viven en `backend/services/document_logic.py`. La
clase de negocio `LogicaNegocioArchivos` que vive ahí ya no toca disco ni SQL
directamente: orquesta dos módulos hermanos, cada uno protegiendo una
interfaz propia para poder cambiar de implementación sin tocar el resto:

- `backend/services/storage.py` — **patrón Strategy** para el contenido
  físico de un archivo. `EstrategiaAlmacenamiento` (guardar/renombrar/
  eliminar/existe) es el único contrato que conoce la lógica de negocio.
  `AlmacenamientoLocal` es la implementación real en uso hoy (mismo
  comportamiento que antes de extraerla). `AlmacenamientoS3` está lista para
  conectar el día que haga falta S3 -no cuesta nada mientras tanto: no
  importa `boto3` a nivel de módulo-.
- `backend/services/repositorio.py` — **patrón Repository** para el acceso
  SQL. `RepositorioArchivos` (tabla `archivos`) y `RepositorioOrdenOpciones`
  (tabla `orden_opciones`), cada método mapeado 1:1 con el bloque de SQL que
  antes vivía inline en `LogicaNegocioArchivos`.

`backend/app.py` (`from services.document_logic import app, DEBUG_MODE`) SÍ
es el entry point real que corre la imagen de Docker -no es código muerto
pese a lo mínimo que parece-. Por eso `document_logic.py` se importa de dos
formas distintas (directo por `make run`, o como submódulo `services.
document_logic` por `app.py`), y fija su propio directorio en `sys.path`
antes de sus imports hermanos para que ambas formas resuelvan igual.

`document_logic.py` calcula `PROJECT_ROOT` subiendo tres niveles desde su
propia ubicación, y a partir de ahí deriva `frontend/templates`,
`frontend/style` (montado en `/static`), `frontend/client_logic` y
`storage_database/documents_pool/` (BD SQLite + archivos subidos). Por eso
`frontend/` y `storage_database/` tienen que existir como directorios
hermanos de `backend/` para que la app funcione -algo a tener en cuenta si
armás una imagen de Docker con contexto de build distinto al repo entero-.

## Árbol de archivos (real)

```
sissydex/
├── .github/
│   ├── workflows/
│   │   ├── python-package.yml     # Instala vía Makefile, lintea con flake8, corre pytest
│   │   ├── docker-publish.yml     # Build + push de la imagen (firmada con cosign)
│   │   └── codeql.yml             # Análisis de seguridad estático
│   └── dependabot.yml             # Actualiza deps de pip, docker y github-actions
│
├── backend/
│   ├── app.py                     # Entry point real -lo corre el CMD del Dockerfile-
│   ├── config.py                  # Vacío por ahora
│   ├── Dockerfile                 # Build desde la raíz del repo (ver docker-compose.yml)
│   ├── requirements.txt
│   └── services/
│       ├── document_logic.py      # App Flask, rutas, y la clase de negocio LogicaNegocioArchivos
│       ├── storage.py             # Strategy: EstrategiaAlmacenamiento (Local/S3)
│       └── repositorio.py         # Repository: RepositorioArchivos / RepositorioOrdenOpciones
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
├── tests/
│   ├── conftest.py                # Pone backend/services/ en sys.path
│   ├── test_smoke.py              # La app bootea, rutas clave no tiran 500
│   └── test_hash_scheme.py        # Unit tests del esquema de hash PK^opciones
│
├── docker-compose.yml
├── .dockerignore
├── Makefile
└── venv/                          # Entorno virtual local (no versionado)
```

## Comandos (Makefile)

Todo corre a través de `venv/` local, salvo los targets de Docker:

```bash
make              # = make all (default goal): install + apply-seed, idempotente
make all          # lo mismo, explícito
make install      # crea venv/ e instala backend/requirements.txt
make setup        # install + apply-seed
make run          # corre la app Flask (puerto 5000, debug=True)
make watch        # corre storage_database/watcher.py en primer plano
make update       # reconcilia storage_database/documents_pool/ contra la tabla `archivos`
                   # (borra archivos en disco sin fila en BD, y filas sin archivo en disco)
make seed         # regenera orden_opciones_seed.sql a partir de orden_opciones.csv
make apply-seed   # regenera el seed desde el CSV (depende de `seed`) y lo carga en la BD SQLite
make dockerize    # docker compose up -d && docker compose ps
make clean        # borra venv/, __pycache__ y baja los contenedores (docker compose down)
```

`apply-seed` depende de `seed`: siempre regenera `orden_opciones_seed.sql` a
partir del CSV actual antes de cargarlo, así que nunca se aplica una versión
vieja del seed sin importar qué target lo dispare (`all`, `setup`, o
invocarlo directo).

**Nunca ejecutes `make .PHONY` directamente** — es un nombre de target válido
para make, así que invocarlo por nombre lo convierte en el objetivo pedido y
construye TODOS sus prerequisitos en orden de declaración (`venv install run
watch seed apply-seed setup update dockerize clean`), incluyendo `run`, que
arranca el server de Flask en primer plano y nunca retorna. Es inherente a
cómo funciona `.PHONY` en make; la mitigación es que `make`/`make all` ya es
el default correcto, así que nunca hace falta escribir `.PHONY`.

Hay una suite de tests real en `tests/` (`venv/bin/pytest tests/`, ver más
abajo) y `flake8` corre en CI. No hay formatter configurado.

## Tests

```bash
venv/bin/pytest tests/ -v
```

- `test_smoke.py`: la app bootea vía `test_client()` de Flask y las rutas
  clave (`/`, `/static/app.js`, `/api/orden`, `/api/procesar`) no tiran 500.
  Verifica forma de la respuesta, no reglas de negocio -`validar_combinacion`
  es un stub, así que afirmar un valor específico de `"valido"` solo
  fijaría el comportamiento placeholder de hoy-.
- `test_hash_scheme.py`: unit tests del esquema de hash `PK XOR
  calcular_hash_opciones(...)` y del renombrado del archivo físico -la parte
  mecánica del proyecto que no depende de qué reglas de negocio se terminen
  definiendo-.

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
  que existan en esta tabla): `app.js` crea cada
  `<div class="categoria-col" id="col-{categoria}">` al vuelo a partir de
  `GET /api/orden`, así que reseedear con un CSV nuevo (categorías
  agregadas/renombradas/eliminadas) no requiere tocar el HTML.

El hash de cada archivo se calcula con `PK XOR xxhash32(opciones)` y se
recalcula -renombrando también el archivo físico vía
`EstrategiaAlmacenamiento.renombrar`- cada vez que se sube un archivo nuevo o
se le cambia su combinación de opciones desde la UI. Ver `storage.py` y
`repositorio.py` en la sección de Arquitectura para dónde vive cada parte de
ese flujo.
