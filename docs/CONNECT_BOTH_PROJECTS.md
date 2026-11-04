# Conectar Avatar Studio y Webcam Companion en Windows

Este procedimiento usa únicamente los dos proyectos públicos. Cada persona aporta su vídeo y selecciona un perfil revisado. OBS Virtual Camera debe estar instalada para enviar la imagen a otra aplicación.

No se cambia silenciosamente la cámara del navegador. No uses este flujo en verificaciones de identidad, procesos bancarios o pruebas de vida.

## Usar los ZIP publicados sin instalar Python

Esta es la ruta recomendada para usuarios finales. Los apartados numerados siguientes explican la alternativa desde código fuente.

1. Descarga `AvatarStudio-Windows.zip` y `WebcamCompanion-Windows.zip` desde **Releases** de los dos repositorios. Descomprime ambos, conservando todas sus dependencias. Instala OBS Studio con OBS Virtual Camera por separado.
2. Abre PowerShell. Ajusta las dos primeras rutas a las carpetas extraídas que contienen los EXE:

```powershell
$StudioDir = "C:\AvatarApps\AvatarStudio"
$CompanionDir = "C:\AvatarApps\WebcamCompanion"
$Studio = Join-Path $StudioDir "AvatarStudio.exe"
$StudioCLI = Join-Path $StudioDir "AvatarStudio-CLI.exe"
$CompanionCLI = Join-Path $CompanionDir "AvatarStudioWebcamPC-CLI.exe"
$Companion = Join-Path $CompanionDir "AvatarStudioWebcamPC.exe"
$Workspace = Join-Path $env:LOCALAPPDATA "AvatarStudio"
$Config = Join-Path $env:LOCALAPPDATA "AvatarStudioWebcamPC\avatar-studio-webcam-pc.local.json"
& $CompanionCLI --self-test
& $Studio --workspace "$Workspace"
```

3. En Avatar Studio, importa un vídeo propio, analiza y revisa los trece segmentos y pulsa **Confirmar revisión**. Debe quedar **Listo para usar**. No actives todavía otra salida de cámara virtual. Conserva esta ventana de PowerShell para los pasos siguientes.
4. Lista los perfiles y copia el campo `id` del perfil listo. Sustituye el ejemplo:

```powershell
& $StudioCLI --workspace "$Workspace" --list-profiles
$ProfileId = "SUSTITUYE_POR_EL_ID_REAL"
& $StudioCLI --workspace "$Workspace" --play-profile "$ProfileId" --check-profile
```

Si la comprobación no termina correctamente, corrige el perfil antes de continuar.

5. Configura la conexión local:

```powershell
& $CompanionCLI --config "$Config" --setup --runtime-executable "$Studio" --project-root "$Workspace" --profile-id "$ProfileId"
```

Debe indicar que la configuración se ha creado. No publiques ese archivo ni el manifiesto de integridad. Si cambias el perfil, su catálogo, el vídeo o la distribución, detén el monitor, revisa el cambio y repite la configuración.

6. Detén cualquier otro productor de OBS Virtual Camera. Cierra cualquier monitor anterior desde su bandeja e inicia el nuevo:

```powershell
& $Companion --config "$Config"
```

Con una webcam integrada ya presente no necesitas desconectar nada. Espera unos segundos; el conector debe abrir el estudio y el controlador del perfil.

7. Consulta el estado desde la misma consola:

```powershell
& $CompanionCLI --config "$Config" --status
```

El resultado normal es `phase: "active"` y `output_ready: true`. En la web o aplicación receptora selecciona **OBS Virtual Camera** y comprueba visualmente la imagen y los movimientos. El micrófono se elige aparte; no se sustituye automáticamente la cámara que una web haya seleccionado.

8. Para detenerlo, cierra el receptor y sal del monitor desde su icono junto al reloj. Para usarlo otro día, repite el comando del paso 6: no necesitas Python ni este chat. La guía no instala el arranque con Windows automáticamente.

