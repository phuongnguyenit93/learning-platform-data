# Đồng bộ dữ liệu nhập bằng bảng trung gian và upsert

Khi nhận dữ liệu từ CSV, API, hệ thống đối tác hoặc database khác, ghi thẳng từng dòng vào bảng nghiệp vụ có thể làm hỏng cả lô vì một dòng sai, để dữ liệu cũ ghi đè dữ liệu mới, tạo bản ghi lặp khi retry hoặc xóa nhầm dữ liệu khi snapshot chưa tải đủ.

Một quy trình bền vững dùng **bảng trung gian (staging table)** để tiếp nhận, chuẩn hóa và kiểm tra dữ liệu trước khi công bố vào bảng đích. Sau validation, hệ thống dùng **upsert** để thêm bản ghi chưa có hoặc cập nhật bản ghi đã tồn tại theo khóa nghiệp vụ.

Bài thuộc module **Database SQL**, chương **Thực hành tổng hợp**, chủ đề **“Đồng bộ dữ liệu nhập bằng bảng trung gian và upsert”**. PostgreSQL được dùng làm ví dụ chính; các phần sau đối chiếu MySQL, SQL Server, Oracle và SQLite.

## 1. Luồng đồng bộ và vai trò staging

Luồng phổ biến:

1. Tạo batch/import job có idempotency key.
2. Nạp dữ liệu thô vào raw staging.
3. Parse, normalize và chuyển sang typed staging.
4. Validate kiểu dữ liệu, required fields, business rules và quyền truy cập.
5. Reject hoặc quarantine dòng lỗi; xử lý duplicate trong batch.
6. Upsert theo business key và source version.
7. Áp dụng delete semantics phù hợp với incremental hoặc full snapshot.
8. Reconcile counts/checksum.
9. Cập nhật checkpoint và batch status trong transaction phù hợp.

| Khu vực | Mục tiêu |
|---|---|
| Raw staging | Giữ nguyên dữ liệu nguồn để điều tra và replay |
| Typed staging | Dữ liệu đã parse, có trạng thái validation |
| Reject/quarantine | Lưu dòng lỗi cùng lý do |
| Target | Dữ liệu nghiệp vụ đã công bố |
| Batch metadata | Theo dõi trạng thái, số dòng, mode và checksum |

Staging cô lập lỗi, hỗ trợ retry và giảm thời gian giữ lock trên target. Tuy nhiên, staging không tự động làm import an toàn: vẫn cần unique constraint, version policy, validation và transaction. Raw data có thể chứa thông tin nhạy cảm nên cần quyền đọc và retention chặt chẽ.

## 2. Batch metadata và trạng thái

Mỗi file hoặc đợt dữ liệu cần batch ID và source batch key ổn định. Unique key ngăn cùng một lần nhập bị tạo hai batch khi client retry.

Ví dụ PostgreSQL:

```sql
CREATE TABLE import_batches (
    batch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_batch_key TEXT NOT NULL,
    import_mode TEXT NOT NULL
        CHECK (import_mode IN ('INCREMENTAL', 'FULL_SNAPSHOT')),
    status TEXT NOT NULL,
    expected_rows BIGINT,
    received_rows BIGINT NOT NULL DEFAULT 0,
    accepted_rows BIGINT NOT NULL DEFAULT 0,
    rejected_rows BIGINT NOT NULL DEFAULT 0,
    inserted_rows BIGINT NOT NULL DEFAULT 0,
    updated_rows BIGINT NOT NULL DEFAULT 0,
    stale_rows BIGINT NOT NULL DEFAULT 0,
    checksum TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    UNIQUE (source_name, source_batch_key)
);
```

Không dùng tên file đơn lẻ làm idempotency key nếu cùng tên có thể được tái sử dụng. Có thể kết hợp source identifier, file version, manifest ID hoặc checksum. Cùng batch key nhưng checksum khác là xung đột hợp đồng, không nên âm thầm coi là retry hợp lệ.

