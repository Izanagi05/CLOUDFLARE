# Product Requirement Document (PRD)
## Cloudflare Tunnel Manager GUI (Open-Source Edition)

---

## 1. Executive Summary & Vision

### 1.1 Background
Pengembang web lokal (misalnya pengembang Laravel, Node.js/Vite, Python FastAPI, Go) sering kali perlu mengekspos port lokal ke internet untuk:
- Webhook testing (Payment Gateway seperti Midtrans/Xendit/Stripe, WhatsApp Bot, OAuth callbacks).
- Client review atau presentasi demo tanpa perlu deployment server.
- Mobile device testing di jaringan berbeda.

Cloudflare Tunnel (`cloudflared`) merupakan solusi tunneling gratis, cepat, dan aman. Namun, penggunaan CLI sering merepotkan:
- Mengharuskan menghafal command flag yang panjang.
- Mengelola banyak proses secara manual (Terminal untuk `php artisan serve`, Terminal untuk `npm run dev`, Terminal untuk `cloudflared tunnel`).
- Pengaturan Named Tunnel dengan custom domain memerlukan sinkronisasi manual file konfigurasi YAML dan DNS CNAME di dashboard Cloudflare.

### 1.2 Vision
Membangun **Cloudflare Tunnel Manager GUI** sebagai aplikasi desktop open-source yang ringan, aman, dan mudah digunakan bagi pengembang. Aplikasi ini menggabungkan **Local Process Runner** dan **Cloudflare Tunnel Client (Quick & Named Tunnel)** dalam satu antarmuka modern tanpa memunculkan jendela console hitam (`cmd.exe`).

---

## 2. Target Audience & Personas

1. **Solo Web Developer**: Mengembangkan backend & frontend di lokal dan membutuhkan URL publik instan untuk testing webhook.
2. **Team Collaborator / Freelancer**: Memerlukan custom domain tetap (contoh: `api-demo.domain.com`) untuk klien dengan integrasi DNS Cloudflare otomatis.
3. **Open-Source Community**: Pengembang yang mencari alternatif ringan untuk Ngrok / Localtunnel dengan privasi dan kontrol penuh.

---

## 3. System Architecture & Tech Stack

```
+-------------------------------------------------------------+
|                     CustomTkinter GUI                       |
|   (Dashboard | Projects & Services | Tunnel | Logs | Setup) |
+------------------------------+------------------------------+
                               |
         +---------------------+---------------------+
         |                                           |
         v                                           v
+------------------+                       +-------------------+
|  ProcessManager  |                       |  CloudflareClient |
|  - CREATE_NO_WIN |                       |  (REST API v4)    |
|  - env TUNNEL_TOK|                       |  - CNAME Records  |
|  - Non-blocking  |                       |  - Ingress Config |
+--------+---------+                       +-------------------+
         |
         +-------------> Subprocesses (cloudflared.exe, php, node, etc.)
         |
         v
+------------------+        +----------------------------------+
|    Database      |        |           SecretStore            |
|   SQLite (WAL)   |        |   Windows Credential Manager     |
| (Profiles/Config)|        |     (via Python keyring)         |
+------------------+        +----------------------------------+
```

### 3.1 Tech Stack
- **Language**: Python 3.10+
- **GUI Framework**: `customtkinter` (Modern dark-mode UI berbasis Tkinter)
- **Credential Storage**: `keyring` (Terintegrasi langsung dengan Windows Credential Manager)
- **Database**: SQLite3 dengan mode WAL (Write-Ahead Logging)
- **HTTP Client**: `requests` dengan strict HTTPS, TLS verification, bounded timeouts
- **Binary Runner**: `cloudflared.exe` (Cloudflare Tunnel daemon)
- **Packaging**: PyInstaller dengan flag `--noconsole` / `--windowed`

---

## 4. Analisis Kerentanan & Mitigasi Keamanan

| Area | Potensi Kerentanan / Risiko | Status / Mitigasi yang Diterapkan |
| :--- | :--- | :--- |
| **Penyimpanan Token** | API Token & Tunnel Token disimpan dalam plaintext di SQLite atau file `.env`. | **Mitigasi:** Token disimpan di **Windows Credential Manager** via `keyring`. SQLite hanya menyimpan metadata (Account ID, Zone ID, Hostname). |
| **Command Line Exposure** | Passing token via CLI arg: `cloudflared tunnel run --token <token>` dapat dibaca oleh proses lokal lain melalui Task Manager/WMI. | **Mitigasi:** Token di-pass via environment variable `TUNNEL_TOKEN` ke child process, bukan via CLI arg. |
| **Command Injection** | Menjalankan perintah shell sembarangan via `shell=True`. | **Mitigasi:** Menggunakan `shell=False`, arguments divalidasi sebagai JSON array of strings, karakter NUL/newline ditolak. |
| **DNS Hijacking / Overwrite** | Mengubah record DNS yang sudah ada tanpa izin pengguna. | **Mitigasi:** `cloudflare_api.py` memvalidasi CNAME eksisting dan menolak menimpa record selain CNAME target tunnel. |
| **SSRF / Origin Loopback** | Tunnel diarahkan ke IP privat berbahaya / cloud metadata (`169.254.169.254`). | **Mitigasi:** Target service divalidasi ketat hanya ke `localhost` atau `127.0.0.1`. |
| **Data Leakage in Logs** | Token atau authorization header tercetak ke log file. | **Mitigasi:** `EventLogger` menerapkan regex redactor otomatis (`Bearer [REDACTED]`, `--token [REDACTED]`, `api-token [REDACTED]`). |
| **DoS / Memory Exhaustion** | Output proses yang masif membuat GUI hang dan menghabiskan RAM. | **Mitigasi:** Batch event queue reading dan pembatasan buffer log widget maksimal 1.000 baris dengan pembersihan berkala. |

