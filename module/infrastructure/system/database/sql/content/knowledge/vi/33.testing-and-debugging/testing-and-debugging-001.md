# Xác định tập kết quả mong đợi và mức chi tiết từng hàng

Một câu truy vấn có thể chạy thành công nhưng vẫn trả kết quả sai. Có thể nó thừa hàng, thiếu hàng, nhân đôi một đơn, tính tổng sai hoặc làm mất những hàng chưa có dữ liệu liên quan. Lỗi thường xuất hiện khi ta không xác định rõ **một hàng trong kết quả đại diện cho điều gì** và **chính xác những hàng nào phải xuất hiện**.

Ví dụ, yêu cầu “liệt kê đơn hàng cùng tổng tiền” có thể có nhiều cách hiểu:

- Một hàng cho mỗi đơn hàng.
- Một hàng cho mỗi sản phẩm trong đơn.
- Một hàng cho mỗi lần thanh toán.
- Một hàng cho mỗi cặp đơn hàng và sản phẩm.

Nếu truy vấn JOIN ba bảng có quan hệ một-nhiều, kết quả có thể có nhiều hàng hơn số đơn hàng. Nếu kiểm thử chỉ nhìn vài dòng đầu hoặc chỉ so tổng số hàng, lỗi nhân bản có thể bị bỏ sót.

Bài học **Database SQL → Kiểm thử và gỡ lỗi** hướng dẫn cách xác định một kết quả SQL có thể kiểm chứng:

1. Viết hợp đồng kết quả trước khi viết truy vấn: cột, kiểu dữ liệu, ý nghĩa và điều kiện xuất hiện.
2. Xác định **grain** (mức chi tiết) — một hàng đại diện cho một thực thể hay một tổ hợp thực thể nào.
3. Dự đoán cardinality và phát hiện JOIN làm nhân bản hoặc loại bỏ hàng.
4. Xây dựng tập dữ liệu nhỏ có kết quả mong đợi rõ ràng, gồm NULL, trùng lặp và trường hợp biên.
5. So sánh actual result với expected result theo giá trị, số hàng, tính duy nhất và thứ tự khi thứ tự có ý nghĩa.
6. Phân biệt lỗi logic SQL với khác biệt về kiểu, độ chính xác số, thời gian, transaction snapshot và cách hiển thị của client.

Các ví dụ chính dùng **PostgreSQL**, với lưu ý cho SQL Server, MySQL, Oracle và SQLite. Tên đối tượng bắt đầu bằng lab_r414_ để giới hạn phạm vi bài thực hành. Chạy các lệnh tạo dữ liệu trong database sandbox.

## 1. Kết quả mong đợi là một hợp đồng

Trước khi viết SQL, hãy mô tả kết quả cần nhận được. Một hợp đồng kết quả tốt trả lời:

| Thành phần | Câu hỏi cần xác định |
| --- | --- |
| Mục đích | Truy vấn giải quyết yêu cầu nghiệp vụ nào? |
| Grain | Mỗi hàng đại diện cho đơn hàng, dòng hàng, khách hàng hay một cặp? |
| Columns | Cần trả những cột nào, tên và ý nghĩa của chúng là gì? |
| Types | Kiểu dữ liệu, khả năng NULL và độ chính xác ra sao? |
| Row inclusion | Hàng nào phải xuất hiện, hàng nào phải bị loại? |
| Uniqueness | Khóa nào phải duy nhất trong kết quả? |
| Relationships | Quan hệ JOIN là một-một, một-nhiều hay nhiều-nhiều? |
| Aggregation | Tổng, đếm, trung bình được tính trên tập hàng nào? |
| Ordering | Có cần thứ tự xác định không? Nếu có, tiêu chí phụ là gì? |
| Time boundary | Khoảng ngày giờ theo múi giờ nào và biên có bao gồm không? |
| Error behavior | Dữ liệu không hợp lệ bị từ chối, bỏ qua hay trả mã lỗi nào? |

### 1.1. Ví dụ hợp đồng báo cáo đơn hàng

Yêu cầu: “Liệt kê các đơn hàng cùng thông tin khách và tổng giá trị các dòng hàng.”

Ta cụ thể hóa:

- **Một hàng cho mỗi đơn hàng**, kể cả đơn chưa có dòng hàng.
- Có mã đơn, mã khách, trạng thái và tổng tiền hàng.
- Tổng tiền hàng bằng tổng số lượng nhân đơn giá của từng dòng.
- Đơn chưa có dòng hàng có tổng bằng 0.
- Một đơn chỉ xuất hiện một lần.
- Thứ tự tăng dần theo mã đơn nếu kết quả được dùng để so sánh hoặc phân trang.

Hợp đồng này giúp phát hiện ngay một truy vấn trả hai hàng cho đơn có hai sản phẩm: truy vấn đang trả theo **dòng hàng**, không theo **đơn hàng**.

### 1.2. Kết quả trông hợp lý chưa chắc đã đúng

Một kết quả có thể có đúng số hàng nhưng sai nội dung; có đúng tổng tiền nhưng phân bổ sai giữa các đơn; có đúng mã đơn nhưng lặp mã; hoặc có đúng vài hàng đầu nhưng thiếu hàng ở trang sau. Vì vậy, **ảnh chụp kết quả không phải là đặc tả kiểm thử**. Hãy xác định những bất biến có thể kiểm tra.

## 2. Grain — mức chi tiết của một hàng

**Grain** là đơn vị dữ liệu mà mỗi hàng của bảng hoặc kết quả truy vấn biểu diễn.

| Grain | Ví dụ khóa nhận diện một hàng |
| --- | --- |
| Một hàng cho mỗi khách hàng | customer_id |
| Một hàng cho mỗi đơn hàng | order_id |
| Một hàng cho mỗi dòng đơn hàng | order_id + line_id |
| Một hàng cho mỗi lần thanh toán | payment_id |
| Một hàng cho mỗi sản phẩm trong một đơn | order_id + product_id, nếu sản phẩm chỉ xuất hiện một lần |
| Một hàng cho mỗi khách hàng theo tháng | customer_id + month_start |

Nếu không xác định grain, bạn không thể biết một hàng trùng là lỗi hay hợp lệ. Hai dòng cùng customer_id có thể là sai trong báo cáo một hàng mỗi khách, nhưng đúng trong bảng lịch sử giao dịch.

### 2.1. Grain nguồn và grain kết quả có thể khác

~~~text
order_items
  mot hang / dong san pham
          |
          | GROUP BY order_id
          v
order_totals
  mot hang / don hang
~~~

GROUP BY chuyển dữ liệu từ mức dòng hàng sang mức đơn hàng. Đó là một phép biến đổi có chủ đích; cần ghi rõ và kiểm tra sau khi biến đổi.

### 2.2. Kiểm tra tính duy nhất theo grain

Nếu grain là một hàng cho mỗi đơn hàng:

~~~sql
SELECT
    order_id,
    COUNT(*) AS row_count
FROM lab_r414_order_report
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Expected là **không có hàng nào**. Nếu grain là một hàng cho mỗi dòng đơn, kiểm tra cặp khóa order_id và line_id. Không kiểm tra uniqueness bằng một cột nếu yêu cầu thực tế dùng khóa ghép.

## 3. Bộ dữ liệu thực hành có quan hệ một-nhiều

Ta tạo ba bảng để quan sát sự khác biệt giữa đơn hàng, dòng hàng và thanh toán.

### 3.1. Tạo schema và bảng

~~~sql
CREATE TABLE lab_r414_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL
);

CREATE TABLE lab_r414_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_r414_customers(customer_id),
    order_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE lab_r414_order_items (
    line_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lab_r414_orders(order_id),
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE lab_r414_payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lab_r414_orders(order_id),
    paid_amount NUMERIC(12, 2) NOT NULL CHECK (paid_amount >= 0),
    paid_at TIMESTAMPTZ NOT NULL
);
~~~

### 3.2. Nạp dữ liệu khách hàng và đơn hàng

~~~sql
INSERT INTO lab_r414_customers (
    customer_id, customer_code, customer_name
)
VALUES
    (1, 'C001', 'An Nguyen'),
    (2, 'C002', 'Binh Tran'),
    (3, 'C003', 'Chi Le');

INSERT INTO lab_r414_orders (
    order_id, customer_id, order_status, created_at
)
VALUES
    (101, 1, 'PAID',      TIMESTAMPTZ '2026-01-10 09:00:00+07'),
    (102, 1, 'NEW',       TIMESTAMPTZ '2026-01-11 10:00:00+07'),
    (103, 2, 'PAID',      TIMESTAMPTZ '2026-01-12 11:00:00+07'),
    (104, 3, 'CANCELLED', TIMESTAMPTZ '2026-01-13 12:00:00+07');
