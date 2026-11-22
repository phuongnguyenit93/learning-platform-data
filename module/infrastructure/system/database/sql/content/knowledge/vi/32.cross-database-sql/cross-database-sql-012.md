# Cú pháp routine, trigger và xử lý ngoại lệ

Khi logic nghiệp vụ cần được thực thi gần dữ liệu, database cung cấp nhiều cơ chế: **stored procedure**, **function**, **trigger** và **xử lý ngoại lệ**. Chúng có thể gom nhiều thao tác SQL thành một đơn vị, tái sử dụng quy tắc, tự động phản ứng khi INSERT/UPDATE/DELETE, hoặc báo lỗi có cấu trúc khi một điều kiện không thỏa mãn.

Các cơ chế này không giống nhau giữa các hệ quản trị. PostgreSQL dùng PL/pgSQL và trigger functions; MySQL có stored procedures/functions, handlers và trigger theo từng hàng; SQL Server dùng T-SQL procedures, functions và trigger theo statement; Oracle có PL/SQL, packages, exception handlers và nhiều loại trigger; SQLite có trigger nhưng không có stored procedure native theo mô hình server truyền thống.

**Điều quan trọng là chọn đúng nơi đặt logic và hiểu transaction/error semantics của DBMS.** Một trigger có thể bảo vệ invariant dữ liệu nhưng cũng có thể tạo side effect khó nhìn thấy. Một procedure có thể gom nhiều thao tác vào một API database nhưng không tự bảo đảm transaction nếu code commit sai. Một exception handler có thể chuyển lỗi thành thông báo dễ hiểu, nhưng nếu nuốt lỗi hoặc tiếp tục sau trạng thái transaction không hợp lệ, dữ liệu có thể sai.

> **Nguyên tắc:** dùng constraint cho quy tắc dữ liệu đơn giản và bất biến; dùng routine cho thao tác nhiều bước có hợp đồng rõ; dùng trigger cho phản ứng dữ liệu thực sự cần tự động áp dụng với mọi writer; dùng exception handling để phân loại, rollback và truyền lỗi đúng cách. Luôn xác định ai sở hữu transaction, quyền thực thi và side effects.

Bài học thuộc **Database SQL → SQL đa hệ quản trị**. Nội dung so sánh PostgreSQL PL/pgSQL, MySQL stored programs, SQL Server T-SQL, Oracle PL/SQL và SQLite. Các phần chính gồm procedure/function, tham số và kết quả, trigger timing và granularity, OLD/NEW hoặc inserted/deleted, exception/error handling, transaction semantics, recursion, security, testing, migration và 30 bài tập.

## 1. Phân biệt constraint, routine, function và trigger

Các cơ chế database thường được dùng cho những mục tiêu khác nhau:

| Cơ chế | Vai trò điển hình | Ví dụ |
| --- | --- | --- |
| PRIMARY KEY / UNIQUE | Bảo đảm định danh duy nhất | Email không trùng |
| FOREIGN KEY | Bảo đảm quan hệ tham chiếu | Order phải có customer |
| CHECK | Bảo đảm điều kiện trên hàng | Amount không âm |
| NOT NULL | Bắt buộc có giá trị | Created_at phải có |
| Stored procedure | Thực hiện một thao tác nghiệp vụ nhiều bước | Tạo đơn và các dòng đơn |
| Function | Tính hoặc trả về một giá trị/tập dữ liệu theo contract | Tính thuế, trả summary |
| Trigger | Phản ứng tự động với DML | Ghi audit khi đổi trạng thái |
| Exception handler | Bắt, chuyển tiếp hoặc xử lý lỗi | Báo mã nghiệp vụ khi thiếu hàng |

Nếu quy tắc có thể biểu diễn bằng `UNIQUE`, `FOREIGN KEY`, `CHECK` hoặc `NOT NULL`, nên ưu tiên constraint. Constraint được DBMS áp dụng ở mọi đường ghi phù hợp, kể cả ứng dụng, batch job và thao tác SQL thủ công. Nếu chỉ kiểm ở một service, một writer khác có thể bỏ qua quy tắc.

### 1.1. Stored procedure

Procedure là một routine được gọi để thực hiện hành động. Nó có thể:
- Nhận tham số IN/OUT/INOUT tùy DBMS.
- Chạy nhiều câu SQL.
- Thực hiện kiểm tra và cập nhật dữ liệu.
- Trả result set hoặc output parameters theo dialect.
- Dùng transaction theo quy tắc của engine.

Ví dụ khái niệm: `create_order(customer_id, items)` kiểm tra customer, tạo order, tạo order lines và ghi trạng thái.

### 1.2. Function

Function thường trả một giá trị, một hàng hoặc một tập hàng. Nó có thể được dùng trong biểu thức SQL tùy DBMS và loại function.

Ví dụ:
- `calculate_tax(amount, region)`.
- `normalize_phone(value)`.
- `get_customer_summary(customer_id)`.

Function có thể bị giới hạn về side effects, transaction control hoặc câu lệnh được phép chạy. Không giả định function ở mọi DBMS có quyền và khả năng giống procedure.

### 1.3. Trigger

Trigger được DBMS gọi tự động khi một sự kiện xảy ra trên một bảng, view hoặc đối tượng được hỗ trợ.

Trigger có thể chạy:
- Trước hoặc sau một DML event.
- Theo từng hàng hoặc một lần cho cả statement.
- Thay thế thao tác trên view trong một số DBMS.
- Theo sự kiện DDL hoặc database event ở một số hệ quản trị.

Trigger hữu ích khi một quy tắc cần áp dụng cho **mọi writer**. Nhưng nó cũng khiến hành vi ghi dữ liệu khó nhìn thấy nếu logic quá nhiều hoặc trigger gọi trigger khác.

### 1.4. Exception handling

Exception/error handling định nghĩa cách routine phản ứng khi:
- Không tìm thấy hàng.
- Có nhiều hàng trong khi mong một.
- Vi phạm UNIQUE/FK/CHECK.
- Timeout, deadlock hoặc lỗi kết nối.
- Điều kiện nghiệp vụ không thỏa.
- Lỗi nội bộ không dự kiến.

Một handler tốt không chỉ in thông báo. Nó cần quyết định lỗi có thể phục hồi không, transaction đang ở trạng thái nào, có cần rollback hay không và lỗi có phải được truyền về caller.

## 2. Bộ dữ liệu thực hành

Các ví dụ SQL chính dùng PostgreSQL và bảng TEMP. Chạy trên cùng session; nếu dùng JDBC/ORM connection khác, tạo lại các bảng trong connection/schema lab tương ứng.

```sql
CREATE TEMP TABLE demo_routine_customers (
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY,
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'BLOCKED')),
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email)
);

CREATE TEMP TABLE demo_routine_orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED')),
    total NUMERIC(12,2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_routine_customers (tenant_id, customer_id)
);

CREATE TEMP TABLE demo_routine_order_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT
);

INSERT INTO demo_routine_customers (tenant_id, email)
VALUES
    (10, 'an@example.com'),
    (10, 'binh@example.com'),
    (20, 'an@example.com');

INSERT INTO demo_routine_orders
    (tenant_id, customer_id, status, total)
VALUES
    (10, 1, 'PENDING', 100.00),
    (10, 1, 'PAID', 50.00),
    (10, 2, 'PENDING', 75.00);
```

Kiểm dữ liệu:

```sql
SELECT * FROM demo_routine_customers ORDER BY tenant_id, customer_id;
SELECT * FROM demo_routine_orders ORDER BY tenant_id, order_id;
```

Bộ dữ liệu có hai tenant và hai customer cùng email ở tenant khác nhau. Điều này giúp minh họa vì sao routine/trigger phải giữ điều kiện tenant trong mọi thao tác.

## 3. Stored procedure và function khác nhau thế nào?

Sự khác biệt phụ thuộc DBMS, nhưng có một cách phân biệt hữu ích:

- Procedure được gọi như một hành động riêng, thường bằng `CALL` hoặc `EXEC`.
- Function được gọi trong expression hoặc query, thường trả giá trị/tập dữ liệu.
- Function có thể bị giới hạn transaction control hoặc side effects nhiều hơn procedure.
- Cách trả result set, output parameter và xử lý lỗi khác theo engine.

| Hệ quản trị | Procedure | Function |
| --- | --- | --- |
| PostgreSQL | `CREATE PROCEDURE`, gọi bằng `CALL` | `CREATE FUNCTION`, dùng trong SQL expression/query |
| MySQL | `CREATE PROCEDURE`, `CALL` | `CREATE FUNCTION`, trả một giá trị |
| SQL Server | `CREATE PROCEDURE`, `EXEC` | Scalar/table-valued function |
| Oracle | PL/SQL procedure | PL/SQL function |
| SQLite | Không có stored procedure native | Không có stored function lưu trong DB theo mô hình server; ứng dụng có thể đăng ký UDF |

Không chuyển cú pháp routine giữa các hệ quản trị chỉ bằng cách đổi dấu tham số. Cần chuyển cả **hợp đồng trả kết quả, quyền, transaction và lỗi**.

## 4. PostgreSQL: PL/pgSQL function

PostgreSQL dùng `CREATE FUNCTION` để định nghĩa function. Ví dụ function tính tổng đơn đã thanh toán của một customer:

```sql
CREATE OR REPLACE FUNCTION demo_paid_total(
    p_tenant_id INTEGER,
    p_customer_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_total NUMERIC(12,2);
BEGIN
    SELECT COALESCE(SUM(total), 0)
    INTO v_total
    FROM demo_routine_orders
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id
      AND status = 'PAID';

    RETURN v_total;
END;
$$;
```

Gọi function:

```sql
SELECT demo_paid_total(10, 1);
```

Function trả một scalar `NUMERIC`.

### 4.1. DECLARE, BEGIN và RETURN

Một function PL/pgSQL thường có cấu trúc:
- `DECLARE`: khai báo biến cục bộ (có thể bỏ nếu không cần).
- `BEGIN ... END`: khối thực thi.
- `RETURN`: trả giá trị theo kiểu khai báo ở `RETURNS`.

Các câu SQL trong PL/pgSQL có thể dùng biến tham số trực tiếp. `SELECT ... INTO variable` gán kết quả vào biến PL/pgSQL; đây là cú pháp khác `SELECT ... INTO new_table` của một số DBMS.

### 4.2. Function trả TABLE hoặc SETOF

Nếu muốn trả nhiều hàng, PostgreSQL hỗ trợ `RETURNS TABLE`:

```sql
CREATE OR REPLACE FUNCTION demo_customer_orders(
    p_tenant_id INTEGER,
    p_customer_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    order_status TEXT,
    order_total NUMERIC
)
LANGUAGE sql
AS $$
    SELECT o.order_id, o.status, o.total
    FROM demo_routine_orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.customer_id = p_customer_id
    ORDER BY o.order_id
$$;
```