## 1. Instalar y compilar Avatar Studio

Descarga los dos repositorios y descomprímelos por separado. Sigue primero [INSTALL_AND_TEST.md](INSTALL_AND_TEST.md) para los requisitos del proyecto que estés leyendo. En la carpeta del repositorio **Avatar Studio**, instala y compila:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build_avatar_studio_windows.py
```

Obtendrás `release/AvatarStudio/`, que debe conservarse completa. Incluye `AvatarStudio.exe`, `AvatarStudio-CLI.exe`, sus dependencias y `avatar_studio_project.json`.

El marcador se genera durante la compilación y solo describe el contrato público; no contiene una ruta de tu PC. No lo inventes ni copies uno de otro runtime. Para distribuir a otras personas, usa una compilación de GitHub Actions, no el binario compilado en tu PC.

## 2. Preparar el perfil con el ejecutable público

Desde la carpeta del repositorio **Avatar Studio**:

```powershell
$Studio = (Resolve-Path ".\release\AvatarStudio\AvatarStudio.exe").Path
$StudioCLI = (Resolve-Path ".\release\AvatarStudio\AvatarStudio-CLI.exe").Path
$Workspace = Join-Path $env:LOCALAPPDATA "AvatarStudio"
& $Studio --workspace "$Workspace"
```

Importa un vídeo propio, analiza los movimientos, revisa los trece segmentos y pulsa **Confirmar revisión**. El estado debe ser **Listo para usar**. La guía de Avatar Studio explica la revisión en detalle.

Cierra el controlador si lo abriste y no dejes otra aplicación produciendo OBS Virtual Camera. Puedes cerrar también la interfaz después de preparar el perfil.

Si ya tenías un perfil en la ejecución desde código fuente, puedes elegir como `$Workspace` la raíz de esa copia de trabajo. Usa siempre el mismo espacio de trabajo al preparar, comprobar y conectar el perfil.

## 3. Obtener y comprobar el ID del perfil

En la misma ventana de PowerShell:

```powershell
& $StudioCLI --workspace "$Workspace" --list-profiles
$ProfileId = "SUSTITUYE_POR_EL_ID_REAL"
& $StudioCLI --workspace "$Workspace" --play-profile "$ProfileId" --check-profile
$LASTEXITCODE
```

Copia el campo `id` de un perfil cuyo `status` sea `ready`; no copies su nombre visible. Sustituye el texto de ejemplo antes de ejecutar la comprobación. El resultado esperado es un mensaje de perfil válido y código `0`. Este comando no reproduce vídeo ni abre una cámara.

Usa **AvatarStudio-CLI.exe**, no el EXE de interfaz, para ver mensajes y resultados en la consola.

## 4. Instalar el conector público

En otra ventana de PowerShell, abre la carpeta del repositorio **Avatar Studio Webcam Companion** y ejecuta:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest
```

Estas pruebas no necesitan tu vídeo ni abren cámaras. Antes de iniciar el monitor público, cierra cualquier monitor anterior desde su bandeja: solo puede haber uno por usuario. No se instalan ni sustituyen accesos de inicio automáticamente.

## 5. Vincular el programa y el perfil

En esta segunda ventana, asigna las rutas y el ID reales. La ruta del ejecutable debe apuntar a la carpeta completa que compilaste en el paso 1:

```powershell
$Studio = "C:\AvatarProjects\avatar-studio\release\AvatarStudio\AvatarStudio.exe"
$Workspace = Join-Path $env:LOCALAPPDATA "AvatarStudio"
$ProfileId = "SUSTITUYE_POR_EL_ID_REAL"
.\.venv\Scripts\python.exe -m avatar_studio_webcam_pc --setup --runtime-executable "$Studio" --project-root "$Workspace" --profile-id "$ProfileId"
```