~~~

### 3.3. Nạp dòng hàng

~~~sql
INSERT INTO lab_r414_order_items (
    line_id, order_id, product_code, quantity, unit_price
)
VALUES
    (1, 101, 'PEN',   2, 100.00),
    (2, 101, 'BOOK',  1,  50.00),
    (3, 102, 'PEN',   1, 100.00),
    (4, 103, 'MOUSE', 3,  40.00),
    (5, 104, 'PAD',   2,  30.00);
~~~

| line_id | order_id | product_code | quantity | unit_price | line_total |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 101 | PEN | 2 | 100.00 | 200.00 |
| 2 | 101 | BOOK | 1 | 50.00 | 50.00 |
| 3 | 102 | PEN | 1 | 100.00 | 100.00 |
| 4 | 103 | MOUSE | 3 | 40.00 | 120.00 |
| 5 | 104 | PAD | 2 | 30.00 | 60.00 |

### 3.4. Nạp thanh toán

~~~sql
INSERT INTO lab_r414_payments (
    payment_id, order_id, paid_amount, paid_at
)
VALUES
    (1, 101, 100.00, TIMESTAMPTZ '2026-01-10 09:10:00+07'),
    (2, 101, 150.00, TIMESTAMPTZ '2026-01-10 09:20:00+07'),
    (3, 103, 120.00, TIMESTAMPTZ '2026-01-12 11:10:00+07');
~~~

Đơn 101 có **hai dòng hàng và hai lần thanh toán**. Đơn 102 và 104 chưa có thanh toán. Đây là dữ liệu có chủ đích để làm lộ lỗi nhân bản khi JOIN.

### 3.5. Bản đồ cardinality

~~~text
customers (1) ----< orders (N)
                       |
                       +----< order_items (N)
                       |
                       +----< payments (N)
~~~

Một khách có nhiều đơn. Một đơn có nhiều dòng hàng và có thể có nhiều lần thanh toán. Hai quan hệ một-nhiều xuất phát từ cùng một đơn sẽ tạo tích các hàng khi JOIN trực tiếp.

## 4. Xác định expected result trước khi truy vấn

Ta muốn báo cáo **một hàng cho mỗi đơn hàng**, gồm order_id, customer_code, order_status, item_count và item_total.

Quy tắc:

- item_count là số dòng hàng, không phải tổng số sản phẩm.
- item_total là tổng quantity nhân unit_price.
- Đơn không có dòng hàng vẫn xuất hiện với số dòng và tổng bằng 0.
- Mỗi order_id chỉ xuất hiện một lần.

### 4.1. Tính expected result bằng tay

| order_id | customer_code | order_status | item_count | item_total |
| ---: | --- | --- | ---: | ---: |
| 101 | C001 | PAID | 2 | 250.00 |
| 102 | C001 | NEW | 1 | 100.00 |
| 103 | C002 | PAID | 1 | 120.00 |
| 104 | C003 | CANCELLED | 1 | 60.00 |

Tập mong đợi có **4 hàng**. Tổng tiền hàng của tất cả đơn là 530.00. Đây là kiểm tra chéo, nhưng không đủ chứng minh từng hàng đúng.

### 4.2. Viết truy vấn theo đúng grain

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS item_total
    FROM lab_r414_order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.customer_code,
    o.order_status,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.item_total, 0.00::NUMERIC) AS item_total
FROM lab_r414_orders AS o
JOIN lab_r414_customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id;
~~~

Ta tổng hợp order_items về **một hàng cho mỗi order_id trước khi JOIN** với orders. JOIN cuối cùng vì vậy không nhân đơn hàng theo số dòng hàng.

### 4.3. Vì sao cần LEFT JOIN?

Nếu có đơn chưa có dòng hàng, yêu cầu “mỗi đơn một hàng” nghĩa là đơn ấy vẫn phải xuất hiện. LEFT JOIN giữ hàng từ orders; các cột từ item_totals là NULL nếu không có dòng tổng hợp. COALESCE chuyển NULL thành 0 theo quy tắc nghiệp vụ.

## 5. JOIN có thể làm thay đổi số hàng như thế nào?

### 5.1. JOIN đơn với dòng hàng

~~~sql
SELECT
    o.order_id,
    i.line_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM lab_r414_orders AS o
JOIN lab_r414_order_items AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.line_id;
~~~

Kết quả có **5 hàng**, không phải 4. Đây là kết quả đúng nếu grain là **một hàng cho mỗi dòng hàng**.

### 5.2. JOIN đồng thời order_items và payments

~~~sql
SELECT
    o.order_id,
    i.line_id,
    p.payment_id,
    i.quantity * i.unit_price AS line_total,
    p.paid_amount
FROM lab_r414_orders AS o
LEFT JOIN lab_r414_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lab_r414_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101
ORDER BY i.line_id, p.payment_id;
~~~

Với đơn 101 có 2 dòng hàng và 2 lần thanh toán, JOIN tạo **2 × 2 = 4 hàng**:

| order_id | line_id | payment_id | line_total | paid_amount |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 1 | 200.00 | 100.00 |
| 101 | 1 | 2 | 200.00 | 150.00 |
| 101 | 2 | 1 | 50.00 | 100.00 |
| 101 | 2 | 2 | 50.00 | 150.00 |

Nếu cộng line_total sau JOIN, tổng thành 500.00 thay vì 250.00. Nếu cộng paid_amount, tổng cũng thành 500.00 thay vì 250.00.

### 5.3. Tổng hợp mỗi nhánh trước khi JOIN

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM lab_r414_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(paid_amount) AS paid_total
    FROM lab_r414_payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_total, 0.00::NUMERIC) AS item_total,
    COALESCE(p.paid_total, 0.00::NUMERIC) AS paid_total
FROM lab_r414_orders AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Expected:

| order_id | item_total | paid_total |
| ---: | ---: | ---: |
| 101 | 250.00 | 250.00 |
| 102 | 100.00 | 0.00 |
| 103 | 120.00 | 120.00 |
| 104 | 60.00 | 0.00 |

Mỗi CTE tạo tối đa một hàng cho mỗi order_id. Sau đó mỗi LEFT JOIN giữ grain của orders.

### 5.4. Đừng dùng DISTINCT để che lỗi JOIN

DISTINCT chỉ loại các hàng trùng trên **các cột đang chọn**. Nó không sửa phép nhân bản ở những phép tổng hợp, cũng không khôi phục đơn không có dòng hàng. Nếu đã JOIN sai grain rồi SUM trước DISTINCT, số tiền vẫn sai.

Hãy sửa cardinality của truy vấn, không dùng DISTINCT như miếng vá cho mọi lỗi trùng.

## 6. INNER JOIN, LEFT JOIN và vị trí điều kiện lọc

Một lỗi phổ biến là viết LEFT JOIN nhưng đặt điều kiện của bảng phải trong WHERE, khiến kết quả có hành vi như INNER JOIN.

### 6.1. Điều kiện trong WHERE

~~~sql
SELECT
    o.order_id,
    p.payment_id
FROM lab_r414_orders AS o
LEFT JOIN lab_r414_payments AS p
    ON p.order_id = o.order_id
WHERE p.paid_amount > 0
ORDER BY o.order_id;
~~~

Hàng không có payment có p.paid_amount = NULL. Điều kiện WHERE không nhận TRUE cho hàng đó, nên đơn không thanh toán bị loại.

### 6.2. Điều kiện trong ON

~~~sql
SELECT
    o.order_id,
    p.payment_id
FROM lab_r414_orders AS o
LEFT JOIN lab_r414_payments AS p
    ON p.order_id = o.order_id
   AND p.paid_amount > 0
ORDER BY o.order_id, p.payment_id;
~~~

Ở đây đơn vẫn được giữ, chỉ những payment thỏa điều kiện mới được nối. Nếu không có payment phù hợp, cột payment là NULL.

### 6.3. Chọn phép nối theo yêu cầu

| Yêu cầu | Kiểu JOIN/điều kiện thường phù hợp |
| --- | --- |
| Chỉ đơn có ít nhất một thanh toán | INNER JOIN hoặc EXISTS |
| Tất cả đơn, có thể chưa thanh toán | LEFT JOIN |
| Tất cả đơn và chỉ nối payment hợp lệ | LEFT JOIN với điều kiện ở ON |
| Đơn chưa có payment | LEFT JOIN rồi kiểm tra khóa payment IS NULL, hoặc NOT EXISTS |

Nếu chỉ muốn kiểm tra sự tồn tại, EXISTS thường tránh nhân bản hàng:

~~~sql
SELECT
    o.order_id,
    o.order_status
