# TOAST và lưu trữ giá trị lớn trong PostgreSQL

Một hàng PostgreSQL có thể chứa các giá trị rất lớn: văn bản dài, JSON, mảng hoặc dữ liệu nhị phân. Nếu toàn bộ giá trị luôn nằm trong tuple của bảng chính, hệ thống sẽ gặp giới hạn kích thước tuple và giảm hiệu quả lưu trữ. PostgreSQL giải quyết vấn đề này bằng **TOAST — The Oversized-Attribute Storage Technique**.

TOAST cho phép PostgreSQL tự động:

- Nén những giá trị có thể nén.
- Đưa giá trị lớn ra một quan hệ lưu trữ phụ.
- Chia giá trị thành nhiều chunks.
- Giữ một tham chiếu nhỏ trong tuple chính.
- Đọc và tái tạo giá trị khi câu SQL cần sử dụng nó.

Ứng dụng vẫn truy vấn cột như bình thường:

~~~sql
SELECT document_body
FROM documents
WHERE document_id = 10;
~~~

Dù phần lớn nội dung có thể nằm ngoài heap table chính, PostgreSQL trả về giá trị SQL đầy đủ. TOAST là cơ chế nội bộ, không phải API upload file hay message store.

Bài **“TOAST và lưu trữ giá trị lớn”**, thuộc chương **Lưu trữ** của module **Database Engine Relational PostgreSQL**, trình bày tuple/page limits, inline và out-of-line storage, compression, storage strategies, catalog và size inspection, MVCC/vacuum/WAL, indexes, so sánh với Large Objects và object storage, cùng ví dụ SQL và Java.

---

## 1. Vì sao PostgreSQL cần TOAST?

PostgreSQL lưu heap rows trong các data pages có kích thước cố định theo cấu hình build, thường là **8 KB**. Một tuple không thể lớn tùy ý vượt quá khả năng lưu trữ của page.

Ví dụ:

~~~sql
CREATE TABLE articles (
    article_id BIGINT PRIMARY KEY,
    title TEXT,
    body TEXT
);
~~~

Một body 200 KB không thể luôn được giữ nguyên inline trong tuple chính nếu làm tuple vượt ngưỡng lưu trữ.

Nếu mọi cột phải nằm cùng page, các giá trị lớn sẽ làm giảm số hàng mỗi page, khiến truy vấn chỉ cần id/title cũng bị ảnh hưởng bởi độ rộng tuple, và làm tăng chi phí cập nhật.

TOAST cho phép **giữ phần dữ liệu lớn tách khỏi tuple chính**, để tuple trong heap vẫn có kích thước phù hợp.

## 2. Tuple size và ngưỡng TOAST

Với cấu hình page 8 KB phổ biến, TOAST thường can thiệp khi tuple rộng hơn khoảng **2 KB**. Đây là ngưỡng/target mặc định điển hình, không phải giới hạn tối đa của TEXT hoặc BYTEA.

Điều PostgreSQL cần đạt là:

- Tuple chính đủ nhỏ để lưu trong heap page.
- Giá trị lớn được nén nếu có lợi.
- Những giá trị phù hợp được chuyển ra ngoài.
- Phần inline còn lại nằm trong mục tiêu lưu trữ.

### 2.1. 2 KB không phải giới hạn của một cột

Một giá trị text có thể lớn hơn nhiều. TOAST xử lý cách lưu trữ khi kiểu dữ liệu và storage strategy cho phép. Ngược lại, một giá trị 2 KB không nhất thiết luôn bị đưa ra ngoài; quyết định còn phụ thuộc tổng kích thước tuple và các cột khác.

## 3. Những kiểu dữ liệu có thể TOAST

TOAST chủ yếu áp dụng cho các kiểu variable-length, thường gọi là varlena trong implementation PostgreSQL.

Ví dụ:

- `text` và `varchar`.
- `bytea`.
- `json` và `jsonb`.
- Array.
- Một số kiểu phức hợp có biểu diễn varlena.

Các kiểu fixed-length như `integer`, `bigint` và `boolean` không được TOAST theo cách của các varlena values.

### 3.1. TOAST làm việc theo thuộc tính

Một tuple có thể gồm:

~~~text
id           -> inline
created_at   -> inline
title        -> inline
body         -> external TOAST value
thumbnail    -> inline hoặc compressed
metadata     -> inline/compressed/external
~~~

Không phải toàn bộ hàng được chuyển ra ngoài cùng lúc. PostgreSQL lựa chọn những thuộc tính toastable để giảm kích thước tuple.

## 4. Inline, compressed và out-of-line

**Inline:** giá trị nằm trực tiếp trong tuple heap.

~~~text
Heap tuple
+----------------------------------+
| id | title | body value          |
+----------------------------------+
~~~

**Compressed inline:** giá trị đã nén nhưng vẫn nằm trong tuple.

~~~text
Heap tuple
+----------------------------------+
| id | title | compressed body    |
+----------------------------------+
~~~

**Out-of-line:** tuple chính giữ một tham chiếu nội bộ đến giá trị lưu trong relation phụ.

~~~text
Main heap tuple
+----------------------------------+
| id | title | TOAST pointer       |
+----------------------------------+
                 |
                 v
TOAST relation
+-------------------------------+
| chunk 0                       |
| chunk 1                       |
| chunk 2                       |
| ...                           |
+-------------------------------+
~~~

Khi query cần giá trị đầy đủ, PostgreSQL lấy các chunks cần thiết và tái tạo datum.

## 5. TOAST relation và chunks

Một table có các cột toastable có thể có một **TOAST table** được PostgreSQL quản lý. Relation phụ này lưu những phần dữ liệu đã được đưa ra ngoài.

Cấu trúc nội bộ thường có các trường tương tự:

- `chunk_id`: định danh giá trị TOAST.
- `chunk_seq`: thứ tự chunk.
- `chunk_data`: bytes của chunk.

Một index nội bộ hỗ trợ tìm chunks theo value ID và thứ tự. Tên relation được sinh theo OID của bảng chính và thường thuộc schema hệ thống `pg_toast`.

### 5.1. Không sửa TOAST table trực tiếp

Không INSERT, UPDATE hoặc DELETE chunk rows bằng SQL ứng dụng. Không tự tạo pointer hoặc hard-code tên relation nội bộ. PostgreSQL quản lý tạo, đọc, cập nhật và thu hồi TOAST values cùng với table chính.

## 6. TOAST pointer

