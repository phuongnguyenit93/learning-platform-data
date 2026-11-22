# WITH và Common Table Expression để đặt tên tập kết quả trung gian

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Viết CTE bằng mệnh đề WITH trong MySQL.
- Đặt tên cho một truy vấn con để câu SQL dễ đọc và dễ bảo trì.
- Khai báo tên cột đầu ra cho CTE và hiểu cách MySQL suy ra tên cột.
- Kết hợp nhiều CTE, trong đó CTE sau sử dụng kết quả của CTE trước.
- Dùng CTE trong SELECT, UPDATE và DELETE.
- Phân biệt CTE với derived table, view và temporary table.
- Hiểu optimizer có thể merge hoặc materialize CTE và biết cách kiểm tra bằng EXPLAIN.
- Tránh các lỗi về phạm vi tên, cột trùng, thứ tự khai báo và dữ liệu trung gian quá lớn.

Common Table Expression (CTE) là một tập kết quả được đặt tên, chỉ có hiệu lực trong một câu lệnh SQL. CTE giúp chia một truy vấn phức tạp thành các bước có tên rõ nghĩa. Thay vì lồng nhiều SELECT vào nhau, ta có thể mô tả từng bước trong WITH rồi dùng tên của chúng ở truy vấn chính.

Trong MySQL, CTE không phải bảng vật lý và cũng không tự động làm truy vấn nhanh hơn. Optimizer có thể gộp CTE vào truy vấn ngoài hoặc tạo tập kết quả trung gian để sử dụng. Vì vậy, cần hiểu cả cú pháp lẫn cách kiểm tra kế hoạch thực thi.

## 1. CTE là gì?

CTE là một truy vấn con được khai báo ở đầu một câu lệnh và gắn với một tên. Truy vấn chính có thể tham chiếu tên đó như tham chiếu một bảng trong mệnh đề FROM.

Ví dụ, thay vì viết truy vấn con trực tiếp:

~~~sql
SELECT
    customer_id,
    total_amount
FROM (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price) AS total_amount
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.customer_id
) AS customer_spending
WHERE total_amount >= 5000000;
~~~

Có thể đặt tên cho tập kết quả trung gian bằng WITH:

~~~sql
WITH customer_spending AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price) AS total_amount
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    customer_id,
    total_amount
FROM customer_spending
WHERE total_amount >= 5000000;
~~~

Tên customer_spending mô tả ý nghĩa của bước tổng hợp. Truy vấn chính thể hiện rõ mục tiêu: lấy những khách hàng có tổng chi tiêu từ 5 triệu trở lên.

Một CTE thường có ba thành phần:

1. Tên CTE.
2. Truy vấn định nghĩa tập kết quả nằm trong dấu ngoặc.
3. Câu lệnh chính sử dụng CTE.

CTE chỉ tồn tại trong phạm vi câu lệnh đó. Sau khi câu lệnh kết thúc, tên CTE không còn dùng được.

## 2. Cú pháp WITH

Cú pháp tổng quát cho CTE không đệ quy:

~~~sql
WITH cte_name [(column_name, ...)] AS (
    subquery
)
SELECT ...
FROM cte_name;
~~~

Trong đó:

- WITH bắt đầu danh sách CTE.
- cte_name là tên do người viết đặt.
- Danh sách column_name là tùy chọn, dùng để đặt tên cho các cột đầu ra.
- AS mở đầu truy vấn định nghĩa CTE.
- subquery là câu SELECT tạo tập kết quả.
- SELECT phía sau là câu lệnh chính sử dụng CTE.

Nếu có nhiều CTE, phân tách các định nghĩa bằng dấu phẩy:

~~~sql
WITH
first_cte AS (
    SELECT ...
),
second_cte AS (
    SELECT ...
    FROM first_cte
)
SELECT ...
FROM second_cte;
~~~

Chỉ viết WITH một lần ở cùng cấp câu lệnh. Không viết WITH lặp lại giữa các CTE trong cùng danh sách.

Mỗi tên CTE phải duy nhất trong cùng mệnh đề WITH. Với CTE không đệ quy, không thêm từ khóa RECURSIVE. Chỉ dùng WITH RECURSIVE khi một CTE tự tham chiếu chính nó; phần anchor và recursive member sẽ được trình bày ở bài về truy vấn đệ quy.

### 2.1. Đặt tên cột cho CTE

Có thể khai báo tên cột ngay sau tên CTE:

~~~sql
WITH order_totals (order_id, item_count, order_value) AS (
    SELECT
        order_id,
        COUNT(*),
        SUM(quantity * unit_price)
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    item_count,
    order_value
FROM order_totals;
~~~

Ba tên trong danh sách phải tương ứng với ba biểu thức được SELECT trả về. Số lượng cột không khớp sẽ khiến câu lệnh báo lỗi.

Nếu bỏ danh sách cột, MySQL lấy tên từ các biểu thức trong SELECT:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS order_value
    FROM order_item
    GROUP BY order_id
)
SELECT *
FROM order_totals;
~~~

Nên đặt alias rõ ràng cho biểu thức tính toán. Không dựa vào tên cột tự sinh từ biểu thức phức tạp, vì chúng có thể khó đọc hoặc không phù hợp khi được tham chiếu ở bước sau.

### 2.2. Tên cột phải rõ ràng và duy nhất

Một CTE hoạt động như một bảng logic với các cột đầu ra. Các tên cột trong CTE cần phân biệt được để truy vấn ngoài tham chiếu chính xác.

Ví dụ không nên trả về hai cột cùng tên id:

~~~sql
WITH customer_order AS (
    SELECT
        c.customer_id AS id,
        o.order_id AS id,
        o.ordered_at
    FROM customer AS c
    JOIN sales_order AS o
        ON o.customer_id = c.customer_id
)
SELECT *
FROM customer_order;
~~~

Cách sửa là đặt alias thể hiện nguồn gốc:

~~~sql
WITH customer_order AS (
    SELECT
        c.customer_id,
        o.order_id,
        o.ordered_at
    FROM customer AS c
    JOIN sales_order AS o
        ON o.customer_id = c.customer_id
)
SELECT *
FROM customer_order;
~~~

Nếu hai bảng có cột cùng tên, hãy chỉ rõ alias bảng và đặt tên đầu ra phù hợp. Cách này cũng tránh nhầm lẫn khi câu truy vấn được mở rộng sau này.

## 3. Chuẩn bị dữ liệu thực hành

Các ví dụ sau sử dụng một mô hình đơn giản gồm khách hàng, đơn hàng và dòng hàng. Có thể chạy DDL và dữ liệu mẫu trong một database thực hành.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    lifetime_value DECIMAL(14, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    ordered_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_sales_order_customer_date (customer_id, ordered_at),
    KEY idx_sales_order_status_date (order_status, ordered_at),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
) ENGINE = InnoDB;

INSERT INTO customer (customer_id, full_name)
VALUES
    (101, 'Nguyễn An'),
    (102, 'Trần Bình'),
    (103, 'Lê Chi');

INSERT INTO sales_order (
    order_id, customer_id, order_status, ordered_at
)
VALUES
    (1001, 101, 'completed', '2026-01-05 09:15:00'),
    (1002, 101, 'completed', '2026-01-20 14:30:00'),
    (1003, 102, 'pending',   '2026-02-02 10:00:00'),
    (1004, 102, 'completed', '2026-02-12 16:45:00'),
    (1005, 103, 'cancelled', '2026-02-15 11:20:00');

INSERT INTO order_item (
    order_id, line_no, product_name, quantity, unit_price
)
VALUES
    (1001, 1, 'Bàn phím cơ', 1, 1250000.00),
    (1001, 2, 'Chuột không dây', 2, 450000.00),
    (1002, 1, 'Màn hình 27 inch', 1, 5200000.00),
    (1003, 1, 'Tai nghe', 1, 890000.00),
    (1004, 1, 'Webcam', 2, 750000.00),
    (1004, 2, 'Micro USB', 1, 1100000.00);
~~~

Tổng giá trị dòng hàng được tính bằng quantity * unit_price. Trong ví dụ, sales_order không lưu total_amount; các truy vấn sẽ tính từ order_item để minh họa CTE tạo tập kết quả trung gian.

## 4. CTE đơn giản để đặt tên kết quả

Ví dụ tính tổng tiền từng đơn:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
ORDER BY order_id;
~~~

CTE order_totals trả về một hàng cho mỗi order_id. Câu SELECT bên ngoài có thể lọc, sắp xếp hoặc JOIN tập kết quả này như một nguồn dữ liệu.

Lọc các đơn có tổng tiền ít nhất 2 triệu:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE total_amount >= 2000000
ORDER BY total_amount DESC;
~~~

Có thể đặt điều kiện tổng hợp ngay trong CTE bằng HAVING:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
    HAVING SUM(quantity * unit_price) >= 2000000
)
SELECT *
FROM order_totals;
~~~

Hai cách có thể trả về cùng kết quả, nhưng vị trí điều kiện thể hiện ý định khác nhau:

- HAVING lọc nhóm ngay trong bước tạo CTE.
- WHERE ở truy vấn ngoài lọc tập kết quả đã đặt tên.

Chọn cách giúp ranh giới logic dễ hiểu. Không cần đưa mọi điều kiện vào CTE nếu điều kiện đó chỉ phục vụ truy vấn chính.

## 5. Kết hợp nhiều CTE

Một truy vấn có thể được chia thành nhiều bước. CTE khai báo trước có thể được CTE khai báo sau tham chiếu.

Ví dụ cần tính tổng chi tiêu hoàn tất của từng khách hàng, rồi lấy những khách hàng có doanh thu từ 2 triệu trở lên:

~~~sql
WITH
order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
),
completed_orders AS (
    SELECT
        o.order_id,
        o.customer_id,
        ot.total_amount
    FROM sales_order AS o
    JOIN order_totals AS ot
        ON ot.order_id = o.order_id
    WHERE o.order_status = 'completed'
),
customer_totals AS (
    SELECT
        customer_id,
        COUNT(*) AS completed_order_count,
        SUM(total_amount) AS spending
    FROM completed_orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.full_name,
    ct.completed_order_count,
    ct.spending
FROM customer_totals AS ct
JOIN customer AS c
    ON c.customer_id = ct.customer_id
WHERE ct.spending >= 2000000
ORDER BY ct.spending DESC;
~~~

Có thể đọc truy vấn theo từng tầng:

1. order_totals tính tiền từng đơn.
2. completed_orders chỉ giữ đơn đã hoàn tất và gắn khách hàng.
3. customer_totals tính số đơn cùng tổng chi tiêu theo khách.
4. SELECT cuối cùng thêm tên khách hàng và lọc ngưỡng chi tiêu.

Mỗi CTE đảm nhiệm một ý nghĩa cụ thể. Khi cần thay đổi cách tính tổng tiền, có thể sửa ở order_totals mà không phải lặp lại biểu thức ở mọi nơi.

### 5.1. CTE sau tham chiếu CTE trước

Trong một danh sách WITH không đệ quy, CTE chỉ được tham chiếu các CTE đã khai báo trước đó.

Hợp lệ:

~~~sql
WITH
base_orders AS (
    SELECT order_id, customer_id
    FROM sales_order
),
customer_order_count AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM base_orders
    GROUP BY customer_id
)
SELECT *
FROM customer_order_count;
~~~

Không hợp lệ nếu base_orders tham chiếu đến customer_order_count được khai báo phía sau. Cũng không thể tự tham chiếu chính nó nếu không dùng WITH RECURSIVE.

Vì vậy, hãy sắp xếp CTE theo chiều phụ thuộc: tập dữ liệu nền trước, bước biến đổi sau, kết quả cuối cùng ở cuối.

### 5.2. Tái sử dụng một CTE

Một CTE có thể được tham chiếu nhiều lần trong cùng câu lệnh:

~~~sql
WITH completed_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM sales_order
    WHERE order_status = 'completed'
)
SELECT
    (SELECT COUNT(*) FROM completed_orders) AS total_completed,
    (
        SELECT COUNT(DISTINCT customer_id)
        FROM completed_orders
    ) AS customer_count;
~~~

Tên completed_orders được dùng ở hai scalar subquery. CTE giúp định nghĩa điều kiện order_status = 'completed' một lần.

Việc tham chiếu nhiều lần không có nghĩa truy vấn con luôn được chạy lại độc lập. Optimizer có thể lựa chọn chiến lược thực thi phù hợp, bao gồm materialize tập kết quả và tái sử dụng. Hành vi thực tế cần được kiểm tra bằng EXPLAIN.

### 5.3. Dùng CTE để tách phép biến đổi nhiều bước

Ví dụ báo cáo doanh thu theo tháng:

~~~sql
WITH
order_totals AS (
    SELECT
        o.order_id,
        o.ordered_at,
        SUM(oi.quantity * oi.unit_price) AS order_amount
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.order_id, o.ordered_at
),
monthly_sales AS (
    SELECT
        DATE_FORMAT(ordered_at, '%Y-%m') AS sales_month,
        COUNT(*) AS order_count,
        SUM(order_amount) AS revenue
    FROM order_totals
    GROUP BY DATE_FORMAT(ordered_at, '%Y-%m')
)
SELECT
    sales_month,
    order_count,
    revenue
FROM monthly_sales
ORDER BY sales_month;
~~~