FROM lab_r414_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM lab_r414_payments AS p
    WHERE p.order_id = o.order_id
);
~~~

Một đơn có 2 hay 20 payment vẫn xuất hiện đúng một lần vì EXISTS chỉ kiểm tra có ít nhất một hàng phù hợp.

## 7. NULL và các quy tắc đếm

NULL không đồng nghĩa với 0, chuỗi rỗng hoặc false. Nó biểu thị giá trị chưa biết/không có theo ngữ nghĩa SQL.

### 7.1. COUNT(*) và COUNT(column)

~~~sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(p.payment_id) AS payment_rows,
    SUM(p.paid_amount) AS payment_sum
FROM lab_r414_orders AS o
LEFT JOIN lab_r414_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 102;
~~~

Đơn 102 chưa có payment:

| joined_rows | payment_rows | payment_sum |
| ---: | ---: | --- |
| 1 | 0 | NULL |

LEFT JOIN tạo một hàng với cột phía payment là NULL. Vì vậy COUNT(*) là 1, nhưng COUNT(payment_id) là 0. SUM trên tập không có giá trị khác NULL trả NULL.

### 7.2. COALESCE phải theo ý nghĩa nghiệp vụ

~~~sql
SELECT
    o.order_id,
    COALESCE(SUM(p.paid_amount), 0.00::NUMERIC) AS paid_total
FROM lab_r414_orders AS o
LEFT JOIN lab_r414_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Ở đây chuyển NULL thành 0 là hợp lý nếu báo cáo định nghĩa “chưa có thanh toán” có tổng thanh toán bằng 0. Nhưng không phải cột NULL nào cũng nên chuyển thành 0. Chưa biết số lượng tồn kho khác với tồn kho bằng 0.

### 7.3. So sánh NULL an toàn

Trong SQL, biểu thức NULL = NULL không trả TRUE mà trả UNKNOWN. PostgreSQL hỗ trợ:

~~~sql
actual_value IS DISTINCT FROM expected_value
~~~

Biểu thức này coi hai NULL là bằng nhau, NULL và non-NULL là khác nhau. Nó rất hữu ích khi kiểm thử actual result với expected result.

## 8. GROUP BY và mức chi tiết sau tổng hợp

GROUP BY xác định grain mới bằng các cột nhóm.

### 8.1. Một hàng cho mỗi trạng thái

~~~sql
SELECT
    order_status,
    COUNT(*) AS order_count
FROM lab_r414_orders
GROUP BY order_status
ORDER BY order_status;
~~~

Expected:

| order_status | order_count |
| --- | ---: |
| CANCELLED | 1 |
| NEW | 1 |
| PAID | 2 |

Grain kết quả là **một hàng cho mỗi order_status**, không còn một hàng cho mỗi đơn.

### 8.2. Một hàng cho mỗi khách hàng và trạng thái

~~~sql
SELECT
    customer_id,
    order_status,
    COUNT(*) AS order_count
FROM lab_r414_orders
GROUP BY customer_id, order_status
ORDER BY customer_id, order_status;
~~~

Grain là **customer_id + order_status**. Khách C001 có hai hàng kết quả vì có đơn PAID và NEW. Không được gọi đây là duplicate chỉ vì customer_id xuất hiện hai lần.

### 8.3. COUNT(*) sau LEFT JOIN có thể đếm sai

~~~sql
SELECT
    o.order_id,
    COUNT(*) AS count_rows,
    COUNT(i.line_id) AS line_count
FROM lab_r414_orders AS o
LEFT JOIN lab_r414_order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Với đơn không có dòng hàng, COUNT(*) có thể là 1 vì hàng NULL-extended của LEFT JOIN vẫn tồn tại, còn COUNT(line_id) là 0. Khi cần đếm thực thể ở bảng phải, hãy đếm cột khóa không NULL của bảng đó.

### 8.4. HAVING lọc nhóm, WHERE lọc hàng trước nhóm

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM lab_r414_orders
WHERE order_status <> 'CANCELLED'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

WHERE loại đơn CANCELLED trước khi nhóm. HAVING chỉ giữ nhóm có ít nhất hai đơn sau lọc. Đổi vị trí hai điều kiện sẽ đổi tập kết quả hoặc làm câu SQL không hợp lệ.

## 9. Window functions không làm mất grain nguồn

Window function tính toán trên cửa sổ hàng nhưng thường **giữ số hàng đầu vào**. Đây là điểm khác GROUP BY.

### 9.1. Xếp hạng đơn theo khách hàng

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS order_number_for_customer
FROM lab_r414_orders
ORDER BY customer_id, created_at, order_id;
~~~

Kết quả vẫn có 4 hàng, một hàng mỗi đơn. order_id là tiêu chí phụ giúp thứ tự xác định khi created_at trùng nhau.

### 9.2. Lấy đơn mới nhất mỗi khách

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM lab_r414_orders AS o
)
SELECT
    order_id,
    customer_id,
    order_status,
    created_at
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

Grain chuyển thành **một hàng cho mỗi khách có ít nhất một đơn**. Khách không có đơn sẽ không xuất hiện; nếu yêu cầu tất cả khách kể cả khách chưa có đơn, phải bắt đầu từ customers và LEFT JOIN kết quả ranked.

### 9.3. Tie cần được xử lý theo yêu cầu

Nếu hai đơn có cùng created_at, ROW_NUMBER vẫn cần một quy tắc phá hòa. Nếu nghiệp vụ muốn giữ **tất cả đơn đồng hạng mới nhất**, dùng RANK hoặc DENSE_RANK và lọc hạng 1. Không dùng ROW_NUMBER khi yêu cầu phải giữ mọi trường hợp đồng hạng.

## 10. Thứ tự hàng: không có ORDER BY thì không có cam kết

SQL trả về một tập hàng. Nếu không có ORDER BY ở câu SELECT ngoài cùng, ứng dụng không được dựa vào thứ tự tình cờ nhìn thấy.

~~~sql
SELECT order_id, order_status
FROM lab_r414_orders;
~~~

Database có thể trả các hàng theo thứ tự khác sau khi đổi index, kế hoạch thực thi, phiên bản hoặc dữ liệu.

### 10.1. ORDER BY cần đủ tiêu chí

~~~sql
SELECT order_id, order_status, created_at
FROM lab_r414_orders
ORDER BY created_at, order_id;
~~~

Nếu chỉ ORDER BY created_at và có hai hàng cùng timestamp, thứ tự giữa chúng vẫn chưa xác định. Thêm khóa duy nhất làm tie-breaker.

### 10.2. ORDER BY trong CTE/subquery không đảm bảo thứ tự đầu ra ngoài

ORDER BY bên trong subquery có thể phục vụ LIMIT, window hoặc xử lý cụ thể, nhưng câu SELECT ngoài cùng vẫn cần ORDER BY nếu caller yêu cầu thứ tự. Đừng xem thứ tự nội bộ của một bước trung gian là hợp đồng hiển thị.

### 10.3. NULLS FIRST và NULLS LAST

PostgreSQL hỗ trợ chỉ rõ vị trí NULL:

~~~sql
ORDER BY created_at DESC NULLS LAST, order_id DESC;
~~~

Thứ tự NULL mặc định có thể khác giữa hệ quản trị hoặc hướng sort. Nếu cột có thể NULL, ghi rõ mong muốn để kết quả ổn định khi chuyển dialect.

## 11. LIMIT, OFFSET và phân trang ổn định

### 11.1. LIMIT không có ORDER BY

~~~sql
SELECT order_id, order_status
FROM lab_r414_orders
LIMIT 2;
~~~

Câu lệnh trả hai hàng nào không được đảm bảo. Nó không thích hợp làm expected result cố định.

### 11.2. OFFSET có thể bỏ sót hoặc lặp hàng khi dữ liệu thay đổi

~~~sql
SELECT order_id, created_at
FROM lab_r414_orders
ORDER BY created_at, order_id
LIMIT 2 OFFSET 2;
~~~

Nếu một đơn mới được chèn trước vị trí offset giữa hai lần lấy trang, trang sau có thể lặp hoặc bỏ qua một hàng so với tập người dùng mong đợi.

### 11.3. Keyset pagination

~~~sql
SELECT order_id, created_at, order_status
FROM lab_r414_orders
WHERE (created_at, order_id) >
      (TIMESTAMPTZ '2026-01-11 10:00:00+07', 102)
ORDER BY created_at, order_id
LIMIT 2;
~~~

Đây là trang tiếp theo sau cặp khóa đã đọc. Cách so sánh tuple phù hợp khi các cột sắp xếp có quy tắc so sánh nhất quán và không NULL theo thiết kế. Với thứ tự DESC hoặc cột NULL, cần điều chỉnh predicate tương ứng.