State machine gợi ý:

```text
RECEIVING -> LOADED -> VALIDATING -> VALIDATED -> APPLYING -> APPLIED
                      |                         |
                      +------> REJECTED          +------> RETRYABLE / FAILED
```

Trạng thái chỉ được chuyển khi điều kiện trước đó đã đạt. Nếu worker chết khi APPLYING, cần lease/heartbeat hoặc cơ chế xác định transaction đã commit chưa.

## 3. Thiết kế raw và typed staging

Raw staging thường lưu trường ngoài dưới dạng text để một giá trị sai định dạng không làm bulk load typed column thất bại:

```sql
CREATE TABLE raw_product_rows (
    batch_id BIGINT NOT NULL REFERENCES import_batches(batch_id),
    source_row_no BIGINT NOT NULL,
    raw_source_key TEXT,
    raw_sku TEXT,
    raw_product_name TEXT,
    raw_unit_price TEXT,
    raw_source_version TEXT,
    raw_operation TEXT,
    raw_payload TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, source_row_no)
);
```

Typed staging lưu dữ liệu đã parse:

```sql
CREATE TABLE staging_products (
    batch_id BIGINT NOT NULL REFERENCES import_batches(batch_id),
    source_row_no BIGINT NOT NULL,
    source_name TEXT NOT NULL,
    source_key TEXT,
    sku TEXT,
    product_name TEXT,
    unit_price NUMERIC(12, 2),
    source_version BIGINT,
    source_updated_at TIMESTAMPTZ,
    operation TEXT NOT NULL DEFAULT 'UPSERT'
        CHECK (operation IN ('UPSERT', 'DELETE')),
    validation_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (validation_status IN ('PENDING', 'VALID', 'REJECTED')),
    error_code TEXT,
    error_message TEXT,
    row_hash TEXT,
    PRIMARY KEY (batch_id, source_row_no)
);
```

Giữ batch_id và source_row_no để truy vết lỗi về dòng gốc. Chỉ dòng VALID mới được đưa vào target. Không cast mù từ raw text sang NUMERIC/TIMESTAMP: hãy parse từng trường, ghi lỗi theo dòng và chỉ nạp giá trị hợp lệ. Parser/schema version hữu ích khi cần replay sau khi sửa logic.

## 4. Business key và target constraint

Business key xác định hai dòng có đại diện cùng một thực thể hay không. Ví dụ:
- SKU duy nhất trong catalog.
- Cặp source_name và source_key nếu nhiều nguồn có external key riêng.
- Cặp tenant_id và external_customer_id nếu dữ liệu phân vùng theo tenant.

Ví dụ target:

```sql
CREATE TABLE catalog_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_key TEXT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    source_version BIGINT NOT NULL,
    source_updated_at TIMESTAMPTZ,
    row_hash TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_batch_id BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_key)
);
```

Unique constraint là nền tảng cho upsert. Index không unique không ngăn hai transaction tạo cùng key. Không chọn tên, mô tả hoặc địa chỉ làm business key nếu các trường đó có thể thay đổi.

Nếu nhiều nguồn cùng cập nhật một thực thể, cần quy định nguồn master, field ownership, source priority và mapping external key với internal ID. Không để “last import wins” thành chính sách ngầm.

## 5. Validation, reject và duplicate

Validation có nhiều lớp:

| Lớp | Ví dụ | Xử lý |
|---|---|---|
| Cấu trúc | Header, delimiter, encoding sai | Fail batch |
| Kiểu dữ liệu | Giá không parse được | Reject dòng |
| Required fields | Thiếu source key/SKU | Reject dòng |
| Miền giá trị | Giá âm | Reject dòng |
| Tham chiếu | Category không tồn tại | Reject hoặc map |
| Quyền | Source không được cập nhật tenant | Reject/fail batch |
| Chất lượng | Tỷ lệ reject vượt ngưỡng | Từ chối batch |

