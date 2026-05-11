import os
import time
import random
import asyncio
import re
import hashlib
import json
import feedparser
import requests
import instaloader
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import cloudscraper
import pymongo
from pymongo import UpdateOne
from google import genai
from dotenv import load_dotenv

load_dotenv()

IG_SESSION_ID = os.environ.get("IG_SESSION_ID", "")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = "scraper_fit"
COLLECTION_NAME = "edukasi_olahraga"

# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NEWSDATA_API_KEY = os.environ.get("NEWSDATA_API_KEY")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY")
FREENEWS_API_KEY = os.environ.get("FREENEWS_API_KEY")

try:
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        gemini_client = None
except Exception:
    gemini_client = None

KATEGORI_KEYWORDS = [
    'fitness', 'posture', 'workout', 'stretching', 'exercise', 
    'mobility', 'healthy lifestyle', 'sports injury', 'back pain',
    'olahraga', 'kebugaran', 'kesehatan', 'nutrisi', 'diet', 'protein', 
    'otot', 'muscle', 'cardio', 'strength', 'stretching', 'recovery'
]

IG_AKUN_FITNESS = [
    'ade_rai',
    'dr.tirta',
    'dr.gia_pratama',
    'fitnessindonesia',
    'gofitid',
]


def buat_id(judul: str, sumber: str) -> str:
    return hashlib.md5(f"{sumber}_{judul}".lower().strip().encode()).hexdigest()[:12]


def is_konten_fitness(teks: str) -> bool:
    teks_lower = str(teks).lower()
    return any(kw in teks_lower for kw in KATEGORI_KEYWORDS)


def deteksi_kategori(teks: str) -> str:
    teks_lower = teks.lower()
    if any(k in teks_lower for k in ['postur', 'posture', 'punggung', 'tulang', 'spine']):
        return 'postur'
    if any(k in teks_lower for k in ['nutrisi', 'diet', 'kalori', 'protein', 'makan']):
        return 'nutrisi'
    if any(k in teks_lower for k in ['cardio', 'lari', 'running', 'hiit', 'berenang']):
        return 'kardio'
    if any(k in teks_lower for k in ['strength', 'squat', 'deadlift', 'bench', 'otot', 'muscle']):
        return 'kekuatan'
    if any(k in teks_lower for k in ['yoga', 'pilates', 'stretching', 'fleksibilitas']):
        return 'fleksibilitas'
    if any(k in teks_lower for k in ['tidur', 'sleep', 'recovery', 'istirahat']):
        return 'pemulihan'
    return 'umum'


def proses_batch_dengan_gemini(data_batch: list[dict]) -> list[dict]:
    if not gemini_client or not data_batch:
        return data_batch

    payload_llm = [
        {
            "id": item["id"],
            "sumber": item["sumber"],
            "caption": item["caption"][:2000],
        }
        for item in data_batch
    ]

    prompt = f"""Kamu adalah AI Data Extractor untuk konten edukasi olahraga dan kebugaran Indonesia. Proses setiap item dalam JSON Array berikut.

TUGAS PER FIELD:

1. "judul"
   - Temukan judul artikel/konten olahraga dari "caption".
   - Hapus semua: emoji, simbol markdown (* _ # >), kata sapaan/pembuka.
   - Hasil akhir: judul bersih dan informatif tentang topik olahraga/kebugaran.
   - Jika tidak ditemukan, kembalikan "Tips Olahraga".

2. "ringkasan"
   - Buat ringkasan 2-3 kalimat dari "caption" yang menjelaskan isi konten.
   - Fokus pada informasi berguna tentang olahraga, postur, nutrisi, atau kebugaran.
   - Jika tidak relevan dengan olahraga/kebugaran, kembalikan "".

3. "tips"
   - Ekstrak 3-5 tips praktis dari "caption" dalam bentuk array of strings.
   - Setiap tips maksimal 1 kalimat.
   - Jika tidak ada tips spesifik, kembalikan [].

4. "link_sumber"
   - Jika "sumber" mengandung "IG": ekstrak semua URL dari "caption" → array of strings.
   - Jika bukan IG: kembalikan [].

5. Jangan ubah nilai "id".
6. Output: HANYA JSON Array valid. Tanpa markdown code block, tanpa teks penjelasan.

Format output:
{{"id": "...", "judul": "...", "ringkasan": "...", "tips": [], "link_sumber": []}}

Data:
{json.dumps(payload_llm, ensure_ascii=False)}"""

    for attempt in range(3):
        try:
            res = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            hasil_llm: list[dict] = json.loads(res.text)
            llm_map = {str(item["id"]): item for item in hasil_llm}

            for item in data_batch:
                llm = llm_map.get(str(item["id"]), {})
                item["judul"] = llm.get("judul") or item["judul"]
                item["ringkasan"] = llm.get("ringkasan", "")
                item["tips"] = llm.get("tips", [])
                if "IG" in item["sumber"]:
                    item["link_sumber"] = list(dict.fromkeys(llm.get("link_sumber", [])))

            time.sleep(3)
            return data_batch

        except Exception as e:
            print(f"[LLM] Error attempt {attempt + 1}: {e}")
            time.sleep(15)

    print("[LLM] Semua retry gagal, mengembalikan data mentah.")
    return data_batch


