-- PERMANECE · Esquema PostgreSQL (Neon), generado desde app/models.py.
-- No hace falta ejecutarlo: `flask --app run init-db` crea estas mismas tablas.

CREATE TABLE instituciones (
	id SERIAL NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	codigo_dane VARCHAR(12), 
	municipio VARCHAR(40) NOT NULL, 
	sector VARCHAR(12) NOT NULL, 
	direccion VARCHAR(150), 
	telefono VARCHAR(20), 
	activa BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_instituciones_municipio ON instituciones (municipio);

CREATE TABLE materias (
	id SERIAL NOT NULL, 
	institucion_id INTEGER NOT NULL, 
	nombre VARCHAR(80) NOT NULL, 
	activa BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_materia_institucion UNIQUE (institucion_id, nombre), 
	FOREIGN KEY(institucion_id) REFERENCES instituciones (id)
);

CREATE INDEX ix_materias_institucion_id ON materias (institucion_id);

CREATE TABLE periodos (
	id SERIAL NOT NULL, 
	institucion_id INTEGER NOT NULL, 
	nombre VARCHAR(20) NOT NULL, 
	fecha_inicio DATE NOT NULL, 
	fecha_fin DATE NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_periodo_institucion UNIQUE (institucion_id, nombre), 
	FOREIGN KEY(institucion_id) REFERENCES instituciones (id)
);

CREATE INDEX ix_periodos_institucion_id ON periodos (institucion_id);

CREATE TABLE usuarios (
	id SERIAL NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	email VARCHAR(160) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	rol VARCHAR(20) NOT NULL, 
	institucion_id INTEGER, 
	activo BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(institucion_id) REFERENCES instituciones (id)
);

CREATE UNIQUE INDEX ix_usuarios_email ON usuarios (email);
CREATE INDEX ix_usuarios_institucion_id ON usuarios (institucion_id);

CREATE TABLE asignaciones (
	id SERIAL NOT NULL, 
	institucion_id INTEGER NOT NULL, 
	materia_id INTEGER NOT NULL, 
	docente_id INTEGER NOT NULL, 
	grado INTEGER NOT NULL, 
	grupo VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_asignacion_curso UNIQUE (materia_id, grado, grupo), 
	FOREIGN KEY(institucion_id) REFERENCES instituciones (id), 
	FOREIGN KEY(materia_id) REFERENCES materias (id), 
	FOREIGN KEY(docente_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_asignaciones_docente_id ON asignaciones (docente_id);
CREATE INDEX ix_asignaciones_institucion_id ON asignaciones (institucion_id);

CREATE TABLE estudiantes (
	id SERIAL NOT NULL, 
	institucion_id INTEGER NOT NULL, 
	documento VARCHAR(20) NOT NULL, 
	nombres VARCHAR(80) NOT NULL, 
	apellidos VARCHAR(80) NOT NULL, 
	fecha_nacimiento DATE, 
	grado INTEGER NOT NULL, 
	grupo VARCHAR(10), 
	acudiente VARCHAR(120), 
	telefono_acudiente VARCHAR(20), 
	email_acudiente VARCHAR(160), 
	activo BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	creado_por_id INTEGER, 
	puntaje_actual INTEGER, 
	nivel_actual VARCHAR(10), 
	datos_incompletos BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_estudiante_doc_institucion UNIQUE (institucion_id, documento), 
	FOREIGN KEY(institucion_id) REFERENCES instituciones (id), 
	FOREIGN KEY(creado_por_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_estudiantes_documento ON estudiantes (documento);
CREATE INDEX ix_estudiantes_grado ON estudiantes (grado);
CREATE INDEX ix_estudiantes_institucion_id ON estudiantes (institucion_id);
CREATE INDEX ix_estudiantes_nivel_actual ON estudiantes (nivel_actual);

CREATE TABLE actividades (
	id SERIAL NOT NULL, 
	asignacion_id INTEGER NOT NULL, 
	periodo_id INTEGER NOT NULL, 
	nombre VARCHAR(80) NOT NULL, 
	porcentaje INTEGER NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignacion_id) REFERENCES asignaciones (id), 
	FOREIGN KEY(periodo_id) REFERENCES periodos (id)
);

CREATE INDEX ix_actividades_asignacion_id ON actividades (asignacion_id);
CREATE INDEX ix_actividades_periodo_id ON actividades (periodo_id);

CREATE TABLE intervenciones (
	id SERIAL NOT NULL, 
	estudiante_id INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	tipo VARCHAR(30) NOT NULL, 
	descripcion VARCHAR(4000) NOT NULL, 
	compromisos VARCHAR(4000), 
	estado VARCHAR(10) NOT NULL, 
	responsable_id INTEGER NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(estudiante_id) REFERENCES estudiantes (id), 
	FOREIGN KEY(responsable_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_intervenciones_estudiante_id ON intervenciones (estudiante_id);

CREATE TABLE registros_factores (
	id SERIAL NOT NULL, 
	estudiante_id INTEGER NOT NULL, 
	periodo VARCHAR(20) NOT NULL, 
	asistencia_pct NUMERIC(5, 2), 
	asignaturas_reprobadas INTEGER, 
	promedio NUMERIC(3, 2), 
	apoyo_familiar VARCHAR(20), 
	reporte_activo BOOLEAN, 
	observaciones VARCHAR(4000), 
	puntaje INTEGER NOT NULL, 
	nivel VARCHAR(10) NOT NULL, 
	datos_incompletos BOOLEAN NOT NULL, 
	registrado_por_id INTEGER, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_registro_estudiante_periodo UNIQUE (estudiante_id, periodo), 
	FOREIGN KEY(estudiante_id) REFERENCES estudiantes (id), 
	FOREIGN KEY(registrado_por_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_registros_factores_estudiante_id ON registros_factores (estudiante_id);

CREATE TABLE sesiones_clase (
	id SERIAL NOT NULL, 
	asignacion_id INTEGER NOT NULL, 
	periodo_id INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	tema VARCHAR(150), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_sesion_asignacion_fecha UNIQUE (asignacion_id, fecha), 
	FOREIGN KEY(asignacion_id) REFERENCES asignaciones (id), 
	FOREIGN KEY(periodo_id) REFERENCES periodos (id)
);

CREATE INDEX ix_sesiones_clase_asignacion_id ON sesiones_clase (asignacion_id);
CREATE INDEX ix_sesiones_clase_periodo_id ON sesiones_clase (periodo_id);

CREATE TABLE asistencias (
	id SERIAL NOT NULL, 
	sesion_id INTEGER NOT NULL, 
	estudiante_id INTEGER NOT NULL, 
	estado VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_asistencia_sesion_estudiante UNIQUE (sesion_id, estudiante_id), 
	FOREIGN KEY(sesion_id) REFERENCES sesiones_clase (id), 
	FOREIGN KEY(estudiante_id) REFERENCES estudiantes (id)
);

CREATE INDEX ix_asistencias_estudiante_id ON asistencias (estudiante_id);
CREATE INDEX ix_asistencias_sesion_id ON asistencias (sesion_id);

CREATE TABLE notas (
	id SERIAL NOT NULL, 
	actividad_id INTEGER NOT NULL, 
	estudiante_id INTEGER NOT NULL, 
	valor NUMERIC(3, 2) NOT NULL, 
	actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_nota_actividad_estudiante UNIQUE (actividad_id, estudiante_id), 
	FOREIGN KEY(actividad_id) REFERENCES actividades (id), 
	FOREIGN KEY(estudiante_id) REFERENCES estudiantes (id)
);

CREATE INDEX ix_notas_actividad_id ON notas (actividad_id);
CREATE INDEX ix_notas_estudiante_id ON notas (estudiante_id);

