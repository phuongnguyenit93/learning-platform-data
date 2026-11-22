# Gán giá trị, SELECT INTO, FOUND và GET DIAGNOSTICS trong PL/pgSQL

## 1. Vì sao bốn kỹ thuật này phải được học cùng nhau?

Trong PL/pgSQL, một thao tác nghiệp vụ thường có chuỗi bước:

1. Đọc dữ liệu từ bảng vào biến.
2. Kiểm tra có tìm thấy hàng hay không.
3. Thực hiện INSERT, UPDATE hoặc DELETE.
4. Xác định có bao nhiêu hàng thực sự bị tác động.
5. Ghi nhật ký hoặc xử lý ngoại lệ bằng thông tin chẩn đoán.

Ví dụ: API yêu cầu thay đổi trạng thái một đơn hàng. Nếu đơn không tồn tại, hệ thống phải trả tình trạng khác với khi đơn đã ở trạng thái cần thay đổi. Nếu có lỗi UNIQUE hoặc FOREIGN KEY, cần ghi đúng SQLSTATE nhưng không để lộ dữ liệu nhạy cảm.

Bốn công cụ thường xuyên xuất hiện:

- **Phép gán `:=`:** tính một biểu thức và lưu vào biến PL/pgSQL.
- **`SELECT ... INTO`:** đọc kết quả câu SQL vào biến, record hoặc row variable.
- **`FOUND`:** biến boolean đặc biệt cho biết một số câu lệnh vừa xử lý có tìm thấy hoặc tác động hàng nào hay không.
- **`GET DIAGNOSTICS`:** lấy thông tin của lệnh SQL gần nhất như `ROW_COUNT`; trong khối `EXCEPTION` dùng **`GET STACKED DIAGNOSTICS`** để lấy nguyên nhân lỗi.

**Điểm then chốt:** `FOUND` không đồng nghĩa “câu SQL vừa chạy thành công”; `ROW_COUNT` không đồng nghĩa “tổng số hàng khớp điều kiện nghiệp vụ”; `SELECT INTO` của PL/pgSQL **không phải** câu SQL tạo bảng có cùng cụm từ.

### 1.1. Mục tiêu

Sau bài học, bạn có thể:

