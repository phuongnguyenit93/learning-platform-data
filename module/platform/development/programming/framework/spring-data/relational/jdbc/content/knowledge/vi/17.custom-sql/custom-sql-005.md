# JOIN, truy vấn con, tổng hợp và window function trong SQL tự viết

**Spring Data JDBC** cung cấp repository để lưu và tải aggregate, nhưng không giới hạn ứng dụng ở các thao tác CRUD tự sinh. Khi nghiệp vụ cần kết hợp nhiều bảng, lọc theo kết quả của truy vấn khác, tính tổng hoặc xếp hạng dữ liệu, bạn có thể viết SQL tùy chỉnh bằng `@Query`, `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`.

Bài học tập trung vào bốn nhóm kỹ thuật SQL thường dùng trong ứng dụng Spring Data Relational JDBC:

- **JOIN** kết hợp dữ liệu từ nhiều bảng.
- **Subquery** (truy vấn con) dùng kết quả của một truy vấn bên trong truy vấn khác.
- **Aggregate function** như `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` để tổng hợp nhiều hàng.
- **Window function** như `ROW_NUMBER`, `RANK`, `LAG` và `SUM() OVER` để tính toán trên một nhóm hàng mà vẫn giữ từng hàng trong kết quả.

Ta sẽ dùng một hệ thống đơn hàng làm ví dụ. Repository tiếp tục quản lý aggregate root; những truy vấn đọc có JOIN hoặc kết quả báo cáo có thể trả về DTO riêng. SQL phải được tham số hóa, kết quả cần có thứ tự rõ ràng khi phân trang, và câu lệnh cần được kiểm tra theo database thực tế của ứng dụng.

## 1. Bối cảnh dữ liệu và các công cụ truy vấn

Giả sử ứng dụng có ba bảng:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_lines_quantity CHECK (quantity > 0)
);
~~~

Một đơn hàng có nhiều dòng hàng. Trong domain, `PurchaseOrder` có thể là aggregate root, còn `OrderLine` là entity con. `Customer` là aggregate độc lập và đơn hàng giữ tham chiếu `customerId`.

Tùy nhu cầu, ứng dụng có thể dùng ba cách:

| Công cụ | Cách sử dụng | Khi phù hợp |
|---|---|---|
| Derived query trong repository | Đặt tên method theo thuộc tính | Lọc đơn giản, ít điều kiện |
| `@Query` trên repository | Viết SQL tường minh trong repository | Query gắn với repository và kết quả mapping phù hợp |
| `JdbcTemplate` / `NamedParameterJdbcTemplate` | Viết SQL và ánh xạ kết quả thủ công | JOIN phức tạp, DTO báo cáo, aggregate function, window function |

Không cần tạo repository riêng cho từng bảng chỉ để viết JOIN. Repository mô tả cổng truy cập aggregate; DAO/query service có thể phục vụ mô hình đọc riêng.

## 2. JOIN: kết hợp dữ liệu từ nhiều bảng

JOIN dùng điều kiện liên kết hàng của hai hoặc nhiều bảng. Trong ví dụ, `purchase_orders.customer_id` trỏ đến `customers.id`, còn `order_lines.order_id` trỏ đến `purchase_orders.id`.

### 2.1. INNER JOIN

`INNER JOIN` chỉ trả về các hàng có cặp liên kết thỏa mãn điều kiện:

~~~sql
SELECT
    o.id,
    o.order_number,
    o.status,
    c.display_name AS customer_name
FROM purchase_orders o
INNER JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'SUBMITTED'
ORDER BY o.created_at DESC, o.id DESC;
~~~

Mỗi đơn có khách hàng tương ứng sẽ xuất hiện trong kết quả. Nếu một đơn có tham chiếu khách hàng không hợp lệ, đơn đó không xuất hiện với INNER JOIN; trong schema có foreign key, trường hợp này thường bị ngăn từ lúc ghi dữ liệu.

### 2.2. LEFT JOIN

`LEFT JOIN` giữ tất cả hàng ở bảng bên trái, kể cả khi không có hàng tương ứng ở bảng bên phải:

~~~sql
SELECT
    o.id,
    o.order_number,
    c.display_name AS customer_name
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
ORDER BY o.id;
~~~

Nếu không tìm thấy khách hàng, các cột của `c` có giá trị `NULL`. Cách này hữu ích khi dữ liệu liên kết là tùy chọn hoặc báo cáo vẫn cần hiển thị hàng bên trái dù thiếu dữ liệu bên phải.