Gọi:

```sql
SELECT *
FROM demo_customer_orders(10, 1);
```

Function trả một tập hàng, có thể dùng trong `FROM`. PostgreSQL còn có `RETURNS SETOF some_type` và `RETURN QUERY` trong PL/pgSQL.

### 4.3. SQL function và PL/pgSQL function

Nếu chỉ cần một câu SQL, `LANGUAGE sql` thường ngắn gọn. Nếu cần biến, nhánh điều kiện, vòng lặp hoặc exception block, PL/pgSQL phù hợp hơn.

Đừng chọn PL/pgSQL chỉ vì nó có vẻ “mạnh hơn”. Một SQL function đơn giản có thể dễ tối ưu và đọc hơn.

## 5. PostgreSQL: procedure và CALL

Procedure được định nghĩa bằng `CREATE PROCEDURE`, gọi bằng `CALL`. Ví dụ cập nhật trạng thái customer:

```sql
CREATE OR REPLACE PROCEDURE demo_block_customer(
    p_tenant_id INTEGER,
    p_customer_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE demo_routine_customers
    SET status = 'BLOCKED'
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            USING ERRCODE = 'P0002',
                  MESSAGE = 'Customer not found';
    END IF;
END;
$$;
```

Gọi:

```sql
CALL demo_block_customer(10, 1);
```

`FOUND` là trạng thái của câu lệnh PL/pgSQL gần nhất có ý nghĩa đặt cờ này; vì vậy hãy kiểm tra ngay sau `UPDATE`, trước khi chạy một câu khác có thể thay đổi trạng thái.

### 5.1. Procedure có thể có IN/OUT parameters

PostgreSQL hỗ trợ các mode tham số như `IN`, `OUT`, `INOUT` theo cú pháp function/procedure. Khi có output parameters, `CALL` có thể trả hàng kết quả chứa output values. Hãy xem contract của caller và driver.

### 5.2. Transaction control trong PostgreSQL procedure

PostgreSQL procedure có khả năng `COMMIT`/`ROLLBACK` trong một số ngữ cảnh gọi, khác function. Nhưng transaction control chỉ được phép trong điều kiện cụ thể, chẳng hạn `CALL` ở top-level hoặc chuỗi CALL phù hợp; gọi bên trong một transaction block tường minh có thể không cho phép procedure commit. Exception block cũng tạo subtransaction và có giới hạn với transaction control.

**Không thêm COMMIT vào procedure theo thói quen.** Thông thường application/service sở hữu transaction; procedure chỉ thực hiện thao tác và để caller quyết định commit/rollback. Nếu procedure thực sự quản lý transaction, phải thiết kế rõ cách gọi và kiểm tra đúng ngữ cảnh.

### 5.3. Procedure không tự động là một transaction riêng

Nhiều câu lệnh trong procedure được thực thi trong transaction của caller. Nếu một câu lỗi và exception không được xử lý, transaction có thể chuyển sang trạng thái aborted cho đến rollback. Đừng nghĩ việc đóng gói SQL vào procedure tự động bảo đảm commit từng bước.

## 6. PostgreSQL: tham số, biến và kết quả

Một function có thể dùng tham số đầu vào trong SQL:

```sql
CREATE OR REPLACE FUNCTION demo_order_count(
    p_tenant_id INTEGER,
    p_customer_id BIGINT
)
RETURNS BIGINT
LANGUAGE sql
AS $$
    SELECT COUNT(*)
    FROM demo_routine_orders
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id
$$;
```

Trong PL/pgSQL:
- Biến tham số có thể dùng trực tiếp.
- `SELECT ... INTO` lấy giá trị vào biến.
- `RETURN` trả scalar/record theo contract.
- `RETURN NEXT`/`RETURN QUERY` hỗ trợ set-returning function.

Không nối giá trị tham số thành SQL text. Nếu thực sự cần dynamic SQL, dùng `EXECUTE ... USING` cho values và `format('%I', ...)` cho identifiers đã allowlist.

### 6.1. SELECT INTO phải trả đúng số hàng theo ý định

Trong PL/pgSQL, `SELECT ... INTO variable` mặc định lấy một hàng đầu tiên nếu có nhiều hàng; nếu cần kiểm soát, dùng `INTO STRICT` để yêu cầu đúng một hàng:

```sql
DECLARE
    v_email TEXT;
BEGIN
    SELECT email
    INTO STRICT v_email
    FROM demo_routine_customers
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id;
END;
```

`INTO STRICT` có thể phát `NO_DATA_FOUND` nếu không có hàng và `TOO_MANY_ROWS` nếu có nhiều hàng. Khóa chính/unique và điều kiện đúng vẫn rất quan trọng.

### 6.2. Không dùng SELECT INTO như assignment mơ hồ

PostgreSQL PL/pgSQL `SELECT ... INTO variable` gán vào biến. Trong SQL thuần PostgreSQL, `SELECT ... INTO new_table` là cú pháp tạo bảng từ query trong một số ngữ cảnh. Cần phân biệt PL/pgSQL block và SQL statement bên ngoài.

## 7. PostgreSQL: xử lý ngoại lệ trong PL/pgSQL

PL/pgSQL có block `EXCEPTION`:

```sql
CREATE OR REPLACE FUNCTION demo_safe_insert_customer(
    p_tenant_id INTEGER,
    p_email TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_id BIGINT;
BEGIN
    INSERT INTO demo_routine_customers (tenant_id, email)
    VALUES (p_tenant_id, p_email)
    RETURNING customer_id INTO v_customer_id;

    RETURN v_customer_id;

EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION
            USING ERRCODE = 'P0001',
                  MESSAGE = 'Customer email already exists in this tenant';
END;
$$;
```

Gọi:

```sql
SELECT demo_safe_insert_customer(10, 'new@example.com');
```

Nếu email đã tồn tại trong tenant, function phát lỗi có thông điệp nghiệp vụ.

### 7.1. Exception condition và SQLSTATE

Có thể bắt theo condition name như:
- `unique_violation`
- `foreign_key_violation`
- `check_violation`
- `not_null_violation`
- `no_data_found`
- `too_many_rows`
- `serialization_failure`
- `deadlock_detected`

Hoặc bắt theo SQLSTATE. Mã lỗi giúp application phân loại ổn định hơn so với so sánh chuỗi message. Không bắt mọi lỗi rồi biến thành một thông báo “invalid input” chung nếu caller cần biết retry hay không.

### 7.2. RAISE NOTICE, WARNING và EXCEPTION

PostgreSQL `RAISE` có mức độ:
- `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING`: phát thông tin theo mức.
- `EXCEPTION`: ném lỗi, mặc định hủy statement hiện tại và truyền lỗi lên caller.

Ví dụ:

```sql
RAISE NOTICE 'Processing customer %', p_customer_id;
```

Không dùng NOTICE thay logging/audit bảo mật chính thức. Nội dung notice có thể được driver gửi về client hoặc log theo cấu hình.

### 7.3. GET STACKED DIAGNOSTICS

Trong exception handler, có thể đọc thông tin lỗi:

```sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
BEGIN
    INSERT INTO demo_routine_customers (tenant_id, email)
    VALUES (10, 'an@example.com');

EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS
        v_state = RETURNED_SQLSTATE,
        v_message = MESSAGE_TEXT,
        v_detail = PG_EXCEPTION_DETAIL;

    RAISE NOTICE 'state=%, message=%, detail=%',
        v_state, v_message, v_detail;
    RAISE;
END;
$$;
```

Ví dụ cố tình gây UNIQUE violation để minh họa. `RAISE;` ném lại lỗi gốc sau khi ghi nhận. Trong production, không log dữ liệu nhạy cảm trong detail/hint.

### 7.4. Exception block và rollback cục bộ

Một PL/pgSQL block có `EXCEPTION` được thực thi với subtransaction semantics. Khi lỗi xảy ra trong block, các thay đổi database trong block đó được rollback trước khi handler chạy; thay đổi ở bên ngoài block có thể còn. Điều này cho phép thử một thao tác rồi xử lý lỗi, nhưng không thay thế transaction design tổng thể.

Ví dụ:

```sql
DO $$
BEGIN
    BEGIN
        INSERT INTO demo_routine_customers (tenant_id, email)
        VALUES (10, 'an@example.com');
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate customer ignored by this block';
    END;

    RAISE NOTICE 'Outer block continues';
END;
$$;
```

Nếu handler chỉ ghi NOTICE và không re-raise, caller có thể không biết insert thất bại. Chỉ nuốt lỗi khi đó là **hành vi nghiệp vụ có chủ ý**.

### 7.5. Không bắt OTHERS rồi im lặng

Mẫu nguy hiểm:

```sql
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
```

Nó làm mọi lỗi — kể cả deadlock, permission denied, lỗi schema hoặc bug — biến thành kết quả NULL. Caller khó phân biệt “không có dữ liệu” với “hệ thống hỏng”. Hãy bắt lỗi cụ thể có thể xử lý, còn lỗi không dự kiến thì truyền lại.

## 8. PostgreSQL: trigger và trigger function

Trong PostgreSQL, trigger gọi một **trigger function** được định nghĩa `RETURNS trigger`. Trigger function có thể truy cập biến đặc biệt:
- `NEW`: hàng mới trong INSERT/UPDATE.
- `OLD`: hàng cũ trong UPDATE/DELETE.
- `TG_OP`: `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE`.
- `TG_TABLE_NAME`, `TG_TABLE_SCHEMA`.
- `TG_WHEN`, `TG_LEVEL`, `TG_ARGV` và metadata liên quan.

Ví dụ audit trạng thái order:

```sql
CREATE OR REPLACE FUNCTION demo_audit_order_status()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO demo_routine_order_audit (
            tenant_id,
            order_id,
            old_status,
            new_status,
            changed_by
        )
        VALUES (
            NEW.tenant_id,
            NEW.order_id,
            OLD.status,
            NEW.status,
            current_user
        );
    END IF;

    RETURN NEW;
END;
$$;
```

Tạo trigger:

```sql
CREATE TRIGGER demo_order_status_audit
AFTER UPDATE OF status ON demo_routine_orders
FOR EACH ROW
EXECUTE FUNCTION demo_audit_order_status();
```

Khi update:

```sql
UPDATE demo_routine_orders
SET status = 'PAID'
WHERE tenant_id = 10
  AND order_id = 1;
```

Trigger tự ghi một hàng audit nếu status thực sự thay đổi.

### 8.1. BEFORE và AFTER

