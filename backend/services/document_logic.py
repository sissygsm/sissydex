import os
import sys
import sqlite3
import xxhash
from flask import Flask, jsonify, request, render_template, send_from_directory
from werkzeug.utils import secure_filename

# storage.py y repositorio.py son módulos hermanos sin paquete formal (sin
# __init__.py). Este archivo se invoca de dos formas distintas -directo
# (`make run` -> sys.path[0] ya es este directorio) y como `services.
# document_logic` importado desde backend/app.py (usado por el CMD del
# Dockerfile -> sys.path[0] es backend/, no backend/services/)-, así que se
# fija este directorio en sys.path explícitamente para que los imports de
# abajo resuelvan igual en ambos casos.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import EstrategiaAlmacenamiento, AlmacenamientoReferenciado  # noqa: E402
from repositorio import RepositorioArchivos, RepositorioOrdenOpciones  # noqa: E402
from tokens import AlmacenTokens  # noqa: E402

# El modo debug del servidor de desarrollo de Werkzeug expone un debugger
# interactivo que permite ejecutar código arbitrario si queda accesible
# públicamente, así que solo se habilita explícitamente vía variable de
# entorno (ver `make run`), nunca por defecto.
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0") == "1"

# Raíz del proyecto (dos niveles arriba de backend/services/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
STYLE_DIR = os.path.join(PROJECT_ROOT, "frontend", "style")
CLIENT_LOGIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "client_logic")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STYLE_DIR, static_url_path="/static")

DB_PATH = os.path.join(PROJECT_ROOT, "storage_database", "documents_pool", "catalogo_archivos.db")
# Ya no se copian archivos acá dentro (ver AlmacenamientoReferenciado): esta
# carpeta solo aloja la base de datos SQLite.
MEDIA_FOLDER = os.path.join(PROJECT_ROOT, "storage_database", "documents_pool")
SEED_SQL_PATH = os.path.join(PROJECT_ROOT, "storage_database", "seeds", "orden_opciones_seed.sql")

# Asegurar que la carpeta física de almacenamiento exista en el disco
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Directorio raíz al que se restringen GET /api/explorar y POST /api/subir
# (CWE-22 / CodeQL py/path-injection). Por defecto es el home del usuario del
# SO que corre el server -el caso de uso típico de "tagear mis propios
# archivos"-, configurable si esos archivos viven en otro disco/punto de
# montaje. El chequeo de contención en sí se repite inline en cada punto que
# toca el filesystem (acá y en storage.py) en vez de vivir en un único
# helper compartido: CodeQL no reconoce un sanitizer aplicado dentro de una
# función auxiliar como una barrera para el dato que termina en el
# llamador, solo el patrón guardián inline en la misma función que hace el
# acceso a disco. Esto sigue corriendo como defensa en profundidad aunque
# `ruta`/`ruta_absoluta` ya no lleguen crudas desde el request -ver
# tokens.py: GET /api/explorar y POST /api/subir solo aceptan un token
# opaco, resuelto a la ruta que el propio servidor ya validó al mintearlo-.
RAIZ_PERMITIDA = os.path.realpath(os.environ.get("SISSYDEX_ROOT_PERMITIDO", os.path.expanduser("~")))


@app.route('/static/app.js')
def static_app_js():
    """app.js vive en frontend/client_logic, fuera de la carpeta static_folder."""
    return send_from_directory(CLIENT_LOGIC_DIR, 'app.js')


