# Thiết kế nhập dữ liệu có thể chạy lại và đối soát trong PostgreSQL

## 1. Vì sao một pipeline nhập dữ liệu phải chạy lại được?

Một hệ thống nhận đơn hàng từ đối tác qua file CSV hoặc message queue. Mỗi đêm, pipeline lấy dữ liệu, kiểm tra, cập nhật bảng PostgreSQL và ghi nhận watermark để biết lần sau bắt đầu từ đâu.

Một lần chạy có thể gặp các sự cố:

- File đã tải xong nhưng worker chết trước khi cập nhật trạng thái batch.
- Database đã commit dữ liệu, nhưng ứng dụng mất kết nối trước khi nhận phản hồi.
- Message broker gửi lại cùng một message sau khi consumer không xác nhận kịp.
- Một batch chứa 100.000 dòng, 99.000 dòng đã xử lý thì tiến trình dừng.
- Cùng một bản ghi đến hai lần, hoặc đến sai thứ tự.
- Hai worker cùng nhận một batch do lease hết hạn.
- File nguồn thay đổi nội dung nhưng vẫn giữ tên file cũ.
- Dữ liệu đích đã được cập nhật nhưng checkpoint chưa được ghi.
- Một snapshot bị thiếu trang nhưng pipeline vẫn tưởng đã nhập đầy đủ.
- Số lượng rows khớp nhưng giá trị một số cột đã sai.

Nếu chạy lại một pipeline như vậy bằng thao tác `INSERT` đơn giản, có thể tạo duplicate, ghi đè dữ liệu mới bằng dữ liệu cũ, hoặc xóa nhầm records.

Một pipeline tốt phải có hai khả năng:

1. **Idempotent ingestion:** nhận lại cùng batch/message nhiều lần vẫn dẫn tới cùng trạng thái dữ liệu đích.
2. **Reconciliation:** so sánh nguồn, dữ liệu đã nhận, dữ liệu đã áp dụng và dữ liệu đích để phát hiện thiếu, thừa hoặc sai khác.

```text
Source file / CDC / API / Message queue
                  |
                  v
          Register batch identity
                  |
                  v
        Immutable raw landing area
                  |
                  v
       Parse, normalize, validate
                  |
                  v
         Typed staging tables
                  |
                  v
       Deduplicate + order versions
                  |
                  v
       Transactional UPSERT / tombstone
                  |
                  v
       Commit data + checkpoint
                  |
                  v
         Reconciliation checks
                  |
                  v
       Mark batch reconciled / publish

        Failure at any stage
                  |
                  v
          Resume / replay safely
```

**Nguyên tắc cốt lõi:** thiết kế để dữ liệu có thể được giao ít nhất một lần (at-least-once), nhưng việc áp dụng dữ liệu có tính lặp an toàn nhờ khóa ổn định, unique constraints, version checks và transaction boundaries. Không dựa vào giả định “mỗi message chỉ đến đúng một lần”.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt idempotency, retry safety, deduplication và reconciliation.
2. Giải thích vì sao “exactly once” xuyên qua nhiều hệ thống khó được bảo đảm chỉ bằng một transaction PostgreSQL.
3. Thiết kế batch key và record key ổn định qua nhiều lần chạy.
4. Phân biệt `batch_id`, `source_batch_key`, `source_record_id`, version và checkpoint.
5. Tổ chức raw landing, staging, target và quarantine tables.
6. Dùng unique constraints và `INSERT ... ON CONFLICT` làm lớp bảo vệ cuối.
7. Xử lý duplicate cùng payload và duplicate có payload khác nhau.
8. Bỏ qua stale events và cập nhật theo source version.
9. Dùng tombstone để xử lý delete events và ngăn dữ liệu cũ tái xuất hiện.
10. Tách full snapshot reconciliation khỏi incremental/CDC ingestion.
11. Thiết kế pipeline atomic hoặc chunked theo transaction.
12. Ghi checkpoint cùng transaction với dữ liệu mà nó đại diện.
13. Dùng `COPY FROM STDIN` để nạp dữ liệu lớn vào staging.
14. Validate dữ liệu trước khi cast và merge vào bảng nghiệp vụ.
15. Quản lý worker concurrency bằng row locks, leases và fencing.
16. Dùng `FOR UPDATE SKIP LOCKED` cho hàng đợi batch.
17. Đối soát counts, keys, versions, aggregates và checksums.
18. Phát hiện missing rows, extra rows và same-key/different-value conflicts.
19. Xử lý late-arriving events, out-of-order events và schema evolution.
20. Thiết kế export có snapshot ổn định và file publish có thể chạy lại.
21. Phân biệt transaction nội bộ database với side effects ở message broker/file/API.
22. Dùng outbox/idempotency keys cho những side effects cần giao tiếp với hệ thống khác.
23. Kiểm thử crash, replay, concurrent workers, rollback và commit outcome không rõ.
24. Xây runbook, metrics và quy trình sửa sai có thể kiểm toán.

## 3. Các khái niệm cần phân biệt

### 3.1. Idempotent operation

Một thao tác `f` được gọi là idempotent nếu áp dụng cùng một yêu cầu nhiều lần cho cùng trạng thái ban đầu vẫn cho cùng trạng thái cuối:

```text
f(f(S, x), x) = f(S, x)
```

Ví dụ, cập nhật trạng thái đơn hàng từ một event có ID cố định và version đã kiểm tra có thể idempotent. Cộng tiền vào số dư mỗi lần nhận message thì không idempotent nếu không ghi nhận message đã áp dụng.

### 3.2. Retry-safe

Một thao tác retry-safe có thể chạy lại sau một lỗi mà không gây side effect sai. Idempotency thường là nền tảng để retry-safe, nhưng còn cần xét các hệ thống bên ngoài, thời điểm commit và trạng thái kết quả.

### 3.3. Deduplication

Deduplication xác định các bản ghi hoặc sự kiện đại diện cùng một logical event/entity. Nó cần **identity key** đáng tin cậy. Hai rows có nội dung giống hệt nhau chưa chắc là cùng một sự kiện; ngược lại, cùng event ID với payload khác nhau là một xung đột cần điều tra.

### 3.4. Reconciliation

Reconciliation so sánh các quan sát độc lập để trả lời:

- Đã nhận đủ số records chưa?
- Có records bị từ chối hoặc duplicate không?
- Dữ liệu đích có cùng key/version/value với nguồn không?
- Có records thừa trong phạm vi đáng lẽ phải khớp không?
- Checkpoint có phản ánh đúng dữ liệu đã commit không?

Đối soát không chỉ là `COUNT(*)`; hai tập dữ liệu có cùng số rows nhưng vẫn có thể khác hoàn toàn.

### 3.5. At-least-once và exactly-once

- **At-most-once:** có thể bỏ mất message, nhưng không giao lặp theo cơ chế đó.
- **At-least-once:** message có thể được giao lại, nên consumer phải chịu được duplicate.
- **Exactly-once effect:** trạng thái nghiệp vụ cuối cùng có hiệu ứng như chỉ áp dụng một lần, dù transport có thể giao lặp.

Trong thực tế, thường xây **at-least-once delivery + idempotent sink + transactional checkpoints**. “Exactly once” giữa PostgreSQL, broker, file system và API bên ngoài cần một giao thức phối hợp cụ thể; không có một `COMMIT` đơn lẻ bao trùm mọi hệ thống.

## 4. Xác định identity trước khi viết SQL

Một pipeline cần ít nhất hai cấp identity.

| Identity | Phạm vi | Ví dụ | Mục đích |
| --- | --- | --- | --- |
| `source_system` | Hệ thống nguồn | `partner_a` | Phân biệt namespace |
| `source_batch_key` | Một batch nguồn | `daily-2026-11-14-001` | Nhận biết batch giao lại |
| `batch_id` | Một lần đăng ký batch trong DB | UUID | Khóa nội bộ và liên kết staging |
| `source_record_id` | Một logical record/event | `order-9381` | Deduplicate bản ghi |
| `source_version` | Phiên bản của record | `17` | Chống ghi đè dữ liệu mới bằng dữ liệu cũ |
| `source_event_id` | Một event cụ thể | UUID từ broker | Deduplicate delivery |
| `source_watermark` | Vị trí đã đọc từ nguồn | LSN/offset/cursor | Resume incremental extraction |

### 4.1. Không dùng số dòng file làm business key

`row_number = 42` chỉ là vị trí trong một file. Khi nguồn sắp xếp lại rows, cùng một đơn hàng có thể nằm ở dòng khác.

Row number hữu ích để truy vết lỗi import và bảo đảm cùng một file replay không thêm lặp raw rows, nhưng không thay thế `source_record_id`.

### 4.2. Khóa phải ổn định qua lần chạy

Một key nên được tạo từ định danh nghiệp vụ do nguồn cấp hoặc một mapping được quản lý. Không tạo key ngẫu nhiên mới mỗi lần retry.

### 4.3. Scope key phải rõ ràng

Nếu `order_id` chỉ duy nhất trong tenant, target key cần chứa tenant:

```text
(tenant_id, source_system, source_record_id)
```

Nếu ID duy nhất toàn hệ thống nguồn, có thể dùng `(source_system, source_record_id)`. Chọn đúng theo hợp đồng dữ liệu nguồn.

### 4.4. Batch key và record key giải quyết hai việc khác nhau

Batch key nhận biết **cả gói dữ liệu** đã được giao trước đó. Record key nhận biết **từng entity/event** trong các batch khác nhau. Cần cả hai nếu cùng record có thể xuất hiện trong nhiều incremental batches.

## 5. Kiến trúc dữ liệu cho lab

Chúng ta xây một pipeline nhập đơn hàng từ đối tác vào PostgreSQL.

Các lớp:

- `ingest.batches`: trạng thái, identity và checksum của batch.
- `ingest.raw_order_rows`: payload gốc, giữ để audit/replay.
- `ingest.stage_orders`: dữ liệu đã parse và validate.
- `app.orders`: bảng nghiệp vụ hiện tại.
- `ingest.rejected_rows`: bản ghi không hợp lệ và lý do.
- `ingest.checkpoints`: vị trí nguồn đã được lưu bền vững.

### 5.1. Tạo schemas

Chạy trong database lab:

```sql
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS app;
```

### 5.2. Bảng batch registry

```sql
CREATE TABLE ingest.batches (
    batch_id uuid PRIMARY KEY,
    source_system text NOT NULL,
    source_batch_key text NOT NULL,
    payload_sha256 text NOT NULL
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL
        CHECK (status IN (
            'received',
            'loading',
            'ready',
            'applying',
            'applied',
            'reconciled',
            'retryable',
            'failed'
        )),
    expected_rows bigint
        CHECK (expected_rows IS NULL OR expected_rows >= 0),
    received_rows bigint NOT NULL DEFAULT 0
        CHECK (received_rows >= 0),
    valid_rows bigint NOT NULL DEFAULT 0
        CHECK (valid_rows >= 0),
    rejected_rows bigint NOT NULL DEFAULT 0
        CHECK (rejected_rows >= 0),
    attempt_count integer NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    lease_owner text,
    lease_until timestamptz,
    source_watermark_start text,
    source_watermark_end text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    reconciled_at timestamptz,
    last_error text,
    UNIQUE (source_system, source_batch_key)
);
```

Unique constraint `(source_system, source_batch_key)` bảo vệ batch registration khi request đến lại hoặc hai workers cùng đăng ký.

`payload_sha256` dùng để phát hiện tình huống **cùng batch key nhưng nội dung khác**. Khi đó không được âm thầm coi đây là retry bình thường.

### 5.3. Raw landing table

```sql
CREATE TABLE ingest.raw_order_rows (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    source_row_no bigint NOT NULL
        CHECK (source_row_no > 0),
    raw_payload jsonb NOT NULL,
    payload_sha256 text NOT NULL
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, source_row_no)
);
```

Raw payload được giữ nguyên về mặt dữ liệu JSON đã parse. Nếu cần giữ **byte-for-byte file gốc**, lưu file gốc ở object storage/content-addressed storage và giữ URI + checksum trong batch registry; `jsonb` không bảo toàn whitespace, key order hay định dạng CSV gốc.

### 5.4. Typed staging table

```sql
CREATE TABLE ingest.stage_orders (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    source_row_no bigint NOT NULL,
    tenant_id bigint,
    source_record_id text,
    source_version bigint,
    customer_code text,
    status text,
    amount numeric(12,2),
    source_updated_at timestamptz,
    payload_sha256 text,
    validation_error text,
    PRIMARY KEY (batch_id, source_row_no)
);
```

Staging cho phép tách parse/validation khỏi ghi vào bảng nghiệp vụ. Những rows lỗi được giữ cùng batch và row number để truy vết.

### 5.5. Bảng quarantine

```sql
CREATE TABLE ingest.rejected_rows (
    batch_id uuid NOT NULL,
    source_row_no bigint NOT NULL,
    raw_payload jsonb NOT NULL,
    error_code text NOT NULL,
    error_detail text,
    rejected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, source_row_no)
);
```

Không loại bỏ row lỗi một cách âm thầm. Quarantine giữ bằng chứng, nguyên nhân và khả năng sửa/replay.

### 5.6. Bảng đích

```sql
CREATE TABLE app.orders (
    tenant_id bigint NOT NULL,
    source_system text NOT NULL,
    source_record_id text NOT NULL,
    source_version bigint NOT NULL,
    payload_sha256 text NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL,
    amount numeric(12,2) NOT NULL,
    source_updated_at timestamptz,
    deleted_at timestamptz,
    last_batch_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        tenant_id,
        source_system,
        source_record_id
    )
);
```

Target giữ source version và payload hash để phân biệt event mới, event cũ và xung đột cùng version. `deleted_at` là tombstone mềm trong ví dụ.

### 5.7. Bảng checkpoint cho nguồn có offset số

§§§sql
CREATE TABLE ingest.checkpoints (
    source_system text NOT NULL,
    stream_name text NOT NULL,
    partition_id integer NOT NULL,
    last_committed_offset bigint NOT NULL DEFAULT -1,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_system, stream_name, partition_id)
);
§§§

Ví dụ này phù hợp nguồn có offset số như một số message partitions. Với API cursor opaque hoặc CDC token không phải integer, lưu đúng kiểu/token do nguồn cấp và định nghĩa comparator/checkpoint semantics theo contract; không ép mọi watermark thành bigint.

