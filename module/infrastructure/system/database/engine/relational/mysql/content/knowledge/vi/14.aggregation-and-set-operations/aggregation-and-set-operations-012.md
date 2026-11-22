# Kiểm chứng tổng hợp sau JOIN để tránh đếm hoặc cộng trùng

Bài học thuộc chương **Gom nhóm và tập hợp** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Khi tổng hợp dữ liệu từ nhiều bảng, điều quan trọng là hiểu số hàng mà JOIN tạo ra trước khi dùng `COUNT()`, `SUM()` hoặc các hàm tổng hợp khác.

Sau bài này, bạn có thể xác định grain (mức chi tiết) của dữ liệu, nhận diện fan-out do quan hệ một-nhiều hoặc nhiều-nhiều, giải thích vì sao JOIN làm số đếm và tổng tiền bị nhân lên, chọn cách tổng hợp trước JOIN, dùng `EXISTS` khi chỉ cần kiểm tra sự tồn tại và đối chiếu kết quả với số liệu gốc.

## 1. Vì sao tổng hợp sau JOIN có thể sai?

JOIN kết hợp các hàng dựa trên điều kiện liên kết. Nếu một hàng ở bảng cha khớp với nhiều hàng ở bảng con, hàng cha xuất hiện lặp lại trong kết quả JOIN.

Điều này là hành vi đúng của quan hệ dữ liệu. Vấn đề phát sinh khi ta áp dụng hàm tổng hợp lên các hàng đã bị nhân bản mà vẫn nghĩ mỗi hàng cha chỉ xuất hiện một lần.

Ví dụ:

- Một đơn hàng có 3 dòng hàng.
- Cùng đơn hàng đó có 2 lần thanh toán.
- JOIN đơn hàng với dòng hàng tạo 3 hàng.
- JOIN tiếp với thanh toán tạo \(3 \times 2 = 6\) hàng.

Mỗi dòng hàng xuất hiện hai lần và mỗi khoản thanh toán xuất hiện ba lần. Nếu cộng tiền hàng hoặc tiền thanh toán trên tập 6 hàng, kết quả sẽ bị nhân lên.

### Khái niệm grain

**Grain** là ý nghĩa của một hàng trong tập dữ liệu. Trước khi viết truy vấn tổng hợp, hãy diễn đạt rõ một hàng đại diện cho điều gì:

| Bảng | Grain của một hàng |
|---|---|
| `customers` | Một khách hàng |
| `orders` | Một đơn hàng |
| `order_items` | Một dòng hàng trong đơn hàng |
| `payments` | Một lần thanh toán |

Khi JOIN `orders`, `order_items` và `payments`, grain kết quả không còn là một đơn hàng. Nó là một tổ hợp giữa dòng hàng và lần thanh toán của đơn hàng đó.

Nếu một phép tổng hợp cần tính ở grain đơn hàng, nhưng đầu vào đã chuyển thành grain dòng hàng × lần thanh toán, thì các giá trị ở cấp đơn hàng hoặc cấp con có thể bị lặp.

Trước khi viết `GROUP BY`, hãy trả lời:

1. Một hàng kết quả cần đại diện cho khách hàng, đơn hàng, dòng hàng hay lần thanh toán?
2. Mỗi bảng tham gia có bao nhiêu hàng cho một khóa JOIN?
3. JOIN có thể tạo nhiều hàng cho một thực thể không?
4. Giá trị nào đang được cộng hoặc đếm ở grain nào?

## 2. Quan hệ một-nhiều và fan-out

Giả sử một đơn hàng có nhiều dòng hàng và nhiều lần thanh toán:

~~~text
orders
  order_id = 1001
      |
      +---- order_items
      |       item 1: 200
      |       item 2:  50
      |       item 3: 200
      |
      +---- payments
              payment 1: 150
              payment 2: 300
~~~

Khi chỉ JOIN với dòng hàng, đơn hàng có 3 hàng kết quả. Khi chỉ JOIN với thanh toán, đơn hàng có 2 hàng kết quả.

Khi JOIN cả hai bảng con trên cùng khóa `order_id`, mỗi dòng hàng ghép với mỗi lần thanh toán:

| Dòng hàng | Thanh toán | Giá trị dòng hàng | Giá trị thanh toán |
|---|---|---:|---:|
| Item 1 | Payment 1 | 200 | 150 |
| Item 1 | Payment 2 | 200 | 300 |
| Item 2 | Payment 1 | 50 | 150 |
| Item 2 | Payment 2 | 50 | 300 |
| Item 3 | Payment 1 | 200 | 150 |
| Item 3 | Payment 2 | 200 | 300 |

