# Bao phủ bảng rỗng, một hàng, nhiều hàng và bản sao

Một truy vấn SQL có thể chạy đúng với dữ liệu mẫu gồm vài bản ghi đẹp, nhưng thất bại khi bảng chưa có dữ liệu, chỉ có một hàng, có nhiều hàng hoặc chứa những bản ghi trùng nhau. Đây là một nhóm lỗi rất thường gặp khi kiểm thử cơ sở dữ liệu: code vô tình giả định rằng luôn có kết quả, luôn chỉ có một kết quả, hoặc mỗi khóa tìm được chỉ xuất hiện đúng một lần.

Trong SQL, số lượng hàng và tính trùng lặp ảnh hưởng đến cách truy vấn hoạt động. Một phép JOIN có thể nhân số hàng; một truy vấn con dùng như giá trị đơn có thể lỗi khi trả nhiều hàng; phép tổng hợp trên tập rỗng có thể trả NULL thay vì 0; còn ORDER BY không đầy đủ có thể khiến thứ tự các hàng bằng nhau thay đổi giữa các lần chạy.

Bài học thuộc chương **Kiểm thử và gỡ lỗi** của **Database SQL**. Ta xây dựng bộ dữ liệu có các trường hợp **0 hàng, 1 hàng, nhiều hàng và duplicate**, sau đó dùng chúng để kiểm thử SELECT, JOIN, aggregate, subquery, window function, UPDATE/DELETE, UNIQUE, UPSERT và phân trang. Mục tiêu là biến các giả định về số lượng hàng thành những trường hợp kiểm thử có thể lặp lại và xác minh được.

> **Nguyên tắc:** mỗi truy vấn cần được kiểm thử với tập kết quả rỗng, một hàng, nhiều hàng và dữ liệu trùng khi các trường hợp đó có thể xảy ra theo nghiệp vụ. Đừng chỉ kiểm tra rằng câu SQL không báo lỗi; hãy kiểm tra **số hàng, giá trị, tính duy nhất, thứ tự và tác động dữ liệu**.

## 1. Bốn hình dạng dữ liệu cần bao phủ

Giả sử ứng dụng có bảng đơn hàng và truy vấn tìm đơn theo khách hàng.

### 1.1. Bảng rỗng — 0 hàng

Một bảng rỗng là bảng hợp lệ có cấu trúc nhưng chưa có bản ghi:

~~~sql
SELECT order_id, customer_id, total_amount
FROM sales_orders
WHERE customer_id = 42;
~~~

Nếu không có đơn hàng phù hợp, kết quả là tập rỗng. Truy vấn SELECT vẫn chạy thành công. Ứng dụng phải xử lý được việc không có hàng để đọc.

Những giả định dễ sai:

- Luôn có ít nhất một hàng.
- Hàm lấy hàng đầu tiên luôn trả dữ liệu.
- Tổng tiền của tập rỗng bằng 0 trong mọi hàm tổng hợp.
- Một thao tác UPDATE luôn tác động ít nhất một hàng.
- Trang đầu tiên luôn có dữ liệu.

### 1.2. Một hàng — đúng 1 hàng

Khi có một đơn hàng phù hợp:

~~~sql
SELECT order_id, customer_id, total_amount
FROM sales_orders
WHERE customer_id = 42;
~~~

truy vấn trả đúng một hàng. Đây là trường hợp thường làm lộ lỗi truy cập kết quả không kiểm tra, xử lý NULL, hoặc code vô tình giả định có nhiều hàng.

### 1.3. Nhiều hàng — 2 hàng trở lên

Một khách hàng có thể có nhiều đơn:

~~~sql
SELECT order_id, customer_id, total_amount
FROM sales_orders
WHERE customer_id = 42;
~~~

Ứng dụng cần lặp qua toàn bộ tập kết quả, không chỉ đọc hàng đầu. Một số lỗi chỉ xuất hiện khi kết quả có nhiều hơn một hàng, ví dụ scalar subquery, phép JOIN, gom nhóm hoặc phân trang.

### 1.4. Bản sao — nhiều hàng có giá trị giống nhau

Hai hàng có thể giống nhau ở một số hoặc tất cả các cột được truy vấn:

~~~text
order_id | customer_id | status
---------+-------------+--------
7001     | 42          | PAID
7002     | 42          | PAID
~~~

Hai hàng có status giống nhau nhưng là hai đơn hàng khác nhau. Nếu SELECT chỉ lấy status, kết quả sẽ có hai dòng PAID. Đó là kết quả đúng khi không dùng DISTINCT.

Duplicate cần được hiểu theo ngữ cảnh:

- **Trùng khóa nghiệp vụ:** hai hàng có cùng email, mã ngoài hoặc mã giao dịch vốn phải duy nhất.
- **Trùng giá trị một cột:** nhiều hàng có cùng status, category hoặc amount; thường hoàn toàn hợp lệ.
- **Trùng toàn bộ các cột được chiếu:** hai hàng khác nhau ở cột không được SELECT, nên kết quả nhìn như hai dòng giống nhau.
- **Trùng do JOIN:** một hàng phía trái khớp nhiều hàng phía phải, làm kết quả nhân lên.
- **Trùng do dữ liệu lặp ngoài ý muốn:** cùng một sự kiện bị nhập hai lần hoặc một job chạy lặp.

Không phải mọi hàng giống nhau đều là dữ liệu lỗi. Phải xác định khóa và quy tắc nghiệp vụ trước khi dùng DISTINCT hoặc thêm UNIQUE.

## 2. Tạo bộ dữ liệu thực hành có chủ ý

Ta dùng PostgreSQL làm ví dụ chính. Bảng mẫu có khách hàng, đơn hàng và dòng chi tiết. Dữ liệu được sắp đặt để có:

- Khách hàng chưa có đơn.
- Khách hàng có đúng một đơn.
- Khách hàng có nhiều đơn.
- Nhiều đơn có cùng trạng thái.
- Nhiều dòng chi tiết có cùng product_id.
- Một đơn có nhiều dòng hàng.
- Một sản phẩm xuất hiện ở nhiều đơn.

### 2.1. Tạo bảng

~~~sql
DROP TABLE IF EXISTS order_items_lab;
DROP TABLE IF EXISTS sales_orders_lab;
DROP TABLE IF EXISTS customers_lab;

