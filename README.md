# Cloudflare Tunnel Manager (Windows-first)

Aplikasi desktop Python untuk mengelola project lokal, proses service, Cloudflare Quick Tunnel, Named Tunnel, konfigurasi route DNS/ingress melalui Cloudflare API, dan log.

> Ini adalah tool development/preview. Bukan hosting production dan bukan pengganti autentikasi aplikasi.

## Fitur

- Dashboard status project, service, dan tunnel.
- Multi-project dengan beberapa service per project.
- Start/stop service lokal per service atau Start All/Stop All per project menggunakan executable + JSON arguments.
- Quick Tunnel untuk URL sementara `trycloudflare.com`.
- Named Tunnel menggunakan Tunnel Token dari Windows Credential Manager.
- Integrasi Cloudflare API untuk mengatur ingress route dan CNAME DNS bagi satu Named Tunnel.
- Log real-time ke GUI dan file dengan rotasi 5 MB × 5 file.
- SQLite untuk metadata project/service.
- Secret disimpan lewat `keyring`, bukan di SQLite atau file konfigurasi.

## 1. Persyaratan

- Windows 10/11 64-bit direkomendasikan.
- Python 3.11 atau lebih baru.
- `cloudflared.exe` dari halaman resmi Cloudflare.
- Koneksi internet.
- Untuk Named Tunnel + Cloudflare API: domain sudah aktif di Cloudflare dan Named Tunnel sudah dibuat.

Unduh Cloudflared hanya dari:
<https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>

Letakkan executable di `bin/cloudflared.exe`, atau isi path lengkap melalui **Settings**. Binary Cloudflared tidak disertakan di ZIP ini.

## 2. Cara Menjalankan

### Cara 1: Jalankan Tanpa Jendela CMD (Rekomendasi)
- Cukup double-click file **`run_gui.vbs`** (atau jalankan **`tunnel.bat`**).
- `tunnel.bat` akan menjalankan aplikasi via `pythonw.exe` di background dan jendela command prompt akan langsung tertutup otomatis.