Kết quả có 6 hàng.

Tổng đúng ở bảng dòng hàng là:

\[
200 + 50 + 200 = 450
\]

Tổng đúng ở bảng thanh toán là:

\[
150 + 300 = 450
\]

Nhưng sau JOIN:

- Tổng dòng hàng thành \(450 \times 2 = 900\).
- Tổng thanh toán thành \(450 \times 3 = 1350\).

Đây là **fan-out**: số hàng bị mở rộng do một hàng khớp với nhiều hàng ở nhiều nhánh JOIN. Fan-out không phải lỗi của MySQL; nó là hệ quả của cardinality trong dữ liệu và điều kiện JOIN.

### Công thức tổng quát

Nếu một hàng cha có:

- \(m\) hàng ở bảng con A.
- \(n\) hàng ở bảng con B.

Với INNER JOIN và khi cả hai nhánh đều có hàng khớp, kết quả có thể có:

\[
m \times n
\]

hàng cho hàng cha đó.

Với LEFT JOIN, nếu một nhánh không có hàng khớp, MySQL vẫn giữ hàng phía trái và điền NULL cho cột phía phải. Vì vậy, khi xét riêng các nhánh độc lập, số hàng có thể được hình dung là `max(1, m) × max(1, n)` thay vì `m × n`; điều kiện JOIN bổ sung có thể làm số hàng nhỏ hơn.

Nếu có ba nhánh một-nhiều với lần lượt \(m\), \(n\), \(p\) hàng, số tổ hợp có thể là:

\[
m \times n \times p
\]

Vì thế, chỉ nhìn số hàng của từng bảng riêng lẻ không đủ để dự đoán kết quả tổng hợp sau JOIN.

## 3. Tạo bộ dữ liệu minh họa

Ta dùng bốn bảng:

- `customers`: khách hàng.
- `orders`: đơn hàng.
- `order_items`: dòng hàng của đơn hàng.
- `payments`: các lần thanh toán.

Bộ dữ liệu có ba khách hàng. Khách hàng thứ ba chưa có đơn hàng để kiểm tra hành vi `LEFT JOIN`.

### Cấu trúc dữ liệu

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_join_aggregation_lab;
USE mysql_join_aggregation_lab;

CREATE TABLE customers (
    customer_id INT NOT NULL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    item_id INT NOT NULL PRIMARY KEY,
    order_id INT NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id)
) ENGINE=InnoDB;

CREATE TABLE payments (
    payment_id INT NOT NULL PRIMARY KEY,
    order_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id)
) ENGINE=InnoDB;
~~~

### Dữ liệu mẫu

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Cuong');

INSERT INTO orders (order_id, customer_id)
VALUES
    (1001, 1),
    (1002, 1),
    (1003, 2);

INSERT INTO order_items
    (item_id, order_id, product_name, quantity, unit_price)
VALUES
    (1, 1001, 'Keyboard', 2, 100.00),
    (2, 1001, 'Mouse', 1, 50.00),
    (3, 1001, 'Dock', 1, 200.00),
    (4, 1002, 'Cable', 3, 20.00),
    (5, 1003, 'Monitor stand', 1, 80.00),
    (6, 1003, 'USB cable', 2, 30.00);

INSERT INTO payments (payment_id, order_id, amount, status)
VALUES
    (1, 1001, 150.00, 'SUCCESS'),
    (2, 1001, 300.00, 'SUCCESS'),
    (3, 1003, 140.00, 'SUCCESS');
~~~

Tổng tiền hàng đúng của từng đơn:

| Đơn hàng | Số dòng hàng | Tổng tiền hàng |
|---|---:|---:|
| 1001 | 3 | 450.00 |
| 1002 | 1 | 60.00 |
| 1003 | 2 | 140.00 |

Tổng thanh toán đúng:

| Đơn hàng | Số lần thanh toán | Tổng thanh toán |
|---|---:|---:|
| 1001 | 2 | 450.00 |
| 1002 | 0 | 0.00 |
| 1003 | 1 | 140.00 |

Các số liệu này là mốc đối chiếu để phát hiện tổng hợp sai sau JOIN.

## 4. Truy vấn sai: JOIN nhiều bảng con rồi SUM trực tiếp

Truy vấn sau có vẻ hợp lý: nối khách hàng, đơn hàng, dòng hàng và thanh toán rồi nhóm theo khách hàng.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COUNT(oi.item_id) AS item_line_count,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả sai ở các khách hàng có đơn hàng vừa nhiều dòng hàng vừa nhiều lần thanh toán:

| Khách hàng | Chỉ số | Kết quả truy vấn sai | Giá trị đúng |
|---|---|---:|---:|
| An | Số đơn hàng | 7 | 2 |
| An | Số dòng hàng | 7 | 4 |
| An | Tổng tiền hàng | 960.00 | 510.00 |
| An | Tổng thanh toán | 1350.00 | 450.00 |
| Binh | Số đơn hàng | 2 | 1 |
| Binh | Số dòng hàng | 2 | 2 |
| Binh | Tổng tiền hàng | 280.00 | 140.00 |
| Binh | Tổng thanh toán | 280.00 | 140.00 |

Với khách hàng An:

- Đơn 1001 có 3 dòng hàng và 2 thanh toán, tạo 6 hàng.
- Đơn 1002 có 1 dòng hàng và không có thanh toán, tạo 1 hàng do LEFT JOIN.
- Tổng cộng có 7 hàng trong kết quả JOIN.

Vì vậy:

- `COUNT(o.order_id)` đếm 7 lần xuất hiện của đơn hàng, thay vì 2 đơn.
- `COUNT(oi.item_id)` đếm 7 lần xuất hiện của dòng hàng, thay vì 4 dòng.
- Tổng tiền hàng của đơn 1001 bị nhân đôi do có 2 lần thanh toán.
- Tổng thanh toán của đơn 1001 bị nhân ba do có 3 dòng hàng.

Kết quả của khách hàng Binh cũng sai ở tổng tiền: hai dòng hàng ghép với một khoản thanh toán nên mỗi dòng và khoản thanh toán đều bị lặp hai lần.

**Không phải mọi hàng đều sai theo cùng một hệ số.** Hệ số fan-out phụ thuộc số hàng khớp của từng đơn. Điều này khiến lỗi khó phát hiện nếu chỉ kiểm tra một vài tổng cuối cùng.

## 5. COUNT(DISTINCT) sửa được gì và không sửa được gì?

Một phản ứng thường gặp là thêm DISTINCT vào các phép đếm:

~~~sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(DISTINCT oi.item_id) AS item_line_count,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id;
~~~

Hai phép đếm đã được sửa vì:

- `COUNT(DISTINCT o.order_id)` đếm các mã đơn hàng khác nhau.
- `COUNT(DISTINCT oi.item_id)` đếm các mã dòng hàng khác nhau.

Nhưng hai phép SUM vẫn bị nhân bản. COUNT DISTINCT không làm thay đổi số hàng đầu vào của SUM.

### Vì sao SUM(DISTINCT amount) không phải cách sửa tổng quát?

Có thể nghĩ đến:

~~~sql
SUM(DISTINCT oi.quantity * oi.unit_price)
~~~

Cách này loại các giá trị số trùng nhau, không loại các bản sao của cùng một dòng hàng dựa trên khóa `item_id`.

Trong dữ liệu mẫu của đơn 1001:

- Dòng hàng 1 có giá trị 200.
- Dòng hàng 2 có giá trị 50.
- Dòng hàng 3 cũng có giá trị 200.

Tổng đúng là:

\[
200 + 50 + 200 = 450
\]

Nhưng `SUM(DISTINCT ...)` chỉ cộng mỗi giá trị số một lần:

\[
200 + 50 = 250
\]

Kết quả thấp hơn thực tế vì hai dòng hàng hợp lệ có cùng số tiền.

Tương tự, hai lần thanh toán có thể có cùng số tiền. `SUM(DISTINCT p.amount)` sẽ gộp chúng thành một giá trị, dù đó là hai giao dịch khác nhau.

Hãy nhớ:

- `COUNT(DISTINCT primary_key)` thường phù hợp khi muốn đếm số thực thể duy nhất sau JOIN.
- `SUM(DISTINCT measure)` chỉ phù hợp khi nghiệp vụ thật sự muốn cộng các **giá trị khác nhau**, không phải các bản ghi khác nhau.
- DISTINCT không thể thay thế việc hiểu grain và cardinality của dữ liệu.

## 6. Cách đúng: tổng hợp từng bảng con trước khi JOIN

Với ví dụ này, mục tiêu là báo cáo theo khách hàng. Ta cần:

1. Tính tổng và số dòng hàng theo từng đơn.
2. Tính tổng và số lần thanh toán theo từng đơn.
3. JOIN các kết quả đã được thu gọn về một hàng cho mỗi đơn.
4. Nhóm theo khách hàng.

