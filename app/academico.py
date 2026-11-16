"""Cálculos académicos que alimentan la clasificación de riesgo.

Reglas (acordadas con el equipo):
- Nota de una materia en el periodo = promedio PONDERADO por el porcentaje de
  cada actividad, usando solo las actividades ya calificadas (se normaliza).
- Una materia está reprobada si su nota es inferior a 3,0.
- Promedio del periodo = promedio simple de las notas de las materias.
- Asistencia (%) = (presente + tarde) / (clases registradas − ausencias con excusa).
  La ausencia con excusa queda registrada pero NO baja el porcentaje.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from .extensions import db
from .models import (Actividad, Asignacion, Asistencia, Estudiante, Materia, Nota, Periodo,
                     RegistroFactores, SesionClase)
from .riesgo import UMBRAL_PROMEDIO

NOTA_APROBATORIA = UMBRAL_PROMEDIO  # 3,0


def periodo_activo(institucion_id):
    return db.session.execute(
        db.select(Periodo).filter_by(institucion_id=institucion_id, activo=True)).scalar_one_or_none()


def periodos_de(institucion_id):
    return db.session.execute(
        db.select(Periodo).filter_by(institucion_id=institucion_id).order_by(Periodo.nombre.desc())
    ).scalars().all()


def asignaciones_del_estudiante(est):
    return db.session.execute(
        db.select(Asignacion).join(Asignacion.materia)
        .filter(Asignacion.institucion_id == est.institucion_id, Asignacion.grado == est.grado,
                Asignacion.grupo == (est.grupo or ""), Materia.activa == db.true())
        .order_by(Materia.nombre)).scalars().all()


@dataclass
class ResumenMateria:
    asignacion: Asignacion
    actividades: list = field(default_factory=list)    # [(nombre, porcentaje, valor|None)]
    nota: float | None = None
    porcentaje_evaluado: int = 0
    clases: int = 0
    presentes: int = 0
    tardes: int = 0
    ausencias: int = 0
    excusas: int = 0

    @property
    def reprobada(self):
        return self.nota is not None and self.nota < NOTA_APROBATORIA

    @property
    def asistencia_pct(self):
        base = self.clases - self.excusas
        return round((self.presentes + self.tardes) * 100 / base, 1) if base > 0 else None


@dataclass
class ResumenAcademico:
    materias: list
    promedio: float | None
    reprobadas: int | None
    asistencia_pct: float | None
    clases: int
    ausencias: int
    excusas: int
    tardes: int

    @property
    def tiene_notas(self):
        return self.promedio is not None


def resumen_academico(est, periodo):
    """Calcula notas y asistencia del estudiante en el periodo (pocas consultas)."""
    asignaciones = asignaciones_del_estudiante(est)
    por_id = {a.id: ResumenMateria(asignacion=a) for a in asignaciones}
    if periodo is None or not por_id:
        return ResumenAcademico(list(por_id.values()), None, None, None, 0, 0, 0, 0)

    # Notas: todas las actividades del periodo con la nota del estudiante (si existe)
    filas = db.session.execute(
        db.select(Actividad.asignacion_id, Actividad.nombre, Actividad.porcentaje, Nota.valor)
        .outerjoin(Nota, (Nota.actividad_id == Actividad.id) & (Nota.estudiante_id == est.id))
        .filter(Actividad.asignacion_id.in_(por_id), Actividad.periodo_id == periodo.id)
        .order_by(Actividad.creado_en, Actividad.id)).all()
    acumulado = defaultdict(lambda: [0.0, 0])   # asignacion -> [suma ponderada, % calificado]
    for asig_id, nombre, porcentaje, valor in filas:
        rm = por_id[asig_id]
        rm.actividades.append((nombre, porcentaje, float(valor) if valor is not None else None))
        if valor is not None:
            acumulado[asig_id][0] += float(valor) * porcentaje
            acumulado[asig_id][1] += porcentaje
    for asig_id, (suma, pct) in acumulado.items():
        if pct:
            por_id[asig_id].nota = round(suma / pct, 2)
            por_id[asig_id].porcentaje_evaluado = pct

    # Asistencia
    filas = db.session.execute(
        db.select(SesionClase.asignacion_id, Asistencia.estado, db.func.count())
        .join(Asistencia, Asistencia.sesion_id == SesionClase.id)
        .filter(SesionClase.asignacion_id.in_(por_id), SesionClase.periodo_id == periodo.id,
                Asistencia.estudiante_id == est.id)
        .group_by(SesionClase.asignacion_id, Asistencia.estado)).all()
    for asig_id, estado, n in filas:
        rm = por_id[asig_id]
        rm.clases += n
        if estado == "presente":
            rm.presentes += n
        elif estado == "tarde":
            rm.tardes += n
        elif estado == "excusa":
            rm.excusas += n
        else:
            rm.ausencias += n

    materias = list(por_id.values())
    notas = [m.nota for m in materias if m.nota is not None]
    clases = sum(m.clases for m in materias)
    excusas = sum(m.excusas for m in materias)
    asistidas = sum(m.presentes + m.tardes for m in materias)
    base = clases - excusas
    return ResumenAcademico(
        materias=materias,
        promedio=round(sum(notas) / len(notas), 2) if notas else None,
        reprobadas=sum(1 for m in materias if m.reprobada) if notas else None,
        asistencia_pct=round(asistidas * 100 / base, 1) if base > 0 else None,
        clases=clases, ausencias=sum(m.ausencias for m in materias), excusas=excusas,
        tardes=sum(m.tardes for m in materias),
    )


def recalcular_estudiante(est, periodo, usuario=None, apoyo_familiar=..., reporte_activo=...,
                          observaciones=..., notificar=True):
    """Actualiza el registro de factores del periodo con los datos académicos y
    recalcula el riesgo. Los argumentos con ... conservan el valor existente.

    Devuelve (resultado, paso_a_alto).
    """
    res = resumen_academico(est, periodo)
    reg = db.session.execute(
        db.select(RegistroFactores).filter_by(estudiante_id=est.id, periodo=periodo.nombre)).scalar_one_or_none()
    if reg is None:
        reg = RegistroFactores(estudiante_id=est.id, periodo=periodo.nombre)
        db.session.add(reg)
    reg.asistencia_pct = res.asistencia_pct
    reg.promedio = res.promedio
    reg.asignaturas_reprobadas = res.reprobadas
    if apoyo_familiar is not ...:
        reg.apoyo_familiar = apoyo_familiar
    if reporte_activo is not ...:
        reg.reporte_activo = reporte_activo
    if observaciones is not ...:
        reg.observaciones = observaciones
    if usuario is not None:
        reg.registrado_por_id = usuario.id
    resultado = reg.recalcular()
    db.session.flush()

    nivel_anterior = est.nivel_actual
    db.session.expire(est, ["registros"])
    est.actualizar_riesgo()
    paso_a_alto = est.nivel_actual == "alto" and nivel_anterior != "alto"
    if paso_a_alto and notificar:
        from .correo import notificar_riesgo_alto
        notificar_riesgo_alto(est)
    return resultado, paso_a_alto


def recalcular_curso(asignacion, periodo, notificar=True):
    """Recalcula a todos los estudiantes del curso. Devuelve cuántos pasaron a riesgo alto."""
    nuevos_altos = 0
    for est in asignacion.estudiantes():
        _, alto = recalcular_estudiante(est, periodo, notificar=notificar)
        nuevos_altos += alto
    return nuevos_altos


def estudiantes_por_id(ids):
    if not ids:
        return {}
    return {e.id: e for e in db.session.execute(db.select(Estudiante).filter(Estudiante.id.in_(ids))).scalars()}
