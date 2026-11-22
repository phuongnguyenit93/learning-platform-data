# Truy vấn con vô hướng, dạng bảng và truy vấn tương quan trong PostgreSQL

Trong SQL, một câu `SELECT` không nhất thiết chỉ đứng ở đầu câu truy vấn. Nó còn có thể xuất hiện **bên trong một câu SQL khác** để tính một giá trị, tạo một tập dữ liệu trung gian hoặc kiểm tra sự tồn tại của những hàng liên quan.

Ví dụ, ứng dụng nhân sự có thể muốn tìm nhân viên có lương cao hơn **mức trung bình của chính phòng ban đó**. Hệ thống bán hàng có thể cần hiển thị **đơn hàng gần nhất của từng khách hàng**, kể cả khách hàng chưa mua hàng. Một báo cáo khác cần tìm **khách hàng không có đơn đã thanh toán**.

Các bài toán này đều có thể sử dụng *subquery* — **truy vấn con** — nhưng cách viết và kết quả phụ thuộc vào vị trí của truy vấn con và số hàng/cột mà nó trả về.

Ba khái niệm chính của bài học:

- **Truy vấn con vô hướng (*scalar subquery*)**: trả về tối đa **một hàng, một cột**, dùng như một biểu thức đơn trị. Nếu không có hàng thì giá trị là `NULL`; nếu trả hơn một hàng thì phát sinh lỗi.
- **Truy vấn con dạng bảng (*table subquery / derived table*)**: tạo một quan hệ tạm thời có thể gồm **nhiều hàng, nhiều cột**, thường xuất hiện trong `FROM` hoặc `JOIN`, có tên bí danh và có thể tham gia kết hợp dữ liệu như một bảng.
- **Truy vấn tương quan (*correlated subquery*)**: truy vấn con có **tham chiếu đến cột của truy vấn bên ngoài**. Nó có thể là truy vấn vô hướng, `EXISTS`, `NOT EXISTS` hoặc truy vấn dạng bảng dùng `LATERAL`.

Một điểm cần lưu ý: **“vô hướng”, “dạng bảng” và “tương quan” không phải ba nhóm loại trừ nhau**. “Vô hướng/dạng bảng” nói về **hình dạng kết quả và ngữ cảnh sử dụng**; “tương quan” nói về **phạm vi tham chiếu dữ liệu**. Một scalar subquery có thể tương quan hoặc không tương quan.

Bài học sử dụng PostgreSQL hiện đại, cung cấp schema thực hành, phân tích kết quả, bẫy thường gặp, các cách viết tương đương bằng `JOIN`/window function, cùng cách xem execution plan.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Chỉ ra đâu là truy vấn ngoài, đâu là truy vấn con; phân biệt kết quả vô hướng và kết quả dạng bảng.
2. Dùng scalar subquery trong `SELECT`, `WHERE` và các biểu thức tính toán khác.
3. Hiểu cách PostgreSQL xử lý scalar subquery trả **0, 1 hoặc nhiều hàng**.
4. Dùng một derived table trong `FROM`/`JOIN` để tổng hợp rồi kết hợp dữ liệu.
5. Viết correlated subquery đúng bằng bí danh của bảng trong và ngoài.
6. Dùng `EXISTS`, `NOT EXISTS`, `IN` và các phép so sánh với kết quả truy vấn con.
7. Dùng `JOIN LATERAL` và `LEFT JOIN LATERAL` cho bài toán chọn hàng gần nhất/top-N theo từng bản ghi.
8. Phân biệt `NULL`, “không có hàng”, aggregate và bẫy `NOT IN`.
9. So sánh subquery với `JOIN`, CTE và window function theo ngữ nghĩa và độ phức tạp.
10. Biết khi nào nên kiểm tra `EXPLAIN (ANALYZE, BUFFERS)` và cân nhắc index.
11. Thiết kế truy vấn an toàn, không để việc dùng subquery che giấu lỗi ràng buộc dữ liệu hoặc concurrency.

Tất cả lệnh tạo, xóa bảng và thay đổi dữ liệu trong bài **chỉ dùng trên database thực hành riêng**.

---

## 2. Bản đồ các kiểu truy vấn con

Một câu truy vấn con được phân loại theo **cách tiêu thụ kết quả**:

| Vị trí / dạng | Kết quả được sử dụng như | Ví dụ điển hình |
| --- | --- | --- |
| `SELECT (SELECT ...) AS value` | Một giá trị đơn | Mức lương trung bình của toàn công ty |
| `WHERE salary > (SELECT ...)` | Một giá trị để so sánh | Lương cao hơn trung bình |
| `FROM (SELECT ...) AS stats` | Một bảng trung gian | Tổng số đơn theo khách hàng |
| `JOIN (SELECT ...) AS stats ON ...` | Một bảng để join | Ghép customer với thống kê |
| `WHERE id IN (SELECT ...)` | Tập giá trị một cột | Khách hàng có đơn PAID |
| `WHERE EXISTS (SELECT ...)` | Kiểm tra có ít nhất một hàng | Khách hàng có đơn |
| `WHERE NOT EXISTS (SELECT ...)` | Kiểm tra không có hàng nào | Khách hàng chưa mua |
| `JOIN LATERAL (SELECT ... outer_column ...)` | Bảng con được phép tham chiếu bảng phía trước | Đơn gần nhất của từng khách hàng |

**Tương quan** là một chiều phân loại khác:

```text
                        TRUY VẤN CON
                             |
                 +-----------+-----------+
                 |                       |
           Theo kết quả            Theo tham chiếu
                 |                       |
          +------+-------+          +----+------+
          |              |          |           |
       Vô hướng       Dạng bảng  Độc lập     Tương quan
       0..1 x 1       0..N x M   với ngoài  dùng cột ngoài
          |              |          |           |
          +--------------+----------+-----------+
                 Có thể kết hợp các đặc tính
```

Ví dụ một scalar subquery tương quan:

```sql
SELECT e.employee_name,
       (
           SELECT AVG(e2.salary)
           FROM employees AS e2
           WHERE e2.department_id = e.department_id
       ) AS department_avg
FROM employees AS e;
```

Nó trả một giá trị trung bình cho mỗi nhân viên, đồng thời dùng `e.department_id` của truy vấn ngoài. Đây vừa là **scalar**, vừa là **correlated**.

---

## 3. Chuẩn bị bộ dữ liệu PostgreSQL thực hành

Chúng ta dùng hai nhóm bảng:

1. `departments` và `employees` cho mức lương, thống kê theo phòng và truy vấn tương quan.
2. `customers` và `orders` cho đơn hàng gần nhất, tổng hợp dạng bảng, `EXISTS`, `NOT EXISTS` và `LATERAL`.

Dữ liệu được thiết kế có **phòng ban không có nhân viên**, **nhân viên chưa thuộc phòng ban**, **khách hàng chưa có đơn** và **nhiều đơn cùng timestamp**, giúp quan sát các trường hợp biên.

> **Cảnh báo:** Khối `DROP TABLE IF EXISTS` dưới đây sẽ xóa bảng thực hành có cùng tên trong schema `subquery_lab`. Không chạy trên database sản xuất hoặc schema đang chứa dữ liệu cần giữ.

### 3.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS subquery_lab;

DROP TABLE IF EXISTS subquery_lab.orders;
DROP TABLE IF EXISTS subquery_lab.customers;
DROP TABLE IF EXISTS subquery_lab.employees;
DROP TABLE IF EXISTS subquery_lab.departments;

CREATE TABLE subquery_lab.departments (
    department_id INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL UNIQUE
);

CREATE TABLE subquery_lab.employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name TEXT NOT NULL,
    department_id INTEGER
        REFERENCES subquery_lab.departments(department_id),
    salary NUMERIC(12,2) NOT NULL CHECK (salary >= 0),
    joined_at DATE NOT NULL
);

CREATE TABLE subquery_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE subquery_lab.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES subquery_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL
);
```

Ở đây, `employees.department_id` **được phép NULL** để mô tả nhân viên chưa được phân phòng. Ngược lại, `orders.customer_id` là `NOT NULL` và có `FOREIGN KEY`, nên mỗi đơn hàng phải thuộc một khách hàng hợp lệ.

### 3.2. Nạp phòng ban và nhân viên

```sql
INSERT INTO subquery_lab.departments (
    department_id, department_name
)
VALUES
    (10, 'Kỹ thuật'),
    (20, 'Kinh doanh'),
    (30, 'Vận hành'),
    (40, 'Pháp chế');

INSERT INTO subquery_lab.employees (
    employee_id, employee_name, department_id, salary, joined_at
)
VALUES
    (1, 'An',   10,   3000.00, DATE '2026-01-10'),
    (2, 'Bình', 10,   4200.00, DATE '2026-01-11'),
    (3, 'Chi',  10,   4200.00, DATE '2026-02-02'),
    (4, 'Dũng', 20,   2500.00, DATE '2026-02-10'),
    (5, 'Hà',   20,   3500.00, DATE '2026-03-01'),
    (6, 'Lan',  30,   2800.00, DATE '2026-03-05'),
    (7, 'Mai',  NULL, 2600.00, DATE '2026-03-06'),
    (8, 'Nam',  30,   3200.00, DATE '2026-03-08');
```

Dữ liệu có cấu trúc:

| Phòng ban | Nhân viên | Lương | Trung bình phòng |
| --- | --- | ---: | ---: |
| 10 — Kỹ thuật | An | 3000 | 3800 |
| 10 — Kỹ thuật | Bình | 4200 | 3800 |
| 10 — Kỹ thuật | Chi | 4200 | 3800 |
| 20 — Kinh doanh | Dũng | 2500 | 3000 |
| 20 — Kinh doanh | Hà | 3500 | 3000 |
| 30 — Vận hành | Lan | 2800 | 3000 |
| 30 — Vận hành | Nam | 3200 | 3000 |
| Chưa phân phòng | Mai | 2600 | Chưa xác định |
| 40 — Pháp chế | Không có nhân viên | — | NULL |

Trung bình toàn bộ 8 nhân viên là **3250**.

### 3.3. Nạp khách hàng và đơn hàng

```sql
INSERT INTO subquery_lab.customers (
    customer_id, customer_name
)
VALUES
    (101, 'An Nhiên'),
    (102, 'Bảo Châu'),
    (103, 'Gia Hân'),
    (104, 'Minh Khoa'),
    (105, 'Quốc Nam');

INSERT INTO subquery_lab.orders (
    order_id, customer_id, status, amount, ordered_at
)
VALUES
    (1001, 101, 'PAID',      100.00, '2026-01-01 09:00:00+00'),
    (1002, 101, 'DRAFT',     150.00, '2026-02-15 08:00:00+00'),
    (1003, 102, 'PAID',      200.00, '2026-02-15 08:00:00+00'),
    (1004, 103, 'CANCELED',   50.00, '2026-03-01 10:00:00+00'),
    (1005, 103, 'PAID',       75.00, '2026-03-01 10:00:00+00'),
    (1006, 101, 'PAID',      175.00, '2026-04-03 12:00:00+00');
```

Đặc điểm:

- Khách hàng **101** có ba đơn, hai đơn PAID; tổng PAID = 275.
- Khách hàng **102** có một đơn PAID; tổng PAID = 200.
- Khách hàng **103** có hai đơn cùng thời điểm `ordered_at` nhưng khác `order_id`, chỉ một đơn PAID; tổng PAID = 75.
- Khách hàng **104** và **105** chưa có đơn.

Việc hai đơn của khách hàng 103 có cùng timestamp giúp minh họa **vì sao `ORDER BY ordered_at DESC LIMIT 1` chưa đủ để chọn một hàng xác định khi có tie**.

### 3.4. Kiểm tra sơ bộ

```sql
SELECT COUNT(*) AS departments_count
FROM subquery_lab.departments;

SELECT COUNT(*) AS employees_count
FROM subquery_lab.employees;

