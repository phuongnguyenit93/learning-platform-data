# Trả giá trị đơn, bảng dữ liệu hoặc nhiều tập kết quả trong SQL

Khi tạo **hàm (function)** hoặc **thủ tục (stored procedure)** trong cơ sở dữ liệu, người viết cần xác định không chỉ *tính toán điều gì* mà còn **trả kết quả dưới hình dạng nào**. Một phép tính tổng doanh thu có thể trả **một số**; danh sách đơn hàng là **một bảng nhiều dòng**; báo cáo gồm phần tổng quan và phần chi tiết có thể cần **hai tập kết quả khác cấu trúc**.

Ba cách trả dữ liệu thường gặp:

~~~text
Một giá trị đơn                   Một tập hàng                 Nhiều tập kết quả
┌───────────────────┐            ┌─────────────────────┐      ┌──────────────────────┐
│ paid_total        │            │ order_id | amount   │      │ Result set 1: orders │
│ 430000.00         │            │ 101      | 100000   │      │ id | date | amount   │
└───────────────────┘            │ 103      | 150000   │      └──────────────────────┘
                                 │ 110      | 180000   │      ┌──────────────────────┐
                                 └─────────────────────┘      │ Result set 2: items  │
                                                              │ order | sku | qty    │
                                                              └──────────────────────┘
~~~

Cần đặc biệt phân biệt:

- **Một kết quả scalar**: ví dụ số `430000`, kiểu `NUMERIC`.
- **Một result set có nhiều dòng**: ví dụ bảng 3 đơn hàng, **vẫn là một tập kết quả**.
- **Nhiều result set**: ví dụ một bảng đơn hàng và một bảng dòng sản phẩm, mỗi bảng có các cột riêng, được trả như các kết quả tách biệt.

Không thể suy ra rằng một hàm `RETURNS TABLE` của PostgreSQL sẽ tự trả *nhiều result set*. `RETURNS TABLE` mô tả **một tập hàng**, dù tập đó có nhiều dòng và nhiều cột. Hệ quản trị và API của ứng dụng quyết định cách xuất và đọc nhiều kết quả riêng biệt.

Bài này thuộc module **Database SQL**, chương **Thủ tục và hàm**, chủ đề **“Trả giá trị đơn, bảng dữ liệu hoặc nhiều tập kết quả”**. Các ví dụ chính dùng **PostgreSQL**; phần so sánh mô tả SQL Server, MySQL/MariaDB, Oracle, SQLite và Java/JDBC.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Chọn dạng đầu ra dựa trên yêu cầu: scalar, bản ghi một dòng, bảng nhiều dòng hoặc nhiều tập kết quả.
2. Tạo hàm PostgreSQL `RETURNS INTEGER`, `RETURNS NUMERIC` và `RETURNS TEXT` bằng `LANGUAGE SQL` hoặc `PL/pgSQL`.
3. Phân biệt `RETURN biểu_thức`, `RETURN QUERY` và `RETURN NEXT`.
4. Tạo hàm `RETURNS TABLE(...)` và `RETURNS SETOF ...`; gọi bằng `SELECT * FROM ham(...)`.
5. Phân biệt tham số `IN`, `OUT`, `INOUT` và việc trả **một hàng nhiều cột** với trả **nhiều hàng**.
6. Biết dùng `CALL` cho procedure PostgreSQL và hiểu kết quả của tham số OUT/INOUT không giống nhiều result set độc lập.
7. Hiểu mẫu `refcursor` khi cần nhiều tập dữ liệu khác cấu trúc trong PostgreSQL, cùng yêu cầu transaction và `FETCH`.
8. Xử lý tập rỗng, giá trị `NULL`, thống kê `COUNT/SUM` và lỗi không có kết quả.
9. Biết cách đọc scalar, một result set và nhiều result set bằng Java/JDBC.
10. So sánh `SELECT` trong stored procedure SQL Server/MySQL, `SYS_REFCURSOR` của Oracle và giới hạn của SQLite.
11. Lựa chọn API ổn định, dễ kiểm thử và không đánh đồng định dạng dữ liệu với hiệu năng truyền tải.

## 2. Bốn hình dạng đầu ra dễ bị nhầm

| Hình dạng | Mẫu ý nghĩa | PostgreSQL thường dùng | Cách nhận |
|---|---|---|---|
| **Một giá trị scalar** | Tổng tiền của khách An: 430000 | Hàm `RETURNS NUMERIC` | `SELECT ham(...)`, 1 ô |
| **Một bản ghi nhiều cột** | Số đơn PAID và tổng tiền | Hàm có nhiều `OUT`; bản ghi composite | `SELECT * FROM ham(...)`, 1 hàng |
| **Một bảng nhiều hàng** | Các đơn của An | `RETURNS TABLE(...)` hoặc `RETURNS SETOF` | `SELECT * FROM ham(...)`, 0..N hàng |
| **Nhiều tập kết quả độc lập** | Danh sách đơn và danh sách chi tiết | PostgreSQL: cursor/refcursor và `FETCH`; hệ khác có thể trả trực tiếp từ procedure | Đọc từng tập bằng API phù hợp |

Hai câu SQL sau không đồng nghĩa về kết quả:

~~~sql
-- Một tập kết quả duy nhất, mỗi hàng gồm nhiều cột:
SELECT order_id, amount
FROM some_order_table;

-- Hai SELECT độc lập:
SELECT ... FROM some_order_table;
SELECT ... FROM some_item_table;
~~~

Ở SQL client, hai SELECT độc lập có thể hiển thị thành hai lưới. Nhưng điều đó **không** có nghĩa mọi hàm của mọi DBMS đều có thể trả trực tiếp hai tập độc lập theo cách đó. Sự hỗ trợ tùy ngữ cảnh và hệ quản trị.

### 2.1. Một cột và một dòng chưa chắc tương ứng một scalar function

Một truy vấn `SELECT SUM(amount) ...` thường trả một hàng chứa một giá trị. Nhưng một hàm `RETURNS TABLE(total NUMERIC)` có thể cũng trả một hàng một cột. **Hình thức trình bày trong SQL client có thể giống nhau**, còn giao diện hợp đồng của hàm khác nhau: trả scalar so với trả quan hệ có thể có 0..N hàng.

### 2.2. Một hàng JSON vẫn là một scalar theo kiểu SQL

Một hàm `RETURNS JSONB` có thể gói trong một giá trị JSON cả danh sách đơn lẫn phần thống kê. Về SQL nó vẫn là **một giá trị của kiểu JSONB**, không phải hai result set độc lập. Cách này có điểm mạnh và hạn chế riêng.

## 3. Hàm khác thủ tục ở điểm nào?

Cả function và procedure đều giúp đóng gói logic ở phía database, nhưng cách gọi và quy tắc trả kết quả có khác biệt.

| Đặc điểm | PostgreSQL function | PostgreSQL procedure |
|---|---|---|
| Cách gọi | Trong biểu thức `SELECT ham(...)` hoặc `FROM ham(...)` | `CALL ten_thu_tuc(...)` |
| Giá trị trả về | Khai báo `RETURNS ...`; có scalar, composite, TABLE/SETOF | Không có `RETURNS ...` kiểu function |
| Tham số OUT/INOUT | Có thể tạo kết quả scalar/composite | `CALL` có thể trả một hàng chứa OUT/INOUT |
| Sử dụng trong JOIN | Hàm table-valued có thể xuất hiện ở FROM/LATERAL | Procedure không dùng trực tiếp như bảng JOIN |
| Điều khiển transaction | Hàm không tự COMMIT/ROLLBACK theo cách tự do | Procedure có quy tắc transaction control riêng và giới hạn ngữ cảnh |
| Nhiều tập dữ liệu | Có thể trả tham chiếu cursor để FETCH từng tập | Có thể dùng tham số refcursor; không tự hiểu nhiều SELECT trong body là nhiều result set |

Đây là bảng **riêng cho PostgreSQL**. SQL Server và MySQL có cách stored procedure xuất tập kết quả trực tiếp bằng các câu SELECT bên trong procedure; đừng áp dụng cơ chế đó nguyên xi cho PostgreSQL.

### 3.1. Không nhầm function trả TABLE với một bảng vật lý

Một hàm `RETURNS TABLE(...)` cho ứng dụng đọc một **tập hàng sinh ra bởi hàm**. Nó không tự tạo bảng lưu trữ bền vững như `CREATE TABLE`.

Ví dụ:

~~~sql
SELECT *
FROM some_table_function(1);
~~~

kết quả có thể nhìn giống SELECT một bảng, nhưng hàng có thể được tính theo tham số và dữ liệu tại thời điểm thực thi.

## 4. Chuẩn bị dữ liệu thực hành PostgreSQL

Ta dùng bốn khách hàng, mười đơn hàng và mười dòng sản phẩm. Các bảng là **TEMP TABLE** trong phiên kết nối PostgreSQL đang thực hành, có tiền tố `lab340_` để tránh trùng với ứng dụng của bạn.

Trong phần sau, ta tạo hàm trong schema tạm `pg_temp`, gọi **có tiền tố `pg_temp.`** để chúng gắn với phiên thực hành. PostgreSQL không dùng cú pháp `CREATE TEMP FUNCTION`; cách minh họa này dùng tên schema tạm hiện hành. Nếu SQL client hoặc chính sách DB của bạn không cho tạo hàm trong schema tương ứng, hãy dùng một schema thử nghiệm riêng có quyền phù hợp và xóa đối tượng khi hoàn tất.

### 4.1. Tạo bảng khách hàng

~~~sql
CREATE TEMP TABLE lab340_customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

INSERT INTO lab340_customers (id, name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dũng');
~~~

### 4.2. Tạo bảng đơn hàng

~~~sql
CREATE TEMP TABLE lab340_orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab340_customers(id),
    order_date DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(12,2) NOT NULL
        CHECK (amount >= 0)
);

INSERT INTO lab340_orders
    (id, customer_id, order_date, status, amount)
VALUES
    (101, 1, DATE '2026-10-01', 'PAID',      100000),
    (102, 1, DATE '2026-10-03', 'NEW',       200000),
    (103, 1, DATE '2026-10-10', 'PAID',      150000),
    (104, 2, DATE '2026-10-02', 'PAID',       50000),
    (105, 2, DATE '2026-10-05', 'CANCELLED',  80000),
    (106, 2, DATE '2026-10-14', 'PAID',      300000),
    (107, 3, DATE '2026-10-04', 'NEW',       120000),
    (108, 3, DATE '2026-10-06', 'PAID',       90000),
    (109, 3, DATE '2026-11-02', 'PAID',      220000),
    (110, 1, DATE '2026-11-09', 'PAID',      180000);