### 11.4. Expected result cho phân trang

Hãy ghi rõ thứ tự sắp xếp đầy đủ, khóa cursor, biên cursor là > hay >=, cách xử lý hàng mới/chỉnh sửa trong lúc phân trang và có yêu cầu snapshot nhất quán giữa các trang không. Nếu kiểm thử nhiều trang, xác nhận hợp các trang không trùng khóa và không thiếu hàng trong cùng snapshot.

## 12. Kiểu dữ liệu và độ chính xác

Một giá trị có thể nhìn giống nhau trong SQL client nhưng khác kiểu hoặc độ chính xác.

### 12.1. NUMERIC và FLOAT

Với tiền tệ, ưu tiên kiểu số thập phân có độ chính xác được định nghĩa, ví dụ NUMERIC(12,2), thay vì dựa vào số dấu phẩy động nhị phân.

~~~sql
SELECT
    SUM(quantity * unit_price) AS item_total
FROM lab_r414_order_items
WHERE order_id = 101;
~~~

Kết quả là NUMERIC 250.00 theo dữ liệu mẫu. Nếu client hiển thị 250, điều đó không nhất thiết là sai về giá trị; cần xác định hợp đồng có yêu cầu scale 2 hay chỉ yêu cầu số tiền tương đương.

### 12.2. Làm tròn ở cấp dòng hay sau khi tổng?

~~~sql
SELECT SUM(ROUND(quantity * unit_price, 2))
FROM some_order_items;
~~~

và:

~~~sql
SELECT ROUND(SUM(quantity * unit_price), 2)
FROM some_order_items;
~~~

có thể khác nhau nếu biểu thức đầu vào có phần thập phân dài. Hợp đồng phải nói rõ quy tắc làm tròn theo dòng, theo tổng, theo tiền tệ hoặc theo nghiệp vụ.

### 12.3. Kiểu trả về của aggregate

Kiểu dữ liệu của COUNT, SUM, AVG và biểu thức có thể khác kiểu cột đầu vào. Ví dụ PostgreSQL trả COUNT dưới dạng BIGINT. Khi so expected fixture, hãy xác định kiểu/scale và không ép kiểu mất thông tin chỉ để làm test dễ qua.

## 13. Ngày giờ và biên khoảng thời gian

Một báo cáo theo ngày thường sai vì không xác định rõ múi giờ và cách xử lý biên.

### 13.1. Dùng khoảng nửa mở

Với TIMESTAMPTZ, truy vấn các đơn trong ngày 10/01/2026 theo giờ Việt Nam:

~~~sql
SELECT order_id, created_at
FROM lab_r414_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-10 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-01-11 00:00:00+07'
ORDER BY created_at, order_id;
~~~

Khoảng **[đầu ngày, đầu ngày kế tiếp)** tránh phải đoán thời điểm cuối ngày như 23:59:59.999999. Cách này thuận tiện khi timestamp có độ chính xác khác nhau.

### 13.2. Không dùng BETWEEN nếu biên cuối cần loại trừ

BETWEEN thường bao gồm cả hai biên. Nếu hai khoảng ngày liền nhau dùng BETWEEN với mốc cuối và mốc đầu chung, bản ghi tại ranh giới có thể bị tính hai lần. Khoảng nửa mở giúp phân vùng không chồng lấn.

### 13.3. TIMESTAMP và TIMESTAMPTZ khác nhau

PostgreSQL:

- TIMESTAMP WITHOUT TIME ZONE lưu ngày giờ không gắn múi giờ.
- TIMESTAMPTZ biểu diễn thời điểm tuyệt đối và hiển thị theo timezone của session.

Nếu test so chuỗi hiển thị, hai session timezone khác nhau có thể nhìn khác nhau dù cùng thời điểm. Nên so giá trị thời điểm theo quy tắc rõ ràng hoặc chuẩn hóa session timezone khi tạo output.

### 13.4. Thời gian hiện tại làm test khó tái lập

Truy vấn dùng CURRENT_TIMESTAMP hoặc NOW() có thể trả kết quả khác nhau mỗi lần. Để kiểm thử ranh giới thời gian, truyền mốc thời gian làm tham số, dùng fixture timestamp cố định, xác định timezone và kiểm tra thời điểm trước, tại và sau biên.

## 14. NULL, duplicate và tập rỗng

Một bộ fixture tốt không chỉ có các hàng “đẹp”. Cần tạo những tình huống có khả năng làm lộ lỗi logic.

### 14.1. Hàng không có quan hệ

Thêm đơn không có dòng hàng:

~~~sql
INSERT INTO lab_r414_orders (
    order_id, customer_id, order_status, created_at
)
VALUES (
    105, 3, 'NEW',
    TIMESTAMPTZ '2026-01-14 09:00:00+07'
);
~~~

Expected report một hàng mỗi đơn phải có:

| order_id | customer_code | order_status | item_count | item_total |
| ---: | --- | --- | ---: | ---: |
| 105 | C003 | NEW | 0 | 0.00 |

Nếu hàng 105 biến mất, hãy xem lại INNER JOIN. Nếu item_count thành 1, kiểm tra COUNT(*) trên LEFT JOIN thay vì COUNT(line_id).

### 14.2. Một tập kết quả rỗng vẫn có thể đúng

~~~sql
SELECT order_id
FROM lab_r414_orders
WHERE order_status = 'UNKNOWN';
~~~

Kết quả rỗng có thể là expected result. Không coi truy vấn trả 0 hàng là lỗi nếu yêu cầu cho phép không có bản ghi phù hợp.

### 14.3. NULL và chuỗi rỗng

NULL và chuỗi rỗng có thể mang ý nghĩa khác nhau. Nếu nghiệp vụ xem cả hai là “chưa nhập”:

~~~sql
WHERE phone IS NULL OR BTRIM(phone) = ''
~~~

Nếu chỉ dùng IS NULL, chuỗi rỗng vẫn được xem là một giá trị đã nhập.

### 14.4. Duplicate hợp lệ và duplicate lỗi

Hai hàng có cùng customer_id trong order report có thể hợp lệ nếu grain là mỗi đơn; chúng là lỗi nếu grain là mỗi khách. Hãy luôn xác định **khóa của grain**, không chỉ tìm các cột trông giống nhau.

### 14.5. Dữ liệu biên nên có trong fixture

| Trường hợp | Lý do cần kiểm thử |
| --- | --- |
| Không có hàng | Xác nhận kết quả rỗng đúng |
| Một hàng | Bắt lỗi giả định phải có nhiều hàng |
| Nhiều hàng cùng khóa cha | Bắt lỗi fan-out |
| Không có hàng con | Bắt lỗi INNER JOIN/COUNT |
| NULL | Kiểm tra ba giá trị logic và aggregate |
| Giá trị bằng 0 | Phân biệt 0 với NULL |
| Giá trị âm nếu được phép | Kiểm tra dấu và điều kiện |
| Hai timestamp trùng nhau | Kiểm tra tie-breaker |
| Ngay tại biên thời gian | Kiểm tra inclusive/exclusive |
| Số tiền có phần lẻ | Kiểm tra scale và rounding |
| Giá trị lớn gần giới hạn | Kiểm tra overflow/precision |

## 15. So sánh actual result và expected result

Đừng chỉ nhìn bằng mắt. Có thể biểu diễn expected result thành CTE hoặc bảng fixture rồi so sánh hai chiều.

### 15.1. Expected result bằng VALUES

~~~sql
WITH expected (
    order_id,
    customer_code,
    order_status,
    item_count,
    item_total
) AS (
    VALUES
        (101, 'C001'::TEXT, 'PAID'::TEXT, 2, 250.00::NUMERIC),
        (102, 'C001'::TEXT, 'NEW'::TEXT, 1, 100.00::NUMERIC),
        (103, 'C002'::TEXT, 'PAID'::TEXT, 1, 120.00::NUMERIC),
        (104, 'C003'::TEXT, 'CANCELLED'::TEXT, 1, 60.00::NUMERIC),
        (105, 'C003'::TEXT, 'NEW'::TEXT, 0, 0.00::NUMERIC)
)
SELECT *
FROM expected
ORDER BY order_id;
~~~

CTE expected là một fixture nhỏ, dễ đọc và không phụ thuộc vào cách truy vấn thực tế được viết.

### 15.2. So sánh hai chiều bằng EXCEPT

Đặt expected và truy vấn cần kiểm thử vào hai CTE:

~~~sql
WITH expected AS (
    SELECT *
    FROM (
        VALUES
            (101, 'C001'::TEXT, 'PAID'::TEXT, 2, 250.00::NUMERIC),
            (102, 'C001'::TEXT, 'NEW'::TEXT, 1, 100.00::NUMERIC),
            (103, 'C002'::TEXT, 'PAID'::TEXT, 1, 120.00::NUMERIC),
            (104, 'C003'::TEXT, 'CANCELLED'::TEXT, 1, 60.00::NUMERIC),
            (105, 'C003'::TEXT, 'NEW'::TEXT, 0, 0.00::NUMERIC)
    ) AS e(order_id, customer_code, order_status, item_count, item_total)
),
actual AS (
    WITH item_totals AS (
        SELECT
            order_id,
            COUNT(*) AS item_count,
            SUM(quantity * unit_price) AS item_total
        FROM lab_r414_order_items
        GROUP BY order_id
    )
    SELECT
        o.order_id,
        c.customer_code,
        o.order_status,
        COALESCE(i.item_count, 0)::BIGINT AS item_count,
        COALESCE(i.item_total, 0.00::NUMERIC) AS item_total
    FROM lab_r414_orders AS o
    JOIN lab_r414_customers AS c
        ON c.customer_id = o.customer_id
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
)
SELECT 'missing_from_actual' AS difference, d.*
FROM (
    SELECT * FROM expected
    EXCEPT
    SELECT * FROM actual
) AS d
UNION ALL
SELECT 'unexpected_in_actual' AS difference, d.*
FROM (
    SELECT * FROM actual
    EXCEPT
    SELECT * FROM expected
) AS d
ORDER BY difference, order_id;
~~~

Nếu không có khác biệt, truy vấn trả **0 hàng**. missing_from_actual là expected có nhưng actual thiếu; unexpected_in_actual là actual có nhưng expected không có.

### 15.3. EXCEPT và EXCEPT ALL

EXCEPT loại trùng theo ngữ nghĩa tập hợp. Nếu actual có cùng một hàng hai lần còn expected có một lần, phép EXCEPT thông thường có thể không cho thấy khác biệt multiplicity.

PostgreSQL hỗ trợ EXCEPT ALL, giữ số lần xuất hiện của hàng khi so sánh:

~~~sql
SELECT * FROM expected
EXCEPT ALL
SELECT * FROM actual;
~~~

Và chiều ngược lại:

~~~sql
SELECT * FROM actual
EXCEPT ALL
SELECT * FROM expected;
~~~

Kết hợp hai chiều EXCEPT ALL giúp phát hiện hàng thiếu, hàng thừa và số lần xuất hiện sai.

### 15.4. Cột kiểu khác nhau cần chuẩn hóa có chủ đích

Hai phía của UNION/EXCEPT phải có số cột và kiểu dữ liệu tương thích. Nếu expected dùng INTEGER còn actual dùng BIGINT, database có thể tìm kiểu chung. Đừng ép về kiểu nhỏ hơn chỉ để test chạy; xác định hợp đồng kiểu dữ liệu và ép kiểu an toàn nếu cần.

## 16. So sánh NULL an toàn bằng FULL OUTER JOIN

Một cách khác là nối expected và actual theo khóa grain, rồi so từng cột.

~~~sql
WITH expected AS (
    SELECT *
    FROM (
        VALUES
            (101, 'C001'::TEXT, 'PAID'::TEXT, 250.00::NUMERIC),
            (102, 'C001'::TEXT, 'NEW'::TEXT, 100.00::NUMERIC)
    ) AS e(order_id, customer_code, order_status, item_total)
),
actual AS (
    SELECT
        o.order_id,
        c.customer_code,
        o.order_status,
        COALESCE(SUM(i.quantity * i.unit_price), 0.00::NUMERIC)
            AS item_total
    FROM lab_r414_orders AS o
    JOIN lab_r414_customers AS c
        ON c.customer_id = o.customer_id
    LEFT JOIN lab_r414_order_items AS i
        ON i.order_id = o.order_id
    GROUP BY o.order_id, c.customer_code, o.order_status
)
SELECT
    COALESCE(e.order_id, a.order_id) AS order_id,
    e.customer_code AS expected_customer,
    a.customer_code AS actual_customer,
    e.order_status AS expected_status,
    a.order_status AS actual_status,
    e.item_total AS expected_total,
    a.item_total AS actual_total
FROM expected AS e
FULL OUTER JOIN actual AS a
    ON a.order_id = e.order_id
WHERE
       e.order_id IS NULL
    OR a.order_id IS NULL
    OR e.customer_code IS DISTINCT FROM a.customer_code
    OR e.order_status IS DISTINCT FROM a.order_status
    OR e.item_total IS DISTINCT FROM a.item_total
ORDER BY order_id;
~~~

Truy vấn trả những khóa thiếu/thừa hoặc cột khác. Ví dụ dùng expected subset để minh họa; khi kiểm thử toàn bộ kết quả, expected phải chứa đầy đủ các hàng theo hợp đồng.

**IS DISTINCT FROM** giúp so sánh NULL có ý nghĩa xác định. Với dialect không hỗ trợ cú pháp này, cần viết điều kiện NULL-aware tương ứng.

## 17. Kiểm tra từng bất biến thay vì chỉ so toàn bộ bảng

Một bài kiểm thử dễ gỡ lỗi khi kiểm tra từng thuộc tính riêng.

### 17.1. Số hàng

~~~sql
SELECT COUNT(*) AS actual_rows
FROM (
    SELECT
        o.order_id,
        COALESCE(SUM(i.quantity * i.unit_price), 0.00::NUMERIC)
            AS item_total
    FROM lab_r414_orders AS o
    LEFT JOIN lab_r414_order_items AS i
        ON i.order_id = o.order_id
    GROUP BY o.order_id
) AS result;
~~~

Sau khi thêm đơn 105, expected là 5 hàng.

### 17.2. Tính duy nhất theo grain

~~~sql
WITH result AS (
    SELECT
        o.order_id,
        COALESCE(SUM(i.quantity * i.unit_price), 0.00::NUMERIC)
            AS item_total
    FROM lab_r414_orders AS o
    LEFT JOIN lab_r414_order_items AS i
        ON i.order_id = o.order_id
    GROUP BY o.order_id
)
SELECT order_id, COUNT(*)
FROM result
GROUP BY order_id
HAVING COUNT(*) <> 1;
~~~

Expected là 0 hàng. Đây là kiểm tra grain một hàng mỗi đơn.

### 17.3. Tổng toàn cục như kiểm tra chéo

~~~sql
SELECT SUM(quantity * unit_price) AS all_item_total
FROM lab_r414_order_items;
~~~

Expected là 530.00 cho các đơn 101–104; đơn 105 chưa có dòng nên không đổi tổng. Tổng này giúp phát hiện một số lỗi, nhưng không thay thế so sánh từng đơn.

### 17.4. Kiểm tra quan hệ tham chiếu

~~~sql
SELECT
    i.order_id,
    COUNT(*) AS line_count
FROM lab_r414_order_items AS i
LEFT JOIN lab_r414_orders AS o
    ON o.order_id = i.order_id
WHERE o.order_id IS NULL
GROUP BY i.order_id;
~~~

Với FK đang hoạt động, expected là 0 hàng. Kiểm tra này hữu ích khi dữ liệu import hoặc constraint bị tắt trong quy trình đặc biệt.

### 17.5. Kiểm tra trạng thái cho phép

~~~sql
SELECT order_id, order_status
FROM lab_r414_orders
WHERE order_status NOT IN ('PAID', 'NEW', 'CANCELLED');
~~~

Expected là 0 hàng nếu miền trạng thái chỉ gồm ba giá trị đó. Nếu cột nullable, cần xét NULL riêng vì NOT IN với NULL trả UNKNOWN.

## 18. Đối chiếu nhiều mức

Không nên chỉ có một test lớn. Hãy kiểm tra từ tổng quan tới từng thực thể:

1. **Cardinality tổng:** số hàng kết quả.
2. **Uniqueness:** số hàng trên mỗi khóa grain.
3. **Coverage:** tập khóa phải xuất hiện có đủ không.
4. **No extras:** có khóa ngoài phạm vi không?
5. **Column values:** từng thuộc tính có đúng không?
6. **Aggregate reconciliation:** tổng chi tiết có khớp tổng báo cáo không?
7. **Nullability:** NULL có xuất hiện đúng chỗ không?
8. **Ordering:** thứ tự có ổn định khi được yêu cầu không?
9. **Type/precision:** kiểu, scale và định dạng có phù hợp không?

### 18.1. Tránh test tautology

Nếu expected được tạo bằng cách gọi lại chính hàm hoặc cùng biểu thức logic với actual, cả hai có thể cùng sai và test vẫn qua. Expected result nên được xây dựng độc lập bằng fixture nhỏ, tính tay hoặc cách diễn đạt khác.

