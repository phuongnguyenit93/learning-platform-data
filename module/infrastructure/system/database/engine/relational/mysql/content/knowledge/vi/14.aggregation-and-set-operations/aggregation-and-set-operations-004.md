# Phân biệt WHERE và HAVING

Trong truy vấn SELECT, WHERE và HAVING đều dùng để lọc dữ liệu, nhưng chúng lọc ở hai giai đoạn khác nhau. **WHERE lọc từng hàng trước khi nhóm và tính tổng hợp; HAVING lọc các nhóm sau khi GROUP BY và các phép tổng hợp được tính.**

Hiểu đúng sự khác biệt này giúp viết báo cáo chính xác, tránh đặt điều kiện tổng hợp sai vị trí và giảm lượng dữ liệu phải xử lý. Với MySQL, cần chú ý thêm đến thứ tự xử lý logic, cách dùng alias, SQL mode ONLY_FULL_GROUP_BY và hành vi của NULL trong các hàm tổng hợp.

Bài viết sử dụng các bảng minh họa customers và orders:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL,
    shipped_at  DATETIME NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_status_created (status, created_at),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB;
~~~

## 1. WHERE lọc hàng trước khi nhóm

WHERE xác định hàng nào được đưa vào các bước tiếp theo của truy vấn. Hàng không thỏa điều kiện WHERE bị loại khỏi tập kết quả trung gian trước khi GROUP BY tạo nhóm.

Ví dụ chỉ lấy đơn hàng đã thanh toán:

~~~sql
SELECT order_id, customer_id, total
FROM orders
WHERE status = 'PAID';
~~~

Ở đây mỗi hàng là một đơn hàng. WHERE kiểm tra status trên từng đơn và chỉ giữ lại các đơn có trạng thái PAID.

Có thể kết hợp nhiều điều kiện hàng:

~~~sql
SELECT order_id, customer_id, total, created_at
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01';
~~~

Các điều kiện này không cần tổng hợp dữ liệu. Chúng mô tả hàng nào đủ điều kiện tham gia truy vấn.

WHERE thường được dùng cho:

- Lọc theo khóa hoặc thuộc tính của hàng.
- Lọc theo trạng thái, ngày tháng, khoảng số.
- Giới hạn phạm vi dữ liệu trước khi GROUP BY.
- Điều kiện nối và lọc hàng trong các truy vấn nhiều bảng (cần phân biệt điều kiện ON với WHERE khi dùng outer join).

## 2. HAVING lọc nhóm sau khi tổng hợp

HAVING được áp dụng sau GROUP BY để kiểm tra từng nhóm. Nó thường dùng với các hàm tổng hợp như COUNT(), SUM(), AVG(), MIN() và MAX().

Ví dụ tìm khách hàng có ít nhất ba đơn hàng:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 3;
~~~

Quy trình:

1. MySQL đọc các hàng từ orders.
2. GROUP BY gom các hàng có cùng customer_id.
3. COUNT(*) tính số đơn trong mỗi nhóm.
4. HAVING chỉ giữ nhóm có số đơn từ ba trở lên.

Nếu thay HAVING bằng WHERE:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
WHERE COUNT(*) >= 3
GROUP BY customer_id;
~~~

Truy vấn này không hợp lệ vì WHERE được xử lý trước khi nhóm được hình thành; COUNT(*) chưa có giá trị ở giai đoạn đó. Điều kiện phụ thuộc kết quả tổng hợp phải đặt ở HAVING.

## 3. Thứ tự xử lý logic của SELECT

Để biết nên đặt điều kiện ở đâu, có thể hình dung thứ tự xử lý logic phổ biến của truy vấn SELECT như sau:

~~~text
FROM / JOIN
     |
     v
WHERE       Lọc từng hàng
     |
     v
GROUP BY    Tạo nhóm
     |
     v
HAVING      Lọc nhóm
     |
     v
SELECT      Tính biểu thức và hàm tổng hợp
     |
     v
ORDER BY    Sắp xếp kết quả
     |
     v
LIMIT       Giới hạn số hàng trả về
~~~

Đây là thứ tự logic để hiểu ngữ nghĩa, không phải cam kết rằng MySQL thực thi vật lý từng bước đúng theo thứ tự trên. Optimizer có thể biến đổi kế hoạch nếu vẫn giữ nguyên kết quả theo ngữ nghĩa SQL.

