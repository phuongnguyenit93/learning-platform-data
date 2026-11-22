# Nạp dữ liệu lớn với ràng buộc, trigger và chỉ mục

Một file CSV vài trăm dòng thường có thể nạp vào PostgreSQL bằng vài lệnh `INSERT`. Khi số lượng tăng lên hàng triệu hay hàng trăm triệu bản ghi, cách tiếp cận đó dễ bộc lộ các vấn đề khác: dữ liệu sai kiểu làm cả lô dừng, khóa ngoại phải tra cứu nhiều lần, unique index phải được cập nhật liên tục, row trigger ghi audit cho từng hàng, WAL và ổ đĩa tăng, replica bị trễ, transaction lớn giữ tài nguyên quá lâu. Nếu vì muốn tăng tốc mà tắt tất cả kiểm tra, database có thể nạp nhanh nhưng mất chính những bảo đảm khiến dữ liệu đáng tin cậy.

**Nạp dữ liệu lớn đúng cách** là bài toán cân bằng giữa **thông lượng, tính đúng đắn, khả năng phục hồi, mức độ sẵn sàng và chi phí vận hành**. PostgreSQL cung cấp `COPY`, giao dịch, bảng staging, `INSERT ... SELECT`, `ON CONFLICT`, ràng buộc `CHECK`/`FOREIGN KEY`/`UNIQUE`, triggers và công cụ xây/kiểm chứng index. Không có một trình tự tối ưu cho mọi workload: nạp vào bảng mới trống khác với cập nhật bảng đang phục vụ người dùng 24/7.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn `COPY`, `\\copy`, batch INSERT hoặc JDBC CopyManager theo nguồn dữ liệu và môi trường.
2. Giải thích ảnh hưởng của `NOT NULL`, `CHECK`, `UNIQUE`, primary key, foreign key và trigger trong quá trình nạp.
3. Thiết kế hai chiến lược: **nạp trực tiếp** và **staging → validate → merge**.
4. Giữ lại những dòng dữ liệu lỗi mà không vô tình để hàng sai đi vào bảng nghiệp vụ.
5. Kiểm soát duplicates, idempotency, batch identifier và retry sau sự cố.
6. Dùng `INSERT ... ON CONFLICT` để upsert từ staging, tránh cập nhật no-op.
7. Phân biệt lúc nào xây index sau khi nạp và lúc nào cần `CREATE INDEX CONCURRENTLY`.
8. Hiểu `NOT VALID` và `VALIDATE CONSTRAINT` cho các loại ràng buộc được hỗ trợ.
9. Đánh giá chi phí row/statement triggers, audit và transition tables khi nạp hàng loạt.
10. Thiết kế transaction size, batching, WAL, checkpoint, vacuum và `ANALYZE`.
11. Dùng `pg_stat_progress_copy`, `pg_stat_activity` và các chỉ số tải để phát hiện điểm nghẽn.
12. Viết Java/JDBC streaming COPY, quản lý transaction và lỗi.
13. Lập kế hoạch nạp online, cutover, partition/replica và rollback.
14. Tạo bộ kiểm chứng số lượng, uniqueness, FK, checksums và đối soát theo lô.

> **Phạm vi lab:** PostgreSQL hiện đại; phần phân loại lỗi bằng `pg_input_is_valid` yêu cầu **PostgreSQL 16 trở lên**. Nếu dùng phiên bản cũ, thực hiện kiểm tra kiểu ở ứng dụng hoặc dùng parsing helpers có xử lý lỗi trước khi chuyển text sang kiểu đích. Mọi câu lệnh `TRUNCATE`, `ALTER TABLE`, `DROP INDEX` hoặc thay đổi trigger phải được cân nhắc riêng trên production; ví dụ dùng schema `lesson_bulk_load` trong database thực hành.

## 2. Bức tranh tổng thể

```text
                    file/object storage/API export
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                Direct COPY                 COPY vào staging
                    │                           │
                    ▼                           ▼
             PostgreSQL target           Raw rows (TEXT, batch)
           ┌────────┼────────┐                  │
           │        │        │                  ▼
        checks    indexes  triggers       Validate/normalize
           │        │        │            ┌─────┴──────┐
           │        │        │            ▼            ▼
           │        │        │         accepted      rejects
           │        │        │            │            │
           │        │        │            ▼            ▼
           │        │        │        INSERT/UPSERT  Repair/export
           │        │        │            │
           └────────┴────────┴────────────┘
                              │
                            COMMIT
                              │
                     ANALYZE / reconcile
                              │
                     Monitor + publish status
```

**Direct COPY** tối giản số bước, thích hợp khi dữ liệu đã sạch và schema đích kiểm soát chặt. **Staging** thêm một bước I/O nhưng hỗ trợ lưu raw input, phân loại lỗi, khử trùng lặp và retry có kiểm soát trước khi tác động bảng nghiệp vụ.

## 3. Vì sao nhiều INSERT đơn lẻ thường chậm?

Một vòng lặp naïve:

```java
for (Row row : rows) {
    // Mỗi dòng tự mở kết nối, INSERT, commit, đóng kết nối.
}
```

có thể phát sinh hàng triệu round trips, commits, parses và connection startups.

### Những cách tốt hơn

| Cách | Điểm mạnh | Điểm cần cân nhắc |
|---|---|---|
| Một `INSERT` mỗi dòng, autocommit | Đơn giản | Round trips/commit overhead lớn |
| JDBC `addBatch`/`executeBatch` | Ít round trips, dễ giữ API parameterized | Batch size, memory và semantics retry |
| Multi-row `INSERT ... VALUES` | Dễ viết, một statement nhiều hàng | SQL text lớn, số placeholders, conflict semantics |
| `COPY FROM STDIN` | Thông lượng thường rất tốt khi streaming | Lỗi kiểu/dữ liệu có thể làm lô dừng |
| `COPY` vào raw staging | Giữ nguyên input, tách validation | Tốn thêm storage, orchestration và bước merge |
| `INSERT ... SELECT` từ staging | Xử lý set-based, áp constraint/trigger ở target | Cần idempotency, duplicate handling, transaction planning |

Không khẳng định COPY luôn nhanh hơn mọi phương án trong mọi tình huống: số indexes, triggers, nguồn I/O, kiểu dữ liệu, batch size và transaction durability đều ảnh hưởng.

## 4. COPY là gì?

`COPY` là câu lệnh PostgreSQL chuyển dữ liệu giữa bảng hoặc kết quả truy vấn với file/STDIN/STDOUT theo định dạng hỗ trợ.

Ví dụ mẫu:

```sql
COPY lesson_bulk_load.raw_orders (
    batch_id, row_no, tenant_raw, source_key_raw,
    customer_raw, amount_raw, ordered_on_raw
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

Khi dùng `COPY FROM STDIN`, client phải triển khai **COPY protocol** và gửi luồng dữ liệu theo giao thức tương ứng; câu SQL trên không phải lệnh tự biết tìm file CSV trên laptop.

### COPY không phải “INSERT bỏ kiểm tra”

Với `COPY FROM` vào bảng thông thường, PostgreSQL thực hiện cơ chế kiểm tra ràng buộc và các row triggers phù hợp. `COPY` không có nghĩa tự bỏ `CHECK`, `NOT NULL`, uniqueness hay foreign keys.

### Một ngoại lệ cần nhớ

PostgreSQL `COPY FROM` không kích hoạt **query rewrite rules** như một câu INSERT được rewrite, nên không dùng RULE như cơ chế kiểm soát nạp dữ liệu. Hãy dùng constraints/triggers hoặc staging được thiết kế rõ.

## 5. COPY cấp server và \copy cấp client

Hai câu lệnh dễ nhầm:

```sql
-- SQL cấp PostgreSQL: file đường dẫn thuộc máy chủ DB.
COPY lesson_bulk_load.raw_orders
FROM '/server/import/orders.csv'
WITH (FORMAT csv, HEADER true);
```

```text
-- Lệnh meta-command của psql: file thuộc máy chạy psql.
\copy lesson_bulk_load.raw_orders FROM '/client/import/orders.csv' WITH (FORMAT csv, HEADER true)
```

| Đặc điểm | `COPY FROM 'file'` | `\copy ... FROM 'file'` |
|---|---|---|
| Ai đọc file? | PostgreSQL server process | psql client |
| File path thuộc ai? | Máy chủ database | Máy chạy psql |
| Loại lệnh | SQL | psql meta-command |
| Quyền filesystem | Server-side và roles phù hợp | Quyền file của client |
| Network transfer | Server đọc local | Client truyền qua PostgreSQL connection |
| Dùng từ JDBC | Qua COPY protocol/driver | Không dùng nguyên meta-command của psql |

Đối với ứng dụng và managed PostgreSQL, thường dùng **client-side streaming COPY** hoặc `\\copy` dễ triển khai hơn server-side file access.

### Cảnh báo bảo mật

`COPY ... PROGRAM` thực thi chương trình ở phía server trong điều kiện được cấp quyền đặc biệt, rủi ro cao; không cấp khả năng này cho role ứng dụng nạp CSV thông thường.

## 6. Dữ liệu CSV và những nguồn lỗi phổ biến

Giả sử file đầu vào có header:

```csv
batch_id,row_no,tenant_raw,source_key_raw,customer_raw,amount_raw,ordered_on_raw
B-2026-11,1,10,SO-001,CUS-01,125000.00,2026-11-01
B-2026-11,2,10,SO-002,CUS-02,300500.00,2026-11-02
B-2026-11,3,10,SO-003,CUS-X,28000.00,2026-11-03
B-2026-11,4,oops,SO-004,CUS-01,5000.00,2026-11-04
B-2026-11,5,10,SO-005,CUS-01,-100.00,2026-11-05
B-2026-11,6,10,SO-006,CUS-01,not-a-number,2026-11-06
```

Các lỗi có thể là:

- Số/giá trị thời gian không hợp lệ.
- Thiếu customer tham chiếu.
- Số tiền âm vi phạm `CHECK`.
- Trùng `(tenant_id, source_key)`.
- Thiếu cột, sai delimiter, quote/escape không hợp lệ.
- Trùng dòng do gửi lại cùng file.
- Text có dấu phẩy, xuống dòng, CRLF hoặc ký tự Unicode.
- Mã hóa không phù hợp `client_encoding`.

Nếu nạp trực tiếp vào bảng typed, một lỗi ở giữa file có thể khiến toàn statement bị lỗi. Với raw staging, những fields đáng ngờ ban đầu là TEXT và được phân loại rõ trước khi cast.

## 7. Tạo schema và bảng danh mục cho lab

Chạy trên database thực hành mới:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_bulk_load;

CREATE TABLE lesson_bulk_load.customers (
    tenant_id BIGINT NOT NULL,
    customer_ref TEXT NOT NULL,
    display_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_ref)
);

INSERT INTO lesson_bulk_load.customers (
    tenant_id, customer_ref, display_name
)
VALUES
    (10, 'CUS-01', 'Công ty Hòa Bình'),
    (10, 'CUS-02', 'Công ty An Việt'),
    (20, 'CUS-01', 'Công ty Sao Mai');
```

`tenant_id` nằm trong primary key vì cùng `customer_ref` có thể tồn tại ở hai tenants. Những FK từ đơn hàng tới khách hàng sẽ phải khớp **cả tenant lẫn customer_ref**, tránh tham chiếu nhầm cross-tenant.

## 8. Bảng đích với ràng buộc

```sql
CREATE TABLE lesson_bulk_load.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_key TEXT NOT NULL,
    customer_ref TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    ordered_on DATE NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_orders_tenant_source
        UNIQUE (tenant_id, source_key),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (tenant_id, customer_ref)
        REFERENCES lesson_bulk_load.customers (
            tenant_id, customer_ref
        )
);

CREATE INDEX ix_orders_tenant_date
ON lesson_bulk_load.orders (
    tenant_id, ordered_on DESC, order_id DESC
);
```

### Những bảo đảm có ngay

| Ràng buộc/index | Bảo vệ |
|---|---|
| `PRIMARY KEY (order_id)` | ID duy nhất của mỗi hàng |
| `UNIQUE (tenant_id,source_key)` | Một đơn nguồn không nhập hai lần trong cùng tenant |
| `NOT NULL` | Các fields bắt buộc |
| `CHECK amount>=0` | Không chấp nhận số tiền âm |
| `FOREIGN KEY` | Customer phải tồn tại **trong tenant tương ứng** |
| B-tree `tenant_id,ordered_on` | Truy vấn theo tenant/thời gian |

Chỉ mục `ix_orders_tenant_date` là **index phục vụ query**, không phải ràng buộc duy nhất. Khi nạp hàng triệu bản ghi, mỗi index bổ sung chi phí insert/index WAL; cần cân nhắc workload trước khi tạo nhiều indexes.

## 9. Bảng raw staging và batch identity

```sql
CREATE TABLE lesson_bulk_load.raw_orders (
    batch_id TEXT NOT NULL,
    row_no BIGINT NOT NULL,
    tenant_raw TEXT,
    source_key_raw TEXT,
    customer_raw TEXT,
    amount_raw TEXT,
    ordered_on_raw TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_no)
);
```

Ở staging, các fields từ CSV là **TEXT**, chưa có FK/CHECK kiểu nghiệp vụ. Vì vậy dòng `tenant_raw='oops'` hoặc `amount_raw='not-a-number'` vẫn có thể được lưu để điều tra.

### Có nên giữ PK trên staging?

Trong lab, PK `(batch_id,row_no)` giúp nạp lại một batch có lỗi trùng dòng được phát hiện ngay. Nhưng trên staging cực lớn, PK index tạo write overhead. Tùy yêu cầu restart/idempotency, có thể:

- Nạp vào raw heap ít indexes, sau đó tạo/kiểm tra uniqueness.
- Sử dụng load-id + file offset từ ingestion coordinator.
- Tạo một staging table tạm/UNLOGGED riêng cho từng batch.

Không bỏ mọi khóa rồi giả định sẽ khử duplicate chính xác khi đầu vào không có định danh ổn định.

## 10. Nạp mẫu vào staging

Để bài lab có thể chạy ngay mà không cần chuẩn bị file ngoài:

```sql
INSERT INTO lesson_bulk_load.raw_orders (
    batch_id, row_no, tenant_raw, source_key_raw,
    customer_raw, amount_raw, ordered_on_raw
)
VALUES
    ('B-2026-11', 1, '10', 'SO-001', 'CUS-01', '125000.00', '2026-11-01'),
    ('B-2026-11', 2, '10', 'SO-002', 'CUS-02', '300500.00', '2026-11-02'),
    ('B-2026-11', 3, '10', 'SO-003', 'CUS-X',  '28000.00',  '2026-11-03'),
    ('B-2026-11', 4, 'oops', 'SO-004', 'CUS-01', '5000.00',  '2026-11-04'),
    ('B-2026-11', 5, '10', 'SO-005', 'CUS-01', '-100.00',   '2026-11-05'),
    ('B-2026-11', 6, '10', 'SO-006', 'CUS-01', 'not-a-number','2026-11-06'),
    ('B-2026-11', 7, '20', 'SO-007', 'CUS-01', '92000.00',  '2026-11-07');
```

Bảy dòng này gồm:

- **3 dòng hợp lệ** (row_no 1, 2, 7).
- Một dòng customer không tồn tại trong tenant (3).
- Một dòng tenant ID không parse được (4).
- Một dòng amount âm (5).
- Một dòng amount không parse được (6).

Đây là kết quả kỳ vọng cho **dữ liệu khởi tạo trên**. Những lần chạy thêm hoặc thay dữ liệu sẽ làm kết quả thay đổi.

## 11. Nạp file thực với psql \copy

Nếu có file CSV ở máy chạy psql:

```text
\copy lesson_bulk_load.raw_orders (batch_id,row_no,tenant_raw,source_key_raw,customer_raw,amount_raw,ordered_on_raw) FROM '/client/path/orders.csv' WITH (FORMAT csv, HEADER true)
```

Đây là **psql meta-command** (không phải SQL chạy qua JDBC PreparedStatement). Cột `ingested_at` không nằm trong danh sách COPY nên dùng default.