Ví dụ PostgreSQL:

```sql
UPDATE staging_products
SET validation_status = 'REJECTED',
    error_code = 'REQUIRED_FIELD',
    error_message = 'source_key and sku are required'
WHERE batch_id = 42
  AND validation_status = 'PENDING'
  AND (
      NULLIF(TRIM(source_key), '') IS NULL
      OR NULLIF(TRIM(sku), '') IS NULL
  );
```

Trong production, bind batch ID bằng driver; không nối dữ liệu đầu vào vào SQL. Oracle SQL coi chuỗi rỗng là NULL, trong khi một số DBMS khác phân biệt hai giá trị. Chuẩn hóa theo hợp đồng nguồn.

Một batch có thể chứa nhiều dòng cùng business key. Chính sách thường dùng: reject tất cả duplicate, chọn version cao nhất hoặc dùng event sequence nếu nguồn cam kết thứ tự. Không dựa vào thứ tự vật lý của query.

```sql
WITH ranked AS (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY source_name, source_key
               ORDER BY source_version DESC,
                        source_updated_at DESC NULLS LAST,
                        source_row_no DESC
           ) AS rn
    FROM staging_products AS s
    WHERE batch_id = 42
      AND validation_status = 'VALID'
)
SELECT *
FROM ranked
WHERE rn = 1;
```

source_row_no chỉ là tie-breaker kỹ thuật. Nếu hai payload cùng version nhưng khác nội dung, nên reject/quarantine conflict thay vì âm thầm chọn một dòng. Không deduplicate chỉ bằng MAX(version), vì nhiều dòng cùng version có thể cùng được chọn.

## 6. Upsert và version policy

Một policy phổ biến:

| Điều kiện | Hành động |
|---|---|
| Target chưa có key | INSERT |
| Incoming version lớn hơn target | UPDATE trường do nguồn sở hữu |
| Incoming version nhỏ hơn target | Bỏ qua stale row |
| Version bằng, hash giống | Replay/no-op |
| Version bằng, hash khác | Conflict cần điều tra |

PostgreSQL:

```sql
INSERT INTO catalog_products (
    source_name, source_key, sku, product_name,
    unit_price, source_version, row_hash
)
VALUES ('supplier-a', 'P-100', 'SKU-100', 'Keyboard', 55.00, 12, 'hash-12')
ON CONFLICT (source_name, source_key)
DO UPDATE SET
    sku = EXCLUDED.sku,
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    source_version = EXCLUDED.source_version,
    row_hash = EXCLUDED.row_hash,
    updated_at = CURRENT_TIMESTAMP
WHERE EXCLUDED.source_version > catalog_products.source_version;
```

EXCLUDED là dòng đề xuất insert. Điều kiện version ngăn batch cũ ghi đè bản mới. Nếu nguồn không có version, cân nhắc CDC sequence, LSN/binlog offset, event number, ETag hoặc revision token. Timestamp đơn lẻ có thể trùng, lệch đồng hồ hoặc đến muộn.

Chỉ cập nhật cột thuộc quyền sở hữu của nguồn. Không để import supplier ghi đè internal_note, created_by hoặc reviewed_at do ứng dụng quản lý. NULL cũng cần semantics rõ: NULL có thể có nghĩa xóa giá trị hoặc trường không được gửi. Dùng field-present flag/patch format nếu cần phân biệt; không dùng COALESCE nếu phải cho phép đặt giá trị thành NULL.

Row hash hữu ích khi canonicalization nhất quán về thứ tự field, decimal, timestamp, encoding và NULL/empty. Hash không thay unique key hoặc validation.

## 7. Incremental sync và full snapshot

**Incremental sync** chỉ gửi thay đổi kể từ lần trước. Key không xuất hiện không có nghĩa là bị xóa. Delete cần tombstone/event riêng có key và version.