## 6. Đăng ký batch idempotently

Ứng dụng tạo `batch_id` một lần cho batch mới và giữ lại nó khi retry. `source_batch_key` do nguồn cấp hoặc do extractor tạo theo quy tắc ổn định.

### 6.1. Đăng ký lần đầu

```sql
INSERT INTO ingest.batches (
    batch_id,
    source_system,
    source_batch_key,
    payload_sha256,
    status,
    expected_rows,
    source_watermark_start,
    source_watermark_end
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    'partner_a',
    'daily-2026-11-14-001',
    repeat('a', 64),
    'received',
    1000,
    'offset:5000',
    'offset:5999'
)
ON CONFLICT (source_system, source_batch_key)
DO NOTHING
RETURNING batch_id;
```

UUID và checksum trên chỉ là giá trị minh họa cho lab. Trong ứng dụng thật, checksum phải được tính từ một representation canonical của batch.

### 6.2. Retry cùng batch key

Nếu `INSERT ... RETURNING` không trả row, batch key đã tồn tại. Đọc batch hiện có:

```sql
SELECT
    batch_id,
    payload_sha256,
    status,
    expected_rows,
    received_rows
FROM ingest.batches
WHERE source_system = 'partner_a'
  AND source_batch_key = 'daily-2026-11-14-001'
FOR UPDATE;
```

So sánh `payload_sha256`:

- Cùng checksum: cùng batch content; tiếp tục/resume hoặc trả kết quả cũ nếu đã hoàn tất.
- Khác checksum: cùng identity nhưng content khác; đánh dấu conflict và điều tra nguồn.
- Không tạo một batch mới chỉ vì request retry.

### 6.3. Concurrency

Unique constraint là lớp bảo vệ cuối khi hai requests đăng ký cùng key đồng thời. Một request có thể chờ request kia commit rồi nhận conflict. Sau đó đọc record hiện hữu và so checksum.

### 6.4. Vì sao không chỉ dùng file name?

Tên file `orders.csv` thường được tái sử dụng mỗi ngày. Batch key nên gồm source identity và sequence/snapshot/date/version phù hợp, không chỉ tên file chung.

## 7. Tính checksum ổn định

Checksum giúp nhận diện cùng nội dung hoặc phát hiện thay đổi. Nhưng hai hệ thống phải hash **cùng một representation**.

### 7.1. Những gì cần canonicalize

- Encoding và Unicode normalization policy.
- Thứ tự records nếu batch order có ý nghĩa hay không.
- Tên và thứ tự fields.
- `NULL` khác empty string.
- Timestamp timezone/precision.
- Decimal scale/rounding.
- JSON number/string distinction.
- Line endings và CSV quoting nếu hash file bytes.
- Các trường metadata không thuộc business payload.

### 7.2. Hash file bytes và hash logical records là hai thứ khác

Hash nguyên file giúp xác định file byte-for-byte giống nhau. Hash logical records giúp so sánh dữ liệu sau parse/normalize. Cần ghi rõ loại checksum đang dùng.

### 7.3. Không hash chuỗi nối mơ hồ

Ví dụ nối `('ab','c')` và `('a','bc')` đều có thể thành `abc` nếu không có delimiter/length framing. Dùng serialization canonical có schema, encoding, field delimiters/length prefixes rõ.

### 7.4. SHA-256

Ứng dụng có thể tính SHA-256 trước khi upload. Nếu dùng PostgreSQL `pgcrypto`, có thể tính trong DB:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SELECT encode(
    digest(convert_to('canonical payload', 'UTF8'), 'sha256'),
    'hex'
);
```

Không cần cài extension nếu application/object store đã tạo checksum đáng tin. SHA-256 ở đây dùng kiểm tra content identity/integrity, không thay authentication hoặc chữ ký nguồn.

### 7.5. Hash không thay identity

Hai đơn hàng khác nhau có thể có payload giống hệt nhau. Hash giống nhau không có nghĩa chúng là cùng một order. Identity phải dựa trên source keys.

## 8. Nạp file lớn vào staging bằng COPY

Với dữ liệu lớn, `COPY FROM STDIN` thường hiệu quả hơn hàng nghìn câu `INSERT` riêng lẻ.

### 8.1. Temporary landing table

```sql
CREATE TEMP TABLE incoming_order_rows (
    source_row_no bigint,
    tenant_id bigint,
    source_record_id text,
    source_version bigint,
    customer_code text,
    status text,
    amount numeric(12,2),
    source_updated_at timestamptz,
    payload_sha256 text
) ON COMMIT DROP;
```

### 8.2. COPY từ client

```sql
COPY incoming_order_rows (
    source_row_no,
    tenant_id,
    source_record_id,
    source_version,
    customer_code,
    status,
    amount,
    source_updated_at,
    payload_sha256
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

Trong `psql`, `COPY ... FROM STDIN` dùng data stream do client gửi. Trong Java pgJDBC, có thể dùng `CopyManager` từ package `org.postgresql.copy` để truyền stream. Không nhầm với `COPY FROM '/path'`, vốn đọc file trên filesystem **server** và cần quyền/đường dẫn phù hợp.

### 8.3. Ghi staging có batch identity

Sau khi COPY vào temp table:

```sql
INSERT INTO ingest.stage_orders (
    batch_id,
    source_row_no,
    tenant_id,
    source_record_id,
    source_version,
    customer_code,
    status,
    amount,
    source_updated_at,
    payload_sha256
)
SELECT
    '11111111-1111-4111-8111-111111111111'::uuid,
    source_row_no,
    tenant_id,
    source_record_id,
    source_version,
    customer_code,
    status,
    amount,
    source_updated_at,
    payload_sha256
FROM pg_temp.incoming_order_rows
ON CONFLICT (batch_id, source_row_no)
DO NOTHING;
```

`ON CONFLICT DO NOTHING` giúp replay cùng batch/row number không tạo duplicate staging row. Nhưng trước khi bỏ qua conflict, phải xác minh row hiện có cùng payload hash. Nếu row number giống mà payload khác, đây là batch mutation/corruption, cần fail hoặc quarantine.

### 8.4. Không COPY trực tiếp vào target khi cần validate/reconcile

COPY trực tiếp target làm khó:

- Quarantine từng row lỗi.
- Kiểm tra duplicate keys.
- So source versions.
- Đối chiếu expected rows.
- Phân biệt new/update/unchanged/stale.
- Replay từng phần.

Staging tạo ranh giới rõ giữa dữ liệu chưa tin cậy và bảng nghiệp vụ.

## 9. Validate trước khi cast và merge

Dữ liệu ngoài hệ thống có thể sai định dạng, thiếu field, status lạ hoặc amount không hợp lệ.

### 9.1. Các lớp validation

1. **Structural:** record có đủ fields bắt buộc không?
2. **Type:** version là integer, amount là decimal, timestamp parse được?
3. **Domain:** status có thuộc enum cho phép, amount không âm?
4. **Referential:** tenant/customer/product có tồn tại và thuộc đúng scope?
5. **Business:** transition status có hợp lệ không?
6. **Identity:** record ID có ổn định, version có hợp lệ?
7. **Consistency:** cùng key/version có payload mâu thuẫn không?

### 9.2. Không cast raw text mù quáng

Nếu `amount_text` chứa `12,34` theo locale hoặc `not-a-number`, một cast trực tiếp có thể làm cả batch fail. Có thể parse trong application/validation layer hoặc dùng safe parsing routine có kiểm soát, ghi lỗi theo row.

### 9.3. Ví dụ quarantine rows đã được đánh dấu lỗi

```sql
INSERT INTO ingest.rejected_rows (
    batch_id,
    source_row_no,
    raw_payload,
    error_code,
    error_detail
)
SELECT
    r.batch_id,
    r.source_row_no,
    r.raw_payload,
    'INVALID_ORDER',
    s.validation_error
FROM ingest.stage_orders AS s
JOIN ingest.raw_order_rows AS r
  ON r.batch_id = s.batch_id
 AND r.source_row_no = s.source_row_no
WHERE s.batch_id =
    '11111111-1111-4111-8111-111111111111'
  AND s.validation_error IS NOT NULL
ON CONFLICT (batch_id, source_row_no)
DO UPDATE SET
    error_code = EXCLUDED.error_code,
    error_detail = EXCLUDED.error_detail;
```

Quarantine phải giữ cùng batch/row identity để một lần replay không tạo nhiều lỗi trùng.

### 9.4. Từ chối hay partial acceptance?

Định nghĩa chính sách trước:

- **Atomic batch:** một row lỗi làm toàn batch không được áp dụng.
- **Partial acceptance:** rows hợp lệ được áp dụng, rows lỗi được quarantine; batch chỉ hoàn tất khi reconciliation ghi rõ accepted/rejected counts.

Không để hệ thống tự chọn semantics theo cách code vô tình bỏ qua exceptions.

## 10. Deduplicate trong một batch

Một file có thể chứa nhiều rows cho cùng `source_record_id`.

### 10.1. Cùng key, cùng version, cùng payload

Đây có thể là duplicate delivery. Giữ một row đại diện và đếm số duplicate.

### 10.2. Cùng key, cùng version, payload khác nhau

Đây là conflict. Không tùy tiện chọn “row cuối cùng” theo thứ tự file, trừ khi hợp đồng nguồn xác định rõ thứ tự đó là authoritative.

Tìm conflict:

```sql
SELECT
    tenant_id,
    source_record_id,
    source_version,
    COUNT(*) AS rows_seen,
    COUNT(DISTINCT payload_sha256) AS distinct_payloads
FROM ingest.stage_orders
WHERE batch_id =
    '11111111-1111-4111-8111-111111111111'
  AND validation_error IS NULL
GROUP BY tenant_id, source_record_id, source_version
HAVING COUNT(DISTINCT payload_sha256) > 1;
```

### 10.3. Chọn phiên bản mới nhất

Nếu source version có thứ tự tăng đơn điệu theo record:

```sql
SELECT *
FROM (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY tenant_id, source_record_id
            ORDER BY source_version DESC, source_row_no DESC
        ) AS rn
    FROM ingest.stage_orders AS s
    WHERE batch_id =
        '11111111-1111-4111-8111-111111111111'
      AND validation_error IS NULL
) AS ranked
WHERE rn = 1;
```

`source_row_no DESC` chỉ là tie-breaker kỹ thuật sau khi đã xác nhận các rows cùng key/version có payload giống nhau. Không dùng nó để giải quyết conflict dữ liệu thật.

### 10.4. Version không phải timestamp nhận ở consumer

Một event cũ có thể đến muộn sau event mới. `received_at` ở hệ thống đích không thể quyết định record nào mới hơn. Dùng source sequence/version hoặc một ordering contract được định nghĩa rõ.

## 11. UPSERT có điều kiện theo source version

Unique constraint của target bảo đảm chỉ có một current row cho mỗi business key:

```text
(tenant_id, source_system, source_record_id)
```

### 11.1. Kiểm tra cùng version nhưng payload khác

Trước khi merge, phát hiện source conflict với target:

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version,
    t.payload_sha256 AS target_hash,
    s.payload_sha256 AS incoming_hash
FROM ingest.stage_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = 'partner_a'
 AND t.source_record_id = s.source_record_id
WHERE s.batch_id =
    '11111111-1111-4111-8111-111111111111'
  AND s.validation_error IS NULL
  AND s.source_version = t.source_version
  AND s.payload_sha256 <> t.payload_sha256;
```

Nếu có rows, cần xử lý theo conflict policy; không âm thầm update hoặc coi là duplicate.

### 11.2. Merge bản mới nhất của từng key

Sau khi validate và loại conflict:

```sql
WITH ranked AS (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY s.tenant_id, s.source_record_id
            ORDER BY s.source_version DESC, s.source_row_no DESC
        ) AS rn
    FROM ingest.stage_orders AS s
    WHERE s.batch_id =
        '11111111-1111-4111-8111-111111111111'
      AND s.validation_error IS NULL
),
latest AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
INSERT INTO app.orders AS current_order (
    tenant_id,
    source_system,
    source_record_id,
    source_version,
    payload_sha256,
    customer_code,
    status,
    amount,
    source_updated_at,
    last_batch_id
)
SELECT
    l.tenant_id,
    'partner_a',
    l.source_record_id,
    l.source_version,
    l.payload_sha256,
    l.customer_code,
    l.status,
    l.amount,
    l.source_updated_at,
    l.batch_id
FROM latest AS l
ON CONFLICT (
    tenant_id,
    source_system,
    source_record_id
)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    payload_sha256 = EXCLUDED.payload_sha256,
    customer_code = EXCLUDED.customer_code,
    status = EXCLUDED.status,
    amount = EXCLUDED.amount,
    source_updated_at = EXCLUDED.source_updated_at,
    deleted_at = NULL,
    last_batch_id = EXCLUDED.last_batch_id,
    updated_at = clock_timestamp()
WHERE EXCLUDED.source_version > current_order.source_version;
```

### 11.3. Tác dụng của điều kiện version

- Target chưa có key: insert.
- Incoming version lớn hơn: update.
- Incoming version nhỏ hơn: bỏ qua stale event.
- Incoming version bằng và cùng payload: unchanged/no-op.
- Incoming version bằng nhưng payload khác: phải bị phát hiện như conflict trước merge.

### 11.4. Không dựa vào `xmax = 0` để phân loại nghiệp vụ

Một số ví dụ dùng system column `xmax` để đoán INSERT hay UPDATE trong `ON CONFLICT`. Đây không phải hợp đồng ứng dụng ổn định để làm accounting. Nếu cần số lượng inserted/updated chính xác, thiết kế một change ledger hoặc quy trình phân loại/ghi nhận rõ ràng.

### 11.5. Concurrent UPSERT vẫn cần unique constraint

Hai workers có thể cùng thấy key chưa tồn tại. Unique constraint và `ON CONFLICT` xử lý cạnh tranh ở database. Chỉ `SELECT` kiểm tra trước rồi `INSERT` không đủ an toàn trước race.

## 12. Delete events: dùng tombstone để ngăn dữ liệu cũ sống lại

Giả sử nguồn phát:

- Version 8: order đang `PAID`.
- Version 9: order bị xóa.
- Version 7: event cũ đến muộn sau đó.

Nếu consumer physically DELETE row ở version 9, event version 7 có thể INSERT lại order và làm record “sống lại”.

### 12.1. Tombstone

Thay vì xóa ngay, lưu:

- Business key.
- Delete version.
- `deleted_at`.
- Source event identity/hash.

Trong target schema đã có `deleted_at`; tombstone giữ version 9 để chặn event cũ.

### 12.2. Apply delete như một versioned upsert

Có thể dùng một bảng event/tombstone riêng hoặc một câu lệnh `INSERT ... ON CONFLICT DO UPDATE` với action `DELETE`, chỉ update nếu incoming version lớn hơn. Phần ví dụ rút gọn:

```sql
UPDATE app.orders
SET
    source_version = 9,
    deleted_at = clock_timestamp(),
    last_batch_id =
        '11111111-1111-4111-8111-111111111111',
    updated_at = clock_timestamp()
