# LATERAL derived table và điều kiện phiên bản hỗ trợ

Một derived table là truy vấn con nằm trong mệnh đề FROM. Dù optimizer có thể merge hoặc materialize derived table tùy truy vấn, derived table thông thường không có phạm vi tham chiếu trực tiếp đến bảng ngang hàng trong cùng FROM. Từ MySQL 8.0.14, từ khóa LATERAL cho phép derived table tham chiếu các bảng xuất hiện trước nó trong cùng query block.

Khả năng này hữu ích khi mỗi hàng cha cần một truy vấn con riêng, chẳng hạn lấy ba đơn hàng mới nhất của từng khách hàng, tính các chỉ số từ những hàng liên quan hoặc thực hiện phép tính dựa trên cột của hàng hiện tại. LATERAL thể hiện rõ mối quan hệ tương quan giữa bảng ngoài và truy vấn con.

Trong module DATABASE_MYSQL, LATERAL kết nối kiến thức JOIN, derived table, truy vấn tương quan, index và execution plan. Bài học này trình bày điều kiện phiên bản, phạm vi tham chiếu, cú pháp JOIN, các tình huống sử dụng, cách thay thế và những điểm cần đo trước khi đưa vào hệ thống thực tế.

## 1. Derived table thông thường và giới hạn tham chiếu

Derived table là một truy vấn SELECT được đặt trong FROM, sau đó được đặt bí danh như một bảng trong phạm vi câu truy vấn.

Ví dụ, tổng tiền đơn hàng theo khách hàng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    totals.order_count,
    totals.total_amount
FROM customers AS c
JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS totals
  ON totals.customer_id = c.customer_id;
```

Derived table totals tự tổng hợp toàn bộ bảng orders theo customer_id. Nó không tham chiếu trực tiếp c.customer_id ở truy vấn bên ngoài.

Nếu cố viết điều kiện tương quan bên trong derived table:

```sql
SELECT
    c.customer_id,
    recent.order_id
FROM customers AS c
JOIN (
    SELECT order_id
    FROM orders
    WHERE orders.customer_id = c.customer_id
    ORDER BY created_at DESC
    LIMIT 3
) AS recent;
```

MySQL báo lỗi vì alias c thuộc query block bên ngoài không nằm trong phạm vi tham chiếu của derived table thông thường. Đây là điểm khác biệt mà LATERAL giải quyết.

## 2. Phiên bản MySQL hỗ trợ LATERAL

MySQL hỗ trợ lateral derived table từ **MySQL 8.0.14**.

| Phiên bản | LATERAL derived table |
|---|---|
| MySQL 5.7 | Không hỗ trợ |
| MySQL 8.0.11–8.0.13 | Chưa hỗ trợ |
| MySQL 8.0.14 trở lên | Hỗ trợ |
| MySQL 8.4 | Hỗ trợ |

MySQL 8.0.14 là mốc bổ sung khả năng này. Nếu ứng dụng chạy MySQL 5.7 hoặc MySQL 8.0.13 trở xuống, câu truy vấn có từ khóa LATERAL sẽ không chạy theo cú pháp này. Cần chọn cách viết tương thích với phiên bản cũ hoặc nâng cấp server theo kế hoạch.

Kiểm tra phiên bản và bản phân phối:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution;
```

Đừng suy ra khả năng hỗ trợ chỉ từ phiên bản JDBC hoặc ORM. Cần kiểm tra server đích, vì câu SQL cuối cùng được thực thi bởi database server. Với MariaDB hoặc dịch vụ tương thích MySQL, hãy kiểm tra tài liệu của đúng sản phẩm và phiên bản; không mặc định cú pháp, optimizer hoặc thời điểm hỗ trợ giống MySQL.

## 3. Cú pháp LATERAL derived table

Mẫu cơ bản:

```sql
SELECT ...
FROM parent_table AS p
JOIN LATERAL (
    SELECT ...
    FROM child_table AS c
    WHERE c.parent_id = p.parent_id
) AS related ON TRUE;
```

Các thành phần:

- LATERAL đặt ngay trước derived table trong dấu ngoặc.
- Derived table có thể tham chiếu cột từ bảng đứng trước nó trong cùng FROM.
- Derived table cần bí danh, ví dụ related.
- ON TRUE thường được dùng khi toàn bộ điều kiện tương quan đã nằm trong truy vấn con.
- Dùng JOIN LATERAL hoặc CROSS JOIN LATERAL để chỉ giữ hàng cha có kết quả phù hợp; dùng LEFT JOIN LATERAL để giữ cả hàng cha không có kết quả.

