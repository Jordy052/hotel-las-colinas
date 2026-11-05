# Alojamiento de Hotel Las Colinas

Estado al 4 de noviembre de 2026:

- Web: https://jordy052.github.io/hotel-las-colinas/
- API HTTPS: https://hotel-las-colinas-api.onrender.com/api
- Servicio Render: hotel-las-colinas-api, plan Free, una instancia.
- MySQL Aiven: hotel-las-colinas-mysql, plan Free. Es la base única compartida por web, administración y recepción.
- Migración: 11 habitaciones, cuentas, huéspedes, reservas, pagos y permisos copiados y comparados con el respaldo. Las 22 fotografías están almacenadas en MySQL con verificación SHA-256.
- Correo: Google Apps Script autorizado y configurado en Render mediante HTTPS y firmas HMAC. Se verificaron la autorización, la cuota y la configuración activa sin enviar correos de prueba; la recepción real queda por comprobar desde la web. Brevo queda como alternativa mientras su soporte revisa la verificación SMS.

## Configuración

usuario/js/configuracion.js contiene únicamente la dirección pública de la API. Los datos de MySQL y las claves de servicios se guardan en variables privadas de Render y archivos .env excluidos de GitHub. No se deben copiar contraseñas a JavaScript ni a este documento.

administrador/.env apunta a la base remota usando TLS y certificado CA verificado. Es necesario cerrar y volver a abrir las aplicaciones de administración y recepción para cargar esa configuración. Los respaldos previos se conservan en `administrador/storage/backups/`; el sistema activo usa Aiven.

Las fotos se guardan en `archivos_foto_habitacion` y se relacionan con `fotos_habitacion`. El escritorio mantiene una caché local para mostrarlas; la API las sirve desde MySQL. Se admiten imágenes de hasta 8 MB. El disco temporal de Render no es el almacenamiento principal.

## Comprobaciones realizadas

HTTPS, CORS de GitHub Pages, MySQL TLS, listado de habitaciones y fotos, inicio de sesión, perfil, bloqueo temporal de habitación, repetición del pago sin duplicar registros, cancelación y reembolso, cierre de sesión. Los registros temporales de las pruebas se eliminaron. No se realizaron cobros externos ni se enviaron correos de prueba.

## Límites del plan gratuito

Render Free se suspende tras inactividad y puede tardar cerca de un minuto en despertar. Las sesiones y los códigos de verificación están en memoria y se pierden cuando se reinicia el proceso; en ese caso se inicia sesión o se solicita otro código. Se usa una sola instancia.

Render Free bloquea SMTP en los puertos 25, 465 y 587. Por eso el correo remoto utiliza Google Apps Script mediante HTTPS; Brevo también está disponible como alternativa. La instalación local conserva su transporte SMTP.

Aiven Free tiene límites de almacenamiento y conexiones y puede apagarse por inactividad. Estos planes sirven para pruebas y demostraciones; no garantizan disponibilidad continua.

Referencias: https://render.com/docs/free · https://aiven.io/docs/products/mysql/concepts/mysql-free-tier · https://developers.brevo.com/docs/send-a-transactional-email

El proyecto público de Apps Script está en administrador/apps_script/. Es una plantilla sin claves. El archivo preparado con la clave privada se guarda en administrador/storage/deployment/ y está excluido de GitHub. Las cuentas Gmail personales tienen una cuota de 100 destinatarios diarios.

## Optimización de carga

El arranque del escritorio consulta los metadatos del esquema en conjunto, manteniendo las validaciones de tablas, columnas, roles y permisos. La medición en la misma computadora pasó de 21,3 s (20 consultas) a 4,0 s (5 consultas). La autenticación carga rol y permisos en una consulta.

Las 22 imágenes se optimizaron a WebP: 52,97 MB → 4,41 MB. Los originales se respaldaron de forma privada antes de convertir las copias de la base remota. Las cargas futuras se optimizan automáticamente y las fotos ya optimizadas no se recomprimen al editar. El navegador recibe URLs con versión, ETag y caché; las imágenes fuera de la vista se cargan al acercarse a ellas. Las tarjetas y la galería muestran el encuadre completo.

El tiempo de arranque de una instancia dormida de Render Free depende del proveedor y es independiente de estas mediciones del escritorio. Reiniciar el escritorio y recargar la web para usar los ajustes nuevos.
