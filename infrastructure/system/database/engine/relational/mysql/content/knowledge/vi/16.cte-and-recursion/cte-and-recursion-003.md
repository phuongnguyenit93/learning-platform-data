# Derived table, CTE và lựa chọn tái sử dụng truy vấn

## Mục tiêu

Sau bài này, bạn có thể:

- Viết derived table trong mệnh đề `FROM` và đặt alias cho kết quả truy vấn con.
- Dùng common table expression (CTE) với `WITH` để đặt tên cho một phần truy vấn.
- Tái sử dụng một CTE nhiều lần trong cùng câu lệnh khi cần.
- Phân biệt phạm vi sử dụng của derived table, CTE, view và temporary table.
- Hiểu optimizer có thể merge hoặc materialize derived table/CTE như thế nào.
- Chọn cấu trúc phù hợp theo độ phức tạp, khả năng tái sử dụng, hiệu năng và phiên bản MySQL.
- Kiểm tra kế hoạch thực thi thay vì giả định CTE luôn nhanh hơn hoặc luôn được thực thi một lần.

## 1. Vì sao cần đặt tên cho truy vấn con?

Khi một câu SQL phải tổng hợp dữ liệu, lọc kết quả tổng hợp rồi tiếp tục JOIN hoặc tính toán, một truy vấn có thể trở nên dài và khó đọc. Derived table và CTE cho phép chia câu lệnh thành các khối truy vấn có tên hoặc có vị trí rõ ràng.

Ví dụ, muốn tìm khách hàng có tổng doanh thu cao hơn mức trung bình của tất cả khách hàng, trước hết cần tính doanh thu theo khách hàng, sau đó so sánh các tổng này với trung bình của chúng. Có thể thực hiện bằng derived table hoặc CTE.

Hai cấu trúc này giúp:

- Tách một phép tính trung gian thành một query block dễ hiểu.
- Đặt tên cho dữ liệu trung gian như `customer_totals` hoặc `monthly_sales`.
- Tránh lặp lại cùng một đoạn SQL dài trong một câu lệnh.
- Kết hợp kết quả trung gian với các bảng khác.
- Làm cho việc đọc, kiểm thử và thay đổi truy vấn dễ hơn.

Điểm cần nhớ: derived table và CTE là cấu trúc của một câu lệnh SQL. Chúng không tự tạo bảng lưu trữ lâu dài và không mặc nhiên làm cho truy vấn nhanh hơn.

## 2. Derived table là gì?

Derived table là một truy vấn con được đặt trong mệnh đề `FROM`. Kết quả của truy vấn con được dùng như một bảng trong truy vấn bên ngoài.

Cú pháp tổng quát:

```sql
SELECT outer_query_columns
FROM (
    SELECT inner_query_columns
    FROM source_table
    WHERE conditions
) AS derived_alias
WHERE outer_conditions;
```

Trong MySQL, derived table phải có alias. Alias giúp truy vấn bên ngoài tham chiếu các cột của kết quả truy vấn con.

### 2.1. Ví dụ tổng hợp trước rồi lọc sau

Giả sử bảng `orders` lưu các đơn hàng. Muốn tìm khách hàng có tổng tiền đơn hàng lớn hơn 10.000.000:

```sql
SELECT
    customer_totals.customer_id,
    customer_totals.total_amount
FROM (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS customer_totals
WHERE customer_totals.total_amount > 10000000;
```

Truy vấn bên trong tạo một hàng cho mỗi khách hàng. Truy vấn bên ngoài xem kết quả đó như một bảng có tên `customer_totals` và lọc theo tổng doanh thu.

### 2.2. JOIN với derived table

