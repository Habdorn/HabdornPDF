# PROJECT STATUS

> **Proyecto:** Habdorn PDF
> **Tipo:** aplicación de escritorio local para Windows
> **Estado del documento:** estado técnico actualizado al 13 de julio de 2026
> **Rama y revisión base:** `feature/i18n-es-en`, basada en `main` commit `119b651` (`Refactor dialogs into modular package`)
> **Fuente de verdad:** código modular bajo `app/`, `dialogs/`, `i18n/`, `models/`, `commands/`, `widgets/` y `services/`; `main.py`; dependencias; scripts; reglas e historial Git.
> **Importante:** este documento diferencia entre funcionalidad comprobable en el código, limitaciones explícitas y riesgos inferidos que todavía requieren una prueba manual para considerarse bugs reproducidos.

## 1. Resumen del proyecto

### Objetivo principal

Habdorn PDF es una aplicación gráfica de escritorio para componer y reorganizar documentos PDF sin enviar archivos a servicios externos. Permite construir un documento nuevo a partir de páginas de uno o varios PDF, imágenes y páginas A4 en blanco; modificar el orden; eliminar y rotar páginas; colocar imágenes superpuestas; y exportar el resultado a un PDF nuevo.

La aplicación está orientada a usuarios de Windows que necesitan operaciones visuales frecuentes sobre documentos, pero no requieren un editor de contenido PDF completo. La interfaz puede iniciarse en español o inglés; español es el idioma predeterminado.

### Problema que resuelve

Centraliza en una interfaz sencilla tareas que normalmente exigirían varias herramientas:

- unir páginas procedentes de distintos PDF;
- reorganizar y eliminar páginas mediante miniaturas;
- convertir imágenes en páginas A4;
- insertar páginas en blanco;
- colocar imágenes, firmas, sellos o elementos gráficos sobre páginas existentes;
- ajustar visualmente posición, tamaño y rotación de esas imágenes;
- deshacer y rehacer operaciones de edición;
- exportar preservando el contenido vectorial/raster original de las páginas PDF siempre que sea posible.

El procesamiento es local. El programa no contiene red, telemetría, subida de documentos ni persistencia automática de los archivos abiertos.

### Estado general del desarrollo

**Estimación global: 82 % para el alcance de una primera versión estable y distribuible.**

Esta cifra no significa que sea un editor PDF general al 80 %. Respecto del alcance declarado en el repositorio, las funciones esenciales están implementadas: carga, unión, miniaturas, orden, eliminación, páginas en blanco, imágenes, overlays, rotación, Undo/Redo, proyectos `.hpdf` y exportación. Lo restante se concentra en robustez, pruebas, rendimiento, recuperación automática, PDFs cifrados y edición de texto.

Estado por dimensión:

| Dimensión | Estimación | Observación |
|---|---:|---|
| Flujo principal de composición | 95 % | El recorrido importar → editar → exportar existe completo. |
| Interacción visual | 85 % | Miniaturas, selección múltiple, zoom, overlays y rotación están implementados. |
| Historial Undo/Redo | 90 % | Cubre las mutaciones principales y limita el historial a 20 comandos. |
| Robustez ante archivos problemáticos | 65 % | Hay manejo general de excepciones, pero no validación centralizada ni recuperación de referencias perdidas. |
| Rendimiento con documentos grandes | 55 % | El renderizado y refresco de miniaturas es síncrono y puede repetirse de forma costosa. |
| Pruebas y garantía de calidad | 25 % | No existe suite automática; solo están prescritas comprobaciones de compilación/importación y pruebas manuales. |
| Mantenibilidad/arquitectura | 55 % | El diseño es comprensible, pero casi toda la aplicación reside en un único archivo y `MainWindow` concentra demasiadas responsabilidades. |
| Distribución Windows | 80 % | Existe un flujo PyInstaller `--onedir`; falta automatización de release, metadatos, firma e instalador. |

## 2. Tecnologías utilizadas

### Lenguaje y plataforma

- **Python 3.11 o superior.** Las reglas del repositorio exigen Python 3.11+; `README.txt` y los scripts recomiendan 3.11 o 3.12.
- **Windows** como plataforma objetivo principal. Los scripts de ejecución y empaquetado son archivos batch.
- La lógica central es en principio portable a otros sistemas compatibles con Qt/Python, pero esa portabilidad no está documentada ni validada.

### Framework de interfaz

- **PySide6 `>=6.8,<7`**: bindings oficiales de Qt 6 para Python.
- Componentes relevantes:
  - `QMainWindow`, menús, barra de herramientas, barra de estado y diálogos;
  - `QListWidget` para miniaturas y reordenamiento por arrastre;
  - `QGraphicsScene`/`QGraphicsView`/`QGraphicsItem` para la vista previa y edición de overlays;
  - `QUndoStack`/`QUndoCommand` para Undo/Redo;
  - `QPainter`, `QPixmap`, `QImage` y `QTransform` para renderizado y transformaciones;
  - señales Qt y `QTimer` para interacción y refrescos diferidos.

### Procesamiento de PDF e imágenes

- **PyMuPDF `>=1.24,<2`**, importado como `fitz`:
  - apertura e inspección de PDF;
  - lectura de tamaños y páginas;
  - rasterización de vistas previas;
  - composición del documento de salida;
  - inclusión de páginas fuente con `show_pdf_page`;
  - inserción de imágenes y optimización al guardar.
- **Pillow `>=10,<12`**:
  - lectura de dimensiones y validación básica de imágenes;
  - rotación de imágenes superpuestas antes de incrustarlas en la exportación;
  - conversión a PNG en memoria para rotaciones arbitrarias.
- Las clases de imagen de Qt también participan en vista previa, transformación y una ruta alternativa de rotación si Pillow no puede procesar una imagen.

### Empaquetado

- **PyInstaller `>=6.10,<7`**.
- Se genera una distribución de carpeta (`--onedir`), sin consola (`--windowed`), llamada `HabdornPDF`.
- Resultado esperado: `dist\HabdornPDF\HabdornPDF.exe`.

### Biblioteca estándar

- `os`, `sys`, `uuid`, `math`;
- `copy.deepcopy` para aislar estados guardados en comandos Undo/Redo;
- `io.BytesIO` para flujos de imagen en memoria;
- `dataclasses` para modelos;
- `pathlib.Path` para etiquetas basadas en nombres de archivo;
- `typing` para anotaciones.

### Versiones y restricciones importantes

`requirements.txt` usa rangos, no versiones exactas. Esto admite actualizaciones compatibles, pero hace que dos instalaciones puedan resolver versiones distintas. Antes de un release reproducible conviene probar y registrar las versiones efectivas (`pip freeze`) sin sustituir necesariamente los rangos de desarrollo.

No hay dependencias de red en tiempo de ejecución. `pip` sí necesita acceso a internet la primera vez que instala paquetes.

## 3. Arquitectura

### Estilo arquitectónico actual

La aplicación es un **programa de escritorio dirigido por eventos con separación modular por responsabilidad**. No sigue un MVC/MVVM formal, pero distingue claramente:

- **modelo de dominio:** `PageModel` y `OverlayModel`;
- **vista/interacción especializada:** `PreviewView`, `PageListWidget` y `OverlayGraphicsItem`;
- **comandos de historial:** siete subclases de `QUndoCommand`;
- **controlador/orquestador:** `MainWindow`;
- **infraestructura de PDF e imagen:** funciones de `services/` independientes de la ventana.

`MainWindow` conserva deliberadamente la coordinación, estado de sesión, diálogos, miniaturas y sincronización visual. La implementación técnica de render, transformaciones reutilizables, imágenes y exportación se delega a servicios. La separación se realizó de forma incremental, conservando nombres y wrappers para reducir riesgo.

### Organización de carpetas

El código se organiza en `app/`, `dialogs/`, `i18n/`, `models/`, `commands/`, `widgets/` y `services/`. No existen todavía `tests/`, archivos `.ui` ni configuración de CI. Los SVG y catálogos JSON estáticos viven bajo `resources/` e `i18n/locales/`; los assets importados por el usuario se crean fuera del repositorio, dentro de workspaces administrados.

### Responsabilidades por componente

#### `OverlayModel`

Dataclass que representa una imagen colocada sobre una página:

- `id`: identificador UUID hexadecimal estable;
- `path`: ruta absoluta interna por compatibilidad temporal;
- `asset_id`: identidad canónica del asset administrado;
- `x`, `y`, `w`, `h`: geometría normalizada respecto de la página ya orientada, normalmente entre 0 y 1;
- `rotation`: rotación visual en grados.

El uso de coordenadas normalizadas desacopla el estado de la resolución de vista previa y permite exportar a puntos PDF.

#### `PageModel`

Dataclass que representa una página lógica del documento en construcción:

- `id`: identificador estable;
- `kind`: `pdf`, `image` o `blank`;
- `source`: ruta absoluta interna por compatibilidad temporal;
- `asset_id`: identidad canónica del PDF o imagen administrada; es `None` en páginas blancas;
- `page_index`: índice cero de la página dentro de un PDF fuente;
- `width_pt`/`height_pt`: dimensiones base en puntos PDF;
- `rotation`: múltiplo acumulado de 90°;
- `label`: texto de la miniatura;
- `overlays`: imágenes superpuestas en orden de inserción.

No almacena los bytes del documento. Es un modelo **referencial y no destructivo**: conserva rutas e instrucciones de composición.

#### `OverlayGraphicsItem`

Representa un overlay editable dentro de `QGraphicsScene`. Se encarga de:

- dibujar la imagen y sus controles;
- selección y movimiento;
- cuatro tiradores de redimensionamiento con proporción conservada;
- tirador de rotación; con `Shift` ajusta a intervalos de 15°;
- mantener el elemento dentro de los límites de página;
- capturar geometría anterior/posterior y notificar una edición confirmada para Undo/Redo.

#### `PreviewView`

Especializa `QGraphicsView`:

- `Ctrl + rueda` cambia el zoom;
- `Supr` o `Retroceso` emite una señal para eliminar overlays seleccionados;
- mantiene selección rectangular y renderizado suavizado.

#### `PageListWidget`

Especializa `QListWidget` para capturar el orden antes y después de un `dropEvent`. Emite ambos órdenes de IDs después de que Qt termina el movimiento. Esto permite registrar un reordenamiento nativo como un único comando Undo/Redo.

#### Comandos Undo/Redo

- `InsertPagesCommand`: inserta o retira páginas agregadas.
- `DeletePagesCommand`: elimina y restaura páginas junto con su posición y estado completo.
- `RotatePagesCommand`: aplica el giro y su inverso.
- `ReorderPagesCommand`: restaura el orden anterior o nuevo; omite el primer `redo` porque el drag ya ocurrió en la vista.
- `InsertOverlayCommand`: agrega o quita una imagen superpuesta.
- `DeleteOverlaysCommand`: elimina y restaura overlays conservando índices.
- `UpdateOverlayCommand`: alterna entre dos copias completas del estado de un overlay para movimiento, tamaño o rotación.

Todos conservan copias profundas. Esto evita que mutaciones posteriores corrompan el historial.

#### `MainWindow`

Es el composition root y controlador principal. Posee:

- diccionario de páginas por ID;
- orden visible mantenido por `page_list`;
- página activa;
- mapa de items gráficos de overlays;
- cache de miniaturas;
- `QUndoStack` con límite de 20 comandos;
- construcción y estilo de la UI;
- importación, selección, mutación y exportación;
- sincronización entre modelo, miniaturas y preview;
- mensajes de progreso y errores.

### Flujo general

1. `main()` crea `QApplication`, configura organización/nombre para `QSettings`, carga `preferences/language`, construye `Translator`, aplica el estilo Qt `Fusion`, inyecta traducción/configuración en `MainWindow` e inicia el event loop.
2. `MainWindow` inicializa estado en memoria y construye panel de miniaturas, preview, toolbar y menús.
3. Una importación produce uno o más `PageModel` y los inserta en el diccionario y lista.
4. Seleccionar una miniatura renderiza la página base y materializa sus overlays como items editables.
5. Las mutaciones se canalizan por `QUndoStack`; los métodos con sufijo `_direct` aplican cambios sin crear otro comando.
6. Las miniaturas y la preview se regeneran cuando cambia el estado relevante.
7. La exportación recorre los IDs en el orden visual y reconstruye un nuevo PDF con PyMuPDF.

### Interacción entre clases

`MainWindow` crea y conecta todas las demás clases. `PreviewView` emite una señal de eliminación; `PageListWidget` emite órdenes de página; `OverlayGraphicsItem` usa un callback asignado por `MainWindow`; y los `QUndoCommand` llaman métodos internos de la ventana. No hay bus de eventos ni inyección de dependencias.

El modelo canónico durante la sesión reside en `MainWindow.pages`. La lista visual define el orden. Los `OverlayGraphicsItem` son una representación editable temporal de los `OverlayModel` de la página activa; `save_current_overlay_positions()` sincroniza esa geometría de vuelta al modelo.

## 4. Estructura del proyecto

Árbol observado en los archivos fuente del repositorio:

```text
HabdornPDF/
├── app/
│   ├── __init__.py
│   ├── constants.py            # Nombre, A4 y formatos de imagen declarados.
│   ├── i18n_resources.py       # Catálogos JSON compilados como recursos Qt.
│   ├── lucide_resources.py     # Recursos Qt generados para incluir los SVG.
│   └── main_window.py          # UI, estado y coordinación del flujo de usuario.
├── dialogs/
│   ├── __init__.py             # API pública de diálogos y helpers.
│   ├── common.py               # Estilo, clase base y enlaces compartidos.
│   ├── help_dialog.py          # Primeros pasos y accesos de ayuda.
│   ├── shortcuts_dialog.py     # Tabla de atajos reales.
│   ├── whats_new_dialog.py     # Novedades de la versión de desarrollo.
│   ├── about_dialog.py         # Información de producto y créditos.
│   ├── third_party_dialog.py   # Carga y visor de avisos de terceros.
│   └── preferences_dialog.py   # Selección persistente de idioma y preferencias visibles.
├── i18n/
│   ├── __init__.py             # API pública de internacionalización.
│   ├── translator.py           # Carga, fallback, pluralización y QSettings.
│   └── locales/
│       ├── es.json             # Catálogo español canónico (171 claves).
│       └── en.json             # Catálogo inglés con las mismas claves.
├── models/
│   ├── __init__.py
│   ├── asset_record.py         # Metadatos inmutables de cada recurso interno.
│   ├── overlay_model.py        # Estado normalizado de imágenes superpuestas.
│   ├── page_model.py           # Estado lógico de páginas.
│   └── project_data.py         # Resultado completo de cargar un proyecto.
├── commands/
│   ├── __init__.py
│   ├── overlay_commands.py     # Undo/Redo de overlays.
│   └── page_commands.py        # Undo/Redo de páginas.
├── widgets/
│   ├── __init__.py
│   ├── overlay_graphics_item.py
│   ├── page_list_widget.py
│   └── preview_view.py
├── services/
│   ├── __init__.py
│   ├── asset_manager.py        # Workspace, copia atómica, hash y deduplicación.
│   ├── image_utils.py          # Rotación/conversión de imagen en memoria.
│   ├── pdf_exporter.py         # Construcción técnica del PDF final.
│   ├── pdf_renderer.py         # Render y transformaciones geométricas.
│   └── project_service.py      # Guardado/apertura segura del formato .hpdf.
├── resources/
│   ├── i18n.qrc                # Catálogos compilables como recursos Qt.
│   ├── lucide.qrc              # Manifiesto de recursos compilables por Qt.
│   └── icons/lucide/           # Iconos SVG lineales usados por la mini-ribbon.
├── AGENTS.md
├── THIRD_PARTY_NOTICES.md      # Atribución y licencia ISC de Lucide.
├── main.py                     # Punto de entrada mínimo.
├── requirements.txt
├── README.txt
├── EJECUTAR_EN_WINDOWS.bat
├── CREAR_EXE_WINDOWS.bat
└── PROJECT_STATUS.md
```

Directorios que pueden aparecer localmente, pero son generados y no constituyen módulos fuente:

```text
HabdornPDF/
├── .venv/                      # Entorno virtual local.
├── __pycache__/                # Bytecode de Python.
├── build/                      # Trabajo temporal de PyInstaller.
└── dist/
    └── HabdornPDF/
        └── HabdornPDF.exe      # Ejecutable y dependencias de la distribución onedir.
```

