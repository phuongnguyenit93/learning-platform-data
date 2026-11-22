# Phân biệt tìm chính xác, theo tiền tố, mẫu và toàn văn trong PostgreSQL

Khi người dùng nhập từ khóa vào ô tìm kiếm, câu hỏi đầu tiên **không phải “dùng index nào?”**, mà là **“người dùng muốn tìm theo quy tắc khớp nào?”**. PostgreSQL có nhiều cách tìm văn bản, mỗi cách trả lời một loại câu hỏi khác nhau.

Giả sử một ứng dụng quản lý bài viết có tiêu đề:

- `PostgreSQL cơ bản`
- `PostgreSQL nâng cao`
- `Tối ưu hiệu năng PostgreSQL`
- `Giới thiệu SQL`
- `Cơ sở dữ liệu quan hệ`

Nếu người dùng nhập `PostgreSQL`, các cách hiểu có thể khác hẳn:

1. **Tìm chính xác:** tiêu đề phải bằng đúng chuỗi `PostgreSQL`.
2. **Tìm theo tiền tố:** tiêu đề phải **bắt đầu bằng** `PostgreSQL`.
3. **Tìm theo mẫu:** tiêu đề chứa `PostgreSQL` ở bất kỳ vị trí nào, hoặc đáp ứng một biểu thức như “bắt đầu bằng A và kết thúc bằng B”.
4. **Tìm toàn văn (*full-text search*)**: phân tích tiêu đề và nội dung thành các từ khóa (*lexeme*), rồi tìm các tài liệu có từ liên quan theo quy tắc ngôn ngữ, kết hợp AND/OR, cụm từ và thứ hạng liên quan.

Các truy vấn PostgreSQL điển hình:

```sql
-- 1. Khớp toàn bộ giá trị theo phép so sánh =
WHERE title = 'PostgreSQL'

-- 2. Khớp tiền tố của toàn bộ chuỗi
WHERE title LIKE 'PostgreSQL%'

-- 3. Khớp mẫu/chuỗi con, không phân biệt hoa-thường
WHERE title ILIKE '%postgresql%'

-- 4. Tìm toàn văn trên tsvector
WHERE search_vector @@ plainto_tsquery('simple', 'PostgreSQL')
```

Đây là những **biểu thức WHERE minh họa**, không phải bốn statement đầy đủ. Dù người dùng nhập cùng một từ, **ngữ nghĩa, tập kết quả, khả năng dùng index và chi phí thực thi có thể khác nhau rất nhiều**.

Bài học sẽ giải thích cách lựa chọn, triển khai và đo hiệu năng cho từng kiểu tìm trong **PostgreSQL**, đặc biệt ở ứng dụng Java/JDBC, API tìm kiếm và dữ liệu tiếng Việt.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt chính xác các nghĩa của **khớp toàn bộ chuỗi, khớp tiền tố, khớp mẫu, khớp từ và tìm toàn văn**.
2. Dùng `=`, `LIKE`, `ILIKE`, `SIMILAR TO` và các toán tử regex `~`, `~*` một cách đúng ngữ nghĩa.
3. Hiểu wildcard `%`, `_`, ký tự escape và các trường hợp người dùng nhập dấu phần trăm/gạch dưới như dữ liệu thật.
4. Giải thích vì sao B-tree index phù hợp với equality/prefix nhưng thường không giúp trực tiếp cho mẫu `'%keyword%'`.
5. Dùng `text_pattern_ops`, expression index trên `lower(...)` và khi phù hợp có thể cân nhắc `citext`.
6. Dùng `pg_trgm` với GIN/GiST cho substring search, `ILIKE`, regex và tìm tương đồng.
7. Dùng PostgreSQL Full-Text Search (FTS): `to_tsvector`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`, `to_tsquery` và toán tử `@@`.
8. Xây dựng cột `tsvector` sinh tự động, GIN index và xếp hạng với `ts_rank`/`ts_rank_cd`.
9. Nhận biết hạn chế của cấu hình `simple` với tiếng Việt, dấu, chữ hoa, tách từ và chính sách chuẩn hóa.
10. Dùng parameter binding an toàn, không biến chuỗi tìm kiếm của người dùng thành SQL hoặc regex không kiểm soát.
11. Đọc `EXPLAIN (ANALYZE, BUFFERS)` để kiểm tra index, filter, cardinality và chi phí.
12. Thiết kế API tìm kiếm có phân trang, ranking, giới hạn tài nguyên và kiểm thử ngữ nghĩa.

## 2. Bản đồ bốn kiểu tìm

| Kiểu | Ý định | Biểu thức PostgreSQL | Ví dụ khớp với input `PostgreSQL` |
| --- | --- | --- | --- |
| **Chính xác** | Cả giá trị bằng chuỗi | `title = 'PostgreSQL'` | Chỉ giá trị tương đương theo quy tắc so sánh/collation |
| **Tiền tố** | Chuỗi bắt đầu bằng từ khóa | `title LIKE 'PostgreSQL%'` | `PostgreSQL cơ bản` |
| **Mẫu** | Vị trí/khuôn mẫu ký tự | `title ILIKE '%postgresql%'` hoặc regex | `Tối ưu PostgreSQL` |
| **Toàn văn** | Từ và ý nghĩa biểu thức tìm | `search_vector @@ plainto_tsquery(...)` | Tài liệu chứa lexeme `postgresql` trong title/body |

### 2.1. Không có toán tử “tìm tốt nhất” cho mọi trường hợp

- **Mã hàng, mã đơn, username định danh:** thường dùng `=`.
- **Autocomplete theo đầu mã/tiêu đề:** thường dùng `LIKE 'abc%'` với key/index phù hợp.
- **Tra chuỗi con trong mã hoặc tiêu đề:** thường cần `ILIKE '%abc%'`/`LIKE '%abc%'` và có thể dùng `pg_trgm`.
- **Tìm bài viết theo nội dung nhiều từ, có liên quan và ranking:** thường bắt đầu từ FTS.

Nếu người dùng nhập một từ không đầy đủ ở giữa chuỗi, FTS không tự giải quyết mọi trường hợp; nếu cần tìm các từ có nghĩa trong bài viết, `LIKE '%...%'` cũng không tự có stemming, stop words hay ranking thích hợp.

### 2.2. “Chính xác” có thể chỉ ba ý nghĩa khác nhau

Đừng nhầm:

1. **Chính xác toàn bộ chuỗi:** `title = 'SQL'`.
2. **Chính xác một từ trong nội dung:** FTS tìm lexeme `sql` (không đồng nghĩa cả title bằng SQL).
3. **Chính xác một cụm từ:** FTS phrase query, kiểm tra các lexeme theo vị trí/thứ tự, **không bảo đảm chuỗi byte nguyên bản giống hệt**.

Ba yêu cầu này không dùng chung một phép so sánh.

## 3. Chuẩn bị bảng tài liệu cho bài lab

Phần thực hành dùng schema riêng để không ảnh hưởng dữ liệu khác. Các câu lệnh DDL/DML chỉ nên chạy trên **database PostgreSQL thử nghiệm**.

### 3.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS text_search_lab;

CREATE TABLE text_search_lab.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple'::regconfig, COALESCE(title, '')),
            'A'
        ) ||
        setweight(
            to_tsvector('simple'::regconfig, COALESCE(body, '')),
            'B'
        )
    ) STORED
);
```

Cột `search_vector` lưu lexemes của **title** và **body**, gán trọng số **A** cho title và **B** cho body. Cú pháp generated column `STORED` dùng được trong các phiên bản PostgreSQL hiện đại hỗ trợ generated columns. Việc cung cấp cấu hình `'simple'::regconfig` tường minh cho `to_tsvector` giúp biểu thức có tính xác định phù hợp với cột sinh và tránh phụ thuộc `default_text_search_config` của session.

**Lưu ý:** `summary` chưa được đưa vào `search_vector`; đó là lựa chọn thiết kế của lab. Nếu yêu cầu tìm cả summary, cần bổ sung vào biểu thức và đánh giá lại trọng số/chi phí.

### 3.2. Nạp dữ liệu mô phỏng

```sql
INSERT INTO text_search_lab.documents
    (title, summary, body, category, published_at)
VALUES
    (
        'PostgreSQL cơ bản',
        'Giới thiệu PostgreSQL cho người mới',
        'Học tạo bảng, SELECT và các phép JOIN trong PostgreSQL.',
        'database', '2026-01-03 08:00:00+00'
    ),
    (
        'PostgreSQL nâng cao',
        'Tìm hiểu cơ chế nội bộ',
        'Giải thích MVCC, transaction, WAL và cách tối ưu truy vấn.',
        'database', '2026-01-05 08:00:00+00'
    ),
    (
        'Tối ưu PostgreSQL',
        'Phân tích query plan và chỉ mục',
        'Dùng EXPLAIN ANALYZE để đo truy vấn PostgreSQL.',
        'database', '2026-01-10 08:00:00+00'
    ),
    (
        'Postgres và hệ sinh thái',
        'Các công cụ kết nối',
        'Giới thiệu công cụ quản trị PostgreSQL và JDBC.',
        'database', '2026-01-12 08:00:00+00'
    ),
    (
        'Giới thiệu SQL',
        'Câu lệnh SQL nhập môn',
        'SQL cho phép truy vấn dữ liệu từ các bảng quan hệ.',
        'sql', '2026-01-15 08:00:00+00'
    ),
    (
        'SQL nâng cao',
        'CTE và window functions',
        'Học SQL với subquery, CTE, ROW_NUMBER và JOIN.',
        'sql', '2026-01-18 08:00:00+00'
    ),
    (
        'Java JDBC với PostgreSQL',
        'Kết nối Java tới database',
        'PreparedStatement, ResultSet và truy vấn dữ liệu an toàn.',
        'java', '2026-02-01 08:00:00+00'
    ),
    (
        'Học Java căn bản',
        'Biến, kiểu và lớp',
        'Java có class, object và exception handling.',
        'java', '2026-02-03 08:00:00+00'
    ),
    (
        'MySQL và PostgreSQL',
        'So sánh hai hệ quản trị',
        'Cả MySQL và PostgreSQL đều hỗ trợ SQL.',
        'database', '2026-02-08 08:00:00+00'
    ),
    (
        'Tìm kiếm toàn văn',
        'Giới thiệu full text search',
        'PostgreSQL hỗ trợ tsvector, tsquery và chỉ mục GIN.',
        'search', '2026-02-11 08:00:00+00'
    ),
    (
        'Tìm kiếm tiền tố',
        'Gợi ý tìm kiếm qua LIKE',
        'LIKE với dấu phần trăm ở cuối có thể tìm theo tiền tố.',
        'search', '2026-02-14 08:00:00+00'
    ),
    (
        'Mẫu và biểu thức chính quy',
        'LIKE, ILIKE và regex',
        'Biểu thức chính quy giúp khớp cấu trúc của chuỗi.',
        'search', '2026-02-17 08:00:00+00'
    ),
    (
        '50% tối ưu SQL',
        'Dấu phần trăm là dữ liệu',
        'Một tiêu đề chứa ký tự phần trăm đúng nghĩa.',
        'sql', '2026-03-01 08:00:00+00'
    ),
    (
        'Mã A_B trong hệ thống',
        'Dấu gạch dưới là dữ liệu',
        'Tên mã chứa dấu gạch dưới cần escape khi dùng LIKE.',
        'search', '2026-03-03 08:00:00+00'
    ),
    (
        'postgresql không viết hoa',
        'So sánh phân biệt hoa thường',
        'Cách dùng ILIKE và lower để tìm tiêu đề.',
        'database', '2026-03-05 08:00:00+00'
    ),
    (
        'Hiệu năng truy vấn',
        'Đọc EXPLAIN và chỉ mục',
        'Index Scan có thể nhanh hơn Seq Scan với điều kiện phù hợp.',
        'database', '2026-03-07 08:00:00+00'
    ),
    (
        'Chỉ mục GIN',
        'Cấu trúc chỉ mục chuyên biệt',
        'GIN hỗ trợ full text search và nhiều kiểu dữ liệu khác.',
        'database', '2026-03-10 08:00:00+00'
    ),
    (
        'Tìm kiếm gần đúng',
        'Trigram và similarity',
        'pg_trgm có thể giúp tìm chuỗi con và chuỗi gần giống.',
        'search', '2026-03-12 08:00:00+00'
    ),
    (
        'Phân tích tiếng Việt',
        'Từ ghép và dấu thanh',
        'Tìm kiếm tiếng Việt cần chính sách chuẩn hóa và phân tích từ.',
        'search', '2026-03-15 08:00:00+00'
    ),
    (
        'PostgreSQL backup',
        'Sao lưu và phục hồi',
        'pg_dump và PITR là các cách phục hồi theo nhu cầu.',
        'database', '2026-03-20 08:00:00+00'
    ),
    (
        'SQL injection là gì?',
        'Tham số hóa câu SQL',
        'Dùng PreparedStatement, không nối input vào SQL.',
        'security', '2026-03-22 08:00:00+00'
    ),
    (
        'Khóa và transaction',
        'Cơ chế khóa trong database',
        'Transaction isolation và deadlock ảnh hưởng cạnh tranh.',
        'database', '2026-03-24 08:00:00+00'
    ),
    (
        'Tài liệu không có PostgreSQL trong tiêu đề',
        'Chỉ đề cập công nghệ trong summary',
        'Nội dung body nói về JSONB, MVCC và locking.',
        'database', '2026-03-26 08:00:00+00'
    ),
    (
        'Tài liệu về cấu trúc dữ liệu',
        'Không nhắc tới các hệ quản trị cụ thể',
        'Giải thích cây, danh sách liên kết và thuật toán.',
        'algorithm', '2026-03-30 08:00:00+00'
    );
```

