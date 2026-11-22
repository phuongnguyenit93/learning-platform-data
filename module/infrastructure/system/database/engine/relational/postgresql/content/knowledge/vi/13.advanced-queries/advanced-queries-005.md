# LATERAL và truy vấn phụ phụ thuộc từng hàng trong PostgreSQL

Một hệ thống bán hàng thường cần những câu hỏi như: “Với **mỗi khách hàng**, lấy **hai đơn hàng mới nhất**”, “Với **mỗi đơn hàng**, tách danh sách nhãn JSON thành từng dòng”, hoặc “Với **mỗi cửa hàng**, tìm ba sản phẩm bán chạy nhất trong cửa hàng đó”. Điểm chung là **một truy vấn hoặc hàm ở phía sau cần sử dụng giá trị của hàng đang xét ở phía trước**.

Trong PostgreSQL, từ khóa **`LATERAL`** giúp viết loại truy vấn này một cách tự nhiên. Nó cho phép một bảng con (*subquery*) hoặc một lời gọi hàm trong mệnh đề `FROM` tham chiếu các cột từ những thành phần `FROM` xuất hiện trước nó trong cùng phạm vi.

Ví dụ điển hình:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE;
~~~

Không giống một subquery độc lập trong `FROM`, truy vấn mang `LATERAL` ở đây có thể dùng `c.customer_id` để chọn **những đơn hàng riêng cho từng khách hàng**. `LEFT JOIN` giữ cả khách hàng chưa có đơn; nếu dùng `CROSS JOIN LATERAL` hoặc `JOIN LATERAL ... ON TRUE`, khách hàng không có hàng khớp sẽ không xuất hiện.

Bài học trình bày mô hình tư duy, cú pháp, thí nghiệm đầy đủ, sự khác nhau giữa các kiểu JOIN, so sánh với correlated subquery/`EXISTS`/window function/`DISTINCT ON`, xử lý JSONB và set-returning function, cùng các lưu ý tối ưu hiệu năng bằng `EXPLAIN` và index.

## 1. Truy vấn phụ độc lập và truy vấn phụ tương quan

Trước khi học `LATERAL`, cần phân biệt hai loại subquery.

### 1.1. Subquery độc lập

Ví dụ lấy tổng số đơn hàng toàn hệ thống:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    totals.all_orders
FROM customers AS c
CROSS JOIN (
    SELECT COUNT(*) AS all_orders
    FROM orders
) AS totals;
~~~

Subquery `totals` **không dùng** cột nào từ `c`. Về mặt logic, nó tính một giá trị tổng toàn hệ thống và có thể dùng chung cho mọi hàng khách hàng. Không có nhu cầu sử dụng `LATERAL`.

### 1.2. Truy vấn phụ tương quan (*correlated subquery*)

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c;
~~~

Subquery ở **danh sách `SELECT`** đọc `c.customer_id` của truy vấn ngoài. Nó là **correlated subquery**, dù **không viết `LATERAL`**.

Điểm quan trọng:

- “Tương quan” nói về **quan hệ phụ thuộc dữ liệu** giữa truy vấn trong và truy vấn ngoài.
- `LATERAL` là cú pháp đặc biệt cho **thành phần trong `FROM`** được phép tham chiếu các thành phần `FROM` đứng trước.
- Không phải mọi correlated subquery đều phải viết `LATERAL`. Ví dụ scalar subquery trong `SELECT` hoặc `EXISTS` trong `WHERE` đã có cơ chế tham chiếu truy vấn ngoài phù hợp.

## 2. Vì sao một subquery thông thường trong FROM không đủ?

Xét yêu cầu lấy hai đơn mới nhất cho mỗi khách hàng:

~~~sql
SELECT
    c.customer_name,
    x.order_id
FROM customers AS c
JOIN (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 2
) AS x ON TRUE;
~~~

Đoạn trên **không hợp lệ trong PostgreSQL**, vì subquery độc lập trong `FROM` không tự được phép tham chiếu `c.customer_id` ở phạm vi `FROM` bao quanh.

Thêm `LATERAL`:

~~~sql
SELECT
    c.customer_name,
    x.order_id
FROM customers AS c
JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS x ON TRUE;
~~~

Bây giờ cột `c.customer_id` có thể được dùng trong subquery `x`. Về **ngữ nghĩa SQL**, PostgreSQL xác định kết quả phía `x` theo giá trị của mỗi hàng `c`, rồi ghép các hàng kết quả. Bộ tối ưu có thể chọn cách thực thi phù hợp; không nên coi mô hình logic này là cam kết rằng PostgreSQL luôn khởi chạy lại nguyên một subquery vật lý đúng một lần cho từng hàng.

### Mô hình trực quan

~~~text
customers
  |
  +-- c = An    ---> subquery WHERE customer_id = 1
  |                   ORDER BY created_at DESC LIMIT 2
  |                   => hai đơn gần nhất của An
  |
  +-- c = Bình  ---> subquery WHERE customer_id = 2
  |                   ORDER BY created_at DESC LIMIT 2
  |                   => hai đơn gần nhất của Bình
  |
  +-- c = Chi   ---> subquery WHERE customer_id = 3
  |                   ORDER BY created_at DESC LIMIT 2
  |                   => hai đơn gần nhất của Chi
  |
  +-- c = Dũng  ---> subquery WHERE customer_id = 4
                      => tập rỗng nếu Dũng chưa có đơn
~~~

Việc xử lý **tập rỗng** là lý do cần phân biệt `CROSS JOIN LATERAL` và `LEFT JOIN LATERAL`.

## 3. Cú pháp LATERAL và phạm vi tham chiếu

Dạng phổ biến:

~~~sql
SELECT ...
FROM left_relation AS l
CROSS JOIN LATERAL (
    SELECT ...
    WHERE some_column = l.some_column
) AS r;
~~~

Hoặc:

~~~sql
SELECT ...
FROM left_relation AS l
LEFT JOIN LATERAL (
    SELECT ...
    WHERE some_column = l.some_column
) AS r ON TRUE;
~~~

Đối với hàm trả về tập hàng:

~~~sql
SELECT ...
FROM left_relation AS l
CROSS JOIN LATERAL
    some_set_returning_function(l.some_column) AS f;
~~~

### 3.1. LATERAL được phép nhìn những gì?

Một item `LATERAL` có thể tham chiếu các thành phần `FROM` đứng **trước nó** trong phạm vi hợp lệ. Khi `LATERAL` nằm bên phải một `JOIN`, nó có thể đọc các cột từ item hoặc cây JOIN ở bên trái theo cấu trúc câu SQL.

Ví dụ:

~~~sql
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT ...
    WHERE o.customer_id = c.customer_id
) AS latest ON TRUE
~~~

Hợp lệ vì `c` có mặt trước `latest`.

Không nên cố tham chiếu alias chỉ được khai báo **sau** item `LATERAL`:

~~~sql
-- Minh họa lỗi phạm vi; alias o2 chưa tồn tại khi x được định nghĩa:
FROM customers AS c
CROSS JOIN LATERAL (
    SELECT o2.order_id
) AS x
JOIN orders AS o2 ON TRUE
~~~

### 3.2. Phải đặt alias rõ ràng

Một subquery trong `FROM` nên có alias dễ hiểu:

~~~sql
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 1
) AS latest_order ON TRUE
~~~

Alias `latest_order` dùng để tham chiếu các cột ở phía ngoài:

~~~sql
SELECT latest_order.order_id
~~~

Khi hai bảng cùng có cột `order_id` hoặc `customer_id`, ghi đầy đủ `c.customer_id` và `o.customer_id` giúp tránh nhầm lẫn, đặc biệt trong truy vấn nhiều tầng.

### 3.3. LATERAL không phải một kiểu JOIN riêng

`LATERAL` **không thay thế** `INNER`, `LEFT` hoặc `CROSS`. Nó quyết định **khả năng tham chiếu bên trái** của item; kiểu JOIN quyết định cách ghép kết quả và xử lý trường hợp không có hàng.

| Cách viết | Có thể dùng cột bên trái? | Không có hàng kết quả bên phải |
| --- | --- | --- |
| `CROSS JOIN LATERAL (...) x` | Có | Hàng bên trái bị loại |
| `JOIN LATERAL (...) x ON TRUE` | Có | Hàng bên trái bị loại |
| `LEFT JOIN LATERAL (...) x ON TRUE` | Có | Giữ một hàng bên trái, cột phải là null |
| `CROSS JOIN (SELECT ...) x` | Không tham chiếu bên trái như item LATERAL | Hàng bên trái bị loại nếu subquery rỗng |

Với các trường hợp phức tạp, có thể tồn tại các kiểu join khác và cách nhóm cây JOIN ảnh hưởng phạm vi tên. Trong bài này, dùng `CROSS` và `LEFT` vì chúng biểu đạt rõ nhất các mẫu truy vấn thực tế.

## 4. Tạo bộ dữ liệu PostgreSQL để thực hành

Các câu SQL sau dành cho **database lab**, không chạy trong môi trường chứa dữ liệu cần giữ. Giả sử bạn có quyền tạo schema và bảng.

### 4.1. Tạo schema và bảng khách hàng

~~~sql
CREATE SCHEMA lateral_lab;

CREATE TABLE lateral_lab.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    signup_date date NOT NULL
);

INSERT INTO lateral_lab.customers
    (customer_id, customer_name, signup_date)
VALUES
    (1, 'An',   DATE '2026-08-10'),
    (2, 'Binh', DATE '2026-08-12'),
    (3, 'Chi',  DATE '2026-08-15'),
    (4, 'Dung', DATE '2026-08-20');
