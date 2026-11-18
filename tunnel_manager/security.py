from __future__ import annotations

import keyring
from keyring.errors import KeyringError

SERVICE_NAME = "CloudflareTunnelManager"


class SecretStore:
    """Store secrets in the OS credential store, never in the app SQLite DB."""

    @staticmethod
    def set_secret(name: str, value: str) -> None:
        if not value:
            SecretStore.delete_secret(name)
            return
        try:
            keyring.set_password(SERVICE_NAME, name, value)
        except KeyringError as exc:
            raise RuntimeError(
                "Windows Credential Manager tidak dapat menyimpan secret. "
                "Pastikan keyring terpasang dan backend Windows tersedia."
            ) from exc

    @staticmethod
    def get_secret(name: str) -> str:
        try:
            return keyring.get_password(SERVICE_NAME, name) or ""
        except KeyringError as exc:
            raise RuntimeError("Tidak dapat membaca secret dari credential store.") from exc

    @staticmethod
    def delete_secret(name: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, name)
        except (KeyringError, Exception):
            # Missing credentials are not an error for the caller.
            pass
