# Thứ tự thực thi, đệ quy và trigger dây chuyền

Một câu SQL đơn giản có thể gây ra nhiều thao tác mà ứng dụng không gọi trực tiếp:

~~~sql
UPDATE products
SET quantity = quantity + 5
WHERE product_id = 101;
~~~

Khi bảng có **trigger**, hệ quản trị có thể chuẩn hóa dữ liệu trước khi ghi, ghi lịch sử sau khi ghi, thêm sự kiện vào bảng khác, rồi kích hoạt tiếp trigger ở bảng sự kiện. Nếu một trigger **sửa lại chính hàng đã kích hoạt nó**, vòng đệ quy có thể xuất hiện.

Vì vậy, hiểu trigger không chỉ là biết viết `CREATE TRIGGER`. Ta cần trả lời:

1. **Trigger chạy khi nào?** `BEFORE`, `AFTER`, `INSTEAD OF` và cấp `ROW`/`STATEMENT` có ý nghĩa gì?
2. **Nếu nhiều trigger cùng gắn vào một bảng, chúng chạy theo thứ tự nào?**
3. **Một thao tác A tạo thao tác B, rồi B tạo thao tác C** thì dữ liệu và thứ tự thực hiện ra sao?
4. **Đệ quy trực tiếp hoặc gián tiếp** xảy ra khi nào, và cần thiết kế điểm dừng thế nào?
5. Khi trigger cuối **lỗi**, điều gì xảy ra với các thao tác trước trong transaction?
6. Vì sao PostgreSQL, MySQL, SQL Server, Oracle và SQLite có thể cho hành vi khác nhau?

Bài thuộc **Database SQL → Trigger**, với ví dụ thực hành trên **PostgreSQL và PL/pgSQL**. Các cú pháp khác hệ quản trị sẽ được tách riêng.

## 1. Bản đồ thực thi của trigger

Một trigger DML có các thuộc tính chính:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Sự kiện** | `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` | Thao tác nào có thể kích hoạt |
| **Thời điểm** | `BEFORE`, `AFTER`, `INSTEAD OF` | Thực thi ở giai đoạn nào |
| **Cấp độ** | `FOR EACH ROW` hoặc `FOR EACH STATEMENT` | Xử lý từng hàng hay toàn statement |
| **Điều kiện** | `WHEN (OLD.qty IS DISTINCT FROM NEW.qty)` | Có gọi hàm trigger trong trường hợp này không |
| **Hành động** | `EXECUTE FUNCTION some_function()` | Hàm được gọi khi trigger kích hoạt |

Luồng khái quát của một lệnh `UPDATE` trên PostgreSQL:

~~~text
Ung dung: UPDATE items SET qty = ...
                     |
                     v
             BEFORE STATEMENT
                     |
                     v
            BEFORE ROW cho tung hang
                     |
                     v
                 Ghi hang
                     |
                     v
           AFTER ROW (giai doan sau)
                     |
                     v
              AFTER STATEMENT
                     |
                     v
             Hoan tat statement
~~~

Sơ đồ này giúp hình dung thứ tự cơ bản nhưng **không phải lời hứa về một thứ tự toàn phần của mọi trigger có thể tồn tại**. PostgreSQL có các sự kiện AFTER ROW được xếp và xử lý vào cuối statement, các constraint trigger có thể trì hoãn, các thao tác khóa ngoại và nested DML có thể tạo thêm các đường thực thi.

### 1.1. BEFORE, AFTER và INSTEAD OF

**BEFORE ROW** cho phép kiểm tra hoặc sửa `NEW` trước khi hàng được ghi. **AFTER ROW** có thể ghi audit, sinh sự kiện hoặc tác động bảng khác sau thao tác hàng; giá trị `RETURN` từ một AFTER trigger không dùng để thay đổi hàng đã ghi.

**INSTEAD OF** trên view theo ngữ cảnh PostgreSQL được dùng để xử lý thao tác thay cho thao tác trực tiếp lên view. Nó không phải một tùy chọn áp dụng tùy ý cho mọi bảng thường.

### 1.2. FOR EACH ROW và FOR EACH STATEMENT

~~~sql
-- Mau PostgreSQL cap hang:
CREATE TRIGGER example_row
AFTER UPDATE ON some_table
FOR EACH ROW
EXECUTE FUNCTION some_row_function();

-- Mau PostgreSQL cap statement:
CREATE TRIGGER example_statement
AFTER UPDATE ON some_table
FOR EACH STATEMENT
EXECUTE FUNCTION some_statement_function();
~~~

Hai đoạn trên **chỉ minh họa cú pháp**, cần có bảng và hàm tương ứng trước khi chạy.

Với một lệnh `UPDATE` thay đổi 5 hàng:

- Trigger `FOR EACH ROW` có thể kích hoạt **5 lượt** theo điều kiện thích hợp.
- Trigger `FOR EACH STATEMENT` kích hoạt **một lượt** đối với statement ấy.
- Khi `UPDATE` khớp **0 hàng**, statement trigger vẫn có thể được gọi, còn row trigger không có hàng để xử lý.

Điều kiện `WHEN`, `RETURN NULL` từ BEFORE ROW, loại statement đặc biệt và các đường thực thi khác có thể ảnh hưởng số lần gọi thực tế.

### 1.3. OLD, NEW và các biến TG_*

Trong PostgreSQL trigger function:

| Sự kiện | `OLD` | `NEW` |
| --- | --- | --- |
| INSERT | Không có hàng cũ | Hàng được đề xuất chèn |
| UPDATE | Hàng trước cập nhật | Hàng sau cập nhật/đang chuẩn bị ghi |
| DELETE | Hàng trước khi xóa | Không có hàng mới |

Các biến đặc biệt thường dùng:

- `TG_OP`: tên sự kiện `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`.
- `TG_WHEN`: `BEFORE`/`AFTER`/`INSTEAD OF`.
- `TG_LEVEL`: `ROW` hoặc `STATEMENT`.
- `TG_NAME`: tên trigger đang gọi function.
- `TG_TABLE_NAME`: tên bảng/view gắn trigger.
- `pg_trigger_depth()`: độ sâu trigger đang lồng nhau, dùng để quan sát.

`OLD` và `NEW` mô tả **một hàng** nên không thể giả định chúng có giá trị tương ứng trong statement trigger. Nếu cần tập hàng của một statement, PostgreSQL có **transition tables** ở những trường hợp được hỗ trợ.

## 2. Bộ dữ liệu thực hành

Chỉ tạo các đối tượng sau trong **database PostgreSQL thực hành riêng**, khi chưa có tên `lab_t354_*` tương ứng. Không thử vòng lặp đệ quy trên cơ sở dữ liệu sản xuất.

### 2.1. Bảng sản phẩm