MySQL 8.0 trở lên hỗ trợ CTE bằng `WITH`. Ví dụ dưới đây sử dụng CTE để thể hiện rõ từng bước.

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(it.item_line_count), 0) AS item_line_count,
    COALESCE(SUM(it.item_total), 0.00) AS item_total,
    COALESCE(SUM(pt.payment_count), 0) AS payment_count,
    COALESCE(SUM(pt.paid_total), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY c.customer_id;
~~~

Mỗi CTE có grain rõ ràng:

| CTE | Grain | Số hàng tối đa cho một order_id |
|---|---|---:|
| `item_totals` | Một đơn hàng | 1 |
| `payment_totals` | Một đơn hàng | 1 |

Khi JOIN hai CTE với `orders`, mỗi đơn hàng vẫn chỉ có tối đa một hàng tổng hợp dòng hàng và một hàng tổng hợp thanh toán. Các nhánh con không còn nhân chéo với nhau.

Kết quả đúng:

| Khách hàng | Số đơn | Số dòng hàng | Tổng tiền hàng | Số thanh toán | Đã thanh toán |
|---|---:|---:|---:|---:|---:|
| An | 2 | 4 | 510.00 | 2 | 450.00 |
| Binh | 1 | 2 | 140.00 | 1 | 140.00 |
| Cuong | 0 | 0 | 0.00 | 0 | 0.00 |

### Vì sao cần COALESCE sau SUM?

Với khách hàng không có đơn hàng hoặc đơn hàng không có dữ liệu con, các cột tổng hợp có thể là NULL sau LEFT JOIN.

Ví dụ:

- `SUM(it.item_total)` không có giá trị đầu vào khác NULL thì trả NULL.
- `COALESCE(..., 0.00)` chuyển kết quả đó thành 0 để báo cáo hiển thị.

Chỉ thay NULL bằng 0 nếu nghiệp vụ xem “không có bản ghi” tương đương tổng bằng 0. Trong báo cáo phân tích, đôi khi cần giữ NULL để phân biệt “không có dữ liệu” với “đã có dữ liệu và tổng bằng 0”.

### CTE không phải là một bảng lưu sẵn

CTE là cách đặt tên cho một truy vấn trong phạm vi câu lệnh. Optimizer có thể xử lý, gộp hoặc materialize CTE tùy cấu trúc và kế hoạch. Tính đúng của cách làm đến từ việc mỗi nhánh đã tạo ra tối đa một hàng trên mỗi `order_id`, không phải vì CTE nhất thiết được ghi ra bảng vật lý.

Có thể viết cùng ý tưởng bằng derived table:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(it.item_total), 0.00) AS item_total,
    COALESCE(SUM(pt.paid_total), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
) AS it
    ON it.order_id = o.order_id
LEFT JOIN (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
) AS pt
    ON pt.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name;
~~~

## 7. Khi chỉ cần kiểm tra sự tồn tại, dùng EXISTS

Nếu mục tiêu là tìm đơn hàng có ít nhất một lần thanh toán, không cần JOIN tất cả các lần thanh toán:

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
);
~~~

EXISTS kiểm tra có ít nhất một hàng thỏa điều kiện. Nó không nhân bản hàng của `orders` theo số lần thanh toán.

Nếu dùng JOIN:

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
JOIN payments AS p
    ON p.order_id = o.order_id;
~~~

Đơn 1001 xuất hiện hai lần vì có hai khoản thanh toán.

Nếu chỉ muốn biết đơn nào có thanh toán, EXISTS diễn đạt đúng ý định hơn. Tương tự, có thể dùng NOT EXISTS để tìm đơn chưa có thanh toán:

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
);
~~~

EXISTS không phải lúc nào cũng nhanh hơn JOIN trong mọi tình huống; optimizer có thể chuyển đổi cả hai cách. Lợi ích quan trọng ở đây là biểu đạt phép kiểm tra tồn tại mà không đưa các hàng con vào tập kết quả cần tổng hợp.

## 8. Tổng hợp khi chỉ JOIN một nhánh một-nhiều

JOIN một bảng con rồi tổng hợp có thể hoàn toàn đúng nếu bạn muốn tổng hợp ở grain của bảng con.

Ví dụ, tính tổng tiền hàng theo khách hàng:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(oi.item_id) AS item_line_count,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name;
~~~

Ở đây chỉ có một nhánh một-nhiều là `order_items`; mỗi dòng hàng xuất hiện một lần. Vì vậy SUM tiền hàng không bị nhân chéo với bảng thanh toán.