class LogicaNegocioArchivos:
    def __init__(self, conn=None, almacenamiento: EstrategiaAlmacenamiento | None = None):
        # conn/almacenamiento son inyectables (Strategy + Repository via
        # Dependency Inversion) para poder testear con una BD/carpeta
        # temporales; por defecto usan la BD y el storage reales del
        # proyecto, igual que antes de este refactor.
        self.conn = conn if conn is not None else sqlite3.connect(DB_PATH, check_same_thread=False)
        self.almacenamiento = almacenamiento if almacenamiento is not None else AlmacenamientoReferenciado(RAIZ_PERMITIDA)
        self.repo_archivos = RepositorioArchivos(self.conn)
        self.repo_orden = RepositorioOrdenOpciones(self.conn)
        # Namespaces separados para que un token de carpeta nunca pueda
        # reusarse como token de archivo (ver tokens.py / CLAUDE.md "Security:
        # path containment").
        self._tokens_carpetas = AlmacenTokens()
        self._tokens_archivos = AlmacenTokens()
        self._inicializar_db()

    def _inicializar_db(self):
        self.repo_archivos.crear_tabla_si_no_existe()
        self.repo_orden.crear_tabla_si_no_existe()

        # Si la tabla quedó vacía (BD nueva o borrada a mano), autopoblarla desde
        # el seed ya generado y versionado en git (storage_database/seeds/
        # orden_opciones_seed.sql), ejecutado acá con sqlite3 de Python -sin
        # depender del binario `sqlite3` de línea de comandos, que puede no estar
        # instalado (`make apply-seed` sí lo requiere). La fuente de verdad sigue
        # siendo el CSV (storage_database/seeds/orden_opciones.csv); NO se
        # hardcodea ninguna copia de esos datos acá, para evitar que este fallback
        # vuelva a divergir del CSV como pasaba antes.
        if self.repo_orden.contar_filas() == 0:
            if os.path.exists(SEED_SQL_PATH):
                with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
                    self.repo_orden.cargar_seed(f.read())
            else:
                print(f"[document_logic] Aviso: no se encontró {SEED_SQL_PATH}; "
                      "orden_opciones queda vacía. Corré 'make seed' para generarlo "
                      "a partir de orden_opciones.csv.")

    def validar_combinacion(self, opciones_seleccionadas):
        """
        REGLA DE NEGOCIO: Centraliza las restricciones aquí.
        SUSPENDIDO TEMPORALMENTE: las reglas antiguas referenciaban códigos
        (Opcion_Premium/Opcion_Free) que ya no existen tras el nuevo seed de
        orden_opciones. Se acepta cualquier combinación hasta que se defina el
        significado real de los nuevos códigos (a, b, aa, etc.) y se reescriban
        las reglas de negocio correspondientes.
        """
        return True, "Combinación totalmente válida."

    def calcular_hash_opciones(self, opciones_seleccionadas):
        """Genera el hash base del conjunto de opciones usando XOR."""
        hash_acumulado = 0
        for opcion in opciones_seleccionadas:
            hash_acumulado ^= xxhash.xxh32(opcion.encode('utf-8')).intdigest()
        return hash_acumulado

    def _separar_prefijo_hash(self, nombre_archivo):
        """
        El hash_calculado_hex siempre se genera con f"{...:08x}" (8 caracteres
        hexadecimales), y ese mismo texto se antepone al nombre físico del
        archivo (ver procesar_y_guardar_archivo / cambiar_opciones_archivo).
        Dado un nombre_original ya guardado, separa ese prefijo del nombre
        base original para poder reconstruir el nombre con un hash nuevo.
        Si los primeros 8 caracteres no son hexadecimales (archivo subido
        antes de esta funcionalidad), se asume que no tiene prefijo.
        """
        posible_prefijo = nombre_archivo[:8]
        if len(posible_prefijo) == 8 and all(c in '0123456789abcdefABCDEF' for c in posible_prefijo):
            return nombre_archivo[8:]
        return nombre_archivo

    def obtener_mapa_orden(self):
        """Retorna el orden actual ordenado de arriba a abajo (Y creciente)"""
        return self.repo_orden.obtener_mapa()

    def actualizar_orden_categoria(self, categoria, lista_opciones):
        """
        Actualiza en bloque las posiciones Y para una categoría específica.
        El repositorio borra por opcion_id sin importar la categoría (no solo
        por `categoria`): el drag-and-drop nativo reparenta el elemento
        arrastrado al soltar, así que "dragend" solo dispara el guardado en la
        columna DESTINO — la columna ORIGEN nunca recibe su propio guardado. Si
        solo borráramos por `categoria`, la fila vieja en la categoría de origen
        quedaría huérfana y la opción aparecería duplicada en dos categorías tras
        recargar la página.
        """
        self.repo_orden.reordenar_categoria(categoria, lista_opciones)

    def agregar_opcion(self, categoria, opcion_id):
        """
        Crea una nueva opción al final de una categoría (botón "Agregar" al pie
        de cada columna en la 2da Sección). posicion_y se calcula como el
        máximo actual de la categoría + 1, para que quede al final de la lista.
        opcion_id debe ser único en toda la tabla: actualizar_orden_categoria
        borra filas por opcion_id sin importar la categoría, así que un id
        duplicado entre categorías rompería ese guardado de orden.
        Retorna (True, None) si se creó, o (False, mensaje_error) si no.
        """
        if "," in opcion_id:
            return False, "El nombre de la opción no puede contener comas."

        if self.repo_orden.existe_opcion_id(opcion_id):
            return False, "Ya existe una opción con ese nombre."

        siguiente_posicion = self.repo_orden.obtener_siguiente_posicion(categoria)
        self.repo_orden.insertar(categoria, opcion_id, siguiente_posicion)

        return True, None

    def listar_archivos_por_combinacion(self, opciones_seleccionadas):
        """
        Busca y lista los archivos que fueron guardados bajo esta combinación exacta.
        Como el frontend llama a este método cada 2s (ver INTERVALO_REFRESCO_MS en
        app.js), autosanamos acá mismo: si un archivo fue borrado manualmente del
        disco (fuera de la app), su fila queda huérfana hasta que algo la limpie.
        Sin esta verificación, el polling del frontend no alcanzaba para reflejar
        el borrado -solo lo hacía storage_database/watcher.py, que requiere correr
        `make watch` en un proceso aparte-.
        """
        texto_opciones = ",".join(sorted(opciones_seleccionadas))
        filas = self.repo_archivos.buscar_por_combinacion(texto_opciones)

        archivos_listados = []
        ids_huerfanos = []
        for archivo_id, ruta_absoluta, hash_calculado_hex in filas:
            if self.almacenamiento.existe(ruta_absoluta):
                nombre_mostrado = os.path.basename(ruta_absoluta)
                archivos_listados.append({"id": archivo_id, "nombre": nombre_mostrado, "hash": hash_calculado_hex})
            else:
                ids_huerfanos.append(archivo_id)

        self.repo_archivos.eliminar_por_ids(ids_huerfanos)

        return archivos_listados

    def buscar_archivos_por_subconjunto(self, opciones_seleccionadas):
        """
        3ra Sección ("Resultados de Búsqueda" / botón Buscar): a diferencia de
        listar_archivos_por_combinacion (que exige la combinación EXACTA),
        esta búsqueda es por subconjunto -devuelve todo archivo cuyas
        opciones de identidad incluyan TODAS las opciones seleccionadas,
        pudiendo el archivo tener además otras opciones no seleccionadas. Si
        no hay ninguna opción seleccionada no se devuelve nada (igual que
        listar_archivos_por_combinacion con selección vacía): el conjunto
        vacío es subconjunto de cualquier archivo, pero "mostrar todo el pool
        sin haber tildado nada" no tiene sentido de negocio acá.
        Mismo autosanado de huérfanos que listar_archivos_por_combinacion,
        ver su docstring.
        """
        if not opciones_seleccionadas:
            return []

        conjunto_seleccionado = set(opciones_seleccionadas)
        filas = self.repo_archivos.obtener_todos()

        archivos_listados = []
        ids_huerfanos = []
        for archivo_id, ruta_absoluta, combinacion_opciones, hash_calculado_hex in filas:
            conjunto_archivo = set(combinacion_opciones.split(",")) if combinacion_opciones else set()
            if not conjunto_seleccionado <= conjunto_archivo:
                continue

            if self.almacenamiento.existe(ruta_absoluta):
                nombre_mostrado = os.path.basename(ruta_absoluta)
                archivos_listados.append({"id": archivo_id, "nombre": nombre_mostrado, "hash": hash_calculado_hex})
            else:
                ids_huerfanos.append(archivo_id)

        self.repo_archivos.eliminar_por_ids(ids_huerfanos)

        return archivos_listados

    def procesar_y_guardar_archivo(self, ruta_absoluta, opciones_seleccionadas):
        """
        El archivo NUNCA se copia (ver AlmacenamientoReferenciado): permanece
        en `ruta_absoluta`, elegida vía el explorador de directorios del
        backend (explorar_directorio / GET /api/explorar).
        1. Inserta el registro (con la ruta original) para obtener la PK
        2. Calcula el hash final combinando (PK ^ Hash_Opciones)
        3. Renombra el archivo IN PLACE anteponiendo el hash al nombre base
           (ej: hash "abc123" + "feele.txt" -> "abc123feele.txt", en el mismo
           directorio) y guarda esa ruta absoluta ya renombrada en
           `nombre_original`, ya que el resto del código usa esa columna para
           ubicar el archivo físico a través de self.almacenamiento.
        """
        # Limpiar el nombre base para evitar problemas de rutas en Windows/Linux
        nombre_base = secure_filename(os.path.basename(ruta_absoluta))

        # Serializar el conjunto de opciones para guardarlo como texto (ej: "Opcion_A,Opcion_B")
        texto_opciones = ",".join(sorted(opciones_seleccionadas))

        # Registrar inicialmente el archivo (con su ruta original) para detonar el AUTOINCREMENT (PK)
        pk_generada = self.repo_archivos.insertar_inicial(ruta_absoluta, texto_opciones)

        # Calcular el hash definitivo: Operación XOR entre la PK (int) y el Hash de Opciones (int)
        hash_opciones_int = self.calcular_hash_opciones(opciones_seleccionadas)
        hash_final_int = pk_generada ^ hash_opciones_int
        hash_final_hex = f"{hash_final_int:08x}"

        # Renombrar el archivo físico in place anteponiendo el hash al nombre base
        nombre_con_hash = f"{hash_final_hex}{nombre_base}"
        ruta_con_hash = self.almacenamiento.renombrar(ruta_absoluta, nombre_con_hash)

        # Actualizar el registro con su Hash definitivo y la ruta física final
        self.repo_archivos.actualizar_nombre_y_hash(pk_generada, ruta_con_hash, hash_final_hex)

        return pk_generada, hash_final_hex

    def eliminar_archivo(self, archivo_id):
        """
        Busca el registro por su PK, le quita el prefijo de hash a su nombre
        físico (renombrado in place, el archivo NUNCA se borra de disco) y
        elimina el registro de la base de datos.
        Retorna la ruta absoluta (ya sin el prefijo de hash) si se eliminó el
        registro, o None si el id no existe.
        """
        ruta_actual = self.repo_archivos.obtener_nombre_por_id(archivo_id)
        if ruta_actual is None:
            return None

        nombre_sin_hash = self._separar_prefijo_hash(os.path.basename(ruta_actual))
        # renombrar() no falla si el archivo ya no está presente en disco.
        ruta_sin_hash = self.almacenamiento.renombrar(ruta_actual, nombre_sin_hash)
        self.repo_archivos.eliminar_por_id(archivo_id)

        return ruta_sin_hash

    def cambiar_opciones_archivo(self, archivo_id, opciones_seleccionadas):
        """
        Reasigna la combinación de opciones de un archivo ya tageado (botón
        "Cambiar Opciones" / "Aceptar" en la 1ra Sección). Recalcula el hash
        igual que en procesar_y_guardar_archivo (PK XOR hash de opciones) y
        renombra el archivo físico IN PLACE para que su prefijo de hash quede
        acorde a la nueva combinación, conservando el nombre base y el
        directorio original.
        Retorna la ruta absoluta (nueva) si existía, o None si el id no existe.
        """
        ruta_actual = self.repo_archivos.obtener_nombre_por_id(archivo_id)
        if ruta_actual is None:
            return None

        nombre_base = self._separar_prefijo_hash(os.path.basename(ruta_actual))

        texto_opciones = ",".join(sorted(opciones_seleccionadas))
        hash_opciones_int = self.calcular_hash_opciones(opciones_seleccionadas)
        hash_final_hex = f"{(archivo_id ^ hash_opciones_int):08x}"
        nombre_con_hash = f"{hash_final_hex}{nombre_base}"

        # renombrar() no falla si el archivo ya no está presente en disco.
        ruta_nueva = self.almacenamiento.renombrar(ruta_actual, nombre_con_hash)
        self.repo_archivos.actualizar_combinacion(archivo_id, ruta_nueva, texto_opciones, hash_final_hex)

        return ruta_nueva

    def obtener_ruta_por_id(self, archivo_id):
        """Ruta absoluta del archivo referenciado por esta PK, o None si no existe."""
        return self.repo_archivos.obtener_nombre_por_id(archivo_id)

    def eliminar_registro_huerfano(self, archivo_id):
        """
        Autosanado: borra el registro de `archivos` con esta PK. Se usa cuando
        GET /media/<id> detecta que el archivo ya no existe en su ruta
        original (movido o borrado fuera de la app, o la ventana de espera
        antes de que storage_database/watcher.py actualice la BD), para que
        ese registro deje de aparecer en el listado desde ya.
        """
        self.repo_archivos.eliminar_por_id(archivo_id)

    def explorar_directorio(self, ruta):
        """
        Lista subcarpetas y archivos de `ruta` dentro de RAIZ_PERMITIDA (cae a
        esa raíz si `ruta` viene vacía, no es una carpeta válida, o intenta
        escapar de la raíz vía ".." o symlinks), para el explorador de
        directorios que reemplaza al <input type="file"> del navegador -este
        último no puede exponerle a JS la ruta absoluta de un archivo local,
        así que "AGREGAR ARCHIVO" navega el disco del propio servidor en vez
        de subir bytes-. No copia ni modifica nada, solo lee el árbol.
        La contención dentro de RAIZ_PERMITIDA se resuelve inline (no vía un
        helper compartido, ver comentario junto a RAIZ_PERMITIDA) justo antes
        de cada acceso a disco: `ruta` crudo del request nunca se usa
        directo, solo `ruta_resuelta`. El chequeo usa raise/except en vez de
        reasignar `ruta_resuelta` a la raíz sobre la marcha: CodeQL reconoce
        "código posterior solo se alcanza si el chequeo no lanzó" como
        barrera, no "esta variable se reasignó a un valor limpio en la rama
        que falló" -aunque el resultado final sea el mismo (cae a
        RAIZ_PERMITIDA), la forma del control de flujo es la que determina si
        el análisis estático confirma la validación-. Además mintea un token
        opaco por entrada y para "subir un nivel" (ver tokens.py): son la capa
        real que reemplaza a `ruta` como entrada de estos endpoints -ver
        CLAUDE.md "Security: path containment"-. `ruta_actual_texto` en la
        respuesta es SOLO para mostrar en pantalla: el frontend nunca la
        manda de vuelta, así que reflejarla no reintroduce una ruta cruda
        como dato de entrada.
        """
        ruta_resuelta = RAIZ_PERMITIDA
        try:
            if not ruta:
                raise ValueError("ruta vacía")

            candidata = ruta if os.path.isabs(ruta) else os.path.join(RAIZ_PERMITIDA, ruta)
            candidata_resuelta = os.path.realpath(candidata)
            if not (candidata_resuelta == RAIZ_PERMITIDA or candidata_resuelta.startswith(RAIZ_PERMITIDA + os.sep)):
                raise ValueError("fuera de la raíz permitida")
            if not os.path.isdir(candidata_resuelta):
                raise ValueError("no es un directorio válido")

            ruta_resuelta = candidata_resuelta
        except ValueError:
            pass

        entradas = []
        try:
            with os.scandir(ruta_resuelta) as directorio:
                entradas = self._listar_entradas_visibles(directorio)
        except PermissionError:
            pass

        # Mintea un token por entrada (ver tokens.py): el valor minteado sale
        # de `ruta_resuelta` (ya validada arriba) + el nombre que el propio
        # os.scandir devolvió, nunca de `ruta` cruda del request -por eso el
        # token resultante es seguro de reflejar de vuelta al cliente sin que
        # eso reintroduzca la ruta como dato de entrada no confiable-.
        for entrada in entradas:
            ruta_entrada = os.path.join(ruta_resuelta, entrada["nombre"])
            almacen = self._tokens_carpetas if entrada["es_carpeta"] else self._tokens_archivos
            entrada["token"] = almacen.mintear(ruta_entrada)

        ruta_padre_candidata = os.path.dirname(ruta_resuelta)
        token_padre = None
        if ruta_padre_candidata == RAIZ_PERMITIDA or ruta_padre_candidata.startswith(RAIZ_PERMITIDA + os.sep):
            token_padre = self._tokens_carpetas.mintear(ruta_padre_candidata)

        return {
            "ruta_actual_texto": ruta_resuelta,
            "token_padre": token_padre,
            "entradas": entradas,
        }

    def _listar_entradas_visibles(self, directorio):
        """
        Filtra ocultos y ordena carpetas primero, luego alfabético. `directorio`
        ya es un os.scandir() en curso sobre una ruta que explorar_directorio
        validó contra RAIZ_PERMITIDA -esta función no vuelve a tocar el
        filesystem por fuera de leer atributos de los DirEntry ya obtenidos-.
        """
        entradas = []
        for entrada in directorio:
            if entrada.name.startswith('.'):
                continue
            try:
                es_carpeta = entrada.is_dir()
            except OSError:
                continue
            entradas.append({"nombre": entrada.name, "es_carpeta": es_carpeta})

        entradas.sort(key=lambda entrada: (not entrada["es_carpeta"], entrada["nombre"].lower()))
        return entradas

    def resolver_token_carpeta(self, token):
        """Ruta absoluta minteada por explorar_directorio para este token, o None."""
        return self._tokens_carpetas.resolver(token) if token else None

    def resolver_token_archivo(self, token):
        """Ruta absoluta minteada por explorar_directorio para este token, o None."""
        resultado = self._tokens_archivos.resolver(token) if token else None
        return str(resultado) if resultado is not None else None

    def invalidar_token_archivo(self, token):
        """
        Se llama tras un tageo exitoso (ver POST /api/subir): sin esto, un
        replay del mismo token apuntaría a la ruta PRE-hash, que ya no existe
        con ese nombre -renombrar() no falla si el origen no está, así que un
        replay silencioso insertaría una segunda fila de BD apuntando a un
        archivo que nunca se creó-.
        """
        self._tokens_archivos.descartar(token)