Khi một giá trị được lưu out-of-line, tuple chính chứa một representation nhỏ gọi là external TOAST pointer. Pointer chứa thông tin cần thiết để PostgreSQL tìm giá trị trong relation liên quan.

Ứng dụng không cần biết định dạng nhị phân của pointer. Khi chạy:

~~~sql
SELECT body
FROM articles;
~~~

PostgreSQL tự lấy và trả về giá trị SQL bình thường.

Pointer không phải business ID, không phải file path và không nên được serialize thành dữ liệu ứng dụng.

## 7. Chunking

Một giá trị out-of-line được chia thành nhiều chunks:

~~~text
value_id = 5001

chunk_seq 0 -> phần đầu
chunk_seq 1 -> phần tiếp
chunk_seq 2 -> phần tiếp
...
chunk_seq N -> phần cuối
~~~

Kích thước chunk là chi tiết implementation phụ thuộc page size và cấu trúc nội bộ. Ứng dụng không nên hard-code chunk size.

Chunking nội bộ không có nghĩa một câu SELECT tự động trả stream từng phần. Nếu ứng dụng SELECT toàn bộ cột, giá trị có thể phải được tái tạo và truyền qua protocol.

## 8. Compression và out-of-line storage

TOAST kết hợp hai kỹ thuật:

1. **Compression:** giảm số bytes của giá trị.
2. **Out-of-line storage:** đưa giá trị ra relation phụ.

Text lặp lại thường nén tốt:

~~~sql
SELECT repeat('PostgreSQL storage ', 10000);
~~~

Dữ liệu đã nén như JPEG, MP4, ZIP hoặc ciphertext thường không giảm đáng kể khi nén thêm.

### 8.1. Không phải mọi giá trị TOAST đều compressed

PostgreSQL có thể thử nén theo storage strategy, nhưng nếu compression không đem lại hiệu quả phù hợp, giá trị có thể được lưu external mà không nén. Không giả định mọi giá trị out-of-line đều compressed.

## 9. Bốn storage strategies

PostgreSQL cho phép cấu hình storage strategy cho từng cột toastable:

| Strategy | Compression | Out-of-line | Đặc điểm |
|---|---|---|---|
| `PLAIN` | Không | Không | Luôn inline; không phù hợp giá trị lớn |
| `EXTENDED` | Có | Có | Mặc định phổ biến; nén rồi có thể đưa ra ngoài |
| `EXTERNAL` | Không | Có | Lưu ngoài hàng nhưng không nén |
| `MAIN` | Có | Có, khi cần hơn | Ưu tiên giữ inline sau nén; out-of-line là lựa chọn cuối |

### 9.1. PLAIN

`PLAIN` không cho compression và không cho out-of-line storage. Với giá trị lớn, INSERT/UPDATE có thể thất bại do tuple không thể lưu vừa page.

Không đặt PLAIN tùy tiện cho TEXT/BYTEA lớn.

### 9.2. EXTENDED

Đây là lựa chọn phổ biến cho các kiểu toastable. PostgreSQL có thể nén và/hoặc chuyển giá trị ra ngoài khi cần giữ tuple phù hợp.

Thường là lựa chọn mặc định hợp lý cho text, JSONB, arrays và bytea.

### 9.3. EXTERNAL

`EXTERNAL` cho phép out-of-line nhưng không nén. Một số thao tác đọc slice của text/bytea có thể tránh giải nén toàn bộ compressed value, đổi lại storage có thể lớn hơn.

EXTERNAL vẫn lưu trong PostgreSQL, không phải S3 hay filesystem ngoài.

### 9.4. MAIN

`MAIN` cho phép compression nhưng ưu tiên giữ dữ liệu inline. PostgreSQL chỉ đưa giá trị ra ngoài khi cần thiết hơn để tuple phù hợp.

Đây là strategy ít phổ biến hơn trong thiết kế ứng dụng thông thường.

## 10. Thay storage strategy

Có thể thay đổi storage strategy của một cột:

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET STORAGE EXTENDED;
~~~

Hoặc:

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET STORAGE EXTERNAL;
~~~

Thiết lập áp dụng cho những lần lưu trữ mới phù hợp; **không tự viết lại tất cả values hiện có**.

Nếu bảng đã có hàng triệu giá trị nén theo strategy cũ, ALTER COLUMN SET STORAGE không tự động chuyển toàn bộ dữ liệu.

## 11. Compression methods

Các phương pháp nén TOAST phổ biến:

- `pglz`: phương pháp truyền thống, luôn có trong PostgreSQL.
- `lz4`: có thể sử dụng nếu PostgreSQL được build với hỗ trợ LZ4.

Từ PostgreSQL 14, có thể chọn compression method theo cột:

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET COMPRESSION lz4;
~~~

Chỉ dùng LZ4 nếu server hỗ trợ; nếu không, câu lệnh sẽ báo lỗi.

### 11.1. Storage strategy khác compression method

- `SET STORAGE EXTENDED` quyết định cột có thể nén/lưu ngoài hàng theo strategy nào.
- `SET COMPRESSION lz4` chọn thuật toán nén khi giá trị được nén.

Một cột có thể dùng EXTENDED và phương pháp pglz hoặc LZ4.

### 11.2. default_toast_compression

~~~sql
SHOW default_toast_compression;
~~~

GUC này chọn phương pháp mặc định cho các cột không có lựa chọn riêng phù hợp. Giá trị mặc định thường là `pglz`; LZ4 phụ thuộc build.

Đừng nhầm TOAST compression với WAL compression.

## 12. Đổi compression không rewrite dữ liệu cũ

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET COMPRESSION lz4;
~~~

làm thay đổi phương pháp cho những values được lưu trong tương lai. Values đã tồn tại không tự giải nén và nén lại chỉ vì ALTER COLUMN.

Muốn đổi representation hiện có, cần rewrite/UPDATE có kiểm soát hoặc phương pháp rewrite table phù hợp.

Rewrite hàng loạt có thể tạo nhiều tuple versions, tăng WAL, I/O, replication lag, dung lượng tạm và vacuum pressure. Không UPDATE toàn bảng trên production chỉ để thử một compression method.

## 13. toast_tuple_target

Table storage parameter `toast_tuple_target` điều khiển kích thước mục tiêu của tuple sau khi TOAST xử lý.

~~~sql
ALTER TABLE articles
SET (toast_tuple_target = 4096);
~~~

