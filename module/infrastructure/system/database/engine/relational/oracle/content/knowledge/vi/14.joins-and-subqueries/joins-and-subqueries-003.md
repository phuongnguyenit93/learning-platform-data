# CROSS JOIN, self join và nguy cơ nhân số dòng trong Oracle

Khi truy vấn nhiều bảng trong Oracle Database, số dòng kết quả không nhất thiết bằng số dòng của bảng chính. Một phép nối có thể tạo ra nhiều dòng cho mỗi dòng nguồn nếu phía còn lại có nhiều bản ghi phù hợp. Với **CROSS JOIN**, số dòng có thể tăng theo tích số lượng hai tập dữ liệu. Với **self join**, cùng một bảng xuất hiện nhiều lần dưới các bí danh khác nhau; nếu điều kiện nối không đủ chặt, truy vấn có thể ghép một hàng với chính nó, tạo cặp đối xứng hoặc nhân bản kết quả.

Bài học này giải thích cách dùng CROSS JOIN và self join, cách tính cardinality, cách nhận diện fan-out trong quan hệ 1:N/N:M và các phương án viết truy vấn để giữ đúng mức chi tiết dữ liệu.

Sau bài học, bạn có thể:

- Giải thích CROSS JOIN và tính số dòng kết quả theo số dòng hai nguồn.
- Tạo các tổ hợp có chủ đích, ví dụ sản phẩm × ngày hoặc nhân viên × ca làm.
- Dùng self join để nối nhân viên với quản lý, tìm các cặp bản ghi hoặc so sánh những hàng trong cùng bảng.
- Phân biệt self join với truy vấn phân cấp nhiều cấp bằng `CONNECT BY` hoặc recursive subquery factoring.
- Phát hiện điều kiện join thiếu khóa, khóa không duy nhất và quan hệ nhiều-nhiều.
- Hiểu vì sao join nhiều bảng con có thể làm COUNT/SUM bị nhân lên.
- Chọn `EXISTS`, `NOT EXISTS`, pre-aggregation hoặc join chi tiết theo đúng mục tiêu.
- Kiểm tra số dòng và execution plan trước khi đưa truy vấn vào báo cáo hoặc ứng dụng.

> Các ví dụ dùng bảng có tiền tố `LAB_` và phù hợp để chạy trong schema thực hành. Không dùng câu lệnh tạo bảng hoặc truy vấn Cartesian lớn trên production khi chưa ước lượng cardinality và tài nguyên. Một CROSS JOIN nhỏ có thể rất hữu ích; một CROSS JOIN hàng triệu dòng có thể nhanh chóng trở thành vấn đề CPU, PGA, TEMP và I/O.

## 1. Vì sao số dòng sau JOIN có thể tăng?

Giả sử có bảng khách hàng:

| CUSTOMER_ID | CUSTOMER_NAME |
| ---: | --- |
| 101 | An |
| 102 | Binh |

Và bảng đơn hàng:

| ORDER_ID | CUSTOMER_ID |
| ---: | ---: |
| 1 | 101 |
| 2 | 101 |
| 3 | 102 |

Một khách hàng có thể có nhiều đơn hàng. Khi join:

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;
```

Kết quả có ba dòng. Khách hàng 101 xuất hiện hai lần vì có hai đơn hàng; khách hàng 102 xuất hiện một lần. Đây là hành vi đúng của quan hệ **một-nhiều (1:N)**.

Một JOIN không có nghĩa “mỗi hàng bảng trái chỉ xuất hiện một lần”. Quy tắc thực tế là: **mỗi cặp hàng thỏa điều kiện ON tạo ra một hàng kết quả**. Nếu một hàng trái khớp ba hàng phải, hàng trái đó xuất hiện ba lần.

### 1.1. Cardinality của JOIN

Cardinality là số lượng hàng của một tập kết quả. Với một điều kiện join tổng quát:

```text
Số dòng kết quả
= tổng số cặp (hàng trái, hàng phải)
  thỏa điều kiện JOIN
```

Với quan hệ 1:N có khóa cha duy nhất:

- Mỗi hàng cha có thể ghép với 0, 1 hoặc nhiều hàng con.
- `INNER JOIN` chỉ giữ cha có ít nhất một hàng con.
- `LEFT JOIN` giữ mọi hàng cha; cha không có con vẫn xuất hiện với cột phía con là NULL.

Nếu khóa join ở phía phải **không duy nhất**, một hàng trái có thể ghép với nhiều hàng phải ngay cả khi người viết truy vấn nghĩ đó là quan hệ 1:1. Đây là nguồn fan-out phổ biến.

## 2. CROSS JOIN: tích Descartes có chủ đích

### 2.1. Cú pháp và ý nghĩa

`CROSS JOIN` tạo mọi tổ hợp giữa các hàng của hai nguồn:

```sql
SELECT *
FROM table_a
CROSS JOIN table_b;
```

Không có điều kiện `ON` trong cú pháp CROSS JOIN. Nếu bảng A có M dòng và bảng B có N dòng, kết quả có:

```text
M × N dòng
```

Ví dụ:

| A | Số dòng |
| --- | ---: |
| Bảng A | 3 |
| Bảng B | 4 |
| Kết quả CROSS JOIN | 3 × 4 = 12 |

Nếu một trong hai tập rỗng, kết quả cũng rỗng. Nếu cả hai có dữ liệu, mỗi hàng A kết hợp với tất cả hàng B.

### 2.2. Ví dụ nhỏ có thể chạy

```sql
WITH colors AS (
    SELECT 'RED' AS color FROM dual UNION ALL
    SELECT 'GREEN' FROM dual UNION ALL
    SELECT 'BLUE' FROM dual
),
sizes AS (
    SELECT 'S' AS size_code FROM dual UNION ALL
    SELECT 'M' FROM dual UNION ALL
    SELECT 'L' FROM dual UNION ALL
    SELECT 'XL' FROM dual
)
SELECT color, size_code
FROM colors
CROSS JOIN sizes
ORDER BY color, size_code;
```

Kết quả có 12 tổ hợp màu và kích thước. Đây là ví dụ phù hợp khi nghiệp vụ thật sự cần **mọi tổ hợp**.

### 2.3. CROSS JOIN dùng khi nào?

Một số trường hợp hợp lý:

- Tạo tập **sản phẩm × ngày** để hiển thị cả ngày không có doanh số.
- Tạo ma trận **chi nhánh × chỉ tiêu** trước khi ghép dữ liệu thực tế.
- Kết hợp các lựa chọn cấu hình để sinh test cases.
- Tạo tổ hợp tham số nhỏ cho một báo cáo hoặc phép tính.
- Tạo cặp giữa hai tập độc lập khi bài toán thật sự yêu cầu mọi kết hợp.

Ví dụ, tạo các ngày trong một tuần rồi kết hợp với danh sách sản phẩm:

```sql
WITH days AS (
    SELECT DATE '2026-01-01' + LEVEL - 1 AS sales_day
    FROM dual
    CONNECT BY LEVEL <= 7
),
products AS (
    SELECT 10 AS product_id, 'Keyboard' AS product_name FROM dual
    UNION ALL
    SELECT 20, 'Mouse' FROM dual
    UNION ALL
    SELECT 30, 'Monitor' FROM dual
)
SELECT d.sales_day, p.product_id, p.product_name
FROM days d
CROSS JOIN products p
ORDER BY d.sales_day, p.product_id;
```

Kết quả có 7 × 3 = 21 tổ hợp. Đây có thể là khung dữ liệu cho báo cáo ngày; bước tiếp theo có thể `LEFT JOIN` với doanh số tổng hợp để ngày không có bán hàng vẫn xuất hiện.

### 2.4. CROSS JOIN không phải cách viết thay thế JOIN có điều kiện

Hai cách sau có thể biểu diễn cùng tập kết quả khi điều kiện lọc tương ứng:

```sql
-- Cách viết rõ ràng cho quan hệ join:
SELECT c.customer_id, o.order_id
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;

