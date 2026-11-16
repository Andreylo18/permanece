"""Modelo de datos (BE-01): usuarios, estudiantes, factores e intervenciones.

Base de datos: PostgreSQL (Neon) en producción, SQLite en desarrollo local.
"""
from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .riesgo import calcular_riesgo


def ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


ROLES = (
    ("admin", "Administrador general"),
    ("colegio", "Colegio (coordinación)"),
    ("docente", "Docente / orientador"),
)

MUNICIPIOS_SABANA_CENTRO = (
    "Cajicá", "Chía", "Cogua", "Cota", "Gachancipá", "Nemocón",
    "Sopó", "Tabio", "Tenjo", "Tocancipá", "Zipaquirá",
)

GRADOS = tuple(range(0, 12))  # 0 = transición, 1–11


def nombre_grado(g):
    return "Transición" if g == 0 else f"{g}°"


SECTORES = (("oficial", "Oficial"), ("no_oficial", "No oficial"))


class Institucion(db.Model):
    """Colegio. Todo estudiante y todo usuario no administrador pertenece a uno."""
    __tablename__ = "instituciones"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.Unicode(150), nullable=False)
    codigo_dane = db.Column(db.String(12))  # único si existe (se valida en la app)
    municipio = db.Column(db.Unicode(40), nullable=False, index=True)
    sector = db.Column(db.String(12), nullable=False, default="oficial")
    direccion = db.Column(db.Unicode(150))
    telefono = db.Column(db.String(20))
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    usuarios = db.relationship("Usuario", back_populates="institucion")
    estudiantes = db.relationship("Estudiante", back_populates="institucion")

    @property
    def sector_nombre(self):
        return dict(SECTORES).get(self.sector, self.sector)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.Unicode(120), nullable=False)
    email = db.Column(db.Unicode(160), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="docente")
    # NULL solo para el administrador general
    institucion_id = db.Column(db.Integer, db.ForeignKey("instituciones.id"), index=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    institucion = db.relationship("Institucion", back_populates="usuarios")

    def set_password(self, clave):
        self.password_hash = generate_password_hash(clave)

    def check_password(self, clave):
        return check_password_hash(self.password_hash, clave)

    @property
    def es_admin(self):
        return self.rol == "admin"

    @property
    def es_colegio(self):
        return self.rol == "colegio"

    @property
    def puede_gestionar_estudiantes(self):
        """Registrar y editar datos de estudiantes: administrador y colegio."""
        return self.rol in ("admin", "colegio")

    @property
    def puede_gestionar_usuarios(self):
        return self.rol in ("admin", "colegio")

    @property
    def rol_nombre(self):
        return dict(ROLES).get(self.rol, self.rol)

    # Flask-Login: un usuario inactivo, o de un colegio inactivo, no puede entrar
    @property
    def is_active(self):
        if not self.activo:
            return False
        return self.institucion is None or self.institucion.activa


class Estudiante(db.Model):
    __tablename__ = "estudiantes"
    # El documento es único dentro de cada colegio
    __table_args__ = (db.UniqueConstraint("institucion_id", "documento", name="uq_estudiante_doc_institucion"),)

    id = db.Column(db.Integer, primary_key=True)
    institucion_id = db.Column(db.Integer, db.ForeignKey("instituciones.id"), nullable=False, index=True)
    tipo_documento = db.Column(db.String(3), nullable=False, default="TI", server_default="TI")
    documento = db.Column(db.String(20), nullable=False, index=True)
    nombres = db.Column(db.Unicode(80), nullable=False)
    apellidos = db.Column(db.Unicode(80), nullable=False)
    fecha_nacimiento = db.Column(db.Date)
    grado = db.Column(db.Integer, nullable=False, index=True)
    grupo = db.Column(db.Unicode(10))
    acudiente = db.Column(db.Unicode(120))
    telefono_acudiente = db.Column(db.String(20))
    email_acudiente = db.Column(db.Unicode(160))
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora, onupdate=ahora)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    # Riesgo vigente (copia del último registro de factores, para filtrar rápido)
    puntaje_actual = db.Column(db.Integer)
    nivel_actual = db.Column(db.String(10), index=True)
    datos_incompletos = db.Column(db.Boolean, nullable=False, default=True)

    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    institucion = db.relationship("Institucion", back_populates="estudiantes")

    @property
    def documento_formateado(self):
        from .documentos import formatear
        return formatear(self.tipo_documento, self.documento)
    registros = db.relationship(
        "RegistroFactores", back_populates="estudiante",
        order_by="desc(RegistroFactores.periodo)", cascade="all, delete-orphan")
    intervenciones = db.relationship(
        "Intervencion", back_populates="estudiante",
        order_by="desc(Intervencion.fecha), desc(Intervencion.id)", cascade="all, delete-orphan")

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}"

    @property
    def municipio(self):
        return self.institucion.municipio if self.institucion else ""

    @property
    def grado_nombre(self):
        g = nombre_grado(self.grado)
        return f"{g} {self.grupo}" if self.grupo else g

    @property
    def registro_vigente(self):
        return self.registros[0] if self.registros else None

    def registro_de(self, periodo):
        return next((r for r in self.registros if r.periodo == periodo), None)

    @property
    def intervenciones_abiertas(self):
        return [i for i in self.intervenciones if i.estado == "abierta"]

    def actualizar_riesgo(self):
        """Sincroniza el riesgo vigente con el último registro de factores."""
        reg = self.registro_vigente
        if reg is None:
            self.puntaje_actual = None
            self.nivel_actual = None
            self.datos_incompletos = True
        else:
            self.puntaje_actual = reg.puntaje
            self.nivel_actual = reg.nivel
            self.datos_incompletos = reg.datos_incompletos