- Viết khối `DECLARE ... BEGIN ... END` và gán đúng kiểu dữ liệu.
- Phân biệt `:=`, `SELECT INTO`, `PERFORM`, `RETURNING INTO`.
- Giải thích kết quả khi query trả **0, 1, nhiều hàng**, có/không có `STRICT`.
- Sử dụng `FOUND` mà không bị thay đổi ngoài ý muốn bởi lệnh SQL kế tiếp.
- Đọc `ROW_COUNT` kiểu `bigint` ngay sau INSERT/UPDATE/DELETE và dynamic `EXECUTE`.
- Phân biệt `GET CURRENT DIAGNOSTICS` với `GET STACKED DIAGNOSTICS`.
- Xử lý `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `unique_violation` và dùng `SQLSTATE` an toàn.
- Phân tích tác động của `FOR`, `FETCH`, `RETURN QUERY`, function calls và các lệnh không làm thay đổi `FOUND`.
- Thiết kế hàm trả kết quả nhất quán, an toàn với transaction và concurrency.
- Thực hành với SQL lab và bài tập có lời giải.

### 1.2. Ví dụ tổng quan

~~~sql
CREATE OR REPLACE FUNCTION demo_lookup(p_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
    v_found boolean;
    v_rows bigint;
BEGIN
    SELECT customer_name
      INTO v_name
      FROM some_schema.customers
     WHERE customer_id = p_id;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF NOT v_found THEN
        RETURN 'Không tìm thấy';
    END IF;

    RETURN format('Đã tìm thấy: %s; rows=%s', v_name, v_rows);
END;
$$;
~~~

Đây là mã **minh họa cấu trúc**, chưa chạy được nếu chưa có bảng `some_schema.customers`. Lab đầy đủ sẽ được tạo ở phần sau.

---

## 2. Khối PL/pgSQL và phạm vi biến

### 2.1. Cấu trúc cơ bản

~~~sql
DO $$
DECLARE
    v_counter integer := 0;
    v_message text DEFAULT 'Bắt đầu';
BEGIN
    v_counter := v_counter + 1;
    RAISE NOTICE '% / %', v_message, v_counter;
END;
$$ LANGUAGE plpgsql;
~~~

`DO` chạy một **khối PL/pgSQL vô danh** một lần. Khi viết stored function/procedure, phần thân cũng có thể có `DECLARE` và `BEGIN...END` nhưng có khai báo tham số và kiểu trả về.

~~~text
DO / FUNCTION / PROCEDURE
  |
  +-- DECLARE: khai báo biến, kiểu, giá trị khởi tạo
  |
  +-- BEGIN: thực thi tuần tự
  |     |
  |     +-- Gán biến / SELECT INTO / SQL / IF / LOOP
  |     |
  |     +-- GET DIAGNOSTICS / RAISE / RETURN
  |
  +-- EXCEPTION: nhánh bắt lỗi, nếu có
  |
  +-- END;
~~~

### 2.2. Hai chữ BEGIN có nghĩa khác nhau

- `BEGIN` của khối PL/pgSQL bắt đầu **khối lệnh**.
- `BEGIN;` ở SQL ngoài function mở **transaction**.

Không suy ra mỗi khối PL/pgSQL có một transaction riêng. Trong một function bình thường, các SQL statements tham gia transaction hiện tại của caller.

### 2.3. Khai báo biến và giá trị mặc định

~~~sql
DO $$
DECLARE
    v_id bigint;
    v_amount numeric(12,2) := 100.50;
    v_status text DEFAULT 'open';
    v_enabled boolean := true;
    v_today date := CURRENT_DATE;
BEGIN
    RAISE NOTICE 'id=%, amount=%, status=%, enabled=%, today=%',
        v_id, v_amount, v_status, v_enabled, v_today;
END $$;
~~~

Nếu không gán mặc định, biến thông thường được khởi tạo là **NULL**. Khai báo có `DEFAULT` và `:=` đều có thể đặt biểu thức khởi tạo. Với một số cú pháp khai báo, `=` cũng được chấp nhận khi khởi tạo.

### 2.4. Biểu thức khởi tạo được đánh giá khi vào block

~~~sql
DO $$
DECLARE
    v_started_at timestamptz := clock_timestamp();
BEGIN
    RAISE NOTICE 'Started at %', v_started_at;
END $$;
~~~

Biểu thức được đánh giá khi block được vào (trong context thực thi tương ứng), không phải một lần cố định lúc function được định nghĩa. Với biến `CONSTANT`, giá trị không được gán lại.

### 2.5. Biến kiểu gắn với bảng

~~~sql
DO $$
DECLARE
    v_customer_id bigint;
    v_row record;
BEGIN
    v_customer_id := 101;
    RAISE NOTICE 'ID %', v_customer_id;
END $$;
~~~

Phần sau sẽ minh họa `%TYPE`, `%ROWTYPE` và `record` sau khi tạo schema lab để có bảng cụ thể.

---

## 3. Phép gán `:=` và biểu thức bên phải

### 3.1. Cú pháp quen thuộc

~~~sql
DO $$
DECLARE
    v_number integer := 4;
    v_label text := 'Đơn hàng';
BEGIN
    v_number := v_number + 6;
    v_label := v_label || ' #' || v_number::text;

    RAISE NOTICE '%, kết quả=%', v_label, v_number;
END $$;
~~~

`:=` là phép gán trong PL/pgSQL. PostgreSQL cũng hỗ trợ cú pháp `=` cho một phép gán PL/pgSQL ở những vị trí hợp lệ; dùng `:=` thường làm code dễ phân biệt hơn với phép so sánh SQL `=`.

### 3.2. Gán khác so sánh

~~~sql
v_status := 'paid';  -- gán
~~~

Trong điều kiện:

~~~sql
IF v_status = 'paid' THEN
    RAISE NOTICE 'Đã thanh toán';
END IF;
~~~

`=` ở `IF` là **toán tử so sánh**, trả boolean (hoặc NULL nếu SQL NULL tham gia theo quy tắc). Không viết `IF v_status := 'paid' THEN` rồi nghĩ rằng đó là so sánh.

### 3.3. Biến có kiểu xác định, có kiểm tra và chuyển đổi kiểu

~~~sql
DO $$
DECLARE
    v_total numeric(12,2);
    v_text text := '18.50';
BEGIN
    v_total := v_text::numeric;
    RAISE NOTICE 'Total %', v_total;
END $$;
~~~

PL/pgSQL có các quy tắc ép kiểu/assignment cast; không nên dựa vào ép kiểu ngầm giữa input user và các kiểu dữ liệu nhạy cảm như tiền tệ, ID hoặc timestamp. Khi chuyển đổi không hợp lệ, câu lệnh có thể báo lỗi (ví dụ `invalid_text_representation`).

### 3.4. Gán bằng biểu thức SQL và scalar subquery

~~~sql
DO $$
DECLARE
    v_count integer;
BEGIN
    v_count := (SELECT COUNT(*)::integer FROM pg_catalog.pg_class);
    RAISE NOTICE 'Số relation trong catalog: %', v_count;
END $$;
~~~

PL/pgSQL hỗ trợ đánh giá biểu thức SQL ở vế phải. Tuy nhiên nếu mục tiêu là **đọc một hoặc nhiều cột từ một truy vấn** và kiểm soát 0/1/nhiều rows, `SELECT ... INTO [STRICT]` thường rõ ràng hơn.

### 3.5. NULL trong phép gán

~~~sql
DO $$
DECLARE
    v_a integer := NULL;
    v_b integer;
BEGIN
    v_b := v_a + 1; -- kết quả NULL

    RAISE NOTICE 'v_b=%', v_b;
    IF v_b IS NULL THEN
        RAISE NOTICE 'Phép toán với NULL không tạo số mới';
    END IF;
END $$;
~~~

`NULL` là “không có giá trị đã biết”, không phải số 0 hay chuỗi rỗng.

### 3.6. COALESCE khi muốn giá trị mặc định

~~~sql
v_total := COALESCE(v_total, 0);
~~~

Dùng `COALESCE` khi nghiệp vụ **thật sự** coi NULL là 0. Không thay mọi NULL thành 0 một cách tự động, vì có thể xóa mất phân biệt “chưa biết” và “không phát sinh”.

---

## 4. PL/pgSQL `SELECT ... INTO` không tạo bảng

### 4.1. Hai ngữ cảnh cùng dùng chữ INTO

Trong PL/pgSQL:

~~~sql
SELECT customer_name
INTO v_customer_name
FROM app.customers
WHERE customer_id = 101;
~~~

Nghĩa là **gán giá trị query vào biến PL/pgSQL**.

Trong SQL thông thường, cú pháp lịch sử:

~~~sql
SELECT *
INTO new_table
FROM old_table;
~~~

có nghĩa tạo bảng mới từ SELECT. Cú pháp tạo bảng nên viết rõ:

~~~sql
CREATE TABLE new_table AS
SELECT * FROM old_table;
~~~

**Trong function PL/pgSQL**, `SELECT ... INTO` được phân tích theo cú pháp PL/pgSQL dành cho **biến**, không dùng nó để tạo bảng. Nếu cần tạo bảng trong function, dùng `CREATE TABLE ... AS SELECT ...` theo điều kiện DDL được phép.

### 4.2. Các vị trí hợp lệ của INTO

Một cách thường đọc:

~~~sql
SELECT expression_list
INTO target_list
FROM ...
WHERE ...;
~~~

PostgreSQL PL/pgSQL có thể chấp nhận `INTO` ở các vị trí khác nhau trong statement SELECT, nhưng đặt gần SELECT list hoặc vị trí chuẩn đang dùng trong đội giúp mã dễ đọc. Các ví dụ của bài dùng dạng:

~~~sql
SELECT ...
  INTO ...
  FROM ...;
~~~

### 4.3. Một biến

~~~sql
DO $$
DECLARE
    v_database text;
BEGIN
    SELECT current_database()
      INTO v_database;

    RAISE NOTICE 'Database: %', v_database;
END $$;
~~~

`SELECT current_database()` luôn tạo một hàng khi chạy thành công; biến được gán một string.

### 4.4. Nhiều biến

~~~sql
DO $$
DECLARE
    v_user text;
    v_schema text;
BEGIN
    SELECT current_user, current_schema()
      INTO v_user, v_schema;

    RAISE NOTICE 'User=%; schema=%', v_user, v_schema;
END $$;
~~~

Số lượng và kiểu cột trả về cần tương thích target variables. Dùng tên biến nhất quán để không bị nhầm giữa SQL column và PL/pgSQL variable.

### 4.5. SELECT INTO không nhất thiết trả một hàng

Nếu WHERE không đủ chọn lọc, câu SELECT có thể tạo 0, 1 hoặc nhiều rows. **Không STRICT**, PL/pgSQL chỉ gán **hàng đầu tiên mà executor trả** và bỏ các hàng sau khi đạt mục tiêu tương ứng. Không có `ORDER BY`, “hàng đầu tiên” không được bảo đảm ổn định theo khóa nghiệp vụ.

Đây là khác biệt lớn với nhiều đoạn code giả định:

> “SELECT INTO biến scalar chắc chắn báo lỗi nếu query có hai hàng.”

Điều đó **không đúng nếu không có STRICT** đối với SELECT. Muốn bắt trường hợp nhiều rows, dùng `INTO STRICT`.

### 4.6. SELECT có output nhưng không có INTO

Trong PL/pgSQL, câu:

~~~sql
SELECT 1;
~~~

trong block thường báo lỗi **query has no destination for result data**. Nếu bạn muốn bỏ kết quả nhưng vẫn chạy query, dùng `PERFORM`:

~~~sql
PERFORM 1;
~~~

Nếu muốn trả kết quả cho caller, dùng `RETURN QUERY` trong set-returning function hoặc câu lệnh RETURN phù hợp.

---

## 5. Dữ liệu thực hành thống nhất

Các câu SQL trong phần này tạo một schema độc lập. Đảm bảo chạy **một lần trên database thử nghiệm**, có quyền `CREATE` và thao tác bảng phù hợp. Không dùng schema production có tên giống.

### 5.1. Tạo schema

~~~sql
CREATE SCHEMA IF NOT EXISTS pl_diag_lab;
~~~

### 5.2. Tạo khách hàng

~~~sql
CREATE TABLE pl_diag_lab.customers (
    customer_id bigint PRIMARY KEY,
    customer_code text NOT NULL UNIQUE,
    customer_name text NOT NULL,
    customer_status text NOT NULL
        CHECK (customer_status IN ('active', 'inactive'))
);
~~~

### 5.3. Tạo đơn hàng

~~~sql
CREATE TABLE pl_diag_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES pl_diag_lab.customers(customer_id),
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    order_status text NOT NULL
        CHECK (order_status IN ('new','paid','canceled')),
    created_at timestamptz NOT NULL
);
~~~

### 5.4. Nạp dữ liệu mẫu

~~~sql
INSERT INTO pl_diag_lab.customers
    (customer_id, customer_code, customer_name, customer_status)
VALUES
    (101, 'C101', 'An', 'active'),
    (102, 'C102', 'Bình', 'active'),
    (103, 'C103', 'Chi', 'inactive');

INSERT INTO pl_diag_lab.orders
    (order_id, customer_id, amount, order_status, created_at)
VALUES
    (1001, 101, 250.00, 'new',      '2026-11-01 09:00:00+00'),
    (1002, 101, 125.50, 'paid',     '2026-11-02 10:00:00+00'),
    (1003, 102, 300.00, 'new',      '2026-11-03 11:00:00+00'),
    (1004, 102, 450.00, 'canceled', '2026-11-04 12:00:00+00'),
    (1005, 103, 100.00, 'new',      '2026-11-05 13:00:00+00');
~~~

### 5.5. Dữ liệu cơ sở để đọc kết quả

| Customer ID | Tên | Trạng thái | Số đơn |
|---:|---|---|---:|
| 101 | An | active | 2 |
| 102 | Bình | active | 2 |
| 103 | Chi | inactive | 1 |

| Order ID | Customer | Amount | Status |
|---:|---:|---:|---|
| 1001 | 101 | 250.00 | new |
| 1002 | 101 | 125.50 | paid |
| 1003 | 102 | 300.00 | new |
| 1004 | 102 | 450.00 | canceled |
| 1005 | 103 | 100.00 | new |

Nếu chạy nhiều lần `INSERT` với cùng primary keys, lần sau sẽ gặp lỗi unique. Để làm lại từ đầu, sử dụng database/schema lab mới hoặc dọn đối tượng **đã xác nhận chỉ thuộc lab** với quy trình riêng.

---

## 6. `%TYPE`, `%ROWTYPE` và `record`

### 6.1. `%TYPE`: biến có kiểu của cột

~~~sql
DO $$
DECLARE
    v_name pl_diag_lab.customers.customer_name%TYPE;
    v_amount pl_diag_lab.orders.amount%TYPE;
BEGIN
    v_name := 'Ví dụ';
    v_amount := 199.90;
    RAISE NOTICE 'name=%, amount=%', v_name, v_amount;
END $$;
~~~

Dùng `%TYPE` giúp biến phản ánh kiểu cột ở schema tương ứng, giảm nguy cơ định nghĩa local variable không khớp kiểu dữ liệu. Nếu kiểu cột thay đổi, việc biên dịch lại function/validation vẫn cần được xem xét; `%TYPE` không loại bỏ mọi rủi ro migration.

### 6.2. `%ROWTYPE`: nhận cả hàng với cấu trúc đã biết

~~~sql
DO $$
DECLARE
    v_customer pl_diag_lab.customers%ROWTYPE;
BEGIN
    SELECT *
      INTO v_customer
      FROM pl_diag_lab.customers
     WHERE customer_id=101;

    RAISE NOTICE 'ID=%, tên=%',
        v_customer.customer_id,
        v_customer.customer_name;
END $$;
~~~

`%ROWTYPE` có các field tương ứng với cấu trúc bảng. Nếu query chọn một cấu trúc khác, việc gán vào row variable có thể gặp lỗi không tương thích.

### 6.3. `record`: hình dạng được xác định bởi kết quả

~~~sql
DO $$
DECLARE
    v_result record;
BEGIN
    SELECT
        c.customer_name AS name,
        COUNT(o.order_id) AS orders_count
    INTO v_result
    FROM pl_diag_lab.customers AS c
    LEFT JOIN pl_diag_lab.orders AS o
      ON o.customer_id = c.customer_id
    WHERE c.customer_id=101
    GROUP BY c.customer_name;

    RAISE NOTICE 'name=%, orders=%',
        v_result.name, v_result.orders_count;
END $$;
~~~

`record` không gắn cứng với một rowtype cụ thể tại khai báo. Sau SELECT INTO thành công, nó mang các field do result set xác định. Không truy cập field chưa tồn tại; điều đó dẫn đến lỗi runtime.

### 6.4. Gán cả row và gán từng field

~~~sql
DO $$
DECLARE
    v_customer pl_diag_lab.customers%ROWTYPE;
BEGIN
    SELECT * INTO v_customer
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    v_customer.customer_name := 'Tên tạm thời';
    RAISE NOTICE 'Bản ghi trong bộ nhớ: %', v_customer.customer_name;
END $$;
~~~

Phép gán này chỉ sửa **biến record/row local**, không tự UPDATE bảng. Muốn ghi thay đổi vào bảng, phải chạy SQL `UPDATE` có kiểm soát.

---

## 7. SELECT INTO không STRICT: 0, 1 hoặc nhiều rows

### 7.1. Query trả đúng một hàng

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
    INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    RAISE NOTICE 'name=%; FOUND=%', v_name, FOUND;
END $$;
~~~

Kết quả mong đợi `v_name='An'` và `FOUND=true`.

### 7.2. Query trả 0 hàng

~~~sql
DO $$
DECLARE
    v_name text := 'giá trị ban đầu';
BEGIN
    SELECT customer_name
    INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=999;

    RAISE NOTICE 'name=%; FOUND=%', v_name, FOUND;
END $$;
~~~

Khi SELECT INTO không STRICT **không tìm thấy row**, PL/pgSQL gán target **NULL**, không giữ nguyên “giá trị ban đầu”. `FOUND=false`.

Đừng viết:

~~~sql
IF v_name = NULL THEN
    ...
END IF;
~~~

Hãy dùng `v_name IS NULL` hoặc tốt hơn là kiểm tra **`FOUND` ngay sau SELECT** nếu yêu cầu phân biệt việc có tìm thấy row.

### 7.3. Query trả nhiều rows nhưng không STRICT

~~~sql
DO $$
DECLARE
    v_order_id bigint;
BEGIN
    SELECT order_id
    INTO v_order_id
    FROM pl_diag_lab.orders
    WHERE customer_id=101;

    RAISE NOTICE 'first order=%; FOUND=%', v_order_id, FOUND;
END $$;
~~~

Có hai orders 1001 và 1002. Query không STRICT **không tự báo TOO_MANY_ROWS**, mà lấy một hàng đầu tiên theo thứ tự executor cung cấp. Giá trị `v_order_id` **không được đảm bảo là 1001** nếu không có ORDER BY.

### 7.4. Chọn một hàng có quy tắc rõ

~~~sql
SELECT order_id
INTO v_order_id
FROM pl_diag_lab.orders
WHERE customer_id=101
ORDER BY created_at DESC, order_id DESC
LIMIT 1;
~~~

Khi muốn “đơn mới nhất”, ORDER BY nên bao gồm cột tie-breaker ổn định (ví dụ primary key) để tránh kết quả tùy ý khi nhiều hàng cùng `created_at`.

### 7.5. LIMIT 1 không kiểm tra duy nhất

`LIMIT 1` giải quyết yêu cầu **chọn một hàng**, không xác nhận bộ dữ liệu chỉ có một hàng thỏa predicate. Nếu nghiệp vụ yêu cầu “phải có đúng một khách hàng với customer_code này”, dùng UNIQUE constraint ở schema và cân nhắc `INTO STRICT` để phát hiện sai assumptions của query.

### 7.6. Dùng SELECT INTO với aggregation

~~~sql
DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM pl_diag_lab.orders
     WHERE customer_id=999;

    RAISE NOTICE 'count=%; FOUND=%', v_count, FOUND;
END $$;
~~~

Kết quả: `v_count=0`, nhưng **`FOUND=true`**, vì `COUNT(*)` không GROUP BY trả **một hàng chứa số 0**.

Do đó, `FOUND` phản ánh “statement trả hàng”, **không** phải “giá trị aggregate lớn hơn 0”.

---

## 8. SELECT INTO STRICT: phải đúng một hàng

### 8.1. Cú pháp

~~~sql
SELECT customer_name
INTO STRICT v_name
FROM pl_diag_lab.customers
WHERE customer_id=101;
~~~

`STRICT` yêu cầu query trả **chính xác một row**.

| Số rows từ query | Không STRICT | Có STRICT |
|---:|---|---|
| 0 | Target thành NULL, `FOUND=false` | Báo `NO_DATA_FOUND` |
| 1 | Target nhận giá trị, `FOUND=true` | Target nhận giá trị, `FOUND=true` |
| Nhiều hơn 1 | Target nhận một row đầu tiên, `FOUND=true` | Báo `TOO_MANY_ROWS` |

### 8.2. STRICT không có nghĩa “không cho cột NULL”

Nếu query trả đúng một row nhưng cột `optional_note` có giá trị NULL, `INTO STRICT` vẫn **thành công**. STRICT kiểm tra **số lượng row**, không bắt mỗi giá trị trong row NOT NULL.

### 8.3. Ví dụ đúng một row

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO STRICT v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=101;

    RAISE NOTICE 'Customer=%', v_name;
END $$;
~~~

### 8.4. Ví dụ NO_DATA_FOUND

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO STRICT v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=999;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE NOTICE 'Khách hàng không tồn tại';
END $$;
~~~

Exception được bắt trong block; `RAISE NOTICE` trong handler chỉ để demo. Trong ứng dụng, có thể trả trạng thái “not found” hoặc raise domain-specific error thích hợp.

### 8.5. Ví dụ TOO_MANY_ROWS

~~~sql
DO $$
DECLARE
    v_order bigint;
BEGIN
    SELECT order_id
      INTO STRICT v_order
      FROM pl_diag_lab.orders
     WHERE customer_id=101;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'Customer 101 có hơn một order';
END $$;
~~~

Hai orders 1001,1002 khiến STRICT báo lỗi, được handler bắt.

### 8.6. STRICT với aggregate

~~~sql
SELECT COUNT(*)
INTO STRICT v_count
FROM pl_diag_lab.orders
WHERE customer_id=999;
~~~

`COUNT(*)` không GROUP BY vẫn trả **một hàng**, nên STRICT **thành công**, giá trị bằng 0. Nếu có `GROUP BY` và không tạo nhóm nào, query có thể trả 0 rows và STRICT khi đó báo NO_DATA_FOUND.

### 8.7. STRICT không phải thay thế ràng buộc UNIQUE

Nếu data cần unique, đặt `UNIQUE` hoặc `PRIMARY KEY` tại database schema. `INTO STRICT` hữu ích để kiểm tra assumptions tại runtime, nhưng không ngăn transaction khác chèn dữ liệu vi phạm giả định nếu schema không có ràng buộc; chỉ constraint phù hợp mới thực thi invariant một cách nhất quán khi có concurrency.

---

## 9. FOUND: biến boolean đặc biệt của PL/pgSQL

### 9.1. FOUND tồn tại ở đâu?

Trong mỗi lần gọi function PL/pgSQL, có biến boolean đặc biệt `FOUND`:

- Được khởi tạo **false** khi bắt đầu mỗi lần gọi function.
- Có phạm vi trong function/block PL/pgSQL đó, không phải biến toàn server.
- Được một số câu lệnh PL/pgSQL cập nhật sau khi thực thi.
- Có thể đọc bằng `IF FOUND THEN` hoặc lưu lại: `v_was_found := FOUND;`.

~~~sql
DO $$
BEGIN
    RAISE NOTICE 'FOUND lúc đầu block: %', FOUND;
    PERFORM 1;
    RAISE NOTICE 'FOUND sau PERFORM 1: %', FOUND;
END $$;
~~~

### 9.2. FOUND sau SELECT INTO

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    IF FOUND THEN
        RAISE NOTICE 'Đã tìm thấy khách hàng: %', v_name;
    ELSE
        RAISE NOTICE 'Không thấy khách hàng';
    END IF;
END $$;
~~~

`FOUND=true` nếu SELECT INTO **gán từ ít nhất một row** thành công; ngược lại false.

### 9.3. FOUND là trạng thái gần nhất, không tự gắn với một biến

Mẫu dễ sai:

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=p_id;

PERFORM 1;

IF FOUND THEN
    -- Ở đây FOUND phản ánh PERFORM 1, KHÔNG còn SELECT INTO!
END IF;
~~~

`PERFORM 1` tạo một hàng và đặt FOUND=true, có thể che việc SELECT INTO không tìm thấy.

### 9.4. Cách đúng: chụp kết quả ngay sau statement

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=p_id;

v_customer_found := FOUND;

PERFORM 1;

IF v_customer_found THEN
    ...
END IF;
~~~

Phép gán boolean `v_customer_found := FOUND` không đại diện cho một SQL query mới cần tìm row. Đừng lưu tình trạng vào `FOUND` lâu dài; tạo biến có tên nghiệp vụ khi dùng qua nhiều bước.

### 9.5. FOUND không mang số hàng

`FOUND` chỉ là boolean. Với UPDATE tác động 1 hay 1000 rows, `FOUND=true` trong cả hai trường hợp. Để biết chính xác số hàng, dùng `GET DIAGNOSTICS ... = ROW_COUNT`.

### 9.6. FOUND không phải cờ transaction success

Một câu lệnh SQL trả **0 rows** vẫn có thể **thành công hoàn toàn** và `FOUND=false`. Ngược lại, một câu lệnh báo exception không có nghĩa bạn sẽ nhận một giá trị FOUND mới để kiểm tra; luồng điều khiển đã chuyển sang exception handler nếu được bắt.

---

## 10. Những câu lệnh nào cập nhật FOUND?

Không phải mọi câu lệnh PL/pgSQL đều đặt lại FOUND. Đây là một nguồn lỗi phổ biến khi viết nhiều SQL statements liên tiếp.

| Câu lệnh | FOUND khi nào true? | Ghi chú |
|---|---|---|
| `SELECT ... INTO` | Có ít nhất một row được trả | Không STRICT có thể chỉ chọn hàng đầu tiên |
| `PERFORM query` | Query tạo ít nhất một row | Dùng khi không cần nhận giá trị |
| `INSERT ...` | Chèn ít nhất một row | Bao gồm trường hợp `ON CONFLICT DO NOTHING` khiến không chèn được row |
| `UPDATE ...` | Tác động ít nhất một row | Không đồng nghĩa giá trị mới khác giá trị cũ |
| `DELETE ...` | Xóa ít nhất một row | Có thể false dù SQL thành công |
| `MERGE ...` | Có hàng được tác động theo ngữ nghĩa statement | Phụ thuộc phiên bản hỗ trợ; PostgreSQL 15+ |
| `FETCH cursor INTO ...` | Fetch được một row | Cursor có thể đã hết dữ liệu |
| `MOVE cursor` | Di chuyển được vị trí ít nhất một row | Không cần trả row cho application |
| `FOR query LOOP ... END LOOP` | Loop đã chạy ít nhất một lần | **FOUND được đặt khi kết thúc loop** |
| `FOREACH ... LOOP` | Có ít nhất một iteration | Tương tự khi kết thúc loop |
| `RETURN QUERY` hoặc `RETURN QUERY EXECUTE` | Có ít nhất một row được thêm vào result set | Trong set-returning function |
| `EXECUTE dynamic_string` | **Không tự thay đổi FOUND** | Dùng `GET DIAGNOSTICS ROW_COUNT` |
| Phép gán `v := expression` | Không tự thay đổi FOUND | Giá trị FOUND cũ còn tồn tại |
| `IF`, `RAISE` | Không phải nguồn cập nhật FOUND thông thường | Không dùng FOUND như state global |

### 10.1. Một ví dụ PERFORM

~~~sql
DO $$
BEGIN
    PERFORM 1
    FROM pl_diag_lab.customers
    WHERE customer_id=999;

    RAISE NOTICE 'Customer 999 exists? %', FOUND;

    PERFORM 1
    FROM pl_diag_lab.customers
    WHERE customer_id=101;

    RAISE NOTICE 'Customer 101 exists? %', FOUND;
END $$;
~~~

Kỳ vọng lần lượt **false**, **true**.

### 10.2. PERFORM dùng để bỏ qua kết quả SELECT

~~~sql
DO $$
BEGIN
    PERFORM pg_sleep(0.01);
    RAISE NOTICE 'Query đã thực thi';
END $$;
~~~

Đây chỉ là ví dụ nhỏ trên lab. Trong code thực, gọi function có tác động phụ cần hiểu idempotency và retry. Không dùng `PERFORM` để “đánh dấu thành công” nếu query trả 0 rows hợp lệ nhưng business vẫn thành công.

### 10.3. FOR query loop

~~~sql
DO $$
DECLARE
    r record;
    v_iterations integer := 0;
BEGIN
    FOR r IN
        SELECT order_id
        FROM pl_diag_lab.orders
        WHERE customer_id=101
        ORDER BY order_id
    LOOP
        v_iterations := v_iterations + 1;
        RAISE NOTICE 'Order %', r.order_id;
    END LOOP;

    RAISE NOTICE 'Iterations=%; FOUND=%', v_iterations, FOUND;
END $$;
~~~

Kỳ vọng hai iterations, `FOUND=true` **sau vòng lặp**.

Nếu trong vòng lặp có SQL cập nhật FOUND, trạng thái FOUND bên trong có thể bị thay đổi theo các lệnh đó. Theo quy tắc PL/pgSQL, vòng `FOR` đặt FOUND **khi vòng lặp kết thúc**, phản ánh việc nó có chạy iterations hay không.

### 10.4. FOREACH với mảng rỗng

~~~sql
DO $$
DECLARE
    v_tag integer;
    v_count integer := 0;
BEGIN
    FOREACH v_tag IN ARRAY ARRAY[]::integer[]
    LOOP
        v_count := v_count + 1;
    END LOOP;

    RAISE NOTICE 'iterations=%, FOUND=%', v_count, FOUND;
END $$;
~~~

Không có iteration, nên `FOUND=false` khi loop kết thúc (bỏ qua trạng thái từ các câu lệnh trước đó).

### 10.5. FOUND sau DML

~~~sql
DO $$
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_id=-1;

    RAISE NOTICE 'UPDATE affected any rows? %', FOUND;
END $$;
~~~

UPDATE 0 rows là câu SQL hợp lệ; `FOUND=false`.

### 10.6. Chụp FOUND khi phải thực thi lệnh khác

~~~sql
DO $$
DECLARE
    v_had_orders boolean;
    v_has_active_customer boolean;
BEGIN
    PERFORM 1 FROM pl_diag_lab.orders
    WHERE customer_id=101;

    v_had_orders := FOUND;

    PERFORM 1 FROM pl_diag_lab.customers
    WHERE customer_id=101 AND customer_status='active';

    v_has_active_customer := FOUND;

    RAISE NOTICE 'Has orders=%; active=%',
        v_had_orders, v_has_active_customer;
END $$;
~~~

Không dùng `FOUND` lần thứ hai để suy luận tình trạng của PERFORM thứ nhất.

---

## 11. GET DIAGNOSTICS: lấy thông tin sau khi statement chạy

### 11.1. Cú pháp cơ bản

~~~sql
GET DIAGNOSTICS v_rows = ROW_COUNT;
~~~

Tương đương dạng tường minh:

~~~sql
GET CURRENT DIAGNOSTICS v_rows = ROW_COUNT;
~~~

`CURRENT` là tùy chọn không bắt buộc cho GET DIAGNOSTICS thông thường.

### 11.2. Hai item chẩn đoán thường dùng

| Item | Kiểu target thường dùng | Ý nghĩa |
|---|---|---|
| `ROW_COUNT` | `bigint` | Số rows được xử lý bởi **lệnh SQL gần nhất** theo cơ chế command status PL/pgSQL |
| `PG_CONTEXT` | `text` | Chuỗi mô tả **call stack hiện tại** tại vị trí gọi GET DIAGNOSTICS |

`ROW_COUNT` không tự chứa thông tin của cả transaction; `PG_CONTEXT` không phải SQL query plan hoặc exception traceback.

### 11.3. ROW_COUNT khác FOUND

- `FOUND` trả lời “có row được xử lý hoặc tìm thấy không?” cho **những loại statement được hỗ trợ cập nhật FOUND**.
- `ROW_COUNT` trả lời “bao nhiêu rows” của **SQL statement gần nhất**, kể cả trong trường hợp dynamic EXECUTE không thay đổi FOUND.

Ví dụ:

~~~sql
DO $$
DECLARE
    v_count bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE customer_id=101 AND order_status='new';

    v_found := FOUND;
    GET DIAGNOSTICS v_count = ROW_COUNT;

    RAISE NOTICE 'found=%; affected=%', v_found, v_count;
END $$;
~~~

Trong dữ liệu lab ban đầu, ORDER 1001 đổi new → paid, `FOUND=true` và `ROW_COUNT=1`. **Lệnh này thay đổi bảng**; để giữ dữ liệu ban đầu, chạy trong transaction test có ROLLBACK hoặc sử dụng bản lab riêng.

### 11.4. Vì sao dùng bigint?

`ROW_COUNT` có thể rất lớn với bulk UPDATE/DELETE. Dùng `bigint` tránh giới hạn `integer` 32-bit và thể hiện đúng ý nghĩa lượng hàng tác động.

### 11.5. Chụp ngay sau lệnh quan trọng

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE customer_id=101
  AND order_status='new';

GET DIAGNOSTICS v_updated = ROW_COUNT;
v_updated_any := FOUND;

-- Các câu SELECT/UPDATE khác có thể đổi trạng thái được quan sát.
~~~

Cách đọc code này rõ: `v_updated` và `v_updated_any` phản ánh **UPDATE ngay trước đó**.

### 11.6. Không lấy ROW_COUNT sau nhiều lệnh khác

Sai:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

PERFORM 1;

GET DIAGNOSTICS v_rows = ROW_COUNT;
~~~

Lúc này `ROW_COUNT` không còn đại diện trực tiếp cho UPDATE ban đầu. **GET DIAGNOSTICS phải đặt sát SQL cần đo**.

### 11.7. Dữ liệu trả về không phải luôn số hàng được cập nhật

Một query:

~~~sql
SELECT COUNT(*) INTO v_count
FROM pl_diag_lab.orders
WHERE order_status='new';
~~~

trả một row aggregate chứa số lượng đơn. Nếu muốn biết **số đơn khớp predicate**, sử dụng `v_count`, không coi `GET DIAGNOSTICS ROW_COUNT` là total matching rows: câu SELECT aggregate chỉ tạo một hàng kết quả.

---

## 12. DML RETURNING INTO: vừa thay đổi dữ liệu vừa nhận kết quả

### 12.1. UPDATE RETURNING INTO

~~~sql
DO $$
DECLARE
    v_amount numeric(12,2);
    v_rows bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount + 50
     WHERE order_id=1001
     RETURNING amount INTO v_amount;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'amount=%, found=%, rows=%',
        v_amount, v_found, v_rows;
END $$;
~~~

Khi update thành công trên đúng một row, `v_amount` nhận giá trị sau UPDATE; `FOUND=true`, `ROW_COUNT=1`.

### 12.2. DELETE RETURNING INTO

~~~sql
DO $$
DECLARE
    v_deleted_order bigint;
    v_rows bigint;
BEGIN
    DELETE FROM pl_diag_lab.orders
    WHERE order_id=-999
    RETURNING order_id INTO v_deleted_order;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'deleted_id=%, rows=%, found=%',
        v_deleted_order, v_rows, FOUND;
END $$;
~~~

Với ID không tồn tại, `v_deleted_order` trở thành NULL, `ROW_COUNT=0`, `FOUND=false`. Đây không phải lỗi SQL.

### 12.3. INSERT RETURNING INTO

~~~sql
DO $$
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO pl_diag_lab.orders
        (order_id,customer_id,amount,order_status,created_at)
    VALUES
        (2001,101,75.00,'new',now())
    RETURNING order_id INTO v_id;

    RAISE NOTICE 'new order id=%', v_id;
END $$;
~~~

Chỉ chạy khi chưa có `order_id=2001`; nếu chạy nhiều lần trên cùng lab, câu INSERT sau có thể bị lỗi unique. Có thể chạy một lần trong transaction rồi ROLLBACK nếu muốn giữ bộ dữ liệu không đổi.

### 12.4. DML RETURNING khác SELECT INTO khi trả nhiều rows

**Chú ý đặc biệt:** Với `INSERT/UPDATE/DELETE/MERGE ... RETURNING ... INTO`, PL/pgSQL có thể báo lỗi khi RETURNING trả **hơn một row**, **ngay cả khi không viết STRICT**.

Ví dụ thử nghiệm:

~~~sql
DO $$
DECLARE
    v_id bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount
     WHERE customer_id=101
     RETURNING order_id INTO v_id;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'RETURNING có nhiều hơn một row';
END $$;
~~~

Với lab ban đầu, customer 101 có hai orders nên statement RETURNING muốn trả hai rows → PL/pgSQL không tự chọn row đầu tiên như SELECT INTO không STRICT. Lỗi được bắt; thay đổi trong block chứa statement bị rollback theo cơ chế exception subtransaction.

### 12.5. Khi cần cập nhật hàng loạt, không dùng scalar RETURNING INTO

Nếu mục tiêu là xử lý **mọi hàng được cập nhật**, có thể:

- Chạy DML **không RETURNING INTO** và lấy `ROW_COUNT`.
- Dùng `RETURN QUERY UPDATE ... RETURNING ...` trong set-returning function khi phù hợp.
- Cân nhắc viết logic SQL set-based, không lặp một UPDATE mỗi row.
- Dùng một bảng audit hoặc CTE RETURNING để nạp kết quả theo transaction, khi cần lưu mọi changed IDs.

Ví dụ đếm đúng:

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_status='new';

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'Đã cập nhật % đơn', v_rows;
END $$;
~~~

**Đây là DML thật.** Trong lab, bọc transaction `BEGIN; DO ...; ROLLBACK;` để thử mà không thay trạng thái lâu dài.

---

## 13. SELECT INTO + FOUND, hay SELECT EXISTS/COUNT?

### 13.1. Khi cần lấy đúng một giá trị

~~~sql
SELECT customer_name
  INTO v_name
  FROM pl_diag_lab.customers
 WHERE customer_id=p_customer_id;

IF NOT FOUND THEN
    ...
END IF;
~~~

Phù hợp khi muốn nhận giá trị đã tìm.

### 13.2. Khi chỉ cần biết có tồn tại

~~~sql
SELECT EXISTS (
    SELECT 1
    FROM pl_diag_lab.orders
    WHERE customer_id=p_customer_id
)
INTO v_has_order;
~~~

Đây là query **luôn trả một row boolean** khi thành công, nên `FOUND=true` ngay cả khi `v_has_order=false`. Với cách này **kiểm tra `v_has_order`**, không kiểm tra FOUND để biết có đơn.

### 13.3. PERFORM cho existence check

~~~sql
PERFORM 1
FROM pl_diag_lab.orders
WHERE customer_id=p_customer_id;

IF FOUND THEN
    ...
END IF;
~~~

`FOUND` trực tiếp phản ánh query có trả ít nhất một row hay không. Với điều kiện tồn tại, có thể dùng `PERFORM 1 ... LIMIT 1` để thể hiện chủ đích. Với bảng có index phù hợp, planner có cơ hội stop early.

### 13.4. Khi cần số lượng chính xác

~~~sql
SELECT COUNT(*)
INTO v_order_count
FROM pl_diag_lab.orders
WHERE customer_id=p_customer_id;
~~~

Đúng khi nghiệp vụ cần count. `COUNT(*)` có thể phải xử lý nhiều row hơn existence check. Không dùng COUNT để kiểm tra tồn tại trên bảng rất lớn khi chỉ cần một boolean và không có lý do khác.

### 13.5. Khi cần bảo đảm đúng một row

~~~sql
SELECT customer_name
INTO STRICT v_name
FROM pl_diag_lab.customers
WHERE customer_code=p_code;
~~~

Với UNIQUE constraint trên customer_code, STRICT có ý nghĩa xác minh case “không có” và phát hiện assumptions sai. Nếu không muốn raise khi missing, có thể dùng SELECT INTO không STRICT + FOUND.

### 13.6. Bảng lựa chọn nhanh

| Mục tiêu | SQL/PLpgSQL | Cần đọc gì? |
|---|---|---|
| Lấy một giá trị nếu có | SELECT ... INTO | Target + FOUND |
| Phải đúng một row | SELECT ... INTO STRICT | NO_DATA_FOUND / TOO_MANY_ROWS |
| Chỉ kiểm tra tồn tại | PERFORM 1 FROM ... LIMIT 1 | FOUND |
| Chỉ kiểm tra tồn tại thành boolean | SELECT EXISTS(...) INTO v_bool | v_bool, **không phải FOUND** |
| Đếm rows thỏa predicate | SELECT COUNT(*) INTO v_count | v_count |
| UPDATE có tác động hay không | UPDATE ... | FOUND |
| UPDATE bao nhiêu rows | UPDATE ...; GET DIAGNOSTICS | ROW_COUNT |
| DML một row và nhận output | UPDATE/INSERT/DELETE ... RETURNING INTO | Target + FOUND |
| DML nhiều rows, chỉ cần count | DML không RETURNING INTO; GET DIAGNOSTICS | ROW_COUNT |

---

## 14. Dynamic SQL với EXECUTE: trường hợp đặc biệt của FOUND

### 14.1. EXECUTE dùng khi SQL được xây ở runtime

~~~sql
DO $$
DECLARE
    v_id bigint := 101;
    v_name text;
    v_rows bigint;
BEGIN
    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
          WHERE customer_id=$1'
    INTO v_name
    USING v_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'name=%, row_count=%', v_name, v_rows;
END $$;
~~~

`EXECUTE ... INTO target USING ...` cho phép nhận kết quả của SQL động. Dùng `USING` cho **giá trị dữ liệu** nhằm tránh ghép literal không an toàn.

### 14.2. EXECUTE **không cập nhật FOUND**

Đây là khác biệt cốt lõi:

~~~sql
DO $$
DECLARE
    v_name text;
    v_rows bigint;
    v_found_before boolean;
BEGIN
    PERFORM 1 FROM pl_diag_lab.customers WHERE customer_id=101;
    v_found_before := FOUND; -- true

    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
          WHERE customer_id=$1'
    INTO v_name
    USING 999;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'found_before=%, FOUND_now=%, dynamic_rows=%',
        v_found_before, FOUND, v_rows;
END $$;
~~~

Dynamic SELECT không tìm thấy customer 999, `v_name=NULL` và `ROW_COUNT=0`. Nhưng **`FOUND` vẫn có thể true từ PERFORM trước**. Đừng dùng `IF FOUND` để kiểm tra dynamic EXECUTE.

### 14.3. Cách đúng sau EXECUTE

~~~sql
EXECUTE v_sql INTO v_value USING p_id;
GET DIAGNOSTICS v_rows = ROW_COUNT;

IF v_rows = 0 THEN
    ...
END IF;
~~~

Nếu target value có thể NULL hợp lệ, không dùng `IF v_value IS NULL` thay kiểm tra số hàng. `ROW_COUNT` phản ánh statement mới thực thi tốt hơn trong trường hợp này.

### 14.4. Dynamic EXECUTE ... INTO STRICT

~~~sql
EXECUTE
    'SELECT customer_name FROM pl_diag_lab.customers
      WHERE customer_id=$1'
INTO STRICT v_name
USING p_customer_id;
~~~

`INTO STRICT` trên dynamic EXECUTE cũng có thể raise `NO_DATA_FOUND` hoặc `TOO_MANY_ROWS` nếu query không trả đúng một row, theo quy tắc của PL/pgSQL.

### 14.5. Không ghép tên bảng từ input bằng cách nối chuỗi

Sai:

~~~text
v_sql := 'SELECT * FROM ' || untrusted_table_name;
~~~

Dùng `format('%I', identifier)` cho tên đối tượng, `USING` cho values, và validate danh sách tên bảng/cột được phép.

~~~sql
DO $$
DECLARE
    v_schema text := 'pl_diag_lab';
    v_table text := 'customers';
    v_id bigint := 101;
    v_count bigint;
BEGIN
    EXECUTE format(
        'SELECT COUNT(*) FROM %I.%I WHERE customer_id=$1',
        v_schema, v_table
    )
    INTO v_count
    USING v_id;

    RAISE NOTICE 'count=%', v_count;
END $$;
~~~

Lệnh SELECT COUNT(*) luôn tạo một row; `v_count` là số khách khớp, còn ROW_COUNT sau dynamic SELECT aggregate phản ánh row kết quả, **không phải v_count**.

### 14.6. EXECUTE dynamic UPDATE

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    EXECUTE
        'UPDATE pl_diag_lab.orders
           SET order_status=$1
         WHERE order_id=$2'
    USING 'paid', -999;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'dynamic update affected % rows', v_rows;
END $$;
~~~

Kỳ vọng `v_rows=0` trong lab. `FOUND` không được dynamic EXECUTE đặt lại, kể cả khi SQL động là UPDATE.

### 14.7. Dynamic SQL và plan caching

PL/pgSQL có thể cache plans cho statements tĩnh trong những trường hợp thích hợp. `EXECUTE` dynamic string được lập kế hoạch mỗi lần thực thi, điều này có thể có lợi hoặc tốn kém tùy parameter-sensitive plans và workload. **Không chọn dynamic SQL chỉ để né FOUND**; chọn theo nhu cầu query structure thực sự thay đổi.

---

## 15. GET DIAGNOSTICS PG_CONTEXT: biết vị trí đang chạy

### 15.1. Cú pháp

~~~sql
DO $$
DECLARE
    v_context text;
BEGIN
    GET DIAGNOSTICS v_context = PG_CONTEXT;
    RAISE NOTICE 'Current PL/pgSQL stack:%', chr(10) || v_context;
END $$;
~~~

`PG_CONTEXT` trả về chuỗi mô tả **current call stack**, gồm thông tin các PL/pgSQL functions/blocks và dòng thực thi theo khả năng của PostgreSQL.

### 15.2. PG_CONTEXT không phải error context

Khi code đang chạy bình thường, `GET DIAGNOSTICS ... PG_CONTEXT` cho biết **vị trí hiện tại**. Khi một exception xảy ra, muốn biết **vị trí phát sinh lỗi**, hãy dùng `GET STACKED DIAGNOSTICS ... PG_EXCEPTION_CONTEXT` trong exception handler.

Nếu đọc `PG_CONTEXT` sau khi đã vào handler, bạn đang xem **stack hiện tại tại handler**, không nhất thiết là toàn bộ thông tin gốc về vị trí lỗi.

### 15.3. Dùng PG_CONTEXT để ghi log

Trong procedure lớn, chuỗi call stack giúp xác định dòng nào đang thực thi khi log được ghi. Nhưng:

- Không nên trả full internal stack ra HTTP API cho khách hàng.
- Stack có thể lộ tên schema/function, line numbers và logic nội bộ.
- Log cần chính sách bảo mật/retention.
- Dùng log có định danh request/transaction thích hợp để liên kết với hệ thống quan sát.

### 15.4. Có thể lấy nhiều diagnostic items trong một lệnh

~~~sql
DO $$
DECLARE
    v_rows bigint;
    v_context text;
BEGIN
    PERFORM 1;
    GET DIAGNOSTICS
        v_rows = ROW_COUNT,
        v_context = PG_CONTEXT;

    RAISE NOTICE 'rows=%', v_rows;
    RAISE NOTICE 'context:%', chr(10) || v_context;
END $$;
~~~

Đối với hiệu năng và độ rõ ràng, lưu thông tin cần dùng vào biến ngay sau statement thay vì gọi nhiều lệnh không cần thiết trước khi kiểm tra.

---

## 16. GET STACKED DIAGNOSTICS: thông tin của exception hiện tại

### 16.1. Hai loại diagnostics cần phân biệt

| Cú pháp | Dùng ở đâu? | Thông tin chính |
|---|---|---|
| `GET [CURRENT] DIAGNOSTICS ...` | Khi đang chạy PL/pgSQL bình thường, kể cả trong handler nếu cần current context | `ROW_COUNT`, `PG_CONTEXT` |
| `GET STACKED DIAGNOSTICS ...` | Trong một `EXCEPTION` handler đang xử lý lỗi | `RETURNED_SQLSTATE`, `MESSAGE_TEXT`, `PG_EXCEPTION_*` và các thông tin object |

`GET STACKED DIAGNOSTICS` không phải cách lấy row count sau UPDATE. Nó dành cho **lỗi đang được bắt**.

### 16.2. Các item phổ biến của stacked diagnostics

| Item | Ý nghĩa |
|---|---|
| `RETURNED_SQLSTATE` | SQLSTATE 5 ký tự của lỗi |
| `MESSAGE_TEXT` | Thông báo lỗi chính |
| `PG_EXCEPTION_DETAIL` | Thông tin chi tiết của lỗi, nếu có |
| `PG_EXCEPTION_HINT` | Gợi ý của lỗi, nếu có |
| `PG_EXCEPTION_CONTEXT` | Stack/đường thực thi tại điểm lỗi |
| `COLUMN_NAME` | Tên cột gắn với lỗi, nếu được cung cấp |
| `CONSTRAINT_NAME` | Tên constraint liên quan, nếu được cung cấp |
| `DATATYPE_NAME` | Kiểu dữ liệu liên quan, nếu được cung cấp |
| `TABLE_NAME` | Bảng liên quan, nếu được cung cấp |
| `SCHEMA_NAME` | Schema liên quan, nếu được cung cấp |

Không phải lỗi nào cũng điền đầy đủ mọi trường. Thông tin không có có thể là chuỗi rỗng; đừng giả định tên constraint luôn được trả.

### 16.3. Ví dụ bắt lỗi khóa duy nhất

~~~sql
DO $$
DECLARE
    v_state text;
    v_message text;
    v_constraint text;
    v_detail text;
BEGIN
    INSERT INTO pl_diag_lab.customers
        (customer_id,customer_code,customer_name,customer_status)
    VALUES
        (101,'C999','Trùng ID','active');
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_constraint = CONSTRAINT_NAME,
            v_detail = PG_EXCEPTION_DETAIL;

        RAISE NOTICE
            'sqlstate=%, constraint=%, message=%',
            v_state,v_constraint,v_message;
END $$;
~~~

Với lab đã có customer 101, câu INSERT vi phạm PK và handler chạy. Kết quả **không** chèn thêm một customer 101.

### 16.4. SQLSTATE và tên condition

PostgreSQL quy định SQLSTATE 5 ký tự; một số mã thường gặp:

| Tên exception | SQLSTATE | Thường gặp ở |
|---|---|---|
| `unique_violation` | `23505` | PK hoặc UNIQUE conflict |
| `foreign_key_violation` | `23503` | FK target không tồn tại hoặc bị tham chiếu |
| `not_null_violation` | `23502` | Ghi NULL vào cột NOT NULL |
| `check_violation` | `23514` | CHECK constraint không thỏa |
| `no_data_found` | `P0002` | `SELECT INTO STRICT` không có row |
| `too_many_rows` | `P0003` | `SELECT INTO STRICT` nhiều rows |
| `raise_exception` | `P0001` | `RAISE EXCEPTION` không gắn mã riêng |
| `division_by_zero` | `22012` | Phép chia cho 0 |
| `serialization_failure` | `40001` | Xung đột isolation/retry |
| `deadlock_detected` | `40P01` | Deadlock được PostgreSQL phát hiện |

Các SQLSTATE này không phải mọi lỗi PL/pgSQL; dùng SQLSTATE chính xác từ handler thay vì parse thông báo lỗi có thể thay đổi theo version/ngôn ngữ.

### 16.5. SQLSTATE và SQLERRM trong handler

Trong `EXCEPTION` handler, PL/pgSQL cung cấp các biến đặc biệt `SQLSTATE`, `SQLERRM` có thể đọc trực tiếp.

~~~sql
DO $$
BEGIN
    RAISE EXCEPTION 'Lỗi thử nghiệm';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'SQLSTATE=%, message=%',
            SQLSTATE, SQLERRM;
END $$;
~~~

Những biến này **chỉ có ý nghĩa/khả dụng trong exception handling context**; không dùng chúng như state luôn có sau mỗi SELECT hay UPDATE.

### 16.6. PG_EXCEPTION_CONTEXT vs PG_CONTEXT

~~~sql
DO $$
DECLARE
    v_error_context text;
    v_current_context text;
BEGIN
    PERFORM 1 / 0;
EXCEPTION
    WHEN division_by_zero THEN
        GET STACKED DIAGNOSTICS
            v_error_context = PG_EXCEPTION_CONTEXT;

        GET DIAGNOSTICS
            v_current_context = PG_CONTEXT;

        RAISE NOTICE 'Error origin:%',
            chr(10) || v_error_context;
        RAISE NOTICE 'Current handler:%',
            chr(10) || v_current_context;
END $$;
~~~

`v_error_context` mô tả nơi lỗi xảy ra; `v_current_context` mô tả nơi code đang chạy sau khi vào handler.

### 16.7. Không để lộ nội dung lỗi nhạy cảm

`PG_EXCEPTION_DETAIL` có thể chứa giá trị khóa bị trùng hoặc những dữ liệu khác. Chỉ ghi vào log được bảo vệ theo chính sách vận hành; không tự trả toàn bộ message/detail/hint/context cho client.

---

## 17. Exception block và rollback của thay đổi bên trong block

### 17.1. Một block có EXCEPTION sử dụng cơ chế subtransaction

Trong PL/pgSQL, khi lỗi được bắt bằng `EXCEPTION`, những thay đổi dữ liệu **được thực hiện trong phần thân block đó trước khi lỗi** bị rollback. Nhưng các biến PL/pgSQL vẫn giữ giá trị theo trạng thái logic tại thời điểm chuyển sang handler.

### 17.2. Ví dụ một INSERT trước lỗi

~~~sql
DO $$
DECLARE
    v_step text := 'initial';
BEGIN
    BEGIN
        INSERT INTO pl_diag_lab.customers
            (customer_id,customer_code,customer_name,customer_status)
        VALUES
            (900,'C900','Temporary','active');

        v_step := 'after first insert';

        INSERT INTO pl_diag_lab.customers
            (customer_id,customer_code,customer_name,customer_status)
        VALUES
            (101,'C101X','Duplicate ID','active');
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Step reached: %', v_step;
    END;
END $$;
~~~

Khi INSERT thứ hai vi phạm PK, INSERT đầu tiên **trong block có EXCEPTION** cũng bị rollback. `v_step` vẫn có thể là `after first insert` trong handler, thể hiện PL/pgSQL variables không được rollback giống row changes.

### 17.3. Xác minh dữ liệu

~~~sql
SELECT COUNT(*)
FROM pl_diag_lab.customers
WHERE customer_id=900;
~~~

Kỳ vọng 0 nếu chạy lab từ trạng thái gốc, vì inner block bị rollback.

### 17.4. Bắt exception không tự commit giao dịch

Một `EXCEPTION` handler có thể cho function tiếp tục, nhưng nó không tự COMMIT bất kỳ transaction nào. Nếu caller rollback transaction bao ngoài thì mọi thay đổi chưa commit còn lại cũng bị rollback.

### 17.5. Không bắt OTHERS rồi lờ mọi lỗi

Mẫu gây khó chẩn đoán:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
~~~

Nó có thể che lỗi quyền, schema, constraint, deadlock, loại dữ liệu và lỗi logic thành một kết quả NULL khó phân biệt. Nên bắt **những lỗi mà nghiệp vụ thực sự xử lý được**; nếu không, dùng `RAISE;` để phát lại sau khi log tối thiểu an toàn.

### 17.6. Không bắt mọi lỗi serialization/deadlock rồi tiếp tục như thành công

Các lỗi `40001` và `40P01` thường đòi **retry toàn transaction theo cơ chế application**. Không đơn thuần bắt rồi trả FOUND=false vì đó không phải “không tìm thấy hàng”.

---

## 18. Khi nào dùng RAISE; để phát lại lỗi?

### 18.1. Ghi log an toàn rồi rethrow

~~~sql
DO $$
DECLARE
    v_state text;
    v_message text;
BEGIN
    PERFORM 1 / 0;
EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT;

        RAISE NOTICE 'Failure SQLSTATE=%, message=%',
            v_state, v_message;
        RAISE;
END $$;
~~~

Đây là mẫu **cố ý phát lại lỗi** để minh họa, nên khi chạy, câu DO cuối cùng báo lỗi division_by_zero. Để ứng dụng xử lý lỗi, caller có thể bắt ngoại lệ ở lớp phù hợp; đừng chạy qua deployment pipeline mong mọi câu SQL thành công.

### 18.2. RAISE EXCEPTION tùy chỉnh SQLSTATE

~~~sql
RAISE EXCEPTION 'Đơn hàng % không tồn tại', p_order_id
    USING ERRCODE = 'P0002';
~~~

Có thể dùng condition name hoặc mã SQLSTATE hợp lệ. Nhưng **không tự trả lỗi tùy chỉnh giống lỗi hệ thống** khi API cần phân biệt nhiều tình huống; xác định contract lỗi rõ và nhất quán.

### 18.3. Đọc SQLSTATE tốt hơn parse message

Lỗi từ PostgreSQL có thể chứa tên cột, schema, constraint trong message. Khi quyết định retry, classify unique/FK, hãy dùng `RETURNED_SQLSTATE` hoặc tên exception, không dựa vào chuỗi tiếng Anh “duplicate key” dễ thay đổi.

### 18.4. Mẫu xử lý unique theo tên constraint

~~~sql
DO $$
DECLARE
    v_constraint text;
BEGIN
    INSERT INTO pl_diag_lab.customers
        (customer_id,customer_code,customer_name,customer_status)
    VALUES
        (101,'CXXX','Duplicate','active');
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME;

        IF v_constraint = 'customers_pkey' THEN
            RAISE NOTICE 'ID khách hàng đã tồn tại';
        ELSE
            RAISE;
        END IF;
END $$;
~~~

Kết quả phụ thuộc tên PK thực tế; nếu bạn đặt tên constraint khác hoặc migrate schema, cần cập nhật. **Tên constraint nên được kiểm soát bằng migration** nếu logic ứng dụng dựa vào nó, nhưng đừng che lỗi unique ở constraint khác.

---

## 19. Function hoàn chỉnh: tìm khách hàng với kết quả rõ ràng

### 19.1. Tìm theo primary key, không STRICT

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.get_customer_name(
    p_customer_id bigint
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=p_customer_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN v_name;
END;
$$;
~~~

Thử:

~~~sql
SELECT pl_diag_lab.get_customer_name(101) AS existing_name;
SELECT pl_diag_lab.get_customer_name(999) AS missing_name;
~~~

Kỳ vọng `An` và NULL.

### 19.2. Một hạn chế của cách trả NULL

Nếu `customer_name` cho phép NULL, kết quả NULL sẽ mơ hồ giữa “không có khách” và “có khách nhưng tên NULL”. Trong lab có `NOT NULL` nên không mơ hồ. Trong hệ thống thật có thể trả **composite result/status code**, dùng STRICT với exception hoặc caller nhận thêm cờ FOUND.

### 19.3. Function STRICT với exception chuyên biệt

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.get_customer_name_strict(
    p_customer_id bigint
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
BEGIN
    SELECT customer_name
      INTO STRICT v_name
      FROM pl_diag_lab.customers
     WHERE customer_id=p_customer_id;

    RETURN v_name;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'Không tìm thấy khách hàng %', p_customer_id
            USING ERRCODE = 'P0002';
END;
$$;
~~~

Thử thành công:

~~~sql
SELECT pl_diag_lab.get_customer_name_strict(101);
~~~

Với 999, function phát exception. Đây là lựa chọn hợp lý khi “customer phải tồn tại” là **precondition** bắt buộc, không phải kết quả trống thông thường.

### 19.4. Bắt TOO_MANY_ROWS vẫn cần schema constraint

Vì WHERE dùng PRIMARY KEY customer_id, dữ liệu hợp lệ bảo đảm tối đa một row. STRICT xử lý lỗi missing, còn TOO_MANY_ROWS gần như không thể xảy ra trừ khi query/schema thay đổi. Chính PK là nguồn bảo đảm uniqueness, không phải STRICT.

---

## 20. Function hoàn chỉnh: cập nhật đơn hàng và trả số hàng

### 20.1. Hàm chỉ cập nhật đơn ở trạng thái new

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.mark_order_paid(
    p_order_id bigint
)
RETURNS TABLE (
    was_updated boolean,
    affected_rows bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_id=p_order_id
       AND order_status='new';

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    was_updated := v_found;
    affected_rows := v_rows;

    RETURN NEXT;
END;
$$;
~~~

### 20.2. Thử trong transaction an toàn

~~~sql
BEGIN;

SELECT *
FROM pl_diag_lab.mark_order_paid(1001);

SELECT order_id,order_status
FROM pl_diag_lab.orders
WHERE order_id=1001;

ROLLBACK;
~~~

Với dữ liệu gốc, hàm trả `was_updated=true` và `affected_rows=1`; trong transaction, order 1001 trở thành paid, rồi ROLLBACK đưa trở lại new.

### 20.3. Gọi với order không tồn tại

~~~sql
SELECT *
FROM pl_diag_lab.mark_order_paid(-999);
~~~

Kỳ vọng false, 0. Function không biến “0 hàng update” thành SQL exception. Đây có thể là kết quả hợp lệ tùy API contract.

### 20.4. Không đồng nhất “không tồn tại” và “không thỏa trạng thái”

Với hàm trên, `was_updated=false` có thể có hai nguyên nhân:

1. Không có order với ID đó.
2. Order tồn tại nhưng status không phải new (đã paid/canceled).

Nếu nghiệp vụ cần phân biệt, phải thiết kế thêm query/return status và concurrency control phù hợp. Không thể biết hai trường hợp chỉ từ `ROW_COUNT=0` của UPDATE có WHERE gồm cả ID và status.

### 20.5. Concurrency và atomic UPDATE

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=p_order_id
  AND order_status='new';
~~~

Đây là một statement kiểm tra điều kiện và cập nhật dưới transaction semantics của PostgreSQL, thường an toàn hơn quy trình ứng dụng “SELECT status → nếu new thì UPDATE không có guard” dễ gặp race.

Tuy nhiên không phải mọi nghiệp vụ tự giải quyết chỉ nhờ một UPDATE: với thanh toán thật, cần idempotency key, khóa/constraint và toàn vẹn các side effects ngoài DB. `FOUND=true` không chứng minh việc gửi tiền hay gọi dịch vụ ngoài đã hoàn thành.

---

## 21. SELECT INTO STRICT hay RETURNING INTO: tránh query thừa khi có thể

### 21.1. Pattern đọc rồi cập nhật

~~~sql
SELECT amount INTO STRICT v_amount
FROM pl_diag_lab.orders
WHERE order_id=p_order_id;

UPDATE pl_diag_lab.orders
SET amount=v_amount + 10
WHERE order_id=p_order_id;
~~~

Nếu giữa SELECT và UPDATE có transaction khác thay amount, pattern này có nguy cơ tính trên giá trị cũ ở isolation thích hợp. Chỉ dùng khi có locking/isolation strategy đúng.

### 21.2. Pattern cập nhật trực tiếp

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount + 10
WHERE order_id=p_order_id
RETURNING amount INTO v_amount;
~~~

Một SQL statement diễn đạt biến đổi dựa trên giá trị hiện tại và nhận new amount. Khi order_id là PK, RETURNING tối đa một row, phù hợp scalar INTO.

### 21.3. Phân biệt zero rows

Sau UPDATE:

~~~sql
v_was_updated := FOUND;
GET DIAGNOSTICS v_rows = ROW_COUNT;
~~~

Nếu không tìm thấy, `v_amount` có thể NULL và `FOUND=false`. Nếu dùng số tiền nullable, không dựa vào amount NULL để kết luận missing; dùng status/rowcount.

### 21.4. Khi có nhiều rows cần xử lý

Không dùng scalar RETURNING INTO sau UPDATE hàng loạt và hy vọng “chọn first row”. Với RETURNING nhiều rows, có thể bị lỗi ngay cả không STRICT. Chuyển sang set-based result hoặc đếm ROW_COUNT phù hợp.

---

## 22. Vì sao phép gán, SELECT INTO và GET DIAGNOSTICS dễ bị nhầm?

### 22.1. Ba dòng trông gần giống nhau nhưng có nguồn dữ liệu khác

~~~sql
v_amount := 120.00;

SELECT amount INTO v_amount
FROM pl_diag_lab.orders
WHERE order_id=1001;

GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

| Dòng | Tác động lên biến | Có đọc rows bảng? | Có phát sinh FOUND từ statement? |
|---|---|---|---|
| `v_amount := 120.00` | Gán literal/expression | Không nhất thiết | Phép gán không tự đặt FOUND |
| `SELECT ... INTO` | Gán từ kết quả query | Có | Đặt FOUND true/false |
| `GET DIAGNOSTICS` | Gán thông tin diagnostic như ROW_COUNT | Đọc command status nội bộ, không phải query nghiệp vụ | Không dùng nó để suy ra FOUND của một query khác |

### 22.2. Với SELECT INTO không STRICT, không phải COUNT tất cả rows

Nếu:

~~~sql
SELECT order_id INTO v_id
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

có hai đơn, bạn **không** nên suy ra `ROW_COUNT=2` rồi dùng nó để xác định "customer có hai đơn". SELECT INTO không STRICT chỉ cần một hàng; để đếm mọi row thỏa điều kiện, viết:

~~~sql
SELECT COUNT(*) INTO v_order_count
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

### 22.3. FOUND không lưu lịch sử nhiều lệnh

Lệnh SQL A đặt FOUND=true, SQL B đặt FOUND=false; sau B không còn một biến đặc biệt nào tự giữ trạng thái của A. Nếu cần phân tích từng bước, đặt biến:

~~~sql
v_found_customer := FOUND;
v_rows_updated := v_rows;
~~~

### 22.4. ROW_COUNT không phải luôn "số hàng trả cho HTTP"

`ROW_COUNT` của DML cho biết số hàng được xử lý bởi statement, không phải số bản ghi API sẽ trả. Với một hàm trả tổng hợp hoặc pagination, số hàng output của function có thể không trùng số hàng update ở bảng.

### 22.5. Đọc diagnostic phải gắn với thời điểm

Nếu bạn debug bằng cách thêm `PERFORM` hoặc câu SQL khác **ở giữa câu DML và GET DIAGNOSTICS**, bạn có thể làm thay đổi điều đang đo. Khi instrumentation, ưu tiên chụp `FOUND` và `ROW_COUNT` ngay sau statement quan trọng, rồi mới log/đi tiếp.

---

## 23. SELECT INTO với JOIN và row multiplication

### 23.1. Một join có thể trả nhiều rows dù WHERE trên primary key

~~~sql
DO $$
DECLARE
    v_order_id bigint;
BEGIN
    SELECT o.order_id
      INTO v_order_id
      FROM pl_diag_lab.customers AS c
      JOIN pl_diag_lab.orders AS o
        ON o.customer_id=c.customer_id
     WHERE c.customer_id=101;

    RAISE NOTICE 'Một trong các order IDs: %', v_order_id;
END $$;
~~~

WHERE chỉ định đúng một customer theo PK nhưng JOIN tạo **hai orders**. Không STRICT sẽ chọn một row không có ORDER BY rõ ràng.

### 23.2. Nếu muốn phát hiện hơn một đơn

~~~sql
DO $$
DECLARE
    v_order_id bigint;
BEGIN
    SELECT o.order_id
      INTO STRICT v_order_id
      FROM pl_diag_lab.orders AS o
     WHERE o.customer_id=101;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'Customer có nhiều orders';
END $$;
~~~

### 23.3. Nếu muốn lấy đơn mới nhất

~~~sql
SELECT order_id
  INTO v_order_id
  FROM pl_diag_lab.orders
 WHERE customer_id=101
 ORDER BY created_at DESC,order_id DESC
 LIMIT 1;
~~~

### 23.4. Nếu muốn lấy mọi orders

Đừng dùng scalar SELECT INTO. Có các cách khác:

~~~sql
SELECT array_agg(order_id ORDER BY order_id)
INTO v_order_ids
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

Mẫu này trả **một row aggregate** chứa một array of IDs. Nếu không có orders, `array_agg` trả NULL; dùng `COALESCE(array_agg(...), '{}'::bigint[])` khi muốn array rỗng.

Hoặc dùng cursor, FOR query loop, RETURN QUERY ở function set-returning, tùy số lượng rows và nhu cầu xử lý.

### 23.5. Không dùng SELECT INTO như cursor tự động

`SELECT INTO` không tự tạo con trỏ để iterating rows, cũng không lặp tất cả rows như `FOR r IN SELECT ... LOOP`. Nó là thao tác gán kết quả vào một target.

---

## 24. Cursor và FOUND trong FETCH/MOVE

### 24.1. Ví dụ cursor đơn giản

~~~sql
DO $$
DECLARE
    cur_orders CURSOR FOR
        SELECT order_id
        FROM pl_diag_lab.orders
        ORDER BY order_id;
    v_id bigint;
    v_fetch_found boolean;
BEGIN
    OPEN cur_orders;

    FETCH cur_orders INTO v_id;
    v_fetch_found := FOUND;

    RAISE NOTICE 'first=%; fetched=%', v_id, v_fetch_found;

    CLOSE cur_orders;
END $$;
~~~

`FETCH` đặt FOUND=true nếu lấy được một row; false khi không có row.

### 24.2. Khi cursor hết dữ liệu

~~~sql
DO $$
DECLARE
    cur_orders CURSOR FOR
        SELECT order_id
        FROM pl_diag_lab.orders
        WHERE order_id<0;
    v_id bigint;
BEGIN
    OPEN cur_orders;
    FETCH cur_orders INTO v_id;
    RAISE NOTICE 'FOUND=%; id=%', FOUND, v_id;
    CLOSE cur_orders;
END $$;
~~~

Với lab không có order ID âm, `FOUND=false`.

### 24.3. MOVE thay đổi FOUND theo số rows di chuyển

`MOVE` là thao tác reposition cursor, không trả row dữ liệu giống FETCH. Nếu MOVE thực sự di chuyển một hoặc nhiều rows thì FOUND có thể true, khi không di chuyển thì false. Đừng nhầm với câu UPDATE/DELETE: đây là cursor movement.

### 24.4. FETCH có thể là nguồn ghi đè FOUND

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=1001;

-- FETCH cur_orders INTO v_id; -- nếu thêm vào, FOUND phản ánh FETCH
IF FOUND THEN
    ...
END IF;
~~~

Đây là ví dụ logic minh họa; không chạy UPDATE thật nếu bạn chỉ muốn đọc code. Để biết UPDATE thành công, hãy lưu `v_updated := FOUND` ngay sau UPDATE **trước FETCH**.

---

## 25. FOUND trong RETURN QUERY và set-returning functions

### 25.1. Hàm trả nhiều rows

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.list_customer_orders(
    p_customer_id bigint
)
RETURNS TABLE (
    order_id bigint,
    amount numeric,
    order_status text
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_had_rows boolean;
BEGIN
    RETURN QUERY
    SELECT o.order_id,o.amount,o.order_status
    FROM pl_diag_lab.orders AS o
    WHERE o.customer_id=p_customer_id
    ORDER BY o.order_id;

    v_had_rows := FOUND;

    IF NOT v_had_rows THEN
        RAISE NOTICE 'Customer % chưa có order',p_customer_id;
    END IF;
END;
$$;
~~~

Thử:

~~~sql
SELECT *
FROM pl_diag_lab.list_customer_orders(101);
~~~

Kỳ vọng hai rows (orders 1001,1002).

### 25.2. RETURN QUERY đặt FOUND, nhưng không kết thúc hàm

`RETURN QUERY` thêm rows vào result set của set-returning PL/pgSQL function; flow có thể tiếp tục chạy các statements phía sau. `RETURN` riêng (không có expression ở set-returning function) kết thúc thực thi.

### 25.3. Trong các câu RETURN QUERY tiếp theo

Nếu function gọi nhiều RETURN QUERY, `FOUND` phản ánh câu RETURN QUERY vừa chạy gần nhất, không phải tự động “đã từng trả bất kỳ row nào trong cả function”. Muốn biết tổng rows trả, lập biến đếm hoặc thiết kế logic phù hợp.

### 25.4. Dynamic RETURN QUERY EXECUTE

Với set-returning function có dynamic SQL, `RETURN QUERY EXECUTE` cũng có thể đặt FOUND theo số rows được thêm. Đừng nhầm với `EXECUTE dynamic_sql INTO ...` thông thường, **không cập nhật FOUND**.

---

## 26. Trigger functions và FOUND

### 26.1. PL/pgSQL trigger có biến ngữ cảnh khác

Trong trigger function, bạn thường gặp `NEW`, `OLD`, `TG_OP`, `TG_TABLE_NAME`. Đây không phải các biến thay thế cho FOUND/ROW_COUNT.

- `NEW`: row mới trong tình huống áp dụng.
- `OLD`: row cũ trong tình huống áp dụng.
- `TG_OP`: INSERT/UPDATE/DELETE.
- `FOUND`: vẫn là trạng thái của những PL/pgSQL statements có cơ chế đặt FOUND.

### 26.2. Một trigger không tự biết affected rows tổng của statement qua FOUND

Trong row-level trigger, số rows của câu UPDATE nguyên gốc không đồng nghĩa một biến FOUND bên trong trigger tự nhận giá trị tương ứng. `FOUND` trong lần gọi trigger function là một trạng thái local cho SQL statements mà trigger function chạy.

### 26.3. DML từ trigger có thể ảnh hưởng command status được chụp

Nếu trigger function tự chạy INSERT/UPDATE/DELETE và bạn dùng `GET DIAGNOSTICS ROW_COUNT` bên trong, số này phản ánh SQL command gần nhất **trong trigger function** theo quy tắc PL/pgSQL, không phải luôn là số hàng thay đổi của câu DML bên ngoài.

### 26.4. Thiết kế audit trigger rõ ràng

Để audit từng row, dùng `NEW/OLD/TG_OP` theo trigger type; để audit số hàng của một batch DML, thường cần tổng hợp ở statement level, transition tables hoặc log từ layer thực hiện statement. Không dùng FOUND như một event bus toàn cục.

---

## 27. Logging bằng RAISE NOTICE và quản lý lỗi

### 27.1. RAISE với nhiều mức độ

Một số mức thường gặp:

~~~sql
RAISE DEBUG 'Debug information';
RAISE LOG 'Diagnostic event';
RAISE NOTICE 'Thông báo cho người gọi';
RAISE WARNING 'Cảnh báo';
RAISE EXCEPTION 'Dừng vì lỗi';
~~~

Các mức và nơi hiển thị/log phụ thuộc `client_min_messages`, `log_min_messages` và cấu hình hệ thống. **RAISE EXCEPTION** làm luồng chuyển sang handler hoặc trả lỗi cho caller.

### 27.2. Không log giá trị nhạy cảm tùy ý

Một exception detail có thể chứa primary key, email hoặc nhiều thông tin cá nhân. Cần phân biệt log nội bộ được phép truy cập và thông báo API cho người dùng cuối. Với `GET STACKED DIAGNOSTICS`, thường nên ghi SQLSTATE, constraint name và request correlation ID, còn message/detail/context chỉ theo chính sách cho phép.

### 27.3. Chụp ROW_COUNT trước khi log phức tạp

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

GET DIAGNOSTICS v_updated = ROW_COUNT;
v_found := FOUND;

RAISE NOTICE 'Updated % rows',v_updated;
~~~

Lệnh RAISE tự nó không phải DML, nhưng nếu logging helper gọi SQL, FOUND/ROW_COUNT có thể bị đổi; chụp trước mọi helper gọi SQL là thói quen tốt.

### 27.4. RAISE EXCEPTION không phải một giá trị trạng thái

Khi `RAISE EXCEPTION` được thực thi, code thường **không tiếp tục** ở dòng sau trong cùng normal path. Không viết:

~~~sql
RAISE EXCEPTION 'Không tìm thấy';
IF NOT FOUND THEN
    -- Không chạy trong normal path sau RAISE.
END IF;
~~~

Hãy xác định rõ API contract: **trả dữ liệu trạng thái**, hay **ném exception** khi không tìm thấy. Hai hướng có ưu/nhược khác nhau.

---

## 28. Tính đúng khi nhiều transaction cùng truy cập dữ liệu

### 28.1. FOUND=true không giữ khóa cho bước sau

Một query:

~~~sql
SELECT order_status INTO v_status
FROM pl_diag_lab.orders
WHERE order_id=p_id;

IF FOUND THEN
    -- Một transaction khác có thể đổi trạng thái sau SELECT.
END IF;
~~~

`FOUND=true` chỉ cho biết query vừa tìm thấy row tại snapshot thích hợp. Nó **không hứa** row hoặc status không bị transaction khác sửa sau đó.

### 28.2. Update có điều kiện thường tốt hơn SELECT rồi UPDATE rời rạc

Với nghiệp vụ chuyển new → paid:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=p_id
  AND order_status='new';
GET DIAGNOSTICS v_updated = ROW_COUNT;
~~~

Một statement giúp tránh nhiều lỗ hổng read-modify-write. Nếu có side effects khác (ví dụ trừ kho, tạo hóa đơn), cần một transaction bao nhiều thao tác, constraints/idempotency và lock design phù hợp.

### 28.3. SELECT FOR UPDATE

Nếu business thật sự cần đọc một row, quyết định và cập nhật nhiều bảng trong một transaction, có thể dùng:

~~~sql
SELECT order_status
INTO STRICT v_status
FROM pl_diag_lab.orders
WHERE order_id=p_id
FOR UPDATE;
~~~

`FOR UPDATE` khóa row đã chọn trong transaction theo quy tắc PostgreSQL; câu này không tự cập nhật status. Cần dùng một transaction boundary hợp lệ và xử lý deadlock/retry.

### 28.4. COUNT rồi INSERT có race

Sai ý tưởng:

~~~text
SELECT COUNT(*) INTO v_count FROM orders WHERE ...;
IF v_count=0 THEN
   INSERT ...;
END IF;
~~~

Hai transactions có thể cùng thấy count=0 rồi cùng INSERT. Dùng **UNIQUE constraint** và `INSERT ... ON CONFLICT` hoặc locking/isolation thích hợp để bảo đảm dữ liệu không trùng.

### 28.5. ROW_COUNT không thay ràng buộc dữ liệu

`ROW_COUNT=1` nói UPDATE vừa tác động một row; nó không chứng minh hàng đó hợp lệ theo mọi invariant nghiệp vụ nếu schema/policies/transactions không đúng. Ràng buộc ở database vẫn cần thiết.

### 28.6. Không nuốt serialization_failure

Trong isolation cao, lỗi `40001` có thể xuất hiện. Không bắt lỗi rồi trả “không tìm thấy hàng”. Cần retry toàn transaction từ lớp quản lý transaction, với chính sách backoff/giới hạn retry phù hợp.

---

## 29. Parameter naming: tránh nhầm cột và biến PL/pgSQL

### 29.1. Mẫu dễ mơ hồ

~~~sql
-- Tránh khi tên biến và cột giống nhau:
SELECT amount INTO amount
FROM pl_diag_lab.orders
WHERE order_id=order_id;
~~~

Tên `order_id` có thể vừa là cột vừa là biến, và điều kiện `order_id=order_id` có thể vô nghĩa hoặc gây ambiguity. PostgreSQL PL/pgSQL có quy tắc xử lý mơ hồ, có thể báo lỗi tùy cấu hình và ngữ cảnh.

### 29.2. Dùng prefix và table alias

~~~sql
SELECT o.amount
INTO v_amount
FROM pl_diag_lab.orders AS o
WHERE o.order_id=p_order_id;
~~~

- `p_` cho parameter.
- `v_` cho local variable.
- `o.` cho SQL column.

Cách này giúp giảm lỗi logic và dễ đọc khi SQL có nhiều JOINs.

### 29.3. Ký hiệu #variable_conflict không nên là cách sửa mặc định

PL/pgSQL có cơ chế như `#variable_conflict use_variable` hoặc các cấu hình tương đương để xử lý tên mơ hồ. Không dựa vào điều chỉnh cấu hình toàn cục để chữa một tên biến sai; dùng **alias và tên rõ ràng** an toàn hơn, đặc biệt trong function có quyền cao.

