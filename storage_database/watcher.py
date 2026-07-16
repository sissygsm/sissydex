"""
Proceso standalone que observa storage_database/documents_pool/ y mantiene la
tabla `archivos` sincronizada con lo que realmente existe en disco.

Si un archivo se elimina manualmente (fuera de la app, ej. `rm` o un gestor de
archivos), su registro correspondiente en catalogo_archivos.db queda huérfano
-la app no se entera-. Este script revisa periódicamente cada registro y
borra los que ya no tienen su archivo físico en documents_pool/.

Uso:
    venv/bin/python storage_database/watcher.py
"""
import functools
import os
import sqlite3
import sys
import time

# stdout se bufferea por bloques (no por línea) cuando no es una terminal -p.ej.
# al redirigir a un archivo de log con `make watch > log.txt`-, así que sin esto
# los mensajes tardarían en aparecer. Forzamos flush en cada print.
print = functools.partial(print, flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_FOLDER = os.path.join(BASE_DIR, "documents_pool")
DB_PATH = os.path.join(MEDIA_FOLDER, "catalogo_archivos.db")

POLL_INTERVAL_SECONDS = 2


def sincronizar_una_vez(conn):
    """Elimina de `archivos` cualquier registro cuyo archivo físico ya no exista."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre_original FROM archivos")
    registros = cursor.fetchall()

    eliminados = 0
    for archivo_id, nombre_original in registros:
        ruta_fisica = os.path.join(MEDIA_FOLDER, nombre_original)
        if not os.path.exists(ruta_fisica):
            cursor.execute("DELETE FROM archivos WHERE id = ?", (archivo_id,))
            eliminados += 1
            print(f"[watcher] '{nombre_original}' (id={archivo_id}) ya no está en disco "
                  "-> registro eliminado de la base de datos.")

    if eliminados:
        conn.commit()

    return eliminados


def main():
    if not os.path.exists(DB_PATH):
        print(f"[watcher] No se encontró la base de datos en {DB_PATH}.")
        print("[watcher] Ejecutá 'make run' al menos una vez para crearla, luego reintentá.")
        sys.exit(1)

    print(f"[watcher] Observando {MEDIA_FOLDER} cada {POLL_INTERVAL_SECONDS}s (Ctrl+C para detener)...")
    conn = sqlite3.connect(DB_PATH)
    try:
        while True:
            sincronizar_una_vez(conn)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n[watcher] Detenido.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