Nhưng nếu bổ sung `payments` vào truy vấn, grain thay đổi và tổng tiền hàng có thể bị lặp. Khi truy vấn phát triển, hãy đánh giá lại cardinality sau mỗi JOIN. Một truy vấn đúng trước khi thêm bảng có thể trở thành sai sau khi thêm một quan hệ một-nhiều khác.

### Tổng hợp riêng theo từng grain

Nếu cần cả số đơn và số dòng hàng:

- `COUNT(DISTINCT o.order_id)` có thể đếm đơn hàng duy nhất sau JOIN một-nhiều.
- `COUNT(oi.item_id)` đếm số dòng hàng nếu mỗi dòng hàng chỉ xuất hiện một lần.
- `SUM(oi.quantity * oi.unit_price)` cộng tiền hàng nếu không có nhánh JOIN khác nhân bản dòng hàng.

Khi có thêm nhiều bảng con, nên tổng hợp riêng trước JOIN thay vì tiếp tục thêm DISTINCT vào từng biểu thức.

## 9. COUNT(*) và COUNT(child_id) khi dùng LEFT JOIN

LEFT JOIN giữ hàng bên trái ngay cả khi không có hàng khớp ở bảng phải. Trong trường hợp không có hàng con, MySQL tạo một hàng kết quả với các cột phía phải là NULL.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Với khách hàng Cuong không có đơn:

- `COUNT(*)` trả 1 vì LEFT JOIN vẫn tạo một hàng đại diện cho khách hàng.
- `COUNT(o.order_id)` trả 0 vì cột khóa đơn hàng là NULL ở hàng không khớp.

Nếu đếm hàng con sau LEFT JOIN, hãy dùng một cột khóa của bảng con không thể NULL, thường là primary key:

~~~sql
COUNT(o.order_id)
COUNT(oi.item_id)
COUNT(p.payment_id)
~~~

Không dùng `COUNT(*)` để đếm số hàng con khi truy vấn có LEFT JOIN.

Nếu có nhiều nhánh một-nhiều, ngay cả `COUNT(child_id)` vẫn có thể bị nhân bản bởi nhánh khác. Khi đó, cần COUNT DISTINCT theo khóa thực thể hoặc tổng hợp nhánh trước.

## 10. Các tình huống cần cẩn thận khác

### Một bảng có nhiều quan hệ con độc lập

Ví dụ một khách hàng có nhiều địa chỉ và nhiều số điện thoại. JOIN cả hai bảng trực tiếp theo `customer_id` sẽ tạo mọi tổ hợp địa chỉ × số điện thoại.

Nếu khách hàng có 3 địa chỉ và 2 số điện thoại, kết quả có 6 hàng. COUNT địa chỉ hoặc số điện thoại đều có thể bị nhân đôi.

Hãy tổng hợp mỗi bảng con theo customer trước khi JOIN nếu báo cáo cần một hàng cho mỗi khách hàng.

### Quan hệ nhiều-nhiều qua bảng trung gian

Một bài viết có thể gắn nhiều tag và một tag có thể thuộc nhiều bài viết. JOIN `articles`, `article_tags`, `tags` làm mỗi bài xuất hiện một lần cho mỗi tag.

Nếu cộng một giá trị ở cấp bài viết sau JOIN, giá trị đó sẽ được lặp theo số tag. Nếu mục tiêu là đếm tag, đó là đúng; nếu mục tiêu là tổng lượt xem của bài viết, cần tổng hợp ở grain bài viết trước hoặc dùng một phép đếm phù hợp.

### Phân bổ giá trị qua nhiều nhóm

Có những báo cáo muốn chia doanh thu của một đơn hàng cho nhiều chiến dịch hoặc nhiều bộ phận. Trong trường hợp đó, việc một giá trị xuất hiện nhiều lần có thể là chủ ý, nhưng phải có quy tắc phân bổ rõ ràng.

Ví dụ, đơn hàng có doanh thu 100 được phân bổ 60% cho chiến dịch A và 40% cho chiến dịch B:

| Chiến dịch | Tỷ lệ | Doanh thu phân bổ |
|---|---:|---:|
| A | 0.60 | 60.00 |
| B | 0.40 | 40.00 |

Công thức cần dùng là:

\[
\text{allocated amount} = \text{order amount} \times \text{allocation weight}
\]

Tổng trọng số của các nhóm phải được kiểm chứng theo quy tắc nghiệp vụ, thường bằng 1. Không được đơn giản JOIN rồi SUM cùng một order amount cho từng nhóm nếu muốn bảo toàn tổng doanh thu.

### Điều kiện lọc đặt trong ON hay WHERE

