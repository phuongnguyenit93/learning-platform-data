# EXISTS, NOT EXISTS và truy vấn kiểm tra tồn tại

Trong nhiều truy vấn, ứng dụng không cần lấy dữ liệu từ bảng liên quan; nó chỉ cần biết có ít nhất một hàng thỏa điều kiện hay không. Ví dụ: khách hàng nào đã có đơn hàng, sản phẩm nào chưa từng được bán, đơn hàng nào có ít nhất một dòng chi tiết hoặc tài khoản nào chưa phát sinh giao dịch.

MySQL cung cấp hai predicate EXISTS và NOT EXISTS để diễn đạt trực tiếp yêu cầu đó:

- **EXISTS** đúng nếu truy vấn con trả về ít nhất một hàng.
- **NOT EXISTS** đúng nếu truy vấn con không trả về hàng nào.

Hai predicate này thường được dùng với correlated subquery, tức truy vấn con tham chiếu đến hàng hiện tại của truy vấn bên ngoài. EXISTS giúp lọc hàng cha theo sự tồn tại của hàng con mà không làm nhân bản hàng cha khi có nhiều kết quả khớp. NOT EXISTS diễn đạt truy vấn tìm các hàng không có quan hệ phù hợp.

Bài viết tập trung vào cách kiểm tra sự tồn tại, phân biệt EXISTS với JOIN và IN, xử lý NULL, đọc kế hoạch thực thi và thiết kế index cho truy vấn con trong MySQL.

## 1. Chuẩn bị dữ liệu minh họa

Các ví dụ sử dụng khách hàng, đơn hàng, sản phẩm và dòng chi tiết đơn hàng:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    email       VARCHAR(255) NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(150) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_id   BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity   INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    KEY idx_order_items_product (product_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
) ENGINE = InnoDB;
~~~

Khóa chính và khóa ngoại bảo đảm quan hệ giữa các bảng. Index trên orders.customer_id hỗ trợ tra cứu đơn theo khách hàng. Ở phần tối ưu bên dưới, bài viết sẽ bổ sung một index ghép customer_id, status, created_at cho truy vấn cần lọc đồng thời theo khách hàng, trạng thái và thời gian. Index trên order_items.product_id hỗ trợ tra cứu các đơn có chứa một sản phẩm.

## 2. EXISTS kiểm tra có ít nhất một hàng

### 2.1. Cú pháp

Mẫu cơ bản:

~~~sql
SELECT columns
FROM outer_table AS outer_alias
WHERE EXISTS (
    SELECT 1
    FROM inner_table AS inner_alias
    WHERE inner_alias.related_key = outer_alias.related_key
);
~~~

EXISTS nhận một truy vấn con. Nó không quan tâm truy vấn con trả về những cột nào; điều cần biết là truy vấn con có tạo ra ít nhất một hàng hay không.

Ví dụ tìm khách hàng đã từng đặt hàng:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Với mỗi khách hàng, MySQL kiểm tra xem có hàng orders nào mang cùng customer_id hay không. Nếu có ít nhất một đơn, khách hàng được đưa vào kết quả.

Một khách hàng có một đơn hay một trăm đơn vẫn chỉ xuất hiện một lần trong kết quả vì EXISTS là điều kiện đúng/sai trên từng hàng của truy vấn ngoài.

### 2.2. Vì sao thường viết SELECT 1?

Trong EXISTS, giá trị ở danh sách SELECT của truy vấn con không được dùng để tạo kết quả đầu ra. Các cách sau có cùng ý nghĩa kiểm tra tồn tại:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