def scrape_hellosehat(id_sudah_ada: set) -> list[dict]:
    print("[hellosehat] Mulai scraping...")
    base_url = "https://hellosehat.com/kebugaran"
    scraper = cloudscraper.create_scraper()
    hasil = []

    try:
        soup = BeautifulSoup(scraper.get(base_url, headers=HEADERS, timeout=15).text, 'html.parser')
        artikel_links = list({
            urljoin("https://hellosehat.com", a.get('href', '')): a
            for a in soup.find_all('a', href=True)
            if '/kebugaran/' in a.get('href', '') and len(a.get('href', '').split('/')) > 4
        }.items())

        for link, anchor in artikel_links[:12]:
            try:
                res = scraper.get(link, headers=HEADERS, timeout=15)
                if res.status_code != 200:
                    continue

                dsoup = BeautifulSoup(res.text, 'html.parser')
                full_text = dsoup.get_text(separator=' ')

                if not is_konten_fitness(full_text):
                    continue

                judul_el = dsoup.find('h1')
                judul_kasar = judul_el.text.strip() if judul_el else link.split('/')[-2].replace('-', ' ').title()
                uid = buat_id(judul_kasar, "hellosehat.com")
                if uid in id_sudah_ada:
                    continue

                artikel_el = dsoup.find('article') or dsoup.find('div', class_=re.compile(r'content|article|post'))
                caption = artikel_el.get_text(separator=' ')[:3000] if artikel_el else full_text[:3000]

                gambar_el = dsoup.find('meta', property='og:image')
                gambar = gambar_el['content'] if gambar_el else ''

                hasil.append({
                    "id": uid,
                    "sumber": "hellosehat.com",
                    "judul": judul_kasar,
                    "ringkasan": "",
                    "tips": [],
                    "kategori": deteksi_kategori(caption),
                    "gambar": gambar,
                    "caption": caption,
                    "link_sumber": [link],
                    "link_direct": link,
                })
                id_sudah_ada.add(uid)

            except Exception:
                pass

    except Exception as e:
        print(f"[hellosehat] Error: {e}")

    print(f"[hellosehat] Selesai: {len(hasil)} data")
    return hasil


def scrape_alodokter(id_sudah_ada: set) -> list[dict]:
    print("[alodokter] Mulai scraping...")
    base_url = "https://www.alodokter.com/hidup-sehat/olahraga"
    scraper = cloudscraper.create_scraper()
    hasil = []

    try:
        soup = BeautifulSoup(scraper.get(base_url, headers=HEADERS, timeout=15).text, 'html.parser')
        links_artikel = list({
            urljoin("https://www.alodokter.com", a.get('href', '')): a
            for a in soup.find_all('a', href=True)
            if '/hidup-sehat/olahraga/' in a.get('href', '')
        }.items())

        for link, anchor in links_artikel[:12]:
            try:
                res = scraper.get(link, headers=HEADERS, timeout=15)
                if res.status_code != 200:
                    continue

                dsoup = BeautifulSoup(res.text, 'html.parser')
                full_text = dsoup.get_text(separator=' ')

                if not is_konten_fitness(full_text):
                    continue

                judul_el = dsoup.find('h1')
                judul_kasar = judul_el.text.strip() if judul_el else link.split('/')[-1].replace('-', ' ').title()
                uid = buat_id(judul_kasar, "alodokter.com")
                if uid in id_sudah_ada:
                    continue

                konten_el = dsoup.find('div', class_=re.compile(r'post-content|entry-content|article'))
                caption = konten_el.get_text(separator=' ')[:3000] if konten_el else full_text[:3000]

                gambar_el = dsoup.find('meta', property='og:image')
                gambar = gambar_el['content'] if gambar_el else ''

                hasil.append({
                    "id": uid,
                    "sumber": "alodokter.com",
                    "judul": judul_kasar,
                    "ringkasan": "",
                    "tips": [],
                    "kategori": deteksi_kategori(caption),
                    "gambar": gambar,
                    "caption": caption,
                    "link_sumber": [link],
                    "link_direct": link,
                })
                id_sudah_ada.add(uid)

            except Exception:
                pass

    except Exception as e:
        print(f"[alodokter] Error: {e}")

    print(f"[alodokter] Selesai: {len(hasil)} data")
    return hasil


