from typing import Any

import httpx


class ApiClient:
    def __init__(self) -> None:
        self.base_url = ""
        self.token = ""

    def configure(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def login(self, base_url: str, username: str, password: str) -> str:
        base_url = base_url.rstrip("/")
        response = httpx.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=10.0,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self.configure(base_url, token)
        return token

    def create_sede(self, nome: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/sedi",
            headers=self._headers(),
            json={"nome": nome},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()

    def create_bambino(self, sede_id: str, nome: str, cognome: str, attivo: bool = True) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/bambini",
            headers=self._headers(),
            json={"sede_id": sede_id, "nome": nome, "cognome": cognome, "attivo": attivo},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()

    def create_device(self, sede_id: str, nome: str, activation_expires_minutes: int = 15) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/devices",
            headers=self._headers(),
            json={
                "sede_id": sede_id,
                "nome": nome,
                "attivo": True,
                "activation_expires_minutes": activation_expires_minutes,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
