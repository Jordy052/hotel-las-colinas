-- Migración de identificadores en Aiven defaultdb.
-- Ejecutar UNA SOLA VEZ en MySQL Workbench conectado a Aiven.
-- Renombra tablas/columnas sin copiar ni borrar sus filas o IDs.
-- Detén temporalmente la API antes de ejecutar. Conserva un respaldo previo.

USE defaultdb;

-- La restricción de validación hace referencia al nombre inglés de la columna.
-- Se quita antes del renombre y se vuelve a crear en español al final.
DROP PROCEDURE IF EXISTS preparar_renombre_esquema;
DELIMITER $$
CREATE PROCEDURE preparar_renombre_esquema()
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'app_users'
      AND constraint_name = 'ck_app_users_username_length'
      AND constraint_type = 'CHECK'
  ) THEN
    ALTER TABLE app_users DROP CHECK ck_app_users_username_length;
  END IF;
END$$
DELIMITER ;
CALL preparar_renombre_esquema();
DROP PROCEDURE preparar_renombre_esquema;

RENAME TABLE
  permissions TO permisos,
  app_users TO usuarios_app,
  guests TO huespedes,
  rooms TO habitaciones,
  reservations TO reservas,
  payments TO pagos,
  room_photos TO fotos_habitacion,
  room_photo_assets TO archivos_foto_habitacion,
  user_permissions TO usuarios_permisos,
  booking_holds TO bloqueos_reserva;

ALTER TABLE roles RENAME COLUMN name TO nombre;

ALTER TABLE permisos
  RENAME COLUMN code TO codigo,
  RENAME COLUMN label TO etiqueta;

ALTER TABLE usuarios_app
  RENAME COLUMN username TO nombre_usuario,
  RENAME COLUMN email TO correo,
  RENAME COLUMN password_hash TO hash_contrasena,
  RENAME COLUMN phone TO telefono,
  RENAME COLUMN active TO activo,
  RENAME COLUMN role_id TO rol_id,
  RENAME COLUMN created_at TO creado_en,
  RENAME COLUMN updated_at TO actualizado_en;

ALTER TABLE huespedes
  RENAME COLUMN username TO nombre,
  RENAME COLUMN email TO correo,
  RENAME COLUMN phone TO telefono,
  RENAME COLUMN document_number TO numero_documento,
  RENAME COLUMN active TO activo,
  RENAME COLUMN created_at TO creado_en;

ALTER TABLE habitaciones
  RENAME COLUMN number TO numero,
  RENAME COLUMN category TO categoria,
  RENAME COLUMN nightly_rate TO precio_noche,
  RENAME COLUMN capacity TO capacidad,
  RENAME COLUMN bed_count TO cantidad_camas,
  RENAME COLUMN bed_type TO tipo_cama,
  RENAME COLUMN status TO estado,
  RENAME COLUMN description TO descripcion,
  RENAME COLUMN amenities TO comodidades,
  RENAME COLUMN active TO activo,
  RENAME COLUMN created_at TO creado_en;

ALTER TABLE reservas
  RENAME COLUMN code TO codigo,
  RENAME COLUMN guest_id TO huesped_id,
  RENAME COLUMN room_id TO habitacion_id,
  RENAME COLUMN check_in TO fecha_entrada,
  RENAME COLUMN check_out TO fecha_salida,
  RENAME COLUMN guest_count TO cantidad_huespedes,
  RENAME COLUMN total_amount TO importe_total,
  RENAME COLUMN status TO estado,
  RENAME COLUMN payment_status TO estado_pago,
  RENAME COLUMN source TO origen,
  RENAME COLUMN created_at TO creado_en;

ALTER TABLE pagos
  RENAME COLUMN reservation_id TO reserva_id,
  RENAME COLUMN amount TO importe,
  RENAME COLUMN method TO metodo,
  RENAME COLUMN status TO estado,
  RENAME COLUMN reference TO referencia,
  RENAME COLUMN paid_at TO pagado_en;

ALTER TABLE fotos_habitacion
  RENAME COLUMN room_id TO habitacion_id,
  RENAME COLUMN path TO ruta,
  RENAME COLUMN caption TO leyenda,
  RENAME COLUMN position TO posicion;

ALTER TABLE archivos_foto_habitacion
  RENAME COLUMN photo_id TO foto_id,
  RENAME COLUMN content TO contenido,
  RENAME COLUMN mime_type TO tipo_mime,
  RENAME COLUMN sha256 TO resumen_sha256;

ALTER TABLE usuarios_permisos
  RENAME COLUMN user_id TO usuario_id,
  RENAME COLUMN permission_id TO permiso_id;

ALTER TABLE bloqueos_reserva
  RENAME COLUMN user_id TO usuario_id,
  RENAME COLUMN room_id TO habitacion_id,
  RENAME COLUMN check_in TO fecha_entrada,
  RENAME COLUMN check_out TO fecha_salida,
  RENAME COLUMN guest_count TO cantidad_huespedes,
  RENAME COLUMN expires_at TO expira_en,
  RENAME COLUMN reservation_id TO reserva_id;

