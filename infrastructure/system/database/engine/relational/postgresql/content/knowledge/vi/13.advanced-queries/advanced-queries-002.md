# WITH và tổ chức truy vấn bằng CTE trong PostgreSQL

Một truy vấn SQL không phải lúc nào cũng chỉ gồm một bảng, một phép `JOIN` và một điều kiện `WHERE`. Trong báo cáo thực tế, ta thường cần làm nhiều bước: lấy các đơn đã hoàn tất, tính tổng tiền từ dòng hàng, tổng hợp theo khách, chọn khách có doanh số cao và cuối cùng định dạng kết quả cho ứng dụng. Nếu cố nhồi toàn bộ vào một câu `SELECT` nhiều tầng lồng nhau, SQL vẫn có thể chạy, nhưng rất khó đọc, kiểm tra và thay đổi.

PostgreSQL hỗ trợ **Common Table Expression (CTE)** qua mệnh đề `WITH`. CTE giúp đặt tên cho kết quả trung gian trong phạm vi **một câu lệnh SQL**, để mỗi bước có thể được trình bày như một phần nhỏ của bài toán. Khi cần duyệt dữ liệu phân cấp (cây phòng ban, danh mục cha–con, đường đi trong đồ thị), PostgreSQL còn có `WITH RECURSIVE`.

Ví dụ nhìn nhanh:

```sql
WITH completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
),
order_totals AS (
    SELECT
        o.customer_id,
        o.order_id,
        SUM(i.quantity * i.unit_price) AS total_amount
    FROM completed_orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    GROUP BY o.customer_id, o.order_id
)
SELECT
    customer_id,
    COUNT(*) AS completed_order_count,
    SUM(total_amount) AS completed_revenue
FROM order_totals
GROUP BY customer_id
ORDER BY completed_revenue DESC, customer_id;
```

Hai tên `completed_orders` và `order_totals` cho thấy ngay hai giai đoạn xử lý. Tuy nhiên, **CTE không mặc nhiên là một bảng tạm được ghi xuống đĩa**, cũng không mặc nhiên làm câu SQL nhanh hơn. PostgreSQL có thể gộp CTE vào kế hoạch cha hoặc materialize kết quả tùy phiên bản, tính chất và số lần tham chiếu. Đây là điểm rất quan trọng khi dùng CTE cho truy vấn nâng cao.

Sau bài học, bạn sẽ biết:

1. Viết CTE thường, đặt tên cột và phối hợp nhiều CTE theo thứ tự phụ thuộc.
2. Phân biệt CTE với subquery, view, temporary table và transaction.
3. Dùng CTE để tổ chức lọc, `JOIN`, aggregate, window function và câu SQL có tham số.
4. Giải thích việc *fold/inlining* và *materialization* từ PostgreSQL 12, dùng `MATERIALIZED`/`NOT MATERIALIZED` có chủ đích.
5. Viết `WITH RECURSIVE` an toàn cho dữ liệu phân cấp và đồ thị có chu trình.
6. Hiểu `SEARCH`/`CYCLE` (PostgreSQL 14+), cơ chế dừng đệ quy và thứ tự kết quả.
7. Sử dụng `WITH` trong `INSERT`, `UPDATE`, `DELETE`, `MERGE` khi phiên bản hỗ trợ; hiểu giới hạn của CTE thay đổi dữ liệu qua `RETURNING`.
8. Kiểm chứng kết quả và đọc `EXPLAIN (ANALYZE, BUFFERS)` trước khi tối ưu.

Các ví dụ nhắm tới PostgreSQL hiện đại; một số tính năng được ghi rõ major tối thiểu. Hãy kiểm tra phiên bản server khi áp dụng vào dự án đang vận hành.

## 1. Khái niệm CTE: đặt tên cho kết quả trung gian

CTE là một truy vấn phụ được khai báo bằng `WITH` và được tham chiếu trong câu lệnh chính như một nguồn hàng có tên.

Cấu trúc cơ bản:

```sql
WITH ten_cte AS (
    SELECT ...
)
SELECT ...
FROM ten_cte;
```

Trong cú pháp mô tả trên, `...` là vị trí cần thay bằng SQL hợp lệ. `ten_cte` chỉ tồn tại trong **phạm vi câu lệnh** đang chứa `WITH`.

Ví dụ chạy độc lập, không cần tạo bảng:

```sql
WITH numbers AS (
    SELECT 10 AS a, 20 AS b
)
SELECT
    a,
    b,
    a + b AS total
FROM numbers;
```

Kết quả:

| a | b | total |
| ---: | ---: | ---: |
| 10 | 20 | 30 |

Đây không phải câu lệnh `CREATE TABLE numbers`. Sau khi `SELECT` hoàn tất, một câu lệnh khác như `SELECT * FROM numbers;` sẽ không tìm thấy CTE đó, trừ khi có một bảng/view thực sự mang tên ấy trong phạm vi phân giải tên.

### 1.1. Vì sao cần đặt tên các bước?

Khi một bài toán gồm nhiều phép biến đổi, ta có thể biểu diễn:

```text
orders + order_items
          |
          v
    order_totals
          |
          v
  completed_totals
          |
          v
   customer_revenue
          |
          v
    SELECT kết quả
```

Mỗi CTE là một cách gọi tên kết quả trung gian để mô tả **ý định**, giúp:

- Đọc câu SQL từ các phần nhỏ có tên rõ ràng.
- Tránh lặp lại một biểu thức dài trong một cấp truy vấn.
- Tách công việc lọc, nối, nhóm và trình bày dữ liệu.
- Dễ lấy một bước thành truy vấn độc lập để kiểm tra.
- Dùng một CTE nhiều lần trong cùng câu lệnh khi thực sự cần.

Nhưng CTE **không tự tạo hợp đồng dữ liệu lâu dài**. Định nghĩa CTE không được lưu như view và không tự chia sẻ giữa hai câu SQL độc lập.

## 2. Chuẩn bị dữ liệu thực hành

Để các ví dụ có thể chạy mà không phụ thuộc phần học trước, ta tạo schema `cte_lab` gồm khách hàng, đơn hàng, dòng hàng, cây danh mục, đồ thị và bảng công việc.

**Lưu ý:** chỉ chạy DDL/DML trong database lab được phép. Các lệnh tạo dữ liệu chỉ cần chạy một lần; chạy lại `INSERT` với cùng khóa chính sẽ gây lỗi trùng khóa.

### 2.1. Khách hàng, đơn hàng và dòng hàng

```sql
CREATE SCHEMA IF NOT EXISTS cte_lab;

CREATE TABLE cte_lab.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    region text
);

CREATE TABLE cte_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES cte_lab.customers(customer_id),
    ordered_at date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('completed', 'pending', 'cancelled'))
);

CREATE TABLE cte_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES cte_lab.orders(order_id),
    line_no integer NOT NULL CHECK (line_no > 0),
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Chèn dữ liệu mẫu:

```sql
INSERT INTO cte_lab.customers
    (customer_id, customer_name, region)
VALUES
    (1, 'An', 'Bac'),
    (2, 'Binh', 'Nam'),
    (3, 'Chi', 'Nam'),
    (4, 'Dung', NULL);

INSERT INTO cte_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (1001, 1, DATE '2026-10-01', 'completed'),
    (1002, 1, DATE '2026-10-02', 'pending'),
    (1003, 2, DATE '2026-10-03', 'completed'),
    (1004, 3, DATE '2026-11-01', 'completed'),
    (1005, 2, DATE '2026-11-02', 'cancelled');

INSERT INTO cte_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (1001, 1, 'BOOK-SQL', 2, 100.00),
    (1001, 2, 'NOTE-A5',  1,  50.00),
    (1002, 1, 'PEN-BLUE', 3,  30.00),
    (1003, 1, 'BOOK-PG',  1, 300.00),
    (1004, 1, 'MUG-01',  4,  25.00),
    (1005, 1, 'BAG-01',  1,  80.00);
```

Bảng đối chiếu tổng tiền từng đơn:

| order_id | customer_id | status | total từ dòng hàng |
| ---: | ---: | --- | ---: |
| 1001 | 1 | completed | 250.00 |
| 1002 | 1 | pending | 90.00 |
| 1003 | 2 | completed | 300.00 |
| 1004 | 3 | completed | 100.00 |
| 1005 | 2 | cancelled | 80.00 |

Khách 4 chưa có đơn. Điều này hữu ích để kiểm tra `LEFT JOIN` với dữ liệu tổng hợp.

Trong bài, `completed` được dùng làm điều kiện báo cáo đơn đã hoàn tất; nó **không phải định nghĩa chuẩn chung của doanh thu kế toán**. Hệ thống thật còn cần xử lý hoàn tiền, chiết khấu, thuế và các mốc ghi nhận doanh thu.

### 2.2. Cây danh mục

```sql
CREATE TABLE cte_lab.categories (
    category_id bigint PRIMARY KEY,
    category_name text NOT NULL,
    parent_id bigint
        REFERENCES cte_lab.categories(category_id)
);

INSERT INTO cte_lab.categories
    (category_id, category_name, parent_id)
VALUES
    (10, 'Sản phẩm', NULL),
    (11, 'Sách', 10),
    (12, 'Phụ kiện', 10),
    (13, 'Sách công nghệ', 11),
    (14, 'Dịch vụ', NULL),
    (15, 'Đào tạo', 14);
```

Sơ đồ:

```text
10 Sản phẩm
├── 11 Sách
│   └── 13 Sách công nghệ
└── 12 Phụ kiện

14 Dịch vụ
└── 15 Đào tạo
```

### 2.3. Đồ thị có chu trình

```sql
CREATE TABLE cte_lab.graph_edges (
    from_id bigint NOT NULL,
    to_id bigint NOT NULL,
    PRIMARY KEY (from_id, to_id)
);

INSERT INTO cte_lab.graph_edges (from_id, to_id)
VALUES
    (1, 2),
    (2, 3),
    (3, 1),
    (1, 4),
    (4, 5);
```

Đồ thị có chu trình `1 → 2 → 3 → 1` và nhánh `1 → 4 → 5`. Nó sẽ giúp giải thích tại sao một recursive CTE không có điều kiện dừng hợp lý có thể sinh kết quả không kết thúc.

## 3. Một CTE đơn giản để lọc dữ liệu

Yêu cầu: lấy những đơn đã hoàn tất, gồm ID, tên khách và ngày đặt.

```sql
WITH completed_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT
    o.order_id,
    c.customer_name,
    o.ordered_at
FROM completed_orders AS o
JOIN cte_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Kết quả:

| order_id | customer_name | ordered_at |
| ---: | --- | --- |
| 1001 | An | 2026-10-01 |
| 1003 | Binh | 2026-10-03 |
| 1004 | Chi | 2026-11-01 |

`completed_orders` giống một nguồn hàng có các cột `order_id`, `customer_id` và `ordered_at` ở phần `SELECT` cuối.

### 3.1. Tên CTE và tên alias bảng

```sql
WITH completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT o.order_id
FROM completed_orders AS o
ORDER BY o.order_id;
```

Ở đây:

- `completed_orders` là tên CTE.
- `o` là alias của nguồn CTE trong `FROM`.
- `o.order_id` là cột đầu ra của CTE, không nhất thiết phải giữ nguyên vị trí trong bảng gốc.

CTE và alias bảng đều dùng để đặt tên trong SQL, nhưng đóng vai trò khác nhau. CTE chứa **định nghĩa truy vấn**; alias bảng đặt **tên tham chiếu cho một lần dùng nguồn** trong một cấp truy vấn.

## 4. Đặt danh sách tên cột cho CTE

Có thể đặt tên các cột đầu ra sau tên CTE:

```sql
WITH sample_metrics(metric_name, metric_value) AS (
    SELECT 'orders'::text, COUNT(*)::numeric
    FROM cte_lab.orders
)
SELECT metric_name, metric_value
FROM sample_metrics;
```

Kết quả một hàng:

| metric_name | metric_value |
| --- | ---: |
| orders | 5 |

Danh sách `(metric_name, metric_value)` đặt **tên cột** cho kết quả CTE theo vị trí. Nó hữu ích khi:

- Biểu thức trong CTE không có alias rõ ràng.
- Muốn xác định giao diện cột ngay tại nơi khai báo CTE.
- Cần đặt cột của recursive CTE một cách dễ đọc.

Nhưng nếu danh sách tên cột không khớp ý nghĩa các biểu thức, SQL vẫn có thể chạy và cho kết quả khó hiểu. Tên cột không thay đổi **thứ tự hay giá trị** do `SELECT` bên trong tạo ra.

Ví dụ:

```sql
WITH n(x, y) AS (
    SELECT 5, 9
)
SELECT x, y, x + y AS total
FROM n;
```

Trả `x=5`, `y=9`, `total=14`.

## 5. Nhiều CTE: chia một bài toán thành các bước

CTE rất hữu ích khi cần nhiều bước biến đổi có phụ thuộc. Các CTE được phân tách bằng dấu phẩy:

```sql
WITH
completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
),
order_totals AS (
    SELECT
        co.order_id,
        co.customer_id,
        SUM(i.quantity * i.unit_price) AS total_amount
    FROM completed_orders AS co
    JOIN cte_lab.order_items AS i
        ON i.order_id = co.order_id
    GROUP BY co.order_id, co.customer_id
),
customer_revenue AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM order_totals
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    cr.order_count,
    cr.revenue
FROM customer_revenue AS cr
JOIN cte_lab.customers AS c
    ON c.customer_id = cr.customer_id
ORDER BY cr.revenue DESC, c.customer_id;
```

Kết quả:

| customer_id | customer_name | order_count | revenue |
| ---: | --- | ---: | ---: |
| 2 | Binh | 1 | 300.00 |
| 1 | An | 1 | 250.00 |
| 3 | Chi | 1 | 100.00 |

Khách Dung không có đơn nên không có hàng trong `customer_revenue`; nếu nghiệp vụ muốn **mọi khách và doanh thu 0**, cần đổi hướng JOIN ở truy vấn cuối (phần 7).

### 5.1. Đọc chuỗi phụ thuộc từ trên xuống

```text
completed_orders
       |
       v
  order_totals
       |
       v
customer_revenue ---- customers
       |                  |
       +-------- JOIN -----+
                  |
                  v
              kết quả
```

Trong một `WITH` không đệ quy, CTE được định nghĩa ở trước có thể được CTE sau tham chiếu theo thứ tự hợp lệ. Không thể tùy ý tạo quan hệ vòng giữa hai CTE rồi mong PostgreSQL tự suy ra đệ quy; khi cần đệ quy phải dùng cú pháp `WITH RECURSIVE` và tuân thủ các giới hạn tương ứng.

### 5.2. Đừng chia quá nhỏ chỉ vì có WITH

Một CTE chỉ viết `SELECT * FROM bảng` và không làm rõ ý định đôi khi chỉ tăng số dòng SQL. Cấu trúc hiệu quả là mỗi CTE đại diện một **bước có ngữ nghĩa riêng**: lọc dữ liệu hợp lệ, tổng hợp đơn, tính chỉ số, xếp hạng hoặc phân loại.

Từ tên `customer_revenue`, người đọc nên hiểu ngay một hàng là doanh thu **của một khách**, thay vì phải đọc hết 40 dòng SQL để đoán.

## 6. CTE và truy vấn con: cùng bài toán, khác cách trình bày

Một truy vấn con trong `FROM` cũng có thể tạo nguồn hàng:

```sql
SELECT
    t.order_id,
    t.total_amount
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM cte_lab.order_items
    GROUP BY order_id
) AS t
WHERE t.total_amount >= 100
ORDER BY t.order_id;
```

Viết bằng CTE:

```sql
WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, total_amount
FROM totals
WHERE total_amount >= 100
ORDER BY order_id;
```

Hai câu đều biểu diễn yêu cầu giống nhau trong dữ liệu này:

| order_id | total_amount |
| ---: | ---: |
| 1001 | 250.00 |
| 1003 | 300.00 |
| 1004 | 100.00 |

### 6.1. Bảng so sánh

| Đặc điểm | CTE với WITH | Derived table trong FROM |
| --- | --- | --- |
| Phạm vi | Một statement chứa `WITH`. | Một cấp truy vấn chứa subquery. |
| Đặt tên bước xử lý | Rõ ràng, tập trung ở đầu câu lệnh. | Đặt tên sau subquery trong `FROM`. |
| Dùng lại nhiều vị trí trong một statement | Tham chiếu cùng tên CTE nhiều lần. | Thường phải lặp lại hoặc tái cấu trúc subquery. |
| Đệ quy | `WITH RECURSIVE` hỗ trợ. | Derived table thông thường không tự tham chiếu đệ quy. |
| Hiệu năng | Phụ thuộc optimizer/materialization. | Phụ thuộc optimizer và các điều kiện tối ưu. |

Không có kết luận chung rằng CTE **luôn** nhanh hơn hoặc chậm hơn subquery. Hình thức SQL, số lần tham chiếu, loại hàm và phiên bản PostgreSQL có thể làm kế hoạch khác nhau.

## 7. CTE phối hợp LEFT JOIN để giữ hàng không có quan hệ

Yêu cầu: hiển thị **tất cả khách**, gồm người không có đơn hoàn tất, với doanh thu 0.

```sql
WITH completed_totals AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS completed_revenue
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(t.completed_revenue, 0) AS completed_revenue
FROM cte_lab.customers AS c
LEFT JOIN completed_totals AS t
    ON t.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | completed_revenue |
| ---: | --- | ---: |
| 1 | An | 250.00 |
| 2 | Binh | 300.00 |
| 3 | Chi | 100.00 |
| 4 | Dung | 0 |

Điểm cần hiểu:

- CTE `completed_totals` có **một hàng mỗi customer_id có đơn completed và dòng hàng phù hợp**.
- `customers LEFT JOIN completed_totals` giữ mọi khách.
- Khách Dung thiếu hàng bên phải, nên `completed_revenue` bên phải là SQL NULL.
- `COALESCE(..., 0)` chỉ biến thành 0 ở **kết quả hiển thị**, không tạo dòng ở CTE.

Nếu một đơn completed không có dòng hàng, truy vấn CTE hiện tại dùng `JOIN` sẽ **không tính đơn đó**. Nếu yêu cầu phải đếm cả đơn không có item, cần `LEFT JOIN` `order_items` và xác định công thức tiền cho đơn trống. Đây là ví dụ vì sao CTE giúp **phân lớp ý nghĩa**, nhưng không tự bảo đảm truy vấn đúng nếu điều kiện JOIN chưa đúng.

### 7.1. COUNT(*) sau LEFT JOIN

Để đếm số đơn thực tế, không nên `COUNT(*)` trên hàng khách được LEFT JOIN với đơn khi thiếu đơn. Hãy đếm một khóa bên phải `NOT NULL` như `o.order_id`:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM cte_lab.customers AS c
LEFT JOIN cte_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Kết quả lần lượt `2, 2, 1, 0`. Một CTE ở phía bên phải có thể giúp tính trước một hàng mỗi khách, giảm nguy cơ nhân hàng trong một báo cáo kết hợp nhiều nguồn một-nhiều.

## 8. CTE giúp tái sử dụng biểu thức đầu ra ở cấp ngoài

Trong PostgreSQL, alias được định nghĩa trong `SELECT` không thể được tham chiếu trực tiếp trong `WHERE` của **cùng cấp** truy vấn.

Ví dụ không hợp lệ:

```sql
-- Sai ý định: total_amount là alias SELECT cùng cấp.
-- SELECT order_id,
--        SUM(quantity * unit_price) AS total_amount
-- FROM cte_lab.order_items
-- GROUP BY order_id
-- WHERE total_amount > 100;
```

Ngoài lỗi alias, phép aggregate `SUM(...)` không được đặt trực tiếp trong `WHERE` ở cấp đang nhóm; những trường hợp lọc nhóm đơn giản nên dùng `HAVING`.

Viết với CTE:

```sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, total_amount
FROM order_totals
WHERE total_amount > 100
ORDER BY total_amount DESC, order_id;
```

Ở cấp ngoài, `total_amount` là **cột nguồn của CTE**, nên dùng được trong `WHERE`. Kết quả là đơn 1003 (300) và 1001 (250).

Nếu yêu cầu chỉ là lọc nhóm có tổng lớn hơn 100, cũng có thể:

```sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS total_amount
FROM cte_lab.order_items
GROUP BY order_id
HAVING SUM(quantity * unit_price) > 100
ORDER BY total_amount DESC, order_id;
```

CTE không phải cách duy nhất đúng. Hãy chọn `HAVING` cho biểu thức tổng hợp ngắn, hoặc CTE khi cần dùng kết quả nhóm để thực hiện nhiều bước tiếp theo.

## 9. Kết hợp CTE với window function

CTE có thể tạo một tập kết quả đã tổng hợp, rồi câu truy vấn ngoài dùng window function để đánh số thứ hạng.

Ví dụ xếp hạng khách theo doanh thu completed:

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS total_revenue
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
),
ranked AS (
    SELECT
        customer_id,
        total_revenue,
        DENSE_RANK() OVER (
            ORDER BY total_revenue DESC
        ) AS revenue_rank
    FROM revenue
)
SELECT
    c.customer_name,
    r.total_revenue,
    r.revenue_rank
FROM ranked AS r
JOIN cte_lab.customers AS c
    ON c.customer_id = r.customer_id
ORDER BY r.revenue_rank, c.customer_id;
```

Trong dữ liệu hiện tại:

| customer_name | total_revenue | revenue_rank |
| --- | ---: | ---: |
| Binh | 300.00 | 1 |
| An | 250.00 | 2 |
| Chi | 100.00 | 3 |

Lưu ý `DENSE_RANK` xếp các giá trị bằng nhau cùng hạng và không bỏ số thứ hạng tiếp theo. Khi cần đúng một hàng mỗi nhóm, hãy dùng một quy tắc phá hòa rõ ràng hoặc `ROW_NUMBER()` với `ORDER BY` xác định, thay vì trông đợi thứ tự bất kỳ.

### 9.1. Lọc theo window result

Không thể dùng alias `revenue_rank` trong `WHERE` của cấp truy vấn đã tính window function. Nhưng khi đưa phép xếp hạng vào CTE `ranked`, truy vấn ngoài có thể lọc:

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
),
ranked AS (
    SELECT
        customer_id,
        amount,
        ROW_NUMBER() OVER (
            ORDER BY amount DESC, customer_id
        ) AS row_num
    FROM revenue
)
SELECT customer_id, amount, row_num
FROM ranked
WHERE row_num <= 2
ORDER BY row_num;
```

Kết quả lấy hai khách doanh thu cao nhất: Binh và An. Đây là pattern hữu ích cho `top N` sau aggregate và các báo cáo xếp hạng nhiều tầng.

## 10. Tham chiếu cùng một CTE nhiều lần

Giả sử cần so sánh mỗi đơn completed với trung bình tổng tiền của các đơn completed.

```sql
WITH completed_totals AS (
    SELECT
        o.order_id,
        SUM(i.quantity * i.unit_price) AS total_amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.order_id
),
stats AS (
    SELECT AVG(total_amount) AS average_amount
    FROM completed_totals
)
SELECT
    t.order_id,
    t.total_amount,
    s.average_amount,
    t.total_amount > s.average_amount AS above_average