Derived table có thể được JOIN với bảng gốc:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(t.total_amount, 0) AS total_amount
FROM customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.customer_id;
```

Truy vấn con tổng hợp đơn hàng theo khách hàng. `LEFT JOIN` giữ lại cả khách hàng chưa có đơn; `COALESCE()` hiển thị 0 khi không có hàng tương ứng trong derived table. Chỉ dùng 0 nếu đó là cách biểu diễn phù hợp với nghiệp vụ.

### 2.3. Đặt tên cột rõ ràng

Nên đặt alias cho biểu thức tổng hợp:

```sql
SELECT
    totals.customer_id,
    totals.order_count,
    totals.revenue
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS totals;
```

Tên cột của derived table đến từ tên cột nguồn hoặc alias biểu thức. Có thể khai báo danh sách tên cột sau alias trong cú pháp phù hợp, nhưng alias biểu thức ngay tại SELECT thường giúp người đọc hiểu nguồn gốc giá trị hơn.

### 2.4. Derived table có thể lồng nhau

Có thể đặt một derived table bên trong một derived table khác, nhưng lồng nhiều tầng làm truy vấn khó đọc và khó tối ưu bằng mắt. Nếu một bước trung gian có tên nghiệp vụ rõ ràng hoặc được dùng nhiều lần, CTE thường giúp thể hiện cấu trúc tốt hơn.

Không nên tách mọi biểu thức thành một derived table riêng. Chỉ tạo query block khi nó làm rõ một bước xử lý hoặc cần một ranh giới logic hữu ích.

## 3. CTE là gì?

CTE (common table expression) là một tập kết quả được đặt tên trong phần `WITH` ở đầu một câu lệnh. Truy vấn chính có thể tham chiếu CTE giống như tham chiếu một bảng trong phạm vi câu lệnh đó.

Cú pháp cơ bản:

```sql
WITH cte_name AS (
    SELECT ...
)
SELECT ...
FROM cte_name;
```

Ví dụ viết lại truy vấn doanh thu bằng CTE:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    total_amount
FROM customer_totals
WHERE total_amount > 10000000;
```

CTE có tên `customer_totals`, nên truy vấn chính thể hiện rõ dữ liệu đang được lọc là tổng doanh thu theo khách hàng.

### 3.1. CTE chỉ có hiệu lực trong một câu lệnh

CTE không phải bảng tạm tồn tại trong session. Tên CTE chỉ có thể được tham chiếu trong câu lệnh gắn với phần `WITH` đó.

Ví dụ:

```sql
WITH active_customers AS (
    SELECT customer_id, full_name
    FROM customers
    WHERE status = 'ACTIVE'
)
SELECT *
FROM active_customers;
```

Ngay sau khi câu SELECT hoàn tất, tên `active_customers` không còn tồn tại để dùng trong một câu SQL độc lập tiếp theo. Nếu cần dùng lại giữa nhiều câu lệnh, hãy cân nhắc view hoặc temporary table.

CTE không tự lưu dữ liệu qua các lần gọi API, không có index do người dùng khai báo trực tiếp và không thay thế bảng lưu trữ.

### 3.2. Khai báo tên cột cho CTE

Có thể khai báo danh sách tên cột ngay sau tên CTE:

```sql
WITH customer_totals (customer_id, order_count, revenue) AS (
    SELECT
        customer_id,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, order_count, revenue
FROM customer_totals;
```

Số tên cột phải khớp với số cột được truy vấn con trả về. Cách này hữu ích khi biểu thức trong SELECT không có tên rõ ràng, nhưng alias trực tiếp trong truy vấn con vẫn thường dễ đọc hơn.

## 4. Khai báo nhiều CTE và tạo pipeline truy vấn

Một câu lệnh có thể khai báo nhiều CTE, phân tách bằng dấu phẩy. CTE phía sau có thể tham chiếu CTE được khai báo trước đó.

Ví dụ tính doanh thu theo tháng rồi xếp hạng tháng:

```sql
WITH monthly_sales AS (
    SELECT
        DATE_FORMAT(created_at, '%Y-%m') AS sales_month,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY DATE_FORMAT(created_at, '%Y-%m')
), ranked_months AS (
    SELECT
        sales_month,
        revenue,
        RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM monthly_sales
)
SELECT
    sales_month,
    revenue,
    revenue_rank
FROM ranked_months
WHERE revenue_rank <= 3
ORDER BY revenue_rank, sales_month;
```

Luồng xử lý được chia thành hai bước:

1. `monthly_sales` tính doanh thu cho từng tháng.
2. `ranked_months` dùng kết quả đó để xếp hạng.
3. Truy vấn cuối lấy ba hạng đầu và sắp xếp kết quả.

