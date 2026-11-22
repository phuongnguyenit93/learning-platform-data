# WITH và tái sử dụng khối truy vấn có tên

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** JOIN và truy vấn con  
> **Mục tiêu:** Sử dụng mệnh đề `WITH` (subquery factoring/common table expression – CTE) để chia một câu SQL phức tạp thành các khối truy vấn có tên; hiểu phạm vi sử dụng, thứ tự phụ thuộc, cách tái sử dụng CTE trong JOIN và truy vấn con, tổng hợp dữ liệu theo từng bước, truy vấn phân cấp đệ quy và cách Oracle optimizer xử lý CTE.

## 1. Vì sao cần khối truy vấn có tên?

Một báo cáo có thể phải thực hiện nhiều việc liên tiếp:

1. Chọn đơn hàng trong khoảng ngày cần báo cáo.
2. Tính tổng tiền mặt hàng theo từng đơn.
3. Tính số tiền thanh toán thành công theo từng đơn.
4. Kết nối các kết quả với khách hàng.
5. Tổng hợp doanh thu và số đơn theo khách hàng.

Nếu viết toàn bộ logic thành một câu SELECT dài, các truy vấn con có thể lồng nhiều tầng. Người đọc phải lần theo dấu ngoặc để hiểu mỗi tập dữ liệu được tạo ra từ đâu, có bao nhiêu dòng và đang đại diện cho đối tượng nào.

Oracle cho phép đặt tên cho các khối truy vấn ngay đầu câu lệnh bằng **`WITH`**:

```sql
WITH
order_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           SUM(paid_amount) AS paid_total
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       NVL(i.item_total, 0) AS item_total,
       NVL(p.paid_total, 0) AS paid_total
FROM orders o
LEFT JOIN order_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id;
```

Hai khối `ORDER_TOTALS` và `PAYMENT_TOTALS` là các **common table expression (CTE)**, còn gọi là **named subquery** hoặc **subquery factoring** trong tài liệu Oracle.

Có thể hiểu chúng như những tập kết quả được đặt tên để câu truy vấn chính tham chiếu. Mỗi CTE có một định nghĩa SELECT riêng; các CTE có thể tham chiếu CTE được khai báo trước đó trong cùng mệnh đề WITH.

Lợi ích chính:

- Tách một truy vấn phức tạp thành các bước có ý nghĩa.
- Đặt tên cho logic dùng nhiều lần trong cùng câu SQL.
- Làm rõ grain (một dòng đại diện cho đối tượng nào) trước khi JOIN.
- Dễ kiểm tra từng bước bằng cách chạy riêng phần SELECT của CTE.
- Hỗ trợ các truy vấn đệ quy như duyệt cây tổ chức, danh mục phân cấp hoặc cấu trúc cha-con.

**Lưu ý:** CTE là thành phần của một câu lệnh SQL. Nó không tự tạo bảng vật lý, không tồn tại như view độc lập sau khi câu lệnh kết thúc và không mặc nhiên được materialize thành dữ liệu tạm.

## 2. Cú pháp WITH cơ bản

Cấu trúc phổ biến:

```sql
WITH cte_name [(column_alias_1, column_alias_2, ...)] AS (
    subquery
)
SELECT ...
FROM cte_name;
```

Ví dụ:

```sql
WITH active_employees AS (
    SELECT employee_id,
           first_name,
           last_name,
           department_id,
           salary
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT employee_id,
       first_name,
       last_name,
       salary
FROM active_employees
WHERE salary >= 5000
ORDER BY salary DESC;
```

Giải thích:

- `ACTIVE_EMPLOYEES` là tên CTE.
- SELECT bên trong ngoặc là định nghĩa tập dữ liệu.
- Truy vấn chính sử dụng CTE giống một nguồn dữ liệu trong FROM.
- Các điều kiện ở truy vấn chính có thể tiếp tục lọc tập dữ liệu CTE.

### 2.1. CTE có danh sách alias cột

Có thể khai báo tên cột ngay sau tên CTE:

```sql
WITH department_summary (
    department_id,
    employee_count,
    average_salary
) AS (
    SELECT department_id,
           COUNT(*),
           AVG(salary)
    FROM employees
    GROUP BY department_id
)
SELECT department_id,
       employee_count,
       average_salary
FROM department_summary
ORDER BY department_id;
```

Danh sách alias giúp đặt tên đầu ra rõ ràng, nhất là khi biểu thức SELECT là hàm tổng hợp hoặc phép tính. Số lượng alias phải phù hợp số biểu thức trong SELECT của CTE.

Nếu không khai báo danh sách alias, có thể đặt alias trong chính SELECT:

```sql
WITH department_summary AS (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT *
FROM department_summary;
```

Hai cách đều hợp lệ. Nên chọn một quy ước nhất quán để người đọc biết cột nào được cung cấp bởi CTE.

### 2.2. Một WITH có nhiều CTE

Các CTE được ngăn cách bằng dấu phẩy:

```sql
WITH
high_salary AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE salary >= 10000
),
department_info AS (
    SELECT department_id, department_name
    FROM departments
)
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM high_salary e
JOIN department_info d
  ON d.department_id = e.department_id;
```

Không đặt dấu phẩy sau CTE cuối cùng. Truy vấn chính xuất hiện sau danh sách CTE.

### 2.3. CTE sau có thể dùng CTE trước

Ví dụ một pipeline ba bước:

```sql
WITH
active_orders AS (
    SELECT order_id, customer_id, order_date
    FROM orders
    WHERE status = 'ACTIVE'
),
item_totals AS (
    SELECT i.order_id,
           SUM(i.quantity * i.unit_price) AS item_amount
    FROM order_items i
    JOIN active_orders a
      ON a.order_id = i.order_id
    GROUP BY i.order_id
),
customer_totals AS (
    SELECT a.customer_id,
           COUNT(*) AS order_count,
           SUM(t.item_amount) AS total_amount
    FROM active_orders a
    JOIN item_totals t
      ON t.order_id = a.order_id
    GROUP BY a.customer_id
)
SELECT customer_id, order_count, total_amount
FROM customer_totals
ORDER BY total_amount DESC;
```

`ITEM_TOTALS` sử dụng `ACTIVE_ORDERS`; `CUSTOMER_TOTALS` sử dụng cả hai CTE đã khai báo trước đó. Việc đặt thứ tự như vậy giúp thể hiện luồng phụ thuộc.

Một CTE không thể tham chiếu tùy tiện một CTE được khai báo sau nó trong danh sách không đệ quy. Nếu có quan hệ phụ thuộc vòng hoặc cần tự tham chiếu, phải dùng cú pháp recursive subquery factoring phù hợp.

## 3. CTE và inline view (subquery trong FROM)

Trước khi có WITH, một cách phổ biến để chia logic là dùng inline view:

```sql
SELECT d.department_id,
       d.employee_count,
       d.average_salary
FROM (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
) d
WHERE d.employee_count >= 5;
```

Có thể viết cùng logic bằng CTE:

```sql
WITH department_summary AS (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT department_id,
       employee_count,
       average_salary
FROM department_summary
WHERE employee_count >= 5;
```

Hai cách đều đặt một query block làm nguồn dữ liệu cho query bên ngoài. CTE thường dễ đọc hơn khi:

- Có nhiều bước tính toán.
- Một query block được tham chiếu ở nhiều nơi trong cùng câu SQL.
- Cần đặt tên có ý nghĩa cho từng tập dữ liệu.
- Có truy vấn đệ quy.

Inline view vẫn phù hợp với truy vấn nhỏ, chỉ dùng một lần và không cần tách thành tên riêng. Không cần chuyển mọi subquery trong FROM thành CTE chỉ để câu SQL dài hơn.

### 3.1. CTE không phải view

| Đối tượng | Phạm vi tồn tại | Có lưu định nghĩa riêng trong schema? | Dùng lại ở câu SQL khác? |
|---|---|---|---|
| Inline view | Một câu SQL | Không | Không trực tiếp |
| CTE (WITH) | Một câu SQL | Không | Không trực tiếp |
| View | Schema database | Có | Có |
| Materialized view | Schema database và có dữ liệu được lưu | Có | Có; dữ liệu cần refresh theo chiến lược |
| Global temporary table | Schema database; dữ liệu theo session/transaction tùy khai báo | Có | Có trong phạm vi dữ liệu tạm phù hợp |

Nếu một logic truy vấn cần được nhiều câu SQL hoặc nhiều ứng dụng dùng chung, cân nhắc tạo view. Nếu cần lưu kết quả tổng hợp để đọc nhiều lần và chấp nhận chính sách refresh, cân nhắc materialized view. CTE chủ yếu phục vụ tổ chức một câu lệnh.

## 4. Tái sử dụng một CTE nhiều lần

Một điểm hữu ích của CTE là có thể tham chiếu cùng tên nhiều lần trong truy vấn chính hoặc trong các CTE tiếp theo.

Ví dụ: tìm khách hàng có đơn hàng, rồi so sánh tổng đơn hàng với mức trung bình toàn bộ khách hàng:

```sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(order_total) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.order_count,
       c.total_amount,
       (SELECT AVG(total_amount)
        FROM customer_totals) AS average_customer_total
FROM customer_totals c
WHERE c.total_amount >
      (SELECT AVG(total_amount)
       FROM customer_totals)
ORDER BY c.total_amount DESC;
```

`CUSTOMER_TOTALS` được dùng ở truy vấn chính và hai scalar subquery. Việc đặt tên giúp không phải lặp lại toàn bộ định nghĩa GROUP BY.

Tuy nhiên, **tham chiếu một CTE nhiều lần không đồng nghĩa Oracle chắc chắn tính nó đúng một lần**. Optimizer quyết định biến đổi query block, inline, merge hoặc dùng temporary table transformation tùy chi phí và ngữ cảnh.

### 4.1. Tái sử dụng trong nhiều JOIN

```sql
WITH
eligible_customers AS (
    SELECT customer_id, customer_name
    FROM customers
    WHERE customer_status = 'ACTIVE'
),
orders_by_customer AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(order_total) AS order_total
    FROM orders
    GROUP BY customer_id
),
returns_by_customer AS (
    SELECT o.customer_id,
           COUNT(r.return_id) AS return_count
    FROM orders o
    JOIN returns r
      ON r.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT c.customer_id,
       c.customer_name,
       NVL(o.order_count, 0) AS order_count,
       NVL(o.order_total, 0) AS order_total,
       NVL(r.return_count, 0) AS return_count
FROM eligible_customers c
LEFT JOIN orders_by_customer o
  ON o.customer_id = c.customer_id
LEFT JOIN returns_by_customer r
  ON r.customer_id = c.customer_id;
```

Mỗi CTE có một grain cụ thể:

- `ELIGIBLE_CUSTOMERS`: một dòng mỗi customer.
- `ORDERS_BY_CUSTOMER`: tối đa một dòng mỗi customer.
- `RETURNS_BY_CUSTOMER`: tối đa một dòng mỗi customer.

Nhờ tổng hợp các bảng chi tiết trước khi JOIN, truy vấn tránh nhân số dòng order với số dòng return của cùng khách hàng.

## 5. Dùng CTE để chia JOIN phức tạp thành các bước

