"""Dashboard e indicadores por grado y nivel de riesgo (RF-14, BE-05, FE-04)."""
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, true

from ..estudiantes.routes import consulta_filtrada, instituciones_visibles
from ..extensions import db
from ..models import nombre_grado, GRADOS, MUNICIPIOS_SABANA_CENTRO, Estudiante, Intervencion

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def raiz():
    return redirect(url_for("dashboard.inicio" if current_user.is_authenticated else "auth.login"))


def calcular_indicadores(args):
    """Consultas agregadas. Se separa para poder probar que los totales cuadran."""
    base = consulta_filtrada(args).subquery()
    E = db.aliased(Estudiante, base)

    # Totales por nivel
    filas = db.session.execute(db.select(E.nivel_actual, func.count()).group_by(E.nivel_actual)).all()
    por_nivel = {"bajo": 0, "medio": 0, "alto": 0, "sin": 0}
    for nivel, n in filas:
        por_nivel[nivel or "sin"] += n
    total = sum(por_nivel.values())

    # Por grado y nivel
    filas = db.session.execute(
        db.select(E.grado, E.nivel_actual, func.count()).group_by(E.grado, E.nivel_actual)).all()
    grados_presentes = sorted({g for g, _, _ in filas})
    matriz = {g: {"bajo": 0, "medio": 0, "alto": 0, "sin": 0} for g in grados_presentes}
    for g, nivel, n in filas:
        matriz[g][nivel or "sin"] += n

    incompletos = db.session.execute(
        db.select(func.count()).select_from(base).where(base.c.datos_incompletos == true())).scalar()

    abiertas = db.session.execute(
        db.select(func.count(Intervencion.id))
        .join(base, base.c.id == Intervencion.estudiante_id)
        .where(Intervencion.estado == "abierta")).scalar()

    # Casos de riesgo alto sin ninguna intervención abierta: requieren atención
    con_abierta = db.select(Intervencion.estudiante_id).where(Intervencion.estado == "abierta")
    prioritarios = db.session.execute(
        db.select(E).where(E.nivel_actual == "alto", E.id.not_in(con_abierta))
        .order_by(E.puntaje_actual.desc(), E.apellidos).limit(10)).scalars().all()

    # Resumen por colegio (útil para el administrador)
    filas = db.session.execute(
        db.select(E.institucion_id, E.nivel_actual, func.count()).group_by(E.institucion_id, E.nivel_actual)).all()
    por_colegio = {}
    for inst_id, nivel, n in filas:
        fila = por_colegio.setdefault(inst_id, {"bajo": 0, "medio": 0, "alto": 0, "sin": 0})
        fila[nivel or "sin"] += n

    return {
        "por_colegio": por_colegio,
        "total": total, "por_nivel": por_nivel, "matriz": matriz,
        "grados_presentes": grados_presentes,
        "etiquetas_grados": [nombre_grado(g) for g in grados_presentes], "incompletos": incompletos,
        "intervenciones_abiertas": abiertas, "prioritarios": prioritarios,
    }


@bp.route("/dashboard")
@login_required
def inicio():
    datos = calcular_indicadores(request.args)
    instituciones = instituciones_visibles()
    return render_template("dashboard/inicio.html", d=datos, grados=GRADOS,
                           municipios=MUNICIPIOS_SABANA_CENTRO, instituciones=instituciones,
                           nombres_colegio={i.id: i.nombre for i in instituciones})
