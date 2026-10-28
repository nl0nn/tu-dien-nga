import os
import sys
import json
import sqlite3
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "openrussian_vi.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search_words(query, limit=10):
    query = query.strip()
    if not query:
        return []
    
    clean_q = query.lower().replace("'", "").replace("́", "")
    conn = get_db()
    c = conn.cursor()
    
    # 1. Exact match lemma
    c.execute("""
        SELECT id, bare, accented, pos, translations_vi, translations_en, grammar_json, 'lemma' as match_type, NULL as form_type
        FROM words
        WHERE bare = ? COLLATE NOCASE
        LIMIT ?
    """, (clean_q, limit))
    results = [dict(row) for row in c.fetchall()]
    
    # 2. Inflected forms match
    if len(results) < limit:
        remaining = limit - len(results)
        found_ids = {r['id'] for r in results}
        c.execute("""
            SELECT w.id, w.bare, w.accented, w.pos, w.translations_vi, w.translations_en, w.grammar_json, 'form' as match_type, f.form_type
            FROM word_forms f
            JOIN words w ON f.word_id = w.id
            WHERE f.form = ?
            LIMIT ?
        """, (clean_q, remaining * 2))
        for row in c.fetchall():
            d = dict(row)
            if d['id'] not in found_ids:
                found_ids.add(d['id'])
                results.append(d)
                if len(results) >= limit:
                    break
    
    # 3. Prefix search lemma
    if len(results) < limit:
        remaining = limit - len(results)
        found_ids = {r['id'] for r in results}
        c.execute("""
            SELECT id, bare, accented, pos, translations_vi, translations_en, grammar_json, 'prefix' as match_type, NULL as form_type
            FROM words
            WHERE bare LIKE ? || '%'
            ORDER BY length(bare) ASC
            LIMIT ?
        """, (clean_q, remaining * 3))
        for row in c.fetchall():
            d = dict(row)
            if d['id'] not in found_ids:
                found_ids.add(d['id'])
                results.append(d)
                if len(results) >= limit:
                    break

    # Parse grammar_json into dict
    for r in results:
        try:
            r['grammar'] = json.loads(r['grammar_json'])
        except Exception:
            r['grammar'] = {}
        del r['grammar_json']

    conn.close()
    return results

