-- Agrega la cédula del personal de recepción a una base ya existente.
-- Ejecutar en MySQL Workbench sobre hotel_reservas.
-- La columna permite NULL para usuarios web, administradores y cuentas previas;
-- el formulario administrativo exige cédula para nuevas cuentas de recepción.
USE hotel_reservas;

DROP PROCEDURE IF EXISTS migrar_cedula_personal_app;
DELIMITER $$
CREATE PROCEDURE migrar_cedula_personal_app()
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'app_users'
      AND column_name = 'cedula'
  ) THEN
    ALTER TABLE app_users
      ADD COLUMN cedula VARCHAR(16) DEFAULT NULL AFTER email;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'app_users'
      AND index_name = 'uq_app_users_cedula'
  ) THEN
    ALTER TABLE app_users
      ADD UNIQUE KEY uq_app_users_cedula (cedula);
  END IF;
END$$
DELIMITER ;

CALL migrar_cedula_personal_app();
DROP PROCEDURE migrar_cedula_personal_app;
