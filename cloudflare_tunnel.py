
import re
import subprocess
from pathlib import Path


# Lokasi cloudflared.exe mengikuti lokasi file Python
BASE_DIR = Path(__file__).resolve().parent
CLOUDFLARED = BASE_DIR / "bin" / "cloudflared.exe"


def main():
    print("=" * 55)
    print("          CLOUDFLARE QUICK TUNNEL")
    print("=" * 55)

    # Periksa keberadaan cloudflared.exe
    if not CLOUDFLARED.is_file():
        print("\n[ERROR] cloudflared.exe tidak ditemukan!")
        print(f"Lokasi yang dicari: {CLOUDFLARED}")
        input("\nTekan Enter untuk keluar...")
        return

    # Input port lokal
    port = input("\nMasukkan port lokal [8000]: ").strip()

    if not port:
        port = "8000"

    if not port.isdigit() or not (1 <= int(port) <= 65535):
        print("[ERROR] Port tidak valid.")
        input("\nTekan Enter untuk keluar...")
        return

    local_url = f"http://localhost:{port}"

    print(f"\n[INFO] Local URL : {local_url}")
    print(f"[INFO] Cloudflared: {CLOUDFLARED}")
    print("\n[INFO] Memulai Cloudflare Tunnel...")
    print("[INFO] Menunggu URL publik...\n")

    command = [
        str(CLOUDFLARED),
        "tunnel",
        "--url",
        local_url
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )

        url_found = False

        # Baca dan tampilkan output Cloudflare
        for line in process.stdout:
            print(line, end="", flush=True)

            # Deteksi URL Quick Tunnel
            match = re.search(
                r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",
                line
            )

            if match and not url_found:
                public_url = match.group(0)
                url_found = True

                print("\n")
                print("=" * 55)
                print("          TUNNEL BERHASIL DIJALANKAN")
                print("=" * 55)
                print(f"\nLOCAL  : {local_url}")
                print(f"PUBLIC : {public_url}")
                print("\nGunakan URL PUBLIC untuk mengakses aplikasi.")
                print("Tekan CTRL+C untuk menghentikan tunnel.")
                print("=" * 55 + "\n")

        process.wait()

        if process.returncode != 0:
            print(
                f"\n[ERROR] Cloudflared berhenti "
                f"dengan kode: {process.returncode}"
            )

    except KeyboardInterrupt:
        print("\n\n[INFO] Menghentikan Cloudflare Tunnel...")

    except FileNotFoundError:
        print("\n[ERROR] Executable cloudflared tidak ditemukan.")

    except OSError as error:
        print(f"\n[ERROR] {error}")

    finally:
        if "process" in locals() and process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        print("[INFO] Tunnel dihentikan.")


if __name__ == "__main__":
    main()