order_totals giải quyết việc tính tiền theo đơn. monthly_sales giải quyết việc gom theo tháng. Nếu báo cáo sau này cần thêm số khách hàng, có thể bổ sung một CTE hoặc biểu thức tổng hợp phù hợp mà không phải viết lại toàn bộ phép tính tiền đơn.

## 6. CTE với JOIN và truy vấn nhiều nguồn

CTE có thể JOIN với bảng vật lý, view, derived table hoặc CTE khác.

Ví dụ tìm khách hàng chưa có đơn hàng:

~~~sql
WITH customers_with_orders AS (
    SELECT DISTINCT customer_id
    FROM sales_order
)
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
LEFT JOIN customers_with_orders AS x
    ON x.customer_id = c.customer_id
WHERE x.customer_id IS NULL;
~~~

CTE customers_with_orders biểu diễn tập khách hàng đã từng có đơn. Truy vấn ngoài dùng LEFT JOIN để tìm những khách không khớp.

Cũng có thể dùng NOT EXISTS:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_order AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Không phải truy vấn nào cũng cần CTE. Với một điều kiện đơn giản, NOT EXISTS trực tiếp có thể ngắn và dễ đọc hơn. Hãy dùng CTE khi tên tập kết quả giúp làm sáng tỏ một bước nghiệp vụ hoặc khi cùng logic cần được tham chiếu nhiều lần.

## 7. CTE với UPDATE và DELETE

Trong MySQL, mệnh đề WITH có thể đứng trước câu UPDATE hoặc DELETE. Truy vấn định nghĩa CTE cung cấp tập kết quả để câu lệnh DML chính sử dụng; CTE là nguồn đọc, còn các thay đổi dữ liệu do UPDATE hoặc DELETE thực hiện.

### 7.1. UPDATE dựa trên tập kết quả tính trước

Ví dụ cập nhật lifetime_value của khách hàng bằng tổng giá trị các đơn đã hoàn tất:

~~~sql
WITH customer_spending AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price) AS spending
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.customer_id
)
UPDATE customer AS c
JOIN customer_spending AS cs
    ON cs.customer_id = c.customer_id
SET c.lifetime_value = cs.spending;
~~~

customer_spending tạo một hàng cho mỗi khách có đơn hoàn tất. UPDATE dùng tập kết quả đó để ghi lại lifetime_value.

Khách hàng không có đơn hoàn tất không xuất hiện trong CTE, vì vậy câu UPDATE trên không thay lifetime_value của họ. Nếu nghiệp vụ yêu cầu đưa giá trị của các khách đó về 0, cần viết truy vấn bao phủ toàn bộ customer, chẳng hạn LEFT JOIN với COALESCE.

### 7.2. DELETE dựa trên tập kết quả xác định

Ví dụ xác định các đơn đã bị hủy trước một mốc thời gian:

~~~sql
WITH cancelled_orders AS (
    SELECT order_id
    FROM sales_order
    WHERE order_status = 'cancelled'
      AND ordered_at < '2026-02-16 00:00:00'
)
DELETE so
FROM sales_order AS so
JOIN cancelled_orders AS co
    ON co.order_id = so.order_id;
~~~

CTE chỉ chọn tập order_id. DELETE mới là thao tác xóa dữ liệu.

Nếu bảng có foreign key từ bảng con, hành động xóa phụ thuộc constraint ON DELETE. Với dữ liệu nghiệp vụ hoặc dữ liệu cần lưu lịch sử, hãy cân nhắc lưu trữ, đánh dấu trạng thái hoặc archive trước khi xóa vật lý.

### 7.3. Kiểm tra trước khi chạy DML

Trước khi chạy UPDATE hoặc DELETE có ảnh hưởng nhiều hàng, hãy chạy phần SELECT tương đương để xem chính xác tập bản ghi:

~~~sql
WITH cancelled_orders AS (
    SELECT order_id
    FROM sales_order
    WHERE order_status = 'cancelled'
      AND ordered_at < '2026-02-16 00:00:00'
)
SELECT so.*
FROM sales_order AS so
JOIN cancelled_orders AS co
    ON co.order_id = so.order_id;
~~~

Trong môi trường cần kiểm soát chặt, hãy chạy DML trong transaction InnoDB khi câu lệnh và các thao tác liên quan cho phép, xác minh số hàng bị ảnh hưởng rồi COMMIT hoặc ROLLBACK. Bản thân WITH không tạo transaction và không bảo đảm rollback.

## 8. Phạm vi và quy tắc đặt tên CTE

### 8.1. CTE chỉ có hiệu lực trong một câu lệnh

Ví dụ:

~~~sql
WITH active_orders AS (
    SELECT order_id
    FROM sales_order
    WHERE order_status = 'completed'
)
SELECT *
FROM active_orders;
~~~

Câu lệnh tiếp theo không thể dùng lại tên active_orders:

~~~sql
SELECT *
FROM active_orders;
~~~

Câu lệnh thứ hai sẽ báo không tìm thấy bảng hoặc view tương ứng vì CTE đã hết phạm vi.

Nếu cần dùng cùng một tập kết quả ở nhiều câu lệnh, cân nhắc:

- View nếu logic cần được chia sẻ lâu dài.
- Temporary table nếu cần lưu kết quả theo session và dùng lại qua nhiều câu lệnh.
- Bảng vật lý nếu dữ liệu cần được lưu bền vững.

### 8.2. CTE lồng trong subquery

Có thể khai báo CTE ở đầu một truy vấn con. Phạm vi của CTE đó thuộc câu lệnh con tương ứng:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
WHERE c.customer_id IN (
    WITH high_value_orders AS (
        SELECT customer_id
        FROM sales_order
        GROUP BY customer_id
        HAVING COUNT(*) >= 2
    )
    SELECT customer_id
    FROM high_value_orders
);
~~~

Dù cú pháp này hợp lệ trong MySQL 8.0, không nên lồng WITH quá sâu nếu làm truy vấn khó theo dõi. Thường có thể đưa CTE lên đầu câu lệnh chính để người đọc thấy toàn bộ các bước ngay từ đầu.

### 8.3. Tên CTE và tên bảng

Nên chọn tên phản ánh ý nghĩa tập kết quả, ví dụ:

- order_totals
- active_customers
- monthly_revenue
- ranked_products
- overdue_invoices

Tránh tên chung chung như temp1, data2 hoặc result. Tên tốt giúp truy vấn gần với ngôn ngữ nghiệp vụ.

MySQL có quy tắc phân giải tên giữa CTE, derived table, view và bảng. Derived table có thể che khuất CTE; CTE có thể che khuất bảng, temporary table hoặc view trùng tên trong phạm vi câu lệnh. Vì vậy, tránh đặt CTE trùng tên với bảng thật đang được truy vấn; tên riêng có hậu tố như _cte hoặc tên mô tả rõ thường dễ review hơn.

## 9. CTE, derived table, view và temporary table

Các cấu trúc này đều có thể biểu diễn một tập kết quả, nhưng khác nhau về phạm vi và cách sử dụng.

| Đặc điểm | CTE | Derived table | View | Temporary table |
|---|---|---|---|---|
| Cách khai báo | WITH ... AS (...) | Subquery trong FROM | CREATE VIEW | CREATE TEMPORARY TABLE |
| Phạm vi | Một câu lệnh | Một truy vấn chứa nó | Nhiều câu lệnh, nhiều session theo quyền | Session tạo bảng |
| Có tên | Có tên CTE | Alias bắt buộc | Tên schema object | Tên bảng trong session |
| Tái sử dụng | Trong cùng câu lệnh | Thường một vị trí trong FROM | Nhiều câu lệnh | Nhiều câu lệnh trong session |
| Lưu dữ liệu vật lý | Không do người dùng quản lý | Không do người dùng quản lý | Không lưu kết quả riêng theo mặc định | Có lưu tập hàng tạm |
| Index riêng | Không khai báo trực tiếp | Không khai báo trực tiếp | Không khai báo trực tiếp | Có thể tạo index |
| Phù hợp | Chia truy vấn thành bước có tên | Truy vấn con ngắn, dùng một lần | Logic dùng chung lâu dài | Tập trung gian lớn hoặc cần tái sử dụng qua nhiều câu lệnh |

### 9.1. CTE và derived table

Derived table:

~~~sql
SELECT
    x.customer_id,
    x.order_count
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM sales_order
    GROUP BY customer_id
) AS x
WHERE x.order_count >= 2;
~~~

Dùng CTE:

~~~sql
WITH customer_order_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM sales_order
    GROUP BY customer_id
)
SELECT
    customer_id,
    order_count
FROM customer_order_counts
WHERE order_count >= 2;
~~~

Hai cách có thể mô tả cùng logic. CTE hữu ích hơn khi truy vấn có nhiều tầng hoặc cùng tập kết quả được dùng nhiều lần. Derived table phù hợp với một phép biến đổi nhỏ nằm ngay trong FROM.

### 9.2. CTE và view

View được tạo thành object trong database:

~~~sql
CREATE VIEW completed_order_summary AS
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed'
GROUP BY customer_id;
~~~