**Full snapshot** gửi toàn bộ dữ liệu trong scope xác định tại một thời điểm. Chỉ được deactivate key vắng mặt sau khi:
- Nguồn xác nhận snapshot hoàn chỉnh.
- Expected row count/checksum khớp.
- Tất cả raw rows đã tải.
- Validation đạt policy.
- Scope source/tenant chính xác.
- Không có reject làm mất khả năng xác định key.

| Đặc điểm | Incremental | Full snapshot |
|---|---|---|
| Nội dung | Chỉ thay đổi | Toàn bộ scope |
| Key vắng mặt | Không có nghĩa xóa | Có thể là xóa khi complete |
| Delete | Tombstone/event | So sánh tập key/generation |
| Retry | Theo event/version | Theo snapshot key |

Ví dụ deactivate trong đúng source scope:

```sql
UPDATE catalog_products AS target
SET is_active = FALSE,
    updated_at = CURRENT_TIMESTAMP
WHERE target.source_name = 'supplier-a'
  AND target.is_active = TRUE
  AND target.last_seen_batch_id IS DISTINCT FROM 42;
```

Chỉ chạy câu lệnh này sau khi full snapshot complete và validated. Nếu một dòng snapshot bị reject do thiếu source_key, không biết key nào đã vắng mặt; mặc định an toàn là không deactivate. Soft delete thường dễ rollback và audit hơn hard delete. NOT IN có thể cho kết quả bất ngờ khi subquery chứa NULL; NOT EXISTS thường rõ hơn nhưng vẫn phải giới hạn scope.

## 8. Watermark, checkpoint và idempotency

Watermark ghi nhận vị trí đã xử lý: timestamp, event sequence, CDC log position, LSN/binlog offset hoặc snapshot generation. Không chỉ dùng MAX(updated_at) nếu có timestamp trùng hoặc event đến muộn. Dùng CDC sequence hoặc cursor có tie-breaker theo hợp đồng nguồn. Overlap window có thể giảm rủi ro nhưng cần upsert idempotent để xử lý replay.

Cập nhật checkpoint sau khi target apply thành công. Nếu checkpoint và target cùng database, cập nhật trong cùng transaction. Nếu khác database, cần outbox/protocol có thể replay.

Idempotency có nhiều lớp:
- Batch: unique source_name và source_batch_key.
- Row: unique business key ở target.
- Version: chỉ nhận version mới hơn.
- Event: event ID/sequence duy nhất.
- Side effect: outbox và consumer chống lặp.

Nếu worker chết sau khi upsert nhưng trước response, retry cùng batch phải đọc lại kết quả hoặc áp lại thao tác idempotent. Cập nhật target, checkpoint và batch status trong cùng transaction nếu cùng database. Nếu cần gửi message/gọi API, ghi outbox trong transaction và phát sau commit.

## 9. Bulk loading

| DBMS | Cơ chế | Lưu ý |
|---|---|---|
| PostgreSQL | COPY FROM STDIN | Driver có thể stream dữ liệu |
| MySQL | LOAD DATA LOCAL INFILE | Chỉ bật LOCAL INFILE có chủ đích |
| SQL Server | BULK INSERT, bcp, SqlBulkCopy | File phải được service truy cập |
| Oracle | SQL*Loader, external tables | Phù hợp tải lớn |
| SQLite | Prepared batch inserts | Gói insert trong transaction |

PostgreSQL:

```sql
COPY raw_product_rows (
    batch_id, source_row_no, raw_source_key, raw_sku, raw_unit_price
)
FROM STDIN WITH (FORMAT CSV, HEADER TRUE);
```

MySQL:

```sql
LOAD DATA LOCAL INFILE 'products.csv'
INTO TABLE raw_product_rows
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES;
```

SQL Server:

```sql
BULK INSERT dbo.raw_product_rows
FROM 'D:\imports\products.csv'
WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a');
```

