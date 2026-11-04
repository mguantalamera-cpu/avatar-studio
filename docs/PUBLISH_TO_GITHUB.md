# Publicar en GitHub sin datos personales

La carpeta `github-avatar-studio` ya es una copia pública separada. No añadas los directorios privados del proyecto original ni una compilación existente.

La guía [INSTALL_AND_TEST.md](INSTALL_AND_TEST.md) ya está incluida y enlazada desde el README; se publica junto con el código. Ejecuta la instalación, pruebas de vídeo y compilación en una **copia de trabajo distinta**. Conserva la carpeta destinada a publicación sin `.venv`, datos locales, cachés ni binarios, porque el auditor también rechaza los archivos ignorados que encuentre físicamente.

## Comprobación local

Desde la raíz de esta carpeta, ejecuta:

```powershell
python scripts\normalize_public_metadata.py
python scripts\audit_public_tree.py
powershell -ExecutionPolicy Bypass -File scripts\audit_public_metadata.ps1
```

El primer comando normaliza las fechas de los archivos de código y elimina marcas de descarga de Windows. El segundo rechaza vídeos, imágenes, binarios, cachés, rutas de usuarios, secretos y directorios locales. El tercero revisa flujos alternativos de Windows. Ejecuta las pruebas automáticas en la copia de trabajo, como indica la guía completa.

Si alguna comprobación falla, no publiques: elimina de esta carpeta el elemento señalado y vuelve a ejecutarlas.

## Crear el repositorio

1. Crea un repositorio vacío en GitHub sin añadir archivos iniciales desde la web.
2. Elige una licencia y añádela a la carpeta; consulta `LICENSE-CHOICE.md`.
3. Revisa el resultado de `git status` y confirma que solo aparecen archivos de esta carpeta pública.
4. Sube el contenido a tu nuevo repositorio.

No incluyas `data/`, `assets/`, `.venv/`, `build/`, `release/`, un ejecutable local, vídeos o capturas. `.gitignore` evita que se añadan por accidente, pero el auditor es la comprobación final.

## Releases de Windows

En una copia limpia y validada:

```powershell
python -m pip install -r requirements-build.txt
python tools\build_avatar_studio_windows.py
```

Para distribuir públicamente, usa preferentemente el artefacto generado en la compilación limpia de GitHub. Una compilación local puede incorporar rutas del entorno de construcción. Comprueba el ejecutable en una cuenta de Windows de prueba antes de anunciarlo; distribuye toda su carpeta y no solo el EXE.

La automatización de GitHub incluida repite los auditores, las pruebas y la compilación en Windows.