-- Dạng tích rồi lọc:
SELECT c.customer_id, o.order_id
FROM lab_customers c
CROSS JOIN lab_orders o
WHERE o.customer_id = c.customer_id;
```

Về ngữ nghĩa, truy vấn thứ hai tạo quan hệ các cặp rồi giữ những cặp thỏa predicate. Optimizer Oracle có thể biến đổi/đẩy điều kiện để thực thi hiệu quả; không nhất thiết vật lý tạo toàn bộ tích khổng lồ rồi mới lọc. Tuy nhiên, **cách viết JOIN ... ON diễn đạt ý định nối bảng rõ ràng hơn** và ít rủi ro bỏ quên điều kiện.

Không dùng CROSS JOIN cộng WHERE để che một phép nối thông thường nếu thực chất bạn cần INNER JOIN. CROSS JOIN nên được dùng khi tích Descartes là ý định thực sự.

## 3. Nguy cơ Cartesian product ngoài ý muốn

### 3.1. Thiếu điều kiện join

Một lỗi kinh điển:

```sql
SELECT c.customer_id, o.order_id
FROM lab_customers c, lab_orders o;
```

Đây là cú pháp comma join cũ không có điều kiện nối; kết quả là tích Descartes. Nếu có 100.000 khách hàng và 2.000.000 đơn hàng, tập kết quả lý thuyết có thể lên tới 200 tỷ cặp trước các điều kiện lọc khác.

Khi truy vấn nhiều bảng, thiếu một điều kiện join có thể làm số dòng tăng đột biến mà không có lỗi cú pháp. Kết quả vẫn “hợp lệ” về SQL, nhưng sai nghiệp vụ và rất tốn tài nguyên.

### 3.2. Điều kiện join thiếu một phần khóa ghép

Giả sử bảng chi tiết có khóa nghiệp vụ gồm `ORDER_ID` và `LINE_NO`, nhưng truy vấn chỉ nối theo `ORDER_ID` hoặc thậm chí chỉ theo `CUSTOMER_ID`. Khi nhiều dòng cùng khóa cha, một hàng có thể ghép với tất cả chi tiết của nhóm thay vì đúng dòng cần tìm.

Ví dụ:

```sql
-- Sai nếu mục tiêu là nối đúng một dòng chi tiết:
SELECT *
FROM order_lines a
JOIN shipment_lines b
  ON a.order_id = b.order_id;

-- Đúng hơn khi hai bảng cùng xác định dòng bằng cả hai khóa:
SELECT *
FROM order_lines a
JOIN shipment_lines b
  ON b.order_id = a.order_id
 AND b.line_no = a.line_no;
```

Điều kiện chính xác phụ thuộc mô hình dữ liệu; đừng thêm cột vào ON chỉ để làm giảm số dòng nếu những cột đó không thuộc quan hệ thật. Cần xem PK/UK/FK và quy tắc nghiệp vụ.

### 3.3. Join vào bảng có khóa không duy nhất

Giả sử một bảng ánh xạ mã khách hàng có nhiều bản ghi lịch sử:

| CUSTOMER_CODE | VERSION | SEGMENT |
| --- | ---: | --- |
| C101 | 1 | RETAIL |
| C101 | 2 | PREMIUM |

Nếu nối chỉ bằng `CUSTOMER_CODE`, một khách hàng có thể ghép cả hai phiên bản. Nếu nghiệp vụ muốn phiên bản hiện hành, cần predicate trạng thái/ngày hiệu lực phù hợp hoặc chọn một bản ghi trước khi join.

**Tên cột giống nhau không chứng minh khóa là duy nhất.** Hãy xác minh bằng constraint hoặc truy vấn kiểm tra:

```sql
SELECT customer_code, COUNT(*) AS row_count
FROM customer_mapping
GROUP BY customer_code
HAVING COUNT(*) > 1;
```

Nếu kết quả có hàng, `CUSTOMER_CODE` không phải khóa duy nhất trong tập dữ liệu đó.

## 4. Self join là gì?

**Self join** là phép join một bảng với chính nó. SQL không có từ khóa riêng tên SELF JOIN; ta khai báo bảng nhiều lần và đặt alias khác nhau để mỗi lần xuất hiện đóng vai trò riêng.

Ví dụ bảng nhân viên có cột `MANAGER_ID` tham chiếu `EMPLOYEE_ID` của một nhân viên khác:

```text
EMPLOYEES
┌─────────────┬───────────────┬────────────┐
│ EMPLOYEE_ID │ EMPLOYEE_NAME │ MANAGER_ID │
├─────────────┼───────────────┼────────────┤
│ 1           │ An            │ NULL       │
│ 2           │ Binh          │ 1          │
│ 3           │ Chi           │ 1          │
│ 4           │ Dung          │ 2          │
└─────────────┴───────────────┴────────────┘

      Binh ── reports to ── An
       │
       └── Dung reports to Binh

      Chi ─── reports to ── An
