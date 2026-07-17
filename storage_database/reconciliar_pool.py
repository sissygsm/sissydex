"""
Reconciliación en un solo paso entre lo que hay realmente en disco y la tabla
`archivos` de catalogo_archivos.db.

Caso de uso: cuando se copia un catalogo_archivos.db de otro proyecto/entorno,
sus filas pueden apuntar a rutas absolutas que no existen en esta máquina.
`make update` corre este script una sola vez (a diferencia de watcher.py, que
hace lo mismo en un loop continuo) para borrar esas filas huérfanas.

Los archivos tagueados NUNCA se copian a documents_pool/ (ver
AlmacenamientoReferenciado en backend/services/storage.py): `nombre_original`
guarda la ruta absoluta original de cada archivo, dondequiera que esté en
disco, así que no hay ningún "archivo huérfano dentro de documents_pool/" que
reconciliar en sentido inverso -esa carpeta solo aloja la base de datos-.

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


def reconciliar():
    if not os.path.exists(DB_PATH):
        print(f"[reconciliar_pool] No se encontró la base de datos en {DB_PATH}.")
        print("[reconciliar_pool] Ejecutá 'make run' al menos una vez para crearla, luego reintentá.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre_original FROM archivos")
    filas = cursor.fetchall()

    ids_huerfanos = [archivo_id for archivo_id, ruta_absoluta in filas if not os.path.isfile(ruta_absoluta)]

    if ids_huerfanos:
        cursor.executemany("DELETE FROM archivos WHERE id = ?", [(i,) for i in ids_huerfanos])
        conn.commit()
        for archivo_id in ids_huerfanos:
            print(
                f"[reconciliar_pool] Fila id={archivo_id} no tiene archivo físico en su ruta "
                "original -> borrada de la base de datos."
            )

    conn.close()

    print(f"[reconciliar_pool] Listo: {len(ids_huerfanos)} fila(s) borrada(s) de la base de datos.")


if __name__ == "__main__":
    reconciliar()
