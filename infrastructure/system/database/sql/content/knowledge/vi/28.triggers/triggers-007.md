# Ghi lịch sử thay đổi và giới hạn của nhật ký bằng trigger trong SQL

Một bảng dữ liệu thường chỉ lưu **trạng thái hiện tại**. Sau khi cập nhật đơn hàng từ `NEW` sang `PAID`, ứng dụng thấy giá trị mới nhưng không tự biết trạng thái cũ, ai thực hiện thay đổi hoặc nó thuộc giao dịch nào. **Audit trigger** là một cách lưu dấu vết thay đổi dữ liệu: khi bảng nguồn được `INSERT`, `UPDATE` hoặc `DELETE`, trigger ghi một dòng vào bảng lịch sử.

~~~text
Đơn hàng trước                         Đơn hàng sau
id = 101                               id = 101
status = NEW           UPDATE          status = PAID
amount = 100000       ───────►         amount = 100000
                          │
                          ▼
                  AFTER UPDATE trigger
                          │
                          ▼
                 Bảng order_history
        record_id = 101, operation = UPDATE
        old_data = {"status":"NEW",...}
        new_data = {"status":"PAID",...}
        actor, time, transaction_id
~~~

Nhật ký như vậy hữu ích để truy vết một số thay đổi đã được ghi nhận, nhưng **không phải thiết bị giám sát tuyệt đối**. Trong PostgreSQL, INSERT vào bảng lịch sử do trigger thực hiện thường nằm **cùng transaction** với thay đổi bảng gốc. Nếu transaction rollback, dòng lịch sử cũng rollback. Trigger DML không tự theo dõi các câu `SELECT`, không bắt tất cả DDL hoặc `TRUNCATE` theo từng hàng, và không tự ngăn người có đặc quyền cao sửa/xóa dữ liệu audit.

Bài học thuộc module **Database SQL**, chương **Trigger**, với chủ đề **Ghi lịch sử thay đổi và giới hạn của nhật ký bằng trigger**. Ví dụ chính dùng PostgreSQL và dữ liệu thử nghiệm, sau đó đối chiếu các hướng tiếp cận trên MySQL/MariaDB, SQL Server, Oracle và SQLite.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích audit trail là gì và phân biệt **lịch sử thay đổi hàng** với **nhật ký truy cập**, **sự kiện nghiệp vụ** và **backup**.
2. Phân biệt trigger `BEFORE`/`AFTER`, `FOR EACH ROW`/`FOR EACH STATEMENT`.
3. Hiểu `OLD`, `NEW`, `TG_OP`, `TG_TABLE_NAME` trong trigger PostgreSQL.
4. Tạo bảng audit có khóa bản ghi, loại hành động, snapshot trước/sau, thời gian, actor và mã transaction.
5. Viết hàm `RETURNS TRIGGER` và gắn `AFTER INSERT OR UPDATE OR DELETE` vào bảng.
6. Thực hành INSERT/UPDATE/DELETE để kiểm tra dữ liệu JSONB `OLD`/`NEW`.
7. Hiểu tại sao **ROLLBACK hủy cả thay đổi lẫn lịch sử** và tại sao log không ghi được những thao tác chưa commit.
8. Phân biệt UPDATE tác động 0 hàng với UPDATE gán lại cùng giá trị.
9. Phân tích hạn chế với `SELECT`, `TRUNCATE`, DDL, bulk operations, trigger bị tắt và thay đổi từ các bảng khác.
10. Nhận ra giới hạn của `current_user`, `session_user`, custom session variables và `SECURITY DEFINER` khi ghi người thao tác.
11. Cân nhắc quyền truy cập, chống sửa log, dữ liệu nhạy cảm, retention, chi phí ghi và vòng đời schema.
12. Biết khi nào cần bổ sung **CDC**, **server audit log**, **temporal table**, **application log** hoặc **transactional outbox**.
13. Hoàn thành các bài tập về trigger audit và các tình huống nghiệp vụ.

## 2. Audit log cần trả lời những câu hỏi nào?

Một bản ghi lịch sử nên mô tả:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Bảng nguồn | Đối tượng nào bị tác động? | `orders` |
| Khóa bản ghi | Hàng nào bị tác động? | `101` |
| Hành động | DML nào xảy ra? | `UPDATE` |
| Dữ liệu cũ | Hàng trước đó ra sao? | `status = NEW` |
| Dữ liệu mới | Hàng sau đó ra sao? | `status = PAID` |
| Thời điểm | Trigger được thực thi khi nào? | Timestamp có múi giờ |
| Actor | Ai/ngữ cảnh nào được ghi nhận? | `employee-17` |
| Role database | Kết nối chạy dưới quyền nào? | `app_service` |
| Transaction | Những log nào cùng một giao dịch? | `txid` |
| Yêu cầu nghiệp vụ | Tại sao thay đổi? | `request_id`, `reason` |

Không phải mọi cột đều có sẵn trong trigger. `OLD` và `NEW` phản ánh hàng dữ liệu; lý do nghiệp vụ và người dùng cuối cần đến từ hệ thống gọi hoặc bảng yêu cầu được kiểm soát.

### 2.1. Các dạng lịch sử phổ biến

**Snapshot cũ/mới:** mỗi dòng audit lưu toàn bộ hàng trước và sau. Cách này dễ thực hiện với JSONB, nhưng lặp dữ liệu và có nguy cơ lưu bí mật.

**Chỉ cột thay đổi:** lưu tên cột cùng giá trị cũ/mới; giảm dữ liệu nếu UPDATE đổi ít cột, nhưng triển khai truy vấn và xử lý NULL phức tạp hơn.

**Sự kiện nghiệp vụ:** lưu `ORDER_PAID`, `ORDER_CANCELLED`, người duyệt, nguyên nhân. Nó giàu nghĩa nghiệp vụ hơn “cột status đổi”, nhưng thường do service hoặc quy trình nghiệp vụ tạo ra.

Một hệ thống có thể dùng nhiều dạng song song tùy mục đích. Audit lịch sử hàng **không phải** sổ cái tài chính, nhật ký đăng nhập hay kế hoạch sao lưu tự động.

## 3. Trigger hoạt động khi nào?

Trong PostgreSQL, trigger được gắn vào một bảng và sự kiện. Một trigger function có kiểu trả `TRIGGER` được gọi tự động khi thao tác thích hợp diễn ra.

~~~text
INSERT/UPDATE/DELETE bảng nguồn
                 │
                 ▼
        PostgreSQL xử lý DML
                 │
                 ▼
       AFTER FOR EACH ROW
                 │
           TG_OP là gì?
        ┌────────┼────────┐
        ▼        ▼        ▼
      INSERT   UPDATE    DELETE
       NEW    OLD+NEW     OLD
        └────────┼────────┘
                 ▼
            INSERT audit
                 │
                 ▼
        Cùng database transaction
~~~

### 3.1. OLD và NEW

| Sự kiện | `OLD` | `NEW` |
|---|---|---|
| INSERT | Không có bản ghi cũ | Hàng được chèn |
| UPDATE | Hàng trước cập nhật | Hàng sau cập nhật |
| DELETE | Hàng trước khi xóa | Không có hàng mới |
| TRUNCATE | Không có dữ liệu từng hàng qua row trigger | Không có dữ liệu từng hàng qua row trigger |

Trong PL/pgSQL, đừng đọc `OLD.id` trong nhánh INSERT hoặc `NEW.id` trong nhánh DELETE mà không kiểm soát loại thao tác.

### 3.2. BEFORE và AFTER

**BEFORE ROW** phù hợp khi cần kiểm tra, chuẩn hóa hoặc thay đổi `NEW` trước khi ghi; một BEFORE ROW trigger có thể trả `NULL` để bỏ qua thao tác trên hàng theo ngữ nghĩa PostgreSQL.

**AFTER ROW** phù hợp để ghi dấu vết hàng đã thực sự được xử lý, bao gồm tác động của những BEFORE triggers. Tuy nhiên, AFTER không có nghĩa dữ liệu đã commit. Nếu transaction rollback hoặc ràng buộc deferred không đạt, dữ liệu nguồn và audit cùng bị hủy.

### 3.3. FOR EACH ROW và FOR EACH STATEMENT

Nếu một UPDATE tác động 100 hàng:

- `FOR EACH ROW` có thể chạy **100 lần**, ghi 100 log.
- `FOR EACH STATEMENT` chạy cho **một statement**, kể cả khi statement không tác động hàng nào trong các trường hợp áp dụng.

Row trigger hữu ích nếu cần một history entry cho mỗi hàng. Statement trigger hữu ích nếu muốn biết có một lệnh được thực thi, hoặc dùng transition tables để xử lý nhiều hàng theo tập.

## 4. Tạo bộ dữ liệu thực hành PostgreSQL