Với LEFT JOIN, điều kiện ở ON và WHERE có thể tạo kết quả khác nhau:

~~~sql
-- Giữ tất cả đơn hàng, chỉ nối thanh toán đã thành công
SELECT o.order_id, p.amount
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
   AND p.status = 'SUCCESS';
~~~

~~~sql
-- WHERE loại các hàng không có payment thành công
SELECT o.order_id, p.amount
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
WHERE p.status = 'SUCCESS';
~~~

Ở truy vấn thứ hai, điều kiện WHERE loại hàng có `p.status IS NULL`, khiến kết quả gần như INNER JOIN đối với điều kiện này. Điều đó có thể làm mất đơn chưa thanh toán. Hãy đặt điều kiện đúng vị trí trước khi tổng hợp.

## 11. Quy trình kiểm chứng một truy vấn tổng hợp sau JOIN

Dùng quy trình này khi viết báo cáo hoặc điều tra tổng tiền, số lượng bị lệch.

### Bước 1: xác định grain mong muốn

Viết bằng một câu: “Mỗi hàng kết quả đại diện cho một khách hàng” hoặc “mỗi hàng kết quả đại diện cho một đơn hàng”.

### Bước 2: xác định khóa và cardinality

Với từng JOIN, ghi lại quan hệ:

| JOIN | Cardinality thường gặp |
|---|---|
| `orders.customer_id → customers.customer_id` | Nhiều đơn đến một khách hàng |
| `order_items.order_id → orders.order_id` | Nhiều dòng hàng đến một đơn |
| `payments.order_id → orders.order_id` | Nhiều lần thanh toán đến một đơn |

Kiểm tra khóa được dùng có duy nhất ở phía được kỳ vọng là một hay không.

### Bước 3: đo số hàng sau từng JOIN

~~~sql
SELECT COUNT(*) AS rows_after_orders
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id;

SELECT COUNT(*) AS rows_after_items
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id;

SELECT COUNT(*) AS rows_after_items_and_payments
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id;
~~~

Số hàng tăng mạnh sau khi thêm một bảng con là dấu hiệu cần kiểm tra fan-out. Tuy nhiên, số hàng tăng không tự chứng minh truy vấn sai; hãy đối chiếu với cardinality dự kiến.

Với bộ dữ liệu lab:

- Sau JOIN customers với orders: 4 hàng (An có 2, Binh có 1, Cuong có 1 hàng NULL-extended).
- Sau khi thêm order_items: 7 hàng.
- Sau khi thêm payments: 10 hàng.

Sự tăng từ 7 lên 10 hàng phản ánh các dòng hàng của đơn 1001 được ghép với hai lần thanh toán. Đây là dấu hiệu để kiểm tra tổng hợp, không phải bằng chứng rằng JOIN sai.

### Bước 4: kiểm tra một khóa cụ thể

~~~sql
SELECT
    o.order_id,
    oi.item_id,
    p.payment_id,
    oi.quantity * oi.unit_price AS item_amount,
    p.amount AS payment_amount
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY oi.item_id, p.payment_id;
~~~

Quan sát các item và payment lặp lại. Kiểm tra số tổ hợp có khớp với số dòng hàng × số lần thanh toán không.

### Bước 5: đối chiếu tổng độc lập

Tính tổng tiền hàng từ đúng bảng dòng hàng:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS expected_item_total
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.customer_id;
~~~

Tính tổng thanh toán từ đúng bảng thanh toán:

~~~sql
SELECT
    o.customer_id,
    SUM(p.amount) AS expected_paid_total
FROM orders AS o
JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY o.customer_id;
~~~

Đây là các số liệu đối chiếu độc lập. Nếu truy vấn báo cáo tổng hợp cả hai nhánh, hãy so sánh từng chỉ số với kết quả tương ứng.

### Bước 6: tổng hợp trước JOIN và so sánh

Viết CTE hoặc derived table cho từng nhánh một-nhiều. Khi CTE GROUP BY đúng khóa `order_id`, cấu trúc truy vấn đã bảo đảm tối đa một hàng trên mỗi đơn. Truy vấn kiểm tra dưới đây hữu ích nếu nguồn tổng hợp là bảng summary hoặc view được tạo ở nơi khác; với CTE vừa viết, nó sẽ luôn trả 0 hàng theo cấu trúc:

~~~sql
WITH item_totals AS (
    SELECT order_id, SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
)
SELECT
    order_id,
    COUNT(*) AS rows_per_order
FROM item_totals
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Nếu kiểm tra một nguồn summary độc lập và có hàng trả về, grain của nguồn đó chưa đúng với khóa JOIN dự kiến.

