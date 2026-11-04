-- Actualiza una base hotel_reservas ya creada en MySQL Workbench.
-- No elimina cuentas. Se detiene si un nombre existente no cumple 5–30
-- caracteres o si hay duplicados que deban resolverse primero.
-- La contraseña original se valida entre 12 y 30 caracteres en la aplicación.
-- La base de datos recibe solo el hash; password_hash queda en VARCHAR(255).
USE hotel_reservas;

DROP PROCEDURE IF EXISTS migrar_limites_cuenta_app;
DELIMITER $$
CREATE PROCEDURE migrar_limites_cuenta_app()
BEGIN
  IF EXISTS (
    SELECT 1
    FROM app_users
    WHERE CHAR_LENGTH(email) > 160
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Hay correos de más de 160 caracteres. Corrígelos antes de migrar.';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM app_users
    WHERE CHAR_LENGTH(TRIM(username)) < 5
       OR CHAR_LENGTH(TRIM(username)) > 30
       OR CHAR_LENGTH(username) <> CHAR_LENGTH(TRIM(username))
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Hay nombres de usuario fuera de 5–30 caracteres o con espacios externos. Corrígelos antes de migrar.';
  END IF;

  IF EXISTS (
    SELECT LOWER(TRIM(username))
    FROM app_users
    GROUP BY LOWER(TRIM(username))
    HAVING COUNT(*) > 1
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Hay nombres de usuario duplicados. Resuélvelos antes de crear la restricción única.';
  END IF;

  ALTER TABLE app_users
    MODIFY username VARCHAR(30) NOT NULL,
    MODIFY email VARCHAR(160) NOT NULL;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'app_users'
      AND index_name = 'uq_app_users_username'
  ) THEN
    ALTER TABLE app_users
      ADD UNIQUE KEY uq_app_users_username (username);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'app_users'
      AND constraint_name = 'ck_app_users_username_length'
      AND constraint_type = 'CHECK'
  ) THEN
    ALTER TABLE app_users
      ADD CONSTRAINT ck_app_users_username_length
      CHECK (
        CHAR_LENGTH(TRIM(username)) BETWEEN 5 AND 30
        AND CHAR_LENGTH(username) = CHAR_LENGTH(TRIM(username))
      );
  END IF;
END$$
DELIMITER ;

CALL migrar_limites_cuenta_app();
DROP PROCEDURE migrar_limites_cuenta_app;