## 19. Kiểm thử thay đổi dữ liệu và transaction snapshot

Một truy vấn chạy hai lần có thể trả kết quả khác nhau vì dữ liệu thay đổi giữa hai lần.

### 19.1. Kiểm thử trong transaction

~~~sql
BEGIN;

INSERT INTO lab_r414_orders (
    order_id, customer_id, order_status, created_at
)
VALUES (
    106, 1, 'NEW',
    TIMESTAMPTZ '2026-01-15 09:00:00+07'
);

SELECT COUNT(*)
FROM lab_r414_orders;

ROLLBACK;
~~~

Transaction giúp fixture tạm không còn sau rollback. Nhưng sequence/identity trong PostgreSQL có thể không trả lại số đã cấp; ở đây dùng ID tường minh để kết quả dễ tái tạo.

### 19.2. Snapshot và isolation

Trong PostgreSQL READ COMMITTED, mỗi statement thường nhìn một snapshot mới. Hai SELECT trong cùng transaction có thể thấy dữ liệu mới được commit giữa hai statement. Với REPEATABLE READ, transaction giữ snapshot nhất quán theo quy tắc isolation.

Nếu test đếm hàng rồi truy vấn chi tiết, một transaction khác có thể chèn/xóa hàng giữa hai bước, làm số đếm và chi tiết không khớp dù từng truy vấn đều đúng tại snapshot riêng.

Khi cần so sánh nhất quán, chọn transaction isolation phù hợp hoặc chạy một truy vấn tạo kết quả ở một snapshot. Đừng giả định mọi DBMS có cùng mặc định isolation.

### 19.3. Test song song

Test chạy đồng thời có thể đụng dữ liệu dùng chung: hai test cùng chèn ID cố định, một test xóa fixture khi test khác đang đọc, hoặc một test thay đổi trạng thái trước khi test khác kiểm tra.

Giải pháp: fixture cô lập theo test, transaction rollback, schema/database riêng, khóa hoặc dữ liệu định danh duy nhất theo lượt chạy. Đừng dựa vào thứ tự thực thi của test runner nếu không có ràng buộc rõ.

## 20. Debugging khi actual khác expected

Khi phát hiện khác biệt, hãy khoanh vùng theo thứ tự:

### Bước 1 — Xác nhận fixture

~~~sql
SELECT * FROM lab_r414_orders ORDER BY order_id;
SELECT * FROM lab_r414_order_items ORDER BY line_id;
SELECT * FROM lab_r414_payments ORDER BY payment_id;
~~~

Xác nhận đúng database, schema, dữ liệu test và transaction. Một sai khác có thể đến từ fixture chưa được nạp hoặc dữ liệu cũ còn sót.

### Bước 2 — Kiểm tra grain trước JOIN

~~~sql
SELECT order_id, COUNT(*) AS lines
FROM lab_r414_order_items
GROUP BY order_id
ORDER BY order_id;

SELECT order_id, COUNT(*) AS payments
FROM lab_r414_payments
GROUP BY order_id
ORDER BY order_id;
~~~

Nhìn ra quan hệ một-nhiều trước khi JOIN sẽ giúp dự đoán số hàng.

### Bước 3 — Thêm JOIN từng bước

Bắt đầu từ orders, thêm customers, rồi mới thêm một nhánh con. Sau mỗi JOIN, kiểm tra tổng số hàng, số khóa order_id duy nhất, những khóa bị mất và những khóa bị nhân bản.

### Bước 4 — Kiểm tra WHERE và ON

Xem điều kiện ở WHERE có loại hàng NULL-extended của LEFT JOIN không. Kiểm tra điều kiện có lọc nhầm trạng thái hoặc khoảng thời gian không.

### Bước 5 — Kiểm tra aggregate

Đảm bảo aggregate được tính trên grain đúng. Đếm khóa con thay vì COUNT(*) khi cần. Tổng hợp từng nhánh một-nhiều trước khi nối nhiều nhánh.

### Bước 6 — So sánh khóa trước, giá trị sau

Trước tiên tìm khóa thiếu/thừa. Sau đó mới so cột thuộc tính trên những khóa ghép được. Cách này phân biệt lỗi coverage với lỗi tính giá trị.

### Bước 7 — Kiểm tra kiểu và thời gian

Xác nhận NUMERIC/FLOAT, rounding, timezone, inclusive/exclusive boundary, NULL và cách client format.

### Bước 8 — Xem execution plan khi logic đã đúng

EXPLAIN có thể giúp hiểu kế hoạch và chi phí. EXPLAIN ANALYZE thực thi câu lệnh; dùng cẩn trọng trong sandbox và transaction rollback khi phù hợp. Execution plan giúp điều tra hiệu năng, nhưng không thay thế việc xác định expected result.

## 21. Một bộ kiểm thử SQL có cấu trúc

~~~text
Arrange
  Tao fixture va expected result
       |
       v
Act
  Chay query can kiem thu
       |
       v
Assert
  So schema / grain / keys / values / count / order
       |
       v
Cleanup
  Rollback hoac xoa fixture test
~~~

### 21.1. Arrange

Fixture nên có ít nhất một đơn nhiều dòng hàng, một đơn nhiều lần thanh toán, một đơn không có thanh toán, một đơn không có dòng hàng, hai đơn cùng khách hàng và trạng thái cần/không cần lọc.

Fixture nhỏ giúp tính expected bằng tay và quan sát fan-out.

### 21.2. Act

Đặt truy vấn trong CTE actual hoặc view test để có thể tái sử dụng trong các assertion.

### 21.3. Assert

~~~sql
SELECT NOT EXISTS (
    SELECT order_id
    FROM lab_r414_order_report
    GROUP BY order_id
    HAVING COUNT(*) > 1
) AS grain_ok;
~~~

Expected là TRUE nếu report có một hàng mỗi đơn. Các CTE expected/actual phải được định nghĩa trong cùng statement nếu cần tham chiếu trực tiếp.

### 21.4. Cleanup

Nếu fixture được tạo trong transaction, dùng ROLLBACK. Nếu test framework quản lý fixture theo schema riêng, xóa fixture theo phạm vi test. Không chạy DELETE/TRUNCATE trên dữ liệu dùng chung chỉ để dọn bài thực hành.

## 22. Tự động hóa assertion bằng DO block trong PostgreSQL

Với test đơn giản, có thể dùng PL/pgSQL để báo lỗi nếu bất biến không đạt.

~~~sql
DO $do$
DECLARE
    v_order_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_order_count
    FROM lab_r414_orders;

    IF v_order_count <> 5 THEN
        RAISE EXCEPTION
            'Expected 5 orders, got %',
            v_order_count;
    END IF;
END;
$do$;
~~~

Đây là assertion cho fixture sau khi đã thêm order 105. Trong test có dữ liệu nhạy cảm, không đưa raw values vào exception message. Với fixture giả, in số đếm thường không có vấn đề; trong môi trường thật, message vẫn nên chỉ chứa thông tin cần thiết.

Với dự án PostgreSQL lớn, có thể sử dụng framework kiểm thử database như pgTAP hoặc tích hợp test SQL vào pipeline. Framework giúp tổ chức assertion, báo cáo pass/fail và fixture. Dù dùng công cụ nào, vẫn cần định nghĩa grain và expected result độc lập.

## 23. Khác biệt giữa các SQL dialect

Nguyên tắc grain, cardinality, expected result, NULL và thứ tự áp dụng rộng rãi, nhưng cú pháp so sánh và kiểu dữ liệu khác nhau.

### 23.1. PostgreSQL

PostgreSQL hỗ trợ CTE, VALUES để khai báo expected fixtures, EXCEPT và EXCEPT ALL để so sánh tập, IS DISTINCT FROM để so sánh NULL an toàn, window functions và các phép JOIN chuẩn.

### 23.2. SQL Server

SQL Server hỗ trợ CTE, VALUES, window functions và EXCEPT nhưng không có cú pháp EXCEPT ALL giống PostgreSQL. Nếu cần so sánh multiplicity, nhóm theo tất cả cột và đếm số lần xuất hiện rồi FULL OUTER JOIN hai tập đã đếm.

SQL Server dùng datetime, datetime2 và datetimeoffset với độ chính xác và múi giờ khác PostgreSQL. Khi so expected timestamp, hãy xác định kiểu và offset.

### 23.3. MySQL

MySQL hỗ trợ CTE và window functions ở các phiên bản hiện đại; EXCEPT được hỗ trợ ở các phiên bản mới hơn, nên phải xác định phiên bản trước khi dùng. Với phiên bản không hỗ trợ phép set difference phù hợp, dùng LEFT JOIN/NOT EXISTS hai chiều và so sánh NULL-aware.

