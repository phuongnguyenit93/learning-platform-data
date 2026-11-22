# Chọn JOIN hay truy vấn con theo ngữ nghĩa và kế hoạch thực thi

Trong MySQL, `JOIN` và truy vấn con (subquery) đều có thể kết hợp dữ liệu từ nhiều bảng. Tuy nhiên, chúng biểu đạt những ý định khác nhau: `JOIN` tạo các hàng kết hợp từ hai nguồn; `EXISTS` kiểm tra sự tồn tại; `IN` kiểm tra một giá trị có thuộc tập kết quả hay không; truy vấn con vô hướng cung cấp một giá trị; còn derived table tạo một tập kết quả trung gian để truy vấn bên ngoài tiếp tục xử lý.

Không có quy tắc chung rằng `JOIN` luôn nhanh hơn subquery hoặc `EXISTS` luôn nhanh hơn `IN`. MySQL optimizer có thể biến đổi nhiều dạng truy vấn sang cùng một chiến lược thực thi, chẳng hạn semijoin, materialization hoặc nested-loop/hash join. Cách chọn đúng bắt đầu từ **ngữ nghĩa và số hàng cần trả về**, sau đó mới đọc kế hoạch thực thi, index và số hàng thực tế.

## 1. Mô hình dữ liệu dùng trong bài

Các ví dụ dùng hệ thống khách hàng, đơn hàng và phiếu hỗ trợ. Mỗi khách hàng có thể có nhiều đơn hàng và nhiều phiếu hỗ trợ:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;