negocio = LogicaNegocioArchivos()

# =====================================================================
# ENDPOINTS PARA EL ORDENAMIENTO VISUAL PERSISTENTE
# =====================================================================


@app.route('/api/orden', methods=['GET'])
def obtener_orden():
    return jsonify(negocio.obtener_mapa_orden())


@app.route('/api/orden/guardar', methods=['POST'])
def guardar_orden():
    data = request.json or {}
    categoria = data.get('categoria')
    lista_opciones = data.get('opciones', [])

    if not categoria:
        return jsonify({"success": False, "error": "Categoría faltante"}), 400

    negocio.actualizar_orden_categoria(categoria, lista_opciones)
    return jsonify({"success": True})


@app.route('/api/orden/agregar', methods=['POST'])
def agregar_opcion():
    data = request.json or {}
    categoria = data.get('categoria')
    opcion_id = (data.get('opcion_id') or '').strip()

    if not categoria or not opcion_id:
        return jsonify({"success": False, "error": "Categoría u opción faltante"}), 400

    exito, error = negocio.agregar_opcion(categoria, opcion_id)
    if not exito:
        return jsonify({"success": False, "error": error}), 400

    return jsonify({"success": True, "opcion_id": opcion_id})

# =====================================================================
# ENDPOINT PARA RENDERIZAR LA INTERFAZ WEB
# =====================================================================


