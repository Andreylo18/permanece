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
