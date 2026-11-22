# Viết báo cáo có CTE, hàm cửa sổ, xếp hạng và tổng phụ

Một báo cáo vận hành thường cần kết hợp nhiều phép xử lý: lọc dữ liệu theo thời gian, gom doanh thu theo tháng và khu vực, xếp hạng nhóm bán chạy, so sánh với tháng trước, tính lũy kế và hiển thị tổng phụ. Nếu viết tất cả trong một truy vấn lồng nhiều tầng, SQL sẽ khó đọc và khó kiểm chứng. MySQL 8.0 cung cấp Common Table Expression (CTE) và window functions để chia bài toán thành các bước có tên, đồng thời giữ được ngữ cảnh của từng hàng khi tính thứ hạng và số liệu theo cửa sổ.

Bài thực hành này xây dựng báo cáo doanh thu theo tháng, khu vực và danh mục sản phẩm. Ta sẽ dùng CTE để lọc và tổng hợp, recursive CTE để tạo đủ các tháng trong kỳ kể cả tháng không phát sinh giao dịch, hàm cửa sổ để xếp hạng và tính biến động, rồi dùng `WITH ROLLUP` cùng `GROUPING()` để tạo tổng phụ. Ví dụ hướng đến MySQL 8.0 trở lên; các tính năng CTE và window functions cần phiên bản hỗ trợ.

## 1. Mô tả bài toán và quy tắc tính

Một nhóm thương mại điện tử cần báo cáo hàng tháng theo từng khu vực và danh mục sản phẩm. Báo cáo phải trả lời:

- Mỗi tháng, mỗi khu vực, danh mục nào có doanh thu cao nhất?
- Doanh thu tháng hiện tại tăng hay giảm so với tháng liền trước?
- Doanh thu lũy kế từ đầu kỳ là bao nhiêu?
- Trung bình doanh thu của ba tháng gần nhất là bao nhiêu?
- Mỗi khu vực có tổng doanh thu bao nhiêu, và toàn hệ thống có tổng bao nhiêu?
- Tháng không có đơn hàng có được hiển thị với doanh thu bằng 0 không?

Quy ước nghiệp vụ trong ví dụ:

1. Chỉ tính đơn có `status = 'COMPLETED'`.
2. Doanh thu dòng hàng bằng `quantity * unit_price * (1 - discount_percent / 100)`.
3. Doanh thu được tổng hợp theo tháng của `ordered_at`, khu vực của khách hàng và danh mục của sản phẩm.
4. `from_date` được tính bao gồm, `to_date` là mốc kết thúc không bao gồm: `ordered_at >= from_date AND ordered_at < to_date`.
5. Tháng không phát sinh giao dịch được đưa vào chuỗi tháng và có doanh thu 0 để `LAG()` và rolling average phản ánh đúng các tháng lịch liên tiếp.
6. Thứ hạng được tính trong từng cặp tháng/khu vực. Khi doanh thu bằng nhau, `RANK()` cho cùng thứ hạng; `ROW_NUMBER()` dùng thêm mã danh mục để tạo thứ tự ổn định.

## 2. Tạo schema mẫu

Ta dùng các bảng khu vực, khách hàng, danh mục, sản phẩm, đơn hàng và dòng đơn hàng. Tất cả bảng giao dịch dùng InnoDB để có transaction và foreign key.

```sql
CREATE DATABASE IF NOT EXISTS sales_lab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE sales_lab;

CREATE TABLE regions (
    region_code VARCHAR(10) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (region_code)
) ENGINE = InnoDB;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY ix_customers_region (region_code),
    CONSTRAINT fk_customers_region
      FOREIGN KEY (region_code) REFERENCES regions (region_code)
) ENGINE = InnoDB;

CREATE TABLE product_categories (
    category_code VARCHAR(30) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (category_code)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    category_code VARCHAR(30) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (product_id),
    KEY ix_products_category (category_code),
    CONSTRAINT fk_products_category
      FOREIGN KEY (category_code) REFERENCES product_categories (category_code)
) ENGINE = InnoDB;

CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    ordered_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_status_date_customer (status, ordered_at, customer_id),
    CONSTRAINT fk_orders_customer
      FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
) ENGINE = InnoDB;

CREATE TABLE sales_order_items (
    order_item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (order_item_id),
    KEY ix_order_items_order_product (order_id, product_id),
    KEY ix_order_items_product (product_id),
    CONSTRAINT chk_order_items_discount
      CHECK (discount_percent >= 0 AND discount_percent <= 100),
    CONSTRAINT fk_order_items_order
      FOREIGN KEY (order_id) REFERENCES sales_orders (order_id),
    CONSTRAINT fk_order_items_product
      FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE = InnoDB;
```

