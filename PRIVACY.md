# Privacidad

## Principios del repositorio público

Este repositorio contiene únicamente código, pruebas, plantillas y documentación. No debe contener vídeos, imágenes, avatares, perfiles creados, informes generados, rutas locales, registros, binarios, certificados ni secretos.

## Datos que se quedan en el equipo de cada usuario

Al importar un vídeo, Avatar Studio genera una configuración, un catálogo de perfiles, segmentos y diagnósticos bajo `data/studio/` en ejecución desde código fuente. El ejecutable usa `%LOCALAPPDATA%\AvatarStudio` de forma predeterminada. Esos archivos pueden incluir el nombre y la ruta del vídeo elegido, por lo que nunca se deben añadir a Git.

La aplicación no modifica el vídeo original.

## Red y salida de vídeo

El código de este repositorio no implementa subida de vídeos, cuentas de usuario, telemetría ni llamadas a servicios remotos. Cuando se activa la cámara virtual, los fotogramas se entregan a un controlador local de cámara virtual. Cualquier envío posterior depende de la plataforma que el usuario abra y configure.

## Antes de compartir

Ejecuta los tres auditores documentados en el README y revisa `git status` antes de cada publicación. Si un auditor falla, elimina el dato local de la copia destinada a GitHub o crea una copia limpia desde esta carpeta pública.