CREATE TABLE support_tickets (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    priority VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_tickets_customer_priority (customer_id, priority),
    CONSTRAINT fk_tickets_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;
```

Các index trên chỉ là điểm bắt đầu cho những truy vấn minh họa. Trong hệ thống thật, hãy chọn thứ tự cột dựa trên điều kiện lọc, join key, phân bố dữ liệu và workload thực tế.

## 2. Khác biệt ngữ nghĩa: kết hợp hàng hay kiểm tra sự tồn tại?

Giả sử cần lấy danh sách khách hàng có ít nhất một đơn hàng đã thanh toán. Có hai cách viết phổ biến:

```sql
-- JOIN: kết hợp khách hàng với từng đơn hàng phù hợp
SELECT c.id, c.name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
WHERE o.status = 'paid';
```

```sql
-- EXISTS: chỉ kiểm tra có ít nhất một đơn hàng phù hợp
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

Hai câu lệnh không luôn trả về cùng số hàng. Nếu một khách hàng có ba đơn hàng đã thanh toán, `JOIN` trả khách hàng đó ba lần; `EXISTS` trả khách hàng một lần vì điều kiện chỉ cần đúng ít nhất một lần.

| Nhu cầu | Cách viết thường phù hợp | Ngữ nghĩa |
| --- | --- | --- |
| Cần thông tin từng đơn hàng cùng khách hàng | `JOIN` | Một hàng kết quả cho mỗi cặp khách hàng/đơn hàng |
| Cần danh sách khách hàng có đơn hàng phù hợp | `EXISTS` | Mỗi hàng khách hàng xuất hiện tối đa một lần |
| Cần danh sách khách hàng không có đơn hàng phù hợp | `NOT EXISTS` | Giữ khách hàng không tìm thấy hàng khớp |
| Cần lấy một giá trị tính toán từ bảng khác | Scalar subquery hoặc derived table | Tùy số hàng và phạm vi tính toán |

Không thêm `DISTINCT` vào truy vấn `JOIN` chỉ để chữa duplicate trước khi xác định duplicate đó có phải là kết quả đúng theo nghiệp vụ hay không. Nếu chỉ cần kiểm tra sự tồn tại, `EXISTS` thể hiện ý định rõ hơn.

## 3. JOIN: khi cần dữ liệu từ cả hai phía

Dùng `JOIN` khi các cột của cả hai bảng đều cần xuất hiện trong kết quả, hoặc khi mỗi cặp hàng kết hợp là một đơn vị dữ liệu có ý nghĩa.

Ví dụ hiển thị từng đơn hàng cùng tên khách hàng:

```sql
SELECT
    o.id AS order_id,
    o.created_at,
    o.total_amount,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders AS o
JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.status = 'paid'
ORDER BY o.created_at DESC, o.id DESC;
```

Mỗi đơn hàng phù hợp tạo một hàng kết quả. Đây là điều cần thiết nếu ứng dụng cần hiển thị từng đơn, chứ không chỉ biết khách hàng có đơn hàng hay không.

### 3.1. INNER JOIN và OUTER JOIN

- `INNER JOIN` chỉ giữ các cặp hàng có điều kiện `ON` khớp.
- `LEFT JOIN` giữ mọi hàng bên trái; nếu không có hàng bên phải, các cột bên phải nhận `NULL`.
- `RIGHT JOIN` giữ mọi hàng bên phải; trong thiết kế truy vấn mới, thường có thể đổi thứ tự bảng và dùng `LEFT JOIN` để dễ đọc.

Ví dụ lấy mọi khách hàng, kể cả người chưa từng mua hàng:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id;
```

Nếu một khách hàng có nhiều đơn, khách hàng vẫn xuất hiện nhiều hàng. Với khách hàng chưa có đơn, `order_id` là `NULL`.

### 3.2. Điều kiện ON và WHERE với LEFT JOIN

Vị trí điều kiện có thể làm thay đổi ngữ nghĩa:

```sql
-- Giữ mọi khách hàng; chỉ ghép đơn đã thanh toán
SELECT c.id, c.name, o.id AS paid_order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
 AND o.status = 'paid';
```

So với:

```sql
-- WHERE loại hàng không có đơn paid, khiến kết quả gần với INNER JOIN
SELECT c.id, c.name, o.id AS paid_order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
WHERE o.status = 'paid';
```

Ở truy vấn thứ hai, khách hàng không có đơn phù hợp có `o.status = NULL`; điều kiện `WHERE` không nhận `TRUE` nên hàng bị loại. Khi muốn giữ hàng không khớp của phía phải, đặt điều kiện lọc phía phải trong `ON` hoặc dùng `NOT EXISTS` tùy mục tiêu.

## 4. EXISTS: kiểm tra có ít nhất một hàng phù hợp

`EXISTS` trả về TRUE nếu truy vấn con trả về ít nhất một hàng; nội dung cột trong danh sách `SELECT` của subquery không quan trọng. Vì vậy, quy ước thường dùng là `SELECT 1`.

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

Đây là truy vấn tương quan (correlated subquery), vì subquery tham chiếu `c.id` từ truy vấn bên ngoài. Về mặt logic, nó kiểm tra sự tồn tại đơn hàng cho từng khách hàng. Tuy nhiên, không nên kết luận MySQL nhất thiết phải chạy subquery từ đầu cho từng hàng: optimizer có thể biến đổi dạng `EXISTS` đủ điều kiện thành semijoin hoặc chiến lược khác.

Không cần viết `SELECT o.id` hay `SELECT *` trong subquery `EXISTS` nếu không dùng giá trị đó. `SELECT 1` thể hiện rõ chỉ kiểm tra sự tồn tại.

## 5. IN và EXISTS cho điều kiện thành viên

`IN (subquery)` kiểm tra biểu thức bên trái có thuộc tập giá trị do truy vấn con trả về hay không:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE c.id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'paid'
);
```

Với khóa không NULL và cùng ngữ nghĩa so sánh, truy vấn này thường diễn đạt cùng mục tiêu với `EXISTS` ở phần trước. `IN` có thể dễ đọc khi tư duy theo tập giá trị; `EXISTS` nhấn mạnh việc tìm một hàng khớp.

Không có quy tắc hiệu năng tuyệt đối giữa `IN` và `EXISTS`. MySQL có thể chuyển cả hai thành semijoin hoặc materialize tập con tùy cấu trúc truy vấn và phiên bản. Hãy đo bằng kế hoạch thực thi.

### 5.1. NULL và NOT IN

`NOT IN` có rủi ro ngữ nghĩa khi tập con chứa `NULL`. Ví dụ:

```sql
SELECT c.id
FROM customers AS c
WHERE c.id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

Nếu subquery trả về một `NULL`, phép so sánh với giá trị không có mặt trong tập vẫn có thể trở thành `UNKNOWN`, khiến điều kiện `WHERE` không giữ hàng đó. Kết quả có thể rỗng hoặc thiếu hàng so với điều người viết mong đợi.

Để tìm khách hàng không có đơn hàng phù hợp, thường dùng `NOT EXISTS`:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

Nếu `orders.customer_id` được khai báo `NOT NULL`, `NOT IN` có thể an toàn hơn về mặt NULL, nhưng `NOT EXISTS` vẫn thể hiện rõ quan hệ anti-match và ít phụ thuộc giả định về dữ liệu nullable.

## 6. NOT EXISTS và LEFT JOIN ... IS NULL

Có hai mẫu phổ biến để tìm hàng không có đối tượng liên quan.

**Dùng NOT EXISTS:**

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

**Dùng LEFT JOIN và kiểm tra khóa bên phải:**

```sql
SELECT c.id, c.name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
 AND o.status = 'paid'
WHERE o.id IS NULL;
```

Hai truy vấn trên có thể diễn đạt cùng mục tiêu nếu `o.id` là khóa chính không NULL và điều kiện khớp được đặt trong `ON`. `NOT EXISTS` thường dễ đọc hơn vì không cần tạo các cột NULL giả lập rồi lọc lại.

Khi dùng `LEFT JOIN ... IS NULL`, hãy kiểm tra một cột bên phải chắc chắn không NULL đối với hàng thật, thường là primary key. Không kiểm tra một cột nullable như `o.shipped_at IS NULL`, vì hàng có tồn tại nhưng `shipped_at` chưa được gán cũng sẽ bị nhầm thành không có hàng.

## 7. JOIN có thể nhân số hàng: fan-out và duplicate

Một quan hệ one-to-many làm một hàng phía cha xuất hiện nhiều lần. Khi nối nhiều bảng con cùng lúc, số hàng có thể tăng theo tích số hàng khớp ở từng phía.

Ví dụ một khách hàng có 2 đơn hàng và 3 phiếu hỗ trợ:

```sql
SELECT c.id, o.id AS order_id, t.id AS ticket_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
JOIN support_tickets AS t
  ON t.customer_id = c.id
WHERE c.id = 42;
```

Kết quả có thể có 2 × 3 = 6 hàng cho khách hàng 42. Đây không phải lỗi của MySQL; nó là ngữ nghĩa kết hợp mọi cặp hàng thỏa điều kiện join.

Điều này đặc biệt nguy hiểm khi tính tổng:

```sql
-- Dễ đếm và cộng trùng do fan-out giữa orders và tickets
SELECT
    c.id,
    COUNT(o.id) AS order_count,
    SUM(o.total_amount) AS order_total,
    COUNT(t.id) AS ticket_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
LEFT JOIN support_tickets AS t
  ON t.customer_id = c.id
GROUP BY c.id;
```

Nếu khách hàng có 2 đơn và 3 ticket, mỗi đơn bị lặp 3 lần, mỗi ticket bị lặp 2 lần. `COUNT(DISTINCT ...)` có thể sửa một số phép đếm, nhưng `SUM(DISTINCT total_amount)` không phải cách tổng quát vì hai đơn khác nhau có thể có cùng số tiền.

### 7.1. Tổng hợp từng bảng trước khi JOIN

Một cách an toàn là tổng hợp từng quan hệ con về một hàng cho mỗi khách hàng rồi mới join:

```sql
SELECT
    c.id,
    c.name,
    COALESCE(o.order_count, 0) AS order_count,
    COALESCE(o.order_total, 0.00) AS order_total,
    COALESCE(t.ticket_count, 0) AS ticket_count
FROM customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS order_total
    FROM orders
    GROUP BY customer_id
) AS o
  ON o.customer_id = c.id
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS ticket_count
    FROM support_tickets
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.id;
```

Mỗi derived table trả tối đa một hàng cho mỗi `customer_id`, vì vậy việc ghép với `customers` không nhân số đơn với số ticket. Dùng `COALESCE` để hiển thị 0 khi không có hàng tổng hợp; chỉ thay `NULL` bằng 0 khi đúng ngữ nghĩa báo cáo.

## 8. Scalar subquery: truy vấn con trả một giá trị

Scalar subquery là truy vấn con được dùng ở nơi cần một giá trị đơn:

```sql
SELECT
    c.id,
    c.name,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.id
    ) AS last_order_at