Giá trị mặc định thường quanh 2 KB trên cấu hình phổ biến. Phạm vi hợp lệ phụ thuộc giới hạn nội bộ và page size của server.

- Target thấp hơn có thể đưa nhiều dữ liệu ra ngoài sớm hơn.
- Target cao hơn có thể giữ nhiều dữ liệu inline hơn.
- Tác động phụ thuộc số cột toastable, khả năng nén và workload.

Đây không phải tham số “tăng lên để chứa file lớn hơn”; nó điều khiển mục tiêu tuple inline.

### 13.1. Khác fillfactor

| Parameter | Mục đích |
|---|---|
| `toast_tuple_target` | Mục tiêu kích thước tuple sau TOAST |
| `fillfactor` | Tỷ lệ lấp đầy page và phần không gian để dành cho UPDATE |

Hai tham số giải quyết những vấn đề lưu trữ khác nhau.

## 14. Tạo bảng lab

~~~sql
CREATE SCHEMA toast_lab;

CREATE TABLE toast_lab.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    raw_data BYTEA,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);
~~~

Bảng có các kiểu toastable thường gặp: TEXT, BYTEA và JSONB.

### 14.1. Chèn dữ liệu lớn

~~~sql
INSERT INTO toast_lab.documents (
    title, body, raw_data, metadata
)
VALUES (
    'TOAST demonstration',
    repeat('PostgreSQL TOAST storage technique. ', 5000),
    convert_to(repeat('ABCD', 20000), 'UTF8'),
    jsonb_build_object(
        'category', 'database',
        'description', repeat('large json value ', 2000),
        'tags', jsonb_build_array('postgresql', 'storage')
    )
);
~~~

Dữ liệu lặp thường có khả năng nén tốt. Kích thước lưu trữ chính xác phụ thuộc build và representation.

## 15. Đo logical bytes và storage size

~~~sql
SELECT
    document_id,
    octet_length(body) AS body_logical_bytes,
    pg_column_size(body) AS body_storage_bytes,
    octet_length(raw_data) AS raw_logical_bytes,
    pg_column_size(raw_data) AS raw_storage_bytes,
    pg_column_size(metadata) AS metadata_storage_bytes
FROM toast_lab.documents;
~~~

- `octet_length`: số bytes của giá trị text/bytea theo representation SQL.
- `pg_column_size`: kích thước storage của datum, có thể phản ánh compression.

`pg_column_size` không phải tổng dung lượng của toàn bộ TOAST relation; nó không bao gồm tất cả chunks, index và overhead của các rows khác.

## 16. Xem compression method

Trên PostgreSQL 14+:

~~~sql
SELECT
    document_id,
    pg_column_compression(body) AS body_compression,
    pg_column_compression(raw_data) AS raw_compression,
    pg_column_compression(metadata) AS metadata_compression
FROM toast_lab.documents;
~~~

`pg_column_compression` trả tên phương pháp nén của datum đã compressed; trả NULL nếu datum không được nén theo representation tương ứng.

NULL không có nghĩa dữ liệu bị mất. Giá trị có thể nhỏ, inline hoặc external uncompressed.

Nếu server cũ hơn không có function này, bỏ nó khỏi query.

## 17. Xem TOAST relation qua pg_class

Catalog field `pg_class.reltoastrelid` liên kết bảng chính với TOAST relation.

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE c.reltoastrelid::regclass::TEXT
    END AS toast_relation,
    CASE
        WHEN c.reltoastrelid = 0 THEN 0
        ELSE pg_relation_size(c.reltoastrelid::regclass)
    END AS toast_relation_bytes
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'toast_lab'
  AND c.relname = 'documents';
~~~

Dùng OID association thay vì hard-code tên TOAST relation.

Một bảng có cột toastable có thể có relation phụ nhưng hiện chưa chứa out-of-line values. Sự tồn tại của TOAST relation không chứng minh mọi giá trị lớn đang nằm ngoài hàng.

## 18. Các hàm đo relation size

| Hàm | Phạm vi |
|---|---|
| `pg_relation_size(table)` | Kích thước relation/fork cụ thể, thường là heap chính |
| `pg_table_size(table)` | Bảng và thành phần phụ như TOAST/FSM/VM, không tính indexes |
| `pg_indexes_size(table)` | Tổng kích thước indexes |
| `pg_total_relation_size(table)` | Tổng bảng, TOAST và indexes |
| `pg_size_pretty(bytes)` | Hiển thị bytes dễ đọc |

