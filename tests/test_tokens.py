"""Unit tests for AlmacenTokens (see backend/services/tokens.py and
CLAUDE.md "Security: path containment" for the indirect-reference-map
rationale). Pure/mechanical, independent of any business rule.
"""
from tokens import AlmacenTokens


class TestAlmacenTokens:
    def test_mintear_y_resolver_hacen_roundtrip(self):
        almacen = AlmacenTokens()
        token = almacen.mintear("/home/user/documento.txt")
        assert almacen.resolver(token) == "/home/user/documento.txt"

    def test_token_desconocido_resuelve_a_none(self):
        almacen = AlmacenTokens()
        assert almacen.resolver("token-que-no-existe") is None

    def test_descartar_invalida_el_token(self):
        almacen = AlmacenTokens()
        token = almacen.mintear("valor")
        almacen.descartar(token)
        assert almacen.resolver(token) is None

    def test_descartar_token_desconocido_no_falla(self):
        almacen = AlmacenTokens()
        almacen.descartar("token-que-no-existe")  # no debe lanzar

    def test_tokens_son_distintos_para_el_mismo_valor(self):
        almacen = AlmacenTokens()
        token_a = almacen.mintear("mismo-valor")
        token_b = almacen.mintear("mismo-valor")
        assert token_a != token_b

    def test_supera_la_capacidad_descarta_la_entrada_mas_vieja(self):
        almacen = AlmacenTokens(capacidad_maxima=3)
        tokens = [almacen.mintear(f"valor-{i}") for i in range(3)]

        almacen.mintear("valor-nuevo")

        assert almacen.resolver(tokens[0]) is None
        for token in tokens[1:]:
            assert almacen.resolver(token) is not None
