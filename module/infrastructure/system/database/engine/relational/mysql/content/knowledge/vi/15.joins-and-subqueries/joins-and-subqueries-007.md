# Scalar subquery và điều kiện trả về tối đa một dòng

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết scalar subquery và phân biệt nó với subquery trả về nhiều hàng hoặc nhiều cột.
- Giải thích hành vi khi subquery trả về 0, 1 hoặc nhiều hơn 1 hàng.
- Xử lý lỗi `Subquery returns more than 1 row` và lỗi subquery trả về nhiều cột.
- Bảo đảm truy vấn con trả về tối đa một hàng bằng khóa duy nhất, hàm tổng hợp hoặc `ORDER BY ... LIMIT 1`.
- Viết correlated scalar subquery trong `SELECT`, `WHERE` và các biểu thức khác.
- Xử lý `NULL`, kiểm tra tính duy nhất và chọn giữa scalar subquery, `IN`, `EXISTS` hoặc `JOIN`.
- Đánh giá hiệu năng bằng index và `EXPLAIN`.

## 1. Scalar subquery là gì?

Scalar subquery là truy vấn con được dùng tại vị trí cần một giá trị đơn. Nó phải trả về đúng một cột và không được trả về nhiều hơn một hàng. Giá trị của hàng đó trở thành kết quả của biểu thức.

Ví dụ, lấy tên khách hàng có mã 101:

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = 101) AS customer_name;
```

Nếu `customer_id` là primary key, truy vấn con có thể tìm tối đa một khách hàng. Kết quả là tên khách hàng đó; nếu không có khách hàng mã 101, kết quả scalar là `NULL`.

Scalar subquery có thể được dùng ở nhiều vị trí cần một biểu thức đơn:

- Trong danh sách `SELECT` để tạo một cột kết quả.
- Trong điều kiện `WHERE` hoặc `HAVING` để so sánh với một giá trị.
- Trong biểu thức tính toán, `CASE`, `COALESCE()` hoặc phép gán.
- Trong các câu lệnh `INSERT`, `UPDATE` nếu ngữ cảnh và quy tắc của câu lệnh cho phép.

Ví dụ:

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > (
    SELECT AVG(price)
    FROM products
);
```

Truy vấn con tính giá trung bình của toàn bộ sản phẩm; truy vấn ngoài lấy các sản phẩm có giá cao hơn giá trị scalar đó.

## 2. Quy tắc số hàng và số cột của scalar subquery

Scalar subquery phải trả về một cột. Số hàng có ba trường hợp:

| Số hàng subquery trả về | Hành vi |
|---:|---|
| 0 hàng | Giá trị scalar được xem là `NULL` |
| 1 hàng | Giá trị của cột duy nhất trong hàng đó |
| Nhiều hơn 1 hàng | MySQL báo lỗi `1242: Subquery returns more than 1 row` |

Nếu subquery trả về nhiều hơn một cột trong ngữ cảnh scalar, MySQL báo lỗi `1241: Operand should contain 1 column(s)`.

### 2.1. Không có hàng: kết quả là NULL

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = -1) AS customer_name;
```

Nếu không có khách hàng mang mã `-1`, biểu thức trả về `NULL`. Câu truy vấn ngoài vẫn có thể trả về một hàng vì subquery chỉ là một biểu thức trong danh sách `SELECT`.

### 2.2. Có đúng một hàng: nhận giá trị

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = 101) AS customer_name;
```

Nếu có đúng một khách hàng phù hợp, biểu thức nhận giá trị `full_name` của hàng đó.

### 2.3. Nhiều hàng: lỗi 1242

```sql
SELECT
    (SELECT status
     FROM orders
     WHERE customer_id = 101) AS one_status;
```

Một khách hàng có thể có nhiều đơn hàng, vì vậy subquery có thể trả về nhiều trạng thái. Trong ngữ cảnh scalar, MySQL không tự chọn một hàng và cũng không tự nối các giá trị; câu lệnh thất bại với lỗi 1242.

### 2.4. Nhiều cột: lỗi 1241