~~~sql
WHERE EXISTS (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

~~~sql
WHERE EXISTS (
    SELECT *
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

SELECT 1 là quy ước dễ đọc vì thể hiện rõ rằng truy vấn chỉ kiểm tra sự tồn tại, không cần lấy cột nào. Nó không có nghĩa MySQL phải đọc một cột hằng theo cách riêng; optimizer có thể biến đổi truy vấn để kiểm tra hiệu quả.

Không cần thêm LIMIT 1 chỉ để làm EXISTS dừng sau hàng đầu tiên. Ngữ nghĩa EXISTS đã cho phép server chỉ cần xác định có hàng phù hợp hay không; optimizer thường có thể tận dụng điều đó.

### 2.3. EXISTS không trả danh sách hàng con

Truy vấn:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

chỉ trả cột của customers. Nếu cần hiển thị thông tin đơn hàng, chẳng hạn order_id hoặc created_at, JOIN thường phù hợp hơn:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

Chọn EXISTS khi câu hỏi là “có hay không”; chọn JOIN khi cần ghép và trả dữ liệu từ cả hai phía.

## 3. Correlated subquery: truy vấn con tham chiếu hàng bên ngoài

Trong ví dụ EXISTS, điều kiện:

~~~sql
o.customer_id = c.customer_id
~~~

tham chiếu đến alias c của truy vấn bên ngoài. Đây là correlated subquery (truy vấn con tương quan).

Có thể hình dung logic như sau:

1. Lấy một hàng khách hàng từ truy vấn ngoài.
2. Dùng customer_id của hàng đó làm điều kiện kiểm tra trong truy vấn con.
3. Nếu truy vấn con có ít nhất một hàng, EXISTS đúng.
4. Nếu không có hàng phù hợp, EXISTS sai.
5. Tiếp tục đánh giá khách hàng kế tiếp.

Đây là mô hình giải thích ngữ nghĩa, không phải lời khẳng định rằng MySQL luôn chạy một truy vấn con độc lập cho từng hàng. Optimizer có thể chuyển đổi correlated EXISTS thành semijoin hoặc chọn chiến lược khác nếu truy vấn đủ điều kiện.

### 3.1. Lọc theo nhiều điều kiện

Tìm khách hàng có ít nhất một đơn đã thanh toán:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Truy vấn con kiểm tra đồng thời quan hệ khách hàng và trạng thái đơn. Không cần GROUP BY hay COUNT nếu yêu cầu chỉ là có ít nhất một đơn.

### 3.2. Kiểm tra tồn tại trong khoảng thời gian

Tìm khách hàng có đơn thanh toán trong quý đầu năm 2026:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.created_at >= '2026-01-01'
      AND o.created_at <  '2026-04-01'
);
~~~

Điều kiện thời gian được đặt trong truy vấn con vì nó xác định đơn nào được xem là bằng chứng tồn tại. Khoảng nửa mở gồm ngày bắt đầu và không gồm ngày kết thúc giúp tránh phải tự tính giây cuối cùng của ngày.

### 3.3. Kiểm tra hàng con thỏa điều kiện trên bảng thứ ba

Tìm khách hàng có đơn chứa sản phẩm đang hoạt động:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    JOIN products AS p
        ON p.product_id = oi.product_id
    WHERE o.customer_id = c.customer_id
      AND p.active = TRUE
);
~~~

Truy vấn con có thể dùng JOIN nội bộ để xác định một hàng bằng chứng. EXISTS chỉ cần biết có ít nhất một tổ hợp đơn hàng, dòng chi tiết và sản phẩm phù hợp.

## 4. NOT EXISTS kiểm tra không tồn tại

NOT EXISTS đúng khi truy vấn con không trả về hàng nào. Nó thường dùng để tìm hàng cha chưa có hàng con tương ứng.

Ví dụ tìm khách hàng chưa từng đặt hàng:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Với mỗi khách hàng, MySQL tìm đơn hàng tương ứng. Nếu không tìm thấy đơn nào, NOT EXISTS đúng và khách hàng được giữ lại.

### 4.1. Tìm sản phẩm chưa từng được bán

~~~sql
SELECT
    p.product_id,
    p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
);
~~~

Truy vấn trả về sản phẩm không xuất hiện trong bất kỳ dòng chi tiết đơn hàng nào. Nó không cần đếm số lần xuất hiện; chỉ cần không có hàng khớp.

### 4.2. Tìm đơn hàng chưa có dòng chi tiết

~~~sql
SELECT o.order_id, o.customer_id, o.created_at
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.order_id = o.order_id
);
~~~

Đây là mẫu hữu ích để tìm dữ liệu chưa hoàn chỉnh hoặc bản ghi cha chưa có dữ liệu con.

### 4.3. Tìm khách hàng không có đơn đã thanh toán

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Điều kiện trong truy vấn con xác định chính xác loại hàng con cần loại trừ. Kết quả vẫn bao gồm khách hàng chưa có đơn nào và khách hàng chỉ có đơn ở trạng thái khác PAID.

