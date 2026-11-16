"""Formularios con validación en servidor (RF-15, RNF-06).

Flask-WTF aporta además protección CSRF en todos los POST.
"""
from datetime import date

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, DecimalField, EmailField,
                     IntegerField, PasswordField, SelectField, StringField,
                     SubmitField, TextAreaField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length,
                                NumberRange, Optional, Regexp, ValidationError)

from .models import (GRADOS, MUNICIPIOS_SABANA_CENTRO, ROLES, SECTORES,
                     TIPOS_INTERVENCION, nombre_grado)
from .riesgo import APOYO_OPCIONES

REQ = "Este campo es obligatorio."


class DecimalComa(DecimalField):
    """Acepta coma o punto decimal (3,5 o 3.5)."""
    def process_formdata(self, valuelist):
        if valuelist:
            valuelist = [valuelist[0].replace(",", ".").strip()]
        super().process_formdata(valuelist)


class LoginForm(FlaskForm):
    email = EmailField("Correo", validators=[DataRequired(REQ), Email("Correo no válido.")])
    password = PasswordField("Contraseña", validators=[DataRequired(REQ)])
    recordar = BooleanField("Mantener la sesión iniciada")
    submit = SubmitField("Ingresar")


class OlvideForm(FlaskForm):
    email = EmailField("Correo", validators=[DataRequired(REQ), Email("Correo no válido.")])
    submit = SubmitField("Enviar enlace")


class DefinirContrasenaForm(FlaskForm):
    password = PasswordField("Nueva contraseña", validators=[DataRequired(REQ), Length(min=8, message="Mínimo 8 caracteres.")])
    confirmar = PasswordField("Confirmar contraseña", validators=[DataRequired(REQ), EqualTo("password", "Las contraseñas no coinciden.")])
    submit = SubmitField("Guardar contraseña")


def _no_futura(form, field):
    if field.data and field.data > date.today():
        raise ValidationError("La fecha no puede ser futura.")


class EstudianteForm(FlaskForm):
    documento = StringField("Documento de identidad", validators=[
        DataRequired(REQ), Length(min=5, max=20),
        Regexp(r"^[0-9A-Za-z\-]+$", message="Solo números, letras y guiones.")])
    nombres = StringField("Nombres", validators=[DataRequired(REQ), Length(max=80)])
    apellidos = StringField("Apellidos", validators=[DataRequired(REQ), Length(max=80)])
    fecha_nacimiento = DateField("Fecha de nacimiento", validators=[Optional(), _no_futura])
    grado = SelectField("Grado", coerce=int,
                        choices=[(g, nombre_grado(g)) for g in GRADOS])  # valida que sea una opción
    grupo = StringField("Grupo / curso", validators=[Optional(), Length(max=10)],
                        description="Ej.: A, 01, 902")
    # Solo lo ve el administrador; para un colegio se asigna automáticamente.
    institucion_id = SelectField("Colegio", coerce=int, choices=[], validate_choice=False)
    acudiente = StringField("Nombre del acudiente", validators=[Optional(), Length(max=120)])
    telefono_acudiente = StringField("Teléfono del acudiente", validators=[
        Optional(), Regexp(r"^[0-9+\s\-]{7,20}$", message="Teléfono no válido.")])
    email_acudiente = EmailField("Correo del acudiente", validators=[
        Optional(), Email("Correo no válido."), Length(max=160)],
        description="Se usa para alertas de riesgo y para compartir intervenciones.")
    submit = SubmitField("Guardar")

    def validate_fecha_nacimiento(self, field):
        if field.data and (date.today().year - field.data.year) > 25:
            raise ValidationError("Revisa la fecha: el estudiante tendría más de 25 años.")


