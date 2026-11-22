# Cập nhật tsvector bằng biểu thức hoặc trigger phù hợp trong PostgreSQL

Một ứng dụng tìm kiếm tài liệu thường có bảng chứa `title`, `body`, `tags` và các thuộc tính khác. Người dùng sửa tiêu đề hoặc nội dung, sau đó mong kết quả tìm kiếm phản ánh thay đổi ngay. Với PostgreSQL Full-Text Search (FTS), câu hỏi không chỉ là **tạo chỉ mục GIN như thế nào**, mà còn là:

> **Khi dữ liệu nguồn đổi, ai sẽ cập nhật nội dung `tsvector` mà hệ thống dùng để tìm kiếm?**

Ba chiến lược phổ biến:

1. **Chỉ mục biểu thức (expression index)**: PostgreSQL tính `to_tsvector(...)` từ các cột nguồn rồi lưu các mục tìm kiếm vào index; ứng dụng không cần tự duy trì cột `tsvector`.
2. **Cột phát sinh lưu trữ (stored generated column)**: khai báo `search_vector tsvector GENERATED ALWAYS AS (...) STORED`; PostgreSQL tự tính và lưu vector khi hàng được ghi, có thể đánh GIN trực tiếp trên cột này.
3. **Trigger**: tạo cột `tsvector` bình thường và trigger `BEFORE INSERT OR UPDATE` để gán vector trước khi lưu hàng. Có thể dùng trigger có sẵn `tsvector_update_trigger` hoặc tự viết trigger cho trọng số, cấu hình theo hàng và logic đặc thù.

Ba cách đều có thể tạo kết quả tìm kiếm tốt nếu định nghĩa và cập nhật nhất quán. Chúng **không giống nhau** về lưu trữ, chi phí vận hành, khả năng xếp hạng, độ phức tạp migration và rủi ro mất đồng bộ.

```text
                     title, body, tags
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
    Expression GIN     Stored generated    BEFORE trigger
     index key         tsvector column     tsvector column
           |                |                |
           |                v                v
           |          GIN(search_vector) GIN(search_vector)
           |                |                |
           +----------------+----------------+
                            |
                            v
             search vector @@ tsquery
                            |
                            v
                  Kết quả tìm kiếm
```

Bài thuộc chương **Tìm kiếm văn bản** của module *Database Engine Relational PostgreSQL*. Mục tiêu là giúp bạn tự triển khai và chọn đúng chiến lược **cập nhật `tsvector`**, không chỉ học một cú pháp trigger.

Sau khi hoàn thành, bạn sẽ hiểu:

- `to_tsvector`, `tsquery`, `@@`, từ vựng đã chuẩn hóa, stop words và vị trí từ.
- Vì sao phải chỉ rõ text search configuration khi xây expression index hoặc generated column.
- Cách tạo GIN expression index **không cần lưu `tsvector` thành cột**.
- Cách tạo **stored generated tsvector** với trọng số khác nhau cho tiêu đề và nội dung.
- Cách dùng **`tsvector_update_trigger`** và **custom PL/pgSQL trigger**.
- Cách chọn sự kiện `INSERT`/`UPDATE`, xử lý `NULL`, cấu hình ngôn ngữ, thứ tự trigger và dữ liệu cập nhật.
- Cách migration/backfill trên bảng đã có dữ liệu, phát hiện vector cũ, tạo index an toàn và đo chi phí.
- Những trường hợp trigger hữu ích nhưng generated column hoặc expression index lại đơn giản, ít lỗi hơn.

> **Lưu ý thực hành:** Toàn bộ SQL của bài sử dụng schema `fts_refresh_lab` trong database thử nghiệm. Các ví dụ `EXPLAIN (ANALYZE)` chỉ áp dụng với SELECT thuần trên dữ liệu lab. `EXPLAIN ANALYZE UPDATE/INSERT/DELETE` **thực sự thực thi câu lệnh ghi**, không phải chế độ xem trước vô hại.

---

## 1. Nền tảng: tsvector và tsquery dùng để làm gì?

### 1.1. Không tìm chuỗi nguyên văn như LIKE

Một ứng dụng có thể bắt đầu bằng:

```sql
SELECT *
FROM articles
WHERE title ILIKE '%search%'
   OR body ILIKE '%search%';
```

Cách này tìm theo chuỗi con, có ích trong một số tình huống nhưng không tự hiểu:

- Phân tách từ.
- **Lexeme** và stemming.
- Stop words.
- Vị trí xuất hiện của từ.
- Truy vấn nhiều từ bằng toán tử logic.
- Xếp hạng theo tần suất/trọng số.

PostgreSQL FTS cung cấp các kiểu và hàm riêng cho những nhu cầu ấy.

### 1.2. tsvector: tài liệu đã chuẩn hóa

```sql
SELECT to_tsvector(
    'pg_catalog.english'::regconfig,
    'PostgreSQL indexes help searching documents'
) AS document_vector;
```

Kết quả sẽ chứa các lexeme đã xử lý theo cấu hình `english`, thường kèm **vị trí** trong văn bản. Dấu hiệu là những từ được đưa về dạng dùng để tìm kiếm, ví dụ từ số nhiều/biến thể có thể được stem.

Không coi output của ví dụ này là một chuỗi cố định bất biến giữa mọi cấu hình và phiên bản từ điển; hãy chạy `SELECT` để quan sát trên server thật.

### 1.3. tsquery: biểu thức điều kiện tìm kiếm

```sql
SELECT plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'searching documents'
) AS query_terms;
```

`plainto_tsquery` chuyển văn bản người dùng thành một biểu thức tìm kiếm thông thường, dùng quy tắc cấu hình để chuẩn hóa từ.

`websearch_to_tsquery` hỗ trợ cú pháp tìm kiếm thân thiện hơn như chuỗi trong dấu ngoặc kép, dấu trừ để loại từ và `OR`:

```sql
SELECT websearch_to_tsquery(
    'pg_catalog.english'::regconfig,
    '"full text" OR indexing'
);
```

### 1.4. Toán tử @@ đối chiếu vector và query

```sql
SELECT
    to_tsvector(
        'pg_catalog.english'::regconfig,
        'Full text search uses inverted indexes'
    ) @@
    plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'search indexes'
    ) AS matches;
```

Hai toán hạng có kiểu `tsvector` và `tsquery`; kết quả của `@@` là boolean.

### 1.5. FTS không phải tìm chuỗi con

Với FTS, truy vấn một từ không nhất thiết khớp phần bất kỳ bên trong một từ dài hơn. Nếu muốn tìm `'sql'` trong mọi substring, FTS không tương đương với `ILIKE '%sql%'`. Với substring search, `pg_trgm` có thể là công cụ phù hợp hơn.

Ngoài ra:

- FTS hỗ trợ **chuẩn hóa lexeme** theo cấu hình.
- FTS có các toán tử logic và hỗ trợ phrase/proximity theo vị trí.
- B-tree, GIN và GiST có vai trò khác nhau.
- Kết quả được coi là phù hợp `@@` chưa chắc là kết quả được xếp hạng cao nhất; ranking là bước bổ sung.

---

## 2. Chọn text search configuration trước khi tạo vector

`to_tsvector` không tự hiểu mọi ngôn ngữ. Nó dùng **text search configuration** để chọn parser và dictionary xử lý token.

### 2.1. Xem cấu hình mặc định

```sql
SHOW default_text_search_config;
```

Giá trị này có thể khác nhau giữa databases, roles hoặc sessions.

### 2.2. Tránh hàm dạng một tham số trong expression index

```sql
SELECT to_tsvector('PostgreSQL search indexes');
```

Lời gọi một tham số phụ thuộc cấu hình mặc định của session. Điều đó gây hai vấn đề nếu dùng để bảo trì vector/index:

1. Hai sessions có cấu hình khác nhau có thể sinh các lexeme khác nhau cho cùng một văn bản.
2. Biểu thức index/generated column thường yêu cầu function **IMMUTABLE**, trong khi biến thể phụ thuộc cấu hình mặc định không đáp ứng hợp đồng ấy.

Vì vậy, khi định nghĩa expression index hoặc generated column, hãy chỉ rõ cấu hình:

```sql
SELECT to_tsvector(
    'pg_catalog.english'::regconfig,
    'PostgreSQL search indexes'
);
```

### 2.3. Vì sao dạng regconfig, text quan trọng?

`to_tsvector(regconfig, text)` dùng cấu hình được chọn rõ ràng, cho phép PostgreSQL coi kết quả phụ thuộc vào những đối số xác định theo hợp đồng function. Đây là dạng phù hợp để viết biểu thức index trong những trường hợp được hỗ trợ.

```sql
-- Dạng phù hợp để làm nguồn của expression index:
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title, '')
)
```

Lưu ý: `regconfig` trỏ tới cấu hình hiện có. **Thay đổi định nghĩa của dictionary/config đã dùng** có thể làm lexeme cũ trong stored vector hoặc index không còn tương thích; đó là một migration cần rebuild/recompute có chủ đích, không phải thay đổi “miễn phí”.

### 2.4. English và simple khác nhau

```sql
SELECT
    to_tsvector('pg_catalog.english'::regconfig,
                'running searches') AS english_vector,
    to_tsvector('pg_catalog.simple'::regconfig,
                'running searches') AS simple_vector;
```

`english` có từ điển stem/stop words cho tiếng Anh; `simple` chủ yếu chuẩn hóa token ở mức đơn giản hơn và không có cùng quy tắc stemming tiếng Anh.

Không dùng `simple` chỉ vì tên “đơn giản” rồi mong chất lượng tìm kiếm cho tiếng Việt hoặc nhiều ngôn ngữ tự động tương đương hệ thống tìm kiếm chuyên biệt.

### 2.5. Nội dung tiếng Việt cần kiểm chứng riêng

PostgreSQL có các cấu hình và extension khác nhau tùy cài đặt. Các từ tiếng Việt có dấu, phân tách theo âm tiết, từ ghép và biến thể ngôn ngữ đòi hỏi kiểm chứng riêng. `pg_catalog.english` **không phải từ điển stemming tiếng Việt**.

Một sản phẩm tiếng Việt có thể cần:

- Cấu hình từ điển phù hợp hoặc pipeline tách từ bên ngoài.
- Quy tắc chuẩn hóa dấu/chữ hoa đã được thống nhất.
- Các cột token/search riêng theo nghiệp vụ.
- Đo precision/recall của truy vấn tiếng Việt thực tế.

Không gắn nhãn một trigger “FTS tiếng Việt chuẩn” chỉ vì nó gọi `to_tsvector('simple', text)`.

### 2.6. Quy tắc nhất quán giữa document và query

Một vector được tạo bằng `english` nên thường được đối chiếu với query tạo bằng **cùng cấu hình**:

```sql
to_tsvector('pg_catalog.english'::regconfig, body)
  @@
websearch_to_tsquery('pg_catalog.english'::regconfig, 'search phrase')
```

Trộn `english` và `simple` có thể cho kết quả không mong đợi vì lexeme ở hai phía khác nhau.

---

## 3. Thiết kế chiến lược: expression index, generated column, trigger

### 3.1. Bảng so sánh nhanh