Điểm quan trọng:

- WHERE không thể tham chiếu kết quả của hàm tổng hợp trong cùng cấp SELECT.
- HAVING nhìn thấy các nhóm và kết quả tổng hợp.
- Alias được tạo trong danh sách SELECT không dùng được trong WHERE của cùng cấp truy vấn.
- MySQL cho phép dùng alias của biểu thức SELECT trong HAVING như một phần mở rộng; cần cân nhắc khả năng chuyển đổi nếu muốn SQL tương thích nhiều hệ quản trị.

## 4. Kết hợp WHERE và HAVING trong cùng truy vấn

Trong báo cáo thực tế, thường cần lọc hàng trước rồi mới lọc nhóm.

Yêu cầu: tìm khách hàng có ít nhất ba đơn hàng đã thanh toán trong năm 2026 và tổng giá trị các đơn đó từ 1.000.000 trở lên.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY customer_id
HAVING COUNT(*) >= 3
   AND SUM(total) >= 1000000
ORDER BY paid_total DESC;
~~~

Phân chia điều kiện:

| Điều kiện | Nơi đặt | Lý do |
|---|---|---|
| status = 'PAID' | WHERE | Thuộc tính của từng đơn hàng |
| created_at nằm trong năm 2026 | WHERE | Thuộc tính thời gian của từng đơn |
| COUNT(*) >= 3 | HAVING | Số lượng hàng trong mỗi nhóm |
| SUM(total) >= 1000000 | HAVING | Tổng giá trị sau khi nhóm |

Nếu đặt điều kiện trạng thái ở HAVING, truy vấn có thể phải đưa nhiều hàng không cần thiết vào quá trình nhóm rồi mới loại nhóm. Điều kiện hàng nên được đặt ở WHERE nếu không làm thay đổi ý nghĩa báo cáo.

## 5. Điều kiện trên cột nhóm: có thể dùng WHERE hoặc HAVING?

Một điều kiện trên cột nhóm có thể xuất hiện ở cả hai vị trí về mặt khả năng biểu đạt, nhưng thời điểm lọc khác nhau.

Hai truy vấn sau có cùng mục tiêu: tính số đơn của khách hàng 42.

~~~sql
-- Lọc khách hàng trước khi nhóm
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id = 42
GROUP BY customer_id;

-- Tạo các nhóm trước, sau đó chỉ giữ nhóm khách hàng 42
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING customer_id = 42;
~~~

Trong ví dụ đơn giản này, kết quả thường giống nhau. Tuy nhiên, WHERE loại bỏ các hàng của khách hàng khác trước khi nhóm; HAVING tạo các nhóm rồi mới loại các nhóm không phù hợp.

Vì customer_id = 42 là điều kiện trên hàng nguồn, nên ưu tiên WHERE. Điều này thể hiện đúng ý định và thường cho phép giảm số hàng đầu vào cho bước tổng hợp. Không nên chuyển mọi điều kiện sang HAVING chỉ vì truy vấn có GROUP BY.

## 6. Những hàm tổng hợp thường dùng với HAVING

### 6.1. COUNT()

COUNT(*) đếm tất cả hàng trong nhóm:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 10;
~~~

COUNT(column) chỉ đếm các hàng mà biểu thức column không NULL:

~~~sql
SELECT customer_id, COUNT(shipped_at) AS shipped_count
FROM orders
GROUP BY customer_id
HAVING COUNT(shipped_at) = 0;
~~~

Ví dụ thứ hai cần cột shipped_at có trong bảng. Nếu cột cho phép NULL, COUNT(shipped_at) bằng 0 nghĩa là nhóm không có giá trị shipped_at khác NULL; nó không nhất thiết có nghĩa là không có đơn hàng.

### 6.2. SUM()

Tìm khách hàng có tổng giá trị đơn hàng lớn:

~~~sql
SELECT customer_id, SUM(total) AS total_spent
FROM orders
GROUP BY customer_id
HAVING SUM(total) >= 5000000;
~~~