### 3.3. Thống kê sau khi nạp

```sql
ANALYZE text_search_lab.documents;

SELECT
    COUNT(*) AS document_count,
    COUNT(*) FILTER (WHERE category = 'search')
        AS search_category_count
FROM text_search_lab.documents;
```

Bộ dữ liệu có **24 tài liệu giả**, đủ để quan sát ngữ nghĩa. Trên bảng nhỏ như vậy, planner có thể ưu tiên `Seq Scan` ngay cả khi ta tạo index. **Không ép kết luận hiệu năng từ 24 hàng**; các index được minh họa để hiểu thiết kế, còn benchmark cần tập dữ liệu đại diện.

## 4. Tìm chính xác bằng dấu bằng

Truy vấn:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL cơ bản';
```

Yêu cầu ở đây là **toàn bộ giá trị title khớp theo phép so sánh `=`**, không phải chỉ chứa một từ.

### 4.1. Khác gì với tìm chứa chuỗi?

```sql
-- So sánh cả chuỗi:
WHERE title = 'PostgreSQL'

-- Bắt đầu bằng chuỗi:
WHERE title LIKE 'PostgreSQL%'

-- Có chuỗi con ở bất kỳ vị trí:
WHERE title LIKE '%PostgreSQL%'
```

Ví dụ tiêu đề `PostgreSQL cơ bản`:

| Điều kiện | Có khớp? |
| --- | :---: |
| `title = 'PostgreSQL'` | Không |
| `title = 'PostgreSQL cơ bản'` | Có |
| `title LIKE 'PostgreSQL%'` | Có |
| `title LIKE '%PostgreSQL%'` | Có |
| `title = 'postgresql cơ bản'` theo so sánh phân biệt case thông thường | Không |

Sự tương đương chính xác theo `=` chịu ảnh hưởng của **kiểu dữ liệu và collation**. Với các collations xác định thông dụng, khác chữ hoa/thường hoặc khác dấu thường không được coi là bằng nhau; nhưng PostgreSQL còn có các cấu hình collation đặc biệt. Đừng thiết kế yêu cầu “so byte tuyệt đối” mà bỏ qua collation, Unicode normalization hoặc kiểu `CHAR(n)`.

### 4.2. Dùng B-tree index

```sql
CREATE INDEX idx_lab_documents_title_eq
ON text_search_lab.documents (title);
```

Một B-tree index thường là lựa chọn tự nhiên cho equality:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL cơ bản';
```

Trên bảng lớn có tính chọn lọc cao, có thể thấy `Index Scan` hoặc `Bitmap Index Scan`. Trên bảng 24 hàng, `Seq Scan` cũng có thể là lựa chọn tốt.

### 4.3. Tìm theo mã chuẩn hóa

Với mã định danh, thường cần xác định quy tắc:

- Có phân biệt chữ hoa và thường không?
- Có loại khoảng trắng đầu/cuối không?
- Có giữ ký tự Unicode nguyên bản không?
- Có ràng buộc unique theo đúng quy tắc đó không?

Nếu mã được chuẩn hóa ở lúc ghi, một equality query và unique index có thể tốt hơn dùng `ILIKE` trên mỗi lần đọc.

### 4.4. Không nhầm NULL với chuỗi rỗng

```sql
-- Không tìm được các hàng NULL:
WHERE title = NULL

-- Đúng cách kiểm tra NULL:
WHERE title IS NULL

-- Chuỗi rỗng là một giá trị riêng:
WHERE title = ''
```

Ở schema lab, `title NOT NULL`, nhưng trong hệ thống thật sự phân biệt rõ null, empty string và whitespace.

## 5. Tìm không phân biệt chữ hoa/thường ở mức toàn chuỗi

Nếu yêu cầu cả tiêu đề phải khớp nhưng bỏ qua khác biệt về hoa/thường, một lựa chọn đơn giản:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) = lower('POSTGRESQL CƠ BẢN');
```

Hoặc dùng `ILIKE` **không có wildcard**:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'POSTGRESQL CƠ BẢN';
```

Hai cách trên không nên bị hiểu thành **chuẩn hóa Unicode/dấu tiếng Việt toàn diện**. Chúng dựa vào quy tắc case folding/locale của PostgreSQL, và có thể có khác biệt với những chính sách normalize phức tạp mà sản phẩm đặt ra.

### 5.1. Expression index cho lower(title)

```sql
CREATE INDEX idx_lab_documents_title_lower_eq
ON text_search_lab.documents (lower(title));
```

Query phải dùng biểu thức phù hợp:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) = 'postgresql cơ bản';
```

Nếu dùng `WHERE title ILIKE '...'`, không tự suy luận PostgreSQL luôn chuyển nó thành điều kiện trên expression index `lower(title)`. Hãy kiểm tra plan của **biểu thức thực tế**.

### 5.2. CITEXT là lựa chọn khác, không phải yêu cầu bắt buộc

Extension `citext` cung cấp kiểu ký tự có hành vi so sánh không phân biệt hoa/thường ở những trường hợp phù hợp. Nếu ứng dụng cần username/email case-insensitive theo một chính sách cụ thể, có thể cân nhắc dùng kiểu đó và index/constraint tương ứng.

Nhưng:

- Cần extension và quyền phù hợp.
- Quy tắc so sánh chịu ảnh hưởng locale/collation.
- Không phải mọi yêu cầu Unicode, accent-insensitive hoặc case folding đa ngôn ngữ đều được giải quyết chỉ bằng `citext`.
- Migration kiểu dữ liệu có thể ảnh hưởng unique constraints và giá trị đang tồn tại.

Trong bài lab, ta giữ `TEXT` để nhìn rõ từng phép toán.

## 6. Tìm theo tiền tố bằng LIKE 'abc%'

Ví dụ:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%'
ORDER BY title;
```

`LIKE` dùng ký tự wildcard:

- `%`: khớp **không hoặc nhiều ký tự**.
- `_`: khớp **đúng một ký tự**.

Mẫu `'PostgreSQL%'` nghĩa là:

```text
Chuỗi phải bắt đầu bằng: PostgreSQL
Sau đó có thể có 0, 1 hoặc nhiều ký tự tùy ý
```

### 6.1. Vì sao tiền tố khác tìm chuỗi con?

```sql
-- Tiền tố: bắt đầu bằng PostgreSQL
WHERE title LIKE 'PostgreSQL%'

-- Hậu tố: kết thúc bằng PostgreSQL
WHERE title LIKE '%PostgreSQL'

-- Chuỗi con: ở đâu cũng được
WHERE title LIKE '%PostgreSQL%'
```

Với title `Tối ưu PostgreSQL`:

- Không khớp `'PostgreSQL%'`.
- Có thể khớp `'%PostgreSQL'`.
- Khớp `'%PostgreSQL%'`.

### 6.2. Dùng LIKE cho autocomplete

Khi người dùng gõ `Postg`:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'Postg%'
ORDER BY title
LIMIT 10;
```

Đây là gợi ý theo **tiền tố chuỗi title**, không tự chọn kết quả theo độ liên quan ngôn ngữ.

Nếu muốn không phân biệt hoa/thường:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'postg%'
ORDER BY title
LIMIT 10;
```

Đừng giả định hai query sẽ có cùng access path: `ILIKE` và `LIKE` có quy tắc matching/index khác nhau.

## 7. B-tree index cho tiền tố và text_pattern_ops

B-tree có thể hỗ trợ hiệu quả pattern với **tiền tố cố định**, vì nó có thể tìm một khoảng giá trị bắt đầu từ prefix.

Với dữ liệu `TEXT`:

```sql
CREATE INDEX idx_lab_documents_title_pattern
ON text_search_lab.documents (title text_pattern_ops);
```

`text_pattern_ops` là **B-tree operator class** cho các phép so sánh theo mẫu, hữu ích khi dùng `LIKE 'prefix%'` dưới các collations mà B-tree index mặc định không thể tối ưu prefix bằng cách suy ra range phù hợp.

### 7.1. Khi nào index B-tree thường có thể đủ?

Ở collation kiểu **C** hoặc môi trường có thứ tự so sánh thích hợp, một B-tree index mặc định có thể hỗ trợ prefix LIKE. Với các collation theo ngôn ngữ, `text_pattern_ops` có thể cần thiết để tận dụng index cho pattern không phân biệt theo quy tắc binary-like thích hợp.

Không nên tạo cả hai index trên mọi bảng theo phản xạ. Hãy xem truy vấn thật và plan thực tế.

### 7.2. LIKE cần prefix cố định ở đầu

```sql
WHERE title LIKE 'PostgreSQL%'
```

có prefix cố định `PostgreSQL`.

Nhưng:

```sql
WHERE title LIKE '%PostgreSQL'
```

bắt đầu bằng wildcard, nên B-tree theo thứ tự **toàn bộ title từ trái qua phải** không thể tự nhảy tới những giá trị có hậu tố tùy ý.

### 7.3. Expression index cho tiền tố không phân biệt case

```sql
CREATE INDEX idx_lab_documents_lower_title_pattern
ON text_search_lab.documents
    (lower(title) text_pattern_ops);
```

Truy vấn tương ứng:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE 'postgresql%'
ORDER BY title
LIMIT 20;
```

Đây là cách đưa giá trị đã lowercase thành **search key** của index, không phải chỉ lưu `title` nguyên dạng rồi hy vọng `ILIKE` tự dùng expression index.

### 7.4. LIKE có giá trị bind

Nếu query dùng:

```sql
WHERE title LIKE $1
```

planner có thể cần biết mẫu cụ thể để suy ra tiền tố cố định. Với **generic prepared plan**, giá trị tham số chưa được biết theo cách của custom plan, nên không được giả định mọi câu `LIKE ?` đều tận dụng prefix index như khi dùng literal.

Cần kiểm tra `EXPLAIN EXECUTE` trên **hình thức query và chế độ plan mà ứng dụng thực sự dùng**.

## 8. LIKE và ký tự wildcard: % không phải dấu phần trăm thông thường

Giả sử người dùng muốn tìm tiêu đề bắt đầu bằng chữ:

```text
50%
```

Nếu ứng dụng làm:

```sql
WHERE title LIKE '50%%'
```

thì hai dấu `%` đều là wildcard; pattern này khớp **bất kỳ chuỗi bắt đầu bằng '50'**, kể cả không có dấu phần trăm thật.

Muốn dấu phần trăm là dữ liệu literal, cần escape nó.

### 8.1. Escape bằng ký tự rõ ràng

Chọn `!` làm escape character:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '50!%%' ESCAPE '!';
```

Giải thích:

- `50`: hai ký tự thường.
- `!%`: **một dấu % literal**.
- `%` cuối: wildcard cho phần còn lại.

Vì vậy pattern tìm các title bắt đầu bằng `50%`.

### 8.2. Escape dấu gạch dưới

Nếu muốn tìm chuỗi `A_B`:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%A!_B%' ESCAPE '!';
```

`!_` là một dấu gạch dưới literal; còn `%` hai đầu cho phép chuỗi con ở vị trí bất kỳ.

### 8.3. Escape chính ký tự escape

Khi dùng `ESCAPE '!'`, một dấu `!` literal phải được viết thành `!!` trong pattern. Quy tắc escape phải được xử lý ở **ứng dụng tạo pattern**, không lấy raw input rồi thêm % một cách máy móc.

### 8.4. Lưu ý về backslash

PostgreSQL cho phép lựa chọn ký tự escape trong LIKE. Cách biểu diễn backslash trong SQL literal và Java string literal có thể dễ nhầm; dùng `ESCAPE '!'` trong lab làm ví dụ rõ nghĩa và tránh phụ thuộc các tầng escaping không cần thiết.

## 9. Parameter binding trong JDBC: an toàn cho cả SQL và LIKE pattern

Không tạo câu SQL bằng nối chuỗi:

```java
// KHÔNG NÊN: đưa input vào SQL text trực tiếp.
String sql = "SELECT * FROM documents WHERE title LIKE '%"
    + userInput + "%'";
```

Đó là rủi ro **SQL injection** khi input trở thành một phần mã SQL.

Dùng `PreparedStatement`:

```java
String sql = """
    SELECT document_id, title
    FROM text_search_lab.documents
    WHERE title LIKE ? ESCAPE '!'
    ORDER BY title
    LIMIT 20
    """;

String escaped = userInput
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

