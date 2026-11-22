# Đối chiếu số hàng trước và sau mỗi JOIN

Một truy vấn có thể trả về nhiều hàng hơn dự kiến dù không có bản ghi nào bị nhân bản trong bảng gốc. Nguyên nhân thường là một JOIN khớp một hàng bên trái với nhiều hàng bên phải. Ngược lại, INNER JOIN có thể loại những hàng không tìm được đối tác. Nếu chỉ nhìn số hàng cuối cùng, rất khó biết sự thay đổi bắt đầu ở JOIN nào.

Khi kiểm thử và gỡ lỗi SQL, hãy coi mỗi JOIN là một bước biến đổi tập dữ liệu. Trước khi thêm JOIN, ghi nhận số hàng và khóa của tập đầu vào. Sau JOIN, ghi nhận số hàng, số khóa phân biệt, số hàng không khớp và số lần một khóa xuất hiện. Lặp lại việc này cho từng JOIN giúp xác định chính xác chỗ mất hàng hoặc phát sinh nhân bản.

Ví dụ bảng khách hàng có 4 hàng, bảng đơn hàng có 5 hàng. Khi nối khách hàng với đơn hàng, INNER JOIN có thể trả 5 hàng và LEFT JOIN có thể trả 7 hàng. Con số 7 không nhất thiết là lỗi: khách hàng có nhiều đơn tạo nhiều hàng kết quả, còn khách hàng chưa có đơn vẫn xuất hiện một lần.

Bài học thuộc module **Database SQL**, chương **Kiểm thử và gỡ lỗi**, chủ đề **“Đối chiếu số hàng trước và sau mỗi JOIN”**. Trọng tâm là kiểm tra cardinality, phát hiện fan-out, xác định hàng bị loại và bảo vệ tính đúng đắn của báo cáo.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đo số hàng và số khóa phân biệt trước/sau từng JOIN.
2. Giải thích vì sao INNER JOIN có thể giảm hoặc tăng số hàng.
3. Phân biệt quan hệ 1:1, 1:N và N:M qua khóa tham gia JOIN.
4. Phát hiện duplicate key ở bảng bên phải gây fan-out.
5. Kiểm tra hàng không có đối tác bằng LEFT JOIN, NOT EXISTS và anti-join.
6. Phân biệt COUNT(*), COUNT(column) và COUNT(DISTINCT key).
7. Hiểu tác động của NULL, điều kiện ON, WHERE và bộ lọc sau JOIN.
8. Phát hiện tổng tiền hoặc COUNT bị phóng đại do JOIN một-nhiều.
9. Dùng CTE để chia truy vấn thành từng stage có thể kiểm tra.
10. Xác minh khóa, constraint và index có thực sự phản ánh quan hệ dữ liệu.
11. Kết hợp row-count diagnostics với execution plan và dữ liệu kiểm thử.
12. Xây dựng kiểm thử hồi quy cho truy vấn nhiều JOIN.

## 2. Vì sao phải đối chiếu sau từng JOIN?

Giả sử truy vấn gồm bốn bảng:

~~~sql
SELECT
    c.id,
    o.id,
    oi.id,
    p.name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id
JOIN products AS p
    ON p.id = oi.product_id;
~~~

Nếu kết quả thiếu khách hàng, có thể do:

- Khách hàng không có đơn nên bị INNER JOIN loại.
- Đơn hàng không có dòng chi tiết nên bị JOIN tiếp theo loại.
- Dòng chi tiết tham chiếu product không tồn tại.
- Điều kiện JOIN sai cột hoặc sai kiểu.
- WHERE lọc mất hàng sau khi JOIN.
- Dữ liệu có NULL hoặc khóa không đồng nhất.
- Một JOIN trước đó đã nhân hàng, làm số đếm và aggregate thay đổi.

Nếu kết quả có quá nhiều hàng, có thể do:

- Cột JOIN ở phía bên phải không duy nhất.
- JOIN thiếu một phần của khóa ghép.
- JOIN hai bảng chi tiết độc lập cùng cấp, tạo tích nhân.
- Điều kiện nối quá rộng hoặc nối nhầm cột.
- Bảng bridge có nhiều quan hệ hợp lệ nhưng truy vấn đang đếm entity như thể mỗi entity chỉ có một hàng.

**Nguyên tắc:** không chỉ so sánh tổng số hàng. Hãy so sánh cả khóa định danh của entity mà truy vấn muốn đại diện.

## 3. Bộ dữ liệu mẫu để thực hành

Các ví dụ dùng PostgreSQL làm cú pháp minh họa; phần lớn câu lệnh kiểm tra cũng dùng được trên DBMS phổ biến sau khi điều chỉnh cú pháp riêng.

### 3.1. Tạo bảng

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    amount NUMERIC(12,2) NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
~~~

### 3.2. Dữ liệu mẫu

~~~sql
INSERT INTO customers (id, name) VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO orders (id, customer_id, status, amount) VALUES
    (101, 1, 'PAID', 100000),
    (102, 1, 'NEW',   50000),
    (103, 2, 'PAID', 200000),
    (104, 2, 'NEW',   70000),
    (105, 2, 'PAID',  30000);

INSERT INTO products (id, name) VALUES
    (10, 'Keyboard'),
    (11, 'Mouse'),
    (12, 'Monitor');

INSERT INTO order_items
    (id, order_id, product_id, quantity, unit_price)
VALUES
    (201, 101, 10, 1, 100000),
    (202, 101, 11, 2,  20000),
    (203, 102, 11, 1,  25000),
    (204, 103, 12, 1, 200000),
    (205, 103, 10, 1, 100000),
    (206, 103, 11, 1,  20000),
    (207, 105, 10, 1,  30000);
~~~

Dữ liệu có:

- 4 khách hàng.
- 5 đơn hàng: khách hàng 1 có 2 đơn, khách hàng 2 có 3 đơn, khách hàng 3 và 4 chưa có đơn.
- 7 dòng chi tiết: đơn 101 có 2 dòng, 102 có 1, 103 có 3, 104 không có dòng, 105 có 1.
- 3 sản phẩm; sản phẩm có thể xuất hiện trong nhiều dòng chi tiết.

### 3.3. Baseline trước JOIN

~~~sql
SELECT COUNT(*) AS customer_rows FROM customers;
SELECT COUNT(*) AS order_rows FROM orders;
SELECT COUNT(*) AS item_rows FROM order_items;
SELECT COUNT(*) AS product_rows FROM products;
~~~

| Bảng | COUNT(*) |
|---|---:|
| customers | 4 |
| orders | 5 |
| order_items | 7 |
| products | 3 |

Baseline là mốc đối chiếu. Nếu dữ liệu thay đổi trong lúc kiểm tra, các lần đếm ở statement khác nhau có thể nhìn thấy snapshot khác nhau tùy isolation level. Với kiểm thử cần tính nhất quán, dùng transaction/snapshot phù hợp hoặc fixture không bị tiến trình khác thay đổi.

## 4. Đếm hàng và đếm entity là hai việc khác nhau

~~~sql
SELECT
    c.id AS customer_id,
    o.id AS order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Kết quả có 5 hàng vì có 5 đơn, nhưng chỉ có 2 khách hàng xuất hiện.

~~~sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT c.id) AS distinct_customers,
    COUNT(DISTINCT o.id) AS distinct_orders
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

| joined_rows | distinct_customers | distinct_orders |
|---:|---:|---:|
| 5 | 2 | 5 |

Nếu mục tiêu là đếm khách hàng có đơn, dùng COUNT(DISTINCT c.id). Nếu mục tiêu là đếm hàng kết quả, dùng COUNT(*). Không thay hai đại lượng cho nhau.