class FactoresForm(FlaskForm):
    """Factores que NO salen de notas ni asistencia: los registra orientación/coordinación."""
    apoyo_familiar = SelectField("Apoyo familiar", choices=[("", "Sin registrar")] + list(APOYO_OPCIONES),
                                 validators=[Optional()])
    reporte_activo = SelectField("Reporte de seguimiento activo",
                                 choices=[("", "Sin registrar"), ("1", "Sí"), ("0", "No")],
                                 validators=[Optional()])
    observaciones = TextAreaField("Observaciones", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Guardar y recalcular riesgo")


class IntervencionForm(FlaskForm):
    fecha = DateField("Fecha", default=date.today, validators=[DataRequired(REQ), _no_futura])
    tipo = SelectField("Tipo de intervención", choices=[("", "Selecciona…")] + list(TIPOS_INTERVENCION),
                       validators=[DataRequired(REQ)])
    descripcion = TextAreaField("Descripción", validators=[DataRequired(REQ), Length(min=10, max=4000,
                                message="Describe la intervención (mínimo 10 caracteres).")])
    compromisos = TextAreaField("Compromisos / próximos pasos", validators=[Optional(), Length(max=2000)])
    estado = SelectField("Estado", choices=[("abierta", "Abierta"), ("cerrada", "Cerrada")])
    notificar_acudiente = BooleanField("Enviar esta intervención por correo al acudiente")
    submit = SubmitField("Registrar intervención")


class InstitucionForm(FlaskForm):
    nombre = StringField("Nombre del colegio", validators=[DataRequired(REQ), Length(max=150)])
    codigo_dane = StringField("Código DANE", validators=[
        Optional(), Regexp(r"^\d{12}$", message="El código DANE tiene 12 dígitos.")])
    municipio = SelectField("Municipio", choices=[("", "Selecciona…")] +
                            [(m, m) for m in MUNICIPIOS_SABANA_CENTRO],
                            validators=[DataRequired(REQ)])
    sector = SelectField("Sector", choices=list(SECTORES))
    direccion = StringField("Dirección", validators=[Optional(), Length(max=150)])
    telefono = StringField("Teléfono", validators=[
        Optional(), Regexp(r"^[0-9+\s\-]{7,20}$", message="Teléfono no válido.")])
    activa = BooleanField("Colegio activo", default=True)
    # Credenciales de acceso del colegio (solo al crear)
    usuario_nombre = StringField("Nombre del responsable", validators=[Optional(), Length(max=120)],
                                 description="Ej.: coordinador académico o rector")
    usuario_email = EmailField("Correo de acceso", validators=[Optional(), Email("Correo no válido."), Length(max=160)])
    usuario_password = PasswordField("Contraseña inicial (opcional)", validators=[Optional(), Length(min=8, message="Mínimo 8 caracteres.")])
    submit = SubmitField("Guardar")


class UsuarioForm(FlaskForm):
    nombre = StringField("Nombre completo", validators=[DataRequired(REQ), Length(max=120)])
    email = EmailField("Correo", validators=[DataRequired(REQ), Email("Correo no válido."), Length(max=160)])
    rol = SelectField("Rol", choices=list(ROLES))
    institucion_id = SelectField("Colegio", coerce=int, choices=[], validate_choice=False)
    activo = BooleanField("Usuario activo", default=True)
    password = PasswordField("Contraseña", validators=[Optional(), Length(min=8, message="Mínimo 8 caracteres.")])
    confirmar = PasswordField("Confirmar contraseña", validators=[EqualTo("password", "Las contraseñas no coinciden.")])
    submit = SubmitField("Guardar")


# ---------------- Módulo académico ----------------

class PeriodoForm(FlaskForm):
    nombre = StringField("Periodo", validators=[
        DataRequired(REQ), Regexp(r"^\d{4}-P[1-4]$", message="Usa el formato AAAA-P# (ej. 2026-P4).")])
    fecha_inicio = DateField("Inicio", validators=[DataRequired(REQ)])
    fecha_fin = DateField("Fin", validators=[DataRequired(REQ)])
    activo = BooleanField("Marcar como periodo activo", default=True)
    submit = SubmitField("Crear periodo")

    def validate_fecha_fin(self, field):
        if self.fecha_inicio.data and field.data and field.data <= self.fecha_inicio.data:
            raise ValidationError("La fecha de fin debe ser posterior al inicio.")


class MateriaForm(FlaskForm):
    nombre = StringField("Nombre de la materia", validators=[DataRequired(REQ), Length(max=80)])
    submit = SubmitField("Agregar materia")


class AsignacionForm(FlaskForm):
    materia_id = SelectField("Materia", coerce=int, choices=[], validate_choice=False)
    docente_id = SelectField("Docente", coerce=int, choices=[], validate_choice=False)
    grado = SelectField("Grado", coerce=int, choices=[(g, nombre_grado(g)) for g in GRADOS])
    grupo = StringField("Grupo", validators=[Optional(), Length(max=10)], description="Ej.: A, 01, 902")
    submit = SubmitField("Asignar curso")


class ActividadForm(FlaskForm):
    nombre = StringField("Actividad", validators=[DataRequired(REQ), Length(max=80)],
                         description="Ej.: Quiz 1, Taller, Examen")
    porcentaje = IntegerField("Porcentaje (%)", validators=[
        DataRequired(REQ), NumberRange(1, 100, "Entre 1 y 100.")])
    submit = SubmitField("Agregar actividad")


class SesionForm(FlaskForm):
    fecha = DateField("Fecha de la clase", default=date.today, validators=[DataRequired(REQ), _no_futura])
    tema = StringField("Tema (opcional)", validators=[Optional(), Length(max=150)])
    submit = SubmitField("Guardar asistencia")