### Đường dẫn và header

- Đường dẫn theo **máy của psql client**.
- Header phải khớp cấu trúc file; cấu hình `HEADER true` bỏ qua dòng header.
- Danh sách cột trong COPY xác định mapping theo **vị trí dữ liệu** trong file; không tự căn chỉnh tên cột từ header ở mọi chế độ.
- Với định dạng CSV, giá trị NULL và chuỗi rỗng có semantics cụ thể; đừng tưởng cả hai luôn giống nhau.
- Nên xác nhận `client_encoding` và dữ liệu UTF-8.

### Lưu ý khi đã chạy INSERT mẫu

Nếu nạp file có cùng `batch_id,row_no` vào staging lab đang chứa những keys ấy, PK sẽ báo lỗi. Đây là dấu hiệu replay chưa được thiết kế, không phải lỗi của lệnh `\\copy`. Dùng batch ID mới hoặc một quy trình idempotent có kiểm soát.

## 12. COPY CSV có cột text chứa dấu phẩy

Một bản ghi hợp lệ có thể chứa trường:

```csv
B-2026-12,8,10,SO-008,CUS-01,"125,000.00",2026-12-01
```

CSV parser sẽ đọc `"125,000.00"` như **một field text**, nhưng **PostgreSQL numeric parser thường không chấp nhận dấu phẩy phân nhóm hàng nghìn theo biểu diễn numeric SQL** nếu cast trực tiếp.

### Hai lớp cần phân biệt

1. **CSV format** quy định dấu phân cách fields và cách quote text.
2. **Domain validation** quy định numeric amount được chấp nhận ở dạng nào.

Nếu business cho phép `125,000.00`, bước normalize phải được định nghĩa rõ theo locale; đừng dùng `replace(',', '')` vô điều kiện khi dữ liệu có thể dùng dấu phẩy làm dấu thập phân.

## 13. Tại sao cần ghi rejects riêng?

Một pipeline nạp bền vững thường có:

```text
raw source
   ├── accepted → typed target
   └── rejected → row number + reason + raw payload
```

Giữ rejects giúp:

- Dễ sửa file nguồn và nạp lại một phần.
- Phân biệt lỗi kiểu, lỗi FK và lỗi business validation.
- Báo tỷ lệ lỗi/quality SLO.
- Có dấu vết batch để điều tra.

Thiết kế:

```sql
CREATE TABLE lesson_bulk_load.load_rejects (
    batch_id TEXT NOT NULL,
    row_no BIGINT NOT NULL,
    reason TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_no)
);
```

### Chính sách bảo mật

Raw payload có thể chứa PII/secrets. Bảng rejects cần quyền truy cập và retention riêng, không trở thành nơi lưu dữ liệu nhạy cảm vô thời hạn.

## 14. Phân loại dữ liệu thô trước khi ép kiểu

Trên PostgreSQL 16+, `pg_input_is_valid(text,type)` có thể kiểm tra khả năng chuyển chuỗi sang một kiểu trước khi thực hiện cast.

Ví dụ:

```sql
SELECT
    pg_input_is_valid('10', 'bigint') AS tenant_valid,
    pg_input_is_valid('oops', 'bigint') AS tenant_invalid,
    pg_input_is_valid('125000.00', 'numeric(14,2)') AS amount_valid,
    pg_input_is_valid('not-a-number', 'numeric(14,2)') AS amount_invalid,
    pg_input_is_valid('2026-11-01', 'date') AS date_valid;
```

Với các built-in types trong ví dụ, có thể dùng kết quả để phân luồng trước khi cast. `pg_input_is_valid` là công cụ hỗ trợ validation **ở mức kiểu PostgreSQL**, không thay kiểm tra business rules như amount không âm, customer cùng tenant và uniqueness.

### Vì sao không chỉ viết WHERE tenant_raw ~ '^\d+$'?

Regex chưa phát hiện số vượt giới hạn bigint; với date, regex `YYYY-MM-DD` chưa loại trừ `2026-02-30`. Hàm input validation của PostgreSQL giúp xử lý nhiều lỗi parse/typmod tốt hơn.

### Giới hạn

Kiểm tra input ở thời điểm A và cast ở thời điểm B phải cùng nguồn dữ liệu/encoding/semantics; với một số custom types có input functions không hỗ trợ soft-error reporting đầy đủ, cần test theo version. Trong lab, các trường là built-in `bigint`, `numeric` và `date`.

## 15. Tạo tập đã chuẩn hóa trong một transaction

Xây một bảng tạm với casts được bảo vệ bởi `CASE`:

```sql
BEGIN;

CREATE TEMP TABLE tmp_orders_typed
ON COMMIT DROP
AS
SELECT
    r.batch_id,
    r.row_no,
    CASE
        WHEN pg_input_is_valid(btrim(r.tenant_raw), 'bigint')
        THEN btrim(r.tenant_raw)::bigint
        ELSE NULL
    END AS tenant_id,
    NULLIF(btrim(r.source_key_raw), '') AS source_key,
    NULLIF(btrim(r.customer_raw), '') AS customer_ref,
    CASE
        WHEN pg_input_is_valid(btrim(r.amount_raw), 'numeric(14,2)')
        THEN btrim(r.amount_raw)::numeric(14,2)
        ELSE NULL
    END AS amount,
    CASE
        WHEN pg_input_is_valid(btrim(r.ordered_on_raw), 'date')
        THEN btrim(r.ordered_on_raw)::date
        ELSE NULL
    END AS ordered_on,
    to_jsonb(r) AS raw_payload
FROM lesson_bulk_load.raw_orders AS r
WHERE r.batch_id = 'B-2026-11';
```

`CASE` ở đây giúp **không thực hiện cast trên giá trị được báo không hợp lệ**. `NULLIF(btrim(...),'')` quy ước text toàn khoảng trắng là thiếu.

### Không COMMIT ngay

Bảng tạm có `ON COMMIT DROP`: nó sẽ bị xóa khi transaction kết thúc. Những bước phân loại rejects và merge ở phần tiếp theo cần chạy **trong cùng transaction**, trước COMMIT.

### Transaction size trong thực tế

Đây là lab vài dòng. Với nhiều triệu rows, nên xử lý theo batch/partition có kiểm soát thay vì bắt một transaction quá lớn tạo mọi temp data, rejects và target inserts cùng lúc.

## 16. Phân loại business rules và tham chiếu

Tiếp tục **trong transaction đã bắt đầu ở mục trước**, tạo một bảng tạm với lý do loại bỏ rõ ràng:

```sql
CREATE TEMP TABLE tmp_orders_checked
ON COMMIT DROP
AS
WITH ranked AS (
    SELECT
        t.*,
        row_number() OVER (
            PARTITION BY t.tenant_id, t.source_key
            ORDER BY t.row_no
        ) AS key_rank
    FROM tmp_orders_typed AS t
)
SELECT
    r.*,
    CASE
        WHEN r.tenant_id IS NULL
            THEN 'INVALID_TENANT'
        WHEN r.source_key IS NULL
            THEN 'MISSING_SOURCE_KEY'
        WHEN r.customer_ref IS NULL
            THEN 'MISSING_CUSTOMER'
        WHEN r.amount IS NULL
            THEN 'INVALID_AMOUNT'
        WHEN r.amount < 0
            THEN 'NEGATIVE_AMOUNT'
        WHEN r.ordered_on IS NULL
            THEN 'INVALID_DATE'
        WHEN c.customer_ref IS NULL
            THEN 'UNKNOWN_CUSTOMER_IN_TENANT'
        WHEN r.key_rank > 1
            THEN 'DUPLICATE_SOURCE_KEY_IN_BATCH'
        ELSE NULL
    END AS reject_reason
FROM ranked AS r
LEFT JOIN lesson_bulk_load.customers AS c
  ON c.tenant_id = r.tenant_id
 AND c.customer_ref = r.customer_ref;
```

### Tại sao kiểm tra cả customer?

Khi khách `CUS-01` của tenant 20 tồn tại, nó **không** làm đơn hàng tenant 10 tham chiếu hợp lệ đến `CUS-01` thuộc tenant khác. `LEFT JOIN` dùng đủ hai cột để bảo vệ phạm vi.

### Vì sao vẫn giữ FOREIGN KEY ở target?

Validation staging có thể sai, bị bỏ qua hoặc chịu race với transaction khác xóa customer. **FK trong bảng đích** là lớp bảo vệ cuối cùng khi INSERT/UPDATE thực thi. Pre-validation giúp báo lỗi dễ hiểu, không thay thế constraint.

## 17. Đếm accepted/rejected trước merge

Vẫn trong transaction:

```sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (
        WHERE reject_reason IS NULL
    ) AS accepted_rows,
    count(*) FILTER (
        WHERE reject_reason IS NOT NULL
    ) AS rejected_rows
FROM tmp_orders_checked;
```

Với dữ liệu ban đầu:

```text
total_rows    = 7
accepted_rows = 3
rejected_rows = 4
```

Xem chi tiết:

```sql
SELECT
    batch_id,
    row_no,
    tenant_id,
    source_key,
    amount,
    reject_reason
FROM tmp_orders_checked
ORDER BY row_no;
```

Điều tra theo lý do:

```sql
SELECT
    reject_reason,
    count(*) AS rows
FROM tmp_orders_checked
WHERE reject_reason IS NOT NULL
GROUP BY reject_reason
ORDER BY rows DESC, reject_reason;
```

### Khi một dòng có nhiều lỗi?

`CASE` trên ghi **lý do đầu tiên theo độ ưu tiên**. Một hệ thống muốn báo toàn bộ lỗi có thể tạo `TEXT[]` các reason codes hoặc bảng lỗi nhiều dòng cho mỗi input row. Đó là thay đổi contract, không phải một sự khác biệt nhỏ khi viết SQL.

## 18. Ghi rejects có thể chạy lại

```sql
INSERT INTO lesson_bulk_load.load_rejects (
    batch_id,
    row_no,
    reason,
    raw_payload
)
SELECT
    batch_id,
    row_no,
    reject_reason,
    raw_payload
FROM tmp_orders_checked
WHERE reject_reason IS NOT NULL
ON CONFLICT (batch_id, row_no)
DO UPDATE
SET reason = EXCLUDED.reason,
    raw_payload = EXCLUDED.raw_payload;
```

`ON CONFLICT` giúp nếu chạy lại bước phân loại trên **cùng batch**, một reject row được cập nhật thay vì tạo thêm một bản ghi cùng khóa.

### Nhưng có hoàn toàn idempotent chưa?

Chưa hẳn. Nếu người vận hành chỉnh raw source của cùng batch/row từ lỗi thành hợp lệ, bản ghi reject cũ có thể vẫn tồn tại. Cần một protocol rõ:

- Batch ID **bất biến**: mỗi phiên bản file có batch ID mới; rejects cũ giữ làm lịch sử.
- Hoặc reconcile rejects: xóa/đánh dấu resolved cho những row hiện hợp lệ.

Không tự xóa tất cả reject history trên production nếu cần truy vết.

## 19. Tạo trigger audit trên bảng đích

Một hệ thống muốn ghi các thay đổi thực sự áp dụng vào `orders`.

```sql
CREATE TABLE lesson_bulk_load.order_audit (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    old_row JSONB,
    new_row JSONB,
    event_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION lesson_bulk_load.audit_orders()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO lesson_bulk_load.order_audit (
            order_id, action, old_row, new_row
        )
        VALUES (
            NEW.order_id, 'INSERT',
            NULL, to_jsonb(NEW)
        );

    ELSIF TG_OP = 'UPDATE' THEN
        IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            INSERT INTO lesson_bulk_load.order_audit (
                order_id, action, old_row, new_row
            )
            VALUES (
                NEW.order_id, 'UPDATE',
                to_jsonb(OLD), to_jsonb(NEW)
            );
        END IF;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO lesson_bulk_load.order_audit (
            order_id, action, old_row, new_row
        )
        VALUES (
            OLD.order_id, 'DELETE',
            to_jsonb(OLD), NULL
        );
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE
ON lesson_bulk_load.orders
FOR EACH ROW
EXECUTE FUNCTION lesson_bulk_load.audit_orders();
```

### Thứ tự thực hành

Trigger được tạo **trước khi chèn dữ liệu từ staging**. Nếu bạn đã nạp target trước khi tạo trigger, lịch sử không tự được bổ sung cho dữ liệu cũ.

### Vì sao AFTER ROW?

Trigger nhận các giá trị `NEW`/`OLD` sau biến đổi hàng ở mức statement và ghi lịch sử vào bảng riêng. Với một `INSERT ... SELECT` tạo nhiều hàng, function có thể chạy cho từng hàng, gây thêm CPU, JSONB conversion, index writes và WAL.

## 20. Hợp nhất các dòng hợp lệ bằng UPSERT

Vẫn trong transaction và sau khi tạo trigger:

```sql
INSERT INTO lesson_bulk_load.orders AS o (
    tenant_id,
    source_key,
    customer_ref,
    amount,
    ordered_on
)
SELECT
    tenant_id,
    source_key,
    customer_ref,
    amount,
    ordered_on
FROM tmp_orders_checked
WHERE reject_reason IS NULL
ON CONFLICT (tenant_id, source_key)
DO UPDATE
SET customer_ref = EXCLUDED.customer_ref,
    amount = EXCLUDED.amount,
    ordered_on = EXCLUDED.ordered_on
WHERE (
    o.customer_ref,
    o.amount,
    o.ordered_on
) IS DISTINCT FROM (
    EXCLUDED.customer_ref,
    EXCLUDED.amount,
    EXCLUDED.ordered_on
);
```

### Vai trò của unique constraint

`ON CONFLICT (tenant_id,source_key)` cần một unique arbiter phù hợp. Nếu không có unique index/constraint tương ứng, UPSERT không thể xác định dòng nào là cùng một đơn nguồn.

### Vì sao có WHERE IS DISTINCT FROM?

Nếu chạy lại cùng batch, dữ liệu đã tồn tại và không đổi thì không cần tạo một UPDATE mới. Điều này giảm:

- Heap tuple churn.
- Row trigger audit event.
- WAL và index maintenance liên quan cập nhật.

### Vì sao vẫn cần khử duplicate trong staging?

Một `INSERT ... ON CONFLICT DO UPDATE` **không thể tác động cùng target row nhiều lần trong cùng statement**. Nếu đầu vào có hai rows trùng `(tenant_id,source_key)` và cùng được UPSERT, PostgreSQL có thể báo cardinality violation. `row_number()` ở bước phân loại là biện pháp chọn đúng một row trước merge.

## 21. Kết thúc transaction và xem kết quả

Sau bước merge:

```sql
COMMIT;

SELECT
    tenant_id,
    source_key,
    customer_ref,
    amount,
    ordered_on
FROM lesson_bulk_load.orders
ORDER BY tenant_id, source_key;

SELECT
    action,
    count(*) AS events
FROM lesson_bulk_load.order_audit
GROUP BY action
ORDER BY action;

SELECT
    row_no,
    reason
FROM lesson_bulk_load.load_rejects
WHERE batch_id = 'B-2026-11'
ORDER BY row_no;
```

Với dữ liệu mẫu và khi target ban đầu trống, kỳ vọng:

- Target có 3 đơn hợp lệ.
- Bảng rejects có 4 dòng.
- Audit ghi 3 sự kiện INSERT cho các đơn được chèn.

### Không nhầm số accepted và số INSERT thật

Nếu chạy lại batch, các dòng accepted có thể là **đã tồn tại**; UPSERT với `WHERE ... IS DISTINCT FROM` có thể không thực hiện thao tác DML cho chúng. Vì vậy số accepted trong file **không phải** số rows mới chèn mỗi lần chạy.

### Lưu ý trigger function creation trong transaction

Trong luồng lab, trigger audit được tạo sau `BEGIN` của bước phân loại; PostgreSQL DDL này là transactional và commit cùng các thay đổi. Trong production, nên triển khai schema/triggers bằng migration riêng trước khi xử lý batch để tránh DDL lock kéo dài và phân tách quyền.

## 22. Tại sao kiểm tra ở staging và giữ constraint đích?

Có hai mục tiêu khác nhau:

**Staging validation:**

- Cho biết **lỗi nào** ở **row nào**.
- Giúp người dùng sửa input.
- Phân loại dữ liệu cần xử lý lại.
- Có thể chọn threshold tỷ lệ lỗi của batch.

**Target constraints:**

- Bảo đảm không một code path nào (COPY, INSERT, UPDATE, job, admin tool) ghi dữ liệu sai.
- Bảo vệ trước race với dữ liệu tham chiếu thay đổi giữa validation và merge.
- Tạo contract mạnh cho ứng dụng truy vấn dữ liệu sau nạp.

Nếu chỉ validate ở staging mà sau đó tắt FK/CHECK ở target, mọi writer khác có thể tạo inconsistency.

## 23. Trường hợp COPY trực tiếp vào bảng đích

Khi nguồn chắc chắn sạch và yêu cầu atomic load đơn giản:

```text
\copy lesson_bulk_load.orders (tenant_id,source_key,customer_ref,amount,ordered_on) FROM '/client/path/clean-orders.csv' WITH (FORMAT csv, HEADER true)
```

PostgreSQL sẽ phải bảo vệ các ràng buộc trên target và thực thi triggers phù hợp. Từ đó phát sinh chi phí:

- Unique/PK index updates.
- FK lookups.
- CHECK và type conversion.
- Index `ix_orders_tenant_date` updates.
- `AFTER INSERT` audit cho mỗi hàng.

### Một khác biệt về identity

`order_id` được omitted khỏi COPY columns, nên PostgreSQL sinh ID qua identity. Nếu muốn import khóa cũ trong data migration, cần đánh giá identity semantics và sequence alignment; không thay thế IDs tùy tiện nếu các bảng khác tham chiếu chúng.

### Nếu có dòng lỗi?

COPY trực tiếp không cho phép tự “INSERT ... ON CONFLICT DO UPDATE” theo cú pháp UPSERT. Nếu file có duplicates hoặc FK sai, câu COPY có thể lỗi. Khi cần hòa giải dữ liệu từ nhiều nguồn, staging thường phù hợp hơn.

## 24. Điều gì xảy ra khi COPY bị lỗi giữa chừng?

Trong chế độ xử lý lỗi mặc định, một dòng dữ liệu sai có thể khiến `COPY FROM` dừng và statement bị lỗi. Trong transaction tường minh, lỗi không được xử lý khiến transaction bị aborted và cần rollback.

### Điều cần biết về disk

Các rows đã được nạp vào heap trước khi lỗi có thể chiếm không gian vật lý dù chúng không trở thành dữ liệu visible đã commit. PostgreSQL có thể cần `VACUUM` để thu hồi/reuse không gian sau một COPY lớn bị lỗi.

### On-error support phụ thuộc phiên bản

Các phiên bản PostgreSQL mới có thể hỗ trợ tùy chọn `ON_ERROR ignore` và các tùy chọn liên quan cho một số định dạng/lỗi chuyển đổi. **Không mặc định mọi bản PostgreSQL hỗ trợ bỏ qua mọi loại lỗi**: unique violation, FK violation, trigger errors và lỗi CSV structure có quy tắc khác; kiểm tra tài liệu phiên bản trước khi bật.

Đối với pipeline cần một reject report đầy đủ và sửa/retry có kiểm soát, raw staging vẫn là một lựa chọn dễ hiểu.

## 25. COPY và row triggers

Một bảng có row-level trigger `AFTER INSERT` sẽ thực thi trigger khi COPY thêm các hàng tương ứng.

Với 5 triệu dòng, chi phí trigger có thể gồm:

- Gọi PL/pgSQL 5 triệu lần.
- Chuyển row sang JSONB mỗi lần.
- Ghi thêm 5 triệu audit records.
- Duy trì indexes trên audit table.
- Ghi WAL cho cả target lẫn audit.

### Không phải trigger nào cũng cần ghi cả hàng

Một BEFORE trigger chuẩn hóa cột có thể rất nhẹ, nhưng một AFTER trigger gọi nhiều truy vấn SQL mỗi dòng có thể tạo bottleneck nghiêm trọng.

### Vấn đề tính đúng đắn

Nếu audit là bắt buộc, tắt trigger để tăng tốc làm đứt chuỗi lịch sử. Chỉ tách/chuyển phương pháp audit khi có thiết kế thay thế, kiểm toán và provenance rõ ràng.

## 26. Trigger và constraint không giống nhau

| Cơ chế | Khi nạp | Có thể thay bằng cái khác không? |
|---|---|---|
| `NOT NULL` | Kiểm tra thiếu giá trị | Không nên thay bằng staging-only validation |
| `CHECK` | Kiểm tra điều kiện trên row | Trigger không thay hoàn toàn semantics |
| `UNIQUE/PK` | Phát hiện duplicates, hỗ trợ ON CONFLICT | Hash/ROW_NUMBER tại staging không thay arbiter đích |
| `FOREIGN KEY` | Bảo đảm tham chiếu tồn tại | LEFT JOIN kiểm tra trước vẫn có race |
| BEFORE trigger | Chuẩn hóa/validation tùy logic | Một số logic nên chuyển sang CHECK/generated columns |
| AFTER trigger | Audit/business side effects | Cần tính chi phí và transaction semantics |
| Index truy vấn không unique | Giúp SELECT, tăng write cost | Có thể xây sau load nếu workflow cho phép |

Một **constraint** thường diễn đạt invariant dữ liệu lâu dài ở engine. Trigger diễn đạt hành vi khi có sự kiện DML. Không xem chúng là hai cách hoàn toàn tương đương để “kiểm tra đầu vào”.

## 27. Dùng FOREIGN KEY với nhiều dòng

FK trên `orders(tenant_id,customer_ref)` tham chiếu `customers`. Khi COPY/INSERT vào target, PostgreSQL phải bảo đảm giá trị tham chiếu hợp lệ.

### Các điều có thể gây chậm

- Lookup target trong indexed key của bảng cha.
- Locks và concurrent writes tới bảng cha.
- Volume lớn nếu mỗi row cần kiểm tra quan hệ.
- Cache effectiveness.

### Cách làm an toàn

1. Nạp bảng cha `customers` trước bảng con `orders` nếu quan hệ yêu cầu.
2. Dọn dữ liệu missing FK ở staging.
3. Giữ PK/unique index trên referenced columns.
4. Kiểm tra lock waits nếu loader chậm.
5. Nếu tải vào **bảng mới offline**, cân nhắc thêm FK sau khi nhập và validate theo kế hoạch.

Không vô hiệu hóa FK constraint triggers trên bảng production chỉ để import nhanh rồi giả định mọi dữ liệu vẫn hợp lệ.

## 28. FK được thực thi bằng trigger nội bộ

Trong PostgreSQL, foreign key được thực thi thông qua cơ chế **constraint triggers** của engine. Vì thế:

```sql
-- Rất nguy hiểm nếu dùng không đúng môi trường:
-- ALTER TABLE lesson_bulk_load.orders DISABLE TRIGGER ALL;
```

có thể ảnh hưởng không chỉ business audit triggers mà còn ràng buộc tham chiếu (tùy quyền, trigger type và lệnh).

### Vì sao không khuyến nghị?

- Có thể nạp orphan rows.
- Các hàng sai không tự được sửa khi bật trigger lại.
- Có thể cần superuser/privilege mạnh để tắt internal constraint triggers.
- App khác vẫn có thể ghi dữ liệu trong lúc invariants bị vô hiệu.

Ngay cả nếu bạn kiểm chứng cuối cùng, khoảng thời gian target chấp nhận dữ liệu sai vẫn là một vấn đề của hệ thống online. Ưu tiên staging, thêm constraint offline hoặc `NOT VALID`/`VALIDATE CONSTRAINT` khi áp dụng được.

## 29. NOT VALID cho CHECK và FOREIGN KEY

Với một bảng **đã có dữ liệu**, có thể bổ sung một số constraints mà **chưa quét toàn bộ dữ liệu cũ ngay lúc ADD CONSTRAINT**:

```sql
-- Minh họa trên bảng thích hợp, không chạy nếu đã có tên constraint:
ALTER TABLE lesson_bulk_load.orders
ADD CONSTRAINT chk_orders_upper_amount
CHECK (amount <= 1000000000)
NOT VALID;
```

Điểm quan trọng:

- `NOT VALID` bỏ qua việc kiểm chứng **toàn bộ hàng đã tồn tại** lúc thêm constraint.
- Các thao tác INSERT/UPDATE mới vẫn chịu kiểm tra constraint theo quy tắc.
- Sau khi dữ liệu cũ được chuẩn hóa, chạy `VALIDATE CONSTRAINT` để kiểm chứng.

```sql
ALTER TABLE lesson_bulk_load.orders
VALIDATE CONSTRAINT chk_orders_upper_amount;
```

### Chỉ cho những constraint types được hỗ trợ

Không coi `NOT VALID` là tùy chọn dùng cho mọi loại constraint. Phổ biến với `CHECK` và `FOREIGN KEY`; uniqueness/primary key có cơ chế index khác, không tạo bằng `UNIQUE ... NOT VALID` tùy ý.

### Vẫn cần lập kế hoạch lock

Thêm và validate constraint có lock levels, scan và impact riêng. Validation thường giúp giảm mức độ chặn một số tác vụ concurrent so với thêm constraint kiểm tra toàn bảng ngay lập tức, nhưng không miễn phí và phải xem kế hoạch cụ thể.

## 30. Thêm FK sau khi nạp bảng mới

Giả sử một bảng nhập dữ liệu đã có khóa `tenant_id,customer_ref` nhưng chưa có FK.

Mẫu triển khai khi đã quản lý schema phù hợp:

```sql
ALTER TABLE lesson_bulk_load.orders
ADD CONSTRAINT fk_orders_extra_example
FOREIGN KEY (tenant_id, customer_ref)
REFERENCES lesson_bulk_load.customers (
    tenant_id, customer_ref
)
NOT VALID;

ALTER TABLE lesson_bulk_load.orders
VALIDATE CONSTRAINT fk_orders_extra_example;
```

Ví dụ trên thêm một FK cùng ý nghĩa với `fk_orders_customer` đã tồn tại trong lab, nên **không cần chạy thật** trừ khi chủ ý thử trên bản sao bảng chưa có FK. Trong production, thêm constraint hai lần như vậy không mang lại lợi ích.

### Trình tự đề xuất

1. Xây referenced PK/unique index trên bảng cha.
2. Nạp và chuẩn hóa bảng con.
3. Dùng anti-join tìm orphan rows.
4. Thêm FK `NOT VALID` nếu cần giảm thời gian khóa ban đầu.
5. `VALIDATE CONSTRAINT`.
6. Đảm bảo tất cả writers sau đó hoạt động dưới FK đã được bảo vệ.

## 31. Tìm orphan records trước khi VALIDATE

Ví dụ:

```sql
SELECT
    o.tenant_id,
    o.customer_ref,
    count(*) AS affected_orders
FROM lesson_bulk_load.orders AS o
LEFT JOIN lesson_bulk_load.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_ref = o.customer_ref
WHERE c.customer_ref IS NULL
GROUP BY o.tenant_id, o.customer_ref
ORDER BY affected_orders DESC;
```

Với FK của lab đang hoạt động từ đầu, kỳ vọng **0 rows**, trừ khi ràng buộc bị bypass hoặc dữ liệu bị can thiệp theo cách đặc biệt.

### Tại sao nên có bước pre-check?

Nếu `VALIDATE CONSTRAINT` phát hiện orphan trong tập rất lớn, bạn phải điều tra/sửa và chạy lại. Một anti-join theo batch có thể cho biết trước phạm vi lỗi để tổ chức correction.

Tuy nhiên pre-check **không thay validation chính thức** vì writers khác có thể thay đổi dữ liệu; constraint là nguồn bảo đảm cuối cùng.

## 32. CHECK constraints và NULL semantics

Trong PostgreSQL, một `CHECK` chỉ từ chối biểu thức trả **FALSE**; nếu biểu thức trả SQL NULL, hàng có thể vẫn được chấp nhận. Vì vậy:

```sql
CHECK (amount >= 0)
```

không tự thay `amount NOT NULL`.

### Thiết kế đúng

```sql
amount NUMERIC(14,2) NOT NULL
    CHECK (amount >= 0)
```

Hai ràng buộc giải quyết hai vấn đề: thiếu dữ liệu và giá trị âm.

### Quan trọng với staging

Nếu `amount_raw` không parse được và chuyển thành NULL, bước phân loại phải reject. Nếu cast NULL vào target có `NOT NULL`, PostgreSQL sẽ từ chối, nhưng error ở target thường ít thân thiện hơn báo lỗi theo `batch_id,row_no`.

## 33. UNIQUE và việc xây index trước/sau nạp

Trong PostgreSQL, primary key và unique constraints dựa trên unique indexes thích hợp. Mỗi bản ghi mới làm engine phải xác định không có khóa trùng.

**Nạp vào bảng mới, offline:** đôi khi nạp heap trước, sau đó tạo indexes và constraints sẽ nhanh hơn việc duy trì nhiều indexes từng row; nhưng trong khoảng chưa áp uniqueness, dữ liệu có thể bị trùng. Chỉ phù hợp khi bảng chưa được public cho writers/readers và pipeline có bước xác thực cuối.

**Nạp vào bảng đang phục vụ:** không được bỏ unique arbiter mà các requests đang dựa vào; thường giữ constraints/indexes hiện có, nạp qua staging và merge theo từng batch.

### Quyết định theo mục tiêu

| Tình huống | Hướng tiếp cận |
|---|---|
| Bảng mới trống, offline, dữ liệu sạch | COPY rồi tạo secondary indexes/constraints thích hợp |
| Bảng online có UPSERT | Giữ unique index để `ON CONFLICT` hoạt động |
| Index chỉ phục vụ truy vấn, chưa cần trong lúc nạp | Có thể tạo sau khi bulk load trên bảng mới |
| Index đang hỗ trợ SLA production | Không drop chỉ để nạp nhanh nếu chưa có kế hoạch downtime |
| Unique constraint mới trên bảng lớn hiện hữu | Kiểm tra duplicate rồi dùng đường tạo unique index online phù hợp |

Không có quy tắc “luôn drop tất cả indexes trước COPY”. Với bảng đang sống, việc drop/rebuild có thể gây lỗi ứng dụng, lock hoặc mất tính đúng đắn.

## 34. Secondary index làm chậm INSERT như thế nào?

Giả sử một hàng mới vào `orders`:

```text
heap INSERT
 ├── PK index(order_id)
 ├── UNIQUE index(tenant_id,source_key)
 └── B-tree index(tenant_id,ordered_on,order_id)
      + WAL/index page activity
```

Thêm năm indexes nữa đồng nghĩa mỗi row có thêm công việc duy trì index entries. Khối lượng tăng còn phụ thuộc loại index, page splits, cache locality, fillfactor và phân bố khóa.

### Khi nào xây index sau?

Với bảng import mới chưa có clients:

1. Tạo bảng với schema cần thiết.
2. COPY dữ liệu đã được kiểm tra.
3. Xây secondary indexes hàng loạt.
4. Tạo/validate constraints còn thiếu.
5. `ANALYZE`.
6. Xác minh rồi mới đưa bảng vào sử dụng.

Phải cân nhắc unique/FK correctness trong thời gian giữa các bước. Không bỏ unique nếu pipeline cần dùng `ON CONFLICT` ngay khi nhập.

## 35. CREATE INDEX thông thường

Ví dụ một index phục vụ báo cáo:

```sql
CREATE INDEX ix_orders_customer_date
ON lesson_bulk_load.orders (
    tenant_id,
    customer_ref,
    ordered_on DESC
);
```

Khi xây index bình thường, PostgreSQL có các loại locks ảnh hưởng concurrent writes. Trên bảng mới/offline, điều này có thể chấp nhận và nhanh hơn biến thể concurrent.

### Không chạy trùng bừa bãi

Nếu index tương tự đã tồn tại, tạo thêm có thể tăng storage và write costs mà không cải thiện plans. Trong production, xem `pg_indexes`, query patterns và `EXPLAIN` trước.