```

Ta cần đọc hai vai trò từ cùng bảng:

- Alias `e`: nhân viên cấp dưới.
- Alias `m`: nhân viên quản lý.

### 4.1. Self join để lấy tên nhân viên và tên quản lý

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.manager_id,
    m.employee_name AS manager_name
FROM employees e
LEFT JOIN employees m
       ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

`EMPLOYEES` xuất hiện hai lần:

| Alias | Vai trò |
| --- | --- |
| `e` | Hàng nhân viên đang hiển thị |
| `m` | Hàng quản lý được tìm qua `e.manager_id` |

Dùng `LEFT JOIN` để giữ cả nhân viên không có quản lý (ví dụ CEO). Nếu dùng `INNER JOIN`, hàng có `MANAGER_ID IS NULL` sẽ không match và bị loại.

### 4.2. Tại sao phải dùng alias?

Nếu viết:

```sql
SELECT employee_name
FROM employees
JOIN employees
  ON manager_id = employee_id;
```

Oracle không thể phân biệt cột nào thuộc lần xuất hiện thứ nhất hay thứ hai, và có thể báo lỗi tên cột không rõ ràng. Alias làm rõ vai trò và mọi tham chiếu cột:

```sql
SELECT e.employee_name AS employee,
       m.employee_name AS manager
FROM employees e
JOIN employees m
  ON m.employee_id = e.manager_id;
```

Trong self join, hãy đặt alias có ý nghĩa như `employee`/`manager`, `current_row`/`previous_row` hoặc `parent`/`child` thay vì alias quá chung khó đọc.

## 5. Tạo bộ dữ liệu nhân viên cho self join

Ví dụ lab đầy đủ:

```sql
CREATE TABLE lab_employees (
    employee_id   NUMBER(10)
        CONSTRAINT pk_lab_employees PRIMARY KEY,
    employee_name VARCHAR2(80) NOT NULL,
    department_id NUMBER(10),
    manager_id    NUMBER(10),
    CONSTRAINT fk_lab_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees (employee_id)
);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (1, 'An', 10, NULL);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (2, 'Binh', 10, 1);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (3, 'Chi', 20, 1);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (4, 'Dung', 10, 2);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (5, 'Ha', 10, 2);

COMMIT;
```

Bảng có self-referencing foreign key: `MANAGER_ID` có thể tham chiếu `EMPLOYEE_ID` của cùng bảng. Oracle bảo đảm manager được tham chiếu tồn tại (trừ khi giá trị NULL); constraint này **không tự bảo đảm cấu trúc quản lý không có chu trình**. Quy tắc như “nhân viên không được là quản lý của chính mình” hoặc “không được tạo vòng A → B → A” cần kiểm tra nghiệp vụ riêng.

### 5.1. Hiển thị nhân viên cùng quản lý

```sql
SELECT
    e.employee_id,
    e.employee_name,
    m.employee_id AS manager_id,
    m.employee_name AS manager_name
FROM lab_employees e
LEFT JOIN lab_employees m
       ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

### 5.2. Tìm các nhân viên báo cáo trực tiếp cho một quản lý

```sql
SELECT
    m.employee_name AS manager_name,
    e.employee_name AS direct_report
FROM lab_employees m
JOIN lab_employees e
  ON e.manager_id = m.employee_id
WHERE m.employee_id = 2
ORDER BY e.employee_id;
```

Ở truy vấn này, alias `m` là người quản lý, alias `e` là cấp dưới. Vai trò alias phụ thuộc mục tiêu truy vấn, không phải alias nào cũng cố định là bảng trái/bảng phải theo một nghĩa nghiệp vụ duy nhất.

### 5.3. Tìm nhân viên cùng phòng ban

Self join có thể tạo các cặp nhân viên cùng phòng:

```sql
SELECT
    e1.employee_name AS employee_1,
    e2.employee_name AS employee_2,
    e1.department_id
FROM lab_employees e1
JOIN lab_employees e2
  ON e2.department_id = e1.department_id
 AND e2.employee_id > e1.employee_id
ORDER BY e1.department_id, e1.employee_id, e2.employee_id;
```

Điều kiện `e2.employee_id > e1.employee_id` có hai tác dụng:

1. Loại trường hợp một nhân viên ghép với chính mình (`id = id`).
2. Chỉ giữ một chiều của mỗi cặp; không trả đồng thời (Binh, Dung) và (Dung, Binh).

Nếu dùng `e1.employee_id <> e2.employee_id`, cả hai hướng của một cặp sẽ xuất hiện. Nếu không có điều kiện khác, hàng có thể tự ghép với chính nó.

### 5.4. Đếm số cấp dưới trực tiếp

```sql
SELECT
    m.employee_id,
    m.employee_name,
    COUNT(e.employee_id) AS direct_report_count
FROM lab_employees m
LEFT JOIN lab_employees e
       ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.employee_name
ORDER BY m.employee_id;
```

Dùng `COUNT(e.employee_id)` thay vì `COUNT(*)` để quản lý không có cấp dưới nhận số 0. Với LEFT JOIN, hàng quản lý không có nhân viên con vẫn tạo một hàng kết quả với các cột `e` là NULL; `COUNT(*)` sẽ đếm hàng outer-join đó thành 1, trong khi `COUNT(e.employee_id)` bỏ NULL.

## 6. Self join để so sánh bản ghi trong cùng bảng

Self join không chỉ dùng cho quan hệ nhân viên-quản lý. Nó còn có thể tìm:

- Những sản phẩm cùng nhóm có giá khác nhau.
- Các lần đo liên tiếp của cùng thiết bị.
- Các cặp giao dịch cùng khách hàng trong một khoảng thời gian.
- Các bản ghi nghi trùng theo email/số điện thoại.
- Những hàng có ngày hiệu lực chồng lấn.

Ví dụ tìm các cặp giao dịch cùng khách hàng trong bảng `LAB_TRANSACTIONS`:

```sql
SELECT
    t1.transaction_id AS transaction_1,
    t2.transaction_id AS transaction_2,
    t1.customer_id,
    t1.transaction_time AS time_1,
    t2.transaction_time AS time_2
FROM lab_transactions t1
JOIN lab_transactions t2
  ON t2.customer_id = t1.customer_id
 AND t2.transaction_id > t1.transaction_id
WHERE t2.transaction_time >= t1.transaction_time
  AND t2.transaction_time < t1.transaction_time + INTERVAL '1' DAY
ORDER BY t1.customer_id, t1.transaction_id, t2.transaction_id;
```

