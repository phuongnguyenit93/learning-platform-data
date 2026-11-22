# Ứng dụng ghi lịch sử thay đổi và kiểm chứng tính đúng đắn

Trong ứng dụng nghiệp vụ, biết **trạng thái hiện tại** thường chưa đủ. Khi một hạn mức tín dụng bị thay đổi, một đơn hàng chuyển từ `NEW` sang `PAID`, hay một hồ sơ bị xóa, người vận hành có thể cần trả lời: **Giá trị trước đó là gì? Giá trị mới là gì? Thao tác nào xảy ra? Khi nào? Do ai hoặc tác vụ nào yêu cầu? Thao tác đã commit hay rollback?**

Một giải pháp phổ biến trong PostgreSQL là dùng **trigger** để ghi một dòng lịch sử vào bảng audit cùng transaction với thay đổi trên bảng nguồn. Trigger quan sát `OLD`, `NEW`, `TG_OP` và có thể ghi snapshot `jsonb`. Cách này giúp quản lý lịch sử tập trung mà không phụ thuộc hoàn toàn vào việc mỗi endpoint của ứng dụng nhớ tự ghi audit.

Nhưng một audit trail đúng cần nhiều hơn một `INSERT INTO audit_log`: phải định nghĩa **sự kiện cần ghi**, **phạm vi bảo mật**, **độ chính xác của dữ liệu trước/sau**, **ngữ nghĩa transaction**, **thao tác có thể bỏ qua trigger**, **cách kiểm chứng với dữ liệu nguồn** và **giới hạn truy vết**. Đặc biệt, trigger audit transactional **không** phải một hệ thống lịch sử bất biến chống superuser sửa xóa và **không** lưu lại những transaction đã rollback.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **audit trail**, **history table**, **business event**, **CDC** và **temporal snapshot**.
2. Chọn `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW` để ghi lịch sử dữ liệu đã được sửa bởi statement.
3. Sử dụng `OLD`, `NEW`, `TG_OP`, `TG_TABLE_SCHEMA` và `TG_TABLE_NAME` trong trigger function.
4. Thiết kế bảng audit chứa khóa đối tượng, tenant, hành động, dữ liệu trước/sau, actor, transaction ID và thời gian.
5. Ghi `jsonb` trước/sau và kiểm tra chính xác các thay đổi của một hàng.
6. Tránh ghi sự kiện `UPDATE` không làm đổi giá trị thực tế khi nghiệp vụ cần.
7. Hiểu audit entry được commit/rollback **cùng transaction** với dữ liệu nguồn.
8. Phân biệt `BEFORE`, `AFTER`, row-level, statement-level và transition tables.
9. Nhận biết khác biệt giữa trigger và PostgreSQL `RULE`; hiểu các thao tác như `TRUNCATE`, DDL, replication có thể nằm ngoài row-audit.
10. Kiểm chứng bằng SQL assertions, đối soát snapshot, kiểm thử transaction, concurrency và quyền truy cập.
11. Thiết kế quyền, `SECURITY DEFINER`, `search_path`, RLS, log bảo mật và chính sách retention.
12. Áp dụng từ Java/JDBC/Spring với transaction context và actor metadata đáng tin.

> **Môi trường:** Ví dụ chạy trên PostgreSQL hiện đại, dùng `plpgsql`, `jsonb`, row-level triggers và transaction bình thường. SQL tạo/sửa/xóa dữ liệu chỉ dành cho **database thực hành**. Người học nên chạy từng khối theo thứ tự. Những ví dụ liên quan quyền, replication, event triggers hoặc table partitioning cần kiểm tra phiên bản và quyền máy chủ trước khi áp dụng production.

## 2. Bài toán: cần nhớ những gì?

Giả sử bảng `accounts` chứa:

| account_id | tenant_id | account_code | display_name | credit_limit | status |
|---:|---:|---|---|---:|---|
| 1001 | 10 | AC-001 | Công ty An Bình | 500000 | ACTIVE |
| 2001 | 20 | AC-002 | Công ty Minh Hà | 800000 | ACTIVE |

Người dùng chỉnh hạn mức account 1001 từ 500000 lên 700000. Bảng nguồn chỉ chứa **giá trị mới**. Nếu không có cơ chế lịch sử, bạn khó biết hạn mức cũ và khi nào nó đổi.

Một hàng audit mong muốn:

```text
audit_id      = 3
account_id    = 1001
tenant_id     = 10
operation     = UPDATE
actor_id      = editor-42
old_row       = {"credit_limit": 500000, ...}
new_row       = {"credit_limit": 700000, ...}
occurred_at   = 2026-...+00
transaction_id= ...
```

Những dữ liệu trên chỉ là **ví dụ minh họa**; sequence ID, thời gian và transaction ID thực tế do server sinh.

### Những câu hỏi cần xác định trước khi code

- Có ghi mọi thay đổi hay chỉ cột nghiệp vụ?
- UPDATE không làm thay đổi giá trị có cần audit không?
- Có ghi INSERT và DELETE không?
- Có cần biết actor ứng dụng hoặc chỉ role database?
- Dữ liệu có PII/secret nào không được sao chép vào history?
- Ai được đọc, xóa, cập nhật, purge audit?
- Cần tra cứu lịch sử theo thời điểm hay dựng lại trạng thái?
- Có cần chứng cứ độc lập ngay cả khi transaction rollback hoặc DB superuser xóa dấu vết?

Không phải mọi ứng dụng cần cùng một cấp độ audit.

## 3. Audit trail khác history và event sourcing

| Cơ chế | Mục đích chính | Điểm cần nhớ |
|---|---|---|
| Row audit trigger | Ghi DML trước/sau thay đổi bảng | Transactional, gắn với thao tác nguồn |
| History/version table | Giữ nhiều phiên bản dữ liệu có cấu trúc | Có thể hỗ trợ temporal query |
| Business event | Diễn đạt sự kiện nghiệp vụ như `OrderPaid` | Không đồng nhất với mọi SQL UPDATE |
| Transactional outbox | Ghi sự kiện dự định gửi ra hệ khác trong cùng transaction | Cần publisher/consumer idempotent |
| Logical decoding/CDC | Đọc thay đổi từ WAL theo cơ chế replication | Có thể bao phủ workload khác trigger, cần vận hành slot/lag |
| PostgreSQL server logs / pgAudit | Theo dõi hoạt động/truy vấn ở cấp database | Khác với row snapshots có thể query |
| External tamper-evident audit | Chứng cứ được lưu/neo ngoài DB nguồn | Dùng khi cần chống sửa đổi bởi người có quyền cao |

Row audit phù hợp khi muốn **truy vấn ai sửa hàng nào, từ giá trị nào sang giá trị nào** trong phạm vi DML được theo dõi.

Audit trigger **không** đồng nghĩa event sourcing: trong event sourcing, events là nguồn chuẩn để xây state; với row audit, bảng nghiệp vụ thường vẫn là **source of truth**, còn audit là dữ liệu dẫn xuất được ghi cùng transaction.

## 4. Trigger và RULE: chọn đúng cơ chế

Trong PostgreSQL, **trigger** chạy khi một sự kiện trên table/view xảy ra theo timing và level được khai báo. **RULE** thuộc cơ chế query rewrite: có thể biến đổi câu query trước giai đoạn execution.

### Dùng trigger để audit

- Có `OLD`/`NEW` tương ứng hàng bị thay đổi.
- Có `TG_OP` phân biệt INSERT, UPDATE, DELETE.
- Có thể ghi một sự kiện cho mỗi hàng đã thao tác.
- Có thể dùng `AFTER` để quan sát row cuối sau các `BEFORE` triggers.
- Audit DML được thực hiện trong cùng transaction.

### Vì sao thường không dùng RULE để audit row changes?

`RULE` hoạt động ở tầng rewrite, không phải hook thực thi “sau khi hàng đã đổi” với đối tượng `OLD`/`NEW` giống row-level trigger. Các rewrite rules có thể làm semantics phức tạp, đặc biệt với nhiều hàng, `RETURNING`, side effects và views. PostgreSQL thường khuyến nghị dùng trigger cho phần lớn tác vụ ghi log/kiểm tra per-row, trừ những trường hợp cụ thể như view rewrite.

**Kết luận:** Khi yêu cầu là **ghi lịch sử dữ liệu đã thay đổi**, chọn trigger trước, không dùng RULE chỉ vì tên chương bao gồm “Trigger và luật”.

## 5. BEFORE và AFTER cho audit

| Timing | Khi nào chạy | Dùng cho |
|---|---|---|
| `BEFORE INSERT/UPDATE` | Trước khi ghi một row | Chuẩn hóa giá trị, validation, kiểm soát thay đổi `NEW` |
| `AFTER INSERT/UPDATE/DELETE` | Sau thao tác row trong statement | Ghi lịch sử của giá trị đã áp dụng ở tầng statement |
| `INSTEAD OF` trên view | Thay thế thao tác trên view | Cập nhật nguồn qua view |
| `AFTER ... FOR EACH STATEMENT` | Một lần cho statement | Log thống kê hoặc thao tác theo transition tables |

### Vì sao ưu tiên AFTER ROW?

Nếu có một trigger `BEFORE UPDATE` tự chuẩn hóa tên hoặc đặt timestamp, audit `AFTER UPDATE` quan sát `NEW` đã được các BEFORE triggers biến đổi. Điều này gần với **row state mà statement đã ghi** hơn.

Tuy nhiên, AFTER không có nghĩa thay đổi chắc chắn **đã commit**; nếu transaction rollback, thay đổi nguồn và audit entry transactional sẽ cùng bị rollback.

### RETURN trong AFTER trigger

Giá trị trả về của row-level `AFTER` trigger không được dùng để thay đổi hàng nguồn. Trong ví dụ sẽ `RETURN NULL` để biểu đạt không có row replacement; đó **không** phải lệnh bỏ qua hàng của DML chính.

## 6. Row-level và statement-level

Một SQL:

```sql
UPDATE accounts
SET status = 'SUSPENDED'
WHERE tenant_id = 10;
```

có thể cập nhật 100 hàng.

**FOR EACH ROW**: trigger chạy cho từng row được tác động, có `OLD`/`NEW` cụ thể.

**FOR EACH STATEMENT**: trigger chạy một lần theo statement, kể cả khi statement tác động 0 rows; thông thường không có `OLD/NEW` per-row. Với `AFTER` statement trigger và cú pháp `REFERENCING OLD TABLE/NEW TABLE` thích hợp, có thể truy cập các **transition relations** chứa tập hàng cũ/mới.

### Chọn mô hình nào?

- Muốn snapshot từng row: `AFTER ... FOR EACH ROW` đơn giản.
- Muốn xử lý tập bằng SQL set-based: có thể dùng `AFTER ... FOR EACH STATEMENT` + transition tables.
- Muốn biết câu lệnh được thử ngay cả khi không ảnh hưởng rows: statement-level log có thể khác row audit.

Hai cơ chế có chi phí, ngữ nghĩa và giới hạn khác nhau; cần kiểm thử cả các statement tác động 0 rows.

## 7. Chuẩn bị schema lab

Chạy lần đầu trên database thực hành:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_audit;

CREATE TABLE lesson_audit.accounts (
    account_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    account_code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    credit_limit NUMERIC(14,2) NOT NULL
        CHECK (credit_limit >= 0),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (tenant_id, account_code)
);
```

`GENERATED BY DEFAULT AS IDENTITY` cho phép truyền ID xác định trong các ví dụ; môi trường production có thể chọn `GENERATED ALWAYS` hoặc khóa khác phù hợp.

### Vì sao dùng tenant_id?

Để minh họa rằng lịch sử cũng phải có **phạm vi tenant**, không phải “ai có SELECT audit đều xem được tất cả”. Mỗi hàng nguồn có tenant_id; audit sẽ lưu tenant của sự kiện tương ứng.

## 8. Bảng lịch sử dùng JSONB snapshots

```sql
CREATE TABLE lesson_audit.account_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    operation TEXT NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    old_row JSONB,
    new_row JSONB,
    actor_id TEXT,
    transaction_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        (operation = 'INSERT'
         AND old_row IS NULL AND new_row IS NOT NULL)
        OR
        (operation = 'UPDATE'
         AND old_row IS NOT NULL AND new_row IS NOT NULL)
        OR
        (operation = 'DELETE'
         AND old_row IS NOT NULL AND new_row IS NULL)
    )
);

CREATE INDEX ix_account_audit_tenant_account_event
ON lesson_audit.account_audit (
    tenant_id,
    account_id,
    audit_id DESC
);

CREATE INDEX ix_account_audit_occurred
ON lesson_audit.account_audit (occurred_at DESC);
```

### Vì sao tách audit_id và account_id?

`account_id` là **khóa business entity**, có thể xuất hiện qua nhiều phiên bản lịch sử.

`audit_id` là **khóa riêng của sự kiện audit**. Dùng identity/sequence để phân biệt các log entries, không phải bản sao ID nguồn.

### Vì sao không tạo FK account_audit.account_id → accounts?

Nếu nguồn bị DELETE, bảng audit vẫn cần giữ snapshot lịch sử. Một FK trực tiếp yêu cầu row nguồn còn tồn tại có thể cản DELETE hoặc khiến cascade phá lịch sử. Có thể chọn thiết kế tham chiếu khác, nhưng cần chủ động không để lifecycle của nguồn xóa mất log.

### Vì sao dùng JSONB?

`to_jsonb(OLD)` và `to_jsonb(NEW)` lưu snapshot các cột mà trigger được triển khai trên row. Khi schema nguồn thêm cột, snapshot mới có thể chứa field mới mà không cần thêm từng cột vào audit table.

Đổi lại, JSONB không thay thế schema typed cho mọi mục đích analytics; audit table sẽ tăng kích thước nhanh nếu lưu nhiều cột lớn hoặc nhạy cảm.

## 9. Ngữ nghĩa metadata: thời gian và transaction ID

Các trường:

- `occurred_at`: lấy `clock_timestamp()` khi trigger ghi sự kiện, phản ánh đồng hồ tại thời điểm gọi.
- `transaction_id`: dùng `txid_current()` cho mã transaction ở dạng bigint theo cơ chế PostgreSQL.
- `actor_id`: minh họa một context mà application đặt qua `current_setting('app.actor_id', true)`.

### Không nhầm ba loại timestamp

```sql
SELECT
    transaction_timestamp() AS transaction_started,
    statement_timestamp() AS statement_started,
    clock_timestamp() AS wall_clock_now;
