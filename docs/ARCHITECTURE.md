# Arquitectura

```text
Vídeo local elegido por el usuario
            │
            ▼
Importar perfil local ──► data/studio/ (ignorado por Git)
            │
            ▼
Análisis de segmentos ──► revisión manual
            │                     │
            └─────────────────────┘
                      │
                      ▼
Controlador de avatar local
          │                       │
          ▼                       ▼
   Vista de escritorio     OBS Virtual Camera
                                      │
                                      ▼
                         Aplicación elegida por el usuario
```

## Límites de datos

El repositorio público contiene código y plantillas. El perfil importado contiene una ruta local al vídeo, configuraciones y resultados de análisis; por eso se crea en el área local de datos y se ignora mediante Git.

El controlador reproduce segmentos del vídeo original. No transforma un vídeo de una persona en otro ni modifica el archivo fuente.

## Ejecución compilada

Al usar el ejecutable, el código se empaqueta con las herramientas seguras necesarias. El ejecutable no depende de una ruta del ordenador que realizó la compilación. Crea su área de datos local bajo `%LOCALAPPDATA%\AvatarStudio`, o en la ubicación que indique `AVATAR_STUDIO_DATA_DIR`.