| Tiêu chí | Expression GIN index | Stored generated tsvector | Trigger cập nhật tsvector |
|---|---|---|---|
| Có cột `tsvector` riêng? | **Không bắt buộc** | **Có**, được PostgreSQL quản lý | **Có**, là cột bình thường |
| Tự đồng bộ khi INSERT/UPDATE nguồn? | **Có**, index key được duy trì | **Có**, generated expression tính khi ghi | **Có nếu trigger chạy đúng** |
| Cần viết function/trigger riêng? | Không | Không | Trigger built-in hoặc custom |
| Dùng `GIN`? | GIN trên biểu thức | GIN trên generated column | GIN trên cột do trigger duy trì |
| Hỗ trợ trọng số A/B/C/D? | Có thể, biểu thức cần khớp query | Rất thuận tiện với `setweight` | Rất linh hoạt |
| Query ngắn gọn bằng `search_vector @@ ...`? | Không, trừ khi có thiết kế khác | Có | Có |
| Chi phí lưu trữ vector riêng | Không có cột vector riêng | Có | Có |
| Rủi ro dữ liệu vector cũ do lỗi logic | Thấp nếu index hợp lệ | Thấp nếu expression/config đúng | Cao hơn nếu trigger thiếu/bị tắt/logic sai |
| Migration bảng lớn | Build index, có thể concurrently | Thêm STORED column có thể tốn thời gian/rewrite | Thêm cột, backfill, tạo trigger/index |
| Logic phức tạp và quy tắc riêng | Giới hạn bởi immutable index expression | Giới hạn bởi immutable generated expression | Linh hoạt theo PL/pgSQL |

**Nguyên tắc lựa chọn:** Nếu `to_tsvector` là biểu thức thuần từ các cột, và không có nhu cầu điều phối thủ công, **expression index hoặc stored generated column thường là phương án đơn giản hơn trigger**. Dùng trigger khi có lý do cụ thể như logic cập nhật đặc thù, nhiều quy tắc phức tạp, yêu cầu triển khai từng giai đoạn hoặc tương thích hệ thống cũ.

### 3.2. Ba đường dữ liệu

```text
Expression index
title/body -> to_tsvector(...) -> GIN index entries
SQL query -> phải dùng biểu thức tương ứng với index

Stored generated column
title/body -> PostgreSQL tính search_vector STORED
search_vector -> GIN index entries
SQL query -> search_vector @@ tsquery

Trigger
title/body -> BEFORE trigger gán NEW.search_vector
search_vector -> GIN index entries
SQL query -> search_vector @@ tsquery
```

### 3.3. Đừng thêm cả ba vào cùng một bảng chỉ để “chắc chắn”

Nếu một bảng vừa có GIN expression index cho toàn bộ tiêu đề/nội dung, vừa có stored generated vector cùng từ, lại có trigger tạo thêm một vector tương đương, việc duy trì sẽ phức tạp và tốn ghi. Hãy chọn **một nguồn tìm kiếm chính** cho mỗi nhu cầu; có thể có nhiều index nếu workload thực sự khác nhau, nhưng phải có lý do.

---

## 4. Phòng thực hành A: expression index không lưu cột tsvector

### 4.1. Kiểm tra môi trường

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Chỉ tiếp tục trong database lab có quyền tạo schema và bảng. Các phiên bản PostgreSQL hiện đại hỗ trợ các công cụ FTS và expression index dùng ở đây.

### 4.2. Tạo schema và bảng nguồn

```sql
CREATE SCHEMA fts_refresh_lab;

CREATE TABLE fts_refresh_lab.articles_expr (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'archived')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Bảng này **không có cột `tsvector`**. Ta sẽ tạo GIN index trên biểu thức được tính trực tiếp từ `title` và `body`.

### 4.3. Nạp tài liệu mẫu

```sql
INSERT INTO fts_refresh_lab.articles_expr
    (tenant_id, title, body, status)
VALUES
    (1, 'PostgreSQL text search tutorial',
        'Learn full text search with inverted indexes.',
        'published'),
    (1, 'Trigger maintenance patterns',
        'Keep search vectors up to date after edits.',
        'published'),
    (2, 'Database indexing strategies',
        'B-tree and GIN indexes solve different access problems.',
        'published'),
    (1, 'Search quality and ranking',
        NULL,
        'draft'),
    (2, 'Vietnamese customer support',
        'An English-config demonstration, not a Vietnamese tokenizer.',
        'published');
```

### 4.4. Thêm dữ liệu để quan sát optimizer

```sql
INSERT INTO fts_refresh_lab.articles_expr
    (tenant_id, title, body, status)
SELECT
    1 + (g % 8),
    CASE
        WHEN g % 200 = 0
            THEN 'PostgreSQL search indexing guide ' || g::text
        WHEN g % 10 = 0
            THEN 'Database operations note ' || g::text
        ELSE 'Daily operational record ' || g::text
    END,
    CASE
        WHEN g % 200 = 0
            THEN 'Full text search with GIN, dictionaries and lexemes.'
        WHEN g % 10 = 0
            THEN 'A routine database maintenance entry.'
        ELSE 'Routine service logs and application metrics.'
    END,
    'published'
FROM generate_series(1, 30000) AS gs(g);
```

Với dữ liệu nạp một lần, bảng có **30.005** rows. Dữ liệu giả nhằm quan sát kế hoạch; không đại diện workload thật.

### 4.5. Tạo expression GIN index

```sql
CREATE INDEX articles_expr_fts_gin_idx
ON fts_refresh_lab.articles_expr
USING GIN (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);

ANALYZE fts_refresh_lab.articles_expr;
```

Trong biểu thức:

- `coalesce(title, '')` và `coalesce(body, '')` xử lý cột NULL.
- `|| ' ' ||` nối văn bản có dấu cách ngăn cách.
- `'pg_catalog.english'::regconfig` cố định cấu hình cho index.
- `to_tsvector(...)` chuyển văn bản sang tsvector.
- GIN ghi nhận các mục tìm kiếm cho lexeme trong index.

### 4.6. Truy vấn phải sử dụng biểu thức phù hợp

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
          'pg_catalog.english'::regconfig,
          coalesce(title, '') || ' ' || coalesce(body, '')
      ) @@ websearch_to_tsquery(
          'pg_catalog.english'::regconfig,
          'PostgreSQL search'
      );
```

Ở đây toán tử `@@` áp lên **chính biểu thức được index**. Planner có thể dùng `articles_expr_fts_gin_idx` nếu chi phí hợp lý.

Một plan có thể hiển thị:

```text
Bitmap Heap Scan on articles_expr
  Recheck Cond: (to_tsvector(...) @@ websearch_to_tsquery(...))
  -> Bitmap Index Scan on articles_expr_fts_gin_idx
       Index Cond: (to_tsvector(...) @@ websearch_to_tsquery(...))
```

Đây là **hình minh họa**, không phải plan cứng. Nếu truy vấn match nhiều hàng, PostgreSQL có thể chọn Seq Scan.

### 4.7. Expression index tự được duy trì khi sửa dữ liệu

Giả sử bài viết `article_id=1` được đổi nội dung:

```sql
UPDATE fts_refresh_lab.articles_expr
SET title = 'New search performance guide',
    body = 'Understanding full text search and GIN',
    updated_at = now()
WHERE article_id = 1;
```

Sau UPDATE, PostgreSQL duy trì index keys liên quan đến hàng đã đổi theo cơ chế index maintenance. **Không cần trigger riêng** chỉ để “làm mới GIN expression index”.

Thử:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
          'pg_catalog.english'::regconfig,
          coalesce(title, '') || ' ' || coalesce(body, '')
      ) @@ plainto_tsquery(
          'pg_catalog.english'::regconfig,
          'performance'
      );
```

### 4.8. Điều kiện không khớp biểu thức index

Nếu query khác:

```sql
SELECT article_id
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
    'pg_catalog.english'::regconfig,
    title
) @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'search'
);
```

thì biểu thức `to_tsvector(config,title)` **khác** expression index trên `coalesce(title,'') || ' ' || coalesce(body,'')`. Index trước không mặc nhiên dùng được cho phép tìm chỉ trên title.

Tương tự, dùng cấu hình `simple` khi index được tạo bằng `english` không còn là biểu thức tương ứng.

### 4.9. Một ưu điểm và một hạn chế

**Ưu điểm:** không có thêm stored tsvector column hay logic trigger; sự đồng bộ gắn trực tiếp với index mechanism của PostgreSQL.

**Hạn chế:** muốn lọc/rank bằng vector tương ứng, query thường phải lặp lại biểu thức. Điều này làm câu SQL dài và dễ bị lệch định nghĩa giữa truy vấn, index và code ứng dụng.

Đó là một lý do nên cân nhắc stored generated column.

---

## 5. Vì sao cần coalesce khi title/body có NULL?

### 5.1. NULL khi nối chuỗi

```sql
SELECT 'Title'::text || NULL::text AS combined_text;
```

Kết quả là SQL `NULL`. Nếu:

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    title || ' ' || body
)
```

và `body IS NULL`, toàn bộ chuỗi đầu vào có thể thành NULL, khiến tìm kiếm không còn từ nào của title trong giá trị vector tính theo biểu thức ấy.

### 5.2. Đúng cách

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title, '') || ' ' || coalesce(body, '')
)
```

Nếu body NULL, title vẫn được xử lý.

### 5.3. Không dùng concat_ws một cách vô thức trong index

`concat_ws` thuận tiện để bỏ qua NULL:

```sql
SELECT concat_ws(' ', 'Title', NULL, 'Body');
```

Nhưng **`concat_ws` không được PostgreSQL khai báo IMMUTABLE cho mọi kiểu đối số**, vì nó phải xử lý dữ liệu có thể phụ thuộc định dạng/ngữ cảnh. Do đó, không nên thay bằng `concat_ws` trong một expression index/generated expression rồi mặc định nó được chấp nhận.

Với cột `TEXT` rõ ràng, `coalesce(title,'') || ' ' || coalesce(body,'')` là biểu thức dễ kiểm soát hơn khi cần immutability.

### 5.4. Từ điển vẫn có thể loại stop words

Một tài liệu chỉ chứa `'the and or'` khi dùng `english` có thể tạo vector rỗng vì stop words. Điều này **khác** việc NULL làm hỏng phép nối. Thiết kế bộ kiểm tra dữ liệu cần phân biệt:

- Vector NULL do logic không xử lý.
- Vector rỗng hợp lệ do văn bản không có lexeme hữu ích.

---

## 6. Phòng thực hành B: generated column lưu tsvector

Stored generated column là lựa chọn rõ ràng khi muốn biểu thức tìm kiếm được định nghĩa **một lần trong schema** và đọc bằng tên cột.

### 6.1. Tạo bảng có search_vector phát sinh

```sql
CREATE TABLE fts_refresh_lab.articles_generated (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'published',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'pg_catalog.english'::regconfig,
                coalesce(title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.english'::regconfig,
                coalesce(body, '')
            ),
            'D'
        )
    ) STORED
);
```

**Ý nghĩa:**

- Vector được PostgreSQL tính khi row được ghi.
- Nó được **lưu** trong bảng như một giá trị phát sinh.
- Tiêu đề dùng weight `A`, nội dung dùng weight `D`.
- Không cần trigger để đồng bộ vector từ `title`/`body`.

Đây là **stored generated column**, không phải generated column ở dạng tính ảo. Cú pháp `STORED` được chỉ định rõ để áp dụng đúng kiểu lưu vector mà bài học đang bàn.

### 6.2. Vì sao gọi setweight riêng từng phần?

Nếu:

```sql
to_tsvector(config, coalesce(title,'') || ' ' || coalesce(body,''))
```

thì từ tiêu đề và nội dung đều nhận weight mặc định. Muốn tăng ưu tiên tiêu đề khi ranking:

```sql
setweight(to_tsvector(config, coalesce(title,'')), 'A')
||
setweight(to_tsvector(config, coalesce(body,'')), 'D')
```

`setweight` gắn trọng số lên vị trí từ **trước khi ghép hai vector**. Các trọng số có nhãn `A`, `B`, `C`, `D`; `A` thường được quy ước quan trọng nhất khi hàm rank dùng trọng số mặc định, nhưng ứng dụng có thể cung cấp mảng trọng số riêng.

### 6.3. Nạp dữ liệu

```sql
INSERT INTO fts_refresh_lab.articles_generated
    (tenant_id, title, body)
