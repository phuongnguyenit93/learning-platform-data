# VALUES và tập dữ liệu nhỏ không cần bảng trong PostgreSQL

Một truy vấn PostgreSQL không nhất thiết phải đọc từ bảng đã lưu trên đĩa. Có nhiều lúc chúng ta chỉ cần vài hàng dữ liệu để thử một biểu thức, mô tả danh sách tham chiếu ngắn, đối chiếu trạng thái, tạo đầu vào cho phép `JOIN`, hoặc kiểm tra một câu SQL trước khi áp dụng lên dữ liệu thật. Trong những tình huống đó, câu lệnh **`VALUES`** là một công cụ rất hữu ích.

Ví dụ, nếu muốn có ba hàng gồm mã và tên sản phẩm:

~~~sql
VALUES
    (101, 'Sách SQL'),
    (102, 'Bàn phím'),
    (103, 'Chuột');
~~~

PostgreSQL trả một tập kết quả gồm ba hàng và hai cột mà **không cần tạo bảng**. Tập kết quả này có thể được đặt tên, tham gia `JOIN`, nằm trong `WITH`/CTE, đóng vai trò nguồn cho `INSERT` hoặc `UPDATE`, và hỗ trợ nhiều bài toán dữ liệu nhỏ.

Bài học thuộc chương **Truy vấn cơ bản** của module **Database Engine Relational PostgreSQL**. Mục tiêu không chỉ là nhớ cú pháp `VALUES`, mà còn hiểu rõ nó khác bảng vật lý và `SELECT` như thế nào, cách PostgreSQL suy luận kiểu, cách kiểm soát thứ tự và `NULL`, cũng như khi nào nên chuyển sang bảng tạm, `unnest` hoặc `generate_series`.

## 1. VALUES là gì?

`VALUES` là cấu trúc SQL dùng để tạo **một tập hàng từ những biểu thức viết trực tiếp trong câu lệnh**. Mỗi cặp ngoặc đơn biểu diễn một hàng; các biểu thức trong cặp ngoặc tương ứng với những cột của hàng đó.

Cú pháp chung:

~~~sql
VALUES
    (expression_1_1, expression_1_2, ...),
    (expression_2_1, expression_2_2, ...),
    (expression_3_1, expression_3_2, ...);
~~~

Nếu có ba nhóm ngoặc và mỗi nhóm có hai biểu thức, kết quả là ba hàng và hai cột.

Ví dụ đơn giản nhất:

~~~sql
VALUES (1);
~~~

Kết quả là **một hàng, một cột**, có giá trị 1.

Ví dụ nhiều hàng:

~~~sql
VALUES
    (1),
    (2),
    (3);
~~~

Kết quả là **ba hàng, một cột**.

Ví dụ nhiều cột:

~~~sql
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', FALSE),
    (3, 'Chi', TRUE);
~~~

Kết quả là **ba hàng, ba cột**.

### 1.1. Không nhầm số cột với số hàng

Hai câu sau hoàn toàn khác nhau:

~~~sql
-- Một hàng có ba cột.
VALUES (1, 2, 3);

-- Ba hàng, mỗi hàng có một cột.
VALUES
    (1),
    (2),
    (3);
~~~

Trong ví dụ đầu, các số 1, 2, 3 là những **cột khác nhau của một hàng**. Trong ví dụ sau, chúng thuộc cùng một cột ở ba hàng.

Điều này đặc biệt quan trọng khi tạo đầu vào cho phép `JOIN` hoặc `IN` có nhiều cột.

### 1.2. VALUES có tạo bảng thật không?

Không. Chạy:

~~~sql
VALUES (101, 'Sách SQL');
~~~

**không tạo** một đối tượng bảng trong schema, không có primary key, không có index lưu trữ riêng và không để lại một tập dữ liệu có thể truy vấn lại theo tên ở câu lệnh tiếp theo.

Nó chỉ trả về một quan hệ kết quả trong phạm vi câu lệnh. PostgreSQL có thể lập kế hoạch thực thi thích hợp cho tập giá trị này; không nên coi đó là một bảng vật lý được tạo ngầm trong database.

## 2. So sánh VALUES với SELECT không có FROM

PostgreSQL cũng cho phép `SELECT` một số biểu thức mà không cần `FROM`:

~~~sql
SELECT
    101 AS product_id,
    'Sách SQL' AS product_name;
~~~

Truy vấn trên trả **một hàng**.

Nếu cần nhiều hàng, có thể sử dụng `UNION ALL`:

~~~sql
SELECT 101 AS product_id, 'Sách SQL' AS product_name
UNION ALL
SELECT 102, 'Bàn phím'
UNION ALL
SELECT 103, 'Chuột';
~~~

Nhưng với một danh sách ngắn được khai báo trực tiếp, `VALUES` thường dễ đọc hơn:

~~~sql
VALUES
    (101, 'Sách SQL'),
    (102, 'Bàn phím'),
    (103, 'Chuột');
~~~

| Nhu cầu | Cách thường tiện |
|---|---|
| Tính một biểu thức đơn giản | `SELECT 2 + 3;` |
| Trả về một hàng có tên cột rõ ràng | `SELECT 1 AS id, 'An' AS name;` |
| Tạo nhiều hàng literal ngắn | `VALUES (...) , (...);` |
| Tạo hàng từ bảng thật | `SELECT ... FROM table` |
| Kết hợp nhiều query phức tạp | `UNION ALL` hoặc CTE |
| Sinh dãy số đều | `generate_series` |
| Lưu dữ liệu để nhiều câu lệnh sử dụng | Bảng thật hoặc bảng tạm |

`VALUES` không thay thế toàn bộ `SELECT`; nó bổ sung một cách ngắn gọn để mô tả **các hàng dữ liệu cụ thể**.

## 3. Tên cột mặc định và cách đặt tên có ý nghĩa

Khi chạy `VALUES` độc lập, PostgreSQL tạo các tên cột mặc định như `column1`, `column2`, ...:

~~~sql
VALUES
    (101, 'Sách SQL'),
    (102, 'Bàn phím');
~~~

Với những câu SQL cần đọc/biến đổi nhiều lần, tên mặc định `column1` và `column2` không dễ bảo trì. Hãy đưa `VALUES` vào phần `FROM` và dùng alias:

~~~sql
SELECT
    p.product_id,
    p.product_name
FROM (
    VALUES
        (101, 'Sách SQL'),
        (102, 'Bàn phím'),
        (103, 'Chuột')
) AS p(product_id, product_name)
ORDER BY p.product_id;
~~~

Giải thích:

- `(VALUES ...)` đóng vai trò một **table expression** trong `FROM`.
- `AS p` đặt alias cho nguồn dữ liệu.
- `(product_id, product_name)` đặt tên cho các cột theo đúng thứ tự biểu thức.
- `p.product_id` và `p.product_name` giúp truy vấn rõ nghĩa và tránh trùng tên với các nguồn khác.
- `ORDER BY` yêu cầu thứ tự kết quả một cách tường minh.

### 3.1. Alias không làm phát sinh bảng bền vững

Sau khi truy vấn kết thúc:

~~~sql
SELECT *
FROM (VALUES (1, 'A')) AS v(id, label);
~~~

không có bảng `v` nào được lưu lại. `v` chỉ là tên tạm **trong phạm vi câu SQL đang thực thi**.

### 3.2. Đặt tên cột theo thứ tự vị trí

Nếu bạn viết:

~~~sql
SELECT *
FROM (VALUES (101, 'A')) AS x(label, id);
~~~

thì cột `label` sẽ chứa số 101 và cột `id` sẽ chứa chuỗi `A`. PostgreSQL **không tự hiểu ý nghĩa** dựa trên tên alias; nó ánh xạ theo thứ tự cột.

Vì vậy luôn rà soát thứ tự biểu thức trong mọi hàng và danh sách alias.

## 4. Quy tắc: các hàng phải có cùng số lượng cột

Một tập `VALUES` hợp lệ cần có số biểu thức tương ứng ở mọi hàng.

Hợp lệ:

~~~sql
VALUES
    (1, 'An', 10),
    (2, 'Bình', 20),
    (3, 'Chi', 30);
~~~

Không hợp lệ:

~~~sql
-- Hàng 1 có hai cột, hàng 2 có ba cột.
-- VALUES
--     (1, 'An'),
--     (2, 'Bình', 20);
~~~

PostgreSQL không tự bổ sung `NULL` cho hàng ngắn hơn. Nếu một giá trị chưa biết, hãy ghi `NULL` rõ ràng và suy nghĩ về **kiểu dữ liệu của cột đó**.

~~~sql
VALUES
    (1, 'An', 10),
    (2, 'Bình', NULL),
    (3, 'Chi', 30);
~~~

Câu lệnh trên có ba cột ở mọi hàng, nên hình dạng dữ liệu nhất quán.

## 5. PostgreSQL suy luận kiểu cột trong VALUES như thế nào?

Dù `VALUES` không khai báo `CREATE TABLE`, PostgreSQL vẫn phải xác định **một kiểu dữ liệu chung cho mỗi cột** để trả kết quả, so sánh và thực hiện toán tử.

Ví dụ:

~~~sql
SELECT
    v.number_value,
    pg_typeof(v.number_value) AS inferred_type
FROM (
    VALUES
        (1),
        (2),
        (3)
) AS v(number_value);
~~~

Cột chỉ chứa literal số nguyên thông dụng, nên kiểu suy luận có thể là `integer` trong ví dụ này.

Nếu trộn số nguyên và số có phần thập phân:

~~~sql
SELECT
    v.amount,
    pg_typeof(v.amount) AS amount_type
FROM (
    VALUES
        (1),
        (2.75),
        (3)
) AS v(amount);
~~~

PostgreSQL cần chọn một kiểu có thể biểu diễn các giá trị theo quy tắc phân giải kiểu chung. Với các literal số đơn giản như ví dụ, kiểu thường được chọn là `numeric`.

### 5.1. Mỗi cột được giải quyết kiểu riêng

Trong:

~~~sql
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', FALSE);
~~~

PostgreSQL suy luận kiểu cho **cột thứ nhất**, **cột thứ hai** và **cột thứ ba** riêng biệt. Nó không yêu cầu tất cả các cột trong một hàng có cùng kiểu.

### 5.2. Không giả định các chuỗi luôn tự chuyển được

Ví dụ có thể lỗi:

~~~sql
-- Một cột trộn integer và một chuỗi không đổi được thành số.
-- VALUES
--     (1),
--     ('khong-phai-so');
~~~

Một chuỗi literal chưa biết kiểu có thể được ép theo kiểu của các hàng khác. Nếu nội dung không chuyển được, PostgreSQL báo lỗi thay vì âm thầm giữ hai kiểu không tương thích trong cùng một cột.

Khi dữ liệu mẫu được dùng cho bài test hoặc câu SQL quan trọng, **ép kiểu tường minh** giúp kiểm soát kết quả hơn là phụ thuộc vào suy luận.

## 6. Ép kiểu tường minh để tạo tập dữ liệu ổn định

Ví dụ bảng giá:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price,
    pg_typeof(p.unit_price) AS price_type
FROM (
    VALUES
        (101::BIGINT, 'Sách SQL'::TEXT, 150000.00::NUMERIC(12, 2)),
        (102::BIGINT, 'Bàn phím'::TEXT, 420000.00::NUMERIC(12, 2)),
        (103::BIGINT, 'Chuột'::TEXT, 175000.00::NUMERIC(12, 2))
) AS p(product_id, product_name, unit_price)
ORDER BY p.product_id;
~~~

Ở đây, ta chủ động chọn:

- `BIGINT` cho ID.
- `TEXT` cho tên.
- `NUMERIC(12, 2)` cho tiền.

Kiểu `NUMERIC` phù hợp với phép tính tiền thập phân trong ví dụ; không nên dùng `REAL` hoặc `DOUBLE PRECISION` khi nghiệp vụ cần phép tính thập phân chính xác theo quy tắc cụ thể.

### 6.1. DATE và TIMESTAMPTZ trong VALUES

Để không phụ thuộc vào ngày chạy câu SQL, dùng literal thời gian cố định:

~~~sql
SELECT
    e.event_id,
    e.event_date,
    e.observed_at
FROM (
    VALUES
        (
            1,
            DATE '2026-01-10',
            TIMESTAMPTZ '2026-01-10 08:00:00+00'
        ),
        (
            2,
            DATE '2026-01-11',
            TIMESTAMPTZ '2026-01-11 09:30:00+00'
        )
) AS e(event_id, event_date, observed_at)
ORDER BY e.event_id;
~~~

`DATE` biểu diễn ngày lịch; `TIMESTAMPTZ` biểu diễn thời điểm theo semantics timezone của PostgreSQL. Cách hiển thị `TIMESTAMPTZ` có thể thay đổi theo timezone của session, dù thời điểm được lưu có ý nghĩa giống nhau.

### 6.2. BOOLEAN và JSONB

~~~sql
SELECT
    cfg.setting_key,
    cfg.enabled,
    cfg.payload
FROM (
    VALUES
        (
            'new_checkout'::TEXT,
            TRUE,
            '{"version":2,"group":"beta"}'::JSONB
        ),
        (
            'audit_mode'::TEXT,
            FALSE,
            '{"version":1,"group":"all"}'::JSONB
        )
) AS cfg(setting_key, enabled, payload);
~~~

Không cần tạo bảng chỉ để thử phép trích xuất JSON:

~~~sql
SELECT
    cfg.setting_key,
    cfg.payload ->> 'group' AS audience_group
FROM (
    VALUES
        ('new_checkout', '{"group":"beta"}'::JSONB),
        ('audit_mode', '{"group":"all"}'::JSONB)
) AS cfg(setting_key, payload);
~~~

Đây là một cách tốt để thử biểu thức PostgreSQL với dữ liệu nhỏ, kiểm soát được kiểu và giá trị.

## 7. NULL trong VALUES: giá trị thiếu và kiểu dữ liệu

`NULL` không biểu diễn số 0, chuỗi rỗng hoặc boolean FALSE. Nó biểu diễn giá trị không có/không biết theo ngữ nghĩa SQL.

~~~sql
SELECT
    v.customer_id,
    v.note
FROM (
    VALUES
        (101, 'Đã liên hệ'::TEXT),
        (102, NULL::TEXT),
        (103, 'Cần gọi lại'::TEXT)
) AS v(customer_id, note)
ORDER BY v.customer_id;
~~~

`NULL::TEXT` làm rõ kiểu của cột `note`. Nếu không ép kiểu, PostgreSQL có thể suy luận kiểu từ các hàng khác; nhưng nếu **toàn bộ cột đều là `NULL`**, cần chú ý quy tắc xử lý kiểu unknown.

~~~sql
SELECT
    v.id,
    v.reason,
    pg_typeof(v.reason) AS reason_type
FROM (
    VALUES
        (1, NULL::TEXT),
        (2, NULL::TEXT)
) AS v(id, reason);
~~~

### 7.1. Điều kiện đúng để kiểm tra NULL

Không viết:

~~~sql
-- Không dùng phép = để hỏi có NULL hay không.
-- WHERE v.note = NULL;
~~~

Thay vào đó:

~~~sql
SELECT *
FROM (
    VALUES
        (101, 'Có ghi chú'::TEXT),
        (102, NULL::TEXT)
) AS v(id, note)
WHERE v.note IS NULL;
~~~

Để so sánh hai giá trị và muốn coi hai `NULL` là tương đương trong phép kiểm tra, có thể dùng `IS NOT DISTINCT FROM`:

~~~sql
SELECT
    a.value IS NOT DISTINCT FROM b.value AS same_including_null
FROM (VALUES (NULL::INTEGER)) AS a(value)
CROSS JOIN (VALUES (NULL::INTEGER)) AS b(value);
~~~

Kết quả là TRUE. Đây là một tính năng hữu ích khi so sánh các tập dữ liệu mẫu có giá trị thiếu.

## 8. Dùng biểu thức, không chỉ literal trong VALUES

Mỗi phần tử của `VALUES` có thể là một biểu thức phù hợp với ngữ cảnh SQL, không chỉ một hằng số.

Ví dụ:

~~~sql
SELECT
    v.product_id,
    v.base_price,
    v.vat_amount
FROM (
    VALUES
        (101, 150000.00::NUMERIC, 150000.00::NUMERIC * 0.08),
        (102, 420000.00::NUMERIC, 420000.00::NUMERIC * 0.08)
) AS v(product_id, base_price, vat_amount);
~~~

Tuy nhiên, việc lặp biểu thức trong từng hàng có thể khó bảo trì. Thông thường rõ ràng hơn khi khai báo **dữ liệu đầu vào** bằng `VALUES` và tính toán trong `SELECT`:

~~~sql
SELECT
    p.product_id,
    p.base_price,
    p.base_price * 0.08 AS vat_amount,
    p.base_price * 1.08 AS gross_price
FROM (
    VALUES
        (101, 150000.00::NUMERIC),
        (102, 420000.00::NUMERIC)
) AS p(product_id, base_price)
ORDER BY p.product_id;
~~~

Cách này tránh phải sửa công thức ở nhiều hàng và dễ kiểm thử hơn.

### 8.1. Cẩn thận với hàm phụ thuộc thời gian hoặc ngẫu nhiên

~~~sql
VALUES
    (1, now()),
    (2, now());
~~~

Câu SQL hợp lệ, nhưng thời điểm được sinh phụ thuộc thời gian chạy transaction. Nếu cần **test fixture có thể tái tạo**, hãy dùng literal cố định.

Tương tự, `random()` tạo dữ liệu thay đổi giữa các lần chạy nếu không có chiến lược kiểm soát phù hợp. Không nên dựa vào giá trị ngẫu nhiên khi muốn so sánh chính xác đầu ra của bài tập.

## 9. ORDER BY, LIMIT và OFFSET với VALUES

**Không có `ORDER BY` thì không được bảo đảm thứ tự hàng trả về**, ngay cả khi bạn viết các dòng trong `VALUES` theo thứ tự đẹp mắt.

Ví dụ:

~~~sql
VALUES
    (3, 'C'),
    (1, 'A'),
    (2, 'B')
ORDER BY 1;
~~~

Ở đây `ORDER BY 1` sắp xếp theo **cột thứ nhất**. Kết quả theo ID tăng dần là 1, 2, 3.

PostgreSQL cũng hỗ trợ `LIMIT` và `OFFSET` cho biểu thức `VALUES` ở vị trí phù hợp:

~~~sql
VALUES
    (3, 'C'),
    (1, 'A'),
    (2, 'B')
ORDER BY 1
LIMIT 2;
~~~

Kết quả lấy hai hàng đầu **sau khi sắp xếp**.

### 9.1. Ưu tiên ORDER BY có tên cột

Khi dữ liệu trở thành table expression:

~~~sql
SELECT
    v.id,
    v.label
FROM (
    VALUES
        (3, 'C'),
        (1, 'A'),
        (2, 'B')
) AS v(id, label)
ORDER BY v.id
LIMIT 2;
~~~

`ORDER BY v.id` thường dễ hiểu và ít nhầm hơn `ORDER BY 1` nếu câu `SELECT` sau này đổi thứ tự cột.

### 9.2. Muốn giữ thứ tự khai báo, phải lưu số thứ tự

Không có khái niệm “thứ tự mặc định của hàng trong VALUES” mà query bên ngoài được phép dựa vào.

Nếu thứ tự đầu vào có ý nghĩa, hãy tạo cột thứ tự:

~~~sql
SELECT
    v.product_code
FROM (
    VALUES
        (1, 'MOUSE'),
        (2, 'BOOK'),
        (3, 'KEYBOARD')
) AS v(input_position, product_code)
ORDER BY v.input_position;
~~~

Cột `input_position` giúp kết quả nhất quán, kể cả khi `VALUES` tham gia các phép `JOIN` hoặc `GROUP BY`.

## 10. VALUES trong FROM: biến danh sách thành một nguồn dữ liệu

Một mẫu SQL thực tế:

~~~sql
SELECT
    s.status_code,
    s.display_name,
    s.sort_rank
FROM (
    VALUES
        ('new'::TEXT, 'Mới tạo'::TEXT, 10),
        ('processing', 'Đang xử lý', 20),
        ('done', 'Hoàn thành', 30),
        ('cancelled', 'Đã hủy', 40)
) AS s(status_code, display_name, sort_rank)
ORDER BY s.sort_rank;
~~~

Tập này phù hợp khi:

- Chỉ có vài dòng.
- Danh sách phục vụ một câu truy vấn cụ thể.
- Các giá trị cố định, được review cùng SQL.
- Không cần chỉnh sửa danh sách độc lập bởi nhiều hệ thống.
- Không cần primary key/index/foreign key hoặc phân quyền riêng trên danh mục.