~~~

### 4.3. Tạo bảng dòng đơn hàng

~~~sql
CREATE TEMP TABLE lab340_order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lab340_orders(id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL
        CHECK (unit_price >= 0)
);

INSERT INTO lab340_order_items
    (id, order_id, sku, quantity, unit_price)
VALUES
    (1001, 101, 'BOOK_SQL', 2,  50000),
    (1002, 102, 'BOOK_JAVA',1, 200000),
    (1003, 103, 'BOOK_SQL', 3,  50000),
    (1004, 104, 'NOTE',     1,  50000),
    (1005, 105, 'PEN',      2,  40000),
    (1006, 106, 'COURSE',   3, 100000),
    (1007, 107, 'BOOK_SQL', 2,  60000),
    (1008, 108, 'NOTE',     3,  30000),
    (1009, 109, 'COURSE',   2, 110000),
    (1010, 110, 'COURSE',   3,  60000);
~~~

Mỗi đơn trong tập dữ liệu đơn giản này có một dòng sản phẩm và thành tiền bằng `quantity * unit_price`. Hệ thống thực thường có nhiều dòng mỗi đơn; ta sẽ không viết logic phụ thuộc giả định một-dòng-mỗi-đơn như một quy tắc chung.

### 4.4. Kiểm tra dữ liệu gốc

~~~sql
SELECT
    c.id,
    c.name,
    COUNT(o.id) AS order_count,
    COUNT(o.id) FILTER (WHERE o.status = 'PAID')
        AS paid_order_count,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS paid_total
FROM lab340_customers AS c
LEFT JOIN lab340_orders AS o
    ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
~~~

Kết quả mong đợi:

| Khách | Tổng đơn | Đơn PAID | Tổng tiền PAID |
|---|---:|---:|---:|
| An (1) | 4 | 3 | 430000 |
| Bình (2) | 3 | 2 | 350000 |
| Chi (3) | 3 | 2 | 310000 |
| Dũng (4) | 0 | 0 | 0 |

Tổng thể: **10 đơn**, trong đó **7 PAID**, **2 NEW**, **1 CANCELLED**. Khách Dũng chưa có đơn để kiểm tra trường hợp tập kết quả rỗng.

> Các câu lệnh ở phần sau có thể chạy lần lượt trong cùng phiên. Hàm sử dụng `CREATE OR REPLACE` để tiện thử sửa phần thân; nếu đổi kiểu dữ liệu đầu ra, PostgreSQL có thể yêu cầu DROP hàm cũ rồi CREATE lại vì `OR REPLACE` không cho thay tùy ý kiểu kết quả.

## 5. Trả một giá trị đơn bằng hàm SQL

Bài toán: tính **tổng tiền của các đơn PAID** thuộc một khách hàng.

Đầu vào: `customer_id`. Đầu ra: một số `NUMERIC`.

### 5.1. Định nghĩa hàm RETURNS NUMERIC

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_paid_total(
    p_customer_id INTEGER
)
RETURNS NUMERIC
LANGUAGE SQL
STABLE
AS $fn$
    SELECT COALESCE(SUM(o.amount), 0)
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'PAID';
$fn$;
~~~

Giải thích:

- `CREATE FUNCTION` tạo một hàm.
- `p_customer_id` là tham số đầu vào có kiểu `INTEGER`.
- `RETURNS NUMERIC`: giao diện đầu ra **một giá trị số**.
- `LANGUAGE SQL`: phần thân là câu SQL.
- `STABLE`: khai báo tính chất hàm phù hợp với thao tác đọc dữ liệu ở đây; không đánh dấu `IMMUTABLE` cho hàm đọc bảng có thể thay đổi.
- `SUM` tính tổng tiền đơn PAID.
- `COALESCE(..., 0)` chuyển tổng NULL thành 0.

### 5.2. Gọi hàm

~~~sql
SELECT pg_temp.lab340_paid_total(1) AS paid_total;
~~~

Kết quả:

| paid_total |
|---:|
| 430000 |

Gọi khách khác:

~~~sql
SELECT
    pg_temp.lab340_paid_total(2) AS binh_total,
    pg_temp.lab340_paid_total(3) AS chi_total,
    pg_temp.lab340_paid_total(4) AS dung_total;
~~~

Kết quả tương ứng: **350000**, **310000**, **0**.

### 5.3. Dùng scalar function trong SELECT của bảng khác

~~~sql
SELECT
    c.id,
    c.name,
    pg_temp.lab340_paid_total(c.id) AS paid_total
FROM lab340_customers AS c
ORDER BY c.id;
~~~

Mỗi hàng khách có một giá trị total. Đây vẫn là một câu SELECT trả một result set; hàm bên trong trả scalar cho từng hàng.

**Lưu ý hiệu năng:** gọi hàm tính SUM lặp lại cho rất nhiều khách có thể khiến database phải thực hiện nhiều lần tra cứu/tổng hợp. Với báo cáo lớn, một câu `JOIN + GROUP BY` hoặc tập kết quả tổng hợp theo khách có thể phù hợp hơn. Đóng gói thành function thuận tiện về giao diện không bảo đảm tự động nhanh.

## 6. Trả scalar bằng PL/pgSQL: RETURN và SELECT INTO

Hàm SQL đơn giản thường ngắn gọn. Khi cần nhiều bước kiểm tra, biến cục bộ hoặc nhánh điều kiện, có thể dùng `LANGUAGE plpgsql`.

