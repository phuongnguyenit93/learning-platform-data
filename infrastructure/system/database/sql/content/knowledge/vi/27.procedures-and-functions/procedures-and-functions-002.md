# Khối lệnh, biến cục bộ và phép gán theo phương ngữ

Trong SQL thuần, một câu lệnh thường mô tả **tập dữ liệu cần đọc hoặc thay đổi**. Nhưng khi xây dựng **hàm** (*function*), **thủ tục** (*procedure*), **trigger** hoặc một khối lệnh chạy một lần, ta còn cần các công cụ của lập trình thủ tục: **biến cục bộ**, **gán giá trị**, **rẽ nhánh**, **lặp**, và **phạm vi của biến**.

Ví dụ, một thủ tục xác nhận đơn hàng có thể phải:

1. Nhận một **mã đơn** từ tham số.
2. Đọc **tổng tiền trước giảm giá** từ bảng.
3. Tính **tiền giảm** và **số tiền phải trả**.
4. Kiểm tra đơn còn ở trạng thái cho phép xác nhận.
5. Cập nhật bảng đơn, ghi nhật ký và trả kết quả.

Mã giả có thể rất đơn giản:

~~~text
amount := lấy tổng tiền của đơn
discount := amount * percent / 100
net_amount := amount - discount

IF đơn hợp lệ THEN
    UPDATE orders
END IF
~~~

Tuy nhiên, khi chuyển sang một hệ quản trị thực tế, cú pháp khác nhau đáng kể:

- **PostgreSQL PL/pgSQL:** DECLARE ở đầu khối; gán bằng **:=** (hoặc = trong ngữ cảnh gán PL/pgSQL); **SELECT ... INTO biến**; **DO $$ ... $$**.
- **MySQL stored programs:** **BEGIN ... END**, DECLARE trước câu lệnh thực thi; **SET biến = biểu thức**, **SELECT ... INTO biến**; **DELIMITER** là lệnh của client.
- **SQL Server T-SQL:** **DECLARE @bien**, **SET @bien = ...**, **SELECT @bien = ...**; BEGIN...END nhóm câu lệnh nhưng không tạo cùng một kiểu phạm vi biến như PL/pgSQL.
- **Oracle PL/SQL:** **DECLARE ... BEGIN ... EXCEPTION ... END;**; gán bằng **:=**, SELECT ... INTO thường phải trả **đúng một hàng**.
- **SQLite:** SQL lõi **không có hệ biến cục bộ và khối thủ tục tự do giống bốn hệ trên**; thường dùng tham số do ứng dụng bind, CTE hoặc trigger.

Bài học thuộc chương **Thủ tục và hàm** của module **Database SQL**. Phần thực hành chi tiết sử dụng **PostgreSQL 15+**, còn những ví dụ theo phương ngữ khác được tách riêng để tránh hiểu nhầm một cú pháp có thể chạy ở mọi database.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **SQL khai báo** với **ngôn ngữ thủ tục** được nhúng vào hệ quản trị.
2. Giải thích **khối lệnh**, **phạm vi cục bộ**, **tham số**, **biến**, **hằng** và **phép gán**.
3. Viết một **DO block PL/pgSQL** có DECLARE, BEGIN...END, IF, SELECT INTO và UPDATE.
4. Phân biệt **:=**, **SELECT INTO**, **PERFORM**, **FOUND** và **GET DIAGNOSTICS** của PL/pgSQL.
5. Nhận biết biến **record**, **%TYPE**, **%ROWTYPE**, biến nullable và biến có DEFAULT.
6. Tránh nhầm **SELECT INTO biến trong PL/pgSQL** với **SELECT INTO tạo bảng** trong SQL ở những hệ hỗ trợ cách đó.
7. Viết stored procedure MySQL có **DECLARE**, **SET** và **SELECT ... INTO**, phân biệt biến cục bộ với **@user_variable**.
8. So sánh **SET @v = ...** và **SELECT @v = ...** trong SQL Server, cùng phạm vi batch và sự khác nhau giữa BEGIN...END với BEGIN TRANSACTION.
9. Viết một khối Oracle PL/SQL và hiểu **NO_DATA_FOUND**, **TOO_MANY_ROWS**, SQL%ROWCOUNT.
10. Sử dụng tham số và CTE thay cho biến thủ tục khi làm việc với **SQLite**.
11. Áp dụng cách đặt tên, quản lý NULL, kiểm tra số hàng và giao dịch để tránh lỗi thường gặp.

## 2. Ba lớp khác nhau: SQL, ngôn ngữ thủ tục và chương trình gọi SQL

Hãy hình dung ba lớp:

~~~text
Ứng dụng Java / Python / Node.js
          |
          | gọi SQL hoặc CALL procedure
          v
    Database server
          |
    +-----+-------------------+
    |                         |
 SQL khai báo           Ngôn ngữ thủ tục
 SELECT/INSERT          DECLARE/IF/LOOP
 UPDATE/DELETE          biến/tham số/gán
    |                         |
    +-----------+-------------+
                |
             Bảng dữ liệu
~~~

**SQL khai báo** diễn đạt *cần kết quả gì*, ví dụ:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

**Ngôn ngữ thủ tục** cho phép tổ chức *trình tự và điều kiện thực hiện*:

~~~text
đọc trạng thái đơn
IF trạng thái = NEW THEN
    tính tiền
    UPDATE đơn
ELSE
    báo lỗi
END IF
~~~

**Ứng dụng** có thể thực hiện cùng logic bằng nhiều SQL trong transaction, hoặc gọi một procedure để cơ sở dữ liệu thực thi. Chọn nơi đặt logic phụ thuộc kiến trúc, nhu cầu kiểm soát giao dịch, quyền, hiệu năng và khả năng bảo trì.

### 2.1. Không phải mọi biểu thức đều cần biến

Một phép tính tập hợp đơn giản thường không cần khối thủ tục:

~~~sql
SELECT
    order_id,
    subtotal_vnd,
    discount_pct,
    ROUND(subtotal_vnd * (1 - discount_pct / 100), 2) AS net_vnd
FROM orders;
~~~

Nếu SQL khai báo biểu diễn công việc rõ và hiệu quả, không cần tạo thủ tục chỉ để có biến trung gian. Biến hữu ích khi cần **kiểm tra điều kiện, tổ chức các bước, phản hồi lỗi hoặc giữ trạng thái cục bộ** trong phạm vi thực thi.

## 3. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Khối lệnh (block)** | Nhóm khai báo và câu lệnh được thực thi trong một phạm vi | DECLARE ... BEGIN ... END |
| **Biến cục bộ** | Vị trí lưu giá trị thuộc một phạm vi thực thi | v_subtotal |
| **Tham số** | Giá trị truyền vào hoặc ra khỏi function/procedure | p_order_id |
| **Hằng (constant)** | Giá trị không được phép gán lại theo ngôn ngữ | v_rate CONSTANT NUMERIC |
| **Phép gán** | Đặt kết quả biểu thức vào biến | v_total := v_price * v_qty |
| **Khởi tạo** | Đặt giá trị khi biến được tạo hoặc khối bắt đầu | v_count INTEGER := 0 |
| **Scope/phạm vi** | Đoạn mã có thể truy cập một biến | bên trong block |
| **Shadowing/che khuất tên** | Biến ở phạm vi trong cùng tên với biến ngoài | v_count ở block con |
| **Session variable** | Biến gắn với kết nối thay vì một lần gọi thủ tục | @x của MySQL |
| **Bind parameter** | Placeholder nhận giá trị từ chương trình hoặc client | ? hoặc :name |

Một lỗi quan trọng là coi **biến cục bộ của procedure** giống **cột bảng** hoặc **biến phiên kết nối**. Chúng có vòng đời, cú pháp và phạm vi truy cập khác nhau.

### 3.1. Vòng đời thông thường của một biến

~~~text
Gọi procedure / vào block
            |
            v
       Khai báo biến
            |
            v
      Khởi tạo giá trị
            |
            v
      Gán/đọc trong block
            |
            v
        Ra khỏi scope
            |
            v
    Biến cục bộ hết hiệu lực
~~~

Không được dựa vào biến cục bộ để lưu trạng thái lâu dài giữa hai kết nối hay hai lần gọi thủ tục. Muốn lưu trạng thái bền vững, cần bảng hoặc cơ chế lưu trữ được thiết kế riêng.

## 4. Bảng đối chiếu cú pháp nhanh

| Tác vụ | PostgreSQL PL/pgSQL | MySQL stored program | SQL Server T-SQL | Oracle PL/SQL |
| --- | --- | --- | --- | --- |
| Khối cơ bản | DECLARE ... BEGIN ... END | BEGIN ... END | BEGIN ... END | DECLARE ... BEGIN ... END |
| Khai báo số | v_sum NUMERIC; | DECLARE v_sum DECIMAL(12,2); | DECLARE @sum DECIMAL(12,2); | v_sum NUMBER; |
| Gán từ biểu thức | v_sum := 100; | SET v_sum = 100; | SET @sum = 100; | v_sum := 100; |
| Gán từ query 1 hàng | SELECT col INTO v_sum ... | SELECT col INTO v_sum ... | SELECT @sum = col ... | SELECT col INTO v_sum ... |
| Tham số | p_id INTEGER | IN p_id INT | @id INT | p_id IN NUMBER |
| Ghi thông báo debug | RAISE NOTICE | SELECT hoặc cơ chế log/diagnostics | PRINT/SELECT | DBMS_OUTPUT.PUT_LINE |
| Biến ngoài thủ tục | Không như cú pháp DECLARE của PL/pgSQL trong SQL thuần | @session_var | @local trong batch | Bind variable client :name, không phải local |

**Không sao chép trực tiếp một cột cú pháp sang hệ khác.** Đặc biệt, chữ **SELECT INTO** có nhiều ý nghĩa tùy ngữ cảnh. Phần sau sẽ phân tích.

## 5. Chuẩn bị dữ liệu PostgreSQL tự chứa

Ví dụ xuyên suốt là xác nhận một hóa đơn đang ở trạng thái NEW. Ta cần đọc subtotal và discount, tính net amount, chuyển trạng thái sang APPROVED, rồi ghi audit.

Tạo hai bảng tạm:

~~~sql
CREATE TEMP TABLE lab_blocks_invoices (
    invoice_id      INTEGER PRIMARY KEY,
    customer_code   TEXT NOT NULL,
    subtotal_vnd    NUMERIC(12,2) NOT NULL CHECK (subtotal_vnd >= 0),
    discount_pct    NUMERIC(5,2) NOT NULL
        CHECK (discount_pct BETWEEN 0 AND 100),
    net_amount_vnd  NUMERIC(12,2),
    status          TEXT NOT NULL
        CHECK (status IN ('NEW', 'APPROVED', 'CANCELLED'))
);

