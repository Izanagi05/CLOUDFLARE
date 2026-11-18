import unittest

from tunnel_manager.cloudflare_api import CloudflareClient
from tunnel_manager.validation import parse_arguments, validate_hostname_basic, validate_local_url, validate_port


class ValidationTests(unittest.TestCase):
    def test_port_range(self):
        self.assertEqual(validate_port("8000"), 8000)
        with self.assertRaises(ValueError):
            validate_port("70000")
        with self.assertRaises(ValueError):
            validate_port("80; whoami")

    def test_json_arguments_only(self):
        self.assertEqual(parse_arguments('["artisan", "serve"]'), ["artisan", "serve"])
        self.assertEqual(parse_arguments("['artisan', 'serve']"), ["artisan", "serve"])
        self.assertEqual(parse_arguments(""), [])
        with self.assertRaises(ValueError):
            parse_arguments('print("bad")')
        with self.assertRaises(ValueError):
            parse_arguments('["ok", 123]')

    def test_hostname_normalization(self):
        self.assertEqual(validate_hostname_basic("API-DEV.Example.com"), "api-dev.example.com")
        with self.assertRaises(ValueError):
            validate_hostname_basic("https://example.com")

    def test_local_url_loopback_only(self):
        self.assertEqual(validate_local_url("http://localhost:8000"), "http://127.0.0.1:8000")
        with self.assertRaises(ValueError):
            validate_local_url("http://169.254.169.254:80")
        with self.assertRaises(ValueError):
            validate_local_url("https://localhost:8000")

    def test_cloudflare_hostname_must_be_in_zone(self):
        client = CloudflareClient("fake-token", "account", "zone", "tunnel", "example.com")
        self.assertEqual(client.validate_hostname("api-dev.example.com"), "api-dev.example.com")
        with self.assertRaises(ValueError):
            client.validate_hostname("api.other-domain.com")
        with self.assertRaises(ValueError):
            client.validate_hostname("example.com")

    def test_cloudflare_service_rejects_non_loopback(self):
        self.assertEqual(CloudflareClient.validate_local_service("http://localhost:5173"), "http://127.0.0.1:5173")
        with self.assertRaises(ValueError):
            CloudflareClient.validate_local_service("http://192.168.1.20:8000")

    def test_apply_routes_preserves_unmanaged_ingress(self):
        client = CloudflareClient("fake-token", "account", "zone", "tunnel", "example.com")
        captured = {}

        def fake_request(method, path, **kwargs):
            if method == "GET":
                return {"config": {"ingress": [
                    {"hostname": "legacy.example.com", "service": "http://127.0.0.1:9000"},
                    {"service": "http_status:404"},
                ]}}
            if method == "PUT":
                captured.update(kwargs["json"])
                return {}
            raise AssertionError(method)

        client._request = fake_request
        client._ensure_dns_record = lambda hostname: "DNS ok"
        client.apply_routes([{"hostname": "api-dev.example.com", "service": "http://127.0.0.1:8000"}])
        ingress = captured["config"]["ingress"]
        self.assertEqual(ingress[0]["hostname"], "legacy.example.com")
        self.assertEqual(ingress[1]["hostname"], "api-dev.example.com")
        self.assertEqual(ingress[-1]["service"], "http_status:404")

    def test_apply_routes_refuses_path_route_overwrite(self):
        client = CloudflareClient("fake-token", "account", "zone", "tunnel", "example.com")
        client._request = lambda method, path, **kwargs: (
            {"config": {"ingress": [
                {"hostname": "api-dev.example.com", "path": "/private/*", "service": "http://127.0.0.1:9000"},
                {"service": "http_status:404"},
            ]}} if method == "GET" else {}
        )
        client._ensure_dns_record = lambda hostname: "DNS ok"
        with self.assertRaises(Exception):
            client.apply_routes([{"hostname": "api-dev.example.com", "service": "http://127.0.0.1:8000"}])


if __name__ == "__main__":
    unittest.main()