Một lỗi phổ biến là đặt điều kiện của bảng bên phải trong `WHERE`:

~~~sql
SELECT o.id, c.display_name
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.display_name LIKE 'An%';
~~~

Điều kiện `WHERE c.display_name ...` loại các hàng có `c.display_name IS NULL`, khiến kết quả gần như INNER JOIN. Nếu muốn giữ tất cả đơn nhưng chỉ nối khách hàng có tên bắt đầu bằng “An”, chuyển điều kiện vào `ON`:

~~~sql
SELECT o.id, c.display_name
FROM purchase_orders o
LEFT JOIN customers c
    ON c.id = o.customer_id
   AND c.display_name LIKE 'An%';
~~~

### 2.3. JOIN với bảng con một-nhiều

Lấy từng đơn và dòng hàng:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    l.id AS line_id,
    l.product_id,
    l.quantity,
    l.unit_price
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
ORDER BY o.id, l.id;
~~~

Nếu một đơn có ba dòng hàng, kết quả có ba hàng mang cùng `order_id`. Đây là cardinality tự nhiên của quan hệ một-nhiều. Không được giả định mỗi hàng kết quả tương ứng với một aggregate root duy nhất.

Điều này quan trọng khi ánh xạ DTO. Nếu màn hình cần một hàng cho mỗi đơn, hãy dùng GROUP BY, subquery tổng hợp trước hoặc một query khác. Nếu cần danh sách dòng hàng, hãy để mỗi hàng kết quả đại diện cho một dòng.

### 2.4. Tránh nhân bản dữ liệu khi JOIN nhiều collection

Giả sử mỗi đơn có nhiều dòng hàng và nhiều khoản thanh toán. JOIN trực tiếp cả hai bảng con:

~~~sql
SELECT o.id, l.id AS line_id, p.id AS payment_id
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN payments p ON p.order_id = o.id;
~~~

Nếu một đơn có 3 dòng hàng và 2 khoản thanh toán, kết quả có thể có 3 × 2 = 6 hàng. Khi đó `SUM(l.quantity * l.unit_price)` có thể bị nhân đôi do mỗi dòng hàng xuất hiện cùng từng khoản thanh toán.

Cách xử lý thường là tổng hợp từng bảng con trước rồi mới JOIN:

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
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
    o.id,
    COALESCE(l.order_total, 0) AS order_total,
    COALESCE(p.paid_total, 0) AS paid_total
FROM purchase_orders o
LEFT JOIN line_totals l ON l.order_id = o.id
LEFT JOIN payment_totals p ON p.order_id = o.id;
~~~

Mỗi CTE trả về tối đa một hàng cho mỗi đơn, nên JOIN không nhân bản các tổng đã tính. CTE và derived table là công cụ hữu ích để tách các bước tổng hợp.

## 3. Subquery: dùng truy vấn bên trong truy vấn

Subquery là một câu SELECT được lồng trong một câu SQL khác. Nó có thể trả một giá trị, một tập giá trị hoặc một bảng tạm để truy vấn bên ngoài sử dụng.

### 3.1. Scalar subquery

Scalar subquery trả một giá trị đơn, chẳng hạn tổng tiền của một đơn:

~~~sql
SELECT
    o.id,
    o.order_number,
    (
        SELECT COALESCE(SUM(l.quantity * l.unit_price), 0)
        FROM order_lines l
        WHERE l.order_id = o.id
    ) AS order_total
FROM purchase_orders o
WHERE o.status = 'SUBMITTED';
~~~

Subquery tham chiếu `o.id` từ truy vấn ngoài, nên đây là **correlated subquery**. Nó biểu diễn rõ phép tính tổng cho từng đơn. Database có thể tối ưu truy vấn này theo cách riêng; hãy kiểm tra execution plan nếu số đơn lớn.

### 3.2. EXISTS và NOT EXISTS

`EXISTS` kiểm tra có ít nhất một hàng thỏa điều kiện hay không:

~~~sql
SELECT o.id, o.order_number
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.quantity >= 5
);
~~~

Truy vấn trả các đơn có ít nhất một dòng hàng số lượng từ 5 trở lên. Không cần JOIN tất cả các dòng vào kết quả, nên mỗi đơn chỉ xuất hiện một lần.

`NOT EXISTS` tìm đơn chưa có dòng hàng:

~~~sql
SELECT o.id, o.order_number
FROM purchase_orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
);
~~~

Với câu hỏi “có ít nhất một” hoặc “không có bất kỳ”, EXISTS thường diễn đạt đúng ý định hơn JOIN kết hợp DISTINCT.

