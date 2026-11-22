# Xếp hạng sản phẩm, tính lũy kế và so sánh theo tháng

Báo cáo bán hàng thường cần trả lời đồng thời nhiều câu hỏi: sản phẩm nào bán chạy nhất trong từng danh mục, doanh thu cộng dồn đến ngày hiện tại là bao nhiêu, tháng này tăng hay giảm so với tháng trước, và sản phẩm nào nằm trong top 3 mỗi tháng. Đây là nhóm bài toán rất phù hợp với **window functions**, kết hợp với aggregation, date series và các phép JOIN.

Điểm quan trọng là chọn đúng mức độ chi tiết trước khi tính. Nếu dữ liệu nguồn có một hàng cho mỗi dòng bán hàng, muốn xếp hạng sản phẩm thì phải cộng doanh thu theo sản phẩm trước. Muốn tính lũy kế theo ngày thì thường phải gom về một hàng mỗi ngày trước khi chạy `SUM() OVER`. Muốn so sánh tháng liên tiếp, phải quyết định tháng không có giao dịch được xem là **0** hay **không có dữ liệu**, và phải tạo đủ các tháng trên lịch nếu cần so đúng tháng liền trước.

Bài học này dùng PostgreSQL làm môi trường thực hành, giải thích cách chuyển các bước tương tự sang MySQL 8+, SQL Server, Oracle và SQLite phiên bản có hỗ trợ window functions. Các nội dung chính:

- Xếp hạng sản phẩm toàn bộ và trong từng danh mục bằng `ROW_NUMBER`, `RANK`, `DENSE_RANK`.
- Lấy top N có hoặc không giữ các trường hợp đồng hạng.
- Tính doanh thu lũy kế theo sản phẩm, danh mục và toàn hệ thống.
- Phân biệt window frame `ROWS` và `RANGE`.
- Tính rolling totals và lũy kế theo tháng.
- So sánh Month-over-Month (MoM), Year-over-Year (YoY), chênh lệch tuyệt đối và tỷ lệ phần trăm.
- Xử lý tháng không có giao dịch, NULL, mẫu số bằng 0, timezone và precision.
- Kiểm thử kết quả, tối ưu index và đọc execution plan.

> **Nguyên tắc:** aggregate về đúng grain trước, sau đó mới xếp hạng hoặc chạy lũy kế; dùng `PARTITION BY` để xác định phạm vi reset; dùng `ORDER BY` cùng tie-breaker khi cần thứ tự xác định; và tạo calendar rows nếu phép so sánh yêu cầu đủ mọi tháng.

## 1. Ba loại bài toán và ba cách nghĩ khác nhau

### 1.1. Xếp hạng (ranking)

Xếp hạng trả lời câu hỏi: sản phẩm nào đứng thứ mấy theo doanh thu, số lượng bán hoặc lợi nhuận?

Ví dụ dữ liệu đã tổng hợp:

| Sản phẩm | Danh mục | Doanh thu |
| --- | --- | ---: |
| Laptop | Electronics | 3.900 |
| Phone | Electronics | 4.350 |
| Headphones | Electronics | 740 |
| Desk | Furniture | 1.220 |
| Chair | Furniture | 300 |

Ta có thể xếp hạng:
- Toàn bộ sản phẩm.
- Trong từng danh mục.
- Riêng từng tháng.
- Theo nhiều tiêu chí, ví dụ doanh thu giảm dần rồi số lượng giảm dần.

### 1.2. Lũy kế (running/cumulative total)

Lũy kế là tổng từ điểm bắt đầu đến hàng hiện tại theo một thứ tự:

| Ngày | Doanh thu ngày | Doanh thu lũy kế |
| --- | ---: | ---: |
| 01/01 | 1.000 | 1.000 |
| 02/01 | 500 | 1.500 |
| 03/01 | 250 | 1.750 |
| 04/01 | 800 | 2.550 |

Lũy kế có thể reset:
- Mỗi sản phẩm.
- Mỗi danh mục.
- Mỗi customer.
- Mỗi tháng hoặc mỗi năm.
- Không reset, cho toàn hệ thống.

### 1.3. So sánh theo tháng (period-over-period)

MoM so sánh một tháng với tháng ngay trước đó:

\[
\text{MoM change} = \text{Current month} - \text{Previous month}
\]

\[
\text{MoM \%} =
\frac{\text{Current} - \text{Previous}}{\text{Previous}}\times 100
\]

Ví dụ tháng 3 doanh thu 1.200, tháng 2 doanh thu 1.000:

- Chênh lệch tuyệt đối: `+200`.
- Tỷ lệ thay đổi: `+20%`.

Nếu tháng trước bằng 0, tỷ lệ phần trăm không xác định theo công thức thông thường. Phải định nghĩa rõ cách hiển thị thay vì chia cho 0 hoặc tự gán một tỷ lệ tùy tiện.

## 2. Chuẩn bị dữ liệu PostgreSQL

Các ví dụ dùng bảng `TEMP`, tồn tại trong session tạo bảng. Chạy toàn bộ phần setup và truy vấn trong **cùng một PostgreSQL connection/session**. Nếu thực hành bằng JDBC hoặc một ứng dụng mở connection riêng, tạo dữ liệu lab trên chính connection ấy hoặc chuyển sang schema lab riêng.

### 2.1. Tạo bảng sản phẩm và giao dịch

Mỗi hàng `demo_product_sales` đại diện cho một dòng bán hàng của một sản phẩm. Một sản phẩm có thể xuất hiện nhiều lần trong cùng ngày/tháng.

```sql
CREATE TEMP TABLE demo_products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TEMP TABLE demo_product_sales (
    sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id INTEGER NOT NULL
        REFERENCES demo_products(product_id),
    sold_at TIMESTAMPTZ NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0),
    status TEXT NOT NULL CHECK (
        status IN ('COMPLETED', 'CANCELED')
    )
);
```

### 2.2. Thêm sản phẩm

```sql
INSERT INTO demo_products
    (product_id, product_name, category, active)
VALUES
    (1, 'Laptop', 'Electronics', TRUE),
    (2, 'Phone', 'Electronics', TRUE),
    (3, 'Headphones', 'Electronics', TRUE),
    (4, 'Desk', 'Furniture', TRUE),
    (5, 'Chair', 'Furniture', TRUE),
    (6, 'Lamp', 'Furniture', TRUE),
    (7, 'Notebook', 'Stationery', TRUE),
    (8, 'Pen', 'Stationery', TRUE);
```

Sản phẩm `Lamp` chưa có giao dịch. Đây là trường hợp hữu ích để kiểm tra LEFT JOIN, doanh thu 0 và ranking.

### 2.3. Thêm giao dịch từ tháng 1 đến tháng 4

```sql
INSERT INTO demo_product_sales
    (product_id, sold_at, quantity, unit_price, discount_amount, status)
VALUES
    (1, '2026-01-05 09:00:00+07', 2, 1000.00, 100.00, 'COMPLETED'),
    (1, '2026-01-15 10:00:00+07', 1, 1000.00,  50.00, 'COMPLETED'),
    (2, '2026-01-10 11:00:00+07', 3,  500.00,   0.00, 'COMPLETED'),
    (3, '2026-01-12 12:00:00+07', 5,   80.00,   0.00, 'COMPLETED'),
    (4, '2026-01-20 13:00:00+07', 1,  300.00,   0.00, 'COMPLETED'),

    (1, '2026-02-02 09:00:00+07', 1, 1000.00,   0.00, 'COMPLETED'),
    (2, '2026-02-03 10:00:00+07', 2,  500.00,   0.00, 'COMPLETED'),
    (2, '2026-02-15 11:00:00+07', 1,  500.00,  50.00, 'COMPLETED'),
    (3, '2026-02-20 12:00:00+07', 2,   80.00,   0.00, 'COMPLETED'),
    (5, '2026-02-21 13:00:00+07', 4,   50.00,   0.00, 'COMPLETED'),

    (1, '2026-03-01 09:00:00+07', 1, 1000.00,   0.00, 'COMPLETED'),
    (2, '2026-03-02 10:00:00+07', 1,  500.00,   0.00, 'COMPLETED'),
    (4, '2026-03-08 11:00:00+07', 2,  300.00,   0.00, 'COMPLETED'),
    (5, '2026-03-11 12:00:00+07', 2,   50.00,   0.00, 'COMPLETED'),
    (7, '2026-03-14 13:00:00+07', 10,   5.00,   0.00, 'COMPLETED'),

    (1, '2026-04-01 09:00:00+07', 1, 1100.00,   0.00, 'COMPLETED'),
    (2, '2026-04-02 10:00:00+07', 3,  450.00,   0.00, 'COMPLETED'),
    (3, '2026-04-03 11:00:00+07', 2,   90.00,   0.00, 'COMPLETED'),
    (4, '2026-04-10 12:00:00+07', 1,  320.00,   0.00, 'COMPLETED'),
    (8, '2026-04-12 13:00:00+07', 20,   2.00,   0.00, 'COMPLETED'),

    (6, '2026-04-15 14:00:00+07', 5,  100.00,   0.00, 'CANCELED');
```

Các giao dịch được chọn để có:
- Nhiều sản phẩm cùng danh mục.
- Nhiều giao dịch cho cùng sản phẩm trong tháng.
- Một số sản phẩm không bán trong một vài tháng.
- Một sản phẩm chưa từng bán.
- Một giao dịch bị hủy cần loại khỏi doanh thu.
- Nhiều ngày và nhiều mức doanh thu.

### 2.4. Kiểm tra dữ liệu nguồn

