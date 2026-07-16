"""Unit tests for the PK^options hash scheme (see CLAUDE.md "Hash scheme").

These target pure/mechanical invariants, not business rules, so they're safe
to write without a user story: the hashing math and file-naming convention
won't change even if the option codes/categories do.
"""
import io

import pytest
from werkzeug.datastructures import FileStorage

import document_logic


@pytest.fixture
def negocio(tmp_path, monkeypatch):
    # Redirige DB y carpeta de medios a tmp_path para no tocar el storage real del proyecto.
    monkeypatch.setattr(document_logic, "MEDIA_FOLDER", str(tmp_path))
    monkeypatch.setattr(document_logic, "DB_PATH", str(tmp_path / "test.db"))
    instancia = document_logic.LogicaNegocioArchivos()
    yield instancia
    instancia.conn.close()


def _archivo(nombre="prueba.txt", contenido=b"contenido"):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre)


class TestCalcularHashOpciones:
    def test_es_determinista(self, negocio):
        assert negocio.calcular_hash_opciones(["a", "c"]) == negocio.calcular_hash_opciones(["a", "c"])

    def test_no_depende_del_orden_de_seleccion(self, negocio):
        # XOR es conmutativo: el orden en que el usuario tildó las opciones no debe alterar el hash.
        assert negocio.calcular_hash_opciones(["a", "c", "o"]) == negocio.calcular_hash_opciones(["o", "a", "c"])

    def test_combinaciones_distintas_dan_hashes_distintos(self, negocio):
        assert negocio.calcular_hash_opciones(["a"]) != negocio.calcular_hash_opciones(["b"])

    def test_lista_vacia_da_hash_cero(self, negocio):
        assert negocio.calcular_hash_opciones([]) == 0


class TestSepararPrefijoHash:
    def test_quita_prefijo_hex_de_8_caracteres(self, negocio):
        assert negocio._separar_prefijo_hash("deadbeeffeele.txt") == "feele.txt"

    def test_nombre_sin_prefijo_hex_queda_igual(self, negocio):
        assert negocio._separar_prefijo_hash("feele.txt") == "feele.txt"

    def test_nombre_mas_corto_que_8_queda_igual(self, negocio):
        assert negocio._separar_prefijo_hash("abc.txt") == "abc.txt"


class TestProcesarYGuardarArchivo:
    def test_hash_final_es_pk_xor_hash_opciones(self, negocio):
        # Valor esperado precalculado de forma independiente (xxhash.xxh32("b")
        # = 2718739903, un número impar) en vez de re-derivarlo con la misma
        # fórmula que el código de producción: a^b y a+b coinciden en la
        # práctica cuando a y b no comparten bits en 1 (p. ej. con "a", cuyo
        # hash es par, PK=1 ^ hash == PK=1 + hash), así que ese caso no
        # detectaría una regresión de "^" a "+". "b" fuerza el solapamiento de
        # bits con PK=1 para que XOR y suma den resultados distintos de verdad.
        pk, hash_hex = negocio.procesar_y_guardar_archivo(_archivo(), ["b"])

        assert pk == 1
        assert hash_hex == "a20cadbe"

    def test_archivo_fisico_queda_renombrado_con_el_hash_como_prefijo(self, negocio, tmp_path):
        pk, hash_hex = negocio.procesar_y_guardar_archivo(_archivo("doc.txt"), ["a"])

        assert (tmp_path / f"{hash_hex}doc.txt").exists()
        assert not (tmp_path / "doc.txt").exists()