Ngược lại, khi danh mục có hàng trăm giá trị, thay đổi thường xuyên hoặc do người dùng quản trị, nên dùng **bảng tra cứu** thực sự thay vì nhúng `VALUES` lặp lại trong nhiều query.

## 11. WITH và VALUES: tạo CTE có tên cột

CTE (`Common Table Expression`) giúp đặt tên cho một tập kết quả trong phạm vi một câu SQL.

~~~sql
WITH status_map(status_code, display_name, sort_rank) AS (
    VALUES
        ('new'::TEXT, 'Mới tạo'::TEXT, 10),
        ('processing', 'Đang xử lý', 20),
        ('done', 'Hoàn thành', 30),
        ('cancelled', 'Đã hủy', 40)
)
SELECT
    status_code,
    display_name
FROM status_map
ORDER BY sort_rank;
~~~

Ưu điểm:

- Tên cột khai báo gọn trong dấu ngoặc sau tên CTE.
- Có thể tham chiếu CTE ở những phần khác trong cùng statement.
- Dễ kết hợp nhiều bộ dữ liệu nhỏ.
- Tách bước khai báo dữ liệu khỏi bước tính toán.

### 11.1. CTE không tự là bảng lưu trữ

Sau khi statement kết thúc, `status_map` không tồn tại như một bảng bền vững. Chạy:

~~~sql
-- Nếu không có bảng thật cùng tên:
-- SELECT * FROM status_map;
~~~

ở câu lệnh tiếp theo sẽ không tìm thấy CTE cũ.

### 11.2. Nhiều tập VALUES trong một WITH

~~~sql
WITH
customers(customer_id, customer_name) AS (
    VALUES
        (1, 'An'::TEXT),
        (2, 'Bình'),
        (3, 'Chi')
),
orders(order_id, customer_id, amount) AS (
    VALUES
        (1001, 1, 150000.00::NUMERIC),
        (1002, 1, 200000.00::NUMERIC),
        (1003, 2, 300000.00::NUMERIC)
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.amount), 0) AS total_amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả kỳ vọng:

| customer_id | customer_name | total_amount |
|---:|---|---:|
| 1 | An | 350000.00 |
| 2 | Bình | 300000.00 |
| 3 | Chi | 0.00 |

Dữ liệu này **tự chứa hoàn toàn trong câu SQL**, nên rất tiện để luyện `JOIN`, `GROUP BY` và `COALESCE` khi chưa có database mẫu.

## 12. JOIN với một danh sách mã nhỏ

Giả sử bảng đơn hàng thật có cột `status_code` nhưng bạn chỉ muốn trình bày tên tiếng Việt cho một báo cáo cụ thể. Thay vì viết nhiều điều kiện `CASE` dài, có thể dùng bảng ánh xạ nhỏ từ `VALUES`:

~~~sql
WITH
orders(order_id, status_code, amount) AS (
    VALUES
        (1001, 'new'::TEXT, 100000.00::NUMERIC),
        (1002, 'done', 250000.00::NUMERIC),
        (1003, 'cancelled', 80000.00::NUMERIC),
        (1004, 'unknown', 99000.00::NUMERIC)
),
status_map(status_code, display_name) AS (
    VALUES
        ('new'::TEXT, 'Mới tạo'::TEXT),
        ('done', 'Hoàn thành'),
        ('cancelled', 'Đã hủy')
)
SELECT
    o.order_id,
    o.status_code,
    COALESCE(m.display_name, 'Chưa định nghĩa') AS status_label,
    o.amount
FROM orders AS o
LEFT JOIN status_map AS m
    ON m.status_code = o.status_code
ORDER BY o.order_id;
~~~

Kết quả:

| order_id | status_code | status_label | amount |
|---:|---|---|---:|
| 1001 | new | Mới tạo | 100000.00 |
| 1002 | done | Hoàn thành | 250000.00 |
| 1003 | cancelled | Đã hủy | 80000.00 |
| 1004 | unknown | Chưa định nghĩa | 99000.00 |

`LEFT JOIN` giữ lại hàng có mã không nằm trong danh sách. `COALESCE` giúp hiển thị nhãn dự phòng.

Nếu dùng `INNER JOIN`, đơn 1004 sẽ không xuất hiện vì không có bản ghi ánh xạ tương ứng. Điều này có thể làm báo cáo thiếu hàng ngoài ý muốn.

### 12.1. Tránh ánh xạ trùng mã

Giả sử `status_map` chứa hai dòng có `status_code = 'done'`. Một đơn ở trạng thái done có thể **nhân thành hai hàng** sau `JOIN`.

~~~sql
WITH status_map(status_code, display_name) AS (
    VALUES
        ('done'::TEXT, 'Hoàn thành'),
        ('done', 'Đã xử lý')
)
SELECT status_code, COUNT(*) AS mapping_rows
FROM status_map
GROUP BY status_code
HAVING COUNT(*) > 1;
~~~

Đây là cách phát hiện mã trùng trong một bộ dữ liệu nhỏ. `VALUES` không có unique constraint giống bảng thật, nên việc duy trì tính duy nhất của danh sách phụ thuộc vào cách viết/truy vấn.

## 13. VALUES và phép lọc IN

Nếu chỉ muốn lọc theo vài giá trị của **một cột**, cú pháp `IN` ngắn gọn:

~~~sql
WITH orders(order_id, status_code) AS (
    VALUES
        (1001, 'new'::TEXT),
        (1002, 'done'),
        (1003, 'cancelled')
)
SELECT *
FROM orders
WHERE status_code IN ('new', 'done')
ORDER BY order_id;
~~~

Không nhất thiết phải viết `VALUES` bên trong `IN` cho một danh sách literal đơn giản. Nhưng `VALUES` trở nên tiện khi muốn lọc theo **nhiều cột cùng lúc**.

### 13.1. IN với cặp giá trị (composite row)

~~~sql
WITH assignments(customer_id, project_id) AS (
    VALUES
        (1, 10),
        (1, 20),
        (2, 10),
        (3, 30)
)
SELECT
    customer_id,
    project_id
FROM assignments
WHERE (customer_id, project_id) IN (
    VALUES
        (1, 20),
        (3, 30)
)
ORDER BY customer_id, project_id;
~~~

Kết quả gồm cặp `(1,20)` và `(3,30)`. So sánh cặp giá trị giúp tránh lỗi logic của điều kiện:

~~~sql
-- Có thể trả sai tổ hợp vì tách hai danh sách độc lập:
-- WHERE customer_id IN (1, 3)
--   AND project_id IN (20, 30);
~~~

Hai điều kiện độc lập có thể chấp nhận cả những cặp **không nằm trong danh sách cho phép**.

### 13.2. NULL trong IN/NOT IN

`IN` và `NOT IN` có semantics SQL ba giá trị khi danh sách chứa `NULL`.

Ví dụ:

~~~sql
SELECT
    4 NOT IN (1, 2, NULL) AS result_with_null;
~~~

Kết quả là `NULL` (UNKNOWN), **không phải TRUE**, do chưa thể kết luận 4 khác mọi giá trị nếu có một phần tử chưa biết.

Khi cần kiểm tra “không có dòng khớp” một cách rõ ràng, `NOT EXISTS` thường dễ kiểm soát hơn:

~~~sql
WITH
candidates(id) AS (
    VALUES (1), (2), (4)
),
excluded_ids(id) AS (
    VALUES (1), (NULL::INTEGER)
)
SELECT c.id
FROM candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM excluded_ids AS e
    WHERE e.id = c.id
)
ORDER BY c.id;
~~~

Theo dấu bằng SQL thông thường, `NULL` không bằng bất kỳ số cụ thể nào; kết quả gồm 2 và 4. Nếu chính sách muốn hai `NULL` khớp nhau, cần dùng điều kiện khác như `IS NOT DISTINCT FROM` trong truy vấn tương quan.

## 14. EXISTS, NOT EXISTS và danh sách nhỏ

`VALUES` có thể là nguồn dữ liệu trong một subquery:

~~~sql
WITH orders(order_id, customer_id) AS (
    VALUES
        (1001, 1),
        (1002, 2),
        (1003, 3)
)
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM (
        VALUES (1), (3)
    ) AS allowed(customer_id)
    WHERE allowed.customer_id = o.customer_id
)
ORDER BY o.order_id;
~~~

Kết quả là đơn của khách 1 và 3.

Mẫu này thuận tiện khi tập khóa lọc có nhiều trường hoặc cần dùng thêm metadata trong danh sách. Với danh sách ID đơn cột, `WHERE customer_id IN (1,3)` thường ngắn hơn và dễ đọc hơn.

### 14.1. EXISTS không làm nhân hàng

Nếu bảng tham chiếu có hai hàng trùng khóa, `JOIN` có thể nhân hàng kết quả. `EXISTS` chỉ kiểm tra có ít nhất một hàng khớp, vì vậy phù hợp với yêu cầu “có thuộc tập hay không”.

~~~sql
WITH
orders(order_id, customer_id) AS (
    VALUES (1001, 1), (1002, 2)
),
allowed(customer_id) AS (
    VALUES (1), (1)
)
SELECT o.*
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM allowed AS a
    WHERE a.customer_id = o.customer_id
);
~~~

Đơn 1001 xuất hiện một lần trong kết quả. `EXISTS` không phải cơ chế xử lý duplicate của nguồn; nó chỉ dùng semantics tồn tại phù hợp với bài toán lọc.

## 15. VALUES để kiểm thử JOIN không cần schema

Một tác dụng mạnh của `VALUES` là có thể viết **query mẫu chạy độc lập**.

Ví dụ muốn dạy sự khác biệt giữa `INNER JOIN` và `LEFT JOIN`:

~~~sql
WITH
departments(department_id, department_name) AS (
    VALUES
        (1, 'Kỹ thuật'::TEXT),
        (2, 'Kinh doanh'),
        (3, 'Hỗ trợ')
),
employees(employee_id, employee_name, department_id) AS (
    VALUES
        (101, 'An'::TEXT, 1),
        (102, 'Bình', 1),
        (103, 'Chi', 2)
)
SELECT
    d.department_id,
    d.department_name,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Với `LEFT JOIN`, phòng “Hỗ trợ” vẫn xuất hiện với cột nhân viên `NULL`. Nếu đổi thành `INNER JOIN`, phòng không có nhân viên sẽ bị loại khỏi kết quả.