ALTER TABLE usuarios_app
  ADD CONSTRAINT ck_usuarios_app_nombre_usuario_longitud
  CHECK (
    CHAR_LENGTH(TRIM(nombre_usuario)) BETWEEN 5 AND 30
    AND CHAR_LENGTH(nombre_usuario) = CHAR_LENGTH(TRIM(nombre_usuario))
  );

-- Traduce los códigos internos de permisos. Si coexistieran códigos en ambos idiomas,
-- combina primero las asignaciones y elimina únicamente la fila de permiso duplicada.
INSERT IGNORE INTO usuarios_permisos (usuario_id, permiso_id)
SELECT origen.usuario_id, destino.id
FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'reservas'
WHERE permiso_origen.codigo = 'reservations';
DELETE origen FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'reservas'
WHERE permiso_origen.codigo = 'reservations';
DELETE permiso_origen FROM permisos AS permiso_origen
JOIN permisos AS destino ON destino.codigo = 'reservas'
WHERE permiso_origen.codigo = 'reservations';
UPDATE permisos AS origen
LEFT JOIN permisos AS destino ON destino.codigo = 'reservas'
SET origen.codigo = 'reservas'
WHERE origen.codigo = 'reservations' AND destino.id IS NULL;

INSERT IGNORE INTO usuarios_permisos (usuario_id, permiso_id)
SELECT origen.usuario_id, destino.id
FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'habitaciones'
WHERE permiso_origen.codigo = 'rooms';
DELETE origen FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'habitaciones'
WHERE permiso_origen.codigo = 'rooms';
DELETE permiso_origen FROM permisos AS permiso_origen
JOIN permisos AS destino ON destino.codigo = 'habitaciones'
WHERE permiso_origen.codigo = 'rooms';
UPDATE permisos AS origen
LEFT JOIN permisos AS destino ON destino.codigo = 'habitaciones'
SET origen.codigo = 'habitaciones'
WHERE origen.codigo = 'rooms' AND destino.id IS NULL;

INSERT IGNORE INTO usuarios_permisos (usuario_id, permiso_id)
SELECT origen.usuario_id, destino.id
FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'huespedes'
WHERE permiso_origen.codigo = 'guests';
DELETE origen FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'huespedes'
WHERE permiso_origen.codigo = 'guests';
DELETE permiso_origen FROM permisos AS permiso_origen
JOIN permisos AS destino ON destino.codigo = 'huespedes'
WHERE permiso_origen.codigo = 'guests';
UPDATE permisos AS origen
LEFT JOIN permisos AS destino ON destino.codigo = 'huespedes'
SET origen.codigo = 'huespedes'
WHERE origen.codigo = 'guests' AND destino.id IS NULL;

INSERT IGNORE INTO usuarios_permisos (usuario_id, permiso_id)
SELECT origen.usuario_id, destino.id
FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'pagos'
WHERE permiso_origen.codigo = 'payments';
DELETE origen FROM usuarios_permisos AS origen
JOIN permisos AS permiso_origen ON permiso_origen.id = origen.permiso_id
JOIN permisos AS destino ON destino.codigo = 'pagos'
WHERE permiso_origen.codigo = 'payments';
DELETE permiso_origen FROM permisos AS permiso_origen
JOIN permisos AS destino ON destino.codigo = 'pagos'
WHERE permiso_origen.codigo = 'payments';
UPDATE permisos AS origen
LEFT JOIN permisos AS destino ON destino.codigo = 'pagos'
SET origen.codigo = 'pagos'
WHERE origen.codigo = 'payments' AND destino.id IS NULL;

-- Comprueba que están las tablas traducidas y sus relaciones.
SHOW TABLES;
SHOW COLUMNS FROM usuarios_app;
SHOW COLUMNS FROM reservas;
SHOW COLUMNS FROM pagos;

-- Traduce también los nombres de índices y relaciones para que Workbench
-- muestre el esquema completo en español. Estas operaciones conservan filas.
ALTER TABLE roles RENAME INDEX uq_roles_name TO uq_roles_nombre;
ALTER TABLE permisos
  RENAME INDEX uq_permissions_code TO uq_permisos_codigo,
  RENAME INDEX uq_permissions_label TO uq_permisos_etiqueta;
-- El esquema inicial puede o no traer una llave única para username.
DROP PROCEDURE IF EXISTS traducir_indice_nombre_usuario;
DELIMITER $$
CREATE PROCEDURE traducir_indice_nombre_usuario()
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'usuarios_app'
      AND index_name = 'uq_app_users_username'
  ) THEN
    ALTER TABLE usuarios_app
      RENAME INDEX uq_app_users_username TO uq_usuarios_app_nombre_usuario;
  ELSEIF NOT EXISTS (
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'usuarios_app'
      AND index_name = 'uq_usuarios_app_nombre_usuario'
  ) THEN
    ALTER TABLE usuarios_app
      ADD UNIQUE KEY uq_usuarios_app_nombre_usuario (nombre_usuario);
  END IF;
END$$
DELIMITER ;
CALL traducir_indice_nombre_usuario();
DROP PROCEDURE traducir_indice_nombre_usuario;