VALUES
    (1, 'PostgreSQL full text search',
        'Generated columns keep search vectors current.'),
    (1, 'Trigger implementation notes',
        'Triggers maintain values before writing rows.'),
    (2, 'Index architecture',
        'GIN indexes help search many documents.'),
    (2, 'Search-only title',
        NULL);
```

Không đưa `search_vector` vào `INSERT` vì đây là cột generated.

### 6.4. Quan sát giá trị vector được lưu

```sql
SELECT
    article_id,
    title,
    search_vector
FROM fts_refresh_lab.articles_generated
ORDER BY article_id;
```

Output thường có các lexeme kèm số vị trí/trọng số như `1A` cho từ trong title và các vị trí khác ở body. Giá trị cụ thể phụ thuộc cấu hình và văn bản.

### 6.5. Tạo GIN trên cột generated

```sql
CREATE INDEX articles_generated_fts_gin_idx
ON fts_refresh_lab.articles_generated
USING GIN (search_vector);
```

Câu truy vấn ngắn hơn:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english'::regconfig,
    'PostgreSQL search'
);
```

### 6.6. UPDATE title/body tự làm mới vector

```sql
SELECT article_id, title, search_vector
FROM fts_refresh_lab.articles_generated
WHERE article_id = 1;

UPDATE fts_refresh_lab.articles_generated
SET title = 'Improved full text indexing',
    body = 'Indexing and ranking with generated tsvector',
    updated_at = now()
WHERE article_id = 1;

SELECT article_id, title, search_vector
FROM fts_refresh_lab.articles_generated
WHERE article_id = 1;
```

Sau UPDATE, vector được PostgreSQL tính lại theo biểu thức generated, rồi index GIN trên vector cũng được duy trì tương ứng.

### 6.7. Không được tự gán giá trị tùy ý

```sql
-- Không hợp lệ như một giá trị tự do của generated column:
-- UPDATE fts_refresh_lab.articles_generated
-- SET search_vector = 'manual lexeme'::tsvector
-- WHERE article_id = 1;
```

Giá trị `search_vector` do biểu thức generated quyết định. Nếu muốn đổi cách lập vector, thay đổi **định nghĩa schema** có kiểm soát thay vì cập nhật cột generated thủ công.

### 6.8. Generated column và BEFORE trigger

Với stored generated column, biểu thức được tính **sau các BEFORE triggers** theo cơ chế PostgreSQL, để phản ánh giá trị hàng cuối cùng trước khi lưu. Không nên thiết kế BEFORE trigger dựa vào việc đọc giá trị generated column của `NEW` như thể nó đã tính xong.

Nếu một BEFORE trigger chuẩn hóa title, generated expression thường tính trên giá trị đã chuẩn hóa ở thời điểm phù hợp. Dù vậy, hãy kiểm tra hành vi và những trigger khác theo phiên bản server, đặc biệt khi migration.

### 6.9. Chi phí của generated column

Đổi title/body sẽ làm PostgreSQL tính vector mới khi ghi. Bảng còn lưu dữ liệu vector ngoài title/body, và GIN index cần được duy trì. Điều này tăng storage và write work so với một bảng không có FTS, dù giảm lỗi đồng bộ do custom trigger.

---

## 7. Xếp hạng kết quả với tsvector có trọng số

### 7.1. @@ chỉ xác định phù hợp, không tự sort theo mức độ liên quan

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'indexing'
);
```

Nếu không có `ORDER BY`, SQL **không bảo đảm** thứ tự kết quả. GIN không tự trả kết quả theo mức ranking.

### 7.2. ts_rank

```sql
WITH search_input AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.english'::regconfig,
        'indexing'
    ) AS q
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, s.q) AS score
FROM fts_refresh_lab.articles_generated AS a
CROSS JOIN search_input AS s
WHERE a.search_vector @@ s.q
ORDER BY score DESC, a.article_id DESC
LIMIT 20;
```

`ts_rank` dùng thông tin lexeme/trọng số/tần suất theo công thức của PostgreSQL để cho điểm. Điểm rank không phải xác suất chính xác rằng kết quả “đúng 95%”, và không nên so score tùy ý giữa các phiên bản thuật toán/corpus.

### 7.3. ts_rank_cd

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'full text'
    ) AS needle
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(a.search_vector, q.needle) AS cover_density
FROM fts_refresh_lab.articles_generated AS a
CROSS JOIN q
WHERE a.search_vector @@ q.needle
ORDER BY cover_density DESC, a.article_id DESC;
```

`ts_rank_cd` là cách tính rank dựa vào *cover density*, quan tâm vị trí gần nhau của từ. Các vector bị **strip position** sẽ hạn chế cách tính này; xem `strip()` và yêu cầu ranking trước khi cắt bỏ positions.

### 7.4. GIN không thay sort theo score

Một query FTS phổ biến có thể:

```text
Bitmap Index Scan on GIN(search_vector)
         |
         v
Bitmap Heap Scan / recheck
         |
         v
Compute ts_rank(...)
         |
         v
Sort by score DESC
         |
         v
LIMIT 20
```

GIN hỗ trợ **lọc candidate**, nhưng không cung cấp sẵn thứ tự `ts_rank`. Nếu hit count quá lớn, bước ranking/sort vẫn có thể tốn nhiều CPU và memory.

### 7.5. Weight restriction trong tsquery

PostgreSQL có cú pháp `tsquery` hạn chế theo weight, ví dụ lexeme gắn hậu tố `:A` khi dùng `to_tsquery`:

```sql
SELECT to_tsquery(
    'pg_catalog.english'::regconfig,
    'postgresql:A'
);
```

Khi truy vấn giới hạn weight, cần biết rằng **GIN index không lưu đầy đủ thông tin weight của các vị trí như tsvector heap**, nên bước recheck có thể cần thiết để xác minh điều kiện.

Không coi GIN là index “vừa lọc vừa xếp hạng chính xác toàn bộ” chỉ vì tsvector có trọng số.

---

## 8. Phòng thực hành C: trigger tích hợp tsvector_update_trigger

Trước khi stored generated column trở nên phổ biến, một chiến lược truyền thống là lưu `tsvector` bình thường và dùng trigger tích hợp để duy trì.

### 8.1. Tạo bảng có cột search_vector thường

```sql
CREATE TABLE fts_refresh_lab.articles_builtin_trigger (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    search_vector TSVECTOR
);
```

`search_vector` ở bảng này **không phải generated column**. Nếu không có trigger hoặc thao tác cập nhật thủ công, nó có thể NULL hoặc cũ.

### 8.2. Tạo trigger built-in

```sql
CREATE TRIGGER articles_builtin_search_refresh
BEFORE INSERT OR UPDATE
ON fts_refresh_lab.articles_builtin_trigger
FOR EACH ROW
EXECUTE FUNCTION pg_catalog.tsvector_update_trigger(
    search_vector,
    'pg_catalog.english',
    title,
    body
);
```

Các tham số truyền cho trigger function được hiểu:

1. **Cột đích `tsvector`**: `search_vector`.
2. **Tên text search configuration**: `'pg_catalog.english'` (dạng chuỗi, schema-qualified).
3. **Các cột text nguồn**: `title` và `body`.

`tsvector_update_trigger` là trigger function tích hợp của PostgreSQL. Nó không đòi hỏi người học tạo function PL/pgSQL mới cho trường hợp đơn giản.

### 8.3. Vì sao schema-qualified config?

`'pg_catalog.english'` làm rõ cấu hình được dùng, không phụ thuộc vào `search_path` của session để chọn cấu hình trùng tên. Cấu hình dùng cho vector và tsquery nên nhất quán.

### 8.4. Thử INSERT

```sql
INSERT INTO fts_refresh_lab.articles_builtin_trigger
    (title, body)
VALUES
    ('PostgreSQL trigger tutorial',
     'A trigger maintains the search vector.'),
    ('Database indexing',
     'Using GIN for full text documents.');

SELECT article_id, title, search_vector
FROM fts_refresh_lab.articles_builtin_trigger
ORDER BY article_id;
```

Mỗi row được insert sẽ chạy BEFORE trigger; trigger gán vector từ title/body trước khi lưu.

### 8.5. Thử UPDATE

```sql
UPDATE fts_refresh_lab.articles_builtin_trigger
SET title = 'Automatic text search refresh',
    body = 'The trigger runs after the application changes source text.'
WHERE article_id = 1;

SELECT article_id, search_vector
FROM fts_refresh_lab.articles_builtin_trigger
WHERE article_id = 1;
```

Vector được tính lại bởi trigger. Vì trigger khai báo `BEFORE INSERT OR UPDATE` **không giới hạn cột UPDATE**, mỗi UPDATE row phù hợp đều kích hoạt, kể cả khi chỉ sửa cột khác.

### 8.6. Tạo GIN trên cột do trigger duy trì

```sql
CREATE INDEX articles_builtin_trigger_gin_idx
ON fts_refresh_lab.articles_builtin_trigger
USING GIN (search_vector);
```