Bài sử dụng **TEMP TABLE** trong một kết nối PostgreSQL thử nghiệm. Các bảng có tiền tố `lab355_`. Đừng chạy những ví dụ DELETE/TRUNCATE lên dữ liệu sản xuất.

### 4.1. Bảng đơn hàng

~~~sql
CREATE TEMP TABLE lab355_orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    note TEXT
);
~~~

Nạp trước khi gắn trigger, để không tạo log cho các hàng dữ liệu mẫu:

~~~sql
INSERT INTO lab355_orders
    (id, customer_id, status, amount, note)
VALUES
    (101, 1, 'NEW',       100000, NULL),
    (102, 2, 'PAID',      250000, 'Đã giao hàng'),
    (103, 1, 'CANCELLED',  80000, NULL),
    (104, 3, 'NEW',       120000, 'Chờ duyệt');
~~~

Kết quả:

| ID | Khách | Trạng thái | Số tiền | Ghi chú |
|---:|---:|---|---:|---|
| 101 | 1 | NEW | 100000 | NULL |
| 102 | 2 | PAID | 250000 | Đã giao hàng |
| 103 | 1 | CANCELLED | 80000 | NULL |
| 104 | 3 | NEW | 120000 | Chờ duyệt |

**Lưu ý:** dữ liệu tồn tại từ trước khi tạo trigger sẽ không tự được tạo log quá khứ. Production cần quyết định cách đánh dấu **trạng thái ban đầu/baseline** và thời điểm bắt đầu audit.

### 4.2. Bảng audit

~~~sql
CREATE TEMP TABLE lab355_order_history (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_data JSONB,
    new_data JSONB,
    actor_hint TEXT,
    session_role TEXT NOT NULL,
    effective_role TEXT NOT NULL,
    transaction_id BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
        DEFAULT clock_timestamp()
);
~~~

Ý nghĩa:

- `audit_id` định danh dòng audit, không tự chứng minh thứ tự COMMIT.
- `table_name` và `record_id` xác định hàng nguồn. Khi PK có thể đổi, cần lưu thêm khóa cũ.
- `action` ghi INSERT/UPDATE/DELETE.
- `old_data`, `new_data` lưu snapshot dạng JSONB.
- `actor_hint` là thông tin ứng dụng cung cấp, **chưa phải danh tính chống giả mạo**.
- `session_role` và `effective_role` ghi ngữ cảnh role PostgreSQL.
- `transaction_id` giúp nhóm những thay đổi trong cùng database transaction.
- `recorded_at` là lúc trigger ghi, không phải commit timestamp.

Bảng audit của bài là TEMP nên không bền vững qua hết session; audit production phải dùng bảng bền vững với quyền, chỉ mục, backup và retention thích hợp.

## 5. Tạo một trigger function cho ba sự kiện

Hàm này cần phân nhánh theo `TG_OP`:

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab355_capture_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_id INTEGER;
    v_old JSONB;
    v_new JSONB;
    v_actor TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_id := NEW.id;
        v_old := NULL;
        v_new := to_jsonb(NEW);

    ELSIF TG_OP = 'UPDATE' THEN
        v_id := NEW.id;
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);

    ELSIF TG_OP = 'DELETE' THEN
        v_id := OLD.id;
        v_old := to_jsonb(OLD);
        v_new := NULL;

    ELSE
        RAISE EXCEPTION 'Thao tác không hỗ trợ: %', TG_OP;
    END IF;

    v_actor := NULLIF(
        current_setting('app.actor_id', TRUE),
        ''
    );

    INSERT INTO lab355_order_history (
        table_name,
        record_id,
        action,
        old_data,
        new_data,
        actor_hint,
        session_role,
        effective_role,
        transaction_id
    )
    VALUES (
        TG_TABLE_NAME,
        v_id,
        TG_OP,
        v_old,
        v_new,
        v_actor,
        session_user,
        current_user,
        txid_current()
    );

    -- Giá trị RETURN của AFTER ROW trigger không được dùng
    -- để thay thế hàng nguồn.
    RETURN NULL;
END;
$fn$;
~~~

Gắn vào bảng:

~~~sql
CREATE TRIGGER lab355_audit_orders
AFTER INSERT OR UPDATE OR DELETE
ON lab355_orders
FOR EACH ROW
EXECUTE FUNCTION pg_temp.lab355_capture_change();
~~~

PostgreSQL không có cú pháp `CREATE TEMP FUNCTION` giống `CREATE TEMP TABLE`. Bài dùng tên schema `pg_temp` tường minh để phục vụ ví dụ trong session; nếu môi trường không hỗ trợ/quyền hạn không cho cách làm này, hãy đặt function trong schema sandbox được quản lý và dọn sau thực hành.

### 5.1. Các biến đặc biệt của trigger

| Biến | Giá trị |
|---|---|
| `TG_OP` | Tên thao tác: INSERT, UPDATE, DELETE… |
| `TG_TABLE_NAME` | Tên bảng đã kích hoạt trigger |
| `OLD` | Record cũ, khi sự kiện hỗ trợ |
| `NEW` | Record mới, khi sự kiện hỗ trợ |
| `TG_WHEN` | BEFORE, AFTER hoặc INSTEAD OF |
| `TG_LEVEL` | ROW hoặc STATEMENT |

Đối với AFTER ROW trong bài, việc `RETURN NULL` không khiến INSERT/UPDATE/DELETE bị bỏ qua: giá trị trả về của AFTER row trigger bị bỏ qua theo ngữ nghĩa PostgreSQL. Điều này **khác** BEFORE ROW trigger, nơi việc trả `NULL` có thể ngăn thao tác trên hàng.

### 5.2. Kiểm tra ban đầu

~~~sql
SELECT COUNT(*) AS audit_rows
FROM lab355_order_history;
~~~

Kết quả bằng **0** vì trigger được tạo **sau** khi nạp bốn đơn mẫu.

## 6. INSERT: ghi NEW, không có OLD

~~~sql
BEGIN;

SET LOCAL app.actor_id = 'employee-17';

INSERT INTO lab355_orders
    (id, customer_id, status, amount, note)
VALUES
    (105, 2, 'NEW', 130000, 'Đơn mẫu');

SELECT
    audit_id,
    record_id,
    action,
    old_data,
    new_data,
    actor_hint
FROM lab355_order_history
ORDER BY audit_id;

ROLLBACK;
~~~

Trong transaction có **một dòng**:

| record_id | action | old_data | new_data |
|---:|---|---|---|
| 105 | INSERT | SQL NULL | Snapshot đơn 105 |

`new_data` chứa cả `id`, `customer_id`, `status`, `amount` và `note` của bản ghi mới. `old_data` là SQL NULL vì INSERT không có hàng cũ.

`SET LOCAL app.actor_id` đặt một cấu hình tùy chỉnh chỉ có hiệu lực trong transaction hiện tại. Nó hữu ích để truyền actor context qua service, nhưng client có quyền sử dụng connection vẫn có thể tự đặt giá trị; cần kiểm soát nguồn gốc actor khi coi đây là bằng chứng.

Sau `ROLLBACK`, đơn 105 **và dòng history của nó** đều biến mất.

## 7. UPDATE: ghi cả OLD lẫn NEW

~~~sql
BEGIN;

SET LOCAL app.actor_id = 'employee-18';

UPDATE lab355_orders
SET
    status = 'PAID',
    note = 'Đã xác nhận thanh toán'
WHERE id = 101
RETURNING id, status, note;

SELECT
    audit_id,
    record_id,
    action,
    old_data ->> 'status' AS status_cu,
    new_data ->> 'status' AS status_moi,
    old_data ->> 'note' AS note_cu,
    new_data ->> 'note' AS note_moi
FROM lab355_order_history
WHERE record_id = 101;

ROLLBACK;
~~~

Kết quả trước ROLLBACK:

| record_id | action | status_cu | status_moi | note_cu | note_moi |
|---:|---|---|---|---|---|
| 101 | UPDATE | NEW | PAID | NULL | Đã xác nhận thanh toán |

**Cần phân biệt:** `OLD` và `NEW` là giá trị hàng trước và sau thao tác; không chỉ chứa những cột được liệt kê trong `SET`. Nếu `amount` không đổi, snapshot cả hai phía vẫn có `amount = 100000`.

### 7.1. Toán tử JSONB

- `old_data -> 'status'`: lấy giá trị dạng JSONB.
- `old_data ->> 'status'`: lấy giá trị dưới dạng TEXT.
- `(new_data ->> 'amount')::NUMERIC`: chuyển text số trở lại NUMERIC để tính toán.
- Một khóa không tồn tại và một giá trị JSON null cần được phân biệt cẩn thận khi audit qua nhiều phiên bản schema.

## 8. DELETE: ghi OLD, không có NEW

