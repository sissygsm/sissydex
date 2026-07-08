import os
import sqlite3
import xxhash
from flask import Flask, jsonify, request, render_template, send_from_directory
from werkzeug.utils import secure_filename

# Raíz del proyecto (dos niveles arriba de backend/services/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
STYLE_DIR = os.path.join(PROJECT_ROOT, "frontend", "style")
CLIENT_LOGIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "client_logic")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STYLE_DIR, static_url_path="/static")

DB_PATH = os.path.join(PROJECT_ROOT, "storage_database", "documents_pool", "catalogo_archivos.db")
MEDIA_FOLDER = os.path.join(PROJECT_ROOT, "storage_database", "documents_pool")

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
        
        # Insertar valores por defecto ordenados inicialmente (X, Y) si la tabla está vacía
        cursor.execute("SELECT COUNT(*) FROM orden_opciones")
        if cursor.fetchone()[0] == 0:
            valores_iniciales = [
                # Categoría a (Opciones A hasta H)
                ('a', 'A', 1), ('a', 'B', 2), ('a', 'C', 3), ('a', 'D', 4),
                ('a', 'E', 5), ('a', 'F', 6), ('a', 'G', 7), ('a', 'H', 8),

                # Categoría c (Opciones I hasta N)
                ('c', 'I', 1), ('c', 'J', 2), ('c', 'K', 3), ('c', 'L', 4),
                ('c', 'M', 5), ('c', 'N', 6),

                # Categoría e (Opciones O hasta X)
                ('e', 'O', 1), ('e', 'P', 2), ('e', 'Q', 3), ('e', 'R', 4),
                ('e', 'S', 5), ('e', 'T', 6), ('e', 'U', 7), ('e', 'V', 8),
                ('e', 'W', 9), ('e', 'X', 10),

                # Categoría g (Opciones Y hasta JJ)
                ('g', 'Y', 1), ('g', 'Z', 2), ('g', 'AA', 3), ('g', 'BB', 4),
                ('g', 'CC', 5), ('g', 'DD', 6), ('g', 'EE', 7), ('g', 'FF', 8),
                ('g', 'GG', 9), ('g', 'HH', 10), ('g', 'II', 11), ('g', 'JJ', 12),

                # Categoría i (Opciones KK hasta MM)
                ('i', 'KK', 1), ('i', 'LL', 2), ('i', 'MM', 3),

                # Categoría k (Opciones NN hasta PP)
                ('k', 'NN', 1), ('k', 'OO', 2), ('k', 'PP', 3)
            ]

            cursor.executemany(
                "INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES (?, ?, ?)",
                valores_iniciales
            )
            self.conn.commit()
            
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
        # Eliminar el orden viejo de esa categoría para evitar conflictos de llave primaria
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM orden_opciones WHERE categoria = ?", (categoria,))
        
        # Insertar las nuevas posiciones Y correlativas (1, 2, 3...)
        for indice, opcion_id in enumerate(lista_opciones, start=1):
            cursor.execute(
                "INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES (?, ?, ?)",
                (categoria, opcion_id, indice)
            )
        self.conn.commit()
        cursor.close()

    def listar_archivos_por_combinacion(self, opciones_seleccionadas):
        """Busca y lista los archivos que fueron guardados bajo esta combinación exacta."""
        texto_opciones = ",".join(sorted(opciones_seleccionadas))
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, nombre_original, hash_calculado_hex FROM archivos WHERE combinacion_opciones = ?",
            (texto_opciones,)
        )
        archivos_listados = [{"id": fila[0], "nombre": fila[1], "hash": fila[2]} for fila in cursor.fetchall()]
        cursor.close()
        return archivos_listados

    def procesar_y_guardar_archivo(self, archivo_flask, opciones_seleccionadas):
        """
        1. Guarda el archivo físicamente en media/
        2. Inserta el registro para obtener la PK automáticamente
        3. Calcula el hash final combinando (PK ^ Hash_Opciones) y actualiza la fila
        """
        # Limpiar el nombre del archivo para evitar problemas de rutas en Windows/Linux
        nombre_original = secure_filename(archivo_flask.filename)
        ruta_destino = os.path.join(MEDIA_FOLDER, nombre_original)
        
        # Guardar el archivo físicamente en la carpeta media/
        archivo_flask.save(ruta_destino)

        # Serializar el conjunto de opciones para guardarlo como texto (ej: "Opcion_A,Opcion_B")
        texto_opciones = ",".join(sorted(opciones_seleccionadas))

        # Registrar inicialmente el archivo para detonar el AUTOINCREMENT (PK)
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO archivos (nombre_original, combinacion_opciones) VALUES (?, ?)",
            (nombre_original, texto_opciones)
        )
        pk_generada = cursor.lastrowid  # Obtener la PK generada automáticamente

        # Calcular el hash definitivo: Operación XOR entre la PK (int) y el Hash de Opciones (int)
        hash_opciones_int = self.calcular_hash_opciones(opciones_seleccionadas)
        hash_final_int = pk_generada ^ hash_opciones_int
        hash_final_hex = f"{hash_final_int:08x}"

        # Actualizar el registro con su Hash definitivo asignado
        cursor.execute(
            "UPDATE archivos SET hash_calculado_hex = ? WHERE id = ?",
            (hash_final_hex, pk_generada)
        )
        self.conn.commit()
        cursor.close()
        
        return pk_generada, hash_final_hex
   


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
        # 1. Buscar el nombre del archivo en la base de datos usando la PK
        negocio.cursor.execute("SELECT nombre_original FROM archivos WHERE id = ?", (archivo_id,))
        resultado = negocio.cursor.fetchone()
        
        if not resultado:
            return jsonify({"success": False, "error": "El archivo no existe en la base de datos."}), 404
            
        nombre_archivo = resultado[0]
        ruta_fisica = os.path.join(MEDIA_FOLDER, nombre_archivo)
        
        # 2. Eliminar el archivo físico del disco si existe
        if os.path.exists(ruta_fisica):
            os.remove(ruta_fisica)
            
        # 3. Eliminar el registro de la base de datos
        negocio.cursor.execute("DELETE FROM archivos WHERE id = ?", (archivo_id,))
        negocio.conn.commit()
        
        return jsonify({"success": True, "mensaje": "Archivo eliminado correctamente."})
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al eliminar: {str(e)}"}), 500
    

if __name__ == '__main__':
    app.run(port=5000, debug=True)
