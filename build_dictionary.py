import os
import sys
import io
import gzip
import struct
import sqlite3
import json
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "raw_data")
DB_PATH = os.path.join(BASE_DIR, "openrussian_vi.db")

os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

URLS = {
    'nouns': 'https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/nouns.csv',
    'verbs': 'https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/verbs.csv',
    'adjectives': 'https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/adjectives.csv',
    'others': 'https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/others.csv',
    'stardict_ru_vi': 'https://github.com/catusf/tudien/releases/download/v4.4/star_ngaviet.stardict.zip'
}

def download_file(url, target_path):
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        print(f"[Skip] File already exists: {os.path.basename(target_path)}")
        return
    print(f"[Downloading] {url} -> {os.path.basename(target_path)} ...")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp, open(target_path, 'wb') as f:
        f.write(resp.read())
    print(f"[Done] {os.path.basename(target_path)} ({os.path.getsize(target_path):,} bytes)")

def parse_stardict(zip_path):
    print("[Parsing] Loading Vietnamese translations from StarDict...")
    ru_vi_dict = {}
    with zipfile.ZipFile(zip_path) as z:
        idx_data = z.read('star_ngaviet.idx')
        dict_data = gzip.decompress(z.read('star_ngaviet.dict.dz'))
        
        pos = 0
        total_idx = len(idx_data)
        while pos < total_idx:
            null_pos = idx_data.find(b'\x00', pos)
            if null_pos == -1:
                break
            word = idx_data[pos:null_pos].decode('utf-8', errors='ignore')
            offset, size = struct.unpack('>II', idx_data[null_pos+1:null_pos+9])
            definition = dict_data[offset:offset+size].decode('utf-8', errors='ignore').strip()
            
            # Key normalized: lower-case without stress marks
            clean_key = word.lower().replace("'", "").replace("́", "").strip()
            if clean_key:
                if clean_key not in ru_vi_dict:
                    ru_vi_dict[clean_key] = definition
            pos = null_pos + 9
            
    print(f"[Loaded] {len(ru_vi_dict):,} Vietnamese definitions.")
    return ru_vi_dict

def setup_database(db_conn):
    cursor = db_conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bare TEXT NOT NULL,
            accented TEXT,
            pos TEXT NOT NULL,
            translations_vi TEXT,
            translations_en TEXT,
            translations_de TEXT,
            grammar_json TEXT
        );

        CREATE TABLE IF NOT EXISTS word_forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER NOT NULL,
            form TEXT NOT NULL,
            form_type TEXT,
            FOREIGN KEY (word_id) REFERENCES words (id)
        );

        CREATE INDEX IF NOT EXISTS idx_words_bare ON words(bare);
        CREATE INDEX IF NOT EXISTS idx_word_forms_form ON word_forms(form);
        CREATE INDEX IF NOT EXISTS idx_words_pos ON words(pos);
    ''')
    db_conn.commit()

def process_and_merge():
    # 1. Download all sources
    for name, url in URLS.items():
        ext = ".zip" if url.endswith(".zip") else ".csv"
        target_path = os.path.join(DATA_DIR, f"{name}{ext}")
        download_file(url, target_path)

    # 2. Parse Vietnamese StarDict
    stardict_path = os.path.join(DATA_DIR, "stardict_ru_vi.zip")
    vi_dict = parse_stardict(stardict_path)

    # 3. Create SQLite Database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    setup_database(conn)
    cursor = conn.cursor()

    total_words = 0
    total_forms = 0
    matched_vi = 0

    # 4. Import OpenRussian files
    pos_mapping = [
        ('nouns', 'noun'),
        ('verbs', 'verb'),
        ('adjectives', 'adjective'),
        ('others', 'other')
    ]

    for filename, pos_type in pos_mapping:
        file_path = os.path.join(DATA_DIR, f"{filename}.csv")
        print(f"[Processing] {filename}.csv ({pos_type})...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            header_line = f.readline().rstrip('\r\n')
            headers = header_line.split('\t')
            
            words_batch = []
            forms_batch = []
            
            for line in f:
                parts = line.rstrip('\r\n').split('\t')
                if len(parts) < len(headers):
                    parts += [''] * (len(headers) - len(parts))
                
                row = dict(zip(headers, parts))
                bare = row.get('bare', '').strip()
                if not bare:
                    continue
                
                accented = row.get('accented', '').strip()
                trans_en = row.get('translations_en', '').strip()
                trans_de = row.get('translations_de', '').strip()
                
                # Look up Vietnamese translation
                clean_bare = bare.lower().strip()
                trans_vi = vi_dict.get(clean_bare, '')
                if trans_vi:
                    matched_vi += 1
                
                # Separate grammar fields
                grammar_data = {k: v for k, v in row.items() if k not in ['bare', 'accented', 'translations_en', 'translations_de'] and v}
                grammar_json = json.dumps(grammar_data, ensure_ascii=False)
                
                total_words += 1
                word_id = total_words
                
                words_batch.append((word_id, bare, accented, pos_type, trans_vi, trans_en, trans_de, grammar_json))
                
                # Index forms (e.g. declensions, conjugations)
                # This allows searching any inflected form back to the dictionary lemma
                for k, v in grammar_data.items():
                    if k in ['gender', 'partner', 'aspect', 'animate', 'indeclinable', 'sg_only', 'pl_only']:
                        continue
                    # Multiple forms can be separated by commas or slashes
                    raw_forms = v.replace('/', ',').split(',')
                    for rf in raw_forms:
                        clean_f = rf.strip().replace("'", "").replace("́", "").lower()
                        if clean_f and clean_f != clean_bare:
                            forms_batch.append((word_id, clean_f, k))
                            total_forms += 1
                
                if len(words_batch) >= 5000:
                    cursor.executemany(
                        "INSERT INTO words (id, bare, accented, pos, translations_vi, translations_en, translations_de, grammar_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        words_batch
                    )
                    cursor.executemany(
                        "INSERT INTO word_forms (word_id, form, form_type) VALUES (?, ?, ?)",
                        forms_batch
                    )
                    conn.commit()
                    words_batch = []
                    forms_batch = []

            if words_batch:
                cursor.executemany(
                    "INSERT INTO words (id, bare, accented, pos, translations_vi, translations_en, translations_de, grammar_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    words_batch
                )
                cursor.executemany(
                    "INSERT INTO word_forms (word_id, form, form_type) VALUES (?, ?, ?)",
                    forms_batch
                )
                conn.commit()

    conn.close()
    print("\n" + "="*50)
    print(f"DATABASE BUILT SUCCESSFULLY: {DB_PATH}")
    print(f"Total Dictionary Words: {total_words:,}")
    print(f"Total Inflected Forms Indexed: {total_forms:,}")
    print(f"Direct Vietnamese Matches: {matched_vi:,} / {total_words:,} ({matched_vi*100/total_words:.1f}%)")
    print("="*50)

if __name__ == "__main__":
    process_and_merge()
