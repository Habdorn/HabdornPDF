# Repository Guidelines

## Project Structure & Module Organization

This repository contains a compact Windows-oriented Python desktop app for assembling and editing PDF files.

- `main.py`: main PySide6 application, including UI, page models, preview scene, image overlays, and PDF export logic.
- `requirements.txt`: runtime and packaging dependencies.
- `README.txt`: end-user instructions in Spanish.
- `EJECUTAR_EN_WINDOWS.bat`: launches the app on Windows.
- `CREAR_EXE_WINDOWS.bat`: builds a distributable executable with PyInstaller.

There is currently no dedicated `tests/` directory or separate asset folder. Keep new modules small and only split code out of `main.py` when it clearly improves maintainability.

## Build, Test, and Development Commands

Create and activate a virtual environment before installing dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the app locally:

```powershell
python main.py
```

Build the Windows executable:

```powershell
.\CREAR_EXE_WINDOWS.bat
```

The generated executable is expected under `dist\HabdornPDF\HabdornPDF.exe`.

## Coding Style & Naming Conventions

Use Python 3.11+ syntax and keep code compatible with the dependency ranges in `requirements.txt`. Follow PEP 8 with 4-space indentation. Use `snake_case` for functions, variables, and methods; `PascalCase` for classes such as `PageModel` and `MainWindow`; and uppercase constants such as `APP_NAME`.

Prefer typed dataclasses for app state models, as seen with `PageModel` and `OverlayModel`. Keep UI text in Spanish unless a feature is explicitly intended for developers.

## Testing Guidelines

No automated test framework is currently configured. For now, validate changes manually by running `python main.py` and checking the affected PDF workflow: opening PDFs, adding images or blank pages, reordering pages, inserting overlays, resizing overlays, deleting items, and exporting a new PDF.

If tests are added, place them under `tests/`, use `pytest`, and name files `test_*.py`.

## Commit & Pull Request Guidelines

This folder is not currently a Git repository, so no local commit history conventions are available. Use concise imperative commit messages if version control is added, for example `Fix overlay resize bounds` or `Add blank page export test`.

Pull requests should include a short description, manual test steps, screenshots for visible UI changes, and notes about any packaging impact.

## Security & Configuration Tips

The app works locally and should not upload user documents. Treat opened PDFs and images as private user data. Avoid adding network access, telemetry, or persistent document copies unless the behavior is clearly documented and user-controlled.
