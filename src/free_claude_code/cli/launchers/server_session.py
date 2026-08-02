"""Share an FCC server between managed Claude Code sessions."""

import os
import signal
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from free_claude_code.cli.launchers.common import preflight_proxy
from free_claude_code.core.interprocess_lock import InterprocessFileLock

_READY_TIMEOUT_SECONDS = 10.0
_READY_POLL_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class ServerSessionPaths:
    """State files used to coordinate one configured server port."""

    lock: Path
    references: Path
    pid: Path


def server_session_paths(port: int) -> ServerSessionPaths:
    """Return per-user temporary state paths for a server port."""

    root = Path(tempfile.gettempdir())
    prefix = f"free-claude-code-{os.getuid() if hasattr(os, 'getuid') else os.getpid()}-{port}"
    return ServerSessionPaths(
        lock=root / f"{prefix}.lock",
        references=root / f"{prefix}.refs",
        pid=root / f"{prefix}.pid",
    )


@dataclass(slots=True)
class ServerSession:
    """A reference to a shared FCC server, with idempotent cleanup."""

    paths: ServerSessionPaths
    server_pid: int | None
    reference_pid: int
    owns_server: bool = False
    _released: bool = False

    def release(self) -> None:
        """Remove this session and stop an owned server when it is unused."""

        if self._released:
            return
        self._released = True
        with InterprocessFileLock(self.paths.lock):
            references = _read_references(self.paths.references)
            references = {
                pid
                for pid in references
                if _process_is_alive(pid) and pid != self.reference_pid
            }
            if references:
                _write_references(self.paths.references, references)
                return

            self.paths.references.unlink(missing_ok=True)
            owned_pid = _read_pid(self.paths.pid)
            if (
                self.owns_server
                and self.server_pid is not None
                and owned_pid == self.server_pid
            ):
                _stop_process(self.server_pid)
                self.paths.pid.unlink(missing_ok=True)


class ServerSessionError(RuntimeError):
    """Raised when a shared FCC server cannot be acquired."""


def acquire_server_session(
    *,
    proxy_root_url: str,
    port: int,
    server_command: str = "fcc-server",
    paths: ServerSessionPaths | None = None,
    pid: int | None = None,
    process_factory: Callable[..., subprocess.Popen[bytes]] | None = None,
    wait_for_ready: Callable[[str], str | None] = preflight_proxy,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> ServerSession:
    """Acquire a reference to an existing or newly started FCC server."""

    resolved_paths = paths or server_session_paths(port)
    reference_pid = os.getpid() if pid is None else pid
    with InterprocessFileLock(resolved_paths.lock):
        references = {
            reference
            for reference in _read_references(resolved_paths.references)
            if _process_is_alive(reference)
        }
        existing_pid = _read_pid(resolved_paths.pid)
        if wait_for_ready(proxy_root_url) is None:
            references.add(reference_pid)
            _write_references(resolved_paths.references, references)
            return ServerSession(
                resolved_paths,
                existing_pid,
                reference_pid,
                owns_server=(
                    existing_pid is not None and _is_fcc_server_process(existing_pid)
                ),
            )

        if _port_is_open("127.0.0.1", port):
            raise ServerSessionError(
                f"Port {port} is occupied by another process and is not an FCC server."
            )

        try:
            start_process = process_factory or subprocess.Popen
            process = start_process(
                [server_command],
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise ServerSessionError(
                f"Could not start {server_command}: {exc}"
            ) from exc

        started_pid = process.pid
        _write_pid(resolved_paths.pid, started_pid)
        deadline = monotonic() + _READY_TIMEOUT_SECONDS
        while monotonic() < deadline:
            if process.poll() is not None:
                resolved_paths.pid.unlink(missing_ok=True)
                raise ServerSessionError("fcc-server exited before becoming ready.")
            if wait_for_ready(proxy_root_url) is None:
                references.add(reference_pid)
                _write_references(resolved_paths.references, references)
                return ServerSession(
                    resolved_paths,
                    started_pid,
                    reference_pid,
                    owns_server=True,
                )
            sleep(_READY_POLL_SECONDS)

        _stop_process(started_pid, process)
        resolved_paths.pid.unlink(missing_ok=True)
        raise ServerSessionError("fcc-server did not become ready within 10 seconds.")


def _read_references(path: Path) -> set[int]:
    try:
        return {
            int(line) for line in path.read_text(encoding="utf-8").splitlines() if line
        }
    except FileNotFoundError, ValueError:
        return set()


def _write_references(path: Path, references: set[int]) -> None:
    path.write_text("".join(f"{pid}\n" for pid in sorted(references)), encoding="utf-8")


def _write_pid(path: Path, pid: int) -> None:
    path.write_text(f"{pid}\n", encoding="utf-8")


def _read_pid(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return int(value) if value else None
    except FileNotFoundError, ValueError:
        return None


def _is_fcc_server_process(pid: int) -> bool:
    try:
        command_line = (
            Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\\0", b" ").decode()
        )
    except FileNotFoundError, OSError, UnicodeDecodeError:
        return False
    return "fcc-server" in command_line


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.2)
        return connection.connect_ex((host, port)) == 0


def _stop_process(pid: int, process: subprocess.Popen[bytes] | None = None) -> None:
    if pid <= 0:
        return
    try:
        if process is not None and process.poll() is not None:
            return
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        return
    if process is not None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