```sql
-- Không hợp lệ trong ngữ cảnh scalar
SELECT (
    SELECT customer_id, full_name
    FROM customers
    WHERE customer_id = 101
);
```

Scalar subquery chỉ được trả về một cột. Nếu cần nhiều cột từ hàng liên quan, hãy dùng `JOIN` hoặc một cấu trúc truy vấn trả về hàng thay vì cố đặt nhiều cột vào một scalar expression.

### 2.5. Một hàng có giá trị NULL cũng cho kết quả NULL

Nếu subquery tìm được một hàng nhưng cột được chọn là `NULL`, kết quả scalar cũng là `NULL`. Vì vậy, chỉ nhìn kết quả scalar là `NULL` thì không thể phân biệt chắc chắn giữa hai tình huống:

- Không tìm thấy hàng nào.
- Có một hàng nhưng giá trị cột là `NULL`.

Nếu nghiệp vụ cần phân biệt, hãy kiểm tra thêm `EXISTS()` hoặc trả về một dấu hiệu hiện diện cùng giá trị bằng `JOIN`.

## 3. Bảo đảm tối đa một hàng bằng khóa duy nhất

Cách tốt nhất khi nghiệp vụ yêu cầu một bản ghi duy nhất là biểu diễn quy tắc đó trong schema bằng `PRIMARY KEY` hoặc `UNIQUE`.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;
```

Tra cứu bằng primary key:

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = 101) AS customer_name;
```

Tra cứu bằng unique key:

```sql
SELECT
    (SELECT customer_id
     FROM customers
     WHERE email = 'an@example.com') AS customer_id;
```

Vì `email` có unique constraint, điều kiện bằng với một email không NULL có thể khớp tối đa một hàng theo collation của cột.

### 3.1. Lưu ý UNIQUE và NULL

Trong MySQL, unique index cho phép nhiều hàng có giá trị `NULL` ở cột nullable. Vì vậy, unique constraint không bảo đảm chỉ có một hàng khi truy vấn dùng `IS NULL` trên cột đó.

Ví dụ:

```sql
CREATE TABLE external_accounts (
    account_id BIGINT NOT NULL AUTO_INCREMENT,
    external_code VARCHAR(80) NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_external_code (external_code)
);

INSERT INTO external_accounts (external_code)
VALUES (NULL), (NULL);
```

Hai hàng có thể cùng tồn tại với `external_code IS NULL`. Vì vậy, subquery sau có thể trả nhiều hàng:

```sql
SELECT (
    SELECT account_id
    FROM external_accounts
    WHERE external_code IS NULL
);
```

Đừng suy luận rằng `UNIQUE` luôn bảo đảm một hàng cho mọi điều kiện. Hãy xét tính nullable, phép so sánh và tất cả cột của unique key.

### 3.2. Collation cũng quyết định tính duy nhất

Với unique key trên chuỗi, collation ảnh hưởng hai giá trị có được coi là bằng nhau hay không. Nếu cột dùng collation không phân biệt hoa thường, `An@example.com` và `an@example.com` có thể xung đột unique key. Điều này cũng ảnh hưởng việc scalar subquery tra cứu theo chuỗi.

Khi thiết kế unique key, xác định rõ quy tắc case/accent sensitivity và chuẩn hóa dữ liệu theo cùng quy tắc ở ứng dụng.

## 4. Bảo đảm một hàng bằng hàm tổng hợp

Hàm tổng hợp không có `GROUP BY` thường trả về một hàng cho toàn bộ tập đầu vào, kể cả khi không có hàng nguồn phù hợp. Đây là cách hữu ích để tạo scalar value.

### 4.1. MAX, MIN, AVG và SUM

```sql
SELECT
    customer_id,
    (SELECT MAX(total_amount)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS largest_order,
    (SELECT AVG(total_amount)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS average_order
FROM customers AS c;
```

Mỗi subquery có hàm tổng hợp và không có `GROUP BY`, nên tạo một hàng kết quả cho mỗi khách hàng ở truy vấn ngoài.