```sql
SELECT
    p.category,
    p.product_id,
    p.product_name,
    COUNT(s.sale_id) AS sale_rows,
    COALESCE(
        SUM(s.quantity * s.unit_price - s.discount_amount)
            FILTER (WHERE s.status = 'COMPLETED'),
        0
    ) AS revenue
FROM demo_products AS p
LEFT JOIN demo_product_sales AS s
    ON s.product_id = p.product_id
GROUP BY p.category, p.product_id, p.product_name
ORDER BY p.category, p.product_id;
```

Lưu ý:
- `COUNT(s.sale_id)` trả 0 cho sản phẩm không có giao dịch.
- `COUNT(*)` trên LEFT JOIN sẽ đếm hàng placeholder của sản phẩm không có sale thành 1.
- `FILTER` là cú pháp PostgreSQL; có thể thay bằng `SUM(CASE WHEN ... THEN ... ELSE 0 END)` để portable hơn.

## 3. Xác định đúng grain trước khi xếp hạng

**Grain** là ý nghĩa của một hàng trong tập kết quả.

Bảng nguồn ở lab có grain là một dòng bán hàng. Nhưng yêu cầu “xếp hạng sản phẩm theo doanh thu” cần grain là **một hàng cho mỗi sản phẩm**.

Không xếp hạng trực tiếp từng dòng sale:

```sql
SELECT
    product_id,
    quantity * unit_price - discount_amount AS line_revenue,
    RANK() OVER (
        ORDER BY quantity * unit_price - discount_amount DESC
    ) AS sale_rank
FROM demo_product_sales
WHERE status = 'COMPLETED';
```

Query trên xếp hạng từng dòng giao dịch, không xếp hạng tổng doanh thu sản phẩm. Một sản phẩm có 10 dòng bán nhỏ có thể đứng sau sản phẩm chỉ có một dòng bán lớn dù tổng doanh thu của nó cao hơn.

### 3.1. Aggregate trước, rank sau

```sql
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(
            SUM(s.quantity * s.unit_price - s.discount_amount),
            0
        ) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
       AND s.status = 'COMPLETED'
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT *
FROM product_revenue
ORDER BY revenue DESC, product_id;
```

Bây giờ mỗi sản phẩm chỉ có một hàng, kể cả sản phẩm không bán.

### 3.2. Vì sao status condition đặt ở ON?

Ta muốn giữ sản phẩm không có giao dịch completed. Nếu viết:

```sql
FROM demo_products AS p
LEFT JOIN demo_product_sales AS s
    ON s.product_id = p.product_id
WHERE s.status = 'COMPLETED'
```

các sản phẩm không có sale sẽ bị loại vì `s.status` là NULL. Điều kiện ở WHERE khiến LEFT JOIN có hiệu quả như INNER JOIN đối với predicate ấy.

Đặt `s.status = 'COMPLETED'` trong ON giúp giữ mọi sản phẩm và chỉ ghép sale hợp lệ.

### 3.3. CTE tạo các bước có thể đọc được

Một query phân tích thường có pipeline:

```text
Bảng giao dịch
     |
     v
Lọc thời gian và trạng thái
     |
     v
Aggregate theo product/month/day
     |
     v
Window function: rank / cumulative / lag
     |
     v
Filter top-N hoặc tính tỷ lệ
     |
     v
ORDER BY cuối cùng
```

CTE (`WITH`) giúp đặt tên từng grain. Optimizer có thể inline hoặc materialize tùy DBMS/version/điều kiện; CTE không mặc định là bảng tạm vật lý.

## 4. Ba hàm xếp hạng quan trọng

Giả sử doanh thu theo sản phẩm đã tổng hợp:

| Sản phẩm | Doanh thu |
| --- | ---: |
| Phone | 4.350 |
| Laptop | 3.900 |
| Desk | 900 |
| Headphones | 740 |
| Chair | 300 |
| Notebook | 50 |
| Pen | 40 |
| Lamp | 0 |

Ba hàm:

- `ROW_NUMBER()`: đánh số từng hàng 1, 2, 3…; không tạo đồng hạng.
- `RANK()`: các hàng cùng giá trị sort nhận cùng hạng, hạng sau có khoảng nhảy.
- `DENSE_RANK()`: các hàng cùng giá trị nhận cùng hạng, hạng kế tiếp không nhảy.

### 4.1. Ví dụ có đồng hạng

Giả sử doanh thu:

| Sản phẩm | Revenue | ROW_NUMBER | RANK | DENSE_RANK |
| --- | ---: | ---: | ---: | ---: |
| A | 100 | 1 | 1 | 1 |
| B | 90 | 2 | 2 | 2 |
| C | 90 | 3 | 2 | 2 |
| D | 80 | 4 | 4 | 3 |
| E | 70 | 5 | 5 | 4 |

Khác biệt nằm ở hàng D:
- `ROW_NUMBER`: 4 vì mỗi hàng có vị trí riêng.
- `RANK`: 4 vì hai hàng B/C cùng hạng 2, bỏ qua hạng 3.
- `DENSE_RANK`: 3 vì chỉ đếm các mức giá trị khác nhau.

### 4.2. Xếp hạng toàn bộ sản phẩm

```sql
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(
            SUM(s.quantity * s.unit_price - s.discount_amount),
            0
        ) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
       AND s.status = 'COMPLETED'
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT
    product_id,
    product_name,
    category,
    revenue,
    ROW_NUMBER() OVER (
        ORDER BY revenue DESC, product_id ASC
    ) AS row_number_rank,
    RANK() OVER (
        ORDER BY revenue DESC
    ) AS competition_rank,
    DENSE_RANK() OVER (
        ORDER BY revenue DESC
    ) AS dense_rank
FROM product_revenue
ORDER BY revenue DESC, product_id ASC;
```

Chú ý:
- `ROW_NUMBER` có `product_id` tie-breaker để kết quả ổn định.
- `RANK` và `DENSE_RANK` chỉ sort theo revenue để các sản phẩm doanh thu bằng nhau thật sự đồng hạng.
- Nếu thêm `product_id` vào ORDER BY của `RANK`, các hàng có cùng revenue nhưng khác ID không còn là peers, do đó mất tie.

### 4.3. Ranking theo từng danh mục với PARTITION BY

```sql
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(
            SUM(s.quantity * s.unit_price - s.discount_amount),
            0
        ) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
       AND s.status = 'COMPLETED'
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT
    product_id,
    product_name,
    category,
    revenue,
    DENSE_RANK() OVER (
        PARTITION BY category
        ORDER BY revenue DESC
    ) AS category_rank
FROM product_revenue
ORDER BY category, category_rank, product_id;
```

`PARTITION BY category` chia dữ liệu thành các nhóm độc lập. Hạng bắt đầu lại từ 1 trong mỗi danh mục. Nó không gộp các hàng như `GROUP BY`.

### 4.4. PARTITION BY khác GROUP BY

- `GROUP BY category` tạo một hàng mỗi category nếu chỉ chọn category và aggregate.
- `PARTITION BY category` giữ từng hàng sản phẩm và tính thứ hạng/tổng trên nhóm category đó.

Đây là khác biệt nền tảng giữa aggregate và window function.

## 5. Lấy top N sản phẩm

Window function được tính sau WHERE/GROUP BY ở cùng query level. Vì vậy, không thể lọc trực tiếp `WHERE rank <= 3` ở cùng SELECT list đã tạo alias rank. Dùng CTE/subquery.

### 5.1. Top 3 sản phẩm mỗi category: tối đa đúng 3 hàng

```sql
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(SUM(
            CASE WHEN s.status = 'COMPLETED'
                 THEN s.quantity * s.unit_price - s.discount_amount
                 ELSE 0
            END
        ), 0) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
    GROUP BY p.product_id, p.product_name, p.category
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY category
            ORDER BY revenue DESC, product_id
        ) AS rn
    FROM product_revenue
)
SELECT product_id, product_name, category, revenue
FROM ranked
WHERE rn <= 3
ORDER BY category, rn;
```

`ROW_NUMBER <= 3` đảm bảo tối đa ba hàng mỗi category. Nếu doanh thu bằng nhau ở ranh giới top 3, tie-breaker product_id quyết định ai được chọn.

### 5.2. Top 3 rank, giữ đồng hạng tại ranh giới

```sql
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(SUM(
            CASE WHEN s.status = 'COMPLETED'
                 THEN s.quantity * s.unit_price - s.discount_amount
                 ELSE 0
            END
        ), 0) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
    GROUP BY p.product_id, p.product_name, p.category
),
ranked AS (
    SELECT
        *,
        RANK() OVER (
            PARTITION BY category
            ORDER BY revenue DESC
        ) AS rnk
    FROM product_revenue
)
SELECT *
FROM ranked
WHERE rnk <= 3
ORDER BY category, rnk, product_id;
```

Có thể trả hơn ba hàng nếu nhiều sản phẩm đồng hạng. Vì `RANK` có khoảng nhảy, hạng 1, 1, 3 vẫn thỏa `rnk <= 3`.

### 5.3. Top 3 mức doanh thu khác nhau

```sql
DENSE_RANK() OVER (
    PARTITION BY category
    ORDER BY revenue DESC
)
```

Lọc `dense_rank <= 3` trả tất cả sản phẩm thuộc ba **mức doanh thu cao nhất** trong từng category. Nếu mức doanh thu thứ ba có 10 sản phẩm, tất cả 10 đều được trả.

### 5.4. Chọn đúng định nghĩa top-N