### 4.1. Xác định grain của truy vấn

*Grain* là ý nghĩa của một hàng kết quả: một hàng đại diện cho điều gì?

Ví dụ:

- Một hàng cho mỗi customer.
- Một hàng cho mỗi order.
- Một hàng cho mỗi order item.
- Một hàng cho mỗi cặp customer-product.
- Một hàng cho mỗi customer trong mỗi tháng.

Trước khi JOIN, hãy viết rõ grain mong muốn. Sau mỗi JOIN, hỏi grain có thay đổi không. Nếu query cần một hàng mỗi order nhưng JOIN sang order_items, grain thường chuyển thành một hàng mỗi item.

## 5. Công thức cardinality cơ bản

Giả sử quan hệ trái có N hàng. Với mỗi hàng trái i, gọi mᵢ là số hàng bên phải khớp điều kiện JOIN.

### 5.1. INNER JOIN

Số hàng kết quả:

\[
R_{inner} = \sum_{i=1}^{N} m_i
\]

Hàng trái có 0 match bị loại. Hàng trái có 1 match đóng góp 1 hàng. Hàng trái có 3 match đóng góp 3 hàng.

Vì mᵢ có thể bằng 0, 1 hoặc lớn hơn 1, INNER JOIN có thể giảm, giữ nguyên hoặc tăng số hàng so với bảng trái.

### 5.2. LEFT JOIN

Số hàng kết quả:

\[
R_{left} = \sum_{i=1}^{N} \max(1,m_i)
\]

Mỗi hàng trái xuất hiện ít nhất một lần. Nếu không có match, các cột phía phải là NULL. Nếu có nhiều match, hàng trái được lặp theo số match.

Do đó, LEFT JOIN không đảm bảo số hàng bằng số hàng trái. Nó chỉ bảo đảm mỗi hàng trái được đại diện ít nhất một lần.

### 5.3. RIGHT JOIN

Tương tự LEFT JOIN nhưng bảo toàn các hàng bên phải. Trong truy vấn nhiều bảng, thường có thể đổi thứ tự bảng và dùng LEFT JOIN để diễn đạt rõ hơn.

### 5.4. FULL OUTER JOIN

FULL OUTER JOIN giữ các hàng khớp và cả hàng không khớp ở hai phía. Số hàng gồm:

- Các tổ hợp match, có thể nhiều hàng nếu khóa trùng.
- Mỗi hàng trái không có match được giữ một lần.
- Mỗi hàng phải không có match được giữ một lần.

Không thể chỉ lấy số hàng lớn hơn giữa hai bảng để suy ra số hàng FULL JOIN.

### 5.5. CROSS JOIN

Nếu trái có L hàng và phải có R hàng:

\[
R_{cross} = L \times R
\]

CROSS JOIN tạo mọi cặp. Đây là tích Descartes; đôi khi có chủ đích (calendar × dimension), nhưng cũng là dấu hiệu thường gặp khi thiếu điều kiện JOIN.

## 6. Cardinality của ví dụ customers → orders

### 6.1. INNER JOIN

~~~sql
SELECT
    c.id AS customer_id,
    o.id AS order_id
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.id
ORDER BY c.id, o.id;
~~~

| customer_id | order_id |
|---:|---:|
| 1 | 101 |
| 1 | 102 |
| 2 | 103 |
| 2 | 104 |
| 2 | 105 |

Có 5 hàng, 2 customer distinct và 5 order distinct.

- Customers đầu vào: 4.
- INNER JOIN output: 5.
- Khách hàng bị loại: 3 và 4.
- Hàng tăng từ 4 lên 5 do khách hàng 1 và 2 có nhiều đơn.

Đây không phải lỗi. Grain của kết quả là một hàng cho mỗi order.

### 6.2. LEFT JOIN

~~~sql
SELECT
    c.id AS customer_id,
    o.id AS order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
ORDER BY c.id, o.id;
~~~

| customer_id | order_id |
|---:|---:|
| 1 | 101 |
| 1 | 102 |
| 2 | 103 |
| 2 | 104 |
| 2 | 105 |
| 3 | NULL |
| 4 | NULL |

Có 7 hàng: 5 hàng match và 2 hàng giữ lại cho khách chưa có đơn. Số hàng lớn hơn 4 vì quan hệ một-nhiều. Số khách hàng distinct vẫn là 4.

### 6.3. Đếm khách không có đơn

Cách 1 — LEFT JOIN và kiểm tra khóa bên phải:

~~~sql
SELECT c.id, c.name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
WHERE o.id IS NULL;
~~~

Cách 2 — NOT EXISTS:

~~~sql
SELECT c.id, c.name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
~~~

Cả hai trả khách hàng 3 và 4. NOT EXISTS thường diễn đạt trực tiếp câu hỏi “không có hàng liên quan” và tránh nhân bản hàng trái do nhiều match.

## 7. Đối chiếu trước và sau từng JOIN

Không nên gộp toàn bộ truy vấn thành một câu dài ngay khi đang chẩn đoán. Hãy chạy từng stage.

### 7.1. Stage 0 — bảng gốc

~~~sql
SELECT COUNT(*) AS rows_before
FROM customers;
~~~

Kết quả: 4.

### 7.2. Stage 1 — sau JOIN orders

~~~sql
SELECT COUNT(*) AS rows_after_orders
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Kết quả: 5.

Kiểm tra grain:

~~~sql
SELECT
    COUNT(*) AS rows_after_orders,
    COUNT(DISTINCT c.id) AS customer_count,
    COUNT(DISTINCT o.id) AS order_count
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

### 7.3. Stage 2 — sau JOIN order_items

~~~sql
SELECT COUNT(*) AS rows_after_items
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id;
~~~

Kết quả: 7 hàng. Đơn 104 không có item nên bị loại bởi INNER JOIN.

### 7.4. Stage 3 — sau JOIN products

~~~sql
SELECT COUNT(*) AS rows_after_products
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id
JOIN products AS p
    ON p.id = oi.product_id;
~~~

Kết quả vẫn là 7 vì mọi product_id trong item đều match đúng một product.

### 7.5. Bảng đối chiếu

| Stage | Phép biến đổi | Số hàng |
|---|---|---:|
| 0 | customers | 4 |
| 1 | customers INNER JOIN orders | 5 |
| 2 | thêm INNER JOIN order_items | 7 |
| 3 | thêm INNER JOIN products | 7 |

Nếu truy vấn thực tế có 70.000 hàng ở stage 2 trong khi mong đợi 7, hãy điều tra quan hệ orders → order_items trước khi xem JOIN products. Stage nơi số hàng đổi bất thường thường khoanh vùng được nguyên nhân.

### 7.6. Dùng CTE để đo từng stage trong một statement

~~~sql
WITH
base_customers AS (
    SELECT id
    FROM customers
),
after_orders AS (
    SELECT c.id AS customer_id, o.id AS order_id
    FROM base_customers AS c
    JOIN orders AS o ON o.customer_id = c.id
),
after_items AS (
    SELECT
        ao.customer_id,
        ao.order_id,
        oi.id AS item_id,
        oi.product_id
    FROM after_orders AS ao
    JOIN order_items AS oi ON oi.order_id = ao.order_id
),
after_products AS (
    SELECT ai.customer_id, ai.order_id, ai.item_id, p.id AS product_id
    FROM after_items AS ai
    JOIN products AS p ON p.id = ai.product_id
)
SELECT '0 customers' AS stage, COUNT(*) AS row_count FROM base_customers
UNION ALL
SELECT '1 orders', COUNT(*) FROM after_orders
UNION ALL
SELECT '2 items', COUNT(*) FROM after_items
UNION ALL
SELECT '3 products', COUNT(*) FROM after_products;
~~~

