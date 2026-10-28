# OpenRussian-Vi (Từ Điển Nga - Việt Ngữ Pháp)

Dự án từ điển tiếng Nga toàn diện dành cho người Việt, lấy **lõi ngữ pháp từ OpenRussian** kết hợp với **dữ liệu ngữ nghĩa Tiếng Việt chuẩn** từ bộ từ điển Nga - Việt của OVDP (Open Vietnamese Dictionary Project) và StarDict.

---

## 📊 Thống Kê Dataset Hiện Tại
* **Tổng số từ vựng (Lemmas):** `58,825` từ (Danh từ, Động từ, Tính từ, Trạng từ, Giới từ...).
* **Tổng số dạng biến cách được lập chỉ mục:** `705,665` dạng từ (cho phép gõ bất kỳ dạng chia cách nào cũng tự động quy về từ gốc!).
* **Từ vựng có sẵn định nghĩa Tiếng Việt chuẩn:** `32,017` từ (> 54.4%).
* **Các từ còn lại:** Có đầy đủ định nghĩa Tiếng Anh và Tiếng Đức, sẵn sàng cho việc dịch tự động.

---

## 🗂️ Cấu Trúc Dự Án

```text
openrussian-vi/
├── openrussian_vi.db          # Database SQLite hoàn chỉnh (Words, Word_Forms, Indexes)
├── build_dictionary.py       # Script tự động tải nguồn & merge dữ liệu
├── app.py                    # Server tra cứu demo & giao diện Web tra từ giống OpenRussian
├── raw_data/                 # Thư mục chứa dữ liệu thô (.csv và .zip)
│   ├── nouns.csv             # OpenRussian dataset: Danh từ + 6 cách số ít/nhiều
│   ├── verbs.csv             # OpenRussian dataset: Động từ + thì + ngôi + thể
│   ├── adjectives.csv        # OpenRussian dataset: Tính từ + biến cách + so sánh
│   ├── others.csv            # OpenRussian dataset: Trạng từ, liên từ, giới từ
│   └── stardict_ru_vi.zip    # Từ điển Nga - Việt StarDict v1.0 (~38k từ)
└── README.md
```

---

## 🚀 Cách Chạy Thử Giao Diện Web

Dự án sử dụng Python thuần và thư viện chuẩn (không cần cài thêm bất kỳ gói pip phức tạp nào):

```bash
cd "C:\Users\ASUS\.gemini\antigravity\scratch\openrussian-vi"
python app.py
```

Sau đó mở trình duyệt truy cập: **`http://127.0.0.1:8080`**

### Các tính năng đã có trong giao diện:
1. **Live Search & Autocomplete:** Gõ tới đâu hiển thị gợi ý từ gốc và nghĩa tới đó.
2. **Hỗ trợ tra từ theo dạng biến cách (Inflected Forms):**
   * Ví dụ: Gõ `читаю` -> Tự động nhận diện là dạng ngôi 1 thì hiện tại của động từ gốc **`читать`**.
   * Gõ `людьми` -> Tự động nhận diện là dạng Cách 5 số nhiều của danh từ gốc **`человек`**.
   * Gõ `красивая` -> Tự động nhận diện là dạng giống cái của tính từ **`красивый`**.
3. **Bảng ngữ pháp chi tiết:**
   * **Danh từ:** Bảng biến cách đầy đủ 6 cách (И, Р, Д, В, Т, П) ở số ít và số nhiều.
   * **Động từ:** Thể (НСВ / СВ), Cặp thể (Partner), Bảng chia ngôi (я, ты, он, мы, вы, они) và quá khứ (он, она, оно, они), thể mệnh lệnh.
   * **Tính từ:** Dạng ngắn (краткая форма), so sánh hơn/nhất, bảng biến cách theo giống.
4. **Bàn phím ảo mini:** Gắn nhanh dấu trọng âm (`́`) và các ký tự đặc biệt như `ы`, `ё`, `й`, `ь`, `ъ`, `э`.

---

## 🔌 Tích Hợp Vào Dự Án Web Của Bạn (Next.js / Vue / Express / FastAPI)

File SQLite `openrussian_vi.db` có thể dùng trực tiếp trong bất kỳ framework backend nào:

### Ví dụ truy vấn SQL:
```sql
-- Tìm từ theo từ gốc:
SELECT * FROM words WHERE bare = 'человек';

-- Tìm từ gốc khi người dùng gõ dạng biến cách bất kỳ (ví dụ 'людьми'):
SELECT w.*, f.form_type 
FROM word_forms f
JOIN words w ON f.word_id = w.id
WHERE f.form = 'людьми';
```
