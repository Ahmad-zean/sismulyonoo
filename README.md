# Ruang Tenang

Ruang Tenang adalah aplikasi web berbahasa Indonesia untuk bercerita kepada AI, mengelola akun dan riwayat percakapan, serta mendengarkan audio relaksasi.

## Fitur

- Chat dengan AI melalui Groq.
- Registrasi, login, pengaturan profil, dan penggantian password.
- Riwayat percakapan yang dapat dibuka, diubah namanya, dan dihapus.
- Halaman bantuan darurat.
- Pemutar Relaxing Sound dengan kontrol putar/jeda, posisi audio, dan volume.
- Pustaka audio yang otomatis membaca file dari folder [static/audio/](static/audio/).

## Persyaratan

- Python 3.10 atau lebih baru.
- pip.
- API key Groq untuk mengaktifkan jawaban AI.

## Menjalankan secara lokal

1. Clone repository dan masuk ke direktori proyek.
2. Buat dan aktifkan virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   Di macOS atau Linux, aktifkan dengan:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Pasang dependensi:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Buat file `.env` di direktori proyek. Contoh konfigurasi pengembangan:

   ```dotenv
   APP_ENV=development
   DATABASE_URL=sqlite:///./blog.db
   SITE_URL=http://localhost:8000
   JWT_SECRET_KEY=ganti-dengan-kunci-rahasia-minimal-32-karakter
   GROQ_API_KEY=
   # GROQ_MODEL=nama-model-groq
   ```

   `GROQ_API_KEY` diperlukan agar AI dapat menjawab chat. Tanpa key yang valid, aplikasi tetap dapat dijalankan tetapi fitur AI tidak tersedia. `GROQ_MODEL` opsional; jika tidak diisi, aplikasi akan memilih model yang tersedia.

5. Jalankan server:

   ```bash
   uvicorn main:app --reload
   ```

6. Buka [http://localhost:8000](http://localhost:8000). Dokumentasi API FastAPI tersedia di [http://localhost:8000/docs](http://localhost:8000/docs).

File `.env` tidak boleh dimasukkan ke Git. Jangan membagikan API key atau kunci rahasia.

## Menggunakan Relaxing Sound

Buka [http://localhost:8000/relaxing-sound](http://localhost:8000/relaxing-sound), lalu tambahkan audio berformat MP3, M4A, OGG, atau WAV ke [static/audio/](static/audio/). Muat ulang halaman agar audio yang baru ditambahkan muncul di daftar.

Endpoint `GET /api/relaxing-sounds` mengembalikan daftar file audio yang tersedia. Aplikasi belum menyediakan form upload melalui halaman web.

## Route utama

| Method | Path | Keterangan |
| --- | --- | --- |
| `GET` | `/` | Halaman chat Ruang Tenang |
| `POST` | `/chat` | Mengirim pesan ke AI |
| `GET` | `/relaxing-sound` | Halaman pemutar audio |
| `GET` | `/api/relaxing-sounds` | Daftar audio di `static/audio/` |
| `GET` | `/help` | Bantuan darurat |
| `GET` | `/api/conversations` | Daftar riwayat percakapan pengguna |
| `POST` | `/api/Users` | Registrasi |
| `POST` | `/api/Users/token` | Login |
| `GET` | `/api/Users/me` | Informasi akun saat ini |
| `POST` | `/api/Users/password/forgot` | Meminta tautan reset password |
| `POST` | `/api/Users/password/reset` | Mengatur ulang password |

Endpoint akun lainnya mencakup pembaruan profil, perubahan password, dan logout.

## Konfigurasi produksi

Produksi memerlukan `APP_ENV=production`, `JWT_SECRET_KEY` yang aman, PostgreSQL melalui `DATABASE_URL`, `SITE_URL` HTTPS, dan daftar host di `TRUSTED_HOSTS`. Email reset password memerlukan konfigurasi SMTP, termasuk `SMTP_HOST` dan `SMTP_FROM_EMAIL`; aktifkan TLS melalui `SMTP_STARTTLS` atau `SMTP_SSL`.

Jangan gunakan konfigurasi pengembangan atau nilai rahasia contoh di lingkungan produksi.