String containsPattern = "%" + escaped + "%";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, containsPattern);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("title"));
        }
    }
}
```

Những điều cần nhớ:

1. `?` là **bind parameter**, không phải chỗ nối SQL text.
2. `%` và `_` của input người dùng được escape để được hiểu là **dữ liệu literal**.
3. Hai dấu `%` do ứng dụng chủ đích thêm vào định nghĩa tìm chuỗi con.
4. Thứ tự replace rất quan trọng: escape `!` trước rồi mới escape `%` và `_`.
5. `PreparedStatement` **chống SQL injection theo ngữ cảnh giá trị bind**, nhưng **không tự biến wildcard của LIKE thành literal**.

### 9.1. Prefix search

Nếu muốn bắt đầu bằng input:

```java
String prefixPattern = escaped + "%";
```

Nếu muốn equality:

```sql
WHERE title = ?
```

thì không cần wildcard hay LIKE escaping; chỉ bind nguyên giá trị.

### 9.2. Validate input

Một API nên có giới hạn:

- Độ dài tối đa từ khóa, đo theo chính sách Unicode phù hợp.
- Loại query được phép: exact/prefix/contains/full_text.
- Page size, timeout và quyền truy cập dữ liệu.
- Trường nào được tìm: title/body/category hoặc tập cột whitelist.

Không cho client tùy ý đưa cả tên cột, SQL expression, ORDER BY hoặc operator vào câu SQL bằng nối string.

## 10. ILIKE: không phân biệt hoa-thường nhưng không tự bỏ dấu

`ILIKE` là toán tử PostgreSQL mở rộng để match pattern theo quy tắc không phân biệt chữ hoa/thường phù hợp với locale/collation.

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'postgresql%';
```

Câu này có thể tìm:

- `PostgreSQL cơ bản`.
- `PostgreSQL nâng cao`.
- `postgresql không viết hoa`.

Nhưng **không tự đồng nghĩa “không phân biệt dấu tiếng Việt”**:

```text
toi uu   ≠   tối ưu
```

trong nhiều cấu hình phổ biến.

### 10.1. Vì sao không mặc định bỏ dấu?

Hoa/thường và dấu là hai chiều chuẩn hóa khác nhau. Ví dụ:

- `A` và `a`: khác hoa/thường.
- `a` và `á`: khác dấu.
- `Đ` và `D`: khác ký tự/chính tả, không chỉ đơn giản là case.

Nếu sản phẩm yêu cầu tìm không dấu ra có dấu, phải thiết kế **normalization pipeline** và kiểm tra tương thích Unicode/ngôn ngữ.

### 10.2. Collation có thể thay đổi kết quả so sánh

PostgreSQL hỗ trợ collations xác định và không xác định, với khả năng so sánh có thể khác nhau theo phiên bản/provider. Một số thao tác pattern có giới hạn khác nhau tùy loại collation và phiên bản.

Không lấy kết quả một câu `ILIKE` ở một server rồi mặc định áp dụng cho mọi cluster/collation. Nếu nghiệp vụ đòi hành vi ổn định, hãy xác định rõ normalization/collation và kiểm thử.

## 11. Tìm theo mẫu bằng LIKE: % và _

`LIKE` là công cụ đơn giản cho **mẫu ký tự**, không có đầy đủ sức mạnh của regex.

Ví dụ:

```sql
-- Bắt đầu bằng 'Post' và kết thúc bằng 'SQL'
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'Post%SQL';
```

```sql
-- Một ký tự bất kỳ giữa 'A' và 'B'
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%A_B%';
```

Mẫu `'A_B'` **không đòi dấu gạch dưới literal**. Nó có thể khớp `A-B`, `A0B` hay `A_B` trong ngữ cảnh phù hợp, vì `_` là wildcard đúng một ký tự.

### 11.1. LIKE so cả chuỗi theo mẫu

```sql
WHERE title LIKE 'SQL'
```

khớp giá trị theo **toàn bộ pattern** `SQL`, không tự tìm `SQL` ở giữa chuỗi. Muốn substring:

```sql
WHERE title LIKE '%SQL%'
```

### 11.2. Phạm vi của LIKE

LIKE phù hợp với:

- Tiền tố/hậu tố.
- Vài vị trí ký tự cố định.
- Chuỗi con literal.
- Kiểm tra mẫu đơn giản dễ hiểu.

Nếu cần character classes, repetition bounds hoặc alternatives phức tạp, regex thường diễn đạt rõ hơn.

## 12. SIMILAR TO: kiểu mẫu gần biểu thức chính quy của SQL

PostgreSQL hỗ trợ `SIMILAR TO` với mẫu có một số toán tử regex của SQL, kết hợp wildcard `%` và `_` giống LIKE.

Ví dụ:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title SIMILAR TO '(PostgreSQL|MySQL)%';
```

Ở đây:

- `(PostgreSQL|MySQL)`: chọn một trong hai chuỗi mở đầu.
- `%`: phần còn lại của title.

### 12.1. SIMILAR TO khác POSIX regex

`SIMILAR TO` kiểm tra **toàn bộ chuỗi theo mẫu**, giống tinh thần của LIKE. Trong khi các toán tử POSIX regex `~`/`~*` **có thể tìm một phần chuỗi** nếu không có anchor `^`/`$`.

Ví dụ:

```sql
-- POSIX regex: chuỗi con ở bất kỳ vị trí
WHERE title ~ 'SQL'

-- SQL SIMILAR TO: cần viết wildcard hai bên
WHERE title SIMILAR TO '%SQL%'
```

Không dùng cùng một pattern text giữa hai họ toán tử rồi kỳ vọng hành vi giống hệt.

### 12.2. Khi nào chọn SIMILAR TO?

Chỉ khi mẫu SQL-regex mô tả rõ yêu cầu và đội ngũ quen cú pháp. Với regex phức tạp, các toán tử PostgreSQL POSIX regex thường là lựa chọn rõ ràng hơn; với pattern đơn giản, LIKE dễ hiểu hơn.

## 13. POSIX regular expressions: ~, ~*, !~, !~*

Các toán tử thường gặp:

| Toán tử | Ngữ nghĩa |
| --- | --- |
| `~` | Match regex, phân biệt hoa/thường theo quy tắc tương ứng |
| `~*` | Match regex, không phân biệt hoa/thường |
| `!~` | Không match regex, phân biệt hoa/thường |
| `!~*` | Không match regex, không phân biệt hoa/thường |

Ví dụ:

```sql
-- Tiêu đề bắt đầu với PostgreSQL
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~ '^PostgreSQL';

-- Tiêu đề kết thúc bằng SQL, không phân biệt case
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~* 'sql$';

-- Tiêu đề có cụm 'Java' hoặc 'SQL'
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~ '(Java|SQL)';
```

### 13.1. Anchor

- `^`: bắt đầu chuỗi.
- `$`: kết thúc chuỗi.

Không có anchor:

```sql
WHERE title ~ 'SQL'
```

có thể khớp bất kỳ vị trí nào trong title.

Có anchor:

```sql
WHERE title ~ '^SQL$'
```

thì yêu cầu **toàn bộ title** chính là `SQL` theo quy tắc regex đang dùng.

### 13.2. Character class và repetition

Ví dụ kiểm tra một chuỗi mã ASCII giả định, không liên quan bảng lab:

```sql
SELECT
    'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$' AS valid_code,
    'AB-12'   ~ '^[A-Z]{2}-[0-9]{4}$' AS invalid_code;
```

Trong mẫu:

- `[A-Z]`: một ký tự trong khoảng A tới Z.
- `{2}`: lặp đúng hai lần.
- `[0-9]{4}`: bốn chữ số.

Regex rất hữu ích cho validate format, nhưng validation nghiêm ngặt còn phải tính nghiệp vụ, ký tự Unicode, độ dài byte, encoding và các trường hợp biên.

### 13.3. Không phó mặc regex do người dùng tùy ý

Nếu API cho người dùng nhập một regex không kiểm soát, có thể gặp:

- Pattern quá phức tạp, tốn CPU.
- Query quét nhiều rows.
- Các trường hợp regex engine xử lý chậm với pattern/dữ liệu cụ thể.
- Kết quả không đúng ý vì ký tự regex là metacharacters.

Parameter binding giúp ngăn SQL injection, nhưng **không biến regex input thành literal** và cũng **không ngăn một regex nặng tiêu tốn tài nguyên**.

Các hệ thống thường nên giới hạn độ dài/pattern, dùng timeout, rate limit, và chỉ cho phép regex khi đó là tính năng thực sự của sản phẩm.

## 14. LIKE '%keyword%' và vì sao B-tree thường không giúp

Truy vấn tìm chuỗi con:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%';
```

Ở đây `%` đầu nghĩa là **không biết prefix của title**. B-tree theo `title` sắp dữ liệu từ bên trái, nên không có một dải key liên tiếp đơn giản đại diện cho mọi chuỗi **có chứa** `postgresql` ở giữa.

Trên bảng lớn, query dạng này có thể phải:

1. `Seq Scan` và kiểm tra từng title; hoặc
2. Dùng một chỉ mục chuyên biệt cho pattern/substring như `pg_trgm` nếu có và planner đánh giá phù hợp.

### 14.1. Prefix có thể dùng B-tree, substring thường cần phương án khác

```text
LIKE 'postgres%'
  -> Có prefix cố định
  -> B-tree với cấu hình/opclass phù hợp có thể tìm vùng key

LIKE '%postgres%'
  -> Không có prefix cố định của toàn bộ title
  -> B-tree thông thường không giúp định vị vùng key đơn giản
  -> Cân nhắc trigram index, FTS hoặc scan tùy semantics
```

### 14.2. Không nên “chữa” substring bằng cách đổi thành FTS nếu sai yêu cầu

Nếu người dùng tìm một chuỗi ẩn bên trong mã `ABCD1234` bằng `'CD12'`, FTS dựa trên lexemes **không tự có nghĩa khớp đoạn giữa mã**.

Ngược lại, nếu người dùng tìm một bài viết về “cơ chế transaction”, substring LIKE có thể quá thô và không xếp hạng liên quan tốt.

**Ngữ nghĩa phải quyết định công nghệ tìm kiếm.**

## 15. pg_trgm cho substring, ILIKE và tìm tương đồng

Extension `pg_trgm` hỗ trợ xử lý văn bản dựa trên **trigram** – các chuỗi con gồm ba ký tự theo quy tắc tokenization tương ứng. Nó có thể hỗ trợ index search cho nhiều phép toán pattern và similarity.

Trên môi trường được cấp quyền, có thể:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

**Đây là phần tùy chọn của lab.** Extension phải có sẵn và người chạy cần quyền tương ứng. Trên production, phải được DBA/đội vận hành phê duyệt; không tự cài extension hoặc đổi cấu hình hệ thống chỉ để chạy bài.

### 15.1. GIN trigram index

```sql
CREATE INDEX idx_lab_documents_title_trgm
ON text_search_lab.documents
USING GIN (title gin_trgm_ops);
```

Sau đó một query:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%';
```

có thể dùng index trigram khi PostgreSQL suy ra đủ thông tin từ pattern và bảng đủ lớn để index có lợi.

### 15.2. GIN vs GiST cho pg_trgm

`pg_trgm` còn hỗ trợ GiST operator class:

```sql
-- Một phương án khác, không cần tạo cả hai trên mọi workload:
-- CREATE INDEX idx_lab_documents_title_trgm_gist
-- ON text_search_lab.documents
-- USING GIST (title gist_trgm_ops);
```

GIN thường hữu ích cho các phép kiểm tra pattern/filter; GiST có thể hữu ích với những chiến lược khác như truy vấn lân cận theo khoảng cách khi phù hợp. **Không có một index method thắng mọi workload**; cần đo tốc độ đọc, chi phí ghi, dung lượng và loại toán tử.

### 15.3. Pattern quá ngắn có thể không tạo được bộ trigram chọn lọc

Ví dụ:

```sql
WHERE title ILIKE '%a%'
```

Một ký tự đơn thường không đủ trigram để giới hạn tập kết quả hiệu quả. PostgreSQL có thể phải quét phần lớn index hoặc bảng. Tìm kiếm substring rất ngắn trên bảng lớn thường cần:

- Giới hạn độ dài tối thiểu.
- Yêu cầu thêm điều kiện category/tenant/date.
- Chọn prefix search nếu phù hợp sản phẩm.
- Thiết kế một cơ chế tìm đặc biệt cho một ký tự/mã nếu thật sự cần.

Đừng hứa rằng tạo `gin_trgm_ops` làm **mọi `LIKE '%...%'`** đều nhanh.

### 15.4. Similarity không giống contains

`pg_trgm` có hàm/toán tử tìm tương đồng, ví dụ khi extension đã có:

```sql
SELECT
    title,
    similarity(title, 'Postgres') AS score