Nếu khách hàng chưa có đơn:

- `MAX()` và `MIN()` trả `NULL`.
- `AVG()` trả `NULL`.
- `SUM()` trả `NULL`.
- `COUNT(*)` trả `0`.

Ví dụ:

```sql
SELECT
    (SELECT COUNT(*)
     FROM orders
     WHERE customer_id = 9999) AS order_count,
    (SELECT MAX(total_amount)
     FROM orders
     WHERE customer_id = 9999) AS largest_order;
```

Nếu khách hàng không có đơn, `order_count` là 0 và `largest_order` là NULL.

### 4.2. GROUP BY có thể làm subquery trả nhiều hàng

Không phải cứ dùng hàm tổng hợp là chắc chắn có một hàng:

```sql
-- Có thể trả nhiều hàng vì nhóm theo status
SELECT (
    SELECT COUNT(*)
    FROM orders
    WHERE customer_id = 101
    GROUP BY status
);
```

Nếu khách hàng có đơn ở nhiều trạng thái, subquery tạo một hàng cho mỗi trạng thái và lỗi 1242 xảy ra. Nếu muốn tổng số đơn, bỏ `GROUP BY status`. Nếu muốn số đơn theo từng trạng thái, dùng truy vấn trả về nhiều hàng hoặc JOIN với derived table.

### 4.3. HAVING có thể loại bỏ hàng tổng hợp

Một truy vấn aggregate không có `GROUP BY` thường tạo một hàng, nhưng `HAVING` vẫn có thể loại hàng đó:

```sql
SELECT (
    SELECT MAX(total_amount)
    FROM orders
    WHERE customer_id = 101
    HAVING COUNT(*) > 0
);
```

Nếu khách hàng không có đơn, `HAVING COUNT(*) > 0` loại kết quả aggregate, khiến subquery trả 0 hàng và scalar trở thành NULL. Hãy hiểu rõ điều kiện `HAVING` khi dựa vào tính chất một hàng của aggregate.

## 5. Chọn một hàng có chủ đích bằng ORDER BY và LIMIT 1

Khi cần lấy bản ghi mới nhất, cũ nhất, có ưu tiên cao nhất hoặc theo một quy tắc xếp hạng, có thể dùng `ORDER BY ... LIMIT 1`.

Ví dụ lấy trạng thái mới nhất của mỗi đơn hàng:

```sql
SELECT
    o.order_id,
    (
        SELECT h.status
        FROM order_status_history AS h
        WHERE h.order_id = o.order_id
        ORDER BY h.changed_at DESC, h.history_id DESC
        LIMIT 1
    ) AS latest_status
FROM orders AS o;
```

`LIMIT 1` bảo đảm subquery trả tối đa một hàng. `history_id DESC` là tie-breaker khi nhiều sự kiện có cùng `changed_at`, giúp kết quả xác định.

### 5.1. LIMIT 1 không thay thế quy tắc nghiệp vụ

Ví dụ:

```sql
SELECT (
    SELECT status
    FROM orders
    WHERE customer_id = 101
    LIMIT 1
);
```

Câu lệnh không lỗi 1242, nhưng nếu khách hàng có nhiều đơn, MySQL được phép chọn một hàng mà không có thứ tự nghiệp vụ xác định. Kết quả có thể thay đổi theo execution plan hoặc trạng thái dữ liệu.

Nếu muốn đơn mới nhất, hãy viết:

```sql
SELECT (
    SELECT status
    FROM orders
    WHERE customer_id = 101
    ORDER BY created_at DESC, order_id DESC
    LIMIT 1
);
```

Nếu muốn đơn có giá trị lớn nhất, dùng `ORDER BY total_amount DESC, order_id DESC LIMIT 1` hoặc `MAX(total_amount)` tùy mục đích. `MAX()` chỉ trả giá trị lớn nhất; `ORDER BY ... LIMIT 1` có thể lấy thêm các cột của chính hàng được chọn.

### 5.2. OFFSET 0 và cú pháp giới hạn