### Bước 7: kiểm tra kế hoạch thực thi

Dùng EXPLAIN để xem cách MySQL đọc bảng, chọn index và ước lượng số hàng:

~~~sql
EXPLAIN
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
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
    o.order_id,
    it.item_total,
    pt.paid_total
FROM orders AS o
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id;
~~~

EXPLAIN giúp kiểm tra hiệu năng và kế hoạch JOIN; nó không tự chứng minh phép tổng hợp đúng về mặt nghiệp vụ. Tính đúng vẫn phải được xác nhận bằng grain, cardinality và số liệu đối chiếu.

## 12. Bài thực hành: sửa báo cáo doanh thu sau JOIN

Dùng database lab đã tạo ở phần 3.

### Bước 1: chạy truy vấn gây fan-out

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Ghi lại kết quả và giải thích tại sao An có 7 lần xuất hiện của đơn hàng.

### Bước 2: thử COUNT DISTINCT và SUM DISTINCT

~~~sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(DISTINCT oi.item_id) AS item_line_count,
    SUM(DISTINCT oi.quantity * oi.unit_price) AS distinct_item_amounts,
    SUM(DISTINCT p.amount) AS distinct_payment_amounts
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Đối chiếu với số liệu đúng. Giải thích vì sao tổng các giá trị dòng hàng DISTINCT của An không còn là 510.00.

### Bước 3: tổng hợp từng bảng con theo đơn hàng

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(it.item_line_count), 0) AS item_line_count,
    COALESCE(SUM(it.item_total), 0.00) AS item_total,
    COALESCE(SUM(pt.payment_count), 0) AS payment_count,
    COALESCE(SUM(pt.paid_total), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả kỳ vọng:

| Khách hàng | Số đơn | Dòng hàng | Tổng tiền hàng | Số lần thanh toán | Tổng thanh toán |
|---|---:|---:|---:|---:|---:|
| An | 2 | 4 | 510.00 | 2 | 450.00 |
| Binh | 1 | 2 | 140.00 | 1 | 140.00 |
| Cuong | 0 | 0 | 0.00 | 0 | 0.00 |

### Bước 4: dùng EXISTS để tìm đơn chưa thanh toán

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
);
~~~

Kết quả kỳ vọng là đơn 1002. Giải thích vì sao EXISTS/NOT EXISTS không tạo thêm hàng theo số lần thanh toán.

### Bước 5: dọn dẹp

~~~sql
DROP DATABASE mysql_join_aggregation_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh này xóa toàn bộ bảng và dữ liệu thực hành.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tổng tiền tăng sau khi thêm JOIN | Bảng mới có nhiều hàng khớp cho cùng khóa cha | Kiểm tra fan-out và tổng hợp nhánh trước JOIN |
| COUNT đơn hàng lớn hơn thực tế | Một đơn xuất hiện nhiều lần do JOIN bảng con | Dùng COUNT DISTINCT theo khóa đơn hoặc giữ grain một hàng/đơn |
| COUNT(*) trả 1 dù khách hàng không có đơn | LEFT JOIN vẫn giữ một hàng phía trái | Đếm khóa không NULL của bảng phải, ví dụ COUNT(o.order_id) |
| COUNT(DISTINCT) đúng nhưng SUM vẫn sai | DISTINCT chỉ áp dụng cho phép đếm đã sửa | Tổng hợp số tiền ở grain đúng trước JOIN |
| SUM(DISTINCT amount) thấp hơn thực tế | Hai bản ghi hợp lệ có cùng giá trị tiền bị gộp | SUM theo bản ghi sau khi loại nguyên nhân nhân hàng, không DISTINCT trên measure |
| Một nhánh JOIN làm số hàng tăng theo cấp số nhân | Nhiều quan hệ một-nhiều hoặc nhiều-nhiều được nối đồng thời | Đo cardinality từng nhánh và pre-aggregate |
| Đơn không có bản ghi con biến mất | Điều kiện của bảng phải đặt trong WHERE sau LEFT JOIN | Đưa điều kiện phù hợp vào ON hoặc dùng EXISTS |
| Tổng không có dữ liệu trả NULL | SUM không có giá trị khác NULL | Dùng COALESCE nếu nghiệp vụ muốn hiển thị 0 |
| Truy vấn sau khi pre-aggregate chậm | Thiếu index khóa ngoại hoặc quét dữ liệu lớn | Kiểm tra index, lọc sớm phù hợp và EXPLAIN |
| Báo cáo không khớp bảng nguồn | Dùng sai grain hoặc phạm vi lọc khác nhau | Đối chiếu cùng điều kiện lọc và cùng kỳ dữ liệu |