FROM customers AS c;
```

Subquery trả về một giá trị tổng hợp cho từng khách hàng. `MAX()` luôn tạo một hàng kết quả; nếu không có đơn hàng, giá trị trả về là `NULL`.

Quy tắc scalar subquery:

- Không có hàng: kết quả là `NULL`.
- Có đúng một hàng và một cột: dùng giá trị đó.
- Có nhiều hơn một hàng: MySQL báo lỗi `Subquery returns more than 1 row`.
- Có nhiều hơn một cột: không phù hợp với vị trí scalar.

Không dùng scalar subquery khi truy vấn con có thể trả nhiều hàng mà chưa giới hạn hoặc tổng hợp. Nếu cần nhiều hàng con, dùng `JOIN`, `EXISTS`, `IN` hoặc derived table theo mục tiêu.

## 9. Correlated subquery và uncorrelated subquery

**Correlated subquery** tham chiếu cột từ query block bên ngoài:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

**Uncorrelated subquery** không tham chiếu cột của query block bên ngoài:

```sql
SELECT id, name
FROM customers
WHERE id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'paid'
);
```

Subquery tương quan thường được hiểu như phép kiểm tra theo từng hàng bên ngoài, nhưng optimizer có thể biến đổi nó. Subquery không tương quan có thể được materialize hoặc thực thi theo chiến lược khác; không nên mặc định nó chỉ chạy đúng một lần hay luôn nhanh hơn.

Khi đọc kế hoạch, xem MySQL đã chuyển đổi subquery chưa, có materialization hay dependent execution không, và số hàng thực tế mỗi bước xử lý.

## 10. Derived table và tổng hợp trước khi kết hợp

Derived table là một truy vấn `SELECT` đặt trong mệnh đề `FROM` và có alias. Nó giúp tách logic thành các tập kết quả có cấu trúc rõ ràng:

```sql
SELECT
    c.id,
    c.name,
    paid.total_paid
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, SUM(total_amount) AS total_paid
    FROM orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS paid
  ON paid.customer_id = c.id;