### 29.4. Tên biến trong dynamic SQL

~~~sql
EXECUTE 'SELECT amount FROM pl_diag_lab.orders WHERE order_id=$1'
INTO v_amount
USING p_order_id;
~~~

Trong dynamic statement, `$1` lấy từ `USING`, không phải tự truy cập biến PL/pgSQL bằng tên string. Khi muốn parameterize values, dùng `USING` thay ghép text.

---

## 30. Phân biệt GET DIAGNOSTICS ROW_COUNT và statement statistics

### 30.1. ROW_COUNT là kết quả một statement vừa chạy

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount*1.01
WHERE customer_id=101;

GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

Nó cho biết số rows được UPDATE trong lần statement này, không phải toàn bộ số rows của bảng hay tổng tất cả transactions.

### 30.2. ROW_COUNT không nói bao nhiêu rows thật sự đổi giá trị

~~~sql
UPDATE pl_diag_lab.orders
SET order_status=order_status
WHERE customer_id=101;
~~~

Các rows vẫn được UPDATE theo SQL, ngay cả khi giá trị logic không đổi. `ROW_COUNT` phản ánh số rows statement xử lý, **không phải** chỉ rows có giá trị mới khác giá trị cũ.

### 30.3. UPDATE WHERE không khớp vẫn thành công

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount+10
WHERE order_id=-12345;
~~~