class RegistroFactores(db.Model):
    """Factores de riesgo de un estudiante en un periodo (uno por periodo).

    Asistencia, promedio y reprobadas se CALCULAN de las notas y la asistencia
    que digitan los docentes. Apoyo familiar y reporte activo los registra
    orientación / coordinación.
    """
    __tablename__ = "registros_factores"
    __table_args__ = (db.UniqueConstraint("estudiante_id", "periodo", name="uq_registro_estudiante_periodo"),)

    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("estudiantes.id"), nullable=False, index=True)
    periodo = db.Column(db.String(20), nullable=False)          # ej. 2026-P3
    asistencia_pct = db.Column(db.Numeric(5, 2))                # 0–100
    asignaturas_reprobadas = db.Column(db.Integer)
    promedio = db.Column(db.Numeric(3, 2))                      # 0,00–5,00
    apoyo_familiar = db.Column(db.String(20))                   # adecuado | parcial | insuficiente
    reporte_activo = db.Column(db.Boolean)
    observaciones = db.Column(db.Unicode(4000))

    puntaje = db.Column(db.Integer, nullable=False)
    nivel = db.Column(db.String(10), nullable=False)
    datos_incompletos = db.Column(db.Boolean, nullable=False)

    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))  # NULL = cálculo automático
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora, onupdate=ahora)

    estudiante = db.relationship("Estudiante", back_populates="registros")
    registrado_por = db.relationship("Usuario")

    def resultado(self):
        return calcular_riesgo(
            asistencia_pct=float(self.asistencia_pct) if self.asistencia_pct is not None else None,
            asignaturas_reprobadas=self.asignaturas_reprobadas,
            promedio=float(self.promedio) if self.promedio is not None else None,
            apoyo_familiar=self.apoyo_familiar,
            reporte_activo=self.reporte_activo,
        )

    def recalcular(self):
        r = self.resultado()
        self.puntaje, self.nivel, self.datos_incompletos = r.puntaje, r.nivel, r.datos_incompletos
        return r


TIPOS_INTERVENCION = (
    ("reunion_acudiente", "Reunión con acudiente"),
    ("tutoria", "Tutoría académica"),
    ("orientacion", "Atención en orientación"),
    ("llamada", "Llamada / contacto"),
    ("remision", "Remisión externa"),
    ("plan_mejora", "Plan de mejoramiento"),
    ("otro", "Otro"),
)


class Intervencion(db.Model):
    """Acción de seguimiento realizada con un estudiante (RF-12, RF-13)."""
    __tablename__ = "intervenciones"

    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("estudiantes.id"), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    tipo = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.Unicode(4000), nullable=False)
    compromisos = db.Column(db.Unicode(4000))
    estado = db.Column(db.String(10), nullable=False, default="abierta")  # abierta | cerrada
    responsable_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    estudiante = db.relationship("Estudiante", back_populates="intervenciones")
    responsable = db.relationship("Usuario")

    @property
    def tipo_nombre(self):
        return dict(TIPOS_INTERVENCION).get(self.tipo, self.tipo)


# ---------------------------------------------------------------------------
# Módulo académico: periodos, materias, cursos, notas y asistencia
# ---------------------------------------------------------------------------

class Periodo(db.Model):
    """Periodo académico de un colegio (ej. 2026-P4). Solo uno está activo."""
    __tablename__ = "periodos"
    __table_args__ = (db.UniqueConstraint("institucion_id", "nombre", name="uq_periodo_institucion"),)

    id = db.Column(db.Integer, primary_key=True)
    institucion_id = db.Column(db.Integer, db.ForeignKey("instituciones.id"), nullable=False, index=True)
    nombre = db.Column(db.String(20), nullable=False)          # 2026-P4
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=False)

    institucion = db.relationship("Institucion")