ALTER TABLE usuarios_app
  RENAME INDEX uq_app_users_email TO uq_usuarios_app_correo,
  RENAME INDEX uq_app_users_cedula TO uq_usuarios_app_cedula,
  RENAME INDEX ix_app_users_active TO ix_usuarios_app_activo,
  RENAME INDEX ix_app_users_role_id TO ix_usuarios_app_rol_id;
ALTER TABLE huespedes
  RENAME INDEX uq_guests_email TO uq_huespedes_correo,
  RENAME INDEX ix_guests_username TO ix_huespedes_nombre;
ALTER TABLE habitaciones
  RENAME INDEX uq_rooms_number TO uq_habitaciones_numero,
  RENAME INDEX ix_rooms_category TO ix_habitaciones_categoria,
  RENAME INDEX ix_rooms_status TO ix_habitaciones_estado;
ALTER TABLE reservas
  RENAME INDEX uq_reservations_code TO uq_reservas_codigo,
  RENAME INDEX ix_reservations_status TO ix_reservas_estado,
  RENAME INDEX ix_reservations_guest_id TO ix_reservas_huesped_id,
  RENAME INDEX ix_reservations_room_id TO ix_reservas_habitacion_id;
ALTER TABLE pagos RENAME INDEX ix_payments_reservation_id TO ix_pagos_reserva_id;
ALTER TABLE fotos_habitacion RENAME INDEX ix_room_photos_room_id TO ix_fotos_habitacion_id;
ALTER TABLE usuarios_permisos RENAME INDEX ix_user_permissions_permission_id TO ix_usuarios_permisos_permiso_id;
ALTER TABLE bloqueos_reserva
  RENAME INDEX ix_booking_holds_user_id TO ix_bloqueos_reserva_usuario_id,
  RENAME INDEX ix_booking_holds_room_id TO ix_bloqueos_reserva_habitacion_id,
  RENAME INDEX ix_booking_holds_expires_at TO ix_bloqueos_reserva_expira_en,
  RENAME INDEX reservation_id TO uq_bloqueos_reserva_reserva_id;

ALTER TABLE usuarios_app DROP FOREIGN KEY fk_app_users_role;
ALTER TABLE usuarios_app ADD CONSTRAINT fk_usuarios_app_roles
  FOREIGN KEY (rol_id) REFERENCES roles (id);
ALTER TABLE reservas
  DROP FOREIGN KEY fk_reservations_guest,
  DROP FOREIGN KEY fk_reservations_room;
ALTER TABLE reservas
  ADD CONSTRAINT fk_reservas_huespedes FOREIGN KEY (huesped_id) REFERENCES huespedes (id),
  ADD CONSTRAINT fk_reservas_habitaciones FOREIGN KEY (habitacion_id) REFERENCES habitaciones (id);
ALTER TABLE pagos DROP FOREIGN KEY fk_payments_reservation;
ALTER TABLE pagos ADD CONSTRAINT fk_pagos_reservas
  FOREIGN KEY (reserva_id) REFERENCES reservas (id) ON DELETE CASCADE;
ALTER TABLE fotos_habitacion DROP FOREIGN KEY fk_room_photos_room;
ALTER TABLE fotos_habitacion ADD CONSTRAINT fk_fotos_habitacion_habitaciones
  FOREIGN KEY (habitacion_id) REFERENCES habitaciones (id) ON DELETE CASCADE;
ALTER TABLE usuarios_permisos
  DROP FOREIGN KEY fk_user_permissions_user,
  DROP FOREIGN KEY fk_user_permissions_permission;
ALTER TABLE usuarios_permisos
  ADD CONSTRAINT fk_usuarios_permisos_usuarios_app
    FOREIGN KEY (usuario_id) REFERENCES usuarios_app (id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_usuarios_permisos_permisos
    FOREIGN KEY (permiso_id) REFERENCES permisos (id) ON DELETE CASCADE;
ALTER TABLE bloqueos_reserva
  DROP FOREIGN KEY bloqueos_reserva_ibfk_1,
  DROP FOREIGN KEY bloqueos_reserva_ibfk_2,
  DROP FOREIGN KEY bloqueos_reserva_ibfk_3;
ALTER TABLE bloqueos_reserva
  ADD CONSTRAINT fk_bloqueos_reserva_usuarios_app
    FOREIGN KEY (usuario_id) REFERENCES usuarios_app (id),
  ADD CONSTRAINT fk_bloqueos_reserva_habitaciones
    FOREIGN KEY (habitacion_id) REFERENCES habitaciones (id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_bloqueos_reserva_reservas
    FOREIGN KEY (reserva_id) REFERENCES reservas (id);
ALTER TABLE archivos_foto_habitacion DROP FOREIGN KEY archivos_foto_habitacion_ibfk_1;
ALTER TABLE archivos_foto_habitacion ADD CONSTRAINT fk_archivos_foto_habitacion_fotos
  FOREIGN KEY (foto_id) REFERENCES fotos_habitacion (id) ON DELETE CASCADE;
