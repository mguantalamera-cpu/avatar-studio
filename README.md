# Avatar Studio

Avatar Studio es una aplicación local para preparar un avatar de vídeo propio y usarlo en streaming o como fuente de una cámara virtual. El repositorio no contiene ningún vídeo, avatar, perfil, historial, ruta local ni compilación de la persona que lo publica.

La aplicación empieza con una biblioteca vacía. Cada usuario importa un vídeo propio y sus perfiles, informes y rutas se guardan únicamente en su carpeta local `data/studio/`, que Git ignora.

**Empieza por [la guía completa de instalación y pruebas](docs/INSTALL_AND_TEST.md)**: explica cómo instalar, importar un vídeo, revisar movimientos, probar la cámara virtual, detener la emisión y resolver errores.

**Conectar ambos proyectos:** esta versión incluye el contrato público de Webcam Companion. Compila la distribución, prepara un perfil revisado y sigue [la guía de conexión paso a paso](docs/CONNECT_BOTH_PROJECTS.md). El conector abre este estudio y reproduce el perfil elegido; no necesita el runtime privado anterior.

## Uso permitido

Avatar Studio está pensado para creación de contenido, streaming, presentaciones, demostraciones y otros usos consentidos con material propio o autorizado.

No está diseñado ni autorizado para suplantar a una persona, evitar una verificación de identidad o prueba de vida, abrir cuentas, acceder a servicios financieros, eludir controles de seguridad ni usarse en procesos de alta confianza.

## Qué necesita cada persona

- Windows 10 u 11.
- Una instalación de Python 3.11 para ejecutar el código fuente, o el ejecutable que genere la compilación de GitHub.
- Un vídeo del que tenga derechos de uso.
- OBS Studio con **OBS Virtual Camera** instalada y registrada solo si quiere enviar el avatar a un navegador, una videollamada o una plataforma de streaming como si fuese una cámara.

OBS no es necesario para importar, analizar, revisar o previsualizar el vídeo.

## Inicio rápido desde código fuente

En PowerShell, dentro de una copia limpia del repositorio:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\run_avatar_studio.py
```

La primera vez:

1. Pulsa **Importar vídeo** y elige un vídeo propio.
2. Espera al análisis automático o pulsa **Analizar movimientos**.
3. Revisa los trece segmentos; corrígelos si es necesario.
4. Pulsa **Confirmar revisión** cuando el resultado sea correcto.
5. Pulsa **Abrir controlador** para probarlo o **Activar cámara virtual** para publicarlo localmente.

En el controlador se usan las flechas o WASD para mover el avatar, `R` para volver al centro, espacio para pausar y `Q`/Esc para salir.

## Usarlo en una web o aplicación de streaming

1. Instala y registra OBS Virtual Camera.
2. En Avatar Studio, abre un perfil ya revisado y pulsa **Activar cámara virtual**.
3. En el navegador o aplicación de destino, elige **OBS Virtual Camera** en el selector de cámara.
4. Mantén abierto Avatar Studio mientras dure la emisión.

El navegador no se redirige por la fuerza: por seguridad, cada web o aplicación permite seleccionar la cámara que va a utilizar. Selecciona OBS Virtual Camera en esa aplicación en lugar de la cámara física.

## Privacidad

- No se incluye ni se sube material audiovisual de ejemplo.
- El código no envía vídeos, perfiles o diagnósticos a servidores remotos.
- La salida de cámara virtual se entrega al controlador local de cámara virtual; la plataforma de destino solo recibirá lo que el usuario decida emitir.
- Las rutas locales y metadatos de vídeos viven bajo `data/studio/` y quedan fuera de Git.
- La carpeta incluye comprobaciones que bloquean medios, binarios, cachés, rutas de usuario, secretos y flujos alternativos de Windows antes de publicar.

Consulta [PRIVACY.md](PRIVACY.md) y [docs/PUBLISH_TO_GITHUB.md](docs/PUBLISH_TO_GITHUB.md).

## Compilar un ejecutable para Windows

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build_avatar_studio_windows.py
```

El resultado queda en `release/AvatarStudio/` y se usa para probar la compilación local. Para distribuir públicamente, usa preferentemente una compilación limpia de GitHub: los binarios locales pueden incluir rutas del entorno de construcción. Distribuye la carpeta completa como artefacto o release, fuera del repositorio fuente.

El ejecutable guarda el catálogo y la configuración de cada persona en `%LOCALAPPDATA%\AvatarStudio` de forma predeterminada. Se puede cambiar con la variable de entorno `AVATAR_STUDIO_DATA_DIR`.

## Validar antes de publicar

```powershell
python scripts\normalize_public_metadata.py
python scripts\audit_public_tree.py
powershell -ExecutionPolicy Bypass -File scripts\audit_public_metadata.ps1
```

Ejecuta estas comprobaciones sobre la copia limpia de publicación; instala y prueba en otra copia de trabajo siguiendo la guía completa. El auditor falla si encuentra datos locales, vídeos, imágenes, ejecutables, rutas personales, secretos, cachés o metadatos de Windows.

## Documentación

- [Instalación y pruebas paso a paso](docs/INSTALL_AND_TEST.md)
- [Conectar Avatar Studio y Webcam Companion](docs/CONNECT_BOTH_PROJECTS.md)
- [Instalación en Windows](docs/INSTALL_WINDOWS.md)
- [Publicar en GitHub sin datos personales](docs/PUBLISH_TO_GITHUB.md)
- [Arquitectura y almacenamiento local](docs/ARCHITECTURE.md)
- [Pruebas realizadas y límites de validación](docs/VALIDATION.md)
- [Política de privacidad](PRIVACY.md)
- [Política de seguridad](SECURITY.md)

Antes de publicar, elige una licencia en [LICENSE-CHOICE.md](LICENSE-CHOICE.md). No se ha incluido una licencia por defecto para no conceder derechos sobre tu código sin tu decisión expresa.