def fetch_news_api(id_sudah_ada: set) -> list[dict]:
    print("[NewsAPI] Fetching from various News APIs...")
    hasil = []
    keywords = "fitness OR posture OR workout OR stretching OR exercise"
    
    # 1. NewsData.io
    if NEWSDATA_API_KEY:
        try:
            url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&q={keywords}&language=en,id"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for art in data.get('results', []):
                    uid = buat_id(art['title'], "newsdata.io")
                    if uid not in id_sudah_ada:
                        hasil.append({
                            "id": uid, "sumber": "newsdata.io", "judul": art['title'],
                            "ringkasan": "", "tips": [], "kategori": deteksi_kategori(art.get('description', '')),
                            "gambar": art.get('image_url', ''), "caption": art.get('description', art['title']),
                            "link_direct": art['link'], "link_sumber": [art['link']]
                        })
                        id_sudah_ada.add(uid)
        except Exception as e: print(f"[NewsData] Error: {e}")

    # 2. GNews API
    if GNEWS_API_KEY:
        try:
            url = f"https://gnews.io/api/v4/search?q={keywords}&lang=en&token={GNEWS_API_KEY}"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for art in data.get('articles', []):
                    uid = buat_id(art['title'], "gnews.io")
                    if uid not in id_sudah_ada:
                        hasil.append({
                            "id": uid, "sumber": "gnews.io", "judul": art['title'],
                            "ringkasan": "", "tips": [], "kategori": deteksi_kategori(art.get('description', '')),
                            "gambar": art.get('image', ''), "caption": art.get('description', art['content']),
                            "link_direct": art['url'], "link_sumber": [art['url']]
                        })
                        id_sudah_ada.add(uid)
        except Exception as e: print(f"[GNews] Error: {e}")

    return hasil

def fetch_rss_feeds(id_sudah_ada: set) -> list[dict]:
    print("[RSS] Fetching from feeds...")
    feeds = {
        "Healthline": "https://www.healthline.com/rss/fitness",
        "BBC Sport": "https://push.api.bbci.co.uk/pushed/rss/public/services/news/sports/rss.xml",
        "Verywell Fit": "https://www.verywellfit.com/rss"
    }
    hasil = []
    for name, url in feeds.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                if not is_konten_fitness(entry.title + " " + entry.get('summary', '')):
                    continue
                uid = buat_id(entry.title, name)
                if uid not in id_sudah_ada:
                    hasil.append({
                        "id": uid, "sumber": name, "judul": entry.title,
                        "ringkasan": "", "tips": [], "kategori": deteksi_kategori(entry.get('summary', '')),
                        "gambar": "", "caption": entry.get('summary', entry.title),
                        "link_direct": entry.link, "link_sumber": [entry.link]
                    })
                    id_sudah_ada.add(uid)
        except Exception as e: print(f"[RSS {name}] Error: {e}")
    return hasil

def scrape_generic(url: str, source_name: str, id_sudah_ada: set, selector="article") -> list[dict]:
    print(f"[{source_name}] Scraping...")
    scraper = cloudscraper.create_scraper()
    hasil = []
    try:
        res = scraper.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if len(href) > 20 and any(kw in href.lower() for kw in ['fit', 'health', 'sport', 'exercise']):
                full_url = urljoin(url, href)
                if full_url not in [l[0] for l in links]:
                    links.append((full_url, a.get_text(strip=True)))
        
        for link, title_text in links[:8]:
            try:
                if buat_id(title_text or link, source_name) in id_sudah_ada: continue
                art_res = scraper.get(link, headers=HEADERS, timeout=10)
                art_soup = BeautifulSoup(art_res.text, 'html.parser')
                content = art_soup.find(selector) or art_soup.find('main') or art_soup.find('body')
                text = content.get_text(separator=' ', strip=True) if content else ""
                if not is_konten_fitness(text): continue
                
                judul = art_soup.find('h1').text.strip() if art_soup.find('h1') else title_text
                uid = buat_id(judul, source_name)
                if uid in id_sudah_ada: continue
                
                img = art_soup.find('meta', property='og:image')
                img_url = img['content'] if img else ""
                
                hasil.append({
                    "id": uid, "sumber": source_name, "judul": judul,
                    "ringkasan": "", "tips": [], "kategori": deteksi_kategori(text),
                    "gambar": img_url, "caption": text[:3000],
                    "link_direct": link, "link_sumber": [link]
                })
                id_sudah_ada.add(uid)
            except: continue
    except Exception as e: print(f"[{source_name}] Error: {e}")
    return hasil