## 36. CREATE INDEX CONCURRENTLY khi bảng đang online

Trên bảng đang phục vụ writes:

```sql
-- Lệnh top-level, không nằm trong BEGIN ... COMMIT:
CREATE INDEX CONCURRENTLY ix_orders_status_date
ON lesson_bulk_load.orders (
    tenant_id,
    ordered_on DESC
);
```

`CREATE INDEX CONCURRENTLY` nhằm giảm mức chặn concurrent inserts/updates/deletes so với xây index thường, nhưng có overhead và thời gian xây dựng lớn hơn trong nhiều trường hợp.

### Ba giới hạn quan trọng

1. **Không chạy trong transaction block tường minh.**
2. Có thể mất nhiều thời gian, chờ transactions cũ và phát sinh thêm I/O.
3. Nếu thất bại, có thể để lại một **invalid index**, phải kiểm tra và xử lý.

### Vì sao không dùng trên mọi bảng mới?

Một bảng offline chưa có writers thường không cần chi phí của concurrent index build. Mặt khác, trên production online, index build thường có thể được lên lịch đồng thời có kiểm soát.

## 37. Kiểm tra index hợp lệ sau khi xây

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    i.indisvalid AS valid_for_queries,
    i.indisready AS ready_for_insert_updates,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
  ON c.oid = i.indexrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lesson_bulk_load'
ORDER BY c.relname;
```

Một invalid index sau thất bại của `CREATE INDEX CONCURRENTLY` có thể vẫn chiếm disk và có trường hợp tiếp tục gây overhead cho writes.

### Phản ứng

Kiểm tra chính xác index nào invalid; với quyền và phiên bản phù hợp, dùng lệnh quản trị như `REINDEX INDEX CONCURRENTLY` hoặc xóa/xây lại theo kế hoạch đã được duyệt. Không drop các indexes ngẫu nhiên nếu có thể được constraint hay ứng dụng phụ thuộc.

## 38. Tạo unique index trên bảng đã nạp

Nếu một bảng mới chưa có unique constraint, một workflow có thể:

1. Tìm duplicates trong raw/typed rows.
2. Sửa dữ liệu trùng hoặc quyết định conflict policy.
3. Tạo unique index trên cặp khóa thật sự.
4. Liên kết index với constraint khi phù hợp, hoặc dùng index như unique arbiter.

Ví dụ truy vấn phát hiện duplicate:

```sql
SELECT tenant_id, source_key, count(*) AS occurrences
FROM lesson_bulk_load.orders
GROUP BY tenant_id, source_key
HAVING count(*) > 1
ORDER BY occurrences DESC;
```

Trong lab, UNIQUE đã tồn tại nên truy vấn thường không ra rows.

### Không dùng UNIQUE ... NOT VALID

`NOT VALID` áp dụng cho những constraint types cụ thể như CHECK/FK, không phải một cách tạo unique constraint không kiểm chứng dữ liệu cũ.

Với bảng online, có thể tạo unique index concurrently rồi dùng `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` nếu index đủ điều kiện; phải kiểm tra cột, expressions/partial predicate, ownership, partitioning và migration locks.

## 39. Index hỗ trợ FK ở hai phía

PostgreSQL yêu cầu referenced columns của foreign key được bảo vệ bằng uniqueness phù hợp (PK/unique index/constraint). Tuy nhiên **không tự tạo index trên mọi referencing column của bảng con**.

Với `orders(tenant_id,customer_ref)`:

```sql
CREATE INDEX ix_orders_customer_fk
ON lesson_bulk_load.orders (
    tenant_id,
    customer_ref
);
```

Index này có thể hữu ích khi:

- Query orders theo customer.
- Parent customer bị UPDATE/DELETE và cần kiểm tra các child rows.
- Truy vấn cần join theo cặp khóa ấy.

### Nhưng không tạo vô điều kiện

Mỗi index tăng write cost cho bulk import. Nếu workload không truy vấn theo customer và parent hiếm khi delete, hãy benchmark/read plans trước khi tạo. Index phù hợp với query/load patterns quan trọng hơn một danh sách indexes theo kiểu “có FK là tạo ngay”.

## 40. Trigger audit và row-by-row overhead

Trong lab, mỗi hàng INSERT vào `orders` tạo một audit row qua `AFTER ROW` trigger.

Nếu nạp 1 triệu orders, số rows có thể tăng thành:

```text
orders:      1,000,000 rows
order_audit: 1,000,000 events
```

Hơn nữa mỗi audit event chứa JSONB snapshot, nên tổng bytes viết có thể lớn hơn đáng kể so với chỉ bảng orders.

### Không phải tất cả audit là vô ích

Nếu cần chứng minh dữ liệu nhập từ batch nào, thời gian nào và thay đổi gì, audit có giá trị nghiệp vụ/compliance. Nhưng hãy thiết kế:

- Data minimization: chỉ log fields cần thiết.
- Batch ID và source provenance có thể được ghi riêng.
- Tối ưu indexes trên audit.
- Retention/partitioning phù hợp.
- Không dùng trigger làm HTTP/network call đồng bộ.

## 41. Statement-level trigger và transition tables

Với những workload bulk, `AFTER ... FOR EACH STATEMENT` kết hợp **transition tables** có thể xử lý các rows vừa thay đổi bằng một `INSERT ... SELECT` thay vì gọi PL/pgSQL cho từng row.

Để tránh ghi audit trùng trên bảng `orders`, tạo một bảng demo riêng:

```sql
CREATE TABLE lesson_bulk_load.bulk_demo (
    item_id BIGINT PRIMARY KEY,
    qty INTEGER NOT NULL CHECK (qty >= 0)
);

