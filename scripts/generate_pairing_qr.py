#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import qrcode
from dotenv import load_dotenv


def detect_magicdns() -> str | None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate XTTS mobile pairing QR.")
    parser.add_argument("--host", help="Server host (defaults to Tailscale MagicDNS if available)")
    parser.add_argument("--port", type=int, default=None, help="Server port override")
    parser.add_argument("--token", help="Auth token override")
    parser.add_argument(
        "--output",
        default="/tmp/xtts-pairing-qr.png",
        help="Output path for QR image",
    )
    args = parser.parse_args()

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)

    host = args.host or os.getenv("XTTS_PAIR_HOST") or detect_magicdns() or ""
    port = args.port or int(os.getenv("XTTS_PORT", "8020"))
    token = args.token or os.getenv("XTTS_AUTH_TOKEN", "")

    if not host:
        raise SystemExit("Host is required. Pass --host or set XTTS_PAIR_HOST.")
    if not token:
        raise SystemExit("Token is required. Set XTTS_AUTH_TOKEN in .env or pass --token.")

    payload = f"xtts://pair?{urlencode({'host': host, 'port': str(port), 'token': token})}"

    image = qrcode.make(payload)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)

    print("Pairing URL:")
    print(payload)
    print(f"\nQR image saved to: {output_path}")
    print("Open the PNG on Mac and scan it from the iOS app -> Connect -> Scan Pairing QR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