### 6.1. RETURN một biểu thức

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_order_level(
    p_amount NUMERIC
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $fn$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'UNKNOWN';
    ELSIF p_amount >= 200000 THEN
        RETURN 'HIGH';
    ELSIF p_amount >= 100000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LOW';
    END IF;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT
    pg_temp.lab340_order_level(300000) AS high_value,
    pg_temp.lab340_order_level(150000) AS medium_value,
    pg_temp.lab340_order_level(50000) AS low_value,
    pg_temp.lab340_order_level(NULL) AS unknown_value;
~~~

Kết quả tương ứng: `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`.

`RETURN 'HIGH'` **kết thúc hàm scalar ngay lập tức**, trả về giá trị. Vì hàm này chỉ phụ thuộc tham số và biểu thức thuần, `IMMUTABLE` phù hợp trong phạm vi ví dụ. Khác với `lab340_paid_total` đọc bảng, không nên đánh dấu hàm tính tổng dữ liệu động là IMMUTABLE.

### 6.2. SELECT INTO biến

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_paid_total_pl(
    p_customer_id INTEGER
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $fn$
DECLARE
    v_total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(o.amount), 0)
    INTO v_total
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'PAID';

    RETURN v_total;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT pg_temp.lab340_paid_total_pl(1);
~~~

Kết quả: **430000**.

Trong **PL/pgSQL**, `SELECT ... INTO v_total` lưu kết quả vào biến, không có nghĩa “tạo bảng mới” như một số cách dùng `SELECT INTO` ở SQL mức ngoài. Nếu câu SELECT trả nhiều hàng mà không dùng `STRICT`, hành vi chọn hàng cần được xử lý cẩn trọng; ở đây `SUM` không GROUP BY tạo đúng một hàng tổng hợp.

### 6.3. SELECT INTO STRICT dùng khi cần đúng một dòng

Nếu nghiệp vụ yêu cầu một ID đơn tồn tại:

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_order_amount_strict(
    p_order_id INTEGER
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $fn$
DECLARE
    v_amount NUMERIC;
BEGIN
    SELECT o.amount
    INTO STRICT v_amount
    FROM lab340_orders AS o
    WHERE o.id = p_order_id;

    RETURN v_amount;
END;
$fn$;
~~~

Gọi `pg_temp.lab340_order_amount_strict(101)` trả 100000. Với ID không tồn tại, `INTO STRICT` ném lỗi `NO_DATA_FOUND`; nếu kết quả có nhiều hàng, nó ném lỗi `TOO_MANY_ROWS`. Trong ví dụ, `id` là PRIMARY KEY nên không thể có hơn một hàng cho ID.

**Phân biệt:** hàm tổng hợp không có hàng đầu vào vẫn thường trả một hàng với SUM = NULL/COALESCE = 0; hàm SELECT theo ID với `INTO STRICT` có thể phát sinh lỗi khi ID thiếu.

## 7. NULL, không có hàng và kết quả 0

Đây là ba trạng thái cần phân biệt khi thiết kế hàm:

| Trường hợp | Ví dụ | Ý nghĩa |
|---|---|---|
| Scalar bằng `NULL` | `SUM` trên tập rỗng không dùng COALESCE | Không có giá trị tổng số được xác định |
| Scalar bằng `0` | `COALESCE(SUM(...),0)` | Quy ước tổng không có hàng thành 0 |
| Table function trả **0 hàng** | Khách Dũng không có đơn | Không có bản ghi nào thuộc tập |
| Table function trả **1 hàng với cột NULL** | Query có `LEFT JOIN` và hàng phía phải thiếu | Một hàng kết quả vẫn tồn tại, nhưng vài cột là NULL |

### 7.1. COUNT khác SUM trên tập rỗng

~~~sql
SELECT
    COUNT(*) AS so_don,
    SUM(amount) AS tong_raw,
    COALESCE(SUM(amount), 0) AS tong_quy_uoc
FROM lab340_orders
WHERE customer_id = 4;
~~~

Kết quả: `so_don = 0`, `tong_raw = NULL`, `tong_quy_uoc = 0`.

Quy ước 0 giúp API hiển thị “không phát sinh doanh thu”, nhưng đôi khi nghiệp vụ cần phân biệt **chưa có dữ liệu** và **doanh thu thực sự bằng 0**. Lựa chọn kiểu trả và ý nghĩa NULL phải được ghi rõ trong hợp đồng hàm.

### 7.2. Tham số NULL

Hàm scalar ở mục 5 với `p_customer_id = NULL`:

~~~sql
SELECT pg_temp.lab340_paid_total(NULL);
~~~

được định nghĩa để trả 0 do `WHERE o.customer_id = NULL` không khớp hàng nào và COALESCE chuyển SUM NULL thành 0. Nhưng một API nghiệp vụ có thể muốn **từ chối NULL** thay vì trả 0. Bạn có thể thêm kiểm tra trong PL/pgSQL hoặc xác thực tại lớp gọi.

**Không gắn `STRICT` một cách máy móc:** một function PostgreSQL khai báo `STRICT` sẽ tự trả NULL khi có đối số NULL trước khi chạy thân hàm, có thể thay đổi ngữ nghĩa so với quy tắc trả 0 đang dùng.

## 8. Trả một bảng bằng RETURNS TABLE

Bài toán: tìm những đơn thuộc một khách kể từ một ngày, và trả **các cột có tên rõ ràng**.

### 8.1. Tạo table-valued function bằng LANGUAGE SQL

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_customer_orders(
    p_customer_id INTEGER,
    p_from_date DATE DEFAULT DATE '2026-10-01'
)
RETURNS TABLE (
    order_id INTEGER,
    order_date DATE,
    order_status TEXT,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
AS $fn$
    SELECT
        o.id,
        o.order_date,
        o.status,
        o.amount
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.order_date >= p_from_date;
$fn$;
~~~

`RETURNS TABLE(...)` xác định **kiểu và tên cột đầu ra**. Một lần gọi có thể trả **0, 1 hoặc nhiều hàng**, tất cả có cùng cấu trúc bốn cột.

### 8.2. Gọi bằng SELECT * FROM

~~~sql
SELECT *
FROM pg_temp.lab340_customer_orders(1)
ORDER BY order_date DESC, order_id DESC;
~~~

Kết quả:

| order_id | order_date | order_status | amount |
|---:|---|---|---:|
| 110 | 2026-11-09 | PAID | 180000 |
| 103 | 2026-10-10 | PAID | 150000 |
| 102 | 2026-10-03 | NEW | 200000 |
| 101 | 2026-10-01 | PAID | 100000 |

Khi gọi bỏ ngày, tham số mặc định là 01/10/2026. Gọi với ngày khác:

~~~sql
SELECT *
FROM pg_temp.lab340_customer_orders(
    1, DATE '2026-11-01'
)
ORDER BY order_id;
~~~

Kết quả chỉ có đơn **110**.

### 8.3. Tập rỗng là kết quả hợp lệ

~~~sql
SELECT *
FROM pg_temp.lab340_customer_orders(4);
~~~

Trả **0 hàng**, vì Dũng không có đơn. Nó không trả một hàng giả với order_id NULL. Nếu ứng dụng đọc `ResultSet`, vòng lặp `while (rs.next())` đơn giản không chạy lần nào.

### 8.4. Không nhầm SELECT func với SELECT * FROM func

~~~sql
SELECT pg_temp.lab340_customer_orders(1);
~~~

Đây là cách gọi một set-returning function trong danh sách SELECT, có thể biểu diễn các dòng composite như một cột chứa bản ghi, không tiện cho việc thao tác bảng thông thường.

Để xử lý từng cột, JOIN, lọc hoặc sắp xếp, nên viết:

~~~sql
SELECT order_id, order_status, amount
FROM pg_temp.lab340_customer_orders(1)
WHERE order_status = 'PAID'
ORDER BY amount DESC;
~~~

**Một table-valued function vẫn chỉ trả một result set**, không phải nhiều result set chỉ vì có nhiều dòng.

## 9. RETURNS TABLE trong PL/pgSQL: RETURN QUERY

Khi phải tính điều kiện hoặc ghép nhiều bước, PL/pgSQL cho phép thêm các dòng kết quả bằng `RETURN QUERY`.

### 9.1. Ví dụ lọc các đơn PAID theo ngưỡng tiền

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_paid_orders_min(
    p_min_amount NUMERIC DEFAULT 0
)
RETURNS TABLE (
    order_id INTEGER,
    customer_id INTEGER,
    order_date DATE,
    amount NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $fn$
BEGIN
    IF p_min_amount IS NULL OR p_min_amount < 0 THEN
        RAISE EXCEPTION
            'p_min_amount phải là số không âm';
    END IF;

    RETURN QUERY
    SELECT
        o.id,
        o.customer_id,
        o.order_date,
        o.amount
    FROM lab340_orders AS o
    WHERE o.status = 'PAID'
      AND o.amount >= p_min_amount;

    RETURN;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT *
FROM pg_temp.lab340_paid_orders_min(200000)
ORDER BY amount DESC, order_id;
~~~

Kết quả:

| order_id | customer_id | order_date | amount |
|---:|---:|---|---:|
| 106 | 2 | 2026-10-14 | 300000 |
| 109 | 3 | 2026-11-02 | 220000 |

**Lưu ý:** đơn 110 có 180000 nên không được chọn; đơn 102 là NEW dù tiền 200000 nên cũng không được chọn.

### 9.2. RETURN QUERY không kết thúc hàm ngay

Trong một hàm trả set, `RETURN QUERY` **thêm toàn bộ các hàng từ truy vấn vào tập kết quả đang xây**, không hoạt động như `RETURN gia_tri` của hàm scalar vốn kết thúc ngay.

Sau `RETURN QUERY`, PL/pgSQL có thể thực hiện các statement khác hoặc thêm hàng qua `RETURN NEXT`. `RETURN;` không đối số dùng để kết thúc hàm set-returning; ở cuối thân hàm, nó cũng có thể được lược bỏ theo ngữ cảnh.

### 9.3. Kiểu đầu ra phải tương thích

`RETURNS TABLE` trong PL/pgSQL yêu cầu kết quả `RETURN QUERY` tương thích về **số cột, vị trí và kiểu**. Một cột `VARCHAR(n)` hay `BIGINT` không phải lúc nào cũng tự được diễn giải như `TEXT` hay `INTEGER` theo cách bạn dự đoán.

Nếu cần, hãy ép kiểu rõ ràng:

~~~sql
SELECT
    o.id::INTEGER,
    o.customer_id::INTEGER,
    o.order_date::DATE,
    o.amount::NUMERIC
FROM lab340_orders AS o;
~~~

Đây là một đoạn `SELECT` minh họa kiểu dữ liệu, không thay cho thân hàm đầy đủ. Khi nhận lỗi `structure of query does not match function result type`, hãy đối chiếu **từng cột trong RETURNS TABLE với từng biểu thức SELECT**.

## 10. RETURN NEXT: trả các hàng từng bước

Một hàm set-returning PL/pgSQL có thể cần kiểm tra từng phần tử rồi phát từng hàng qua `RETURN NEXT`.

### 10.1. Ví dụ trả hai mốc thống kê cho một khách

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_customer_metrics(
    p_customer_id INTEGER
)
RETURNS TABLE (
    metric TEXT,
    metric_value NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $fn$
DECLARE
    v_count NUMERIC;
    v_total NUMERIC;
BEGIN
    SELECT
        COUNT(*)::NUMERIC,
        COALESCE(SUM(o.amount), 0)
    INTO v_count, v_total
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'PAID';

    metric := 'PAID_COUNT';
    metric_value := v_count;
    RETURN NEXT;

    metric := 'PAID_TOTAL';
    metric_value := v_total;
    RETURN NEXT;

    RETURN;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT *
FROM pg_temp.lab340_customer_metrics(1);
~~~

Kết quả gồm hai hàng:

| metric | metric_value |
|---|---:|
| PAID_COUNT | 3 |
| PAID_TOTAL | 430000 |

### 10.2. RETURN NEXT khác RETURN biểu thức

Trong hàm có `RETURNS TABLE`, tên cột đầu ra hoạt động như biến trong PL/pgSQL. Ta gán `metric` và `metric_value`, rồi `RETURN NEXT` không đối số để **thêm một hàng**.

`RETURN NEXT` không kết thúc hàm; hai lệnh RETURN NEXT tạo **hai hàng trong một result set**. Nó **không tạo hai result set**.

### 10.3. RETURN QUERY và RETURN NEXT có thể kết hợp

Một hàm PL/pgSQL trả set có thể:

- `RETURN QUERY SELECT ...` để thêm nhiều hàng.
- `RETURN NEXT` để thêm một hàng được tính thủ công.
- `RETURN;` để kết thúc.

Nhưng việc gom nhiều loại bản ghi khác cấu trúc vào một bảng chung bằng cột `metric` và `metric_value` có thể làm mất sự rõ ràng kiểu dữ liệu. Nếu hai nhóm dữ liệu khác cấu trúc hoàn toàn, nhiều cursor hoặc JSON có thể hợp lý hơn.

## 11. RETURNS SETOF: trả nhiều hàng theo kiểu có sẵn

`RETURNS TABLE(...)` phù hợp khi muốn định nghĩa rõ từng cột. Nếu muốn trả nguyên hàng cùng kiểu với bảng hiện có, PostgreSQL có thể dùng `RETURNS SETOF ten_kieu`.

### 11.1. SETOF kiểu hàng của bảng

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_paid_order_rows(
    p_customer_id INTEGER
)
RETURNS SETOF lab340_orders
LANGUAGE SQL
STABLE
AS $fn$
    SELECT o.*
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'PAID';
$fn$;
~~~

Gọi:

~~~sql
SELECT id, customer_id, order_date, status, amount
FROM pg_temp.lab340_paid_order_rows(1)
ORDER BY order_date, id;
~~~

Kết quả ba đơn PAID của An: **101, 103, 110**.

### 11.2. SETOF so với TABLE

| Khía cạnh | `RETURNS SETOF lab340_orders` | `RETURNS TABLE(...)` |
|---|---|---|
| Mẫu sử dụng | Trả hàng theo kiểu bảng có sẵn | Thiết kế cột đầu ra tùy ý |
| Danh sách cột | Gắn với kiểu hàng của bảng | Khai báo trong định nghĩa hàm |
| Thêm/bớt cột bảng nguồn | Có thể kéo theo ảnh hưởng giao diện | Có thể giữ hợp đồng cố định hơn |
| Chọn cột tổng hợp/đổi tên | Kém linh hoạt hơn nếu dùng nguyên kiểu | Linh hoạt |
| Số tập kết quả | Một | Một |

Không nên chọn SETOF kiểu bảng chỉ vì viết ít dòng hơn nếu API công khai phải có cấu trúc ổn định qua thay đổi schema. Việc để lộ `SELECT *` trực tiếp có thể làm contract gắn quá chặt với bảng lưu trữ.

### 11.3. SETOF scalar cũng là một tập hàng

PostgreSQL còn có hàm trả `SETOF INTEGER`: nhiều hàng, mỗi hàng một số. Ví dụ, ý tưởng “trả danh sách ID” khác hẳn `RETURNS INTEGER` chỉ trả một ID.

Câu gọi `SELECT * FROM ham_tra_setof_integer(...)` vẫn đọc một result set gồm một cột, chứ không phải nhiều giá trị scalar tách thành nhiều thông điệp response.

## 12. Trả một bản ghi nhiều cột bằng OUT parameters

Có lúc ứng dụng cần **một bản ghi tổng quan duy nhất**, không phải một bảng tùy ý nhiều dòng. Ví dụ số đơn PAID và tổng doanh thu PAID của một khách.

### 12.1. Function với hai OUT

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_paid_summary(
    IN p_customer_id INTEGER,
    OUT paid_count BIGINT,
    OUT paid_total NUMERIC
)
LANGUAGE SQL
STABLE
AS $fn$
    SELECT
        COUNT(*)::BIGINT,
        COALESCE(SUM(o.amount), 0)
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'PAID';
$fn$;
~~~

Gọi:

~~~sql
SELECT *
FROM pg_temp.lab340_paid_summary(1);
~~~

Kết quả **một hàng, hai cột**:

| paid_count | paid_total |
|---:|---:|
| 3 | 430000 |

### 12.2. Vì sao không phải nhiều result set?

Hai tham số OUT tạo ra hai **trường** trong một bản ghi kết quả, không phải “hai bảng riêng”. Với hàm trên, SQL client trả **một tập kết quả chứa một hàng hai cột**.

Một lần gọi:

~~~sql
SELECT pg_temp.lab340_paid_summary(1);
~~~

có thể hiện một cột composite chứa bộ `(3,430000)` thay vì tách hai cột. Dùng `SELECT * FROM` nếu muốn tên cột có thể truy cập riêng.

### 12.3. RETRUNS TABLE và OUT có liên hệ

`RETURNS TABLE(col1 type1, col2 type2)` trong PostgreSQL có thể hiểu là một giao diện xuất các cột dạng OUT kết hợp trả **tập hàng** (set-returning). Trong khi chỉ có hai OUT mà không khai báo SETOF, hàm `lab340_paid_summary` bên trên trả **một bản ghi**.

**Không nhầm:** nhiều cột OUT **không đồng nghĩa** nhiều dòng; nhiều dòng `RETURNS TABLE` **không đồng nghĩa** nhiều result set.

### 12.4. INOUT

Tham số `INOUT` vừa cung cấp một giá trị đầu vào, vừa nhận giá trị được cập nhật. Trong function/procedure, cách khai báo và lời gọi cụ thể khác nhau theo DBMS. Ở PostgreSQL, procedure với INOUT có thể trả một hàng các giá trị tham số đầu ra sau `CALL`, sẽ minh họa ngay phần sau.

## 13. Procedure PostgreSQL: CALL và tham số INOUT

Một procedure PostgreSQL không được gọi như một expression trong SELECT. Nó được gọi bằng `CALL`.

### 13.1. Tạo procedure trả tổng qua INOUT

~~~sql
CREATE OR REPLACE PROCEDURE pg_temp.lab340_paid_total_proc(
    IN p_customer_id INTEGER,
    INOUT p_total NUMERIC
)
LANGUAGE plpgsql
AS $proc$
BEGIN
    SELECT COALESCE(SUM(o.amount), 0)
    INTO p_total
    FROM lab340_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'PAID';
END;
$proc$;
~~~

Gọi:

~~~sql
CALL pg_temp.lab340_paid_total_proc(1, NULL);
~~~

Kết quả là một hàng có cột `p_total` tương ứng **430000** trong PostgreSQL hỗ trợ ngữ nghĩa CALL/INOUT này. Tham số `NULL` ở vị trí thứ hai đóng vai trò giá trị đầu vào ban đầu của INOUT; procedure gán lại trước khi trả.

### 13.2. Tại sao không SELECT procedure?

Không gọi:

~~~sql
-- Không phải cách gọi một PROCEDURE PostgreSQL:
SELECT pg_temp.lab340_paid_total_proc(1, NULL);
~~~

`SELECT` trong PostgreSQL gọi **function**, còn procedure gọi bằng `CALL`. Dùng đúng loại đối tượng giúp ứng dụng và quyền truy cập minh bạch hơn.

### 13.3. OUT/INOUT của CALL không tạo hai result set

Nếu procedure có nhiều tham số OUT/INOUT, một lời gọi `CALL` có thể trả **một hàng chứa các cột đầu ra**. Điều đó khác với SQL Server procedure chạy hai SELECT và gửi hai bộ metadata/kết quả độc lập.

PostgreSQL procedure cũng có quy tắc đặc thù về điều khiển COMMIT/ROLLBACK: không phải procedure nào, trong mọi cách CALL hoặc trong transaction block, cũng có thể tự kết thúc transaction. Đừng mở transaction control trong procedure chỉ vì cần trả kết quả.

## 14. Trả bảng nhiều dòng từ function có thể JOIN với bảng khác

Một lợi thế của table-valued function là có thể xuất hiện trong `FROM` giống một nguồn dữ liệu quan hệ.

### 14.1. Lọc thêm trên kết quả hàm

~~~sql
SELECT
    order_id,
    order_date,
    amount
FROM pg_temp.lab340_customer_orders(1)
WHERE order_status = 'PAID'
ORDER BY amount DESC;
~~~

Kết quả: các đơn PAID của An, sắp theo tiền giảm.

### 14.2. Dùng LATERAL để truyền tham số từ từng hàng ngoài

Ví dụ muốn xem đơn của khách 1 và khách 4:

~~~sql
SELECT
    c.id AS customer_id,
    c.name,
    t.order_id,
    t.order_date,
    t.order_status
FROM lab340_customers AS c
LEFT JOIN LATERAL
    pg_temp.lab340_customer_orders(c.id) AS t
    ON TRUE
WHERE c.id IN (1, 4)
ORDER BY c.id, t.order_id;
~~~

- Với An, table function trả bốn hàng, nên An hiện bốn dòng.
- Với Dũng, function trả **0 hàng**; `LEFT JOIN LATERAL` vẫn giữ một dòng của Dũng với các cột của `t` bằng NULL.

Nhờ vậy, người học có thể quan sát sự khác biệt giữa **tập rỗng của hàm** và **hàng đệm do LEFT JOIN tạo ra**.

### 14.3. Hiệu năng không tự tốt chỉ vì dùng function

Một table-valued function gọi trên từng hàng khách có thể làm nhiều công việc lặp lại. Với dữ liệu lớn, hãy xem planner có inline/optimize function được không, thống kê và `EXPLAIN`, thay vì mặc định dạng function nhanh hơn JOIN trực tiếp.

Có những function `LANGUAGE SQL` có thể được optimizer inline theo điều kiện thích hợp; PL/pgSQL thường là hộp đen hơn đối với một số phép tối ưu. Đây là yếu tố chọn cách tổ chức câu truy vấn.

## 15. Muốn trả hai bảng khác cấu trúc: hiểu đúng “nhiều result set”

Một báo cáo có thể cần:

1. **Result set 1 — Đơn hàng:** `order_id, order_date, status, amount`.
2. **Result set 2 — Chi tiết:** `order_id, sku, quantity, unit_price`.

Hai tập có metadata khác nhau. Việc chỉ gộp hai bảng bằng UNION thường không phù hợp, vì UNION yêu cầu số cột và kiểu dữ liệu tương thích; hơn nữa, bản ghi header và detail biểu diễn hai thực thể khác nhau.

### 15.1. Hai SELECT độc lập trong một client

~~~sql
SELECT id, order_date, status, amount
FROM lab340_orders
WHERE customer_id = 1
ORDER BY id;

SELECT
    i.order_id,
    i.sku,
    i.quantity,
    i.unit_price
FROM lab340_order_items AS i
JOIN lab340_orders AS o
    ON o.id = i.order_id
WHERE o.customer_id = 1
ORDER BY i.order_id, i.id;
~~~

Nhiều công cụ SQL hiển thị hai lưới kết quả tách biệt khi chạy đoạn script. Đây là **hai statement SELECT**, không phải một function trả trực tiếp hai result set.

### 15.2. Tại sao không đơn giản viết hai SELECT trong function PostgreSQL?

Trong PL/pgSQL, một câu `SELECT` trả hàng mà không có nơi nhận kết quả thường gây lỗi kiểu:

~~~text
query has no destination for result data
~~~

Nếu muốn bỏ qua kết quả, dùng `PERFORM`; nếu muốn lấy một giá trị, dùng `SELECT ... INTO`; nếu muốn trả tập hàng, dùng `RETURN QUERY`. PostgreSQL **không tự truyền mỗi SELECT trần trong thân function/procedure thành một JDBC ResultSet riêng** theo cách một số hệ khác làm.

## 16. PostgreSQL: nhiều refcursor cho nhiều tập kết quả

Một cách xử lý nhiều tập kết quả khác cấu trúc trên PostgreSQL là **mở nhiều cursor**, trả ra *tên/tham chiếu cursor*, rồi người gọi **FETCH** dữ liệu từng cursor.

### 16.1. Hàm mở hai cursor

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_open_customer_report(
    IN p_customer_id INTEGER,
    OUT orders_cur REFCURSOR,
    OUT items_cur REFCURSOR
)
LANGUAGE plpgsql
AS $fn$
BEGIN
    orders_cur := 'lab340_orders_cur';

    OPEN orders_cur FOR
        SELECT
            o.id AS order_id,
            o.order_date,
            o.status,
            o.amount
        FROM lab340_orders AS o
        WHERE o.customer_id = p_customer_id
        ORDER BY o.id;

    items_cur := 'lab340_items_cur';

    OPEN items_cur FOR
        SELECT
            i.order_id,
            i.sku,
            i.quantity,
            i.unit_price
        FROM lab340_order_items AS i
        JOIN lab340_orders AS o
            ON o.id = i.order_id
        WHERE o.customer_id = p_customer_id
        ORDER BY i.order_id, i.id;
END;
$fn$;
~~~

Hàm này có hai tham số OUT kiểu `REFCURSOR`. Nó trả **một hàng chứa hai tên cursor**; dữ liệu thực nằm ở hai cursor đã mở trong phiên.

### 16.2. Gọi trong một transaction

~~~sql
BEGIN;

SELECT *
FROM pg_temp.lab340_open_customer_report(1);

-- Hai tập dữ liệu có cấu trúc khác nhau:
FETCH ALL FROM lab340_orders_cur;

FETCH ALL FROM lab340_items_cur;

CLOSE lab340_orders_cur;
CLOSE lab340_items_cur;

COMMIT;
~~~

Kết quả:

- `SELECT * FROM ...`: một hàng gồm `orders_cur` và `items_cur`, nhận giá trị `lab340_orders_cur` và `lab340_items_cur`.
- `FETCH ALL FROM lab340_orders_cur`: **4 đơn của An**.
- `FETCH ALL FROM lab340_items_cur`: **4 dòng sản phẩm** tương ứng.

### 16.3. Vì sao BEGIN quan trọng?

Cursor PostgreSQL mở theo mẫu trên thường tồn tại trong **transaction hiện tại**. Nếu SQL client ở chế độ autocommit và chạy `SELECT * FROM function(...)` như một statement độc lập, transaction ngầm có thể kết thúc ngay sau đó và cursor sẽ đóng trước khi bạn chạy FETCH.

Vì vậy, phải:

1. Mở transaction.
2. Gọi hàm mở cursor.
3. FETCH từng tập kết quả **trên cùng connection, trước COMMIT/ROLLBACK**.
4. Đóng cursor hoặc kết thúc transaction.

`WITH HOLD` có ngữ nghĩa tồn tại khác nhưng **không phải mặc định** của refcursor này; không nên dựa vào holdable cursor nếu không thiết kế riêng.

### 16.4. Chú ý tên cursor và lần gọi lặp

Ví dụ dùng hai tên cố định `lab340_orders_cur` và `lab340_items_cur` trong cùng session. Nếu gọi hàm lần nữa trong khi các portal cùng tên còn mở, có thể gặp xung đột tên. Hãy **CLOSE trước khi mở lại**, hoặc dùng tên cursor duy nhất do ứng dụng quản lý.

Không ghép trực tiếp tên cursor tùy ý do người dùng gửi vào một câu `FETCH` bằng nối chuỗi không kiểm soát. Tên đối tượng SQL cần được xác thực và quote đúng; tham số dữ liệu thông thường không thể thay thế mọi vị trí tên định danh.

### 16.5. refcursor không đồng nghĩa server gửi hai result set cùng một lúc

Hàm chỉ trả tham chiếu. Người dùng phải FETCH để nhận các hàng; mỗi FETCH tạo **một kết quả SELECT riêng**. Vì vậy, trên wire/API việc đọc khác so với SQL Server/MySQL procedure phát nhiều kết quả trực tiếp từ một `CALL/EXEC`.

Một số driver có thể cung cấp API lấy refcursor thuận tiện hơn; cần kiểm tra phiên bản và cách ánh xạ ResultSet của driver đang dùng.

## 17. PostgreSQL: RETURNS SETOF REFCURSOR

Ngoài việc dùng hai OUT cursor như trên, PostgreSQL có thể định nghĩa hàm trả một **tập các giá trị refcursor**:

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_open_cursor_list(
    p_customer_id INTEGER
)
RETURNS SETOF REFCURSOR
LANGUAGE plpgsql
AS $fn$
DECLARE
    c_orders REFCURSOR := 'lab340_orders_list_cur';
    c_items  REFCURSOR := 'lab340_items_list_cur';
BEGIN
    OPEN c_orders FOR
        SELECT o.id, o.order_date, o.amount
        FROM lab340_orders AS o
        WHERE o.customer_id = p_customer_id
        ORDER BY o.id;

    RETURN NEXT c_orders;

    OPEN c_items FOR
        SELECT i.order_id, i.sku, i.quantity
        FROM lab340_order_items AS i
        JOIN lab340_orders AS o ON o.id = i.order_id
        WHERE o.customer_id = p_customer_id
        ORDER BY i.order_id, i.id;

    RETURN NEXT c_items;

    RETURN;
END;
$fn$;
~~~

Thực hành:

~~~sql
BEGIN;

SELECT *
FROM pg_temp.lab340_open_cursor_list(2);

FETCH ALL FROM lab340_orders_list_cur;
FETCH ALL FROM lab340_items_list_cur;

CLOSE lab340_orders_list_cur;
CLOSE lab340_items_list_cur;

COMMIT;
~~~

Câu SELECT đầu tiên trả **hai hàng kiểu REFCURSOR**, mỗi hàng là một tên cursor, chứ không trả trực tiếp bảng đơn hàng và bảng dòng đơn. FETCH tương ứng tạo hai tập dữ liệu có cấu trúc khác nhau.

### 17.1. Khi nào dùng OUT cursor, khi nào SETOF refcursor?

- **Hai OUT cursor có tên** phù hợp khi giao diện biết chắc có hai tập “orders” và “items”.
- **SETOF refcursor** có thể phù hợp nếu số cursor được trả linh hoạt hoặc người gọi xử lý danh sách cursor.

Cả hai cách tăng yêu cầu quản lý transaction, cursor lifetime và kết nối. Nếu chỉ cần một bảng thông thường, `RETURNS TABLE` đơn giản hơn nhiều.

## 18. Một kết quả JSONB chứa cả summary và detail

Đôi khi ứng dụng web cần một response tự chứa, không muốn duy trì nhiều cursor/result set. PostgreSQL có thể trả một giá trị `JSONB` gói nhiều khối dữ liệu.

### 18.1. Hàm RETURNS JSONB

~~~sql
CREATE OR REPLACE FUNCTION pg_temp.lab340_customer_report_json(
    p_customer_id INTEGER
)
RETURNS JSONB
LANGUAGE SQL
STABLE
AS $fn$
    SELECT jsonb_build_object(
        'customer_id', p_customer_id,
        'paid_total', pg_temp.lab340_paid_total(p_customer_id),
        'orders',
            COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'order_id', o.id,
                            'order_date', o.order_date,
                            'status', o.status,
                            'amount', o.amount
                        )
                        ORDER BY o.id
                    )
                    FROM lab340_orders AS o
                    WHERE o.customer_id = p_customer_id
                ),
                '[]'::JSONB
            )
    );
$fn$;
~~~

Gọi:

~~~sql
SELECT pg_temp.lab340_customer_report_json(1)
    AS report_json;
~~~

Kết quả là **một giá trị JSONB** chứa khóa `customer_id`, `paid_total` và mảng `orders`.

### 18.2. Ưu điểm

- Một giá trị có cấu trúc lồng nhau, thuận tiện cho API JSON.
- Không cần giữ cursor mở nhiều statement.
- Có thể biểu diễn danh sách rỗng bằng `[]`.
- Dễ bổ sung metadata phiên bản response khi thiết kế contract.

### 18.3. Hạn chế

- Không còn là những result set SQL riêng biệt với metadata cột đơn giản.
- Ứng dụng cần parse JSON và kiểm soát schema JSON.
- Payload có thể lớn; nếu trả hàng triệu đơn, cách gói một JSON khổng lồ có chi phí bộ nhớ/truyền tải.
- Việc đặt toàn bộ JSON trong một scalar không tự biến truy vấn thành nhanh hơn.

**Kết luận:** JSONB là *một cấu trúc chứa nhiều nhóm dữ liệu*, không phải “nhiều tập kết quả” theo nghĩa JDBC/SQL protocol.

## 19. Một result set gồm nhiều loại bản ghi có thể dùng UNION ALL không?

Nếu hai nhóm dữ liệu có thể chuẩn hóa thành **cùng một cấu trúc cột**, `UNION ALL` có thể gộp thành một tập duy nhất.

Ví dụ gộp hai chỉ số thành bảng “tên chỉ số + giá trị”:

~~~sql
SELECT 'PAID_COUNT'::TEXT AS metric,
       COUNT(*)::NUMERIC AS value
FROM lab340_orders
WHERE customer_id = 1
  AND status = 'PAID'

UNION ALL

SELECT 'PAID_TOTAL'::TEXT AS metric,
       COALESCE(SUM(amount), 0)::NUMERIC AS value
FROM lab340_orders
WHERE customer_id = 1
  AND status = 'PAID';
~~~

Kết quả hai hàng trong một result set:

| metric | value |
|---|---:|
| PAID_COUNT | 3 |
| PAID_TOTAL | 430000 |

### 19.1. Khi nào không nên UNION?

Không nên ép dữ liệu đơn hàng và dòng sản phẩm thành một bảng đầy cột NULL chỉ để tránh đọc hai tập, nếu ứng dụng cần hai cấu trúc riêng rõ ràng.

`UNION ALL` đòi số cột và kiểu dữ liệu giữa các SELECT tương thích; nó **không** làm database trả hai schema kết quả độc lập. Dùng khi mục tiêu thực sự là **một bảng tổng hợp cùng schema**.

## 20. SQL Server: stored procedure có nhiều SELECT và nhiều result set

SQL Server cho phép stored procedure phát nhiều result set từ những lệnh SELECT khác nhau trong phần thân.

Ví dụ T-SQL, giả sử có bảng `dbo.Orders` và `dbo.OrderItems`:

~~~sql
CREATE OR ALTER PROCEDURE dbo.usp_CustomerReport
    @CustomerId INT
AS
BEGIN
    SET NOCOUNT ON;

    -- Result set 1: danh sách đơn.
    SELECT
        o.Id,
        o.OrderDate,
        o.Amount
    FROM dbo.Orders AS o
    WHERE o.CustomerId = @CustomerId
    ORDER BY o.Id;

    -- Result set 2: danh sách dòng đơn.
    SELECT
        i.OrderId,
        i.Sku,
        i.Quantity,
        i.UnitPrice
    FROM dbo.OrderItems AS i
    JOIN dbo.Orders AS o
        ON o.Id = i.OrderId
    WHERE o.CustomerId = @CustomerId
    ORDER BY i.OrderId, i.Id;
END;
~~~

Gọi:

~~~sql
EXEC dbo.usp_CustomerReport @CustomerId = 1;
~~~

Trong driver/client hỗ trợ, lời gọi procedure có thể phát ra **hai result set độc lập**:

1. Tập gồm `Id, OrderDate, Amount`.
2. Tập gồm `OrderId, Sku, Quantity, UnitPrice`.

### 20.1. SET NOCOUNT ON

`SET NOCOUNT ON` thường giúp giảm các thông điệp đếm số hàng ảnh hưởng (row count messages) trong procedure SQL Server. Các thông điệp/update count có thể ảnh hưởng cách client duyệt những kết quả nhận được; tuy nhiên, vẫn phải viết JDBC/client có khả năng xử lý cả result set và update count, không chỉ giả định kết quả đầu là bảng đầu tiên.

### 20.2. Function SQL Server và procedure khác nhau

SQL Server có scalar user-defined functions và table-valued functions, nhưng stored procedure có thể trả **nhiều result set** bằng nhiều SELECT. Không đồng nhất tính năng procedure với interface của table-valued function; chúng không có cùng quy tắc gọi trong FROM, side effects hay tối ưu.

## 21. MySQL/MariaDB: CALL procedure trả nhiều tập

MySQL và MariaDB có thể dùng nhiều SELECT trong stored procedure để xuất các tập kết quả.

Ví dụ cú pháp MySQL client, giả sử bảng `orders`, `order_items` tồn tại:

~~~sql
DELIMITER //

CREATE PROCEDURE sp_customer_report(
    IN p_customer_id INT
)
BEGIN
    SELECT id, order_date, amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY id;

    SELECT
        i.order_id,
        i.sku,
        i.quantity,
        i.unit_price
    FROM order_items AS i
    JOIN orders AS o
        ON o.id = i.order_id
    WHERE o.customer_id = p_customer_id
    ORDER BY i.order_id, i.id;
END//

DELIMITER ;

CALL sp_customer_report(1);
~~~

`DELIMITER` là **lệnh của một số SQL client** (để nhập được thân procedure có dấu chấm phẩy), không phải câu lệnh SQL chạy như nhau qua mọi driver. Trong ứng dụng, DDL được gửi qua JDBC theo cơ chế phù hợp của driver, không gắn cứng `DELIMITER` vào SQL statement.

### 21.1. MySQL stored function không giống stored procedure

Stored function MySQL thường trả **một giá trị** và dùng trong biểu thức SQL. Stored procedure được gọi qua `CALL`, có thể trả **các result set** và có tham số OUT/INOUT.

MariaDB tương tự ở cấp ý tưởng, nhưng cần kiểm tra khả năng cú pháp/driver của từng phiên bản. Đừng dùng cú pháp PostgreSQL `RETURNS TABLE` làm giả định mặc nhiên cho MySQL.

### 21.2. Client phải đọc hết các kết quả

Khi procedure xuất nhiều result set, một số driver yêu cầu client tiêu thụ hoặc đóng đúng các kết quả trước khi gửi lệnh tiếp theo trên cùng connection. Với JDBC, các API `execute` và `getMoreResults` là cơ chế chung để xử lý tình huống này.

## 22. Oracle: OUT SYS_REFCURSOR và nhiều cursor

Oracle thường dùng `SYS_REFCURSOR` để trả tập dữ liệu từ thủ tục PL/SQL, đặc biệt khi cần nhiều tập khác cấu trúc.

Ví dụ minh họa trên schema Oracle có `ORDERS` và `ORDER_ITEMS`:

~~~sql
CREATE OR REPLACE PROCEDURE customer_report (
    p_customer_id IN NUMBER,
    p_orders OUT SYS_REFCURSOR,
    p_items  OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN p_orders FOR
        SELECT id, order_date, amount
        FROM orders
        WHERE customer_id = p_customer_id
        ORDER BY id;

    OPEN p_items FOR
        SELECT i.order_id, i.sku, i.quantity, i.unit_price
        FROM order_items i
        JOIN orders o ON o.id = i.order_id
        WHERE o.customer_id = p_customer_id
        ORDER BY i.order_id, i.id;
END;
/
~~~

Ở phía client, đăng ký các tham số đầu ra là refcursor và đọc các ResultSet/cursor tương ứng theo driver.

### 22.1. PL/SQL function scalar

Oracle function có cú pháp kiểu:

~~~sql
CREATE OR REPLACE FUNCTION double_amount(
    p_amount IN NUMBER
)
RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 2;
END;
/
~~~

Ở đây `RETURN NUMBER` là khai báo kiểu trả; `RETURN p_amount * 2` trả scalar. Đây là cú pháp Oracle, **không phải PostgreSQL `RETURNS NUMERIC LANGUAGE plpgsql`**.

### 22.2. Các lựa chọn khác

Oracle còn có các cơ chế như pipelined table function và implicit statement results trong các phiên bản phù hợp. Tùy bài toán, nhiều OUT SYS_REFCURSOR có thể là lựa chọn rõ ràng; tuy nhiên, ứng dụng phải giữ/đóng cursor và giao dịch đúng theo driver.

## 23. SQLite: không có CREATE PROCEDURE như PostgreSQL/MySQL

SQLite không cung cấp cú pháp chuẩn để tạo stored procedure và stored function SQL trong database theo các mẫu PostgreSQL/SQL Server/MySQL ở trên.

Ứng dụng có thể:

- Thực hiện một hay nhiều câu SELECT riêng.
- Đăng ký **user-defined functions** thông qua API của thư viện kết nối nếu cần scalar/aggregate do ứng dụng triển khai.
- Dùng view/CTE hoặc JSON functions phù hợp cho truy vấn có cấu trúc.

Do đó, không sao chép `CREATE PROCEDURE ... CALL` vào SQLite. Một API trả nhiều tập dữ liệu trong ứng dụng SQLite thường được xây bằng nhiều truy vấn/ResultSet ở tầng ứng dụng, thay vì một stored procedure server-side.

## 24. JDBC: đọc scalar function

Với PostgreSQL JDBC, gọi hàm scalar bằng SELECT và đọc một ô từ ResultSet.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static BigDecimal paidTotal(
        Connection conn,
        int customerId
) throws SQLException {

    String sql =
        "SELECT pg_temp.lab340_paid_total(?) AS total";

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setInt(1, customerId);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "Scalar function không trả một hàng"
                );
            }

            BigDecimal result = rs.getBigDecimal("total");

            if (rs.next()) {
                throw new SQLException(
                    "Scalar function trả hơn một hàng"
                );
            }

            return result;
        }
    }
}
~~~