Ví dụ:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('toast_lab.documents'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_table_size('toast_lab.documents'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('toast_lab.documents'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('toast_lab.documents'::regclass)
    ) AS total_size;
~~~

Nếu chỉ nhìn pg_relation_size của heap chính, bạn có thể bỏ qua phần đáng kể nằm trong TOAST relation.

## 19. Detoasting khi đọc

Khi expression cần giá trị đầy đủ, PostgreSQL có thể thực hiện **detoasting**: lấy compressed/out-of-line value, giải nén và tái tạo datum.

~~~sql
SELECT body
FROM toast_lab.documents
WHERE document_id = 1;
~~~

Client nhận body như text bình thường.

Một query chỉ đọc ID/title có thể không cần tải body. Vì vậy hãy chọn projection rõ ràng:

~~~sql
SELECT document_id, title, created_at
FROM toast_lab.documents
ORDER BY document_id;
~~~

Không dùng SELECT * ở endpoint danh sách nếu UI không cần nội dung lớn.

### 19.1. ORM có thể tải blob ngoài ý muốn

Một entity JPA/Hibernate có trường body/bytea có thể bị tải cùng metadata nếu mapping hoặc query không phù hợp. Kiểm tra SQL thực tế của ORM, đặc biệt ở list endpoints.

## 20. TOAST và MVCC

PostgreSQL dùng MVCC: UPDATE tạo row version mới thay vì ghi đè trực tiếp mọi dữ liệu của version cũ.

Với row chứa TOAST value:

- Version mới có thể tiếp tục tham chiếu giá trị lớn không đổi.
- Nếu giá trị lớn thay đổi, PostgreSQL có thể tạo TOAST value/chunks mới.
- Version cũ cần được giữ khi snapshot còn có thể đọc nó.
- Vacuum thu hồi dữ liệu không còn được tham chiếu khi an toàn.

Điều này giải thích vì sao UPDATE một cột TEXT/BYTEA lớn liên tục có thể làm tăng storage và WAL.

### 20.1. Sửa metadata không nhất thiết ghi lại blob

Nếu body không đổi, PostgreSQL có thể tái sử dụng representation TOAST hiện có. Không nên dựa vào chi tiết implementation này để thay thế đo đạc workload.

## 21. VACUUM và TOAST

TOAST relation có dữ liệu/version riêng và được PostgreSQL quản lý cùng các cơ chế vacuum/autovacuum phù hợp.

Sau UPDATE/DELETE nhiều giá trị lớn:

- Old tuple versions trở thành dead tuples khi không còn snapshot cần.
- TOAST chunks không còn được tham chiếu có thể được thu hồi.
- VACUUM giúp không gian được tái sử dụng.

~~~sql
VACUUM (VERBOSE) toast_lab.documents;
~~~

### 21.1. VACUUM không đồng nghĩa file nhỏ lại ngay

VACUUM thường làm không gian có thể tái sử dụng trong relation; nó không nhất thiết trả dung lượng file về filesystem.

`VACUUM FULL` viết lại bảng và có thể thu nhỏ file nhưng cần lock mạnh, dung lượng tạm và thời gian. Không dùng tùy tiện chỉ để “dọn TOAST”.

## 22. Autovacuum và transaction dài

Nếu transaction giữ snapshot lâu, PostgreSQL có thể chưa dọn row versions và TOAST values mà snapshot đó vẫn cần.

Quan sát transactions:

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Nếu workload cập nhật blob lớn thường xuyên, theo dõi dead tuples, vacuum activity, TOAST relation growth, long-running snapshots và replication slots/WAL retention.

## 23. TOAST và WAL

INSERT/UPDATE một giá trị lớn có thể ghi nhiều TOAST chunks và sinh WAL tương ứng. Hệ quả:

- WAL volume tăng.
- Replication phải truyền nhiều bytes.
- Backup/archive volume tăng.
- Logical decoding workload có thể tốn tài nguyên.
- Update blob liên tục gây I/O đáng kể.

### 23.1. TOAST compression khác wal_compression

TOAST compression lưu datum theo phương pháp nén của cột. `wal_compression` là thiết lập khác, liên quan full-page images trong WAL theo hỗ trợ PostgreSQL. Không nhầm hai cơ chế.

## 24. TOAST và indexes

TOAST xử lý storage của giá trị trong heap row. Indexes có giới hạn tuple/index entry riêng và **không được tự động TOAST** như cột trong heap.

Một B-tree index trên text rất lớn có thể gặp giới hạn kích thước index tuple. Không giả định cột có thể TOAST thì có thể index toàn giá trị không giới hạn.

Lựa chọn theo truy vấn:

- Metadata/ID: B-tree trên key nhỏ.
- Full-text search: GIN với tsvector.
- JSONB operators: GIN/jsonb operator class phù hợp.
- Tìm chuỗi gần đúng: cân nhắc pg_trgm.
- BYTEA lớn: index checksum/metadata thay vì toàn payload.

Indexing nội dung lớn làm tăng storage, WAL và write cost; chỉ tạo khi workload cần.

## 25. BYTEA với TOAST

~~~sql
CREATE TABLE toast_lab.attachments (
    attachment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);
~~~

BYTEA là kiểu SQL nhị phân, phù hợp dữ liệu cần lưu cùng row. Giá trị lớn có thể được TOAST tự động.

Ưu điểm:

- INSERT/UPDATE cùng transaction với metadata.
- GRANT và RLS áp dụng theo row/bảng.
- SQL đơn giản.
- Backup table chứa giá trị.

Nhược điểm:

- SELECT toàn BYTEA có thể truyền toàn payload.
- Update payload lớn tăng TOAST/WAL churn.
- Không có API random access theo offset như Large Objects.
- Không tự cung cấp CDN/object lifecycle.

## 26. Large Objects là gì?

PostgreSQL có subsystem riêng gọi là **Large Objects (LO)**. Object được định danh bằng OID; ứng dụng thường lưu OID trong một bảng tham chiếu.

~~~sql
CREATE TABLE toast_lab.file_refs (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename TEXT NOT NULL,
    object_oid OID NOT NULL
);
~~~

Large Objects được quản lý trong các catalog relations riêng, thường là:

- `pg_largeobject_metadata`: metadata, ownership và privileges.
- `pg_largeobject`: nội dung chia thành các pages/chunks.

### 26.1. RLS trên bảng tham chiếu không thay LO privileges

Một row file_refs bị RLS ẩn không tự thu hồi quyền truy cập Large Object qua mọi đường khác. Large Objects có ACL riêng. Cần bảo vệ cả bảng tham chiếu lẫn object permissions/lifecycle.

## 27. TOAST và Large Objects khác nhau

| Tiêu chí | TOAST | Large Objects |
|---|---|---|
| Mục tiêu | Giá trị lớn của cột | Object nhị phân riêng |
| Truy cập | SQL như TEXT/BYTEA/JSONB | OID và LO API |
| Quan hệ với row | Giá trị thuộc row | Row thường giữ OID |
| Chunking | Tự động nội bộ | LO subsystem quản lý |
| Partial read/write | Tùy kiểu/operator | Hỗ trợ offset qua API |
| Quyền | Table/column và RLS | Large object privileges riêng |
| Lifecycle | Theo row version/MVCC | Phải quản lý unlink/reference |
| Backup | Đi cùng table data | Cần đảm bảo dump có LO |

TOAST thường phù hợp khi dữ liệu là một giá trị thuộc row và SQL access đơn giản. Large Objects phù hợp khi cần đọc/ghi theo phần hoặc stream object lớn.

## 28. Tạo Large Object trong lab

PostgreSQL có các function như `lo_create`, `lo_put`, `lo_get` và `lo_unlink`.

~~~sql
DO $$
DECLARE
    v_oid OID;
BEGIN
    v_oid := lo_create(0);

    PERFORM lo_put(
        v_oid,
        0,
        convert_to('Large object payload', 'UTF8')
    );

    INSERT INTO toast_lab.file_refs (
        filename,
        object_oid
    )
    VALUES ('example.txt', v_oid);
END;
$$;
~~~

Đây là ví dụ trong database lab. Các thao tác LO cần transaction phù hợp.

### 28.1. Đọc nội dung

~~~sql
SELECT
    filename,
    convert_from(lo_get(object_oid), 'UTF8') AS content
FROM toast_lab.file_refs;
~~~

Chỉ dùng convert_from khi nội dung thực sự là UTF-8 text. File binary không được cast thành text tùy tiện.

### 28.2. Đọc một phần

~~~sql
SELECT lo_get(object_oid, 0, 8)
FROM toast_lab.file_refs;
~~~

Kết quả là một đoạn bytes; có thể không phải chuỗi UTF-8 hoàn chỉnh nếu cắt giữa một ký tự nhiều bytes.

## 29. Xóa Large Object đúng cách

Xóa row tham chiếu không tự đảm bảo object được unlink. Cần kiểm tra object không còn reference hợp lệ khác:

~~~sql
BEGIN;

SELECT lo_unlink(object_oid)
FROM toast_lab.file_refs
WHERE filename = 'example.txt';

DELETE FROM toast_lab.file_refs
WHERE filename = 'example.txt';

COMMIT;
~~~

Nếu nhiều rows cùng tham chiếu một OID, unlink có thể phá những references còn lại.

### 29.1. Orphaned large objects

Object được tạo nhưng reference bị rollback/xóa sai quy trình có thể trở thành orphan. Tiện ích `vacuumlo` (contrib) giúp tìm/xóa những Large Objects không còn được tham chiếu theo phạm vi kiểm tra của tiện ích. Trên production phải backup và review schema references trước cleanup.

## 30. Large Object privileges

Large Objects có privileges riêng. Ví dụ:

~~~sql
GRANT SELECT
ON LARGE OBJECT 12345
TO app_reader;
~~~

OID phải là object tồn tại và role phải được quản lý phù hợp. Không cấp quyền rộng mà không xem ai có thể biết OID và đường ứng dụng truy cập.

RLS trên bảng tham chiếu không thay thế ACL của Large Object.

## 31. Large Object và JDBC streaming

pgJDBC có API Large Object qua:

- `PGConnection`.
- `LargeObjectManager`.
- `LargeObject`.

Các thao tác LO cần transaction. Ví dụ hình dạng:

~~~java
import java.io.InputStream;
import java.sql.Connection;

import org.postgresql.PGConnection;
import org.postgresql.largeobject.LargeObject;
import org.postgresql.largeobject.LargeObjectManager;

public long store(Connection connection, InputStream input)
        throws Exception {

    boolean oldAutoCommit = connection.getAutoCommit();

    try {
        connection.setAutoCommit(false);

        PGConnection pg =
            connection.unwrap(PGConnection.class);

        LargeObjectManager manager =
            pg.getLargeObjectAPI();

        long oid = manager.createLO(
            LargeObjectManager.READWRITE
        );

        LargeObject object = manager.open(
            oid,
            LargeObjectManager.WRITE
        );

        try (object) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                object.write(buffer, 0, count);
            }
        }

        connection.commit();
        return oid;

    } catch (Exception e) {
        connection.rollback();
        throw e;
    } finally {
        connection.setAutoCommit(oldAutoCommit);
    }
}
~~~