SUM() cộng các giá trị khác NULL. Nếu biểu thức được cộng cho phép NULL và một nhóm không có giá trị khác NULL, SUM() có thể trả NULL; phép so sánh NULL với một số cho kết quả UNKNOWN và nhóm không vượt qua HAVING.

### 6.3. AVG()

Tìm khách hàng có giá trị đơn trung bình trên ngưỡng:

~~~sql
SELECT
    customer_id,
    AVG(total) AS average_order_value
FROM orders
GROUP BY customer_id
HAVING AVG(total) > 750000;
~~~

AVG() bỏ qua giá trị NULL. Khi diễn giải kết quả, cần hiểu mẫu số là số giá trị khác NULL chứ không nhất thiết là tổng số hàng trong nhóm.

### 6.4. MIN() và MAX()

Tìm khách hàng có đơn hàng lớn nhất đạt ngưỡng:

~~~sql
SELECT
    customer_id,
    MAX(total) AS largest_order
FROM orders
GROUP BY customer_id
HAVING MAX(total) >= 10000000;
~~~

MIN() và MAX() có thể áp dụng cho số, ngày giờ và chuỗi theo quy tắc so sánh của kiểu dữ liệu/collation.

## 7. Dùng alias trong HAVING

MySQL cho phép tham chiếu alias của biểu thức SELECT trong HAVING:

~~~sql
SELECT
    customer_id,
    SUM(total) AS total_spent
FROM orders
GROUP BY customer_id
HAVING total_spent >= 5000000;
~~~

Cách này ngắn gọn và dễ đọc. Tuy nhiên, alias không có sẵn trong WHERE của cùng cấp truy vấn:

~~~sql
-- Không hợp lệ: total_spent là alias được tạo ở SELECT
SELECT
    customer_id,
    SUM(total) AS total_spent
FROM orders
WHERE total_spent >= 5000000
GROUP BY customer_id;
~~~

Nếu cần lọc theo kết quả tổng hợp ở một truy vấn bên ngoài, có thể dùng derived table hoặc CTE:

~~~sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total) AS total_spent
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, total_spent
FROM customer_totals
WHERE total_spent >= 5000000;
~~~

Trong truy vấn ngoài, total_spent đã là cột của derived result nên WHERE có thể sử dụng. CTE giúp biểu đạt logic theo từng bước; optimizer có thể merge hoặc materialize CTE tùy truy vấn và phiên bản.

## 8. HAVING không có GROUP BY

Nếu truy vấn dùng hàm tổng hợp mà không có GROUP BY, toàn bộ tập hàng được xem như một nhóm duy nhất:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(total) AS gross_value
FROM orders
HAVING COUNT(*) > 0;
~~~

Truy vấn trả về một hàng nếu nhóm tổng hợp thỏa điều kiện HAVING; nếu không, nó không trả hàng nào. Điều này hữu ích khi muốn điều kiện hóa kết quả tổng hợp toàn bảng.

MySQL cũng cho phép HAVING trong một số truy vấn không có GROUP BY như một phần mở rộng. Với điều kiện lọc từng hàng thông thường, hãy dùng WHERE để thể hiện đúng ngữ nghĩa và tăng khả năng tương thích SQL.

## 9. WHERE, HAVING và ONLY_FULL_GROUP_BY

ONLY_FULL_GROUP_BY là SQL mode kiểm soát các biểu thức không tổng hợp xuất hiện trong SELECT, HAVING hoặc ORDER BY của truy vấn nhóm.

Khi mode này bật, các cột không nằm trong GROUP BY thường phải:

- Được dùng bên trong hàm tổng hợp; hoặc
- Có quan hệ phụ thuộc hàm (functional dependency) với các cột nhóm; hoặc
- Được giới hạn để MySQL chứng minh chỉ có một giá trị phù hợp trong ngữ cảnh được hỗ trợ.

MySQL 8.0 bật ONLY_FULL_GROUP_BY trong cấu hình SQL mode mặc định. Kiểm tra session hiện tại:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Ví dụ không an toàn về mặt ngữ nghĩa:

~~~sql
SELECT
    customer_id,
    status,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
~~~

Một khách hàng có thể có nhiều đơn với trạng thái khác nhau. Nếu MySQL không thể xác định một giá trị status duy nhất cho mỗi nhóm, truy vấn bị từ chối khi ONLY_FULL_GROUP_BY bật. Khi mode tắt, MySQL có thể chọn một giá trị status không xác định trong nhóm; không nên dựa vào kết quả đó.