Trong subquery, cú pháp thông dụng là `ORDER BY ... LIMIT 1`. `LIMIT 1 OFFSET 0` tương đương nhưng không cần thiết. Nếu dùng `LIMIT 1` mà không có `ORDER BY`, kết quả chỉ được giới hạn số lượng, không xác định hàng được chọn.

### 5.3. LIMIT 1 có thể che dữ liệu trùng

Nếu nghiệp vụ yêu cầu email hoặc mã ngoài phải duy nhất, đừng dùng `LIMIT 1` để làm cho truy vấn chạy qua khi dữ liệu bị trùng. Làm như vậy che giấu vi phạm toàn vẹn dữ liệu và chọn một bản ghi tùy ý.

Hãy kiểm tra duplicate và sửa schema bằng unique constraint nếu phù hợp. Chỉ dùng `LIMIT 1` khi nghiệp vụ thực sự muốn chọn một hàng theo thứ tự đã xác định, chẳng hạn sự kiện mới nhất.

## 6. Correlated scalar subquery

Correlated subquery tham chiếu tới cột của truy vấn bên ngoài. Với mỗi hàng ngoài, truy vấn con sử dụng giá trị của hàng đó để tính kết quả.

Ví dụ lấy số đơn của từng khách hàng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c;
```

`c.customer_id` là tham chiếu từ query ngoài. Subquery được viết theo từng khách hàng và trả về một scalar count.

### 6.1. So sánh với giá trị trung bình của chính nhóm

Lấy các đơn có giá cao hơn mức trung bình của khách hàng tương ứng:

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.total_amount
FROM orders AS o
WHERE o.total_amount > (
    SELECT AVG(o2.total_amount)
    FROM orders AS o2
    WHERE o2.customer_id = o.customer_id
);
```

Subquery tính trung bình cho `customer_id` của hàng ngoài. Vì `AVG()` không có `GROUP BY`, mỗi lần đánh giá trả một hàng. Nếu giá trị trung bình là NULL, phép so sánh `>` cho kết quả UNKNOWN và hàng không được chọn.

### 6.2. Lấy hàng mới nhất theo từng nhóm

```sql
SELECT
    c.customer_id,
    c.full_name,
    (
        SELECT o.order_id
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_order_id
FROM customers AS c;
```

Khách hàng chưa có đơn nhận `NULL` cho `latest_order_id`. Mỗi khách hàng vẫn có một hàng trong kết quả vì truy vấn ngoài bắt đầu từ `customers`.

### 6.3. Phân biệt correlated và non-correlated

Non-correlated subquery không tham chiếu cột của truy vấn ngoài:

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > (
    SELECT AVG(price)
    FROM products
);
```

Correlated subquery có tham chiếu như `o.customer_id = c.customer_id`. Optimizer có thể biến đổi hoặc tối ưu một số dạng subquery, nên không nên kết luận rằng mọi correlated subquery chắc chắn chạy lại toàn bộ truy vấn con độc lập cho từng hàng. Hãy xem execution plan và đo thực tế.

## 7. Scalar subquery trong SELECT, WHERE và HAVING

### 7.1. Trong danh sách SELECT

```sql
SELECT
    p.product_id,
    p.product_name,
    p.price,
    (SELECT AVG(price) FROM products) AS overall_average_price
FROM products AS p;
```

Mỗi hàng sản phẩm hiển thị thêm giá trung bình toàn bảng. Subquery không correlated nên cùng một giá trị được dùng cho các hàng kết quả.

### 7.2. Trong WHERE

```sql
SELECT product_id, product_name, price
FROM products
WHERE price = (
    SELECT MAX(price)
    FROM products
);
```

Truy vấn lấy sản phẩm có giá bằng mức giá cao nhất. Có thể có nhiều sản phẩm cùng giá cao nhất; điều đó không gây lỗi vì scalar subquery chỉ trả về một giá trị MAX, còn query ngoài có thể trả nhiều hàng.

### 7.3. Trong HAVING

```sql
SELECT
    customer_id,
    SUM(total_amount) AS customer_revenue