Ví dụ dùng window function `RANK()`, vì vậy cần MySQL 8.0 trở lên. Nếu nhiều tháng có cùng doanh thu, `RANK()` có thể tạo cùng thứ hạng và bỏ qua số thứ hạng tiếp theo; nếu muốn thứ tự liên tục, cân nhắc `DENSE_RANK()`.

### 4.1. Thứ tự tham chiếu giữa các CTE

Trong một danh sách CTE không đệ quy, hãy khai báo CTE nguồn trước CTE sử dụng nó:

```sql
WITH base_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
), customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM base_orders
    GROUP BY customer_id
)
SELECT *
FROM customer_totals;
```

`customer_totals` tham chiếu `base_orders` đã khai báo trước. Việc sắp xếp CTE theo luồng phụ thuộc giúp người đọc theo dõi được dữ liệu đi từ nguồn đến kết quả.

### 4.2. CTE có thể có tên cột tường minh

Tên cột rõ ràng giúp tránh nhầm lẫn khi có nhiều bước tính toán:

```sql
WITH order_metrics (customer_id, order_count, total_revenue) AS (
    SELECT
        customer_id,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    order_count,
    total_revenue
FROM order_metrics;
```

Đặt tên theo ý nghĩa nghiệp vụ thay vì tên chung như `result1`, `temp_data` hoặc `query_data`.

## 5. Tái sử dụng một CTE nhiều lần trong cùng câu lệnh

Một lợi ích rõ của CTE là có thể tham chiếu cùng một tên ở nhiều vị trí trong một statement. Ví dụ, tính doanh thu mỗi khách hàng rồi lấy các khách hàng có doanh thu cao hơn mức trung bình:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    ct.customer_id,
    ct.revenue
FROM customer_totals AS ct
WHERE ct.revenue > (
    SELECT AVG(other.revenue)
    FROM customer_totals AS other
)
ORDER BY ct.revenue DESC, ct.customer_id;
```

`customer_totals` được tham chiếu ở truy vấn ngoài và scalar subquery. Định nghĩa logic chỉ xuất hiện một lần trong phần `WITH`, giúp tránh phải sao chép cả câu `GROUP BY` vào hai vị trí.

Tuy nhiên, tái sử dụng về mặt cú pháp không đồng nghĩa với bảo đảm CTE được tính đúng một lần trong mọi execution plan. Optimizer có thể merge CTE vào query block bên ngoài hoặc materialize nó. Phần tiếp theo giải thích sự khác nhau.

## 6. Derived table và CTE khác nhau thế nào?

Hai cấu trúc có mục đích gần nhau: đưa một truy vấn con vào câu lệnh lớn hơn. Khác biệt chính nằm ở cách tổ chức và phạm vi tham chiếu.

| Tiêu chí | Derived table | CTE |
|---|---|---|
| Vị trí khai báo | Trực tiếp trong `FROM` hoặc vị trí hỗ trợ derived table | Đầu câu lệnh trong `WITH` |
| Cách đặt tên | Alias ngay sau dấu ngoặc đóng | Tên CTE trong phần `WITH` |
| Phạm vi | Query block chứa derived table | Câu lệnh có phần `WITH` |
| Tái sử dụng cùng định nghĩa | Thường phải viết lại query block nếu dùng ở nhiều vị trí | Có thể tham chiếu cùng tên nhiều lần trong statement |
| Đọc truy vấn nhiều bước | Có thể khó theo dõi khi lồng nhiều tầng | Có thể đặt tên từng bước và thể hiện pipeline rõ |
| Đệ quy | Không phải cấu trúc dùng cho recursive CTE | Có thể dùng `WITH RECURSIVE` |
| Hiệu năng | Có thể được merge hoặc materialize | Cũng có thể được merge hoặc materialize |

### 6.1. Khi nào nên dùng derived table?

Derived table thường phù hợp khi:

- Kết quả trung gian chỉ dùng một lần.
- Phép tính nhỏ và gắn chặt với JOIN hoặc truy vấn bên ngoài.
- Đặt query block ngay cạnh nơi sử dụng giúp người đọc hiểu quan hệ dữ liệu.
- Không cần tên chung để tham chiếu từ nhiều vị trí.

Ví dụ:

```sql
SELECT
    c.customer_id,
    t.revenue
