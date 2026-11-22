# Tạo, sửa, xóa và kiểm thử routine theo phương ngữ

Trong một hệ thống bán hàng, cùng một công thức tính số tiền sau giảm giá có thể được dùng ở API, tác vụ nhập dữ liệu và báo cáo. Một quy trình khác cần **xác nhận hóa đơn**, đổi trạng thái, cập nhật tiền phải trả và ghi nhật ký. Nhiều hệ quản trị SQL cho phép đóng gói logic này thành **routine** có tên: thường là **function** hoặc **stored procedure**.

Nhưng vòng đời của một routine không dừng ở câu lệnh CREATE. Khi thay đổi công thức, nhà phát triển cần biết dùng **CREATE OR REPLACE**, **ALTER** hay **DROP rồi CREATE**; khi xóa phải hiểu **chữ ký tham số** và các đối tượng phụ thuộc; khi kiểm thử phải kiểm tra **kết quả trả về, trạng thái bảng, lỗi, quyền và transaction**.

Bài **“Tạo, sửa, xóa và kiểm thử routine theo phương ngữ”** thuộc chương **Thủ tục và hàm** của module **Database SQL**. Thực hành chính sử dụng **PostgreSQL 15 trở lên**, kèm ví dụ độc lập cho **MySQL 8.0, SQL Server, Oracle Database và SQLite**.

> **Lưu ý thực hành:** Các lệnh CREATE TABLE/SCHEMA/FUNCTION/PROCEDURE dưới đây dùng cho **database học tập**. Chúng thay đổi schema, không nên chạy trên production. Bài có phần dọn đối tượng ở cuối; tránh DROP ... CASCADE nếu chưa xem phụ thuộc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **function**, **procedure**, **trigger** và cách gọi chúng.
2. Tạo và gọi function PostgreSQL bằng **CREATE FUNCTION** và SELECT.
3. Thay thân hàm bằng **CREATE OR REPLACE FUNCTION** khi chữ ký và kiểu trả về tương thích.
4. Hiểu **signature**, **overload**, **tham số mặc định**, và DROP đúng routine.
5. Tạo procedure PostgreSQL, gọi bằng CALL và kiểm tra DML/audit.
6. Kiểm thử happy path, boundary, NULL, đầu vào lỗi, thiếu hàng, gọi lặp và rollback.
7. Dùng ALTER để sửa thuộc tính routine, đồng thời nhận diện giới hạn của ALTER.
8. Xem metadata, dependency và quyền EXECUTE; hiểu SECURITY INVOKER/DEFINER.
9. Đối chiếu cách tạo, sửa, xóa routine trên MySQL, SQL Server và Oracle.
10. Hiểu vì sao SQLite không có CREATE PROCEDURE SQL lõi tương đương và dùng UDF từ host.
11. Thiết kế migration routine không phá vỡ hợp đồng ứng dụng.

## 2. Function và procedure là hai loại routine

**Routine** là đơn vị logic có tên và giao diện gọi. Trong hệ SQL, hai loại phổ biến:

| Loại | Vai trò điển hình | Cách dùng PostgreSQL |
| --- | --- | --- |
| **Scalar function** | Nhận tham số và trả một giá trị dùng trong biểu thức | SELECT schema.function(...) |
| **Set-returning/table function** | Trả tập hàng cho truy vấn | SELECT ... FROM schema.function(...) |
| **Stored procedure** | Thực hiện một quy trình gồm nhiều lệnh, có thể thay đổi bảng | CALL schema.procedure(...) |
| **Trigger function/trigger** | Chạy theo sự kiện DML của bảng | Do database kích hoạt, không thay thế procedure tổng quát |

Một function tính toán thuần túy có thể là:

~~~text
net_amount(subtotal, discount_percent)
    → amount after discount
~~~

Một procedure có side effects:

~~~text
approve_invoice(invoice_id)
    → đọc trạng thái hóa đơn
    → tính tiền nhờ net_amount
    → cập nhật bảng hóa đơn
    → chèn audit
~~~

**Không được suy luận function trên mọi hệ đều thuần túy và procedure nào cũng tự COMMIT.** Khả năng truy cập bảng, trả kết quả và quản lý transaction phụ thuộc RDBMS, ngôn ngữ routine và ngữ cảnh gọi.

### 2.1. Bốn loại công việc trong vòng đời routine

~~~text
    Thiết kế hợp đồng
            |
            v
    CREATE routine
            |
            v
    Gọi và kiểm thử
            |
            v
    REPLACE / ALTER
            |
            v
    Regression test
            |
            v
    Triển khai migration
            |
            v
    Ngừng dùng và DROP
~~~

Phần **CREATE/ALTER/DROP** là DDL quản lý code trong database; **SELECT/CALL/EXEC** là thao tác thực thi routine.

## 3. Bảng đối chiếu cú pháp nhanh

| Hệ quản trị | Tạo hàm | Tạo thủ tục | Sửa thân routine | Xóa routine | Gọi procedure |
| --- | --- | --- | --- | --- | --- |
| **PostgreSQL** | CREATE FUNCTION | CREATE PROCEDURE | CREATE OR REPLACE khi tương thích | DROP FUNCTION / DROP PROCEDURE, chú ý chữ ký | CALL |
| **MySQL 8.0** | CREATE FUNCTION | CREATE PROCEDURE | Thường DROP rồi CREATE; ALTER chỉ sửa thuộc tính hỗ trợ | DROP FUNCTION / DROP PROCEDURE | CALL |
| **SQL Server** | CREATE FUNCTION | CREATE PROCEDURE | ALTER hoặc CREATE OR ALTER ở bản hỗ trợ | DROP FUNCTION / DROP PROCEDURE | EXEC/EXECUTE |
| **Oracle** | CREATE OR REPLACE FUNCTION | CREATE OR REPLACE PROCEDURE | CREATE OR REPLACE, kể cả package body khi áp dụng | DROP FUNCTION / DROP PROCEDURE | Gọi trong PL/SQL hoặc CALL phù hợp |
| **SQLite core** | Không có stored CREATE FUNCTION bằng SQL lõi tương đương | Không có CREATE PROCEDURE native | Đăng ký/sửa UDF qua host API/extension | Không có DROP routine SQL lõi tương đương | Không có CALL procedure native |

Chữ **OR REPLACE**, **ALTER**, **CALL** và cả từ **FUNCTION** không có cùng cú pháp/khả năng ở mọi hệ. Ví dụ **DELIMITER** của MySQL và **GO** của SQL Server là chỉ thị của một số client, không phải SQL server chuẩn.

## 4. Thiết kế ví dụ: hàm tính tiền và thủ tục duyệt hóa đơn

Hàm nhận **số tiền gốc** và **phần trăm giảm**:

\[
\operatorname{net}(s,d)
=\operatorname{round}\left(s\left(1-\frac{d}{100}\right),2\right).
\]

Quy tắc:

- **subtotal** phải không âm.
- **discount_pct** nằm trong đoạn **0–100**.
- Hàm trả giá trị **NUMERIC** làm tròn hai chữ số thập phân.
- Nếu input NULL, chính sách của hàm PostgreSQL trong bài là **trả NULL**.
- Đầu vào ngoài miền hợp lệ làm hàm **báo lỗi**, không tự sửa thành 0.

Procedure **approve_invoice(invoice_id)**:

1. Tìm hóa đơn bằng khóa chính.
2. Chỉ chấp nhận hóa đơn **NEW**.
3. Tính net từ function.
4. UPDATE hóa đơn thành **APPROVED**.
5. Kiểm tra đúng một hàng được UPDATE.
6. Ghi một dòng audit trong cùng transaction.

Trong phần sau, ta còn thay đổi procedure để lời gọi lặp trên hóa đơn đã APPROVED **không ghi audit trùng**.

## 5. PostgreSQL: chuẩn bị schema độc lập

Để các routine còn tồn tại qua nhiều lần gọi và có thể minh họa dependency, phần này sử dụng **schema/bảng thường** trên database học tập, không phải TEMP TABLE.

~~~sql
CREATE SCHEMA lab347;

CREATE TABLE lab347.invoices (
    invoice_id      INTEGER PRIMARY KEY,
    customer_code   TEXT NOT NULL,
    subtotal_vnd    NUMERIC(14,2) NOT NULL
        CHECK (subtotal_vnd >= 0),
    discount_pct    NUMERIC(5,2) NOT NULL
        CHECK (discount_pct BETWEEN 0 AND 100),
    net_amount_vnd  NUMERIC(14,2),
    status          TEXT NOT NULL
        CHECK (status IN ('NEW', 'APPROVED', 'CANCELLED'))
);