Kết quả lần lượt là 4, 5, 7, 7. CTE giúp đặt tên cho từng phép biến đổi. Optimizer vẫn có thể inline hoặc materialize CTE tùy DBMS; mục đích ở đây là tổ chức logic và đối chiếu, không giả định mỗi CTE là bảng vật lý.

## 8. Đo số match trên từng khóa

Tổng số hàng cho biết kích thước, nhưng chưa nói khóa nào gây nhân bản. Hãy đếm số hàng bên phải cho mỗi khóa bên trái.

~~~sql
SELECT
    c.id AS customer_id,
    COUNT(o.id) AS matching_orders
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
GROUP BY c.id
ORDER BY c.id;
~~~

| customer_id | matching_orders |
|---:|---:|
| 1 | 2 |
| 2 | 3 |
| 3 | 0 |
| 4 | 0 |

Đây là chẩn đoán cardinality trực tiếp:

- 0: không có match.
- 1: một match.
- Lớn hơn 1: quan hệ một-nhiều hoặc duplicate key tùy grain mong muốn.

### 8.1. Tìm khóa có nhiều hơn một match

~~~sql
SELECT
    customer_id,
    COUNT(*) AS matching_rows
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Kết quả cho biết khách hàng 1 và 2 có nhiều đơn. Đây có thể là quan hệ đúng theo mô hình dữ liệu.

Nếu query kỳ vọng mỗi customer chỉ có tối đa một order, kết quả này chứng minh giả định sai hoặc dữ liệu vi phạm quy tắc nghiệp vụ.

### 8.2. Kiểm tra uniqueness phía phải

Nếu JOIN dự kiến nhiều nhất một hàng bên phải cho mỗi khóa:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS key_count
FROM customer_profile
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả hàng, customer_id không duy nhất. Một JOIN theo customer_id có thể nhân hàng.

Để đảm bảo điều kiện ở mức database, dùng UNIQUE constraint/index nếu nghiệp vụ yêu cầu:

~~~sql
ALTER TABLE customer_profile
ADD CONSTRAINT uq_customer_profile_customer
UNIQUE (customer_id);
~~~

Chỉ thêm constraint sau khi xử lý duplicate hiện có và xác nhận quy tắc nghiệp vụ. Index thường không đồng nghĩa với unique index.

## 9. Phân biệt 1:1, 1:N và N:M

### 9.1. Một-một (1:1)

Ví dụ customer và profile, nếu profile.customer_id có UNIQUE:

~~~sql
SELECT c.id, cp.id
FROM customers AS c
LEFT JOIN customer_profile AS cp
    ON cp.customer_id = c.id;
~~~

Mỗi customer có tối đa một profile. LEFT JOIN không làm tăng số hàng so với customers, mặc dù có thể có cột profile NULL.

### 9.2. Một-nhiều (1:N)

Customer có nhiều orders:

~~~text
customers.id = orders.customer_id
~~~

Mỗi customer có thể tạo nhiều hàng kết quả. Đây là nguyên nhân phổ biến làm COUNT(customer) hoặc SUM(customer-level amount) bị lặp.

### 9.3. Nhiều-nhiều (N:M)

Ví dụ students và courses qua enrollment:

~~~text
students 1 ─── N enrollments N ─── 1 courses
~~~

Một student đăng ký nhiều course; một course có nhiều student. Khi JOIN qua bridge table, số hàng biểu diễn **cặp student-course**, không còn là số student hay số course.

~~~sql
SELECT
    s.id AS student_id,
    c.id AS course_id
FROM students AS s
JOIN enrollments AS e
    ON e.student_id = s.id
JOIN courses AS c
    ON c.id = e.course_id;
~~~

Nếu cần đếm student, dùng COUNT(DISTINCT s.id); nếu cần đếm lượt đăng ký, dùng COUNT(*) hoặc COUNT(e.id), tùy cấu trúc.

### 9.4. Thiếu một phần khóa ghép

Giả sử order_items có khóa ghép logic (order_id, line_no), còn shipment_lines cũng dùng hai cột đó. JOIN chỉ theo order_id có thể nối mọi dòng của đơn với mọi shipment line của đơn.

Sai:

~~~sql
ON oi.order_id = sl.order_id
~~~

Đúng nếu nghiệp vụ cần match đúng dòng:

~~~sql
ON oi.order_id = sl.order_id
AND oi.line_no = sl.line_no
~~~

Nếu mỗi đơn có 4 item và 3 shipment line, JOIN thiếu line_no có thể tạo 12 cặp thay vì 3 cặp mong muốn.

## 10. Phát hiện fan-out do duplicate key

Fan-out là hiện tượng một hàng đầu vào tạo ra nhiều hàng kết quả do nhiều hàng bên phải cùng khớp.

Giả sử có bảng:

~~~sql
CREATE TABLE customer_tags (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    tag VARCHAR(30) NOT NULL
);
~~~

Một khách có thể có nhiều tag. JOIN customers → customer_tags làm tăng hàng theo số tag. Đây là đúng nếu query cần mỗi customer-tag pair.

Nhưng nếu bảng customer_profile vốn được kỳ vọng một hàng/customer mà lại có nhiều dòng, đó là duplicate gây lỗi.

### 10.1. Đếm duplicate key

~~~sql
SELECT
    customer_id,
    COUNT(*) AS duplicate_count
FROM customer_profile
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

### 10.2. Xem chi tiết các hàng duplicate

~~~sql
WITH duplicate_keys AS (
    SELECT customer_id
    FROM customer_profile
    GROUP BY customer_id
    HAVING COUNT(*) > 1
)
SELECT cp.*
FROM customer_profile AS cp
JOIN duplicate_keys AS d
    ON d.customer_id = cp.customer_id
ORDER BY cp.customer_id, cp.id;
~~~

Đừng vội dùng DISTINCT để che duplicate. Hãy tìm nguồn tạo duplicate: import lặp, thiếu UNIQUE, join sai, lịch sử nhiều phiên bản hoặc dữ liệu cần chọn bản ghi hiện hành.

### 10.3. Chọn một bản ghi theo quy tắc nghiệp vụ

Nếu bảng lưu lịch sử profile và chỉ cần phiên bản mới nhất, dùng window function:

~~~sql
WITH ranked_profiles AS (
    SELECT
        cp.*,
        ROW_NUMBER() OVER (
            PARTITION BY cp.customer_id
            ORDER BY cp.updated_at DESC, cp.id DESC
        ) AS rn
    FROM customer_profile AS cp
)
SELECT *
FROM ranked_profiles
WHERE rn = 1;
~~~

Phải xác định tie-breaker ổn định. Chọn một hàng tùy tiện bằng MIN(id) hoặc MAX(id) không phải lúc nào cũng đồng nghĩa với “bản ghi đúng”.

## 11. Phân biệt hàng bị mất và hàng bị nhân

Với LEFT JOIN, có thể đếm số hàng match và không match:

~~~sql
SELECT
    COUNT(*) AS output_rows,
    COUNT(o.id) AS matched_order_rows,
    SUM(CASE WHEN o.id IS NULL THEN 1 ELSE 0 END)
        AS unmatched_customer_rows
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id;
~~~

| output_rows | matched_order_rows | unmatched_customer_rows |
|---:|---:|---:|
| 7 | 5 | 2 |

Lưu ý: unmatched_customer_rows ở đây là số hàng output không match. Nếu bảng trái đã bị lặp từ một stage trước, phép đếm này có thể đếm cùng entity nhiều lần. Khi cần số entity, hãy tính trên khóa trái distinct hoặc kiểm tra từ bảng gốc.

### 11.1. Tìm hàng trái không có match