~~~sql
BEGIN;

SET LOCAL app.actor_id = 'employee-19';

DELETE FROM lab355_orders
WHERE id = 103
RETURNING id, status;

SELECT
    record_id,
    action,
    old_data,
    new_data
FROM lab355_order_history
WHERE record_id = 103;

ROLLBACK;
~~~

Kết quả: một dòng `DELETE` có `old_data` là snapshot đơn 103, `new_data` bằng SQL NULL. Sau ROLLBACK, đơn 103 và nhật ký DELETE đều trở về trạng thái trước giao dịch.

Đây là một trong những lý do lịch sử DELETE hữu ích: khi DELETE đã commit, hàng chính không còn nhưng snapshot cũ trong audit có thể cho biết nó từng chứa những giá trị nào.

## 9. Một transaction tạo nhiều bản ghi lịch sử

~~~sql
BEGIN;

SET LOCAL app.actor_id = 'batch-operator-01';

UPDATE lab355_orders
SET status = 'PAID'
WHERE id = 101;

INSERT INTO lab355_orders
    (id, customer_id, status, amount, note)
VALUES
    (105, 2, 'NEW', 130000, 'Nạp theo lô');

DELETE FROM lab355_orders
WHERE id = 103;

SELECT
    audit_id,
    record_id,
    action,
    actor_hint,
    transaction_id,
    recorded_at
FROM lab355_order_history
ORDER BY audit_id;

ROLLBACK;
~~~

Trước ROLLBACK, có ba dòng audit:

- UPDATE đơn 101.
- INSERT đơn 105.
- DELETE đơn 103.

Chúng do cùng transaction tạo ra nên có cùng transaction ID của PostgreSQL. Tuy nhiên, `transaction_id` là **thông tin kỹ thuật ở database**, không phải request ID hoặc mã nghiệp vụ toàn cục.

Nếu muốn cùng biết thao tác thuộc request nào, thường cần thêm `request_id` được ứng dụng cung cấp có kiểm soát.

## 10. ROLLBACK hủy cả dữ liệu lẫn audit

Một tình huống:

~~~sql
BEGIN;

UPDATE lab355_orders
SET amount = amount + 10000
WHERE id = 101;

-- Trigger INSERT một log trong cùng transaction.

ROLLBACK;
~~~

Sau ROLLBACK:

- `amount` của đơn 101 trở lại giá trị ban đầu.
- Dòng audit của UPDATE này cũng không còn.

Điều này thể hiện **tính nguyên tử**. Trên PostgreSQL, trigger insert vào một bảng audit bình thường của cùng transaction không tạo một giao dịch độc lập.

### 10.1. Lợi ích của cùng transaction

Khi UPDATE được commit thành công, dòng audit tương ứng cũng commit; nếu UPDATE thất bại và rollback, không để lại một dòng audit nói rằng dữ liệu đã thay đổi được xác nhận.

Với audit mục tiêu là **lịch sử dữ liệu được commit**, hành vi này có lợi.

### 10.2. Giới hạn: không lưu đủ failed attempts

Nếu một người cố sửa dữ liệu nhưng transaction bị rollback hoặc vi phạm constraint, bảng history thường không giữ nỗ lực đó.

Các yêu cầu “ai đã thử sửa nhưng bị từ chối?”, “ai truy cập dữ liệu?” hoặc “ai cố xóa log?” cần **nhật ký truy cập/statement ngoài transaction**, audit extension/server logs, log ứng dụng hoặc kho log độc lập.

### 10.3. Ví dụ lỗi CHECK

~~~sql
BEGIN;

UPDATE lab355_orders
SET amount = -1
WHERE id = 101;

ROLLBACK;
~~~

Cột `amount` có `CHECK (amount >= 0)`. Lệnh cập nhật sai sẽ bị PostgreSQL từ chối; transaction bị lỗi và phải rollback. Không có một audit hàng thay đổi được commit cho nỗ lực ấy.

### 10.4. Sequence không nhất thiết rollback

`audit_id` dùng identity sequence. PostgreSQL có thể không hoàn trả các số sequence đã cấp trong transaction bị hủy, khiến audit_id sau đó **nhảy số**. Khoảng trống ID không tự chứng minh log bị xóa hoặc một thay đổi đã commit.

## 11. UPDATE 0 hàng khác UPDATE không đổi giá trị

### 11.1. UPDATE không tìm thấy hàng

~~~sql
BEGIN;

UPDATE lab355_orders
SET status = 'PAID'
WHERE id = 999;

SELECT COUNT(*) AS count_audit
FROM lab355_order_history;

ROLLBACK;
~~~

Không có hàng 999, nên row-level trigger **không chạy** cho lệnh này. Nếu history ban đầu rỗng, COUNT bằng 0.

### 11.2. UPDATE tự gán lại giá trị cũ

~~~sql
BEGIN;

UPDATE lab355_orders
SET status = status
WHERE id = 101;

SELECT
    action,
    old_data = new_data AS khong_doi
FROM lab355_order_history
WHERE record_id = 101;

ROLLBACK;
~~~

Câu UPDATE vẫn tác động hàng 101 theo ngữ nghĩa statement; AFTER UPDATE row trigger **ghi một dòng** theo cách thiết kế của bài. Với dữ liệu không đổi và không có BEFORE trigger chỉnh hàng, `old_data = new_data` bằng TRUE.

Đây là sự khác nhau quan trọng giữa:

- **Nhật ký thao tác UPDATE xảy ra trên hàng**, kể cả no-op.
- **Nhật ký giá trị thực sự thay đổi**, chỉ ghi khi trước/sau khác nhau.

### 11.3. Chỉ log UPDATE khi hàng thực sự đổi

Có thể khai báo trigger UPDATE riêng:

~~~sql
CREATE TRIGGER lab355_changed_update_only
AFTER UPDATE ON lab355_orders
FOR EACH ROW
WHEN (OLD IS DISTINCT FROM NEW)
EXECUTE FUNCTION pg_temp.lab355_capture_change();
~~~

**Chỉ xem đây là cấu hình thay thế.** Không bật trigger này cùng trigger tổng hợp ở phần 5 nếu mục tiêu là đúng một dòng audit cho mỗi UPDATE: cả hai có thể cùng ghi log khi hàng thay đổi.

`IS DISTINCT FROM` có ngữ nghĩa so sánh xác định với NULL, phù hợp hơn so sánh ba giá trị thông thường trong nhiều tình huống.

Nhược điểm: nếu ai đó đã gửi UPDATE nhưng giá trị cuối không đổi, log changed-only không ghi lại nỗ lực ấy.

## 12. Truy vấn lịch sử theo bản ghi

Trong môi trường có các transaction đã COMMIT, muốn xem những thay đổi liên quan đơn 101:

~~~sql
SELECT
    audit_id,
    table_name,
    record_id,
    action,
    actor_hint,
    session_role,
    transaction_id,
    recorded_at,
    old_data ->> 'status' AS old_status,
    new_data ->> 'status' AS new_status
FROM lab355_order_history
WHERE record_id = 101
ORDER BY audit_id;
~~~

### 12.1. Audit ID không phải commit order

Audit ID thường được cấp từ sequence. Trong hai transaction đồng thời, transaction A có thể nhận audit ID trước nhưng COMMIT **sau** transaction B.

`recorded_at` của bài cũng là thời gian trigger thực thi, **không phải thời gian COMMIT**. Nếu cần thứ tự commit chắc chắn để phát lại/đối soát, phải thiết kế cơ chế ghi nhận theo WAL/LSN hoặc giải pháp phù hợp, không chỉ dựa vào audit_id hoặc timestamp.

### 12.2. Đổi khóa chính ảnh hưởng truy vết

Hàm đặt `record_id := NEW.id` cho UPDATE. Nếu người dùng cho đổi khóa 101 thành 201, log UPDATE mới có record_id 201, còn `old_data` chứa id 101.

Nếu chỉ lọc `record_id = 101` sẽ không tìm đủ chuỗi lịch sử. Có thể:

- Cấm đổi PRIMARY KEY vì đây là định danh ổn định.
- Lưu `old_record_id` và `new_record_id`.
- Dùng khóa nghiệp vụ bất biến để nối lịch sử.

Đừng giả định mọi ID có thể đổi mà nhật ký vẫn tự liên kết chính xác.

## 13. Tìm những cột khác nhau giữa OLD và NEW

Với snapshot JSONB, có thể tạo báo cáo những trường thực sự thay đổi trong một dòng UPDATE:

~~~sql
SELECT
    h.audit_id,
    h.record_id,
    k.key AS column_name,
    h.old_data -> k.key AS old_value,
    h.new_data -> k.key AS new_value
