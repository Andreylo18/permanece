"""Ejemplos y valores límite de las reglas de riesgo (AN-02 / BE-04)."""
import pytest

from app.riesgo import calcular_riesgo, nivel_para

COMPLETO_SIN_RIESGO = dict(asistencia_pct=95, asignaturas_reprobadas=0, promedio=4.2,
                           apoyo_familiar="adecuado", reporte_activo=False)


def test_sin_factores_es_bajo_y_completo():
    r = calcular_riesgo(**COMPLETO_SIN_RIESGO)
    assert (r.puntaje, r.nivel, r.datos_incompletos) == (0, "bajo", False)


def test_todos_los_factores_suman_100():
    r = calcular_riesgo(70, 4, 2.5, "insuficiente", True)
    assert (r.puntaje, r.nivel) == (100, "alto")
    assert len(r.factores_que_aplican) == 5


@pytest.mark.parametrize("campo,valor,puntos", [
    ("asistencia_pct", 79.99, 30), ("asistencia_pct", 80, 0),      # límite: inferior al 80 %
    ("asignaturas_reprobadas", 3, 25), ("asignaturas_reprobadas", 2, 0),  # límite: 3 o más
    ("promedio", 2.99, 20), ("promedio", 3.0, 0),                  # límite: inferior a 3,0
    ("apoyo_familiar", "insuficiente", 15), ("apoyo_familiar", "parcial", 0),
    ("reporte_activo", True, 10),
])
def test_cada_factor_y_sus_limites(campo, valor, puntos):
    datos = dict(COMPLETO_SIN_RIESGO, **{campo: valor})
    assert calcular_riesgo(**datos).puntaje == puntos


@pytest.mark.parametrize("puntaje,nivel", [
    (0, "bajo"), (29, "bajo"), (30, "medio"), (59, "medio"), (60, "alto"), (100, "alto")])
def test_limites_de_nivel(puntaje, nivel):
    assert nivel_para(puntaje)[0] == nivel


def test_ejemplo_medio_asistencia_sola():
    r = calcular_riesgo(**dict(COMPLETO_SIN_RIESGO, asistencia_pct=75))
    assert (r.puntaje, r.nivel) == (30, "medio")


def test_ejemplo_alto_asistencia_y_reprobadas_y_reporte():
    r = calcular_riesgo(**dict(COMPLETO_SIN_RIESGO, asistencia_pct=70, asignaturas_reprobadas=3,
                               reporte_activo=True))
    assert (r.puntaje, r.nivel) == (65, "alto")


def test_ejemplo_limite_59_no_es_alto():
    # reprobadas (25) + promedio (20) + reporte (10) = 55 -> medio
    r = calcular_riesgo(**dict(COMPLETO_SIN_RIESGO, asignaturas_reprobadas=4, promedio=2.8,
                               reporte_activo=True))
    assert (r.puntaje, r.nivel) == (55, "medio")


def test_datos_faltantes_se_marcan_y_no_suman():
    r = calcular_riesgo(asistencia_pct=None, asignaturas_reprobadas=1, promedio=None,
                        apoyo_familiar=None, reporte_activo=None)
    assert r.puntaje == 0
    assert r.datos_incompletos is True
    assert {f.clave for f in r.faltantes} == {"asistencia", "promedio", "apoyo_familiar", "reporte_activo"}
