# Panduan Best Practice: JSON Array Arguments & Executable
## Cloudflare Tunnel Manager GUI (Untuk Semua Stack Frontend & Backend)

Dokumen ini adalah referensi lengkap konfigurasi **Executable** dan **Arguments (JSON Array)** agar semua jenis project (Frontend maupun Backend) dapat berjalan sempurna, stabil, dan terhubung tanpa kendala ke Cloudflare Tunnel di Windows.

---

## 1. Mengapa Menggunakan Format JSON Array?

Aplikasi ini menjalankan proses menggunakan `subprocess.Popen(..., shell=False)`:
1. **Keamanan (Anti-Command Injection)**: Command tidak dilewatkan ke shell `cmd.exe` atau PowerShell, sehingga terhindar dari injeksi karakter berbahaya (`&`, `|`, `;`, `` ` ``).
2. **Kestabilan Argument**: Setiap parameter dipisahkan secara eksplisit sebagai elemen array, sehingga argumen yang memiliki spasi atau tanda sama dengan (`=`) tidak akan terpotong salah oleh Windows.
3. **Multi-Platform Ready**: Format array adalah standar POSIX dan Windows PE yang konsisten di semua sistem operasi.

---

## 2. Aturan Emas (Crucial Golden Rules)

### Aturan 1: Wajib Bind ke IPv4 `127.0.0.1` (Penyebab Utama 502 Bad Gateway)
Pada Node.js v17+ dan Windows modern:
- `localhost` sering kali di-resolve ke IPv6 loopback (`::1`).
- Jika service frontend Anda (misal Vite atau Next.js) hanya mendengarkan di IPv6, sedangkan Cloudflare Tunnel mencoba menyambung ke IPv4 `http://127.0.0.1:PORT`, maka koneksi akan **ditolak (Connection Refused)** dan Cloudflare menampilkan error **502 Bad Gateway**.
- **Solusi**: Selalu tambahkan flag `--host 127.0.0.1` atau `-H 127.0.0.1` pada service Anda!

### Aturan 2: Gunakan Pemisah `--` pada NPM / Yarn / PNPM
Jika menjalankan script npm (misalnya `npm run dev`), flag tambahan untuk Vite atau Next.js harus dipisahkan dengan tanda `--`:
```json
["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]
```
Tanpa `--`, npm akan mengira flag `--host` adalah opsi untuk npm itu sendiri, bukan untuk Vite.

### Aturan 3: Format Petik Ganda `"` atau Petik Tunggal `'`
Sistem Cloudflare Tunnel Manager telah dilengkapi **Smart JSON Parser**:
- Standar: `["artisan", "serve"]` (Direkomendasikan)
- Format Python: `['artisan', 'serve']` (Didukung secara otomatis)

---

## 3. Katalog Presets Lengkap (Frontend & Backend)

### A. Frontend Frameworks

#### 1. React / Vue / Svelte / Solid (Vite)
- **Executable**: `npm` (atau `pnpm` / `yarn` / `bun`)
- **Working directory**: Folder frontend (yang berisi `package.json`)
- **Arguments**:
```json
["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]
```
- **Local Port**: `5173`

#### 2. Next.js (App Router / Pages Router)
- **Executable**: `npm`
- **Working directory**: Folder project Next.js
- **Arguments**:
```json
["run", "dev", "--", "-H", "127.0.0.1", "-p", "3000"]
```
- **Local Port**: `3000`

#### 3. Nuxt 3 (Vue)
- **Executable**: `npm`
- **Working directory**: Folder project Nuxt
- **Arguments**:
```json
["run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"]
```
- **Local Port**: `3000`

#### 4. Angular CLI
- **Executable**: `npx` (atau `npm`)
- **Working directory**: Folder project Angular
- **Arguments**:
```json
["ng", "serve", "--host", "127.0.0.1", "--port", "4200"]
```
- **Local Port**: `4200`

#### 5. Astro
- **Executable**: `npm`
- **Working directory**: Folder project Astro
- **Arguments**:
```json
["run", "dev", "--", "--host", "127.0.0.1", "--port", "4321"]
```
- **Local Port**: `4321`

---

### B. Backend Frameworks

#### 1. PHP / Laravel
- **Executable**: `php`
- **Working directory**: Root folder Laravel (yang berisi file `artisan`)
- **Arguments**:
```json
["artisan", "serve", "--host=127.0.0.1", "--port=8000"]
```
- **Local Port**: `8000`

#### 2. Node.js (Express / Fastify / NestJS standalone)
- **Executable**: `node`
- **Working directory**: Folder backend
- **Arguments**:
```json
["dist/main.js"]
```
*(atau untuk dev mode dengan npm)*:
- **Executable**: `npm`
- **Arguments**:
```json
["run", "start:dev"]
```
- **Local Port**: `3000` (atau sesuai konfigurasi app Anda)

#### 3. Python (FastAPI / Starlette via Uvicorn)
- **Executable**: `python` (atau path relatif virtualenv: `.venv\Scripts\python.exe`)
- **Working directory**: Folder root project Python
- **Arguments**:
```json
["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
```
- **Local Port**: `8000`

#### 4. Python (Django)
- **Executable**: `python` (atau `.venv\Scripts\python.exe`)
- **Working directory**: Folder yang berisi `manage.py`
- **Arguments**:
```json
["manage.py", "runserver", "127.0.0.1:8000"]
```
- **Local Port**: `8000`

#### 5. Python (Flask)
- **Executable**: `python` (atau `.venv\Scripts\python.exe`)
- **Working directory**: Folder root Flask
- **Arguments**:
```json
["-m", "flask", "run", "--host=127.0.0.1", "--port=5000"]
```
- **Local Port**: `5000`

#### 6. Golang (Go)
- **Dev Mode**:
  - **Executable**: `go`
  - **Arguments**:
  ```json
  ["run", "main.go"]
  ```
- **Compiled Binary**:
  - **Executable**: `main.exe` (atau `./bin/server.exe`)
  - **Arguments**: `[]`
- **Local Port**: `8080`

#### 7. .NET Core / C#
- **Executable**: `dotnet`
- **Working directory**: Folder project `.csproj`
- **Arguments**:
```json
["run", "--urls", "http://127.0.0.1:5000"]
```
- **Local Port**: `5000`

#### 8. Java (Spring Boot)
- **Menggunakan JAR**:
  - **Executable**: `java`
  - **Arguments**:
  ```json
  ["-jar", "target/app.jar", "--server.address=127.0.0.1", "--server.port=8080"]
  ```
- **Menggunakan Maven Wrapper**:
  - **Executable**: `mvnw.cmd`
  - **Arguments**:
  ```json
  ["spring-boot:run"]
  ```
- **Local Port**: `8080`

#### 9. Rust (Actix-web / Axum / Rocket)
- **Executable**: `cargo`
- **Working directory**: Folder project (yang berisi `Cargo.toml`)
- **Arguments**:
```json
["run"]
```
- **Local Port**: `8080` (sesuai konfigurasi source code)

---

## 4. Fitur Kemudahan di GUI (Quick Presets)

Anda tidak perlu menghafal semua konfigurasi di atas! Di dialog **Add Service** / **Edit Service**:
1. Terdapat dropdown **Quick Preset**.
2. Pilih framework Anda (misal: *Laravel*, *React / Vite*, *Next.js*, *FastAPI*).
3. Field **Executable**, **Arguments**, dan **Local Port** akan otomatis terisi dengan konfigurasi best practice di atas.
4. Anda cukup memilih **Working directory** project Anda dan klik **Save Service**.
