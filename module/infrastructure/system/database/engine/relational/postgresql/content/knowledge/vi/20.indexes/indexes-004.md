# GIN, dữ liệu nhiều thành phần và tìm kiếm văn bản trong PostgreSQL

Một chỉ mục B-tree rất hiệu quả cho những câu hỏi như “hàng nào có `id = 42`?”, “đơn nào có `created_at >= ...`?” hoặc “lấy các hàng theo thứ tự điểm giảm dần?”. Nhưng nhiều ứng dụng hiện đại không chỉ lưu mỗi giá trị đơn: một bản ghi có thể mang **mảng nhãn**, **tài liệu JSONB**, **các từ khóa của một bài viết** hoặc **văn bản dài**.

Ví dụ một tài liệu có:

```text
doc_id = 101
tags = ['postgresql', 'gin', 'database']
attributes = {
  "type": "guide",
  "skills": ["sql", "indexing"],
  "features": {"fts": true, "jsonb": true}
}
title = "PostgreSQL GIN index"
description = "GIN indexes support arrays JSONB and full text search"
```

Ứng dụng cần tìm:

- “Các tài liệu có **đồng thời** nhãn `postgresql` và `gin`?”
- “Các tài liệu có **ít nhất một** nhãn `fts` hoặc `array`?”
- “JSONB có chứa cấu trúc `{"features":{"fts":true}}`?”
- “Các bài có cụm từ **full text**?”
- “Gõ `postgre` để tìm gần đúng những tên chứa PostgreSQL?”

Với những truy vấn này, PostgreSQL cung cấp **GIN — Generalized Inverted Index**: một họ chỉ mục ngược ánh xạ từ *thành phần có thể tìm kiếm* (một phần tử mảng, key/value của JSONB, lexeme của văn bản, trigram...) đến các hàng chứa thành phần đó.

GIN là một công cụ rất mạnh, nhưng **không phải index mặc định tốt nhất cho mọi cột**. Khả năng sử dụng GIN phụ thuộc **kiểu dữ liệu, toán tử truy vấn, operator class**, độ chọn lọc, số lượng cập nhật và chi phí bảo trì. Bài học này đi từ cơ chế inverted index đến truy vấn thực tế, full-text search, `pg_trgm`, kế hoạch thực thi, pending list và lựa chọn triển khai an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa **B-tree** và **GIN inverted index**.
2. Hiểu vì sao GIN phù hợp với dữ liệu có nhiều thành phần trong một hàng: `TEXT[]`, `JSONB` và `TSVECTOR`.
3. Viết `CREATE INDEX ... USING GIN` và chọn operator class phù hợp.
4. Sử dụng các toán tử mảng `@>`, `<@`, `&&` và phân biệt chúng với `= ANY(...)`.
5. Tìm kiếm JSONB bằng `@>`, `?`, `?|`, `?&` và hiểu ý nghĩa key tồn tại ở **mức cao nhất**.
6. So sánh `jsonb_ops` với `jsonb_path_ops`, các toán tử hỗ trợ và đánh đổi kích thước/chọn lọc.
7. Dùng `to_tsvector`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`, `to_tsquery` và `@@`.
8. Kết hợp `setweight`, `ts_rank`, `ts_rank_cd`, `ts_headline` để xây dựng kết quả tìm kiếm có xếp hạng.
9. Hiểu hạn chế của PostgreSQL FTS tích hợp đối với **tiếng Việt** và tầm quan trọng của tách từ, dấu, cấu hình từ điển.
10. Phân biệt **full-text search** với tìm chuỗi con `LIKE/ILIKE` và tìm gần đúng qua extension `pg_trgm`.
11. Đọc `EXPLAIN (ANALYZE, BUFFERS)` với `Bitmap Index Scan`, `Bitmap Heap Scan`, `Recheck Cond` và `Rows Removed by Index Recheck`.
12. Phân tích tác động của `fastupdate`, **GIN pending list**, VACUUM, insert/update và các loại index khác.
13. Lựa chọn giữa GIN, GiST, B-tree và index biểu thức theo câu truy vấn, không chỉ theo tên kiểu cột.
14. Thực hiện một lab SQL có thể chạy lại, thử cả ca dữ liệu trùng nhãn, JSONB lồng nhau và truy vấn kết hợp nhiều điều kiện.

**Phạm vi:** PostgreSQL hiện đại. Một số operator class, khả năng lập chỉ mục JSONPath, view thống kê và tính năng extension thay đổi theo phiên bản; khi triển khai phải xem phiên bản của hệ thống thật. Các câu `DROP TABLE`, `CREATE INDEX`, `UPDATE` và tạo extension trong bài chỉ dành cho môi trường thử nghiệm được phép thao tác.

---

## 2. Từ B-tree đến inverted index

Giả sử bảng tài liệu có một cột `tags TEXT[]`:

```text
doc_id | tags
-------+-----------------------------------
101    | {postgresql,gin,database}
102    | {postgresql,jsonb,database}
103    | {postgresql,fts,search}
104    | {postgresql,trigram,search}
105    | {postgresql,array,database}
106    | {postgresql,fts,viet}
107    | {database,search,design}
```

Một B-tree truyền thống sắp xếp **giá trị khóa của hàng**, ví dụ:

```text
id=101 -> hàng 101
id=102 -> hàng 102
id=103 -> hàng 103
...
```

Còn inverted index ý niệm lập ánh xạ ngược:

```text
"postgresql" -> {101,102,103,104,105,106}
"gin"        -> {101}
"jsonb"      -> {102}
"fts"        -> {103,106}
"search"     -> {103,104,107}
"database"   -> {101,102,105,107}
```

Khi tìm `tags @> ARRAY['postgresql','fts']`, engine có thể giao các tập ứng viên cho “postgresql” và “fts”, rồi xác nhận những hàng phù hợp.

### 2.1. Một GIN entry không phải một hàng

Ý tưởng cốt lõi:

- **Key của GIN** là thành phần được operator class trích xuất từ giá trị cột.
- Mỗi key có danh sách hoặc cấu trúc các **posting references** tới các hàng tương ứng.
- Với key phổ biến, tập posting có thể rất lớn và cần cấu trúc lưu trữ riêng.
- Khi tìm nhiều key, index có thể kết hợp các tập ứng viên, sau đó kiểm tra điều kiện thực tế theo kế hoạch PostgreSQL.

Không hiểu ví dụ này là cách mô tả mọi byte lưu trữ. GIN còn có posting lists, posting trees, pending list và metadata nội bộ.

### 2.2. Hàng có nhiều thành phần không nhất thiết tạo một entry duy nhất

Một giá trị `tags = ARRAY['postgresql','gin','database']` đóng góp thông tin tìm kiếm cho nhiều key. Tương tự:

- Một `JSONB` object có nhiều đường dẫn/key/value.
- Một `tsvector` chứa nhiều **lexeme**.
- Một chuỗi text được dùng với `gin_trgm_ops` đóng góp nhiều **trigram**.

Đó cũng là nguyên nhân INSERT và UPDATE kiểu dữ liệu nhiều thành phần có thể làm GIN tốn công việc hơn một index B-tree nhỏ.

### 2.3. Khi nào GIN có ý nghĩa?

GIN đặc biệt có ích khi:

- Mỗi hàng chứa **nhiều phần tử/từ khóa**.
- Query thường hỏi một hay nhiều thành phần **có xuất hiện không**.
- Điều kiện có toán tử được operator class GIN hỗ trợ.
- Tập ứng viên đủ chọn lọc để index scan có lợi hơn quét toàn bảng.

GIN thường không phải lựa chọn đầu tiên khi chỉ cần:

```sql
WHERE id = 101
ORDER BY id
LIMIT 10;
```

Ở đây B-tree trên khóa chính hoặc cột sắp xếp mới là ứng viên rõ ràng.

---

## 3. Operator class quyết định index trả lời được câu hỏi nào

Cú pháp tổng quát:

```sql
CREATE INDEX index_name
ON table_name
USING GIN (indexed_expression operator_class);
```

Có thể bỏ `operator_class` nếu kiểu dữ liệu có GIN operator class mặc định phù hợp.

| Dữ liệu | Operator class GIN thường dùng | Truy vấn tiêu biểu |
| --- | --- | --- |
| `TEXT[]`, mảng phù hợp | `array_ops` (mặc định cho array) | `@>`, `<@`, `&&`, `=` |
| `JSONB` | `jsonb_ops` (mặc định) | `@>`, `?`, `?|`, `?&`, `@?`, `@@` |
| `JSONB` | `jsonb_path_ops` | `@>`, `@?`, `@@` |
| `TSVECTOR` | `tsvector_ops` (mặc định) | Toán tử đối sánh truy vấn toàn văn `@@` |
| `TEXT` với extension `pg_trgm` | `gin_trgm_ops` | Tìm gần đúng/trigram, `LIKE`/`ILIKE`, toán tử tương thích |

**Điểm quan trọng:** có GIN index trên một cột **không có nghĩa mọi toán tử trên cột đó đều dùng được index**. Planner chỉ có thể tận dụng những toán tử và biểu thức phù hợp operator class của index.

### 3.1. Cùng JSONB, hai operator class khác nhau

```sql
CREATE INDEX idx_attributes_ops
ON documents USING GIN (attributes jsonb_ops);
```

và:

```sql
CREATE INDEX idx_attributes_path
ON documents USING GIN (attributes jsonb_path_ops);
```

có thiết kế và phạm vi toán tử khác nhau. Không coi `jsonb_path_ops` là phiên bản “luôn nhanh hơn” của `jsonb_ops`.

### 3.2. Index trên biểu thức khác index trên toàn cột

Giả sử query:

```sql
WHERE attributes -> 'features' ? 'fts'
```

Toán tử `?` được áp dụng cho kết quả của biểu thức `attributes -> 'features'`, không áp dụng trực tiếp cho `attributes`. Muốn index hóa đúng biểu thức đó, có thể dùng:

```sql
CREATE INDEX idx_features
ON documents USING GIN ((attributes -> 'features'));
```

hoặc viết lại câu hỏi thành containment trực tiếp trên toàn JSONB nếu ngữ nghĩa phù hợp:

```sql
WHERE attributes @> '{"features":{"fts":true}}'::jsonb
```

Hai cách đặt câu hỏi không hoàn toàn tương đương: tồn tại key `fts` khác với kiểm tra key `fts` có giá trị `true`.

---

## 4. Bộ dữ liệu lab thống nhất

Để các ví dụ có thể chạy lại, ta tạo bảng tài liệu chứa:

- `tags TEXT[]`: mảng nhãn.
- `attributes JSONB`: cấu trúc thuộc tính.
- `title` và `description`: nội dung text.
- `search_vector TSVECTOR`: representation cho full-text search.
- `locale`: ngôn ngữ khai báo để minh họa yêu cầu xử lý đa ngữ.

> **Cảnh báo:** `DROP TABLE IF EXISTS` xóa bảng lab có cùng tên. Chỉ chạy trên **database thử nghiệm** và khi được phép reset dữ liệu.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS gin_lab;

DROP TABLE IF EXISTS gin_lab.documents;

CREATE TABLE gin_lab.documents (
    doc_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    attributes JSONB NOT NULL DEFAULT '{}'::JSONB,
    locale TEXT NOT NULL DEFAULT 'en',
    search_vector TSVECTOR
        GENERATED ALWAYS AS (
            setweight(
                to_tsvector('simple'::REGCONFIG, coalesce(title, '')),
                'A'
            )
            ||
            setweight(
                to_tsvector(
                    'simple'::REGCONFIG, coalesce(description, '')
                ),
                'B'
            )
        ) STORED
);
```