CREATE TABLE customers_lab (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE sales_orders_lab (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES customers_lab(customer_id),
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_items_lab (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES sales_orders_lab(order_id),
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
);
~~~

### 2.2. Nạp khách hàng

~~~sql
INSERT INTO customers_lab
    (customer_id, customer_name, email)
VALUES
    (1, 'An', 'an@example.test'),
    (2, 'Binh', 'binh@example.test'),
    (3, 'Chi', 'chi@example.test'),
    (4, 'Dung', 'dung@example.test'),
    (5, 'Ha', 'ha@example.test');
~~~

### 2.3. Nạp đơn hàng

~~~sql
INSERT INTO sales_orders_lab
    (order_id, customer_id, status, total_amount, created_at)
VALUES
    (101, 2, 'PAID', 120.00, '2025-01-01 08:00:00+00'),
    (102, 3, 'NEW',   80.00, '2025-01-02 08:00:00+00'),
    (103, 3, 'PAID', 200.00, '2025-01-03 08:00:00+00'),
    (104, 3, 'PAID', 200.00, '2025-01-03 08:00:00+00'),
    (105, 4, 'CANCELLED', 50.00, '2025-01-04 08:00:00+00');
~~~

Ý nghĩa:

| Khách hàng | Số đơn | Tình huống |
|---|---:|---|
| An (1) | 0 | Không có đơn |
| Binh (2) | 1 | Một hàng |
| Chi (3) | 3 | Nhiều hàng |
| Dung (4) | 1 | Một hàng với trạng thái khác |
| Ha (5) | 0 | Một trường hợp rỗng khác |

Hai đơn 103 và 104 có cùng customer, status, amount và timestamp nhưng order_id khác nhau. Đây là **các hàng khác nhau có nhiều giá trị giống nhau**, không phải duplicate khóa chính.

### 2.4. Nạp dòng chi tiết

~~~sql
INSERT INTO order_items_lab
    (item_id, order_id, product_id, quantity, unit_price)
VALUES
    (1, 101, 900, 1, 120.00),
    (2, 102, 901, 1,  80.00),
    (3, 103, 900, 1, 100.00),
    (4, 103, 902, 2,  50.00),
    (5, 104, 900, 1, 100.00),
    (6, 104, 902, 2,  50.00),
    (7, 104, 902, 1,  50.00),
    (8, 105, 903, 1,  50.00);
~~~

Sản phẩm 900 xuất hiện trong nhiều đơn. Sản phẩm 902 xuất hiện hai lần trong đơn 104. Nếu truy vấn chỉ chiếu order_id và product_id, hai dòng có thể nhìn giống nhau.

## 3. Kiểm thử đúng số lượng hàng của SELECT

### 3.1. Truy vấn không tìm thấy hàng

~~~sql
SELECT order_id, status
FROM sales_orders_lab
WHERE customer_id = 1;
~~~

Kết quả: **0 hàng**.

Điều cần xác minh:

- Không phát sinh exception chỉ vì không có kết quả.
- Ứng dụng trả danh sách rỗng hoặc trạng thái not found theo hợp đồng API.
- Không đọc cột của một ResultSet chưa có hàng.
- Không biến “không có đơn” thành “lỗi database”.

### 3.2. Truy vấn trả đúng một hàng

~~~sql
SELECT order_id, status
FROM sales_orders_lab
WHERE customer_id = 2;
~~~

Kết quả: một hàng, order_id 101.

Điều cần xác minh:

- Code đọc đúng hàng.
- Trạng thái và giá trị được ánh xạ đúng kiểu.
- Nếu API yêu cầu một kết quả duy nhất, nó không chỉ kiểm tra hàng đầu rồi bỏ qua khả năng có thêm hàng.

### 3.3. Truy vấn trả nhiều hàng

~~~sql
SELECT order_id, status
FROM sales_orders_lab
WHERE customer_id = 3
ORDER BY order_id;
~~~

Kết quả có ba hàng: 102, 103, 104.

Điều cần xác minh:

- Tất cả ba hàng được đọc.
- Không dừng vòng lặp sau hàng đầu.
- Không ghi đè kết quả trước bằng kết quả sau khi đáng lẽ phải tích lũy danh sách.
- Thứ tự được xác định bằng ORDER BY nếu thứ tự là một phần hợp đồng.

### 3.4. Nhiều hàng có giá trị lặp

~~~sql
SELECT status
FROM sales_orders_lab
WHERE customer_id = 3
ORDER BY order_id;
~~~

Kết quả:

~~~text
NEW
PAID
PAID
~~~

Nếu ứng dụng nhận hai giá trị PAID, đó là đúng theo truy vấn. Không tự loại bản sao chỉ vì chúng giống nhau ở cột status.

### 3.5. Đếm số hàng trong kết quả

~~~sql
SELECT COUNT(*) AS row_count
FROM sales_orders_lab
WHERE customer_id = 3;
~~~

Kết quả là 3. Với customer_id 1, kết quả của COUNT(*) là **một hàng chứa giá trị 0**, không phải tập kết quả rỗng. Đây là khác biệt quan trọng giữa:

- Truy vấn thường không có hàng phù hợp: kết quả 0 hàng.
- Truy vấn aggregate không GROUP BY: thường vẫn trả một hàng tổng hợp; COUNT(*) có giá trị 0.

## 4. Phân biệt tập kết quả rỗng với một hàng có giá trị NULL

Hai kết quả sau không giống nhau.

### 4.1. Không có hàng

~~~sql
SELECT order_id
FROM sales_orders_lab
WHERE order_id = -1;
~~~

Không có dòng nào. Ứng dụng không thể đọc một order_id NULL từ một hàng không tồn tại.

### 4.2. Có một hàng nhưng cột NULL

~~~sql
SELECT NULL::INTEGER AS order_id;
~~~

Kết quả có **một hàng**, trong đó order_id là NULL.

### 4.3. Kiểm tra ở tầng ứng dụng

Khi đọc ResultSet JDBC:

~~~java
if (rs.next()) {
    int value = rs.getInt("some_value");
    boolean wasNull = rs.wasNull();
    // Có hàng; giá trị cột có thể NULL.
} else {
    // Không có hàng.
}
~~~

Không dùng giá trị mặc định mà driver trả về cho kiểu primitive để suy ra có dữ liệu hay không. Với JDBC, getInt trên SQL NULL trả 0; phải kiểm tra wasNull nếu cần phân biệt 0 thật với NULL.

## 5. SQL dùng bag semantics: hàng trùng được giữ lại

SQL thông thường không tự loại các hàng trùng. Nhiều phép toán làm việc theo **multiset/bag semantics**: một giá trị có thể xuất hiện nhiều lần.

### 5.1. SELECT không có DISTINCT giữ duplicate

~~~sql
SELECT status
FROM sales_orders_lab
WHERE customer_id = 3;
~~~

Kết quả có hai hàng PAID. Nếu thêm DISTINCT:

~~~sql
SELECT DISTINCT status
FROM sales_orders_lab
WHERE customer_id = 3;
~~~

Kết quả chỉ có NEW và PAID.

Hai câu trả lời khác nhau cho hai câu hỏi:

- Không DISTINCT: có bao nhiêu đơn và trạng thái của từng đơn?
- DISTINCT: khách hàng có những trạng thái khác nhau nào?

### 5.2. DISTINCT không sửa dữ liệu nguồn

~~~sql
SELECT DISTINCT status
FROM sales_orders_lab;
~~~

chỉ loại hàng trùng trong **tập kết quả truy vấn**. Nó không xóa đơn hàng trùng khỏi bảng, không tạo UNIQUE constraint và không ngăn dữ liệu trùng được chèn lần sau.

### 5.3. DISTINCT trên nhiều cột

~~~sql
SELECT DISTINCT status, total_amount
FROM sales_orders_lab
ORDER BY status, total_amount;
~~~

Database loại những hàng trùng theo **toàn bộ tổ hợp cột được chọn**. Hai hàng cùng status nhưng khác amount vẫn là hai tổ hợp khác nhau.

### 5.4. COUNT(*) và COUNT(DISTINCT ...)

~~~sql
SELECT
    COUNT(*) AS order_rows,
    COUNT(DISTINCT status) AS distinct_statuses,
    COUNT(DISTINCT customer_id) AS customers_with_orders
FROM sales_orders_lab;
~~~

Với dữ liệu mẫu:

| order_rows | distinct_statuses | customers_with_orders |
|---:|---:|---:|
| 5 | 3 | 3 |

COUNT(*) đếm hàng. COUNT(DISTINCT status) đếm giá trị trạng thái phân biệt không NULL. COUNT(DISTINCT customer_id) đếm số khách hàng có ít nhất một đơn trong tập đầu vào.

## 6. JOIN có thể nhân số hàng

Một lỗi phổ biến là thấy duplicate sau JOIN rồi cho rằng database tự nhân bản dữ liệu. Thường đó là kết quả đúng của quan hệ một-nhiều.

### 6.1. Một khách hàng có ba đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers_lab AS c
JOIN sales_orders_lab AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 3
ORDER BY o.order_id;
~~~

Kết quả có ba hàng, tên khách hàng Chi lặp ba lần. Một hàng khách hàng khớp ba hàng đơn hàng.

### 6.2. LEFT JOIN giữ khách hàng không có đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers_lab AS c
LEFT JOIN sales_orders_lab AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Kết quả có:

- Customer 1: một hàng với order_id NULL.
- Customer 2: một hàng có order_id 101.
- Customer 3: ba hàng có order_id 102, 103, 104.
- Customer 4: một hàng có order_id 105.
- Customer 5: một hàng với order_id NULL.

Tổng cộng **7 hàng kết quả**, dù bảng khách hàng có 5 hàng và bảng đơn hàng có 5 hàng.

### 6.3. COUNT(*) sau LEFT JOIN có thể đếm sai ý định

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS actual_order_count
FROM customers_lab AS c
LEFT JOIN sales_orders_lab AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | joined_rows | actual_order_count |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 1 | 1 |
| 3 | 3 | 3 |
| 4 | 1 | 1 |
| 5 | 1 | 0 |

Với khách hàng không có đơn, LEFT JOIN tạo một hàng placeholder có cột phía đơn NULL. Vì thế COUNT(*) là 1, còn COUNT(o.order_id) là 0.

### 6.4. Hai bảng con cùng JOIN có thể tạo tích nhân

Giả sử một đơn có 2 dòng hàng và có 3 bản ghi thanh toán. JOIN cả order_items và payments theo order_id có thể tạo 2 × 3 = 6 hàng cho đơn đó.

Nếu chỉ muốn tổng tiền dòng hàng và tổng tiền thanh toán, không nên cộng trực tiếp sau khi JOIN hai quan hệ một-nhiều vì mỗi dòng hàng bị lặp theo số bản ghi thanh toán. Hãy tổng hợp từng bảng con trước rồi JOIN các kết quả đã gom:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items_lab
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
    i.item_total,
    p.paid_total
FROM sales_orders_lab AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id;
~~~

Trong ví dụ này bảng payments chỉ minh họa mô hình quan hệ; cần tạo bảng đó nếu muốn chạy toàn bộ truy vấn. Bài học là **tổng hợp từng phía một-nhiều trước khi ghép** nếu mục tiêu là một hàng trên mỗi đơn.

### 6.5. EXISTS không nhân hàng cha

Nếu chỉ cần biết khách hàng có đơn hay không, dùng EXISTS:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers_lab AS c
WHERE EXISTS (
    SELECT 1
    FROM sales_orders_lab AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Mỗi khách hàng xuất hiện tối đa một lần trong kết quả, bất kể họ có một hay nhiều đơn. Đây là khác biệt với JOIN trực tiếp.

## 7. Truy vấn con: 0, 1 và nhiều hàng có ý nghĩa khác nhau

Scalar subquery là truy vấn con được dùng ở vị trí cần một giá trị đơn.

### 7.1. Scalar subquery trả 0 hàng

~~~sql
SELECT
    c.customer_id,
    (
        SELECT o.total_amount
        FROM sales_orders_lab AS o
        WHERE o.customer_id = c.customer_id
          AND o.order_id = -1
    ) AS amount
FROM customers_lab AS c
WHERE c.customer_id = 1;
~~~

Trong PostgreSQL, scalar subquery không có hàng trả về NULL.

### 7.2. Scalar subquery trả đúng 1 hàng

~~~sql
SELECT
    c.customer_id,
    (
        SELECT o.total_amount
        FROM sales_orders_lab AS o
        WHERE o.order_id = 101
    ) AS amount
FROM customers_lab AS c
WHERE c.customer_id = 2;
~~~

Kết quả amount là 120.00.

### 7.3. Scalar subquery trả nhiều hàng

~~~sql
SELECT
    c.customer_id,
    (
        SELECT o.total_amount
        FROM sales_orders_lab AS o
        WHERE o.customer_id = 3
    ) AS amount
FROM customers_lab AS c
WHERE c.customer_id = 3;
~~~

Trong PostgreSQL, truy vấn này lỗi vì scalar subquery trả nhiều hơn một hàng. Đây không phải trường hợp database tự chọn hàng đầu tiên.

Nếu nghiệp vụ cần một giá trị, hãy xác định quy tắc:

- MAX(total_amount) nếu cần giá trị lớn nhất.
- MIN(created_at) nếu cần thời điểm sớm nhất.
- ORDER BY ... LIMIT 1 nếu cần bản ghi gần nhất theo một tiêu chí rõ ràng.
- UNIQUE constraint nếu quan hệ đáng lẽ chỉ có một hàng.

Không dùng LIMIT 1 chỉ để che việc dữ liệu có nhiều hàng trái với giả định.

### 7.4. Dùng IN khi chấp nhận nhiều hàng

~~~sql
SELECT customer_id, customer_name
FROM customers_lab
WHERE customer_id IN (
    SELECT customer_id
    FROM sales_orders_lab
    WHERE status = 'PAID'
)
ORDER BY customer_id;
~~~

IN chấp nhận truy vấn con trả nhiều giá trị. Bản sao trong tập con không làm customer xuất hiện lặp trong kết quả outer query.

### 7.5. EXISTS và IN

EXISTS trả lời câu hỏi có ít nhất một hàng phù hợp hay không. IN kiểm tra giá trị có thuộc tập kết quả hay không. Khi dữ liệu con có duplicate, cả hai thường vẫn giữ hàng outer một lần vì điều kiện là predicate, nhưng NULL có thể ảnh hưởng logic của NOT IN.

Đặc biệt:

~~~sql
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM sales_orders_lab AS o
)
~~~

nếu tập con có NULL, kết quả NOT IN có thể trở thành UNKNOWN cho nhiều hàng. Với quan hệ kiểm tra không tồn tại, NOT EXISTS thường dễ diễn đạt đúng hơn:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_orders_lab AS o
    WHERE o.customer_id = c.customer_id
)
~~~

## 8. Aggregate trên tập rỗng và nhiều hàng

Các hàm aggregate không có cùng quy tắc trả về khi đầu vào rỗng.

### 8.1. COUNT trả 0

~~~sql
SELECT COUNT(*) AS order_count
FROM sales_orders_lab
WHERE customer_id = 1;
~~~

Kết quả là một hàng: order_count = 0.

### 8.2. SUM, AVG, MIN, MAX trên tập rỗng

~~~sql
SELECT
    COUNT(*) AS n,
    SUM(total_amount) AS total,
    AVG(total_amount) AS average,
    MIN(total_amount) AS minimum,
    MAX(total_amount) AS maximum
FROM sales_orders_lab
WHERE customer_id = 1;
~~~

Trong PostgreSQL và nhiều DBMS:

| n | total | average | minimum | maximum |
|---:|---|---|---|---|
| 0 | NULL | NULL | NULL | NULL |

COUNT trả 0; các aggregate còn lại thường trả NULL khi không có giá trị đầu vào. Đừng mặc định SUM trên tập rỗng là 0.

### 8.3. COALESCE khi nghiệp vụ muốn 0

~~~sql
SELECT
    COALESCE(SUM(total_amount), 0) AS total_amount
FROM sales_orders_lab
WHERE customer_id = 1;
~~~

Kết quả là 0.00. COALESCE thể hiện quyết định nghiệp vụ: coi tổng của tập rỗng là 0 trong báo cáo này.

### 8.4. GROUP BY không tạo nhóm cho khóa không tồn tại

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM sales_orders_lab
GROUP BY customer_id
ORDER BY customer_id;
~~~

Chỉ những customer_id có hàng trong sales_orders_lab mới xuất hiện. Khách hàng 1 và 5 không có nhóm.

Nếu báo cáo cần tất cả khách hàng, kể cả người chưa có đơn, hãy bắt đầu từ customers và LEFT JOIN:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM customers_lab AS c
LEFT JOIN sales_orders_lab AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Đếm COUNT(o.order_id), không phải COUNT(*), để khách hàng không có đơn được đếm 0.

### 8.5. DISTINCT aggregate thay đổi ý nghĩa

~~~sql
SELECT
    COUNT(*) AS rows_count,
    COUNT(DISTINCT total_amount) AS distinct_amounts,
    SUM(total_amount) AS sum_all_orders,
    SUM(DISTINCT total_amount) AS sum_distinct_amounts
FROM sales_orders_lab
WHERE customer_id = 3;
~~~

Với customer 3, có ba đơn 80, 200, 200:

- rows_count = 3.
- distinct_amounts = 2.
- sum_all_orders = 480.
- sum_distinct_amounts = 280.

SUM(DISTINCT total_amount) thường **không phải** tổng doanh thu nếu hai đơn hợp lệ có cùng giá trị. Chỉ dùng DISTINCT khi nghiệp vụ yêu cầu tổng các mức giá phân biệt.

## 9. Kiểm thử GROUP BY, HAVING và bản sao

### 9.1. Nhóm có nhiều hàng

~~~sql
SELECT
    customer_id,
    status,
    COUNT(*) AS order_count
FROM sales_orders_lab
GROUP BY customer_id, status
ORDER BY customer_id, status;
~~~

Customer 3 có hai hàng PAID trong cùng nhóm, nên order_count là 2.

### 9.2. HAVING lọc theo số lượng

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM sales_orders_lab
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Chỉ customer 3 được trả về. Truy vấn này cần test với:

- Không có nhóm nào đạt điều kiện.
- Đúng một nhóm đạt điều kiện.
- Nhiều nhóm đạt điều kiện.
- Một nhóm có đúng ngưỡng và một nhóm vượt ngưỡng.

### 9.3. Duplicate có thể làm sai COUNT sau JOIN

Nếu bảng con có nhiều dòng khớp, COUNT(*) sau JOIN đếm số cặp hàng. Nếu cần số đơn duy nhất:

~~~sql
COUNT(DISTINCT o.order_id)
~~~

Nếu cần số dòng hàng:

~~~sql
COUNT(i.item_id)
~~~

Đặt tên alias theo ý nghĩa đếm để tránh nhầm “số hàng join” với “số đơn” hay “số khách hàng”.

## 10. Window function và tie rows

Window function thường chạy trên nhiều hàng và giữ lại từng hàng đầu vào.

### 10.1. ROW_NUMBER

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC, order_id DESC
    ) AS row_num