~~~sql
CREATE TABLE lab_t354_items (
    item_id INTEGER PRIMARY KEY,
    item_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    item_label TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lab_t354_items
    (item_id, item_code, quantity, item_label)
VALUES
    (101, 'PEN',   3, 'PEN:3'),
    (102, 'NOTE',  5, 'NOTE:5'),
    (103, 'MOUSE', 2, 'MOUSE:2');
~~~

### 2.2. Bảng trace

~~~sql
CREATE TABLE lab_t354_trace (
    trace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id INTEGER,
    trigger_name TEXT NOT NULL,
    trigger_when TEXT NOT NULL,
    trigger_op TEXT NOT NULL,
    observed_code TEXT,
    observed_label TEXT,
    note TEXT,
    traced_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
~~~

`trace_id` giúp quan sát **thứ tự chèn log trong một lần thử**, không phải một đồng hồ tuyệt đối giữa những giao dịch đồng thời. PostgreSQL có thể **không hoàn trả giá trị sequence** đã cấp sau `ROLLBACK`.

Kiểm tra:

~~~sql
SELECT item_id, item_code, quantity, item_label
FROM lab_t354_items
ORDER BY item_id;
~~~

| item_id | item_code | quantity | item_label |
| ---: | --- | ---: | --- |
| 101 | PEN | 3 | PEN:3 |
| 102 | NOTE | 5 | NOTE:5 |
| 103 | MOUSE | 2 | MOUSE:2 |

**Quy tắc thực hành:** tạo bảng và trigger theo hướng dẫn một lần. Mỗi ví dụ cập nhật sau đó được bao bằng `BEGIN ... ROLLBACK` để không làm thay đổi dữ liệu ban đầu cho các ví dụ tiếp theo.

## 3. Thứ tự hai BEFORE trigger có phụ thuộc nhau

Ta có hai nhiệm vụ:

1. Chuẩn hóa `item_code` thành chữ hoa, bỏ khoảng trắng hai đầu.
2. Tính `item_label` từ **mã đã chuẩn hóa** và `quantity`.

Nếu bước 2 chạy trước bước 1, nhãn có thể dùng mã chưa được chuẩn hóa. Vì vậy **thứ tự trigger quan trọng**.

### 3.1. Hàm A: chuẩn hóa mã

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_normalize_code()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    NEW.item_code := UPPER(BTRIM(NEW.item_code));

    INSERT INTO lab_t354_trace (
        item_id, trigger_name, trigger_when, trigger_op,
        observed_code, observed_label, note
    )
    VALUES (
        NEW.item_id, TG_NAME, TG_WHEN, TG_OP,
        NEW.item_code, NEW.item_label, 'Normalized code'
    );

    RETURN NEW;
END;
$fn$;
~~~

Hàm này **gán vào `NEW.item_code`**, chứ không mở một lệnh `UPDATE lab_t354_items` khác. Đây là cách phù hợp với mục tiêu chuẩn hóa cột của **chính hàng đang ghi**.

### 3.2. Hàm B: xây nhãn

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_build_label()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    NEW.item_label := NEW.item_code || ':' || NEW.quantity::TEXT;

    INSERT INTO lab_t354_trace (
        item_id, trigger_name, trigger_when, trigger_op,
        observed_code, observed_label, note
    )
    VALUES (
        NEW.item_id, TG_NAME, TG_WHEN, TG_OP,
        NEW.item_code, NEW.item_label, 'Built label'
    );

    RETURN NEW;
END;
$fn$;
~~~

### 3.3. Gắn hai trigger

~~~sql
CREATE TRIGGER lab_t354_a_normalize
BEFORE INSERT OR UPDATE ON lab_t354_items
FOR EACH ROW
EXECUTE FUNCTION lab_t354_normalize_code();

CREATE TRIGGER lab_t354_b_label
BEFORE INSERT OR UPDATE ON lab_t354_items
FOR EACH ROW
EXECUTE FUNCTION lab_t354_build_label();
~~~

**Quy tắc PostgreSQL:** khi nhiều trigger **cùng loại** cùng đủ điều kiện kích hoạt trên một đối tượng, chúng chạy theo **thứ tự alphabet của tên trigger**.

Ở đây `lab_t354_a_normalize` đứng trước `lab_t354_b_label`. **Không phải vì `CREATE TRIGGER a` được chạy trước `CREATE TRIGGER b`**.

~~~text
lab_t354_a_normalize
          |
          v
       NEW.item_code = "MOUSE"
          |
          v
lab_t354_b_label
          |
          v
       NEW.item_label = "MOUSE:4"
~~~

### 3.4. Thử cập nhật một hàng

~~~sql
BEGIN;

UPDATE lab_t354_items
SET
    item_code = '  mOuSe  ',
    quantity = 4,
    item_label = 'ignored'
WHERE item_id = 101
RETURNING item_id, item_code, quantity, item_label;

SELECT
    trace_id,
    trigger_name,
    trigger_when,
    observed_code,
    observed_label
FROM lab_t354_trace
ORDER BY trace_id;

ROLLBACK;
~~~

Kết quả tạm thời của hàng 101:

| item_id | item_code | quantity | item_label |
| ---: | --- | ---: | --- |
| 101 | MOUSE | 4 | MOUSE:4 |

Trace trong transaction:

| Thứ tự | trigger_name | observed_code | observed_label |
| ---: | --- | --- | --- |
| 1 | lab_t354_a_normalize | MOUSE | ignored |
| 2 | lab_t354_b_label | MOUSE | MOUSE:4 |

Trigger B nhìn thấy `NEW.item_code` đã được A sửa. `item_label='ignored'` trong lệnh UPDATE bị B ghi đè trên `NEW`. `ROLLBACK` hoàn tác thay đổi hàng sản phẩm và cả các hàng trace.

### 3.5. Đừng tạo phụ thuộc ngầm nếu có thể tránh

Với biến đổi mà B **luôn phụ thuộc** kết quả A, một function BEFORE gộp:

~~~sql
NEW.item_code := UPPER(BTRIM(NEW.item_code));
NEW.item_label := NEW.item_code || ':' || NEW.quantity::TEXT;
RETURN NEW;
~~~

thường dễ bảo trì hơn hai trigger rời. Thứ tự tên có thể bị ảnh hưởng khi đổi tên trigger hoặc chuyển DBMS. Tách trigger hợp lý khi trách nhiệm độc lập, nhưng không nên tạo chuỗi phụ thuộc khó nhận biết chỉ bằng tên.

## 4. BEFORE ROW trả NEW hoặc NULL

Với PostgreSQL:

- `RETURN NEW;` trong `BEFORE INSERT/UPDATE FOR EACH ROW` cho phép tiếp tục xử lý hàng, với các giá trị `NEW` đã sửa.
- `RETURN OLD;` thường dùng với `BEFORE DELETE FOR EACH ROW` nếu muốn cho phép xóa.
- `RETURN NULL;` trong **BEFORE ROW** làm **bỏ qua thao tác cho hàng đó**. Các row triggers tiếp theo cho thao tác ấy không được gọi.
- `RETURN` của **AFTER trigger** và statement trigger bị bỏ qua; `RETURN NULL;` ở đó không có ý nghĩa chặn hàng như trong BEFORE ROW.

### 4.1. Ví dụ BEFORE chặn hàng

~~~sql
CREATE TABLE lab_t354_gate (
    id INTEGER PRIMARY KEY,
    flag TEXT NOT NULL
);

CREATE OR REPLACE FUNCTION lab_t354_gate_before_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.flag = 'SKIP' THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER lab_t354_gate_filter
BEFORE INSERT ON lab_t354_gate
FOR EACH ROW
EXECUTE FUNCTION lab_t354_gate_before_insert();
~~~

~~~sql
BEGIN;

INSERT INTO lab_t354_gate(id, flag)
VALUES (1, 'KEEP'), (2, 'SKIP'), (3, 'KEEP')
RETURNING id, flag;

ROLLBACK;
~~~

`RETURNING` chỉ có **1 và 3**, không có 2. Hàng 2 bị BEFORE trigger bỏ qua mà không nhất thiết làm statement lỗi.

**Cảnh báo:** nếu dữ liệu sai cần **báo lỗi**, `RAISE EXCEPTION` có thể phù hợp hơn bỏ qua âm thầm. Đừng `RETURN NULL` chỉ vì “function không cần trả một giá trị nghiệp vụ”.

## 5. Thêm AFTER ROW và AFTER STATEMENT để quan sát đầy đủ

Ta bổ sung:

- `BEFORE UPDATE` cập nhật timestamp nếu thuộc tính nghiệp vụ thực sự khác.
- `AFTER INSERT/UPDATE/DELETE FOR EACH ROW` ghi log.
- `AFTER UPDATE FOR EACH STATEMENT` ghi một dấu cho cả statement.

### 5.1. Trigger C: timestamp khi mã hoặc số lượng thay đổi

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_touch_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    NEW.updated_at := clock_timestamp();

    INSERT INTO lab_t354_trace (
        item_id, trigger_name, trigger_when, trigger_op,
        observed_code, observed_label, note
    )
    VALUES (
        NEW.item_id, TG_NAME, TG_WHEN, TG_OP,
        NEW.item_code, NEW.item_label, 'Changed updated_at'
    );

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER lab_t354_c_timestamp
BEFORE UPDATE ON lab_t354_items
FOR EACH ROW
WHEN (
    OLD.item_code IS DISTINCT FROM NEW.item_code
    OR OLD.quantity IS DISTINCT FROM NEW.quantity
)
EXECUTE FUNCTION lab_t354_touch_timestamp();
~~~

Trong PostgreSQL, `WHEN` của BEFORE ROW được kiểm tra **ngay trước khi function tương ứng được gọi**. Vì tên C đứng sau A và B, nó có thể nhìn thấy `NEW` **đã bị A/B sửa**.

### 5.2. AFTER ROW ghi dấu giá trị cuối

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_after_item_row()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO lab_t354_trace (
            item_id, trigger_name, trigger_when, trigger_op,
            observed_code, observed_label, note
        )
        VALUES (
            OLD.item_id, TG_NAME, TG_WHEN, TG_OP,
            OLD.item_code, OLD.item_label, 'Row deleted'
        );
    ELSE
        INSERT INTO lab_t354_trace (
            item_id, trigger_name, trigger_when, trigger_op,
            observed_code, observed_label, note
        )
        VALUES (
            NEW.item_id, TG_NAME, TG_WHEN, TG_OP,
            NEW.item_code, NEW.item_label, 'Row written'
        );
    END IF;

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab_t354_after_row
AFTER INSERT OR UPDATE OR DELETE ON lab_t354_items
FOR EACH ROW
EXECUTE FUNCTION lab_t354_after_item_row();
~~~

Với AFTER ROW, `RETURN NULL` không hủy kết quả INSERT/UPDATE/DELETE; giá trị trả của function bị bỏ qua. Hàm này **chỉ ghi sang bảng trace**, không UPDATE lại bảng sản phẩm.

### 5.3. AFTER STATEMENT ghi dấu lệnh UPDATE

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_after_update_statement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO lab_t354_trace (
        item_id, trigger_name, trigger_when, trigger_op,
        observed_code, observed_label, note
    )
    VALUES (
        NULL, TG_NAME, TG_WHEN, TG_OP,
        NULL, NULL, 'One UPDATE statement completed'
    );

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab_t354_after_statement
AFTER UPDATE ON lab_t354_items
FOR EACH STATEMENT
EXECUTE FUNCTION lab_t354_after_update_statement();
~~~

Đây là một **statement trigger**, không có một `NEW`/`OLD` duy nhất để gán vào log.

## 6. Thứ tự thực thi ở ví dụ UPDATE một hàng

~~~sql
BEGIN;

UPDATE lab_t354_items
SET item_code = '  pen-blue  ',
    quantity = 7,
    item_label = 'overridden'
WHERE item_id = 101
RETURNING item_id, item_code, quantity, item_label;

SELECT
    trace_id,
    trigger_name,
    trigger_when,
    trigger_op,
    observed_code,
    observed_label
FROM lab_t354_trace
ORDER BY trace_id;

ROLLBACK;
~~~

Với các trigger vừa tạo, trace có thứ tự:

| Thứ tự | Trigger | Loại |
| ---: | --- | --- |
| 1 | `lab_t354_a_normalize` | BEFORE UPDATE ROW |
| 2 | `lab_t354_b_label` | BEFORE UPDATE ROW |
| 3 | `lab_t354_c_timestamp` | BEFORE UPDATE ROW, WHEN đúng |
| 4 | `lab_t354_after_row` | AFTER UPDATE ROW |
| 5 | `lab_t354_after_statement` | AFTER UPDATE STATEMENT |

Giá trị sản phẩm tạm thời: **PEN-BLUE, 7, PEN-BLUE:7**. Sau rollback, giá trị ban đầu **PEN, 3, PEN:3** được khôi phục.

### 6.1. UPDATE 0 hàng vẫn kích hoạt statement trigger

~~~sql
BEGIN;

UPDATE lab_t354_items
SET quantity = 99
WHERE item_id = -999;

SELECT trigger_name, note
FROM lab_t354_trace
ORDER BY trace_id;

ROLLBACK;
~~~

Không có hàng có ID -999, vì vậy **không có BEFORE/AFTER ROW trigger** được gọi. Nhưng `lab_t354_after_statement` vẫn ghi được một dòng cho lệnh UPDATE.

**Có log statement không chứng minh có hàng thật sự thay đổi.**

### 6.2. UPDATE giá trị bằng chính giá trị cũ

~~~sql
BEGIN;

UPDATE lab_t354_items
SET quantity = quantity
WHERE item_id = 101;

SELECT trigger_name, trigger_when
FROM lab_t354_trace
ORDER BY trace_id;

ROLLBACK;
~~~

Trong ví dụ này:

- A và B vẫn có thể chạy vì là BEFORE UPDATE ROW.
- C không chạy nếu `OLD.item_code` và `OLD.quantity` **không khác `NEW` sau A/B**.
- AFTER ROW và AFTER STATEMENT vẫn chạy đối với UPDATE đã khớp hàng.

**Một lệnh `UPDATE` là sự kiện UPDATE ngay cả khi giá trị cột sau ghi giống giá trị cũ.** Muốn chỉ xử lý những thay đổi thật, dùng điều kiện so `OLD` và `NEW`.

### 6.3. Thứ tự hàng khác thứ tự trigger

Với:

~~~sql
UPDATE lab_t354_items
SET quantity = quantity + 1
WHERE item_id IN (101, 102, 103);
~~~

PostgreSQL bảo đảm thứ tự **giữa các trigger cùng loại** theo tên, nhưng **không bảo đảm thứ tự xử lý các hàng** là 101 → 102 → 103. Không xây logic nghiệp vụ dựa trên thứ tự các row triggers tương ứng các ID.

Nếu cần một thứ tự xử lý nghiệp vụ, phải thiết kế khóa, câu lệnh và giao diện thích hợp; `ORDER BY` ở một truy vấn xem kết quả không chứng minh thứ tự mà trigger đã được gọi.

## 7. Quy tắc thứ tự của PostgreSQL cần hiểu chính xác

**Nhiều trigger cùng loại** trên cùng đối tượng, cùng sự kiện/thời điểm/cấp độ, được PostgreSQL kích hoạt theo **tên trigger theo thứ tự alphabet**.

Không nên diễn giải rộng thành:

~~~text
Trigger co ten bat dau bang "a" se luon chay truoc
trigger bat dau bang "b" tren moi bang, moi giai doan.
~~~

**BEFORE** và **AFTER** là những giai đoạn khác nhau; **ROW** và **STATEMENT** là cấp khác nhau; nested DML tạo statement bên trong. Đặc biệt, constraint trigger có thể có thời điểm kiểm tra trì hoãn.

### 7.1. Khi nào nên dùng một function?

Nếu một quy tắc **bắt buộc** nối tiếp nhiều bước, ví dụ chuẩn hóa mã rồi tính nhãn, nên cân nhắc đặt cả hai trong **một BEFORE ROW function** để phụ thuộc được thể hiện bằng thứ tự lệnh.

Nếu hai trigger có trách nhiệm độc lập, tách riêng giúp bảo trì. Tuy nhiên cần ghi chú rằng **đổi tên trigger trên PostgreSQL có thể đổi thứ tự chạy** nếu nhiều trigger cùng loại.

### 7.2. BEFORE trigger có thể ảnh hưởng trigger sau

Trong PostgreSQL, một BEFORE ROW trigger trả `NEW` đã sửa; trigger BEFORE ROW kế tiếp trên hàng đó nhận các giá trị `NEW` đã thay đổi. Điều này là lý do hàm B trong bài nhìn thấy mã do A chuẩn hóa.

Không suy ra điều tương tự cho tất cả DBMS: có hệ thống dùng `FOLLOWS`/`PRECEDES` hoặc không bảo đảm thứ tự giữa nhiều trigger.

## 8. Trigger dây chuyền: một INSERT sinh ba bước tiếp theo

Một hệ thống bán hàng có thể muốn:

~~~text
INSERT orders
    |
    v
AFTER INSERT trigger A
    | INSERT reservations
    v
AFTER INSERT trigger B
    | INSERT outbox
    v
AFTER INSERT trigger C
    | INSERT chain_trace
    v
Hoan tat C, roi quay ve B, roi A
~~~

Trong bài, `reservations` ghi **ý định giữ hàng**, **không trực tiếp trừ tồn kho**. Hệ thống thực sự cần thêm kiểm soát tồn, ngăn sự kiện trùng, quản lý giao dịch và worker xử lý outbox.

### 8.1. Bảng cho chuỗi

~~~sql
CREATE TABLE lab_t354_orders (
    order_id INTEGER PRIMARY KEY,
    customer_code TEXT NOT NULL,
    requested_qty INTEGER NOT NULL CHECK (requested_qty > 0)
);

CREATE TABLE lab_t354_reservations (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES lab_t354_orders(order_id),
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty > 0),
    source_event TEXT NOT NULL,
    UNIQUE (order_id, source_event)
);

CREATE TABLE lab_t354_outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL UNIQUE
        REFERENCES lab_t354_reservations(event_id),
    order_id INTEGER NOT NULL REFERENCES lab_t354_orders(order_id),
    payload TEXT NOT NULL
);