Ở đây:

- `to_tsvector('simple'::REGCONFIG, ...)` dùng cấu hình tìm kiếm cố định, vì hàm hai đối số với `REGCONFIG` rõ ràng có thể được dùng trong biểu thức generated column phù hợp.
- `setweight(...,'A')` cho title, `'B'` cho description. Có thể dùng các trọng số A/B/C/D khi xếp hạng.
- `||` nối hai tsvector; vị trí lexeme ở vector thứ hai được điều chỉnh theo vector thứ nhất.
- Đây là **STORED generated column**, được PostgreSQL tính lại khi hàng thay đổi các cột phụ thuộc, không cần client tự cập nhật.
- Ta cố ý dùng `simple` để học cơ chế chung và quan sát tiếng Việt, **không giả định simple có tách từ tiếng Việt chất lượng cao**.

### 4.2. Nạp tám tài liệu

```sql
INSERT INTO gin_lab.documents (
    doc_id, title, description,
    tags, attributes, locale
)
VALUES
(
    101,
    'PostgreSQL GIN index',
    'GIN indexes support arrays JSONB and full text search',
    ARRAY['postgresql','gin','database']::TEXT[],
    '{"type":"guide","level":"advanced",
       "skills":["sql","indexing"],
       "features":{"fts":true,"jsonb":true}}'::JSONB,
    'en'
),
(
    102,
    'JSONB catalog',
    'JSONB containment and top level key operators',
    ARRAY['postgresql','jsonb','database']::TEXT[],
    '{"type":"tutorial","level":"intermediate",
       "skills":["jsonb","sql"],
       "features":{"fts":false,"jsonb":true}}'::JSONB,
    'en'
),
(
    103,
    'Full text search',
    'PostgreSQL tsvector and tsquery rank text documents',
    ARRAY['postgresql','fts','search']::TEXT[],
    '{"type":"guide","level":"advanced",
       "skills":["fts","ranking"],
       "features":{"fts":true,"jsonb":false}}'::JSONB,
    'en'
),
(
    104,
    'Search with trigrams',
    'Trigram similarity supports fuzzy matching',
    ARRAY['postgresql','trigram','search']::TEXT[],
    '{"type":"tutorial","level":"beginner",
       "skills":["trigram"],
       "features":{"fts":false}}'::JSONB,
    'en'
),
(
    105,
    'Indexing arrays',
    'Array overlaps and containment with GIN',
    ARRAY['postgresql','array','database']::TEXT[],
    '{"type":"reference","level":"beginner",
       "skills":["array","sql"],
       "features":{"jsonb":false}}'::JSONB,
    'en'
),
(
    106,
    'Tìm kiếm văn bản',
    'Chỉ mục GIN cho tiếng Việt cần cân nhắc tách từ',
    ARRAY['postgresql','fts','viet']::TEXT[],
    '{"type":"guide","level":"intermediate",
       "skills":["fts","vietnamese"],
       "features":{"fts":true}}'::JSONB,
    'vi'
),
(
    107,
    'Search architecture',
    'GIN and B-tree serve different access patterns',
    ARRAY['database','search','design']::TEXT[],
    '{"type":"article","level":"advanced",
       "skills":["architecture"],
       "features":{}}'::JSONB,
    'en'
),
(
    108,
    'Empty metadata',
    'Minimal jsonb object and empty array examples',
    ARRAY[]::TEXT[],
    '{"type":"note","skills":[],"features":{}}'::JSONB,
    'en'
);

ANALYZE gin_lab.documents;
```

### 4.3. Kiểm tra dữ liệu

```sql
SELECT doc_id, title, tags, attributes, search_vector
FROM gin_lab.documents
ORDER BY doc_id;
```

Cột `search_vector` không chứa một bản sao raw text đơn thuần, mà là các **lexeme** được parser và dictionary xử lý, kèm vị trí và trọng số nếu có.

### 4.4. Tạo các GIN index cơ bản

```sql
CREATE INDEX idx_documents_tags_gin
    ON gin_lab.documents USING GIN (tags);

CREATE INDEX idx_documents_attributes_ops_gin
    ON gin_lab.documents USING GIN (attributes jsonb_ops);

CREATE INDEX idx_documents_search_gin
    ON gin_lab.documents USING GIN (search_vector);

ANALYZE gin_lab.documents;
```

Đây là ba index riêng cho ba câu hỏi khác nhau. Trong thực tế không nên tạo mọi index chỉ vì “có thể”: cần kiểm tra workload đọc, số lần UPDATE và dung lượng.

---

## 5. GIN với mảng: @>, <@ và &&

Mảng PostgreSQL lưu nhiều phần tử trong một giá trị:

```sql
SELECT ARRAY['postgresql','gin','database']::TEXT[];
```

GIN có thể tạo các khóa tìm kiếm từ phần tử mảng để giúp những toán tử tương thích.

### 5.1. @> — mảng chứa các phần tử yêu cầu

Tìm tài liệu có **cả hai nhãn** `postgresql` và `fts`:

```sql
SELECT doc_id, title, tags
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql','fts']::TEXT[]
ORDER BY doc_id;
```

Với dữ liệu lab, hai hàng được chọn là:

| doc_id | title |
| ---: | --- |
| 103 | Full text search |
| 106 | Tìm kiếm văn bản |

`@>` là toán tử **contains**: mảng bên trái có các phần tử được yêu cầu ở mảng bên phải.

### 5.2. && — có giao ít nhất một phần tử

```sql
SELECT doc_id, title, tags
FROM gin_lab.documents
WHERE tags && ARRAY['fts','array']::TEXT[]
ORDER BY doc_id;
```

Truy vấn chọn các tài liệu có nhãn `fts` **hoặc** `array` (trong lab: 103, 105, 106).

### 5.3. <@ — mảng nằm trong mảng khác

```sql
SELECT doc_id, title, tags
FROM gin_lab.documents
WHERE tags <@ ARRAY[
    'postgresql','gin','database','fts','search','viet'
]::TEXT[]
ORDER BY doc_id;
```

Với `<@`, mọi phần tử của mảng trái phải nằm trong tập phần tử của mảng phải theo semantics của toán tử. Đó không phải phép hỏi “chỉ cần một nhãn trùng”.

### 5.4. Mảng rỗng và phần tử trùng

Một số góc biên:

```sql
SELECT
    ARRAY['a','a']::TEXT[] @> ARRAY['a']::TEXT[]
        AS duplicate_contains_a,
    ARRAY['a']::TEXT[] @> ARRAY['a','a']::TEXT[]
        AS a_contains_duplicate_request,
    ARRAY[]::TEXT[] && ARRAY['a']::TEXT[]
        AS empty_overlap_a;
```

Với toán tử contains của array, bản sao trùng thường **không được coi là số lượng cần đếm**. Nếu nghiệp vụ cần “phần tử a xuất hiện ít nhất hai lần”, phải viết logic đếm phù hợp; không dùng `@>` để suy ra multiplicity.

Một mảng rỗng không overlap với mảng chỉ chứa phần tử `a`.

### 5.5. Vì sao = ANY(tags) không tương đương cho mục đích index?

Hai câu hỏi logic có thể giống nhau với phần tử đơn:

```sql
WHERE 'fts' = ANY(tags)
```

và:

```sql
WHERE tags @> ARRAY['fts']::TEXT[]
```

nhưng GIN `array_ops` được thiết kế để hỗ trợ **toán tử mảng** như `@>`. Không mặc định planner có thể dùng GIN array index cho dạng scalar `= ANY(tags)`.

Nếu muốn tận dụng GIN trong một truy vấn chứa phần tử, ưu tiên biểu đạt điều kiện bằng toán tử nằm trong operator class, và xác nhận bằng `EXPLAIN`.

### 5.6. NULL và giá trị không nhất quán

Mảng có thể chứa NULL; phép đối sánh với NULL có semantics riêng. Với nhãn tìm kiếm, thường nên:

- Chuẩn hóa nhãn trước khi lưu (chữ thường, khoảng trắng, không nhập duplicate nếu nghiệp vụ không cần).
- Tránh phần tử NULL nếu không có ý nghĩa.
- Dùng constraint hoặc logic ứng dụng để thống nhất nhãn.
- Không trộn nhãn có dấu/không dấu mà kỳ vọng phép bằng tự nhận diện là cùng một từ.

GIN giúp tìm nhanh các giá trị đã lưu, **không tự chuẩn hóa dữ liệu**.

---

## 6. JSONB: toán tử containment @>

`JSONB` lưu cấu trúc key/value, object và array. GIN cho phép lập chỉ mục các thành phần để tìm kiếm điều kiện trong tài liệu.

Ví dụ thuộc tính doc 101:

```json
{
  "type": "guide",
  "level": "advanced",
  "skills": ["sql", "indexing"],
  "features": {
    "fts": true,
    "jsonb": true
  }
}
```

### 6.1. Tìm JSONB chứa cấu trúc con

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"features":{"fts":true}}'::JSONB
ORDER BY doc_id;
```

Trong lab, các hàng có `features.fts=true` là 101, 103, 106.

Toán tử `@>` xét tính **containment về cấu trúc và giá trị**. Nó khác so sánh raw JSON text; thứ tự key object không làm thay đổi ý nghĩa JSONB.

### 6.2. Tìm array element nằm trong JSONB

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"skills":["sql"]}'::JSONB
ORDER BY doc_id;
```

Kết quả gồm 101 và 102.

Với JSONB containment, mảng có thể chứa nhiều phần tử hơn mảng yêu cầu; thứ tự các phần tử không phải điều kiện so khớp theo ý nghĩa containment. Nhưng không vì vậy mà coi toàn bộ semantics của JSONB array giống mọi phép so sánh mảng SQL.