Đây là code minh họa cho connection do method sở hữu. Trong Spring/JPA transaction, không tự thay autoCommit/commit/rollback nếu transaction manager đang sở hữu connection.

### 31.1. Streaming tránh materialize toàn file

Ứng dụng đọc từng buffer từ InputStream rồi ghi qua LO API, thay vì đọc toàn bộ bytes vào một mảng lớn. Kiểm tra pgJDBC version, resource cleanup và exception handling thực tế.

## 32. Large Objects và backup

TOAST relation được gắn với table chính; backup table data bằng công cụ PostgreSQL phù hợp sẽ mang theo các values TOAST. Không cần tự dump từng chunk.

Large Objects là subsystem riêng. Với `pg_dump`, kiểm tra tùy chọn include Large Objects, ví dụ `-b/--blobs`, và chú ý các chế độ lọc table/schema. Không giả định một dump có filter luôn chứa mọi LO mà ứng dụng cần.

Sau restore, kiểm tra:

- Bảng tham chiếu.
- Large Object contents.
- OID references.
- Ownership/privileges.
- Ứng dụng đọc/ghi được object.

## 33. lo_import và lo_export

PostgreSQL có function import/export Large Object ở phía **server filesystem**, không phải filesystem của Java client.

Các function này bị giới hạn quyền vì có thể tạo bề mặt truy cập file máy chủ. Không dùng chúng để đọc file tùy ý do người dùng gửi lên.

Ứng dụng thường dùng streaming qua JDBC hoặc upload object storage, không cấp quyền filesystem database server cho user request.

## 34. Object storage cho file lớn

Với ảnh/video/file cần CDN hoặc được nhiều services dùng, object storage có thể phù hợp hơn lưu toàn bộ bytes trong PostgreSQL.

Database lưu metadata:

~~~sql
CREATE TABLE toast_lab.object_metadata (
    object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_key TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    content_size BIGINT NOT NULL,
    checksum TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Object bytes nằm trong storage service; database lưu key, size, checksum và metadata.

### 34.1. DB transaction không rollback object store

Nếu application upload object rồi INSERT metadata, hai thao tác không cùng một PostgreSQL transaction. Cần upload intent, trạng thái, checksum, outbox/retry và job dọn object mồ côi.

Khi xóa, phối hợp DB record và object deletion theo retry/idempotency.

## 35. Chọn TOAST, Large Objects hay object storage?

| Lựa chọn | Phù hợp khi | Đánh đổi |
|---|---|---|
| TOAST-backed TEXT/BYTEA | Giá trị thuộc row, SQL access đơn giản | Detoast, network và WAL khi đọc/ghi |
| Large Objects | Cần offset/partial read-write và streaming trong DB | ACL, unlink, orphan và backup riêng |
| Object storage | File lớn, CDN, nhiều consumers, lifecycle độc lập | Consistency giữa DB và object store |

Không có một ngưỡng kích thước cố định cho mọi hệ thống. Đánh giá payload size, tần suất đọc/ghi, concurrency, network và backup.

## 36. TOAST và Java memory

Khi JDBC query:

~~~sql
SELECT raw_data
FROM toast_lab.documents
WHERE document_id = ?;
~~~

và gọi:

~~~java
byte[] content = resultSet.getBytes("raw_data");
~~~

driver thường materialize giá trị BYTEA thành một byte array trong JVM heap.

Điều này có thể gây:

- Heap usage tăng.
- Allocation lớn và GC pressure.
- Copy/encode làm tăng memory.
- Network transfer và latency.
- OutOfMemoryError khi nhiều request tải blob đồng thời.

### 36.1. Chỉ query cột cần thiết

Nếu list endpoint chỉ cần title:

~~~sql
SELECT document_id, title
FROM toast_lab.documents;
~~~

Không SELECT body/raw_data nếu UI không cần. Với file lớn cần random access/partial reads, xem LO API hoặc object storage.

## 37. Compression là CPU đổi lấy storage/I/O

| Nén nhiều | Không nén hoặc nén ít |
|---|---|
| Giảm bytes lưu trữ trong trường hợp phù hợp | Tốn storage hơn |
| Có thể giảm I/O | Ít CPU nén/giải nén |
| Tốn CPU khi đọc/ghi | Có thể nhanh hơn cho một số access patterns |
| Phụ thuộc nội dung | Dễ dự đoán hơn với dữ liệu khó nén |

Dữ liệu JPEG/MP4/ZIP hoặc ciphertext thường không giảm đáng kể. Benchmark với mẫu dữ liệu thực tế.

## 38. EXTERNAL và partial access

`EXTERNAL` có thể hữu ích với một số thao tác đọc slice của text/bytea vì không cần giải nén toàn bộ compressed datum. Nhưng hiệu năng còn phụ thuộc function, kiểu dữ liệu, chunks và I/O.

~~~sql
ALTER TABLE toast_lab.documents
ALTER COLUMN body
SET STORAGE EXTERNAL;
~~~

Không chọn EXTERNAL chỉ vì tên của nó; đo workload trước khi thay strategy.

## 39. Update metadata và HOT

PostgreSQL có Heap-Only Tuple (HOT) updates trong một số điều kiện, chẳng hạn indexed columns không đổi và page còn không gian phù hợp.

TOAST không tự bảo đảm UPDATE là HOT. Kết quả còn phụ thuộc index, fillfactor, page free space và những cột thay đổi.

Không coi “cột lớn đã TOAST” là bằng chứng update metadata luôn rẻ.

## 40. TOAST và logical replication

Thay đổi giá trị lớn có thể tăng WAL và replication traffic. Logical decoding/replication có semantics riêng về TOASTed columns và những cột không đổi giữa các versions.

Nếu downstream cần full row image, xác minh replica identity, output plugin, PostgreSQL version, unchanged TOAST columns và replication lag. Không giả định mọi event CDC luôn chứa full value.

## 41. Quan sát storage sau UPDATE/DELETE

Sau khi cập nhật nhiều blob, theo dõi:

- Heap size.
- TOAST relation size.
- Index size.
- Dead tuples.
- Autovacuum activity.
- Long-running snapshots.
- WAL/replication lag.

Một bảng heap nhỏ vẫn có thể có TOAST/index storage lớn. Dùng nhiều hàm size để hiểu phạm vi, không chỉ một số liệu.

## 42. Troubleshooting: row quá lớn

Nếu INSERT/UPDATE báo tuple quá lớn, kiểm tra:

1. Cột có phải kiểu toastable?
2. Storage strategy có bị đặt PLAIN?
3. Tuple có quá nhiều giá trị inline?
4. toast_tuple_target có cấu hình bất thường?
5. Trigger/function có tạo thêm dữ liệu?
6. Kiểu dữ liệu/extension có hỗ trợ TOAST?

Không vội thay block size hoặc tách database trước khi hiểu schema.

## 43. Troubleshooting: disk usage lớn hơn heap

Có thể vì:

- TOAST relation lớn.
- Indexes lớn.
- Dead tuples/old versions.
- Free space map/visibility map.
- Long transactions cản cleanup.
- Large Objects riêng.
- WAL/archive/backup nằm ngoài relation size.

So sánh pg_relation_size, pg_table_size, pg_indexes_size và pg_total_relation_size. Xem relation association khi nghi TOAST.

## 44. Những hiểu lầm thường gặp

### 44.1. TOAST là extension phải cài

Sai. Đây là cơ chế nội bộ PostgreSQL.

### 44.2. 2 KB là giới hạn tối đa của TEXT

Sai. Đây là threshold/target điển hình.

### 44.3. Mọi giá trị lớn đều nén

Sai. Compression phụ thuộc strategy và khả năng nén.

### 44.4. EXTERNAL nghĩa là S3

Sai. EXTERNAL vẫn là TOAST relation trong database.

### 44.5. SET COMPRESSION rewrite dữ liệu cũ

Sai. Cần rewrite riêng nếu muốn chuyển representation cũ.

### 44.6. pg_column_size bằng toàn bộ TOAST table size

Sai. Nó đo datum, không phải mọi chunks/index/overhead.

### 44.7. pg_relation_size bao gồm tất cả TOAST và indexes

Sai. Dùng pg_table_size/pg_total_relation_size.

### 44.8. VACUUM luôn thu nhỏ file

Sai. VACUUM thường giúp space tái sử dụng; VACUUM FULL rewrite và lock mạnh.

### 44.9. TOAST có streaming API cho Java

Sai. TOAST là nội bộ; JDBC có thể materialize BYTEA. LO API/object storage có semantics streaming rõ hơn.

### 44.10. BYTEA và Large Object giống nhau

Sai. BYTEA là column value; LO là object riêng với OID/ACL/lifecycle.

### 44.11. RLS trên bảng tham chiếu bảo vệ mọi Large Object

Sai. LO có privileges riêng.

### 44.12. Xóa row tham chiếu tự động unlink LO

Không nên giả định. Quản lý unlink/lifecycle rõ ràng.

### 44.13. Backup table luôn có mọi Large Objects

Không mặc định; kiểm tra tùy chọn dump và restore.

### 44.14. Index được TOAST tự động

Sai. Index tuple có giới hạn riêng.

### 44.15. TOAST compression giống WAL compression

Sai. Hai cơ chế khác nhau.

## 45. Checklist lựa chọn storage

**Dữ liệu:**

1. Giá trị là text, JSON, bytea hay file?
2. Kích thước trung bình/p95/p99?
3. Có compressible không?
4. Cần đọc toàn bộ hay theo phần?
5. Có thường xuyên UPDATE payload?
6. Có cần CDN/versioning/retention?

**PostgreSQL:**

7. Storage strategy nào?
8. Compression method nào được hỗ trợ?
9. TOAST/table/index size ra sao?
10. WAL và replication impact?
11. Vacuum/autovacuum có theo kịp?
12. Query có vô tình SELECT blob?
13. Index strategy có phù hợp?

**Ứng dụng/vận hành:**

14. JDBC có materialize toàn byte[]?
15. Có streaming API phù hợp?
16. LO ACL/unlink/backup đã rõ?
17. Object storage consistency/lifecycle đã rõ?
18. Upload/download có giới hạn?
19. Có checksum/retry?
20. Backup/restore đã test với dữ liệu lớn?

## 46. Bài tập thực hành

### Bài 1 — TOAST là gì?

Viết đầy đủ ý nghĩa chữ TOAST.

**Gợi ý:** The Oversized-Attribute Storage Technique.

### Bài 2 — Tuple size

Vì sao tuple không thể lớn tùy ý trên một page?

**Gợi ý:** page có kích thước cố định.

### Bài 3 — Ngưỡng

Khoảng 2 KB có phải max size của TEXT?

**Gợi ý:** không, đó là threshold/target điển hình.

### Bài 4 — Varlena

Nêu ba kiểu dữ liệu thường được TOAST.

**Gợi ý:** TEXT, BYTEA, JSONB.

### Bài 5 — Inline

Giải thích inline storage.

**Gợi ý:** value nằm trong heap tuple.

### Bài 6 — Out-of-line

TOAST pointer làm gì?

**Gợi ý:** tham chiếu giá trị ở relation phụ.

### Bài 7 — Chunk

Vì sao giá trị lớn được chia thành chunks?

**Gợi ý:** lưu thành nhiều phần phù hợp page/storage.

### Bài 8 — Catalog

Field nào liên kết bảng với TOAST relation?

**Gợi ý:** pg_class.reltoastrelid.

### Bài 9 — Internal relation

Vì sao không sửa chunk rows trực tiếp?

**Gợi ý:** PostgreSQL quản lý pointer/MVCC/storage.

### Bài 10 — PLAIN

PLAIN cho phép compression/out-of-line không?

**Gợi ý:** không.

### Bài 11 — EXTENDED

Strategy phổ biến có đặc điểm gì?

**Gợi ý:** compression và out-of-line.

### Bài 12 — EXTERNAL

Khác EXTENDED ở đâu?

**Gợi ý:** out-of-line nhưng không compression.

### Bài 13 — MAIN

MAIN ưu tiên điều gì?

**Gợi ý:** giữ inline sau compression, out-of-line khi cần.

### Bài 14 — Compression

Nêu hai compression methods.

**Gợi ý:** pglz và LZ4 nếu build hỗ trợ.

### Bài 15 — Version

SET COMPRESSION theo cột được hỗ trợ từ phiên bản nào?

**Gợi ý:** PostgreSQL 14.

### Bài 16 — Existing data

SET COMPRESSION có rewrite values hiện tại không?

**Gợi ý:** không.

### Bài 17 — toast_tuple_target

Tham số này điều khiển điều gì?

**Gợi ý:** mục tiêu tuple size sau TOAST.

### Bài 18 — fillfactor

Phân biệt toast_tuple_target và fillfactor.

**Gợi ý:** inline tuple target vs page free space.

### Bài 19 — pg_column_size

Viết query đo storage size của body.

**Gợi ý:** pg_column_size(body).

### Bài 20 — octet_length

Khác gì pg_column_size?

**Gợi ý:** logical bytes vs storage representation.

### Bài 21 — Compression inspection

Function nào xem method của datum đã nén trên PostgreSQL 14+?

**Gợi ý:** pg_column_compression.

### Bài 22 — Relation size

Phân biệt pg_relation_size, pg_table_size và pg_total_relation_size.

**Gợi ý:** heap, table phụ trợ, table cộng indexes.

### Bài 23 — Detoast

SELECT toàn body có thể cần làm gì?

**Gợi ý:** fetch/decompress/reconstruct datum.

### Bài 24 — Projection

Vì sao tránh SELECT * khi body lớn?

**Gợi ý:** giảm detoast, network và JVM memory.

### Bài 25 — MVCC

UPDATE body lớn có thể tạo thêm storage nào?

**Gợi ý:** row version và TOAST chunks mới.

### Bài 26 — Vacuum

Vì sao old TOAST data chưa xóa ngay?

**Gợi ý:** snapshot cũ có thể vẫn cần.

### Bài 27 — VACUUM FULL

Khác VACUUM thường ở đâu?

**Gợi ý:** rewrite và lock mạnh.

### Bài 28 — WAL

Vì sao update BYTEA lớn có thể làm WAL tăng?

**Gợi ý:** nhiều TOAST chunks/row versions.

### Bài 29 — Index

Cột TOAST có thể B-tree index toàn giá trị vô hạn không?

**Gợi ý:** không, index tuple có giới hạn.

### Bài 30 — BYTEA

Nêu ưu/nhược điểm lưu file trong BYTEA.

**Gợi ý:** transaction đơn giản vs materialization/WAL/storage.

### Bài 31 — Large Object

LO được tham chiếu bằng gì?

**Gợi ý:** OID.

### Bài 32 — LO catalogs

Nêu hai catalog relations của Large Objects.

**Gợi ý:** pg_largeobject và pg_largeobject_metadata.

### Bài 33 — LO functions

Nêu function tạo, đọc, ghi và xóa LO.

**Gợi ý:** lo_create, lo_get, lo_put, lo_unlink.

### Bài 34 — LO ACL

RLS trên bảng file_refs có thay LO privileges không?

**Gợi ý:** không.

### Bài 35 — Orphan LO

Vì sao cần lo_unlink/vacuumlo?

**Gợi ý:** dọn object không còn reference.

### Bài 36 — JDBC LO

Vì sao Large Object API cần transaction?

**Gợi ý:** thao tác trong transaction context.

### Bài 37 — Backup

Vì sao phải xác minh --blobs trong pg_dump?

**Gợi ý:** Large Objects là subsystem riêng.

### Bài 38 — Object storage

Vì sao upload object và INSERT metadata không atomic cùng PostgreSQL?

**Gợi ý:** external service không tham gia DB transaction.

### Bài 39 — Java memory

getBytes() trên BYTEA lớn có rủi ro gì?

**Gợi ý:** materialize byte[] và tăng heap/GC.

### Bài 40 — Storage choice

Chọn storage cho video lớn cần CDN.

**Gợi ý:** thường object storage, database giữ metadata/key.

## 47. Câu hỏi thường gặp

### TOAST có phải extension không?

Không. Đây là cơ chế lưu trữ nội bộ PostgreSQL.

### 2 KB có phải giới hạn tối đa của TEXT?

Không. Đó là threshold/target mặc định điển hình trên cấu hình phổ biến.

### Mọi giá trị lớn đều được nén?

Không. Compression phụ thuộc strategy và khả năng giảm kích thước.

### EXTERNAL có nghĩa lưu ở filesystem ngoài database?

Không. Đây là strategy out-of-line không nén của TOAST.

### SET STORAGE/SET COMPRESSION có đổi dữ liệu cũ?

Không tự động. Cần rewrite/update được kiểm soát nếu muốn đổi representation hiện có.

### Làm sao xem compression method?

Trên PostgreSQL 14+, dùng pg_column_compression(column).

### pg_column_size có bằng dung lượng TOAST relation?

Không. Nó đo một datum, không bao gồm mọi chunks/index/overhead.

### pg_relation_size có bao gồm TOAST không?

Không nhất thiết. Dùng pg_table_size hoặc pg_total_relation_size để xem phạm vi lớn hơn.

### TOAST có thay Large Objects không?

Không. TOAST lưu giá trị cột; Large Objects có OID và API đọc/ghi theo offset.

### BYTEA có chịu RLS không?

BYTEA là cột của row, nên truy cập qua table chịu GRANT/RLS tương ứng. Large Objects có ACL riêng.

### Xóa row chứa OID có xóa LO không?

Không nên giả định. Quản lý lo_unlink và lifecycle.

### TOAST có tự stream file cho Java không?

Không. TOAST là nội bộ. JDBC có thể materialize BYTEA; LO API/object storage phù hợp hơn cho một số file lớn.

### VACUUM có thu nhỏ file ngay?

Thường không. VACUUM giúp space tái sử dụng; VACUUM FULL rewrite và lock mạnh.

### Compression có luôn nhanh hơn?

Không. Compression đổi CPU lấy storage/I/O, hiệu quả tùy dữ liệu và workload.

### Có nên lưu ảnh/video trong PostgreSQL?

Có thể trong một số hệ thống, nhưng phải đánh giá kích thước, tần suất, streaming, backup, WAL, replication và CDN. Object storage thường phù hợp hơn cho media lớn được phân phối rộng.

## 48. Tổng kết

Các lệnh/công cụ đáng nhớ:

~~~sql
-- Kích thước storage của một datum.
SELECT pg_column_size(body)
FROM toast_lab.documents;

-- Logical bytes.
SELECT octet_length(body)
FROM toast_lab.documents;

-- Compression method (PostgreSQL 14+).
SELECT pg_column_compression(body)
FROM toast_lab.documents;

-- TOAST relation liên kết với bảng.
SELECT reltoastrelid::regclass
FROM pg_class
WHERE oid = 'toast_lab.documents'::regclass;

-- Heap/table/index/total size.
SELECT
    pg_relation_size('toast_lab.documents'::regclass),
    pg_table_size('toast_lab.documents'::regclass),
    pg_indexes_size('toast_lab.documents'::regclass),
    pg_total_relation_size('toast_lab.documents'::regclass);

-- Storage strategy áp dụng cho lần lưu trữ mới.
ALTER TABLE toast_lab.documents
ALTER COLUMN body SET STORAGE EXTENDED;

-- Compression cho lần lưu mới nếu server hỗ trợ.
ALTER TABLE toast_lab.documents
ALTER COLUMN body SET COMPRESSION pglz;

SHOW default_toast_compression;
~~~

Những nguyên tắc cần ghi nhớ:

1. TOAST xử lý oversized attributes để tuple chính phù hợp heap page.
2. Nó áp dụng chủ yếu cho các kiểu variable-length có hỗ trợ.
3. Giá trị có thể inline, compressed hoặc out-of-line.
4. TOAST relation, chunks và pointers là nội bộ; không sửa trực tiếp.
5. EXTENDED là strategy phổ biến; PLAIN không nén/không out-of-line, EXTERNAL out-of-line không nén, MAIN ưu tiên inline.
6. pglz luôn có; LZ4 phụ thuộc build hỗ trợ và compression theo cột có từ PostgreSQL 14.
7. SET STORAGE và SET COMPRESSION không tự rewrite dữ liệu cũ.
8. toast_tuple_target điều khiển tuple target, khác fillfactor.
9. pg_column_size đo datum; pg_table_size/pg_total_relation_size quan sát phạm vi storage lớn hơn.
10. Đọc toàn bộ giá trị có thể cần detoast và truyền nhiều bytes; chỉ query cột cần thiết.
11. UPDATE giá trị lớn có thể tạo row versions/chunks mới, WAL và vacuum pressure.
12. Index tuple có giới hạn riêng; không giả định mọi TOAST column có thể B-tree index toàn giá trị.
13. BYTEA/TOAST tích hợp với row transaction và RLS; Large Objects có OID/ACL/lifecycle riêng.
14. Object storage phù hợp khi cần streaming, CDN và lifecycle độc lập, nhưng không atomic với DB transaction.
15. Với file lớn trong Java, tránh materialize byte[] không cần thiết; cân nhắc LO API/object storage.
16. Backup/restore phải bao gồm Large Objects theo tùy chọn và được kiểm thử; TOAST đi cùng table storage.
17. Compression, vacuum, WAL, replication và JVM memory cần được đánh giá theo workload thực tế.

Sơ đồ lựa chọn:

~~~text
Dữ liệu lớn cần lưu
       |
       v
Là một giá trị thuộc row?
       |
   +---+---+
   |       |
  Có      Không / file object riêng
   |              |
   v              v
TOAST-backed     Cần random/partial
TEXT/BYTEA?      read/write trong DB?
   |              |
   |           +--+--+
   |           |     |
   |          Có    Không
   |           |      |
   |           v      v
   |       Large     Object
   |       Object    storage
   |
   v
Chỉ query metadata hay toàn payload?
   |
   +--> Metadata: không SELECT blob
   |
   +--> Payload: đánh giá detoast, memory,
                 network, WAL và compression
~~~

**Kết luận:** TOAST giúp PostgreSQL lưu giá trị lớn một cách trong suốt với SQL, nhưng **lưu trữ được không có nghĩa mọi cách đọc/ghi đều rẻ**. Hãy lựa chọn storage strategy và compression theo kiểu dữ liệu, đo kích thước TOAST thực tế, tránh tải cột lớn không cần thiết, và so sánh TOAST với Large Objects hoặc object storage khi ứng dụng cần streaming, partial access hoặc phân phối file quy mô lớn.