@app.route('/')
def home():
    # Flask buscará automáticamente este archivo dentro de la carpeta 'templates/'
    return render_template('index.html')

# =====================================================================
# ENDPOINTS DE LA API
# =====================================================================


@app.route('/api/procesar', methods=['POST'])
def procesar_seleccion():
    data = request.json or {}
    opciones = data.get('opciones', [])

    valido, mensaje = negocio.validar_combinacion(opciones)
    archivos = negocio.listar_archivos_por_combinacion(opciones) if valido else []

    return jsonify({
        "valido": valido,
        "mensaje": mensaje,
        "archivos": archivos
    })


@app.route('/api/buscar', methods=['POST'])
def buscar_archivos():
    """
    3ra Sección ("Resultados de Búsqueda"): a diferencia de /api/procesar
    (combinación EXACTA, refrescado automáticamente en cada cambio de
    checkbox), esta ruta solo se dispara con el botón "Buscar" y devuelve
    archivos por subconjunto -ver LogicaNegocioArchivos.buscar_archivos_por_subconjunto-.
    """
    data = request.json or {}
    opciones = data.get('opciones', [])

    archivos = negocio.buscar_archivos_por_subconjunto(opciones)

    return jsonify({"archivos": archivos})


@app.route('/api/explorar', methods=['GET'])
def explorar_directorio():
    """
    Backend del explorador de directorios que reemplaza al <input
    type="file"> nativo: el navegador no puede exponerle a JS la ruta
    absoluta de un archivo local, así que "AGREGAR ARCHIVO" navega el disco
    del propio servidor (esta app corre localmente) en vez de subir bytes.

    `token` (minteado por una respuesta anterior de este mismo endpoint, ver
    LogicaNegocioArchivos.explorar_directorio) es la única entrada aceptada:
    se resuelve acá a la ruta que el servidor ya validó al mintearlo, así que
    ninguna ruta de filesystem cruda llega nunca desde el request (ver
    CLAUDE.md "Security: path containment"). Un token vacío/desconocido cae
    al mismo fallback ('' -> RAIZ_PERMITIDA) que explorar_directorio ya
    maneja para cualquier entrada inválida.
    """
    token = request.args.get('token', '')
    ruta = negocio.resolver_token_carpeta(token) or ''
    return jsonify(negocio.explorar_directorio(ruta))