~~~sql
SELECT c.id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
~~~

### 11.2. Tìm hàng phải mồ côi

Nếu không có foreign key hoặc cần kiểm tra dữ liệu import:

~~~sql
SELECT o.id, o.customer_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM customers AS c
    WHERE c.id = o.customer_id
);
~~~

Foreign key được enforce sẽ ngăn nhiều trường hợp orphan, nhưng dữ liệu legacy, constraint chưa validate, import ngoài luồng hoặc schema không có FK vẫn có thể có orphan.

### 11.3. Kiểm tra FULL OUTER JOIN

Khi cần đối chiếu hai tập dữ liệu:

~~~sql
SELECT
    a.id AS left_id,
    b.id AS right_id,
    CASE
        WHEN a.id IS NULL THEN 'RIGHT_ONLY'
        WHEN b.id IS NULL THEN 'LEFT_ONLY'
        ELSE 'MATCHED'
    END AS match_status
FROM source_a AS a
FULL OUTER JOIN source_b AS b
    ON b.id = a.id;
~~~

Đếm từng loại:

~~~sql
SELECT
    SUM(CASE WHEN a.id IS NOT NULL AND b.id IS NOT NULL
             THEN 1 ELSE 0 END) AS matched_rows,
    SUM(CASE WHEN a.id IS NOT NULL AND b.id IS NULL
             THEN 1 ELSE 0 END) AS left_only_rows,
    SUM(CASE WHEN a.id IS NULL AND b.id IS NOT NULL
             THEN 1 ELSE 0 END) AS right_only_rows
FROM source_a AS a
FULL OUTER JOIN source_b AS b
    ON b.id = a.id;
~~~

Nếu DBMS không hỗ trợ FULL OUTER JOIN, có thể kết hợp LEFT JOIN hai chiều bằng UNION ALL; cần loại đúng các hàng đã match để không đếm trùng.

## 12. COUNT(*), COUNT(column) và COUNT(DISTINCT)

Đây là ba phép đếm khác nhau.

### 12.1. COUNT(*)

Đếm mọi hàng kết quả, kể cả hàng có các cột NULL do outer join:

~~~sql
SELECT COUNT(*)
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Với ví dụ, kết quả là 7.

### 12.2. COUNT(column)

Đếm số hàng mà biểu thức/cột không NULL:

~~~sql
SELECT
    COUNT(*) AS output_rows,
    COUNT(o.id) AS rows_with_order
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Kết quả 7 và 5. Dùng cột khóa chính bên phải để đếm match; đừng dùng cột nghiệp vụ nullable vì một hàng match vẫn có thể có cột đó NULL.

### 12.3. COUNT(DISTINCT key)

Đếm số giá trị khóa khác nhau:

~~~sql
SELECT
    COUNT(DISTINCT c.id) AS customer_count,
    COUNT(DISTINCT o.id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Kết quả 4 và 5.

### 12.4. COUNT(DISTINCT) không phải thuốc chữa JOIN sai

Nếu query tạo ra 100 hàng do join sai, COUNT(DISTINCT customer_id) có thể vẫn trả 4. Điều đó không làm những cột khác trong kết quả trở nên đúng.

DISTINCT chỉ thay đổi phép đếm hoặc loại duplicate output theo các cột được chọn. Nó không sửa điều kiện JOIN sai và không khôi phục grain mong muốn.

### 12.5. Composite key

Nếu khóa gồm nhiều cột, cú pháp COUNT(DISTINCT col1, col2) khác nhau giữa DBMS. Cách dễ hiểu và portable hơn là distinct trong subquery:

~~~sql
SELECT COUNT(*) AS distinct_pairs
FROM (
    SELECT DISTINCT tenant_id, external_id
    FROM imported_records
) AS pairs;
~~~

## 13. ON và WHERE: bẫy phổ biến với OUTER JOIN

Xét mục tiêu: lấy mọi khách hàng và chỉ nối đơn hàng PAID nếu có.

### 13.1. Điều kiện ở ON

~~~sql
SELECT c.id, o.id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
   AND o.status = 'PAID';
~~~

Khách chưa có đơn PAID vẫn xuất hiện, cột orders là NULL.

### 13.2. Điều kiện ở WHERE

~~~sql
SELECT c.id, o.id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
WHERE o.status = 'PAID';
~~~

Điều kiện WHERE loại hàng mà o.status là NULL. Kết quả thực tế không còn giữ các khách không có đơn PAID; query có hành vi gần INNER JOIN cho điều kiện đó.

### 13.3. Cách hiểu

- ON xác định hàng nào được coi là match trong phép JOIN.
- WHERE lọc hàng sau khi quan hệ JOIN được hình thành.
- Với INNER JOIN, nhiều predicate có thể chuyển giữa ON và WHERE mà giữ kết quả logic.
- Với OUTER JOIN, di chuyển predicate có thể thay đổi hàng được bảo toàn.

Khi số hàng thay đổi bất ngờ sau khi thêm điều kiện, kiểm tra predicate có nằm đúng vị trí không.

### 13.4. Dùng CTE lọc trước

~~~sql
WITH paid_orders AS (
    SELECT id, customer_id, amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT c.id, po.id
FROM customers AS c
LEFT JOIN paid_orders AS po
    ON po.customer_id = c.id;
~~~

Cách này làm rõ tập phải nối, đồng thời vẫn giữ khách không có đơn PAID.

## 14. NULL trong điều kiện JOIN

Với phép so sánh bằng thông thường:

~~~sql
ON a.external_id = b.external_id
~~~

NULL không bằng NULL. Nếu cả hai phía đều NULL, điều kiện không TRUE nên không được coi là match.

### 14.1. Đếm khóa NULL trước JOIN

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN external_id IS NULL THEN 1 ELSE 0 END)
        AS null_key_rows
FROM source_a;
~~~

Làm tương tự cho bảng bên phải.

### 14.2. NULL có phải cùng một khóa không?

Thông thường NULL biểu thị thiếu/không xác định, không phải một giá trị định danh chung. Nếu hai NULL cùng được nối với nhau bằng điều kiện NULL-safe, nhiều hàng NULL có thể tạo fan-out lớn.

PostgreSQL có:

~~~sql
ON a.external_id IS NOT DISTINCT FROM b.external_id
~~~

MySQL có toán tử NULL-safe equality `<=>`. Với SQL portable rộng, hãy xác định rõ nghiệp vụ thay vì tự động coi hai khóa NULL là bằng nhau.

### 14.3. NULL ở foreign key

Foreign key nullable thường cho phép hàng con không tham chiếu hàng cha khi khóa là NULL (theo cấu hình và loại constraint). Khi đó INNER JOIN bỏ hàng con ấy; LEFT JOIN từ bảng con giữ hàng nhưng cột cha NULL.

## 15. JOIN nhiều bảng một-nhiều có thể nhân chéo

Một lỗi khó phát hiện: nối hai bảng con độc lập vào cùng một bảng cha.

Giả sử mỗi order có 3 order_items và 2 payments.

~~~sql
SELECT
    o.id,
    oi.id AS item_id,
    pay.id AS payment_id
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.id
LEFT JOIN payments AS pay
    ON pay.order_id = o.id;
~~~

Với một order có 3 item và 2 payment, kết quả có 3 × 2 = 6 hàng. Mỗi item bị lặp hai lần, mỗi payment bị lặp ba lần. Đây là fan-out kép.

### 15.1. Tại sao tổng tiền bị phóng đại?

~~~sql
SELECT
    o.id,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(pay.amount) AS paid_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.id
LEFT JOIN payments AS pay
    ON pay.order_id = o.id
GROUP BY o.id;
~~~

Nếu có 3 items và 2 payments, mỗi item bị lặp hai lần và mỗi payment bị lặp ba lần. Cả hai tổng có thể bị nhân sai.

### 15.2. Aggregate từng bảng con trước khi JOIN

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.id AS order_id,
    COALESCE(it.item_total, 0) AS item_total,
    COALESCE(pt.paid_total, 0) AS paid_total
FROM orders AS o
LEFT JOIN item_totals AS it
    ON it.order_id = o.id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.id;
~~~

Mỗi CTE có tối đa một hàng/order. Hai JOIN sau đó không tạo tích nhân giữa item và payment.

### 15.3. SUM(DISTINCT amount) không phải cách sửa tổng quát

Nếu hai payment hợp lệ có cùng số tiền 100.000, SUM(DISTINCT amount) chỉ cộng 100.000 một lần, làm thiếu tiền. DISTINCT trên giá trị không thay thế việc tổng hợp theo đúng khóa.

## 16. JOIN và GROUP BY: xác định grain trước khi aggregate

Ví dụ muốn tính doanh thu theo customer.

Nếu amount nằm ở bảng orders và một order có nhiều items:

~~~sql
SELECT
    c.id,
    SUM(o.amount) AS revenue
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id
GROUP BY c.id;
~~~

o.amount bị lặp theo số item. Tổng doanh thu bị phóng đại.

Nếu chỉ cần doanh thu đơn hàng, không cần JOIN order_items:

~~~sql
SELECT
    c.id,
    SUM(o.amount) AS revenue
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
GROUP BY c.id;
~~~

Nếu cần thông tin item, hãy tổng hợp item trước hoặc tính từng metric ở grain riêng.

### 16.1. Kiểm tra grain bằng khóa

~~~sql
SELECT
    COUNT(*) AS rows_after_join,
    COUNT(DISTINCT o.id) AS distinct_orders
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.id;
~~~

Nếu rows_after_join lớn hơn distinct_orders, truy vấn đang có nhiều hàng/order. Điều này bình thường nếu grain là item, nhưng sai nếu metric amount ở grain order được cộng trực tiếp.

### 16.2. Aggregate trước khi JOIN

~~~sql
WITH order_item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
)
SELECT
    o.id,
    o.amount,
    i.item_total