`ROW_COUNT=0`; không có SQL exception. Ứng dụng phải tự quyết định đây là success-with-zero hay business error.

### 30.4. ROW_COUNT và triggers/rules

Trên bảng có triggers hoặc rewrite rules, hành vi cập nhật/affected row counts có thể phức tạp hơn trực giác “bao nhiêu row trước/sau”. Hãy hiểu command tag/row count của PostgreSQL theo statement thực, không coi nó là kiểm chứng tất cả side effects trong trigger và cascading operations.

### 30.5. ROW_COUNT và COUNT(*)

`SELECT COUNT(*)` trả về một row chứa số lượng rows thỏa predicate. `ROW_COUNT` sau statement SELECT INTO chỉ nói về rows kết quả statement xử lý, không thay biến count.

### 30.6. ROW_COUNT và pg_stat_statements

`pg_stat_statements` (nếu được cấu hình) thống kê theo query fingerprint qua nhiều calls, còn `GET DIAGNOSTICS ROW_COUNT` là trạng thái **của statement trong một lần function thực thi**. Không dùng một cái thay cái kia.

---

## 31. So sánh các cơ chế theo mục tiêu nghiệp vụ

| Cần làm gì? | Công cụ chính | Trạng thái nên đọc |
|---|---|---|
| Gán literal/tính toán | `v := expr` | Chính biến v |
| Chọn scalar từ row | `SELECT ... INTO` | Target + FOUND |
| Bắt query trả sai số hàng | `INTO STRICT` | Exceptions |
| Kiểm tra tồn tại, không cần dữ liệu | `PERFORM ... LIMIT 1` | FOUND |
| Kiểm tra tồn tại và lưu boolean | `SELECT EXISTS(...) INTO v_exists` | v_exists |
| Đếm tất cả matching rows | `COUNT(*) INTO v_count` | v_count |
| DML kiểm tra có row tác động | `UPDATE/DELETE/INSERT ...` | FOUND |
| DML đếm rows | `GET DIAGNOSTICS ... ROW_COUNT` | bigint v_rows |
| DML một row nhận giá trị mới | `... RETURNING ... INTO` | Target + FOUND |
| SQL động SELECT một row | `EXECUTE ... INTO ... USING` | Target + ROW_COUNT |
| SQL động DML | `EXECUTE ... USING` | ROW_COUNT |
| Theo dõi stack đang chạy | `GET DIAGNOSTICS ... PG_CONTEXT` | text context |
| Đọc thông tin lỗi đang bắt | `GET STACKED DIAGNOSTICS` | SQLSTATE, MESSAGE, DETAIL... |
| Bắt chính xác missing row | `INTO STRICT` + `WHEN NO_DATA_FOUND` | Handler |
| Lặp query nhiều rows | `FOR r IN SELECT ... LOOP` | r, counter, FOUND sau loop |
| Trả nhiều rows từ function | `RETURN QUERY` | Result set + FOUND |