### 6.3. Tìm key và value cùng lúc

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"type":"guide","level":"advanced"}'::JSONB
ORDER BY doc_id;
```

Với lab: 101 và 103.

Đây là cách rất trực tiếp để mô tả một phần cấu trúc JSONB có giá trị chính xác.

### 6.4. Containment không phải tìm chuỗi con

Nếu `attributes @> '{"type":"gui"}'`, nó **không tự khớp** `"guide"`. JSONB containment đối sánh phần tử JSON theo semantics tương ứng, không thực hiện fuzzy/substring search trên string.

Nếu cần tìm chuỗi con trong giá trị một key, có thể trích string ra rồi dùng toán tử text/index khác:

```sql
SELECT doc_id
FROM gin_lab.documents
WHERE attributes ->> 'type' ILIKE '%gui%';
```

Đây là một câu hỏi **text pattern** chứ không phải JSONB containment; GIN jsonb_ops mặc định không đương nhiên xử lý `ILIKE` trên kết quả `->>`.

---

## 7. JSONB: ?, ?|, ?& và key ở mức nào?

Với `jsonb_ops`, những toán tử existence có thể được hỗ trợ bởi GIN.

### 7.1. ? — key tồn tại ở mức cao nhất

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ? 'skills'
ORDER BY doc_id;
```

Tất cả hàng lab có key `skills` ở top-level.

Nhưng:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ? 'fts';
```

sẽ không tìm được key `fts` nằm **bên trong object `features`** chỉ bằng toán tử top-level `?` trên toàn attributes.

### 7.2. ?| — có ít nhất một key

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ?| ARRAY['type','unknown_key']::TEXT[]
ORDER BY doc_id;
```

Ở đây là phép OR của các key top-level.

### 7.3. ?& — có đầy đủ các key

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes ?& ARRAY['type','skills']::TEXT[]
ORDER BY doc_id;
```

Ở đây là phép AND của các key top-level.

### 7.4. Muốn hỏi key trong object lồng nhau?

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE (attributes -> 'features') ? 'fts'
ORDER BY doc_id;
```

Ở ví dụ này, toán tử `?` được dùng trên **JSONB con**, không phải toàn bộ attributes.

Hoặc nếu muốn xác định giá trị bool:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @> '{"features":{"fts":true}}'::JSONB
ORDER BY doc_id;
```

Hai điều kiện có nghĩa khác nhau:

- `features ? 'fts'`: key tồn tại, kể cả giá trị `false`.
- `@> {"features":{"fts":true}}`: key phải có giá trị JSON boolean `true`.

### 7.5. Top-level array cũng liên quan existence

Trên một giá trị JSONB là **array string**, `?` có thể hỏi string element xuất hiện ở top-level. Nó không phải toán tử đệ quy tìm string ở mọi tầng object/array.

Để kiểm tra cấu trúc sâu, dùng containment, JSONPath hoặc expression index đúng vị trí.

---

## 8. jsonb_ops và jsonb_path_ops: chọn thế nào?

PostgreSQL cung cấp hai GIN operator classes nổi bật cho JSONB:

### 8.1. jsonb_ops (mặc định)

```sql
CREATE INDEX idx_documents_attributes_ops_gin
ON gin_lab.documents
USING GIN (attributes jsonb_ops);
```

Đặc điểm:

- Tương thích với nhiều toán tử trên JSONB, trong đó có `@>`, `?`, `?|`, `?&`, `@?`, `@@`.
- Hữu ích khi workload phải tìm **key tồn tại** hoặc nhiều kiểu điều kiện JSONB.
- Có thể tạo nhiều index entries cho cấu trúc JSONB phức tạp.

### 8.2. jsonb_path_ops

Có thể tạo một index **thứ hai trên lab để thử nghiệm**, nhưng trên production không nên mặc định giữ cả hai:

```sql
CREATE INDEX idx_documents_attributes_path_gin
ON gin_lab.documents
USING GIN (attributes jsonb_path_ops);
```

Đặc điểm chính:

- Hỗ trợ `@>`, `@?`, `@@` trên các phiên bản PostgreSQL hiện đại có hỗ trợ tương ứng.
- **Không hỗ trợ** trực tiếp các toán tử existence `?`, `?|`, `?&` như `jsonb_ops`.
- Thường tạo index nhỏ hơn và có thể tìm containment chọn lọc hơn với những cấu trúc/value phù hợp.
- Có hạn chế đáng chú ý với cấu trúc JSON không có giá trị để index, ví dụ tìm object rỗng `{"a":{}}` có thể kém hiệu quả vì không có index item tương ứng.

### 8.3. So sánh ngắn

| Câu hỏi | jsonb_ops | jsonb_path_ops |
| --- | --- | --- |
| `attributes @> '{"type":"guide"}'` | Có | Có |
| `attributes ? 'type'` | Có | Không |
| `attributes ?| ARRAY['type','level']` | Có | Không |
| `attributes ?& ARRAY['type','level']` | Có | Không |
| JSONPath `@?`/`@@` với biểu thức indexable | Có | Có |
| Truy vấn containment rất chọn lọc | Có thể phù hợp | Thường đáng thử |
| Truy vấn key-existence tổng quát | Phù hợp | Không phải lựa chọn trực tiếp |
| Containment với cấu trúc rỗng | Cần đo | Có thể đặc biệt kém hiệu quả |

**Không có quy tắc “path_ops luôn tốt hơn”.** Phải đo query thực tế và xem operator hỗ trợ, kích thước index, tốc độ ghi và dữ liệu.

### 8.4. Index trên cùng cột không có nghĩa planner dùng cả hai

Khi có `jsonb_ops` và `jsonb_path_ops`, planner cân nhắc chi phí và toán tử để chọn plan. Có thể chọn một index, kết hợp bitmap với index khác, hoặc quét tuần tự khi dữ liệu ít.

Trên bảng lab tám hàng, Seq Scan thường rất hợp lý dù đã có index.

---

## 9. JSONPath: @? và @@

PostgreSQL hỗ trợ các toán tử JSONPath hữu ích cho điều kiện phức tạp trên `JSONB`.

### 9.1. @? — đường dẫn có kết quả phù hợp?

Ví dụ tìm tài liệu có một skill là `sql`:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @? '$.skills[*] ? (@ == "sql")'
ORDER BY doc_id;
```

### 9.2. @@ — đối sánh predicate JSONPath

Ví dụ kiểm tra một giá trị boolean ở đường dẫn:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE attributes @@ '$.features.fts == true'
ORDER BY doc_id;
```

### 9.3. Không phải mọi JSONPath đều được tăng tốc như nhau

GIN có thể trích những điều kiện nhất định từ biểu thức JSONPath, nhất là những đường dẫn đi tới so sánh bằng với giá trị cụ thể. Các biểu thức phức tạp, điều kiện không hỗ trợ trích index hoặc kết hợp đường dẫn đặc thù vẫn có thể cần kiểm tra nhiều hàng.

Do đó:

- “Dùng `@?`” không đủ để cam kết sẽ có Index Scan.
- Operator class jsonb_ops/path_ops khác nhau về những dạng accessor được hỗ trợ cho việc index.
- Cần xem plan với dữ liệu thực tế.
- Một điều kiện `@>` đơn giản có thể rõ ràng và dễ tối ưu hơn JSONPath nếu nó diễn đạt đúng yêu cầu.

---

## 10. Expression index cho JSONB lồng nhau

Nếu ứng dụng thường xuyên hỏi:

```sql
WHERE (attributes -> 'features') ? 'fts'
```

có thể tạo index đúng biểu thức:

```sql
CREATE INDEX idx_documents_features_gin
ON gin_lab.documents
USING GIN ((attributes -> 'features'));
```

Khi đó planner có thể tận dụng GIN operator class của JSONB cho kết quả `attributes -> 'features'`.

### 10.1. Biểu thức trong query phải phù hợp index

Index:

```sql
USING GIN ((attributes -> 'features'))
```

không tự đồng nghĩa với index toàn `attributes`. Nó giúp những query đặt toán tử indexable lên biểu thức tương ứng.

Nếu ứng dụng cần cả existence ở nhiều tầng và containment tổng quát, lựa chọn giữa index toàn JSONB và index biểu thức cần dựa trên workload.

### 10.2. Những cách viết khác có thể có semantics khác

Ví dụ:

```sql
attributes -> 'features' ? 'fts'
```

và:

```sql
attributes @> '{"features":{"fts":true}}'::JSONB
```

khác nhau khi `fts=false`. Vì vậy tối ưu index không được biến một điều kiện “key tồn tại” thành “giá trị true” nếu nghiệp vụ không cho phép.

### 10.3. Khi nào nên chuẩn hóa JSONB ra cột riêng?

Nếu một field JSONB:

- Được filter/join rất thường xuyên.
- Có ràng buộc `NOT NULL`, `UNIQUE` hoặc FK.
- Cần range query/ORDER BY thường xuyên.
- Có tính chất định danh nghiệp vụ.

có thể nên đặt thành **cột SQL riêng**, kèm B-tree hoặc index thích hợp, thay vì mọi truy vấn đều trích JSONB. GIN giúp dữ liệu linh hoạt nhưng không thay thiết kế schema quan hệ khi invariant yêu cầu.

---

## 11. Full-text search: từ văn bản sang tsvector

Full-text search (FTS) không đơn thuần làm `LIKE '%word%'`. PostgreSQL phân tích văn bản thành **lexeme** theo parser và dictionary, có thể chuẩn hóa từ, loại stop words và ghi vị trí.

Ví dụ:

```sql
SELECT to_tsvector(
    'english',
    'PostgreSQL indexes support searching documents'
);
```

Với `english`, một số từ có thể được stem thành dạng chuẩn; output cũng có vị trí. Những gì được giữ/lược phụ thuộc cấu hình dictionary và input.

So với:

```sql
SELECT to_tsvector(
    'simple',
    'PostgreSQL indexes support searching documents'
);
```

Cấu hình `simple` không thực hiện stemming tiếng Anh giống `english`.

### 11.1. tsvector là gì?

`TSVECTOR` là cấu trúc các lexeme đã được phân tích cho mục đích tìm kiếm:

```text
Raw text:
"PostgreSQL full text search"

Conceptual tsvector:
'full':2 'postgresql':1 'search':4 'text':3
```

Đây là ví dụ minh họa; cách hiển thị/lexeme cụ thể phụ thuộc cấu hình, xử lý token và position.

### 11.2. tsquery là gì?

`TSQUERY` biểu diễn điều kiện tìm kiếm:

```text
postgresql & gin
full <-> text
jsonb | array
```

Từ đó `@@` so khớp:

```sql
search_vector @@ some_tsquery
```

GIN có thể tạo index theo lexeme trong `search_vector` để tìm ứng viên phù hợp.

### 11.3. Vì sao không lưu mỗi raw text rồi dùng GIN trực tiếp?

GIN FTS thông thường dùng `TSVECTOR`, không phải tự áp dụng mọi cơ chế phân tích văn bản lên một cột TEXT tùy ý. Bạn có thể:

- Lưu cột `TSVECTOR` và duy trì tự động bằng generated column.
- Tạo GIN **expression index** trên `to_tsvector(config, text)`.
- Dùng cơ chế trigger hoặc code ứng dụng nếu cần pipeline đặc biệt.

Điều quan trọng là **query phải sử dụng cùng chính sách cấu hình/token hóa** với dữ liệu được index.

---

## 12. GIN cho tsvector

Trong lab đã có:

```sql
CREATE INDEX idx_documents_search_gin
ON gin_lab.documents
USING GIN (search_vector);
```

Một truy vấn FTS điển hình:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ plainto_tsquery(
    'simple', 'full text'
)
ORDER BY doc_id;
```