`CHECK` constraint được MySQL thực thi từ 8.0.16. Nếu dùng phiên bản cũ hơn, cần kiểm tra giới hạn của server và bảo đảm discount hợp lệ ở tầng ứng dụng hoặc bằng cơ chế tương thích. Collation `utf8mb4_0900_ai_ci` yêu cầu MySQL 8.0; nếu môi trường cũ hơn, chọn collation có hỗ trợ và đánh giá lại quy tắc so sánh.

Các index trong ví dụ phục vụ đường join và bộ lọc chính. Index `(status, ordered_at, customer_id)` có thể hỗ trợ lọc đơn theo trạng thái và khoảng thời gian, nhưng tính hiệu quả còn phụ thuộc cardinality, phân bố trạng thái và query plan. Không nên coi index mẫu là tối ưu cho mọi workload.

## 3. Nạp dữ liệu minh họa

```sql
INSERT INTO regions (region_code, region_name) VALUES
('NORTH', 'Miền Bắc'),
('CENTRAL', 'Miền Trung'),
('SOUTH', 'Miền Nam');

INSERT INTO customers (customer_id, region_code, email) VALUES
(1, 'NORTH', 'an@example.test'),
(2, 'NORTH', 'binh@example.test'),
(3, 'CENTRAL', 'chi@example.test'),
(4, 'SOUTH', 'dung@example.test');

INSERT INTO product_categories (category_code, category_name) VALUES
('BOOK', 'Sách'),
('HOME', 'Gia dụng'),
('TECH', 'Thiết bị công nghệ');

INSERT INTO products (product_id, category_code, product_name) VALUES
(101, 'BOOK', 'MySQL thực hành'),
(102, 'HOME', 'Đèn bàn'),
(103, 'TECH', 'Bàn phím cơ');

INSERT INTO sales_orders (order_id, customer_id, ordered_at, status) VALUES
(1001, 1, '2026-01-05 09:15:00', 'COMPLETED'),
(1002, 1, '2026-01-20 14:30:00', 'COMPLETED'),
(1003, 2, '2026-02-03 10:00:00', 'COMPLETED'),
(1004, 3, '2026-02-14 11:20:00', 'COMPLETED'),
(1005, 4, '2026-03-01 08:00:00', 'COMPLETED'),
(1006, 4, '2026-03-15 16:45:00', 'CANCELLED');

INSERT INTO sales_order_items
    (order_item_id, order_id, product_id, quantity, unit_price, discount_percent)
VALUES
(1, 1001, 101, 2, 100.00, 0.00),
(2, 1001, 103, 1, 500.00, 10.00),
(3, 1002, 102, 1, 300.00, 0.00),
(4, 1003, 101, 1, 100.00, 0.00),
(5, 1003, 103, 1, 500.00, 0.00),
(6, 1004, 102, 2, 300.00, 0.00),
(7, 1005, 103, 1, 500.00, 20.00),
(8, 1006, 101, 10, 100.00, 0.00);
```

Trong dữ liệu mẫu, đơn `1006` đã hủy nên không được tính. Đơn `1001` có hai dòng thuộc hai danh mục khác nhau. Khi đếm đơn hàng theo danh mục, cần `COUNT(DISTINCT order_id)` vì một đơn có thể có nhiều dòng cùng danh mục.

Với kỳ `2026-01-01` đến trước `2026-04-01`, tổng doanh thu kỳ vọng của dữ liệu mẫu là `2550.00`: tháng 1 là `950.00`, tháng 2 là `1200.00`, tháng 3 là `400.00`. Theo khu vực, NORTH có `1550.00`, CENTRAL có `600.00` và SOUTH có `400.00`. Các giá trị này giúp đối chiếu kết quả tổng hợp và `WITH ROLLUP` ở các phần sau.

Kiểm tra dữ liệu ban đầu:

```sql
SELECT status, COUNT(*) AS order_count
FROM sales_orders
GROUP BY status;

SELECT
    oi.order_id,
    p.category_code,
    SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100)) AS line_revenue
FROM sales_order_items AS oi
JOIN products AS p ON p.product_id = oi.product_id
GROUP BY oi.order_id, p.category_code
ORDER BY oi.order_id, p.category_code;
```

## 4. Bước đầu: tổng hợp doanh thu bằng GROUP BY

Trước khi thêm CTE và window functions, hãy tạo truy vấn tổng hợp cơ bản:

```sql
SELECT
    CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
    c.region_code,
    p.category_code,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS units_sold,
    CAST(
        SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100))
        AS DECIMAL(20, 2)
    ) AS revenue
FROM sales_orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id
JOIN sales_order_items AS oi ON oi.order_id = o.order_id
JOIN products AS p ON p.product_id = oi.product_id
WHERE o.status = 'COMPLETED'
  AND o.ordered_at >= '2026-01-01'
  AND o.ordered_at <  '2026-04-01'
GROUP BY
    CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE),
    c.region_code,
    p.category_code
ORDER BY month_start, c.region_code, p.category_code;
```

