-- Actualiza la cuenta de usuarios_app en Aiven defaultdb.
-- No elimina cuentas. Se detiene si un nombre existente no cumple 5–30
-- caracteres o si hay duplicados que deban resolverse primero.
-- La contraseña original se valida entre 12 y 30 caracteres en la aplicación.
-- La base de datos recibe solo el hash; hash_contrasena queda en VARCHAR(255).
USE defaultdb;

DROP PROCEDURE IF EXISTS migrar_limites_cuenta_app;
DELIMITER $$
CREATE PROCEDURE migrar_limites_cuenta_app()
BEGIN
  IF EXISTS (
    SELECT 1
    FROM usuarios_app
    WHERE CHAR_LENGTH(correo) > 160
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Hay correos de más de 160 caracteres. Corrígelos antes de migrar.';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM usuarios_app
    WHERE CHAR_LENGTH(TRIM(nombre_usuario)) < 5
       OR CHAR_LENGTH(TRIM(nombre_usuario)) > 30
       OR CHAR_LENGTH(nombre_usuario) <> CHAR_LENGTH(TRIM(nombre_usuario))
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Hay nombres de usuario fuera de 5–30 caracteres o con espacios externos. Corrígelos antes de migrar.';
  END IF;

  IF EXISTS (
    SELECT LOWER(TRIM(nombre_usuario))
    FROM usuarios_app
    GROUP BY LOWER(TRIM(nombre_usuario))
    HAVING COUNT(*) > 1
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Hay nombres de usuario duplicados. Resuélvelos antes de crear la restricción única.';
  END IF;

  ALTER TABLE usuarios_app
    MODIFY nombre_usuario VARCHAR(30) NOT NULL,
    MODIFY correo VARCHAR(160) NOT NULL;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'usuarios_app'
      AND index_name = 'uq_usuarios_app_nombre_usuario'
  ) THEN
    ALTER TABLE usuarios_app
      ADD UNIQUE KEY uq_usuarios_app_nombre_usuario (nombre_usuario);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'usuarios_app'
      AND constraint_name = 'ck_usuarios_app_nombre_usuario_longitud'
      AND constraint_type = 'CHECK'
  ) THEN
    ALTER TABLE usuarios_app
      ADD CONSTRAINT ck_usuarios_app_nombre_usuario_longitud
      CHECK (
        CHAR_LENGTH(TRIM(nombre_usuario)) BETWEEN 5 AND 30
        AND CHAR_LENGTH(nombre_usuario) = CHAR_LENGTH(TRIM(nombre_usuario))
      );
  END IF;
END$$
DELIMITER ;

CALL migrar_limites_cuenta_app();
DROP PROCEDURE migrar_limites_cuenta_app;
