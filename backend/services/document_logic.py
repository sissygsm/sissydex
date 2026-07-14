import os
import sqlite3
import xxhash
from flask import Flask, jsonify, request, render_template, send_from_directory
from markupsafe import escape
from werkzeug.utils import secure_filename

# Raíz del proyecto (dos niveles arriba de backend/services/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
STYLE_DIR = os.path.join(PROJECT_ROOT, "frontend", "style")
CLIENT_LOGIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "client_logic")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STYLE_DIR, static_url_path="/static")

DB_PATH = os.path.join(PROJECT_ROOT, "storage_database", "documents_pool", "catalogo_archivos.db")
MEDIA_FOLDER = os.path.join(PROJECT_ROOT, "storage_database", "documents_pool")
SEED_SQL_PATH = os.path.join(PROJECT_ROOT, "storage_database", "seeds", "orden_opciones_seed.sql")

# Asegurar que la carpeta física de almacenamiento exista en el disco
os.makedirs(MEDIA_FOLDER, exist_ok=True)


@app.route('/static/app.js')
def static_app_js():
    """app.js vive en frontend/client_logic, fuera de la carpeta static_folder."""
    return send_from_directory(CLIENT_LOGIC_DIR, 'app.js')

class LogicaNegocioArchivos:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._inicializar_db()

    def _inicializar_db(self):
        # 1. Tabla de archivos existente
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_original TEXT NOT NULL,
                combinacion_opciones TEXT NOT NULL,
                hash_calculado_hex TEXT
            )
        ''')
        
        # 2. NUEVA TABLA: Almacena de forma persistente la matriz visual (X, Y) de cada opción
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orden_opciones (
                categoria TEXT NOT NULL,
                opcion_id TEXT NOT NULL,
                posicion_y INTEGER NOT NULL,
                PRIMARY KEY (categoria, opcion_id)
            )
        ''')
        
        # Si la tabla quedó vacía (BD nueva o borrada a mano), autopoblarla desde
        # el seed ya generado y versionado en git (storage_database/seeds/
        # orden_opciones_seed.sql), ejecutado acá con sqlite3 de Python -sin
        # depender del binario `sqlite3` de línea de comandos, que puede no estar
        # instalado (`make apply-seed` sí lo requiere). La fuente de verdad sigue
        # siendo el CSV (storage_database/seeds/orden_opciones.csv); NO se
        # hardcodea ninguna copia de esos datos acá, para evitar que este fallback
        # vuelva a divergir del CSV como pasaba antes.
        cursor.execute("SELECT COUNT(*) FROM orden_opciones")
        if cursor.fetchone()[0] == 0:
            if os.path.exists(SEED_SQL_PATH):
                with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
                    self.conn.executescript(f.read())
            else:
                print(f"[document_logic] Aviso: no se encontró {SEED_SQL_PATH}; "
                      "orden_opciones queda vacía. Corré 'make seed' para generarlo "
                      "a partir de orden_opciones.csv.")

        self.conn.commit()
        cursor.close()

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
        cursor = self.conn.cursor()
        cursor.execute("SELECT categoria, opcion_id, posicion_y FROM orden_opciones ORDER BY categoria, posicion_y ASC")
        filas = cursor.fetchall()

        # Estructurar dinámicamente como un diccionario de categorías: ya no se
        # asume una lista fija (Suscripcion/Region/TipoDatos), sino que se toman
        # las categorías tal cual existen en la tabla (p. ej. Grupo_c, Grupo_e...)
        mapa = {}
        for cat, op_id, pos in filas:
            mapa.setdefault(cat, []).append(op_id)
        
        cursor.close()
        return mapa

    def actualizar_orden_categoria(self, categoria, lista_opciones):
        """Actualiza en bloque las posiciones Y para una categoría específica"""
        cursor = self.conn.cursor()

        # Eliminar cualquier fila previa de estas opciones sin importar en qué
        # categoría estuvieran antes. El drag-and-drop nativo reparenta el elemento
        # arrastrado al soltar, así que "dragend" solo dispara el guardado en la
        # columna DESTINO — la columna ORIGEN nunca recibe su propio guardado. Si
        # solo borráramos por `categoria`, la fila vieja en la categoría de origen
        # quedaría huérfana y la opción aparecería duplicada en dos categorías tras
        # recargar la página.
        cursor.executemany(
            "DELETE FROM orden_opciones WHERE opcion_id = ?",
            [(opcion_id,) for opcion_id in lista_opciones]
        )

        # Insertar las nuevas posiciones Y correlativas (1, 2, 3...)
        for indice, opcion_id in enumerate(lista_opciones, start=1):
            cursor.execute(
                "INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES (?, ?, ?)",
                (categoria, opcion_id, indice)
            )
        self.conn.commit()
        cursor.close()

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

        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM orden_opciones WHERE opcion_id = ?", (opcion_id,))
        if cursor.fetchone():
            cursor.close()
            return False, "Ya existe una opción con ese nombre."

        cursor.execute("SELECT COALESCE(MAX(posicion_y), 0) FROM orden_opciones WHERE categoria = ?", (categoria,))
        siguiente_posicion = cursor.fetchone()[0] + 1

        cursor.execute(
            "INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES (?, ?, ?)",
            (categoria, opcion_id, siguiente_posicion)
        )
        self.conn.commit()
        cursor.close()

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
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, nombre_original, hash_calculado_hex FROM archivos WHERE combinacion_opciones = ?",
            (texto_opciones,)
        )
        filas = cursor.fetchall()

        archivos_listados = []
        ids_huerfanos = []
        for archivo_id, nombre_original, hash_calculado_hex in filas:
            if os.path.exists(os.path.join(MEDIA_FOLDER, nombre_original)):
                archivos_listados.append({"id": archivo_id, "nombre": nombre_original, "hash": hash_calculado_hex})
            else:
                ids_huerfanos.append(archivo_id)

        if ids_huerfanos:
            cursor.executemany("DELETE FROM archivos WHERE id = ?", [(i,) for i in ids_huerfanos])
            self.conn.commit()

        cursor.close()
        return archivos_listados

    def procesar_y_guardar_archivo(self, archivo_flask, opciones_seleccionadas):
        """
        1. Guarda el archivo físicamente en media/ con su nombre original
        2. Inserta el registro para obtener la PK automáticamente
        3. Calcula el hash final combinando (PK ^ Hash_Opciones)
        4. Renombra el archivo físico anteponiendo el hash al nombre original
           (ej: hash "abc123" + "feele.txt" -> "abc123feele.txt") y guarda ese
           mismo nombre en `nombre_original`, ya que el resto del código usa
           esa columna para ubicar el archivo físico en MEDIA_FOLDER.
        """
        # Limpiar el nombre del archivo para evitar problemas de rutas en Windows/Linux
        nombre_base = secure_filename(archivo_flask.filename)
        ruta_temporal = os.path.join(MEDIA_FOLDER, nombre_base)

        # Guardar el archivo físicamente en la carpeta media/ con su nombre base
        # (todavía no se conoce el hash: depende de la PK autoincremental)
        archivo_flask.save(ruta_temporal)

        # Serializar el conjunto de opciones para guardarlo como texto (ej: "Opcion_A,Opcion_B")
        texto_opciones = ",".join(sorted(opciones_seleccionadas))

        # Registrar inicialmente el archivo para detonar el AUTOINCREMENT (PK)
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO archivos (nombre_original, combinacion_opciones) VALUES (?, ?)",
            (nombre_base, texto_opciones)
        )
        pk_generada = cursor.lastrowid  # Obtener la PK generada automáticamente

        # Calcular el hash definitivo: Operación XOR entre la PK (int) y el Hash de Opciones (int)
        hash_opciones_int = self.calcular_hash_opciones(opciones_seleccionadas)
        hash_final_int = pk_generada ^ hash_opciones_int
        hash_final_hex = f"{hash_final_int:08x}"

        # Renombrar el archivo físico anteponiendo el hash al nombre original
        nombre_con_hash = f"{hash_final_hex}{nombre_base}"
        ruta_final = os.path.join(MEDIA_FOLDER, nombre_con_hash)
        os.rename(ruta_temporal, ruta_final)

        # Actualizar el registro con su Hash definitivo y el nombre físico final
        cursor.execute(
            "UPDATE archivos SET nombre_original = ?, hash_calculado_hex = ? WHERE id = ?",
            (nombre_con_hash, hash_final_hex, pk_generada)
        )
        self.conn.commit()
        cursor.close()

        return pk_generada, hash_final_hex

    def eliminar_archivo(self, archivo_id):
        """
        Busca el registro por su PK, borra el archivo físico si aún existe
        y elimina el registro de la base de datos.
        Retorna el nombre_original si se eliminó, o None si el id no existe.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT nombre_original FROM archivos WHERE id = ?", (archivo_id,))
        resultado = cursor.fetchone()

        if not resultado:
            cursor.close()
            return None

        nombre_archivo = resultado[0]
        ruta_fisica = os.path.join(MEDIA_FOLDER, nombre_archivo)

        # Eliminar el archivo físico solo si sigue presente en disco
        if os.path.exists(ruta_fisica):
            os.remove(ruta_fisica)

        cursor.execute("DELETE FROM archivos WHERE id = ?", (archivo_id,))
        self.conn.commit()
        cursor.close()

        return nombre_archivo

    def cambiar_opciones_archivo(self, archivo_id, opciones_seleccionadas):
        """
        Reasigna la combinación de opciones de un archivo ya subido (botón
        "Cambiar Opciones" / "Aceptar" en la 1ra Sección). Recalcula el hash
        igual que en procesar_y_guardar_archivo (PK XOR hash de opciones) y
        renombra el archivo físico para que su prefijo de hash quede acorde a
        la nueva combinación, conservando el nombre base original.
        Retorna el nombre_original (nuevo) si existía, o None si el id no existe.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT nombre_original FROM archivos WHERE id = ?", (archivo_id,))
        resultado = cursor.fetchone()

        if not resultado:
            cursor.close()
            return None

        nombre_actual = resultado[0]
        nombre_base = self._separar_prefijo_hash(nombre_actual)

        texto_opciones = ",".join(sorted(opciones_seleccionadas))
        hash_opciones_int = self.calcular_hash_opciones(opciones_seleccionadas)
        hash_final_hex = f"{(archivo_id ^ hash_opciones_int):08x}"
        nombre_nuevo = f"{hash_final_hex}{nombre_base}"

        ruta_actual = os.path.join(MEDIA_FOLDER, nombre_actual)
        ruta_nueva = os.path.join(MEDIA_FOLDER, nombre_nuevo)
        if os.path.exists(ruta_actual):
            os.rename(ruta_actual, ruta_nueva)

        cursor.execute(
            "UPDATE archivos SET nombre_original = ?, combinacion_opciones = ?, hash_calculado_hex = ? WHERE id = ?",
            (nombre_nuevo, texto_opciones, hash_final_hex, archivo_id)
        )
        self.conn.commit()
        cursor.close()

        return nombre_nuevo

    def eliminar_por_nombre(self, nombre_archivo):
        """
        Autosanado: borra cualquier registro de `archivos` cuyo nombre_original
        coincida, sin importar su PK. Se usa cuando /media/<filename> detecta
        que el archivo ya no existe físicamente (borrado manual, watcher, o la
        ventana de espera antes de que cualquiera de los dos actualice la BD),
        para que ese registro deje de aparecer en el listado desde ya, en vez
        de depender únicamente de que storage_database/watcher.py esté corriendo.
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM archivos WHERE nombre_original = ?", (nombre_archivo,))
        eliminados = cursor.rowcount
        self.conn.commit()
        cursor.close()
        return eliminados


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
# ENDPOINTS DE LA API (MANEJO DE MULTIPART FORM DATA PARA SUBIDA REAL)
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

@app.route('/api/subir', methods=['POST'])
def subir_archivo():
    # Validar que venga el archivo físico en el cuerpo del request
    if 'archivo' not in request.files:
        return jsonify({"success": False, "error": "No se envió ningún archivo"}), 400
        
    archivo = request.files['archivo']
    # Recuperar las opciones asociadas que vienen desde el formulario
    opciones = request.form.getlist('opciones')

    # Validar que la combinación sea permitida antes de guardar en disco/DB
    valido, mensaje = negocio.validar_combinacion(opciones)
    if not valido:
        return jsonify({"success": False, "error": mensaje}), 400

    pk, hash_resultado = negocio.procesar_y_guardar_archivo(archivo, opciones)
    
    return jsonify({
        "success": True,
        "pk": pk,
        "hash_generado": hash_resultado
    })

# =====================================================================
# ENDPOINT PARA SERVIR ARCHIVOS MULTIMEDIA DESDE LA CARPETA MEDIA/
# =====================================================================
@app.route('/media/<filename>')
def servir_archivo_multimedia(filename):
    """
    Busca el archivo dentro de la carpeta 'media/' y lo envía al navegador.
    Flask detectará automáticamente el tipo (mp3, mp4, png, txt) para que
    el navegador lo reproduzca en lugar de descargarlo de golpe.
    """
    ruta_fisica = os.path.join(MEDIA_FOLDER, filename)

    if not os.path.isfile(ruta_fisica):
        # El archivo ya no existe en disco (borrado manual, por el watcher, o
        # la ventana de espera antes de que cualquiera de los dos actualice la
        # BD). Autosanar cualquier registro huérfano que aún lo referencie, y
        # mostrar un error claro en vez del 404 genérico de Flask.
        negocio.eliminar_por_nombre(filename)
        nombre_seguro = escape(filename)
        return (
            "<h2>Archivo no encontrado</h2>"
            f"<p>El archivo <code>{nombre_seguro}</code> ya no existe en el almacenamiento. "
            "Es posible que haya sido eliminado.</p>"
            '<p><a href="/">Volver al inicio</a></p>'
        ), 404

    return send_from_directory(MEDIA_FOLDER, filename)

# =====================================================================
# ENDPOINT PARA ELIMINAR UN ARCHIVO (DISCO + BASE DE DATOS)
# =====================================================================
@app.route('/api/eliminar/<int:archivo_id>', methods=['DELETE'])
def eliminar_archivo(archivo_id):
    """
    Busca el nombre del archivo usando su PK, lo borra de la carpeta media/
    y finalmente elimina su registro en la base de datos.
    """
    try:
        resultado = negocio.eliminar_archivo(archivo_id)

        if resultado is None:
            return jsonify({"success": False, "error": "El archivo no existe en la base de datos."}), 404

        return jsonify({"success": True, "mensaje": "Archivo eliminado correctamente."})

    except Exception as e:
        return jsonify({"success": False, "error": f"Error al eliminar: {str(e)}"}), 500

# =====================================================================
# ENDPOINT PARA CAMBIAR LA COMBINACIÓN DE OPCIONES DE UN ARCHIVO YA SUBIDO
# =====================================================================
@app.route('/api/archivos/<int:archivo_id>/opciones', methods=['PUT'])
def cambiar_opciones_archivo(archivo_id):
    """
    Reasigna la combinación de opciones de un archivo existente (botón
    "Cambiar Opciones" -> "Aceptar" de la 1ra Sección). No mueve ni renombra
    el archivo físico, solo actualiza su fila en `archivos`.
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
    app.run(port=5000, debug=True)
