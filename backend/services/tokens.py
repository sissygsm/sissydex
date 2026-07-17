"""
Indirección de tokens opacos para evitar que una ruta de filesystem cruda del
request llegue a tocar disco (CWE-22 / CodeQL py/path-injection). En vez de
que el cliente mande/reciba rutas absolutas, recibe un token que el propio
servidor generó al enumerar el filesystem (ver explorar_directorio en
document_logic.py): el valor detrás de un token nunca se derivó del token en
sí, así que no hay un flujo de datos real entre "el token llega en este
request" y "la ruta que termina tocando disco" -son dos cosas que quedaron
en el mismo diccionario por casualidad, no por dependencia de datos-. Es el
patrón "indirect reference map" recomendado por OWASP para path traversal.

No hay expiración por tiempo -sería sobreingeniería para una herramienta de
un solo usuario local-: alcanza con un tope de tamaño (FIFO, se descarta la
entrada más vieja) porque cada listado de carpeta vuelve a emitir tokens
frescos de cualquier forma.
"""
import secrets
from collections import OrderedDict


class AlmacenTokens:
    """Mapea tokens opacos (secrets.token_urlsafe) a valores arbitrarios."""

    def __init__(self, capacidad_maxima: int = 512):
        self._capacidad_maxima = capacidad_maxima
        self._mapa: "OrderedDict[str, object]" = OrderedDict()

    def mintear(self, valor: object) -> str:
        token = secrets.token_urlsafe(16)
        self._mapa[token] = valor
        if len(self._mapa) > self._capacidad_maxima:
            self._mapa.popitem(last=False)
        return token

    def resolver(self, token: str):
        return self._mapa.get(token)

    def descartar(self, token: str) -> None:
        self._mapa.pop(token, None)
