# Seguridad

## Alcance

Los informes de seguridad deben centrarse en el código, dependencias, compilación, almacenamiento local y salida de cámara virtual de Avatar Studio.

No incluyas vídeos, perfiles reales, rutas locales, credenciales ni otros datos privados en un informe público. Usa las alertas privadas de seguridad del repositorio de GitHub cuando estén habilitadas.

## Publicación segura

Antes de crear una versión, ejecuta los auditores de `scripts/`, las pruebas y una compilación limpia. Los binarios deben distribuirse como artefactos o releases, no añadirse al historial de código fuente.
