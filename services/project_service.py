from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Mapping, Optional, Tuple

import fitz
from PIL import Image

from models.asset_record import AssetRecord
from models.overlay_model import OverlayModel
from models.page_model import PageModel
from models.project_data import ProjectData
from services.asset_manager import AssetManager

FORMAT_VERSION = 1
MAX_PROJECT_UNCOMPRESSED_BYTES = 8 * 1024**3
MAX_ASSETS = 5000
MAX_PAGES = 10000
MAX_OVERLAYS_PER_PAGE = 5000
MAX_JSON_BYTES = 64 * 1024**2
MAX_ZIP_ENTRIES = 6000
MAX_COMPRESSION_RATIO = 1000
CHUNK_SIZE = 1024 * 1024

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_EXTENSION_PATTERN = re.compile(r"^\.[a-z0-9]{1,10}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ProjectError(Exception):
    pass


class ProjectFormatError(ProjectError):
    pass


class ProjectVersionError(ProjectError):
    pass


class ProjectAssetError(ProjectError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_project_path(project_path: str) -> str:
    path = Path(project_path).expanduser()
    if path.suffix.lower() != ".hpdf":
        path = path.with_name(path.name + ".hpdf")
    return str(path.resolve())


def save_project(
    project_path: str,
    pages: Mapping[str, PageModel],
    page_order: Iterable[str],
    asset_manager: AssetManager,
    metadata: Mapping[str, str],
) -> str:
    final_path = Path(normalize_project_path(project_path))
    final_path.parent.mkdir(parents=True, exist_ok=True)
    order = list(page_order)
    used_assets = _validate_models_and_collect_assets(
        pages,
        order,
        asset_manager.assets,
    )
    for asset_id, record in used_assets.items():
        _validate_source_asset(
            record,
            Path(asset_manager.resolve_path(asset_id)),
            asset_manager,
        )
    _validate_extracted_content(pages, used_assets)
    project_json, archive_assets = _build_project_json(
        pages,
        order,
        used_assets,
        metadata,
    )
    json_bytes = json.dumps(
        project_json,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"
    if len(json_bytes) > MAX_JSON_BYTES:
        raise ProjectFormatError("Los datos del proyecto exceden el límite permitido.")

    temporary = final_path.parent / f".{final_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            archive.writestr(
                "project.json",
                json_bytes,
                compress_type=zipfile.ZIP_DEFLATED,
            )
            for asset_id, record in used_assets.items():
                archive_path = archive_assets[asset_id]
                internal_path = Path(asset_manager.resolve_path(asset_id))
                archive.write(
                    internal_path,
                    archive_path,
                    compress_type=zipfile.ZIP_STORED,
                )

        _read_and_validate_archive(temporary)
        os.replace(temporary, final_path)
        return str(final_path)
    except ProjectError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise ProjectError(f"No se pudo guardar el proyecto: {exc}") from exc


def load_project(
    project_path: str,
    workspace_base: Optional[Path] = None,
) -> ProjectData:
    source_path = Path(project_path).expanduser().resolve()
    document, asset_specs = _read_and_validate_archive(source_path)
    manager: Optional[AssetManager] = None
    try:
        manager = AssetManager(base_dir=workspace_base)
        records = _extract_assets(source_path, asset_specs, manager)
        pages, page_order = _deserialize_pages(document, records)
        _validate_extracted_content(pages, records)
        project = document["project"]
        return ProjectData(
            format_version=FORMAT_VERSION,
            project_id=project["id"],
            project_name=project["name"],
            created_at=project["created_at"],
            modified_at=project["modified_at"],
            pages=pages,
            page_order=page_order,
            assets=records,
            workspace_id=manager.workspace_id,
            source_project_path=str(source_path),
            asset_manager=manager,
        )
    except ProjectError:
        if manager is not None:
            shutil.rmtree(manager.workspace_path, ignore_errors=True)
        raise
    except Exception as exc:
        if manager is not None:
            shutil.rmtree(manager.workspace_path, ignore_errors=True)
        raise ProjectError(f"No se pudo abrir el proyecto: {exc}") from exc


def _build_project_json(
    pages: Mapping[str, PageModel],
    page_order: list[str],
    assets: Mapping[str, AssetRecord],
    metadata: Mapping[str, str],
) -> Tuple[dict, Dict[str, str]]:
    project_id = _required_identifier(metadata.get("id"), "proyecto")
    name = _required_string(metadata.get("name"), "nombre del proyecto")
    created_at = _required_string(metadata.get("created_at"), "fecha de creación")
    modified_at = _required_string(metadata.get("modified_at"), "fecha de modificación")

    archive_assets: Dict[str, str] = {}
    serialized_assets = []
    for asset_id, record in assets.items():
        extension = _validate_extension(record.extension)
        archive_path = f"assets/{asset_id}{extension}"
        if archive_path in archive_assets.values():
            raise ProjectAssetError("Dos assets usan la misma ruta interna.")
        archive_assets[asset_id] = archive_path
        serialized_assets.append(
            {
                "id": record.id,
                "archive_path": archive_path,
                "original_path": record.original_path,
                "original_name": record.original_name,
                "extension": extension,
                "media_type": record.media_type,
                "size_bytes": record.size_bytes,
                "sha256": record.sha256,
                "created_at": record.created_at,
            }
        )

    serialized_pages = []
    for page_id in page_order:
        page = pages[page_id]
        serialized_pages.append(
            {
                "id": page.id,
                "kind": page.kind,
                "asset_id": page.asset_id,
                "page_index": page.page_index,
                "width_pt": page.width_pt,
                "height_pt": page.height_pt,
                "rotation": page.rotation,
                "label": page.label,
                "overlays": [
                    {
                        "id": overlay.id,
                        "asset_id": overlay.asset_id,
                        "x": overlay.x,
                        "y": overlay.y,
                        "w": overlay.w,
                        "h": overlay.h,
                        "rotation": overlay.rotation,
                    }
                    for overlay in page.overlays
                ],
            }
        )

    return (
        {
            "format_version": FORMAT_VERSION,
            "project": {
                "id": project_id,
                "name": name,
                "created_at": created_at,
                "modified_at": modified_at,
            },
            "page_order": page_order,
            "pages": serialized_pages,
            "assets": serialized_assets,
        },
        archive_assets,
    )


def _validate_models_and_collect_assets(
    pages: Mapping[str, PageModel],
    page_order: list[str],
    assets: Mapping[str, AssetRecord],
) -> Dict[str, AssetRecord]:
    if len(pages) > MAX_PAGES:
        raise ProjectFormatError("El proyecto contiene demasiadas páginas.")
    if len(page_order) != len(pages) or len(set(page_order)) != len(page_order):
        raise ProjectFormatError("El orden de páginas no es válido.")
    if set(page_order) != set(pages):
        raise ProjectFormatError("El orden no contiene todas las páginas.")

    used_ids: set[str] = set()
    overlay_ids: set[str] = set()
    for page_id in page_order:
        page = pages[page_id]
        if page.id != page_id:
            raise ProjectFormatError("La identidad de una página no coincide.")
        _validate_page_values(page)
        if page.kind == "blank":
            if page.asset_id is not None:
                raise ProjectFormatError("Una página en blanco no debe tener asset.")
        else:
            if page.asset_id is None or page.asset_id not in assets:
                raise ProjectAssetError("Falta un asset requerido por una página.")
            expected_type = "pdf" if page.kind == "pdf" else "image"
            if assets[page.asset_id].media_type != expected_type:
                raise ProjectAssetError("El tipo de asset de una página no es válido.")
            used_ids.add(page.asset_id)
        if len(page.overlays) > MAX_OVERLAYS_PER_PAGE:
            raise ProjectFormatError("Una página contiene demasiados overlays.")
        for overlay in page.overlays:
            _validate_overlay_values(overlay)
            if overlay.id in overlay_ids:
                raise ProjectFormatError("Hay IDs de overlays duplicados.")
            overlay_ids.add(overlay.id)
            if overlay.asset_id is None or overlay.asset_id not in assets:
                raise ProjectAssetError("Falta un asset requerido por un overlay.")
            if assets[overlay.asset_id].media_type != "image":
                raise ProjectAssetError("Un overlay debe usar un asset de imagen.")
            used_ids.add(overlay.asset_id)

    if len(used_ids) > MAX_ASSETS:
        raise ProjectFormatError("El proyecto contiene demasiados assets.")
    return {asset_id: assets[asset_id] for asset_id in sorted(used_ids)}


def _validate_page_values(page: PageModel) -> None:
    _required_identifier(page.id, "página")
    if page.kind not in {"pdf", "image", "blank"}:
        raise ProjectFormatError("El tipo de página no es válido.")
    if not _is_positive_finite(page.width_pt) or not _is_positive_finite(page.height_pt):
        raise ProjectFormatError("Las dimensiones de una página no son válidas.")
    if type(page.rotation) is not int or page.rotation not in {0, 90, 180, 270}:
        raise ProjectFormatError("La rotación de una página no es válida.")
    if not isinstance(page.label, str):
        raise ProjectFormatError("La etiqueta de una página no es válida.")
    if page.kind == "pdf":
        if type(page.page_index) is not int or page.page_index < 0:
            raise ProjectFormatError("El índice de una página PDF no es válido.")
    elif page.page_index is not None:
        raise ProjectFormatError("Solo las páginas PDF pueden tener índice.")


def _validate_overlay_values(overlay: OverlayModel) -> None:
    _required_identifier(overlay.id, "overlay")
    for value in (overlay.x, overlay.y, overlay.w, overlay.h, overlay.rotation):
        if not _is_finite_number(value):
            raise ProjectFormatError("La geometría de un overlay no es válida.")
    if overlay.w <= 0 or overlay.h <= 0:
        raise ProjectFormatError("El tamaño de un overlay debe ser positivo.")


def _validate_source_asset(
    record: AssetRecord,
    path: Path,
    manager: AssetManager,
) -> None:
    manager.get_asset(record.id)
    resolved = path.resolve()
    try:
        resolved.relative_to(manager.workspace_path.resolve())
    except ValueError as exc:
        raise ProjectAssetError("Un asset escapa del workspace administrado.") from exc
    if not resolved.is_file() or resolved.stat().st_size != record.size_bytes:
        raise ProjectAssetError(f"Falta el asset interno: {record.original_name}")
    size, digest = _hash_path(resolved)
    if size != record.size_bytes or digest != record.sha256:
        raise ProjectAssetError(f"El asset interno está dañado: {record.original_name}")


def _read_and_validate_archive(path: Path) -> Tuple[dict, Dict[str, dict]]:
    if not path.exists() or not path.is_file():
        raise ProjectFormatError("El archivo de proyecto no existe.")
    if not zipfile.is_zipfile(path):
        raise ProjectFormatError("El archivo de proyecto está dañado o no es válido.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ProjectFormatError("El proyecto contiene demasiadas entradas.")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ProjectFormatError("El proyecto contiene entradas duplicadas.")
            if "project.json" not in names:
                raise ProjectFormatError("Falta project.json en el proyecto.")
            total_size = 0
            for info in infos:
                _validate_archive_entry(info)
                total_size += info.file_size
                if total_size > MAX_PROJECT_UNCOMPRESSED_BYTES:
                    raise ProjectFormatError("El proyecto excede el tamaño permitido.")
            json_info = archive.getinfo("project.json")
            if json_info.file_size > MAX_JSON_BYTES:
                raise ProjectFormatError("project.json excede el tamaño permitido.")
            raw_json = archive.read(json_info)
            try:
                document = json.loads(raw_json.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProjectFormatError("project.json no contiene JSON válido.") from exc
            asset_specs = _validate_document_structure(document)
            expected_names = {"project.json"} | {
                spec["archive_path"] for spec in asset_specs.values()
            }
            missing_names = expected_names - set(names)
            if missing_names:
                raise ProjectAssetError(
                    "Falta un recurso interno necesario para abrir el proyecto."
                )
            if set(names) - expected_names:
                raise ProjectFormatError("El proyecto contiene entradas inesperadas.")
            for asset_id, spec in asset_specs.items():
                info = archive.getinfo(spec["archive_path"])
                if info.file_size != spec["size_bytes"]:
                    raise ProjectAssetError("El tamaño declarado de un asset no coincide.")
                size, digest = _hash_zip_entry(archive, info)
                if size != spec["size_bytes"] or digest != spec["sha256"]:
                    raise ProjectAssetError("El hash de un asset no coincide.")
            return document, asset_specs
    except ProjectError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ProjectFormatError("El archivo de proyecto está dañado o no es válido.") from exc


def _validate_archive_entry(info: zipfile.ZipInfo) -> None:
    name = info.filename
    if info.file_size < 0 or info.compress_size < 0 or info.is_dir():
        raise ProjectFormatError("El proyecto contiene una entrada no válida.")
    if info.flag_bits & 0x1:
        raise ProjectFormatError("El proyecto contiene una entrada cifrada.")
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise ProjectFormatError("El proyecto usa una compresión no compatible.")
    unix_mode = (info.external_attr >> 16) & 0o170000
    if unix_mode == 0o120000:
        raise ProjectFormatError("El proyecto contiene un enlace simbólico.")
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or "\\" in name:
        raise ProjectFormatError("El proyecto contiene una ruta interna insegura.")
    if re.match(r"^[A-Za-z]:", name) or name.startswith("/"):
        raise ProjectFormatError("El proyecto contiene una ruta absoluta.")
    if name != "project.json":
        if len(pure.parts) != 2 or pure.parts[0] != "assets":
            raise ProjectFormatError("El proyecto contiene una entrada inesperada.")
        if not pure.parts[1] or not _safe_archive_filename(pure.parts[1]):
            raise ProjectFormatError("El proyecto contiene un nombre interno inseguro.")
    if info.file_size > 10 * 1024**2:
        if info.compress_size == 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ProjectFormatError("El proyecto tiene una compresión sospechosa.")


def _validate_document_structure(document: object) -> Dict[str, dict]:
    if not isinstance(document, dict):
        raise ProjectFormatError("El archivo no contiene un formato de proyecto válido.")
    version = document.get("format_version")
    if type(version) is not int:
        raise ProjectFormatError("El archivo no contiene un formato de proyecto válido.")
    if version > FORMAT_VERSION:
        raise ProjectVersionError(
            "Este proyecto fue creado con una versión más reciente de Habdorn PDF."
        )
    if version != FORMAT_VERSION:
        raise ProjectFormatError("El archivo no contiene un formato de proyecto válido.")
    project = document.get("project")
    pages = document.get("pages")
    order = document.get("page_order")
    assets = document.get("assets")
    if not isinstance(project, dict) or not isinstance(pages, list):
        raise ProjectFormatError("La estructura de project.json no es válida.")
    if not isinstance(order, list) or not isinstance(assets, list):
        raise ProjectFormatError("La estructura de project.json no es válida.")
    _required_identifier(project.get("id"), "proyecto")
    _required_string(project.get("name"), "nombre del proyecto")
    _required_string(project.get("created_at"), "fecha de creación")
    _required_string(project.get("modified_at"), "fecha de modificación")
    if len(pages) > MAX_PAGES or len(assets) > MAX_ASSETS:
        raise ProjectFormatError("El proyecto supera los límites permitidos.")

    asset_specs: Dict[str, dict] = {}
    archive_paths: set[str] = set()
    for raw in assets:
        spec = _validate_asset_spec(raw)
        asset_id = spec["id"]
        if asset_id in asset_specs or spec["archive_path"] in archive_paths:
            raise ProjectFormatError("Hay assets duplicados en el proyecto.")
        asset_specs[asset_id] = spec
        archive_paths.add(spec["archive_path"])

    page_ids: set[str] = set()
    overlay_ids: set[str] = set()
    for raw_page in pages:
        _validate_serialized_page(raw_page, asset_specs, page_ids, overlay_ids)
    if any(not isinstance(item, str) for item in order):
        raise ProjectFormatError("El orden de páginas no es válido.")
    if len(order) != len(set(order)) or set(order) != page_ids or len(order) != len(pages):
        raise ProjectFormatError("El orden de páginas no es válido.")
    return asset_specs


def _validate_asset_spec(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ProjectFormatError("Un registro de asset no es válido.")
    asset_id = _required_identifier(raw.get("id"), "asset")
    extension = _validate_extension(raw.get("extension"))
    archive_path = raw.get("archive_path")
    expected_path = f"assets/{asset_id}{extension}"
    if archive_path != expected_path:
        raise ProjectFormatError("La ruta interna de un asset no es válida.")
    media_type = raw.get("media_type")
    if media_type not in {"pdf", "image"}:
        raise ProjectFormatError("El tipo de un asset no es válido.")
    size = raw.get("size_bytes")
    if type(size) is not int or size < 0:
        raise ProjectFormatError("El tamaño de un asset no es válido.")
    digest = raw.get("sha256")
    if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
        raise ProjectFormatError("El hash de un asset no es válido.")
    _required_string(raw.get("original_path"), "ruta original")
    _required_string(raw.get("original_name"), "nombre original")
    created_at = raw.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        raise ProjectFormatError("La fecha de un asset no es válida.")
    return raw


def _validate_serialized_page(
    raw: object,
    assets: Mapping[str, dict],
    page_ids: set[str],
    overlay_ids: set[str],
) -> None:
    if not isinstance(raw, dict):
        raise ProjectFormatError("Una página no es válida.")
    page_id = _required_identifier(raw.get("id"), "página")
    if page_id in page_ids:
        raise ProjectFormatError("Hay IDs de páginas duplicados.")
    page_ids.add(page_id)
    kind = raw.get("kind")
    asset_id = raw.get("asset_id")
    if kind not in {"pdf", "image", "blank"}:
        raise ProjectFormatError("El tipo de página no es válido.")
    if kind == "blank":
        if asset_id is not None:
            raise ProjectFormatError("Una página en blanco no debe tener asset.")
    else:
        if asset_id not in assets:
            raise ProjectAssetError("Una página referencia un asset inexistente.")
        expected = "pdf" if kind == "pdf" else "image"
        if assets[asset_id]["media_type"] != expected:
            raise ProjectAssetError("El tipo de asset de una página es incompatible.")
    page_index = raw.get("page_index")
    if kind == "pdf":
        if type(page_index) is not int or page_index < 0:
            raise ProjectFormatError("El índice de página PDF no es válido.")
    elif page_index is not None:
        raise ProjectFormatError("Una página no PDF contiene un índice.")
    if not _is_positive_finite(raw.get("width_pt")) or not _is_positive_finite(raw.get("height_pt")):
        raise ProjectFormatError("Las dimensiones de una página no son válidas.")
    rotation = raw.get("rotation")
    if type(rotation) is not int or rotation not in {0, 90, 180, 270}:
        raise ProjectFormatError("La rotación de una página no es válida.")
    if not isinstance(raw.get("label"), str):
        raise ProjectFormatError("La etiqueta de una página no es válida.")
    overlays = raw.get("overlays")
    if not isinstance(overlays, list) or len(overlays) > MAX_OVERLAYS_PER_PAGE:
        raise ProjectFormatError("La lista de overlays no es válida.")
    for overlay in overlays:
        _validate_serialized_overlay(overlay, assets, overlay_ids)


def _validate_serialized_overlay(
    raw: object,
    assets: Mapping[str, dict],
    overlay_ids: set[str],
) -> None:
    if not isinstance(raw, dict):
        raise ProjectFormatError("Un overlay no es válido.")
    overlay_id = _required_identifier(raw.get("id"), "overlay")
    if overlay_id in overlay_ids:
        raise ProjectFormatError("Hay IDs de overlays duplicados.")
    overlay_ids.add(overlay_id)
    asset_id = raw.get("asset_id")
    if asset_id not in assets:
        raise ProjectAssetError("Un overlay referencia un asset inexistente.")
    if assets[asset_id]["media_type"] != "image":
        raise ProjectAssetError("El asset de un overlay no es una imagen.")
    for key in ("x", "y", "w", "h", "rotation"):
        if not _is_finite_number(raw.get(key)):
            raise ProjectFormatError("La geometría de un overlay no es válida.")
    if raw["w"] <= 0 or raw["h"] <= 0:
        raise ProjectFormatError("El tamaño de un overlay debe ser positivo.")


def _extract_assets(
    project_path: Path,
    asset_specs: Mapping[str, dict],
    manager: AssetManager,
) -> Dict[str, AssetRecord]:
    records: Dict[str, AssetRecord] = {}
    with zipfile.ZipFile(project_path, "r") as archive:
        for asset_id, spec in asset_specs.items():
            target = manager.assets_path / f"{asset_id}{spec['extension']}"
            temporary = manager.assets_path / f".{asset_id}.tmp"
            digest = hashlib.sha256()
            size = 0
            try:
                with archive.open(spec["archive_path"], "r") as source, temporary.open("xb") as output:
                    while chunk := source.read(CHUNK_SIZE):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                        if size > spec["size_bytes"]:
                            raise ProjectAssetError("Un asset excede su tamaño declarado.")
                    output.flush()
                    os.fsync(output.fileno())
                if size != spec["size_bytes"] or digest.hexdigest() != spec["sha256"]:
                    raise ProjectAssetError("Un asset extraído no coincide con su registro.")
                os.replace(temporary, target)
                record = AssetRecord(
                    id=asset_id,
                    internal_path=str(target.resolve()),
                    original_path=spec["original_path"],
                    original_name=spec["original_name"],
                    extension=spec["extension"],
                    media_type=spec["media_type"],
                    size_bytes=size,
                    sha256=spec["sha256"],
                    created_at=spec.get("created_at"),
                )
                manager.register_asset(record)
                records[asset_id] = record
            finally:
                temporary.unlink(missing_ok=True)
    return records


def _deserialize_pages(
    document: dict,
    assets: Mapping[str, AssetRecord],
) -> Tuple[Dict[str, PageModel], list[str]]:
    pages: Dict[str, PageModel] = {}
    for raw in document["pages"]:
        overlays = []
        for overlay_raw in raw["overlays"]:
            asset = assets[overlay_raw["asset_id"]]
            overlays.append(
                OverlayModel(
                    id=overlay_raw["id"],
                    path=asset.internal_path,
                    x=overlay_raw["x"],
                    y=overlay_raw["y"],
                    w=overlay_raw["w"],
                    h=overlay_raw["h"],
                    rotation=overlay_raw["rotation"],
                    asset_id=asset.id,
                )
            )
        asset_id = raw["asset_id"]
        source = assets[asset_id].internal_path if asset_id is not None else None
        page = PageModel(
            id=raw["id"],
            kind=raw["kind"],
            source=source,
            page_index=raw["page_index"],
            width_pt=raw["width_pt"],
            height_pt=raw["height_pt"],
            rotation=raw["rotation"],
            label=raw["label"],
            overlays=overlays,
            asset_id=asset_id,
        )
        pages[page.id] = page
    return pages, list(document["page_order"])


def _validate_extracted_content(
    pages: Mapping[str, PageModel],
    assets: Mapping[str, AssetRecord],
) -> None:
    checked_images: set[str] = set()
    pdf_counts: Dict[str, int] = {}
    for page in pages.values():
        if page.kind == "pdf":
            if page.asset_id not in pdf_counts:
                try:
                    with fitz.open(assets[page.asset_id].internal_path) as document:
                        pdf_counts[page.asset_id] = document.page_count
                except Exception as exc:
                    raise ProjectAssetError("Un PDF interno no es válido.") from exc
            if page.page_index >= pdf_counts[page.asset_id]:
                raise ProjectFormatError("El índice de una página no existe en el PDF.")
        elif page.kind == "image" and page.asset_id not in checked_images:
            _verify_image(assets[page.asset_id].internal_path)
            checked_images.add(page.asset_id)
        for overlay in page.overlays:
            if overlay.asset_id not in checked_images:
                _verify_image(assets[overlay.asset_id].internal_path)
                checked_images.add(overlay.asset_id)


def _verify_image(path: str) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise ProjectAssetError("Una imagen interna no es válida.") from exc


def _hash_path(path: Path) -> Tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _hash_zip_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
) -> Tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with archive.open(info, "r") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
            if size > info.file_size:
                raise ProjectAssetError("Una entrada excede su tamaño declarado.")
    return size, digest.hexdigest()


def _required_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ProjectFormatError(f"El ID de {label} no es válido.")
    return value


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProjectFormatError(f"El campo {label} no es válido.")
    return value


def _validate_extension(value: object) -> str:
    if not isinstance(value, str):
        raise ProjectFormatError("La extensión de un asset no es válida.")
    extension = value.lower()
    if not _EXTENSION_PATTERN.fullmatch(extension):
        raise ProjectFormatError("La extensión de un asset no es válida.")
    return extension


def _safe_archive_filename(value: str) -> bool:
    stem = PurePosixPath(value).stem
    suffix = PurePosixPath(value).suffix
    return bool(_ID_PATTERN.fullmatch(stem) and _EXTENSION_PATTERN.fullmatch(suffix))


def _is_finite_number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(value)


def _is_positive_finite(value: object) -> bool:
    return _is_finite_number(value) and value > 0