Ví dụ này tìm cặp có cùng khách hàng, ID thứ hai lớn hơn ID thứ nhất và thời điểm thứ hai nằm trong 24 giờ sau thời điểm thứ nhất. Nó là **mẫu minh họa**; ý nghĩa của ID và khoảng thời gian phải khớp yêu cầu nghiệp vụ. Nếu bảng lớn, điều kiện theo thời gian và index cần được thiết kế để tránh số cặp quá lớn.

### 6.1. Tìm bản ghi trùng

Ví dụ tìm các hàng cùng email:

```sql
SELECT
    a.customer_id AS customer_1,
    b.customer_id AS customer_2,
    a.email
FROM customers a
JOIN customers b
  ON b.email = a.email
 AND b.customer_id > a.customer_id
WHERE a.email IS NOT NULL
ORDER BY a.email, a.customer_id, b.customer_id;
```

Điều kiện thứ tự khóa loại cặp trùng hai chiều và self-match. Điều kiện `email IS NOT NULL` tránh ghép các hàng thiếu email theo quy tắc NULL. Nếu collation của cột không phân biệt hoa/thường hoặc dấu, việc so sánh có thể coi nhiều email khác nhau về ký tự là bằng nhau; cần chọn quy tắc trùng phù hợp và chuẩn hóa email theo nghiệp vụ.

### 6.2. Vì sao self join có thể tăng số cặp rất nhanh?

Nếu một nhóm có n hàng, số cặp không thứ tự, không ghép chính nó là:

```text
n × (n - 1) / 2
```

Với n = 100, nhóm có 4.950 cặp. Với n = 10.000, nhóm có 49.995.000 cặp. Do đó self join dùng để tìm cặp có thể rất tốn tài nguyên dù bảng nguồn có vẻ không quá lớn.

Nếu chỉ cần biết **có ít nhất một bản ghi trùng** thay vì liệt kê mọi cặp, `GROUP BY ... HAVING COUNT(*) > 1` hoặc `EXISTS` có thể phù hợp hơn. Không sinh hàng triệu cặp nếu ứng dụng chỉ cần một cờ “có trùng”.

## 7. Self join khác truy vấn phân cấp nhiều cấp

Self join với hai alias thường mô tả **một quan hệ giữa hai cấp** (ví dụ nhân viên và quản lý trực tiếp). Nếu muốn đi từ một nhân viên qua quản lý, lên cấp cao hơn nhiều lần, cần một truy vấn phân cấp.

### 7.1. CONNECT BY PRIOR

Oracle hỗ trợ hierarchical query:

```sql
SELECT
    LEVEL AS hierarchy_level,
    employee_id,
    employee_name,
    manager_id,
    CONNECT_BY_ROOT employee_name AS top_employee,
    SYS_CONNECT_BY_PATH(employee_name, ' / ') AS management_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
```

Giải thích:

- `START WITH manager_id IS NULL` chọn nhân viên gốc (không có quản lý).
- `CONNECT BY PRIOR employee_id = manager_id` đi từ hàng cha có employee_id tới hàng con có manager_id bằng ID của cha.
- `LEVEL` cho biết cấp trong cây.
- `CONNECT_BY_ROOT` lấy giá trị ở hàng gốc.
- `SYS_CONNECT_BY_PATH` tạo đường dẫn qua các cấp.
- `ORDER SIBLINGS BY` sắp xếp các nhân viên cùng cấp cha mà không phá cấu trúc phân cấp.

Nếu dữ liệu có vòng lặp, hierarchical query có thể báo lỗi chu trình; Oracle có tùy chọn `NOCYCLE` và `CONNECT_BY_ISCYCLE` để phát hiện/điều khiển một số trường hợp. Dùng NOCYCLE không thay thế việc sửa dữ liệu phân cấp sai.

### 7.2. Recursive subquery factoring

Các phiên bản Oracle hỗ trợ recursive subquery factoring có thể dùng `WITH ... UNION ALL` để đi qua nhiều cấp. Cú pháp/khả năng cụ thể phụ thuộc version và quy tắc recursive query của Oracle. Một mẫu khái niệm:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    depth
) AS (
    SELECT employee_id,
           employee_name,
           manager_id,
           1
    FROM lab_employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           t.depth + 1
    FROM lab_employees e
    JOIN employee_tree t
      ON e.manager_id = t.employee_id
)
SELECT *
FROM employee_tree
ORDER BY depth, employee_id;
```

Đây là recursive traversal, không còn là self join hai alias đơn thuần. Khi dữ liệu có chu trình, cần có cơ chế phát hiện/giới hạn vòng lặp phù hợp.

### 7.3. Chọn kỹ thuật nào?

| Nhu cầu | Kỹ thuật phù hợp |
| --- | --- |
| Lấy tên nhân viên và quản lý trực tiếp | Self join |
| Tìm các cặp nhân viên cùng phòng | Self join có điều kiện loại self-pair và cặp đảo |
| Tìm xem có hàng liên quan không | EXISTS |
| Đếm cấp dưới trực tiếp | Self join + GROUP BY |
| Liệt kê toàn bộ cấp quản lý nhiều tầng | CONNECT BY hoặc recursive query |
| Chỉ cần kiểm tra chu trình | Cơ chế kiểm tra hierarchy phù hợp và constraint/validation nghiệp vụ |

## 8. Fan-out khi JOIN nhiều bảng: nguyên nhân tổng tiền bị nhân

Đây là lỗi báo cáo rất phổ biến. Giả sử:

- Một đơn hàng có nhiều dòng sản phẩm.
- Một đơn hàng cũng có nhiều lần thanh toán hoặc nhiều lần ghi nhận trạng thái.

Nếu join cả hai bảng con trực tiếp vào đơn hàng, các dòng con có thể tạo tích kết hợp.

### 8.1. Ví dụ 1 đơn hàng, 2 order lines và 3 payment events

```text
ORDERS
ORDER_ID = 100
      │
      ├───────────────┐
      ▼               ▼
ORDER_LINES        PAYMENT_EVENTS
2 dòng             3 dòng
      │               │
      └───────┬───────┘
              ▼
      JOIN theo ORDER_ID
              │
              ▼
        2 × 3 = 6 dòng
```

Truy vấn:

```sql
SELECT
    o.order_id,
    l.line_id,
    l.line_amount,
    p.payment_event_id,
    p.paid_amount
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id
JOIN payment_events p
  ON p.order_id = o.order_id
WHERE o.order_id = 100;
```

Kết quả có 6 hàng: mỗi dòng chi tiết được ghép với mỗi sự kiện thanh toán. Nếu cộng `LINE_AMOUNT` trong kết quả, tổng dòng chi tiết bị nhân 3; nếu cộng `PAID_AMOUNT`, tổng thanh toán bị nhân 2.

### 8.2. Tạo dữ liệu lab để thấy tổng bị sai

```sql
CREATE TABLE lab_fanout_orders (
    order_id NUMBER PRIMARY KEY
);

