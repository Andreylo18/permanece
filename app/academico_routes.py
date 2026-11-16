"""Módulo académico.

Colegio: periodos, materias y cursos (materia + docente + grado/grupo).
Docente: en sus cursos, toma asistencia por clase y califica actividades.
Cada vez que se guardan notas o asistencia se recalcula el riesgo del curso.
"""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .academico import periodo_activo, periodos_de, recalcular_curso
from .extensions import db
from .forms import ActividadForm, AsignacionForm, MateriaForm, PeriodoForm, SesionForm
from .models import (ESTADOS_ASISTENCIA, Actividad, Asignacion, Asistencia, Materia, Nota, Periodo,
                     SesionClase, Usuario)
from .permisos import rol_requerido, verificar_institucion

bp = Blueprint("academico", __name__)
colegio_requerido = rol_requerido("colegio")


def _flash_alertas(n):
    if n:
        flash(f"{n} estudiante(s) pasaron a riesgo alto: se notificó a la coordinación y al acudiente.", "warning")


# ============================ Configuración (colegio) ============================

@bp.route("/periodos", methods=["GET", "POST"])
@colegio_requerido
def periodos():
    inst_id = current_user.institucion_id
    form = PeriodoForm()
    if form.validate_on_submit():
        nombre = form.nombre.data.strip().upper()
        if db.session.execute(db.select(Periodo.id).filter_by(institucion_id=inst_id, nombre=nombre)).first():
            form.nombre.errors.append("Ese periodo ya existe.")
        else:
            if form.activo.data:
                for p in periodos_de(inst_id):
                    p.activo = False
            db.session.add(Periodo(institucion_id=inst_id, nombre=nombre, fecha_inicio=form.fecha_inicio.data,
                                   fecha_fin=form.fecha_fin.data, activo=form.activo.data))
            db.session.commit()
            flash(f"Periodo {nombre} creado.", "success")
            return redirect(url_for("academico.periodos"))
    return render_template("academico/periodos.html", form=form, periodos=periodos_de(inst_id))


@bp.route("/periodos/<int:periodo_id>/activar", methods=["POST"])
@colegio_requerido
def activar_periodo(periodo_id):
    p = db.session.get(Periodo, periodo_id) or abort(404)
    verificar_institucion(p.institucion_id)
    for otro in periodos_de(p.institucion_id):
        otro.activo = otro.id == p.id
    db.session.commit()
    flash(f"{p.nombre} es ahora el periodo activo.", "success")
    return redirect(url_for("academico.periodos"))


@bp.route("/materias", methods=["GET", "POST"])
@colegio_requerido
def materias():
    inst_id = current_user.institucion_id
    form = MateriaForm()
    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        existe = db.session.execute(db.select(Materia.id).filter(
            Materia.institucion_id == inst_id, db.func.lower(Materia.nombre) == nombre.lower())).first()
        if existe:
            form.nombre.errors.append("Esa materia ya existe.")
        else:
            db.session.add(Materia(institucion_id=inst_id, nombre=nombre))
            db.session.commit()
            flash(f"Materia {nombre} agregada.", "success")
            return redirect(url_for("academico.materias"))
    lista = db.session.execute(db.select(Materia).filter_by(institucion_id=inst_id)
                               .order_by(Materia.activa.desc(), Materia.nombre)).scalars().all()
    cursos = dict(db.session.execute(db.select(Asignacion.materia_id, db.func.count())
                                     .filter_by(institucion_id=inst_id).group_by(Asignacion.materia_id)).all())
    return render_template("academico/materias.html", form=form, materias=lista, cursos=cursos)


@bp.route("/materias/<int:materia_id>/estado", methods=["POST"])
@colegio_requerido
def estado_materia(materia_id):
    m = db.session.get(Materia, materia_id) or abort(404)
    verificar_institucion(m.institucion_id)
    m.activa = not m.activa
    db.session.commit()
    flash(f"Materia {m.nombre} {'activada' if m.activa else 'desactivada'}.", "info")
    return redirect(url_for("academico.materias"))


def _opciones_asignacion(form, inst_id):
    form.materia_id.choices = [(m.id, m.nombre) for m in db.session.execute(
        db.select(Materia).filter_by(institucion_id=inst_id, activa=True).order_by(Materia.nombre)).scalars()]
    form.docente_id.choices = [(u.id, u.nombre) for u in db.session.execute(
        db.select(Usuario).filter_by(institucion_id=inst_id, rol="docente", activo=True)
        .order_by(Usuario.nombre)).scalars()]


