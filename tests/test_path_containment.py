"""Unit tests for the path-containment guard.

CodeQL flags GET /api/explorar and POST /api/subir for py/path-injection
since `ruta`/`ruta_absoluta` are untrusted request data used directly in
filesystem calls. The containment check is inlined at each site that
actually touches disk (LogicaNegocioArchivos.explorar_directorio and
AlmacenamientoReferenciado's methods) rather than living in one shared
helper, since CodeQL doesn't treat a sanitizer applied inside a helper
function as a barrier for the caller's return value (see CLAUDE.md
"Security: path containment"). These are pure/mechanical tests of that
containment logic, independent of any future business rules.
"""
import os

import pytest

import document_logic
from storage import AlmacenamientoReferenciado


@pytest.fixture
def raiz(tmp_path):
    return os.path.realpath(str(tmp_path))


@pytest.fixture
def negocio(tmp_path, monkeypatch):
    monkeypatch.setattr(document_logic, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(document_logic, "RAIZ_PERMITIDA", os.path.realpath(str(tmp_path)))
    instancia = document_logic.LogicaNegocioArchivos()
    yield instancia
    instancia.conn.close()


class TestAlmacenamientoReferenciadoContencion:
    def test_renombrar_dentro_de_la_raiz_funciona(self, raiz):
        origen = os.path.join(raiz, "doc.txt")
        with open(origen, "w") as f:
            f.write("contenido")

        almacenamiento = AlmacenamientoReferenciado(raiz)
        ruta_nueva = almacenamiento.renombrar(origen, "abc123doc.txt")

        assert ruta_nueva == os.path.join(raiz, "abc123doc.txt")
        assert os.path.exists(ruta_nueva)

    def test_renombrar_fuera_de_la_raiz_se_rechaza(self, raiz):
        almacenamiento = AlmacenamientoReferenciado(raiz)
        with pytest.raises(ValueError):
            almacenamiento.renombrar("/etc/passwd", "hackeado")

    def test_renombrar_con_traversal_se_rechaza(self, raiz):
        almacenamiento = AlmacenamientoReferenciado(raiz)
        fuera_por_traversal = os.path.join(raiz, "..", "..", "etc", "passwd")
        with pytest.raises(ValueError):
            almacenamiento.renombrar(fuera_por_traversal, "hackeado")

    def test_renombrar_con_destino_que_escapa_la_raiz_se_rechaza(self, raiz):
        # El origen es válido, pero nombre_nuevo intenta escapar la raíz vía
        # "..": el destino construido (directorio + nombre_nuevo) debe
        # validarse por separado del origen.
        origen = os.path.join(raiz, "doc.txt")
        with open(origen, "w") as f:
            f.write("contenido")

        almacenamiento = AlmacenamientoReferenciado(raiz)
        with pytest.raises(ValueError):
            almacenamiento.renombrar(origen, "../../etc/cron.d/evil")

        # El archivo original no debe haberse movido/renombrado.
        assert os.path.exists(origen)

    def test_existe_fuera_de_la_raiz_devuelve_false_aunque_el_archivo_exista(self, raiz):
        almacenamiento = AlmacenamientoReferenciado(raiz)
        assert almacenamiento.existe("/etc/passwd") is False

    def test_eliminar_fuera_de_la_raiz_no_hace_nada(self, raiz, tmp_path):
        afuera = tmp_path.parent / "no_deberia_borrarse.txt"
        afuera.write_text("contenido")
        try:
            almacenamiento = AlmacenamientoReferenciado(raiz)
            almacenamiento.eliminar(str(afuera))
            assert afuera.exists()
        finally:
            afuera.unlink(missing_ok=True)

    def test_directorio_hermano_con_prefijo_similar_no_cuenta_como_contenido(self, raiz):
        # Un directorio hermano cuyo nombre EMPIEZA con el mismo string que la
        # raíz (ej. raiz=".../x", hermano=".../x2") no debe colar por un
        # chequeo naive de startswith() sin el separador de por medio.
        hermano = raiz + "2"
        os.makedirs(hermano, exist_ok=True)
        try:
            almacenamiento = AlmacenamientoReferenciado(raiz)
            assert almacenamiento.existe(os.path.join(hermano, "archivo.txt")) is False
        finally:
            os.rmdir(hermano)


class TestExplorarDirectorioContencion:
    def test_lista_una_carpeta_dentro_de_la_raiz(self, negocio, raiz):
        os.makedirs(os.path.join(raiz, "sub"))
        with open(os.path.join(raiz, "sub", "archivo.txt"), "w") as f:
            f.write("x")

        resultado = negocio.explorar_directorio(os.path.join(raiz, "sub"))

        assert resultado["ruta_actual"] == os.path.join(raiz, "sub")
        assert resultado["entradas"] == [{"nombre": "archivo.txt", "es_carpeta": False}]

    def test_ruta_fuera_de_la_raiz_cae_a_la_raiz(self, negocio, raiz):
        resultado = negocio.explorar_directorio("/etc")
        assert resultado["ruta_actual"] == raiz

    def test_traversal_con_puntos_dobles_cae_a_la_raiz(self, negocio, raiz):
        fuera = os.path.join(raiz, "..", "..", "etc")
        resultado = negocio.explorar_directorio(fuera)
        assert resultado["ruta_actual"] == raiz

    def test_subir_un_nivel_desde_la_raiz_misma_queda_deshabilitado(self, negocio, raiz):
        resultado = negocio.explorar_directorio(raiz)
        assert resultado["ruta_padre"] is None