Không ghép file path do người dùng cung cấp vào SQL. Xác thực file, giới hạn dung lượng và quyền truy cập trước khi nạp. Oracle có SQL*Loader/external tables; SQLite thường dùng prepared batch inserts trong một transaction.

## 10. Khác biệt upsert giữa DBMS

| DBMS | Cơ chế | Lưu ý |
|---|---|---|
| PostgreSQL | ON CONFLICT DO UPDATE | Chỉ rõ conflict target; dùng EXCLUDED |
| MySQL | ON DUPLICATE KEY UPDATE | Có thể conflict với bất kỳ unique key phù hợp |
| SQL Server | MERGE hoặc UPDATE + INSERT | Kiểm soát concurrency và unique constraint |
| Oracle | MERGE INTO ... USING | Source cần deduplicate |
| SQLite | ON CONFLICT DO UPDATE | Có từ SQLite 3.24 |

MySQL 8.0.19+ hỗ trợ row alias; VALUES(column) trong ON DUPLICATE KEY UPDATE bị deprecated từ 8.0.20. SQL Server MERGE cần kiểm thử theo phiên bản, trigger và concurrency; UPDATE rồi INSERT trong transaction cũng cần locking và unique constraint. Oracle MERGE không nên nhận nhiều source row cùng match một target row. SQLite chỉ có một writer tại một thời điểm.

## 11. Transaction, chunking và publish

Một transaction lớn giúp toàn batch commit/rollback nhưng có thể giữ lock lâu và tạo log lớn. Chunked apply giảm kích thước transaction nhưng người đọc có thể thấy dữ liệu cập nhật một phần. Cần checkpoint chunk, idempotent apply và không đánh dấu batch hoàn tất trước khi mọi chunk thành công.

Khi cần publish toàn snapshot nguyên tử, nạp dữ liệu vào generation mới, validate/reconcile rồi đổi active_generation_id trong transaction ngắn. Người đọc chỉ truy vấn generation active; generation cũ được giữ để rollback rồi mới dọn.

Một worker nên sở hữu batch tại một thời điểm. PostgreSQL có thể dùng SELECT FOR UPDATE hoặc FOR UPDATE SKIP LOCKED để claim job. Nếu APPLYING được commit trước khi apply, cần lease/heartbeat và recovery policy. Hai batch có thể cùng cập nhật một key; unique constraint ngăn duplicate nhưng source version quyết định bản nào thắng. Retry toàn transaction khi deadlock/serialization failure.

## 12. Reconciliation và kiểm thử

Theo dõi riêng received_rows, parsed_rows, accepted_rows, rejected_rows, unique_keys, inserted_rows, updated_rows, stale_rows, unchanged_rows, deactivated_rows và error_rows. Không kỳ vọng received = inserted + updated vì có reject, duplicate, stale và no-op. Định nghĩa rõ mỗi metric đếm dòng, key hay event.

| Tình huống | Kết quả mong đợi |
|---|---|
| Batch mới, mọi dòng hợp lệ | Upsert đúng, APPLIED |
| Retry cùng batch | Không duplicate, không side effect lặp |
| Duplicate key | Theo policy reject/winner |
| Version incoming cũ | Bỏ qua, giữ target mới |
| Cùng version, hash khác | Conflict/reject |
| Incremental thiếu key | Không deactivate |
| Full snapshot complete thiếu key | Deactivate đúng scope |
| Full snapshot partial | Không chạy delete |
| Crash trong transaction | Target và status rollback |
| Crash sau commit trước response | Retry đọc kết quả APPLIED |
| Hai worker claim cùng batch | Chỉ một worker sở hữu |

Test nhiều connection và dữ liệu ngoài scope để phát hiện race condition hoặc câu UPDATE/DELETE thiếu điều kiện.

## 13. Bảo vệ staging và lỗi thường gặp

