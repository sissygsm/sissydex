"""
Repository (GoF/PoEAA) para las dos tablas de catalogo_archivos.db. Antes de
este módulo, LogicaNegocioArchivos ejecutaba sqlite3 directo (cursor.execute
mezclado con reglas de negocio) — este módulo centraliza ese acceso, para que
LogicaNegocioArchivos deje de saber que hay SQL de por medio.

Cada método mapea 1:1 con un bloque de SQL que existía antes en
document_logic.py, preservando exactamente los mismos límites de commit()
que tenía el código original (no se reagrupan transacciones).
"""


class RepositorioArchivos:
    """INTERFAZ A PROTEGER: único punto de acceso SQL a la tabla `archivos`."""

    def __init__(self, conn):
        self._conn = conn

    def crear_tabla_si_no_existe(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_original TEXT NOT NULL,
                combinacion_opciones TEXT NOT NULL,
                hash_calculado_hex TEXT
            )
        ''')
        cursor.close()

    def insertar_inicial(self, nombre_base: str, texto_opciones: str) -> int:
        """Inserta la fila para detonar el AUTOINCREMENT; devuelve la PK generada."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO archivos (nombre_original, combinacion_opciones) VALUES (?, ?)",
            (nombre_base, texto_opciones)
        )
        pk_generada = cursor.lastrowid
        cursor.close()
        return pk_generada

    def actualizar_nombre_y_hash(self, pk: int, nombre_con_hash: str, hash_hex: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE archivos SET nombre_original = ?, hash_calculado_hex = ? WHERE id = ?",
            (nombre_con_hash, hash_hex, pk)
        )
        self._conn.commit()
        cursor.close()

    def obtener_nombre_por_id(self, archivo_id: int) -> str | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT nombre_original FROM archivos WHERE id = ?", (archivo_id,))
        resultado = cursor.fetchone()
        cursor.close()
        return resultado[0] if resultado else None

    def eliminar_por_id(self, archivo_id: int) -> None:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM archivos WHERE id = ?", (archivo_id,))
        self._conn.commit()
        cursor.close()

    def buscar_por_combinacion(self, texto_opciones: str) -> list[tuple[int, str, str]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, nombre_original, hash_calculado_hex FROM archivos WHERE combinacion_opciones = ?",
            (texto_opciones,)
        )
        filas = cursor.fetchall()
        cursor.close()
        return filas

    def eliminar_por_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        cursor = self._conn.cursor()
        cursor.executemany("DELETE FROM archivos WHERE id = ?", [(i,) for i in ids])
        self._conn.commit()
        cursor.close()

    def actualizar_combinacion(self, archivo_id: int, nombre_nuevo: str, texto_opciones: str, hash_hex: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE archivos SET nombre_original = ?, combinacion_opciones = ?, hash_calculado_hex = ? WHERE id = ?",
            (nombre_nuevo, texto_opciones, hash_hex, archivo_id)
        )
        self._conn.commit()
        cursor.close()

    def eliminar_por_nombre(self, nombre_archivo: str) -> int:
        """Devuelve cuántas filas se eliminaron."""
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM archivos WHERE nombre_original = ?", (nombre_archivo,))
        eliminados = cursor.rowcount
        self._conn.commit()
        cursor.close()
        return eliminados


class RepositorioOrdenOpciones:
    """INTERFAZ A PROTEGER: único punto de acceso SQL a la tabla `orden_opciones`."""

    def __init__(self, conn):
        self._conn = conn

    def crear_tabla_si_no_existe(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orden_opciones (
                categoria TEXT NOT NULL,
                opcion_id TEXT NOT NULL,
                posicion_y INTEGER NOT NULL,
                PRIMARY KEY (categoria, opcion_id)
            )
        ''')
        cursor.close()

    def contar_filas(self) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orden_opciones")
        total = cursor.fetchone()[0]
        cursor.close()
        return total

    def cargar_seed(self, sql_script: str) -> None:
        self._conn.executescript(sql_script)
        self._conn.commit()

    def obtener_mapa(self) -> dict:
        cursor = self._conn.cursor()
        cursor.execute("SELECT categoria, opcion_id, posicion_y FROM orden_opciones ORDER BY categoria, posicion_y ASC")
        filas = cursor.fetchall()
        cursor.close()

        mapa: dict = {}
        for cat, op_id, pos in filas:
            mapa.setdefault(cat, []).append(op_id)
        return mapa

    def reordenar_categoria(self, categoria: str, lista_opciones: list[str]) -> None:
        cursor = self._conn.cursor()
        cursor.executemany(
            "DELETE FROM orden_opciones WHERE opcion_id = ?",
            [(opcion_id,) for opcion_id in lista_opciones]
        )
        for indice, opcion_id in enumerate(lista_opciones, start=1):
            cursor.execute(
                "INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES (?, ?, ?)",
                (categoria, opcion_id, indice)
            )
        self._conn.commit()
        cursor.close()

    def existe_opcion_id(self, opcion_id: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT 1 FROM orden_opciones WHERE opcion_id = ?", (opcion_id,))
        existe = cursor.fetchone() is not None
        cursor.close()
        return existe

    def obtener_siguiente_posicion(self, categoria: str) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(posicion_y), 0) FROM orden_opciones WHERE categoria = ?", (categoria,))
        siguiente = cursor.fetchone()[0] + 1
        cursor.close()
        return siguiente

    def insertar(self, categoria: str, opcion_id: str, posicion_y: int) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES (?, ?, ?)",
            (categoria, opcion_id, posicion_y)
        )
        self._conn.commit()
        cursor.close()