Điều kiện ngày dùng khoảng nửa mở (`>=` và `<`) để bao gồm đầy đủ thời điểm trong ngày cuối cùng mà không phải tạo giá trị `23:59:59.999999`. Tránh bọc `ordered_at` trong `DATE()` ở `WHERE` nếu muốn optimizer sử dụng range access trên index ngày.

Kết quả chỉ chứa tổ hợp tháng/khu vực/danh mục có doanh thu. Nếu một danh mục không bán trong tháng 2, hàng của danh mục đó sẽ không xuất hiện. Điều này làm `LAG()` trên kết quả thưa có thể so sánh với tháng có dữ liệu gần nhất thay vì tháng lịch ngay trước đó. Ta sẽ tạo date spine và grid đầy đủ để xử lý vấn đề này.

## 5. CTE giúp chia báo cáo thành các bước

CTE được khai báo bằng `WITH` và chỉ tồn tại trong phạm vi một câu lệnh. Mỗi CTE có tên, có thể được truy vấn như một bảng logic:

```sql
WITH monthly_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        SUM(oi.quantity * oi.unit_price) AS revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE o.status = 'COMPLETED'
    GROUP BY month_start, c.region_code, p.category_code
)
SELECT *
FROM monthly_sales
ORDER BY month_start, region_code, category_code;
```

Lợi ích chính của CTE là đặt tên cho từng bước như `filtered_orders`, `monthly_sales`, `dense_sales` hoặc `ranked_sales`. Nhờ đó, truy vấn tổng hợp có thể được đọc và kiểm tra theo từng tầng. CTE không mặc nhiên làm query nhanh hơn subquery hoặc temporary table; MySQL có thể merge CTE vào query ngoài hoặc materialize tùy cấu trúc và optimizer. Hãy kiểm tra execution plan thay vì chọn CTE chỉ vì cú pháp mới.

## 6. Tạo chuỗi tháng bằng recursive CTE

Để tính biến động tháng liền trước, cần có một hàng cho mọi tháng trong kỳ. Recursive CTE tạo các tháng từ tháng bắt đầu đến tháng chứa ngày trước `to_date`.

Đặt tham số cho ví dụ:

```sql
SET @from_date = '2026-01-01';
SET @to_date = '2026-04-01'; -- exclusive
SET @top_n = 3;
```

Kiểm tra `from_date < to_date` trước khi chạy báo cáo. CTE tháng:

```sql
WITH RECURSIVE
params AS (
    SELECT
        CAST(@from_date AS DATE) AS from_date,
        CAST(@to_date AS DATE) AS to_date
),
month_series (month_start) AS (
    SELECT CAST(DATE_FORMAT(p.from_date, '%Y-%m-01') AS DATE)
    FROM params AS p
    WHERE p.from_date < p.to_date

    UNION ALL

    SELECT DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
    FROM month_series AS ms
    CROSS JOIN params AS p
    WHERE DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
          <= CAST(
              DATE_FORMAT(DATE_SUB(p.to_date, INTERVAL 1 DAY), '%Y-%m-01')
              AS DATE
          )
)
SELECT month_start
FROM month_series
ORDER BY month_start;
```

Với `@from_date = '2026-01-01'` và `@to_date = '2026-04-01'`, kết quả là ba tháng 1, 2 và 3. Nếu `to_date` là `2026-03-15`, tháng 3 vẫn được đưa vào vì khoảng thời gian có chứa ngày trong tháng 3.

Nếu `from_date` hoặc `to_date` nằm giữa tháng, tháng đầu/cuối trong báo cáo là tháng một phần. Khi so sánh MoM, cần cân nhắc so sánh cùng số ngày hoặc chỉ phát hành số liệu sau khi tháng hoàn tất; `LAG()` chỉ đảm bảo so sánh hai bucket tháng liên tiếp, không tự điều chỉnh độ dài kỳ.

Recursive CTE chịu giới hạn `cte_max_recursion_depth` (mặc định thường là 1000). Nếu báo cáo cần hàng chục năm hoặc lịch phức tạp, nên dùng bảng calendar dimension đã được nạp trước thay vì tạo chuỗi dài cho từng request. Không tăng recursion limit vô hạn.

## 7. Báo cáo đầy đủ với CTE và hàm cửa sổ

Truy vấn dưới đây kết hợp các bước:

1. `params`: chuẩn hóa khoảng ngày.
2. `month_series`: sinh tháng liên tiếp.
3. `region_dim`, `category_dim`: lấy các chiều báo cáo.
4. `monthly_sales`: tính doanh thu, số đơn và số lượng đã bán.
5. `report_grid`: tạo mọi tổ hợp tháng/khu vực/danh mục.
6. `dense_sales`: gán 0 cho tổ hợp không có giao dịch.
7. `windowed_sales`: xếp hạng, so sánh tháng trước và tính lũy kế/trung bình trượt.