@app.route('/api/subir', methods=['POST'])
def subir_archivo():
    data = request.json or {}
    token = data.get('token')
    opciones = data.get('opciones', [])

    # El archivo se referencia por ruta absoluta (elegida vía el explorador
    # de GET /api/explorar), nunca se sube/copia. `token` (minteado por una
    # respuesta anterior de GET /api/explorar) es la única entrada aceptada:
    # se resuelve acá a la ruta que el servidor ya validó al mintearlo, así
    # que ninguna ruta de filesystem cruda llega nunca desde este request
    # (ver CLAUDE.md "Security: path containment"). El chequeo de
    # os.path.isfile va en su propia sentencia `if`, dominada por el `return`
    # del chequeo de token anterior -la forma que CodeQL reconoce como
    # barrera-.
    if not token:
        return jsonify({"success": False, "error": "La ruta indicada no corresponde a un archivo válido."}), 400

    ruta_absoluta = negocio.resolver_token_archivo(token)
    if not ruta_absoluta or not os.path.isfile(ruta_absoluta):
        return jsonify({"success": False, "error": "La ruta indicada no corresponde a un archivo válido."}), 400

    if not os.path.isfile(ruta_absoluta):
        return jsonify({"success": False, "error": "La ruta indicada no corresponde a un archivo válido."}), 400

    # Validar que la combinación sea permitida antes de tocar disco/DB
    valido, mensaje = negocio.validar_combinacion(opciones)
    if not valido:
        return jsonify({"success": False, "error": mensaje}), 400

    pk, hash_resultado = negocio.procesar_y_guardar_archivo(ruta_absoluta, opciones)
    negocio.invalidar_token_archivo(token)

    return jsonify({
        "success": True,
        "pk": pk,
        "hash_generado": hash_resultado
    })

