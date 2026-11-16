"""Reglas de clasificación de riesgo académico (BE-04, RF-09).

Modelo explicable: suma de factores de 0 a 100. Los pesos y umbrales son una
PROPUESTA INICIAL de diseño (documento del proyecto, sección 5.2) y deben
revisarse con responsables académicos (AN-02) antes de usarse con casos reales.
El puntaje orienta la revisión; NO es una probabilidad de deserción.

Este módulo no depende de Flask ni de la base de datos para poder probarlo
de forma aislada con los ejemplos y valores límite de AN-02.
"""
from dataclasses import dataclass, field

# --- Parámetros (ajustar aquí tras la revisión AN-02) ----------------------
UMBRAL_ASISTENCIA = 80.0      # % ; riesgo si es INFERIOR
UMBRAL_REPROBADAS = 3         # riesgo si es IGUAL O MAYOR
UMBRAL_PROMEDIO = 3.0         # escala 0,0–5,0 ; riesgo si es INFERIOR

PUNTOS = {
    "asistencia": 30,
    "reprobadas": 25,
    "promedio": 20,
    "apoyo_familiar": 15,
    "reporte_activo": 10,
}

NIVELES = (  # (nivel, mínimo, máximo, interpretación)
    ("bajo", 0, 29, "Seguimiento ordinario."),
    ("medio", 30, 59, "Revisión del caso y acompañamiento."),
    ("alto", 60, 100, "Revisión prioritaria por el responsable académico."),
)

APOYO_OPCIONES = (
    ("adecuado", "Adecuado"),
    ("parcial", "Parcial"),
    ("insuficiente", "Insuficiente"),
)


@dataclass
class FactorEvaluado:
    clave: str
    nombre: str
    valor: str          # valor legible registrado
    aplica: bool        # suma puntos
    puntos: int
    faltante: bool = False


@dataclass
class ResultadoRiesgo:
    puntaje: int
    nivel: str
    interpretacion: str
    datos_incompletos: bool
    factores: list = field(default_factory=list)

    @property
    def factores_que_aplican(self):
        return [f for f in self.factores if f.aplica]

    @property
    def faltantes(self):
        return [f for f in self.factores if f.faltante]


def nivel_para(puntaje: int):
    for nivel, minimo, maximo, texto in NIVELES:
        if minimo <= puntaje <= maximo:
            return nivel, texto
    raise ValueError(f"Puntaje fuera de rango: {puntaje}")


def _fmt_num(valor, decimales=1):
    return f"{valor:.{decimales}f}".replace(".", ",")


def calcular_riesgo(asistencia_pct=None, asignaturas_reprobadas=None,
                    promedio=None, apoyo_familiar=None, reporte_activo=None):
    """Calcula puntaje, nivel y factores. Un valor None = dato no registrado.

    Los datos faltantes NO suman puntos, pero el resultado se marca como
    incompleto para revisión: no se asumen como ausencia de riesgo (5.3).
    """
    factores = []

    # 1. Asistencia
    if asistencia_pct is None:
        factores.append(FactorEvaluado("asistencia", "Asistencia", "Sin registrar", False, 0, True))
    else:
        aplica = asistencia_pct < UMBRAL_ASISTENCIA
        factores.append(FactorEvaluado(
            "asistencia", f"Asistencia inferior al {int(UMBRAL_ASISTENCIA)} %",
            f"{_fmt_num(asistencia_pct)} %", aplica, PUNTOS["asistencia"] if aplica else 0))

    # 2. Asignaturas reprobadas
    if asignaturas_reprobadas is None:
        factores.append(FactorEvaluado("reprobadas", "Asignaturas reprobadas", "Sin registrar", False, 0, True))
    else:
        aplica = asignaturas_reprobadas >= UMBRAL_REPROBADAS
        factores.append(FactorEvaluado(
            "reprobadas", f"{UMBRAL_REPROBADAS} o más asignaturas reprobadas",
            str(asignaturas_reprobadas), aplica, PUNTOS["reprobadas"] if aplica else 0))

    # 3. Promedio
    if promedio is None:
        factores.append(FactorEvaluado("promedio", "Promedio", "Sin registrar", False, 0, True))
    else:
        aplica = promedio < UMBRAL_PROMEDIO
        factores.append(FactorEvaluado(
            "promedio", f"Promedio inferior a {_fmt_num(UMBRAL_PROMEDIO)} sobre 5,0",
            _fmt_num(promedio, 2), aplica, PUNTOS["promedio"] if aplica else 0))

    # 4. Apoyo familiar
    etiquetas = dict(APOYO_OPCIONES)
    if not apoyo_familiar:
        factores.append(FactorEvaluado("apoyo_familiar", "Apoyo familiar", "Sin registrar", False, 0, True))
    else:
        aplica = apoyo_familiar == "insuficiente"
        factores.append(FactorEvaluado(
            "apoyo_familiar", "Apoyo familiar insuficiente registrado",
            etiquetas.get(apoyo_familiar, apoyo_familiar), aplica,
            PUNTOS["apoyo_familiar"] if aplica else 0))

    # 5. Reporte de seguimiento activo
    if reporte_activo is None:
        factores.append(FactorEvaluado("reporte_activo", "Reporte de seguimiento", "Sin registrar", False, 0, True))
    else:
        aplica = bool(reporte_activo)
        factores.append(FactorEvaluado(
            "reporte_activo", "Reporte de seguimiento activo",
            "Sí" if aplica else "No", aplica, PUNTOS["reporte_activo"] if aplica else 0))

    puntaje = sum(f.puntos for f in factores)
    nivel, texto = nivel_para(puntaje)
    return ResultadoRiesgo(
        puntaje=puntaje,
        nivel=nivel,
        interpretacion=texto,
        datos_incompletos=any(f.faltante for f in factores),
        factores=factores,
    )