### 5.1. Bài toán: tổng hợp đơn hàng, item và payment

Giả sử:

- `ORDERS` có một dòng mỗi đơn.
- `ORDER_ITEMS` có nhiều dòng mỗi đơn.
- `PAYMENTS` có nhiều dòng mỗi đơn.

Nếu JOIN item và payment trực tiếp, mỗi item có thể ghép với mỗi payment của cùng order, khiến các phép SUM bị nhân dòng.

CTE giúp tính riêng từng bảng con:

```sql
WITH
item_totals AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(quantity) AS total_units,
           SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS paid_amount
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       o.order_total,
       NVL(i.line_count, 0) AS line_count,
       NVL(i.total_units, 0) AS total_units,
       NVL(i.item_amount, 0) AS item_amount,
       NVL(p.payment_count, 0) AS payment_count,
       NVL(p.paid_amount, 0) AS paid_amount
FROM orders o
LEFT JOIN item_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id;
```

Mỗi CTE được GROUP BY order_id nên có tối đa một dòng cho mỗi order. Khi JOIN với ORDERS, hai tập tổng hợp không nhân lẫn nhau.

### 5.2. Kiểm chứng grain của CTE

Có thể kiểm tra CTE đã thực sự duy nhất theo khóa chưa:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
)
SELECT order_id, COUNT(*) AS rows_per_order
FROM item_totals
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Kết quả đúng phải không có dòng. Nếu có nhiều dòng cho một order, cần xem lại khóa GROUP BY hoặc dữ liệu đầu vào.

CTE không tự đảm bảo unique; chính biểu thức SELECT, GROUP BY, DISTINCT và constraint mới xác định cardinality.

### 5.3. Chọn LEFT JOIN hay INNER JOIN ở truy vấn chính

Dùng `LEFT JOIN` nếu muốn giữ cả đơn hàng không có item/payment phù hợp. Dùng `INNER JOIN` nếu chỉ muốn đơn có dữ liệu ở cả hai phía.

Ví dụ lọc payment thành công bên trong CTE:

```sql
WITH settled_payment_totals AS (
    SELECT order_id,
           SUM(paid_amount) AS settled_amount
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       NVL(p.settled_amount, 0) AS settled_amount
FROM orders o
LEFT JOIN settled_payment_totals p
  ON p.order_id = o.order_id;
```

Đơn không có payment SETTLED vẫn xuất hiện với settled_amount bằng 0 do NVL. Nếu điều kiện payment status được đưa vào WHERE sau LEFT JOIN, các hàng NULL-extended có thể bị loại và kết quả gần như INNER JOIN.

## 6. CTE kết hợp truy vấn con và EXISTS

CTE có thể là nguồn dữ liệu cho subquery, và ngược lại CTE có thể chứa điều kiện EXISTS.

### 6.1. EXISTS trong CTE

```sql
WITH customers_with_recent_orders AS (
    SELECT c.customer_id,
           c.customer_name
    FROM customers c
    WHERE EXISTS (
        SELECT 1
        FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.order_date >= DATE '2026-01-01'
    )
)
SELECT customer_id, customer_name
FROM customers_with_recent_orders;
```

`EXISTS` kiểm tra có ít nhất một dòng phù hợp. Nếu một khách có 20 đơn, CTE vẫn chỉ trả một dòng khách hàng vì truy vấn ngoài xuất phát từ customers và EXISTS không nhân dòng.

### 6.2. NOT EXISTS để tìm đối tượng không có bản ghi liên quan

```sql
WITH customers_without_orders AS (
    SELECT c.customer_id,
           c.customer_name
    FROM customers c
    WHERE NOT EXISTS (
        SELECT 1
        FROM orders o
        WHERE o.customer_id = c.customer_id
    )
)
SELECT *
FROM customers_without_orders;
```

Đây là mẫu anti-join logic. Nó thường dễ diễn đạt ý nghĩa “không có bản ghi liên quan” và tránh một số vấn đề NULL có thể gặp khi viết NOT IN.

### 6.3. Scalar subquery trong CTE

```sql
WITH employee_metrics AS (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           (
               SELECT AVG(e2.salary)
               FROM employees e2
               WHERE e2.department_id = e.department_id
           ) AS department_average
    FROM employees e
)
SELECT employee_id,
       department_id,
       salary,
       department_average
FROM employee_metrics
WHERE salary > department_average;
```

Scalar subquery phải trả về tối đa một dòng. Ở đây AVG luôn trả một giá trị tổng hợp cho tập phù hợp (có thể NULL nếu không có giá trị đầu vào). Nếu scalar subquery trả nhiều hơn một dòng, Oracle có thể báo lỗi `ORA-01427`.

Có thể viết cùng bài toán bằng CTE tổng hợp rồi JOIN:

```sql
WITH department_averages AS (
    SELECT department_id,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT e.employee_id,
       e.department_id,
       e.salary,
       d.average_salary
FROM employees e
JOIN department_averages d
  ON d.department_id = e.department_id
WHERE e.salary > d.average_salary;
```

Cách thứ hai làm rõ tập trung bình theo phòng ban và có thể thuận tiện hơn khi dùng nhiều lần.

## 7. CTE cho phép đặt tên cho nhiều bước lọc và biến đổi

Ví dụ pipeline báo cáo theo tháng:

```sql
WITH
filtered_orders AS (
    SELECT order_id,
           customer_id,
           order_date,
           order_total
    FROM orders
    WHERE order_date >= DATE '2026-01-01'
      AND order_date <  DATE '2027-01-01'
      AND status <> 'CANCELLED'
),
monthly_totals AS (
    SELECT TRUNC(order_date, 'MM') AS order_month,
           COUNT(*) AS order_count,
           SUM(order_total) AS revenue
    FROM filtered_orders
    GROUP BY TRUNC(order_date, 'MM')
),
ranked_months AS (
    SELECT order_month,
           order_count,
           revenue,
           RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM monthly_totals
)
SELECT order_month,
       order_count,
       revenue,
       revenue_rank
FROM ranked_months
ORDER BY order_month;
```

Mỗi bước có một nhiệm vụ:

- Lọc phạm vi ngày và trạng thái.
- Gom theo tháng.
- Tính thứ hạng trên kết quả tổng hợp.
- Trả kết quả theo thứ tự thời gian.

CTE giúp tên bước phản ánh ý nghĩa nghiệp vụ. Không nhất thiết mỗi phép tính nhỏ đều cần một CTE riêng; hãy tách khi điều đó giúp hiểu hoặc tái sử dụng logic.

### 7.1. CTE với analytic function

Có thể đặt analytic function trong CTE để lọc kết quả của nó ở query bên ngoài:

```sql
WITH employee_rankings AS (
    SELECT employee_id,
           department_id,
           salary,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC
           ) AS salary_rank
    FROM employees
)
SELECT employee_id,
       department_id,
       salary,
       salary_rank
FROM employee_rankings
WHERE salary_rank <= 3
ORDER BY department_id, salary_rank, employee_id;
```

Không thể dùng alias `SALARY_RANK` ở WHERE cùng query block nơi analytic expression được tính theo cách thông thường; CTE tạo query block bên ngoài để lọc kết quả đó.

Nếu nhiều nhân viên đồng hạng, DENSE_RANK có thể trả hơn ba người ở một phòng ban. Nếu yêu cầu đúng tối đa ba hàng, dùng ROW_NUMBER với quy tắc tie-breaker rõ ràng.

## 8. Phạm vi và cách đặt tên CTE

### 8.1. CTE chỉ có hiệu lực trong một statement

Ví dụ:

```sql
WITH active_customers AS (
    SELECT customer_id
    FROM customers
    WHERE status = 'ACTIVE'
)
SELECT *
FROM active_customers;
```

Sau khi statement kết thúc, tên `ACTIVE_CUSTOMERS` không trở thành bảng hoặc view để câu lệnh tiếp theo sử dụng. Nếu chạy riêng:

```sql
SELECT * FROM active_customers;
```

Oracle không tìm thấy CTE đó, trừ khi schema thực sự có đối tượng cùng tên.

### 8.2. Đặt tên rõ nghĩa, tránh tên quá chung

Tên như `A`, `T1`, `TEMP` không nói lên vai trò của tập dữ liệu. Nên dùng tên mô tả grain hoặc nội dung:

- `ORDERS_IN_PERIOD`
- `ITEM_TOTALS_BY_ORDER`
- `SETTLED_PAYMENTS_BY_ORDER`
- `CUSTOMER_MONTHLY_REVENUE`
- `EMPLOYEE_HIERARCHY`

Tên nên ngắn vừa đủ, nhất quán với alias cột và quy ước schema.

### 8.3. Alias bảng trong CTE

```sql
WITH employee_base AS (
    SELECT employee_id,
           manager_id,
           department_id
    FROM employees
)
SELECT e.employee_id,
       m.employee_id AS manager_employee_id
FROM employee_base e
LEFT JOIN employee_base m
  ON m.employee_id = e.manager_id;
```

Cùng một CTE có thể được tham chiếu nhiều lần với alias khác nhau, tương tự self-join bảng. Mỗi alias biểu diễn một vai trò trong câu JOIN.

### 8.4. Tên CTE và tên đối tượng schema

CTE có thể trùng tên với bảng hoặc view trong một số ngữ cảnh phân giải tên; việc này làm câu SQL khó đọc và dễ gây nhầm. Tránh đặt tên CTE trùng với đối tượng thật trong schema. Chọn tên riêng mô tả query block và luôn dùng alias rõ ràng trong FROM.

## 9. CTE đệ quy: duyệt dữ liệu phân cấp

Một CTE không đệ quy chỉ tham chiếu các query block đã định nghĩa trước. Oracle còn hỗ trợ **recursive subquery factoring**, cho phép một CTE tham chiếu chính nó để duyệt cấu trúc cây hoặc tạo dãy.

Ví dụ bảng nhân viên có quan hệ quản lý:

```text
EMPLOYEES
employee_id | employee_name | manager_id
------------+---------------+-----------
1           | An             | NULL
2           | Bình           | 1
3           | Chi            | 1
4           | Dũng           | 2
5           | Hà             | 2
```

Mục tiêu: bắt đầu từ nhân viên gốc, tìm tất cả cấp dưới.

### 9.1. Cấu trúc recursive WITH

Mẫu khái quát:

```sql
WITH hierarchy_cte (column_1, column_2, level_no) AS (
    -- Anchor member: hàng bắt đầu
    SELECT ...
    FROM ...
    WHERE ...

    UNION ALL

    -- Recursive member: mở rộng từ kết quả trước
    SELECT ...
    FROM base_table b
    JOIN hierarchy_cte h
      ON ...
)
SELECT *
FROM hierarchy_cte;
```

Có hai phần:

- **Anchor member:** tạo các hàng ban đầu, không tham chiếu CTE đệ quy.
- **Recursive member:** lấy hàng đã có trong CTE để tìm hàng tiếp theo.
- `UNION ALL` kết hợp anchor và các vòng mở rộng.
- Tên cột được khai báo sau tên CTE giúp quy định rõ cấu trúc kết quả.