```

Ở đây subquery tổng hợp các đơn đã thanh toán theo khách hàng trước khi join với bảng khách hàng. Đây là cách diễn đạt phù hợp khi cần một kết quả tổng hợp cho mỗi nhóm.

MySQL có thể merge một derived table vào query block ngoài hoặc materialize nó thành kết quả trung gian. Các yếu tố như `GROUP BY`, aggregate, `DISTINCT`, `LIMIT` và cấu trúc truy vấn có thể ảnh hưởng khả năng merge. Không nên giả định cứ viết subquery trong `FROM` là MySQL luôn tạo bảng tạm; cũng không nên giả định nó luôn được inline.

## 11. Optimizer có thể biến đổi JOIN và subquery

SQL mô tả kết quả mong muốn, còn optimizer chọn cách thực hiện. Một số biến đổi quan trọng:

- **Semijoin:** dùng cho một số truy vấn `IN`/`EXISTS` để chỉ giữ hàng bên ngoài có ít nhất một hàng khớp, tránh nhân hàng như join thông thường.
- **Antijoin:** dùng cho một số dạng `NOT EXISTS`/`NOT IN` để giữ hàng không có kết quả khớp, với điều kiện NULL semantics được xử lý phù hợp.
- **Materialization:** tính một tập con hoặc derived table thành kết quả trung gian để truy vấn bên ngoài sử dụng.
- **Derived-table merging:** gộp query block trung gian vào truy vấn ngoài khi điều kiện cho phép.
- **Join reordering:** thay đổi thứ tự kết hợp các bảng trong inner join để giảm chi phí.

Các biến đổi phụ thuộc cấu trúc truy vấn, SQL mode, nullable, phiên bản và lựa chọn optimizer. Ví dụ `NOT IN` với tập con có thể chứa `NULL` có ngữ nghĩa khác `NOT EXISTS`; không được viết lại chỉ vì hai câu lệnh trông giống nhau.

Điều quan trọng là cùng một ý định logic có thể được thực thi bằng chiến lược khác nhau. Vì vậy, không nên tối ưu chỉ bằng cách thay `IN` thành `EXISTS` hoặc đổi subquery thành join mà không đo.

## 12. Các chiến lược JOIN vật lý

MySQL có thể dùng các chiến lược join khác nhau tùy phiên bản, index, điều kiện join và thống kê:

### 12.1. Nested-loop join

Một hàng từ bảng ngoài được dùng để tìm các hàng khớp ở bảng trong. Nếu bảng trong có index trên join key, mỗi lần dò có thể hiệu quả:

```sql
SELECT c.id, o.id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
WHERE c.id BETWEEN 100 AND 200;
```

Với tập khách hàng ngoài nhỏ và index phù hợp trên `orders.customer_id`, nested loop thường là lựa chọn tốt. Nếu phải quét bảng trong rất nhiều lần mà không có index phù hợp, chi phí có thể tăng mạnh.

### 12.2. Hash join

Trên MySQL 8.0.18 trở lên, optimizer có thể dùng hash join cho một số phép join phù hợp, đặc biệt khi điều kiện equi-join không có index hữu ích. Một phía được dùng để xây hash table; phía còn lại được dò theo khóa.

Hash join không có nghĩa truy vấn luôn nhanh hơn nested loop. Nó cần bộ nhớ và có thể phải xử lý spill hoặc chi phí lớn nếu tập dữ liệu lớn. Khả năng chọn hash join phụ thuộc phiên bản, điều kiện và optimizer.

### 12.3. Không suy luận thuật toán từ cú pháp

Viết `JOIN`, `IN` hay `EXISTS` không ép MySQL dùng một thuật toán duy nhất. Optimizer có thể chuyển đổi và chọn kế hoạch vật lý dựa trên chi phí ước tính. Đọc `EXPLAIN` để biết kế hoạch mà server chọn thay vì suy luận từ hình thức SQL.

## 13. Đọc EXPLAIN để so sánh hai cách viết

`EXPLAIN` cho biết kế hoạch mà MySQL dự định dùng:

```sql
EXPLAIN
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