### Cara 2: Manual via Terminal
```bat
cd /d D:\Coding\CLOUDFLARE
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

### Cara 3: Build Menjadi Standalone EXE (No Console / Windowed)
Jalankan file batch:
```bat
build_exe.bat
```
Script ini akan mem-package aplikasi menggunakan PyInstaller dengan mode `--noconsole` / `--windowed`. Hasil build ada di `dist\CloudflareTunnelManager\CloudflareTunnelManager.exe` dan saat dibuka tidak akan memunculkan jendela hitam `cmd.exe` sama sekali.

## 3. Tambahkan Project dan Service

1. Buka **Projects & Services**.
2. Klik **Add Project** dan pilih folder project.
3. Klik **Add Service**.
4. **Pilih template dari dropdown "Quick Preset"** (Tersedia Laravel, React/Vite, Next.js, FastAPI, Express, Django, Flask, Go, .NET Core) atau isi manual.
5. Pilih **Working directory** dan sesuaikan port jika perlu, lalu klik **Save Service**.
6. Klik **Start** untuk menjalankan service.

> **Panduan Lengkap Semua Framework (Frontend & Backend)**:
> Lihat panduan best practice lengkap di [docs/JSON_ARRAY_BEST_PRACTICE.md](file:///d:/Coding/CLOUDFLARE/docs/JSON_ARRAY_BEST_PRACTICE.md).

### Contoh Laravel
- **Quick Preset**: Pilih `Laravel (PHP Artisan)`
- Executable: `php`
- Arguments: `["artisan", "serve", "--host=127.0.0.1", "--port=8000"]`
- Port: `8000`

### Contoh React / Vite / Vue
- **Quick Preset**: Pilih `React / Vite / Vue (npm dev)`
- Executable: `npm`
- Arguments: `["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]`
- Port: `5173`
```

- Port: `5173`
- Public hostname: kosong jika tidak perlu route terpisah.

`Arguments` wajib JSON array. Jangan menaruh password, API key, atau Tunnel Token di sana.

## 4. Quick Tunnel

1. Jalankan service yang ingin diuji.
2. Buka **Tunnel Manager**.
3. Pilih service dari daftar Quick Tunnel.
4. Klik **Start Quick Tunnel**.
5. URL `https://....trycloudflare.com` akan muncul di log dan label Public URL.
6. Stop tunnel dengan **Stop Tunnel**.

Quick Tunnel URL bersifat sementara dan dapat berubah setiap kali tunnel dibuat ulang.

## 5. Named Tunnel dengan hostname tetap

Aplikasi ini mengelola koneksi untuk Named Tunnel yang sudah dibuat. Pembuatan Named Tunnel awal tetap dilakukan dari Cloudflare Dashboard.

1. Tambahkan domain ke Cloudflare dan pastikan statusnya **Active**.
2. Di Cloudflare Zero Trust, buat tunnel melalui **Networking → Tunnels → Create Tunnel**.
3. Pilih Cloudflared dan Windows AMD64. Simpan Tunnel ID dan Tunnel Token.
4. Di aplikasi, buka **Settings**.
5. Isi `cloudflared.exe path`, Account ID, Zone ID, Tunnel ID, dan domain zone (contoh `example.com`).
6. Masukkan Tunnel Token. Klik **Save Settings**.
7. Tambahkan `Public hostname` untuk service, misalnya `api-dev.example.com`.
8. Klik **Apply Routes via API** di halaman Tunnel Manager.
9. Klik **Start Named Tunnel**.

Semua hostname yang terisi di konfigurasi service akan dimasukkan ke ingress Named Tunnel yang sama. Route lama yang tidak dikelola aplikasi dipertahankan; route dengan hostname yang sama akan diperbarui oleh konfigurasi service. Rule catch-all dipastikan berada paling akhir. Jika menemukan konfigurasi ingress ambigu atau route path khusus dengan hostname yang sama, aplikasi berhenti dan meminta pemeriksaan manual.

### Cloudflare API Token

Buat API Token khusus, jangan gunakan Global API Key. Batasi resource ke account dan zone yang relevan. Untuk operasi aplikasi ini, berikan izin yang diperlukan oleh Cloudflare API:

- Account → Cloudflare Tunnel → Edit (untuk membaca/mengubah konfigurasi tunnel).
- Zone → DNS → Edit (untuk membaca/membuat CNAME tunnel).

Simpan token API melalui menu Settings. Aplikasi menyimpannya menggunakan `keyring`/Windows Credential Manager. Bila account menggunakan kebijakan permission yang lebih granular, sesuaikan izin dengan dokumentasi Cloudflare.

Dokumentasi resmi:
- <https://developers.cloudflare.com/tunnel/get-started/>
- <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/>
- <https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/>

## 6. Vercel Preview

Untuk frontend Vite, set environment variable pada Vercel Preview:

```env
VITE_API_URL=https://api-dev.example.com/api
```

Lakukan redeploy agar environment variable baru masuk ke build frontend. Pastikan konfigurasi CORS Laravel mengizinkan origin Vercel yang digunakan. Untuk Sanctum cookie-based SPA authentication, atur domain/cookie sesuai persyaratan Sanctum; jangan berasumsi token bearer dan cookie-based auth memiliki konfigurasi yang sama.

## 7. Penyimpanan lokal

Data aplikasi disimpan di:

```text
%APPDATA%\CloudflareTunnelManager\
├── manager.db
└── logs\
    ├── manager.log
    ├── manager.log.1
    └── ...
```

- SQLite hanya menyimpan nama project, service, hostname, port, path, dan preferensi non-secret.
- Cloudflare API Token dan Named Tunnel Token disimpan melalui keyring ke Windows Credential Manager.
- Log dirotasi pada 5 MB dengan maksimal 5 file backup.

## 8. Catatan keamanan penting

1. **Tidak ada klaim bebas vulnerability.** Paket ini menggunakan beberapa kontrol defensif, tetapi tetap perlu diperiksa dan diuji di komputer target.
2. Proses lokal dijalankan menggunakan `subprocess` dengan `shell=False`. Aplikasi tidak mengeksekusi command string melalui `cmd.exe` atau PowerShell.
3. Executable dan arguments adalah konfigurasi lokal yang kamu masukkan sendiri. Menjalankan executable yang tidak tepercaya tetap dapat membahayakan akun Windows kamu.
4. Named Tunnel Token diberikan ke proses `cloudflared` melalui environment variable `TUNNEL_TOKEN` (bukan command-line argument). Ini menjaga token tidak dapat dibaca oleh user/proses lain melalui pemeriksaan command line (Task Manager / Process Explorer).
5. Output aplikasi service diteruskan ke log. Jika aplikasi sendiri mencetak password, cookie, token, atau data pribadi, informasi tersebut dapat masuk ke file log. Hindari logging secret di aplikasi yang sedang diuji.
6. Log melakukan redaksi pola umum Bearer/API token, tetapi redaksi bukan jaminan semua format rahasia terdeteksi.
7. Hostname route dibatasi ke subdomain dari domain yang diisi, dan service origin dibatasi ke HTTP localhost/127.0.0.1. Record DNS A/AAAA atau CNAME konflik tidak ditimpa otomatis.
8. Jangan mengekspos MySQL, phpMyAdmin, Redis, atau port manajemen database melalui tunnel.
9. Hostname publik tetap dapat diakses dari internet ketika tunnel dan service berjalan. Untuk preview privat, aktifkan Cloudflare Access atau autentikasi aplikasi.
10. Jangan commit file database/log, token, file `.env`, atau credential ke Git.
11. Gunakan versi Python, dependency, dan `cloudflared` yang masih didukung serta update secara berkala.

## 9. Limitasi versi ini

- Pembuatan Named Tunnel awal dilakukan di Cloudflare Dashboard; aplikasi ini mengelola route dan menjalankan tunnel yang sudah ada.
- Satu konfigurasi Named Tunnel global dipakai bersama oleh route service dari seluruh project.
- Quick Tunnel hanya mengekspos satu service lokal per proses tunnel.
- Aplikasi ini tidak mengubah `.env` Vercel secara otomatis dan tidak melakukan deploy Vercel.
- Penghentian service mencoba terminate proses dan, jika perlu di Windows, menghentikan process tree berdasarkan PID yang dibuat aplikasi.
- App belum dipaketkan menjadi `.exe`; jalankan dengan Python sesuai langkah instalasi.

## 10. Troubleshooting

- **`cloudflared.exe not found`**: atur path lengkap di Settings.
- **Service gagal start**: cek executable, working directory, format JSON arguments, dan port.
- **Port sudah dipakai**: hentikan proses lain yang memakai port tersebut.
- **Named Tunnel tidak connect**: cek Tunnel Token, koneksi internet, dan status tunnel di Cloudflare Dashboard.
- **Apply Routes gagal**: cek Account ID, Zone ID, Tunnel ID, domain, API Token permissions, dan DNS record yang sudah ada.
- **Hostname tidak merespons**: pastikan Named Tunnel berjalan, service lokal berjalan, ingress mengarah ke port yang benar, dan DNS record aktif.
- **Credential Manager gagal**: pastikan dependency `keyring` terpasang dan Windows Credential Manager dapat digunakan.

---

Versi paket: 1.0.0 · Python desktop GUI · Windows-first

## 11. Pemeriksaan dependency

Setelah environment dibuat, kamu dapat memeriksa dependency terhadap advisory kerentanan yang diketahui:

```bat
.venv\Scripts\python.exe -m pip install pip-audit
.venv\Scripts\pip-audit.exe -r requirements.txt
```

`pip-audit` memeriksa dependency yang terdaftar terhadap database advisory yang tersedia; hasil bersih bukan jaminan aplikasi atau semua dependency transitif bebas dari risiko.