CREATE TABLE lab_fanout_lines (
    line_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    line_amount NUMBER(10, 2)
);

CREATE TABLE lab_fanout_payments (
    payment_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    paid_amount NUMBER(10, 2)
);

INSERT INTO lab_fanout_orders VALUES (100);

INSERT INTO lab_fanout_lines VALUES (1, 100, 60);
INSERT INTO lab_fanout_lines VALUES (2, 100, 40);

INSERT INTO lab_fanout_payments VALUES (10, 100, 50);
INSERT INTO lab_fanout_payments VALUES (11, 100, 30);
INSERT INTO lab_fanout_payments VALUES (12, 100, 20);

COMMIT;
```

Tổng đúng:

- Tổng dòng chi tiết = 60 + 40 = 100.
- Tổng thanh toán = 50 + 30 + 20 = 100.

Nhưng truy vấn join cả hai bảng con:

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    SUM(l.line_amount) AS wrong_line_total,
    SUM(p.paid_amount) AS wrong_payment_total
FROM lab_fanout_orders o
JOIN lab_fanout_lines l
  ON l.order_id = o.order_id
JOIN lab_fanout_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Kết quả:

| ORDER_ID | JOINED_ROWS | WRONG_LINE_TOTAL | WRONG_PAYMENT_TOTAL |
| ---: | ---: | ---: | ---: |
| 100 | 6 | 300 | 200 |

Hai dòng chi tiết được lặp ba lần, ba khoản thanh toán được lặp hai lần. SQL không sai cú pháp; **mức chi tiết của kết quả đã thay đổi**, nên phép cộng trên kết quả join không còn tương ứng tổng nghiệp vụ ban đầu.

### 8.3. Vì sao SUM(DISTINCT amount) không phải cách sửa chung?

Một cách chữa cháy thường thấy:

```sql
SELECT
    SUM(DISTINCT l.line_amount) AS line_total
FROM lab_fanout_orders o
JOIN lab_fanout_lines l
  ON l.order_id = o.order_id
JOIN lab_fanout_payments p
  ON p.order_id = o.order_id;
```

Trong dữ liệu lab, `SUM(DISTINCT line_amount)` cho 100 vì hai line amount là 60 và 40. Nhưng nếu hai dòng sản phẩm hợp lệ đều có giá trị 60, DISTINCT chỉ cộng 60 một lần và **làm mất một dòng nghiệp vụ thật**.

DISTINCT loại giá trị trùng, không biết hai giá trị giống nhau thuộc hai giao dịch khác nhau hay là một hàng bị nhân do join. Đừng dùng `SUM(DISTINCT ...)` như một giải pháp tổng quát cho fan-out.

## 9. Giải quyết fan-out bằng pre-aggregation

Nếu cần một hàng cho mỗi đơn hàng, hãy tổng hợp riêng từng bảng con về đúng mức chi tiết rồi mới join:

```sql
WITH line_totals AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(line_amount) AS line_total
    FROM lab_fanout_lines
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS payment_total
    FROM lab_fanout_payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    NVL(l.line_count, 0) AS line_count,
    NVL(l.line_total, 0) AS line_total,
    NVL(p.payment_count, 0) AS payment_count,
    NVL(p.payment_total, 0) AS payment_total
FROM lab_fanout_orders o
LEFT JOIN line_totals l
       ON l.order_id = o.order_id
LEFT JOIN payment_totals p
       ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Mỗi CTE trả về tối đa một hàng cho mỗi `ORDER_ID`, vì vậy join các kết quả tổng hợp không tạo tích 2 × 3 nữa. Kết quả đúng:

| ORDER_ID | LINE_COUNT | LINE_TOTAL | PAYMENT_COUNT | PAYMENT_TOTAL |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 2 | 100 | 3 | 100 |

`NVL(...,0)` ở đây là lựa chọn trình bày/nghiệp vụ: đơn hàng không có dòng hoặc thanh toán được hiển thị tổng 0. Nếu NULL có ý nghĩa khác với 0 trong hệ thống, hãy giữ NULL hoặc dùng trạng thái riêng thay vì thay thế máy móc.

### 9.1. Nguyên tắc mức chi tiết (grain)

Trước khi join, hãy xác định mỗi nguồn đang có **một hàng đại diện cho điều gì**:

| Nguồn | Grain |
| --- | --- |
| `ORDERS` | Một hàng cho mỗi đơn hàng |
| `ORDER_LINES` | Một hàng cho mỗi dòng chi tiết đơn hàng |
| `PAYMENT_EVENTS` | Một hàng cho mỗi sự kiện thanh toán |
| `LINE_TOTALS` | Một hàng cho mỗi đơn hàng sau GROUP BY |
| `PAYMENT_TOTALS` | Một hàng cho mỗi đơn hàng sau GROUP BY |

Nếu báo cáo cần một hàng/đơn hàng, mọi bảng được join vào kết quả cuối phải có **tối đa một hàng cho mỗi order_id** hoặc được tổng hợp về grain đó. Đây là cách tư duy hiệu quả nhất để tránh fan-out.

### 9.2. Khi cần chi tiết cả dòng hàng và thanh toán

Nếu mục tiêu là hiển thị tất cả cặp line-payment, kết quả 6 hàng là đúng theo yêu cầu. Khi đó không cộng tổng line/payment trực tiếp trên tập kết quả rồi gọi đó là tổng đơn hàng. Có thể:

- Trả hai tập dữ liệu riêng.
- Trả order header kèm hai collection/JSON arrays riêng.
- Tổng hợp trước rồi join tổng vào dữ liệu chi tiết theo grain phù hợp.
- Chọn một bảng con làm grain chính và chỉ nối các bảng có quan hệ đúng với từng dòng đó.

**Không có một câu JOIN đúng cho mọi báo cáo**; câu truy vấn phải phản ánh mức chi tiết đầu ra mong muốn.

## 10. EXISTS và NOT EXISTS để tránh nhân dòng

Nếu chỉ cần kiểm tra một hàng cha có ít nhất một hàng con hay không, join chi tiết có thể tạo nhiều dòng không cần thiết. `EXISTS` diễn đạt điều kiện tồn tại và giữ mỗi hàng cha tối đa một lần trong kết quả của truy vấn ngoài.