FROM lab355_order_history AS h
CROSS JOIN LATERAL jsonb_object_keys(
    COALESCE(h.old_data, '{}'::JSONB)
    ||
    COALESCE(h.new_data, '{}'::JSONB)
) AS k(key)
WHERE h.action = 'UPDATE'
  AND h.old_data -> k.key
      IS DISTINCT FROM h.new_data -> k.key
ORDER BY h.audit_id, k.key;
~~~

Truy vấn tạo danh sách các khóa JSONB của hai snapshot, rồi chỉ lấy những khóa có giá trị trước/sau khác nhau.

Ví dụ đổi status NEW → PAID và note NULL → “Đã xác nhận” sẽ sinh hai dòng thông tin cột **status** và **note**.

### 13.1. SQL NULL và JSON null không giống nhau

`old_data IS NULL` nghĩa là không có snapshot cũ (như INSERT). Nhưng một snapshot có `"note": null` là **một object JSONB tồn tại** với trường note mang JSON null.

Với thay đổi schema, khóa không tồn tại và khóa chứa JSON null có thể cần xử lý khác nhau. Nếu yêu cầu tái dựng dữ liệu nghiêm ngặt, định nghĩa semantics rõ trước khi dùng phép trừ/so JSONB.

### 13.2. Snapshot hay delta?

Snapshot full row giúp tra cứu trạng thái tại một lần thay đổi, nhưng tốn dung lượng và có thể chứa dữ liệu nhạy cảm.

Delta chỉ lưu cột đổi tiết kiệm hơn khi UPDATE ít cột; ngược lại, khó dựng trạng thái đầy đủ nếu thiếu bản chụp ban đầu. Có thể dùng hybrid: snapshots định kỳ + deltas.

## 14. Những gì row trigger này KHÔNG ghi được

| Tình huống | AFTER ROW trigger của bài có log không? | Giải thích |
|---|---|---|
| INSERT một hàng | Có, nếu trigger bật và transaction commit | DML INSERT hàng |
| UPDATE hàng khớp | Có, kể cả no-op theo cách thiết kế hiện tại | Có sự kiện UPDATE hàng |
| DELETE hàng khớp | Có | Có sự kiện DELETE hàng |
| UPDATE khớp 0 hàng | Không | Không có row trigger được gọi |
| SELECT đọc bảng | Không | Không phải INSERT/UPDATE/DELETE |
| TRUNCATE | Không ghi OLD từng hàng | Sự kiện TRUNCATE khác DELETE |
| ALTER/CREATE/DROP TABLE | Không | DDL không phải row DML |
| Thao tác lỗi/rollback | Không có log committed | Audit cùng transaction bị hủy |
| Thay đổi bảng khác không gắn trigger | Không | Trigger không tự phủ mọi bảng |
| Trigger bị vô hiệu hóa | Không bảo đảm | Cơ chế thu thập đã bị tắt |
| Log bị sửa/xóa bởi role có quyền | Không tự phát hiện | Bảng audit không chống sửa tuyệt đối |

### 14.1. SELECT là khoảng trống lớn

Một người có thể truy vấn:

~~~sql
SELECT *
FROM lab355_orders
WHERE customer_id = 1;
~~~

Trigger DML không chạy. Nếu mục tiêu là theo dõi **ai đã xem dữ liệu** hoặc **ai đã thử truy cập bảng**, cần cơ chế khác như PostgreSQL server logging, pgAudit được quản trị cấu hình, logging ở API/service, proxy hoặc hệ thống SIEM.

### 14.2. DDL cần công cụ khác

~~~sql
ALTER TABLE lab355_orders
ADD COLUMN channel TEXT;
~~~

không tạo log INSERT/UPDATE/DELETE của từng hàng. PostgreSQL có **event triggers** cho một số sự kiện DDL, nhưng đây là cơ chế khác có yêu cầu quyền và ngữ nghĩa riêng; thông thường còn có quản lý migration, review thay đổi schema và server audit.

## 15. TRUNCATE không kích hoạt DELETE row trigger

`DELETE FROM lab355_orders` chọn và xóa từng hàng theo ngữ nghĩa DML, nên AFTER DELETE row trigger có thể ghi history cho mỗi hàng.

Ngược lại:

~~~sql
TRUNCATE TABLE lab355_orders;
~~~

là một thao tác riêng, không gọi row-level DELETE trigger cho từng hàng. PostgreSQL hỗ trợ trigger **FOR EACH STATEMENT** cho sự kiện `TRUNCATE`.

**Không chạy TRUNCATE thật trên bảng cần giữ** để thử hành vi này.

### 15.1. Chặn TRUNCATE bằng trigger

Nếu cần cấm TRUNCATE một bảng được audit, có thể dùng:

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab355_reject_truncate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE EXCEPTION
        'TRUNCATE bị cấm đối với bảng %', TG_TABLE_NAME;
END;
$fn$;

CREATE TRIGGER lab355_no_truncate
BEFORE TRUNCATE ON lab355_orders
FOR EACH STATEMENT
EXECUTE FUNCTION pg_temp.lab355_reject_truncate();
~~~

Về sau:

~~~sql
TRUNCATE TABLE lab355_orders;
~~~

sẽ báo lỗi trong phạm vi trigger đang bật. Nếu lệnh nằm trong transaction, cần rollback hoặc xử lý trạng thái transaction bị lỗi theo PostgreSQL.

### 15.2. Log một lệnh TRUNCATE không có OLD của từng hàng

Một AFTER TRUNCATE statement trigger có thể ghi “đã có TRUNCATE” nhưng **không tự có dữ liệu của từng hàng** qua OLD/NEW. Muốn giữ các hàng trước khi bị xóa, cần cơ chế archive/snapshot trước, cấm TRUNCATE hoặc chính sách sao lưu phù hợp.

Không coi sự kiện TRUNCATE statement-level là thay thế tương đương cho mọi dòng DELETE audit.

## 16. Hàng loạt: số lần trigger và chi phí

~~~sql
BEGIN;

UPDATE lab355_orders
SET status = 'PAID'
WHERE status = 'NEW';

SELECT record_id, action
FROM lab355_order_history
ORDER BY audit_id;

ROLLBACK;
~~~

Trong dữ liệu mẫu, đơn 101 và 104 là NEW. Câu UPDATE thay đổi **hai hàng**, row trigger ghi **hai log UPDATE**.

Nếu thay bằng cập nhật 100.000 hàng, có thể có 100.000 lần trigger chạy và 100.000 INSERT audit. Hệ quả:

- Tốn CPU chuyển đổi JSONB.
- Thêm WAL và I/O.
- Tăng kích thước history và index.
- Tăng thời gian transaction, áp lực VACUUM/backup.
- Có thể gây contention khi nhiều tác vụ ghi audit.

Việc dùng trigger có thể ảnh hưởng đáng kể đến thời gian phản hồi của cả INSERT, UPDATE và DELETE. Đừng chỉ đo truy vấn SELECT trên bảng nhỏ để kết luận “audit không tốn hiệu năng”.

### 16.1. INSERT ... ON CONFLICT

