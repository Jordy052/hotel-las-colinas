-- Agrega la cédula del personal de recepción a una base ya existente.
-- Ejecutar en MySQL Workbench conectado a Aiven, sobre defaultdb.
-- La columna permite NULL para usuarios web, administradores y cuentas previas;
-- el formulario administrativo exige cédula para nuevas cuentas de recepción.
USE defaultdb;

DROP PROCEDURE IF EXISTS migrar_cedula_personal_app;
DELIMITER $$
CREATE PROCEDURE migrar_cedula_personal_app()
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'usuarios_app'
      AND column_name = 'cedula'
  ) THEN
    ALTER TABLE usuarios_app
      ADD COLUMN cedula VARCHAR(16) DEFAULT NULL AFTER correo;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'usuarios_app'
      AND index_name = 'uq_usuarios_app_cedula'
  ) THEN
    ALTER TABLE usuarios_app
      ADD UNIQUE KEY uq_usuarios_app_cedula (cedula);
  END IF;
END$$
DELIMITER ;

CALL migrar_cedula_personal_app();
DROP PROCEDURE migrar_cedula_personal_app;