---

## 5. Fitur Utama & Functional Requirements

### 5.1 Project & Service Management
- Membuat profile project (misal: "E-Commerce App", "Portfolio").
- Mengatur multi-service dalam 1 project:
  - **Quick Preset Dropdown**: Template siap pakai untuk Laravel, Vite, Next.js, FastAPI, Express, Django, Flask, Go, dan .NET Core.
  - Working directory.
  - Executable (`php`, `node`, `python`, path relatif seperti `.venv\Scripts\python.exe`, atau full path).
  - Arguments (format JSON array: `["artisan", "serve"]` dengan smart parser yang mendukung petik tunggal dan ganda).
  - Local port (`1–65535`).
  - Public hostname (opsional).
- Tombol **Start All** & **Stop All** dengan thread asynchronous agar UI tidak freeze.

### 5.2 Quick Tunnel (Gratis & Instan)
- Memilih service lokal yang akan diekspos.
- Menjalankan `cloudflared tunnel --url http://127.0.0.1:PORT`.
- Auto-detect URL publik sementara (`https://*.trycloudflare.com`) dari stream stdout.
- Tombol **Copy URL** satu kali klik ke clipboard.

### 5.3 Named Tunnel (Domain Sendiri)
- Integrasi ke akun Cloudflare resmi dengan custom domain.
- Fitur **Apply Routes via API**:
  - Otomatis membuat record CNAME di Cloudflare DNS (`hostname -> tunnel-id.cfargotunnel.com`).
  - Otomatis memperbarui konfigurasi ingress rules remote Cloudflare tanpa perlu edit file YAML manual.
  - Mempertahankan route ingress yang sudah ada (tidak menimpa rule kustom milik user).
- Menjalankan tunnel persisten dengan token aman.

### 5.4 Logs & Diagnostics Real-Time
- Tampilan live logs dari `cloudflared` dan semua service lokal yang berjalan.
- Log rotasi otomatis (5 MB x 5 file backup).
- Fitur **Refresh from file**, **Clear view**, dan **Open log folder**.

### 5.5 Settings & Credential Store
- Konfigurasi path `cloudflared.exe`.
- Input Account ID, Zone ID, Tunnel ID, Domain.
- Input Cloudflare API Token & Named Tunnel Token (disimpan terlindung).
- Fitur **Test Cloudflare API** untuk validasi koneksi sebelum menjalankan route.

---

## 6. Non-Functional Requirements (NFR)

### 6.1 Performa & Zero-Lag GUI
- **Non-blocking Operations**: Semua panggilan jaringan (Cloudflare API) dan operasi penghentian proses (`taskkill`) dijalankan pada background daemon thread.
- **Throttled Logging**: Pengiriman log ke Textbox di-batch per 50 item dan membatasi ukuran teks agar CustomTkinter tetap responsif.
- **Disk I/O Cache**: Status deteksi file `cloudflared` dicache untuk mencegah scan hard disk (`shutil.which`) berulang setiap 1-2 detik.

### 6.2 Zero-Console Window Experience
- Saat aplikasi di-compile menjadi `.exe` dengan PyInstaller, flag `--noconsole` dan `--windowed` memastikan Windows PE subsystem diset ke GUI, bukan Console.
- Semua child process (`cloudflared`, service lokal, `taskkill`) menggunakan flag `subprocess.CREATE_NO_WINDOW` (`0x08000000`) sehingga tidak ada jendela cmd hitam yang berkedip atau tetap terbuka.
- Disediakan runner `tunnel.bat` (dengan `start pythonw` lalu exit) dan `run_gui.vbs` untuk menjalankan skrip Python langsung di background.

---

## 7. Roadmap Pengembangan GitHub Open-Source

```
+-------------------------------------------------------------------------+
| Milestone 1: Core Stability & Silent Execution (CURRENT)                |
| - Async background workers for API & process tasks                      |
| - Subprocess CREATE_NO_WINDOW & TUNNEL_TOKEN env variable               |
| - Zero cmd window runner (tunnel.bat & run_gui.vbs)                     |
| - PyInstaller build script (build_exe.bat)                              |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Milestone 2: Usability & Auto-Setup (Next Release)                      |
| - Auto-download latest cloudflared binary jika belum ada di folder bin  |
| - System Tray Icon (pystray) agar GUI bisa diminimize ke tray           |
| - Auto-start on boot option                                             |
| - Export / Import Project Profiles (JSON backup)                        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Milestone 3: Advanced Tunnel Features & CI/CD                           |
| - Webhook Request Inspector (mini traffic log: method, status, latency) |
| - Dukungan Multi-Tunnel simultan (Quick Tunnel + Named Tunnel bersamaan)|
| - GitHub Actions CI/CD workflow untuk compile exe otomatis per release  |
| - Multi-platform support (Linux & macOS)                                |
+-------------------------------------------------------------------------+
```
