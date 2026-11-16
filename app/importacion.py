"""Carga masiva de estudiantes desde Excel (.xlsx).

Cada fila pasa por las MISMAS reglas del formulario de registro (tipo y número de
documento colombiano, edad, grado, teléfono, correo). La carga es de todo o nada:
si alguna fila tiene errores no se guarda ninguna, y se muestra qué corregir.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

from email_validator import EmailNotValidError, validate_email
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .documentos import TIPOS_DOCUMENTO, normalizar, validar
from .models import GRADOS

MAX_FILAS = 2000

# (clave interna, encabezado en la plantilla, obligatorio, ancho)
COLUMNAS = [
    ("tipo_documento", "Tipo de documento", True, 14),
    ("documento", "Número de documento", True, 20),
    ("nombres", "Nombres", True, 22),
    ("apellidos", "Apellidos", True, 24),
    ("fecha_nacimiento", "Fecha de nacimiento", False, 18),
    ("grado", "Grado", True, 9),
    ("grupo", "Grupo", False, 9),
    ("acudiente", "Nombre del acudiente", False, 26),
    ("telefono_acudiente", "Teléfono del acudiente", False, 20),
    ("email_acudiente", "Correo del acudiente", False, 30),
]
NOMBRES_GRADO = {"transicion": 0, "primero": 1, "segundo": 2, "tercero": 3, "cuarto": 4, "quinto": 5,
                 "sexto": 6, "septimo": 7, "octavo": 8, "noveno": 9, "decimo": 10, "once": 11, "undecimo": 11}


@dataclass
class Resultado:
    filas: list = field(default_factory=list)       # dicts listos para crear Estudiante
    errores: list = field(default_factory=list)     # (fila, columna, mensaje)
    omitidos: int = 0                               # ya registrados (si se pidió omitirlos)


def _sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _clave_encabezado(texto):
    return re.sub(r"[^a-z]", "", _sin_tildes(str(texto or "")).lower())


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)                 # 1012345678.0 -> "1012345678"
    return str(valor).strip()


def _fecha(valor):
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = _texto(valor)
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ValueError("Fecha no válida: usa dd/mm/aaaa (ej. 15/03/2012).")


def _grado(valor):
    texto = _sin_tildes(_texto(valor)).lower().replace("°", "").replace("º", "").strip()
    if texto.isdigit() and int(texto) in GRADOS:
        return int(texto)
    if texto in NOMBRES_GRADO:
        return NOMBRES_GRADO[texto]
    raise ValueError("Grado no válido: escribe un número de 0 (transición) a 11.")


def leer_estudiantes(archivo, documentos_existentes, omitir_existentes=False):
    """Lee y valida el Excel. `documentos_existentes`: números ya registrados en el colegio."""
    res = Resultado()
    try:
        libro = load_workbook(archivo, read_only=True, data_only=True)
    except Exception:
        res.errores.append((None, None, "No se pudo leer el archivo. Debe ser un Excel .xlsx (usa la plantilla)."))
        return res
    hoja = libro.worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    encabezados = next(filas, None) or ()

    # Ubica cada columna por su encabezado (el orden no importa)
    por_titulo = {_clave_encabezado(t): i for i, t in enumerate(encabezados) if t}
    posicion = {}
    for clave, titulo, obligatoria, _ in COLUMNAS:
        i = por_titulo.get(_clave_encabezado(titulo))
        if i is None and obligatoria:
            res.errores.append((1, titulo, "Falta esta columna en la primera fila. Usa la plantilla."))
        posicion[clave] = i
    if res.errores:
        return res

    vistos = {}
    for n, fila in enumerate(filas, start=2):
        valores = {c: (fila[i] if i is not None and i < len(fila) else None) for c, i in posicion.items()}
        if all(_texto(v) == "" for v in valores.values()):
            continue                                   # fila vacía
        if len(res.filas) + res.omitidos >= MAX_FILAS:
            res.errores.append((n, None, f"El archivo supera el máximo de {MAX_FILAS} estudiantes por carga."))
            break
        errores = []

        def error(columna, mensaje):
            errores.append((n, columna, mensaje))

        datos = {}
        tipo = _texto(valores["tipo_documento"]).upper()
        if tipo not in TIPOS_DOCUMENTO:
            # también acepta el nombre completo ("Tarjeta de identidad")
            tipo = next((k for k, v in TIPOS_DOCUMENTO.items()
                         if _clave_encabezado(v[0]) == _clave_encabezado(tipo)), tipo)
        datos["tipo_documento"] = tipo
        datos["documento"] = normalizar(_texto(valores["documento"]))
        for c in ("nombres", "apellidos"):
            datos[c] = " ".join(_texto(valores[c]).split())
            if not datos[c]:
                error(c.capitalize(), "Es obligatorio.")
            elif len(datos[c]) > 80:
                error(c.capitalize(), "Máximo 80 caracteres.")
        try:
            datos["fecha_nacimiento"] = _fecha(valores["fecha_nacimiento"])
            if datos["fecha_nacimiento"] and datos["fecha_nacimiento"] > date.today():
                error("Fecha de nacimiento", "La fecha no puede ser futura.")
        except ValueError as e:
            datos["fecha_nacimiento"] = None
            error("Fecha de nacimiento", str(e))
        try:
            datos["grado"] = _grado(valores["grado"])
        except ValueError as e:
            error("Grado", str(e))
        datos["grupo"] = _texto(valores["grupo"]).upper()[:10] or None
        datos["acudiente"] = _texto(valores["acudiente"])[:120] or None
        tel = _texto(valores["telefono_acudiente"])
        if tel and not re.fullmatch(r"[0-9+\s\-]{7,20}", tel):
            error("Teléfono del acudiente", "Teléfono no válido.")
        datos["telefono_acudiente"] = tel or None
        correo = _texto(valores["email_acudiente"]).lower()
        if correo:
            try:
                validate_email(correo, check_deliverability=False)
            except EmailNotValidError:
                error("Correo del acudiente", "Correo no válido.")
        datos["email_acudiente"] = correo or None

        if not datos["documento"]:
            error("Número de documento", "Es obligatorio.")
        else:
            msg = validar(tipo, datos["documento"], datos["fecha_nacimiento"])
            if msg:
                error("Tipo de documento" if tipo not in TIPOS_DOCUMENTO else "Número de documento", msg)
            elif datos["documento"] in vistos:
                error("Número de documento", f"Repetido en el archivo (ya está en la fila {vistos[datos['documento']]}).")
            elif datos["documento"] in documentos_existentes:
                if omitir_existentes:
                    res.omitidos += 1
                    continue
                error("Número de documento", "Ya está registrado en el colegio.")
            vistos.setdefault(datos["documento"], n)

        if errores:
            res.errores.extend(errores)
        else:
            res.filas.append(datos)
    libro.close()
    return res


def plantilla():
    """Excel vacío con encabezados, lista de tipos de documento e instrucciones."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Estudiantes"
    azul = PatternFill("solid", fgColor="3442B8")
    for col, (_, titulo, obligatoria, ancho) in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=col, value=titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = azul if obligatoria else PatternFill("solid", fgColor="7C86D6")
        celda.alignment = Alignment(vertical="center", wrap_text=True)
        hoja.column_dimensions[celda.column_letter].width = ancho
    hoja.row_dimensions[1].height = 32
    hoja.freeze_panes = "A2"
    # Número de documento y teléfono como TEXTO: Excel no los convierte a 1,01E+09
    for letra in ("B", "I"):
        for fila in range(2, MAX_FILAS + 2):
            hoja[f"{letra}{fila}"].number_format = "@"
    for fila in range(2, MAX_FILAS + 2):
        hoja[f"E{fila}"].number_format = "DD/MM/YYYY"
    lista = DataValidation(type="list", formula1='"' + ",".join(TIPOS_DOCUMENTO) + '"', allow_blank=False,
                           errorTitle="Tipo de documento", error="Elige un tipo de la lista (RC, TI, CC…).")
    grados = DataValidation(type="whole", operator="between", formula1="0", formula2="11",
                            errorTitle="Grado", error="Escribe un número de 0 (transición) a 11.")
    hoja.add_data_validation(lista)
    hoja.add_data_validation(grados)
    lista.add(f"A2:A{MAX_FILAS + 1}")
    grados.add(f"F2:F{MAX_FILAS + 1}")

    ayuda = libro.create_sheet("Instrucciones")
    ayuda.column_dimensions["A"].width = 30
    ayuda.column_dimensions["B"].width = 80
    lineas = [
        ("Cómo llenar la plantilla", ""),
        ("", ""),
        ("Columnas en azul oscuro", "Son obligatorias. Las de azul claro son opcionales."),
        ("Una fila por estudiante", "Desde la fila 2 de la hoja «Estudiantes». No cambies los encabezados."),
        ("Número de documento", "Sin puntos ni espacios (si los pones, se quitan solos)."),
        ("Fecha de nacimiento", "dd/mm/aaaa, por ejemplo 15/03/2012. Si la pones, se revisa con el tipo de documento."),
        ("Grado", "Número de 0 (transición) a 11."),
        ("Grupo", "Letra o número del curso: A, B, 01, 902…"),
        ("Si hay errores", "No se guarda nada: la página muestra la fila y la columna a corregir."),
        ("", ""),
        ("Tipos de documento", ""),
    ] + [(k, f"{v[0]} — {v[2]}") for k, v in TIPOS_DOCUMENTO.items()] + [
        ("", ""),
        ("Edad y documento", "RC: menores de 7 años · TI: de 7 a 17 · CC: desde los 18."),
        ("", ""),
        ("Ejemplo (no lo copies tal cual)", "TI | 1012345678 | Laura Sofía | Gómez Rincón | 15/03/2012 | 8 | A | "
                                            "María Rincón | 3001234567 | maria.rincon@gmail.com"),
    ]
    for i, (a, b) in enumerate(lineas, start=1):
        ayuda.cell(row=i, column=1, value=a).font = Font(bold=True)
        ayuda.cell(row=i, column=2, value=b).alignment = Alignment(wrap_text=True)
    ayuda["A1"].font = Font(bold=True, size=14, color="3442B8")
    ayuda["A11"].font = Font(bold=True, size=12, color="3442B8")

    salida = BytesIO()
    libro.save(salida)
    salida.seek(0)
    return salida
