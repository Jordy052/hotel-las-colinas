# Correo con Google Apps Script

Alternativa HTTPS para registro y recuperación de contraseña, sin depender de SMTP ni de la verificación telefónica de Brevo.

1. Abrir https://script.google.com/home/start con la cuenta Gmail remitente.
2. Crear un proyecto llamado Correo Hotel Las Colinas.
3. Pegar el contenido del archivo privado preparado en administrador/storage/deployment/CorreoHotel-PEGAR-EN-GOOGLE.gs dentro de Código.gs. El archivo público CorreoHotel.gs es solo una plantilla sin credenciales.
4. Guardar, seleccionar configurar y Ejecutar. Autorizar el permiso de envío de correo. Esta función no envía mensajes.
5. Implementar → Nueva implementación → Aplicación web. Ejecutar como Yo (la cuenta remitente). Acceso: Cualquier persona. Publicar el endpoint no permite enviar correos sin la firma privada que solo conoce la API.
6. Copiar la URL terminada en /exec a HOTEL_GOOGLE_MAIL_URL en administrador/.env.google-mail. No cambiar HOTEL_GOOGLE_MAIL_SECRET; debe coincidir con la del proyecto.
7. Configurar en Render HOTEL_EMAIL_PROVIDER=google_apps_script y las variables privadas URL, SECRET y EMAIL_FROM. Comprobar la autorización con una solicitud firmada operation=check, que no envía correos.

Las solicitudes y respuestas usan HMAC-SHA256; se rechazan firmas y fechas inválidas y se evitan reenvíos inmediatos del mismo identificador. No se registran destinatarios ni códigos. La web nunca recibe la clave privada.

Las cuentas Gmail personales tienen una cuota de 100 destinatarios diarios en Apps Script. El servicio no garantiza entrega inmediata ni ofrece un SLA de correo. El remitente real es la cuenta que autoriza y ejecuta el script.

Referencias: https://developers.google.com/apps-script/guides/web · https://developers.google.com/apps-script/reference/mail/mail-app · https://developers.google.com/apps-script/guides/services/quotas