### 10.1. Tìm khách hàng có ít nhất một đơn hàng

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Nếu một khách hàng có 100 đơn hàng, khách hàng vẫn chỉ xuất hiện một lần vì EXISTS chỉ cần biết có ít nhất một hàng thỏa điều kiện.

So sánh với:

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;
```

Truy vấn JOIN trả một dòng cho mỗi đơn hàng; khách hàng có nhiều đơn xuất hiện nhiều lần.

### 10.2. Tìm khách hàng chưa có đơn hàng

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

NOT EXISTS là cách diễn đạt anti-join rõ ràng. Nó không gặp bẫy “một NULL trong subquery làm NOT IN không trả hàng” theo cách `NOT IN` có thể gặp. Dù vậy, vẫn cần xác định quy tắc với khóa NULL ở phía ngoài và điều kiện tương quan.

### 10.3. EXISTS không thay thế JOIN khi cần dữ liệu chi tiết

Nếu cần tên từng sản phẩm trong đơn, hãy JOIN tới bảng chi tiết. EXISTS chỉ trả lời câu hỏi “có tồn tại hay không”, không trả cột của hàng con. Chọn công cụ theo mục tiêu, không thay mọi JOIN bằng EXISTS.

## 11. LEFT JOIN và điều kiện lọc: tránh mất hàng hoặc nhân dòng

Một truy vấn có thể giữ hàng bên trái nhưng điều kiện đặt sai chỗ làm kết quả thành inner join:

```sql
-- Chỉ trả khách hàng có đơn hàng PAID:
SELECT c.customer_id, o.order_id
FROM lab_customers c
LEFT JOIN lab_orders o
       ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Hàng khách hàng không có đơn sẽ có `o.status = NULL`; điều kiện WHERE là UNKNOWN nên bị loại. Nếu mục tiêu là **giữ tất cả khách hàng, chỉ ghép đơn PAID**, đặt điều kiện ở ON:

```sql
SELECT c.customer_id, o.order_id
FROM lab_customers c
LEFT JOIN lab_orders o
       ON o.customer_id = c.customer_id
      AND o.status = 'PAID';
```

Đây là vấn đề khác với fan-out nhưng có thể xuất hiện cùng lúc. `LEFT JOIN` vẫn có thể nhân dòng nếu một khách hàng có nhiều đơn PAID; outer join không có nghĩa “mỗi hàng trái tối đa một lần”.

### 11.1. Lọc bảng con trước khi join

Có thể viết CTE/subquery để diễn đạt rõ tập con:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, amount
    FROM lab_orders
    WHERE status = 'PAID'
)
SELECT c.customer_id, p.order_id, p.amount
FROM lab_customers c
LEFT JOIN paid_orders p
       ON p.customer_id = c.customer_id;
```

Đây vẫn là quan hệ 1:N nếu mỗi khách hàng có nhiều đơn PAID. CTE giúp tách logic lọc, không tự làm dữ liệu duy nhất.

## 12. Kiểm tra row multiplication một cách có hệ thống

Khi một truy vấn trả nhiều dòng hơn mong đợi, hãy đo từng bước thay vì thêm DISTINCT để che hiện tượng.

### 12.1. Đếm nguồn trước khi join

```sql
SELECT COUNT(*) AS customers FROM lab_customers;
SELECT COUNT(*) AS orders FROM lab_orders;
```

Đếm số hàng từng bảng nguồn và kiểm tra tính duy nhất của khóa:

```sql
SELECT customer_id, COUNT(*) AS matches
FROM lab_orders
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Kết quả này không nhất thiết là lỗi: nhiều đơn hàng cho một khách hàng là bình thường. Mục tiêu là hiểu mức độ 1:N trước khi join.

### 12.2. Đếm số dòng sau mỗi bước join

```sql
SELECT COUNT(*) AS joined_rows
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;
```

Sau đó thêm từng bảng một và đo lại. Nếu số dòng tăng đột ngột khi nối một bảng, kiểm tra:

- Khóa join ở phía mới có unique không?
- Predicate có thiếu một phần khóa ghép không?
- Có nhiều phiên bản/lịch sử cho cùng một business key không?
- Có điều kiện lọc theo trạng thái/ngày hiệu lực bị thiếu không?
- Có vô tình tạo Cartesian product do thiếu điều kiện nối không?

### 12.3. Kiểm tra mỗi khóa cha có bao nhiêu hàng kết quả

```sql
SELECT c.customer_id,
       COUNT(*) AS rows_after_join,
       COUNT(o.order_id) AS matched_orders
FROM lab_customers c
LEFT JOIN lab_orders o
       ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

`COUNT(*)` ít nhất là 1 cho mỗi khách hàng trong LEFT JOIN; `COUNT(o.order_id)` đếm số đơn match vì order_id là khóa không NULL. Đây là cách quan sát fan-out theo từng khóa cha.

### 12.4. Kiểm tra khóa phía phải có duy nhất

Nếu kỳ vọng quan hệ 1:1:

```sql
SELECT reference_code, COUNT(*) AS row_count
FROM reference_table
GROUP BY reference_code
HAVING COUNT(*) > 1;
```

Nếu có kết quả, không thể giả định `reference_code` xác định một hàng. Cần dùng khóa đầy đủ hoặc quy tắc chọn phiên bản (ví dụ bản ghi hiện hành theo thời gian).

### 12.5. So sánh số khóa chính và số hàng

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM (
    SELECT o.order_id
    FROM lab_orders o
    JOIN lab_order_lines l
      ON l.order_id = o.order_id
    JOIN lab_payment_events p
      ON p.order_id = o.order_id
);
```

Nếu `ROW_COUNT` lớn hơn `DISTINCT_ORDERS`, mỗi order_id xuất hiện nhiều lần trong kết quả. Điều đó có thể đúng với báo cáo chi tiết; nếu mục tiêu là một hàng/order thì cần thay đổi cấu trúc truy vấn.

**COUNT(DISTINCT primary_key)** là công cụ chẩn đoán hữu ích, không tự sửa các tổng tiền hoặc cột measure đã bị nhân.

## 13. Execution plan và cardinality estimate

Oracle Optimizer ước tính số hàng ở từng bước của execution plan để chọn join order, join method (nested loops, hash join, sort merge join) và cách truy cập dữ liệu. Khi ước tính sai nhiều, plan có thể không phù hợp với workload.

### 13.1. Xem plan ước tính

