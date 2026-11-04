-- Esquema único para los roles Usuario, Administrador y Recepcionista.
-- Compatible con MySQL 8. Ejecutar desde MySQL Workbench.
-- No elimina ni reemplaza datos existentes.
-- Las contraseñas se guardan como hash desde la aplicación.

CREATE DATABASE IF NOT EXISTS hotel_reservas
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hotel_reservas;

CREATE TABLE IF NOT EXISTS roles (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(40) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_roles_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS permissions (
  id INT NOT NULL AUTO_INCREMENT,
  code VARCHAR(40) NOT NULL,
  label VARCHAR(60) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_permissions_code (code),
  UNIQUE KEY uq_permissions_label (label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Una sola tabla de cuentas para los tres roles.
CREATE TABLE IF NOT EXISTS app_users (
  id INT NOT NULL AUTO_INCREMENT,
  username VARCHAR(30) NOT NULL,
  email VARCHAR(160) NOT NULL,
  cedula VARCHAR(16) DEFAULT NULL, -- requerida para las nuevas cuentas de recepción
  password_hash VARCHAR(255) NOT NULL, -- hash seguro; la contraseña original admite 12–30 caracteres en la aplicación
  phone VARCHAR(30) DEFAULT NULL,
  active TINYINT NOT NULL DEFAULT 1,
  role_id INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_app_users_username (username),
  UNIQUE KEY uq_app_users_email (email),
  UNIQUE KEY uq_app_users_cedula (cedula),
  KEY ix_app_users_active (active),
  KEY ix_app_users_role_id (role_id),
  CONSTRAINT ck_app_users_username_length
    CHECK (
      CHAR_LENGTH(TRIM(username)) BETWEEN 5 AND 30
      AND CHAR_LENGTH(username) = CHAR_LENGTH(TRIM(username))
    ),
  CONSTRAINT fk_app_users_role
    FOREIGN KEY (role_id) REFERENCES roles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS guests (
  id INT NOT NULL AUTO_INCREMENT,
  username VARCHAR(80) NOT NULL,
  email VARCHAR(160) NOT NULL,
  phone VARCHAR(30) DEFAULT NULL,
  document_number VARCHAR(40) DEFAULT NULL,
  active TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_guests_email (email),
  KEY ix_guests_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rooms (
  id INT NOT NULL AUTO_INCREMENT,
  number VARCHAR(12) NOT NULL,
  category VARCHAR(40) NOT NULL,
  nightly_rate DECIMAL(10,2) NOT NULL,
  capacity INT NOT NULL DEFAULT 2,
  bed_count INT NOT NULL DEFAULT 1,
  bed_type VARCHAR(40) NOT NULL DEFAULT 'Queen',
  status VARCHAR(24) NOT NULL DEFAULT 'Disponible',
  description TEXT DEFAULT NULL,
  amenities JSON NOT NULL,
  active TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rooms_number (number),
  KEY ix_rooms_category (category),
  KEY ix_rooms_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reservations (
  id INT NOT NULL AUTO_INCREMENT,
  code VARCHAR(24) NOT NULL,
  guest_id INT NOT NULL,
  room_id INT NOT NULL,
  check_in DATE NOT NULL,
  check_out DATE NOT NULL,
  guest_count INT NOT NULL DEFAULT 1,
  total_amount DECIMAL(10,2) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'Confirmada',
  payment_status VARCHAR(24) NOT NULL DEFAULT 'Pagado',
  source VARCHAR(24) NOT NULL DEFAULT 'Administración',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reservations_code (code),
  KEY ix_reservations_status (status),
  KEY ix_reservations_guest_id (guest_id),
  KEY ix_reservations_room_id (room_id),
  CONSTRAINT fk_reservations_guest
    FOREIGN KEY (guest_id) REFERENCES guests (id),
  CONSTRAINT fk_reservations_room
    FOREIGN KEY (room_id) REFERENCES rooms (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payments (
  id INT NOT NULL AUTO_INCREMENT,
  reservation_id INT NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  method VARCHAR(32) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'Pagado',
  reference VARCHAR(80) DEFAULT NULL,
  paid_at DATETIME DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_payments_reservation_id (reservation_id),
  CONSTRAINT fk_payments_reservation
    FOREIGN KEY (reservation_id) REFERENCES reservations (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS room_photos (
  id INT NOT NULL AUTO_INCREMENT,
  room_id INT NOT NULL,
  path VARCHAR(500) NOT NULL,
  caption VARCHAR(120) NOT NULL DEFAULT '',
  position INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY ix_room_photos_room_id (room_id),
  CONSTRAINT fk_room_photos_room
    FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_permissions (
  user_id INT NOT NULL,
  permission_id INT NOT NULL,
  PRIMARY KEY (user_id, permission_id),
  KEY ix_user_permissions_permission_id (permission_id),
  CONSTRAINT fk_user_permissions_user
    FOREIGN KEY (user_id) REFERENCES app_users (id) ON DELETE CASCADE,
  CONSTRAINT fk_user_permissions_permission
    FOREIGN KEY (permission_id) REFERENCES permissions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Catálogo inicial de roles y permisos; las cuentas se crean desde la aplicación.
INSERT INTO roles (name) VALUES
  ('Usuario'),
  ('Administrador'),
  ('Recepcionista')
AS incoming_roles
ON DUPLICATE KEY UPDATE name = incoming_roles.name;

INSERT INTO permissions (code, label) VALUES
  ('reservations', 'Reservas'),
  ('rooms', 'Habitaciones'),
  ('guests', 'Huéspedes'),
  ('payments', 'Pagos')
AS incoming_permissions
ON DUPLICATE KEY UPDATE label = incoming_permissions.label;

-- Comprobación del esquema y sus roles.
SHOW TABLES;
SELECT id, name FROM roles ORDER BY id;



-- Apartados temporales y clave única para evitar pagos duplicados.
CREATE TABLE IF NOT EXISTS booking_holds (
  token VARCHAR(64) NOT NULL PRIMARY KEY,
  user_id INT NOT NULL,
  room_id INT NOT NULL,
  check_in DATE NOT NULL,
  check_out DATE NOT NULL,
  guest_count INT NOT NULL,
  expires_at DATETIME NOT NULL,
  reservation_id INT DEFAULT NULL UNIQUE,
  INDEX ix_booking_holds_user_id (user_id),
  INDEX ix_booking_holds_room_id (room_id),
  INDEX ix_booking_holds_expires_at (expires_at),
  FOREIGN KEY (user_id) REFERENCES app_users(id),
  FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
  FOREIGN KEY (reservation_id) REFERENCES reservations(id)
) ENGINE=InnoDB;