SELECT COUNT(*) AS customers_count
FROM subquery_lab.customers;

SELECT COUNT(*) AS orders_count
FROM subquery_lab.orders;
```

Kết quả tương ứng: **4, 8, 5, 6**.

Bạn có thể kiểm tra dữ liệu:

```sql
SELECT *
FROM subquery_lab.employees
ORDER BY employee_id;

SELECT *
FROM subquery_lab.orders
ORDER BY customer_id, ordered_at, order_id;
```

---

## 4. Truy vấn con vô hướng là gì?

**Scalar subquery** là một truy vấn con được sử dụng ở nơi SQL mong đợi **một giá trị đơn**.

Cú pháp thường gặp:

```sql
SELECT (
    SELECT expression
    FROM some_table
    WHERE ...
) AS one_value;
```

Các quy tắc trọng tâm:

1. Truy vấn con phải tạo ra **một cột** phù hợp với ngữ cảnh biểu thức vô hướng.
2. Nếu trả **đúng một hàng** → dùng giá trị trong hàng đó.
3. Nếu trả **không có hàng** → kết quả của scalar subquery là **NULL**.
4. Nếu trả **hơn một hàng** → PostgreSQL báo lỗi `more than one row returned by a subquery used as an expression`.
5. Giá trị một cột trong hàng duy nhất có thể tự nó là NULL; cần phân biệt với trường hợp không có hàng.

### 4.1. Scalar subquery không tương quan

Tìm mức lương cao nhất công ty:

```sql
SELECT (
    SELECT MAX(salary)
    FROM subquery_lab.employees
) AS company_max_salary;
```

Kết quả: **4200**.

Truy vấn con ở đây không dùng bất kỳ cột nào từ truy vấn ngoài; nó được gọi là **uncorrelated subquery**.

Bạn cũng có thể viết:

```sql
SELECT employee_id, employee_name, salary
FROM subquery_lab.employees
WHERE salary > (
    SELECT AVG(salary)
    FROM subquery_lab.employees
)
ORDER BY salary DESC, employee_id;
```

Giá trị trung bình toàn công ty là 3250; các nhân viên có lương lớn hơn mức này:

| ID | Nhân viên | Lương |
| ---: | --- | ---: |
| 2 | Bình | 4200 |
| 3 | Chi | 4200 |
| 5 | Hà | 3500 |

Nếu bảng thay đổi, kết quả có thể khác. Ví dụ này dựa trên dữ liệu lab ban đầu.

### 4.2. Đặt scalar subquery trong danh sách SELECT

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.salary,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
    ) AS company_avg_salary
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Ở đây, tất cả tám nhân viên đều có cột `company_avg_salary = 3250` trong kết quả. Truy vấn con không tương quan nên **về mặt ngữ nghĩa** nó cung cấp cùng một giá trị cho tất cả hàng ngoài.

Không nên kết luận PostgreSQL chắc chắn sẽ thực thi nó tám lần. Planner có thể nhận ra subquery độc lập và thực thi theo cơ chế tối ưu như `InitPlan`.

### 4.3. Không có hàng: scalar subquery trả NULL

```sql
SELECT (
    SELECT o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 104
) AS customer_104_order_amount;
```

Khách hàng 104 không có đơn nào, nên subquery trả **0 hàng** và kết quả vô hướng là **NULL**.

Đây không phải số 0. NULL ở đây có nghĩa **không lấy được một giá trị từ subquery**.

Nếu nghiệp vụ hiển thị “không có đơn thì tổng bằng 0”, có thể dùng:

```sql
SELECT COALESCE(
    (
        SELECT SUM(o.amount)
        FROM subquery_lab.orders AS o
        WHERE o.customer_id = 104
    ),
    0::NUMERIC
) AS customer_104_total;
```

Kết quả là 0 do **`COALESCE`**, không phải vì PostgreSQL tự coi không có đơn là tổng 0.

### 4.4. Có nhiều hàng: scalar subquery gây lỗi

Đây là ví dụ **cố ý sai**:

```sql
-- DỰ KIẾN LỖI: khách hàng 101 có ba đơn hàng.
SELECT (
    SELECT o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
) AS one_amount;
```

Subquery trả ba hàng, nhưng ngữ cảnh chỉ cho phép một giá trị. PostgreSQL từ chối thay vì tự chọn hàng đầu tiên.

Thông báo thường có dạng:

```text
ERROR: more than one row returned by a subquery used as an expression
```

Không nên giải quyết lỗi này bằng cách thêm `LIMIT 1` mà không hiểu ý nghĩa nghiệp vụ. Bạn phải trả lời: muốn tổng tiền, số lớn nhất, đơn gần nhất, một đơn theo khóa duy nhất hay danh sách tất cả đơn?

### 4.5. Chọn đúng một hàng bằng ORDER BY ... LIMIT 1

Nếu muốn số tiền của **đơn gần nhất** của khách hàng 101:

```sql
SELECT (
    SELECT o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS latest_order_amount;
```

Kết quả: **175.00** (đơn 1006).

Hai cột trong ORDER BY có ý nghĩa:

- `ordered_at DESC`: thời gian mới hơn đứng trước.
- `order_id DESC`: khi hai đơn có cùng timestamp, chọn ID lớn hơn theo quy tắc minh họa.

Nếu chỉ dùng `LIMIT 1` mà không có ORDER BY, PostgreSQL **không hứa hẹn sẽ chọn hàng nào**. Nếu chỉ ORDER BY timestamp mà tồn tại nhiều đơn bằng timestamp, kết quả vẫn có thể không xác định theo ý định.

### 4.6. Số cột cũng phải đúng

Ví dụ **cố ý sai trong ngữ cảnh vô hướng**:

```sql
-- DỰ KIẾN LỖI: scalar subquery không nhận hai cột riêng biệt.
SELECT (
    SELECT o.order_id, o.amount
    FROM subquery_lab.orders AS o
    WHERE o.order_id = 1001
);
```

Dù subquery chỉ trả một hàng, nó trả **hai cột**. Nếu muốn hai thuộc tính của cùng đơn, hãy dùng derived table/`JOIN LATERAL`, một cấu trúc composite được khai báo có chủ đích hoặc một biểu diễn JSON phù hợp, không cố đặt một bảng hai cột vào nơi cần một giá trị.

### 4.7. Aggregate giúp bảo đảm một giá trị

Thay vì chọn trực tiếp nhiều order:

```sql
SELECT (
    SELECT SUM(o.amount)
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
) AS total_order_amount;
```

Kết quả là **425.00** (100 + 150 + 175), bao gồm cả order DRAFT vì chưa có điều kiện status.

Nếu chỉ tính đơn PAID:

```sql
SELECT (
    SELECT SUM(o.amount)
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
      AND o.status = 'PAID'
) AS paid_total;
```

Kết quả **275.00**.

Các aggregate thông dụng như `SUM`, `AVG`, `MAX`, `MIN` và `COUNT` **không có GROUP BY** thường trả một hàng tổng hợp, kể cả khi tập đầu vào rỗng. Tuy nhiên, kết quả của nhiều aggregate trên tập rỗng là NULL, còn `COUNT(*)` là 0.

---

## 5. Scalar subquery với COUNT, SUM và NULL

Đây là điểm quan trọng khi làm báo cáo.

```sql
SELECT
    (
        SELECT COUNT(*)
        FROM subquery_lab.orders
        WHERE customer_id = 104
    ) AS order_count,

    (
        SELECT SUM(amount)
        FROM subquery_lab.orders
        WHERE customer_id = 104
    ) AS order_amount_sum,

    (
        SELECT AVG(amount)
        FROM subquery_lab.orders
        WHERE customer_id = 104
    ) AS order_amount_avg;
```

Với khách hàng 104 không có order:

| Biểu thức | Kết quả |
| --- | --- |
| `COUNT(*)` | 0 |
| `SUM(amount)` | NULL |
| `AVG(amount)` | NULL |

Lý do:

- `COUNT(*)` đếm số hàng, nên tập rỗng có số hàng bằng 0.
- `SUM` và `AVG` không có giá trị đầu vào để xác định số tiền trung bình/tổng theo quy tắc aggregate SQL, nên trả NULL.

Một số trường hợp có thể dùng:

```sql
COALESCE(SUM(amount), 0::NUMERIC)
```

để biểu diễn “không có đơn thì tổng doanh thu bằng 0”. Nhưng không nên tự biến mọi `AVG` NULL thành 0: trung bình của một tập không có quan sát không nhất thiết nên được diễn giải là 0.

### 5.1. Scalar subquery không có hàng khác với một hàng có NULL

So sánh:

```sql
-- Subquery không có hàng:
SELECT (
    SELECT amount
    FROM subquery_lab.orders
    WHERE order_id = -1
) AS a;

-- Aggregate trả một hàng, giá trị là NULL:
SELECT (
    SELECT AVG(amount)
    FROM subquery_lab.orders
    WHERE order_id = -1
) AS b;
```

Cả `a` và `b` đều có thể hiển thị NULL, nhưng nguyên nhân khác nhau:

- `a`: subquery không có hàng → scalar context trả NULL.
- `b`: aggregate tạo một hàng với giá trị AVG bằng NULL.

Nếu cần phân biệt hai trạng thái trong nghiệp vụ, phải truy vấn thêm số lượng hoặc trạng thái tồn tại, thay vì chỉ nhìn một ô NULL.

---

## 6. Truy vấn con tương quan là gì?

**Correlated subquery** tham chiếu tới ít nhất một cột từ query block bên ngoài.

Hãy xem:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
        WHERE e2.department_id = e.department_id
    ) AS department_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Các bí danh:

- `e`: nhân viên đang được xét bởi truy vấn ngoài.
- `e2`: nhân viên được truy vấn bên trong để tính trung bình.
- `e2.department_id = e.department_id`: điều kiện **tương quan** hai phạm vi.

Ý tưởng:

```text
Truy vấn ngoài: nhân viên e
        |
        +--> An   (department_id=10)
        |      |
        |      +--> Truy vấn con tìm lương phòng 10 -> AVG=3800
        |
        +--> Hà   (department_id=20)
        |      |
        |      +--> Truy vấn con tìm lương phòng 20 -> AVG=3000
        |
        +--> Mai  (department_id=NULL)
               |
               +--> e2.department_id = NULL không có hàng TRUE
                    -> AVG trên tập rỗng là NULL
```

Kết quả minh họa:

| ID | Nhân viên | Phòng | Lương | department_avg |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 10 | 3000 | 3800 |
| 2 | Bình | 10 | 4200 | 3800 |
| 3 | Chi | 10 | 4200 | 3800 |
| 4 | Dũng | 20 | 2500 | 3000 |
| 5 | Hà | 20 | 3500 | 3000 |
| 6 | Lan | 30 | 2800 | 3000 |
| 7 | Mai | NULL | 2600 | NULL |
| 8 | Nam | 30 | 3200 | 3000 |

### 6.1. Vì sao nhân viên Mai nhận department_avg NULL?

Điều kiện:

```sql
WHERE e2.department_id = e.department_id
```

nếu `e.department_id` là NULL sẽ trở thành:

```sql
e2.department_id = NULL
```

Với SQL, phép so sánh `= NULL` trả **UNKNOWN**, kể cả khi `e2.department_id` cũng NULL. Do đó không có hàng nào của subquery thỏa điều kiện WHERE; AVG là NULL.

Nếu nghiệp vụ muốn coi các nhân viên chưa phân phòng như một **nhóm NULL chung**, có thể dùng phép so sánh null-safe:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
        WHERE e2.department_id
              IS NOT DISTINCT FROM e.department_id
    ) AS department_or_unassigned_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Khi đó Mai được so sánh với các nhân viên có `department_id IS NULL`, nên nhận trung bình **2600** trong lab.

**Hai cách đều có thể đúng**, tùy định nghĩa “nhân viên cùng phòng”: nhóm chưa phân phòng có được coi là một nhóm chung hay không?

### 6.2. Dùng correlated scalar subquery trong WHERE

Yêu cầu:

> Tìm những nhân viên có lương **cao hơn trung bình phòng ban của chính họ**.

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
  AND e.salary > (
      SELECT AVG(e2.salary)
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
ORDER BY e.department_id, e.salary DESC, e.employee_id;
```

Kết quả:

| ID | Nhân viên | Phòng | Lương | TB phòng |
| ---: | --- | ---: | ---: | ---: |
| 2 | Bình | 10 | 4200 | 3800 |
| 3 | Chi | 10 | 4200 | 3800 |
| 5 | Hà | 20 | 3500 | 3000 |
| 8 | Nam | 30 | 3200 | 3000 |

Điểm khác với truy vấn ở mục 4.1: ở đó mỗi nhân viên được so với **một trung bình toàn công ty** bằng 3250. Ở đây mỗi người được so với **trung bình phòng riêng**.

### 6.3. Đừng quên điều kiện tương quan

Truy vấn sau **không tương quan**:

```sql
SELECT e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM subquery_lab.employees AS e2
);
```

Nó trả những nhân viên lương cao hơn **trung bình toàn công ty**, không phải cao hơn trung bình phòng. Nếu mục tiêu là nhóm phòng, thiếu điều kiện `e2.department_id = e.department_id` sẽ làm sai nghiệp vụ dù SQL hoàn toàn hợp lệ.

---

## 7. Bí danh và phạm vi tên cột: tránh một lỗi nguy hiểm

Trong subquery tương quan, cùng tên cột thường tồn tại ở nhiều query block. Hãy **ghi rõ bí danh bảng**.

Ví dụ đúng:

```sql
SELECT e.employee_id, e.department_id
FROM subquery_lab.employees AS e
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.departments AS d
    WHERE d.department_id = e.department_id
);
```

Ví dụ **sai về ý nghĩa**:

```sql
-- KHÔNG dùng để kiểm tra liên kết:
SELECT e.employee_id
FROM subquery_lab.employees AS e
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.departments AS d
    WHERE department_id = department_id
);
```

Hai vế `department_id` trong subquery có thể cùng được PostgreSQL phân giải tới **cột của bảng d bên trong**, không phải một vế của d và một vế của e. Điều kiện trở thành dạng tự so sánh và có thể TRUE cho hầu hết các hàng department, làm EXISTS luôn TRUE khi bảng departments không rỗng.

Không nên dựa vào quy tắc phân giải tên để đoán engine “tự hiểu một cột là bên ngoài”.

### 7.1. Khi tên cột không tồn tại ở query block trong

PostgreSQL cho phép tìm tên cột ở các phạm vi query ngoài khi không tìm thấy trong phạm vi trong. Điều đó đôi khi hữu ích, nhưng cũng khiến câu SQL **vô tình trở thành correlated subquery** nếu schema thay đổi hoặc đặt tên không rõ ràng.

Quy tắc làm việc:

- Đặt alias `e`, `e2`, `d`, `c`, `o` và dùng chúng trong điều kiện join.
- Phân biệt `outer_alias.column` và `inner_alias.column`.
- Không viết `WHERE id = id` rồi dựa vào suy đoán.
- Khi refactor subquery, kiểm tra lại alias và column resolution.
- Nếu truy vấn cần chạy qua nhiều tenant, nêu đầy đủ khóa tenant trong điều kiện.

---

## 8. Truy vấn con dạng bảng: derived table trong FROM

Khác scalar subquery, một **derived table** là kết quả của SELECT được đặt trong `FROM`, thường có nhiều hàng và nhiều cột:

```sql
SELECT result_alias.column_name
FROM (
    SELECT ...
) AS result_alias;
```

Tên `result_alias` giúp truy vấn ngoài tham chiếu các cột của kết quả trung gian.

Trong PostgreSQL hiện đại, một số phiên bản có thể cho phép lược bỏ alias đối với subquery trong FROM, nhưng **viết alias tường minh** là thói quen dễ đọc, tương thích tốt và tránh nhập nhằng.

### 8.1. Tổng hợp số nhân viên theo phòng rồi join

```sql
SELECT
    d.department_id,
    d.department_name,
    COALESCE(stats.employee_count, 0) AS employee_count,
    stats.avg_salary
FROM subquery_lab.departments AS d
LEFT JOIN (
    SELECT
        e.department_id,
        COUNT(*) AS employee_count,
        AVG(e.salary) AS avg_salary
    FROM subquery_lab.employees AS e
    WHERE e.department_id IS NOT NULL
    GROUP BY e.department_id
) AS stats
    ON stats.department_id = d.department_id
ORDER BY d.department_id;
```

Derived table `stats` có các cột:

```text
department_id | employee_count | avg_salary
--------------+----------------+-----------
10            | 3              | 3800
20            | 2              | 3000
30            | 2              | 3000
```

Nó **không có hàng cho phòng 40**, vì phòng 40 không có employee để GROUP BY. Truy vấn ngoài `LEFT JOIN` giữ phòng 40 và tạo NULL ở các cột stats.

Dùng `COALESCE(employee_count,0)` để hiển thị **0 nhân viên**. Không bắt buộc đổi `avg_salary` NULL thành 0, vì “mức lương trung bình của phòng trống” không có giá trị quan sát.

Kết quả cuối:

| Phòng | Tên | employee_count | avg_salary |
| ---: | --- | ---: | ---: |
| 10 | Kỹ thuật | 3 | 3800 |
| 20 | Kinh doanh | 2 | 3000 |
| 30 | Vận hành | 2 | 3000 |
| 40 | Pháp chế | 0 | NULL |

### 8.2. Derived table không tồn tại độc lập sau câu truy vấn

Kết quả `stats` là **quan hệ tạm trong phạm vi statement**. Nó không tự tạo một bảng vật lý có thể đọc ở statement kế tiếp.

Nếu bạn cần:

- **Chỉ dùng một lần trong một câu SQL**: derived table hoặc CTE có thể đủ.
- **Tái sử dụng nhiều lần trong một statement**: cân nhắc CTE.
- **Lưu và đọc qua nhiều statement**: có thể cần temporary table, materialized view hoặc bảng thật theo yêu cầu.

Không gọi derived table là “bảng đã được tạo và lưu” nếu không có DDL thực sự.

### 8.3. Có thể lọc, sắp xếp và join derived table

Ví dụ chỉ giữ phòng có trung bình trên 3100:

```sql
SELECT
    stats.department_id,
    stats.employee_count,
    stats.avg_salary
FROM (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS avg_salary
    FROM subquery_lab.employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
) AS stats
WHERE stats.avg_salary > 3100
ORDER BY stats.avg_salary DESC;
```

Kết quả chỉ phòng **10** (AVG=3800).

Điều kiện `WHERE stats.avg_salary > 3100` được áp dụng ở query block ngoài, vì lúc này `avg_salary` đã là một cột của derived table.

Nếu chỉ cần lọc group một lần, có thể viết trực tiếp bằng `HAVING`:

```sql
SELECT department_id, AVG(salary) AS avg_salary
FROM subquery_lab.employees
WHERE department_id IS NOT NULL
GROUP BY department_id
HAVING AVG(salary) > 3100;
```

Không phải mọi phép tổng hợp đều cần bọc thành subquery. Chọn cấu trúc làm logic dễ hiểu nhất.

### 8.4. Không nhầm thứ tự trong derived table với thứ tự kết quả cuối

Ví dụ:

```sql
SELECT *
FROM (
    SELECT employee_id, salary
    FROM subquery_lab.employees
    ORDER BY salary DESC
) AS x;
```

Nếu truy vấn ngoài cần một thứ tự bảo đảm, **vẫn phải có ORDER BY ở query block ngoài cùng**. Không mặc định thứ tự trong derived table được duy trì qua mọi bước join, filter hay tối ưu hóa.

Ngoại lệ thực dụng: `ORDER BY` bên trong subquery kết hợp `LIMIT`/`FETCH FIRST` có thể quyết định **những hàng được chọn** trước khi truy vấn ngoài xử lý, nhưng thứ tự **hiển thị cuối cùng** vẫn cần ORDER BY của SELECT ngoài.

---

## 9. Derived table cho báo cáo đơn hàng

Một báo cáo muốn hiển thị mỗi khách hàng kèm tổng số đơn và tổng doanh thu **chỉ của các đơn PAID**.

Dùng derived table:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    COALESCE(s.total_paid, 0::NUMERIC) AS total_paid
FROM subquery_lab.customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS total_paid
    FROM subquery_lab.orders AS o
    GROUP BY o.customer_id
) AS s
  ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Trong subquery:

- `COUNT(*)` đếm **mọi** đơn của khách hàng.
- `SUM(amount) FILTER (WHERE status='PAID')` chỉ tính tổng những đơn PAID.
- `GROUP BY customer_id` tạo một dòng thống kê trên mỗi khách hàng có ít nhất một order.

Kết quả:

| customer_id | Khách hàng | order_count | total_paid |
| ---: | --- | ---: | ---: |
| 101 | An Nhiên | 3 | 275 |
| 102 | Bảo Châu | 1 | 200 |
| 103 | Gia Hân | 2 | 75 |
| 104 | Minh Khoa | 0 | 0 |
| 105 | Quốc Nam | 0 | 0 |

### 9.1. Vì sao không đếm sau khi join thô một cách bất cẩn?

Nếu một báo cáo join `customers` với `orders` rồi lại join một bảng `order_items` có nhiều item cho mỗi order, mỗi order có thể xuất hiện **nhiều lần** trong kết quả join, khiến `COUNT(order_id)` và `SUM(order_amount)` bị nhân lên.

Một derived table tổng hợp ở **đúng mức hạt dữ liệu (grain)** trước khi join thường giúp kiểm soát vấn đề đó.

Ví dụ:

```text
customers        orders              order_items
    1  ------->  3 orders ----------> nhiều items / order

JOIN tất cả rồi SUM(order.amount):
    amount của mỗi order có thể bị lặp theo số item

GROUP orders theo customer trước:
    mỗi customer có 1 dòng tổng hợp
    -> LEFT JOIN customers không nhân tổng lên
```

Tuy nhiên, việc tổng hợp trước không tự làm mọi báo cáo đúng: nếu cần thống kê ở mức item, phải chọn grain và công thức phù hợp ngay từ đầu.

### 9.2. LEFT JOIN hay INNER JOIN?

Nếu đổi thành:

```sql
FROM subquery_lab.customers AS c
JOIN (...) AS s
  ON s.customer_id = c.customer_id
```

khách hàng 104 và 105 sẽ **biến mất** vì không có hàng thống kê tương ứng.

Dùng `LEFT JOIN` khi yêu cầu vẫn phải hiển thị khách hàng **chưa có đơn**, và dùng `INNER JOIN` khi chỉ muốn những khách hàng đã có thống kê.

---

## 10. CTE: cách đặt tên cho truy vấn con dạng bảng

Một **Common Table Expression** dùng `WITH` tạo một kết quả được đặt tên trong phạm vi câu SQL:

```sql
WITH order_stats AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(amount) FILTER (WHERE status = 'PAID') AS total_paid
    FROM subquery_lab.orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    COALESCE(s.total_paid, 0::NUMERIC) AS total_paid
FROM subquery_lab.customers AS c
LEFT JOIN order_stats AS s
  ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Về ý tưởng, đây là một cách viết khác cho derived table ở mục 9, nhưng phần định nghĩa được đưa lên đầu câu SQL và có tên `order_stats`.

Ưu điểm:

- Dễ chia truy vấn lớn thành những bước logic.
- Có thể tham chiếu CTE nhiều lần trong cùng statement khi phù hợp.
- Có thể dùng trong những truy vấn đệ quy với `WITH RECURSIVE` — một chủ đề riêng.

Không nên mặc định CTE **luôn được lưu thành bảng trung gian vật lý**. PostgreSQL hiện đại có thể **inline/fold** những CTE SELECT không có tác dụng phụ theo điều kiện tối ưu hóa, hoặc materialize tùy ngữ cảnh và số lần tham chiếu. Các tùy chọn `MATERIALIZED` / `NOT MATERIALIZED` ở phiên bản hỗ trợ có thể tác động lên kế hoạch.

**Dùng CTE để biểu diễn logic rõ**, rồi xem `EXPLAIN` nếu hiệu năng quan trọng. Đừng coi CTE là bảo đảm mặc định rằng một query block chỉ được tính đúng một lần.

---

## 11. Truy vấn con tương quan với EXISTS

`EXISTS (subquery)` kiểm tra **có ít nhất một hàng** được trả về hay không.

Ví dụ tìm khách hàng đã có ít nhất một đơn PAID:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM subquery_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả: **101, 102, 103**.

Đây là correlated subquery vì `o.customer_id = c.customer_id` tham chiếu `c` ở truy vấn ngoài.

### 11.1. EXISTS chỉ quan tâm có hàng hay không

```sql
SELECT
    EXISTS (SELECT NULL::INTEGER) AS has_null_valued_row,
    EXISTS (SELECT 1 WHERE FALSE) AS has_no_row;
```

Kết quả:

- `EXISTS(SELECT NULL)` là TRUE vì SELECT trả **một hàng**; giá trị bên trong hàng là NULL không quan trọng.
- `EXISTS(SELECT 1 WHERE FALSE)` là FALSE vì subquery **không trả hàng nào**.

Vì thế:

```sql
EXISTS (SELECT 1 FROM ...)
```

và:

```sql
EXISTS (SELECT * FROM ...)
```

thường cùng ý nghĩa. `SELECT 1` là quy ước cho thấy chỉ quan tâm sự tồn tại, không phải lời hứa luôn nhanh hơn `SELECT *`.

### 11.2. EXISTS giúp tránh nhân bản hàng bởi join

Nếu một khách hàng có ba order PAID, một `INNER JOIN` có thể tạo nhiều hàng cho cùng khách hàng:

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Khách hàng 101 có thể xuất hiện **hai lần** vì có hai đơn PAID. Nếu yêu cầu chỉ là “khách hàng nào có ít nhất một đơn PAID”, `EXISTS` trả **một dòng theo mỗi hàng customers** mà không cần dùng DISTINCT để xóa những hàng trùng do join tạo ra.

Một kỹ thuật có thể viết:

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Nhưng `EXISTS` mô tả đúng ý định kiểm tra sự tồn tại hơn trong trường hợp này.

---

## 12. NOT EXISTS: tìm phần thiếu bằng truy vấn tương quan

Yêu cầu:

> Tìm khách hàng **chưa từng có đơn hàng nào**.

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả: **104, 105**.

Yêu cầu khác:

> Tìm khách hàng **chưa có đơn PAID**, dù có thể có đơn DRAFT hoặc CANCELED.

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Với dữ liệu lab, kết quả cũng là **104, 105** vì tất cả khách hàng đã có đơn đều có ít nhất một đơn PAID. Nhưng nếu sau này thêm khách hàng chỉ có order DRAFT, họ sẽ **không thuộc** tập “chưa từng có đơn” nhưng sẽ **thuộc** tập “chưa có đơn PAID”.

Đây là ví dụ cho thấy **hai truy vấn có thể tình cờ cùng kết quả trên dữ liệu hiện tại nhưng khác nhau về ý nghĩa nghiệp vụ**.

### 12.1. Tìm “có đơn nhưng không có đơn PAID”

Mẫu tổng quát:

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS p
    WHERE p.customer_id = c.customer_id
      AND p.status = 'PAID'
)
ORDER BY c.customer_id;
```

Trong dữ liệu gốc, truy vấn trả **0 hàng** vì tất cả người có order đều có PAID. Đây là một kết quả hợp lệ, không phải lỗi.

Để thấy sự khác biệt, có thể thêm dữ liệu **tạm thời trong transaction lab**:

```sql
BEGIN;

INSERT INTO subquery_lab.orders (
    order_id, customer_id, status, amount, ordered_at
)
VALUES (
    1007, 104, 'DRAFT', 10.00, '2026-04-05 09:00:00+00'
);

SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS p
    WHERE p.customer_id = c.customer_id
      AND p.status = 'PAID'
)
ORDER BY c.customer_id;

ROLLBACK;
```

Trong transaction, kết quả tạm thời có **104**; sau `ROLLBACK`, dữ liệu trở về trạng thái ban đầu.

### 12.2. Không nhầm “không có PAID” với “có một order không PAID”

Câu:

```sql
SELECT DISTINCT c.customer_id
FROM subquery_lab.customers AS c
JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status <> 'PAID';
```

**không tương đương** với NOT EXISTS tìm người chưa có PAID. Nó tìm người có ít nhất một order không PAID; khách hàng 101 xuất hiện vì có order DRAFT 1002, **dù vẫn có hai order PAID**.

Quy tắc cần nhớ:

```text
Có ít nhất một order KHÔNG PAID
    EXISTS(order WHERE status <> 'PAID')

Không tồn tại order PAID
    NOT EXISTS(order WHERE status = 'PAID')
```

Hai mệnh đề khác nhau khi một khách hàng có nhiều order.

---

## 13. IN, NOT IN và bẫy NULL trong subquery

Khi subquery trả một cột, bạn có thể dùng nó như một **tập giá trị** trong `IN`:

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM subquery_lab.orders AS o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả: 101, 102, 103.

Tuy nhiên, `NOT IN` có quy tắc đặc biệt với `NULL`.

### 13.1. NULL bên phải có thể khiến NOT IN trả UNKNOWN

```sql
SELECT
    1 NOT IN (2, 3, NULL) AS not_in_with_null,
    2 NOT IN (2, 3, NULL) AS matched_value,
    1 NOT IN (2, 3) AS not_in_no_null;
```

| Biểu thức | Kết quả |
| --- | --- |
| `1 NOT IN (2,3,NULL)` | NULL (UNKNOWN) |
| `2 NOT IN (2,3,NULL)` | FALSE |
| `1 NOT IN (2,3)` | TRUE |

Vì `1 <> NULL` là UNKNOWN, PostgreSQL không thể kết luận 1 khác **mọi phần tử** của danh sách. Trong `WHERE`, UNKNOWN bị loại như FALSE.

Vì vậy, nếu subquery lấy khóa từ bảng có thể chứa NULL:

```sql
WHERE id NOT IN (SELECT nullable_id FROM some_table)
```

có thể cho **kết quả rỗng bất ngờ**. Với bài toán “không có hàng liên quan”, `NOT EXISTS` thường dễ đọc và an toàn hơn về ngữ nghĩa.

### 13.2. Cần xác định NULL ở cả hai phía

Nếu khóa của hàng ngoài có thể NULL, `NOT EXISTS` dùng toán tử `=` sẽ coi nó là **không có hàng khớp**, vì `NULL = NULL` trả UNKNOWN.

Nếu nghiệp vụ muốn coi hai NULL là tương đương khi tìm match, PostgreSQL hỗ trợ:

```sql
a IS NOT DISTINCT FROM b
```

Ví dụ:

```sql
SELECT
    NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER AS both_null,
    NULL::INTEGER IS DISTINCT FROM 10 AS null_vs_ten;
```

Hai cột trả TRUE.

Nhưng cần suy xét: **hai mã khách hàng chưa biết có thực sự đại diện cùng một khách hàng không?** Đa số bài toán khóa tham chiếu nên tách trường hợp NULL/thiếu dữ liệu, thay vì tự gộp hai NULL thành một đối tượng.

### 13.3. Tập bên phải rỗng

Một điểm dễ quên: nếu danh sách/subquery bên phải hoàn toàn **rỗng**, `NOT IN` trả TRUE cho mọi giá trị bên trái, kể cả NULL:

```sql
SELECT
    NULL::INTEGER NOT IN (
        SELECT x
        FROM (VALUES (1), (2)) AS t(x)
        WHERE FALSE
    ) AS null_not_in_empty;
```

Kết quả là TRUE. Không nên diễn đạt quá đơn giản rằng “NULL bên trái luôn làm NOT IN trả UNKNOWN” mà bỏ qua trường hợp tập rỗng.

---

## 14. So sánh với ANY và ALL

Ngoài `IN`, PostgreSQL cho phép so sánh một giá trị với kết quả subquery dùng `ANY`/`SOME` và `ALL`.

Cú pháp:

```sql
expression operator ANY (subquery)
expression operator ALL (subquery)
```

### 14.1. ANY: ít nhất một hàng thỏa

Ví dụ:

```sql
SELECT e.employee_id, e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > ANY (
    SELECT e2.salary
    FROM subquery_lab.employees AS e2
    WHERE e2.department_id = 10
)
ORDER BY e.salary DESC, e.employee_id;
```

Mệnh đề “salary lớn hơn **ít nhất một mức lương** của phòng 10” khác “salary lớn hơn mức lương cao nhất của phòng 10”.

Dữ liệu phòng 10 có lương 3000, 4200, 4200. Một nhân viên lương 3200 đã lớn hơn **3000**, nên thỏa `> ANY` dù chưa vượt mức tối đa 4200.

Có thể dùng `= ANY(array)` như cú pháp khác cho IN trên mảng; nhưng `ANY (SELECT ...)` nhận tập kết quả của subquery, còn `ANY(array)` nhận một biểu thức mảng. Cần phân biệt kiểu đối số và bind parameter.

### 14.2. ALL: thỏa với tất cả hàng