~~~

Khách hàng `Dung` cố ý **chưa có đơn hàng** để dễ nhận biết sự khác biệt giữa `CROSS JOIN LATERAL` và `LEFT JOIN LATERAL`.

### 4.2. Tạo bảng đơn hàng

~~~sql
CREATE TABLE lateral_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lateral_lab.customers(customer_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    amount numeric(12, 2) NOT NULL
        CHECK (amount >= 0),
    tags jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(tags) = 'array')
);

INSERT INTO lateral_lab.orders (
    order_id, customer_id, created_at,
    status, amount, tags
) VALUES
    (101, 1, '2026-09-01 09:00+07',
        'paid', 120.00, '["gift","priority"]'::jsonb),
    (102, 1, '2026-09-03 10:00+07',
        'pending', 80.00, '["review"]'::jsonb),
    (103, 1, '2026-09-05 09:00+07',
        'paid', 200.00, '["priority"]'::jsonb),
    (201, 2, '2026-09-02 08:00+07',
        'paid', 50.00, '["gift"]'::jsonb),
    (202, 2, '2026-09-06 11:00+07',
        'cancelled', 30.00, '[]'::jsonb),
    (301, 3, '2026-09-04 14:00+07',
        'pending', 90.00, '["review","fragile"]'::jsonb),
    (302, 3, '2026-09-07 15:00+07',
        'paid', 160.00, '["priority"]'::jsonb),
    (303, 3, '2026-09-07 16:00+07',
        'paid', 210.00, '["gift","priority"]'::jsonb);
~~~

### 4.3. Tạo bảng chi tiết đơn hàng

~~~sql
CREATE TABLE lateral_lab.order_items (
    item_id integer PRIMARY KEY,
    order_id integer NOT NULL
        REFERENCES lateral_lab.orders(order_id),
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);

INSERT INTO lateral_lab.order_items (
    item_id, order_id, sku, quantity, unit_price
) VALUES
    (1, 101, 'PEN',   2, 10.00),
    (2, 101, 'NOTE',  1, 100.00),
    (3, 102, 'BOOK',  1, 80.00),
    (4, 103, 'BAG',   2, 100.00),
    (5, 201, 'BOOK',  1, 50.00),
    (6, 202, 'BOOK',  1, 30.00),
    (7, 301, 'GIFT',  3, 30.00),
    (8, 302, 'LAMP',  2, 80.00),
    (9, 303, 'CLOCK', 1, 100.00),
    (10, 303, 'PAD',  1, 110.00);
~~~

Trong bộ dữ liệu này:

| customer_id | Khách hàng | Số đơn | Đơn mới nhất | Hai đơn mới nhất |
| ---: | --- | ---: | ---: | --- |
| 1 | An | 3 | 103 | 103, 102 |
| 2 | Binh | 2 | 202 | 202, 201 |
| 3 | Chi | 3 | 303 | 303, 302 |
| 4 | Dung | 0 | Không có | Không có |

Bảng chi tiết có hai mặt hàng cho đơn 101 và 303, còn những đơn khác chỉ có một mặt hàng. Điều đó giúp minh họa **một hàng ở bên trái có thể sinh nhiều hàng bên phải**.

### 4.4. Kiểm tra dữ liệu

~~~sql
SELECT c.customer_id, c.customer_name, COUNT(o.order_id) AS n
FROM lateral_lab.customers AS c
LEFT JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả số đơn theo khách là **3, 2, 3, 0**. Các ví dụ tiếp theo giả định dữ liệu mẫu chưa bị chỉnh sửa.

## 5. Correlated scalar subquery: lấy một giá trị cho mỗi hàng

Cách viết không cần `LATERAL`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.order_id
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_order_id
FROM lateral_lab.customers AS c
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | customer_name | latest_order_id |
| ---: | --- | ---: |
| 1 | An | 103 |
| 2 | Binh | 202 |
| 3 | Chi | 303 |
| 4 | Dung | `NULL` |

Vì subquery trả về **một cột** và có `LIMIT 1`, nó phù hợp làm **scalar expression** trong `SELECT`. Khi không có đơn, scalar subquery trả `NULL`.

### Khi nào scalar subquery trở nên bất tiện?

Nếu cần `order_id`, `created_at`, `status` và `amount` của **cùng một đơn mới nhất**, bạn có thể viết bốn correlated subquery gần giống nhau. Nhưng điều đó lặp logic `WHERE`/`ORDER BY` và làm truy vấn khó bảo trì.

LATERAL cho phép lấy **nhiều cột từ cùng một subquery**:

~~~sql
SELECT
    c.customer_name,
    latest.order_id,
    latest.created_at,
    latest.status,
    latest.amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id, o.created_at, o.status, o.amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
~~~

Về ý nghĩa, đây là “mỗi khách hàng kèm một đơn mới nhất nếu có”.

### Lưu ý scalar subquery có thể lỗi khi trả nhiều hàng

Một scalar subquery được dùng làm biểu thức phải trả **không quá một hàng**. Nếu bỏ `LIMIT 1` mà một khách có nhiều đơn:

~~~sql
-- Có thể lỗi vì subquery trả nhiều hơn một hàng:
SELECT
    c.customer_id,
    (
        SELECT o.order_id
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS one_order_id
FROM lateral_lab.customers AS c;
~~~

PostgreSQL không tự chọn ngẫu nhiên một hàng khi scalar subquery trả nhiều hàng; đây là lỗi ngữ nghĩa. Nếu thực sự cần **tập nhiều hàng cho mỗi khách**, `LATERAL` trong `FROM` là công cụ thích hợp hơn.

## 6. CROSS JOIN LATERAL: chỉ giữ hàng có kết quả

Lấy **hai đơn mới nhất của mỗi khách**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.created_at,
    recent.status
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.created_at, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent
ORDER BY
    c.customer_id,
    recent.created_at DESC,
    recent.order_id DESC;
~~~

Kết quả có **6 hàng**:

| customer_id | Khách | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 103 | paid |
| 1 | An | 102 | pending |
| 2 | Binh | 202 | cancelled |
| 2 | Binh | 201 | paid |
| 3 | Chi | 303 | paid |
| 3 | Chi | 302 | paid |

**Dung không xuất hiện**, vì subquery ứng với `customer_id = 4` trả tập rỗng. `CROSS JOIN LATERAL` có ngữ nghĩa ghép các hàng hiện có từ bên phải; không có hàng thì không tạo ra hàng kết quả cho khách đó.

### Một khách có thể xuất hiện nhiều lần

`LATERAL` không bảo đảm kết quả một-một. Nếu subquery trả hai hàng cho một khách, khách ấy xuất hiện hai lần trong kết quả. Nếu subquery trả 100 hàng, có thể xuất hiện 100 lần.

Điều này đặc biệt quan trọng khi kết quả sau `LATERAL` được đưa vào phép `SUM` hoặc một JOIN tiếp theo.

### CROSS JOIN LATERAL và JOIN LATERAL ... ON TRUE

Trong ví dụ trả các hàng phù hợp, hai dạng sau tương đương về kết quả:

~~~sql
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (...) AS recent
~~~

~~~sql
FROM lateral_lab.customers AS c
JOIN LATERAL (...) AS recent ON TRUE
~~~

Hãy chọn một phong cách nhất quán và làm rõ ý nghĩa “chỉ lấy khách có kết quả”. Khi muốn giữ khách không có đơn, chuyển sang `LEFT JOIN LATERAL`.

## 7. LEFT JOIN LATERAL: giữ cả khách chưa có đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.created_at,
    recent.status
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.created_at DESC NULLS LAST,
    recent.order_id DESC NULLS LAST;
~~~

Kết quả có **7 hàng**: sáu hàng giống phần trước, cộng thêm:

| customer_id | customer_name | order_id | created_at | status |
| ---: | --- | --- | --- | --- |
| 4 | Dung | `NULL` | `NULL` | `NULL` |

`LEFT JOIN` giữ **một hàng phía trái** khi subquery bên phải trả rỗng, và đặt các cột bên phải thành null.

### Vì sao ON TRUE?

`ON TRUE` có nghĩa không thêm điều kiện lọc sau khi ghép. Điều kiện liên kết đã nằm **bên trong subquery LATERAL**:

~~~sql
WHERE o.customer_id = c.customer_id
~~~

Đối với mẫu này, `LEFT JOIN LATERAL (...) AS recent ON TRUE` là cách viết rõ ràng và thường gặp.

### Không chuyển điều kiện bên phải ra WHERE một cách tùy tiện

So sánh:

~~~sql
SELECT c.customer_id, recent.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
WHERE recent.status = 'paid';
~~~

Điều kiện `WHERE recent.status = 'paid'` chạy **sau LEFT JOIN**:

- Khách chưa có đơn có `recent.status = NULL` nên bị loại.
- Khách có đơn mới nhất không paid cũng bị loại.
- Nó **không** có nghĩa “lấy đơn paid mới nhất”.

Muốn giữ mọi khách và tìm đơn **paid** mới nhất, đặt điều kiện **bên trong** subquery `LATERAL`.

## 8. Top 1 theo điều kiện: đơn paid gần nhất của mỗi khách

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    paid_latest.order_id AS latest_paid_order_id,
    paid_latest.amount AS latest_paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.amount, o.created_at
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS paid_latest ON TRUE
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | Khách | latest_paid_order_id | latest_paid_amount |
| ---: | --- | ---: | ---: |
| 1 | An | 103 | 200.00 |
| 2 | Binh | 201 | 50.00 |
| 3 | Chi | 303 | 210.00 |
| 4 | Dung | `NULL` | `NULL` |

Điều kiện `status = 'paid'` được áp dụng **trước `ORDER BY ... LIMIT 1` trong subquery**. Vì vậy, đơn mới nhất của Binh tuy là 202 (`cancelled`) nhưng truy vấn chọn đơn paid gần nhất là 201.

**Quy tắc thiết kế:** nếu yêu cầu là “top N hàng thỏa điều kiện X cho mỗi nhóm”, điều kiện X cần được áp dụng ở **tập đầu vào được xếp hạng**, trước khi giới hạn N. Đổi thứ tự lọc có thể làm sai nghiệp vụ dù cú pháp SQL vẫn hợp lệ.

### Tại sao cần ORDER BY với LIMIT?

~~~sql
LIMIT 1
~~~

một mình không định nghĩa “mới nhất”. Nếu không có `ORDER BY` phù hợp, PostgreSQL có thể trả một hàng bất kỳ tùy plan và trạng thái lưu trữ.

Nếu nhiều đơn có cùng `created_at`, thêm `order_id DESC` làm khóa phá hòa. Hãy chọn một tiêu chí có thứ tự quyết định phù hợp nghiệp vụ, thay vì trông chờ thứ tự ngầm của bảng.

## 9. LIMIT bên trong LATERAL và LIMIT bên ngoài khác nhau

Xét hai truy vấn:

~~~sql
-- A: tối đa hai đơn cho MỖI khách.
SELECT c.customer_id, recent.order_id
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS recent;
~~~

~~~sql
-- B: giới hạn hai hàng trên TOÀN BỘ kết quả join.
SELECT c.customer_id, o.order_id
FROM lateral_lab.customers AS c
JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 2;
~~~

Trong A, `LIMIT 2` nằm **trong subquery tương quan**, nên tối đa hai đơn **mỗi khách**.

Trong B, `LIMIT 2` nằm **ngoài cùng**, nên chỉ có hai hàng **toàn bộ kết quả**, không bảo đảm mỗi khách có hai đơn.

Đây là lý do `LATERAL` đặc biệt tiện cho bài toán **top-N-per-group**.

## 10. LATERAL với aggregate: thống kê riêng cho mỗi khách

Một subquery `LATERAL` không nhất thiết trả nhiều hàng; nó có thể trả **một hàng aggregate cho mỗi khách**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    stats.total_orders,
    stats.paid_orders,
    stats.paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (
            WHERE o.status = 'paid'
        ) AS paid_orders,
        COALESCE(
            SUM(o.amount) FILTER (
                WHERE o.status = 'paid'
            ),
            0::numeric
        ) AS paid_amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS stats ON TRUE
ORDER BY c.customer_id;
~~~

Kết quả:

| Khách | total_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| An | 3 | 2 | 320.00 |
| Binh | 2 | 1 | 50.00 |
| Chi | 3 | 2 | 370.00 |
| Dung | 0 | 0 | 0.00 |

Trong subquery:

~~~sql
SELECT COUNT(*), SUM(...)
FROM lateral_lab.orders AS o
WHERE o.customer_id = c.customer_id
~~~

không có `GROUP BY`. Đây là phép tổng hợp trên toàn bộ tập đơn của khách tương ứng.

### Vì sao khách không có đơn vẫn nhận một hàng stats?

Một aggregate query **không có `GROUP BY`** như:

~~~sql
SELECT COUNT(*) AS n
FROM lateral_lab.orders
WHERE customer_id = -1;
~~~

vẫn trả **một hàng** chứa `n = 0`. `SUM(...)` trong tập rỗng thường trả `NULL`, nên ví dụ trên dùng `COALESCE` để biểu diễn 0 khi nghiệp vụ phù hợp.

Do subquery aggregate tự tạo **một hàng** cho khách không có đơn, trong trường hợp này `CROSS JOIN LATERAL` cũng có thể giữ khách Dung. **Không được suy rộng** rằng `CROSS JOIN LATERAL` nói chung luôn giữ hàng trái: các subquery trả nhiều hàng không có aggregate có thể trả rỗng và làm mất khách.

### Khi nào không cần LATERAL cho thống kê?

Cùng kết quả có thể đạt bằng `LEFT JOIN` và `GROUP BY`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Nếu cần thống kê **cho toàn bộ khách**, cách `GROUP BY` có thể thuận tiện và có kế hoạch thực thi hiệu quả hơn tùy dữ liệu. `LATERAL` đặc biệt hữu ích khi subquery phụ thuộc hàng trái có `ORDER BY ... LIMIT`, chọn một tập đặc biệt hoặc trả cấu trúc phức tạp.

## 11. Correlated EXISTS và NOT EXISTS: khi chỉ cần biết có hay không

Nếu yêu cầu là **khách nào đã từng có đơn paid**, không nhất thiết cần `LATERAL`.

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lateral_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
)
ORDER BY c.customer_id;
~~~

Kết quả: An, Binh và Chi.

`EXISTS` chỉ cần biết tập con có **ít nhất một hàng**; PostgreSQL có thể tối ưu theo kiểu semi-join và không cần tạo ra mọi hàng đơn trong kết quả.

Khách chưa có đơn:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lateral_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả: Dung.

### EXISTS hay LEFT JOIN LATERAL?

| Mục tiêu | Mẫu thường phù hợp |
| --- | --- |
| Chỉ lọc khách có đơn paid hay không | `EXISTS` |
| Chỉ lọc khách chưa có đơn | `NOT EXISTS` |
| Lấy thông tin của đơn paid mới nhất | `LEFT JOIN LATERAL ... ORDER BY ... LIMIT 1` |
| Lấy hai đơn mới nhất cho mỗi khách | `JOIN LATERAL ... LIMIT 2` |
| Tính nhiều tổng hợp từ các hàng cùng khách | `GROUP BY` hoặc LATERAL aggregate tùy workload |

`LATERAL` không phải câu trả lời duy nhất cho mọi correlated query. Chọn công cụ đơn giản nhất thể hiện đúng kết quả cần lấy.

## 12. LATERAL với truy vấn nhiều tầng: kết quả của tầng trước thành đầu vào tầng sau

Một mẫu hữu ích là **chuỗi LATERAL**:

1. Tìm đơn gần nhất của khách hàng.
2. Dùng `order_id` vừa tìm được để thống kê số mặt hàng của đơn ấy.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    latest.order_id AS latest_order_id,
    latest.status AS latest_status,
    item_stats.item_lines,
    item_stats.total_quantity
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status, o.created_at
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS item_lines,
        COALESCE(SUM(i.quantity), 0) AS total_quantity
    FROM lateral_lab.order_items AS i
    WHERE i.order_id = latest.order_id
) AS item_stats ON TRUE
ORDER BY c.customer_id;
~~~

Kết quả có thể đọc như sau:

| Khách | latest_order_id | latest_status | item_lines | total_quantity |
| --- | ---: | --- | ---: | ---: |
| An | 103 | paid | 1 | 2 |
| Binh | 202 | cancelled | 1 | 1 |
| Chi | 303 | paid | 2 | 2 |
| Dung | `NULL` | `NULL` | 0 | 0 |

Phần `item_stats` nhìn thấy alias `latest` vì `latest` đã xuất hiện trước nó trong cây JOIN. Với Dung, `latest.order_id` là `NULL`; điều kiện `i.order_id = NULL` không khớp hàng nào, nhưng aggregate không có `GROUP BY` vẫn trả `COUNT(*) = 0`.

### Điều gì xảy ra nếu tầng đầu dùng CROSS JOIN LATERAL?

Nếu thay `LEFT JOIN LATERAL` đầu tiên bằng `CROSS JOIN LATERAL`, khách Dung bị loại **ngay từ tầng đầu**, nên không còn hàng để chuyển sang tầng sau. Cần quyết định giữ hay loại nhóm rỗng **ở mỗi bước**.

### Chú ý cách ghi tên cột

Trong chuỗi nhiều tầng, có thể có cột `order_id` ở cả bảng `orders` và `order_items`. Ghi `latest.order_id` và `i.order_id` đầy đủ giúp tránh lỗi ambiguous column và làm rõ phụ thuộc.

## 13. LATERAL với set-returning function

Một số hàm PostgreSQL trả về **nhiều hàng**, không phải một scalar. Khi tham số của hàm phụ thuộc vào hàng trước, `LATERAL` là cách diễn đạt tự nhiên.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    dates.day_ts::date AS calendar_day
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL generate_series(
    c.signup_date::timestamp,
    (c.signup_date + 2)::timestamp,
    interval '1 day'
) AS dates(day_ts)
ORDER BY c.customer_id, dates.day_ts;
~~~

Mỗi khách tạo ra **ba ngày**: ngày đăng ký, ngày kế tiếp và ngày thứ hai sau đăng ký.

| Khách | signup_date | Các ngày sinh ra |
| --- | --- | --- |
| An | 2026-08-10 | 10, 11, 12 tháng 8 |
| Binh | 2026-08-12 | 12, 13, 14 tháng 8 |
| Chi | 2026-08-15 | 15, 16, 17 tháng 8 |
| Dung | 2026-08-20 | 20, 21, 22 tháng 8 |

Hàm `generate_series` trả nhiều hàng; mỗi hàng của `customers` có thể tạo một dải giá trị riêng theo `signup_date`.

### Hàm trong FROM có thể tham chiếu bên trái mà không ghi LATERAL

PostgreSQL cho phép **đối số của hàm** trong `FROM` tham chiếu các item `FROM` trước đó ngay cả khi không viết từ khóa `LATERAL` tường minh:

~~~sql
FROM lateral_lab.customers AS c
CROSS JOIN generate_series(
    c.signup_date::timestamp,
    (c.signup_date + 2)::timestamp,
    interval '1 day'
) AS d(day_ts)
~~~

Đó là hành vi đặc biệt dành cho **function calls in FROM**. Với một **SELECT subquery trong FROM** muốn tham chiếu hàng bên trái, hãy viết `LATERAL` rõ ràng.

Trong tài liệu hoặc code team, nhiều người vẫn viết `LATERAL` với hàm để biểu đạt ý định “hàm phụ thuộc từng hàng”.

## 14. JSONB array và LATERAL: biến mảng thành các dòng

Bảng `orders` có cột `tags jsonb`, mỗi giá trị là một JSON array.

Ví dụ đơn 101:

~~~json
["gift", "priority"]
~~~

Muốn trả từng nhãn thành một hàng:

~~~sql
SELECT
    o.order_id,
    tag.value AS tag
FROM lateral_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.tags) AS tag(value)
ORDER BY o.order_id, tag.value;
~~~

Hàm `jsonb_array_elements_text` trả các phần tử array dưới dạng text.

Đối với đơn 101:

| order_id | tag |
| ---: | --- |
| 101 | gift |
| 101 | priority |

Đơn 202 có `tags = []`, nên hàm trả **không hàng nào**. Khi dùng `CROSS JOIN LATERAL`, **đơn 202 biến mất khỏi kết quả**.

### LEFT JOIN LATERAL giữ đơn có mảng rỗng

~~~sql
SELECT
    o.order_id,
    tag.value AS tag
FROM lateral_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(o.tags) AS tag(value)
    ON TRUE
ORDER BY o.order_id, tag.value NULLS LAST;
~~~

Lúc này đơn 202 xuất hiện với `tag = NULL`. Cũng giống khách không có đơn, đây là hành vi **null-extend** của `LEFT JOIN`.

### WITH ORDINALITY: giữ vị trí phần tử

~~~sql
SELECT
    o.order_id,
    tag.position,
    tag.value AS tag
FROM lateral_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.tags)
        WITH ORDINALITY AS tag(value, position)
ORDER BY o.order_id, tag.position;
~~~

`WITH ORDINALITY` thêm số thứ tự phần tử **bắt đầu từ 1**. Với đơn 101:

| order_id | position | tag |
| ---: | ---: | --- |
| 101 | 1 | gift |
| 101 | 2 | priority |

Điều này quan trọng khi thứ tự mảng có ý nghĩa. Không nên chỉ `ORDER BY tag.value` rồi coi đó là thứ tự ban đầu trong JSON.

### Nếu JSON không phải array?

`jsonb_array_elements_text` yêu cầu dữ liệu đầu vào phù hợp là JSON array (giá trị SQL null thì không sinh hàng). Trong bộ dữ liệu mẫu, `CHECK (jsonb_typeof(tags) = 'array')` và `NOT NULL` bảo vệ hình dạng dữ liệu.

Nếu dữ liệu JSONB thực tế có thể là object, scalar hoặc kiểu không mong đợi, hàm tách mảng có thể báo lỗi. Cần chuẩn hóa dữ liệu hoặc đặt điều kiện/xử lý đúng hình dạng trước khi triển khai.

## 15. UNNEST và mảng SQL

PostgreSQL có kiểu mảng SQL như `text[]` hoặc `integer[]`, khác với JSONB array. Hàm `unnest` cũng có thể trả nhiều hàng.

Ví dụ một danh sách mã trên mỗi cửa hàng:

~~~sql
WITH stores(store_id, sku_codes) AS (
    VALUES
        (1, ARRAY['A','B','C']::text[]),
        (2, ARRAY['D']::text[]),
        (3, ARRAY[]::text[])
)
SELECT
    s.store_id,
    sku.sku_code
FROM stores AS s
LEFT JOIN LATERAL unnest(s.sku_codes)
    AS sku(sku_code) ON TRUE
ORDER BY s.store_id, sku.sku_code;
~~~

Kết quả:

| store_id | sku_code |
| ---: | --- |
| 1 | A |
| 1 | B |
| 1 | C |
| 2 | D |
| 3 | `NULL` |

Đổi `LEFT JOIN LATERAL` sang `CROSS JOIN LATERAL` thì store 3 sẽ bị loại vì mảng rỗng.

### Nhiều mảng song song có thể cần cẩn thận

PostgreSQL hỗ trợ một số dạng `unnest` nhiều mảng, nhưng cách ghép phần tử theo vị trí, mảng khác độ dài và giá trị null cần được hiểu rõ trước khi dùng. Với dữ liệu quan hệ quan trọng và có nhiều thuộc tính trên từng phần tử, một **bảng con chuẩn hóa** thường dễ bảo vệ bằng `FOREIGN KEY`, `CHECK` và index hơn việc giữ nhiều mảng song song.

## 16. LATERAL có thể gom nhiều hàng thành một giá trị

Một `LATERAL` không nhất thiết làm **tăng số dòng** kết quả. Ta có thể gom danh sách top 2 thành JSONB array trên **một hàng mỗi khách**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        recent.orders_json,
        '[]'::jsonb
    ) AS recent_orders
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object(
            'order_id', x.order_id,
            'status', x.status,
            'amount', x.amount
        )
        ORDER BY x.created_at DESC, x.order_id DESC
    ) AS orders_json
    FROM (
        SELECT
            o.order_id, o.created_at, o.status, o.amount
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 2
    ) AS x
) AS recent ON TRUE
ORDER BY c.customer_id;
~~~

Ý nghĩa các lớp:

1. Subquery `x` chọn tối đa **hai đơn mới nhất theo từng khách**.
2. `jsonb_agg(...)` gom những hàng đã chọn thành JSONB array.
3. `LEFT JOIN LATERAL` gắn array vào khách hàng đang xét.
4. `COALESCE(..., '[]'::jsonb)` trả array rỗng cho Dung.

Đây là một cách chuẩn bị dữ liệu cho API cần trả:

~~~json
{
  "customer_id": 1,
  "customer_name": "An",
  "recent_orders": [
    {"order_id": 103, "status": "paid", "amount": 200.00},
    {"order_id": 102, "status": "pending", "amount": 80.00}
  ]
}
~~~

Ví dụ JSON trên minh họa **cấu trúc kết quả**, không khẳng định byte-for-byte thứ tự key hay biểu diễn numeric của driver/JSON serializer. `jsonb` không bảo đảm thứ tự các **khóa đối tượng**, còn thứ tự **phần tử array** được chỉ rõ bằng `ORDER BY` bên trong `jsonb_agg`.

### Vì sao không chỉ viết LIMIT 2 sau jsonb_agg?

~~~sql
SELECT jsonb_agg(...)
FROM lateral_lab.orders
LIMIT 2;
~~~

`LIMIT 2` ở ngoài aggregate **không giới hạn hai hàng được đưa vào JSONB_AGG**; aggregate đã gom các hàng thành một kết quả trước khi giới hạn các hàng đầu ra. Muốn “hai đơn rồi mới gom”, đặt `ORDER BY ... LIMIT 2` trong subquery trước `jsonb_agg`.

## 17. Cẩn thận khi ghép nhiều LATERAL trả nhiều hàng

Giả sử một khách có hai đơn gần nhất, và bạn ghép thêm ba nhãn/tập kết quả độc lập ở phía sau. Các bảng phải được ghép theo cấu trúc cụ thể; nếu hai `LATERAL` độc lập đều trả nhiều hàng mà không có mối liên hệ thích hợp, số hàng có thể bị **nhân lên**.

Mô hình:

~~~text
Một khách
  |
  +-- recent_orders => 2 hàng
  |
  +-- special_tags  => 3 hàng
  |
  +-- ghép độc lập   => 2 x 3 = 6 hàng
~~~

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    r.order_id,
    t.tag
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS r
CROSS JOIN LATERAL (
    SELECT tag
    FROM unnest(ARRAY['a','b','c']::text[]) AS q(tag)
) AS t
WHERE c.customer_id = 1
ORDER BY r.order_id, t.tag;
~~~

Kết quả có **6 hàng** cho khách An: 2 đơn × 3 nhãn độc lập.

**Không phải lỗi của PostgreSQL:** đó là ngữ nghĩa kết hợp tập hàng. Nếu chỉ muốn mỗi đơn có những tag thật sự của nó, subquery/hàm phía sau phải **tương quan với `r.order_id` hoặc cột của đơn tương ứng**:

~~~sql
SELECT
    c.customer_id,
    r.order_id,
    tag.value AS tag
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.tags
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS r
LEFT JOIN LATERAL
    jsonb_array_elements_text(r.tags)
        AS tag(value) ON TRUE
WHERE c.customer_id = 1
ORDER BY r.order_id, tag.value;
~~~

Trong ví dụ này, nhãn được mở rộng **từ mảng tag của chính đơn đó**, không phải từ một tập độc lập dùng chung.

### Quy tắc tổng hợp

Trước khi viết `COUNT(*)` hoặc `SUM(amount)` sau nhiều `LATERAL`, hỏi:

- Một hàng ở bảng nguồn còn đại diện **một đơn**, hay đã trở thành **một cặp đơn–tag**?
- Một đối tượng nghiệp vụ có thể xuất hiện bao nhiêu lần?
- Nếu cần tính tổng tiền đơn, có nên tổng hợp tiền **trước khi mở rộng tag** hay không?