LATERAL không phải một loại JOIN độc lập. Nó cho phép derived table có tham chiếu tương quan; cách ghép hàng vẫn do INNER, CROSS hoặc LEFT JOIN quyết định.

## 4. Phạm vi tham chiếu và thứ tự bảng

Một lateral derived table có thể tham chiếu bảng đứng trước nó trong danh sách FROM hoặc ở phía trái của phép JOIN tương ứng. Vì vậy, hãy đặt bảng cung cấp giá trị tương quan trước derived table:

```sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE;
```

Ở đây, recent tham chiếu c.customer_id, vì customers AS c xuất hiện trước lateral derived table.

Không thể tham chiếu một bảng xuất hiện phía sau như thể bảng đó đã có trong phạm vi:

```sql
-- Minh họa sai phạm vi tham chiếu
SELECT ...
FROM LATERAL (
    SELECT ...
    WHERE child.parent_id = p.parent_id
) AS x
JOIN parent_table AS p ON TRUE;
```

Alias p chưa xuất hiện khi derived table được khai báo. Cần sắp xếp lại thứ tự FROM để bảng được tham chiếu đứng trước.

Trong các truy vấn thông thường, ưu tiên đặt lateral derived table ở phía phải của INNER JOIN, CROSS JOIN hoặc LEFT JOIN mà nó phụ thuộc. MySQL có quy tắc phạm vi tham chiếu riêng khi dùng RIGHT JOIN; nếu cần cấu trúc này, hãy kiểm tra đúng quy tắc của phiên bản đang chạy. Có thể viết lại theo thứ tự JOIN trái sang phải để truy vấn dễ đọc hơn.

## 5. Ví dụ chính: lấy N đơn hàng mới nhất của từng khách hàng

Giả sử có hai bảng:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB;
```

Yêu cầu: lấy tối đa ba đơn hàng mới nhất của mỗi khách hàng.

```sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id,
    recent.created_at,
    recent.total_amount
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at,
        o.total_amount
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.created_at DESC,
    recent.order_id DESC;
```

Đối với từng hàng customers, truy vấn con tìm các đơn hàng có cùng customer_id, sắp xếp mới nhất trước và trả tối đa ba hàng. Nhờ đó, LIMIT 3 được áp dụng riêng cho mỗi khách hàng.

LEFT JOIN bảo toàn khách hàng không có đơn hàng. Với khách hàng không có đơn phù hợp, các cột của recent sẽ là NULL. Nếu dùng JOIN LATERAL hoặc CROSS JOIN LATERAL, khách hàng không có đơn hàng phù hợp sẽ bị loại khỏi kết quả.

### 5.1. Vì sao cần ORDER BY ổn định?

Chỉ sắp xếp theo created_at DESC có thể chưa đủ nếu nhiều đơn hàng có cùng timestamp. Thêm order_id DESC làm tiêu chí phụ để thứ tự xác định hơn.

Nếu bỏ ORDER BY, MySQL không có nghĩa vụ chọn những hàng mới nhất. Nếu bỏ ORDER BY ở truy vấn ngoài, kết quả cuối cũng không được bảo đảm có thứ tự hiển thị, dù truy vấn con đã dùng thứ tự để chọn top 3.

### 5.2. Thêm điều kiện trong truy vấn con

Có thể lọc chỉ các đơn đã thanh toán:

```sql
SELECT
    c.customer_id,
    c.full_name,
    paid.order_id,
    paid.created_at,
    paid.total_amount
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at,
        o.total_amount
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS paid ON TRUE
ORDER BY c.customer_id, paid.created_at DESC, paid.order_id DESC;
```

Điều kiện status = 'PAID' được áp dụng trước khi ORDER BY và LIMIT, vì vậy kết quả là ba đơn đã thanh toán mới nhất của từng khách hàng, không phải lấy ba đơn gần nhất rồi mới lọc PAID.

## 6. LEFT JOIN LATERAL và xử lý hàng cha không có kết quả

So sánh hai cách:

```sql
-- Chỉ giữ khách hàng có ít nhất một đơn hàng
SELECT c.customer_id, x.order_id
FROM customers AS c
JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 1
) AS x ON TRUE;