Nếu yêu cầu là “đã có đơn nhưng không có đơn PAID”, cần kết hợp EXISTS và NOT EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS any_order
    WHERE any_order.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS paid_order
    WHERE paid_order.customer_id = c.customer_id
      AND paid_order.status = 'PAID'
);
~~~

Hai điều kiện diễn đạt hai yêu cầu độc lập: có ít nhất một đơn bất kỳ và không có đơn nào đã thanh toán.

## 5. EXISTS và JOIN khác nhau như thế nào?

JOIN kết hợp hàng từ hai bảng. Nếu một khách hàng có nhiều đơn, JOIN tạo một hàng kết quả cho mỗi đơn phù hợp. EXISTS chỉ kiểm tra có hàng phù hợp nên mỗi hàng khách hàng của truy vấn ngoài được xét như một đơn vị.

Ví dụ JOIN:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

Khách hàng có năm đơn có thể xuất hiện năm lần.

Ví dụ EXISTS:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Khách hàng chỉ xuất hiện một lần dù có bao nhiêu đơn.

| Nhu cầu | Cách viết thường phù hợp |
|---|---|
| Lấy cột từ cả hai bảng | JOIN |
| Lấy khách hàng và thông tin khách hàng có đơn | EXISTS |
| Lấy khách hàng chưa có đơn | NOT EXISTS |
| Đếm số đơn của mỗi khách hàng | JOIN + GROUP BY hoặc truy vấn tổng hợp |
| Kiểm tra có ít nhất một hàng phù hợp | EXISTS |
| Kiểm tra không có hàng phù hợp | NOT EXISTS |

Có thể dùng JOIN kết hợp DISTINCT để lấy khách hàng duy nhất:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.full_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

Kết quả có thể giống EXISTS, nhưng JOIN tạo ra các cặp hàng phù hợp trước khi DISTINCT loại trùng. DISTINCT có thể cần thêm bước loại trùng hoặc cấu trúc tạm. EXISTS diễn đạt trực tiếp hơn khi không cần cột của bảng con.

Không có quy tắc rằng EXISTS luôn nhanh hơn JOIN. Optimizer có thể biến đổi cả hai dạng; hãy chọn theo ý nghĩa dữ liệu rồi kiểm tra EXPLAIN trên workload thực tế.

## 6. EXISTS và IN

EXISTS và IN có thể diễn đạt nhiều truy vấn kiểm tra thành viên tương đương.

Tìm khách hàng có đơn:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Viết bằng EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Với khóa customer_id không NULL và phép so sánh bằng như ví dụ, hai truy vấn thường cho cùng tập khách hàng. Tuy nhiên, ngữ nghĩa NULL của IN và NOT IN cần được hiểu kỹ trước khi thay thế.

### 6.1. IN với truy vấn con

IN kiểm tra một biểu thức có bằng một giá trị trong tập do truy vấn con trả về hay không:

~~~sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
)
~~~

IN phù hợp khi diễn đạt membership trong một tập giá trị. Nó có thể dùng với danh sách literal hoặc subquery.

### 6.2. EXISTS kiểm tra hàng phù hợp

EXISTS kiểm tra truy vấn con có tạo ra hàng nào hay không:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

EXISTS thường tự nhiên hơn khi truy vấn con cần tham chiếu nhiều cột từ hàng ngoài hoặc cần diễn đạt nhiều điều kiện quan hệ.

## 7. Cẩn thận với NOT IN và NULL

Một khác biệt quan trọng giữa NOT IN và NOT EXISTS xuất hiện khi tập truy vấn con có NULL.

Giả sử truy vấn con trả về tập:

~~~text
10, 20, NULL
~~~

Điều kiện:

~~~sql
30 NOT IN (10, 20, NULL)
~~~

không thể được kết luận là TRUE. MySQL dùng logic ba giá trị: phép so sánh với NULL tạo UNKNOWN, và điều kiện WHERE chỉ giữ hàng khi biểu thức là TRUE. Vì vậy, truy vấn có thể không trả về hàng mà người viết mong đợi.

Ví dụ bảng nhập liệu có cột tham chiếu nullable:

~~~sql
CREATE TABLE imported_order_refs (
    customer_id BIGINT UNSIGNED NULL
) ENGINE = InnoDB;
~~~