class Materia(db.Model):
    __tablename__ = "materias"
    __table_args__ = (db.UniqueConstraint("institucion_id", "nombre", name="uq_materia_institucion"),)

    id = db.Column(db.Integer, primary_key=True)
    institucion_id = db.Column(db.Integer, db.ForeignKey("instituciones.id"), nullable=False, index=True)
    nombre = db.Column(db.Unicode(80), nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)


class Asignacion(db.Model):
    """Curso: una materia dictada por un docente a un grado y grupo."""
    __tablename__ = "asignaciones"
    __table_args__ = (db.UniqueConstraint("materia_id", "grado", "grupo", name="uq_asignacion_curso"),)

    id = db.Column(db.Integer, primary_key=True)
    institucion_id = db.Column(db.Integer, db.ForeignKey("instituciones.id"), nullable=False, index=True)
    materia_id = db.Column(db.Integer, db.ForeignKey("materias.id"), nullable=False)
    docente_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    grado = db.Column(db.Integer, nullable=False)
    grupo = db.Column(db.Unicode(10), nullable=False, default="")

    materia = db.relationship("Materia")
    docente = db.relationship("Usuario")

    @property
    def curso_nombre(self):
        g = nombre_grado(self.grado)
        return f"{g} {self.grupo}".strip()

    @property
    def nombre(self):
        return f"{self.materia.nombre} · {self.curso_nombre}"

    def estudiantes(self):
        """Estudiantes activos del curso, ordenados por apellido."""
        q = (db.select(Estudiante)
             .filter(Estudiante.institucion_id == self.institucion_id, Estudiante.grado == self.grado,
                     Estudiante.activo == db.true(), db.func.coalesce(Estudiante.grupo, "") == (self.grupo or ""))
             .order_by(Estudiante.apellidos, Estudiante.nombres))
        return db.session.execute(q).scalars().all()


class Actividad(db.Model):
    """Actividad evaluativa con su porcentaje dentro de la materia en el periodo."""
    __tablename__ = "actividades"

    id = db.Column(db.Integer, primary_key=True)
    asignacion_id = db.Column(db.Integer, db.ForeignKey("asignaciones.id"), nullable=False, index=True)
    periodo_id = db.Column(db.Integer, db.ForeignKey("periodos.id"), nullable=False, index=True)
    nombre = db.Column(db.Unicode(80), nullable=False)
    porcentaje = db.Column(db.Integer, nullable=False)        # 1–100
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    asignacion = db.relationship("Asignacion")
    notas = db.relationship("Nota", back_populates="actividad", cascade="all, delete-orphan")


class Nota(db.Model):
    __tablename__ = "notas"
    __table_args__ = (db.UniqueConstraint("actividad_id", "estudiante_id", name="uq_nota_actividad_estudiante"),)

    id = db.Column(db.Integer, primary_key=True)
    actividad_id = db.Column(db.Integer, db.ForeignKey("actividades.id"), nullable=False, index=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("estudiantes.id"), nullable=False, index=True)
    valor = db.Column(db.Numeric(3, 2), nullable=False)        # 0,00–5,00
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora, onupdate=ahora)

    actividad = db.relationship("Actividad", back_populates="notas")


ESTADOS_ASISTENCIA = (
    ("presente", "Presente"),
    ("tarde", "Llegó tarde"),
    ("ausente", "Ausente"),
    ("excusa", "Ausente con excusa"),
)


class SesionClase(db.Model):
    """Una clase dictada en una fecha (sobre ella se toma asistencia)."""
    __tablename__ = "sesiones_clase"
    __table_args__ = (db.UniqueConstraint("asignacion_id", "fecha", name="uq_sesion_asignacion_fecha"),)

    id = db.Column(db.Integer, primary_key=True)
    asignacion_id = db.Column(db.Integer, db.ForeignKey("asignaciones.id"), nullable=False, index=True)
    periodo_id = db.Column(db.Integer, db.ForeignKey("periodos.id"), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False)
    tema = db.Column(db.Unicode(150))

    asignacion = db.relationship("Asignacion")
    asistencias = db.relationship("Asistencia", back_populates="sesion", cascade="all, delete-orphan")


class Asistencia(db.Model):
    __tablename__ = "asistencias"
    __table_args__ = (db.UniqueConstraint("sesion_id", "estudiante_id", name="uq_asistencia_sesion_estudiante"),)

    id = db.Column(db.Integer, primary_key=True)
    sesion_id = db.Column(db.Integer, db.ForeignKey("sesiones_clase.id"), nullable=False, index=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("estudiantes.id"), nullable=False, index=True)
    estado = db.Column(db.String(10), nullable=False, default="presente")

    sesion = db.relationship("SesionClase", back_populates="asistencias")
