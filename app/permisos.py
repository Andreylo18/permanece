"""Permisos por rol y alcance por colegio (RF-04, RNF-01).

Roles:
  admin    -> administrador general: ve y gestiona todos los colegios.
  colegio  -> coordinación de un colegio: gestiona sus estudiantes y docentes.
  docente  -> docente/orientador: consulta su colegio, registra factores e intervenciones.

Regla de oro: un usuario que no es admin SOLO ve datos de su propio colegio.
Si intenta abrir un registro de otro colegio recibe 404 (no se revela que existe).
"""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def rol_requerido(*roles):
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(*args, **kwargs):
            if current_user.rol not in roles:
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


admin_requerido = rol_requerido("admin")
gestion_estudiantes_requerida = rol_requerido("admin", "colegio")
gestion_usuarios_requerida = rol_requerido("admin", "colegio")


def limitar_a_institucion(consulta, columna_institucion):
    """Restringe una consulta al colegio del usuario (el admin ve todo)."""
    if current_user.es_admin:
        return consulta
    return consulta.filter(columna_institucion == current_user.institucion_id)


def verificar_institucion(institucion_id):
    """404 si el registro pertenece a otro colegio."""
    if not current_user.es_admin and institucion_id != current_user.institucion_id:
        abort(404)


# ---------------- Alcance del docente: solo los estudiantes de sus cursos ----------------

def _filtro_cursos_docente(docente_id):
    """Condición SQL: el estudiante está en un grado/grupo donde el docente dicta alguna materia."""
    from sqlalchemy import exists, func

    from .models import Asignacion, Estudiante
    return exists().where(
        Asignacion.docente_id == docente_id,
        Asignacion.institucion_id == Estudiante.institucion_id,
        Asignacion.grado == Estudiante.grado,
        Asignacion.grupo == func.coalesce(Estudiante.grupo, ""),
    )


def limitar_estudiantes(consulta):
    """Colegio del usuario y, si es docente, solo los cursos que tiene asignados."""
    from .models import Estudiante
    consulta = limitar_a_institucion(consulta, Estudiante.institucion_id)
    if current_user.rol == "docente":
        consulta = consulta.filter(_filtro_cursos_docente(current_user.id))
    return consulta


def verificar_estudiante(est):
    """404 si el estudiante no es visible para el usuario actual."""
    verificar_institucion(est.institucion_id)
    if current_user.rol == "docente":
        from .extensions import db
        from .models import Asignacion
        dicta = db.session.execute(db.select(Asignacion.id).filter_by(
            docente_id=current_user.id, institucion_id=est.institucion_id,
            grado=est.grado, grupo=est.grupo or "")).first()
        if dicta is None:
            abort(404)