- `BEFORE`: chạy trước khi thay đổi hàng được áp dụng; row-level trigger có thể sửa và trả `NEW`, hoặc trả `NULL` để bỏ qua hàng trong một số thao tác.
- `AFTER`: chạy sau thao tác hàng/statement theo trigger timing; thay đổi `NEW` không còn ý nghĩa để sửa hàng mục tiêu.
- `INSTEAD OF`: thường dùng với view trong PostgreSQL để thay thao tác gốc bằng logic trigger phù hợp.

Chọn timing theo yêu cầu. Nếu chỉ chuẩn hóa một giá trị trước khi lưu, `BEFORE` thường hợp lý. Nếu ghi audit dựa trên thay đổi đã thực hiện, `AFTER` thường dễ diễn đạt.

### 8.2. Row-level và statement-level

`FOR EACH ROW`: chạy một lần cho mỗi hàng bị tác động.

`FOR EACH STATEMENT`: chạy một lần cho statement, dù statement tác động 0, 1 hay nhiều hàng.

Ví dụ một UPDATE 10.000 orders:
- Row trigger có thể chạy 10.000 lần.
- Statement trigger chạy một lần.

Đây là khác biệt lớn về chi phí và cách viết logic. Không giả định trigger luôn chỉ chạy một lần vì ứng dụng chỉ gửi một câu UPDATE.

### 8.3. BEFORE trigger trả NEW hoặc NULL

Ví dụ chuẩn hóa tên:

```sql
CREATE OR REPLACE FUNCTION demo_normalize_customer_email()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.email := lower(trim(NEW.email));
    RETURN NEW;
END;
$$;

CREATE TRIGGER demo_customer_email_normalize
BEFORE INSERT OR UPDATE OF email
ON demo_routine_customers
FOR EACH ROW
EXECUTE FUNCTION demo_normalize_customer_email();
```

`NEW` là bản ghi mới có thể sửa trong BEFORE row trigger. Trigger trả `NEW` để tiếp tục ghi hàng đã chuẩn hóa.

Trả `NULL` trong BEFORE row trigger sẽ bỏ qua thao tác trên hàng đó. Dùng cẩn thận vì nó có thể khiến số hàng thực tế bị ghi ít hơn số hàng ứng dụng gửi.

### 8.4. AFTER trigger return value

Với AFTER trigger, giá trị return của trigger function bị bỏ qua. Có thể `RETURN NULL` theo convention hoặc trả NEW/OLD; điều quan trọng là side effect. Không dựa vào `RETURN NEW` của AFTER trigger để sửa hàng mục tiêu.

## 9. PostgreSQL: trigger statement và transition tables

PostgreSQL hỗ trợ transition relations cho một số AFTER triggers theo statement, giúp nhìn tập hàng cũ/mới của toàn statement.

Ví dụ audit nhiều hàng UPDATE:

```sql
CREATE TEMP TABLE demo_order_bulk_audit (
    order_id BIGINT,
    old_status TEXT,
    new_status TEXT,
    changed_at TIMESTAMPTZ DEFAULT now()
);

CREATE OR REPLACE FUNCTION demo_audit_order_bulk()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO demo_order_bulk_audit (
        order_id, old_status, new_status
    )
    SELECT
        n.order_id,
        o.status,
        n.status
    FROM old_rows AS o
    JOIN new_rows AS n
      ON n.tenant_id = o.tenant_id
     AND n.order_id = o.order_id
    WHERE o.status IS DISTINCT FROM n.status;

    RETURN NULL;
END;
$$;
```

Trigger dùng transition tables:

```sql
CREATE TRIGGER demo_order_bulk_audit
AFTER UPDATE ON demo_routine_orders
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION demo_audit_order_bulk();
```

Trong trigger function, `old_rows` và `new_rows` là các relation chuyển tiếp được khai báo trong trigger. Cú pháp và giới hạn transition tables phụ thuộc event/timing/trigger form; kiểm tài liệu PostgreSQL cho tổ hợp cụ thể. Không phải mọi trigger đều có thể kết hợp transition relations với mọi loại event/column list.

### 9.1. Vì sao statement trigger hữu ích?

Nếu một UPDATE thay đổi hàng nghìn orders, có thể INSERT audit theo tập hợp từ transition tables thay vì chạy một câu INSERT riêng cho mỗi hàng. Điều này có thể giảm overhead PL/pgSQL và round trips nội bộ.

### 9.2. Transition table không phải bảng vĩnh viễn

Tên relation chỉ tồn tại trong ngữ cảnh trigger statement. Không lưu tên `new_rows` vào SQL ngoài trigger rồi kỳ vọng dùng được ở session khác.

## 10. MySQL: stored procedure

MySQL stored procedure có tham số `IN`, `OUT`, `INOUT`. Ví dụ:

```sql
DELIMITER //

CREATE PROCEDURE demo_get_customer_status(
    IN p_tenant_id INT,
    IN p_customer_id BIGINT,
    OUT p_status VARCHAR(20)
)
BEGIN
    SELECT status
    INTO p_status
    FROM customers
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id;
END//

DELIMITER ;
```

Gọi từ MySQL client:

```sql
CALL demo_get_customer_status(10, 1, @customer_status);
SELECT @customer_status;
```

`DELIMITER` là lệnh của một số client như mysql CLI để đổi ký tự kết thúc khi định nghĩa routine có dấu `;` bên trong. Nó **không phải câu lệnh SQL được gửi tới server**; driver JDBC thường gửi phần `CREATE PROCEDURE ... BEGIN ... END` theo cách riêng, không gửi `DELIMITER`.

### 10.1. IN, OUT và INOUT

- `IN`: caller truyền giá trị vào.
- `OUT`: procedure gán giá trị để caller đọc.
- `INOUT`: vừa nhận giá trị đầu vào vừa trả giá trị cập nhật.

Output parameter hữu ích cho một scalar result. Nếu cần nhiều hàng, procedure MySQL có thể trả result set bằng SELECT trong procedure.

### 10.2. Procedure có thể điều khiển transaction

MySQL stored procedure có thể dùng `START TRANSACTION`, `COMMIT`, `ROLLBACK` theo quy tắc engine và ngữ cảnh. Nhưng cần xác định transaction do procedure hay caller sở hữu. Nếu procedure commit giữa chừng, caller không thể rollback toàn bộ thao tác như một transaction duy nhất.

Stored function và trigger có giới hạn transaction control khác procedure; không chuyển nguyên code procedure vào function/trigger.

## 11. MySQL: stored function

MySQL function khai báo `RETURNS` một kiểu và phải trả giá trị:

```sql
DELIMITER //

CREATE FUNCTION demo_tax_amount(
    p_amount DECIMAL(12,2),
    p_rate DECIMAL(6,4)
)
RETURNS DECIMAL(12,2)
DETERMINISTIC
NO SQL
BEGIN
    RETURN ROUND(p_amount * p_rate, 2);
END//

DELIMITER ;
```

Dùng trong query:

```sql
SELECT demo_tax_amount(100.00, 0.1000);
```

### 11.1. DETERMINISTIC và data access declarations

Các đặc tính như `DETERMINISTIC`, `NO SQL`, `READS SQL DATA` hoặc `MODIFIES SQL DATA` mô tả hành vi theo contract MySQL. Khai báo sai có thể ảnh hưởng optimizer/replication hoặc quản trị. Không đánh dấu DETERMINISTIC nếu kết quả phụ thuộc thời gian, session, bảng mutable hoặc trạng thái ngoài.

### 11.2. Function khác procedure

Function MySQL trả một giá trị và có thể dùng trong expression theo quy tắc DBMS. Nó không được dùng như một procedure trả nhiều result sets. Stored function còn có các giới hạn về câu lệnh, dynamic SQL và transaction; hãy kiểm đúng phiên bản thay vì giả định function có thể làm mọi điều procedure làm.

## 12. MySQL: DECLARE HANDLER, SIGNAL và RESIGNAL

MySQL dùng `DECLARE ... HANDLER` để xử lý condition:

```sql
DELIMITER //

CREATE PROCEDURE demo_insert_customer(
    IN p_tenant_id INT,
    IN p_email VARCHAR(320)
)
BEGIN
    DECLARE EXIT HANDLER FOR 1062
    BEGIN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Customer email already exists';
    END;

    INSERT INTO customers (tenant_id, email)
    VALUES (p_tenant_id, p_email);
END//

DELIMITER ;
```

Mã `1062` là lỗi duplicate key phổ biến của MySQL. Có thể bắt theo SQLSTATE hoặc condition name phù hợp.

### 12.1. CONTINUE và EXIT handler

- `CONTINUE`: sau handler, chương trình tiếp tục ở statement tiếp theo của block theo quy tắc MySQL.
- `EXIT`: kết thúc block nơi handler được khai báo.
- Handler có thể áp dụng cho SQLWARNING, NOT FOUND, SQLEXCEPTION hoặc condition cụ thể.

Một cursor loop thường dùng `NOT FOUND` để đánh dấu hết dữ liệu:

```sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_id BIGINT;

DECLARE cur CURSOR FOR
    SELECT customer_id FROM customers;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

Trong MySQL, thứ tự khai báo trong block có quy tắc: variables/conditions trước cursor, handlers sau cursor; tất cả DECLARE phải đứng đầu block trước câu lệnh thực thi. Đừng đặt DECLARE sau INSERT/SELECT.

### 12.2. SIGNAL

`SIGNAL SQLSTATE '45000'` phát lỗi do ứng dụng routine định nghĩa. Có thể đặt `MESSAGE_TEXT`, `MYSQL_ERRNO` và thông tin condition phù hợp.

Dùng SQLSTATE lớp `45` cho user-defined exception theo quy ước MySQL. Không giả mạo mã lỗi hệ thống tùy tiện.

### 12.3. RESIGNAL

Trong handler, `RESIGNAL` ném lại lỗi đang được xử lý, có thể giữ nguyên hoặc thay đổi một số thuộc tính. Nếu chỉ ghi nhận lỗi rồi muốn caller vẫn biết thao tác thất bại, cần RESIGNAL thay vì im lặng tiếp tục.

### 12.4. Handler không tự rollback toàn transaction

`EXIT HANDLER` chỉ định luồng điều khiển. Nó không có nghĩa transaction tự động rollback theo ý muốn nghiệp vụ. Nếu handler chạy `ROLLBACK`, cần biết routine có sở hữu transaction không. Tránh rollback transaction do caller quản lý mà không có hợp đồng rõ.

## 13. MySQL: trigger

MySQL trigger là trigger **FOR EACH ROW**; không có statement-level trigger tương đương PostgreSQL/SQL Server trong mô hình trigger bảng thông thường.

Ví dụ BEFORE INSERT chuẩn hóa email:

```sql
DELIMITER //

CREATE TRIGGER demo_customer_email_before_insert
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
END//