FROM text_search_lab.documents
ORDER BY score DESC, document_id
LIMIT 10;
```

Kết quả xếp theo mức tương đồng của chuỗi, không phải chỉ kiểm tra title chứa đúng một chuỗi con. Các toán tử threshold similarity (ví dụ `%` trong hệ `pg_trgm`) có điều kiện và mức ngưỡng riêng; không nhầm nó với wildcard `%` của LIKE.

## 16. Tìm toàn văn khác tìm chuỗi con như thế nào?

PostgreSQL Full-Text Search hoạt động trên **các thành phần ngôn ngữ/từ vựng** chứ không chỉ vị trí ký tự.

Các khái niệm:

- **Parser:** tách văn bản thành token theo quy tắc parser/configuration.
- **Dictionary:** chuẩn hóa token thành lexeme hoặc loại bỏ stop words tùy cấu hình.
- **`tsvector`:** tập lexemes đã chuẩn hóa, kèm vị trí và có thể trọng số.
- **`tsquery`:** biểu thức truy vấn trên lexemes với các toán tử AND/OR/NOT/phrase/prefix.
- **`@@`:** kiểm tra tsvector có đáp ứng tsquery không.

Ví dụ:

```sql
SELECT
    to_tsvector(
        'simple',
        'PostgreSQL hỗ trợ tìm kiếm toàn văn'
    ) AS vector;
```

Kết quả là biểu diễn các lexemes và vị trí, **không phải bản sao nguyên văn chuỗi**.

### 16.1. FTS không phải kiểu LIKE thông minh hơn cho mọi thứ

Ví dụ với `simple`:

```sql
SELECT
    to_tsvector('simple', 'PostgreSQL')
      @@ plainto_tsquery('simple', 'PostgreSQL')
      AS matches_word,
    to_tsvector('simple', 'PostgreSQL')
      @@ plainto_tsquery('simple', 'post')
      AS matches_partial_lexeme;
```

Từ `post` **không mặc định** khớp lexeme `postgresql` như `LIKE 'post%'`. FTS và prefix chuỗi là hai ngữ nghĩa khác nhau.

FTS có thể hỗ trợ **prefix của lexeme** với cú pháp riêng, nhưng không tự hỗ trợ tìm **chuỗi con bất kỳ nằm giữa lexeme**.

### 16.2. Từ vs cụm từ vs chuỗi chính xác

```text
title = 'Java JDBC'
  -> Cả giá trị title bằng đúng chuỗi theo quy tắc so sánh

title ILIKE '%java jdbc%'
  -> Hai đoạn ký tự liên tiếp xuất hiện trong title,
     có thể có khác biệt case

search_vector @@ phraseto_tsquery('simple', 'Java JDBC')
  -> Lexemes Java và JDBC xuất hiện theo quan hệ vị trí
     của phrase query sau xử lý token
```

FTS phrase không bảo đảm các ký tự dấu cách, dấu câu hoặc Unicode bytes trong nguồn giống nguyên văn input.

## 17. to_tsvector và cấu hình phân tích từ

Hàm:

```sql
SELECT to_tsvector(
    'simple',
    'PostgreSQL giúp tìm kiếm văn bản'
);
```

biến văn bản thành tsvector.

### 17.1. Chọn cấu hình tường minh

```sql
SELECT
    to_tsvector('simple', 'Running runners run') AS simple_vector,
    to_tsvector('english', 'Running runners run') AS english_vector;
```

Với `simple`, token được xử lý theo từ điển simple, chủ yếu lowercase theo quy tắc; không tự stemming tiếng Anh giống cấu hình `english`. Cấu hình `english` có dictionary/nguyên tắc phù hợp tiếng Anh, bao gồm stemming và stop words theo cấu hình.

Kết quả thực tế phụ thuộc parser, dictionary, phiên bản và dữ liệu, nên đừng viết test cứng các chuỗi vector không cần thiết nếu mục tiêu là hiểu cơ chế.

### 17.2. Không phụ thuộc cấu hình mặc định của session

```sql
SELECT to_tsvector('PostgreSQL search example');
```

phiên bản một tham số sử dụng `default_text_search_config`; hai môi trường có thể có giá trị mặc định khác nhau.

Trong hệ thống production, nên chọn cấu hình rõ và dùng nhất quán khi **ghi vector, lập chỉ mục và tạo query**.

### 17.3. simple và dữ liệu tiếng Việt

PostgreSQL không mặc định cung cấp một bộ phân tích hình thái tiếng Việt chuyên biệt tương đương các bộ tokenizer ứng dụng đã được huấn luyện. `simple` hữu ích để làm nền tảng nhưng thường:

- Không hiểu mọi từ ghép tiếng Việt theo nghĩa ngôn ngữ.
- Không tự bỏ dấu.
- Không tự sửa chính tả.
- Không tự mở rộng từ đồng nghĩa.
- Không bảo đảm một phrase nhiều âm tiết được phân tích đúng như một từ ghép về mặt ngữ nghĩa.

Nếu sản phẩm tìm kiếm nội dung tiếng Việt ở quy mô lớn, cần thử dữ liệu thật, xác định dictionary/tokenizer và có thể đánh giá giải pháp chuyên biệt ngoài mặc định PostgreSQL.

## 18. plainto_tsquery: chuyển input thường thành query tìm từ

Không nên chuyển raw input của người dùng thành biểu thức `to_tsquery` một cách mù quáng. Với input người dùng bình thường, bắt đầu từ:

```sql
SELECT plainto_tsquery(
    'simple',
    'PostgreSQL tối ưu'
);
```

Nó tạo `tsquery` từ các từ đã phân tích, thông thường kết hợp lexemes bằng **AND**.

Để tìm trong bảng lab:

```sql
SELECT document_id, title, category
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

Điểm quan trọng: ở schema lab, `search_vector` gồm **title + body**, nên một tài liệu có `PostgreSQL` trong body cũng được trả, dù title không chứa.

### 18.1. AND có thể làm query nhiều từ hẹp hơn

```sql
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL JDBC')
```

thông thường yêu cầu cả các lexemes `postgresql` và `jdbc` xuất hiện trong document vector, nhưng **không nhất thiết đứng cạnh nhau**.

### 18.2. Khi nào nên dùng plainto_tsquery?

- Ô tìm kiếm văn bản đơn giản.
- Muốn người dùng không phải biết cú pháp `&`, `|`, `!`.
- Muốn parse văn bản người dùng theo dictionary đã chọn.
- Không cần cú pháp kiểu công cụ tìm kiếm web cho quotation/exclusion.

Nếu người dùng cần phrase search hoặc OR/NOT có chủ đích, xem các hàm sau.

## 19. phraseto_tsquery: khớp theo vị trí của từ

Ví dụ:

```sql
SELECT phraseto_tsquery(
    'simple',
    'Java JDBC'
);
```

Hàm tạo biểu thức tìm có yêu cầu về **thứ tự và khoảng cách lexeme**, phù hợp bài toán tìm một phrase hơn `plainto_tsquery`.

Truy vấn:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ phraseto_tsquery('simple', 'Java JDBC');
```

### 19.1. Phrase search không giống '='

Tiêu đề:

```text
Java JDBC với PostgreSQL
```

có thể khớp phrase `Java JDBC` dù cả title không bằng `Java JDBC`.

Nếu nội dung chứa dấu câu hoặc stop words, vị trí và khoảng cách lexeme có thể khác so với chỉ so sánh chuỗi ký tự liên tiếp.

### 19.2. Sự khác nhau với AND

```text
plainto_tsquery('simple', 'Java JDBC')
  -> Các lexemes cần có, không nhất thiết liền kề

phraseto_tsquery('simple', 'Java JDBC')
  -> Các lexemes cần theo thứ tự/vị trí phrase
```

Nếu yêu cầu “hai từ liên tiếp theo ý nghĩa token”, phrase FTS phù hợp hơn LIKE, nhưng phải kiểm tra chính sách parser của ngôn ngữ.

## 20. websearch_to_tsquery: cú pháp gần công cụ tìm kiếm

PostgreSQL hỗ trợ:

```sql
SELECT websearch_to_tsquery(
    'simple',
    '"Java JDBC" OR PostgreSQL -MySQL'
);
```

Ý tưởng:

- Dấu ngoặc kép tạo yêu cầu phrase.
- `OR` diễn đạt lựa chọn.
- Dấu trừ trước từ loại trừ theo cú pháp được hỗ trợ.
- Văn bản thông thường được phân tích thành lexemes.

### 20.1. Dùng cho search box

```sql
SELECT
    document_id,
    title
FROM text_search_lab.documents
WHERE search_vector
    @@ websearch_to_tsquery(
        'simple',
        '"Java JDBC" OR PostgreSQL'
    );
```

Hàm phù hợp khi muốn cho người dùng nhập biểu thức gần syntax tìm kiếm web và tránh phải dùng strict tsquery syntax.

### 20.2. Không hiểu mọi cú pháp công cụ tìm kiếm

`websearch_to_tsquery` **không phải parser đầy đủ của Google**. Không mặc định nó hiểu mọi toán tử `site:`, wildcard tùy ý, regex hoặc field-specific syntax.

Nếu API tự công bố grammar phức tạp, phải kiểm thử và tự xây parser/validation đúng theo contract.

## 21. to_tsquery: dùng cú pháp biểu thức FTS có kiểm soát

Khi cần xây query chuyên biệt:

```sql
SELECT to_tsquery(
    'simple',
    'postgresql & (jdbc | sql)'
);
```

Các toán tử phổ biến:

| Toán tử tsquery | Nghĩa |
| --- | --- |
| `&` | AND |
| `|` | OR |
| `!` | NOT |
| `<->` | Hai lexemes kề nhau theo vị trí phrase |
| `<N>` | Hai lexemes cách nhau N vị trí theo cú pháp tsquery |
| `:*` | Prefix match **của lexeme** |

Ví dụ:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery(
        'simple',
        'postgresql & (jdbc | sql)'
    );
```

### 21.1. Strict syntax có thể gây lỗi input

`to_tsquery` yêu cầu biểu thức có cú pháp hợp lệ. Không gửi trực tiếp user input như `java sql postgres` rồi kỳ vọng luôn được parse như văn bản thuần; input đó có thể không phù hợp grammar.

Với search box thông thường, chọn `plainto_tsquery` hoặc `websearch_to_tsquery`; dùng `to_tsquery` khi **ứng dụng tự tạo biểu thức hợp lệ** hoặc user có quyền nhập advanced query đã được kiểm soát.

### 21.2. Prefix của lexeme không phải prefix của whole title

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery('simple', 'postgr:*');
```

`postgr:*` có nghĩa tìm lexemes bắt đầu bằng `postgr`. Nó không yêu cầu **toàn bộ title bắt đầu** bằng `postgr`.

Vì vậy có thể khớp một tài liệu có lexeme `postgresql` trong body hoặc ở giữa title.

## 22. Chỉ mục GIN cho Full-Text Search

Một cách tạo chỉ mục:

```sql
CREATE INDEX idx_lab_documents_fts
ON text_search_lab.documents
USING GIN (search_vector);
```

Với truy vấn:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

GIN index cho phép tìm các tài liệu có lexeme phù hợp mà không nhất thiết phải quét toàn bộ văn bản từng row.

### 22.1. GIN không phải B-tree

Khác B-tree index trên nguyên title, GIN cho tsvector tổ chức những mục tìm (lexemes) và các tài liệu chứa chúng. Nó phù hợp truy vấn chứa từ theo `@@`.

Không nên giả định `USING GIN(search_vector)` tự tối ưu:

```sql
WHERE title LIKE 'PostgreSQL%'
```

hoặc:

```sql
WHERE title = 'PostgreSQL cơ bản'
```

Những biểu thức đó có access paths/indexes riêng. **Index dùng được hay không phụ thuộc operator và expression trong query.**

### 22.2. GIN index làm tăng chi phí ghi

Khi cập nhật title/body, generated tsvector và index entries liên quan phải được duy trì. Chi phí:

- Dung lượng lưu index và tsvector.
- CPU khi tokenize/normalize.
- WAL và index maintenance.
- Vacuum/reindex khi workload yêu cầu.

Trên bảng đọc nhiều, FTS GIN có thể đáng giá. Trên bảng ghi cực cao hoặc bài toán chỉ tìm đúng ID, không nên mặc định thêm FTS cho mọi cột.

### 22.3. Expression GIN index thay vì cột generated

Một phương án khác:

```sql
CREATE INDEX idx_lab_documents_fts_expression
ON text_search_lab.documents
USING GIN (
    to_tsvector(
        'simple'::regconfig,
        COALESCE(title, '') || ' ' || COALESCE(body, '')
    )
);
```

Nhưng query cần dùng **biểu thức phù hợp** để planner nhận diện index:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE to_tsvector(
    'simple'::regconfig,
    COALESCE(title, '') || ' ' || COALESCE(body, '')
) @@ plainto_tsquery('simple', 'PostgreSQL');
```

Index này không lưu trọng số title A/body B như cột `search_vector` ban đầu. Trong lab đã có generated column; phần expression index chỉ để so sánh kiến trúc, **không cần giữ hai FTS indexes trùng chức năng trong production**.

### 22.4. Vì sao generated column hữu ích?

- Query đơn giản: `WHERE search_vector @@ ...`.
- Có thể dùng cùng vector cho filtering và ranking.
- Dễ gán trọng số cho từng field.
- Không phải lặp một biểu thức dài ở mọi query.