Hãy sửa theo ý định nghiệp vụ. Nếu muốn đếm đơn theo cả khách hàng và trạng thái:

~~~sql
SELECT customer_id, status, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id, status;
~~~

Nếu muốn lọc nhóm có tổng số đơn lớn:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 5;
~~~

### 9.1. Functional dependency

MySQL có thể cho phép chọn một cột không được liệt kê trong GROUP BY nếu chứng minh được cột đó phụ thuộc hàm vào các cột nhóm. Ví dụ, customers.customer_id là primary key nên xác định duy nhất customers.full_name:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

Trong MySQL, functional dependency dựa trên khóa duy nhất NOT NULL có thể giúp truy vấn hợp lệ khi ONLY_FULL_GROUP_BY bật. Dù vậy, việc đưa rõ cột vào GROUP BY đôi khi giúp ý định dễ hiểu hơn, đặc biệt khi cần SQL tương thích nhiều hệ quản trị.

Không nên tắt ONLY_FULL_GROUP_BY chỉ để làm cho truy vấn sai ngữ nghĩa chạy được. Hãy xác định rõ nhóm đại diện cho điều gì và cột nào có một giá trị duy nhất trong nhóm.

## 10. WHERE và HAVING khi dùng JOIN

Với JOIN, điều kiện có thể nằm trong ON, WHERE hoặc HAVING. Ba vị trí này có vai trò khác nhau:

- ON xác định hàng nào khớp khi kết hợp hai bảng.
- WHERE lọc kết quả hàng sau JOIN nhưng trước GROUP BY.
- HAVING lọc nhóm sau khi tổng hợp.

Ví dụ cần liệt kê tất cả khách hàng và số đơn đã thanh toán, kể cả khách hàng chưa có đơn:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.full_name;
~~~

Điều kiện o.status = 'PAID' nằm trong ON nên chỉ những đơn đã thanh toán được ghép; khách hàng không có đơn phù hợp vẫn xuất hiện với các cột của orders là NULL. COUNT(o.order_id) trả 0 cho nhóm đó.

Nếu chuyển điều kiện trạng thái sang WHERE:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.full_name;
~~~

Các hàng được mở rộng với NULL của khách hàng không có đơn sẽ bị WHERE loại bỏ. Kết quả lúc này không còn giữ các khách hàng không có đơn phù hợp; LEFT JOIN về mặt kết quả gần như trở thành INNER JOIN.

Nếu chỉ muốn giữ các khách hàng có ít nhất ba đơn đã thanh toán, thêm HAVING:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.full_name
HAVING COUNT(o.order_id) >= 3;
~~~

Điều kiện ở HAVING áp dụng cho số đơn trong mỗi nhóm, không phải từng hàng đơn lẻ.

## 11. NULL và điều kiện HAVING

Các hàm tổng hợp không xử lý NULL giống nhau:

| Hàm | Cách xử lý NULL |
|---|---|
| COUNT(*) | Đếm mọi hàng |
| COUNT(column) | Chỉ đếm giá trị column khác NULL |
| SUM(column) | Bỏ qua NULL; trả NULL nếu không có giá trị khác NULL |
| AVG(column) | Bỏ qua NULL khi tính trung bình |
| MIN()/MAX() | Bỏ qua NULL; trả NULL nếu không có giá trị khác NULL |

Ví dụ:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS row_count,
    COUNT(shipped_at) AS shipped_count,
    MAX(shipped_at) AS last_shipped_at
FROM orders
GROUP BY customer_id
HAVING COUNT(shipped_at) = 0;
~~~

Truy vấn giữ các khách hàng có đơn hàng nhưng không có giá trị shipped_at khác NULL trong nhóm. Nếu muốn tính tổng và coi nhóm không có giá trị là 0, có thể dùng COALESCE:

~~~sql
SELECT
    customer_id,
    COALESCE(SUM(total), 0) AS total_spent
FROM orders
GROUP BY customer_id
HAVING COALESCE(SUM(total), 0) = 0;
~~~