### 3.3. IN với subquery

`IN` kiểm tra một giá trị có thuộc tập giá trị do subquery trả về:

~~~sql
SELECT id, order_number
FROM purchase_orders
WHERE customer_id IN (
    SELECT id
    FROM customers
    WHERE display_name LIKE 'Nguyen%'
);
~~~

Kết quả là các đơn thuộc khách hàng có tên phù hợp. Trong ví dụ này, có thể viết INNER JOIN thay thế; lựa chọn phụ thuộc việc truy vấn cần cột nào từ bảng khách và cách đọc dễ hiểu nhất.

### 3.4. NOT IN và NULL

Hãy cẩn thận khi `NOT IN` có thể nhận một tập giá trị chứa `NULL`:

~~~sql
SELECT id
FROM customers
WHERE id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
~~~

Nếu tập kết quả chứa NULL, logic ba giá trị của SQL có thể khiến điều kiện không trả về hàng nào như người viết mong đợi. Khi cột có khả năng NULL, `NOT EXISTS` thường an toàn và dễ hiểu hơn:

~~~sql
SELECT c.id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers b
    WHERE b.customer_id = c.id
);
~~~

### 3.5. Derived table và CTE

Một subquery trong mệnh đề FROM tạo thành derived table:

~~~sql
SELECT totals.order_id, totals.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
) totals
WHERE totals.order_total >= 1000000;
~~~

CTE (`WITH`) đặt tên cho kết quả truy vấn trung gian:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_lines
    GROUP BY order_id
)
SELECT o.order_number, t.total_amount
FROM purchase_orders o
JOIN order_totals t ON t.order_id = o.id
WHERE t.total_amount >= 1000000;
~~~

CTE hữu ích khi query có nhiều bước, cần đặt tên cho phép tính trung gian hoặc tái sử dụng logic trong cùng câu SQL. Tùy hệ quản trị, CTE có thể được inline hoặc materialize; không nên mặc định nó luôn tạo bảng tạm vật lý.

## 4. Aggregate function: tổng hợp nhiều hàng

Aggregate function tính một giá trị từ nhiều hàng. Các hàm thường gặp:

| Hàm | Ý nghĩa | Ví dụ |
|---|---|---|
| `COUNT(*)` | Đếm số hàng | Số đơn hàng |
| `COUNT(column)` | Đếm giá trị khác NULL | Số dòng có product_id |
| `SUM(expression)` | Tính tổng | Tổng doanh thu |
| `AVG(expression)` | Tính trung bình | Giá trị đơn trung bình |
| `MIN(expression)` | Giá trị nhỏ nhất | Ngày đơn sớm nhất |
| `MAX(expression)` | Giá trị lớn nhất | Ngày đơn mới nhất |

### 4.1. GROUP BY

Đếm số đơn theo trạng thái:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM purchase_orders
GROUP BY status
ORDER BY status;
~~~

Tổng doanh thu theo khách hàng:

~~~sql
SELECT
    o.customer_id,
    SUM(l.quantity * l.unit_price) AS revenue
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
GROUP BY o.customer_id
ORDER BY revenue DESC;
~~~

`GROUP BY` gom các hàng có cùng giá trị ở cột nhóm, rồi tính aggregate function cho từng nhóm.

### 4.2. HAVING và WHERE

`WHERE` lọc hàng **trước khi nhóm**. `HAVING` lọc nhóm **sau khi tổng hợp**:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM purchase_orders
WHERE created_at >= :fromTime
GROUP BY customer_id
HAVING COUNT(*) >= 3
ORDER BY order_count DESC;
~~~

Trong ví dụ, chỉ các đơn từ thời điểm `fromTime` mới tham gia nhóm; sau đó chỉ giữ khách có ít nhất ba đơn trong khoảng thời gian đó.

Không dùng `WHERE COUNT(*) >= 3` vì aggregate function không thể được lọc theo cách đó trong WHERE cùng cấp. Dùng HAVING.

### 4.3. COUNT(*) và COUNT(column) khi LEFT JOIN

Xem truy vấn:

~~~sql
SELECT
    o.id,
    COUNT(*) AS joined_rows,
    COUNT(l.id) AS line_count
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id;
~~~

Với đơn không có dòng hàng, LEFT JOIN vẫn tạo một hàng kết quả với các cột `l.*` là NULL. Vì vậy `COUNT(*)` có thể trả 1, trong khi `COUNT(l.id)` trả 0. Khi đếm phần tử bên phải của LEFT JOIN, thường phải đếm khóa không null của bảng con.