| Yêu cầu nghiệp vụ | Hàm |
| --- | --- |
| Chính xác tối đa N sản phẩm, có tie-breaker | `ROW_NUMBER()` |
| Top N vị trí, giữ tie và có khoảng nhảy | `RANK()` |
| Top N mức giá trị khác nhau, không nhảy hạng | `DENSE_RANK()` |

Không chọn hàm chỉ vì tên nghe phù hợp. Hãy xác định người dùng muốn “ba dòng”, “ba vị trí” hay “ba mức doanh thu”.

## 6. Xếp hạng sản phẩm trong từng tháng

Trước hết aggregate theo tháng và sản phẩm:

```sql
WITH monthly_product_sales AS (
    SELECT
        date_trunc(
            'month',
            s.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        p.category,
        p.product_id,
        p.product_name,
        SUM(s.quantity * s.unit_price - s.discount_amount) AS revenue
    FROM demo_product_sales AS s
    JOIN demo_products AS p
        ON p.product_id = s.product_id
    WHERE s.status = 'COMPLETED'
      AND s.sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND s.sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY
        date_trunc(
            'month',
            s.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date,
        p.category,
        p.product_id,
        p.product_name
),
ranked AS (
    SELECT
        *,
        DENSE_RANK() OVER (
            PARTITION BY month_start, category
            ORDER BY revenue DESC
        ) AS category_month_rank
    FROM monthly_product_sales
)
SELECT *
FROM ranked
WHERE category_month_rank <= 3
ORDER BY month_start, category, category_month_rank, product_id;
```

Ở đây:
- `PARTITION BY month_start, category` reset ranking mỗi tháng và danh mục.
- `ORDER BY revenue DESC` xếp doanh thu cao trước.
- Sản phẩm không có sale trong tháng không xuất hiện trong CTE. Nếu muốn sản phẩm không bán vẫn có doanh thu 0 và được xếp hạng, cần tạo grid tháng × sản phẩm rồi LEFT JOIN, như phần so sánh MoM.

### 6.1. Ranking chỉ trên sản phẩm có giao dịch

Đây thường là contract cho leaderboard: chỉ xếp hạng sản phẩm thực sự bán được trong tháng.

### 6.2. Ranking gồm cả sản phẩm doanh thu 0

Phù hợp khi dashboard phải hiển thị danh mục đầy đủ. Nhưng nếu tất cả sản phẩm không bán đều có revenue 0, chúng có thể đồng hạng. Cần cân nhắc hiển thị riêng “không có giao dịch” thay vì coi như đã tham gia cạnh tranh.

## 7. Window SUM để tính lũy kế

Window aggregate dùng cú pháp:

```sql
SUM(expression) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN ...
)
```

Ví dụ tổng lũy kế toàn bộ giao dịch theo thời gian:

```sql
SELECT
    sale_id,
    sold_at,
    quantity * unit_price - discount_amount AS sale_revenue,
    SUM(quantity * unit_price - discount_amount) OVER (
        ORDER BY sold_at, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM demo_product_sales
WHERE status = 'COMPLETED'
ORDER BY sold_at, sale_id;
```

### 7.1. Ý nghĩa window frame

- `UNBOUNDED PRECEDING`: bắt đầu từ hàng đầu tiên trong partition.
- `CURRENT ROW`: kết thúc tại hàng hiện tại.
- `ROWS`: tính theo số hàng vật lý trong thứ tự window.
- `BETWEEN ... AND ...`: định nghĩa khoảng hàng được aggregate.