CREATE TABLE lab_t354_chain_trace (
    trace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage TEXT NOT NULL,
    order_id INTEGER NOT NULL,
    trigger_depth INTEGER NOT NULL
);
~~~

### 8.2. Trigger A: orders → reservations

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_order_to_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE NOTICE 'A %, depth %', TG_NAME, pg_trigger_depth();

    INSERT INTO lab_t354_reservations (
        order_id, reserved_qty, source_event
    )
    VALUES (
        NEW.order_id, NEW.requested_qty, 'ORDER_CREATED'
    );

    INSERT INTO lab_t354_chain_trace (
        stage, order_id, trigger_depth
    )
    VALUES (
        'A finished', NEW.order_id, pg_trigger_depth()
    );

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab_t354_orders_after_insert
AFTER INSERT ON lab_t354_orders
FOR EACH ROW
EXECUTE FUNCTION lab_t354_order_to_event();
~~~

`pg_trigger_depth()` thường cho **1** khi A được gọi trực tiếp từ câu `INSERT orders` của ứng dụng.

### 8.3. Trigger B: reservations → outbox

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_event_to_outbox()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE NOTICE 'B %, depth %', TG_NAME, pg_trigger_depth();

    INSERT INTO lab_t354_outbox (
        event_id, order_id, payload
    )
    VALUES (
        NEW.event_id,
        NEW.order_id,
        format(
            'order_id=%s;reserved_qty=%s',
            NEW.order_id, NEW.reserved_qty
        )
    );

    INSERT INTO lab_t354_chain_trace (
        stage, order_id, trigger_depth
    )
    VALUES (
        'B finished', NEW.order_id, pg_trigger_depth()
    );

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab_t354_reservations_after_insert
AFTER INSERT ON lab_t354_reservations
FOR EACH ROW
EXECUTE FUNCTION lab_t354_event_to_outbox();
~~~

Trigger B chạy khi A gọi `INSERT reservations`, nên độ sâu quan sát được ở đường đi này là **2**.

### 8.4. Trigger C: outbox → trace

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_outbox_to_trace()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO lab_t354_chain_trace (
        stage, order_id, trigger_depth
    )
    VALUES (
        'C finished', NEW.order_id, pg_trigger_depth()
    );

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab_t354_outbox_after_insert
AFTER INSERT ON lab_t354_outbox
FOR EACH ROW
EXECUTE FUNCTION lab_t354_outbox_to_trace();
~~~

Trong đường A → B → C không có trigger lồng khác, C quan sát được **depth = 3**.

## 9. Quan sát chuỗi và lý giải thứ tự C → B → A

~~~sql
BEGIN;

INSERT INTO lab_t354_orders(
    order_id, customer_code, requested_qty
)
VALUES (5001, 'C001', 2);