Truy vấn:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_builtin_trigger
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'automatic search'
);
```

### 8.7. Khi nào built-in trigger không đủ?

`tsvector_update_trigger` thích hợp cho việc tổng hợp một số cột text thành vector với cấu hình cố định. Nhưng nếu muốn:

- Trọng số **A cho title**, **D cho body**.
- Quy tắc chuẩn hóa dựa vào nhiều thuộc tính.
- Cấu hình ngôn ngữ theo từng hàng.
- Bỏ/nhận nội dung theo điều kiện nghiệp vụ.

thì có thể cần **stored generated expression** hoặc **custom trigger**.

### 8.8. Trigger có sẵn vẫn là một dependency vận hành

Nếu trigger bị vô hiệu hóa, DDL làm nó mất hiệu lực, bulk load chạy với cấu hình bỏ qua trigger tương ứng hoặc schema bị thay đổi không đồng bộ, `search_vector` có thể không còn phản ánh dữ liệu nguồn. Đây là điểm khác biệt chính so với generated column hoặc expression index được hệ thống quản lý như một biểu thức.

---

## 9. Custom PL/pgSQL trigger với trọng số và cấu hình theo hàng

Khi logic vượt khả năng built-in trigger, có thể viết trigger riêng.

### 9.1. Tạo bảng đa ngôn ngữ ở mức cấu hình

```sql
CREATE TABLE fts_refresh_lab.articles_weighted_trigger (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    search_config REGCONFIG NOT NULL
        DEFAULT 'pg_catalog.english'::regconfig,
    search_vector TSVECTOR NOT NULL
        DEFAULT ''::tsvector,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`search_config` là một cột PostgreSQL kiểu `regconfig`. Cột này cho phép mỗi hàng chọn một text search configuration, nhưng **không tự bảo đảm chất lượng tìm kiếm đa ngôn ngữ**. Ứng dụng phải có quy tắc chọn cấu hình và query tương thích.

### 9.2. Viết trigger function

```sql
CREATE OR REPLACE FUNCTION
    fts_refresh_lab.refresh_weighted_search_vector()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.search_vector :=
        setweight(
            to_tsvector(
                NEW.search_config,
                coalesce(NEW.title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                NEW.search_config,
                coalesce(NEW.body, '')
            ),
            'D'
        );

    RETURN NEW;
END;
$function$;
```

Các điểm quan trọng:

- Function trả kiểu `trigger`, không trả trực tiếp `tsvector`.
- `NEW` là row sẽ được ghi.
- Trigger gán `NEW.search_vector`.
- `RETURN NEW` để INSERT/UPDATE tiếp tục với row đã được sửa.
- `NEW.search_config` quyết định cách token hóa và stemming cho từng hàng.
- Không dùng dynamic SQL hoặc ghép tên hàm/cột từ input người dùng.

### 9.3. Gắn BEFORE trigger

```sql
CREATE TRIGGER articles_weighted_search_refresh
BEFORE INSERT OR UPDATE
ON fts_refresh_lab.articles_weighted_trigger
FOR EACH ROW
EXECUTE FUNCTION
    fts_refresh_lab.refresh_weighted_search_vector();
```

Ở ví dụ này, trigger chạy trên **mọi INSERT/UPDATE** để bảo vệ bất biến `search_vector` luôn được tính từ `title`, `body` và `search_config` theo logic function.

### 9.4. Tạo GIN

```sql
CREATE INDEX articles_weighted_trigger_gin_idx
ON fts_refresh_lab.articles_weighted_trigger
USING GIN (search_vector);
```

### 9.5. Chèn dữ liệu

```sql
INSERT INTO fts_refresh_lab.articles_weighted_trigger
    (tenant_id, title, body, search_config)
VALUES
    (
        1,
        'PostgreSQL search implementation',
        'Custom triggers provide weighted documents.',
        'pg_catalog.english'::regconfig
    ),
    (
        2,
        'Simple token demonstration',
        'Running runners run.',
        'pg_catalog.simple'::regconfig
    );
```

Xem vector:

```sql
SELECT
    article_id,
    search_config,
    title,
    search_vector
FROM fts_refresh_lab.articles_weighted_trigger
ORDER BY article_id;
```

Hai hàng có thể có lexeme khác nhau vì text search configurations khác nhau.

### 9.6. Truy vấn nhóm tiếng Anh

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_weighted_trigger
WHERE search_config = 'pg_catalog.english'::regconfig
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.english'::regconfig,
      'PostgreSQL implementation'
  );
```

Khi document được xử lý bằng `english`, tsquery cũng dùng `english`. Không lấy một cấu hình query duy nhất rồi tuyên bố mọi ngôn ngữ đều sẽ match giống nhau.

### 9.7. Cập nhật cấu hình cũng phải cập nhật vector

```sql
UPDATE fts_refresh_lab.articles_weighted_trigger
SET search_config = 'pg_catalog.english'::regconfig
WHERE article_id = 2;

SELECT article_id, search_config, search_vector
FROM fts_refresh_lab.articles_weighted_trigger
WHERE article_id = 2;
```

Vì trigger khai báo cho mọi UPDATE, việc thay `search_config` cũng tính lại vector. Nếu một trigger chỉ lắng nghe `UPDATE OF title, body`, thao tác đổi cấu hình có thể khiến vector cũ **không được tính lại**.

---

## 10. Trigger chỉ chạy khi những cột liên quan được UPDATE?

PostgreSQL cho phép khai báo trigger theo danh sách cột:

```sql
-- Ví dụ lựa chọn thay thế, KHÔNG tạo thêm trên bảng đang có trigger:
--
-- CREATE TRIGGER articles_weighted_search_refresh
-- BEFORE INSERT OR UPDATE OF title, body, search_config
-- ON fts_refresh_lab.articles_weighted_trigger
-- FOR EACH ROW
-- EXECUTE FUNCTION
--     fts_refresh_lab.refresh_weighted_search_vector();
```

### 10.1. Lợi ích

Nếu hệ thống cập nhật `updated_at` rất thường xuyên nhưng hiếm khi đổi nội dung, trigger `UPDATE OF title, body, search_config` có thể tránh việc chạy function khi câu UPDATE **không liệt kê** các cột liên quan trong `SET`.

### 10.2. Bẫy quan trọng: UPDATE OF dựa vào danh sách SET

Không nên diễn giải trigger `UPDATE OF title` là “trigger chỉ chạy khi giá trị title thực sự đổi”.

Ví dụ:

```sql
UPDATE fts_refresh_lab.articles_weighted_trigger
SET title = title
WHERE article_id = 1;
```

Vì `title` nằm trong danh sách `SET`, column-specific trigger có thể chạy **dù giá trị mới bằng cũ**.

Ngược lại, nếu một BEFORE trigger khác sửa `NEW.title` khi câu SQL chỉ `SET body = body` hoặc một cột khác, việc kích hoạt `UPDATE OF title` không nhất thiết phát hiện sự thay đổi title do trigger khác gây ra.

### 10.3. Thứ tự nhiều BEFORE triggers

Khi có nhiều trigger **cùng loại** trên một bảng và cùng event, PostgreSQL áp dụng quy tắc thứ tự theo **tên trigger**. Nếu một trigger chuẩn hóa title chạy **sau** trigger FTS, vector có thể được tính từ title chưa chuẩn hóa.

Vì vậy:

- Tránh phân tán nhiều trigger phụ thuộc lẫn nhau mà không xác định thứ tự.
- Nếu có trigger làm sạch title/body, đảm bảo FTS nhìn giá trị cuối cùng.
- Cân nhắc gộp logic hoặc dùng generated column khi bài toán chỉ là biểu thức thuần.
- Viết thử nghiệm sau INSERT/UPDATE để phát hiện vector lệch.

### 10.4. Dùng IS DISTINCT FROM để tránh tính lại không cần thiết

Trong custom trigger, có thể tối ưu bằng điều kiện:

```sql
-- Phần minh họa để đưa vào đầu thân trigger,
-- chỉ khi đã thiết kế chính sách vector không cho ứng dụng sửa trực tiếp.
--
-- IF TG_OP = 'UPDATE'
--    AND NEW.title IS NOT DISTINCT FROM OLD.title
--    AND NEW.body IS NOT DISTINCT FROM OLD.body
--    AND NEW.search_config IS NOT DISTINCT FROM OLD.search_config
-- THEN
--     RETURN NEW;
-- END IF;
```

`IS NOT DISTINCT FROM` so sánh có xử lý NULL rõ ràng, phù hợp hơn `=` khi body nullable.

**Nhưng phải có bất biến**: nếu ứng dụng được phép sửa `search_vector` trực tiếp, nhánh bỏ qua có thể để một vector sai tồn tại. Nếu vector có thể NULL do migration, logic bỏ qua cũng có thể khiến row không được sửa. Với bài lab, trigger **tính lại trên mọi UPDATE** để đơn giản và an toàn về nhất quán.

### 10.5. Trigger WHEN và INSERT

`WHEN` có thể giảm số lần gọi trigger function cho UPDATE. Tuy nhiên, `OLD` không tồn tại như row cũ trong INSERT, nên không viết một điều kiện WHEN duy nhất dùng OLD cho cả INSERT và UPDATE nếu không phù hợp cú pháp/semantics. Có thể tách trigger INSERT và UPDATE khi tối ưu sâu.

Không ưu tiên tối ưu vài microseconds nếu làm hệ thống tạo stale vectors âm thầm.

---

## 11. Khi nào dùng built-in trigger theo cột cấu hình?

Ngoài `tsvector_update_trigger`, PostgreSQL còn hỗ trợ `tsvector_update_trigger_column` để đọc cấu hình tìm kiếm từ **một cột của chính row** thay vì một tên config cố định.

### 11.1. Ý tưởng

```text
article row
  title, body
  search_config = 'pg_catalog.english'::regconfig
           |
           v
  tsvector_update_trigger_column
           |
           v
  search_vector
```

Với bảng có cột `search_config REGCONFIG`, có thể cân nhắc:

```sql
-- Phương án thay thế cho custom trigger của mục 9,
-- KHÔNG tạo đồng thời hai trigger bảo trì cùng một cột.
--
-- CREATE TRIGGER articles_search_from_config_column
-- BEFORE INSERT OR UPDATE
-- ON fts_refresh_lab.articles_weighted_trigger
-- FOR EACH ROW
-- EXECUTE FUNCTION pg_catalog.tsvector_update_trigger_column(
--     search_vector,
--     search_config,
--     title,
--     body
-- );
```

### 11.2. Khi nào nó phù hợp?

Khi yêu cầu chỉ là **gom các cột text thành một vector** nhưng mỗi row dùng text search configuration khác nhau. Nếu muốn **trọng số title A/body D**, function built-in này không cung cấp ngôn ngữ gán trọng số theo từng input trong lời gọi đơn giản; khi đó generated expression hoặc custom trigger dễ diễn đạt hơn.

### 11.3. Cấu hình theo row có cái giá của nó

Nếu search query đến từ người dùng, bạn phải quyết định:

- Query dùng config nào?
- Có một request tìm đồng thời nhiều config không?
- Cần nhóm theo ngôn ngữ/tenant trước khi tạo tsquery không?
- Có đảm bảo từ điển/config không bị đổi tùy tiện không?

`WHERE search_vector @@ websearch_to_tsquery(search_config, $1)` có **RHS phụ thuộc vào giá trị mỗi row**, có thể khó dùng đường truy cập GIN hiệu quả như khi RHS là một tsquery xác định cho toàn truy vấn. Đối với nhiều ngôn ngữ, thường cân nhắc query theo từng config cố định rồi hợp nhất kết quả theo yêu cầu ứng dụng.

---

## 12. Biểu thức index và generated column cũng có giới hạn immutability

### 12.1. Biểu thức hợp lệ với config tường minh

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title, '') || ' ' || coalesce(body, '')
)
```

Dạng này thể hiện rõ mọi input từ row và một config cụ thể.

### 12.2. Dạng thiếu config thường không phù hợp

```sql
-- Không dùng như expression index key:
-- CREATE INDEX bad_fts_idx
-- ON fts_refresh_lab.articles_expr
-- USING GIN (to_tsvector(title || ' ' || body));
```

`to_tsvector(text)` phụ thuộc `default_text_search_config` và không đáp ứng yêu cầu immutable của biểu thức index.

