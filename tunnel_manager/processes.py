from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable

from .logging_setup import redact


class ProcessManager:
    """Runs explicitly configured local processes without shell interpretation."""

    def __init__(self, log_callback: Callable[[str], None]) -> None:
        self.log_callback = log_callback
        self.processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def _emit(self, text: str) -> None:
        self.log_callback(redact(text))

    @staticmethod
    def _resolve_executable(executable: str, workdir: Path | None = None) -> str:
        candidate = executable.strip().strip('"')
        if not candidate:
            raise ValueError("Executable belum diisi.")
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        if workdir:
            workdir_path = (workdir / candidate).expanduser()
            if workdir_path.is_file():
                return str(workdir_path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        raise FileNotFoundError(f"Executable tidak ditemukan: {candidate}")

    def start_service(self, service: dict) -> None:
        process_key = f"service:{service['id']}"
        with self._lock:
            current = self.processes.get(process_key)
            if current and current.poll() is None:
                raise RuntimeError(f"Service '{service['name']}' sudah berjalan.")

            workdir = Path(service["workdir"]).expanduser().resolve()
            if not workdir.is_dir():
                raise NotADirectoryError(f"Working directory tidak ditemukan: {workdir}")

            args = service.get("args", [])
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError("Arguments harus berupa JSON array berisi string.")
            if any("\x00" in arg or "\n" in arg or "\r" in arg for arg in args):
                raise ValueError("Arguments mengandung karakter yang tidak diizinkan.")

            executable = self._resolve_executable(service["executable"], workdir=workdir)
            command = [executable, *args]
            creationflags = 0
            if os.name == "nt":
                creationflags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )

            process = subprocess.Popen(
                command,
                cwd=str(workdir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
                creationflags=creationflags,
                start_new_session=(os.name != "nt"),
            )
            self.processes[process_key] = process
            self._emit(f"[SERVICE] Started {service['name']} (PID {process.pid}) in {workdir}")
            threading.Thread(
                target=self._read_output,
                args=(process_key, service["name"], process),
                daemon=True,
            ).start()

    def _read_output(self, key: str, name: str, process: subprocess.Popen) -> None:
        try:
            if process.stdout:
                for line in process.stdout:
                    self._emit(f"[{name}] {line.rstrip()}")
        except (OSError, ValueError) as exc:
            self._emit(f"[{name}] Output reader stopped: {exc}")
        finally:
            try:
                code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    code = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    code = process.wait(timeout=2)
            if process.stdout:
                try:
                    process.stdout.close()
                except OSError:
                    pass
            self._emit(f"[SERVICE] {name} exited (code={code})")
            with self._lock:
                if self.processes.get(key) is process:
                    self.processes.pop(key, None)

    def start_tunnel(self, key: str, cloudflared_path: str, mode: str, target: str, token: str = "") -> None:
        with self._lock:
            current = self.processes.get(key)
            if current and current.poll() is None:
                raise RuntimeError("Tunnel sudah berjalan.")

            executable = self._resolve_executable(cloudflared_path)
            env = os.environ.copy()
            if mode == "quick":
                command = [executable, "tunnel", "--url", target]
                label = f"Quick Tunnel -> {target}"
            elif mode == "named":
                if not token:
                    raise ValueError("Tunnel token belum disimpan di Settings.")
                # Pass token securely via TUNNEL_TOKEN environment variable rather than CLI argv
                # to prevent exposure in process listing / Task Manager / WMI.
                env["TUNNEL_TOKEN"] = token
                command = [executable, "tunnel", "run"]
                label = "Named Tunnel"
            else:
                raise ValueError("Mode tunnel tidak dikenal.")

            creationflags = 0
            if os.name == "nt":
                creationflags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
                env=env,
                creationflags=creationflags,
                start_new_session=(os.name != "nt"),
            )
            self.processes[key] = process
            self._emit(f"[TUNNEL] Started {label} (PID {process.pid})")
            threading.Thread(
                target=self._read_output,
                args=(key, "CLOUDFLARED", process),
                daemon=True,
            ).start()

    def stop(self, key: str) -> None:
        with self._lock:
            process = self.processes.get(key)
        if not process or process.poll() is not None:
            with self._lock:
                self.processes.pop(key, None)
            return

        self._emit(f"[PROCESS] Stopping {key}...")
        try:
            if os.name == "nt":
                # Stop the process tree (e.g. npm -> vite child) without invoking a shell or flashing a console.
                try:
                    taskkill_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        shell=False,
                        timeout=6,
                        creationflags=taskkill_flags,
                    )
                except subprocess.TimeoutExpired:
                    process.kill()
            else:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        process.kill()
                else:
                    process.kill()
                process.wait(timeout=2)
        finally:
            with self._lock:
                if self.processes.get(key) is process:
                    self.processes.pop(key, None)
            self._emit(f"[PROCESS] Stopped {key}")

    def is_running(self, key: str) -> bool:
        with self._lock:
            process = self.processes.get(key)
            return bool(process and process.poll() is None)

    def running_keys(self) -> list[str]:
        with self._lock:
            return [key for key, process in self.processes.items() if process.poll() is None]

    def stop_all(self) -> None:
        for key in self.running_keys():
            self.stop(key)