FROM orders AS o
LEFT JOIN order_item_totals AS i
    ON i.order_id = o.id;
~~~

Sau GROUP BY, CTE có tối đa một hàng/order, giữ grain order.

## 17. Kiểm tra điều kiện JOIN có đủ khóa không

Một JOIN đúng thường nối các khóa có quan hệ nghiệp vụ đã xác định. Nếu bảng có tenant_id, organization_id hoặc partition key, chỉ nối id có thể tạo match xuyên tenant.

Sai:

~~~sql
ON a.customer_id = b.customer_id
~~~

Nếu customer_id chỉ duy nhất trong từng tenant, cần:

~~~sql
ON a.tenant_id = b.tenant_id
AND a.customer_id = b.customer_id
~~~

Tương tự với khóa ghép, phiên bản dữ liệu, loại bản ghi, effective date hoặc source system.

### 17.1. Phát hiện match sai tenant

~~~sql
SELECT
    a.tenant_id AS left_tenant,
    b.tenant_id AS right_tenant,
    COUNT(*) AS bad_matches
FROM a
JOIN b
    ON a.customer_id = b.customer_id
WHERE a.tenant_id <> b.tenant_id
GROUP BY a.tenant_id, b.tenant_id;
~~~

Nếu query này trả hàng, điều kiện JOIN có thể thiếu tenant key. Không chỉ so sánh số hàng; hãy kiểm tra thuộc tính định danh và phạm vi dữ liệu.

### 17.2. Temporal join

Một số mô hình cần nối theo khoảng hiệu lực:

~~~sql
ON fact.customer_id = dim.customer_id
AND fact.event_time >= dim.valid_from
AND fact.event_time < dim.valid_to
~~~

Nếu khoảng hiệu lực chồng lấn, một event có thể match nhiều phiên bản dimension. Đếm số dimension match trên từng fact để phát hiện overlap.

~~~sql
SELECT
    fact.id,
    COUNT(dim.version_id) AS matching_versions
FROM facts AS fact
LEFT JOIN customer_dimension AS dim
    ON dim.customer_id = fact.customer_id
   AND fact.event_time >= dim.valid_from
   AND fact.event_time < dim.valid_to
GROUP BY fact.id
HAVING COUNT(dim.version_id) <> 1;
~~~

Kết quả có 0 match hoặc nhiều hơn 1 match cần được phân loại theo quy tắc dữ liệu. Không mặc định chọn MAX(version_id) nếu chưa có quy tắc xác định.

## 18. Dùng DISTINCT và GROUP BY đúng mục đích

### 18.1. DISTINCT che duplicate output

~~~sql
SELECT DISTINCT c.id, c.name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Truy vấn trả mỗi customer một lần, nhưng chỉ vì hai cột chọn ra giống nhau được loại duplicate. Nếu thêm o.id, mỗi order lại là một hàng khác.

### 18.2. GROUP BY tạo grain tổng hợp

~~~sql
SELECT
    c.id,
    COUNT(o.id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
GROUP BY c.id;
~~~

Mỗi customer một hàng. Đây là cách có chủ đích để thay đổi grain từ order/customer pair về customer.

### 18.3. Không GROUP BY chỉ để làm biến mất fan-out

Nếu JOIN sai rồi GROUP BY để lấy một hàng, các giá trị aggregate vẫn có thể đã bị nhân. Hãy sửa quan hệ JOIN hoặc aggregate đúng grain trước.

## 19. Kiểm tra khóa và constraint

Row-count diagnostics có thể phát hiện vấn đề, nhưng constraint giúp ngăn lỗi dữ liệu tái diễn.

### 19.1. Primary key

PRIMARY KEY bảo đảm giá trị khóa không NULL và duy nhất trong bảng. Nếu cột JOIN phía phải là PK, mỗi hàng trái có thể match tối đa một hàng phải theo điều kiện equality trên toàn bộ khóa.

### 19.2. Unique constraint

Nếu quan hệ 1:1 cần được bảo đảm:

~~~sql
ALTER TABLE customer_profile
ADD CONSTRAINT uq_customer_profile_customer
UNIQUE (customer_id);
~~~

Unique constraint bảo vệ invariant ở database, kể cả khi nhiều ứng dụng ghi đồng thời.

### 19.3. Foreign key

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id);
~~~

Foreign key giúp đảm bảo mỗi customer_id không NULL của order tham chiếu customer tồn tại khi constraint được enforce. Nó không đảm bảo customer chỉ có một order.

### 19.4. Index không đồng nghĩa uniqueness

Index thường giúp tìm hàng hiệu quả hơn. Index không UNIQUE vẫn cho phép nhiều hàng cùng khóa và không ngăn fan-out.

### 19.5. Constraint có thể chưa được validate hoặc chưa enforce

Khi điều tra dữ liệu legacy, kiểm tra trạng thái constraint trên DBMS. Một constraint bị disable, not validated hoặc không được hỗ trợ như kỳ vọng có thể không bảo vệ dữ liệu hiện tại.

## 20. Execution plan và cardinality estimates

Sau khi xác định stage gây thay đổi số hàng, xem execution plan để hiểu cách DBMS thực hiện JOIN.

### 20.1. PostgreSQL

~~~sql
EXPLAIN
SELECT ...
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

EXPLAIN ANALYZE chạy câu query để thu thập số hàng thực tế và thời gian:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Chỉ dùng ANALYZE khi có thể chấp nhận query thực sự chạy. Với SELECT, query sẽ thực thi và có thể tiêu tốn tài nguyên; với DML, phải đặc biệt thận trọng vì statement có thể thay đổi dữ liệu.