```sql
EXPLAIN PLAN FOR
SELECT
    c.customer_id,
    o.order_id
FROM lab_customers c
CROSS JOIN lab_orders o;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Plan có thể hiển thị bước Cartesian hoặc các operation liên quan. Chi tiết tên operation và cách optimizer biến đổi phụ thuộc phiên bản, thống kê và query. EXPLAIN PLAN cho biết **ước tính**, không phải số hàng thực tế chắc chắn.

### 13.2. Xem actual rows khi có quyền và thống kê runtime

Trong môi trường test, có thể thu thập row-source statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       o.order_id
FROM lab_customers c
CROSS JOIN lab_orders o;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

`ALLSTATS LAST` có thể hiển thị estimated rows và actual rows cho lần chạy cuối nếu thống kê runtime được thu thập và tài khoản có quyền phù hợp. Trên hệ thống thật, việc bật/đọc plan cần tuân theo quyền và quy trình DBA.

### 13.3. CROSS JOIN không luôn đồng nghĩa full materialization

Về logic, CROSS JOIN định nghĩa tích Descartes. Về thực thi, optimizer có thể áp dụng predicate pushdown, join transformation hoặc các chiến lược khác khi query có điều kiện phù hợp. Vì thế không nên suy luận thời gian chạy chỉ từ số dòng lý thuyết của một trung gian nếu optimizer có thể loại bỏ/giảm dữ liệu sớm.

Tuy nhiên, nếu kết quả cuối thật sự cần M × N tổ hợp, không có phép tối ưu nào xóa được yêu cầu tạo/tiêu thụ từng tổ hợp đó. Ước lượng cardinality và giới hạn tập đầu vào trước khi chạy là cần thiết.

## 14. Các mẫu truy vấn và cách lựa chọn

| Mục tiêu | Mẫu phù hợp | Lý do |
| --- | --- | --- |
| Mọi tổ hợp giữa hai tập nhỏ | `CROSS JOIN` | Tích Descartes là kết quả mong muốn |
| Nối khách hàng với từng đơn | `JOIN ... ON` | Quan hệ 1:N, một hàng/order |
| Lấy khách hàng có ít nhất một đơn | `EXISTS` | Không nhân khách hàng theo số đơn |
| Lấy khách hàng chưa có đơn | `NOT EXISTS` | Anti-join rõ ràng, tránh bẫy NULL của NOT IN |
| Nhân viên và quản lý trực tiếp | Self join | Hai vai trò của cùng bảng |
| Mọi cặp nhân viên khác nhau, không lặp cặp đảo | Self join với `id1 < id2` | Mỗi cặp không thứ tự xuất hiện một lần |
| Toàn bộ cây quản lý nhiều cấp | `CONNECT BY`/recursive query | Đi qua nhiều cấp quan hệ |
| Tổng dòng hàng và tổng thanh toán theo đơn | Pre-aggregate từng bảng con rồi join | Giữ mỗi nguồn ở grain một hàng/order |
| Cần tất cả dòng chi tiết và sự kiện thanh toán | Join chi tiết có chủ đích | Fan-out là một phần của yêu cầu; không cộng lại measure sai grain |

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Số dòng tăng đột biến | Thiếu điều kiện join hoặc CROSS JOIN ngoài ý muốn | Kiểm tra FROM/ON và cardinality từng bước |
| Một khách hàng xuất hiện nhiều lần | Quan hệ 1:N hợp lệ hoặc khóa phía phải không unique | Xác định grain; không mặc định là lỗi |
| Tổng tiền cao gấp nhiều lần | Join hai bảng con độc lập tạo fan-out | Pre-aggregate mỗi bảng con trước khi join |
| COUNT(*) lớn hơn số đơn | Mỗi đơn có nhiều line/payment | Đếm theo grain cần báo cáo; cân nhắc COUNT DISTINCT chỉ cho mục đích đếm khóa |
| SUM(DISTINCT amount) bị thiếu tiền | Nhiều dòng hợp lệ có cùng amount | Không dùng DISTINCT để khử hàng bị nhân; sửa cấu trúc join |
| Self join trả cặp A-B và B-A | Điều kiện chỉ loại bằng nhau, không loại cặp đảo | Dùng khóa duy nhất với điều kiện nhỏ hơn hoặc lớn hơn |
| Self join trả hàng ghép với chính nó | Thiếu predicate loại self-match | Thêm điều kiện khóa khác nhau nếu nghiệp vụ yêu cầu |
| CEO/nhân viên không có quản lý biến mất | Dùng INNER JOIN thay vì LEFT JOIN | Dùng LEFT JOIN khi phải giữ hàng không có parent |
| Cấp quản lý nhiều tầng không hiển thị | Chỉ self join một cấp | Dùng CONNECT BY hoặc recursive query |
| EXISTS/NOT EXISTS trả khác JOIN | Mục tiêu existence khác mục tiêu trả chi tiết | Chọn cú pháp theo dữ liệu cần trả |
| LEFT JOIN mất hàng bên trái | Điều kiện phía phải đặt trong WHERE | Xem xét chuyển predicate sang ON |
| Plan ước tính ít hàng nhưng thực tế rất nhiều | Thống kê, correlation, join key hoặc cardinality estimate không phù hợp | Xem actual rows, stats và predicate |

## 16. Bài thực hành tổng hợp

### Phần A — Tính tích Descartes

Chạy CTE màu và kích thước ở mục 2.2. Trả lời:

1. Nếu thêm hai màu thì kết quả có bao nhiêu dòng?
2. Nếu bảng sizes rỗng thì kết quả ra sao?
3. Nếu thêm WHERE chỉ giữ màu RED, cardinality còn bao nhiêu?

### Phần B — Self join nhân viên-quản lý

Chạy bảng LAB_EMPLOYEES và truy vấn ở mục 5.1. Thử đổi LEFT JOIN thành INNER JOIN. Ghi lại hàng nào biến mất và giải thích.

### Phần C — Tìm cặp đồng nghiệp

Chạy truy vấn self join ở mục 5.3. Đổi điều kiện lớn hơn thành khác nhau. Vì sao số cặp tăng? Bỏ hẳn predicate ID. Vì sao mỗi nhân viên có thể ghép với chính mình?

### Phần D — Tái hiện fan-out

Chạy truy vấn join LAB_FANOUT_ORDERS, LAB_FANOUT_LINES và LAB_FANOUT_PAYMENTS ở mục 8.2. Ghi lại:

- Số hàng của từng bảng con.
- Số hàng sau join.
- Tổng line amount đúng và tổng bị nhân.
- Tổng payment đúng và tổng bị nhân.

### Phần E — Sửa bằng pre-aggregation

Chạy truy vấn CTE LINE_TOTALS và PAYMENT_TOTALS ở mục 9. Xác nhận mỗi CTE chỉ có tối đa một hàng/order và kết quả tổng trở lại đúng 100 cho cả hai nhóm.

### Phần F — Chọn EXISTS hay JOIN

Viết hai truy vấn:

1. Trả danh sách khách hàng có đơn hàng (mỗi khách hàng một lần).
2. Trả danh sách từng đơn hàng cùng tên khách hàng.

Giải thích vì sao truy vấn thứ nhất phù hợp EXISTS còn truy vấn thứ hai cần JOIN.

### Phần G — Chẩn đoán một truy vấn có số dòng bất thường

Giả sử truy vấn báo cáo join bốn bảng và trả 10 triệu hàng trong khi bảng gốc chỉ có 100 nghìn khách hàng. Hãy lập thứ tự điều tra:

1. Đếm hàng nguồn.
2. Xác định grain và khóa duy nhất của mỗi bảng.
3. Đếm hàng sau từng join.
4. Kiểm tra điều kiện join có đủ các cột khóa không.
5. Xác định quan hệ 1:N/N:M có chủ đích.
6. Tổng hợp trước những bảng con nếu báo cáo cần một hàng/khóa cha.
7. Xem actual plan và đánh giá tài nguyên.

## 17. Nguyên tắc thực hành tốt

1. **Viết điều kiện JOIN tường minh.** Dùng JOIN ... ON để người đọc nhận ra quan hệ; chỉ dùng CROSS JOIN khi muốn mọi tổ hợp.
2. **Xác định grain trước khi viết SELECT.** Một hàng kết quả đại diện cho khách hàng, đơn hàng, dòng hàng hay cặp sự kiện?
3. **Kiểm tra tính duy nhất của khóa join.** Tên cột giống nhau không bảo đảm phía phải chỉ có một hàng.
4. **Đếm từng bước.** So sánh row count sau mỗi join để tìm đúng nơi fan-out bắt đầu.
5. **Không chữa fan-out bằng DISTINCT một cách máy móc.** DISTINCT có thể che lỗi và làm mất các bản ghi hợp lệ.
6. **Không dùng SUM(DISTINCT measure) để khử hàng bị nhân.** Hai giao dịch thật có thể có cùng số tiền.
7. **Pre-aggregate bảng con về đúng grain** trước khi join nếu báo cáo cần một hàng cho mỗi khóa cha.
8. **Dùng EXISTS khi chỉ cần kiểm tra tồn tại.** Đừng join ra nhiều hàng con rồi loại trùng nếu không cần dữ liệu con.
9. **Self join cần alias và điều kiện rõ.** Dùng khóa duy nhất với điều kiện thứ tự khi tạo cặp không thứ tự.
10. **Dùng CONNECT BY/recursive query cho cây nhiều cấp.** Self join hai alias chỉ mô tả quan hệ giữa hai lần xuất hiện.
11. **Đánh giá cardinality và execution plan.** Một phép nối hợp lệ về logic vẫn có thể quá lớn đối với tài nguyên thực tế.
12. **Kiểm thử cả dữ liệu biên.** Parent không có child, child có nhiều dòng, khóa NULL, khóa trùng và nhóm có hàng nghìn phần tử.

## 18. Câu hỏi tự kiểm tra

1. Hai bảng lần lượt có 40 và 25 hàng. CROSS JOIN tạo bao nhiêu hàng nếu cả hai đều không rỗng?
2. CROSS JOIN khác INNER JOIN ở điểm nào về điều kiện ghép?
3. Vì sao một JOIN có thể làm hàng bảng trái xuất hiện nhiều lần?
4. Một bảng có CUSTOMER_ID nhưng không unique. Điều gì có thể xảy ra nếu dùng nó để join với bảng khách hàng?
5. Self join có phải một từ khóa SQL riêng không? Vì sao cần alias?
6. Trong employee-manager self join, vì sao LEFT JOIN giữ được CEO còn INNER JOIN loại CEO?
7. Vì sao điều kiện e2.id lớn hơn e1.id phù hợp khi liệt kê các cặp không thứ tự?
8. Một nhóm có 1.000 hàng. Số cặp không thứ tự, không ghép chính nó là bao nhiêu?
9. Hai bảng con có lần lượt 2 và 3 hàng cho một order. Join theo order_id tạo bao nhiêu cặp?
10. Vì sao tổng line amount bị nhân theo số payment events?
11. Vì sao SUM(DISTINCT amount) không phải cách sửa chung?
12. Khi nào EXISTS phù hợp hơn JOIN?
13. Một truy vấn cần một hàng/order và có hai bảng con 1:N. Bạn nên đưa các bảng con về grain nào trước khi join?
14. Self join hai alias khác gì CONNECT BY khi cần đi qua nhiều cấp?
15. COUNT(*) và COUNT(child.primary_key) khác nhau thế nào trong LEFT JOIN khi parent không có child?

## 19. Mô hình ghi nhớ

```text
                    JOIN
                      │
          Mỗi cặp hàng thỏa ON tạo một hàng
                      │
             ┌────────┴─────────┐
             ▼                  ▼
        CROSS JOIN           SELF JOIN
       M × N tổ hợp       Cùng bảng, nhiều alias
             │                  │
       Chỉ dùng khi         Quan hệ 2 vai trò
       muốn mọi cặp         hoặc tạo các cặp hàng
             │                  │
             └────────┬─────────┘
                      ▼
              KIỂM SOÁT GRAIN
                      │
          ┌───────────┼─────────────┐
          ▼           ▼             ▼
        EXISTS    PRE-AGGREGATE   JOIN ĐÚNG KHÓA
      Chỉ cần có   Mỗi bảng con    Đủ khóa ghép,
      hay không    về đúng grain   kiểm tra uniqueness
          │           │             │
          └───────────┼─────────────┘
                      ▼
           Đếm dòng / kiểm tra plan
                      │
                      ▼
            Tổng hợp không bị nhân
```

**Điểm quan trọng nhất:** số dòng sau JOIN được quyết định bởi số cặp hàng thỏa điều kiện, không phải bởi số dòng của bảng chính. CROSS JOIN tạo tích Descartes có chủ đích; self join dùng nhiều alias để so sánh hoặc biểu diễn quan hệ trong cùng bảng; còn fan-out thường xuất hiện khi nối nhiều quan hệ 1:N hoặc khi khóa join không duy nhất. Hãy xác định grain, kiểm tra cardinality và tổng hợp từng bảng con đúng mức trước khi nối để tránh báo cáo sai và truy vấn phình to ngoài dự kiến.
