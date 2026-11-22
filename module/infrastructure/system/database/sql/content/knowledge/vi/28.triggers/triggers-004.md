# Tham chiếu dữ liệu cũ, mới và tập hàng bị ảnh hưởng

## 1. Vì sao trigger cần phân biệt OLD, NEW và cả một tập hàng?

Một câu lệnh SQL có thể thay đổi một hàng hoặc hàng nghìn hàng:

~~~sql
UPDATE demo_orders
SET amount = amount + 20,
    order_status = 'PAID'
WHERE order_id IN (101, 102);
~~~

Nếu muốn ghi nhật ký **trước và sau thay đổi**, ta cần biết:

- Hàng 101 có giá trị **cũ** nào và **mới** nào?
- Hàng 102 có giá trị **cũ** nào và **mới** nào?
- Hai hàng đó có nằm trong cùng một câu UPDATE không?
- Câu UPDATE không khớp hàng nào thì trigger có chạy không?
- Khi thêm hàng, có “hàng cũ” không? Khi xóa hàng, có “hàng mới” không?
- Nếu chỉ thay đổi một cột, làm sao tránh ghi nhật ký sai hoặc thừa?
- Khi cập nhật khóa định danh, có thể ghép OLD và NEW dựa trên khóa nào?

Đây là trung tâm của chủ đề **Tham chiếu dữ liệu cũ, mới và tập hàng bị ảnh hưởng** thuộc **Database SQL → Trigger**.

Trigger là đoạn logic do database tự gọi khi một sự kiện phù hợp xảy ra trên bảng hoặc đối tượng được hỗ trợ. Tuy cùng gắn với `INSERT`, `UPDATE` và `DELETE`, các DBMS có mô hình trigger khác nhau:

- **Trigger theo hàng** (*row-level trigger*): chạy cho từng hàng được sự kiện tác động. PostgreSQL sử dụng bản ghi `OLD`/`NEW`; MySQL dùng `OLD.column`/`NEW.column`; Oracle dùng `:OLD`/`:NEW`; SQLite hỗ trợ `OLD`/`NEW`.
- **Trigger theo câu lệnh** (*statement-level trigger*): chạy cho câu SQL, không đồng nghĩa chạy một lần **mỗi hàng**. PostgreSQL có `FOR EACH STATEMENT` và có thể dùng **transition tables** để đọc các tập hàng cũ/mới trong những trường hợp phù hợp.
- **SQL Server** sử dụng hai bảng logic `deleted` và `inserted` trong DML trigger. Mỗi bảng logic có thể chứa **0, 1 hoặc nhiều hàng**; không được viết trigger như thể chúng chỉ chứa một hàng.

Ba ý chính cần nhớ:

1. **`OLD`** mô tả giá trị **trước** thao tác; **`NEW`** mô tả giá trị **sau hoặc đang đề xuất ghi**, tùy thời điểm trigger.
2. **Phạm vi theo hàng khác phạm vi theo statement**: 100 hàng được UPDATE có thể kích hoạt 100 lần row trigger, nhưng chỉ một lần statement trigger cho câu lệnh đó.
3. **Tập hàng chuyển tiếp không có thứ tự hay cặp ghép ngầm định**: muốn so OLD/NEW của từng thực thể trong hai bảng, cần một khóa liên hệ đủ ổn định.

Bài sử dụng **PostgreSQL PL/pgSQL** làm hệ chính để có ví dụ đầy đủ. Các phần riêng sẽ đối chiếu SQL Server, MySQL, Oracle và SQLite. Không sao chép cú pháp một engine sang engine khác.

## 2. Bản đồ OLD và NEW theo từng thao tác

### 2.1. Một hàng INSERT có gì?

~~~text
Trước INSERT: chưa tồn tại hàng trong bảng đích
                    |
                    v
         INSERT (order_id=105, amount=90)
                    |
                    v
Sau INSERT: NEW = (105, 90, ...)
            OLD không có hàng tương ứng
~~~

Một row-level `INSERT` trigger có bản ghi `NEW`; **không có bản ghi `OLD` của cùng hàng**, vì hàng này chưa tồn tại trong bảng đích.

### 2.2. Một hàng UPDATE có gì?

~~~text
OLD: (order_id=101, amount=100, status=NEW)
                            |
                    UPDATE amount + 20,
                           status=PAID
                            |
NEW: (order_id=101, amount=120, status=PAID)
~~~

Cả hai bản ghi đều hữu ích:

- `OLD.amount` = 100;
- `NEW.amount` = 120;
- `OLD.order_status` = NEW;
- `NEW.order_status` = PAID.

### 2.3. Một hàng DELETE có gì?

~~~text
Trước DELETE: OLD = (order_id=104, amount=50, status=CANCELLED)
                          |
                        DELETE
                          |
Sau DELETE: hàng không còn trong bảng đích
            NEW không tồn tại
~~~

Row-level `DELETE` trigger có `OLD` nhưng không có `NEW` cho hàng bị xóa.

### 2.4. Bảng khả dụng

| Sự kiện | Hình ảnh trước thao tác | Hình ảnh sau/đề xuất | Row-level PostgreSQL |
| --- | --- | --- | --- |
| INSERT | Không có hàng đích cũ | Hàng mới | `NEW`; `OLD` không có |
| UPDATE | Hàng trước sửa | Hàng sau/đang sửa | Cả `OLD` và `NEW` |
| DELETE | Hàng trước xóa | Không có hàng mới | `OLD`; `NEW` không có |
| TRUNCATE | Thao tác cấp bảng | Không có tập OLD/NEW kiểu DML thường | Trigger TRUNCATE có quy tắc riêng, không phải row trigger DELETE |

Không suy rằng `TRUNCATE` tương đương hàng nghìn `DELETE` và sẽ sinh các bản ghi `OLD` cho từng hàng. PostgreSQL cho phép trigger cấp statement trên TRUNCATE nhưng **không** có row-level TRUNCATE trigger với `OLD` của từng hàng như DELETE.

## 3. Dữ liệu mẫu PostgreSQL

### 3.1. Tạo bảng đơn hàng

~~~sql
CREATE TABLE demo_orders (
    order_id       BIGINT PRIMARY KEY,
    customer_id    BIGINT NOT NULL,
    amount         NUMERIC(12, 2) NOT NULL,
    order_status   TEXT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL
                   DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_demo_amount CHECK (amount >= 0),
    CONSTRAINT chk_demo_order_status CHECK (
        order_status IN (
            'NEW', 'PAID', 'CANCELLED', 'REFUNDED'
        )
    )
);
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO demo_orders (
    order_id, customer_id, amount, order_status
)
VALUES
    (101, 1, 100.00, 'NEW'),
    (102, 1, 250.00, 'NEW'),
    (103, 2, 400.00, 'PAID'),
    (104, 3,  50.00, 'CANCELLED');
~~~

Trạng thái ban đầu:

| order_id | customer_id | amount | order_status |
| ---: | ---: | ---: | --- |
| 101 | 1 | 100.00 | NEW |
| 102 | 1 | 250.00 | NEW |
| 103 | 2 | 400.00 | PAID |
| 104 | 3 | 50.00 | CANCELLED |

Giả sử nghiệp vụ muốn ghi log khi số tiền hoặc trạng thái thay đổi. Chúng ta sẽ triển khai hai cách, mỗi cách ghi vào **một bảng log riêng** để so sánh:

- `demo_order_row_audit`: row trigger dùng `OLD`/`NEW`.
- `demo_order_set_audit`: statement trigger dùng `OLD TABLE`/`NEW TABLE`.

Không nhất thiết nên dùng cả hai trên production: hai bảng ở đây chủ yếu phục vụ học cách truy cập dữ liệu khác nhau.

### 3.2. Bảng lưu audit theo hàng

~~~sql
CREATE TABLE demo_order_row_audit (
    audit_id       BIGINT GENERATED ALWAYS AS IDENTITY
                   PRIMARY KEY,
    operation      TEXT NOT NULL,
    order_id       BIGINT NOT NULL,
    old_amount     NUMERIC(12, 2),
    new_amount     NUMERIC(12, 2),
    old_status     TEXT,
    new_status     TEXT,
    logged_at      TIMESTAMPTZ NOT NULL
                   DEFAULT CURRENT_TIMESTAMP
);
~~~

Không tạo FK từ `demo_order_row_audit.order_id` tới `demo_orders.order_id`: một bản ghi log **DELETE** cần tiếp tục tồn tại sau khi đơn gốc đã bị xóa. Trong hệ thống thực, lựa chọn lưu định danh, phân vùng, quyền đọc, thời hạn giữ và dữ liệu nhạy cảm của audit phải theo chính sách riêng.

### 3.3. Bảng audit theo tập

~~~sql
CREATE TABLE demo_order_set_audit (
    audit_id       BIGINT GENERATED ALWAYS AS IDENTITY
                   PRIMARY KEY,
    order_id       BIGINT NOT NULL,
    old_amount     NUMERIC(12, 2),
    new_amount     NUMERIC(12, 2),
    old_status     TEXT,
    new_status     TEXT,
    logged_at      TIMESTAMPTZ NOT NULL
                   DEFAULT CURRENT_TIMESTAMP
);
~~~

Bảng thứ hai ghi theo tập các hàng trước và sau UPDATE. Sau khi tạo trigger ở các phần sau, cùng một UPDATE có thể ghi cả hai bảng log. Ta sẽ luôn nêu rõ đang đọc bảng nào.

### 3.4. Thực hành trong transaction

Một câu UPDATE/DELETE có thể tác động dữ liệu thật. Với bài học PostgreSQL, chạy thử:

~~~sql
BEGIN;

-- Ví dụ INSERT, UPDATE hoặc DELETE ở đây.

SELECT *
FROM demo_orders
ORDER BY order_id;

ROLLBACK;
~~~

Nếu một trigger phát sinh exception, transaction PostgreSQL có thể rơi vào trạng thái lỗi; cần `ROLLBACK` hoặc savepoint phù hợp trước khi chạy ví dụ khác.

**Các kết quả kỳ vọng bên dưới giả định mỗi ví dụ bắt đầu từ dữ liệu mẫu ban đầu**, trừ khi có nói khác. Không chạy tùy tiện các lệnh này trên production.

## 4. PostgreSQL: OLD và NEW trong trigger FOR EACH ROW

### 4.1. Tạo trigger function

Trong PostgreSQL, function dùng cho trigger khai báo `RETURNS trigger`, sau đó được đăng ký bằng `CREATE TRIGGER`.

~~~sql
CREATE OR REPLACE FUNCTION demo_log_order_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO demo_order_row_audit (
            operation, order_id,
            old_amount, new_amount,
            old_status, new_status
        )
        VALUES (
            'INSERT', NEW.order_id,
            NULL, NEW.amount,
            NULL, NEW.order_status
        );

    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.amount IS DISTINCT FROM NEW.amount
           OR OLD.order_status IS DISTINCT FROM NEW.order_status
        THEN
            INSERT INTO demo_order_row_audit (
                operation, order_id,
                old_amount, new_amount,
                old_status, new_status
            )
            VALUES (
                'UPDATE', NEW.order_id,
                OLD.amount, NEW.amount,
                OLD.order_status, NEW.order_status
            );
        END IF;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO demo_order_row_audit (
            operation, order_id,
            old_amount, new_amount,
            old_status, new_status
        )
        VALUES (
            'DELETE', OLD.order_id,
            OLD.amount, NULL,
            OLD.order_status, NULL
        );
    END IF;

    -- Với AFTER trigger, giá trị trả về bị bỏ qua.
    RETURN NULL;
END;
$$;
~~~

Các điểm cần chú ý:

- `TG_OP` là biến đặc biệt cho biết sự kiện, thường là chuỗi `'INSERT'`, `'UPDATE'` hoặc `'DELETE'`.
- `NEW` chứa dữ liệu hàng mới/đề xuất khi INSERT hoặc UPDATE.
- `OLD` chứa dữ liệu hàng cũ khi UPDATE hoặc DELETE.
- Function kiểm tra `TG_OP` trước khi truy cập các biến tương ứng.
- `IS DISTINCT FROM` so sánh an toàn cả khi có `NULL`.
- Nhánh UPDATE chỉ ghi log nếu **giá trị thực sự khác** ở một trong hai cột cần theo dõi.
- `RETURN NULL` hợp lệ ở `AFTER` trigger vì giá trị trả về không dùng để sửa/loại hàng. Trong **BEFORE row trigger**, `RETURN NULL` lại có ý nghĩa đặc biệt; xem mục 7.

### 4.2. Gắn function vào bảng

~~~sql
CREATE TRIGGER trg_demo_order_row_audit
AFTER INSERT OR UPDATE OR DELETE
ON demo_orders
FOR EACH ROW
EXECUTE FUNCTION demo_log_order_row();
~~~

Vì là `FOR EACH ROW`:

- INSERT 1 hàng → function chạy 1 lần.
- UPDATE 2 hàng → function chạy 2 lần.
- DELETE 3 hàng → function chạy 3 lần.
- UPDATE 0 hàng → function không có lượt row-level nào.

Việc trigger **được gọi** và việc function **ghi log** là hai khái niệm khác: nếu một UPDATE gán lại cùng giá trị, function vẫn có thể được gọi, nhưng điều kiện `IS DISTINCT FROM` khiến nó không ghi bản log UPDATE.

### 4.3. Ví dụ INSERT: chỉ có NEW

~~~sql
BEGIN;

INSERT INTO demo_orders (
    order_id, customer_id, amount, order_status
)
VALUES (105, 4, 90.00, 'NEW');

SELECT operation, order_id,
       old_amount, new_amount, old_status, new_status
FROM demo_order_row_audit
WHERE order_id = 105
ORDER BY audit_id;

ROLLBACK;
~~~

Bảng log trong transaction:

| operation | order_id | old_amount | new_amount | old_status | new_status |
| --- | ---: | --- | ---: | --- | --- |
| INSERT | 105 | NULL | 90.00 | NULL | NEW |

`OLD` không mang một hàng tồn tại trước đó. Chúng ta ghi `NULL` vào cột log old một cách tường minh.

### 4.4. Ví dụ UPDATE: OLD và NEW trên cùng hàng

~~~sql
BEGIN;

UPDATE demo_orders
SET
    amount = 120.00,
    order_status = 'PAID'
WHERE order_id = 101;

SELECT
    operation, order_id,
    old_amount, new_amount,
    old_status, new_status
FROM demo_order_row_audit
WHERE order_id = 101
ORDER BY audit_id;

ROLLBACK;
~~~

Một hàng log UPDATE mới có:

| order_id | old_amount | new_amount | old_status | new_status |
| ---: | ---: | ---: | --- | --- |
| 101 | 100.00 | 120.00 | NEW | PAID |

Lưu ý rằng `OLD.amount` là giá **trước khi cập nhật hàng**, trong khi `NEW.amount` là giá **sau khi cập nhật/đang được xử lý** trong ngữ cảnh AFTER trigger.

### 4.5. Ví dụ DELETE: chỉ có OLD

~~~sql
BEGIN;

DELETE FROM demo_orders
WHERE order_id = 104;

SELECT operation, order_id,
       old_amount, new_amount, old_status, new_status
FROM demo_order_row_audit
WHERE order_id = 104
ORDER BY audit_id;

ROLLBACK;
~~~

Một hàng audit mới:

| operation | order_id | old_amount | new_amount | old_status | new_status |
| --- | ---: | ---: | --- | --- | --- |
| DELETE | 104 | 50.00 | NULL | CANCELLED | NULL |

Không thể đọc `NEW.amount` của hàng bị DELETE như một giá trị “sau xóa”. Sau DELETE, hàng không tồn tại trong bảng đích.

## 5. UPDATE nhiều hàng và row trigger

### 5.1. Một statement, nhiều lượt row trigger

~~~sql
BEGIN;

UPDATE demo_orders
SET
    amount = amount + 20,
    order_status = 'PAID'
WHERE order_id IN (101, 102)
RETURNING order_id, amount, order_status;

SELECT operation, order_id,
       old_amount, new_amount,
       old_status, new_status
FROM demo_order_row_audit
WHERE operation = 'UPDATE'
ORDER BY audit_id;

ROLLBACK;
~~~

Hai hàng bị cập nhật:

| order_id | amount trước | amount sau | status trước | status sau |
| ---: | ---: | ---: | --- | --- |
| 101 | 100.00 | 120.00 | NEW | PAID |
| 102 | 250.00 | 270.00 | NEW | PAID |

Function audit row-level được gọi **hai lần**. Nó không có biến `OLD` “chứa mảng hai hàng”; ở mỗi lần gọi, `OLD` và `NEW` ứng với **một hàng cụ thể**.

### 5.2. Không suy thứ tự xử lý hàng từ thứ tự kết quả

Với:

~~~sql
UPDATE demo_orders
SET amount = amount + 20
WHERE order_id IN (101, 102);
~~~

không được cam kết rằng row trigger cho 101 luôn chạy trước row trigger cho 102. DBMS có thể chọn kế hoạch truy cập khác. Thứ tự lưu `audit_id` phản ánh thứ tự log được tạo trong một thực thi, nhưng không phải quy tắc nghiệp vụ để kết luận thứ tự của các hàng trong mọi lần chạy.

Nếu muốn báo cáo có thứ tự, viết `ORDER BY` ở câu **SELECT đọc log**. Không dùng thứ tự trigger như một “thứ tự xử lý theo ID” được bảo đảm.

### 5.3. UPDATE gán lại giá trị cũ vẫn là một UPDATE

~~~sql
BEGIN;

UPDATE demo_orders
SET amount = amount
WHERE order_id = 101;

SELECT COUNT(*)
FROM demo_order_row_audit
WHERE operation = 'UPDATE'
  AND order_id = 101;

ROLLBACK;
~~~

Câu UPDATE **khớp một hàng** và row-level UPDATE trigger có thể chạy. Nhưng function của ta chỉ insert log khi `OLD.amount IS DISTINCT FROM NEW.amount` hoặc trạng thái khác; vì không thay đổi hai giá trị đó, **không có log UPDATE mới** từ câu này.

Do đó cần phân biệt:

- Hàng **được UPDATE statement nhắm tới**;
- Trigger **được gọi**;
- Giá trị dữ liệu **thật sự thay đổi**;
- Audit **có ghi bản mới hay không** theo điều kiện riêng.

### 5.4. UPDATE 0 hàng

~~~sql
BEGIN;

UPDATE demo_orders
SET amount = amount + 20
WHERE order_id = 999;

ROLLBACK;
~~~

Không có hàng 999 nên **row trigger không có lần chạy nào**. Nhưng statement trigger vẫn có thể được kích hoạt; phần tiếp theo sẽ minh họa.

## 6. PostgreSQL: transition tables OLD TABLE và NEW TABLE

### 6.1. Vì sao phải có bảng chuyển tiếp?

Ở row-level trigger, database gọi logic riêng cho từng hàng. Nhưng khi cần kiểm toán hàng loạt, ta có thể muốn **một câu INSERT ... SELECT** từ toàn bộ tập hàng được UPDATE.

PostgreSQL cung cấp **transition relations**, thường gọi **transition tables**, qua cú pháp:

~~~sql
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
~~~

Với `AFTER UPDATE`, bảng `old_rows` chứa **tập hàng trước UPDATE**, còn `new_rows` chứa **tập hàng sau UPDATE** của statement theo cơ chế hỗ trợ.

Sơ đồ:

~~~text
UPDATE demo_orders
SET amount = amount + 20
WHERE order_id IN (101, 102)
            |
            v
OLD TABLE                 NEW TABLE
+----------+--------+     +----------+--------+
| order_id | amount |     | order_id | amount |
+----------+--------+     +----------+--------+
| 101      | 100    |     | 101      | 120    |
| 102      | 250    |     | 102      | 270    |
+----------+--------+     +----------+--------+
            \              /
             \  JOIN by   /
              \ stable ID/
                |
                v
       Một INSERT ... SELECT
          vào bảng audit
~~~

Đây là **tập quan hệ** chứ không phải hai mảng được sắp theo cùng chỉ số. Không ghép hàng cũ thứ nhất với hàng mới thứ nhất bằng vị trí; phải có **khóa liên hệ**.

### 6.2. Tạo function ghi audit theo tập

~~~sql
CREATE OR REPLACE FUNCTION demo_log_order_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO demo_order_set_audit (
        order_id,
        old_amount, new_amount,
        old_status, new_status
    )
    SELECT
        n.order_id,
        o.amount, n.amount,
        o.order_status, n.order_status
    FROM old_rows AS o
    JOIN new_rows AS n
      ON n.order_id = o.order_id
    WHERE o.amount IS DISTINCT FROM n.amount
       OR o.order_status IS DISTINCT FROM n.order_status;

    RETURN NULL;
END;
$$;
~~~

Bên trong trigger function, hai tên `old_rows` và `new_rows` sẽ được gắn với transition relations bởi `CREATE TRIGGER` bên dưới. Đây không phải hai bảng thường đã tồn tại trong schema.

### 6.3. Tạo AFTER UPDATE trigger cấp statement

~~~sql
CREATE TRIGGER trg_demo_order_set_audit
AFTER UPDATE ON demo_orders
REFERENCING
    OLD TABLE AS old_rows
    NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION demo_log_order_set();
~~~

Ở đây:

- `AFTER UPDATE`: trigger chạy sau thao tác UPDATE theo quy tắc của PostgreSQL.
- `REFERENCING OLD TABLE ... NEW TABLE ...`: cấp quyền tham chiếu hai tập hàng chuyển tiếp.
- `FOR EACH STATEMENT`: function được gọi **một lần cho statement**, không phải một lần mỗi hàng.
- Function dùng **một câu INSERT ... SELECT** để ghi log cho toàn bộ hàng đổi giá trị.

PostgreSQL chỉ hỗ trợ transition tables trong các loại trigger/ngữ cảnh phù hợp, đặc biệt **AFTER triggers** trên bảng thường với các giới hạn. Chúng **không** là tính năng tự động của mọi `BEFORE`, constraint trigger, foreign table hoặc TRUNCATE trigger. Khi dùng transition tables với `UPDATE`, không khai báo danh sách cột kiểu `AFTER UPDATE OF amount` trong cùng trigger, vì PostgreSQL có hạn chế kết hợp này.

### 6.4. Thử UPDATE hai hàng

~~~sql
BEGIN;

UPDATE demo_orders
SET
    amount = amount + 20,
    order_status = 'PAID'
WHERE order_id IN (101, 102);

SELECT
    order_id, old_amount, new_amount,
    old_status, new_status
FROM demo_order_set_audit
ORDER BY order_id;

ROLLBACK;
~~~

Hai hàng trong log cấp tập:

| order_id | old_amount | new_amount | old_status | new_status |
| ---: | ---: | ---: | --- | --- |
| 101 | 100.00 | 120.00 | NEW | PAID |
| 102 | 250.00 | 270.00 | NEW | PAID |

Function `demo_log_order_set` chỉ chạy một lần cho câu UPDATE, nhưng câu `INSERT ... SELECT` bên trong chèn được **hai hàng log**.

Bây giờ cả row trigger (mục 4) lẫn statement trigger (mục 6) cùng được gắn lên `demo_orders`. Vì ta sử dụng **hai bảng log khác nhau**, có thể quan sát cả hai cách. Trong hệ thống thực, nếu cả hai ghi cùng sự kiện vào một audit stream, có nguy cơ **log trùng**; hãy chọn mô hình hoặc phân chia trách nhiệm rõ.