---

## 32. Sơ đồ chọn kỹ thuật

~~~mermaid
flowchart TD
    A["Bài toán đọc hoặc thay đổi dữ liệu trong PL/pgSQL"] --> B{"Chỉ tính một biểu thức?"}
    B -- "Có" --> C["Biến := biểu thức"]
    B -- "Không" --> D{"Đọc hay ghi dữ liệu?"}
    D -- "Đọc" --> E{"Cần giá trị hay chỉ kiểm tra?"}
    E -- "Cần giá trị" --> F{"Phải đúng một row?"}
    F -- "Có" --> G["SELECT ... INTO STRICT"]
    F -- "Không" --> H["SELECT ... INTO; kiểm tra FOUND"]
    E -- "Chỉ tồn tại" --> I["PERFORM ...; kiểm tra FOUND"]
    E -- "Cần số lượng" --> J["SELECT COUNT(*) INTO v_count"]
    D -- "Ghi" --> K{"Có RETURNING một row?"}
    K -- "Có" --> L["DML ... RETURNING INTO"]
    K -- "Không" --> M["DML; GET DIAGNOSTICS ROW_COUNT"]
    H --> N{"SQL động EXECUTE?"}
    M --> N
    N -- "Có" --> O["EXECUTE ...; đọc ROW_COUNT, không dựa FOUND"]
    N -- "Không" --> P["Chụp FOUND/ROW_COUNT ngay sau statement"]
    G --> Q{"Exception xảy ra?"}
    L --> Q
    O --> Q
    Q -- "Có" --> R["EXCEPTION ... GET STACKED DIAGNOSTICS"]
    Q -- "Không" --> S["Trả kết quả theo API contract"]
    R --> T["Phân loại SQLSTATE, log an toàn, retry/rethrow"]
~~~

Không phải mọi nhánh đều yêu cầu function PL/pgSQL. Nếu một câu `UPDATE ... WHERE ... RETURNING` đơn giản đã làm đúng việc, viết SQL trực tiếp có thể rõ hơn một function hàng trăm dòng.

---

## 33. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Hướng xử lý |
|---|---|---|
| “`:=` và `=` luôn là cùng một toán tử” | Gán PL/pgSQL khác so sánh SQL | Dùng `:=` để gán và `=` để so sánh |
| “Biến không khởi tạo có giá trị 0” | Mặc định NULL | Xét NULL/DEFAULT |
| “SELECT INTO trong function tạo bảng” | PL/pgSQL INTO gán biến | Dùng CREATE TABLE AS SELECT |
| “SELECT INTO không STRICT báo lỗi nếu >1 rows” | Nó lấy một row đầu tiên | STRICT hoặc ORDER BY LIMIT 1 |
| “Hàng đầu tiên không ORDER BY luôn có PK nhỏ nhất” | Không có thứ tự bảo đảm | ORDER BY có tie-breaker |
| “SELECT INTO 0 rows giữ giá trị target cũ” | Nó gán NULL | FOUND false và kiểm tra target |
| “STRICT nghĩa giá trị cột không NULL” | STRICT kiểm số rows | NOT NULL/constraint nếu cần |
| “COUNT(*)=0 → FOUND=false” | Aggregate vẫn tạo một row | Kiểm tra v_count |
| “SELECT EXISTS(false) → FOUND=false” | SELECT EXISTS trả một row boolean false | Kiểm tra v_exists |
| “FOUND là trạng thái của SELECT đã chạy lâu trước đó” | Các statements có thể ghi đè | Chụp ngay |
| “FOUND=true nghĩa SQL transaction commit” | Chỉ row presence/affected status | Transaction control riêng |
| “FOUND biết số rows” | Boolean | GET DIAGNOSTICS ROW_COUNT |
| “FOUND sau EXECUTE phản ánh SQL động” | EXECUTE không cập nhật FOUND | ROW_COUNT hoặc INTO STRICT |
| “ROW_COUNT luôn là tổng số rows WHERE khớp” | Phản ánh SQL command gần nhất | COUNT(*) khi cần đếm |
| “ROW_COUNT sau COUNT(*) bằng giá trị COUNT” | COUNT(*) trả một row | Đọc target v_count |
| “ROW_COUNT sau PERFORM khác không phải lần SQL gần nhất” | Command status có thể bị thay đổi | Chụp ROW_COUNT ngay |
| “UPDATE SET x=x không tính row” | UPDATE vẫn xử lý row khớp | ROW_COUNT không đo chênh lệch giá trị |
| “DML RETURNING INTO không STRICT chọn row đầu” | Nhiều RETURNING rows có thể lỗi | DML count hoặc set-returning |
| “PERFORM không thay FOUND” | PERFORM có thay | Kiểm tra/ghi nhớ trạng thái |
| “FOR loop cập nhật FOUND trên mọi iteration theo cùng cách” | FOUND của FOR được đặt khi loop kết thúc | Đọc sau END LOOP |
| “GET DIAGNOSTICS dùng để lấy error message” | Current diagnostics có ROW_COUNT/PG_CONTEXT | GET STACKED trong handler |
| “PG_CONTEXT là vị trí lỗi gốc” | PG_CONTEXT là stack hiện tại | PG_EXCEPTION_CONTEXT trong handler |
| “SQLSTATE chỉ có trong app driver” | PL/pgSQL handler truy cập được | GET STACKED DIAGNOSTICS |
| “Mọi exception nên WHEN OTHERS RETURN NULL” | Nuốt lỗi logic/constraint/transaction | Catch cụ thể, rethrow |
| “Block EXCEPTION không rollback SQL đã chạy trước lỗi” | Thay đổi trong block được rollback khi lỗi được bắt | Hiểu subtransaction |
| “Các biến local rollback như row changes” | Biến giữ giá trị theo flow handler | Không dùng biến như bằng chứng commit |
| “SELECT thấy row thì row sẽ tồn tại mãi” | Concurrent transaction có thể đổi | Atomic DML/locking |
| “COUNT rồi INSERT bảo đảm unique” | Có race giữa transactions | UNIQUE + ON CONFLICT |
| “Tên cột và biến trùng không sao” | Ambiguous hoặc bug SQL | Prefix/alias rõ |
| “Dynamic SQL nên nối raw user input” | SQL injection và sai quoting | USING / format(%I) |
| “RAISE NOTICE là audit bảo mật tự động” | Log không thay transaction/audit policy | Logging control riêng |

---

## 34. Checklist viết PL/pgSQL có thể bảo trì

### 34.1. Biến và SQL

- [ ] Mỗi biến có kiểu và tên rõ (`p_`, `v_`).
- [ ] Dùng `%TYPE`/`%ROWTYPE` khi phù hợp.
- [ ] Xử lý NULL theo business contract.
- [ ] Có SQL column aliases để tránh ambiguity.
- [ ] Không dùng SELECT có output mà thiếu INTO/PERFORM/RETURN QUERY.
- [ ] SELECT một row không có ORDER BY nếu dữ liệu có nhiều row thì đã xác định rõ semantics.

### 34.2. Gán kết quả

- [ ] Query có thể trả 0 rows không? Nếu có, xử lý FOUND/STRICT.
- [ ] Query có thể trả nhiều rows không? Nếu cần đúng một, dùng STRICT hoặc constraint.
- [ ] `COUNT(*)`/`EXISTS` được hiểu là query trả một row, không phải FOUND của business condition.
- [ ] DML RETURNING scalar target không có khả năng trả nhiều rows ngoài ý muốn.
- [ ] Mọi thay đổi dữ liệu có `RETURNING INTO` chỉ khi cần và biết cardinality.

### 34.3. FOUND và ROW_COUNT

- [ ] Capture FOUND ngay sau statement cần theo dõi.
- [ ] Không dùng FOUND sau một PERFORM/SELECT/UPDATE khác.
- [ ] Dùng bigint cho ROW_COUNT.
- [ ] GET DIAGNOSTICS đặt ngay sau SQL tương ứng.
- [ ] Với dynamic EXECUTE không phụ thuộc FOUND cũ.
- [ ] Không nhầm ROW_COUNT với COUNT(*)/aggregate.
- [ ] FOR/FOREACH loop đọc FOUND ở thời điểm chính xác.