`COUNT(DISTINCT order_id)` có thể giúp đếm số đơn sau khi nhân hàng, nhưng `SUM(DISTINCT amount)` **không phải sửa lỗi tổng quát** vì hai đơn khác nhau có thể có cùng số tiền.

## 18. LATERAL so với ROW_NUMBER cho top-N-per-group

Ngoài `LATERAL`, PostgreSQL có thể dùng window function `ROW_NUMBER()` để xếp hạng mỗi nhóm.

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM lateral_lab.orders AS o
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id,
    r.created_at,
    r.status
FROM lateral_lab.customers AS c
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
   AND r.rn <= 2
ORDER BY c.customer_id, r.rn NULLS LAST;
~~~

Kết quả tương đương ví dụ `LEFT JOIN LATERAL ... LIMIT 2`: An, Binh, Chi có tối đa hai đơn và Dung có một hàng null.

### Hai hướng xử lý

~~~text
LATERAL:
  Duyệt tập khách cần lấy
       -> với mỗi khách, tìm top 2 đơn phù hợp

ROW_NUMBER:
  Xếp hạng các đơn theo từng customer_id
       -> giữ rn <= 2
       -> nối lại khách
~~~

Đây là **mô hình logic**; kế hoạch vật lý do PostgreSQL quyết định.

| Tình huống | LATERAL thường đáng cân nhắc | ROW_NUMBER thường đáng cân nhắc |
| --- | --- | --- |
| Chỉ lấy top 1–3 cho một số ít khách đã lọc | Có | Có thể tốn công xếp hạng nhiều đơn hơn cần thiết |
| Có index theo `(customer_id, created_at DESC)` | Có thể tận dụng lookup + LIMIT | Cũng có thể tận dụng thứ tự index tùy plan |
| Cần top N cho rất nhiều khách | Cần đo số lần lookup | Một lần xử lý tập đơn có thể phù hợp |
| Cần thứ hạng của mọi đơn | Không phải mục tiêu chính | Rất phù hợp |
| Cần giữ cả khách không có đơn | `LEFT JOIN LATERAL` | `LEFT JOIN` với ranked result |

Không có “một mẫu luôn nhanh hơn”. Hãy dùng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện, với cùng tập khách và cùng điều kiện.

## 19. LATERAL so với DISTINCT ON cho top 1

PostgreSQL có cú pháp `DISTINCT ON` để chọn **một hàng đầu tiên** của mỗi nhóm theo thứ tự đã định:

~~~sql
SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    o.order_id,
    o.created_at,
    o.status
FROM lateral_lab.orders AS o
ORDER BY
    o.customer_id,
    o.created_at DESC,
    o.order_id DESC;
~~~

Kết quả trả đơn mới nhất cho khách 1, 2, 3; không có hàng cho Dung vì không có đơn.

Muốn giữ tất cả khách:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    latest.order_id,
    latest.status
FROM lateral_lab.customers AS c
LEFT JOIN (
    SELECT DISTINCT ON (o.customer_id)
        o.customer_id, o.order_id, o.status, o.created_at
    FROM lateral_lab.orders AS o
    ORDER BY
        o.customer_id,
        o.created_at DESC,
        o.order_id DESC
) AS latest
    ON latest.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

### Quy tắc của DISTINCT ON

Trong PostgreSQL, biểu thức `DISTINCT ON` phải tương ứng với các biểu thức đứng đầu `ORDER BY` theo quy tắc của cú pháp. Nếu muốn một đơn mới nhất cho mỗi khách:

~~~sql
DISTINCT ON (customer_id)
ORDER BY customer_id, created_at DESC, order_id DESC
~~~

`ORDER BY` quyết định **hàng nào được giữ** trong mỗi nhóm. Nếu thiếu thứ tự rõ ràng, “hàng đầu tiên” không có ý nghĩa nghiệp vụ ổn định.

### Khi nào chọn cách nào?

- `DISTINCT ON` gọn khi cần **một hàng** cho mỗi nhóm.
- `ROW_NUMBER()` linh hoạt khi cần top N, ranking hoặc nhiều phép window.
- `LATERAL` mạnh khi top N phụ thuộc vào **tập thực thể bên ngoài** đã lọc, có giới hạn riêng theo từng hàng, hoặc cần dữ liệu phụ từ những subquery/hàm tương quan.

Đừng chuyển cú pháp chỉ vì nghe một mẹo tối ưu; kiểm chứng kết quả và plan.

## 20. Tạo chỉ mục phù hợp cho LATERAL top-N

Truy vấn:

~~~sql
SELECT c.customer_id, recent.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE;
~~~

đặt điều kiện bằng trên `customer_id` và sắp xếp theo `created_at DESC, order_id DESC`. Một B-tree index đáng đánh giá:

~~~sql
CREATE INDEX idx_orders_customer_recent
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

Với tập đơn hàng lớn, PostgreSQL có thể sử dụng index này để:

1. Đi tới các mục `customer_id` của khách tương ứng.
2. Đọc theo thứ tự gần với `ORDER BY`.
3. Dừng sau khi lấy đủ 2 hàng nếu kế hoạch và điều kiện cho phép.

Đó là tình huống thường đem lại lợi ích cho mẫu `LATERAL ... ORDER BY ... LIMIT N`.

### Nếu chỉ tìm đơn paid mới nhất

Một phương án khác cần cân nhắc:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
WHERE status = 'paid';
~~~

Đây là **partial index** chỉ chứa đơn có `status = 'paid'`. Nó có thể hữu ích nếu ứng dụng thường chạy:

~~~sql
WHERE o.customer_id = c.customer_id
  AND o.status = 'paid'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 1
~~~

Nhưng đừng tạo cả hai index vô điều kiện: mỗi index chiếm dung lượng và tăng chi phí ghi. Nếu hầu hết đơn đều paid hoặc workload không dùng truy vấn ấy, lợi ích của partial index có thể không đáng chi phí.

### INCLUDE có nên sử dụng?

Nếu truy vấn cần thêm `status` và `amount`, có thể xem xét chỉ mục bao phủ:

~~~sql
CREATE INDEX idx_orders_recent_include
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, amount);
~~~

Đây là **một lựa chọn thay thế để thử nghiệm**, không phải chỉ thị phải tạo thêm index thứ ba. Index-only scan chỉ khả thi khi dữ liệu cần nằm trong index và **điều kiện visibility** cho phép; INCLUDE tăng dung lượng index. Đánh giá bằng plan thực tế và số lần đọc dữ liệu.

## 21. Đọc EXPLAIN cho truy vấn LATERAL

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    r.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS r ON TRUE
ORDER BY c.customer_id;
~~~

Trong một kế hoạch điển hình, bạn có thể gặp:

~~~text
Nested Loop Left Join
  -> Scan customers
  -> Limit
       -> Index Scan using idx_orders_customer_recent
            Index Cond: (customer_id = c.customer_id)
~~~

Đoạn trên chỉ là **sơ đồ minh họa**, không phải output `EXPLAIN` cam kết xuất hiện. Với bảng mẫu rất nhỏ, PostgreSQL có thể chọn `Seq Scan` và `Sort` vì cách đó rẻ hơn dùng index.

### Những điểm cần đọc

| Thành phần EXPLAIN | Cách hiểu |
| --- | --- |
| `Nested Loop` | Có thể thấy bên trong được đánh giá theo tham số từ phía ngoài |
| `loops` | Số lần node thực thi theo số liệu đo được; cần xem cùng rows/time |
| `Index Cond` | Phần điều kiện được dùng cho truy cập index |
| `Filter` | Điều kiện lọc còn lại tại node |
| `Limit` | Giới hạn số hàng của tập con trong phạm vi tương ứng |
| `Sort` | PostgreSQL cần sắp xếp nếu đường truy cập không trả sẵn thứ tự phù hợp |
| `actual rows` / `actual time` | Kết quả/thời gian đo từ lần thực thi |
| `BUFFERS` | Hoạt động bộ đệm và truy cập block theo cách PostgreSQL thống kê |

Đọc **`loops` kết hợp `actual rows`**: số hàng được hiển thị cho node có thể là trung bình trên một lần lặp; không nên nhân hoặc cộng tùy tiện khi so sánh chi phí.

### LATERAL có luôn chạy một lần vật lý trên mỗi hàng?

Không thể khẳng định vậy cho mọi truy vấn. `LATERAL` mô tả **khả năng phụ thuộc tham chiếu và ngữ nghĩa kết quả**; planner có thể biến đổi biểu thức, kết hợp join hoặc chọn các bước thực thi tối ưu hợp lệ. Với mẫu `ORDER BY ... LIMIT` phụ thuộc hàng ngoài, nested loop parameterized index scan là một kiểu plan thường gặp, nhưng không phải một bảo đảm.

## 22. Rủi ro N+1 ở phía database

Ứng dụng có thể gặp mẫu **N+1 query** khi:

1. Gửi SQL lấy 10.000 khách hàng.
2. Từ Java, lặp qua khách và gửi thêm 10.000 SQL lấy đơn mới nhất.

`LATERAL` có thể gom việc đó thành **một câu SQL gửi từ client**, giảm rất nhiều round trip qua mạng.

Tuy nhiên, nó không tự xóa **chi phí lookup bên trong database**. Với 10.000 khách, một kế hoạch nested loop có thể thực hiện nhiều lần tra cứu index. Nếu truy vấn cần quét gần như toàn bộ bảng đơn, cách `ROW_NUMBER` hoặc `DISTINCT ON` có thể đáng so sánh.

### Khi bên trái rất lớn

Ví dụ một báo cáo chạy cho 2 triệu khách:

~~~sql
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (...) AS recent ON TRUE
~~~