## 14. Checklist kiểm chứng trước khi phát hành báo cáo

- [ ] Đã xác định grain của từng bảng và grain của kết quả cuối.
- [ ] Đã ghi rõ khóa JOIN và cardinality dự kiến của mỗi quan hệ.
- [ ] Đã kiểm tra khóa phía “một” là duy nhất theo ràng buộc hoặc dữ liệu thực tế.
- [ ] Đã đo số hàng sau từng bước JOIN.
- [ ] Đã kiểm tra một số khóa cụ thể có nhiều bản ghi con.
- [ ] Đã xác nhận không có nhánh một-nhiều nào nhân bản measure của nhánh khác.
- [ ] Đã dùng COUNT trên khóa phù hợp thay vì COUNT(*) trong trường hợp LEFT JOIN.
- [ ] Chỉ dùng COUNT(DISTINCT primary_key) khi cần đếm thực thể duy nhất.
- [ ] Không dùng SUM(DISTINCT measure) như một cách chữa fan-out.
- [ ] Đã tổng hợp từng bảng con về grain cha trước khi nối các nhánh độc lập.
- [ ] Đã cân nhắc EXISTS khi chỉ cần kiểm tra có/không có hàng liên quan.
- [ ] Đã kiểm tra điều kiện lọc ở ON và WHERE, đặc biệt với LEFT JOIN.
- [ ] Đã đối chiếu từng tổng với truy vấn nguồn độc lập.
- [ ] Đã kiểm tra trường hợp không có dữ liệu và quyết định cách hiển thị NULL/0.
- [ ] Đã dùng EXPLAIN để đánh giá hiệu năng sau khi xác nhận logic đúng.

## 15. Nguyên tắc cần ghi nhớ

1. JOIN có thể nhân số hàng khi một hàng khớp với nhiều hàng ở bảng khác.
2. Grain của tập kết quả thay đổi sau mỗi quan hệ một-nhiều hoặc nhiều-nhiều.
3. Khi JOIN hai nhánh một-nhiều độc lập, số tổ hợp có thể bằng tích số hàng của hai nhánh.
4. COUNT và SUM chỉ đúng khi đầu vào có grain phù hợp với điều đang đếm hoặc cộng.
5. COUNT(DISTINCT primary_key) có thể sửa số đếm thực thể, nhưng không sửa tổng tiền bị nhân.
6. SUM(DISTINCT value) loại giá trị số trùng nhau, không nhận diện bản ghi trùng do JOIN.
7. Tổng hợp từng bảng con về một hàng trên mỗi khóa cha trước khi JOIN là cách an toàn cho báo cáo nhiều nhánh.
8. Dùng EXISTS hoặc NOT EXISTS khi chỉ cần kiểm tra sự tồn tại.
9. Với LEFT JOIN, COUNT(*) vẫn đếm hàng giữ lại phía trái; dùng COUNT khóa phía phải để đếm hàng khớp.
10. Kiểm chứng bằng grain, cardinality, truy vấn đối chiếu và EXPLAIN trước khi phát hành báo cáo.

## Tài liệu tham khảo chính thức

Các cú pháp và hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [JOIN Clause](https://dev.mysql.com/doc/refman/9.7/en/join.html): cú pháp JOIN, INNER/LEFT JOIN và điều kiện kết hợp bảng.
2. [Aggregate Function Descriptions](https://dev.mysql.com/doc/refman/9.7/en/aggregate-functions.html): COUNT, COUNT(DISTINCT), SUM, AVG và cách hàm tổng hợp xử lý NULL.
3. [MySQL Handling of GROUP BY](https://dev.mysql.com/doc/refman/9.7/en/group-by-handling.html): quy tắc GROUP BY, ONLY_FULL_GROUP_BY và phụ thuộc hàm.
4. [Subqueries with EXISTS or NOT EXISTS](https://dev.mysql.com/doc/refman/9.7/en/exists-and-not-exists-subqueries.html): kiểm tra sự tồn tại mà không cần đưa các hàng con vào kết quả.
5. [Common Table Expressions](https://dev.mysql.com/doc/refman/9.7/en/with.html): cú pháp WITH và CTE.
6. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): đọc kế hoạch thực thi của truy vấn.
7. [Optimization and Indexes](https://dev.mysql.com/doc/refman/9.7/en/optimization-indexes.html): index cho điều kiện JOIN và truy vấn tổng hợp.