-- Giữ mọi khách hàng, kể cả khi không có đơn hàng
SELECT c.customer_id, x.order_id
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 1
) AS x ON TRUE;
```

Ở truy vấn thứ hai, khách hàng không có đơn vẫn xuất hiện với x.order_id IS NULL. Nếu muốn đặt thêm điều kiện trên kết quả lateral, cần cân nhắc đặt điều kiện ở trong truy vấn con hay ở ON.

Ví dụ, nếu đưa x.total_amount > 0 vào WHERE bên ngoài, hàng được NULL-extend sẽ bị loại, khiến LEFT JOIN có hiệu quả giống inner join đối với điều kiện đó. Nếu muốn giữ khách hàng không có kết quả, hãy lọc bên trong lateral derived table hoặc đặt điều kiện thích hợp trong ON.

## 7. Dùng LATERAL để tính nhiều chỉ số liên quan cho mỗi hàng cha

Một correlated scalar subquery phù hợp khi chỉ cần một giá trị. Nếu cần nhiều kết quả tính từ cùng tập hàng con, lateral derived table có thể trả nhiều cột trong một lần khai báo.

Ví dụ tính số đơn hàng và tổng giá trị đơn của từng khách hàng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    stats.order_count,
    stats.total_amount,
    stats.last_order_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS order_count,
        SUM(o.total_amount) AS total_amount,
        MAX(o.created_at) AS last_order_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) AS stats ON TRUE;
```

Truy vấn con là aggregate không có GROUP BY, vì vậy nó trả về một hàng tổng hợp ngay cả khi không có đơn hàng. Khi không có hàng con, COUNT(*) trả 0, còn SUM() và MAX() trả NULL.

Có thể dùng COALESCE(stats.total_amount, 0) nếu nghiệp vụ muốn hiển thị tổng bằng 0. Chỉ chuyển NULL thành 0 khi hai giá trị đó có cùng ý nghĩa trong báo cáo.

Đừng mặc định gom tất cả phép tính vào một lateral subquery sẽ luôn nhanh hơn. Optimizer, index, số hàng cha và số hàng con quyết định chi phí. Hãy so sánh với một derived table tổng hợp toàn bảng nếu truy vấn cần thống kê cho hầu hết khách hàng.

## 8. LATERAL cho phép tính phụ thuộc vào từng hàng

Một tình huống khác là tính giá trị dẫn xuất từ nhiều cột của hàng hiện tại rồi dùng kết quả đó trong câu truy vấn:

```sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price,
    pricing.discount_rate,
    p.unit_price * (1 - pricing.discount_rate) AS final_price
FROM products AS p
CROSS JOIN LATERAL (
    SELECT
        CASE
            WHEN p.unit_price >= 1000 THEN 0.15
            WHEN p.unit_price >= 500 THEN 0.10
            ELSE 0.05
        END AS discount_rate
) AS pricing;
```

Ví dụ minh họa cách biểu diễn một tập phép tính phụ thuộc hàng ngoài. Với biểu thức đơn giản, có thể viết trực tiếp trong SELECT; LATERAL hữu ích hơn khi phần tính toán có nhiều biểu thức, cần tổ chức thành một đơn vị dễ đọc hoặc kết hợp với truy vấn con thực sự lấy dữ liệu liên quan.

Không dùng lateral chỉ để bọc một phép cộng đơn giản. Cấu trúc truy vấn cần làm rõ quan hệ phụ thuộc hoặc giúp tái sử dụng các kết quả trung gian.

## 9. So sánh LATERAL với scalar subquery, EXISTS và derived table

| Nhu cầu | Cấu trúc thường phù hợp | Đặc điểm |
|---|---|---|
| Lấy một giá trị từ bảng con | Scalar correlated subquery | Trả về một giá trị; cần xử lý trường hợp nhiều hàng |
| Kiểm tra có hàng liên quan | EXISTS | Trả boolean, không cần lấy cột bảng con |
| Tổng hợp dữ liệu cho toàn bộ nhóm | Derived table + GROUP BY | Có thể tổng hợp toàn bộ bảng con một lần |
| Lấy nhiều hàng liên quan cho mỗi hàng cha | LATERAL derived table | Truy vấn con được tham chiếu dữ liệu hàng cha |
| Lấy top N hàng mỗi nhóm | LATERAL + ORDER BY/LIMIT hoặc window function | Chọn N hàng cho từng nhóm |
| Chọn hạng theo partition | ROW_NUMBER/RANK/DENSE_RANK | Phân hạng trên tập dữ liệu đã truy vấn |