### 34.4. Ngoại lệ

- [ ] Bắt SQLSTATE/condition chính xác, tránh WHEN OTHERS không cần.
- [ ] GET STACKED DIAGNOSTICS trong handler, không phải current ROW_COUNT.
- [ ] Không log/return nhạy cảm PG_EXCEPTION_DETAIL.
- [ ] Exception subtransaction được hiểu; không suy biến local chứng minh commit.
- [ ] Nếu lỗi không xử lý được, RAISE lại.
- [ ] Deadlock/serialization được retry ở transaction boundary.

### 34.5. Hiệu năng và bảo mật

- [ ] SQL set-based thay vì loop row-by-row khi phù hợp.
- [ ] Có index hỗ trợ predicates chính.
- [ ] Không SELECT COUNT(*) chỉ để kiểm tra tồn tại nếu không cần count.
- [ ] Dynamic SQL dùng USING/format(%I) và whitelist identifiers.
- [ ] Functions có quyền execute và SECURITY DEFINER/INVOKER phù hợp.
- [ ] Có integration tests với dữ liệu 0/1/nhiều rows và lỗi constraint.
- [ ] Có cách rollback khi chạy DML thử nghiệm.

---

## 35. Bài toán ứng dụng 1: cập nhật tồn kho có kiểm soát

### 35.1. Yêu cầu

Một hệ thống cần trừ tồn kho của một mặt hàng. Nếu không đủ tồn, phải trả trạng thái khác với khi SKU không tồn tại. Nếu đủ tồn, update phải an toàn khi hai giao dịch cùng mua.

### 35.2. Schema minh họa riêng

~~~sql
CREATE TABLE pl_diag_lab.inventory (
    sku text PRIMARY KEY,
    available integer NOT NULL CHECK (available >= 0)
);

INSERT INTO pl_diag_lab.inventory(sku,available)
VALUES ('SKU-A',10),('SKU-B',0);
~~~