MySQL có quy tắc NULL, collation, timezone session và kiểu DECIMAL cần xét. So sánh chuỗi có thể phụ thuộc collation.

### 23.4. Oracle Database

Oracle hỗ trợ CTE, analytic/window functions, MINUS thay cho EXCEPT trong phép hiệu tập hợp truyền thống, và phép so sánh NULL cần xử lý rõ ràng. Cú pháp so sánh NULL-safe phụ thuộc phiên bản; cần kiểm tra trước khi dùng.

Kiểu NUMBER và TIMESTAMP có quy tắc độ chính xác riêng. Đừng giả định định dạng hiển thị ngày giờ giống PostgreSQL.

### 23.5. SQLite

SQLite hỗ trợ CTE, window functions ở phiên bản phù hợp và EXCEPT theo ngữ nghĩa tập hợp. EXCEPT loại duplicate; để so multiplicity cần nhóm và đếm. SQLite có kiểu dữ liệu linh hoạt hơn và không có cùng hệ kiểu NUMERIC/TIMESTAMPTZ như PostgreSQL.

### 23.6. Bảng so sánh

| Nội dung | PostgreSQL | SQL Server | MySQL | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| CTE | Có | Có | Có ở phiên bản hiện đại | Có | Có |
| Window functions | Có | Có | Có ở phiên bản hiện đại | Có | Có ở phiên bản phù hợp |
| EXCEPT | Có | Có | Tùy phiên bản mới | Thường dùng MINUS | Có |
| EXCEPT ALL | Có | Không cùng cú pháp | Tùy phiên bản/không đồng nhất | Không cùng cú pháp | Không |
| NULL-safe equality | IS DISTINCT FROM | Cần cú pháp/biểu thức theo phiên bản | <=> | Biểu thức tương đương theo kiểu | IS / IS NOT theo ngữ nghĩa SQLite |
| Timestamp có timezone | TIMESTAMPTZ | datetimeoffset | Phụ thuộc TIMESTAMP/DATETIME | TIMESTAMP WITH TIME ZONE | Không có kiểu chuyên biệt tương đương |
| Decimal chính xác | NUMERIC/DECIMAL | DECIMAL/NUMERIC | DECIMAL | NUMBER | Kiểu linh hoạt, cần kiểm soát |

**Luôn kiểm tra phiên bản DBMS và driver** khi bài test phụ thuộc cú pháp hoặc định dạng kết quả cụ thể.

## 24. Những lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Không nói rõ một hàng đại diện cho gì | Grain bị ngầm định | Viết grain và khóa nhận diện trước |
| Đếm số hàng nguồn rồi mong số hàng JOIN bằng nhau | JOIN một-nhiều mở rộng hàng | Tính cardinality theo từng quan hệ |
| JOIN hai nhánh con rồi SUM | Fan-out nhân các hàng | Tổng hợp mỗi nhánh trước khi JOIN |
| Dùng DISTINCT để chữa duplicate | Chỉ loại trùng trên cột đang chọn | Sửa JOIN/grain |
| INNER JOIN làm mất hàng không có con | Chỉ giữ hàng khớp | Dùng LEFT JOIN khi yêu cầu giữ cha |
| LEFT JOIN nhưng lọc cột phải trong WHERE | Hàng NULL-extended bị loại | Đặt điều kiện phù hợp trong ON |
| COUNT(*) sau LEFT JOIN | Đếm cả hàng NULL-extended | COUNT khóa của bảng con |
| SUM không có hàng trả NULL | Aggregate bỏ qua NULL | COALESCE nếu nghiệp vụ định nghĩa 0 |
| Dùng NOT IN với tập có NULL | UNKNOWN làm điều kiện khó đoán | Dùng NOT EXISTS hoặc xử lý NULL rõ |
| So sánh NULL bằng dấu bằng | NULL = NULL không TRUE | IS NULL hoặc IS DISTINCT FROM |
| Nghĩ GROUP BY giữ grain cũ | GROUP BY tạo grain mới | Xác định khóa nhóm |
| Window function bị hiểu như GROUP BY | Window giữ hàng nguồn | Đếm lại và mô tả grain |
| Dựa vào thứ tự tự nhiên | SQL không đảm bảo nếu thiếu ORDER BY | ORDER BY đầy đủ và tie-breaker |
| LIMIT không ORDER BY | Tập hàng được chọn không ổn định | ORDER BY trước LIMIT |
| ORDER BY không đủ tie-breaker | Nhiều hàng đồng giá trị sort | Thêm khóa duy nhất |
| OFFSET trên dữ liệu thay đổi | Trang có thể lặp/bỏ hàng | Keyset hoặc snapshot phù hợp |
| Expected chỉ là tổng toàn cục | Sai phân bổ vẫn có thể cùng tổng | So từng khóa và từng cột |
| Expected lặp lại logic actual | Hai phía có thể cùng sai | Fixture độc lập/tính tay |
| Chỉ dùng EXCEPT | Không phát hiện multiplicity trong mọi trường hợp | EXCEPT ALL hoặc so count theo hàng |
| Không kiểm tra kiểu/scale | Client format che khác biệt | Kiểm tra type, NUMERIC scale và rounding |
| So timestamp theo chuỗi hiển thị | Timezone/session format khác | So thời điểm và xác định timezone |
| Dùng BETWEEN cho các khoảng liền nhau | Hai khoảng có thể chồng biên | Dùng khoảng nửa mở |
| Dữ liệu test chỉ có trường hợp đẹp | Lỗi biên không xuất hiện | Thêm NULL, empty, no-child, ties, empty set |
| Test song song dùng fixture chung | Race và va chạm khóa | Cô lập fixture/test schema |
| Đếm và truy vấn detail ở snapshot khác nhau | Concurrent transaction thay đổi dữ liệu | Dùng isolation/snapshot phù hợp |
| EXPLAIN ANALYZE trên câu ghi không kiểm soát | Thực thi thật | Sandbox và transaction rollback khi phù hợp |

## 25. Bài tập thực hành có đáp án

Các bài dựa trên dữ liệu lab_r414. Hãy chạy trên sandbox. Nếu đã thêm order 105, giữ dữ liệu đó cho các bài liên quan hoặc nạp fixture từ đầu trong schema mới.

### Bài 1 — Xác định grain

**Yêu cầu:** một báo cáo có order_id, trạng thái và tổng tiền hàng. Một hàng đại diện cho điều gì?

**Đáp án:** một hàng cho mỗi **đơn hàng**. Khóa grain là order_id; mỗi order_id phải xuất hiện đúng một lần.

### Bài 2 — Đếm số hàng dòng hàng

**Yêu cầu:** truy vấn dòng hàng của tất cả đơn.

**Đáp án:** kết quả có **5 hàng** trong fixture ban đầu, grain là một hàng cho mỗi line_id. Nó không phải report một hàng mỗi đơn.

### Bài 3 — Tính tổng đơn 101

~~~sql
SELECT SUM(quantity * unit_price) AS item_total
FROM lab_r414_order_items
WHERE order_id = 101;
~~~

Expected là **250.00**.

### Bài 4 — Nhận diện fan-out

**Tình huống:** JOIN order_items và payments trực tiếp cho order 101.

**Đáp án:** có **4 hàng**, do 2 dòng hàng nhân 2 lần thanh toán. Nếu SUM line_total sau JOIN, kết quả thành 500.00 và sai.

### Bài 5 — Sửa fan-out

**Yêu cầu:** trả một hàng cho mỗi đơn với item_total và paid_total.

**Đáp án:** tổng hợp order_items theo order_id trong một CTE; tổng hợp payments theo order_id trong CTE khác; rồi LEFT JOIN hai kết quả đã có tối đa một hàng mỗi order_id vào orders.

### Bài 6 — Giữ đơn không thanh toán

**Yêu cầu:** liệt kê mọi đơn, kể cả đơn không có payment.

**Đáp án:** dùng LEFT JOIN từ orders sang payments hoặc payment_totals. Không lọc cột payment bằng điều kiện trong WHERE nếu muốn giữ hàng chưa có payment.

### Bài 7 — Phân biệt COUNT

**Tình huống:** đơn 102 không có payment, LEFT JOIN payment.

**Đáp án:** COUNT(*) là 1 vì hàng orders vẫn có mặt; COUNT(payment_id) là 0 vì payment_id NULL.

### Bài 8 — Đếm đơn theo trạng thái

**Yêu cầu:** với fixture ban đầu, đếm từng trạng thái.

**Đáp án:**

| order_status | order_count |
| --- | ---: |
| CANCELLED | 1 |
| NEW | 1 |
| PAID | 2 |

Grain là một hàng cho mỗi trạng thái.

### Bài 9 — Kiểm tra khóa trùng