Chỉ dùng COALESCE khi nghiệp vụ thực sự định nghĩa không có giá trị tương đương số 0. NULL và 0 có ý nghĩa khác nhau trong nhiều báo cáo.

## 12. Hiệu năng: đặt điều kiện ở đúng giai đoạn

WHERE thường giúp giảm số hàng cần đưa vào bước GROUP BY. Nếu điều kiện có thể lọc trên cột nguồn, hãy ưu tiên WHERE:

~~~sql
SELECT customer_id, SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY customer_id
HAVING SUM(total) >= 1000000;
~~~

Trong ví dụ:

- WHERE giới hạn dữ liệu theo trạng thái và thời gian.
- GROUP BY gom phần dữ liệu còn lại theo khách hàng.
- HAVING chỉ giữ nhóm có tổng giá trị đạt ngưỡng.

Index phù hợp có thể giúp MySQL tìm các hàng cần thiết nhanh hơn. Ví dụ index bắt đầu bằng status và có created_at có thể hỗ trợ điều kiện lọc này, nhưng index cụ thể còn phụ thuộc độ chọn lọc, thứ tự cột, số lượng hàng và các truy vấn khác.

HAVING thường phải đánh giá biểu thức tổng hợp sau khi nhóm được tạo. Không thể chỉ tạo index trên total rồi kỳ vọng index trực tiếp trả lời điều kiện SUM(total) >= ... cho từng nhóm. Tuy nhiên, optimizer có thể biến đổi một số điều kiện HAVING không phụ thuộc aggregate thành điều kiện lọc sớm hơn nếu an toàn.

Kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT customer_id, SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY customer_id
HAVING SUM(total) >= 1000000;
~~~

Đọc access type, key, rows ước lượng và Extra. EXPLAIN cho biết kế hoạch dự kiến; nếu cần số liệu thực thi, có thể dùng EXPLAIN ANALYZE trên phiên bản hỗ trợ và môi trường phù hợp vì lệnh này thực sự chạy SELECT.

Không chuyển điều kiện từ WHERE sang HAVING chỉ để thử hiệu năng nếu điều đó làm thay đổi tập hàng đầu vào và ý nghĩa báo cáo.

## 13. Một số mẫu truy vấn thường gặp

### 13.1. Lọc hàng rồi tính tổng theo tháng

~~~sql
SELECT
    YEAR(created_at) AS order_year,
    MONTH(created_at) AS order_month,
    COUNT(*) AS order_count,
    SUM(total) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY YEAR(created_at), MONTH(created_at)
HAVING SUM(total) > 10000000
ORDER BY order_year, order_month;
~~~

WHERE giới hạn đơn đã thanh toán trong năm; HAVING chỉ giữ tháng có doanh thu trên ngưỡng.

### 13.2. Đếm theo trạng thái và chỉ giữ nhóm đông

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
HAVING COUNT(*) >= 100;
~~~

Mỗi nhóm là một trạng thái. HAVING loại các trạng thái có ít hơn 100 đơn.

### 13.3. Điều kiện trên hàng và nhóm cùng cột

~~~sql
SELECT customer_id, AVG(total) AS average_paid_order
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING AVG(total) >= 500000;
~~~

WHERE xác định những đơn được tính vào trung bình; HAVING quyết định khách hàng nào có trung bình đạt ngưỡng.

### 13.4. Dùng DISTINCT trong aggregate

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT status) AS status_count
FROM orders
GROUP BY customer_id
HAVING COUNT(DISTINCT status) >= 3;
~~~

COUNT(DISTINCT status) đếm số trạng thái khác nhau, bỏ qua NULL. HAVING lọc khách hàng có ít nhất ba trạng thái khác nhau.

## 14. Những lỗi và nhầm lẫn thường gặp

**“WHERE và HAVING đều chỉ là điều kiện lọc, có thể thay thế tùy ý.”** Không. WHERE lọc hàng trước khi nhóm; HAVING lọc nhóm sau tổng hợp. Đổi vị trí có thể thay đổi dữ liệu được tổng hợp và kết quả.

**“Có GROUP BY thì mọi điều kiện phải đặt trong HAVING.”** Không. Điều kiện trên hàng nguồn vẫn nên đặt trong WHERE. Chỉ điều kiện cần kết quả tổng hợp hoặc điều kiện cấp nhóm mới đặt ở HAVING.