@bp.route("/cursos", methods=["GET", "POST"])
@colegio_requerido
def cursos():
    inst_id = current_user.institucion_id
    form = AsignacionForm()
    _opciones_asignacion(form, inst_id)
    if form.validate_on_submit():
        ok = True
        if form.materia_id.data not in {c[0] for c in form.materia_id.choices}:
            form.materia_id.errors = ["Selecciona una materia."]
            ok = False
        if form.docente_id.data not in {c[0] for c in form.docente_id.choices}:
            form.docente_id.errors = ["Selecciona un docente."]
            ok = False
        grupo = (form.grupo.data or "").strip().upper()
        if ok and db.session.execute(db.select(Asignacion.id).filter_by(
                materia_id=form.materia_id.data, grado=form.grado.data, grupo=grupo)).first():
            form.materia_id.errors = ["Esa materia ya está asignada a ese curso."]
            ok = False
        if ok:
            db.session.add(Asignacion(institucion_id=inst_id, materia_id=form.materia_id.data,
                                      docente_id=form.docente_id.data, grado=form.grado.data, grupo=grupo))
            db.session.commit()
            flash("Curso asignado.", "success")
            return redirect(url_for("academico.cursos"))
    lista = db.session.execute(
        db.select(Asignacion).join(Asignacion.materia).filter(Asignacion.institucion_id == inst_id)
        .order_by(Asignacion.grado, Asignacion.grupo, Materia.nombre)).scalars().all()
    return render_template("academico/cursos.html", form=form, asignaciones=lista,
                           docentes=form.docente_id.choices)


@bp.route("/cursos/<int:asignacion_id>/docente", methods=["POST"])
@colegio_requerido
def cambiar_docente(asignacion_id):
    a = db.session.get(Asignacion, asignacion_id) or abort(404)
    verificar_institucion(a.institucion_id)
    nuevo = db.session.get(Usuario, request.form.get("docente_id", type=int) or 0)
    if nuevo is None or nuevo.rol != "docente" or nuevo.institucion_id != a.institucion_id:
        flash("Docente no válido.", "danger")
    else:
        a.docente_id = nuevo.id
        db.session.commit()
        flash(f"{a.nombre}: ahora la dicta {nuevo.nombre}.", "success")
    return redirect(url_for("academico.cursos"))


# ============================ Docente: mis cursos ============================

def _curso(asignacion_id):
    """Curso visible y editable: su docente, la coordinación de su colegio o el admin."""
    a = db.session.get(Asignacion, asignacion_id) or abort(404)
    verificar_institucion(a.institucion_id)
    if current_user.rol == "docente" and a.docente_id != current_user.id:
        abort(404)
    return a


def _periodo_o_aviso(inst_id):
    p = periodo_activo(inst_id)
    if p is None:
        flash("El colegio aún no tiene un periodo activo. La coordinación debe crearlo en Académico → Periodos.",
              "warning")
    return p


@bp.route("/mis-cursos")
@login_required
def mis_cursos():
    q = db.select(Asignacion).join(Asignacion.materia)
    if current_user.rol == "docente":
        q = q.filter(Asignacion.docente_id == current_user.id)
    elif not current_user.es_admin:
        q = q.filter(Asignacion.institucion_id == current_user.institucion_id)
    lista = db.session.execute(q.order_by(Asignacion.grado, Asignacion.grupo, Materia.nombre)).scalars().all()
    periodo = periodo_activo(current_user.institucion_id) if current_user.institucion_id else None
    return render_template("academico/mis_cursos.html", asignaciones=lista, periodo=periodo)


# ---------------- Notas ----------------

def _parse_nota(texto):
    texto = (texto or "").strip().replace(",", ".")
    if texto == "":
        return None, None
    try:
        v = round(float(texto), 2)
    except ValueError:
        return None, "No es un número"
    if not 0 <= v <= 5:
        return None, "Debe estar entre 0,0 y 5,0"
    return v, None


