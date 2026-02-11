from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import perf_counter
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

    def _headers_with_token(self, token: str) -> dict[str, str]:
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=4.0)
            response.raise_for_status()
            return response.json().get("status") == "ok"
        except httpx.HTTPError:
            return False

    def ping(self) -> dict[str, Any]:
        started = perf_counter()
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=4.0)
            latency_ms = int((perf_counter() - started) * 1000)
            response.raise_for_status()
            data = response.json()
            server_dt_raw = str(data.get("server_time_utc", ""))
            server_dt = datetime.fromisoformat(server_dt_raw.replace("Z", "+00:00")) if server_dt_raw else None
            local_dt = datetime.now(timezone.utc)
            skew_seconds = int((local_dt - server_dt).total_seconds()) if server_dt else 0
            return {
                "ok": data.get("status") == "ok",
                "latency_ms": latency_ms,
                "clock_skew_seconds": skew_seconds,
            }
        except httpx.HTTPError as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}

    def health_details(self) -> dict[str, Any]:
        response = httpx.get(f"{self.base_url}/health", timeout=4.0)
        response.raise_for_status()
        data = response.json()
        server_dt_raw = data.get("server_time_utc", "")
        server_dt = datetime.fromisoformat(server_dt_raw.replace("Z", "+00:00")) if server_dt_raw else None
        local_dt = datetime.now(timezone.utc)
        skew_seconds = int((local_dt - server_dt).total_seconds()) if server_dt else 0
        date_header = response.headers.get("Date", "")
        parsed_header = parsedate_to_datetime(date_header).astimezone(timezone.utc).isoformat() if date_header else ""
        return {
            "status": data.get("status"),
            "server_time_utc": server_dt.isoformat() if server_dt else "",
            "server_tz": data.get("server_tz", "UTC"),
            "local_time_utc": local_dt.isoformat(),
            "clock_skew_seconds": skew_seconds,
            "http_date_utc": parsed_header,
        }

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

    def auth_challenge(self, username: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/auth/challenge",
            json={"username": username},
            timeout=8.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def auth_challenge_complete(self, challenge_id: str, key_id: str, signature_b64: str) -> str:
        response = httpx.post(
            f"{self.base_url}/auth/challenge/complete",
            json={"challenge_id": challenge_id, "key_id": key_id, "signature_b64": signature_b64},
            timeout=8.0,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self.set_token(token)
        return token

    def login_no_store(self, username: str, password: str) -> str:
        response = httpx.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def auth_me(self) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/auth/me",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def claim_device(self, activation_code: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/devices/claim",
            json={"activation_code": activation_code},
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def register_device(self, client_id: str, nome: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"client_id": client_id}
        if nome:
            payload["nome"] = nome
        response = httpx.post(
            f"{self.base_url}/devices/register",
            headers=self._headers(),
            json=payload,
            timeout=8.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def create_sede(self, nome: str, admin_token: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/sedi",
            headers=self._headers_with_token(admin_token),
            json={"nome": nome},
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def list_sedi(self, admin_token: str) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/admin/sedi",
            headers=self._headers_with_token(admin_token),
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def list_sedi_auth(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/admin/sedi",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def disable_sede_auth(self, sede_id: str) -> dict[str, Any]:
        response = httpx.delete(
            f"{self.base_url}/admin/sedi/{sede_id}",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def create_bambino(self, sede_id: str, nome: str, cognome: str, admin_token: str, attivo: bool = True) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/bambini",
            headers=self._headers_with_token(admin_token),
            json={
                "sede_id": sede_id,
                "nome": nome,
                "cognome": cognome,
                "attivo": attivo,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def list_bambini_admin(self, sede_id: str | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"include_inactive": include_inactive}
        if sede_id:
            params["sede_id"] = sede_id
        response = httpx.get(
            f"{self.base_url}/admin/bambini",
            headers=self._headers(),
            params=params,
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def create_bambino_admin(self, sede_id: str, nome: str, cognome: str, attivo: bool = True) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/bambini",
            headers=self._headers(),
            json={
                "sede_id": sede_id,
                "nome": nome,
                "cognome": cognome,
                "attivo": attivo,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def delete_bambino_admin(self, bambino_id: str) -> dict[str, Any]:
        response = httpx.delete(
            f"{self.base_url}/admin/bambini/{bambino_id}",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def create_device(self, sede_id: str, nome: str, admin_token: str, activation_expires_minutes: int = 15) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/devices",
            headers=self._headers_with_token(admin_token),
            json={
                "sede_id": sede_id,
                "nome": nome,
                "attivo": True,
                "activation_expires_minutes": activation_expires_minutes,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def list_users(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/admin/users",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def create_user(
        self,
        username: str,
        role: str = "EDUCATORE",
        attivo: bool = True,
        sede_id: str | None = None,
        key_name: str = "default",
        key_passphrase: str = "",
        key_valid_days: int = 180,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/users",
            headers=self._headers(),
            json={
                "username": username,
                "role": role,
                "attivo": attivo,
                "sede_id": sede_id,
                "key_name": key_name,
                "key_passphrase": key_passphrase,
                "key_valid_days": key_valid_days,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()

    def token_still_valid(self) -> bool:
        if not self.token:
            return False
        try:
            response = httpx.get(f"{self.base_url}/audit", headers=self._headers(), timeout=8.0)
            if response.status_code == 401:
                return False
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

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

    def list_bambini_presence_state(self, dispositivo_id: str, limit: int = 200) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/catalog/presenze-stato",
            params={"dispositivo_id": dispositivo_id, "limit": limit},
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def list_accessible_sedi(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/catalog/sedi-accessibili",
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def list_accessible_iscritti(self, sede_id: str | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"include_inactive": include_inactive}
        if sede_id:
            params["sede_id"] = sede_id
        response = httpx.get(
            f"{self.base_url}/catalog/iscritti-accessibili",
            params=params,
            headers=self._headers(),
            timeout=8.0,
        )
        response.raise_for_status()
        return list(response.json())

    def list_presence_history(
        self,
        unita: str,
        periodo: str,
        sede_id: str | None = None,
        bambino_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"unita": unita, "periodo": periodo}
        if sede_id:
            params["sede_id"] = sede_id
        if bambino_id:
            params["bambino_id"] = bambino_id
        response = httpx.get(
            f"{self.base_url}/presenze/storico",
            params=params,
            headers=self._headers(),
            timeout=12.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def export_presence_history_pdf(
        self,
        unita: str,
        periodo: str,
        sede_id: str | None = None,
        bambino_id: str | None = None,
    ) -> bytes:
        params: dict[str, Any] = {"unita": unita, "periodo": periodo}
        if sede_id:
            params["sede_id"] = sede_id
        if bambino_id:
            params["bambino_id"] = bambino_id
        response = httpx.get(
            f"{self.base_url}/presenze/storico/export-pdf",
            params=params,
            headers=self._headers(),
            timeout=20.0,
        )
        response.raise_for_status()
        return response.content

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
