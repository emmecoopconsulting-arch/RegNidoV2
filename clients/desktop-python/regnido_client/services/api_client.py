from typing import Any

import httpx

from regnido_client.models import Bambino


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def set_base_url(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def set_token(self, token: str) -> None:
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=4.0)
            response.raise_for_status()
            return response.json().get("status") == "ok"
        except httpx.HTTPError:
            return False

    def login(self, username: str, password: str) -> str:
        response = httpx.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=8.0,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self.set_token(token)
        return token

    def get_device(self, device_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/devices/{device_id}",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def list_bambini(self, dispositivo_id: str, q: str = "", limit: int = 100) -> list[Bambino]:
        response = httpx.get(
            f"{self.base_url}/catalog/bambini",
            params={"dispositivo_id": dispositivo_id, "q": q, "limit": limit},
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return [Bambino(id=row["id"], nome=row["nome"], cognome=row["cognome"]) for row in response.json()]

    def submit_presence_event(self, endpoint: str, payload: dict[str, str]) -> None:
        response = httpx.post(
            f"{self.base_url}{endpoint}",
            json=payload,
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()

    def sync_events(self, events: list[dict[str, str]]) -> dict[str, int]:
        response = httpx.post(
            f"{self.base_url}/sync",
            json={"eventi": events},
            headers=self._headers(),
            timeout=12.0,
        )
        response.raise_for_status()
        data = response.json()
        return {"accepted": int(data.get("accepted", 0)), "skipped": int(data.get("skipped", 0))}