La modularización fue autorizada expresamente. Los imports son absolutos desde la raíz y los paquetes no dependen del directorio de ejecución más allá de iniciar el proyecto desde su raíz, como ya requieren los scripts existentes.

## 5. Funcionalidades implementadas

Leyenda: ✅ terminada para el alcance actual; 🟡 parcial/limitada; 🔴 pendiente.

| Funcionalidad | Estado | Qué hace y alcance real |
|---|:---:|---|
| Inicio de aplicación | ✅ | Crea ventana principal, layout dividido, toolbar, menús, estado y tema oscuro. |
| Abrir uno o varios PDF | ✅ | Selector múltiple; copia cada PDF una vez y crea páginas que comparten `asset_id` e índice. |
| Unir varios PDF | ✅ | Las páginas importadas comparten una lista ordenable y se materializan juntas al exportar. |
| Detectar PDF protegido | 🟡 | Detecta `needs_pass`, advierte y omite el archivo; no solicita contraseña. |
| Imágenes como páginas | ✅ | Admite PNG, JPEG, WebP, BMP y TIFF; crea A4 vertical u horizontal según orientación. |
| Páginas A4 en blanco | ✅ | Inserta A4 vertical en blanco después de la selección actual. |
| Miniaturas | ✅ | Renderiza contenido, rotación y overlays; muestra etiqueta y permite selección múltiple. |
| Reordenar páginas | ✅ | Drag-and-drop nativo, validación de orden e integración con Undo/Redo. |
| Eliminar páginas | ✅ | Elimina una o varias seleccionadas y permite restaurarlas con su contenido lógico. |
| Rotar páginas | ✅ | Giro múltiple de 90° izquierda/derecha; ajusta overlays y exportación. |
| Insertar imagen sobre página | ✅ | Copia/deduplica la imagen, la centra proporcionalmente y conserva su `asset_id`. |
| Seleccionar varios overlays | ✅ | `QGraphicsScene` y rubber-band permiten selección; la eliminación acepta múltiples items. |
| Mover overlay | ✅ | Arrastre limitado a la página y comando Undo/Redo al soltar. |
| Redimensionar overlay | ✅ | Cuatro esquinas, proporción conservada, tamaño mínimo y límites de página. |
| Rotar overlay | ✅ | Tirador dedicado, grados libres y ajuste de 15° con `Shift`. |
| Eliminar overlay | ✅ | Toolbar o teclas Supr/Retroceso; restaurable con Undo. |
| Zoom de preview | ✅ | `Ctrl + rueda`; al cambiar de página vuelve a encajar la vista. |
| Undo/Redo | ✅ | Inserción/eliminación/orden/rotación de páginas e inserción/eliminación/geometría de overlays; límite 20. |
| Detección de cambios pendientes | ✅ | Compara el punto limpio de `QUndoStack` y la revisión de cambios directos; Undo/Redo puede volver exactamente al estado exportado. |
| Advertencia de cierre | ✅ | Muestra una confirmación segura con “Cancelar” predeterminado cuando existen cambios sin guardar. |
| Indicador en el título | ✅ | Añade `*` a “Habdorn PDF” mientras el documento difiere del último estado exportado. |
| Estado base inicial protegido | ✅ | La primera carga de PDF o lote de imágenes en documento vacío se inserta directamente y limpia el historial, por lo que no se deshace accidentalmente el documento base. |
| Exportar PDF | ✅ | Recompone en orden, incorpora páginas PDF, imágenes, blancos, rotaciones y overlays. |
| Conservación de calidad PDF | ✅ | Usa `show_pdf_page` en vez de rasterizar las páginas PDF para la salida. |
| Progreso/cancelación de exportación | 🟡 | Hay diálogo y cancelación entre páginas; una operación pesada dentro de una página no se interrumpe. |
| Gestión de errores | 🟡 | Hay mensajes en importación/exportación y placeholder en preview; algunas excepciones de render se silencian. |
| Cache de miniaturas | 🟡 | Existe un diccionario de cache, pero el refresco vuelve a renderizar y sobrescribir miniaturas ampliamente. |
| Atajos | ✅ | `Ctrl+N` nuevo, `Ctrl+O` abrir proyecto, `Ctrl+S` guardar, `Ctrl+Shift+S` guardar como, `Ctrl+Alt+O` añadir PDF, `Ctrl+Shift+E` exportar, más Undo/Redo y giros. |
| Ejecución automatizada en Windows | ✅ | El batch crea `.venv`, instala requisitos y ejecuta. |
| Empaquetado `.exe` | ✅ | Batch PyInstaller produce distribución `onedir`. |
| Operación local/privada | ✅ | No existe código de red ni persistencia documental oculta. |
| Assets embebidos al importar | ✅ | PDF e imágenes se copian a un workspace administrado y el documento usa la copia interna. |
| Deduplicación de assets | ✅ | Reutiliza contenido idéntico por tamaño y SHA-256 sin cargar archivos completos en memoria. |
| Independencia de originales | ✅ | Preview, miniaturas, edición y exportación resuelven `asset_id`; el original puede eliminarse después de importar. |
| Manifiesto de workspace | ✅ | `workspace.json` registra versión, ID, creación y assets mediante reemplazo atómico. |
| Pantalla inicial útil | ✅ | El documento vacío muestra bienvenida, accesos para añadir contenido y apertura de `.hpdf`. |
| Estado vacío de páginas | ✅ | El panel lateral muestra instrucciones sin insertar elementos ficticios en la lista. |
| Contador de páginas | ✅ | Actualización automática para importación, eliminación, Undo/Redo, nuevo y apertura. |
| Toolbar jerarquizada | ✅ | Acciones compartidas agrupadas; guardar es secundaria, exportar principal y eliminar usa hover cauteloso. |
| Barra de estado contextual | ✅ | Informa estado guardado/modificado, página seleccionada y progreso complementario. |
| Interfaz Español/English | ✅ | 171 claves por catálogo cubren ventana, ribbon, menús, diálogos, mensajes, filtros, estados y comandos Undo/Redo. |
| Preferencia de idioma | ✅ | Guarda `es` o `en` en `QSettings` bajo `preferences/language`; el cambio se aplica al reiniciar para evitar una sesión parcialmente traducida. |
| Edición de texto PDF existente | 🔴 | Explícitamente fuera de la versión actual. |
| Guardar/abrir proyecto editable | ✅ | Contenedor `.hpdf` portable con estado JSON explícito y assets embebidos. |
| Nuevo proyecto | ✅ | Crea workspace vacío, limpia historial y registra un punto limpio. |
| Guardar proyecto/Guardar como | ✅ | Escritura ZIP temporal, verificación y reemplazo atómico del destino. |
| Abrir proyecto | ✅ | Validación completa, extracción segura a workspace nuevo y reconstrucción editable. |
| PDF con contraseña | 🔴 | Se detecta, pero no se puede desbloquear. |

## 6. Funcionalidades pendientes

No existe un backlog formal versionado. La siguiente lista combina limitaciones explícitas con trabajo necesario para llevar el producto a una versión robusta, y debe validarse con el propietario antes de ampliar alcance.

### Prioridad P0 — confiabilidad del alcance existente

1. **Crear pruebas automáticas del modelo, geometría, comandos y exportación.** Deben cubrir las tres clases de página, los cuatro giros, overlays rotados, Undo/Redo y orden.
2. **Mantener la matriz manual de regresión en cambios futuros.** La modularización fue validada manualmente en Windows con los flujos principales; debe repetirse cuando cambien render, geometría, Undo/Redo o exportación.
3. **Diagnosticar assets internos ausentes o dañados antes de exportar.** Los originales ya no son necesarios, pero una copia administrada perdida debe identificarse con precisión.
4. **Diagnosticar render en vez de ocultar cualquier excepción.** El placeholder blanco actual evita un crash, pero elimina evidencia del fallo.

### Prioridad P1 — rendimiento y experiencia básica

1. Renderizado incremental o asíncrono de miniaturas para documentos grandes.
2. Invalidación real del cache: regenerar solo páginas afectadas.
3. Indicador de carga/importación y posibilidad de cancelar procesos largos.
4. Mostrar mensajes cuando una acción no puede ejecutarse, en vez de retornar silenciosamente.
5. Estado de “documento modificado” y título de ventana informativo.
6. Navegación/zoom más completa: ajustar, 100 %, acercar/alejar y conservar zoom opcionalmente.
7. Gestión explícita del orden Z de overlays (traer al frente/enviar atrás).
8. Copiar, pegar y duplicar páginas u overlays.
9. Selección “todas las páginas” y acciones masivas más visibles.
10. Preferencias adicionales: carpeta reciente, tamaño/orientación de página en blanco y calidad. El idioma ya es editable y persistente.

