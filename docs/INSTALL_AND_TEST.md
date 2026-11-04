# Instalar y probar Avatar Studio en Windows, paso a paso

Esta guía corresponde al código público de Avatar Studio. La aplicación empieza vacía: cada persona aporta un vídeo propio. Puedes usarla para preparar contenido y emitir un avatar en contextos consentidos.

**Integración entre ambos proyectos:** después de probar el estudio, sigue [CONNECT_BOTH_PROJECTS.md](CONNECT_BOTH_PROJECTS.md) para preparar la distribución y conectar un perfil revisado con Webcam Companion. El marcador público se genera al compilar, no contiene rutas personales y no depende del runtime privado.

## 1. Preparar una copia de trabajo

1. Descarga el proyecto desde GitHub mediante **Code → Download ZIP**, o clónalo si usas Git.
2. Descomprime el ZIP; no ejecutes archivos dentro del ZIP.
3. Usa una carpeta local para trabajar. En los ejemplos la carpeta se llama `C:\AvatarProjects\avatar-studio`; sustituye esa ruta por la tuya.
4. Conserva aparte una copia limpia para publicar. Las pruebas crearán entornos y perfiles locales que no deben subirse.

No necesitas permisos de administrador para ejecutar el código de la aplicación.

## 2. Instalar los requisitos