### 6.5. Statement trigger vẫn chạy khi UPDATE 0 hàng

~~~sql
BEGIN;

UPDATE demo_orders
SET amount = amount + 10
WHERE order_id = 999;

SELECT COUNT(*) AS set_audit_rows
FROM demo_order_set_audit;

ROLLBACK;
~~~

Nếu bảng `demo_order_set_audit` ban đầu rỗng, số hàng vẫn là **0**. Nhưng không nên kết luận function không được gọi:

- Câu `UPDATE` xảy ra và `AFTER ... FOR EACH STATEMENT` vẫn có thể chạy.
- `old_rows` và `new_rows` là **hai tập rỗng**.
- `INSERT ... SELECT ... JOIN ...` từ hai tập rỗng chèn **0 hàng**.

Để quan sát số lần gọi statement trigger, có thể làm một bảng summary và ghi **một hàng cho mỗi statement**, kể cả số hàng bằng 0.

### 6.6. Ghi số hàng bị tác động, kể cả 0 hàng

Tạo bảng summary độc lập:

~~~sql
CREATE TABLE demo_order_stmt_summary (
    summary_id     BIGINT GENERATED ALWAYS AS IDENTITY
                   PRIMARY KEY,
    operation      TEXT NOT NULL,
    affected_rows  BIGINT NOT NULL,
    logged_at      TIMESTAMPTZ NOT NULL
                   DEFAULT CURRENT_TIMESTAMP
);
~~~

Function summary:

~~~sql
CREATE OR REPLACE FUNCTION demo_count_updated_orders()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM new_rows;

    INSERT INTO demo_order_stmt_summary (
        operation, affected_rows
    )
    VALUES ('UPDATE', v_count);

    RETURN NULL;
END;
$$;
~~~

Gắn trigger:

~~~sql
CREATE TRIGGER trg_demo_count_updated_orders
AFTER UPDATE ON demo_orders
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION demo_count_updated_orders();
~~~

Ví dụ:

~~~sql
BEGIN;

UPDATE demo_orders
SET amount = amount
WHERE order_id = 999;

SELECT operation, affected_rows
FROM demo_order_stmt_summary
ORDER BY summary_id;

ROLLBACK;
~~~

Lệnh UPDATE không khớp hàng nào nhưng summary trigger cấp statement vẫn ghi:

| operation | affected_rows |
| --- | ---: |
| UPDATE | 0 |

Nếu UPDATE khớp hai hàng, summary có `affected_rows=2`, kể cả khi giá trị cột được gán bằng chính giá trị cũ. `COUNT(*)` trong transition table đếm **hàng được UPDATE**, không phải số cột đổi giá trị hay số hàng audit lọc ra là “thật sự thay đổi”.

### 6.7. INSERT và DELETE chỉ có một phía của tập chuyển tiếp

Với PostgreSQL:

- `AFTER INSERT ... REFERENCING NEW TABLE AS inserted_rows`: dùng tập hàng được chèn.
- `AFTER DELETE ... REFERENCING OLD TABLE AS deleted_rows`: dùng tập hàng bị xóa.
- `AFTER UPDATE ... REFERENCING OLD TABLE ... NEW TABLE ...`: có cả trước và sau.

Ví dụ trigger summary cho INSERT:

~~~sql
CREATE OR REPLACE FUNCTION demo_count_inserted_orders()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM inserted_rows;

    INSERT INTO demo_order_stmt_summary (
        operation, affected_rows
    )
    VALUES ('INSERT', v_count);

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_demo_count_inserted_orders
AFTER INSERT ON demo_orders
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION demo_count_inserted_orders();
~~~

Thử:

~~~sql
BEGIN;

INSERT INTO demo_orders (
    order_id, customer_id, amount, order_status
)
VALUES
    (105, 4, 90.00, 'NEW'),
    (106, 4, 20.00, 'NEW');

SELECT operation, affected_rows
FROM demo_order_stmt_summary
WHERE operation = 'INSERT'
ORDER BY summary_id;

ROLLBACK;
~~~

Một statement INSERT hai hàng tạo summary `INSERT, 2`.

Tương tự, function cho DELETE có thể `SELECT COUNT(*) FROM deleted_rows` và trigger khai báo `REFERENCING OLD TABLE AS deleted_rows`; không có lý do tham chiếu `NEW TABLE` của DELETE.

### 6.8. Transition tables là theo statement, không phải cả transaction

Một transaction gồm hai UPDATE:

~~~sql
BEGIN;

UPDATE demo_orders
SET amount = amount + 10
WHERE order_id = 101;

UPDATE demo_orders
SET amount = amount + 20
WHERE order_id = 102;

ROLLBACK;
~~~

Có **hai câu UPDATE**, vì vậy statement-level UPDATE triggers có thể chạy **hai lần**, mỗi lần có tập chuyển tiếp riêng của câu lệnh tương ứng.

Transition relation **không tự gom tất cả hàng được thay đổi từ đầu tới cuối transaction**. Nếu cần audit theo giao dịch hoặc request ID, thiết kế một khóa tương quan/transaction metadata riêng và lưu ở đúng phạm vi, không suy một lần gọi trigger bằng một transaction.

## 7. BEFORE khác AFTER: NEW có thể bị sửa khi nào?

### 7.1. BEFORE ROW trigger: kiểm tra hoặc chỉnh NEW

PostgreSQL cho phép `BEFORE INSERT` hoặc `BEFORE UPDATE` row trigger thay đổi các trường trong `NEW` trước khi hàng được ghi.

Ví dụ tự đặt thời gian khi dữ liệu nghiệp vụ thực sự đổi:

~~~sql
CREATE OR REPLACE FUNCTION demo_stamp_order_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.amount IS DISTINCT FROM NEW.amount
       OR OLD.order_status IS DISTINCT FROM NEW.order_status
    THEN
        NEW.updated_at := statement_timestamp();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_demo_stamp_order_update
BEFORE UPDATE ON demo_orders
FOR EACH ROW
EXECUTE FUNCTION demo_stamp_order_update();
~~~

`NEW.updated_at := statement_timestamp()` thay đổi bản ghi **đang chuẩn bị ghi**. `RETURN NEW` cho PostgreSQL tiếp tục xử lý hàng với dữ liệu đó.

Nếu sau đó `AFTER UPDATE` trigger ghi log, `NEW` của nó phản ánh kết quả sau khi những `BEFORE` trigger phù hợp đã tác động lên hàng theo quy tắc engine. Không suy từ ví dụ rằng mọi DBMS hỗ trợ gán trực tiếp `NEW` trong AFTER trigger.

### 7.2. BEFORE UPDATE: OLD có thể đọc, không nên coi là dữ liệu để sửa

Trong PostgreSQL, với UPDATE:

- `OLD` biểu diễn hàng trước sửa, dùng cho kiểm tra/đối chiếu.
- `NEW` là hàng đề xuất sửa và có thể bị điều chỉnh bởi `BEFORE ROW` trigger.
- Kết quả `RETURN NEW` mới ảnh hưởng hàng được ghi.
- Việc thay đổi các trường của `OLD` không phải cách cập nhật hàng đích.

Trong MySQL và Oracle cũng có những quy tắc riêng về giá trị cũ là chỉ đọc và giá trị mới trong BEFORE row trigger; không sao chép cú pháp gán `NEW.field := ...` của PostgreSQL vào MySQL, nơi thường dùng `SET NEW.field = ...`.

### 7.3. RETURN NULL trong BEFORE ROW có thể bỏ qua hàng

Ví dụ chỉ để giải thích, **không dùng để im lặng bỏ giao dịch quan trọng**:

~~~sql
CREATE OR REPLACE FUNCTION demo_skip_zero_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.amount = 0 THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$$;
~~~

Nếu function này được gắn là `BEFORE INSERT ... FOR EACH ROW`, `RETURN NULL` có thể làm PostgreSQL **bỏ qua thao tác INSERT cho hàng hiện tại**. Những hàng khác trong cùng statement có thể vẫn được xử lý theo quy tắc SQL/trigger.

Điều này khác hoàn toàn với `RETURN NULL` ở `AFTER ROW` trigger, nơi giá trị trả về **bị bỏ qua**. Nếu chỉ muốn từ chối dữ liệu đầu vào sai, thường nên dùng `NOT NULL`, `CHECK` hoặc `RAISE EXCEPTION` với lý do rõ thay vì bỏ hàng âm thầm.

### 7.4. BEFORE DELETE: trả OLD để cho phép xóa

Một `BEFORE DELETE FOR EACH ROW` function PostgreSQL thường cần `RETURN OLD;` nếu muốn tiếp tục xóa. `RETURN NULL;` trong BEFORE row trigger có thể chặn thao tác với hàng đó.

Ví dụ khung:

~~~sql
CREATE OR REPLACE FUNCTION demo_before_delete_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.order_status = 'PAID' THEN
        RAISE EXCEPTION
            'Khong xoa don PAID: %', OLD.order_id;
    END IF;

    RETURN OLD;
END;
$$;
~~~

Function này chưa được gắn vào bảng mẫu; nếu gắn thành BEFORE DELETE, việc xóa đơn PAID sẽ phát sinh exception theo chính sách minh họa. Không viết `RETURN NEW` cho DELETE khi không có bản ghi NEW.

### 7.5. AFTER phù hợp cho audit các thay đổi đã qua bước BEFORE

Một `AFTER` trigger phù hợp để ghi log DML trong cùng transaction vì nó chạy sau phần thao tác tương ứng theo cơ chế DBMS, có thể quan sát giá trị NEW sau các điều chỉnh BEFORE.

Nhưng **“AFTER” không đồng nghĩa “sau COMMIT”**:

- Nếu transaction về sau `ROLLBACK`, bản ghi audit được ghi bằng SQL thông thường trong cùng transaction cũng bị rollback.
- Dùng AFTER trigger không có nghĩa có thể gửi email/webhook ra ngoài rồi chắc chắn transaction sẽ commit.
- Trigger ghi bảng audit và giao dịch chính vẫn cùng một hệ giao dịch; với side effects bên ngoài nên xem mô hình **transactional outbox** hoặc worker gửi sự kiện sau khi dữ liệu đã commit.

### 7.6. Cẩn thận khi UPDATE chính bảng trong trigger

Một anti-pattern:

~~~sql
-- Trong AFTER UPDATE trigger, lại UPDATE chính demo_orders:
UPDATE demo_orders
SET updated_at = CURRENT_TIMESTAMP
WHERE order_id = NEW.order_id;
~~~

Câu UPDATE mới có thể kích hoạt trigger UPDATE của chính bảng một lần nữa, gây **đệ quy trigger**, lặp, contention và audit dư thừa.

Trong PostgreSQL, nếu chỉ muốn sửa cột của chính hàng đang được cập nhật, thường dùng `BEFORE UPDATE FOR EACH ROW` để gán vào `NEW.updated_at` và `RETURN NEW`. Nếu thực sự phải cập nhật các hàng khác, thiết kế điều kiện chống đệ quy và transaction logic rõ ràng.

## 8. So sánh OLD và NEW đúng cách, kể cả NULL

### 8.1. Không dùng <> một cách mù quáng với NULL

Giả sử một cột nullable có:

~~~text
OLD.note = NULL
NEW.note = 'Da giao'
~~~

Biểu thức:

~~~sql
OLD.note <> NEW.note
~~~

trả **NULL/UNKNOWN**, không phải TRUE. Nếu đặt trong `IF`, có thể không đi vào nhánh như mong đợi.

PostgreSQL hỗ trợ:

~~~sql
OLD.note IS DISTINCT FROM NEW.note
~~~

cho kết quả TRUE khi một phía NULL và phía kia không NULL.

### 8.2. Bốn trường hợp so sánh