### 12.3. Không giả danh IMMUTABLE

Không nên tạo một wrapper function đọc cấu hình session/dịch vụ ngoài rồi khai báo `IMMUTABLE` chỉ để vượt lỗi khi tạo index/generated column. Khi PostgreSQL tin kết quả bất biến mà thực tế khác, index hoặc generated data có thể **không phản ánh đúng nội dung**.

### 12.4. Generated column không dành cho phép truy vấn bảng khác

Generated expression phải tuân thủ giới hạn của PostgreSQL, ví dụ không được tùy tiện dùng subquery/volatile function hoặc đọc bảng khác trong biểu thức. Nếu bài toán muốn lấy text từ nhiều bảng liên quan:

- Cân nhắc truy vấn JOIN/FTS có cấu trúc.
- Thiết kế bảng tìm kiếm tổng hợp có quy trình đồng bộ.
- Dùng trigger/event/outbox có kiểm soát nếu cần denormalization.
- Đảm bảo xử lý thay đổi ở **tất cả nguồn dữ liệu**, không chỉ row chính.

Không nghĩ trigger trên bảng article tự được gọi khi một hàng comments trong bảng khác thay đổi.

---

## 13. Chất lượng dữ liệu: tsvector có thể cũ như thế nào?

### 13.1. Stale vector là gì?

Giả sử row có:

```text
title = 'PostgreSQL indexing'
body  = 'Learn GIN indexes'
search_vector = vector của văn bản cũ 'Trigger tutorial'
```

Nếu query tìm theo `search_vector`, nội dung mới có thể **không được tìm thấy** mặc dù title/body đã đổi.

### 13.2. Những nguyên nhân hay gặp với trigger

- Trigger chưa được tạo khi import dữ liệu cũ.
- Trigger chỉ chạy `INSERT`, quên `UPDATE`.
- Trigger `UPDATE OF title` nhưng nội dung thực tế thay đổi qua cột khác hoặc trigger khác.
- Thêm cột `summary` vào văn bản tìm kiếm nhưng không cập nhật function.
- Thay cấu hình từ `english` sang `simple` mà không rebuild vector cũ.
- Một quá trình bulk load/replication bypass hoặc disable trigger.
- Code application ghi trực tiếp `search_vector` mà không giữ bất biến.
- Trigger function bị thay thế có logic mới nhưng rows cũ chưa được backfill.
- Một record có `body NULL` làm phép nối text trả NULL nếu không dùng `coalesce`.

### 13.3. Stored generated column giảm một nhóm lỗi

Nếu `search_vector` được định nghĩa bằng generated expression từ title/body, ứng dụng khó vô tình sửa riêng cột vector và bỏ qua cập nhật nguồn. Cơ chế PostgreSQL tính lại khi ghi giúp giảm rủi ro mất đồng bộ.

Nhưng generated column **không tự cập nhật toàn bộ rows khi định nghĩa từ điển/cấu hình tìm kiếm bên ngoài dữ liệu được thay đổi**, và một migration đổi logic vector vẫn có thể yêu cầu recompute/rewrite.

### 13.4. Expression index cũng không tự thay đổi khi dictionary được sửa

Nếu expression index tạo từ `to_tsvector(config,title/body)`, các index entries phản ánh kết quả tại thời điểm chúng được tính. Thay đổi mapping/dictionary của config có thể đòi hỏi **REINDEX hoặc rebuild có kiểm soát** để các index keys phù hợp với quy tắc mới.

Phân biệt:

- **Expression index**: cần tái xây **index entries** theo cấu hình mới.
- **Stored generated / trigger-maintained tsvector**: cần **tính lại giá trị vector được lưu trên rows** (và GIN sẽ được duy trì theo), không chỉ REINDEX trên vector cũ.

### 13.5. Kiểm chứng nhất quán bằng truy vấn

Với bảng `articles_weighted_trigger` và function đã định nghĩa, ta có thể tìm rows lệch:

```sql
SELECT article_id, title, search_config
FROM fts_refresh_lab.articles_weighted_trigger AS a
WHERE a.search_vector IS DISTINCT FROM (
    setweight(
        to_tsvector(
            a.search_config,
            coalesce(a.title, '')
        ),
        'A'
    )
    ||
    setweight(
        to_tsvector(
            a.search_config,
            coalesce(a.body, '')
        ),
        'D'
    )
);
```

Điều kiện kiểm chứng phải dùng **chính sách xây vector giống function thực tế**. Trên bảng lớn, truy vấn này có thể tốn CPU vì phải tính tsvector cho rất nhiều rows; chạy theo lô hoặc lấy mẫu khi cần.

### 13.6. Không dùng sai lệch độ dài làm bằng chứng chính xác

Hai vector có thể có cùng `length(search_vector)` nhưng chứa lexeme khác nhau. Muốn kiểm chứng đúng phải so **nội dung vector** hoặc so kết quả tìm kiếm theo một bộ test representative.

---

## 14. Backfill bảng cũ: từ NULL vector tới tìm kiếm đầy đủ

Một hệ thống đã có nhiều rows thường không thể chỉ tạo trigger rồi coi tất cả dữ liệu cũ đã có vector.

### 14.1. Tình huống

```text
articles cũ:
  id=1 title='...' body='...' search_vector=NULL
  id=2 title='...' body='...' search_vector=NULL

CREATE TRIGGER ...
  -> bảo trì INSERT/UPDATE mới
  -> KHÔNG tự đi qua và cập nhật mọi row cũ
```

### 14.2. Quy trình migration tổng quát

1. Chuẩn bị cột `search_vector TSVECTOR` nullable.
2. Tạo function/trigger để **bảo vệ các ghi mới**.
3. Backfill các rows cũ theo từng batch với cùng logic vector.
4. Kiểm tra số rows NULL/sai lệch.
5. Tạo GIN index (có thể concurrently nếu yêu cầu tải online).
6. Chuyển read queries sang dùng vector, giám sát kết quả.
7. Thêm ràng buộc `NOT NULL` nếu thực sự cần và có kế hoạch DDL phù hợp.

Thứ tự này giảm thời gian các ghi mới tồn tại ngoài cơ chế cập nhật, nhưng deployment vẫn cần xử lý concurrency giữa backfill và writers.

### 14.3. DDL minh họa thêm cột cho bảng sẵn có

Giả sử một bảng nghiệp vụ đã tồn tại:

```sql
-- Mẫu minh họa, không chạy trên bảng đã có cột.
-- ALTER TABLE existing_articles
-- ADD COLUMN search_vector TSVECTOR;
```

Không dùng migration `ADD COLUMN ... GENERATED ... STORED` mà không đánh giá chi phí bảng lớn: thêm một stored generated column có thể đòi hỏi tính vector cho toàn bộ rows và tác động DDL/locks đáng kể, tùy phiên bản.

### 14.4. Backfill trong lô

Với bảng trigger có cột `search_vector` bình thường và cùng công thức:

```sql
-- Ví dụ cho bảng articles_weighted_trigger;
-- giả sử một migration cũ để lại những row search_vector IS NULL.
--
-- UPDATE fts_refresh_lab.articles_weighted_trigger AS a
-- SET search_vector =
--       setweight(
--           to_tsvector(
--               a.search_config,
--               coalesce(a.title,'')
--           ),
--           'A'
--       )
--       ||
--       setweight(
--           to_tsvector(
--               a.search_config,
--               coalesce(a.body,'')
--           ),
--           'D'
--       )
-- WHERE a.article_id BETWEEN 1 AND 1000
--   AND a.search_vector IS NULL;
```

Trong bài lab, cột có `NOT NULL DEFAULT ''::tsvector` nên những row mới không có giá trị NULL. Ví dụ backfill minh họa trường hợp **bảng legacy nullable** trước khi áp constraint; điều kiện `IS NULL` không phù hợp nếu legacy dùng vector rỗng thay cho trạng thái “chưa backfill”.

**Chọn một dấu hiệu backfill rõ ràng** (NULL, boolean migration marker hoặc bảng checkpoint), thay vì giả định mọi vector rỗng đều sai; một bài viết chỉ có stop words có thể cho vector rỗng hợp lệ.

### 14.5. Lặp theo primary-key ranges

Một job backfill thực tế có thể:

```text
batch 1: id 1..1000
batch 2: id 1001..2000
batch 3: id 2001..3000
...
```

Với mỗi batch:

- Mở transaction ngắn.
- Tính vector cho phạm vi.
- Commit.
- Ghi checkpoint.
- Đo WAL/I/O và replication lag.
- Có thể tạm dừng khi production tải cao.

Không bọc UPDATE hàng chục triệu rows trong một transaction kéo dài nhiều giờ nếu không có đánh giá lock, WAL, bloat và rollback.

### 14.6. Đồng thời có writer mới

Nếu trigger đã được bật trước backfill, những INSERT/UPDATE mới sẽ được cập nhật. Nhưng vẫn phải tránh:

- Job cũ ghi trực tiếp search_vector không theo quy tắc.
- Trigger bị tắt trong session import.
- Hai quy trình tính vector với phiên bản function khác nhau.
- Backfill đè dữ liệu bằng một snapshot cũ được tính bên ngoài DB.

Để giảm race, tính vector trong statement UPDATE dựa trên **giá trị row hiện tại** dưới transaction/row lock phù hợp, thay vì xuất dữ liệu ra client, xử lý nhiều giờ rồi ghi ngược mà không kiểm tra version.

### 14.7. Hậu kiểm

Với bảng legacy:

```sql
-- Đổi tên bảng theo migration thực tế:
-- SELECT COUNT(*)
-- FROM existing_articles
-- WHERE search_vector IS NULL;
```

Kết hợp kiểm tra:

- Số hàng chưa backfill.
- So vector với công thức nguồn trên sample hoặc theo batch.
- Kiểm tra query FTS tìm được rows mới và cũ.
- Quan sát trigger enabled/disabled.
- Kiểm tra index hợp lệ.

---

## 15. Tạo GIN trên bảng lớn: CONCURRENTLY và trạng thái index

### 15.1. CREATE INDEX thông thường

```sql
CREATE INDEX articles_generated_new_gin_idx
ON fts_refresh_lab.articles_generated
USING GIN (search_vector);
```

**Chú ý:** bảng `articles_generated` ở mục 6 đã có index `articles_generated_fts_gin_idx` tương tự. Dòng trên chỉ minh họa DDL trên schema thử nghiệm; **không cần tạo một GIN index thứ hai trùng key**.

### 15.2. CREATE INDEX CONCURRENTLY

```sql
-- Chỉ chạy khi cần tạo index mới thực sự.
-- Không đặt trong BEGIN ... COMMIT tường minh.
--
-- CREATE INDEX CONCURRENTLY articles_generated_online_gin_idx
-- ON fts_refresh_lab.articles_generated
-- USING GIN (search_vector);
```

`CONCURRENTLY` nhằm giảm việc ngăn các thao tác ghi trong quá trình build, nhưng có những yêu cầu:

- Không chạy trong **transaction block tường minh**.
- Có thể chờ transaction/snapshot khác.
- Có thể sử dụng đáng kể CPU, I/O, disk và WAL.
- Nếu thất bại hoặc bị ngắt, có thể để lại index **invalid** cần xử lý.
- Việc có index mới không có nghĩa planner sẽ dùng nó ngay trong mọi query.