FROM completed_totals AS t
CROSS JOIN stats AS s
ORDER BY t.order_id;
```

CTE `completed_totals` được tham chiếu trong `stats` và trong query cuối. Câu SQL dễ đọc vì định nghĩa tổng tiền chỉ xuất hiện một lần.

Về hiệu năng, PostgreSQL có thể materialize CTE dùng nhiều lần theo mặc định, nếu CTE thích hợp và ở phiên bản hỗ trợ. Đọc phần `MATERIALIZED` để hiểu khi nào việc tính một lần là lợi thế, khi nào lại ngăn việc đẩy bộ lọc xuống bảng nguồn.

## 11. CTE và bộ tối ưu PostgreSQL: không mặc nhiên lưu thành bảng tạm

Đây là phần quan trọng của CTE trong PostgreSQL hiện đại.

Trước PostgreSQL 12, CTE `SELECT` thường hoạt động như một **optimization fence**: PostgreSQL không tự gộp nó vào query cha để tối ưu xuyên ranh giới như nhiều subquery.

Từ **PostgreSQL 12**, những CTE `SELECT` **không đệ quy, không có side effect và đáp ứng điều kiện thích hợp** có thể được gộp (*folded/inlined*) vào query cha. Mặc định thường là:

- **CTE được tham chiếu một lần:** PostgreSQL có thể gộp vào query cha, cho phép tối ưu chung.
- **CTE được tham chiếu nhiều lần:** PostgreSQL thường materialize để tránh tính lại kết quả, với điều kiện phù hợp.
- **CTE đệ quy hoặc có side effect:** không thuộc nhóm có thể gộp tự do như CTE `SELECT` thuần.

Lưu ý: mô tả trên là nguyên tắc chính; kế hoạch cụ thể cần quan sát bằng `EXPLAIN`.

### 11.1. Ví dụ predicate pushdown

```sql
WITH all_orders AS (
    SELECT *
    FROM cte_lab.orders
)
SELECT order_id, status
FROM all_orders
WHERE order_id = 1003;
```

Nếu PostgreSQL gộp CTE vào query cha, điều kiện `order_id = 1003` có thể được tối ưu như đang trực tiếp đọc `cte_lab.orders`. Chỉ mục primary key trên `order_id` có thể được xem xét khi planner lập kế hoạch.

Không nên hình dung PostgreSQL bắt buộc phải tạo toàn bộ danh sách đơn rồi mới lọc `order_id` chỉ vì cú pháp có `WITH`.

### 11.2. MATERIALIZED: yêu cầu ranh giới tính toán

Từ PostgreSQL 12:

```sql
WITH all_orders AS MATERIALIZED (
    SELECT *
    FROM cte_lab.orders
)
SELECT order_id, status
FROM all_orders
WHERE order_id = 1003;
```

`MATERIALIZED` yêu cầu PostgreSQL không gộp CTE kiểu phù hợp vào query cha. CTE được xử lý như một tập kết quả trung gian cho mục đích thực thi câu lệnh. Điều này có thể hữu ích để:

- Tránh tính lại một phép tính tốn kém khi được tham chiếu nhiều lần.
- Kiểm soát ranh giới tối ưu khi optimizer chọn kế hoạch bất lợi.
- Bảo toàn đặc tính đánh giá một lần của một số logic `SELECT` phù hợp.

Nhưng nó cũng có thể khiến PostgreSQL phải xử lý **nhiều hàng hơn cần thiết** trước khi bộ lọc của query ngoài được áp dụng.

### 11.3. NOT MATERIALIZED: cho phép gộp để tối ưu

```sql
WITH all_orders AS NOT MATERIALIZED (
    SELECT *
    FROM cte_lab.orders
)
SELECT order_id, status
FROM all_orders
WHERE order_id = 1003;
```

`NOT MATERIALIZED` cho phép PostgreSQL gộp CTE `SELECT` đủ điều kiện vào query cha dù CTE được tham chiếu nhiều lần. Điều này có thể cho phép đẩy `WHERE` xuống gần bảng nguồn.

Đánh đổi: nếu cùng CTE chứa biểu thức đắt đỏ và được sử dụng nhiều lần, việc gộp có thể khiến công việc **bị lặp lại**. Không chọn `NOT MATERIALIZED` vì nghĩ “NOT nghĩa là chắc chắn nhanh hơn”.

Các chỉ dẫn này không biến CTE đệ quy hoặc CTE có volatile/side effects thành biểu thức thuần có thể gộp tùy ý; PostgreSQL vẫn có các giới hạn để giữ đúng ngữ nghĩa.

### 11.4. Ví dụ dùng nhiều lần và đẩy lọc

Giả sử một CTE bao toàn bộ orders nhưng mỗi nhánh chỉ muốn một khách:

```sql
WITH base AS NOT MATERIALIZED (
    SELECT order_id, customer_id, status
    FROM cte_lab.orders
)
SELECT a.order_id AS order_of_customer_1,
       b.order_id AS order_of_customer_2
FROM base AS a
CROSS JOIN base AS b
WHERE a.customer_id = 1
  AND b.customer_id = 2;