Necesitas Windows 10/11 de 64 bits y Python 3.11 de 64 bits. Descarga Python desde [Python para Windows](https://www.python.org/downloads/windows/). OBS solo es necesario para la salida de cámara virtual.

Abre PowerShell desde Inicio y entra en la carpeta del proyecto:

```powershell
Set-Location "C:\AvatarProjects\avatar-studio"
py -3.11 --version
```

El segundo comando debe mostrar `Python 3.11.x`. Si `py` no existe o no encuentra esa versión, completa la instalación de Python y abre una nueva ventana de PowerShell.

Ejecuta estos comandos uno a uno. Espera a que termine cada comando antes del siguiente:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

El último debe mostrar `No broken requirements found.`. La instalación necesita Internet para descargar dependencias; el procesamiento del vídeo se hace localmente.

Los comandos de esta guía usan el Python del entorno directamente. Así no necesitas activar scripts ni cambiar la política de ejecución de PowerShell.

## 3. Comprobar que la interfaz arranca

Desde la misma carpeta:

```powershell
.\.venv\Scripts\python.exe tools\run_avatar_studio.py --smoke-test
$LASTEXITCODE
```

La prueba abre la interfaz fuera de pantalla y se cierra sola. El resultado esperado es `0`. Esto comprueba el arranque y los recursos básicos de OpenCV; no comprueba todavía tu vídeo ni la cámara virtual.

Abre ahora la aplicación normalmente:

```powershell
.\.venv\Scripts\python.exe tools\run_avatar_studio.py
```

Debe aparecer una ventana titulada **Avatar Studio** con el botón **Importar vídeo**. La biblioteca estará vacía en una instalación nueva.

Para volver a abrirla otro día, repite únicamente este último comando desde la carpeta del proyecto. No hace falta reinstalar las dependencias ni usar este chat.

## 4. Preparar el vídeo de prueba

1. Elige un vídeo propio o autorizado en MP4, MOV, MKV, AVI o WEBM.
2. Guárdalo fuera del repositorio. No se incluye ningún vídeo de ejemplo para proteger la privacidad.
3. Para probar los controles direccionales, el vídeo debe contener: centro, giro hacia la derecha y vuelta al centro, giro hacia la izquierda y vuelta al centro, mirada arriba y vuelta al centro, mirada abajo y vuelta al centro.
4. Mantén cada posición un momento y procura que el rostro sea visible. Un vídeo sin esas acciones no permite preparar los trece segmentos requeridos.

El programa reproduce segmentos del archivo elegido; no crea automáticamente movimientos que no estén en el vídeo. La detección automática es una propuesta y puede necesitar correcciones.

## 5. Importar y revisar

1. Pulsa **Importar vídeo** y selecciona el archivo.
2. Comprueba que la vista previa corresponde al vídeo que has elegido.
3. Espera al diagnóstico y al análisis automático. Si no comienza, selecciona el perfil y pulsa **Analizar movimientos**.
4. Revisa la pestaña **Actividad** si aparece un error.
5. Pulsa **Revisar segmentos**. En esa ventana, `N` pasa al siguiente segmento, `P` al anterior, `V` reproduce una vez y `B` reproduce en bucle. `Q` o Esc cierra la ventana, o detiene primero el bucle si estás reproduciendo uno.
6. Comprueba los trece segmentos: una posición central y, para cada dirección, movimiento de entrada, posición mantenida y vuelta al centro.

Si un segmento falta o empieza/termina en el lugar incorrecto, pulsa **Corregir segmentos**:

| Tecla | Acción en el editor |
| --- | --- |
| A / D | Retroceder / avanzar un fotograma |
| J / L | Retroceder / avanzar diez fotogramas |
| K / O | Retroceder / avanzar treinta fotogramas |
| Espacio | Reproducir / pausar |
| N / P | Siguiente / anterior segmento |
| `[` / `]` | Marcar inicio / final del segmento seleccionado |
| S | Guardar los cambios |
| V / B | Ver una vez / en bucle |
| Q / Esc | Salir |

Los segmentos de posición mantenida necesitan al menos quince fotogramas y las transiciones al menos tres. En un teclado español puede ser necesario usar la combinación del teclado que produce `[` o `]`.

Guarda con `S` antes de salir. Cuando hayas revisado todos los segmentos, pulsa **Confirmar revisión** en Avatar Studio. El perfil debe pasar a **Listo para usar**. Si la aplicación indica que faltan segmentos, corrígelos antes de continuar.

## 6. Probar el controlador local

1. Pulsa **Abrir controlador**.
2. Haz clic en la ventana del controlador para que reciba las teclas.
3. Pulsa izquierda, derecha, arriba y abajo, o WASD. Comprueba que se reproduce la acción correspondiente.
4. Pulsa `R` y comprueba que vuelve al centro.
5. Pulsa espacio para pausar y otra vez para continuar.
6. Sal con `Q` o Esc.

La primera prueba está superada si la imagen se reproduce, los movimientos corresponden a las teclas y no aparece un error de lectura de vídeo. No se emite por Internet en esta prueba.

## 7. Probar la cámara virtual directamente desde Avatar Studio

1. Instala OBS Studio desde [la descarga oficial](https://obsproject.com/download). En Windows, su instalación proporciona OBS Virtual Camera, según [la documentación de pyvirtualcam](https://github.com/letmaik/pyvirtualcam#supported-virtual-cameras).
2. Si OBS está abierto y su cámara virtual está iniciada, pulsa **Detener cámara virtual**. Para esta prueba deja a Avatar Studio como único productor de esa cámara; puedes cerrar OBS.
3. En un perfil **Listo para usar**, pulsa **Activar cámara virtual**.
4. Comprueba en **Actividad** que no hay errores y que el proceso indica que la cámara está lista.
5. Abre la configuración de vídeo de una aplicación de videollamada o streaming donde tengas permitido usar un avatar.
6. Selecciona explícitamente **OBS Virtual Camera**, concede el permiso de cámara y comprueba la vista previa.
7. Mueve el avatar desde la ventana del controlador y verifica que esos movimientos aparecen en la aplicación de destino.

El nombre del dispositivo por sí solo no demuestra que se esté enviando el avatar: comprueba la imagen en la aplicación receptora. Si ves la cámara física, cambia el selector también dentro de esa aplicación y reinicia su vista previa.

La cámara virtual transporta vídeo. Selecciona el micrófono por separado. Mantén abiertos Avatar Studio y el controlador mientras quieras enviar la señal.

## 8. Otra forma de emitir: componer la escena en OBS

Este flujo permite añadir audio, rótulos y otras fuentes:

1. Cierra el controlador que esté enviando directamente a la cámara virtual.
2. En Avatar Studio pulsa **Abrir controlador**.
3. Abre OBS y crea una escena con una fuente **Captura de ventana** que muestre el controlador. Ajusta el encuadre para evitar controles o textos; el controlador también admite `--no-overlay` cuando se lanza desde su herramienta de línea de comandos.
4. Añade el micrófono por separado y comprueba una grabación local breve.
5. Si otra aplicación necesita la escena como cámara, pulsa **Iniciar cámara virtual** en OBS y selecciona **OBS Virtual Camera** en esa aplicación.

En este flujo OBS produce la cámara virtual. No pulses simultáneamente **Activar cámara virtual** en Avatar Studio. OBS dispone de una sola instancia de su cámara virtual; consulta [pyvirtualcam](https://github.com/letmaik/pyvirtualcam#supported-virtual-cameras) y [la guía de OBS](https://obsproject.com/kb/virtual-camera-guide).

## 9. Detener y volver a usar

1. Cierra la vista previa en la aplicación de destino.
2. Sal del controlador con `Q` o Esc. Si OBS produce la cámara, pulsa **Detener cámara virtual** en OBS.
3. Cierra Avatar Studio.

Los perfiles quedan guardados. Al volver a abrir la aplicación podrás seleccionar el perfil preparado, siempre que el vídeo siga en la misma ubicación.

Desde código fuente, los perfiles viven en `data/studio/` dentro de la copia de trabajo. En el ejecutable viven normalmente en `%LOCALAPPDATA%\AvatarStudio\data\studio`. Contienen rutas locales y no deben publicarse.

## 10. Pruebas automáticas opcionales

En la copia de trabajo:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest==9.0.3
.\.venv\Scripts\python.exe -m pytest
```

Estas pruebas comprueban lógica de configuración, perfiles y reproducción. No sustituyen la prueba visual con tu vídeo, Windows y OBS.

## 11. Compilar y probar un ejecutable

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build_avatar_studio_windows.py
.\release\AvatarStudio\AvatarStudio.exe --smoke-test
```

Después abre `release/AvatarStudio/AvatarStudio.exe` y repite la prueba de importación y cámara. Si se distribuye, conserva **toda** la carpeta `AvatarStudio`, incluidas sus dependencias; no copies solo el EXE.

Un ZIP del código fuente no incluye un ejecutable ya instalado. Los ejecutables de GitHub solo estarán disponibles cuando el responsable publique un release o un artefacto de compilación. El arranque del código fuente y el del EXE requieren comprobaciones separadas.

## 12. Problemas frecuentes

| Problema | Qué comprobar |
| --- | --- |
| No existe `.venv/Scripts/python.exe` | Entra en la raíz correcta y completa el paso 2. |
| `No module named ...` | Repite la instalación usando el Python de `.venv`; no otro Python del sistema. |
| El vídeo no se abre | Comprueba que el archivo exista y se reproduzca normalmente; prueba MP4 compatible con OpenCV. |
| El análisis no encuentra movimientos | Comprueba el contenido descrito en el paso 4 y corrige segmentos manualmente. |
| Cámara virtual ocupada o no disponible | Comprueba la instalación de OBS y detén cualquier otro productor de OBS Virtual Camera. |
| Imagen negra o cámara física | Selecciona la cámara correcta, vuelve a abrir la vista previa y confirma que el controlador sigue funcionando. |
| Un perfil dejó de funcionar | Si moviste el vídeo, impórtalo de nuevo desde su ubicación actual. |
| `avatar-studio` pide `--config` | Ese comando instalado corresponde al reproductor simple; abre la interfaz con `tools/run_avatar_studio.py`. |

## 13. Subir esta guía a GitHub

Este archivo ya está dentro del proyecto y se enlaza desde el README. Súbelo junto con el código de la copia limpia. Para las comprobaciones de publicación, sigue [PUBLISH_TO_GITHUB.md](PUBLISH_TO_GITHUB.md). La copia de publicación debe quedar sin `.venv`, perfiles, vídeos, cachés o compilaciones.
