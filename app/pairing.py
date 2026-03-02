from __future__ import annotations

import json
import socket
import subprocess
from io import StringIO
from urllib.parse import urlencode

import qrcode


def detect_pair_host(explicit_host: str | None = None) -> str:
    if explicit_host:
        return explicit_host

    dns_name = _detect_tailscale_magicdns()
    if dns_name:
        return dns_name

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass

    return "127.0.0.1"


def build_pairing_url(host: str, port: int, token: str) -> str:
    query = urlencode({"host": host, "port": str(port), "token": token})
    return f"xtts://pair?{query}"


def render_ascii_qr(payload: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(payload)
    qr.make(fit=True)

    buffer = StringIO()
    qr.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()


def _detect_tailscale_magicdns() -> str | None:
    try:
        proc = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        dns_name = payload.get("Self", {}).get("DNSName")
        if isinstance(dns_name, str) and dns_name:
            return dns_name.rstrip(".")
    except Exception:
        return None
    return None