```

PostgreSQL có cơ hội tối ưu từng lần tham chiếu theo điều kiện riêng. Nhưng bản thân `CROSS JOIN` tạo các cặp hàng giữa hai tập, vì vậy số hàng đầu ra là tích số hàng phù hợp (trong bộ dữ liệu có 2 đơn khách 1 và 2 đơn khách 2, nên có 4 cặp). CTE không sửa cardinality của phép nối.

Một phiên bản dùng `MATERIALIZED` có thể phải tính tập base một lần rồi lọc trên hai lần quét CTE. Với tập dữ liệu lớn và điều kiện chọn lọc, đó có thể là chi phí đáng kể.

## 12. Đọc EXPLAIN để nhận biết materialization

Ví dụ:

```sql
EXPLAIN
WITH base AS MATERIALIZED (
    SELECT order_id, customer_id, status
    FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE customer_id = 1;
```

Một kế hoạch có thể chứa những mục như `CTE base` và `CTE Scan on base`. Điều này phản ánh CTE được xử lý thành nguồn trung gian.

So sánh:

```sql
EXPLAIN
WITH base AS NOT MATERIALIZED (
    SELECT order_id, customer_id, status
    FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE customer_id = 1;
```

Kế hoạch có thể cho thấy thao tác đọc bảng `orders` với bộ lọc ngay tại scan, không còn một `CTE Scan` riêng.

### 12.1. EXPLAIN và EXPLAIN ANALYZE

| Công cụ | Mục đích | Lưu ý |
| --- | --- | --- |
| `EXPLAIN SELECT ...` | Xem kế hoạch ước lượng. | Không chạy phần truy vấn theo cách `ANALYZE`. |
| `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | Thực thi và đo thời gian, số hàng, buffer. | Thực sự chạy truy vấn; có thể tốn tài nguyên. |
| `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` | Đo DML. | **Thực sự sửa dữ liệu**; chỉ thử trong transaction lab có kiểm soát rồi rollback nếu phù hợp. |

Trên bảng lab nhỏ, planner có thể chọn sequential scan vì đọc vài hàng rẻ hơn dùng index. Không suy luận chiến lược `MATERIALIZED` tốt/xấu chỉ từ vài hàng ví dụ.

### 12.2. Đừng biến CTE thành “hint” mặc định

Nếu chưa thấy bottleneck thực tế, bắt đầu bằng CTE mô tả logic **rõ ràng**. Sau đó đo. Chỉ khi có bằng chứng, mới thử `MATERIALIZED` hoặc `NOT MATERIALIZED` và so sánh:

- Tổng số hàng được đọc.
- Chi phí tính lại biểu thức khi CTE dùng nhiều lần.
- Khả năng pushdown điều kiện.
- Số vòng lặp thực thi (*loops*), số hàng thực tế.
- Bộ nhớ/temporary file khi cần materialize/sort/hash.
- Thời gian thực thi trên dữ liệu và workload đại diện.

Một truy vấn có kế hoạch tốt vẫn phải được kiểm chứng đúng kết quả nghiệp vụ; `EXPLAIN` không thay thế bài kiểm tra logic.

## 13. CTE và các hàm volatile hoặc có side effect

Không phải mọi hàm trong PostgreSQL đều là hàm thuần. Có các hàm được phân loại theo tính chất như `IMMUTABLE`, `STABLE` và `VOLATILE`. Một số hàm thay đổi trạng thái hoặc trả giá trị biến đổi giữa các lần gọi.

Ví dụ:

```sql
WITH one_random_value AS MATERIALIZED (
    SELECT random() AS value
)
SELECT
    a.value AS first_read,
    b.value AS second_read
FROM one_random_value AS a
CROSS JOIN one_random_value AS b;
```

CTE `one_random_value` tạo một hàng chứa giá trị từ `random()`; hai lần tham chiếu dùng cùng kết quả CTE đã materialize trong câu lệnh. Điều này khác việc gọi `random()` độc lập hai lần trong select list:

```sql
SELECT
    random() AS first_value,
    random() AS second_value;
```

Hai lời gọi có thể trả giá trị khác nhau. Không xây business logic có tác dụng bên ngoài dựa vào suy luận “hàm SQL sẽ chắc chắn được gọi đúng N lần” mà chưa nắm mức volatility và kế hoạch.

**Thực hành tốt:** dùng CTE để biểu diễn quan hệ dữ liệu và phép tính. Nếu có thao tác phụ thuộc trình tự side effect, hãy thiết kế luồng transaction/command rõ ràng thay vì dùng những hàm có side effect ẩn trong `SELECT`.

## 14. WITH RECURSIVE: xử lý dữ liệu phân cấp

Một CTE thông thường không thể tự tham chiếu trong định nghĩa của chính nó. Khi duyệt cây hoặc đồ thị, cần `WITH RECURSIVE`.

Ví dụ đơn giản tạo dãy số:

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers
ORDER BY n;
```

Kết quả:

| n |
| ---: |
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

Trong recursive CTE:

1. **Phần khởi tạo** (*non-recursive term / anchor*) tạo hàng đầu tiên, ở đây `SELECT 1`.
2. **Phần đệ quy** (*recursive term*) dùng kết quả lặp trước để tạo hàng tiếp theo, ở đây `SELECT n + 1 FROM numbers`.
3. `UNION ALL` kết hợp hàng khởi tạo và các hàng sinh tiếp.
4. Điều kiện `WHERE n < 5` khiến quá trình dừng sau khi tạo giá trị 5.

### 14.1. Hình dung các vòng lặp

```text
Khởi tạo:
  working set = {1}
  result      = {1}

Lượt 1:
  từ {1} sinh {2}
  result = {1,2}

Lượt 2:
  từ {2} sinh {3}
  result = {1,2,3}

Lượt 3:
  từ {3} sinh {4}

Lượt 4:
  từ {4} sinh {5}

Lượt tiếp:
  n < 5 không còn đúng đối với 5
  working set rỗng -> dừng
```

PostgreSQL thực hiện recursive CTE theo cơ chế **lặp trên working table**, không phải gọi đệ quy hàm theo stack theo đúng cách viết trong ngôn ngữ lập trình. Hiểu mô hình này giúp giải thích tại sao chu trình trong dữ liệu có thể khiến quá trình lặp kéo dài vô hạn nếu không có chặn.

### 14.2. UNION ALL và UNION khác nhau

`UNION ALL` giữ toàn bộ hàng sinh ra. `UNION` có cơ chế loại hàng trùng giữa các bước theo toàn bộ bộ giá trị đầu ra.

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION
    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n FROM numbers ORDER BY n;
```

Với dãy số đơn giản này, cả hai vẫn trả 1–5. Nhưng trên đồ thị, loại trùng có thể giúp kết thúc một số dạng tìm kiếm **chỉ chứa định danh node**. Nếu hàng recursive còn có `depth` tăng liên tục, hai lần gặp cùng node vẫn có `depth` khác nhau, nên `UNION` không nhất thiết loại được chu trình.

**Không xem `UNION` là cơ chế chống chu trình tổng quát.** Với đồ thị thật, hãy có quy tắc ghi nhận node đã đi qua hoặc dùng cú pháp `CYCLE` ở major hỗ trợ.

## 15. Duyệt cây danh mục cha–con bằng recursive CTE

Bảng `cte_lab.categories` có một cột `parent_id` tham chiếu `category_id` của hàng cha. Muốn liệt kê cả cây, kèm độ sâu:

```sql
WITH RECURSIVE category_tree AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        0 AS depth
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.category_id,
        child.category_name,
        child.parent_id,
        parent.depth + 1
    FROM cte_lab.categories AS child
    JOIN category_tree AS parent
        ON child.parent_id = parent.category_id
)
SELECT
    category_id,
    category_name,
    parent_id,
    depth
FROM category_tree
ORDER BY depth, category_id;
```

Kết quả:

| category_id | category_name | parent_id | depth |
| ---: | --- | ---: | ---: |
| 10 | Sản phẩm | NULL | 0 |
| 14 | Dịch vụ | NULL | 0 |
| 11 | Sách | 10 | 1 |
| 12 | Phụ kiện | 10 | 1 |
| 15 | Đào tạo | 14 | 1 |
| 13 | Sách công nghệ | 11 | 2 |

Điểm quan trọng:

- Anchor lấy tất cả các node gốc (`parent_id IS NULL`), không chỉ một gốc.
- Phần recursive lấy các node con có `child.parent_id = parent.category_id`.
- `depth` tăng một đơn vị mỗi lần đi xuống.
- Câu `ORDER BY depth, category_id` tạo thứ tự đầu ra có chủ đích; **đừng dựa vào thứ tự phát hàng nội bộ** của recursive query.

### 15.1. Điều gì xảy ra với node không thuộc cây gốc?

Nếu có một vùng dữ liệu không thể đi đến từ anchor `parent_id IS NULL`, truy vấn trên sẽ không liệt kê nó. Ví dụ trong dữ liệu không có FK hoặc có chu trình giữa các node không có gốc, những node ấy không tự xuất hiện trong cây khởi đầu từ root.

Khi kiểm tra chất lượng dữ liệu phân cấp, có thể cần:

- Kiểm tra node mồ côi không tìm được parent.
- Kiểm tra chu trình.
- So sánh tập `category_id` toàn bảng với tập reachable từ các gốc.

Recursive CTE giúp phát hiện/duyệt quan hệ, nhưng không tự thay thế ràng buộc nghiệp vụ về cấu trúc cây.

### 15.2. Chỉ lấy nhánh dưới một danh mục

```sql
WITH RECURSIVE subtree AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        0 AS depth
    FROM cte_lab.categories
    WHERE category_id = 11

    UNION ALL

    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        s.depth + 1
    FROM cte_lab.categories AS c
    JOIN subtree AS s
        ON c.parent_id = s.category_id
)
SELECT category_id, category_name, depth
FROM subtree
ORDER BY depth, category_id;
```

Kết quả gồm:

| category_id | category_name | depth |
| ---: | --- | ---: |
| 11 | Sách | 0 |
| 13 | Sách công nghệ | 1 |

Khi anchor là node 11, `depth` đếm **từ node đó**, không phải độ sâu tuyệt đối từ gốc toàn hệ thống. Cách tính là quyết định thiết kế báo cáo cần ghi rõ.

## 16. Dựng đường dẫn (path) trong cây

Muốn hiển thị “Sản phẩm / Sách / Sách công nghệ”, có thể tích lũy path qua mỗi bước recursive:

```sql
WITH RECURSIVE category_paths AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        category_name::text AS display_path,
        ARRAY[category_id] AS id_path
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        p.display_path || ' / ' || c.category_name,
        p.id_path || c.category_id
    FROM cte_lab.categories AS c
    JOIN category_paths AS p
        ON c.parent_id = p.category_id
    WHERE NOT c.category_id = ANY(p.id_path)
)
SELECT
    category_id,
    display_path,
    id_path
FROM category_paths
ORDER BY id_path;
```

Kết quả nổi bật:

```text
10 | Sản phẩm                       | {10}
11 | Sản phẩm / Sách                | {10,11}
13 | Sản phẩm / Sách / Sách công nghệ | {10,11,13}
12 | Sản phẩm / Phụ kiện            | {10,12}
14 | Dịch vụ                        | {14}
15 | Dịch vụ / Đào tạo             | {14,15}
```

`id_path` là `bigint[]` chứa những ID đi qua. `ANY` dùng để kiểm tra node hiện tại đã xuất hiện trong path hay chưa, giúp **chặn chu trình trên một đường đi**.

### 16.1. Phòng ngừa chu trình ngay cả với mô hình cây

Một foreign key tự tham chiếu chỉ bảo đảm `parent_id` trỏ tới node tồn tại, **không tự bảo đảm cấu trúc không có vòng**. Chẳng hạn một node có thể trở thành cha của chính nó nếu không có ràng buộc bổ sung; nhiều node cũng có thể tạo vòng.

Trong hệ thống production, nên kiểm soát chu trình khi cập nhật quan hệ cha–con, không chỉ dựa vào `WHERE NOT ... ANY(path)` của truy vấn đọc. Recursive CTE có điều kiện chặn là **biện pháp bảo vệ lúc đọc**, không phải cơ chế xác nhận toàn bộ mô hình dữ liệu luôn là cây hợp lệ.

### 16.2. Thứ tự path có vai trò gì?

`ORDER BY id_path` sắp xếp các hàng theo chuỗi ID trong đường dẫn, gần cách duyệt chiều sâu của cây. Nó là một **quy tắc sắp xếp đầu ra** dựa vào path chứ không phải cam kết về thứ tự xử lý vật lý của PostgreSQL.

Nếu cần sắp thứ tự theo tên, quyền ưu tiên hoặc chỉ số sắp xếp của node, hãy lưu thuộc tính tương ứng và xây path từ những thành phần đó thay vì tin rằng ID luôn phản ánh trình tự giao diện mong muốn.

## 17. Đồ thị có chu trình: cách phòng truy vấn lặp mãi

Bảng `cte_lab.graph_edges` có vòng `1 → 2 → 3 → 1`. Nếu viết:

```sql
-- KHÔNG CHẠY trên graph_edges của bài nếu không có bảo vệ:
-- WITH RECURSIVE walk(node_id) AS (
--     SELECT 1::bigint
--     UNION ALL
--     SELECT e.to_id
--     FROM cte_lab.graph_edges AS e
--     JOIN walk AS w
--         ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
```

thì quá trình có thể tiếp tục sinh chuỗi 1,2,3,1,2,3,... không kết thúc theo logic đã viết.

### 17.1. Dùng mảng path để chặn node đã thăm

```sql
WITH RECURSIVE walk AS (
    SELECT
        1::bigint AS node_id,
        ARRAY[1::bigint] AS visited,
        0 AS depth

    UNION ALL

    SELECT
        e.to_id,
        w.visited || e.to_id,
        w.depth + 1
    FROM walk AS w
    JOIN cte_lab.graph_edges AS e
        ON e.from_id = w.node_id
    WHERE NOT e.to_id = ANY(w.visited)
)
SELECT
    node_id,
    visited,
    depth
FROM walk
ORDER BY visited;
```

Đường đi hợp lệ từ node 1:

```text
1
1 -> 2
1 -> 2 -> 3
1 -> 4
1 -> 4 -> 5
```

Không sinh bước `1 → 2 → 3 → 1`, vì node 1 đã ở trong `visited`.

**Quan trọng:** điều kiện này chặn lặp **trong từng đường đi**, không bảo đảm mỗi node chỉ xuất hiện **một lần trong toàn bộ kết quả** nếu đồ thị có nhiều đường khác nhau cùng dẫn tới một node. Nếu cần tập node reachable duy nhất, có thể xét `SELECT DISTINCT node_id` ở ngoài hoặc một thuật toán duyệt phù hợp với bài toán.

### 17.2. Thêm giới hạn độ sâu

```sql
WITH RECURSIVE walk AS (
    SELECT
        1::bigint AS node_id,
        ARRAY[1::bigint] AS visited,
        0 AS depth

    UNION ALL

    SELECT
        e.to_id,
        w.visited || e.to_id,
        w.depth + 1
    FROM walk AS w
    JOIN cte_lab.graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 10
      AND NOT e.to_id = ANY(w.visited)
)
SELECT *
FROM walk
ORDER BY depth, node_id;
```

`w.depth < 10` là chốt an toàn cho số cạnh tối đa của đường đi được sinh; **không thay thế kiểm tra cycle** trong đồ thị có nhiều nhánh hoặc có logic đặc biệt. Độ sâu tối đa nên phản ánh nghiệp vụ, không chỉ một hằng số đặt tùy tiện.

Ngoài độ sâu, có thể cần giới hạn số node/path theo logic ứng dụng, timeout phù hợp, quan sát workload, và phân trang hoặc tìm kiếm có chiến lược thay vì liệt kê mọi đường đi của đồ thị lớn.

## 18. SEARCH và CYCLE trong PostgreSQL 14+

PostgreSQL 14 bổ sung cú pháp `SEARCH` và `CYCLE` cho recursive CTE, giúp diễn đạt thứ tự duyệt và phát hiện chu trình theo cách khai báo.

### 18.1. CYCLE tự tạo cột đánh dấu và path

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::bigint

    UNION ALL

    SELECT e.to_id
    FROM cte_lab.graph_edges AS e
    JOIN walk AS w
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    is_cycle,
    cycle_path
FROM walk
ORDER BY cycle_path;
```

PostgreSQL tự bổ sung:

- `is_cycle`: cờ cho biết một hàng được phát hiện là điểm lặp của đường đi.
- `cycle_path`: thông tin đường đi được theo dõi để xác định cycle.

Khi một hàng được đánh dấu cycle, PostgreSQL không mở rộng tiếp hàng đó theo cơ chế của `CYCLE`. Bản thân **hàng cycle có thể vẫn xuất hiện** trong kết quả, nên nếu chỉ muốn liệt kê đường đi không lặp:

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::bigint
    UNION ALL
    SELECT e.to_id
    FROM cte_lab.graph_edges AS e
    JOIN walk AS w
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, cycle_path
FROM walk
WHERE NOT is_cycle
ORDER BY cycle_path;
```

Trên PostgreSQL 13 hoặc cũ hơn, cú pháp `CYCLE` theo chuẩn này chưa có; hãy dùng mảng path/điều kiện như phần 17.

### 18.2. SEARCH để tạo khóa thứ tự duyệt

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, category_name, parent_id
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT c.category_id, c.category_name, c.parent_id
    FROM cte_lab.categories AS c
    JOIN category_tree AS t
        ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET traversal_order
SELECT
    category_id,
    category_name,
    traversal_order
FROM category_tree
ORDER BY traversal_order;
```

`SEARCH DEPTH FIRST ... SET traversal_order` tạo một cột phụ dùng để **sắp xếp đầu ra theo thứ tự duyệt chiều sâu**. Có thể dùng `SEARCH BREADTH FIRST` khi cần biểu diễn thứ tự duyệt chiều rộng.

Đừng hiểu `SEARCH` là PostgreSQL bắt buộc thực hiện các lần đọc vật lý theo thứ tự chiều sâu/chiều rộng tương ứng. Nó cung cấp **khóa sắp xếp kết quả**; muốn thứ tự đầu ra ổn định phải viết `ORDER BY traversal_order`.

### 18.3. Dùng SEARCH cùng CYCLE có cần không?

Khi cần vừa kiểm soát chu trình vừa có thứ tự duyệt, có thể phối hợp theo cú pháp được major hỗ trợ. Tuy nhiên, nếu `CYCLE` đã tạo path phù hợp cho cách sắp xếp chiều sâu, việc thêm `SEARCH DEPTH FIRST` đôi khi tạo công việc dư thừa. Hãy chọn những cột thực sự cần cho kết quả và đo trên dữ liệu đại diện.

## 19. Không dùng LIMIT phía ngoài làm cơ chế chặn đệ quy

Đôi khi người học viết recursive CTE không có điều kiện dừng rồi thử:

```sql
-- KHÔNG XEM ĐÂY LÀ CÁCH THIẾT KẾ AN TOÀN:
-- WITH RECURSIVE numbers(n) AS (
--     SELECT 1
--     UNION ALL
--     SELECT n + 1 FROM numbers
-- )
-- SELECT n FROM numbers LIMIT 10;
```

Trong một số kế hoạch PostgreSQL, query cha có `LIMIT` có thể chỉ yêu cầu một phần hàng của recursive CTE, khiến ví dụ đơn giản dừng sau khi đã đủ hàng. Nhưng đó là **một đặc tính thực thi phụ thuộc kế hoạch**, không phải cách đảm bảo chương trình đệ quy đúng.

Chỉ cần query cha thêm `ORDER BY`, `JOIN` hoặc aggregate cần toàn bộ dữ liệu, việc lấy đủ hàng có thể đòi đệ quy nhiều hơn hoặc vô hạn.

Thiết kế an toàn phải có:

- Điều kiện kết thúc về mặt logic trong recursive term.
- Cơ chế chặn chu trình khi dữ liệu có khả năng tạo vòng.
- Kiểm soát mức độ sâu/kích thước workload theo nghiệp vụ.
- Theo dõi timeout/tài nguyên cho các query graph lớn.

Một `LIMIT` dùng để hiển thị một số hàng là yêu cầu trình bày, không nên là chốt an toàn duy nhất cho một thuật toán không có điểm dừng.

## 20. Kiểu dữ liệu của phần anchor và recursive term

Recursive CTE yêu cầu **hai nhánh của `UNION [ALL]` có kiểu dữ liệu tương thích** ở từng cột.

Ví dụ:

```sql
WITH RECURSIVE seq(n, label) AS (
    SELECT
        1,
        'Level 1'::text

    UNION ALL

    SELECT
        n + 1,
        ('Level ' || (n + 1)::text)
    FROM seq
    WHERE n < 3
)
SELECT n, label
FROM seq
ORDER BY n;
```

Trả các nhãn `Level 1`, `Level 2`, `Level 3`.

Khi dùng đường dẫn văn bản, ép kiểu anchor thành `text` thường giúp tránh những lỗi kiểu dữ liệu từ một literal `unknown` hoặc `varchar(n)` trong khi recursive branch tạo `text`. Khi lưu path số, tạo mảng đúng kiểu:

```sql
SELECT
    ARRAY[1::bigint] AS bigint_path,
    ARRAY[1::bigint] || 2::bigint AS extended_path;
```

Một lỗi cú pháp/kiểu thường gặp là anchor tạo `integer[]` còn recursive branch trả `bigint[]`, hoặc anchor dùng kiểu text có giới hạn độ dài trong khi path đệ quy nối ngày càng dài. Tốt hơn là **định nghĩa kiểu có chủ đích ngay ở anchor**.

## 21. Hiệu năng recursive CTE và những giới hạn của mô hình cây

Recursive CTE có thể rất tiện cho cây vừa phải, nhưng đồ thị lớn hoặc quá nhiều nhánh có thể sinh số đường đi rất lớn.

### 21.1. Chỉ mục cho truy vấn cha–con

Trong recursive term, điều kiện thường là:

```sql
JOIN cte_lab.categories AS child
    ON child.parent_id = parent.category_id
```

Một chỉ mục trên `parent_id` có thể hữu ích khi bảng đủ lớn:

```sql
CREATE INDEX idx_categories_parent_id
ON cte_lab.categories (parent_id);
```

Đối với đồ thị:

```sql
CREATE INDEX idx_graph_edges_to_id
ON cte_lab.graph_edges (to_id);
```

Primary key `(from_id, to_id)` đã giúp các truy vấn bắt đầu từ `from_id`; index bổ sung `to_id` có thể hữu ích khi cần duyệt chiều ngược lại. Không tạo index vô điều kiện nếu workload không có nhu cầu.

### 21.2. Những câu hỏi trước khi dùng recursive CTE

1. Độ sâu tối đa có thể đạt bao nhiêu?
2. Mỗi node có thể có bao nhiêu con hoặc cạnh?
3. Có cycle, đường đi trùng hay node cô lập không?
4. Muốn tất cả **đường đi**, tất cả **node duy nhất**, hay chỉ **đường đi ngắn nhất**?
5. Có cần thứ tự kết quả cố định hoặc pagination không?
6. Query được gọi bao nhiêu lần mỗi giây?
7. Có bộ chỉ mục phù hợp và giới hạn thời gian hợp lý không?

Một CTE liệt kê **mọi đường đi đơn** trong đồ thị có nhiều nhánh vẫn có thể tạo số hàng rất lớn ngay cả khi đã chặn chu trình. Nếu bài toán là tìm đường đi ngắn nhất trên đồ thị khổng lồ hoặc phân tích mạng chuyên sâu, cần đánh giá thuật toán/cấu trúc dữ liệu phù hợp thay vì mặc định recursive SQL là giải pháp tối ưu.

### 21.3. Các cách mô hình hóa cây khác

| Mô hình | Ý tưởng | Điểm đánh đổi |
| --- | --- | --- |
| Adjacency list (`parent_id`) | Mỗi hàng lưu ID cha. | Dễ ghi/cập nhật, truy vấn toàn bộ hậu duệ cần đệ quy. |
| Materialized path | Mỗi hàng lưu đường dẫn tổ tiên. | Đọc theo nhánh thuận tiện, đổi cha có thể phải cập nhật nhiều path. |
| Closure table | Bảng lưu cặp tổ tiên–hậu duệ và độ sâu. | Truy vấn ancestor/descendant dễ, chi phí duy trì quan hệ cao hơn. |
| Nested set | Lưu khoảng chỉ số để biểu diễn cấu trúc cây. | Một số truy vấn đọc nhánh thuận tiện, di chuyển node có thể tốn cập nhật. |

`WITH RECURSIVE` thường phù hợp với adjacency list; nếu hệ thống thường xuyên truy vấn hậu duệ ở quy mô rất lớn, cân nhắc những phương án lưu trữ phụ trợ với đánh đổi ghi và tính nhất quán rõ ràng.

## 22. Dùng WITH với UPDATE

`WITH` không chỉ được dùng trước `SELECT`. PostgreSQL cho phép đặt CTE trước câu lệnh thay đổi dữ liệu như `INSERT`, `UPDATE`, `DELETE`; với `MERGE` cần kiểm tra major hỗ trợ cú pháp và hành vi tương ứng.

Ví dụ chọn các đơn pending của khách 1 rồi chuyển trạng thái thành completed:

```sql
WITH target_orders AS (
    SELECT order_id
    FROM cte_lab.orders
    WHERE customer_id = 1
      AND status = 'pending'
)
UPDATE cte_lab.orders AS o
SET status = 'completed'
FROM target_orders AS t
WHERE o.order_id = t.order_id
RETURNING
    o.order_id,
    o.customer_id,
    o.status;
```

Với dữ liệu ban đầu, câu SQL cập nhật đơn 1002 thành `completed`. **Không chạy nếu muốn giữ nguyên số liệu ở các ví dụ trước**, vì doanh thu completed và số lượng đơn completed sẽ thay đổi.

Để thử trong lab rồi trả lại dữ liệu:

```sql
BEGIN;

WITH target_orders AS (
    SELECT order_id
    FROM cte_lab.orders
    WHERE customer_id = 1
      AND status = 'pending'
)
UPDATE cte_lab.orders AS o
SET status = 'completed'
FROM target_orders AS t
WHERE o.order_id = t.order_id
RETURNING o.order_id, o.status;

ROLLBACK;
```

Trong ví dụ lab không có thay đổi song song, rollback giúp giữ trạng thái ban đầu. Trong ứng dụng thực tế có writer cạnh tranh, điều kiện lựa chọn và update cần thiết kế xử lý concurrency, khóa hàng và retry; CTE không tự làm tất cả việc đó.

### 22.1. Không cho rằng CTE luôn “đóng băng” tập hàng

Nếu CTE `target_orders` là một `SELECT` có thể được optimizer gộp vào statement, cách thực thi vật lý có thể khác so với tưởng tượng “PostgreSQL tạo xong danh sách ID riêng rồi mới chạy UPDATE”.

Khi cần bảo đảm một điều kiện nghiệp vụ không thay đổi trong lúc ghi, hãy thiết kế câu `UPDATE` với predicate/locking đúng. Tránh suy luận về thứ tự thực thi từ thứ tự các CTE trong văn bản SQL.

## 23. Data-modifying CTE: thay đổi dữ liệu rồi dùng RETURNING

PostgreSQL còn hỗ trợ các CTE chứa thao tác thay đổi dữ liệu, thường là `INSERT`, `UPDATE`, `DELETE` và `MERGE` theo phiên bản. Một pattern hữu ích là chuyển các hàng đã xử lý sang bảng lưu trữ trong **một câu SQL có thể atomic**.

### 23.1. Dựng bảng jobs độc lập

Để không ảnh hưởng orders:

```sql
CREATE TABLE cte_lab.jobs (
    job_id bigint PRIMARY KEY,
    job_status text NOT NULL
        CHECK (job_status IN ('pending', 'running', 'completed')),
    payload text NOT NULL
);

CREATE TABLE cte_lab.jobs_archive (
    job_id bigint PRIMARY KEY,
    job_status text NOT NULL,
    payload text NOT NULL,
    archived_at timestamptz NOT NULL
);

INSERT INTO cte_lab.jobs (job_id, job_status, payload)
VALUES
    (1, 'completed', 'done-A'),
    (2, 'pending',   'queued-B'),
    (3, 'completed', 'done-C');
```

### 23.2. DELETE ... RETURNING rồi INSERT

```sql
WITH moved AS (
    DELETE FROM cte_lab.jobs
    WHERE job_status = 'completed'
    RETURNING job_id, job_status, payload
)
INSERT INTO cte_lab.jobs_archive (
    job_id, job_status, payload, archived_at
)
SELECT
    job_id,
    job_status,
    payload,
    clock_timestamp()
FROM moved
RETURNING job_id, archived_at;
```

Kết quả kỳ vọng: những job đã hoàn tất (1, 3) được xóa khỏi `jobs` và chèn vào `jobs_archive`; job 2 vẫn ở bảng hoạt động.

Giải thích:

- CTE `moved` không phải một `SELECT` mà là câu `DELETE`.
- `DELETE ... RETURNING` xuất các hàng bị xóa dưới dạng quan hệ kết quả.
- Lệnh `INSERT` chính nhận các hàng từ `moved`.
- Cả hai tác động là thành phần của cùng câu statement và được PostgreSQL thực hiện trong ranh giới atomic của transaction.

Nếu gặp lỗi vi phạm khóa duy nhất ở `jobs_archive`, statement sẽ bị hủy theo cơ chế transaction; không nên suy luận rằng các hàng đã xóa chắc chắn mất vĩnh viễn.

### 23.3. Cẩn trọng với thứ tự và snapshot của DML CTE

**Đây là điểm khác biệt rất quan trọng** so với cách tưởng tượng “mỗi CTE chạy xong, câu tiếp theo mới nhìn thấy bảng đã bị sửa”:

- Các phần DML trong một statement `WITH` có thể được thực hiện với thứ tự không thể dựa vào để viết logic nghiệp vụ.
- Chúng dùng snapshot phù hợp của cùng statement; không nên trông đợi một DML CTE thấy các hàng vừa thay đổi của DML CTE khác qua việc quét lại bảng gốc.
- **`RETURNING` là kênh rõ ràng để truyền dữ liệu đã thay đổi** từ CTE DML sang lệnh khác trong cùng statement.
- Tránh cố sửa cùng một hàng **hai lần** trong một statement qua nhiều DML CTE hoặc giữa CTE và statement chính; kết quả không được xác định đầy đủ theo ý định người viết.
- Một data-modifying CTE không có `RETURNING` vẫn có thể thực hiện tác động, nhưng không tạo quan hệ đầu ra để CTE khác dùng như `FROM moved`.

Đừng dùng tên CTE như một cơ chế ra lệnh tuần tự kiểu:

```text
step_a chắc chắn cập nhật xong bảng gốc
     ->
step_b SELECT lại bảng gốc thấy ngay hàng mới
```

Nếu cần từng bước nhìn thấy trạng thái sau commit theo thứ tự, hãy dùng các statement riêng trong transaction và cơ chế phù hợp, hoặc truyền dữ liệu bằng `RETURNING` theo pattern được PostgreSQL hỗ trợ.

### 23.4. Giới hạn vị trí của data-modifying CTE

Data-modifying CTE trong PostgreSQL có giới hạn vị trí và phải thuộc `WITH` gắn với statement ở cấp trên cùng phù hợp, không thể đặt tùy tiện mọi loại DML ở mọi subquery lồng nhau như một CTE `SELECT`.

Các truy vấn thay đổi dữ liệu còn có quyền truy cập, trigger, constraint, WAL, locking và khả năng rollback như DML bình thường; không nên thử trên production chỉ để xem `EXPLAIN ANALYZE`.

## 24. CTE trong INSERT ... SELECT

Giả sử cần tạo một bảng báo cáo cache từ dữ liệu có thể tính toán. CTE giúp diễn đạt tập nguồn trước khi chèn.

Trên lab:

```sql
CREATE TABLE cte_lab.customer_revenue_snapshot (
    snapshot_date date NOT NULL,
    customer_id bigint NOT NULL,
    completed_revenue numeric(14, 2) NOT NULL,
    PRIMARY KEY (snapshot_date, customer_id)
);
```

Lưu snapshot theo ngày:

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
INSERT INTO cte_lab.customer_revenue_snapshot (
    snapshot_date, customer_id, completed_revenue
)
SELECT
    DATE '2026-11-14',
    c.customer_id,
    COALESCE(r.amount, 0)
FROM cte_lab.customers AS c
LEFT JOIN revenue AS r
    ON r.customer_id = c.customer_id
RETURNING
    snapshot_date,
    customer_id,
    completed_revenue;
```

Snapshot này lưu **kết quả tại thời điểm statement chạy** vào bảng thật; nó khác CTE `revenue` vốn chỉ tồn tại trong phạm vi statement. Nếu chạy lại cùng `snapshot_date` khi chưa có `ON CONFLICT` phù hợp, primary key sẽ từ chối những hàng trùng.

Ngoài ra, nếu bảng nguồn thay đổi trong lúc snapshot được tạo, ngữ nghĩa snapshot tuân theo isolation và thời điểm quan sát của câu SQL. Đừng gọi một bảng snapshot là “lịch sử chính xác theo ngày” khi chưa xác định cách chốt dữ liệu và xử lý giao dịch đến muộn.

## 25. CTE trong UPDATE ... FROM và nguy cơ nhiều hàng khớp

CTE có thể làm nguồn cho `UPDATE ... FROM`:

```sql
WITH amounts AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    a.amount
FROM cte_lab.orders AS o
JOIN amounts AS a
    ON a.order_id = o.order_id
ORDER BY o.order_id;
```

Nếu sau này thêm cột `orders.total_amount` và dùng `UPDATE ... FROM amounts`, cần bảo đảm `amounts` có **đúng một hàng mỗi `order_id`**. Ở ví dụ, `GROUP BY order_id` giúp thỏa điều kiện ấy.

Trong PostgreSQL, nếu một target row khớp nhiều hàng source ở `UPDATE ... FROM`, kết quả giá trị dùng để cập nhật có thể không xác định theo ý định nghiệp vụ. **CTE không tự loại trùng**. Hãy thiết kế khóa, tổng hợp hoặc lựa chọn đại diện có thứ tự rõ trước khi cập nhật.

Một truy vấn chỉ đọc để kiểm tra cardinality:

```sql
WITH amounts AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, COUNT(*) AS rows_per_order
FROM amounts
GROUP BY order_id
HAVING COUNT(*) <> 1;
```

Với CTE như trên, truy vấn không trả hàng. Trên dữ liệu thực, nên kiểm tra các giả định về grain, không chỉ nhìn SQL có `WITH` là tin dữ liệu đã được chuẩn hóa.

## 26. CTE không đồng nghĩa transaction

Một CTE `SELECT` chỉ là cấu trúc biểu thức của **một statement**; nó không tự mở hay đóng transaction mới.

Phân biệt:

```sql
BEGIN;

WITH completed_orders AS (
    SELECT order_id
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT COUNT(*) FROM completed_orders;

SELECT COUNT(*) FROM cte_lab.orders;

COMMIT;
```

Hai câu `SELECT` là hai statement trong một transaction. CTE `completed_orders` chỉ tồn tại ở statement đầu, không thể dùng trong `SELECT` thứ hai.

Ở isolation level `READ COMMITTED`, hai statement trong cùng transaction có thể nhìn các snapshot đã commit khác nhau theo quy tắc PostgreSQL. `WITH` không tự tạo snapshot chung xuyên qua nhiều câu SQL khác nhau.

Nếu báo cáo nhiều statement cần nhất quán cùng một snapshot, phải chọn isolation/transaction phù hợp theo yêu cầu. Ngược lại, một data-modifying CTE và statement chính thuộc cùng statement có những quy tắc snapshot/RETURNING riêng như phần trước.

## 27. CTE, VIEW, MATERIALIZED VIEW và TEMP TABLE

Tên các công cụ dễ gây nhầm lẫn vì đều có thể giúp chia nhỏ câu SQL hoặc lưu kết quả trung gian.

| Công cụ | Thời gian tồn tại | Lưu dữ liệu riêng? | Trường hợp phù hợp |
| --- | --- | --- | --- |
| CTE `WITH name AS (...)` | Trong một SQL statement | Không phải đối tượng lưu trữ lâu dài; có thể được materialize **nội bộ khi chạy**. | Tổ chức một câu SQL phức tạp. |
| View `CREATE VIEW` | Đối tượng schema cho đến khi xóa | Thường không lưu kết quả truy vấn. | Tái sử dụng giao diện truy vấn trong nhiều statement/service. |
| Materialized view | Đối tượng schema cho đến khi xóa | **Có lưu kết quả**, cần refresh. | Tăng tốc đọc truy vấn tổng hợp và chấp nhận độ trễ dữ liệu. |
| Temporary table | Trong session/transaction theo cấu hình | **Có bảng tạm và dữ liệu tạm** trong phạm vi áp dụng. | Nhiều statement cùng cần thao tác trên tập trung gian, có thể lập chỉ mục. |

### 27.1. So sánh với VIEW

```sql
CREATE VIEW cte_lab.v_completed_orders AS
SELECT order_id, customer_id, ordered_at
FROM cte_lab.orders
WHERE status = 'completed';
```

Sau đó ở nhiều statement:

```sql
SELECT * FROM cte_lab.v_completed_orders;
```

View cung cấp định nghĩa có tên tồn tại trong schema, có thể dùng chung và quản lý quyền. Nhưng cần xem schema dependency, migration và cách quyền trên view được áp dụng; không tự xem view là một bản sao dữ liệu materialized.

### 27.2. So sánh với TEMP TABLE

```sql
CREATE TEMP TABLE temp_completed_orders AS
SELECT order_id, customer_id
FROM cte_lab.orders
WHERE status = 'completed';

SELECT COUNT(*) FROM temp_completed_orders;
SELECT * FROM temp_completed_orders ORDER BY order_id;
```

Bảng tạm ở đây có thể dùng qua nhiều statement của session. Nhưng dữ liệu của nó là một bản chụp lúc tạo, **không tự thay đổi** theo bảng `orders` về sau. Nó cũng có chi phí tạo dữ liệu, quản lý session và có thể cần thống kê/chỉ mục riêng khi lớn.

Khi chỉ cần một câu `SELECT`, CTE thường đơn giản hơn. Khi cần nhiều câu SQL dùng chung tập trung gian, có thể cân nhắc temp table, nhưng phải tính tác động của connection pooling và vòng đời session.

### 27.3. MATERIALIZED CTE không phải MATERIALIZED VIEW

`WITH base AS MATERIALIZED (...)` là chỉ dẫn về **cách xử lý CTE trong một statement**. Nó không tạo một materialized view có tên lâu dài. `REFRESH MATERIALIZED VIEW` không áp dụng cho CTE.

Hai chữ “materialized” có liên hệ về ý tưởng lưu kết quả trung gian, nhưng **phạm vi và vòng đời rất khác nhau**.

## 28. CTE và SQL có tham số trong ứng dụng Java

Ứng dụng Java thường dùng `PreparedStatement` hoặc thư viện truy cập dữ liệu để bind giá trị một cách an toàn.

Ví dụ SQL có chỗ giữ tham số dưới dạng PostgreSQL server-side `$1` khi dùng giao diện chuẩn bị statement phù hợp:

```sql
PREPARE completed_orders_for_customer(bigint) AS
WITH selected_orders AS (
    SELECT order_id, ordered_at
    FROM cte_lab.orders
    WHERE status = 'completed'
      AND customer_id = $1
)
SELECT order_id, ordered_at
FROM selected_orders
ORDER BY ordered_at DESC, order_id DESC;

EXECUTE completed_orders_for_customer(1);

DEALLOCATE completed_orders_for_customer;
```

Trong JDBC, placeholder do `PreparedStatement` cung cấp thường là `?`, không phải nối giá trị input trực tiếp vào SQL string:

```java
String sql = """
    WITH selected_orders AS (
        SELECT order_id, ordered_at
        FROM cte_lab.orders
        WHERE status = 'completed'
          AND customer_id = ?
    )
    SELECT order_id, ordered_at
    FROM selected_orders
    ORDER BY ordered_at DESC, order_id DESC
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Xử lý kết quả phù hợp với ứng dụng.
        }
    }
}
```

Đoạn Java minh họa giả định `connection` và `customerId` đã được khởi tạo theo cơ chế an toàn của ứng dụng. Trong thực tế, cần quản lý transaction, pool, timeout và lỗi kết nối phù hợp.

**CTE không bảo vệ SQL injection** nếu ứng dụng vẫn nối chuỗi user input vào truy vấn. Mọi giá trị do người dùng cung cấp nên đi qua cơ chế tham số hóa tương ứng; không cho phép input tùy ý điều khiển tên bảng, tên cột hoặc mệnh đề SQL không được kiểm tra.

## 29. CTE và thứ tự kết quả

Một lỗi thường gặp là đặt `ORDER BY` trong CTE rồi mặc định kết quả ngoài giữ thứ tự đó.

```sql
WITH sorted_orders AS (
    SELECT order_id, ordered_at
    FROM cte_lab.orders
    ORDER BY ordered_at DESC
)
SELECT order_id, ordered_at
FROM sorted_orders;
```

Không nên dựa vào thứ tự hiển thị của query cuối khi nó **không có `ORDER BY` ở cấp ngoài**. PostgreSQL có thể thay đổi kế hoạch hoặc thao tác tiếp theo gây thay đổi thứ tự.

Để bảo đảm thứ tự trả về:

```sql
WITH selected_orders AS (
    SELECT order_id, ordered_at
    FROM cte_lab.orders
)
SELECT order_id, ordered_at
FROM selected_orders
ORDER BY ordered_at DESC, order_id DESC;
```

### 29.1. ORDER BY và LIMIT trong CTE có ý nghĩa riêng

Nếu mục tiêu là chọn **ba đơn mới nhất** rồi xử lý tiếp, đặt `ORDER BY ... LIMIT 3` trong CTE có ý nghĩa ngữ nghĩa:

```sql
WITH latest_three AS (
    SELECT order_id, customer_id, ordered_at
    FROM cte_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
)
SELECT
    l.order_id,
    c.customer_name,
    l.ordered_at
FROM latest_three AS l
JOIN cte_lab.customers AS c
    ON c.customer_id = l.customer_id
ORDER BY l.ordered_at DESC, l.order_id DESC;
```

Lúc này, `ORDER BY ... LIMIT 3` bên trong xác định **tập ba đơn** được chọn; `ORDER BY` bên ngoài xác định **thứ tự hàng trả về** sau JOIN. Hai mệnh đề phục vụ những mục tiêu khác nhau.

## 30. Những lỗi thường gặp với CTE

### Lỗi 1. Quên dấu phẩy giữa hai CTE

```sql
-- Sai cú pháp vì thiếu dấu phẩy:
-- WITH a AS (SELECT 1 AS n)
--      b AS (SELECT 2 AS n)
-- SELECT * FROM a;
```

Đúng:

```sql
WITH a AS (SELECT 1 AS n),
     b AS (SELECT 2 AS n)
SELECT a.n AS a_value, b.n AS b_value
FROM a CROSS JOIN b;
```

### Lỗi 2. Dùng CTE ở statement khác

```sql
-- Statement 1:
WITH temp_values AS (SELECT 1 AS n)
SELECT n FROM temp_values;

-- Statement 2 sẽ không còn CTE temp_values:
-- SELECT n FROM temp_values;
```

Muốn tái sử dụng định nghĩa giữa nhiều statement, cân nhắc view hoặc temp table.

### Lỗi 3. Dùng tên cột không tồn tại trong output CTE

```sql
-- Sai vì chosen chỉ xuất order_id, không có customer_id:
-- WITH chosen AS (
--     SELECT order_id FROM cte_lab.orders
-- )
-- SELECT customer_id FROM chosen;
```

CTE chỉ công khai những cột mà truy vấn của nó thực sự trả về. Nếu cần `customer_id` ở cấp ngoài, chọn cột đó trong CTE.

### Lỗi 4. Nghĩ CTE luôn chạy trước và được lưu xuống đĩa

PostgreSQL 12+ có thể fold CTE `SELECT` thuần khi phù hợp. `MATERIALIZED` cho phép thiết lập ranh giới tính toán trong các trường hợp hỗ trợ. Không đoán kế hoạch chỉ từ cú pháp.

### Lỗi 5. Nghĩ NOT MATERIALIZED chắc chắn tăng tốc

Khi CTE dùng nhiều lần và có biểu thức tốn kém, gộp CTE có thể tính lại công việc. Hãy so sánh `EXPLAIN` và workload thay vì coi `NOT MATERIALIZED` là một chỉ dẫn “tối ưu tự động”.

### Lỗi 6. Không có điều kiện dừng ở WITH RECURSIVE

Một chu trình dữ liệu hoặc phép tăng vô hạn có thể khiến truy vấn không kết thúc hợp lý. Phải thiết kế anchor, recursive term, cycle detection và giới hạn tài nguyên.

### Lỗi 7. Tin rằng UNION tự loại mọi chu trình

Nếu hàng recursive chứa `depth` thay đổi, mỗi lần gặp node cũ vẫn là hàng mới theo toàn bộ bộ giá trị. `UNION` không thay thế `CYCLE` hoặc mảng visited path khi cần phát hiện node lặp.

### Lỗi 8. Đọc thứ tự recursive output như một cam kết

Kết quả có thể trông giống breadth-first, nhưng không nên dựa vào đó. Dùng `ORDER BY` trên path, depth hoặc cột `SEARCH ... SET` phù hợp.

### Lỗi 9. Đặt LIMIT ngoài cùng để “chữa” truy vấn vô hạn

Thêm JOIN/ORDER BY/aggregate ở query ngoài có thể buộc PostgreSQL lấy nhiều hàng hơn. Điều kiện dừng phải nằm trong logic đệ quy hoặc cơ chế cycle detection.

### Lỗi 10. Tưởng có WITH thì COUNT(*) sau LEFT JOIN chắc chắn đúng

CTE không tự sửa outer join. Nếu kết quả có một hàng NULL-extended cho khách chưa có đơn, `COUNT(*)` vẫn đếm 1; hãy đếm khóa bên phải `NOT NULL`.

### Lỗi 11. Bỏ qua grain khi nối nhiều CTE tổng hợp

Một CTE có một hàng mỗi khách, CTE khác có một hàng mỗi đơn. Nếu nối không đúng khóa/độ hạt, tổng có thể bị nhân. Ghi rõ đơn vị một hàng và kiểm tra tính duy nhất của khóa JOIN.

### Lỗi 12. Viết data-modifying CTE theo trình tự tưởng tượng

Các DML substatements không phải chuỗi thao tác tuần tự để câu sau đọc lại bảng gốc thấy thay đổi. Truyền dữ liệu bằng `RETURNING`; tránh đụng cùng một target row ở nhiều DML trong một statement.

### Lỗi 13. Dùng CTE tên giống bảng thật nhưng không hiểu scope

Một CTE có thể che khuất tên quan hệ không schema-qualified trong phạm vi truy vấn. Đặt tên mô tả và dùng tên schema khi cần chỉ rõ bảng nguồn.

### Lỗi 14. Nhầm MATERIALIZED CTE với materialized view

CTE không tồn tại sau statement và không có lệnh refresh. Materialized view là đối tượng schema có kết quả lưu và cơ chế refresh riêng.

### Lỗi 15. Tạo quá nhiều CTE “một dòng”

CTE làm rõ logic khi mỗi bước có ý nghĩa. Nhiều bước vô nghĩa có thể khiến SQL khó đọc hơn; ưu tiên tên theo nghiệp vụ và cấu trúc vừa đủ.

### Lỗi 16. Không bảo vệ thông tin nhạy cảm

CTE không tự giới hạn quyền đọc bảng nguồn. Một truy vấn `WITH` có thể join thêm nhiều bảng và trả dữ liệu người dùng không cần thiết. Chỉ chọn cột phục vụ mục đích, dùng role có quyền tối thiểu và tham số hóa input.

## 31. Quy trình viết và kiểm chứng một truy vấn CTE

Khi nhận yêu cầu báo cáo phức tạp, hãy làm theo quy trình:

1. **Định nghĩa đầu ra:** một hàng đại diện đối tượng nào; cần những trường gì?
2. **Xác định nguồn sự thật:** bảng và quan hệ nào cung cấp dữ liệu?
3. **Chia bước theo ngữ nghĩa:** lọc hợp lệ, tính từng đơn, tổng hợp theo khách, xếp hạng, trình bày.
4. **Đặt tên CTE rõ:** `completed_orders`, `order_totals`, `customer_revenue` thay vì `a`, `b`, `tmp1`.
5. **Kiểm tra grain từng CTE:** khóa có duy nhất không? Có hàng không khớp hoặc NULL không?
6. **Kiểm tra kiểu dữ liệu:** aggregate, numeric, timestamp và NULL.
7. **Đối chiếu kết quả:** đếm hàng, tổng tiền, tập ID và dữ liệu biên bằng mẫu có thể tính tay.
8. **Nếu có đệ quy:** định nghĩa anchor, điều kiện dừng, cycle detection, depth và thứ tự output.
9. **Nếu có DML:** xem quyền, ranh giới transaction, locking và `RETURNING`; không chạy thử trên production.
10. **Đo hiệu năng:** `EXPLAIN`, số lần tham chiếu, fold/materialize, index và write overhead.
11. **Chỉ thêm chỉ dẫn MATERIALIZED nếu cần:** so sánh hai phương án dưới workload thực.
12. **Tài liệu hóa giả định:** status nào tính doanh thu, giới hạn sâu bao nhiêu, điều kiện thời gian nào, snapshot/isolation gì.

Mục tiêu không phải tối đa số CTE mà là **kết quả đúng, truy vấn đọc được và hiệu năng phù hợp**.

## 32. Bài tập thực hành

Các bài dựa trên dữ liệu `cte_lab` khởi tạo ở phần 2. Nếu bạn đã chạy các ví dụ DML thay đổi `orders` hoặc lưu trữ jobs, hãy đưa dữ liệu lab về trạng thái ban đầu trước khi so sánh với đáp án cố định.

### Bài 1. CTE lọc đơn

Viết `WITH completed_orders` để lấy `order_id`, `customer_id` của các đơn `status='completed'`, sau đó chọn kết quả theo `order_id`.

**Kỳ vọng:** 1001, 1003, 1004.

### Bài 2. Đặt tên cột

Viết một CTE `pair(x, y)` chứa giá trị 7 và 9, rồi trả `x`, `y` và tổng.

**Kỳ vọng:** 7, 9, 16.

### Bài 3. Tính tổng từng đơn

Dùng CTE tổng hợp `order_items` để trả `order_id` và tổng tiền. Lọc các đơn có tổng ≥ 100 ở cấp query ngoài.

**Kỳ vọng:** 1001 (250), 1003 (300), 1004 (100).

### Bài 4. Mọi khách kể cả không có đơn

Tạo CTE doanh thu `completed` theo khách. `LEFT JOIN` từ `customers` để trả mọi khách, dùng `COALESCE` cho doanh thu 0.

**Kỳ vọng:** An 250, Binh 300, Chi 100, Dung 0.

### Bài 5. Top 2 doanh thu

Tạo ít nhất hai CTE: `customer_revenue` và `ranked`. Dùng `ROW_NUMBER` với khóa phá hòa để lấy 2 khách doanh thu cao nhất.

**Kỳ vọng:** Binh, An.

### Bài 6. Tham chiếu một CTE hai lần

Tạo `completed_totals`, sau đó trả mỗi đơn completed kèm trung bình tổng tiền của mọi đơn completed và cờ `above_average`.

**Gợi ý:** dùng một CTE `stats` nhận dữ liệu từ `completed_totals` rồi `CROSS JOIN` với `completed_totals` ở query cuối.

### Bài 7. So sánh MATERIALIZED và NOT MATERIALIZED

Viết hai phiên bản query lọc một đơn theo `order_id`, một phiên bản `MATERIALIZED`, một phiên bản `NOT MATERIALIZED`. Xem kế hoạch `EXPLAIN`.

**Câu hỏi:** trong trường hợp nào ranh giới materialization có thể khiến PostgreSQL phải đọc nhiều hàng hơn?

### Bài 8. Recursive dãy số

Viết `WITH RECURSIVE` sinh số 1–10, có điều kiện dừng trong recursive term. Trả ra thứ tự tăng dần.

### Bài 9. Duyệt toàn bộ cây danh mục

Tạo recursive CTE từ những node có `parent_id IS NULL` để trả `category_id`, `category_name` và `depth`.

**Kỳ vọng:** danh mục 10,14 có depth 0; 11,12,15 có depth 1; 13 có depth 2.

### Bài 10. Liệt kê hậu duệ của Sách

Anchor tại `category_id = 11`. Trả danh mục 11 và mọi hậu duệ của nó.

**Kỳ vọng:** 11 và 13.

### Bài 11. Dựng đường dẫn

Tạo `display_path` từ tên các category theo cấu trúc gốc tới con. Dự đoán path của category 13.

**Kỳ vọng:** `Sản phẩm / Sách / Sách công nghệ`.

### Bài 12. Ngăn cycle

Trên `graph_edges`, viết recursive CTE bắt đầu từ node 1, lưu danh sách ID đã đi qua trong mảng và không thăm lại node cũ.

**Kỳ vọng:** có đường đi tới các node 1,2,3,4,5; không sinh vô hạn qua vòng 1–2–3–1.

### Bài 13. Dùng CYCLE trên PostgreSQL 14+

Thay mảng visited thủ công bằng `CYCLE node_id SET is_cycle USING cycle_path`. Lọc các hàng được đánh dấu cycle và giải thích vì sao cách này an toàn hơn query không có chặn.

### Bài 14. Data-modifying CTE

Trên bản sao lab của bảng `jobs`, chuyển các job `completed` sang `jobs_archive` bằng `DELETE ... RETURNING` trong CTE và `INSERT ... SELECT` ở statement chính.

**Câu hỏi:** nếu statement gặp lỗi chèn archive, điều gì xảy ra với việc xóa trong cùng statement?

### Bài 15. CTE hay VIEW?

Hệ thống có một báo cáo chỉ dùng một lần và một truy vấn nghiệp vụ được 12 service dùng trong nhiều statement. Chọn CTE hay view cho từng trường hợp, nêu lý do.

### Bài 16. Sai lầm ORDER BY trong CTE

Viết một truy vấn chọn ba đơn mới nhất bằng CTE rồi join tên khách. Dùng `ORDER BY` ở nơi cần thiết để xác định ba đơn và thứ tự đầu ra.

### Bài 17. Phát hiện nhân hàng

Một CTE `daily_totals` có một hàng mỗi khách–ngày; CTE `customer_tags` có nhiều tag mỗi khách. Nếu join rồi `SUM(daily_totals.amount)`, tổng có thể bị nhân. Hãy đề xuất cách đối chiếu và tránh nhân.

### Bài 18. Tạo báo cáo nhiều cấp

Dùng ba CTE: `eligible_orders`, `order_totals` và `customer_summary`. Trả toàn bộ khách và tổng tiền completed, sắp xếp theo doanh thu giảm dần, ID tăng dần.

**Kỳ vọng:** Binh 300, An 250, Chi 100, Dung 0.

## 33. Gợi ý lời giải

### Đáp án 1: lọc completed

```sql
WITH completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT order_id, customer_id
FROM completed_orders
ORDER BY order_id;
```

### Đáp án 2: đặt tên cột

```sql
WITH pair(x, y) AS (
    SELECT 7, 9
)
SELECT x, y, x + y AS total
FROM pair;
```

### Đáp án 3: tổng từng đơn

```sql
WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, amount
FROM totals
WHERE amount >= 100
ORDER BY order_id;
```

### Đáp án 4: giữ mọi khách

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(r.amount, 0) AS completed_revenue
FROM cte_lab.customers AS c
LEFT JOIN revenue AS r
    ON r.customer_id = c.customer_id
ORDER BY c.customer_id;
```

### Đáp án 5: top 2

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
),
ranked AS (
    SELECT
        customer_id,
        amount,
        ROW_NUMBER() OVER (
            ORDER BY amount DESC, customer_id
        ) AS rn
    FROM revenue
)
SELECT
    c.customer_name,
    r.amount
FROM ranked AS r
JOIN cte_lab.customers AS c
    ON c.customer_id = r.customer_id
WHERE r.rn <= 2
ORDER BY r.rn;
```

### Đáp án 6: trung bình tổng tiền

```sql
WITH completed_totals AS (
    SELECT
        o.order_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.order_id
),
stats AS (
    SELECT AVG(amount) AS average_amount
    FROM completed_totals
)
SELECT
    t.order_id,
    t.amount,
    s.average_amount,
    t.amount > s.average_amount AS above_average
FROM completed_totals AS t
CROSS JOIN stats AS s
ORDER BY t.order_id;
```

Ba đơn có tổng 250, 300, 100; trung bình là khoảng 216.67. Hai đơn 1001 và 1003 nằm trên trung bình.

### Đáp án 7: materialization

```sql
EXPLAIN
WITH base AS MATERIALIZED (
    SELECT * FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE order_id = 1003;

EXPLAIN
WITH base AS NOT MATERIALIZED (
    SELECT * FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE order_id = 1003;
```

`MATERIALIZED` có thể tạo ranh giới ngăn điều kiện `order_id` được đẩy xuống source scan theo cùng cách. `NOT MATERIALIZED` cho phép fold một CTE phù hợp để optimizer xét lọc sớm. Kết quả hiệu năng phải đo trên dữ liệu đại diện.

### Đáp án 8: dãy 1–10

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n;
```

### Đáp án 9: cây danh mục

```sql
WITH RECURSIVE tree AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        0 AS depth
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        t.depth + 1
    FROM cte_lab.categories AS c
    JOIN tree AS t
        ON c.parent_id = t.category_id
)
SELECT category_id, category_name, depth
FROM tree
ORDER BY depth, category_id;
```

### Đáp án 10: hậu duệ của danh mục 11

```sql
WITH RECURSIVE branch AS (
    SELECT category_id, category_name, parent_id
    FROM cte_lab.categories
    WHERE category_id = 11

    UNION ALL

    SELECT c.category_id, c.category_name, c.parent_id
    FROM cte_lab.categories AS c
    JOIN branch AS b
        ON c.parent_id = b.category_id
)
SELECT category_id, category_name
FROM branch
ORDER BY category_id;
```

### Đáp án 11: path danh mục

```sql
WITH RECURSIVE paths AS (
    SELECT
        category_id,
        parent_id,
        category_name::text AS path
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        p.path || ' / ' || c.category_name
    FROM cte_lab.categories AS c
    JOIN paths AS p
        ON c.parent_id = p.category_id
)
SELECT category_id, path
FROM paths
WHERE category_id = 13;
```

Đáp án: `Sản phẩm / Sách / Sách công nghệ`. Truy vấn này giả định cây không có chu trình reachable từ root; với nguồn không đáng tin cần path visited hoặc `CYCLE`.

### Đáp án 12: graph visited

```sql
WITH RECURSIVE walk AS (
    SELECT 1::bigint AS node_id,
           ARRAY[1::bigint] AS visited
    UNION ALL
    SELECT e.to_id, w.visited || e.to_id
    FROM walk AS w
    JOIN cte_lab.graph_edges AS e
        ON e.from_id = w.node_id
    WHERE NOT e.to_id = ANY(w.visited)
)
SELECT node_id, visited
FROM walk
ORDER BY visited;
```

### Đáp án 13: CYCLE

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::bigint
    UNION ALL
    SELECT e.to_id
    FROM cte_lab.graph_edges AS e
    JOIN walk AS w ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, cycle_path
FROM walk
WHERE NOT is_cycle
ORDER BY cycle_path;
```

Chỉ dùng khi server hỗ trợ `CYCLE` (PostgreSQL 14+).

### Đáp án 14: di chuyển jobs

```sql
WITH moved AS (
    DELETE FROM cte_lab.jobs
    WHERE job_status = 'completed'
    RETURNING job_id, job_status, payload
)
INSERT INTO cte_lab.jobs_archive (
    job_id, job_status, payload, archived_at
)
SELECT job_id, job_status, payload, now()
FROM moved
RETURNING job_id;
```

Nếu lệnh chèn archive thất bại, statement bị lỗi; các tác động thuộc cùng statement/transaction không được coi là đã commit thành công. Hãy thử trên bản sao lab vì câu SQL này thay đổi dữ liệu.

### Đáp án 15: CTE hay VIEW?

- Báo cáo một lần: CTE thường đủ để tổ chức nhiều bước trong một statement.
- Định nghĩa truy vấn được nhiều service tái sử dụng: view có thể phù hợp nếu nhóm cần một giao diện dữ liệu có tên trong schema, có version và quyền truy cập được quản lý. Cũng cần cân nhắc nhu cầu parameterization và vòng đời migration.

### Đáp án 16: top ba đơn mới nhất

```sql
WITH latest AS (
    SELECT order_id, customer_id, ordered_at
    FROM cte_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
)
SELECT
    l.order_id,
    c.customer_name,
    l.ordered_at
FROM latest AS l
JOIN cte_lab.customers AS c
    ON c.customer_id = l.customer_id
ORDER BY l.ordered_at DESC, l.order_id DESC;
```

### Đáp án 17: kiểm soát nhân hàng

Kiểm tra mỗi `customer_id` có bao nhiêu tag trước JOIN, so sánh `COUNT(*)` và `COUNT(DISTINCT order_id)` ở grain phù hợp. Nếu chỉ cần biết khách có tag, dùng `EXISTS`; nếu cần số liệu trên từng tag, hãy tổng hợp ở grain đúng trước khi nối và xác định chính sách phân bổ tiền nếu một giao dịch thuộc nhiều tag.

Không dùng `SUM(DISTINCT amount)` làm giải pháp tổng quát: hai đơn khác nhau có thể có cùng số tiền.

### Đáp án 18: báo cáo nhiều cấp

```sql
WITH eligible_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
),
order_totals AS (
    SELECT
        e.order_id,
        e.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM eligible_orders AS e
    JOIN cte_lab.order_items AS i
        ON i.order_id = e.order_id
    GROUP BY e.order_id, e.customer_id
),
customer_summary AS (
    SELECT customer_id, SUM(amount) AS revenue
    FROM order_totals
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.revenue, 0) AS revenue
FROM cte_lab.customers AS c
LEFT JOIN customer_summary AS s
    ON s.customer_id = c.customer_id
ORDER BY revenue DESC, c.customer_id;
```

## 34. Tổng kết

`WITH` trong PostgreSQL giúp **tổ chức một SQL statement thành những bước có tên**, làm rõ mục đích và tính toán trung gian:

- CTE `SELECT` có phạm vi trong **một statement**. Nó không tạo bảng/view lâu dài.
- Một câu `WITH` có thể chứa **nhiều CTE**; CTE sau dùng CTE trước để chia logic lọc, JOIN, aggregate và window function.
- Với PostgreSQL 12+, một CTE `SELECT` thuần, không đệ quy và đáp ứng điều kiện phù hợp có thể được **fold** vào query cha. `MATERIALIZED` và `NOT MATERIALIZED` điều khiển một số ranh giới tối ưu, nhưng không tự bảo đảm nhanh hơn.
- `WITH RECURSIVE` dùng **anchor + recursive term**, thường qua `UNION ALL`, để duyệt cây/đồ thị. Cần điều kiện dừng, chống chu trình và giới hạn workload.
- PostgreSQL 14+ hỗ trợ `SEARCH` và `CYCLE` để xây khóa thứ tự duyệt và phát hiện node lặp trong recursive CTE; muốn sắp thứ tự ổn định vẫn cần `ORDER BY`.
- `WITH` có thể phối hợp DML. Với **data-modifying CTE**, `RETURNING` là kênh chính thức chuyển dữ liệu giữa thao tác thay đổi và statement chính; không dựa vào thứ tự DML substatement được suy ra từ vị trí văn bản.
- CTE không thay thế transaction, constraint, index, view hay bảng tạm. Nó cũng không tự sửa lỗi `JOIN` nhân hàng, `NULL`, aggregation sai grain hoặc SQL injection.

Một truy vấn CTE tốt là truy vấn mà mỗi tên CTE trả lời được câu hỏi: **“Bước này biến dữ liệu thành tập hàng có ý nghĩa gì, ở grain nào, để bước tiếp theo dùng ra sao?”** Khi kết hợp câu hỏi đó với phép kiểm chứng kết quả và `EXPLAIN`, `WITH` trở thành công cụ mạnh để viết SQL PostgreSQL nâng cao vừa rõ ràng vừa đáng tin.