def get_word_by_id(word_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, bare, accented, pos, translations_vi, translations_en, translations_de, grammar_json FROM words WHERE id = ?", (word_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d['grammar'] = json.loads(d['grammar_json'])
    except Exception:
        d['grammar'] = {}
    del d['grammar_json']
    return d

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenRussian Việt - Từ điển Nga Việt Ngữ Pháp</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --accent: #dc2626;
            --border: #e2e8f0;
            --tag-noun: #dbeafe;
            --tag-verb: #fef3c7;
            --tag-adj: #dcfce7;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text-main); line-height: 1.5; padding-bottom: 50px; }
        header { background: #1e293b; color: white; padding: 20px 0; border-bottom: 3px solid var(--primary); }
        .container { max-width: 900px; margin: 0 auto; padding: 0 20px; }
        .logo-area { display: flex; align-items: baseline; gap: 12px; margin-bottom: 15px; }
        .logo { font-size: 26px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
        .logo span { color: #38bdf8; }
        .badge { background: #334155; color: #94a3b8; font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
        
        .search-box { position: relative; margin: 20px 0; }
        .search-input-wrap { display: flex; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; background: white; }
        input[type="text"] { flex: 1; padding: 14px 18px; font-size: 18px; border: 2px solid transparent; outline: none; }
        input[type="text"]:focus { border-color: var(--primary); }
        button.search-btn { background: var(--primary); color: white; border: none; padding: 0 24px; font-size: 16px; font-weight: 600; cursor: pointer; transition: 0.2s; }
        button.search-btn:hover { background: var(--primary-dark); }
        
        .quick-chars { display: flex; gap: 6px; margin-top: 8px; align-items: center; }
        .quick-chars span { font-size: 13px; color: var(--text-muted); }
        .char-btn { background: white; border: 1px solid var(--border); padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .char-btn:hover { background: #f1f5f9; }

        .suggestions { background: white; border: 1px solid var(--border); border-radius: 8px; margin-top: 4px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); max-height: 350px; overflow-y: auto; display: none; }
        .suggestion-item { padding: 12px 16px; border-bottom: 1px solid #f1f5f9; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
        .suggestion-item:hover { background: #f8fafc; }
        .sugg-word { font-size: 17px; font-weight: 600; color: #1e293b; }
        .sugg-accented { color: var(--accent); font-weight: bold; }
        .sugg-en { color: var(--text-muted); font-size: 14px; max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

        .word-card { background: white; border: 1px solid var(--border); border-radius: 12px; padding: 25px; margin-top: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
        .word-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; }
        .word-title { font-size: 32px; font-weight: 700; color: #0f172a; }
        .word-pos { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; text-transform: uppercase; }
        .pos-noun { background: var(--tag-noun); color: #1e40af; }
        .pos-verb { background: var(--tag-verb); color: #92400e; }
        .pos-adjective { background: var(--tag-adj); color: #166534; }
        .pos-other { background: #f1f5f9; color: #475569; }

        .section-title { font-size: 16px; font-weight: 700; color: #334155; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
        .definition-box { background: #f0fdf4; border-left: 4px solid #22c55e; padding: 14px 18px; border-radius: 0 8px 8px 0; margin-bottom: 20px; }
        .definition-text { white-space: pre-wrap; font-size: 16px; color: #166534; line-height: 1.6; }
        
        .other-defs { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 25px; }
        .lang-box { background: #f8fafc; border: 1px solid var(--border); padding: 12px; border-radius: 6px; }
        .lang-label { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 4px; }

        .table-wrap { overflow-x: auto; margin-top: 15px; }
        table.grammar-table { width: 100%; border-collapse: collapse; font-size: 15px; }
        table.grammar-table th, table.grammar-table td { border: 1px solid var(--border); padding: 10px 14px; text-align: left; }
        table.grammar-table th { background: #f1f5f9; color: #475569; font-weight: 600; width: 22%; }
        table.grammar-table td { background: white; }
        .stress { color: #dc2626; font-weight: 600; }
        
        .inflected-notice { background: #fffbeb; border: 1px solid #fde68a; padding: 10px 14px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; color: #92400e; }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <div class="logo-area">
                <div class="logo">OpenRussian <span>Việt</span></div>
                <div class="badge">Lõi OpenRussian + Dữ liệu Tiếng Việt</div>
            </div>
            <p style="color: #cbd5e1; font-size: 14px;">58,800+ từ vựng • 705,000+ dạng biến cách • Bảng chia 6 cách & thì động từ chi tiết</p>
        </div>
    </header>

    <main class="container">
        <div class="search-box">
            <div class="search-input-wrap">
                <input type="text" id="searchInput" placeholder="Tra từ tiếng Nga (ví dụ: человек, читаю, красивый, дом)..." autocomplete="off">
                <button class="search-btn" onclick="doSearch()">Tìm kiếm</button>
            </div>
            <div class="quick-chars">
                <span>Ký tự nhanh:</span>
                <button class="char-btn" onclick="insertChar('́')">́ (dấu trọng âm)</button>
                <button class="char-btn" onclick="insertChar('ы')">ы</button>
                <button class="char-btn" onclick="insertChar('ё')">ё</button>
                <button class="char-btn" onclick="insertChar('й')">й</button>
                <button class="char-btn" onclick="insertChar('ь')">ь</button>
                <button class="char-btn" onclick="insertChar('ъ')">ъ</button>
                <button class="char-btn" onclick="insertChar('э')">э</button>
            </div>
            <div class="suggestions" id="suggestionsBox"></div>
        </div>

        <div id="resultsContainer"></div>
    </main>

    <script>
        const searchInput = document.getElementById('searchInput');
        const suggestionsBox = document.getElementById('suggestionsBox');
        const resultsContainer = document.getElementById('resultsContainer');
        let searchDebounce = null;

        function insertChar(ch) {
            const pos = searchInput.selectionStart;
            const val = searchInput.value;
            searchInput.value = val.slice(0, pos) + ch + val.slice(pos);
            searchInput.focus();
            searchInput.setSelectionRange(pos + 1, pos + 1);
        }

        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchDebounce);
            const q = e.target.value.trim();
            if (q.length < 1) {
                suggestionsBox.style.display = 'none';
                return;
            }
            searchDebounce = setTimeout(() => {
                fetch('/api/search?q=' + encodeURIComponent(q))
                    .then(r => r.json())
                    .then(data => renderSuggestions(data));
            }, 180);
        });

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                doSearch();
            }
        });

        function renderSuggestions(items) {
            if (!items || items.length === 0) {
                suggestionsBox.style.display = 'none';
                return;
            }
            suggestionsBox.innerHTML = items.map(item => `
                <div class="suggestion-item" onclick="loadWord(${item.id})">
                    <div>
                        <span class="sugg-word">${item.accented || item.bare}</span>
                        <span class="word-pos pos-${item.pos}" style="font-size:10px; margin-left:6px;">${item.pos}</span>
                        ${item.match_type === 'form' ? `<span style="font-size:11px; color:#d97706; margin-left:6px;">(dạng biến cách: ${item.form_type})</span>` : ''}
                    </div>
                    <div class="sugg-en">${item.translations_vi ? item.translations_vi.slice(0, 40) : item.translations_en}</div>
                </div>
            `).join('');
            suggestionsBox.style.display = 'block';
        }

        function doSearch() {
            suggestionsBox.style.display = 'none';
            const q = searchInput.value.trim();
            if (!q) return;
            fetch('/api/search?q=' + encodeURIComponent(q))
                .then(r => r.json())
                .then(items => {
                    if (items.length > 0) {
                        loadWord(items[0].id, items[0]);
                    } else {
                        resultsContainer.innerHTML = '<div class="word-card"><p>Không tìm thấy từ phù hợp với: <b>' + q + '</b></p></div>';
                    }
                });
        }

        function loadWord(id, extraInfo) {
            suggestionsBox.style.display = 'none';
            fetch('/api/word?id=' + id)
                .then(r => r.json())
                .then(w => renderWordCard(w, extraInfo));
        }

        function renderWordCard(w, extraInfo) {
            let grammarHtml = '';
            const g = w.grammar || {};

            if (w.pos === 'noun') {
                grammarHtml = `
                    <div class="section-title">Bảng biến cách 6 cách (Падежи)</div>
                    <div class="table-wrap">
                        <table class="grammar-table">
                            <thead>
                                <tr><th>Cách</th><th>Số ít (Ед. число)</th><th>Số nhiều (Мн. число)</th></tr>
                            </thead>
                            <tbody>
                                <tr><td><b>Cách 1 (Именительный)</b></td><td>${g.sg_nom || '-'}</td><td>${g.pl_nom || '-'}</td></tr>
                                <tr><td><b>Cách 2 (Родительный)</b></td><td>${g.sg_gen || '-'}</td><td>${g.pl_gen || '-'}</td></tr>
                                <tr><td><b>Cách 3 (Дательный)</b></td><td>${g.sg_dat || '-'}</td><td>${g.pl_dat || '-'}</td></tr>
                                <tr><td><b>Cách 4 (Винительный)</b></td><td>${g.sg_acc || '-'}</td><td>${g.pl_acc || '-'}</td></tr>
                                <tr><td><b>Cách 5 (Творительный)</b></td><td>${g.sg_inst || '-'}</td><td>${g.pl_inst || '-'}</td></tr>
                                <tr><td><b>Cách 6 (Предложный)</b></td><td>${g.sg_prep || '-'}</td><td>${g.pl_prep || '-'}</td></tr>
                            </tbody>
                        </table>
                    </div>
                `;
            } else if (w.pos === 'verb') {
                grammarHtml = `
                    <div class="section-title">Bảng chia động từ (Спряжение)</div>
                    <p style="margin-bottom: 10px; font-size: 14px; color: #475569;">
                        <b>Thể:</b> ${g.aspect === 'imperfective' ? 'Chưa hoàn thành (НСВ)' : 'Hoàn thành (СВ)'} 
                        ${g.partner ? `| <b>Cặp thể:</b> <span class="stress">${g.partner}</span>` : ''}
                    </p>
                    <div class="table-wrap">
                        <table class="grammar-table">
                            <thead>
                                <tr><th>Ngôi / Dạng</th><th>Hiện tại / Tương lai</th><th>Thời quá khứ</th></tr>
                            </thead>
                            <tbody>
                                <tr><td><b>Я (1-е лицо ед.)</b></td><td>${g.presfut_sg1 || '-'}</td><td><b>Он:</b> ${g.past_m || '-'}</td></tr>
                                <tr><td><b>Ты (2-е лицо ед.)</b></td><td>${g.presfut_sg2 || '-'}</td><td><b>Она:</b> ${g.past_f || '-'}</td></tr>
                                <tr><td><b>Он / Она / Оно</b></td><td>${g.presfut_sg3 || '-'}</td><td><b>Оно:</b> ${g.past_n || '-'}</td></tr>
                                <tr><td><b>Мы (1-е лицо мн.)</b></td><td>${g.presfut_pl1 || '-'}</td><td rowspan="3"><b>Они:</b> ${g.past_pl || '-'}</td></tr>
                                <tr><td><b>Вы (2-е лицо мн.)</b></td><td>${g.presfut_pl2 || '-'}</td></tr>
                                <tr><td><b>Они (3-е лицо мн.)</b></td><td>${g.presfut_pl3 || '-'}</td></tr>
                                <tr><td><b>Mệnh lệnh (Повелительное)</b></td><td colspan="2">Số ít: <b>${g.imperative_sg || '-'}</b> | Số nhiều: <b>${g.imperative_pl || '-'}</b></td></tr>
                            </tbody>
                        </table>
                    </div>
                `;
            } else if (w.pos === 'adjective') {
                grammarHtml = `
                    <div class="section-title">Bảng biến cách tính từ & Dạng ngắn</div>
                    <p style="margin-bottom: 10px; font-size: 14px; color: #475569;">
                        <b>So sánh hơn:</b> ${g.comparative || '-'} | <b>So sánh nhất:</b> ${g.superlative || '-'}
                    </p>
                    <div class="table-wrap">
                        <table class="grammar-table">
                            <thead>
                                <tr><th>Dạng ngắn</th><th>Nam (м)</th><th>Nữ (ж)</th><th>Trung (с)</th><th>Nhiều (мн)</th></tr>
                            </thead>
                            <tbody>
                                <tr><td>Краткая форма</td><td>${g.short_m || '-'}</td><td>${g.short_f || '-'}</td><td>${g.short_n || '-'}</td><td>${g.short_pl || '-'}</td></tr>
                            </tbody>
                        </table>
                    </div>
                `;
            }

            resultsContainer.innerHTML = `
                <div class="word-card">
                    ${extraInfo && extraInfo.match_type === 'form' ? `
                        <div class="inflected-notice">
                            ℹ️ Bạn đã tìm kiếm một dạng biến cách (<b>${extraInfo.form_type}</b>). Dưới đây là thông tin từ gốc tương ứng:
                        </div>
                    ` : ''}
                    <div class="word-header">
                        <div>
                            <div class="word-title">${w.accented || w.bare}</div>
                            <div style="color: var(--text-muted); font-size: 15px;">Dạng cơ bản: <b>${w.bare}</b></div>
                        </div>
                        <span class="word-pos pos-${w.pos}">${w.pos}</span>
                    </div>

                    <div class="section-title">Nghĩa Tiếng Việt</div>
                    <div class="definition-box">
                        <div class="definition-text">${w.translations_vi ? w.translations_vi : '<i>(Chưa có bản dịch Tiếng Việt chuẩn trong bộ StarDict, xem bản dịch tiếng Anh bên dưới)</i>'}</div>
                    </div>

                    <div class="other-defs">
                        <div class="lang-box">
                            <div class="lang-label">TIẾNG ANH (ENGLISH)</div>
                            <div>${w.translations_en || 'None'}</div>
                        </div>
                        <div class="lang-box">
                            <div class="lang-label">TIẾNG ĐỨC (DEUTSCH)</div>
                            <div>${w.translations_de || 'Keine'}</div>
                        </div>
                    </div>

                    ${grammarHtml}
                </div>
            `;
        }

        // Demo query
        loadWord(1);
    </script>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif path == "/api/search":
            q = params.get("q", [""])[0]
            results = search_words(q, limit=8)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(results, ensure_ascii=False).encode("utf-8"))
        elif path == "/api/word":
            word_id = int(params.get("id", [0])[0])
            word = get_word_by_id(word_id)
            if word:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(word, ensure_ascii=False).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8080):
    server = HTTPServer(('127.0.0.1', port), RequestHandler)
    print(f"OpenRussian Vi Server running at http://127.0.0.1:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)