Với PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` không chèn một hàng khi có xung đột; AFTER INSERT row trigger không ghi một dòng “INSERT thành công” cho hàng bị bỏ qua ấy.

`ON CONFLICT DO UPDATE` có thể đi theo nhánh UPDATE và gọi AFTER UPDATE row trigger cho hàng thực sự cập nhật, theo ngữ nghĩa trigger của PostgreSQL. Trên một số trường hợp, các trigger statement-level của INSERT/UPDATE cũng có thể được gọi; cần phân biệt row- và statement-level.

### 16.2. UPDATE FROM không đúng JOIN

Nếu câu UPDATE có JOIN nhiều dòng nguồn khớp một dòng đích, trigger ghi trạng thái đích sau thao tác nhưng **không sửa được lỗi logic** của câu UPDATE. Audit trả lời “giá trị đã ghi là gì?”, không tự trả lời “truy vấn ban đầu có cập nhật đúng hàng và đúng giá trị không?”.

## 17. Statement trigger và transition tables

PostgreSQL có **transition relations** để AFTER statement trigger nhìn thấy tập hàng cũ/mới của một số câu DML. Đây là một kỹ thuật thay thế cách INSERT audit một lần cho từng hàng.

Ví dụ cho UPDATE:

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab355_capture_update_set()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO lab355_order_history (
        table_name,
        record_id,
        action,
        old_data,
        new_data,
        actor_hint,
        session_role,
        effective_role,
        transaction_id
    )
    SELECT
        TG_TABLE_NAME,
        n.id,
        'UPDATE',
        to_jsonb(o),
        to_jsonb(n),
        NULLIF(current_setting('app.actor_id', TRUE), ''),
        session_user,
        current_user,
        txid_current()
    FROM before_rows AS o
    JOIN after_rows AS n
        ON n.id = o.id;

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab355_update_statement
AFTER UPDATE ON lab355_orders
REFERENCING
    OLD TABLE AS before_rows
    NEW TABLE AS after_rows
FOR EACH STATEMENT
EXECUTE FUNCTION pg_temp.lab355_capture_update_set();
~~~

**Không dùng đồng thời trigger này với trigger UPDATE row-level ở phần 5** nếu bạn không muốn ghi trùng. Đoạn này là **một phương án thiết kế**, không phải bước nối tiếp bắt buộc của bài thực hành.

### 17.1. Lợi ích và giới hạn

- Một lệnh `INSERT ... SELECT` có thể ghi nhiều audit entries thay cho nhiều INSERT riêng.
- PostgreSQL phải tạo/duy trì các transition relations, nên hiệu quả thực tế cần đo.
- `JOIN n.id = o.id` giả định khóa ID **không đổi** trong UPDATE. Nếu ID thay đổi, ánh xạ old/new theo ID có thể sai hoặc thiếu.
- Transition tables có giới hạn theo sự kiện, kiểu trigger, partition và cú pháp phiên bản; phải đối chiếu tài liệu PostgreSQL trước khi triển khai.

Vì vậy, statement-level không tự tốt hơn row-level trong mọi tình huống.

## 18. Timestamp và thứ tự sự kiện

Một nhật ký có thể dùng ba loại thời gian khác nhau:

| PostgreSQL | Diễn giải |
|---|---|
| `transaction_timestamp()` / `CURRENT_TIMESTAMP` | Thời điểm bắt đầu transaction |
| `statement_timestamp()` | Thời điểm bắt đầu statement |
| `clock_timestamp()` | Đồng hồ hiện tại khi hàm được gọi |
| `audit_id` identity | Số sequence, không phải thời gian |

Bài lưu `recorded_at TIMESTAMPTZ DEFAULT clock_timestamp()`. Nếu transaction thực thi trong 30 giây, các log của nó có thể mang thời điểm khác nhau. Nhưng đó vẫn không phải timestamp của COMMIT.

Ví dụ:

~~~text
Transaction A: trigger ghi lúc 10:00, COMMIT 10:05
Transaction B: trigger ghi lúc 10:01, COMMIT 10:02
~~~

A được ghi log sớm hơn nhưng COMMIT muộn hơn B. Audit ID và clock_timestamp không tự cung cấp thứ tự commit đáng tin cậy.

Nếu cần khôi phục/đối soát theo thứ tự commit, nên dùng cơ chế có định nghĩa phù hợp về transaction/LSN/CDC và xử lý các giao dịch đồng thời.

## 19. Ai thực hiện thao tác? Database role khác người dùng ứng dụng

Ứng dụng Java có thể dùng một connection pool, mọi request đều kết nối bằng role `app_service`.

~~~text
Người dùng trong ứng dụng: employee-17
                    │
                    ▼
             Java API service
                    │
                    ▼
    PostgreSQL role kết nối: app_service
                    │
                    ▼
      Trigger:
        session_user = app_service
        current_user = app_service (thường vậy)
        app.actor_id = employee-17 (nếu được đặt)
~~~

### 19.1. current_user và session_user

- `session_user` thường cho biết role khởi tạo session.
- `current_user` là role hiện có hiệu lực, có thể thay đổi qua `SET ROLE` hoặc khi thực thi `SECURITY DEFINER`.
- Không trường nào tự biết ai đã đăng nhập vào ứng dụng web nếu mọi request dùng một role DB.

### 19.2. SET LOCAL app.actor_id

~~~sql
BEGIN;

SET LOCAL app.actor_id = 'employee-17';

UPDATE lab355_orders
SET note = 'Đã kiểm tra'
WHERE id = 101;

ROLLBACK;
~~~

Thông tin này hữu ích để liên kết request với log, nhưng **có thể bị giả mạo** nếu client có quyền tự chạy SQL trên connection. Cần xác thực actor tại service, giới hạn quyền truy cập, bảo vệ token/request và cân nhắc log riêng độc lập.

### 19.3. SECURITY DEFINER

Một hàm `SECURITY DEFINER` chạy với quyền của chủ sở hữu hàm. Do đó, `current_user` bên trong có thể là **role sở hữu audit function**, chứ không phải role người gửi câu UPDATE hoặc người dùng ứng dụng.

Nếu thiết kế audit production với SECURITY DEFINER, không dùng `current_user` như bằng chứng tuyệt đối cho danh tính actor cuối. Cần mô hình rõ về role login, effective role, actor và request ID được kiểm soát.

### 19.4. Lý do thay đổi không tự có trong OLD/NEW

Một UPDATE:

~~~sql
UPDATE lab355_orders SET status = 'PAID' WHERE id = 101;
~~~

không chứa “người dùng đã thanh toán bằng phương thức nào” hoặc “vì sao đơn được duyệt”, trừ khi bạn lưu ở bảng nghiệp vụ hay truyền qua ngữ cảnh đáng tin cậy.

Audit thay đổi hàng cần được kết hợp **application/business event log** khi mục tiêu là giải thích quyết định nghiệp vụ.

## 20. Bảo vệ bảng audit bằng phân quyền

Một người dùng có quyền ghi bảng chính **không nên tự có quyền sửa hoặc xóa lịch sử**.

Trong production thường cân nhắc:

1. Bảng history ở schema riêng, không cùng quyền sửa với bảng nghiệp vụ.
2. Application role có quyền cần thiết trên bảng nguồn, **không có UPDATE/DELETE trực tiếp** vào history.
3. Trigger function do role riêng sở hữu với quyền INSERT audit.
4. Role đọc audit chỉ được đọc dữ liệu cần thiết và đã xử lý dữ liệu nhạy cảm.
5. Mọi hoạt động DBA/quản trị thay đổi trigger/schema được giám sát.

Ví dụ ý tưởng (các role/schema cần tồn tại và được cấu hình đầy đủ):

~~~sql
REVOKE UPDATE, DELETE
ON audit.order_history
FROM app_role;

GRANT SELECT
ON audit.order_history
TO audit_reader;
~~~

Đây là minh họa **không phải cấu hình phân quyền hoàn chỉnh**: còn quyền từ PUBLIC, quyền chủ bảng, schema USAGE, quyền kế thừa và các role khác.

### 20.1. SECURITY DEFINER phải khóa search_path

Nếu trigger cần ghi audit bằng quyền cao hơn role ứng dụng, có thể cân nhắc function `SECURITY DEFINER` với owner đáng tin, search_path cố định và tên bảng/hàm được schema-qualified.

Mẫu thuộc tính:

~~~sql
CREATE OR REPLACE FUNCTION audit.capture_row()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = audit, app_schema, pg_temp
AS $fn$
BEGIN
    -- Mẫu minh họa thuộc tính bảo mật;
    -- phần thân audit thật phải được triển khai riêng.
    RETURN NULL;
END;
$fn$;
~~~

Không dùng function rỗng này thay cho trigger ghi lịch sử thực. Khi thiết kế thật cần:

- Không cho role không tin cậy sửa code/function hoặc tạo đối tượng trong schema được tra cứu.
- Schema-qualify đối tượng nhạy cảm.
- Không ghép tên bảng/cột/SQL động tùy ý từ input.
- Cấp quyền tối thiểu cho owner/EXECUTE.
- Phân biệt current_user trong SECURITY DEFINER với actor thực.

### 20.2. Audit ở cùng database không hoàn toàn chống sửa

Role sở hữu bảng, DBA/superuser hoặc kẻ tấn công đã có đặc quyền rộng có thể thay function, tắt trigger, sửa bảng audit hoặc xóa log tùy quyền thực tế.

Nếu yêu cầu kiểm toán chống giả mạo mạnh, cần **kho log ngoài với quyền tách biệt**, append-only/WORM phù hợp, kiểm chứng tính toàn vẹn và giám sát thay đổi cấu hình. Một hash chain lưu hoàn toàn trong cùng database vẫn có thể bị người toàn quyền tính lại/sửa nếu không có neo tin cậy ở nơi khác.

## 21. Trigger có thể bị tắt hoặc bỏ qua

Ví dụ cú pháp PostgreSQL:

~~~sql
ALTER TABLE lab355_orders
DISABLE TRIGGER lab355_audit_orders;

-- Khi trigger bị tắt, các DML trên bảng nguồn
-- không được trigger này ghi lịch sử.

ALTER TABLE lab355_orders
ENABLE TRIGGER lab355_audit_orders;
~~~

**Đây là tình huống rủi ro, không phải khuyến nghị tắt trigger.** Không thực hiện trên hệ thống thật nếu chưa có quy trình giám sát, phê duyệt và bù lịch sử.

Các nguyên nhân cần xét:

- Owner/role có quyền đủ cao vô hiệu hóa trigger.
- Quá trình migration/restore/replication làm thay đổi cơ chế gọi trigger.
- PostgreSQL `session_replication_role` ảnh hưởng các trigger theo chế độ kích hoạt và quyền cấu hình.
- Bảng mới/partition có thể chưa được bao phủ như mong đợi.
- Thao tác trên bảng khác không có trigger không tự xuất hiện trong log.

Có thể đọc metadata của trigger:

~~~sql
SELECT
    tgname,
    tgenabled
FROM pg_trigger
WHERE tgrelid = 'pg_temp.lab355_orders'::REGCLASS
  AND NOT tgisinternal
ORDER BY tgname;
~~~

Theo dõi metadata là một lớp kiểm soát, nhưng không chứng minh mọi thay đổi trong quá khứ đã được ghi nhận.

## 22. Dữ liệu nhạy cảm trong JSONB audit

`to_jsonb(OLD)` và `to_jsonb(NEW)` ghi mọi cột. Nếu bảng chứa dữ liệu cá nhân, địa chỉ, số điện thoại, mật khẩu hash, payment token, bí mật API hoặc thông tin sức khỏe, việc snapshot toàn hàng có thể **nhân đôi dữ liệu nhạy cảm** trong history.

Ví dụ chọn loại hai khóa khi thiết kế snapshot:

~~~sql
to_jsonb(NEW) - 'payment_token' - 'api_secret'
~~~

Tương tự áp dụng cho `OLD`.

Một số hệ thống còn chỉ cho phép log các thuộc tính được duyệt:

~~~sql
jsonb_build_object(
    'status', NEW.status,
    'amount', NEW.amount
)
~~~

Đây là các biểu thức minh họa, không phải đầy đủ chức năng masking. Người thiết kế cần xác định dữ liệu nào phải giữ, ai có quyền đọc, thời hạn retention và cách xóa/ẩn danh/mã hóa theo chính sách áp dụng.

### 22.1. Retention và schema evolution

Giữ full snapshots vô thời hạn khiến dữ liệu phình to. Ngoài chi phí lưu trữ/backup còn có rủi ro chính sách dữ liệu.

Nếu bảng nguồn được `ALTER TABLE ADD COLUMN`, snapshot sau đó có thể chứa khóa mới, trong khi snapshot cũ không có khóa ấy. Khi đọc lịch sử phải phân biệt:

- Cột chưa tồn tại.
- Cột tồn tại nhưng NULL.
- Cột đổi tên.
- Cột bị bỏ sau migration.

Có thể lưu thêm `schema_version` hoặc version của migration để diễn giải payload lâu dài.

## 23. Hiệu năng và tính sẵn sàng

Một row trigger ghi full JSONB hai phía có thể tốn nhiều tài nguyên khi bảng thay đổi lớn.

Chi phí gồm:

- Gọi PL/pgSQL mỗi hàng.
- Chuyển OLD/NEW thành JSONB.
- INSERT history và cập nhật các chỉ mục của nó.
- WAL, I/O, MVCC, VACUUM, replication và backup.
- Transaction dài, giữ tài nguyên lâu hơn.
- Dung lượng log/history cần partition/retention.

### 23.1. Lỗi ghi audit có thể làm lỗi nghiệp vụ

Nếu trigger function không có quyền INSERT vào history, audit table đầy hoặc một ràng buộc trên audit bị lỗi, **statement dữ liệu chính có thể thất bại**, vì trigger chạy trong cùng transaction.

Đây có thể là mục tiêu của chế độ “không ghi được audit thì không cho đổi dữ liệu”, nhưng đồng thời là nguy cơ availability. Cần monitor, capacity planning, cảnh báo, chính sách fail-closed/fail-open đúng yêu cầu.

### 23.2. Chỉ mục cho truy vấn lịch sử

Nếu bảng audit production có hàng triệu dòng và thường hỏi “lịch sử của đơn 101”, có thể cân nhắc:

~~~sql
CREATE INDEX lab355_history_lookup
ON lab355_order_history (
    table_name,
    record_id,
    recorded_at DESC
);
~~~

Index này có thể tăng tốc đọc, nhưng cũng làm mỗi INSERT audit tốn thêm công ghi. Cần đánh giá theo workload thật và cân nhắc partition theo thời gian, archive, giới hạn kết quả và phân trang.

### 23.3. Khi nào nên lưu delta?

Nếu UPDATE thường chỉ đổi `status`, ghi snapshot của cả một hàng chứa hàng chục cột/văn bản lớn rất đắt. Lưu delta hoặc các cột có giá trị nghiệp vụ có thể giảm chi phí. Đổi lại, tái dựng trạng thái toàn hàng cần baseline/snapshot hoặc khả năng giải thích qua version của schema.

## 24. Trigger đệ quy và hiệu ứng dây chuyền

Một trigger có thể thực thi SQL và SQL ấy lại kích hoạt trigger khác.

~~~text
UPDATE orders
   └── trigger orders
          └── UPDATE summary
                 └── trigger summary
                        └── INSERT history
~~~

Đây có thể là logic hợp lệ. Nhưng nếu trigger của bảng A lại UPDATE A mà không có điều kiện dừng, nó có thể gây **đệ quy/lặp vô hạn**, xung đột hoặc lỗi tài nguyên.

Hàm audit của bài chỉ INSERT vào `lab355_order_history`, bảng này không có trigger ghi ngược vào bảng nguồn, nên không tạo đệ quy trực tiếp trong ví dụ.

Không gắn cùng một trigger ghi audit vào **chính bảng audit** nếu hàm sẽ INSERT trở lại nó; cần thiết kế rõ bảng nào là nguồn, bảng nào là đích log.

### 24.1. pg_trigger_depth không phải giải pháp mặc định

PostgreSQL có `pg_trigger_depth()` để nhận biết độ sâu thực thi trigger. Nhưng bỏ qua mọi trigger ở depth lớn hơn một mức có thể làm mất những thay đổi hợp lệ do chuỗi trigger nghiệp vụ sinh ra. Ưu tiên thiết kế không đệ quy, kiểm soát luồng và giới hạn phạm vi tác động.

### 24.2. Foreign key cascade

Nếu xóa cha dẫn đến `ON DELETE CASCADE` xóa hàng con, các thay đổi con có thể kích hoạt trigger trên **bảng con** khi phù hợp. Để có audit đầy đủ, cần gắn/kiểm tra trigger đúng trên từng bảng liên quan, không chỉ bảng cha.

## 25. Audit không thay thế backup hoặc khôi phục thời điểm

Dòng history có OLD/NEW có thể giúp điều tra và lập thao tác bù trừ, nhưng không thể giả định chỉ cần đảo ngược các log là khôi phục hoàn chỉnh một database:

- Có thể có DELETE/TRUNCATE hoặc DDL chưa được ghi đầy đủ.
- Foreign key, trigger khác và dữ liệu liên bảng ảnh hưởng tính hợp lệ.
- Schema thay đổi qua các thời kỳ.
- Timestamp/sequence không đảm bảo thứ tự commit.
- Log có thể bị xóa/sửa bởi role đặc quyền.
- Dữ liệu nhạy cảm có thể bị mask, thiếu một số trường.
- Trạng thái của hệ thống ngoài DB không nằm trong history.

**Backup, PITR, WAL archiving và diễn tập khôi phục** giải quyết mục tiêu recovery khác với audit trail.

## 26. Trigger audit và những cơ chế liên quan

| Cơ chế | Phù hợp để ghi gì? | Ưu điểm | Hạn chế |
|---|---|---|---|
| Trigger + bảng history | OLD/NEW hàng DML trong transaction | Gắn với DB, log thay đổi đã commit | Không log SELECT/failure; quyền cao có thể bypass; chi phí ghi |
| CDC (WAL/binlog) | Dòng thay đổi đã commit theo log giao dịch | Có thể đẩy sang downstream | Cần replication/connector; thường thiếu actor nghiệp vụ |
| Server audit/pgAudit | Statement, truy cập theo cấu hình | Có thể bao gồm đọc và attempt lỗi | Log lớn, phải bảo vệ/retention; không tự là snapshot OLD/NEW |
| Application audit | Actor, lý do, yêu cầu | Ngữ cảnh người dùng phong phú | Có thể bỏ sót SQL trực tiếp |
| Temporal tables | Các phiên bản hàng theo thời gian | Truy vấn as-of thuận tiện khi DBMS hỗ trợ | Không tự theo dõi SELECT/ngữ cảnh ý định |
| Transactional outbox | Sự kiện cần phát sau commit | Gắn bản ghi sự kiện với thay đổi DB | Không tự làm audit toàn bộ; consumer cần retry/idempotency |
| External immutable logs | Dấu vết được đưa ra kho có quyền tách biệt | Tăng khả năng chống sửa/xóa | Cần quản lý truyền tải, xác minh, lưu trữ |

### 26.1. CDC

**Change Data Capture** dựa trên log giao dịch có thể thu thập thay đổi đã commit mà không viết một row trigger riêng cho mọi bảng theo cách truyền thống. Nhưng actor ứng dụng, lý do cập nhật và request ID có thể không có sẵn trong WAL/binlog nếu ứng dụng không lưu hoặc truyền chúng vào dữ liệu được capture.

CDC cũng không tự ghi lại SELECT bị từ chối hay các nỗ lực chưa commit.

### 26.2. Server audit log

Một hệ thống database audit có thể ghi truy vấn hoặc các hành động khác ở mức statement, tùy cài đặt. Nó phù hợp khi yêu cầu là **ai đã thử đọc/chạy lệnh gì**, nhưng thường không tự cung cấp cặp snapshot OLD/NEW thuận tiện như trigger history.

### 26.3. Outbox

Outbox lưu một event như `ORDER_PAID` vào bảng cùng transaction với đơn hàng, sau đó worker đọc và gửi tới message broker. Nó giải quyết một phần bài toán **phát sự kiện sau commit**, không tự đảm bảo lưu toàn bộ lịch sử mọi cột của đơn.

Khi cần cả lịch sử và sự kiện, có thể dùng hai cơ chế khác nhau, mỗi cơ chế với phạm vi và giới hạn rõ ràng.

## 27. Các hệ quản trị SQL có cú pháp khác nhau

| DBMS | Kiểu trigger DML | Dữ liệu trước/sau | Chú ý |
|---|---|---|---|
| PostgreSQL | Hàm RETURNS TRIGGER + CREATE TRIGGER | `OLD`, `NEW` và `TG_OP` | Row/statement triggers, JSONB, transition tables |
| MySQL / MariaDB | CREATE TRIGGER ... FOR EACH ROW | `OLD.column`, `NEW.column` | Cú pháp BEGIN/END; engine transactional |
| SQL Server | Trigger cấp statement | Bảng `inserted`, `deleted` | Phải xử lý tập hàng, không giả định một hàng |
| Oracle | Row trigger FOR EACH ROW | `:OLD.column`, `:NEW.column` | PL/SQL và quy tắc riêng |
| SQLite | CREATE TRIGGER theo hàng | `OLD.column`, `NEW.column` | Không dùng PL/pgSQL như PostgreSQL |

### 27.1. MySQL

Ví dụ cú pháp cho bảng mẫu có sẵn `orders` và `orders_history`:

~~~sql
DELIMITER //

CREATE TRIGGER orders_after_update
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO orders_history(
        order_id,
        old_status,
        new_status
    )
    VALUES (
        OLD.id,
        OLD.status,
        NEW.status
    );
END//

DELIMITER ;
~~~

`DELIMITER` là lệnh của SQL client MySQL/MariaDB, không phải SQL dùng giống nhau trong mọi JDBC driver. Với bảng transactional như InnoDB, nhật ký trigger thường tham gia cùng transaction; cần kiểm tra storage engine cụ thể.

### 27.2. SQL Server

SQL Server dùng các bảng logic **inserted** và **deleted** có thể chứa **nhiều hàng** vì trigger DML chạy theo statement.

~~~sql
CREATE TRIGGER dbo.orders_after_update
ON dbo.Orders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.OrdersHistory (
        OrderId,
        OldStatus,
        NewStatus
    )
    SELECT
        i.Id,
        d.Status,
        i.Status
    FROM inserted AS i
    JOIN deleted AS d
        ON d.Id = i.Id;
END;
~~~

Phép JOIN trên Id giả định ID không đổi; nếu UPDATE đổi Id, cần thiết kế ánh xạ khác. SQL Server còn có **system-versioned temporal tables** hữu ích khi cần truy vấn lịch sử theo thời gian, nhưng mục tiêu và các giới hạn không giống trigger audit hoàn chỉnh.

### 27.3. Oracle

Oracle tham chiếu các giá trị hàng trong row trigger bằng `:OLD.column` và `:NEW.column`, khác cú pháp PL/pgSQL. Cơ chế DDL, transaction và những hạn chế khi đọc bảng đang thay đổi có thể khác PostgreSQL.

### 27.4. SQLite

SQLite có trigger và `OLD/NEW`, nhưng không có `LANGUAGE plpgsql` hay `RETURNS TRIGGER` của PostgreSQL. Với ứng dụng SQLite, có thể dùng triggers, câu SQL và logging ở tầng ứng dụng theo kiến trúc triển khai.

## 28. Bài tập thực hành có lời giải

Các bài sử dụng `lab355_orders` và `lab355_order_history` đã tạo. Những bài thay đổi dữ liệu nên chạy trong `BEGIN ... ROLLBACK`, để không làm sai kết quả bài sau. Nếu đã COMMIT nhiều thay đổi, cần tạo lại dữ liệu gốc trong phiên học.

### Bài 1. INSERT ghi những snapshot nào?

**Đề:** Chèn đơn 105 vào bảng có AFTER INSERT trigger. Giá trị OLD/NEW ra sao?

**Đáp án:** `OLD` không có hàng cũ, `NEW` chứa hàng 105. Log có action INSERT, old_data SQL NULL và new_data là JSONB snapshot đơn 105.

### Bài 2. Quan sát UPDATE

~~~sql
BEGIN;

UPDATE lab355_orders
SET status = 'PAID'
WHERE id = 101;

SELECT
    old_data ->> 'status' AS old_status,
    new_data ->> 'status' AS new_status
FROM lab355_order_history
WHERE record_id = 101;

ROLLBACK;
~~~

**Đáp án:** trước ROLLBACK thấy NEW → PAID. Sau ROLLBACK, hàng gốc và log của lần UPDATE này đều không thay đổi bền vững.

### Bài 3. DELETE lấy dữ liệu cũ ở đâu?

~~~sql
BEGIN;

DELETE FROM lab355_orders
WHERE id = 103;

SELECT action, old_data, new_data
FROM lab355_order_history
WHERE record_id = 103;

ROLLBACK;
~~~

**Đáp án:** action DELETE, old_data chứa hàng 103 trước xóa, new_data SQL NULL.

### Bài 4. Vì sao khi UPDATE id 999 không có log?

**Đáp án:** WHERE id = 999 không chọn hàng nào. Với `FOR EACH ROW` không có hàng để gọi trigger, dù statement UPDATE về cú pháp thành công.

### Bài 5. UPDATE no-op có ghi không?

~~~sql
BEGIN;

UPDATE lab355_orders
SET status = status
WHERE id = 101;

SELECT action, old_data = new_data AS same_data
FROM lab355_order_history
WHERE record_id = 101;

ROLLBACK;
~~~

**Đáp án:** có thể có một dòng UPDATE với same_data = TRUE. Nếu yêu cầu chỉ lưu thay đổi thực, dùng trigger UPDATE có `WHEN (OLD IS DISTINCT FROM NEW)` trong cấu hình thay thế phù hợp.

### Bài 6. INSERT ba hàng

~~~sql
BEGIN;

INSERT INTO lab355_orders
    (id, customer_id, status, amount)
VALUES
    (201, 1, 'NEW', 10000),
    (202, 2, 'NEW', 20000),
    (203, 3, 'NEW', 30000);

SELECT COUNT(*)
FROM lab355_order_history
WHERE record_id IN (201, 202, 203);

ROLLBACK;
~~~

**Đáp án:** COUNT bằng **3** trong transaction, vì có ba hàng INSERT. Sau ROLLBACK, các bản ghi nguồn/audit tương ứng đều bị hủy.

### Bài 7. DELETE 0 hàng?

**Đáp án:** DELETE WHERE id = 999 tác động 0 hàng, nên không có row DELETE audit. Nếu muốn biết có ai gửi lệnh này, cần statement/application logging.

### Bài 8. Hai UPDATE trong cùng transaction

**Đề:** UPDATE đơn 101, UPDATE đơn 104, sau đó rollback. Có bao nhiêu dòng audit committed mới?

**Đáp án:** **0** vì rollback cả bảng nguồn và history. Trước rollback có thể quan sát hai dòng tạm trong cùng connection.

### Bài 9. Vai trò TG_OP

**Đáp án:** TG_OP giúp chọn nhánh xử lý INSERT (NEW), UPDATE (OLD+NEW), DELETE (OLD). Dùng OLD vô điều kiện khi INSERT hoặc NEW vô điều kiện khi DELETE có thể gây lỗi.

### Bài 10. Lấy actor từ SET LOCAL

~~~sql
BEGIN;

SET LOCAL app.actor_id = 'user-42';

UPDATE lab355_orders
SET note = 'Đã kiểm tra'
WHERE id = 104;

SELECT actor_hint
FROM lab355_order_history
WHERE record_id = 104;

ROLLBACK;
~~~

**Đáp án:** có thể đọc user-42. Nhưng thông tin do client/ứng dụng truyền, **không chứng minh** người dùng cuối một cách độc lập.

### Bài 11. SQL NULL và JSON null

**Đề:** Ở INSERT, old_data SQL NULL; trong new_data có `"note": null`. Hai nghĩa có giống nhau không?

**Đáp án:** không. Một bên là **không có snapshot cũ**, bên kia là **snapshot tồn tại nhưng giá trị cột note NULL**.

### Bài 12. Theo dõi SELECT

**Đề:** Trigger AFTER INSERT/UPDATE/DELETE có ghi lần đọc `SELECT * FROM lab355_orders` không?

**Đáp án:** không. Cần audit truy cập/database statement logging hoặc application logging nếu mục tiêu theo dõi đọc.

### Bài 13. TRUNCATE hay DELETE?

**Đáp án:** DELETE có thể kích hoạt row DELETE trigger; TRUNCATE không gọi các row DELETE triggers. Có thể chặn TRUNCATE bằng BEFORE TRUNCATE statement trigger hoặc thiết kế lưu trữ riêng.

### Bài 14. Vì sao audit_id nhảy số?

**Đáp án:** identity sequence có thể cấp ID trong transaction rollback mà không hoàn lại số. ID không liên tục không tự chứng minh log đã bị xóa.

### Bài 15. Lỗi INSERT audit

**Đề:** Một UPDATE hợp lệ làm trigger ghi history; INSERT history gặp lỗi quyền. UPDATE có tự commit được không?

**Đáp án:** không nếu lỗi trigger không được xử lý và cả hai nằm cùng transaction. Statement/transaction có thể thất bại. Đây vừa là bảo đảm nhất quán vừa là rủi ro availability.

### Bài 16. SECURITY DEFINER làm ai là current_user?

**Đáp án:** có thể là owner của trigger function, không phải người gọi DML hoặc người dùng web. Cần phân biệt session role, effective role và actor ứng dụng.

### Bài 17. Dữ liệu nhạy cảm

**Đề:** Bảng có `payment_token`; dùng `to_jsonb(NEW)` có nguy cơ gì?

**Đáp án:** audit lưu cả token, tăng phạm vi lộ dữ liệu và nghĩa vụ retention. Cần giới hạn cột, loại token hoặc bảo vệ thích hợp, đồng thời kiểm soát quyền đọc history/backup.

### Bài 18. Trigger bị tắt

**Đề:** Một role đặc quyền tắt audit trigger, UPDATE, rồi bật lại. Trigger có tự bổ sung log cho UPDATE đó không?

**Đáp án:** không. Cần kiểm soát cấu hình/quyền và kênh audit độc lập nếu yêu cầu phát hiện bypass.

### Bài 19. Theo dõi giao dịch đã rollback

**Đề:** Tổ chức muốn ghi lại cả những UPDATE bị từ chối, rollback, SELECT vào dữ liệu bí mật. Chỉ audit trigger hàng đủ không?

**Đáp án:** không. Trigger cùng transaction không giữ được log rollback, không ghi SELECT. Cần server/database audit logs, logging ứng dụng, kho log độc lập và chính sách quyền phù hợp.

### Bài 20. Truy vấn lịch sử đơn đã DELETE

**Đề:** Sau DELETE đã COMMIT, làm sao đọc old_data nếu không còn hàng ở bảng nguồn?

**Đáp án:** truy vấn trực tiếp bảng history theo `record_id`. Không dùng INNER JOIN bắt buộc với bảng nguồn khiến history của đơn đã xóa biến mất khỏi kết quả.

### Bài 21. Khóa chính đổi từ 101 sang 201

**Đáp án:** hàm ví dụ lưu `record_id = NEW.id = 201`. Nếu truy vấn chỉ bằng 101 có thể không thấy log sau đổi khóa. Nên cấm đổi PK hoặc lưu old_id/new_id/khóa ổn định.

### Bài 22. Chọn cơ chế kiến trúc

**Đề:** Hệ thống vừa cần lịch sử trạng thái đơn đã commit, vừa cần audit người xem hồ sơ, vừa cần đẩy sự kiện đến analytics. Chỉ một trigger có đủ không?

**Đáp án:** không. Có thể dùng row audit trigger/history cho thay đổi committed; server/application audit cho truy cập đọc; CDC/outbox cho phát sự kiện. Các thành phần cần quyền, retention, retry và giám sát riêng.

## 29. Checklist trước khi đưa audit trigger vào thực tế

1. **Mục tiêu** là lịch sử thay đổi đã commit, hay cả failed attempt/đọc dữ liệu?
2. **Đối tượng** nào được theo dõi, bao gồm bảng mới và partition?
3. Cần snapshot **OLD/NEW toàn hàng** hay chỉ delta?
4. Đổi khóa chính có được phép không, cần old/new ID không?
5. Timestamp cần là thời điểm trigger hay thứ tự COMMIT?
6. Ai có thể đặt/can thiệp `actor_id`, có nguồn nhận dạng tin cậy không?
7. Có correlation ID và lý do thay đổi từ nghiệp vụ không?
8. Log rollback cùng dữ liệu có đúng mục tiêu không?
9. Lệnh UPDATE 0 hàng và UPDATE no-op nên được diễn giải ra sao?
10. Có cần theo dõi SELECT, DDL, TRUNCATE bằng cơ chế khác không?
11. Ai có thể DISABLE TRIGGER hoặc thay function?
12. Quyền đọc/ghi/sửa/xóa trên history được tách thế nào?
13. Có dùng SECURITY DEFINER và search_path an toàn không?
14. Có dữ liệu nhạy cảm phải không được snapshot không?
15. Retention, archive, xóa/ẩn danh và backup thực hiện thế nào?
16. Khối lượng UPDATE hàng loạt có được đo trên dữ liệu đại diện chưa?
17. Trigger recursion, cascade và các trigger khác đã được xét chưa?
18. Lỗi INSERT history phải khiến DML thất bại hay có thiết kế khác?
19. Có index cho truy vấn theo table/id/time không?
20. Thay đổi schema có cần lưu version không?
21. Audit có bị hiểu nhầm là backup/khôi phục điểm thời gian không?
22. Cần bổ sung CDC, temporal, outbox, pgAudit hoặc external logs không?

## 30. Tổng kết

Trigger là một cách thuận tiện để tự ghi lịch sử của **những hàng INSERT/UPDATE/DELETE** trên bảng đã được cấu hình:

~~~text
DML bảng nguồn
      │
      ▼
AFTER ROW trigger
      │
      ├── INSERT → NEW
      ├── UPDATE → OLD + NEW
      └── DELETE → OLD
      │
      ▼
Bảng audit
      │
      ▼
Cùng transaction
  COMMIT   → dữ liệu và lịch sử cùng được xác nhận
  ROLLBACK → dữ liệu và lịch sử cùng bị hủy
~~~

Các điểm cần nhớ:

- **`OLD`, `NEW` và `TG_OP`** giúp mô tả thay đổi hàng; chúng không tự ghi đầy đủ lý do nghiệp vụ.
- **AFTER ROW** ghi theo từng hàng, do đó bulk DML có thể phát sinh rất nhiều audit entries và chi phí lưu trữ/WAL.
- **UPDATE 0 hàng** không kích hoạt row trigger; **UPDATE gán cùng giá trị** vẫn có thể kích hoạt.
- **ROLLBACK xóa cả lịch sử trong transaction**, nên trigger đơn thuần không theo dõi toàn bộ attempt thất bại.
- Trigger DML **không tự theo dõi SELECT, DDL**, và **TRUNCATE không kích hoạt row DELETE trigger**.
- **Actor truyền qua custom setting**, session_user hoặc current_user không tự bảo đảm danh tính người dùng cuối; SECURITY DEFINER còn thay đổi ý nghĩa role hiện hành.
- Bảng audit trong cùng database **không chống sửa xóa tuyệt đối** trước người có đặc quyền; cần phân quyền, giám sát và kho log ngoài khi yêu cầu mạnh.
- Snapshot JSONB tiện lợi nhưng có rủi ro **dữ liệu nhạy cảm**, schema evolution, dung lượng và hiệu năng.
- Khi cần khả năng mạnh hơn, hãy kết hợp đúng mục đích **database audit logging, CDC, temporal tables, application logs, outbox và hệ thống lưu nhật ký độc lập**.

Thiết kế audit tốt bắt đầu từ **câu hỏi cần điều tra, dữ liệu nào phải lưu, ai được tin cậy, giới hạn nào phải chấp nhận và bằng cách nào kiểm chứng nhật ký đầy đủ**, thay vì giả định rằng chỉ cần một trigger thì mọi thay đổi và truy cập đều đã được ghi lại.
