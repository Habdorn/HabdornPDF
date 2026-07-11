from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from models.asset_record import AssetRecord


class AssetManagerError(RuntimeError):
    pass


class AssetNotFoundError(AssetManagerError):
    pass


class AssetManager:
    FORMAT_VERSION = 1
    CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        workspace_id: Optional[str] = None,
    ) -> None:
        self.workspace_id = workspace_id or uuid.uuid4().hex
        self.created_at = self._utc_now()
        self.base_dir = Path(base_dir) if base_dir else self._default_base_dir()
        self.workspace_path = (
            self.base_dir.expanduser().resolve() / self.workspace_id
        )
        self.assets_path = self.workspace_path / "assets"
        self.manifest_path = self.workspace_path / "workspace.json"
        self.assets: Dict[str, AssetRecord] = {}
        self._assets_by_content: Dict[Tuple[int, str], str] = {}

        try:
            self.assets_path.mkdir(parents=True, exist_ok=False)
        except OSError:
            if base_dir is not None:
                raise
            fallback = Path(tempfile.gettempdir()) / "HabdornPDF" / "workspaces"
            if self.base_dir == fallback:
                raise
            self.base_dir = fallback
            self.workspace_path = (
                self.base_dir.expanduser().resolve() / self.workspace_id
            )
            self.assets_path = self.workspace_path / "assets"
            self.manifest_path = self.workspace_path / "workspace.json"
            self.assets_path.mkdir(parents=True, exist_ok=False)
        self._write_manifest()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _default_base_dir() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "HabdornPDF" / "workspaces"
        # Fallback seguro cuando LOCALAPPDATA no está disponible.
        return Path(tempfile.gettempdir()) / "HabdornPDF" / "workspaces"

    def import_asset(self, source_path: str, media_type: str) -> AssetRecord:
        if media_type not in {"pdf", "image"}:
            raise AssetManagerError(
                f"Tipo de asset no compatible: {media_type}"
            )

        source = Path(source_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise AssetManagerError(
                f"El archivo de origen no existe o no es válido: {source}"
            )

        size_bytes, sha256 = self._hash_file(source)
        content_key = (size_bytes, sha256)
        existing_id = self._assets_by_content.get(content_key)
        if existing_id:
            existing = self.assets[existing_id]
            self._validate_internal_path(Path(existing.internal_path))
            if Path(existing.internal_path).is_file():
                return existing

        asset_id = uuid.uuid4().hex
        extension = source.suffix.lower()
        target = self.assets_path / f"{asset_id}{extension}"
        temporary = self.assets_path / f".{asset_id}.tmp"
        self._validate_internal_path(target)
        self._validate_internal_path(temporary)

        try:
            copied_size, copied_sha256 = self._copy_and_hash(
                source,
                temporary,
            )
            if copied_size != size_bytes or copied_sha256 != sha256:
                raise AssetManagerError(
                    "La copia interna no coincide con el archivo de origen."
                )
            os.replace(temporary, target)
            if not target.is_file() or target.stat().st_size != size_bytes:
                raise AssetManagerError(
                    "No se pudo validar la copia interna del asset."
                )

            record = AssetRecord(
                id=asset_id,
                internal_path=str(target.resolve()),
                original_path=str(source),
                original_name=source.name,
                extension=extension,
                media_type=media_type,
                size_bytes=size_bytes,
                sha256=sha256,
                created_at=self._utc_now(),
            )
            self.assets[asset_id] = record
            self._assets_by_content[content_key] = asset_id
            try:
                self._write_manifest()
            except Exception:
                self.assets.pop(asset_id, None)
                self._assets_by_content.pop(content_key, None)
                target.unlink(missing_ok=True)
                raise
            return record
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            if isinstance(exc, AssetManagerError):
                raise
            raise AssetManagerError(
                f"No se pudo crear la copia interna de {source.name}: {exc}"
            ) from exc

    def get_asset(self, asset_id: str) -> AssetRecord:
        record = self.assets.get(asset_id)
        if record is None:
            raise AssetNotFoundError(
                f"No se encontró el asset interno: {asset_id}"
            )
        self._validate_internal_path(Path(record.internal_path))
        return record

    def resolve_path(self, asset_id: str) -> str:
        record = self.get_asset(asset_id)
        path = Path(record.internal_path)
        if not path.is_file():
            raise AssetNotFoundError(
                f"Falta el archivo interno del asset: {record.original_name}"
            )
        return str(path)

    def register_asset(self, record: AssetRecord) -> None:
        if record.id in self.assets:
            raise AssetManagerError(
                f"El asset interno ya está registrado: {record.id}"
            )
        path = Path(record.internal_path)
        self._validate_internal_path(path)
        if path.parent.resolve() != self.assets_path.resolve():
            raise AssetManagerError(
                "El asset debe estar dentro de la carpeta administrada."
            )
        if not path.is_file() or path.stat().st_size != record.size_bytes:
            raise AssetManagerError(
                f"No se pudo validar el asset interno: {record.original_name}"
            )
        content_key = (record.size_bytes, record.sha256)
        existing_id = self._assets_by_content.get(content_key)
        if existing_id and existing_id != record.id:
            raise AssetManagerError(
                "El contenido ya pertenece a otro asset del workspace."
            )
        self.assets[record.id] = record
        self._assets_by_content[content_key] = record.id
        try:
            self._write_manifest()
        except Exception:
            self.assets.pop(record.id, None)
            self._assets_by_content.pop(content_key, None)
            raise

    def _validate_internal_path(self, path: Path) -> None:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace_path)
        except ValueError as exc:
            raise AssetManagerError(
                "La ruta del asset escapa del workspace administrado."
            ) from exc

    @classmethod
    def _hash_file(cls, path: Path) -> Tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            while chunk := source.read(cls.CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
        return size, digest.hexdigest()

    @classmethod
    def _copy_and_hash(cls, source_path: Path, target_path: Path) -> Tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with source_path.open("rb") as source, target_path.open("xb") as target:
            while chunk := source.read(cls.CHUNK_SIZE):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        return size, digest.hexdigest()

    def _write_manifest(self) -> None:
        manifest = {
            "format_version": self.FORMAT_VERSION,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "assets": [asdict(record) for record in self.assets.values()],
        }
        temporary = self.workspace_path / f".workspace-{uuid.uuid4().hex}.tmp"
        self._validate_internal_path(temporary)
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.manifest_path)
        finally:
            temporary.unlink(missing_ok=True)