```

| Hàm | Ý nghĩa |
|---|---|
| `now()` / `transaction_timestamp()` | Cùng giá trị bắt đầu transaction trong transaction hiện tại |
| `statement_timestamp()` | Thời điểm bắt đầu statement hiện tại |
| `clock_timestamp()` | Thời gian thực tại lần gọi, có thể khác trong cùng statement |

Lịch sử dùng `clock_timestamp` để dễ quan sát nhiều sự kiện trong một transaction, **nhưng nó không phải commit timestamp đáng tin tuyệt đối**. `occurred_at` có thể sớm hơn commit, và đồng hồ/độ phân giải không bảo đảm thứ tự commit giữa transactions.

### Sequence ID không phải thứ tự commit toàn cục

Sequence/identity cấp số ngoài cơ chế rollback thông thường; số có thể bị bỏ trống hoặc được cấp trước nhưng transaction commit sau. `audit_id DESC` hữu ích để xem lịch sử trong nhiều tình huống, song **không chứng minh thứ tự commit toàn cục** khi có transaction đồng thời.

## 10. Trigger function ghi lịch sử

```sql
CREATE OR REPLACE FUNCTION lesson_audit.capture_account_changes()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_account_id BIGINT;
    v_tenant_id BIGINT;
    v_old JSONB;
    v_new JSONB;
    v_actor TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_account_id := NEW.account_id;
        v_tenant_id := NEW.tenant_id;
        v_old := NULL;
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'UPDATE' THEN
        v_account_id := NEW.account_id;
        v_tenant_id := NEW.tenant_id;
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);

        -- Tránh tạo audit khi cả row không đổi giá trị.
        IF v_old IS NOT DISTINCT FROM v_new THEN
            RETURN NULL;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        v_account_id := OLD.account_id;
        v_tenant_id := OLD.tenant_id;
        v_old := to_jsonb(OLD);
        v_new := NULL;
    ELSE
        RAISE EXCEPTION 'Unsupported trigger operation: %', TG_OP;
    END IF;

    v_actor := NULLIF(
        current_setting('app.actor_id', true),
        ''
    );

    INSERT INTO lesson_audit.account_audit (
        account_id,
        tenant_id,
        operation,
        old_row,
        new_row,
        actor_id,
        transaction_id,
        occurred_at
    )
    VALUES (
        v_account_id,
        v_tenant_id,
        TG_OP,
        v_old,
        v_new,
        v_actor,
        txid_current(),
        clock_timestamp()
    );

    -- Kết quả trả về của AFTER ROW trigger bị bỏ qua.
    RETURN NULL;
END;
$$;
```

### Tại sao dùng SECURITY DEFINER?

Mục tiêu của ví dụ là cho role ứng dụng sửa `accounts` mà **không có quyền INSERT trực tiếp** vào `account_audit`. Trigger function được chủ sở hữu đáng tin thực thi với quyền phù hợp để ghi audit.

Đây **không phải** công thức bảo mật tự động: owner phải được kiểm soát, không có quyền thừa; `search_path` và các object references phải an toàn; quyền EXECUTE/DDL và quản trị schema phải được thiết kế đúng. Trong môi trường lab dùng role có quyền tạo các objects; khi triển khai production, cần chủ động quản lý role owner và GRANT/REVOKE.

## 11. Đính trigger vào bảng nguồn

```sql
CREATE TRIGGER trg_accounts_audit
AFTER INSERT OR UPDATE OR DELETE
ON lesson_audit.accounts
FOR EACH ROW
EXECUTE FUNCTION lesson_audit.capture_account_changes();
```

### Đọc từng phần

- `AFTER`: chạy sau thao tác row ở mức statement.
- `INSERT OR UPDATE OR DELETE`: ba sự kiện DML được theo dõi.
- `FOR EACH ROW`: mỗi hàng thay đổi có một lần trigger invocation.
- `EXECUTE FUNCTION`: gọi PL/pgSQL trigger function; không tự truyền `OLD` và `NEW` qua tham số thường.

Trigger function đọc các biến đặc biệt:

```text
TG_OP            'INSERT' | 'UPDATE' | 'DELETE'
TG_TABLE_SCHEMA  tên schema của bảng kích hoạt
TG_TABLE_NAME    tên bảng kích hoạt
OLD              row trước UPDATE/DELETE
NEW              row sau INSERT/UPDATE
```

Không tự tham chiếu `OLD.column` trong nhánh INSERT hoặc `NEW.column` trong nhánh DELETE; chúng không đại diện một hàng hợp lệ ở hai trường hợp ấy.

## 12. Chèn dữ liệu đầu tiên và quan sát lịch sử

```sql
BEGIN;

SELECT set_config('app.actor_id', 'seed-job', true);

INSERT INTO lesson_audit.accounts (
    account_id,
    tenant_id,
    account_code,
    display_name,
    credit_limit,
    status
)
VALUES
    (
        1001, 10, 'AC-001',
        'Công ty An Bình',
        500000.00, 'ACTIVE'
    ),
    (
        2001, 20, 'AC-002',
        'Công ty Minh Hà',
        800000.00, 'ACTIVE'
    );

COMMIT;
```

`set_config(..., true)` đặt cấu hình cục bộ cho transaction hiện tại; ở đây `app.actor_id` sẽ phục vụ metadata audit.

Xem:

```sql
SELECT
    audit_id,
    tenant_id,
    account_id,
    operation,
    actor_id,
    old_row,
    new_row
FROM lesson_audit.account_audit
ORDER BY audit_id;
```

Kỳ vọng có **hai sự kiện INSERT**, mỗi sự kiện có `old_row IS NULL` và `new_row` chứa snapshot của row vừa chèn.

### Điều quan trọng về actor_id

`app.actor_id` là **custom session setting mà ứng dụng có thể đặt**; không phải một danh tính chống giả mạo do PostgreSQL tự xác thực. Nếu untrusted client được phép chạy SQL hoặc `SET`, họ có thể thay đổi giá trị ấy. Không dùng custom setting chưa được kiểm soát làm **bằng chứng pháp lý rằng chính user đó thực hiện hành động**.

## 13. UPDATE: ghi ảnh trước và sau

```sql
BEGIN;

SELECT set_config('app.actor_id', 'editor-42', true);

UPDATE lesson_audit.accounts
SET credit_limit = 700000.00,
    updated_at = clock_timestamp()
WHERE tenant_id = 10
  AND account_id = 1001;

COMMIT;
```

Truy vấn lịch sử:

```sql
SELECT
    audit_id,
    operation,
    actor_id,
    old_row ->> 'credit_limit' AS old_limit,
    new_row ->> 'credit_limit' AS new_limit,
    occurred_at
FROM lesson_audit.account_audit
WHERE tenant_id = 10
  AND account_id = 1001
ORDER BY audit_id;
```

Sự kiện mới có operation `UPDATE`, `old_row` chứa hạn mức 500000 và `new_row` chứa hạn mức 700000, cùng các fields khác của row.

### Vì sao lưu cả hai snapshot?

Nếu chỉ lưu `new_row`, một truy vấn lịch sử phải tìm phiên bản trước ở event khác; khó hơn khi có dữ liệu thiếu log, schema đổi hoặc sự kiện đầu tiên là UPDATE. Lưu **old + new** đơn giản hóa điều tra và đối soát, đổi lại storage/WAL lớn hơn.

## 14. DELETE vẫn cần giữ khóa và snapshot cũ

```sql
BEGIN;

SELECT set_config('app.actor_id', 'admin-17', true);

DELETE FROM lesson_audit.accounts
WHERE tenant_id = 20
  AND account_id = 2001;

COMMIT;
```

Sau DELETE, `accounts` không còn hàng 2001, nhưng bảng audit sẽ có sự kiện:

```text
operation = DELETE
old_row   = {... account_id: 2001, ...}
new_row   = NULL
```

Xem:

```sql
SELECT
    audit_id,
    operation,
    old_row ->> 'display_name' AS deleted_name,
    new_row
FROM lesson_audit.account_audit
WHERE account_id = 2001
ORDER BY audit_id;
```

Vì không ràng buộc FK audit → accounts, lịch sử không bị ngăn khi hàng nguồn bị xóa. Đây là một **quyết định schema có chủ đích**, không có nghĩa audit được phép có các `account_id` vô hạn không hợp lệ; trigger và việc giám sát đảm nhiệm tính liên hệ với nguồn.

## 15. Không ghi UPDATE không có thay đổi

Trong trigger:

```sql
IF v_old IS NOT DISTINCT FROM v_new THEN
    RETURN NULL;
END IF;
```

được đặt sau khi chuyển `OLD` và `NEW` thành JSONB. Nếu toàn bộ fields bằng nhau, trigger không chèn event audit.

Thử:

```sql
UPDATE lesson_audit.accounts
SET status = status
WHERE tenant_id = 10
  AND account_id = 1001;
```

Giả sử không có trigger khác tự thay đổi timestamp hoặc column, row snapshots bằng nhau nên **không sinh sự kiện audit mới**.

### Đó là quy tắc nghiệp vụ, không phải chân lý duy nhất

Một số hệ thống muốn ghi cả **attempted update** ngay cả khi giá trị không đổi. Khi đó không nên bỏ event `UPDATE` dựa trên equality. Ngược lại, với nhu cầu ghi **thay đổi trạng thái thực**, bỏ no-op giúp giảm noise.

Đừng viết `OLD IS DISTINCT FROM NEW` mà không cân nhắc những cột kỹ thuật luôn thay đổi như `updated_at` hay version counter. Chúng có thể khiến update nghiệp vụ không đổi vẫn tạo audit.

## 16. Kiểm soát cột khóa bất biến

Các ví dụ audit dựa vào `account_id` và `tenant_id` để truy vết một thực thể. Nếu người dùng sửa chúng, một sự kiện UPDATE có thể mang khóa mới trong metadata và khó đối soát với lịch sử cũ.

Có thể ngăn thay đổi khóa:

```sql
CREATE OR REPLACE FUNCTION lesson_audit.guard_account_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.account_id IS DISTINCT FROM OLD.account_id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION
            'account_id and tenant_id are immutable';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_accounts_guard_identity
BEFORE UPDATE
ON lesson_audit.accounts
FOR EACH ROW
EXECUTE FUNCTION lesson_audit.guard_account_identity();
```

### Vì sao dùng BEFORE?

Đây là **validation** trước khi ghi hàng. Nếu một UPDATE cố sửa khóa, exception ngăn thay đổi trước khi AFTER audit trigger phải xử lý một thực thể “chuyển ID”.

Không phải mọi khóa business đều bắt buộc bất biến; nếu nghiệp vụ cho đổi `account_code`, log trước/sau đã có thể ghi biến đổi đó. Nhưng **primary key/tenant key** thường nên được xem là identity ổn định hoặc có cơ chế migration/merge riêng.

## 17. Điều gì xảy ra khi transaction ROLLBACK?

Audit row được chèn bằng trigger **cùng transaction** với thay đổi nguồn. Thử:

```sql
BEGIN;

SELECT set_config('app.actor_id', 'rollback-test', true);

UPDATE lesson_audit.accounts
SET credit_limit = credit_limit + 12345.00
WHERE tenant_id = 10
  AND account_id = 1001;

SELECT credit_limit
FROM lesson_audit.accounts
WHERE account_id = 1001;

SELECT
    audit_id,
    actor_id,
    operation
FROM lesson_audit.account_audit
WHERE actor_id = 'rollback-test';

ROLLBACK;
```

Sau ROLLBACK:

```sql
SELECT credit_limit
FROM lesson_audit.accounts
WHERE account_id = 1001;

SELECT count(*) AS audit_events_after_rollback
FROM lesson_audit.account_audit
WHERE actor_id = 'rollback-test';
```

**Kỳ vọng:** Hạn mức nguồn trở lại giá trị đã commit trước test; `audit_events_after_rollback = 0` nếu không có sự kiện khác cùng actor ID đã commit.

### Hệ quả quan trọng

Row audit trigger ghi lại **những thay đổi đã commit**, không phải nhật ký của mọi thao tác bị thử rồi rollback. Nếu cần ghi cả những lần cố xóa/sửa thất bại hoặc cuộc gọi bị từ chối, cần một lớp audit độc lập với transaction nguồn, ví dụ logging an toàn bên ngoài, không chỉ một bảng cùng database transaction.

## 18. Trigger failure làm statement thất bại

Giả sử audit function không thể INSERT audit row do thiếu quyền hoặc vi phạm constraint:

```text
UPDATE accounts
  └── AFTER UPDATE trigger
        └── INSERT account_audit → ERROR
              └── statement/transaction báo lỗi
```

PostgreSQL không tự bỏ qua lỗi của trigger rồi commit bảng nguồn thành công. Nếu lỗi không được xử lý, DML sẽ thất bại và các thay đổi trong statement bị rollback theo semantics transaction.

### Lợi ích

Đối với nghiệp vụ cần **không bao giờ commit thay đổi nguồn nếu thiếu audit**, cơ chế cùng transaction là lựa chọn mạnh.

### Đổi lại

Nếu bảng audit đầy disk, khóa bị tranh chấp hoặc function bị lỗi, thao tác nghiệp vụ cũng có thể bị chặn. Đó là trade-off giữa tính nhất quán và availability; cần giám sát và capacity planning.

## 19. BEFORE trigger có thể đổi NEW trước audit

Giả sử thêm một trigger chuẩn hóa `display_name`:

```sql
CREATE OR REPLACE FUNCTION lesson_audit.trim_display_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.display_name := btrim(NEW.display_name);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_accounts_trim_name
BEFORE INSERT OR UPDATE
ON lesson_audit.accounts
FOR EACH ROW
EXECUTE FUNCTION lesson_audit.trim_display_name();
```

Thử:

```sql
UPDATE lesson_audit.accounts
SET display_name = '  Công ty An Bình  '
WHERE tenant_id = 10
  AND account_id = 1001;
```

BEFORE trigger trim text; AFTER audit trigger quan sát `NEW.display_name` đã được chuẩn hóa. Vì tên gốc vốn là “Công ty An Bình”, trạng thái cuối có thể không thay đổi, nên **trigger audit no-op sẽ bỏ qua** nếu các cột khác giữ nguyên.

### Thứ tự nhiều triggers

Với nhiều triggers cùng loại/timing/event trên cùng bảng, PostgreSQL có quy tắc thứ tự kích hoạt theo **tên trigger**. Nhưng đừng phụ thuộc vào tên trigger để che quan hệ nghiệp vụ khó hiểu; nếu cần thứ tự chuẩn hóa, validate và audit rõ ràng, nên thiết kế/test theo kết quả mong muốn.

## 20. Thay đổi kỹ thuật và thay đổi nghiệp vụ

Nếu `updated_at` luôn được cập nhật khi có một câu UPDATE, dù các trường nghiệp vụ giống nhau:

```sql
UPDATE lesson_audit.accounts
SET updated_at = clock_timestamp()
WHERE account_id = 1001;
```

thì `to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW)` thường đúng vì timestamp thay đổi, và audit ghi event.

### Ba chiến lược

**Ghi mọi thay đổi column:** phù hợp khi cần điều tra mọi giá trị row, kể cả updated_at.

**Chỉ ghi thay đổi business fields:** so sánh một tập cột cụ thể, bỏ updated_at/technical version.

**Ghi cả business + technical với classification:** thêm `change_kind` hoặc `changed_fields` để phân tích.

### Ví dụ so sánh business fields

```sql
IF (OLD.display_name,
    OLD.credit_limit,
    OLD.status,
    OLD.account_code)
   IS NOT DISTINCT FROM
   (NEW.display_name,
    NEW.credit_limit,
    NEW.status,
    NEW.account_code) THEN
    RETURN NULL;
