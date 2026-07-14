"""
Reconciliación en un solo paso entre storage_database/documents_pool/ y la
tabla `archivos` de catalogo_archivos.db.

Caso de uso: cuando se copia un catalogo_archivos.db de otro proyecto/entorno
dentro de documents_pool/, los archivos físicos que ya estaban en esta carpeta
pueden no estar referenciados por ese nuevo `archivos`, y filas de ese nuevo
`archivos` pueden apuntar a archivos que no existen acá. `make update` corre
este script una sola vez (a diferencia de watcher.py, que solo hace la mitad
del trabajo -DB -> disco- en un loop continuo) para sincronizar ambos sentidos:

1. Borra del disco cualquier archivo dentro de documents_pool/ que no esté
   referenciado por ninguna fila de `archivos` (nombre_original).
2. Borra de `archivos` cualquier fila cuyo nombre_original no exista en disco.

Uso:
    venv/bin/python storage_database/reconciliar_pool.py
    (o `make update`)
"""
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_FOLDER = os.path.join(BASE_DIR, "documents_pool")
DB_PATH = os.path.join(MEDIA_FOLDER, "catalogo_archivos.db")

# Nombres dentro de documents_pool/ que NO son documentos subidos por el
# usuario y por lo tanto nunca deben borrarse aunque no aparezcan en `archivos`.
NOMBRES_RESERVADOS = {
    "catalogo_archivos.db",
    "catalogo_archivos.db-journal",
    "catalogo_archivos.db-wal",
    "catalogo_archivos.db-shm",
    ".gitkeep",
}


def reconciliar():
    if not os.path.exists(DB_PATH):
        print(f"[reconciliar_pool] No se encontró la base de datos en {DB_PATH}.")
        print("[reconciliar_pool] Ejecutá 'make run' al menos una vez para crearla, luego reintentá.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre_original FROM archivos")
    filas = cursor.fetchall()
    nombres_en_db = {nombre for _id, nombre in filas}

    # 1. Archivos en disco que ya no están referenciados por ninguna fila
    archivos_en_disco = set(os.listdir(MEDIA_FOLDER)) - NOMBRES_RESERVADOS
    huerfanos_en_disco = archivos_en_disco - nombres_en_db

    borrados_disco = 0
    for nombre in huerfanos_en_disco:
        ruta = os.path.join(MEDIA_FOLDER, nombre)
        if os.path.isfile(ruta):
            os.remove(ruta)
            borrados_disco += 1
            print(f"[reconciliar_pool] '{nombre}' no está referenciado en la base de datos -> borrado de disco.")

    # 2. Filas de `archivos` cuyo archivo físico no existe en disco
    ids_huerfanos_db = [
        archivo_id for archivo_id, nombre in filas
        if not os.path.isfile(os.path.join(MEDIA_FOLDER, nombre))
    ]

    if ids_huerfanos_db:
        cursor.executemany("DELETE FROM archivos WHERE id = ?", [(i,) for i in ids_huerfanos_db])
        conn.commit()
        for archivo_id in ids_huerfanos_db:
            print(f"[reconciliar_pool] Fila id={archivo_id} no tiene archivo físico -> borrada de la base de datos.")

    conn.close()

    print(
        f"[reconciliar_pool] Listo: {borrados_disco} archivo(s) borrado(s) de disco, "
        f"{len(ids_huerfanos_db)} fila(s) borrada(s) de la base de datos."
    )


if __name__ == "__main__":
    reconciliar()