def scrape_instagram_instaloader(id_sudah_ada: set) -> list[dict]:
    print("[IG] Scraping with Instaloader...")
    L = instaloader.Instaloader(user_agent=HEADERS['User-Agent'])
    
    if IG_SESSION_ID:
        try:
            # Simple hack to use session ID without a file
            L.context._session.cookies.set("sessionid", IG_SESSION_ID, domain=".instagram.com")
            print("[IG] Session ID applied.")
        except Exception as e:
            print(f"[IG] Failed to apply session: {e}")

    hasil = []
    for akun in IG_AKUN_FITNESS:
        try:
            print(f"[IG] Fetching @{akun}...")
            profile = instaloader.Profile.from_username(L.context, akun)
            posts = profile.get_posts()
            
            count = 0
            for post in posts:
                if count >= 5: break
                
                caption = post.caption or ""
                if not is_konten_fitness(caption):
                    continue
                
                judul_kasar = caption.split('\n')[0][:100].strip() or f"Post by {akun}"
                uid = buat_id(judul_kasar, f"IG @{akun}")
                
                if uid not in id_sudah_ada:
                    hasil.append({
                        "id": uid,
                        "sumber": f"IG @{akun}",
                        "judul": judul_kasar,
                        "ringkasan": "",
                        "tips": [],
                        "kategori": deteksi_kategori(caption),
                        "gambar": post.url,
                        "caption": caption,
                        "link_sumber": [],
                        "link_direct": f"https://www.instagram.com/p/{post.shortcode}/"
                    })
                    id_sudah_ada.add(uid)
                    count += 1
                
                time.sleep(random.randint(2, 5))
        except Exception as e:
            print(f"[IG] Error @{akun}: {e}")
            
    print(f"[IG] Selesai: {len(hasil)} data")
    return hasil


def normalisasi_judul(judul: str) -> set:
    stopwords = {
        'the', 'of', 'and', 'in', 'on', 'at', 'to', 'a', 'an',
        'di', 'ke', 'se', 'dan', 'atau', 'untuk', 'dengan', 'dalam',
        'dari', 'oleh', 'yang', 'adalah', 'ini', 'itu', 'cara', 'tips',
        'manfaat', 'panduan', 'how', 'why', 'what', 'best',
    }
    judul_bersih = re.sub(r'[^\w\s]', ' ', judul.lower())
    return {t for t in judul_bersih.split() if t not in stopwords and len(t) > 1}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


PRIORITAS_SUMBER = {
    "Healthline": 0,
    "Verywell Fit": 1,
    "Medical News Today": 2,
    "hellosehat.com": 3,
    "alodokter.com": 4,
    "BBC Sport": 5,
    "ESPN": 6,
    "newsdata.io": 7,
    "gnews.io": 8,
}


def prioritas(item: dict) -> int:
    return PRIORITAS_SUMBER.get(item["sumber"], 3)


def dedup_hasil(hasil_baru: list, data_di_db: list, threshold: float = 0.6) -> list:
    link_direct_db: set = {d["link_direct"] for d in data_di_db if d.get("link_direct")}
    token_judul_db: list = [normalisasi_judul(d["judul"]) for d in data_di_db if d.get("judul")]

    unik: list = []

    for item in hasil_baru:
        judul_item = item.get("judul", "")
        link_item = item.get("link_direct", "")
        token_item = normalisasi_judul(judul_item)

        if link_item and link_item in link_direct_db:
            print(f"[DEDUP-DB] Skip (URL sama): {link_item}")
            continue

        if any(jaccard(token_item, t) >= threshold for t in token_judul_db):
            print(f"[DEDUP-DB] Skip (judul mirip di DB): {judul_item!r}")
            continue

        duplikat_idx = None
        for idx, existing in enumerate(unik):
            skor = jaccard(token_item, normalisasi_judul(existing.get("judul", "")))
            if skor >= threshold:
                duplikat_idx = idx
                break

        if duplikat_idx is not None:
            existing = unik[duplikat_idx]
            gabungan_link = list(dict.fromkeys(
                existing["link_sumber"] + item["link_sumber"]
            ))
            if prioritas(item) < prioritas(existing):
                item["link_sumber"] = gabungan_link
                unik[duplikat_idx] = item
                print(f"[DEDUP-NEW] Ganti {existing['sumber']} → {item['sumber']}: {judul_item!r}")
            else:
                unik[duplikat_idx]["link_sumber"] = gabungan_link
                print(f"[DEDUP-NEW] Gabung link {item['sumber']} → {existing['sumber']}: {judul_item!r}")
        else:
            unik.append(item)

    print(f"[DEDUP] {len(hasil_baru)} item masuk → {len(unik)} item unik.")
    return unik