END IF;
```

Đây là đoạn minh họa **đặt trong nhánh UPDATE của trigger**, không chạy độc lập. Nếu schema đổi, danh sách business columns phải được xem xét lại.

## 21. Từ audit row đến danh sách thay đổi các cột

Mỗi UPDATE snapshot chứa JSONB trước và sau. Có thể hiển thị những keys có giá trị khác nhau bằng cách biến mỗi JSONB object thành các hàng `(key,value)` và đối chiếu bằng `FULL JOIN` trong một subquery `LATERAL`:

```sql
SELECT
    a.audit_id,
    d.field_name,
    d.before_value,
    d.after_value
FROM lesson_audit.account_audit AS a
CROSS JOIN LATERAL (
    SELECT
        COALESCE(o.key, n.key) AS field_name,
        o.value AS before_value,
        n.value AS after_value
    FROM jsonb_each(a.old_row) AS o(key, value)
    FULL JOIN jsonb_each(a.new_row) AS n(key, value)
      USING (key)
    WHERE o.value IS DISTINCT FROM n.value
) AS d
WHERE a.operation = 'UPDATE'
  AND a.account_id = 1001
ORDER BY a.audit_id, d.field_name;
```

Ở đây trường `field_name` dùng từ cả hai phía; nếu key chỉ có ở một snapshot, giá trị phía thiếu sẽ là SQL NULL.

### JSON null khác key không tồn tại

Trong JSONB, giá trị `null` bên trong một object khác với không có key. `jsonb_each` trả JSON null dưới dạng JSONB value, còn khi key thiếu ở phía JOIN, giá trị tương ứng là SQL NULL. Khi báo cáo sự khác biệt, cần phân biệt hai trường hợp nếu migration schema tạo/xóa keys.

## 22. Audit history theo tài khoản

Truy vấn:

```sql
SELECT
    audit_id,
    operation,
    actor_id,
    transaction_id,
    occurred_at,
    old_row,
    new_row
FROM lesson_audit.account_audit
WHERE tenant_id = 10
  AND account_id = 1001
ORDER BY audit_id;
```

Chỉ mục `(tenant_id, account_id, audit_id DESC)` hỗ trợ tìm lịch sử của một tài khoản trong phạm vi tenant và trả các sự kiện gần đây theo ID.

### Không đồng nghĩa thứ tự pháp lý tuyệt đối

`audit_id` do sequence cấp trước commit nên không phải một đồng hồ commit-order xuyên transactions. Nếu nghiệp vụ cần dựng state ở một **thời điểm commit chính xác** dưới concurrent transactions, phải thiết kế thêm cơ chế sequencing/snapshot/CDC phù hợp.

Trong một bài lab tuần tự, `ORDER BY audit_id` thường đủ để người học nhìn chuỗi thay đổi đã tạo.

## 23. Những bất biến cần kiểm chứng

Trước khi viết test, xác định những **invariants** mà giải pháp audit cần giữ:

| Mã | Bất biến | Cách kiểm chứng |
|---|---|---|
| A1 | Mỗi INSERT được theo dõi sinh một event INSERT | Đếm event mới và kiểm tra `new_row` |
| A2 | Mỗi UPDATE có thay đổi giá trị sinh event UPDATE | So `old_row`/`new_row` với bản ghi trước/sau |
| A3 | UPDATE no-op không sinh event theo chính sách bài | Đếm chênh lệch audit trước/sau |
| A4 | Mỗi DELETE được theo dõi sinh event DELETE | `old_row` có dữ liệu, `new_row` là SQL NULL |
| A5 | Audit không vượt phạm vi tenant | Khóa và tenant trong event khớp với row |
| A6 | DML rollback không để lại audit đã commit | ROLLBACK rồi truy vấn lại |
| A7 | DML lỗi thì không để lại thay đổi nguồn một phần | Test constraint/exception trong transaction |
| A8 | Chỉ role được cấp quyền đọc audit | Test GRANT/REVOKE/RLS |
| A9 | Mọi đường ghi thực tế đều kích hoạt trigger cần thiết | Test INSERT/UPDATE/DELETE, COPY, UPSERT, admin tools |
| A10 | Nguồn và lịch sử có thể đối soát tại mốc nhất quán | So snapshot cuối với dữ liệu nguồn |

Một lời khẳng định “có trigger là xong” không đủ. Chỉ khi đã định nghĩa **cái gì đúng** và **cách phát hiện sai**, hệ thống mới có thể vận hành lâu dài.

## 24. Kiểm chứng số event sau INSERT

Sau khi tạo trigger và chạy hai INSERT trong lab:

```sql
SELECT
    operation,
    count(*) AS event_count
FROM lesson_audit.account_audit
GROUP BY operation
ORDER BY operation;
```

Nếu chỉ chạy đến bước INSERT ban đầu, kỳ vọng:

```text
INSERT | 2
```

Sau các ví dụ UPDATE/DELETE phía trên, số lượng đương nhiên khác. Khi muốn test **không phụ thuộc lịch sử các bước trước**, hãy đếm event theo khóa được tạo riêng cho từng test hoặc ghi baseline count ngay trong transaction trước thao tác.

### Tránh giả định identity luôn bắt đầu từ 1

`audit_id` và `account_id` dùng identity/sequence có thể có gaps do transactions rollback hoặc các lần thử trước đó. Không hard-code kiểm chứng rằng “event đầu tiên luôn là audit_id=1” trong hệ thống thực.

## 25. Test INSERT có assertion trong một transaction

Một ví dụ có khả năng chạy lại theo một ID test riêng, rồi rollback:

```sql
BEGIN;

DO $$
DECLARE
    v_before BIGINT;
    v_after BIGINT;
    v_account_id BIGINT := 900001;
BEGIN
    SELECT count(*)
    INTO v_before
    FROM lesson_audit.account_audit
    WHERE account_id = v_account_id;

    INSERT INTO lesson_audit.accounts (
        account_id, tenant_id, account_code,
        display_name, credit_limit, status
    )
    VALUES (
        v_account_id, 90, 'TEST-900001',
        'Tài khoản kiểm thử', 10000, 'ACTIVE'
    );

    SELECT count(*)
    INTO v_after
    FROM lesson_audit.account_audit
    WHERE account_id = v_account_id;

    IF v_after <> v_before + 1 THEN
        RAISE EXCEPTION
            'Expected one audit INSERT event, got %',
            v_after - v_before;
    END IF;
END;
$$;

ROLLBACK;
```

### Tại sao dùng ROLLBACK?

Để test tạo và quan sát audit event nhưng không để tài khoản kiểm thử lâu dài trong database. Nếu assertion lỗi, transaction sẽ ở trạng thái lỗi và bạn vẫn phải rollback trước khi chạy bước tiếp theo.

Lưu ý: nếu database lab đã có account_id 900001, INSERT sẽ bị lỗi unique key; dùng khóa test chưa tồn tại hoặc test-fixture riêng.

## 26. Test UPDATE dựa trên snapshot

Một kiểm chứng mạnh hơn việc chỉ đếm:

```sql
BEGIN;

DO $$
DECLARE
    v_before JSONB;
    v_after JSONB;
    v_event lesson_audit.account_audit%ROWTYPE;
BEGIN
    SELECT to_jsonb(a)
    INTO STRICT v_before
    FROM lesson_audit.accounts AS a
    WHERE a.tenant_id = 10
      AND a.account_id = 1001;

    UPDATE lesson_audit.accounts
    SET credit_limit = credit_limit + 5000,
        updated_at = clock_timestamp()
    WHERE tenant_id = 10
      AND account_id = 1001;

    SELECT to_jsonb(a)
    INTO STRICT v_after
    FROM lesson_audit.accounts AS a
    WHERE a.tenant_id = 10
      AND a.account_id = 1001;

    SELECT *
    INTO STRICT v_event
    FROM lesson_audit.account_audit
    WHERE tenant_id = 10
      AND account_id = 1001
      AND operation = 'UPDATE'
    ORDER BY audit_id DESC
    LIMIT 1;

    IF v_event.old_row IS DISTINCT FROM v_before
       OR v_event.new_row IS DISTINCT FROM v_after THEN
        RAISE EXCEPTION 'Audit snapshot mismatch';
    END IF;
END;
$$;

ROLLBACK;
```

### Ý nghĩa

Test không chỉ xác nhận event đã có, mà xác nhận **OLD khớp với snapshot trước UPDATE** và **NEW khớp với snapshot sau UPDATE** trong cùng transaction.

### Giới hạn

Ví dụ chọn `ORDER BY audit_id DESC LIMIT 1`; trong môi trường nhiều writer/concurrent events cùng account, cần test isolation/locking hoặc fixture riêng để tránh lấy nhầm event khác. Vì UPDATE trên cùng hàng có row lock, trong transaction này các writer khác không thể commit một UPDATE trên cùng row giữa thao tác UPDATE và đọc event của transaction đang giữ lock, nhưng lựa chọn test-fixture độc lập vẫn là tốt nhất.

## 27. Test UPDATE không đổi giá trị

```sql
BEGIN;

DO $$
DECLARE
    v_count_before BIGINT;
    v_count_after BIGINT;
BEGIN
    SELECT count(*)
    INTO v_count_before
    FROM lesson_audit.account_audit
    WHERE tenant_id = 10 AND account_id = 1001;

    UPDATE lesson_audit.accounts
    SET status = status
    WHERE tenant_id = 10 AND account_id = 1001;

    SELECT count(*)
    INTO v_count_after
    FROM lesson_audit.account_audit
    WHERE tenant_id = 10 AND account_id = 1001;

    IF v_count_after <> v_count_before THEN
        RAISE EXCEPTION 'No-op UPDATE unexpectedly audited';
    END IF;
END;
$$;

ROLLBACK;
```

### Điều kiện của test

Không có trigger khác làm thay đổi các cột trên row khi `UPDATE status=status`; nếu có cơ chế tự tăng version hay tự cập nhật `updated_at` trên mọi UPDATE, chính sách bỏ no-op cần so **business columns** thay vì toàn row.

Đừng lẫn “câu UPDATE đã chạy và matched một row” với “giá trị đã thay đổi”. PostgreSQL có thể tạo tuple version mới cho UPDATE mà kết quả logical fields giống nhau; audit logic phải quyết định có ghi hay không.

## 28. Test DELETE giữ lại dữ liệu cũ

```sql
BEGIN;

DO $$
DECLARE
    v_before JSONB;
    v_old_event JSONB;
    v_new_event JSONB;
BEGIN
    INSERT INTO lesson_audit.accounts (
        account_id, tenant_id, account_code,
        display_name, credit_limit
    )
    VALUES (
        900002, 90, 'TEST-900002',
        'Tài khoản sẽ xóa', 2000
    );

    SELECT to_jsonb(a)
    INTO STRICT v_before
    FROM lesson_audit.accounts AS a
    WHERE a.account_id = 900002;

    DELETE FROM lesson_audit.accounts
    WHERE account_id = 900002;

    SELECT old_row, new_row
    INTO STRICT v_old_event, v_new_event
    FROM lesson_audit.account_audit
    WHERE account_id = 900002
      AND operation = 'DELETE';

    IF v_old_event IS DISTINCT FROM v_before
       OR v_new_event IS NOT NULL THEN
        RAISE EXCEPTION 'Invalid DELETE audit event';
    END IF;
END;
$$;

ROLLBACK;
```

Sau DELETE, hàng nguồn 900002 không tồn tại trong transaction, nhưng `old_row` vẫn chứa snapshot. Sau ROLLBACK, cả account được chèn cho test và các audit INSERT/DELETE test đều biến mất.

## 29. Kiểm chứng nhất quán nguồn và audit cuối

Nếu **mọi row đã được audit từ thời điểm INSERT**, có thể đối chiếu trạng thái hiện tại với event cuối của mỗi tài khoản.

```sql
WITH latest AS (
    SELECT DISTINCT ON (tenant_id, account_id)
        tenant_id,
        account_id,
        operation,
        new_row
    FROM lesson_audit.account_audit
    ORDER BY tenant_id, account_id, audit_id DESC
)
SELECT
    a.tenant_id,
    a.account_id,
    to_jsonb(a) AS current_row,
    l.new_row AS last_audited_row
FROM lesson_audit.accounts AS a
LEFT JOIN latest AS l
  ON l.tenant_id = a.tenant_id
 AND l.account_id = a.account_id
WHERE l.account_id IS NULL
   OR l.operation = 'DELETE'
   OR l.new_row IS DISTINCT FROM to_jsonb(a);
```

### Kỳ vọng

Trong lab tuần tự và khi tất cả đường ghi đều thông qua trigger, truy vấn nên trả **0 rows**.

### Những điều kiện để kết luận

- Không có hàng nguồn được nạp trước khi bật audit mà thiếu baseline.
- Không có trigger bị disable hoặc đường ghi bypass.
- Snapshot/JSONB schema còn tương thích với row hiện tại.
- Không có thay đổi đồng thời gây snapshot lệch trong quá trình đối chiếu.
- Thứ tự `audit_id` phản ánh chuỗi event theo cách cần dùng trong phạm vi thử nghiệm; **không** dùng query này làm bộ chứng minh commit-order toàn cục.

Nếu dữ liệu production cần đối soát chắc chắn dưới concurrency, thực hiện trên **consistent snapshot** và cân nhắc khóa/CDC/commit sequencing.

## 30. Kiểm tra hàng đã xóa mà event cuối chưa phải DELETE

Một dạng đối soát ngược là tìm thực thể mà **event cuối nói còn tồn tại** nhưng bảng nguồn không còn:

```sql
WITH latest AS (
    SELECT DISTINCT ON (tenant_id, account_id)
        tenant_id,
        account_id,
        operation,
        new_row
    FROM lesson_audit.account_audit
    ORDER BY tenant_id, account_id, audit_id DESC
)
SELECT
    l.tenant_id,
    l.account_id,
    l.operation,
    l.new_row
FROM latest AS l
LEFT JOIN lesson_audit.accounts AS a
  ON a.tenant_id = l.tenant_id
 AND a.account_id = l.account_id
WHERE a.account_id IS NULL
  AND l.operation <> 'DELETE';
```

Nếu có rows, nguyên nhân có thể gồm:

- DELETE không chạy audit.
- Log event bị xóa/sửa.
- Hàng bị xóa qua thao tác không được theo dõi.
- Dữ liệu được nạp/migrate không giữ đúng contract.
- Một sự kiện chưa được biểu diễn hoặc không được sắp theo commit order thực tế.

Không tự sửa bằng cách chèn event DELETE giả nếu chưa điều tra. Một sự kiện do hệ thống tạo sau để “vá log” cần được đánh dấu là **reconciliation/correction**, không giả làm một thao tác DELETE thật ở quá khứ.

## 31. Kiểm chứng phép thay đổi liên tiếp

Một chuỗi:

```text
INSERT limit 500000
UPDATE limit 700000
UPDATE status SUSPENDED
DELETE
```

theo chính sách lab có thể tạo bốn events. Với một chuỗi tuần tự của cùng entity:

- `INSERT.new_row` là trạng thái đầu.
- `UPDATE_1.old_row` bằng trạng thái trước sự kiện; `UPDATE_1.new_row` bằng trạng thái sau.
- `UPDATE_2.old_row` bằng `UPDATE_1.new_row` (nếu không có thay đổi khác).
- `DELETE.old_row` bằng trạng thái ngay trước xóa.

Có thể dùng `LAG` trên audit events để so kế tiếp:

```sql
WITH ordered AS (
    SELECT
        tenant_id,
        account_id,
        audit_id,
        operation,
        old_row,
        new_row,
        lag(new_row) OVER (
            PARTITION BY tenant_id, account_id
            ORDER BY audit_id
        ) AS previous_new
    FROM lesson_audit.account_audit
)
SELECT *
FROM ordered
WHERE operation IN ('UPDATE', 'DELETE')
  AND previous_new IS DISTINCT FROM old_row;
