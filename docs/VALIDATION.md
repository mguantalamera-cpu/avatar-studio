# Validación de la integración pública

Validación realizada el 4 de noviembre de 2026 sobre las dos copias públicas.

- Avatar Studio: 15 pruebas automáticas superadas.
- Webcam Companion: 102 pruebas automáticas y comprobación de código superadas.
- Ambas distribuciones de Windows se han compilado en una copia de prueba separada.
- La CLI empaquetada de Avatar Studio ha listado un perfil sintético y validado los argumentos generados por el conector.
- Se ha comprobado el rechazo de un perfil sin revisar y de un catálogo modificado tras configurar el conector.
- El arranque fuera de pantalla del estudio y `AvatarStudioWebcamPC-CLI.exe --self-test` han terminado correctamente.
- Las auditorías del árbol público y de metadatos de Windows han pasado sin hallazgos bloqueantes.

La prueba conjunta usa exclusivamente un vídeo sintético temporal; no accede a vídeos personales ni a fotogramas de webcam, no activa cámara virtual y no emite por Internet. Puede repetirse desde la carpeta de Avatar Studio:

```powershell
.\.venv\Scripts\python.exe tools\verify_companion_contract.py --companion-source "..\avatar-studio-webcam-pc" --studio-release ".\release\AvatarStudio"
```

Sustituye las rutas si tus carpetas están en otro lugar. Primero instala los requisitos de ambos proyectos y compila Avatar Studio.

## Prueba real de recepción de la cámara virtual

Además del contrato sin cámaras, se ha realizado una prueba local acotada con los dos ejecutables descargados de la compilación limpia de GitHub:

- El conector empaquetado detectó la presencia de una webcam integrada, sin abrir sus fotogramas, y arrancó la interfaz y la salida del perfil sintético seleccionado.
- El monitor alcanzó `phase: active` y `output_ready: true`.
- Un receptor independiente (FFmpeg/DirectShow), configurado explícitamente con `video=OBS Virtual Camera`, recibió cinco fotogramas. Se comprobaron numéricamente los colores de fondo y centro del patrón sintético, no solo la existencia de un proceso.
- No se abrió la cámara física ni el micrófono, no se usaron archivos personales y no hubo emisión por Internet. Los procesos creados para la prueba se detuvieron al terminar.

## Límite de la validación

La recepción real se ha verificado en un equipo Windows, no en todas las webcams, versiones de OBS, navegadores o plataformas. Cada usuario debe completar la prueba visual descrita en [CONNECT_BOTH_PROJECTS.md](CONNECT_BOTH_PROJECTS.md). Un proceso vivo o `output_ready` no demuestra por sí solo que la imagen correcta llegue a una plataforma.

Los ejecutables construidos localmente para estas pruebas no forman parte del repositorio público. Las distribuciones públicas deben proceder de una compilación limpia de GitHub Actions.