| OLD.x | NEW.x | `OLD.x <> NEW.x` | `OLD.x IS DISTINCT FROM NEW.x` |
| --- | --- | --- | --- |
| 10 | 10 | FALSE | FALSE |
| 10 | 20 | TRUE | TRUE |
| NULL | 10 | NULL | TRUE |
| NULL | NULL | NULL | FALSE |

Trong SQL Server, phiên bản hiện đại có cú pháp null-safe `IS DISTINCT FROM`, nhưng khi cần tương thích những phiên bản cũ, có thể dùng mẫu xử lý NULL bằng `EXCEPT` hoặc biểu thức tường minh. MySQL có toán tử null-safe equality `<=>`; SQLite dùng `IS`/`IS NOT` theo cú pháp và quy tắc engine.

### 8.3. Không nhầm “cột được nêu trong UPDATE” và “cột thực sự đổi”

PostgreSQL cho phép trigger theo cột, ví dụ:

~~~sql
CREATE TRIGGER trg_demo_amount_update
AFTER UPDATE OF amount
ON demo_orders
FOR EACH ROW
EXECUTE FUNCTION demo_log_order_row();
~~~

Đây là **một ví dụ trigger độc lập**, chưa cần tạo thêm trên bảng đang có audit trigger. Ý nghĩa `UPDATE OF amount` gắn với việc cột `amount` được nêu như mục tiêu cập nhật ở câu lệnh `SET`, **không mặc định chứng minh giá trị thực sự khác**.

Ví dụ:

~~~sql
UPDATE demo_orders
SET amount = amount
WHERE order_id = 101;
~~~

Cột `amount` vẫn xuất hiện trong danh sách `SET`. Nếu cần chỉ chạy logic khi số tiền đổi thực sự, so `OLD.amount` và `NEW.amount` một cách null-safe.

### 8.4. PostgreSQL WHEN lọc lời gọi row trigger

Có thể yêu cầu `AFTER UPDATE ROW` trigger chỉ gọi function nếu những giá trị cần theo dõi thay đổi:

~~~sql
CREATE TRIGGER trg_demo_amount_changed
AFTER UPDATE ON demo_orders
FOR EACH ROW
WHEN (OLD.amount IS DISTINCT FROM NEW.amount)
EXECUTE FUNCTION demo_log_order_row();
~~~

Đoạn này là **mẫu minh họa cách dùng `WHEN`**, không cần tạo cùng lúc với các trigger audit khác vì sẽ sinh các bản log trùng. Trong PostgreSQL, `WHEN` của row-level trigger có thể tham chiếu `OLD`/`NEW` theo sự kiện phù hợp. Với trigger dùng transition table và `FOR EACH STATEMENT`, không dùng `OLD.amount` như thể OLD là một hàng duy nhất.

### 8.5. Biểu thức so sánh nhiều cột

Có thể viết:

~~~sql
IF OLD.amount IS DISTINCT FROM NEW.amount
   OR OLD.order_status IS DISTINCT FROM NEW.order_status
THEN
    -- Ghi audit một lần cho hàng này.
END IF;
~~~

Nếu nghiệp vụ quan tâm thêm `updated_at`, cân nhắc xem cột timestamp do trigger tự thay đổi có nên tính là một thay đổi cần log không. Nếu đưa quá nhiều cột kỹ thuật vào điều kiện, một UPDATE không mang thay đổi nghiệp vụ có thể vẫn tạo nhiều log.

## 9. Ghép OLD TABLE với NEW TABLE theo khóa ổn định

### 9.1. Vì sao JOIN theo order_id hoạt động trong ví dụ?

Trong mẫu:

~~~sql
FROM old_rows AS o
JOIN new_rows AS n
  ON n.order_id = o.order_id
~~~

ta giả định `order_id` **không đổi trong câu UPDATE**. Vì nó là khóa chính và không bị chỉnh sửa, có đúng một cặp hàng trước/sau cho mỗi đơn bị cập nhật.

Tuy vậy `PRIMARY KEY` không tự cấm một câu UPDATE đổi giá trị khóa. Nếu hệ thống cho phép đổi `order_id` từ 101 sang 201, thì:

~~~text
OLD TABLE: order_id = 101
NEW TABLE: order_id = 201
~~~

Hai hàng **không thể JOIN với nhau bằng điều kiện `old.order_id = new.order_id`**. Bản audit theo tập sẽ bỏ sót cặp hàng nếu dùng INNER JOIN như trên.

### 9.2. Khi khóa có thể thay đổi

Cần một **định danh bất biến** để nối cặp OLD và NEW, chẳng hạn một cột surrogate key không được phép cập nhật:

~~~text
internal_row_id = 7829  (không đổi)
business_code   = BK-001 → BK-202
~~~

Ghép theo `internal_row_id` sẽ giữ tương quan đúng. Nhưng nếu tất cả khóa ứng viên đều có thể đổi, hai tập OLD/NEW **không cung cấp một phép ghép cặp tự động bằng thứ tự**. Có thể cần row-level trigger, thiết kế định danh khác hoặc cơ chế đặc thù DBMS.

### 9.3. Không dùng ROW_NUMBER để tự ghép hai tập

Mẫu nguy hiểm:

~~~text
OLD row số 1 ↔ NEW row số 1
OLD row số 2 ↔ NEW row số 2
~~~

Không có cam kết rằng hai transition tables chứa các hàng theo cùng một thứ tự vật lý. Thêm `ROW_NUMBER() OVER (ORDER BY amount)` riêng cho OLD và NEW cũng không đảm bảo hai hàng cùng thực thể giữ cùng thứ tự sau khi `amount` đổi.

**Cần khóa tương quan ổn định**, không phải một thứ tự suy đoán.

### 9.4. Hàng bị ảnh hưởng và cột thay đổi là hai đại lượng khác nhau

Một UPDATE:

~~~sql
UPDATE demo_orders
SET amount = amount,
    order_status = order_status
WHERE order_id IN (101, 102);
~~~

có thể tạo tập chuyển tiếp gồm **hai hàng**, dù giá trị của chúng không đổi. Chỉ tiêu:

- `COUNT(*) FROM new_rows` = 2 (số hàng được UPDATE statement xử lý theo tập);
- Số hàng được lọc bằng `IS DISTINCT FROM` cho hai cột = 0;
- Số cột được nêu trong SET = 2.

Ba số không nên bị ghi chung thành một nhãn “số thay đổi thực tế”.

## 10. SQL Server: inserted và deleted luôn là tập hàng

### 10.1. Mô hình khác PostgreSQL

Trong **SQL Server DML trigger**, có hai logical tables:

- `inserted` chứa các hàng **được chèn** hoặc **giá trị sau UPDATE**.
- `deleted` chứa các hàng **bị xóa** hoặc **giá trị trước UPDATE**.

Chúng là **tập hàng** ngay cả khi câu UPDATE chỉ sửa một hàng. SQL Server không có cùng loại `FOR EACH ROW` trigger của PostgreSQL/MySQL.

| SQL Server DML | `inserted` | `deleted` |
| --- | --- | --- |
| INSERT | Các hàng mới | Rỗng |
| UPDATE | Các hàng sau cập nhật | Các hàng trước cập nhật |
| DELETE | Rỗng | Các hàng trước xóa |

Không viết:

~~~sql
-- Không an toàn nếu statement ảnh hưởng nhiều hàng:
SELECT @order_id = order_id
FROM inserted;
~~~

rồi giả định `@order_id` đại diện **mọi** hàng được chèn/cập nhật. Khi `inserted` có nhiều hàng, gán vào một biến scalar có thể chỉ giữ một giá trị theo cách không xác định hữu ích cho nghiệp vụ.

### 10.2. Ví dụ audit set-based trên SQL Server

Giả sử có bảng `dbo.demo_orders` và `dbo.demo_order_audit` với các cột tương ứng. T-SQL:

~~~sql
-- SQL Server: chạy trong database có schema tương ứng.
CREATE OR ALTER TRIGGER dbo.trg_demo_order_audit
ON dbo.demo_orders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.demo_order_audit (
        order_id,
        old_amount, new_amount,
        old_status, new_status
    )
    SELECT
        i.order_id,
        d.amount, i.amount,
        d.order_status, i.order_status
    FROM inserted AS i
    INNER JOIN deleted AS d
      ON d.order_id = i.order_id
    WHERE
        i.amount <> d.amount
        OR i.order_status <> d.order_status;
END;
GO
~~~

Ví dụ này giả định `amount` và `order_status` đều `NOT NULL` như bảng mẫu; với cột nullable phải dùng so sánh **an toàn với NULL**. `GO` thường là batch separator của công cụ SQL Server như SSMS/sqlcmd, không phải SQL statement được mọi driver gửi nguyên văn.

Điểm quan trọng: câu `INSERT ... SELECT` dùng **toàn bộ tập `inserted` và `deleted`**, nên không bỏ sót hàng khi UPDATE sửa 2, 200 hoặc 2000 hàng.

### 10.3. Kiểm tra thay đổi NULL-safe trong T-SQL

Một cách tương thích với các phiên bản SQL Server không có `IS DISTINCT FROM` là dùng `EXCEPT` để so một bộ giá trị. SQL Server `EXCEPT` xem các giá trị NULL là tương đương khi xác định tập:

~~~sql
-- Dùng trong WHERE của câu JOIN inserted/deleted.
WHERE EXISTS (
    SELECT
        i.amount,
        i.order_status
    EXCEPT
    SELECT
        d.amount,
        d.order_status
)
~~~

Nếu hai bộ giá trị bằng nhau, `EXCEPT` trả rỗng. Nếu khác, kể cả NULL ở một phía, nó trả một hàng. Khi so nhiều cột, kiểu dữ liệu giữa hai phía phải tương thích theo quy tắc SQL Server.

Ở các phiên bản hỗ trợ `IS DISTINCT FROM`, có thể dùng trực tiếp cho từng cột.

### 10.4. INSERT/DELETE trong SQL Server

Với trigger sau INSERT:

~~~sql
CREATE OR ALTER TRIGGER dbo.trg_demo_order_inserted
ON dbo.demo_orders
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.demo_insert_audit (
        order_id, amount
    )
    SELECT order_id, amount
    FROM inserted;
END;
GO
~~~

`dbo.demo_insert_audit` là bảng giả định cần tạo nếu chạy ví dụ này.

Tương tự, trigger DELETE đọc `deleted`:

~~~sql
CREATE OR ALTER TRIGGER dbo.trg_demo_order_deleted
ON dbo.demo_orders
AFTER DELETE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.demo_delete_audit (
        order_id, old_amount
    )
    SELECT order_id, amount
    FROM deleted;
END;
GO
~~~

Hai bảng audit là ví dụ giả định nhằm làm rõ nguồn dữ liệu. Không mong `inserted` chứa hàng bị DELETE hoặc `deleted` chứa hàng được INSERT.

### 10.5. Trigger SQL Server có thể chạy khi 0 hàng bị tác động

Một trigger SQL Server gắn với DML statement có thể được kích hoạt ngay cả khi statement ảnh hưởng **0 hàng**. `inserted`/`deleted` khi đó rỗng cho trường hợp liên quan.

Có thể viết điều kiện:

~~~sql
IF NOT EXISTS (SELECT 1 FROM inserted)
   AND NOT EXISTS (SELECT 1 FROM deleted)
BEGIN
    RETURN;
END;
~~~

trong trigger phù hợp để bỏ qua công việc không cần thiết khi cả hai tập rỗng. Nhưng không được dùng kiểm tra “inserted rỗng” riêng lẻ để kết luận chẳng có DELETE: với DELETE, `deleted` mới là tập có dữ liệu.

### 10.6. UPDATE(column) và COLUMNS_UPDATED không đồng nghĩa giá trị khác

Trong SQL Server:

~~~sql
IF UPDATE(amount)
BEGIN
    -- Cột amount xuất hiện như mục tiêu của thao tác.
END;
~~~

`UPDATE(amount)` không phải phép so `deleted.amount` với `inserted.amount`. Nó có thể TRUE khi cột được nêu trong SET nhưng giá trị sau cùng không đổi.

`COLUMNS_UPDATED()` là bitmask cho các cột được chỉ định trong DML, cũng không thay thế so dữ liệu cũ/mới. Nếu audit chỉ được ghi khi giá trị đổi, sử dụng `inserted`/`deleted` và phép so phù hợp.

### 10.7. SQL Server OUTPUT khác inserted/deleted trong trigger

T-SQL còn có mệnh đề `OUTPUT` của DML:

~~~sql
UPDATE dbo.demo_orders
SET amount = amount + 20
OUTPUT
    DELETED.order_id,
    DELETED.amount AS old_amount,
    INSERTED.amount AS new_amount
WHERE order_id IN (101, 102);
~~~

`OUTPUT` cho câu UPDATE trả thông tin trực tiếp về các hàng cũ/mới. Các tên `DELETED`/`INSERTED` trong `OUTPUT` liên quan đến cùng khái niệm hình ảnh hàng, nhưng **ngữ cảnh sử dụng khác**: một bên là mệnh đề trả kết quả của DML, một bên là hai logical tables đọc trong trigger.

Có những hạn chế liên quan trigger và `OUTPUT INTO` theo schema/phiên bản; không coi đây là cú pháp PostgreSQL.

## 11. MySQL: chỉ có row-level trigger với OLD và NEW

### 11.1. MySQL không có statement trigger kiểu PostgreSQL

MySQL hỗ trợ trigger `BEFORE`/`AFTER` trên `INSERT`/`UPDATE`/`DELETE` với `FOR EACH ROW`. Khi một câu UPDATE sửa 100 hàng, trigger có thể được thực thi 100 lần — **không có bảng chuyển tiếp statement-level `OLD TABLE`/`NEW TABLE` tương đương PostgreSQL**.

Các tham chiếu:

- INSERT: `NEW.column`.
- UPDATE: `OLD.column` và `NEW.column`.
- DELETE: `OLD.column`.

### 11.2. BEFORE UPDATE có thể chỉnh NEW trong MySQL

Ví dụ cú pháp MySQL, giả định bảng `demo_orders` tương ứng đã có:

~~~sql
DELIMITER //

CREATE TRIGGER trg_demo_orders_stamp
BEFORE UPDATE ON demo_orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.amount <=> NEW.amount)
       OR NOT (OLD.order_status <=> NEW.order_status)
    THEN
        SET NEW.updated_at = CURRENT_TIMESTAMP;
    END IF;
END//

DELIMITER ;
~~~

`<=>` là toán tử so sánh bằng **NULL-safe** trong MySQL. `NOT (OLD.amount <=> NEW.amount)` nghĩa là hai giá trị khác nhau kể cả khi một phía NULL.

Trong MySQL:

- `OLD.column` là giá trị cũ và chỉ đọc.
- `NEW.column` ở BEFORE trigger có thể được gán theo quy tắc hỗ trợ.
- Không sửa `NEW.column` trong AFTER trigger như cách gán của BEFORE.
- `DELIMITER` là lệnh của một số client SQL dùng để tách câu lệnh, không phải cú pháp SQL server phổ quát.

### 11.3. AFTER UPDATE audit từng hàng

~~~sql
DELIMITER //

CREATE TRIGGER trg_demo_orders_audit
AFTER UPDATE ON demo_orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.amount <=> NEW.amount)
       OR NOT (OLD.order_status <=> NEW.order_status)
    THEN
        INSERT INTO demo_order_row_audit (
            operation, order_id,
            old_amount, new_amount,
            old_status, new_status
        )
        VALUES (
            'UPDATE', NEW.order_id,
            OLD.amount, NEW.amount,
            OLD.order_status, NEW.order_status
        );
    END IF;
END//

DELIMITER ;
~~~

Đây là **cú pháp MySQL**; schema bảng audit/định danh cần được điều chỉnh theo MySQL (ví dụ identity/auto-increment của PostgreSQL không sao chép nguyên văn).

Nếu DML sửa nhiều hàng, function của trigger xử lý riêng từng cặp OLD/NEW. Muốn tổng hợp theo toàn bộ statement, cần thiết kế khác (như xử lý dữ liệu theo tập ở ứng dụng/bảng staging), không giả định một biến `inserted` nhiều hàng có sẵn.

### 11.4. Điều kiện và giao dịch vẫn quan trọng

Với InnoDB, những thay đổi do trigger thực hiện trong cùng giao dịch có thể rollback cùng DML. Không suy rằng cùng quy tắc áp dụng cho mọi storage engine/side effect bên ngoài. Trigger ghi audit không tự tạo event “đã commit” trước khi transaction được commit.

Nếu trigger phải từ chối dữ liệu, MySQL hỗ trợ `SIGNAL SQLSTATE` ở ngữ cảnh thích hợp:

~~~sql
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'Gia tri khong hop le';
~~~

Đó là cơ chế báo lỗi, không phải bỏ qua hàng một cách im lặng.

## 12. SQLite: OLD và NEW trong row trigger

### 12.1. SQLite dùng trigger theo hàng

SQLite hỗ trợ trigger `BEFORE`, `AFTER`, `INSTEAD OF` theo loại đối tượng/sự kiện, với dữ liệu hàng có thể tham chiếu qua `OLD.column` và `NEW.column` khi thích hợp. SQLite **không có statement-level trigger** tương đương PostgreSQL `FOR EACH STATEMENT` có transition tables.

Ví dụ SQLite AFTER UPDATE cho cột `amount`:

~~~sql
CREATE TRIGGER trg_demo_order_amount_audit
AFTER UPDATE OF amount ON demo_orders
FOR EACH ROW
WHEN OLD.amount IS NOT NEW.amount
BEGIN
    INSERT INTO demo_order_row_audit (
        operation, order_id,
        old_amount, new_amount,
        old_status, new_status
    )
    VALUES (
        'UPDATE', NEW.order_id,
        OLD.amount, NEW.amount,
        OLD.order_status, NEW.order_status
    );
END;
~~~

Đoạn này giả định bảng audit tương ứng tồn tại trong SQLite. `IS NOT` giúp phân biệt giá trị khác nhau theo ngữ nghĩa có xét NULL của SQLite. Không dùng cú pháp `OLD TABLE` hoặc `REFERENCING ... TABLE` của PostgreSQL trong SQLite.

### 12.2. Không gán NEW trong SQLite theo cú pháp PostgreSQL

Không sao chép câu:

~~~sql
NEW.updated_at := CURRENT_TIMESTAMP;
~~~

vào một SQLite trigger và tưởng nó sửa bản ghi mới. SQLite không có phép gán trực tiếp vào `NEW` theo kiểu PL/pgSQL `:=` hay MySQL `SET NEW.col = ...`.

Nếu cần tự cập nhật timestamp, cân nhắc default, logic ứng dụng, hoặc mẫu trigger/UPDATE tương thích với SQLite đã được thiết kế chống đệ quy. Cần xét `recursive_triggers`, mức thay đổi hàng và side effects trước khi lựa chọn.

### 12.3. WHEN lọc gọi trigger

SQLite cho phép `WHEN` trong khai báo trigger để điều kiện hóa thực thi thân, ví dụ chỉ log khi tiền đổi. Nhưng điều đó **không biến SQLite thành statement-level trigger** và không thay bảo đảm về transaction.

## 13. Oracle PL/SQL: :OLD và :NEW trong row trigger

### 13.1. Cú pháp Oracle với dấu hai chấm

Oracle row-level trigger dùng `:OLD` và `:NEW`:

~~~sql
-- Oracle PL/SQL, giả định demo_orders tồn tại.
CREATE OR REPLACE TRIGGER trg_demo_orders_check
BEFORE UPDATE OF amount
ON demo_orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'So tien phai khong am va khong NULL'
        );
    END IF;
END;
/
~~~

`/` là lệnh thực thi khối PL/SQL trong một số client, không phải phần SQL chuẩn được mọi driver gửi nguyên văn.

Các điểm cần nhớ:

- `:OLD.amount`: giá trị trước UPDATE.
- `:NEW.amount`: giá trị đang đề xuất sau UPDATE trong row trigger.
- Trong BEFORE row trigger, có thể thay đổi `:NEW` theo quy tắc Oracle.
- Trong AFTER row trigger, không sửa `:NEW`.
- Trigger cấp statement không có bản ghi `:OLD`/`:NEW` của một hàng duy nhất.

### 13.2. REFERENCING OLD AS/NEW AS không phải transition TABLE

Oracle có thể cho phép khai báo tên tương quan cho row values:

~~~sql
-- Cú pháp khái niệm Oracle:
REFERENCING OLD AS old_row NEW AS new_row
~~~

Điều này đặt tên cho **row pseudorecords** ở row trigger; nó **không tương đương** PostgreSQL `REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows`.

Dấu hai chấm ở trong thân PL/SQL gắn với cách tham chiếu correlation values. Không cố dùng Oracle `REFERENCING OLD AS ...` để đọc một tập hàng cả statement.

### 13.3. Compound trigger khi cần phối hợp nhiều thời điểm

Oracle hỗ trợ **compound triggers** với các phần như:

- `BEFORE STATEMENT`;
- `BEFORE EACH ROW`;
- `AFTER EACH ROW`;
- `AFTER STATEMENT`.

Compound trigger có thể giữ trạng thái dùng chung cho một statement để thu thập thông tin từng hàng rồi thực hiện logic theo tập ở phần sau, theo giới hạn của Oracle. Đây là kỹ thuật riêng, không phải tự động có bảng `inserted`/`deleted` của SQL Server.

Đặc biệt cần chú ý **mutating-table restrictions** khi row trigger Oracle đọc hoặc sửa chính bảng đang được thay đổi. Một thiết kế compound trigger đúng có thể giúp giải quyết một số bài toán tổng hợp, nhưng vẫn phải xử lý khả năng nhiều hàng, khóa ổn định và transaction.

## 14. BEFORE, AFTER, INSTEAD OF và phạm vi thực thi

### 14.1. BEFORE

Dùng khi cần:

- Kiểm tra dữ liệu đầu vào;
- Chuẩn hóa giá trị `NEW` theo tính năng engine;
- Từ chối dữ liệu không hợp lệ;
- Tránh cần UPDATE lại cùng hàng trong AFTER.

Điều cần nhớ: `OLD` là hình ảnh trước thay đổi, `NEW` là hình ảnh **đang đề xuất**; một số DBMS cho phép sửa `NEW` trong BEFORE row trigger, nhưng không phải mọi loại trigger đều cho phép.

### 14.2. AFTER

Dùng khi cần:

- Ghi audit trong cùng transaction;
- Ghi sự kiện nội bộ/outbox sau DML;
- Tính số hàng của statement qua transition relations;
- Phản ứng sau khi hàng được thao tác theo ngữ nghĩa engine.

Không coi AFTER đồng nghĩa **sau COMMIT**.

### 14.3. INSTEAD OF

Một số DBMS như SQL Server, Oracle và SQLite hỗ trợ `INSTEAD OF` triggers trong những ngữ cảnh thích hợp, thường liên quan **view** hoặc thay thế xử lý DML mặc định.

Ví dụ, một view ghép nhiều bảng không cập nhật trực tiếp được có thể dùng INSTEAD OF trigger để định nghĩa cách phân phối thay đổi về các bảng nền.

Ngữ nghĩa `OLD`/`NEW` hoặc `inserted`/`deleted` ở INSTEAD OF cần đọc theo DBMS, vì thao tác đích **không tự xảy ra như AFTER trigger**. Không suy rằng mọi INSTEAD OF trigger đều có “hàng mới đã ghi” trong bảng nền.