### 9.1. LATERAL và scalar correlated subquery

Ví dụ lấy thời gian đơn hàng mới nhất:

```sql
SELECT
    c.customer_id,
    c.full_name,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS last_order_at
FROM customers AS c;
```

Scalar subquery phù hợp vì chỉ trả một giá trị. Nếu cần đồng thời order_id, created_at, total_amount của cùng đơn hàng mới nhất, có thể dùng lateral query với ORDER BY ... LIMIT 1 để lấy các cột từ cùng một hàng.

### 9.2. LATERAL và EXISTS

Nếu chỉ cần biết khách hàng có đơn PAID hay không, không cần trả dữ liệu từng đơn hàng:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

EXISTS thể hiện trực tiếp mục tiêu kiểm tra sự tồn tại và thường là lựa chọn đơn giản nhất. LATERAL phù hợp khi cần lấy các cột hoặc nhiều hàng từ truy vấn con.

### 9.3. LATERAL và window function

MySQL 8.0 hỗ trợ window function. Có thể giải bài toán top N theo nhóm bằng ROW_NUMBER():

```sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM orders AS o
)
SELECT
    c.customer_id,
    c.full_name,
    r.order_id,
    r.created_at,
    r.total_amount
FROM customers AS c
LEFT JOIN ranked_orders AS r
  ON r.customer_id = c.customer_id
 AND r.rn <= 3
ORDER BY c.customer_id, r.created_at DESC, r.order_id DESC;
```

Hai cách có thể trả cùng kết quả nhưng kế hoạch thực thi khác nhau:

- LATERAL có thể thực hiện một lần tìm kiếm giới hạn theo từng khách hàng, hữu ích khi tập khách hàng nhỏ và index hỗ trợ tốt.
- Window function có thể xếp hạng một tập lớn đơn hàng rồi nối với khách hàng; phù hợp khi cần xử lý phần lớn hoặc toàn bộ bảng.
- Cần đo trên dữ liệu thực tế để chọn cách tốt hơn. Không có quy tắc rằng LATERAL luôn nhanh hơn window function hoặc ngược lại.

### 9.4. Cách thay thế trên MySQL 5.7

MySQL 5.7 không có LATERAL và cũng chưa có window function. Với yêu cầu lấy đúng một hàng mới nhất cho mỗi khách hàng, có thể dùng scalar correlated subquery để chọn khóa của hàng đó rồi JOIN lại:

[[FENCE]]sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
LEFT JOIN orders AS o
  ON o.order_id = (
      SELECT o2.order_id
      FROM orders AS o2
      WHERE o2.customer_id = c.customer_id
      ORDER BY o2.created_at DESC, o2.order_id DESC
      LIMIT 1
  );
[[FENCE]]

Subquery chỉ trả một order_id cho mỗi khách hàng; JOIN bên ngoài lấy các cột còn lại từ đúng hàng đó. Với top N lớn hơn 1, MySQL 5.7 cần một cách viết khác, chẳng hạn truy vấn tương quan đếm số hàng đứng trước hoặc xử lý thứ hạng ở tầng ứng dụng. Các cách này có thể tốn kém trên bảng lớn; hãy cân nhắc nâng cấp lên MySQL 8.0 để dùng LATERAL hoặc window function, và đo kế hoạch trên dữ liệu thực tế.

## 10. Index và tối ưu truy vấn LATERAL

LATERAL không tự làm truy vấn nhanh. Vì truy vấn con thường phụ thuộc vào từng hàng cha, index trên cột liên kết và thứ tự sắp xếp có thể quyết định phần lớn chi phí.

Với truy vấn lấy ba đơn mới nhất cho mỗi khách hàng:

```sql
CREATE INDEX idx_orders_customer_recent
    ON orders (customer_id, created_at DESC, order_id DESC);
```

Index bắt đầu bằng customer_id để tìm vùng đơn hàng của một khách hàng, sau đó hỗ trợ thứ tự created_at DESC, order_id DESC. MySQL 8.0 hỗ trợ descending index. Nếu chỉ có index (customer_id), server vẫn có thể cần sắp xếp các đơn của mỗi khách hàng.