Mỗi hàng khách có thể khiến một công việc phụ thuộc được kích hoạt theo plan. Vì vậy:

- Lọc tập khách thật sự cần trước khi chạy top-N.
- Dùng index hợp lý cho điều kiện tương quan.
- Tránh function tốn CPU hoặc truy cập bên ngoài cho hàng triệu lần gọi.
- Xem xét pre-aggregation, materialized view hoặc báo cáo batch nếu không cần dữ liệu tức thời.

**Một câu SQL duy nhất vẫn có thể rất tốn tài nguyên.** Chỉ giảm số round trip không bảo đảm toàn bộ truy vấn nhanh.

## 23. Điều kiện tương quan cần có trong subquery

Một sai lầm nghiêm trọng là quên:

~~~sql
WHERE o.customer_id = c.customer_id
~~~

Khi đó:

~~~sql
SELECT
    c.customer_id,
    latest.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE;
~~~

Subquery không còn tương quan và sẽ trả **đơn mới nhất toàn hệ thống** cho mọi khách. Việc có từ khóa `LATERAL` không tự thêm quan hệ `customer_id` cho bạn.

### Không nhầm điều kiện liên kết với điều kiện chọn top-N

Trong phần top-N, điều kiện liên kết **phải nằm trong subquery hoặc định nghĩa phụ thuộc tương ứng** để mỗi tập con được giới hạn theo đúng khách.

Sai ý nghĩa:

~~~sql
-- Lấy 2 đơn mới nhất toàn hệ thống rồi mới ghép khách:
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, customer_id
    FROM lateral_lab.orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS x ON x.customer_id = c.customer_id;
~~~

Truy vấn này không “lấy 2 đơn mới nhất của mỗi khách”: `LIMIT 2` đã áp dụng **toàn hệ thống** trước khi so `customer_id` ở `ON`.

Đúng ý định:

~~~sql
LEFT JOIN LATERAL (
    SELECT order_id, customer_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS x ON TRUE
~~~

## 24. Thứ tự JOIN và phạm vi tên

Các thành phần `FROM` có thể được nối bằng dấu phẩy hoặc các toán tử `JOIN`. **Thứ tự nhóm cây JOIN** ảnh hưởng phạm vi tên mà một `LATERAL` được phép nhìn. Đồng thời, `JOIN` tường minh có quy tắc kết hợp/ưu tiên khác cách liệt kê bằng dấu phẩy.

Để tránh lỗi khó đọc:

- Ưu tiên `JOIN ... ON ...` tường minh thay cho trộn nhiều dấu phẩy.
- Đặt item cung cấp dữ liệu **bên trái** item `LATERAL` sử dụng dữ liệu đó.
- Nếu cần tương quan tới cả hai bảng đã ghép, dùng `LATERAL` phía sau một cây JOIN đã xác định rõ.
- Dùng alias rõ và tránh tên cột không định danh khi có nhiều bảng.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    item_stat.lines
FROM lateral_lab.customers AS c
JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS lines
    FROM lateral_lab.order_items AS i
    WHERE i.order_id = o.order_id
) AS item_stat ON TRUE
ORDER BY c.customer_id, o.order_id;
~~~

Ở đây `item_stat` đọc được `o.order_id` vì `o` thuộc cây JOIN bên trái. Không cần tham chiếu `c.customer_id` nếu không dùng.

### Tránh SELECT *

Nếu viết:

~~~sql
SELECT *
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (...) AS x ON TRUE;
~~~

trong hệ thống lớn, output có thể có tên cột trùng và dễ bị phá vỡ khi schema thay đổi. Nên chọn cột cần thiết, đặt alias hiển thị rõ ràng, đặc biệt khi dùng kết quả trong Java DTO hoặc API.

## 25. LATERAL với LEFT JOIN: vấn đề NULL

Hãy xem:

~~~sql
SELECT
    c.customer_id,
    r.order_id,
    r.status
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS r ON TRUE
ORDER BY c.customer_id;
~~~

Với khách Dung, `r.order_id` và `r.status` đều `NULL`. Đừng coi:

~~~sql
r.status IS NULL
~~~

luôn đồng nghĩa “không có đơn”, nếu schema thật cho phép `status` null. Hãy kiểm tra một khóa xác định của hàng bên phải như `r.order_id IS NULL`, trong ví dụ `order_id` là `PRIMARY KEY` nên không null ở hàng thực sự.

### COALESCE trên giá trị hiển thị

~~~sql
COALESCE(r.status, 'no_orders') AS display_status
~~~

có thể tiện cho giao diện, nhưng nên tách **trạng thái nghiệp vụ của đơn** khỏi **trạng thái “khách không có đơn”**. Không nên nhập chuỗi `no_orders` vào cột `orders.status` nếu đây không phải trạng thái đơn được phép.

## 26. LATERAL và dữ liệu đã lọc trước ở phía trái

Giả sử dashboard chỉ cần khách đã đăng ký sau ngày 12/8:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
WHERE c.signup_date >= DATE '2026-08-12'
ORDER BY c.customer_id, recent.order_id;
~~~

Với dữ liệu mẫu, khách An (10/8) không có trong kết quả; Binh, Chi, Dung còn lại. Bộ tối ưu có thể áp dụng điều kiện trên `customers` trước khi cần xét phía `LATERAL`.

Khi tập bên trái là danh sách khách rất lớn và chỉ cần một phần nhỏ, việc **giới hạn đúng tập khách từ đầu** là một cơ hội quan trọng để giảm tổng công việc.

### Phân trang phía khách hàng

Nếu API trả 20 khách mỗi trang và mỗi khách 2 đơn mới nhất, nên xác định:

1. Thứ tự phân trang ổn định của khách (ví dụ `customer_id`).
2. Trang gồm 20 khách nào.
3. Sau đó mới ghép top 2 đơn **theo mỗi khách trong trang**.

Ví dụ:

~~~sql
WITH page_customers AS (
    SELECT customer_id, customer_name
    FROM lateral_lab.customers
    ORDER BY customer_id
    LIMIT 20
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id
FROM page_customers AS c
LEFT JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS r ON TRUE
ORDER BY c.customer_id, r.order_id DESC NULLS LAST;
~~~

Đặt `LIMIT 20` **ngoài cùng sau join** sẽ giới hạn **số hàng khách–đơn**, không nhất thiết tương đương 20 khách. Đây là lỗi phân trang rất phổ biến.

## 27. Những sai lầm thường gặp

### Sai lầm 1: Dùng FROM subquery tương quan nhưng quên LATERAL

Subquery trong `FROM` thường không nhìn được alias trước nó nếu không có `LATERAL`. Với correlated scalar subquery trong `SELECT` hoặc `EXISTS` thì cú pháp khác và không cần từ khóa này.

### Sai lầm 2: Dùng CROSS JOIN LATERAL khi muốn giữ nhóm rỗng

Nếu subquery trả không hàng, `CROSS JOIN LATERAL` làm mất hàng bên trái. Dùng `LEFT JOIN LATERAL ... ON TRUE` khi cần giữ khách chưa có đơn, hoặc giữ đơn có array rỗng.

### Sai lầm 3: Chuyển điều kiện chọn vào WHERE ngoài LEFT JOIN

`WHERE r.status = 'paid'` loại những hàng có `r.status` null và có thể làm mất nhóm rỗng. Nếu yêu cầu “đơn paid mới nhất”, lọc paid **trong subquery** trước `LIMIT`.

### Sai lầm 4: LIMIT ở ngoài cùng

`LIMIT 2` ở kết quả cuối chỉ lấy 2 hàng tổng, **không phải 2 hàng cho mỗi nhóm**. Với `LATERAL` top-N, giới hạn đặt ở truy vấn con tương quan.

### Sai lầm 5: ORDER BY không xác định thứ tự hoàn toàn

Nếu hai đơn cùng timestamp, chỉ `ORDER BY created_at DESC` có thể chọn khác nhau tùy dữ liệu/plan. Thêm khóa phụ ổn định như `order_id DESC`.

### Sai lầm 6: Nghĩ có LATERAL là tự có correlation

`LATERAL` chỉ cho phép tham chiếu, không tự viết điều kiện `WHERE o.customer_id = c.customer_id`. Quên điều kiện này có thể khiến mọi khách nhận đơn mới nhất của toàn hệ thống.

### Sai lầm 7: Chồng nhiều LATERAL tạo tích Descartes

Hai tập kết quả độc lập với 2 và 3 hàng có thể tạo 6 hàng cho mỗi đối tượng bên trái. Trước khi tính tổng/đếm, phải kiểm tra độ chi tiết dữ liệu.

### Sai lầm 8: SUM sau khi mở rộng JSONB tag

Nếu mỗi đơn có nhiều tag, `SUM(o.amount)` sau `jsonb_array_elements_text` có thể cộng giá trị tiền một lần cho **mỗi tag**. Tổng hợp ở mức đơn trước khi mở rộng hoặc xử lý dữ liệu sao cho mỗi đơn chỉ đóng góp một lần.

### Sai lầm 9: Cho rằng LATERAL chắc chắn nhanh hơn window function

Với ít khách và index tốt, `LIMIT` tương quan có thể hiệu quả. Với rất nhiều khách, số lookup có thể lớn. Dùng `EXPLAIN` và dữ liệu đại diện, không chọn theo cảm tính.

### Sai lầm 10: Bỏ qua NULL của scalar subquery và LEFT JOIN

Scalar subquery không trả hàng thì cho `NULL`; `LEFT JOIN LATERAL` không có kết quả cũng sinh cột phải null. Hãy kiểm tra `order_id` hoặc khóa đáng tin cậy để phân biệt không có hàng.

### Sai lầm 11: Dùng ROW_NUMBER FILTER

`ROW_NUMBER() FILTER (...)` không hợp lệ vì `FILTER` áp dụng cho aggregate, không phải mọi window function. Để đánh thứ tự riêng đơn paid, lọc trong CTE rồi dùng `ROW_NUMBER()`.

### Sai lầm 12: Trộn dấu phẩy và JOIN không để ý scope

Một item `LATERAL` chỉ tham chiếu những thành phần hợp lệ trong cây `FROM`. Dùng explicit join và alias rõ tránh lỗi không thấy cột hoặc ghép sai số hàng.

### Sai lầm 13: Tưởng một câu SQL thay thế N+1 là luôn rẻ

`LATERAL` giảm vòng gọi mạng, nhưng có thể vẫn tốn hàng nghìn lookup index hoặc chạy function đắt đỏ nhiều lần. Cần quan sát plan và giới hạn đúng tập bên trái.

## 28. Bài tập thực hành

Các bài tập sử dụng schema `lateral_lab` trong phần 4. Hãy dự đoán số hàng/trường hợp rỗng trước khi chạy.

### Bài 1. Đơn gần nhất theo từng khách

Viết `LEFT JOIN LATERAL` để trả mỗi khách **tối đa một đơn mới nhất**, gồm `order_id`, `status` và `amount`. Khách Dung phải xuất hiện.

### Bài 2. Hai đơn gần nhất

Viết `CROSS JOIN LATERAL` lấy tối đa hai đơn mới nhất của mỗi khách. Kết quả có bao nhiêu hàng? Khách nào không xuất hiện?

### Bài 3. Giữ khách chưa có đơn

Chuyển bài 2 sang `LEFT JOIN LATERAL`. Kết quả có bao nhiêu hàng? Những cột của phía đơn với khách Dung có giá trị gì?

### Bài 4. Đơn paid gần nhất

Viết `LEFT JOIN LATERAL` tìm đơn **paid** gần nhất cho từng khách. Với Binh, đơn nào được chọn và vì sao không phải đơn 202?

### Bài 5. Correlated scalar subquery

Không dùng `LATERAL`, viết một scalar subquery trong `SELECT` đếm đơn của mỗi khách. Nếu không có đơn, kết quả đếm là gì?

### Bài 6. EXISTS và NOT EXISTS

Viết hai truy vấn: (a) khách có ít nhất một đơn paid; (b) khách chưa có đơn nào. Vì sao `EXISTS` phù hợp khi chỉ cần câu trả lời có/không?

### Bài 7. Thống kê riêng cho mỗi khách

Dùng `LEFT JOIN LATERAL` với aggregate để trả `total_orders`, `paid_orders` và `paid_amount` cho mỗi khách. Tổng paid của An và Chi lần lượt là bao nhiêu?

### Bài 8. Tầng LATERAL thứ hai

Với mỗi khách, lấy đơn mới nhất rồi đếm số dòng `order_items` của đơn đó bằng một `LEFT JOIN LATERAL` thứ hai. Khách Dung nhận `item_lines` bằng bao nhiêu nếu dùng `COUNT(*)`?

### Bài 9. Tách tags JSONB

Viết truy vấn biến mỗi `tags` của đơn thành từng hàng bằng `jsonb_array_elements_text`. Dùng `WITH ORDINALITY` để giữ vị trí tag. Vì sao đơn 202 biến mất khi dùng `CROSS JOIN`?

### Bài 10. Giữ đơn không có tags

Chuyển bài 9 sang `LEFT JOIN LATERAL ... ON TRUE`. Đơn 202 có được giữ không, và `tag` có giá trị gì?

### Bài 11. LIMIT bên trong và bên ngoài

Hai truy vấn sau có cùng ý nghĩa không?

~~~sql
-- A
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT ...
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 2
) AS x
~~~

~~~sql
-- B
FROM lateral_lab.customers AS c
JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
LIMIT 2
~~~

Nếu không cùng nghĩa, giải thích cách sửa trường hợp B để có top 2 per customer.

### Bài 12. So sánh ROW_NUMBER

Viết truy vấn sử dụng `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC, order_id DESC)` để lấy hai đơn mới nhất của mỗi khách, rồi nối lại bảng khách hàng để giữ Dung.

### Bài 13. DISTINCT ON

Dùng `DISTINCT ON (customer_id)` lấy một đơn mới nhất của mỗi khách **đã có đơn**. Vì sao truy vấn này không tự trả khách Dung?

### Bài 14. Tính giá trị đơn khi có tags

Đơn 101 có amount = 120 và hai tags. Nếu mở rộng JSONB bằng `CROSS JOIN LATERAL` rồi `SUM(o.amount)`, đơn 101 đóng góp bao nhiêu? Hãy nêu cách tránh bị nhân đôi khi tính tổng tiền đơn.

### Bài 15. Index cho top-N

Một bảng `orders` có 20 triệu hàng. Truy vấn quan trọng nhất là “lấy ba đơn mới nhất của khách X”. Đề xuất B-tree index cho điều kiện `customer_id` và thứ tự `created_at DESC, order_id DESC`. Lý do sắp thứ tự cột?

### Bài 16. EXPLAIN

Một query `LEFT JOIN LATERAL ... LIMIT 2` có plan `Nested Loop Left Join` với inner `Index Scan` và `loops = 10000`. Điều đó gợi ý gì? Có thể khẳng định truy vấn chậm chỉ từ số vòng lặp không?

### Bài 17. Tách mảng SQL

Cho cột `sku_codes text[]`, viết `LEFT JOIN LATERAL unnest(sku_codes)` để hiển thị các SKU, nhưng vẫn giữ hàng có mảng rỗng.

### Bài 18. Tạo JSON top 2 cho API

Viết `LATERAL` trả một JSONB array các đơn mới nhất của mỗi khách, tối đa hai đơn, trả `[]` cho khách không có đơn. Vì sao cần một subquery giới hạn top 2 trước `jsonb_agg`?

### Bài 19. Lọc sai thời điểm

Giải thích sự khác nhau giữa:

~~~sql
LEFT JOIN LATERAL (
    SELECT *
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC
    LIMIT 1
) AS x ON TRUE
WHERE x.status = 'paid'
~~~

và:

~~~sql
LEFT JOIN LATERAL (
    SELECT *
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
    ORDER BY created_at DESC
    LIMIT 1
) AS x ON TRUE
~~~

### Bài 20. Chọn kỹ thuật

Với mỗi yêu cầu, chọn `EXISTS`, scalar subquery, `LATERAL`, `ROW_NUMBER` hoặc `DISTINCT ON` và giải thích: (a) khách có đơn hay không; (b) một mã đơn mới nhất; (c) ba đơn mới nhất của 20 khách được chọn; (d) thứ hạng của mọi đơn; (e) một đơn mới nhất cho mỗi khách đang có đơn.

## 29. Gợi ý lời giải

### Bài 1. Latest order với LEFT JOIN

~~~sql
SELECT
    c.customer_id, c.customer_name,
    latest.order_id, latest.status, latest.amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status, o.amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
~~~

Kết quả gồm 4 hàng, khách Dung có cột latest là null.

### Bài 2 và 3. Top 2

~~~sql
-- Bài 2: sáu hàng, không có Dung.
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS x
ORDER BY c.customer_id, x.order_id DESC;
~~~

~~~sql
-- Bài 3: bảy hàng, có Dung với order_id null.
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS x ON TRUE
ORDER BY c.customer_id, x.order_id DESC NULLS LAST;
~~~

### Bài 4. Latest paid

~~~sql
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS x ON TRUE
ORDER BY c.customer_id;
~~~

Binh nhận đơn 201; đơn 202 có trạng thái `cancelled` nên bị loại **trước khi chọn latest**.

### Bài 5. Correlated scalar count

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM lateral_lab.customers AS c
ORDER BY c.customer_id;
~~~

Kết quả 3, 2, 3, 0. `COUNT(*)` aggregate không có GROUP BY trả 0 khi tập lọc rỗng.

### Bài 6. EXISTS / NOT EXISTS

~~~sql
SELECT c.customer_name
FROM lateral_lab.customers AS c
WHERE EXISTS (
    SELECT 1 FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
~~~

~~~sql
SELECT c.customer_name
FROM lateral_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1 FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Kết quả lần lượt là An/Binh/Chi và Dung. Không cần mang nhiều hàng đơn lên kết quả để biết “có tồn tại” hay không.

### Bài 7. Aggregate per customer

~~~sql
SELECT
    c.customer_name,
    x.n_all,
    x.n_paid,
    x.paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS n_all,
        COUNT(*) FILTER (WHERE status = 'paid') AS n_paid,
        COALESCE(
            SUM(amount) FILTER (WHERE status = 'paid'),
            0::numeric
        ) AS paid_amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x ON TRUE
ORDER BY c.customer_id;
~~~

Tổng paid của An = `320` và Chi = `370`.

### Bài 8. Chuỗi LATERAL

~~~sql
SELECT c.customer_id, latest.order_id, stats.lines
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS lines
    FROM lateral_lab.order_items AS i
    WHERE i.order_id = latest.order_id
) AS stats ON TRUE
ORDER BY c.customer_id;
~~~

Dung có `lines = 0`.

### Bài 9 và 10. JSONB array

~~~sql
-- Bài 9: không có order 202 vì tags là mảng rỗng.
SELECT
    o.order_id, t.position, t.tag