FROM orders
GROUP BY customer_id
HAVING SUM(total_amount) > (
    SELECT AVG(customer_total)
    FROM (
        SELECT SUM(total_amount) AS customer_total
        FROM orders
        GROUP BY customer_id
    ) AS customer_totals
);
```

Subquery dẫn xuất tính doanh thu từng khách hàng; scalar subquery bên ngoài lấy trung bình các tổng đó. Derived table cần alias (`customer_totals`) trong MySQL.

## 8. NULL và phép so sánh với scalar subquery

Nếu scalar subquery trả về NULL, các phép so sánh thông thường thường cho UNKNOWN:

```sql
SELECT product_id, product_name
FROM products
WHERE price > (
    SELECT MAX(price)
    FROM products
    WHERE category_id = -1
);
```

Nếu không có sản phẩm trong category `-1`, `MAX(price)` là NULL. `price > NULL` không phải TRUE nên truy vấn không trả hàng.

### 8.1. Dùng COALESCE khi có giá trị thay thế hợp lệ

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > COALESCE(
    (SELECT AVG(price)
     FROM products
     WHERE category_id = 10),
    0
);
```

Ví dụ này thay NULL bằng 0. Chỉ dùng khi 0 là giá trị thay thế đúng theo nghiệp vụ. Không dùng `COALESCE(..., 0)` một cách máy móc vì nó có thể biến trường hợp “không có dữ liệu” thành một con số có ý nghĩa khác.

### 8.2. Phân biệt không có hàng và giá trị NULL

Vì scalar subquery trả NULL trong cả hai trường hợp, có thể dùng `EXISTS` song song:

```sql
SELECT
    c.customer_id,
    EXISTS (
        SELECT 1
        FROM customer_profiles AS p
        WHERE p.customer_id = c.customer_id
    ) AS profile_exists,
    (
        SELECT p.nickname
        FROM customer_profiles AS p
        WHERE p.customer_id = c.customer_id
    ) AS nickname
FROM customers AS c;
```

Nếu `profile_exists = 0`, không có profile. Nếu `profile_exists = 1` nhưng `nickname IS NULL`, có profile nhưng nickname chưa được cung cấp. Để bảo đảm scalar thứ hai không lỗi, `customer_profiles.customer_id` phải được bảo đảm duy nhất, chẳng hạn bằng primary key hoặc unique constraint.

### 8.3. Không dùng = NULL

Nếu muốn kiểm tra scalar result có NULL hay không, dùng `IS NULL`:

```sql
SELECT product_id
FROM products
WHERE (
    SELECT MAX(price)
    FROM products
    WHERE category_id = 10
) IS NULL;
```

Không viết `= NULL`, vì phép so sánh thông thường với NULL trả UNKNOWN.

## 9. Khi nào dùng scalar subquery, IN, EXISTS hoặc JOIN?

Các dạng truy vấn con không thể thay thế nhau trong mọi tình huống:

| Cấu trúc | Kỳ vọng kết quả subquery | Dùng khi |
|---|---|---|
| Scalar subquery | Một cột, tối đa một hàng | Cần một giá trị đơn như MAX, AVG, tên theo khóa duy nhất hoặc hàng top-1 |
| `IN (subquery)` | Một cột, có thể nhiều hàng | Kiểm tra giá trị có nằm trong một tập giá trị không |
| `EXISTS (subquery)` | Kiểm tra có hàng phù hợp hay không | Chỉ cần biết quan hệ có tồn tại |
| `JOIN` | Ghép các hàng và có thể lấy nhiều cột | Cần dữ liệu từ cả hai bảng hoặc xử lý quan hệ hàng với hàng |

### 9.1. Scalar subquery so với IN

Không dùng `=` với subquery có thể trả nhiều hàng:

```sql
-- Có thể lỗi 1242 nếu một khách hàng có nhiều đơn
SELECT customer_id
FROM customers
WHERE customer_id = (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

Nếu mục tiêu là lấy khách hàng có ít nhất một đơn đã thanh toán, dùng `IN`:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

Hoặc dùng `EXISTS`, thường diễn đạt rõ quan hệ tương quan:

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

### 9.2. Scalar subquery so với JOIN

Nếu cần lấy nhiều cột từ hàng mới nhất, một scalar subquery cho mỗi cột có thể làm truy vấn khó đọc và lặp logic. Có thể dùng derived table hoặc window function tùy phiên bản.

Ví dụ với `ROW_NUMBER()` trên MySQL 8.0:

```sql
WITH ranked_history AS (
    SELECT
        h.order_id,
        h.status,
        h.changed_at,
        ROW_NUMBER() OVER (
            PARTITION BY h.order_id
            ORDER BY h.changed_at DESC, h.history_id DESC
        ) AS rn
    FROM order_status_history AS h
)
SELECT
    o.order_id,
    rh.status AS latest_status,
    rh.changed_at AS latest_changed_at
FROM orders AS o
LEFT JOIN ranked_history AS rh
  ON rh.order_id = o.order_id
 AND rh.rn = 1;
