"""Dashboard e indicadores por grado y nivel de riesgo (RF-14, BE-05, FE-04)."""
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, true

from ..estudiantes.routes import consulta_filtrada, instituciones_visibles
from ..extensions import db
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..academico import periodo_activo
from ..models import (GRADOS, MUNICIPIOS_SABANA_CENTRO, Asignacion, Estudiante, Intervencion, Materia,
                      RegistroFactores, SesionClase, nombre_grado)

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
    sin_intervencion = db.select(E).where(E.nivel_actual == "alto", E.id.not_in(con_abierta))
    prioritarios = db.session.execute(
        sin_intervencion.order_by(E.puntaje_actual.desc(), E.apellidos).limit(5)).scalars().all()
    n_sin_intervencion = db.session.execute(
        db.select(func.count()).select_from(sin_intervencion.subquery())).scalar()

    # Asistencia, promedio y materias reprobadas del registro vigente de cada estudiante
    R = RegistroFactores
    ultimo = (db.select(R.estudiante_id, func.max(R.periodo).label("periodo"))
              .join(base, base.c.id == R.estudiante_id).group_by(R.estudiante_id).subquery())
    asis, prom, reprob = db.session.execute(
        db.select(func.avg(R.asistencia_pct), func.avg(R.promedio), func.sum(R.asignaturas_reprobadas))
        .join(ultimo, (ultimo.c.estudiante_id == R.estudiante_id) & (ultimo.c.periodo == R.periodo))).one()

    # Resumen por colegio (útil para el administrador)
    filas = db.session.execute(
        db.select(E.institucion_id, E.nivel_actual, func.count()).group_by(E.institucion_id, E.nivel_actual)).all()
    por_colegio = {}
    for inst_id, nivel, n in filas:
        fila = por_colegio.setdefault(inst_id, {"bajo": 0, "medio": 0, "alto": 0, "sin": 0})
        fila[nivel or "sin"] += n

    return {
        "asistencia_promedio": round(float(asis), 1) if asis is not None else None,
        "promedio_general": round(float(prom), 2) if prom is not None else None,
        "reprobadas_total": int(reprob or 0),
        "sin_intervencion": n_sin_intervencion,
        "max_alto_grado": max([1] + [m["alto"] for m in matriz.values()]),
        "por_colegio": por_colegio,
        "total": total, "por_nivel": por_nivel, "matriz": matriz,
        "grados_presentes": grados_presentes,
        "etiquetas_grados": [nombre_grado(g) for g in grados_presentes], "incompletos": incompletos,
        "intervenciones_abiertas": abiertas, "prioritarios": prioritarios,
    }


def asistencia_de_hoy(limite=6):
    """Cursos visibles y si ya se tomó asistencia hoy (pendientes primero)."""
    if current_user.es_admin:
        return []
    q = db.select(Asignacion).join(Asignacion.materia).filter(Materia.activa == true())
    if current_user.rol == "docente":
        q = q.filter(Asignacion.docente_id == current_user.id)
    else:
        q = q.filter(Asignacion.institucion_id == current_user.institucion_id)
    cursos = db.session.execute(q.order_by(Asignacion.grado, Asignacion.grupo, Materia.nombre)).scalars().all()
    if not cursos or periodo_activo(current_user.institucion_id) is None:
        return []
    tomadas = set(db.session.execute(
        db.select(SesionClase.asignacion_id).filter(SesionClase.fecha == date.today(),
                                                    SesionClase.asignacion_id.in_([c.id for c in cursos]))).scalars())
    filas = [{"curso": c, "tomada": c.id in tomadas} for c in cursos]
    filas.sort(key=lambda f: f["tomada"])
    return filas[:limite], len(tomadas), len(cursos)


def saludo():
    hora = datetime.now(ZoneInfo("America/Bogota")).hour
    return "Buenos días" if hora < 12 else ("Buenas tardes" if hora < 19 else "Buenas noches")


@bp.route("/dashboard")
@login_required
def inicio():
    datos = calcular_indicadores(request.args)
    instituciones = instituciones_visibles()
    hoy = asistencia_de_hoy()
    clases, tomadas, total_cursos = hoy if hoy else ([], 0, 0)
    return render_template("dashboard/inicio.html", d=datos, grados=GRADOS,
                           municipios=MUNICIPIOS_SABANA_CENTRO, instituciones=instituciones,
                           nombres_colegio={i.id: i.nombre for i in instituciones},
                           saludo=saludo(), clases=clases, tomadas=tomadas, total_cursos=total_cursos)