DELIMITER ;
```

`NEW` đại diện giá trị hàng sắp được ghi. Trong BEFORE UPDATE có thể đọc `OLD` và sửa `NEW`. Trong DELETE chỉ có `OLD`.

### 13.1. OLD và NEW

| Event | OLD | NEW |
| --- | --- | --- |
| INSERT | Không có hàng cũ | Hàng sắp thêm |
| UPDATE | Hàng trước update | Hàng sau update |
| DELETE | Hàng bị xóa | Không có hàng mới |

Trong MySQL, trigger row-level xử lý từng hàng của statement. UPDATE 10.000 hàng có thể kích hoạt trigger 10.000 lần.

### 13.2. AFTER INSERT audit

```sql
DELIMITER //

CREATE TRIGGER demo_customer_audit_after_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_audit (
        tenant_id, customer_id, action_name, changed_at
    )
    VALUES (
        NEW.tenant_id, NEW.customer_id, 'INSERT', CURRENT_TIMESTAMP
    );
END//

DELIMITER ;
```

Bảng `customer_audit` là bảng audit giả định. Nếu bảng chính dùng transactional engine như InnoDB, thay đổi trong trigger thường thuộc transaction của statement; nếu statement rollback, audit insert cũng rollback. Các engine không transactional có semantics khác, nên cần kiểm storage engine.

### 13.3. Không thể sửa NEW trong AFTER trigger

Trong MySQL, `NEW.column` có thể được gán trong BEFORE trigger; AFTER trigger không dùng để thay đổi hàng đã ghi. Nếu cần chuẩn hóa field trước khi lưu, dùng BEFORE hoặc application/constraint thích hợp.

### 13.4. Trigger không thể tự START TRANSACTION/COMMIT

MySQL trigger không được dùng transaction-control statements như `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`. Trigger chạy trong ngữ cảnh statement/transaction kích hoạt nó. Không thiết kế trigger như một worker tự commit độc lập.

### 13.5. Hạn chế sửa lại bảng đang được statement dùng

MySQL có giới hạn khi trigger/stored function cố sửa bảng đã được statement gọi trigger đang sử dụng. Ví dụ trigger trên `orders` không thể tùy tiện UPDATE lại chính `orders` trong một số ngữ cảnh; DBMS có thể báo lỗi. Thiết kế tránh vòng lặp tự sửa bảng và dùng BEFORE trigger để gán `NEW` khi phù hợp.

## 14. SQL Server: stored procedure T-SQL

SQL Server procedure dùng `CREATE PROCEDURE`/`CREATE OR ALTER PROCEDURE`, gọi bằng `EXEC`:

```sql
CREATE OR ALTER PROCEDURE dbo.DemoGetCustomerStatus
    @TenantId INT,
    @CustomerId BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT status
    FROM dbo.Customers
    WHERE tenant_id = @TenantId
      AND customer_id = @CustomerId;
END;
```

Gọi:

```sql
EXEC dbo.DemoGetCustomerStatus
    @TenantId = 10,
    @CustomerId = 1;
```

`SET NOCOUNT ON` giảm các thông báo row count cho từng statement, hữu ích trong procedure có nhiều thao tác. Nó không thay đổi kết quả query.

### 14.1. OUTPUT parameter

```sql
CREATE OR ALTER PROCEDURE dbo.DemoGetCustomerStatusOut
    @TenantId INT,
    @CustomerId BIGINT,
    @Status NVARCHAR(20) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT @Status = status
    FROM dbo.Customers
    WHERE tenant_id = @TenantId
      AND customer_id = @CustomerId;
END;
```

Gọi:

```sql
DECLARE @status NVARCHAR(20);

EXEC dbo.DemoGetCustomerStatusOut
    @TenantId = 10,
    @CustomerId = 1,
    @Status = @status OUTPUT;

SELECT @status;
```

Nếu SELECT không trả hàng, output variable có thể giữ giá trị cũ/NULL tùy cách khởi tạo và assignment. Hãy khởi tạo biến và xác định contract “không tìm thấy”.

### 14.2. RETURN status khác OUTPUT data

SQL Server procedure có `RETURN integer` cho mã trạng thái điều khiển; nó không phải cơ chế trả một hàng dữ liệu tổng quát. Dùng result set hoặc OUTPUT parameters cho dữ liệu, RETURN code cho trạng thái theo contract.

### 14.3. Procedure có thể trả nhiều result sets

Một procedure có thể chạy nhiều SELECT; client driver có thể phải duyệt nhiều result sets/update counts. Đừng thiết kế API mà caller không biết thứ tự và schema của từng result set.

## 15. SQL Server: function

SQL Server có nhiều loại function:
- Scalar-valued function trả một giá trị.
- Inline table-valued function trả một query table expression.
- Multi-statement table-valued function xây tập kết quả qua biến bảng.

Scalar function:

```sql
CREATE OR ALTER FUNCTION dbo.DemoTaxAmount
(
    @Amount DECIMAL(12,2),
    @Rate DECIMAL(6,4)
)
RETURNS DECIMAL(12,2)
AS
BEGIN
    RETURN ROUND(@Amount * @Rate, 2);
END;
```

Dùng:

```sql
SELECT dbo.DemoTaxAmount(100.00, 0.1000);
```

Inline table-valued function:

```sql
CREATE OR ALTER FUNCTION dbo.DemoCustomerOrders
(
    @TenantId INT,
    @CustomerId BIGINT
)
RETURNS TABLE
AS
RETURN
(
    SELECT order_id, status, total
    FROM dbo.Orders
    WHERE tenant_id = @TenantId
      AND customer_id = @CustomerId
);
```

Dùng:

```sql
SELECT *
FROM dbo.DemoCustomerOrders(10, 1);
```

### 15.1. Function có giới hạn side effects

T-SQL user-defined functions bị giới hạn so với stored procedures. Không dùng function như procedure để thực hiện transaction control hoặc thay đổi dữ liệu tùy ý. Các giới hạn cụ thể phụ thuộc loại function và phiên bản. Nếu cần thao tác ghi nhiều bước, procedure thường là abstraction phù hợp hơn.

### 15.2. Scalar UDF và hiệu năng

Scalar UDF gọi theo từng hàng có thể tạo overhead đáng kể ở một số phiên bản/plan. SQL Server có scalar UDF inlining trong những điều kiện nhất định ở các phiên bản hỗ trợ, nhưng không phải function nào cũng inline. Kiểm actual plan và workload thay vì giả định function luôn được tối ưu thành biểu thức.

## 16. SQL Server: TRY...CATCH, THROW và transaction state

Ví dụ procedure xử lý lỗi:

```sql
CREATE OR ALTER PROCEDURE dbo.DemoCreateCustomer
    @TenantId INT,
    @Email NVARCHAR(320)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO dbo.Customers (tenant_id, email)
        VALUES (@TenantId, @Email);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;

        THROW;
    END CATCH
END;
```

Đây là mẫu minh họa khi procedure chủ động sở hữu transaction. Trong hệ thống có transaction bên ngoài, procedure không nên rollback tùy tiện toàn bộ transaction của caller. Cần quy định rõ ownership/nesting và dùng savepoint khi phù hợp.

### 16.1. TRY/CATCH không bắt mọi loại lỗi

`TRY...CATCH` bắt nhiều runtime errors trong cùng execution scope, nhưng không bắt mọi lỗi compile/parse hoặc lỗi khiến session bị ngắt. Lỗi severity cao có thể kết thúc connection. Không coi CATCH là một hàng rào bao phủ tuyệt đối.

### 16.2. XACT_STATE()

- `1`: transaction đang hoạt động và có thể commit.
- `-1`: transaction không thể commit; chỉ có thể đọc/rollback toàn bộ.
- `0`: không có transaction hoạt động.

`@@TRANCOUNT` cho biết nesting count nhưng không đủ để biết transaction còn commit được không. Trong CATCH, dùng `XACT_STATE()` khi cần quyết định rollback.

### 16.3. THROW và RAISERROR

`THROW` là cách hiện đại để ném lỗi hoặc rethrow lỗi đang bắt, giữ thông tin gốc khi dùng không đối số trong CATCH. `RAISERROR` là cơ chế cũ hơn và có behavior khác, vẫn tồn tại vì compatibility. Không dùng `PRINT` làm error handling vì nó không tạo lỗi có cấu trúc cho caller.

### 16.4. XACT_ABORT

`SET XACT_ABORT ON` làm nhiều runtime errors kết thúc và rollback transaction theo semantics SQL Server. Nó hữu ích trong nhiều procedure ghi dữ liệu, nhưng cần hiểu ảnh hưởng với distributed transaction, lỗi và TRY/CATCH. Không thêm mù quáng vào mọi routine.

## 17. SQL Server: trigger theo statement với inserted/deleted

SQL Server DML trigger là trigger **theo statement**, không phải row-level trigger. Một câu UPDATE ảnh hưởng 1.000 hàng sẽ gọi trigger một lần; các hàng cũ/mới có trong pseudo tables:
- `deleted`: phiên bản trước của hàng với UPDATE, hoặc hàng bị DELETE.
- `inserted`: hàng mới với INSERT, hoặc phiên bản mới với UPDATE.

Ví dụ audit nhiều hàng:

```sql
CREATE OR ALTER TRIGGER dbo.trg_OrderStatusAudit
ON dbo.Orders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.OrderAudit (
        tenant_id, order_id, old_status, new_status, changed_at
    )
    SELECT
        i.tenant_id,
        i.order_id,
        d.status,
        i.status,
        SYSUTCDATETIME()
    FROM inserted AS i
    JOIN deleted AS d
      ON d.tenant_id = i.tenant_id
     AND d.order_id = i.order_id
    WHERE d.status <> i.status
       OR (d.status IS NULL AND i.status IS NOT NULL)
       OR (d.status IS NOT NULL AND i.status IS NULL);
END;
```

Trigger xử lý toàn bộ tập `inserted`/`deleted`, không được giả định chỉ có một hàng.

### 17.1. Lỗi thường gặp: SELECT một hàng từ inserted

Mẫu sai:

```sql
DECLARE @order_id BIGINT;
SELECT @order_id = order_id FROM inserted;
```

Nếu statement update nhiều hàng, biến chỉ giữ một giá trị nào đó trong tập theo quy tắc assignment, không xử lý đầy đủ mọi hàng. Dùng INSERT...SELECT/JOIN set-based với inserted/deleted.

### 17.2. AFTER và INSTEAD OF

- `AFTER`: chạy sau thao tác DML và kiểm tra constraint phù hợp.
- `INSTEAD OF`: thay thế thao tác INSERT/UPDATE/DELETE trên bảng/view trong những trường hợp được hỗ trợ; trigger phải tự thực hiện logic ghi mong muốn.

Một view có thể dùng INSTEAD OF trigger để ánh xạ thao tác vào nhiều bảng nền. Cần bảo đảm trigger xử lý đầy đủ nhiều hàng và concurrency.

### 17.3. Trigger có thể kích hoạt trigger khác

Một DML trong trigger có thể kích hoạt trigger trên bảng khác. SQL Server có cấu hình nested/recursive triggers. Tránh chuỗi trigger khó theo dõi, vòng lặp và side effects không được ghi trong hợp đồng.

### 17.4. UPDATE(column) không chứng minh giá trị đã đổi

Hàm `UPDATE(status)` trong trigger cho biết cột có được nhắm tới trong statement, không chứng minh giá trị mới khác giá trị cũ. So sánh `inserted.status` với `deleted.status` theo semantics NULL-safe khi cần audit thay đổi thực tế.

## 18. Oracle: PL/SQL procedure và function

Oracle dùng PL/SQL. Procedure:

```sql
CREATE OR REPLACE PROCEDURE demo_block_customer (
    p_tenant_id IN NUMBER,
    p_customer_id IN NUMBER
)
AS
BEGIN
    UPDATE customers
    SET status = 'BLOCKED'
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Customer not found');
    END IF;