Sau đó có thể truy vấn view ở nhiều câu lệnh:

~~~sql
SELECT *
FROM completed_order_summary;
~~~

CTE không cần CREATE VIEW và không tồn tại sau câu lệnh. Nếu logic chỉ phục vụ một truy vấn, CTE thường thuận tiện hơn. Nếu nhiều báo cáo hoặc ứng dụng cùng dùng một định nghĩa, view có thể phù hợp hơn.

### 9.3. CTE và temporary table

Temporary table được tạo rõ ràng:

~~~sql
CREATE TEMPORARY TABLE tmp_customer_spending (
    customer_id BIGINT UNSIGNED NOT NULL,
    spending DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id)
);
~~~

Có thể nạp dữ liệu và sử dụng trong nhiều câu lệnh của cùng session. Temporary table có thể có index do người dùng khai báo.

CTE không cho phép khai báo index riêng hay giữ dữ liệu để dùng ở câu lệnh tiếp theo. Nếu cần nhiều bước xử lý trên một tập trung gian lớn và muốn chủ động index nó, temporary table có thể phù hợp hơn.

## 10. Optimizer xử lý CTE như thế nào?

Việc viết CTE thành một khối riêng không đồng nghĩa MySQL luôn tạo bảng tạm. Với CTE không đệ quy, optimizer có thể chọn một trong hai chiến lược chính:

- **Merge:** gộp truy vấn định nghĩa CTE vào truy vấn bên ngoài, tương tự việc mở rộng derived table hoặc view.
- **Materialize:** thực thi truy vấn CTE và lưu kết quả trung gian để truy vấn bên ngoài đọc.

Chiến lược được chọn phụ thuộc cấu trúc truy vấn, khả năng tối ưu và chi phí ước tính.

### 10.1. Khi CTE có thể được merge

Một CTE đơn giản như lọc một bảng và chọn một vài cột có thể được merge:

~~~sql
WITH recent_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM sales_order
    WHERE ordered_at >= '2026-01-01'
)
SELECT
    order_id,
    customer_id
FROM recent_orders
WHERE customer_id = 101;
~~~

Optimizer có thể kết hợp các điều kiện để tạo kế hoạch truy cập trực tiếp sales_order. Khi merge, CTE không nhất thiết tạo một bảng trung gian riêng.

### 10.2. Khi CTE cần materialize

Một số cấu trúc ngăn merge, ví dụ aggregate, GROUP BY, DISTINCT, window function hoặc LIMIT trong các trường hợp được quy định. Khi đó MySQL có thể materialize kết quả trung gian.

Ví dụ:

~~~sql
WITH customer_order_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM sales_order
    GROUP BY customer_id
)
SELECT *
FROM customer_order_counts
WHERE order_count >= 2;
~~~

Bước GROUP BY tạo kết quả tổng hợp. Optimizer có thể cần materialize CTE rồi áp dụng điều kiện ngoài, hoặc thực hiện các tối ưu khác phù hợp.

Materialization có chi phí tạo và đọc tập kết quả. Nếu CTE tạo hàng triệu hàng nhưng truy vấn ngoài chỉ cần một phần nhỏ, hãy cân nhắc đẩy điều kiện lọc vào trong CTE khi điều đó không làm thay đổi ý nghĩa.

### 10.3. CTE được tham chiếu nhiều lần

Khi một CTE không đệ quy được tham chiếu nhiều lần, MySQL có thể materialize một lần rồi tái sử dụng tập kết quả đã materialize. Optimizer có thể tạo các index nội bộ phù hợp cho các cách truy cập khác nhau.

Điều này có thể tiết kiệm việc thực hiện lại cùng phép tổng hợp, nhưng tập kết quả lớn vẫn cần tài nguyên để materialize. Không giả định CTE được tham chiếu nhiều lần luôn nhanh hơn viết lại truy vấn. Hãy đo bằng EXPLAIN và workload thực tế.

### 10.4. CTE không phải cơ chế cache

CTE không lưu kết quả giữa các lần chạy câu lệnh. Nếu cùng câu SQL được thực thi ở hai request, CTE được xử lý trong từng lần thực thi theo kế hoạch của câu lệnh đó.

Nếu cần cache hoặc lưu kết quả tổng hợp, cần một cơ chế riêng như bảng summary, materialized result do ứng dụng quản lý, cache ở tầng ứng dụng hoặc giải pháp phù hợp với kiến trúc.

## 11. Kiểm tra CTE bằng EXPLAIN

Dùng EXPLAIN để xem MySQL dự định thực thi truy vấn như thế nào:

~~~sql
EXPLAIN
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE total_amount >= 2000000;
~~~

Quan sát:

- Bảng nguồn nào được đọc.
- Loại truy cập và index được chọn.
- Ước lượng số hàng.
- Có bước materialize CTE hay không.
- Có temporary table hoặc filesort hay không.
- Điều kiện lọc được đẩy vào bước nào.

Với MySQL 8.0.18 trở lên, EXPLAIN ANALYZE có thể chạy truy vấn và cung cấp số liệu thực tế về thời gian cùng số hàng ở các iterator:

~~~sql
EXPLAIN ANALYZE
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE total_amount >= 2000000;
~~~

EXPLAIN ANALYZE thực sự thực thi câu SELECT. Không dùng tùy tiện với truy vấn nặng hoặc truy vấn có tác dụng phụ. Với UPDATE/DELETE, hãy kiểm tra tập hàng bằng SELECT và dùng quy trình vận hành phù hợp trước khi thay đổi dữ liệu.

Không chỉ nhìn vào việc có dòng Materialize hay không để kết luận tốt/xấu. Materialize có thể hợp lý nếu một tập kết quả được dùng nhiều lần; merge có thể tốt hơn nếu nó cho phép lọc sớm. Hãy đánh giá toàn bộ kế hoạch và thời gian thực tế.

## 12. Những giới hạn và lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Quên alias cho biểu thức tính toán | Cột đầu ra khó tham chiếu hoặc tên không rõ | Đặt alias hoặc khai báo danh sách cột CTE |
| Trùng tên cột đầu ra | Tham chiếu cột mơ hồ hoặc lỗi định nghĩa | Đặt tên cột duy nhất |
| Tham chiếu CTE khai báo phía sau | Không hợp lệ với CTE không đệ quy | Khai báo theo thứ tự phụ thuộc |
| Dùng CTE ở câu lệnh tiếp theo | CTE đã hết phạm vi | Dùng view hoặc temporary table nếu cần tái sử dụng |
| Cho rằng CTE luôn materialize | Hiểu sai kế hoạch thực thi | Kiểm tra EXPLAIN |
| Cho rằng CTE luôn nhanh hơn subquery | Có thể tạo thêm materialization hoặc xử lý thừa | So sánh kế hoạch và workload |
| Dùng SELECT * trong CTE lớn | Mang theo cột không cần thiết | Chỉ chọn các cột truy vấn ngoài sử dụng |
| Đặt mọi logic vào một CTE khổng lồ | Khó đọc và khó kiểm thử | Chia theo bước nghiệp vụ có ý nghĩa |
| Tách quá nhiều CTE nhỏ | Tăng số tầng cần theo dõi | Gộp các bước đơn giản không tạo thêm ý nghĩa |
| Nhầm CTE với temporary table | Mong có index riêng hoặc dùng qua nhiều câu lệnh | Chọn đúng cấu trúc theo phạm vi và vòng đời |
| Không lọc sớm dữ liệu | Tập trung gian có thể quá lớn | Đưa điều kiện phù hợp vào bước nguồn |

### 12.1. Chú ý phiên bản MySQL

CTE được hỗ trợ từ MySQL 8.0. Các ví dụ dùng CTE và window function trong bài cần MySQL 8.0 trở lên. EXPLAIN ANALYZE có từ MySQL 8.0.18.

Kiểm tra phiên bản server:

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Nếu hệ thống đang chạy MySQL 5.7 hoặc cũ hơn, cú pháp WITH của MySQL 8.0 không dùng được. Khi đó có thể cần derived table, view hoặc temporary table tùy mục đích.

## 13. Quy trình thiết kế truy vấn bằng CTE

Khi gặp một truy vấn phức tạp, hãy thực hiện theo trình tự:

1. **Viết kết quả cuối cần có:** xác định một hàng đại diện cho đối tượng nào, cần những cột nào và điều kiện lọc nào.
2. **Xác định các bước nghiệp vụ:** ví dụ tính tiền từng đơn, lọc đơn hoàn tất, tổng hợp theo khách hàng.
3. **Đặt tên từng tập kết quả:** dùng danh từ hoặc cụm từ phản ánh ý nghĩa, không dùng tên tạm chung chung.
4. **Khai báo theo thứ tự phụ thuộc:** CTE nguồn trước, CTE sử dụng nguồn sau.
5. **Chỉ chọn cột cần thiết:** tránh SELECT * khi dữ liệu trung gian rộng.
6. **Đặt alias rõ ràng:** mỗi biểu thức tính toán cần tên dễ hiểu.
7. **Kiểm tra từng bước:** chạy SELECT của CTE riêng để xác nhận số hàng và giá trị.
8. **Ghép truy vấn chính:** JOIN hoặc lọc các CTE để tạo kết quả cuối.
9. **Đo kế hoạch:** dùng EXPLAIN, và EXPLAIN ANALYZE khi phù hợp.
10. **So sánh phương án:** nếu CTE bị materialize quá lớn, thử đẩy điều kiện lọc sớm hơn hoặc dùng temporary table có index khi cần tái sử dụng.