```

Trong lab thay đổi tuần tự, kết quả mong muốn là 0 rows.

### Giới hạn của kiểm tra

Nếu có hai transactions đồng thời cấp audit IDs theo thứ tự khác thứ tự commit, hoặc account đã có dữ liệu trước khi bật trigger, thứ tự/chuỗi có thể không đại diện timeline hoàn chỉnh. Đối soát này là tín hiệu **phát hiện bất thường**, không tự chứng minh bằng chứng lịch sử toàn cục.

## 32. Test transaction atomicity với nhiều bảng

Giả sử application cập nhật tài khoản và tạo một bản ghi business event cùng transaction:

```text
BEGIN
  UPDATE accounts
    └── trigger INSERT account_audit
  INSERT business_event
COMMIT
```

Nếu lệnh thứ hai lỗi và transaction rollback, audit event của UPDATE cũng bị rollback.

### Vì sao có lợi?

Không có trạng thái “tài khoản đã đổi nhưng audit không có” cho một transaction commit thành công, nếu audit trigger được kích hoạt và lỗi được xử lý theo chính sách không nuốt mất.

### Vẫn cần boundary rõ ràng

Nếu application tách UPDATE nguồn và ghi sự kiện ra **hai transactions**, audit trigger chỉ đảm bảo lịch sử của transaction UPDATE; nó không tự đảm bảo transaction khác hoặc HTTP call đã thành công.

Để phát event ra hệ ngoài nhất quán với DB commit, dùng **transactional outbox**, không gửi message/network request trực tiếp trong row trigger rồi nghĩ nó sẽ rollback theo PostgreSQL.

## 33. Ràng buộc nguồn là một phần tính đúng đắn

Bảng `accounts` có:

```sql
credit_limit NUMERIC(14,2) NOT NULL CHECK (credit_limit >= 0)
```

Thử:

```sql
BEGIN;

UPDATE lesson_audit.accounts
SET credit_limit = -1
WHERE account_id = 1001;

-- Lệnh UPDATE sẽ lỗi check_constraint.
ROLLBACK;
```

Khi constraint lỗi, statement không commit một trạng thái credit_limit âm. Audit trigger không tự biến dữ liệu sai thành đúng; **constraints** đảm bảo invariants nguồn, trigger audit ghi lịch sử những thay đổi được áp dụng trong transaction.

### Lỗi có thể xảy ra ở nhiều thời điểm

Constraint checks có thể là immediate hoặc deferred theo loại/ràng buộc và thiết kế; ngay cả khi AFTER row trigger đã chèn audit trong transaction, nếu cuối cùng transaction rollback vì constraint khác, cả audit entry cũng rollback.

Đừng giải thích “trigger đã chạy” như “transaction đã commit”.

## 34. Cập nhật nhiều hàng: bao nhiêu events?

```sql
BEGIN;

SELECT set_config('app.actor_id', 'bulk-job', true);

UPDATE lesson_audit.accounts
SET status = 'SUSPENDED'
WHERE tenant_id = 10
  AND status = 'ACTIVE';

SELECT
    count(*) AS events_in_transaction
FROM lesson_audit.account_audit
WHERE actor_id = 'bulk-job'
  AND operation = 'UPDATE';

ROLLBACK;
```

Với **AFTER ROW trigger**, mỗi row có sự thay đổi thực tế theo chính sách audit có thể tạo một event. Nếu WHERE match 0 rows, không có row-level invocation. Một statement có thể tạo hàng chục nghìn audit entries khi cập nhật hàng loạt.

### Đánh giá chi phí

- CPU chạy function mỗi row.
- Tạo JSONB snapshots.
- WAL cho audit inserts và indexes.
- Kích thước transaction.
- Locks và potential contention.

Không tự gắn row audit đầy đủ vào một bảng có rất nhiều UPDATE/giây mà không benchmark write throughput và storage.

## 35. Statement-level transition tables: khi muốn xử lý theo tập

PostgreSQL hỗ trợ **transition relations** cho các `AFTER` triggers thích hợp. Với UPDATE, có thể dùng:

```sql
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
```

Trigger function có thể đọc `old_rows`/`new_rows` như các relations tạm trong phạm vi invocation, thay vì lặp từng row bằng PL/pgSQL.

### Khi nào hữu ích?

- Ghi log theo batch bằng một `INSERT ... SELECT`.
- Tính summary của tập rows vừa sửa.
- Giảm overhead gọi function per-row trong một số workload.

### Các giới hạn

- Trigger phải thuộc dạng/timing phù hợp; không dùng transition tables tùy tiện với mọi trigger type.
- Không dùng `UPDATE OF column_list` kết hợp transition tables theo quy tắc PostgreSQL.
- Muốn ghép OLD và NEW bằng primary key, phải có **khóa ổn định** trong statement.
- Với partitioning và các dạng DML đặc biệt, cần kiểm tra chi tiết semantics/phiên bản.

## 36. Lab statement-level transition tables

Tạo bảng độc lập để không tạo duplicate audit trong cùng `accounts`:

```sql
CREATE TABLE lesson_audit.batch_items (
    item_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty >= 0)
);

