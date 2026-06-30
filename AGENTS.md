# Instrucciones del repositorio

Habdorn PDF es una aplicación de escritorio para Windows escrita en Python/PySide6. La versión actual funciona y es la base canónica del proyecto.

## Ramas y estabilidad

- La rama `main` representa siempre la versión estable.
- Trabaja solamente sobre la rama indicada por el usuario.
- No hagas commits ni push sin autorización explícita.
- Las mejoras deben ser incrementales, pequeñas y fáciles de revisar.

## Reglas de cambio

- No reescribas el programa desde cero.
- No reorganices la arquitectura ni dividas `main.py` salvo autorización expresa.
- No elimines ni sustituyas funciones existentes sin autorización.
- No cambies nombres de clases, métodos, variables, archivos ni scripts si no es indispensable para la tarea aprobada.
- Antes de cambios grandes, informa qué archivos serán afectados y espera confirmación si el alcance no fue pedido con claridad.
- Después de cada cambio, ejecuta verificaciones apropiadas y seguras.
- Mantén los archivos de texto en UTF-8.
- Mantén el texto visible de la aplicación en español.

## Funciones obligatorias a conservar

Cualquier cambio debe conservar estas capacidades:

- abrir y unir varios PDF;
- mostrar y reordenar miniaturas;
- eliminar páginas;
- agregar páginas en blanco;
- agregar imágenes como páginas;
- insertar, mover y redimensionar imágenes;
- exportar conservando la calidad original.

## Estructura del proyecto

- `main.py`: aplicación principal PySide6, modelos de página, vista previa, miniaturas, overlays de imagen y exportación PDF.
- `requirements.txt`: dependencias de ejecución y empaquetado.
- `README.txt`: instrucciones para usuarios en español.
- `EJECUTAR_EN_WINDOWS.bat`: ejecuta la aplicación en Windows.
- `CREAR_EXE_WINDOWS.bat`: crea el ejecutable distribuible con PyInstaller.

No hay actualmente un directorio `tests/` ni una carpeta separada de assets. Si se agregan módulos, deben ser pequeños y estar justificados por mantenibilidad real.

## Comandos de desarrollo

Crear y activar entorno virtual antes de instalar dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Ejecutar la aplicación:

```powershell
python main.py
```

Crear el ejecutable:

```powershell
.\CREAR_EXE_WINDOWS.bat
```

El ejecutable generado debe quedar en `dist\HabdornPDF\HabdornPDF.exe`.

## Estilo de código

Usa Python 3.11+ y conserva compatibilidad con los rangos de `requirements.txt`. Sigue PEP 8 con indentación de 4 espacios. Usa `snake_case` para funciones, variables y métodos; `PascalCase` para clases como `PageModel` y `MainWindow`; y constantes en mayúsculas como `APP_NAME`.

Prefiere dataclasses tipadas para modelos de estado, como `PageModel` y `OverlayModel`.

## Verificaciones

No hay framework automático configurado. Para cambios de código, ejecuta como mínimo comprobaciones seguras:

```powershell
python -m py_compile main.py
python -c "import main"
```

Si las dependencias ya están instaladas y el cambio lo amerita, también puedes iniciar la aplicación con:

```powershell
python main.py
```

No instales dependencias nuevas sin autorización. Para validación manual, revisa el flujo afectado: abrir PDF, agregar imágenes o páginas en blanco, reordenar páginas, insertar overlays, mover y redimensionar overlays, eliminar elementos y exportar un PDF nuevo.

Si se agregan tests, colócalos en `tests/`, usa `pytest` y nombra los archivos `test_*.py`.

## Scripts de Windows

No modifiques `EJECUTAR_EN_WINDOWS.bat` ni `CREAR_EXE_WINDOWS.bat`, salvo que exista un error evidente que impida ejecutar la aplicación. En ese caso, informa primero el problema y espera autorización.

## Seguridad y privacidad

La aplicación trabaja localmente y no debe subir documentos del usuario. Trata los PDF e imágenes abiertos como datos privados. Evita agregar red, telemetría o copias persistentes de documentos salvo que el comportamiento esté documentado y controlado por el usuario.