FROM sales_orders_lab
ORDER BY customer_id, row_num;
~~~

Với customer 3, có ba hàng được đánh số 1, 2, 3. Thêm order_id vào ORDER BY để thứ tự xác định khi created_at bằng nhau.

### 10.2. RANK và DENSE_RANK

Nếu hai đơn có cùng created_at:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC
    ) AS rnk,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC
    ) AS dense_rnk
FROM sales_orders_lab
WHERE customer_id = 3
ORDER BY created_at DESC, order_id;
~~~

Hai đơn 103 và 104 cùng timestamp:

- RANK có thể cho hai hàng cùng hạng 1 rồi hạng tiếp theo là 3.
- DENSE_RANK cho hai hàng hạng 1 rồi hạng tiếp theo là 2.

Nếu thêm order_id vào ORDER BY của RANK, hai hàng không còn tie. Vì thế chọn cột trong cửa sổ phải phản ánh đúng câu hỏi nghiệp vụ: xếp hạng theo thời điểm hay tạo thứ tự duy nhất cho từng hàng?

### 10.3. Window function trên tập rỗng

Nếu WHERE loại hết hàng, truy vấn window trả 0 hàng. Window function không tự tạo một hàng tổng hợp như aggregate không GROUP BY.

## 11. Kiểm thử UPDATE và DELETE với 0, 1, nhiều hàng

