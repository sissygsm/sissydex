"""
Convierte storage_database/seeds/orden_opciones.csv en un script SQL
(orden_opciones_seed.sql) que reemplaza el contenido de la tabla orden_opciones.

Uso:
    python storage_database/seeds/generate_orden_opciones_sql.py

Cuando actualices el CSV, vuelve a correr este script para regenerar el .sql.
"""
import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "orden_opciones.csv")
SQL_PATH = os.path.join(BASE_DIR, "orden_opciones_seed.sql")


def generar():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        filas = [fila for fila in csv.DictReader(f) if fila.get("categoria")]

    lineas = [
        "BEGIN TRANSACTION;",
        "",
        "CREATE TABLE IF NOT EXISTS orden_opciones (",
        "    categoria TEXT NOT NULL,",
        "    opcion_id TEXT NOT NULL,",
        "    posicion_y INTEGER NOT NULL,",
        "    PRIMARY KEY (categoria, opcion_id)",
        ");",
        "",
        "DELETE FROM orden_opciones;",
        "",
    ]

    for fila in filas:
        categoria = fila["categoria"].replace("'", "''")
        opcion_id = fila["opcion_id"].replace("'", "''")
        posicion_y = int(fila["posicion_y"])
        lineas.append(
            f"INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) "
            f"VALUES ('{categoria}', '{opcion_id}', {posicion_y});"
        )

    lineas += ["", "COMMIT;", ""]

    with open(SQL_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    print(f"OK: {len(filas)} filas -> {SQL_PATH}")


if __name__ == "__main__":
    generar()
