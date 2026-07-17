"""Unit tests for the path-containment guard (_resolver_dentro_de_raiz).

CodeQL flags GET /api/explorar and POST /api/subir for py/path-injection since
`ruta`/`ruta_absoluta` are untrusted request data used directly in filesystem
calls (see CLAUDE.md "Security: path containment"). These are pure/mechanical
tests of the containment logic itself, independent of any future business
rules.
"""
import os

import pytest

import document_logic


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setattr(document_logic, "RAIZ_PERMITIDA", str(tmp_path))
    return tmp_path


class TestResolverDentroDeRaiz:
    def test_ruta_absoluta_dentro_de_la_raiz_se_resuelve(self, raiz):
        candidata = str(raiz / "sub" / "archivo.txt")
        assert document_logic._resolver_dentro_de_raiz(candidata) == candidata

    def test_ruta_fuera_de_la_raiz_se_rechaza(self, raiz):
        assert document_logic._resolver_dentro_de_raiz("/etc/passwd") is None

    def test_traversal_con_puntos_dobles_se_rechaza(self, raiz):
        fuera = os.path.join(str(raiz), "..", "..", "etc", "passwd")
        assert document_logic._resolver_dentro_de_raiz(fuera) is None

    def test_ruta_vacia_o_none_se_rechaza(self, raiz):
        assert document_logic._resolver_dentro_de_raiz("") is None
        assert document_logic._resolver_dentro_de_raiz(None) is None

    def test_la_raiz_misma_es_valida(self, raiz):
        assert document_logic._resolver_dentro_de_raiz(str(raiz)) == str(raiz)

    def test_directorio_hermano_con_prefijo_similar_no_cuenta_como_contenido(self, raiz):
        # Un directorio hermano cuyo nombre EMPIEZA con el mismo string que la
        # raíz (ej. raiz=".../x", hermano=".../x2") no debe colar por un
        # chequeo naive de startswith() en vez de os.path.commonpath.
        hermano = str(raiz) + "2"
        os.makedirs(hermano, exist_ok=True)
        try:
            assert document_logic._resolver_dentro_de_raiz(os.path.join(hermano, "archivo.txt")) is None
        finally:
            os.rmdir(hermano)
