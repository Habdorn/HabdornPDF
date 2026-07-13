from __future__ import annotations

import json
from typing import Mapping, Optional

from PySide6.QtCore import QFile, QIODevice, QSettings

from app import i18n_resources  # noqa: F401 - registers bundled locales


SUPPORTED_LOCALES = ("es", "en")
DEFAULT_LOCALE = "es"
LANGUAGE_SETTING_KEY = "preferences/language"


class TranslationCatalogError(ValueError):
    pass


def _load_catalog(locale: str) -> dict[str, str]:
    resource = QFile(f":/i18n/{locale}.json")
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        raise TranslationCatalogError(
            f"Translation resource is unavailable: {locale}"
        )
    try:
        raw = bytes(resource.readAll()).decode("utf-8")
        catalog = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranslationCatalogError(
            f"Translation resource is invalid: {locale}"
        ) from exc
    finally:
        resource.close()
    if not isinstance(catalog, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in catalog.items()
    ):
        raise TranslationCatalogError(
            f"Translation catalog must contain string pairs: {locale}"
        )
    return dict(catalog)


def normalize_locale(locale: object) -> str:
    return locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE


def load_saved_locale(settings: Optional[QSettings] = None) -> str:
    store = settings or QSettings()
    return normalize_locale(store.value(LANGUAGE_SETTING_KEY, DEFAULT_LOCALE))


def save_locale(locale: str, settings: Optional[QSettings] = None) -> str:
    normalized = normalize_locale(locale)
    store = settings or QSettings()
    store.setValue(LANGUAGE_SETTING_KEY, normalized)
    store.sync()
    return normalized


class Translator:
    def __init__(
        self,
        locale: str = DEFAULT_LOCALE,
        catalogs: Optional[Mapping[str, Mapping[str, str]]] = None,
    ) -> None:
        self.locale = normalize_locale(locale)
        if catalogs is None:
            self._catalogs = {
                language: _load_catalog(language)
                for language in SUPPORTED_LOCALES
            }
        else:
            self._catalogs = self._validate_catalogs(catalogs)

    @staticmethod
    def _validate_catalogs(
        catalogs: Mapping[str, Mapping[str, str]],
    ) -> dict[str, dict[str, str]]:
        validated: dict[str, dict[str, str]] = {}
        for locale in SUPPORTED_LOCALES:
            catalog = catalogs.get(locale, {})
            if not isinstance(catalog, Mapping) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in catalog.items()
            ):
                raise TranslationCatalogError(
                    f"Translation catalog must contain string pairs: {locale}"
                )
            validated[locale] = dict(catalog)
        return validated

    def get(self, key: str, **values: object) -> str:
        text = self._catalogs[self.locale].get(key)
        if text is None:
            text = self._catalogs[DEFAULT_LOCALE].get(key)
        if text is None:
            return f"[{key}]"
        if not values:
            return text
        try:
            return text.format(**values)
        except (KeyError, ValueError, IndexError):
            return text

    def plural(
        self,
        one_key: str,
        other_key: str,
        count: int,
        **values: object,
    ) -> str:
        values.setdefault("count", count)
        return self.get(one_key if count == 1 else other_key, **values)

    def keys(self, locale: Optional[str] = None) -> set[str]:
        return set(self._catalogs[normalize_locale(locale or self.locale)])