### 9.2. Ví dụ duyệt cấp dưới theo manager

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1 AS hierarchy_level
    FROM employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id,
       employee_name,
       manager_id,
       hierarchy_level
FROM employee_tree
ORDER BY hierarchy_level, employee_id;
```

Ở mỗi vòng, Oracle tìm nhân viên có `MANAGER_ID` bằng `EMPLOYEE_ID` của các hàng đã được tìm ở vòng trước. `HIERARCHY_LEVEL` tăng một đơn vị qua mỗi cấp.

### 9.3. Tìm cây con của một nhân viên cụ thể

Nếu cần bắt đầu từ manager có ID do ứng dụng cung cấp, bind giá trị:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1
    FROM employees e
    WHERE e.employee_id = :p_root_employee_id

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
SELECT *
FROM employee_tree
ORDER BY hierarchy_level, employee_id;
```

Giá trị root là dữ liệu nên bind được. Cấu trúc đệ quy và tên bảng vẫn cố định.

### 9.4. SEARCH để quy định thứ tự duyệt

Oracle hỗ trợ mệnh đề `SEARCH` trong recursive subquery factoring để tạo cột sắp xếp theo kiểu depth-first hoặc breadth-first.

Ví dụ:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1
    FROM employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
SEARCH DEPTH FIRST BY employee_id SET traversal_order
SELECT employee_id,
       employee_name,
       manager_id,
       hierarchy_level
FROM employee_tree
ORDER BY traversal_order;
```

`SEARCH DEPTH FIRST` tạo thứ tự duyệt theo nhánh; `SEARCH BREADTH FIRST` tạo thứ tự theo từng cấp. Cột được tạo bởi `SET traversal_order` có thể dùng trong ORDER BY của truy vấn ngoài.

### 9.5. CYCLE để phát hiện vòng lặp

Dữ liệu phân cấp có thể lỗi, ví dụ nhân viên A quản lý B và B lại quản lý A. Nếu recursive query không kiểm soát, quá trình mở rộng có thể lặp không mong muốn.

Oracle hỗ trợ mệnh đề `CYCLE` để phát hiện chu kỳ theo một hoặc nhiều cột:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1
    FROM employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
CYCLE employee_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT employee_id,
       employee_name,
       manager_id,
       hierarchy_level,
       cycle_flag
FROM employee_tree;
```

`CYCLE` đánh dấu hàng tham gia chu kỳ theo cột chỉ định và ngăn tiếp tục mở rộng nhánh chu kỳ theo quy tắc Oracle. Chọn cột định danh phù hợp; kiểm tra cả chất lượng dữ liệu đầu vào và constraint của quan hệ cha-con.

### 9.6. Recursive WITH không giống CONNECT BY

Oracle có cú pháp phân cấp truyền thống:

```sql
SELECT employee_id,
       employee_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
```

`CONNECT BY` là cú pháp Oracle chuyên cho truy vấn phân cấp. Recursive WITH là cách biểu diễn bằng CTE có anchor và recursive member, gần với chuẩn SQL hiện đại và có thể kết hợp các CTE khác.

Không cần chuyển mọi truy vấn cây cũ sang recursive WITH. Chọn cách viết phù hợp với phiên bản Oracle, yêu cầu SEARCH/CYCLE, độ dễ đọc và quy ước codebase.

## 10. CTE và DML trong Oracle

Subquery factoring không chỉ hữu ích với SELECT. Oracle hỗ trợ đặt WITH trong nhiều dạng câu lệnh, bao gồm một số dạng INSERT, UPDATE, DELETE và MERGE theo cú pháp của phiên bản.

Ví dụ dùng CTE làm nguồn cho INSERT:

```sql
INSERT INTO high_value_orders (
    order_id,
    customer_id,
    order_total
)
WITH qualifying_orders AS (
    SELECT order_id,
           customer_id,
           order_total
    FROM orders
    WHERE order_total >= 1000000
)
SELECT order_id,
       customer_id,
       order_total
FROM qualifying_orders;
```

CTE `QUALIFYING_ORDERS` đặt tên tập nguồn, SELECT cuối cung cấp các dòng cần chèn. Cú pháp vị trí WITH trong DML phải theo đúng grammar của Oracle release đang sử dụng.

Ví dụ UPDATE dựa trên tập tổng hợp:

```sql
MERGE INTO customers c
USING (
    WITH customer_totals AS (
        SELECT customer_id,
               SUM(order_total) AS total_spent
        FROM orders
        GROUP BY customer_id
    )
    SELECT customer_id, total_spent
    FROM customer_totals
) t
ON (t.customer_id = c.customer_id)
WHEN MATCHED THEN
    UPDATE SET c.total_spent = t.total_spent;
```

Ví dụ trên minh họa một nguồn đã tổng hợp một dòng mỗi customer trước khi MERGE. Khi dùng MERGE thật, phải bảo đảm nguồn không có nhiều dòng khớp cùng một dòng đích; nếu không, Oracle có thể báo lỗi về việc một row đích bị cập nhật nhiều lần.

## 11. CTE có được materialize không?

Đây là điểm rất quan trọng khi đọc về hiệu năng.

Một số người hiểu rằng CTE luôn được tính trước, lưu thành bảng tạm rồi query chính mới đọc. Đây **không phải bảo đảm chung** của mệnh đề WITH trong Oracle.

Oracle optimizer có thể:

- **Inline/merge** query block vào truy vấn ngoài, tương tự biến đổi inline view.
- Đẩy predicate xuống CTE hoặc biến đổi thứ tự JOIN khi tính tương đương.
- Tạo **temporary table transformation** trong một số trường hợp để lưu kết quả trung gian tạm thời.
- Chọn kế hoạch khác dựa trên cost, statistics, số lần tham chiếu và cấu trúc truy vấn.