### Prioridad P2 — formatos, persistencia y distribución

1. Recuperación automática ante cierre inesperado.
2. Soporte de PDFs cifrados mediante solicitud de contraseña, sin persistirla.
3. Elección de tamaño de papel, orientación y márgenes para páginas de imagen/blancas.
4. Metadatos de aplicación, icono, información de versión y recursos de PyInstaller.
5. Instalador, desinstalador, firma de código y proceso de release reproducible.
6. CI para compilación, pruebas y smoke test del paquete.
7. Archivo de bloqueo o registro de versiones probadas para builds oficiales.

### Prioridad P3 — ampliaciones de producto

1. Edición/agregado de texto.
2. Anotaciones, formas, firmas administradas, numeración y marcas de agua.
3. Recorte de páginas e imágenes.
4. Extracción de páginas como archivos independientes.
5. Optimización/compresión configurable y reporte de tamaño.
6. Soporte de enlaces, formularios, marcadores, metadatos y otros objetos PDF, si el producto lo requiere.
7. Accesibilidad, idiomas adicionales y pruebas de alto DPI.

## 7. Bugs conocidos

### Bugs/limitaciones confirmados por código o documentación

#### 1. Los PDF protegidos por contraseña no se pueden abrir

- **Gravedad:** media; alta si el flujo del usuario depende de documentos cifrados.
- **Causa:** `add_pdfs()` verifica `doc.needs_pass`, muestra una advertencia y descarta el documento.
- **Solución posible:** solicitar contraseña con un diálogo, llamar a `doc.authenticate()`, limitar intentos y mantener la contraseña solo en memoria.

#### 2. Los fallos de renderizado de preview se convierten silenciosamente en una página blanca

- **Gravedad:** media.
- **Causa:** `render_page_pixmap()` captura `Exception` sin registrar el error y devuelve un placeholder blanco.
- **Solución posible:** registrar contexto, mostrar una miniatura de error y conservar el detalle para el usuario/desarrollador.

#### 3. No existe confirmación antes de sobrescribir mediante lógica propia

- **Gravedad:** baja/media.
- **Causa:** se delega la selección al diálogo de guardado y luego se llama a `output.save(path)`; el comportamiento de confirmación depende del diálogo/plataforma.
- **Solución posible:** comprobar `Path.exists()` y confirmar explícitamente si las garantías del diálogo no son suficientes.

### Riesgos probables que necesitan reproducción antes de declararlos bugs

#### 4. Lentitud o congelamiento con muchas páginas

- **Gravedad potencial:** alta para documentos grandes.
- **Causa probable:** render síncrono en el hilo UI; `_refresh_thumbnail_layout_now()` vuelve a renderizar todas las miniaturas, y varios cambios disparan refrescos adicionales.
- **Solución posible:** invalidación por página, tareas en background con resultados entregados al hilo GUI, debounce y cache por firma de estado.

#### 5. Crecimiento de memoria por miniaturas y estados Undo

- **Gravedad potencial:** media.
- **Causa probable:** cada miniatura es un `QPixmap`; comandos guardan copias profundas de páginas y overlays. El límite de 20 contiene el historial, pero páginas grandes/muchos overlays pueden pesar.
- **Solución posible:** medir, limitar cache, almacenar estados mínimos y liberar pixmaps no visibles.

#### 6. Diferencias entre preview y exportación para rotaciones arbitrarias

- **Gravedad potencial:** media.
- **Causa probable:** preview y exportación siguen rutas de render distintas. La exportación rota a un bitmap con bounding box y lo estira al rectángulo calculado; deben probarse transparencia, TIFF multipágina, EXIF y bordes.
- **Solución posible:** pruebas golden de imagen/PDF y una función geométrica compartida.

#### 7. TIFF animado/multipágina y orientación EXIF no están definidos

- **Gravedad potencial:** baja/media.
- **Causa probable:** se toma el tamaño/frame predeterminado de Pillow o Qt sin política explícita de frames/orientación.
- **Solución posible:** normalizar EXIF, definir si se admite cada frame y validar formatos por una sola ruta.

#### 8. La cancelación puede dejar un archivo previo intacto o un resultado parcial según el punto de fallo

- **Gravedad potencial:** media.
- **Causa probable:** la salida se construye en memoria y se guarda al final, lo cual es positivo, pero no se usa ruta temporal + reemplazo atómico ni se documenta la semántica al sobrescribir.
- **Solución posible:** guardar en temporal del mismo volumen, validar y reemplazar atómicamente.

## 8. Deuda técnica

### Clase orquestadora todavía extensa

`main.py` ya es un punto de entrada mínimo. `MainWindow` supera 1.800 líneas porque sigue coordinando la UI, selección, cache, sincronización, proyectos, traducción de la superficie visual y mensajes. Esta concentración residual es aceptable para las extracciones conservadoras realizadas, pero es el mayor riesgo de mantenibilidad al agregar funciones.

### Funciones extensas o con múltiples responsabilidades

- `MainWindow.__init__`: estado, widgets, layout, conexiones y configuración.
- `render_page_pixmap`: selección de tipo, apertura, geometría, rasterización, composición y fallback.
- `export_pdf`: diálogo, progreso, composición, manejo de fuentes, guardado, cancelación y errores.
- `_apply_page_order`: validación, preservación de selección, reconstrucción del widget y preview.
- `_refresh_thumbnail_layout_now`: mezcla layout e invalidación/render completo.

### Código repetido

- búsqueda iterativa de items por `page_id` en la lista;
- refresco repetido preview + miniatura después de mutaciones;
- apertura/lectura de imágenes por Pillow y Qt en distintas rutas;
- transformación de geometría de overlays en preview, thumbnail y exportación;
- cierre defensivo de documentos en rutas normal y de excepción;
- selección/normalización de IDs y actualización de estado visual.

### Estado distribuido entre modelo y widgets

El diccionario contiene páginas, pero el orden vive en `QListWidget`; la selección y orden no tienen modelo independiente. La geometría editable vive temporalmente en `OverlayGraphicsItem` y se sincroniza manualmente. Esta dualidad exige llamadas correctas a `save_current_overlay_positions()` antes de cada transición.

### Cache incompleto

`thumbnail_cache` se escribe y se limpia al eliminar páginas, pero `_set_thumbnail` no reutiliza entradas. El nombre sugiere una optimización que no está realizada. Debe implementarse con invalidación por versión o eliminarse si se demuestra innecesario; no conviene mantener una falsa abstracción.

### Manejo amplio de excepciones

Hay `except Exception`, necesario en fronteras UI, pero en render se pierde el error. Se necesita logging local sin documentos ni datos sensibles, excepciones más específicas y mensajes accionables.

### Ausencia de pruebas y tooling

No hay `tests/`, linter, formatter configurado, type checker, cobertura ni CI. Las anotaciones son útiles pero no están verificadas. Tampoco hay fixtures PDF/imagen controlados.

### Dependencias no bloqueadas

Los rangos ofrecen flexibilidad, pero un build futuro puede cambiar por resoluciones nuevas. Para releases, registrar un lock/constraints probado o conservar un manifiesto de build.

### Codificación/documentación heredada

Los archivos deben conservar UTF-8. Todo texto nuevo visible debe añadirse a ambos catálogos y consumirse mediante `Translator`; no deben reaparecer cadenas sueltas en un solo idioma. Cualquier mojibake observado desde consolas con code page incorrecta debe verificarse a nivel de bytes/editor antes de modificar cadenas; no se debe “corregir” masivamente basándose solo en una consola mal configurada.

## 9. Decisiones importantes del proyecto

### Monolito incremental

Se eligió una sola unidad de código. Esto reduce fricción para una primera aplicación y su empaquetado, pero ahora limita pruebas y evolución. Las reglas dejan claro que la base actual es canónica: no debe reescribirse ni reorganizarse sin permiso.

### Fase 1 de interfaz

