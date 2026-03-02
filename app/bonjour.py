from __future__ import annotations

import logging
import socket

from zeroconf import ServiceInfo, Zeroconf

from app.config import settings

logger = logging.getLogger("xtts.bonjour")


class BonjourPublisher:
    def __init__(self, port: int) -> None:
        self.port = port
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None
        self._advertised = False

    @property
    def advertised(self) -> bool:
        return self._advertised

    def _local_ip(self) -> str:
        # First try route-based detection.
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

        # Fallback to first non-loopback IPv4 from hostname resolution.
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127."):
                    return ip
        except OSError:
            pass

        # Final fallback to localhost (discovery will likely fail off-device).
        return "127.0.0.1"

    def start(self) -> None:
        ip = self._local_ip()
        hostname = socket.gethostname()

        service_type = settings.bonjour_service_type
        if not service_type.endswith("."):
            service_type = f"{service_type}."

        service_name = f"{settings.bonjour_service_name} - {hostname}.{service_type}"
        properties = {
            b"ver": b"1",
            b"auth": b"bearer",
            b"model": b"xtts-v2",
            b"name": hostname.encode("utf-8"),
        }

        self._zeroconf = Zeroconf()
        self._info = ServiceInfo(
            type_=service_type,
            name=service_name,
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties=properties,
            server=f"{hostname}.local.",
        )

        self._zeroconf.register_service(self._info, ttl=settings.bonjour_ttl)
        self._advertised = True
        logger.info("bonjour_advertised", extra={"extra": {"service": service_name, "ip": ip, "port": self.port}})

    def stop(self) -> None:
        if self._zeroconf and self._info:
            try:
                self._zeroconf.unregister_service(self._info)
            except Exception:  # noqa: BLE001
                logger.exception("bonjour_unregister_failed")
            self._zeroconf.close()
            logger.info("bonjour_stopped")

        self._zeroconf = None
        self._info = None
        self._advertised = False