Các nguyên tắc:

1. Đặt cột liên kết bằng (customer_id) ở đầu index.
2. Thêm các cột phục vụ ORDER BY tiếp theo.
3. Nếu có điều kiện lọc như status = 'PAID', đánh giá index ghép có thêm status hay không dựa trên selectivity và thứ tự truy cập.
4. Chỉ đưa thêm cột trả về vào index nếu lợi ích covering đáng kể và chi phí lưu trữ/ghi chấp nhận được.
5. Tránh tạo nhiều index gần giống nhau khi một index ghép có thể đáp ứng các truy vấn chính.

Ví dụ index có status:

```sql
CREATE INDEX idx_orders_customer_status_recent
    ON orders (
        customer_id,
        status,
        created_at DESC,
        order_id DESC
    );
```

Index này có thể hỗ trợ điều kiện equality trên customer_id và status, sau đó đọc theo thứ tự thời gian. Nhưng nó không tương đương với index trước cho truy vấn không lọc status, vì cột status nằm giữa các cột. Kiểm tra workload trước khi chọn một trong hai.

## 11. Đọc execution plan và đánh giá chi phí

Bắt đầu với EXPLAIN:

```sql
EXPLAIN
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE;
```

Quan sát:

- Bảng ngoài customers được đọc theo access path nào.
- Truy vấn con có dùng index bắt đầu bằng customer_id không.
- Ước lượng số hàng đọc từ orders cho mỗi giá trị liên kết.
- Có bước filesort hay temporary table hay không.
- Có dấu hiệu rematerialize lateral derived table cho từng hàng ngoài hay không; dạng hiển thị phụ thuộc phiên bản và định dạng EXPLAIN.

Trên phiên bản hỗ trợ, EXPLAIN ANALYZE thực thi câu SELECT và cung cấp thời gian cùng số hàng thực tế:

```sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    recent.order_id
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE;
```

EXPLAIN ANALYZE chạy truy vấn thật. Chỉ dùng với câu SELECT an toàn, tập dữ liệu phù hợp và tải đã được cân nhắc.

### 11.1. Ước lượng số lần chạy truy vấn con

Nếu truy vấn ngoài trả về 50.000 khách hàng, truy vấn con có thể cần được đánh giá cho rất nhiều hàng cha. Ngược lại, nếu truy vấn ngoài lọc còn 20 khách hàng và index cho phép lấy ba đơn nhanh chóng cho mỗi người, LATERAL có thể rất hiệu quả.

Vì vậy, hãy lọc tập hàng cha càng sớm càng tốt nếu điều kiện lọc không làm thay đổi ngữ nghĩa:

```sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE
WHERE c.created_at >= '2026-01-01'
  AND c.status = 'ACTIVE';
```

Nếu có index phù hợp trên bảng customers, MySQL có thể giảm số hàng ngoài trước khi thực hiện phần truy vấn tương quan.

## 12. Các giới hạn và điểm cần lưu ý

- **Phiên bản:** LATERAL derived table cần MySQL 8.0.14 trở lên.
- **Thứ tự tham chiếu:** đặt bảng được tham chiếu trước lateral derived table trong FROM.
- **Bí danh:** derived table cần alias.
- **Số hàng trả về:** một hàng cha có thể tạo nhiều hàng kết quả nếu lateral subquery trả nhiều hàng.
- **LEFT JOIN:** giữ hàng cha không có kết quả; các cột derived table được NULL-extend.
- **ORDER BY:** dùng trong subquery để xác định top N; dùng ORDER BY ngoài để xác định thứ tự cuối cùng.
- **Hiệu năng:** lateral query có thể phải thực hiện nhiều lần theo số hàng cha; cần index và đo execution plan.
- **NULL:** điều kiện tương quan với giá trị NULL thường không khớp bằng phép so sánh =; nếu nghiệp vụ cần khớp NULL, phải định nghĩa rõ semantics.
- **RIGHT JOIN:** có quy tắc phạm vi tham chiếu riêng; ưu tiên viết lại theo thứ tự JOIN dễ hiểu nếu có thể.
- **Dữ liệu lớn:** không dùng LATERAL chỉ vì cú pháp ngắn hơn; window function hoặc pre-aggregation có thể phù hợp hơn.