FROM customers AS c
JOIN (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.customer_id;
```

### 6.2. Khi nào nên dùng CTE?

CTE thường phù hợp khi:

- Truy vấn có nhiều bước logic.
- Cùng một tập kết quả được tham chiếu nhiều lần trong một statement.
- Cần tách riêng các bước lọc, tổng hợp, xếp hạng hoặc chuẩn hóa.
- Muốn đặt tên theo ngữ nghĩa nghiệp vụ để truy vấn dễ đọc và review.
- Cần viết recursive query cho cấu trúc cây hoặc quan hệ phân cấp.

Ví dụ:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
), customer_revenue AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM paid_orders
    GROUP BY customer_id
)
SELECT c.customer_id, c.full_name, cr.revenue
FROM customers AS c
JOIN customer_revenue AS cr
  ON cr.customer_id = c.customer_id;
```

Mỗi CTE có một nhiệm vụ rõ ràng. Nếu pipeline chỉ có một bước nhỏ, derived table có thể ngắn gọn hơn.

## 7. CTE không mặc nhiên là temporary table

Một hiểu nhầm phổ biến là CTE luôn được chạy trước, lưu toàn bộ kết quả vào bảng tạm, rồi truy vấn chính mới đọc bảng đó. Đây không phải quy tắc chung.

MySQL optimizer có thể xử lý derived table, view reference và CTE theo hai hướng chính:

1. **Merge:** hợp nhất query block vào query bên ngoài để optimizer tối ưu như một truy vấn chung.
2. **Materialize:** tính kết quả trung gian và lưu vào internal temporary table để query bên ngoài đọc.

CTE chỉ là tên logic trong một statement. Quyết định merge hay materialize thuộc optimizer và phụ thuộc cấu trúc truy vấn, thống kê, phiên bản cùng các điều kiện tối ưu.

### 7.1. Merge query block

Khi merge, optimizer đưa phần truy vấn con vào query block bên ngoài. Việc này có thể cho phép:

- Đẩy điều kiện lọc xuống gần bảng nguồn hơn.
- Tận dụng index của bảng gốc.
- Tối ưu thứ tự JOIN cùng các phép lọc.
- Tránh tạo và đọc một bảng tạm không cần thiết.

Vì vậy, một CTE đơn giản như lọc các đơn hàng đã thanh toán có thể được merge:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT order_id, total_amount
FROM paid_orders
WHERE customer_id = 101;
```

Optimizer có thể kết hợp hai điều kiện thành truy vấn trực tiếp trên `orders`.

### 7.2. Materialize kết quả trung gian

Khi materialize, MySQL tạo internal temporary table cho kết quả query block. Bảng tạm nội bộ có thể ở bộ nhớ hoặc chuyển sang lưu trữ tạm trên đĩa tùy kích thước và giới hạn cấu hình.

Materialization có chi phí tạo kết quả trung gian, nhưng có thể hữu ích khi:

- Query block cần được dùng như một tập kết quả riêng.
- Có phép tổng hợp hoặc cấu trúc khiến merge không phù hợp.
- CTE được tham chiếu nhiều lần và việc materialize một lần có lợi.
- Optimizer có thể tạo index nội bộ để hỗ trợ truy cập kết quả đã materialize.

MySQL có thể trì hoãn việc materialize cho tới khi kết quả thực sự cần thiết. Nếu một nhánh JOIN trước đó cho ra 0 hàng và kết quả trung gian không cần dùng, việc materialize có thể được bỏ qua.

### 7.3. Cấu trúc có thể ngăn merge

Một số cấu trúc thường khiến derived table/CTE không thể merge vào query block ngoài, ví dụ:

- Aggregate function như `SUM()`, `COUNT()`, `AVG()`.
- `GROUP BY` hoặc `HAVING`.
- `DISTINCT`.
- Window function.
- `LIMIT`.
- `UNION` hoặc `UNION ALL` trong các trường hợp liên quan.

Đây là các quy tắc phụ thuộc điều kiện và phiên bản; không nên dùng danh sách này như một phép đoán thay cho execution plan. Khi không merge được, optimizer có thể materialize kết quả.

### 7.4. CTE được tham chiếu nhiều lần

Nếu một CTE được materialize và được tham chiếu nhiều lần trong cùng câu lệnh, MySQL materialize nó một lần rồi tái sử dụng kết quả. Optimizer có thể tạo các index nội bộ khác nhau để phục vụ các cách truy cập khác nhau tới CTE đó.

Nếu CTE được merge, định nghĩa có thể được hòa vào từng query block tham chiếu. Vì vậy, không nên dựa vào giả định rằng một CTE được viết một lần thì nội dung chắc chắn chỉ được tính một lần.

Nếu mục tiêu là kiểm soát hiệu năng, hãy so sánh kế hoạch thực thi. Nếu mục tiêu là dễ bảo trì, CTE vẫn hữu ích ngay cả khi optimizer merge nó.

## 8. ORDER BY bên trong derived table/CTE

Không có bảo đảm rằng kết quả từ derived table hoặc CTE sẽ giữ nguyên thứ tự chỉ vì truy vấn con có `ORDER BY`.

Ví dụ:

```sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC
) AS recent_orders;
```

Truy vấn ngoài không khai báo `ORDER BY`, nên không có cam kết thứ tự đầu ra. Nếu cần kết quả mới nhất trước, phải sắp xếp ở truy vấn ngoài:

```sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
) AS recent_orders
ORDER BY created_at DESC, order_id DESC;
```

Nếu `ORDER BY` được dùng cùng `LIMIT` bên trong để chọn top-N, thứ tự đó quyết định hàng nào được chọn vào tập trung gian:

```sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 10
) AS latest_orders
ORDER BY created_at DESC, order_id DESC;
```

Ở đây, `ORDER BY` bên trong chọn 10 đơn mới nhất; `ORDER BY` bên ngoài bảo đảm thứ tự khi trả kết quả. Hãy dùng tie-breaker duy nhất nếu timestamp có thể trùng.

## 9. CTE so với view và temporary table

Derived table và CTE chỉ tồn tại trong cấu trúc một câu lệnh. Khi cần tái sử dụng logic hoặc dữ liệu qua nhiều câu lệnh, cần cân nhắc các cơ chế khác.

| Cơ chế | Phạm vi tồn tại | Dùng khi |
|---|---|---|
| Derived table | Một vị trí trong một statement | Query block nhỏ, chỉ dùng một lần |
| CTE | Một statement | Nhiều bước logic hoặc tái sử dụng tên CTE trong cùng statement |
| View | Đối tượng schema tồn tại cho đến khi bị thay đổi/xóa | Muốn đóng gói truy vấn và tái sử dụng qua nhiều statement/người dùng có quyền |
| Temporary table | Session hiện tại, đến khi drop hoặc session kết thúc | Cần lưu kết quả trung gian qua nhiều statement hoặc tạo index riêng cho bước xử lý |
| Bảng thường/materialized result do ứng dụng quản lý | Tồn tại theo chính sách lưu trữ | Cần lưu kết quả tính sẵn, chia sẻ giữa session hoặc phục vụ workload lặp lại |

### 9.1. Khi nào dùng view?

View phù hợp khi cùng một logic truy vấn cần được sử dụng bởi nhiều câu lệnh hoặc nhiều thành phần ứng dụng:

```sql
CREATE VIEW customer_order_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