Với `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, mỗi hàng cộng tất cả hàng trước đó và chính nó.

### 7.2. Lũy kế reset theo sản phẩm

```sql
SELECT
    product_id,
    sale_id,
    sold_at,
    quantity * unit_price - discount_amount AS sale_revenue,
    SUM(quantity * unit_price - discount_amount) OVER (
        PARTITION BY product_id
        ORDER BY sold_at, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS product_cumulative_revenue
FROM demo_product_sales
WHERE status = 'COMPLETED'
ORDER BY product_id, sold_at, sale_id;
```

`PARTITION BY product_id` làm tổng lũy kế bắt đầu lại cho từng sản phẩm.

### 7.3. Lũy kế theo danh mục

```sql
SELECT
    p.category,
    s.sale_id,
    s.sold_at,
    s.quantity * s.unit_price - s.discount_amount AS sale_revenue,
    SUM(s.quantity * s.unit_price - s.discount_amount) OVER (
        PARTITION BY p.category
        ORDER BY s.sold_at, s.sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS category_cumulative_revenue
FROM demo_product_sales AS s
JOIN demo_products AS p
    ON p.product_id = s.product_id
WHERE s.status = 'COMPLETED'
ORDER BY p.category, s.sold_at, s.sale_id;
```

### 7.4. ORDER BY bên trong OVER khác ORDER BY cuối query

`ORDER BY` trong `OVER` quyết định thứ tự tính window. `ORDER BY` cuối query quyết định thứ tự trình bày kết quả.

Ví dụ có thể tính cumulative theo `sold_at, sale_id` nhưng cuối cùng hiển thị theo `product_id, sold_at`. Hai ORDER BY phục vụ hai mục đích khác nhau.

## 8. ROWS và RANGE: tránh sai lũy kế khi có ties

Nếu chỉ viết:

```sql
SUM(amount) OVER (ORDER BY sold_at)
```

DBMS dùng frame mặc định có semantics dựa trên `RANGE` khi có ORDER BY trong nhiều dialect. Những hàng có cùng giá trị sort key là peers và có thể cùng nhận tổng lũy kế đến hết nhóm peer.

Ví dụ:

| sale_id | sold_at | amount |
| ---: | --- | ---: |
| 1 | 09:00 | 10 |
| 2 | 09:00 | 20 |
| 3 | 10:00 | 5 |

Với frame RANGE theo `sold_at`, hai hàng 09:00 có thể cùng thấy cumulative 30. Với ROWS và thứ tự có tie-breaker, kết quả tuần tự có thể là 10 rồi 30.

### 8.1. ROWS: từng hàng theo thứ tự

```sql
SUM(amount) OVER (
    ORDER BY sold_at, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Dùng khi cần số dư/lũy kế tăng sau mỗi giao dịch riêng biệt.

### 8.2. RANGE: theo giá trị sort và nhóm peers

```sql
SUM(amount) OVER (
    ORDER BY sold_at
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Dùng khi các hàng có cùng sort value được xem như cùng một nhóm thời điểm. Cú pháp RANGE có giới hạn khác nhau giữa DBMS; offset RANGE trên một số kiểu dữ liệu cũng khác nhau.

### 8.3. GROUPS

Một số DBMS, bao gồm PostgreSQL hiện đại, hỗ trợ frame `GROUPS`, đếm theo nhóm peer thay vì từng hàng hoặc khoảng giá trị. Đây là tính năng nâng cao; không portable trên mọi hệ quản trị.

### 8.4. Luôn viết frame tường minh khi logic quan trọng

Đừng dựa vào default frame nếu kết quả tài chính hoặc số dư phải chính xác từng hàng. Viết rõ:
- Sort keys.
- Tie-breaker.
- ROWS/RANGE/GROUPS.
- Start/end frame.

## 9. Tổng lũy kế theo ngày

Dữ liệu nguồn có thể có nhiều giao dịch trong một ngày. Nếu muốn một hàng mỗi ngày, aggregate trước:

```sql
WITH daily_sales AS (
    SELECT
        (sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sale_day,
        SUM(quantity * unit_price - discount_amount) AS daily_revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY (sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    sale_day,
    daily_revenue,
    SUM(daily_revenue) OVER (
        ORDER BY sale_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_sales
ORDER BY sale_day;
```

Kết quả chỉ có các ngày có giao dịch. Nếu muốn hiển thị cả ngày doanh thu 0, cần tạo calendar day series rồi LEFT JOIN.

### 9.1. Tạo calendar ngày đầy đủ

```sql
WITH calendar AS (
    SELECT d::date AS sale_day
    FROM generate_series(
        DATE '2026-01-01',
        DATE '2026-04-30',
        INTERVAL '1 day'
    ) AS g(d)
),
daily_sales AS (
    SELECT
        (sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sale_day,
        SUM(quantity * unit_price - discount_amount) AS daily_revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY (sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
),
daily_grid AS (
    SELECT
        c.sale_day,
        COALESCE(d.daily_revenue, 0::numeric) AS daily_revenue
    FROM calendar AS c
    LEFT JOIN daily_sales AS d USING (sale_day)
)
SELECT
    sale_day,
    daily_revenue,
    SUM(daily_revenue) OVER (
        ORDER BY sale_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_grid
ORDER BY sale_day;
```

Giờ mỗi ngày đều có một hàng. Ngày không bán có daily revenue 0, cumulative giữ nguyên so với ngày trước.

### 9.2. Calendar và timezone

Trong ví dụ, ngày được xác định theo `Asia/Ho_Chi_Minh`. Nếu business dùng timezone khác, đổi timezone. Với `TIMESTAMPTZ`, mốc ngày local cần được chuyển đúng về instant khi lọc. Dùng khoảng nửa mở `[start, end)` để tránh lỗi ở thời điểm cuối ngày và precision.

## 10. Lũy kế theo tháng và rolling total

Sau khi aggregate về một hàng mỗi tháng, tính lũy kế:

```sql
WITH monthly_sales AS (
    SELECT
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY 1
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM monthly_sales
ORDER BY month_start;
```

### 10.1. Rolling 3-month sum

```sql
WITH monthly_sales AS (
    SELECT
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
    GROUP BY 1
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3_rows_revenue
FROM monthly_sales
ORDER BY month_start;
```

Tên alias `rolling_3_rows_revenue` cố ý nói rõ đây là ba hàng gần nhất. Nếu có tháng không giao dịch, query trên bỏ tháng đó; ba hàng gần nhất có thể là ba tháng có dữ liệu, không phải ba tháng lịch liên tiếp.

### 10.2. Rolling 3 calendar months cần dense month grid

Để `ROWS BETWEEN 2 PRECEDING` có nghĩa ba tháng lịch, phải tạo đủ mỗi tháng trước khi window:

```sql
WITH months AS (
    SELECT g::date AS month_start
    FROM generate_series(
        DATE '2026-01-01',
        DATE '2026-04-01',
        INTERVAL '1 month'
    ) AS g
),
monthly_sales AS (
    SELECT
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY 1
),
dense_months AS (
    SELECT
        m.month_start,
        COALESCE(s.revenue, 0::numeric) AS revenue
    FROM months AS m
    LEFT JOIN monthly_sales AS s USING (month_start)
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3_calendar_month_revenue
FROM dense_months
ORDER BY month_start;
```

## 11. So sánh doanh thu theo tháng bằng LAG

`LAG(value, offset)` lấy giá trị từ hàng trước đó trong window order, không cần self-join.

### 11.1. Tổng doanh thu toàn hệ thống theo tháng

```sql
WITH monthly_sales AS (
    SELECT
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY 1
),
with_previous AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (
            ORDER BY month_start
        ) AS previous_month_revenue
    FROM monthly_sales
)
SELECT
    month_start,
    revenue,
    previous_month_revenue,
    revenue - previous_month_revenue AS revenue_change,
    CASE
        WHEN previous_month_revenue IS NULL THEN NULL
        WHEN previous_month_revenue = 0 THEN NULL
        ELSE ROUND(
            100.0 * (revenue - previous_month_revenue)
            / previous_month_revenue,
            2
        )
    END AS mom_change_percent
FROM with_previous
ORDER BY month_start;
```

### 11.2. LAG chỉ nhìn hàng trước có trong input

Nếu dữ liệu có tháng 1, tháng 2, tháng 4 nhưng không có tháng 3, `LAG` ở tháng 4 sẽ lấy tháng 2. Nó không tự biết rằng tháng 3 bị thiếu.

Đây là khác biệt quan trọng:
- **Previous observed row**: hàng trước đó trong tập query.
- **Previous calendar month**: tháng lịch ngay trước, dù tháng đó không có giao dịch.

Nếu cần so đúng tháng liền trước, tạo dense calendar trước khi gọi LAG.

## 12. Tạo đủ tháng và so sánh MoM đúng tháng liền trước

### 12.1. Tạo calendar month series

```sql
WITH months AS (
    SELECT g::date AS month_start
    FROM generate_series(
        DATE '2026-01-01',
        DATE '2026-04-01',
        INTERVAL '1 month'
    ) AS g
)
SELECT *
FROM months
ORDER BY month_start;
```

Kết quả có bốn hàng: ngày đầu tháng 1, 2, 3 và 4.

### 12.2. Monthly revenue theo sản phẩm

```sql
WITH monthly_sales AS (
    SELECT
        product_id,
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY product_id, 2
)
SELECT *
FROM monthly_sales
ORDER BY product_id, month_start;
```

Sản phẩm 3 không có sale trong tháng 3. Nếu gọi LAG trực tiếp trên CTE này, tháng 4 của sản phẩm 3 sẽ so với tháng 2, không phải tháng 3.

### 12.3. Dense grid sản phẩm × tháng

```sql
WITH months AS (
    SELECT g::date AS month_start
    FROM generate_series(
        DATE '2026-01-01',
        DATE '2026-04-01',
        INTERVAL '1 month'
    ) AS g
),
monthly_sales AS (
    SELECT
        product_id,
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY product_id, 2
),
product_month_grid AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        m.month_start,
        COALESCE(ms.revenue, 0::numeric) AS revenue
    FROM demo_products AS p
    CROSS JOIN months AS m
    LEFT JOIN monthly_sales AS ms
        ON ms.product_id = p.product_id
       AND ms.month_start = m.month_start
    WHERE p.active = TRUE
),
with_previous AS (
    SELECT
        *,
        LAG(revenue) OVER (
            PARTITION BY product_id
            ORDER BY month_start
        ) AS previous_month_revenue
    FROM product_month_grid
)
SELECT
    product_id,
    product_name,
    category,
    month_start,
    revenue,
    previous_month_revenue,
    revenue - previous_month_revenue AS revenue_change,
    CASE
        WHEN previous_month_revenue IS NULL THEN NULL
        WHEN previous_month_revenue = 0 THEN NULL
        ELSE ROUND(
            100.0 * (revenue - previous_month_revenue)
            / previous_month_revenue,
            2
        )
    END AS mom_change_percent
FROM with_previous
ORDER BY product_id, month_start;
```

Bây giờ mỗi sản phẩm có đủ bốn tháng. Tháng không có giao dịch được thể hiện bằng doanh thu 0. `LAG` vì thế lấy đúng tháng lịch liền trước.

### 12.4. Grid có thể lớn

Số hàng grid là:

\[
\text{Số sản phẩm} \times \text{Số tháng}
\]

Nếu có 100.000 sản phẩm và 120 tháng, grid có 12 triệu hàng. Cần giới hạn sản phẩm, khoảng thời gian hoặc tạo summary table/materialized view nếu dashboard cần truy vấn thường xuyên.

## 13. Tính tỷ lệ MoM và xử lý số 0

Công thức:

\[
\text{MoM \%} =
\frac{current - previous}{previous} \times 100
\]

Các trường hợp:

| Previous | Current | Absolute change | Tỷ lệ thường dùng |
| ---: | ---: | ---: | --- |
| 100 | 120 | +20 | +20% |
| 100 | 80 | -20 | -20% |
| 100 | 0 | -100 | -100% |
| 0 | 50 | +50 | Không xác định |
| 0 | 0 | 0 | Không xác định theo công thức |
| NULL | 50 | NULL | Chưa có kỳ trước |

### 13.1. Không dùng NULLIF rồi quên ý nghĩa

```sql
(revenue - previous_revenue)
    / NULLIF(previous_revenue, 0)
```

`NULLIF` ngăn chia cho 0 bằng cách trả NULL nếu mẫu số bằng 0. Nhưng API/report vẫn phải diễn giải NULL:
- Tháng đầu tiên?
- Tháng trước không có doanh thu?
- Không có dữ liệu lịch sử?
- Không thể tính tỷ lệ?

Nên có thêm cột trạng thái:

```sql
CASE
    WHEN previous_month_revenue IS NULL THEN 'NO_PREVIOUS_MONTH'
    WHEN previous_month_revenue = 0 AND revenue = 0 THEN 'ZERO_TO_ZERO'
    WHEN previous_month_revenue = 0 THEN 'NEW_FROM_ZERO'
    ELSE 'COMPARABLE'
END AS comparison_status
```

Business có thể định nghĩa `ZERO_TO_ZERO` là 0% hoặc N/A. Đó là chính sách báo cáo, không phải quy tắc SQL bắt buộc.

### 13.2. Tăng trưởng khi tháng trước âm

Nếu metric có thể âm (ví dụ lợi nhuận), tỷ lệ phần trăm thông thường có thể khó diễn giải hoặc đổi dấu không trực quan. Cần xác định công thức business, có thể dùng chênh lệch tuyệt đối, tỷ lệ theo trị tuyệt đối hoặc báo riêng trạng thái chuyển lỗ/lãi. Không áp công thức doanh thu dương cho mọi metric.

### 13.3. Numeric precision

Dùng `NUMERIC`/`DECIMAL` cho tiền. Tránh chuyển doanh thu qua FLOAT/DOUBLE rồi làm tròn cuối cùng nếu nghiệp vụ cần exact decimal. Chọn scale cho phép phép nhân quantity × price và discount có độ chính xác đủ.

## 14. So sánh cùng tháng năm trước (YoY)

YoY so sánh tháng hiện tại với cùng tháng của năm trước:

\[
\text{YoY \%} =
\frac{\text{Current month} - \text{Same month previous year}}
{\text{Same month previous year}} \times 100
\]

Nếu calendar grid có đủ tháng liên tục, dùng:

```sql
LAG(revenue, 12) OVER (
    PARTITION BY product_id
    ORDER BY month_start
)
```

`12` là 12 hàng trước. Nó chỉ có nghĩa 12 tháng trước nếu grid có **mỗi tháng đúng một hàng**.

### 14.1. Không dùng LAG(12) trên dữ liệu tháng thưa

Nếu sản phẩm chỉ có giao dịch ở tháng 1, 2, 4 và 5, `LAG(revenue, 12)` đếm 12 hàng quan sát trước, không phải 12 tháng lịch trước. Tạo dense month grid trước.

### 14.2. Dùng self-join theo month offset

Có thể so theo tháng bằng cách JOIN tháng hiện tại với tháng trừ 12 tháng, đặc biệt khi dataset có grain rõ:

```sql
SELECT
    current.product_id,
    current.month_start,
    current.revenue AS current_revenue,
    previous.revenue AS previous_year_revenue
FROM monthly_sales AS current
LEFT JOIN monthly_sales AS previous
    ON previous.product_id = current.product_id
   AND previous.month_start =
       (current.month_start - INTERVAL '1 year')::date;
```

Đây là fragment giả định `monthly_sales` đã được định nghĩa và có một hàng mỗi product/month. Self-join cần unique grain và index/keys phù hợp.

## 15. Ranking theo tháng kết hợp MoM

Có thể kết hợp các bước:
1. Tạo monthly product revenue.
2. Tạo grid đầy đủ nếu cần.
3. Tính MoM bằng LAG.
4. Xếp hạng sản phẩm trong từng tháng bằng RANK/DENSE_RANK.
5. Lọc top-N ở query ngoài.

```sql
WITH months AS (
    SELECT g::date AS month_start
    FROM generate_series(
        DATE '2026-01-01',
        DATE '2026-04-01',
        INTERVAL '1 month'
    ) AS g
),
monthly_sales AS (
    SELECT
        product_id,
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
      AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY product_id, 2
),
grid AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        m.month_start,
        COALESCE(s.revenue, 0::numeric) AS revenue
    FROM demo_products AS p
    CROSS JOIN months AS m
    LEFT JOIN monthly_sales AS s
        ON s.product_id = p.product_id
       AND s.month_start = m.month_start
    WHERE p.active
),
metrics AS (
    SELECT
        *,
        LAG(revenue) OVER (
            PARTITION BY product_id
            ORDER BY month_start
        ) AS previous_revenue,
        SUM(revenue) OVER (
            PARTITION BY product_id
            ORDER BY month_start
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue
    FROM grid
),
ranked AS (
    SELECT
        *,
        DENSE_RANK() OVER (
            PARTITION BY month_start, category
            ORDER BY revenue DESC
        ) AS category_rank
    FROM metrics
)
SELECT
    product_id,
    product_name,
    category,
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS mom_change,
    cumulative_revenue,
    category_rank
FROM ranked
WHERE category_rank <= 3
ORDER BY month_start, category, category_rank, product_id;
```

Đây là một pipeline phân tích tổng hợp. Trong production, có thể cần tách CTE hoặc materialize summary để dễ tối ưu, nhưng logic grain vẫn phải được giữ rõ.

## 16. Filter trước hay sau window function?

Thứ tự logic của SQL rất quan trọng.

Ví dụ muốn ranking toàn bộ sản phẩm nhưng chỉ hiển thị top 3:
- Aggregate.
- Tính rank.
- Filter `rank <= 3` ở query ngoài.

Nếu lọc `WHERE revenue > 0` trước khi rank, sản phẩm doanh thu 0 không tham gia ranking. Điều đó có thể đúng hoặc sai theo contract.

### 16.1. WHERE lọc input trước window

```sql
SELECT
    product_id,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS rnk
FROM monthly_product_revenue
WHERE month_start = DATE '2026-04-01';
```

Window chỉ nhìn các hàng tháng 4.

### 16.2. Filter sau window

```sql
WITH ranked AS (
    SELECT
        product_id,
        revenue,
        RANK() OVER (ORDER BY revenue DESC) AS rnk
    FROM monthly_product_revenue
    WHERE month_start = DATE '2026-04-01'
)
SELECT *
FROM ranked
WHERE rnk <= 3;
```

Outer WHERE lọc kết quả đã có rank.

### 16.3. HAVING lọc nhóm trước window

```sql
SELECT
    product_id,
    SUM(quantity * unit_price) AS revenue,
    RANK() OVER (
        ORDER BY SUM(quantity * unit_price) DESC
    ) AS rnk
FROM demo_product_sales
WHERE status = 'COMPLETED'
GROUP BY product_id
HAVING SUM(quantity * unit_price) > 0;
```

`HAVING` lọc các nhóm sau aggregate và trước window stage. Sản phẩm có tổng 0 không tham gia ranking.

## 17. Tổng số lượng và doanh thu: hai ranking khác nhau

Một sản phẩm có thể bán nhiều chiếc nhưng doanh thu thấp; sản phẩm khác bán ít nhưng giá cao.

```sql
WITH product_metrics AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        COALESCE(SUM(
            CASE WHEN s.status = 'COMPLETED'
                 THEN s.quantity
                 ELSE 0
            END
        ), 0) AS units_sold,
        COALESCE(SUM(
            CASE WHEN s.status = 'COMPLETED'
                 THEN s.quantity * s.unit_price - s.discount_amount
                 ELSE 0
            END
        ), 0) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT
    *,
    DENSE_RANK() OVER (
        ORDER BY revenue DESC
    ) AS revenue_rank,
    DENSE_RANK() OVER (
        ORDER BY units_sold DESC
    ) AS units_rank
FROM product_metrics
ORDER BY revenue_rank, product_id;
```

Đừng dùng `COUNT(*)` để đếm số sản phẩm đã bán nếu bảng nguồn là sale lines và mỗi dòng có thể chứa nhiều units. `SUM(quantity)` mới là số lượng sản phẩm bán ra trong ví dụ.

## 18. Ranking theo tỷ trọng và phân bố

Ngoài rank, các hàm phân tích khác hữu ích:

### 18.1. Tỷ trọng doanh thu trong danh mục

```sql
WITH product_revenue AS (
    SELECT
        p.category,
        p.product_id,
        p.product_name,
        COALESCE(SUM(
            CASE WHEN s.status = 'COMPLETED'
                 THEN s.quantity * s.unit_price - s.discount_amount
                 ELSE 0
            END
        ), 0) AS revenue
    FROM demo_products AS p
    LEFT JOIN demo_product_sales AS s
        ON s.product_id = p.product_id
    GROUP BY p.category, p.product_id, p.product_name
)
SELECT
    *,
    SUM(revenue) OVER (
        PARTITION BY category
    ) AS category_revenue,
    CASE
        WHEN SUM(revenue) OVER (PARTITION BY category) = 0
            THEN NULL
        ELSE ROUND(
            100.0 * revenue
            / SUM(revenue) OVER (PARTITION BY category),
            2
        )
    END AS category_share_percent
FROM product_revenue
ORDER BY category, revenue DESC, product_id;
```

Tỷ trọng không nhất thiết cộng đúng 100.00 sau khi làm tròn từng dòng; sai số làm tròn là bình thường.

### 18.2. PERCENT_RANK và CUME_DIST

- `PERCENT_RANK()` biểu diễn vị trí tương đối theo rank, trong khoảng 0 đến 1; với partition chỉ một hàng, kết quả là 0.
- `CUME_DIST()` biểu diễn tỷ lệ hàng trong partition có giá trị sort nhỏ hơn hoặc bằng giá trị của hàng hiện tại theo ordering; kết quả lớn hơn 0 và không vượt 1.

Chúng hữu ích cho percentile/relative position, nhưng phải xác định chiều ORDER BY. Nếu revenue cao là tốt, `ORDER BY revenue DESC` đặt sản phẩm tốt ở đầu; ý nghĩa percentile sẽ phụ thuộc chiều này.

### 18.3. NTILE

```sql
NTILE(4) OVER (
    PARTITION BY category
    ORDER BY revenue DESC, product_id
)
```

Chia các hàng thành bốn bucket có số hàng gần bằng nhau. `NTILE(4)` không đảm bảo mỗi bucket có cùng tổng doanh thu hoặc cùng khoảng doanh thu. Đây là chia theo số lượng hàng, không phải equal-width numeric bins.

## 19. Moving average và rolling metrics

Moving average giúp làm mượt biến động theo thời gian:

```sql
AVG(revenue) OVER (
    ORDER BY month_start
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
) AS moving_avg_3_rows
```

Nếu muốn trung bình 3 tháng lịch, phải có đủ mỗi tháng trong input. Nếu thiếu tháng, ba hàng gần nhất có thể đại diện ba kỳ quan sát không liền nhau.

### 19.1. Rolling average có tính tháng hiện tại

`2 PRECEDING AND CURRENT ROW` gồm hai hàng trước và hàng hiện tại, tổng cộng tối đa ba hàng. Nếu chỉ có một hoặc hai hàng đầu kỳ, frame ngắn hơn ba hàng.

Nếu business muốn chỉ hiển thị rolling average khi đủ ba tháng, thêm:

```sql
COUNT(*) OVER (
    ORDER BY month_start
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
) = 3
```

hoặc kiểm `month_start` bắt đầu từ kỳ đủ dữ liệu.

### 19.2. Weighted average khác average của monthly average

Nếu mỗi tháng có số giao dịch khác nhau, trung bình các monthly average không bằng trung bình trên tất cả giao dịch. Xác định muốn:
- Trung bình theo tháng (mỗi tháng trọng số bằng nhau).
- Trung bình theo giao dịch (mỗi giao dịch trọng số bằng nhau).
- Trung bình theo số lượng bán (weighted by units).

Đừng dùng AVG của aggregate mà không xem trọng số.

## 20. So sánh theo tháng bằng self-join

`LAG` thường ngắn gọn khi cần kỳ trước trong một dãy đã sắp xếp. Self-join có ích khi:
- So với một kỳ cụ thể, ví dụ cùng tháng năm trước.
- Cần lấy nhiều thuộc tính từ kỳ so sánh.
- Dữ liệu thưa và muốn match chính xác period key.
- Cần so với kỳ có offset không cố định.

Ví dụ so tháng hiện tại với tháng trước sau khi đã có monthly summary:

```sql
WITH monthly_sales AS (
    SELECT
        product_id,
        date_trunc(
            'month',
            sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(quantity * unit_price - discount_amount) AS revenue
    FROM demo_product_sales
    WHERE status = 'COMPLETED'
    GROUP BY product_id, 2
)
SELECT
    current.product_id,
    current.month_start,
    current.revenue AS current_revenue,
    previous.revenue AS previous_revenue,
    current.revenue - previous.revenue AS revenue_change
FROM monthly_sales AS current
LEFT JOIN monthly_sales AS previous
    ON previous.product_id = current.product_id
   AND previous.month_start =
       (current.month_start - INTERVAL '1 month')::date
ORDER BY current.product_id, current.month_start;
```

Với dữ liệu thưa, tháng 4 không có row previous nếu tháng 3 vắng. Đây là so đúng month key, khác LAG trên tập hàng quan sát thưa (vốn lấy tháng trước có dữ liệu). Nếu muốn tháng không có giao dịch được coi là 0, COALESCE sau LEFT JOIN hoặc dùng dense grid.

## 21. Lũy kế theo sản phẩm và danh mục trong cùng query

Có thể tính nhiều window metrics trên cùng tập daily product revenue:

```sql
WITH daily_product AS (
    SELECT
        p.category,
        s.product_id,
        (s.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sale_day,
        SUM(s.quantity * s.unit_price - s.discount_amount) AS daily_revenue
    FROM demo_product_sales AS s
    JOIN demo_products AS p
        ON p.product_id = s.product_id
    WHERE s.status = 'COMPLETED'
    GROUP BY
        p.category,
        s.product_id,
        (s.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    category,
    product_id,
    sale_day,
    daily_revenue,
    SUM(daily_revenue) OVER (
        PARTITION BY product_id
        ORDER BY sale_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS product_running_total,
    SUM(daily_revenue) OVER (
        PARTITION BY category
        ORDER BY sale_day, product_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS category_running_total
FROM daily_product
ORDER BY category, sale_day, product_id;
```

Window `product_running_total` reset theo sản phẩm. Window `category_running_total` reset theo category và đi theo thứ tự ngày, product. Nếu nhiều sản phẩm có giao dịch cùng ngày, `product_id` làm tie-breaker cho một thứ tự tuần tự trong category. Nếu business muốn mọi giao dịch cùng ngày nhận cùng cumulative daily total, hãy aggregate lên category/day trước khi window.

## 22. Phân biệt lũy kế theo giao dịch và lũy kế theo ngày

Hai báo cáo có thể dùng cùng dữ liệu nhưng grain khác nhau.

**Theo giao dịch:** một hàng mỗi sale line, cumulative thay đổi sau mỗi sale. Cần tie-breaker duy nhất như sale_id.

**Theo ngày:** một hàng mỗi ngày, cumulative chỉ thay đổi một lần mỗi ngày. Cần aggregate sale lines thành daily totals trước.

Ví dụ giao dịch cùng ngày:
- 09:00: 100.
- 10:00: 200.

Theo giao dịch, cumulative là 100 rồi 300.
Theo ngày, daily revenue là 300 và cumulative cuối ngày tăng 300.

Nếu dashboard chỉ hiển thị theo ngày, tính cumulative trên sale lines rồi chọn một hàng cuối ngày có thể làm query phức tạp và dễ sai; aggregate daily trước sẽ rõ hơn.

## 23. Cửa sổ thời gian và timezone

Khi nhóm theo tháng, cần quyết định tháng thuộc timezone nào:
- UTC.
- Timezone của doanh nghiệp.
- Timezone địa phương của khách hàng.
- Timezone của chi nhánh.

Một giao dịch lúc `2026-03-31 17:30:00Z` có thể thuộc tháng 3 ở UTC nhưng tháng 4 ở một timezone phía Đông.

### 23.1. Lọc bằng khoảng nửa mở

Khuyến nghị:

```sql
WHERE sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND sold_at <  TIMESTAMPTZ '2026-02-01 00:00:00+07'
```

Tránh:

```sql
WHERE sold_at BETWEEN
    TIMESTAMPTZ '2026-01-01 00:00:00+07'
    AND TIMESTAMPTZ '2026-01-31 23:59:59+07'
```

`BETWEEN` bao gồm cả hai đầu; mốc cuối giây có thể bỏ sót dữ liệu có fractional seconds. Khoảng `[start, end)` dễ ghép các kỳ liên tiếp mà không overlap.

### 23.2. Không bọc cột trong WHERE nếu cần index range

Điều kiện:

```sql
WHERE date_trunc('month', sold_at) = DATE '2026-01-01'
```

có thể làm khó việc sử dụng index B-tree trên `sold_at` nếu không có expression index phù hợp. Thường dùng range predicate trên cột gốc:

```sql
WHERE sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND sold_at <  TIMESTAMPTZ '2026-02-01 00:00:00+07'
```

Sau khi lọc, dùng `date_trunc` trong SELECT/GROUP BY.

### 23.3. Daylight Saving Time

Một số timezone có DST, ngày địa phương có thể dài 23 hoặc 25 giờ. Tính mốc tháng/ngày theo timezone bằng thư viện/timezone database phù hợp; không giả định một ngày luôn đúng 24 giờ khi chuyển local boundaries thành instant.

## 24. Các lỗi logic hay gặp khi làm báo cáo

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Rank từng sale line thay vì tổng product | Sai grain | GROUP BY product trước |
| `PARTITION BY category` bị bỏ | Rank toàn hệ thống thay vì theo nhóm | Thêm partition đúng |
| Thêm product_id vào ORDER BY của RANK | Phá tie | Chỉ thêm tie-breaker cho ROW_NUMBER/final order |
| Lọc rank trong WHERE cùng query level | Alias/window chưa có ở WHERE | CTE/subquery |
| Lấy top 3 bằng LIMIT 3 toàn query | Chỉ top 3 toàn tập | ROW_NUMBER/RANK theo partition |
| Dùng RANK khi muốn đúng 3 dòng | Tie có thể trả hơn 3 | ROW_NUMBER |
| Dùng ROW_NUMBER khi phải giữ đồng hạng | Chọn tùy tiện một sản phẩm | RANK/DENSE_RANK |
| Lũy kế không có ORDER BY | Không có thứ tự tính rõ | ORDER BY |
| Lũy kế có ties nhưng thiếu tie-breaker | Thứ tự từng hàng không xác định | Thêm khóa unique hoặc aggregate peers |
| Dựa vào frame mặc định | RANGE peers có thể cùng tổng | Viết ROWS/RANGE tường minh |
| LAG trên tháng thưa | Lấy kỳ quan sát trước, không phải tháng lịch trước | Dense calendar hoặc self-join period key |
| Chia cho previous = 0 | Lỗi/undefined | NULLIF và status policy |
| COALESCE mọi NULL thành 0 | Mất khác biệt no-data và zero | Xác định ý nghĩa từng NULL |
| Cộng sale bị hủy | Doanh thu sai | Lọc status đúng |
| COUNT(*) trên LEFT JOIN | Đếm placeholder | COUNT(child key) |
| Group theo UTC trong khi business dùng local month | Giao dịch vào sai tháng | Chuyển timezone rõ |
| BETWEEN đến 23:59:59 | Bỏ fractional seconds | Khoảng nửa mở |
| Rolling 3 rows nhưng gọi 3 calendar months | Bỏ tháng không giao dịch | Dense calendar |
| Aggregate monthly average rồi AVG không trọng số | Sai metric | Weighted average theo grain |
| Window trên JOIN nhiều bảng detail | Row multiplication làm tổng sai | Aggregate mỗi nguồn trước |
| Lọc dữ liệu sau khi rank sai tầng | Thay đổi tập tham gia ranking | Phân biệt filter trước/sau window |
| Chỉ kiểm vài hàng đầu | Bỏ sót ties và zero-sales | Fixture biên và test toàn partition |

## 25. Index và hiệu năng

Window functions có thể yêu cầu sort theo `PARTITION BY` và `ORDER BY`. Index phù hợp đôi khi giúp giảm sort hoặc đọc dữ liệu có thứ tự, nhưng không đảm bảo optimizer dùng index cho mọi query.

### 25.1. Index theo thời gian và sản phẩm

```sql
CREATE INDEX idx_demo_sales_status_time_product
ON demo_product_sales (status, sold_at, product_id);
```

Hữu ích tiềm năng cho query lọc status và khoảng thời gian rồi nhóm theo product. Cột thứ tự index phải dựa vào workload; nếu filter status có selectivity thấp, index khác có thể tốt hơn.

### 25.2. Index theo product và thời gian

```sql
CREATE INDEX idx_demo_sales_product_time
ON demo_product_sales (product_id, sold_at);
```

Có thể hỗ trợ truy vấn theo sản phẩm và thời gian, ví dụ monthly series từng product. Không có một index tối ưu cho mọi cách lọc.

### 25.3. Partial index cho giao dịch hoàn tất

PostgreSQL:

```sql
CREATE INDEX idx_demo_sales_completed_time_product
ON demo_product_sales (sold_at, product_id)
WHERE status = 'COMPLETED';
```

Nếu phần lớn query chỉ quan tâm completed sales và tỷ lệ hàng completed phù hợp, partial index có thể nhỏ hơn index toàn bảng. Planner cần chứng minh predicate query phù hợp với điều kiện partial index.

### 25.4. EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    SUM(quantity * unit_price - discount_amount) AS revenue
FROM demo_product_sales
WHERE status = 'COMPLETED'
  AND sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
GROUP BY product_id
ORDER BY revenue DESC;
```

Quan sát:
- Actual rows và estimated rows.
- Scan type.
- Sort/HashAggregate.
- Buffers read/hit.
- Execution time.
- Temporary file/sort spill nếu có.

Bảng lab nhỏ có thể chọn Seq Scan dù đã tạo index. Điều đó không chứng minh index vô dụng trên dữ liệu production.

### 25.5. Window sort và memory

`ROW_NUMBER`, `RANK`, `LAG` và running SUM thường cần input được sắp theo partition/order. Tập dữ liệu lớn có thể cần sort hoặc spill ra disk. Giảm dữ liệu trước window khi contract cho phép, chọn range hợp lý và aggregate đúng grain.

Không lọc mất dữ liệu cần thiết chỉ để giảm sort rồi trả kết quả sai.

## 26. Khác biệt cú pháp giữa các hệ quản trị

Các window functions phổ biến đã được nhiều DBMS hỗ trợ, nhưng date generation, date truncation và interval syntax khác nhau.

| Nhu cầu | PostgreSQL | MySQL 8+ | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Row number | `ROW_NUMBER()` | `ROW_NUMBER()` | `ROW_NUMBER()` | `ROW_NUMBER()` | `ROW_NUMBER()` |
| Rank | `RANK()` | `RANK()` | `RANK()` | `RANK()` | `RANK()` |
| Dense rank | `DENSE_RANK()` | `DENSE_RANK()` | `DENSE_RANK()` | `DENSE_RANK()` | `DENSE_RANK()` |
| Previous value | `LAG()` | `LAG()` | `LAG()` | `LAG()` | `LAG()` |
| Running sum | `SUM() OVER(...)` | Có | Có | Có | Có |
| Month truncation | `date_trunc` | `DATE_FORMAT`/month expressions | `DATETRUNC` bản hỗ trợ hoặc `DATEFROMPARTS` | `TRUNC(date,'MM')` | `strftime` |
| Calendar series | `generate_series` | recursive CTE/calendar table | calendar table/recursive CTE | calendar table/CONNECT BY | recursive CTE |
| NULL sort control | `NULLS FIRST/LAST` | Expression/order rules | CASE expression | `NULLS FIRST/LAST` | Expression/order rules |

### 26.1. MySQL 8+

Window functions có từ MySQL 8.0. Ví dụ monthly key:

```sql
DATE_FORMAT(sold_at, '%Y-%m-01')
```

Có thể dùng để nhóm tháng, nhưng kiểu trả về là string; nếu cần date key, chuyển kiểu phù hợp. Tạo calendar series thường dùng recursive CTE hoặc calendar table.

### 26.2. SQL Server

Có `DATEFROMPARTS(YEAR(sold_at), MONTH(sold_at), 1)` để tạo month start trong các version hỗ trợ. `DATETRUNC(month, sold_at)` có ở phiên bản SQL Server mới hơn; kiểm version trước khi dùng. `LAG`, `ROW_NUMBER`, `RANK`, `SUM OVER` được hỗ trợ rộng.

### 26.3. Oracle

Có `TRUNC(sold_at, 'MM')` để lấy đầu tháng; calendar series có thể dùng calendar table hoặc `CONNECT BY LEVEL`. Window functions có cú pháp `OVER` và frame tương ứng. Kiểm type DATE/TIMESTAMP/TIMESTAMP WITH TIME ZONE.

### 26.4. SQLite

SQLite có window functions từ 3.25.0. Có thể nhóm tháng bằng `strftime('%Y-%m-01', sold_at)`, nhưng timezone/date storage phụ thuộc cách ứng dụng lưu dữ liệu. Không có `generate_series` mặc định trong mọi build; dùng recursive CTE hoặc calendar table.

### 26.5. Không copy nguyên SQL PostgreSQL sang dialect khác

Các phần cần chuyển:
- `TIMESTAMPTZ`.
- `AT TIME ZONE`.
- `date_trunc`.
- `generate_series`.
- `INTERVAL`.
- `FILTER (WHERE ...)`.
- `::date`, `::numeric`.
- `NULLS LAST`.

Giữ nguyên logic grain, partition, ranking và comparison semantics khi viết lại cú pháp.

## 27. Kiểm thử kết quả ranking và lũy kế

Một test tốt không chỉ kiểm vài giá trị đầu. Cần fixture bắt các trường hợp biên:

### 27.1. Ranking
- Hai sản phẩm cùng doanh thu.
- Ba sản phẩm đồng hạng ở ranh giới top N.
- Category chỉ có một sản phẩm.
- Category có nhiều sản phẩm doanh thu 0.
- Sản phẩm không có giao dịch.
- Giao dịch canceled.
- Doanh thu âm nếu có returns/refunds trong mô hình.

### 27.2. Cumulative
- Hai giao dịch cùng timestamp.
- Hai giao dịch cùng ngày.
- Sản phẩm bắt đầu bán giữa kỳ.
- Ngày không có giao dịch.
- Partition mới phải reset.
- Sale bị hủy phải không cộng vào tổng.
- Decimal có scale khác nhau.

### 27.3. MoM/YoY
- Tháng đầu không có previous period.
- Tháng trước bằng 0.
- Tháng hiện tại bằng 0.
- Tháng không có giao dịch.
- Thiếu tháng ở giữa.
- Tháng 1 so với tháng 12 năm trước.
- Timezone làm giao dịch gần ranh giới tháng đổi period.
- Thay đổi dữ liệu lịch sử sau khi báo cáo đã chạy.

### 27.4. Test bằng expected table

Có thể tạo expected summary nhỏ rồi so:
- Bag comparison nếu thứ tự không phải contract.
- Sequence comparison nếu ORDER BY được cam kết.
- Numeric comparison đúng precision.
- Từng partition/category/product.
- Số hàng và multiplicity.

Không dùng Set để so một kết quả có thể có duplicate hợp lệ.

## 28. Mẫu báo cáo tổng hợp hoàn chỉnh

Ví dụ báo cáo top sản phẩm theo tháng, có doanh thu, rank, cumulative và MoM. Đây là một mẫu đầy đủ trên dataset lab:

```sql
WITH months AS (
    SELECT g::date AS month_start
    FROM generate_series(
        DATE '2026-01-01',
        DATE '2026-04-01',
        INTERVAL '1 month'
    ) AS g
),
monthly_sales AS (
    SELECT
        s.product_id,
        date_trunc(
            'month',
            s.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(s.quantity * s.unit_price - s.discount_amount) AS revenue,
        SUM(s.quantity) AS units_sold
    FROM demo_product_sales AS s
    WHERE s.status = 'COMPLETED'
      AND s.sold_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
      AND s.sold_at <  TIMESTAMPTZ '2026-05-01 00:00:00+07'
    GROUP BY
        s.product_id,
        date_trunc(
            'month',
            s.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date
),
grid AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        m.month_start,
        COALESCE(ms.revenue, 0::numeric) AS revenue,
        COALESCE(ms.units_sold, 0::bigint) AS units_sold
    FROM demo_products AS p
    CROSS JOIN months AS m
    LEFT JOIN monthly_sales AS ms
        ON ms.product_id = p.product_id
       AND ms.month_start = m.month_start
    WHERE p.active = TRUE
),
metrics AS (
    SELECT
        *,
        LAG(revenue) OVER (
            PARTITION BY product_id
            ORDER BY month_start
        ) AS previous_revenue,
        SUM(revenue) OVER (
            PARTITION BY product_id
            ORDER BY month_start
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue,
        DENSE_RANK() OVER (
            PARTITION BY month_start, category
            ORDER BY revenue DESC
        ) AS category_rank
    FROM grid
)
SELECT
    product_id,
    product_name,
    category,
    month_start,
    revenue,
    units_sold,
    previous_revenue,
    revenue - previous_revenue AS mom_change,
    CASE
        WHEN previous_revenue IS NULL THEN NULL
        WHEN previous_revenue = 0 THEN NULL
        ELSE ROUND(
            100.0 * (revenue - previous_revenue) / previous_revenue,
            2
        )
    END AS mom_percent,
    cumulative_revenue,
    category_rank
FROM metrics
WHERE category_rank <= 3
ORDER BY month_start, category, category_rank, product_id;
```

### 28.1. Cách đọc pipeline

1. `months`: tạo các kỳ lịch cần báo cáo.
2. `monthly_sales`: tổng hợp giao dịch về một hàng product/month.
3. `grid`: tạo đủ product × month và gán doanh thu 0 khi không có sale.
4. `metrics`: tính previous month, cumulative và rank.
5. Query cuối: lọc top 3 rank và trình bày.

### 28.2. Điều chỉnh theo yêu cầu thực tế

- Nếu chỉ xếp hạng sản phẩm có giao dịch, bỏ grid hoặc thêm điều kiện.
- Nếu muốn đúng tối đa ba dòng, dùng `ROW_NUMBER`.
- Nếu muốn top ba mức doanh thu, dùng `DENSE_RANK`.
- Nếu muốn top ba vị trí có đồng hạng, dùng `RANK`.
- Nếu doanh thu có thể âm, xem lại ranking và phần trăm MoM.
- Nếu cần YoY, thêm `LAG(revenue, 12)` trên grid có đủ 12 tháng trước.
- Nếu có nhiều tenant, thêm tenant vào keys, GROUP BY, JOIN và PARTITION BY để không trộn dữ liệu.

## 29. Bài tập thực hành

Các bài PostgreSQL dùng `demo_products` và `demo_product_sales` trong cùng session tạo bảng. Với những bài cần tie, NULL hoặc tháng thiếu, hãy thêm fixture riêng mà không thay đổi dữ liệu gốc của bài trước.

### Bài 1 — Grain
Bảng sales có một hàng mỗi sale line. Viết query aggregate doanh thu theo product. Giải thích vì sao rank trực tiếp sale lines không trả thứ hạng sản phẩm.

### Bài 2 — Revenue
Tính revenue = quantity × unit_price − discount cho giao dịch COMPLETED. Loại CANCELED. Kiểm tra sản phẩm không có sale vẫn có doanh thu 0.

### Bài 3 — ROW_NUMBER
Xếp hạng sản phẩm toàn hệ thống theo revenue giảm dần, product_id tăng dần. Vì sao cần tie-breaker?

### Bài 4 — RANK
Tạo hai sản phẩm cùng revenue. Dùng RANK và giải thích khoảng nhảy hạng.

### Bài 5 — DENSE_RANK
Dùng DENSE_RANK cho cùng fixture. So sánh rank của hàng đứng sau nhóm đồng hạng.

### Bài 6 — Ranking theo category
Dùng PARTITION BY category. Xác nhận rank reset ở Electronics, Furniture và Stationery.

### Bài 7 — Top 3 đúng ba hàng
Dùng ROW_NUMBER để lấy tối đa ba sản phẩm mỗi category. Tạo tie ở vị trí thứ ba và xác định tie-breaker.

### Bài 8 — Top 3 rank
Dùng RANK <= 3. Tạo nhiều sản phẩm đồng hạng ở ranh giới. Đếm số hàng trả về.

### Bài 9 — Top 3 mức doanh thu
Dùng DENSE_RANK <= 3. So sánh với top 3 dòng và top 3 rank.

### Bài 10 — Ranking theo tháng
Aggregate theo product/month rồi rank trong từng month/category. Kiểm tra sản phẩm không bán trong tháng có xuất hiện không.

### Bài 11 — Lũy kế toàn hệ thống
Tính cumulative revenue theo sold_at, sale_id. Dùng ROWS frame rõ ràng.

### Bài 12 — Lũy kế theo sản phẩm
PARTITION BY product_id. Xác nhận tổng reset khi chuyển sang sản phẩm khác.

### Bài 13 — Lũy kế theo category
JOIN products, PARTITION BY category. Chọn tie-breaker khi nhiều sản phẩm bán cùng thời điểm.

### Bài 14 — ROWS và RANGE
Tạo hai sale rows cùng sold_at. So sánh cumulative với ROWS và RANGE. Vì sao peers có thể nhận cùng tổng trong RANGE?

### Bài 15 — Daily aggregate
Aggregate nhiều sale lines thành daily revenue rồi tính running total. So với cumulative theo từng sale line.

### Bài 16 — Calendar day
Tạo series từ 1/1 đến 30/4. LEFT JOIN daily totals, gán 0 cho ngày không bán. Tính cumulative mỗi ngày.

### Bài 17 — Monthly aggregate
Tính doanh thu toàn hệ thống theo tháng. Dùng khoảng thời gian nửa mở.

### Bài 18 — Lũy kế theo tháng
Dùng SUM OVER trên monthly summary. Kiểm cumulative tăng qua từng tháng.

### Bài 19 — Rolling 3 rows
Tính rolling sum 3 hàng. Bỏ một tháng khỏi dataset và quan sát vì sao không còn là 3 calendar months.

### Bài 20 — Dense monthly grid
Tạo product × month grid. Tính rolling 3 calendar months bằng ROWS 2 PRECEDING.

### Bài 21 — MoM bằng LAG
Tính revenue, previous revenue, absolute change và phần trăm. Xử lý tháng đầu tiên.

### Bài 22 — Tháng thiếu
Sản phẩm 3 không có giao dịch tháng 3. Chạy LAG trên monthly rows thưa và trên dense grid. So sánh previous month được chọn.

### Bài 23 — Zero denominator
Tạo một sản phẩm có doanh thu tháng trước 0 và tháng hiện tại 100. Thiết kế comparison_status và mom_percent.

### Bài 24 — YoY
Tạo 24 tháng dữ liệu và dense calendar. Dùng LAG(12). Vì sao LAG(12) trên dữ liệu thưa không chắc là cùng tháng năm trước?

### Bài 25 — Ranking + MoM
Kết hợp dense grid, LAG và DENSE_RANK. Lấy top 3 mức doanh thu mỗi category/month.

### Bài 26 — Tỷ trọng
Tính revenue share của từng sản phẩm trong category. Xử lý category total bằng 0.

### Bài 27 — NTILE
Chia sản phẩm thành 4 bucket trong mỗi category. Vì sao mỗi bucket có số hàng gần bằng nhau nhưng tổng revenue không nhất thiết bằng nhau?

### Bài 28 — Timezone
Tạo sale gần nửa đêm UTC và chuyển sang timezone nghiệp vụ. Kiểm tra sale được nhóm vào tháng/ngày nào. So sánh với lọc UTC.

### Bài 29 — Execution plan
Tạo index theo status/time/product. Chạy EXPLAIN ANALYZE cho monthly aggregate và ranking. Xem sort, aggregate, buffers và actual rows.

### Bài 30 — Báo cáo tổng hợp
Xây báo cáo product/month gồm revenue, units, rank trong category, cumulative revenue, MoM change và status. Test tie, tháng thiếu, sản phẩm không bán, sale canceled, tenant scope, timezone và tháng đầu tiên.

## 30. Checklist trước khi phát hành báo cáo

### Grain và dữ liệu
- [ ] Mỗi bước query có grain rõ ràng?
- [ ] Đã aggregate trước khi rank/running total?
- [ ] Sale status, discount, returns và quy tắc revenue đúng?
- [ ] Sản phẩm không có giao dịch được xử lý có chủ ý?
- [ ] JOIN không nhân bản sale rows?

### Ranking
- [ ] Ranking toàn hệ thống hay theo partition?
- [ ] ROW_NUMBER/RANK/DENSE_RANK phù hợp định nghĩa top-N?
- [ ] Tie có được giữ đúng?
- [ ] ROW_NUMBER/final output có tie-breaker ổn định?
- [ ] Filter rank đặt ở query level bên ngoài?

### Lũy kế
- [ ] PARTITION BY đúng phạm vi reset?
- [ ] ORDER BY phản ánh thứ tự nghiệp vụ?
- [ ] Frame ROWS/RANGE/GROUPS được chọn rõ?
- [ ] Cùng timestamp được xử lý đúng?
- [ ] Grain là sale, ngày hay tháng?
- [ ] Rolling period có đủ calendar rows?

### So sánh tháng
- [ ] Calendar month được tạo nếu cần previous calendar month?
- [ ] Tháng không có giao dịch là 0 hay NULL theo contract?
- [ ] Tháng đầu tiên được đánh dấu đúng?
- [ ] Mẫu số 0 được xử lý?
- [ ] MoM/YoY dùng đúng period?
- [ ] Timezone và khoảng `[start, end)` chính xác?
- [ ] Decimal precision và rounding đúng?

### Hiệu năng và kiểm thử
- [ ] Range filter có thể tận dụng index?
- [ ] Window sort và aggregate có spill không?
- [ ] Grid product × month có kích thước kiểm soát?
- [ ] Fixture có ties, tháng thiếu, zero và canceled?
- [ ] Kết quả được so theo đúng set/bag/order semantics?
- [ ] EXPLAIN/ANALYZE và workload thực tế đã được xem?

## 31. Sơ đồ tổng hợp

```text
                  DỮ LIỆU GIAO DỊCH
                          |
                          v
             Lọc status + khoảng thời gian
                          |
                          v
                 Xác định grain cần tính
                    /           \
               Product         Day/Month
                  |                |
                  v                v
             SUM revenue      SUM revenue
                  |                |
                  v                v
           RANK / DENSE_RANK   SUM OVER
                  |                |
                  v                v
              Top-N          Running/Rolling
                                   |
                                   v
                         Calendar đầy đủ?
                           /          \
                         Có            Không
                         |               |
                         v               v
                     LAG MoM/YoY   Previous observed row
                         |
                         v
                 Xử lý NULL / zero
                         |
                         v
             Output + ORDER BY + tie-breaker
                         |
                         v
                  Test + EXPLAIN
```

## 32. Tổng kết

Xếp hạng, tính lũy kế và so sánh theo tháng đều dựa trên việc xác định đúng tập hàng và thứ tự của nó. Để xếp hạng sản phẩm, hãy aggregate doanh thu về một hàng mỗi sản phẩm trước; dùng `ROW_NUMBER` khi cần đúng N dòng, `RANK` khi muốn giữ đồng hạng theo vị trí, và `DENSE_RANK` khi muốn top N mức giá trị khác nhau. `PARTITION BY` xác định nơi rank hoặc cumulative reset.

Running total cần `ORDER BY` và window frame rõ ràng. `ROWS` tính theo hàng trong thứ tự, còn `RANGE` xử lý các peer có cùng sort value theo nhóm; khi cần số dư tuần tự, thêm tie-breaker và dùng ROWS frame tường minh. Muốn rolling ba tháng lịch, phải có một hàng cho mọi tháng, kể cả tháng không phát sinh giao dịch.

MoM dùng `LAG`, nhưng LAG chỉ lấy hàng trước trong tập input. Nếu tháng bị thiếu, previous observed month có thể khác previous calendar month. Tạo month series, ghép với sản phẩm và gán 0 hay NULL theo contract trước khi tính LAG. Khi tính phần trăm, xử lý tháng đầu và mẫu số 0 rõ ràng; giữ tiền ở kiểu decimal và xác định timezone của ranh giới kỳ.

Một báo cáo đáng tin cậy luôn thể hiện rõ grain, filter, partition, sort, tie policy, calendar semantics và quy tắc NULL/zero. Sau đó mới tối ưu bằng index, summary hoặc materialization và kiểm bằng fixture có ties, tháng thiếu, sản phẩm không bán và giao dịch bị hủy. Khi các quyết định ấy được viết rõ trong SQL, kết quả ranking, cumulative và monthly comparison sẽ nhất quán, dễ giải thích và có thể kiểm thử khi dữ liệu tăng lên.