~~~sql
SELECT order_id, COUNT(*)
FROM report_result
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Expected là 0 hàng nếu grain của report là một hàng mỗi đơn. Thay report_result bằng truy vấn/view thật.

### Bài 10 — WHERE hay ON

**Tình huống:** LEFT JOIN payments nhưng WHERE p.paid_amount > 0.

**Đáp án:** đơn không có payment bị loại. Nếu muốn giữ mọi đơn và chỉ nối payment dương, chuyển điều kiện sang ON.

### Bài 11 — EXISTS hay JOIN

~~~sql
SELECT o.order_id
FROM lab_r414_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM lab_r414_payments AS p
    WHERE p.order_id = o.order_id
);
~~~

EXISTS liệt kê mỗi đơn có ít nhất một payment đúng một lần, bất kể có bao nhiêu payment.

### Bài 12 — Thêm đơn không có dòng hàng

**Yêu cầu:** thêm order 105 không có order_items. Report một hàng mỗi đơn phải trả item_count và item_total bao nhiêu?

**Đáp án:** **0 và 0.00**, nếu hợp đồng quy định đơn chưa có dòng hàng có tổng bằng 0. Dùng LEFT JOIN và COALESCE.

### Bài 13 — So sánh NULL

~~~sql
actual_value IS DISTINCT FROM expected_value
~~~

Biểu thức trả TRUE khi khác nhau, kể cả một phía NULL và phía kia không NULL.

### Bài 14 — EXCEPT và duplicate

**Câu hỏi:** vì sao EXCEPT thường không đủ để phát hiện một hàng actual bị lặp?

**Đáp án:** EXCEPT có ngữ nghĩa tập hợp và loại duplicate. Dùng EXCEPT ALL hai chiều hoặc nhóm toàn bộ cột rồi so COUNT để kiểm tra multiplicity.

### Bài 15 — Thứ tự kết quả

**Yêu cầu:** sắp xếp đơn theo created_at tăng dần, ổn định khi timestamp trùng.

**Đáp án:**

~~~sql
ORDER BY created_at, order_id
~~~

order_id làm tie-breaker.

### Bài 16 — Phân trang

**Câu hỏi:** LIMIT 2 OFFSET 2 có đảm bảo trang sau không lặp hàng khi có insert mới giữa hai lần gọi?

**Đáp án:** không. OFFSET phụ thuộc vị trí hiện tại trong tập đã sắp xếp. Cân nhắc keyset pagination hoặc snapshot nhất quán theo yêu cầu.

### Bài 17 — Khoảng ngày

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-01-10 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-01-11 00:00:00+07'
~~~

Khoảng nửa mở lấy ngày 10/01/2026 theo múi giờ +07.

### Bài 18 — GROUP BY đổi grain

**Câu hỏi:** GROUP BY customer_id, order_status tạo một hàng cho mỗi khách hay mỗi khách-trạng thái?

**Đáp án:** một hàng cho mỗi **cặp customer_id + order_status**.

### Bài 19 — Window function

**Câu hỏi:** ROW_NUMBER() OVER (PARTITION BY customer_id ...) có làm giảm số hàng không?

**Đáp án:** không. Nó gắn số thứ tự vào từng hàng. Chỉ khi lọc rn = 1 ở query ngoài, tập kết quả mới giảm xuống một hàng mỗi partition.

### Bài 20 — Expected result độc lập

**Tình huống:** actual và expected cùng gọi một function tổng tiền đang kiểm thử.

**Đáp án:** test có thể cùng sai vì dùng chung logic. Hãy tạo fixture nhỏ, tính expected độc lập bằng tay hoặc một cách diễn đạt khác.

### Bài 21 — COUNT(*) sau LEFT JOIN

**Yêu cầu:** đếm số dòng hàng của từng đơn, bao gồm đơn chưa có dòng.

**Đáp án:** COUNT(i.line_id), không phải COUNT(*), vì line_id NULL trên hàng được LEFT JOIN giữ lại.

### Bài 22 — Tổng toàn cục có đủ không?

**Câu hỏi:** actual và expected có cùng SUM(item_total). Có thể kết luận report đúng không?

**Đáp án:** không. Một đơn có thể bị cộng thừa và đơn khác bị thiếu với tổng chung vẫn trùng. So từng khóa grain và từng cột.

### Bài 23 — Test transaction

**Yêu cầu:** thêm fixture tạm và không giữ lại sau test.

**Đáp án:** chạy trong BEGIN, thực hiện INSERT và assertion, sau đó ROLLBACK. Lưu ý sequence có thể không quay lại giá trị trước đó.

### Bài 24 — Điều tra sai số

**Tình huống:** report trả 8 hàng trong khi expected là 4; mỗi order có hai dòng hàng.

**Đáp án:** kiểm tra JOIN từ orders sang order_items. Có khả năng query đang ở grain dòng hàng hoặc chưa tổng hợp về order_id trước khi JOIN. Đừng thêm DISTINCT trước khi hiểu nguyên nhân.

## 26. Checklist xác định tập kết quả mong đợi

- [ ] Mục đích nghiệp vụ của truy vấn.
- [ ] Grain: một hàng đại diện cho thực thể/tổ hợp nào.
- [ ] Khóa duy nhất của grain.
- [ ] Các cột đầu ra, kiểu, NULLability và scale.
- [ ] Điều kiện bao gồm/loại hàng.
- [ ] Cardinality của mỗi JOIN và nhánh một-nhiều.
- [ ] Cách xử lý hàng thiếu quan hệ, NULL, empty và duplicate.
- [ ] Quy tắc GROUP BY, COUNT, SUM và rounding.
- [ ] Thứ tự đầy đủ, tie-breaker và pagination.
- [ ] Timezone, khoảng nửa mở và biên thời gian.
- [ ] Expected fixture độc lập, có dữ liệu biên.
- [ ] Assertion số hàng, uniqueness, coverage, values và multiplicity.
- [ ] Snapshot/transaction và cách cô lập test song song.
- [ ] Cleanup/rollback để không làm bẩn dữ liệu.

## 27. Ghi nhớ

| Câu hỏi | Nguyên tắc |
| --- | --- |
| Một hàng đại diện cho điều gì? | Grain phải được xác định trước |
| JOIN một-nhiều làm gì? | Có thể nhân số hàng theo cardinality |
| Hai nhánh con đều nhiều hàng? | Có thể tạo tích số hàng; aggregate từng nhánh trước JOIN |
| Khi nào dùng LEFT JOIN? | Khi cần giữ hàng bên trái dù không có hàng khớp |
| WHERE lọc sau JOIN ra sao? | Có thể loại hàng NULL-extended của LEFT JOIN |
| COUNT(*) khác COUNT(child_id)? | COUNT(*) đếm hàng nối; COUNT(child_id) bỏ NULL |
| SUM trên tập rỗng trả gì? | NULL, dùng COALESCE nếu nghiệp vụ định nghĩa 0 |
| GROUP BY làm gì với grain? | Tạo grain theo các cột nhóm |
| Window function có giữ số hàng? | Thường có; nó thêm giá trị trên từng hàng |
| Có ORDER BY mặc định không? | Không có cam kết thứ tự nếu thiếu ORDER BY ngoài cùng |
| LIMIT cần gì? | ORDER BY ổn định, có tie-breaker |
| EXCEPT có bắt duplicate không? | Không đầy đủ; dùng EXCEPT ALL hoặc so multiplicity |
| So NULL thế nào trong PostgreSQL? | IS DISTINCT FROM / IS NOT DISTINCT FROM |
| Kiểm tra tổng chung đã đủ chưa? | Không; so theo khóa grain và từng cột |
| Expected nên lấy từ đâu? | Fixture độc lập và có thể tính/giải thích |
| Ngày giờ cần ghi rõ gì? | Timezone, biên và độ chính xác |
| Test nhiều statement cần lưu ý? | Snapshot/isolation và concurrent changes |
| Test có dữ liệu tạm cần gì? | Transaction rollback hoặc cleanup cô lập |

**Điểm cốt lõi:** một kết quả SQL chỉ có thể kiểm thử rõ ràng khi ta biết **mỗi hàng đại diện cho điều gì**, **hàng nào phải xuất hiện** và **giá trị nào phải nằm trong từng hàng**. Xác định grain trước JOIN, tính cardinality theo quan hệ, tổng hợp đúng mức, kiểm soát NULL và thứ tự, rồi so actual với expected theo cả khóa, giá trị và số lần xuất hiện. Khi hợp đồng kết quả được viết rõ, việc gỡ lỗi trở thành quá trình tìm ra bước biến đổi làm sai tập hàng thay vì phỏng đoán dựa trên vài dòng trông có vẻ hợp lý.