SELECT order_id, requested_qty
FROM lab_t354_orders
WHERE order_id = 5001;

SELECT order_id, reserved_qty, source_event
FROM lab_t354_reservations
WHERE order_id = 5001;

SELECT order_id, payload
FROM lab_t354_outbox
WHERE order_id = 5001;

SELECT stage, trigger_depth
FROM lab_t354_chain_trace
WHERE order_id = 5001
ORDER BY trace_id;

ROLLBACK;
~~~

Mặc dù người dùng chỉ `INSERT` vào `orders`, trong transaction có một hàng mới ở **orders**, một hàng ở **reservations**, một hàng ở **outbox**, ba hàng ở **chain_trace**.

Kết quả trace:

| stage | trigger_depth |
| --- | ---: |
| C finished | 3 |
| B finished | 2 |
| A finished | 1 |

**Vì sao thứ tự hoàn tất là C → B → A trong khi thứ tự bắt đầu là A → B → C?**

Hàm A chỉ chèn log `'A finished'` **sau khi** `INSERT reservations` trả về. Nhưng lệnh INSERT đó kích hoạt B; B lại chờ `INSERT outbox` kích hoạt C. Vì vậy C hoàn tất, B tiếp tục và hoàn tất, cuối cùng A mới tiếp tục.

~~~text
Bat dau goi:  A -> B -> C
Quay ve:      C -> B -> A
~~~

Đây là **nested execution**, không phải một hàng đợi bất đồng bộ tự chạy về sau.

### 9.1. Trigger chạy cùng transaction

Sau `ROLLBACK`, cả đơn hàng, event, outbox và trace của ví dụ bị hoàn tác. Một trigger thông thường không tự commit phần của nó thành một transaction độc lập.

### 9.2. Outbox không có nghĩa thông báo đã được gửi

Outbox là **bản ghi trong database** được tạo cùng transaction; nó có thể được worker ứng dụng đọc và gửi **sau commit**. Gửi email/HTTP trực tiếp từ trigger không được `ROLLBACK` của database thu hồi, nên transactional outbox có thể giúp giữ nhất quán giữa dữ liệu và thông điệp cần gửi.

### 9.3. Không suy ra thứ tự tất cả hàng từ trace_id

`trace_id` tăng theo lần cấp sequence; nó giúp quan sát một lần chạy cụ thể. Với nhiều transaction đồng thời hoặc trigger xử lý nhiều hàng, không coi nó là **thứ tự nghiệp vụ tuyệt đối** và không suy rằng ID liên tiếp nghĩa là không có rollback.

## 10. Đệ quy trực tiếp: tự UPDATE lại cùng hàng

Đệ quy trực tiếp xảy ra khi trigger thực hiện thao tác làm **chính trigger ấy** được gọi lại:

~~~text
UPDATE items
    -> AFTER UPDATE trigger
        -> UPDATE items
            -> AFTER UPDATE trigger
                -> UPDATE items
                    -> ...
~~~

### 10.1. Mẫu nguy hiểm — tuyệt đối không chạy

~~~sql
-- KHONG CHAY: minh hoa thiet ke de quy.
CREATE OR REPLACE FUNCTION lab_t354_bad_self_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE lab_t354_items
    SET updated_at = clock_timestamp()
    WHERE item_id = NEW.item_id;

    RETURN NULL;
END;
$fn$;

-- KHONG TAO trigger sau:
-- CREATE TRIGGER lab_t354_bad_recursive
-- AFTER UPDATE ON lab_t354_items
-- FOR EACH ROW
-- EXECUTE FUNCTION lab_t354_bad_self_update();
~~~

Mỗi `UPDATE items` bên trong lại kích hoạt AFTER UPDATE trên cùng hàng. PostgreSQL không tự biết yêu cầu chỉ “chạm timestamp một lần”. Một chuỗi như vậy có thể chạy cho tới khi gặp lỗi stack/tài nguyên, thay vì dừng theo quy tắc nghiệp vụ.

### 10.2. Cách sửa: thao tác với NEW ở BEFORE ROW

Nếu chỉ muốn đặt `updated_at` trong hàng đang ghi:

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_good_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$fn$;
~~~

Hàm này là **mẫu thay thế**, không cần gắn thêm trigger nếu bạn đã dùng `lab_t354_c_timestamp` ở mục 5. `BEFORE UPDATE` gán `NEW`, tránh mở **một UPDATE mới trên cùng bảng** chỉ để đổi cùng hàng.

### 10.3. AFTER không dùng RETURN NEW để thay đổi hàng

Trong PostgreSQL, giá trị trả về của AFTER trigger bị bỏ qua. Nếu muốn sửa dữ liệu của **hàng sắp được ghi**, hãy dùng BEFORE ROW và `RETURN NEW` khi phù hợp. Nếu muốn ghi audit hoặc event trên **bảng khác**, AFTER ROW thường rõ nghĩa.

## 11. Đệ quy gián tiếp: vòng A → B → A

Không cần tự UPDATE cùng bảng ngay trong function để xảy ra recursion. Một vòng qua **hai hoặc nhiều bảng** cũng nguy hiểm:

~~~text
UPDATE orders
    |
    v
trigger orders -> INSERT order_events
                      |
                      v
                trigger order_events -> UPDATE orders
                                            |
                                            v
                                      trigger orders
                                            |
                                           ...
~~~

Ví dụ:

- AFTER UPDATE trên `orders` phát event mỗi lần sửa status.
- AFTER INSERT trên `order_events` cập nhật lại status của `orders`.
- UPDATE thứ hai vẫn kích hoạt AFTER UPDATE dù status không đổi.
- Chuỗi phát event mới lặp lại.

### 11.1. Điểm dừng phải có ý nghĩa nghiệp vụ

Các biện pháp hữu ích:

1. **Phân luồng một chiều**: orders → events → outbox, không để outbox cập nhật ngược orders trong cùng chuỗi nếu không cần.
2. **Chỉ phản ứng khi trạng thái thật sự đổi**: `OLD.status IS DISTINCT FROM NEW.status`.
3. **Khóa idempotency**: một event nghiệp vụ có mã duy nhất và chỉ được ghi một lần.
4. **Trạng thái đã xử lý**: chỉ tiếp tục khi chưa hoàn tất một giai đoạn rõ ràng.
5. **Kiểm thử đường đi toàn hệ**: rà cả trigger bảng A, bảng B và constraint/cascade liên quan.

Không phải mọi đường đi A → B → A đều vô hạn nếu có điểm dừng hợp lệ, nhưng thiếu điểm dừng có thể khiến sự cố khó theo dõi hơn đệ quy trực tiếp.

## 12. WHEN và UPDATE OF: hai cách lọc rất khác

### 12.1. Chỉ chạy audit khi giá trị thật sự khác

Mẫu PostgreSQL:

~~~sql
-- Minh hoa, khong can tao neu da co AFTER row log khac.
CREATE TRIGGER lab_t354_qty_audit_only
AFTER UPDATE ON lab_t354_items
FOR EACH ROW
WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)
EXECUTE FUNCTION lab_t354_after_item_row();
~~~

Mệnh đề `WHEN` đánh giá sự khác nhau giữa `OLD` và `NEW`. Không nên tạo trigger này **đồng thời** với trigger audit mọi UPDATE đã có nếu không muốn ghi log trùng.

### 12.2. UPDATE OF xét cột có trong SET

~~~sql
-- Minh hoa cu phap:
CREATE TRIGGER lab_t354_qty_targeted
AFTER UPDATE OF quantity ON lab_t354_items
FOR EACH ROW
EXECUTE FUNCTION lab_t354_after_item_row();
~~~

Khi chạy:

~~~sql
UPDATE lab_t354_items
SET quantity = quantity
WHERE item_id = 101;
~~~

`quantity` có mặt trong `SET`, nên trigger `UPDATE OF quantity` vẫn có thể kích hoạt **dù số không đổi**. Đây không phải điều kiện kiểm tra khác biệt giá trị.

| Cơ chế | Điều kiện thực sự được hỏi |
| --- | --- |
| `UPDATE OF quantity` | Lệnh UPDATE có **nêu cột quantity trong SET** không? |
| `WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)` | Giá trị quantity **có khác tại thời điểm kiểm tra** không? |

Ngoài ra, việc một BEFORE ROW trigger sửa `NEW.quantity` không tự biến một câu `UPDATE` vốn không nêu quantity thành `UPDATE OF quantity`. Khi cần phát event dựa trên giá trị đã thay đổi, ưu tiên điều kiện `OLD`/`NEW` phù hợp.

### 12.3. WHEN chưa đủ nếu mỗi lần trigger tự làm dữ liệu thay đổi

Một trigger chỉ so `OLD.updated_at IS DISTINCT FROM NEW.updated_at` vẫn có thể kích hoạt lặp nếu mỗi lượt đều gán timestamp mới. Điểm dừng phải dựa trên **trạng thái nghiệp vụ**, không chỉ việc chọn bất kỳ cột nào “khác” sau mỗi cập nhật.

## 13. pg_trigger_depth(): công cụ chẩn đoán

PostgreSQL cung cấp:

~~~sql
SELECT pg_trigger_depth() AS outside_depth;
~~~

Ở ngoài trigger, kết quả thông thường là **0**. Bên trong trigger:

~~~sql
RAISE NOTICE
    'name=%, op=%, depth=%',
    TG_NAME, TG_OP, pg_trigger_depth();
~~~

Trong chuỗi A → B → C của bài, độ sâu quan sát được lần lượt là **1, 2, 3**.

### 13.1. Không dùng depth làm chính sách duy nhất

Một mẹo:

~~~sql
-- Chi minh hoa, khong phai giai phap tong quat.
IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
END IF;
~~~

không đáng tin cậy làm giải pháp chung vì:

- **Nested trigger hợp lệ** cũng có depth > 1.
- Thêm một trigger trung gian có thể đổi độ sâu dù nghiệp vụ không đổi.
- Depth không biết **event_id đã xử lý chưa**, dữ liệu có đổi không hoặc đường đi nào gây vòng.
- `RETURN NEW` không áp dụng như nhau cho AFTER, DELETE và statement triggers.

Hãy dùng độ sâu để **quan sát**, còn chính sách dừng nên dựa trên bất biến dữ liệu, chuyển trạng thái, khóa duy nhất và idempotency.

## 14. Transaction: lỗi ở trigger cuối ảnh hưởng toàn chuỗi

Giả sử:

~~~text
INSERT orders
  -> trigger A INSERT reservations
     -> trigger B INSERT outbox
        -> trigger C RAISE EXCEPTION
~~~

Nếu exception trong C không được xử lý đúng cách, câu lệnh gây chuỗi đó **thất bại**, các thay đổi database thuộc statement không được commit một phần. Khi trong transaction PostgreSQL tường minh, transaction có thể chuyển sang trạng thái **aborted**, cần `ROLLBACK` trước khi tiếp tục.

### 14.1. Lỗi ràng buộc

~~~sql
BEGIN;

-- DU KIEN LOI CHECK, KHONG PHAI MOT DON HOP LE.
INSERT INTO lab_t354_orders(
    order_id, customer_code, requested_qty
)
VALUES (5002, 'C002', -1);

-- Sau loi PostgreSQL, chay ROLLBACK o ket noi nay.
~~~

Hàng có `requested_qty < 0` bị từ chối. Để kết thúc transaction đang lỗi:

~~~sql
ROLLBACK;
~~~

Không xem trigger là một transaction độc lập tự lưu kết quả. Nếu người gọi rollback, các hàng log/reservation/outbox được tạo trong cùng transaction cũng rollback.

### 14.2. Sequence không bảo đảm liền mạch sau rollback

Các bảng trace/outbox sử dụng identity. PostgreSQL có thể đã cấp một ID trước khi statement lỗi; **sequence có thể không hoàn lại giá trị đó**. Vì vậy audit ID không liên tục không chứng minh rằng có dữ liệu mất theo nghĩa nghiệp vụ.

### 14.3. Tác dụng phụ bên ngoài không tự rollback

Nếu một trigger trực tiếp gửi email hoặc HTTP request, rollback database **không thu hồi được** thông điệp đã gửi. Thiết kế outbox dùng **một hàng trong transaction**, rồi worker gửi sau commit thường có tính nhất quán hơn. Worker phải xử lý retry, xử lý trùng và xác nhận.

## 15. Trigger của khóa ngoại CASCADE

Một tác động dây chuyền khác là **hành động khóa ngoại**:

~~~sql
CREATE TABLE lab_t354_parent (
    parent_id INTEGER PRIMARY KEY
);

CREATE TABLE lab_t354_child (
    child_id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL
        REFERENCES lab_t354_parent(parent_id)
        ON DELETE CASCADE
);

INSERT INTO lab_t354_parent(parent_id) VALUES (1);
INSERT INTO lab_t354_child(child_id, parent_id)
VALUES (10, 1), (11, 1);
~~~

~~~sql
BEGIN;

DELETE FROM lab_t354_parent
WHERE parent_id = 1;

SELECT COUNT(*) AS children_left
FROM lab_t354_child
WHERE parent_id = 1;

ROLLBACK;
~~~

Trong transaction, `children_left = 0` vì hai hàng con bị xóa theo CASCADE. Sau rollback, hàng cha và con trở lại.

Trong PostgreSQL, khóa ngoại được hỗ trợ bởi **constraint/internal triggers**; cascade có thể tạo các thao tác DML trên bảng liên quan và dẫn tới **user triggers** thích hợp của bảng con. Phải xét cả:

- Trigger trên bảng cha.
- Quy tắc `ON DELETE CASCADE`/`SET NULL`/`RESTRICT`/`NO ACTION`.
- Trigger trên bảng con và những bảng tiếp theo mà chúng sửa.

**Không giả định câu DELETE chỉ ảnh hưởng bảng được nêu trực tiếp.** Nhưng cũng **không suy rằng MySQL, PostgreSQL và SQLite kích hoạt user triggers giống nhau khi FK cascade**; đó là điểm khác biệt theo DBMS.

## 16. Constraint trigger có thể chạy trễ

PostgreSQL có **constraint trigger** dạng AFTER ROW có thể khai báo `DEFERRABLE`:

~~~sql
-- Mau khai bao, can ten/bang/ham thuc te de chay:
CREATE CONSTRAINT TRIGGER constraint_name
AFTER INSERT OR UPDATE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_constraint_function();
~~~

Trong trạng thái deferred, thời điểm thực thi có thể được lùi tới lúc kiểm tra constraint, ví dụ **trước COMMIT**, chứ không nhất thiết cuối statement như AFTER trigger thông thường.

~~~text
BEGIN
  INSERT/UPDATE
  ... cac statement khac ...
  SET CONSTRAINTS ... IMMEDIATE (neu duoc yeu cau)
  hoac COMMIT
       -> kiem tra constraint deferred
~~~

**Chi tiết quan trọng:** mệnh đề `WHEN` của constraint trigger trong PostgreSQL được đánh giá **tại thời điểm sự kiện hàng xảy ra**, để quyết định có xếp sự kiện chờ hay không; bản thân phép kiểm tra WHEN không bị dời tới COMMIT.

Không áp dụng thứ tự alphabet của trigger cùng loại thành lời hứa rằng **constraint trigger deferred** phải chạy trước mọi `AFTER STATEMENT` trigger trong cùng transaction.

## 17. Trigger cấp statement với transition tables

Một `FOR EACH ROW` trigger ghi log từng hàng có thể tốn chi phí khi cập nhật rất nhiều hàng. PostgreSQL hỗ trợ **transition tables** cho một số AFTER triggers để truy cập tập hàng cũ và mới của statement.

### 17.1. Bảng giá và bảng audit riêng

~~~sql
CREATE TABLE lab_t354_prices (
    item_id INTEGER PRIMARY KEY,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
);

INSERT INTO lab_t354_prices(item_id, price)
VALUES (101, 100.00), (102, 200.00), (103, 300.00);

CREATE TABLE lab_t354_price_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id INTEGER NOT NULL,
    old_price NUMERIC(12, 2) NOT NULL,
    new_price NUMERIC(12, 2) NOT NULL
);
~~~

### 17.2. Hàm ghi audit theo tập

~~~sql
CREATE OR REPLACE FUNCTION lab_t354_audit_price_statement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO lab_t354_price_audit (
        item_id, old_price, new_price
    )
    SELECT
        n.item_id,
        o.price,
        n.price
    FROM new_rows AS n
    JOIN old_rows AS o USING (item_id)
    WHERE o.price IS DISTINCT FROM n.price;

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER lab_t354_price_after_update
AFTER UPDATE ON lab_t354_prices
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION lab_t354_audit_price_statement();
~~~

`old_rows` và `new_rows` là **transition relations do PostgreSQL cung cấp** cho trigger, không phải bảng thường trực bạn tự tạo.

### 17.3. Thử UPDATE hai hàng

~~~sql
BEGIN;

UPDATE lab_t354_prices
SET price = price + 10
WHERE item_id IN (101, 103);

SELECT item_id, old_price, new_price
FROM lab_t354_price_audit
ORDER BY audit_id;

ROLLBACK;
~~~

Kết quả trong transaction:

| item_id | old_price | new_price |
| ---: | ---: | ---: |
| 101 | 100.00 | 110.00 |
| 103 | 300.00 | 310.00 |

Function trigger chạy **một lần** cho statement, nhưng câu `INSERT ... SELECT` có thể ghi nhiều hàng audit.

### 17.4. Giới hạn cần biết

- Transition tables có quy tắc chỉ hỗ trợ những dạng **AFTER** trigger phù hợp trong PostgreSQL, không phải cú pháp chung của mọi DBMS.
- `AFTER UPDATE` dùng transition relations **không được kết hợp** danh sách cột `UPDATE OF ...` theo những giới hạn của PostgreSQL.
- Statement trigger có thể chạy khi statement ảnh hưởng **0 hàng**; transition table lúc đó có thể rỗng.
- `JOIN USING(item_id)` trong ví dụ dựa vào **khóa item_id không đổi**. Nếu cập nhật cả khóa ghép, old/new có thể không nối được; phải thiết kế so sánh khác.
- Có quy tắc riêng cho hành động khóa ngoại, partitions và các statement phức tạp; không suy diễn từ ba hàng mẫu cho mọi cấu trúc.

## 18. INSERT ON CONFLICT, MERGE và TRUNCATE