CREATE TABLE lesson_bulk_load.bulk_demo_history (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id BIGINT NOT NULL,
    new_qty INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION lesson_bulk_load.log_bulk_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson_bulk_load.bulk_demo_history (
        item_id, new_qty
    )
    SELECT item_id, qty
    FROM inserted_rows;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_bulk_demo_history
AFTER INSERT
ON lesson_bulk_load.bulk_demo
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION lesson_bulk_load.log_bulk_demo();

INSERT INTO lesson_bulk_load.bulk_demo (item_id, qty)
SELECT g, g % 100
FROM generate_series(1, 10000) AS g;

SELECT count(*) AS logged_rows
FROM lesson_bulk_load.bulk_demo_history;
-- 10000
```

### Ý nghĩa

Một statement INSERT 10.000 rows có thể kích hoạt **một** invocation của statement trigger function, trong đó `inserted_rows` chứa tập hàng mới.

### Các giới hạn

- Transition relations chỉ được hỗ trợ với những timing/event/target combinations nhất định.
- Statement trigger chạy kể cả khi statement ảnh hưởng 0 hàng, nhưng transition table khi ấy rỗng.
- Không dùng transition table thay toàn bộ semantics của row-level validation/audit mà chưa đánh giá thứ tự triggers, partitioning và nhu cầu OLD/NEW.
- Nếu COPY được chia thành nhiều statements/chunks, có thể có nhiều transition batches; đừng mong một tập “toàn bộ file” tự nhiên xuất hiện ở một statement khi loader đã tách lô.

## 42. BEFORE trigger có thể làm đổi dữ liệu trước constraint

Một `BEFORE INSERT` trigger có thể:

- Chuẩn hóa chuỗi.
- Đặt giá trị mặc định nghiệp vụ.
- Từ chối dữ liệu.
- Gán `NEW.column`.

Nhưng nếu trigger cố gắng sửa một trường amount âm thành 0 thay vì báo lỗi, đó là **quyết định nghiệp vụ rất lớn**: người dùng có thể không biết input sai đã bị thay.

### Gợi ý

Tách:

1. **Normalize không mất nghĩa:** trim whitespace khi hợp đồng cho phép.
2. **Validate và reject:** amount âm, customer không tồn tại.
3. **Audit thay đổi thực:** ghi dữ liệu cuối cùng được chấp nhận.

Không dùng trigger để tự “chữa” mọi dữ liệu bẩn âm thầm trong pipeline lớn.

## 43. Trigger không chạy như một lệnh độc lập

Một `COPY FROM` hoặc `INSERT ... SELECT` có thể kích hoạt trigger hàng nghìn lần. Nhưng các trigger invocations diễn ra trong **transaction của statement/caller**.

Nếu trigger INSERT audit thất bại và error không được xử lý:

- Statement nạp có thể thất bại.
- Dữ liệu target không commit một phần chỉ vì vài triggers đã chạy.
- Transaction tường minh có thể cần `ROLLBACK`.

Điều này giúp bảo đảm **data + audit** cùng tồn tại hoặc cùng bị hủy, với điều kiện audit được yêu cầu trong cùng transaction và không bị bypass.

### Không nhầm audit với outbox gửi mạng ngoài

Một trigger không nên trực tiếp gửi HTTP message rồi kỳ vọng side effect được rollback nếu PostgreSQL transaction thất bại. Muốn phát sự kiện ra hệ khác, dùng **transactional outbox** và publisher phù hợp.

## 44. Transaction size: lớn hay nhỏ?

**Một transaction lớn**:

- Có thể bảo đảm all-or-nothing cho toàn batch.
- Ít commit boundaries.
- Nhưng có thể giữ locks/snapshots lâu, tăng WAL và rollback cost.
- Một lỗi gần cuối có thể buộc nạp lại từ đầu.

**Nhiều transactions nhỏ**:

- Hạn chế blast radius khi lỗi.
- Dễ checkpoint tiến độ/resume.
- Giải phóng locks theo batch.
- Nhưng làm batch chỉ có **atomicity từng phần**, nếu không có cơ chế publish/cutover.

### Chọn theo nghiệp vụ

Nếu dataset chỉ được public khi đủ toàn bộ, có thể nạp vào **bảng mới/staging riêng** theo nhiều transactions, validate xong rồi **cutover nguyên tử** khi điều kiện cho phép.

Nếu cần cập nhật target online liên tục, dùng microbatches idempotent, progress journal và thông báo trạng thái “batch đang xử lý” đến khi đối soát hoàn tất.

## 45. Ví dụ batch 10.000 rows

Giả sử stage có hàng triệu rows với `batch_id='B-LARGE'`. Một coordinator có thể chia theo `row_no`:

```sql
-- Chunk 1: hàng 1 đến 10000
SELECT *
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-LARGE'
  AND row_no BETWEEN 1 AND 10000;

-- Chunk 2: hàng 10001 đến 20000
SELECT *
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-LARGE'
  AND row_no BETWEEN 10001 AND 20000;
```

Đây chỉ là ví dụ **xác định vùng dữ liệu**, chưa phải toàn bộ pipeline. Ở mỗi chunk, thực hiện:

1. Cast/validate với điều kiện `batch_id,row_no` của chunk.
2. Lưu rejects.
3. UPSERT accepted rows.
4. Ghi checkpoint/progress.
5. Commit.

### Vì sao không viết OFFSET pagination?

Trên dữ liệu rất lớn, `OFFSET` tăng cao có thể tốn chi phí scan/skip và xử lý không ổn định khi nguồn thay đổi. Dùng **keyset/ranges** trên khóa ổn định hoặc một partition/queue ID.

### Chọn chunk size

Không có đáp án phổ quát “10.000 luôn tối ưu”. Thử 1.000, 5.000, 10.000, 50.000... theo row width, index/trigger cost, latency, checkpoint size và khả năng rollback.

## 46. Atomicity và khả năng tiếp tục khi lỗi

Một pipeline xử lý 100 chunks:

```text
Chunk 1..47 COMMITTED
Chunk 48 FAILED
Chunk 49..100 NOT STARTED
```

Nếu batch metadata chỉ ghi “DONE” sau tất cả chunks, downstream không được hiểu bảng đích đã có dataset hoàn chỉnh ngay từ chunk đầu.

### Hai mô hình publish

**Online upsert:** hàng mới hiển thị từng chunk; phù hợp incremental feed, với trạng thái batch/reporting watermark rõ.

**Offline replacement/cutover:** nhập vào bảng hoặc partition chưa public, kiểm chứng đầy đủ, rồi đổi pointer/view/partition trong một thao tác cutover có kiểm soát.

### Quan trọng

Không có “all-or-nothing toàn batch” khi đã commit 47 chunks riêng biệt lên cùng target online. Muốn khả năng rollback toàn dữ liệu, cần design versioning, shadow table hoặc compensation, không chỉ gửi `ROLLBACK` cho transaction hiện tại.

## 47. Idempotency qua source key

Khi network ngắt sau commit, loader có thể không nhận được ACK. Nếu chạy lại:

```sql
INSERT INTO ... ON CONFLICT (tenant_id,source_key) DO UPDATE ...
```

với unique key ổn định, quy trình có thể được thiết kế để tạo cùng **final state** thay vì duplicates.

### Điều kiện

- Key đến từ nguồn đáng tin, không thay đổi sau lần đầu.
- Merge logic có ý nghĩa idempotent.
- No-op update được loại khi dữ liệu không đổi.
- Audit không tạo sự kiện mới vô ích do replay.
- Batch checkpoint/side effects được đồng bộ.

### Cẩn thận nguồn “nhiều phiên bản”

Nếu cùng `source_key` được gửi hai lần với amount khác, UPSERT sẽ cập nhật giá trị mới; đó có thể là correction hợp lệ hoặc một lỗi nguồn. Hãy định nghĩa **latest-wins theo version/timestamp** hoặc conflict-reject policy, không dùng thứ tự file ngẫu nhiên làm quy tắc.

## 48. Batch registry và trạng thái

Một bảng quản lý import:

```sql
CREATE TABLE lesson_bulk_load.load_batches (
    batch_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_checksum TEXT,
    status TEXT NOT NULL
        CHECK (status IN (
            'RECEIVED', 'VALIDATING', 'APPLYING',
            'COMPLETED', 'FAILED'
        )),
    total_rows BIGINT,
    rejected_rows BIGINT,
    applied_rows BIGINT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ
);
```

### Mục đích

- Phát hiện cùng file/batch bị gửi lại.
- Theo dõi tiến độ.
- Có nơi gắn checksum và nguồn.
- Giữ phân biệt **accepted**, **applied**, **rejected**.
- Chỉ đánh dấu completed sau khi validations/checkpoints thành công.

### Không cập nhật status ngược tùy ý

Một batch đã COMPLETED mà client gửi payload khác cùng batch_id cần bị từ chối hoặc tạo phiên bản mới, chứ không đơn giản overwrite raw data và làm mất provenance.

## 49. COPY vào UNLOGGED staging

PostgreSQL hỗ trợ bảng `UNLOGGED`:

```sql
CREATE UNLOGGED TABLE lesson_bulk_load.raw_fast_stage (
    batch_id TEXT NOT NULL,
    row_no BIGINT NOT NULL,
    payload JSONB NOT NULL
);
```

### Ưu điểm tiềm năng

Giảm WAL cho dữ liệu của bảng UNLOGGED, có thể giúp nạp staging nhanh hơn nếu workload phù hợp.

### Đánh đổi lớn

- Dữ liệu unlogged **không crash-safe**; có thể bị xóa/truncate sau crash/recovery.
- Nội dung không được replicate qua streaming replication như logged table.
- Cần khả năng **đọc lại nguồn** khi staging mất.
- Không dùng làm nơi duy nhất chứa bản sao dữ liệu quan trọng.

### Tình huống phù hợp

Raw source vẫn còn trong object storage có checksum, và pipeline có thể nạp lại staging sau crash. Khi đó staging là dữ liệu tạm có thể tái tạo. Nếu staging là bản sao duy nhất của file do đối tác gửi, UNLOGGED là một rủi ro nghiêm trọng.

## 50. TEMP staging và connection pool

`TEMP TABLE` tồn tại theo **PostgreSQL session**, không phải một bảng dùng chung giữa mọi connections.

Nếu ứng dụng tạo temp table trên connection A rồi lấy connection B từ Hikari, B có thể không nhìn thấy temp table.

Nếu dùng PgBouncer **transaction pooling**, transaction sau có thể chạy trên backend PostgreSQL khác; temp table state qua transaction không được đảm bảo.

### Cách làm an toàn

- Giữ create/use/drop temp table trong cùng connection/transaction khi phù hợp.
- Dùng logged/UNLOGGED staging schema cố định cho pipeline nhiều workers.
- Nếu cần temp table sống qua nhiều transactions, dùng session-affine connection/mode phù hợp.
- Không dựa vào việc một HTTP request luôn được mượn đúng physical backend qua pooler.

### ON COMMIT DROP

Bảng tạm trong lab dùng `ON COMMIT DROP`, nên sẽ tự bị xóa khi transaction commit. Điều đó phù hợp với một pipeline validation+merge gọn trong một transaction, không phù hợp nếu muốn lưu lỗi để sửa lại vào ngày sau; lỗi phải được chép vào bảng rejects persistent trước COMMIT.

## 51. COPY FREEZE không phải công tắc bỏ ràng buộc

PostgreSQL có tùy chọn `COPY ... WITH (FREEZE ...)` cho một số kịch bản nạp dữ liệu mới. Mục tiêu là giảm công việc đóng băng tuple khi thỏa điều kiện rất cụ thể, chứ **không** vô hiệu FK/CHECK/UNIQUE hoặc bỏ qua transaction semantics.

### Điều kiện quan trọng

Tính năng áp dụng có giới hạn, ví dụ bảng được tạo hoặc truncation trong subtransaction hiện tại và không có những tình huống snapshot/portal xung đột; đồng thời không hỗ trợ trên mọi dạng bảng, chẳng hạn target partitioned table theo quy tắc PostgreSQL hiện hành.

### Cảnh báo

FREEZE ảnh hưởng khả năng hiển thị tuple theo MVCC trong trường hợp đặc biệt. Không bật nó chỉ vì “nạp nhiều dữ liệu thì luôn dùng FREEZE”; cần đọc tài liệu của phiên bản chạy và test với replication/snapshot behavior.

Trong các luồng staging/merge online của bài, mặc định không cần COPY FREEZE.

## 52. WAL là chi phí tính bền vững

Với bảng logged, bulk load tạo WAL để hỗ trợ crash recovery và replication theo cơ chế PostgreSQL. Những phần phát sinh WAL có thể gồm:

- Heap INSERT/UPDATE.
- Index pages và page splits.
- Trigger ghi thêm bảng audit.
- Visibility/free-space management.
- Full-page images sau checkpoint theo cấu hình.
- Những hoạt động DDL/index build khác.

### Vì sao cần theo dõi?

Một file CSV 10GB không đảm bảo chỉ tạo 10GB data files hoặc 10GB WAL. Nếu có nhiều indexes, JSONB audit và UPSERT updates, tổng write amplification có thể lớn hơn rất nhiều.

### Không tắt WAL cho bảng nghiệp vụ

Giảm `wal_level` toàn cluster hoặc dùng cấu hình durability rủi ro chỉ để tăng tốc nhập có thể ảnh hưởng backup/PITR/replication. Lựa chọn này cần quyết định ở kiến trúc và mục tiêu khôi phục, không phải mẹo mặc định khi import.

## 53. synchronous_commit và đánh đổi durability

Trong một số hệ thống, `synchronous_commit` có thể được điều chỉnh để thay đổi mức chờ WAL flush/replica acknowledgment cho transaction.

Ví dụ chỉ để quan sát cấu hình:

```sql
SHOW synchronous_commit;

SELECT name, setting, context
FROM pg_catalog.pg_settings
WHERE name = 'synchronous_commit';
```

### Không khuyến nghị tắt vô điều kiện

`synchronous_commit=off` có thể giảm commit latency cho những workload có yêu cầu đặc biệt, nhưng một transaction được trả ACK có thể **mất sau crash** trong cửa sổ durability tương ứng. Nếu import không tái tạo được, hoặc `COMPLETED` đã được thông báo cho hệ khác, rủi ro này có thể không chấp nhận được.

Hãy phân biệt throughput nạp, độ bền transaction và khả năng replay từ raw source có checksum.

## 54. Checkpoints và tải ghi lớn

Bulk load có thể tạo nhiều dirty buffers/WAL và làm checkpoint activity tăng. Các yếu tố cần theo dõi:

- WAL bytes/second.
- Checkpoint/writeback thời gian.
- Disk queue depth và I/O latency.
- Replica lag.
- CPU load.
- Burst commit frequency.

### Tối ưu như thế nào?

Không nên chỉnh đồng loạt `shared_buffers`, `max_wal_size`, `checkpoint_timeout` và pool size theo một bộ “magic numbers”. Trước tiên xác định bottleneck là disk, checkpoint, index maintenance hay row triggers rồi benchmark từng thay đổi.

### Staging và replication

UNLOGGED staging có thể giảm WAL cho data tạm, nhưng target logged tables và audit logs vẫn tạo WAL khi merge. Giảm WAL ở một bước không có nghĩa toàn pipeline đã loại bỏ write amplification.

## 55. VACUUM và ANALYZE sau nạp

Sau khi nạp lượng dữ liệu lớn, **statistics** có thể chưa phản ánh phân bố rows mới, khiến planner chọn kế hoạch truy vấn chưa tốt.

```sql
ANALYZE lesson_bulk_load.orders;

ANALYZE lesson_bulk_load.customers;
```

### Phân biệt

**ANALYZE** thu thập thống kê phục vụ planner.

**VACUUM** dọn/recycle dead tuples, cập nhật visibility information và hỗ trợ cơ chế tránh transaction ID wraparound.

**VACUUM ANALYZE** kết hợp công việc khi cần:

```sql
VACUUM (ANALYZE) lesson_bulk_load.orders;
```

### Không chạy VACUUM trong transaction block

`VACUUM` không được thực thi bên trong transaction block tường minh. Lên lịch sau commit theo nhu cầu, tránh chạy cùng lúc với những tác vụ gây I/O cao nếu production đang chịu tải.

### Có nên VACUUM ngay sau COPY sạch?

Không phải cứ COPY INSERT mới là cần VACUUM FULL. Nếu không có dead tuples đáng kể, `ANALYZE` có thể là bước quan trọng hơn; VACUUM thường do autovacuum quản lý. Sau COPY thất bại hoặc UPSERT updates lớn, có thể có nhiều dead tuples cần vacuum.

## 56. AUTOVACUUM trong quá trình import

Autovacuum giúp xử lý dead tuples và statistics theo các thresholds. Bulk import làm table size thay đổi nhanh có thể ảnh hưởng thời điểm autoanalyze/autovacuum.

### Sai lầm

Tắt autovacuum trên toàn cluster để có thêm I/O cho import rồi quên bật lại. Hậu quả có thể là bloat, statistics stale và nguy cơ wraparound dài hạn.

### Lựa chọn hợp lý hơn

- Đo khi nào autoanalyze chạy.
- Chạy `ANALYZE` thủ công sau batch quan trọng.
- Điều chỉnh autovacuum parameters cho bảng cụ thể khi đã có bằng chứng.
- Lên lịch bulk import và maintenance hợp lý.
- Kiểm tra dead tuples, vacuum progress và table bloat.

## 57. pg_stat_progress_copy

PostgreSQL cung cấp view `pg_stat_progress_copy` ở các phiên bản hỗ trợ để quan sát những backend đang chạy COPY:

```sql
SELECT
    pid,
    datid,
    relid::regclass AS target_relation,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_catalog.pg_stat_progress_copy;
```

### Đọc output

- `command` cho biết hướng COPY.
- `type` liên quan nguồn/đích như file, program, pipe, callback tùy phiên bản.
- `bytes_processed` là tiến độ bytes được xử lý.
- `bytes_total` có thể không xác định/không hữu dụng cho một số nguồn như stream.
- `tuples_processed` là số bản ghi mà view cho biết đã xử lý trong scope thống kê.

**Không xem một dòng trong view là số rows đã commit thành công.** Một COPY đang chạy có thể rollback; một COPY nhanh có thể kết thúc trước khi bạn kịp quan sát.

### Phiên bản

Danh sách cột có thể thay đổi, ví dụ một số phiên bản bổ sung metrics cho excluded/skipped tuples. Nếu truy vấn cột không có trong phiên bản cũ, xem `\d pg_stat_progress_copy` trong psql hoặc metadata của view.

## 58. Quan sát index build progress

Với quá trình xây index lớn:

```sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done
FROM pg_catalog.pg_stat_progress_create_index;
```

View có thể thể hiện các phases như scan table, sort tuples, wait for lockers, validation... tùy loại index/version.

### Cần chú ý khi CREATE INDEX CONCURRENTLY

Thời gian có thể dài do phải chờ những transactions cũ, không chỉ vì đọc disk chậm. Nếu job ở phase waiting, đừng vội tăng `maintenance_work_mem` hay dừng backend khác không rõ nguồn.

## 59. Bảng thống kê sau nạp

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_analyze,
    last_autoanalyze,
    last_vacuum,
    last_autovacuum
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_bulk_load'
ORDER BY relname;
```

### Không lấy n_live_tup làm số đếm chính xác

`n_live_tup` là **ước lượng thống kê**, không thay `SELECT count(*)` khi cần đối soát số rows chính xác. Những bộ đếm cumulative có thể bị reset; cần đo **delta** theo thời điểm và kiểm tra thống kê reset.

## 60. Quan sát tiến độ và điểm nghẽn trong pg_stat_activity

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Những tín hiệu:

- `wait_event_type='Lock'`: loader có thể chờ index/row/table locks.
- I/O wait: storage có thể là bottleneck.
- Query age lớn: có thể là COPY/index build/merge lâu.
- `idle in transaction`: batch worker giữ transaction nhưng không làm việc, có nguy cơ giữ locks/snapshots.

### Cảnh báo quyền riêng tư

`query` có thể chứa SQL literals và dữ liệu nhạy cảm nếu application không dùng parameters. Hạn chế quyền xem và log; không đưa nguyên full query/credentials vào dashboard công khai.

## 61. Replica lag khi nạp dữ liệu lớn

Trong streaming replication, bulk imports có thể tạo lượng WAL lớn phải được replica nhận và replay. Hệ quả:

- Read replicas có thể trễ cập nhật.
- Read-after-write từ replica chưa thấy records mới.
- Replication slots/retention có thể giữ WAL lâu.
- Failover readiness có thể bị ảnh hưởng bởi lag.

### Những chỉ số cần theo dõi

- WAL generated rate.
- WAL sent/write/flush/replay positions.
- Replica replay delay.
- Disk free space trên primary/replica.
- Consumer/slot lag nếu dùng logical replication.

### Hệ quả nghiệp vụ

Không đánh dấu import là “đã visible ở mọi nơi” ngay sau primary COMMIT nếu ứng dụng đọc replica và yêu cầu nhất quán tức thời. Định nghĩa completion theo mục tiêu: **committed at primary**, **replicated to standby** hay **published to analytics**.

## 62. Bảo mật COPY và các role đặc quyền

Server-side `COPY FROM '/server/file'`, `COPY PROGRAM` hoặc ghi file server-side có những quyền đặc biệt, chẳng hạn các roles được thiết kế cho server file read/write/program execution.

### Không cấp chỉ để tiện import

Ứng dụng nạp dữ liệu thông thường nên có quyền phù hợp trên bảng/staging và dùng COPY protocol từ client. Không cấp quyền chạy chương trình trên server hoặc đọc tùy ý files trên máy DB.

### Những điều khác cần bảo vệ

- TLS và xác minh server identity.
- Credentials qua secret manager.
- File CSV trong object storage có access policy.
- Temporary staging/rejects có PII.
- Log SQL/job metadata không lộ secrets.
- Tách importer role với migration/admin role.
- Không cho importer tắt triggers/FK.

## 63. COPY và Row-Level Security

PostgreSQL có hạn chế đối với `COPY FROM` trên bảng chịu RLS. Trong các phiên bản tài liệu hiện đại, `COPY FROM` không hỗ trợ nạp trực tiếp vào target có row-level security theo cách như INSERT; có thể phải dùng các `INSERT` tương đương hoặc nạp staging rồi áp policy trong merge.

### Kiến trúc multi-tenant an toàn

1. COPY từ nguồn vào staging có quyền giới hạn.
2. Import service xác thực tenant và scope nguồn.
3. Validate tenant IDs và references.
4. Merge bằng role/policy được thiết kế đúng, trong transaction.
5. Bảng target giữ RLS/FK/unique/business constraints.
6. Ghi batch audit và kiểm chứng cross-tenant isolation.

### Cảnh báo SECURITY DEFINER

Một function SECURITY DEFINER thực thi merge với quyền owner có thể có semantics RLS khác caller, thậm chí bypass trong cấu hình liên quan. Không xem `WHERE tenant_id = p_tenant_id` với tenant từ client là authorization đủ mạnh.

## 64. Song song nhiều workers để tăng throughput

Một loader có thể xử lý nhiều chunks đồng thời:

```text
Staging 10M rows
 ├── worker A: chunk 1
 ├── worker B: chunk 2
 ├── worker C: chunk 3
 └── worker D: chunk 4
           ↓
     PostgreSQL target
```

Nhưng quá nhiều workers có thể:

- Tranh cùng unique index pages.
- Tranh FK/reference locks.
- Tạo deadlocks khi UPDATE cùng keys khác thứ tự.
- Saturate disk/WAL.
- Làm autovacuum/replica lag tăng.
- Vượt connection pool budget.

### Cách thử

Benchmark concurrency 1, 2, 4, 8... cùng chunk size, đo:

```text
rows/s accepted and committed
lock waits / deadlocks
WAL bytes/s
CPU, memory, disk latency
replica lag
error/retry rate
```

Tối ưu **committed good rows/s và tính đúng đắn**, không chỉ số COPY rows đã parse.

## 65. Claim chunks bằng queue và SKIP LOCKED

Một bảng quản lý work items có thể dùng `FOR UPDATE SKIP LOCKED` để nhiều workers claim chunks không chờ nhau:

```sql
CREATE TABLE lesson_bulk_load.load_chunks (
    batch_id TEXT NOT NULL,
    chunk_no INTEGER NOT NULL,
    first_row BIGINT NOT NULL,
    last_row BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (batch_id, chunk_no)
);
```

Ví dụ lấy một task (chỉ minh họa transaction claim):

```sql
BEGIN;

SELECT batch_id, chunk_no, first_row, last_row
FROM lesson_bulk_load.load_chunks
WHERE status = 'PENDING'
ORDER BY batch_id, chunk_no
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Đánh dấu task được chọn thành RUNNING trước COMMIT.
COMMIT;
```

### Lưu ý

Chỉ SELECT FOR UPDATE rồi COMMIT **không tự đánh dấu task**; phải có UPDATE/RETURNING hoặc cơ chế claim state trong transaction. Nếu worker crash sau khi claim, cần lease expiry/requeue policy.

`SKIP LOCKED` hỗ trợ queue consumers, không tự bảo đảm phân phối công bằng hoặc xử lý đúng một lần; idempotency ở target và progress journal vẫn cần.

## 66. Atomic claim với UPDATE ... RETURNING

Ví dụ một câu update claim:

```sql
WITH next_chunk AS (
    SELECT batch_id, chunk_no
    FROM lesson_bulk_load.load_chunks
    WHERE status = 'PENDING'
    ORDER BY batch_id, chunk_no
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE lesson_bulk_load.load_chunks AS q
SET status = 'RUNNING'
FROM next_chunk AS n
WHERE q.batch_id = n.batch_id
  AND q.chunk_no = n.chunk_no
RETURNING
    q.batch_id,
    q.chunk_no,
    q.first_row,
    q.last_row;
```

### Sử dụng thế nào?

Trong transaction có commit rõ ràng, coordinator/worker lấy một chunk rồi chuyển trạng thái RUNNING. Sau khi merge/reconcile thành công, đánh dấu COMPLETED theo contract.

### Cần thêm trong production

- Worker ID và lease deadline.
- Heartbeat.
- Attempt count và retry backoff.
- Dead-letter/failed status.
- Checkpoint/counters theo chunk.
- Bảo vệ khi hai workers cùng nhận lại một chunk sau timeout.

Không giữ row lock của hàng queue trong một transaction chạy import vài phút nếu có thể claim nhanh và sau đó xử lý dưới cơ chế lease.

## 67. Khử trùng lặp giữa các chunks

`ROW_NUMBER() OVER (PARTITION BY tenant_id,source_key ORDER BY row_no)` trong từng chunk chỉ loại duplicates **nội bộ chunk**. Nếu cùng key xuất hiện ở chunk 2 và chunk 8, cả hai có thể được coi là hợp lệ trong từng tập.

### Các lựa chọn

- Pre-deduplicate **toàn bộ batch** trước chunking.
- Xây bảng keys canonical theo nguồn/version.
- Dùng unique constraint đích và `ON CONFLICT` làm bảo vệ cuối cùng.
- Quy định order/version để chọn bản ghi thắng.
- Dùng error/reporting policy nếu duplicate không được phép.

### Vì sao chưa đủ chỉ có ON CONFLICT?

ON CONFLICT có thể bảo đảm không có hai rows cùng unique key, nhưng nếu input mâu thuẫn về amount, nó không tự biết **dòng nào đúng**. Một upsert “last committer wins” trong parallel workers có thể phụ thuộc thứ tự scheduling, không phải nghiệp vụ.

## 68. Version-aware merge để tránh dữ liệu cũ ghi đè mới

Với dữ liệu nguồn có `source_version` tăng đều theo mỗi entity, target có thể lưu version và chỉ update khi phiên bản đến **mới hơn**:

```sql
-- Mẫu khái niệm sau khi hai bảng có cột source_version:
-- INSERT INTO target AS t (source_key, source_version, ...)
-- SELECT source_key, source_version, ...
-- FROM validated_stage
-- ON CONFLICT (source_key) DO UPDATE
-- SET source_version = EXCLUDED.source_version,
--     ...
-- WHERE t.source_version < EXCLUDED.source_version;
```

### Tại sao?

Nếu chunk chứa version 4 được commit trước chunk chứa version 3, merge chỉ theo thời điểm đến có thể làm state cuối lùi về version 3.

### Không nên giả định timestamp là version

Timestamps từ nguồn khác nhau có thể lệch múi giờ/clock, cùng precision hoặc không tăng đơn điệu. Tùy nguồn, dùng event sequence/LSN/source revision đáng tin hơn cho conflict resolution.

## 69. Retry toàn transaction khi deadlock/serialization failure

Trong bulk upsert parallel, một số transaction errors có thể là:

| SQLSTATE | Ý nghĩa |
|---|---|
| `40P01` | Deadlock detected |
| `40001` | Serialization failure |
| `23505` | Unique violation |
| `23503` | Foreign key violation |
| `23514` | Check violation |
| `22P02` | Invalid text representation |
| `53300` | Too many connections |
| `57014` | Query canceled (ví dụ timeout) |

### Retry policy

`40P01` và `40001` thường có thể retry **toàn bộ transaction** với giới hạn và backoff, sau khi xác nhận idempotency.

`23503` có thể là lỗi dữ liệu thiếu customer, không retry tức thì vô hạn.

`23505` có thể là duplicate chưa xử lý hoặc một race; phân loại theo key/policy trước khi quyết định.

`53300` phản ánh cạn connection slots, không phải lời mời mở thêm workers vô hạn.

### Một nguy cơ

Nếu transaction commit nhưng client mất kết nối trước khi nhận ACK, không biết chắc nó đã commit hay chưa. Chỉ retry an toàn với idempotency/reconciliation theo batch key, không chỉ dựa vào exception message.

## 70. Timeout và việc dừng một batch

Những timeout đáng cân nhắc:

- `statement_timeout`: giới hạn thời gian SQL statement.
- `lock_timeout`: giới hạn chờ locks.
- `idle_in_transaction_session_timeout`: phòng transaction bỏ dở.
- Pool acquisition timeout: giới hạn chờ connection.
- Client socket/network timeout: cần phối hợp để tránh treo vô hạn.

### Không dùng một số cố định cho mọi workload

HTTP API có thể đặt statement timeout vài giây, trong khi import/CREATE INDEX có thể cần lâu hơn. Có thể dùng role hoặc transaction-local settings cho batch workers với quyền phù hợp.

### Dừng một COPY

Nếu client hủy/đứt luồng giữa COPY, driver/server có cơ chế kết thúc statement/transaction phù hợp. Phải kiểm tra status, rollback khi lỗi, rồi quyết định retry dựa trên batch journal; không giả định “file gửi được 80% nghĩa target đã commit 80%”.

## 71. JDBC CopyManager trong pgJDBC

PostgreSQL JDBC driver (`org.postgresql:postgresql`) có API hỗ trợ streaming COPY protocol, không cần tạo hàng triệu `PreparedStatement` cho từng row.

Ví dụ Java:

```java
import org.postgresql.PGConnection;

import javax.sql.DataSource;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;

public final class RawOrderCsvLoader {
    private final DataSource dataSource;

    public RawOrderCsvLoader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long copy(Path csvPath)
            throws SQLException, IOException {
        String copySql = """
            COPY lesson_bulk_load.raw_orders (
                batch_id,
                row_no,
                tenant_raw,
                source_key_raw,
                customer_raw,
                amount_raw,
                ordered_on_raw
            ) FROM STDIN WITH (FORMAT csv, HEADER true)
            """;

        try (Connection conn = dataSource.getConnection();
             InputStream input = Files.newInputStream(csvPath)) {
            conn.setAutoCommit(false);
            try {
                PGConnection pg = conn.unwrap(PGConnection.class);
                long copied = pg.getCopyAPI().copyIn(
                    copySql,
                    input
                );
                conn.commit();
                return copied;
            } catch (SQLException | IOException | RuntimeException ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }
}
```

### Ý nghĩa

- `FROM STDIN` nhận stream bytes từ Java client.
- `CopyManager.copyIn` thực hiện COPY protocol của driver.
- `try-with-resources` đóng connection lease và input stream.
- Transaction chỉ commit khi COPY thành công.
- Khi có lỗi, rollback trong cùng connection.

### Những điều còn phải thêm cho production

- Batch registry và duplicate-file detection trước COPY.
- File checksum/size, trusted path/object storage access.
- Upload/parse progress, metrics, cancellation.
- Retry policy có idempotency.
- Deadline/network timeout và pool size riêng nếu cần.
- Không cho bất kỳ client nào tự cung cấp raw SQL COPY command hoặc đường dẫn server.

## 72. JDBC COPY và batch idempotency

Trong Java example, `copy` chèn trực tiếp vào staging có primary key `(batch_id,row_no)`. Nếu ứng dụng mất kết nối **sau COMMIT** nhưng trước khi nhận kết quả, retry cùng CSV có thể gặp duplicate key.

### Một quy trình mạnh hơn

1. Tính SHA-256 của file và cấp `batch_id` bất biến.
2. Đăng ký batch trong bảng `load_batches` với uniqueness.
3. Nếu cùng checksum đã COMPLETED: trả kết quả cũ.
4. Nếu cùng batch_id nhưng checksum khác: từ chối/hỏi xử lý phiên bản mới.
5. Nếu batch đang dở: xác định phần đã commit từ registry/checkpoints.
6. Nạp vào staging sạch dành riêng cho attempt, hoặc có cơ chế resume theo row ranges.
7. Đối soát rồi mark COMPLETED.

### Không chỉ dùng một cờ boolean

Một cờ “already_loaded” không bảo đảm file đúng checksum hay toàn bộ target rows khớp. Cần phân biệt **received**, **parsed**, **validated**, **applied**, **committed**, **published**.

## 73. JDBC batch insert khi không dùng COPY

Không phải mọi nguồn dữ liệu là CSV/stream. Với các object records và cần logic từng hàng, JDBC batching có thể phù hợp:

```java
String sql = """
    INSERT INTO lesson_bulk_load.orders (
        tenant_id, source_key, customer_ref, amount, ordered_on
    ) VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (tenant_id, source_key)
    DO NOTHING
    """;

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);
    try {
        try (var ps = conn.prepareStatement(sql)) {
            for (OrderRow row : rows) {
                ps.setLong(1, row.tenantId());
                ps.setString(2, row.sourceKey());
                ps.setString(3, row.customerRef());
                ps.setBigDecimal(4, row.amount());
                ps.setObject(5, row.orderedOn());
                ps.addBatch();
            }
            ps.executeBatch();
        }
        conn.commit();
    } catch (SQLException | RuntimeException ex) {
        conn.rollback();
        throw ex;
    }
}
```

Ví dụ giả định `rows` là collection các `OrderRow` records có typed fields. Câu SQL `DO NOTHING` chỉ phù hợp khi duplicate được phép bỏ qua; nếu cần update version mới thì dùng conflict policy khác.

### Định kích thước batch

Với hàng triệu rows, không giữ toàn bộ ở `rows` trong bộ nhớ Java. Đọc theo chunks và `executeBatch` mỗi chunk, kiểm soát memory, commit boundaries và error reporting.

### PostgreSQL driver optimization

pgJDBC có một số tối ưu batch INSERT tùy cấu hình, ví dụ `reWriteBatchedInserts`. Cần test với SQL shape/RETURNING/conflict modes thực tế, không giả định mọi batch đều được rewrite giống nhau.

## 74. Kết nối pool cho importer

Một importer có thể chạy trên cùng PostgreSQL với HTTP API nhưng có workload khác:

- Kết nối giữ lâu trong COPY.
- Transaction lớn.
- Burst I/O/WAL.
- Ít workers nhưng mỗi worker dùng tài nguyên nhiều.

### Gợi ý

Đặt một **pool/budget riêng** cho importer với concurrency thấp có kiểm soát, cộng số connections ấy vào ngân sách tổng `max_connections`.

### Không mở một connection cho từng CSV row

Một connection có thể truyền toàn bộ COPY stream; mở connection hàng triệu lần vừa tốn startup vừa phá connection capacity.

### Khi qua PgBouncer

COPY protocol, temporary tables, transaction boundaries và session features cần test theo pooling mode. Với `TEMP TABLE` giữ state qua nhiều transactions, PgBouncer transaction mode không đảm bảo session affinity.

## 75. Streaming và memory budget Java

Với file nhiều GB:

```java
byte[] data = Files.readAllBytes(path);
```

là một cách làm nguy hiểm: toàn bộ dữ liệu được tải vào JVM heap, có thể gây OOM hoặc GC pauses lớn.

### Tốt hơn

```java
try (InputStream in = Files.newInputStream(path)) {
    // Truyền in vào CopyManager.copyIn(...)
}
```

Trong trường hợp cần normalize CSV trước COPY, dùng parser streaming với bounded buffers, không đọc nguyên file rồi nối thành một SQL string.

### Một lưu ý

Streaming giảm **client memory footprint**, không tự giảm WAL/index/trigger work ở PostgreSQL. Nếu server là bottleneck, tăng client buffer lớn vô hạn không làm throughput tăng tương ứng.

## 76. CSV encoding và NULL/empty string

PostgreSQL hiểu dữ liệu theo client/server encodings đã cấu hình. File chứa UTF-8 phải được xử lý đúng:

```sql
SHOW server_encoding;
SHOW client_encoding;
```

### Phân biệt

- SQL NULL: thiếu một giá trị.
- Chuỗi rỗng `''`: giá trị text có độ dài 0.
- Chuỗi `'NULL'`: bốn ký tự, nếu không có convention đặc biệt.
- Field CSV được quote có quy tắc phân biệt với unquoted empty field.

Tùy `COPY ... WITH (NULL '...', FORCE_NULL/FORCE_NOT_NULL)` và format, cách map có thể khác. Định nghĩa file contract rồi test với những dòng có dấu phẩy, dấu nháy, xuống dòng, Unicode và NULL.

### BOM

Một file có UTF-8 BOM có thể khiến tên header/field đầu tiên không khớp kỳ vọng trong một số công cụ. Nên chuẩn hóa encoding ở ingestion boundary và có test fixture cho BOM thay vì âm thầm sửa dữ liệu trong DB.

## 77. Chia file theo partition hoặc theo tenant

Nếu bảng đích được partition:

- COPY vào partitioned parent có thể route rows vào partitions theo policy engine.
- Việc tạo indexes/constraints trên partitioned parent và từng partition có giới hạn/DDL riêng.
- `ATTACH PARTITION`/`DETACH PARTITION` có lock và validation costs.
- Có thể chuẩn bị partitions riêng rồi attach/cutover khi schema và bounds hợp lệ.

### Không tự coi mỗi tenant là một partition

Partitioning giúp các workload cụ thể khi pruning/maintenance phát huy tác dụng. Nếu có hàng chục nghìn tenants, partition-per-tenant có thể tạo catalog overhead rất lớn. Chọn key/number of partitions theo query patterns, retention và volume.

### Constraint và uniqueness

Unique/primary constraints trên partitioned tables có các giới hạn về partition keys. Đừng giả định một global unique index xuyên mọi partitions hoạt động giống bảng thường; cần thiết kế khóa và phiên bản PostgreSQL phù hợp.

## 78. Staging table và cutover

Đối với full refresh của một bảng báo cáo:

```text
Existing table (serving reads)
          │
          ├── Build new_table offline
          ├── COPY validated data
          ├── Build indexes / constraints
          ├── ANALYZE and reconcile
          └── Controlled cutover
                  ↓
             New published data
```

### Cutover không tự đơn giản

Đổi tên bảng bằng DDL, thay view, attach partition hay switch application pointer đều có thể ảnh hưởng:

- Locks.
- Foreign key dependencies.
- Prepared query plans.
- Grants/RLS.
- Replication/CDC.
- Sequences và triggers.

Không tuyên bố `ALTER TABLE ... RENAME` là “zero downtime atomic swap” cho mọi schema. Cần kế hoạch theo dependencies và reader/writer behavior thực.

## 79. Kiểm chứng số rows của lô

Sau nạp, cần đối chiếu:

```text
raw rows
= accepted rows + rejected rows
```

theo **định nghĩa classification**.

Trong lab:

```sql
SELECT count(*) AS raw_rows
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-2026-11';

SELECT count(*) AS rejected_rows
FROM lesson_bulk_load.load_rejects
WHERE batch_id = 'B-2026-11';
```

Để kiểm tra accepted rows/keys, dùng typed/validated data từ pipeline hoặc một báo cáo persisted ngoài temporary table (vì `tmp_orders_checked` đã bị DROP khi COMMIT).

### Không lấy target count chênh lệch làm accepted

Với UPSERT:

- Một accepted row có thể INSERT.
- Một accepted row có thể UPDATE.
- Một accepted row có thể là no-op.

Vì vậy:

`raw = accepted + rejected` là partition của **đầu vào**, còn số target rows tăng chỉ đếm inserts mới, không phải toàn bộ accepted.

## 80. Kiểm chứng duplicates trong source

```sql
SELECT
    batch_id,
    tenant_raw,
    source_key_raw,
    count(*) AS duplicates
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-2026-11'
GROUP BY
    batch_id, tenant_raw, source_key_raw
HAVING count(*) > 1
ORDER BY duplicates DESC;
```

Đây là bước phát hiện sơ bộ ở raw text. Nếu `'10'` và `' 10 '` được normalize thành cùng bigint tenant 10, raw grouping có thể coi chúng khác nhau. Để kiểm tra duplicates theo **business identity thực**, dùng keys đã normalize/cast trước khi xét uniqueness.

### Cẩn thận nguồn nhiều phiên bản

Hai rows cùng source key nhưng source version khác không nhất thiết là duplicates sai; có thể là hai updates của cùng entity. Pipeline cần policy chọn phiên bản thắng theo một sequence đáng tin.

## 81. Kiểm chứng tiền và số liệu aggregate

Một kiểm chứng sau merge:

```sql
SELECT
    tenant_id,
    count(*) AS orders,
    sum(amount) AS total_amount
FROM lesson_bulk_load.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Với dữ liệu mẫu ban đầu:

```text
tenant 10: 2 orders, 425500.00
tenant 20: 1 order,   92000.00
```

### Khi làm trên production

So số liệu này với aggregate **độc lập** từ source sau khi áp cùng rules về duplicates, currency, cutoff và record versions. Nếu cả hai cùng dùng một đoạn logic sai, chúng có thể cho cùng kết quả nhưng vẫn sai nghiệp vụ.

Không chỉ kiểm tra tổng tiền; cần đối chiếu số lượng, distinct keys và một số samples/edge cases.

## 82. Checksum và source provenance

Lưu một checksum như SHA-256 của **file bytes** trong batch registry giúp biết cùng một payload có bị gửi lại hay bị thay đổi.

### Checksum nào?

- Checksum file: phát hiện payload bytes đổi, kể cả khác newline/encoding.
- Checksum các normalized rows: phù hợp kiểm tra nội dung sau canonicalization, nhưng phải định nghĩa thứ tự, null/collation/casts.
- Per-chunk checksum: giúp retry/đối soát từng phần.

### Giới hạn

Checksum giống nhau cho biết bytes/representation phù hợp theo thuật toán, nhưng không chứng minh source được phép truy cập, dữ liệu đúng business semantics hay đã được apply đầy đủ vào target.

Không tự coi một hash lưu ở cùng hệ thống bị tấn công là chứng cứ chống sửa đổi tuyệt đối.

## 83. Vì sao không kiểm tra chỉ bằng count(*)?

Giả sử source có keys:

```text
SO-001, SO-002, SO-003
```

target có:

```text
SO-001, SO-002, SO-004
```

Cả hai có count=3 nhưng một key bị thiếu và một key thừa.

### Kiểm chứng tốt hơn

- Count tổng input/accepted/rejected/applied.
- Distinct business keys.
- Anti-joins kiểm tra missing/extra keys.
- Field-level comparisons hoặc aggregate hash có canonicalization.
- Sum/Min/Max theo tenant/currency/date.
- Transaction/batch version consistency.

Với nguồn rất lớn, có thể kiểm tra theo partitions/chunks để tránh full table scan ảnh hưởng production.

## 84. Tìm dữ liệu đích thiếu so với staging hợp lệ

Khi còn bảng `tmp_orders_checked` trong transaction, có thể:

```sql
SELECT
    t.tenant_id,
    t.source_key
FROM tmp_orders_checked AS t
LEFT JOIN lesson_bulk_load.orders AS o
  ON o.tenant_id = t.tenant_id
 AND o.source_key = t.source_key
WHERE t.reject_reason IS NULL
  AND o.order_id IS NULL;
```

Kỳ vọng **0 rows** sau một merge thành công và trước COMMIT, nếu không có tác nhân khác thay đổi target theo cách gây sai khác trong snapshot đang kiểm tra.

### Khi COMMIT đã xảy ra

`tmp_orders_checked` sẽ không còn. Vì thế nếu cần post-commit reconciliation, lưu canonical accepted rows/keys hoặc một manifest bền vững theo batch, không dựa vào temporary table đã bị xóa.

## 85. Kiểm chứng ràng buộc ở target

Ví dụ tìm rows có amount âm (dự kiến không thể có nếu CHECK đang được thực thi):

```sql
SELECT order_id, tenant_id, source_key, amount
FROM lesson_bulk_load.orders
WHERE amount < 0;
```

Tìm orphan customer:

```sql
SELECT o.order_id, o.tenant_id, o.customer_ref
FROM lesson_bulk_load.orders AS o
LEFT JOIN lesson_bulk_load.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_ref = o.customer_ref
WHERE c.customer_ref IS NULL;
```

Tìm duplicate keys:

```sql
SELECT tenant_id, source_key, count(*)
FROM lesson_bulk_load.orders
GROUP BY tenant_id, source_key
HAVING count(*) > 1;
```

### Điều cần biết

Những truy vấn này là đối soát bổ sung. Sự đảm bảo chống dữ liệu xấu vẫn chủ yếu đến từ **constraints được enable và validate**, không phải chỉ một query kiểm tra chạy sau import rồi không chạy lại nữa.

## 86. Kiểm chứng trigger/audit sau import

```sql
SELECT
    action,
    count(*) AS events
FROM lesson_bulk_load.order_audit
GROUP BY action
ORDER BY action;

SELECT
    event_id,
    action,
    order_id,
    old_row ->> 'amount' AS old_amount,
    new_row ->> 'amount' AS new_amount
FROM lesson_bulk_load.order_audit
ORDER BY event_id DESC
LIMIT 20;
```

### Một điểm quan trọng

Không kỳ vọng số audit INSERT events bằng số raw rows khi staging có rejects, duplicates hoặc UPSERT update existing targets.

Nếu audit là yêu cầu compliance, cần đảm bảo migrations/bulk load không disable trigger và có monitoring trigger enabled state; một lượng event **ít hơn** số raw rows chưa tự chứng minh lỗi.

## 87. Tỷ lệ lỗi và chính sách cho phép batch

Giả sử batch có 1.000.000 dòng và 3.000 rejects:

\[
\text{reject rate}
= \frac{3000}{1000000}\times 100\%
= 0.3\%
\]

### Ba chính sách thường gặp

**Strict:** chỉ commit/publish nếu reject rate=0.

**Threshold:** cho phép một tỷ lệ lỗi nhỏ, nhưng vẫn lưu rejects và thông báo chính xác.

**Partial acceptance:** apply accepted rows, để rejected rows sửa lại sau.

### Chọn theo nghiệp vụ

Một bảng kế toán có thể yêu cầu strict; một feed marketing enrichment có thể cho phép partial acceptance. Không tự áp threshold=1% cho mọi domain.

### Công bố số liệu

Phân biệt:

- `total_raw`.
- `valid_rows`.
- `invalid_rows`.
- `inserted_rows`.
- `updated_rows`.
- `unchanged_rows`.
- `published_rows`.

Đặc biệt với UPSERT, `valid_rows` khác `inserted_rows`.

## 88. Reconciliation trước khi đánh dấu COMPLETED

Một batch được coi hoàn thành khi:

1. Raw source được lưu và checksum xác minh.
2. Các chunks/records expected đã được xử lý.
3. Rejected rows có reason/provenance.
4. Target constraints không phát hiện lỗi.
5. Các accepted keys đã có đúng final state.
6. Các side effects nội bộ như audit/outbox được commit đồng bộ.
7. Có snapshot/watermark phù hợp nếu downstream cần.
8. Các metrics/replica requirements đã đạt theo contract.
9. Batch status được cập nhật atomically với checkpoint cuối hoặc qua protocol an toàn.

### Không dùng status COMMIT trước rồi merge sau

Nếu ghi `load_batches.status='COMPLETED'` ở một transaction trước khi target merge transaction thực sự commit, hệ thống khác có thể đọc trạng thái completed sai.

Trong pipeline nhiều transactions, dùng trạng thái trung gian và reconciliation cuối rõ.

## 89. Khi nào cần khóa hoặc cô lập writer khác?

Một bulk import full-refresh có thể mâu thuẫn với writers online:

- Batch xây trạng thái snapshot.
- API đồng thời cập nhật một số order.
- Loader thay bảng/UPSERT và ghi đè thay đổi mới.

### Cách thiết kế

- Version-aware merge hoặc optimistic locking.
- Cutover vào một bảng mới với writer coordination.
- Transaction isolation/locks ở mức phù hợp.
- CDC tailing để bắt kịp thay đổi trong giai đoạn nạp.
- Quiesce writes trong một cửa sổ bảo trì khi business cho phép.

Không chỉ “chọn SERIALIZABLE” cho một transaction lớn rồi mặc định mọi race biến mất: vẫn có retry, contention và giới hạn thiết kế.

## 90. Rủi ro lock khi thay indexes/constraints

Các thao tác:

- `ALTER TABLE ADD CONSTRAINT`.
- `VALIDATE CONSTRAINT`.
- `CREATE INDEX`.
- `CREATE INDEX CONCURRENTLY`.
- `ALTER TABLE ATTACH PARTITION`.
- `TRUNCATE`.

có lock modes và thời gian giữ khác nhau. Một import rất nhanh có thể bị ảnh hưởng bởi DDL lock hoặc làm migration waits kéo dài.

### Thực hành

- Test lock behavior trên staging với workload đại diện.
- Đặt `lock_timeout` cho migration nếu phù hợp.
- Theo dõi `pg_locks`/`pg_stat_activity` khi thấy blocked backend.
- Không đặt DDL phá schema vào transaction nạp khổng lồ.
- Có rollback/cancellation criteria.

`CREATE INDEX CONCURRENTLY` giảm chặn writes nhưng có thể chờ transactions lâu; không diễn giải “concurrently” thành “không bao giờ có tác động”.

## 91. Bảng quyết định nhanh

| Yêu cầu | Ưu tiên xem |
|---|---|
| File sạch, bảng mới | COPY trực tiếp, tạo indexes phù hợp sau |
| File có nhiều dòng lỗi | Raw staging + validation + reject log |
| Target online | Giữ constraints/unique arbiter, microbatch UPSERT |
| Cần idempotent retry | Batch ID + checksum + unique source key |
| Bảng đích có nhiều trigger | Benchmark overhead, audit/transition table design |
| FK tới bảng cha | Load parent trước, validate references và giữ FK |
| Thêm FK vào bảng lớn hiện hữu | `NOT VALID` + `VALIDATE CONSTRAINT` khi phù hợp |
| Tạo index cho bảng online | `CREATE INDEX CONCURRENTLY` với runbook |
| Tạo index cho bảng offline | `CREATE INDEX` thường có thể phù hợp |
| Nạp source lớn nhưng có thể replay | Cân nhắc UNLOGGED staging |
| Cần staging qua nhiều connections | Persistent staging, tránh chỉ dùng TEMP |
| Multi-tenant + RLS | Validate tenant, áp quyền tại merge, test RLS/COPY behavior |
| Import gây replica lag | Giới hạn throughput, monitor WAL/replay |
| Need all-or-nothing full refresh | Shadow table/cutover hoặc transaction model phù hợp |
| Need incremental online feed | Idempotent chunks + progress journal |

## 92. Runbook: COPY lỗi do dữ liệu

1. Ghi `batch_id`, source checksum, file location và dòng lỗi khi có.
2. Đọc SQLSTATE: lỗi parse (`22P02`), range, FK (`23503`), unique (`23505`), check (`23514`), not-null (`23502`).
3. Phân biệt lỗi CSV syntax, type conversion và business constraints.
4. Nếu transaction đã aborted, rollback; không tiếp tục gửi SQL trong transaction lỗi.
5. Không tự sửa file gốc mà không đổi checksum/version.
6. Nạp vào raw staging nếu cần báo đầy đủ các lỗi theo dòng.
7. Áp correction rule có review và kiểm chứng.
8. Retry theo batch/chunk idempotent.
9. Reconcile keys/counts/amounts sau xử lý.
10. Ghi rõ các rejects được bỏ qua hay sửa hợp lệ, không làm biến mất lịch sử lỗi.

### Khi COPY trực tiếp đã ghi một phần heap rồi lỗi

Kiểm tra khả năng thu hồi không gian qua VACUUM/autovacuum sau rollback. Đừng chạy `VACUUM FULL` trên bảng production lớn như phản ứng đầu tiên: nó đòi lock mạnh và có thể gây downtime.

## 93. Runbook: import chậm vì index hoặc FK

1. Đo rows/s **đã commit**, không chỉ bytes đọc từ CSV.
2. So chi phí COPY vào staging không constraints với merge vào target.
3. Xem index count/type/size của target.
4. Xem `pg_stat_activity.wait_event` và lock waits.
5. Xác nhận referenced keys có index phù hợp.
6. So thời gian trigger function/audit overhead.
7. Kiểm tra WAL, disk, buffer pressure, replica lag.
8. Test batch size/concurrency nhỏ hơn hoặc khác.
9. Với bảng mới offline, benchmark build index sau load.
10. Trên online target, **không tự drop constraints** để đạt một benchmark đẹp.

### Một cách đo có ích

Test cùng dữ liệu trên:

- Staging raw.
- Target với constraints/indexes nhưng chưa audit (chỉ trên **bản clone lab**).
- Target với constraints/indexes/audit như production.

Chênh lệch có thể giúp định vị overhead, nhưng kết quả phải đo dưới workload/concurrency đúng.

## 94. Runbook: số dòng đích không đúng sau nạp

1. So total raw, valid, rejected, duplicates.
2. Xem UPSERT đã INSERT, UPDATE hay no-op.
3. Kiểm tra business key normalization và tenant scope.
4. Kiểm tra source keys xuất hiện ở nhiều chunks.
5. Kiểm tra batch version/correction policy.
6. Chạy anti-join từ accepted staging sang target.
7. So aggregate theo tenant/date/currency.
8. Xem transaction logs/status và retry sau crash.
9. Kiểm tra hàng bị DELETE/UPDATE bởi writers khác sau merge.
10. Chỉ mark COMPLETED khi reconciliation vượt qua các điều kiện đã định.

### Không tạo số liệu bằng cách “nạp thêm một lần nữa”

Nếu nguồn có duplicate hoặc merge không idempotent, nạp lại có thể làm tình hình tệ hơn. Phải hiểu invariant và conflict policy trước khi retry.

## 95. Runbook: phát hiện thiếu audit sau bulk import

1. Xác nhận trigger có được tạo trước import không.
2. Đọc `pg_trigger.tgenabled`, migration logs và audit policy.
3. Kiểm tra COPY/INSERT path đã thực sự tác động target không.
4. Phân biệt rejects, no-op UPSERT và target row inserts.
5. Xem trigger function có bỏ qua events theo policy không.
6. Kiểm tra TRUNCATE, replication apply, bypass/disabled triggers.
7. Đối soát audit với **committed target effects**, không với tổng raw rows.
8. Nếu có gap, ghi nhận provenance và sửa bằng cơ chế correction/baseline minh bạch.

### Không làm giả lịch sử

Nếu đã nạp trước khi bật trigger, không chèn lại một loạt audit INSERT events với thời gian hiện tại rồi khẳng định đó là thời gian nạp gốc. Có thể tạo **BASELINE** record với metadata rõ ràng nếu compliance cho phép.

## 96. Kịch bản end-to-end cho một file 100 triệu dòng

Một kiến trúc được cân nhắc:

```text
Object storage immutable upload
     └─ SHA-256 + batch registry
             └─ Partition files / chunks
                     └─ COPY to staging (bounded workers)
                             ├─ normalize + classify
                             ├─ persist rejects
                             └─ accepted canonical keys
                                     └─ merge target
                                           ├─ PK/UNIQUE
                                           ├─ CHECK/NOT NULL
                                           ├─ FK
                                           └─ audit/outbox triggers
                                                   └─ COMMIT chunk
     └─ reconcile all chunks + source/version checks
             └─ ANALYZE/monitor replica lag
                     └─ mark batch COMPLETED / publish watermark
```

### Tại sao không giữ một transaction cho 100 triệu rows?

Một transaction cực lớn có thể tăng rollback cost, lock/snapshot duration và disk/WAL pressure. Nhưng chia chunks làm giảm atomicity của **toàn batch**. Cần quyết định explicit: partial online visibility hay publish/cutover sau khi đủ dataset.

### Những điều cần thử trước production

- Failure ở dòng giữa file.
- Failure sau COMMIT nhưng mất ACK.
- Duplicate business key ở hai chunks.
- Tăng workers và deadlocks.
- Replica bị lag.
- Full disk/WAL pressure.
- DB restart, loader restart và resume.
- Thay schema/constraint giữa batch.
- Importer role mất quyền.
- Audit/outbox trigger lỗi.

## 97. Bảng tổng hợp trade-off khi nạp dữ liệu lớn

| Quyết định | Được gì? | Đổi lại |
|---|---|---|
| COPY thay nhiều INSERT đơn lẻ | Streaming throughput, ít round trips | Cần hiểu COPY protocol, lỗi giữa lô |
| Staging trước target | Phân loại rejects, khử duplicate, dễ replay | Thêm I/O, storage và orchestration |
| Keep target constraints | Invariants được engine bảo vệ mọi writer | Chi phí kiểm tra/lookup/index |
| Nạp bảng mới rồi tạo index | Có thể giảm chi phí duy trì index per-row | Cần offline phase và validation/cutover |
| CREATE INDEX CONCURRENTLY | Giảm chặn writes khi index bảng online | Thời gian/overhead cao và invalid index nếu lỗi |
| FK NOT VALID rồi VALIDATE | Tách việc thêm constraint khỏi scan dữ liệu cũ | Validation vẫn tiêu tốn I/O/locks; hàng mới vẫn bị kiểm tra |
| Row audit trigger | Snapshot từng hàng, transactional | CPU, JSONB, WAL, audit storage |
| Statement transition table | Xử lý set-based một statement | Giới hạn triggers/DDL và key matching |
| Một transaction lớn | Atomic toàn lô | Rollback cost, locks, failure blast radius |
| Chia chunk commit | Dễ resume và giới hạn transaction | Partial visibility, cần progress/reconcile |
| UNLOGGED staging | Giảm WAL cho dữ liệu tạm | Không crash-safe/không replicate |
| Nhiều workers | Có thể tăng thông lượng | Contention, WAL/IO/replica lag, deadlock |
| COPY FREEZE khi đủ điều kiện | Giảm một số chi phí freeze về sau | Điều kiện nghiêm ngặt và MVCC caveats |
| ANALYZE sau load | Planner nhận statistics mới | Tốn scan/tài nguyên, cần timing |

Mục đích của bảng là chỉ ra **mỗi tối ưu hóa mang theo điều kiện và chi phí**; không có cấu hình vạn năng.

## 98. Checklist trước khi bắt đầu import production

### Nguồn và dữ liệu

- File immutable hoặc có version/checksum chưa?
- Đã xác nhận encoding/CSV dialect/NULL semantics chưa?
- Có định danh duy nhất cho batch, row và business entity không?
- Có quy tắc xử lý duplicate, late arrival và correction không?
- Có biết reject rate được phép theo nghiệp vụ không?

### Schema và quyền

- Target `NOT NULL`/`CHECK`/`UNIQUE`/`FK` đã đủ để bảo vệ invariants chưa?
- Có RLS, triggers hoặc column defaults tác động đến COPY/UPSERT không?
- Importer role chỉ có quyền cần thiết chưa?
- Chỉ mục nào phải tồn tại trước import để giữ correctness?
- Có migration cần tạo index/constraint mới, lock impact đã được đánh giá chưa?

### Tài nguyên và vận hành

- Đủ disk/WAL/headroom trên primary và replica không?
- Importer concurrency có nằm trong DB/pool budget không?
- Có quy định transaction/chunk size và timeout không?
- Có monitor progress COPY/index build, lock waits, autovacuum, replica lag không?
- Có kế hoạch dừng/resume khi network/db restart không?

### Kiểm chứng và phát hành

- Có phân loại accepted/rejected và lý do theo hàng không?
- Có đối soát counts, keys, sums và checksums không?
- Có kiểm tra trigger/audit coverage không?
- Có ngưỡng và rollback criteria chưa?
- Khi nào mới đổi trạng thái batch thành COMPLETED?
- Downstream đọc partial dữ liệu hay chỉ dữ liệu đã published?

Checklist này phục vụ **vận hành pipeline nạp dữ liệu**, không phải quy trình QA tài liệu học.

## 99. Bộ bài tập thực hành

### Bài 1 — Lựa chọn phương thức nạp

Một nguồn CSV có 5 triệu hàng, đã được kiểm tra, target mới và chưa có người dùng. So sánh JDBC batch INSERT với COPY trực tiếp. Những điều kiện nào quyết định cách chọn?

### Bài 2 — COPY và psql \copy

Viết ví dụ `COPY ... FROM '/server/file.csv'` và `\copy ... FROM '/client/file.csv'`. Đường dẫn thuộc máy nào và vì sao role ứng dụng không nên có quyền server-file access?

### Bài 3 — Tạo schema customers/orders

Tạo `customers(tenant_id,customer_ref)` và `orders` với `NOT NULL`, `CHECK amount>=0`, `UNIQUE (tenant_id,source_key)` và FK kết hợp hai cột.

### Bài 4 — Cross-tenant FK

Khách `CUS-01` tồn tại ở tenant 20 nhưng không tồn tại ở tenant 10. Vì sao một order tenant 10 tham chiếu `CUS-01` không được xem là hợp lệ chỉ vì customer_ref tồn tại ở tenant khác?

### Bài 5 — Raw staging

Tạo bảng `raw_orders` với các fields dạng TEXT và `batch_id,row_no`. Giải thích vì sao raw staging có thể giữ dữ liệu mà target typed sẽ từ chối.

### Bài 6 — Chuẩn bị CSV

Tạo file có đúng header/cột như bài lab. Thêm một field chứa dấu phẩy được quote, một tên Unicode, một amount có dấu phẩy phân nhóm và một trường rỗng. Xác định những lỗi format và nghiệp vụ khác nhau.

### Bài 7 — pg_input_is_valid

Trên PostgreSQL 16+, dùng `pg_input_is_valid` phân biệt bigint hợp lệ, bigint overflow, date sai và numeric không parse được. Vì sao regex đơn giản không đủ kiểm tra tất cả?

### Bài 8 — CASE trước cast

Viết `CASE WHEN pg_input_is_valid(...) THEN text::numeric END`. Chứng minh dòng `not-a-number` trở thành NULL được phân loại thay vì làm câu SELECT cast trực tiếp lỗi.

### Bài 9 — Data quality rules

Phân loại các lỗi `INVALID_TENANT`, `MISSING_SOURCE_KEY`, `NEGATIVE_AMOUNT` và `INVALID_DATE`. Chọn precedence khi một dòng có nhiều lỗi.

### Bài 10 — Reject log

Tạo `load_rejects(batch_id,row_no,reason,raw_payload)`, chèn lỗi từ staging và dùng `ON CONFLICT` để lần chạy lại không tạo duplicate reject key.

### Bài 11 — Duplicate trong một file

Thêm hai rows cùng `(tenant_id,source_key)` nhưng khác row_no. Dùng `row_number() OVER(PARTITION BY ... ORDER BY row_no)` để chọn một row và báo reject row còn lại.

### Bài 12 — Duplicate giữa nhiều chunks

Một key xuất hiện ở chunk 2 và 8. Tại sao dedup chỉ ở từng chunk chưa đủ? Đề xuất batch-wide canonical key set hoặc source-version policy.

### Bài 13 — UPSERT hợp lệ

Viết `INSERT ... SELECT` từ temporary validated rows và `ON CONFLICT(tenant_id,source_key) DO UPDATE`. Giải thích vai trò của unique arbiter.

### Bài 14 — UPSERT no-op

Thêm điều kiện `WHERE (target.field1,target.field2) IS DISTINCT FROM (...)`. Chạy lại cùng batch; so số audit events và target updates.

### Bài 15 — Một UPSERT chạm cùng row hai lần

Không dedup đầu vào rồi thử UPSERT hai rows cùng target key trong một statement. Giải thích lỗi cardinality có thể xảy ra và cách tránh.

### Bài 16 — Constraint CHECK và NULL

Vì sao `CHECK (amount>=0)` không đủ để đảm bảo amount khác SQL NULL? Thiết kế column có cả `NOT NULL` và CHECK.

### Bài 17 — FK validation

Thử nạp một đơn tham chiếu customer không tồn tại. So lỗi trả về từ target với reject reason do pre-validation ở staging tạo ra.

### Bài 18 — FOREIGN KEY NOT VALID

Trên một bảng lab riêng đã có dữ liệu, thêm FK `NOT VALID` rồi `VALIDATE CONSTRAINT`. Lúc chưa validate, một hàng INSERT mới có bị kiểm tra FK không?

### Bài 19 — CHECK NOT VALID

Thêm CHECK `amount <= 1000000000 NOT VALID` trên một bảng có dữ liệu cũ. Xác nhận new writes chịu ràng buộc rồi validate dữ liệu cũ.

### Bài 20 — UNIQUE không dùng NOT VALID

Phân biệt cách thêm UNIQUE với CHECK/FK. Lập kế hoạch tạo unique index concurrently rồi attach constraint nếu điều kiện cho phép, không cố viết `UNIQUE ... NOT VALID`.

### Bài 21 — Chi phí indexes

Một bảng có PK, unique source key và sáu B-tree indexes phụ. Nêu chi phí index maintenance với 10 triệu INSERT rows và khi nào có thể xây indexes sau load.

### Bài 22 — CREATE INDEX CONCURRENTLY

Trên bảng lab, chạy `CREATE INDEX CONCURRENTLY` từ session top-level. Vì sao nó không được chạy trong `BEGIN ... COMMIT`? Làm gì nếu build thất bại và index ở trạng thái invalid?

### Bài 23 — Audit row trigger

Tạo `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW` trigger ghi OLD/NEW snapshots. Nạp ba rows hợp lệ và đếm events.

### Bài 24 — Trigger overhead

Giả sử 1 triệu target inserts tạo 1 triệu JSONB audit rows. Những tài nguyên nào tăng ngoài riêng kích thước bảng orders?

### Bài 25 — Statement trigger với transition table

Tạo bảng demo và trigger `AFTER INSERT ... REFERENCING NEW TABLE`; ghi history bằng `INSERT ... SELECT`. So số lần gọi function với row trigger cho một INSERT 10.000 rows.

### Bài 26 — Không DISABLE TRIGGER ALL tùy tiện

Vì sao `ALTER TABLE ... DISABLE TRIGGER ALL` có thể nguy hiểm cho FK và audit? Đề xuất staging/NOT VALID/index scheduling thay vì bỏ constraints.

### Bài 27 — Một transaction hay nhiều chunks?

So sánh nạp 50 triệu rows trong một transaction với 100 chunks tự commit. Trình bày all-or-nothing, rollback cost, resume và partial visibility.

### Bài 28 — Batch registry

Thiết kế `load_batches` có checksum, status, total/rejected/applied counts. Phân biệt nhận file với hoàn thành merge.

### Bài 29 — Retry sau mất COMMIT ACK

Connection mất ngay sau khi loader gửi COMMIT. Tại sao không thể tự quyết định chưa commit? Viết cơ chế tra batch ID/checksum và retry idempotent.

### Bài 30 — UNLOGGED staging

Tạo một bảng UNLOGGED trong lab. Nêu lý do tăng throughput có thể xảy ra và dữ liệu nào sẽ có nguy cơ mất sau crash; vì sao raw source phải có thể replay?

### Bài 31 — TEMP staging và PgBouncer

Một job tạo TEMP table trong transaction 1, commit rồi đọc ở transaction 2 qua PgBouncer transaction pooling. Vì sao không thể giả định cùng backend session?

### Bài 32 — WAL và replication lag

Import gây WAL tăng nhanh và replica trễ 2 phút. Nêu metrics phải theo dõi và phân biệt “committed trên primary” với “visible trên read replica”.

### Bài 33 — ANALYZE và VACUUM

Sau khi nạp hàng triệu rows, planner chọn Seq Scan bất ngờ. Viết lệnh `ANALYZE` và giải thích khác biệt với VACUUM; khi nào chạy VACUUM ngoài transaction?

### Bài 34 — pg_stat_progress_copy

Trong lúc COPY chạy, truy vấn `pg_stat_progress_copy`. Những cột nào phản ánh tiến độ? Vì sao `tuples_processed` không phải số rows đã commit?

### Bài 35 — Parallel workers và SKIP LOCKED

Thiết kế `load_chunks` và truy vấn claim bằng `UPDATE ... FROM (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING`. Thêm lease timeout và retry logic.

### Bài 36 — JDBC CopyManager

Viết Java method streaming CSV qua `PGConnection.getCopyAPI().copyIn`, dùng try-with-resources, commit thành công, rollback khi lỗi. Vì sao không dùng `Files.readAllBytes` với file nhiều GB?

### Bài 37 — COPY và security

Giải thích tại sao importer role không nên được cấp quyền chạy server-side `COPY PROGRAM`, tắt triggers hoặc là superuser. Thiết kế cấp quyền tối thiểu.

### Bài 38 — RLS và tenant scope

Một bảng target bật RLS và dữ liệu nhiều tenants. Thiết kế staging + merge bảo vệ tenant, đồng thời giải thích vì sao current_setting tenant từ untrusted user không tự là bằng chứng authorization.

### Bài 39 — Reconciliation

Một batch có 1 triệu raw rows, 10.000 rejects, 5.000 accepted duplicates/no-ops và 985.000 accepted mới/update. Hãy xác định những counters cần lưu; vì sao chỉ xem `count(*)` trên target sau nạp không đủ?

### Bài 40 — Thiết kế pipeline lớn đầy đủ

Một công ty cần nạp 100 triệu đơn hàng từ nhiều file CSV:

- Dữ liệu có lỗi kiểu, thiếu customer, source keys trùng và late corrections.
- PostgreSQL target đang phục vụ ứng dụng 24/7.
- Có FK/UNIQUE/CHECK và row audit trigger.
- Read replicas phải tiếp tục phục vụ báo cáo.
- Không được phá lịch sử audit để tối ưu nạp.
- Import chạy qua Java/Spring và PgBouncer.
- Có thể mất kết nối sau COMMIT, worker bị restart hoặc một chunk thất bại.

Hãy xây phương án:

1. Bảo vệ nguồn bằng batch ID, checksums và storage quyền tối thiểu.
2. Chọn COPY vào logged/UNLOGGED staging hay COPY trực tiếp và giải thích.
3. Phân loại typed/business errors, lưu rejects có thể tái xử lý.
4. Khử duplicates trong batch và xử lý source version.
5. Thiết kế `INSERT ... ON CONFLICT` idempotent không tạo UPDATE no-op.
6. Giữ FK/UNIQUE/CHECK/audit contract, chọn chiến lược indexes.
7. Dùng chunk queues và bounded parallel workers, chọn timeout/transaction size.
8. Xử lý PostgreSQL/Java errors, mất COMMIT ACK và retry toàn transaction.
9. Đo COPY, index build, WAL, locks, autovacuum, replica lag và committed good rows/s.
10. Reconcile counts/keys/sums/checksums, publish dữ liệu và đánh dấu COMPLETED.

## 100. Kết luận

**Nạp dữ liệu lớn vào PostgreSQL không đơn giản là chạy COPY nhanh nhất có thể.** Mục tiêu là đưa đúng dữ liệu vào đúng bảng, bảo đảm khóa chính, khóa duy nhất, khóa ngoại, CHECK và trigger behavior vẫn được tôn trọng, đồng thời giữ khả năng dừng, sửa, chạy lại và chứng minh kết quả.

**COPY** thường rất hiệu quả với dữ liệu sạch hoặc khi streaming vào staging. **Staging** thêm một bước nhưng cho phép giữ raw rows, phân loại lỗi theo batch/row, chuẩn hóa kiểu, loại duplicates và chỉ hợp nhất các bản ghi hợp lệ vào target. **Unique constraint và ON CONFLICT** là công cụ bảo vệ idempotency của business key; **FOREIGN KEY/CHECK/NOT NULL** bảo vệ tính đúng đắn cuối cùng, kể cả khi validation staging có race hoặc lỗi code.

**Indexes và triggers có chi phí thật.** Với bảng mới/offline, có thể nạp rồi tạo secondary indexes/constraints; với bảng đang phục vụ, thường phải giữ unique/FK/audit và chọn online index build, batch sizing, throttling phù hợp. **NOT VALID/VALIDATE** hữu ích khi thêm một số constraints vào bảng lớn nhưng không có nghĩa hàng mới được phép vi phạm. Tắt trigger nội bộ hoặc giảm durability mà không có kế hoạch chỉ chuyển chi phí sang rủi ro mất dữ liệu.

Cuối cùng, chọn **transaction boundaries, chunk progress, WAL/replica monitoring, vacuum/analyze, JDBC streaming và idempotent replay** theo khả năng phục hồi của hệ thống. Một batch chỉ thật sự hoàn tất khi raw/accepted/rejected/applied counts, business keys, constraints, audit và trạng thái downstream được đối soát theo hợp đồng đã định. **Tốc độ nạp có giá trị chỉ khi kết quả nạp đúng, có thể kiểm chứng và có thể phục hồi.**
