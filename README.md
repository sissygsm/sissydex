# SissyDex

Sistema de gestión documental (DMS) chico, hecho con Flask + JS vanilla. Los
usuarios marcan una combinación de checkboxes agrupados por categoría y
tagean/buscan archivos etiquetados con esa combinación exacta. Hay una segunda
búsqueda independiente (botón "Buscar", 3ra Sección) sobre la misma selección
de checkboxes pero con matching por subconjunto en vez de exacto: devuelve
cualquier archivo que tenga TODAS las opciones seleccionadas entre sus
opciones de identidad, aunque el archivo tenga además otras opciones no
seleccionadas.

Los archivos nunca se copian: tagear un archivo lo referencia por su ruta
absoluta original y le antepone el hash al nombre ahí mismo, para que la app
funcione incluso con muy poco disco libre.

## Arquitectura

La app Flask y las rutas viven en `backend/services/document_logic.py`. La
clase de negocio `LogicaNegocioArchivos` que vive ahí ya no toca disco ni SQL
directamente: orquesta dos módulos hermanos, cada uno protegiendo una
interfaz propia para poder cambiar de implementación sin tocar el resto:

- `backend/services/storage.py` — **patrón Strategy** para el contenido
  físico de un archivo. `EstrategiaAlmacenamiento` (guardar/renombrar/
  eliminar/existe) es el único contrato que conoce la lógica de negocio.
  `AlmacenamientoReferenciado` es la implementación real en uso hoy: nunca
  copia bytes, todo identificador que maneja es una ruta absoluta a la
  ubicación original del archivo, y `renombrar` renombra in place (mismo
  directorio, nuevo nombre base). `AlmacenamientoS3` está lista para
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
`storage_database/documents_pool/` (hoy solo aloja la BD SQLite; los archivos
tageados quedan donde ya estaban). Por eso `frontend/` y `storage_database/`
tienen que existir como directorios hermanos de `backend/` para que la app
funcione -algo a tener en cuenta si armás una imagen de Docker con contexto
de build distinto al repo entero-.

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
│       ├── repositorio.py         # Repository: RepositorioArchivos / RepositorioOrdenOpciones
│       └── tokens.py              # AlmacenTokens: indirección de tokens opacos (ver Seguridad)
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
│   ├── documents_pool/            # BD SQLite (no versionado; los archivos tageados NO viven acá)
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
│   ├── test_hash_scheme.py        # Unit tests del esquema de hash PK^opciones
│   ├── test_path_containment.py   # Contención de RAIZ_PERMITIDA (storage.py + explorar_directorio)
│   ├── test_tokens.py             # Unit tests de AlmacenTokens (mint/resolver/descartar/FIFO)
│   ├── test_explorador_tokens.py  # E2E vía test_client() del flujo /api/explorar + /api/subir por token
│   └── test_busqueda_subconjunto.py  # buscar_archivos_por_subconjunto / POST /api/buscar (botón "Buscar")
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
make update       # borra de la tabla `archivos` las filas cuya ruta absoluta ya no exista en disco
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
  calcular_hash_opciones(...)`, del renombrado in place del archivo físico al
  tagearlo, y de que "Eliminar" le quite el prefijo de hash sin borrar el
  archivo de disco -la parte mecánica del proyecto que no depende de qué
  reglas de negocio se terminen definiendo-.
- `test_path_containment.py`: que `AlmacenamientoReferenciado` y
  `explorar_directorio` rechacen/caigan a la raíz ante rutas fuera de
  `RAIZ_PERMITIDA`, traversal con "..", y el caso límite de un directorio
  hermano con nombre-prefijo similar (`/home/user` vs `/home/user2`).
- `test_tokens.py` / `test_explorador_tokens.py`: la indirección de tokens
  opacos -mint/resolve/descarte, expulsión FIFO al superar la capacidad, y el
  flujo completo de `GET /api/explorar` + `POST /api/subir` por token vía
  `test_client()`, incluyendo que un token reusado tras un tageo exitoso se
  rechace en vez de duplicar filas- (ver "Seguridad" más abajo).
- `test_busqueda_subconjunto.py`: la búsqueda por subconjunto del botón
  "Buscar" (3ra Sección) -que un archivo con opciones extra igual aparezca,
  que falte una sola opción seleccionada lo excluya (no es matching OR), que
  selección vacía no devuelva nada, que no haya falsos positivos por
  coincidencia parcial de nombres de opción (`"a"` vs `"aa"`), y el mismo
  autosanado de huérfanos que `listar_archivos_por_combinacion`- tanto a
  nivel de `LogicaNegocioArchivos` como de `POST /api/buscar` vía
  `test_client()`.

## Docker

La app es un único proceso Flask que sirve HTML, CSS y JS desde el mismo
origen (rutas `/static/...`), así que se dockeriza como **un solo
contenedor** -no hace falta nginx ni un contenedor de frontend aparte-.

```bash
make dockerize          # o: docker compose up -d
```

Esto expone el puerto `5000` y monta `storage_database/documents_pool/` como
volumen, para que la base de datos persista entre reinicios del contenedor.
`backend/Dockerfile` se construye con contexto en la raíz del repo
(`docker-compose.yml` fija `context: .`) para poder copiar `backend/`,
`frontend/` y `storage_database/` juntos, tal como los espera `PROJECT_ROOT`
en tiempo de ejecución.

**Ojo con Docker**: como los archivos tageados nunca se copian, `GET
/api/explorar` navega el filesystem *del contenedor*, no el del host -así
que, dentro de Docker, solo se puede tagear algo que ya esté accesible
adentro del contenedor (p. ej. montando el directorio real del host como
volumen adicional). Para el caso de uso original (disco del propio usuario
con poco espacio libre) correr la app directo con `make run`, sin Docker, es
lo que tiene sentido.

## Modelo de datos

- `archivos`: archivos tageados — `id` (PK), `nombre_original` (pese al
  nombre de la columna, guarda la **ruta absoluta completa** del archivo en
  su ubicación original, con el hash antepuesto al nombre base:
  `.../carpeta/{hash}{nombre_original_del_usuario}`), `combinacion_opciones`
  (ids de opción ordenados y unidos por coma, ej. `"a,c,o"`),
  `hash_calculado_hex`.
- `orden_opciones`: orden persistente del drag-and-drop — `(categoria,
  opcion_id)` como PK, `posicion_y`. Las categorías son dinámicas (las filas
  que existan en esta tabla): `app.js` crea cada
  `<div class="categoria-col" id="col-{categoria}">` al vuelo a partir de
  `GET /api/orden`, así que reseedear con un CSV nuevo (categorías
  agregadas/renombradas/eliminadas) no requiere tocar el HTML.

El hash de cada archivo se calcula con `PK XOR xxhash32(opciones)` y se
recalcula -renombrando también el archivo físico **in place** (mismo
directorio, nunca se mueve) vía `EstrategiaAlmacenamiento.renombrar`- cada
vez que se tagea un archivo nuevo o se le cambia su combinación de opciones
desde la UI. Al eliminar ("Eliminar" en la UI), el archivo se renombra de
vuelta a su nombre sin hash pero **nunca se borra de disco**: solo se borra
su fila en `archivos`. Ver `storage.py` y `repositorio.py` en la sección de
Arquitectura para dónde vive cada parte de ese flujo.

La 1ra Sección (`POST /api/procesar`, se refresca sola en cada cambio de
checkbox / cada 2s) filtra por combinación EXACTA: `combinacion_opciones` debe
ser igual a la selección actual. La 3ra Sección (botón "Buscar",
`LogicaNegocioArchivos.buscar_archivos_por_subconjunto` / `POST /api/buscar`)
es una búsqueda distinta e independiente sobre la misma selección de
checkboxes, pero por subconjunto: incluye cualquier archivo cuyas opciones de
identidad contengan TODAS las opciones seleccionadas, aunque el archivo tenga
además otras opciones no seleccionadas. No se refresca sola -solo corre al
hacer clic en "Buscar"- y una selección vacía devuelve lista vacía tanto en el
cliente como en el servidor (el conjunto vacío es subconjunto de cualquier
archivo, pero "mostrar todo el pool sin tildar nada" no tiene sentido de
negocio acá). Comparte con la 1ra Sección el mismo autosanado de filas
huérfanas (archivo borrado del disco fuera de la app).

Como el navegador no puede exponerle a JS la ruta absoluta de un archivo
local, "AGREGAR ARCHIVO" no usa un `<input type="file">`: abre un explorador
de directorios respaldado por `GET /api/explorar?token=<token>` (token vacío
= raíz), que lista carpetas/archivos del propio disco donde corre el
servidor. Cada entrada -y el enlace "subir un nivel"- llevan su propio token
opaco, nunca una ruta cruda; el frontend nunca vuelve a mandarle una ruta de
filesystem al servidor. Elegir un archivo ahí dispara `POST /api/subir` con
`{"token": ..., "opciones": [...]}` (JSON, no multipart) en vez de subir sus
bytes; el servidor resuelve el token a la ruta real antes de tocar disco (ver
"Seguridad: contención de rutas" más abajo).

## Seguridad: contención de rutas

La app no tiene autenticación. `GET /api/explorar` y `POST /api/subir`
aceptan **solo un token opaco** minteado por el propio servidor -nunca una
ruta de filesystem cruda-, que es lo que elimina de raíz la superficie de
`py/path-injection` que CodeQL marcaba (`os.scandir`, `os.rename` recibiendo
dato del request). Restringir a una carpeta base fija habría roto la idea
misma de la feature (elegir cualquier archivo propio), así que la mitigación
real es el patrón "indirect reference map" de OWASP:

- `LogicaNegocioArchivos` guarda dos `AlmacenTokens` (`backend/services/
  tokens.py`) -namespaces separados para carpetas y archivos, así un token de
  carpeta nunca sirve como token de archivo-. Cada uno es un diccionario en
  memoria con clave `secrets.token_urlsafe`, con tope de tamaño fijo
  (se descarta la entrada más vieja al superarlo, sin expiración por
  tiempo -sería sobreingeniería para una herramienta de un solo usuario-).
- `explorar_directorio` mintea un token por entrada listada y para "subir un
  nivel", construido a partir de la ruta que el propio servidor ya validó
  más el nombre que su propio `os.scandir` devolvió -nunca a partir de la
  `ruta` cruda del request-.
- `GET /api/explorar?token=<token>` y `POST /api/subir` resuelven el token
  con un lookup de diccionario y usan ese *resultado* -nunca el token en
  sí- para el resto del flujo. Por eso corta la cadena de taint en vez de
  reubicarla: el valor que termina en `os.rename` es el resultado de un
  `dict.get()`, y ese diccionario lo pobló un request *distinto* -la llamada
  anterior a `explorar_directorio`-, sin ninguna dependencia de datos con el
  token de este request. Dentro del grafo de dataflow de un único request no
  hay conexión posible entre "llegó este token" y "se tocó esta ruta".
- `POST /api/subir` invalida el token de archivo apenas el tageo tiene éxito
  -no es solo prolijidad: `renombrar` no falla si el origen ya no existe y
  aun así devuelve la ruta que *habría* renombrado, así que reusar un token
  ya usado insertaría una segunda fila de BD apuntando a un archivo que
  nunca se creó-. Los tokens de carpeta nunca se invalidan (navegar es de
  solo lectura).

Toda la contención de `RAIZ_PERMITIDA` que ya existía (ver debajo) sigue
funcionando exactamente igual: la capa de tokens se agrega delante, no la
reemplaza.

**Por qué hizo falta esta capa** (`RAIZ_PERMITIDA`, `backend/services/
document_logic.py`, home del usuario por defecto, configurable con
`SISSYDEX_ROOT_PERMITIDO`): varias rondas de intentos previos -confinar a
esa raíz con `os.path.realpath` + `startswith(raíz + separador)`, escribir
el chequeo inline en cada punto que toca el filesystem en vez de en un
helper compartido (CodeQL no reconoce un sanitizer aplicado dentro de una
función llamada como barrera para el valor que recibe quien la llama),
`AlmacenamientoReferenciado` validando tanto el origen como el **destino**
construido (`directorio + nombre_nuevo`), y ajustar la forma del guard a
`raise`/`return` en vez de reasignar la variable a un valor seguro y seguir
de largo (CodeQL reconoce la primera forma como barrera, no la segunda,
aunque el resultado final sea idéntico)- todas mejoraron el código real pero
CodeQL siguió marcando los mismos sinks. La conclusión fue dejar de intentar
que una ruta llegue "reconocida como sanitizada" y en cambio asegurarse de
que una ruta del request nunca llegue a tocar el filesystem -de ahí la capa
de tokens de arriba-. Todo ese trabajo de contención sigue activo como
defensa en profundidad (ver CLAUDE.md "Security: path containment" para el
detalle completo).

Por la misma razón (elegir cualquier archivo = superficie de ataque real sin
login), `make run` liga el server a `127.0.0.1` únicamente por defecto
-nadie más en tu red local puede alcanzarlo-, configurable con la variable de
entorno `FLASK_HOST` si en algún momento hace falta acceso desde otro
dispositivo. Esto no aplica al entrypoint de Docker (`backend/app.py`), que
necesita `0.0.0.0` para que el mapeo de puertos del contenedor funcione.