### 18.1. INSERT ... ON CONFLICT DO UPDATE

~~~sql
-- Mau PostgreSQL:
INSERT INTO some_table(id, value_col)
VALUES (101, 'new value')
ON CONFLICT (id) DO UPDATE
SET value_col = EXCLUDED.value_col;
~~~

Không nên suy từ từ khóa đầu `INSERT` rằng **chỉ INSERT triggers được kích hoạt**. Trên PostgreSQL, xử lý `ON CONFLICT DO UPDATE` có thể kéo theo **INSERT và UPDATE triggers** ở những giai đoạn tương ứng, kể cả các statement-level triggers. `BEFORE INSERT ROW` có thể chỉnh hàng đề xuất chèn, ảnh hưởng tới dữ liệu trong `EXCLUDED` của nhánh UPDATE.

### 18.2. MERGE

`MERGE` có các nhánh INSERT/UPDATE/DELETE theo điều kiện khớp. Các trigger liên quan phụ thuộc **nhánh hành động thực tế**, cấp statement và phiên bản hệ quản trị. Không đếm số lượt trigger chỉ bằng số `WHEN` trong SQL.

### 18.3. TRUNCATE khác DELETE

`TRUNCATE` của PostgreSQL **không kích hoạt DELETE ROW trigger trên từng hàng**. Nó có sự kiện `TRUNCATE` riêng với trigger cấp statement. Vì vậy:

~~~sql
TRUNCATE TABLE lab_t354_gate;
~~~

không tương đương `DELETE FROM lab_t354_gate` nếu nghiệp vụ phụ thuộc DELETE ROW audit. **Không chạy TRUNCATE trên dữ liệu quan trọng** chỉ để thử trigger; hãy xem quy tắc khóa và transaction của nó.

## 19. Quan sát metadata, log và độ sâu

### 19.1. Liệt kê user triggers hiện có

~~~sql
SELECT
    tgname AS trigger_name,
    tgenabled AS enabled_mode,
    pg_get_triggerdef(oid) AS trigger_definition
FROM pg_trigger
WHERE tgrelid = 'lab_t354_items'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

`pg_trigger` là system catalog PostgreSQL. Điều kiện `NOT tgisinternal` lọc bớt internal triggers; những quy tắc FK/internal trigger vẫn có thể ảnh hưởng thao tác dù không nằm trong danh sách trên.

### 19.2. RAISE NOTICE theo ngữ cảnh trigger

~~~sql
RAISE NOTICE
    'trigger=%, event=%, level=%, depth=%',
    TG_NAME, TG_OP, TG_LEVEL, pg_trigger_depth();
~~~

Thích hợp quan sát trong môi trường thử. Không ghi log từng hàng rất lớn hoặc in dữ liệu nhạy cảm một cách không kiểm soát trong production.

### 19.3. EXPLAIN ANALYZE thực thi lệnh

~~~sql
BEGIN;

EXPLAIN ANALYZE
UPDATE lab_t354_items
SET quantity = quantity + 1
WHERE item_id = 101;

ROLLBACK;
~~~

`EXPLAIN ANALYZE UPDATE` **thực thi UPDATE và các trigger thật**; transaction trong ví dụ giúp hoàn tác thay đổi cơ sở dữ liệu thử. `EXPLAIN` không `ANALYZE` chỉ mô tả kế hoạch dự kiến.

### 19.4. Trigger dây chuyền có thể gây chờ khóa và deadlock

Giao dịch A UPDATE bảng X rồi trigger ghi Y. Giao dịch B lại UPDATE Y rồi trigger ghi X. Nếu cả hai giữ khóa theo thứ tự đối nghịch, chúng có thể **chờ lẫn nhau**, gây deadlock.

Giảm rủi ro bằng cách:

- Lập sơ đồ những bảng được trigger sửa, không chỉ bảng mà ứng dụng ghi trực tiếp.
- Giữ transaction ngắn.
- Chọn thứ tự khóa/cập nhật nhất quán khi cần.
- Tránh trigger truy vấn lớn cho từng hàng.
- Thiết kế rollback và retry cho lỗi deadlock/serialization phù hợp.

PostgreSQL có thể dùng `pg_stat_activity`, `pg_locks` và `pg_blocking_pids(...)` để điều tra các phiên bị chặn khi được cấp quyền thích hợp.

### 19.5. Tạm tắt trigger không phải cách sửa thiết kế

~~~sql
-- CHI MINH HOA; KHONG CHAY TREN PRODUCTION.
ALTER TABLE lab_t354_items
DISABLE TRIGGER lab_t354_after_row;

ALTER TABLE lab_t354_items
ENABLE TRIGGER lab_t354_after_row;
~~~

Tắt trigger audit có thể tạo **lỗ hổng lịch sử thay đổi**; tắt internal triggers/ràng buộc có thể có hạn chế quyền và hậu quả toàn vẹn dữ liệu. Nếu có vòng đệ quy, hãy sửa **nguyên nhân và điểm dừng**, không tắt trigger để che lỗi rồi quên bật lại.

## 20. Khác biệt giữa các SQL dialect

Quy tắc **thứ tự, cấp độ và đệ quy** là nơi chuyển DBMS dễ gây lỗi. Không dịch nguyên từng dòng PL/pgSQL sang các hệ khác rồi mặc định hành vi giống nhau.

### 20.1. PostgreSQL

PostgreSQL hỗ trợ:

- `BEFORE` và `AFTER` triggers cấp **ROW** hoặc **STATEMENT**.
- `INSTEAD OF` trên view trong ngữ cảnh được phép.
- Nhiều trigger **cùng loại** được gọi **theo tên alphabet**.
- `OLD`, `NEW`, `TG_OP`, `TG_NAME`, `TG_WHEN`, `TG_LEVEL` và `pg_trigger_depth()`.
- `WHEN`, `UPDATE OF`, transition tables và constraint trigger deferrable theo các điều kiện tương ứng.
- Nested DML trong trigger function có thể kích hoạt thêm trigger và gây recursion nếu không có điều kiện dừng.

### 20.2. MySQL

MySQL có các DML triggers `BEFORE`/`AFTER` cho `INSERT`/`UPDATE`/`DELETE` theo **hàng**; không có DML `FOR EACH STATEMENT` trigger tương đương PostgreSQL trong các phiên bản thông dụng.

~~~sql
-- MySQL minh hoa; DELIMITER la lenh cua client.
DELIMITER //
CREATE TRIGGER demo_mysql_before_update
BEFORE UPDATE ON items
FOR EACH ROW
BEGIN
    SET NEW.item_code = UPPER(TRIM(NEW.item_code));
END//
DELIMITER ;
~~~

MySQL hỗ trợ nhiều trigger cùng thời điểm/sự kiện, với **`FOLLOWS`/`PRECEDES`** trong phiên bản hỗ trợ; mặc định liên quan tới **thứ tự tạo** thay vì quy tắc alphabet của PostgreSQL.

MySQL có hạn chế quan trọng: trigger/stored function không được **sửa một bảng đang được sử dụng bởi statement đã kích hoạt** trong một số tình huống; mẫu tự UPDATE cùng bảng có thể bị từ chối thay vì lặp như PostgreSQL.

**Hành động FOREIGN KEY CASCADE không kích hoạt user triggers trong MySQL** theo cơ chế FK cascade thông dụng. Không áp dụng kết luận về cascade của PostgreSQL cho MySQL.

### 20.3. SQL Server

SQL Server có DML triggers **cấp statement**. Tập hàng cũ/mới được cung cấp qua bảng giả `deleted` và `inserted`, không phải một bản ghi `NEW` đơn lẻ.

~~~sql
-- SQL Server/T-SQL minh hoa.
CREATE OR ALTER TRIGGER dbo.demo_items_audit
ON dbo.Items
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.ItemAudit(
        item_id, old_qty, new_qty
    )
    SELECT
        i.item_id, d.quantity, i.quantity
    FROM inserted AS i
    JOIN deleted AS d ON d.item_id = i.item_id
    WHERE i.quantity <> d.quantity;
END;
~~~

Nếu một statement UPDATE 50 hàng, `inserted`/`deleted` có thể chứa 50 hàng; trigger không nên giả định chỉ có một hàng.

SQL Server có `AFTER`/`INSTEAD OF` triggers, khả năng thiết lập **FIRST/LAST** cho một số trigger bằng `sp_settriggerorder`, còn thứ tự giữa các trigger không được định rõ thì không nên dựa vào. Nested/recursive triggers chịu ảnh hưởng các cấu hình như `RECURSIVE_TRIGGERS`, `nested triggers` và giới hạn độ sâu của SQL Server.

### 20.4. Oracle Database

Oracle PL/SQL hỗ trợ trigger cấp row/statement, `BEFORE`/`AFTER`, và **compound triggers**:

~~~sql
-- Oracle PL/SQL minh hoa.
CREATE OR REPLACE TRIGGER demo_oracle_before_update
BEFORE UPDATE ON items
FOR EACH ROW
BEGIN
    :NEW.item_code := UPPER(TRIM(:NEW.item_code));
END;
/
~~~

Oracle dùng `:OLD`/`:NEW` cho row triggers. Thứ tự nhiều trigger cùng loại có thể được định nghĩa bằng quan hệ **`FOLLOWS`** trong ngữ cảnh được hỗ trợ; không suy theo alphabet tên như PostgreSQL.