### 14.4. Trigger level và timing là hai trục độc lập

Trong PostgreSQL có thể hình dung:

| Timing | FOR EACH ROW | FOR EACH STATEMENT |
| --- | --- | --- |
| BEFORE | Có, dùng OLD/NEW tương ứng | Có, không có cặp OLD/NEW cho từng hàng |
| AFTER | Có, dùng OLD/NEW tương ứng | Có; transition tables ở những ngữ cảnh phù hợp |
| INSTEAD OF | Hỗ trợ ở các loại đối tượng phù hợp, ví dụ view | Không phải lựa chọn tự do cho mọi đối tượng |
| TRUNCATE | Không có row trigger TRUNCATE | Có BEFORE/AFTER TRUNCATE statement triggers |

Không tự động suy rằng MySQL/SQLite có bảng timing × level giống PostgreSQL hoặc SQL Server.

## 15. DML nhiều hàng, CTE, UPSERT và MERGE: điều gì được ghi log?

### 15.1. INSERT ... SELECT có thể thêm nhiều hàng

~~~sql
INSERT INTO demo_orders (
    order_id, customer_id, amount, order_status
)
SELECT
    1000 + x,
    10,
    x * 10,
    'NEW'
FROM generate_series(1, 3) AS g(x);
~~~

Câu PostgreSQL này thêm ba hàng nếu không vi phạm khóa/ràng buộc. Row trigger INSERT chạy theo từng hàng, còn statement trigger INSERT có transition table `NEW TABLE` có thể nhìn thấy ba hàng.

Không viết trigger giả định `INSERT` chỉ thêm một hàng vì giao diện người dùng thường tạo một đơn một lần.

### 15.2. UPDATE ... FROM có thể cập nhật nhiều hàng

~~~sql
UPDATE demo_orders AS o
SET amount = o.amount * 1.10
FROM (
    VALUES
        (101::BIGINT),
        (102::BIGINT)
) AS selected(order_id)
WHERE o.order_id = selected.order_id;
~~~

Row trigger chạy với mỗi hàng được cập nhật. Statement transition tables chứa tập trước/sau của statement. Nếu bảng nguồn `selected` có nhiều hàng khớp cùng một hàng đích, phải xác định tính duy nhất của nguồn và ngữ nghĩa DBMS; trigger không tự chữa một UPDATE JOIN thiếu tính đơn trị.

### 15.3. UPSERT có thể có nhiều loại sự kiện trigger

PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` có thể dẫn đến nhánh INSERT đối với một số hàng và nhánh UPDATE đối với hàng xung đột; các row-level và statement-level triggers có quy tắc kích hoạt theo loại sự kiện và thời điểm.

Không chỉ nhìn câu SQL **bắt đầu bằng INSERT** rồi kết luận tất cả row audit phải có operation INSERT. Với `DO UPDATE`, hàng xung đột được **UPDATE** về mặt thao tác trigger có liên quan. Statement-level trigger firing có những chi tiết riêng của PostgreSQL, kể cả khả năng trigger cấp statement của cả INSERT và UPDATE được kích hoạt trong một UPSERT.

Khi một hàng đi nhánh `DO NOTHING`, không được tự coi nó đã có row-level INSERT thành công. Quy trình kiểm toán nên phân biệt “được thử chèn”, “đã chèn”, “đã cập nhật” và “bị bỏ qua do conflict” theo dữ liệu trả về/logic ứng dụng, không chỉ suy từ tên câu lệnh.

### 15.4. MERGE không bảo đảm một hành động duy nhất cho toàn câu

Ở các DBMS có `MERGE`, một câu lệnh có thể tạo các hành động INSERT/UPDATE/DELETE khác nhau theo nguồn và điều kiện. Ngữ nghĩa kích hoạt trigger, tập hàng và thứ tự xử lý **khác theo engine và phiên bản**.

Ví dụ SQL Server dùng inserted/deleted và có quy tắc riêng với MERGE; PostgreSQL hỗ trợ MERGE từ phiên bản 15 với các điều kiện trigger riêng. Không suy từ SQL Server MERGE sang PostgreSQL MERGE mà không kiểm tra tài liệu phiên bản.

Đối với audit, trước hết xác định **mỗi hàng thực tế đã làm thao tác gì**, sau đó chọn cách ghi log đúng theo contract.

### 15.5. TRUNCATE không là DELETE nhiều hàng

Ví dụ:

~~~sql
TRUNCATE TABLE demo_orders;
~~~

Trong PostgreSQL, statement này có các tính năng, lock, ràng buộc FK, transaction và trigger riêng. Nó không được xử lý như DELETE có OLD TABLE của toàn bộ hàng bị xóa.

**Đừng dùng row-level DELETE trigger làm nguồn audit duy nhất nếu ứng dụng có thể TRUNCATE bảng.** Nếu dữ liệu phải được bảo toàn lịch sử, cần chính sách quyền, migration và các thao tác quản trị phù hợp.

## 16. Audit, nhất quán và transaction

### 16.1. Audit trong cùng transaction

Với trigger PostgreSQL ghi log bằng `INSERT INTO demo_order_row_audit`, nếu DML gốc và transaction thành công, log là một phần của thay đổi database. Nếu sau đó transaction rollback, cả dữ liệu đơn và log SQL thông thường trong transaction **được hoàn tác**.

~~~sql
BEGIN;

UPDATE demo_orders
SET amount = amount + 20
WHERE order_id = 101;

SELECT *
FROM demo_order_row_audit
WHERE order_id = 101;

ROLLBACK;
~~~

Trong transaction ta có thể nhìn thấy log mới; sau ROLLBACK log mới không còn (theo tính chất transactional của bảng audit).

Vì thế audit trigger này phù hợp để ghi lịch sử **các thay đổi đã được commit**, nhưng nó không lưu thành công những lần thử cập nhật đã rollback. Nếu tổ chức cần ghi cả những lần thao tác bị từ chối/rollback, phải có kênh nhật ký khác nằm ngoài giao dịch hoặc hệ quan sát chuyên dụng được thiết kế đúng.

### 16.2. Không gửi side effect bên ngoài mà không có kế hoạch commit

Một AFTER trigger gọi HTTP API, gửi email hoặc đẩy message trực tiếp ra ngoài có thể tạo side effect **không rollback cùng database** nếu transaction sau đó thất bại. Một mô hình thường dùng:

1. Câu DML và trigger/ứng dụng ghi **outbox event** vào một bảng transactional.
2. Commit dữ liệu và outbox cùng transaction.
3. Worker riêng đọc những event đã commit và gửi ra hệ ngoài.
4. Dùng idempotency/event ID để xử lý gửi lại mà không nhân đôi tác động.

Không coi một AFTER trigger là “sự kiện đã commit” chỉ vì nó chạy sau thao tác DML.

### 16.3. Trigger audit không tự bảo đảm dữ liệu nguồn đúng nghiệp vụ

Nếu ứng dụng chạy:

~~~sql
UPDATE demo_orders
SET order_status = 'PAID'
WHERE order_id = 101;
~~~

một trigger có thể ghi log chính xác OLD=NEW, NEW=PAID. Nhưng điều đó **không chứng minh tiền đã được thanh toán**. Trigger chỉ thấy dữ liệu database và quy tắc được cài đặt; các bất biến nghiệp vụ vẫn cần được bảo vệ ở tầng phù hợp.

### 16.4. Có thể ghi log cũ/mới bằng RETURNING hoặc OUTPUT không?

Có, trong các DBMS hỗ trợ cú pháp tương ứng:

- PostgreSQL có `RETURNING` để trả các giá trị sau DML và ở những phiên bản mới có thêm khả năng truy cập hình ảnh old/new theo cú pháp riêng; cần kiểm tra đúng phiên bản.
- SQL Server có `OUTPUT DELETED... INSERTED...` cho giá trị cũ/mới.
- Ứng dụng cũng có thể ghi audit/event trong cùng transaction bằng logic nghiệp vụ.

Không mặc định trigger là cách duy nhất để ghi lịch sử. Trigger phù hợp khi cần bao phủ nhiều đường ghi database, nhưng cũng có chi phí bảo trì, debugging và quyền thực thi.

## 17. Concurrency: OLD/NEW của trigger có bảo vệ lost update không?

### 17.1. OLD/NEW cho biết điều gì đã được sửa

Nếu client A sửa số tiền từ 100 thành 120 và client B sau đó sửa từ 120 thành 140, hai lần UPDATE có thể ghi audit:

~~~text
Event A: OLD 100 → NEW 120
Event B: OLD 120 → NEW 140
~~~

Audit giúp **quan sát lịch sử**, nhưng không tự ngăn B sửa dữ liệu từ một biểu mẫu cũ nếu câu UPDATE không có điều kiện bảo vệ.

### 17.2. Cập nhật có điều kiện vẫn cần trong UPDATE

Ví dụ bảng có cột version:

~~~sql
-- Bảng giả định orders_with_version có version_no.
UPDATE orders_with_version
SET
    amount = :new_amount,
    version_no = version_no + 1
WHERE order_id = :order_id
  AND version_no = :expected_version;
~~~

Trigger có thể ghi OLD/NEW sau khi câu UPDATE thành công, còn **`WHERE version_no = :expected_version`** giúp tránh ghi đè từ phiên bản cũ.

Nếu UPDATE ảnh hưởng 0 hàng, row trigger không có hàng để xử lý. Statement trigger vẫn có thể chạy với transition tables rỗng. Vì vậy **không nên dùng “có row audit hay không” làm tín hiệu duy nhất** để báo API rằng một optimistic update đã thành công; hãy kiểm tra row count hoặc `RETURNING` của thao tác.

### 17.3. Ghi log cho nhiều hàng không đồng nghĩa chia sẻ snapshot toàn transaction

Một transition table mô tả **tập hàng cho một statement**. Nó không tự bao gồm tất cả thay đổi của hai câu UPDATE trong cùng transaction. Nếu cần đối soát xuyên câu lệnh hoặc so với một bảng khác, phải xét transaction isolation và cách lấy snapshot.

### 17.4. Trigger có thể gây lock contention

Một UPDATE ảnh hưởng 10.000 hàng có thể kéo theo:

- 10.000 lượt row trigger;
- Nhiều INSERT vào audit;
- Index updates trên bảng audit;
- Locks/logging trong transaction;
- Tăng thời gian giữ khóa trên bảng nguồn;
- Nếu trigger cũng cập nhật những bảng khác, nguy cơ deadlock/lock order phức tạp hơn.

Statement trigger với `INSERT ... SELECT` có thể giảm overhead lập trình theo hàng ở một số workload, nhưng **không tự luôn nhanh hơn** và có thể cần bộ nhớ/temp space cho transition relations. Đo trên dữ liệu thật và lập kế hoạch bảo trì.

## 18. Bảo mật, đặc quyền và khả năng quan sát

### 18.1. Trigger function chạy với quyền nào?

Trong PostgreSQL, trigger function tuân theo quy tắc quyền thực thi function và có thể khai báo `SECURITY DEFINER` khi cần. Điều này ảnh hưởng khả năng ghi vào bảng audit mà người dùng thường không có quyền INSERT trực tiếp.

Tuy nhiên một function `SECURITY DEFINER` thiếu kiểm soát `search_path` hoặc dynamic SQL có thể dẫn đến rủi ro quyền hạn. Nếu dùng quyền cao để ghi audit:

- Giới hạn schema/tables mà function truy cập;
- Khai báo tên đối tượng đủ rõ;
- Kiểm soát `search_path`;
- Không cấp quyền sửa/xóa audit tùy tiện;
- Đảm bảo các role không thể thay thế function hoặc bảng audit trái phép.

### 18.2. Đừng ghi toàn bộ dữ liệu nhạy cảm chỉ vì có OLD/NEW

`OLD`/`NEW` có thể chứa cột mang thông tin cá nhân, token, secret hoặc dữ liệu tài chính. Không copy `ROW(OLD.*)`/`to_jsonb(OLD)` một cách vô điều kiện vào log mà không có chính sách dữ liệu.

Một audit tốt cần quyết định:

- Cột nào thực sự cần lưu;
- Dữ liệu nhạy cảm có phải ẩn/mã hóa không;
- Ai được đọc bảng log;
- Giữ log bao lâu và xóa theo chính sách nào;
- Có cần gắn `request_id`, actor hoặc trace ID không;
- Có phải phân biệt thay đổi tự động với thay đổi người dùng không.

### 18.3. Không lấy thứ tự audit_id làm thứ tự commit toàn hệ

Audit ID từ sequence/identity có thể được cấp trong các transaction khác nhau. Sequence có thể có khoảng trống, và thứ tự cấp ID không nhất thiết trùng **thứ tự commit** của các transaction đồng thời.

Nếu hệ thống cần thứ tự sự kiện nghiêm ngặt, phải thiết kế cơ chế sắp xếp/đồng bộ phù hợp. `logged_at` cũng có độ chính xác và quy tắc thời gian theo DBMS; không tự dùng nó như một thứ tự tuyệt đối không bao giờ trùng.

### 18.4. Trigger log không tự ghi toàn bộ ngữ cảnh người dùng

Database trigger có thể biết `current_user` hoặc thông tin session, nhưng không tự biết “người dùng cuối nào vừa bấm nút” nếu ứng dụng dùng một database account chung. Nếu cần audit actor:

- Truyền và xác thực actor/request metadata ở tầng ứng dụng;
- Dùng session-local transaction metadata khi có contract rõ;
- Tránh tin một session variable do client không đáng tin tự khai báo;
- Kiểm soát connection pooling để metadata từ request trước không rò sang request sau.

## 19. Những lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Xem OLD/NEW là hai bảng trong row trigger PostgreSQL | Viết sai ngữ nghĩa | ROW trigger có mỗi lần một cặp bản ghi |
| Xem transition table là một bản ghi OLD/NEW duy nhất | Bỏ sót các hàng bị UPDATE hàng loạt | Dùng SQL theo tập và khóa tương quan |
| Nghĩ statement trigger chỉ chạy khi có hàng | Bỏ sót case UPDATE 0 hàng | Statement trigger có thể chạy với tập rỗng |
| Nghĩ row trigger chạy khi UPDATE 0 hàng | Sai số lượt | 0 hàng → 0 lần row trigger |
| Đọc OLD trong INSERT hoặc NEW trong DELETE | Không có hình ảnh phù hợp | Kiểm tra sự kiện và dùng đúng OLD/NEW |
| Tưởng TRUNCATE sẽ chạy DELETE row triggers | Mất audit xóa hàng | Thiết kế quyền/trigger TRUNCATE riêng |
| Ghép OLD TABLE và NEW TABLE bằng thứ tự | Ghép nhầm thực thể | JOIN bằng định danh bất biến |
| JOIN bằng khóa có thể UPDATE | Bỏ sót khi khóa đổi | Dùng stable key hoặc row-level correlation |
| Dùng `<>` với cột nullable | Không phát hiện đổi NULL ↔ giá trị | `IS DISTINCT FROM`/so sánh null-safe |
| Nghĩ `UPDATE OF col` chỉ chạy khi giá trị đổi | Trigger chạy cả với `SET col=col` | So OLD với NEW |
| RETURN NULL trong BEFORE row và tưởng không ảnh hưởng | Hàng có thể bị bỏ qua | RETURN NEW/OLD phù hợp để tiếp tục |
| RETURN NEW trong AFTER và tưởng thay dữ liệu | Return value AFTER bị bỏ qua | Chỉnh NEW ở BEFORE phù hợp |
| UPDATE chính bảng trong AFTER trigger không guard | Có thể đệ quy và ghi log lặp | Dùng BEFORE NEW hoặc thiết kế chống đệ quy |
| Nghĩ AFTER nghĩa là sau COMMIT | Side effects có thể xảy ra trước rollback | Dùng transactional outbox/worker |
| Viết SQL Server trigger đọc inserted vào một biến | Bỏ sót multirow | INSERT ... SELECT từ toàn bộ inserted/deleted |
| Dùng SQL Server `UPDATE(col)` làm changed-value test | Sai khi SET col=col | So inserted/deleted |
| Dùng PostgreSQL OLD TABLE ở MySQL/SQLite | Sai cú pháp | Hai engine có row-level OLD/NEW |
| Coi Oracle REFERENCING OLD AS giống OLD TABLE | Nhầm row pseudorecord với transition set | Hiểu :OLD/:NEW và compound trigger |
| Ghi audit trên mỗi row dù không có đổi giá trị | Log phình to | Điều kiện null-safe theo cột nghiệp vụ |
| Nghĩ audit trigger ngăn lost update | Vẫn có stale update | CAS/version và transaction guards |
| Nghĩ transition relation tồn tại cả transaction | Gộp sai nhiều statements | Transition data theo statement |
| Nghĩ audit_id phản ánh commit order | Sai thứ tự khi concurrent | Cơ chế ordering phù hợp |
| Ghi mọi cột nhạy cảm vào audit | Rủi ro rò rỉ dữ liệu | Data minimization và quyền |
| Dùng trigger cho external API trực tiếp | Side effect không rollback | Outbox/worker sau commit |
| Coi INSERT ... ON CONFLICT DO UPDATE luôn chỉ là INSERT | Sai phân loại row operation | Xem event thực tế và quy tắc trigger |

## 20. Bài tập thực hành kèm đáp án

Các bài dùng `demo_orders` ở mục 3 và các trigger đã tạo ở mục 4–6. Với những bài thay đổi dữ liệu, nên chạy trong `BEGIN ... ROLLBACK`; nếu đã chạy nhiều ví dụ có COMMIT, hãy khôi phục dữ liệu mẫu trước khi đối chiếu kết quả.

### Bài 1 — OLD và NEW khi INSERT

Thêm hàng:

~~~sql
INSERT INTO demo_orders (
    order_id, customer_id, amount, order_status
)
VALUES (105, 4, 90.00, 'NEW');
~~~

Row INSERT trigger có thể đọc gì?

**Đáp án:** `NEW.order_id=105`, `NEW.amount=90`, `NEW.order_status='NEW'`. Không có bản ghi OLD của cùng hàng, vì hàng chưa tồn tại trước INSERT.

### Bài 2 — OLD và NEW khi UPDATE

Ban đầu đơn 101 có `amount=100` và `order_status='NEW'`. UPDATE thành 120/PAID. Old/new là gì?

**Đáp án:**

~~~text
OLD.order_id       = 101
OLD.amount         = 100
OLD.order_status   = NEW

NEW.order_id       = 101
NEW.amount         = 120
NEW.order_status   = PAID
~~~

Dùng các giá trị này để ghi audit, không nhầm OLD là bản ghi của khách hàng hoặc bảng khác.

### Bài 3 — OLD và NEW khi DELETE

Xóa đơn 104. Cần ghi giá trị nào vào log?

**Đáp án:** `OLD.order_id=104`, `OLD.amount=50`, `OLD.order_status='CANCELLED'`. Không có NEW của hàng bị xóa.

### Bài 4 — Row trigger và UPDATE nhiều hàng

~~~sql
UPDATE demo_orders
SET amount = amount + 20
WHERE order_id IN (101, 102);
~~~

Một row-level AFTER UPDATE trigger PostgreSQL chạy mấy lần?

**Đáp án:** **hai lần**, mỗi hàng bị UPDATE có một lượt gọi. Cặp OLD/NEW của 101 là 100→120, của 102 là 250→270.

### Bài 5 — Statement trigger và UPDATE nhiều hàng

Cùng câu UPDATE ở bài 4, một `AFTER UPDATE FOR EACH STATEMENT` trigger PostgreSQL chạy mấy lần?

**Đáp án:** **một lần** cho câu statement đó. Nếu dùng transition tables, `old_rows` và `new_rows` có hai hàng mỗi tập.

### Bài 6 — Statement trigger với UPDATE 0 hàng

~~~sql
UPDATE demo_orders
SET amount = amount + 20
WHERE order_id = 999;
~~~

Row trigger và statement trigger chạy thế nào?

**Đáp án:** row trigger chạy **0 lần**. Statement trigger có thể chạy **1 lần**, với transition tables rỗng; function summary ở mục 6.6 có thể ghi `affected_rows=0`.

### Bài 7 — UPDATE SET col=col

~~~sql
UPDATE demo_orders
SET amount = amount
WHERE order_id = 101;
~~~

Điều này có nhất thiết bỏ qua row UPDATE trigger không?

**Đáp án:** không. Hàng có thể vẫn được xem là hàng của UPDATE statement và row UPDATE trigger được gọi. Nhưng `OLD.amount IS DISTINCT FROM NEW.amount` là FALSE, nên audit có điều kiện “chỉ khi giá khác” có thể không chèn log.

### Bài 8 — Phát hiện đổi giá từ NULL

Giả sử bảng có `note` nullable, từ NULL thành `'Giao hang'`. Vì sao `OLD.note <> NEW.note` không đủ?

**Đáp án:** phép so với NULL cho UNKNOWN/NULL. Với PostgreSQL dùng:

~~~sql
OLD.note IS DISTINCT FROM NEW.note
~~~

kết quả TRUE khi một phía NULL và phía kia là giá trị cụ thể.

### Bài 9 — BEFORE hay AFTER để đặt updated_at?

Muốn tự sửa `NEW.updated_at` của chính hàng trước khi ghi. Trong PostgreSQL chọn trigger nào?

**Đáp án:** **`BEFORE UPDATE FOR EACH ROW`**; đặt `NEW.updated_at := statement_timestamp();` và `RETURN NEW;`. Không dùng AFTER trigger để cố sửa NEW bằng cách trả về bản ghi đã đổi; return value của AFTER trigger bị bỏ qua.

### Bài 10 — RETURN NULL trong BEFORE

Một PostgreSQL BEFORE INSERT row trigger trả `NULL` cho một hàng. Điều gì có thể xảy ra?

**Đáp án:** thao tác INSERT của **hàng đó có thể bị bỏ qua**, không giống `RETURN NULL` của AFTER trigger. Không dùng hành vi này để âm thầm bỏ dữ liệu sai quan trọng.

### Bài 11 — JOIN hai transition tables

Viết phần SELECT audit theo tập khi `order_id` được bảo đảm không đổi.

**Đáp án:**

~~~sql
SELECT
    n.order_id,
    o.amount AS old_amount,
    n.amount AS new_amount
FROM old_rows AS o
JOIN new_rows AS n
  ON n.order_id = o.order_id
WHERE o.amount IS DISTINCT FROM n.amount;
~~~

Đây là SQL bên trong trigger function được gắn bằng `REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows`; chạy ngoài ngữ cảnh trigger sẽ không có hai quan hệ này.

### Bài 12 — Khóa chính thay đổi

Nếu UPDATE đổi `order_id=101` thành `201`, có thể JOIN old_rows và new_rows bằng `order_id` không?

**Đáp án:** không đáng tin. `old_rows.order_id=101` và `new_rows.order_id=201` không khớp. Cần một định danh ổn định khác, row trigger có cặp OLD/NEW sẵn, hoặc thiết kế correlation phù hợp.

### Bài 13 — Đếm tập chuyển tiếp

Viết function ý tưởng đếm số hàng UPDATE trong transition table PostgreSQL `new_rows`.

**Đáp án:**

~~~sql
SELECT COUNT(*)
INTO v_count
FROM new_rows;
~~~

`v_count` là biến đã khai báo trong PL/pgSQL trigger function. Với UPDATE 2 hàng, bằng 2; với UPDATE 0 hàng, bằng 0. Không nhầm số hàng với số cột thay đổi.

### Bài 14 — SQL Server inserted/deleted

Một UPDATE SQL Server đổi `amount` từ 100 sang 120 cho đơn 101. Giá cũ và mới ở đâu?

**Đáp án:** `deleted.amount=100` và `inserted.amount=120` đối với hàng 101. Các logical tables có thể chứa nhiều hàng; dùng JOIN theo khóa và SQL set-based, không giả định một scalar row.

### Bài 15 — Vì sao SQL Server UPDATE(amount) chưa đủ?

Một trigger dùng `IF UPDATE(amount)` để log “giá đã thay đổi”. Câu UPDATE `SET amount=amount` được chạy. Có thể ghi log sai không?

**Đáp án:** có. `UPDATE(amount)` kiểm tra cột xuất hiện trong thao tác cập nhật, không chứng minh giá khác. Cần so `inserted.amount` và `deleted.amount` bằng phép so phù hợp NULL.

### Bài 16 — MySQL OLD/NEW

MySQL BEFORE UPDATE row trigger muốn xác định `amount` có thực sự đổi, kể cả NULL. Viết điều kiện.

**Đáp án MySQL:**

~~~sql
IF NOT (OLD.amount <=> NEW.amount) THEN
    -- Thực hiện khi khác nhau.
END IF;
~~~

`<=>` là null-safe equality của MySQL. Không dùng `IS DISTINCT FROM` PostgreSQL nguyên văn nếu engine/phiên bản MySQL không hỗ trợ cùng cú pháp.

### Bài 17 — SQLite BEFORE/AFTER

Một người viết `NEW.amount := 100` trong SQLite trigger và mong nó sửa bản ghi. Điều này có đúng không?

**Đáp án:** không theo cú pháp đó. SQLite không có phép gán NEW kiểu PL/pgSQL. Cần thiết kế bằng SQL/cơ chế phù hợp SQLite và tránh tự UPDATE lặp trigger không kiểm soát.

### Bài 18 — Oracle :OLD/:NEW

Trong Oracle row trigger, cú pháp đọc giá trị trước UPDATE là gì? Có thể dùng `:OLD.amount` trong trigger cấp statement như một hàng duy nhất không?

**Đáp án:** row trigger dùng `:OLD.amount`/`:NEW.amount`. Trigger cấp statement không có cặp row pseudorecord tương ứng một hàng; nếu muốn thu thập nhiều hàng, cần cơ chế phù hợp như compound trigger.

### Bài 19 — AFTER có phải sau COMMIT không?

Một AFTER UPDATE PostgreSQL trigger ghi audit, nhưng transaction chính sau đó ROLLBACK. Audit có còn không?

**Đáp án:** audit INSERT trong cùng transaction thường bị rollback cùng dữ liệu nguồn. AFTER nghĩa là sau sự kiện DML trong ngữ cảnh trigger, **không đồng nghĩa sau COMMIT**.

### Bài 20 — External side effects

Một AFTER trigger gửi HTTP request trực tiếp rồi transaction rollback. Điều gì có thể sai?

**Đáp án:** HTTP request có thể đã thành công dù dữ liệu DB bị rollback. Dùng transactional outbox và worker sau commit, với xử lý idempotency.

### Bài 21 — UPSERT kích hoạt loại trigger nào?

Câu `INSERT ... ON CONFLICT DO UPDATE` gặp SKU trùng và thực hiện UPDATE. Có được tự gắn operation=INSERT cho audit hàng đó chỉ vì câu SQL bắt đầu bằng INSERT không?

**Đáp án:** không. Hàng đi nhánh UPDATE cần được nhìn nhận theo sự kiện trigger thích hợp; statement-level firing còn có chi tiết riêng. Audit phải dựa trên operation thực và quy tắc DBMS.

### Bài 22 — Khi nào nên dùng transition table?

Một câu UPDATE sửa 50.000 hàng, cần ghi một bảng audit từ tất cả OLD/NEW, trong PostgreSQL. Row-level hay statement transition table là lựa chọn nên đánh giá?

**Đáp án:** có thể **đánh giá statement trigger với transition tables** và một câu `INSERT ... SELECT` theo tập, nếu bài toán phù hợp và có khóa tương quan ổn định. Row trigger vẫn có thể đúng và đôi khi cần khi phải xử lý từng cặp OLD/NEW; quyết định dựa trên ngữ nghĩa và benchmark chứ không coi một dạng luôn nhanh hơn.

### Bài 23 — Tập hàng có thứ tự không?

Một người lấy `ROW_NUMBER() OVER (ORDER BY amount)` trên OLD và NEW rồi ghép theo số thứ tự. Điều gì sai?

**Đáp án:** giá trị amount có thể đổi làm thứ tự hai tập khác nhau, và các transition relations không cam kết tương quan theo vị trí. Phải JOIN theo khóa ổn định hoặc dùng row-level cặp OLD/NEW.

### Bài 24 — TRUNCATE và DELETE

Nếu ứng dụng dùng TRUNCATE, có thể tin row-level DELETE audit sẽ ghi toàn bộ hàng bị xóa không?

**Đáp án:** không. TRUNCATE có cơ chế trigger riêng; trong PostgreSQL, row DELETE trigger không tự chạy cho từng hàng TRUNCATE. Muốn bảo vệ lịch sử, cần chính sách quyền hoặc xử lý riêng.

### Bài 25 — Lost update và audit

Một bảng có AFTER UPDATE audit trigger nhưng API ghi bằng `UPDATE ... WHERE id=?` không có version guard. Điều đó có ngăn lost update không?

**Đáp án:** không. Trigger giúp ghi lại **những thay đổi đã xảy ra**, không tự từ chối cập nhật từ bản dữ liệu cũ. Cần optimistic locking/version guard, transaction hoặc chiến lược concurrency phù hợp.

### Bài 26 — Thiết kế audit chuẩn cho thay đổi tiền/trạng thái

Hãy đề xuất thiết kế PostgreSQL để lưu OLD/NEW cho `amount`/`order_status` khi cập nhật nhiều hàng, không log khi cả hai cột không đổi, và không làm mất lịch sử khi xóa đơn.

**Gợi ý đáp án:**

1. Tạo bảng audit độc lập, **không phụ thuộc FK trực tiếp vào hàng đích có thể bị xóa**.
2. Với thao tác nhỏ hoặc cần chính xác từng cặp, dùng AFTER UPDATE FOR EACH ROW, so `IS DISTINCT FROM`, ghi OLD/NEW.
3. Với thay đổi nhiều hàng, có thể dùng AFTER UPDATE FOR EACH STATEMENT + OLD TABLE/NEW TABLE, JOIN bằng **định danh bất biến**, lọc giá trị khác nhau.
4. Với INSERT/DELETE, dùng NEW/OLD đúng sự kiện.
5. Đảm bảo ghi audit transactional, quyền tối thiểu, không tự gửi side effect ngoài DB trước commit.
6. Nếu cần actor/request ID, truyền metadata có kiểm soát và quản lý connection pooling.
7. Kiểm tra số hàng 0/1/N, các đường ghi DML khác nhau, UPSERT, DELETE và TRUNCATE theo chính sách.
8. Nếu cần ngăn ghi đè từ dữ liệu cũ, thêm CAS/version vào câu UPDATE, không chỉ dựa vào audit trigger.

## 21. Checklist triển khai

Trước khi đưa trigger sử dụng OLD/NEW hoặc transition relations vào database, hãy trả lời:

1. **Sự kiện:** INSERT, UPDATE, DELETE hay TRUNCATE? Có UPSERT/MERGE không?
2. **Timing:** BEFORE, AFTER hay INSTEAD OF? Dữ liệu NEW đang đề xuất hay đã được xử lý theo timing?
3. **Level:** Theo hàng hay theo statement? DBMS hỗ trợ những level nào?
4. **Phạm vi:** Một cặp OLD/NEW hay một tập 0/1/N hàng?
5. **Hàng 0:** Statement trigger có chạy khi DML không khớp hàng không?
6. **Dữ liệu khả dụng:** INSERT có NEW; DELETE có OLD; UPDATE có cả hai theo sự kiện.
7. **Đổi giá trị thực:** Đang so OLD/NEW hay chỉ nhìn cột nằm trong SET?
8. **NULL:** Điều kiện changed-value có null-safe không?
9. **Khóa ghép:** Transition tables có một định danh không bị UPDATE không?
10. **Thứ tự:** Có vô tình dựa vào thứ tự hàng hoặc audit sequence không?
11. **Giá trị trả về:** BEFORE row trả NEW/OLD đúng cách? AFTER return có bị bỏ qua?
12. **Đệ quy:** Trigger có UPDATE lại cùng bảng và tự kích hoạt không?
13. **Transaction:** Audit có rollback cùng dữ liệu không? Có side effects ngoài DB?
14. **Concurrency:** Trigger có được nhầm là cơ chế chống lost update không?
15. **Bulk operation:** Có tương thích với INSERT SELECT, UPDATE nhiều hàng, DELETE nhiều hàng không?
16. **Quyền:** Function owner/definer, quyền bảng audit, search_path có an toàn không?
17. **Dữ liệu nhạy cảm:** Có log cột không cần thiết hoặc tiết lộ thông tin cá nhân không?
18. **Hiệu năng:** Audit index/insert/transition materialization có tăng chi phí ghi/khóa không?
19. **Khả chuyển:** PostgreSQL, SQL Server, MySQL, Oracle, SQLite có đúng cú pháp tương ứng không?
20. **Vận hành:** Có cơ chế quản lý migration, version, monitoring và phục hồi trigger lỗi không?

## 22. Tổng kết

Một trigger có thể quan sát dữ liệu **trước** và **sau** thao tác, nhưng phải hiểu đúng **mức chi tiết** và **thời điểm thực thi**:

- Trong PostgreSQL `FOR EACH ROW`, `OLD`/`NEW` là hai **bản ghi của một hàng**; INSERT chỉ có NEW, DELETE chỉ có OLD, UPDATE có cả hai.
- Trong PostgreSQL `AFTER ... FOR EACH STATEMENT` ở ngữ cảnh hỗ trợ, `REFERENCING OLD TABLE`/`NEW TABLE` tạo **tập hàng chuyển tiếp** cho cả statement, có thể ghi audit bằng một `INSERT ... SELECT`.
- Trong SQL Server, `deleted`/`inserted` là **các logical tables 0/1/N hàng**, không phải hai biến scalar; SQL Server trigger phải được viết theo tập.
- MySQL và SQLite chủ yếu dùng **row-level OLD/NEW**, không có transition tables statement-level giống PostgreSQL. Oracle sử dụng `:OLD`/`:NEW` cho row triggers và có compound triggers cho những bài toán phối hợp nhiều thời điểm.
- `BEFORE` trong các engine hỗ trợ có thể dùng để điều chỉnh `NEW`; `AFTER` thích hợp cho audit nhưng **không phải sự kiện sau COMMIT**.
- `IS DISTINCT FROM` hoặc biểu thức null-safe tương ứng giúp tách **hàng bị UPDATE** khỏi **hàng thực sự đổi giá trị nghiệp vụ**.
- Khi ghép hai tập OLD/NEW, cần **khóa tương quan ổn định**: không ghép bằng vị trí hay thứ tự giả định.

**Nguyên tắc cần nhớ:** *OLD/NEW trả lời “hàng này đã đổi từ gì sang gì?”, còn transition tables/inserted/deleted trả lời “toàn bộ những hàng trong statement đã đổi như thế nào?”*. Hãy chọn đúng phạm vi, so sánh NULL an toàn, quản lý transaction và tránh coi trigger audit là biện pháp thay thế cho kiểm soát cập nhật đồng thời.