### 15.3. Kiểm tra trạng thái index

```sql
SELECT
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    pg_size_pretty(pg_relation_size(idx.oid)) AS size
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_namespace AS ns
    ON ns.oid = idx.relnamespace
WHERE ns.nspname = 'fts_refresh_lab'
ORDER BY idx.relname;
```

Nếu `indisvalid=false`, cần đánh giá tình huống và khôi phục theo quy trình (`DROP INDEX CONCURRENTLY` hoặc rebuild khi phù hợp). Không coi chỉ mục mới “đã sẵn sàng” chỉ vì tồn tại tên trong catalog.

### 15.4. Trên bảng lớn, thứ tự migration quan trọng

Với trigger-maintained column có dữ liệu cũ, tốt nhất thường là **backfill trước, build GIN sau**, nếu mục tiêu là không buộc GIN duy trì từng UPDATE backfill quá lớn. Nhưng cũng cần bảo vệ writes mới và đo workload; với hệ thống cần search online liên tục, có thể phải chấp nhận chiến lược chuyển đổi nhiều pha.

Không có một thứ tự cố định tối ưu cho mọi môi trường; phải cân nhắc downtime, IO, concurrency và thời điểm cho phép bật search mới.

---

## 16. Đọc EXPLAIN và hiểu GIN không đồng nghĩa ranking index

### 16.1. Truy vấn trên generated vector

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'indexing'
);
```

### 16.2. Plan có thể dùng Bitmap Index Scan

Một kế hoạch minh họa:

```text
Bitmap Heap Scan on articles_generated
  Recheck Cond: (search_vector @@ ...)
  -> Bitmap Index Scan on articles_generated_fts_gin_idx
       Index Cond: (search_vector @@ ...)
```

GIN thường hỗ trợ xác định vị trí candidate rows; sau đó bitmap heap scan truy cập heap và kiểm tra lại khi cần.

### 16.3. Một bảng demo vài rows thường không dùng GIN

Trong `articles_generated` chỉ có bốn rows, PostgreSQL có thể chọn Seq Scan dù GIN tồn tại. Điều đó hợp lý vì quét vài rows rẻ hơn đi qua index và heap.

Khi đánh giá performance thực tế, dùng dữ liệu và tham số đại diện; không ép `enable_seqscan=off` thành cấu hình production.

### 16.4. Biểu thức index không đồng nghĩa materialized column

Trong bảng `articles_expr`, query có thể dùng GIN expression index nhưng không có cột `search_vector` để SELECT trực tiếp. Nếu cần ranking, SQL có thể phải tính lại expression vector trên những rows liên quan:

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'PostgreSQL search'
    ) AS needle
)
SELECT
    a.article_id,
    a.title,
    ts_rank(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(a.title,'') || ' ' || coalesce(a.body,'')
        ),
        q.needle
    ) AS score
FROM fts_refresh_lab.articles_expr AS a
CROSS JOIN q
WHERE to_tsvector(
          'pg_catalog.english'::regconfig,
          coalesce(a.title,'') || ' ' || coalesce(a.body,'')
      ) @@ q.needle
ORDER BY score DESC, a.article_id DESC
LIMIT 20;
```

Đây là một đánh đổi của expression-index-only so với stored generated vector: mã SQL có thể dài và phần ranking cần tính giá trị biểu thức cho rows được xem xét. Tối ưu thực tế còn tùy planner, cache và workload.

### 16.5. GIN không tự cung cấp thứ tự ts_rank

Ngay cả với GIN trên `search_vector`, `ORDER BY ts_rank(...) DESC` thường cần tính điểm và sort kết quả phù hợp. Đừng nhầm truy xuất ứng viên bằng GIN với bảng đã được sắp xếp sẵn theo relevance.

### 16.6. BUFFERS và rows quan trọng hơn tên node

Đọc:

- Estimated `rows` và actual `rows`.
- `Rows Removed by Filter` nếu có.
- `Recheck Cond` và các trang bitmap exact/lossy.
- `Buffers shared hit/read`.
- Sort method nếu cần ranking.
- Tổng `Execution Time` và biến thiên nhiều lần đo.

Một plan dùng GIN nhưng phải đọc 90% bảng chưa chắc nhanh hơn Seq Scan.

---

## 17. Theo dõi write amplification và chi phí FTS

### 17.1. GIN duy trì nhiều lexemes

Một row tài liệu dài có thể sinh hàng trăm hoặc hàng nghìn lexemes. Khi nội dung thay đổi, việc duy trì GIN có thể tốn nhiều công việc hơn một B-tree trên khóa số.

### 17.2. Pending list và fastupdate

GIN có cơ chế `fastupdate` với pending list để giảm chi phí trung bình của một số thao tác ghi. Những entry đang chờ được hợp nhất/dọn sau đó theo cơ chế GIN, có thể làm độ trễ ghi biến động.

```text
INSERT/UPDATE
     |
     v
  GIN pending list
     |
     | cleanup / merge
     v
  GIN main index
```

Điều chỉnh `gin_pending_list_limit` hoặc `fastupdate` phải dựa trên số liệu và tải hệ thống, không phải mẹo áp dụng mọi database.

### 17.3. Stored vector làm bảng lớn hơn

Khi dùng stored generated hoặc trigger-maintained tsvector:

- `title` và `body` vẫn tồn tại.
- `search_vector` cũng chiếm dung lượng.
- GIN index trên vector chiếm thêm dung lượng.

So với expression index-only, đó là đánh đổi **lưu thêm vector để query đơn giản và tránh tính vector nhiều lần trong một số workload**.

### 17.4. UPDATE không đổi source vẫn có chi phí

Với custom trigger `BEFORE INSERT OR UPDATE` không giới hạn cột, UPDATE `updated_at` vẫn gọi function tính vector. Có thể tối ưu theo cột hoặc thay đổi thực khi workload chứng minh cần thiết, nhưng phải bảo vệ việc không tạo stale vectors.

### 17.5. Theo dõi index usage và dung lượng

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'fts_refresh_lab'
ORDER BY relname, indexrelname;
```

`idx_scan` là thống kê tích lũy, không phải bằng chứng tự động rằng một index “không dùng bao giờ”. Hãy xem cửa sổ quan sát và workload thật.

### 17.6. Kiểm tra kích thước bảng/index

```sql
SELECT
    c.oid::regclass AS object_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS bytes_pretty
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'fts_refresh_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

Khi đổi từ expression index sang stored column, so sánh **tổng chi phí table + index**, không chỉ kích thước một index.

---

## 18. Khi thay đổi text search dictionary/config

### 18.1. Cùng một text có thể tạo lexeme khác

Nếu thay mapping của text search configuration, các stop words, stem rules hoặc dictionary có thể đổi. Cùng `title/body` nhưng `to_tsvector(config,text)` có thể cho kết quả khác sau migration.

### 18.2. Expression index cần rebuild

Với:

```sql
CREATE INDEX ... USING GIN (
    to_tsvector('pg_catalog.english'::regconfig, ...)
);
```

index chứa mục tra cứu tính theo quy tắc tại thời điểm tạo/cập nhật. Nếu thay định nghĩa config/dictionary mà index phụ thuộc, phải lên kế hoạch **REINDEX hoặc tái tạo index** theo hướng dẫn phù hợp, chứ không giả định index tự chỉnh toàn bộ entries.

### 18.3. Stored generated column cần tính lại vector

Giả sử:

```sql
search_vector GENERATED ALWAYS AS (
  to_tsvector('your_config'::regconfig, ...)
) STORED
```

Thay `your_config` ở catalog không phải là UPDATE mỗi row trong bảng, nên stored values có thể chưa được tính lại. Cần một migration có kế hoạch **recompute data**; chỉ REINDEX trên những vector cũ không tự sinh ra lexemes mới.

### 18.4. Trigger-maintained column tương tự

Nếu trigger function đổi logic hoặc config, PostgreSQL không tự chạy lại trigger trên toàn bộ hàng cũ. Chỉ những rows được INSERT/UPDATE theo điều kiện trigger mới được cập nhật. Hãy backfill theo lô trước khi coi search index có semantics mới hoàn chỉnh.

### 18.5. Đừng âm thầm đổi language config

Khi cần chuyển đổi toàn hệ thống từ `english` sang một cấu hình tùy biến:

1. Chốt nghiệp vụ, từ điển và test cases.
2. Đánh giá query terms được parse thế nào.
3. Chọn chiến lược update/rebuild.
4. Theo dõi progress và WAL/disk.
5. Đối chiếu kết quả search cũ/mới.
6. Chỉ chuyển traffic sau khi xác nhận vector/index mới sẵn sàng.

Đổi cấu hình FTS là **thay đổi semantics tìm kiếm**, không chỉ tuning SQL.

---

## 19. Search query phía ứng dụng: tránh sai config và SQL injection

### 19.1. Sử dụng tsquery function phù hợp

Các hàm hay dùng:

| Hàm | Ý nghĩa |
|---|---|
| `plainto_tsquery(config, text)` | Văn bản bình thường, các từ có logic tìm kiếm cơ bản |
| `phraseto_tsquery(config, text)` | Tạo truy vấn theo thứ tự/khoảng từ |
| `websearch_to_tsquery(config, text)` | Cú pháp gần công cụ web: dấu nháy, `OR`, loại từ |
| `to_tsquery(config, text)` | Cú pháp tsquery rõ toán tử, mạnh nhưng yêu cầu input hợp lệ |

### 19.2. Không ghép string vào SQL

Không làm:

```java
// KHÔNG AN TOÀN:
// String sql = "SELECT * FROM articles WHERE search_vector @@ "
//            + "to_tsquery('english', '" + userInput + "')";
```

Thay bằng parameter:

```sql
SELECT article_id, title
FROM fts_refresh_lab.articles_generated
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english'::regconfig,
    $1
);
```

`$1` là placeholder dùng trong prepared statement PostgreSQL; JDBC dùng `?`.