Sau đó:

```sql
SELECT customer_id, revenue
FROM customer_order_totals
WHERE revenue > 10000000;
```

View thông thường lưu định nghĩa truy vấn, không lưu sẵn kết quả như materialized view ở một số hệ quản trị khác. Khi truy vấn view, optimizer vẫn xử lý định nghĩa view và có thể merge hoặc materialize theo quy tắc của MySQL.

### 9.2. Khi nào dùng temporary table?

Nếu cần tạo một tập trung gian rồi dùng qua nhiều câu SQL trong cùng session:

```sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT UNSIGNED NOT NULL,
    revenue DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (customer_id)
);

INSERT INTO tmp_customer_totals (customer_id, revenue)
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;

SELECT customer_id, revenue
FROM tmp_customer_totals
WHERE revenue > 10000000;

DROP TEMPORARY TABLE tmp_customer_totals;
```

Temporary table cho phép khai báo index/constraint theo nhu cầu và tái sử dụng kết quả qua nhiều statement. Đổi lại, ứng dụng phải quản lý vòng đời, session và dọn dẹp. Connection pool có thể tái sử dụng connection, vì vậy cần tránh để temporary table cũ ảnh hưởng request tiếp theo.

## 10. Lựa chọn giữa derived table và CTE theo ví dụ