END;
/
```

Gọi:

```sql
BEGIN
    demo_block_customer(10, 1);
END;
/
```

Function:

```sql
CREATE OR REPLACE FUNCTION demo_paid_total (
    p_tenant_id IN NUMBER,
    p_customer_id IN NUMBER
)
RETURN NUMBER
AS
    v_total NUMBER(12,2);
BEGIN
    SELECT NVL(SUM(total), 0)
    INTO v_total
    FROM orders
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id
      AND status = 'PAID';

    RETURN v_total;
END;
/
```

Dùng:

```sql
SELECT demo_paid_total(10, 1)
FROM dual;
```

### 18.1. IN, OUT và IN OUT

PL/SQL parameters có mode:
- `IN`: chỉ đọc giá trị caller truyền vào.
- `OUT`: procedure/function gán giá trị để trả.
- `IN OUT`: nhận giá trị ban đầu và trả giá trị đã sửa.

Khai báo type, precision và mode phải phù hợp contract. Nếu caller dùng JDBC, cách bind OUT parameters phụ thuộc Oracle driver và kiểu dữ liệu.

### 18.2. Package

Oracle package gom procedure, function, cursor/type và biến liên quan vào một namespace:
- Package specification công bố API.
- Package body chứa implementation.

Package giúp tổ chức API database lớn và che giấu chi tiết triển khai. Package state có thể tồn tại theo session, vì vậy cần cẩn thận khi connection pool tái sử dụng session và khi state vô tình rò giữa request.

## 19. Oracle: exception handling

PL/SQL có section `EXCEPTION`:

```sql
CREATE OR REPLACE PROCEDURE demo_find_customer (
    p_tenant_id IN NUMBER,
    p_customer_id IN NUMBER
)
AS
    v_email VARCHAR2(320);
BEGIN
    SELECT email
    INTO v_email
    FROM customers
    WHERE tenant_id = p_tenant_id
      AND customer_id = p_customer_id;

    DBMS_OUTPUT.PUT_LINE(v_email);

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20002, 'Customer not found');

    WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(-20003, 'Expected one customer');

    WHEN OTHERS THEN
        RAISE;