WHERE tenant_id = 10
  AND source_system = 'partner_a'
  AND source_record_id = 'order-9381'
  AND source_version < 9;
```

Trong production, delete event đến trước insert event cũng cần được lưu như tombstone key ngay cả khi target row chưa tồn tại; nếu không, event insert cũ có thể tạo lại row. Một bảng tombstone độc lập hoặc target record có trạng thái deleted đáp ứng trường hợp đó.

### 12.3. Không xóa tombstone quá sớm

Giữ tombstones ít nhất qua khoảng thời gian tối đa mà nguồn có thể replay/đưa event trễ. Nếu nguồn có retention/replay window 30 ngày, việc xóa tombstone sau 1 ngày có thể cho phép event cũ tái xuất hiện.

### 12.4. Soft delete và API reads

Các queries nghiệp vụ phải lọc `deleted_at IS NULL` theo policy. Nhưng reconciliation/audit cần nhìn thấy tombstones để biết key đã được xóa, không phải chưa từng tồn tại.

## 13. Ghi nhận batch progress và checkpoint

Một checkpoint là vị trí trong nguồn mà pipeline tuyên bố đã xử lý bền vững.

Ví dụ:

- Kafka partition + offset.
- CDC log sequence number (LSN).
- API page cursor.
- Source updated timestamp + unique tie-breaker.
- File batch key + row number.

### 13.1. Không advance checkpoint trước khi data durable

Trình tự nguy hiểm:

1. Ghi checkpoint đến offset 9000.
2. Crash trước khi ghi target rows tương ứng.
3. Restart từ 9001.
4. Events 8001–9000 bị bỏ mất.

### 13.2. Transactional checkpoint với data

Nếu target data và checkpoint cùng PostgreSQL database, ghi chúng trong **cùng transaction**:

```sql
BEGIN;

-- INSERT/UPSERT target rows cho chunk tương ứng.

UPDATE ingest.checkpoints
SET last_committed_offset = 9000,
    updated_at = clock_timestamp()
WHERE source_system = 'partner_a'
  AND stream_name = 'orders'
  AND partition_id = 0;

COMMIT;
```

Nếu transaction rollback, cả data và checkpoint rollback. Nếu commit, cả hai cùng durable theo database transaction semantics. Bảng `ingest.checkpoints` là bảng cần tạo theo source/stream/partition contract của ứng dụng.

### 13.3. Raw landing và checkpoint có thể có hai giai đoạn

Một thiết kế tốt có thể:

1. Ghi raw events bền vững vào PostgreSQL.
2. Commit raw landing.
3. Acknowledge broker/advance source offset.
4. Apply raw events vào target theo batch có thể replay.

Khi đó checkpoint nguồn có nghĩa **đã lưu raw events bền vững**, không phải đã merge vào target. Cần tách hai watermark để vận hành không hiểu nhầm.

### 13.4. Broker offset ở hệ thống ngoài DB

Nếu broker offset commit không nằm cùng transaction PostgreSQL, không thể giả định một transaction bao trùm cả hai. Chọn at-least-once delivery: persist event với unique event ID, commit DB, sau đó ack; nếu crash giữa hai bước, broker giao lại và unique constraint/dedup làm lần giao lại an toàn.

### 13.5. Watermark dạng timestamp cần tie-breaker

`updated_at > last_timestamp` có thể bỏ sót records cùng timestamp hoặc records cập nhật muộn. Dùng composite cursor như `(updated_at, source_record_id)` với thứ tự ổn định, hoặc CDC sequence có ordering rõ ràng.

### 13.6. Watermark không phải thời gian server nhận

Đối với CDC, lưu source LSN/offset. Với API, lưu cursor do nguồn cấp. Không tự thay bằng `clock_timestamp()` ở consumer rồi coi đó là vị trí nguồn.

## 14. Batch atomic hay chunked?

Hai chiến lược phổ biến có trade-off khác nhau.

| Chiến lược | Cách chạy | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Atomic batch | Toàn batch trong một transaction | Dễ rollback, target không ở trạng thái nửa batch | Transaction/WAL/locks lớn |
| Chunked | Mỗi chunk commit riêng, checkpoint theo chunk | Resume nhanh, transaction ngắn | Target có trạng thái partial giữa các chunks |
| Raw-first + apply later | Raw durable trước, merge thành nhiều chunks | Tách transport khỏi business processing | Cần state machine/reconciliation rõ |
| Snapshot generation | Nạp snapshot version mới rồi switch | Dễ giữ snapshot nhất quán | Cần storage và cơ chế publish |

### 14.1. Atomic batch

Phù hợp batch nhỏ/vừa, yêu cầu tất cả hoặc không gì cả. Đặt batch state, merge và checkpoint trong cùng transaction.

### 14.2. Chunked batch

Mỗi chunk cần identity ổn định, ví dụ `(batch_id, chunk_no)`, và checkpoint riêng. Retry một chunk không tạo duplicate hoặc skip dữ liệu.

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL,
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applied')),
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

Data của chunk và trạng thái `applied` nên commit trong cùng transaction.

### 14.3. Đừng đánh dấu batch hoàn tất trước chunk cuối

Batch status `applied` chỉ được đặt khi mọi chunks bắt buộc đã applied và counts được kiểm tra. Nếu một chunk bị lỗi/quarantine, trạng thái tổng phải thể hiện điều đó.

### 14.4. Định nghĩa visibility cho downstream

Nếu consumers khác đọc target giữa lúc chunked batch đang chạy, họ có thể thấy snapshot partial. Có thể dùng batch generation/visibility flag, staging target rồi switch, hoặc đảm bảo downstream chỉ đọc generation `published`.

## 15. Quản lý nhiều workers an toàn

Khi nhiều workers xử lý batch, cần tránh hai worker apply cùng batch đồng thời hoặc worker cũ tiếp tục ghi sau khi lease đã chuyển chủ.

### 15.1. Claim một batch bằng SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

Đây là ví dụ trong một transaction ngắn. Commit claim rồi worker mới thực hiện phần xử lý.

### 15.2. Vì sao SKIP LOCKED?

Nếu worker A đang khóa batch row 1, worker B bỏ qua row đó và nhận batch khác thay vì chờ. Phù hợp queue workers, nhưng không bảo đảm thứ tự FIFO tuyệt đối khi có locks/retries.

### 15.3. Lease không phải khóa tuyệt đối

Worker A có thể bị pause lâu, lease hết hạn, worker B claim lại; sau đó A thức dậy và tiếp tục. Cần fencing token/ownership check trong transaction apply, heartbeat và/hoặc transaction-level advisory lock.

### 15.4. Fencing token

Một số hệ thống tăng `lease_generation` mỗi lần claim. Worker chỉ được commit kết quả nếu generation vẫn là token của nó. Worker cũ không thể ghi sau khi worker mới đã claim generation cao hơn.

Ví dụ ý tưởng:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

Để dùng câu lệnh này, thêm cột `lease_generation bigint NOT NULL DEFAULT 0` vào schema batch. Trong transaction apply, khóa row batch và xác minh generation trước khi ghi target.

### 15.5. Advisory transaction lock

Có thể serialize theo source/batch bằng `pg_advisory_xact_lock(...)` nếu quy ước lock key nhất quán. Advisory lock hỗ trợ phối hợp, nhưng unique constraints và idempotent writes vẫn phải bảo vệ dữ liệu.

### 15.6. Đừng giữ transaction mở trong suốt thời gian tải file từ mạng

Tải file, gọi API, giải nén và validate tốn thời gian. Làm chúng trước hoặc ở ngoài transaction apply. Chỉ mở transaction DB đủ ngắn để ghi chunk/merge/checkpoint.

## 16. Reconciliation: đối soát từ số lượng đến nội dung

Đối soát phải có các tầng kiểm tra.

### 16.1. Count reconciliation

Với một batch:

- `expected_rows`: số rows nguồn tuyên bố.
- `received_rows`: số raw rows đã nhận.
- `valid_rows`: số rows vượt validation.
- `rejected_rows`: số rows bị quarantine.
- `duplicate_rows`: số deliveries/rows lặp.
- `applied_new_rows`: records mới.
- `applied_update_rows`: records cập nhật.
- `unchanged_rows`: cùng version/cùng payload.
- `stale_rows`: event cũ bị bỏ qua.

Định nghĩa các nhóm **không chồng lấn** hoặc ghi rõ nhóm nào là subset. Nếu `received = valid + rejected`, duplicates có thể là một thuộc tính của valid rows chứ không tự cộng thêm lần nữa.

### 16.2. Ví dụ accounting rõ ràng

Một batch có 1.000 source rows:

| Phân loại cuối cùng (mutually exclusive) | Số lượng |
| --- | ---: |
| New records applied | 700 |
| Existing records updated | 150 |
| Unchanged duplicates | 80 |
| Stale events ignored | 30 |
| Rejected | 40 |
| **Total received** | **1.000** |

Nếu source contract tuyên bố 1.000 rows, `received_rows` phải khớp. `valid_rows` theo ví dụ này là 960 nếu stale/unchanged vẫn hợp lệ; rejected là 40. Không lấy `700 + 150 + 80 + 30 + 40` rồi cộng duplicates lần nữa.

### 16.3. Reconcile raw rows với expected

```sql
SELECT
    b.batch_id,
    b.expected_rows,
    COUNT(r.source_row_no) AS actual_raw_rows,
    b.received_rows
FROM ingest.batches AS b
LEFT JOIN ingest.raw_order_rows AS r
  ON r.batch_id = b.batch_id
WHERE b.batch_id =
    '11111111-1111-4111-8111-111111111111'
GROUP BY b.batch_id, b.expected_rows, b.received_rows;
```

Nếu batch bị chunked, kiểm tra số row numbers unique và dải row numbers/partition completeness theo source contract; count bằng nhau chưa chứng minh không bị thay row.

### 16.4. Missing và extra keys bằng anti-join

Nếu có bảng snapshot nguồn đã chuẩn hóa `ingest.source_snapshot_orders`, so sánh:

```sql
-- Có ở nguồn nhưng thiếu ở target.
SELECT s.tenant_id, s.source_record_id
FROM ingest.source_snapshot_orders AS s
LEFT JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND t.source_record_id IS NULL;

-- Có ở target trong scope nhưng không còn ở snapshot nguồn.
SELECT t.tenant_id, t.source_record_id
FROM app.orders AS t
LEFT JOIN ingest.source_snapshot_orders AS s
  ON s.tenant_id = t.tenant_id
 AND s.source_system = t.source_system
 AND s.source_record_id = t.source_record_id
 AND s.snapshot_id = $1
WHERE t.source_system = $2
  AND t.tenant_id = $3
  AND t.deleted_at IS NULL
  AND s.source_record_id IS NULL;
```

Câu thứ hai chỉ có ý nghĩa nếu snapshot nguồn **đầy đủ, đã hoàn tất và đúng cùng scope**. Không xóa records dựa trên một snapshot partial.

### 16.5. So versions và payload hashes

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version AS source_version,
    t.source_version AS target_version,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM ingest.source_snapshot_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND (
      s.source_version <> t.source_version
      OR s.payload_sha256 <> t.payload_sha256
  );
```

Điều tra từng category: target stale, source stale, same-version conflict, normalization mismatch hoặc lỗi apply.

## 17. Checksum reconciliation cho dữ liệu lớn

Count và key checks chưa đủ để chứng minh payload giống nhau. Checksum có thể phát hiện sai khác trên tập records.

### 17.1. Canonical row representation

Ví dụ mỗi record được biểu diễn theo thứ tự field cố định:

```text
tenant_id | source_system | source_record_id |
source_version | status | amount | deleted_at
```

Cần quy ước chính xác cách biểu diễn NULL, numeric scale, timestamp timezone và Unicode.

### 17.2. Checksum theo partition

Với `pgcrypto`:

```sql
SELECT
    tenant_id,
    COUNT(*) AS row_count,
    encode(
        digest(
            convert_to(
                string_agg(
                    concat_ws(
                        E'\x1f',
                        source_record_id,
                        source_version::text,
                        payload_sha256
                    ),
                    E'\n'
                    ORDER BY source_record_id
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    ) AS partition_sha256
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id
ORDER BY tenant_id;
```

### 17.3. Giới hạn của ví dụ string_agg

Một partition rất lớn có thể tạo chuỗi tạm rất lớn trong memory. Trong production, chia theo tenant/key range/date partitions, hoặc dùng Merkle tree/hierarchical checksums với canonical leaf hashing.

### 17.4. Không cộng các hash như số học để coi là checksum chắc chắn

`SUM(hash_as_number)` hoặc XOR đơn giản có thể có collision và không bảo toàn thứ tự/identity như mong đợi. Dùng thuật toán/checksum design được xác định rõ, có thể tái tạo từ cả hai phía.

### 17.5. Hash không chứng minh nguồn là đáng tin

Checksum chỉ chứng minh nội dung khớp với digest đã tính. Nếu nguồn bị giả mạo, cần authenticated transport, signatures hoặc trusted source controls.

## 18. Đối soát tổng hợp nghiệp vụ

Ngoài row count/hash, so các totals có ý nghĩa:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS amount_total,
    MIN(source_updated_at) AS first_seen,
    MAX(source_updated_at) AS last_seen
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Nếu nguồn cung cấp summary theo tenant/status, so với các totals tương ứng.