async def main():
    print("[INFO] Menghubungkan ke MongoDB...")
    client = None
    id_sudah_ada = set()
    data_di_db = []
    
    if MONGO_URI:
        try:
            client = pymongo.MongoClient(MONGO_URI)
            collection = client[DB_NAME][COLLECTION_NAME]
            data_di_db = list(collection.find({}, {"id": 1, "link_direct": 1, "judul": 1, "_id": 0}))
            id_sudah_ada = {d["id"] for d in data_di_db if "id" in d}
            print(f"[INFO] {len(id_sudah_ada)} data dari MongoDB.")
        except Exception as e:
            print(f"[ERROR] MongoDB: {e}")

    # Gather data from all sources
    print("[INFO] Scraping from all sources...")
    
    # 1. APIs & RSS (Fast)
    results_fast = [
        fetch_news_api(id_sudah_ada),
        fetch_rss_feeds(id_sudah_ada),
    ]
    
    # 2. Websites (Lighter CloudScraper)
    results_web = [
        scrape_hellosehat(id_sudah_ada),
        scrape_alodokter(id_sudah_ada),
        scrape_generic("https://www.healthline.com/kesehatan", "Healthline", id_sudah_ada),
        scrape_generic("https://www.verywellfit.com", "Verywell Fit", id_sudah_ada),
        scrape_generic("https://www.medicalnewstoday.com", "Medical News Today", id_sudah_ada),
        scrape_generic("https://www.espn.com/fitness", "ESPN", id_sudah_ada),
        scrape_generic("https://www.bbc.com/sport", "BBC Sport", id_sudah_ada),
    ]
    
    # 3. Instagram (Lighter Instaloader)
    results_ig = [
        scrape_instagram_instaloader(id_sudah_ada)
    ]

    hasil_mentah = []
    for batch in results_fast + results_web + results_ig:
        if isinstance(batch, list):
            hasil_mentah.extend(batch)
    
    print(f"[INFO] Total {len(hasil_mentah)} data mentah baru.")

    if not hasil_mentah:
        print("[INFO] Tidak ada data baru.")
        if client: client.close()
        return

    # Process with AI
    BATCH_SIZE = 10
    hasil_llm = []
    for i in range(0, len(hasil_mentah), BATCH_SIZE):
        batch = hasil_mentah[i:i + BATCH_SIZE]
        print(f"[LLM] Batch {i // BATCH_SIZE + 1}...")
        hasil_llm.extend(proses_batch_dengan_gemini(batch))

    hasil_final = dedup_hasil(hasil_llm, data_di_db, threshold=0.6)

    if not hasil_final:
        print("[INFO] Tidak ada data unik untuk disimpan.")
        if client: client.close()
        return

    # Clean up for storage
    for item in hasil_final:
        item.pop("caption", None)
        item["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Save to JSON (requested as one of the options)
    try:
        with open("data_edukasi.json", "w", encoding="utf-8") as f:
            json.dump(hasil_final, f, ensure_ascii=False, indent=2)
        print("[INFO] Data disimpan ke data_edukasi.json")
    except Exception as e:
        print(f"[ERROR] Save JSON: {e}")

    # Save to MongoDB if available
    if client:
        try:
            collection = client[DB_NAME][COLLECTION_NAME]
            result = collection.bulk_write([
                UpdateOne({'id': item['id']}, {'$set': item}, upsert=True)
                for item in hasil_final
            ])
            print(f"[INFO] MongoDB: {result.upserted_count} baru, {result.modified_count} update.")
            client.close()
        except Exception as e:
            print(f"[ERROR] MongoDB Bulk Write: {e}")


if __name__ == "__main__":
    asyncio.run(main())
