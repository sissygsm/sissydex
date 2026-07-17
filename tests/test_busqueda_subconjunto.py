"""Tests for the 3ra Sección "Resultados de Búsqueda" (botón Buscar): a
subset search, distinct from listar_archivos_por_combinacion's EXACT-match
filter used by the 1ra Sección. A file matches if its identity options
(combinacion_opciones) contain, as a subset, EVERY currently selected
option -it may have extra options beyond the selection, but nothing
selected can be missing from it.
"""
import os

import pytest

import document_logic


@pytest.fixture
def negocio(tmp_path, monkeypatch):
    monkeypatch.setattr(document_logic, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(document_logic, "RAIZ_PERMITIDA", os.path.realpath(str(tmp_path)))
    instancia = document_logic.LogicaNegocioArchivos()
    yield instancia
    instancia.conn.close()


@pytest.fixture
def client(negocio, monkeypatch):
    monkeypatch.setattr(document_logic, "negocio", negocio)
    document_logic.app.config.update(TESTING=True)
    return document_logic.app.test_client()


def _crear_archivo(tmp_path, nombre, contenido=b"contenido"):
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    return str(ruta)


class TestBuscarArchivosPorSubconjunto:
    def test_seleccion_vacia_no_devuelve_nada(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        negocio.procesar_y_guardar_archivo(ruta, ["x", "y", "z"])

        assert negocio.buscar_archivos_por_subconjunto([]) == []

    def test_archivo_con_todas_las_opciones_seleccionadas_ademas_de_otras_aparece(self, negocio, tmp_path):
        # El archivo A del ejemplo de la aclaración: tageado con {x, y, z},
        # buscando por un subconjunto {x} debe aparecer.
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, _ = negocio.procesar_y_guardar_archivo(ruta, ["x", "y", "z"])

        resultado = negocio.buscar_archivos_por_subconjunto(["x"])

        assert [f["id"] for f in resultado] == [pk]

    def test_archivo_al_que_le_falta_una_opcion_seleccionada_no_aparece(self, negocio, tmp_path):
        # Selección {x, w}: el archivo solo tiene {x, y, z} -le falta "w",
        # así que NO debe aparecer aunque comparta "x" (subconjunto, no OR).
        ruta = _crear_archivo(tmp_path, "doc.txt")
        negocio.procesar_y_guardar_archivo(ruta, ["x", "y", "z"])

        assert negocio.buscar_archivos_por_subconjunto(["x", "w"]) == []

    def test_combinacion_exacta_tambien_aparece(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, _ = negocio.procesar_y_guardar_archivo(ruta, ["x", "y"])

        resultado = negocio.buscar_archivos_por_subconjunto(["x", "y"])

        assert [f["id"] for f in resultado] == [pk]

    def test_no_confunde_prefijos_de_opciones_similares(self, negocio, tmp_path):
        # "a" no debe matchear como subconjunto de un archivo tageado solo
        # con "aa" (falso positivo por coincidencia parcial de substring).
        ruta = _crear_archivo(tmp_path, "doc.txt")
        negocio.procesar_y_guardar_archivo(ruta, ["aa"])

        assert negocio.buscar_archivos_por_subconjunto(["a"]) == []

    def test_autosana_archivos_huerfanos_borrados_fuera_de_la_app(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, hash_hex = negocio.procesar_y_guardar_archivo(ruta, ["x"])
        os.remove(tmp_path / f"{hash_hex}doc.txt")

        resultado = negocio.buscar_archivos_por_subconjunto(["x"])

        assert resultado == []
        assert negocio.obtener_ruta_por_id(pk) is None


class TestRutaBuscar:
    def test_post_api_buscar_devuelve_archivos_que_cumplen_el_subconjunto(self, client, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, _ = negocio.procesar_y_guardar_archivo(ruta, ["x", "y", "z"])

        resp = client.post("/api/buscar", json={"opciones": ["x"]})

        assert resp.status_code == 200
        data = resp.get_json()
        assert [f["id"] for f in data["archivos"]] == [pk]

    def test_post_api_buscar_con_opcion_faltante_no_lo_incluye(self, client, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        negocio.procesar_y_guardar_archivo(ruta, ["x", "y", "z"])

        resp = client.post("/api/buscar", json={"opciones": ["x", "w"]})

        assert resp.get_json()["archivos"] == []

    def test_post_api_buscar_sin_opciones_devuelve_lista_vacia(self, client):
        resp = client.post("/api/buscar", json={"opciones": []})

        assert resp.status_code == 200
        assert resp.get_json()["archivos"] == []