END;
/
```

### 19.1. Các exception thường gặp

- `NO_DATA_FOUND`: SELECT INTO không trả hàng.
- `TOO_MANY_ROWS`: SELECT INTO trả nhiều hơn một hàng.
- `DUP_VAL_ON_INDEX`: vi phạm unique/index.
- `ZERO_DIVIDE`: chia cho 0.
- `VALUE_ERROR`: lỗi chuyển/độ dài/giá trị.
- `OTHERS`: các lỗi khác.

`WHEN OTHERS THEN RAISE;` truyền lại lỗi gốc. Nếu chỉ log rồi không raise, caller có thể tưởng routine thành công.

### 19.2. RAISE_APPLICATION_ERROR

Oracle cho phép mã lỗi ứng dụng trong phạm vi `-20000` đến `-20999` qua `RAISE_APPLICATION_ERROR`. Dùng mã ổn định để client/service phân loại lỗi nghiệp vụ. Không gửi stack trace hoặc thông tin nội bộ nhạy cảm cho caller.

### 19.3. SQLCODE và SQLERRM

Trong handler, `SQLCODE` và `SQLERRM` cung cấp mã/thông điệp lỗi hiện tại. Có thể ghi log nội bộ, sau đó raise lại. Tránh ghi payload nhạy cảm hoặc thông tin credential vào audit/error table.

### 19.4. Exception không tự rollback toàn transaction

PL/SQL exception handler xử lý luồng lỗi; transaction vẫn cần được caller quyết định commit/rollback. Nếu exception truyền ra host, statement/transaction behavior còn phụ thuộc caller, driver và transaction scope. Không giả định bắt exception là rollback tất cả thao tác trước đó.

## 20. Oracle: trigger

Oracle hỗ trợ trigger ở nhiều mức:
- Statement-level.
- Row-level (`FOR EACH ROW`).
- BEFORE/AFTER.
- INSTEAD OF trên view.
- Compound trigger trong các trường hợp phù hợp.
- Một số trigger theo DDL/database events.

Ví dụ row-level audit:

```sql
CREATE OR REPLACE TRIGGER demo_order_status_audit
AFTER UPDATE OF status ON orders
FOR EACH ROW
WHEN (OLD.status <> NEW.status)
BEGIN
    INSERT INTO order_audit (
        tenant_id,
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.tenant_id,
        :NEW.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
```

Trong trigger Oracle:
- `:OLD` và `:NEW` là tham chiếu tới giá trị hàng cũ/mới trong row-level trigger.
- `:NEW` có thể được sửa trong BEFORE row trigger theo quy tắc.
- `:OLD` không thể gán.
- Statement-level trigger không dùng row pseudorecord theo cách row-level dùng.

### 20.1. Mutating table error

Oracle có hạn chế khi row-level trigger truy vấn hoặc sửa lại chính bảng đang bị statement thay đổi trong một số tình huống; điều này thường được gọi là **mutating table error** (`ORA-04091`). Lý do liên quan tính nhất quán khi statement chưa hoàn tất.

Các giải pháp tùy bài toán:
- Dùng statement-level logic khi đủ.
- Compound trigger lưu thông tin trong row section rồi xử lý sau statement.
- Dùng constraint hoặc thiết kế schema khác.
- Chuyển logic về procedure/application nếu phù hợp.

Không tìm cách né lỗi bằng cách tạo side effect ngoài transaction mà làm mất tính đúng.

### 20.2. Compound trigger

Compound trigger cho phép nhiều timing points của cùng một trigger chia sẻ trạng thái PL/SQL trong thời gian statement. Nó hữu ích khi cần thu thập row keys trong AFTER EACH ROW rồi xử lý tập hợp ở AFTER STATEMENT, tránh truy vấn bảng đang mutating trong row trigger.

Cú pháp và timing section phụ thuộc trigger event; cần kiểm đúng phiên bản Oracle. Đây là công cụ nâng cao, không cần dùng cho audit một hàng đơn giản.

### 20.3. Trigger không nên tự COMMIT

Trigger Oracle thông thường chạy trong transaction của statement kích hoạt nó. Không commit transaction caller từ trigger. `PRAGMA AUTONOMOUS_TRANSACTION` cho phép một routine/trigger dùng transaction độc lập trong trường hợp được hỗ trợ, nhưng rất dễ tạo audit ghi nhận một thay đổi mà transaction chính sau đó rollback. Chỉ dùng autonomous transaction khi nghiệp vụ thật sự muốn log độc lập và hiểu hậu quả.

## 21. SQLite: trigger có, stored procedure native không có

SQLite không cung cấp stored procedures lưu trong database theo mô hình PostgreSQL/MySQL/SQL Server/Oracle. Ứng dụng có thể:
- Đăng ký user-defined functions (UDF) trên từng connection.
- Dùng prepared statements.
- Tạo trigger SQL.
- Đặt logic nghiệp vụ nhiều bước ở application transaction/service.

Ví dụ trigger audit:

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL
);

CREATE TABLE customer_audit (
    audit_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    action_name TEXT NOT NULL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER customer_after_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_audit (customer_id, action_name)
    VALUES (NEW.customer_id, 'INSERT');
END;
```

SQLite trigger là **row-level**. Một INSERT nhiều hàng có thể kích hoạt trigger cho từng hàng.

### 21.1. OLD và NEW trong SQLite

| Event | OLD | NEW |
| --- | --- | --- |
| INSERT | Không có | Có |
| UPDATE | Có | Có |
| DELETE | Có | Không có |

Trigger body có thể chứa các câu SQL phù hợp theo grammar SQLite. Không có statement-level trigger tương đương PostgreSQL/SQL Server.

### 21.2. RAISE trong trigger

SQLite hỗ trợ `RAISE()` trong trigger để điều khiển lỗi:

```sql
CREATE TRIGGER prevent_negative_amount
BEFORE INSERT ON payments
FOR EACH ROW
WHEN NEW.amount < 0
BEGIN
    SELECT RAISE(ABORT, 'amount must be non-negative');
END;
```

Các hành vi thường gặp:
- `RAISE(ABORT, message)`: hủy statement hiện tại với constraint error.
- `RAISE(FAIL, message)`: báo lỗi nhưng có semantics khác ABORT về các thay đổi trước đó trong statement.
- `RAISE(ROLLBACK, message)`: rollback transaction hiện tại.
- `RAISE(IGNORE)`: bỏ phần còn lại của trigger/statement theo quy tắc SQLite mà không phát lỗi thông thường.

Chọn hành vi rất cẩn thận; `FAIL` và `ABORT` không đồng nghĩa. Kiểm tra version SQLite vì khả năng truyền expression làm message có thay đổi theo phiên bản.

### 21.3. User-defined function không phải stored function

Ứng dụng Python/C/JavaScript có thể đăng ký function với connection SQLite. Function đó thường thuộc runtime/connection, không phải một routine được lưu độc lập trong file database và tự có mặt ở mọi client. Mỗi connection cần đăng ký UDF theo API driver.

## 22. Trigger timing và granularity: so sánh

| DBMS | Row-level | Statement-level | Before/After | INSTEAD OF |
| --- | --- | --- | --- | --- |
| PostgreSQL | Có | Có | Có | Có, đặc biệt view |
| MySQL | Có | Không có trigger statement-level bảng tương đương | Có | Không theo mô hình trigger SQL Server |
| SQL Server | Không theo row; trigger theo statement với inserted/deleted sets | Có | AFTER/INSTEAD OF | Có |
| Oracle | Có | Có | Có | Có trên view |
| SQLite | Có | Không | BEFORE/AFTER | Không có cơ chế tổng quát tương đương |

Bảng tóm tắt mô hình phổ biến, không thay thế tài liệu version-specific. Một số DBMS còn có trigger DDL/database events hoặc loại trigger chuyên biệt.

## 23. Trigger recursion, cascade và side effects

Một trigger có thể gây DML lên bảng khác, kích hoạt trigger khác. Một trigger có thể cập nhật lại bảng gốc, gây recursion tùy DBMS/cấu hình. FK cascade cũng có thể kích hoạt các thao tác liên quan theo engine semantics.

### 23.1. Sơ đồ side effect

```text
UPDATE orders
    |
    v
order status trigger
    |
    +--> INSERT order_audit
    |        |
    |        v
    |    audit trigger?
    |
    +--> UPDATE customer_stats
             |
             v
         customer_stats trigger
```

Nếu chuỗi side effect không được kiểm soát, một thao tác đơn giản có thể kích hoạt nhiều câu SQL và trigger lồng nhau.

### 23.2. Tránh trigger tự kích hoạt vô hạn

Các biện pháp:
- Không UPDATE lại cùng bảng nếu có thể sửa NEW trong BEFORE trigger.
- Chỉ ghi khi giá trị thực sự thay đổi.
- Đặt điều kiện rõ trong trigger.
- Tránh hai trigger cập nhật qua lại hai bảng.
- Hiểu recursion/nested trigger settings của DBMS.
- Có test cho multi-row và cascade.
- Giữ logic trigger nhỏ, dễ quan sát.

Không dựa vào biến session/global “đang chạy trigger” làm khóa logic nếu connection pool hoặc nested invocation có thể làm trạng thái rò rỉ.

### 23.3. Trigger order

Nhiều trigger cùng timing/event có thể có thứ tự thực thi phụ thuộc DBMS và cấu hình. Không dựa vào thứ tự tạo trigger nếu engine không cam kết. Nếu hai logic cần thứ tự, gộp vào một routine/trigger có thứ tự rõ hoặc dùng tính năng ordering được DBMS hỗ trợ và test.

### 23.4. Audit trigger và transaction

Nếu audit row được ghi trong cùng transaction:
- DML chính commit thì audit commit.
- DML chính rollback thì audit rollback.

Đây thường là điều mong muốn cho audit thay đổi dữ liệu. Nếu audit cần tồn tại ngay cả khi transaction thất bại, đó là yêu cầu khác và cần thiết kế logging độc lập; không dùng autonomous transaction một cách vô thức.

### 23.5. Không gọi dịch vụ ngoài từ trigger

Trigger thường nên thực hiện thay đổi database có transaction semantics rõ. Gọi HTTP, gửi email hoặc publish message trực tiếp từ trigger có thể tạo tình huống:
- Message gửi thành công nhưng transaction rollback.
- Transaction commit nhưng network call thất bại.
- Trigger giữ lock trong lúc chờ dịch vụ.
- Retry gây gửi trùng.

Một mẫu phù hợp hơn là **transactional outbox**: trigger/procedure hoặc application ghi một outbox row trong cùng transaction; worker riêng publish sau commit, có retry/idempotency.

## 24. Transaction ownership và xử lý lỗi

Trước khi viết routine, xác định:
- Caller mở transaction hay routine mở?
- Routine có được phép commit?
- Khi một bước lỗi, rollback phần nào?
- Handler có rethrow không?
- Retry lỗi nào?
- Có thể gọi routine trong transaction lớn hơn không?

### 24.1. Application-owned transaction

Một pattern phổ biến:
1. Service bắt đầu transaction.
2. Gọi procedure hoặc chạy nhiều câu SQL.
3. Nếu thành công, commit.
4. Nếu lỗi, rollback và truyền lỗi.
5. Chỉ gửi response success sau commit.

Procedure không tự commit giúp caller có thể kết hợp nhiều thao tác trong một transaction lớn.

### 24.2. Routine-owned transaction

Nếu procedure tự quản lý transaction, contract phải nói rõ:
- Caller không bọc transaction theo cách xung đột.
- Procedure commit ở điểm nào.
- Lỗi giữa các bước rollback đến đâu.
- Caller xử lý kết quả partial như thế nào.

Khả năng nested transaction khác giữa DBMS. Ví dụ SQL Server `BEGIN TRAN` lồng nhau chủ yếu tăng `@@TRANCOUNT`, không tạo independent nested transactions; savepoint có semantics riêng. PostgreSQL savepoint/subtransaction và Oracle/MySQL transaction rules cũng khác. Không giả định mọi `BEGIN` lồng nhau là transaction độc lập.

### 24.3. Savepoint cho phần có thể phục hồi

Một thao tác có thể thất bại riêng mà caller vẫn muốn tiếp tục các việc khác. Có thể dùng SAVEPOINT nếu DBMS/driver và transaction state hỗ trợ:

```sql
BEGIN;

INSERT INTO demo_routine_customers (tenant_id, email)
VALUES (10, 'new-one@example.com');

SAVEPOINT optional_step;

-- Một thao tác tùy chọn có thể lỗi.
INSERT INTO demo_routine_customers (tenant_id, email)
VALUES (10, 'an@example.com');

-- Nếu lỗi và application xử lý được:
ROLLBACK TO SAVEPOINT optional_step;

COMMIT;
```

Đây là kịch bản minh họa cần điều khiển lỗi từ client/PL block phù hợp; khi một statement lỗi ở PostgreSQL, transaction ở trạng thái aborted cho tới rollback to savepoint. Không chạy nguyên chuỗi trong một script client không có xử lý lỗi rồi mong các câu sau tiếp tục.

### 24.4. Không retry mọi exception

Có thể retry một số lỗi tạm thời như serialization failure hoặc deadlock sau khi rollback toàn transaction và chạy lại toàn bộ đơn vị công việc. Không retry:
- Validation error.
- Unique conflict mang ý nghĩa nghiệp vụ.
- Permission denied.
- Syntax error.
- Data conversion error.

Retry phải có giới hạn, backoff và idempotency. Không retry chỉ một statement ở giữa transaction đã aborted.

## 25. Error contract giữa database và application

Một routine tốt cần quy định lỗi có thể xảy ra và ý nghĩa của chúng.

| Nhóm lỗi | Ví dụ | Cách xử lý thường gặp |
| --- | --- | --- |
| Validation/business | Amount âm, trạng thái không hợp lệ | Trả lỗi client/4xx |
| Not found | Không có customer | 404 hoặc business result theo contract |
| Conflict | Email trùng, version không khớp | 409 hoặc xử lý idempotent |
| Authorization | Không có quyền tenant/object | 403/404 theo chính sách |
| Transient concurrency | Deadlock, serialization failure | Rollback rồi retry có giới hạn |
| Resource timeout | Statement timeout | Hủy, cleanup, báo retryable tùy context |
| Infrastructure | Connection lost | Không giả định commit outcome |
| Internal bug | Unexpected exception | Log có correlation ID, trả lỗi chung |

### 25.1. Không expose SQL error nguyên văn cho người dùng

Error message có thể chứa:
- Tên bảng/cột nội bộ.
- SQL fragment.
- Giá trị dữ liệu.
- Schema names.
- Chi tiết constraint.
- Stack hoặc thông tin môi trường.

Log nội bộ có kiểm soát; response bên ngoài nên trả error code/message phù hợp, không phơi chi tiết nội bộ.

### 25.2. Giữ SQLSTATE/vendor code

Application nên phân loại bằng SQLSTATE/vendor code khi driver cung cấp, không chỉ so sánh message text vốn có thể thay đổi theo locale/version. Ví dụ PostgreSQL unique violation SQLSTATE `23505`; các DBMS khác có mã riêng.

### 25.3. Truyền lại lỗi sau khi ghi log

Handler ghi log rồi `RAISE`/`RESIGNAL`/`THROW`/`RAISE;` theo dialect nếu caller cần biết thao tác thất bại. Đừng đổi mọi lỗi thành một giá trị mặc định như 0 hoặc NULL.

## 26. Security: quyền thực thi routine

Stored routine và trigger có thể chạy với quyền khác caller. Điều này vừa hữu ích vừa nguy hiểm.

### 26.1. PostgreSQL SECURITY INVOKER/DEFINER

Function mặc định chạy theo quyền invoker; `SECURITY DEFINER` chạy theo quyền owner. Nếu dùng DEFINER:
- Cố định/kiểm soát `search_path`.
- Schema-qualify object nhạy cảm.
- Giới hạn quyền owner.
- Kiểm input và authorization.
- Tránh dynamic SQL từ input.
- Chỉ GRANT EXECUTE cho role cần.

`SECURITY DEFINER` có thể tạo đường leo thang quyền nếu object resolution/search_path hoặc dynamic SQL không an toàn.

### 26.2. MySQL SQL SECURITY

MySQL routine/view có `SQL SECURITY DEFINER` hoặc `INVOKER` theo đối tượng và cú pháp hỗ trợ. Definer account phải được quản lý cẩn thận; quyền của routine có thể rộng hơn caller. Không cấp EXECUTE rộng cho routine làm việc nhạy cảm nếu không có kiểm tra quyền.

### 26.3. SQL Server EXECUTE AS và module signing

SQL Server hỗ trợ `EXECUTE AS` và cơ chế module signing/certificate để cấp quyền thực thi cụ thể. Cần hiểu ownership chaining, execution context và quyền caller. Tránh cấp `db_owner` chỉ để procedure chạy được.

### 26.4. Oracle AUTHID

Oracle PL/SQL có `AUTHID DEFINER` hoặc `AUTHID CURRENT_USER` cho quyền chạy routine theo definer/invoker trong ngữ cảnh phù hợp. Packages/procedures quyền cao cần API hẹp, grant tối thiểu và kiểm input.

### 26.5. SQLite

SQLite file database thường dựa nhiều vào quyền file và process. Trigger/UDF chạy trong tiến trình ứng dụng; kiểm soát ai mở được file và UDF nào được đăng ký. Không coi trigger trong file SQLite là security boundary chống người có quyền sửa file.

## 27. Routine và SQL injection

Stored routine không tự miễn nhiễm SQL injection. Nguy cơ xuất hiện khi xây dynamic SQL bằng cách nối chuỗi input.

Không an toàn:
```text
sql = "SELECT ... WHERE email = '" + p_email + "'"
EXECUTE sql
```

An toàn hơn:
- PostgreSQL: `EXECUTE ... USING`.
- MySQL: prepared statements/binding theo API phù hợp; tránh raw concat và hiểu giới hạn stored programs.
- SQL Server: `sp_executesql` với parameters.
- Oracle: `EXECUTE IMMEDIATE ... USING`.
- Application: driver parameter binding.

Identifier động vẫn cần allowlist/quoting riêng; bind values không thể thay tên bảng/cột.

### 27.1. Không dùng routine để che giấu SQL động tùy tiện

Một endpoint gọi `CALL do_anything(user_supplied_sql)` không an toàn chỉ vì caller dùng prepared statement khi gọi procedure. Bên trong routine vẫn có thể thực thi raw SQL nguy hiểm. Kiểm soát dynamic SQL ở đúng nơi nó được tạo.

## 28. Trigger và dữ liệu multi-row

Một lỗi thường gặp là viết trigger với giả định một statement chỉ tác động một hàng. Nhưng ứng dụng có thể chạy:

```sql
UPDATE demo_routine_orders
SET status = 'CANCELED'
WHERE tenant_id = 10
  AND status = 'PENDING';
```

Statement có thể đổi nhiều hàng.

Cần hiểu mô hình DBMS:
- PostgreSQL/MySQL/Oracle row trigger chạy một lần mỗi hàng.
- PostgreSQL/Oracle có statement-level trigger.
- SQL Server trigger chạy theo statement và dùng tập `inserted`/`deleted`.
- SQLite trigger chạy theo hàng.

### 28.1. Tác động lên hiệu năng

Row trigger thực hiện một INSERT audit mỗi hàng có thể tạo lượng lớn DML nội bộ. Điều này không nhất thiết sai, nhưng phải đo. Nếu DBMS hỗ trợ statement transition tables/inserted sets, có thể xử lý audit theo tập hợp.

### 28.2. Tác động lên semantics

Nếu trigger bỏ qua hàng bằng cách trả NULL (PostgreSQL BEFORE row) hoặc thay đổi NEW, số hàng được ghi có thể khác số hàng ứng dụng gửi. Application nên hiểu affected row count và kết quả thực tế.

### 28.3. Không dựa vào thứ tự hàng trigger

Thứ tự row processing không nên được coi là business ordering. Nếu cần sequence/order nghiệp vụ, thể hiện rõ bằng cột và query `ORDER BY`, không phụ thuộc trigger xử lý hàng nào trước.

## 29. Testing routines và triggers

Routines/triggers cần integration tests trên DBMS thực tế, không chỉ mock repository.

### 29.1. Test routine contract

- Tham số hợp lệ.
- Không tìm thấy hàng.
- Nhiều hàng trong khi mong một.
- Unique/FK/CHECK violation.
- NULL và giá trị biên.
- Quyền caller.
- Result set/output parameter đúng schema.
- Error code/SQLSTATE ổn định theo contract.

### 29.2. Test trigger contract

- INSERT một hàng.
- INSERT nhiều hàng.
- UPDATE không đổi giá trị.
- UPDATE đổi giá trị.
- DELETE.
- Parent không có child.
- Trigger chain/cascade.
- Rollback transaction.
- Multi-tenant keys.
- Trigger không tạo recursion ngoài ý muốn.

### 29.3. Test rollback

Trong integration test:
1. Bắt đầu transaction.
2. Chạy thao tác kích hoạt trigger.
3. Xác nhận hàng chính và audit đều tồn tại trong transaction.
4. Rollback.
5. Xác nhận cả hai không còn (nếu cùng transaction/transactional engine).

Không kiểm rollback bằng cách chỉ đọc trên cùng transaction đã aborted; cần rollback rồi đọc lại bằng transaction/connection hợp lệ.

### 29.4. Test lỗi và rethrow

Tạo một lỗi có chủ đích, xác nhận:
- Handler có bắt đúng lỗi?
- Caller nhận mã lỗi mong muốn?
- Transaction còn usable hay đã aborted?
- Có rollback đúng phạm vi?
- Log có correlation ID?
- Không lộ dữ liệu nhạy cảm?

### 29.5. Test concurrency

Hai session cùng tạo/cập nhật một tài nguyên:
- Unique constraint có bảo vệ đúng?
- Trigger audit có ghi đúng mỗi thay đổi?
- Deadlock có thể xảy ra?
- Retry có idempotent?
- Procedure kiểm tồn kho có race condition không?

Một procedure `SELECT stock; IF stock > 0 THEN UPDATE` có thể sai khi hai session cùng đọc một số lượng. Cần atomic UPDATE/locking hoặc isolation phù hợp, không chỉ đóng logic vào procedure.

## 30. Observability và vận hành

Routine/trigger có thể khiến SQL chạy mà application không gọi trực tiếp từng câu. Cần quan sát được:
- Routine name và version/migration.
- Query/statement count.
- Duration và rows affected.
- Error code/SQLSTATE.
- Trigger side effects.
- Transaction age/rollback.
- Deadlock/lock wait.
- Execution plan của SQL bên trong routine.
- Caller/request/job correlation ID nếu có.

### 30.1. Logging trong trigger

Không ghi toàn bộ row payload vào log/audit nếu không cần. Chọn cột thay đổi có ý nghĩa, che thông tin nhạy cảm và giới hạn dung lượng. Audit table cần retention, index và quyền truy cập riêng.

### 30.2. Routine thay đổi schema

Khi thay procedure/function/trigger:
- Dùng migration versioned.
- Kiểm dependency.
- Triển khai tương thích với version application đang chạy.
- Tránh deploy nửa chừng khiến app gọi signature chưa tồn tại.
- Test rollback/forward migration.
- Kiểm quyền execute và owner/definer sau migration.

### 30.3. Trigger là logic ẩn nếu không được tài liệu hóa

Một bảng có 5 trigger và mỗi trigger gọi routine khác sẽ khiến một UPDATE đơn giản khó hiểu. Duy trì catalog/documentation:
- Event/timing.
- Bảng/view.
- Routine function/procedure.
- Side effects.
- Transaction behavior.
- Owner/security.
- Điều kiện chạy.
- Ai phụ trách.

## 31. Bảng so sánh xử lý ngoại lệ

| Hệ quản trị | Cơ chế chính | Cách phát lỗi ứng dụng | Cách truyền lại |
| --- | --- | --- | --- |
| PostgreSQL | `EXCEPTION WHEN ...` trong PL/pgSQL | `RAISE EXCEPTION` | `RAISE;` |
| MySQL | `DECLARE HANDLER` | `SIGNAL SQLSTATE` | `RESIGNAL` |
| SQL Server | `TRY...CATCH` | `THROW`/`RAISERROR` | `THROW;` trong CATCH |
| Oracle | `EXCEPTION WHEN ...` | `RAISE_APPLICATION_ERROR` hoặc `RAISE` | `RAISE;` |
| SQLite | Error codes/driver exceptions; trigger `RAISE()` | `RAISE(ABORT/FAIL/ROLLBACK, ...)` trong trigger | Application quyết định rollback/rethrow |

Tên hàm/cú pháp khác nhau; mục tiêu thiết kế tương tự: caller cần phân biệt lỗi nghiệp vụ, lỗi dữ liệu, lỗi tạm thời và lỗi hệ thống.

## 32. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách thay |
| --- | --- | --- |
| Dùng trigger thay mọi business service | Logic ẩn, khó trace | Chỉ dùng trigger cho invariant/phản ứng dữ liệu rõ |
| Dùng procedure cho một câu SELECT đơn giản | Abstraction không cần thiết | SQL trực tiếp hoặc view/function phù hợp |
| Dùng function có side effects không rõ | Khó hiểu khi gọi trong SELECT | Procedure/service cho command |
| Nuốt mọi exception | Caller tưởng thành công | Bắt lỗi cụ thể, rethrow lỗi không dự kiến |
| Trả NULL cho mọi lỗi | Mất phân biệt not found và failure | Error contract |
| Trigger giả định một hàng | Sai khi multi-row DML | Set-based/row-aware logic |
| SQL Server trigger SELECT một hàng từ inserted | Bỏ qua các hàng khác | Join/insert-select từ inserted/deleted |
| MySQL trigger cố COMMIT | Không hợp lệ | Transaction thuộc caller |
| Oracle row trigger query bảng đang mutating | ORA-04091 | Compound/statement-level redesign |
| PostgreSQL dùng lastval cho ID khi trigger gọi sequence khác | Có thể lấy nhầm sequence | RETURNING |
| Trigger gọi HTTP/email trực tiếp | Side effect lệch transaction | Transactional outbox |
| Trigger cập nhật lại bảng gốc | Recursion/loop | BEFORE NEW hoặc thiết kế lại |
| Nhiều trigger phụ thuộc thứ tự không cam kết | Kết quả khó dự đoán | Gộp logic hoặc dùng ordering được hỗ trợ |
| Procedure tự COMMIT bất ngờ | Caller không rollback được toàn bộ | Rõ transaction ownership |
| Retry lỗi mọi loại | Lặp side effect, tăng tải | Phân loại transient vs permanent |
| Retry statement trong transaction aborted | Lỗi tiếp tục | Rollback transaction rồi retry toàn unit |
| Dùng dynamic SQL concat | SQL injection | Bind values + allowlist identifiers |
| SECURITY DEFINER/DEFINER quá rộng | Leo thang quyền | Least privilege, search_path/owner review |
| Log full row trong audit | Lộ PII và phình storage | Chọn field, redaction, retention |
| Không test trigger multi-row | Bug chỉ xuất hiện khi bulk update | Integration tests theo tập hàng |
| Dùng trigger để duy trì count dễ tính | Race/consistency complexity | Aggregate/query/materialized strategy phù hợp |

## 33. Quy trình thiết kế một routine/trigger

### Bước 1 — Viết contract

Ví dụ `create_order`:
- Input: tenant, customer, list items.
- Output: order ID.
- Điều kiện: customer active, item hợp lệ, total không âm.
- Side effects: order, order lines, outbox event.
- Error: customer missing, invalid item, conflict.
- Transaction: caller sở hữu.
- Idempotency: request key duy nhất.

### Bước 2 — Xem constraint trước

Đặt PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK và NOT NULL ở schema. Đừng dùng trigger để thay constraint có sẵn nếu constraint giải quyết được.

### Bước 3 — Chọn procedure hay application service

Nếu logic cần nhiều statement gần dữ liệu, routine có thể phù hợp. Nếu workflow gồm nhiều dịch vụ ngoài, orchestration thường ở application/job worker. Không nhồi HTTP, email và payment gateway vào trigger.

### Bước 4 — Chọn trigger nếu mọi writer phải tuân theo

Ví dụ audit thay đổi status hoặc chuẩn hóa dữ liệu cần áp dụng cho mọi đường ghi. Giữ trigger nhỏ, xác định rõ timing, row/statement và multi-row semantics.

### Bước 5 — Định nghĩa error contract

Phân biệt:
- Not found.
- Duplicate/conflict.
- Invalid state.
- Transient concurrency.
- Permission.
- Infrastructure/internal error.

Chọn SQLSTATE/vendor code và mapping ở application.

### Bước 6 — Xác định transaction owner

Không commit/rollback tùy tiện. Xác định procedure có được tự điều khiển transaction hay không; trigger thông thường nằm trong transaction statement kích hoạt nó.

### Bước 7 — Kiểm security

Quyền EXECUTE, definer/invoker, owner, search_path, dynamic SQL, tenant scope và secret/logging.

### Bước 8 — Test trên DBMS thực tế

Test multi-row, trigger chain, rollback, exception, concurrency, driver result sets và migration.

### Bước 9 — Đo và quan sát

Query count, duration, rows, locks, plan, trigger overhead và transaction lifetime.

## 34. Bài tập thực hành

Các bài PostgreSQL dùng bảng `demo_routine_*` ở mục 2 trong cùng session. Các ví dụ MySQL, SQL Server, Oracle và SQLite cần database tương ứng; không chạy một dialect trên DBMS khác.

### Bài 1 — Constraint hay trigger?
Một cột amount không được âm. So sánh CHECK constraint với BEFORE trigger. Vì sao constraint thường là lựa chọn rõ hơn?

### Bài 2 — Stored procedure
Viết PostgreSQL procedure nhận tenant_id/customer_id và đổi customer status thành BLOCKED. Báo lỗi có mã nếu customer không tồn tại.

### Bài 3 — Function scalar
Viết function trả tổng order PAID theo customer. Dùng COALESCE để customer chưa có order trả 0.

### Bài 4 — Function trả tập
Viết `RETURNS TABLE` liệt kê order của customer. Gọi function trong FROM và kiểm thứ tự.

### Bài 5 — SELECT INTO STRICT
Viết PL/pgSQL function dùng INTO STRICT để tìm email theo khóa. Thử không có hàng và nhiều hàng; phân loại NO_DATA_FOUND/TOO_MANY_ROWS.

### Bài 6 — PostgreSQL exception
Bắt unique_violation khi tạo customer và phát lỗi nghiệp vụ. Giải thích SQLSTATE và vì sao không bắt OTHERS rồi trả NULL.

### Bài 7 — GET STACKED DIAGNOSTICS
Viết exception handler đọc RETURNED_SQLSTATE và MESSAGE_TEXT, log an toàn rồi RAISE lại.

### Bài 8 — Subtransaction
Tạo nested PL/pgSQL block có exception handler. INSERT gây duplicate trong block con rồi handler tiếp tục. Xác định thay đổi nào rollback cục bộ.

### Bài 9 — Procedure transaction control
Viết ví dụ procedure PostgreSQL có COMMIT và kiểm các ngữ cảnh CALL được phép. Giải thích vì sao không commit bên trong function.

### Bài 10 — BEFORE trigger
Viết trigger normalize email bằng lower/trim. So sánh BEFORE với AFTER và giải thích RETURN NEW.

### Bài 11 — AFTER audit trigger
Viết trigger ghi old_status/new_status khi order status thay đổi. Dùng IS DISTINCT FROM để xử lý NULL đúng.

### Bài 12 — Row vs statement
Một UPDATE đổi 5.000 hàng. So sánh số lần chạy row trigger và statement trigger trong PostgreSQL/MySQL/SQL Server.

### Bài 13 — Transition tables
Viết PostgreSQL AFTER UPDATE FOR EACH STATEMENT trigger dùng OLD TABLE/NEW TABLE để audit nhiều hàng. Giải thích giới hạn áp dụng.

### Bài 14 — MySQL procedure OUT
Viết procedure nhận tenant/customer và trả status bằng OUT parameter. Gọi qua session variable.

### Bài 15 — MySQL DECLARE HANDLER
Viết EXIT HANDLER bắt duplicate key, phát SIGNAL SQLSTATE 45000. Khi nào dùng RESIGNAL?

### Bài 16 — MySQL cursor loop
Viết cursor đọc customer IDs, dùng CONTINUE HANDLER FOR NOT FOUND và flag done. Vì sao mọi DECLARE phải nằm đầu block?

### Bài 17 — MySQL trigger
Viết BEFORE INSERT chuẩn hóa email và AFTER INSERT ghi audit. Vì sao trigger chỉ chạy FOR EACH ROW?

### Bài 18 — SQL Server procedure
Viết procedure có input và output parameter. Phân biệt OUTPUT data với RETURN status code.

### Bài 19 — SQL Server TRY/CATCH
Viết procedure với XACT_ABORT, BEGIN TRAN, TRY/CATCH, XACT_STATE và THROW. Xác định khi nào rollback.

### Bài 20 — SQL Server multi-row trigger
Viết AFTER UPDATE trigger audit toàn bộ inserted/deleted. Vì sao SELECT một biến từ inserted không đúng?

### Bài 21 — SQL Server UPDATE(column)
Giải thích vì sao UPDATE(status) không chứng minh status thực sự đổi. Viết phép so sánh old/new có xử lý NULL.

### Bài 22 — Oracle procedure/function
Viết procedure cập nhật customer và function trả tổng order. Dùng SQL%ROWCOUNT kiểm hàng bị tác động.

### Bài 23 — Oracle exception
Bắt NO_DATA_FOUND, TOO_MANY_ROWS và DUP_VAL_ON_INDEX; dùng RAISE_APPLICATION_ERROR cho lỗi nghiệp vụ.

### Bài 24 — Oracle trigger
Viết row-level audit dùng :OLD/:NEW. So sánh statement-level trigger và row-level trigger.

### Bài 25 — Oracle mutating table
Mô tả một row trigger truy vấn lại bảng đang update và lỗi ORA-04091. Đề xuất compound trigger hoặc thiết kế khác.

### Bài 26 — SQLite trigger
Viết BEFORE INSERT trigger dùng RAISE(ABORT) khi amount âm. So sánh ABORT, FAIL và ROLLBACK.

### Bài 27 — SQLite UDF
Đăng ký một function trong Python sqlite3 connection và gọi từ SELECT. Vì sao connection khác cần đăng ký riêng?

### Bài 28 — Transactional outbox
Thiết kế trigger/procedure hoặc application transaction ghi order và outbox row. Worker publish sau commit, có idempotency. Vì sao không gọi HTTP trực tiếp trong trigger?

### Bài 29 — Security definer
Một PostgreSQL SECURITY DEFINER function chạy dynamic SQL từ input. Nêu rủi ro search_path, identifier, owner privilege và cách giảm quyền.

### Bài 30 — API routine đa hệ quản trị
Thiết kế thao tác `create_order` cho PostgreSQL, MySQL, SQL Server, Oracle và SQLite. Ghi rõ signature, output ID/result, transaction ownership, error mapping, trigger side effects, multi-row behavior, quyền execute và integration tests.

## 35. Checklist trước khi triển khai

### Lựa chọn cơ chế
- [ ] Quy tắc có thể được bảo đảm bằng constraint thay vì trigger?
- [ ] Procedure/function có hợp đồng input/output rõ?
- [ ] Trigger có thực sự cần chạy với mọi writer?
- [ ] Đã xác định row-level hay statement-level?
- [ ] Không đặt workflow bên ngoài DB vào trigger?

### Transaction và lỗi
- [ ] Ai sở hữu transaction?
- [ ] Procedure có commit/rollback hay để caller quản lý?
- [ ] Handler bắt đúng condition?
- [ ] Lỗi không dự kiến được truyền lại?
- [ ] Transaction state sau lỗi được kiểm tra?
- [ ] Retry chỉ áp dụng cho lỗi tạm thời và có idempotency?

### Trigger
- [ ] OLD/NEW hoặc inserted/deleted được xử lý đúng?
- [ ] Multi-row DML đã được test?
- [ ] Trigger không tự recursion ngoài ý muốn?
- [ ] Không dựa vào thứ tự trigger không được đảm bảo?
- [ ] Audit có cùng transaction theo yêu cầu?
- [ ] Không gọi dịch vụ ngoài trực tiếp?

### Security và vận hành
- [ ] EXECUTE/grant/definer/invoker tối thiểu?
- [ ] Dynamic SQL bind values và allowlist identifiers?
- [ ] search_path/schema/owner được kiểm soát?
- [ ] Log không lộ PII/secret?
- [ ] Có migration versioned và rollback plan?
- [ ] Có integration tests trên đúng DBMS/driver?
- [ ] Có query count, duration, lock/deadlock và trigger metrics?

## 36. Sơ đồ chọn cơ chế

```text
                 CẦN THỰC THI QUY TẮC DỮ LIỆU
                              |
                              v
                 Có thể dùng constraint không?
                       /              \
                     Có                Không
                     |                   |
                     v                   v
              PK/FK/UNIQUE/CHECK    Có phải phản ứng tự động
                                   với mọi DML writer?
                                      /       \
                                    Có         Không
                                    |            |
                                    v            v
                                  Trigger    Logic nhiều bước?
                                                /       \
                                              Có         Không
                                              |            |
                                              v            v
                                         Procedure     Query/function
                                              |
                                              v
                                 Ai sở hữu transaction?
                                              |
                                              v
                                  Error contract rõ ràng
                                              |
                                              v
                           Test multi-row, rollback, security
```

## 37. Tổng kết

Stored procedure, function, trigger và exception handling là các công cụ mạnh để đặt logic gần dữ liệu, nhưng mỗi công cụ có contract và giới hạn riêng. Procedure phù hợp với một thao tác nhiều bước có đầu vào/đầu ra rõ. Function phù hợp với phép tính hoặc tập dữ liệu có thể dùng trong query theo quy tắc DBMS. Trigger tự động phản ứng với DML, hữu ích cho audit hoặc invariant áp dụng cho mọi writer, nhưng có thể làm side effect khó quan sát. Constraint vẫn là lựa chọn ưu tiên cho các quy tắc dữ liệu cơ bản.

Khác biệt giữa hệ quản trị rất quan trọng: PostgreSQL có PL/pgSQL function/procedure và trigger functions; MySQL có handlers, SIGNAL/RESIGNAL và trigger theo hàng; SQL Server có TRY/CATCH, XACT_STATE và trigger theo statement với inserted/deleted; Oracle có PL/SQL exception, packages, :OLD/:NEW, compound trigger và mutating-table considerations; SQLite có trigger nhưng không có stored procedure native theo mô hình server. Không chỉ đổi cú pháp mà bỏ qua khác biệt về transaction, quyền, result sets và trigger timing.

Một thiết kế bền vững xác định ai sở hữu transaction, lỗi nào có thể retry, handler nào phải rethrow, trigger có chạy với multi-row hay không, side effect nào cùng commit, và routine chạy với quyền của ai. Giữ dynamic SQL được parameterize, quyền tối thiểu, log an toàn, migration có kiểm soát và integration tests trên DBMS thật. Khi những điều đó rõ ràng, routine/trigger sẽ trở thành phần có thể dự đoán và vận hành được của kiến trúc dữ liệu, thay vì một lớp logic ẩn khó gỡ lỗi.