Nếu bảng này có ít nhất một NULL, truy vấn sau có thể không trả về khách hàng nào:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT r.customer_id
    FROM imported_order_refs AS r
);
~~~

Lý do là với một customer_id không xuất hiện trong các giá trị khác, phép so sánh với NULL vẫn làm kết quả NOT IN thành UNKNOWN.

Viết lại bằng NOT EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM imported_order_refs AS r
    WHERE r.customer_id = c.customer_id
);
~~~

Một hàng NULL ở bảng imported_order_refs không thỏa phép so sánh bằng với customer_id của khách hàng, nên nó không làm các khách hàng không khớp khác bị loại khỏi kết quả. Đây là lý do NOT EXISTS thường an toàn và dễ hiểu hơn cho truy vấn anti-join khi cột con có thể NULL.

### 7.1. Nếu dùng NOT IN, phải xử lý NULL có chủ đích

Nếu ngữ nghĩa nghiệp vụ cho phép bỏ qua giá trị NULL trong tập con, có thể lọc NULL:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT r.customer_id
    FROM imported_order_refs AS r
    WHERE r.customer_id IS NOT NULL
);
~~~

Việc thêm IS NOT NULL thay đổi cách xử lý tập dữ liệu và cần phù hợp với nghiệp vụ. Nếu mục tiêu là “không có hàng con nào thỏa phép so sánh”, NOT EXISTS thường diễn đạt trực tiếp hơn.

### 7.2. NULL ở phía ngoài

NOT EXISTS cũng có quy tắc rõ ràng với giá trị ngoài là NULL. Ví dụ:

~~~sql
SELECT r.customer_id
FROM imported_order_refs AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = r.customer_id
);
~~~

Nếu r.customer_id là NULL, phép so sánh o.customer_id = r.customer_id không TRUE cho hàng nào. Truy vấn con không tìm thấy hàng phù hợp, vì vậy NOT EXISTS là TRUE và hàng có NULL được trả về.

Nếu không muốn lấy các hàng ngoài có khóa NULL, thêm điều kiện:

~~~sql
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = r.customer_id
  )
~~~

Nếu nghiệp vụ muốn xem hai giá trị NULL là cùng một giá trị để đối chiếu, MySQL có toán tử so sánh null-safe <=>. Chỉ dùng nó khi đó đúng là quy tắc nghiệp vụ; quan hệ khóa ngoại thông thường thường không xem NULL là một khóa tham chiếu.

## 8. LEFT JOIN ... IS NULL như một cách viết anti-join

Một cách khác để tìm hàng không có quan hệ là LEFT JOIN rồi kiểm tra cột phía phải là NULL:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

LEFT JOIN giữ mọi khách hàng. Nếu không có đơn phù hợp, các cột của orders được mở rộng thành NULL. Điều kiện WHERE o.order_id IS NULL giữ lại những khách hàng không tìm thấy đơn.

Hãy kiểm tra một cột phía phải chắc chắn NOT NULL khi hàng thực sự tồn tại, thường là primary key như order_id. Không nên kiểm tra một cột nullable như status IS NULL vì một hàng đơn hàng thật có thể có status NULL trong schema khác, làm điều kiện nhận nhầm hàng đó là không khớp.

So sánh:

~~~sql
-- Dùng NOT EXISTS
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);

-- Dùng LEFT JOIN ... IS NULL
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Hai dạng có thể cho cùng kết quả khi điều kiện nối và cột kiểm tra được chọn đúng. NOT EXISTS thường thể hiện ý định “không có hàng liên quan” rõ ràng hơn và tránh vô tình kiểm tra một cột nullable.

## 9. EXISTS không cần đếm tất cả hàng

Nếu chỉ cần biết có hàng phù hợp hay không, dùng EXISTS thay cho COUNT(*) > 0:

~~~sql
-- Diễn đạt trực tiếp kiểm tra tồn tại
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Một cách viết dựa trên đếm:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) > 0;
~~~

Cách thứ hai yêu cầu biểu thức đếm số hàng phù hợp để so sánh. EXISTS chỉ cần xác định có ít nhất một hàng. Optimizer có thể tối ưu cả hai dạng trong một số trường hợp, nhưng EXISTS diễn đạt đúng mục tiêu và tránh yêu cầu đếm khi không cần số lượng.

Một lỗi dễ gặp là:

~~~sql
WHERE EXISTS (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

Không dùng COUNT(*) như vậy để kiểm tra tồn tại. Truy vấn con có aggregate nhưng không có GROUP BY vẫn trả về một hàng tổng hợp ngay cả khi không có đơn; do đó EXISTS có thể luôn đúng. Hãy dùng SELECT 1 với điều kiện hàng, hoặc dùng COUNT(*) > 0 ở cấp biểu thức nếu thực sự cần số lượng.

## 10. EXISTS trong các yêu cầu nghiệp vụ thường gặp

### 10.1. Khách hàng có đơn trong khoảng thời gian gần đây

Nếu chỉ cần biết khách hàng có đơn trong 30 ngày gần đây, dùng EXISTS với mốc thời gian do ứng dụng hoặc truy vấn xác định:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.created_at >= CURRENT_DATE - INTERVAL 30 DAY
);
~~~

Đây là ví dụ minh họa cách đặt điều kiện thời gian trong truy vấn con. Với hệ thống nhiều múi giờ, cần thống nhất session time zone và ý nghĩa của cột created_at trước khi xác định “30 ngày gần đây”.

### 10.2. Khách hàng có ít nhất một đơn giá trị lớn

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.total >= 10000000
);
~~~

Không cần tính MAX(total) nếu chỉ hỏi có đơn nào đạt ngưỡng. Nếu cần trả giá trị đơn lớn nhất, dùng aggregate hoặc truy vấn lấy hàng tương ứng.

### 10.3. Sản phẩm chưa xuất hiện trong đơn đã thanh toán

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    JOIN orders AS o
        ON o.order_id = oi.order_id
    WHERE oi.product_id = p.product_id
      AND o.status = 'PAID'
);
~~~

Truy vấn giữ các sản phẩm không có dòng chi tiết nào thuộc đơn đã thanh toán. Sản phẩm vẫn có thể xuất hiện trong đơn nháp hoặc đơn đã hủy.

### 10.4. Tìm khách hàng có đơn nhưng chưa có đơn giao thành công

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'DELIVERED'
);
~~~

Hai predicate cho phép diễn đạt điều kiện kết hợp mà không phải đếm hoặc nhóm đơn hàng.

### 10.5. Tìm khách hàng đã mua tất cả sản phẩm bắt buộc

Một mẫu nâng cao là dùng hai lớp NOT EXISTS để diễn đạt “không tồn tại sản phẩm bắt buộc nào mà khách hàng chưa mua”.

Giả sử có bảng required_products(product_id) chứa danh sách sản phẩm cần có:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM required_products AS rp
    WHERE NOT EXISTS (
        SELECT 1
        FROM orders AS o
        JOIN order_items AS oi
            ON oi.order_id = o.order_id
        WHERE o.customer_id = c.customer_id
          AND oi.product_id = rp.product_id
          AND o.status = 'PAID'
    )
);
~~~

Đọc từ trong ra ngoài:

1. Truy vấn NOT EXISTS bên trong tìm sản phẩm bắt buộc mà khách hàng chưa mua trong đơn PAID.
2. NOT EXISTS bên ngoài kiểm tra không có sản phẩm bắt buộc nào như vậy.
3. Nếu không thiếu sản phẩm bắt buộc nào, khách hàng được chọn.

Nếu required_products rỗng, điều kiện ngoài cũng đúng với mọi khách hàng. Đây là hành vi logic của mệnh đề “đã mua tất cả phần tử trong tập rỗng”; nếu nghiệp vụ không muốn kết quả đó, cần kiểm tra danh sách bắt buộc không rỗng riêng.

## 11. EXISTS và phép biến đổi semijoin/antijoin

EXISTS thường tương ứng với ý tưởng **semijoin**: giữ hàng từ phía ngoài nếu có ít nhất một hàng khớp ở phía trong. Nó không nhân bản hàng ngoài theo số lượng hàng khớp.

NOT EXISTS tương ứng với ý tưởng **antijoin**: giữ hàng phía ngoài nếu không có hàng nào khớp ở phía trong.

MySQL có thể biến đổi một số truy vấn IN hoặc EXISTS thành semijoin để chọn chiến lược thực thi phù hợp. Với các truy vấn phủ định, optimizer cũng có thể áp dụng antijoin transformation trong những điều kiện nhất định. Việc biến đổi phụ thuộc cấu trúc truy vấn, NULL semantics, phiên bản và khả năng chứng minh tương đương.

