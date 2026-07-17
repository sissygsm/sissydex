"""Unit tests for the PK^options hash scheme (see CLAUDE.md "Hash scheme").

These target pure/mechanical invariants, not business rules, so they're safe
to write without a user story: the hashing math and file-naming convention
won't change even if the option codes/categories do.
"""
import os

import pytest

import document_logic


@pytest.fixture
def negocio(tmp_path, monkeypatch):
    # Redirige la BD y la raíz permitida a tmp_path para no tocar el storage
    # real del proyecto -AlmacenamientoReferenciado rechaza cualquier ruta
    # fuera de RAIZ_PERMITIDA, así que los archivos de prueba deben quedar
    # contenidos ahí-.
    monkeypatch.setattr(document_logic, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(document_logic, "RAIZ_PERMITIDA", os.path.realpath(str(tmp_path)))
    instancia = document_logic.LogicaNegocioArchivos()
    yield instancia
    instancia.conn.close()


def _crear_archivo(tmp_path, nombre="prueba.txt", contenido=b"contenido"):
    """Crea un archivo real en tmp_path (el archivo NUNCA se copia: se referencia
    por ruta absoluta, ver AlmacenamientoReferenciado) y devuelve su ruta."""
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    return str(ruta)


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
    def test_hash_final_es_pk_xor_hash_opciones(self, negocio, tmp_path):
        # Valor esperado precalculado de forma independiente (xxhash.xxh32("b")
        # = 2718739903, un número impar) en vez de re-derivarlo con la misma
        # fórmula que el código de producción: a^b y a+b coinciden en la
        # práctica cuando a y b no comparten bits en 1 (p. ej. con "a", cuyo
        # hash es par, PK=1 ^ hash == PK=1 + hash), así que ese caso no
        # detectaría una regresión de "^" a "+". "b" fuerza el solapamiento de
        # bits con PK=1 para que XOR y suma den resultados distintos de verdad.
        ruta = _crear_archivo(tmp_path)
        pk, hash_hex = negocio.procesar_y_guardar_archivo(ruta, ["b"])

        assert pk == 1
        assert hash_hex == "a20cadbe"

    def test_archivo_fisico_queda_renombrado_in_place_con_el_hash_como_prefijo(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, hash_hex = negocio.procesar_y_guardar_archivo(ruta, ["a"])

        assert (tmp_path / f"{hash_hex}doc.txt").exists()
        assert not (tmp_path / "doc.txt").exists()


class TestEliminarArchivo:
    def test_quita_el_prefijo_de_hash_pero_no_borra_el_archivo_de_disco(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, hash_hex = negocio.procesar_y_guardar_archivo(ruta, ["a"])

        resultado = negocio.eliminar_archivo(pk)

        assert resultado == str(tmp_path / "doc.txt")
        assert (tmp_path / "doc.txt").exists()
        assert not (tmp_path / f"{hash_hex}doc.txt").exists()


class TestCambiarOpcionesArchivo:
    def test_renombra_in_place_con_el_hash_de_la_nueva_combinacion(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, hash_original = negocio.procesar_y_guardar_archivo(ruta, ["a"])

        ruta_nueva = negocio.cambiar_opciones_archivo(pk, ["b"])

        hash_nuevo = f"{(pk ^ negocio.calcular_hash_opciones(['b'])):08x}"
        assert hash_nuevo != hash_original
        assert ruta_nueva == str(tmp_path / f"{hash_nuevo}doc.txt")
        assert (tmp_path / f"{hash_nuevo}doc.txt").exists()
        assert not (tmp_path / f"{hash_original}doc.txt").exists()

    def test_actualiza_la_ruta_en_la_base_de_datos(self, negocio, tmp_path):
        ruta = _crear_archivo(tmp_path, "doc.txt")
        pk, _ = negocio.procesar_y_guardar_archivo(ruta, ["a"])

        ruta_nueva = negocio.cambiar_opciones_archivo(pk, ["b"])

        assert negocio.obtener_ruta_por_id(pk) == ruta_nueva