Không chỉ SELECT mới cần bao phủ cardinality. DML cũng có ba trường hợp quan trọng.

### 11.1. UPDATE không khớp hàng nào

~~~sql
UPDATE sales_orders_lab
SET status = 'REVIEW'
WHERE order_id = -1
RETURNING order_id, status;
~~~

Kết quả RETURNING có 0 hàng. Số hàng bị ảnh hưởng là 0. Đây không nhất thiết là lỗi SQL; có thể là đối tượng không tồn tại hoặc điều kiện không khớp.

Ứng dụng cần quyết định:

- Trả 404 nếu cập nhật một tài nguyên không tồn tại.
- Trả kết quả no-op nếu cập nhật theo lô.
- Ghi nhận optimistic locking conflict nếu version không khớp.

### 11.2. UPDATE đúng một hàng

~~~sql
UPDATE sales_orders_lab
SET status = 'SHIPPED'
WHERE order_id = 101
RETURNING order_id, status;
~~~

Kết quả một hàng. Kiểm tra giá trị mới và số hàng ảnh hưởng.

### 11.3. UPDATE nhiều hàng

~~~sql
UPDATE sales_orders_lab
SET status = 'REVIEW'
WHERE customer_id = 3
RETURNING order_id, status;
~~~

Kết quả ba hàng. Nếu code ứng dụng chỉ đọc một dòng RETURNING, nó có thể bỏ sót hai hàng còn lại dù database đã cập nhật cả ba.

### 11.4. Dùng transaction để chạy thử DML

Các ví dụ thay đổi dữ liệu nên được chạy trong transaction thực hành:

~~~sql
BEGIN;

UPDATE sales_orders_lab
SET status = 'REVIEW'
WHERE customer_id = 3
RETURNING order_id, status;

ROLLBACK;
~~~

ROLLBACK trả dữ liệu về trạng thái trước transaction. Trong ứng dụng thực tế, commit hay rollback phải dựa trên kết quả nghiệp vụ và lỗi, không phải luôn rollback.

### 11.5. DELETE 0/1/N

~~~sql
BEGIN;

DELETE FROM sales_orders_lab
WHERE order_id = -1
RETURNING order_id;

DELETE FROM sales_orders_lab
WHERE order_id = 101
RETURNING order_id;

DELETE FROM sales_orders_lab
WHERE customer_id = 3
RETURNING order_id;

ROLLBACK;
~~~

Ba lệnh lần lượt xóa 0, 1 và 3 hàng trong transaction rồi rollback. Kiểm tra số hàng ảnh hưởng và tác động tới bảng con có FK. Nếu có ON DELETE CASCADE, số hàng ở bảng con bị xóa cũng cần được hiểu và kiểm thử.

## 12. UNIQUE constraint và kiểm thử duplicate

Nếu một thuộc tính phải duy nhất, hãy để database thực thi quy tắc đó thay vì chỉ dựa vào kiểm tra ở ứng dụng.

### 12.1. UNIQUE trên email

~~~sql
ALTER TABLE customers_lab
ADD CONSTRAINT uq_customers_lab_email UNIQUE (email);
~~~

Thử chèn email đã tồn tại:

~~~sql
INSERT INTO customers_lab
    (customer_id, customer_name, email)
VALUES
    (6, 'An copy', 'an@example.test');
~~~

Database từ chối vì email trùng. Kiểm thử nên xác minh:

- Hàng mới không được chèn.
- Lỗi được ánh xạ thành conflict/validation phù hợp.
- Transaction có trạng thái xử lý đúng sau lỗi.
- Ứng dụng không trả thông báo thành công giả.

### 12.2. Unique nhiều cột

Nếu mã ngoài chỉ cần duy nhất trong từng tenant:

~~~sql
CREATE TABLE external_records_lab (
    record_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_code TEXT NOT NULL,
    UNIQUE (tenant_id, external_code)
);
~~~

Hai tenant có thể dùng cùng external_code, nhưng cùng tenant không thể có hai hàng với cùng cặp khóa.

Kiểm thử:

~~~sql
INSERT INTO external_records_lab VALUES
    (1, 10, 'EXT-100'),
    (2, 20, 'EXT-100');
~~~

Hai hàng hợp lệ vì tenant khác nhau. Thử thêm (3, 10, 'EXT-100') phải bị từ chối.

### 12.3. NULL và UNIQUE

Quy tắc UNIQUE đối với NULL có chi tiết khác nhau giữa DBMS và phiên bản. PostgreSQL mặc định cho phép nhiều NULL trong cột UNIQUE vì NULL không được xem là bằng nhau theo quy tắc unique thông thường; PostgreSQL còn có tùy chọn NULLS NOT DISTINCT ở phiên bản hỗ trợ.

Nếu nghiệp vụ yêu cầu mỗi hàng phải có giá trị duy nhất và không NULL, dùng cả:

~~~sql
email TEXT NOT NULL UNIQUE
~~~

Đừng chỉ kiểm thử hai giá trị giống nhau không NULL; hãy kiểm thử cả NULL theo quy tắc DBMS và constraint thực tế.

### 12.4. Duplicate không thuộc khóa unique vẫn hợp lệ

Hai đơn có cùng total_amount không vi phạm PRIMARY KEY hoặc UNIQUE order_id. Không thêm UNIQUE(total_amount) chỉ vì dữ liệu mẫu có giá trị trùng.

## 13. UPSERT: kiểm thử insert mới và conflict

PostgreSQL hỗ trợ INSERT ... ON CONFLICT.

### 13.1. Chèn bản ghi mới

~~~sql
CREATE TABLE inventory_lab (
    product_id INTEGER PRIMARY KEY,
    quantity INTEGER NOT NULL
);

INSERT INTO inventory_lab (product_id, quantity)
VALUES (900, 5)
ON CONFLICT (product_id)
DO UPDATE SET quantity = EXCLUDED.quantity
RETURNING product_id, quantity;
~~~

Lần đầu, không có conflict; hàng được chèn.

### 13.2. Chạy lại cùng khóa

~~~sql
INSERT INTO inventory_lab (product_id, quantity)
VALUES (900, 8)
ON CONFLICT (product_id)
DO UPDATE SET quantity = EXCLUDED.quantity
RETURNING product_id, quantity;
~~~

Lần thứ hai, khóa đã tồn tại; hàng được cập nhật thành quantity 8. Kết quả vẫn có một hàng RETURNING.

### 13.3. Không phải mọi conflict đều nên UPDATE

Nếu cùng external key được gửi lại với payload khác, ứng dụng cần quyết định:

- Đây là retry idempotent, giữ hoặc cập nhật dữ liệu theo quy tắc.
- Đây là conflict nghiệp vụ cần báo lỗi.
- Đây là bản ghi trùng phải ghi nhận để điều tra.

ON CONFLICT DO UPDATE là lựa chọn kỹ thuật, không tự quyết định semantics nghiệp vụ. Kiểm thử cả insert mới, conflict không thay đổi, conflict có thay đổi và constraint khác không được xử lý bởi conflict target.

## 14. Kiểm thử EXISTS, NOT EXISTS và dữ liệu trùng

EXISTS chỉ quan tâm có ít nhất một hàng khớp:

~~~sql
SELECT c.customer_id
FROM customers_lab AS c
WHERE EXISTS (
    SELECT 1
    FROM sales_orders_lab AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Nếu customer 3 có ba đơn hay ba trăm đơn, nó vẫn xuất hiện một lần trong outer result.

NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers_lab AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_orders_lab AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả 1 và 5.

Bộ test nên có:

- Không có hàng con.
- Một hàng con.
- Nhiều hàng con.
- Nhiều hàng con có cùng giá trị được so sánh.
- Giá trị NULL nếu schema cho phép.

Duplicate ở bảng con không làm nhân hàng cha trong EXISTS, nhưng có thể ảnh hưởng JOIN, COUNT và NOT IN.

## 15. Phân trang khi có hàng bằng nhau và duplicate

### 15.1. ORDER BY không đủ cột tạo thứ tự chưa xác định

~~~sql
SELECT order_id, created_at
FROM sales_orders_lab
ORDER BY created_at DESC;
~~~

Hai đơn 103 và 104 có cùng created_at. Database không cam kết thứ tự giữa chúng nếu không có tiêu chí phân biệt bổ sung.

Thêm tie-breaker:

~~~sql
SELECT order_id, created_at
FROM sales_orders_lab
ORDER BY created_at DESC, order_id ASC;
~~~

### 15.2. Phân trang có thể lặp hoặc bỏ hàng

Nếu hai request lấy trang kế tiếp dựa trên ORDER BY không duy nhất, những hàng có cùng khóa sort có thể đổi thứ tự giữa các lần chạy. Khi dùng OFFSET, dữ liệu được chèn/xóa giữa hai request còn có thể làm dịch chuyển vị trí hàng.

Kiểm thử:

- Trang đầu có đúng page size.
- Trang cuối có ít hàng hơn hoặc rỗng.
- Không có hàng nào bị lặp giữa các trang trong snapshot/điều kiện kiểm thử đã xác định.
- Không bỏ sót hàng khi dữ liệu không thay đổi.
- Các hàng bằng nhau ở sort key được phân biệt bằng tie-breaker.
- Quy tắc xử lý dữ liệu mới giữa các request được xác định.

### 15.3. Keyset pagination

Với sort created_at DESC, order_id ASC, cursor của trang trước có thể gồm cả created_at và order_id:

~~~sql
SELECT order_id, created_at, total_amount
FROM sales_orders_lab
WHERE (created_at, order_id) < ($1, $2)
ORDER BY created_at DESC, order_id ASC
LIMIT $3;
~~~

Lưu ý: biểu thức so sánh tuple ở trên chỉ là ví dụ minh họa và cần điều chỉnh dấu so sánh theo hướng của từng cột. Khi các hướng sort hỗn hợp, một điều kiện lexicographic tường minh thường cần dạng:

~~~sql
WHERE created_at < $1
   OR (created_at = $1 AND order_id > $2)
~~~

Cursor phải bao gồm đủ các cột tạo thứ tự duy nhất và phải xử lý NULL nhất quán với ORDER BY.

## 16. Kiểm thử dữ liệu trùng do JOIN

Một truy vấn có thể tạo ra số hàng lớn hơn dự kiến mà không có bản ghi nào bị duplicate trong bảng nguồn.

### 16.1. Xem số hàng trước và sau JOIN

~~~sql
SELECT COUNT(*) AS order_count
FROM sales_orders_lab;

SELECT COUNT(*) AS item_join_rows
FROM sales_orders_lab AS o
JOIN order_items_lab AS i
    ON i.order_id = o.order_id;
~~~

Bảng đơn có 5 hàng; JOIN với dòng hàng tạo 8 hàng vì mỗi đơn có số dòng chi tiết khác nhau.

### 16.2. Phát hiện quan hệ một-nhiều

~~~sql
SELECT order_id, COUNT(*) AS item_count
FROM order_items_lab
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY order_id;
~~~

Đơn 103 có 2 dòng; đơn 104 có 3 dòng. Đây không phải lỗi nếu một đơn có thể có nhiều sản phẩm/dòng hàng.

### 16.3. Khi cần một hàng trên mỗi đơn

Tổng hợp dòng hàng trước:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS calculated_total,
        COUNT(*) AS line_count
    FROM order_items_lab
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.total_amount,
    i.calculated_total,
    i.line_count
FROM sales_orders_lab AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id;
~~~

CTE item_totals có tối đa một hàng cho mỗi order_id vì đã GROUP BY. JOIN kết quả đó giúp giữ một hàng trên mỗi đơn.

### 16.4. Không dùng DISTINCT để che lỗi JOIN

Nếu tổng tiền bị nhân lên do JOIN hai bảng con, thêm DISTINCT vào SELECT có thể làm kết quả nhìn bớt trùng nhưng không sửa phép tính sai. Phải xác định cardinality của từng quan hệ và tổng hợp đúng trước khi JOIN.

## 17. Kiểm thử repository và tầng ứng dụng

SQL đúng không đảm bảo code đọc kết quả đúng. Cần kiểm thử cả đường đi từ repository đến đối tượng trả về.

### 17.1. Repository trả List

Một phương thức như findOrdersByCustomer thường nên trả danh sách:

~~~java
List<Order> findOrdersByCustomer(long customerId);
~~~

Hợp đồng của List cho phép:

- Danh sách rỗng khi không có hàng.
- Một phần tử.
- Nhiều phần tử.

Test nên assert kích thước và nội dung, không chỉ assert list != null.

### 17.2. Repository trả Optional

Một phương thức tìm theo khóa duy nhất có thể trả:

~~~java
Optional<Order> findById(long orderId);
~~~

Optional phù hợp khi kết quả có thể là 0 hoặc 1 hàng. Nó không phải cơ chế xử lý an toàn cho truy vấn có thể trả nhiều hàng. Nếu truy vấn không được đảm bảo unique mà code chỉ lấy hàng đầu, duplicate có thể bị che giấu.

### 17.3. Repository trả một đối tượng đơn

Nếu phương thức được định nghĩa là tìm duy nhất theo email:

~~~java
Order findUniqueByExternalCode(String code);
~~~

cần một UNIQUE constraint phù hợp ở database hoặc logic kiểm tra rõ ràng. Chỉ dùng LIMIT 1 không đảm bảo tính duy nhất.

### 17.4. Kiểm tra số hàng ảnh hưởng

JDBC:

~~~java
int affected = ps.executeUpdate();

if (affected == 0) {
    // Không có hàng khớp hoặc không có thay đổi theo ngữ nghĩa driver.
} else if (affected == 1) {
    // Một hàng.
} else {
    // Nhiều hàng: xác minh đây có phải kết quả dự kiến.
}
~~~

Số hàng được báo có thể phụ thuộc DBMS/driver và loại statement. Với UPDATE gán một cột bằng chính giá trị hiện tại, một số hệ thống có thể báo số hàng khớp, hệ khác có chi tiết riêng về hàng thực sự thay đổi. Hãy xác định hợp đồng cụ thể của driver/database.

## 18. Ma trận kiểm thử cardinality

Không phải mọi truy vấn đều cần tất cả trường hợp theo cùng cách. Hãy chọn ma trận theo cardinality có thể xảy ra và rủi ro của truy vấn.

| Trường hợp | Dữ liệu chuẩn bị | Điều cần xác minh |
|---|---|---|
| 0 hàng | Không có bản ghi khớp | Danh sách rỗng, COUNT = 0, không đọc hàng giả |
| 1 hàng | Một bản ghi khớp | Ánh xạ đúng, giá trị NULL được xử lý |
| N hàng | Nhiều bản ghi khớp | Đọc đủ, không mất hàng, thứ tự đúng |
| Hai hàng có cùng một giá trị | Cùng status/amount | Duplicate được giữ nếu không DISTINCT |
| Hai hàng trùng projection | Khác khóa nhưng cùng cột SELECT | Hiểu DISTINCT và bag semantics |
| Một cha, không có con | LEFT JOIN | Giữ hàng cha, COUNT(con.key) = 0 |
| Một cha, một con | Quan hệ 1:1 | Một hàng kết quả |
| Một cha, nhiều con | Quan hệ 1:N | Nhân hàng đúng dự kiến |
| Nhiều cha, nhiều con | Nhiều nhóm quan hệ | Không nhân sai aggregate |
| Dữ liệu NULL | Cột cho phép NULL | COUNT(col), SUM, NOT IN, sort |
| Khóa trùng | Vi phạm UNIQUE | Database từ chối hoặc UPSERT đúng |
| Nhiều hàng cùng sort key | Timestamp/amount bằng nhau | Tie-breaker và phân trang ổn định |

### 18.1. Chọn test theo hợp đồng truy vấn

- Truy vấn tìm theo PRIMARY KEY: 0 và 1 là trọng tâm; nhiều hàng phải bị ngăn bởi constraint.
- Truy vấn tìm theo email chưa unique: phải test 0, 1 và nhiều hàng cho tới khi quy tắc dữ liệu được xác định.
- Báo cáo GROUP BY: test tập nguồn rỗng, một nhóm, nhiều nhóm và nhóm có duplicate.
- JOIN 1:N: test không có con, một con và nhiều con.
- UPDATE theo khóa: test 0/1; UPDATE theo batch: test 0/1/N.
- Pagination: test 0, ít hơn page size, đúng page size, nhiều trang và tie rows.

## 19. Fixture: dữ liệu kiểm thử phải tái lập

Fixture là dữ liệu được chuẩn bị có chủ ý để một test chạy với trạng thái database xác định.

### 19.1. Tạo fixture nhỏ và dễ hiểu

Một fixture tốt:

- Có khóa ổn định và dễ đọc.
- Mỗi hàng phục vụ một tình huống cụ thể.
- Không phụ thuộc dữ liệu còn sót từ test trước.
- Có thể được nạp lại nhiều lần.
- Không dùng timestamp hiện tại nếu không cần.
- Không giả định thứ tự vật lý của bảng.

Bộ dữ liệu ở mục 2 là ví dụ: customer 1/5 không có đơn; customer 2/4 có một đơn; customer 3 có ba đơn; order 103/104 có nhiều giá trị giống nhau.

### 19.2. Cô lập test

Các cách phổ biến:

- Mỗi test chạy trong transaction và rollback nếu framework hỗ trợ.
- Dùng schema/database riêng cho test suite.
- Tạo và xóa fixture bằng migration/test setup.
- Dùng container database tạm thời cho integration test.

Không chạy test phá dữ liệu trên database dùng chung hoặc production.

### 19.3. Tránh test phụ thuộc thứ tự chạy

Một test không nên cần test khác chạy trước để tạo dữ liệu. Mỗi test hoặc nhóm test phải thiết lập trạng thái cần thiết của nó.

### 19.4. Không dựa vào thứ tự INSERT

Database không cam kết SELECT trả hàng theo thứ tự INSERT. Nếu assertion yêu cầu thứ tự, truy vấn phải có ORDER BY.

## 20. Assertion: kiểm tra số lượng và nội dung

### 20.1. Kiểm tra list rỗng

~~~java
assertNotNull(result);
assertTrue(result.isEmpty());
~~~

Nếu hợp đồng trả Optional, kiểm tra Optional.empty. Nếu API trả trang, kiểm tra content rỗng và metadata phù hợp.

### 20.2. Kiểm tra một hàng

~~~java
assertEquals(1, result.size());
assertEquals(101L, result.get(0).id());
assertEquals("PAID", result.get(0).status());
~~~

### 20.3. Kiểm tra nhiều hàng

~~~java
assertEquals(3, result.size());
assertEquals(
    Set.of(102L, 103L, 104L),
    result.stream()
        .map(Order::id)
        .collect(Collectors.toSet())
);
~~~

Nếu thứ tự là một phần hợp đồng:

~~~java
assertEquals(
    List.of(104L, 103L, 102L),
    result.stream().map(Order::id).toList()
);
~~~

Nếu thứ tự không thuộc hợp đồng, so sánh theo khóa hoặc tập phần tử thay vì ép test phụ thuộc thứ tự không được bảo đảm.

### 20.4. Kiểm tra duplicate

~~~java
assertEquals(
    List.of("NEW", "PAID", "PAID"),
    result.stream().map(Order::status).toList()
);
~~~

Assertion này xác minh duplicate PAID được giữ. Nếu test chỉ kiểm tra Set.of("NEW","PAID"), nó sẽ bỏ qua lỗi làm mất số lần xuất hiện.

### 20.5. Kiểm tra số hàng bị ảnh hưởng

~~~java
assertEquals(0, repository.updateStatus(-1L, "PAID"));
assertEquals(1, repository.updateStatus(101L, "PAID"));
assertEquals(3, repository.updateStatusForCustomer(3L, "REVIEW"));
~~~

Đây là ví dụ về ba cardinality. Test cần kiểm tra thêm dữ liệu sau UPDATE để đảm bảo số hàng và giá trị thay đổi đều đúng.

## 21. Property-based testing và invariant

Ngoài fixture cố định, có thể kiểm tra các thuộc tính phải đúng với nhiều bộ dữ liệu sinh tự động.

### 21.1. Đếm số hàng bằng số phần tử

Với một tập order_id không trùng khóa:

~~~sql
SELECT COUNT(*) FROM sales_orders_lab;
~~~

phải bằng số hàng fixture đã chèn.

### 21.2. Tổng theo nhóm bằng tổng toàn cục

Nếu mỗi đơn thuộc đúng một customer:

~~~sql
SELECT SUM(customer_total)
FROM (
    SELECT customer_id, SUM(total_amount) AS customer_total
    FROM sales_orders_lab
    GROUP BY customer_id
) AS grouped;
~~~

phải bằng SUM(total_amount) của bảng nguồn, khi cùng tập lọc và NULL semantics được giữ nhất quán.

### 21.3. JOIN và EXISTS không thay đổi tập khóa cha

Tập customer có ít nhất một đơn:

~~~sql
SELECT customer_id
FROM customers_lab c
WHERE EXISTS (
    SELECT 1
    FROM sales_orders_lab o
    WHERE o.customer_id = c.customer_id
);
~~~

phải tương đương với tập DISTINCT customer_id từ bảng đơn trong dữ liệu mẫu. JOIN có thể lặp customer_id, nhưng DISTINCT trên kết quả JOIN phải cho cùng tập khóa.

### 21.4. UNIQUE invariant

Sau mọi thao tác ghi hợp lệ, không tồn tại hai hàng cùng khóa duy nhất. Có thể kiểm tra bằng:

~~~sql
SELECT email, COUNT(*)
FROM customers_lab
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Kết quả phải rỗng nếu email là unique. Tốt hơn, để UNIQUE constraint đảm bảo invariant ngay cả khi có ghi đồng thời.

### 21.5. Tính lũy đẳng của thao tác

Nếu API có thao tác “đặt trạng thái thành PAID”, chạy hai lần có thể cho cùng trạng thái cuối. Nhưng nếu thao tác “tăng quantity thêm 1”, chạy hai lần không lũy đẳng.

Test retry cần xác định:

- Cùng request ID có được xử lý một lần không?
- Unique idempotency key có ngăn tạo duplicate không?
- UPSERT có ghi đè dữ liệu ngoài ý muốn không?
- Retry sau timeout có thể gây hai lần side effect không?

## 22. Kiểm thử cạnh tranh và trạng thái dữ liệu thay đổi

Một bộ test cardinality cũng nên xem xét dữ liệu có thể thay đổi giữa lúc kiểm tra và lúc ghi.

### 22.1. Race giữa kiểm tra tồn tại và INSERT

Mẫu không đủ an toàn:

~~~sql
SELECT 1
FROM customers_lab
WHERE email = 'new@example.test';

-- Nếu không thấy, ứng dụng mới INSERT.
~~~

Hai transaction có thể đồng thời không thấy email, rồi cả hai cùng INSERT. Nếu email phải unique, UNIQUE constraint mới là lớp bảo vệ cuối cùng.

### 22.2. UPDATE theo điều kiện không còn khớp

Một ứng dụng đọc trạng thái NEW, sau đó một transaction khác đổi thành PAID. Khi ứng dụng đầu tiên chạy UPDATE với điều kiện status = 'NEW', số hàng ảnh hưởng có thể là 0.

~~~sql
UPDATE sales_orders_lab
SET status = 'CANCELLED'
WHERE order_id = 101
  AND status = 'NEW';
~~~

Kết quả 0 hàng có thể là optimistic concurrency conflict. Không mặc định mọi UPDATE 0 hàng đều là lỗi hệ thống.

### 22.3. Isolation level ảnh hưởng kết quả đọc

Trong transaction, số hàng mà một truy vấn nhìn thấy phụ thuộc isolation level và thời điểm snapshot. Khi test concurrency:

- Xác định isolation level.
- Dùng hai connection riêng.
- Đồng bộ thời điểm đọc/ghi bằng barrier hoặc lock có kiểm soát.
- Xác minh trạng thái cuối và số hàng ảnh hưởng.
- Không dựa vào sleep cố định để điều phối test nếu có cơ chế đồng bộ tốt hơn.

### 22.4. Duplicate khi xử lý retry

Nếu một worker gửi cùng event hai lần, database có thể có hai hàng giống nhau nếu không có unique event key. Tạo unique constraint theo event_id hoặc idempotency key nếu nghiệp vụ yêu cầu chỉ ghi một lần.

## 23. Dùng EXPLAIN khi gỡ lỗi số hàng bất ngờ

EXPLAIN giúp xem cách database dự định thực thi truy vấn; EXPLAIN ANALYZE thực thi truy vấn và báo số hàng thực tế theo node.

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    o.order_id
FROM customers_lab AS c
JOIN sales_orders_lab AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 3;
~~~

Khi điều tra số hàng:

- So sánh estimated rows với actual rows.
- Quan sát node JOIN có làm tăng số hàng đúng như cardinality quan hệ không.
- Xem filter có loại hàng nhiều hơn dự kiến không.
- Kiểm tra điều kiện JOIN có thiếu khóa hay không.
- Xem một quan hệ phía phải có duplicate key ngoài dự kiến không.

EXPLAIN ANALYZE thực thi câu lệnh. Với UPDATE/DELETE/INSERT, nó có thể thay đổi dữ liệu; hãy dùng transaction phù hợp và rollback trong môi trường kiểm thử.

## 24. Quy trình gỡ lỗi khi số hàng sai

Khi API trả 0, 1 hoặc N hàng khác kỳ vọng, kiểm tra theo thứ tự:

1. **Đếm nguồn:** bảng cha và bảng con thực tế có bao nhiêu hàng phù hợp?
2. **Kiểm tra predicate:** từng điều kiện WHERE có loại hàng ngoài dự kiến không?
3. **Kiểm tra NULL:** phép so sánh có thể trả UNKNOWN không?
4. **Kiểm tra JOIN key:** điều kiện JOIN có đủ cột khóa không?
5. **Kiểm tra cardinality:** quan hệ là 1:1, 1:N hay N:N?
6. **Kiểm tra duplicate:** duplicate có trong bảng nguồn hay phát sinh do JOIN?
7. **Kiểm tra aggregate:** COUNT(*) hay COUNT(column), DISTINCT có đúng ý nghĩa không?
8. **Kiểm tra ORDER BY:** có thứ tự ổn định khi phân trang không?
9. **Kiểm tra transaction:** snapshot hoặc ghi đồng thời có làm dữ liệu thay đổi không?
10. **Kiểm tra tầng ứng dụng:** ResultSet/list/Optional có bị đọc hoặc chuyển đổi sai không?

Các truy vấn chẩn đoán hữu ích:

~~~sql
-- Tổng số hàng nguồn.
SELECT COUNT(*) FROM sales_orders_lab;

-- Đếm theo khóa nhóm.
SELECT customer_id, COUNT(*)
FROM sales_orders_lab
GROUP BY customer_id
ORDER BY customer_id;

-- Tìm khóa có nhiều hàng.
SELECT customer_id, COUNT(*)
FROM sales_orders_lab
GROUP BY customer_id
HAVING COUNT(*) > 1;

-- Tìm hàng có khóa ngoài bị lặp ở bảng con.
SELECT order_id, COUNT(*)
FROM order_items_lab
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Những truy vấn này giúp phân biệt duplicate dữ liệu với duplicate do phép JOIN.

## 25. Các lỗi thường gặp

### Lỗi 1 — Chỉ test khi bảng có dữ liệu

Truy vấn có thể đúng với nhiều hàng nhưng code lỗi khi kết quả rỗng. Luôn có test no-result nếu nghiệp vụ cho phép.

### Lỗi 2 — Giả định SELECT luôn trả một hàng

Một điều kiện tìm kiếm có thể trả 0 hoặc N hàng. Dùng List, Optional hoặc API phù hợp với cardinality thật.

### Lỗi 3 — Dùng Optional để che truy vấn có nhiều hàng

Optional chỉ biểu diễn 0 hoặc 1 giá trị. Nếu query có thể trả nhiều hàng, cần List hoặc constraint bảo đảm unique.

### Lỗi 4 — Dùng LIMIT 1 để che duplicate

LIMIT 1 không sửa dữ liệu trùng và có thể chọn một hàng bất kỳ nếu thiếu ORDER BY. Xác định quy tắc chọn hàng hoặc enforce UNIQUE.

### Lỗi 5 — Nghĩ SELECT tự loại hàng trùng

SQL giữ duplicate theo bag semantics. Chỉ DISTINCT hoặc phép toán cụ thể mới thay đổi số lần xuất hiện.

### Lỗi 6 — Dùng DISTINCT để sửa JOIN sai

DISTINCT có thể che triệu chứng nhưng không sửa tích nhân do thiếu điều kiện JOIN hoặc aggregate sai.

### Lỗi 7 — COUNT(*) sau LEFT JOIN để đếm hàng con

Hàng placeholder vẫn được COUNT(*). Dùng COUNT khóa phía con không NULL.

### Lỗi 8 — Nhầm COUNT(column) với COUNT(*)

COUNT(column) bỏ qua NULL; COUNT(*) đếm hàng. Cả hai khác nhau khi cột có NULL hoặc outer join tạo placeholder.

### Lỗi 9 — Nghĩ SUM trên tập rỗng là 0

SUM thường trả NULL trên tập không có giá trị. Dùng COALESCE khi nghiệp vụ muốn 0.

### Lỗi 10 — Nghĩ GROUP BY tạo nhóm cho khóa không có hàng

GROUP BY chỉ tạo nhóm từ dữ liệu đầu vào. Muốn mọi khách hàng xuất hiện, bắt đầu từ bảng khách hàng rồi LEFT JOIN.

### Lỗi 11 — Scalar subquery trả nhiều hàng

Trong PostgreSQL, scalar subquery nhiều hàng gây lỗi. Dùng aggregate, quy tắc chọn hàng rõ ràng hoặc constraint unique.

### Lỗi 12 — NOT IN gặp NULL

NULL trong tập con có thể làm NOT IN trả UNKNOWN. NOT EXISTS thường diễn đạt kiểm tra không tồn tại rõ hơn.

### Lỗi 13 — JOIN hai bảng con làm nhân tổng

Hai quan hệ 1:N có thể tạo tích số hàng. Tổng hợp từng bảng con trước khi JOIN nếu cần một hàng trên mỗi cha.

### Lỗi 14 — Coi hai hàng có cùng status là dữ liệu duplicate sai

Status thường không unique. Xác định khóa nghiệp vụ trước khi xóa hoặc thêm constraint.

### Lỗi 15 — Không kiểm thử UNIQUE với dữ liệu đồng thời

Kiểm tra tồn tại ở ứng dụng không ngăn hai transaction cùng INSERT. Dùng constraint unique làm bảo đảm ở database.

### Lỗi 16 — Chỉ test UNIQUE với giá trị không NULL

NULL có quy tắc riêng và có khác biệt theo DBMS/phiên bản. Test đúng semantics và kết hợp NOT NULL khi cần.

### Lỗi 17 — UPDATE 0 hàng bị coi là luôn thành công

Ứng dụng cần phân biệt not found, conflict, no-op và cập nhật theo batch không khớp.

### Lỗi 18 — UPDATE nhiều hàng nhưng chỉ đọc một hàng RETURNING

Database có thể đã cập nhật N hàng. Ứng dụng phải xử lý toàn bộ kết quả hoặc dùng row count theo hợp đồng.

### Lỗi 19 — Phân trang thiếu tie-breaker

Các hàng có cùng sort key có thể đổi thứ tự. Thêm khóa duy nhất vào ORDER BY.

### Lỗi 20 — Test phụ thuộc thứ tự vật lý

Không có ORDER BY thì không có bảo đảm thứ tự kết quả. Assertion phải phản ánh đúng hợp đồng.

### Lỗi 21 — Test dùng dữ liệu còn sót

Test trước có thể làm test sau thay đổi kết quả. Dùng fixture cô lập, transaction rollback hoặc database riêng.

### Lỗi 22 — Chỉ kiểm tra kích thước mà không kiểm tra nội dung

Danh sách có ba hàng vẫn có thể chứa sai ba ID. Assert khóa, giá trị và thứ tự khi cần.

### Lỗi 23 — Chuyển List thành Set rồi mất duplicate

Set loại phần tử trùng. Nếu số lần xuất hiện quan trọng, so sánh List hoặc multiset.

### Lỗi 24 — Không phân biệt 0 hàng với một hàng NULL

ResultSet có một hàng với cột NULL khác ResultSet rỗng. Kiểm tra next() và wasNull() đúng chỗ.

### Lỗi 25 — Dùng EXPLAIN ANALYZE DML trên dữ liệu thật

ANALYZE thực thi câu lệnh. DML có thể thay đổi dữ liệu; dùng transaction/rollback và môi trường test.

## 26. Bài tập thực hành có đáp án

Các bài dùng bộ dữ liệu ở mục 2, trừ khi đề bài nói khác.

### Bài 1 — Khách hàng không có đơn

Viết truy vấn tìm đơn của customer 1.

~~~sql
SELECT *
FROM sales_orders_lab
WHERE customer_id = 1;
~~~

**Đáp án:** 0 hàng.

### Bài 2 — Khách hàng có một đơn

Tìm đơn của customer 2.

**Đáp án:** một hàng, order_id 101.

### Bài 3 — Khách hàng có nhiều đơn

Tìm đơn của customer 3, sắp theo order_id.

**Đáp án:** ba hàng, order_id 102, 103, 104.

### Bài 4 — Duplicate trong projection

~~~sql
SELECT status
FROM sales_orders_lab
WHERE customer_id = 3
ORDER BY order_id;
~~~

**Đáp án:** NEW, PAID, PAID. Hai PAID phải được giữ vì không có DISTINCT.

### Bài 5 — Loại giá trị trùng

Thêm DISTINCT vào truy vấn bài 4. Có bao nhiêu hàng?

**Đáp án:** hai hàng: NEW và PAID.

### Bài 6 — Đếm tổng số đơn

~~~sql
SELECT COUNT(*)
FROM sales_orders_lab
WHERE customer_id = 1;
~~~

**Đáp án:** một hàng kết quả chứa 0.

### Bài 7 — SUM trên tập rỗng

Chạy SUM(total_amount) cho customer 1. Kết quả?

**Đáp án:** NULL trong PostgreSQL; dùng COALESCE nếu muốn 0.

### Bài 8 — LEFT JOIN

LEFT JOIN khách hàng với đơn hàng. Customer 1 có bao nhiêu hàng kết quả?

**Đáp án:** một hàng placeholder với cột đơn hàng NULL.

### Bài 9 — COUNT sau LEFT JOIN

Với customer 1, so COUNT(*) và COUNT(o.order_id).

**Đáp án:** COUNT(*) = 1; COUNT(o.order_id) = 0.

### Bài 10 — EXISTS

Tìm khách hàng có ít nhất một đơn bằng EXISTS.

**Đáp án:** customer 2, 3, 4. Mỗi khách hàng xuất hiện một lần dù customer 3 có ba đơn.

### Bài 11 — NOT EXISTS

Tìm khách hàng không có đơn.

**Đáp án:** customer 1 và 5.

### Bài 12 — Scalar subquery rỗng

Scalar subquery trả 0 hàng có kết quả gì trong PostgreSQL?

**Đáp án:** NULL.

### Bài 13 — Scalar subquery nhiều hàng

Scalar subquery lấy total_amount của customer 3 có kết quả gì?

**Đáp án:** lỗi vì trả nhiều hơn một hàng.

### Bài 14 — IN và duplicate

Subquery customer_id của các đơn PAID có duplicate. IN có làm customer 3 xuất hiện ba lần không?

**Đáp án:** Không. Predicate IN không nhân hàng outer; kết quả outer có mỗi khách hàng một lần nếu không có JOIN khác.

### Bài 15 — COUNT DISTINCT

Đếm số trạng thái phân biệt trong đơn của customer 3.

**Đáp án:** 2.

### Bài 16 — SUM và SUM DISTINCT

Với customer 3 có amount 80, 200, 200, hai tổng là bao nhiêu?

**Đáp án:** SUM = 480; SUM(DISTINCT) = 280.

### Bài 17 — JOIN dòng hàng

Có bao nhiêu hàng khi JOIN tất cả đơn với order_items_lab?

**Đáp án:** 8 hàng vì có 8 dòng chi tiết.

### Bài 18 — Phát hiện đơn nhiều dòng

Dùng GROUP BY order_id HAVING COUNT(*) > 1.

**Đáp án:** order 103 có 2 dòng; order 104 có 3 dòng.

### Bài 19 — UPDATE không khớp

UPDATE order_id = -1 ảnh hưởng bao nhiêu hàng?

**Đáp án:** 0.

### Bài 20 — UPDATE theo customer 3

UPDATE status cho customer 3 ảnh hưởng bao nhiêu hàng?

**Đáp án:** 3 hàng.

### Bài 21 — UNIQUE email

Chèn email an@example.test lần thứ hai sau khi tạo UNIQUE constraint. Kết quả?

**Đáp án:** database từ chối do vi phạm unique.

### Bài 22 — UNIQUE nhiều cột

Hai hàng có tenant khác nhau nhưng cùng external_code có hợp lệ với UNIQUE(tenant_id, external_code) không?

**Đáp án:** Có. Chỉ cặp giá trị phải duy nhất.

### Bài 23 — ROW_NUMBER

Vì sao nên thêm order_id vào ORDER BY của ROW_NUMBER khi created_at có thể bằng nhau?

**Đáp án:** để thứ tự đánh số ổn định và xác định cho từng hàng.

### Bài 24 — RANK và DENSE_RANK

Hai đơn cùng timestamp đứng đầu. Hạng tiếp theo là gì?

**Đáp án:** RANK có thể nhảy đến 3; DENSE_RANK là 2.

### Bài 25 — Phân trang

Một bảng có nhiều hàng cùng created_at. Chỉ ORDER BY created_at có đủ để phân trang ổn định không?

**Đáp án:** Không. Thêm khóa duy nhất như order_id làm tie-breaker.

### Bài 26 — DISTINCT có sửa dữ liệu không?

SELECT DISTINCT status có xóa duplicate trong bảng không?

**Đáp án:** Không. Nó chỉ loại duplicate trong tập kết quả.

### Bài 27 — COUNT(*) và COUNT(column)

Một outer join tạo một hàng placeholder có order_id NULL. Hai COUNT khác nhau thế nào?

**Đáp án:** COUNT(*) đếm hàng placeholder; COUNT(order_id) bỏ qua NULL.

### Bài 28 — Dữ liệu trùng do JOIN

JOIN hai bảng con 2 hàng và 3 hàng theo cùng order_id có thể tạo bao nhiêu cặp?

**Đáp án:** 2 × 3 = 6 hàng.

### Bài 29 — Tìm duplicate khóa

Viết truy vấn phát hiện email xuất hiện nhiều lần.

~~~sql
SELECT email, COUNT(*)
FROM customers_lab
GROUP BY email
HAVING COUNT(*) > 1;
~~~

**Đáp án:** kết quả rỗng nếu constraint UNIQUE đang được thực thi.

### Bài 30 — Fixture

Nêu các tình huống tối thiểu cho truy vấn tìm đơn theo customer.

**Đáp án:** customer không có đơn, một đơn, nhiều đơn và nhiều đơn có cùng status/amount nếu những giá trị trùng được phép.

## 27. Bảng ghi nhớ nhanh

| Trường hợp | Kết quả/điều cần nhớ |
|---|---|
| SELECT không khớp hàng | 0 hàng |
| SELECT khớp một hàng | 1 hàng |
| SELECT khớp N hàng | N hàng; phải đọc hết |
| Nhiều hàng cùng giá trị | SQL giữ duplicate nếu không DISTINCT |
| SELECT DISTINCT | Loại duplicate theo toàn bộ projection |
| COUNT(*) trên tập rỗng không GROUP BY | Một hàng có giá trị 0 |
| SUM/AVG/MIN/MAX trên tập rỗng | Thường NULL |
| GROUP BY trên nguồn rỗng | Không có nhóm |
| LEFT JOIN không có hàng con | Một hàng placeholder |
| COUNT(*) sau LEFT JOIN | Đếm placeholder |
| COUNT(child.key) | Đếm hàng con có khóa không NULL |
| Scalar subquery 0 hàng | NULL |
| Scalar subquery 1 hàng | Giá trị đó |
| Scalar subquery nhiều hàng | Lỗi trong PostgreSQL |
| EXISTS | Chỉ kiểm tra có hàng phù hợp |
| JOIN 1:N | Hàng cha có thể lặp theo số hàng con |
| UPDATE/DELETE | Kiểm thử 0, 1 và N hàng ảnh hưởng |
| UNIQUE | Database chặn duplicate theo khóa được khai báo |
| ORDER BY không duy nhất | Thứ tự tie không được bảo đảm |
| Fixture | Tái lập, cô lập, không phụ thuộc thứ tự chạy |

## Kết luận

**Bao phủ bảng rỗng, một hàng, nhiều hàng và bản sao giúp phát hiện những giả định sai về cardinality và tính duy nhất.** Một truy vấn có thể trả tập rỗng hợp lệ, đúng một hàng, nhiều hàng hoặc nhiều dòng giống nhau ở một số cột. Ứng dụng và database phải xử lý từng trường hợp theo hợp đồng nghiệp vụ.

Khi kiểm thử:

- **Kiểm tra cả 0, 1 và N hàng** cho SELECT, DML và API repository khi nghiệp vụ cho phép.
- **Phân biệt tập kết quả rỗng với một hàng có giá trị NULL**; kiểm tra đúng COUNT, SUM và NULL semantics.
- **Hiểu bag semantics của SQL**: duplicate được giữ nếu không dùng DISTINCT. Chỉ áp UNIQUE khi khóa nghiệp vụ thực sự phải duy nhất.
- **Kiểm tra cardinality của JOIN**: quan hệ 1:N làm lặp hàng cha; JOIN nhiều bảng con có thể nhân số hàng và làm sai aggregate.
- **Kiểm thử scalar subquery, EXISTS, GROUP BY và window function** với dữ liệu rỗng, một hàng, nhiều hàng và tie values.
- **Kiểm tra số hàng ảnh hưởng của UPDATE/DELETE**, constraint UNIQUE, UPSERT và retry.
- **Dùng fixture cô lập và assertion đúng ý nghĩa**: số hàng, khóa, giá trị, số lần xuất hiện và thứ tự khi cần.

Khi biết rõ một truy vấn được phép trả bao nhiêu hàng, những hàng nào có thể lặp và cách xử lý khi không có kết quả, việc kiểm thử SQL sẽ đáng tin cậy hơn. Đây cũng là nền tảng để gỡ lỗi các trường hợp báo cáo sai tổng, JOIN nhân hàng, phân trang bỏ sót bản ghi và cập nhật không tác động số hàng như dự kiến.