So sánh với truy vấn JOIN:

```sql
EXPLAIN
SELECT DISTINCT c.id, c.name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
WHERE o.status = 'paid';
```

Khi đọc kết quả, chú ý:

- `type`/access method: `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` và các access path khác.
- `possible_keys` và `key`: index có thể dùng và index thực tế được chọn.
- `key_len`: độ dài phần index được sử dụng.
- `rows` và `filtered`: ước tính số hàng và tỷ lệ còn lại.
- `Extra`: thông tin bổ sung như `Using where`, `Using index`, `Using temporary`, `Using filesort`.
- `select_type` hoặc cấu trúc query block: nhận diện subquery, derived table hoặc materialization trong dạng EXPLAIN tương ứng.

Không có một cột đơn lẻ quyết định truy vấn nhanh hay chậm. Ví dụ `type = ALL` có thể hợp lý khi bảng nhỏ hoặc cần đọc phần lớn dữ liệu; `Using index` không tự động chứng minh truy vấn tối ưu nếu vẫn đọc quá nhiều hàng.

## 14. EXPLAIN ANALYZE: đo số hàng và thời gian thực tế

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi câu lệnh được phân tích và báo thời gian, số vòng lặp cùng số hàng thực tế của các iterator:

```sql
EXPLAIN ANALYZE
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

So sánh với kế hoạch của JOIN tương ứng. Hãy xem:

- Số hàng thực tế khác bao nhiêu so với ước tính.
- Iterator nào chiếm phần lớn thời gian.
- Có iterator nào chạy nhiều vòng lặp với số hàng lớn không.
- Có bước materialization hoặc sort gây chi phí không.
- Index có giảm được số hàng đọc như dự kiến không.

`EXPLAIN ANALYZE` thực sự chạy truy vấn. Chỉ dùng với câu lệnh đọc an toàn như `SELECT` trên môi trường phù hợp; không gắn nó vào DML có tác động dữ liệu khi chưa hiểu hành vi và phiên bản. Với truy vấn nặng, dữ liệu lớn hoặc production nhạy tải, cần đánh giá tác động trước khi chạy.

## 15. Index cho JOIN và subquery

Index nên hỗ trợ các cột dùng để nối và lọc. Với truy vấn tìm khách hàng có đơn đã thanh toán:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

Có thể đánh giá hai thứ tự index:

```sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);

