-- Esquema único de Hotel Las Colinas para Aiven defaultdb.
-- Compatible con MySQL 8. Ejecutar sobre defaultdb desde MySQL Workbench.
-- No elimina ni reemplaza datos existentes.
-- Las contraseñas se guardan como hash desde la aplicación.

USE defaultdb;

CREATE TABLE IF NOT EXISTS roles (
  id INT NOT NULL AUTO_INCREMENT,
  nombre VARCHAR(40) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_roles_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS permisos (
  id INT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(40) NOT NULL,
  etiqueta VARCHAR(60) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_permisos_codigo (codigo),
  UNIQUE KEY uq_permisos_etiqueta (etiqueta)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Una sola tabla de cuentas para los tres roles.
CREATE TABLE IF NOT EXISTS usuarios_app (
  id INT NOT NULL AUTO_INCREMENT,
  nombre_usuario VARCHAR(30) NOT NULL,
  correo VARCHAR(160) NOT NULL,
  cedula VARCHAR(16) DEFAULT NULL, -- requerida para las nuevas cuentas de recepción
  hash_contrasena VARCHAR(255) NOT NULL, -- hash seguro; la contraseña original admite 12–30 caracteres en la aplicación
  telefono VARCHAR(30) DEFAULT NULL,
  activo TINYINT NOT NULL DEFAULT 1,
  rol_id INT NOT NULL,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_usuarios_app_nombre_usuario (nombre_usuario),
  UNIQUE KEY uq_usuarios_app_correo (correo),
  UNIQUE KEY uq_usuarios_app_cedula (cedula),
  KEY ix_usuarios_app_activo (activo),
  KEY ix_usuarios_app_rol_id (rol_id),
  CONSTRAINT ck_usuarios_app_nombre_usuario_longitud
    CHECK (
      CHAR_LENGTH(TRIM(nombre_usuario)) BETWEEN 5 AND 30
      AND CHAR_LENGTH(nombre_usuario) = CHAR_LENGTH(TRIM(nombre_usuario))
    ),
  CONSTRAINT fk_usuarios_app_roles
    FOREIGN KEY (rol_id) REFERENCES roles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS huespedes (
  id INT NOT NULL AUTO_INCREMENT,
  nombre VARCHAR(80) NOT NULL,
  correo VARCHAR(160) NOT NULL,
  telefono VARCHAR(30) DEFAULT NULL,
  numero_documento VARCHAR(40) DEFAULT NULL,
  activo TINYINT NOT NULL DEFAULT 1,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_huespedes_correo (correo),
  KEY ix_huespedes_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS habitaciones (
  id INT NOT NULL AUTO_INCREMENT,
  numero VARCHAR(12) NOT NULL,
  categoria VARCHAR(40) NOT NULL,
  precio_noche DECIMAL(10,2) NOT NULL,
  capacidad INT NOT NULL DEFAULT 2,
  cantidad_camas INT NOT NULL DEFAULT 1,
  tipo_cama VARCHAR(40) NOT NULL DEFAULT 'Queen',
  estado VARCHAR(24) NOT NULL DEFAULT 'Disponible',
  descripcion TEXT DEFAULT NULL,
  comodidades JSON NOT NULL,
  activo TINYINT NOT NULL DEFAULT 1,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_habitaciones_numero (numero),
  KEY ix_habitaciones_categoria (categoria),
  KEY ix_habitaciones_estado (estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reservas (
  id INT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(24) NOT NULL,
  huesped_id INT NOT NULL,
  habitacion_id INT NOT NULL,
  fecha_entrada DATE NOT NULL,
  fecha_salida DATE NOT NULL,
  cantidad_huespedes INT NOT NULL DEFAULT 1,
  importe_total DECIMAL(10,2) NOT NULL,
  estado VARCHAR(24) NOT NULL DEFAULT 'Confirmada',
  estado_pago VARCHAR(24) NOT NULL DEFAULT 'Pagado',
  origen VARCHAR(24) NOT NULL DEFAULT 'Administración',
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reservas_codigo (codigo),
  KEY ix_reservas_estado (estado),
  KEY ix_reservas_huesped_id (huesped_id),
  KEY ix_reservas_habitacion_id (habitacion_id),
  CONSTRAINT fk_reservas_huespedes
    FOREIGN KEY (huesped_id) REFERENCES huespedes (id),
  CONSTRAINT fk_reservas_habitaciones
    FOREIGN KEY (habitacion_id) REFERENCES habitaciones (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pagos (
  id INT NOT NULL AUTO_INCREMENT,
  reserva_id INT NOT NULL,
  importe DECIMAL(10,2) NOT NULL,
  metodo VARCHAR(32) NOT NULL,
  estado VARCHAR(24) NOT NULL DEFAULT 'Pagado',
  referencia VARCHAR(80) DEFAULT NULL,
  pagado_en DATETIME DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_pagos_reserva_id (reserva_id),
  CONSTRAINT fk_pagos_reservas
    FOREIGN KEY (reserva_id) REFERENCES reservas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fotos_habitacion (
  id INT NOT NULL AUTO_INCREMENT,
  habitacion_id INT NOT NULL,
  ruta VARCHAR(500) NOT NULL,
  leyenda VARCHAR(120) NOT NULL DEFAULT '',
  posicion INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY ix_fotos_habitacion_id (habitacion_id),
  CONSTRAINT fk_fotos_habitacion_habitaciones
    FOREIGN KEY (habitacion_id) REFERENCES habitaciones (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usuarios_permisos (
  usuario_id INT NOT NULL,
  permiso_id INT NOT NULL,
  PRIMARY KEY (usuario_id, permiso_id),
  KEY ix_usuarios_permisos_permiso_id (permiso_id),
  CONSTRAINT fk_usuarios_permisos_usuarios_app
    FOREIGN KEY (usuario_id) REFERENCES usuarios_app (id) ON DELETE CASCADE,
  CONSTRAINT fk_usuarios_permisos_permisos
    FOREIGN KEY (permiso_id) REFERENCES permisos (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Catálogo inicial de roles y permisos; las cuentas se crean desde la aplicación.
INSERT INTO roles (nombre) VALUES
  ('Usuario'),
  ('Administrador'),
  ('Recepcionista')
AS incoming_roles
ON DUPLICATE KEY UPDATE nombre = incoming_roles.nombre;

INSERT INTO permisos (codigo, etiqueta) VALUES
  ('reservas', 'Reservas'),
  ('habitaciones', 'Habitaciones'),
  ('huespedes', 'Huéspedes'),
  ('pagos', 'Pagos')
AS incoming_permissions
ON DUPLICATE KEY UPDATE etiqueta = incoming_permissions.etiqueta;

-- Comprobación del esquema y sus roles.
SHOW TABLES;
SELECT id, nombre FROM roles ORDER BY id;



-- Apartados temporales y clave única para evitar pagos duplicados.
CREATE TABLE IF NOT EXISTS bloqueos_reserva (
  token VARCHAR(64) NOT NULL PRIMARY KEY,
  usuario_id INT NOT NULL,
  habitacion_id INT NOT NULL,
  fecha_entrada DATE NOT NULL,
  fecha_salida DATE NOT NULL,
  cantidad_huespedes INT NOT NULL,
  expira_en DATETIME NOT NULL,
  reserva_id INT DEFAULT NULL UNIQUE,
  INDEX ix_bloqueos_reserva_usuario_id (usuario_id),
  INDEX ix_bloqueos_reserva_habitacion_id (habitacion_id),
  INDEX ix_bloqueos_reserva_expira_en (expira_en),
  CONSTRAINT fk_bloqueos_reserva_usuarios_app FOREIGN KEY (usuario_id) REFERENCES usuarios_app(id),
  CONSTRAINT fk_bloqueos_reserva_habitaciones FOREIGN KEY (habitacion_id) REFERENCES habitaciones(id) ON DELETE CASCADE,
  CONSTRAINT fk_bloqueos_reserva_reservas FOREIGN KEY (reserva_id) REFERENCES reservas(id)
) ENGINE=InnoDB;

-- Fotografías persistentes para compartir entre web, administración y recepción.
CREATE TABLE IF NOT EXISTS archivos_foto_habitacion (
  foto_id INT NOT NULL PRIMARY KEY,
  contenido MEDIUMBLOB NOT NULL,
  tipo_mime VARCHAR(80) NOT NULL,
  resumen_sha256 VARCHAR(64) NOT NULL,
  CONSTRAINT fk_archivos_foto_habitacion_fotos
    FOREIGN KEY (foto_id) REFERENCES fotos_habitacion (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