### 10.1. Một lần dùng, một bước đơn giản: derived table

```sql
SELECT
    p.category_id,
    p.product_name,
    p.price
FROM products AS p
JOIN (
    SELECT category_id, AVG(price) AS avg_price
    FROM products
    GROUP BY category_id
) AS category_average
  ON category_average.category_id = p.category_id
WHERE p.price > category_average.avg_price;
```

Derived table được dùng một lần để tính giá trung bình theo danh mục. Cách viết này gọn nếu logic trung gian chỉ có một bước.

### 10.2. Nhiều bước hoặc dùng lại: CTE

```sql
WITH category_average AS (
    SELECT
        category_id,
        AVG(price) AS avg_price
    FROM products
    GROUP BY category_id
), above_average AS (
    SELECT
        p.product_id,
        p.category_id,
        p.product_name,
        p.price,
        ca.avg_price
    FROM products AS p
    JOIN category_average AS ca
      ON ca.category_id = p.category_id
    WHERE p.price > ca.avg_price
)
SELECT
    product_id,
    category_id,
    product_name,
    price,
    avg_price
FROM above_average
ORDER BY category_id, price DESC, product_id;
```

Mỗi CTE biểu diễn một bước nghiệp vụ: tính trung bình theo danh mục, sau đó lấy sản phẩm cao hơn trung bình. Truy vấn cuối chỉ định rõ thứ tự trả về.

### 10.3. Không dùng CTE chỉ để đổi tên mọi bảng

CTE không tự làm câu lệnh tốt hơn nếu chỉ thêm một tầng tên không có ý nghĩa:

```sql
WITH all_orders AS (
    SELECT * FROM orders
)
SELECT * FROM all_orders;
```

Nếu CTE không thêm bộ lọc, phép tính, tên nghiệp vụ hoặc khả năng tái sử dụng, truy vấn trực tiếp thường dễ đọc hơn. Tránh `SELECT *` trong CTE dùng lâu dài vì thay đổi schema nguồn có thể làm thay đổi tập cột và tăng dữ liệu không cần thiết.

## 11. Hiệu năng: EXPLAIN và các yếu tố cần quan sát

Không thể kết luận CTE nhanh hơn derived table chỉ từ cú pháp. Nếu hai câu SQL biểu diễn cùng logic, optimizer có thể tạo execution plan giống hoặc gần giống nhau.

### 11.1. Dùng EXPLAIN

```sql
EXPLAIN
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_totals
WHERE revenue > 10000000;
```

Kiểm tra:

- Bảng nguồn nào được đọc và theo access type nào.
- Index nào được chọn.
- Số hàng ước lượng ở từng bước.
- Có bước materialize hoặc temporary table hay không.
- Có filesort hoặc xử lý tạm nào đáng kể không.
- Điều kiện lọc được áp dụng sớm hay muộn.

Chi tiết hiển thị của CTE/derived table trong `EXPLAIN` phụ thuộc phiên bản và định dạng explain. Có thể dùng `EXPLAIN FORMAT=TREE` trên phiên bản hỗ trợ để đọc luồng thực thi rõ hơn.

### 11.2. EXPLAIN ANALYZE

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho các câu lệnh SELECT phù hợp:

```sql
EXPLAIN ANALYZE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_totals
WHERE revenue > 10000000;
```

Lệnh này thực sự thực thi truy vấn và báo thời gian cùng số hàng thực tế ở các iterator. Chỉ dùng với truy vấn và môi trường phù hợp, vì một câu truy vấn tổng hợp lớn vẫn tạo tải thật trên server.

### 11.3. Index vẫn cần thiết trên bảng nguồn

