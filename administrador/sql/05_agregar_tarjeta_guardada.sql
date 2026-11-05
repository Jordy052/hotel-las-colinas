-- Tarjeta asociada a cada cuenta. Conserva referencia, terminacion y facturacion.
-- No guarda el numero completo ni el codigo de seguridad. No altera datos existentes.
USE defaultdb;

CREATE TABLE IF NOT EXISTS tarjetas_guardadas (
  usuario_id INT NOT NULL,
  referencia VARCHAR(32) NOT NULL,
  titular VARCHAR(60) NOT NULL,
  ultimos_cuatro VARCHAR(4) NOT NULL,
  mes_vencimiento INT NOT NULL,
  anio_vencimiento INT NOT NULL,
  facturacion JSON NOT NULL,
  creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id),
  UNIQUE KEY uq_tarjetas_guardadas_referencia (referencia),
  CONSTRAINT fk_tarjetas_guardadas_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios_app (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
