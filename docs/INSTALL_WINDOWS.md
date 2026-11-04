# Instalación en Windows

Para instalar y probar desde cero, sigue [INSTALL_AND_TEST.md](INSTALL_AND_TEST.md), que incluye los comandos sin activar scripts de PowerShell, la preparación del vídeo, las pruebas visuales y la compatibilidad actual con Webcam Companion. Esta página es un resumen.

## Opción A: ejecutar el código fuente

1. Instala Python 3.11 desde su página oficial y marca la opción para añadirlo al sistema.
2. Abre PowerShell en la carpeta de Avatar Studio.
3. Crea y activa un entorno aislado:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Instala las dependencias:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

5. Abre la aplicación:

   ```powershell
   python tools\run_avatar_studio.py
   ```

La detección básica de movimiento funciona con OpenCV. Para un análisis adicional de puntos faciales, instala opcionalmente:

```powershell
python -m pip install ".[enhanced-analysis]"
```

## Opción B: usar un ejecutable de GitHub

Si el repositorio publica un release firmado o verificado, descarga solo el archivo adjunto a ese release. Descomprime la carpeta y ejecuta `AvatarStudio.exe`.

El ejecutable guarda los perfiles en `%LOCALAPPDATA%\AvatarStudio`. No copies esa carpeta al repositorio ni la compartas si contiene rutas o informes privados.

## Cámara virtual

Para publicar la señal como una cámara local:

1. Instala OBS Studio y asegúrate de que OBS Virtual Camera esté disponible en Windows.
2. Abre Avatar Studio, prepara un perfil y confirma su revisión.
3. Pulsa **Activar cámara virtual**.
4. En la web o aplicación de destino, selecciona **OBS Virtual Camera** explícitamente.

No uses Avatar Studio cuando una plataforma requiera una comprobación de identidad, una prueba de vida u otro control de alta confianza.