### 24.1. Vì sao dùng BigDecimal?

`NUMERIC` của PostgreSQL phù hợp với Java `BigDecimal` khi xử lý tiền theo số thập phân. `double` có thể gây sai số nhị phân; đừng dùng `getDouble` rồi xem kết quả là giá trị tiền tuyệt đối chính xác.

`getBigDecimal` có thể trả `null` nếu cột SQL là NULL. Hàm bài này dùng COALESCE nên tổng hiện tại không NULL, nhưng người viết repository cần biết hợp đồng hàm để xử lý nếu định nghĩa thay đổi.

### 24.2. Scalar không có nghĩa truy vấn JDBC trả thẳng BigDecimal

JDBC `executeQuery()` trả **ResultSet**, ngay cả khi câu SELECT gồm một ô. Ứng dụng phải gọi `rs.next()` rồi đọc giá trị. “Hàm trả scalar” là hợp đồng SQL của hàm; giao diện JDBC để đọc `SELECT` vẫn là ResultSet.

## 25. JDBC: đọc table-valued function

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void printCustomerOrders(
        Connection conn,
        int customerId
) throws SQLException {

    String sql = """
        SELECT order_id, order_date, order_status, amount
        FROM pg_temp.lab340_customer_orders(?)
        ORDER BY order_date DESC, order_id DESC
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setInt(1, customerId);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                int id = rs.getInt("order_id");
                Date date = rs.getDate("order_date");
                String status = rs.getString("order_status");
                BigDecimal amount = rs.getBigDecimal("amount");

                System.out.printf(
                    "%d | %s | %s | %s%n",
                    id, date, status, amount
                );
            }
        }
    }
}
~~~

Với khách 4 không có đơn, `rs.next()` trả false ngay lần đầu. Không nên tự thêm hàng “id = 0” để biểu diễn tập rỗng; trả **danh sách rỗng** ở tầng ứng dụng là lựa chọn thường phù hợp.

### 25.1. PreparedStatement dùng cùng connection phiên tạm

Các hàm và bảng `pg_temp/lab340` thuộc cùng session thực hành; Connection khác sẽ không tự nhìn thấy chúng. Trong ứng dụng thật, function/procedure thường được triển khai vào schema bền vững và quản lý bằng migration, còn kết nối từ pool dùng chung các đối tượng đó.

## 26. JDBC: đọc nhiều result set từ stored procedure

Với SQL Server/MySQL và driver JDBC hỗ trợ một procedure trả nhiều result set, chỉ gọi `executeQuery()` rồi đọc một ResultSet có thể làm mất các kết quả sau.

API JDBC có:

- `CallableStatement.execute()`: bắt đầu thực thi, trả boolean cho biết **kết quả đầu tiên có là ResultSet hay không**.
- `getResultSet()`: lấy tập kết quả hiện tại nếu có.
- `getUpdateCount()`: lấy update count hiện tại, trả -1 khi không còn update count.
- `getMoreResults()`: chuyển tới kết quả tiếp theo.

### 26.1. Mẫu duyệt toàn bộ kết quả

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

public static void readAllProcedureResults(
        Connection conn,
        int customerId
) throws SQLException {

    // Mẫu CALL kiểu JDBC; cách driver xử lý có thể khác.
    String callSql = "{ call sp_customer_report(?) }";

    try (CallableStatement cs = conn.prepareCall(callSql)) {
        cs.setInt(1, customerId);

        boolean isResultSet = cs.execute();
        int resultSetNo = 0;

        while (true) {
            if (isResultSet) {
                resultSetNo++;

                try (ResultSet rs = cs.getResultSet()) {
                    ResultSetMetaData md = rs.getMetaData();
                    int columnCount = md.getColumnCount();

                    System.out.println(
                        "Result set #" + resultSetNo
                    );

                    while (rs.next()) {
                        for (int c = 1; c <= columnCount; c++) {
                            System.out.print(
                                md.getColumnLabel(c) + "="
                                + rs.getObject(c) + " "
                            );
                        }
                        System.out.println();
                    }
                }

            } else {
                int updateCount = cs.getUpdateCount();

                if (updateCount == -1) {
                    break;
                }

                System.out.println(
                    "Update count = " + updateCount
                );
            }

            isResultSet = cs.getMoreResults();
        }
    }
}
~~~

### 26.2. Vì sao phải xử lý update count?

Một procedure có thể thực hiện DML trước, giữa hoặc sau các SELECT. Driver có thể cung cấp một **update count** thay vì ResultSet ở một vị trí trong chuỗi kết quả. Nếu code viết:

~~~java
if (!cs.execute()) {
    return;
}
~~~

thì có thể bỏ sót tất cả result set phía sau khi kết quả đầu là update count. Vòng lặp `getMoreResults/getUpdateCount` giúp duyệt hợp lý hơn.

### 26.3. Không giả định thứ tự kết quả tùy ý được phép đổi

Nếu một procedure có hợp đồng “Result set 1 = orders; Result set 2 = items”, ứng dụng dựa vào **thứ tự** đó. Khi thêm một SELECT debug vào procedure, ứng dụng có thể đọc nhầm result set.

Hãy coi **số lượng, thứ tự, tên cột và kiểu cột** của các result set là một phần API contract. Thay đổi procedure cần tương thích với client.

### 26.4. Không áp dụng vòng lặp này trực tiếp cho PostgreSQL refcursor

Hàm refcursor ở phần 16 trả **một hàng gồm hai tên cursor**, sau đó bạn phải `FETCH` từng cursor. Nó không tự trả hai result set liên tiếp qua cùng lời gọi `SELECT function(...)` theo mẫu SQL Server/MySQL ở đây.

JDBC cho PostgreSQL có những cách sử dụng refcursor qua CallableStatement/ResultSet tùy phiên bản driver, nhưng phải tuân theo transaction, cursor lifetime và API được driver hỗ trợ.

## 27. PostgreSQL JDBC với refcursor: tư duy truy cập đúng

Nếu ứng dụng cần dùng mẫu ở phần 16, luồng tối thiểu:

~~~text
Connection A, autoCommit = false
    │
    ├── SELECT * FROM pg_temp.lab340_open_customer_report(?)
    │        → tên orders_cur, items_cur
    │
    ├── FETCH ALL FROM orders_cur
    │        → ResultSet đơn hàng
    │
    ├── FETCH ALL FROM items_cur
    │        → ResultSet dòng đơn
    │
    ├── CLOSE các cursor
    │
    └── commit / rollback theo nghiệp vụ
~~~

**Điều quan trọng:**

1. Cùng Connection cho mở cursor và FETCH.
2. Transaction phải còn mở cho đến khi FETCH xong.
3. Không coi tên cursor là dữ liệu người dùng có thể nối tùy ý vào SQL.
4. Đảm bảo đóng ResultSet, Statement và cursor.
5. Tránh giữ cursor/transaction trong thời gian dài khi UI chờ thao tác.
6. Nếu dữ liệu rất lớn, cân nhắc đọc theo batch và cơ chế streaming/driver thay vì `FETCH ALL` một lần.

Với một báo cáo chỉ vài chục hàng, function `RETURNS TABLE` hoặc hai truy vấn SQL rõ ràng thường ít phức tạp hơn việc quản lý nhiều cursor.

## 28. Chọn hình dạng kết quả theo yêu cầu API

Dưới đây là một số tình huống và hướng lựa chọn:

| Yêu cầu | Đầu ra phù hợp | Vì sao |
|---|---|---|
| Tính tổng doanh thu PAID của một khách | Scalar `NUMERIC` | Một đại lượng xác định |
| Trả số đơn PAID và tổng tiền trong một hàng | Composite/OUT | Một bản ghi thống kê nhiều cột |
| Danh sách đơn của khách | `RETURNS TABLE` | Cùng cấu trúc, 0..N hàng; dùng JOIN/WHERE được |
| Trả nguyên bản ghi đơn theo kiểu bảng | `RETURNS SETOF ten_bang` | Ít khai báo, nhưng ràng buộc schema mạnh |
| Bảng đơn và bảng chi tiết độc lập | Nhiều result set/cursor hoặc hai SELECT | Mỗi tập có cấu trúc và ý nghĩa riêng |
| API trả report JSON lồng nhau | Scalar `JSONB` | Dễ đóng gói response, cần parse JSON |
| Nhiều nhóm số liệu cùng hai cột tên/giá trị | Một tập `UNION ALL` | Dữ liệu cùng schema nên gộp được |
| Cần dùng như bảng trong một truy vấn lớn | Table-valued function trong FROM/LATERAL | Có thể lọc, JOIN, tổng hợp tiếp |
| Procedure SQL Server/MySQL cần trả orders + items | Hai SELECT trong procedure | Driver có thể duyệt nhiều ResultSet |
| Procedure Oracle cần trả orders + items | Hai OUT SYS_REFCURSOR | Client đọc từng cursor phù hợp |

### 28.1. Thiết kế hợp đồng trước khi code

Một hợp đồng tốt nên ghi rõ:

- Kiểu đầu vào, tham số bắt buộc/mặc định.
- Đầu ra là scalar, một hàng, 0..N hàng hay nhiều result set.
- Cột nào NOT NULL, cột nào có thể NULL.
- Thứ tự kết quả có cam kết không? Nếu có, bằng ORDER BY nào?
- Có thể trả 0 hàng hoặc thiếu một result set không?
- Khi không tìm thấy dữ liệu: trả NULL, 0, tập rỗng hay ném lỗi?
- Dữ liệu có được đổi không, và cần transaction không?
- Các quyền đọc bảng và gọi function/procedure.
- Versioning khi thay đổi số cột, tên cột hoặc thứ tự result set.

Một result set trả đúng dữ liệu nhưng khác contract vẫn có thể làm ứng dụng lỗi.

## 29. Các lỗi hay gặp

| Lỗi | Hậu quả | Cách đúng hơn |
|---|---|---|
| Dùng `RETURNS NUMERIC` nhưng thân hàm trả nhiều cột | Không khớp kiểu kết quả | Chọn scalar hoặc composite/TABLE |
| Nghĩ `RETURNS TABLE` tạo bảng vật lý | Hiểu sai dữ liệu lưu trữ | Đây là tập hàng kết quả của function |
| Nghĩ bảng 100 dòng là 100 result set | Nhầm bản chất result set | Một bảng nhiều dòng vẫn là một result set |
| Dùng `RETURN expr` như `RETURN QUERY` | Nhầm hàm scalar với set-returning | Chọn theo RETURNS |
| Gọi PL/pgSQL `SELECT` không INTO/PERFORM/RETURN QUERY | Có thể lỗi “no destination” | Chỉ rõ nơi nhận |
| Hàm `RETURNS TABLE` trả sai kiểu/số cột | Lỗi structure mismatch | Kiểm tra từng kiểu và thứ tự |
| Dùng `SELECT f()` rồi kỳ vọng tách cột | Nhận một cột composite | `SELECT * FROM f()` |
| Không xử lý khách không có đơn | Null/tập rỗng bị hiểu nhầm | Định nghĩa contract NULL/0/empty |
| Đánh dấu hàm đọc bảng là IMMUTABLE | Có thể tạo giả định sai cho planner | Dùng volatility đúng với ngữ nghĩa |
| Tạo function vĩnh viễn tham chiếu TEMP TABLE rồi quên dọn | Hàm có thể lỗi ở session khác | Dùng schema thử nghiệm/session temp và dọn dẹp |
| Nghĩ procedure PostgreSQL phát nhiều result set từ SELECT trần | Không đúng cơ chế | Dùng refcursor/FETCH, table function hoặc JSON |
| FETCH cursor sau autocommit | Cursor đã đóng | BEGIN và FETCH trước COMMIT |
| Dùng tên cursor cố định nhiều lần không đóng | Xung đột portal | CLOSE hoặc dùng tên duy nhất |
| Ghép tên cursor từ request vào FETCH | Rủi ro injection/sai identifier | Kiểm soát/quote tên đúng |
| Coi JSONB là nhiều result set | API đọc sai hình dạng | JSONB là một scalar chứa cấu trúc |
| Dùng UNION để trộn header/detail khác schema | Sai số cột/ý nghĩa | Nhiều tập hoặc JSON/quan hệ thiết kế rõ |
| JDBC chỉ đọc ResultSet đầu | Bỏ sót tập kết quả sau | `execute/getMoreResults/getUpdateCount` |
| JDBC không tiêu thụ update count | Có thể dừng vòng kết quả sớm | Xử lý cả kết quả đếm hàng |
| Đổi thứ tự SELECT trong procedure | Client đọc nhầm tập | Giữ API contract/version |
| Giữ cursor/transaction quá lâu | Tốn tài nguyên/khóa/phiên | Trả kết quả có giới hạn, quản lý vòng đời |
| Gọi function từng khách mà không đo | Có thể lặp query nhiều lần | So với JOIN/GROUP BY và EXPLAIN |
| Tin mọi DBMS hỗ trợ `CREATE PROCEDURE` giống nhau | Lỗi cú pháp/khả năng | Đọc tài liệu đúng DBMS và phiên bản |

## 30. Bài tập thực hành có lời giải

Các bài dưới dùng bộ dữ liệu `lab340_customers`, `lab340_orders` và `lab340_order_items` ở phần 4; tất cả ví dụ PostgreSQL yêu cầu cùng session, các hàm tạo trong `pg_temp`. Những ví dụ SQL Server/MySQL/Oracle là cú pháp minh họa độc lập, **không chạy** trên bảng PostgreSQL temp của bài.

### Bài 1. Scalar tổng doanh thu PAID của khách An

**Yêu cầu:** gọi hàm tổng tiền đã tạo.

~~~sql
SELECT pg_temp.lab340_paid_total(1) AS paid_total;
~~~

**Đáp án:** một giá trị **430000**.

### Bài 2. Scalar cho khách không có đơn

~~~sql
SELECT pg_temp.lab340_paid_total(4) AS paid_total;
~~~

**Đáp án:** **0** vì hàm dùng `COALESCE(SUM(...),0)`. Nếu bỏ COALESCE, SUM trên tập rỗng trả NULL.

### Bài 3. Một bản ghi hai cột

~~~sql
SELECT *
FROM pg_temp.lab340_paid_summary(2);
~~~

**Đáp án:** **một hàng**, `paid_count = 2` và `paid_total = 350000`. Đây không phải hai result set.

### Bài 4. RETURNS TABLE của khách Chi

~~~sql
SELECT *
FROM pg_temp.lab340_customer_orders(3)
ORDER BY order_id;
~~~

**Đáp án:** 3 hàng có ID **107, 108, 109**; trạng thái lần lượt NEW, PAID, PAID. Cấu trúc gồm 4 cột.

### Bài 5. Lọc theo ngày bằng tham số thứ hai

~~~sql
SELECT *
FROM pg_temp.lab340_customer_orders(
    1, DATE '2026-11-01'
);
~~~

**Đáp án:** một hàng đơn **110**, vì ba đơn khác của An được đặt trong tháng 10.

### Bài 6. Phân biệt không có hàng và một hàng NULL

**Đề:** `SELECT * FROM pg_temp.lab340_customer_orders(4)` trả gì?

**Đáp án:** **0 hàng**, không phải một hàng có `order_id = NULL`. Nếu dùng `LEFT JOIN LATERAL` từ khách Dũng tới hàm ấy, JOIN có thể tạo một hàng Dũng và các cột đơn NULL.

### Bài 7. PL/pgSQL RETURN QUERY

~~~sql
SELECT *
FROM pg_temp.lab340_paid_orders_min(200000)
ORDER BY order_id;
~~~

**Đáp án:** ID **106** và **109**. Đơn 102 không được chọn vì status NEW.

### Bài 8. RETURN NEXT trả bao nhiêu result set?

~~~sql
SELECT *
FROM pg_temp.lab340_customer_metrics(1);
~~~

**Đáp án:** **một result set có hai hàng**: PAID_COUNT = 3 và PAID_TOTAL = 430000. Hai RETURN NEXT không đồng nghĩa hai result set.

### Bài 9. RETURN và RETURN QUERY khác nhau thế nào?

**Đề:** hàm `RETURNS NUMERIC` dùng `RETURN v_total`; hàm `RETURNS TABLE` dùng `RETURN QUERY SELECT ...`. Hai lệnh nào kết thúc hàm ngay?

**Đáp án:** `RETURN v_total` kết thúc hàm scalar và trả giá trị. `RETURN QUERY` thêm hàng vào tập kết quả nhưng không tự kết thúc; có thể thêm RETURN QUERY/NEXT sau đó và kết thúc bằng `RETURN;`.

### Bài 10. SETOF nguyên hàng đơn

~~~sql
SELECT id, status, amount
FROM pg_temp.lab340_paid_order_rows(1)
ORDER BY id;
~~~

**Đáp án:** 3 hàng đơn PAID của An: ID 101 (100000), 103 (150000), 110 (180000).

### Bài 11. Gọi procedure đúng cú pháp

~~~sql
CALL pg_temp.lab340_paid_total_proc(1, NULL);
~~~

**Đáp án:** một hàng trả tham số INOUT `p_total = 430000`. Không gọi procedure này bằng `SELECT pg_temp.lab340_paid_total_proc(...)`.

### Bài 12. Hai tập kết quả trên PostgreSQL

**Đề:** muốn nhận danh sách đơn và danh sách dòng sản phẩm của khách 2. Hãy dùng refcursor.

~~~sql
BEGIN;

SELECT *
FROM pg_temp.lab340_open_customer_report(2);

FETCH ALL FROM lab340_orders_cur;
FETCH ALL FROM lab340_items_cur;

CLOSE lab340_orders_cur;
CLOSE lab340_items_cur;

COMMIT;
~~~

**Đáp án:** FETCH thứ nhất trả 3 đơn **104, 105, 106**; FETCH thứ hai trả 3 dòng tương ứng. SELECT function đầu chỉ trả **tên hai cursor**.

### Bài 13. Vì sao cần transaction cho cursor?

**Đề:** gọi hàm mở refcursor trong một statement autocommit, sau đó chạy FETCH ở statement khác.

**Đáp án:** cursor thường đã đóng khi transaction ngầm đầu kết thúc. Phải đặt mở và FETCH trong cùng transaction, trên cùng connection, trước COMMIT.

### Bài 14. JSONB có phải nhiều result set không?

~~~sql
SELECT pg_temp.lab340_customer_report_json(1);
~~~

**Đáp án:** không. Kết quả SQL là **một giá trị JSONB**, bên trong có paid_total và mảng orders; ứng dụng phải đọc/parse JSON nếu cần các trường.

### Bài 15. SQL Server procedure có hai SELECT

**Đề:** một procedure SQL Server có hai SELECT độc lập, một SELECT đơn và một SELECT chi tiết, được gọi bằng EXEC. Có thể có mấy result set?

**Đáp án:** có thể có **hai result set độc lập**, tùy đường đi logic và driver. Java/JDBC cần xử lý `getMoreResults()` và có thể cả update count; không chỉ đọc tập đầu.

### Bài 16. Update count đứng trước result set

**Đề:** JDBC `CallableStatement.execute()` trả false vì kết quả đầu là update count. Có nên kết thúc?

**Đáp án:** không. Kiểm tra `getUpdateCount()`, sau đó gọi `getMoreResults()` để đi tiếp. Chỉ kết thúc khi không còn result set và `getUpdateCount() = -1` theo vòng lặp API.

### Bài 17. Nêu sai sót kiểu dữ liệu RETURN QUERY

**Đề:** hàm `RETURNS TABLE(order_id INTEGER, amount NUMERIC)` nhưng SELECT trả `order_id, status TEXT`.

**Đáp án:** cột thứ hai không tương thích với NUMERIC; hàm không đáp ứng contract. Phải SELECT đúng biểu thức amount hoặc thiết kế lại RETURNS TABLE tương ứng, không ép kiểu tùy tiện làm sai nghĩa.

### Bài 18. Chọn function hay procedure

**Đề:** dùng scalar trong SELECT của danh sách khách, hay thực hiện một thủ tục nhiều bước ghi và thông báo kết quả?

**Đáp án:** tính scalar đọc có thể dùng function với `RETURNS NUMERIC`. Quy trình thao tác nhiều bước có side effects có thể phù hợp procedure/service transaction, tùy DBMS. Không dùng chức năng trả dữ liệu làm lý do bỏ qua transaction/permission.

### Bài 19. Tại sao SUM và COUNT trả khác nhau trên tập rỗng?

~~~sql
SELECT
    COUNT(*) AS cnt,
    SUM(amount) AS total
FROM lab340_orders
WHERE customer_id = 4;
~~~

**Đáp án:** `cnt = 0`, `total = NULL`. SUM không tự bằng 0. Dùng COALESCE nếu contract muốn không có đơn thì tổng bằng 0.

### Bài 20. Thiết kế API báo cáo

**Đề:** API cần tổng tiền PAID, danh sách đơn, danh sách dòng sản phẩm của khách An. Nêu hai phương án và đánh đổi.

**Đáp án gợi ý:**

- **Phương án A:** scalar tổng, một table function cho đơn và một query cho dòng; hoặc một function trả hai refcursor. Kết quả có kiểu SQL rõ, nhưng cần nhiều lần đọc/result set và quản lý cursor/transaction khi dùng refcursor.
- **Phương án B:** một JSONB chứa tổng và hai mảng. Dễ đóng gói API JSON, nhưng phải parse, giới hạn dung lượng và quản lý schema payload.
- Trong cả hai, cần hợp đồng đầu ra ổn định, quyền đọc, thứ tự rõ ràng và kiểm tra hiệu năng thực tế.

## 31. Checklist khi thiết kế kết quả của hàm/thủ tục

1. **Đầu ra là một giá trị hay một bảng?** Đừng dựa vào cách SQL client hiển thị để đoán.
2. **Bảng chỉ có một hàng hay có thể 0..N hàng?**
3. **Nhiều cột OUT có nghĩa một record hay nhiều result set?**
4. **Hai tập dữ liệu có cấu trúc khác nhau không?** Nếu có, cân nhắc nhiều result set/cursor/JSON.
5. **Hàm dùng đúng RETURNS và RETURN/RETURN QUERY/RETURN NEXT chưa?**
6. **Cột đầu ra có đúng số lượng, vị trí, tên và kiểu không?**
7. **Không tìm thấy dữ liệu được biểu diễn bằng NULL, 0, empty set hay exception?**
8. **Result set có yêu cầu ORDER BY xác định không?**
9. **Có nên trả cả bảng gốc qua SETOF, hay khai báo contract riêng bằng RETURNS TABLE?**
10. **Function đọc dữ liệu được đánh dấu volatility đúng chưa?**
11. **Nếu procedure trả nhiều result set, số lượng và thứ tự có ổn định không?**
12. **Nếu dùng refcursor, transaction có còn mở khi FETCH không?**
13. **Cursor có được đóng và tên có tránh xung đột không?**
14. **Driver có hỗ trợ cơ chế OUT/REF_CURSOR theo phiên bản không?**
15. **JDBC đã đọc cả ResultSet và update count chưa?**
16. **Có chuẩn hóa schema/metadata ở tầng API để dễ versioning không?**
17. **Kích thước payload có giới hạn hợp lý không?**
18. **Có truy vấn lặp trong function, gây N+1 không?**
19. **Các function/procedure có quyền chạy/đọc bảng phù hợp không?**
20. **Đã phân biệt các cú pháp PostgreSQL, SQL Server, MySQL, Oracle và SQLite chưa?**

## 32. Tổng kết

Một hàm hoặc thủ tục SQL có thể cung cấp dữ liệu theo những hình dạng rất khác nhau; chọn đúng hình dạng là một phần quan trọng của thiết kế giao diện giữa database và ứng dụng.

- **Một giá trị đơn** thường được trả bằng function `RETURNS NUMERIC/TEXT/INTEGER/...`, bên trong dùng `RETURN biểu_thức` hoặc một câu SQL hợp lệ.
- **Một bản ghi nhiều cột** có thể được biểu diễn bằng nhiều tham số `OUT`, nhưng vẫn là **một hàng**, không phải nhiều result set.
- **Một bảng 0..N hàng** được biểu diễn bằng `RETURNS TABLE(...)` hoặc `RETURNS SETOF ...`; trong PL/pgSQL dùng `RETURN QUERY` hoặc `RETURN NEXT` để xây tập kết quả.
- **Nhiều tập kết quả độc lập** không giống một bảng có nhiều dòng. PostgreSQL có thể dùng **nhiều refcursor rồi FETCH trong cùng transaction**; SQL Server/MySQL có thể xuất các result set trực tiếp từ nhiều SELECT trong procedure; Oracle có thể dùng nhiều OUT `SYS_REFCURSOR`.
- **JSONB** có thể gói nhiều nhóm dữ liệu vào một giá trị, nhưng nó vẫn là **một scalar SQL chứa cấu trúc JSON**, không phải các ResultSet riêng.
- Trong **JDBC**, scalar và table function gọi bằng SELECT thường được đọc từ ResultSet; stored procedure trả nhiều kết quả cần vòng lặp `execute() / getResultSet() / getMoreResults() / getUpdateCount()`.
- Kiểu dữ liệu, tập rỗng, NULL, thứ tự hàng, vòng đời cursor, quyền đọc và thay đổi contract phải được thiết kế rõ ràng.

Hãy bắt đầu từ câu hỏi **ứng dụng cần một giá trị, một bản ghi, một bảng nhiều hàng hay nhiều bảng độc lập**. Sau đó chọn `RETURNS`, `RETURN`, `RETURNS TABLE/SETOF`, `OUT/INOUT`, `refcursor` hoặc cơ chế đa result set theo **đúng hệ quản trị và driver**, thay vì cố dùng một cú pháp cho mọi kiểu kết quả.