@bp.route("/cursos/<int:asignacion_id>/notas", methods=["GET", "POST"])
@login_required
def notas(asignacion_id):
    a = _curso(asignacion_id)
    periodo = _periodo_o_aviso(a.institucion_id)
    if periodo is None:
        return redirect(url_for("academico.mis_cursos"))
    actividades = db.session.execute(db.select(Actividad).filter_by(asignacion_id=a.id, periodo_id=periodo.id)
                                     .order_by(Actividad.creado_en, Actividad.id)).scalars().all()
    estudiantes = a.estudiantes()
    existentes = {(n.actividad_id, n.estudiante_id): n for n in db.session.execute(
        db.select(Nota).filter(Nota.actividad_id.in_([x.id for x in actividades]))).scalars()} if actividades else {}
    valores = {k: f"{float(n.valor):.1f}".replace(".", ",") for k, n in existentes.items()}
    errores = {}

    if request.method == "POST":
        nuevos = {}
        for act in actividades:
            for est in estudiantes:
                clave = (act.id, est.id)
                texto = request.form.get(f"n_{act.id}_{est.id}", "")
                valores[clave] = texto
                v, err = _parse_nota(texto)
                if err:
                    errores[clave] = err
                nuevos[clave] = v
        if errores:
            flash(f"Hay {len(errores)} nota(s) con errores (marcadas en rojo). No se guardó nada.", "danger")
        else:
            for (act_id, est_id), v in nuevos.items():
                n = existentes.get((act_id, est_id))
                if v is None and n is not None:
                    db.session.delete(n)
                elif v is not None and n is None:
                    db.session.add(Nota(actividad_id=act_id, estudiante_id=est_id, valor=v))
                elif v is not None:
                    n.valor = v
            db.session.flush()
            altos = recalcular_curso(a, periodo)
            db.session.commit()
            flash("Notas guardadas. Promedios y riesgo actualizados.", "success")
            _flash_alertas(altos)
            return redirect(url_for("academico.notas", asignacion_id=a.id))

    # Nota ponderada de cada estudiante (con lo ya guardado)
    definitivas = {}
    for est in estudiantes:
        suma = pct = 0
        for act in actividades:
            n = existentes.get((act.id, est.id))
            if n is not None:
                suma += float(n.valor) * act.porcentaje
                pct += act.porcentaje
        definitivas[est.id] = round(suma / pct, 2) if pct else None
    return render_template("academico/notas.html", a=a, periodo=periodo, actividades=actividades,
                           estudiantes=estudiantes, valores=valores, errores=errores, definitivas=definitivas,
                           total_pct=sum(x.porcentaje for x in actividades), form_act=ActividadForm())


@bp.route("/cursos/<int:asignacion_id>/actividades", methods=["POST"])
@login_required
def agregar_actividad(asignacion_id):
    a = _curso(asignacion_id)
    periodo = _periodo_o_aviso(a.institucion_id)
    form = ActividadForm()
    if periodo and form.validate_on_submit():
        usado = db.session.execute(db.select(db.func.coalesce(db.func.sum(Actividad.porcentaje), 0))
                                   .filter_by(asignacion_id=a.id, periodo_id=periodo.id)).scalar()
        if usado + form.porcentaje.data > 100:
            flash(f"Con esa actividad el total pasaría de 100 % (ya hay {usado} %).", "danger")
        else:
            db.session.add(Actividad(asignacion_id=a.id, periodo_id=periodo.id, nombre=form.nombre.data.strip(),
                                     porcentaje=form.porcentaje.data))
            db.session.commit()
            flash(f"Actividad «{form.nombre.data.strip()}» agregada ({form.porcentaje.data} %).", "success")
    elif periodo:
        flash("Revisa la actividad: " + "; ".join(e for errs in form.errors.values() for e in errs), "danger")
    return redirect(url_for("academico.notas", asignacion_id=a.id))


@bp.route("/actividades/<int:actividad_id>/eliminar", methods=["POST"])
@login_required
def eliminar_actividad(actividad_id):
    act = db.session.get(Actividad, actividad_id) or abort(404)
    a = _curso(act.asignacion_id)
    periodo = db.session.get(Periodo, act.periodo_id)
    nombre = act.nombre
    db.session.delete(act)
    db.session.flush()
    altos = recalcular_curso(a, periodo)
    db.session.commit()
    flash(f"Actividad «{nombre}» y sus notas eliminadas.", "info")
    _flash_alertas(altos)
    return redirect(url_for("academico.notas", asignacion_id=a.id))