CTE không tạo index trực tiếp cho bảng nguồn. Nếu truy vấn lọc đơn theo trạng thái và thời gian:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount, created_at
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= '2026-01-01'
)
SELECT customer_id, SUM(total_amount) AS revenue
FROM paid_orders
GROUP BY customer_id;
```

cần xem workload để đánh giá index trên `orders`, ví dụ `(status, created_at, customer_id)` hoặc một thứ tự cột khác theo độ chọn lọc và truy vấn thực tế. Không có index mẫu nào đúng cho mọi phân bố dữ liệu.

### 11.4. Materialization và chi phí bộ nhớ/đĩa

Nếu query block materialize nhiều hàng hoặc nhiều cột, internal temporary table có thể lớn. Giảm chi phí bằng cách:

- Chỉ chọn các cột cần dùng, tránh `SELECT *`.
- Lọc hàng sớm nếu điều kiện có thể áp dụng an toàn.
- Tổng hợp ở đúng mức chi tiết cần thiết.
- Tránh materialize một tập dữ liệu lớn chỉ để dùng một lần khi có thể merge hiệu quả.
- Đo với quy mô gần production và theo dõi temporary table trên đĩa.

Nếu CTE được tham chiếu nhiều lần, materialize một lần có thể tiết kiệm việc tính lại. Nhưng nếu tập trung gian rất lớn hoặc optimizer có thể đẩy điều kiện riêng vào từng query block khi merge, materialization có thể không phải lựa chọn tốt nhất. Hãy dựa vào execution plan và số liệu đo.

## 12. Kiểm soát merge/materialization khi cần

Trong một số tình huống tối ưu nâng cao, MySQL cung cấp optimizer hints `MERGE()` và `NO_MERGE()` cho derived table, view reference và CTE ở các phiên bản hỗ trợ.

Ví dụ minh họa yêu cầu optimizer không merge CTE:

```sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT /*+ NO_MERGE(customer_totals) */
    customer_id,
    revenue
FROM customer_totals
WHERE revenue > 10000000;
```

Hint là gợi ý cho optimizer, không phải cách thay thế việc đo hiệu năng. Cú pháp, phạm vi và khả năng áp dụng phụ thuộc phiên bản MySQL. Hãy kiểm tra warning nếu hint không được nhận diện hoặc không áp dụng, rồi so sánh `EXPLAIN`/`EXPLAIN ANALYZE` trước và sau.

Không ép materialize hoặc merge chỉ vì nghĩ một phương án luôn nhanh hơn. Một hint không phù hợp có thể làm optimizer mất cơ hội đẩy điều kiện, dùng index hoặc chọn thứ tự JOIN tốt hơn.

## 13. CTE đệ quy và phạm vi bài học

CTE không đệ quy được khai báo bằng `WITH`. Khi cần truy vấn cấu trúc phân cấp như cây danh mục hoặc sơ đồ quản lý, MySQL hỗ trợ `WITH RECURSIVE`:

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, parent_id, category_name, 0 AS depth
    FROM categories
    WHERE category_id = 10

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        ct.depth + 1
    FROM categories AS c
    JOIN category_tree AS ct
      ON c.parent_id = ct.category_id
)
SELECT category_id, parent_id, category_name, depth
FROM category_tree
ORDER BY depth, category_id;
```

Phần anchor query lấy nút gốc; phần recursive query tìm các nút con của những hàng đã có. Ví dụ này minh họa cấu trúc và giả định dữ liệu không có chu trình gây lặp vô hạn. Cần có chính sách chống chu trình và giới hạn độ sâu phù hợp khi triển khai.

CTE đệ quy là chủ đề chuyên biệt cho truy vấn cây. Bài này tập trung vào derived table, CTE không đệ quy và cách chọn cấu trúc tái sử dụng truy vấn; khi làm việc với cây, cần học thêm điều kiện dừng, kiểu dữ liệu của cột đệ quy, `cte_max_recursion_depth` và xử lý chu trình.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Derived table không có alias | MySQL báo lỗi cú pháp/thiếu tên bảng dẫn xuất | Đặt alias ngay sau dấu ngoặc đóng |
| Nghĩ CTE là temporary table | Mong đợi CTE tồn tại ở câu lệnh tiếp theo | Dùng view hoặc temporary table nếu cần nhiều statement |
| Nghĩ CTE luôn được tính một lần | Dự đoán sai chi phí khi optimizer merge | Kiểm tra merge/materialization bằng EXPLAIN |
| Nghĩ CTE luôn materialize | Có thể bỏ lỡ khả năng merge và predicate pushdown | Hiểu CTE là query block; optimizer quyết định cách thực thi |
| Dùng CTE chỉ để bọc SELECT * | Tăng tầng không cần thiết và phụ thuộc schema nguồn | Chọn cột rõ ràng, chỉ tạo CTE khi có ý nghĩa |
| Dựa vào ORDER BY trong CTE để sắp xếp đầu ra | Kết quả ngoài không được bảo đảm thứ tự | Đặt ORDER BY ở SELECT cuối |
| Lồng quá nhiều derived table | SQL khó đọc và khó bảo trì | Đặt tên các bước bằng CTE nếu giúp rõ luồng xử lý |
| Dùng CTE nhiều lần mà không đo | Materialization hoặc merge có thể không phù hợp workload | So sánh execution plan và latency |
| Tạo temporary table nhưng không quản lý pool | Session tái sử dụng có thể giữ bảng tạm cũ | Dọn dẹp và quản lý vòng đời theo connection |