# =====================================================================
# ENDPOINT PARA SERVIR ARCHIVOS MULTIMEDIA DESDE SU UBICACIÓN ORIGINAL
# =====================================================================


@app.route('/media/<int:archivo_id>')
def servir_archivo_multimedia(archivo_id):
    """
    Busca la ruta absoluta del archivo por su PK y lo envía al navegador.
    Flask detectará automáticamente el tipo (mp3, mp4, png, txt) para que
    el navegador lo reproduzca en lugar de descargarlo de golpe. Los archivos
    ya no viven bajo MEDIA_FOLDER (ver AlmacenamientoReferenciado), así que se
    sirven desde su directorio original en vez de por nombre relativo.
    """
    ruta_absoluta = negocio.obtener_ruta_por_id(archivo_id)

    if ruta_absoluta is None or not os.path.isfile(ruta_absoluta):
        # El archivo ya no existe en su ruta original (movido/borrado fuera de
        # la app, o la ventana de espera antes de que el watcher actualice la
        # BD). Autosanar el registro huérfano y mostrar un error claro en vez
        # del 404 genérico de Flask.
        negocio.eliminar_registro_huerfano(archivo_id)
        return (
            "<h2>Archivo no encontrado</h2>"
            "<p>El archivo ya no existe en su ubicación original. "
            "Es posible que haya sido movido o eliminado.</p>"
            '<p><a href="/">Volver al inicio</a></p>'
        ), 404

    directorio, nombre_archivo = os.path.split(ruta_absoluta)
    return send_from_directory(directorio, nombre_archivo)