```sql
WITH RECURSIVE
params AS (
    SELECT
        CAST(@from_date AS DATE) AS from_date,
        CAST(@to_date AS DATE) AS to_date
),
month_series (month_start) AS (
    SELECT CAST(DATE_FORMAT(p.from_date, '%Y-%m-01') AS DATE)
    FROM params AS p
    WHERE p.from_date < p.to_date

    UNION ALL

    SELECT DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
    FROM month_series AS ms
    CROSS JOIN params AS p
    WHERE DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
          <= CAST(
              DATE_FORMAT(DATE_SUB(p.to_date, INTERVAL 1 DAY), '%Y-%m-01')
              AS DATE
          )
),
region_dim AS (
    SELECT region_code
    FROM regions
),
category_dim AS (
    SELECT category_code
    FROM product_categories
),
monthly_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        COUNT(DISTINCT o.order_id) AS order_count,
        SUM(oi.quantity) AS units_sold,
        CAST(
            SUM(
                oi.quantity * oi.unit_price
                * (1 - oi.discount_percent / 100)
            ) AS DECIMAL(20, 2)
        ) AS revenue
    FROM params AS prm
    JOIN sales_orders AS o
      ON o.ordered_at >= prm.from_date
     AND o.ordered_at < prm.to_date
     AND o.status = 'COMPLETED'
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    GROUP BY
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE),
        c.region_code,
        p.category_code
),
report_grid AS (
    SELECT
        ms.month_start,
        r.region_code,
        cat.category_code
    FROM month_series AS ms
    CROSS JOIN region_dim AS r
    CROSS JOIN category_dim AS cat
),
dense_sales AS (
    SELECT
        g.month_start,
        g.region_code,
        g.category_code,
        COALESCE(s.order_count, 0) AS order_count,
        COALESCE(s.units_sold, 0) AS units_sold,
        COALESCE(s.revenue, CAST(0 AS DECIMAL(20, 2))) AS revenue
    FROM report_grid AS g
    LEFT JOIN monthly_sales AS s
      ON s.month_start = g.month_start
     AND s.region_code = g.region_code
     AND s.category_code = g.category_code
),
windowed_sales AS (
    SELECT
        month_start,
        region_code,
        category_code,
        order_count,
        units_sold,
        revenue,
        RANK() OVER (
            PARTITION BY month_start, region_code
            ORDER BY revenue DESC
        ) AS category_rank,
        DENSE_RANK() OVER (
            PARTITION BY month_start, region_code
            ORDER BY revenue DESC
        ) AS category_dense_rank,
        ROW_NUMBER() OVER (
            PARTITION BY month_start, region_code
            ORDER BY revenue DESC, category_code
        ) AS category_row_number,
        LAG(revenue) OVER (
            PARTITION BY region_code, category_code
            ORDER BY month_start
        ) AS previous_month_revenue,
        SUM(revenue) OVER (
            PARTITION BY region_code, category_code
            ORDER BY month_start
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue,
        AVG(revenue) OVER (
            PARTITION BY region_code, category_code
            ORDER BY month_start
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS trailing_3_month_avg
    FROM dense_sales
)
SELECT
    month_start,
    region_code,
    category_code,
    order_count,
    units_sold,
    revenue,
    category_rank,
    category_dense_rank,
    category_row_number,
    previous_month_revenue,
    revenue - previous_month_revenue AS revenue_change,
    ROUND(
        100 * (revenue - previous_month_revenue)
        / NULLIF(previous_month_revenue, 0),
        2
    ) AS revenue_change_percent,
    cumulative_revenue,
    ROUND(trailing_3_month_avg, 2) AS trailing_3_month_avg
FROM windowed_sales
WHERE category_rank <= @top_n
ORDER BY month_start, region_code, category_rank, category_code;
```

### Đọc kết quả

- `category_rank`: hạng có khoảng trống khi đồng hạng, ví dụ 1, 1, 3.
- `category_dense_rank`: hạng không có khoảng trống, ví dụ 1, 1, 2.
- `category_row_number`: số thứ tự duy nhất, dùng `category_code` làm tiêu chí phá hòa.
- `previous_month_revenue`: doanh thu của tháng lịch ngay trước vì `dense_sales` có đủ tháng.
- `revenue_change`: chênh lệch doanh thu so với tháng trước.
- `revenue_change_percent`: phần trăm thay đổi; trả `NULL` khi doanh thu tháng trước bằng 0 để tránh chia cho 0.
- `cumulative_revenue`: tổng doanh thu từ tháng đầu kỳ đến tháng hiện tại theo khu vực/danh mục.
- `trailing_3_month_avg`: trung bình doanh thu của tháng hiện tại và tối đa hai tháng trước.