Nhược điểm là thêm cột lưu trữ và chi phí duy trì khi write.

## 23. Xếp hạng kết quả FTS bằng ts_rank

`@@` chỉ quyết định **có khớp hay không**. Kết quả còn cần sắp theo độ liên quan.

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple',
        'PostgreSQL tối ưu'
    ) AS query
)
SELECT
    d.document_id,
    d.title,
    d.published_at,
    ts_rank(d.search_vector, q.query) AS relevance
FROM text_search_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY relevance DESC, d.published_at DESC, d.document_id DESC
LIMIT 20;
```

### 23.1. Vì sao có trọng số A/B?

Trong schema lab:

```sql
setweight(to_tsvector(...title...), 'A') ||
setweight(to_tsvector(...body...), 'B')
```

Giá trị xuất hiện trong title có thể được chấm điểm khác so với trong body, tùy hàm ranking và vector weights.

Một ví dụ kỳ vọng nghiệp vụ:

```text
Tài liệu có cả từ khóa trong title:
  có thể đáng xếp cao hơn tài liệu chỉ nhắc thoáng qua trong body
```

Nhưng ranking của PostgreSQL không tự hiểu toàn bộ ngữ nghĩa như mô hình semantic search. Cần đo kết quả relevance trên tập truy vấn thật, không chỉ nhìn điểm số.

### 23.2. GIN không tự sắp thứ tự theo ts_rank

GIN có thể giúp tìm **các document khớp**, nhưng thông thường PostgreSQL vẫn cần **tính rank cho candidates và sắp xếp** để có top kết quả.

Nếu từ khóa quá phổ biến, candidate set lớn, câu `ORDER BY ts_rank(...) LIMIT 20` vẫn có thể tốn CPU/Sort dù có GIN index.

### 23.3. ts_rank_cd

`ts_rank_cd` là lựa chọn dựa trên cover density, có thể nhấn mạnh vị trí/cụm từ gần nhau trong những trường hợp phù hợp.

```sql
SELECT
    document_id,
    title,
    ts_rank_cd(
        search_vector,
        plainto_tsquery('simple', 'PostgreSQL')
    ) AS cover_density_rank
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL')
ORDER BY cover_density_rank DESC, document_id
LIMIT 10;
```

Đừng kỳ vọng `ts_rank` và `ts_rank_cd` cho cùng thứ tự trong mọi query; thuật toán ranking khác nhau.

### 23.4. Tie-breaker

Hai tài liệu có thể cùng score. Thêm `document_id` vào ORDER BY làm thứ tự rõ ràng hơn trong một snapshot, giúp pagination và test bớt bất định.

## 24. Highlight các từ khớp bằng ts_headline

FTS có thể tạo đoạn nội dung có đánh dấu các từ khớp:

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'simple',
        'PostgreSQL'
    ) AS query
)
SELECT
    d.document_id,
    d.title,
    ts_headline(
        'simple',
        d.body,
        q.query
    ) AS snippet
FROM text_search_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY d.document_id
LIMIT 10;
```

### 24.1. ts_headline không thay thế sanitizer/XSS protection

Nếu ứng dụng dùng kết quả `ts_headline` để render HTML với thẻ highlight, phải xử lý an toàn nội dung tài liệu và markup.

Một đoạn body do người dùng tạo có thể chứa HTML hoặc ký tự đặc biệt. Không truyền raw string từ database vào `innerHTML` mà thiếu cơ chế escaping/sanitization phù hợp.

### 24.2. Highlight và ranking là bước sau khi chọn candidate

Tốt hơn nên giới hạn candidate/top results theo chính sách trước khi sinh snippet cho số lượng rất lớn. `ts_headline` trên hàng trăm nghìn body rộng có thể đắt.

## 25. Full-text search với tiếng Việt

Phần khó nhất thường không phải cú pháp `@@`, mà là **ngữ nghĩa ngôn ngữ**.

Ví dụ người dùng nhập:

```text
toi uu co so du lieu
```

trong khi bài viết chứa:

```text
Tối ưu cơ sở dữ liệu
```

Với cấu hình `simple`, PostgreSQL không tự bảo đảm input không dấu sẽ khớp văn bản có dấu.

### 25.1. Cần một chính sách tìm kiếm rõ ràng

Quyết định sản phẩm nên trả lời:

- Có phân biệt dấu hay không?
- Có phân biệt chữ hoa/thường không?
- Có muốn gộp những biến thể cách viết không?
- Có hỗ trợ từ đồng nghĩa và viết tắt, ví dụ `CSDL` ↔ `cơ sở dữ liệu` không?
- Có tìm cụm từ đa âm tiết như một đơn vị không?
- Có cần sửa lỗi chính tả và tìm gần đúng không?
- Có dữ liệu tiếng Anh xen tiếng Việt không?

Không thể giải quyết toàn bộ bằng một `ILIKE` hoặc một `to_tsvector('simple', ...)`.

### 25.2. unaccent là công cụ tùy chọn

PostgreSQL có extension `unaccent` hỗ trợ loại bỏ dấu theo từ điển/rules:

```sql
-- Chỉ chạy nếu môi trường cho phép dùng extension:
-- CREATE EXTENSION IF NOT EXISTS unaccent;
--
-- SELECT unaccent('Tối ưu dữ liệu');
```

Nếu dùng unaccent, cần lưu ý:

- Extension/rules phải được cài và quản lý.
- Chuẩn hóa cách hiển thị/tìm phải nhất quán.
- Hàm `unaccent` không nên bị giả định là **IMMUTABLE** cho mọi use case vì từ điển/rules có thể thay đổi.
- Đừng tự khai báo wrapper IMMUTABLE để tạo expression index nếu không có cam kết mạnh về tính bất biến và quy trình rebuild khi rules đổi.
- Khác biệt chính tả và tách từ vẫn tồn tại sau khi bỏ dấu.

Một chiến lược là lưu **search-normalized field** do pipeline ứng dụng tạo và cập nhật nhất quán, rồi index field đó theo pattern phù hợp. Cần thiết kế việc cập nhật/đồng bộ khi normalization algorithm thay đổi.

### 25.3. Tìm từ đồng nghĩa

Ví dụ người dùng muốn `db` tìm những tài liệu có `database` hoặc `cơ sở dữ liệu`. Có thể cần cấu hình dictionary/thesaurus, logic mở rộng query hoặc search service phù hợp.

Không coi `pg_trgm` là công cụ hiểu từ đồng nghĩa: trigram chủ yếu dựa trên ký tự, không hiểu ngữ nghĩa “db” tương đương “database”.

## 26. So sánh exact, prefix, contains và FTS trên cùng dữ liệu

Với input `PostgreSQL`:

### 26.1. Exact title

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL';
```

Trong dữ liệu lab, không có title **bằng đúng duy nhất** `PostgreSQL`, nên trả **0 hàng**.

### 26.2. Prefix title

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%'
ORDER BY title;
```

Có thể trả:

- `PostgreSQL cơ bản`.
- `PostgreSQL nâng cao`.
- `PostgreSQL backup`.

Không trả `Tối ưu PostgreSQL` vì từ khóa không đứng đầu title.

### 26.3. Contains title không phân biệt case

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%'
ORDER BY title;
```

Câu này có thể trả cả:

- `Tối ưu PostgreSQL`.
- `Java JDBC với PostgreSQL`.
- `MySQL và PostgreSQL`.
- `postgresql không viết hoa`.

### 26.4. FTS title + body

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL')
ORDER BY document_id;
```

Câu này trả các tài liệu có lexeme `postgresql` trong title **hoặc body**, không chỉ trong title. Vì `summary` không nằm trong vector, một tài liệu chỉ nhắc PostgreSQL trong summary sẽ **không được khớp nhờ summary**.

### 26.5. Tập kết quả khác nhau là đúng, không phải bug

Một test tốt cần mã hóa **ý định tìm kiếm**, không lấy tập kết quả của LIKE làm chuẩn rồi buộc FTS trả y hệt.

## 27. Tìm chính xác một từ không đồng nghĩa tìm chuỗi con

Ví dụ:

```text
PostgreSQL
Postgres
postgresql
PostgreSQLbackup
```

Với cấu hình `simple`, FTS làm việc trên lexemes. `ILIKE '%sql%'` có thể khớp đoạn ký tự `SQL` nằm trong `PostgreSQL`, nhưng FTS tìm lexeme riêng `sql` không nhất thiết khớp lexeme `postgresql`.

### 27.1. Một phép thử trực quan

```sql
SELECT
    to_tsvector('simple', 'PostgreSQL')
      @@ plainto_tsquery('simple', 'sql')
        AS fts_sql_in_postgresql,
    'PostgreSQL' ILIKE '%sql%'
        AS substring_sql_in_postgresql;
```

Điểm mấu chốt: **FTS không phải substring search**. Nó match từ khóa đã tokenize/normalize.

### 27.2. Tìm prefix lexeme

```sql
SELECT
    to_tsvector('simple', 'PostgreSQL')
      @@ to_tsquery('simple', 'postgr:*')
        AS fts_prefix_lexeme;
```

Prefix FTS cho phép tìm lexemes có đầu khớp, nhưng không có nghĩa title phải bắt đầu bằng prefix và không hỗ trợ tìm mọi chuỗi ở giữa lexeme.

## 28. Tìm các giá trị cố định: IN và ANY thay cho pattern

Nếu người dùng chọn một tập **category exact**:

```sql
SELECT document_id, title, category
FROM text_search_lab.documents
WHERE category IN ('database', 'java')
ORDER BY document_id;
```

Không nên viết:

```sql
WHERE category ILIKE '%database%'
   OR category ILIKE '%java%'
```

vì category là **mã phân loại cố định**, không cần fuzzy/pattern semantics.

### 28.1. Index bình thường cho category

```sql
CREATE INDEX idx_lab_documents_category
ON text_search_lab.documents(category);
```

Trên bảng lớn và có điều kiện chọn lọc, B-tree có thể hỗ trợ equality/IN.

### 28.2. ANY với tham số mảng

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE category = ANY(ARRAY['database', 'java']::text[]);
```

Trong JDBC có thể bind array thông qua driver. Không nối danh sách category chưa kiểm tra vào SQL string.

## 29. Thêm điều kiện khác để thu hẹp phạm vi trước khi tìm

Một hệ thống nhiều tenant thường muốn tìm trong dữ liệu của tenant đã đăng nhập.

```sql
-- Minh họa giả định bảng có tenant_id;
-- không thực thi trên schema lab vì bảng documents chưa có cột này.
SELECT document_id, title
FROM tenant_documents
WHERE tenant_id = $1
  AND published_at >= $2
  AND search_vector @@ websearch_to_tsquery('simple', $3)
ORDER BY published_at DESC
LIMIT 20;
```

### 29.1. Search index không thay thế authorization

Dù GIN FTS hoặc trigram index rất nhanh, vẫn phải kiểm tra:

- User được xem tenant nào.
- Document có bị ẩn/xóa mềm không.
- Quyền của category/record.
- Row-Level Security khi thích hợp.

Không làm query search toàn hệ thống rồi lọc tenant trong Java. Việc đó vừa overfetch, vừa làm dữ liệu không được phép đi ra khỏi database.

### 29.2. Partial indexes khi có điều kiện ổn định

Nếu phần lớn query chỉ tìm tài liệu đã xuất bản hoặc active:

```sql
-- DDL minh họa cho một bảng giả định có cột published.
CREATE INDEX idx_published_docs_fts
ON published_documents
USING GIN (search_vector)
WHERE published = TRUE;
```

Đây là **mô hình partial index**, không phải lệnh dùng được ngay trong lab (chưa có bảng `published_documents`). Planner chỉ dùng partial index khi điều kiện query đủ để chứng minh predicate ở ngữ cảnh lập kế hoạch thích hợp.

## 30. Chọn index theo loại câu hỏi

| Truy vấn | Index thường đáng thử | Điều cần nhớ |
| --- | --- | --- |
| `title = ?` | B-tree `(title)` | So sánh cả giá trị, collation |
| `lower(title) = ?` | B-tree expression `(lower(title))` | Query phải dùng biểu thức phù hợp |
| `title LIKE 'abc%'` | B-tree C collation hoặc `text_pattern_ops` | Cần prefix cố định |
| `lower(title) LIKE 'abc%'` | B-tree expression + `text_pattern_ops` | Case fold và prefix |
| `title LIKE '%abc%'` | `pg_trgm` GIN/GiST khi phù hợp | Prefix B-tree không giải quyết |
| `title ILIKE '%abc%'` | `pg_trgm` GIN/GiST khi phù hợp | Trigram không bảo đảm nhanh với keyword rất ngắn |
| `title ~ 'regex'` | Có thể cân nhắc trigram cho pattern phù hợp | Không phải regex nào extract được trigram hiệu quả |
| `search_vector @@ query` | GIN `(search_vector)` | Lexeme semantics, không phải substring |
| `category = ANY(...)` | B-tree `(category)` | Mã fixed values nên so equality |

### 30.1. Một bảng không cần mọi index trong bài

Trong lab, ta tạo nhiều index để so cơ chế. Trong production, mỗi index:

- Chiếm storage.
- Tăng chi phí INSERT/UPDATE/DELETE.
- Có thể làm mất cơ hội HOT update nếu cột được index thay đổi.
- Cần VACUUM/maintenance.
- Làm planning/search-space và migration phức tạp hơn.

Chỉ giữ index được biện minh bởi **workload, cardinality và benchmark thật**.

## 31. EXPLAIN: quan sát PostgreSQL chọn scan nào

Trước tiên:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title = 'PostgreSQL cơ bản';
```