CREATE INDEX idx_orders_status_customer
ON orders (status, customer_id);
```

Không cần tạo cả hai chỉ vì chúng xuất hiện trong ví dụ. Chọn theo cách truy vấn truy cập bảng:

- Nếu bắt đầu từ một khách hàng rồi dò trạng thái đơn, `(customer_id, status)` có thể phù hợp.
- Nếu lọc một trạng thái rất chọn lọc trên toàn bảng rồi lấy khách hàng, `(status, customer_id)` có thể phù hợp.

Độ chọn lọc, phân bố dữ liệu, số lượng trạng thái, kích thước bảng và các truy vấn khác đều ảnh hưởng quyết định. Index tăng tốc một số thao tác đọc nhưng làm tăng dung lượng và chi phí `INSERT`/`UPDATE`/`DELETE`.

## 16. Chọn cách viết theo tình huống

| Tình huống | Cách bắt đầu | Lý do |
| --- | --- | --- |
| Cần cột từ cả hai bảng | `JOIN` | Kết quả cần dữ liệu kết hợp |
| Cần từng cặp hàng one-to-many | `JOIN` | Mỗi cặp là một hàng kết quả hợp lệ |
| Chỉ cần biết có hàng liên quan | `EXISTS` | Tránh nhân hàng bên ngoài do nhiều hàng khớp |
| Cần giữ hàng không có đối tượng liên quan | `NOT EXISTS` | Biểu đạt anti-match, ít rủi ro NULL hơn `NOT IN` |
| Kiểm tra một giá trị thuộc tập | `IN` | Cú pháp trực tiếp cho membership |
| Lấy một giá trị tổng hợp cho mỗi hàng | Scalar subquery hoặc derived aggregate | Chọn theo phạm vi và khả năng tái sử dụng kết quả |
| Tổng hợp nhiều bảng con độc lập | Aggregate từng nguồn rồi `JOIN` | Tránh fan-out và cộng/đếm trùng |
| Dùng kết quả trung gian trong FROM | Derived table/CTE | Tách logic, sau đó kiểm tra merge/materialization |

Đây là điểm xuất phát theo ngữ nghĩa, không phải luật hiệu năng. Sau khi viết đúng kết quả, mới so sánh kế hoạch và chi phí.

## 17. Quy trình so sánh JOIN và subquery

Khi một truy vấn có thể viết theo nhiều cách, thực hiện lần lượt:

1. **Mô tả kết quả mong muốn:** một hàng cho mỗi đối tượng, một hàng cho mỗi cặp hay một giá trị tổng hợp?
2. **Xác định cardinality:** quan hệ one-to-one, one-to-many hay many-to-many; có thể phát sinh duplicate không?
3. **Kiểm tra NULL:** các khóa có nullable không; `IN`/`NOT IN` có thể gặp NULL ở tập con không?
4. **Viết cách thể hiện ngữ nghĩa rõ nhất:** `JOIN`, `EXISTS`, `NOT EXISTS`, `IN` hay scalar/derived subquery.
5. **Kiểm tra tính đúng:** thử trường hợp không có hàng con, một hàng con, nhiều hàng con, duplicate và NULL.
6. **Xem index:** có index trên join key và điều kiện lọc không; thứ tự cột có phù hợp không?
7. **Chạy EXPLAIN:** xem access path, estimated rows, materialization, temporary và sort.
8. **Chạy EXPLAIN ANALYZE khi phù hợp:** so sánh actual rows, loops và thời gian trên dữ liệu đại diện.
9. **Đo cả chi phí tổng thể:** thời gian, CPU, I/O, memory, số hàng trả về và chi phí ghi do index.
10. **Chọn truy vấn dễ bảo trì:** nếu hiệu năng tương đương, ưu tiên câu lệnh thể hiện đúng ý định và ít rủi ro duplicate/NULL.

## 18. Bài tập thực hành

1. Tạo dữ liệu trong đó một khách hàng có nhiều đơn đã thanh toán; so sánh số hàng của `JOIN` và `EXISTS`.
2. Viết truy vấn hiển thị từng đơn cùng tên khách hàng bằng `JOIN`.
3. Viết truy vấn tìm khách hàng không có đơn hàng bằng `NOT EXISTS` và `LEFT JOIN ... IS NULL`; đối chiếu kết quả.
4. Tạo dữ liệu có `NULL` trong tập con và so sánh `NOT IN` với `NOT EXISTS`.
5. Nối `customers`, `orders` và `support_tickets` rồi tính tổng đơn; quan sát fan-out và sửa bằng aggregate trước khi join.
6. Viết scalar subquery lấy thời gian đơn hàng mới nhất của từng khách hàng; so sánh với derived table đã `GROUP BY`.
7. Dùng `EXPLAIN` cho `IN`, `EXISTS` và `JOIN DISTINCT` với cùng mục tiêu; ghi nhận index và số hàng ước tính.
8. Dùng `EXPLAIN ANALYZE` trên SELECT phù hợp; so sánh số hàng thực tế, loops và thời gian.
9. Thử thay đổi thứ tự cột trong index ghép trên môi trường lab và đo lại truy vấn.
10. Viết lại một truy vấn nhiều JOIN thành EXISTS hoặc derived table chỉ khi ngữ nghĩa kết quả vẫn đúng; kiểm tra duplicate và NULL.

## 19. Ghi nhớ

Chọn `JOIN` khi cần kết hợp dữ liệu từ hai phía hoặc cần từng cặp hàng; chọn `EXISTS`/`IN` khi chỉ cần kiểm tra sự tồn tại hay membership; chọn `NOT EXISTS` để tìm hàng không có đối tượng liên quan; dùng scalar subquery cho một giá trị và derived table khi cần kết quả trung gian hoặc tổng hợp trước khi join.

`JOIN` có thể nhân hàng trong quan hệ one-to-many và làm sai `COUNT`/`SUM` khi nối nhiều bảng con. `EXISTS` tránh nhân hàng bên ngoài; `NOT IN` cần đặc biệt chú ý NULL. Optimizer có thể biến đổi JOIN và subquery thành semijoin, antijoin, materialization, nested-loop hoặc hash join tùy phiên bản và điều kiện. Vì vậy, hãy chọn theo ngữ nghĩa trước, sau đó kiểm tra index, `EXPLAIN`, số hàng thực tế và `EXPLAIN ANALYZE`. Không có cú pháp nào luôn nhanh nhất cho mọi dữ liệu và workload.