CREATE TABLE lesson_audit.batch_item_changes (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    old_qty INTEGER NOT NULL,
    new_qty INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION lesson_audit.capture_batch_item_updates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson_audit.batch_item_changes (
        item_id,
        tenant_id,
        old_qty,
        new_qty
    )
    SELECT
        n.item_id,
        n.tenant_id,
        o.qty,
        n.qty
    FROM old_rows AS o
    JOIN new_rows AS n
      ON n.item_id = o.item_id
    WHERE o.qty IS DISTINCT FROM n.qty;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_batch_item_updates
AFTER UPDATE
ON lesson_audit.batch_items
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION lesson_audit.capture_batch_item_updates();
```

Chạy:

```sql
INSERT INTO lesson_audit.batch_items (
    item_id, tenant_id, qty
)
VALUES
    (1, 10, 5),
    (2, 10, 8),
    (3, 20, 7);

UPDATE lesson_audit.batch_items
SET qty = qty + 2
WHERE tenant_id = 10;

SELECT *
FROM lesson_audit.batch_item_changes
ORDER BY event_id;
```

Kỳ vọng có **hai events** ứng với item 1 và 2, dù trigger function `capture_batch_item_updates` chạy **một lần cho UPDATE statement**.

### Phạm vi đúng của ví dụ

JOIN OLD/NEW bằng `item_id` chỉ chính xác khi ID không bị đổi. Nếu một UPDATE có thể sửa primary key, cần giữ một khóa bất biến hoặc thiết kế khác. Nếu muốn audit nhiều fields, thêm snapshots hoặc các columns tương ứng thay vì chỉ qty.

## 37. Statement UPDATE tác động 0 rows

```sql
UPDATE lesson_audit.batch_items
SET qty = qty + 1
WHERE tenant_id = -999;
```

Với statement-level trigger, function vẫn có thể được gọi **một lần cho statement**, nhưng `old_rows` và `new_rows` rỗng; `INSERT ... SELECT` không thêm event.

Với row-level trigger trên `accounts`, không có row được sửa nên không có row trigger invocation.

### Vì sao điều này quan trọng?

Nếu hệ thống cần log “một người dùng đã cố chạy UPDATE” kể cả khi ảnh hưởng 0 rows, đó không phải câu hỏi giống việc ghi **lịch sử trạng thái dữ liệu**. Có thể cần statement audit hoặc application request logs riêng.

## 38. Những thao tác không giống UPDATE/DELETE thường

Ứng dụng không chỉ dùng ba câu DML cơ bản. Các đường ghi khác phải được đánh giá:

- `INSERT ... ON CONFLICT DO UPDATE` (UPSERT).
- `MERGE` (trên phiên bản hỗ trợ).
- `COPY FROM` để nạp nhiều hàng.
- Cascading updates/deletes qua foreign key.
- Bulk jobs/migration/admin tools.
- `TRUNCATE`.
- Replication apply và những phiên làm việc có thay đổi trigger firing mode.

Không nên kết luận “đã tạo một trigger là tất cả đường sửa dữ liệu đều được ghi” cho tới khi kiểm thử những đường thật mà ứng dụng sử dụng.

## 39. UPSERT có thể là INSERT hoặc UPDATE

Ví dụ có uniqueness trên `(tenant_id,account_code)`:

```sql
INSERT INTO lesson_audit.accounts (
    tenant_id, account_code, display_name, credit_limit
)
VALUES (
    10, 'AC-001', 'Công ty An Bình', 710000
)
ON CONFLICT (tenant_id, account_code)
DO UPDATE
SET credit_limit = EXCLUDED.credit_limit;
```

Vì bản ghi AC-001 đã có, command đi theo nhánh `DO UPDATE` cho row đó; audit trigger row-level sẽ thấy một UPDATE (trừ khi quy tắc no-op bỏ qua). Nếu conflict không tồn tại, có thể là INSERT.

### Trigger semantics phức tạp hơn khi UPSERT

`INSERT ... ON CONFLICT DO UPDATE` có quy tắc kích hoạt những trigger types liên quan; statement-level INSERT/UPDATE triggers có thể được kích hoạt theo cách khác suy luận “mỗi row một action”. Hãy test thực tế cho **cả row-level và statement-level** triggers khi thiết kế hệ thống có UPSERT.

Nếu câu lệnh `ON CONFLICT DO NOTHING` không chèn hàng nào, row audit không nên tự tạo một INSERT event cho hàng không được thêm.

## 40. MERGE và thao tác nhiều nhánh

`MERGE` có thể kết hợp INSERT, UPDATE, DELETE theo các nhánh match/not match ở các phiên bản PostgreSQL hỗ trợ.

### Thiết kế test

- Nhánh `WHEN MATCHED THEN UPDATE`.
- Nhánh `WHEN MATCHED THEN DELETE`.
- Nhánh `WHEN NOT MATCHED THEN INSERT`.
- Trường hợp không có nhánh thực hiện DML.
- Statement/row trigger firing phù hợp theo phiên bản PostgreSQL.

Không mặc định một `MERGE` là “chỉ một sự kiện” hoặc có semantics đơn giản giống một `UPDATE`. Audit muốn ghi **row outcome** thì cần kiểm tra các action thực sự được áp dụng.

## 41. COPY FROM và nhập dữ liệu hàng loạt

`COPY table FROM ...` dùng để nạp rows có thể kích hoạt INSERT row triggers theo cơ chế PostgreSQL, nhưng ingestion với triggers sẽ có thêm chi phí rất lớn nếu mỗi row tạo snapshot audit.

### Cần cân nhắc

- Import 10 triệu hàng có cần 10 triệu audit INSERT events không?
- Có thể import vào staging table rồi merge theo chính sách audit không?
- Có cần lưu batch ID/source file để truy vết không?
- Nếu tạm tắt trigger để tăng tốc, hệ thống ghi nhận “audit gap” ra sao?

Không ngầm vô hiệu hóa trigger chỉ để import nhanh và vẫn tuyên bố lịch sử đã đầy đủ. Nếu bootstrap import không cần audit từng row, phải có **baseline/migration record** và hợp đồng provenance rõ.

## 42. TRUNCATE là một lỗ hổng nếu chỉ có row audit

`TRUNCATE lesson_audit.accounts` loại bỏ nhiều hàng rất nhanh, nhưng **không phát sinh row-level DELETE triggers cho từng hàng**.

PostgreSQL có **statement-level triggers trên TRUNCATE**:

```sql
CREATE OR REPLACE FUNCTION lesson_audit.log_truncate_attempt()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'TRUNCATE is not allowed on audited table %',
        TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER trg_accounts_block_truncate
BEFORE TRUNCATE
ON lesson_audit.accounts
FOR EACH STATEMENT
EXECUTE FUNCTION lesson_audit.log_truncate_attempt();
```

### Tại sao chặn TRUNCATE ở lab?

Nếu yêu cầu giữ toàn bộ lịch sử per-row, một lệnh TRUNCATE không tạo được `OLD` snapshot từng hàng qua row DELETE trigger. Ta chặn để tránh vô tình mất dữ liệu nguồn mà không có DELETE events.

### Giới hạn

- Role có quyền sửa schema/disable/drop trigger vẫn có thể bypass.
- `TRUNCATE` có những semantics lock và transaction riêng; chặn ở trigger không thay quyền `TRUNCATE`.
- Nếu application thật sự cần TRUNCATE, phải có chính sách audit **theo statement** và baseline/snapshot phù hợp, không giả làm nhiều DELETE events vốn không diễn ra.

## 43. Quyền TRUNCATE phải được kiểm soát

Trong production:

- Không cấp `TRUNCATE` tùy tiện cho application role.
- Không cấp quyền owner/schema DDL nếu không cần.
- Không cho role thông thường `ALTER TABLE ... DISABLE TRIGGER`.
- Tách migrations/admin role khỏi runtime role.
- Có cơ chế quan sát thay đổi schema/trigger state.

Một trigger `BEFORE TRUNCATE` có thể từ chối thao tác bình thường, nhưng **không thể được xem là bất biến trước quyền quản trị cao**. Quyền/monitoring ngoài bảng audit vẫn quan trọng.

## 44. Trigger có thể bị tắt hoặc không được kích hoạt

Những trường hợp phải hiểu:

- `ALTER TABLE ... DISABLE TRIGGER` bởi role có đủ quyền.
- `DROP TRIGGER`/`DROP FUNCTION` bởi role có đủ quyền.
- `session_replication_role` thay đổi firing behavior đối với triggers theo mode và quyền.
- Logical replication apply và cấu hình `ENABLE REPLICA/ALWAYS TRIGGER`.
- Các thao tác trên bảng/partition không được gắn đúng cơ chế.
- Bulk migrations thao tác ngoài pipeline dự kiến.

### Vì sao nguy hiểm?

Nếu thay đổi nguồn diễn ra khi audit trigger không chạy, bạn có thể có **current state** nhưng không có sự kiện lịch sử tương ứng. Việc bật trigger lại **không tự khôi phục những sự kiện đã bỏ lỡ**.

### Phản ứng vận hành

Ghi nhận thời gian và phạm vi audit gap, dùng data snapshots/WAL/CDC/backup nếu có để đối chiếu, và tạo correction/baseline minh bạch. Không lặng lẽ thêm event giả mạo “đã xảy ra chính xác như vậy” nếu không có bằng chứng.

## 45. Kiểm tra trigger đang tồn tại và được bật

PostgreSQL catalog `pg_trigger` giúp quan sát:

```sql
SELECT
    n.nspname AS table_schema,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS firing_mode,
    t.tgisinternal AS internal_trigger,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c
  ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lesson_audit'
ORDER BY c.relname, t.tgname;
```

`tgenabled` có các mã cho enabled/disabled và các firing modes liên quan replication. Không chỉ kiểm tra “có tên trigger”: phải xét nó có đang được phép firing theo môi trường cần bảo vệ không.

### Monitor thay đổi definition

So sánh catalog/DDL với migration manifests trong một hệ thống config management đáng tin. Một truy vấn trực tiếp vào catalog vẫn không đủ làm **tamper-proof evidence** nếu người có quyền cao có thể thay đổi database và logs.

## 46. Trigger recursion và ghi lặp

Audit function ghi vào **bảng khác** (`account_audit`), không tự UPDATE `accounts`, nên bình thường không kích hoạt lại chính row audit trigger.

Nếu bạn tạo trigger trên `account_audit` rồi function đó lại sửa `accounts`, hoặc một trigger trên `accounts` tự UPDATE `accounts`, có thể tạo recursion, deadlock hoặc vòng ghi lặp.

PostgreSQL có hàm:

```sql
SELECT pg_trigger_depth();
```

nhưng không nên chỉ dựa vào `IF pg_trigger_depth()>1 THEN RETURN ...` để che một kiến trúc tự kích hoạt đệ quy.

### Thiết kế tốt

- Trigger validation/normalization sửa `NEW` trong BEFORE khi phù hợp.
- AFTER audit chỉ INSERT vào audit table.
- Audit table không có trigger update ngược lên source trừ khi có yêu cầu cực kỳ rõ.
- Kiểm soát outbox/event hooks tránh tạo vòng lặp.

## 47. Partitioned tables và audit

Với bảng partitioned theo tenant/thời gian, row triggers trên parent có các quy tắc clone/firing ở partitions trong PostgreSQL hiện đại; mức hỗ trợ và hành vi có thể tùy version, kiểu trigger và DDL.

### Những tình huống cần test

- INSERT vào parent và routing sang partition.
- UPDATE khiến row di chuyển giữa partitions.
- DELETE qua parent vs trực tiếp partition.
- ATTACH/DETACH partitions.
- Bulk COPY/maintenance.
- Statement-level triggers trên parent và partitions.

### Không giả định mọi sự kiện chỉ một row UPDATE đơn giản

Việc di chuyển partition do UPDATE partition key có thể dùng cơ chế DELETE/INSERT nội bộ và triggers tương ứng theo PostgreSQL. Khi thiết kế audit, phải thử hành vi trên **đúng phiên bản/cấu trúc partition** để không đếm nhầm hoặc hiểu sai operation sequence.

Nếu dùng audit table partitioned riêng, lập kế hoạch retention/constraints/indexing để không làm tăng overhead DML vượt SLA.

## 48. DDL không nằm trong AFTER INSERT/UPDATE/DELETE

Thay đổi schema:

```sql
ALTER TABLE lesson_audit.accounts
ADD COLUMN IF NOT EXISTS external_ref TEXT;
```

không phải một INSERT/UPDATE/DELETE của dữ liệu ứng dụng theo trigger hiện tại; row audit không tạo event “schema changed”.

### Nếu cần audit DDL

Có thể dùng:

- Versioned migration repository/approval logs.
- Database server logs/audit extension phù hợp.
- PostgreSQL **event triggers** cho một số sự kiện DDL ở mức database.

Event triggers là cơ chế khác row triggers, có yêu cầu quyền cao và phạm vi hỗ trợ cụ thể. Không cho rằng event trigger có thể bắt mọi hành động administrator, hoặc có thể chứng minh lịch sử không bị sửa bởi superuser.

## 49. Audit row không tự lưu DDL schema version

Giả sử trước migration `accounts` có 7 cột; sau migration thêm `external_ref`.

Sự kiện JSONB cũ không có key `external_ref`, sự kiện mới có thể có.

### Hệ quả

- Khả năng so sánh snapshots qua schema versions cần quy tắc rõ.
- Key không tồn tại khác JSON null.
- Một migration đổi tên cột có thể trông giống “xóa key A, thêm key B”.
- Các ứng dụng đọc history không được giả định mọi event có cùng JSON schema.

### Hướng xử lý

Thêm metadata như `schema_version` hoặc `event_version` vào bảng audit nếu cần, quản lý bằng migration. Một màn hình lịch sử có thể render dựa trên field set của từng event; một pipeline phân tích dài hạn cần schema evolution rõ ràng.

## 50. Backfill lịch sử khi mới bật trigger

Nếu bảng đã có hàng triệu hàng trước khi tạo audit, những hàng đó **không có INSERT events lịch sử thật**.

Một phương án rollout:

1. Xác định cutover/baseline timestamp.
2. Tạo audit infrastructure và kiểm tra quyền.
3. Tạo consistent snapshot của nguồn hoặc chiến lược online backfill với watermark.
4. Ghi **BASELINE** records với nguồn và mốc rõ ràng, không giả là INSERT gốc.
5. Bật/theo dõi triggers trong giai đoạn cutover.
6. Đối soát các hàng mới/sửa trong thời gian migration.
7. Tài liệu hóa history coverage bắt đầu từ mốc nào.

### Chú ý schema lab

Bảng `account_audit` ở đầu bài chỉ cho `operation` là INSERT/UPDATE/DELETE. Nếu muốn thêm event `BASELINE`, cần **migration sửa CHECK constraint và contract**, hoặc dùng một bảng baseline riêng. Đừng tự chèn `operation='INSERT'` cho các hàng đã tồn tại từ lâu rồi trình bày như log gốc.

Một audit trail đáng tin không cần giả vờ biết quá khứ chưa được ghi; nó cần nói rõ **giới hạn phạm vi dữ liệu đã quan sát**.

## 51. Concurrency: hai phiên cùng sửa một hàng

Giả sử account 1001 có `credit_limit=700000`. Hai sessions đồng thời:

**Session A:**

```sql
BEGIN;

UPDATE lesson_audit.accounts
SET credit_limit = credit_limit + 10000
WHERE tenant_id = 10 AND account_id = 1001;

-- Chưa COMMIT ngay.
```

**Session B:**

```sql
BEGIN;

UPDATE lesson_audit.accounts
SET credit_limit = credit_limit + 20000
WHERE tenant_id = 10 AND account_id = 1001;

COMMIT;
```

Session B có thể phải chờ row lock của A. Khi A COMMIT, PostgreSQL áp dụng ngữ nghĩa transaction isolation và locking thích hợp; ở `READ COMMITTED`, một UPDATE như `credit_limit = credit_limit + 20000` thường được thực hiện dựa trên hàng được cập nhật hợp lệ sau khi chờ, thay vì đơn giản ghi đè snapshot cũ của client.

**Session A cuối cùng:**

```sql
COMMIT;
```

### Điều audit cần phản ánh

Mỗi UPDATE **đã được commit thành công** làm thay đổi row tạo một audit event với `OLD` và `NEW` tương ứng state thực tế của row được cập nhật. Nếu một transaction bị hủy vì serialization failure hoặc deadlock và rollback, audit event của transaction đó không còn.

### Không hứa thứ tự commit từ audit_id

Audit IDs có thể được cấp trước khi commit; một transaction chạy lâu có thể commit sau transaction được cấp ID lớn hơn. Chỉ dựa vào `audit_id`/`occurred_at` để khẳng định “sự kiện nào commit trước” giữa những transactions độc lập là không đủ.

## 52. Lost update tại tầng ứng dụng

Trigger audit **không tự ngăn** logic ứng dụng đọc một số, tính bên Java, rồi UPDATE bằng một giá trị tuyệt đối đã lỗi thời.

Ví dụ:

```text
A đọc credit_limit = 700000
B đọc credit_limit = 700000
A tính 710000, UPDATE SET credit_limit = 710000
B tính 720000, UPDATE SET credit_limit = 720000
```

Nếu không có optimistic locking/version check hoặc cơ chế kiểm soát phù hợp, thay đổi của A có thể bị mất ở mức nghiệp vụ. Audit có thể ghi:

```text
700000 → 710000
710000 → 720000
```

nhưng nó không biết B đáng lẽ cộng 20000 trên **giá trị mới** chứ không phải đặt giá trị tuyệt đối từ snapshot cũ.

### Giải pháp

- Dùng atomic SQL `SET credit_limit = credit_limit + $1` khi phù hợp.
- Dùng `row_version`/expected version ở WHERE để thực hiện optimistic locking.
- Dùng `SELECT FOR UPDATE`/transaction isolation phù hợp cho quy trình phức tạp.
- Có tests concurrency và retry policy rõ.

Audit giúp **phát hiện** một chuỗi kết quả bất thường, không thay thế cơ chế ngăn lost update.

## 53. Version counter cho mỗi thực thể

Một số hệ thống thêm `row_version BIGINT NOT NULL DEFAULT 1` vào bảng nguồn, rồi tăng khi business state đổi.

### Lợi ích

- Ứng dụng có thể dùng `UPDATE ... WHERE row_version = expected`.
- Audit snapshot ghi được version trước/sau.
- Có thể kiểm tra các version liên tiếp của cùng entity.
- Dễ phân biệt state cũ và mới khi event IDs không hoàn toàn theo commit order.

### Giới hạn

Version counter không tự giải quyết audit khi một role đặc quyền sửa trực tiếp hoặc disable trigger. Nếu increment ở application thay vì trigger/DB constraint, phải bảo đảm mọi đường ghi tuân thủ.

Không thêm version counter cho mọi bảng chỉ để “có vẻ an toàn”; dùng nơi thực sự có concurrency contract.

## 54. Transaction ID có thể nhóm nhiều events

Một transaction sửa ba accounts:

```sql
BEGIN;

SELECT set_config('app.actor_id', 'bulk-editor', true);

UPDATE lesson_audit.accounts
SET status = 'SUSPENDED'
WHERE tenant_id = 10
  AND status = 'ACTIVE';

COMMIT;
```

Các audit entries từ những row changes trong cùng transaction thường mang cùng `txid_current()`. Có thể group:

```sql
SELECT
    transaction_id,
    count(*) AS events,
    min(occurred_at) AS first_event_time,
    max(occurred_at) AS last_event_time
FROM lesson_audit.account_audit
GROUP BY transaction_id
ORDER BY events DESC, transaction_id;
```

### Giới hạn

Transaction ID không giống **business request ID**; một HTTP request có thể mở nhiều transactions, và một transaction có thể thực hiện nhiều business operations. Nếu cần trace từ request sang audit, thêm `request_id`/correlation ID với nguồn đáng tin và privacy controls.

Transaction ID cũng không phải timestamp và không bảo đảm thứ tự commit xuyên transactions khi xem như một số nguyên tăng.

## 55. Dùng actor_id trong ứng dụng đúng ngữ cảnh

Trong lab:

```sql
BEGIN;
SELECT set_config('app.actor_id', 'editor-42', true);
UPDATE lesson_audit.accounts ...;
COMMIT;
```

Ứng dụng backend có thể thực hiện tương tự bằng `SET LOCAL` hoặc `set_config(...,true)` trong transaction.

### Tại sao SET LOCAL?

Khi sử dụng connection pool, giá trị session-level có thể rò từ request trước sang request sau nếu không reset. `SET LOCAL` hoặc `set_config(...,true)` giữ context trong phạm vi transaction.

### Quan trọng về độ tin cậy

Custom GUC như `app.actor_id` **có thể được đặt bởi các sessions có quyền chạy SQL thích hợp**; nó không phải một identity token được PostgreSQL ký xác thực.

Nếu user trực tiếp có SQL access, không tin giá trị này như bằng chứng không thể giả. Có thể bổ sung:

- Authentication/authorization ở backend tin cậy.
- Database role identity (với giới hạn dùng shared app roles).
- Request logs ở một hệ độc lập.
- Audit service dùng credentials riêng.
- Cryptographic signature/external append-only storage nếu compliance đòi hỏi.

## 56. current_user và session_user khác actor nghiệp vụ

```sql
SELECT
    current_user,
    session_user,
    current_setting('app.actor_id', true) AS app_actor;
```

- `session_user` thường là role đăng nhập ban đầu.
- `current_user` phản ánh role dùng để kiểm tra quyền hiện tại và có thể khác khi thực thi `SECURITY DEFINER`.
- `app.actor_id` là chuỗi context ứng dụng chủ động đặt.

Nếu mọi HTTP request dùng chung database role `app_service`, `session_user` không cho bạn biết người dùng web cụ thể nào đã click. Khi trigger là SECURITY DEFINER, `current_user` bên trong có thể là owner function, không phải app role.

### Thiết kế metadata

Có thể ghi đồng thời:

- `database_session_user`.
- `application_actor_id`.
- `request_id`.
- `service_name`.
- `transaction_id`.

Nhưng phải khai báo rõ trường nào là **xác thực bởi database**, trường nào là **application-supplied** và mức độ tin cậy của từng nguồn.

## 57. JDBC: đặt actor trong cùng transaction

Ví dụ Java với JDBC:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class AccountRepository {
    public static void changeLimit(
            Connection conn,
            long authorizedTenantId,
            long accountId,
            BigDecimal newLimit,
            String authenticatedActor
    ) throws SQLException {
        boolean previousAutoCommit = conn.getAutoCommit();
        conn.setAutoCommit(false);

        try {
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT set_config('app.actor_id', ?, true)"
            )) {
                ps.setString(1, authenticatedActor);
                ps.execute();
            }

            String updateSql = """
                UPDATE lesson_audit.accounts
                SET credit_limit = ?,
                    updated_at = clock_timestamp()
                WHERE tenant_id = ?
                  AND account_id = ?
                """;

            try (PreparedStatement ps = conn.prepareStatement(updateSql)) {
                ps.setBigDecimal(1, newLimit);
                ps.setLong(2, authorizedTenantId);
                ps.setLong(3, accountId);

                int changed = ps.executeUpdate();
                if (changed != 1) {
                    throw new SQLException(
                        "Account not found or not authorized"
                    );
                }
            }

            conn.commit();
        } catch (SQLException | RuntimeException ex) {
            conn.rollback();
            throw ex;
        } finally {
            conn.setAutoCommit(previousAutoCommit);
        }
    }
}
```

### Điều được đảm bảo

`set_config(...,true)` và UPDATE diễn ra trong **cùng transaction** và trên **cùng connection**, nên trigger thấy actor context đúng theo session setting của transaction.

### Điều chưa được đảm bảo

- `authenticatedActor` phải đến từ authentication context đáng tin, không lấy nguyên từ request body.
- `authorizedTenantId` phải được backend xác nhận quyền.
- Không chứng minh được user cuối **không thể giả actor** nếu họ có direct SQL access với cùng database role.
- Trong hệ thống lớn cần bảo vệ khỏi connection misuse khi transaction handling bị lỗi.
- Chưa có optimistic locking/version check hay idempotency policy.

## 58. Spring: transaction context và trigger

Trong Spring, một service có thể:

1. Bắt đầu transaction qua `@Transactional`.
2. Gọi `SELECT set_config('app.actor_id', ?, true)` bằng `JdbcTemplate`.
3. Chạy UPDATE trong cùng transaction manager/datasource.
4. Commit hoặc rollback sau khi hoàn tất nghiệp vụ.

Ví dụ skeleton:

```java
@Transactional
public void changeLimit(
        long authorizedTenantId,
        long accountId,
        BigDecimal newLimit,
        String actorId
) {
    jdbcTemplate.queryForObject(
        "SELECT set_config('app.actor_id', ?, true)",
        String.class,
        actorId
    );

    int changed = jdbcTemplate.update(
        """
        UPDATE lesson_audit.accounts
        SET credit_limit = ?,
            updated_at = clock_timestamp()
        WHERE tenant_id = ? AND account_id = ?
        """,
        newLimit,
        authorizedTenantId,
        accountId
    );

    if (changed != 1) {
        throw new IllegalStateException("Account not found");
    }
}
```

### Lưu ý

Đây là skeleton, giả định đã có `JdbcTemplate`, imports và transaction management phù hợp. `@Transactional` chỉ có ý nghĩa nếu Spring thực sự quản lý cùng connection/transaction cho hai calls và không tự mở thêm transaction riêng khi qua các layers khác.

Nếu xảy ra exception không được xử lý theo policy, transaction rollback, và audit event transactional cũng mất theo.

## 59. Không cho ứng dụng trực tiếp ghi audit

Trong production, lý tưởng là role application:

- Có quyền thực hiện những thao tác nghiệp vụ được phép trên `accounts`.
- **Không có quyền INSERT/UPDATE/DELETE/TRUNCATE trực tiếp** trên bảng `account_audit`.
- Không phải owner của schema/audit table.
- Không được tự sửa trigger function hoặc tắt triggers.

Ví dụ DCL dưới đây **chỉ là hướng dẫn khi role `app_writer` đã được tạo**:

```sql
-- REVOKE ALL ON lesson_audit.account_audit FROM PUBLIC;
-- REVOKE ALL ON lesson_audit.account_audit FROM app_writer;
--
-- GRANT USAGE ON SCHEMA lesson_audit TO app_writer;
-- GRANT SELECT, INSERT, UPDATE, DELETE
--   ON lesson_audit.accounts TO app_writer;
```

### Vì sao phải dùng SECURITY DEFINER thận trọng?

Nếu app_writer không được INSERT audit table, trigger vẫn cần ghi audit. `SECURITY DEFINER` cho phép dùng quyền owner khi đã thiết kế và kiểm toán đúng. Nhưng cấp owner quá rộng hoặc để schema không tin cậy trong search_path có thể tạo đường leo thang quyền.

Không cấp cho runtime role quyền thay đổi table owner/DDL/role membership rồi nghĩ REVOKE audit đã đủ.

## 60. RLS trên bảng nguồn và bảng lịch sử

Với nhiều tenants, bảng `accounts` có thể dùng PostgreSQL Row-Level Security; bảng `account_audit` cũng phải có chính sách quyền đọc riêng.

### Những lỗi thường gặp

- RLS chỉ bật trên nguồn, không bật trên history.
- Một báo cáo admin vô tình trả audit của tenant khác.
- Role owner hoặc `BYPASSRLS` được dùng cho ứng dụng.
- `SECURITY DEFINER` truy vấn bằng quyền owner theo cách bypass chính sách dự kiến.
- Tenant ID trong custom session setting do user tự chọn, không được xác thực.

### Quy tắc

Mỗi API tra cứu lịch sử phải kiểm soát:

```sql
WHERE tenant_id = :authorized_tenant_id
  AND account_id = :requested_account_id
```

`:name` ở đây là ký hiệu tham số minh họa của application, **không phải PostgreSQL placeholder gõ trực tiếp trong psql**.

### Không nhầm actor với quyền

Một user có thể có actor ID hợp lệ nhưng vẫn không có quyền xem lịch sử của account khác. Actor metadata dùng cho **attribution**, không thay **authorization**.

## 61. SECURITY DEFINER và search_path

Trigger function trong lab dùng:

```sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
```

và tham chiếu đầy đủ:

```sql
INSERT INTO lesson_audit.account_audit (...)
```

### Tại sao?

Routine đặc quyền nếu gọi object không schema-qualify từ schema mà attacker có thể CREATE có nguy cơ **name-resolution hijacking**.

### Các biện pháp bổ sung

- Owner function là role tin cậy, chỉ có quyền cần thiết.
- Quyền `CREATE` trên schemas được kiểm soát.
- Bảng audit không thể bị writer sửa trực tiếp.
- Các helper functions trong body được schema-qualify hoặc resolution an toàn.
- Không dùng dynamic SQL với identifier không tin cậy.
- Kiểm soát `EXECUTE`/trigger DDL grants.

`SECURITY DEFINER` là một công cụ quyền mạnh, không phải lựa chọn mặc định cho mọi trigger.

## 62. Dữ liệu nhạy cảm trong snapshot

`to_jsonb(OLD)`/`to_jsonb(NEW)` sao chép **toàn bộ columns** của hàng. Nếu nguồn chứa:

- Số điện thoại, email, địa chỉ.
- Thông tin thanh toán.
- Password hash.
- Token/secret.
- Hồ sơ nhạy cảm.

thì audit có thể lưu **cả phiên bản cũ lẫn mới** ngay cả sau khi nguồn xóa/ẩn dữ liệu.

### Bảo vệ

- **Data minimization:** chỉ ghi những columns cần audit.
- Mask/redact fields theo chính sách trước khi lưu.
- Hạn chế quyền SELECT trên audit.
- Cân nhắc encryption at rest và key management.
- Áp dụng retention/deletion policy có cơ sở pháp lý.
- Không xuất JSONB raw ra client hoặc logs.
- Cân nhắc tính chính xác của “quyền được xóa” với audit retention obligations.

Audit không nên trở thành nơi lưu bản sao lịch sử bí mật vô hạn mà không có kiểm soát.

## 63. Chọn column-level snapshot thay full JSONB

Nếu chỉ quan tâm `credit_limit` và `status`, có thể thiết kế bảng:

```text
audit_id
account_id
tenant_id
old_credit_limit
new_credit_limit
old_status
new_status
actor_id
occurred_at
```

### Lợi ích

- Kiểu dữ liệu rõ và có thể index/filter dễ.
- Dễ hạn chế PII ngoài phạm vi cần.
- Storage nhỏ hơn full-row JSONB khi bảng nguồn rất rộng.

### Đổi lại

- Khi thêm business columns cần audit, phải migration schema/function.
- Dễ quên một field mới nếu không có tests phủ schema.
- Khó dùng cho nhiều tables rất khác nhau trong một audit table chung.

Một kiến trúc kết hợp có thể lưu metadata typed và JSONB **chỉ chứa tập fields được phép**, thay vì chụp toàn bộ row.

## 64. Audit table lớn: storage, WAL và TOAST

Mỗi UPDATE có thể ghi:

```text
old snapshot JSONB
new snapshot JSONB
metadata
index entries
WAL records
```

Với tài liệu/bảng rộng, JSONB có thể được lưu ngoài dòng qua TOAST và tạo lượng ghi đáng kể. Một bảng có 1 triệu rows cập nhật nhiều lần mỗi ngày có thể sinh hàng chục triệu audit events.

### Các lựa chọn tối ưu

- Giới hạn các fields audit.
- Bỏ no-op theo policy.
- Index các truy vấn đọc audit thực tế, tránh index mọi key JSONB.
- Partition audit table theo thời gian khi volume đủ lớn và retention yêu cầu.
- Sử dụng compression/storage settings phù hợp sau benchmark.
- Giám sát autovacuum, WAL, replication lag, disk.
- Đặt alerts khi audit grows bất thường.

**Không đánh đổi tính đúng đắn lấy tốc độ bằng cách tự disable trigger khi tải cao**, trừ khi business đã chấp thuận một audit gap có cơ chế thay thế và provenance rõ.

## 65. Index cho audit: không index toàn bộ JSONB mặc định

Truy vấn phổ biến:

```sql
SELECT audit_id, operation, actor_id, occurred_at
FROM lesson_audit.account_audit
WHERE tenant_id = 10
  AND account_id = 1001
ORDER BY audit_id DESC
LIMIT 50;
```

B-tree `(tenant_id,account_id,audit_id DESC)` đã phù hợp.

Nếu cần tìm tất cả events theo actor:

```sql
SELECT *
FROM lesson_audit.account_audit
WHERE actor_id = 'editor-42'
ORDER BY occurred_at DESC;
```

có thể cân nhắc B-tree trên `(actor_id, occurred_at DESC)` sau khi đo workload.

### Khi nào cần GIN trên JSONB?

Nếu có truy vấn containment nhiều keys trong `old_row`/`new_row`, GIN có thể phù hợp, nhưng index có thể lớn và làm tăng write cost. Đừng tạo GIN trên cả hai snapshots chỉ vì kiểu là JSONB.

Không index plaintext PII nếu không có nhu cầu/quyền truy cập rõ ràng.

## 66. Partition audit theo thời gian

Khi log tăng nhanh và có thời hạn lưu, bảng audit có thể được partition theo `occurred_at` hoặc một khóa phân vùng được chọn theo vận hành.

### Lợi ích

- Retention dễ quản lý bằng việc tách/xóa partitions theo chính sách.
- Có thể giảm phạm vi truy vấn khi lọc thời gian.
- Tăng khả năng tổ chức vacuum/index maintenance.

### Đổi lại

- Partition key phải được xét cùng **UNIQUE/PRIMARY KEY constraints** của partitioned table.
- Global uniqueness của `audit_id` không tự có nghĩa giống một bảng thường trong mọi partitioning scheme.
- Clock-based partitioning dùng event timestamp, không phải commit timestamp.
- Cần kế hoạch tạo partitions tiếp theo trước khi tới kỳ mới.
- Không được xóa partition trước retention policy.

Không chuyển ngay bảng lab sang partitioned table nếu chưa có yêu cầu thật; mục tiêu phần này là giúp người học hiểu trade-off.

## 67. Retention và quyền xóa lịch sử

Audit log có thể phải giữ 90 ngày, 1 năm hoặc lâu hơn tùy nghiệp vụ/quy định. Không có một thời hạn chung cho mọi hệ thống.

### Chính sách cần mô tả

- Loại dữ liệu nào được lưu.
- Thời hạn giữ từng loại.
- Ai được yêu cầu purge và phê duyệt.
- Cách chứng minh purge đã thực hiện hợp lệ.
- Cách tách backup có retention khác audit table chính.
- Có legal hold nào phải giữ một số records không.
- Cách bảo đảm API không trả events sau khi hết quyền truy cập.

### Rủi ro

Một auditor với quyền xóa trực tiếp có thể phá lịch sử. Ngược lại, không có retention có thể vi phạm yêu cầu data minimization. Nên dùng workflow có logging độc lập và phân tách nhiệm vụ cho các thao tác purge.

## 68. Append-only ở mức ứng dụng không phải tamper-proof

Ta có thể REVOKE UPDATE/DELETE trên audit table đối với role thông thường, nhưng:

- Owner/superuser có thể có quyền rộng.
- Administrator có thể drop/disable trigger.
- Backup restore có thể thay toàn bộ database state.
- Một role bị chiếm quyền có thể thao túng chính sách hoặc dữ liệu.

**Append-only với application role** là kiểm soát thiết thực, nhưng không phải một bằng chứng mật mã không thể sửa đổi.

### Nếu cần chống sửa đổi

Cân nhắc:

- Gửi audit stream tới hệ thống độc lập với credentials/ownership khác.
- Immutable/WORM object storage theo yêu cầu.
- Chữ ký số/hash chain có **external anchoring** và key management phù hợp.
- Database logs/DDL monitoring được chuyển ra ngoài và bảo vệ.
- Kiểm toán quyền/đổi cấu hình.

Hash của rows lưu **cùng database** và có thể được role đặc quyền tính lại sẽ không tự chống được kẻ sở hữu database.

## 69. Audit và hệ thống event-driven

Row audit chỉ nên phản ánh dữ liệu của bảng nguồn; không nên từ trigger gửi thẳng HTTP/webhook/message ra hệ ngoài mà kỳ vọng transaction rollback cũng “thu hồi” side effect.

### Transactional outbox

Một mô hình tin cậy hơn:

```text
BEGIN
  UPDATE business table
  INSERT audit table (trigger)
  INSERT outbox event
COMMIT

Outbox publisher đọc committed events
  → publish tới broker
  → consumer xử lý idempotent
```

Nếu transaction rollback, audit/outbox events transactional cũng rollback. Nếu commit nhưng publisher tạm lỗi, outbox vẫn có thể được đọc lại.

### Audit event khác business event

`UPDATE status = 'PAID'` không tự chứng minh event `PaymentCaptured` đã xảy ra đúng quy trình tài chính. Domain events phải phản ánh nghiệp vụ/validation và có payload contract riêng.

## 70. Dùng logical decoding/CDC để bổ sung audit

WAL-based CDC có thể theo dõi thay đổi theo transaction/replication protocol, hữu ích khi cần:

- Đồng bộ search/index/analytics.
- Ghi thay đổi sang kho bên ngoài.
- Kiểm tra audit gaps ở tầng khác với row trigger.
- Gắn sự kiện với luồng commit của server.

### Nhưng CDC cũng cần vận hành

- Replication slots có thể giữ WAL và gây đầy disk nếu consumer chậm.
- Không phải mọi DDL đều nằm trong payload như mong muốn.
- Quyền truy cập replication rất nhạy cảm.
- Schema changes cần xử lý.
- Deletes cần replica identity phù hợp để có dữ liệu cũ mong muốn.
- Cần idempotency/ordering và xử lý failover.

CDC không tự chứng minh actor ứng dụng; nhiều thay đổi từ cùng DB role vẫn cần attribution từ nguồn đáng tin.

## 71. Sự khác biệt với pgAudit và server logs

Row trigger có thể trả lời “hàng 1001 trước/sau là gì?”. Một extension audit ở cấp SQL statement hoặc server logs có thể trả lời “role nào đã chạy câu UPDATE/DDL/SELECT?” theo cấu hình.

### Kết hợp khi nào?

- Muốn xem **dữ liệu trước/sau**: row audit trigger.
- Muốn thấy **SELECT/read attempts**: PostgreSQL row trigger không chạy khi SELECT; cần logs/extension hoặc application access logs.
- Muốn ghi **DDL và thay đổi quyền**: server logs/event trigger/migration logs.
- Muốn chứng cứ ngoài database: external append-only logging.

Không dùng row audit như giải pháp duy nhất cho yêu cầu “theo dõi tất cả thao tác đọc dữ liệu nhạy cảm”, vì SELECT không phát sinh INSERT/UPDATE/DELETE trigger trên bảng.

## 72. Replay history cần điều kiện gì?

Trong một hệ thống có **đầy đủ event chain từ baseline**, có thể dùng `new_row` của những events liên tiếp để hình dung state.

Nhưng muốn khôi phục trạng thái tại mốc thời gian T phải giải quyết:

- Chọn **thời điểm event** hay **thời điểm commit**?
- Đảm bảo thứ tự commit toàn cục hoặc theo entity?
- Account có thể bị DELETE rồi INSERT lại cùng ID không?
- Có events bị thiếu trong migration/replication?
- Schema JSONB có thay đổi không?
- Có cần xử lý transactions nhiều entity cùng lúc?

### Phân biệt với point-in-time recovery

Audit history không tự thay backup/WAL PITR. Nếu mục tiêu là khôi phục toàn database về một thời điểm, dùng công cụ backup/restore/PITR được quản lý phù hợp. Audit chủ yếu phục vụ điều tra và các truy vấn lịch sử nghiệp vụ.

## 73. Bổ sung business revision và expected state

Với nhu cầu temporal history nghiêm ngặt hơn, có thể lưu:

```text
entity_id
row_version
old_row
new_row
actor
recorded_at
transaction_id
```

Các events cùng entity có thể được kiểm tra:

```text
new_version = old_version + 1
previous.new_row = next.old_row
```

Nếu nguồn có optimistic locking, ứng dụng có thể reject update từ bản cũ, audit chỉ ghi chuỗi hợp lệ đã commit.

### Khi nào chưa đủ?

Version trong row ghi thứ tự thay đổi **theo entity**, nhưng không là một global commit sequence cho nhiều entities. Cần thêm transaction/order modeling khi bài toán yêu cầu khôi phục nhất quán nhiều bảng cùng thời điểm.

## 74. Error injection để kiểm chứng audit bắt buộc

Một hệ thống coi audit là điều kiện của commit nên kiểm thử khi audit insert thất bại:

1. Trong staging, cấu hình một constraint hoặc quyền khiến audit trigger INSERT lỗi.
2. Thử UPDATE nguồn.
3. Xác nhận UPDATE thất bại và trạng thái nguồn không thay đổi sau rollback.
4. Xác nhận API trả lỗi, không báo thành công.
5. Khôi phục cấu hình audit rồi thử lại.

### Không phá production để test

Không tự REVOKE quyền của trigger owner hoặc xóa bảng audit trong production chỉ để xác minh cơ chế fail-closed. Dùng staging/isolated test database, test transaction và fault injection có kiểm soát.

### Nguyên tắc

Nếu ứng dụng có cơ chế tự bắt lỗi audit và tiếp tục commit DML nguồn, nó đã thay đổi hợp đồng từ **audit bắt buộc** sang **best effort**. Quyết định này phải do business/security chấp thuận, không phải xử lý lỗi ngẫu nhiên.

## 75. Test race conditions và isolation levels

Các kịch bản cần chạy bằng ít nhất hai connections:

- Hai UPDATE cùng hàng, transaction này giữ lock transaction kia chờ.
- Một UPDATE thành công, transaction còn lại serialization failure ở isolation thích hợp.
- Một DELETE tranh chấp với UPDATE.
- UPDATE hàng khác nhau trong cùng tenant.
- Transaction dài giữ snapshot cũ trong khi transaction khác commit.
- Một batch UPDATE có xen DML khác.

### Assertions

- Audit chỉ có events của transactions đã commit.
- `OLD`/`NEW` khớp với row versions mà statement thực sự xử lý.
- Không có event của transaction bị rollback.
- Không có thao tác sửa nguồn thành công mà thiếu audit khi trigger enabled và quyền đúng.
- Không lộ audit của tenant khác.

Thử tải cần đo deadlocks, lock waits, WAL, p95 write latency và audit volume; không chỉ xác nhận một chuỗi UPDATE tuần tự.

## 76. Kiểm tra bằng property-based testing

Thay vì chỉ vài test “giá trị 500000 → 700000”, một test harness có thể sinh ngẫu nhiên:

- INSERT nhiều accounts với tenant IDs hợp lệ.
- UPDATE display_name/status/credit_limit.
- DELETE một số accounts.
- UPDATE no-op.
- Transaction rollback ở các điểm khác nhau.
- Các trường hợp invalid constraints.

Sau mỗi transaction đã commit, kiểm tra:

1. Constraints nguồn luôn đúng.
2. Audit events có shape đúng `operation`.
3. Không còn sự kiện từ transactions đã rollback.
4. State cuối có thể đối soát với snapshots trong phạm vi test.
5. Events không vượt tenant mà test đang thao tác.
6. Các đường DML dùng trong ứng dụng đều được bao phủ.

### Vì sao property-based testing hữu ích?

Nó tìm được tổ hợp edge cases mà kiểm thử từng ví dụ khó nghĩ tới: no-op sau update thật, xóa rồi tạo lại, nhiều hàng cùng transaction, NULL fields, schema additions.

Không chạy property-based stress test trực tiếp trên production; dùng môi trường cô lập và seed tái lập.

## 77. Test SQL shape của event

Kiểm tra cấu trúc audit:

```sql
SELECT
    audit_id,
    operation,
    jsonb_typeof(old_row) AS old_json_type,
    jsonb_typeof(new_row) AS new_json_type,
    old_row IS NULL AS old_is_sql_null,
    new_row IS NULL AS new_is_sql_null
FROM lesson_audit.account_audit
ORDER BY audit_id;
```

Với row snapshots từ `to_jsonb(record)`, phần hiện diện thường là JSONB object; trường không áp dụng `OLD/NEW` được để **SQL NULL** theo CHECK constraint.

### Không nhầm JSON null và SQL NULL

`old_row IS NULL` kiểm tra SQL NULL của cả cột.

`old_row = 'null'::jsonb` là một JSONB value `null` được lưu như dữ liệu trong cột không NULL. Bảng lab không dùng JSONB null như “không có snapshot” vì muốn sự phân biệt rõ.

## 78. Kiểm chứng tenant ID trong JSONB snapshot

Với audit event INSERT/UPDATE, metadata tenant và tenant trong new_row nên khớp:

```sql
SELECT
    audit_id,
    tenant_id,
    new_row ->> 'tenant_id' AS tenant_in_snapshot
FROM lesson_audit.account_audit
WHERE new_row IS NOT NULL
  AND (
      new_row ->> 'tenant_id'
  ) IS DISTINCT FROM tenant_id::text;
```

Đối với DELETE, so với old_row:

```sql
SELECT audit_id, tenant_id
FROM lesson_audit.account_audit
WHERE operation = 'DELETE'
  AND (old_row ->> 'tenant_id')
      IS DISTINCT FROM tenant_id::text;
```

### Chú ý

Đây là một test nhất quán metadata/snapshot, không tự kiểm chứng actor và tenant authorization. Nếu cả metadata lẫn snapshot bị người có quyền cao sửa cho khớp, truy vấn không phát hiện gian lận; cần provenance độc lập khi threat model yêu cầu.

## 79. Kiểm tra trạng thái UPDATE bằng SQL assertion

Một `DO` block có thể xác nhận audit UPDATE gần nhất có old/new không trùng:

```sql
DO $$
DECLARE
    v_mismatch_count BIGINT;
BEGIN
    SELECT count(*)
    INTO v_mismatch_count
    FROM lesson_audit.account_audit
    WHERE operation = 'UPDATE'
      AND old_row IS NOT DISTINCT FROM new_row;

    IF v_mismatch_count <> 0 THEN
        RAISE EXCEPTION
            'Found % audit UPDATE events with no value change',
            v_mismatch_count;
    END IF;
END;
$$;
```

Theo chính sách trigger trong lab, UPDATE không có khác biệt row bị bỏ qua, nên không có `UPDATE` event với `old_row=new_row`.

### Chính sách có thể khác

Nếu sản phẩm chọn ghi cả attempted UPDATE dù values không đổi, assertion này không còn là invariant đúng. Test phải phản ánh **contract được công bố**, không áp đặt một sở thích kỹ thuật cho mọi hệ thống.

## 80. Giám sát trigger coverage và audit gap

Những chỉ số đáng theo dõi:

| Chỉ số | Tại sao |
|---|---|
| Số audit events theo bảng và operation | Phát hiện biến động bất thường |
| Audit insert errors | Đảm bảo thay đổi nguồn không commit thiếu log |
| Trigger enabled state | Phát hiện disable/DDL trái phép |
| Source rows và latest audit mismatch | Tín hiệu có audit gap |
| DML volume so với audit volume | Phát hiện tỷ lệ event không hợp lý |
| Disk/WAL growth | Dự báo dung lượng |
| p95/p99 write latency | Phát hiện trigger overhead |
| Replication/CDC lag | Kiểm soát pipeline đối soát ngoài |
| Audit query latency | Hỗ trợ điều tra kịp thời |
| Unauthorized access attempts | Kiểm soát quyền đọc/sửa log |

### Phân biệt metric “expected difference”

Vì trigger lab bỏ no-op, số `UPDATE` statements có thể **lớn hơn** số `UPDATE` audit events; một statement có thể sửa nhiều rows. Không kỳ vọng tỉ lệ 1:1 giữa số SQL statements và audit rows. Cần biết mô hình row-vs-statement và chính sách event để diễn giải đúng.

## 81. Soft delete có khác hard delete?

Một hệ thống có thể dùng `status='CLOSED'` thay vì DELETE vật lý:

```sql
UPDATE lesson_audit.accounts
SET status = 'CLOSED',
    updated_at = clock_timestamp()
WHERE tenant_id = 10
  AND account_id = 1001;
```

Theo trigger hiện tại, đây là sự kiện **UPDATE**, không phải DELETE. Snapshot mới chứa `status='CLOSED'`; row vẫn tồn tại trong bảng nguồn.

### Vì sao không biến nó thành DELETE audit event?

Loại sự kiện `TG_OP` phản ánh thao tác SQL thực. Nếu muốn phân biệt **business transition** như `AccountClosed`, lưu thêm `business_event_type` hoặc một business event riêng, thay vì ghi sai rằng row đã bị DELETE vật lý.

Một tài khoản có thể từ CLOSED trở lại ACTIVE nếu nghiệp vụ cho phép; lịch sử sẽ chứa một UPDATE khác.

## 82. Dùng view hoặc INSTEAD OF trigger

Ứng dụng có thể expose một view giới hạn cột:

```sql
CREATE OR REPLACE VIEW lesson_audit.public_accounts AS
SELECT
    account_id,
    tenant_id,
    display_name,
    status
FROM lesson_audit.accounts;
```

Khi một thao tác qua view thực sự gây **UPDATE/INSERT/DELETE trên bảng nguồn**, row trigger của bảng nguồn có thể ghi audit cho các thay đổi ấy.

### Khi nào phức tạp?

Một view phức tạp có thể cần `INSTEAD OF` trigger hoặc rewrite rules để chuyển thao tác thành DML lên bảng nguồn. Lúc đó cần kiểm tra:

- Có đường ghi nào chỉ cập nhật bảng phụ mà không đổi bảng accounts?
- Một command qua view có thực hiện nhiều DML nguồn?
- Có thể phát sinh nhiều audit events cho một business request không?
- `OLD`/`NEW` của view trigger khác gì snapshots của base table?

**Không coi trigger gắn trên view là bằng chứng đủ**, nếu ứng dụng vẫn có đường ghi trực tiếp vào base table hoặc bảng khác. Đặt row audit ở **bảng chuẩn cần bảo vệ** và kiểm tra tất cả entry points.

## 83. Temporal query “trạng thái ở thời điểm T”

Một truy vấn minh họa xem snapshot mới nhất có `occurred_at <= T`:

```sql
WITH candidates AS (
    SELECT
        audit_id,
        tenant_id,
        account_id,
        operation,
        new_row,
        occurred_at,
        row_number() OVER (
            PARTITION BY tenant_id, account_id
            ORDER BY occurred_at DESC, audit_id DESC
        ) AS rn
    FROM lesson_audit.account_audit
    WHERE occurred_at <=
        TIMESTAMPTZ '2026-11-01 00:00:00+07'
)
SELECT
    tenant_id,
    account_id,
    new_row,
    occurred_at
FROM candidates
WHERE rn = 1
  AND operation <> 'DELETE';
```

### Quan trọng: đây chỉ là phép xấp xỉ theo event timestamp

`occurred_at` là thời điểm trigger chạy, không phải thời điểm commit. Một transaction có thể ghi audit event trước T nhưng commit **sau T**, nên truy vấn trên không luôn tái dựng snapshot database đã visible chính xác ở T.

Nếu cần **system-time temporal queries** với tính nhất quán chặt dưới concurrency, hãy thiết kế commit-aware history hoặc giải pháp temporal/CDC/backup phù hợp. Không dùng kết quả query đơn giản này làm bằng chứng pháp lý cho state tại một mốc commit tuyệt đối.

## 84. Audit và idempotent requests

Một HTTP request có thể bị retry do timeout. Nếu backend thực hiện:

```sql
UPDATE lesson_audit.accounts
SET credit_limit = credit_limit + 10000
WHERE account_id = 1001;
```

hai lần, audit sẽ ghi **hai events UPDATE** và hạn mức tăng gấp đôi.

### Nguyên nhân

Trigger audit đúng: có hai thay đổi đã commit. Vấn đề là **application thiếu idempotency** cho command nghiệp vụ.

### Cách xử lý

- Dùng request ID/idempotency key.
- Lưu kết quả xử lý theo key trong transaction.
- Với thay đổi có version, dùng expected version/conditional update.
- Không tự gộp hai audit entries giống nhau thành một để “sửa” lỗi request retry.

Audit giúp phát hiện retry duplicate, nhưng không tự bảo vệ nghiệp vụ khỏi nó.

## 85. Bộ truy vấn chẩn đoán nhanh

### A — Tổng hợp số lượng sự kiện theo operation

```sql
SELECT
    tenant_id,
    operation,
    count(*) AS events
FROM lesson_audit.account_audit
GROUP BY tenant_id, operation
ORDER BY tenant_id, operation;
```

### B — Một entity có những sự kiện nào?

```sql
SELECT
    audit_id,
    operation,
    actor_id,
    old_row ->> 'status' AS old_status,
    new_row ->> 'status' AS new_status,
    occurred_at
FROM lesson_audit.account_audit
WHERE tenant_id = 10
  AND account_id = 1001
ORDER BY audit_id;
```

### C — Có event sai shape không?

```sql
SELECT audit_id, operation, old_row, new_row
FROM lesson_audit.account_audit
WHERE
    (operation = 'INSERT'
     AND (old_row IS NOT NULL OR new_row IS NULL))
    OR
    (operation = 'UPDATE'
     AND (old_row IS NULL OR new_row IS NULL))
    OR
    (operation = 'DELETE'
     AND (old_row IS NULL OR new_row IS NOT NULL));
```

Trong lab, CHECK constraint đã ngăn các event sai shape này khi INSERT bình thường. Query vẫn hữu ích khi điều tra dữ liệu di chuyển từ hệ khác hoặc sau migration; không phải một cơ chế chống owner bypass.

### D — Có event UPDATE không đổi row không?

```sql
SELECT audit_id, account_id
FROM lesson_audit.account_audit
WHERE operation = 'UPDATE'
  AND old_row IS NOT DISTINCT FROM new_row;
```

Theo chính sách lab, kỳ vọng không có rows.

### E — Trigger có đang được bật?

```sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid, true) AS trigger_ddl
FROM pg_catalog.pg_trigger
WHERE tgrelid = 'lesson_audit.accounts'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
```

### F — Lịch sử của một actor

```sql
SELECT
    audit_id,
    tenant_id,
    account_id,
    operation,
    occurred_at
FROM lesson_audit.account_audit
WHERE actor_id = 'editor-42'
ORDER BY occurred_at DESC, audit_id DESC
LIMIT 100;
```

Những câu query này là công cụ **điều tra**, không chứng minh audit đầy đủ nếu các logs có thể bị sửa/xóa bởi role có quyền cao.

## 86. Runbook khi phát hiện thiếu sự kiện audit

1. Xác định bảng, entity ID, tenant, khoảng thời gian và symptom cụ thể.
2. Xem `pg_trigger`: trigger có tồn tại, enabled, đúng definition không?
3. Kiểm tra DML path: UPDATE, DELETE, TRUNCATE, UPSERT, MERGE, COPY, partition, direct admin scripts.
4. Kiểm tra thời điểm rollout/audit baseline và migrations.
5. Xem server logs/DDL logs/CDC nếu có.
6. Kiểm tra role/owner có thể disable/drop triggers hay write trực tiếp không.
7. Đối soát current rows với latest audit trong một snapshot phù hợp.
8. Phân biệt no-op bị bỏ theo chính sách với sự kiện thật bị thiếu.
9. Ghi nhận khoảng thời gian audit không chắc chắn và ảnh hưởng người dùng.
10. Khôi phục từ nguồn được chứng thực; nếu không thể, công khai đánh dấu gap và tạo correction record có provenance.

### Không “sửa lịch sử” bằng cách bịa dữ liệu

Nếu chỉ biết state hiện tại 700000 mà không biết nó đổi từ giá trị nào, đừng tạo event giả “500000 → 700000 bởi editor-X” để lấp dòng lịch sử. Một audit trail đáng tin cần cho phép biểu diễn **unknown** và **reconstructed from evidence**, không tự đổi phỏng đoán thành sự thật.

## 87. Runbook khi ghi dữ liệu chậm sau khi bật audit

1. Đo p50/p95/p99 latency của INSERT/UPDATE/DELETE trước/sau triển khai.
2. Kiểm tra tần suất events và số bytes trung bình của old/new snapshots.
3. Xem số lượng indexes trên audit table và chi phí duy trì.
4. Đo WAL volume, disk usage và checkpoint/replication lag.
5. Kiểm tra các cột lớn/TOAST, JSONB conversion và trigger overhead.
6. Kiểm tra contention trên indexes/partition/transaction locks.
7. Thử statement-level transition tables nếu workload bulk và semantics cho phép.
8. Cân nhắc giảm fields, bỏ no-op, batch strategies hoặc thiết kế projection khác.
9. Không bỏ audit trong production mà không có chấp thuận thay đổi chính sách.
10. Kiểm thử lại tính đúng đắn và quyền sau mọi tối ưu hóa.

### Đừng chỉ tối ưu trigger body

Một trigger function rất ngắn vẫn có thể tạo hàng chục MB audit WAL cho một batch. Bài toán hiệu năng gồm **storage/indexing/transaction/replication**, không chỉ thời gian chạy PL/pgSQL.

## 88. Bảng quyết định kiến trúc

| Nhu cầu | Giải pháp thường phù hợp | Giới hạn |
|---|---|---|
| Lưu OLD/NEW cho DML đã commit | AFTER ROW audit trigger | Không thấy rollback hoặc SELECT |
| Bulk UPDATE rất lớn, xử lý set-based | AFTER STATEMENT + transition tables | Có constraints về loại trigger và ghép row |
| Chặn vi phạm trước ghi | BEFORE trigger + constraints | Không thay hậu kiểm audit |
| Ghi business event sang broker | Transactional outbox | Cần publisher/consumer |
| Lưu câu SQL/DDL/access attempts | PostgreSQL logs/pgAudit/event triggers phù hợp | Không có đủ row snapshots như audit table |
| Truy vết thay đổi phục vụ data pipeline | Logical decoding/CDC | Cần replication infrastructure |
| Lịch sử có thời gian hiệu lực | Versioned/temporal model | Cần định nghĩa valid time và commit/system time |
| Bằng chứng chống sửa bởi DB admin | Hệ thống ngoài độc lập, signed/anchored logs | Chi phí bảo mật/vận hành |
| Chỉ cần biết trạng thái hiện tại | Bảng typed bình thường | Không có lịch sử thay đổi |

Không có lựa chọn duy nhất cho mọi mục tiêu. Bắt đầu từ câu hỏi **“cần chứng minh điều gì và trước ai?”** trước khi quyết định công cụ.

## 89. Bộ bài tập thực hành

### Bài 1 — Phân biệt state và history

Một bảng khách hàng chỉ lưu `status` hiện tại. Khi status đổi ba lần, bạn còn biết được những gì nếu không có audit? Đề xuất dữ liệu cần ghi.

### Bài 2 — Trigger hay RULE

Giải thích vì sao muốn lưu `OLD` và `NEW` theo từng hàng thì nên dùng row trigger thay vì query rewrite rule.

### Bài 3 — BEFORE và AFTER

Một BEFORE trigger trim display_name. Tại sao AFTER audit thường phù hợp hơn để ghi trạng thái đã áp dụng?

### Bài 4 — Row-level và statement-level

Một UPDATE tác động 120 hàng. So sánh số lần gọi trigger function giữa `FOR EACH ROW` và `FOR EACH STATEMENT`.

### Bài 5 — Tạo bảng nguồn

Tạo bảng tài khoản có primary key, tenant_id, display_name, credit_limit và status. Thêm CHECK credit_limit không âm.

### Bài 6 — Thiết kế audit table

Thêm các cột audit_id, entity key, tenant, operation, actor, transaction_id, occurred_at, old/new JSONB. Tại sao không dùng account_id làm primary key của audit?

### Bài 7 — Shape constraints

Viết CHECK đảm bảo INSERT không có old_row, DELETE không có new_row và UPDATE có cả hai.

### Bài 8 — AFTER trigger function

Viết function dùng `TG_OP`, `OLD`, `NEW` và `to_jsonb` để ghi lịch sử INSERT/UPDATE/DELETE.

### Bài 9 — Chèn bản ghi đầu tiên

INSERT một account mới rồi kiểm tra audit có một event INSERT với new_row và old_row SQL NULL.

### Bài 10 — Đổi hạn mức

UPDATE credit_limit từ 500000 lên 700000, sau đó truy vấn `old_row ->> 'credit_limit'` và `new_row ->> 'credit_limit'`.

### Bài 11 — DELETE

Xóa một account trong transaction thử nghiệm, xác minh old_row vẫn có snapshot trong audit và new_row là SQL NULL.

### Bài 12 — No-op UPDATE

Chạy `UPDATE ... SET status=status`. Theo chính sách skip no-op của bài, audit event count có thay đổi không?

### Bài 13 — Cột kỹ thuật updated_at

Chỉ đổi `updated_at`. Khi so toàn row, trigger có ghi event không? Hãy viết chiến lược chỉ so cột nghiệp vụ.

### Bài 14 — Giữ khóa bất biến

Viết BEFORE UPDATE trigger ngăn đổi account_id và tenant_id. Vì sao quan trọng khi history partition theo entity key?

### Bài 15 — Rollback

Trong BEGIN, UPDATE một account rồi xem audit. ROLLBACK; kiểm tra cả source state và audit events sau rollback.

### Bài 16 — Fail closed

Trong database staging, mô phỏng lỗi chèn audit. Vì sao thay đổi nguồn phải bị hủy nếu audit là bắt buộc?

### Bài 17 — Kiểm chứng snapshot

Lưu `to_jsonb(account)` trước UPDATE và sau UPDATE; so với old_row/new_row của event vừa sinh bằng `IS DISTINCT FROM`.

### Bài 18 — Test nhiều hàng

UPDATE tất cả tài khoản ACTIVE trong một tenant. Đếm số row events được tạo; cần chú ý những hàng vốn đã có status mong muốn.

### Bài 19 — Query lịch sử

Viết truy vấn lịch sử account 1001 theo audit_id, gồm actor, operation, old/new và occurred_at.

### Bài 20 — Liệt kê trường thay đổi

Dùng `jsonb_each` và `FULL JOIN` để so keys old/new trong event UPDATE; phân biệt key thiếu và JSON null.

### Bài 21 — Latest snapshot

Dùng `DISTINCT ON (tenant_id,account_id)` lấy event cuối theo audit_id rồi so `new_row` với current source row. Kể tên các giả định của phép đối soát.

### Bài 22 — Chuỗi version

Dùng `LAG(new_row)` theo account_id/audit_id để tìm chỗ old_row không khớp previous new_row. Vì sao đây không phải chứng minh commit-order toàn cục?

### Bài 23 — Transaction ID

UPDATE nhiều hàng trong một transaction, group audit theo transaction_id. Transaction ID khác request ID ra sao?

### Bài 24 — Time semantics

So `now()`, `statement_timestamp()` và `clock_timestamp()`. Tại sao cả ba không tự là commit timestamp?

### Bài 25 — Concurrency

Mở hai connections cùng cập nhật account 1001. Quan sát row locks, audit snapshots và rollback nếu một transaction thất bại.

### Bài 26 — Lost update

Hai clients đọc cùng credit_limit cũ và UPDATE bằng giá trị tuyệt đối. Trigger có tự ngăn lost update không? Đề xuất giải pháp.

### Bài 27 — Transition tables

Tạo statement-level AFTER UPDATE trigger trên batch_items với `REFERENCING OLD TABLE/NEW TABLE`. INSERT ... SELECT lịch sử bằng JOIN khóa bất biến.

### Bài 28 — Statement tác động 0 rows

Chạy UPDATE không match row trên bảng có statement trigger. Trigger function có chạy không, và có event rows không?

### Bài 29 — UPSERT

Thử `INSERT ... ON CONFLICT DO UPDATE` trên một account có sẵn. Ghi nhận event row-level, rồi thử DO NOTHING.

### Bài 30 — TRUNCATE

Vì sao `TRUNCATE` không tạo per-row DELETE audit? Viết BEFORE TRUNCATE statement trigger để ngăn trên bảng được kiểm toán.

### Bài 31 — Triggers disabled

Kiểm tra `pg_trigger.tgenabled`. Nếu role đủ quyền disable trigger, dữ liệu bị sửa trong thời gian đó có được truy vết từ audit table không?

### Bài 32 — SECURITY DEFINER

Nêu các điều kiện để trigger function chạy với quyền owner nhưng không tạo lỗ hổng search_path/privilege escalation.

### Bài 33 — RLS và multi-tenant

Một tài khoản tenant 20 có audit events. Viết điều kiện truy vấn để tenant 10 không xem được, giải thích vì sao client-provided tenant_id không đủ.

### Bài 34 — Actor ID trong connection pool

Vì sao nên dùng `SET LOCAL`/`set_config(...,true)`? Nếu untrusted user có SQL access, custom GUC có thể là bằng chứng định danh tuyệt đối không?

### Bài 35 — JDBC/Spring transaction

Viết repository/service đặt actor context và UPDATE nguồn trong **cùng connection/transaction**. Kiểm tra audit khi commit và rollback.

### Bài 36 — Schema migration

Thêm cột external_ref sau khi hệ thống đã ghi history. Phân biệt old events thiếu key với new events có key; thiết kế schema_version.

### Bài 37 — Audit và PII

Một bảng có email, token bí mật và địa chỉ. Thiết kế audit minimization/redaction, quyền đọc và retention.

### Bài 38 — Hiệu năng

Mô phỏng 100.000 UPDATE ở staging; đo WAL, audit rows, index size và write latency. Nêu cách giảm chi phí không đánh mất contract.

### Bài 39 — Tamper-evident audit

Vì sao một hash chain lưu hoàn toàn trong database nguồn chưa chống được superuser? Đề xuất external anchoring/immutable storage/role separation.

### Bài 40 — Thiết kế tổng hợp

Một hệ thống giao dịch đa tenant cần:

- Ghi mọi thay đổi INSERT/UPDATE/DELETE đã commit.
- Không ghi UPDATE no-op của business fields.
- Có lịch sử hạn mức, người yêu cầu, request ID.
- Chặn TRUNCATE và unauthorized modifications.
- Hỗ trợ bulk UPDATE, UPSERT và CDC.
- Cho phép điều tra người dùng và kiểm chứng state.
- Giữ log 18 tháng theo chính sách tổ chức.

Hãy trình bày:

1. Schema nguồn và audit, khóa, constraints và indexes.
2. AFTER ROW trigger function với OLD/NEW/TG_OP và JSONB.
3. Thiết kế actor context, quyền truy cập và SECURITY DEFINER/RLS.
4. Kiểm thử insert/update/delete/no-op/rollback/concurrency.
5. Đối soát current state và event chain, với các giả định về commit order.
6. Biện pháp cho TRUNCATE, disabled triggers, migrations, partitions và bulk paths.
7. Retention, encryption/redaction, monitoring audit gaps và capacity planning.
8. Khi nào cần thêm outbox, CDC, server logs và hệ audit độc lập chống sửa đổi.

## Kết luận

**Ghi lịch sử bằng PostgreSQL trigger là một cách hiệu quả để duy trì dấu vết dữ liệu trước/sau thay đổi ngay trong transaction nguồn.** Với `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW`, trigger có thể dùng `TG_OP`, `OLD` và `NEW` để ghi snapshots `jsonb` cùng khóa thực thể, tenant, actor, transaction ID và thời điểm ghi.

Để **kiểm chứng tính đúng đắn**, không chỉ xem event đã được chèn. Hãy viết invariants và tests cho INSERT/UPDATE/DELETE, no-op, nhiều hàng, rollback, lỗi constraint, đồng thời đối soát `old_row`/`new_row` với các phiên bản thực của hàng nguồn. Khi đọc một chuỗi events, phân biệt **event time**, **transaction time**, **commit order** và số thứ tự identity; một `audit_id` lớn hơn không tự chứng minh transaction commit muộn hơn.

Trigger audit có phạm vi rõ: **không ghi lại những transaction rollback**, không bắt SELECT, không tạo per-row DELETE events cho TRUNCATE, và có thể bị bypass bởi quyền/replication/DDL theo cơ chế server. Nếu compliance đòi hỏi chống sửa đổi bởi DBA hoặc ghi cả failed attempts, cần kết hợp server logs, CDC và một hệ lưu audit độc lập được bảo vệ.

Cuối cùng, bảo vệ audit như dữ liệu nhạy cảm: tránh sao chép PII không cần thiết, hạn chế role được sửa/xóa, cấu hình `SECURITY DEFINER`/`search_path`/RLS đúng, quản lý context từ connection pool, đo WAL/latency và áp dụng retention phù hợp. Một audit trail có giá trị phải **đúng về ngữ nghĩa, có thể kiểm chứng, minh bạch về giới hạn và được vận hành nhất quán** — chứ không chỉ là một bảng log có vài hàng JSONB.