Tiếp theo:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Và:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%';
```

Cuối cùng:

```sql
EXPLAIN
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

### 31.1. Điều quan trọng không phải “có index là phải dùng”

Trên 24 tài liệu, Seq Scan rất rẻ. Planner có thể không chọn một index nào dù tất cả đã được tạo. Điều đó **không có nghĩa index hỏng**.

Với tập lớn và điều kiện chọn lọc, có thể gặp:

- `Index Scan` với B-tree equality/prefix.
- `Bitmap Index Scan + Bitmap Heap Scan` với GIN/trigram.
- `Seq Scan` khi phần lớn hàng phù hợp.
- `Sort` sau khi tính rank.

### 31.2. EXPLAIN ANALYZE BUFFERS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL');
```

`EXPLAIN ANALYZE` thực thi SELECT để đo:

- `actual rows`.
- `loops`.
- `actual time`.
- `Buffers shared hit/read`.
- `Rows Removed by Filter` hoặc `Recheck Cond` nếu có.

### 31.3. GIN có thể cần recheck

Trong Bitmap Heap Scan, `Recheck Cond` có thể xuất hiện. Không tự hiểu đó là lỗi; access method và bitmap lossy/exact có thể yêu cầu xác minh khi đọc heap. Khi có `Heap Blocks: exact/lossy`, đọc thêm các dòng này.

### 31.4. Đừng cộng cost/time của mọi node

Chi phí node cha đã bao gồm subtree theo mô hình planner; thời gian đo node cha có thể bao gồm công việc child. Không cộng mọi dòng EXPLAIN như các khoảng độc lập.

## 32. Benchmark trên dữ liệu lớn hơn

Tạo nhiều row giả trong lab nếu muốn quan sát planer thiên về index trên bảng lớn:

```sql
INSERT INTO text_search_lab.documents
    (title, summary, body, category, published_at)
SELECT
    CASE
        WHEN g.n % 100 = 0 THEN 'PostgreSQL tài liệu ' || g.n
        WHEN g.n % 100 = 1 THEN 'Giới thiệu PostgreSQL ' || g.n
        ELSE 'Tài liệu số ' || g.n
    END,
    'Summary for document ' || g.n,
    CASE
        WHEN g.n % 100 = 0
          THEN 'PostgreSQL GIN index và full text search.'
        WHEN g.n % 100 = 1
          THEN 'Java JDBC kết nối PostgreSQL.'
        ELSE 'Nội dung dữ liệu thử nghiệm và cấu trúc bảng.'
    END,
    CASE WHEN g.n % 2 = 0 THEN 'database'
         ELSE 'algorithm'
    END,
    TIMESTAMPTZ '2026-04-01 00:00:00+00'
        + (g.n % 10000) * INTERVAL '1 minute'
FROM generate_series(1, 100000) AS g(n);

ANALYZE text_search_lab.documents;
```

Đây là **bài nạp bổ sung tùy chọn** và chỉ thực hiện một lần trên database học tập. Nó tạo thêm 100.000 row, dùng CPU/disk/WAL, không chạy tự động trên production.

### 32.1. So query chi phí

Đo:

1. Equality `title = ...`.
2. Prefix `title LIKE 'PostgreSQL%'`.
3. Contains `title ILIKE '%postgresql%'`.
4. FTS `search_vector @@ ...`.

Đối với chứa chuỗi con, thử khi có/không có `pg_trgm` index trong môi trường lab được kiểm soát. Với FTS, thử GIN trên vector.

### 32.2. So đúng workload

Nên ghi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Rows/estimated rows | Planner có ước lượng đúng không? |
| Execution Time | Thời gian SQL đo được |
| Shared hit/read | Truy cập page trong shared buffers |
| Index size | Dung lượng phải duy trì |
| Rows Removed by Filter | Có quét/lọc nhiều hay không |
| Sort Method, memory | Chi phí ranking/order |
| INSERT/UPDATE latency | Chi phí ghi do index |
| P95 API latency | Trải nghiệm ứng dụng thực |

Một index giúp SELECT nhanh hơn nhưng làm INSERT chậm quá nhiều có thể không đáng giữ.

## 33. Prefix trên TEXT khác prefix trên lexeme của FTS

Hai câu:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE 'postgr%';
```

và:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery('simple', 'postgr:*');
```

không tương đương:

- Câu đầu: **toàn bộ title** sau `lower` bắt đầu bằng `postgr`.
- Câu sau: **một lexeme ở bất kỳ vị trí được index** bắt đầu bằng `postgr`.

Ví dụ title `Tối ưu PostgreSQL`:

- Không khớp title-prefix.
- Có thể khớp FTS lexeme-prefix.

### 33.1. Autocomplete theo từ vs theo tiêu đề

Nếu UI gợi ý title bắt đầu bằng chuỗi đã nhập, dùng **title prefix**.

Nếu UI gợi ý tài liệu có một từ bắt đầu bằng prefix bất kỳ trong body, dùng **FTS lexeme prefix**, tùy cách index và ranking.

Nếu UI muốn chứa chuỗi bất kỳ kể cả ở giữa một từ, dùng **substring/trigram** khi phù hợp.

Đừng đổi implementation mà không đổi product behavior/tests.

## 34. Chọn cách tìm cho email, mã hàng, tên người và tài liệu

### 34.1. Email hoặc username

Thường yêu cầu định danh **exact sau normalization** và uniqueness tương ứng:

```sql
WHERE normalized_email = ?
```

Không dùng `ILIKE '%@example.com%'` để xác thực user identity.

### 34.2. SKU hoặc mã sản phẩm

Nếu người dùng nhớ các ký tự đầu mã:

```sql
WHERE sku LIKE 'ABC%'
```

Nếu muốn tìm một đoạn mã ở giữa, cân nhắc `pg_trgm` hoặc chiến lược khác theo độ dài/mã.

### 34.3. Tên hiển thị

Có thể cần:

- Search prefix để gợi ý.
- Case/accent normalization theo chính sách.
- Trigram cho sai chính tả nhẹ.
- Tie-breakers và thứ tự kết quả.

Không tự coi tính năng tìm tên người là phép match từ khóa FTS đơn thuần; tên riêng có cấu trúc ngôn ngữ đặc biệt và yêu cầu bảo vệ thông tin cá nhân.

### 34.4. Bài viết/documentation

FTS thường phù hợp hơn khi cần nhiều từ, phrase, relevancy. Có thể kết hợp filter category/date/tenant và rank.

### 34.5. Nhật ký lỗi

Log đôi khi chứa mã hoặc đoạn lỗi chính xác:

```text
SQLSTATE 23505
connection refused
timeout after 30000 ms
```

FTS có thể không giữ nguyên dấu câu/mã như chuỗi raw. Với tìm log substring/regex, phương án pattern/trigram hoặc hệ thống log search chuyên biệt có thể phù hợp hơn.

## 35. Query kết hợp exact filter + full-text search

Một endpoint có thể dùng nhiều kiểu tìm trong cùng SQL:

```sql
WITH q AS (
    SELECT websearch_to_tsquery('simple', 'PostgreSQL') AS query
)
SELECT
    d.document_id,
    d.title,
    d.category,
    ts_rank(d.search_vector, q.query) AS relevance
FROM text_search_lab.documents AS d
CROSS JOIN q
WHERE d.category = 'database'
  AND d.search_vector @@ q.query
ORDER BY relevance DESC, d.document_id DESC
LIMIT 20;
```

Ở đây:

- `category = 'database'` là **exact filter**.
- `search_vector @@ q.query` là **FTS**.
- `ORDER BY relevance` là **xếp hạng**.

Một B-tree index category và GIN FTS có thể có cơ hội kết hợp qua bitmap operations nếu cost phù hợp; không phải lúc nào planner cũng dùng cả hai.

### 35.1. Không chuyển category sang FTS

Nếu category là một enum/mã dữ liệu, dùng `=` hoặc `IN`. Đưa mọi field vào FTS có thể làm matching mơ hồ và giảm độ chính xác nghiệp vụ.

## 36. Phân trang kết quả tìm kiếm

Ví dụ top 20 theo rank:

```sql
WITH q AS (
    SELECT plainto_tsquery('simple', 'PostgreSQL') AS query
)
SELECT
    document_id,
    title,
    ts_rank(search_vector, q.query) AS rank_score
FROM text_search_lab.documents
CROSS JOIN q
WHERE search_vector @@ q.query
ORDER BY rank_score DESC, document_id DESC
LIMIT 20 OFFSET 0;
```

### 36.1. OFFSET sâu có chi phí

`OFFSET 10000 LIMIT 20` vẫn có thể cần xác định và sắp xếp/đi qua nhiều candidates trước khi lấy 20 hàng. GIN có thể lọc nhanh, nhưng xếp hạng theo rank chưa chắc được index cung cấp thứ tự.

### 36.2. Keyset pagination cho ranking

Có thể thiết kế cursor theo:

```text
(rank_score, document_id)
```

và lấy những hàng có cặp khóa nằm sau cursor trong thứ tự `rank_score DESC, document_id DESC`, nhưng cần tính:

- Điểm rank có thể thay đổi nếu tài liệu chỉnh sửa.
- Cần dùng **cùng query/config/weighting** cho mọi trang.
- Có thể cần snapshot hoặc search session nếu nghiệp vụ muốn kết quả nhất quán.
- Điểm số floating-point có thể gây vấn đề nếu serialize cursor thiếu độ chính xác.
- Generic pagination query phải xử lý NULL/score và tie-breaker cẩn thận.

Đừng sao chép vô điều kiện một keyset query theo timestamp sang relevance score mà chưa định nghĩa ổn định của ranking.

### 36.3. Hạn chế tối đa trả về

API nên đặt max page size, cho phép lọc category/date/tenant và cân nhắc minimum query length cho pattern quá ngắn. Từ khóa một ký tự trên hàng trăm triệu tài liệu có thể tạo quá nhiều candidates.

## 37. Những yếu tố ảnh hưởng hiệu năng tìm văn bản

| Yếu tố | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| Độ chọn lọc | `SQL` xuất hiện 80% title | Index có thể không lợi nhiều |
| Vị trí wildcard | `'abc%'` vs `'%abc%'` | B-tree tiền tố vs substring |
| Độ dài từ | `'a'` vs `'postgresql'` | Trigram có ít tín hiệu với từ rất ngắn |
| Cấu hình FTS | `simple` vs `english` | Lexemes, stopwords, stemming |
| Collation | Locale/case rules | Matching và khả năng index |
| Projection | SELECT title vs SELECT * | Row width, TOAST, I/O |
| Ranking | `ORDER BY ts_rank` | CPU + Sort trên candidates |
| Size/shape bảng | 24 vs 100 triệu rows | Seq Scan vs index decision |
| UPDATE volume | Body thay đổi liên tục | GIN/trigram maintenance, WAL |
| Thống kê | ANALYZE mới/cũ | Ước lượng cardinality |
| Limit/offset | LIMIT 20 vs OFFSET rất sâu | Chi phí top-K |
| Concurrency | 1 vs 1000 request | Contention, CPU, I/O |

### 37.1. Tìm toàn văn có thể trả rất nhiều candidates

Một từ quá phổ biến có thể khớp phần lớn tài liệu. GIN index giúp tìm theo lexeme nhưng không xóa công việc trả, rank và sort hàng triệu matches. Có thể thêm filter hợp lệ, phân trang và định nghĩa search UX để giới hạn công việc.

### 37.2. Pattern trên cột body rất rộng

`body ILIKE '%abc%'` có thể đọc nhiều dữ liệu và tạo áp lực CPU/I/O hơn `title ILIKE '%abc%'` vì body dài. Cân nhắc FTS hoặc index chuyên biệt nếu ngữ nghĩa cho phép.

### 37.3. SQL cost không phải milliseconds

Trong EXPLAIN, `cost=...` là **ước lượng tương đối của planner**, còn `actual time=...` trong `EXPLAIN ANALYZE` mới là thời gian đo ở lần chạy.

Không quyết định giữ index bằng cách so cost của hai môi trường khác cấu hình/dữ liệu.

## 38. Tìm nhiều từ với LIKE: điểm yếu so với FTS

Nếu muốn tìm văn bản chứa cả `PostgreSQL` và `JDBC`, có thể viết:

```sql
WHERE body ILIKE '%PostgreSQL%'
  AND body ILIKE '%JDBC%'