Oracle có vấn đề **mutating table**: row trigger cố đọc/sửa chính bảng đang bị statement DML tác động trong trường hợp bị cấm có thể gặp lỗi `ORA-04091`. Compound trigger hoặc xử lý ở phần statement có thể giúp thiết kế lại.

`PRAGMA AUTONOMOUS_TRANSACTION` tạo một ngữ cảnh giao dịch riêng trong những trường hợp được dùng đúng cách; không phải hành vi mặc định của mọi trigger Oracle. Dùng sai có thể phá kỳ vọng rollback cùng nhau.

### 20.5. SQLite

SQLite có `BEFORE`, `AFTER` và `INSTEAD OF` trên view trong các trường hợp phù hợp; trigger DML thực thi theo **hàng**, không có mô hình statement trigger tương đương PostgreSQL.

~~~sql
-- SQLite minh hoa.
CREATE TRIGGER demo_sqlite_items_audit
AFTER UPDATE ON items
FOR EACH ROW
WHEN OLD.quantity IS NOT NEW.quantity
BEGIN
    INSERT INTO item_audit(
        item_id, old_qty, new_qty
    )
    VALUES(
        NEW.item_id, OLD.quantity, NEW.quantity
    );
END;
~~~

SQLite có `PRAGMA recursive_triggers` liên quan tới trigger đệ quy và giới hạn độ sâu. Không có bảo đảm chung **“các trigger cùng loại chạy theo alphabet”** như PostgreSQL.

Các thao tác BEFORE trigger cố sửa/xóa hàng đang bị statement ngoài tác động có giới hạn/hành vi đặc thù; không dùng cú pháp gán `NEW.column := ...` của PL/pgSQL như thể SQLite hỗ trợ giống hệt.

### 20.6. Bảng so sánh

| Nội dung | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| DML trigger cấp hàng | Có | Có | Tập inserted/deleted, không giống row trigger PostgreSQL | Có | Có |
| DML trigger cấp statement | Có | Không tương đương | **Có** | Có | Không tương đương |
| Thứ tự cùng loại | **Tên alphabet** | FOLLOWS/PRECEDES, mặc định thứ tự tạo | FIRST/LAST có giới hạn, phần còn lại không xác định | FOLLOWS trong trường hợp hỗ trợ | Không dựa vào thứ tự tạo/tên |
| Bản ghi cũ/mới | OLD/NEW | OLD/NEW | deleted/inserted dạng tập | :OLD/:NEW | OLD/NEW |
| Đệ quy | Nested DML, pg_trigger_depth | Có các giới hạn tự sửa bảng | Tùy cấu hình recursive/nested | Có mutating table restrictions | recursive_triggers pragma |
| FK cascade và trigger | Có thể kích hoạt user trigger liên quan | Cascade không kích hoạt user trigger | Theo quy tắc SQL Server | Theo quy tắc Oracle | Theo quy tắc SQLite, cần xác minh |
| Audit theo tập statement | Transition tables | Không cùng cú pháp | inserted/deleted | Compound/statement logic | Không cùng cơ chế |

**Chuyển yêu cầu nghiệp vụ trước, rồi viết trigger theo cơ chế của từng hệ quản trị**, không chỉ đổi từ khóa.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Nhãn dùng mã chưa chuẩn hóa | Trigger tạo nhãn chạy trước bước chuẩn hóa | Xác định thứ tự; tốt hơn là gộp bước phụ thuộc |
| Tin thứ tự CREATE TRIGGER quyết định thứ tự PostgreSQL | PostgreSQL dùng tên alphabet khi trigger cùng loại | Hiểu quy tắc tên và loại |
| Nghĩ mọi trigger trên mọi bảng được sắp alphabet toàn cục | Khác thời điểm, cấp độ, nested statement | Vẽ đồ thị tác động thực tế |
| Có log dù UPDATE 0 hàng | Statement trigger chạy một lần | Phân biệt statement event và row affected |
| UPDATE SET qty = qty vẫn gọi row trigger | UPDATE là sự kiện dù giá trị không đổi | Dùng WHEN OLD/NEW khác nhau |
| Dùng UPDATE OF cột để kiểm tra giá trị khác | UPDATE OF xét cột trong SET | Dùng WHEN với IS DISTINCT FROM |
| BEFORE ROW trả NULL mà không biết | PostgreSQL bỏ qua hàng | RETURN NEW nếu muốn lưu |
| AFTER ROW trả NEW để mong sửa hàng | Return AFTER bị bỏ qua | Dùng BEFORE để sửa NEW |
| AFTER UPDATE tự UPDATE cùng hàng | Đệ quy trực tiếp | Sửa NEW trong BEFORE, không tạo UPDATE thứ hai |
| Trigger A → B → A lặp | Đệ quy gián tiếp thiếu điểm dừng | Trạng thái rõ, event ID duy nhất, luồng một chiều |
| Bỏ nested trigger dựa trên depth > 1 | Chặn cả chuỗi hợp lệ | Dùng depth để debug, guard theo nghiệp vụ |
| Trigger cuối lỗi nhưng mong log trước vẫn lưu | Cùng transaction | Xử lý rollback/exception đúng |
| Trace ID có khoảng trống sau rollback | Sequence không trả lại ID | Không dùng ID liên tiếp làm số event thành công |
| Gửi email trực tiếp trong trigger | HTTP/email không tự rollback | Ghi outbox rồi gửi sau commit |
| TRUNCATE thay DELETE và mất audit hàng | TRUNCATE không gọi DELETE row trigger | Dùng đúng sự kiện |
| Không xét FK CASCADE | DML trên bảng khác có thể kích hoạt trigger khác | Xem đồ thị FK và trigger |
| Giả định nhiều hàng được xử lý theo ID tăng dần | Không có bảo đảm row traversal | Viết logic theo tập |
| Row trigger chạy SELECT lớn cho mỗi hàng | Chi phí N+1 | Transition tables/statement processing |
| Ghép old/new theo khóa đã bị sửa | Không ghép lại được hai bản | Chọn định danh ổn định |
| Tắt trigger để che recursion | Có thể mất audit/khóa ngoại logic | Sửa thiết kế, kiểm soát bật/tắt |
| Đem quy tắc alphabet sang MySQL/Oracle | Các DBMS có thứ tự khác | FOLLOWS/PRECEDES hoặc gộp logic |
| Dùng một hàng inserted trong SQL Server | inserted/deleted là tập | Viết SQL xử lý nhiều hàng |
| Oracle row trigger sửa chính bảng đang mutating | Lỗi ORA-04091 có thể xảy ra | Dùng thiết kế/compound trigger |
| Mang PL/pgSQL NEW.column gán sang SQLite | Cú pháp/semantics khác | Viết theo SQLite, kiểm tra pragma |

## 22. Bài tập thực hành có đáp án

Các bài dựa trên các bảng `lab_t354_*` đã tạo ở trên. Mỗi bài ghi dữ liệu có `BEGIN ... ROLLBACK` để giữ dữ liệu ban đầu. Đoạn đánh dấu **không chạy** là tình huống để phân tích, không phải câu lệnh cần thử trên dữ liệu quan trọng.

### Bài 1 — Thứ tự BEFORE trigger

**Yêu cầu:** UPDATE hàng 101 thành mã `'  note-x  '` và số lượng 6. Trigger nào chạy trước? Nhãn cuối là gì?

**Đáp án:** A chuẩn hóa thành **NOTE-X**, B tính nhãn **NOTE-X:6**, C cập nhật timestamp do giá trị đã đổi.

~~~sql
BEGIN;
UPDATE lab_t354_items
SET item_code = '  note-x  ', quantity = 6
WHERE item_id = 101
RETURNING item_code, quantity, item_label;
ROLLBACK;
~~~

### Bài 2 — ROW và STATEMENT

**Yêu cầu:** một lệnh UPDATE tác động ba hàng. Có một BEFORE UPDATE ROW, một AFTER UPDATE ROW và một AFTER UPDATE STATEMENT, không có WHEN hạn chế.

**Đáp án:** BEFORE ROW **3 lượt**, AFTER ROW **3 lượt**, AFTER STATEMENT **1 lượt** trong trường hợp thông thường. Không suy thứ tự xử lý ba hàng từ giá trị khóa chính.

### Bài 3 — UPDATE 0 hàng

~~~sql
BEGIN;
UPDATE lab_t354_items SET quantity = 9 WHERE item_id = -999;
SELECT trigger_name FROM lab_t354_trace ORDER BY trace_id;
ROLLBACK;
~~~

**Đáp án:** không có row trigger vì không có hàng phù hợp; `lab_t354_after_statement` vẫn có thể ghi một dòng log.

### Bài 4 — BEFORE RETURN NULL

**Yêu cầu:** với bảng `lab_t354_gate`, chèn ba hàng KEEP, SKIP, KEEP.

**Đáp án:** chỉ **hai hàng KEEP** được lưu; hàng SKIP bị BEFORE ROW trả NULL nên không được INSERT.

### Bài 5 — Vì sao AFTER tự UPDATE lại nguy hiểm?

~~~sql
-- KHONG CHAY.
-- Trong AFTER UPDATE trigger:
UPDATE lab_t354_items
SET updated_at = clock_timestamp()
WHERE item_id = NEW.item_id;
~~~