La interfaz mantiene un tema oscuro sobrio con tres niveles de superficie: ventana, panel y superficie activa. `UI_COLORS` centraliza la paleta. Menú, toolbar, panel de páginas, preview y status comparten bordes, espaciado y estados de foco/disabled.

La toolbar evolucionó a una mini-ribbon compacta con icono arriba y texto abajo. Reutiliza los mismos `QAction` del menú y separa cinco grupos: Historial, Añadir, Contenido, Página y Proyecto. `Exportar PDF` conserva el mayor contraste, `Guardar` usa jerarquía secundaria y las eliminaciones solo muestran advertencia al pasar el cursor. Los trece iconos lineales proceden de Lucide y están versionados como SVG bajo `resources/icons/lucide/`.

`resources/lucide.qrc` se compila a `app/lucide_resources.py`; `MainWindow` carga cada icono mediante una ruta Qt `:/icons/lucide/...`. Al ser un módulo Python importado normalmente, PyInstaller detecta e incorpora sus bytes sin requerir `--add-data` ni cambios en los scripts `.bat`. La bienvenida y los mensajes vacíos siguen siendo widgets visuales fuera del modelo; desaparecen al existir páginas y regresan al vaciar el documento.

### Ayuda, Preferencias e internacionalización

La barra de menús incluye `Archivo`, `Editar`, `Página` y `Ayuda`. El menú Ayuda ofrece primeros pasos, una tabla de atajos reales, novedades de la versión de desarrollo, sitio web, reporte de problemas y Acerca de. Los enlaces externos solo se abren por acción explícita mediante `QDesktopServices`; no se realizan solicitudes de red desde Python. Como no hay un correo o tracker público confirmado, `Reportar un problema` usa `https://habdorn.com` como fallback documentado.

`Editar → Preferencias…` abre un diálogo con secciones General, Idioma y Apariencia. El usuario puede elegir Español o English; Guardar persiste el código `es`/`en` con `QSettings` en `preferences/language`. El cambio se aplica únicamente en el próximo inicio y se informa mediante un diálogo, lo que evita reconstruir parcialmente una ventana ya abierta. Cancelar no escribe configuración. El tema Oscuro sigue siendo informativo y no editable.

La internacionalización usa una API propia y pequeña en `i18n/translator.py`, sin dependencias externas. `Translator.get()` resuelve claves simples y acepta formato nombrado; `plural()` selecciona variantes `.one`/`.other`. Un locale ausente o inválido cae a español; una clave ausente en el idioma activo intenta español y, si tampoco existe, devuelve `[clave]` de forma visible. Los catálogos `es.json` y `en.json` tienen exactamente las mismas 171 claves de texto.

`resources/i18n.qrc` se compila a `app/i18n_resources.py`. La importación del módulo registra `:/i18n/es.json` y `:/i18n/en.json`, por lo que la ejecución normal y PyInstaller no dependen de rutas del checkout ni necesitan cambios en los `.bat`. Para añadir un idioma futuro: crear el JSON con el conjunto completo de claves, agregarlo al QRC, regenerar el módulo con `pyside6-rcc`, incluir el código en `SUPPORTED_LOCALES` y añadir la opción traducida a Preferencias.

Los avisos de terceros se incorporan en `app/lucide_resources.py` desde `THIRD_PARTY_NOTICES.md` y se leen mediante `:/notices/THIRD_PARTY_NOTICES.md`, por lo que no dependen de rutas locales al ejecutar con PyInstaller.

Los diálogos se organizan como paquete independiente `dialogs/`: cada ventana reside en un módulo propio, mientras `common.py` concentra estilo, clase base, botón de cierre y apertura controlada de enlaces. `dialogs/__init__.py` mantiene una API pública simple para `MainWindow`. El paquete no importa `MainWindow`; cada diálogo recibe un `Translator`, y Preferencias recibe además el mismo `QSettings` de la aplicación.

### Edición no destructiva con assets administrados

El programa no modifica fuentes. Al importar, `AssetManager` crea una copia interna identificada por `asset_id`; `source/path` se conserva temporalmente apuntando a esa copia para compatibilidad. Renderer y exportador consideran `asset_id` canónico y solo usan rutas directas como fallback para modelos antiguos. La exportación crea un documento nuevo y ya no depende del original.

Cada ventana crea un workspace persistente en `%LOCALAPPDATA%\HabdornPDF\workspaces\<workspace_id>`. Si `LOCALAPPDATA` no está disponible o no puede usarse, se recurre al directorio temporal seguro del sistema. El workspace no se elimina al cerrar; abrir un `.hpdf` crea otro workspace y no existe recuperación automática de workspaces abandonados.

### Formato de proyecto `.hpdf`

Un `.hpdf` es un ZIP portable que el usuario trata como formato propio. Contiene únicamente `project.json` y `assets/<asset_id><extensión>`. El JSON guarda `format_version=1`, metadatos, orden, páginas, overlays y registros de assets sin `internal_path`. Al abrir, se valida todo el archivo antes de crear un workspace nuevo y reconstruir rutas internas.

El guardado se construye en un temporal junto al destino, se reabre y valida, y solo entonces usa `os.replace`. La apertura no usa `extractall`: cada asset se copia por bloques a un temporal controlado, se verifica por tamaño/SHA-256, se sincroniza y se renombra atómicamente.

### Dirty state orientado a proyecto

El asterisco significa cambios no guardados en `.hpdf`. Guardar o abrir proyecto registra el punto limpio; exportar PDF no modifica el dirty state. Undo/Redo conserva la semántica de retorno exacto al último guardado mediante `QUndoStack.setClean`, índice y revisión directa.

### IDs estables independientes del orden

Páginas y overlays reciben UUID hexadecimales. El orden puede cambiar sin alterar identidad; comandos y widgets se conectan por ID. Es una decisión correcta para Undo/Redo y reordenamiento.

### Orden canónico en la lista visual

`pages` es un diccionario sin semántica de orden documental; `page_list` define el orden de exportación. El reordenamiento captura listas de IDs y valida que sean permutaciones exactas.

### Modelos con dataclasses y copias profundas

Los estados son explícitos y tipados. Los comandos guardan `deepcopy` para que Undo restaure el estado histórico, no referencias mutadas.

### Undo/Redo basado en comandos

Qt gestiona la pila, disponibilidad y textos. Hay un máximo de 20 comandos para contener memoria. Los botones mantienen etiquetas fijas “Deshacer”/“Rehacer”, mientras el tooltip comunica la acción concreta. `Ctrl+Z`, el atajo estándar de redo y `Ctrl+Shift+Z` están conectados.

La primera carga que establece la base de un documento vacío no entra en historial: se inserta directamente y se limpia la pila. Las adiciones posteriores sí son reversibles. Para el drag-and-drop, el primer `redo()` se omite porque Qt ya movió el item.

### Coordenadas normalizadas de overlays

Guardar `x/y/w/h` como fracciones de la página evita depender del tamaño raster de preview. Al rotar una página en 90°, `_rotate_overlay()` transforma esas coordenadas para mantener la ubicación relativa coherente.

### Preview raster, exportación de PDF no rasterizada

La vista rasteriza para mostrar rápidamente. La salida usa `show_pdf_page`, que conserva mejor la calidad del contenido fuente que insertar una captura raster. Las imágenes, naturalmente, siguen siendo raster.

### Dos niveles de rotación

- página: múltiplos de 90°;
- overlay: ángulo libre.

En exportación se combina la orientación de página con la del overlay. Para ángulos no nativos de inserción, la imagen se rota en memoria.

### A4 para contenido creado

Una imagen importada como página se ajusta a A4 vertical u horizontal según sus dimensiones. Las páginas en blanco son A4 vertical. Las dimensiones se expresan en puntos: aproximadamente `595.276 × 841.89`.

### Privacidad local

No hay backend ni almacenamiento remoto. Es una restricción de producto y seguridad: no introducir red o telemetría sin una decisión explícita, documentada y controlada por el usuario.

### Distribución `onedir`

PyInstaller produce una carpeta, no un único ejecutable. Suele mejorar compatibilidad/carga y facilita incluir binarios Qt, pero el usuario debe copiar toda la carpeta.

## 10. Flujo interno del programa

### 1. Arranque