Tìm nhân viên có mức lương **không thấp hơn bất kỳ đồng nghiệp nào cùng phòng**:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
  AND e.salary >= ALL (
      SELECT e2.salary
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
ORDER BY e.department_id, e.employee_id;
```

Kết quả: **Bình (2), Chi (3), Hà (5), Nam (8)**.

Phòng 10 có hai người cùng mức cao nhất 4200, vì vậy cả hai đều được giữ. `>= ALL` có ngữ nghĩa “lớn hơn hoặc bằng tất cả”, không chọn một người duy nhất.

### 14.3. Tập rỗng trong ANY và ALL

Theo logic lượng từ:

- `condition ANY (tập rỗng)` là FALSE.
- `condition ALL (tập rỗng)` là TRUE.

Đây là lý do ví dụ trên có:

```sql
WHERE e.department_id IS NOT NULL
```

Nhân viên Mai có `department_id = NULL`; với điều kiện trong subquery `e2.department_id = NULL`, tập đồng nghiệp khớp rỗng, nên `salary >= ALL (tập rỗng)` sẽ là TRUE nếu không lọc Mai. Điều đó có thể tạo kết quả không đúng ý định “cao nhất trong một phòng ban đã xác định”.

Khi tập con có thể chứa `NULL`, `ANY`/`ALL` cũng chịu logic ba giá trị. Đừng tự thay một phép so sánh ALL bằng MIN/MAX mà không xét tập rỗng, NULL và quan hệ so sánh.

---

## 15. LATERAL: truy vấn dạng bảng có tham chiếu hàng phía trước

Một derived table thông thường trong `FROM` **không được tự do tham chiếu cột của những bảng khác cùng mức FROM** nếu không dùng cơ chế phù hợp. PostgreSQL cung cấp **`LATERAL`** để làm điều này.

Ý tưởng:

> Với từng hàng đã có ở bên trái của FROM/JOIN, cho phép subquery ở bên phải sử dụng cột của hàng đó để tạo ra **một bảng kết quả riêng**.

Ví dụ phổ biến nhất: **lấy đơn hàng gần nhất của từng khách hàng**.

### 15.1. LEFT JOIN LATERAL tìm đơn gần nhất

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.status,
    recent.amount,
    recent.ordered_at
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.status,
        o.amount,
        o.ordered_at
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
```

Giải nghĩa:

1. Truy vấn ngoài đang xét một hàng customers `c`.
2. Subquery trong LATERAL tham chiếu `c.customer_id`.
3. Chỉ lấy order của customer đó.
4. Sắp theo thời gian mới nhất, nếu trùng thời gian thì order_id lớn hơn đứng trước.
5. `LIMIT 1` trả nhiều nhất một order.
6. `LEFT JOIN ... ON TRUE` giữ khách hàng ngay cả khi subquery không trả order.

Kết quả:

| customer_id | Khách hàng | order_id gần nhất | status | amount |
| ---: | --- | ---: | --- | ---: |
| 101 | An Nhiên | 1006 | PAID | 175 |
| 102 | Bảo Châu | 1003 | PAID | 200 |
| 103 | Gia Hân | 1005 | PAID | 75 |
| 104 | Minh Khoa | NULL | NULL | NULL |
| 105 | Quốc Nam | NULL | NULL | NULL |

**Điểm quan trọng:** khách hàng 103 có hai order cùng `ordered_at`; `ORDER BY o.order_id DESC` giúp chọn order 1005 theo quy tắc minh họa. Nếu không có tiêu chí xử lý hòa điểm, “mới nhất” có thể không đủ để chọn chính xác một bản ghi.

### 15.2. LEFT JOIN LATERAL khác CROSS JOIN LATERAL

Nếu đổi thành:

```sql
SELECT c.customer_id, recent.order_id
FROM subquery_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent
ORDER BY c.customer_id;
```

chỉ còn khách hàng **101, 102, 103**, vì subquery trả **0 hàng** cho 104 và 105, nên họ không có cặp hàng nào được tạo trong CROSS JOIN.

Tóm tắt:

| Cách join | Nếu subquery LATERAL trả 0 hàng |
| --- | --- |
| `CROSS JOIN LATERAL` | Hàng phía trái bị loại khỏi kết quả |
| `JOIN LATERAL ... ON TRUE` | Tương tự inner join, hàng trái không còn |
| `LEFT JOIN LATERAL ... ON TRUE` | Hàng phía trái vẫn được giữ, cột phải là NULL |

Dùng `LEFT JOIN LATERAL` khi yêu cầu phải hiện cả khách hàng chưa có order.

### 15.3. Top-N theo từng khách hàng

LATERAL không chỉ để lấy một hàng. Lấy **hai đơn gần nhất của mỗi khách hàng**:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.ordered_at
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.ordered_at
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.ordered_at DESC NULLS LAST,
    recent.order_id DESC NULLS LAST;
```

Khách hàng 101 có tối đa hai order được trả; 102 có một; 103 có hai; 104 và 105 vẫn có một hàng với giá trị order NULL do LEFT JOIN.

### 15.4. Tại sao không dùng derived table thường?

Ví dụ ý tưởng **không hợp lệ khi thiếu LATERAL**:

```sql
-- Truy vấn con trong FROM cần LATERAL để tham chiếu c.customer_id.
SELECT c.customer_id, x.order_id
FROM subquery_lab.customers AS c
JOIN (
    SELECT o.order_id
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x ON TRUE;
```

Ở đây subquery trong FROM tham chiếu `c.customer_id` từ bảng khác ở cùng mức FROM. Cần thêm `LATERAL`:

```sql
SELECT c.customer_id, x.order_id
FROM subquery_lab.customers AS c
JOIN LATERAL (
    SELECT o.order_id
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x ON TRUE;
```

Trong PostgreSQL, một số hàm trả tập kết quả trong FROM có hành vi tham chiếu LATERAL theo quy tắc riêng và từ khóa LATERAL có thể tùy chọn; đối với **subquery SELECT trong FROM như ví dụ**, hãy viết `LATERAL` tường minh.

---

## 16. Scalar correlated subquery so với LEFT JOIN LATERAL

Giả sử chỉ muốn **số tiền** đơn gần nhất, scalar subquery cũng giải quyết được:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.amount
        FROM subquery_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.ordered_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_amount
FROM subquery_lab.customers AS c
ORDER BY c.customer_id;
```

Nhưng nếu muốn đồng thời `order_id`, `status`, `amount` và `ordered_at` của **cùng một order**, viết nhiều scalar subquery lặp lại cùng điều kiện sẽ khó bảo trì và có nguy cơ không nhất quán nếu mỗi subquery dùng tiêu chí chọn khác nhau.

Dùng `LEFT JOIN LATERAL` có lợi:

- Một query block xác định rõ “đơn gần nhất”.
- Trả nhiều cột của cùng hàng được chọn.
- Dễ mở rộng sang top-N thay vì chỉ một giá trị.
- Dễ kiểm tra `ORDER BY ... LIMIT ...` và điều kiện lọc.

Ví dụ:

```sql
SELECT
    c.customer_id,
    r.order_id,
    r.amount,
    r.status
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, amount, status
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS r ON TRUE
ORDER BY c.customer_id;
```

**Không có luật chung rằng LATERAL luôn nhanh hơn nhiều scalar subquery**. Hiệu năng còn tùy index, số lượng cột, kế hoạch, thống kê và dữ liệu. Về mặt trình bày logic “một hàng liên quan có nhiều thuộc tính”, LATERAL thường rõ ràng hơn.

---

## 17. Top-N và hàng có giá trị lớn nhất: lựa chọn cách viết

Một câu hỏi phổ biến:

> Tìm nhân viên lương cao nhất trong từng phòng.

Có hai ngữ nghĩa cần phân biệt:

1. **Tất cả những người cùng giữ mức lương cao nhất** (giữ tie).
2. **Chọn đúng một người đại diện cho mỗi phòng** (phải có tie-breaker).

### 17.1. Correlated scalar subquery dùng MAX: giữ tie

```sql
SELECT
    e.department_id,
    e.employee_id,
    e.employee_name,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
  AND e.salary = (
      SELECT MAX(e2.salary)
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
ORDER BY e.department_id, e.employee_id;
```

Kết quả:

| Phòng | ID | Nhân viên | Lương |
| ---: | ---: | --- | ---: |
| 10 | 2 | Bình | 4200 |
| 10 | 3 | Chi | 4200 |
| 20 | 5 | Hà | 3500 |
| 30 | 8 | Nam | 3200 |

Bình và Chi đều đạt MAX 4200, nên cả hai được giữ. Nhân viên Mai chưa phân phòng không được tính trong yêu cầu này.

### 17.2. Window function với RANK: cũng giữ tie

```sql
WITH ranked AS (
    SELECT
        e.department_id,
        e.employee_id,
        e.employee_name,
        e.salary,
        RANK() OVER (
            PARTITION BY e.department_id
            ORDER BY e.salary DESC
        ) AS salary_rank
    FROM subquery_lab.employees AS e
    WHERE e.department_id IS NOT NULL
)
SELECT
    department_id,
    employee_id,
    employee_name,
    salary
FROM ranked
WHERE salary_rank = 1
ORDER BY department_id, employee_id;
```

`RANK() = 1` giữ toàn bộ nhân viên cùng mức lương cao nhất. Đây là một cách thay correlated MAX bằng **window function**.

### 17.3. ROW_NUMBER: chọn đúng một người theo quy tắc

```sql
WITH numbered AS (
    SELECT
        e.department_id,
        e.employee_id,
        e.employee_name,
        e.salary,
        ROW_NUMBER() OVER (
            PARTITION BY e.department_id
            ORDER BY e.salary DESC, e.employee_id ASC
        ) AS rn
    FROM subquery_lab.employees AS e
    WHERE e.department_id IS NOT NULL
)
SELECT
    department_id,
    employee_id,
    employee_name,
    salary
FROM numbered
WHERE rn = 1
ORDER BY department_id;
```

Kết quả đúng **một người mỗi phòng**:

- Phòng 10: Bình (ID 2), vì hòa điểm 4200 và ID 2 nhỏ hơn ID 3.
- Phòng 20: Hà (ID 5).
- Phòng 30: Nam (ID 8).

Đây là một nghiệp vụ khác với “tất cả người giữ mức cao nhất”. Khi cần giữ tie, không thay `RANK` bằng `ROW_NUMBER` mà không đánh giá yêu cầu.

### 17.4. DISTINCT ON: lựa chọn đặc trưng của PostgreSQL

PostgreSQL hỗ trợ `DISTINCT ON` để lấy một hàng đầu tiên theo nhóm, dựa vào thứ tự:

```sql
SELECT DISTINCT ON (e.department_id)
    e.department_id,
    e.employee_id,
    e.employee_name,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
ORDER BY
    e.department_id,
    e.salary DESC,
    e.employee_id ASC;
```

Quy tắc:

- `DISTINCT ON (department_id)` giữ một hàng mỗi department.
- Các biểu thức DISTINCT ON phải khớp với phần đầu phù hợp của `ORDER BY`.
- `salary DESC, employee_id ASC` xác định hàng được chọn trong mỗi phòng.

Một số yêu cầu cần top-N (N > 1), lúc đó `ROW_NUMBER` hoặc `LATERAL ... LIMIT N` có thể tiện hơn.

### 17.5. Không suy diễn top-N từ MAX khi cần toàn bộ hàng

`SELECT MAX(salary) GROUP BY department_id` chỉ trả mức lương, **không tự trả danh tính nhân viên** có lương đó. Muốn có cả nhân viên, phải join lại, correlated query, window function hoặc LATERAL theo nhu cầu giữ tie và số lượng hàng.

---

## 18. Dùng subquery trong WHERE để so sánh theo nhóm

Ngoài “cao hơn trung bình cùng phòng”, có thể viết nhiều bộ lọc khác.

### 18.1. Nhân viên có lương bằng mức cao nhất của công ty

```sql
SELECT employee_id, employee_name, salary
FROM subquery_lab.employees
WHERE salary = (
    SELECT MAX(salary)
    FROM subquery_lab.employees
)
ORDER BY employee_id;
```

Kết quả: Bình và Chi (đều 4200).

### 18.2. Phòng có ít nhất hai nhân viên

Một correlated scalar subquery:

```sql
SELECT d.department_id, d.department_name
FROM subquery_lab.departments AS d
WHERE (
    SELECT COUNT(*)
    FROM subquery_lab.employees AS e
    WHERE e.department_id = d.department_id
) >= 2
ORDER BY d.department_id;
```

Kết quả: phòng **10, 20, 30**.

Một cách khác bằng aggregate và HAVING:

```sql
SELECT d.department_id, d.department_name
FROM subquery_lab.departments AS d
JOIN subquery_lab.employees AS e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(*) >= 2
ORDER BY d.department_id;
```

Hai cách cùng ý nghĩa cho dữ liệu lab. Cách thứ hai có thể phù hợp nếu bạn đã cần tổng hợp nhiều chỉ số; cách thứ nhất biểu đạt trực tiếp “mỗi phòng có bao nhiêu nhân viên”.

### 18.3. Phòng chưa có nhân viên

```sql
SELECT d.department_id, d.department_name
FROM subquery_lab.departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.employees AS e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
```

Kết quả chỉ phòng **40 — Pháp chế**.

Cách dùng scalar COUNT cũng có thể được viết:

```sql
WHERE (
    SELECT COUNT(*)
    FROM subquery_lab.employees AS e
    WHERE e.department_id = d.department_id
) = 0
```

Nhưng `NOT EXISTS` thường truyền tải trực tiếp hơn câu hỏi “không có hàng khớp”. PostgreSQL còn có thể tối ưu nó thành **anti-join**.

---

## 19. Subquery trong SELECT và yêu cầu đặt tên cột

Khi SELECT một expression/subquery, hãy đặt alias để kết quả có tên dễ dùng ở ứng dụng:

```sql
SELECT
    d.department_id,
    d.department_name,
    (
        SELECT COUNT(*)
        FROM subquery_lab.employees AS e
        WHERE e.department_id = d.department_id
    ) AS employee_count
FROM subquery_lab.departments AS d;
```

Nếu không có `AS employee_count`, driver hoặc công cụ SQL có thể trả tên cột không thuận tiện cho code.

Tuy nhiên, một alias đặt trong danh sách SELECT **không tự sẵn có trong mọi phần của cùng query block**. Ví dụ không nên mặc định dùng:

```sql
SELECT
    (
        SELECT COUNT(*)
        FROM subquery_lab.employees
    ) AS employee_count
WHERE employee_count > 0;
```

Cú pháp/khả năng tham chiếu alias ở những clause khác nhau có quy tắc riêng; `WHERE` không thể dùng alias SELECT theo cách này.

Nếu cần lọc theo kết quả đã tính, đặt subquery trong derived table hoặc CTE:

```sql
SELECT q.department_id, q.employee_count
FROM (
    SELECT
        d.department_id,
        (
            SELECT COUNT(*)
            FROM subquery_lab.employees AS e
            WHERE e.department_id = d.department_id
        ) AS employee_count
    FROM subquery_lab.departments AS d
) AS q
WHERE q.employee_count > 0
ORDER BY q.department_id;
```

Kết quả: phòng 10, 20, 30.

### 19.1. Không dùng SELECT * tùy tiện trong derived table lớn

`SELECT *` thuận tiện khi học, nhưng trong truy vấn kết hợp dữ liệu phức tạp nó có thể:

- Lấy cột không cần thiết.
- Tạo tên cột trùng giữa các bảng.
- Khi schema thay đổi, làm kết quả API thay đổi ngoài ý muốn.
- Tăng lượng dữ liệu truyền tải.
- Làm khó phân biệt grain của dữ liệu trung gian.

Với báo cáo dùng nhiều derived table, nên liệt kê những cột thật sự cần thiết và đặt alias rõ nghĩa.

---

## 20. Truy vấn con với khóa ghép và nhiều tenant

Một điều kiện tương quan thường cần **nhiều hơn một cột**.

Giả sử ứng dụng có nhiều tenant, và mỗi tenant dùng `external_id` bắt đầu từ 1. Nếu tìm đơn hàng theo `external_id` mà không so thêm `tenant_id`, subquery có thể lấy **dữ liệu của tenant khác**.

Mẫu đúng về ý tưởng:

```sql
SELECT a.tenant_id, a.external_id
FROM tenant_source AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM tenant_target AS b
    WHERE b.tenant_id = a.tenant_id
      AND b.external_id = a.external_id
);
```

Hai bảng này chỉ là **mẫu schema minh họa**, không thuộc lab đã tạo. Trong hệ thống thật, cần kết hợp điều kiện tenant với quyền truy cập và Row-Level Security nếu có, không xem việc đặt điều kiện SQL đúng là biện pháp bảo mật duy nhất.

### 20.1. Cẩn thận với NULL trong khóa ghép

Với điều kiện:

```sql
b.external_id = a.external_id
```

nếu một trong hai cột là NULL, phép so sánh không TRUE.

Nếu nghiệp vụ thực sự muốn coi hai NULL là tương đương, dùng:

```sql
b.external_id IS NOT DISTINCT FROM a.external_id
```

Nhưng **hai ID chưa xác định không nhất thiết là cùng một đối tượng**. Trong nhiều bài toán, bạn nên cấm NULL ở các thành phần khóa nghiệp vụ và phân loại riêng những hàng đầu vào bị thiếu mã.

### 20.2. Truy vấn con không thay unique/foreign key

Một câu `NOT EXISTS` kiểm tra “chưa có hàng tương ứng” là **một phép đọc theo snapshot**, không bảo đảm transaction khác không chèn hàng tương ứng ngay sau đó.

Nếu một cặp `(tenant_id, external_id)` phải là duy nhất, cần `UNIQUE`/`PRIMARY KEY` phù hợp để bảo vệ dưới concurrency. Nếu giá trị phải tham chiếu một đối tượng có thật, dùng `FOREIGN KEY` theo mô hình.

---

## 21. Truy vấn con trong thao tác UPDATE/DELETE: cần thận trọng

Subquery không chỉ có trong SELECT. Nó còn có thể dùng để xác định những hàng của UPDATE hoặc DELETE.

Ví dụ: tăng lương **5%** cho những người có lương dưới trung bình phòng, với điều kiện thuộc phòng đã xác định.

> **Chỉ chạy trên database lab.** Để không thay đổi dữ liệu cho các ví dụ sau, bao toàn bộ thao tác trong transaction và dùng `ROLLBACK`.

```sql
BEGIN;

UPDATE subquery_lab.employees AS e
SET salary = ROUND(e.salary * 1.05, 2)
WHERE e.department_id IS NOT NULL
  AND e.salary < (
      SELECT AVG(e2.salary)
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
RETURNING
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary;

ROLLBACK;
```

Ở dữ liệu ban đầu, người có lương dưới trung bình phòng là An, Dũng và Lan; họ có thể được cập nhật trong transaction lab rồi hoàn tác.

**Lưu ý về snapshot và thay đổi dữ liệu:** trong các DML phức tạp, các phép đọc thuộc cùng statement và tác động ghi có quy tắc MVCC riêng. Không nên suy luận máy móc rằng PostgreSQL sẽ lần lượt cập nhật một nhân viên rồi dùng lương mới đó để tính trung bình của người kế tiếp. Để thực hiện một quy trình tính lương thực tế, cần thiết kế nguồn dữ liệu, snapshot, transaction và cách đối soát rõ ràng.

### 21.1. DELETE bằng NOT EXISTS

Một ví dụ tổng quát:

```sql
-- CHỈ MINH HỌA: cần xác định rõ phạm vi dữ liệu trước khi DELETE.
DELETE FROM some_staging_table AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM master_table AS m
    WHERE m.business_key = s.business_key
);
```

Trong production, lệnh DELETE là thao tác phá hủy dữ liệu và có thể bị ảnh hưởng bởi concurrency, khóa ngoại và các quy trình khác. Hãy chạy SELECT kiểm tra tập hàng cần tác động, có backup/kế hoạch phục hồi và thực hiện theo quyền được phép.

Truy vấn con dùng trong DML không phải lý do để bỏ qua ràng buộc dữ liệu hay bước review phạm vi thay đổi.

---

## 22. Hiệu năng: correlated subquery có luôn chạy N lần không?

Một mô tả thường gặp là:

> Với mỗi hàng ngoài, PostgreSQL chạy subquery một lần.

Đó là **mô hình tư duy hữu ích**, nhất là khi điều kiện tương quan phụ thuộc vào hàng ngoài. Tuy nhiên, PostgreSQL là một bộ tối ưu truy vấn; **kế hoạch thực thi thực tế không nhất thiết là một vòng lặp literal như mô tả**.

Tùy cấu trúc, planner có thể:

- Chạy subquery độc lập thành `InitPlan` và dùng kết quả.
- Tạo `SubPlan` có tham số và thực thi lặp theo các hàng ngoài.
- Chuyển `EXISTS` thành **Semi Join**.
- Chuyển `NOT EXISTS` thành **Anti Join**.
- Dùng **Hash Join**, **Merge Join** hoặc **Nested Loop**.
- Sử dụng index để tìm hàng khớp nhanh hơn.
- Đẩy một số điều kiện xuống bảng con, gộp query block hoặc materialize theo cách phù hợp.

Do đó không thể kết luận “correlated subquery luôn chậm hơn JOIN” chỉ dựa trên cú pháp.

### 22.1. Xem kế hoạch bằng EXPLAIN

```sql
EXPLAIN
SELECT e.employee_id, e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM subquery_lab.employees AS e2
    WHERE e2.department_id = e.department_id
);
```

Để có số liệu thực thi trên câu **SELECT**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.employee_id, e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM subquery_lab.employees AS e2
    WHERE e2.department_id = e.department_id
);
```

`EXPLAIN ANALYZE` **thực sự thực thi câu lệnh**. Với INSERT/UPDATE/DELETE, đừng dùng nó trực tiếp trên production chỉ để xem plan vì có thể thay đổi dữ liệu. Trong lab, ví dụ dùng SELECT đọc dữ liệu.

### 22.2. Những chi tiết cần đọc trong plan

| Thành phần | Ý nghĩa khi quan sát |
| --- | --- |
| `SubPlan` | Một subquery được thực thi theo cơ chế subplan |
| `InitPlan` | Subquery độc lập có thể được thực hiện để tạo tham số ban đầu |
| `Nested Loop` | Một dạng kết hợp theo vòng lặp giữa nguồn ngoài/trong |
| `Hash Join / Hash Anti Join` | Kết hợp hoặc kiểm tra không khớp bằng cấu trúc hash |
| `Semi Join` | Chỉ cần biết tồn tại match, không nhân bản hàng A |
| `Aggregate / HashAggregate` | Tính tổng hợp, có thể ở subquery hoặc sau join |
| `WindowAgg` | Thực thi window functions |
| `Limit` | Chọn tối đa số hàng yêu cầu, thường kết hợp Sort/Index |
| `loops` | Số lần node được thực thi theo instrument của EXPLAIN ANALYZE |
| `actual rows` | Số hàng thực tế node xử lý/trả về theo cách thống kê |
| `Buffers` | Hoạt động bộ đệm liên quan, hữu ích khi tìm nguyên nhân I/O |

Một plan còn cần hiểu kết hợp với thống kê, cấu trúc index, tính chọn lọc và kích thước dữ liệu. Không suy luận từ duy nhất một node hoặc một benchmark bảng vài hàng.

### 22.3. Index cho điều kiện tương quan

Ví dụ những truy vấn thường dùng:

```sql
WHERE o.customer_id = c.customer_id
```

và:

```sql
WHERE e2.department_id = e.department_id
```

có thể được hỗ trợ bằng index:

```sql
CREATE INDEX idx_orders_customer_id
ON subquery_lab.orders (customer_id);

CREATE INDEX idx_employees_department_id
ON subquery_lab.employees (department_id);
```

Với LATERAL tìm order gần nhất:

```sql
CREATE INDEX idx_orders_customer_latest
ON subquery_lab.orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

Index này có thể giúp PostgreSQL tìm các order của một customer theo thứ tự mong muốn, rồi dừng sau `LIMIT 1` mà không cần sort toàn bộ mỗi lần, tùy kế hoạch.

Với truy vấn “không có order PAID”:

```sql
CREATE INDEX idx_orders_paid_customer
ON subquery_lab.orders (customer_id)
WHERE status = 'PAID';
```

Đây là **partial index**, có thể hiệu quả nếu truy vấn thường chỉ xét status PAID và dữ liệu phân bố phù hợp.

Không cần tạo tất cả index này trong một hệ thống thật: index tăng chi phí lưu trữ, INSERT/UPDATE/DELETE và bảo trì. Chọn theo workload và xem `EXPLAIN`.

### 22.4. Tại sao index không được dùng trong lab?

Bộ dữ liệu chỉ có 8 nhân viên và 6 đơn. Sequential scan có thể rẻ hơn index scan. Nếu `EXPLAIN` chọn scan toàn bảng, điều đó **không chứng minh index không có tác dụng** với dữ liệu lớn hơn.

### 22.5. Không dùng LIMIT 1 để “chữa” một subquery sai logic

Một subquery vô hướng trả nhiều hàng là tín hiệu:

- Bạn chưa xác định khóa duy nhất.
- Có dữ liệu trùng ngoài dự kiến.
- Bạn thực sự cần một aggregate.
- Bạn thực sự cần danh sách hàng, không phải một giá trị.

Thêm `LIMIT 1` khiến câu SQL không báo lỗi nữa nhưng có thể **che giấu sai dữ liệu** hoặc chọn một bản ghi tùy ý. Chỉ dùng LIMIT khi nghiệp vụ xác định rõ một cách chọn và có ORDER BY đủ tiêu chí.

---

## 23. So sánh subquery, JOIN, window function và CTE

Xét yêu cầu **mỗi nhân viên kèm mức lương trung bình phòng**.

### 23.1. Correlated scalar subquery

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
        WHERE e2.department_id = e.department_id
    ) AS department_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Ưu điểm: gần với cách diễn đạt “với mỗi nhân viên, tính trung bình của phòng đó”. Nhược điểm có thể là nhiều lần thực hiện công việc tương tự nếu planner không tối ưu thành cách chung.

### 23.2. JOIN với derived table tổng hợp

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    s.department_avg
FROM subquery_lab.employees AS e
LEFT JOIN (
    SELECT
        department_id,
        AVG(salary) AS department_avg
    FROM subquery_lab.employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
) AS s
  ON s.department_id = e.department_id
ORDER BY e.employee_id;
```

Ưu điểm: tính thống kê **theo nhóm** rồi join một lần theo logic quan hệ. Đây thường là lựa chọn dễ đánh giá trên bảng lớn nếu cần nhiều thống kê của cùng phòng.

### 23.3. Window function

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    CASE
        WHEN e.department_id IS NOT NULL
            THEN AVG(e.salary) OVER (
                PARTITION BY e.department_id
            )
        ELSE NULL
    END AS department_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Ở đây window function tính trung bình theo nhóm **mà vẫn giữ mỗi hàng nhân viên**.

Lưu ý: `PARTITION BY department_id` xem những hàng có department_id NULL như một partition. Để giữ **đúng ngữ nghĩa** của subquery dùng toán tử `=` ở mục trước (Mai có department_avg NULL), ví dụ dùng `CASE WHEN e.department_id IS NOT NULL THEN ... ELSE NULL END`.

Nếu nghiệp vụ coi mọi nhân viên chưa phân phòng thành một nhóm, có thể bỏ CASE đó, nhưng lúc này **ngữ nghĩa khác**.

### 23.4. Chọn theo ý nghĩa và workload

| Mục tiêu | Cách thường đáng cân nhắc |
| --- | --- |
| Một giá trị thống kê chung cho tất cả hàng | Uncorrelated scalar subquery hoặc CTE |
| Một giá trị thống kê riêng theo hàng ngoài | Correlated scalar subquery |
| Nhiều chỉ số tổng hợp theo nhóm rồi join | Derived table / CTE + JOIN |
| Giữ mọi hàng và tính chỉ số theo partition | Window function |
| Chỉ cần kiểm tra có hàng liên quan | EXISTS |
| Chỉ cần kiểm tra không có hàng liên quan | NOT EXISTS |
| Một hoặc top-N hàng liên quan cho mỗi hàng ngoài | LATERAL với ORDER BY/LIMIT |
| Một hàng đại diện cho mỗi nhóm PostgreSQL | DISTINCT ON hoặc ROW_NUMBER |
| Cần giữ tất cả hàng đồng hạng | Correlated MAX / RANK / DENSE_RANK |
| Dữ liệu lớn và truy vấn chậm | So sánh EXPLAIN, index, thống kê, tính chọn lọc |

**Không có một cú pháp luôn vượt trội**. Chọn bản diễn đạt đúng và dễ đọc trước; tối ưu dựa trên bằng chứng thực thi.

---

## 24. Những lỗi ngữ nghĩa thường gặp

### 24.1. Quên GROUP BY rồi nhận sai aggregate

```sql
SELECT AVG(salary)
FROM subquery_lab.employees;
```

trả trung bình toàn công ty.

Nếu yêu cầu theo phòng, phải có `GROUP BY department_id` hoặc điều kiện tương quan tới đúng phòng. Không nhầm hai bài toán.

### 24.2. So sánh với subquery có nhiều hàng

```sql
-- Sai khi subquery có nhiều mức lương:
WHERE salary = (
    SELECT salary
    FROM subquery_lab.employees
    WHERE department_id = 10
)
```

Nếu muốn “bằng **bất kỳ** mức lương nào của phòng 10”, dùng:

```sql
WHERE salary IN (
    SELECT salary
    FROM subquery_lab.employees
    WHERE department_id = 10
)
```

Nếu muốn “bằng **mức lương cao nhất** của phòng 10”, dùng:

```sql
WHERE salary = (
    SELECT MAX(salary)
    FROM subquery_lab.employees
    WHERE department_id = 10
)
```

Hai câu trả lời là **hai yêu cầu khác nhau**.

### 24.3. Quên alias ngoài và trong

```sql
WHERE department_id = department_id
```

có thể chỉ so cùng một cột ở cùng query block. Viết rõ:

```sql
WHERE inner_e.department_id = outer_e.department_id
```

### 24.4. Quên kiểm tra tính duy nhất trước scalar

Một subquery chỉ có một cột không có nghĩa chỉ có một hàng. Nếu subquery trả nhiều order, scalar context sẽ lỗi. Chọn aggregate, điều kiện khóa duy nhất hoặc cấu trúc dạng bảng.

### 24.5. COALESCE quá sớm

Nếu `AVG(salary)` của phòng không có người trả NULL, biến nó thành 0 có thể làm báo cáo hiểu nhầm phòng có **lương bình quân bằng 0**. Dùng `COALESCE` khi nghiệp vụ xác định 0 là giá trị trình bày phù hợp.

### 24.6. ORDER BY thiếu tie-breaker

`ORDER BY ordered_at DESC LIMIT 1` không đủ xác định một order nếu nhiều order cùng timestamp. Thêm điều kiện giải quyết hòa điểm, như `order_id DESC`, nếu đó là chính sách hợp lệ.

### 24.7. LEFT JOIN biến thành INNER JOIN do WHERE

Nếu muốn giữ khách hàng chưa có order:

```sql
SELECT c.customer_id, o.order_id
FROM subquery_lab.customers AS c
LEFT JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

điều kiện `WHERE o.status = 'PAID'` sẽ loại các hàng không khớp bên phải (status NULL), vì thế loại cả khách hàng chưa có order.

Nếu muốn **giữ mọi khách hàng và chỉ ghép các order PAID**, đặt điều kiện vào `ON`:

```sql
SELECT c.customer_id, o.order_id
FROM subquery_lab.customers AS c
LEFT JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
```

Khi cần **một** đơn PAID gần nhất cho mỗi khách hàng, dùng LEFT JOIN LATERAL với điều kiện PAID bên trong và LIMIT 1.

### 24.8. Dùng subquery kiểm tra dữ liệu thay constraint

`NOT EXISTS` không thay unique constraint dưới concurrency; `IN` không thay foreign key; một scalar lookup không chứng minh bản ghi tham chiếu mãi tồn tại.

### 24.9. Tối ưu sớm bằng cách đổi cấu trúc câu SQL

Một truy vấn JOIN viết lại có thể nhân số hàng nếu quan hệ 1-N. Một window function có thể tạo nhóm NULL khác correlated equality. Một `DISTINCT ON` có thể loại những người đồng hạng mà correlated MAX đang giữ.

**Trước khi so sánh tốc độ, phải chứng minh hai truy vấn cùng ý nghĩa và cùng tập kết quả theo dữ liệu biên.**

---

## 25. Tham số đầu vào và an toàn SQL

Một truy vấn con trong ứng dụng thường nhận điều kiện từ người dùng: mã khách hàng, trạng thái đơn, khoảng giá, ngày bắt đầu/kết thúc.

Không nối trực tiếp giá trị request thành SQL:

```text
"WHERE o.customer_id = " + userInput
```

Thay vào đó, dùng **prepared statement/bind parameter** của driver.

Ví dụ PostgreSQL prepared statement:

```sql
PREPARE latest_paid_order_for_customer(INTEGER) AS
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id,
    r.amount
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS r ON TRUE
WHERE c.customer_id = $1;

EXECUTE latest_paid_order_for_customer(101);

DEALLOCATE latest_paid_order_for_customer;
```

Với khách hàng 101, đây là một cách lấy order PAID gần nhất theo quy tắc đã định. Khách hàng không có PAID vẫn được trả với các cột r NULL do LEFT JOIN LATERAL, miễn có hàng customers tương ứng.

Khi có dữ liệu thuộc nhiều tenant:

- Xác thực và phân quyền người truy cập.
- Áp dụng chính sách tenant trong **mọi** truy vấn con/join liên quan.
- Cân nhắc Row-Level Security khi phù hợp.
- Bind dữ liệu đầu vào; không cho client cung cấp SQL fragment tùy ý.
- Giới hạn số hàng/top-N khi endpoint cho phép tự chọn LIMIT.

Subquery không phải ranh giới bảo mật; nó chỉ là một cấu trúc SQL.

---

## 26. Dữ liệu và tính đồng thời: truy vấn con không khóa tương lai

Giả sử bạn tìm những khách hàng chưa có đơn PAID bằng NOT EXISTS và quyết định phát ưu đãi cho họ. Trong lúc đó, transaction khác có thể tạo một đơn PAID mới.

Một SELECT đúng tại thời điểm nó chạy không có nghĩa kết quả sẽ **giữ nguyên trong tương lai**.

```text
Transaction A:
  SELECT ... WHERE NOT EXISTS(order PAID) -> thấy khách hàng 104

Transaction B:
  INSERT order PAID cho khách hàng 104
  COMMIT

Transaction A:
  Phát ưu đãi dựa trên kết quả cũ
```

Nếu yêu cầu nghiệp vụ cần bảo đảm “mỗi khách hàng chỉ được nhận một ưu đãi”, đặt `UNIQUE(customer_id, campaign_id)` thích hợp trên bảng ưu đãi và xử lý `ON CONFLICT` theo chính sách. Nếu yêu cầu còn phụ thuộc chính xác vào trạng thái order tại thời điểm commit, có thể cần transaction, locking, mức cô lập `SERIALIZABLE` với retry khi thích hợp, hoặc thiết kế điều phối theo khóa nghiệp vụ.

Không coi `NOT EXISTS` hoặc scalar subquery như một cơ chế khóa tự động ngăn transaction khác tạo dữ liệu.

---

## 27. Bài tập thực hành

### Bài 1 — Một giá trị chung cho tất cả hàng

Viết SQL trả mỗi nhân viên kèm:

- `salary` của họ.
- Mức trung bình toàn công ty bằng scalar subquery không tương quan.
- Cột boolean cho biết lương của họ có lớn hơn trung bình hay không.

Dữ liệu lab có mức trung bình toàn công ty **3250**. Có bao nhiêu nhân viên cao hơn mức này?

### Bài 2 — Scalar subquery có 0 và nhiều hàng

Chạy từng câu:

```sql
SELECT (
    SELECT amount
    FROM subquery_lab.orders
    WHERE customer_id = 104
) AS no_order_amount;

SELECT (
    SELECT amount
    FROM subquery_lab.orders
    WHERE customer_id = 101
) AS multiple_order_amount;
```

Giải thích tại sao câu đầu trả NULL, còn câu sau báo lỗi. Viết lại câu thứ hai để trả **SUM(amount)** thay vì nhiều hàng.

### Bài 3 — Cao hơn mức trung bình phòng

Tìm các nhân viên lương cao hơn trung bình **phòng của mình** bằng correlated scalar subquery. Kết quả mong đợi: **Bình, Chi, Hà, Nam**.

Giải thích vì sao một câu thiếu điều kiện `e2.department_id = e.department_id` có thể cho kết quả khác.

### Bài 4 — Phòng chưa có nhân viên

Viết:

1. Correlated scalar subquery `COUNT(*) = 0`.
2. `NOT EXISTS`.
3. `LEFT JOIN ... WHERE e.employee_id IS NULL`.

Tất cả phải tìm phòng **40 — Pháp chế**. Vì sao `AVG(salary) = 0` không phải cách đúng để tìm phòng trống?

### Bài 5 — Derived table tổng hợp

Viết một derived table trả `department_id`, `employee_count`, `avg_salary`. `LEFT JOIN` với `departments` để vẫn giữ phòng 40.

Tại sao phòng 40 có count NULL ở phần derived table trước khi dùng `COALESCE`, trong khi scalar subquery `COUNT(*)` riêng cho phòng 40 lại trả 0?

### Bài 6 — Tất cả khách hàng kể cả chưa có đơn

Viết derived table thống kê số đơn theo customer_id và `LEFT JOIN` vào bảng khách hàng. Kết quả phải có **5 khách hàng**, kể cả 104 và 105. Tách `COUNT(*)` của tất cả đơn và `SUM(amount) FILTER (WHERE status='PAID')`.

Dự đoán tổng PAID của khách hàng 101 và 103.

### Bài 7 — EXISTS và JOIN

Tìm khách hàng có ít nhất một đơn PAID bằng `EXISTS`. Kết quả là 101, 102, 103.

Viết phiên bản `INNER JOIN` và giải thích vì sao khách hàng 101 có thể xuất hiện hai lần. Khi nào `DISTINCT` cần được dùng? Vì sao `EXISTS` diễn đạt yêu cầu “có ít nhất một” rõ hơn?

### Bài 8 — NOT EXISTS và NOT IN

Truy vấn danh sách khách hàng không có order bằng `NOT EXISTS`, dự kiến 104 và 105.

Sau đó kiểm tra:

```sql
SELECT 1 NOT IN (2, 3, NULL);
```

Tại sao không được mặc định thay NOT EXISTS bằng NOT IN trên một cột nullable của bảng staging?

### Bài 9 — Đơn gần nhất với LATERAL

Viết `LEFT JOIN LATERAL` để lấy order gần nhất của từng customer với:

```sql
ORDER BY ordered_at DESC, order_id DESC
LIMIT 1
```

Kiểm tra rằng khách hàng 103 nhận order **1005** khi thời gian hòa điểm; 104 và 105 vẫn xuất hiện với order_id NULL.

Thử `CROSS JOIN LATERAL` và mô tả sự khác biệt.

### Bài 10 — Top hai đơn cho từng khách hàng

Thay `LIMIT 1` thành `LIMIT 2` trong LATERAL. Giải thích số hàng của từng customer và vì sao một `LEFT JOIN LATERAL` tạo hàng NULL-extended cho khách hàng không có order.

### Bài 11 — Cao nhất phòng, giữ tie hay không

Tìm các nhân viên lương cao nhất mỗi phòng bằng:

1. Correlated `MAX(salary)` (giữ những người hòa điểm).
2. `RANK() OVER (PARTITION BY department_id ORDER BY salary DESC)`.
3. `ROW_NUMBER()` với tie-breaker `employee_id ASC`.
4. `DISTINCT ON (department_id)`.

Giải thích tại sao cách 1 và 2 trả **Bình và Chi** cùng phòng 10, còn cách 3 và 4 chỉ trả một người.

### Bài 12 — ANY/ALL và tập rỗng

Sử dụng `>= ALL (SELECT salary ... WHERE department_id = e.department_id)` để tìm lương cao nhất mỗi phòng.

Vì sao phải xem lại trường hợp `department_id IS NULL` của Mai? Kết quả `>= ALL(tập rỗng)` là gì?

### Bài 13 — Null-safe equality

So sánh:

```sql
SELECT
    NULL::INTEGER = NULL::INTEGER AS equals_null,
    NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER
        AS null_safe_equals;
```

Viết lại scalar subquery trung bình phòng để **nhóm những nhân viên chưa phân phòng** cùng nhau bằng `IS NOT DISTINCT FROM`. Giải thích tác động lên kết quả của Mai.

### Bài 14 — Phân tích execution plan

Chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM subquery_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Quan sát PostgreSQL chọn loại plan nào trên bảng nhỏ. Tại sao không nên kết luận plan trên 6 đơn giống plan khi bảng orders có hàng triệu đơn?

### Bài 15 — Chọn phương án cho một báo cáo thực tế

Yêu cầu: mỗi customer hiển thị số đơn PAID, tổng tiền PAID, mã order PAID gần nhất và thời điểm của order đó. Bao gồm cả những khách hàng chưa có order.

Đề xuất một truy vấn kết hợp:

- Derived table hoặc CTE tổng hợp theo customer_id.
- `LEFT JOIN LATERAL` lấy order PAID gần nhất.
- `COALESCE` cho số đơn/tổng tiền theo quy tắc báo cáo.

Giải thích vai trò riêng của từng phần và vì sao không nên dùng nhiều scalar subquery khác nhau mà không thống nhất ORDER BY.

---

## 28. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Scalar subquery báo “more than one row” | Subquery trả nhiều hàng | Xác định lại bài toán: aggregate, điều kiện unique, LIMIT có ORDER BY hoặc derived table |
| Scalar subquery trả NULL | Không có hàng, hoặc giá trị/aggregate trả NULL | Kiểm tra COUNT/EXISTS, xử lý COALESCE chỉ khi phù hợp |
| Lấy sai trung bình phòng | Quên tương quan với department_id | Dùng alias rõ cho inner và outer |
| Truy vấn “cùng phòng” bỏ nhân viên NULL | `= NULL` là UNKNOWN | Quyết định loại ra hoặc dùng null-safe equality |
| Derived table không truy cập được cột outer | Thiếu LATERAL cho subquery trong FROM | Dùng `JOIN LATERAL` nếu cần tham chiếu bảng phía trước |
| LEFT JOIN LATERAL làm mất khách hàng chưa có đơn | Đã dùng CROSS/INNER JOIN LATERAL | Dùng `LEFT JOIN LATERAL ... ON TRUE` |
| LIMIT 1 chọn order không ổn định | Không có ORDER BY hoặc thiếu tie-breaker | Sắp theo thời điểm rồi khóa ổn định |
| EXISTS tạo nhiều hàng? | Nhầm với JOIN | EXISTS là phép kiểm tra tồn tại, không nhân bản hàng outer |
| NOT IN trả rỗng bất ngờ | Subquery có NULL | Phân tích NULL, ưu tiên NOT EXISTS khi tìm phần thiếu |
| JOIN làm SUM/COUNT bị nhân lên | Dữ liệu 1-N hoặc join thêm bảng chi tiết | Tổng hợp theo đúng grain trước khi join |
| AVG phòng trống thành 0 không đúng ý | COALESCE mọi aggregate vô điều kiện | Phân biệt không có dữ liệu và giá trị 0 |
| CTE không nhanh hơn | CTE không tự là index hay cache | Xem plan, điều chỉnh cấu trúc khi có bằng chứng |
| Window function trả khác scalar | Phân nhóm NULL/logic filter không tương đương | Đối chiếu dữ liệu biên |
| DISTINCT ON làm mất người đồng hạng | Nó chọn một hàng mỗi nhóm | Dùng RANK/MAX nếu cần giữ tie |
| Query tương quan chạy chậm | SubPlan lặp, thiếu index, số hàng lớn | EXPLAIN, index khóa join, cân nhắc GROUP+JOIN/window |
| Ghi trùng sau NOT EXISTS | Hai transaction cùng thấy thiếu | Dùng UNIQUE, transaction và retry/idempotency |
| Dữ liệu tenant khác bị tính vào subquery | Quên một phần khóa ghép | Thêm điều kiện tenant_id và kiểm soát truy cập |
| Query trên production sai sau sửa schema | Tên cột không có alias bị phân giải khác | Dùng alias đầy đủ và test regression |

---

## 29. Checklist khi viết truy vấn con trong PostgreSQL

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Mục tiêu cần một giá trị hay một bảng? | Scalar subquery hoặc derived table |
| Scalar subquery có chắc tối đa một hàng? | Unique key, aggregate hoặc ORDER BY/LIMIT có chủ đích |
| Nếu không có hàng, kết quả mong muốn là gì? | NULL, 0, bỏ hàng hay một giá trị khác theo nghiệp vụ |
| Có tham chiếu cột của query ngoài? | Dùng alias rõ, xác định tính correlated |
| Derived table cần dùng cột bảng trước cùng FROM? | Dùng LATERAL |
| Cần giữ hàng ngoài khi không có match? | LEFT JOIN / LEFT JOIN LATERAL |
| Cần một hay nhiều hàng liên quan? | LIMIT 1, LIMIT N, aggregate hoặc window |
| Nếu có tie, chọn/giữ thế nào? | Tie-breaker, RANK, ROW_NUMBER hoặc DISTINCT ON |
| Điều kiện là “có hàng” hay “giá trị bằng”? | EXISTS hoặc IN/= tùy ý nghĩa |
| Điều kiện là “không có hàng”? | Thường dùng NOT EXISTS |
| Có NULL trong khóa hoặc tập giá trị? | Kiểm tra logic ba giá trị, NOT IN, IS NOT DISTINCT FROM |
| Có khóa ghép/tenant không? | So đủ các cột tham chiếu |
| Có group/aggregate không? | Xác định grain; tránh đếm và cộng lặp sau join |
| Có dùng COALESCE không? | Phân biệt 0 và không có dữ liệu |
| Có cần CTE để dễ đọc? | Dùng WITH, nhưng không giả định materialize |
| Kết quả cần thứ tự không? | ORDER BY cuối cùng và tie-breaker khi lấy top-N |
| Dữ liệu lớn? | EXPLAIN (ANALYZE, BUFFERS), index và thống kê |
| Kết quả được dùng cho ghi dữ liệu? | Constraint, transaction, locking, concurrency và retry |
| Có tham số user input? | Prepared statement, kiểm tra quyền và phạm vi tenant |
| Các phiên bản truy vấn có thật sự tương đương? | So sánh trên NULL, duplicate, tập rỗng, tie, hàng không match |

## Kết luận

Trong PostgreSQL, **truy vấn con** cho phép lồng một SELECT vào một câu truy vấn khác để tính giá trị, tạo quan hệ trung gian hoặc kiểm tra bản ghi liên quan.

- **Truy vấn con vô hướng** trả một giá trị: một hàng/một cột là hợp lệ, không có hàng thì kết quả NULL, hơn một hàng thì báo lỗi. Dùng aggregate hoặc ORDER BY/LIMIT khi bài toán thực sự yêu cầu một giá trị được xác định rõ.
- **Truy vấn con dạng bảng** tạo kết quả nhiều hàng/cột, thường trong FROM/JOIN. Nó hữu ích khi tổng hợp theo nhóm trước khi join, phân chia các bước logic hoặc hạn chế nhân bản dữ liệu do quan hệ một-nhiều.
- **Truy vấn tương quan** tham chiếu cột của truy vấn ngoài. Nó có thể là scalar, EXISTS, NOT EXISTS hay bảng LATERAL; do đó “tương quan” là đặc tính tham chiếu, không phải một dạng kết quả tách biệt.
- **`LATERAL`** giúp subquery trong FROM dùng cột bảng phía trước, đặc biệt phù hợp bài toán đơn gần nhất hoặc top-N theo từng nhóm.
- **`EXISTS` và `NOT EXISTS`** diễn đạt trực tiếp sự có mặt/vắng mặt của hàng liên quan, thường rõ hơn việc dùng JOIN có thể tạo duplicate hoặc NOT IN gặp bẫy NULL.
- **JOIN, CTE, window functions và DISTINCT ON** có thể diễn đạt những truy vấn tương tự, nhưng không phải lúc nào cũng tương đương về cách xử lý NULL, tie, duplicate và số hàng.

Viết truy vấn con tốt bắt đầu bằng việc xác định **hình dạng kết quả**, **khóa liên kết**, **ngữ nghĩa của NULL**, **số hàng mong muốn** và **mục đích nghiệp vụ**. Sau khi câu SQL đúng, hãy dùng EXPLAIN và dữ liệu thật để quyết định tối ưu hóa. Cách tiếp cận đó giúp các truy vấn phân tích, báo cáo và lọc dữ liệu nâng cao trở nên dễ hiểu, đáng tin cậy và dễ bảo trì.