Trong lab, doc 101 và 103 chứa lexeme `full` và `text` trong các trường được lập vector; kết quả phụ thuộc nội dung thực tế và cấu hình `simple`.

### 12.1. plainto_tsquery — phù hợp input bình thường

```sql
SELECT plainto_tsquery('simple', 'postgresql gin');
```

Với input này, biểu thức tsquery khái niệm gần dạng:

```text
'postgresql' & 'gin'
```

Hàm xử lý văn bản thành từ khóa, không kỳ vọng người dùng nhập đúng cú pháp `&`, `|`, `!`.

### 12.2. to_tsquery — cho cú pháp truy vấn có cấu trúc

```sql
SELECT to_tsquery(
    'simple',
    'postgresql & (gin | jsonb)'
);
```

Các toán tử quan trọng:

| Toán tử trong tsquery | Ý nghĩa |
| --- | --- |
| `&` | AND |
| `|` | OR |
| `!` | NOT |
| `<->` | Từ/cụm ở vị trí kề nhau |
| `<N>` | Khoảng cách vị trí giữa những lexeme |
| `:*` | Prefix match lexeme ở cú pháp phù hợp |

`to_tsquery` yêu cầu input đúng cú pháp và có thể báo lỗi với chuỗi không hợp lệ. **Không nối chuỗi tìm kiếm của người dùng tùy ý** vào to_tsquery rồi giả định an toàn về cú pháp; dùng bind parameters và hàm chuyển đổi phù hợp.

### 12.3. phraseto_tsquery — tìm cụm từ

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ phraseto_tsquery(
    'simple', 'full text'
)
ORDER BY doc_id;
```

Hàm tạo truy vấn có xét thứ tự/vị trí các từ; phù hợp khi muốn câu “full text” liền nhau theo logic FTS.

### 12.4. websearch_to_tsquery — cú pháp gần tìm kiếm web

```sql
SELECT websearch_to_tsquery(
    'simple',
    '"full text" OR jsonb -trigram'
);
```

Hàm hỗ trợ cú pháp thân thiện như cụm trong dấu ngoặc kép, OR và dấu trừ cho phủ định. Đây thường là lựa chọn thân thiện hơn `to_tsquery` cho ô tìm kiếm nhập tay.

Nhưng “thân thiện” không có nghĩa search engine tự hiểu ngữ nghĩa sâu, sửa chính tả, tách từ tiếng Việt hay điều kiện bất kỳ.

### 12.5. Kiểm tra tsquery trước khi đoán kết quả

```sql
SELECT
    plainto_tsquery('simple', 'full text') AS plain_query,
    phraseto_tsquery('simple', 'full text') AS phrase_query,
    websearch_to_tsquery(
        'simple', '"full text" OR jsonb'
    ) AS web_query;
```

Việc in ra tsquery giúp thấy PostgreSQL đã hiểu input như thế nào.

---

## 13. AND, OR, NOT và độ chọn lọc trong FTS

Một câu tìm kiếm:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ to_tsquery(
    'simple', 'postgresql & gin'
);
```

chọn tài liệu có cả hai lexeme. Trong lab, doc 101 là trường hợp rõ ràng.

Với OR:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ to_tsquery(
    'simple', 'gin | jsonb'
)
ORDER BY doc_id;
```

tập kết quả có thể lớn hơn vì chỉ cần một trong hai.

### 13.1. Prefix search khác substring search

Ví dụ:

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE search_vector @@ to_tsquery(
    'simple', 'postgre:*'
);
```

Prefix trong tsquery có nghĩa **lexeme bắt đầu bằng chuỗi đó** theo cấu hình. Nó không phải tìm một substring ở vị trí bất kỳ trong text gốc.

Ví dụ `'tgre'` nằm giữa chữ PostgreSQL có thể được tìm bởi `ILIKE '%tgre%'` nhưng không tự khớp prefix `postgre:*`.

### 13.2. Chỉ dùng phủ định có thể kém chọn lọc

Một tsquery gần nghĩa “không có từ X” có thể khớp phần lớn bảng. Những dạng truy vấn thiếu key khẳng định hoặc quá phổ biến có thể kém phù hợp với inverted index. Planner có thể chọn quét nhiều hàng thay vì tận dụng GIN hiệu quả.

Khi thiết kế API, không nên hứa mọi truy vấn Boolean FTS đều nhanh như tìm một từ khóa rất hiếm.

---

## 14. Full-text search có trọng số: title và description

Bảng lab tạo:

```sql
setweight(to_tsvector('simple', title), 'A')
||
setweight(to_tsvector('simple', description), 'B')
```

Điều này giúp hệ thống phân biệt từ xuất hiện trong **title** và trong **description** để xếp hạng.

### 14.1. Tìm kết quả và tính rank

```sql
WITH q AS (
    SELECT plainto_tsquery('simple', 'full text') AS query
)
SELECT
    d.doc_id,
    d.title,
    ts_rank(d.search_vector, q.query) AS rank
FROM gin_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY rank DESC, d.doc_id ASC;
```

Cột rank biểu diễn độ phù hợp theo thuật toán được chọn; giá trị không mặc định là xác suất “đúng 90%”, không có thang đo thống nhất mọi truy vấn.

### 14.2. Trọng số A/B/C/D

PostgreSQL hỗ trợ gán trọng số lên lexeme. Ví dụ A cho title, B cho description để title thường có đóng góp khác description trong xếp hạng.

Cần hiểu:

- `setweight` gắn weight cho lexeme positions.
- `ts_rank` và `ts_rank_cd` tính rank với công thức riêng.
- Có thể truyền mảng weight vào hàm rank khi muốn điều chỉnh.
- Xếp hạng còn phụ thuộc tần suất và cấu trúc nội dung.
- Những tác vụ tìm kiếm production có thể cần thêm freshness, quyền truy cập, popularity và business ranking.

### 14.3. Index GIN không tự trả theo rank

Một câu:

```sql
WHERE search_vector @@ q
ORDER BY ts_rank(search_vector, q) DESC
LIMIT 20
```

thường phải:

1. Tìm các hàng khớp (có thể dùng GIN).
2. Tính rank trên các hàng phù hợp.
3. Sắp xếp theo rank.
4. Lấy top N.

GIN index trên `tsvector` **không phải index được sắp xếp theo ts_rank của mọi truy vấn**. Vì rank thay đổi theo từng tsquery, không thể xem có GIN là `ORDER BY rank` tự miễn phí.

### 14.4. ts_rank_cd và vị trí

`ts_rank_cd` dùng thuật toán có xét độ gần của từ (cover density), nên phụ thuộc thông tin vị trí. Khi dùng vector đã bị strip hết vị trí, khả năng ranking theo khoảng cách bị ảnh hưởng mạnh.

Với hệ thống cần phrase/proximity/ranking, nên giữ vị trí lexeme khi xây tsvector phù hợp.

---

## 15. ts_headline: làm nổi bật từ khớp

PostgreSQL có hàm `ts_headline` để tạo một đoạn văn bản có đánh dấu những phần liên quan.

```sql
WITH q AS (
    SELECT plainto_tsquery('simple', 'full text') AS query
)
SELECT
    d.doc_id,
    d.title,
    ts_headline(
        'simple',
        d.description,
        q.query,
        'StartSel=<b>, StopSel=</b>, MaxWords=20, MinWords=5'
    ) AS snippet
FROM gin_lab.documents AS d
CROSS JOIN q
WHERE d.search_vector @@ q.query
ORDER BY d.doc_id;
```

Hàm này giúp tạo snippet cho giao diện tìm kiếm.

### 15.1. Cảnh báo XSS khi hiển thị HTML

Nếu dùng `StartSel=<b>` và `StopSel=</b>`, **không được mặc định output của ts_headline an toàn để chèn trực tiếp như HTML** khi nội dung gốc do người dùng cung cấp.

Cần escape/sanitize văn bản và xử lý marker theo cơ chế an toàn của frontend. `ts_headline` là hàm tạo đoạn trích/đánh dấu, **không phải HTML sanitizer**.

### 15.2. ts_headline không phải lý do tự tạo thêm GIN index

GIN giúp tìm những hàng khớp tsquery. `ts_headline` vẫn cần xử lý text của những hàng được chọn để tạo snippet. Vì vậy, tránh tính highlight cho toàn bảng trước rồi mới lọc nếu không cần thiết.

---

## 16. Cấu hình FTS và ngôn ngữ

Một truy vấn FTS phải sử dụng cấu hình xử lý phù hợp:

```sql
SELECT to_tsvector('english', 'Indexes are indexing documents');
SELECT to_tsvector('simple',  'Indexes are indexing documents');
```

Sự khác biệt có thể đến từ stemming, stop words và từ điển được cấu hình.

### 16.1. Văn bản trong một ngôn ngữ, query trong ngôn ngữ khác

Nếu index được tạo với:

```sql
to_tsvector('english', body)
```

nhưng truy vấn lại dùng:

```sql
plainto_tsquery('simple', user_input)
```

các lexeme của query có thể không tương thích các lexeme đã lưu. Ví dụ từ biến thể tiếng Anh có thể được stem ở một phía mà không được stem phía kia.

Nguyên tắc: **cấu hình token hóa và từ điển của index và query phải tương thích**.

### 16.2. Vì sao chỉ dùng mặc định theo session là rủi ro?

Dạng một đối số:

```sql
to_tsvector(body)
```

dựa vào cấu hình tìm kiếm mặc định phù hợp của session/database. Nếu cấu hình đổi, biểu thức có thể cho lexeme khác.

Với expression index/generated column, nên chỉ định cấu hình `REGCONFIG` tường minh:

```sql
to_tsvector('english'::REGCONFIG, body)
```

để index và query có cơ sở lặp lại được. Việc lựa chọn cấu hình là quyết định nghiệp vụ, không chỉ tối ưu kỹ thuật.

---

## 17. Tiếng Việt: giới hạn của simple và english

PostgreSQL có parser và hệ thống text search configuration, nhưng không nên giả định PostgreSQL mặc định cung cấp **bộ phân tích hình thái và tách từ tiếng Việt hoàn chỉnh**.

Tiếng Việt có nhiều **từ gồm nhiều âm tiết viết tách bằng dấu cách**. Ví dụ:

```text
"cơ sở dữ liệu"
"tìm kiếm toàn văn"
"chỉ mục ngược"
```