Đây là cách tạo bài tập gọn và **giữ nguyên toàn bộ tiền đề** mà không cần bảo người học cài một bộ database mẫu.

### 15.1. Bộ dữ liệu nhỏ làm rõ trường hợp biên

Bạn có thể chủ động tạo:

- Khách chưa từng đặt hàng.
- Khách có nhiều đơn.
- Đơn có giá trị `NULL` ở một trường optional.
- Hàng bị trùng khóa trong dữ liệu đầu vào.
- Mã trạng thái không tồn tại trong bảng ánh xạ.
- Giá trị 0 và số âm để kiểm tra `CHECK` logic.

Một bảng dữ liệu production ngẫu nhiên có thể không chứa đầy đủ những trường hợp biên cần minh họa. `VALUES` làm chúng **rõ ràng và tái tạo được**.

## 16. VALUES cho GROUP BY và các phép tổng hợp

~~~sql
WITH sales(sale_id, category, amount) AS (
    VALUES
        (1, 'book'::TEXT, 150000.00::NUMERIC),
        (2, 'book', 200000.00::NUMERIC),
        (3, 'hardware', 420000.00::NUMERIC),
        (4, 'hardware', 180000.00::NUMERIC),
        (5, 'book', 50000.00::NUMERIC)
)
SELECT
    category,
    COUNT(*) AS number_of_sales,
    SUM(amount) AS total_amount,
    ROUND(AVG(amount), 2) AS average_amount
FROM sales
GROUP BY category
ORDER BY category;
~~~

Kết quả kỳ vọng:

| category | number_of_sales | total_amount | average_amount |
|---|---:|---:|---:|
| book | 3 | 400000.00 | 133333.33 |
| hardware | 2 | 600000.00 | 300000.00 |

`VALUES` giúp kiểm chứng kết quả bằng phép tính tay trước khi áp dụng truy vấn tổng hợp cho bảng thật.

### 16.1. Không nhầm COUNT(*) với COUNT(column)

~~~sql
WITH samples(v) AS (
    VALUES
        (10),
        (NULL::INTEGER),
        (20)
)
SELECT
    COUNT(*) AS all_rows,
    COUNT(v) AS non_null_rows,
    SUM(v) AS total_value
FROM samples;
~~~

Kết quả:

- `COUNT(*) = 3` vì có ba hàng.
- `COUNT(v) = 2` vì một hàng có `NULL`.
- `SUM(v) = 30` vì `SUM` bỏ qua `NULL`.

Với dữ liệu mẫu nhỏ, các khác biệt này rất dễ quan sát.

## 17. VALUES để thử CASE, COALESCE và hàm xử lý

~~~sql
WITH examples(score) AS (
    VALUES
        (95),
        (70),
        (45),
        (NULL::INTEGER)
)
SELECT
    score,
    CASE
        WHEN score IS NULL THEN 'Chưa có điểm'
        WHEN score >= 85 THEN 'Giỏi'
        WHEN score >= 60 THEN 'Đạt'
        ELSE 'Cần học thêm'
    END AS classification
FROM examples
ORDER BY score NULLS LAST;
~~~

Thay vì viết nhiều query rời:

~~~sql
SELECT CASE WHEN 95 >= 85 THEN 'Giỏi' ELSE 'Khác' END;
~~~

ta có thể kiểm tra nhiều nhánh logic trong **một tập dữ liệu**. Đây là cách hữu ích để thử điều kiện SQL, hàm xử lý chuỗi hoặc biểu thức ngày tháng trước khi đưa vào query phức tạp.

## 18. CROSS JOIN giữa hai danh sách VALUES

`CROSS JOIN` tạo tất cả tổ hợp giữa hàng của hai tập dữ liệu.

~~~sql
WITH
colors(color_code) AS (
    VALUES ('red'::TEXT), ('blue'), ('green')
),
sizes(size_code) AS (
    VALUES ('S'::TEXT), ('M')
)
SELECT
    c.color_code,
    s.size_code
FROM colors AS c
CROSS JOIN sizes AS s
ORDER BY c.color_code, s.size_code;
~~~

Có 3 màu và 2 cỡ, nên kết quả có:

\[
3 \times 2 = 6 \text{ tổ hợp}
\]

`CROSS JOIN` thường hữu ích khi tạo tổ hợp kiểm thử: trạng thái × kênh, màu × size, môi trường × feature flag, hoặc bộ tham số × trường hợp biên.

**Cẩn thận:** số hàng kết quả bằng tích số hàng của các nguồn. Với hai bảng thật chứa hàng triệu dòng, `CROSS JOIN` thiếu chủ đích có thể tạo kết quả khổng lồ. Với các danh sách `VALUES` rất nhỏ, tác động thường dễ kiểm soát hơn.

## 19. LATERAL và VALUES: tạo nhiều hàng từ mỗi hàng nguồn

`LATERAL` cho phép một nguồn ở `FROM` tham chiếu tới các cột của nguồn đứng trước nó.

Ví dụ, với mỗi sản phẩm ta muốn trả hai phương án giá: giá gốc và giá ưu đãi:

~~~sql
WITH products(product_id, product_name, base_price) AS (
    VALUES
        (101, 'Sách SQL'::TEXT, 150000.00::NUMERIC),
        (102, 'Bàn phím', 420000.00::NUMERIC)
)
SELECT
    p.product_id,
    p.product_name,
    offer.offer_type,
    offer.offered_price
FROM products AS p
CROSS JOIN LATERAL (
    VALUES
        ('regular'::TEXT, p.base_price),
        ('promotion', p.base_price * 0.90)
) AS offer(offer_type, offered_price)
ORDER BY p.product_id, offer.offer_type;
~~~

Mỗi sản phẩm tạo hai hàng kết quả:

~~~text
Sách SQL  -> regular, promotion
Bàn phím -> regular, promotion
~~~

`VALUES` ở đây không phải danh sách toàn cục độc lập: các biểu thức `p.base_price` tham chiếu **từng hàng sản phẩm hiện tại** thông qua `LATERAL`.

### 19.1. Khi nào cần LATERAL?

- Cần tạo vài hàng dẫn xuất cho mỗi hàng đầu vào.
- Mỗi hàng dẫn xuất dùng giá trị của hàng nguồn.
- Muốn viết phép mở rộng hàng gọn thay vì nhiều `SELECT ... UNION ALL`.
- Cần bảo toàn cấu trúc query theo từng nhóm.

Nếu dữ liệu `VALUES` hoàn toàn cố định và không tham chiếu nguồn trước, `CROSS JOIN` thông thường đã đủ; không cần thêm `LATERAL` cho mọi trường hợp.

## 20. Dùng VALUES để tạo bảng ngưỡng hoặc quy tắc đơn giản

Ví dụ phân loại đơn theo tổng tiền:

~~~sql
WITH
orders(order_id, total_amount) AS (
    VALUES
        (1001, 80000.00::NUMERIC),
        (1002, 250000.00::NUMERIC),
        (1003, 900000.00::NUMERIC)
),
amount_ranges(min_amount, max_amount, label) AS (
    VALUES
        (0.00::NUMERIC, 100000.00::NUMERIC, 'Nhỏ'::TEXT),
        (100000.00::NUMERIC, 500000.00::NUMERIC, 'Vừa'::TEXT),
        (500000.00::NUMERIC, NULL::NUMERIC, 'Lớn'::TEXT)
)
SELECT
    o.order_id,
    o.total_amount,
    r.label
FROM orders AS o
JOIN amount_ranges AS r
    ON o.total_amount >= r.min_amount
   AND (
       r.max_amount IS NULL
       OR o.total_amount < r.max_amount
   )
ORDER BY o.order_id;
~~~

Quy tắc dùng khoảng **nửa mở**: từ `min_amount` (bao gồm) đến `max_amount` (không bao gồm). Nhờ đó đúng ranh giới 100000 hoặc 500000 không bị khớp đồng thời hai khoảng.

### 20.1. Tránh khoảng bị chồng hoặc có lỗ

Dữ liệu inline không tự có `EXCLUDE` constraint hay validation để phát hiện khoảng chồng nhau. Nếu khai báo hai khoảng cùng chứa một tổng tiền, `JOIN` có thể sinh hai dòng cho một đơn.

Nếu quy tắc phân loại được quản trị thường xuyên, liên quan nhiều hệ thống hoặc cần kiểm soát lịch sử, **bảng tra cứu có constraint và version** thường phù hợp hơn danh sách `VALUES` nhúng trực tiếp.

## 21. Dùng VALUES trong INSERT INTO

`VALUES` xuất hiện rất thường xuyên trong câu lệnh `INSERT`:

~~~sql
INSERT INTO some_table (id, name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi');
~~~

Đây là cách chèn nhiều hàng vào bảng có sẵn. Khác với câu `VALUES` độc lập, **`INSERT ... VALUES` có tác dụng ghi dữ liệu** và chịu các constraint của bảng đích.

Để ví dụ chạy được trong một database thực hành, tạo bảng:

~~~sql
CREATE SCHEMA IF NOT EXISTS values_lab;

CREATE TABLE IF NOT EXISTS values_lab.inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Lưu ý: nếu bảng đã tồn tại với schema khác, `IF NOT EXISTS` không xác minh cấu trúc có giống ví dụ; hãy dùng database lab riêng và đừng chạy các câu `UPDATE`/`DELETE` dưới đây trên bảng có dữ liệu thật.

Nạp dữ liệu:

~~~sql
INSERT INTO values_lab.inventory
    (sku, quantity, unit_price)
VALUES
    ('BOOK-SQL', 10, 150000.00),
    ('KEYBOARD', 6, 420000.00),
    ('MOUSE', 18, 175000.00)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    modified_at = statement_timestamp()
RETURNING sku, quantity, unit_price;
~~~

`ON CONFLICT` giúp ví dụ có thể chạy lại theo định nghĩa “đặt tồn kho về các giá trị mẫu”. `EXCLUDED` là hàng dự định chèn; PostgreSQL thực thi kiểm tra constraint trên bảng thật.

**Không sử dụng UPSERT đặt lại số lượng tồn kho này trên dữ liệu nghiệp vụ production.** Đây là seed dành cho bài thực hành.

### 21.1. Khác biệt giữa VALUES độc lập và INSERT ... VALUES

| Cách viết | Có tạo hàng bền vững không? | Có dùng constraint của bảng không? |
|---|---|---|
| `VALUES (1, 'An');` | Không | Không có bảng đích |
| `SELECT * FROM (VALUES ...) AS v(...);` | Không | Không có bảng đích |
| `INSERT INTO t (...) VALUES (...);` | Có, nếu commit thành công | Có |
| `WITH v AS (VALUES ...) SELECT ...;` | Không | Không có bảng đích |
| `INSERT INTO t SELECT ... FROM (VALUES ...) v;` | Có, nếu commit thành công | Có |

**Lưu ý:** “VALUES không tạo bảng” không đồng nghĩa “VALUES không bao giờ ghi dữ liệu”. Khi nó nằm trong `INSERT`, tác dụng ghi đến từ statement `INSERT`.

## 22. DEFAULT trong INSERT ... VALUES

Một số bảng có cột mặc định, như `modified_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

Khi chèn và không cung cấp `modified_at`, PostgreSQL sẽ áp dụng default theo quy tắc `INSERT`. Có thể chỉ định rõ từ khóa `DEFAULT`:

~~~sql
INSERT INTO values_lab.inventory
    (sku, quantity, unit_price, modified_at)
VALUES
    ('MONITOR', 3, 2500000.00, DEFAULT)
ON CONFLICT (sku) DO NOTHING;
~~~

Từ khóa `DEFAULT` có vai trò đặc biệt trong **`INSERT ... VALUES`**. Không suy rằng nó là một literal có thể dùng tùy ý trong mọi biểu thức:

~~~sql
-- Không phải cách hợp lệ để tạo một bảng ảo độc lập:
-- SELECT * FROM (VALUES (DEFAULT)) AS v(x);
~~~

Nếu muốn thử giá trị mặc định của một bảng, hãy dùng `INSERT` trên bảng test phù hợp hoặc xem định nghĩa cột; một `VALUES` độc lập không có bảng đích để biết “default của cột nào”.

## 23. INSERT ... SELECT FROM (VALUES ...)

Đôi khi đầu vào cần lọc, chuẩn hóa hoặc tính toán trước khi chèn.

~~~sql
INSERT INTO values_lab.inventory
    (sku, quantity, unit_price)
SELECT
    v.sku,
    v.quantity,
    v.raw_price * 1.10
FROM (
    VALUES
        ('USB-CABLE'::TEXT, 12, 50000.00::NUMERIC),
        ('ADAPTER'::TEXT, 5, 120000.00::NUMERIC)
) AS v(sku, quantity, raw_price)
WHERE v.quantity > 0
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    modified_at = statement_timestamp()
RETURNING sku, quantity, unit_price;
~~~

Câu này gồm hai bước logic:

1. `VALUES` tạo dữ liệu đầu vào.
2. `INSERT ... SELECT` tính giá mới và chỉ chọn các hàng thỏa điều kiện.

Với bộ dữ liệu nhỏ cần thêm quy tắc biến đổi, cách này rõ nghĩa hơn việc viết mọi phép nhân ngay trong từng hàng `VALUES`.

## 24. UPDATE ... FROM (VALUES ...): cập nhật nhiều hàng theo khóa

Đây là một trong những ứng dụng thực tế mạnh nhất của `VALUES`.

Giả sử cần cập nhật số lượng của một số SKU theo danh sách do người vận hành đã kiểm tra:

~~~sql
UPDATE values_lab.inventory AS i
SET
    quantity = patch.new_quantity,
    modified_at = statement_timestamp()
FROM (
    VALUES
        ('BOOK-SQL'::TEXT, 15),
        ('MOUSE'::TEXT, 20)
) AS patch(sku, new_quantity)
WHERE i.sku = patch.sku
RETURNING i.sku, i.quantity, i.modified_at;
~~~

Không cần viết hai câu `UPDATE` riêng biệt.

### 24.1. Vì sao WHERE là bắt buộc về mặt ý nghĩa?

Nếu thiếu điều kiện nối `i.sku = patch.sku`, câu `UPDATE ... FROM` có thể tạo một phép ghép không mong muốn giữa bảng đích và danh sách cập nhật, khiến dữ liệu bị thay đổi ngoài phạm vi dự kiến.

Ví dụ **nguy hiểm**:

~~~sql
-- KHÔNG CHẠY:
-- UPDATE values_lab.inventory AS i
-- SET quantity = patch.new_quantity
-- FROM (VALUES ('BOOK-SQL', 15), ('MOUSE', 20))
--      AS patch(sku, new_quantity);
~~~

Câu trên không xác định SKU nào nhận lượng nào, vì không có điều kiện nối. Trong cập nhật dữ liệu thật, luôn kiểm tra tập hàng sẽ bị tác động trước.

### 24.2. Dùng SELECT xem trước tập hàng khớp

~~~sql
SELECT
    i.sku,
    i.quantity AS current_quantity,
    patch.new_quantity
FROM values_lab.inventory AS i
JOIN (
    VALUES
        ('BOOK-SQL'::TEXT, 15),
        ('MOUSE'::TEXT, 20)
) AS patch(sku, new_quantity)
    ON i.sku = patch.sku
ORDER BY i.sku;
~~~

Sau khi kiểm tra kết quả, mới thực thi `UPDATE` trong transaction phù hợp.

### 24.3. Cảnh báo: khóa trùng trong nguồn UPDATE

Nếu hai hàng `VALUES` có cùng `sku` nhưng `new_quantity` khác nhau:

~~~sql
-- Nguồn cập nhật có hai hàng cùng khóa:
-- VALUES ('BOOK-SQL', 15), ('BOOK-SQL', 99)
~~~

`UPDATE ... FROM` có thể tạo nhiều hàng nguồn khớp với một hàng đích. PostgreSQL chỉ dùng một hàng nguồn cho một lượt cập nhật hàng đích, nhưng **không nên dựa vào việc hàng nào được chọn**.

Điều kiện cần thiết: nguồn cập nhật phải có **tối đa một hàng cho mỗi khóa đích**. Kiểm tra:

~~~sql
WITH patch(sku, new_quantity) AS (
    VALUES
        ('BOOK-SQL'::TEXT, 15),
        ('BOOK-SQL', 99),
        ('MOUSE', 20)
)
SELECT sku, COUNT(*) AS count_per_sku
FROM patch
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Trong production, cần từ chối hoặc giải quyết duplicate theo quy tắc đã xác định, không để kết quả chọn hàng bất định.

## 25. DELETE ... USING (VALUES ...): xóa có chọn lọc

PostgreSQL hỗ trợ nguồn `USING` trong `DELETE` tương tự cách `UPDATE` dùng `FROM`.

Ví dụ minh họa **trong transaction sẽ ROLLBACK**:

~~~sql
BEGIN;

DELETE FROM values_lab.inventory AS i
USING (
    VALUES
        ('MOUSE'::TEXT),
        ('KEYBOARD'::TEXT)
) AS removal(sku)
WHERE i.sku = removal.sku
RETURNING i.sku, i.quantity;

ROLLBACK;
~~~

Điều này minh họa cách đối chiếu các khóa cần xóa bằng một danh sách inline. Vì `ROLLBACK`, thay đổi sẽ không được giữ nếu các câu lệnh trong transaction thực thi như dự kiến.

**Không được nhầm với việc VALUES tự xóa dữ liệu.** Tác động đến bảng đích đến từ `DELETE`, và `WHERE` quyết định hàng nào bị xóa.

### 25.1. Với danh sách nhỏ đơn cột, IN có thể đơn giản hơn

~~~sql
-- Chỉ minh họa; không chạy nếu không muốn xóa dữ liệu test.
-- DELETE FROM values_lab.inventory
-- WHERE sku IN ('MOUSE', 'KEYBOARD');
~~~

Dùng `USING (VALUES ...)` khi danh sách có nhiều cột, có metadata bổ sung hoặc cần logic nối rõ ràng. Không phức tạp hóa một điều kiện `IN` đơn giản.

## 26. Thực hành an toàn với câu lệnh ghi dữ liệu

Khi `VALUES` được dùng để điều khiển `UPDATE`/`DELETE`/`INSERT`, cần thực hiện trong đúng phạm vi:

1. **Xác minh môi trường:** host, database, schema, role và transaction.
2. **Chỉ định khóa có nghĩa:** mã hoặc primary key dùng để nối dữ liệu.
3. **Kiểm tra duplicate trong nguồn:** nhất là với `UPDATE ... FROM`.
4. **Chạy SELECT xem trước:** dùng cùng điều kiện nối/lọc.
5. **Bắt đầu transaction** nếu quy trình cần rollback và lệnh tương thích.
6. **Dùng RETURNING** để quan sát hàng thực sự thay đổi.
7. **Kiểm tra ràng buộc và số hàng mong đợi** trước khi commit.
8. **COMMIT hoặc ROLLBACK có chủ đích.**

Không dùng file danh sách ID do người khác gửi mà không xác minh schema, miền dữ liệu hoặc quyền tác động. Danh sách inline càng ngắn càng dễ đọc, nhưng chỉ cần một khóa gõ sai cũng có thể ảnh hưởng tới đối tượng ngoài dự kiến.

### 26.1. Kiểm soát số hàng kỳ vọng

Ví dụ muốn thay chính xác hai SKU, có thể dùng một lệnh nguồn rồi kiểm tra kết quả trong transaction của ứng dụng. PostgreSQL cung cấp `RETURNING`; client nhận các hàng và có thể so sánh số lượng trước khi commit.

~~~sql
BEGIN;

UPDATE values_lab.inventory AS i
SET
    quantity = patch.new_quantity,
    modified_at = statement_timestamp()
FROM (
    VALUES
        ('BOOK-SQL'::TEXT, 10),
        ('MOUSE'::TEXT, 18)
) AS patch(sku, new_quantity)
WHERE i.sku = patch.sku
RETURNING i.sku, i.quantity;

-- Kiểm tra kết quả ở client trước khi quyết định.
ROLLBACK;
~~~

Bài này dùng `ROLLBACK` để thử an toàn; một chương trình thực tế cần cơ chế quyết định commit trong transaction theo logic và kiểm tra được.

## 27. VALUES, UNNEST và generate_series: chọn công cụ nào?

Cả ba đều tạo tập hàng mà không nhất thiết cần bảng vật lý, nhưng mục tiêu khác nhau.

### 27.1. VALUES: liệt kê những hàng cụ thể

~~~sql
SELECT *
FROM (
    VALUES
        (101, 'A'::TEXT),
        (205, 'B'),
        (900, 'C')
) AS v(id, label);
~~~

Phù hợp khi **mỗi hàng có ý nghĩa riêng** và số lượng nhỏ.

### 27.2. generate_series: sinh dãy có quy luật

~~~sql
SELECT n
FROM generate_series(1, 10) AS n;
~~~

Dễ hơn nhiều so với:

~~~sql
VALUES
    (1), (2), (3), (4), (5),
    (6), (7), (8), (9), (10);
~~~

Khi cần 10.000 số liên tiếp hoặc dãy ngày/giờ đều đặn, `generate_series` thường phù hợp hơn `VALUES`.

### 27.3. unnest: biến một array thành tập hàng

~~~sql
SELECT product_id
FROM unnest(
    ARRAY[101, 205, 900]::INTEGER[]
) AS x(product_id);
~~~

Phù hợp khi ứng dụng đang có một array hoặc muốn truyền danh sách cùng kiểu qua tham số.

Với nhiều mảng song song, phải kiểm soát cách các phần tử được ghép theo vị trí và cách xử lý độ dài không bằng nhau. Nếu mỗi hàng có nhiều trường độc lập, `VALUES` hoặc một cấu trúc record rõ ràng thường dễ đọc hơn.

### 27.4. Bảng tạm khi nào phù hợp hơn?

Nếu danh sách đầu vào có hàng chục nghìn/hàng triệu hàng, cần index, thống kê, kiểm tra tính duy nhất hoặc được tái sử dụng trong nhiều câu SQL, nên cân nhắc:

- `CREATE TEMP TABLE` và nạp dữ liệu vào bảng tạm.
- Bảng staging với constraint, quyền và quy trình quản lý.
- `COPY` để tải nhiều hàng hiệu quả.
- Dữ liệu từ bảng thật hoặc nguồn `SELECT` đã được chuẩn hóa.
- Truyền array/JSON/recordset có cấu trúc phù hợp ở tầng ứng dụng.

`VALUES` **không có giới hạn hàng nhỏ cố định về mặt cú pháp** mà ta phải ghi nhớ trong bài, nhưng danh sách quá lớn gây tăng kích thước SQL, thời gian parse/plan, số tham số và chi phí truyền. Không dùng một câu `VALUES` vài trăm nghìn hàng chỉ vì “không cần tạo bảng”.

## 28. Bảng so sánh các phương án tạo tập hàng

| Phương án | Nguồn dữ liệu | Tốt nhất khi | Giới hạn đáng chú ý |
|---|---|---|---|
| `VALUES` | Biểu thức viết trực tiếp | Vài hàng cố định | Dài dòng nếu nhiều hàng; không có constraint/index riêng |
| `SELECT` không FROM | Biểu thức một hàng | Kiểm thử phép tính đơn | Không tự liệt kê nhiều hàng |
| `UNION ALL` | Nhiều query ghép | Kết hợp nguồn SELECT | Dài hơn VALUES cho literal |
| `generate_series` | Dãy có quy luật | Số/ngày/giờ liên tiếp | Không phù hợp các bản ghi bất kỳ |
| `unnest` | Array | Danh sách đầu vào từ ứng dụng | Cần quản lý kiểu/thứ tự/ghép mảng |
| `jsonb_to_recordset` | Array JSON objects | Đầu vào JSON có cấu trúc | Cần khai báo kiểu và kiểm tra dữ liệu |
| Temp table | Hàng lưu trong session/transaction theo cấu hình | Dữ liệu lớn, nhiều statement | Cần quản lý vòng đời, index, nạp dữ liệu |
| Staging table | Hàng thực trong database | Import/batch có kiểm soát | Cần quyền, cleanup, constraints và monitoring |

Không nên chọn `VALUES` chỉ để tránh tạo bảng trong một ứng dụng có dữ liệu tham chiếu lâu dài. Mục tiêu là **đơn giản và đúng ngữ nghĩa**, không phải luôn viết ít DDL nhất.

## 29. VALUES với dữ liệu đến từ người dùng: bảo vệ khỏi SQL injection

Giả sử ứng dụng nhận danh sách SKU và số lượng. Một cách nguy hiểm là nối trực tiếp dữ liệu người dùng vào chuỗi SQL:

~~~text
"VALUES ('" + userSku + "', " + userQuantity + ")"
~~~

Nếu `userSku` chứa dấu nháy hoặc nội dung không mong muốn, câu SQL có thể sai cú pháp hoặc bị lợi dụng để thay đổi ý nghĩa truy vấn.

Cần dùng **prepared statements / bind parameters**:

~~~sql
SELECT
    input.sku,
    input.requested_quantity
FROM (
    VALUES
        (CAST(? AS TEXT), CAST(? AS INTEGER)),
        (CAST(? AS TEXT), CAST(? AS INTEGER))
) AS input(sku, requested_quantity);
~~~

Dấu `?` là placeholder theo JDBC; nó không phải cú pháp SQL đầy đủ để chạy trực tiếp trong `psql` như một câu query ad hoc. Driver/binding sẽ cung cấp giá trị với cơ chế tham số.

### 29.1. Số lượng hàng thay đổi phải xử lý thế nào?

Với 2 hàng, một prepared statement có 4 tham số. Nếu số hàng thay đổi mỗi lần, có thể:

- Tạo SQL với **số placeholder phù hợp**, nhưng tuyệt đối không ghép giá trị người dùng trực tiếp.
- Dùng array parameter và `unnest` khi các cột có kiểu/phép ghép phù hợp.
- Dùng bảng tạm hoặc staging table cho batch lớn.
- Dùng batch API của driver hoặc cơ chế COPY khi nạp dữ liệu lớn.

Không để người dùng điều khiển trực tiếp SQL identifier như tên bảng hoặc cột qua placeholder giá trị; identifier cần validation và cách quote riêng nếu buộc phải dynamic.

## 30. Cách lưu thứ tự đầu vào khi ứng dụng gửi danh sách

Với danh sách tìm kiếm:

~~~text
MOUSE, BOOK-SQL, KEYBOARD
~~~

ứng dụng có thể muốn hiển thị kết quả **đúng thứ tự người dùng chọn**, không theo thứ tự alphabet.

Một câu SQL dùng `VALUES`:

~~~sql
SELECT
    wanted.input_position,
    wanted.sku,
    i.quantity,
    i.unit_price
FROM (
    VALUES
        (1, 'MOUSE'::TEXT),
        (2, 'BOOK-SQL'::TEXT),
        (3, 'KEYBOARD'::TEXT)
) AS wanted(input_position, sku)
LEFT JOIN values_lab.inventory AS i
    ON i.sku = wanted.sku
ORDER BY wanted.input_position;
~~~

Ưu điểm:

- Có thể giữ lại SKU không tìm thấy (`LEFT JOIN` trả cột của bảng inventory là NULL).
- Kết quả theo đúng thứ tự đầu vào.
- Có thể giữ cả SKU trùng trong input nếu nghiệp vụ cần biết từng vị trí.
- Không phải phụ thuộc thứ tự tự nhiên của dữ liệu từ index hoặc JOIN.

Nếu danh sách SKU trở thành rất lớn, `unnest(array) WITH ORDINALITY` có thể gọn hơn.

## 31. UNION ALL so với VALUES: có giống nhau hoàn toàn?

Cả hai có thể tạo cùng hình dạng dữ liệu trong ví dụ đơn giản:

~~~sql
VALUES
    (1, 'A'),
    (2, 'B');
~~~

~~~sql
SELECT 1, 'A'
UNION ALL
SELECT 2, 'B';
~~~

Nhưng đừng cho rằng hai cách luôn có **cùng quy tắc phân giải kiểu trong mọi biểu thức phức tạp**. Khi ghép nhiều `SELECT` bằng các phép tập hợp, thứ tự/phạm vi phân giải kiểu và các phép ép kiểu có thể làm kết quả khác kỳ vọng.

Với `VALUES`, PostgreSQL xác định một kiểu chung cho **các biểu thức tương ứng của từng cột**. Nếu muốn ổn định, hãy cast tường minh, nhất là:

- Cột có nhiều `NULL`.
- Cột trộn số nguyên và số thập phân.
- Cột có JSON/JSONB.
- Cột có ngày giờ.
- Cột chứa các literal chỉ được suy luận kiểu từ ngữ cảnh.
- Cột dùng ở phép JOIN với bảng thật.

## 32. VALUES không có primary key, foreign key hoặc index riêng

Một bảng thật có thể khai báo:

~~~sql
CREATE TABLE values_lab.reference_status (
    status_code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);
~~~

Bảng này có ràng buộc không trùng khóa. Với tập inline:

~~~sql
VALUES
    ('new', 'Mới tạo'),
    ('new', 'Chưa xử lý');
~~~

cả hai hàng đều có thể xuất hiện; `VALUES` tự nó **không từ chối duplicate**.

Tương tự, một tập `VALUES` có thể chứa số âm hoặc mã không tồn tại. Việc giá trị có hợp lệ hay không được quyết định khi bạn:

- Thêm điều kiện `WHERE`/`CHECK` logic trong truy vấn.
- JOIN tới bảng tham chiếu.
- `INSERT` vào bảng có constraint.
- Thực hiện validation ở ứng dụng.
- Dùng phép đối soát/aggregation.

**Hãy phân biệt “đầu vào thử nghiệm” và “dữ liệu đã được bảo đảm ràng buộc”.** Tập giá trị inline rất tiện, nhưng không phải data model thay thế schema có khóa và constraints.

## 33. Biểu thức VALUES trong EXPLAIN và thực thi

Ví dụ:

~~~sql
EXPLAIN
SELECT v.id, v.label
FROM (
    VALUES
        (1, 'A'::TEXT),
        (2, 'B'),
        (3, 'C')
) AS v(id, label)
WHERE v.id >= 2;
~~~

Bạn có thể thấy một kế hoạch liên quan tới `Values Scan` hoặc dạng kế hoạch tối ưu hóa khác tùy phiên bản, biểu thức và cách planner biến đổi truy vấn.

Điều cần hiểu:

- PostgreSQL phải lập kế hoạch để tạo và tiêu thụ các hàng literal.
- Tập này không có index riêng như một bảng vật lý.
- Khi JOIN với bảng lớn, planner có thể chọn cách kết hợp thích hợp.
- Thêm `VALUES` không bảo đảm planner sẽ thực hiện mọi thứ theo thứ tự viết SQL.
- Dữ liệu quá nhiều hàng inline có thể gây chi phí parse/plan đáng kể.

Không kết luận về hiệu năng production chỉ từ câu `EXPLAIN` của ba hàng. Mục tiêu của `VALUES` ở đây là **diễn tả dữ liệu**, còn kế hoạch cuối phụ thuộc toàn bộ query và thống kê.

## 34. Trường hợp biên: cột rỗng, duplicate và cardinality

### 34.1. Không thể tự biểu diễn tập 0 hàng bằng cách bỏ hết tuple

~~~sql
-- Không phải cấu trúc VALUES hợp lệ:
-- VALUES;
~~~

Khi cần tập trống nhưng vẫn có cấu trúc cột:

~~~sql
SELECT
    NULL::INTEGER AS id,
    NULL::TEXT AS label
WHERE FALSE;
~~~

Truy vấn này trả **0 hàng** với các kiểu cột đã định nghĩa.

Một cách khác:

~~~sql
SELECT *
FROM (
    VALUES
        (1::INTEGER, 'A'::TEXT)
) AS v(id, label)
WHERE FALSE;
~~~

Nhưng cách thứ hai vẫn khai báo một hàng rồi lọc bỏ; nếu mục tiêu là tập rỗng theo thiết kế, cách đầu tiên trực tiếp hơn.

### 34.2. Một hàng nhiều cột không phải nhiều hàng

Nhắc lại:

~~~sql
VALUES (1, 2);
~~~

trả một hàng với hai cột, còn:

~~~sql
VALUES (1), (2);
~~~

trả hai hàng một cột. Nếu `JOIN` làm kết quả tăng số hàng, đừng vội kết luận dữ liệu bị nhân do `VALUES`; cần kiểm tra khóa của hai bên và quan hệ một-nhiều.

### 34.3. Duplicate không tự biến mất

~~~sql
VALUES
    (1),
    (1),
    (2);
~~~

trả ba hàng. Nếu cần một tập không trùng:

~~~sql
SELECT DISTINCT v.id
FROM (
    VALUES
        (1),
        (1),
        (2)
) AS v(id)
ORDER BY v.id;
~~~

Kết quả là 1 và 2.

**Không lạm dụng DISTINCT để che lỗi dữ liệu nguồn.** Nếu duplicate là không hợp lệ với nghiệp vụ, nên phát hiện và từ chối nguồn lỗi, thay vì âm thầm gộp khi cập nhật dữ liệu thật.

## 35. Các lỗi phổ biến khi dùng VALUES

### Lỗi 1 — Mỗi hàng có số cột khác nhau

~~~sql
-- VALUES (1, 'A'), (2, 'B', 3);
~~~

**Khắc phục:** mọi tuple phải có cùng số biểu thức; ghi `NULL::type` khi cần giá trị thiếu.

### Lỗi 2 — Không đặt tên cột mà dựa vào column1

Tên mặc định làm query khó đọc và dễ gõ nhầm.

**Khắc phục:** dùng `AS alias(col_a, col_b)` hoặc CTE `WITH data(col_a, col_b) AS (VALUES ...)`.

### Lỗi 3 — Không kiểm soát kiểu dữ liệu

Trộn `NULL`, chuỗi, số và ngày tháng tùy tiện khiến PostgreSQL ép kiểu ngoài dự kiến hoặc báo lỗi.

**Khắc phục:** cast tường minh tại những cột quan trọng.

### Lỗi 4 — Giả định thứ tự các tuple là thứ tự kết quả

`VALUES` không tự bảo đảm thứ tự đầu ra qua các phép biến đổi.

**Khắc phục:** dùng `ORDER BY`; thêm cột `input_position` khi cần giữ thứ tự khai báo.

### Lỗi 5 — Nhầm VALUES độc lập với INSERT

`VALUES` độc lập không lưu hàng; `INSERT ... VALUES` ghi vào bảng đích.

**Khắc phục:** xác định statement bên ngoài và xem rõ nơi dữ liệu được ghi.

### Lỗi 6 — Dùng DEFAULT ngoài INSERT ... VALUES

`DEFAULT` cần ngữ cảnh của cột đích trong `INSERT`.

**Khắc phục:** chỉ dùng từ khóa đó ở vị trí SQL hỗ trợ.

### Lỗi 7 — Bị nhân hàng khi JOIN với mapping trùng khóa

Một mã xuất hiện hai lần trong nguồn lookup có thể làm kết quả JOIN nhân đôi.

**Khắc phục:** kiểm tra cardinality, dùng bảng lookup có unique constraint nếu cần.

### Lỗi 8 — UPDATE ... FROM có nhiều source rows cho cùng target

Kết quả chọn hàng nguồn không nên được dự đoán.

**Khắc phục:** bảo đảm một khóa đích chỉ khớp tối đa một hàng nguồn; validation trước update.

### Lỗi 9 — Quên điều kiện WHERE của UPDATE/DELETE

Các câu ghi có thể tác động quá nhiều hàng.

**Khắc phục:** dùng SELECT xem trước, transaction và RETURNING.

### Lỗi 10 — NOT IN với NULL

Kết quả có thể là UNKNOWN thay vì TRUE.

**Khắc phục:** kiểm tra semantics `NULL`; dùng `NOT EXISTS` khi mục tiêu là anti-join.

### Lỗi 11 — Nhúng danh sách hàng nghìn/hàng triệu giá trị

SQL trở nên dài, khó truyền và tốn parse/plan.

**Khắc phục:** cân nhắc `unnest`, bảng tạm, staging table, `COPY` hoặc batch API.

### Lỗi 12 — Ghép trực tiếp input người dùng vào VALUES

Tạo nguy cơ SQL injection và lỗi escape.

**Khắc phục:** dùng tham số, cast phù hợp và validation.

### Lỗi 13 — Dùng VALUES làm cấu hình chung lâu dài

Nhiều query lặp cùng một danh mục, nhưng mỗi lần sửa cần chỉnh nhiều nơi.

**Khắc phục:** chuyển sang bảng tra cứu versioned có ràng buộc và quản trị.

### Lỗi 14 — Dùng literal thời gian động cho fixture cố định

`now()` tạo kết quả khác ở những lần chạy khác nhau.

**Khắc phục:** dùng `DATE`/`TIMESTAMPTZ` literal cố định nếu bài test cần đầu vào bất biến.

### Lỗi 15 — Dùng TEXT rồi quên kiểu đích

Một cột nguồn `VALUES` là `TEXT` nhưng bảng đích cần `UUID`/`JSONB`/`DATE` và conversion không rõ.

**Khắc phục:** cast rõ ràng và kiểm tra kiểu với `pg_typeof` khi thiết kế ví dụ.

## 36. Tình huống thực tế: bảng ánh xạ mã trạng thái tạm cho báo cáo

Một báo cáo cần ánh xạ bốn mã trạng thái nhưng hệ thống chưa có bảng lookup, và yêu cầu chỉ áp dụng **trong một câu SQL**.

Dữ liệu giao dịch được mô phỏng:

~~~sql
WITH
orders(order_id, status_code, amount) AS (
    VALUES
        (1001, 'new'::TEXT, 120000.00::NUMERIC),
        (1002, 'paid', 350000.00::NUMERIC),
        (1003, 'cancelled', 90000.00::NUMERIC),
        (1004, 'paid', 210000.00::NUMERIC),
        (1005, 'unknown', 50000.00::NUMERIC)
),
status_map(status_code, status_label, contributes_to_revenue) AS (
    VALUES
        ('new'::TEXT, 'Mới tạo'::TEXT, FALSE),
        ('paid', 'Đã thanh toán', TRUE),
        ('cancelled', 'Đã hủy', FALSE)
)
SELECT
    o.status_code,
    COALESCE(m.status_label, 'Chưa định nghĩa') AS status_label,
    COUNT(*) AS order_count,
    SUM(o.amount) AS amount_all,
    SUM(o.amount) FILTER (
        WHERE m.contributes_to_revenue = TRUE
    ) AS paid_amount
FROM orders AS o
LEFT JOIN status_map AS m
    ON m.status_code = o.status_code
GROUP BY
    o.status_code,
    COALESCE(m.status_label, 'Chưa định nghĩa')
ORDER BY o.status_code;
~~~

Bài toán minh họa:

- `VALUES` tạo danh sách đơn và bảng ánh xạ trong cùng một statement.
- `LEFT JOIN` bảo toàn mã chưa định nghĩa.
- `GROUP BY` tổng hợp theo mã.
- `FILTER` tính tổng cho những trạng thái được đánh dấu có đóng góp doanh thu.
- `paid_amount` có thể là `NULL` nếu không có hàng nào thỏa filter trong một nhóm; nếu muốn hiển thị 0, dùng `COALESCE`.

**Không suy rằng “Đã thanh toán” luôn là định nghĩa doanh thu hợp lệ trong mọi hệ thống kế toán.** Quy tắc doanh thu ở đây chỉ là ví dụ kỹ thuật. Khi dùng trong production, cần mô hình nghiệp vụ và bảng mã trạng thái được quản trị có version.

## 37. Khi nào không nên dùng VALUES?

Một câu trả lời tốt về `VALUES` phải có ranh giới rõ ràng.

Không nên tiếp tục nhúng dữ liệu trực tiếp khi:

- Danh mục có nhiều dòng và được quản lý độc lập với SQL.
- Nhiều service phải dùng cùng danh mục.
- Cần lưu lịch sử thay đổi của một hàng tham chiếu.
- Cần phân quyền riêng ai được sửa từng danh mục.
- Cần foreign key từ nhiều bảng tới mã danh mục.
- Cần index hoặc thống kê cho tập dữ liệu lớn.
- Dữ liệu đến từ upload/file có thể chứa hàng triệu bản ghi.
- Dữ liệu có secret hoặc thông tin cá nhân không được phép lưu trong source SQL.
- Query phải dùng lại tập đầu vào qua nhiều statement khác nhau.

Trong các trường hợp này, **bảng thật hoặc bảng tạm** thường phù hợp hơn. `VALUES` mạnh nhất ở phạm vi **nhỏ, tường minh, có thể review trực tiếp cùng câu SQL**.

## 38. Checklist khi dùng VALUES trong bài tập và dự án

Trước khi chạy một câu SQL dùng `VALUES`, hãy tự hỏi:

1. Mỗi tuple đã có cùng số cột chưa?
2. Cột đã có alias có ý nghĩa chưa?
3. Những cột quan trọng đã được cast về đúng kiểu chưa?
4. `NULL` đã được xử lý theo semantics mong muốn chưa?
5. Có cần `ORDER BY` hoặc cột thứ tự đầu vào không?
6. Nguồn lookup có thể chứa duplicate khóa không?
7. `JOIN` có thể làm nhân hàng hoặc loại hàng ngoài ý muốn không?
8. Nếu `VALUES` nằm trong `UPDATE`/`DELETE`, đã kiểm tra khóa nối và số hàng chưa?
9. Nếu đến từ người dùng, dữ liệu đã được bind bằng parameter chưa?
10. Danh sách có còn đủ nhỏ để inline không?
11. Dữ liệu là fixture thử nghiệm hay dữ liệu tham chiếu nên lưu bền vững?
12. Nếu dùng nhiều lần trong ứng dụng, có nên chuyển sang lookup table/migration không?

Checklist chỉ nhằm tự thiết kế và sử dụng SQL đúng; khi triển khai thật vẫn phải kiểm tra transaction, quyền, dữ liệu và hiệu năng theo môi trường.

## 39. Bài tập thực hành

### Bài 1 — Một hàng hay ba hàng?

Hãy xác định số hàng và cột của hai câu SQL:

~~~sql
VALUES (1, 2, 3);

VALUES
    (1),
    (2),
    (3);
~~~

**Gợi ý:** câu đầu là một hàng ba cột, câu sau là ba hàng một cột.

### Bài 2 — Đặt alias

Viết tập `VALUES` gồm ba sản phẩm, mỗi sản phẩm có ID, tên và giá. Đặt alias `product_id`, `product_name` và `price`.

**Gợi ý:** `FROM (VALUES ...) AS p(product_id, product_name, price)`.

### Bài 3 — Ép kiểu NUMERIC

Tạo hai hàng giá tiền, ép cột giá về `NUMERIC(12,2)` và dùng `pg_typeof` quan sát.

**Gợi ý:** cast tại từng biểu thức hoặc ít nhất biểu thức đủ xác định kiểu chung.

### Bài 4 — Xử lý NULL

Tạo ba nhân viên, một người không có số điện thoại. Tìm người chưa có số điện thoại.

**Gợi ý:** `NULL::TEXT` và `WHERE phone IS NULL`.

### Bài 5 — Sắp xếp

Tạo `VALUES (3,'C'),(1,'A'),(2,'B')`. Viết truy vấn bảo đảm kết quả theo 1,2,3.

**Gợi ý:** `ORDER BY id` sau khi đặt alias.

### Bài 6 — Giữ thứ tự người dùng

Danh sách input là KEYBOARD, MOUSE, BOOK. Làm cách nào giữ nguyên thứ tự đó sau khi JOIN tới bảng sản phẩm?

**Gợi ý:** tạo `input_position` trong `VALUES` và sắp xếp theo cột này.

### Bài 7 — CTE với VALUES

Viết `WITH levels(code,label) AS (VALUES ...)` rồi lọc một mã cụ thể.

**Gợi ý:** dùng `SELECT ... FROM levels WHERE code = ...`.

### Bài 8 — LEFT JOIN và mã không có ánh xạ

Tạo hai đơn hàng với trạng thái `paid` và `unknown`, chỉ có mapping `paid`. Tại sao `LEFT JOIN` và `INNER JOIN` cho số hàng khác nhau?

**Gợi ý:** hàng thiếu mapping được giữ lại bởi LEFT JOIN.

### Bài 9 — Kiểm tra mapping trùng

Dùng `VALUES` tạo hai dòng cùng mã `done`. Viết `GROUP BY ... HAVING COUNT(*) > 1` để tìm mã trùng.

**Gợi ý:** alias cột `status_code` và nhóm theo cột đó.

### Bài 10 — IN theo hai cột

Có ba cặp `(customer_id, product_id)`. Chỉ chọn những hàng thuộc danh sách hai cặp cho phép.

**Gợi ý:** `WHERE (customer_id, product_id) IN (VALUES (...), (...))`.

### Bài 11 — NOT IN có NULL

Dự đoán kết quả:

~~~sql
SELECT 5 NOT IN (1, 2, NULL);
~~~

**Gợi ý:** kết quả UNKNOWN/NULL, không phải TRUE.

### Bài 12 — EXISTS

Dùng một tập `VALUES` làm nguồn danh sách khách hàng hợp lệ và lọc những đơn có khách hàng nằm trong danh sách.

**Gợi ý:** `WHERE EXISTS (SELECT 1 FROM (VALUES...) AS a(id) WHERE a.id = o.customer_id)`.

### Bài 13 — GROUP BY

Tạo bốn hàng doanh thu thuộc hai nhóm và tính tổng từng nhóm bằng `SUM`.

**Gợi ý:** `WITH sales(category, amount) AS (VALUES ...)`.

### Bài 14 — CROSS JOIN

Tạo hai màu và ba size. Kết quả `CROSS JOIN` có bao nhiêu hàng?

**Gợi ý:** 2 × 3 = 6.

### Bài 15 — LATERAL

Với hai sản phẩm có giá gốc, dùng `CROSS JOIN LATERAL (VALUES ...)` tạo hai phương án giá cho từng sản phẩm.

**Gợi ý:** `VALUES ('regular', p.price), ('sale', p.price * 0.9)`.

### Bài 16 — UPDATE có nguồn VALUES

Viết `UPDATE ... FROM (VALUES...)` để thay số lượng của hai SKU trong bảng lab.

**Gợi ý:** khóa nối phải là `i.sku = patch.sku`, không thiếu WHERE.

### Bài 17 — Duplicate trong UPDATE

Điều gì có thể xảy ra nếu có hai hàng nguồn cùng SKU nhưng số lượng mới khác nhau?

**Gợi ý:** không nên dựa vào hàng nào được dùng; phải bảo đảm một hàng nguồn cho mỗi khóa đích.

### Bài 18 — INSERT ... SELECT từ VALUES

Viết `INSERT` chọn những hàng có giá > 0 từ danh sách `VALUES` rồi chèn vào bảng test.

**Gợi ý:** `INSERT ... SELECT ... FROM (VALUES ...) AS v(...) WHERE ...`.

### Bài 19 — DEFAULT

Vì sao `DEFAULT` hợp lệ trong `INSERT ... VALUES` ở một cột có default nhưng không phải literal bình thường trong `SELECT FROM (VALUES ...)`?

**Gợi ý:** cần ngữ cảnh cột của bảng đích.

### Bài 20 — Chọn công cụ thích hợp

Nếu cần sinh dãy 1 đến 100000, nên dùng `VALUES` hay `generate_series`?

**Gợi ý:** `generate_series` ngắn và đúng ý nghĩa hơn.

### Bài 21 — Array làm nguồn

Ứng dụng đã có array ID. Khi nào `unnest` thuận tiện hơn danh sách `VALUES` được lắp động?

**Gợi ý:** khi truyền một mảng đồng kiểu qua parameter và số lượng phần tử thay đổi.

### Bài 22 — Bảng tạm

Một job phải cập nhật 200000 sản phẩm theo file import, có duplicate cần kiểm tra và chạy nhiều statement. Nên dùng `VALUES` khổng lồ hay staging table?

**Gợi ý:** staging/temp table với ràng buộc, validation, index và quy trình batch phù hợp.

### Bài 23 — Chống SQL injection

Tại sao không được nối `userInput` vào chuỗi `VALUES ('...')`? Cách nào an toàn hơn?

**Gợi ý:** prepared statements, placeholder và binding, không ghép dữ liệu trực tiếp.

### Bài 24 — Không có bảng thật

Một người chỉ muốn kiểm thử biểu thức `CASE` với các giá trị 95,70,45,NULL. Có cần `CREATE TABLE` không?

**Gợi ý:** dùng `WITH scores(score) AS (VALUES ...) SELECT CASE ...`, cast NULL về kiểu phù hợp.

## 40. Tổng kết

- **`VALUES` tạo một tập hàng từ biểu thức viết trực tiếp trong SQL**, không cần một bảng dữ liệu có sẵn.
- `VALUES (1,2)` là **một hàng hai cột**, còn `VALUES (1),(2)` là **hai hàng một cột**.
- Các hàng phải có **cùng số cột**; PostgreSQL chọn kiểu chung cho từng cột theo quy tắc suy luận.
- Nên dùng **alias đặt tên cột** hoặc CTE: `FROM (VALUES ...) AS v(id,label)`, `WITH v(id,label) AS (VALUES ...)`.
- **Cast tường minh** giúp ổn định các cột số, ngày giờ, JSONB và những cột chứa `NULL`.
- **Không dựa vào thứ tự khai báo**; dùng `ORDER BY` và cột vị trí nếu cần giữ thứ tự input.
- `VALUES` có thể dùng cùng **`JOIN`, `IN` nhiều cột, `EXISTS`, `GROUP BY`, `CROSS JOIN` và `LATERAL`** để viết những ví dụ SQL tự chứa.
- **`INSERT ... VALUES`** ghi dữ liệu vào bảng, khác `VALUES` độc lập chỉ tạo tập kết quả.
- **`UPDATE ... FROM (VALUES ...)`** và **`DELETE ... USING (VALUES ...)`** rất tiện cho batch nhỏ, nhưng phải kiểm soát khóa nối, duplicate, transaction và số hàng bị tác động.
- `VALUES` **không có constraint, index và vòng đời lưu trữ độc lập**; nếu dữ liệu lớn hoặc được sử dụng lâu dài, hãy cân nhắc bảng tra cứu, temp/staging table, `unnest` hoặc `generate_series`.
- Khi nhận dữ liệu từ ứng dụng, phải dùng **tham số ràng buộc** thay vì ghép literal người dùng vào SQL.

Tư duy quan trọng nhất là xem `VALUES` như **một nguồn dữ liệu có cấu trúc ngay bên trong một câu SQL**. Với vài hàng mẫu, một bảng ánh xạ ngắn hoặc một danh sách khóa cần đối chiếu, nó giúp truy vấn PostgreSQL rõ ràng, tái tạo được và không phải tạo bảng chỉ để thử. Khi nhu cầu chuyển sang dữ liệu lớn, có vòng đời hoặc ràng buộc nghiệp vụ, hãy chuyển sang mô hình lưu trữ phù hợp thay vì kéo dài danh sách `VALUES` vô hạn.