### 35.3. Hàm trừ tồn kho theo một UPDATE có điều kiện

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.reserve_inventory(
    p_sku text,
    p_quantity integer
)
RETURNS TABLE (
    reserved boolean,
    affected_rows bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity phải > 0'
            USING ERRCODE='22023'; -- invalid_parameter_value
    END IF;

    UPDATE pl_diag_lab.inventory AS i
       SET available = i.available - p_quantity
     WHERE i.sku = p_sku
       AND i.available >= p_quantity;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    reserved := (v_rows = 1);
    affected_rows := v_rows;

    RETURN NEXT;
END;
$$;
~~~

Ở đây UPDATE có predicate tồn kho và là statement atomic. `ROW_COUNT=1` nghĩa một row được giảm tồn; `ROW_COUNT=0` có thể là SKU không tồn tại **hoặc** không đủ tồn, cần thêm đường phân loại nếu API cần biết khác nhau.

### 35.4. Chạy thử có ROLLBACK

~~~sql
BEGIN;

SELECT * FROM pl_diag_lab.reserve_inventory('SKU-A',3);
SELECT sku,available FROM pl_diag_lab.inventory WHERE sku='SKU-A';

ROLLBACK;
~~~

Kỳ vọng function trả true,1; trong transaction tồn là 7 rồi ROLLBACK về 10.

### 35.5. Đừng tách thành COUNT rồi UPDATE thiếu điều kiện

Một thiết kế:

~~~text
SELECT available INTO v_stock;
IF v_stock >= quantity THEN
    UPDATE inventory SET available = available-quantity;
END IF;
~~~

có thể bị race giữa hai purchases khi không locking/isolation phù hợp. Query UPDATE có điều kiện trên available là mô hình an toàn hơn trong ví dụ này.

### 35.6. Vì sao FOUND chưa đủ nếu cần phân loại lý do?

`FOUND=false` sau UPDATE cho biết không có row nào thỏa cả SKU và available. Nếu business phải phân biệt “SKU not found” với “out of stock”, cần thêm SELECT/locking/transaction design; không có cách suy ra hai trạng thái chỉ từ boolean này.

---

## 36. Bài toán ứng dụng 2: batch UPDATE và audit số hàng

### 36.1. Yêu cầu

Báo cáo cần cập nhật hàng loạt những đơn new trước một ngày nhất định và lưu số hàng đã đổi.

~~~sql
CREATE TABLE pl_diag_lab.job_runs (
    run_id bigint PRIMARY KEY,
    job_name text NOT NULL,
    affected_rows bigint NOT NULL,
    finished_at timestamptz NOT NULL
);
~~~

### 36.2. Một hàm ghi audit trong cùng transaction

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.cancel_old_new_orders(
    p_before timestamptz,
    p_run_id bigint
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='canceled'
     WHERE order_status='new'
       AND created_at < p_before;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    INSERT INTO pl_diag_lab.job_runs
        (run_id,job_name,affected_rows,finished_at)
    VALUES
        (p_run_id,'cancel_old_new_orders',v_updated,clock_timestamp());

    RETURN v_updated;
END;
$$;
~~~

### 36.3. Chụp ROW_COUNT trước INSERT audit

Nếu bạn viết:

~~~sql
UPDATE orders SET ...;
INSERT INTO job_runs ...;
GET DIAGNOSTICS v_updated = ROW_COUNT;
~~~

`v_updated` sẽ phản ánh **INSERT audit** (thường một row), không phải UPDATE batch. Vì vậy phải lấy ROW_COUNT ngay sau UPDATE.

### 36.4. Chạy thử

~~~sql
BEGIN;

SELECT pl_diag_lab.cancel_old_new_orders(
    '2026-11-05 00:00:00+00',
    7001
);

SELECT * FROM pl_diag_lab.job_runs WHERE run_id=7001;

ROLLBACK;
~~~

Giá trị count phụ thuộc trạng thái dữ liệu lab lúc chạy. Nếu mới nạp dữ liệu ban đầu, orders 1001 và 1003 là new trước 05/11, nên **2 rows**; order 1005 có created_at 05/11 13:00 UTC nên không thỏa cận trước.

### 36.5. Lỗi UNIQUE khi ghi audit

Nếu run_id đã tồn tại, INSERT audit báo unique_violation và toàn bộ call trong transaction (không có handler nuốt lỗi) thất bại, làm UPDATE trước đó bị rollback theo transaction semantics. Nếu cần idempotency, phải thiết kế khóa job và `ON CONFLICT` phù hợp thay vì cố bỏ qua mọi unique_violation.

---

## 37. Bài toán ứng dụng 3: chẩn đoán lỗi khi nhập đơn

### 37.1. Hàm nhập đơn có bắt lỗi cụ thể

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.insert_order_safely(
    p_order_id bigint,
    p_customer_id bigint,
    p_amount numeric
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_state text;
    v_constraint text;
    v_message text;
BEGIN
    INSERT INTO pl_diag_lab.orders
        (order_id,customer_id,amount,order_status,created_at)
    VALUES
        (p_order_id,p_customer_id,p_amount,'new',clock_timestamp());

    RETURN 'created';
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_constraint = CONSTRAINT_NAME;

        IF v_constraint = 'orders_pkey' THEN
            RETURN 'duplicate_order_id';
        END IF;
        RAISE;
    WHEN foreign_key_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_constraint = CONSTRAINT_NAME,
            v_message = MESSAGE_TEXT;

        RETURN 'customer_not_found';
END;
$$;
~~~

### 37.2. Thử với dữ liệu lab

~~~sql
SELECT pl_diag_lab.insert_order_safely(
    1001,101,75.00
);
~~~

Kỳ vọng `duplicate_order_id` nếu PK tên mặc định là `orders_pkey` và order 1001 tồn tại.

~~~sql
SELECT pl_diag_lab.insert_order_safely(
    3001,9999,75.00
);
~~~

Kỳ vọng `customer_not_found` nếu FK tương ứng là lỗi đang gặp. Không có row mới được chèn khi exception được bắt.

### 37.3. Không làm mờ lỗi FK khác

Trong ví dụ đơn giản chỉ có một FK từ order đến customer nên code map mọi foreign_key_violation sang customer_not_found. Trong hệ thống thật có nhiều FKs, phải kiểm tra `CONSTRAINT_NAME`/`TABLE_NAME` và logic nghiệp vụ để phân biệt; nếu là constraint khác, nên `RAISE;` thay vì trả message sai.

### 37.4. Không để lộ PG_EXCEPTION_DETAIL ra API

Lỗi unique/FK có thể ghi thông tin giá trị khóa trong detail. API response nên trả error code có nghĩa và không tiết lộ thông tin bảng, khóa hay stack ngoài phạm vi được phép.

### 37.5. Bắt lỗi không biến operation thành committed

Function trả string `duplicate_order_id` chỉ có nghĩa nó đã bắt lỗi trong block của mình. Nếu có các thao tác khác trước đó trong cùng transaction, chúng còn phụ thuộc transaction boundary của caller. Không suy rằng một RETURN text đồng nghĩa COMMIT.

---

## 38. Bài toán ứng dụng 4: thay COUNT(*) bằng EXISTS/PERFORM

### 38.1. Khi chỉ cần biết khách hàng tồn tại

Cách có thể tốn thêm công việc:

~~~sql
SELECT COUNT(*) INTO v_count
FROM pl_diag_lab.customers
WHERE customer_status='active';

IF v_count > 0 THEN
    ...
END IF;
~~~

Một cách khác:

~~~sql
PERFORM 1
FROM pl_diag_lab.customers
WHERE customer_status='active'
LIMIT 1;

IF FOUND THEN
    ...
END IF;
~~~

Hoặc:

~~~sql
SELECT EXISTS (
    SELECT 1 FROM pl_diag_lab.customers
    WHERE customer_status='active'
) INTO v_exists;

IF v_exists THEN
    ...
END IF;
~~~

### 38.2. Khi cần số khách chính xác

Nếu nghiệp vụ thực sự cần báo “có N khách đang active”, COUNT(*) là hợp lý:

~~~sql
SELECT COUNT(*) INTO v_active_customers
FROM pl_diag_lab.customers
WHERE customer_status='active';
~~~

Đừng thay COUNT(*) bằng FOUND rồi cố dùng boolean để biểu diễn số lượng.

---

## 39. Tình huống thiết kế: đưa lỗi nào lên API?

| Hiện tượng trong PL/pgSQL | Có thể có ý nghĩa nghiệp vụ | Hành động phù hợp |
|---|---|---|
| SELECT INTO không thấy row | Không tìm thấy đối tượng | Trả not-found hoặc raise domain error |
| INTO STRICT NO_DATA_FOUND | Vi phạm precondition phải tồn tại | Catch khi app cho phép missing; khác thì raise |
| INTO STRICT TOO_MANY_ROWS | Query không duy nhất | Kiểm tra schema constraint/query; thường không nuốt |
| UPDATE ROW_COUNT=0 | Không có row thỏa điều kiện | Có thể missing hoặc state conflict; phân biệt nếu cần |
| UPDATE ROW_COUNT=1 | Đã xử lý một row | Trả trạng thái thành công nếu các bước còn lại thành công |
| UPDATE ROW_COUNT>1 | Batch thành công theo set-based logic | Trả count/audit khi đúng |
| unique_violation | Khóa đã tồn tại | Map đúng constraint hoặc ON CONFLICT |
| foreign_key_violation | Tham chiếu không hợp lệ | Map theo constraint, tránh lỗi nhầm |
| serialization_failure | Cần retry transaction | Retry ở transaction boundary |
| deadlock_detected | Cần retry/điều tra lock order | Không coi là missing row |
| permission denied | Role không có quyền | Không che như dữ liệu trống |
| division_by_zero | Lỗi logic/input | Fix/validate, rethrow đúng cách |

---

## 40. Khi nào nên dùng function PL/pgSQL và khi nào SQL thuần là đủ?

Không phải mọi lần đọc ROW_COUNT đều yêu cầu stored function.

### 40.1. SQL thuần trong ứng dụng

Nhiều driver cung cấp affected-row count từ kết quả thực thi:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=$1
  AND order_status='new';
~~~

Ứng dụng có thể nhận row count từ driver/database protocol, không cần một function chỉ để gọi GET DIAGNOSTICS.

### 40.2. PL/pgSQL có lợi khi

- Cần phối hợp nhiều SQL statements trong logic gần dữ liệu.
- Cần control flow có IF/LOOP/EXCEPTION.
- Cần trả status, row count, computed results theo contract.
- Cần xử lý lỗi dựa vào SQLSTATE/constraint name trong DB.
- Muốn áp ràng buộc thứ tự operations và atomic transaction semantics rõ ràng.

### 40.3. SQL một statement có thể đơn giản và hiệu quả hơn

Nếu chỉ muốn:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=$1 AND order_status='new'
RETURNING order_id;
~~~

một SQL statement đã trả đủ thông tin "có row update hay không" cho ứng dụng. Không thêm 100 dòng PL/pgSQL chỉ để xử lý câu này nếu nghiệp vụ không yêu cầu.

### 40.4. Đừng biến function thành vòng lặp DML không cần thiết

Sai hướng hiệu năng:

~~~text
FOR every order:
    UPDATE orders SET ...
END LOOP
~~~

Nếu một câu UPDATE set-based xử lý toàn bộ điều kiện đúng và không cần side effects theo từng row, set-based SQL thường tối ưu hơn. `GET DIAGNOSTICS ROW_COUNT` giúp nhận tổng số rows của một statement batch.

---

## 41. Tài liệu tham khảo PostgreSQL

Khi triển khai với một major version PostgreSQL cụ thể, nên đối chiếu tài liệu chính thức:

- [PL/pgSQL — Structure](https://www.postgresql.org/docs/current/plpgsql-structure.html): cấu trúc block, DECLARE, BEGIN/END, EXCEPTION.
- [PL/pgSQL — Declarations](https://www.postgresql.org/docs/current/plpgsql-declarations.html): biến, %TYPE, %ROWTYPE, RECORD, CONSTANT.
- [PL/pgSQL — Basic Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html): assignment, SELECT INTO, STRICT, PERFORM, EXECUTE, GET DIAGNOSTICS.
- [PL/pgSQL — Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): FOUND, loops, RETURN QUERY, exception handling.
- [PL/pgSQL — Error Reporting](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): RAISE, error levels, SQLSTATE, MESSAGE/DETAIL/HINT.
- [PL/pgSQL — Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): NEW, OLD, TG_OP và ngữ cảnh trigger.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE mapping.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): concurrency, MVCC, serialization failures.
- [PostgreSQL — Data Manipulation RETURNING](https://www.postgresql.org/docs/current/dml-returning.html): giá trị trả về sau DML.

`/current/` có thể trỏ major version mới hơn server bạn đang vận hành. Với cú pháp hoặc hành vi phụ thuộc phiên bản, xem tài liệu chính xác theo major version, không đoán dựa trên SQL của một môi trường khác.

---

## 42. Bài tập thực hành

Các bài dùng dữ liệu `pl_diag_lab` ở phần 5, trừ khi nói rõ. Nếu bạn đã chạy các ví dụ DML làm thay đổi orders, kết quả thực tế có thể khác. Để kiểm tra đáp án theo bộ dữ liệu gốc, dùng database lab mới hoặc chạy thay đổi trong transaction rồi `ROLLBACK`. Các code snippets trong đề có thể cố ý sai để người học sửa; không chạy trên production.

### Bài 1 — Khai báo và gán biến

Viết một `DO` block khai báo `v_price numeric(12,2)` mặc định 150.00 và `v_tax_rate numeric` mặc định 0.1. Gán `v_total := v_price * (1+v_tax_rate)` và in kết quả bằng `RAISE NOTICE`.

### Bài 2 — NULL và phép gán

Một biến `v_a integer` không có giá trị khởi tạo. Giá trị của `v_b := v_a + 5` là gì? Viết cách nhận `v_b=5` khi v_a NULL mà không thay đổi nghĩa giá trị gốc của `v_a`.

### Bài 3 — %TYPE

Khai báo một biến có cùng kiểu với cột `pl_diag_lab.orders.amount`. Gán nó bằng `199.90`.

### Bài 4 — %ROWTYPE

Viết khối `DO` dùng `%ROWTYPE` để đọc toàn bộ hàng khách hàng ID 101 và in `customer_code`, `customer_name`.

### Bài 5 — record

Viết query `SELECT ... INTO` từ JOIN customers/orders, tổng số đơn và tổng tiền theo customer 101, gán vào biến `record`, sau đó in hai trường aggregate.

### Bài 6 — SELECT INTO và bảng mới

Trong PL/pgSQL, câu `SELECT ... INTO new_table FROM ...` tạo bảng hay gán biến? Cú pháp nào nên dùng nếu mục tiêu thật sự là tạo bảng từ SELECT?

### Bài 7 — SELECT INTO một hàng

Viết function `get_customer_code(p_id bigint) RETURNS text` dùng `SELECT customer_code INTO v_code ... WHERE customer_id=p_id`, trả NULL nếu không tìm thấy.

### Bài 8 — SELECT INTO không có hàng

~~~sql
DECLARE
  v_name text := 'initial';
BEGIN
  SELECT customer_name INTO v_name
  FROM pl_diag_lab.customers
  WHERE customer_id=999;
END;
~~~

Sau SELECT, v_name và FOUND là gì? Tại sao không giữ 'initial'?

### Bài 9 — Nhiều rows không STRICT

~~~sql
SELECT order_id INTO v_id
FROM pl_diag_lab.orders
WHERE customer_id=101;
~~~

Có hai orders. PL/pgSQL báo TOO_MANY_ROWS không? v_id có luôn 1001 không?

### Bài 10 — ORDER BY và LIMIT

Viết lại bài 9 để lấy order mới nhất theo `created_at`, tie-breaker `order_id`. Dùng `LIMIT 1` có chứng minh customer chỉ có một order không?

### Bài 11 — INTO STRICT không có hàng

Viết `DO` block dùng `SELECT ... INTO STRICT` tìm customer 999 và bắt `NO_DATA_FOUND` để in Notice.

### Bài 12 — INTO STRICT nhiều rows

Viết `DO` block query order_id theo customer 101 và bắt `TOO_MANY_ROWS`.

### Bài 13 — STRICT và cột NULL

Một query trả đúng một row với `optional_note=NULL`. `INTO STRICT` có báo NO_DATA_FOUND không? Vì sao?

### Bài 14 — COUNT(*) và FOUND

~~~sql
SELECT COUNT(*) INTO v_count
FROM pl_diag_lab.orders
WHERE customer_id=999;
~~~

Giá trị v_count, FOUND dự kiến là gì? Vì sao?

### Bài 15 — EXISTS và FOUND

~~~sql
SELECT EXISTS(
   SELECT 1 FROM pl_diag_lab.orders WHERE customer_id=999
) INTO v_exists;
~~~

Giá trị v_exists và FOUND là gì? Nên dùng biến nào để kiểm tra có đơn hay không?

### Bài 16 — PERFORM

Viết câu `PERFORM` kiểm tra có ít nhất một order thuộc customer 101; sau đó `IF FOUND` in "exists".

### Bài 17 — FOUND bị ghi đè

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=999;

PERFORM 1;

IF FOUND THEN
    RAISE NOTICE 'customer found';
END IF;
~~~

Vì sao mã này sai? Sửa bằng biến boolean `v_customer_found`.

### Bài 18 — FOUND lúc mới vào function

FOUND có giá trị khởi đầu là gì trong mỗi lần gọi PL/pgSQL function? Nó có chia sẻ giữa hai sessions hoặc hai function calls không?

### Bài 19 — FOUND với FOR LOOP

Viết `FOR r IN SELECT ... LOOP` duyệt orders customer 101, đếm số lần lặp, và đọc FOUND sau `END LOOP`. Nếu không có order, FOUND sau loop là gì?

### Bài 20 — FOUND với FOREACH

Viết FOREACH qua `ARRAY[2,4,6]::integer[]` để tính tổng và in FOUND sau loop. Từ vòng lặp rỗng, FOUND sẽ là gì?

### Bài 21 — UPDATE 0 hàng

Viết UPDATE trên order ID -1 và sau đó in FOUND cùng ROW_COUNT. Đó có phải SQL exception không?

### Bài 22 — ROW_COUNT datatype

Tại sao biến để chứa `ROW_COUNT` nên khai báo `bigint` thay vì `integer` trong batch jobs lớn?

### Bài 23 — Bẫy ROW_COUNT sau lệnh khác

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

INSERT INTO pl_diag_lab.job_runs(...);

GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

v_count phản ánh câu nào? Sửa vị trí GET DIAGNOSTICS để có số rows UPDATE.

### Bài 24 — UPDATE RETURNING INTO

Viết SQL cập nhật amount của order 1001 thêm 10 và lấy amount mới vào biến `v_new_amount`. Đọc FOUND và ROW_COUNT.

### Bài 25 — DML RETURNING nhiều rows

~~~sql
UPDATE pl_diag_lab.orders
SET amount=amount
WHERE customer_id=101
RETURNING order_id INTO v_order_id;
~~~

Vì sao câu này có thể báo lỗi dù không có `STRICT`? Nếu chỉ muốn đếm số hàng tác động, làm thế nào?

### Bài 26 — SELECT COUNT và ROW_COUNT

Sau `SELECT COUNT(*) INTO v_count FROM orders WHERE status='new'`, tại sao `GET DIAGNOSTICS v_rows=ROW_COUNT` không thể dùng thay `v_count` để biết số đơn new?

### Bài 27 — EXECUTE không đặt FOUND

Trước khi EXECUTE, `PERFORM 1` đặt FOUND=true. Dynamic SELECT INTO customer 999 không trả row. FOUND sau EXECUTE là gì? Nên dùng gì để biết query động không tìm thấy?

### Bài 28 — EXECUTE INTO STRICT

Viết dynamic SQL lấy customer_name theo customer_id bằng `EXECUTE ... INTO STRICT ... USING ...`. Khi không có customer, lỗi nào phát sinh?

### Bài 29 — Dynamic SQL injection

Một function nhận tên bảng và customer ID. Viết dynamic SELECT COUNT(*) an toàn, dùng `format('%I.%I')` cho schema/table và `USING` cho customer ID. Vì sao không ghép thẳng input?

### Bài 30 — GET DIAGNOSTICS PG_CONTEXT

Viết khối PL/pgSQL lưu `PG_CONTEXT` vào biến text và in một Notice. Context này có phải đường stack gốc của exception trước đó không?

### Bài 31 — GET STACKED DIAGNOSTICS

Viết `DO` block cố ý vi phạm unique PK customer 101, bắt `unique_violation` và lấy `RETURNED_SQLSTATE`, `CONSTRAINT_NAME`, `MESSAGE_TEXT`.

### Bài 32 — SQLSTATE thông dụng

Cho các SQLSTATE: `23505`, `23503`, `P0002`, `P0003`, `40001`. Ghép với unique_violation, foreign_key_violation, no_data_found, too_many_rows, serialization_failure.

### Bài 33 — PG_CONTEXT và PG_EXCEPTION_CONTEXT

Trong handler, bạn muốn biết dòng lỗi phát sinh và dòng handler đang thực thi. Sử dụng hai diagnostic items nào? Vì sao không thay thế nhau?

### Bài 34 — EXCEPTION subtransaction

Một khối có EXCEPTION INSERT customer 900, đặt `v_step='after insert'` rồi INSERT customer 101 gây unique_violation. Sau khi bắt lỗi, customer 900 còn trong bảng không? Biến v_step giữ giá trị gì?

### Bài 35 — Khi nào rethrow?

Một function bắt `WHEN OTHERS`, ghi SQLSTATE rồi trả NULL. Nêu ba rủi ro và viết mẫu `RAISE;` phát lại lỗi trong handler.

### Bài 36 — Bẫy COUNT rồi INSERT

Hai transactions cùng `SELECT COUNT(*)=0` rồi INSERT với cùng key. Tại sao có race? Cần ràng buộc database nào và SQL pattern nào để chống duplicate?

### Bài 37 — SELECT FOR UPDATE

Khi cần đọc amount, kiểm tra điều kiện nghiệp vụ và cập nhật nhiều bảng trong transaction, `SELECT ... FOR UPDATE` giúp gì? FOUND=true có thay cho row lock không?

### Bài 38 — Tính lại trạng thái từ ROW_COUNT

Hàm đánh dấu paid dùng UPDATE `WHERE order_id=p_id AND order_status='new'`. `ROW_COUNT=0` có thể có ít nhất hai nguyên nhân nào? Làm cách nào để phân biệt khi nghiệp vụ yêu cầu?

### Bài 39 — Thực hành job audit

Viết function `cancel_old_new_orders(p_before timestamptz) RETURNS bigint`, đổi những order new trước p_before thành canceled và trả affected-row count. Không cần ghi audit table.

### Bài 40 — Dữ liệu lớn và set-based SQL

Một function loop qua 100.000 orders và UPDATE từng row. Cách nào thường phù hợp hơn nếu mọi rows cùng quy tắc? Cách lấy affected count?

### Bài 41 — Tên biến bị mơ hồ

Sửa SQL có biểu thức `WHERE order_id=order_id` trong function nhận `p_order_id` để so chính xác với cột bảng. Dùng table alias.

### Bài 42 — Trigger và FOUND

Vì sao FOUND trong một trigger function không tự trả affected-row count của DML statement bên ngoài? Nên dùng gì để biết OLD/NEW row values?

### Bài 43 — Transaction rollback khi test DML

Viết khối test `BEGIN; DO $$ ... UPDATE ... GET DIAGNOSTICS ... $$; ROLLBACK;` để đo số rows chuyển trạng thái new→paid nhưng không giữ thay đổi.

### Bài 44 — Tổng hợp

Một API gọi stored function để:
1. Chọn khách hàng theo code.
2. Nếu không có thì trả "customer_not_found".
3. Nếu có, cập nhật đơn new thành paid theo customer đó.
4. Trả số rows cập nhật.
5. Khi lỗi FK/UNIQUE, ghi SQLSTATE an toàn và không biến lỗi thành "không tìm thấy".

Hãy viết giả mã PL/pgSQL, lựa chọn SELECT INTO/FOUND/ROW_COUNT/GET STACKED DIAGNOSTICS thích hợp và giải thích điểm đặt diagnostics.

---

## 43. Lời giải và hướng dẫn thực hành — bài 1 đến 22

### Bài 1 — Gán biến

~~~sql
DO $$
DECLARE
    v_price numeric(12,2) := 150.00;
    v_tax_rate numeric := 0.1;
    v_total numeric(12,2);
BEGIN
    v_total := v_price * (1 + v_tax_rate);
    RAISE NOTICE 'Tổng=%',v_total;
END $$;
~~~

Kỳ vọng kết quả bằng **165.00**. `:=` là phép gán trong PL/pgSQL; các phép toán số học ở vế phải được tính theo kiểu của biểu thức và assignment vào target.

### Bài 2 — NULL

Nếu `v_a` chưa khởi tạo, nó là NULL; `v_a+5` cũng NULL theo SQL NULL propagation.

~~~sql
DO $$
DECLARE
    v_a integer;
    v_b integer;
BEGIN
    v_b := COALESCE(v_a,0) + 5;
    RAISE NOTICE 'v_a=%, v_b=%',v_a,v_b;
END $$;
~~~

`v_b=5`, còn `v_a` vẫn NULL. Chỉ dùng quy tắc NULL→0 khi business cho phép.

### Bài 3 — %TYPE

~~~sql
DO $$
DECLARE
    v_price pl_diag_lab.orders.amount%TYPE;
BEGIN
    v_price := 199.90;
    RAISE NOTICE 'price=%',v_price;
END $$;
~~~

`%TYPE` lấy kiểu từ cột `amount` của bảng đã có.

### Bài 4 — %ROWTYPE

~~~sql
DO $$
DECLARE
    v_customer pl_diag_lab.customers%ROWTYPE;
BEGIN
    SELECT *
      INTO v_customer
      FROM pl_diag_lab.customers
     WHERE customer_id=101;

    IF FOUND THEN
        RAISE NOTICE 'Code=%, name=%',
            v_customer.customer_code,
            v_customer.customer_name;
    END IF;
END $$;
~~~

Với lab gốc, code `C101` và tên `An`. Target dạng row có các field tương ứng bảng.

### Bài 5 — RECORD và GROUP BY

~~~sql
DO $$
DECLARE
    v_result record;
BEGIN
    SELECT
        c.customer_id,
        COUNT(o.order_id) AS number_of_orders,
        COALESCE(SUM(o.amount),0) AS total_amount
    INTO v_result
    FROM pl_diag_lab.customers AS c
    LEFT JOIN pl_diag_lab.orders AS o
      ON o.customer_id=c.customer_id
    WHERE c.customer_id=101
    GROUP BY c.customer_id;

    IF FOUND THEN
        RAISE NOTICE 'orders=%, total=%',
            v_result.number_of_orders,
            v_result.total_amount;
    END IF;
END $$;
~~~

Kỳ vọng `number_of_orders=2`, `total_amount=375.50` trong lab gốc. Nếu customer 999 không tồn tại, query với GROUP BY sẽ không có row, FOUND=false.

### Bài 6 — SELECT INTO của PL/pgSQL

Trong PL/pgSQL, `SELECT ... INTO target` là cú pháp **gán vào biến**. Nếu cần tạo một bảng mới từ SELECT, dùng SQL:

~~~sql
CREATE TABLE pl_diag_lab.customers_copy AS
SELECT *
FROM pl_diag_lab.customers;
~~~

Lệnh này tạo dữ liệu bảng copy, không tự bảo đảm copy các PK, FK, index, trigger, grants của bảng gốc. Chỉ chạy khi muốn tạo đối tượng lab mới.

### Bài 7 — Function đọc customer code

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.get_customer_code(
    p_id bigint
)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_code text;
BEGIN
    SELECT c.customer_code
      INTO v_code
      FROM pl_diag_lab.customers AS c
     WHERE c.customer_id=p_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN v_code;
END;
$$;
~~~

Thử:

~~~sql
SELECT pl_diag_lab.get_customer_code(101),
       pl_diag_lab.get_customer_code(999);
~~~

Kỳ vọng `C101` và NULL.

### Bài 8 — Zero rows

Sau SELECT:

- `v_name=NULL`.
- `FOUND=false`.

PL/pgSQL gán NULL vào target của SELECT INTO không STRICT khi không có row, không giữ giá trị cũ `'initial'`. Muốn giá trị fallback:

~~~sql
SELECT customer_name INTO v_name
FROM pl_diag_lab.customers
WHERE customer_id=999;

IF NOT FOUND THEN
    v_name := 'unknown';
END IF;
~~~

Dùng FOUND để phân biệt row not found; không dựa vào một giá trị cột có thể NULL hợp lệ.

### Bài 9 — Multiple rows

Không STRICT, `SELECT INTO` lấy một row đầu tiên do executor trả, **không tự TOO_MANY_ROWS**. Vì không `ORDER BY`, `v_id` không được bảo đảm là 1001 hoặc 1002 theo bất kỳ thứ tự nghiệp vụ nào.

### Bài 10 — Lấy đơn mới nhất

~~~sql
SELECT o.order_id
INTO v_id
FROM pl_diag_lab.orders AS o
WHERE o.customer_id=101
ORDER BY o.created_at DESC,o.order_id DESC
LIMIT 1;
~~~

Trong lab ban đầu, order 1002 mới hơn 1001. `LIMIT 1` thể hiện “chọn một row”, không xác minh customer chỉ có một order.

### Bài 11 — NO_DATA_FOUND

~~~sql
DO $$
DECLARE
    v_name text;
BEGIN
    SELECT c.customer_name
    INTO STRICT v_name
    FROM pl_diag_lab.customers AS c
    WHERE c.customer_id=999;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE NOTICE 'Không có customer 999';
END $$;
~~~

`SELECT INTO STRICT` phát `NO_DATA_FOUND` (SQLSTATE `P0002`) khi query không trả row.

### Bài 12 — TOO_MANY_ROWS

~~~sql
DO $$
DECLARE
    v_id bigint;
BEGIN
    SELECT o.order_id
    INTO STRICT v_id
    FROM pl_diag_lab.orders AS o
    WHERE o.customer_id=101;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE NOTICE 'Có nhiều order';
END $$;
~~~

Trong lab gốc có hai orders 1001 và 1002. STRICT yêu cầu đúng một row, nên báo `TOO_MANY_ROWS` (SQLSTATE `P0003`).

### Bài 13 — STRICT không cấm NULL ở cột

Nếu query trả **đúng một row** nhưng column value NULL, `INTO STRICT` **thành công** và target nhận NULL. STRICT kiểm tra cardinality row, không thay NOT NULL constraint. Điều kiện NOT NULL cần được schema/validation bảo vệ riêng.

### Bài 14 — COUNT(*) và FOUND

`v_count=0`, **`FOUND=true`**, vì aggregate `COUNT(*)` không GROUP BY tạo **một row** với số 0. Muốn kiểm tra có đơn hay không, dùng `IF v_count>0`, không `IF FOUND`.

### Bài 15 — EXISTS và FOUND

`v_exists=false`, **`FOUND=true`**. SELECT EXISTS trả một row boolean false, nên FOUND phản ánh statement đã trả row. Kiểm tra `v_exists`.

### Bài 16 — PERFORM

~~~sql
DO $$
BEGIN
    PERFORM 1
    FROM pl_diag_lab.orders
    WHERE customer_id=101
    LIMIT 1;

    IF FOUND THEN
        RAISE NOTICE 'exists';
    END IF;
END $$;
~~~

`PERFORM` bỏ kết quả row, nhưng cập nhật FOUND theo việc query có tạo row hay không.

### Bài 17 — FOUND bị ghi đè

Đoạn đầu SELECT không có row nên `FOUND=false`. `PERFORM 1` tạo một row và đặt `FOUND=true`, khiến IF sai về customer.

Sửa:

~~~sql
DO $$
DECLARE
    v_name text;
    v_customer_found boolean;
BEGIN
    SELECT customer_name INTO v_name
    FROM pl_diag_lab.customers
    WHERE customer_id=999;

    v_customer_found := FOUND;

    PERFORM 1;

    IF v_customer_found THEN
        RAISE NOTICE 'customer found';
    ELSE
        RAISE NOTICE 'customer not found';
    END IF;
END $$;
~~~

### Bài 18 — Trạng thái ban đầu

`FOUND=false` tại đầu mỗi lần gọi PL/pgSQL function. Nó là biến local của invocation; không dùng chung giữa hai sessions hoặc là trạng thái vĩnh viễn giữa hai lần gọi function.

Nếu một SQL statement thay FOUND trong một function được gọi lồng bên trong, nó không có nghĩa caller tự nhận giá trị FOUND của function con; caller có trạng thái riêng theo statement gọi function.

### Bài 19 — FOR query

~~~sql
DO $$
DECLARE
    r record;
    v_count integer := 0;
    v_loop_had_rows boolean;
BEGIN
    FOR r IN
        SELECT order_id
        FROM pl_diag_lab.orders
        WHERE customer_id=101
        ORDER BY order_id
    LOOP
        v_count := v_count+1;
    END LOOP;

    v_loop_had_rows := FOUND;
    RAISE NOTICE 'iterations=%, found=%',
        v_count,v_loop_had_rows;
END $$;
~~~

Kỳ vọng `v_count=2` và FOUND true sau loop. Nếu query trả 0 rows, loop không chạy, FOUND sau END LOOP là false.

### Bài 20 — FOREACH

~~~sql
DO $$
DECLARE
    v_number integer;
    v_sum integer := 0;
    v_had_iterations boolean;
BEGIN
    FOREACH v_number IN ARRAY ARRAY[2,4,6]::integer[]
    LOOP
        v_sum := v_sum + v_number;
    END LOOP;

    v_had_iterations := FOUND;

    RAISE NOTICE 'sum=%, found=%',v_sum,v_had_iterations;
END $$;
~~~

Kỳ vọng `sum=12`, FOUND true. Với `ARRAY[]::integer[]`, không có iteration và FOUND false khi loop kết thúc.

### Bài 21 — UPDATE zero rows

~~~sql
DO $$
DECLARE
    v_rows bigint;
    v_found boolean;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_id=-1;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'found=%, row_count=%',
        v_found,v_rows;
END $$;
~~~

Kỳ vọng `found=false`, `row_count=0`. UPDATE 0 rows là một statement thành công, **không tự có exception**.

### Bài 22 — ROW_COUNT bigint

Một batch UPDATE trên hàng tỷ rows có thể vượt giới hạn số nguyên signed 32-bit của `integer` (khoảng 2,147 tỷ). `ROW_COUNT` nên nhận bằng `bigint` để có khoảng giá trị đủ lớn và thể hiện đúng loại thông tin từ PostgreSQL.

---

## 44. Lời giải và hướng dẫn thực hành — bài 23 đến 44

### Bài 23 — Đặt GET DIAGNOSTICS sát UPDATE

Trong code ban đầu, `GET DIAGNOSTICS ROW_COUNT` được gọi sau INSERT vào `job_runs` nên **không** phản ánh UPDATE batch, mà phản ánh lệnh SQL gần nhất.

Sửa:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_status='new';

GET DIAGNOSTICS v_updated = ROW_COUNT;

INSERT INTO pl_diag_lab.job_runs
    (run_id,job_name,affected_rows,finished_at)
VALUES
    (7002,'mark_orders_paid',v_updated,clock_timestamp());
~~~

Giả sử `job_runs` đã được tạo và run_id=7002 chưa tồn tại. Khi chỉ thử nghiệm, bọc transaction rồi ROLLBACK.

### Bài 24 — UPDATE RETURNING INTO

~~~sql
DO $$
DECLARE
    v_new_amount numeric(12,2);
    v_found boolean;
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount+10
     WHERE order_id=1001
     RETURNING amount INTO v_new_amount;

    v_found := FOUND;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'amount=%, found=%, count=%',
        v_new_amount,v_found,v_rows;
END $$;
~~~

Với order 1001 tồn tại, `ROW_COUNT=1` và FOUND true. Vì đây là DML thật, nên nếu muốn giữ dữ liệu gốc, thực thi trong `BEGIN; ... ROLLBACK;` ở lab.

### Bài 25 — RETURNING nhiều rows

UPDATE theo `customer_id=101` tác động hai orders. Khi có `RETURNING order_id INTO v_order_id` scalar, PL/pgSQL có thể báo `TOO_MANY_ROWS` **kể cả khi không STRICT**.

Nếu chỉ cần số hàng:

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=amount
     WHERE customer_id=101;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RAISE NOTICE 'updated=%',v_rows;
END $$;
~~~

Ở bộ dữ liệu gốc, v_rows=2. Nếu cần mọi order IDs, phải dùng SQL trả set hoặc xử lý RETURNING dưới dạng kết quả nhiều hàng phù hợp, không một biến scalar duy nhất.

### Bài 26 — COUNT(*) không phải ROW_COUNT

`SELECT COUNT(*)` không GROUP BY tạo **một row** có giá trị count. `v_count` chứa tổng số orders new; `ROW_COUNT` mô tả lượng row SQL gần nhất xử lý/return, không nhất thiết bằng tổng count. Vì vậy phải dùng `v_count` để biết có bao nhiêu orders new.

### Bài 27 — Dynamic EXECUTE không đặt FOUND

`FOUND` còn true từ `PERFORM 1` trước đó. Dynamic SQL không tìm thấy customer nhưng `EXECUTE` không cập nhật biến đặc biệt FOUND.

~~~sql
DO $$
DECLARE
    v_name text;
    v_rows bigint;
BEGIN
    PERFORM 1;

    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
         WHERE customer_id=$1'
    INTO v_name
    USING 999;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows=0 THEN
        RAISE NOTICE 'Dynamic query không tìm thấy customer';
    END IF;
END $$;
~~~

Nếu cần bắt ngoại lệ khi không đúng một row, dùng dynamic `INTO STRICT`.

### Bài 28 — Dynamic INTO STRICT

~~~sql
DO $$
DECLARE
    v_name text;
    p_customer_id bigint := 999;
BEGIN
    EXECUTE
        'SELECT customer_name FROM pl_diag_lab.customers
         WHERE customer_id=$1'
    INTO STRICT v_name
    USING p_customer_id;

    RAISE NOTICE 'name=%',v_name;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE NOTICE 'Không có customer %',p_customer_id;
END $$;
~~~

Với ID 999, dynamic SELECT không trả hàng và `INTO STRICT` báo `NO_DATA_FOUND`.

### Bài 29 — Dynamic SQL an toàn

~~~sql
DO $$
DECLARE
    v_schema text := 'pl_diag_lab';
    v_table text := 'customers';
    p_customer_id bigint := 101;
    v_count bigint;
BEGIN
    IF v_schema <> 'pl_diag_lab'
       OR v_table <> 'customers' THEN
        RAISE EXCEPTION 'Table không được phép';
    END IF;

    EXECUTE format(
        'SELECT COUNT(*) FROM %I.%I WHERE customer_id=$1',
        v_schema,v_table
    )
    INTO v_count
    USING p_customer_id;

    RAISE NOTICE 'count=%',v_count;
END $$;
~~~

`%I` quote **identifier** đúng; `USING` bind **data value**, giảm SQL injection và lỗi escaping. Trong function nhận tên bảng từ user, cần whitelist schema/table thực sự được phép, không chỉ quote rồi cho truy cập bất kỳ đối tượng.

### Bài 30 — PG_CONTEXT

~~~sql
DO $$
DECLARE
    v_current_context text;
BEGIN
    GET DIAGNOSTICS v_current_context=PG_CONTEXT;
    RAISE NOTICE 'Current context: %',v_current_context;
END $$;
~~~

PG_CONTEXT là stack **hiện tại** tại lệnh GET DIAGNOSTICS, không phải traceback gốc của một lỗi đã xảy ra trước. Trong handler muốn vị trí lỗi, dùng `GET STACKED DIAGNOSTICS ... PG_EXCEPTION_CONTEXT`.

### Bài 31 — Bắt unique_violation

~~~sql
DO $$
DECLARE
    v_state text;
    v_constraint text;
    v_message text;
BEGIN
    INSERT INTO pl_diag_lab.customers
        (customer_id,customer_code,customer_name,customer_status)
    VALUES
        (101,'C101X','Duplicate','active');
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state=RETURNED_SQLSTATE,
            v_constraint=CONSTRAINT_NAME,
            v_message=MESSAGE_TEXT;

        RAISE NOTICE 'state=%, constraint=%, message=%',
            v_state,v_constraint,v_message;
END $$;
~~~

Dự kiến SQLSTATE `23505`. Thông tin constraint phụ thuộc schema thực tế, thường là `customers_pkey` nếu tạo không đặt tên PK.

### Bài 32 — Bảng SQLSTATE

| SQLSTATE | Tên exception |
|---|---|
| `23505` | `unique_violation` |
| `23503` | `foreign_key_violation` |
| `P0002` | `no_data_found` |
| `P0003` | `too_many_rows` |
| `40001` | `serialization_failure` |

Không nhận dạng lỗi bằng cách tìm substring trong `MESSAGE_TEXT` nếu đã có SQLSTATE ổn định.

### Bài 33 — Hai loại context

Trong handler:

~~~sql
GET STACKED DIAGNOSTICS
    v_error_context=PG_EXCEPTION_CONTEXT;

GET DIAGNOSTICS
    v_current_context=PG_CONTEXT;
~~~

`v_error_context` cho stack tại **điểm lỗi xảy ra**, `v_current_context` là stack tại **điểm handler đang chạy**. Hai chuỗi có thể khác nhau; không dùng một chuỗi làm bằng chứng cho cả hai.

### Bài 34 — Exception subtransaction

Customer 900 **không còn** sau khi inner block có EXCEPTION bắt lỗi thứ hai, vì các thay đổi database trong phần thân block được rollback. Biến `v_step` có thể vẫn mang `after insert` khi vào handler, vì local PL/pgSQL variables không rollback theo cùng cách.

Đừng lấy biến v_step làm bằng chứng một INSERT đã commit.

### Bài 35 — Bắt OTHERS rồi RETURN NULL

Ba rủi ro:

1. Lỗi permission denied hoặc schema sai bị ngụy trang thành “không tìm thấy dữ liệu”.
2. Lỗi deadlock/serialization không được retry đúng.
3. Lỗi constraint/data corruption bị giấu, khiến debugging khó và API kết luận sai.

Mẫu rethrow:

~~~sql
DO $$
DECLARE
    v_state text;
BEGIN
    PERFORM 1/0;
EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_state=RETURNED_SQLSTATE;
        RAISE NOTICE 'SQLSTATE=%',v_state;
        RAISE;
END $$;
~~~

Đoạn này **cố ý báo lỗi** ở cuối khi được chạy. Trong production, chỉ log những trường cho phép và không catch/rethrow tất cả chỉ để thêm overhead vô ích.

### Bài 36 — COUNT rồi INSERT race

Hai transactions cùng thấy `COUNT(*)=0` trước khi INSERT. Nếu không có constraint, cả hai có thể chèn duplicate theo business key. Nếu có UNIQUE, một trong hai có thể gặp `23505`.

Cần:

~~~sql
ALTER TABLE pl_diag_lab.customers
ADD CONSTRAINT uq_customers_code
UNIQUE (customer_code);
~~~

**Trong lab đã có UNIQUE(customer_code)**, không chạy lệnh thêm trùng constraint như một bước bắt buộc. Với key đã unique, có thể dùng `INSERT ... ON CONFLICT (customer_code) DO NOTHING` hoặc DO UPDATE theo contract. Đừng dùng COUNT trước INSERT như cơ chế enforce uniqueness.

### Bài 37 — SELECT FOR UPDATE

`SELECT ... FOR UPDATE` lấy row-level lock trên các rows được chọn trong transaction (theo lock mode PostgreSQL), giúp điều phối các transaction khác muốn cập nhật/khóa cùng row. FOUND=true chỉ nói có row được chọn, **không tự đặt row lock**; SELECT thường và SELECT FOR UPDATE khác nhau.

Tuy nhiên nếu UPDATE set-based với predicate đã đủ biểu diễn business invariant, không nhất thiết cần SELECT FOR UPDATE riêng.

### Bài 38 — ROW_COUNT=0 có nhiều nghĩa

Sau:

~~~sql
UPDATE pl_diag_lab.orders
SET order_status='paid'
WHERE order_id=p_id AND order_status='new';
~~~

`ROW_COUNT=0` có thể là:

- ID không tồn tại.
- ID tồn tại nhưng trạng thái đã paid hoặc canceled.

Khi phải phân biệt, có thể query sau đó:

~~~sql
SELECT order_status INTO v_current_status
FROM pl_diag_lab.orders
WHERE order_id=p_id;
v_exists := FOUND;
~~~

Nhưng nếu concurrent transactions được phép thay dữ liệu, hai bước phải được đặt trong mô hình transaction/locking phù hợp. Không coi SELECT tiếp theo luôn phản ánh chính xác trạng thái tại thời điểm UPDATE thất bại trong mọi isolation level.

### Bài 39 — Function batch UPDATE

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.cancel_old_new_orders_count(
    p_before timestamptz
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='canceled'
     WHERE order_status='new'
       AND created_at < p_before;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END;
$$;
~~~

Test:

~~~sql
BEGIN;
SELECT pl_diag_lab.cancel_old_new_orders_count(
    '2026-11-05 00:00:00+00'
);
ROLLBACK;
~~~

Dữ liệu gốc dự kiến 2 rows (1001,1003). Nếu lab đã được sửa, count thay đổi theo trạng thái thực. `RETURN v_rows` không tự COMMIT, kết quả còn phụ thuộc transaction của caller.

### Bài 40 — Set-based UPDATE thay loop

Thường dùng một statement:

~~~sql
DO $$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET amount=round(amount * 1.05,2)
     WHERE order_status='new';

    GET DIAGNOSTICS v_rows=ROW_COUNT;

    RAISE NOTICE 'Updated % rows',v_rows;
END $$;
~~~

Thực hiện thay đổi trong một UPDATE thay vì 100.000 UPDATE riêng, giúp PostgreSQL tối ưu việc quét/ghi và giảm overhead lặp command. Đo trên workload, vì nếu mỗi row có side effect riêng thì thiết kế sẽ khác.

### Bài 41 — Alias để không nhầm tên

Sai:

~~~sql
WHERE order_id=order_id
~~~

Dạng đúng:

~~~sql
SELECT o.amount
INTO v_amount
FROM pl_diag_lab.orders AS o
WHERE o.order_id=p_order_id;
~~~

Prefix `p_` cho parameter, `v_` cho variable, `o.` cho column; không dựa vào rules conflict resolution để tự đoán identifier.

### Bài 42 — FOUND trong trigger

FOUND là biến PL/pgSQL **local** cho statement được trigger function chạy, không phải status của DML statement bên ngoài trên toàn bộ bảng. Trong row-level trigger, dùng `NEW`, `OLD`, `TG_OP` để nhận giá trị row cũ/mới và loại thao tác; nếu cần tổng rows của một statement có thể dùng statement-level trigger/transition tables hoặc affected count ở caller theo đúng thiết kế.

### Bài 43 — Test UPDATE có ROLLBACK

~~~sql
BEGIN;

DO $$
DECLARE
    v_count bigint;
BEGIN
    UPDATE pl_diag_lab.orders
       SET order_status='paid'
     WHERE order_status='new';

    GET DIAGNOSTICS v_count=ROW_COUNT;
    RAISE NOTICE 'Đã chuyển % orders new thành paid',v_count;
END $$;

ROLLBACK;
~~~

Sau ROLLBACK, database trả về trạng thái trước transaction. Không tự gọi COMMIT trong function bình thường. Nếu query thực thi side effects ngoài database, rollback PostgreSQL có thể không đảo ngược những side effects đó.

### Bài 44 — Kết hợp SELECT INTO, FOUND, UPDATE và stacked diagnostics

Một function mẫu trả một record có trạng thái và count:

~~~sql
CREATE OR REPLACE FUNCTION pl_diag_lab.pay_new_orders_by_code(
    p_customer_code text
)
RETURNS TABLE (
    result_code text,
    updated_orders bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_id bigint;
    v_rows bigint;
    v_found boolean;
    v_state text;
    v_constraint text;
BEGIN
    SELECT c.customer_id
      INTO v_customer_id
      FROM pl_diag_lab.customers AS c
     WHERE c.customer_code=p_customer_code;

    v_found := FOUND; -- Chụp ngay SELECT.

    IF NOT v_found THEN
        result_code := 'customer_not_found';
        updated_orders := 0;
        RETURN NEXT;
        RETURN;
    END IF;

    UPDATE pl_diag_lab.orders AS o
       SET order_status='paid'
     WHERE o.customer_id=v_customer_id
       AND o.order_status='new';

    GET DIAGNOSTICS v_rows=ROW_COUNT;

    result_code := 'updated';
    updated_orders := v_rows;

    RETURN NEXT;
    RETURN;

EXCEPTION
    WHEN unique_violation OR foreign_key_violation THEN
        GET STACKED DIAGNOSTICS
            v_state=RETURNED_SQLSTATE,
            v_constraint=CONSTRAINT_NAME;

        -- Ghi log nội bộ có thể dùng v_state và v_constraint
        -- theo chính sách, nhưng đừng biến lỗi constraint
        -- thành customer_not_found hay nuốt lỗi.
        RAISE NOTICE 'Constraint failure SQLSTATE=%; constraint=%',
            v_state,v_constraint;
        RAISE;
END;
$$;
~~~

Giải thích:

1. `SELECT ... INTO` lấy ID theo `customer_code` UNIQUE; nếu không có row, FOUND=false.
2. Lưu ngay `v_found := FOUND` trước khi có câu SQL khác.
3. Khi không có customer, function trả trạng thái rõ và `updated_orders=0`.
4. UPDATE set-based chỉ đổi orders new sang paid, tránh vòng lặp từng order.
5. `GET DIAGNOSTICS ROW_COUNT` đặt **ngay sau UPDATE**, trước logging hay SQL khác.
6. Nếu UPDATE không có row, `result_code='updated'` và count=0 ở mẫu này chỉ có nghĩa batch đã thực thi nhưng không có order new; API có thể muốn code khác nếu business phân biệt.
7. Trong handler chỉ đọc **GET STACKED DIAGNOSTICS** cho exception; không dùng FOUND hay ROW_COUNT để phân loại unique/FK.
8. Mẫu `RAISE;` để không che lỗi DB bằng một trạng thái thành công sai.
9. Nếu caller cần một output row duy nhất thay vì set-returning `RETURNS TABLE`, có thể chọn OUT parameters/return composite theo cách phù hợp, nhưng phải giữ semantics nhất quán.
10. Dữ liệu từ schema lab được thay đổi thật nếu gọi function và commit. Thử với transaction có ROLLBACK.

Ví dụ chạy thử an toàn:

~~~sql
BEGIN;

SELECT *
FROM pl_diag_lab.pay_new_orders_by_code('C101');

SELECT *
FROM pl_diag_lab.pay_new_orders_by_code('NO_SUCH_CODE');

ROLLBACK;
~~~

Với bộ dữ liệu gốc, C101 có order 1001 đang new nên count dự kiến 1, còn code không tồn tại trả `customer_not_found` với count 0. Những row dữ liệu trong transaction được rollback ở cuối.

---

## 45. Tổng kết

Bốn kỹ thuật trong bài liên quan trực tiếp nhưng giải quyết những câu hỏi khác nhau:

1. **`:=`**: gán một biểu thức vào biến PL/pgSQL. Biến chưa khởi tạo thường là NULL. Dùng `%TYPE` và `%ROWTYPE` khi muốn kiểu biến đồng bộ với schema.
2. **`SELECT ... INTO`**: lấy kết quả SQL vào target. Không STRICT: 0 rows → target NULL, FOUND=false; 1 row → gán, FOUND=true; nhiều rows → chọn một row đầu tiên không bảo đảm nếu không ORDER BY. `INTO STRICT` yêu cầu đúng một row, báo `NO_DATA_FOUND` hoặc `TOO_MANY_ROWS` khi sai cardinality.
3. **`FOUND`**: cờ boolean local được một số câu lệnh như SELECT INTO, PERFORM, DML, FETCH và loops cập nhật. Nó **không lưu lịch sử**; phải chụp ngay nếu code còn chạy statements khác. `EXECUTE` dynamic **không** cập nhật FOUND.
4. **`GET DIAGNOSTICS ... ROW_COUNT`**: đọc số rows xử lý bởi SQL command gần nhất, cần đặt sát câu lệnh cần đo và dùng biến `bigint`. Nó không thay biến `COUNT(*)` hoặc giá trị `EXISTS`.
5. **`GET DIAGNOSTICS ... PG_CONTEXT`**: đọc call stack **hiện tại**.
6. **`GET STACKED DIAGNOSTICS`**: trong EXCEPTION handler, đọc `RETURNED_SQLSTATE`, `MESSAGE_TEXT`, `CONSTRAINT_NAME`, `PG_EXCEPTION_CONTEXT` và các trường lỗi khác. Không phải công cụ lấy ROW_COUNT.
7. **DML RETURNING INTO**: phù hợp một row nhưng có giới hạn riêng nếu nhiều rows RETURNING; không coi nó là scalar SELECT INTO nhiều hàng không STRICT.
8. **Truy vấn set-based và constraints** thường tốt hơn đọc rồi update từng row hoặc COUNT rồi INSERT để enforce uniqueness. FOUND/ROW_COUNT giúp quan sát kết quả, không thay transaction isolation, locking, PK/FK hoặc idempotency.
9. **Exception** phải được phân loại theo SQLSTATE và yêu cầu nghiệp vụ; không nuốt mọi lỗi rồi trả NULL. Khi lỗi được bắt, thay đổi dữ liệu trong block có EXCEPTION đã bị rollback theo subtransaction, còn local variables có thể vẫn giữ giá trị.
10. **Quan sát đúng trước tối ưu:** chọn SELECT INTO khi cần dữ liệu, PERFORM/EXISTS khi chỉ hỏi tồn tại, COUNT(*) khi cần lượng chính xác, GET DIAGNOSTICS khi đo affected rows và STACKED DIAGNOSTICS khi thực sự đang xử lý exception.

Quy trình triển khai có thể ghi nhớ: **xác định contract 0/1/nhiều rows → chọn phép gán hoặc SELECT INTO [STRICT] → chụp FOUND ngay sau statement → dùng ROW_COUNT cho số rows DML, đặc biệt với EXECUTE động → bắt và phân loại lỗi bằng SQLSTATE/STACKED DIAGNOSTICS → bảo đảm transaction, concurrency và quyền truy cập đúng → kiểm thử cả trường hợp không có hàng, nhiều hàng và lỗi constraint trước khi đưa vào ứng dụng**.