### 18.1. Aggregate match không chứng minh record-level match

Một order thiếu 100 và một order thừa 100 có thể làm tổng tiền vẫn bằng nhau. Vì vậy aggregate là **một lớp** reconciliation, không thay key-level comparison.

### 18.2. Currency và precision

Không cộng số tiền của nhiều currencies nếu không có currency conversion contract. Dùng `numeric`, không dùng floating point cho accounting values; quy định scale và rounding.

### 18.3. Time window

So sánh cùng snapshot/time window. Nếu source tiếp tục thay đổi trong khi target đang ingest, aggregate có thể khác hợp lệ vì hai bên không cùng thời điểm.

## 19. Full snapshot và incremental/CDC không giống nhau

### 19.1. Full snapshot

Nguồn tuyên bố: “Đây là toàn bộ orders thuộc tenant 10 tại snapshot S”.

Có thể so missing/extra keys và đánh dấu deleted nếu:

- Snapshot có marker hoàn tất.
- Tất cả pages/parts đã nhận.
- Counts/checksums hợp lệ.
- Đúng tenant/source scope.
- Không có batch khác đang cập nhật cùng scope mà chưa được serialize.

### 19.2. Incremental feed

Nguồn chỉ gửi records mới/thay đổi từ watermark. Một record không xuất hiện trong batch incremental **không có nghĩa đã bị xóa**.

### 19.3. CDC

CDC phát các events thay đổi theo log sequence. Cần giữ source offset/LSN, transaction ordering và delete events. Không suy delete từ việc một key vắng mặt trong một chunk.

### 19.4. Full snapshot generation

Một cách quản lý visibility:

1. Tạo `snapshot_id`.
2. Nạp tất cả rows vào generation mới.
3. Đối soát expected count/checksum.
4. Chỉ khi đầy đủ mới đánh dấu generation `published`.
5. Downstream đọc generation hiện hành.
6. Dọn generation cũ theo retention policy.

Điều này tránh downstream đọc snapshot partial trong khi import đang chạy.

### 19.5. Không xóa theo snapshot bị thiếu page

Nếu page 4/10 tải lỗi nhưng pipeline vẫn đánh dấu các records không xuất hiện là deleted, có thể xóa hàng loạt dữ liệu hợp lệ. Full snapshot phải có completion manifest và reconciliation trước delete phase.

## 20. Late-arriving và out-of-order events

Một event version 12 có thể đến trước version 11. Khi version 11 đến sau, nó không được ghi đè version 12.

### 20.1. Version gate

Điều kiện:

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

giữ target ở phiên bản cao hơn.

### 20.2. Version phải có semantics

Nếu source version chỉ reset mỗi ngày hoặc mỗi partition, không thể so sánh toàn cục mà không có thêm epoch/partition identity. Xác định rõ:

- Version tăng theo record?
- Offset tăng theo partition?
- Timestamp có tie-breaker?
- Source có thể replay historical corrections?
- Delete có version như update không?

### 20.3. Same version, different payload

Không chọn winner ngẫu nhiên. Ghi conflict, quarantine và yêu cầu source contract/owner giải quyết.

### 20.4. Late corrections

Một correction hợp lệ có thể mang business effective date cũ nhưng event version mới. Không dùng business date thay event ordering. Lưu cả `source_version` và `source_updated_at`/effective time nếu cần.

## 21. Xử lý lỗi một phần và poison records

Một row lỗi không nhất thiết làm hỏng mọi rows khác, nhưng policy phải rõ.

### 21.1. Atomic batch

Nếu batch là một đơn vị nghiệp vụ bất khả phân, bất kỳ validation/merge error nào rollback toàn batch. Sau khi nguồn sửa file, tạo batch key mới hoặc version mới theo contract; không tái sử dụng cùng key với content khác mà không ghi nhận.

### 21.2. Partial acceptance

Nếu chấp nhận partial rows:

- Ghi mọi row vào raw.
- Validation status rõ ràng.
- Lỗi vào quarantine.
- Chỉ valid rows được merge.
- Counts phải cộng đúng.
- Batch không được `reconciled` cho đến khi rejected rows được chấp nhận theo policy hoặc được xử lý.

### 21.3. Poison message

Một message liên tục làm consumer fail có thể chặn partition/queue. Sau số lần retry có giới hạn, chuyển vào dead-letter/quarantine store, ghi reason và giữ original payload. Đừng âm thầm drop message.

### 21.4. Không dùng `WHEN OTHERS THEN NULL`

Bắt mọi exception rồi tiếp tục có thể làm batch báo thành công dù một số rows chưa được apply. Nếu bắt lỗi để partial process, phải ghi lỗi, phân loại, và đảm bảo transaction/savepoint semantics rõ.

### 21.5. Savepoint theo row có chi phí

Savepoint giúp rollback một phần transaction, nhưng tạo overhead và không thay validation. Với file lớn, validate set-based trước rồi merge valid rows thường hiệu quả hơn vòng lặp một savepoint cho mỗi row.

## 22. Checkpoint theo chunk và khả năng resume

Với batch rất lớn, chia thành chunks có thứ tự ổn định.

### 22.1. Chunk identity

Ví dụ:

`(batch_id, chunk_no)` hoặc `(source_partition, first_offset, last_offset)`.

Cùng một chunk phải có cùng phạm vi nguồn mỗi lần retry.

### 22.2. Chunk ledger

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applying', 'applied', 'failed')),
    rows_received bigint NOT NULL DEFAULT 0,
    rows_applied bigint NOT NULL DEFAULT 0,
    payload_sha256 text,
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

### 22.3. Atomic chunk commit

Trong một transaction:

1. Khóa chunk row.
2. Kiểm tra checksum và status.
3. Merge target rows idempotently.
4. Cập nhật chunk `applied`.
5. Cập nhật checkpoint tương ứng.
6. Commit.

Nếu process crash trước commit, cả merge và progress update rollback. Nếu crash sau commit nhưng trước khi worker nhận phản hồi, lần chạy lại thấy chunk `applied` và không áp dụng lại sai.

### 22.4. Không chỉ dựa row number liên tục

Nếu source pages có gaps hoặc opaque cursor, dùng source cursor/offset do nguồn cấp. `last_row_no` chỉ phù hợp với file/batch có thứ tự và row numbering ổn định.

### 22.5. Batch completion

Batch chuyển `applied` khi mọi chunks cần thiết đã applied hoặc được phân loại rejected theo partial-acceptance policy. Sau đó chạy reconciliation và chỉ chuyển `reconciled` khi checks pass.

## 23. Quản lý nhiều workers an toàn

Khi nhiều workers xử lý batch, cần tránh hai worker apply cùng batch đồng thời hoặc worker cũ tiếp tục ghi sau khi lease đã chuyển chủ.

### 23.1. Claim một batch bằng SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

Đây là ví dụ trong một transaction ngắn. Commit claim rồi worker mới thực hiện phần xử lý.

### 23.2. Vì sao SKIP LOCKED?

Nếu worker A đang khóa batch row 1, worker B bỏ qua row đó và nhận batch khác thay vì chờ. Phù hợp queue workers, nhưng không bảo đảm thứ tự FIFO tuyệt đối khi có locks/retries.

### 23.3. Lease không phải khóa tuyệt đối

Worker A có thể bị pause lâu, lease hết hạn, worker B claim lại; sau đó A thức dậy và tiếp tục. Cần fencing token/ownership check trong transaction apply, heartbeat và/hoặc transaction-level advisory lock.

### 23.4. Fencing token

Một số hệ thống tăng `lease_generation` mỗi lần claim. Worker chỉ được commit kết quả nếu generation vẫn là token của nó. Worker cũ không thể ghi sau khi worker mới đã claim generation cao hơn.

Ví dụ ý tưởng:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

Để dùng câu lệnh này, thêm cột `lease_generation bigint NOT NULL DEFAULT 0` vào schema batch. Trong transaction apply, khóa row batch và xác minh generation trước khi ghi target.

### 23.5. Advisory transaction lock

Có thể serialize theo source/batch bằng `pg_advisory_xact_lock(...)` nếu quy ước lock key nhất quán. Advisory lock hỗ trợ phối hợp, nhưng unique constraints và idempotent writes vẫn phải bảo vệ dữ liệu.

### 23.6. Đừng giữ transaction mở trong suốt thời gian tải file từ mạng

Tải file, gọi API, giải nén và validate tốn thời gian. Làm chúng trước hoặc ở ngoài transaction apply. Chỉ mở transaction DB đủ ngắn để ghi chunk/merge/checkpoint.

## 24. Reconciliation: đối soát từ số lượng đến nội dung

Đối soát phải có các tầng kiểm tra.

### 24.1. Count reconciliation

Với một batch:

- `expected_rows`: số rows nguồn tuyên bố.
- `received_rows`: số raw rows đã nhận.
- `valid_rows`: số rows vượt validation.
- `rejected_rows`: số rows bị quarantine.
- `duplicate_rows`: số deliveries/rows lặp.
- `applied_new_rows`: records mới.
- `applied_update_rows`: records cập nhật.
- `unchanged_rows`: cùng version/cùng payload.
- `stale_rows`: event cũ bị bỏ qua.

Định nghĩa các nhóm **không chồng lấn** hoặc ghi rõ nhóm nào là subset. Nếu `received = valid + rejected`, duplicates có thể là một thuộc tính của valid rows chứ không tự cộng thêm lần nữa.

### 24.2. Ví dụ accounting rõ ràng

Một batch có 1.000 source rows:

| Phân loại cuối cùng (mutually exclusive) | Số lượng |
| --- | ---: |
| New records applied | 700 |
| Existing records updated | 150 |
| Unchanged duplicates | 80 |
| Stale events ignored | 30 |
| Rejected | 40 |
| **Total received** | **1.000** |

Nếu source contract tuyên bố 1.000 rows, `received_rows` phải khớp. `valid_rows` theo ví dụ này là 960 nếu stale/unchanged vẫn hợp lệ; rejected là 40. Không lấy `700 + 150 + 80 + 30 + 40` rồi cộng duplicates lần nữa.

### 24.3. Reconcile raw rows với expected

```sql
SELECT
    b.batch_id,
    b.expected_rows,
    COUNT(r.source_row_no) AS actual_raw_rows,
    b.received_rows
FROM ingest.batches AS b
LEFT JOIN ingest.raw_order_rows AS r
  ON r.batch_id = b.batch_id
WHERE b.batch_id =
    '11111111-1111-4111-8111-111111111111'
GROUP BY b.batch_id, b.expected_rows, b.received_rows;
```

Nếu batch bị chunked, kiểm tra số row numbers unique và dải row numbers/partition completeness theo source contract; count bằng nhau chưa chứng minh không bị thay row.

### 24.4. Missing và extra keys bằng anti-join

Nếu có bảng snapshot nguồn đã chuẩn hóa `ingest.source_snapshot_orders`, so sánh:

```sql
-- Có ở nguồn nhưng thiếu ở target.
SELECT s.tenant_id, s.source_record_id
FROM ingest.source_snapshot_orders AS s
LEFT JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND t.source_record_id IS NULL;

-- Có ở target trong scope nhưng không còn ở snapshot nguồn.
SELECT t.tenant_id, t.source_record_id
FROM app.orders AS t
LEFT JOIN ingest.source_snapshot_orders AS s
  ON s.tenant_id = t.tenant_id
 AND s.source_system = t.source_system
 AND s.source_record_id = t.source_record_id
 AND s.snapshot_id = $1
WHERE t.source_system = $2
  AND t.tenant_id = $3
  AND t.deleted_at IS NULL
  AND s.source_record_id IS NULL;
```

Câu thứ hai chỉ có ý nghĩa nếu snapshot nguồn **đầy đủ, đã hoàn tất và đúng cùng scope**. Không xóa records dựa trên một snapshot partial.

### 24.5. So versions và payload hashes

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version AS source_version,
    t.source_version AS target_version,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM ingest.source_snapshot_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND (
      s.source_version <> t.source_version
      OR s.payload_sha256 <> t.payload_sha256
  );