Ở tháng đầu tiên, `LAG()` trả `NULL` vì chưa có hàng trước. Nếu tháng trước có doanh thu bằng 0, phần trăm thay đổi cũng là `NULL`; nghiệp vụ có thể hiển thị nhãn “mới phát sinh” thay vì một tỷ lệ phần trăm vô hạn.

`RANK()` được lọc ở truy vấn ngoài vì window function được tính sau `WHERE` trong cùng query block. Nếu lọc `category_rank <= @top_n`, các danh mục đồng hạng tại ngưỡng có thể khiến số hàng lớn hơn N. Nếu yêu cầu đúng tối đa N danh mục, thay điều kiện bằng `category_row_number <= @top_n`.

## 8. Hiểu đúng thứ tự xử lý của window function

Window function tính trên các hàng sau khi `FROM`, `WHERE`, `GROUP BY` và `HAVING` của query block đã tạo tập kết quả. Nó giữ từng hàng trong tập thay vì gom nhiều hàng thành một như `GROUP BY`.

| Thành phần | Ý nghĩa |
|---|---|
| `PARTITION BY` | Chia tập kết quả thành các nhóm độc lập để tính cửa sổ. |
| `ORDER BY` trong `OVER` | Xác định thứ tự hàng bên trong mỗi partition. |
| `ROWS`/`RANGE` frame | Xác định những hàng thuộc cửa sổ của hàng hiện tại. |
| `RANK()` | Xếp hạng, có khoảng trống sau đồng hạng. |
| `DENSE_RANK()` | Xếp hạng, không có khoảng trống sau đồng hạng. |
| `ROW_NUMBER()` | Gán số thứ tự duy nhất theo thứ tự đã khai báo. |
| `LAG()`/`LEAD()` | Đọc giá trị ở hàng trước/sau trong partition. |
| `SUM() OVER` | Tính tổng cửa sổ, có thể dùng cho running total. |
| `AVG() OVER` | Tính trung bình cửa sổ, ví dụ moving average. |

Không có `ORDER BY` trong `OVER` thì thứ tự hàng không được xác định cho các hàm cần thứ tự. Khi cần kết quả lặp lại ổn định, thêm cột phá hòa như primary key hoặc mã danh mục. `ORDER BY` ở cuối câu lệnh chỉ sắp xếp kết quả trả về; nó không thay thế `ORDER BY` trong cửa sổ.

### ROWS và RANGE

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` lấy tối đa ba hàng vật lý theo thứ tự của partition. Trong ví dụ, grid tạo một hàng cho mỗi tháng/khu vực/danh mục, nên ba hàng tương ứng ba tháng liên tiếp.

`RANGE` xác định frame theo giá trị của sort key và có quy tắc xử lý peer rows. Với báo cáo tháng, dùng `ROWS` sau khi đã chuẩn hóa thành một hàng cho mỗi tháng thường dễ suy luận hơn. Nếu dùng dữ liệu thưa hoặc có nhiều hàng cùng thời điểm, cần xác định rõ frame mong muốn.

## 9. Tạo tổng phụ bằng WITH ROLLUP và GROUPING()

Window functions tính chỉ số trên từng hàng chi tiết; `WITH ROLLUP` bổ sung hàng tổng phụ cho các cấp nhóm. Với thứ tự nhóm `month_start, region_code, category_code`, MySQL tạo:

1. Tổng chi tiết theo tháng/khu vực/danh mục.
2. Tổng phụ theo tháng/khu vực.
3. Tổng theo tháng.
4. Tổng toàn kỳ.

Truy vấn tổng phụ độc lập:

```sql
WITH filtered_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        CAST(
            SUM(
                oi.quantity * oi.unit_price
                * (1 - oi.discount_percent / 100)
            ) AS DECIMAL(20, 2)
        ) AS revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE o.status = 'COMPLETED'
      AND o.ordered_at >= @from_date
      AND o.ordered_at < @to_date
    GROUP BY
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE),
        c.region_code,
        p.category_code
),
subtotal_rows AS (
    SELECT
        month_start,
        region_code,
        category_code,
        SUM(revenue) AS revenue,
        GROUPING(month_start) AS g_month,
        GROUPING(region_code) AS g_region,
        GROUPING(category_code) AS g_category
    FROM filtered_sales
    GROUP BY month_start, region_code, category_code WITH ROLLUP
)
SELECT
    CASE
        WHEN g_month = 1 THEN 'GRAND TOTAL'
        WHEN g_region = 1 THEN 'MONTH TOTAL'
        WHEN g_category = 1 THEN 'REGION SUBTOTAL'
        ELSE 'DETAIL'
    END AS row_type,
    month_start,
    region_code,
    category_code,
    revenue
FROM subtotal_rows
ORDER BY
    g_month,
    month_start,
    g_region,
    region_code,
    g_category,
    category_code;