Một cấu hình thông dụng như `simple` có thể xử lý các phần phân tách theo token, nhưng không tự đảm bảo nhận diện “cơ sở dữ liệu” là một đơn vị từ/ngữ chuyên ngành. `english` lại có dictionary/stop words dành cho tiếng Anh nên không phải cách thích hợp để xử lý tiếng Việt.

### 17.1. Khám phá output trực tiếp

```sql
SELECT
    to_tsvector('simple', 'Tìm kiếm văn bản tiếng Việt')
        AS vietnamese_vector,
    plainto_tsquery('simple', 'tìm kiếm')
        AS vietnamese_query,
    phraseto_tsquery('simple', 'tìm kiếm')
        AS vietnamese_phrase;
```

Tự xem cách parser/dictionary thực tế tạo lexeme. Không coi kết quả tokenize của câu này là một bộ phân tách từ đầy đủ cho mọi loại tên riêng, tiếng lóng, thuật ngữ hoặc từ ghép.

### 17.2. Có dấu và không dấu

```text
"tim kiem"
"tìm kiếm"
```

không nên được giả định tự khớp giống nhau. Cần quyết định chính sách:

- Tìm phân biệt dấu hay không?
- Lưu vector có dấu hay đã chuẩn hóa?
- Có chuẩn hóa Unicode ở tầng nhập liệu không?
- Có cần cho phép tìm gần đúng lỗi gõ và bỏ dấu không?
- Mất sự khác biệt dấu có làm sai nghĩa từ hoặc tên riêng không?

### 17.3. unaccent là một công cụ, không phải trọn bộ tiếng Việt

Extension `unaccent` (nếu được cấp quyền và cài đặt) giúp loại một số dấu theo rules để phục vụ normalizing. Nhưng:

- Bỏ dấu không giải quyết bài toán **word segmentation**.
- Unaccent không phải tự động sửa chính tả.
- Chuỗi sau chuẩn hóa có thể gộp những từ khác nghĩa.
- Khi dùng trong index/generated column, cần xem **volatility/immutability** của function và cách cấu hình từ điển; không tùy tiện gắn nhãn IMMUTABLE cho wrapper của một hàm mà kết quả phụ thuộc cấu hình có thể đổi.

Có thể thiết kế text-search configuration riêng kết hợp từ điển phù hợp, preprocessing ngoài database hoặc một search engine chuyên biệt nếu yêu cầu tiếng Việt phức tạp.

### 17.4. Đa ngôn ngữ

Bảng lab có cột `locale` nhưng `search_vector` dùng `simple` cho mọi hàng. Đây là lựa chọn dạy cơ chế, **không phải thiết kế tối ưu tiếng Việt và tiếng Anh cùng lúc**.

Trên hệ thống thật có thể:

1. Phân vùng/nhóm tài liệu theo ngôn ngữ.
2. Tạo vector theo cấu hình phù hợp từng ngôn ngữ.
3. Lưu config đã chọn và dùng cùng config khi tạo query.
4. Kiểm tra index expression/generated column tương ứng.
5. Kết hợp tìm kiếm theo tên riêng và fuzzy matching khi cần.

Không mặc định `locale='vi'` sẽ khiến PostgreSQL tự thay từ điển nếu biểu thức index đang cố định `'simple'`.

---

## 18. Full-text search khác LIKE và ILIKE

Ba câu hỏi có thể giống nhau khi nhìn bề ngoài nhưng khác bản chất:

| Yêu cầu | Công cụ thường hợp |
| --- | --- |
| Bản ghi chứa các **từ/lexeme** có nghĩa theo dictionary | FTS: `tsvector @@ tsquery` |
| Chuỗi text chứa **substring chính xác** ở bất kỳ vị trí nào | `LIKE`/`ILIKE`, có thể dùng trigram |
| Chuỗi text **gần giống** input, có lỗi chính tả | `pg_trgm` và similarity |
| Tìm theo một ID/giá trị scalar chính xác | B-tree |
| Tìm semantic similarity theo vector embedding | Phương án vector-search riêng, không phải chức năng GIN FTS thông thường |

### 18.1. FTS không phải substring

Nếu người dùng nhập `postgre`:

- `ILIKE '%postgre%'` có thể khớp chuỗi “PostgreSQL”.
- `to_tsquery('simple','postgre:*')` có thể khớp lexeme bắt đầu với tiền tố đó.
- `plainto_tsquery('simple','postgre')` không tự hiểu rằng nó muốn một phần đầu của từ “postgresql”.

Khi người dùng gõ giữa từ, ví dụ `tgre`, prefix FTS không thay được substring search.

### 18.2. B-tree trên TEXT có giúp ILIKE '%word%'?

B-tree không phải lựa chọn chung để tăng tốc pattern có wildcard đầu chuỗi như `ILIKE '%word%'`. Một số loại prefix search với LIKE, collation và operator class B-tree phù hợp có thể được tối ưu, nhưng **chứa chuỗi con bất kỳ** thường cần phương án khác như pg_trgm.

---

## 19. pg_trgm: GIN cho trigram và tìm gần đúng

Extension `pg_trgm` hỗ trợ phép toán và operator class cho trigram — các chuỗi ba ký tự được trích theo quy tắc extension.

### 19.1. Cài extension khi được phép

Trong database lab mà bạn có quyền:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Nếu tài khoản không có quyền tạo extension, phải nhờ quản trị viên hoặc dùng môi trường đã chuẩn bị; không được cố thay đổi extension tùy tiện trên production.

### 19.2. Tạo GIN trigram index

```sql
CREATE INDEX idx_documents_title_trgm
ON gin_lab.documents
USING GIN (title gin_trgm_ops);
```

Index này có nhiệm vụ **khác** `idx_documents_search_gin` trên `tsvector`.

### 19.3. Tìm substring với ILIKE

```sql
SELECT doc_id, title
FROM gin_lab.documents
WHERE title ILIKE '%postgre%'
ORDER BY doc_id;
```

GIN trigram có thể hỗ trợ truy vấn pattern phù hợp. Trong lab, tiêu đề doc 101 có “PostgreSQL”.

### 19.4. Similarity và toán tử %

```sql
SELECT
    doc_id,
    title,
    similarity(title, 'PostgreSQL GIN indez') AS sim
FROM gin_lab.documents
WHERE title % 'PostgreSQL GIN indez'
ORDER BY sim DESC, doc_id;
```

Toán tử `%` sử dụng ngưỡng similarity được cấu hình cho pg_trgm; nó **không có nghĩa khớp từ nguyên dạng FTS**.

Độ phù hợp do trigram đo là một độ đo chuỗi, không phải ngữ nghĩa. Có những từ gần nhau về ký tự nhưng khác nghĩa.

### 19.5. Không có guarantee index luôn nhanh với chuỗi ngắn

Nếu pattern có quá ít trigram có thể trích xuất, index không có nhiều key chọn lọc và query có thể phải kiểm tra nhiều hàng hoặc planner chọn Seq Scan.

Ví dụ tìm substring một ký tự:

```sql
WHERE title ILIKE '%a%'
```

không mặc định nhanh chỉ vì đã tạo GIN trigram index. Cần đo với dữ liệu thật.

### 19.6. GIN vs GiST cho pg_trgm

`pg_trgm` có thể dùng cả GIN `gin_trgm_ops` lẫn GiST `gist_trgm_ops`. Chúng có cấu trúc/chi phí khác nhau:

- GIN thường phù hợp với tìm khớp/đối sánh ứng viên.
- GiST có thể hỗ trợ một số dạng sắp xếp khoảng cách/k-NN theo operator tương ứng trong pg_trgm.
- Nhu cầu top-K nearest strings, tần suất update và dữ liệu thực tế quyết định lựa chọn.

Không nói chung chung “GIN luôn nhanh hơn GiST”, nhất là khi truy vấn có ORDER BY theo khoảng cách similarity.

---

## 20. Expression index cho tìm kiếm toàn văn

Không bắt buộc lưu cột `search_vector` nếu chỉ cần index biểu thức.

Ví dụ trên bảng giả định:

```sql
CREATE INDEX idx_articles_fts
ON articles
USING GIN (
    to_tsvector(
        'english'::REGCONFIG,
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);
```

Truy vấn cần dùng biểu thức và cấu hình phù hợp:

```sql
SELECT article_id, title
FROM articles
WHERE to_tsvector(
    'english'::REGCONFIG,
    coalesce(title, '') || ' ' || coalesce(body, '')
) @@ plainto_tsquery('english', 'search index');
```

Cột `articles` trong ví dụ này chưa được tạo trong lab; đây là mẫu cấu trúc.

### 20.1. Khi nào generated tsvector column hữu ích?

- Truy vấn có thể tham chiếu tên cột `search_vector` ngắn gọn.
- Dễ dùng cùng vector cho `@@` và ranking.
- Có thể gán trọng số từng trường rõ ràng.
- PostgreSQL duy trì cột STORED khi hàng thay đổi.

Đánh đổi:

- Tốn không gian lưu vector.
- INSERT/UPDATE title/body phải tính lại biểu thức và duy trì GIN.
- Nếu muốn đổi dictionary hoặc logic chuẩn hóa, có thể cần migration/rebuild.
- Logic generated column phải đáp ứng yêu cầu của PostgreSQL về biểu thức.

### 20.2. Cẩn thận với việc tự cập nhật vector trong application

Nếu ứng dụng lưu một `tsvector` thủ công, mọi đường ghi title/body phải đồng bộ vector. Nếu quên, FTS có thể trả kết quả không khớp nội dung thật.

Generated column hoặc trigger có thể giảm sai sót này khi phù hợp, nhưng nên xác định đường ghi và cấu hình rõ ràng.

---

## 21. Kết hợp GIN cho array, JSONB và FTS

Một truy vấn thực tế có thể gồm nhiều điều kiện:

> Tìm tài liệu có nhãn PostgreSQL, có khả năng FTS trong attributes và nói về search.

```sql
SELECT
    doc_id,
    title
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql']::TEXT[]
  AND attributes @> '{"features":{"fts":true}}'::JSONB
  AND search_vector @@ plainto_tsquery('simple','search')
ORDER BY doc_id;
```

Planner có thể:

- Sử dụng một GIN index rồi filter các điều kiện còn lại.
- Kết hợp bitmap từ nhiều index qua `BitmapAnd`.
- Chọn Seq Scan nếu bảng nhỏ hoặc điều kiện không đủ chọn lọc.

Không có bảo đảm mọi điều kiện AND làm planner dùng tất cả index.

### 21.1. Vì sao Bitmap Index Scan thường xuất hiện?

Kết quả từ GIN phù hợp với việc thu các **vị trí hàng ứng viên**, sau đó truy cập heap theo bitmap.

Một kế hoạch ý niệm:

```text
Bitmap Heap Scan on documents
  Recheck Cond: (...)
  -> Bitmap Index Scan on idx_documents_tags_gin
       Index Cond: (tags @> ...)
```