CREATE TEMP TABLE lab_blocks_audit (
    audit_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id     INTEGER NOT NULL REFERENCES lab_blocks_invoices(invoice_id),
    action_name    TEXT NOT NULL,
    amount_vnd     NUMERIC(12,2),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lab_blocks_invoices
    (invoice_id, customer_code, subtotal_vnd, discount_pct,
     net_amount_vnd, status)
VALUES
    (1001, 'C-001', 120000, 10, NULL, 'NEW'),
    (1002, 'C-002',  50000,  0, NULL, 'NEW'),
    (1003, 'C-003', 200000, 15, 170000, 'APPROVED'),
    (1004, 'C-004',  80000,  5, NULL, 'CANCELLED');
~~~

Các giá trị dự kiến khi tính:

| invoice_id | subtotal_vnd | discount_pct | net amount nếu tính | status ban đầu |
| ---: | ---: | ---: | ---: | --- |
| 1001 | 120000 | 10 | 108000 | NEW |
| 1002 | 50000 | 0 | 50000 | NEW |
| 1003 | 200000 | 15 | 170000 | APPROVED |
| 1004 | 80000 | 5 | 76000 | CANCELLED |

Chúng ta **chỉ xác nhận hóa đơn NEW**, vì vậy không nên tự đổi hóa đơn 1003 đã duyệt hoặc 1004 bị hủy.

## 6. PostgreSQL: DO block với DECLARE, BEGIN, END

Một **DO block** của PostgreSQL chạy một khối mã vô danh một lần. Với PL/pgSQL:

~~~sql
DO $$
DECLARE
    v_message TEXT := 'Xin chao tu PL/pgSQL';
BEGIN
    RAISE NOTICE '%', v_message;
END;
$$ LANGUAGE plpgsql;
~~~

Trong đó:

- **DO** thực thi khối vô danh, không cần tạo một hàm có tên.
- **$$ ... $$** là cách **dollar-quote** nội dung mã, tránh phải escape nhiều dấu nháy đơn; đây không phải ký hiệu bắt đầu transaction.
- **DECLARE** chứa khai báo biến cục bộ.
- **BEGIN ... END** của PL/pgSQL là **khối lệnh**, không đồng nghĩa **BEGIN TRANSACTION**.
- **RAISE NOTICE** gửi thông báo trong PostgreSQL, không lưu thông báo như một hàng bảng.
- **LANGUAGE plpgsql** chỉ định ngôn ngữ; PL/pgSQL là lựa chọn thông dụng cho procedural code PostgreSQL.

### 6.1. Khối vô danh hoàn chỉnh: duyệt hóa đơn 1001

~~~sql
DO $$
DECLARE
    v_invoice_id   INTEGER := 1001;
    v_subtotal     NUMERIC(12,2);
    v_discount_pct NUMERIC(5,2);
    v_net_amount   NUMERIC(12,2);
    v_status       TEXT;
    v_updated      INTEGER := 0;
BEGIN
    SELECT
        i.subtotal_vnd,
        i.discount_pct,
        i.status
    INTO STRICT
        v_subtotal,
        v_discount_pct,
        v_status
    FROM lab_blocks_invoices AS i
    WHERE i.invoice_id = v_invoice_id
    FOR UPDATE;

    IF v_status <> 'NEW' THEN
        RAISE EXCEPTION
            'Hoa don % khong o trang thai NEW: %',
            v_invoice_id, v_status;
    END IF;

    v_net_amount :=
        ROUND(v_subtotal * (1 - v_discount_pct / 100), 2);

    UPDATE lab_blocks_invoices AS i
    SET
        net_amount_vnd = v_net_amount,
        status = 'APPROVED'
    WHERE i.invoice_id = v_invoice_id
      AND i.status = 'NEW';

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated <> 1 THEN
        RAISE EXCEPTION
            'Khong cap nhat duoc dung mot hoa don: %',
            v_invoice_id;
    END IF;

    INSERT INTO lab_blocks_audit
        (invoice_id, action_name, amount_vnd)
    VALUES
        (v_invoice_id, 'APPROVE', v_net_amount);

    RAISE NOTICE
        'Invoice %, net amount %, affected rows %',
        v_invoice_id, v_net_amount, v_updated;
END;
$$ LANGUAGE plpgsql;
~~~

Kết quả logic:

1. **SELECT INTO STRICT** lấy đúng một hóa đơn và khóa hàng với **FOR UPDATE**.
2. IF yêu cầu trạng thái **NEW**.
3. Phép gán **:=** tính **108.000 VND**.
4. UPDATE ghi net_amount_vnd và chuyển trạng thái.
5. **GET DIAGNOSTICS ... ROW_COUNT** xác nhận một hàng được cập nhật.
6. INSERT audit ghi lại hành động.
7. RAISE NOTICE cho biết kết quả chạy.

Đọc sau khi chạy:

~~~sql
SELECT invoice_id, net_amount_vnd, status
FROM lab_blocks_invoices
WHERE invoice_id = 1001;

SELECT invoice_id, action_name, amount_vnd
FROM lab_blocks_audit
ORDER BY audit_id;
~~~

Hóa đơn 1001 có net_amount_vnd = **108000.00**, status **APPROVED**, và một bản ghi audit của hành động APPROVE.

### 6.2. DO không tự đảm bảo toàn bộ workflow dài là một giao dịch độc lập

DO là một câu lệnh gửi đến server. Nếu ứng dụng cần nhiều câu SQL phải cùng COMMIT hoặc ROLLBACK, cần quản lý **transaction boundary** phù hợp. Trong PostgreSQL, các câu lệnh DML bên trong cùng một DO được thực hiện trong ngữ cảnh giao dịch của câu lệnh đó, nhưng không nên nhầm **BEGIN của PL/pgSQL** với lệnh bắt đầu transaction SQL.

Trong giao dịch tường minh:

~~~sql
BEGIN;

-- Một hoặc nhiều DO/SELECT/UPDATE.
SELECT invoice_id, status
FROM lab_blocks_invoices
WHERE invoice_id = 1001;

ROLLBACK;
~~~

**BEGIN;** ở ngoài là lệnh transaction. **BEGIN ... END;** ở trong DO là cặp từ khóa tạo khối PL/pgSQL. Hai cơ chế có cùng từ khóa tiếng Anh nhưng **không cùng chức năng**.

## 7. DECLARE trong PL/pgSQL: biến, kiểu, DEFAULT, hằng

Khung khai báo:

~~~sql
DO $$
DECLARE
    v_count       INTEGER := 0;
    v_total       NUMERIC(12,2) DEFAULT 100000;
    v_customer    TEXT;
    v_tax_rate    CONSTANT NUMERIC := 0.08;
    v_label       TEXT NOT NULL := 'READY';
BEGIN
    v_count := v_count + 1;
    v_total := v_total * (1 + v_tax_rate);
    v_customer := 'C-001';

    RAISE NOTICE
        'count=%, total=%, customer=%, label=%',
        v_count, v_total, v_customer, v_label;
END;
$$ LANGUAGE plpgsql;
~~~

Ý nghĩa:

- **INTEGER, NUMERIC, TEXT** là kiểu dữ liệu của biến.
- **:= biểu thức** và **DEFAULT biểu thức** trong khai báo là cách khởi tạo.
- **v_customer TEXT** không khai báo giá trị ban đầu nên bắt đầu bằng **NULL**.
- **CONSTANT** ngăn việc gán lại hằng theo ngữ nghĩa PL/pgSQL.
- Biến **NOT NULL** cần được khởi tạo bằng giá trị phù hợp, vì giá trị mặc định NULL không hợp lệ với nó.

### 7.1. Phép gán trong phần thân khối

~~~sql
v_count := 5;
v_count := v_count + 1;
v_customer := UPPER('c-001');
~~~

Trong PL/pgSQL, **:=** là ký hiệu gán nên dùng để dễ phân biệt với dấu **=** trong so sánh SQL. PostgreSQL PL/pgSQL cũng hỗ trợ **=** làm toán tử gán trong ngữ cảnh phù hợp, nhưng cách viết **:=** giúp người đọc nhận ra thao tác gán tức thì.

**Không lẫn dấu gán của ngôn ngữ thủ tục với toán tử so sánh trong WHERE**:

~~~sql
IF v_count = 6 THEN
    RAISE NOTICE 'Dieu kien dung';
END IF;
~~~

Ở đây dấu **=** kiểm tra bằng nhau. Không dùng **:=** trong WHERE để so sánh cột.

### 7.2. Kiểu số dùng cho tiền

Với tiền, **NUMERIC(12,2)** thích hợp hơn FLOAT/DOUBLE khi cần tính toán thập phân chính xác trong các giới hạn kiểu. Khi viết:

~~~sql
v_net_amount := ROUND(v_subtotal * (1 - v_discount_pct / 100), 2);
~~~

điều quan trọng là **đặt quy tắc làm tròn và miền giá trị rõ ràng**. Dùng phép gán không có nghĩa mọi phép chia số sẽ tự đúng với yêu cầu làm tròn của nghiệp vụ.

### 7.3. NULL trong biến

~~~sql
DO $$
DECLARE
    v_value NUMERIC;
BEGIN
    RAISE NOTICE 'value is null? %', v_value IS NULL;

    v_value := COALESCE(v_value, 0) + 100;

    RAISE NOTICE 'value=%', v_value;
END;
$$;
~~~

Vì biến chưa khởi tạo là NULL, biểu thức **v_value + 100** trực tiếp cũng thành NULL. **COALESCE** là một cách chủ động lựa chọn 0 khi thiếu giá trị, nhưng chỉ dùng khi 0 có ý nghĩa đúng với nghiệp vụ.

## 8. Phạm vi biến: block trong và block ngoài

PL/pgSQL hỗ trợ **block lồng nhau**. Biến được khai báo trong block trong có phạm vi từ lúc vào block đến khi kết thúc block ấy.

~~~sql
DO $$
DECLARE
    v_step INTEGER := 1;
    v_message TEXT := 'outer';
BEGIN
    RAISE NOTICE
        'Before inner: step=%, message=%',
        v_step, v_message;

    DECLARE
        v_message TEXT := 'inner';
        v_local_only INTEGER := 99;
    BEGIN
        v_step := v_step + 1;

        RAISE NOTICE
            'Inside inner: step=%, message=%, local=%',
            v_step, v_message, v_local_only;
    END;

    RAISE NOTICE
        'After inner: step=%, message=%',
        v_step, v_message;
END;
$$;
~~~

Trong ví dụ:

- **v_step** nằm ở block ngoài nhưng được đọc/gán trong block trong, nên sau đó thành 2.
- **v_message** có cùng tên ở hai scope. Biến trong **che khuất (shadow)** biến ngoài khi ở block trong.
- **v_local_only** chỉ sống trong block trong; truy cập ở ngoài sẽ không hợp lệ.

### 8.1. Tránh shadowing không cần thiết

Đặt trùng tên giữa biến và cột hoặc giữa các block có thể khiến truy vấn khó đọc. Một quy ước thực tế:

~~~text
p_...  → tham số của hàm/thủ tục
v_...  → biến cục bộ
r_...  → record/row variable
c_...  → hằng cục bộ, nếu nhóm dự án chọn cách này
~~~

Đây là **quy ước tên**, không phải cú pháp bắt buộc của PostgreSQL.

### 8.2. Scope không đồng nghĩa transaction

Rời khỏi block trong làm biến cục bộ hết hiệu lực, **không tự ROLLBACK** những UPDATE thực hiện trong block. Transaction là cơ chế khác. Chỉ các khối xử lý ngoại lệ có hành vi subtransaction đặc thù mới có quy tắc rollback nội bộ khi bắt lỗi, như phần sau.

## 9. SELECT ... INTO biến trong PL/pgSQL

Một cách nạp dữ liệu bảng vào biến:

~~~sql
DO $$
DECLARE
    v_subtotal NUMERIC(12,2);
    v_status TEXT;
BEGIN
    SELECT
        i.subtotal_vnd,
        i.status
    INTO
        v_subtotal,
        v_status
    FROM lab_blocks_invoices AS i
    WHERE i.invoice_id = 1002;

    RAISE NOTICE 'subtotal=%, status=%', v_subtotal, v_status;
END;
$$;
~~~

**INTO v_subtotal, v_status** ở đây không tạo bảng mới. Nó gán các cột của một hàng truy vấn cho **các biến đã khai báo**.

### 9.1. SELECT INTO không STRICT

Trong PL/pgSQL, câu SELECT INTO không STRICT có những đặc điểm:

- Nếu tìm thấy hàng, gán kết quả của **một hàng** cho biến; với nhiều hàng, chỉ chọn một hàng (không có ORDER BY bảo đảm thì không được dựa vào hàng nào).
- Nếu không tìm thấy hàng, các biến đích được đặt thành **NULL**.
- **FOUND** phản ánh liệu câu lệnh SELECT INTO có lấy được hàng hay không.

Ví dụ:

~~~sql
DO $$
DECLARE
    v_status TEXT := 'BEFORE';
BEGIN
    SELECT status
    INTO v_status
    FROM lab_blocks_invoices
    WHERE invoice_id = 9999;

    IF NOT FOUND THEN
        RAISE NOTICE 'Khong tim thay invoice 9999';
    END IF;

    RAISE NOTICE 'status after SELECT INTO = %', v_status;
END;
$$;
~~~

Vì invoice 9999 không tồn tại, **v_status trở thành NULL**, không giữ chuỗi 'BEFORE'.

### 9.2. SELECT INTO STRICT

Khi logic yêu cầu đúng một hàng:

~~~sql
SELECT subtotal_vnd, status
INTO STRICT v_subtotal, v_status
FROM lab_blocks_invoices
WHERE invoice_id = v_invoice_id;
~~~

Với **STRICT**:

- **0 hàng** → lỗi **NO_DATA_FOUND** trong PL/pgSQL.
- **Nhiều hơn 1 hàng** → lỗi **TOO_MANY_ROWS**.
- **Đúng 1 hàng** → gán giá trị.

Nếu WHERE dựa trên **PRIMARY KEY(invoice_id)** hợp lệ, không thể có hai hàng cùng invoice_id trong bảng ấy. Nhưng truy vấn JOIN có thể nhân hàng, hoặc điều kiện tìm khác khóa có thể trả nhiều hàng; STRICT vẫn hữu ích để kiểm soát giả định.

### 9.3. Bắt lỗi STRICT có chủ đích

~~~sql
DO $$
DECLARE
    v_customer TEXT;
BEGIN
    BEGIN
        SELECT customer_code
        INTO STRICT v_customer
        FROM lab_blocks_invoices
        WHERE invoice_id = 9999;

        RAISE NOTICE 'customer=%', v_customer;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE NOTICE 'Invoice khong ton tai';
        WHEN TOO_MANY_ROWS THEN
            RAISE NOTICE 'Ket qua nhieu hon mot hang';
    END;
END;
$$;
~~~

Khối EXCEPTION cho phép xử lý hai tình huống theo chính sách. **Không nên bắt mọi exception rồi im lặng**, vì có thể bỏ qua lỗi kiểu dữ liệu, phân quyền hoặc dữ liệu hỏng mà ứng dụng cần biết.

## 10. Cảnh báo: SELECT INTO có nhiều nghĩa theo ngữ cảnh

Đây là một bẫy khi học nhiều hệ SQL:

| Ngữ cảnh | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **PostgreSQL PL/pgSQL** | SELECT amount INTO v_amount FROM ... | Gán một kết quả cho biến PL/pgSQL |
| **PostgreSQL SQL ngoài PL/pgSQL** | SELECT ... INTO new_table FROM ... | Cú pháp legacy tạo bảng kết quả; thường ưu tiên CREATE TABLE AS |
| **MySQL stored program** | SELECT amount INTO v_amount FROM ... | Gán vào biến cục bộ |
| **Oracle PL/SQL** | SELECT amount INTO v_amount FROM ... | Gán; yêu cầu chính xác một hàng |
| **SQL Server T-SQL** | SELECT amount INTO new_table FROM ... | Tạo bảng mới từ kết quả SELECT |
| **SQL Server gán biến** | SELECT @amount = amount FROM ... | Gán biến bằng cú pháp riêng |

Trong PostgreSQL khi tạo bảng từ SELECT, nên dùng dạng rõ nghĩa:

~~~sql
CREATE TEMP TABLE lab_subtotal_snapshot AS
SELECT invoice_id, subtotal_vnd
FROM lab_blocks_invoices;
~~~

Đây là **tạo bảng chứa kết quả**, hoàn toàn khác SELECT INTO v_subtotal trong PL/pgSQL.

**Không thể chỉ nhìn từ khóa SELECT INTO và kết luận ý nghĩa khi chưa biết phương ngữ và ngữ cảnh thực thi.**

## 11. SELECT INTO, PERFORM, FOUND và ROW_COUNT

### 11.1. SELECT INTO khi cần lấy giá trị

~~~sql
SELECT subtotal_vnd
INTO v_subtotal
FROM lab_blocks_invoices
WHERE invoice_id = v_invoice_id;
~~~

Lấy một giá trị để dùng trong biến.

### 11.2. PERFORM khi không cần giữ giá trị trả về

Trong PL/pgSQL, nếu muốn thực thi một SELECT hoặc hàm vì tác dụng phụ mà **không cần giữ kết quả**:

~~~sql
PERFORM pg_sleep(0.01);
~~~

Đây là minh họa cú pháp, không có ý nghĩa nghiệp vụ cần ngủ trong xử lý hóa đơn. **PERFORM** là cấu trúc PL/pgSQL; không phải một lệnh SQL độc lập có thể gửi từ mọi client.

Với một SELECT bình thường trả nhiều hàng nhưng không có INTO trong khối PL/pgSQL, PostgreSQL thường báo lỗi **query has no destination for result data**; nếu chỉ cần chạy và bỏ kết quả, dùng PERFORM.

### 11.3. FOUND

**FOUND** là biến BOOLEAN đặc biệt của PL/pgSQL phản ánh trạng thái một số thao tác vừa thực hiện. Sau SELECT INTO, nó cho biết có tìm thấy hàng hay không. Sau UPDATE/DELETE/INSERT kiểu phù hợp, có thể cho biết có hàng bị tác động.

~~~sql
DO $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT status INTO v_status
    FROM lab_blocks_invoices
    WHERE invoice_id = 1002;

    IF FOUND THEN
        RAISE NOTICE 'Invoice exists: %', v_status;
    ELSE
        RAISE NOTICE 'Invoice missing';
    END IF;
END;
$$;
~~~

**Lưu ý:** FOUND có thể thay đổi sau các câu lệnh tiếp theo. Nếu logic phụ thuộc kết quả của một lệnh, hãy đọc/lưu nó **ngay sau lệnh ấy**, không kiểm tra nhiều bước sau và mặc định nó còn giữ nghĩa cũ.

### 11.4. GET DIAGNOSTICS ... ROW_COUNT

Nếu cần số hàng thay đổi:

~~~sql
DO $$
DECLARE
    v_rows BIGINT;
BEGIN
    UPDATE lab_blocks_invoices
    SET status = status
    WHERE status = 'NEW';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'Rows affected=%', v_rows;
END;
$$;
~~~

Đây chỉ là minh họa đọc số hàng; **UPDATE status = status** vẫn là thao tác UPDATE và có thể có chi phí/trigger theo schema thực tế, dù giá trị trông không đổi. Không dùng kỹ thuật này để đếm hàng trong production; **SELECT COUNT(*)** phù hợp hơn nếu chỉ muốn đếm.

## 12. %TYPE, %ROWTYPE và RECORD trong PL/pgSQL

Khi có nhiều cột dữ liệu, khai báo lặp lại kiểu có thể dễ sai nếu schema đổi.

### 12.1. %TYPE

~~~sql
DO $$
DECLARE
    v_subtotal lab_blocks_invoices.subtotal_vnd%TYPE;
BEGIN
    SELECT subtotal_vnd
    INTO STRICT v_subtotal
    FROM lab_blocks_invoices
    WHERE invoice_id = 1002;

    RAISE NOTICE 'Subtotal=%', v_subtotal;
END;
$$;
~~~

**lab_blocks_invoices.subtotal_vnd%TYPE** lấy kiểu theo cột đã định nghĩa, giúp biến theo cùng kiểu dữ liệu của cột, thay vì gõ lại NUMERIC(12,2) bằng tay.

### 12.2. %ROWTYPE

~~~sql
DO $$
DECLARE
    r_invoice lab_blocks_invoices%ROWTYPE;
BEGIN
    SELECT *
    INTO STRICT r_invoice
    FROM lab_blocks_invoices
    WHERE invoice_id = 1002;

    RAISE NOTICE
        'invoice=%, subtotal=%, status=%',
        r_invoice.invoice_id,
        r_invoice.subtotal_vnd,
        r_invoice.status;
END;
$$;
~~~

**%ROWTYPE** khai báo biến record theo cấu trúc hàng của bảng hoặc composite type phù hợp. Truy cập từng trường bằng dấu chấm.

### 12.3. RECORD

~~~sql
DO $$
DECLARE
    r_result RECORD;
BEGIN
    SELECT
        invoice_id,
        subtotal_vnd * (1 - discount_pct / 100) AS computed_net
    INTO STRICT r_result
    FROM lab_blocks_invoices
    WHERE invoice_id = 1002;

    RAISE NOTICE
        'invoice=%, computed=%',
        r_result.invoice_id, r_result.computed_net;
END;
$$;
~~~

**RECORD** có cấu trúc tùy theo truy vấn đã gán giá trị vào nó. Khác với một %ROWTYPE cố định theo bảng, record có thể mô tả nhiều tập cột khác nhau ở những câu SELECT khác nhau, nên cần thận trọng khi truy cập trường chưa tồn tại.

**Không nên SELECT * chỉ vì có RECORD** trong một API/báo cáo có contract nghiêm ngặt; thay đổi schema có thể khiến ý nghĩa và số cột kết quả biến động.

## 13. IF, CASE và LOOP dùng biến như thế nào?

Ngôn ngữ thủ tục kết hợp biến với rẽ nhánh:

~~~sql
DO $$
DECLARE
    v_subtotal NUMERIC := 120000;
    v_tier TEXT;
BEGIN
    IF v_subtotal >= 200000 THEN
        v_tier := 'LARGE';
    ELSIF v_subtotal >= 100000 THEN
        v_tier := 'MEDIUM';
    ELSE
        v_tier := 'SMALL';
    END IF;

    RAISE NOTICE 'Tier=%', v_tier;
END;
$$;
~~~

Ở PostgreSQL PL/pgSQL dùng **ELSIF**, không phải **ELSE IF** theo ngữ nghĩa cú pháp một số ngôn ngữ khác.

Một vòng lặp đơn giản:

~~~sql
DO $$
DECLARE
    v_n INTEGER;
    v_sum INTEGER := 0;
BEGIN
    FOR v_n IN 1..5 LOOP
        v_sum := v_sum + v_n;
    END LOOP;

    RAISE NOTICE 'Sum=%', v_sum;
END;
$$;
~~~

Kết quả v_sum = **15**. Trong trường hợp cộng số trong bảng hàng triệu dòng, **SUM(column)** theo SQL set-based thường tốt hơn vòng lặp qua từng hàng; chỉ dùng LOOP khi công việc thực sự cần quy trình theo bước.

### 13.1. CASE biểu thức và IF thủ tục

Trong câu SELECT, CASE trả một **giá trị biểu thức**:

~~~sql
SELECT
    invoice_id,
    CASE
        WHEN subtotal_vnd >= 100000 THEN 'HIGH'
        ELSE 'LOW'
    END AS amount_group
FROM lab_blocks_invoices;
~~~

Trong PL/pgSQL, **IF...THEN...END IF** điều khiển **những câu lệnh được thực thi**. Hai công cụ giải quyết nhu cầu khác nhau, dù cả hai đều biểu diễn rẽ nhánh.

## 14. Tham số của function và procedure PostgreSQL

Biến cục bộ có phạm vi trong block, còn **tham số** là giao diện của hàm/thủ tục với người gọi.

### 14.1. Hàm tính tiền thuần túy

~~~sql
-- Tạo function trong schema hiện tại, không phải bảng TEMP.
-- Dùng môi trường học riêng và DROP FUNCTION sau khi thực hành.
CREATE OR REPLACE FUNCTION lab_net_amount(
    p_subtotal NUMERIC,
    p_discount_pct NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_net NUMERIC;
BEGIN
    IF p_subtotal IS NULL OR p_discount_pct IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_subtotal < 0
       OR p_discount_pct < 0
       OR p_discount_pct > 100 THEN
        RAISE EXCEPTION 'Gia tri khong hop le';
    END IF;

    v_net :=
        ROUND(p_subtotal * (1 - p_discount_pct / 100), 2);

    RETURN v_net;
END;
$$;

SELECT lab_net_amount(120000, 10) AS net_vnd;
~~~

Kết quả **108000.00**. Hàm dùng **p_** cho tham số, **v_** cho biến. **RETURN** trả một giá trị tới người gọi.

**IMMUTABLE** phù hợp với ví dụ thuần tính toán cùng input luôn trả cùng output; không gắn nhãn IMMUTABLE cho hàm đọc bảng biến động, lấy thời gian hiện tại hoặc có side effect. Hàm đang tạo là đối tượng **permanent trong schema hiện tại**, không tự biến mất theo các bảng TEMP.

Dọn sau bài nếu muốn:

~~~sql
DROP FUNCTION IF EXISTS lab_net_amount(NUMERIC, NUMERIC);
~~~

### 14.2. Procedure và CALL

PostgreSQL hỗ trợ **CREATE PROCEDURE** và **CALL**. Một procedure thực hiện thao tác nghiệp vụ, có thể nhận tham số IN/OUT/INOUT theo quy tắc phiên bản.

~~~sql
-- Minh họa cấu trúc trên PostgreSQL:
CREATE OR REPLACE PROCEDURE lab_print_invoice_id(
    IN p_invoice_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_label TEXT := 'Invoice';
BEGIN
    RAISE NOTICE '% %', v_label, p_invoice_id;
END;
$$;

CALL lab_print_invoice_id(1001);
~~~

Function được gọi qua SELECT hoặc nơi dùng biểu thức phù hợp; procedure được gọi qua **CALL**. Chúng có khác biệt về trả kết quả và quản lý transaction, không nên dùng hai tên như từ đồng nghĩa tuyệt đối.

### 14.3. BEGIN...END không bắt đầu transaction mới

Trong function/procedure:

~~~sql
BEGIN
    -- Các câu lệnh PL/pgSQL.
END;
~~~

chỉ mở và đóng **khối PL/pgSQL**. Còn:

~~~sql
BEGIN;
UPDATE ...;
COMMIT;
~~~

ở cấp SQL là transaction. Trong PostgreSQL, transaction control bên trong procedure/DO có những **hạn chế theo ngữ cảnh CALL/DO, stack và explicit transaction**. Không giả định mỗi function/procedure đều được tự COMMIT hoặc ROLLBACK tùy ý.

## 15. Xử lý ngoại lệ trong khối PostgreSQL

Một block PL/pgSQL có thể chứa **EXCEPTION**:

~~~sql
DO $$
DECLARE
    v_inserted INTEGER := 0;
BEGIN
    BEGIN
        INSERT INTO lab_blocks_invoices
            (invoice_id, customer_code, subtotal_vnd,
             discount_pct, status)
        VALUES
            (1001, 'C-X', 1000, 0, 'NEW');

        v_inserted := 1;
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Invoice 1001 da ton tai';
    END;

    RAISE NOTICE 'Inserted flag=%', v_inserted;
END;
$$;
~~~

Vì invoice_id = 1001 đã tồn tại, INSERT sẽ vi phạm PRIMARY KEY. Khối trong bắt lỗi và thông báo.

Một khối PL/pgSQL có EXCEPTION dùng cơ chế **subtransaction**: khi lỗi được bắt, các thay đổi SQL trong phần block bị lỗi có thể được rollback về đầu block ấy, còn biến PL/pgSQL có quy tắc giữ giá trị riêng. **Không đồng nhất rollback của dữ liệu SQL với việc “hoàn tác mọi phép gán biến”**.

### 15.1. Không bắt unique_violation quá rộng

Một INSERT có thể vi phạm nhiều UNIQUE constraint khác nhau. Nếu nghiệp vụ chỉ cho bỏ qua lỗi “invoice_id đã tồn tại”, catch mọi unique_violation mà không phân biệt ràng buộc có thể che một lỗi quan trọng khác.

Nếu chỉ muốn chèn nếu chưa có theo khóa duy nhất, có thể dùng **INSERT ... ON CONFLICT** theo arbiter phù hợp thay cho exception flow trong nhiều trường hợp.

### 15.2. Không dùng exception để thay điều kiện dữ liệu rõ ràng

Nếu cần biết status của đơn:

~~~sql
SELECT status INTO STRICT v_status
FROM lab_blocks_invoices
WHERE invoice_id = v_invoice_id;
~~~

sau đó IF kiểm tra **status = 'NEW'** là một chính sách dễ hiểu. Đừng chủ động tạo lỗi CHECK chỉ để suy ra đơn đã ở trạng thái nào.

## 16. MySQL: DECLARE và BEGIN...END trong stored procedure

MySQL stored procedures có cú pháp khai báo biến **khác PostgreSQL**. Một biến cục bộ phải được khai báo bằng **DECLARE ... DEFAULT ...** bên trong khối BEGIN...END.

### 16.1. Tạo procedure mẫu

Ví dụ độc lập sau dành cho **MySQL 8.0/InnoDB**, giả sử có bảng invoices với các cột invoice_id, subtotal_vnd, discount_pct, net_amount_vnd và status tương ứng.

~~~sql
-- Chạy trong mysql CLI hoặc client hiểu DELIMITER.
DELIMITER //

CREATE PROCEDURE lab_mysql_approve_invoice(
    IN p_invoice_id INT
)
BEGIN
    DECLARE v_subtotal DECIMAL(12,2) DEFAULT NULL;
    DECLARE v_discount DECIMAL(5,2) DEFAULT NULL;
    DECLARE v_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_net DECIMAL(12,2) DEFAULT NULL;

    SELECT
        subtotal_vnd,
        discount_pct,
        status
    INTO
        v_subtotal,
        v_discount,
        v_status
    FROM invoices
    WHERE invoice_id = p_invoice_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invoice not found';
    END IF;

    IF v_status <> 'NEW' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invoice is not NEW';
    END IF;

    SET v_net = ROUND(v_subtotal * (1 - v_discount / 100), 2);

    UPDATE invoices
    SET net_amount_vnd = v_net,
        status = 'APPROVED'
    WHERE invoice_id = p_invoice_id
      AND status = 'NEW';
END//

DELIMITER ;
~~~

Gọi:

~~~sql
CALL lab_mysql_approve_invoice(1001);
~~~

**DELIMITER //** và **DELIMITER ;** là lệnh của **mysql CLI hoặc công cụ client hỗ trợ**, nhằm báo cho client biết dấu kết thúc toàn bộ CREATE PROCEDURE. Chúng **không phải SQL gửi nguyên văn tới server** qua mọi JDBC driver.

### 16.2. MySQL SET

Gán cục bộ:

~~~sql
SET v_net = ROUND(v_subtotal * 0.9, 2);
~~~

Trong một số ngữ cảnh của MySQL, biến có thể tham gia biểu thức theo cú pháp tương ứng; nhưng **SET var = expression** là cách gán rõ ràng trong stored program. Không port trực tiếp **v_net := ...** của PL/pgSQL và giả định chúng được hỗ trợ giống nhau trong mọi ngữ cảnh.

### 16.3. DECLARE phải nằm đầu block

MySQL yêu cầu các DECLARE cục bộ xuất hiện **trước những câu lệnh thực thi** trong BEGIN...END. Thông thường thứ tự là:

1. Biến và condition.
2. Cursor.
3. Handler.
4. Các câu lệnh thực thi như SET, SELECT, IF, UPDATE.

Ví dụ không hợp lệ:

~~~sql
-- Sai ý tưởng trong MySQL:
BEGIN
    SET @x = 1;
    DECLARE v_total INT DEFAULT 0;
END;
~~~

Không thể chèn DECLARE biến sau khi đã bắt đầu thực thi SET trong cùng block MySQL. Nếu cần biến mới ở giai đoạn sau, dùng một **block con** có phần DECLARE riêng ở đầu.

## 17. MySQL: biến cục bộ khác @user_variable

Đây là khác biệt rất quan trọng:

| Đặc tính | Biến cục bộ MySQL | User-defined variable |
| --- | --- | --- |
| Ví dụ tên | v_total | @total |
| Khai báo | DECLARE v_total DECIMAL(...) | Không khai báo kiểu bằng DECLARE như local |
| Phạm vi | Block stored program | Session/connection |
| Vòng đời | Kết thúc khi ra khỏi block | Tồn tại tới khi session kết thúc hoặc bị đổi giá trị |
| Kiểu | Kiểu được khai báo | Kiểu/giá trị theo cơ chế user variable |
| Cách gán rõ ràng | SET v_total = ... | SET @total = ... |

Ví dụ ở client MySQL:

~~~sql
SET @session_count = 0;
SET @session_count = @session_count + 1;
SELECT @session_count;
~~~

**@session_count** gắn với kết nối. Nếu ứng dụng dùng connection pool và không kiểm soát state, một request có thể kế thừa biến phiên do request trước để lại trên cùng connection.

**Không dùng @user_variable làm nơi lưu state nghiệp vụ bền vững hoặc thay thế biến cục bộ trong procedure chỉ vì không muốn DECLARE.**

### 17.1. Phép gán := với user variable

MySQL có cú pháp gán **:=** cho user variable trong một số biểu thức, nhưng dùng **SET @x = ...** thường dễ đọc. Việc đọc và gán cùng một user variable trong một câu SELECT phức tạp có thể có thứ tự đánh giá không được bảo đảm như người viết tưởng; tránh kiểu lập trình dựa vào thứ tự đó.

## 18. MySQL: SELECT ... INTO và số hàng kết quả

Trong stored program MySQL:

~~~sql
SELECT subtotal_vnd
INTO v_subtotal
FROM invoices
WHERE invoice_id = p_invoice_id;
~~~

Các tình huống:

- **Một hàng:** gán thành công.
- **Không có hàng:** phát sinh điều kiện NOT FOUND/cảnh báo tương ứng; các biến đích có thể **giữ giá trị trước đó**, khác hành vi PL/pgSQL SELECT INTO non-STRICT.
- **Nhiều hàng:** lỗi *Result consisted of more than one row* thường có mã **1172**.

Vì vậy, không port từ PostgreSQL sang MySQL với suy luận:

~~~text
SELECT INTO không có hàng → biến chắc chắn bị gán NULL
~~~

Nếu muốn phát hiện “không có hàng”, khởi tạo biến rõ ràng, dùng điều kiện khóa duy nhất, handler hoặc phép kiểm tra phù hợp. Nhưng nếu cột được phép NULL, **kiểm tra v_subtotal IS NULL một mình** không đủ phân biệt “không tìm thấy hàng” với “tìm thấy hàng mà giá trị là NULL”.

### 18.1. NOT FOUND handler và cursor

Trong procedure dùng cursor, MySQL thường khai báo:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = TRUE;
~~~

Handler **NOT FOUND** cũng có thể liên quan đến các tình huống SELECT ... INTO không có hàng, không chỉ cursor FETCH. Vì vậy, khi dùng cả cursor và SELECT INTO trong một stored program, phải thiết kế phạm vi handler cẩn thận để tránh đặt v_done sai vì một SELECT ngoài ý muốn.

### 18.2. ROW_COUNT()

Sau UPDATE hoặc INSERT trong MySQL, có thể dùng:

~~~sql
SET v_rows = ROW_COUNT();
~~~

trong stored program đã DECLARE v_rows phù hợp. Đọc ngay sau câu DML cần đo; những câu khác có thể làm giá trị rows affected được báo cáo thay đổi. Phải hiểu cách MySQL đếm affected/matched rows với UPDATE và cấu hình client tương ứng.

## 19. SQL Server T-SQL: biến có tiền tố @

Trong SQL Server, biến cục bộ thường bắt đầu bằng **@**:

~~~sql
DECLARE @invoice_id INT = 1001;
DECLARE @subtotal DECIMAL(12,2);
DECLARE @discount DECIMAL(5,2) = 10;
DECLARE @net DECIMAL(12,2);

SET @subtotal = 120000;
SET @net = ROUND(@subtotal * (1 - @discount / 100.0), 2);

SELECT
    @invoice_id AS invoice_id,
    @subtotal AS subtotal_vnd,
    @net AS net_vnd;
~~~

Kết quả net = **108000.00**. Không cần một BEGIN...END để khai báo @invoice_id ở một batch T-SQL. Biến T-SQL tồn tại trong phạm vi **batch, stored procedure hoặc một đơn vị thực thi phù hợp**, không theo cơ chế DECLARE chỉ nằm trong BEGIN...END của PL/pgSQL.

### 19.1. BEGIN...END T-SQL không tạo scope biến lồng kiểu PostgreSQL

~~~sql
DECLARE @counter INT = 0;

BEGIN
    SET @counter = @counter + 1;
END;

SELECT @counter AS result;
~~~

Kết quả là **1**; biến khai báo trước block vẫn dùng được sau END trong cùng batch.

Thêm một **BEGIN...END** không tự tạo phạm vi biến mới cho việc tái khai báo cùng tên như PL/pgSQL. Tránh nghĩ có thể DECLARE @counter lần nữa trong block trong chỉ để shadow biến ngoài.

### 19.2. GO không phải lệnh SQL của server

Trong SSMS/sqlcmd, **GO** thường phân tách **batch phía client**:

~~~sql
DECLARE @x INT = 10;
SELECT @x AS x;
GO

-- Batch mới: @x của batch trước không còn khả dụng.
-- SELECT @x;  -- sẽ lỗi vì chưa khai báo.
~~~

**GO là dấu phân tách của công cụ**, không phải câu SQL chuẩn gửi qua JDBC. Nó cũng không tương đương COMMIT transaction. Không cho GO vào giữa phần DECLARE và câu lệnh dùng biến nếu muốn chúng ở cùng batch.

## 20. SQL Server: SET @v và SELECT @v = col khác nhau

Hai cách gán:

~~~sql
SET @subtotal = 120000;
SELECT @subtotal = subtotal_vnd
FROM dbo.invoices
WHERE invoice_id = @invoice_id;
~~~

Cách thứ hai đọc từ bảng. Sự khác biệt rõ khi SELECT không trả đúng một hàng:

| Tình huống | SET @v = (SELECT ...) | SELECT @v = col FROM ... |
| --- | --- | --- |
| Đúng 1 hàng | Gán giá trị | Gán giá trị |
| Không hàng | Scalar subquery trả NULL, biến được gán NULL | Biến **giữ giá trị trước đó** |
| Nhiều hàng | Scalar subquery có thể báo lỗi nhiều hơn một giá trị | Biến có thể bị gán qua các hàng; giá trị cuối không nên dựa vào nếu thiếu quy tắc chắc chắn |

Ví dụ:

~~~sql
DECLARE @a INT = 99;
DECLARE @b INT = 99;

SELECT @a = value_col
FROM dbo.some_table
WHERE 1 = 0;

SET @b = (
    SELECT value_col
    FROM dbo.some_table
    WHERE 1 = 0
);

SELECT @a AS a, @b AS b;
~~~

Với bảng giả định dbo.some_table:

~~~text
@a = 99
@b = NULL
~~~

**Không giả định SELECT @v = col khi zero rows sẽ tự đặt NULL như SET với scalar subquery.**

### 20.1. Gán nhiều biến

~~~sql
DECLARE @subtotal DECIMAL(12,2);
DECLARE @discount DECIMAL(5,2);

SELECT
    @subtotal = subtotal_vnd,
    @discount = discount_pct
FROM dbo.invoices
WHERE invoice_id = 1001;
~~~

Khi dùng cách này, cần bảo đảm khóa WHERE chỉ trả đúng một hàng, hoặc chủ động kiểm soát kết quả. Nếu SELECT trả nhiều hàng, đừng xem giá trị cuối của biến là một chiến lược chọn bản ghi đáng tin cậy.

### 20.2. SELECT ... INTO trong SQL Server là tạo bảng

~~~sql
-- Tạo bảng mới từ kết quả, KHÔNG gán biến.
SELECT invoice_id, subtotal_vnd
INTO #invoice_snapshot
FROM dbo.invoices;
~~~

Ở đây **#invoice_snapshot** là bảng tạm SQL Server. Đó là ý nghĩa khác với **SELECT ... INTO v_variable** trong MySQL/PostgreSQL PL/pgSQL/Oracle PL/SQL.

## 21. SQL Server: @@ROWCOUNT, OUTPUT parameter, TRY...CATCH

Sau DML, có thể lấy số hàng bằng **@@ROWCOUNT**:

~~~sql
DECLARE @rows INT;

UPDATE dbo.invoices
SET status = 'APPROVED'
WHERE invoice_id = 1001
  AND status = 'NEW';

SET @rows = @@ROWCOUNT;

IF @rows <> 1
    THROW 50001, 'Expected exactly one invoice update', 1;
~~~

Đây là minh họa trên bảng **dbo.invoices giả định**. **@@ROWCOUNT** phản ánh số hàng của câu lệnh trước theo quy tắc T-SQL, nên cần ghi lại ngay; các câu SET/PRINT/SELECT khác có thể thay đổi giá trị này.

### 21.1. OUTPUT parameter

SQL Server có thể dùng **OUTPUT** để đưa kết quả từ stored procedure ra ngoài:

~~~sql
-- SQL Server, procedure thuần tính toán.
CREATE OR ALTER PROCEDURE dbo.lab_calc_net
    @subtotal DECIMAL(12,2),
    @discount_pct DECIMAL(5,2),
    @net DECIMAL(12,2) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @net = ROUND(
        @subtotal * (1 - @discount_pct / 100.0),
        2
    );
END;
~~~

Gọi trong một batch riêng:

~~~sql
DECLARE @result DECIMAL(12,2);

EXEC dbo.lab_calc_net
    @subtotal = 120000,
    @discount_pct = 10,
    @net = @result OUTPUT;

SELECT @result AS net_vnd;
~~~

Lưu ý trong SQL Server, cú pháp khai báo **OUTPUT** trong procedure và khi EXEC rất khác **RETURNS NUMERIC** của hàm PostgreSQL. Chúng là các giao diện khác nhau.

### 21.2. TRY...CATCH và giao dịch

~~~sql
BEGIN TRY
    BEGIN TRANSACTION;

    -- Các DML bắt buộc và kiểm tra số hàng.

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
~~~

Ở SQL Server, **BEGIN...END** nhóm câu lệnh, **BEGIN TRANSACTION** bắt đầu transaction. Một exception có thể khiến transaction ở trạng thái không COMMIT được; cần **XACT_STATE()** chứ không chỉ dựa vào việc BEGIN...END vẫn tồn tại.

## 22. Oracle PL/SQL: DECLARE, BEGIN, EXCEPTION, END

Trong Oracle, khối PL/SQL vô danh có cấu trúc:

~~~sql
DECLARE
    v_subtotal NUMBER(12,2) := 120000;
    v_discount NUMBER(5,2) := 10;
    v_net NUMBER(12,2);
BEGIN
    v_net := ROUND(
        v_subtotal * (1 - v_discount / 100),
        2
    );

    DBMS_OUTPUT.PUT_LINE('Net amount = ' || v_net);
END;
/
~~~

Trong công cụ như SQL*Plus/SQLcl, dấu **/** trên dòng riêng thường là lệnh client yêu cầu thực thi khối PL/SQL đã nhập; nó **không phải toán tử chia** trong nội dung block và không nhất thiết được gửi như vậy qua mọi driver.

Khác PostgreSQL DO:

- Khối vô danh Oracle thường bắt đầu bằng **DECLARE** nếu có khai báo, sau đó **BEGIN**.
- Phép gán dùng **:=**.
- Thông báo dùng **DBMS_OUTPUT.PUT_LINE**, và client cần bật/đọc DBMS_OUTPUT tùy công cụ.
- Có thể có phần **EXCEPTION** giữa BEGIN và END để xử lý lỗi.

### 22.1. Oracle SELECT ... INTO yêu cầu đúng một hàng

~~~sql
DECLARE
    v_subtotal NUMBER(12,2);
BEGIN
    SELECT subtotal_vnd
    INTO v_subtotal
    FROM invoices
    WHERE invoice_id = 1001;

    DBMS_OUTPUT.PUT_LINE(v_subtotal);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Invoice not found');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one invoice');
END;
/
~~~

Đoạn này cần bảng invoices trên Oracle. Với SELECT INTO PL/SQL:

- **Không hàng** → NO_DATA_FOUND.
- **Nhiều hàng** → TOO_MANY_ROWS.
- **Một hàng** → gán biến.

Đây là quy tắc khác với **PostgreSQL SELECT INTO non-STRICT**.

### 22.2. Khai báo bằng %TYPE và %ROWTYPE

~~~sql
DECLARE
    v_subtotal invoices.subtotal_vnd%TYPE;
    r_invoice invoices%ROWTYPE;
BEGIN
    SELECT *
    INTO r_invoice
    FROM invoices
    WHERE invoice_id = 1001;

    v_subtotal := r_invoice.subtotal_vnd;
    DBMS_OUTPUT.PUT_LINE(v_subtotal);
END;
/
~~~

Oracle PL/SQL cũng có **%TYPE, %ROWTYPE** nhưng định nghĩa về kiểu, scope và cách xử lý RECORD là theo PL/SQL của Oracle, không phải một bản sao máy móc của PostgreSQL.

### 22.3. SQL%ROWCOUNT

Sau DML trong Oracle PL/SQL:

~~~sql
BEGIN
    UPDATE invoices
    SET status = 'APPROVED'
    WHERE invoice_id = 1001
      AND status = 'NEW';

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected = ' || SQL%ROWCOUNT
    );
END;
/
~~~

**SQL%ROWCOUNT** là thuộc tính cursor ngầm của PL/SQL, được đọc sau câu SQL phù hợp. Không nhầm với **@@ROWCOUNT** của SQL Server hay **GET DIAGNOSTICS ... ROW_COUNT** của PostgreSQL.

### 22.4. Phạm vi và phép gán

PL/SQL cho phép block lồng và khai báo cục bộ, với quy tắc scope của PL/SQL. Biến bên trong có thể che tên bên ngoài. Dùng tên rõ ràng, tránh trùng cột.

Oracle cũng có tham số **IN, OUT, IN OUT** trong procedure/function; cách dùng khác ký hiệu **@var** của SQL Server hoặc biến @session MySQL.

## 23. SQLite: không có khối thủ tục tự do như PL/pgSQL

SQLite là một hệ quản trị nhúng mạnh về SQL, nhưng **SQL lõi của SQLite không cung cấp khối DECLARE/BEGIN/END và biến cục bộ procedural tương đương PostgreSQL, MySQL, SQL Server hay Oracle** để chạy tùy ý bên ngoài ứng dụng.

Không thể chỉ port:

~~~sql
-- Đây KHÔNG phải cú pháp SQLite SQL thường dùng:
DECLARE v_total NUMERIC;
SET v_total = 100;
~~~

### 23.1. Tham số do ứng dụng bind

SQLite hỗ trợ placeholder trong prepared statement:

~~~sql
SELECT
    invoice_id,
    ROUND(subtotal_vnd * (1 - ? / 100.0), 2) AS net_amount
FROM invoices
WHERE invoice_id = ?;
~~~

Ứng dụng bind hai giá trị, ví dụ **10** và **1001**, thông qua API SQLite/driver. Có các dạng tham số được hỗ trợ như **?**, **?NNN**, **:name**, **@name**, **$name** trong ngữ cảnh SQLite; chúng là **bind parameters**, không phải khai báo biến cục bộ của một procedure.

### 23.2. CTE như tên của kết quả trung gian trong một statement

~~~sql
WITH params(invoice_id, discount_pct) AS (
    VALUES (1001, 10.0)
)
SELECT
    i.invoice_id,
    i.subtotal_vnd,
    p.discount_pct,
    ROUND(
        i.subtotal_vnd * (1 - p.discount_pct / 100.0),
        2
    ) AS net_amount_vnd
FROM invoices AS i
JOIN params AS p
    ON p.invoice_id = i.invoice_id;
~~~

Trong SQLite, **params** ở đây là một **CTE**, không phải biến session hay bảng permanent. Nó chỉ tồn tại trong phạm vi của câu SELECT.

### 23.3. Trigger BEGIN...END không phải khối biến tổng quát

SQLite hỗ trợ body của trigger:

~~~sql
-- Ví dụ SQLite, bảng invoices giả định tồn tại.
CREATE TRIGGER prevent_negative_subtotal
BEFORE UPDATE OF subtotal_vnd ON invoices
FOR EACH ROW
WHEN NEW.subtotal_vnd < 0
BEGIN
    SELECT RAISE(ABORT, 'subtotal must be non-negative');
END;
~~~

**BEGIN...END trong trigger SQLite** nhóm các câu SQL của trigger; không biến SQLite thành một PL/pgSQL interpreter có DECLARE biến cục bộ chung. SQLite dùng **NEW.column/OLD.column** theo ngữ cảnh trigger chứ không dùng biến procedural v_ tùy ý.

### 23.4. Vì sao không nên tự giả lập mọi procedure bằng trigger?

Trigger chạy khi một sự kiện INSERT/UPDATE/DELETE tương ứng xảy ra. Nếu nhiệm vụ là tính toán theo yêu cầu người dùng hoặc điều phối quy trình dài với nhiều quyết định, có thể tốt hơn để:

- Ứng dụng quản lý transaction và biến ở ngôn ngữ host.
- SQL dùng set-based UPDATE, CASE, CTE hoặc RETURNING.
- Trigger chỉ bảo vệ hoặc thực hiện những quy tắc gắn thật sự với sự kiện dữ liệu.

Đừng lạm dụng trigger chỉ để có một khối BEGIN...END tương tự những hệ quản trị khác.

## 24. Một bài toán, năm cách tiếp cận

Mục tiêu thuần tính toán:

~~~text
subtotal = 120000
discount = 10%
net = round(subtotal * (1 - discount/100), 2)
Kết quả = 108000
~~~

### PostgreSQL PL/pgSQL

~~~sql
DO $$
DECLARE
    v_subtotal NUMERIC := 120000;
    v_discount NUMERIC := 10;
    v_net NUMERIC;
BEGIN
    v_net := ROUND(v_subtotal * (1 - v_discount / 100), 2);
    RAISE NOTICE 'net=%', v_net;
END;
$$;
~~~

### MySQL stored procedure

~~~sql
-- Chỉ phần thân BEGIN...END của procedure MySQL.
BEGIN
    DECLARE v_subtotal DECIMAL(12,2) DEFAULT 120000;
    DECLARE v_discount DECIMAL(5,2) DEFAULT 10;
    DECLARE v_net DECIMAL(12,2);

    SET v_net = ROUND(
        v_subtotal * (1 - v_discount / 100),
        2
    );
    SELECT v_net AS net_amount;
END;
~~~

**Khối MySQL trên là thân routine**, không phải khối standalone có thể gửi tùy ý như DO trên PostgreSQL. Cần đặt trong CREATE PROCEDURE/FUNCTION hoặc ngữ cảnh stored program được hỗ trợ.

### SQL Server T-SQL

~~~sql
DECLARE @subtotal DECIMAL(12,2) = 120000;
DECLARE @discount DECIMAL(5,2) = 10;
DECLARE @net DECIMAL(12,2);

SET @net = ROUND(
    @subtotal * (1 - @discount / 100.0),
    2
);

SELECT @net AS net_amount;
~~~

### Oracle PL/SQL

~~~sql
DECLARE
    v_subtotal NUMBER(12,2) := 120000;
    v_discount NUMBER(5,2) := 10;
    v_net NUMBER(12,2);
BEGIN
    v_net := ROUND(
        v_subtotal * (1 - v_discount / 100),
        2
    );
    DBMS_OUTPUT.PUT_LINE(v_net);
END;
/
~~~

### SQLite: câu SELECT không cần biến thủ tục

~~~sql
SELECT ROUND(120000 * (1 - 10.0 / 100), 2) AS net_amount;
~~~

Đây là ví dụ cho thấy có thể giải quyết một phép tính không cần procedural block. SQLite phù hợp với việc bind tham số từ ứng dụng khi giá trị không phải hằng đã biết.

## 25. Bẫy tên biến trùng tên cột

Trong thủ tục:

~~~sql
DECLARE
    status TEXT;
~~~

và bảng cũng có cột status, một câu:

~~~sql
SELECT status INTO status
FROM invoices
WHERE invoice_id = invoice_id;
~~~

có thể **mơ hồ** hoặc thực hiện so sánh sai ý định tùy phương ngữ/cấu hình giải quyết tên. Đặc biệt, điều kiện **invoice_id = invoice_id** có thể trở thành so sánh một cột với chính nó, làm mất bộ lọc khóa.

### 25.1. Quy tắc đặt tên và qualify cột

Đối với PostgreSQL:

~~~sql
SELECT i.status
INTO v_status
FROM lab_blocks_invoices AS i
WHERE i.invoice_id = v_invoice_id;
~~~

Với function:

~~~text
p_invoice_id  → tham số vào
v_status      → biến cục bộ
i.status      → cột bảng có alias i
~~~

Đây là cách diễn đạt rõ mỗi identifier đến từ đâu.

### 25.2. Không phụ thuộc vào cấu hình ưu tiên variable/column

PL/pgSQL có cơ chế cấu hình xử lý trường hợp tên biến trùng cột; những hệ khác có quy tắc ưu tiên tên riêng. Không chọn một câu SQL mơ hồ rồi hy vọng mọi database hiểu giống nhau. **Đặt tên phân biệt và qualify cột** là cách bền vững khi port code.

## 26. NULL, DEFAULT và trạng thái biến

Ba trường hợp dễ bị gộp nhầm:

~~~text
Biến chưa được gán          → thường bắt đầu NULL
Biến được gán NULL          → giá trị hiện tại là NULL
Biến được gán DEFAULT 0     → giá trị hiện tại là 0
~~~

**NULL không phải 0, chuỗi rỗng hoặc FALSE.**

Ví dụ PL/pgSQL:

~~~sql
DO $$
DECLARE
    v_price NUMERIC;
    v_qty INTEGER := 2;
    v_total NUMERIC;
BEGIN
    v_total := v_price * v_qty;

    RAISE NOTICE 'v_total is NULL? %', v_total IS NULL;

    v_price := 10000;
    v_total := v_price * v_qty;

    RAISE NOTICE 'v_total=%', v_total;
END;
$$;
~~~

Kết quả ban đầu NULL, sau đó là 20.000.

### 26.1. Không tự chọn DEFAULT có thể che lỗi đầu vào

Nếu giá từ bảng bị thiếu do dữ liệu chưa hợp lệ, tự đặt:

~~~sql
v_price := COALESCE(v_price, 0);
~~~

có thể làm một hóa đơn thiếu giá thành hóa đơn giá 0. Với dữ liệu tài chính, nên phân biệt:

- **Giá trị thực sự bằng 0**.
- **Giá trị không biết/thiếu**.
- **Không tìm thấy hàng**.
- **Tìm thấy nhiều hàng**.

Các trường hợp này có thể cần những nhánh lỗi khác nhau.

### 26.2. Chuyển kiểu khi gán

Các hệ quản trị có thể thực hiện chuyển kiểu ngầm hoặc yêu cầu CAST rõ ràng. Ví dụ:

~~~sql
v_discount_pct := '10';
~~~

có thể được chấp nhận hoặc phụ thuộc quy tắc ép kiểu ở ngữ cảnh cụ thể, nhưng không nên dựa vào phép chuyển chuỗi tùy tiện từ dữ liệu nguồn. Khi viết procedure nhận đầu vào từ file/API, hãy **validate định dạng và miền giá trị**, khai báo kiểu tham số thích hợp và CAST có kiểm soát.

## 27. Biến không thay thế transaction và khóa đồng thời

Giả sử hai tiến trình đều:

~~~text
SELECT balance INTO v_balance
v_balance := v_balance - amount
UPDATE accounts SET balance = v_balance
~~~

Nếu hai transaction đọc cùng số dư rồi cập nhật dựa trên giá trị cũ mà không có chính sách đồng thời phù hợp, có thể xảy ra **lost update** hoặc sai số dư. Việc dùng biến chỉ lưu một giá trị trong khối, **không tự khóa hàng**.

### 27.1. Ưu tiên UPDATE nguyên tử khi phù hợp

Một số bài toán có thể diễn đạt trực tiếp bằng DML:

~~~sql
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 1
  AND balance >= 100000;
~~~

Sau đó phải kiểm tra **số hàng UPDATE** bằng cơ chế phù hợp với phương ngữ. Nếu 0 hàng, có thể không tồn tại tài khoản hoặc số dư không đủ. Cần quyết định cách phân biệt nếu nghiệp vụ yêu cầu.

Đây thường là hướng dễ kiểm soát hơn mô hình SELECT số dư vào biến rồi UPDATE một số dư được tính từ snapshot cũ.

### 27.2. SELECT ... FOR UPDATE

Khi cần đọc nhiều cột, tính toán và quyết định nhiều bước, có thể dùng khóa hàng:

~~~sql
SELECT subtotal_vnd, discount_pct, status
INTO STRICT v_subtotal, v_discount_pct, v_status
FROM lab_blocks_invoices
WHERE invoice_id = v_invoice_id
FOR UPDATE;
~~~

Đó là cú pháp PostgreSQL bên trong PL/pgSQL. Trong SQL Server, MySQL, Oracle và SQLite, cách khóa/cô lập tương ứng có cú pháp và quy tắc khác. Khóa là cơ chế của transaction, không phải tính chất tự nhiên của phép gán.

### 27.3. Bước bắt buộc thất bại thì phải xử lý giao dịch

Nếu procedure cập nhật bảng đơn và chèn audit nhưng audit thất bại, **không được mặc định tiếp tục COMMIT** nếu cả hai là phần bắt buộc của cùng nghiệp vụ. Hành vi transaction sau lỗi khác nhau theo hệ quản trị; biến cục bộ và BEGIN...END không tự giải quyết atomicity.

## 28. Dynamic SQL và bind parameter

Đôi khi tên bảng hoặc điều kiện được chọn khi chạy. Không nên tạo SQL động bằng cách nối trực tiếp giá trị nhập từ người dùng:

~~~text
sql := 'SELECT ... WHERE customer_code = ''' + input + '''';
~~~

Cách này dễ lỗi dấu nháy và có nguy cơ **SQL injection**. Khi có thể, dùng truy vấn tĩnh với tham số. Khi thật sự cần SQL động, dùng cơ chế bind của phương ngữ.

### 28.1. PostgreSQL EXECUTE ... USING

~~~sql
DO $$
DECLARE
    v_invoice_id INTEGER := 1002;
    v_subtotal NUMERIC(12,2);
BEGIN
    EXECUTE
        'SELECT subtotal_vnd
         FROM lab_blocks_invoices
         WHERE invoice_id = $1'
    INTO v_subtotal
    USING v_invoice_id;

    RAISE NOTICE 'Subtotal=%', v_subtotal;
END;
$$;
~~~

**USING** truyền giá trị làm tham số, không ghép giá trị thô vào chuỗi truy vấn. Ở đây SQL động không cần thiết vì câu lệnh tĩnh cũng giải được, nhưng ví dụ thể hiện cách bind đúng.

### 28.2. Tên đối tượng là trường hợp khác

Tham số giá trị không thường dùng để thay trực tiếp **tên bảng/cột** trong cú pháp SQL. Nếu cần tên đối tượng động, PostgreSQL có thể dùng **format với %I** để quote identifier thích hợp và **USING** cho giá trị. Tuy nhiên, không cho đầu vào người dùng tự chọn tên bảng ngoài một danh sách được phép.

### 28.3. MySQL, SQL Server, Oracle

- **MySQL:** prepared statements và stored-program restrictions; dùng tham số hoặc cơ chế truyền giá trị được hỗ trợ, tránh ghép chuỗi đầu vào tùy tiện.
- **SQL Server:** **sp_executesql** với tham số là một lựa chọn phù hợp khi SQL phải động.
- **Oracle:** **EXECUTE IMMEDIATE ... USING** hỗ trợ bind values trong dynamic SQL theo ngữ cảnh.
- **SQLite:** bind API từ ngôn ngữ host, không tự nối dữ liệu người dùng vào câu SQL.

Khái niệm chung là **tách văn bản SQL khỏi dữ liệu**, dù cú pháp mỗi hệ khác nhau.

## 29. Một số khác biệt sâu về scope và phép gán

### 29.1. Scope được giới hạn ở đâu?

| Tình huống | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Biến local trong block thủ tục | Có, DECLARE của block | Có, DECLARE trong BEGIN...END | Có biến local T-SQL, scope theo batch/proc chứ không phải block lồng kiểu PL/pgSQL | Có, DECLARE của block | Không có khối local tổng quát |
| Block lồng tạo phạm vi local mới | Có | Có | BEGIN...END đơn thuần không tạo scope biến kiểu đó | Có | Không tương đương |
| Biến session dạng @ | Không theo cú pháp local | Có @user_variable | @ là local, không phải user session variable MySQL | Bind variables client khác local | @name có thể là bind parameter |
| Tham số thủ tục | Có | Có IN/OUT/INOUT | Có, OUTPUT | Có IN/OUT/IN OUT | Không có stored procedure core tương đương |
| Zero-row SELECT INTO local | Non-STRICT thường gán NULL | Có thể giữ giá trị cũ và phát NOT FOUND | SELECT @v=col giữ giá trị cũ | NO_DATA_FOUND | Không có local SELECT INTO |

**Đặc biệt:** ký hiệu **@x** ở MySQL, SQL Server và SQLite **không có cùng ý nghĩa**. Ở MySQL nó thường là session user variable; SQL Server dùng @ cho local variable; SQLite có thể dùng @name làm bind parameter do host cung cấp.

### 29.2. Khởi tạo mặc định khi vào block

PostgreSQL và Oracle có cú pháp **:=** trong khai báo; MySQL thường dùng **DEFAULT**; SQL Server có thể gán ngay khi **DECLARE @x INT = 0**. Các biểu thức mặc định và thời điểm đánh giá của chúng phải theo ngữ nghĩa từng hệ, đặc biệt nếu dùng hàm thời gian hoặc giá trị từ ngữ cảnh phiên.

### 29.3. OUT/INOUT không đồng nghĩa RETURN

Một function có thể trả giá trị qua **RETURN**. Một procedure có thể trả dữ liệu qua **OUT/INOUT/OUTPUT parameters** tùy phương ngữ. Một số hệ còn cho procedure trả result set bằng SELECT.

Không nên thiết kế giao diện chỉ dựa vào từ khóa: hãy xác định **có trả giá trị đơn, nhiều hàng, tham số output hay chỉ side effect**, rồi chọn cấu trúc được hỗ trợ.

## 30. Quy tắc đặt tên và tổ chức khối dễ bảo trì

Một phong cách gợi ý:

~~~text
p_invoice_id     tham số input
v_status         biến local
v_subtotal       biến local
v_net_amount     biến local
v_affected       số hàng DML tác động
r_invoice        một record/row
invoice_table    alias bảng hoặc identifier rõ ràng
~~~

Với một thủ tục nghiệp vụ:

1. **Khai báo đầu vào**, kiểu và miền giá trị cần được bảo vệ.
2. **Khai báo biến** có tên phản ánh vai trò, tránh trùng cột.
3. **Đọc đúng một hàng** bằng khóa rõ, dùng strict/single-row check khi cần.
4. **Kiểm tra điều kiện**, ví dụ status = NEW.
5. **Tính giá trị** với kiểu và quy tắc làm tròn rõ ràng.
6. **Ghi dữ liệu set-based**; tránh vòng lặp qua từng hàng khi SQL có thể xử lý cả tập.
7. **Kiểm tra số hàng**, không chỉ tin lệnh UPDATE chạy không báo lỗi.
8. **Ghi audit** trong transaction phù hợp.
9. **Xử lý exception/rollback** theo đơn vị nghiệp vụ.
10. **Trả kết quả** qua RETURN, OUT parameter hoặc SELECT theo phương ngữ.

### 30.1. Tránh block quá dài

Nếu một procedure có hàng chục biến và nhiều tầng IF/LOOP, hãy cân nhắc tách các phần tính toán hoặc câu truy vấn thành chức năng rõ ràng. Nhưng không tách tùy tiện khiến transaction, quyền hoặc side effect khó theo dõi.

### 30.2. Không dùng biến để thay mọi CTE

Nếu một câu SQL có thể tổng hợp:

~~~sql
SELECT customer_code, SUM(subtotal_vnd)
FROM lab_blocks_invoices
GROUP BY customer_code;
~~~

thì không nên mở cursor, FETCH từng hàng vào biến rồi cộng thủ công chỉ để minh họa kỹ năng thủ tục. SQL set-based thường tự nhiên hơn cho thao tác trên tập dữ liệu.

## 31. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dùng DECLARE v INT ở đầu một SQL PostgreSQL thông thường | DECLARE local thuộc PL/pgSQL block, không phải SQL thuần | Dùng DO/function/procedure đúng ngữ cảnh |
| Nhầm BEGIN của PL/pgSQL với BEGIN TRANSACTION | Cùng từ khóa nhưng hai vai trò | Phân biệt khối thủ tục với transaction |
| Nhầm SELECT INTO PL/pgSQL với SELECT INTO tạo bảng | Ngữ cảnh/phương ngữ khác | Xác định SELECT INTO biến hay CREATE TABLE AS |
| SELECT INTO non-STRICT nhưng mong lỗi khi không có hàng | PostgreSQL mặc định đặt biến thành NULL | Dùng STRICT hoặc FOUND |
| SELECT INTO PostgreSQL nhiều hàng rồi tin hàng được chọn | Không có ORDER BY bảo đảm | Dùng khóa duy nhất, STRICT, điều kiện rõ |
| Dùng FOUND nhiều câu lệnh sau | FOUND có thể đã bị thay đổi | Kiểm tra ngay sau câu liên quan |
| Quên GET DIAGNOSTICS ROW_COUNT | Không biết UPDATE có tác động hàng nào | Đọc số hàng và xử lý 0/khác 1 |
| Khai báo biến cùng tên cột | Mơ hồ hoặc so sánh sai cột | p_/v_, alias và qualify cột |
| Nghĩ biến cục bộ sống qua nhiều lần CALL | Scope chỉ trong lần thực thi | Lưu dữ liệu bền vững ở bảng |
| Nghĩ NULL bằng 0 | Logic tính toán bị sai | IS NULL/COALESCE có quy tắc |
| MySQL đặt DECLARE sau SET/SELECT | Vi phạm thứ tự khai báo block | Đưa DECLARE lên đầu block |
| Chép DELIMITER vào JDBC SQL gửi server | DELIMITER là lệnh client | Chỉ dùng ở CLI hỗ trợ |
| Dùng MySQL @session_variable thay biến local | State có thể lưu qua connection pool | DECLARE local khi cần |
| Nghĩ MySQL SELECT INTO zero rows luôn gán NULL | Có thể giữ giá trị cũ | Khởi tạo và xử lý NOT FOUND phù hợp |
| MySQL cursor handler NOT FOUND bị SELECT INTO khác kích hoạt | Handler dùng chung phạm vi | Thiết kế block/handler rõ |
| SQL Server biến @ vẫn dùng sau GO | GO kết thúc batch | Cùng batch hoặc khai báo lại |
| SQL Server BEGIN...END tạo scope shadowing | Không như PL/pgSQL | Không tái khai báo trùng tên |
| SQL Server SELECT @v=col zero rows được gán NULL | Thực tế có thể giữ giá trị cũ | SET với scalar subquery hoặc kiểm tra row count |
| SQL Server SELECT ... INTO được hiểu như gán biến | Tạo bảng mới | Dùng SELECT @v = col |
| SQL Server @@ROWCOUNT bị thay đổi trước khi kiểm tra | Câu khác ghi đè trạng thái | Lưu ngay sau DML |
| Oracle SELECT INTO zero rows không được bắt | NO_DATA_FOUND | Bắt lỗi hoặc thay thiết kế truy vấn |
| Oracle SELECT INTO nhiều rows rồi nghĩ lấy hàng đầu | TOO_MANY_ROWS | Dùng khóa và truy vấn đúng grain |
| DBMS_OUTPUT không hiển thị | Client chưa bật/đọc output | Cấu hình client phù hợp |
| SQLite dùng DECLARE/SET như SQL Server | SQLite không có thủ tục tự do tương đương | Bind params/CTE/host code |
| SQLite nhầm @name với biến session MySQL | @name là dạng bind parameter | Bind qua API |
| Dùng phép gán biến để bảo vệ khỏi lost update | Biến không tạo khóa | DML atomic/transaction/lock |
| Ghép input trực tiếp vào dynamic SQL | SQL injection và lỗi quote | Prepared/bind values |
| Bắt mọi exception rồi COMMIT | Có thể lưu dữ liệu nghiệp vụ một phần | Policy rollback rõ ràng |

## 32. Bài tập thực hành

Các bài PostgreSQL sử dụng bảng tạm **lab_blocks_invoices** và **lab_blocks_audit** ở phần 5. Những bài theo phương ngữ khác dùng schema tương đương trên hệ tương ứng; không dán toàn bộ ví dụ MySQL/Oracle/SQL Server vào PostgreSQL vì cú pháp không tương thích.

1. Tạo hai bảng tạm và nạp dữ liệu mẫu. Kiểm tra invoice 1001 có subtotal 120000, discount 10%, status NEW.
2. Viết DO block khai báo **v_invoice_id = 1002**, SELECT subtotal/discount vào biến, tính net amount 50000 và RAISE NOTICE.
3. Viết DO block cập nhật invoice 1002 từ NEW sang APPROVED, ghi net_amount_vnd và audit tương tự phần 6.
4. Viết SELECT INTO STRICT cho invoice_id = 9999, quan sát NO_DATA_FOUND. Bọc trong EXCEPTION xử lý lỗi có chủ đích.
5. Bỏ STRICT, SELECT INTO cho invoice_id không có, kiểm tra **FOUND** và giá trị biến sau SELECT.
6. Viết truy vấn SELECT INTO non-STRICT chỉ lọc status = 'NEW' trong khi có nhiều đơn. Vì sao không được dựa vào một hàng ngẫu nhiên?
7. Dùng **%TYPE** cho subtotal và **%ROWTYPE** cho toàn dòng invoice, đọc invoice 1001.
8. Dùng một biến RECORD để lấy invoice_id và công thức computed_net, truy cập hai field của record.
9. Tạo block trong có **v_message** cùng tên biến ngoài. Quan sát giá trị trong và sau block.
10. Khai báo v_amount NUMERIC chưa có DEFAULT. Dùng v_amount * 2 và giải thích vì sao ra NULL.
11. Viết IF/E LSIF/ELSE tương ứng các mức tổng tiền SMALL, MEDIUM, LARGE; chọn ngưỡng nhất quán.
12. Viết FOR loop tính tổng 1 tới 10; sau đó đề xuất cách dùng SQL SUM nếu số nằm trong bảng.
13. Trong UPDATE invoice, dùng GET DIAGNOSTICS để lấy số hàng bị đổi; xử lý trường hợp 0 hàng.
14. Viết function lab_net_amount(p_subtotal, p_discount_pct) dùng RETURN thay vì RAISE NOTICE. Thực thi với (120000,10) và (50000,0).
15. Giải thích vì sao function thuần tính toán có thể IMMUTABLE, còn function đọc bảng hóa đơn thay đổi không phù hợp với nhãn này.
16. Viết một procedure chỉ RAISE NOTICE invoice_id nhận qua tham số, gọi bằng CALL.
17. So sánh BEGIN của DO block với BEGIN; ... COMMIT; của SQL transaction.
18. Tạo exception block bắt unique_violation khi thử thêm invoice 1001 lần nữa. Vì sao không nên bắt mọi UNIQUE vô điều kiện?
19. Viết một procedure MySQL có DECLARE ở đầu, SELECT ... INTO, SET v_net và UPDATE.
20. Nêu lý do **DELIMITER //** không được gửi thẳng như một phần SQL qua JDBC.
21. So sánh MySQL v_total local với @total session. Điều gì có thể xảy ra khi ứng dụng tái sử dụng connection?
22. Trong MySQL, xử lý SELECT INTO không có hàng. Tại sao giá trị local có thể vẫn là giá trị cũ?
23. Viết T-SQL DECLARE @subtotal/@discount/@net và SET tính 108000. SQL Server có cần BEGIN...END cho đoạn này không?
24. Trên SQL Server, so sánh SET @x = (SELECT ...) và SELECT @x = col FROM ... khi không có hàng.
25. Giải thích vì sao GO khiến SQL Server @variable được khai báo ở batch trước không còn khả dụng.
26. Viết UPDATE SQL Server và lưu @@ROWCOUNT ngay sau lệnh; giải thích nếu đặt PRINT trước khi đọc sẽ có rủi ro gì.
27. Viết một procedure SQL Server có tham số OUTPUT trả net amount.
28. Viết block PL/SQL Oracle dùng DECLARE, :=, SELECT INTO và DBMS_OUTPUT, có nhánh NO_DATA_FOUND.
29. So sánh SQL%ROWCOUNT Oracle với @@ROWCOUNT SQL Server và GET DIAGNOSTICS ROW_COUNT PostgreSQL.
30. Trên SQLite, tính net amount qua SELECT với placeholder hoặc một CTE params, không dùng DECLARE.
31. Viết trigger SQLite ngăn subtotal âm; giải thích vì sao BEGIN...END ở trigger không có nghĩa SQLite hỗ trợ biến local tổng quát.
32. Mô tả cách tránh lost update khi hai transaction cùng đọc balance vào biến rồi ghi lại.
33. Viết EXECUTE ... USING PostgreSQL bind invoice_id, giải thích vì sao không nên nối input thô vào SQL động.
34. Cho một đoạn procedure có cột status và biến status cùng tên; viết lại dùng alias bảng, p_ và v_.
35. Chọn một ví dụ thực tế cần biến cục bộ và một ví dụ có thể giải bằng SQL set-based ngắn hơn; giải thích lựa chọn.

### Câu hỏi tự kiểm tra

**Câu 1.** Trong PostgreSQL, DECLARE v_amount NUMERIC; có dùng trực tiếp như câu SQL bình thường từ mọi client không?

**Đáp án:** **Không.** Đây là khai báo biến trong **PL/pgSQL** block/function/procedure. SQL khai báo thông thường không có biến cục bộ theo cú pháp ấy.

**Câu 2.** BEGIN...END của một PL/pgSQL block có tự mở một transaction mới giống BEGIN; ở cấp SQL không?

**Đáp án:** **Không.** BEGIN...END là cấu trúc khối; transaction boundary là cơ chế khác.

**Câu 3.** PostgreSQL SELECT INTO không STRICT với 0 hàng có giữ giá trị trước đó của biến không?

**Đáp án:** **Không.** Các biến đích được đặt NULL, và FOUND = FALSE.

**Câu 4.** SELECT INTO STRICT với 0 hoặc nhiều hơn một hàng ra sao?

**Đáp án:** **0 hàng → NO_DATA_FOUND**, **nhiều hàng → TOO_MANY_ROWS** trong PL/pgSQL.

**Câu 5.** SELECT INTO ở SQL Server có phải cú pháp gán vào biến @amount không?

**Đáp án:** **Không.** SELECT ... INTO thường tạo bảng mới. Gán biến bằng SET @amount = ... hoặc SELECT @amount = column.

**Câu 6.** MySQL DECLARE local có được đặt sau một UPDATE trong cùng block không?

**Đáp án:** **Không.** Các DECLARE cần nằm trong phần khai báo đầu block theo thứ tự của MySQL.

**Câu 7.** MySQL @count có vòng đời giống v_count được DECLARE trong stored procedure không?

**Đáp án:** **Không.** @count là user-defined session variable; v_count local thuộc phạm vi block.

**Câu 8.** SQL Server DECLARE @x rồi GO, batch mới còn dùng @x được không?

**Đáp án:** **Không.** GO kết thúc batch ở client; biến local không còn scope ở batch kế tiếp.

**Câu 9.** Oracle SELECT INTO không có hàng có mặc định đặt biến NULL rồi đi tiếp không?

**Đáp án:** **Không.** PL/SQL thường phát sinh **NO_DATA_FOUND**, cần xử lý thích hợp.

**Câu 10.** SQLite có hỗ trợ DECLARE/SET biến local procedural giống SQL Server không?

**Đáp án:** **Không** trong SQL lõi. Dùng bind parameters, CTE hoặc logic trong ứng dụng.

**Câu 11.** Dùng biến v_balance có tự ngăn hai transaction cập nhật chồng lên nhau không?

**Đáp án:** **Không.** Cần DML nguyên tử, khóa/mức cô lập và chính sách transaction phù hợp.

**Câu 12.** Khi phải tạo SQL động, có nên nối trực tiếp giá trị input vào chuỗi truy vấn không?

**Đáp án:** **Không.** Dùng prepared/bind parameters; ở PostgreSQL PL/pgSQL có **EXECUTE ... USING**.

## 33. Ghi nhớ cốt lõi

**Khối lệnh, biến cục bộ và phép gán thuộc về ngôn ngữ thủ tục của từng hệ quản trị**, không phải một cú pháp SQL thống nhất cho mọi database.

Đối với **PostgreSQL PL/pgSQL**, hãy nhớ:

~~~text
DO $$                  -- Chạy một block vô danh
DECLARE                -- Khai báo local variables
    v_x INTEGER := 0;
BEGIN                  -- Bắt đầu các câu lệnh PL/pgSQL
    v_x := v_x + 1;    -- Gán
    SELECT col INTO v_x FROM ...;
END;
$$;
~~~

Với MySQL, DECLARE phải ở đầu **BEGIN...END** của stored program và **SET** thường là phép gán rõ nhất. Với SQL Server, biến local có **@**, gán bằng **SET @v** hoặc **SELECT @v = col**, phạm vi theo batch/procedure và **GO** do client xử lý. Với Oracle PL/SQL, dùng **DECLARE/BEGIN/EXCEPTION/END**, **:=** và SELECT INTO yêu cầu đúng một hàng. Với SQLite, thường dùng **bind parameters và CTE**, không giả định có stored-program variables tương tự.

**Phân biệt SELECT INTO theo ngữ cảnh** là kiến thức quan trọng: nó có thể gán biến ở PL/pgSQL, MySQL, Oracle, nhưng tạo bảng trong T-SQL hoặc PostgreSQL SQL thông thường. Đồng thời cần hiểu khác biệt khi truy vấn trả **0 hàng hoặc nhiều hàng**.

Cuối cùng, biến cục bộ **không thay thế transaction, unique constraints, khóa đồng thời hay kiểm tra số hàng**. Hãy đặt tên biến rõ ràng, qualify cột bảng, xử lý NULL và lỗi đúng phạm vi, ưu tiên SQL set-based khi thích hợp, và truyền tham số an toàn thay vì ghép dữ liệu thô vào SQL động.