1. Python importa PyMuPDF, Pillow y PySide6.
2. `main()` crea `QApplication` con argumentos del proceso.
3. Configura nombre “Habdorn PDF” y estilo `Fusion`.
4. Construye `MainWindow`.
5. La ventana crea diccionarios, selección, cache y `QUndoStack(20)`.
6. Se crean scene/preview y lista de páginas; se conectan señales.
7. Se construyen paneles, splitter, toolbar, menús y estilos.
8. Se muestra la ventana y comienza `app.exec()`.

### 2. Importación de PDF

1. El usuario elige uno o varios PDF.
2. Cada archivo se valida con `fitz.open`.
3. Si requiere contraseña, se advierte y omite.
4. `AssetManager` calcula tamaño/SHA-256, deduplica y copia atómicamente al workspace.
5. El PDF interno se abre y cada página recibe el mismo `asset_id`, ruta interna, índice y dimensiones.
6. Si el documento estaba vacío, los modelos se insertan directamente y se limpia Undo.
7. Si ya había contenido, se crea `InsertPagesCommand` en la posición posterior a la página activa.
8. Se generan miniaturas y se selecciona la primera página insertada.

### 3. Importación de imágenes como páginas

1. El usuario elige imágenes.
2. Pillow valida la imagen.
3. Se importa/deduplica una copia interna y se leen sus dimensiones.
4. Se decide A4 horizontal si ancho ≥ alto; vertical en otro caso.
5. Se crea un `PageModel(kind="image")` con `asset_id`.
6. La inserción sigue la misma política de base inicial/Undo.

### 4. Selección y preview

1. Cambiar el item actual llama `on_page_changed`.
2. Primero se guardan geometrías del overlay anterior.
3. `load_page_into_preview` limpia la scene.
4. `render_page_pixmap(..., include_overlays=False)` produce la base a máximo 1.500 px.
5. La base se añade con Z=0.
6. Cada `OverlayModel` se convierte en `OverlayGraphicsItem` con geometría escalada.
7. La vista restablece zoom, encaja la página y actualiza estado.

### 5. Edición

1. Las operaciones discretas crean un comando y lo empujan a `undo_stack`.
2. Qt llama inmediatamente `redo()`; este invoca un método `_direct`.
3. Los métodos directos mutan modelo/lista y refrescan representaciones.
4. Para un overlay arrastrado/redimensionado/rotado, el item captura estado al presionar y al soltar.
5. El callback convierte píxeles de scene a coordenadas normalizadas.
6. Se crea `UpdateOverlayCommand` rotulado según el cambio dominante.
7. Undo/Redo sustituye el modelo por la copia anterior/posterior y recarga preview/thumbnail.

### 6. Reordenamiento

1. Antes del drop, `PageListWidget` registra IDs.
2. Qt efectúa el movimiento.
3. En el siguiente ciclo se emiten orden anterior y nuevo.
4. `MainWindow` valida longitud, unicidad y conjunto de IDs.
5. Se registra `ReorderPagesCommand` con `skip_first_redo=True`.
6. Undo/Redo reconstruye los items sin perder selección/página activa.

### 7. Exportación

1. Se exige al menos una página.
2. Se sincronizan overlays activos.
3. El usuario elige ruta `.pdf`.
4. Se crea diálogo de progreso y un documento PyMuPDF vacío.
5. Se recorren IDs en el orden de `page_list`.
6. Se calcula orientación y tamaño final.
7. Para página PDF, se reutiliza el documento interno abierto y se coloca la página con `show_pdf_page`.
8. Para página de imagen, se calcula un rectángulo con margen y se inserta la imagen.
9. Para blanco, basta la página nueva vacía.
10. Cada overlay se transforma de coordenadas normalizadas a puntos.
11. Si necesita rotación, se genera un stream PNG rotado; si no, se inserta directamente.
12. Se actualiza progreso y se procesan eventos.
13. Se guarda con `garbage=4`, `deflate=True`, `clean=True`.
14. Se cierran documento de salida y fuentes, y se muestra confirmación.
15. Ante error, se cierran recursos defensivamente y se muestra el detalle.

### 8. Guardado y apertura de proyecto

1. Guardar sincroniza overlays, reúne solo assets utilizados y serializa modelos explícitamente.
2. El servicio valida IDs, referencias, tipos, geometría, índices PDF, tamaños y hashes.
3. Construye y verifica un ZIP temporal antes de reemplazar el `.hpdf`.
4. Abrir valida estructura, versión, límites y rutas antes de modificar la ventana.
5. Extrae a un workspace nuevo sin usar rutas originales ni el workspace anterior.
6. `MainWindow` reemplaza estado, miniaturas y preview únicamente tras carga completa.
7. El proyecto abierto queda limpio y puede seguir editándose/exportándose.

### 9. Sincronización visual de la interfaz

1. Toda mutación existente termina actualizando contador, stacked widgets y disponibilidad de acciones.
2. Con cero páginas se muestran la bienvenida y el mensaje lateral; con contenido se muestra el preview sin cambiar su geometría.
3. La barra de estado combina dirty state, cantidad y selección.
4. Mensajes operativos son temporales y luego restauran automáticamente el estado persistente.

## 11. Dependencias

### Requisitos previos

- Windows 10/11 recomendado.
- Python 3.11 o 3.12 desde python.org.
- Durante la instalación, activar **Add Python to PATH** o disponer del launcher `py`.
- Acceso a internet para la instalación inicial desde PyPI.
- Espacio adicional para Qt, entorno virtual y build PyInstaller.

### Instalación limpia en PowerShell

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Equivalente explícito de las dependencias declaradas:

```powershell
pip install "PySide6>=6.8,<7" "PyMuPDF>=1.24,<2" "Pillow>=10,<12" "pyinstaller>=6.10,<7"
```

Si PowerShell impide activar scripts, puede usarse directamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

No instalar dependencias nuevas sin autorización. Si se necesita reproducibilidad de release, registrar versiones probadas por separado y validar el ejecutable resultante.

## 12. Cómo ejecutar el proyecto

### Método recomendado para desarrollo

```powershell
cd C:\Users\david\OneDrive\Documentos\HabdornProjects\PapersTop\HabdornPDF
.\.venv\Scripts\Activate.ps1
python main.py
```

### Método rápido para usuario Windows

Hacer doble clic en `EJECUTAR_EN_WINDOWS.bat`. El script:

1. cambia a su propia carpeta;
2. verifica el launcher `py`;
3. crea `.venv` si falta;
4. activa el entorno;
5. actualiza `pip`;
6. instala/actualiza requisitos;
7. ejecuta `main.py`.

Advertencia: este método consulta dependencias en cada ejecución y puede actualizar dentro de los rangos. Para operación estable/offline, usar un entorno ya instalado.

### Crear el ejecutable

Hacer doble clic en `CREAR_EXE_WINDOWS.bat` o ejecutarlo desde consola:

```powershell
.\CREAR_EXE_WINDOWS.bat
```

El script elimina `build`, `dist` y `HabdornPDF.spec`, y ejecuta:

```powershell
pyinstaller --noconfirm --clean --windowed --onedir --name HabdornPDF main.py
```

Resultado:

```text
dist\HabdornPDF\HabdornPDF.exe
```

Para distribuir, copiar **toda** la carpeta `dist\HabdornPDF`, no solo el `.exe`.

### Verificación mínima después de cambios

```powershell
python -m py_compile main.py
python -c "import main"
```

Después, prueba manualmente el flujo afectado. Para cambios de render/exportación, comparar visualmente el PDF exportado, no limitarse a que el archivo abra.

## 13. Próximos pasos recomendados

1. **Congelar un baseline verificable:** crear corpus pequeño de PDF/imágenes y checklist de regresión.
2. **Añadir pruebas de funciones puras y Undo/Redo** sin cambiar arquitectura general.
3. **Añadir pruebas de exportación** que inspeccionen número, dimensiones, rotación y presencia de imágenes.
4. **Mejorar diagnóstico agregado de assets internos faltantes y errores de render.**
5. **Perfilar documentos de 50, 200 y 500 páginas**, medir tiempo y memoria.
6. **Corregir invalidación de miniaturas** para renderizar solo lo modificado.
7. **Mover render pesado fuera del hilo UI**, con cuidado de no usar objetos GUI desde workers.
8. **Definir el alcance de persistencia de proyecto** con el propietario: referencias vs assets embebidos.
9. **Preparar un build reproducible y smoke test del `.exe`.**
10. **Decidir roadmap funcional**: contraseñas, texto, recorte, firma, numeración, instalador.

