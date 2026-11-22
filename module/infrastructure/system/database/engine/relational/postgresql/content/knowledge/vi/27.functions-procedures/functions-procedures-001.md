# CREATE FUNCTION, CREATE PROCEDURE và tiêu chí lựa chọn trong PostgreSQL

PostgreSQL cho phép đóng gói logic ở phía cơ sở dữ liệu thành **function (hàm)** hoặc **procedure (thủ tục)**. Cả hai là những đối tượng có tên, tham số, ngôn ngữ thực thi và quyền riêng, nhưng **không có cùng hợp đồng gọi và xử lý giao dịch**.

Ví dụ, khi ứng dụng cần tính tiền của một đơn hàng trong câu `SELECT`, một function là lựa chọn tự nhiên:

~~~sql
SELECT routine_lab.get_order_total(1001);
~~~

Khi ứng dụng cần thực hiện một thao tác nghiệp vụ nhiều bước, chẳng hạn đổi trạng thái đơn hàng và ghi nhật ký trong một lời gọi, procedure có thể là lựa chọn phù hợp:

~~~sql
CALL routine_lab.mark_order_paid(1002);
~~~

Điểm quan trọng: **function không đồng nghĩa “chỉ đọc”, và procedure không đồng nghĩa “luôn tự COMMIT”.** PostgreSQL cho phép một số function gây tác dụng phụ, còn procedure chỉ có khả năng điều khiển transaction trong những ngữ cảnh gọi được phép.

Bài học **“CREATE FUNCTION, CREATE PROCEDURE và tiêu chí lựa chọn”**, thuộc chương **Hàm và thủ tục** của module **Database Engine Relational PostgreSQL**, giải thích cú pháp, kiểu kết quả, transaction, phân quyền, khả năng tối ưu, tình huống dùng trong Java/JDBC, quản lý phiên bản và cách chọn đúng công cụ.

> **Phạm vi thực hành:** toàn bộ DDL/DML minh họa chỉ dành cho database lab riêng. Một số ví dụ cố ý thay dữ liệu hoặc `COMMIT`; không chạy lên production nếu chưa kiểm tra quyền, transaction, dependent objects và quy trình rollback.

---

## 1. Function và procedure có điểm chung nào?

Cả function và procedure đều:

- Là đối tượng schema có tên và tham số.
- Được định nghĩa bằng SQL, PL/pgSQL hoặc những ngôn ngữ được PostgreSQL hỗ trợ.
- Có thể truy cập dữ liệu, thực hiện công việc và phát sinh lỗi.
- Có thể tái sử dụng từ nhiều client.
- Có quyền `EXECUTE`, owner, metadata và dependencies.
- Có thể có các overload với danh sách kiểu tham số thích hợp.
- Có thể được tạo, thay thế, đổi tên và xóa bằng DDL.
- Chịu tác động của `search_path`, role, quyền trên object và cấu hình session.

Khác biệt cốt lõi là **cách gọi, kiểu kết quả và khả năng kết thúc transaction**.

### 1.1. So sánh nhanh

| Câu hỏi | Function | Procedure |
|---|---|---|
| Tạo bằng | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Gọi điển hình | `SELECT f(...)` hoặc dùng trong SQL expression | `CALL p(...)` |
| Dùng trong `WHERE`, `ORDER BY`, `JOIN` | Có, nếu kiểu/hình dạng phù hợp | Không trực tiếp |
| Khai báo giá trị trả về | `RETURNS type`, `RETURNS TABLE`, `RETURNS SETOF`, ... | Không có `RETURNS type` như function |
| Trả nhiều hàng typed | Có thể dùng set-returning function | Không tương đương `RETURNS TABLE` qua `CALL` |
| Có thể sửa dữ liệu | Có, với function phù hợp | Có |
| Có thể `COMMIT`/`ROLLBACK` bên trong | Không | Chỉ trong ngữ cảnh `CALL` được phép và có giới hạn |
| Ngôn ngữ thường gặp | SQL, PL/pgSQL | SQL, PL/pgSQL |
| Dùng cho phép tính trong SELECT | Rất phù hợp | Không phù hợp |
| Dùng cho thao tác nghiệp vụ theo lệnh | Có thể, nhưng phải cân nhắc | Thường dễ biểu đạt |

PostgreSQL hỗ trợ `CREATE PROCEDURE` từ phiên bản 11. Một số tùy chọn/tham số được mở rộng ở những phiên bản tiếp theo. Luôn kiểm tra phiên bản server khi dùng tính năng mới.

## 2. Phân biệt SQL function với stored procedure

Thuật ngữ *stored routine* bao gồm nhiều loại chương trình lưu trong database. Trong PostgreSQL:

- **Function** có `RETURNS` và có thể được gọi như một phần của biểu thức/truy vấn.
- **Procedure** được gọi bằng `CALL` và thường diễn đạt một thao tác, không phải một biểu thức trả giá trị để dùng trong `SELECT`.
- **Trigger function** là một dạng function đặc biệt có `RETURNS trigger` và được gọi bởi cơ chế trigger.
- **Aggregate/window function** là những dạng function đặc thù khác, không đồng nhất với procedure.

Không dùng từ “stored procedure” theo nghĩa chung từ các hệ quản trị khác rồi suy rằng mọi routine PostgreSQL được gọi bằng `EXEC` hoặc đều có output result sets giống nhau.

## 3. Database lab cho các ví dụ

Trong một **database thực hành trống**, tạo schema và bảng đơn hàng:

~~~sql
CREATE SCHEMA routine_lab;