CREATE TABLE lab347.invoice_audit (
    audit_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id   INTEGER NOT NULL
        REFERENCES lab347.invoices(invoice_id),
    action_name  TEXT NOT NULL,
    amount_vnd   NUMERIC(14,2),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lab347.invoices
    (invoice_id, customer_code, subtotal_vnd,
     discount_pct, net_amount_vnd, status)
VALUES
    (1001, 'C-001', 120000, 10, NULL, 'NEW'),
    (1002, 'C-002',  50000,  0, NULL, 'NEW'),
    (1003, 'C-003',  80000,  5, NULL, 'CANCELLED'),
    (1004, 'C-004', 200000, 15, 170000, 'APPROVED');
~~~

Kiểm tra:

~~~sql
SELECT
    invoice_id,
    subtotal_vnd,
    discount_pct,
    net_amount_vnd,
    status
FROM lab347.invoices
ORDER BY invoice_id;
~~~

| invoice_id | subtotal_vnd | discount_pct | net_amount_vnd | status |
| ---: | ---: | ---: | ---: | --- |
| 1001 | 120000 | 10 | NULL | NEW |
| 1002 | 50000 | 0 | NULL | NEW |
| 1003 | 80000 | 5 | NULL | CANCELLED |
| 1004 | 200000 | 15 | 170000 | APPROVED |

**Không chạy CREATE SCHEMA lab347 nếu schema ấy đã thuộc dữ liệu khác.** Hãy dùng database thử sạch hoặc đổi tên schema trong toàn bộ bài. Các bảng này chỉ nên bị xóa khi chắc chắn chúng là đối tượng thực hành.

## 6. PostgreSQL: CREATE FUNCTION đầu tiên

Tạo scalar function bằng **LANGUAGE SQL**:

~~~sql
CREATE FUNCTION lab347.net_amount(
    p_subtotal NUMERIC,
    p_discount_pct NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
RETURNS NULL ON NULL INPUT
AS $$
    SELECT ROUND(
        p_subtotal * (1 - p_discount_pct / 100),
        2
    );
$$;
~~~

Ý nghĩa từng phần:

- **lab347.net_amount**: tên có schema, tránh phụ thuộc vào search_path để tìm đối tượng.
- **p_subtotal**, **p_discount_pct**: tham số đầu vào.
- **RETURNS NUMERIC**: contract của kiểu trả về.
- **LANGUAGE SQL**: thân hàm dùng câu SQL.
- **IMMUTABLE**: khai báo cùng input cho cùng output; phù hợp công thức thuần túy này, không phù hợp một routine đọc dữ liệu thay đổi hoặc lấy thời gian hiện tại.
- **RETURNS NULL ON NULL INPUT**: còn gọi là **STRICT**, trả NULL khi có input NULL thay vì gọi body.
- **$$ ... $$**: dollar-quoting thân routine, khác lệnh bắt đầu transaction.

Gọi function bằng SELECT:

~~~sql
SELECT
    lab347.net_amount(120000, 10) AS a,
    lab347.net_amount(50000, 0) AS b,
    lab347.net_amount(50000, 100) AS c;
~~~

Kết quả là **108000**, **50000**, **0**.

Function cũng dùng được trên cột:

~~~sql
SELECT
    invoice_id,
    subtotal_vnd,
    discount_pct,
    lab347.net_amount(subtotal_vnd, discount_pct)
        AS expected_net_vnd
FROM lab347.invoices
ORDER BY invoice_id;
~~~

Đây là lợi ích của function: nhiều truy vấn tái sử dụng một công thức có tên.

### 6.1. Hàm phiên bản đầu chưa có validation

~~~sql
SELECT lab347.net_amount(100000, 120);
~~~

Phép tính thuần túy có thể trả một số âm vì không kiểm tra discount 120. Nghiệp vụ lại yêu cầu 0 đến 100. Ta sẽ **thay thân hàm** mà không thay chữ ký.

## 7. PostgreSQL: CREATE OR REPLACE FUNCTION

~~~sql
CREATE OR REPLACE FUNCTION lab347.net_amount(
    p_subtotal NUMERIC,
    p_discount_pct NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
BEGIN
    IF p_subtotal < 0 THEN
        RAISE EXCEPTION
            'Subtotal must be nonnegative: %', p_subtotal
            USING ERRCODE = '22023';
    END IF;

    IF p_discount_pct < 0 OR p_discount_pct > 100 THEN
        RAISE EXCEPTION
            'Discount must be from 0 to 100: %',
            p_discount_pct
            USING ERRCODE = '22023';
    END IF;

    RETURN ROUND(
        p_subtotal * (1 - p_discount_pct / 100),
        2
    );
END;
$$;
~~~

Định nghĩa mới:

- Vẫn nhận **(NUMERIC, NUMERIC)** và trả **NUMERIC**.
- Thân hàm đổi sang **PL/pgSQL** để dùng IF, RAISE EXCEPTION và RETURN.
- **STRICT** vẫn giữ chính sách đầu vào NULL.
- **22023** là SQLSTATE cho **invalid_parameter_value**, dùng để minh họa lỗi input ngoài miền hợp lệ.
- Kết quả của (120000,10) vẫn là 108000.

### 7.1. Vì sao REPLACE thường tốt hơn DROP/CREATE?

Với thay đổi tương thích, CREATE OR REPLACE giúp giữ object hiện có và nhiều thuộc tính như owner/quyền đã được cấp. Nếu DROP rồi CREATE:

- Có thể làm mất quyền EXECUTE cần cấp lại.
- Có thể làm hỏng những object phụ thuộc.
- Có thể tạo một khoảng thời gian routine vắng mặt nếu deployment không nguyên tử.
- Có thể thay đổi định danh object mà database đang tham chiếu.

**Tuy nhiên, CREATE OR REPLACE không đảm bảo thay đổi ngữ nghĩa không phá vỡ người gọi.** Bây giờ discount 120 gây lỗi thay vì trả số âm: đó đã là thay đổi hợp đồng hành vi cần regression test.

### 7.2. Không tùy ý đổi RETURNS

Trên PostgreSQL, **CREATE OR REPLACE FUNCTION không cho đổi kiểu trả về của function đã tồn tại** theo cách sửa RETURNS NUMERIC thành RETURNS TEXT. Đó là thay đổi giao diện.

Nếu muốn trả JSON, TEXT hoặc một record khác, thường nên:

1. Tạo routine tên khác hoặc **phiên bản v2**.
2. Di chuyển consumer.
3. Kiểm tra phụ thuộc và quyền.
4. Xóa routine cũ sau khi nó không còn được dùng.

**Đổi tên/kiểu/thứ tự tham số hoặc loại function/procedure cũng phải được đánh giá như thay đổi API**, không phải chỉ là chỉnh vài ký tự body.

## 8. Signature và function overloading trên PostgreSQL

**Signature** giúp hệ quản trị phân biệt routine. PostgreSQL hỗ trợ **overloading**: nhiều function có cùng tên nhưng khác **số hoặc kiểu tham số đầu vào**.

Hiện có:

~~~text
lab347.net_amount(NUMERIC, NUMERIC)
~~~

Tạo một overload chỉ nhận subtotal và giả định không giảm giá:

~~~sql
CREATE FUNCTION lab347.net_amount(
    p_subtotal NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT lab347.net_amount(p_subtotal, 0::NUMERIC);
$$;
~~~

Thử:

~~~sql
SELECT
    lab347.net_amount(50000::NUMERIC) AS no_discount,
    lab347.net_amount(50000::NUMERIC, 10::NUMERIC) AS discounted;
~~~

Kết quả **50000** và **45000**. Hai function cùng tên nhưng **không phải cùng một object**.

### 8.1. DROP phải nêu đúng signature

~~~sql
-- Minh họa cú pháp, chưa chạy ở giữa bài:
DROP FUNCTION lab347.net_amount(NUMERIC);
DROP FUNCTION lab347.net_amount(NUMERIC, NUMERIC);
~~~

Lệnh thứ nhất xóa **overload một tham số**, lệnh thứ hai xóa **overload hai tham số**. Danh sách kiểu là quan trọng; chỉ tên chung có thể không đủ để chỉ rõ overload cần thao tác.

### 8.2. Tên tham số và named arguments

Người dùng PostgreSQL có thể gọi:

~~~sql
SELECT lab347.net_amount(
    p_subtotal => 120000,
    p_discount_pct => 10
);
~~~

Tên tham số không tự tạo một overload khác nếu kiểu và số tham số đầu vào giống nhau. Nhưng **đổi tên tham số công khai** có thể làm hỏng caller dùng **named arguments**; PostgreSQL còn có hạn chế đối với đổi tên input parameter bằng CREATE OR REPLACE.

### 8.3. DEFAULT và overload

Default arguments có thể khiến nhiều overload cùng phù hợp một lời gọi. Đừng thiết kế hàng loạt hàm cùng tên với tổ hợp kiểu/default mơ hồ. Khi cần, dùng **tên schema đầy đủ**, các kiểu ép rõ và test cả lời gọi positional/named mà ứng dụng dùng.

## 9. PostgreSQL: CREATE PROCEDURE duyệt hóa đơn

Tạo procedure sử dụng function **lab347.net_amount**:

~~~sql
CREATE PROCEDURE lab347.approve_invoice(
    IN p_invoice_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_subtotal NUMERIC(14,2);
    v_discount NUMERIC(5,2);
    v_status TEXT;
    v_net NUMERIC(14,2);
    v_rows BIGINT;
BEGIN
    SELECT
        i.subtotal_vnd,
        i.discount_pct,
        i.status
    INTO STRICT
        v_subtotal,
        v_discount,
        v_status
    FROM lab347.invoices AS i
    WHERE i.invoice_id = p_invoice_id
    FOR UPDATE;

    IF v_status <> 'NEW' THEN
        RAISE EXCEPTION
            'Invoice % has status %, expected NEW',
            p_invoice_id, v_status;
    END IF;

    v_net := lab347.net_amount(v_subtotal, v_discount);

    UPDATE lab347.invoices AS i
    SET
        net_amount_vnd = v_net,
        status = 'APPROVED'
    WHERE i.invoice_id = p_invoice_id
      AND i.status = 'NEW';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows <> 1 THEN
        RAISE EXCEPTION
            'Expected one invoice update; got %', v_rows;
    END IF;

    INSERT INTO lab347.invoice_audit
        (invoice_id, action_name, amount_vnd)
    VALUES
        (p_invoice_id, 'APPROVE', v_net);
END;
$$;
~~~

Các phần cần hiểu:

1. **IN p_invoice_id INTEGER** là tham số input.
2. **SELECT INTO STRICT** yêu cầu đúng một hóa đơn; nếu không có hàng có thể báo NO_DATA_FOUND.
3. **FOR UPDATE** khóa hàng được tìm thấy theo cơ chế transaction PostgreSQL.
4. **IF** bảo vệ trạng thái nghiệp vụ.
5. **Gọi function** để dùng công thức chuẩn.
6. **UPDATE** và **GET DIAGNOSTICS ROW_COUNT** kiểm tra đúng một hàng.
7. **INSERT audit** ghi dấu vết thay đổi trong cùng transaction.

### 9.1. Gọi bằng CALL

~~~sql
CALL lab347.approve_invoice(1001);
~~~

Function thường gọi qua SELECT; procedure PostgreSQL được gọi bằng **CALL**. Không dùng SELECT như một cách gọi procedure nếu không có function tương ứng.

### 9.2. BEGIN...END không phải BEGIN TRANSACTION

Trong PL/pgSQL, BEGIN...END định nghĩa **khối thủ tục**, không tự mở một transaction tách biệt. Procedure này **không tự COMMIT**, để người gọi quyết định COMMIT/ROLLBACK. PostgreSQL có các quy tắc hạn chế transaction control bên trong procedure/DO theo ngữ cảnh CALL/DO; không giả định procedure nào cũng có thể COMMIT bên trong một transaction tường minh.

### 9.3. Vì sao phải kiểm tra ROW_COUNT?

Một UPDATE cú pháp hợp lệ vẫn có thể tác động **0 hàng** nếu không khớp điều kiện. Trong nghiệp vụ “duyệt đúng một hóa đơn”, 0 hoặc nhiều hơn một hàng là dấu hiệu cần xử lý. Việc nhìn thấy câu UPDATE không báo lỗi **không đủ để khẳng định một hóa đơn đã được duyệt**.

## 10. Viết ma trận kiểm thử function

Test phải có **input**, **expected output** và **quy tắc xác minh**.

| Ca | subtotal | discount_pct | Kỳ vọng | Kiểu |
| --- | ---: | ---: | --- | --- |
| F01 | 120000 | 10 | 108000 | Bình thường |
| F02 | 50000 | 0 | 50000 | Không giảm |
| F03 | 50000 | 100 | 0 | Giảm tối đa |
| F04 | 0 | 10 | 0 | Biên thấp |
| F05 | 1000.01 | 0 | 1000.01 | Thập phân |
| F06 | NULL | 10 | NULL | NULL |
| F07 | 120000 | NULL | NULL | NULL |
| F08 | -1 | 5 | Lỗi 22023 | Subtotal âm |
| F09 | 100000 | -1 | Lỗi 22023 | Giảm âm |
| F10 | 100000 | 101 | Lỗi 22023 | Giảm quá 100 |

### 10.1. Truy vấn kết quả

~~~sql
SELECT
    lab347.net_amount(120000, 10) AS f01,
    lab347.net_amount(50000, 0) AS f02,
    lab347.net_amount(50000, 100) AS f03,
    lab347.net_amount(0, 10) AS f04,
    lab347.net_amount(1000.01, 0) AS f05;
~~~

Kết quả theo thứ tự: **108000, 50000, 0, 0, 1000.01**.

### 10.2. Assertion trong DO block

~~~sql
DO $$
BEGIN
    IF lab347.net_amount(120000, 10)
       IS DISTINCT FROM 108000::NUMERIC THEN
        RAISE EXCEPTION 'F01 failed';
    END IF;

    IF lab347.net_amount(50000, 100)
       IS DISTINCT FROM 0::NUMERIC THEN
        RAISE EXCEPTION 'F03 failed';
    END IF;

    IF lab347.net_amount(NULL::NUMERIC, 10::NUMERIC)
       IS NOT NULL THEN
        RAISE EXCEPTION 'F06 failed';
    END IF;

    RAISE NOTICE 'Function cases passed';
END;
$$;
~~~

**IS DISTINCT FROM** giúp kiểm tra giá trị kể cả trường hợp có NULL mà không bị kết quả UNKNOWN của so sánh bằng thông thường.

### 10.3. Kiểm thử hàm phải từ chối đầu vào lỗi

~~~sql
DO $$
BEGIN
    BEGIN
        PERFORM lab347.net_amount(100000, 101);

        -- Nếu lời gọi không gây lỗi, bài test phải thất bại.
        RAISE EXCEPTION 'F10 failed: expected invalid input error';
    EXCEPTION
        WHEN SQLSTATE '22023' THEN
            RAISE NOTICE 'F10 passed: invalid discount rejected';
    END;
END;
$$;
~~~

**Không dùng WHEN OTHERS rồi cho mọi exception là PASS**. Một lỗi mất quyền, hàm không tồn tại hoặc bug khác không phải bằng chứng validation hoạt động đúng.

**Các khối test trên chỉ là ví dụ học về kiểm thử routine trong SQL**, không phải bước QA nội dung Markdown của dự án bài học.

## 11. Kiểm thử procedure có side effects

Test procedure phải xem **cả bảng chính và bảng audit**, rồi dọn kết quả.

### 11.1. Happy path trong transaction

~~~sql
BEGIN;

CALL lab347.approve_invoice(1001);

SELECT invoice_id, status, net_amount_vnd
FROM lab347.invoices
WHERE invoice_id = 1001;

SELECT invoice_id, action_name, amount_vnd
FROM lab347.invoice_audit
WHERE invoice_id = 1001;

ROLLBACK;
~~~

Trong transaction, hóa đơn 1001 thành **APPROVED**, net = **108000**, và có **một audit APPROVE/108000**. Sau ROLLBACK, các thay đổi chưa commit của ca thử bị hủy; invoice 1001 lại là NEW.

### 11.2. Assertion kiểm tra trạng thái và số hàng

~~~sql
BEGIN;

CALL lab347.approve_invoice(1001);

DO $$
DECLARE
    v_status TEXT;
    v_net NUMERIC;
    v_audit_count BIGINT;
BEGIN
    SELECT status, net_amount_vnd
    INTO STRICT v_status, v_net
    FROM lab347.invoices
    WHERE invoice_id = 1001;

    SELECT COUNT(*)
    INTO v_audit_count
    FROM lab347.invoice_audit
    WHERE invoice_id = 1001
      AND action_name = 'APPROVE'
      AND amount_vnd = 108000;

    IF v_status IS DISTINCT FROM 'APPROVED'
       OR v_net IS DISTINCT FROM 108000::NUMERIC
       OR v_audit_count <> 1 THEN
        RAISE EXCEPTION 'Procedure assertion failed';
    END IF;

    RAISE NOTICE 'Procedure happy path passed';
END;
$$;

ROLLBACK;
~~~

### 11.3. Đừng test IDENTITY bằng cách đòi liên tiếp

PostgreSQL sequence/identity có thể tăng **không rollback cùng dữ liệu bảng**. Sau một lần INSERT rồi ROLLBACK, audit_id tiếp theo có thể không còn là 1. Không viết test yêu cầu **audit_id = 1, 2, 3 liên tiếp**; test nên dựa trên invoice_id, action_name và giá trị nghiệp vụ.

## 12. Kiểm thử các đường lỗi của procedure

| Ca | Input | Kỳ vọng |
| --- | --- | --- |
| P01 | 1001, NEW | Duyệt, net 108000, một audit |
| P02 | 1002, NEW | Duyệt, net 50000, một audit |
| P03 | 1003, CANCELLED | Báo lỗi, không thêm audit |
| P04 | 1004, APPROVED | Phiên bản đầu báo lỗi |
| P05 | 9999, không tồn tại | NO_DATA_FOUND từ SELECT INTO STRICT |
| P06 | CALL hai lần cùng hóa đơn | Phiên bản đầu từ chối lần hai |

### 12.1. Test lỗi bằng savepoint PostgreSQL

~~~sql
BEGIN;
SAVEPOINT before_expected_error;

-- Cố ý lỗi: hóa đơn đã CANCELLED.
CALL lab347.approve_invoice(1003);

-- Phải khôi phục transaction sau lỗi.
ROLLBACK TO SAVEPOINT before_expected_error;

SELECT status, net_amount_vnd
FROM lab347.invoices
WHERE invoice_id = 1003;

SELECT COUNT(*) AS audit_count
FROM lab347.invoice_audit
WHERE invoice_id = 1003;

ROLLBACK;
~~~

Hóa đơn 1003 vẫn **CANCELLED**, net NULL, audit_count = 0. Vì PostgreSQL thường đánh dấu transaction tường minh là **aborted** sau lỗi, không SELECT tiếp được trước khi **ROLLBACK TO SAVEPOINT** hoặc rollback toàn bộ.

Một số công cụ SQL dừng script ngay khi gặp lỗi. Khi đó, gửi lệnh ROLLBACK TO SAVEPOINT **thủ công trong cùng connection** rồi mới SELECT.

### 12.2. Test thiếu invoice

~~~sql
BEGIN;
SAVEPOINT before_missing_invoice;

-- Cố ý phát sinh NO_DATA_FOUND.
CALL lab347.approve_invoice(9999);

ROLLBACK TO SAVEPOINT before_missing_invoice;

SELECT COUNT(*) AS count_after_error
FROM lab347.invoices
WHERE invoice_id = 9999;

ROLLBACK;
~~~

Kết quả count = 0. Procedure không tự tạo một hóa đơn khi khóa không tồn tại.

### 12.3. Đừng chạy test side effect trên production

Một procedure có thể gửi sự kiện, gọi HTTP, ghi log bên ngoài database hoặc thay đổi tài nguyên phi transactional. **ROLLBACK dữ liệu SQL không tự thu hồi email đã gửi hoặc API đã gọi.** Với routine có side effect bên ngoài, cần sandbox/mock, idempotency key và môi trường thử cô lập.

## 13. Sửa procedure bằng CREATE OR REPLACE

Yêu cầu nghiệp vụ mới: gọi lại duyệt một hóa đơn đã **APPROVED** phải **không làm gì thêm** và không tạo audit trùng; còn hóa đơn CANCELLED vẫn bị từ chối.

~~~sql
CREATE OR REPLACE PROCEDURE lab347.approve_invoice(
    IN p_invoice_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_subtotal NUMERIC(14,2);
    v_discount NUMERIC(5,2);
    v_status TEXT;
    v_net NUMERIC(14,2);
    v_rows BIGINT;
BEGIN
    SELECT i.subtotal_vnd, i.discount_pct, i.status
    INTO STRICT v_subtotal, v_discount, v_status
    FROM lab347.invoices AS i
    WHERE i.invoice_id = p_invoice_id
    FOR UPDATE;

    IF v_status = 'APPROVED' THEN
        RAISE NOTICE
            'Invoice % already approved; no new audit',
            p_invoice_id;
        RETURN;
    END IF;

    IF v_status <> 'NEW' THEN
        RAISE EXCEPTION
            'Invoice % cannot be approved from status %',
            p_invoice_id, v_status;
    END IF;

    v_net := lab347.net_amount(v_subtotal, v_discount);

    UPDATE lab347.invoices AS i
    SET net_amount_vnd = v_net, status = 'APPROVED'
    WHERE i.invoice_id = p_invoice_id
      AND i.status = 'NEW';

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'Expected one updated invoice';
    END IF;

    INSERT INTO lab347.invoice_audit
        (invoice_id, action_name, amount_vnd)
    VALUES (p_invoice_id, 'APPROVE', v_net);
END;
$$;
~~~

Phiên bản mới phân biệt rõ:

- **NEW:** cập nhật một lần, ghi audit.
- **APPROVED:** coi là thao tác lặp, không thêm audit.
- **CANCELLED:** báo lỗi.

### 13.1. Test idempotency

~~~sql
BEGIN;

CALL lab347.approve_invoice(1001);
CALL lab347.approve_invoice(1001);

SELECT invoice_id, status, net_amount_vnd
FROM lab347.invoices
WHERE invoice_id = 1001;

SELECT COUNT(*) AS approve_events
FROM lab347.invoice_audit
WHERE invoice_id = 1001
  AND action_name = 'APPROVE';

ROLLBACK;
~~~

**approve_events = 1**, không phải 2. Đây là một kiểm thử về **hành vi khi gọi lặp**, không chỉ giá trị RETURN.

Lưu ý: việc bỏ qua invoice đã APPROVED chỉ đúng nếu đó là hợp đồng nghiệp vụ mong muốn. Nếu net_amount cũ sai hoặc request đến với thông số khác, một chính sách đối soát khác có thể cần thiết.

## 14. ALTER FUNCTION/PROCEDURE và CREATE OR REPLACE khác nhau

Trên PostgreSQL, **CREATE OR REPLACE** thường dùng sửa body; **ALTER FUNCTION** và **ALTER PROCEDURE** có những tác vụ sửa **thuộc tính/metadata** như rename, owner, schema, volatility hoặc cost theo khả năng hỗ trợ của từng loại.

Ví dụ sửa thuộc tính chi phí ước lượng:

~~~sql
ALTER FUNCTION lab347.net_amount(NUMERIC, NUMERIC)
COST 50;
~~~

Lệnh trên **không sửa công thức**. Thuộc tính COST giúp planner ước lượng chi phí gọi routine; giá trị phù hợp phải dựa trên hành vi thực tế chứ không phải một nút bấm tăng tốc tự động.

Ví dụ tên lệnh khác (chỉ minh họa, không cần thực thi trong bài):

~~~sql
-- ALTER FUNCTION lab347.net_amount(NUMERIC, NUMERIC)
-- RENAME TO net_amount_revised;

-- ALTER PROCEDURE lab347.approve_invoice(INTEGER)
-- RENAME TO approve_invoice_revised;
~~~

Đổi tên có thể làm hỏng câu SELECT/CALL hiện có. Nếu cần migration tên, hãy xem toàn bộ consumer và phụ thuộc trước.

### 14.1. ALTER theo signature

Do lab347.net_amount có hai overload, việc viết:

~~~sql
ALTER FUNCTION lab347.net_amount(NUMERIC, NUMERIC)
COST 50;
~~~

chỉ định **bản hai tham số**. Một function cùng tên nhưng chỉ nhận NUMERIC là object khác.

## 15. Metadata: kiểm tra routine đã tạo

PostgreSQL lưu metadata function/procedure trong catalog **pg_proc**. Có thể tra:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind AS routine_kind,
    pg_get_function_identity_arguments(p.oid) AS identity_args
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'lab347'
ORDER BY p.proname, identity_args;
~~~

Với PostgreSQL hiện đại, **prokind = 'f'** thường là ordinary function, **'p'** là procedure; các loại khác có thể dùng giá trị khác. Kết quả giúp phân biệt hai overload của net_amount.

Đọc định nghĩa function:

~~~sql
SELECT pg_get_functiondef(
    'lab347.net_amount(NUMERIC, NUMERIC)'::REGPROCEDURE
) AS current_definition;
~~~

Ngoài catalog PostgreSQL, có thể dùng information_schema:

~~~sql
SELECT
    routine_schema,
    routine_name,
    routine_type,
    data_type
FROM information_schema.routines
WHERE routine_schema = 'lab347'
ORDER BY routine_name;
~~~

**Metadata xác nhận routine tồn tại và có đặc tính nào; nó không chứng minh routine tính đúng mọi input.** Kiểm thử logic vẫn cần thiết.

## 16. DROP FUNCTION và DROP PROCEDURE

Mẫu PostgreSQL:

~~~sql
-- Chỉ là mẫu, KHÔNG thực thi trước khi kết thúc phần thực hành.
DROP PROCEDURE IF EXISTS lab347.approve_invoice(INTEGER);
DROP FUNCTION IF EXISTS lab347.net_amount(NUMERIC);
DROP FUNCTION IF EXISTS lab347.net_amount(NUMERIC, NUMERIC);
~~~

### 16.1. Vì sao cần chữ ký?

**lab347.net_amount(NUMERIC)** và **lab347.net_amount(NUMERIC, NUMERIC)** là hai overload. Chỉ định đủ kiểu đầu vào giúp xác định đúng routine muốn xóa.

### 16.2. IF EXISTS không bỏ qua mọi lỗi

**IF EXISTS** tránh lỗi đối tượng không tồn tại, nhưng **không bỏ qua lỗi thiếu quyền** hoặc dependency đang ngăn việc xóa.

### 16.3. RESTRICT và CASCADE

Trong PostgreSQL, **DROP ... RESTRICT** không xóa nếu dependency còn cản trở; **CASCADE** có thể kéo theo những object phụ thuộc. Không tự thêm CASCADE chỉ để tránh phải đọc thông báo lỗi.

Một chiến lược an toàn:

1. Xác định ai/đối tượng nào còn gọi routine.
2. Thay thế và chuyển caller.
3. Xem dependency trong database.
4. Thu hồi quyền nếu cần ngừng sử dụng trước khi xóa.
5. DROP đúng routine và chữ ký.

**DROP routine không hoàn tác những dữ liệu đã COMMIT** khi routine từng chạy. Đây là DDL xóa định nghĩa code, không phải rollback lịch sử nghiệp vụ.

## 17. Quyền EXECUTE và bảo mật

Routine có owner, quyền gọi và ngữ cảnh thực thi. Với role giả định **app_invoice_operator** đã được tạo:

~~~sql
GRANT USAGE ON SCHEMA lab347 TO app_invoice_operator;

GRANT EXECUTE ON FUNCTION
    lab347.net_amount(NUMERIC, NUMERIC)
TO app_invoice_operator;

GRANT EXECUTE ON PROCEDURE
    lab347.approve_invoice(INTEGER)
TO app_invoice_operator;
~~~

**Các câu GRANT là ví dụ trên role giả định**, không cần chạy khi chưa có role đó. Chỉ cấp quyền cần thiết theo **least privilege**.

### 17.1. SECURITY INVOKER và SECURITY DEFINER

PostgreSQL có cơ chế:

- **SECURITY INVOKER:** thực thi theo quyền của người gọi ở các trường hợp được định nghĩa.
- **SECURITY DEFINER:** thực thi với quyền của owner của routine theo cơ chế của PostgreSQL.

SECURITY DEFINER có thể hữu ích khi ứng dụng được phép gọi một thủ tục nhưng không được trực tiếp UPDATE mọi bảng nguồn. Tuy nhiên, nó có thể tạo rủi ro nếu:

- Routine dùng SQL động ghép chuỗi đầu vào không đáng tin.
- **search_path** trỏ vào schema mà người khác có quyền tạo đối tượng.
- Owner có đặc quyền quá rộng.
- Quyền EXECUTE được cấp cho PUBLIC hoặc role ngoài ý muốn.

Khi dùng SECURITY DEFINER, hãy **schema-qualify bảng/hàm**, thiết lập search_path đáng tin, quản lý quyền owner, không ghép dữ liệu thô vào SQL động và kiểm thử bằng đúng role ứng dụng.

### 17.2. Quyền mặc định

Trong PostgreSQL, các function mới có **default privileges** theo cấu hình; ở một thiết lập phổ biến, quyền EXECUTE có thể được cấp cho PUBLIC mặc định. Với routine nhạy cảm, nên quản lý **REVOKE/GRANT trong cùng quy trình migration** để tránh phơi quyền không dự tính.

Không dùng SECURITY DEFINER chỉ để “hết lỗi permission denied” mà chưa đánh giá rủi ro.

## 18. Thay đổi routine trong sản phẩm đang chạy

Một API routine có nhiều tầng contract:

| Lớp | Cần giữ hoặc quản lý thay đổi | Ví dụ |
| --- | --- | --- |
| **Tên và schema** | Caller phải tìm đúng object | lab347.net_amount |
| **Signature** | Số/kiểu tham số; tên khi gọi named | NUMERIC, NUMERIC |
| **Kiểu trả về** | Consumer có thể cộng/sort/cast kết quả | RETURNS NUMERIC |
| **Ngữ nghĩa** | NULL, rounding, validation, exception | discount 101 lỗi 22023 |
| **Side effects** | Bảng ghi, audit, output, trạng thái | APPROVED + audit |
| **Quyền** | Role nào gọi được | EXECUTE |
| **Transaction** | Hành vi khi lỗi, rollback, retry | Một thao tác all-or-nothing |

### 18.1. Thay đổi tương thích

Nếu body được tối ưu nhưng chữ ký và kết quả không đổi, **CREATE OR REPLACE** trên PostgreSQL thường phù hợp. Tuy nhiên, vẫn cần regression test: một chỉnh sửa rounding hoặc NULL dù giữ kiểu trả về cũng có thể làm báo cáo lệch.

### 18.2. Thay đổi phá vỡ hợp đồng

Nếu net_amount cần trả cấu trúc JSON thay vì NUMERIC, cách an toàn hơn có thể là:

~~~text
net_amount(NUMERIC, NUMERIC) → giữ cho client cũ
net_amount_detail_v2(...)    → API mới có cấu trúc khác
~~~

Triển khai v2, test, chuyển từng consumer, quan sát sử dụng v1, rồi mới DROP v1. Không sửa phá vỡ trên tên cũ nếu chưa có kế hoạch chuyển caller.

### 18.3. DDL là code được version hóa

Định nghĩa routine nên nằm trong file migration/repository, kèm:

- Contract input/output.
- Những trường hợp báo lỗi.
- Test dựa trên dữ liệu đại diện.
- Thay đổi quyền, owner và dependency.
- Kế hoạch triển khai/rollback.

Không chỉnh routine trực tiếp trên production rồi để các môi trường có phiên bản khác nhau mà không ghi nhận lịch sử.

## 19. PostgreSQL: dọn schema của bài

**Sau khi đã thực hành xong** và xác nhận schema lab347 chỉ chứa những đối tượng của bài:

~~~sql
DROP PROCEDURE IF EXISTS lab347.approve_invoice(INTEGER);

DROP FUNCTION IF EXISTS lab347.net_amount(NUMERIC);
DROP FUNCTION IF EXISTS lab347.net_amount(NUMERIC, NUMERIC);

DROP TABLE IF EXISTS lab347.invoice_audit;
DROP TABLE IF EXISTS lab347.invoices;

DROP SCHEMA IF EXISTS lab347;
~~~

Thứ tự:

1. Xóa procedure dùng function và bảng.
2. Xóa overload một tham số, rồi function hai tham số.
3. Xóa bảng audit có FK tới invoices.
4. Xóa bảng invoices.
5. Xóa schema khi đã rỗng.

**Không thêm CASCADE một cách máy móc.** Nếu phát sinh dependency không dự tính, hãy điều tra thay vì xóa lây những object khác.

Nếu muốn tiếp tục thử các phần PostgreSQL, **chưa chạy cleanup** cho tới khi các ca test đã hoàn thành.

## 20. MySQL 8.0: CREATE FUNCTION

Các ví dụ MySQL dưới đây **độc lập**, không chạy trong PostgreSQL. Với mysql CLI, có thể dùng **DELIMITER** để nhập thân routine nhiều câu.

~~~sql
DELIMITER //

CREATE FUNCTION lab347_mysql_net_amount(
    p_subtotal DECIMAL(14,2),
    p_discount_pct DECIMAL(5,2)
)
RETURNS DECIMAL(14,2)
DETERMINISTIC
NO SQL
BEGIN
    IF p_subtotal < 0
       OR p_discount_pct < 0
       OR p_discount_pct > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid amount or discount';
    END IF;

    RETURN ROUND(
        p_subtotal * (1 - p_discount_pct / 100),
        2
    );
END//

DELIMITER ;
~~~

Gọi:

~~~sql
SELECT lab347_mysql_net_amount(120000, 10) AS net_vnd;
~~~

Kết quả **108000.00**. Những điểm chú ý:

- **DETERMINISTIC** khai báo tính xác định theo input.
- **NO SQL** là đặc tính mô tả routine không đọc/ghi bảng bằng SQL.
- **SIGNAL SQLSTATE '45000'** phát lỗi ứng dụng.
- **RETURN** trả một scalar.
- Cú pháp **STRICT** của PostgreSQL không được copy nguyên văn vào MySQL.

**DELIMITER // và DELIMITER ; là lệnh của một số client, không phải SQL gửi nguyên văn tới server qua JDBC**. Client cần thay separator để gửi trọn CREATE FUNCTION có nhiều dấu chấm phẩy bên trong.

## 21. MySQL: CREATE PROCEDURE và OUT

~~~sql
DELIMITER //

CREATE PROCEDURE lab347_mysql_calc_net(
    IN p_subtotal DECIMAL(14,2),
    IN p_discount_pct DECIMAL(5,2),
    OUT p_result DECIMAL(14,2)
)
BEGIN
    SET p_result = lab347_mysql_net_amount(
        p_subtotal, p_discount_pct
    );
END//

DELIMITER ;
~~~

Gọi:

~~~sql
SET @lab347_result = NULL;

CALL lab347_mysql_calc_net(
    120000, 10, @lab347_result
);

SELECT @lab347_result AS net_vnd;
~~~

**@lab347_result** là **session user variable** của MySQL, không phải biến cục bộ DECLARE trong procedure. Nó có thể còn trên connection sau khi procedure kết thúc; cần lưu ý connection pooling.

### 21.1. MySQL sửa thân routine

MySQL 8.0 **không có CREATE OR REPLACE PROCEDURE/FUNCTION tương đương PostgreSQL** để sửa toàn bộ thân stored routine. **ALTER PROCEDURE/FUNCTION** chỉ thay đổi những thuộc tính được hỗ trợ, không phải bộ chỉnh sửa body tổng quát.

Muốn thay body, quy trình thường là:

1. Lưu định nghĩa hiện tại bằng SHOW CREATE.
2. Kiểm tra người gọi, quyền và definer.
3. DROP routine.
4. CREATE lại định nghĩa mới.
5. Tái lập quyền và kiểm thử.

~~~sql
SHOW CREATE FUNCTION lab347_mysql_net_amount;
SHOW CREATE PROCEDURE lab347_mysql_calc_net;
~~~

### 21.2. Test và DROP MySQL

~~~sql
SELECT lab347_mysql_net_amount(50000, 100)
    AS full_discount;

SET @lab347_result = NULL;
CALL lab347_mysql_calc_net(50000, 0, @lab347_result);
SELECT @lab347_result = 50000 AS test_passed;
~~~

Cleanup khi đã xong:

~~~sql
DROP PROCEDURE IF EXISTS lab347_mysql_calc_net;
DROP FUNCTION IF EXISTS lab347_mysql_net_amount;
~~~

MySQL có quy tắc **implicit commit** với nhiều DDL, nên không giả định một BEGIN...ROLLBACK sẽ hoàn tác chuỗi DROP/CREATE routine giống PostgreSQL.

## 22. SQL Server: CREATE OR ALTER FUNCTION

Trên những bản SQL Server hỗ trợ **CREATE OR ALTER** (ví dụ SQL Server 2016 SP1 trở lên), có thể tạo hoặc sửa routine bằng cùng mẫu:

~~~sql
CREATE OR ALTER FUNCTION dbo.lab347_net_amount (
    @subtotal DECIMAL(14,2),
    @discount_pct DECIMAL(5,2)
)
RETURNS DECIMAL(14,2)
AS
BEGIN
    RETURN CONVERT(
        DECIMAL(14,2),
        ROUND(
            @subtotal * (1 - @discount_pct / 100.0),
            2
        )
    );
END;
GO

SELECT dbo.lab347_net_amount(120000, 10) AS net_vnd;
GO
~~~

**GO** là dấu tách **batch của SSMS/sqlcmd hoặc client tương thích**, không phải một câu SQL do SQL Server xử lý. Khi dùng JDBC hoặc API, cần tổ chức batch theo quy tắc tương ứng.

### 22.1. SQL Server CREATE OR ALTER PROCEDURE

~~~sql
CREATE OR ALTER PROCEDURE dbo.lab347_calc_net
    @subtotal DECIMAL(14,2),
    @discount_pct DECIMAL(5,2),
    @result DECIMAL(14,2) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SET @result = dbo.lab347_net_amount(
        @subtotal, @discount_pct
    );
END;
GO
~~~

Gọi:

~~~sql
DECLARE @actual DECIMAL(14,2);

EXEC dbo.lab347_calc_net
    @subtotal = 120000,
    @discount_pct = 10,
    @result = @actual OUTPUT;

SELECT
    @actual AS actual_net,
    CASE WHEN @actual = 108000
        THEN 'PASS' ELSE 'FAIL'
    END AS test_result;
GO
~~~

Procedure T-SQL gọi bằng **EXEC/EXECUTE**, và OUT parameter sử dụng từ khóa **OUTPUT** trong cả định nghĩa và lời gọi.

### 22.2. ALTER FUNCTION/PROCEDURE

SQL Server cũng có **ALTER FUNCTION** và **ALTER PROCEDURE**. Khác PostgreSQL, ALTER của SQL Server có thể dùng để thay định nghĩa thân routine trong phạm vi hỗ trợ.

~~~sql
ALTER FUNCTION dbo.lab347_net_amount (
    @subtotal DECIMAL(14,2),
    @discount_pct DECIMAL(5,2)
)
RETURNS DECIMAL(14,2)
AS
BEGIN
    RETURN CONVERT(
        DECIMAL(14,2),
        ROUND(@subtotal * (1 - @discount_pct / 100.0), 2)
    );
END;
GO
~~~

Việc chạy CREATE/ALTER FUNCTION và PROCEDURE cần tuân thủ **quy tắc batch**. Đừng ghép mọi câu vào một chuỗi JDBC có GO rồi mong server tự hiểu.

### 22.3. Metadata và xóa

~~~sql
SELECT
    s.name AS schema_name,
    o.name AS routine_name,
    o.type_desc
FROM sys.objects AS o
JOIN sys.schemas AS s
    ON s.schema_id = o.schema_id
WHERE s.name = 'dbo'
  AND o.name IN ('lab347_net_amount', 'lab347_calc_net');
~~~

SQL Server có các view hệ thống như **sys.sql_modules** hoặc **OBJECT_DEFINITION** để xem code khi quyền cho phép.

Cleanup trên bản hỗ trợ IF EXISTS:

~~~sql
DROP PROCEDURE IF EXISTS dbo.lab347_calc_net;
DROP FUNCTION IF EXISTS dbo.lab347_net_amount;
~~~

### 22.4. Transaction khi test SQL Server DML procedure

Một procedure DML cần test dưới transaction. Trong SQL Server, dùng **TRY...CATCH** và **XACT_STATE()** để biết giao dịch còn COMMIT được không. BEGIN...END nhóm câu lệnh **khác BEGIN TRANSACTION**; không phải mọi lỗi đều có thể rollback tới savepoint.

## 23. Oracle: CREATE OR REPLACE FUNCTION

Trong Oracle PL/SQL:

~~~sql
CREATE OR REPLACE FUNCTION lab347_net_amount(
    p_subtotal IN NUMBER,
    p_discount_pct IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    IF p_subtotal < 0
       OR p_discount_pct < 0
       OR p_discount_pct > 100 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Invalid amount or discount'
        );
    END IF;

    RETURN ROUND(
        p_subtotal * (1 - p_discount_pct / 100),
        2
    );
END;
/
~~~

Dấu **/** trên dòng riêng thường được SQL*Plus/SQLcl dùng để thực thi buffer chứa thân PL/SQL; nó **không phải lệnh SQL server chung cho mọi driver**.

Gọi function:

~~~sql
SELECT lab347_net_amount(120000, 10) AS net_vnd
FROM dual;
~~~

### 23.1. Oracle CREATE OR REPLACE PROCEDURE

~~~sql
CREATE OR REPLACE PROCEDURE lab347_calc_net(
    p_subtotal IN NUMBER,
    p_discount_pct IN NUMBER,
    p_result OUT NUMBER
)
AS
BEGIN
    p_result := lab347_net_amount(
        p_subtotal, p_discount_pct
    );
END;
/
~~~

Gọi và test bằng PL/SQL:

~~~sql
DECLARE
    v_result NUMBER;
BEGIN
    lab347_calc_net(120000, 10, v_result);

    IF v_result <> 108000 THEN
        RAISE_APPLICATION_ERROR(
            -20002, 'Unexpected net amount'
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE('PASS: ' || v_result);
END;
/
~~~

Client phải bật/đọc **DBMS_OUTPUT** nếu muốn thấy thông báo. Việc không nhìn thấy dòng PUT_LINE chưa đủ để kết luận routine không chạy.

### 23.2. Sau REPLACE cần kiểm tra VALID

Một CREATE OR REPLACE có lỗi biên dịch trên Oracle có thể để lại object có trạng thái **INVALID**. Vì vậy:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB347_NET_AMOUNT',
    'LAB347_CALC_NET'
);

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN (
    'LAB347_NET_AMOUNT',
    'LAB347_CALC_NET'
)
ORDER BY name, sequence;
~~~

Routine tồn tại trong catalog **không tự chứng minh body hợp lệ hoặc test đã pass**.

### 23.3. Package và chữ ký

Oracle còn có **PACKAGE specification/body** để nhóm procedure/function, overload và công bố interface. Khi sửa một routine nằm trong package, cần xét compatibility của specification, body và các đối tượng phụ thuộc.

### 23.4. Cleanup Oracle

~~~sql
DROP PROCEDURE lab347_calc_net;
DROP FUNCTION lab347_net_amount;
~~~

Trong Oracle, nhiều câu DDL có **implicit COMMIT**, nên không dựa vào ROLLBACK để undo việc CREATE/DROP routine theo cùng cơ chế PostgreSQL.

## 24. SQLite: UDF đăng ký từ ứng dụng

SQLite SQL lõi **không có CREATE PROCEDURE** kiểu stored routine của PostgreSQL/MySQL/SQL Server/Oracle. Nó cũng không lưu function procedural mới bằng một lệnh CREATE FUNCTION SQL lõi tương đương.

Ứng dụng có thể đăng ký **user-defined function (UDF)** bằng host API:

- **sqlite3_create_function_v2()** từ C API.
- **Connection.create_function()** của Python sqlite3.
- API tương ứng của driver/ngôn ngữ host hoặc extension.

### 24.1. Ví dụ Python độc lập

Ví dụ dùng số nguyên VND và phần trăm giảm nguyên để tránh biểu diễn tiền bằng float trong trường hợp mẫu:

~~~python
import sqlite3

conn = sqlite3.connect(":memory:")

def net_vnd(subtotal_vnd, discount_pct):
    if subtotal_vnd is None or discount_pct is None:
        return None
    if subtotal_vnd < 0 or not (0 <= discount_pct <= 100):
        raise ValueError("Invalid amount or discount")
    # Với số không âm, làm tròn tới đơn vị VND.
    return (subtotal_vnd * (100 - discount_pct) + 50) // 100

conn.create_function(
    "lab347_net_vnd", 2, net_vnd, deterministic=True
)

result = conn.execute(
    "SELECT lab347_net_vnd(?, ?)",
    (120000, 10)
).fetchone()[0]

print(result)  # 108000
conn.close()
~~~

**Khác biệt vòng đời:** UDF đã đăng ký thường gắn với **connection**, không tự trở thành routine trong file SQLite để kết nối khác gọi. Đóng connection làm đăng ký của connection ấy hết hiệu lực. Nếu có pool, phải đăng ký trên những connection cần sử dụng.

Ví dụ này trả **số nguyên VND**, không đồng nhất hoàn toàn với hàm PostgreSQL trả NUMERIC hai chữ số thập phân. Nếu nghiệp vụ cần discount lẻ hoặc tiền có phần lẻ, phải thiết kế Decimal/integer cents và quy tắc làm tròn riêng.

### 24.2. Không có DROP FUNCTION SQL lõi tương đương

Không copy:

~~~sql
-- Không phải câu SQL SQLite core để xóa UDF host:
DROP FUNCTION lab347_net_vnd;
~~~

Thay vào đó, code host quản lý vòng đời đăng ký function/extension. Tương tự, SQLite không cung cấp CREATE PROCEDURE/CALL stored procedure native theo mô hình server RDBMS trên.

### 24.3. Khi không cần UDF

Câu SQL tính toán có thể dùng CTE:

~~~sql
WITH params(subtotal_vnd, discount_pct) AS (
    VALUES (120000, 10.0)
)
SELECT
    ROUND(
        subtotal_vnd * (1 - discount_pct / 100.0),
        2
    ) AS net_vnd
FROM params;
~~~

CTE không phải stored routine; nó đặt tên cho một phần truy vấn trong **một statement**. Với ứng dụng SQLite, nhiều workflow phù hợp hơn khi xử lý biến/nhánh tại ngôn ngữ host và thực thi SQL set-based trong transaction.

## 25. Kiểm thử routine từ Java/JDBC

Để gọi function PostgreSQL, Java có thể dùng **PreparedStatement**:

~~~java
String sql = "SELECT lab347.net_amount(?, ?) AS net_vnd";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("120000"));
    ps.setBigDecimal(2, new BigDecimal("10"));

    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new IllegalStateException("Missing result");
        }

        BigDecimal actual = rs.getBigDecimal("net_vnd");
        if (actual.compareTo(new BigDecimal("108000")) != 0) {
            throw new AssertionError("Unexpected amount");
        }
    }
}
~~~

Đây là **đoạn minh họa** giả định đã có biến connection và import java.sql/BigDecimal. Dùng **BigDecimal** thay float/double cho NUMERIC tiền, và compareTo khi cần so sánh giá trị số không phụ thuộc scale.

### 25.1. Test procedure trong transaction JDBC

~~~java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        "CALL lab347.approve_invoice(?)")) {
    ps.setInt(1, 1001);
    ps.execute();

    // Test có thể SELECT invoices và invoice_audit để assert.
    // Hủy thay đổi fixture của ca thử:
    connection.rollback();
} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
}
~~~

Trong ứng dụng thực tế, khi mọi bước bắt buộc hoàn thành, transaction có thể COMMIT thay vì rollback. **Trong test** ta rollback để giữ dữ liệu đầu vào. Nếu procedure gây lỗi PostgreSQL, rollback cũng giúp tránh trả connection ở trạng thái transaction aborted về pool.

### 25.2. CallableStatement khác theo driver

JDBC còn có **CallableStatement** để gọi stored procedure và xử lý OUT parameters. Nhưng cú pháp escape call, cách function trả kết quả và hỗ trợ OUT phụ thuộc driver:

- PostgreSQL phân biệt function và procedure.
- MySQL có cú pháp CALL và cơ chế OUT riêng.
- SQL Server dùng EXEC/EXECUTE.
- Oracle có procedure/function trong PL/SQL và package.

Không mặc định một chuỗi call JDBC duy nhất có ý nghĩa đồng nhất ở cả bốn hệ.

## 26. Test cần độc lập và lặp lại được

Một ca test không nên dựa vào ca trước đã thay đổi dữ liệu:

~~~text
Test A duyệt invoice 1001.
Test B ngầm giả định Test A đã duyệt.
Test C ngầm giả định audit_id = 2.
~~~

Khi chạy riêng Test B, hoặc chạy test song song, kết quả sẽ không ổn định.

Thay vào đó:

1. Mỗi ca có **fixture và trạng thái ban đầu rõ ràng**.
2. Mỗi ca chạy trong transaction phù hợp nếu có DML.
3. Kiểm tra kết quả ngay trong transaction.
4. **ROLLBACK/cleanup** sau ca.
5. Không assert identity ID phải liên tiếp.
6. Với side effect ngoài database, dùng sandbox/mock hoặc cơ chế bù trừ.
7. Kiểm tra cả **role, schema/search_path** và chữ ký caller dùng thật.

### 26.1. Deadlock, retry và idempotency

Một function thuần tính toán thường dễ test hơn procedure có nhiều writer. Procedure thực tế cần xét:

- Hai transaction gọi trên cùng invoice.
- Trạng thái bị đổi trước khi lời gọi đến.
- Deadlock hoặc serialization failure cần retry toàn transaction khi thích hợp.
- Mất phản hồi sau COMMIT khiến client **không chắc transaction đã thành công hay chưa**.
- Lời gọi lặp có tạo audit hoặc tác vụ ngoài database hai lần không.

Phiên bản V2 của approve_invoice có chính sách không tạo audit lặp khi status APPROVED, nhưng không thay thế thiết kế **request idempotency key** và cơ chế đối soát trong hệ phân tán.

## 27. Bảng tổng hợp kiểm thử theo phương ngữ

| Mục tiêu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Test giá trị hàm | SELECT f(...) | SELECT f(...) | SELECT schema.f(...) | SELECT f(...) FROM dual | SELECT UDF đã đăng ký |
| Test procedure có OUT | CALL với tham số phù hợp | CALL + OUT/@session var hoặc driver | EXEC + OUTPUT | PL/SQL block/OUT | Không có procedure native |
| Tạo lỗi nghiệp vụ | RAISE EXCEPTION | SIGNAL SQLSTATE | THROW | RAISE_APPLICATION_ERROR | Exception từ host UDF/SQL constraint |
| Quan sát số hàng DML | GET DIAGNOSTICS ROW_COUNT | ROW_COUNT() | @@ROWCOUNT | SQL%ROWCOUNT | API rows affected/changes() theo ngữ cảnh |
| Dọn DML test | Transaction ROLLBACK | ROLLBACK khi bảng transactional | ROLLBACK nếu transaction hợp lệ; XACT_STATE | ROLLBACK | ROLLBACK qua SQL/API |
| DDL rollback giống PostgreSQL? | Nhiều DDL transactional | Nhiều DDL implicit commit | Có quy tắc riêng | Nhiều DDL implicit commit | DDL thường có thể transactional theo SQLite |
| Kiểm tra code | pg_get_functiondef/pg_proc | SHOW CREATE ROUTINE | sys.sql_modules | USER_OBJECTS/USER_ERRORS | Code host/extension |

Đây là bảng định hướng, **không thay thế tài liệu phiên bản cụ thể** về transaction, quyền và giới hạn từng loại routine.

## 28. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo routine chưa rõ kiểu trả về | Caller không có contract ổn định | Định nghĩa tên, input, output trước |
| Nhầm function với procedure | Dùng sai SELECT/CALL/EXEC | Phân biệt cách gọi theo hệ |
| Nghĩ PostgreSQL REPLACE đổi tùy ý return type | Migration thất bại | Tạo contract v2 và chuyển caller |
| Đổi tên tham số mà bỏ qua named calls | API cũ có thể hỏng | Xem caller và signature |
| Có overload nhưng DROP thiếu kiểu | Không xác định đúng routine | Nêu schema + arg types |
| Thêm DROP ... CASCADE để hết lỗi | Xóa object phụ thuộc | Rà dependency |
| Chỉ test input bình thường | Không thấy lỗi NULL/biên | Test matrix |
| Test procedure chỉ kiểm tra CALL không lỗi | Audit hoặc dữ liệu có thể sai | Assert mọi side effect |
| Test DML không rollback | Dữ liệu test bị lệch | Transaction/fixture riêng |
| Đòi audit identity chạy liên tiếp | Sequence có thể có gap | Assert business event |
| Test lỗi PostgreSQL rồi SELECT tiếp | Transaction aborted/25P02 | ROLLBACK TO SAVEPOINT hoặc ROLLBACK |
| Gọi lặp routine không idempotent sau timeout | Trùng audit hoặc giao dịch | Thiết kế retry/idempotency |
| Nghĩ MySQL CREATE OR REPLACE routine giống PostgreSQL | Sai cú pháp | DROP/CREATE có migration |
| Cho DELIMITER vào SQL gửi JDBC | Không phải SQL server | Chỉ dùng client hỗ trợ |
| Cho GO vào batch JDBC SQL Server | GO là lệnh client | Tách batch |
| Oracle CREATE OR REPLACE không xem trạng thái | Object có thể INVALID | USER_OBJECTS/USER_ERRORS |
| SQLite dùng CREATE PROCEDURE | Không hỗ trợ trong SQL core | Host API và transaction |
| SQLite UDF chỉ đăng ký connection A | Connection B không thấy | Đăng ký theo connection |
| Dùng float để tính tiền rồi assert chính xác | Sai số nhị phân | DECIMAL/BigDecimal/int cents |
| Chỉ test routine bằng admin | Bỏ sót lỗi EXECUTE và quyền nguồn | Test role ứng dụng |
| SECURITY DEFINER không kiểm soát search_path | Rủi ro privilege escalation | Schema-qualify, least privilege |
| Sửa routine trực tiếp trên production | Drift giữa môi trường | Migration được version hóa |
| Nghĩ DROP routine undo DML đã COMMIT | Dữ liệu lịch sử vẫn còn | Phân biệt DDL và rollback |

## 29. Bài tập thực hành

Với bài PostgreSQL, dùng schema lab347 theo phần 5. Khi thử procedure có DML, chạy trong **BEGIN ... ROLLBACK**; bài về cú pháp khác cần hệ quản trị tương ứng.

1. Phân biệt function, procedure và trigger về cách thực thi và mục đích.
2. Tạo hai bảng invoices và invoice_audit trong schema lab347, nhập bốn hóa đơn mẫu.
3. Viết CREATE FUNCTION LANGUAGE SQL tính net amount theo subtotal và discount.
4. Gọi hàm với (120000,10), (50000,0), (50000,100); ghi expected result.
5. Thử NULL khi function khai báo RETURNS NULL ON NULL INPUT.
6. Sửa thân hàm bằng CREATE OR REPLACE FUNCTION PL/pgSQL, thêm validation discount 0–100.
7. Viết test discount 101 phải phát sinh SQLSTATE 22023; không bắt mọi exception như PASS.
8. Giải thích vì sao RETURNS NUMERIC sang RETURNS TEXT cần migration hợp đồng.
9. Tạo overload net_amount(NUMERIC) dùng discount 0.
10. Viết hai DROP FUNCTION riêng cho overload một và hai tham số.
11. Gọi function bằng named arguments và thảo luận thay đổi tên tham số.
12. Tạo procedure approve_invoice có SELECT INTO STRICT, FOR UPDATE, UPDATE, ROW_COUNT và INSERT audit.
13. CALL approve_invoice(1001) trong transaction; kiểm tra net và audit, rồi ROLLBACK.
14. Dùng DO assertion để chắc chắn net = 108000 và đúng một audit.
15. Dùng SAVEPOINT thử lỗi trạng thái CANCELLED cho invoice 1003.
16. Thử invoice 9999 và giải thích NO_DATA_FOUND.
17. Thử gọi procedure phiên bản đầu hai lần và mô tả lần thứ hai.
18. Thay procedure để gọi lại trên APPROVED không thêm audit; test hai lần.
19. Dùng ALTER FUNCTION sửa COST; phân biệt với sửa thân.
20. Tra pg_proc xem chữ ký và loại routine của net_amount/approve_invoice.
21. Dùng pg_get_functiondef lấy định nghĩa hiện tại của function.
22. Thiết kế danh sách test: bình thường, biên, NULL, input lỗi, thiếu hàng, side effect.
23. Giải thích vì sao audit_id không bắt buộc chạy liên tiếp sau test ROLLBACK.
24. Đề xuất quy trình DROP các object mà không dùng CASCADE.
25. Kiểm tra quyền EXECUTE dưới một role ứng dụng; khác biệt với admin.
26. Đề xuất các bước bảo vệ một SECURITY DEFINER function.
27. Viết CREATE FUNCTION MySQL và giải thích vai trò DELIMITER của mysql CLI.
28. MySQL 8.0 muốn thay body procedure thì ALTER PROCEDURE có đủ không?
29. Viết procedure MySQL có IN/OUT và nhận kết quả qua @user_variable.
30. Viết SQL Server CREATE OR ALTER FUNCTION và gọi trong SELECT.
31. Viết SQL Server procedure có OUTPUT rồi gọi qua EXEC.
32. Giải thích vì sao GO không phải SQL server.
33. Viết Oracle CREATE OR REPLACE FUNCTION và block PL/SQL gọi procedure OUT.
34. Oracle USER_ERRORS và USER_OBJECTS giúp kiểm tra điều gì?
35. Đăng ký SQLite UDF qua Python create_function và gọi bằng SELECT.
36. Vì sao một UDF SQLite trên connection A không tự có trên connection B?
37. Thiết kế migration khi net_amount cần trả JSON mà caller cũ cần NUMERIC.
38. Thiết kế cách test side effect email/HTTP sao cho không gửi thật.
39. Vì sao không nên dùng cùng chiến lược rollback DDL trên PostgreSQL, MySQL và Oracle?
40. Xác định rủi ro khi client retry CALL approve_invoice sau khi mất phản hồi COMMIT.

### Câu hỏi tự kiểm tra

**Câu 1.** PostgreSQL scalar function thường gọi bằng CALL giống procedure không?

**Đáp án:** **Không.** Function dùng SELECT/biểu thức; procedure dùng CALL.

**Câu 2.** CREATE OR REPLACE FUNCTION PostgreSQL có thể đổi RETURNS NUMERIC thành TEXT mà giữ cùng chữ ký cũ?

**Đáp án:** **Không.** Đây là thay đổi contract cần migration hoặc routine mới.

**Câu 3.** Hai hàm net_amount(NUMERIC) và net_amount(NUMERIC,NUMERIC) là một object?

**Đáp án:** **Không.** Chúng là hai overload với signature khác nhau.

**Câu 4.** Vì sao cần arg types khi DROP FUNCTION PostgreSQL?

**Đáp án:** Để xác định đúng overload cần xóa.

**Câu 5.** CALL procedure không báo lỗi đã đủ để coi test thành công?

**Đáp án:** **Chưa.** Cần xác minh dữ liệu đích, audit và các side effect.

**Câu 6.** ROLLBACK trong test có đảm bảo identity sequence trở lại số cũ?

**Đáp án:** **Không.** Sequence có thể có khoảng trống sau rollback.

**Câu 7.** Sau lỗi trong transaction PostgreSQL, có thể SELECT tiếp bình thường ngay không?

**Đáp án:** **Thường không.** Cần ROLLBACK hoặc ROLLBACK TO SAVEPOINT hợp lệ.

**Câu 8.** MySQL ALTER PROCEDURE có thay body như PostgreSQL CREATE OR REPLACE không?

**Đáp án:** **Không.** Thường cần DROP/CREATE khi thay body.

**Câu 9.** SQL Server GO là câu SQL được server thực thi?

**Đáp án:** **Không.** Đó là dấu phân tách batch của công cụ client.

**Câu 10.** Oracle CREATE OR REPLACE thành công về mặt gửi lệnh đã bảo đảm routine VALID?

**Đáp án:** **Không.** Cần xem trạng thái compile và USER_ERRORS.

**Câu 11.** SQLite UDF đăng ký trên một connection được lưu như procedure permanent trong file DB?

**Đáp án:** **Không.** UDF đăng ký qua host thường gắn với connection.

**Câu 12.** DROP procedure có rollback những dữ liệu đã COMMIT trong quá khứ?

**Đáp án:** **Không.** DROP xóa code, không hoàn tác lịch sử DML.

## 30. Ghi nhớ cốt lõi

**Routine là code có hợp đồng trong hệ dữ liệu.** Hãy thiết kế tên, schema, tham số, kiểu trả về, ngữ nghĩa NULL, lỗi và side effect trước khi nghĩ tới CREATE/ALTER/DROP.

Trong **PostgreSQL**, dùng **CREATE FUNCTION/PROCEDURE**, thay thân bằng **CREATE OR REPLACE** khi contract tương thích, dùng **ALTER** cho thuộc tính được hỗ trợ và **DROP đúng chữ ký** khi đã xử lý phụ thuộc. Overloading khiến tên routine một mình chưa chắc xác định được một object duy nhất.

Kiểm thử không chỉ là chạy lệnh:

~~~text
Function:
  input → expected output
  normal / boundary / NULL / invalid

Procedure:
  fixture → CALL → assert dữ liệu + audit → ROLLBACK
  valid / missing / wrong status / retry / concurrency

Migration:
  signature → dependency → quyền → REPLACE hoặc version mới
  → regression tests → chuyển caller → DROP bản cũ
~~~

**MySQL** thường cần DROP/CREATE để thay body stored routine; **SQL Server** dùng ALTER hoặc CREATE OR ALTER và EXEC; **Oracle** dùng CREATE OR REPLACE nhưng còn phải kiểm tra trạng thái VALID; **SQLite** thường đăng ký UDF bằng host API hoặc dùng CTE/SQL thay cho procedure native.

Cuối cùng, **cú pháp CREATE chạy được không đồng nghĩa routine đã đúng và an toàn để triển khai**. Quan trọng hơn là hợp đồng tương thích, quyền EXECUTE, transaction, xử lý side effect và một bộ kiểm thử có thể lặp lại.