```

`JOIN` phù hợp khi cần nhiều cột của hàng được chọn. Scalar subquery phù hợp khi chỉ cần một giá trị và biểu thức vẫn dễ đọc.

### 9.3. Cẩn thận với NOT IN và NULL

Nếu subquery của `NOT IN` trả về một giá trị NULL, phép kiểm tra có thể thành UNKNOWN và làm truy vấn không trả các hàng như mong đợi. Khi kiểm tra “không tồn tại hàng liên quan”, `NOT EXISTS` thường dễ kiểm soát hơn:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Đây là phép kiểm tra tồn tại, không phải scalar subquery. Chọn cấu trúc theo ý nghĩa logic thay vì chỉ theo hình thức viết ngắn.

## 10. Hiệu năng và index cho scalar subquery

Scalar subquery có thể rất hiệu quả nếu điều kiện tìm kiếm dùng index và chỉ cần đọc một giá trị. Nhưng correlated subquery trên tập ngoài lớn có thể tạo nhiều lần tra cứu; cần xem kế hoạch thực thi.

### 10.1. Index cho tra cứu theo khóa ngoại

Ví dụ đếm đơn theo khách hàng:

```sql
SELECT
    c.customer_id,
    (SELECT COUNT(*)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS order_count
FROM customers AS c;
```

Index trên `orders(customer_id)` có thể giúp tìm các đơn của từng khách hàng. InnoDB thường yêu cầu index phù hợp cho foreign key, nhưng nếu không có constraint hoặc schema khác, hãy kiểm tra index thực tế.

### 10.2. Index cho hàng mới nhất

Với subquery:

```sql
SELECT h.status
FROM order_status_history AS h
WHERE h.order_id = ?
ORDER BY h.changed_at DESC, h.history_id DESC
LIMIT 1;
```

Một index phù hợp có thể là:

```sql
CREATE INDEX idx_history_order_changed_id
ON order_status_history (order_id, changed_at DESC, history_id DESC);
```

Index đặt cột lọc bằng `order_id` trước, sau đó là các cột sắp xếp. MySQL 8.0 hỗ trợ descending index; hãy kiểm tra kế hoạch và hiệu quả trên phiên bản mục tiêu.

### 10.3. Index cho MAX theo nhóm

Với:

```sql
SELECT MAX(total_amount)
FROM orders
WHERE customer_id = ?;
```

Index `(customer_id, total_amount)` có thể hỗ trợ tìm giá trị lớn nhất trong phạm vi khách hàng. Optimizer có thể áp dụng chiến lược tối ưu MIN/MAX khi điều kiện phù hợp, nhưng không nên giả định mọi truy vấn aggregate đều chỉ đọc một entry. Dùng `EXPLAIN` và đo thực tế.

### 10.4. Kiểm tra kế hoạch thực thi

```sql
EXPLAIN
SELECT
    c.customer_id,
    (
        SELECT h.status
        FROM order_status_history AS h
        WHERE h.order_id = o.order_id
        ORDER BY h.changed_at DESC, h.history_id DESC
        LIMIT 1
    ) AS latest_status
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

Quan sát cách truy cập bảng ngoài và bảng trong, index được chọn, số hàng ước lượng và loại subquery. Tên cột/alias trong ví dụ được thiết kế để minh họa; schema thực tế cần có các khóa tương ứng.

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho các câu SELECT phù hợp. Lệnh này thực sự thực thi truy vấn để đo số hàng và thời gian, nên thử trên dữ liệu và môi trường phù hợp trước khi dùng với truy vấn nặng trong production.

### 10.5. Khi nào nên chuyển sang JOIN hoặc tổng hợp trước?

Nếu correlated scalar subquery chạy trên hàng trăm nghìn hàng ngoài và mỗi lần tra cứu đều quét nhiều dữ liệu, cân nhắc:

- Tạo index cho điều kiện tương quan.
- Tổng hợp dữ liệu con theo khóa trong derived table rồi JOIN.
- Dùng window function để xếp hạng hàng theo nhóm trên MySQL 8.0.
- Tách truy vấn thành bước lấy tập khóa cần thiết rồi mới tra cứu chi tiết.

Không chuyển mọi scalar subquery thành JOIN theo máy móc. Optimizer có thể tối ưu scalar subquery tốt; hãy so sánh execution plan, số hàng thực tế và latency trước khi đổi cấu trúc.

## 11. Các lỗi thường gặp và cách xử lý

| Lỗi/tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Subquery returns more than 1 row` (1242) | Subquery dùng ở ngữ cảnh scalar nhưng trả nhiều hàng | Xác minh tính duy nhất; dùng aggregate, `ORDER BY ... LIMIT 1`, `IN`, `EXISTS` hoặc JOIN theo mục tiêu |
| `Operand should contain 1 column(s)` (1241) | Scalar subquery trả nhiều cột | Chỉ chọn một biểu thức hoặc chuyển sang JOIN |
| Dùng LIMIT 1 nhưng kết quả thay đổi | Không có ORDER BY hoặc tie-breaker duy nhất | Khai báo thứ tự nghiệp vụ đầy đủ |
| Dùng LIMIT 1 để che duplicate | Dữ liệu vi phạm quy tắc duy nhất | Kiểm tra duplicate và thêm unique constraint nếu phù hợp |
| So sánh với subquery NULL không cho hàng nào | Subquery không có hàng hoặc aggregate trả NULL; phép so sánh thành UNKNOWN | Xác định ngữ nghĩa NULL, dùng `IS NULL`, `COALESCE` hoặc `EXISTS` khi cần |
| UNIQUE nhưng subquery `IS NULL` trả nhiều hàng | MySQL cho phép nhiều NULL trong unique index | Đặt `NOT NULL` nếu nghiệp vụ yêu cầu hoặc xử lý NULL riêng |
| Correlated subquery chậm | Điều kiện tương quan thiếu index hoặc nhiều lần tra cứu | Kiểm tra `EXPLAIN`, tạo index phù hợp hoặc so sánh với JOIN/derived table |
| GROUP BY làm scalar subquery trả nhiều hàng | Có nhiều nhóm kết quả | Bỏ GROUP BY nếu cần tổng hợp toàn tập hoặc đổi sang truy vấn nhiều hàng |

## 12. Quy trình thiết kế scalar subquery an toàn

1. **Xác định giá trị cần lấy:** một con số tổng hợp, một thuộc tính duy nhất hay một hàng theo thứ tự ưu tiên?
2. **Xác định cardinality:** điều kiện có được bảo vệ bởi primary key/unique key không? Có thể có nhiều hàng phù hợp không?
3. **Chọn cách bảo đảm một hàng:** unique constraint, aggregate không GROUP BY hoặc `ORDER BY ... LIMIT 1` với thứ tự rõ ràng.
4. **Xử lý trường hợp không có dữ liệu:** chấp nhận NULL, thay bằng giá trị nghiệp vụ qua `COALESCE()` hay cần phân biệt bằng `EXISTS`?
5. **Xem xét NULL trong khóa:** unique key nullable có thể cho phép nhiều NULL.
6. **Chọn đúng loại subquery:** scalar cho một giá trị; `IN` cho tập giá trị; `EXISTS` cho kiểm tra hiện diện; JOIN cho nhiều cột/hàng liên quan.
7. **Tạo index phù hợp:** ưu tiên điều kiện tương quan và thứ tự lấy hàng.
8. **Kiểm tra execution plan:** dùng `EXPLAIN`, đo với dữ liệu có quy mô tương đương production.
9. **Kiểm thử biên:** không có hàng, một hàng, nhiều hàng, cột NULL, dữ liệu trùng và các giá trị sort bằng nhau.

## 13. Bộ truy vấn thực hành

Các truy vấn sau dùng schema minh họa `customers`, `orders` và `order_status_history`.

### Bài 1: Lấy tổng số đơn của từng khách hàng

```sql
SELECT
    c.customer_id,
    c.full_name,
    (SELECT COUNT(*)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS order_count
FROM customers AS c
ORDER BY c.customer_id;
```

### Bài 2: Lấy đơn có giá trị lớn nhất của từng khách hàng

```sql
SELECT
    c.customer_id,
    (SELECT MAX(o.total_amount)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS largest_order_amount
FROM customers AS c;
```

### Bài 3: Lấy mã đơn mới nhất của từng khách hàng

```sql
SELECT
    c.customer_id,
    (SELECT o.order_id
     FROM orders AS o
     WHERE o.customer_id = c.customer_id
     ORDER BY o.created_at DESC, o.order_id DESC
     LIMIT 1) AS latest_order_id
FROM customers AS c;
```

### Bài 4: Lấy sản phẩm có giá cao hơn trung bình toàn bộ

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > (SELECT AVG(price) FROM products);
```

### Bài 5: Tìm khách hàng chưa có đơn hàng

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Bài 5 dùng `NOT EXISTS` vì mục tiêu là kiểm tra không có hàng liên quan; không cần ép subquery thành scalar.

## 14. Checklist trước khi đưa vào production

- [ ] Subquery trả về đúng một cột trong ngữ cảnh scalar.
- [ ] Đã xác minh subquery trả tối đa một hàng bằng constraint hoặc logic truy vấn.
- [ ] Nếu dùng `LIMIT 1`, đã có `ORDER BY` và tie-breaker duy nhất.
- [ ] Không dùng `LIMIT 1` để che dữ liệu trùng trái với nghiệp vụ.
- [ ] Đã xác định kết quả khi subquery không có hàng hoặc trả giá trị NULL.
- [ ] Đã xét trường hợp unique key cho phép nhiều NULL.
- [ ] Đã chọn scalar, `IN`, `EXISTS` hay JOIN theo đúng ngữ nghĩa.
- [ ] Correlated subquery có index hỗ trợ điều kiện tra cứu.
- [ ] Đã kiểm tra `EXPLAIN` và đo với dữ liệu thực tế.
- [ ] Đã kiểm thử trường hợp 0, 1 và nhiều hàng, gồm giá trị trùng và NULL.

## 15. Kết luận

Scalar subquery cung cấp một giá trị cho biểu thức SQL. Nó phải trả về một cột và tối đa một hàng: không có hàng thì kết quả là NULL, một hàng thì lấy giá trị, nhiều hàng gây lỗi 1242 và nhiều cột gây lỗi 1241.

Hãy dùng primary key/unique constraint khi nghiệp vụ yêu cầu duy nhất, aggregate không `GROUP BY` khi cần một giá trị tổng hợp, hoặc `ORDER BY ... LIMIT 1` khi thật sự muốn chọn một hàng theo thứ tự xác định. Kiểm soát NULL, phân biệt scalar với `IN`/`EXISTS`/JOIN và đo correlated subquery bằng execution plan để truy vấn vừa đúng dữ liệu vừa vận hành hiệu quả.