### 4.4. COALESCE và xử lý NULL

`SUM` trên tập không có giá trị có thể trả NULL. Nếu muốn tổng bằng 0:

~~~sql
SELECT
    o.id,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id;
~~~

`COALESCE(a, b, ...)` trả giá trị đầu tiên không NULL. Nó hữu ích cho read model, nhưng cần chọn giá trị thay thế phù hợp với ý nghĩa nghiệp vụ; không phải mọi NULL đều nên đổi thành 0 hoặc chuỗi rỗng.

### 4.5. DISTINCT và COUNT DISTINCT

JOIN một-nhiều có thể làm một khách hàng xuất hiện nhiều lần. Đếm số khách hàng có đơn:

~~~sql
SELECT COUNT(DISTINCT customer_id) AS active_customer_count
FROM purchase_orders
WHERE created_at >= :fromTime;
~~~

`DISTINCT` loại bỏ giá trị trùng trước khi đếm. Tuy nhiên, không dùng DISTINCT để che một JOIN sai cardinality nếu mục tiêu là tổng hợp số tiền; hãy xác định quan hệ và nhóm đúng.

## 5. Window function: tính trên nhóm hàng nhưng vẫn giữ từng hàng

Aggregate function với GROUP BY thường thu gọn mỗi nhóm thành một hàng. **Window function** tính toán trên một cửa sổ hàng liên quan nhưng vẫn giữ từng hàng đầu vào trong kết quả.

Cấu trúc chung:

~~~sql
function_name(expression) OVER (
    PARTITION BY grouping_columns
    ORDER BY ordering_columns
    window_frame
)
~~~

- `PARTITION BY` chia kết quả thành các nhóm độc lập.
- `ORDER BY` xác định thứ tự bên trong mỗi nhóm.
- Window frame xác định phạm vi hàng mà hàm tính toán tại mỗi vị trí.

### 5.1. ROW_NUMBER: đánh số hàng

Đánh số đơn hàng theo thời gian trong từng khách hàng:

~~~sql
SELECT
    customer_id,
    id AS order_id,
    order_number,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC, id DESC
    ) AS row_num
FROM purchase_orders;
~~~

Mỗi khách hàng có một chuỗi đánh số bắt đầu từ 1. `id DESC` là tiêu chí phụ để kết quả xác định khi hai đơn có cùng thời điểm tạo.

### 5.2. Lấy đơn mới nhất của mỗi khách

Window function có thể kết hợp với CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, id DESC
        ) AS rn
    FROM purchase_orders o
)
SELECT id, customer_id, order_number, status, created_at
FROM ranked_orders
WHERE rn = 1;
~~~

Kết quả chỉ giữ đơn mới nhất của từng khách hàng. Không thể đặt điều kiện `WHERE rn = 1` cùng cấp với window expression trong nhiều hệ SQL vì WHERE được xử lý trước window function; bọc trong CTE hoặc subquery để lọc kết quả đã tính.

### 5.3. RANK và DENSE_RANK

Xếp hạng khách hàng theo doanh thu:

~~~sql
WITH customer_revenue AS (
    SELECT
        o.customer_id,
        SUM(l.quantity * l.unit_price) AS revenue
    FROM purchase_orders o
    JOIN order_lines l ON l.order_id = o.id
    GROUP BY o.customer_id
)
SELECT
    customer_id,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_revenue_rank
FROM customer_revenue
ORDER BY revenue DESC;
~~~

Khác biệt:

| Doanh thu | RANK | DENSE_RANK |
|---:|---:|---:|
| 900000 | 1 | 1 |
| 750000 | 2 | 2 |
| 750000 | 2 | 2 |
| 500000 | 4 | 3 |

`RANK` để lại khoảng trống sau nhóm đồng hạng. `DENSE_RANK` không để khoảng trống.

### 5.4. SUM OVER: tổng lũy kế

Tính doanh thu lũy kế theo thời gian:

~~~sql
SELECT
    o.id,
    o.created_at,
    SUM(l.quantity * l.unit_price) AS order_total,
    SUM(SUM(l.quantity * l.unit_price)) OVER (
        ORDER BY o.created_at, o.id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id, o.created_at
ORDER BY o.created_at, o.id;
~~~

Truy vấn nhóm các dòng hàng thành tổng theo đơn trước, rồi window function cộng dồn tổng đơn theo thứ tự. Window frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` nói rằng mỗi hàng tính từ hàng đầu tiên đến hàng hiện tại.

Nếu muốn tính tổng lũy kế riêng theo từng khách, thêm `PARTITION BY o.customer_id`.

### 5.5. LAG và LEAD: so sánh hàng trước/sau

`LAG` đọc giá trị từ hàng trước trong cửa sổ; `LEAD` đọc từ hàng sau:

~~~sql
SELECT
    customer_id,
    id AS order_id,
    created_at,
    LAG(created_at) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, id
    ) AS previous_order_at,
    LEAD(created_at) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, id
    ) AS next_order_at
FROM purchase_orders;
~~~

Ứng dụng có thể tính khoảng cách giữa các lần đặt hàng, tìm đơn trước/sau hoặc phân tích chuỗi sự kiện. Hàng đầu tiên không có hàng trước sẽ nhận NULL từ LAG nếu không truyền giá trị mặc định.

### 5.6. Window frame và thứ tự

Khi dùng aggregate function như `SUM` trong OVER, cần hiểu frame. Nếu chỉ viết:

~~~sql
SUM(amount) OVER (ORDER BY created_at)
~~~

quy tắc mặc định của window frame có thể tính theo nhóm peer cùng giá trị sort key, tùy SQL dialect. Nếu cần tổng lũy kế theo từng hàng, nên khai báo rõ `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` và thêm khóa phụ duy nhất trong ORDER BY.

Không nhầm:

- `ORDER BY` trong OVER quyết định cách hàm tính cửa sổ.
- `ORDER BY` ở cuối SELECT quyết định thứ tự hàng trả về cho client.

Nếu cần thứ tự hiển thị ổn định, vẫn phải có ORDER BY ở ngoài.

## 6. Kết hợp SQL tùy chỉnh với Spring Data JDBC

Spring Data JDBC có thể thực thi SQL thông qua repository hoặc Spring JDBC. Lựa chọn tùy vào cách ánh xạ kết quả và độ phức tạp của query.

### 6.1. Dùng `@Query` cho truy vấn gắn với repository

Ví dụ repository tìm đơn theo trạng thái:

~~~java
package com.example.orders.repository;

import java.util.List;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, customer_id, order_number, status, created_at
        FROM purchase_orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        """)
    List<PurchaseOrder> findByStatusSql(
        @Param("status") String status
    );
}
~~~

Ví dụ giả định mapping `PurchaseOrder` có các thuộc tính tương ứng với những cột được SELECT. Nếu aggregate có collection con, truy vấn tùy chỉnh trả root không tự động có nghĩa rằng các bảng con sẽ được tải như khi gọi `findById`; hãy xác định rõ kiểu kết quả và cách tải aggregate theo API/version đang dùng. Với query chỉ đọc báo cáo, DTO qua Spring JDBC thường minh bạch hơn.

### 6.2. Dùng `@Query` cho câu lệnh cập nhật

Với câu SQL thay đổi dữ liệu, Spring Data JDBC hỗ trợ `@Modifying`:

~~~java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :newStatus
    WHERE id = :id
    """)
int updateStatus(
    @Param("id") Long id,
    @Param("newStatus") String newStatus
);
~~~

`@Modifying` đánh dấu query thay đổi dữ liệu; kiểu trả về `int` cho biết số hàng bị tác động. Đây là cập nhật SQL trực tiếp, có thể bỏ qua các phương thức domain và các cơ chế lưu aggregate như optimistic locking nếu không tự xử lý. Không dùng kiểu query này để thay thế repository `save()` một cách tùy tiện khi cần bảo vệ invariant.

### 6.3. Dùng `NamedParameterJdbcTemplate` cho DTO và JOIN

Với kết quả báo cáo, DAO riêng thường dễ kiểm soát:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        LocalDateTime createdAt,
        long lineCount,
        BigDecimal totalAmount
) {
}
~~~

DAO:

~~~java
package com.example.orders.read;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReportDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReportDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findSummaries(
            LocalDateTime from,
            LocalDateTime to) {

        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                c.display_name AS customer_name,
                o.status,
                o.created_at,
                COUNT(l.id) AS line_count,
                COALESCE(
                    SUM(l.quantity * l.unit_price),
                    0
                ) AS total_amount
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN order_lines l ON l.order_id = o.id
            WHERE o.created_at >= :fromTime
              AND o.created_at < :toTime
            GROUP BY
                o.id,
                o.order_number,
                c.display_name,
                o.status,
                o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            """;

        Map<String, Object> params = Map.of(
            "fromTime", from,
            "toTime", to
        );

        return jdbc.query(sql, params, (rs, rowNum) ->
            new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("customer_name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
            )
        );
    }
}
~~~

DAO ánh xạ từng hàng SQL thành `OrderSummary`. Dữ liệu chỉ chứa các cột màn hình cần; không có ý định gọi `save()` trên DTO này.

### 6.4. Dùng window function trong DAO

Ví dụ lấy ba đơn mới nhất của mỗi khách:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.order_number,
        o.status,
        o.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.id DESC
        ) AS rn
    FROM purchase_orders o
)
SELECT
    id,
    customer_id,
    order_number,
    status,
    created_at
FROM ranked_orders
WHERE rn <= :limitPerCustomer
ORDER BY customer_id, created_at DESC, id DESC;
~~~

DAO có thể truyền `limitPerCustomer` qua named parameter. Đây là giá trị dữ liệu, không phải tên cột hay đoạn SQL được nối chuỗi.

Window function chạy trong database, vì vậy ứng dụng không cần tải mọi đơn về Java rồi nhóm và sắp xếp từng khách. Tuy nhiên, phải xác nhận database đích hỗ trợ cú pháp window function cần dùng.

## 7. Tham số hóa SQL và tránh SQL injection

Mọi giá trị do người dùng hoặc hệ thống bên ngoài cung cấp cần được bind qua parameter:

~~~java
String sql = """
    SELECT id, order_number
    FROM purchase_orders
    WHERE status = :status
      AND created_at >= :fromTime
    """;

Map<String, Object> params = Map.of(
    "status", requestedStatus,
    "fromTime", fromTime
);

List<Map<String, Object>> rows = jdbc.queryForList(sql, params);
~~~

Không nối trực tiếp giá trị vào SQL:

~~~java
// KHÔNG an toàn:
String sql = "SELECT * FROM purchase_orders WHERE status = '"
    + requestedStatus + "'";
~~~

Bind parameter bảo vệ giá trị dữ liệu và giúp driver xử lý kiểu đúng. Nhưng parameter **không thay thế được tên bảng, tên cột hoặc từ khóa SQL**. Nếu cần sort động, hãy dùng whitelist:

~~~java
String orderBy = switch (requestedSort) {
    case "created" -> "created_at";
    case "number" -> "order_number";
    case "status" -> "status";
    default -> "created_at";
};

String sql = """
    SELECT id, order_number, status
    FROM purchase_orders
    ORDER BY
    """ + orderBy + " DESC, id DESC";
~~~

Đoạn nối chuỗi trên chỉ dùng giá trị lấy từ whitelist cố định trong code. Không nối trực tiếp `requestedSort` từ request vào câu SQL. Tương tự, hướng ASC/DESC phải được kiểm tra bằng danh sách giá trị cho phép.

## 8. Phân trang, sắp xếp và kết quả ổn định

Với báo cáo nhiều hàng, cần phân trang ở database:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

Thứ tự có khóa phụ `id` để ổn định khi nhiều đơn cùng `created_at`. Nếu thiếu ORDER BY xác định, database không bảo đảm cùng thứ tự giữa các lần chạy.

OFFSET lớn có thể tốn chi phí vì database phải bỏ qua nhiều hàng. Với danh sách lớn, cân nhắc keyset pagination:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Client gửi cursor gồm thời gian và ID cuối trang trước. Index kết hợp phù hợp có thể giúp truy vấn trang tiếp theo hiệu quả hơn. Cần xử lý nhất quán timezone và độ chính xác timestamp giữa database với ứng dụng.

## 9. Chọn JOIN, subquery, GROUP BY hay window function?

| Nhu cầu | Kỹ thuật thường phù hợp | Ví dụ |
|---|---|---|
| Lấy tên khách cùng đơn hàng | JOIN | `purchase_orders JOIN customers` |
| Chỉ kiểm tra đơn có dòng hàng | EXISTS | Có ít nhất một `order_lines` |
| Lấy tổng tiền theo đơn | GROUP BY hoặc scalar subquery | `SUM(quantity * unit_price)` |
| Lọc nhóm theo số lượng | HAVING | Khách có từ 3 đơn |
| Lấy đơn mới nhất mỗi khách | ROW_NUMBER + CTE | `rn = 1` |
| Xếp hạng doanh thu | RANK/DENSE_RANK | Top khách hàng |
| Tính tổng lũy kế | SUM OVER | Doanh thu chạy theo ngày |
| So sánh với hàng trước | LAG | Khoảng cách giữa hai lần mua |
| Đọc DTO nhiều bảng | JdbcTemplate DAO | Báo cáo danh sách đơn |

Không có kỹ thuật nào luôn tốt nhất. Hãy chọn câu SQL thể hiện đúng quan hệ và cardinality, dễ bảo trì, rồi đo hiệu năng với dữ liệu gần thực tế.

## 10. Tối ưu truy vấn và kiểm tra execution plan

Một câu SQL ngắn không đảm bảo nhanh. Các yếu tố quan trọng gồm:

- Số lượng hàng phải đọc và trả về.
- Index trên các cột JOIN, WHERE và ORDER BY.
- Độ chọn lọc của điều kiện lọc.
- Cardinality của các quan hệ một-nhiều.
- Chi phí sort, group và window partition.
- Kích thước kết quả và số round-trip giữa ứng dụng với database.

Index minh họa cho các query phía trên:

~~~sql
CREATE INDEX idx_orders_status_created
    ON purchase_orders(status, created_at, id);

CREATE INDEX idx_orders_customer_created
    ON purchase_orders(customer_id, created_at, id);

CREATE INDEX idx_lines_order
    ON order_lines(order_id);
~~~

Đây chỉ là ví dụ. Thứ tự cột trong composite index cần dựa vào điều kiện lọc và thứ tự sắp xếp thực tế. Mỗi index làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE, nên không thêm index theo mọi cột.

Dùng công cụ execution plan của database, chẳng hạn `EXPLAIN` hoặc `EXPLAIN ANALYZE` ở hệ quản trị hỗ trợ. Kiểm tra:

1. Database có dùng index dự kiến không?
2. Có full table scan trên bảng lớn không?
3. JOIN có tạo nhiều hàng trung gian bất ngờ không?
4. GROUP BY hoặc ORDER BY có sort tốn kém không?
5. Window partition có xử lý tập dữ liệu quá lớn không?
6. Ước lượng hàng có khác xa số hàng thực tế không?

Không áp dụng cú pháp `EXPLAIN ANALYZE` giống nhau cho mọi database; hãy dùng tài liệu và công cụ của hệ quản trị đang chạy.

## 11. Khác biệt SQL giữa các hệ quản trị

Spring Data JDBC không làm cho mọi câu SQL trở nên portable. Các tính năng sau có thể khác nhau:

- Cú pháp phân trang (`LIMIT/OFFSET`, `FETCH FIRST`, `TOP`).
- Kiểu dữ liệu timestamp, UUID và decimal.
- Cách nối chuỗi, xử lý NULL và ép kiểu.
- Hỗ trợ CTE đệ quy hoặc window frame.
- Tên hàm, cú pháp JSON và hàm ngày tháng.
- Quy tắc quoting identifier và chữ hoa/thường của tên cột.

JOIN, GROUP BY và nhiều window function phổ biến có mặt trong các database hiện đại, nhưng vẫn cần xác nhận phiên bản database mục tiêu. Nếu ứng dụng hỗ trợ nhiều database, hãy giữ SQL ở phần dễ thay thế, viết integration test trên từng hệ quản trị được hỗ trợ và tránh phụ thuộc vào cú pháp riêng khi không cần thiết.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một đơn xuất hiện nhiều lần sau JOIN | Quan hệ một-nhiều làm nhân bản hàng | GROUP BY, subquery hoặc EXISTS tùy mục tiêu |
| Tổng tiền lớn hơn thực tế | JOIN nhiều collection làm nhân bản dòng | Tổng hợp từng bảng con trước khi JOIN |
| LEFT JOIN nhưng mất hàng không có quan hệ | Điều kiện bảng phải đặt trong WHERE | Chuyển điều kiện phù hợp vào ON |
| Đếm đơn không có dòng hàng thành 1 | Dùng COUNT(*) sau LEFT JOIN | Dùng COUNT(child.id) |
| WHERE báo lỗi khi dùng COUNT/SUM | Lọc aggregate ở sai giai đoạn | Dùng HAVING |
| NOT IN trả kết quả bất ngờ | Subquery có NULL | Dùng NOT EXISTS hoặc lọc NULL rõ ràng |
| Window function không lọc được trong WHERE cùng cấp | Window tính sau WHERE | Bọc query bằng CTE/subquery |
| Kết quả phân trang đổi thứ tự | ORDER BY không có khóa phụ ổn định | Thêm cột unique vào thứ tự |
| SQL injection qua bộ lọc/sort | Nối input vào SQL | Bind giá trị và whitelist identifier |
| DTO thiếu hoặc sai cột | Alias và RowMapper không khớp | Đặt alias rõ và ánh xạ theo tên |
| Query chậm khi dữ liệu tăng | Thiếu index hoặc cardinality lớn | Xem execution plan và tối ưu theo workload |

## 13. Bài tập thực hành

### Bài 1 — JOIN và DTO

1. JOIN đơn hàng với khách hàng để trả mã đơn, tên khách và trạng thái.
2. Thêm LEFT JOIN với dòng hàng.
3. Đếm số dòng hàng cho từng đơn.
4. Tạo DTO `OrderSummary` và ánh xạ bằng `NamedParameterJdbcTemplate`.
5. Tạo một đơn chưa có dòng hàng và xác nhận `lineCount` là 0.

### Bài 2 — Subquery và EXISTS

1. Tìm đơn có ít nhất một dòng số lượng lớn hơn 5 bằng EXISTS.
2. Tìm đơn không có dòng hàng bằng NOT EXISTS.
3. Viết lại truy vấn đầu bằng JOIN.
4. So sánh số hàng và ý nghĩa kết quả khi một đơn có nhiều dòng phù hợp.

### Bài 3 — Tổng hợp

1. Tính tổng tiền theo đơn.
2. Tính doanh thu theo khách hàng.
3. Chỉ lấy khách có doanh thu trên ngưỡng bằng HAVING.
4. So sánh COUNT(*) và COUNT(line.id) khi dùng LEFT JOIN.
5. Thêm COALESCE cho đơn chưa có dòng.

### Bài 4 — Window function

1. Dùng ROW_NUMBER để đánh số đơn theo từng khách.
2. Dùng CTE để lấy đơn mới nhất mỗi khách.
3. Dùng RANK và DENSE_RANK để xếp hạng doanh thu.
4. Dùng SUM OVER để tính tổng lũy kế theo ngày.
5. Dùng LAG để lấy ngày mua trước của mỗi khách.

### Bài 5 — Hiệu năng và tính ổn định

1. Tạo dữ liệu thử đủ lớn.
2. Chạy query có và không có index phù hợp.
3. Xem execution plan.
4. Phân trang bằng OFFSET và keyset.
5. Thêm dữ liệu có cùng timestamp và xác nhận ORDER BY có khóa phụ cho kết quả ổn định.

## 14. Nguyên tắc áp dụng trong ứng dụng Spring Data JDBC

Khi viết SQL tùy chỉnh, hãy giữ ranh giới rõ:

- **Command và thay đổi aggregate:** tải root, gọi hành vi domain và lưu bằng repository khi cần bảo vệ invariant.
- **Truy vấn đọc chuyên biệt:** dùng JOIN, subquery, aggregate function hoặc window function để trả DTO phù hợp.
- **SQL thay đổi trực tiếp:** dùng `@Modifying` hoặc Spring JDBC khi có lý do cụ thể; hiểu rằng câu lệnh đó có thể bỏ qua lifecycle và optimistic locking của aggregate.
- **Tham số:** bind giá trị; whitelist tên cột và hướng sort nếu cần động.
- **Hiệu năng:** kiểm tra cardinality, index, execution plan và kích thước kết quả.
- **Tính portable:** kiểm tra cú pháp với database và phiên bản thực tế.

## 15. Kết luận

JOIN kết hợp dữ liệu giữa các bảng; subquery cho phép dùng kết quả của truy vấn khác; aggregate function thu gọn nhiều hàng thành các giá trị tổng hợp; window function tính toán trên từng nhóm hàng mà vẫn giữ chi tiết của mỗi hàng. Đây là những công cụ quan trọng khi xây truy vấn SQL tùy chỉnh trong ứng dụng Spring Data JDBC.

Hãy dùng `@Query` cho SQL gắn với repository và kết quả mapping phù hợp; dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` cho JOIN, báo cáo và DTO phức tạp. Luôn hiểu cardinality để tránh nhân bản hàng và tổng tiền, dùng HAVING cho điều kiện trên nhóm, xử lý NULL cẩn thận, và khai báo thứ tự ổn định khi phân trang.

Repository tiếp tục là cổng truy cập aggregate cho nghiệp vụ ghi. SQL tùy chỉnh mở rộng khả năng đọc và tổng hợp dữ liệu mà không buộc mọi kết quả truy vấn phải trở thành aggregate có thể lưu ngược.