### 20.2. MySQL

MySQL có EXPLAIN và EXPLAIN ANALYZE trong các phiên bản hỗ trợ. Xem estimated rows, actual rows, access type và join order.

### 20.3. SQL Server

Dùng estimated/actual execution plan hoặc SET STATISTICS IO/TIME theo môi trường. Actual plan cho biết số hàng thực tế tại operator.

### 20.4. Oracle

Có thể dùng EXPLAIN PLAN và DBMS_XPLAN để đọc plan; actual row statistics cần thu thập theo cách phù hợp với quyền/cấu hình.

### 20.5. SQLite

EXPLAIN QUERY PLAN cho biết chiến lược truy cập và index. Khả năng thông tin actual row count khác các DBMS server lớn.

### 20.6. Estimated rows khác actual rows

Optimizer ước lượng số hàng để chọn join algorithm/order. Nếu estimate lệch xa actual, nguyên nhân có thể là statistics cũ, skew, correlation giữa cột hoặc biểu thức JOIN phức tạp.

- **Actual rows tăng bất thường:** điều tra duplicate key và fan-out.
- **Actual rows ít hơn dự kiến:** điều tra unmatched keys, filters và NULL.
- **Estimated rows lệch lớn:** xem statistics, histogram, index và điều kiện lọc.

Execution plan giải thích cách chạy; nó không thay thế kiểm tra logic và grain của dữ liệu.

## 21. Index và hiệu năng không sửa lỗi logic

Một JOIN có thể rất nhanh nhưng vẫn sai kết quả. Index trên khóa JOIN giúp tìm hàng hiệu quả, nhưng không biến quan hệ một-nhiều thành một-một.

~~~sql
CREATE INDEX ix_orders_customer_id
ON orders(customer_id);
~~~

Index này có thể cải thiện truy cập theo customer_id. Nó vẫn cho phép khách có nhiều order. Nếu cần mỗi customer tối đa một profile, phải dùng UNIQUE constraint, không chỉ index thường.

Khi tối ưu:

1. Xác nhận điều kiện JOIN đúng.
2. Xác nhận grain và cardinality đúng.
3. Xem actual row counts.
4. Xem access path và index.
5. Sau đó mới điều chỉnh index/query plan.

## 22. So sánh count trong một snapshot nhất quán

Nếu chạy từng COUNT trong các statement riêng trong lúc dữ liệu đang được ghi, kết quả có thể không khớp nhau do transaction khác insert/delete/update giữa các lần đo.

Ví dụ:

1. Đếm orders được 100.
2. Một transaction khác insert order.
3. Đếm JOIN được 101.
4. Người kiểm thử tưởng JOIN tạo thêm một hàng.

Để so sánh chính xác:

- Dùng transaction và isolation level phù hợp.
- Chạy stage counts trong một statement khi có thể.
- Dùng fixture cố định cho kiểm thử.
- Nếu hệ thống đang hoạt động, ghi rõ thời điểm/snapshot của phép đo.

Snapshot semantics khác nhau theo DBMS; không giả định cùng tên isolation level tạo đúng một hành vi ở mọi sản phẩm.

## 23. Truy vấn chẩn đoán tổng quát

Một mẫu hữu ích cho LEFT JOIN:

~~~sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT l.id) AS distinct_left_keys,
    COUNT(DISTINCT r.id) AS distinct_right_keys,
    COUNT(r.id) AS matched_right_rows,
    SUM(CASE WHEN r.id IS NULL THEN 1 ELSE 0 END)
        AS unmatched_left_rows
FROM left_table AS l
LEFT JOIN right_table AS r
    ON r.left_id = l.id;
~~~

Thay tên bảng và khóa bằng schema thực tế.

Diễn giải:

- joined_rows: số hàng sau LEFT JOIN.
- distinct_left_keys: số entity trái còn xuất hiện.
- distinct_right_keys: số entity phải được match.
- matched_right_rows: số hàng kết quả có khóa phải không NULL; nếu khóa phải là PK thì đây là số match row.
- unmatched_left_rows: số hàng output không match; nếu phía trái đã bị lặp từ stage trước, đây có thể không phải số entity trái distinct không match.

### 23.1. Đếm unmatched entity chính xác

~~~sql
SELECT COUNT(*) AS unmatched_left_entities
FROM left_table AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM right_table AS r
    WHERE r.left_id = l.id
);
~~~

Câu này đếm hàng trái không có match mà không bị nhân do nhiều match.

### 23.2. Đếm fan-out theo từng key

~~~sql
SELECT
    l.id,
    COUNT(r.id) AS match_count
FROM left_table AS l
LEFT JOIN right_table AS r
    ON r.left_id = l.id
GROUP BY l.id
HAVING COUNT(r.id) > 1
ORDER BY match_count DESC, l.id;
~~~

Đây thường là truy vấn đầu tiên nên chạy khi JOIN trả quá nhiều hàng.

## 24. Debug một truy vấn thực tế theo trình tự

Giả sử báo cáo cần một hàng mỗi customer, gồm tổng tiền đơn hàng và số sản phẩm đã mua.

### Bước 1 — ghi lại grain đầu ra

Một hàng = một customer. Vì vậy, số hàng cuối dự kiến không vượt số customer thuộc tập báo cáo, nếu query chỉ trả customer trong phạm vi đó.

### Bước 2 — đếm baseline

~~~sql
SELECT COUNT(*) FROM customers;
~~~

Đếm cả số customer trong scope nếu có filter.

### Bước 3 — kiểm tra JOIN customer → orders

~~~sql
SELECT
    c.id,
    COUNT(o.id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
GROUP BY c.id;
~~~

Xác nhận 0, 1 hay nhiều order mỗi customer.

### Bước 4 — kiểm tra JOIN orders → items

~~~sql
SELECT
    o.id,
    COUNT(oi.id) AS item_count
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.id
GROUP BY o.id;
~~~

Xác nhận đơn không item có được giữ hay loại theo nghiệp vụ.

### Bước 5 — kiểm tra JOIN items → products

~~~sql
SELECT
    oi.id,
    COUNT(p.id) AS product_matches
FROM order_items AS oi
LEFT JOIN products AS p
    ON p.id = oi.product_id
GROUP BY oi.id
HAVING COUNT(p.id) <> 1;
~~~

Nếu query trả hàng, có item không có product hoặc product_id không unique trong bảng products.

### Bước 6 — aggregate trước khi ghép về customer

~~~sql
WITH order_totals AS (
    SELECT
        customer_id,
        SUM(amount) AS total_order_amount,
        COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
),
item_totals AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity) AS total_item_quantity
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.id
    GROUP BY o.customer_id
)
SELECT
    c.id AS customer_id,
    COALESCE(ot.order_count, 0) AS order_count,
    COALESCE(ot.total_order_amount, 0) AS total_order_amount,
    COALESCE(it.total_item_quantity, 0) AS total_item_quantity
FROM customers AS c
LEFT JOIN order_totals AS ot
    ON ot.customer_id = c.id
LEFT JOIN item_totals AS it
    ON it.customer_id = c.id;
~~~

Mỗi CTE có tối đa một hàng/customer. Hai phép LEFT JOIN cuối giữ grain customer và không nhân tổng đơn với số item.

### Bước 7 — so sánh invariant

~~~sql
SELECT
    COUNT(*) AS report_rows,
    COUNT(DISTINCT customer_id) AS distinct_customers
FROM (
    -- đặt query báo cáo tại đây
) AS report;
~~~

Nếu báo cáo cần một hàng/customer, hai số phải bằng nhau và số hàng phải khớp số customer trong scope.