Vì vậy:

- CTE giúp tổ chức SQL và tái sử dụng logic ở cấp câu lệnh.
- CTE không mặc nhiên là materialized view hoặc temporary table.
- Việc tham chiếu CTE nhiều lần không đảm bảo phép tính vật lý chỉ chạy một lần.
- CTE cũng không tự động nhanh hơn inline view hoặc subquery.

### 11.1. Inline/merge

Khi optimizer inline hoặc merge một CTE, biểu thức của nó có thể được đưa vào query block bên ngoài. Điều này cho phép optimizer phối hợp predicate, JOIN và access path trên toàn câu truy vấn.

Ví dụ:

```sql
WITH active_orders AS (
    SELECT order_id, customer_id, order_total
    FROM orders
    WHERE status = 'ACTIVE'
)
SELECT order_id, order_total
FROM active_orders
WHERE customer_id = :p_customer_id;
```

Optimizer có thể kết hợp điều kiện khách hàng với điều kiện trạng thái khi tối ưu truy vấn.

### 11.2. Temporary table transformation

Trong một số truy vấn, đặc biệt khi một CTE được tham chiếu nhiều lần và phép tính có chi phí, Oracle có thể chọn temporary table transformation. Execution plan có thể hiển thị operation như `TEMP TABLE TRANSFORMATION` và thao tác load/read dữ liệu trung gian.

Đây là quyết định của optimizer theo ngữ cảnh. Không nên suy ra rằng mọi CTE đều tạo một bảng tạm chỉ vì cú pháp có WITH.

### 11.3. Có nên dùng hint MATERIALIZE hoặc INLINE?

Oracle có một số hint thường được nhắc tới trong cộng đồng để tác động xử lý CTE, ví dụ `MATERIALIZE` hoặc `INLINE`. Khả năng hỗ trợ, hành vi và trạng thái tài liệu của hint có thể khác theo release.

Không nên thêm hint chỉ vì nghĩ materialize luôn tốt:

- Materialize có thể tránh tính lại một tập trung gian, nhưng cần tài nguyên và có chi phí ghi/đọc temporary segment.
- Inline có thể giúp predicate pushdown và tối ưu toàn cục, nhưng một số biểu thức có thể bị lặp lại.
- Tác động còn phụ thuộc số hàng, số lần tham chiếu, statistics, PGA/TEMP và concurrent workload.

Hãy đo execution plan và thời gian trên dữ liệu đại diện trước khi áp dụng hint; kiểm tra tài liệu chính thức đúng release. Không coi hint là cam kết vĩnh viễn rằng optimizer sẽ giữ nguyên một kế hoạch trong mọi phiên bản.

## 12. Kiểm tra execution plan của truy vấn có CTE

Có thể xem plan ước tính:

```sql
EXPLAIN PLAN FOR
WITH department_totals AS (
    SELECT department_id,
           SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
)
SELECT d.department_name,
       t.total_salary
FROM department_totals t
JOIN departments d
  ON d.department_id = t.department_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Trong plan, chú ý:

- Query block/operation được optimizer biến đổi như thế nào.
- Có HASH GROUP BY hoặc SORT GROUP BY không.
- Có TEMP TABLE TRANSFORMATION không.
- Có full table scan, index range scan hoặc join method nào.
- Số dòng ước lượng ở các bước trung gian.

`EXPLAIN PLAN` cung cấp plan ước tính, không nhất thiết là plan thực thi thực tế. Nếu có quyền và truy vấn đã chạy với thống kê phù hợp, xem cursor:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

Các thống kê runtime như A-Rows chỉ có khi được thu thập phù hợp, ví dụ bằng cơ chế statistics trong execution. Việc truy cập V$ views hoặc DBMS_XPLAN có thể cần quyền DBA/được cấp trực tiếp.

### 12.1. So sánh CTE với inline view bằng plan

Nếu hai câu SQL diễn đạt cùng logic, Oracle có thể biến đổi chúng thành plan tương đương. Đừng giả định CTE luôn tạo thêm bước thực thi hoặc inline view luôn nhanh hơn.

Khi so sánh:

1. Dùng cùng dữ liệu và cùng bind values.
2. Chạy trong điều kiện cache/workload có thể so sánh.
3. Xem actual rows, buffers và thời gian.
4. Xác nhận kết quả giống nhau.
5. Kiểm tra plan có thay đổi do statistics hoặc session optimizer settings không.

## 13. Lỗi và bẫy thường gặp với WITH

### 13.1. Quên dấu phẩy giữa các CTE

Sai:

```sql
WITH
active_orders AS (
    SELECT order_id FROM orders
)
payment_totals AS (
    SELECT order_id, SUM(paid_amount)
    FROM payments
    GROUP BY order_id
)
SELECT * FROM active_orders;
```

Đúng:

```sql
WITH
active_orders AS (
    SELECT order_id FROM orders
),
payment_totals AS (
    SELECT order_id, SUM(paid_amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT * FROM active_orders;
```

### 13.2. Thiếu alias cho biểu thức

Nếu CTE tạo biểu thức không có tên cột rõ ràng, truy vấn ngoài khó tham chiếu và có thể gặp lỗi khi dùng danh sách alias không phù hợp.

Nên viết:

```sql
WITH employee_metrics AS (
    SELECT employee_id,
           salary * 12 AS annual_salary
    FROM employees
)
SELECT employee_id, annual_salary
FROM employee_metrics;
```

### 13.3. Alias count không khớp số biểu thức

```sql
-- Danh sách alias có 2 tên nhưng SELECT có 3 biểu thức:
WITH x (employee_id, salary) AS (
    SELECT employee_id, salary, department_id
    FROM employees
)
SELECT * FROM x;
```

Số lượng tên cột khai báo phải tương ứng số biểu thức SELECT. Đặt alias đầy đủ hoặc bỏ danh sách alias ngoài nếu đã alias trong SELECT.

### 13.4. CTE không được sử dụng trong query block phù hợp

CTE có scope trong statement chứa WITH. Không thể khai báo CTE trong một câu lệnh rồi gọi tên ở câu SQL kế tiếp như bảng vật lý.

Nếu cần dùng lại ở nhiều statement, tạo view, materialized view, bảng staging hoặc lặp lại định nghĩa theo lựa chọn kiến trúc phù hợp.

### 13.5. JOIN CTE đã tổng hợp với tập chi tiết

Nếu `ITEM_TOTALS` một dòng mỗi order nhưng sau đó JOIN trực tiếp `ORDER_ITEMS`, item_total sẽ lặp trên mỗi item. Nếu lại SUM item_total, tổng có thể bị nhân.

Một measure phải được tổng hợp ở đúng grain và không cộng lại sau khi bị nhân bởi JOIN chi tiết. Nếu đầu ra cần chi tiết, hãy hiển thị measure cha nhưng đừng cộng nó theo số dòng con; nếu cần tổng theo cha, giữ tập kết quả ở grain cha.

### 13.6. CTE có tên không đồng nghĩa dữ liệu không trùng

`SELECT DISTINCT`, `GROUP BY`, khóa duy nhất hoặc logic nguồn mới quyết định tính duy nhất. Tên như `CUSTOMER_TOTALS` không tự đảm bảo một dòng mỗi customer.

Kiểm tra:

```sql
WITH customer_totals AS (
    SELECT customer_id,
           SUM(order_total) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, COUNT(*)
FROM customer_totals
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Kết quả đúng phải rỗng.

### 13.7. Đệ quy không có điều kiện kết thúc hợp lý

Recursive member cần có điều kiện/quan hệ khiến tập kết quả mở rộng có giới hạn. Dữ liệu có cycle hoặc quan hệ sai có thể tạo kết quả không mong muốn.

Dùng `CYCLE` khi phù hợp, kiểm soát khóa cha-con, xác định anchor chính xác và thử trên dữ liệu có nhánh sâu, nhánh rỗng, root nhiều cấp và dữ liệu lỗi.

## 14. Thiết kế CTE dễ bảo trì

Một truy vấn WITH tốt thường có các đặc điểm:

1. Tên CTE nói rõ vai trò hoặc grain.
2. Mỗi CTE có một nhiệm vụ chính, không gom quá nhiều logic không liên quan.
3. Alias cột rõ ràng, nhất quán.
4. Các bảng con được tổng hợp về grain cần thiết trước khi JOIN.
5. Điều kiện lọc được đặt ở bước phù hợp, không làm thay đổi ngoài ý muốn semantics của outer join.
6. Query cuối chỉ tập trung trình bày kết quả hoặc thực hiện bước tổng hợp cuối.
7. Không tạo quá nhiều CTE nhỏ chỉ để chia từng phép toán đơn giản.
8. Được kiểm chứng kết quả và execution plan trên dữ liệu đại diện.

Ví dụ bố cục:

```sql
WITH
source_rows AS (
    -- Lấy dữ liệu nguồn và lọc phạm vi
),
detail_metrics AS (
    -- Tổng hợp bảng chi tiết về grain mục tiêu
),
dimension_data AS (
    -- Chọn các thuộc tính mô tả cần thiết
),
final_result AS (
    -- Kết hợp các tập dữ liệu đã chuẩn hóa grain
)
SELECT ...
FROM final_result;
```

Đây là mẫu tổ chức, không phải yêu cầu bắt buộc phải tạo đúng bốn CTE cho mọi truy vấn.

## 15. Bài thực hành tổng hợp

Các ví dụ sử dụng schema mẫu Oracle phổ biến hoặc bảng lab riêng. Chỉ chạy DDL/DML trên schema mà bạn được phép sử dụng.

### Bài 1 — CTE cơ bản

Tạo CTE `high_salary_employees` chọn nhân viên có salary từ 8.000 trở lên. Truy vấn ngoài chỉ hiển thị employee_id, tên, salary và sắp xếp giảm dần.

Yêu cầu:

- Viết định nghĩa CTE.
- Đặt alias cho biểu thức ghép tên nếu cần.
- Thử thay giá trị lọc bằng bind variable.
- Giải thích scope của CTE.

### Bài 2 — Nhiều CTE phụ thuộc

Tạo ba CTE:

- `orders_in_period` lọc đơn trong một khoảng ngày.
- `item_totals` tính tổng item theo order.
- `customer_summary` tính số đơn và tổng item theo customer.

Kết quả cần một dòng mỗi customer. Xác nhận `item_totals` có tối đa một dòng mỗi order trước khi JOIN.

### Bài 3 — Tái sử dụng một CTE

Tạo CTE `department_totals` tính tổng lương theo phòng ban. Dùng CTE đó:

- Trong query chính để hiển thị tổng lương.
- Trong scalar subquery để lấy trung bình tổng lương các phòng ban.
- Trong điều kiện lọc các phòng ban cao hơn trung bình.

Giải thích vì sao một tên CTE có thể được tham chiếu nhiều lần trong cùng statement.

### Bài 4 — CTE và fanout

Một order có ba item và hai payment. Viết truy vấn JOIN trực tiếp để quan sát sáu dòng tổ hợp. Sau đó viết hai CTE tổng hợp riêng theo order và JOIN lại. So sánh tổng item và payment.

### Bài 5 — EXISTS trong CTE

Tạo CTE khách hàng có ít nhất một đơn hàng trong năm. Dùng EXISTS thay cho JOIN. Giải thích vì sao mỗi customer chỉ xuất hiện một lần khi bảng nguồn là CUSTOMERS và điều kiện EXISTS không nhân dòng.

### Bài 6 — Analytic function trong CTE

Tạo CTE tính ROW_NUMBER theo department_id, sắp salary giảm dần và employee_id tăng dần. Truy vấn ngoài lấy tối đa ba nhân viên mỗi phòng ban. Giải thích vì sao analytic alias được lọc ở query block ngoài.

### Bài 7 — Recursive WITH

Dùng bảng employee có manager_id để:

- Bắt đầu từ nhân viên gốc.
- Tìm toàn bộ cấp dưới.
- Tạo hierarchy_level.
- Sắp theo depth-first bằng SEARCH.
- Thử dữ liệu có chu kỳ và tìm hiểu CYCLE.

Đối chiếu kết quả với cú pháp START WITH/CONNECT BY.

### Bài 8 — Đánh giá materialization

Viết một CTE được tham chiếu hai lần. Xem execution plan để tìm xem optimizer inline hay dùng temporary table transformation. Thử một phiên bản inline view tương đương, so sánh kết quả và runtime statistics. Không kết luận chỉ từ số dòng SQL hoặc số CTE.

## 16. Quy trình kiểm chứng truy vấn có WITH

Trước khi đưa truy vấn vào ứng dụng:

1. **Xác định đầu ra cần một dòng cho mỗi đối tượng nào.**
2. **Ghi grain của từng CTE**: một dòng mỗi order, item, customer, tháng hay node cây.
3. **Kiểm tra CTE phụ thuộc đúng thứ tự** và alias cột không mơ hồ.
4. **Chạy riêng SELECT của từng CTE** để kiểm tra dữ liệu đầu ra.
5. **Đếm dòng và khóa khác nhau** để xác nhận cardinality.
6. **Kiểm tra JOIN giữa các CTE** có tạo fanout hay làm mất dòng cha không.
7. **Đối chiếu aggregate với truy vấn nguồn độc lập.**
8. **Kiểm tra NULL và trường hợp không có dữ liệu liên quan.**
9. **Nếu đệ quy**, kiểm tra root, nhánh sâu, nhánh rỗng và cycle.
10. **Xem execution plan/actual rows** để đánh giá hiệu năng và cách optimizer xử lý CTE.
11. **Chỉ thêm hint khi có bằng chứng** và đã kiểm tra release Oracle.
12. **Nếu cần dùng logic ở nhiều statement**, đánh giá view hoặc materialized view thay vì kỳ vọng CTE sống ngoài statement.

## 17. Sơ đồ lựa chọn CTE, inline view, view và bảng tạm

```text
Cần tổ chức một truy vấn SQL?
|
+-- Query block nhỏ, chỉ dùng một lần trong FROM?
|      └── Inline view
|
+-- Nhiều bước hoặc cần tham chiếu nhiều lần trong cùng statement?
|      └── WITH / CTE
|
+-- Nhiều statement hoặc nhiều ứng dụng cần dùng chung logic?
|      └── VIEW
|
+-- Cần lưu kết quả tính toán để tái sử dụng và có lịch refresh?
|      └── MATERIALIZED VIEW
|
+-- Cần nạp dữ liệu trung gian theo session/transaction?
|      └── GLOBAL TEMPORARY TABLE hoặc staging table
|
+-- Cần duyệt cấu trúc cha-con/cây?
       └── Recursive WITH hoặc CONNECT BY
```

## 18. Ghi nhớ cốt lõi

- **WITH** đặt tên cho query block trong phạm vi một statement.
- **CTE** giúp chia truy vấn phức tạp thành bước có ý nghĩa và có thể tham chiếu lại trong cùng câu lệnh.
- **CTE không phải bảng vật lý, view hoặc materialized view**; nó không tự tồn tại sau statement.
- CTE sau có thể tham chiếu CTE được khai báo trước; tránh phụ thuộc vòng ngoài cấu trúc recursive.
- **CTE không tự đảm bảo một dòng mỗi khóa**; grain do SELECT, GROUP BY, DISTINCT và constraint quyết định.
- Khi JOIN nhiều bảng con độc lập, hãy pre-aggregate mỗi bảng về grain chung trước khi kết hợp measure.
- **EXISTS/NOT EXISTS** thích hợp khi chỉ cần kiểm tra có/không có dòng liên quan.
- **Recursive WITH** có anchor member và recursive member; SEARCH/CYCLE hỗ trợ thứ tự duyệt và kiểm soát chu kỳ.
- Oracle optimizer có thể inline/merge hoặc dùng temporary table transformation; WITH không bảo đảm materialization hay tăng tốc.
- Dùng execution plan và actual runtime statistics để đánh giá; không suy luận hiệu năng chỉ từ cách viết.
- Nếu logic cần dùng giữa nhiều statement, cân nhắc VIEW, materialized view hoặc bảng staging.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SELECT, subquery factoring clause, recursive subquery factoring, SEARCH và CYCLE.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/) — query transformations, view merging, optimizer và execution plans.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — query blocks, joins, views và materialized views.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — aggregation, query rewrite và materialized views.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — runtime plan statistics, cardinality và temporary space.

Cú pháp chi tiết và các phép biến đổi optimizer có thể khác theo Oracle release. Khi triển khai, đối chiếu đúng phiên bản đang dùng; điều quan trọng là CTE phải làm rõ grain và quan hệ dữ liệu, còn hiệu năng phải được xác nhận bằng execution plan và phép đo thực tế.