Đây chỉ là dạng minh họa; plan thật phụ thuộc PostgreSQL, thống kê, selectivity và cấu hình.

### 21.2. Recheck không đồng nghĩa index sai

Một số điều kiện qua GIN hoặc các bitmap trở nên lossy có thể cần kiểm tra lại trên heap để bảo đảm kết quả chính xác. `Recheck Cond` là cách PostgreSQL xác nhận các hàng ứng viên, không phải lỗi của index.

Khi bitmap mất độ chính xác ở mức page do giới hạn bộ nhớ, có thể thấy số hàng bị loại bởi index recheck. Điều này khác với việc filter thông thường sau khi quét.

### 21.3. Không nhầm ORDER BY với GIN

Khi cần:

```sql
ORDER BY created_at DESC
LIMIT 20
```

GIN trên tags hay JSONB không tự trả hàng theo created_at. Cần xem thêm B-tree trên timestamp hoặc một kế hoạch khác.

Nếu truy vấn luôn yêu cầu filter tags + sắp newest-first, chọn index phải dựa trên **toàn workload và kết quả EXPLAIN** chứ không đơn thuần thêm GIN là xong.

---

## 22. Đọc EXPLAIN cho GIN

Trên dữ liệu lab chỉ tám hàng, PostgreSQL thường chọn **Seq Scan**, ngay cả khi index tồn tại. Đó là quyết định hợp lý vì truy cập vài page có thể rẻ hơn đi qua index rồi heap.

### 22.1. Xem plan thực tế

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id, title
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql','fts']::TEXT[];
```

Cần chú ý:

- Có `Seq Scan` hay `Bitmap Heap Scan`?
- Có `Bitmap Index Scan` trên GIN không?
- `actual rows` và `Rows Removed by Filter` là bao nhiêu?
- Có `Recheck Cond` và `Rows Removed by Index Recheck` không?
- `Buffers: shared hit/read` ra sao?
- Planning Time và Execution Time?

### 22.2. Thử cho planner có thể chọn index để học plan

Chỉ trong transaction lab:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id, title
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql','fts']::TEXT[];

ROLLBACK;
```

`SET LOCAL` có hiệu lực trong transaction hiện tại, sau đó tự hết. Việc hạn chế Seq Scan ở đây nhằm **quan sát một phương án dùng index**, không phải chứng minh nó nhanh hơn.

Không áp dụng `enable_seqscan=off` như tuning mặc định production. Planner có thể vẫn phải dùng Seq Scan trong những trường hợp không có lựa chọn khác.

### 22.3. BitmapAnd khi kết hợp nhiều GIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id
FROM gin_lab.documents
WHERE tags @> ARRAY['postgresql']::TEXT[]
  AND attributes @> '{"type":"guide"}'::JSONB;
```

Planner có thể kết hợp bitmap hoặc chọn một điều kiện làm access path chính. Khi bảng nhỏ, Seq Scan có thể là tốt nhất. Đánh giá số hàng trả về và selectivity, không tìm kiếm một node cụ thể bằng mọi giá.

### 22.4. Đọc cost không phải đo mili giây

Các số `cost=...` của `EXPLAIN` là **ước lượng chi phí tương đối** theo mô hình planner, không trực tiếp là milliseconds. `EXPLAIN ANALYZE` mới cung cấp thời gian đo thực thi trên môi trường cụ thể.

---

## 23. GIN và chi phí ghi: một hàng có nhiều khóa

Với B-tree trên `doc_id`, mỗi hàng thường có một entry tương ứng theo kiểu index. Với GIN trên `tags`, một hàng có thể liên quan nhiều keys. GIN trên JSONB/TSVECTOR cũng có thể liên quan rất nhiều thành phần.

Điều này tạo ra đánh đổi:

| Lợi ích đọc | Chi phí ghi/bảo trì |
| --- | --- |
| Tìm nhanh nhiều nhãn | INSERT phải cập nhật các GIN keys liên quan |
| JSONB containment linh hoạt | UPDATE cấu trúc JSONB có thể đòi hỏi nhiều index work |
| Tìm toàn văn theo lexeme | Thay title/body phải tính vector và duy trì GIN |
| Trigram tìm substring/fuzzy | Chuỗi text có thể đóng góp nhiều trigrams |
| Kết hợp nhiều điều kiện | Nhiều index cũng tốn disk, WAL và VACUUM |

### 23.1. UPDATE một trường không liên quan tới GIN?

Trong PostgreSQL MVCC, UPDATE thường tạo tuple version mới. Nếu UPDATE có thể thực hiện HOT và các cột liên quan index không thay đổi, PostgreSQL có cơ hội tránh tạo index entries mới.

Nhưng khi sửa `tags`, `attributes`, `title` hoặc `description` (và generated `search_vector`), cơ chế index liên quan có thể bị ảnh hưởng. Một UPDATE non-HOT còn có thể gây bảo trì nhiều index khác vì tuple location thay đổi.

Không nên kết luận chi phí từ riêng số phần tử mới trong array mà bỏ qua các index còn lại.

### 23.2. UPDATE JSONB có phải sửa chỉ một key tại chỗ?

Một câu:

```sql
UPDATE gin_lab.documents
SET attributes = jsonb_set(
    attributes,
    '{features,fts}',
    'true'::JSONB
)
WHERE doc_id = 102;
```

ở mức SQL tạo giá trị JSONB kết quả mới; PostgreSQL MVCC tạo tuple version mới cho UPDATE. Không mặc định JSONB/Gin cho phép sửa một key ở vị trí vật lý cũ với chi phí bằng không.

Câu này còn có thể thay đổi GIN entries và sinh WAL. Chỉ chạy trên lab khi muốn thay dữ liệu.

---

## 24. fastupdate và GIN pending list

GIN thường hỗ trợ cơ chế `fastupdate` để cải thiện throughput ghi bằng cách ghi các index entries mới vào **pending list** trước, rồi tích hợp chúng vào phần cấu trúc chính trong quá trình cleanup.

Mô hình ý niệm:

```text
INSERT / UPDATE
     |
     v
GIN fastupdate enabled
     |
     v
Pending list (chưa merge hết)
     |
     +--> Query vẫn phải xét dữ liệu pending phù hợp
     |
     v
Cleanup / VACUUM / hoạt động hợp lệ khác
     |
     v
GIN main index structure
```

### 24.1. Vì sao pending list có ích?

Nếu mỗi lần INSERT đều phải cập nhật ngay nhiều keys rải rác trong GIN main index, việc ghi có thể tốn nhiều random I/O. Pending list giúp gom một phần công việc, cải thiện ghi trong nhiều workload.

Nhưng đây là **dời công việc**, không phải loại bỏ nó.

### 24.2. Hệ quả khi pending list lớn

- Một truy vấn đọc có thể phải xét pending list, gây thêm công việc.
- Khi đến thời điểm cleanup, có thể xuất hiện một đợt CPU/I/O đáng kể.
- Nếu autovacuum và các cơ chế cleanup không theo kịp workload INSERT/UPDATE, độ trễ có thể biến động.
- WAL và maintenance cost vẫn tồn tại.

Đây là lý do một GIN index có thể có latency ghi không đều: nhiều statement nhanh xen với đợt xử lý pending list.

### 24.3. gin_pending_list_limit và fastupdate

Các cấu hình liên quan:

- Index storage parameter `fastupdate`.
- Giới hạn pending list như `gin_pending_list_limit` (cấu hình và reloption phù hợp).
- VACUUM/autovacuum và điều kiện cleanup.
- Tốc độ ghi và kích thước index.

Ví dụ điều chỉnh **chỉ mang tính minh họa trong lab**:

```sql
ALTER INDEX gin_lab.idx_documents_tags_gin
SET (fastupdate = off);
```

Tắt fastupdate đổi đặc tính đường ghi, **không tự động xóa ngay pending entries cũ**. Không áp dụng vô điều kiện trên production.

### 24.4. Quan sát pending list

Nếu extension `pgstattuple` đã được quản trị viên cài và cho phép sử dụng, PostgreSQL cung cấp chức năng quan sát thống kê GIN, ví dụ:

```sql
-- Chỉ khi pgstattuple đã cài và có quyền thực thi:
SELECT *
FROM pgstatginindex(
    'gin_lab.idx_documents_tags_gin'::REGCLASS
);
```

Kết quả có thể bao gồm thông tin pending pages và pending tuples, tùy phiên bản. Extension không bắt buộc để học nội dung chính; không tự tạo extension trên production.

### 24.5. Vai trò VACUUM

VACUUM giúp các index và bảng duy trì trạng thái hữu ích khi UPDATE/DELETE tạo dead tuples, đồng thời có thể xử lý pending list của GIN.

Không nên tắt autovacuum để tránh CPU rồi kỳ vọng GIN luôn hoạt động ổn định. Tối ưu maintenance cần nhìn tốc độ ghi, dung lượng, query latency và tiến độ VACUUM.

---

## 25. GIN và VACUUM, REINDEX, index bloat

Một số tình huống UPDATE/DELETE nhiều có thể khiến index chứa entries không còn hữu ích hoặc có nhiều không gian chờ tái sử dụng.

### 25.1. VACUUM thông thường

```sql
VACUUM (ANALYZE) gin_lab.documents;
```

Chạy lệnh này ngoài explicit `BEGIN ... COMMIT` trong database lab. VACUUM không phải phép “reset toàn bộ index thành nhỏ nhất”, mà chủ yếu dọn thông tin không còn cần và hỗ trợ tái sử dụng không gian theo cơ chế PostgreSQL.

### 25.2. REINDEX

Nếu có bằng chứng bloat hoặc sự cố cấu trúc index cần rebuild, có thể cân nhắc REINDEX theo quy trình vận hành thích hợp:

```sql
-- Chỉ minh họa, không tự chạy trên production:
REINDEX INDEX gin_lab.idx_documents_tags_gin;
```

REINDEX có thể tốn disk, CPU, I/O, WAL và gây lock/gián đoạn tùy cách thực hiện. Các chế độ concurrent có điều kiện và hạn chế riêng; cần xem phiên bản PostgreSQL, transaction context và lịch bảo trì.

### 25.3. Không xóa GIN index chỉ vì kích thước lớn

Một GIN index lớn có thể rất có giá trị nếu truy vấn containment/FTS quan trọng. Hãy so:

- Query latency và tỷ lệ sử dụng.
- Index size và tốc độ tăng theo thời gian.
- Chi phí INSERT/UPDATE.
- VACUUM/autovacuum.
- Độ chọn lọc từ khóa.
- Khả năng thay bằng index chuyên biệt/partial index.
- Sự thay đổi ngữ nghĩa nếu bỏ index hoặc đổi operator class.

---

## 26. Partial GIN index

Nếu một tập tài liệu lớn có trạng thái `published` và chỉ tài liệu công khai được tìm kiếm, có thể dùng partial GIN:

```sql
-- Mẫu trên bảng giả định có cột published BOOLEAN.
CREATE INDEX idx_articles_public_search_gin
ON articles
USING GIN (search_vector)
WHERE published = true;
```

Query muốn dùng index nên thể hiện predicate phù hợp:

```sql
SELECT article_id, title
FROM articles
WHERE published = true
  AND search_vector @@ plainto_tsquery('english', 'database');