## 15. Quy trình chọn cấu trúc phù hợp

1. **Xác định phạm vi tái sử dụng:** chỉ dùng một lần, nhiều vị trí trong một statement hay nhiều statement?
2. **Xác định các bước logic:** có lọc, tổng hợp, xếp hạng hoặc biến đổi trung gian nào cần tên riêng không?
3. **Chọn derived table nếu:** query block nhỏ, chỉ dùng một lần và đặt cạnh JOIN giúp dễ hiểu.
4. **Chọn CTE nếu:** có nhiều bước, cần đặt tên theo nghiệp vụ hoặc tái sử dụng cùng kết quả trong một statement.
5. **Chọn view nếu:** logic cần dùng lại qua nhiều statement và được quản lý như đối tượng schema.
6. **Chọn temporary table nếu:** cần lưu kết quả qua nhiều statement, tạo index riêng hoặc xử lý theo từng giai đoạn trong một session.
7. **Kiểm tra optimizer:** xác định query block có merge hay materialize, có temporary table hoặc index nội bộ hay không.
8. **Đo hiệu năng:** dùng EXPLAIN, EXPLAIN ANALYZE phù hợp và dữ liệu đại diện.
9. **Kiểm tra đầu ra:** xác minh số hàng, NULL, nhóm, thứ tự và tính đúng của các phép tổng hợp.

## 16. Checklist trước khi đưa truy vấn vào production

- [ ] Derived table có alias rõ ràng.
- [ ] CTE có tên và tên cột phản ánh ý nghĩa nghiệp vụ.
- [ ] Mỗi query block chỉ chọn các cột cần thiết.
- [ ] Đã xác định CTE chỉ dùng trong statement hay cần tái sử dụng lâu dài.
- [ ] Không dựa vào thứ tự của derived table/CTE nếu SELECT cuối không có ORDER BY.
- [ ] Không giả định CTE luôn materialize hoặc luôn chạy một lần.
- [ ] Đã xem xét merge, materialization và kích thước tập trung gian.
- [ ] Bảng nguồn có index phù hợp với điều kiện lọc/JOIN thực tế.
- [ ] Đã kiểm tra EXPLAIN và đo truy vấn với dữ liệu đại diện.
- [ ] Nếu dùng hint, đã xác minh server nhận hint và đã đo trước/sau.
- [ ] Nếu dùng temporary table, đã quản lý vòng đời theo session/connection pool.
- [ ] Nếu dùng recursive CTE, đã xác định anchor, điều kiện dừng, giới hạn độ sâu và chống chu trình.

## 17. Kết luận

Derived table đặt truy vấn con trong `FROM` và thường phù hợp với một bước trung gian chỉ dùng một lần. CTE đặt tên cho query block ở đầu statement, giúp chia truy vấn nhiều bước và tham chiếu cùng định nghĩa ở nhiều vị trí trong một câu lệnh. Cả hai đều có thể được optimizer merge hoặc materialize; CTE không mặc nhiên là temporary table và cũng không bảo đảm truy vấn nhanh hơn.

Hãy chọn cấu trúc theo phạm vi tái sử dụng và độ rõ ràng của logic. Dùng view khi cần tái sử dụng qua nhiều statement, temporary table khi cần lưu kết quả trung gian qua nhiều bước, và luôn kiểm tra execution plan khi hiệu năng quan trọng. Một truy vấn dễ đọc cần đi cùng kết quả đúng, index phù hợp và hành vi thực thi đã được đo.