Một số chiến lược semijoin mà MySQL có thể chọn gồm:

- **FirstMatch**: dừng tìm các hàng khớp tiếp theo khi đã tìm thấy hàng đầu tiên phù hợp cho tổ hợp tương ứng.
- **Duplicate Weedout**: loại bỏ các hàng trùng phát sinh từ cách thực thi join để giữ đúng ngữ nghĩa semijoin.
- **LooseScan**: dùng thứ tự index để lấy đại diện phù hợp từ các nhóm giá trị.
- **Materialization**: tạo tập kết quả trung gian của truy vấn con để tra cứu.
- **Table Pullout**: đưa bảng từ truy vấn con ra phần join bên ngoài khi điều kiện cho phép.

Đây là các lựa chọn của optimizer, không phải điều người viết truy vấn có thể ép buộc chỉ bằng việc dùng EXISTS. Hãy kiểm tra EXPLAIN thay vì giả định một chiến lược cụ thể.

## 12. Index cho correlated EXISTS và NOT EXISTS

Với truy vấn:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.created_at >= '2026-01-01'
);
~~~

Các điều kiện tra cứu phía orders gồm:

- So khớp customer_id với hàng ngoài.
- Lọc status bằng giá trị cố định.
- Lọc created_at theo khoảng.

Index ghép:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

có thể hỗ trợ tìm các hàng phù hợp theo thứ tự cột: điều kiện bằng trên customer_id, điều kiện bằng trên status, rồi điều kiện khoảng trên created_at. Tuy nhiên, index có ích đến đâu còn phụ thuộc số lượng dữ liệu, phân bố giá trị, thống kê và workload.

Với truy vấn kiểm tra sản phẩm có trong order_items:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
)
~~~

index bắt đầu bằng product_id hỗ trợ tìm dòng chi tiết theo sản phẩm. Nếu truy vấn đi theo order_id trước, primary key (order_id, product_id) lại phù hợp với đường tra cứu đó.

Nguyên tắc:

1. Xác định cột nối giữa truy vấn ngoài và truy vấn con.
2. Xác định các điều kiện lọc bổ sung trong truy vấn con.
3. Xem xét index ghép theo các điều kiện bằng trước, điều kiện khoảng sau.
4. Kiểm tra index hiện có để tránh tạo trùng lặp.
5. Đo bằng EXPLAIN và dữ liệu thực tế trước khi quyết định.

Không nên thêm index cho mọi điều kiện EXISTS. Index làm tăng chi phí INSERT, UPDATE, DELETE và dung lượng lưu trữ.

## 13. Đọc kế hoạch thực thi

Dùng EXPLAIN để xem MySQL dự định thực hiện truy vấn như thế nào:

~~~sql
EXPLAIN
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Các thông tin cần xem:

- Bảng nào được đọc trước.
- Access type và index được chọn.
- Số hàng ước lượng cần đọc.
- Điều kiện nào được dùng để truy cập index và điều kiện nào được lọc sau.
- Truy vấn con có được biến đổi thành semijoin hay materialize không.

Ở định dạng EXPLAIN JSON hoặc TREE, có thể quan sát chi tiết hơn về subquery, nested loop, semijoin hoặc materialization tùy phiên bản.

Nếu phiên bản hỗ trợ, EXPLAIN ANALYZE cho biết số liệu thực thi thực tế như thời gian và số hàng qua iterator. Lệnh này thực sự chạy truy vấn; chỉ dùng trên môi trường phù hợp và với truy vấn có chi phí đã được đánh giá.

Khi truy vấn chậm:

1. Kiểm tra index trên cột liên kết ở bảng con.
2. Kiểm tra điều kiện lọc có dùng được index không.
3. So sánh số hàng ước lượng với số hàng thực tế.
4. Cập nhật thống kê nếu optimizer có ước lượng sai đáng kể.
5. Đánh giá lại cấu trúc index theo workload, không chỉ một truy vấn.

## 14. Những lỗi thường gặp

**“EXISTS phải trả về một cột có giá trị.”** Không. EXISTS chỉ quan tâm có hàng hay không; SELECT 1 là cách viết phổ biến và dễ hiểu.