## 13. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng LATERAL trên MySQL 5.7 | Server không hỗ trợ cú pháp | Kiểm tra VERSION(); dùng cách thay thế |
| Quên từ khóa LATERAL | Derived table không được phép tham chiếu bảng ngoài cùng query block | Thêm LATERAL trước subquery |
| Đặt derived table trước bảng mà nó tham chiếu | Alias chưa nằm trong phạm vi | Đổi thứ tự FROM/JOIN |
| Quên alias cho derived table | Câu SQL không hợp lệ | Đặt alias ngay sau dấu ngoặc |
| Dùng JOIN LATERAL khi muốn giữ hàng cha không có kết quả | Hàng cha không có hàng con bị loại | Dùng LEFT JOIN LATERAL ... ON TRUE |
| Dùng LIMIT mà không ORDER BY | Hàng được chọn không xác định | Thêm thứ tự nghiệp vụ và tie-breaker |
| Chỉ ORDER BY trong subquery | Kết quả cuối không được đảm bảo có thứ tự | Thêm ORDER BY ở query ngoài |
| Cho rằng LATERAL luôn nhanh hơn window function | Có thể lặp truy vấn con trên tập hàng cha lớn | So sánh EXPLAIN ANALYZE |
| Thiếu index theo cột liên kết | Truy vấn con phải đọc nhiều hàng | Thiết kế index bắt đầu bằng khóa liên kết |

## 14. Thực hành tổng hợp

Dùng bảng customers và orders trong database lab:

1. Kiểm tra phiên bản server bằng SELECT VERSION().
2. Tạo index (customer_id, created_at DESC, order_id DESC) trên bảng orders.
3. Viết JOIN LATERAL lấy đơn hàng mới nhất cho mỗi khách hàng.
4. Đổi sang LEFT JOIN LATERAL và tạo một khách hàng chưa có đơn để quan sát kết quả NULL.
5. Thay LIMIT 1 bằng LIMIT 3 để lấy top 3 đơn hàng cho mỗi khách hàng.
6. Thêm điều kiện status = 'PAID' vào truy vấn con và xác nhận thứ tự lọc, sắp xếp, giới hạn.
7. Viết lại cùng yêu cầu bằng ROW_NUMBER() OVER (PARTITION BY ...).
8. Chạy EXPLAIN và EXPLAIN ANALYZE để so sánh access path và số hàng thực tế.
9. Thử với tập khách hàng nhỏ và tập lớn để thấy chi phí phụ thuộc số hàng ngoài.
10. Giải thích khi nào scalar subquery, EXISTS, pre-aggregation hoặc window function dễ hiểu và phù hợp hơn.

## 15. Ghi nhớ

- Derived table thông thường không tham chiếu trực tiếp bảng khác trong cùng FROM; LATERAL mở khả năng tham chiếu tương quan.
- MySQL hỗ trợ LATERAL derived table từ phiên bản 8.0.14.
- Đặt LATERAL trước subquery và đặt bảng được tham chiếu ở phía trước trong FROM.
- Derived table cần alias; ON TRUE thường dùng khi điều kiện liên kết đã nằm trong subquery.
- JOIN LATERAL loại hàng cha không có kết quả; LEFT JOIN LATERAL giữ hàng cha và trả NULL cho cột con.
- LATERAL phù hợp với top N cho mỗi hàng cha, nhiều cột từ một truy vấn tương quan và phép tính phụ thuộc hàng ngoài.
- Dùng ORDER BY có tie-breaker trước LIMIT; thêm ORDER BY ngoài nếu cần thứ tự kết quả cuối.
- Index thường nên bắt đầu bằng cột liên kết, tiếp theo là cột lọc và sắp xếp phù hợp.
- LATERAL có thể được đánh giá nhiều lần theo số hàng ngoài; so sánh với window function và pre-aggregation bằng execution plan.
- Kiểm tra phiên bản server, index, số hàng ngoài và số hàng con trước khi triển khai.

Hãy dùng LATERAL khi truy vấn con thực sự cần dữ liệu của hàng đứng trước và cần trả về một tập kết quả liên quan cho từng hàng đó. Kết hợp đúng loại JOIN, thứ tự tham chiếu và index sẽ giúp truy vấn rõ ràng, đúng ngữ nghĩa và có chi phí dễ đánh giá.