```

`WITH ROLLUP` tạo giá trị `NULL` ở các cột được tổng hợp lên cấp cao hơn. Nhưng dữ liệu gốc cũng có thể có `NULL`; `GROUPING(column)` trả 1 nếu `NULL` đó được tạo ra do rollup và 0 nếu là giá trị của nhóm dữ liệu. Dùng cờ `g_month`, `g_region`, `g_category` để phân biệt rõ hàng chi tiết, tổng khu vực, tổng tháng và tổng toàn kỳ.

Thứ tự cột trong `GROUP BY ... WITH ROLLUP` quyết định thứ bậc tổng phụ. Nếu đổi thành `GROUP BY region_code, month_start, category_code WITH ROLLUP`, cấp tổng được tạo ra sẽ khác. Hãy thiết kế thứ tự nhóm theo cấu trúc báo cáo.

## 10. Kết hợp window functions và tổng phụ

Không nhất thiết phải trộn `WITH ROLLUP` và window functions trong cùng query block. Cách dễ kiểm soát hơn là:

- CTE thứ nhất tạo dữ liệu chi tiết và các chỉ số window.
- Query khác hoặc CTE tiếp theo gom các hàng chi tiết thành tổng phụ.
- Nếu cần một dataset duy nhất, có thể `UNION ALL` hàng chi tiết với hàng tổng phụ, đồng thời thêm cột `row_type` để người dùng báo cáo biết cách hiển thị.

Không cộng lại các hàng đã có subtotal với hàng chi tiết, vì sẽ đếm doanh thu hai lần. Khi cần tổng toàn kỳ từ dữ liệu có subtotal, lọc đúng `GROUPING` flags hoặc tính từ CTE chi tiết trước khi thêm rollup.

## 11. Tối ưu truy vấn và kiểm tra execution plan

CTE giúp tổ chức logic, nhưng báo cáo vẫn có thể tốn tài nguyên do join nhiều bảng, `COUNT(DISTINCT)`, cross join grid, sort và window partition.

### Kiểm tra index và bộ lọc

Truy vấn lọc theo `status` và khoảng `ordered_at`, sau đó join theo `customer_id`, `order_id`, `product_id`. Các index mẫu gồm:

| Bảng | Index | Vai trò |
|---|---|---|
| `sales_orders` | `(status, ordered_at, customer_id)` | Lọc theo trạng thái và khoảng ngày, có customer id để join. |
| `sales_order_items` | `(order_id, product_id)` | Tìm dòng hàng theo đơn và product. |
| `sales_order_items` | `(product_id)` | Hỗ trợ chiều join từ product nếu optimizer chọn hướng đó. |
| `customers` | `(region_code)` | Hỗ trợ truy vấn/nhóm theo khu vực khi cần. |
| `products` | `(category_code)` | Hỗ trợ truy vấn theo danh mục. |

Index có chi phí ghi và dung lượng. Dựa trên `EXPLAIN`, số hàng ước lượng, cardinality và query workload để quyết định. Một index mới không nhất thiết được dùng nếu bộ lọc chọn quá nhiều hàng hoặc optimizer có ước lượng khác.

### Dùng EXPLAIN

```sql
EXPLAIN FORMAT=TREE
WITH monthly_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        SUM(oi.quantity * oi.unit_price) AS revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE o.status = 'COMPLETED'
      AND o.ordered_at >= '2026-01-01'
      AND o.ordered_at < '2026-04-01'
    GROUP BY month_start, c.region_code, p.category_code
)
SELECT * FROM monthly_sales;
```

`EXPLAIN FORMAT=TREE` có trên các phiên bản MySQL 8.0 hỗ trợ; nếu phiên bản không hỗ trợ định dạng TREE, dùng `EXPLAIN` mặc định. Trên phiên bản hỗ trợ, `EXPLAIN ANALYZE` thực thi câu truy vấn để đo số hàng và thời gian thực tế; chỉ dùng trên môi trường kiểm thử hoặc sau khi đánh giá tác động của query.

Kiểm tra:

- Bảng `sales_orders` có dùng range/index access cho khoảng ngày không?
- Có full table scan trên bảng lớn không, và đó có thực sự là vấn đề với selectivity hiện tại không?
- Join có dùng primary/foreign key index phù hợp không?
- Số hàng sau join có tăng bất thường do quan hệ một-nhiều không?
- Sort/materialize/windowing có tạo temporary table lớn không?
- CTE nào bị materialize và có bị đọc lặp lại không?

### Giới hạn kích thước grid

`report_grid` tạo số hàng bằng:

\[
N_{grid} = N_{months} \times N_{regions} \times N_{categories}
\]

Ví dụ 36 tháng × 20 khu vực × 50 danh mục tạo 36.000 hàng trước khi tính window. Nếu có hàng nghìn tenant hoặc hàng chục nghìn category, cross join có thể quá lớn. Khi đó:

- Lọc region/category theo phạm vi báo cáo trước khi tạo grid.
- Dùng calendar dimension và dimension table đã chuẩn hóa.
- Chỉ tạo tổ hợp có liên quan, hoặc dùng bảng snapshot/reporting mart.
- Tính theo batch thời gian và lưu kết quả tổng hợp nếu báo cáo chạy thường xuyên.
- Giới hạn khoảng ngày được phép trên endpoint báo cáo.

Nếu không cần hiển thị tháng không có doanh thu, có thể bỏ `month_series` và `report_grid`, dùng trực tiếp `monthly_sales`; nhưng khi đó `LAG()` so sánh với hàng trước có dữ liệu, không nhất thiết là tháng lịch ngay trước.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `GROUP BY` để tính running total | Làm mất các hàng chi tiết cần giữ trong báo cáo. | Dùng `SUM() OVER (...)` với frame rõ ràng. |
| Dùng `LAG()` trên dữ liệu tháng thưa | So sánh với tháng gần nhất có dữ liệu, có thể bỏ qua tháng không phát sinh. | Tạo date spine và grid đầy đủ hoặc mô tả rõ semantics. |
| Dùng `RANK()` nhưng kỳ vọng đúng N hàng | Đồng hạng có thể trả hơn N hàng. | Dùng `ROW_NUMBER()` với tiêu chí phá hòa ổn định. |
| Đặt điều kiện window alias trong `WHERE` cùng query block | Window function chưa được tính tại giai đoạn `WHERE`. | Đưa window result vào CTE/subquery rồi lọc ở query ngoài. |
| Chia cho doanh thu tháng trước bằng 0 | Lỗi chia cho 0 hoặc kết quả không có ý nghĩa. | Dùng `NULLIF(previous_month_revenue, 0)`. |
| Không dùng `COUNT(DISTINCT order_id)` | Một đơn có nhiều dòng cùng category bị đếm lặp. | Xác định grain của báo cáo trước khi đếm. |
| Coi `WITH ROLLUP` NULL là dữ liệu gốc | Nhãn tổng phụ bị nhầm với nhóm có key NULL. | Dùng `GROUPING()` để phân biệt. |
| Cộng cả detail và subtotal | Tổng doanh thu bị nhân đôi. | Tách dataset detail/subtotal hoặc lọc grouping flags. |
| Tạo cross join grid không giới hạn | Số hàng trung gian tăng rất nhanh. | Giới hạn date range/dimensions hoặc dùng summary table. |
| Coi CTE luôn nhanh hơn subquery | Có thể materialize và tăng I/O/temp space. | Kiểm tra execution plan và đo với dữ liệu thật. |
| Dùng `DATE(ordered_at)` trong điều kiện lọc | Có thể làm mất range access trên index ngày. | Dùng khoảng ngày nửa mở trên cột gốc. |

## 13. Kiểm thử kết quả báo cáo

Không chỉ kiểm tra câu SQL chạy không lỗi. Cần xác nhận kết quả đúng với quy tắc nghiệp vụ:

1. Đơn `CANCELLED` không được tính.
2. Một đơn có nhiều dòng cùng danh mục chỉ được đếm một lần trong `order_count` của danh mục đó.
3. Discount được áp dụng trước khi cộng doanh thu.
4. `to_date` không được tính vào kỳ báo cáo.
5. Mỗi tháng/khu vực/danh mục trong grid xuất hiện đúng một hàng.
6. Tổ hợp không có giao dịch có `order_count = 0`, `units_sold = 0`, `revenue = 0`.
7. `LAG()` trỏ đến tháng lịch liền trước, kể cả tháng trước có doanh thu 0.
8. `RANK()` xử lý đồng hạng; `ROW_NUMBER()` có thứ tự ổn định.
9. Running total bằng tổng các tháng từ đầu kỳ đến hàng hiện tại.
10. Tổng phụ theo khu vực và tổng toàn kỳ bằng tổng các hàng chi tiết tương ứng.

### Đối soát bằng truy vấn tổng

Tính doanh thu toàn kỳ trực tiếp:

```sql
SELECT
    CAST(
        SUM(
            oi.quantity * oi.unit_price
            * (1 - oi.discount_percent / 100)
        ) AS DECIMAL(20, 2)
    ) AS expected_total