## 25. Kiểm thử hồi quy cho cardinality

Một truy vấn có thể đúng với dữ liệu hiện tại nhưng sai khi xuất hiện một customer có 10 đơn hoặc một order có nhiều payment. Hãy tạo fixture bao phủ các quan hệ:

- Một hàng trái có 0 match.
- Một hàng trái có đúng 1 match.
- Một hàng trái có nhiều match.
- Nhiều hàng phải cùng một khóa.
- Khóa NULL nếu schema cho phép.
- Hàng mồ côi nếu kiểm tra hệ thống chưa có FK.
- Nhiều bảng con một-nhiều cùng được JOIN.
- Dữ liệu có duplicate ở cột không được khai báo unique.

### 25.1. Assertion theo grain

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_order_count
FROM (
    -- query cần kiểm thử
) AS q;
~~~

Assert hai số bằng nhau nếu query phải trả một hàng mỗi order.

### 25.2. Assertion về số hàng không khớp

Nếu mọi order bắt buộc có customer:

~~~sql
SELECT COUNT(*) AS orphan_orders
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM customers AS c
    WHERE c.id = o.customer_id
);
~~~

Assert kết quả bằng 0. Nếu schema đã có FK enforced, test này vẫn có thể hữu ích để kiểm tra dữ liệu import hoặc các môi trường chưa đồng nhất.

### 25.3. Assertion về match tối đa một

Nếu mỗi item phải tham chiếu đúng một product:

~~~sql
SELECT oi.id
FROM order_items AS oi
LEFT JOIN products AS p
    ON p.id = oi.product_id
GROUP BY oi.id
HAVING COUNT(p.id) <> 1;
~~~

Assert không có hàng.

### 25.4. Kiểm tra tổng tiền đối chiếu độc lập

Để xác minh báo cáo không nhân amount:

~~~sql
SELECT SUM(amount) AS source_total
FROM orders;
~~~

So sánh với tổng order amount trong báo cáo ở cùng scope và snapshot. Không lấy tổng từ query đã JOIN order_items nếu chưa chứng minh mỗi order xuất hiện đúng một lần.

## 26. Khác biệt DBMS cần lưu ý khi đếm

Các khái niệm COUNT và JOIN cơ bản khá rộng, nhưng cú pháp hỗ trợ và chi tiết kiểu dữ liệu có thể khác:

- PostgreSQL, MySQL, MariaDB, SQL Server, Oracle và SQLite đều có INNER/LEFT JOIN phổ biến.
- FULL OUTER JOIN không có trong MySQL; có thể mô phỏng bằng hai LEFT JOIN và UNION ALL.
- SQLite hỗ trợ RIGHT/FULL OUTER JOIN từ phiên bản 3.39.0; runtime cũ hơn cần cách viết thay thế.
- Cách quote identifier và tên schema/database khác nhau.
- COUNT trả kiểu số có thể khác theo driver; SQL Server COUNT trả int, còn COUNT_BIG trả bigint. PostgreSQL COUNT trả bigint.
- Cú pháp FILTER cho aggregate có phạm vi hỗ trợ khác; CASE WHEN bên trong aggregate là lựa chọn thay thế rộng hơn.
- NULL-safe equality có cú pháp riêng theo DBMS.
- EXPLAIN/actual execution plan có cách hiển thị và mức chi tiết khác nhau.

### 26.1. FULL OUTER JOIN thay thế cho MySQL

Một mẫu mô phỏng:

~~~sql
SELECT
    a.id AS left_id,
    b.id AS right_id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.id = a.id

UNION ALL

SELECT
    a.id AS left_id,
    b.id AS right_id
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.id = b.id
WHERE a.id IS NULL;
~~~

Nhánh đầu giữ mọi hàng trái, gồm match. Nhánh hai chỉ thêm hàng phải không match. Dùng UNION ALL để tránh chi phí loại duplicate và không làm thay đổi những hàng trùng có ý nghĩa.

## 27. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| JOIN trả nhiều hàng hơn bảng trái | Quan hệ 1:N hoặc duplicate key phía phải | COUNT match theo từng khóa |
| INNER JOIN làm mất hàng | Không có match, NULL, filter hoặc điều kiện sai | LEFT JOIN + WHERE right.pk IS NULL |
| LEFT JOIN vẫn mất hàng trái | Predicate phía phải đặt ở WHERE | Kiểm tra ON/WHERE |
| COUNT(*) lớn hơn COUNT(DISTINCT id) | Một entity có nhiều hàng output | Xác định grain |
| SUM(amount) bị phóng đại | JOIN sang bảng chi tiết | Aggregate child trước khi JOIN |
| Số hàng tăng theo tích 3×2 | Hai bảng con 1:N cùng JOIN | Đếm cardinality từng bảng con |
| Một khóa có hàng match quá nhiều | Duplicate key hoặc thiếu cột khóa ghép | GROUP BY/HAVING và kiểm tra predicate |
| Một số hàng không match dù ID giống | Kiểu dữ liệu, whitespace, collation hoặc tenant | So sánh raw values, cast, scope |
| NULL không match NULL | Semantics của phép bằng | Xác định NULL-safe join có đúng nghiệp vụ không |
| Kết quả thay đổi giữa hai lần đếm | Dữ liệu đang ghi hoặc snapshot khác | Transaction/isolation |
| Query đúng nhưng chạy chậm | Index/statistics/plan | EXPLAIN actual plan |
| DISTINCT làm số hàng đúng nhưng tổng sai | DISTINCT che output duplicate | Kiểm tra aggregate và grain |

## 28. Checklist trước khi kết luận JOIN đúng

1. Grain đầu ra là một hàng cho mỗi entity/cặp/chi tiết nào?
2. Baseline của mỗi bảng đầu vào là bao nhiêu?
3. Số hàng sau từng JOIN là bao nhiêu?
4. Số khóa distinct trước và sau thay đổi ra sao?
5. Khóa JOIN phía phải có UNIQUE/PRIMARY KEY không?
6. Quan hệ thực tế là 1:1, 1:N hay N:M?
7. Có thiếu cột trong composite key, tenant key hoặc temporal condition không?
8. Có duplicate key hoặc dữ liệu lịch sử cần chọn phiên bản không?
9. Có hàng không match ở hai phía không?
10. NULL có được xử lý theo đúng nghiệp vụ không?
11. Predicate đang nằm đúng ON hay WHERE không?
12. Hai bảng con 1:N có đang tạo fan-out chéo không?
13. COUNT(*) có bị nhầm với COUNT(DISTINCT entity_key) không?
14. Aggregate có được tính ở đúng grain không?
15. DISTINCT có đang che lỗi thay vì sửa nguyên nhân không?
16. Constraint có thực sự enforce uniqueness/referential integrity không?
17. Tất cả phép đếm có cùng snapshot dữ liệu không?
18. Actual row count trong execution plan có gần estimate không?
19. Có test fixture cho 0, 1 và nhiều match không?
20. Query cuối có assertion về uniqueness/grain không?

## 29. Bài tập thực hành có lời giải

Dùng dữ liệu mẫu ở mục 3 trừ khi đề nói khác.

### Bài 1. Đếm baseline

**Đề:** customers, orders và order_items có bao nhiêu hàng?

**Lời giải:** lần lượt 4, 5 và 7.

### Bài 2. INNER JOIN customers và orders có bao nhiêu hàng?

~~~sql
SELECT COUNT(*)
FROM customers c
JOIN orders o ON o.customer_id = c.id;
~~~

**Lời giải:** 5 hàng. Khách 1 có 2 đơn, khách 2 có 3 đơn; khách 3 và 4 bị loại.