- Import account chỉ ghi staging và đọc lookup cần thiết; apply account chỉ ghi cột target được phép.
- Không tin tenant_id/owner do payload tự khai báo.
- Bind mọi giá trị; không nối tên bảng, file path hoặc SQL fragment từ đầu vào.
- Giới hạn file, số dòng, độ dài trường và thời gian xử lý.
- Mask dữ liệu nhạy cảm trong log, áp dụng retention và audit.
- Không bulk load thẳng vào typed target.
- Không đánh dấu APPLIED trước commit.
- Không xóa key vắng mặt trong incremental sync.
- Không deactivate snapshot partial hoặc có reject khóa.
- Không ghi đè trường do ứng dụng/nguồn khác sở hữu.
- Không retry side effect không idempotent.
- Không dựa vào generated ID cục bộ làm khóa liên hệ thống.
- Không chỉ so tổng số dòng; cần key/checksum.
- Không chỉ test SQLite nếu production dùng server DBMS.
- Không xóa staging quá sớm, làm mất bằng chứng điều tra/replay.

## 14. Bài tập có lời giải

1. **Vì sao cần staging?** Tách tiếp nhận khỏi công bố; giữ raw input, validate, reject, deduplicate, retry và đối soát.
2. **Khi nào dùng persistent staging?** Khi import kéo dài qua nhiều worker/connection hoặc cần điều tra sau sự cố.
3. **Vì sao raw staging thường dùng TEXT?** Giá trị sai định dạng không làm bulk load typed column thất bại.
4. **Business key là gì?** Khóa nghiệp vụ ổn định xác định cùng thực thể, ví dụ source_name + source_key.
5. **Upsert cần constraint nào?** Unique/primary key hoặc unique index trên business key.
6. **Hai dòng cùng key trong batch?** Reject cả key hoặc chọn version mới nhất theo thứ tự nguồn có bảo đảm.
7. **Vì sao source_version quan trọng?** Ngăn batch/event cũ ghi đè trạng thái mới hơn.
8. **Cùng version, hash khác?** Conflict/reject hoặc xử lý theo policy được phê duyệt.
9. **PostgreSQL upsert?** INSERT ... ON CONFLICT DO UPDATE.
10. **MySQL upsert?** INSERT ... ON DUPLICATE KEY UPDATE.
11. **SQL Server upsert?** MERGE hoặc UPDATE rồi INSERT trong transaction có locking phù hợp.
12. **Oracle upsert?** MERGE INTO ... USING.
13. **SQLite hỗ trợ UPSERT từ khi nào?** SQLite 3.24.0.
14. **Incremental batch thiếu key có xóa không?** Không; vắng mặt không có nghĩa xóa.
15. **Khi nào full snapshot được deactivate?** Sau khi complete, đúng scope, count/checksum khớp và validation đạt.
16. **Tombstone là gì?** Sự kiện/bản ghi biểu thị key đã xóa, thường kèm version.
17. **Vì sao giữ tombstone?** Ngăn event cũ đến muộn làm bản ghi sống lại.
18. **Vì sao MAX(updated_at) chưa đủ?** Timestamp có thể trùng hoặc event đến muộn.
19. **Khi nào cập nhật checkpoint?** Sau khi target apply thành công, tốt nhất cùng transaction.
20. **Retry sau commit trước response?** Dùng cùng idempotency key và đọc lại kết quả batch cũ.
21. **Vì sao APPLIED cùng transaction target?** Tránh trạng thái batch không phản ánh dữ liệu đã commit.
22. **last_seen_batch_id dùng làm gì?** Đánh dấu key đã thấy trong full snapshot.
23. **Có cập nhật internal_note từ supplier?** Không nếu supplier không sở hữu trường.
24. **NULL luôn có nghĩa xóa?** Không; phân biệt absent với present-null.
25. **Vì sao canonicalize row hash?** Tránh cùng dữ liệu logic tạo hash khác do định dạng.
26. **Vì sao không dùng NOT IN khi có NULL?** Logic ba giá trị có thể làm anti-join sai; cân nhắc NOT EXISTS.
27. **Khi nào chunk batch?** Khi transaction quá lớn về log/lock/thời gian; cần checkpoint và idempotency.
28. **Snapshot partial phải làm gì?** Dừng publish, không deactivate.
29. **Vì sao test nhiều connection?** Phát hiện race, deadlock và claim trùng.
30. **Quy trình CSV an toàn?** Tạo batch, bulk load raw, đối chiếu manifest, parse/validate, deduplicate, upsert transaction, xử lý snapshot delete có điều kiện, reconcile, cập nhật status/checkpoint và giữ reject theo retention.