FROM sales_orders AS o
JOIN sales_order_items AS oi ON oi.order_id = o.order_id
WHERE o.status = 'COMPLETED'
  AND o.ordered_at >= @from_date
  AND o.ordered_at < @to_date;
```

So sánh với tổng toàn kỳ trong kết quả `WITH ROLLUP`. Nếu khác nhau, kiểm tra join có làm nhân dòng, dimension bị thiếu, trạng thái đơn hàng và khoảng thời gian. Vì `sales_order_items` là grain dòng hàng, truy vấn tổng trực tiếp ở trên không cần join customers/products nếu không lọc theo các bảng đó.

### Kiểm tra số hàng của grid

```sql
SELECT
    (SELECT COUNT(*) FROM regions)
    * (SELECT COUNT(*) FROM product_categories) AS dimension_combinations;
```

Nhân với số tháng trong `month_series` để ước lượng số hàng trước khi chạy window. Với báo cáo production, nên ghi lại số hàng ước lượng và thời gian chạy ở khoảng ngày tối đa được phép.

## 14. Mở rộng bài thực hành

Sau khi báo cáo cơ bản chạy đúng, thử các biến thể sau:

### A. Top 3 danh mục theo từng khu vực và tháng

Giữ `WHERE category_rank <= 3` để cho phép đồng hạng cùng xuất hiện. Sau đó đổi thành `category_row_number <= 3` và so sánh số hàng, kết quả khi doanh thu bằng nhau.

### B. So sánh cùng kỳ năm trước

Trên `dense_sales`, thêm:

```sql
LAG(revenue, 12) OVER (
    PARTITION BY region_code, category_code
    ORDER BY month_start
) AS same_month_last_year
```

Điều kiện là date spine có đủ 12 tháng trước đó. Nếu kỳ báo cáo chỉ bắt đầu từ tháng hiện tại, phải mở rộng dữ liệu đầu vào thêm ít nhất 12 tháng để so sánh year-over-year; không chỉ sinh 12 tháng trong kết quả hiển thị.

### C. Xếp hạng khách hàng theo doanh thu

Thay grain báo cáo thành `month_start, region_code, customer_id`, tính doanh thu theo khách hàng rồi dùng:

```sql
RANK() OVER (
    PARTITION BY month_start, region_code
    ORDER BY customer_revenue DESC
) AS customer_rank
```

### D. Thêm tỷ trọng doanh thu trong khu vực

Trong `windowed_sales`, có thể tính tổng doanh thu cùng tháng/khu vực bằng window:

```sql
SUM(revenue) OVER (
    PARTITION BY month_start, region_code
) AS region_month_revenue
```

Sau đó tính tỷ trọng:

```sql
ROUND(100 * revenue / NULLIF(region_month_revenue, 0), 2) AS revenue_share_percent
```

### E. Lưu báo cáo định kỳ

Nếu báo cáo được gọi thường xuyên trên dữ liệu lớn, cân nhắc tạo bảng summary theo tháng/khu vực/danh mục, cập nhật bằng batch hoặc event-driven pipeline. Cần xác định cách xử lý đơn cập nhật trạng thái, hoàn tiền, hủy đơn và dữ liệu đến muộn; summary table phải có quy trình rebuild/đối soát.

## 15. Checklist nghiệm thu báo cáo

- [ ] Đã xác định grain của báo cáo và quy tắc tính doanh thu/đơn hàng.
- [ ] Bộ lọc ngày dùng khoảng nửa mở và không biến đổi cột indexed trong `WHERE`.
- [ ] CTE có tên phản ánh đúng từng bước lọc, tổng hợp, tạo grid và tính window.
- [ ] Recursive CTE dừng đúng tháng cuối kỳ và có giới hạn recursion phù hợp.
- [ ] Tháng không có dữ liệu được điền 0 nếu báo cáo cần so sánh tháng lịch liền trước.
- [ ] `COUNT(DISTINCT)` được dùng đúng grain để tránh đếm trùng đơn.
- [ ] `RANK`, `DENSE_RANK`, `ROW_NUMBER` được chọn theo yêu cầu xử lý đồng hạng.
- [ ] Window frame `ROWS`/`RANGE` được khai báo rõ cho running total/moving average.
- [ ] Phần trăm thay đổi xử lý mẫu số bằng 0 bằng `NULLIF`.
- [ ] `WITH ROLLUP` và `GROUPING()` phân biệt được detail, subtotal và grand total.
- [ ] Không cộng lẫn detail và subtotal làm nhân đôi doanh thu.
- [ ] Grid có kích thước kiểm soát được theo tháng × khu vực × danh mục.
- [ ] Execution plan, temporary table, sort, index và thời gian chạy đã được kiểm tra.
- [ ] Kết quả được đối soát với truy vấn tổng độc lập và dữ liệu mẫu biên.

CTE giúp chia báo cáo thành các bước dễ đọc; recursive CTE tạo lịch tháng liên tục; window functions giữ từng hàng trong khi tính thứ hạng, biến động, lũy kế và trung bình trượt; `WITH ROLLUP` bổ sung các cấp tổng phụ. Khi xác định đúng grain, xử lý tháng trống, phân biệt đồng hạng và kiểm tra execution plan, báo cáo MySQL vừa dễ kiểm chứng vừa có thể mở rộng cho nhu cầu phân tích thực tế.