```

Nhưng câu này:

- Khớp substring, có thể khớp bên trong từ dài.
- Không dùng stemming/dictionary.
- Không có ranking ngôn ngữ nếu không viết thêm.
- Có thể tốn scan/pattern checks trên body rộng.
- Các chuỗi con có thể nằm rất xa nhau.

FTS:

```sql
WHERE search_vector
    @@ plainto_tsquery('simple', 'PostgreSQL JDBC')
```

thể hiện **đòi hỏi lexemes**. Đây là ngữ nghĩa khác, không chỉ “tăng tốc SQL cũ”.

### 38.1. OR và NOT

Nếu cần “PostgreSQL hoặc MySQL nhưng không chứa JDBC”, có thể tạo tsquery với cú pháp thích hợp:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE search_vector
    @@ to_tsquery(
        'simple',
        '(postgresql | mysql) & !jdbc'
    );
```

Hoặc `websearch_to_tsquery` cho input người dùng phù hợp.

### 38.2. NOT một mình có thể không hiệu quả

Một query chỉ loại trừ một từ khỏi toàn bộ tài liệu, không có từ khóa dương chọn lọc, có thể cần xét rất nhiều hàng. Không hứa rằng GIN biến mọi phép `NOT` thành index search hiệu quả.

## 39. Truy vấn ngắn, stop words và vector rỗng

Tùy dictionary, những từ phổ biến có thể bị loại khỏi vector/query. Khi `tsquery` sau phân tích không còn lexeme hữu ích, câu `@@` có thể không khớp như người dùng mong đợi.

Ví dụ với cấu hình tiếng Anh:

```sql
SELECT
    plainto_tsquery('english', 'the and or') AS query_terms;
```

Kết quả có thể là một tsquery rỗng vì toàn stop words trong dictionary tương ứng.

### 39.1. Không dùng kết quả trống như “không có tài liệu” theo phản xạ

API nên phân biệt:

- Từ khóa đầu vào rỗng.
- Từ khóa chỉ có stop words.
- Từ khóa quá ngắn so với chính sách.
- Từ khóa hợp lệ nhưng không match.

Tùy UX, có thể trả thông báo giúp người dùng sửa query hoặc hiển thị danh sách theo filter khác, **không tùy tiện chuyển thành quét tất cả documents**.

### 39.2. Kiểm tra có lexeme hữu ích

PostgreSQL có hàm hỗ trợ thông tin query, ví dụ:

```sql
SELECT
    numnode(plainto_tsquery('english', 'the and or'))
        AS number_of_query_nodes;
```

Đây là một tín hiệu kiểm tra cấu trúc query sau parse; cần gắn vào policy sản phẩm khi xử lý queries không còn từ khóa.

## 40. Nhất quán giữa dữ liệu ghi và cấu hình tìm

Nếu bạn index vector bằng:

```sql
to_tsvector('simple', title || ' ' || body)
```

nhưng query bằng:

```sql
plainto_tsquery('english', user_input)
```

thì normalization có thể **không thống nhất**, nhất là stemming/stopwords.

### 40.1. Quy ước configuration

Một hệ thống nên chọn:

```text
search_configuration = simple
searchable_fields = title, body
title_weight = A
body_weight = B
accent_policy = keep accents (lab)
case_policy = parser's configured normalization
query_parser = websearch_to_tsquery
ranking = ts_rank + published_at + document_id
```

Nếu thay đổi configuration, phải có kế hoạch rebuild/recompute vectors và indexes phù hợp. Đừng âm thầm đổi query parser mà không tính ảnh hưởng tới kết quả.

### 40.2. Generated column cập nhật khi row đổi

Khi `title` hoặc `body` được UPDATE, cột `search_vector GENERATED ALWAYS AS (...) STORED` được tính lại theo expression. GIN index liên quan cũng được duy trì. Đây là lợi ích về đồng bộ, nhưng có write overhead.

### 40.3. Vẫn cần kiểm tra dữ liệu cũ sau migration

Nếu bổ sung search_vector cho bảng có hàng triệu rows, migration có thể tốn CPU/disk và lock theo cú pháp/phương án triển khai. Đánh giá workload và migration windows thay vì xem một `ALTER TABLE` trên production như câu lệnh lab không rủi ro.

## 41. Tìm theo nhiều ngôn ngữ trong một bảng

Một trang tài liệu có thể có tiếng Việt, tiếng Anh và tên công nghệ. Không nhất thiết một dictionary phù hợp tất cả.

Các hướng thiết kế:

- Một cấu hình thống nhất như `simple` và chấp nhận giới hạn.
- Lưu language/config cho tài liệu, tạo vector theo cấu hình phù hợp khi kiến trúc cho phép.
- Tách search vectors theo nhóm ngôn ngữ.
- Kết hợp FTS với normalization/search service chuyên dụng cho từ ghép và từ đồng nghĩa.

### 41.1. Query cần biết đang so với vector nào

Nếu tài liệu tiếng Anh được stem theo `english` nhưng input tiếng Việt dùng `simple`, việc match và ranking không nên được giả định đồng nhất. Hệ thống phải xác định cách route query và giải thích UX.

### 41.2. Tìm tên riêng và thuật ngữ kỹ thuật

Với `PostgreSQL`, `Java`, `JDBC` và các tên sản phẩm, có thể muốn giữ các token nguyên vẹn hơn so với stemming tự động. Dữ liệu đa ngôn ngữ cần thử các truy vấn thực tế, không chỉ dùng một benchmark tiếng Anh.

## 42. Kết hợp tìm chính xác, tiền tố và FTS trong API

Một API tìm kiếm có thể công bố mode:

```text
GET /documents?mode=exact&q=PostgreSQL
GET /documents?mode=prefix&q=Postg
GET /documents?mode=contains&q=gres
GET /documents?mode=full_text&q=PostgreSQL%20JDBC
```

Đây là những URL **minh họa API**, không phải endpoint đang tồn tại.

### 42.1. Mapping mode ↔ SQL rõ ràng

| mode | SQL chính | Tính năng |
| --- | --- | --- |
| `exact` | `title = ?` | Chính xác toàn title |
| `prefix` | `lower(title) LIKE ? ESCAPE '!'` | Tiền tố sau lowercase |
| `contains` | `title ILIKE ? ESCAPE '!'` | Chuỗi con bỏ qua case |
| `full_text` | `search_vector @@ websearch_to_tsquery('simple', ?)` | Lexeme search |

Những query này **không thể bảo đảm cùng ranking**:

- Exact có thể ưu tiên một kết quả rồi fallback.
- Prefix có thể sort theo title hoặc tần suất/độ phổ biến.
- Contains có thể ưu tiên match ở đầu title hơn match ở cuối.
- FTS dùng relevance score từ vector và tsquery.

Định nghĩa UX/ranking rõ giúp người dùng hiểu tại sao cùng từ khóa cho kết quả khác.

### 42.2. Không để client gửi SQL operator tùy ý

Tầng service nên map enum:

```java
enum SearchMode {
    EXACT, PREFIX, CONTAINS, FULL_TEXT
}
```

sang **các câu SQL định sẵn** đã được kiểm soát. Không đưa một chuỗi do người dùng nhập thành tên cột/toán tử/SQL condition qua nối string.

### 42.3. Đặt giới hạn và báo lỗi thân thiện

Ví dụ:

- Từ khóa rỗng: trả validation error hoặc top documents theo mode khác được định nghĩa.
- Prefix ngắn một ký tự: có thể chỉ cho autocomplete với limit rất nhỏ.
- Contains ngắn dưới ba ký tự: có thể yêu cầu nhập thêm chữ nếu data/index không cho phép tìm hiệu quả.
- Regex: không mặc định cho tất cả user.
- FTS chỉ stop words: thông báo không có token tìm được.

Giới hạn phải theo dữ liệu sản phẩm, không phải quy tắc cứng của PostgreSQL.

## 43. Bảo mật và tài nguyên của ô tìm kiếm

Không xem mọi search endpoint đều là SELECT “vô hại”.

### 43.1. SQL injection

Dùng `PreparedStatement`/bind parameters. Dù ở trong LIKE, ILIKE, regex hay tsquery, đừng nối raw input vào SQL text.

### 43.2. Wildcard injection

Bind parameter không tự ngăn input `%`/`_` làm thay đổi nghĩa LIKE. Nếu sản phẩm muốn tìm literal, escape wildcard như mục 8–9.

### 43.3. Query complexity

Người dùng có thể gửi:

- Regex rất phức tạp.
- FTS OR nhiều nhánh.
- Query chỉ toàn NOT.
- Substring một ký tự trên bảng khổng lồ.
- LIMIT/OFFSET rất lớn.

Cần budget/timeout, rate limit, xác thực và giới hạn độ phức tạp.

### 43.4. statement_timeout

Ví dụ trong một transaction thử nghiệm:

```sql
BEGIN;
SET LOCAL statement_timeout = '3s';

SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%postgresql%'
LIMIT 20;

COMMIT;
```

Ba giây chỉ là ví dụ. `statement_timeout` giới hạn một statement ở PostgreSQL; ứng dụng còn cần deadline tổng cho request và xử lý cancellation để không giữ connection vô ích.

### 43.5. Quyền và thông tin nhạy cảm

Search không được dùng để vượt authorization. Đặc biệt với tài liệu nội bộ, phải áp filter quyền trước/đồng thời với search và không highlight hoặc rank tài liệu mà user không được phép nhìn.

## 44. Checklist chọn phương pháp tìm

Trước khi viết SQL hãy hỏi:

1. Người dùng cần **cả chuỗi bằng nhau** hay chỉ một phần?
2. Có cần **tiền tố của toàn title**, hay tiền tố của từ ở giữa tài liệu?
3. Có cần tìm **chuỗi con bất kỳ trong một từ**?
4. Có cần regex pattern phức tạp không?
5. Có cần nhiều từ và **AND/OR/phrase/NOT** không?
6. Có cần **ranking** và highlight không?
7. Có phân biệt hoa/thường, dấu tiếng Việt hoặc Unicode normalization không?
8. Dữ liệu dài bao nhiêu, có bao nhiêu documents?
9. Search trên title, body, tags hay mọi field?
10. Có filter tenant/category/date cần áp đúng không?
11. Có B-tree, text_pattern_ops, trigram hoặc GIN FTS index nào phù hợp?
12. Query parameterized có làm planner chọn generic plan khác literal không?
13. Từ khóa một ký tự và query rỗng xử lý thế nào?
14. Có giới hạn page size/timeout/rate limit không?
15. Đã so actual rows, buffers, latency và write overhead chưa?
16. Có test tập kết quả đúng ngữ nghĩa, kể cả dấu %, dấu _, Unicode và case không?

## 45. Bảng những lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `=` và `LIKE '%...%'` cùng nghĩa | = so toàn giá trị, LIKE có wildcard |
| `LIKE 'SQL'` tìm SQL ở bất kỳ vị trí | Không; pattern không có % hai đầu |
| `LIKE 'SQL%'` và `LIKE '%SQL%'` đều dùng B-tree như nhau | Leading wildcard thường ngăn B-tree prefix scan hiệu quả |
| `_` trong LIKE luôn là dấu gạch dưới literal | Nó là wildcard đúng một ký tự |
| Parameter binding khiến `%` thành literal | Không; phải escape wildcard khi cần |
| ILIKE tự bỏ dấu tiếng Việt | Không mặc định |
| Lowercase là chuẩn hóa Unicode đầy đủ | Không |
| LIKE, SIMILAR TO và regex dùng chung grammar | Không |
| `~ 'abc'` yêu cầu cả title chỉ bằng abc | Regex ~ thường có thể match một phần nếu không anchor |
| Có `GIN(search_vector)` thì `ILIKE '%...%'` dùng index đó | Không; operator/expression khác |
| Trigram tự hiểu nghĩa của các từ | Không; chủ yếu dựa trên ký tự |
| pg_trgm luôn nhanh với tìm một ký tự | Keyword quá ngắn khó có trigram chọn lọc |
| FTS là substring search | FTS làm việc theo lexemes |
| `postgr:*` là tiền tố của whole title | Là tiền tố của một lexeme |
| plainto_tsquery tự hiểu cú pháp `OR` trong input | Không như strict/web search grammar |
| to_tsquery luôn nhận input văn bản thuần | Có cú pháp riêng, có thể báo lỗi |
| phraseto_tsquery kiểm tra bytes giống hệt phrase | Match theo vị trí lexeme sau phân tích |
| GIN tự trả tài liệu theo ranking | Thường cần tính rank và sort |
| English FTS luôn phù hợp tiếng Việt | Không |
| Có GIN là không cần VACUUM/ANALYZE | Vẫn cần maintenance/statistics |
| SELECT * tốt hơn vì “đã có index” | Projection rộng có thể tăng heap/TOAST/transfer |
| Seq Scan trong lab 24 rows chứng minh index vô dụng | Planner có thể chọn Seq Scan vì bảng nhỏ |
| ts_headline tự bảo đảm HTML an toàn | Cần escaping/sanitization ở tầng render |
| Search nhanh thì bỏ qua authorization | Không; cần bảo vệ tenant/document access |
| Một query FTS của user luôn tốn ít tài nguyên | Query phổ biến/OR rộng/ranking có thể rất tốn |