# =====================================================================
# ENDPOINT PARA ELIMINAR UN ARCHIVO (SOLO BASE DE DATOS; EL ARCHIVO FÍSICO
# PERMANECE EN SU UBICACIÓN, SOLO SE LE QUITA EL PREFIJO DE HASH)
# =====================================================================


@app.route('/api/eliminar/<int:archivo_id>', methods=['DELETE'])
def eliminar_archivo(archivo_id):
    """
    Busca el archivo usando su PK, le quita el prefijo de hash del nombre
    físico (in place) y finalmente elimina su registro en la base de datos.
    """
    try:
        resultado = negocio.eliminar_archivo(archivo_id)

        if resultado is None:
            return jsonify({"success": False, "error": "El archivo no existe en la base de datos."}), 404

        return jsonify({"success": True, "mensaje": "Archivo eliminado correctamente."})

    except Exception:
        # No devolver el detalle de la excepción al cliente: podría revelar
        # rutas del servidor u otra información interna. El stack trace queda
        # solo en el log del servidor.
        app.logger.exception("Error al eliminar archivo id=%s", archivo_id)
        return jsonify({"success": False, "error": "Error al eliminar el archivo."}), 500

# =====================================================================
# ENDPOINT PARA CAMBIAR LA COMBINACIÓN DE OPCIONES DE UN ARCHIVO YA SUBIDO
# =====================================================================


