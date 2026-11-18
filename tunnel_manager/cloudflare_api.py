from __future__ import annotations

import re
from urllib.parse import quote

import requests


API_BASE = "https://api.cloudflare.com/client/v4"
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


class CloudflareAPIError(RuntimeError):
    pass


class CloudflareClient:
    def __init__(self, api_token: str, account_id: str, zone_id: str, tunnel_id: str, domain: str) -> None:
        self.api_token = api_token.strip()
        self.account_id = account_id.strip()
        self.zone_id = zone_id.strip()
        self.tunnel_id = tunnel_id.strip()
        self.domain = domain.strip().lower().rstrip(".")
        if not all((self.api_token, self.account_id, self.zone_id, self.tunnel_id, self.domain)):
            raise ValueError("API token, Account ID, Zone ID, Tunnel ID, dan domain wajib diisi.")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "User-Agent": "CloudflareTunnelManager/1.0",
        })

    def _request(self, method: str, path: str, **kwargs):
        url = f"{API_BASE}{path}"
        try:
            response = self.session.request(method, url, timeout=(5, 20), allow_redirects=False, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            # Do not include request headers or token in exception text.
            raise CloudflareAPIError(f"Gagal menghubungi Cloudflare API ({type(exc).__name__}).") from None
        except ValueError:
            raise CloudflareAPIError("Cloudflare mengembalikan respons yang bukan JSON.") from None

        if not isinstance(payload, dict) or not payload.get("success"):
            errors = payload.get("errors", []) if isinstance(payload, dict) else []
            messages = [str(item.get("message", "Unknown error")) for item in errors if isinstance(item, dict)]
            raise CloudflareAPIError("Cloudflare API menolak permintaan: " + ("; ".join(messages[:3]) or "unknown error"))
        return payload.get("result")

    def validate_hostname(self, hostname: str) -> str:
        host = hostname.strip().lower().rstrip(".")
        if not host or len(host) > 253 or host == self.domain:
            raise ValueError(f"Hostname harus berupa subdomain dari {self.domain}.")
        if not host.endswith("." + self.domain):
            raise ValueError(f"Hostname {host} bukan bagian dari zone {self.domain}.")
        labels = host.split(".")
        if any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise ValueError(f"Format hostname tidak valid: {host}")
        return host

    @staticmethod
    def validate_local_service(url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url.strip())
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Service publik hanya boleh diarahkan ke http://localhost atau http://127.0.0.1.")
        if not parsed.port or not (1 <= parsed.port <= 65535):
            raise ValueError("Port service tidak valid.")
        if parsed.username or parsed.password:
            raise ValueError("URL service tidak boleh berisi username/password.")
        return f"http://127.0.0.1:{parsed.port}"

    def test_connection(self) -> str:
        tunnel = self._request(
            "GET",
            f"/accounts/{quote(self.account_id, safe='')}/cfd_tunnel/{quote(self.tunnel_id, safe='')}",
        )
        if not isinstance(tunnel, dict):
            raise CloudflareAPIError("Respons detail tunnel tidak valid.")
        return str(tunnel.get("name") or self.tunnel_id)

    def _ensure_dns_record(self, hostname: str) -> str:
        target = f"{self.tunnel_id}.cfargotunnel.com"
        records = self._request(
            "GET",
            f"/zones/{quote(self.zone_id, safe='')}/dns_records",
            params={"name": hostname, "per_page": 100},
        ) or []
        exact = [record for record in records if isinstance(record, dict) and record.get("name", "").lower() == hostname]
        if exact:
            if len(exact) > 1:
                raise CloudflareAPIError(f"Ada lebih dari satu DNS record untuk {hostname}; periksa DNS secara manual.")
            record = exact[0]
            if record.get("type") != "CNAME":
                raise CloudflareAPIError(
                    f"{hostname} sudah memiliki record {record.get('type')}. "
                    "Aplikasi tidak akan menimpa record DNS yang berbeda."
                )
            if record.get("content", "").lower().rstrip(".") != target.lower():
                raise CloudflareAPIError(
                    f"CNAME {hostname} mengarah ke target lain. Ubah record itu secara manual setelah memeriksanya."
                )
            if not record.get("proxied", False):
                self._request(
                    "PUT",
                    f"/zones/{quote(self.zone_id, safe='')}/dns_records/{quote(str(record['id']), safe='')}",
                    json={"type": "CNAME", "name": hostname, "content": target, "proxied": True},
                )
            return "DNS CNAME sudah tersedia"

        self._request(
            "POST",
            f"/zones/{quote(self.zone_id, safe='')}/dns_records",
            json={"type": "CNAME", "name": hostname, "content": target, "proxied": True, "ttl": 1},
        )
        return "DNS CNAME dibuat"

    def apply_routes(self, routes: list[dict]) -> list[str]:
        if not routes:
            raise ValueError("Belum ada service dengan hostname publik.")

        ingress = []
        seen = set()
        validated = []
        for route in routes:
            hostname = self.validate_hostname(route["hostname"])
            if hostname in seen:
                raise ValueError(f"Hostname duplikat: {hostname}")
            seen.add(hostname)
            service_url = self.validate_local_service(route["service"])
            ingress.append({"hostname": hostname, "service": service_url, "originRequest": {}})
            validated.append(hostname)

        config_path = (
            f"/accounts/{quote(self.account_id, safe='')}/cfd_tunnel/"
            f"{quote(self.tunnel_id, safe='')}/configurations"
        )
        existing_config = self._request("GET", config_path) or {}
        if not isinstance(existing_config, dict):
            raise CloudflareAPIError("Format konfigurasi tunnel dari Cloudflare tidak valid.")
        existing_cfg = existing_config.get("config") or {}
        if not isinstance(existing_cfg, dict):
            raise CloudflareAPIError("Bagian config tunnel dari Cloudflare tidak valid.")
        existing_rules = existing_cfg.get("ingress") or []
        if not isinstance(existing_rules, list):
            raise CloudflareAPIError("Daftar ingress tunnel dari Cloudflare tidak valid.")
        managed_hosts = set(validated)
        preserved_rules = []
        catch_all_rules = []
        for rule in existing_rules:
            if not isinstance(rule, dict):
                continue
            existing_host = str(rule.get("hostname") or "").lower().rstrip(".")
            if existing_host in managed_hosts:
                if rule.get("path"):
                    raise CloudflareAPIError(
                        f"Route {existing_host} memiliki path khusus. Aplikasi tidak akan menggantinya otomatis."
                    )
                continue
            if not existing_host and not rule.get("path"):
                catch_all_rules.append(rule)
            else:
                preserved_rules.append(rule)

        if len(catch_all_rules) > 1:
            raise CloudflareAPIError(
                "Konfigurasi tunnel memiliki lebih dari satu catch-all rule. Rapikan ingress di Cloudflare terlebih dahulu."
            )
        catch_all = catch_all_rules[0] if catch_all_rules else {"service": "http_status:404"}
        merged_ingress = preserved_rules + ingress + [catch_all]

        messages = []
        for hostname in validated:
            messages.append(f"{hostname}: {self._ensure_dns_record(hostname)}")

        self._request(
            "PUT",
            config_path,
            json={"config": {"ingress": merged_ingress}},
        )
        messages.append("Ingress diperbarui; route lain yang tidak dikelola aplikasi dipertahankan")
        return messages
