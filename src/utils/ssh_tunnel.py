"""
SSH tunnel context manager voor Kaironis sandbox verbindingen.

Gebruik environment variables voor configuratie:
  SANDBOX_HOST  - hostname/IP van de sandbox (default: 72.61.167.71)
  SANDBOX_PORT  - SSH port (default: 2847)
  SANDBOX_USER  - SSH user (default: kaironis)
  SANDBOX_KEY   - pad naar private key (default: ~/.ssh/kaironis_sandbox)
"""

import os
import time
import logging
import threading
from contextlib import contextmanager
from typing import Generator, Optional

import paramiko

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────

SANDBOX_HOST = os.getenv("SANDBOX_HOST", "72.61.167.71")
SANDBOX_SSH_PORT = int(os.getenv("SANDBOX_PORT", "2847"))
SANDBOX_USER = os.getenv("SANDBOX_USER", "kaironis")
SANDBOX_KEY_PATH = os.getenv(
    "SANDBOX_KEY",
    os.path.expanduser("~/.ssh/kaironis_sandbox"),
)


class SSHTunnel:
    """
    SSH port-forward tunnel via Paramiko.

    Opent een lokale poort die doorstuurt naar een remote service
    op de sandbox VPS.

    Example::

        with SSHTunnel(remote_port=8000, local_port=8001) as tunnel:
            # Gebruik localhost:8001 om sandbox:8000 te bereiken
            client = SomeClient(host="localhost", port=tunnel.local_port)
    """

    def __init__(
        self,
        remote_port: int,
        local_port: int,
        remote_host: str = "localhost",
        ssh_host: str = SANDBOX_HOST,
        ssh_port: int = SANDBOX_SSH_PORT,
        ssh_user: str = SANDBOX_USER,
        ssh_key_path: str = SANDBOX_KEY_PATH,
    ) -> None:
        self.remote_port = remote_port
        self.local_port = local_port
        self.remote_host = remote_host
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path

        self._client: Optional[paramiko.SSHClient] = None
        self._transport: Optional[paramiko.Transport] = None
        self._server: Optional[paramiko.server.ServerInterface] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> "SSHTunnel":
        """Start de SSH tunnel. Retourneert self voor chaining."""
        logger.info(
            "Opening SSH tunnel %s:%d → %s:%d via %s@%s:%d",
            "localhost",
            self.local_port,
            self.remote_host,
            self.remote_port,
            self.ssh_user,
            self.ssh_host,
            self.ssh_port,
        )

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self._client.connect(
            hostname=self.ssh_host,
            port=self.ssh_port,
            username=self.ssh_user,
            key_filename=self.ssh_key_path,
            timeout=10,
        )

        transport = self._client.get_transport()
        assert transport is not None, "SSH transport is None na connect"
        self._transport = transport

        # Start forwarding in achtergrond thread
        self._thread = threading.Thread(
            target=self._forward_loop,
            daemon=True,
            name=f"ssh-tunnel-{self.local_port}",
        )
        self._thread.start()

        # Korte pauze zodat de tunnel klaar is
        time.sleep(0.3)
        logger.info("SSH tunnel actief op localhost:%d", self.local_port)
        return self

    def stop(self) -> None:
        """Stop de SSH tunnel en sluit de verbinding."""
        self._stop_event.set()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._transport = None
        logger.info("SSH tunnel localhost:%d gesloten", self.local_port)

    def _forward_loop(self) -> None:
        """Interne loop: accepteert en doorstuurt kanaalverbindingen."""
        import socket

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", self.local_port))
        server_sock.listen(5)
        server_sock.settimeout(1.0)

        while not self._stop_event.is_set():
            try:
                client_sock, _ = server_sock.accept()
            except socket.timeout:
                continue
            except Exception as exc:
                if not self._stop_event.is_set():
                    logger.error("Tunnel accept error: %s", exc)
                break

            self._handle_connection(client_sock)

        server_sock.close()

    def _handle_connection(self, client_sock) -> None:  # type: ignore[no-untyped-def]
        """Koppel een inkomende socket aan een SSH forward channel."""
        import socket

        try:
            chan = self._transport.open_channel(  # type: ignore[union-attr]
                "direct-tcpip",
                (self.remote_host, self.remote_port),
                client_sock.getpeername(),
            )
        except Exception as exc:
            logger.error("Kan SSH channel niet openen: %s", exc)
            client_sock.close()
            return

        t1 = threading.Thread(
            target=_forward_data,
            args=(client_sock, chan),
            daemon=True,
        )
        t2 = threading.Thread(
            target=_forward_data,
            args=(chan, client_sock),
            daemon=True,
        )
        t1.start()
        t2.start()

    def __enter__(self) -> "SSHTunnel":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()


def _forward_data(src, dst) -> None:  # type: ignore[no-untyped-def]
    """Kopieer data van src naar dst totdat de verbinding verbroken wordt."""
    try:
        while True:
            data = src.recv(1024)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


@contextmanager
def chromadb_tunnel(
    local_port: int = 8001,
    remote_port: int = 8000,
) -> Generator[int, None, None]:
    """
    Context manager die een SSH tunnel naar ChromaDB op de sandbox opent.

    Yields het lokale poort nummer.

    Example::

        with chromadb_tunnel() as port:
            client = chromadb.HttpClient(host="localhost", port=port)
    """
    tunnel = SSHTunnel(remote_port=remote_port, local_port=local_port)
    try:
        tunnel.start()
        yield local_port
    finally:
        tunnel.stop()


@contextmanager
def ollama_tunnel(
    local_port: int = 11435,
    remote_port: int = 11434,
) -> Generator[int, None, None]:
    """
    Context manager die een SSH tunnel naar Ollama op de sandbox opent.

    Yields het lokale poort nummer.

    Example::

        with ollama_tunnel() as port:
            url = f"http://localhost:{port}/api/embeddings"
    """
    tunnel = SSHTunnel(remote_port=remote_port, local_port=local_port)
    try:
        tunnel.start()
        yield local_port
    finally:
        tunnel.stop()
