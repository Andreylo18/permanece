"""Tipos de documento de identidad usados en Colombia (los mismos del SIMAT).

Reglas de edad (Decreto 1260 de 1970 y Ley 962 de 2005, art. 18 / Registraduría):
  - Registro civil de nacimiento (NUIP): menores de 7 años.
  - Tarjeta de identidad: de 7 a 17 años.
  - Cédula de ciudadanía: desde los 18 años.
El NUIP que asigna la Registraduría se conserva de por vida: el número del
registro civil pasa a la tarjeta de identidad y luego a la cédula.
"""
import re
from datetime import date

# código -> (nombre, regla del número, mensaje de error)
TIPOS_DOCUMENTO = {
    "RC": ("Registro civil de nacimiento", r"\d{10,11}", "El NUIP del registro civil tiene 10 u 11 dígitos."),
    "TI": ("Tarjeta de identidad", r"\d{10,11}", "La tarjeta de identidad tiene 10 u 11 dígitos."),
    "CC": ("Cédula de ciudadanía", r"\d{6,10}", "La cédula de ciudadanía tiene entre 6 y 10 dígitos."),
    "CE": ("Cédula de extranjería", r"\d{3,7}", "La cédula de extranjería tiene hasta 7 dígitos."),
    "PPT": ("Permiso por protección temporal", r"\d{6,8}", "El PPT tiene entre 6 y 8 dígitos."),
    "PEP": ("Permiso especial de permanencia", r"\d{15}", "El PEP tiene 15 dígitos."),
    "PA": ("Pasaporte", r"[A-Z0-9]{5,12}", "El pasaporte tiene entre 5 y 12 letras o números."),
    "NES": ("Número establecido por la Secretaría (NES)", r"[A-Z0-9]{5,15}",
            "El NES tiene entre 5 y 15 letras o números."),
}
OPCIONES_DOCUMENTO = [(k, f"{k} · {v[0]}") for k, v in TIPOS_DOCUMENTO.items()]
NUMERICOS = {"RC", "TI", "CC", "CE", "PPT", "PEP"}


def normalizar(numero):
    """Quita puntos, espacios y guiones: '1.012.345.678' -> '1012345678'."""
    return re.sub(r"[\s.\-,]", "", (numero or "")).upper()


def edad(fecha_nacimiento, hoy=None):
    hoy = hoy or date.today()
    return hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))


def validar(tipo, numero, fecha_nacimiento=None):
    """Devuelve un mensaje de error, o None si el documento es válido."""
    if tipo not in TIPOS_DOCUMENTO:
        return "Elige un tipo de documento válido."
    _, patron, mensaje = TIPOS_DOCUMENTO[tipo]
    numero = normalizar(numero)
    if not re.fullmatch(patron, numero):
        return mensaje
    if tipo in NUMERICOS and numero.startswith("0"):
        return "El número no puede empezar por 0."
    if fecha_nacimiento:
        anios = edad(fecha_nacimiento)
        if tipo == "RC" and anios >= 7:
            return f"Con {anios} años corresponde tarjeta de identidad (el registro civil es para menores de 7)."
        if tipo == "TI" and anios < 7:
            return f"Con {anios} años corresponde registro civil (la tarjeta de identidad es desde los 7)."
        if tipo == "TI" and anios >= 18:
            return f"Con {anios} años corresponde cédula de ciudadanía."
        if tipo == "CC" and anios < 18:
            return f"Con {anios} años aún no puede tener cédula de ciudadanía: usa tarjeta de identidad."
    return None


def formatear(tipo, numero):
    """'TI', '1012345678' -> 'TI 1.012.345.678' (separador de miles colombiano)."""
    if tipo in NUMERICOS and numero and numero.isdigit():
        numero = f"{int(numero):,}".replace(",", ".")
    return f"{tipo} {numero}".strip()