## 14. Archivos más importantes

### `main.py`

Punto de entrada mínimo: crea `QApplication`, configura `QSettings`, selecciona el locale guardado, construye `Translator` y `MainWindow`, e inicia el event loop.

### `app/main_window.py`

Orquestador canónico de la UI y del estado de sesión. Coordina modelos, widgets, comandos, servicios y la traducción de toda la superficie principal.

### `i18n/translator.py`, `i18n/locales/*.json` y `resources/i18n.qrc`

Contrato completo de internacionalización. El módulo carga catálogos embebidos, normaliza locales, implementa fallback y centraliza la clave persistente. Ambos JSON deben conservar idéntico conjunto de claves. Después de modificar un catálogo o el QRC debe regenerarse `app/i18n_resources.py` con `pyside6-rcc` y verificarse que el generado corresponde al manifiesto actual.

### `dialogs/*.py`

Ventanas modales de Ayuda, atajos, novedades, créditos, licencias y Preferencias. Reciben la traducción por inyección; no deben importar `MainWindow` ni crear otro catálogo global.

### `services/pdf_renderer.py` y `services/pdf_exporter.py`

Implementan respectivamente render/transformaciones y construcción del PDF final. Deben mantenerse coherentes al modificar geometría.

### `services/asset_manager.py`

Crea y mantiene el workspace, importa recursos mediante temporal + `os.replace`, calcula SHA-256 por bloques, deduplica y resuelve `asset_id` a rutas internas validadas. `workspace.json` es un manifiesto mínimo de assets, no un proyecto reabrible.

### `services/project_service.py`

Expone `save_project` y `load_project`, excepciones específicas y límites de seguridad. No conoce widgets ni dirty state. Valida ZIP/JSON/referencias, impide Zip Slip, limita entradas/tamaños y crea `ProjectData` con un `AssetManager` nuevo.

### `requirements.txt`

Contrato de compatibilidad de dependencias. Cambiar límites puede alterar Qt, formatos de imagen, PDF o empaquetado. No añadir paquetes sin autorización y pruebas.

### `AGENTS.md`

Reglas obligatorias para colaboradores/agentes: estabilidad de `main`, cambios incrementales, no reescritura, no división de `main.py` sin permiso, preservación de funciones, UTF-8, español, verificaciones y privacidad.

### `README.txt`

Documentación de usuario de primera versión. Debe actualizarse cuando cambie el flujo visible o las limitaciones. No sustituye este documento técnico.

### `EJECUTAR_EN_WINDOWS.bat`

Bootstrap de usuario/desarrollo en Windows. No modificar salvo error evidente y con autorización previa, según las reglas.

### `CREAR_EXE_WINDOWS.bat`

Build PyInstaller. Es destructivo solo respecto de artefactos generados `build/`, `dist/` y `.spec`. No modificar sin el mismo criterio de autorización.

## 15. Contexto para otro desarrollador

### Reglas de trabajo

- `main` debe representar la versión estable.
- Trabajar únicamente en la rama indicada por el usuario.
- No hacer commit ni push sin autorización explícita.
- Preservar cambios ajenos en el worktree.
- Realizar cambios pequeños, incrementales y revisables.
- No reescribir ni reorganizar el programa.
- No dividir `main.py` ni renombrar símbolos/archivos salvo necesidad autorizada.
- No modificar los `.bat` salvo bloqueo evidente y previa autorización.
- Mantener UTF-8 y paridad completa entre textos visibles en español e inglés.
- No agregar red, telemetría ni copias persistentes no controladas.

### Invariantes funcionales

Nunca debe romperse:

- abrir/unir varios PDF;
- mostrar/reordenar miniaturas;
- eliminar páginas;
- crear blancos e imágenes como páginas;
- insertar/mover/redimensionar imágenes;
- exportar conservando calidad original de PDF.

A estas capacidades obligatorias conviene añadir como baseline actual rotación y Undo/Redo, presentes en `main`.

### Convenciones

- Python 3.11+, PEP 8, cuatro espacios.
- `snake_case` para funciones/variables/métodos.
- `PascalCase` para clases.
- mayúsculas para constantes.
- modelos de estado como dataclasses tipadas.
- cadenas visibles identificadas por claves estables en ambos catálogos; nunca guardar el idioma dentro de `.hpdf`.
- la preferencia de idioma se aplica al arrancar, no en vivo; no reconstruir widgets parcialmente.
- métodos `_direct` mutan sin crear comandos; las acciones públicas deben empujar comandos cuando corresponde.
- IDs estables como UUID hex.
- geometría PDF en puntos y overlays en coordenadas normalizadas.

### Puntos delicados al modificar

1. **No crear recursión de Undo:** `redo/undo` deben llamar métodos directos, nunca acciones que vuelvan a `push()`.
2. **Sincronizar overlays antes de abandonar la preview:** si se añade una transición, revisar `save_current_overlay_positions()`.
3. **Preservar identidad y orden:** no usar índice visual como identidad permanente.
4. **Rotación tiene signos distintos:** Qt/PyMuPDF y la orientación PDF no siempre comparten convención; probar las cuatro orientaciones.
5. **Preview no es salida:** toda mejora visual debe comprobar también `export_pdf`.
6. **PDF fuente no debe rasterizarse en exportación** salvo decisión consciente; `show_pdf_page` es clave para calidad.
7. **Qt GUI en hilo principal:** si se paraleliza, no crear/manipular `QPixmap` o widgets de forma insegura desde workers.
8. **Rutas son privadas:** logs no deben volcar documentos ni contenido; si registran rutas, permitir redacción.
9. **Transparencia y perfiles de color:** cualquier cambio de conversión de imagen debe probar PNG alfa, JPEG y TIFF.
10. **Selección múltiple:** operaciones de página deben respetar todos los seleccionados y conservar página actual cuando sea posible.

### Filosofía recomendada

Mantener el enfoque local, no destructivo y predecible. Favorecer estados explícitos, transformaciones puras y comandos reversibles. Optimizar después de medir, pero corregir primero los refrescos globales evidentes. Evitar añadir abstracciones grandes en una sola entrega.

### Definición mínima de terminado para un cambio

1. Código compila e importa.
2. No cambia funciones no relacionadas.
3. El flujo afectado funciona manualmente.
4. Undo/Redo vuelve exactamente al estado anterior si aplica.
5. Miniatura, preview y PDF exportado coinciden.
6. Mensajes visibles permanecen completos y coherentes tanto en español como en inglés.
7. No se añaden dependencias/red/persistencia sin aprobación.
8. Se actualiza documentación pertinente.

## 16. Changelog resumido

Basado en el historial Git disponible:

### 29 de junio de 2026

- `0ad8d78` — **Initial commit**: primera base funcional.
- `bcbfcfe` — **Foundation cleanup and project rules**: limpieza de fundamentos y establecimiento de reglas del repositorio.
- `0d79e80` — **Add page and overlay rotation improvements**: mejoras de rotación de páginas y overlays.

### 30 de junio de 2026

- `9ad8b4b` — **Stable ListMode page reordering checkpoint**: estabilización del reordenamiento en modo lista.
- `5146d25` — **Restore stable undo and redo controls**: recuperación de controles estables de historial.
- `b4f53b9` — **Keep fixed undo and redo button labels**: etiquetas fijas, detalle de comando en tooltip.
- `97e5a68` — **Protect PDF base state and reorder undo**: protección del estado PDF inicial y Undo de reordenamiento.
- `72982c9` — **Protect initial image base and limit undo history**: misma protección para imágenes iniciales y límite de historial.
- `c2a541e` — **Complete stable undo and redo history**: consolidación estable del historial, actual `HEAD` de `main` al auditar.

### 11 de julio de 2026 — cambio local validado, pendiente de commit