## 15. Checklist trước khi công bố batch

- [ ] Batch ID và source batch key ổn định, unique.
- [ ] Import mode là incremental hay full snapshot.
- [ ] Source/tenant scope được xác thực.
- [ ] Raw rows có source_row_no và payload truy vết được.
- [ ] Expected count/checksum đã đối chiếu.
- [ ] Kiểu dữ liệu, required fields, miền giá trị và reference đã kiểm tra.
- [ ] Duplicate key đã xử lý theo policy.
- [ ] Source version/event cursor hợp lệ.
- [ ] Conflict cùng version nhưng payload khác đã phát hiện.
- [ ] Upsert có unique target constraint.
- [ ] Chỉ cột nguồn sở hữu được cập nhật.
- [ ] NULL/absent semantics đã rõ.
- [ ] Delete/tombstone đúng mode.
- [ ] Full snapshot chỉ deactivate khi complete và validated.
- [ ] Apply, checkpoint và status có transaction phù hợp.
- [ ] Retry cùng batch không nhân đôi dữ liệu/side effect.
- [ ] Reconciliation đạt.
- [ ] Audit/outbox, retention và quyền truy cập đã cấu hình.
- [ ] Concurrency/deadlock/retry đã được kiểm thử trên DBMS production.

## 16. Kết luận

Đồng bộ dữ liệu nhập bằng staging và upsert là một pipeline có kiểm soát, không chỉ là một câu INSERT có nhánh UPDATE. Staging giữ dữ liệu nguồn và giúp validation diễn ra trước khi công bố. Business key cùng unique constraint xác định thực thể. Source version ngăn dữ liệu cũ ghi đè dữ liệu mới. Batch ID và idempotency key giúp retry an toàn. Incremental sync và full snapshot cần semantics xóa khác nhau. Transaction, checkpoint và reconciliation bảo đảm hệ thống chỉ báo hoàn tất khi dữ liệu đã được áp dụng đúng.

Một pipeline tốt có thể chạy lại, giải thích được vì sao một dòng được nhận hoặc từ chối, không để dữ liệu cũ ghi đè dữ liệu mới và không công bố snapshot chưa hoàn chỉnh.

## Tài liệu tham khảo

- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): upsert, conflict target và RETURNING.
- [PostgreSQL — COPY](https://www.postgresql.org/docs/current/sql-copy.html): bulk loading.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): locking và concurrency.
- [MySQL — INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html): upsert.
- [MySQL — LOAD DATA](https://dev.mysql.com/doc/refman/8.4/en/load-data.html): nạp dữ liệu file.
- [Microsoft Learn — MERGE](https://learn.microsoft.com/en-us/sql/t-sql/statements/merge-transact-sql): đồng bộ target/source.
- [Microsoft Learn — BULK INSERT](https://learn.microsoft.com/en-us/sql/t-sql/statements/bulk-insert-transact-sql): bulk import.
- [Oracle — MERGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html): conditional insert/update.
- [Oracle — SQL*Loader](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-sql-loader.html): bulk loading.
- [SQLite — UPSERT](https://www.sqlite.org/lang_upsert.html): ON CONFLICT DO UPDATE.
- [SQLite — Transactions](https://www.sqlite.org/lang_transaction.html): transaction và locking.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized query và dynamic SQL an toàn.

