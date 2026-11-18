from __future__ import annotations

import logging
import queue
import re
import shutil
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from tunnel_manager.cloudflare_api import CloudflareClient
from tunnel_manager.database import Database
from tunnel_manager.logging_setup import EventLogger
from tunnel_manager.processes import ProcessManager
from tunnel_manager.security import SecretStore
from tunnel_manager.validation import (
    parse_arguments,
    validate_hostname_basic,
    validate_port,
    validate_workdir,
)

APP_NAME = "Cloudflare Tunnel Manager"
APP_VERSION = "1.0.0"


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home() / ".config"
    return base / "CloudflareTunnelManager"


class TunnelManagerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} · v{APP_VERSION}")
        self.geometry("1240x820")
        self.minsize(1050, 700)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.data_dir = app_data_dir()
        self.logs_dir = self.data_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "manager.db")
        self.event_queue: queue.Queue[str] = queue.Queue()
        self.logger = EventLogger(self.logs_dir, self.event_queue.put)
        self.processes = ProcessManager(self.logger.info)

        bundled_exe = Path(__file__).resolve().parent / "bin" / "cloudflared.exe"
        detected_exe = str(bundled_exe) if bundled_exe.is_file() else (shutil.which("cloudflared") or "")
        self.cloudflared_path = self.db.get_setting("cloudflared_path", detected_exe)
        if detected_exe and not self.db.get_setting("cloudflared_path"):
            self.db.set_setting("cloudflared_path", detected_exe)
        self.quick_url = ""
        self.current_page = "Dashboard"
        self.current_profile_id = ""
        self._closing = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.main_area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=22, pady=20)
        self.show_page("Dashboard")
        self.after(120, self._poll_events)
        self.after(1200, self._refresh_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.logger.info("Application started")

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=225, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(24, 28))
        ctk.CTkLabel(brand, text="☁", font=ctk.CTkFont(size=28, weight="bold"), text_color="#F48120").pack(side="left")
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=10)
        ctk.CTkLabel(brand_text, text="Tunnel Manager", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(brand_text, text="Local Development Toolkit", text_color="gray", font=ctk.CTkFont(size=10)).pack(anchor="w")

        ctk.CTkLabel(sidebar, text="WORKSPACE", text_color="gray", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=20, pady=(0, 8))
        self.nav_buttons = {}
        for name, icon in [
            ("Dashboard", "▦"),
            ("Projects & Services", "▤"),
            ("Tunnel Manager", "⇄"),
            ("Logs & Diagnostics", "≋"),
            ("Settings", "⚙"),
        ]:
            button = ctk.CTkButton(
                sidebar,
                text=f"{icon}   {name}",
                anchor="w",
                height=42,
                corner_radius=9,
                fg_color="#1F538D" if name == self.current_page else "transparent",
                hover_color=("#254F78" if name == self.current_page else "#343434"),
                command=lambda item=name: self.show_page(item),
            )
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[name] = button

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)
        ctk.CTkLabel(bottom, text="LOCAL MACHINE", text_color="gray", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w")
        self.cloudflared_state_label = ctk.CTkLabel(bottom, text="● cloudflared belum diperiksa", text_color="#D6A84B", font=ctk.CTkFont(size=11))
        self.cloudflared_state_label.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(bottom, text=f"Version {APP_VERSION}", text_color="gray", font=ctk.CTkFont(size=10)).pack(anchor="w", pady=(12, 0))

    def show_page(self, page: str) -> None:
        self.current_page = page
        for name, button in self.nav_buttons.items():
            selected = name == page
            button.configure(fg_color="#1F538D" if selected else "transparent", hover_color="#254F78" if selected else "#343434")
        for child in self.main_area.winfo_children():
            child.destroy()
        if page == "Dashboard":
            self._page_dashboard()
        elif page == "Projects & Services":
            self._page_projects()
        elif page == "Tunnel Manager":
            self._page_tunnel()
        elif page == "Logs & Diagnostics":
            self._page_logs()
        elif page == "Settings":
            self._page_settings()

    def _page_header(self, title: str, subtitle: str) -> None:
        ctk.CTkLabel(self.main_area, text=title, font=ctk.CTkFont(size=27, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(self.main_area, text=subtitle, text_color="gray", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(4, 18))

    def _card(self, parent, title: str, value: str, subtitle: str = ""):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        ctk.CTkLabel(frame, text=title, text_color="gray", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=16, pady=(14, 3))
        ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=23, weight="bold")).pack(anchor="w", padx=16)
        if subtitle:
            ctk.CTkLabel(frame, text=subtitle, text_color="gray", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(2, 14))
        else:
            ctk.CTkLabel(frame, text="", height=13).pack()
        return frame

    def _page_dashboard(self) -> None:
        self._page_header("Dashboard", "Ringkasan project, service lokal, dan koneksi Cloudflare Tunnel.")
        profiles = self.db.get_profiles()
        services = self.db.get_services()
        running_services = sum(self.processes.is_running(f"service:{item['id']}") for item in services)
        tunnel_running = self.processes.is_running("tunnel")
        stats = ctk.CTkFrame(self.main_area, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 16))
        for col in range(3):
            stats.grid_columnconfigure(col, weight=1)
        self._card(stats, "PROJECTS", str(len(profiles)), "Profile tersimpan").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._card(stats, "ACTIVE SERVICES", f"{running_services}/{len(services)}", "Proses lokal berjalan").grid(row=0, column=1, sticky="ew", padx=8)
        self._card(stats, "TUNNEL", "Running" if tunnel_running else "Stopped", "Cloudflare connector").grid(row=0, column=2, sticky="ew", padx=(8, 0))

        actions = ctk.CTkFrame(self.main_area, corner_radius=12)
        actions.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(actions, text="Quick Actions", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(14, 10))
        row = ctk.CTkFrame(actions, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 14))
        ctk.CTkButton(row, text="Manage Projects", command=lambda: self.show_page("Projects & Services")).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Open Tunnel Manager", command=lambda: self.show_page("Tunnel Manager")).pack(side="left", padx=4)
        ctk.CTkButton(row, text="View Logs", fg_color="transparent", border_width=1, command=lambda: self.show_page("Logs & Diagnostics")).pack(side="left", padx=4)

        section = ctk.CTkFrame(self.main_area, corner_radius=12)
        section.pack(fill="both", expand=True)
        ctk.CTkLabel(section, text="Configured Services", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=14)
        if not services:
            ctk.CTkLabel(section, text="Belum ada service. Tambahkan project dan service melalui menu Projects & Services.", text_color="gray").pack(anchor="w", padx=16, pady=10)
        else:
            scroll = ctk.CTkScrollableFrame(section, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            for service in services:
                self._service_row(scroll, service, compact=True)

    def _service_row(self, parent, service: dict, compact: bool = False) -> None:
        running = self.processes.is_running(f"service:{service['id']}")
        row = ctk.CTkFrame(parent, corner_radius=10)
        row.pack(fill="x", padx=4, pady=4)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        ctk.CTkLabel(left, text=service["name"], font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        hostname = service.get("hostname") or "No public hostname"
        ctk.CTkLabel(left, text=f"{service['profile_name']}  ·  localhost:{service['port']}  ·  {hostname}", text_color="gray", font=ctk.CTkFont(size=10)).pack(anchor="w", pady=(3, 0))
        status = ctk.CTkLabel(row, text="● Running" if running else "● Stopped", text_color="#3AA76D" if running else "gray", font=ctk.CTkFont(size=11))
        status.pack(side="left", padx=8)
        if running:
            ctk.CTkButton(row, text="Stop", width=70, fg_color="#8B3333", hover_color="#6F2929", command=lambda s=service: self._stop_service(s, refresh=True)).pack(side="right", padx=10, pady=8)
        else:
            ctk.CTkButton(row, text="Start", width=70, command=lambda s=service: self._start_service(s, refresh=True)).pack(side="right", padx=10, pady=8)

    def _page_projects(self) -> None:
        self._page_header("Projects & Services", "Simpan beberapa project dan definisikan proses lokal yang bisa dijalankan dari GUI.")
        toolbar = ctk.CTkFrame(self.main_area, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 12))
        ctk.CTkButton(toolbar, text="+ Add Project", command=self._dialog_profile).pack(side="left")
        self.profile_combo = ctk.CTkComboBox(toolbar, width=280, values=[], command=self._on_profile_selected)
        self.profile_combo.pack(side="left", padx=10)
        ctk.CTkButton(toolbar, text="Add Service", command=self._dialog_service).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Start All", command=self._start_all_services).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Stop All", fg_color="#8B3333", hover_color="#6F2929", command=self._stop_all_services).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Edit Project", fg_color="transparent", border_width=1, command=self._edit_current_profile).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Delete Project", fg_color="transparent", border_width=1, text_color="#E28C8C", command=self._delete_current_profile).pack(side="left", padx=4)

        self.services_frame = ctk.CTkScrollableFrame(self.main_area, corner_radius=12)
        self.services_frame.pack(fill="both", expand=True)
        self._reload_profile_list()

    def _reload_profile_list(self) -> None:
        if not hasattr(self, "profile_combo") or not self.profile_combo.winfo_exists():
            return
        profiles = self.db.get_profiles()
        names = [profile["name"] for profile in profiles]
        self.profile_map = {profile["name"]: profile["id"] for profile in profiles}
        self.profile_combo.configure(values=names or ["No projects"])
        if profiles:
            selected = next((p for p in profiles if p["id"] == self.current_profile_id), profiles[0])
            self.current_profile_id = selected["id"]
            self.profile_combo.set(selected["name"])
        else:
            self.current_profile_id = ""
            self.profile_combo.set("No projects")
        self._render_services()

    def _on_profile_selected(self, name: str) -> None:
        self.current_profile_id = self.profile_map.get(name, "")
        self._render_services()

    def _render_services(self) -> None:
        if not hasattr(self, "services_frame") or not self.services_frame.winfo_exists():
            return
        for child in self.services_frame.winfo_children():
            child.destroy()
        if not self.current_profile_id:
            ctk.CTkLabel(self.services_frame, text="Buat project terlebih dahulu.", text_color="gray").pack(pady=24)
            return
        services = self.db.get_services(self.current_profile_id)
        if not services:
            ctk.CTkLabel(self.services_frame, text="Belum ada service pada project ini. Klik Add Service untuk membuatnya.", text_color="gray").pack(pady=24)
        for service in services:
            outer = ctk.CTkFrame(self.services_frame, corner_radius=10)
            outer.pack(fill="x", padx=5, pady=5)
            top = ctk.CTkFrame(outer, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(top, text=service["name"], font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
            running = self.processes.is_running(f"service:{service['id']}")
            ctk.CTkLabel(top, text="● Running" if running else "● Stopped", text_color="#3AA76D" if running else "gray").pack(side="right")
            details = f"{service['executable']} {service['args']}\nWorking directory: {service['workdir']}\nLocal URL: http://127.0.0.1:{service['port']}"
            if service.get("hostname"):
                details += f"\nPublic hostname: {service['hostname']}"
            ctk.CTkLabel(outer, text=details, justify="left", text_color="gray", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=12, pady=8)
            buttons = ctk.CTkFrame(outer, fg_color="transparent")
            buttons.pack(fill="x", padx=8, pady=(0, 8))
            if running:
                ctk.CTkButton(buttons, text="Stop", width=75, fg_color="#8B3333", hover_color="#6F2929", command=lambda s=service: self._stop_service(s, refresh=True)).pack(side="left", padx=4)
            else:
                ctk.CTkButton(buttons, text="Start", width=75, command=lambda s=service: self._start_service(s, refresh=True)).pack(side="left", padx=4)
            ctk.CTkButton(buttons, text="Edit", width=75, fg_color="transparent", border_width=1, command=lambda s=service: self._dialog_service(s)).pack(side="left", padx=4)
            ctk.CTkButton(buttons, text="Delete", width=75, fg_color="transparent", border_width=1, text_color="#E28C8C", command=lambda s=service: self._delete_service(s)).pack(side="left", padx=4)

    def _start_all_services(self) -> None:
        if not self.current_profile_id:
            return
        services = self.db.get_services(self.current_profile_id)
        started = 0
        errors = []
        for service in services:
            try:
                if not self.processes.is_running(f"service:{service['id']}"):
                    self.processes.start_service(service)
                    started += 1
            except Exception as exc:
                errors.append(f"{service['name']}: {exc}")
        self.logger.info(f"Start All requested for profile; started={started}, errors={len(errors)}")
        self.after(350, self._render_services)
        if errors:
            messagebox.showwarning("Start All", f"{started} service dimulai. Ada error:\n\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Start All", f"{started} service berhasil dimulai atau sudah berjalan.")

    def _stop_all_services(self) -> None:
        if not self.current_profile_id:
            return
        services = self.db.get_services(self.current_profile_id)
        def worker():
            for service in services:
                self.processes.stop(f"service:{service['id']}")
            self.logger.info(f"Stop All requested for profile; services={len(services)}")
            self.after(50, self._render_services)
        threading.Thread(target=worker, daemon=True).start()

    def _dialog_profile(self, existing: dict | None = None) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Project" if existing else "Add Project")
        dialog.geometry("570x260")
        dialog.transient(self)
        dialog.grab_set()
        dialog.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dialog, text="Project name").grid(row=0, column=0, sticky="w", padx=18, pady=(22, 8))
        name_entry = ctk.CTkEntry(dialog, width=350)
        name_entry.grid(row=0, column=1, sticky="ew", padx=18, pady=(22, 8))
        ctk.CTkLabel(dialog, text="Project directory").grid(row=1, column=0, sticky="w", padx=18, pady=8)
        dir_entry = ctk.CTkEntry(dialog)
        dir_entry.grid(row=1, column=1, sticky="ew", padx=(18, 6), pady=8)
        ctk.CTkButton(dialog, text="Browse", width=70, command=lambda: self._browse_into(dir_entry, directory=True)).grid(row=1, column=2, padx=(0, 18), pady=8)
        if existing:
            name_entry.insert(0, existing["name"])
            dir_entry.insert(0, existing["project_dir"])

        def save() -> None:
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Validation", "Nama project wajib diisi.", parent=dialog)
                return
            project_dir = dir_entry.get().strip()
            if project_dir and not Path(project_dir).expanduser().is_dir():
                messagebox.showerror("Validation", "Folder project tidak ditemukan.", parent=dialog)
                return
            duplicate = any(
                profile["name"].casefold() == name.casefold() and profile["id"] != (existing["id"] if existing else "")
                for profile in self.db.get_profiles()
            )
            if duplicate:
                messagebox.showerror("Validation", "Nama project sudah digunakan.", parent=dialog)
                return
            self.current_profile_id = self.db.save_profile(name, project_dir, existing["id"] if existing else None)
            self.logger.info(f"Project saved: {name}")
            dialog.destroy()
            self._reload_profile_list()

        ctk.CTkButton(dialog, text="Save Project", command=save).grid(row=2, column=1, sticky="e", padx=18, pady=18)

    def _browse_into(self, entry, directory: bool = False, file: bool = False) -> None:
        value = filedialog.askdirectory() if directory else filedialog.askopenfilename() if file else ""
        if value:
            entry.delete(0, "end")
            entry.insert(0, value)

    def _edit_current_profile(self) -> None:
        profile = next((p for p in self.db.get_profiles() if p["id"] == self.current_profile_id), None)
        if profile:
            self._dialog_profile(profile)

    def _delete_current_profile(self) -> None:
        profile = next((p for p in self.db.get_profiles() if p["id"] == self.current_profile_id), None)
        if not profile:
            return
        services = self.db.get_services(profile["id"])
        if any(self.processes.is_running(f"service:{s['id']}") for s in services):
            messagebox.showwarning("Project sedang berjalan", "Hentikan seluruh service pada project sebelum menghapusnya.")
            return
        if messagebox.askyesno("Delete Project", f"Hapus project '{profile['name']}' dan seluruh konfigurasi service-nya?"):
            self.db.delete_profile(profile["id"])
            self.current_profile_id = ""
            self.logger.info(f"Project deleted: {profile['name']}")
            self._reload_profile_list()

    def _dialog_service(self, existing: dict | None = None) -> None:
        if not self.current_profile_id and not existing:
            messagebox.showinfo("Pilih project", "Buat atau pilih project terlebih dahulu.")
            return
        if existing and self.processes.is_running(f"service:{existing['id']}"):
            messagebox.showwarning("Service sedang berjalan", "Stop service sebelum mengubah konfigurasinya.")
            return
        profiles = self.db.get_profiles()
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Service" if existing else "Add Service")
        dialog.geometry("780x700")
        dialog.minsize(720, 650)
        dialog.transient(self)
        dialog.grab_set()
        dialog.grid_columnconfigure(1, weight=1)

        SERVICE_PRESETS = {
            "-- Pilih Preset / Template (Opsional) --": None,
            "Laravel (PHP Artisan)": {
                "name": "Laravel Backend",
                "exe": "php",
                "args": '["artisan", "serve", "--host=127.0.0.1", "--port=8000"]',
                "port": "8000",
            },
            "React / Vite / Vue (npm dev)": {
                "name": "Vite Frontend",
                "exe": "npm",
                "args": '["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]',
                "port": "5173",
            },
            "Next.js (npm dev)": {
                "name": "Next.js Web",
                "exe": "npm",
                "args": '["run", "dev", "--", "-H", "127.0.0.1", "-p", "3000"]',
                "port": "3000",
            },
            "Node.js (Express / Script)": {
                "name": "Express API",
                "exe": "node",
                "args": '["server.js"]',
                "port": "3000",
            },
            "Python (FastAPI / Uvicorn)": {
                "name": "FastAPI App",
                "exe": "python",
                "args": '["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]',
                "port": "8000",
            },
            "Python (Django)": {
                "name": "Django App",
                "exe": "python",
                "args": '["manage.py", "runserver", "127.0.0.1:8000"]',
                "port": "8000",
            },
            "Python (Flask)": {
                "name": "Flask App",
                "exe": "python",
                "args": '["-m", "flask", "run", "--host=127.0.0.1", "--port=5000"]',
                "port": "5000",
            },
            "Golang (go run)": {
                "name": "Go Service",
                "exe": "go",
                "args": '["run", "main.go"]',
                "port": "8080",
            },
            ".NET Core (dotnet run)": {
                "name": ".NET API",
                "exe": "dotnet",
                "args": '["run", "--urls", "http://127.0.0.1:5000"]',
                "port": "5000",
            },
        }

        def add_field(row: int, label: str, value: str = "", hint: str = ""):
            ctk.CTkLabel(dialog, text=label).grid(row=row, column=0, sticky="nw", padx=18, pady=(10, 3))
            entry = ctk.CTkEntry(dialog, height=34)
            entry.grid(row=row, column=1, sticky="ew", padx=18, pady=(8, 3))
            if value:
                entry.insert(0, value)
            if hint:
                ctk.CTkLabel(dialog, text=hint, text_color="gray", font=ctk.CTkFont(size=10)).grid(row=row + 1, column=1, sticky="w", padx=18, pady=(0, 2))
            return entry

        ctk.CTkLabel(dialog, text="Project").grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))
        profile_names = [p["name"] for p in profiles]
        profile_combo = ctk.CTkComboBox(dialog, values=profile_names, state="readonly")
        profile_combo.grid(row=0, column=1, sticky="ew", padx=18, pady=(16, 4))
        default_profile = next((p for p in profiles if p["id"] == (existing["profile_id"] if existing else self.current_profile_id)), profiles[0])
        profile_combo.set(default_profile["name"])

        ctk.CTkLabel(dialog, text="Quick Preset").grid(row=1, column=0, sticky="w", padx=18, pady=6)
        preset_combo = ctk.CTkComboBox(dialog, values=list(SERVICE_PRESETS.keys()), state="readonly")
        preset_combo.grid(row=1, column=1, sticky="ew", padx=18, pady=6)
        preset_combo.set(list(SERVICE_PRESETS.keys())[0])

        default_workdir = existing["workdir"] if existing else default_profile.get("project_dir", "")
        name_entry = add_field(2, "Service name", existing["name"] if existing else "Laravel API")
        workdir_entry = add_field(4, "Working directory", default_workdir, "Folder tempat command dijalankan.")
        ctk.CTkButton(dialog, text="Browse", width=70, command=lambda: self._browse_into(workdir_entry, directory=True)).grid(row=4, column=2, padx=(0, 18), pady=(8, 3))
        exe_entry = add_field(6, "Executable", existing["executable"] if existing else "php", "Contoh: php, node, python, atau path lokal seperti .venv\\Scripts\\python.exe")
        default_args = '["artisan", "serve", "--host=127.0.0.1", "--port=8000"]'
        args_entry = add_field(8, "Arguments (JSON array)", __import__("json").dumps(existing.get("args", []), ensure_ascii=False) if existing else default_args, 'Contoh: ["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]')
        port_entry = add_field(10, "Local port", str(existing["port"]) if existing else "8000", "Port ini dipakai untuk target route localhost.")
        host_entry = add_field(12, "Public hostname (optional)", existing.get("hostname", "") if existing else "", "Contoh: api-dev.domainkamu.id. Diperlukan untuk Apply Routes.")

        def on_preset_selected(choice: str) -> None:
            preset = SERVICE_PRESETS.get(choice)
            if not preset:
                return
            if not existing or not name_entry.get().strip():
                name_entry.delete(0, "end")
                name_entry.insert(0, preset["name"])
            exe_entry.delete(0, "end")
            exe_entry.insert(0, preset["exe"])
            args_entry.delete(0, "end")
            args_entry.insert(0, preset["args"])
            port_entry.delete(0, "end")
            port_entry.insert(0, preset["port"])

        preset_combo.configure(command=on_preset_selected)

        warning = ctk.CTkLabel(dialog, text="Security: command dijalankan di komputer kamu. Gunakan executable dan arguments yang kamu percaya. Jangan simpan password/token di Arguments.", text_color="#D6A84B", wraplength=680, justify="left")
        warning.grid(row=14, column=0, columnspan=3, sticky="w", padx=18, pady=(10, 0))

        def save() -> None:
            try:
                profile_name = profile_combo.get()
                profile_id = next(p["id"] for p in profiles if p["name"] == profile_name)
                name = name_entry.get().strip()
                if not name:
                    raise ValueError("Nama service wajib diisi.")
                workdir = validate_workdir(workdir_entry.get())
                executable = exe_entry.get().strip()
                if not executable:
                    raise ValueError("Executable wajib diisi.")
                args = parse_arguments(args_entry.get())
                port = validate_port(port_entry.get())
                hostname = validate_hostname_basic(host_entry.get())
                if existing and self.processes.is_running(f"service:{existing['id']}"):
                    raise ValueError("Stop service sebelum menyimpan perubahan.")
                self.db.save_service(profile_id, name, workdir, executable, args, port, hostname, existing["id"] if existing else None)
                self.current_profile_id = profile_id
                self.logger.info(f"Service configuration saved: {name} (port {port})")
                dialog.destroy()
                self._render_services()
            except Exception as exc:
                messagebox.showerror("Tidak dapat menyimpan service", str(exc), parent=dialog)

        ctk.CTkButton(dialog, text="Save Service", command=save).grid(row=15, column=1, sticky="e", padx=18, pady=18)

    def _delete_service(self, service: dict) -> None:
        if self.processes.is_running(f"service:{service['id']}"):
            messagebox.showwarning("Service sedang berjalan", "Stop service sebelum menghapusnya.")
            return
        if messagebox.askyesno("Delete Service", f"Hapus konfigurasi service '{service['name']}'?"):
            self.db.delete_service(service["id"])
            self.logger.info(f"Service deleted: {service['name']}")
            self._render_services()

    def _start_service(self, service: dict, refresh: bool = False) -> None:
        try:
            self.processes.start_service(service)
            if refresh:
                if self.current_page == "Dashboard":
                    self.after(350, lambda: self.show_page("Dashboard"))
                else:
                    self.after(350, self._render_services)
        except Exception as exc:
            self.logger.error(f"Failed to start service {service.get('name', '')}: {exc}")
            messagebox.showerror("Start Service", str(exc))

    def _stop_service(self, service: dict, refresh: bool = False) -> None:
        def worker():
            self.processes.stop(f"service:{service['id']}")
            if refresh:
                if self.current_page == "Dashboard":
                    self.after(50, lambda: self.show_page("Dashboard"))
                else:
                    self.after(50, self._render_services)
        threading.Thread(target=worker, daemon=True).start()

    def _page_tunnel(self) -> None:
        self._page_header("Tunnel Manager", "Jalankan Quick Tunnel atau Named Tunnel dan sinkronkan hostname melalui Cloudflare API.")
        tunnel_status = "Running" if self.processes.is_running("tunnel") else "Stopped"
        status_card = ctk.CTkFrame(self.main_area, corner_radius=12)
        status_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(status_card, text="Tunnel process", text_color="gray").pack(anchor="w", padx=16, pady=(12, 2))
        self.tunnel_status_label = ctk.CTkLabel(status_card, text=f"● {tunnel_status}", text_color="#3AA76D" if tunnel_status == "Running" else "gray", font=ctk.CTkFont(size=19, weight="bold"))
        self.tunnel_status_label.pack(anchor="w", padx=16, pady=(0, 12))

        quick = ctk.CTkFrame(self.main_area, corner_radius=12)
        quick.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(quick, text="Quick Tunnel", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(14, 8))
        services = self.db.get_services()
        self.quick_service_map = {f"{s['profile_name']} / {s['name']} (:{s['port']})": s for s in services}
        quick_row = ctk.CTkFrame(quick, fg_color="transparent")
        quick_row.pack(fill="x", padx=12, pady=(0, 8))
        self.quick_service_combo = ctk.CTkComboBox(quick_row, values=list(self.quick_service_map) or ["No services"], width=380, state="readonly")
        self.quick_service_combo.pack(side="left", padx=4)
        if self.quick_service_map:
            self.quick_service_combo.set(next(iter(self.quick_service_map)))
        ctk.CTkButton(quick_row, text="Start Quick Tunnel", command=self._start_quick_tunnel).pack(side="left", padx=4)
        ctk.CTkButton(quick_row, text="Stop Tunnel", fg_color="#8B3333", hover_color="#6F2929", command=lambda: self.processes.stop("tunnel")).pack(side="left", padx=4)
        url_actions = ctk.CTkFrame(quick, fg_color="transparent")
        url_actions.pack(fill="x", padx=12, pady=(0, 12))
        self.quick_url_label = ctk.CTkLabel(url_actions, text=f"Public URL: {self.quick_url or 'Belum tersedia'}", text_color="#60A5FA", wraplength=850, justify="left")
        self.quick_url_label.pack(side="left", anchor="w", padx=4, pady=0, expand=True, fill="x")
        ctk.CTkButton(url_actions, text="Copy URL", width=90, fg_color="transparent", border_width=1, command=self._copy_quick_url).pack(side="right", padx=4)

        named = ctk.CTkFrame(self.main_area, corner_radius=12)
        named.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(named, text="Named Tunnel", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(named, text="Token diambil dari Windows Credential Manager. Hostname/ingress harus sudah dibuat atau disinkronkan di Cloudflare.", text_color="gray", wraplength=850, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        row = ctk.CTkFrame(named, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 14))
        ctk.CTkButton(row, text="Start Named Tunnel", command=self._start_named_tunnel).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Stop Tunnel", fg_color="#8B3333", hover_color="#6F2929", command=lambda: self.processes.stop("tunnel")).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Apply Routes via API", fg_color="transparent", border_width=1, command=self._apply_cloudflare_routes).pack(side="left", padx=4)

        ctk.CTkLabel(self.main_area, text="Catatan: Quick Tunnel menggunakan hostname sementara. Named Tunnel memakai token dan hostname tetap yang kamu konfigurasi di Cloudflare.", text_color="gray", wraplength=900, justify="left").pack(anchor="w", pady=4)

    def _start_quick_tunnel(self) -> None:
        if not self.quick_service_map:
            messagebox.showwarning("Quick Tunnel", "Tambahkan service terlebih dahulu.")
            return
        service = self.quick_service_map.get(self.quick_service_combo.get())
        if not service:
            return
        if not self.processes.is_running(f"service:{service['id']}"):
            if not messagebox.askyesno("Service belum berjalan", f"'{service['name']}' belum berjalan. Tetap mulai tunnel?"):
                return
        cloudflared = self.db.get_setting("cloudflared_path", self.cloudflared_path)
        try:
            self.quick_url = ""
            self.processes.start_tunnel("tunnel", cloudflared, "quick", f"http://127.0.0.1:{service['port']}")
            self.logger.info(f"Quick Tunnel requested for service {service['name']}")
        except Exception as exc:
            self.logger.error(f"Quick Tunnel failed: {exc}")
            messagebox.showerror("Quick Tunnel", str(exc))

    def _copy_quick_url(self) -> None:
        if not self.quick_url:
            messagebox.showinfo("Copy URL", "URL Quick Tunnel belum tersedia.")
            return
        self.clipboard_clear()
        self.clipboard_append(self.quick_url)
        self.logger.info("Quick Tunnel URL copied to clipboard")

    def _start_named_tunnel(self) -> None:
        try:
            token = SecretStore.get_secret("named_tunnel_token")
            cloudflared = self.db.get_setting("cloudflared_path", self.cloudflared_path)
            self.processes.start_tunnel("tunnel", cloudflared, "named", "", token)
        except Exception as exc:
            self.logger.error(f"Named Tunnel failed: {exc}")
            messagebox.showerror("Named Tunnel", str(exc))

    def _cloudflare_client(self) -> CloudflareClient:
        token = SecretStore.get_secret("cloudflare_api_token")
        return CloudflareClient(
            token,
            self.db.get_setting("cf_account_id"),
            self.db.get_setting("cf_zone_id"),
            self.db.get_setting("cf_tunnel_id"),
            self.db.get_setting("cf_domain"),
        )

    def _apply_cloudflare_routes(self) -> None:
        def worker():
            try:
                services = self.db.get_services()
                routes = [
                    {"hostname": item["hostname"], "service": f"http://127.0.0.1:{item['port']}"}
                    for item in services if item.get("hostname")
                ]
                client = self._cloudflare_client()
                result = client.apply_routes(routes)
                for message in result:
                    self.logger.info(f"Cloudflare: {message}")
                self.after(0, lambda: messagebox.showinfo("Cloudflare Routes", "Berhasil menerapkan route:\n\n" + "\n".join(result)))
            except Exception as exc:
                self.logger.error(f"Apply Cloudflare routes failed: {exc}")
                self.after(0, lambda e=str(exc): messagebox.showerror("Cloudflare Routes", e))

        threading.Thread(target=worker, daemon=True).start()

    def _page_logs(self) -> None:
        self._page_header("Logs & Diagnostics", "Log aplikasi dan output proses ditampilkan real-time. File log memakai rotasi 5 MB × 5 file.")
        toolbar = ctk.CTkFrame(self.main_area, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(toolbar, text="Refresh from file", command=self._load_log_file).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Clear view", fg_color="transparent", border_width=1, command=self._clear_log_view).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Open log folder", fg_color="transparent", border_width=1, command=self._open_log_folder).pack(side="left", padx=4)
        self.log_box = ctk.CTkTextbox(self.main_area, corner_radius=12, font=ctk.CTkFont(family="Consolas", size=11), wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self._load_log_file()

    def _load_log_file(self) -> None:
        if not hasattr(self, "log_box") or not self.log_box.winfo_exists():
            return
        self.log_box.delete("1.0", "end")
        log_path = self.logs_dir / "manager.log"
        try:
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
                self.log_box.insert("end", "\n".join(lines) + "\n")
        except OSError as exc:
            self.log_box.insert("end", f"Unable to read log: {exc}\n")
        self.log_box.see("end")

    def _clear_log_view(self) -> None:
        if hasattr(self, "log_box") and self.log_box.winfo_exists():
            self.log_box.delete("1.0", "end")

    def _open_log_folder(self) -> None:
        try:
            if sys.platform == "win32":
                import os
                os.startfile(self.logs_dir)  # noqa: S606 - opens a local folder using the OS shell association.
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(self.logs_dir)], shell=False)
        except Exception as exc:
            messagebox.showerror("Open folder", str(exc))

    def _secret_exists(self, name: str) -> bool:
        try:
            return bool(SecretStore.get_secret(name))
        except Exception as exc:
            self.logger.error(f"Credential store unavailable ({type(exc).__name__})")
            return False

    def _page_settings(self) -> None:
        self._page_header("Settings", "Konfigurasi executable dan integrasi Cloudflare. Secret disimpan di OS credential store, bukan database aplikasi.")
        scroll = ctk.CTkScrollableFrame(self.main_area, corner_radius=12)
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(1, weight=1)

        def entry_field(row: int, label: str, key: str, placeholder: str = ""):
            ctk.CTkLabel(scroll, text=label).grid(row=row, column=0, sticky="w", padx=16, pady=9)
            entry = ctk.CTkEntry(scroll, placeholder_text=placeholder)
            entry.grid(row=row, column=1, sticky="ew", padx=16, pady=9)
            value = self.db.get_setting(key)
            if value:
                entry.insert(0, value)
            return entry

        self.setting_entries = {}
        self.setting_entries["cloudflared_path"] = entry_field(0, "cloudflared.exe path", "cloudflared_path", "Contoh: D:\\Coding\\CLOUDFLARE\\cloudflared.exe")
        ctk.CTkButton(scroll, text="Browse", width=75, command=lambda: self._browse_into(self.setting_entries["cloudflared_path"], file=True)).grid(row=0, column=2, padx=(0, 16), pady=9)
        ctk.CTkLabel(scroll, text="Cloudflare API", font=ctk.CTkFont(size=15, weight="bold")).grid(row=1, column=0, columnspan=3, sticky="w", padx=16, pady=(18, 4))
        for row, label, key, placeholder in [
            (2, "Account ID", "cf_account_id", "Cloudflare Account ID"),
            (3, "Zone ID", "cf_zone_id", "Zone ID domain"),
            (4, "Tunnel ID", "cf_tunnel_id", "UUID Named Tunnel"),
            (5, "Domain", "cf_domain", "domainkamu.id"),
        ]:
            self.setting_entries[key] = entry_field(row, label, key, placeholder)

        ctk.CTkLabel(scroll, text="Cloudflare API Token",).grid(row=6, column=0, sticky="w", padx=16, pady=9)
        self.api_token_entry = ctk.CTkEntry(scroll, show="●", placeholder_text="Kosongkan untuk mempertahankan token tersimpan")
        self.api_token_entry.grid(row=6, column=1, sticky="ew", padx=16, pady=9)
        api_saved = self._secret_exists("cloudflare_api_token")
        self.api_token_status = ctk.CTkLabel(scroll, text="Saved in Credential Manager" if api_saved else "Not configured", text_color="#3AA76D" if api_saved else "gray")
        self.api_token_status.grid(row=6, column=2, sticky="w", padx=(0, 16))

        ctk.CTkLabel(scroll, text="Named Tunnel Token").grid(row=7, column=0, sticky="w", padx=16, pady=9)
        self.tunnel_token_entry = ctk.CTkEntry(scroll, show="●", placeholder_text="Kosongkan untuk mempertahankan token tersimpan")
        self.tunnel_token_entry.grid(row=7, column=1, sticky="ew", padx=16, pady=9)
        tunnel_saved = self._secret_exists("named_tunnel_token")
        self.tunnel_token_status = ctk.CTkLabel(scroll, text="Saved in Credential Manager" if tunnel_saved else "Not configured", text_color="#3AA76D" if tunnel_saved else "gray")
        self.tunnel_token_status.grid(row=7, column=2, sticky="w", padx=(0, 16))

        buttons = ctk.CTkFrame(scroll, fg_color="transparent")
        buttons.grid(row=8, column=0, columnspan=3, sticky="ew", padx=12, pady=14)
        ctk.CTkButton(buttons, text="Save Settings", command=self._save_settings).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Test Cloudflare API", fg_color="transparent", border_width=1, command=self._test_cloudflare_api).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Clear API Token", fg_color="transparent", border_width=1, text_color="#E28C8C", command=lambda: self._clear_secret("cloudflare_api_token")).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Clear Tunnel Token", fg_color="transparent", border_width=1, text_color="#E28C8C", command=lambda: self._clear_secret("named_tunnel_token")).pack(side="left", padx=4)

        info = ctk.CTkFrame(scroll, corner_radius=10)
        info.grid(row=9, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 16))
        ctk.CTkLabel(info, text="Credential & log storage", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(info, text=f"App data: {self.data_dir}\nLogs: {self.logs_dir}\nSecrets: Windows Credential Manager (via keyring)", text_color="gray", justify="left", wraplength=850).pack(anchor="w", padx=12, pady=(0, 12))

    def _save_settings(self) -> None:
        for key, entry in self.setting_entries.items():
            value = entry.get().strip()
            if key == "cloudflared_path" and value and not Path(value).expanduser().is_file():
                messagebox.showerror("Settings", "File cloudflared.exe tidak ditemukan.")
                return
            self.db.set_setting(key, value)
        try:
            api_token = self.api_token_entry.get().strip()
            tunnel_token = self.tunnel_token_entry.get().strip()
            if api_token:
                SecretStore.set_secret("cloudflare_api_token", api_token)
                self.api_token_entry.delete(0, "end")
            if tunnel_token:
                SecretStore.set_secret("named_tunnel_token", tunnel_token)
                self.tunnel_token_entry.delete(0, "end")
        except Exception as exc:
            messagebox.showerror("Credential Manager", str(exc))
            return
        self.cloudflared_path = self.db.get_setting("cloudflared_path")
        self.api_token_status.configure(text="Saved in Credential Manager" if self._secret_exists("cloudflare_api_token") else "Not configured")
        self.tunnel_token_status.configure(text="Saved in Credential Manager" if self._secret_exists("named_tunnel_token") else "Not configured")
        self.logger.info("Settings saved")
        messagebox.showinfo("Settings", "Settings berhasil disimpan.")

    def _clear_secret(self, name: str) -> None:
        if messagebox.askyesno("Remove secret", "Hapus secret ini dari Windows Credential Manager?"):
            SecretStore.delete_secret(name)
            self.logger.info(f"Secret removed: {name}")
            if name == "cloudflare_api_token" and hasattr(self, "api_token_status"):
                self.api_token_status.configure(text="Not configured", text_color="gray")
            if name == "named_tunnel_token" and hasattr(self, "tunnel_token_status"):
                self.tunnel_token_status.configure(text="Not configured", text_color="gray")

    def _test_cloudflare_api(self) -> None:
        def worker():
            try:
                # Save non-secret fields first so tests always use visible current values.
                for key, entry in self.setting_entries.items():
                    self.db.set_setting(key, entry.get().strip())
                token = self.api_token_entry.get().strip() or SecretStore.get_secret("cloudflare_api_token")
                if self.api_token_entry.get().strip():
                    SecretStore.set_secret("cloudflare_api_token", token)
                    self.after(0, lambda: self.api_token_entry.delete(0, "end"))
                client = CloudflareClient(
                    token,
                    self.db.get_setting("cf_account_id"),
                    self.db.get_setting("cf_zone_id"),
                    self.db.get_setting("cf_tunnel_id"),
                    self.db.get_setting("cf_domain"),
                )
                tunnel_name = client.test_connection()
                self.logger.info(f"Cloudflare API connection successful (tunnel: {tunnel_name})")
                self.after(0, lambda: messagebox.showinfo("Cloudflare API", f"Koneksi berhasil. Tunnel: {tunnel_name}"))
            except Exception as exc:
                self.logger.error(f"Cloudflare API test failed: {exc}")
                self.after(0, lambda e=str(exc): messagebox.showerror("Cloudflare API", e))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self) -> None:
        collected_lines = []
        for _ in range(50):
            try:
                line = self.event_queue.get_nowait()
                collected_lines.append(line)
            except queue.Empty:
                break

        for line in collected_lines:
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                self.quick_url = match.group(0)
                if self.current_page == "Tunnel Manager" and hasattr(self, "quick_url_label") and self.quick_url_label.winfo_exists():
                    self.quick_url_label.configure(text=f"Public URL: {self.quick_url}")

        if collected_lines and self.current_page == "Logs & Diagnostics" and hasattr(self, "log_box") and self.log_box.winfo_exists():
            self.log_box.insert("end", "\n".join(collected_lines) + "\n")
            try:
                line_count = int(self.log_box.index("end-1c").split(".")[0])
                if line_count > 1000:
                    self.log_box.delete("1.0", f"{line_count - 700}.0")
            except Exception:
                pass
            self.log_box.see("end")

        if not self._closing:
            self.after(120, self._poll_events)

    def _refresh_status(self) -> None:
        if self._closing:
            return
        if hasattr(self, "cloudflared_state_label") and self.cloudflared_state_label.winfo_exists():
            now = time.time()
            if not hasattr(self, "_last_cf_check") or (now - self._last_cf_check > 15):
                path = self.db.get_setting("cloudflared_path", self.cloudflared_path)
                self._cf_exists = bool(path and (Path(path).is_file() or shutil.which(path)))
                self._last_cf_check = now
            exists = getattr(self, "_cf_exists", False)
            self.cloudflared_state_label.configure(
                text="● cloudflared detected" if exists else "● cloudflared not found",
                text_color="#3AA76D" if exists else "#D6A84B",
            )
        if self.current_page == "Tunnel Manager":
            if hasattr(self, "quick_url_label") and self.quick_url_label.winfo_exists():
                self.quick_url_label.configure(text=f"Public URL: {self.quick_url or 'Belum tersedia'}")
            if hasattr(self, "tunnel_status_label") and self.tunnel_status_label.winfo_exists():
                running = self.processes.is_running("tunnel")
                self.tunnel_status_label.configure(text="● Running" if running else "● Stopped", text_color="#3AA76D" if running else "gray")
        self.after(1800, self._refresh_status)

    def _on_close(self) -> None:
        running = self.processes.running_keys()
        if running and not messagebox.askyesno("Exit", "Ada proses yang masih berjalan. Hentikan seluruh proses dan keluar?"):
            return
        self._closing = True
        self.processes.stop_all()
        self.logger.info("Application closed")
        self.destroy()


if __name__ == "__main__":
    try:
        app = TunnelManagerApp()
        app.mainloop()
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.exception("Application failed to start: %s", exc)
        raise