### Bài 3. LEFT JOIN customers và orders có bao nhiêu hàng?

**Lời giải:** 7 hàng. Năm match cộng một hàng cho mỗi khách 3 và 4 không có đơn.

### Bài 4. LEFT JOIN có bao nhiêu customer distinct?

~~~sql
SELECT COUNT(DISTINCT c.id)
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id;
~~~

**Lời giải:** 4.

### Bài 5. Có bao nhiêu order match?

**Lời giải:** COUNT(o.id) bằng 5 nếu o.id là khóa chính không NULL.

### Bài 6. Tìm khách không có đơn

~~~sql
SELECT c.id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM orders o
    WHERE o.customer_id = c.id
);
~~~

**Lời giải:** customer 3 và 4.

### Bài 7. Đơn nào không có item?

~~~sql
SELECT o.id
FROM orders o
WHERE NOT EXISTS (
    SELECT 1 FROM order_items oi
    WHERE oi.order_id = o.id
);
~~~

**Lời giải:** order 104.

### Bài 8. INNER JOIN orders và order_items có bao nhiêu hàng?

**Lời giải:** 7. Order 104 không có item nên bị loại.

### Bài 9. LEFT JOIN orders và order_items có bao nhiêu hàng?

**Lời giải:** 8. Bảy item match cộng một hàng giữ lại cho order 104.

### Bài 10. COUNT(*) và COUNT(oi.id) trong LEFT JOIN orders/items?

**Lời giải:** COUNT(*) = 8; COUNT(oi.id) = 7 vì hàng của order 104 có oi.id NULL.

### Bài 11. Tìm customer có nhiều hơn hai đơn

~~~sql
SELECT customer_id, COUNT(*)
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 2;
~~~

**Lời giải:** customer 2 có 3 đơn.

### Bài 12. Tại sao JOIN profile bị nhân hàng?

**Đề:** Query customers LEFT JOIN customer_profile theo customer_id. Một customer có 3 profile rows.

**Lời giải:** một hàng customer match 3 hàng phải, nên tạo 3 hàng output. Kiểm tra duplicate key và xác định profile hiện hành hoặc thêm UNIQUE nếu quan hệ thực sự 1:1.

### Bài 13. Vì sao index không ngăn duplicate?

**Lời giải:** index thường chỉ hỗ trợ truy cập. Nếu không khai báo UNIQUE, nhiều hàng cùng giá trị vẫn được phép.

### Bài 14. Điều kiện status đặt ở WHERE làm mất khách không có đơn PAID. Vì sao?

**Lời giải:** cột o.status của hàng không match là NULL; WHERE o.status = 'PAID' loại hàng đó. Đưa điều kiện vào ON hoặc lọc orders trong CTE nếu muốn giữ mọi customer.

### Bài 15. JOIN item và payment tạo 6 hàng cho một order có 3 item và 2 payment. Vì sao?

**Lời giải:** hai quan hệ một-nhiều độc lập tạo tích 3 × 2. Aggregate từng bảng con theo order_id trước khi JOIN.

### Bài 16. Có nên dùng SUM(DISTINCT payment.amount) để sửa tổng bị nhân?

**Lời giải:** không. Hai payment hợp lệ có cùng amount sẽ bị cộng một lần. Sửa grain và join fan-out.

### Bài 17. COUNT(DISTINCT customer_id) trả 4. Có chứng minh query đúng không?

**Lời giải:** không. Nó chỉ chứng minh có 4 khóa customer distinct; các cột khác và aggregate vẫn có thể bị nhân hoặc ghép sai.

### Bài 18. Khóa ghép bị thiếu

**Đề:** item và shipment line cần nối theo order_id và line_no, nhưng query chỉ dùng order_id.

**Lời giải:** mỗi item có thể match mọi shipment line cùng đơn. Thêm line_no vào điều kiện JOIN.

### Bài 19. NULL = NULL có match không?

**Lời giải:** không trong phép equality SQL thông thường vì kết quả là UNKNOWN. Dùng NULL-safe equality chỉ khi nghiệp vụ định nghĩa hai NULL là cùng nhóm.

### Bài 20. Đếm orphan orders

~~~sql
SELECT COUNT(*)
FROM orders o
WHERE NOT EXISTS (
    SELECT 1 FROM customers c
    WHERE c.id = o.customer_id
);
~~~

**Lời giải:** nếu FK được enforce, kết quả thường bằng 0; vẫn hữu ích khi audit dữ liệu legacy hoặc môi trường chưa có constraint.

### Bài 21. Tại sao nên đếm sau mỗi JOIN?

**Lời giải:** để khoanh vùng stage đầu tiên làm mất hoặc nhân hàng, thay vì chỉ thấy tổng cuối và phải đoán nguyên nhân.

### Bài 22. Grain của customer-order JOIN là gì?

**Lời giải:** một hàng cho mỗi cặp customer-order match, tương đương một hàng/order nếu order thuộc đúng một customer.

### Bài 23. Grain của order-order_item JOIN là gì?

**Lời giải:** một hàng cho mỗi order item match; order có nhiều item tạo nhiều hàng.

### Bài 24. Làm sao kiểm tra query cần một hàng mỗi order?

**Lời giải:** bọc query trong subquery, so sánh COUNT(*) với COUNT(DISTINCT order_id). Hai số phải bằng nhau nếu order_id không NULL và grain yêu cầu đúng một hàng/order.

### Bài 25. Tại sao phải dùng snapshot nhất quán khi đếm?

**Lời giải:** dữ liệu có thể thay đổi giữa các statement. Nếu count baseline và count sau JOIN nhìn các snapshot khác nhau, chênh lệch có thể do concurrent writes chứ không phải JOIN.

## 30. Tổng kết

Đối chiếu số hàng trước và sau từng JOIN là một kỹ thuật kiểm thử cơ bản nhưng rất hiệu quả. Nó giúp xác định nơi truy vấn loại hàng, nhân hàng hoặc thay đổi grain.

- **Đếm cả hàng lẫn khóa distinct:** COUNT(*) cho biết số hàng kết quả; COUNT(DISTINCT key) cho biết số entity/cặp phân biệt.
- **INNER JOIN có thể giảm, giữ nguyên hoặc tăng số hàng.** LEFT JOIN giữ hàng trái nhưng vẫn có thể tăng do nhiều match.
- **Kiểm tra cardinality trên từng khóa:** GROUP BY/HAVING phát hiện duplicate key và fan-out.
- **Định nghĩa grain trước khi JOIN:** một hàng/customer khác một hàng/order và khác một hàng/order_item.
- **Đặt predicate đúng vị trí:** ON và WHERE có thể tạo kết quả khác nhau với OUTER JOIN.
- **Aggregate ở đúng grain:** JOIN hai bảng con một-nhiều có thể nhân chéo và làm SUM/COUNT bị phóng đại.
- **Dùng constraint để bảo vệ invariant:** PRIMARY KEY, UNIQUE và FOREIGN KEY giúp ngăn một số lỗi dữ liệu tái diễn.
- **Đếm trong snapshot nhất quán và xem actual execution plan:** phân biệt thay đổi dữ liệu, cardinality thật và ước lượng của optimizer.
- **Kiểm thử 0, 1 và nhiều match:** truy vấn đúng với dữ liệu hiện tại vẫn có thể sai khi quan hệ tăng lên.

Khi debug, hãy đi theo chuỗi **baseline → JOIN thứ nhất → JOIN tiếp theo → match count theo khóa → kiểm tra grain → aggregate → đối chiếu invariant**. Cách này giúp xác định đúng JOIN gây sai lệch và giữ kết quả báo cáo đúng với ý nghĩa dữ liệu.