@app.route('/api/archivos/<int:archivo_id>/opciones', methods=['PUT'])
def cambiar_opciones_archivo(archivo_id):
    """
    Reasigna la combinación de opciones de un archivo existente (botón
    "Cambiar Opciones" -> "Aceptar" de la 1ra Sección). Renombra el archivo
    físico in place (nuevo prefijo de hash, mismo directorio) y actualiza su
    fila en `archivos` acorde.
    """
    data = request.json or {}
    opciones = data.get('opciones', [])

    valido, mensaje = negocio.validar_combinacion(opciones)
    if not valido:
        return jsonify({"success": False, "error": mensaje}), 400

    nombre_archivo = negocio.cambiar_opciones_archivo(archivo_id, opciones)

    if nombre_archivo is None:
        return jsonify({"success": False, "error": "El archivo no existe en la base de datos."}), 404

    return jsonify({"success": True, "nombre": nombre_archivo})


if __name__ == '__main__':
    # Solo localhost por defecto: esta ruta de entrada (`make run` / correr
    # este archivo directo) no tiene autenticación y expone tageo de
    # cualquier archivo dentro de RAIZ_PERMITIDA, así que no debe quedar
    # alcanzable desde el resto de la red local sin que alguien lo pida
    # explícitamente. `backend/app.py` -el entrypoint real de Docker- tiene
    # su propio app.run(host='0.0.0.0', ...) sin tocar, porque ahí SÍ hace
    # falta para que el mapeo de puertos del contenedor funcione.
    HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(host=HOST, port=5000, debug=DEBUG_MODE)