**“Có thể gọi SUM() hoặc COUNT() trong WHERE.”** Không. Aggregate của cấp truy vấn hiện tại chưa được tính ở giai đoạn WHERE. Dùng HAVING hoặc truy vấn con/CTE.

**“Alias trong SELECT dùng được ở mọi nơi.”** Không. Alias của SELECT không dùng được trong WHERE cùng cấp. MySQL cho phép alias trong HAVING như một phần mở rộng, nhưng nên cân nhắc khả năng tương thích.

**“HAVING luôn chậm hơn WHERE.”** Không thể kết luận chỉ từ tên mệnh đề. Hai mệnh đề có ngữ nghĩa khác nhau; optimizer có thể đẩy một số điều kiện phù hợp xuống sớm hơn. Hãy đặt điều kiện đúng ngữ nghĩa và kiểm tra EXPLAIN.

**“COUNT(column) giống COUNT(*).”** Không. COUNT(column) bỏ qua NULL, còn COUNT(*) đếm tất cả hàng.

**“Tắt ONLY_FULL_GROUP_BY là cách sửa truy vấn nhóm.”** Không. Tắt mode có thể khiến MySQL chọn giá trị không xác định cho cột không được nhóm hoặc tổng hợp. Hãy sửa GROUP BY và biểu thức SELECT theo ý nghĩa mong muốn.

**“Đưa điều kiện của bảng bên phải LEFT JOIN vào WHERE luôn tương đương đặt trong ON.”** Không. WHERE có thể loại hàng NULL-extended và làm mất những hàng không có bản ghi khớp. Xác định điều kiện dùng để ghép hay lọc kết quả sau JOIN.

## 15. Quy trình quyết định đặt điều kiện

Khi viết một truy vấn, hãy tự hỏi theo thứ tự:

1. Điều kiện có kiểm tra thuộc tính của từng hàng nguồn không? Nếu có, thường đặt ở WHERE.
2. Điều kiện có xác định hàng nào được phép ghép trong OUTER JOIN không? Nếu có, xem xét đặt trong ON.
3. Điều kiện có phụ thuộc COUNT, SUM, AVG, MIN, MAX hoặc kết quả của nhóm không? Nếu có, đặt ở HAVING.
4. Điều kiện có đang lọc kết quả của một truy vấn con/CTE đã tổng hợp không? Khi đó có thể dùng WHERE ở truy vấn ngoài.
5. Các cột không tổng hợp có tuân thủ ONLY_FULL_GROUP_BY và xác định rõ một giá trị cho mỗi nhóm không?
6. Điều kiện WHERE có thể dùng index và giảm số hàng trước khi nhóm không?

Ví dụ đầy đủ:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    SUM(o.total) AS paid_total
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2027-01-01'
GROUP BY c.customer_id, c.full_name
HAVING COUNT(o.order_id) >= 3
   AND SUM(o.total) >= 1000000
ORDER BY paid_total DESC
LIMIT 20;
~~~

Ở đây JOIN xác định quan hệ khách hàng và đơn hàng; WHERE giới hạn đơn được đưa vào báo cáo; GROUP BY tạo nhóm khách hàng; HAVING lọc theo số lượng và tổng giá trị; ORDER BY sắp xếp các nhóm đủ điều kiện; LIMIT chỉ lấy 20 nhóm đầu.

## Kết luận

WHERE lọc từng hàng trước GROUP BY và các phép tổng hợp. HAVING lọc nhóm sau khi các hàm như COUNT(), SUM(), AVG(), MIN() và MAX() được tính. Một truy vấn báo cáo thường dùng cả hai: WHERE thu hẹp dữ liệu nguồn, HAVING chọn những nhóm đáp ứng điều kiện tổng hợp.

Hãy đặt điều kiện theo đúng cấp dữ liệu mà nó mô tả, lưu ý thứ tự xử lý logic, NULL, ONLY_FULL_GROUP_BY và tác động của điều kiện khi JOIN. Cách phân chia này làm truy vấn dễ hiểu, kết quả đúng nghiệp vụ và giúp MySQL có cơ hội giảm lượng dữ liệu cần tổng hợp.