# ---------------- Asistencia ----------------

@bp.route("/cursos/<int:asignacion_id>/asistencia")
@login_required
def asistencia(asignacion_id):
    a = _curso(asignacion_id)
    periodo = _periodo_o_aviso(a.institucion_id)
    if periodo is None:
        return redirect(url_for("academico.mis_cursos"))
    sesiones = db.session.execute(db.select(SesionClase).filter_by(asignacion_id=a.id, periodo_id=periodo.id)
                                  .order_by(SesionClase.fecha.desc())).scalars().all()
    conteos = {}
    if sesiones:
        for sid, estado, n in db.session.execute(
                db.select(Asistencia.sesion_id, Asistencia.estado, db.func.count())
                .filter(Asistencia.sesion_id.in_([s.id for s in sesiones]))
                .group_by(Asistencia.sesion_id, Asistencia.estado)).all():
            conteos.setdefault(sid, {})[estado] = n
    return render_template("academico/asistencia.html", a=a, periodo=periodo, sesiones=sesiones, conteos=conteos,
                           estados=ESTADOS_ASISTENCIA)


@bp.route("/cursos/<int:asignacion_id>/asistencia/tomar", methods=["GET", "POST"])
@login_required
def tomar_asistencia(asignacion_id):
    a = _curso(asignacion_id)
    periodo = _periodo_o_aviso(a.institucion_id)
    if periodo is None:
        return redirect(url_for("academico.mis_cursos"))
    sesion = None
    if request.args.get("sesion", type=int):
        sesion = db.session.get(SesionClase, request.args.get("sesion", type=int))
        if sesion is None or sesion.asignacion_id != a.id:
            abort(404)
    form = SesionForm(obj=sesion)
    estudiantes = a.estudiantes()
    actuales = {x.estudiante_id: x for x in sesion.asistencias} if sesion else {}
    validos = {e for e, _ in ESTADOS_ASISTENCIA}

    if form.validate_on_submit():
        fecha = form.fecha.data
        if not (periodo.fecha_inicio <= fecha <= periodo.fecha_fin):
            form.fecha.errors.append(f"La fecha debe estar dentro del periodo {periodo.nombre} "
                                     f"({periodo.fecha_inicio:%d/%m/%Y} – {periodo.fecha_fin:%d/%m/%Y}).")
        else:
            otra = db.session.execute(db.select(SesionClase).filter_by(asignacion_id=a.id, fecha=fecha)).scalar()
            if otra is not None and (sesion is None or otra.id != sesion.id):
                sesion = otra          # ya había clase ese día: se actualiza esa
                actuales = {x.estudiante_id: x for x in sesion.asistencias}
            if sesion is None:
                sesion = SesionClase(asignacion_id=a.id, periodo_id=periodo.id)
                db.session.add(sesion)
            sesion.fecha, sesion.tema = fecha, (form.tema.data or "").strip() or None
            db.session.flush()
            for est in estudiantes:
                estado = request.form.get(f"e_{est.id}", "presente")
                estado = estado if estado in validos else "presente"
                if est.id in actuales:
                    actuales[est.id].estado = estado
                else:
                    db.session.add(Asistencia(sesion_id=sesion.id, estudiante_id=est.id, estado=estado))
            db.session.flush()
            altos = recalcular_curso(a, periodo)
            db.session.commit()
            fallas = sum(1 for est in estudiantes if request.form.get(f"e_{est.id}") == "ausente")
            flash(f"Asistencia del {fecha:%d/%m/%Y} guardada ({fallas} ausencia(s) sin excusa).", "success")
            _flash_alertas(altos)
            return redirect(url_for("academico.asistencia", asignacion_id=a.id))

    if request.method == "GET" and sesion is None:
        form.fecha.data = min(max(date.today(), periodo.fecha_inicio), periodo.fecha_fin)
    seleccion = {e.id: request.form.get(f"e_{e.id}") or (actuales[e.id].estado if e.id in actuales else "presente")
                 for e in estudiantes}
    return render_template("academico/tomar_asistencia.html", a=a, periodo=periodo, form=form, sesion=sesion,
                           estudiantes=estudiantes, seleccion=seleccion, estados=ESTADOS_ASISTENCIA)
