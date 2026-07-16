"""
Strategy (GoF) para el contenido físico de un archivo. Antes de este módulo,
LogicaNegocioArchivos llamaba directo a os.path.join/.save()/os.rename()/
os.remove() contra MEDIA_FOLDER — acoplando la lógica de negocio al disco
local. Migrar a S3 (o cualquier otro backend) hoy exige reescribir esos
métodos; con esta interfaz de por medio, es escribir una clase nueva.
"""
import os
from abc import ABC, abstractmethod
from typing import Any


class EstrategiaAlmacenamiento(ABC):
    """
    INTERFAZ A PROTEGER: el único contrato que LogicaNegocioArchivos conoce
    para tocar el contenido físico de un archivo.

    `renombrar` es un método propio (no "leer + guardar + eliminar") a
    propósito: en disco local es un os.rename() atómico y barato; en S3 no
    existe un rename nativo, hay que hacer copy_object + delete_object. Esa
    asimetría entre backends es justamente lo que este método existe para
    ocultarle a la capa de negocio.
    """

    @abstractmethod
    def guardar(self, nombre_base: str, archivo_flask) -> str:
        """Persiste un archivo recién subido (objeto FileStorage de Flask/Werkzeug) y devuelve su identificador."""
        ...

    @abstractmethod
    def renombrar(self, identificador_actual: str, nombre_nuevo: str) -> str:
        """Renombra/mueve contenido ya guardado; devuelve el nuevo identificador. No falla si el origen ya no existe."""
        ...

    @abstractmethod
    def eliminar(self, identificador: str) -> None:
        """No falla si el identificador ya no existe (ver eliminar_archivo/idempotencia)."""
        ...

    @abstractmethod
    def existe(self, identificador: str) -> bool: ...


class AlmacenamientoLocal(EstrategiaAlmacenamiento):
    """
    Concrete Strategy: filesystem local. Mismo comportamiento exacto que el
    código anterior a este refactor (mismos os.rename/os.remove/os.path.exists,
    solo movidos detrás de esta interfaz).
    """

    def __init__(self, directorio_base: str):
        self._base = directorio_base
        os.makedirs(self._base, exist_ok=True)

    def guardar(self, nombre_base: str, archivo_flask) -> str:
        ruta = os.path.join(self._base, nombre_base)
        archivo_flask.save(ruta)
        return nombre_base

    def renombrar(self, identificador_actual: str, nombre_nuevo: str) -> str:
        ruta_actual = os.path.join(self._base, identificador_actual)
        ruta_nueva = os.path.join(self._base, nombre_nuevo)
        if os.path.exists(ruta_actual):
            os.rename(ruta_actual, ruta_nueva)
        return nombre_nuevo

    def eliminar(self, identificador: str) -> None:
        ruta = os.path.join(self._base, identificador)
        if os.path.exists(ruta):
            os.remove(ruta)

    def existe(self, identificador: str) -> bool:
        return os.path.exists(os.path.join(self._base, identificador))


class AlmacenamientoS3(EstrategiaAlmacenamiento):
    """
    Concrete Strategy de referencia para cuando de verdad haga falta migrar a
    S3 (o compatible: MinIO, R2...). NO está instanciada en ningún lado del
    proyecto todavía -no hay credenciales/config de S3 hoy-, así que este
    módulo no importa boto3 a nivel de módulo: el cliente se inyecta por
    constructor (Dependency Inversion), y no hace falta tener boto3 instalado
    para correr el resto de la app o sus tests.
    """

    def __init__(self, cliente_s3: Any, bucket: str):
        self._s3 = cliente_s3
        self._bucket = bucket

    def guardar(self, nombre_base: str, archivo_flask) -> str:
        self._s3.upload_fileobj(archivo_flask.stream, self._bucket, nombre_base)
        return nombre_base

    def renombrar(self, identificador_actual: str, nombre_nuevo: str) -> str:
        if self.existe(identificador_actual):
            self._s3.copy_object(
                Bucket=self._bucket,
                CopySource={"Bucket": self._bucket, "Key": identificador_actual},
                Key=nombre_nuevo,
            )
            self._s3.delete_object(Bucket=self._bucket, Key=identificador_actual)
        return nombre_nuevo

    def eliminar(self, identificador: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=identificador)

    def existe(self, identificador: str) -> bool:
        # boto3 siempre trae botocore; import perezoso igual, ver docstring de clase.
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self._bucket, Key=identificador)
            return True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "404":
                return False
            raise