```

Điều tra từng category: target stale, source stale, same-version conflict, normalization mismatch hoặc lỗi apply.

## 25. Checksum reconciliation cho dữ liệu lớn

Count và key checks chưa đủ để chứng minh payload giống nhau. Checksum có thể phát hiện sai khác trên tập records.

### 25.1. Canonical row representation

Ví dụ mỗi record được biểu diễn theo thứ tự field cố định:

```text
tenant_id | source_system | source_record_id |
source_version | status | amount | deleted_at
```

Cần quy ước chính xác cách biểu diễn NULL, numeric scale, timestamp timezone và Unicode.

### 25.2. Checksum theo partition

Với `pgcrypto`:

```sql
SELECT
    tenant_id,
    COUNT(*) AS row_count,
    encode(
        digest(
            convert_to(
                string_agg(
                    concat_ws(
                        E'\x1f',
                        source_record_id,
                        source_version::text,
                        payload_sha256
                    ),
                    E'\n'
                    ORDER BY source_record_id
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    ) AS partition_sha256
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id
ORDER BY tenant_id;
```

### 25.3. Giới hạn của ví dụ string_agg

Một partition rất lớn có thể tạo chuỗi tạm rất lớn trong memory. Trong production, chia theo tenant/key range/date partitions, hoặc dùng Merkle tree/hierarchical checksums với canonical leaf hashing.

### 25.4. Không cộng các hash như số học để coi là checksum chắc chắn

`SUM(hash_as_number)` hoặc XOR đơn giản có thể có collision và không bảo toàn thứ tự/identity như mong đợi. Dùng thuật toán/checksum design được xác định rõ, có thể tái tạo từ cả hai phía.

### 25.5. Hash không chứng minh nguồn là đáng tin

Checksum chỉ chứng minh nội dung khớp với digest đã tính. Nếu nguồn bị giả mạo, cần authenticated transport, signatures hoặc trusted source controls.

## 26. Đối soát tổng hợp nghiệp vụ

Ngoài row count/hash, so các totals có ý nghĩa:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS amount_total,
    MIN(source_updated_at) AS first_seen,
    MAX(source_updated_at) AS last_seen
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Nếu nguồn cung cấp summary theo tenant/status, so với các totals tương ứng.

### 26.1. Aggregate match không chứng minh record-level match

Một order thiếu 100 và một order thừa 100 có thể làm tổng tiền vẫn bằng nhau. Vì vậy aggregate là **một lớp** reconciliation, không thay key-level comparison.

### 26.2. Currency và precision

Không cộng số tiền của nhiều currencies nếu không có currency conversion contract. Dùng `numeric`, không dùng floating point cho accounting values; quy định scale và rounding.

### 26.3. Time window

So sánh cùng snapshot/time window. Nếu source tiếp tục thay đổi trong khi target đang ingest, aggregate có thể khác hợp lệ vì hai bên không cùng thời điểm.

## 27. Full snapshot và incremental/CDC không giống nhau

### 27.1. Full snapshot

Nguồn tuyên bố: “Đây là toàn bộ orders thuộc tenant 10 tại snapshot S”.

Có thể so missing/extra keys và đánh dấu deleted nếu:

- Snapshot có marker hoàn tất.
- Tất cả pages/parts đã nhận.
- Counts/checksums hợp lệ.
- Đúng tenant/source scope.
- Không có batch khác đang cập nhật cùng scope mà chưa được serialize.

### 27.2. Incremental feed

Nguồn chỉ gửi records mới/thay đổi từ watermark. Một record không xuất hiện trong batch incremental **không có nghĩa đã bị xóa**.

### 27.3. CDC

CDC phát các events thay đổi theo log sequence. Cần giữ source offset/LSN, transaction ordering và delete events. Không suy delete từ việc một key vắng mặt trong một chunk.

### 27.4. Full snapshot generation

Một cách quản lý visibility:

1. Tạo `snapshot_id`.
2. Nạp tất cả rows vào generation mới.
3. Đối soát expected count/checksum.
4. Chỉ khi đầy đủ mới đánh dấu generation `published`.
5. Downstream đọc generation hiện hành.
6. Dọn generation cũ theo retention policy.

Điều này tránh downstream đọc snapshot partial trong khi import đang chạy.

### 27.5. Không xóa theo snapshot bị thiếu page

Nếu page 4/10 tải lỗi nhưng pipeline vẫn đánh dấu các records không xuất hiện là deleted, có thể xóa hàng loạt dữ liệu hợp lệ. Full snapshot phải có completion manifest và reconciliation trước delete phase.

## 28. Late-arriving và out-of-order events

Một event version 12 có thể đến trước version 11. Khi version 11 đến sau, nó không được ghi đè version 12.

### 28.1. Version gate

Điều kiện:

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

giữ target ở phiên bản cao hơn.

### 28.2. Version phải có semantics

Nếu source version chỉ reset mỗi ngày hoặc mỗi partition, không thể so sánh toàn cục mà không có thêm epoch/partition identity. Xác định rõ:

- Version tăng theo record?
- Offset tăng theo partition?
- Timestamp có tie-breaker?
- Source có thể replay historical corrections?
- Delete có version như update không?

### 28.3. Same version, different payload

Không chọn winner ngẫu nhiên. Ghi conflict, quarantine và yêu cầu source contract/owner giải quyết.

### 28.4. Late corrections

Một correction hợp lệ có thể mang business effective date cũ nhưng event version mới. Không dùng business date thay event ordering. Lưu cả `source_version` và `source_updated_at`/effective time nếu cần.

## 29. Xử lý lỗi một phần và poison records

Một row lỗi không nhất thiết làm hỏng mọi rows khác, nhưng policy phải rõ.

### 29.1. Atomic batch

Nếu batch là một đơn vị nghiệp vụ bất khả phân, bất kỳ validation/merge error nào rollback toàn batch. Sau khi nguồn sửa file, tạo batch key mới hoặc version mới theo contract; không tái sử dụng cùng key với content khác mà không ghi nhận.

### 29.2. Partial acceptance

Nếu chấp nhận partial rows:

- Ghi mọi row vào raw.
- Validation status rõ ràng.
- Lỗi vào quarantine.
- Chỉ valid rows được merge.
- Counts phải cộng đúng.
- Batch không được `reconciled` cho đến khi rejected rows được chấp nhận theo policy hoặc được xử lý.

### 29.3. Poison message

Một message liên tục làm consumer fail có thể chặn partition/queue. Sau số lần retry có giới hạn, chuyển vào dead-letter/quarantine store, ghi reason và giữ original payload. Đừng âm thầm drop message.

### 29.4. Không dùng `WHEN OTHERS THEN NULL`

Bắt mọi exception rồi tiếp tục có thể làm batch báo thành công dù một số rows chưa được apply. Nếu bắt lỗi để partial process, phải ghi lỗi, phân loại, và đảm bảo transaction/savepoint semantics rõ.

### 29.5. Savepoint theo row có chi phí

Savepoint giúp rollback một phần transaction, nhưng tạo overhead và không thay validation. Với file lớn, validate set-based trước rồi merge valid rows thường hiệu quả hơn vòng lặp một savepoint cho mỗi row.

## 30. Checkpoint theo chunk và khả năng resume

Với batch rất lớn, chia thành chunks có thứ tự ổn định.

### 30.1. Chunk identity

Ví dụ:

`(batch_id, chunk_no)` hoặc `(source_partition, first_offset, last_offset)`.

Cùng một chunk phải có cùng phạm vi nguồn mỗi lần retry.

### 30.2. Chunk ledger

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applying', 'applied', 'failed')),
    rows_received bigint NOT NULL DEFAULT 0,
    rows_applied bigint NOT NULL DEFAULT 0,
    payload_sha256 text,
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

### 30.3. Atomic chunk commit

Trong một transaction:

1. Khóa chunk row.
2. Kiểm tra checksum và status.
3. Merge target rows idempotently.
4. Cập nhật chunk `applied`.
5. Cập nhật checkpoint tương ứng.
6. Commit.

Nếu process crash trước commit, cả merge và progress update rollback. Nếu crash sau commit nhưng trước khi worker nhận phản hồi, lần chạy lại thấy chunk `applied` và không áp dụng lại sai.

### 30.4. Không chỉ dựa row number liên tục

Nếu source pages có gaps hoặc opaque cursor, dùng source cursor/offset do nguồn cấp. `last_row_no` chỉ phù hợp với file/batch có thứ tự và row numbering ổn định.

### 30.5. Batch completion

Batch chuyển `applied` khi mọi chunks cần thiết đã applied hoặc được phân loại rejected theo partial-acceptance policy. Sau đó chạy reconciliation và chỉ chuyển `reconciled` khi checks pass.

## 31. Quản lý nhiều workers an toàn

Khi nhiều workers xử lý batch, cần tránh hai worker apply cùng batch đồng thời hoặc worker cũ tiếp tục ghi sau khi lease đã chuyển chủ.

### 31.1. Claim một batch bằng SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

Đây là ví dụ trong một transaction ngắn. Commit claim rồi worker mới thực hiện phần xử lý.

### 31.2. Vì sao SKIP LOCKED?

Nếu worker A đang khóa batch row 1, worker B bỏ qua row đó và nhận batch khác thay vì chờ. Phù hợp queue workers, nhưng không bảo đảm thứ tự FIFO tuyệt đối khi có locks/retries.

### 31.3. Lease không phải khóa tuyệt đối

Worker A có thể bị pause lâu, lease hết hạn, worker B claim lại; sau đó A thức dậy và tiếp tục. Cần fencing token/ownership check trong transaction apply, heartbeat và/hoặc transaction-level advisory lock.

### 31.4. Fencing token

Một số hệ thống tăng `lease_generation` mỗi lần claim. Worker chỉ được commit kết quả nếu generation vẫn là token của nó. Worker cũ không thể ghi sau khi worker mới đã claim generation cao hơn.

Ví dụ ý tưởng:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

Để dùng câu lệnh này, thêm cột `lease_generation bigint NOT NULL DEFAULT 0` vào schema batch. Trong transaction apply, khóa row batch và xác minh generation trước khi ghi target.

### 31.5. Advisory transaction lock

Có thể serialize theo source/batch bằng `pg_advisory_xact_lock(...)` nếu quy ước lock key nhất quán. Advisory lock hỗ trợ phối hợp, nhưng unique constraints và idempotent writes vẫn phải bảo vệ dữ liệu.

### 31.6. Đừng giữ transaction mở trong suốt thời gian tải file từ mạng

Tải file, gọi API, giải nén và validate tốn thời gian. Làm chúng trước hoặc ở ngoài transaction apply. Chỉ mở transaction DB đủ ngắn để ghi chunk/merge/checkpoint.

## 32. Reconciliation: đối soát từ số lượng đến nội dung

Đối soát phải có các tầng kiểm tra.

### 32.1. Count reconciliation

Với một batch:

- `expected_rows`: số rows nguồn tuyên bố.
- `received_rows`: số raw rows đã nhận.
- `valid_rows`: số rows vượt validation.
- `rejected_rows`: số rows bị quarantine.
- `duplicate_rows`: số deliveries/rows lặp.
- `applied_new_rows`: records mới.
- `applied_update_rows`: records cập nhật.
- `unchanged_rows`: cùng version/cùng payload.
- `stale_rows`: event cũ bị bỏ qua.

Định nghĩa các nhóm **không chồng lấn** hoặc ghi rõ nhóm nào là subset. Nếu `received = valid + rejected`, duplicates có thể là một thuộc tính của valid rows chứ không tự cộng thêm lần nữa.

### 32.2. Ví dụ accounting rõ ràng

Một batch có 1.000 source rows:

| Phân loại cuối cùng (mutually exclusive) | Số lượng |
| --- | ---: |
| New records applied | 700 |
| Existing records updated | 150 |
| Unchanged duplicates | 80 |
| Stale events ignored | 30 |
| Rejected | 40 |
| **Total received** | **1.000** |

Nếu source contract tuyên bố 1.000 rows, `received_rows` phải khớp. `valid_rows` theo ví dụ này là 960 nếu stale/unchanged vẫn hợp lệ; rejected là 40. Không lấy `700 + 150 + 80 + 30 + 40` rồi cộng duplicates lần nữa.

### 32.3. Reconcile raw rows với expected

```sql
SELECT
    b.batch_id,
    b.expected_rows,
    COUNT(r.source_row_no) AS actual_raw_rows,
    b.received_rows
FROM ingest.batches AS b
LEFT JOIN ingest.raw_order_rows AS r
  ON r.batch_id = b.batch_id
WHERE b.batch_id =
    '11111111-1111-4111-8111-111111111111'
GROUP BY b.batch_id, b.expected_rows, b.received_rows;
```

Nếu batch bị chunked, kiểm tra số row numbers unique và dải row numbers/partition completeness theo source contract; count bằng nhau chưa chứng minh không bị thay row.

### 32.4. Missing và extra keys bằng anti-join

Nếu có bảng snapshot nguồn đã chuẩn hóa `ingest.source_snapshot_orders`, so sánh:

```sql
-- Có ở nguồn nhưng thiếu ở target.
SELECT s.tenant_id, s.source_record_id
FROM ingest.source_snapshot_orders AS s
LEFT JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND t.source_record_id IS NULL;

-- Có ở target trong scope nhưng không còn ở snapshot nguồn.
SELECT t.tenant_id, t.source_record_id
FROM app.orders AS t
LEFT JOIN ingest.source_snapshot_orders AS s
  ON s.tenant_id = t.tenant_id
 AND s.source_system = t.source_system
 AND s.source_record_id = t.source_record_id
 AND s.snapshot_id = $1
WHERE t.source_system = $2
  AND t.tenant_id = $3
  AND t.deleted_at IS NULL
  AND s.source_record_id IS NULL;
```

Câu thứ hai chỉ có ý nghĩa nếu snapshot nguồn **đầy đủ, đã hoàn tất và đúng cùng scope**. Không xóa records dựa trên một snapshot partial.

### 32.5. So versions và payload hashes

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version AS source_version,
    t.source_version AS target_version,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM ingest.source_snapshot_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND (
      s.source_version <> t.source_version
      OR s.payload_sha256 <> t.payload_sha256
  );
```

Điều tra từng category: target stale, source stale, same-version conflict, normalization mismatch hoặc lỗi apply.

## 33. Checksum reconciliation cho dữ liệu lớn

Count và key checks chưa đủ để chứng minh payload giống nhau. Checksum có thể phát hiện sai khác trên tập records.

### 33.1. Canonical row representation

Ví dụ mỗi record được biểu diễn theo thứ tự field cố định:

```text
tenant_id | source_system | source_record_id |
source_version | status | amount | deleted_at
```

Cần quy ước chính xác cách biểu diễn NULL, numeric scale, timestamp timezone và Unicode.

### 33.2. Checksum theo partition

Với `pgcrypto`:

```sql
SELECT
    tenant_id,
    COUNT(*) AS row_count,
    encode(
        digest(
            convert_to(
                string_agg(
                    concat_ws(
                        E'\x1f',
                        source_record_id,
                        source_version::text,
                        payload_sha256
                    ),
                    E'\n'
                    ORDER BY source_record_id
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    ) AS partition_sha256
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id
ORDER BY tenant_id;
```

### 33.3. Giới hạn của ví dụ string_agg

Một partition rất lớn có thể tạo chuỗi tạm rất lớn trong memory. Trong production, chia theo tenant/key range/date partitions, hoặc dùng Merkle tree/hierarchical checksums với canonical leaf hashing.

### 33.4. Không cộng các hash như số học để coi là checksum chắc chắn

`SUM(hash_as_number)` hoặc XOR đơn giản có thể có collision và không bảo toàn thứ tự/identity như mong đợi. Dùng thuật toán/checksum design được xác định rõ, có thể tái tạo từ cả hai phía.

### 33.5. Hash không chứng minh nguồn là đáng tin

Checksum chỉ chứng minh nội dung khớp với digest đã tính. Nếu nguồn bị giả mạo, cần authenticated transport, signatures hoặc trusted source controls.

## 34. Đối soát tổng hợp nghiệp vụ

Ngoài row count/hash, so các totals có ý nghĩa:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS amount_total,
    MIN(source_updated_at) AS first_seen,
    MAX(source_updated_at) AS last_seen
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Nếu nguồn cung cấp summary theo tenant/status, so với các totals tương ứng.

### 34.1. Aggregate match không chứng minh record-level match

Một order thiếu 100 và một order thừa 100 có thể làm tổng tiền vẫn bằng nhau. Vì vậy aggregate là **một lớp** reconciliation, không thay key-level comparison.

### 34.2. Currency và precision

Không cộng số tiền của nhiều currencies nếu không có currency conversion contract. Dùng `numeric`, không dùng floating point cho accounting values; quy định scale và rounding.

### 34.3. Time window

So sánh cùng snapshot/time window. Nếu source tiếp tục thay đổi trong khi target đang ingest, aggregate có thể khác hợp lệ vì hai bên không cùng thời điểm.

## 35. Full snapshot và incremental/CDC không giống nhau

### 35.1. Full snapshot

Nguồn tuyên bố: “Đây là toàn bộ orders thuộc tenant 10 tại snapshot S”.

Có thể so missing/extra keys và đánh dấu deleted nếu:

- Snapshot có marker hoàn tất.
- Tất cả pages/parts đã nhận.
- Counts/checksums hợp lệ.
- Đúng tenant/source scope.
- Không có batch khác đang cập nhật cùng scope mà chưa được serialize.

### 35.2. Incremental feed

Nguồn chỉ gửi records mới/thay đổi từ watermark. Một record không xuất hiện trong batch incremental **không có nghĩa đã bị xóa**.

### 35.3. CDC

CDC phát các events thay đổi theo log sequence. Cần giữ source offset/LSN, transaction ordering và delete events. Không suy delete từ việc một key vắng mặt trong một chunk.

### 35.4. Full snapshot generation

Một cách quản lý visibility:

1. Tạo `snapshot_id`.
2. Nạp tất cả rows vào generation mới.
3. Đối soát expected count/checksum.
4. Chỉ khi đầy đủ mới đánh dấu generation `published`.
5. Downstream đọc generation hiện hành.
6. Dọn generation cũ theo retention policy.

Điều này tránh downstream đọc snapshot partial trong khi import đang chạy.

### 35.5. Không xóa theo snapshot bị thiếu page

Nếu page 4/10 tải lỗi nhưng pipeline vẫn đánh dấu các records không xuất hiện là deleted, có thể xóa hàng loạt dữ liệu hợp lệ. Full snapshot phải có completion manifest và reconciliation trước delete phase.

## 36. Late-arriving và out-of-order events

Một event version 12 có thể đến trước version 11. Khi version 11 đến sau, nó không được ghi đè version 12.

### 36.1. Version gate

Điều kiện:

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

giữ target ở phiên bản cao hơn.

### 36.2. Version phải có semantics

Nếu source version chỉ reset mỗi ngày hoặc mỗi partition, không thể so sánh toàn cục mà không có thêm epoch/partition identity. Xác định rõ:

- Version tăng theo record?
- Offset tăng theo partition?
- Timestamp có tie-breaker?
- Source có thể replay historical corrections?
- Delete có version như update không?

### 36.3. Same version, different payload

Không chọn winner ngẫu nhiên. Ghi conflict, quarantine và yêu cầu source contract/owner giải quyết.

### 36.4. Late corrections

Một correction hợp lệ có thể mang business effective date cũ nhưng event version mới. Không dùng business date thay event ordering. Lưu cả `source_version` và `source_updated_at`/effective time nếu cần.

## 37. Xử lý lỗi một phần và poison records

Một row lỗi không nhất thiết làm hỏng mọi rows khác, nhưng policy phải rõ.

### 37.1. Atomic batch

Nếu batch là một đơn vị nghiệp vụ bất khả phân, bất kỳ validation/merge error nào rollback toàn batch. Sau khi nguồn sửa file, tạo batch key mới hoặc version mới theo contract; không tái sử dụng cùng key với content khác mà không ghi nhận.

### 37.2. Partial acceptance

Nếu chấp nhận partial rows:

- Ghi mọi row vào raw.
- Validation status rõ ràng.
- Lỗi vào quarantine.
- Chỉ valid rows được merge.
- Counts phải cộng đúng.
- Batch không được `reconciled` cho đến khi rejected rows được chấp nhận theo policy hoặc được xử lý.

### 37.3. Poison message

Một message liên tục làm consumer fail có thể chặn partition/queue. Sau số lần retry có giới hạn, chuyển vào dead-letter/quarantine store, ghi reason và giữ original payload. Đừng âm thầm drop message.

### 37.4. Không dùng `WHEN OTHERS THEN NULL`

Bắt mọi exception rồi tiếp tục có thể làm batch báo thành công dù một số rows chưa được apply. Nếu bắt lỗi để partial process, phải ghi lỗi, phân loại, và đảm bảo transaction/savepoint semantics rõ.

### 37.5. Savepoint theo row có chi phí

Savepoint giúp rollback một phần transaction, nhưng tạo overhead và không thay validation. Với file lớn, validate set-based trước rồi merge valid rows thường hiệu quả hơn vòng lặp một savepoint cho mỗi row.

## 38. Checkpoint theo chunk và khả năng resume

Với batch rất lớn, chia thành chunks có thứ tự ổn định.

### 38.1. Chunk identity

Ví dụ:

`(batch_id, chunk_no)` hoặc `(source_partition, first_offset, last_offset)`.

Cùng một chunk phải có cùng phạm vi nguồn mỗi lần retry.

### 38.2. Chunk ledger

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applying', 'applied', 'failed')),
    rows_received bigint NOT NULL DEFAULT 0,
    rows_applied bigint NOT NULL DEFAULT 0,
    payload_sha256 text,
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

### 38.3. Atomic chunk commit

Trong một transaction:

1. Khóa chunk row.
2. Kiểm tra checksum và status.
3. Merge target rows idempotently.
4. Cập nhật chunk `applied`.
5. Cập nhật checkpoint tương ứng.
6. Commit.

Nếu process crash trước commit, cả merge và progress update rollback. Nếu crash sau commit nhưng trước khi worker nhận phản hồi, lần chạy lại thấy chunk `applied` và không áp dụng lại sai.

### 38.4. Không chỉ dựa row number liên tục

Nếu source pages có gaps hoặc opaque cursor, dùng source cursor/offset do nguồn cấp. `last_row_no` chỉ phù hợp với file/batch có thứ tự và row numbering ổn định.

### 38.5. Batch completion

Batch chuyển `applied` khi mọi chunks cần thiết đã applied hoặc được phân loại rejected theo partial-acceptance policy. Sau đó chạy reconciliation và chỉ chuyển `reconciled` khi checks pass.

## 39. Quản lý nhiều workers an toàn

Khi nhiều workers xử lý batch, cần tránh hai worker apply cùng batch đồng thời hoặc worker cũ tiếp tục ghi sau khi lease đã chuyển chủ.

### 39.1. Claim một batch bằng SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

Đây là ví dụ trong một transaction ngắn. Commit claim rồi worker mới thực hiện phần xử lý.

### 39.2. Vì sao SKIP LOCKED?

Nếu worker A đang khóa batch row 1, worker B bỏ qua row đó và nhận batch khác thay vì chờ. Phù hợp queue workers, nhưng không bảo đảm thứ tự FIFO tuyệt đối khi có locks/retries.

### 39.3. Lease không phải khóa tuyệt đối

Worker A có thể bị pause lâu, lease hết hạn, worker B claim lại; sau đó A thức dậy và tiếp tục. Cần fencing token/ownership check trong transaction apply, heartbeat và/hoặc transaction-level advisory lock.

### 39.4. Fencing token

Một số hệ thống tăng `lease_generation` mỗi lần claim. Worker chỉ được commit kết quả nếu generation vẫn là token của nó. Worker cũ không thể ghi sau khi worker mới đã claim generation cao hơn.

Ví dụ ý tưởng:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

Để dùng câu lệnh này, thêm cột `lease_generation bigint NOT NULL DEFAULT 0` vào schema batch. Trong transaction apply, khóa row batch và xác minh generation trước khi ghi target.

### 39.5. Advisory transaction lock

Có thể serialize theo source/batch bằng `pg_advisory_xact_lock(...)` nếu quy ước lock key nhất quán. Advisory lock hỗ trợ phối hợp, nhưng unique constraints và idempotent writes vẫn phải bảo vệ dữ liệu.

### 39.6. Đừng giữ transaction mở trong suốt thời gian tải file từ mạng

Tải file, gọi API, giải nén và validate tốn thời gian. Làm chúng trước hoặc ở ngoài transaction apply. Chỉ mở transaction DB đủ ngắn để ghi chunk/merge/checkpoint.

## 40. Transaction boundaries và side effects bên ngoài

PostgreSQL transaction chỉ atomically bảo đảm thay đổi trong **cùng PostgreSQL database**.

Không có transaction đơn giản bao trùm:

- PostgreSQL commit.
- Kafka offset ack.
- Ghi file vào object storage.
- Gửi email.
- Gọi payment API.
- Gửi webhook cho đối tác.

### 40.1. Transactional outbox

Nếu việc merge dữ liệu cần phát event cho hệ thống khác, ghi outbox row **cùng transaction** với target update:

```sql
CREATE TABLE app.outbox (
    event_id uuid PRIMARY KEY,
    aggregate_key text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz
);
```

Trong transaction apply:

```sql
BEGIN;

-- UPSERT app.orders ...

INSERT INTO app.outbox (
    event_id,
    aggregate_key,
    event_type,
    payload
)
VALUES (
    '22222222-2222-4222-8222-222222222222',
    'partner_a:order-9381',
    'order.imported',
    '{"order_id":"order-9381","version":17}'::jsonb
)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
```

Publisher đọc outbox, gửi message, rồi đánh dấu published. Nếu publisher gửi thành công nhưng crash trước khi update `published_at`, event có thể được gửi lại; consumer downstream vẫn cần idempotency theo `event_id`.

### 40.2. Không gọi HTTP trong transaction apply

Gọi API ngoài trong lúc transaction giữ locks có thể kéo dài transaction và không atomically rollback được API nếu DB rollback.

### 40.3. Side effect phải có idempotency key

Email/payment/webhook provider cần idempotency key hoặc một delivery ledger thích hợp. Outbox đảm bảo event không mất giữa DB update và publish intent, nhưng không tự đảm bảo downstream chỉ thực hiện đúng một lần.

## 41. Xuất dữ liệu có thể lặp lại và đối soát

Bài toán export cũng cần identity, snapshot và checksum.

### 41.1. Stable export identity

Dùng `export_id`, source scope, snapshot/version, filter parameters và format version. Retry cùng export identity phải tạo cùng logical dataset nếu snapshot contract giống nhau.

### 41.2. Consistent snapshot

Nếu export nhiều pages trong khi bảng tiếp tục thay đổi, các pages có thể phản ánh những thời điểm khác nhau. Dùng transaction `REPEATABLE READ READ ONLY` hoặc một snapshot/generation đã publish:

```sql
BEGIN TRANSACTION
ISOLATION LEVEL REPEATABLE READ
READ ONLY;

SELECT
    order_id,
    customer_code,
    status,
    amount
FROM app.orders
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY order_id;

COMMIT;
```

Transaction dài có chi phí giữ snapshot; với export lớn, cân nhắc snapshot generation/materialized export dataset hoặc thời gian chạy có kiểm soát.

### 41.3. Keyset pagination

Không dựa `OFFSET` lớn nếu dữ liệu thay đổi giữa các pages. Dùng keyset:

```sql
SELECT order_id, customer_code, amount
FROM app.orders
WHERE tenant_id = $1
  AND order_id > $2
ORDER BY order_id
LIMIT $3;
```

Trong một snapshot ổn định, cursor là last key đã xuất. Nếu không có snapshot ổn định, inserts/updates/deletes giữa pages vẫn có thể làm dataset không nhất quán.

### 41.4. Publish file atomically

Một pattern:

1. Ghi file vào temporary object/path theo `export_id`.
2. Flush/complete upload.
3. Tính checksum và row count.
4. Ghi manifest.
5. Publish bằng atomic rename/object version pointer khi storage hỗ trợ.
6. Retry dùng cùng identity/checksum; không ghi đè file đã publish bằng content khác âm thầm.

### 41.5. Export reconciliation

Manifest có thể ghi:

- `export_id`.
- Snapshot/generation.
- Query/filter version.
- Expected rows.
- Actual rows.
- File size.
- SHA-256.
- Created/published timestamps.
- Schema/format version.

Người nhận kiểm tra checksum, row count và schema version trước khi import.

## 42. Xử lý schema evolution

Nguồn có thể thêm cột, đổi tên field, thay enum hoặc đổi format.

### 42.1. Version payload

Ghi `schema_version`/`format_version` trong batch metadata. Parser chọn đúng schema contract thay vì đoán dựa vào field có mặt.

### 42.2. Raw payload giữ khả năng replay

Lưu raw payload đủ lâu để có thể chạy parser mới trên dữ liệu cũ khi sửa bug hoặc mở rộng schema.

### 42.3. Migration staging có kiểm soát

Đừng thay đổi target schema giữa lúc một batch cũ đang apply mà không có tương thích. Có thể version parser và staging, rồi map vào target model hiện tại.

### 42.4. Unknown fields

Chọn policy rõ: reject, ignore có cảnh báo, hoặc lưu trong JSONB extension field. Không âm thầm bỏ field có ý nghĩa nghiệp vụ.

### 42.5. Backfill có idempotency

Backfill là một pipeline khác về throughput nhưng vẫn dùng source identity/version/checkpoints. Không ghi lại toàn bộ target bằng `UPDATE` vô điều kiện nếu nguồn có thể tiếp tục cập nhật.

## 43. Chuẩn hóa dữ liệu trước khi so sánh

Hai hệ thống có thể biểu diễn cùng giá trị khác nhau:

- `1.0` và `1.00`.
- `2026-11-14T10:00:00+07:00` và `2026-11-14T03:00:00Z`.
- Unicode composed/decomposed.
- Empty string và SQL NULL.
- Uppercase/lowercase status.
- JSON key order/whitespace.
- Currency units hoặc rounding.

### 43.1. Định nghĩa canonical representation

Trước khi hash/compare, xác định:

- Timezone chuẩn (thường lưu instant `timestamptz`).
- Decimal precision/scale.
- Unicode normalization nếu business yêu cầu.
- Case sensitivity/collation.
- NULL/empty semantics.
- Enum mapping.
- JSON canonicalization.
- Field inclusion/exclusion.

### 43.2. Không chuẩn hóa tùy tiện làm mất nghĩa

`trim()` mọi text có thể làm thay đổi mã định danh có whitespace hợp lệ. Lowercase mọi string có thể làm sai case-sensitive IDs. Chỉ normalize theo data contract.

### 43.3. Lưu cả raw và normalized

Raw giúp điều tra/replay; normalized typed values giúp query, index, constraints và reconciliation.

## 44. Bảo mật và phân quyền cho pipeline

Một ingestion worker thường có quyền ghi dữ liệu đáng kể. Tách roles:

- `ingest_reader`: đọc nguồn nếu có connector/database.
- `ingest_writer`: ghi raw/staging/batch metadata.
- `ingest_applier`: merge vào bảng nghiệp vụ trong phạm vi được phép.
- `app_runtime`: quyền ứng dụng bình thường.
- `audit_reader`: đọc kết quả đối soát.
- DBA/migration role: quản trị schema.

### 44.1. Least privilege

Không dùng superuser làm credential của importer. Worker chỉ cần quyền với schemas/tables liên quan và operations đã định nghĩa.

### 44.2. Tenant scope

Nếu batch chứa nhiều tenants, xác minh tenant IDs từ hợp đồng nguồn và authorization. Đừng tin một file do user tải lên có thể tự khai báo tenant bất kỳ.

### 44.3. Raw payload có thể nhạy cảm

Áp retention, encryption/access controls, masking và audit cho raw/quarantine storage. Không log toàn bộ payload chứa PII/secrets.

### 44.4. SQL động trong import

Tên table/partition/schema động phải mapping allowlist và quote identifiers; values vẫn bind. Không lấy field name/DDL fragment raw từ CSV để ghép SQL.

### 44.5. File handling

Dùng `COPY FROM STDIN` hoặc API upload có quyền giới hạn. Không cấp quyền đọc file server filesystem cho application chỉ để tiện import.

## 45. Performance: tối ưu sau khi đã có semantics đúng

### 45.1. Batch size

Batch quá nhỏ tăng round trips/commit overhead; batch quá lớn tăng memory, WAL, lock duration và recovery time. Đo theo payload size, indexes, write amplification và replication capacity.

### 45.2. COPY và set-based merge

COPY raw/staging nhanh, sau đó validate/dedup/merge bằng SQL set-based thường tốt hơn vòng lặp một `INSERT` cho mỗi row.

### 45.3. Index staging vừa đủ

Primary keys và indexes phục vụ dedup/joins cần thiết; quá nhiều indexes làm COPY/UPSERT chậm. Có thể tạo indexes sau bulk load nếu staging lifecycle cho phép.

### 45.4. Target indexes

Mỗi unique/index cần được cập nhật khi UPSERT. Giữ indexes phục vụ business reads, nhưng đánh giá write cost.

### 45.5. Partitioning

Raw/staging lớn theo batch/date có thể partition theo thời gian hoặc source. Partition key cần phù hợp retention và query patterns; không partition chỉ vì bảng lớn mà không có plan.

### 45.6. Vacuum và bloat

UPSERT/update nhiều có thể tạo dead tuples. Theo dõi autovacuum, table/index bloat, WAL, replication lag và long-running snapshots.

### 45.7. Tránh transaction dài

Chunk commits giúp giải phóng locks và giảm transaction age. Nếu downstream cần all-or-nothing visibility, dùng generation/publish switch thay vì giữ một transaction cực lớn.

## 46. Metrics và trạng thái vận hành

Mỗi batch nên có các thông tin:

| Nhóm | Metrics/fields |
| --- | --- |
| Identity | source system, batch key, batch ID, payload checksum |
| Volume | expected, received, valid, rejected, duplicate |
| Apply | inserted, updated, unchanged, stale, deleted/tombstone |
| Reconciliation | missing, extra, conflicts, count/hash match |
| Timing | queued, started, last progress, completed, reconciled |
| Retry | attempt count, last error, worker, lease generation |
| Source | watermark start/end, snapshot ID, schema version |
| Export | export ID, row count, file size, checksum, publish status |

### 46.1. Alert conditions

- Batch stuck ở `loading`/`applying` quá lâu.
- Lease liên tục hết hạn.
- Cùng batch key có checksum khác.
- Reconciliation missing/extra/conflict khác 0.
- Rejected rate tăng bất thường.
- Watermark không tiến triển.
- Target lag so với source vượt SLA.
- Retry attempts tăng nhanh.
- Outbox backlog tăng.
- Export manifest chưa được publish.

### 46.2. Không chỉ báo batch SUCCESS

Trạng thái `applied` và `reconciled` khác nhau:

- `applied`: merge đã commit.
- `reconciled`: các kiểm tra cần thiết đã đạt.

Một batch applied nhưng mismatch không được báo là hoàn tất hoàn toàn.

### 46.3. Giữ history

Batch ledger, chunk ledger, rejected rows và reconciliation results giúp giải thích lần chạy đã làm gì. Có retention/partition/archive policy; đừng xóa bằng chứng trước khi hết replay/audit window.

## 47. Failure scenarios và cách phục hồi

| Điểm crash/lỗi | Trạng thái có thể thấy | Cách resume |
| --- | --- | --- |
| Trước batch registration | Không có batch row | Register cùng source batch key |
| Sau registration, trước raw load | `received` | Claim và load lại |
| Trong COPY trước commit | Temp/raw transaction chưa commit | Retry load cùng batch |
| Sau raw commit, trước broker ack | Raw đã tồn tại, message có thể giao lại | Dedup event/batch identity rồi ack |
| Sau staging, trước apply | Raw/stage bền vững | Resume validation/apply |
| Trong atomic merge trước commit | Target và progress rollback | Retry cùng batch/chunk |
| Sau commit, trước worker nhận response | Target đã thay đổi | Đọc ledger/version/checksum; replay safe |
| Sau apply, trước reconciliation | `applied` | Chạy lại reconciliation |
| Sau export file upload, trước manifest publish | File tạm có thể tồn tại | Verify checksum, resume publish hoặc clean temp |
| Lease hết hạn khi worker cũ còn chạy | Hai workers có thể cạnh tranh | Fencing token/lock + idempotent target |
| Cùng key, checksum khác | Batch identity conflict | Quarantine/incident, không ghi đè |
| Cùng record/version, payload khác | Record conflict | Quarantine/resolve theo source contract |
| Out-of-order stale event | Version thấp hơn target | Bỏ qua có accounting |
| Delete event rồi insert cũ đến muộn | Tombstone version cao | Không resurrect |
| Snapshot thiếu page | Reconciliation không đủ | Không chạy delete reconciliation; lấy đủ snapshot |

## 48. Quy trình triển khai end-to-end

Một pipeline có thể triển khai theo các bước:

### Bước 1. Nhận nguồn và tạo batch manifest

Lấy source system, stable batch key, checksum, expected row count, schema version và source watermark.

### Bước 2. Register idempotently

Insert batch registry với unique `(source_system, source_batch_key)`. Nếu đã có, so checksum và resume/return prior status.

### Bước 3. Persist raw data

Lưu raw file/payload hoặc URI+checksum; COPY vào raw landing/staging. Đảm bảo source ack chỉ sau khi raw data bền vững.

### Bước 4. Validate và normalize

Parse types, domain, identity, tenant scope và source versions. Quarantine rows lỗi.

### Bước 5. Deduplicate và kiểm tra conflicts

Cùng key/version/hash là duplicate; cùng key/version/different hash là conflict; chọn latest version theo source ordering contract.

### Bước 6. Apply transactionally

UPSERT với unique constraints và version gate. Apply tombstones cho delete events. Ghi progress/checkpoint cùng transaction/chunk.

### Bước 7. Reconcile

Đối chiếu counts, keys, versions, payload checksums và aggregates. Với snapshot, chỉ đánh dấu missing/deleted khi snapshot hoàn tất.

### Bước 8. Publish downstream intent

Ghi outbox cùng target transaction. Publisher gửi event theo at-least-once; consumers dedup bằng event ID.

### Bước 9. Mark reconciled

Chỉ chuyển batch thành `reconciled` sau khi các invariant cần thiết đạt và mọi rejected rows được xử lý theo policy.

### Bước 10. Archive/retention

Giữ raw/checkpoint/audit đủ lâu cho replay, reconciliation và yêu cầu pháp lý; sau đó archive/xóa theo retention policy.

## 49. Bài tập thực hành có đáp án

Các bài tập sử dụng schemas `ingest` và `app` trong lab. Những đoạn SQL có `$1`/`$2` giả định chạy trong prepared statement hoặc function phù hợp.

### Bài 1. Idempotent operation là gì?

**Đáp án:** cùng một operation được áp dụng nhiều lần không làm thay đổi trạng thái cuối so với áp dụng một lần, theo identity và semantics đã định nghĩa.

### Bài 2. Vì sao importer phải chịu duplicate delivery?

**Đáp án:** broker, file retry, network failure hoặc worker crash có thể khiến cùng dữ liệu được giao lại; at-least-once thường là lựa chọn thực tế.

### Bài 3. Batch key khác record key thế nào?

**Đáp án:** batch key nhận diện một gói nguồn; record key nhận diện một entity/event qua nhiều batches.

### Bài 4. Vì sao row number không phải business key?

**Đáp án:** thứ tự file có thể đổi, row number chỉ xác định vị trí trong một batch cụ thể.

### Bài 5. Tại sao unique constraint quan trọng?

**Đáp án:** nó là lớp bảo vệ cuối trước duplicate/race; kiểm tra bằng SELECT trước INSERT không an toàn khi concurrent workers.

### Bài 6. Cùng batch key, cùng checksum có ý nghĩa gì?

**Đáp án:** có thể là retry của cùng batch content; resume hoặc trả kết quả đã lưu.

### Bài 7. Cùng batch key, checksum khác phải xử lý ra sao?

**Đáp án:** conflict/incident; không âm thầm thay payload của batch cũ.

### Bài 8. SHA-256 thay thế source identity được không?

**Đáp án:** không. Hai records khác nhau có thể có payload giống nhau; identity cần source keys.

### Bài 9. Raw landing có lợi ích gì?

**Đáp án:** giữ bằng chứng nguồn, cho phép replay/parser mới, truy vết lỗi và tách transport khỏi business merge.

### Bài 10. JSONB có bảo toàn file CSV byte-for-byte không?

**Đáp án:** không. Nó giữ JSON values đã parse, không giữ whitespace/order/CSV quoting của file gốc.

### Bài 11. COPY FROM STDIN khác COPY FROM '/path' thế nào?

**Đáp án:** STDIN nhận stream từ client; path form đọc file trên filesystem server và có yêu cầu quyền/đường dẫn khác.

### Bài 12. Vì sao nên COPY vào staging?

**Đáp án:** để validate, dedup, quarantine, reconcile và merge có kiểm soát trước target.

### Bài 13. Duplicate cùng key/version/hash là gì?

**Đáp án:** thường là duplicate delivery; giữ một record và đếm duplicates.

### Bài 14. Cùng key/version nhưng hash khác?

**Đáp án:** conflict dữ liệu; không tự chọn row cuối nếu source contract không định nghĩa winner.

### Bài 15. Source version dùng để làm gì?

**Đáp án:** ngăn event cũ đến muộn ghi đè trạng thái mới hơn.

### Bài 16. Vì sao received_at không thay source_version?

**Đáp án:** event cũ có thể đến muộn, nên consumer receive time không phản ánh thứ tự thay đổi ở nguồn.

### Bài 17. ON CONFLICT DO NOTHING có đủ để chống mọi corruption không?

**Đáp án:** không. Phải so payload/hash khi conflict; cùng key nhưng content khác cần được phát hiện.

### Bài 18. Điều kiện version trong UPSERT?

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

**Đáp án:** chỉ update target khi incoming version mới hơn.

### Bài 19. Vì sao không dùng xmax=0 làm business accounting contract?

**Đáp án:** đó là cách suy luận từ system column không phải API nghiệp vụ ổn định; dùng ledger/explicit classification.

### Bài 20. Tombstone là gì?

**Đáp án:** record/marker giữ identity và delete version để ngăn event cũ làm sống lại dữ liệu đã xóa.

### Bài 21. Delete event đến trước insert event thì sao?

**Đáp án:** cần lưu tombstone ngay cả khi target row chưa tồn tại, để event insert cũ không tạo lại row.

### Bài 22. Có thể xóa tombstone ngay sau delete không?

**Đáp án:** không nếu nguồn còn khả năng replay/late events; giữ qua replay retention window.

### Bài 23. Checkpoint là gì?

**Đáp án:** vị trí nguồn đã được lưu/xử lý bền vững theo semantics đã định nghĩa, như offset, LSN hoặc cursor.

### Bài 24. Vì sao advance checkpoint trước target commit nguy hiểm?

**Đáp án:** crash có thể làm bỏ mất events mà checkpoint đã vượt qua nhưng target chưa lưu.

### Bài 25. Data và checkpoint cùng PostgreSQL transaction có lợi gì?

**Đáp án:** hoặc cả hai commit, hoặc cả hai rollback.

### Bài 26. Broker offset ngoài PostgreSQL có atomic chung với DB transaction không?

**Đáp án:** không tự động. Thường dùng at-least-once, persist event trước ack và dedup bằng unique event ID.

### Bài 27. Watermark chỉ là timestamp có rủi ro gì?

**Đáp án:** records cùng timestamp hoặc late updates có thể bị bỏ sót; dùng composite cursor/tie-breaker hoặc CDC sequence.

### Bài 28. Atomic batch phù hợp khi nào?

**Đáp án:** batch vừa phải và nghiệp vụ yêu cầu tất cả hoặc không gì cả.

### Bài 29. Chunked apply cần thêm gì?

**Đáp án:** stable chunk identity, chunk ledger và commit progress/checkpoint cùng target changes.

### Bài 30. Vì sao không đánh dấu batch applied trước chunk cuối?

**Đáp án:** downstream có thể coi dữ liệu partial là hoàn chỉnh.

### Bài 31. FOR UPDATE SKIP LOCKED phù hợp với gì?

**Đáp án:** worker queue; mỗi worker bỏ qua batch row đang được worker khác khóa để claim việc khác.

### Bài 32. Lease hết hạn có nghĩa worker cũ chắc đã chết?

**Đáp án:** không. Worker có thể bị pause và thức dậy sau khi worker mới đã claim; cần fencing/ownership checks.

### Bài 33. Fencing token giúp gì?

**Đáp án:** token tăng theo mỗi lần claim; worker cũ có token thấp không được phép commit sau khi ownership đã đổi.

### Bài 34. Advisory lock có thay unique constraint không?

**Đáp án:** không. Advisory lock phối hợp workers; unique constraint vẫn bảo vệ integrity ở database.

### Bài 35. Count reconciliation đủ chứng minh hai datasets giống nhau?

**Đáp án:** không. Hai tập có cùng số rows vẫn có thể khác keys/values.

### Bài 36. Anti-join tìm được gì?

**Đáp án:** keys có trong nguồn nhưng thiếu target và keys target thừa so với source snapshot, khi scope/snapshot đầy đủ.

### Bài 37. Có thể delete mọi target row vắng mặt trong incremental batch?

**Đáp án:** không. Incremental batch chỉ chứa changes; absence không có nghĩa delete.

### Bài 38. Khi nào full snapshot được dùng để mark missing records deleted?

**Đáp án:** chỉ khi snapshot hoàn chỉnh, đúng scope, đã kiểm tra counts/checksum và không bị partial pages.

### Bài 39. Aggregate sum match có chứng minh records match?

**Đáp án:** không. Một record thiếu và một record thừa có thể triệt tiêu tổng.

### Bài 40. Vì sao checksum cần canonical representation?

**Đáp án:** để cùng logical data tạo cùng bytes/hash ở hai phía; timezone, NULL, decimals và field order phải có quy tắc.

### Bài 41. Hash nguyên file và hash logical records khác nhau?

**Đáp án:** file hash kiểm tra byte-for-byte; logical hash kiểm tra dữ liệu sau parse/normalize.

### Bài 42. pgcrypto.digest dùng để làm gì?

**Đáp án:** tính digest như SHA-256 trong PostgreSQL; extension phải được cài và canonical input phải giống nhau.

### Bài 43. Vì sao không so checksum bằng SUM(hash) đơn giản?

**Đáp án:** dễ collision và không phản ánh đúng key/order; dùng hash aggregation design có cấu trúc và phân vùng.

### Bài 44. applied và reconciled khác nhau?

**Đáp án:** applied nghĩa target merge đã commit; reconciled nghĩa các checks cần thiết đã đạt.

### Bài 45. Partial acceptance phải ghi gì?

**Đáp án:** valid/rejected counts, quarantine reasons, batch state và policy về khi nào được coi hoàn tất.

### Bài 46. Vì sao không dùng WHEN OTHERS THEN NULL?

**Đáp án:** có thể che lỗi và báo batch thành công dù rows chưa được apply.

### Bài 47. Outbox giải quyết khoảng trống nào?

**Đáp án:** ghi business data và publish intent trong cùng DB transaction; publisher có thể gửi lại, downstream vẫn cần dedup.

### Bài 48. Outbox bảo đảm email chỉ gửi đúng một lần?

**Đáp án:** không. Email provider/downstream cần idempotency hoặc delivery ledger; outbox chủ yếu bảo đảm intent không mất.

### Bài 49. Vì sao không gọi HTTP service trong transaction apply?

**Đáp án:** giữ locks/transaction lâu và không thể rollback side effect ngoài DB khi DB rollback.

### Bài 50. Export nhiều pages cần snapshot consistency vì sao?

**Đáp án:** dữ liệu có thể thay đổi giữa pages, khiến file chứa rows từ những thời điểm khác nhau.

### Bài 51. Keyset pagination khác OFFSET thế nào?

**Đáp án:** dùng last key đã đọc để tiếp tục, tránh scan/shift lớn; vẫn cần snapshot ổn định nếu yêu cầu dataset nhất quán.

### Bài 52. Export manifest nên chứa gì?

**Đáp án:** export ID, snapshot, filter/schema version, row count, file size, checksum và publish status.

### Bài 53. Vì sao cần schema_version của nguồn?

**Đáp án:** parser biết cách diễn giải payload, tránh đoán cấu trúc khi fields thay đổi.

### Bài 54. Raw payload giúp gì khi parser có bug?

**Đáp án:** có thể replay raw data bằng parser đã sửa mà không cần yêu cầu nguồn gửi lại nếu retention còn hiệu lực.

### Bài 55. Có nên lowercase mọi source ID?

**Đáp án:** không. Chỉ normalize theo contract; ID có thể case-sensitive.

### Bài 56. Numeric và timestamp cần canonicalization nào?

**Đáp án:** decimal scale/rounding/currency rõ; timestamp biểu diễn instant/timezone/precision thống nhất.

### Bài 57. Vì sao importer không nên chạy superuser?

**Đáp án:** một bug hoặc payload độc hại có thể gây hậu quả toàn database; dùng least-privilege roles.

### Bài 58. Raw/quarantine data có thể chứa gì nhạy cảm?

**Đáp án:** PII, tokens hoặc thông tin đối tác; cần access controls, retention và logging masking.

### Bài 59. Reconciliation mismatch nên xử lý thế nào?

**Đáp án:** phân loại missing/extra/version/hash/schema mismatch, giữ evidence, không đánh dấu reconciled hoặc xóa target hàng loạt trước khi xác minh.

### Bài 60. Lập checklist replay một batch an toàn

**Đáp án gợi ý:**

1. Dùng cùng source system và batch key.
2. So checksum; cùng key khác content phải conflict.
3. Xác nhận raw rows/chunks đã persist và row identity ổn định.
4. Validate/deduplicate cùng key/version/hash.
5. Kiểm tra same-version/different-payload conflicts.
6. Merge bằng unique constraints và version-aware UPSERT.
7. Apply tombstones cho delete events.
8. Commit target và progress/checkpoint cùng transaction/chunk.
9. Không ack source trước khi dữ liệu tương ứng durable.
10. Chạy count/key/version/checksum reconciliation.
11. Chỉ mark reconciled sau khi policy checks pass.
12. Dùng idempotency/outbox cho side effects bên ngoài.

## 50. Ma trận kiểm thử cho ingestion và export

| Scenario | Điều cần xác minh | Kết quả mong đợi |
| --- | --- | --- |
| Gửi cùng batch hai lần | Batch key/checksum | Một logical batch, không nhân đôi |
| Cùng batch key, checksum khác | Identity conflict | Bị từ chối/quarantine |
| Cùng row number, payload khác | Raw landing integrity | Conflict, không silently ignore |
| Cùng record/version/hash | Duplicate | Một logical target state |
| Cùng record/version, hash khác | Source conflict | Quarantine/incident |
| Version cũ đến sau version mới | Version gate | Target không bị lùi |
| Delete version cao, insert cũ đến sau | Tombstone | Không resurrect |
| Crash giữa COPY | Raw/staging transaction | Retry không duplicate |
| Crash sau commit trước response | Commit ambiguity | Re-read ledger, replay safe |
| Crash sau raw commit trước broker ack | At-least-once | Duplicate delivery được dedup |
| Chunk đã applied được gửi lại | Chunk ledger | Không áp lại sai |
| Hai workers claim cùng batch | Locks/lease/fencing | Một worker commit ownership hợp lệ |
| Lease hết hạn khi worker cũ chạy | Fencing | Worker cũ bị từ chối |
| Snapshot thiếu page | Manifest/count | Không chạy delete reconciliation |
| Incremental batch thiếu key | Semantics | Không coi absence là delete |
| Source/target count bằng nhưng key khác | Anti-join | Phát hiện missing/extra |
| Count khớp nhưng payload khác | Hash/version | Phát hiện mismatch |
| Parser schema cũ | schema_version | Dùng đúng parser hoặc quarantine |
| Decimal/timezone khác format | Canonicalization | So sánh đúng theo contract |
| Row lỗi một phần | Partial acceptance policy | Quarantine và accounting chính xác |
| Retry outbox publish | Event ID | Consumer idempotent |
| Export retry | Export ID/checksum | Logical file không đổi |
| Export trong lúc target thay đổi | Snapshot | File phản ánh một snapshot xác định |
| Network failure gần COMMIT | Outcome unknown | Reconcile theo key, không blind retry |

## 51. Checklist vận hành production

| Câu hỏi | Điều cần bảo đảm |
| --- | --- |
| Batch key có ổn định không? | Cùng logical batch nhận cùng identity |
| Record key có ổn định không? | Unique theo source/tenant scope |
| Có source version/ordering contract? | Out-of-order xử lý được |
| Có batch payload checksum? | Cùng key khác content bị phát hiện |
| Có raw landing? | Replay/audit evidence |
| Raw có giữ byte gốc khi cần? | File object + checksum/URI |
| Có staging typed? | Validate trước target |
| Có quarantine? | Lỗi không bị mất |
| Duplicate policy rõ? | Same hash vs conflict khác nhau |
| Có unique constraints? | Race-safe target identity |
| UPSERT có version gate? | Không overwrite bằng stale events |
| Delete có tombstone? | Không resurrect |
| Tombstone retention đủ? | Qua replay/late-event window |
| Checkpoint semantics rõ? | Raw persisted hay target applied |
| Data và checkpoint commit cùng transaction? | Khi cùng DB |
| External ack có at-least-once strategy? | Duplicate delivery an toàn |
| Batch atomic/chunked được chọn? | Theo volume/business semantics |
| Chunk có identity và ledger? | Resume đúng phạm vi |
| Worker concurrency có claim/lease? | Không xử lý trùng không kiểm soát |
| Lease có fencing/ownership checks? | Worker cũ không ghi tiếp |
| Reconciliation có count + keys + values? | Không chỉ COUNT |
| Checksum canonical? | Hai phía hash cùng representation |
| Full snapshot có completion manifest? | Không xóa từ snapshot partial |
| Incremental absence không bị coi là delete? | Có |
| Rejected/duplicate/stale accounting rõ? | Counts không double count |
| Outbox có unique event ID? | Publish retry an toàn |
| Downstream có idempotency? | Side effects không lặp |
| Export có snapshot/cursor ổn định? | File nhất quán |
| Export manifest có checksum/count? | Consumer verify được |
| Schema evolution có version? | Parser chọn đúng |
| Data normalization có contract? | NULL/decimal/timezone/Unicode rõ |
| Importer least privilege? | Không superuser |
| Raw/quarantine retention/access? | Đáp ứng privacy/compliance |
| Có failure injection tests? | Crash/duplicate/network/lock |
| Có metrics batch age/retry/lag? | Alert sớm |
| Có runbook mismatch? | Không tự xóa/sửa mù |
| Có backup/restore test? | Recovery không phụ thuộc replay duy nhất |
| Có audit người phê duyệt reprocessing? | Replay production có kiểm soát |

## 52. Tổng kết

Thiết kế nhập dữ liệu có thể chạy lại và đối soát là việc xây **identity, transaction boundaries, progress records và kiểm tra độc lập** cho toàn bộ pipeline.

Những nguyên tắc quan trọng:

1. **At-least-once delivery là thực tế phổ biến.** Hãy giả định file/message có thể được gửi lại.
2. **Batch key và record key phải ổn định.** Không dùng timestamp nhận hoặc row number làm business identity.
3. **Cùng batch key nhưng checksum khác là conflict.** Không ghi đè batch đã nhận một cách âm thầm.
4. **Giữ raw payload và staging.** Tách nhận dữ liệu, parse, validation và merge nghiệp vụ.
5. **Unique constraints là lớp bảo vệ cuối.** `ON CONFLICT` cần đi cùng payload/version checks.
6. **UPSERT phải tôn trọng source ordering.** Event cũ không được ghi đè version mới.
7. **Tombstone bảo vệ delete semantics.** Không để event cũ tái tạo record đã xóa.
8. **Checkpoint chỉ tiến sau khi dữ liệu tương ứng durable.** Khi có thể, commit data và checkpoint trong cùng transaction.
9. **Chunk identity phải ổn định.** Mỗi chunk progress và target changes commit cùng nhau.
10. **Leases không tự khóa worker cũ.** Dùng fencing/ownership checks và idempotent writes.
11. **Reconciliation không chỉ là row count.** Kiểm tra keys, versions, hashes, aggregates và source scope.
12. **Chỉ dùng absence để xóa khi có full snapshot hoàn chỉnh.** Incremental feed không chứng minh record đã biến mất.
13. **Same key/version với payload khác cần được xử lý như conflict.** Không chọn winner tùy tiện.
14. **Outbox nối DB transaction với publish intent.** Downstream vẫn cần dedup vì delivery có thể lặp.
15. **Export cần snapshot và manifest.** Retry cùng export identity phải tạo cùng logical dataset.
16. **Canonicalization phải rõ.** Timezone, numeric, NULL, Unicode và JSON semantics ảnh hưởng checksum.
17. **Partial acceptance phải có accounting.** Quarantine/rejected rows không được biến mất khỏi totals.
18. **Raw data cần retention và access control.** Khả năng replay không có nghĩa giữ dữ liệu nhạy cảm mãi mãi.
19. **Test crash sau commit trước response.** Đây là tình huống dễ gây duplicate khi retry mù.
20. **Chỉ mark batch reconciled khi invariant đã đạt.** `applied` và `reconciled` là hai trạng thái khác nhau.

Mẫu tư duy khi thiết kế một lần nhập:

```text
Identity: batch key + record key + source version
       |
Raw: persist payload + checksum
       |
Validate: typed staging + quarantine
       |
Deduplicate: same event vs conflicting payload
       |
Apply: unique constraint + version-aware UPSERT
       |
Progress: commit checkpoint with data
       |
Reconcile: counts + keys + versions + hashes
       |
Publish: outbox/idempotent downstream
       |
Replay: same identity, same result
```

**Câu hỏi review cuối cùng:** “Nếu process chết ngay trước commit, ngay sau commit, hoặc trước khi source nhận ACK; nếu cùng batch đến lần thứ ba; nếu event cũ đến sau event mới; và nếu snapshot thiếu một phần, hệ thống có thể tiếp tục mà không mất, nhân đôi hoặc xóa nhầm dữ liệu không?” Nếu câu trả lời được chứng minh bằng keys, constraints, transaction boundaries và reconciliation records, pipeline mới thật sự có thể chạy lại an toàn.