## 14. Bài tập thực hành

### Bài 1: CTE cơ bản

Dùng WITH tạo CTE chứa các đơn đã hoàn tất từ sales_order. Truy vấn CTE để lấy order_id, customer_id và ordered_at. Thêm điều kiện chỉ lấy đơn từ tháng 1 năm 2026.

### Bài 2: Đặt tên cột đầu ra

Tạo CTE tính số dòng hàng và tổng giá trị của từng đơn. Khai báo danh sách cột ngay sau tên CTE. Thử cố tình khai báo sai số lượng cột và quan sát lỗi.

### Bài 3: Kết hợp nhiều CTE

Tạo order_totals, completed_orders và customer_totals. Lấy khách hàng có tổng chi tiêu lớn hơn 2 triệu. Giải thích mỗi CTE chịu trách nhiệm phần logic nào.

### Bài 4: Tái sử dụng CTE

Tạo CTE completed_orders rồi tham chiếu nó trong hai subquery để tính tổng số đơn hoàn tất và số khách hàng đã đặt đơn. Kiểm tra kế hoạch thực thi.

### Bài 5: CTE với UPDATE

Dùng CTE tính tổng giá trị đơn hoàn tất theo khách hàng. Cập nhật customer.lifetime_value. Trước khi UPDATE, chạy SELECT tương đương và ghi lại số hàng dự kiến bị thay đổi.

### Bài 6: CTE với DELETE

Tạo CTE xác định đơn thử nghiệm đã hủy. Truy vấn danh sách trước, sau đó thực hiện DELETE trên database thực hành. Kiểm tra tác động của foreign key.

### Bài 7: So sánh CTE và derived table

Viết cùng một truy vấn theo hai cách: derived table và CTE. Dùng EXPLAIN để so sánh kế hoạch. Giải thích khi nào cách viết CTE dễ đọc hơn.

### Bài 8: Tìm CTE cần materialize

Viết một CTE có GROUP BY và được tham chiếu nhiều lần. Quan sát EXPLAIN để tìm bước materialization nếu có. Đánh giá số hàng trung gian và chi phí.

### Bài 9: Báo cáo doanh thu theo tháng

Tạo CTE tính tổng tiền theo đơn, sau đó CTE thứ hai tính doanh thu theo tháng. Mở rộng để tính số đơn và giá trị đơn trung bình.

### Bài 10: Refactor truy vấn nhiều tầng

Chọn một truy vấn lồng nhiều subquery trong dự án cá nhân. Tách các bước có ý nghĩa thành CTE, giữ nguyên kết quả và so sánh EXPLAIN trước/sau.

## Kết luận

CTE cho phép đặt tên tập kết quả trung gian ngay trong câu lệnh SQL bằng WITH. Cấu trúc này giúp chia truy vấn phức tạp thành các bước có ý nghĩa, giảm lặp logic và làm cho việc đọc, review, kiểm tra từng phần dễ hơn.

CTE chỉ có phạm vi trong một câu lệnh và không phải bảng vật lý. MySQL có thể merge hoặc materialize CTE tùy cấu trúc và kế hoạch tối ưu. Hãy đặt tên rõ ràng, khai báo theo thứ tự phụ thuộc, chọn đúng cột và kiểm tra bằng EXPLAIN. Khi cần lưu kết quả qua nhiều câu lệnh hoặc chủ động tạo index cho dữ liệu trung gian, hãy cân nhắc view hoặc temporary table.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — WITH (Common Table Expressions): https://dev.mysql.com/doc/refman/8.4/en/with.html
- MySQL 8.4 Reference Manual — Derived Table Optimization: https://dev.mysql.com/doc/refman/8.4/en/derived-table-optimization.html
- MySQL 8.4 Reference Manual — EXPLAIN Statement: https://dev.mysql.com/doc/refman/8.4/en/explain.html
- MySQL 8.4 Reference Manual — EXPLAIN ANALYZE: https://dev.mysql.com/doc/refman/8.4/en/explain.html#explain-analyze