### 19.3. Java JDBC

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ArticleSearchRepository {
    public void search(Connection connection, String keywords)
            throws SQLException {
        String sql = """
            SELECT article_id, title
            FROM fts_refresh_lab.articles_generated
            WHERE search_vector @@ websearch_to_tsquery(
                'pg_catalog.english'::regconfig,
                ?
            )
            ORDER BY article_id DESC
            LIMIT 20
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setString(1, keywords);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("article_id");
                    String title = rs.getString("title");
                    // Đưa dữ liệu qua lớp ứng dụng phù hợp.
                }
            }
        }
    }
}
```

Ví dụ dùng Java text block (Java 15+). Ở tầng ứng dụng thực, cần bổ sung giới hạn quyền/tenant, timeout, kiểm tra query rỗng/quá dài, phân trang và xử lý kết quả theo hợp đồng.

### 19.4. Search ranking có thể gây tải

Một query `ts_rank(...) ORDER BY score DESC LIMIT 20` vẫn có thể cần tính rank cho hàng chục nghìn candidate nếu query rất phổ biến. Dùng:

- Bộ lọc tenant/status/time nếu hợp lệ.
- Giới hạn query input.
- Chỉ trả cột cần thiết.
- Thống kê và GIN phù hợp.
- Đo tính chọn lọc và thời gian end-to-end.

Không thêm LIMIT rồi mặc định database chỉ phải xem 20 hàng.

### 19.5. Highlighting cần escape phù hợp

`ts_headline` có thể tạo đoạn trích với đánh dấu từ tìm kiếm. Nếu trả về HTML hoặc cho phép markup, phải xem xét escaping/XSS và nội dung do người dùng nhập. Một chuỗi đã được `ts_headline` xử lý **không tự trở thành HTML an toàn** khi render.

---

## 20. Lỗi thường gặp khi cập nhật tsvector

**1. “Tạo GIN index rồi vẫn phải viết trigger cập nhật index.”** Không với expression index: PostgreSQL tự duy trì index khi dữ liệu nguồn thay đổi.

**2. “Expression index lưu một cột tsvector mà SELECT có thể đọc bằng tên.”** Không. Index expression khác cột stored generated.

**3. “Stored generated column phải có trigger đi kèm để cập nhật.”** Không. PostgreSQL tính generated expression khi ghi.

**4. “Trigger built-in tự cho trọng số A cho title, D cho body.”** Không. Muốn weighting phân biệt cần generated expression hoặc custom logic.

**5. “`to_tsvector(text)` là lựa chọn chắc chắn immutable cho index.”** Không. Nó phụ thuộc default config.

**6. “Không cần nêu text search config trong query.”** Dễ gây lệch lexemes giữa document/query khi sessions dùng config khác nhau.

**7. “`body=NULL` không ảnh hưởng việc nối `title||body`.”** Sai. Nối chuỗi với SQL NULL có thể trả NULL.

**8. “Vector rỗng luôn chứng minh trigger bị lỗi.”** Không. Stop words hoặc tài liệu rỗng có thể tạo vector rỗng hợp lệ.

**9. “`concat_ws` luôn immutable trong mọi expression index.”** Không. Không nên giả định.

**10. “Có GIN trên vector thì mọi tìm kiếm trả theo rank.”** Sai. GIN lọc, ranking/sorting là phần việc khác.

**11. “`@@` tự sắp xếp theo độ liên quan.”** Không. Cần `ts_rank`/`ts_rank_cd` và `ORDER BY`.

**12. “ts_rank là xác suất chính xác.”** Không. Là thước đo ranking tương đối.

**13. “Trọng số trong tsvector được GIN lưu đầy đủ để không cần recheck.”** Không. Một số weight restrictions cần xác minh lại trên vector.

**14. “UPDATE title của generated column không đổi vector.”** Sai. Vector được tính lại khi row được ghi.

**15. “Có trigger UPDATE thì dữ liệu cũ trước ngày tạo trigger tự được backfill.”** Sai. Cần migration/backfill.

**16. “Trigger UPDATE OF title chỉ chạy khi giá trị title thật sự đổi.”** Sai. Phụ thuộc danh sách cột SET.

**17. “UPDATE OF title sẽ luôn chạy nếu trigger khác sửa NEW.title.”** Không bảo đảm; column-specific firing dựa vào statement target list.

**18. “Nhiều BEFORE triggers chạy theo thứ tự ngẫu nhiên.”** PostgreSQL có quy tắc theo tên trong cùng loại; phải thiết kế phụ thuộc rõ.

**19. “Chỉ đổi search_config không cần cập nhật vector.”** Sai nếu config làm thay lexemes.

**20. “Có thể sửa tsvector generated bằng UPDATE như cột bình thường.”** Không. Nó được điều khiển bởi generated expression.

**21. “Trigger RETURN NULL trong BEFORE ROW luôn vô hại.”** Không. Nó có thể bỏ qua xử lý row hiện tại theo semantics trigger; function mẫu dùng `RETURN NEW`.

**22. “Thay đổi dictionary/config tự cập nhật mọi stored vectors.”** Không. Cần kế hoạch recompute/reindex phù hợp.

**23. “Chạy REINDEX trên stored tsvector cũ tự thay lexeme trong cột.”** Sai. REINDEX không tính lại giá trị đã lưu.

**24. “Tạo expression index với english thì query dùng simple vẫn giống.”** Sai. Từ điển/stop words/stemming khác.

**25. “FTS tiếng Anh tự hiểu tiếng Việt đầy đủ.”** Không. Cần tách từ/normalization và đánh giá chất lượng riêng.

**26. “Thêm generated column vào bảng trăm triệu rows chắc chắn không tốn lock/rewrite.”** Không nên giả định. Cần xem phiên bản, migration plan và tài nguyên.

**27. “CREATE INDEX CONCURRENTLY chạy được trong BEGIN.”** Không.

**28. “CONCURRENTLY không cần giám sát I/O/WAL và invalid index.”** Sai. Vẫn có chi phí và tình huống lỗi.

**29. “Trigger bật nghĩa là mọi đường nhập dữ liệu chắc chắn đã chạy trigger.”** Không nên mặc định nếu có replication/import/bypass trigger hoặc job cũ.

**30. “Chỉ cần so length(tsvector) để biết vector đúng.”** Không. Có thể cùng độ dài nhưng lexemes khác.

**31. “GIN index làm UPDATE JSON/text miễn phí.”** Không. Duy trì lexemes/positions và index có chi phí ghi.

**32. “Tiêu đề trọng số A luôn giúp tìm được tài liệu dù query không có lexeme.”** Không. Weight ảnh hưởng ranking/restrictions, không tạo từ không tồn tại.

**33. “Để tránh trigger, có thể bỏ mọi constraints và dùng JSONB chứa tất cả field.”** Không. Tính toàn vẹn/typed columns và FTS là vấn đề khác nhau.

**34. “UPDATE last_seen phải chạy trigger FTS để bảo đảm mới nhất.”** Không hẳn. Nếu nguồn search không đổi, có thể tối ưu, nhưng bảo vệ invariant.

**35. “SQL query tìm được vài rows là đủ chứng minh FTS tốt.”** Không. Cần đo chất lượng, sự nhất quán, latency, dữ liệu NULL/đa ngôn ngữ và corner cases.

**36. “Trigger tự chạy khi bảng liên quan khác đổi nội dung.”** Không. Trigger trên một bảng chỉ phản ứng với event của bảng đó; denormalization đa bảng cần workflow riêng.

---

## 21. Bài tập thực hành và đáp án

### Bài 1 — Phân biệt text search và LIKE

**Câu hỏi:** `body ILIKE '%search%'` và `to_tsvector(body) @@ plainto_tsquery('search')` có luôn cùng tập kết quả không?

**Đáp án:** Không. LIKE tìm substring theo quy tắc so sánh chuỗi; FTS chuẩn hóa token/lexeme theo configuration và đánh giá tsquery.

### Bài 2 — Cú pháp tsvector có config tường minh

**Yêu cầu:** tạo vector tiếng Anh từ văn bản `'Running searches'`.

```sql
SELECT to_tsvector(
    'pg_catalog.english'::regconfig,
    'Running searches'
);
```

### Bài 3 — Vì sao không dùng to_tsvector(text) trong expression index?

**Đáp án:** Biến thể một tham số phụ thuộc `default_text_search_config`, không thỏa yêu cầu immutability của index expression.

### Bài 4 — Biểu thức NULL-safe

**Yêu cầu:** nối title/body nullable cho FTS mà không làm mất title nếu body NULL.

```sql
to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title,'') || ' ' || coalesce(body,'')
)
```

### Bài 5 — Tạo expression index

**Đáp án:**

```sql
-- Mẫu tương đương với index lab đã tạo.
CREATE INDEX exercise_articles_expr_gin
ON fts_refresh_lab.articles_expr
USING GIN (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        coalesce(title,'') || ' ' || coalesce(body,'')
    )
);
```

Không giữ hai index trùng expression trong production; câu DDL chỉ để luyện cú pháp.

### Bài 6 — Có cần trigger cho expression index?

**Đáp án:** Không. PostgreSQL duy trì index expression khi các rows được INSERT/UPDATE theo cơ chế index maintenance.

### Bài 7 — Query khớp index expression

**Đáp án:**

```sql
SELECT article_id
FROM fts_refresh_lab.articles_expr
WHERE to_tsvector(
    'pg_catalog.english'::regconfig,
    coalesce(title,'') || ' ' || coalesce(body,'')
) @@ plainto_tsquery(
    'pg_catalog.english'::regconfig,
    'database indexing'
);
```

### Bài 8 — Vì sao chỉ index title không tương đương title + body?

**Đáp án:** Hai expression keys khác nhau và tập lexeme khác. Query chỉ gọi `to_tsvector(config,title)` không tự khớp index expression từ cả title/body.

### Bài 9 — Cột generated STORED

**Yêu cầu:** nêu ưu điểm chính so với expression-index-only.

**Đáp án:** Schema lưu `search_vector` được tính tự động; SQL có thể dùng `WHERE search_vector @@ query` và `ts_rank(search_vector,query)` mà không phải lặp lại toàn bộ biểu thức nguồn.

### Bài 10 — Weight title và body

```sql
setweight(
  to_tsvector('pg_catalog.english'::regconfig,
              coalesce(title,'')), 'A'
)
||
setweight(
  to_tsvector('pg_catalog.english'::regconfig,
              coalesce(body,'')), 'D'
)
```

**Đáp án:** Tiêu đề được đánh trọng số A, body trọng số D; hỗ trợ ranking ưu tiên title khi dùng hàm rank phù hợp.

### Bài 11 — Update generated vector

**Câu hỏi:** sau `UPDATE articles_generated SET body='new content'` có phải UPDATE riêng `search_vector`?

**Đáp án:** Không. PostgreSQL tự tính stored generated column từ dữ liệu row mới.

### Bài 12 — Viết trigger built-in

**Đáp án:**

```sql
CREATE TRIGGER exercise_tsvector_refresh
BEFORE INSERT OR UPDATE
ON fts_refresh_lab.articles_builtin_trigger
FOR EACH ROW
EXECUTE FUNCTION pg_catalog.tsvector_update_trigger(
    search_vector,
    'pg_catalog.english',
    title,
    body
);
```

Lab đã có trigger tương tự; không cần tạo hai trigger bảo trì cùng vector. Mẫu chỉ dùng để học cú pháp.

### Bài 13 — Built-in trigger và weight

**Câu hỏi:** Built-in `tsvector_update_trigger` theo cú pháp trên có tự đặt A cho title không?

**Đáp án:** Không theo cấu hình đơn giản ấy. Muốn weighting khác nhau, dùng generated expression hoặc custom trigger.

### Bài 14 — Trigger phải RETURN gì?

**Đáp án:** Với BEFORE ROW INSERT/UPDATE trigger cập nhật vector, function trả `NEW` để row đã được gán vector tiếp tục được ghi. `RETURN NULL` có semantics có thể bỏ qua row operation.

### Bài 15 — Đổi cấu hình theo row

**Câu hỏi:** Vì sao trigger chỉ `UPDATE OF title, body` có thể sai nếu thêm cột `search_config`?

**Đáp án:** Khi `search_config` đổi mà title/body không nằm trong SET list, trigger có thể không chạy, làm vector giữ lexemes theo config cũ. Phải bao gồm config trong dependency hoặc dùng trigger mọi UPDATE.

### Bài 16 — UPDATE OF vs actual value change

```sql
UPDATE fts_refresh_lab.articles_weighted_trigger
SET title = title
WHERE article_id = 1;
```

**Đáp án:** Trigger `UPDATE OF title` vẫn có thể chạy vì title xuất hiện trong SET list, dù giá trị không đổi.

### Bài 17 — Hai BEFORE triggers

Một trigger chuẩn hóa title chạy **sau** trigger FTS.

**Đáp án:** Có nguy cơ search_vector không khớp title cuối cùng; cần tổ chức thứ tự hoặc dùng generated expression được tính sau BEFORE triggers, tùy yêu cầu.

### Bài 18 — Trigger trên bảng chính và thay đổi bảng phụ

**Câu hỏi:** Comment được sửa trong bảng comments có tự kích hoạt trigger FTS của articles không?

**Đáp án:** Không. Trigger của articles chỉ theo event trên articles; cần workflow đồng bộ từ comments nếu search vector bao gồm comments.

### Bài 19 — Trigger mới có tự backfill rows cũ?

**Đáp án:** Không. Phải tính lại các rows cũ theo batch, rồi kiểm tra vector, index và trạng thái rollout.

### Bài 20 — Vì sao không đánh dấu vector rỗng là chưa backfill?

**Đáp án:** Tài liệu trống hoặc chỉ có stop words có thể sinh vector rỗng hợp lệ. Dùng migration marker/NULL theo thiết kế thay vì đoán từ độ dài vector.

### Bài 21 — Kiểm tra stale vector

**Đáp án:** So `search_vector IS DISTINCT FROM <biểu thức xây vector tương ứng>` trên dữ liệu được chọn; khác biệt cho biết có vấn đề đồng bộ hoặc thay đổi cấu hình/logic.

### Bài 22 — Thay đổi dictionary

**Câu hỏi:** REINDEX GIN trên một stored tsvector cũ có tự biến đổi lexeme trong cột không?

**Đáp án:** Không. Phải recompute dữ liệu vector; index được cập nhật theo. Với expression index từ title/body, rebuild index theo config mới là phần cần thiết.

### Bài 23 — Xếp hạng

**Đáp án:**

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english'::regconfig,
        'search ranking'
    ) AS terms
)
SELECT
    a.article_id,
    ts_rank(a.search_vector, q.terms) AS score
FROM fts_refresh_lab.articles_generated AS a
CROSS JOIN q
WHERE a.search_vector @@ q.terms
ORDER BY score DESC, a.article_id DESC;
```

### Bài 24 — GIN có thứ tự rank?

**Đáp án:** Không. GIN giúp tìm candidate rows. `ts_rank` và `ORDER BY` vẫn là công việc riêng.

### Bài 25 — Tại sao ts_rank_cd quan tâm positions?

**Đáp án:** Hàm *cover-density ranking* dùng khoảng cách/vị trí của lexemes để đánh giá mức độ xuất hiện gần nhau; việc loại bỏ positions bằng `strip()` có thể hạn chế ý nghĩa.

### Bài 26 — Migration bảng 10 triệu rows

**Đáp án gợi ý:** Chốt biểu thức/config, tạo trigger cho writes mới nếu dùng cột thường, backfill batches, kiểm tra inconsistency/NULL, tạo GIN concurrently ngoài transaction, kiểm tra index validity và chuyển read traffic từng giai đoạn. Với generated column, đánh giá chi phí backfill/rewrite trước.

### Bài 27 — CREATE INDEX CONCURRENTLY trong BEGIN

**Câu hỏi:** Có hợp lệ không?

**Đáp án:** Không. `CREATE INDEX CONCURRENTLY` phải chạy ngoài transaction block tường minh; migration runner cần cấu hình phù hợp.

### Bài 28 — Khi nào chọn expression index?

**Đáp án:** Khi biểu thức đơn giản, immutable với config tường minh, không cần một cột tsvector để rank/inspect thường xuyên, và muốn PostgreSQL tự bảo trì index mà không có trigger.

### Bài 29 — Khi nào chọn generated column?

**Đáp án:** Khi muốn vector có tên cột rõ ràng, ranking/truy vấn gọn, trọng số định nghĩa trong schema, và chấp nhận lưu vector + migration cost của stored generated column.

### Bài 30 — Khi nào chọn custom trigger?

**Đáp án:** Khi có logic cập nhật phức tạp, cần kiểm soát config theo row, điều kiện ghi đặc thù hoặc migration tương thích; phải chịu trách nhiệm theo dõi stale vector, dependency, trigger order và backfill.

### Bài 31 — English vs simple

**Câu hỏi:** Có thể dùng `english` để lập vector nhưng `simple` cho tsquery mà coi kết quả tương đương không?

**Đáp án:** Không. Lexemes khác nhau do stemming/stop words; chọn config theo hợp đồng tìm kiếm và dùng nhất quán hai phía.

### Bài 32 — Tác dụng phụ của EXPLAIN ANALYZE

**Câu hỏi:** Có an toàn khi chạy `EXPLAIN ANALYZE UPDATE articles...` để “chỉ xem index” không?

**Đáp án:** Không. Lệnh UPDATE **chạy thật**, trigger cũng có thể thực thi. Dùng `EXPLAIN UPDATE` không `ANALYZE` hoặc đo trên database thử nghiệm.

---

## 22. Checklist chọn và vận hành cơ chế cập nhật tsvector

### Thiết kế semantics

1. **Nguồn tìm kiếm là gì?** Title/body/tags/comments hay bảng khác?
2. **Ngôn ngữ/cấu hình?** `english`, `simple` hay dictionary tùy biến?
3. **Có chuẩn hóa nhất quán?** Config của document và tsquery có khớp?
4. **NULL?** `coalesce` có bảo đảm title không bị mất khi body NULL?
5. **Trọng số?** Title A, body D hay một chiến lược khác?
6. **Cần positions?** Phrase search/rank cover-density có yêu cầu không?
7. **Có nhiều ngôn ngữ?** Query sẽ dùng config nào cho từng nhóm hàng?

### Chọn nơi bảo trì vector

8. **Expression GIN** nếu chỉ cần đường tìm kiếm trên biểu thức immutable.
9. **Stored generated** nếu muốn cột vector có tên, tính tự động và ranking dễ dùng.
10. **Built-in trigger** nếu cần cập nhật cột vector thường từ các trường text, config đơn giản.
11. **Custom trigger** nếu cần trọng số/quy tắc điều kiện linh hoạt.
12. **Không nhân bản** nhiều cơ chế cùng tính một vector nếu không có lý do.
13. **Không khai báo sai IMMUTABLE** để lách quy tắc.

### Cập nhật đúng

14. Trigger có bao gồm **INSERT và UPDATE**?
15. Nếu dùng `UPDATE OF`, đã liệt kê cả **cột config/phụ thuộc**?
16. Có trigger khác chỉnh title/body không? Thứ tự chạy thế nào?
17. Trigger function có `RETURN NEW` và xử lý NULL đúng không?
18. Application/bulk load có thể bypass trigger hoặc sửa search_vector trực tiếp không?
19. Khi thay đổi dictionary/config, có kế hoạch recompute/reindex không?
20. Dữ liệu cũ có được backfill theo batches và kiểm tra không?

### Chỉ mục và hiệu năng

21. GIN trên **đúng expression/cột** mà truy vấn dùng?
22. Có `EXPLAIN`/`EXPLAIN ANALYZE` trên SELECT an toàn và dữ liệu đại diện?
23. Query FTS có match quá nhiều hàng, làm ranking/sort tốn chi phí không?
24. Có đo GIN storage, write amplification, WAL, pending list không?
25. Có dùng `CREATE INDEX CONCURRENTLY` ngoài transaction khi cần triển khai online?
26. Có kiểm tra `indisvalid`/`indisready` sau index build không?
27. Có theo dõi stale vector và query quality sau rollout không?
28. Có đánh giá cả API latency, permissions/RLS, tenant filter và SQL injection không?

---

## 23. Tổng kết

Mục đích của `tsvector` là biến văn bản thành cấu trúc lexeme mà PostgreSQL có thể tìm bằng `tsquery` và toán tử `@@`. Đối với hệ thống có dữ liệu liên tục thay đổi, **phần quan trọng không kém chỉ mục là bảo đảm vector phản ánh đúng nội dung hiện tại**.

Hãy nhớ ba lựa chọn:

- **Expression index**: `GIN (to_tsvector(config, title/body))` tự được PostgreSQL duy trì, không cần cột `tsvector` và không cần trigger. Query cần dùng biểu thức phù hợp. Đây thường là điểm khởi đầu tốt khi biểu thức đơn giản.
- **Stored generated column**: `search_vector TSVECTOR GENERATED ALWAYS AS (...) STORED` lưu vector và tự tính khi INSERT/UPDATE. Dễ viết `search_vector @@ query` và `ts_rank(search_vector, query)`, hỗ trợ `setweight` để ưu tiên title/body. Đánh đổi thêm lưu trữ và chi phí migration khi bảng lớn.
- **Trigger**: `tsvector_update_trigger` hoặc custom `BEFORE INSERT OR UPDATE` gán `NEW.search_vector`. Linh hoạt nhất cho logic riêng nhưng dễ sinh stale vector nếu thiếu event, config đổi, trigger bị tắt hoặc dữ liệu cũ chưa backfill.

Các nguyên tắc để duy trì sự chính xác:

1. **Chỉ rõ text search configuration** ở cả vector và tsquery.
2. Dùng **`coalesce`** khi nguồn text có thể NULL.
3. Nếu cần trọng số, dùng **`setweight` riêng từng nguồn rồi nối vector**.
4. Không coi trigger được tạo sau này là cơ chế tự backfill quá khứ.
5. Khi đổi dictionary/config/logic vector, lập kế hoạch **recompute/reindex** phù hợp từng cơ chế.
6. GIN hỗ trợ tìm kiếm, **không tự sắp xếp theo relevance**.
7. Đo hiệu năng trong điều kiện đại diện, nhưng nhớ `EXPLAIN ANALYZE` **thực thi statement**.

**Câu hỏi cuối cùng trước khi triển khai:** “Nếu người dùng sửa tiêu đề lúc 10:00, lúc 10:01 hệ thống sẽ đọc lexeme mới từ đâu? PostgreSQL tự cập nhật expression index, tự tính generated column, hay có một trigger đáng tin cậy? Những hàng cũ và những trường hợp thay đổi config đã được xử lý chưa?”

### Tài liệu PostgreSQL chính thức

- [Text Search — Introduction](https://www.postgresql.org/docs/current/textsearch-intro.html).
- [Text Search — Tables and Indexes](https://www.postgresql.org/docs/current/textsearch-tables.html).
- [Text Search — Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html).
- [Text Search — Ranking Search Results](https://www.postgresql.org/docs/current/textsearch-controls.html#TEXTSEARCH-RANKING).
- [Text Search — Indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html).
- [Text Search — Updating tsvector, Stored Generated Columns and Triggers](https://www.postgresql.org/docs/current/textsearch-features.html).
- [Text Search Functions and Operators](https://www.postgresql.org/docs/current/functions-textsearch.html).
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html).
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