- Modularización incremental autorizada y validada manualmente en Windows: punto de entrada, modelos, widgets, comandos y servicios separados sin nuevas dependencias ni cambios visibles intencionales.
- En `feature/dirty-state`, funcionalidad validada manualmente en Windows: detección centralizada de cambios pendientes, título con asterisco, punto limpio ligado a exportación exitosa y confirmación segura al cerrar.
- En `feature/embedded-assets`, primera etapa validada manualmente en Windows: workspace persistente, manifiesto atómico, copias internas deduplicadas e independencia de los originales; todavía sin formato `.hpdf` ni reapertura.
- En `feature/hpdf-projects`, funcionalidad validada manualmente en Windows: formato `.hpdf` v1, guardado/apertura portables, dirty state basado en proyecto, menú Archivo ampliado y validación defensiva del contenedor.
- En `feature/ui-phase-1`, limpieza visual conservadora: toolbar agrupada, pantalla inicial, estados vacíos, contador, status contextual, espaciado y jerarquía de acciones.
- En `feature/ui-ribbon-lucide`, cambio visual pendiente de validación manual: mini-ribbon de cinco grupos, trece SVG Lucide embebidos como recursos Qt, acción principal de exportación y estilos neutrales para eliminaciones.
- En `feature/help-and-preferences`, primera etapa pendiente de validación manual: menú Ayuda, diálogos informativos, enlaces explícitos, avisos de terceros embebidos y Preferencias sin controles ficticios ni persistencia.
- En `feature/modular-dialogs`, refactorización estructural pendiente de validación manual: `app/dialogs.py` sustituido por un paquete de módulos pequeños con API pública estable, sin cambios visibles ni internacionalización.

### 13 de julio de 2026 — cambio local pendiente de validación manual y commit

- En `feature/i18n-es-en`, interfaz bilingüe Español/English mediante 171 claves JSON por catálogo, recursos Qt embebidos, fallback a español e inyección de `Translator` en ventana, comandos y diálogos.
- Preferencia `preferences/language` persistida con `QSettings`; el cambio se aplica al reiniciar y no altera el contenido portable de los proyectos `.hpdf`.
- Verificación automatizada local de 40 casos completada, incluida apertura/guardado `.hpdf` entre idiomas y exportación PDF; resta la validación visual manual en Windows y del ejecutable PyInstaller.

La historia muestra evolución incremental desde la primera versión hacia rotación, reordenamiento robusto y Undo/Redo estable. No se observan tags/releases versionados ni changelog previo.

## 17. Evaluación del proyecto

### Arquitectura — 6/10

Para una primera versión, el diseño es pragmático y coherente: modelos pequeños, IDs estables, composición no destructiva, sistema de comandos Qt y separación mínima de widgets especializados. El principal defecto es la concentración en `MainWindow` y la ausencia de fronteras entre dominio, render e infraestructura.

**Riesgo:** cada función nueva aumenta el número de rutas que deben mantener coherencia entre modelo, scene, miniatura y exportación.

**Recomendación:** no hacer una reescritura. Extraer primero lógica pura bajo pruebas cuando exista autorización.

### Mantenibilidad — 5.5/10

Aspectos positivos:

- nombres generalmente descriptivos;
- anotaciones y dataclasses;
- operaciones directas separadas de comandos;
- historial Git incremental;
- reglas claras del repositorio;
- tamaño todavía abordable por una persona.

Aspectos negativos:

- archivo grande y controlador dominante;
- sin tests;
- duplicación geométrica/render;
- excepciones amplias;
- estado repartido entre modelos y widgets;
- escasa documentación interna previa a este archivo.

### Escalabilidad — 4.5/10

La aplicación puede manejar razonablemente documentos pequeños/medianos, pero su escalabilidad funcional y de rendimiento es limitada. El render síncrono global de miniaturas y la dependencia de rutas externas serán los primeros límites. La arquitectura actual tampoco es ideal para edición de texto, múltiples documentos, proyectos persistentes o procesos en background.

### Calidad del código — 6.5/10

El código evidencia cuidado en problemas difíciles: geometría, límites, rotación, snapshots de Undo y conservación de páginas PDF. El manejo de recursos suele ser defensivo. Sin embargo, la falta de pruebas impide convertir esa calidad aparente en garantía. También hay imports potencialmente no usados (`QPushButton`, `BytesIO`, según revisión actual), cache infrautilizado y métodos extensos.

### Riesgos futuros

1. **Regresiones geométricas** por mantener implementaciones paralelas para preview/exportación.
2. **Pérdida de trabajo ante fallos del proceso** mientras no exista persistencia, autosave o recuperación; el cierre normal ya advierte cambios pendientes.
3. **Rendimiento UI** con crecimiento de páginas y miniaturas.
4. **Fuentes desaparecidas** debido al modelo referencial.
5. **Cambios de dependencias** dentro de rangos sin build reproducible.
6. **Expansión descontrolada de `MainWindow`** si se añaden funciones sin fronteras.
7. **Falsa confianza** al no existir pruebas automáticas ni matriz de fixtures.
8. **Complejidad PDF oculta:** cajas, transparencia, color, páginas dañadas, cifrado, anotaciones y recursos atípicos.
9. **Distribución Windows:** antivirus, firma, rutas Unicode, alto DPI y entornos sin runtime deben verificarse.

### Recomendación senior final

El proyecto está en un buen punto para estabilización, no para reescritura. El núcleo de producto ya demuestra valor y las decisiones principales —procesamiento local, edición no destructiva, IDs, dataclasses, comandos Undo/Redo y `show_pdf_page`— son sólidas.

La inversión de mayor retorno es construir una red de seguridad alrededor de lo existente: fixtures, pruebas geométricas/exportación, checklist de GUI, diagnóstico de fuentes y protección contra cierre. Después debe atacarse el rendimiento de miniaturas. La arquitectura ya fue modularizada de forma gradual y debe conservar estas fronteras sin una nueva reorganización amplia.

Una IA o desarrollador nuevo debe comenzar leyendo `AGENTS.md`, este documento y luego `main.py` en este orden: modelos → widgets → comandos → estado de `MainWindow` → inserción/eliminación → preview → geometría → exportación. Antes de proponer una abstracción, debe demostrar qué duplicación o riesgo elimina y preservar exactamente el comportamiento actual.

---

## Apéndice A. Mapa rápido de clases y estado

```text
QApplication
└── MainWindow
    ├── pages: Dict[page_id, PageModel]
    │   └── PageModel.overlays: List[OverlayModel]
    ├── page_list: PageListWidget       ← orden documental y selección
    ├── scene: QGraphicsScene
    │   ├── pixmap de página base
    │   └── OverlayGraphicsItem[]       ← edición temporal de overlays
    ├── preview: PreviewView
    ├── thumbnail_cache
    └── undo_stack: QUndoStack
        └── QUndoCommand[]
```

## Apéndice B. Matriz mínima de regresión manual

| Caso | Verificación |
|---|---|
| PDF único/múltiple | Conteo, etiquetas, orden, preview y exportación. |
| PDF vertical/horizontal | Tamaño y orientación correctos. |
| Imagen vertical/horizontal | A4 correspondiente, proporción y margen. |
| Página blanca | A4 blanco y exportación. |
| Reordenar una/varias veces | Orden final y Undo/Redo completo. |
| Eliminar una/varias páginas | Selección posterior y restauración exacta. |
| Rotar 90/180/270/360 | Preview, thumbnail, overlays y salida coinciden. |
| Overlay PNG alfa/JPEG | Inserción, transparencia, proporción y calidad. |
| Mover/redimensionar/rotar | Límites, handles y Undo/Redo por operación. |
| Varias imágenes | Selección rectangular y eliminación/restauración múltiple. |
| Exportación cancelada | No produce salida corrupta ni bloquea UI. |
| Fuente movida | Mensaje comprensible y recuperación controlada. |
| Documento grande | Tiempo, memoria y respuesta de UI. |
| Build PyInstaller | Inicio en equipo limpio y flujo completo. |
| Español / English | Reiniciar tras guardar cada idioma; revisar menús, ribbon, diálogos, mensajes, filtros, estados, pluralización y atajos. |
| Proyecto entre idiomas | Guardar `.hpdf` en un idioma, abrir/editar/guardar en el otro y comprobar que el JSON no contiene preferencia de idioma. |

## Apéndice C. Alcance explícitamente no presente

No asumir que el proyecto ya soporta: edición de texto existente, OCR, formularios, firmas criptográficas, redacción segura, marcadores, enlaces, contraseñas, autosave, recuperación tras crash, migraciones `.hpdf`, pestañas, impresión, escáner, nube, colaboración, telemetría, actualizaciones automáticas, instalador o firma del ejecutable.

La interfaz actual no incluye panel de propiedades, temas múltiples, modo claro, preferencias adicionales al idioma, cambio de idioma en vivo, animaciones complejas ni drag-and-drop de archivos.