## 46. Bài tập thực hành PostgreSQL

Các bài dùng schema `text_search_lab`, trừ khi nói rõ là ví dụ thiết kế. Các bài có extension `pg_trgm`/`unaccent` chỉ thực hiện nếu môi trường học tập cho phép.

1. **Phân loại:** một khách nhập `PostgreSQL` vào ô tìm tên bài, hãy mô tả khác nhau giữa exact, prefix, contains và FTS.
2. **Exact:** viết SQL tìm title bằng đúng `PostgreSQL cơ bản`.
3. **Không exact:** giải thích vì sao `title = 'PostgreSQL'` không tìm được `PostgreSQL cơ bản`.
4. **B-tree equality:** tạo index trên title, dùng EXPLAIN xem scan được chọn.
5. **Case sensitive:** so `title = 'PostgreSQL cơ bản'` và `title = 'postgresql cơ bản'` dưới collation của lab.
6. **Lower equality:** viết `lower(title) = lower(?)` và tạo expression index phù hợp.
7. **Prefix:** viết query `LIKE 'PostgreSQL%'` và kiểm tra các title được khớp.
8. **Không match ở giữa:** tại sao `Tối ưu PostgreSQL` không khớp prefix?
9. **ILIKE prefix:** tìm title bắt đầu bằng `postg` bỏ qua hoa/thường.
10. **Pattern opclass:** tạo B-tree `title text_pattern_ops` và giải thích khi nào nó hữu ích.
11. **Lower pattern index:** tạo `lower(title) text_pattern_ops`; query phải viết thế nào để dùng index đó?
12. **Contains:** tìm title chứa `postgresql` ở mọi vị trí, không phân biệt case.
13. **B-tree limitation:** vì sao `'%postgresql%'` không tận dụng prefix B-tree như `'postgresql%'`?
14. **Wildcards:** giải thích `%` và `_` trong PostgreSQL LIKE.
15. **Dấu phần trăm:** tìm title bắt đầu bằng literal `50%` dùng `ESCAPE '!'`.
16. **Dấu gạch dưới:** tìm literal `A_B`, so `'%A_B%'` với `'%A!_B%' ESCAPE '!'`.
17. **Escape character:** mô tả cách tìm dấu `!` literal khi `!` là escape.
18. **PreparedStatement:** viết Java tạo pattern `"%"+escapedInput+"%"` và bind parameter an toàn.
19. **SQL injection:** phân biệt SQL injection với wildcard injection trong LIKE.
20. **SIMILAR TO:** tìm những title bắt đầu bằng PostgreSQL hoặc MySQL.
21. **Regex:** tìm title bắt đầu bằng `PostgreSQL` với `~ '^PostgreSQL'`.
22. **Case-insensitive regex:** chuyển ví dụ trên sang `~*`.
23. **Anchor:** giải thích khác nhau giữa `~ 'SQL'` và `~ '^SQL$'`.
24. **Validation regex:** kiểm tra chuỗi mã mẫu `AB-1234` bằng `^[A-Z]{2}-[0-9]{4}$`.
25. **Regex safety:** liệt kê ba rủi ro khi cho input regex tự do từ client.
26. **pg_trgm:** tạo extension trên database test được phép và GIN `gin_trgm_ops` trên title.
27. **Trigram ngắn:** vì sao `ILIKE '%a%'` khó dùng trigram index hiệu quả?
28. **GIN vs GiST trigram:** nêu tình huống cân nhắc từng phương pháp theo operator/workload.
29. **Similarity:** dùng hàm similarity với input `Postgres` và giải thích nó khác contains.
30. **FTS lexeme:** chạy `to_tsvector('simple', ...)` và quan sát lexemes/vị trí.
31. **Language config:** so simple với english cho `Running runners run`; vì sao không dùng english mặc định cho nội dung Việt?
32. **plainto_tsquery:** dùng input `PostgreSQL JDBC`, giải thích ngữ nghĩa AND.
33. **FTS search:** query `search_vector @@ plainto_tsquery('simple','PostgreSQL')`.
34. **Title vs body:** tìm một document FTS match nhờ body dù title không chứa.
35. **Phân biệt summary:** vì sao một document chỉ nhắc keyword trong summary có thể không match vector trong lab?
36. **Phrase:** dùng `phraseto_tsquery('simple', 'Java JDBC')` và so với plainto_tsquery.
37. **Web search syntax:** thử `'"Java JDBC" OR PostgreSQL -MySQL'` với websearch_to_tsquery.
38. **Strict tsquery:** viết `postgresql & (jdbc | sql)` bằng to_tsquery.
39. **Prefix lexeme:** dùng `postgr:*` và giải thích không phải title-prefix.
40. **FTS vs substring:** chạy `to_tsvector('simple','PostgreSQL') @@ plainto_tsquery('simple','sql')` và `'PostgreSQL' ILIKE '%sql%'`.
41. **GIN FTS:** tạo index trên generated `search_vector` và đo EXPLAIN.
42. **Ranking:** sắp xếp bằng `ts_rank(search_vector,q) DESC`, thêm document_id tie-breaker.
43. **Weight:** giải thích title weight A và body weight B trong schema lab.
44. **ts_rank_cd:** so kết quả rank với ts_rank và nêu ý nghĩa cover density.
45. **Highlight:** dùng ts_headline cho body và nêu cách chống HTML injection/XSS.
46. **Vector generated:** UPDATE một body trong lab và kiểm tra search_vector thay đổi; lý giải write overhead.
47. **Nạp lớn:** tạo thêm 100.000 documents trong lab, ANALYZE, đo B-tree/trigram/FTS.
48. **Index choice:** lập bảng chọn chỉ mục cho exact, prefix, contains, FTS.
49. **EXPLAIN:** đọc Index Cond, Filter, Bitmap Heap Scan, rows và buffers nếu xuất hiện.
50. **Thống kê:** vì sao bảng 24 rows có thể dùng Seq Scan dù index tồn tại?
51. **Từ khóa ngắn:** thiết kế UX cho contains chỉ có một ký tự.
52. **Dữ liệu có dấu:** giải thích tại sao `toi uu` không mặc định match `tối ưu`.
53. **unaccent:** nêu lợi ích và lý do không vội khai báo hàm unaccent IMMUTABLE trong expression index.
54. **Từ đồng nghĩa:** thiết kế cách tìm `CSDL` tương đương `cơ sở dữ liệu`.
55. **Tiếng Việt:** giải thích hạn chế của từ ghép với `simple` configuration.
56. **Hỗn hợp ngôn ngữ:** đề xuất cách quản lý cấu hình FTS nếu tài liệu có tiếng Việt/Anh.
57. **Empty query:** sử dụng `numnode` để nhận biết một truy vấn toàn stop words trong english config.
58. **Category filter:** kết hợp `category='database'` với FTS thay vì đưa category vào query text.
59. **Partial index:** nêu khi nào partial FTS index cho tài liệu published có thể hữu ích.
60. **Search API:** phác họa các mode EXACT/PREFIX/CONTAINS/FULL_TEXT và mapping SQL.
61. **Pagination:** vì sao ORDER BY rank cần tie-breaker và OFFSET sâu vẫn đắt?
62. **Keyset ranking:** nêu rủi ro khi cursor chứa rank float và dữ liệu đang thay đổi.
63. **Auth:** thiết kế query search theo tenant mà không lộ tài liệu tenant khác.
64. **Performance:** đo cả SELECT latency, GIN size, UPDATE overhead và request P95.
65. **Sự tương đương:** cho một input, chứng minh exact/prefix/contains/FTS có thể trả bốn tập kết quả khác nhau.
66. **Thiết kế tổng hợp:** ứng dụng có SKU search, title autocomplete và article body search; chọn ba query patterns, indexes, normalization, timeout và tests thích hợp.

## 47. Bộ câu hỏi đánh giá thiết kế tìm kiếm

Một đề xuất:

```sql
SELECT *
FROM documents
WHERE title ILIKE '%' || :q || '%';
```

cần được review bằng những câu hỏi sau:

1. **Yêu cầu tìm kiếm là gì?** Khớp chuỗi con thật sự hay phải tìm nguyên từ?
2. **Có cần truyền SELECT * không?** Có cột TEXT/JSONB rất dài?
3. **Client có thể nhập %/_ không?** Có escape wildcard nếu tìm literal?
4. **Có bind parameter đúng?** Không nối raw user input vào SQL text?
5. **Search term tối thiểu bao nhiêu ký tự?** Một ký tự có tạo quá nhiều matches?
6. **Collation/case/accent semantics đã được xác nhận?**
7. **Có cần ranking không?** Nếu có, ILIKE không tự tạo relevance score tốt.
8. **Có thể dùng B-tree prefix không?** Nếu UI chỉ tìm đầu title, sao lại thêm % ở đầu?
9. **Nếu cần substring, pg_trgm có phù hợp không?** Đã đo và có quyền extension?
10. **Nếu cần nội dung nhiều từ, FTS có đúng ngữ nghĩa không?**
11. **Nếu dữ liệu tiếng Việt, tokenization/không dấu có đạt yêu cầu không?**
12. **Index có được planner dùng trên query thực không?** Generic/custom plans?
13. **Từ khóa phổ biến gây scan/ranking quá nhiều candidates không?**
14. **Có tenant/permission filter, limit và timeout không?**
15. **Có kiểm thử với case, dấu, wildcard, phrase, keyword rỗng không?**
16. **Đã đo chi phí ghi, storage và maintainability của index chưa?**

Một implementation chỉ “có một SELECT chạy được” chưa đủ để khẳng định chức năng search đúng và vận hành bền vững.

## 48. Tổng kết

Sự khác nhau cốt lõi:

```text
TÌM CHÍNH XÁC
  title = 'PostgreSQL'
  -> So sánh toàn bộ giá trị
  -> B-tree thường phù hợp

TÌM TIỀN TỐ
  title LIKE 'PostgreSQL%'
  -> Bắt đầu bằng chuỗi cố định
  -> B-tree / text_pattern_ops / lower expression

TÌM MẪU / CHUỖI CON
  title ILIKE '%postgresql%'
  title ~* '^postgresql'
  -> Match ở cấp ký tự theo wildcard/regex
  -> B-tree prefix không giải quyết mọi mẫu
  -> pg_trgm hữu ích cho nhiều substring/pattern workloads

TÌM TOÀN VĂN
  search_vector @@ plainto_tsquery('simple', 'PostgreSQL')
  -> Token/lexeme search trên các trường đã index
  -> GIN tsvector, tsquery, ranking/phrase/prefix lexeme
  -> Không đồng nghĩa so substring ký tự bất kỳ
```

Các nguyên tắc quan trọng nhất:

- **Chọn ngữ nghĩa trước, index sau.** Một LIKE substring không tự tương đương tìm từ trong nội dung.
- **`=` so cả giá trị; `LIKE 'abc%'` là prefix; `LIKE '%abc%'` là contains.** Vị trí dấu `%` quyết định mạnh đến ý nghĩa và khả năng dùng B-tree.
- **`%` và `_` là wildcard của LIKE.** Nếu người dùng nhập chúng như dữ liệu, phải escape ngay cả khi đã bind SQL parameter.
- **`ILIKE` giải quyết case-insensitive pattern theo quy tắc phù hợp, không tự giải quyết accent-insensitive tiếng Việt.**
- **B-tree/text_pattern_ops phù hợp equality/prefix; `pg_trgm` phù hợp nhiều substring/pattern searches; GIN tsvector dành cho FTS `@@`.** Không tự coi các index này có thể thay thế nhau.
- **FTS tìm lexemes, không phải mọi đoạn ký tự.** Dùng `plainto_tsquery` cho text đơn giản, `phraseto_tsquery` cho phrase, `websearch_to_tsquery` cho cú pháp tìm web và `to_tsquery` cho expression có kiểm soát.
- **Generated tsvector và GIN giúp truy vấn toàn văn ở quy mô lớn**, nhưng thêm chi phí CPU/storage/maintenance khi ghi. GIN cũng không tự xếp hạng theo relevance.
- **Tiếng Việt cần chính sách rõ về dấu, tách từ, viết tắt và đồng nghĩa.** Cấu hình `simple` hữu ích trong lab nhưng không bảo đảm chất lượng ngôn ngữ sản phẩm.
- **Dùng EXPLAIN (ANALYZE, BUFFERS) trên truy vấn thật** để quyết định index và theo dõi cả chi phí ghi, độ rộng payload, số kết quả và latency.
- **Giữ search endpoint an toàn:** bind parameters, validate pattern/query complexity, lọc quyền dữ liệu, giới hạn page size, timeout và xử lý kết quả highlight an toàn.

Khi phân biệt rõ **khớp chính xác, bắt đầu bằng, khớp mẫu ký tự và tìm theo lexeme**, bạn sẽ chọn được SQL, chỉ mục và trải nghiệm tìm kiếm phù hợp cho PostgreSQL — không chỉ “tìm ra vài dòng” mà còn trả **đúng tập tài liệu, đúng mức độ liên quan và đúng chi phí vận hành**.