**“EXISTS luôn chạy truy vấn con một lần cho mỗi hàng ngoài.”** Đây là cách hiểu logic đơn giản. Optimizer có thể biến đổi truy vấn thành semijoin hoặc chọn chiến lược khác.

**“EXISTS luôn nhanh hơn JOIN.”** Không có quy tắc tuyệt đối. Chọn theo ý nghĩa: EXISTS để kiểm tra tồn tại, JOIN để lấy dữ liệu kết hợp; sau đó đo kế hoạch thực thi.

**“Dùng JOIN là luôn có một hàng cho mỗi hàng cha.”** Không. Một hàng cha có thể khớp nhiều hàng con và bị nhân bản. Nếu chỉ cần kiểm tra tồn tại, EXISTS tránh vấn đề đó một cách tự nhiên.

**“NOT IN và NOT EXISTS luôn tương đương.”** Không. NULL trong tập con có thể làm NOT IN thành UNKNOWN và loại các hàng ngoài không khớp. NOT EXISTS với điều kiện tương quan thường phù hợp hơn cho anti-join.

**“NOT EXISTS loại mọi hàng có khóa NULL.”** Không. Nếu khóa phía ngoài là NULL, phép so sánh bằng thường không khớp hàng nào, khiến NOT EXISTS đúng. Thêm IS NOT NULL nếu nghiệp vụ yêu cầu.

**“EXISTS với SELECT COUNT(*) là cách đếm tối ưu.”** Không. Truy vấn con có aggregate không GROUP BY vẫn trả một hàng tổng hợp ngay cả khi COUNT bằng 0; EXISTS có thể luôn đúng. Dùng SELECT 1 để kiểm tra hàng phù hợp.

**“Chỉ cần index ở bảng cha.”** Không. Correlated subquery thường cần tra cứu bảng con bằng khóa liên kết, nên index phía trong rất quan trọng.

## 15. Checklist chọn và tối ưu truy vấn tồn tại

Trước khi viết truy vấn, hãy xác định:

1. Có cần lấy dữ liệu từ bảng con hay chỉ cần biết có/không?
2. Một hàng ngoài có thể khớp nhiều hàng con không?
3. Điều kiện tương quan nào nối truy vấn con với hàng ngoài?
4. Có điều kiện lọc trạng thái, thời gian hoặc thuộc tính khác không?
5. Cột nào có thể NULL và NULL ảnh hưởng kết quả ra sao?
6. NOT EXISTS hay LEFT JOIN ... IS NULL thể hiện ý định rõ hơn?
7. Có đang dùng NOT IN trên một tập có thể chứa NULL không?
8. Index phía bảng con có hỗ trợ cột tương quan và điều kiện lọc không?
9. EXPLAIN cho thấy semijoin, antijoin, materialization hay access path nào?
10. Kết quả có giữ đúng số hàng ngoài mong đợi mà không bị nhân bản không?

Ví dụ tổng hợp: tìm khách hàng có đơn PAID trong năm 2026 nhưng chưa từng có đơn DELIVERED:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS paid
    WHERE paid.customer_id = c.customer_id
      AND paid.status = 'PAID'
      AND paid.created_at >= '2026-01-01'
      AND paid.created_at <  '2027-01-01'
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS delivered
    WHERE delivered.customer_id = c.customer_id
      AND delivered.status = 'DELIVERED'
);
~~~

EXISTS xác nhận có ít nhất một đơn PAID trong khoảng thời gian. NOT EXISTS xác nhận không có đơn DELIVERED ở bất kỳ thời điểm nào. Hai truy vấn con diễn đạt hai điều kiện độc lập trên cùng khách hàng.

## Kết luận

EXISTS kiểm tra truy vấn con có trả về ít nhất một hàng; NOT EXISTS kiểm tra không có hàng phù hợp. Chúng đặc biệt hữu ích cho correlated subquery, semijoin và anti-join: lọc hàng cha theo sự tồn tại của hàng con mà không làm nhân bản kết quả ngoài.

Hãy dùng EXISTS khi chỉ cần biết có, NOT EXISTS khi cần biết không có, JOIN khi cần lấy dữ liệu từ cả hai phía và IN khi muốn kiểm tra thành viên trong một tập giá trị. Cẩn thận với NULL trong NOT IN, chọn index cho cột tương quan và kiểm tra EXPLAIN để đánh giá cách MySQL thực thi truy vấn.
