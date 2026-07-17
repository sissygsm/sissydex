"""End-to-end tests for the token-based GET /api/explorar and POST /api/subir
flow (see backend/services/tokens.py and CLAUDE.md "Security: path
containment"). These exercise the routes through Flask's test_client, not
just the business-logic methods directly, since the token indirection is
partly implemented in the route handlers themselves.
"""
import os

import pytest

import document_logic


@pytest.fixture
def negocio(tmp_path, monkeypatch):
    # Mismo patrón que tests/test_path_containment.py, más monkeypatchear el
    # singleton `negocio` a nivel de módulo: las rutas lo resuelven como
    # global en tiempo de llamada, así que sin esto seguirían usando la
    # instancia real del proyecto.
    raiz = os.path.realpath(str(tmp_path))
    monkeypatch.setattr(document_logic, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(document_logic, "RAIZ_PERMITIDA", raiz)
    instancia = document_logic.LogicaNegocioArchivos()
    monkeypatch.setattr(document_logic, "negocio", instancia)
    yield instancia
    instancia.conn.close()


@pytest.fixture
def client(negocio):
    document_logic.app.config.update(TESTING=True)
    return document_logic.app.test_client()


def _crear_archivo(tmp_path, nombre="doc.txt", contenido=b"contenido"):
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    return ruta


class TestExplorarConTokens:
    def test_explorar_raiz_devuelve_entradas_con_token(self, client, tmp_path):
        _crear_archivo(tmp_path, "doc.txt")

        resp = client.get("/api/explorar")
        assert resp.status_code == 200

        data = resp.get_json()
        entrada = next(e for e in data["entradas"] if e["nombre"] == "doc.txt")
        assert entrada["token"]

    def test_navegar_con_token_de_subcarpeta_lista_su_contenido(self, client, tmp_path):
        os.makedirs(tmp_path / "sub")
        _crear_archivo(tmp_path / "sub", "adentro.txt")

        raiz_resp = client.get("/api/explorar").get_json()
        token_sub = next(e["token"] for e in raiz_resp["entradas"] if e["nombre"] == "sub")

        resp = client.get(f"/api/explorar?token={token_sub}")
        data = resp.get_json()

        assert [e["nombre"] for e in data["entradas"]] == ["adentro.txt"]

    def test_explorar_con_token_desconocido_cae_a_la_raiz(self, client, tmp_path):
        raiz = os.path.realpath(str(tmp_path))

        resp = client.get("/api/explorar?token=token-inventado")

        assert resp.get_json()["ruta_actual_texto"] == raiz


class TestSubirConTokens:
    def test_subir_con_token_de_archivo_tagea_correctamente(self, client, negocio, tmp_path):
        archivo = _crear_archivo(tmp_path, "informe.txt")
        token = negocio._tokens_archivos.mintear(str(archivo))

        resp = client.post("/api/subir", json={"token": token, "opciones": ["a"]})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert not archivo.exists()  # renombrado in place con el hash antepuesto
        assert negocio.obtener_ruta_por_id(data["pk"]) is not None

    def test_subir_con_token_ya_usado_se_rechaza_sin_duplicar_fila(self, client, negocio, tmp_path):
        archivo = _crear_archivo(tmp_path, "informe.txt")
        token = negocio._tokens_archivos.mintear(str(archivo))

        primero = client.post("/api/subir", json={"token": token, "opciones": ["a"]})
        assert primero.status_code == 200

        segundo = client.post("/api/subir", json={"token": token, "opciones": ["a"]})

        assert segundo.status_code == 400
        assert segundo.get_json()["success"] is False

    def test_subir_con_token_desconocido_se_rechaza(self, client):
        resp = client.post("/api/subir", json={"token": "token-inventado", "opciones": ["a"]})

        assert resp.status_code == 400
        assert resp.get_json()["success"] is False
