# 🚀 PostureFit Education Scraper (Lightweight)

Sistem pengumpulan konten edukasi otomatis berbasis AI untuk fitur Edukasi di aplikasi **PostureFit**. Menggunakan metode *lightweight scraping* yang dioptimalkan untuk efisiensi tinggi pada GitHub Actions tanpa perlu browser automation berat.

## ✨ Fitur Utama

- **Multi-Source Scraping**: Mengambil data dari 4 jalur berbeda (API, RSS, Web Scraping, Instagram).
- **AI-Powered Summarization**: Menggunakan **Gemini 2.0 Flash** untuk merangkas konten secara otomatis, ekstraksi tips praktis, dan pembersihan judul.
- **Lightweight Engine**: Menggunakan `cloudscraper` & `instaloader` (Tanpa Playwright/Selenium) sehingga sangat ringan untuk GitHub Actions.
- **Deduplication System**: Algoritma Jaccard Similarity untuk memastikan tidak ada konten duplikat meskipun berasal dari sumber berbeda.
- **Automatic Export**: Menyimpan hasil ke **MongoDB Atlas** dan mengekspor ke **`data_edukasi.json`** secara otomatis.
- **Scheduled Workflow**: Berjalan otomatis setiap hari pukul **00:00 WIB** via GitHub Actions.

## 📊 Sumber Data

| Kategori | Sumber | Metode |
| :--- | :--- | :--- |
| **Berita** | NewsData.io, GNews API | REST API |
| **RSS Feed** | Healthline, BBC Sport, Verywell Fit | XML/RSS Parser |
| **Website** | HelloSehat, Alodokter, Medical News Today, ESPN | CloudScraper + BS4 |
| **Sosial Media** | Ade Rai, dr. Tirta, dr. Gia Pratama, dll | Instaloader |

## 🛠️ Tech Stack

- **Language**: Python 3.11
- **AI Engine**: Google Gemini AI (`google-genai`)
- **Database**: MongoDB Atlas
- **Libraries**: `requests`, `cloudscraper`, `beautifulsoup4`, `feedparser`, `instaloader`
- **Automation**: GitHub Actions

## 🔑 GitHub Secrets yang Diperlukan

Agar scraper berjalan otomatis di GitHub, Anda wajib menambahkan secret berikut:

| Secret | Keterangan |
| :--- | :--- |
| `MONGO_URI` | Connection string MongoDB Atlas |
| `GEMINI_API_KEY` | API key Google Gemini (AI Studio) |
| `IG_SESSION_ID` | Session ID Instagram (Ambil dari browser cookies) |
| `NEWSDATA_API_KEY` | API Key dari newsdata.io (Opsional) |
| `GNEWS_API_KEY` | API Key dari gnews.io (Opsional) |

## 📁 Struktur Data (JSON)

```json
{
  "id": "12char_hash",
  "sumber": "Healthline",
  "judul": "Judul Bersih Hasil AI",
  "ringkasan": "Ringkasan 2-3 kalimat...",
  "tips": ["Tips 1", "Tips 2"],
  "kategori": "postur",
  "gambar": "https://url-gambar.com/img.jpg",
  "link_direct": "https://sumber-asli.com/artikel",
  "updated_at": "2026-05-11 21:00:00"
}
```

## ⚙️ Cara Menjalankan Lokal

1.  **Clone & Install**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Konfigurasi `.env`**: Buat file `.env` dan isi dengan API Key Anda.
3.  **Run**:
    ```bash
    python scraper_fit.py
    ```

---
*Developed for PostureFit App Ecosystem - Indonesia Atletis*