```

Lợi ích:

- Index chỉ chứa tập hàng phù hợp predicate.
- Có thể giảm footprint và write maintenance cho hàng ngoài tập.
- Hữu ích khi phần công khai nhỏ hơn toàn bảng.

Đánh đổi:

- UPDATE làm `published` đổi trạng thái có thể thêm/loại membership trong index.
- Query không có predicate tương ứng không thể mặc định dùng partial index.
- PostgreSQL cần có khả năng chứng minh query predicate suy ra điều kiện của index; các prepared statements với tham số có thể khiến việc suy luận này không luôn như mong muốn.

Không thêm partial index chỉ vì có một cột Boolean; phải đo workload.

---

## 27. GIN, GiST và B-tree: một sơ đồ lựa chọn

```text
Câu hỏi tìm kiếm là gì?
       |
       +--> ID / equality / range / ORDER BY scalar
       |         |
       |         v
       |       B-tree
       |
       +--> Mảng tags contains/overlaps
       |         |
       |         v
       |       GIN array_ops
       |
       +--> JSONB containment / key existence
       |         |
       |         v
       |       GIN jsonb_ops / jsonb_path_ops
       |
       +--> Từ khóa toàn văn
       |         |
       |         v
       |       tsvector + GIN (hoặc so GiST theo workload)
       |
       +--> Substring / gần đúng theo ký tự
       |         |
       |         v
       |       pg_trgm + GIN/GiST
       |
       +--> Range / hình học / nearest neighbor loại khác
                 |
                 v
          Xem GiST/SP-GiST/chuyên dụng
```

### 27.1. GIN so với GiST cho full-text search

Cả GIN và GiST có các lựa chọn operator class phục vụ text search theo PostgreSQL. GIN thường là lựa chọn phổ biến cho FTS có nhiều lexeme, đọc tương đối nhiều; GiST có cơ chế signature và những đánh đổi khác, trong đó có thể cần recheck nhiều hơn.

Không kết luận tuyệt đối nếu không có benchmark. Với workload update-heavy, kích thước document, latency đọc và đặc tính bộ dữ liệu, hai loại index có thể có ưu nhược khác nhau.

### 27.2. B-tree không biến mất khi dùng GIN

Một bảng vẫn có thể cần:

- B-tree cho PRIMARY KEY.
- B-tree trên `created_at` để phân trang theo thời gian.
- GIN trên `tags`.
- GIN trên `search_vector`.

Mỗi index có mục tiêu khác nhau. Chính vì thế phải cân nhắc **tổng chi phí ghi và bảo trì**.

### 27.3. Có nên dùng nhiều cột trong một GIN index?

PostgreSQL có thể hỗ trợ GIN nhiều cột khi từng cột có operator class phù hợp; extension như `btree_gin` cung cấp một số operator class cho giá trị scalar trong GIN.

Nhưng không nên hiểu multi-column GIN giống composite B-tree có thứ tự trái-sang-phải. Cần thiết kế theo các toán tử và pattern truy vấn cụ thể, so sánh với nhiều index riêng có thể kết hợp qua BitmapAnd.

---

## 28. Tìm kiếm kết hợp ranking, filter và pagination

Một API tìm kiếm tài liệu có thể:

1. Lọc quyền/tenant.
2. Lọc tags/JSONB.
3. Tìm các lexeme.
4. Tính rank.
5. Sắp xếp ổn định và phân trang.

Ví dụ lab:

```sql
WITH search_input AS (
    SELECT plainto_tsquery(
        'simple', 'postgresql search'
    ) AS q
)
SELECT
    d.doc_id,
    d.title,
    ts_rank(d.search_vector, s.q) AS relevance
FROM gin_lab.documents AS d
CROSS JOIN search_input AS s
WHERE d.tags @> ARRAY['postgresql']::TEXT[]
  AND d.search_vector @@ s.q
