from dialogs.about_dialog import AboutDialog
from dialogs.common import BaseDialog, open_external_url
from dialogs.help_dialog import HelpDialog
from dialogs.preferences_dialog import PreferencesDialog
from dialogs.shortcuts_dialog import ShortcutsDialog
from dialogs.third_party_dialog import (
    ThirdPartyNoticesDialog,
    load_third_party_notices,
)
from dialogs.whats_new_dialog import WhatsNewDialog

__all__ = [
    "AboutDialog",
    "BaseDialog",
    "HelpDialog",
    "PreferencesDialog",
    "ShortcutsDialog",
    "ThirdPartyNoticesDialog",
    "WhatsNewDialog",
    "load_third_party_notices",
    "open_external_url",
]