**Đáp án:** UPDATE bên trong có thể **kích hoạt lại chính AFTER UPDATE trigger**, tạo vòng đệ quy. Đặt `NEW.updated_at` trong BEFORE ROW phù hợp thay vì mở UPDATE mới.

### Bài 6 — Chỉ audit khi số lượng thật sự đổi

**Yêu cầu:** viết điều kiện WHEN.

**Đáp án:**

~~~sql
WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)
~~~

Không dùng `UPDATE OF quantity` rồi tưởng nó kiểm tra số lượng khác cũ.

### Bài 7 — Trigger A → B → C

~~~sql
BEGIN;
INSERT INTO lab_t354_orders(
    order_id, customer_code, requested_qty
) VALUES (5001, 'C001', 2);

SELECT stage, trigger_depth
FROM lab_t354_chain_trace
WHERE order_id = 5001
ORDER BY trace_id;
ROLLBACK;
~~~

**Đáp án:** A tạo reservation, B tạo outbox, C ghi trace. Thứ tự **bắt đầu** A → B → C; các dấu hoàn tất xuất hiện **C (depth 3), B (2), A (1)**.

### Bài 8 — pg_trigger_depth

**Yêu cầu:** độ sâu của trigger trực tiếp A và nested C là bao nhiêu?

**Đáp án:** A thường là **1**, C là **3** theo chuỗi của bài, còn `SELECT pg_trigger_depth()` ngoài trigger thông thường là **0**. Độ sâu không tự chứng minh một event hợp lệ hay đã xử lý.

### Bài 9 — Đệ quy gián tiếp

**Tình huống:** AFTER UPDATE A thêm hàng B, AFTER INSERT B lại UPDATE A, cả khi không đổi giá trị.

**Đáp án:** nguy cơ vòng A → B → A. Ngăn bằng **điều kiện chuyển trạng thái thật**, event ID duy nhất, phân luồng một chiều hoặc cơ chế idempotency phù hợp; không đơn thuần tắt trigger B.

### Bài 10 — Rollback chuỗi

**Yêu cầu:** một INSERT orders sinh reservation, outbox và trace, sau đó ROLLBACK.

**Đáp án:** các hàng mới của cả chuỗi **không được lưu**. Sequence identity có thể giữ số đã cấp nên ID lần sau không nhất thiết liên tiếp.

### Bài 11 — TRUNCATE và DELETE

**Câu hỏi:** PostgreSQL `TRUNCATE` có kích hoạt AFTER DELETE FOR EACH ROW cho từng hàng không?

**Đáp án:** **không**. TRUNCATE có sự kiện trigger riêng cấp statement; không tương đương DELETE khi có audit từng hàng.

### Bài 12 — Transition tables

**Yêu cầu:** audit thay đổi giá của nhiều hàng bằng một AFTER statement trigger.

**Đáp án:** dùng:

~~~sql
-- Mau cu phap, can function/bang:
AFTER UPDATE ON some_table
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
~~~

Trong function, viết `INSERT ... SELECT` từ tập `old_rows`/`new_rows`, nối bằng khóa ổn định và chỉ ghi giá thật sự khác. Ví dụ chạy đầy đủ ở mục 17.

### Bài 13 — UPDATE OF

**Câu hỏi:** `AFTER UPDATE OF quantity` có thể kích hoạt khi `SET quantity = quantity` không?

**Đáp án:** **có**, vì quantity được nêu trong `SET`. Nếu cần kiểm tra thay đổi thực, dùng `OLD.quantity IS DISTINCT FROM NEW.quantity`.

### Bài 14 — Constraint trigger deferred

**Câu hỏi:** constraint trigger `DEFERRABLE INITIALLY DEFERRED` có nhất thiết chạy ngay trước AFTER STATEMENT trong cùng lệnh?

**Đáp án:** **không**. Nó có thể được thực thi khi constraint được kiểm tra muộn, ví dụ trước COMMIT. `WHEN` của constraint trigger được đánh giá tại thời điểm sự kiện để quyết định có xếp chờ.

### Bài 15 — Liệt kê trigger

~~~sql
SELECT tgname, pg_get_triggerdef(oid)
FROM pg_trigger
WHERE tgrelid = 'lab_t354_items'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

**Đáp án:** câu lệnh trả tên và định nghĩa user triggers của bảng mẫu, giúp không bỏ sót một trigger đã tạo trước đó.

### Bài 16 — MySQL và PostgreSQL có cùng thứ tự không?

**Đáp án:** **không**. PostgreSQL dùng tên alphabet cho trigger cùng loại. MySQL có quy tắc mặc định liên quan thứ tự tạo và hỗ trợ `FOLLOWS`/`PRECEDES` theo phiên bản. Không viết logic phụ thuộc tên khi chuyển MySQL.

### Bài 17 — SQL Server UPDATE 50 hàng

**Câu hỏi:** AFTER UPDATE trigger của SQL Server được gọi 50 lần, mỗi lần một hàng?

**Đáp án:** **không** theo mô hình DML trigger SQL Server. Nó chạy ở **cấp statement** và hai bảng giả `inserted`/`deleted` có thể chứa 50 hàng. Function phải xử lý theo tập.

### Bài 18 — Oracle mutating table

**Câu hỏi:** row trigger Oracle cố đọc hoặc sửa chính bảng đang được DML cập nhật có rủi ro gì?

**Đáp án:** có thể gặp **ORA-04091** do mutating table trong ngữ cảnh bị cấm. Cân nhắc compound trigger/statement-level logic hoặc thiết kế khác theo Oracle.

### Bài 19 — Vì sao cần outbox?

**Tình huống:** trigger gửi email thành công, transaction database sau đó rollback.

**Đáp án:** email đã gửi **không tự được thu hồi**. Một outbox row được chèn trong cùng transaction và worker gửi sau commit thường phù hợp hơn; worker phải có retry và idempotency.

### Bài 20 — Chọn trigger

| Nhiệm vụ | Lựa chọn PostgreSQL |
| --- | --- |
| Chuẩn hóa mã trước ghi | `BEFORE INSERT/UPDATE FOR EACH ROW`, sửa `NEW` |
| Audit giá trị OLD/NEW sau UPDATE | `AFTER UPDATE FOR EACH ROW` với WHEN khi cần |
| Audit toàn bộ tập hàng của statement | `AFTER UPDATE FOR EACH STATEMENT` + transition tables |
| Thay thao tác ghi lên view | `INSTEAD OF` row trigger trên view trong ngữ cảnh phù hợp |

## 23. Ghi nhớ

| Câu hỏi | Nguyên tắc |
| --- | --- |
| BEFORE ROW có thể làm gì? | Chỉnh `NEW`; `RETURN NULL` có thể bỏ qua hàng |
| AFTER ROW có dùng RETURN NEW để sửa hàng không? | **Không**, giá trị RETURN của AFTER bị bỏ qua |
| STATEMENT trigger chạy khi UPDATE 0 hàng không? | **Có thể có**, không cần hàng phù hợp |
| Trigger cùng loại trong PostgreSQL theo thứ tự nào? | **Tên alphabet**, không theo thứ tự CREATE |
| Thứ tự xử lý nhiều hàng có bảo đảm? | **Không** |
| UPDATE OF có nghĩa giá trị cột đã đổi? | **Không**, chỉ xét cột được nêu trong SET |
| AFTER tự UPDATE lại cùng hàng gây gì? | Nguy cơ **đệ quy trực tiếp** |
| A → B → A là gì? | **Đệ quy gián tiếp** |
| Tránh recursion thế nào? | Điều kiện chuyển trạng thái, luồng một chiều, khóa sự kiện/idempotency, BEFORE NEW |
| `pg_trigger_depth()` để làm gì? | Quan sát **độ sâu lồng nhau**, không phải điểm dừng chung |
| Lỗi cuối chuỗi có làm câu gốc thất bại? | Có thể làm **toàn statement/transaction rollback** |
| TRUNCATE có gọi DELETE ROW trigger? | **Không** trên PostgreSQL |
| FK CASCADE liên quan trigger không? | Có thể, nhưng **khác nhau theo DBMS** |
| Constraint trigger deferred có chạy ngay không? | Có thể được **trì hoãn** đến lúc kiểm tra constraint |
| Audit theo tập thế nào? | Transition tables trong AFTER STATEMENT PostgreSQL khi phù hợp |
| SQL Server có NEW của một hàng duy nhất? | Dùng tập **inserted/deleted** |
| MySQL có thứ tự alphabet như PostgreSQL? | **Không** |
| Oracle cần cảnh giác gì? | **Mutating table** và thứ tự trigger |
| SQLite có recursion không? | Có cấu hình `recursive_triggers` và quy tắc riêng |

**Kết luận:** hãy nhìn một câu SQL có trigger như **một đồ thị tác động**, không chỉ là thao tác trên một bảng. Xác định **thời điểm và cấp độ từng trigger**, sự phụ thuộc thứ tự, chuỗi **A → B → C**, khả năng có đường quay lại A, và **điểm dừng dựa trên nghiệp vụ**. Trigger giúp tự động hóa và duy trì tính nhất quán khi được thiết kế có kiểm soát; thiếu hiểu biết về thứ tự, recursion và transaction có thể biến chúng thành nguồn lỗi khó tìm của hệ thống SQL.