ORDER BY relevance DESC, d.doc_id ASC
LIMIT 10;
```

### 28.1. Vì sao cần tie-breaker?

Hai tài liệu có thể nhận cùng relevance score. `ORDER BY relevance DESC, doc_id ASC` giúp thứ tự ổn định hơn khi có điểm bằng nhau.

Với pagination ở quy mô lớn và index/filter phức tạp, nên thiết kế keyset/seek pagination nếu phù hợp, không mặc định OFFSET lớn có chi phí rẻ.

### 28.2. Search ranking không phải authorization

Nếu ứng dụng multi-tenant, mọi query tìm kiếm phải có điều kiện quyền/tenant thích hợp, hoặc chính sách Row-Level Security tương ứng.

Không để GIN trả tài liệu rồi mới lọc quyền ở frontend; quyền cần được thực thi phía server/database theo kiến trúc.

### 28.3. Độ trễ cập nhật và cache

Generated tsvector/GIN được duy trì trong transaction ghi, nên sau COMMIT trên primary các query tiếp theo phù hợp snapshot có thể thấy thay đổi. Nhưng nếu ứng dụng đọc từ asynchronous replica hoặc cache/search service ngoài, kết quả có thể trễ do replication/invalidations.

Không nhầm **consistency của PostgreSQL primary** với độ tươi của toàn bộ kiến trúc tìm kiếm phân tán.

---

## 29. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “GIN là B-tree nhưng nhanh hơn.” | GIN là inverted index cho các thành phần; cơ chế/truy vấn khác |
| “Cứ tạo GIN trên TEXT là tự có full-text search.” | FTS cần tsvector/tsquery hoặc thiết kế expression phù hợp |
| “GIN index giúp mọi toán tử.” | Phải đúng operator class và biểu thức |
| “Mảng = ANY chắc chắn dùng GIN.” | GIN array_ops chủ yếu hỗ trợ toán tử mảng như @>, && |
| “tags @> ARRAY[a,a] bắt buộc có hai bản sao a.” | Containment mảng không là phép đếm multiplicity |
| “JSONB @> là tìm substring.” | Nó là containment cấu trúc/value |
| “attributes ? 'fts' tìm key lồng nhau.” | ? trên JSONB xét top-level |
| “jsonb_path_ops dùng được ?/ ?| / ?&.” | Không; dùng jsonb_ops nếu cần các toán tử đó |
| “jsonb_path_ops luôn tốt hơn ops.” | Có tradeoff với existence và cấu trúc không có value |
| “Chỉ dùng @? là chắc được index.” | JSONPath indexable phụ thuộc biểu thức và opclass |
| “Index trên attributes tự dùng cho mọi (attributes->'x') ? 'y'.” | Có thể cần expression index hoặc viết lại query |
| “LIKE '%abc%' là FTS.” | FTS là lexeme; substring thường dùng LIKE/trigram |
| “plainto_tsquery hiểu cú pháp AND/OR của người dùng.” | Nó xử lý input như plain text; dùng to_tsquery/websearch khi phù hợp |
| “to_tsquery nhận mọi chuỗi tự do.” | Cần cú pháp hợp lệ, có thể báo lỗi |
| “FTS mặc định tách từ tiếng Việt tốt.” | Cần xử lý riêng word segmentation/dấu theo yêu cầu |
| “English stemming giúp tìm tiếng Việt.” | Từ điển tiếng Anh không phải xử lý tiếng Việt |
| “unaccent giải quyết mọi vấn đề tiếng Việt.” | Chỉ một phần chuẩn hóa dấu, không thay tách từ |
| “GIN tự sắp theo ts_rank.” | GIN tìm ứng viên; rank/order có công việc riêng |
| “ts_rank là xác suất chính xác.” | Là relevance score theo thuật toán |
| “ts_headline output an toàn HTML.” | Cần escape/sanitize, đề phòng XSS |
| “pg_trgm chính là search theo nghĩa.” | Chủ yếu dựa tương đồng chuỗi ký tự |
| “ILIKE một ký tự sẽ rất nhanh với trigram.” | Quá ít trigram có thể kém chọn lọc |
| “Có index thì PostgreSQL buộc dùng index.” | Planner có thể chọn Seq Scan khi rẻ hơn |
| “Recheck Cond nghĩa index sai.” | Recheck có thể là phần bình thường của index/bitmap |
| “EXPLAIN cost là milliseconds.” | Cost là ước lượng tương đối |
| “Tạo càng nhiều GIN càng tốt.” | INSERT/UPDATE, WAL, VACUUM và disk tăng |
| “fastupdate làm biến mất chi phí ghi.” | Nó có thể dời công việc vào pending list |
| “Pending list không ảnh hưởng đọc.” | Query cần xét pending list theo cơ chế phù hợp |
| “VACUUM luôn thu nhỏ index về OS.” | Chủ yếu cleanup/reuse; rebuild có tradeoff riêng |
| “REINDEX không có lock/disk/WAL cost.” | Là thao tác maintenance cần kế hoạch |
| “Index lên row JSONB bảo đảm mọi điều kiện nhanh.” | Độ chọn lọc, toán tử và dữ liệu quyết định |
| “GIN tự đảm bảo phân quyền.” | Cần WHERE/RLS/authorization độc lập |

---

## 30. Bài tập thực hành

### Bài 1 — Giải thích inverted index

Dựa trên tags của doc 101, 102, 103, hãy vẽ posting lists cho `postgresql`, `gin`, `fts`. Tập giao của “postgresql” và “fts” gồm những doc_id nào?

### Bài 2 — Mảng chứa nhiều nhãn

Viết query chọn tài liệu có đồng thời hai nhãn `postgresql` và `fts` bằng `@>`. Dự đoán doc 103 và 106.

### Bài 3 — Mảng overlap

Tìm tài liệu có ít nhất một nhãn `array` hoặc `trigram` bằng `&&`. Khác với contains như thế nào?

### Bài 4 — Mảng nằm trong tập

Viết `tags <@ ARRAY[...]` với tập nhãn cho phép. Giải thích vì sao nó yêu cầu toàn bộ phần tử mảng trái thuộc tập bên phải.

### Bài 5 — Array duplicate

Chạy `ARRAY['a'] @> ARRAY['a','a']`. Vì sao kết quả không có nghĩa mảng trái chứa hai phần tử a riêng biệt?

### Bài 6 — JSONB containment lồng nhau

Tìm những tài liệu có `features.fts=true` bằng `@>`. Dự đoán các doc_id trong lab.

### Bài 7 — JSONB array containment

Tìm các tài liệu có `skills` chứa `sql` bằng `@>`. Tại sao array JSONB có phần tử khác vẫn khớp?

### Bài 8 — JSONB top-level existence

So sánh `attributes ? 'fts'` với `(attributes -> 'features') ? 'fts'`. Vì sao kết quả khác nhau?

### Bài 9 — JSONB ?| và ?&

Viết query tìm object có ít nhất một trong các key `type`, `unknown`; rồi object có đồng thời `type` và `skills`. Dùng đúng toán tử.

### Bài 10 — jsonb_ops và path_ops

Giải thích toán tử nào được hỗ trợ bởi từng opclass. Nếu ứng dụng chủ yếu `?` key-existence thì nên thử loại nào? Nếu chủ yếu containment chọn lọc thì loại nào đáng benchmark?

### Bài 11 — Cấu trúc rỗng JSONB

Thử containment `attributes @> '{"features":{}}'`. Vì sao path_ops có thể thiếu index entries hữu ích cho truy vấn kiểu này?

### Bài 12 — JSONPath

Viết `@?` tìm skill `sql` và `@@` kiểm tra `features.fts=true`. Giải thích vì sao không mọi JSONPath đều tận dụng index như nhau.

### Bài 13 — Expression index

Tạo GIN index cho `(attributes -> 'features')`. Viết query dùng expression tương ứng và so với cách dùng containment trên toàn JSONB.

### Bài 14 — TSVECTOR

Chạy `to_tsvector('simple', ...)` và `to_tsvector('english', ...)` trên cùng câu tiếng Anh. Quan sát lexeme, position và stemming.

### Bài 15 — plainto_tsquery

Tạo truy vấn FTS cho `full text` bằng plainto_tsquery, rồi lọc search_vector bằng `@@`. Vì sao kết quả có thể khác với yêu cầu cụm liên tiếp?

### Bài 16 — phraseto_tsquery

Viết truy vấn tìm cụm `full text` theo thứ tự. So sánh biểu thức tsquery của `phraseto_tsquery` với `plainto_tsquery`.

### Bài 17 — websearch_to_tsquery

Thử input `"full text" OR jsonb -trigram` và in ra TSQUERY được tạo. Vì sao hàm này phù hợp hơn to_tsquery khi người dùng nhập cú pháp tìm kiếm kiểu web?

### Bài 18 — Ranking

Tìm tài liệu khớp `full text`, tính `ts_rank`, ORDER BY rank DESC, doc_id ASC. Vì sao GIN không tự có thứ tự rank?

### Bài 19 — ts_headline an toàn

Dùng ts_headline tạo snippet cho kết quả FTS. Nếu raw text do người dùng nhập có chứa HTML độc hại, frontend cần làm gì trước khi render?

### Bài 20 — Tiếng Việt

Thử `to_tsvector('simple', 'Tìm kiếm văn bản tiếng Việt')`. Vì sao không nên coi việc tokenize các âm tiết là giải quyết xong word segmentation?

### Bài 21 — Bỏ dấu

Giải thích khác biệt giữa `tìm kiếm` và `tim kiem`. Vì sao `unaccent` có thể giúp nhưng không thay một bộ tách từ tiếng Việt?

### Bài 22 — pg_trgm

Trong database lab được phép, tạo extension `pg_trgm`, tạo GIN `gin_trgm_ops` trên title, thử `ILIKE '%postgre%'`. Nó giải quyết kiểu tìm kiếm nào mà FTS plain token không giải quyết trực tiếp?

### Bài 23 — Similarity

Thử toán tử `%` và `similarity(title, 'PostgreSQL GIN indez')`. Tại sao kết quả tương tự chuỗi không phải ngữ nghĩa hay độ chắc chắn phần trăm?

### Bài 24 — Plan với GIN

Chạy EXPLAIN (ANALYZE, BUFFERS) cho query tags @>. Vì sao trên bảng tám hàng PostgreSQL có thể chọn Seq Scan? `SET LOCAL enable_seqscan=off` giúp học điều gì và không chứng minh điều gì?

### Bài 25 — BitmapAnd

Kết hợp `tags @> ...`, `attributes @> ...` và `search_vector @@ ...`. Planner có bắt buộc dùng ba GIN index không? Các trường hợp chọn một index rồi filter còn lại?

### Bài 26 — GIN pending list

Giải thích `fastupdate`, pending list và cleanup. Vì sao INSERT có thể nhanh ở một giai đoạn nhưng xảy ra đợt I/O cao khi cleanup?

### Bài 27 — UPDATE và write amplification

UPDATE tags của một tài liệu từ ba nhãn lên mười nhãn; phân tích heap/MVCC, GIN index, WAL và VACUUM. Vì sao không thể chỉ lấy số nhãn mới làm tổng chi phí ghi?

### Bài 28 — Partial GIN

Giả sử bảng articles có `published BOOLEAN`. Viết partial GIN index trên search_vector chỉ cho hàng published. Khi nào query có thể dùng nó? Điều gì xảy ra khi đổi published false→true?

### Bài 29 — GIN hay B-tree?

Chọn index phù hợp cho bốn truy vấn: ID equality, tags contains, JSONB key existence, ORDER BY created_at DESC. Giải thích vì sao không dùng một loại index cho mọi việc.

### Bài 30 — Thiết kế tìm kiếm sản phẩm

Một API yêu cầu filter tags, JSONB properties, tìm cụm từ, rank, trả 20 kết quả, hỗ trợ gõ sai và tiếng Việt không dấu. Hãy thiết kế pipeline FTS/pg_trgm/normalization, quyền truy cập, các index cần benchmark và bộ test đo kết quả đúng/độ trễ.

---

## 31. Checklist triển khai GIN vào hệ thống thật

| Câu hỏi | Điều cần xác định |
| --- | --- |
| Dữ liệu là mảng, JSONB hay văn bản? | Kiểu lưu trữ thực tế |
| Người dùng tìm theo phép nào? | Contains, overlap, existence, lexeme, substring |
| Toán tử có dùng operator class GIN? | Kiểm tra array_ops/jsonb_ops/path_ops/tsvector_ops/trgm |
| Index đặt trên toàn cột hay biểu thức? | Phải phù hợp WHERE |
| JSONB cần ?/ ?| / ?& không? | Nếu có, cân nhắc jsonb_ops |
| JSONB chủ yếu @> không? | So sánh jsonb_ops và path_ops |
| Có tìm cấu trúc JSON rỗng? | Đánh giá hạn chế path_ops |
| Có nhiều mảng/JSON keys rất phổ biến? | Xem selectivity và posting size |
| Có nhiều hàng cùng key? | Kiểm tra candidate volume và recheck |
| FTS dùng cấu hình từ điển gì? | Đồng nhất index/query |
| Có tìm phrase và position? | phraseto_tsquery/positions phù hợp |
| Có ranking? | ts_rank/ts_rank_cd và sort |
| Có highlight? | ts_headline + escape/sanitize |
| Có tiếng Việt? | Segmentation, Unicode, dấu, normalizing |
| Có tiếng Anh và Việt? | Config theo ngôn ngữ, test token |
| Có substring hoặc lỗi gõ? | pg_trgm/LIKE/similarity phù hợp |
| Có truy vấn từ quá ngắn? | Trigram có thể không chọn lọc |
| Có ranking theo thời gian? | Xem B-tree/index phụ trợ |
| Có authorization/tenant scope? | RLS/WHERE server-side |
| Có dữ liệu UPDATE nhiều? | Xem chi phí GIN/WAL/HOT |
| Có pending list lớn? | fastupdate, cleanup, autovacuum |
| VACUUM có theo kịp? | Stats/logs/monitoring |
| Có cần partial index? | Predicate query và membership |
| Đã xem EXPLAIN thật? | Seq Scan, Bitmap Index/Heap, Recheck |
| Đã đo nhiều lần? | Cache, data size, chọn lọc, concurrent writes |
| Có bloat? | Relation size, maintenance, index rebuild khi cần |
| Có cần cột generated tsvector? | Schema, ghi tự động, index maintenance |
| Có migration dictionary/tokenizer? | Rebuild vector/index, regression search |
| Có dữ liệu cá nhân? | Auth, logging, snippet XSS/privacy |
| Có backup/replica/search cache? | Kiểm tra độ tươi kết quả |
| Có benchmark đọc **và ghi**? | Không tối ưu một chiều |
| Có test ngôn ngữ và lỗi gõ? | Ground truth cho relevance |

## Kết luận

**GIN — Generalized Inverted Index** là lựa chọn mạnh của PostgreSQL khi một hàng chứa **nhiều thành phần cần được tra cứu riêng lẻ**. Thay vì index chỉ một khóa scalar của từng hàng, GIN tổ chức ánh xạ từ phần tử/lexeme/trigram tới những hàng có liên quan.

Những nguyên tắc quan trọng:

- Với **mảng**, GIN `array_ops` hỗ trợ các truy vấn chứa, nằm trong và overlap bằng những toán tử phù hợp như `@>`, `<@`, `&&`. Không mặc định `= ANY(tags)` tương đương về khả năng dùng index.
- Với **JSONB**, `jsonb_ops` linh hoạt cho containment và key existence; `jsonb_path_ops` có thể phù hợp cho containment/JSONPath chọn lọc nhưng không hỗ trợ trực tiếp `?`, `?|`, `?&`.
- Với **full-text search**, PostgreSQL dùng `tsvector`, `tsquery` và `@@`. GIN giúp tìm các lexeme; `ts_rank` và `ts_headline` đảm nhiệm xếp hạng và đoạn trích, không được tự biến thành thứ tự index hay HTML đã an toàn.
- Với **tiếng Việt**, phải tính tới tách từ, dấu và cấu hình từ điển. `simple`/`english` mặc định không có nghĩa đã giải quyết toàn bộ ngôn ngữ tiếng Việt; `unaccent` chỉ là một phần của chuẩn hóa.
- Với **substring/fuzzy matching**, extension `pg_trgm` bổ sung những khả năng khác FTS, có thể sử dụng GIN hoặc GiST tùy loại truy vấn.
- Khi đọc **EXPLAIN**, GIN thường tham gia qua bitmap và có thể cần recheck. Trên bảng rất nhỏ, Seq Scan có thể là tối ưu.
- **Chi phí ghi và bảo trì** là một phần của quyết định: nhiều lexeme/JSON keys/trigrams có thể làm index lớn, pending list/cleanup gây biến động và UPDATE vẫn tạo MVCC/WAL.
- Không chọn index chỉ theo tên cột: **toán tử, biểu thức WHERE, độ chọn lọc, chi phí cập nhật, cách sắp kết quả và quyền truy cập** mới là cơ sở thiết kế.

Khi hiểu cả cơ chế index ngược lẫn giới hạn ngôn ngữ và chi phí vận hành, bạn có thể xây truy vấn PostgreSQL cho mảng, JSONB và tìm kiếm văn bản vừa đúng ngữ nghĩa vừa có kế hoạch truy cập phù hợp, thay vì tạo GIN theo thói quen rồi kỳ vọng mọi loại tìm kiếm đều nhanh.