Sustituye la ruta de ejemplo por la ubicación real del ejecutable y usa el mismo ID y espacio de trabajo del paso 3. El asistente guarda una configuración y un manifiesto de integridad locales. No los subas a GitHub.

El conector registra los hashes de la distribución, el catálogo, la configuración y los segmentos del perfil y su vídeo. No recorre el resto de la carpeta que contiene el vídeo. Si actualizas la distribución, modificas el catálogo/perfil, editas segmentos o reemplazas el vídeo, cierra el monitor, revisa el material y repite este paso.

## 6. Probar sin iniciar el avatar

```powershell
.\.venv\Scripts\python.exe -m avatar_studio_webcam_pc --dry-run
```

Consulta el estado desde otra consola en la carpeta del conector:

```powershell
.\.venv\Scripts\python.exe -m avatar_studio_webcam_pc --status
```

Con una webcam física presente debe aparecer en `physical_devices`. Una webcam integrada ya presente basta para disparar el arranque: no necesitas desconectarla.

Si no detecta cámaras, revisa **Configuración de Windows → Privacidad y seguridad → Cámara → Acceso a la cámara** y el permiso para aplicaciones de escritorio. Activarlos permite el acceso a la cámara física; no redirige su imagen por sí solo.

Cierra el monitor de simulación desde su icono junto al reloj.

## 7. Probar el arranque y la recepción

1. Instala OBS Studio y asegúrate de que OBS Virtual Camera esté registrada.
2. Detén cualquier otro productor de esa cámara, incluido el botón **Iniciar cámara virtual** de OBS.
3. Inicia el conector sin `--dry-run`:

```powershell
.\.venv\Scripts\python.exe -m avatar_studio_webcam_pc
```

4. Espera unos segundos con la webcam física presente.
5. Deben abrirse Avatar Studio y el controlador del perfil seleccionado.
6. Consulta `--status`: el resultado normal es `phase: "active"` y `output_ready: true`.
7. En una aplicación de streaming o videollamada donde esté permitido usar un avatar, selecciona **OBS Virtual Camera** y comprueba visualmente la imagen.
8. Usa las flechas/WASD en el controlador y comprueba que sus movimientos llegan a la aplicación receptora. El micrófono se selecciona aparte.

El estado de disponibilidad no demuestra por sí solo que se reciba la imagen correcta: la comprobación visual es obligatoria. El conector no instala OBS, no sustituye permisos del navegador y no abre los fotogramas de la webcam física.

## 8. Detener y repetir

Cierra la vista previa receptora y el monitor desde la bandeja. El conector detiene solo la salida que inició; conserva la interfaz principal. Si una webcam USB se desconecta, detiene su salida tras el tiempo de estabilidad. Para una webcam integrada basta con salir del monitor.

Para volver a usarlo, ejecuta el último comando del paso 7. No necesitas reinstalar ni mantener abierto este chat. Los errores no provocan reintentos automáticos; corrige la causa y vuelve a iniciar el monitor manualmente.

## 9. Si algo falla

- **No hay perfiles / ID desconocido:** usa el mismo `--workspace` en ambos programas, prepara el perfil y copia su `id`.
- **Perfil no revisado:** completa la revisión y confirma que esté listo en Avatar Studio.
- **Falta el marcador:** recompila esta versión de Avatar Studio y conserva toda la distribución.
- **Hash distinto:** revisa el cambio, cierra el monitor y repite `--setup`.
- **Cámara virtual ocupada:** detén el otro productor; no uses Avatar Studio y OBS produciendo la misma cámara a la vez.
- **Otra instancia activa:** cierra primero el monitor anterior desde la bandeja.
- **El navegador muestra la webcam física:** cambia también el selector dentro de la web y vuelve a abrir su vista previa.

La compatibilidad de código y las pruebas automáticas no garantizan todos los controladores de cámara de Windows. Verifica la recepción real con tu equipo antes de emitir.