CREATE TABLE routine_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE routine_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES routine_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE routine_lab.audit_log (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

INSERT INTO routine_lab.customers (
    customer_id, customer_name
)
VALUES
    (101, 'Lan'),
    (102, 'Minh');

INSERT INTO routine_lab.orders (
    order_id, customer_id, status, total_amount, placed_at
)
VALUES
    (1001, 101, 'paid', 125000.00,
     TIMESTAMPTZ '2026-11-01 09:00:00+00'),
    (1002, 102, 'new', 89000.00,
     TIMESTAMPTZ '2026-11-02 10:00:00+00'),
    (1003, 101, 'paid', 35000.00,
     TIMESTAMPTZ '2026-11-03 11:00:00+00');

ANALYZE routine_lab.orders;
~~~

Dữ liệu gồm 2 khách hàng, 3 đơn hàng và bảng audit đang rỗng. `status` và `total_amount` là các cột typed có constraint. Những function/procedure sau đây đều dựa trên schema này.

### 3.1. Vì sao luôn viết tên schema?

Viết `routine_lab.orders` thay vì `orders` giúp tránh va chạm tên trong schema khác và giảm phụ thuộc vào `search_path`.

Điều này đặc biệt quan trọng đối với routine có `SECURITY DEFINER`, vì việc tìm đối tượng theo tên không an toàn có thể gây lỗ hổng nếu một schema trong `search_path` cho phép người khác tạo object.

### 3.2. Lab không được reset bừa bãi

Các lệnh `CREATE SCHEMA`/`CREATE TABLE` sẽ lỗi nếu đã tồn tại. Không dùng `DROP SCHEMA ... CASCADE` trên schema chưa xác nhận chỉ để chạy lại ví dụ. Hãy dùng database lab mới hoặc reset có chủ đích.

## 4. Cú pháp CREATE FUNCTION tổng quát

Một function được khai báo theo hình dạng:

~~~sql
CREATE [ OR REPLACE ] FUNCTION schema_name.function_name(
    [ argument_name argument_type [ DEFAULT default_expr ], ... ]
)
RETURNS return_type
LANGUAGE language_name
[ function_attributes ... ]
AS $function_body$
    ...
$function_body$;
~~~

Các dấu ngoặc vuông là ký hiệu giải thích phần tùy chọn, **không phải câu lệnh có thể chạy nguyên dạng**.

Những thành phần quan trọng:

1. `CREATE FUNCTION` tạo function.
2. `OR REPLACE` thay định nghĩa routine cùng identity với những giới hạn về chữ ký/kết quả.
3. `schema_name.function_name` xác định tên đầy đủ.
4. Danh sách tham số xác định input và overload.
5. `RETURNS` mô tả kiểu kết quả.
6. `LANGUAGE sql` hoặc `LANGUAGE plpgsql` xác định cách thực thi.
7. Thuộc tính `VOLATILE`/`STABLE`/`IMMUTABLE`, `STRICT`, `PARALLEL`, `SECURITY`, `COST` ... cung cấp thông tin hành vi cho PostgreSQL.
8. `AS $$ ... $$` chứa mã nguồn routine.

### 4.1. Dollar quoting

`$$ ... $$` hoặc `$tag$ ... $tag$` tránh việc phải escape từng dấu nháy đơn bên trong thân routine:

~~~sql
CREATE FUNCTION routine_lab.hello_text()
RETURNS TEXT
LANGUAGE sql
AS $body$
    SELECT 'Xin chào PostgreSQL'::TEXT;
$body$;
~~~

`$body$` là delimiter, không phải biến hay tham số SQL.

### 4.2. Không nhầm RETURNS với RETURN

- `RETURNS text` ở header khai báo **kiểu kết quả**.
- `RETURN expression;` trong PL/pgSQL kết thúc function hoặc trả giá trị theo cú pháp của hàm.
- `RETURN QUERY ...;` thêm những hàng vào tập kết quả của set-returning PL/pgSQL function.

## 5. SQL-language function trả một scalar

Ví dụ tính thành tiền:

~~~sql
CREATE FUNCTION routine_lab.line_total(
    p_price NUMERIC,
    p_quantity INTEGER
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_price * p_quantity;
$$;
~~~

Gọi:

~~~sql
SELECT routine_lab.line_total(45000.00, 2);
~~~

Kết quả: 90000.00 theo biểu diễn số phù hợp.

### 5.1. Vì sao dùng LANGUAGE sql?

Đây là phép tính một biểu thức, không cần biến, vòng lặp, nhánh điều kiện hay xử lý exception. SQL-language function gọn và có cơ hội được planner tối ưu/inlining trong những trường hợp đủ điều kiện.

### 5.2. Vì sao IMMUTABLE?

Với cùng `p_price` và `p_quantity`, phép nhân thuần túy theo kiểu SQL được dùng không phụ thuộc dữ liệu bảng hay thời gian. Đó là đặc tính phù hợp với `IMMUTABLE` trong ví dụ này.

### 5.3. Vì sao STRICT?

Nếu một input là SQL NULL, phép nhân trả NULL. `STRICT` cho phép PostgreSQL bỏ qua việc thực hiện function và trả NULL trực tiếp khi có input NULL.

### 5.4. Kiểu trả về không nên phụ thuộc format trình bày

`RETURNS NUMERIC` mô tả số, không buộc client phải nhận một chuỗi tiền có dấu phẩy/đơn vị. Định dạng hiển thị nên do application/presentation layer hoặc lớp xuất dữ liệu quyết định.

## 6. Gọi function bằng SELECT

Function trả scalar có thể xuất hiện ở nhiều vị trí:

~~~sql
SELECT routine_lab.line_total(45000, 2)
    AS amount;
~~~

~~~sql
SELECT
    o.order_id,
    o.total_amount,
    routine_lab.line_total(o.total_amount, 2)
        AS doubled_amount
FROM routine_lab.orders AS o
ORDER BY o.order_id;
~~~

~~~sql
SELECT o.order_id
FROM routine_lab.orders AS o
WHERE routine_lab.line_total(o.total_amount, 1) > 50000
ORDER BY o.order_id;
~~~

Vì là một **SQL expression**, function có thể dùng trong `SELECT`, `WHERE`, `ORDER BY`, `JOIN` hoặc những ngữ cảnh thích hợp khác.

### 6.1. Không mặc định function trong WHERE là tối ưu

Bọc một cột trong function có thể làm index thông thường khó được dùng nếu planner không biến đổi được biểu thức. Khi truy vấn bảng lớn, hãy quan sát `EXPLAIN` thay vì cho rằng việc đóng gói logic bằng function luôn giữ hiệu năng cũ.

## 7. Tham số có tên, DEFAULT và named notation

Ví dụ:

~~~sql
CREATE FUNCTION routine_lab.add_fee(
    p_amount NUMERIC,
    p_rate NUMERIC DEFAULT 0.05
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * (1 + p_rate);
$$;
~~~

Gọi theo vị trí:

~~~sql
SELECT routine_lab.add_fee(100000);
SELECT routine_lab.add_fee(100000, 0.10);
~~~

Gọi theo tên:

~~~sql
SELECT routine_lab.add_fee(
    p_rate => 0.10,
    p_amount => 100000
);
~~~

Ở named notation, tên tham số là một phần interface gọi routine.

### 7.1. DEFAULT không làm thay đổi kiểu kết quả

Nếu bỏ qua `p_rate` khi gọi, PostgreSQL dùng biểu thức default phù hợp. Hàm vẫn trả NUMERIC.

### 7.2. Cẩn thận overload kết hợp tham số mặc định

Nhiều overload có default arguments hoặc tên gần giống có thể làm việc resolve function khó đoán hoặc báo ambiguous. Với public database API, ưu tiên chữ ký rõ ràng và gọi schema-qualified.

## 8. STRICT và xử lý SQL NULL

Hai cú pháp tương đương về ý nghĩa:

~~~sql
STRICT
~~~

và:

~~~sql
RETURNS NULL ON NULL INPUT
~~~

Hàm `STRICT` không được thực thi khi một đối số là SQL NULL; PostgreSQL trả SQL NULL.

Ví dụ:

~~~sql
SELECT routine_lab.line_total(NULL::NUMERIC, 2);
~~~

Kết quả là SQL NULL.

### 8.1. Không dùng STRICT khi NULL có ý nghĩa riêng

Ví dụ nghiệp vụ muốn “không truyền giảm giá nghĩa là 0”. Nếu function phải tự xử lý NULL bằng `COALESCE`, không nên dùng STRICT cho tham số đó vì thân hàm sẽ không chạy khi input NULL.

~~~sql
CREATE FUNCTION routine_lab.discounted_amount(
    p_amount NUMERIC,
    p_discount NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
AS $$
    SELECT
        CASE
            WHEN p_amount IS NULL THEN NULL
            ELSE p_amount - COALESCE(p_discount, 0)
        END;
$$;
~~~

Ở đây NULL của `p_discount` được diễn giải là 0, còn NULL của amount vẫn trả NULL theo quy tắc định nghĩa.

## 9. Function đọc bảng: chọn STABLE

Để lấy tổng tiền đơn hàng theo ID:

~~~sql
CREATE FUNCTION routine_lab.get_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT o.total_amount
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;
$$;
~~~

Gọi:

~~~sql
SELECT routine_lab.get_order_total(1001);
~~~

Kết quả mong đợi: 125000.00.

### 9.1. Vì sao không dùng IMMUTABLE?

Giá trị `total_amount` trong bảng có thể bị UPDATE. Cùng `p_order_id` ở hai thời điểm khác nhau có thể trả kết quả khác nhau. Gắn nhầm `IMMUTABLE` vào function đọc bảng thay đổi được có thể khiến planner tối ưu/caching theo giả định không đúng, dẫn tới kết quả cũ hoặc hành vi gây ngạc nhiên.

### 9.2. Khi không tìm thấy order

SQL scalar function này không tìm được hàng sẽ trả SQL NULL theo cách hàm SQL scalar lấy kết quả. Điều đó khác với trả 0.

Chọn rõ domain semantics:

- “Không tồn tại” → NULL.
- “Không tồn tại” → RAISE EXCEPTION.
- “Không tồn tại” → cấu trúc kết quả có status.

Không tự coi việc không tìm thấy order tương đương total 0 nếu nghiệp vụ không quy định.

## 10. PL/pgSQL function: biến, điều kiện, RETURN

Khi cần điều kiện rẽ nhánh, PL/pgSQL dễ đọc hơn một biểu thức phức tạp.

~~~sql
CREATE FUNCTION routine_lab.order_category(
    p_order_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_amount NUMERIC;
BEGIN
    SELECT o.total_amount
    INTO v_amount
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;

    IF NOT FOUND THEN
        RETURN 'not_found';
    ELSIF v_amount >= 100000 THEN
        RETURN 'large';
    ELSE
        RETURN 'regular';
    END IF;
END;
$$;
~~~

Gọi:

~~~sql
SELECT
    routine_lab.order_category(1001) AS first_category,
    routine_lab.order_category(1002) AS second_category,
    routine_lab.order_category(9999) AS missing_category;
~~~

Kết quả logic: `large`, `regular`, `not_found`.

### 10.1. Những từ khóa cần nhớ

- `DECLARE` khai báo biến.
- `BEGIN ... END` là **khối PL/pgSQL**, không tự động nghĩa là mở transaction SQL mới.
- `SELECT ... INTO variable` lấy kết quả vào biến trong PL/pgSQL.
- `FOUND` cho biết một số câu lệnh trước đó có tìm/ảnh hưởng hàng hay không.
- `IF ... ELSIF ... ELSE ... END IF` xử lý nhánh.
- `RETURN` kết thúc function, trả giá trị scalar.

### 10.2. Tránh tên biến trùng tên cột

Sử dụng prefix `p_` cho parameter, `v_` cho biến, alias `o` cho bảng giúp tránh ambiguous identifiers trong PL/pgSQL.

## 11. Function trả nhiều cột bằng RETURNS TABLE

Function có thể trả một **tập hàng** với schema rõ:

~~~sql
CREATE FUNCTION routine_lab.orders_for_customer(
    p_customer_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    status TEXT,
    total_amount NUMERIC
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        o.order_id,
        o.status,
        o.total_amount
    FROM routine_lab.orders AS o
    WHERE o.customer_id = p_customer_id
    ORDER BY o.order_id;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM routine_lab.orders_for_customer(101);
~~~

Kết quả:

| order_id | status | total_amount |
|---:|---|---:|
| 1001 | paid | 125000.00 |
| 1003 | paid | 35000.00 |

### 11.1. Khác biệt với scalar function

- `RETURNS NUMERIC`: một giá trị.
- `RETURNS TABLE(...)`: nhiều cột, có thể nhiều hàng.
- Khi dùng `SELECT * FROM function(...)`, các cột có tên/kiểu như một relation.
- Có thể `JOIN`, `FILTER`, `ORDER BY` trên kết quả khi thích hợp.

### 11.2. Không nhầm RETURNS TABLE với procedure OUT

Procedure có thể có output parameters, nhưng không tương đương một set-returning function dùng trong `FROM`. Nếu cần biểu thức quan hệ để JOIN, `RETURNS TABLE` thường là lựa chọn trực tiếp hơn.

## 12. PL/pgSQL với RETURN QUERY

Khi có logic trước khi trả nhiều rows:

~~~sql
CREATE FUNCTION routine_lab.paid_orders_for_customer(
    p_customer_id BIGINT,
    p_min_amount NUMERIC DEFAULT 0
)
RETURNS TABLE (
    order_id BIGINT,
    total_amount NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_min_amount < 0 THEN
        RAISE EXCEPTION
            'p_min_amount must be nonnegative: %',
            p_min_amount;
    END IF;

    RETURN QUERY
    SELECT
        o.order_id,
        o.total_amount
    FROM routine_lab.orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'paid'
      AND o.total_amount >= p_min_amount
    ORDER BY o.order_id;
END;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM routine_lab.paid_orders_for_customer(101, 50000);
~~~

Kết quả có order 1001.

### 12.1. RETURN QUERY và RETURN NEXT

Trong PL/pgSQL set-returning functions:

- `RETURN QUERY SELECT ...` thêm các hàng của truy vấn.
- `RETURN NEXT expression` thêm một hàng/giá trị theo cấu trúc return type.
- `RETURN;` không có biểu thức kết thúc set-returning function sau khi thu thập kết quả.

Không dùng `RETURN QUERY` trong function chỉ `RETURNS NUMERIC`.

## 13. RETURNS SETOF type và composite type

Một function có thể trả tập giá trị scalar hoặc tập row một kiểu composite.

Ví dụ số nguyên:

~~~sql
CREATE FUNCTION routine_lab.sequence_1_to(
    p_last INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT g::INTEGER
    FROM generate_series(1, p_last) AS g;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM routine_lab.sequence_1_to(5);
~~~

Kết quả là 1,2,3,4,5 theo các rows; nếu cần bảo đảm thứ tự bên ngoài, nên thêm `ORDER BY`.

### 13.1. Khi nào dùng RETURNS SETOF?

- Trả một tập giá trị cùng kiểu.
- Trả tập một composite type có sẵn.
- Khi muốn mô tả output bằng nhiều cột đặt tên ngay trong khai báo, `RETURNS TABLE` thường dễ đọc.

### 13.2. Function kết quả nhiều hàng dùng trong LATERAL

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    x.order_id,
    x.total_amount
FROM routine_lab.customers AS c
CROSS JOIN LATERAL routine_lab.orders_for_customer(
    c.customer_id
) AS x
ORDER BY c.customer_id, x.order_id;
~~~

`LATERAL` cho function truy cập giá trị customer_id của từng hàng cha. Đây là lý do function trả bảng hữu ích trong SQL composition; procedure không được gọi bằng `JOIN LATERAL ... CALL`.

## 14. Function vẫn có thể sửa dữ liệu

Một hiểu lầm phổ biến là function luôn chỉ dùng để tính toán.

Ví dụ function viết audit:

~~~sql
CREATE FUNCTION routine_lab.add_audit_note(
    p_order_id BIGINT,
    p_action TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_audit_id BIGINT;
BEGIN
    INSERT INTO routine_lab.audit_log(
        order_id, action
    )
    VALUES (p_order_id, p_action)
    RETURNING audit_id INTO v_audit_id;

    RETURN v_audit_id;
END;
$$;
~~~

Gọi:

~~~sql
SELECT routine_lab.add_audit_note(
    1001, 'manual_review'
);
~~~

Hàm đã **INSERT một hàng thật**. Đây là `VOLATILE` function có side effect.

### 14.1. Vì sao vẫn cân nhắc procedure cho command?

Kỹ thuật PostgreSQL cho phép function thực hiện DML, nhưng nếu thao tác nghiệp vụ chủ yếu gây tác dụng phụ và không cần dùng như biểu thức, procedure qua `CALL` có thể làm API rõ nghĩa hơn.

Ngược lại, không phải cứ có một câu INSERT là bắt buộc phải dùng procedure. Hãy xét hợp đồng gọi và transaction.

### 14.2. Tránh side effect bất ngờ trong SELECT số lượng lớn

Nếu gọi function ghi audit cho từng hàng của một bảng lớn, có thể sinh rất nhiều rows và WAL. Đừng đặt function có side effects trong SELECT/WHERE chỉ vì nó có thể được gọi bằng biểu thức.

## 15. VOLATILE, STABLE, IMMUTABLE là gì?

PostgreSQL dùng **volatility classification** để hiểu những bảo đảm mà tác giả routine cung cấp cho planner và cho hành vi snapshot.

| Thuộc tính | Bảo đảm mong muốn | Ví dụ điển hình |
|---|---|---|
| `IMMUTABLE` | Cùng input luôn cùng kết quả, không phụ thuộc trạng thái thay đổi | Phép toán thuần túy |
| `STABLE` | Với input giống nhau, kết quả ổn định trong một statement phù hợp | Đọc bảng hoặc giá trị ổn định theo statement |
| `VOLATILE` | Có thể thay đổi giữa các lời gọi hoặc có tác dụng phụ | Ghi bảng, random, clock_timestamp |

**Mặc định PostgreSQL dùng VOLATILE** nếu không khai báo.

### 15.1. IMMUTABLE không chỉ có nghĩa “không sửa dữ liệu”

Một function đọc `orders` nhưng không UPDATE vẫn **không nên IMMUTABLE**, vì dữ liệu bảng có thể thay đổi giữa các statements.

### 15.2. STABLE không có nghĩa kết quả mãi mãi cố định

Function `get_order_total(id)` có thể trả giá trị khác trong một statement ở thời điểm sau khi đơn hàng bị cập nhật. STABLE chỉ cam kết mức ổn định thích hợp trong phạm vi statement và hành vi snapshot tương ứng.

### 15.3. VOLATILE không mặc định “kém hiệu năng”

Nó mô tả tính biến động/side effects, không phải chỉ số chất lượng. Không khai báo `IMMUTABLE` sai để cố tối ưu một function vốn phải đọc dữ liệu mới.

## 16. Các ví dụ volatility điển hình

~~~sql
SELECT
    now() AS transaction_timestamp,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time,
    random() AS random_value;
~~~

Trong PostgreSQL:

- `now()` / `transaction_timestamp()` thường được xem là `STABLE`.
- `statement_timestamp()` ổn định cho mốc bắt đầu statement tương ứng, được phân loại phù hợp.
- `clock_timestamp()` là `VOLATILE` vì có thể thay đổi ngay trong statement.
- `random()` là `VOLATILE`.

**Không gắn IMMUTABLE cho hàm phụ thuộc thời gian, session configuration, bảng dữ liệu hay nguồn bên ngoài có thể thay đổi.**

### 16.1. Tác động đến prepared statements

Planner có thể dùng những bảo đảm mạnh của IMMUTABLE để đơn giản hóa biểu thức, kể cả trong kế hoạch được cache. Nếu function thực ra không bất biến, việc ghi sai volatility có thể khiến output cũ xuất hiện trong những hoàn cảnh khó nhận ra.

## 17. Snapshot và dữ liệu thay đổi bên trong routine

Với function bằng SQL/PL/pgSQL, volatility có liên hệ với cách các truy vấn nội bộ nhìn dữ liệu:

- Những function `STABLE`/`IMMUTABLE` dùng snapshot của câu lệnh gọi theo cơ chế thích hợp.
- Function `VOLATILE` có thể lấy snapshot mới ở những truy vấn nội bộ liên quan.
- Transaction isolation của caller vẫn chi phối tính nhất quán tổng thể.

Điều này quan trọng khi function đọc dữ liệu cùng lúc với những DML khác.

Không lấy volatility thay cho việc thiết kế `READ COMMITTED`/`REPEATABLE READ`/`SERIALIZABLE`, lock và transaction boundaries. Volatility là contract cho planner/semantics routine, không phải lựa chọn isolation level.

## 18. PARALLEL SAFE, RESTRICTED và UNSAFE

PostgreSQL còn cho phép phân loại function đối với parallel query:

- `PARALLEL SAFE`: có thể chạy trong parallel workers khi đủ điều kiện.
- `PARALLEL RESTRICTED`: phải chạy ở leader trong các kế hoạch phù hợp.
- `PARALLEL UNSAFE`: sự hiện diện của function có thể ngăn dùng parallel plan.

Nếu không khai báo, user-defined function thường được coi là `PARALLEL UNSAFE`.

### 18.1. Chỉ khai báo SAFE khi thực sự an toàn

Function có ghi dữ liệu, thay đổi trạng thái session, dùng sequence hoặc thao tác không an toàn cho parallel workers không nên đánh dấu SAFE để ép tăng tốc.

Ví dụ `line_total` là phép nhân thuần túy nên `PARALLEL SAFE` có thể phù hợp. Function `add_audit_note` có INSERT nên không phù hợp.

### 18.2. Parallel classification độc lập volatility

Một function có thể STABLE nhưng không nhất thiết an toàn chạy trong worker, tùy loại thao tác của nó. Phân loại cần dựa trên hành vi thật, không chỉ tên routine.

## 19. COST và ROWS

PostgreSQL hỗ trợ ước lượng chi phí execution của function:

~~~sql
CREATE FUNCTION routine_lab.double_value(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
COST 1
AS $$
    SELECT p_value * 2;
$$;
~~~

Với set-returning functions, có thể khai báo số hàng ước lượng bằng thuộc tính `ROWS` khi áp dụng.

### 19.1. COST không phải milliseconds

`COST` là thông tin trong mô hình cost của planner, không đại diện chính xác thời gian chạy theo ms. Khai báo quá thấp hoặc quá cao có thể làm kế hoạch kém.

### 19.2. ROWS là ước lượng

Nếu một function thường trả 5 rows nhưng khai báo 10.000, planner có thể ước lượng join sai. Không tùy tiện tối ưu bằng cách gán số tùy ý; đo `EXPLAIN (ANALYZE, BUFFERS)` trên workload thực.

## 20. Cú pháp CREATE PROCEDURE

Một procedure thông thường có dạng:

~~~sql
CREATE [ OR REPLACE ] PROCEDURE schema_name.proc_name(
    [ [ IN | INOUT | OUT ] parameter_name parameter_type, ... ]
)
LANGUAGE language_name
[ procedure_attributes ... ]
AS $procedure_body$
    ...
$procedure_body$;
~~~

Đây là sơ đồ cú pháp, không phải SQL chạy nguyên dạng. Hỗ trợ chi tiết của `OUT` và các tùy chọn có thể phụ thuộc PostgreSQL version.

Khác với function:

- Không viết `RETURNS NUMERIC` hoặc `RETURNS TABLE` ở header.
- Gọi bằng `CALL`.
- Có thể dùng `INOUT`/`OUT` để trả các giá trị output khi phiên bản hỗ trợ.
- Có khả năng điều khiển transaction nhưng chỉ ở những ngữ cảnh nhất định.

## 21. Procedure nghiệp vụ đầu tiên: đổi trạng thái đơn

~~~sql
CREATE PROCEDURE routine_lab.mark_order_paid(
    IN p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE routine_lab.orders AS o
    SET status = 'paid'
    WHERE o.order_id = p_order_id
      AND o.status = 'new';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order % does not exist or is not new',
            p_order_id;
    END IF;

    INSERT INTO routine_lab.audit_log(
        order_id, action
    )
    VALUES (
        p_order_id,
        'marked_paid'
    );
END;
$$;
~~~

Gọi:

~~~sql
CALL routine_lab.mark_order_paid(1002);
~~~

Trong dataset lab ban đầu, order 1002 có `status='new'`, nên procedure:

1. UPDATE thành `paid`.
2. Kiểm tra có hàng bị UPDATE.
3. INSERT audit log.

Nếu gọi lại, điều kiện `status='new'` không còn đúng, nên procedure báo exception. Đây là chính sách **không idempotent bằng cách retry mù quáng**; hệ thống thật phải định nghĩa rõ xử lý retry.

### 21.1. Procedure này không có COMMIT

Mặc dù gọi bằng `CALL`, procedure `mark_order_paid` không tự commit. Nếu client mở transaction, hai DML thuộc transaction đó; caller quyết định COMMIT/ROLLBACK.

### 21.2. Đo tác động bằng transaction lab

Để không giữ trạng thái thay đổi trong ví dụ:

~~~sql
BEGIN;

CALL routine_lab.mark_order_paid(1002);

SELECT
    order_id, status
FROM routine_lab.orders
WHERE order_id = 1002;

ROLLBACK;
~~~

Sau ROLLBACK, status/order audit trở về trạng thái trước transaction. Chỉ thực hiện đúng một lần trên dataset chưa bị thay đổi bởi lần `CALL` trước; nếu đã gọi và commit rồi, reset lab hoặc chọn order tương ứng.

## 22. CALL khác SELECT như thế nào?

Gọi function:

~~~sql
SELECT routine_lab.get_order_total(1001);
~~~

Gọi procedure:

~~~sql
CALL routine_lab.mark_order_paid(1002);
~~~

**Không dùng:**

~~~sql
-- Sai hình dạng lời gọi procedure:
SELECT routine_lab.mark_order_paid(1002);
~~~

và:

~~~sql
-- Sai hình dạng lời gọi function:
CALL routine_lab.get_order_total(1001);
~~~

Tên có thể trùng trong một số tình huống chữ ký khác nhau, nhưng PostgreSQL resolve routine theo loại, tên và argument types. Không dựa vào việc hai câu trên “tự tìm loại phù hợp”.

### 22.1. Procedure không là SQL expression

Không thể viết:

~~~sql
-- Không hợp lệ như biểu thức:
SELECT
    order_id,
    CALL routine_lab.mark_order_paid(order_id)
FROM routine_lab.orders;
~~~

Nếu cần thao tác theo tập hàng, cân nhắc một SQL UPDATE set-based, một procedure thao tác theo điều kiện, hoặc một function phù hợp có side effect được kiểm soát.

## 23. Tham số IN, OUT, INOUT

Thông thường:

- `IN`: dữ liệu từ caller vào routine.
- `OUT`: dữ liệu routine trả cho caller (mức hỗ trợ/cú pháp cần kiểm tra theo phiên bản).
- `INOUT`: nhận input ban đầu và cũng là output parameter.

**Function** có thể dùng `OUT` và `INOUT` theo cú pháp/function return rules; **procedure** cũng hỗ trợ các dạng output parameters thích hợp, nhưng cách gọi qua `CALL` khác cách đọc function result.

### 23.1. Procedure có INOUT trả một kết quả

~~~sql
CREATE PROCEDURE routine_lab.describe_order(
    IN p_order_id BIGINT,
    INOUT p_message TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    SELECT format(
        'Order %s has status %s',
        o.order_id,
        o.status
    )
    INTO p_message
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;

    IF p_message IS NULL THEN
        p_message := format(
            'Order %s not found',
            p_order_id
        );
    END IF;
END;
$$;
~~~

Gọi:

~~~sql
CALL routine_lab.describe_order(1001, NULL);
~~~

Procedure có output parameter nên `CALL` có thể trả **một result row** chứa giá trị `p_message` theo cơ chế output arguments. Điều này **không** tương đương set-returning function trong một SQL JOIN.

### 23.2. Vì sao truyền NULL ở vị trí INOUT?

`INOUT` vẫn nhận một giá trị đầu vào. Ví dụ này không cần nội dung ban đầu nên truyền NULL, rồi procedure gán output.

Với `OUT`-only parameters, cú pháp placeholder và hỗ trợ chi tiết có thể khác theo PostgreSQL version; không sao chép blindly cú pháp procedure từ Oracle/SQL Server.

## 24. Function RETURNS TABLE và procedure OUT: chọn cái nào?

Nếu cần truy vấn kiểu quan hệ:

~~~sql
SELECT *
FROM routine_lab.orders_for_customer(101);
~~~

thì `RETURNS TABLE` của function là lựa chọn tự nhiên.

Nếu cần thực hiện command và trả một mã/kết quả ngắn:

~~~sql
CALL routine_lab.describe_order(1001, NULL);
~~~

thì procedure với `INOUT` có thể phù hợp.

| Nhu cầu | Lựa chọn thường hợp lý |
|---|---|
| JOIN kết quả routine với bảng khác | Function `RETURNS TABLE` |
| Lấy danh sách dữ liệu dưới dạng rows | Function |
| Một phép tính dùng trong WHERE | Function |
| Command đổi trạng thái + audit | Procedure hoặc function VOLATILE, ưu tiên API rõ |
| Một lệnh có thể điều khiển transaction nội bộ | Procedure, nếu ngữ cảnh CALL cho phép |
| Trả một status/message sau command | Procedure INOUT/OUT thích hợp |
| Gọi bằng một expression trong SELECT | Function |

Không chọn procedure chỉ vì nghe “enterprise”; cũng không chọn function vì ngắn hơn mà bỏ qua sự rõ ràng của command semantics.

## 25. Điểm khác biệt lớn nhất: transaction control

**Function không được kết thúc transaction bằng COMMIT/ROLLBACK trong thân function.** Function chạy trong transaction của statement/caller.

**Procedure có thể** thực hiện `COMMIT`/`ROLLBACK` trong **những ngữ cảnh gọi phù hợp**, nhưng không phải mọi lần `CALL` đều được phép.

Điều kiện quan trọng thường gồm:

1. Procedure được gọi bằng **top-level `CALL`** ở ngữ cảnh hỗ trợ transaction control, hoặc chuỗi `CALL`/`DO` lồng nhau phù hợp không có lời gọi SQL khác ngăn cách theo quy tắc.
2. Lời gọi không nằm bên trong một **explicit transaction block** mà transaction control của procedure bị cấm.
3. Procedure không thuộc dạng `SECURITY DEFINER`.
4. Procedure không có clause `SET` gắn với định nghĩa làm cấm transaction control.
5. Không cố `COMMIT` trong block có `EXCEPTION` đang dùng subtransaction.
6. Session/client/driver không tự bọc `CALL` bằng transaction cấm thao tác này.

Đây là lý do “procedure luôn được COMMIT bên trong” là nhận định sai.

## 26. BEGIN trong PL/pgSQL không mở transaction

Ví dụ:

~~~sql
CREATE PROCEDURE routine_lab.noop()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Hello';
END;
$$;
~~~

`BEGIN ... END` ở đây là **khối lập trình PL/pgSQL**; không tương đương:

~~~sql
BEGIN;
...
COMMIT;
~~~

của SQL transaction.

Trong PL/pgSQL, không dùng `BEGIN;` để “bắt đầu giao dịch lồng nhau” theo cách các hệ quản trị khác có thể cho phép. PostgreSQL không hỗ trợ nested transactions độc lập kiểu đó; block có exception tạo subtransaction với semantics riêng.

## 27. Procedure có COMMIT hợp lệ trong lab

Tạo một procedure chèn audit theo từng batch và commit giữa các batch:

~~~sql
CREATE PROCEDURE routine_lab.write_audit_batches(
    IN p_batch_size INTEGER,
    IN p_batch_count INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_batch INTEGER;
BEGIN
    IF p_batch_size <= 0
       OR p_batch_count <= 0
       OR p_batch_size > 100
       OR p_batch_count > 10
    THEN
        RAISE EXCEPTION
            'Invalid demo batch size or count';
    END IF;

    FOR v_batch IN 1..p_batch_count LOOP
        INSERT INTO routine_lab.audit_log(
            order_id, action
        )
        SELECT
            1001,
            format(
                'demo_batch_%s_item_%s',
                v_batch,
                g.item_no
            )
        FROM generate_series(
            1, p_batch_size
        ) AS g(item_no);

        COMMIT;
    END LOOP;
END;
$$;
~~~

**Gọi ở top-level với autocommit phù hợp, không bọc BEGIN:**

~~~sql
CALL routine_lab.write_audit_batches(2, 2);
~~~

Mỗi batch của ví dụ chèn 2 audit rows; có 2 batches. `COMMIT` kết thúc transaction hiện tại và PostgreSQL bắt đầu transaction mới theo quy tắc của procedure transaction control.

### 27.1. Gọi bên trong explicit transaction block sẽ lỗi

Không dùng:

~~~sql
-- Minh họa tình huống transaction control bị cấm:
BEGIN;

CALL routine_lab.write_audit_batches(2, 2);

COMMIT;
~~~

Với procedure có `COMMIT`, lời gọi này sẽ gặp lỗi transaction control trong ngữ cảnh explicit transaction block. Nếu client/framework luôn bắt đầu transaction trước `CALL`, cần thiết kế lại routine boundary.

### 27.2. Commit từng batch có hệ quả

Nếu batch 1 đã COMMIT và batch 2 gặp lỗi, batch 1 **không tự rollback**. Vì vậy:

- Thiết kế idempotency/checkpoint.
- Định nghĩa retry có thể an toàn.
- Không coi toàn bộ procedure batch là atomic.
- Cân nhắc khả năng phục hồi dữ liệu giữa các batches.

Đó là khác biệt đáng kể với procedure không tự COMMIT.

## 28. CALL lồng nhau và giới hạn transaction control

PostgreSQL có thể cho phép transaction control qua chuỗi call phù hợp:

~~~text
CALL proc_outer()
    |
    +--> CALL proc_inner()
              |
              +--> COMMIT
~~~

Tuy nhiên nếu call stack có một lời gọi khác, chẳng hạn `SELECT function()`, nằm giữa những `CALL` theo quy tắc cấm của PostgreSQL, procedure sâu bên trong có thể không được transaction control.

Ngoài ra:

- `SECURITY DEFINER PROCEDURE` không được điều khiển transaction.
- Procedure có clause `SET` trong định nghĩa không được điều khiển transaction.
- Không kết thúc transaction trong một exception-handling block đang là subtransaction.
- Explicit transaction block của caller vẫn là giới hạn quan trọng.

**Không thiết kế cấu trúc nested CALL phức tạp chỉ để lách transaction restrictions**. Nên chọn rõ một đơn vị commit ở application hoặc một procedure top-level đủ đơn giản và kiểm thử trên phiên bản server mục tiêu.

## 29. Procedure không có COMMIT vẫn dùng được trong transaction ứng dụng

Procedure `mark_order_paid` không điều khiển transaction nội bộ. Vì vậy client có thể:

~~~sql
BEGIN;

CALL routine_lab.mark_order_paid(1002);

-- Có thể chạy SELECT/kiểm tra các thay đổi
-- trong cùng transaction.

COMMIT;
~~~

Với transaction này, cả UPDATE và INSERT audit thuộc một đơn vị atomic.

Nếu exception xảy ra và transaction bị lỗi, caller cần xử lý rollback hoặc savepoint thích hợp.

### 29.1. Tiêu chí chọn commit boundary

Hỏi trước khi viết procedure:

- Cần **atomicity toàn bộ command** hay commit từng batch?
- Ai có đủ thông tin để quyết định commit: DB procedure hay service orchestration?
- Có cần phối hợp nhiều SQL/HTTP side effects ở tầng ứng dụng?
- Client có dùng `@Transactional` hoặc JDBC `setAutoCommit(false)`?
- Có logic retry/compensation khi một phần đã commit?

Trong nhiều ứng dụng Java, **để service quản lý transaction** và procedure không tự COMMIT là lựa chọn dễ tích hợp hơn.

## 30. Vì sao function không tự COMMIT?

Một function có thể được gọi từ:

~~~sql
SELECT
    routine_lab.get_order_total(o.order_id)
FROM routine_lab.orders AS o;
~~~

Một statement duy nhất có thể gọi function nhiều lần khi đánh giá từng row. Nếu mỗi lời gọi tùy ý commit, tính atomicity của statement/transaction sẽ bị phá vỡ.

PostgreSQL không cho function thực hiện transaction-ending commands theo cơ chế này. Muốn chia commit thành batches phải thiết kế bên ngoài statement hoặc procedure top-level trong các điều kiện cho phép.

### 30.1. Function gây side effect vẫn nằm trong transaction caller

Nếu function `add_audit_note` được gọi rồi caller ROLLBACK, hàng audit INSERT trong function cũng bị rollback như DML thông thường. Điều này khác procedure dùng COMMIT từng batch ở ví dụ trên.

## 31. EXCEPTION trong PL/pgSQL

Cả function và procedure viết bằng PL/pgSQL đều có thể xử lý exception:

~~~sql
CREATE FUNCTION routine_lab.try_read_order(
    p_order_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT o.status
    INTO STRICT v_status
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;

    RETURN v_status;

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN 'not_found';
END;
$$;
~~~

Ở PL/pgSQL, `SELECT INTO STRICT` đòi đúng một row; nếu không có row, phát sinh `NO_DATA_FOUND`. Nếu nhiều hơn một row (không thể với PK trong ví dụ), có thể phát sinh `TOO_MANY_ROWS`.

### 31.1. Exception block có subtransaction semantics

Các thay đổi persistent database bên trong block có xử lý `EXCEPTION` có thể bị rollback về trạng thái đầu block khi exception được bắt, theo cơ chế subtransaction. Các biến PL/pgSQL có quy tắc riêng.

### 31.2. Không COMMIT trong block có EXCEPTION

Không chèn `COMMIT` vào một block đang xử lý exception rồi mong PostgreSQL cho kết thúc transaction. Hành vi này bị giới hạn bởi subtransaction.

### 31.3. Không nuốt mọi lỗi

~~~sql
EXCEPTION WHEN OTHERS THEN
    RETURN 'ok';
~~~

là anti-pattern nếu làm mất lỗi constraint, permission hoặc dữ liệu sai. Chỉ bắt những lỗi có chính sách xử lý rõ và giữ đủ thông tin phục vụ điều tra.

## 32. RAISE EXCEPTION và SQLSTATE

Routine có thể báo lỗi nghiệp vụ bằng:

~~~sql
RAISE EXCEPTION
    'Order % cannot be processed',
    p_order_id;
~~~

Hoặc với SQLSTATE tùy chỉnh hợp lệ theo quy tắc PostgreSQL:

~~~sql
RAISE EXCEPTION
    USING
        ERRCODE = 'P0001',
        MESSAGE = 'Business validation failed';
~~~

Tầng JDBC nhận `SQLException` với SQLSTATE. Việc dùng code nhất quán giúp application phân biệt business failure với lỗi kết nối/constraint.

### 32.1. Không đưa dữ liệu bí mật vào exception text

Thông báo lỗi có thể xuất hiện trong log, traces hoặc API response. Không in token, secrets, thông tin khách hàng nhạy cảm hoặc toàn bộ payload vào exception nếu không cần thiết.

## 33. SECURITY INVOKER và SECURITY DEFINER

Một routine có thể thực thi theo hai kiểu đặc quyền:

- `SECURITY INVOKER`: dùng đặc quyền của người gọi trong những kiểm tra liên quan. Đây là mặc định đối với functions phù hợp.
- `SECURITY DEFINER`: routine chạy với đặc quyền của owner trong cơ chế liên quan.

Ví dụ hàm chỉ đọc status theo quyền owner:

~~~sql
CREATE FUNCTION routine_lab.get_status_for_api(
    p_order_id BIGINT
)
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = routine_lab, pg_temp
AS $$
    SELECT o.status
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;
$$;
~~~

Đây là mẫu minh họa cơ chế. Không tự cấp quyền EXECUTE cho người dùng chưa được xác thực/chưa có authorization policy.

### 33.1. SECURITY DEFINER không phải mặc định tốt hơn

Nó có thể cho caller truy cập dữ liệu thông qua routine mà caller không có quyền SELECT trực tiếp. Điều đó hữu ích trong một API database được thiết kế chặt, nhưng cũng tạo nguy cơ **leo thang đặc quyền** nếu routine không kiểm tra input, tenant ownership và đường truy cập.

### 33.2. SECURITY DEFINER procedure không được transaction control

Nếu procedure được khai báo `SECURITY DEFINER`, không được dùng `COMMIT`/`ROLLBACK` bên trong. Đừng chọn security definer đồng thời kỳ vọng procedure tự chia commit batches.

## 34. search_path là vấn đề bảo mật

Một function `SECURITY DEFINER` có thể bị khai thác nếu dùng tên bảng/function không schema-qualified và `search_path` chứa schema nơi user ít quyền có thể tạo object.

Biện pháp thực hành:

1. Dùng tên đối tượng đầy đủ `routine_lab.orders` trong thân routine.
2. Đặt `SET search_path` chỉ gồm những schema tin cậy, với `pg_temp` ở vị trí phù hợp (thường cuối).
3. Không đưa schema cho user không tin cậy tạo object vào search_path.
4. Hạn chế `EXECUTE` với role cần thiết.
5. Không ghép identifier từ input không đáng tin cậy.

Một routine chạy bằng quyền owner có thể chạm dữ liệu nhạy cảm; vì vậy cả **định nghĩa SQL** lẫn **quyền tạo object của schema** đều cần được xem xét.

## 35. EXECUTE privilege và quyền mặc định

Đối với function/procedure mới, PostgreSQL có những **default privileges**, trong đó quyền `EXECUTE` thường được cấp cho `PUBLIC` theo mặc định nếu không được điều chỉnh.

Với routine nhạy cảm, tạo và điều chỉnh quyền trong **cùng transaction** để tránh một khoảng thời gian routine có thể được gọi bởi role không mong muốn:

~~~sql
BEGIN;

CREATE FUNCTION routine_lab.private_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT total_amount
    FROM routine_lab.orders
    WHERE order_id = p_order_id;
$$;

REVOKE ALL
ON FUNCTION routine_lab.private_order_total(BIGINT)
FROM PUBLIC;

-- Chỉ thực hiện nếu app_reader là role đã được tạo
-- và thật sự được phép gọi routine:
-- GRANT EXECUTE
-- ON FUNCTION routine_lab.private_order_total(BIGINT)
-- TO app_reader;

COMMIT;
~~~

### 35.1. EXECUTE privilege không phải toàn bộ authorization

Nếu function SECURITY DEFINER trả tổng tiền theo `order_id`, cần kiểm tra liệu caller được phép xem đơn hàng đó không. Chỉ grant EXECUTE không tự thực hiện tenant scoping.

### 35.2. ALTER DEFAULT PRIVILEGES

Với hệ thống có nhiều routines, DBA có thể thiết lập default privileges phù hợp cho routines do một role/schema tạo. Vì default privileges phụ thuộc role tạo và phạm vi, cần đánh giá kỹ quy trình migration trước khi thay đổi.

## 36. Dynamic SQL và SQL injection

PL/pgSQL có `EXECUTE` để chạy SQL động. Nó khác với `CALL` procedure ở SQL client.

**Không an toàn:**

~~~sql
-- Minh họa kiểu nối chuỗi cần tránh:
-- EXECUTE 'SELECT count(*) FROM ' || input_table;
~~~

Nếu tên bảng được lấy từ nguồn không tin cậy, việc nối chuỗi có thể tạo SQL injection hoặc tham chiếu sai đối tượng.

### 36.1. Quoting identifier và bind values

Ví dụ function có quyền invoker:

~~~sql
CREATE FUNCTION routine_lab.count_by_status(
    p_schema NAME,
    p_table NAME,
    p_status TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    EXECUTE format(
        'SELECT count(*) FROM %I.%I WHERE status = $1',
        p_schema,
        p_table
    )
    INTO v_count
    USING p_status;

    RETURN v_count;
END;
$$;
~~~

- `format('%I', ...)` quote identifier theo cú pháp PostgreSQL.
- `USING` truyền giá trị query như parameter, không tự ghép literal.
- Role gọi vẫn cần quyền đọc bảng tương ứng vì dùng `SECURITY INVOKER`.
- Ví dụ giả định bảng được chọn có cột `status` phù hợp.

### 36.2. Quoting không thay authorization

Dù tên bảng được quote an toàn, ứng dụng vẫn nên whitelist schema/table cho use case cụ thể. SECURITY DEFINER với dynamic SQL không kiểm soát đối tượng đích là một rủi ro lớn.

## 37. Function overloading

PostgreSQL có thể có nhiều functions **cùng tên** nhưng khác danh sách input argument types:

~~~sql
CREATE FUNCTION routine_lab.show_value(
    p_value INTEGER
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer:' || p_value::TEXT;
$$;

CREATE FUNCTION routine_lab.show_value(
    p_value TEXT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text:' || p_value;
$$;
~~~

Gọi:

~~~sql
SELECT routine_lab.show_value(10::INTEGER);
SELECT routine_lab.show_value('10'::TEXT);
~~~

PostgreSQL dùng tên và kiểu tham số để resolve overload phù hợp.

### 37.1. Output type không phải cách overload riêng

Không thể định nghĩa hai functions khác nhau chỉ bởi `RETURNS TEXT` so với `RETURNS INTEGER` trong khi danh sách input types giống nhau.

### 37.2. Unknown literal có thể gây bất ngờ

Literal `'10'` chưa cast rõ có thể được suy kiểu theo quy tắc resolve. Khi có overload, nên cast rõ:

~~~sql
SELECT routine_lab.show_value('10'::TEXT);
~~~

### 37.3. Procedure cũng có overload

Các nguyên tắc identity/argument types áp dụng với routine procedures theo quy tắc PostgreSQL. Khi làm migration/drop, phải chỉ rõ chữ ký để tránh tác động sai overload.

## 38. CREATE OR REPLACE FUNCTION

Khi cần sửa logic nhưng giữ interface tương thích:

~~~sql
CREATE OR REPLACE FUNCTION routine_lab.get_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        (
            SELECT o.total_amount
            FROM routine_lab.orders AS o
            WHERE o.order_id = p_order_id
        ),
        0::NUMERIC
    );
$$;
~~~

Ví dụ trên thay semantics: order không tồn tại trước đây trả NULL, giờ trả 0. Đây là thay đổi nghiệp vụ phải được đánh giá, dù cú pháp `OR REPLACE` được PostgreSQL chấp nhận.

### 38.1. Giới hạn OR REPLACE FUNCTION

Thông thường không dùng `CREATE OR REPLACE FUNCTION` để **đổi return type** của một existing function identity. Cũng cần tuân thủ ràng buộc về tham số đầu vào và tên các tham số đã công bố.

Để thay interface không tương thích, cân nhắc:

- Tạo function mới có tên/chữ ký khác.
- Migrate callers.
- Xóa function cũ khi không còn phụ thuộc.

### 38.2. OR REPLACE không tự làm semantic versioning

Cùng tên và return type không bảo đảm output vẫn có cùng nghĩa. Cần test chức năng, quyền, side effects, performance và expected errors.

## 39. CREATE OR REPLACE PROCEDURE

Thay nội dung procedure giữ chữ ký thích hợp:

~~~sql
CREATE OR REPLACE PROCEDURE routine_lab.mark_order_paid(
    IN p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE routine_lab.orders AS o
    SET status = 'paid'
    WHERE o.order_id = p_order_id
      AND o.status = 'new';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order % is not eligible for payment',
            p_order_id;
    END IF;

    INSERT INTO routine_lab.audit_log(
        order_id, action
    )
    VALUES (p_order_id, 'paid_v2');
END;
$$;
~~~

Kết quả là logic command thay đổi; application gọi `CALL routine_lab.mark_order_paid(...)` vẫn có cùng hình dạng.

### 39.1. Không xem OR REPLACE là cách sửa mọi signature

Thay đổi modes, kiểu hoặc cấu trúc parameters có thể đòi routine identity mới hay migration riêng. Kiểm tra cụ thể phiên bản PostgreSQL và caller interface.

### 39.2. Không âm thầm thêm COMMIT vào procedure đang được gọi trong transaction

Một procedure trước đó không tự COMMIT có thể đang được ứng dụng gọi trong `@Transactional`. Nếu OR REPLACE thêm `COMMIT`, lời gọi có thể bắt đầu lỗi hoặc làm thay đổi atomicity. Đó là **breaking behavioral change** dù tên/chữ ký không đổi.

## 40. Identity signature và DROP FUNCTION/PROCEDURE

Khi có overload, muốn xóa đúng routine phải chỉ rõ input signature.

~~~sql
DROP FUNCTION routine_lab.show_value(INTEGER);
~~~

~~~sql
DROP FUNCTION routine_lab.show_value(TEXT);
~~~

Đối với procedure:

~~~sql
DROP PROCEDURE routine_lab.mark_order_paid(BIGINT);
~~~

**Lưu ý:** ví dụ DROP này sẽ xóa routine lab đã tạo; chỉ chạy khi đang chủ động cleanup.

### 40.1. RESTRICT và CASCADE

~~~sql
DROP FUNCTION routine_lab.get_order_total(BIGINT) RESTRICT;
~~~

PostgreSQL mặc định bảo vệ dependent database objects theo hành vi RESTRICT nếu có. `CASCADE` có thể xóa objects phụ thuộc mà PostgreSQL theo dõi.

Không bật CASCADE chỉ vì DROP báo lỗi dependency. Cần kiểm tra object liên quan và consumer bên ngoài database.

### 40.2. DROP PROCEDURE không xóa dữ liệu đã được ghi trước đó

Nếu procedure từng INSERT audit rows và COMMIT, DROP PROCEDURE chỉ xóa định nghĩa routine. Dữ liệu đã được commit không tự biến mất.

## 41. RENAME và ALTER routine

PostgreSQL có DDL để thay metadata hoặc thuộc tính của routine:

~~~sql
ALTER FUNCTION routine_lab.order_category(BIGINT)
RENAME TO classify_order;
~~~

~~~sql
ALTER PROCEDURE routine_lab.mark_order_paid(BIGINT)
RENAME TO mark_order_paid_command;
~~~

Các lệnh trên là **thao tác thay tên thật**; caller còn dùng tên cũ có thể lỗi.

### 41.1. SET SCHEMA và OWNER

Các dạng `ALTER FUNCTION ... SET SCHEMA ...`, `ALTER PROCEDURE ... SET SCHEMA ...`, `OWNER TO ...` được hỗ trợ theo điều kiện quyền/phiên bản.

Không di chuyển routine giữa schemas hoặc thay owner mà chưa kiểm tra:

- Các callers sử dụng tên đầy đủ.
- Grants và execution rights.
- SECURITY DEFINER behavior.
- `search_path` và referenced objects.
- Dynamic SQL strings và code ngoài database.

## 42. Xem routines qua pg_proc

PostgreSQL lưu metadata của functions/procedures trong `pg_proc`, liên kết schema ở `pg_namespace`.

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_function_identity_arguments(
        p.oid
    ) AS identity_arguments,
    pg_get_function_result(
        p.oid
    ) AS result_description
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'routine_lab'
ORDER BY p.proname, identity_arguments;
~~~

`prokind` thường phân biệt:

- `f`: normal function.
- `p`: procedure.
- `a`: aggregate.
- `w`: window function.

`pg_get_function_identity_arguments` trả danh sách dùng xác định identity cho DROP/ALTER theo kiểu routine, không phải toàn bộ default-value semantics.

### 42.1. Xem định nghĩa routine

Với signature cụ thể:

~~~sql
SELECT pg_get_functiondef(
    'routine_lab.get_order_total(bigint)'::regprocedure
);
~~~

`pg_get_functiondef` cũng có thể dựng định nghĩa cho procedure khi truyền đúng OID tương ứng.

### 42.2. Trong psql

~~~text
\df+ routine_lab.*
\dfp routine_lab.*
~~~

Các lệnh `\df` và biến thể type filter giúp liệt kê routines. Đây là psql meta-commands, không phải SQL để gửi trực tiếp qua JDBC.

## 43. information_schema.routines

Khi cần metadata tương đối chuẩn:

~~~sql
SELECT
    routine_schema,
    routine_name,
    routine_type,
    data_type
FROM information_schema.routines
WHERE routine_schema = 'routine_lab'
ORDER BY routine_name;
~~~

`information_schema` có visibility theo quyền, nên role khác nhau có thể thấy thông tin khác nhau.

Khi cần PostgreSQL-specific attributes như volatility, security, prokind và parallel safety, `pg_proc` thường phong phú hơn.

## 44. Kiểm tra volatility, security và parallel flags

~~~sql
SELECT
    n.nspname AS routine_schema,
    p.proname AS routine_name,
    p.prokind,
    p.provolatile,
    p.proparallel,
    p.prosecdef,
    p.proisstrict,
    p.procost,
    p.prorows
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'routine_lab'
ORDER BY p.proname;
~~~

Một số mã có ý nghĩa:

- `provolatile`: `i` immutable, `s` stable, `v` volatile.
- `proparallel`: `s` safe, `r` restricted, `u` unsafe.
- `prosecdef`: true khi SECURITY DEFINER.
- `proisstrict`: true khi STRICT.

Đây là metadata đã khai báo, không phải bằng chứng tự động rằng code bên trong routine thực sự tuân thủ contract. Tác giả phải khai báo chính xác.

## 45. Function/procedure và execution plan

Một function SQL đơn giản có thể được PostgreSQL tối ưu/inlined trong những trường hợp đáp ứng điều kiện, nhưng điều đó **không được bảo đảm** cho mọi SQL function.

Một function PL/pgSQL có thể gọi nhiều SQL statements nội bộ; nhìn `EXPLAIN` của một lời gọi bên ngoài có thể không hiện chi tiết mọi internal SQL node theo cách mong đợi.

### 45.1. Đo một function trên nhiều hàng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    routine_lab.get_order_total(o.order_id)
FROM routine_lab.orders AS o;
~~~

Đây là demo bảng nhỏ. Nếu function thực thi một SELECT cho mỗi row khi không được inlined/optimized, workload lớn có thể phát sinh overhead tương tự kiểu xử lý lặp.

### 45.2. Ưu tiên SQL set-based khi có thể

Thay vì gọi 100.000 lần function làm từng SELECT, đôi khi một JOIN đơn giản hiệu quả hơn:

~~~sql
SELECT
    o.order_id,
    o.total_amount
FROM routine_lab.orders AS o;
~~~

Không nhất thiết function kém trong mọi trường hợp; cách đúng là đo `EXPLAIN (ANALYZE, BUFFERS)` và latency với dataset đại diện.

### 45.3. Không tối ưu bằng cách khai báo sai volatility

Một planner có thể tối ưu aggressive hơn nếu thấy IMMUTABLE, nhưng gắn sai thuộc tính khiến kết quả sai. Tính đúng luôn đứng trước micro-optimization.

## 46. Nhiều SQL statements trong procedure

Một procedure thường phù hợp khi mô tả command có các bước liên tiếp:

~~~text
CALL business_command(...)
    |
    +--> Validate input
    +--> UPDATE state
    +--> INSERT audit
    +--> Kiểm tra rows affected
    +--> Trả status qua OUT/INOUT nếu cần
~~~

Nhưng việc dùng PL/pgSQL loop để xử lý từng hàng **không tự nhanh hơn** một `UPDATE ... WHERE ...` hoặc `INSERT ... SELECT ...` set-based.

### 46.1. Tránh row-by-row không cần thiết

Nếu cần đổi status cho tất cả đơn `new`:

~~~sql
UPDATE routine_lab.orders
SET status = 'paid'
WHERE status = 'new';
~~~

là một thao tác set-based. Viết procedure LOOP qua từng order và UPDATE từng hàng có thể tăng overhead, lock complexity và thời gian chạy.

Procedure là phương tiện đóng gói logic, **không phải giấy phép thay SQL set-based bằng vòng lặp vô hạn**.

## 47. JDBC: gọi function lấy scalar

Java với `PreparedStatement`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderLookup {
    public BigDecimal getOrderTotal(
        Connection connection,
        long orderId
    ) throws SQLException {
        String sql =
            "SELECT routine_lab.get_order_total(?)";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, orderId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Function returned no result row"
                    );
                }
                return rs.getBigDecimal(1);
            }
        }
    }
}
~~~

Khi không tìm thấy order, `get_order_total` có thể trả SQL NULL, nên `getBigDecimal(1)` trả null. Application phải quyết định xử lý dữ liệu vắng mặt, không tự coi null là 0 nếu không có contract.

### 47.1. Parameter binding

Dùng `?` để truyền value, không ghép `orderId` thành raw SQL string. Bind parameter làm code dễ bảo trì và tránh SQL injection từ giá trị.

## 48. JDBC: gọi set-returning function

~~~java
String sql = """
    SELECT order_id, status, total_amount
    FROM routine_lab.orders_for_customer(?)
    ORDER BY order_id
    """;

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            String status = rs.getString("status");
            java.math.BigDecimal amount =
                rs.getBigDecimal("total_amount");

            // Dùng typed rows theo nhu cầu.
        }
    }
}
~~~

Set-returning function là một relation, nên có thể lọc, JOIN, ORDER BY và lấy ResultSet như SELECT thông thường.

## 49. JDBC: gọi procedure bằng CALL

Một procedure không tự COMMIT có thể được gọi trực tiếp:

~~~java
String sql = "CALL routine_lab.mark_order_paid(?)";

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setLong(1, 1002L);
    ps.execute();
}
~~~

Với procedure có output parameters, có thể dùng `CallableStatement` hoặc cơ chế result handling tương ứng của driver, nhưng phải xác minh `CALL` syntax và behavior của phiên bản pgJDBC.

### 49.1. JDBC escape syntax không phải luôn CALL

Một số driver hỗ trợ cú pháp JDBC kiểu `{call routine(...)}`, có thể chuyển thành `SELECT` hoặc `CALL` tùy cấu hình như `escapeSyntaxCallMode` và loại routine. Tránh dựa vào kinh nghiệm của database khác.

Nếu đang gọi PostgreSQL procedure, dùng câu SQL `CALL routine_name(?)` rõ ràng qua PreparedStatement khi phù hợp; với function dùng `SELECT f(?)`. Khi dùng CallableStatement, kiểm tra tài liệu phiên bản driver và test thực tế.

## 50. JDBC autocommit và procedure có COMMIT

Với procedure `write_audit_batches` có `COMMIT` nội bộ:

- Lời gọi nên là **top-level CALL** được server cho transaction control.
- JDBC session phải không ở trạng thái explicit transaction block cấm procedure COMMIT; trong nhiều trường hợp cần autocommit true.
- Framework transaction management như Spring `@Transactional` có thể mở transaction trước lời gọi, làm procedure chứa COMMIT bị lỗi.
- Nếu app cần phối hợp nhiều thao tác atomic, tốt hơn là caller quản lý COMMIT và procedure **không tự commit**.

Ví dụ minh họa ý tưởng:

~~~java
boolean originalAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(true);

    try (PreparedStatement ps = connection.prepareStatement(
        "CALL routine_lab.write_audit_batches(?, ?)"
    )) {
        ps.setInt(1, 2);
        ps.setInt(2, 2);
        ps.execute();
    }
} finally {
    connection.setAutoCommit(originalAutoCommit);
}
~~~

**Chỉ dùng đoạn code này trong demo cô lập.** Đổi autocommit trên connection có thể ảnh hưởng transaction đang mở và trạng thái pool; trong ứng dụng thực nên lấy một connection được quản lý dành riêng cho operation có transaction control, không tự đổi mode trên connection đang tham gia transaction của request.

## 51. Spring @Transactional và routine

Các trường hợp:

**Function được gọi qua SELECT:**

~~~text
@Transactional service
    |
    +--> SELECT function(...)
    +--> UPDATE other_table
    +--> COMMIT/ROLLBACK do service quyết định
~~~

**Procedure không tự COMMIT:**

~~~text
@Transactional service
    |
    +--> CALL proc_no_commit(...)
    +--> SQL khác
    +--> COMMIT/ROLLBACK do service quyết định
~~~

**Procedure có COMMIT nội bộ:**

~~~text
@Transactional service
    |
    +--> CALL proc_with_commit(...)
             |
             +--> COMMIT bên trong
                   ^
                   Không hợp lệ trong ngữ cảnh
                   explicit transaction block bị cấm
~~~

### 51.1. Một API transaction boundary lành mạnh

Nếu nghiệp vụ cần atomicity qua nhiều repository calls và một database routine, thường cho tầng service định nghĩa transaction và routine **không tự COMMIT**.

Procedure có internal commits phù hợp hơn với một số tác vụ admin/batch độc lập, nơi partial commit được chấp nhận và đã thiết kế retry/checkpoint.

## 52. Khi nào cần SQL, khi nào cần PL/pgSQL?

| Tình huống | Ngôn ngữ thường phù hợp |
|---|---|
| Một biểu thức tính toán | `LANGUAGE sql` |
| Một truy vấn SELECT cố định | `LANGUAGE sql` |
| Trả tập rows từ một SELECT | `LANGUAGE sql` |
| Có IF/LOOP/biến/RAISE/exception | `LANGUAGE plpgsql` |
| Command nhiều DML có validation | `LANGUAGE plpgsql` |
| Logic set-based phức tạp nhưng một query | Thử SQL thuần trước |
| Dynamic SQL có identifier động | PL/pgSQL `EXECUTE format(...) USING ...` |

PL/pgSQL có lợi cho luồng điều khiển, nhưng không phải công cụ tối ưu tự động. Khi SQL thuần đơn giản và rõ ràng, thường nên ưu tiên nó.

## 53. Tiêu chí chọn FUNCTION hay PROCEDURE

Bắt đầu từ **hợp đồng sử dụng**, không phải tên nghiệp vụ.

| Câu hỏi | Nếu “Có” | Lựa chọn nghiêng về |
|---|---|---|
| Kết quả cần nằm trong SELECT/WHERE/ORDER BY? | Là expression | Function |
| Cần RETURN một scalar hoặc JSONB object? | Dễ dùng trong query | Function |
| Cần trả nhiều typed rows để JOIN? | Set-returning | Function |
| Routine chủ yếu là command gây side effect? | Dùng CALL rõ nghĩa | Procedure |
| Cần COMMIT từng batch bên trong routine? | Chỉ khi top-level CALL cho phép | Procedure |
| Transaction do Spring/JDBC service quản lý? | Routine không tự kết thúc giao dịch | Cả hai; thường procedure command |
| Cần đọc bảng và trả giá trị? | STABLE/appropriate SQL function | Function |
| Cần xử lý validation nhiều bước? | PL/pgSQL | Function hoặc procedure tùy interface |
| Cần trigger hook? | Trigger function đặc biệt | Function RETURNS trigger |
| Cần SQL composition/LATERAL? | Phải là relation/expression | Function |

### 53.1. Nếu cả hai đều làm được DML

Ưu tiên procedure nếu API được thiết kế là **một hành động**: trả hàng, duyệt giao dịch, đổi trạng thái và audit.

Function VOLATILE vẫn có chỗ đứng nếu cần trả giá trị tạo mới qua SELECT trong một transaction và mọi caller hiểu side effects. Không dùng nó như một công thức “không side effects” trong query tổng hợp.

### 53.2. Nếu chỉ muốn giảm network round trips

Cả function và procedure đều có thể đóng gói nhiều công việc server-side. Chọn theo return/call semantics và transaction, không chỉ vì ít round trips.

## 54. Sơ đồ quyết định

~~~text
Có cần routine được gọi trong SQL expression,
WHERE, JOIN hoặc SELECT FROM không?
             |
         +---+---+
         |       |
        Có      Không
         |       |
      FUNCTION   Chủ yếu là command có side effect?
                  |
              +---+---+
              |       |
             Có      Không
              |       |
          PROCEDURE  Có thể vẫn dùng FUNCTION
              |
      Cần tự COMMIT/ROLLBACK?
              |
          +---+---+
          |       |
         Có      Không
          |       |
   Kiểm tra top-level CALL,
   SECURITY DEFINER/SET,
   exception và client transaction
          |
   Nếu không đáp ứng điều kiện:
   chuyển commit boundary
   về phía caller hoặc thiết kế lại
~~~

Nếu function làm tính toán thuần túy, có thể khai báo IMMUTABLE/STRICT/PARALLEL SAFE **chỉ khi các thuộc tính thật sự chính xác**.

## 55. Anti-pattern: routine quá nhiều trách nhiệm

Một procedure có thể dần phát triển thành:

~~~text
CALL everything(...)
  +--> xác thực người dùng
  +--> gọi service bên ngoài
  +--> ghi 15 bảng
  +--> tạo hóa đơn
  +--> gửi email
  +--> tính ML
  +--> log mọi sự kiện
~~~

Một phần logic này có thể không thuộc phạm vi database transaction hoặc yêu cầu network/service orchestration.

Những dấu hiệu cần tách:

- Procedure gọi nhiều hệ thống ngoài DB không thể rollback cùng nhau.
- Khó kiểm thử độc lập.
- Có nhiều nhánh permission/tenant logic.
- Người vận hành không hiểu commit boundary.
- Mọi schema change làm procedure rất lớn phải thay.
- Tác vụ lâu dài giữ locks/transactions quá lâu.

Một thiết kế tốt chia **transactional database invariants** và **orchestration ở application** một cách rõ ràng.

## 56. Anti-pattern: dùng procedure cho một SELECT đơn

Thay vì:

~~~sql
CREATE PROCEDURE routine_lab.some_lookup(...)
...
~~~

rồi cố tìm cách nhận dataset qua OUT/cursor chỉ để lấy danh sách khách hàng, hãy cân nhắc:

~~~sql
CREATE FUNCTION routine_lab.customer_names()
RETURNS TABLE (
    customer_id BIGINT,
    customer_name TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT c.customer_id, c.customer_name
    FROM routine_lab.customers AS c;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM routine_lab.customer_names()
ORDER BY customer_id;
~~~

Nếu không cần dùng lại logic hoặc abstraction quyền, một SELECT trực tiếp cũng có thể đơn giản hơn function.

## 57. Anti-pattern: routine tạo SQL injection

Các ví dụ cần tránh:

- Nối tên bảng raw từ user vào EXECUTE.
- Nối payload thành SQL string thay vì parameter binding.
- SECURITY DEFINER với search_path không đáng tin.
- GRANT EXECUTE trên function nhạy cảm cho PUBLIC không có kiểm soát.
- Tin `customer_id` từ client là bằng chứng quyền sở hữu.

Thay bằng:

1. Prepared statements ở Java.
2. `EXECUTE format('%I',...) USING ...` khi dynamic SQL thật sự cần.
3. Whitelist identifiers.
4. Schema qualification.
5. SECURITY INVOKER khi không cần đặc quyền tăng thêm.
6. Auth/tenant scoping được kiểm thử.
7. Giới hạn quyền EXECUTE theo role.

## 58. Anti-pattern: function gọi trong WHERE gây N+1 queries

Ví dụ:

~~~sql
SELECT o.order_id
FROM routine_lab.orders AS o
WHERE routine_lab.get_order_total(
    o.order_id
) > 100000;
~~~

Nếu planner không inline/collapse thích hợp, function có thể thực thi truy vấn nội bộ cho từng row.

Trong trường hợp dữ liệu đã nằm ở `orders`, câu SQL thường đơn giản hơn:

~~~sql
SELECT o.order_id
FROM routine_lab.orders AS o
WHERE o.total_amount > 100000;
~~~

Bài học không phải “function lúc nào cũng chậm”, mà là **đừng che logic truy cập bảng trong function rồi bỏ qua EXPLAIN và số lần gọi**.

## 59. Test routine: tính đúng, lỗi và transaction

Đối với function scalar:

~~~sql
SELECT
    routine_lab.line_total(100, 2) = 200
        AS positive_case,
    routine_lab.line_total(100, NULL) IS NULL
        AS strict_null_case;
~~~

Đối với function đọc bảng:

~~~sql
SELECT
    routine_lab.get_order_total(1001)
        AS actual_amount;
~~~

Đối với function trả hàng:

~~~sql
SELECT COUNT(*)
FROM routine_lab.orders_for_customer(101);
~~~

Đối với procedure không tự COMMIT, test trong transaction lab:

~~~sql
BEGIN;

CALL routine_lab.mark_order_paid(1002);

SELECT status
FROM routine_lab.orders
WHERE order_id = 1002;

ROLLBACK;
~~~

### 59.1. Test expected exceptions

Kiểm tra invalid order_id, negative amount, duplicate operation và permission denied. Một routine có thể đúng với happy path nhưng sai khi retry hoặc caller thiếu quyền.

### 59.2. Test không được sửa production

Các câu CALL/SELECT function có DML trong bài có thể thay dữ liệu thật. Luôn dùng database riêng và hiểu rõ transaction boundary.

## 60. Test procedure transaction control

Với `write_audit_batches`:

- Gọi top-level thành công.
- Gọi trong explicit transaction và quan sát lỗi transaction control dự kiến.
- Xác nhận batch đã commit không tự rollback nếu lỗi xảy ra ở batch sau.
- Đảm bảo giới hạn batch size/count.
- Kiểm tra audit rows trước/sau và retry policy.
- Kiểm tra driver/framework autocommit settings.

Không chạy các test commit/rollback nội bộ trên dữ liệu production chỉ để “xem thử lỗi gì”.

## 61. Quản lý dependencies trước DROP/REPLACE

Routines có thể được tham chiếu bởi:

- Views.
- Index expressions.
- Check constraints.
- Triggers.
- Functions/procedures khác.
- Generated expressions hoặc default expressions trong trường hợp hỗ trợ.
- Code Java/ORM/BI jobs nằm ngoài database.

PostgreSQL có catalog dependencies, nhưng không thể tự tìm mọi chuỗi SQL động hoặc source code application.

### 61.1. Một replacement tương thích vẫn cần kiểm tra

Dù `CREATE OR REPLACE FUNCTION` giữ return type, logic có thể đổi ý nghĩa. Một index expression dựa trên function bị thay không đúng IMMUTABLE semantics có thể cần điều tra/reindex theo kế hoạch; đừng chỉ nhìn signature để kết luận an toàn.

### 61.2. DROP CASCADE cần review

Một `DROP FUNCTION ... CASCADE` có thể xóa dependent objects catalog-managed. Không dùng CASCADE theo phản xạ để xóa lỗi phụ thuộc; xác định closure và lộ trình migration trước.

## 62. Migration chiến lược cho routines

Một migration an toàn thường làm:

1. Ghi lại identity signature, owner, grants, config và dependencies.
2. Có database test với dataset đại diện.
3. Với thay đổi logic tương thích: dùng `CREATE OR REPLACE`.
4. Với thay đổi signature/return type: tạo routine mới hoặc overload mới.
5. Chuyển consumer theo giai đoạn.
6. Kiểm thử SQL/JDBC/permissions/transaction.
7. Xóa routine cũ bằng `RESTRICT` khi không còn sử dụng.
8. Theo dõi latency, errors và lock/IO sau deploy.

### 62.1. Expand–migrate–contract

~~~text
EXPAND:
  CREATE FUNCTION/PROCEDURE v2 (hoặc overload rõ)
        |
        v
MIGRATE:
  Deploy Java/SQL clients dùng v2, test kết quả
        |
        v
CONTRACT:
  Khi không còn caller cũ,
  DROP routine v1 có kiểm soát
~~~

Đặc biệt hữu ích khi rolling deployment đang chạy đồng thời nhiều phiên bản ứng dụng.

## 63. Tiêu chí rollback

Trước khi triển khai, chuẩn bị:

- Script khôi phục body/attributes cũ.
- Thông tin return type và argument identity.
- Owner/privileges.
- Tác động đến dependent objects.
- Chuyển app về tên/chữ ký cũ.
- Hành vi dữ liệu đã thay bằng procedure.
- Khả năng rollback transaction hoặc bù trừ nếu batch đã COMMIT.

**Rollback định nghĩa routine không đồng nghĩa rollback dữ liệu đã được commit**. Nếu một procedure mới đã ghi hàng nghìn audit/order rows, thay body về phiên bản cũ không tự hoàn tác những thay đổi đó.

## 64. Kiểm tra performance của routine

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    routine_lab.get_order_total(o.order_id)
FROM routine_lab.orders AS o;
~~~

Một số trường hợp cần:

- Xem số lần gọi routine.
- Đo execution time, CPU, buffers.
- Xem internal SQL statements với công cụ theo dõi phù hợp.
- Đánh giá `pg_stat_statements` và các lớp monitoring.
- So function scalar với JOIN/set-based query.
- Đo procedure DML throughput, WAL, locks và concurrency.
- Xem impact của function volatility và parallel safety.
- Test prepared statements/JDBC khi dùng overload và default params.

Không tuyên bố function hoặc procedure “nhanh hơn loại còn lại” theo bản chất. Hiệu năng phụ thuộc SQL bên trong, plan, volume, context và số round trips.

## 65. Những lỗi phổ biến và cách xử lý

### 65.1. Gọi procedure bằng SELECT

Sai: `SELECT my_proc(...)`. Dùng `CALL my_proc(...)`.

### 65.2. Gọi function bằng CALL

Sai: `CALL my_func(...)` khi object là normal function. Dùng `SELECT my_func(...)` hoặc ngữ cảnh SQL phù hợp.

### 65.3. Procedure có RETURNS TABLE

`RETURNS TABLE` là interface của function, không phải cú pháp chuẩn của `CREATE PROCEDURE`.

### 65.4. COMMIT bên trong function

Function không được kết thúc transaction. Chuyển commit boundary ra caller hoặc dùng procedure phù hợp.

### 65.5. COMMIT bên trong procedure gọi từ @Transactional

Explicit transaction của caller có thể làm transaction control bên trong procedure bị cấm. Xem lại kiến trúc commit.

### 65.6. COMMIT trong procedure SECURITY DEFINER

Không hợp lệ theo giới hạn PostgreSQL; không dùng SECURITY DEFINER procedure để tự commit.

### 65.7. Khai báo IMMUTABLE cho function đọc bảng

Sai về contract và có thể gây stale/planner behavior. Dùng STABLE/VOLATILE phù hợp.

### 65.8. Khai báo PARALLEL SAFE cho function ghi bảng

Sai về an toàn; function DML không được đánh dấu SAFE tùy tiện.

### 65.9. Dùng STRICT dù NULL cần được COALESCE

Function sẽ không chạy khi có input NULL, làm bỏ qua logic xử lý NULL dự định.

### 65.10. OR REPLACE đổi return type

PostgreSQL có thể từ chối. Thiết kế identity mới hoặc migration phù hợp.

### 65.11. Overload không cast literal

Có thể resolve sai/ambiguous. Dùng `::INTEGER`, `::TEXT` khi cần.

### 65.12. Dynamic SQL ghép tên bảng raw

Dễ injection. Quote identifier bằng `format('%I')` và bind values bằng `USING`.

### 65.13. SECURITY DEFINER với search_path không tin cậy

Nguy cơ thay đối tượng được resolve. Đặt search_path tin cậy và schema-qualify references.

### 65.14. Quên REVOKE PUBLIC EXECUTE

Routine mới có thể mở quyền rộng hơn mong muốn tùy default privileges. Thiết lập grants trong cùng transaction.

### 65.15. Dùng PROCEDURE để trả bảng JOIN

Không thuận tiện như function `RETURNS TABLE` khi cần SQL composition.

### 65.16. Dùng row-by-row loop thay SQL set-based

Tạo overhead lớn. Thử `UPDATE ... WHERE`, `INSERT ... SELECT` trước.

### 65.17. DROP routine nhưng quên caller

Code Java, reports và SQL dynamic bên ngoài database có thể vẫn gọi routine cũ. Cần tìm consumer.

### 65.18. Procedure COMMIT từng batch nhưng mong toàn bộ atomic

Các batches đã commit không rollback khi batch sau thất bại. Cần idempotency/checkpoint.

### 65.19. Dùng RAISE EXCEPTION không có error contract

Java khó phân biệt business error với lỗi hệ thống. Quy định SQLSTATE/message phù hợp.

### 65.20. Nhầm PL/pgSQL BEGIN với SQL BEGIN TRANSACTION

`BEGIN ... END` của routine là block, không tự mở nested transaction.

## 66. Bảng quyết định theo ví dụ nghiệp vụ

| Bài toán | Giải pháp thường phù hợp | Lý do |
|---|---|---|
| Tính phí theo số lượng | SQL function IMMUTABLE | Phép toán thuần |
| Lấy số tiền đơn hàng | SQL function STABLE | Đọc dữ liệu bảng |
| Lấy danh sách đơn theo khách | Function RETURNS TABLE | Dùng trong SELECT/JOIN |
| Đọc function có thể trả null | Function có return contract rõ | Biểu thức SQL |
| Ghi audit và trả audit_id | VOLATILE function hoặc procedure INOUT | Tùy interface |
| Xác nhận thanh toán + audit | Procedure không tự COMMIT | Command, caller quản lý transaction |
| Nạp dữ liệu theo batch có partial commits | Procedure với transaction control phù hợp | Top-level CALL |
| Tính tổng từ nhiều bảng trong một query | SQL thuần hoặc function | Set-based |
| Thao tác phức tạp cần IF/EXCEPTION | PL/pgSQL | Control flow |
| Kiểm tra quyền truy cập một đơn | Security-aware routine/SQL/RLS | Cần thiết kế auth, không chỉ chọn routine |
| Trigger trên INSERT | Function RETURNS trigger | Hợp đồng trigger |
| Command gửi email sau COMMIT | Application/outbox pattern | DB transaction không tự bao ngoài hệ thống |
| Trả nhiều pages dữ liệu cho API | SQL SELECT/function TABLE + paging | Không dùng procedure để thay mọi API query |

Không có quy tắc “mọi thao tác ghi đều là procedure”; PostgreSQL cho phép nhiều mô hình. **Tiêu chí chủ đạo là call contract, output shape, transaction boundary và permissions.**

## 67. Quy trình thiết kế một routine mới

**Bước 1 — Xác định dữ liệu đầu vào.** Các tham số, nullability, default, constraints, tên và kiểu.

**Bước 2 — Xác định kết quả.** Scalar, TABLE/SETOF, output status hay không có output.

**Bước 3 — Chọn Function/Procedure.** Cần dùng trong SELECT/JOIN hay chủ yếu CALL command?

**Bước 4 — Chọn transaction owner.** Caller hay procedure top-level? Có partial commits không?

**Bước 5 — Chọn ngôn ngữ.** Một SELECT thuần thì SQL; workflow nhiều bước thì PL/pgSQL khi cần.

**Bước 6 — Khai báo attributes chính xác.** VOLATILE/STABLE/IMMUTABLE, STRICT, PARALLEL, SECURITY.

**Bước 7 — Xác định permissions.** Role owner, GRANT EXECUTE, schema privileges, RLS/auth.

**Bước 8 — Thiết kế errors/retries.** SQLSTATE, idempotency, exception, audit và checkpoint.

**Bước 9 — Đo performance.** EXPLAIN, function call count, DML WAL/locks, concurrency.

**Bước 10 — Kiểm thử với JDBC/framework.** Autocommit, prepared calls, output parameters, transaction boundary.

**Bước 11 — Quản lý migration.** Source control, CREATE OR REPLACE khi tương thích, versioned signature khi breaking.

**Bước 12 — Theo dõi sau deploy.** Errors, latency, audit consistency và consumers.

## 68. Bài tập thực hành

### Bài 1 — Function scalar

Viết function tính `price * quantity`.

**Gợi ý:** `CREATE FUNCTION ... RETURNS NUMERIC LANGUAGE sql`.

### Bài 2 — Gọi function

Gọi function trên từ SELECT với input 10000 và 3.

**Gợi ý:** `SELECT schema.func(10000,3);`.

### Bài 3 — IMMUTABLE

Vì sao hàm nhân hai số có thể IMMUTABLE?

**Gợi ý:** kết quả chỉ phụ thuộc input.

### Bài 4 — STABLE

Vì sao hàm đọc total_amount trong bảng không nên IMMUTABLE?

**Gợi ý:** dữ liệu bảng có thể đổi.

### Bài 5 — VOLATILE

Function INSERT audit nên khai báo volatility nào?

**Gợi ý:** VOLATILE.

### Bài 6 — STRICT

Input NULL vào STRICT function thì điều gì xảy ra?

**Gợi ý:** function không chạy, trả SQL NULL.

### Bài 7 — NULL có nghĩa riêng

Nếu p_discount NULL phải được coi là 0, có nên dùng STRICT?

**Gợi ý:** không, nếu muốn thân function xử lý NULL.

### Bài 8 — RETURNS TABLE

Tạo function trả order_id và status cho một customer_id.

**Gợi ý:** RETURNS TABLE + SELECT.

### Bài 9 — RETURN QUERY

Khi nào dùng RETURN QUERY thay RETURN scalar?

**Gợi ý:** set-returning PL/pgSQL function.

### Bài 10 — LATERAL

Dùng function trả nhiều đơn của từng customer trong JOIN.

**Gợi ý:** `CROSS JOIN LATERAL function(c.customer_id)`.

### Bài 11 — Procedure cơ bản

Tạo procedure ghi một dòng vào audit_log.

**Gợi ý:** CREATE PROCEDURE ... LANGUAGE plpgsql, gọi bằng CALL.

### Bài 12 — CALL

Có thể gọi procedure trong WHERE không?

**Gợi ý:** không, CALL không phải expression.

### Bài 13 — INOUT

Một procedure có INOUT p_message, gọi thế nào?

**Gợi ý:** CALL proc(input, NULL) với ngữ cảnh ví dụ.

### Bài 14 — Transaction của function

Function có được COMMIT không?

**Gợi ý:** không.

### Bài 15 — Transaction của procedure

Procedure có COMMIT được trong mọi CALL không?

**Gợi ý:** không; cần ngữ cảnh top-level, không explicit transaction block và các giới hạn khác.

### Bài 16 — BEGIN khác nhau

PL/pgSQL BEGIN có mở transaction độc lập không?

**Gợi ý:** không, là block.

### Bài 17 — Autocommit JDBC

Vì sao procedure có COMMIT nội bộ có thể lỗi khi gọi trong `@Transactional`?

**Gợi ý:** caller có explicit transaction block.

### Bài 18 — Partial commit

Batch 1 COMMIT, batch 2 lỗi. Batch 1 có rollback tự động không?

**Gợi ý:** không.

### Bài 19 — SECURITY DEFINER

Khi nào cần đặc biệt chú ý search_path?

**Gợi ý:** routine chạy bằng quyền owner có thể resolve object trong schema không tin cậy.

### Bài 20 — GRANT EXECUTE

Vì sao cần kiểm tra PUBLIC default privileges?

**Gợi ý:** function/procedure mới có thể callable rộng hơn dự định.

### Bài 21 — Dynamic SQL

Tạo tên bảng từ input an toàn hơn bằng cách nào?

**Gợi ý:** format('%I', identifier), giá trị qua USING.

### Bài 22 — Overloading

Hai functions khác input types có thể cùng tên không?

**Gợi ý:** có.

### Bài 23 — Return type overload

Hai functions chỉ khác RETURNS type, cùng input types, có tạo riêng được không?

**Gợi ý:** không.

### Bài 24 — OR REPLACE

Vì sao không đổi return type tùy ý bằng CREATE OR REPLACE FUNCTION?

**Gợi ý:** return type là hợp đồng được PostgreSQL bảo vệ.

### Bài 25 — DROP signature

Có show_value(integer) và show_value(text). Xóa overload integer ra sao?

**Gợi ý:** DROP FUNCTION schema.show_value(integer).

### Bài 26 — Catalog

Trong pg_proc, prokind='p' nghĩa là gì?

**Gợi ý:** procedure.

### Bài 27 — pg_get_functiondef

Lấy định nghĩa một routine theo chữ ký như thế nào?

**Gợi ý:** `pg_get_functiondef('schema.func(bigint)'::regprocedure)`.

### Bài 28 — Function call overhead

Vì sao gọi function đọc bảng cho mỗi row có thể kém hơn JOIN?

**Gợi ý:** nhiều executions/internal SQL và overhead; cần đo.

### Bài 29 — Procedure loop

Có nên loop 100.000 lần UPDATE riêng khi có thể dùng UPDATE ... WHERE?

**Gợi ý:** ưu tiên set-based SQL khi phù hợp.

### Bài 30 — Trigger

Có thể gọi trigger function bình thường từ SELECT thay vì CREATE TRIGGER không?

**Gợi ý:** trigger function có hợp đồng đặc biệt.

### Bài 31 — Transaction owner

Ứng dụng cần atomicity giữa 3 repository calls. Nên đặt commit boundary ở đâu?

**Gợi ý:** thường ở service/transaction manager, procedure không tự commit.

### Bài 32 — Idempotency

Vì sao procedure mark_paid có thể lỗi khi caller retry sau lần đầu đã commit?

**Gợi ý:** trạng thái đã đổi, điều kiện status='new' không còn.

### Bài 33 — Exception

Vì sao không nên WHEN OTHERS THEN RETURN 'ok'?

**Gợi ý:** che lỗi quan trọng.

### Bài 34 — Parallel safe

Có thể đánh dấu PARALLEL SAFE cho function INSERT audit không?

**Gợi ý:** không.

### Bài 35 — Versioned routine

Khi đổi chữ ký routine public, tại sao tạo v2 thường an toàn hơn DROP v1 ngay?

**Gợi ý:** cho callers migrate dần và rollback dễ hơn.

## 69. Câu hỏi thường gặp

### Function có được UPDATE/INSERT không?

Có, một function phù hợp, thường được khai báo `VOLATILE`, có thể làm DML và gây side effects. Nhưng function không được tự COMMIT/ROLLBACK transaction.

### Procedure có bắt buộc COMMIT ở cuối không?

Không. Nếu procedure không có COMMIT, thay đổi thuộc transaction của caller giống nhiều câu SQL khác. Một lời gọi `CALL` không tự động buộc thủ tục phải kết thúc transaction trong body.

### Procedure có thể trả dữ liệu không?

Có thể thông qua OUT/INOUT parameters ở các phiên bản hỗ trợ, `CALL` trả result row tương ứng. Nhưng nó không thay một function `RETURNS TABLE` được dùng như relation trong SELECT/JOIN.

### Có thể viết procedure bằng LANGUAGE sql không?

Có. PostgreSQL hỗ trợ SQL-language procedures, ngoài PL/pgSQL và các ngôn ngữ phù hợp khác. Với workflow cần IF/LOOP/RAISE, PL/pgSQL thường dễ dùng.

### Function phải có RETURNS không?

Function có hợp đồng kiểu kết quả. Nếu cần hành vi tương tự command không có output, có `RETURNS void`, nhưng điều đó không làm function thành procedure hay cho phép COMMIT nội bộ.

### RETURNS void có gọi bằng CALL được không?

Không vì vẫn là function. Thường gọi bằng `SELECT schema.func(...)`.

### Khi nào chọn SECURITY DEFINER?

Khi có lý do rõ ràng để routine thực thi một thao tác có đặc quyền được giới hạn, với input validation, grants, search_path an toàn, schema qualification và kiểm thử quyền. Không dùng theo mặc định.

### IMMUTABLE có giúp function nhanh hơn không?

Nó cho planner những bảo đảm mạnh có thể tạo cơ hội tối ưu, nhưng chỉ đúng nếu function thật sự bất biến. Gắn sai có thể gây kết quả không đúng.

### Có thể dùng procedure để vượt transaction của Spring không?

Không. Nếu Spring đang mở explicit transaction, procedure có COMMIT nội bộ có thể bị PostgreSQL từ chối. Cần quyết định rõ transaction boundary thay vì cố lách.

### Có nên viết mọi business logic vào stored routines không?

Không nhất thiết. Các thao tác cần tính nhất quán dữ liệu gần DB có thể hợp lý ở routine; logic liên quan nhiều dịch vụ, presentation hoặc authorization phức tạp có thể phù hợp hơn ở application. Quan trọng là chia trách nhiệm rõ.

### OR REPLACE có tự cập nhật code Java đang gọi routine không?

Không. Chữ ký, named parameters, return semantics và SQL text bên ứng dụng vẫn do code ứng dụng quản lý. Breaking changes phải được phối hợp deployment.

### Khi nào nên benchmark?

Khi routine chạy nhiều lần, được dùng trong WHERE/JOIN, xử lý DML lớn hoặc có transaction control. Dùng EXPLAIN, load test, I/O/WAL/locks/CPU và kiểm thử concurrency phù hợp.

## 70. Tổng kết

- **`CREATE FUNCTION`** định nghĩa một routine có `RETURNS`, dùng được như **SQL expression** hoặc set-returning relation.
- **`CREATE PROCEDURE`** định nghĩa một routine được gọi bằng **`CALL`**, thường phù hợp với command/workflow có side effects.
- Function có thể trả scalar, composite, `SETOF` hoặc `RETURNS TABLE`; procedure có thể dùng output parameters nhưng không có cùng khả năng ghép trực tiếp trong SELECT/JOIN.
- **Function không thể COMMIT/ROLLBACK**. Procedure chỉ có transaction control khi lời gọi/thuộc tính/ngữ cảnh đáp ứng giới hạn PostgreSQL.
- **`BEGIN ... END` trong PL/pgSQL là block**, không phải BEGIN TRANSACTION.
- Function có thể làm DML và cần khai báo `VOLATILE` phù hợp; không mặc định function là pure.
- **`IMMUTABLE`, `STABLE`, `VOLATILE`** là hợp đồng của routine với planner và snapshot behavior. Không gắn sai để ép tối ưu.
- **`STRICT`** trả NULL khi input NULL mà không thực thi thân function, vì vậy không phù hợp nếu cần xử lý NULL tùy chỉnh.
- **`PARALLEL SAFE/RESTRICTED/UNSAFE`** liên quan an toàn song song và không thể đánh dấu tùy ý.
- `LANGUAGE sql` phù hợp phép tính/truy vấn đơn giản; `LANGUAGE plpgsql` phù hợp biến, IF, loop, RAISE và xử lý exception.
- **`SECURITY DEFINER`** có rủi ro nếu `search_path` và quyền EXECUTE không được kiểm soát; ưu tiên schema qualification và minimal privileges.
- **CREATE OR REPLACE** chỉ phù hợp khi giữ contract tương thích; return type/signature và semantics có thể đòi routine phiên bản mới.
- Khi overload, dùng **argument types rõ ràng** để gọi, ALTER hoặc DROP đúng routine.
- Với Java/JDBC, function thường gọi bằng `SELECT f(?)`; procedure bằng `CALL p(?)`. Procedure có COMMIT nội bộ cần đặc biệt chú ý autocommit và `@Transactional`.
- **SQL set-based thường đơn giản hơn vòng lặp** với nhiều rows; function/procedure không tự làm SQL bên trong nhanh hơn.
- Rollback định nghĩa routine không rollback dữ liệu mà procedure đã commit từ trước.
- Lựa chọn tốt nhất dựa trên **hình dạng kết quả, cách gọi, transaction owner, quyền, semantics, khả năng bảo trì và performance**.

Sơ đồ cuối:

~~~text
Yêu cầu nghiệp vụ
       |
       v
Cần giá trị hoặc tập rows dùng trong SELECT?
       |
    +--+--+
    |     |
   Có    Không
    |     |
 FUNCTION  Chủ yếu là command nhiều bước?
    |          |
    |       +--+--+
    |       |     |
    |      Có    Không
    |       |     |
    |    PROCEDURE  SQL thuần cũng có thể đủ
    |       |
    |       v
    |  Có cần COMMIT nội bộ?
    |       |
    |       v
    |  Kiểm tra CALL context, client transaction,
    |  SECURITY DEFINER/SET và error semantics
    |       |
    +-------+
            |
            v
Chọn LANGUAGE, attributes, grants, error contract
            |
            v
Test correctness + transaction + performance
            |
            v
Versioned migration, deploy và giám sát
~~~

Điều cốt lõi không phải “function tốt hơn procedure” hay ngược lại, mà là **đặt đúng hợp đồng thực thi ở đúng tầng**. Khi mục tiêu là biểu thức hoặc tập kết quả SQL, hãy nghĩ tới function; khi mục tiêu là một hành động nghiệp vụ, hãy cân nhắc procedure; khi mục tiêu là chia transaction, hãy kiểm tra trước **giới hạn CALL của PostgreSQL và transaction boundary của ứng dụng**.