FROM lateral_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.tags)
        WITH ORDINALITY AS t(tag, position)
ORDER BY o.order_id, t.position;
~~~

~~~sql
-- Bài 10: vẫn có order 202, tag/position là null.
SELECT
    o.order_id, t.position, t.tag
FROM lateral_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(o.tags)
        WITH ORDINALITY AS t(tag, position)
    ON TRUE
ORDER BY o.order_id, t.position NULLS LAST;
~~~

### Bài 11. Phạm vi LIMIT

A có `LIMIT 2` cho **mỗi khách**; B có `LIMIT 2` toàn kết quả. Để sửa, dùng `JOIN LATERAL (SELECT ... WHERE o.customer_id = c.customer_id ORDER BY ... LIMIT 2)` hoặc một giải pháp ranking theo khách phù hợp.

### Bài 12. ROW_NUMBER

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM lateral_lab.orders AS o
)
SELECT c.customer_id, r.order_id
FROM lateral_lab.customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn <= 2
ORDER BY c.customer_id, r.rn NULLS LAST;
~~~

### Bài 13. DISTINCT ON

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, created_at
FROM lateral_lab.orders
ORDER BY customer_id, created_at DESC, order_id DESC;
~~~

Dung không có hàng ở `orders` nên không xuất hiện. Cần `LEFT JOIN` trở lại `customers` nếu muốn đủ bốn khách.

### Bài 14. Nhân hàng khi mở rộng tag

Đơn 101 có hai tag, nên có thể đóng góp `120 + 120 = 240` nếu tính `SUM(o.amount)` **sau khi mở rộng**. Để tổng tiền đúng, tính aggregate ở cấp đơn trước, hoặc chỉ mở tag để hiển thị/điều kiện mà không nhân giá trị đơn.

### Bài 15. Index

~~~sql
CREATE INDEX idx_orders_customer_top3
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

`customer_id` giúp tìm nhóm khách, `created_at DESC` phục vụ thứ tự mới nhất, `order_id DESC` phá hòa. Đo plan thực tế để biết có phù hợp workload không.

### Bài 16. EXPLAIN

`loops = 10000` có thể cho thấy node bên trong được thực thi nhiều lần, chẳng hạn do 10.000 hàng khách phía ngoài. Nhưng không thể kết luận “chậm” chỉ từ loops; cần xem `actual time`, số hàng, buffers, độ chọn lọc và tổng thời gian.

### Bài 17. UNNEST

~~~sql
WITH stores(store_id, sku_codes) AS (
    VALUES
        (1, ARRAY['A','B']::text[]),
        (2, ARRAY[]::text[])
)
SELECT s.store_id, x.sku
FROM stores AS s
LEFT JOIN LATERAL unnest(s.sku_codes)
    AS x(sku) ON TRUE
ORDER BY s.store_id, x.sku;
~~~

Store 2 có `sku = NULL`.

### Bài 18. JSONB top 2

~~~sql
SELECT
    c.customer_id,
    COALESCE(x.orders_json, '[]'::jsonb) AS recent_orders
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object('order_id', r.order_id)
        ORDER BY r.created_at DESC, r.order_id DESC
    ) AS orders_json
    FROM (
        SELECT o.order_id, o.created_at
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 2
    ) AS r
) AS x ON TRUE
ORDER BY c.customer_id;
~~~

`LIMIT 2` chọn hai đơn **trước khi gom** vào array; `LIMIT` ngoài aggregate chỉ giới hạn số hàng kết quả aggregate.

### Bài 19. Lọc paid trước hay sau LIMIT

Truy vấn đầu chọn **đơn mới nhất bất kể trạng thái**, rồi loại khách nếu đơn mới nhất không paid. Truy vấn thứ hai chọn **đơn paid mới nhất**; khách không có đơn paid vẫn được giữ với cột phải null vì `LEFT JOIN`.

### Bài 20. Chọn giải pháp

| Yêu cầu | Gợi ý |
| --- | --- |
| (a) Có đơn hay không | `EXISTS` hoặc `NOT EXISTS` |
| (b) Một mã đơn mới nhất | Correlated scalar subquery với `ORDER BY ... LIMIT 1` |
| (c) Ba đơn mới nhất cho 20 khách đã chọn | `LEFT JOIN LATERAL ... LIMIT 3` sau khi chọn 20 khách |
| (d) Thứ hạng mọi đơn | `ROW_NUMBER() OVER (PARTITION BY ...)` |
| (e) Một đơn mới nhất trên mỗi khách có đơn | `DISTINCT ON (customer_id)` hoặc `LATERAL ... LIMIT 1` |

## 30. Checklist khi dùng LATERAL trong ứng dụng thực tế

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Item LATERAL có tham chiếu đúng alias bên trái? | Tránh lấy dữ liệu toàn hệ thống cho từng khách |
| Có dùng `CROSS` hay `LEFT` đúng ý nghĩa? | Quyết định giữ nhóm không có kết quả |
| Điều kiện chọn top-N có nằm trước `LIMIT`? | Tránh lấy sai “đơn paid mới nhất” |
| `ORDER BY` có khóa phá hòa? | Kết quả ổn định và có thể kiểm chứng |
| `LIMIT` đặt trong phạm vi nào? | Phân biệt top N mỗi nhóm với N hàng toàn bộ |
| Subquery trả 0, 1 hay nhiều hàng? | Dự đoán cardinality và NULL |
| Có nhiều LATERAL khiến kết quả nhân hàng? | Tránh đếm/tính tổng sai |
| Có cần giữ thứ tự JSON/array? | Dùng `WITH ORDINALITY` hoặc `ORDER BY` trong aggregate |
| Có index đúng điều kiện tương quan + thứ tự? | Giảm chi phí tìm top-N |
| Có quá nhiều hàng phía trái? | Hạn chế lookup/CPU/memory |
| `EXPLAIN` cho thấy loops và buffers thế nào? | Đo plan thực tế |
| Có kỹ thuật đơn giản hơn? | `EXISTS`, `GROUP BY`, scalar subquery, `ROW_NUMBER`, `DISTINCT ON` |

## 31. Bảng cú pháp tra cứu nhanh

| Mục đích | Mẫu SQL |
| --- | --- |
| Item tương quan trong FROM | `FROM t CROSS JOIN LATERAL (SELECT ... WHERE x = t.x) AS s` |
| Top 1 có thể thiếu | `LEFT JOIN LATERAL (SELECT ... ORDER BY ... LIMIT 1) AS x ON TRUE` |
| Top N và loại nhóm rỗng | `CROSS JOIN LATERAL (SELECT ... LIMIT N) AS x` |
| Giữ nhóm rỗng | `LEFT JOIN LATERAL (...) AS x ON TRUE` |
| Aggregate riêng từng hàng | `LEFT JOIN LATERAL (SELECT COUNT(*) ... WHERE key = t.key) AS x ON TRUE` |
| Hàm trả tập phụ thuộc từng hàng | `CROSS JOIN LATERAL unnest(t.arr) AS x(value)` |
| JSONB array thành dòng | `CROSS JOIN LATERAL jsonb_array_elements_text(t.tags) AS x(tag)` |
| Giữ vị trí phần tử | `... WITH ORDINALITY AS x(value, position)` |
| Kiểm tra sự tồn tại | `WHERE EXISTS (SELECT 1 ... WHERE key = t.key)` |
| Top N bằng window | `ROW_NUMBER() OVER (PARTITION BY key ORDER BY ...)` |
| Top 1 bằng PostgreSQL DISTINCT ON | `SELECT DISTINCT ON (key) ... ORDER BY key, ...` |
| Tìm top-N có index | `CREATE INDEX ... ON orders(key, created_at DESC, id DESC)` |
| Kiểm tra plan | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` |

## 32. Tổng kết

`LATERAL` cho phép một thành phần trong `FROM` **sử dụng giá trị của các hàng phía trước** để tạo ra tập kết quả tương ứng. Nó đặc biệt hữu ích khi subquery hoặc set-returning function phụ thuộc vào mỗi hàng, chẳng hạn **hai đơn mới nhất cho mỗi khách hàng**, **thống kê của đơn vừa chọn**, hoặc **mở rộng mảng JSONB thành nhiều dòng**.

Ba nguyên tắc cốt lõi:

1. **`CROSS JOIN LATERAL` loại hàng trái khi tập phải rỗng; `LEFT JOIN LATERAL ... ON TRUE` giữ hàng trái với các cột phải null.** Chọn đúng kiểu join là chọn đúng nghiệp vụ đối với nhóm không có dữ liệu.
2. **Đặt điều kiện tương quan, `ORDER BY` và `LIMIT` ở đúng phạm vi.** Với top-N-per-group, `LIMIT` phải giới hạn hàng **theo từng nhóm**, không phải sau khi toàn bộ kết quả đã được ghép.
3. **`LATERAL` không tự làm truy vấn nhanh hơn hoặc bảo vệ khỏi nhân hàng.** Hãy kiểm tra cardinality, index, `EXPLAIN` và so sánh với `EXISTS`, `GROUP BY`, `ROW_NUMBER` hay `DISTINCT ON` khi phù hợp.

Khi viết truy vấn PostgreSQL nâng cao, hãy bắt đầu bằng câu hỏi: **“Với mỗi hàng ở bên trái, tôi cần lấy bao nhiêu hàng hoặc giá trị nào ở bên phải?”**. Nếu phần bên phải cần tham chiếu trực tiếp tới hàng trái và trả một tập kết quả riêng cho hàng đó, `LATERAL` thường là cách diễn đạt SQL rõ ràng, mạnh mẽ và dễ mở rộng.
