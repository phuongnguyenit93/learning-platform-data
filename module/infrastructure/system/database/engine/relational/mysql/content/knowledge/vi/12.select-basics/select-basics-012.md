# Kiểm chứng truy vấn bằng dữ liệu tối thiểu và trường hợp biên

Một câu `SELECT` chạy không báo lỗi chưa chứng minh truy vấn trả về kết quả đúng. Điều kiện `WHERE` có thể bỏ sót hàng, phép `JOIN` có thể nhân bản dữ liệu, `NULL` có thể làm điều kiện lọc cho kết quả bất ngờ, còn `ORDER BY` thiếu cột phân xử có thể khiến thứ tự thay đổi giữa các lần chạy. Muốn tin cậy truy vấn, cần kiểm tra nó bằng một tập dữ liệu nhỏ nhưng được thiết kế để làm lộ những lỗi có thể xảy ra.

Kiểm chứng truy vấn bằng dữ liệu tối thiểu là cách tạo một fixture nhỏ, xác định trước kết quả mong đợi rồi đối chiếu kết quả thực tế. Mỗi hàng trong fixture nên đại diện cho một tình huống quan trọng: dữ liệu bình thường, giá trị biên, `NULL`, giá trị 0, hàng trùng về nội dung, hàng không có quan hệ, hoặc thời điểm đúng tại ranh giới. Một ví dụ nhỏ, có chủ đích thường giúp tìm lỗi nhanh hơn nhiều so với việc chạy truy vấn trên một database lớn mà không biết kết quả đúng phải là gì.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn thực hành thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và tối ưu truy vấn. Mục tiêu là kiểm tra tính đúng đắn của `SELECT` trước, sau đó mới đánh giá kế hoạch và hiệu năng trên dữ liệu có quy mô phù hợp.

Sau bài học, bạn có thể:

- Thiết kế fixture nhỏ để kiểm tra một truy vấn có chủ đích.
- Xác định kết quả mong đợi trước khi chạy SQL.
- Kiểm tra các trường hợp rỗng, một hàng, nhiều hàng, trùng lặp, `NULL` và giá trị 0.
- Phát hiện lỗi trong `JOIN`, `WHERE`, `GROUP BY`, aggregate và điều kiện thời gian.
- Bảo đảm kết quả sắp xếp và phân trang có thứ tự xác định.
- So sánh kết quả thực tế với kết quả mong đợi bằng SQL hoặc test ở tầng ứng dụng.
- Phân biệt kiểm chứng tính đúng đắn với kiểm tra hiệu năng bằng `EXPLAIN`.

## 1. Quy trình kiểm chứng một truy vấn

Trước khi viết fixture, hãy diễn đạt truy vấn thành một câu hỏi nghiệp vụ cụ thể. Ví dụ: “Với mỗi khách hàng, tổng số đơn đã thanh toán và tổng tiền thanh toán là bao nhiêu, kể cả khách hàng chưa có đơn?” Câu hỏi này đã chỉ ra các trường hợp cần kiểm tra: nhiều đơn, đơn không thuộc trạng thái cần lọc, số tiền `NULL`, tổng tiền bằng 0 và khách hàng không có đơn.

Một quy trình thực hành gồm các bước:

1. **Xác định hợp đồng kết quả:** truy vấn trả cột nào, kiểu gì, một hàng hay nhiều hàng, có cần giữ hàng không có quan hệ không?
2. **Liệt kê tình huống:** đường đi bình thường, biên nhỏ/lớn, `NULL`, tập rỗng, trùng lặp, giá trị bằng nhau và dữ liệu không hợp lệ.
3. **Tạo fixture tối thiểu:** chỉ thêm những hàng cần thiết để phân biệt các tình huống.
4. **Viết expected result trước:** ghi chính xác các hàng và giá trị phải xuất hiện, bao gồm cả `NULL` và thứ tự nếu thứ tự là một phần hợp đồng.
5. **Chạy truy vấn và đối chiếu:** không chỉ nhìn số lượng hàng; so sánh từng giá trị quan trọng.
6. **Thử biến thể gây lỗi:** đổi `LEFT JOIN` thành `INNER JOIN`, bỏ điều kiện, thay `IS NULL` bằng `= NULL`, bỏ cột phân xử trong `ORDER BY` để xem test có phát hiện sai lệch không.
7. **Kiểm tra kế hoạch riêng:** sau khi kết quả đúng, dùng `EXPLAIN` để đánh giá đường truy cập và index.

Fixture tốt không cần mô phỏng toàn bộ production. Nó cần nhỏ nhất có thể nhưng vẫn phân biệt được hành vi đúng với hành vi sai.

## 2. Tạo fixture tối thiểu cho bài thực hành

Ví dụ xuyên suốt dùng hai bảng: khách hàng và đơn hàng. Ta cố ý đưa vào dữ liệu có giá trị trùng nhau, số tiền `NULL`, số tiền bằng 0, trạng thái không cần tính và một khách hàng chưa có đơn.

Chạy toàn bộ phần này trong cùng một session MySQL vì bảng tạm chỉ tồn tại trong connection đã tạo chúng.

```sql
DROP TEMPORARY TABLE IF EXISTS orders;
DROP TEMPORARY TABLE IF EXISTS customers;

CREATE TEMPORARY TABLE customers (
    customer_id INT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2) NULL,
    placed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_status_date (customer_id, status, placed_at)
) ENGINE = InnoDB;

INSERT INTO customers (customer_id, customer_name) VALUES
(1, 'An'),
(2, 'Bình'),
(3, 'Chi'),
(4, 'Dũng');

INSERT INTO orders (order_id, customer_id, status, amount, placed_at) VALUES
(101, 1, 'PAID',    100.00, '2026-11-19 00:00:00.000000'),
(102, 1, 'PENDING',  20.00, '2026-11-19 12:00:00.000000'),
(103, 1, 'PAID',      NULL, '2026-11-19 23:59:59.999999'),
(104, 2, 'PAID',    150.00, '2026-11-20 00:00:00.000000'),
(105, 2, 'PAID',    150.00, '2026-11-20 08:30:00.000000'),
(106, 3, 'PAID',      0.00, '2026-11-19 12:00:00.000000');
```

Fixture có các trường hợp chủ đích:

| Hàng | Tình huống được kiểm tra |
| --- | --- |
| Khách hàng 1 | Có nhiều đơn, gồm một đơn `PENDING`, một số tiền bình thường và một số tiền `NULL` |
| Khách hàng 2 | Có hai đơn đã thanh toán với cùng số tiền để kiểm tra dữ liệu trùng và thứ tự hòa |
| Khách hàng 3 | Có một đơn đã thanh toán với số tiền bằng 0 |
| Khách hàng 4 | Không có đơn hàng để kiểm tra `LEFT JOIN` |
| Đơn 101 | Đúng tại đầu ngày 19/11/2026 |
| Đơn 103 | Đúng tại microsecond cuối cùng của ngày 19/11/2026 |
| Đơn 104 | Đúng tại đầu ngày kế tiếp, phải nằm ngoài khoảng ngày 19/11 |

Đây là fixture kiểm thử, không phải schema production. Không khai báo foreign key vì ví dụ cần tập trung vào cách `SELECT` xử lý các hàng và quan hệ; hai bảng tạm cũng được tự xóa khi session kết thúc.

## 3. Viết expected result trước khi chạy truy vấn

Giả sử yêu cầu là: “Liệt kê mọi khách hàng, số đơn đã thanh toán, số đơn có số tiền được cung cấp và tổng số tiền đã thanh toán.”

Expected result:

| customer_id | customer_name | paid_order_count | amount_count | paid_total |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 2 | 1 | 100.00 |
| 2 | Bình | 2 | 2 | 300.00 |
| 3 | Chi | 1 | 1 | 0.00 |
| 4 | Dũng | 0 | 0 | `NULL` |

Giải thích:

- Khách hàng 1 có hai đơn `PAID`, nhưng một đơn có `amount = NULL`. `COUNT(order_id)` là 2, `COUNT(amount)` là 1 và `SUM(amount)` là 100.00.
- Khách hàng 2 có hai đơn cùng số tiền 150.00; cả hai đều được tính, tổng là 300.00.
- Khách hàng 3 có một đơn trị giá 0.00. Tổng bằng 0, khác với trường hợp không có giá trị để cộng.
- Khách hàng 4 không có đơn `PAID`. `LEFT JOIN` vẫn giữ khách hàng, số đơn bằng 0 và `SUM()` trả `NULL` vì không có giá trị đầu vào.

Việc viết bảng mong đợi trước giúp phát hiện sớm câu hỏi mơ hồ. Ví dụ, “tổng tiền” có bao gồm đơn `PENDING` không? `NULL` có nghĩa là chưa biết số tiền hay được coi như 0? Các quyết định này phải đến từ nghiệp vụ, không được tự suy ra từ kết quả SQL.

## 4. Kiểm tra JOIN và điều kiện lọc

### 4.1. Đặt điều kiện của bảng bên phải trong ON khi cần giữ hàng không có quan hệ

Truy vấn đúng cho yêu cầu ở phần 3:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COUNT(o.amount) AS amount_count,
    SUM(o.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Điều kiện `o.status = 'PAID'` nằm trong `ON`, vì yêu cầu là giữ tất cả khách hàng rồi ghép các đơn đã thanh toán nếu có. Khi không tìm thấy đơn phù hợp, các cột từ `orders` nhận `NULL`, nhưng hàng khách hàng vẫn xuất hiện.

Truy vấn dễ mắc lỗi:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Điều kiện trong `WHERE` loại các hàng mà `o.status` là `NULL`, khiến khách hàng 4 biến mất. Kết quả gần giống `INNER JOIN` đối với điều kiện này. Fixture có khách hàng không có đơn giúp test bắt được lỗi đó.

### 4.2. COUNT(*) khác COUNT(cột bên phải)

Với `LEFT JOIN`, khách hàng không có đơn vẫn tạo ra một hàng kết quả với các cột `orders` là `NULL`:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_row_count,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Đối với khách hàng 4, `COUNT(*)` là 1 vì hàng bên trái vẫn tồn tại; `COUNT(o.order_id)` là 0 vì giá trị `order_id` của hàng ghép là `NULL`. Khi đếm bản ghi ở bảng con sau `LEFT JOIN`, thường phải đếm cột khóa không nullable của bảng con.

### 4.3. Dùng EXISTS khi chỉ cần kiểm tra có hàng liên quan

Nếu yêu cầu là “liệt kê khách hàng có ít nhất một đơn đã thanh toán”, không cần join tất cả đơn rồi loại trùng:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Expected result gồm khách hàng 1, 2 và 3. Khách hàng 4 không xuất hiện. `EXISTS` diễn đạt đúng ý nghĩa kiểm tra sự tồn tại và tránh nhân bản một khách hàng khi có nhiều đơn phù hợp.

## 5. Kiểm tra NULL, 0, chuỗi rỗng và tập rỗng

### 5.1. NULL không phải 0

SQL dùng logic ba giá trị: điều kiện có thể là `TRUE`, `FALSE` hoặc `UNKNOWN`. So sánh bằng `NULL` với toán tử `=` không cho kết quả `TRUE`.

```sql
-- Không tìm thấy hàng amount NULL
SELECT order_id
FROM orders
WHERE amount = NULL;

-- Tìm đúng hàng có amount NULL
SELECT order_id
FROM orders
WHERE amount IS NULL;

-- Toán tử so sánh NULL-safe riêng của MySQL
SELECT order_id
FROM orders
WHERE amount <=> NULL;
```

Hai truy vấn sau trả đơn 103. `<=>` là toán tử so sánh an toàn với `NULL` của MySQL; trong SQL portable, dùng `IS NULL` để kiểm tra giá trị null.

Điều kiện `amount <> 100.00` cũng không chọn hàng có `amount IS NULL`, vì kết quả so sánh là `UNKNOWN`. Nếu nghiệp vụ muốn bao gồm cả hàng không có số tiền, phải viết rõ:

```sql
WHERE amount <> 100.00 OR amount IS NULL
```

### 5.2. NOT IN có thể bị ảnh hưởng bởi NULL

Tạo danh sách loại trừ có một giá trị `NULL`:

```sql
DROP TEMPORARY TABLE IF EXISTS excluded_customers;

CREATE TEMPORARY TABLE excluded_customers (
    customer_id INT UNSIGNED NULL
) ENGINE = InnoDB;

INSERT INTO excluded_customers (customer_id) VALUES (1), (NULL);
```

Truy vấn sau không trả về các khách hàng như người viết thường kỳ vọng:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM excluded_customers AS e
);
```

Do tập con có `NULL`, phép so sánh `NOT IN` có thể trở thành `UNKNOWN` cho các giá trị không khớp, nên không hàng nào vượt qua `WHERE`. Với quan hệ loại trừ, `NOT EXISTS` thường an toàn hơn:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM excluded_customers AS e
    WHERE e.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Expected result: 2, 3 và 4. Hàng `NULL` trong bảng loại trừ không khớp khóa khách hàng nào và không làm hỏng phép kiểm tra tồn tại.

### 5.3. Chuỗi rỗng và chuỗi chỉ có khoảng trắng

Chuỗi rỗng `''`, chuỗi chứa khoảng trắng và `NULL` là ba giá trị khác nhau:

```sql
SELECT
    '' IS NULL AS empty_is_null,
    '   ' IS NULL AS spaces_are_null,
    NULL IS NULL AS null_is_null,
    NULLIF('', '') IS NULL AS empty_after_nullif,
    NULLIF(TRIM('   '), '') IS NULL AS spaces_after_trim;
```

Nếu nghiệp vụ coi chuỗi rỗng hoặc chỉ có khoảng trắng là không có giá trị, hãy chuẩn hóa rõ ràng bằng `TRIM()` và `NULLIF()` hoặc kiểm tra ở tầng ứng dụng. Đừng mặc định MySQL tự đổi chuỗi rỗng thành `NULL`.

### 5.4. Không có hàng khác với một hàng tổng hợp có giá trị 0

```sql
-- Không có hàng chi tiết
SELECT order_id, amount
FROM orders
WHERE customer_id = 999;

-- Aggregate không GROUP BY vẫn trả một hàng
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS amount_sum
FROM orders
WHERE customer_id = 999;
```

Truy vấn đầu trả result set rỗng. Truy vấn thứ hai trả một hàng với `row_count = 0` và `amount_sum = NULL`. Nếu dùng `COALESCE(SUM(amount), 0)`, tổng sẽ hiển thị 0, nhưng đó là quyết định ngữ nghĩa của báo cáo. Cần phân biệt “không có giao dịch” với “có giao dịch nhưng tổng bằng 0” nếu nghiệp vụ yêu cầu.

## 6. Kiểm tra dữ liệu trùng và phép JOIN nhân bản hàng

Hai đơn 104 và 105 có cùng `amount = 150.00`, nhưng là hai đơn riêng biệt vì `order_id` khác nhau. Truy vấn tổng phải tính cả hai:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM orders
WHERE customer_id = 2
  AND status = 'PAID'
GROUP BY customer_id;
```

Expected result: `order_count = 2`, `total_amount = 300.00`. Nếu dùng `SUM(DISTINCT amount)`, kết quả sẽ là 150.00 và sai với yêu cầu tổng tiền của tất cả đơn. `DISTINCT` loại giá trị trùng, không phải loại bản ghi trùng khóa.

Khi join nhiều bảng con một-nhiều, một hàng cha có thể bị nhân lên theo tích số hàng ở các bảng con. Ví dụ một đơn có 2 dòng hàng và 3 lần thanh toán thì join trực tiếp cả hai bảng có thể tạo 6 hàng. Khi đó `COUNT(order_id)` hoặc `SUM(line_total)` có thể bị nhân sai. Cách kiểm tra:

- Tạo fixture có 2 hàng ở bảng con thứ nhất và 3 hàng ở bảng con thứ hai.
- Đếm số hàng sau từng bước join.
- So sánh tổng trước và sau khi thêm join.
- Cân nhắc tổng hợp từng bảng con về một hàng cho mỗi khóa cha trước khi join.

Ví dụ hình thức tổng hợp trước:

```sql
SELECT
    o.order_id,
    item_totals.item_total,
    payment_totals.payment_total
FROM orders AS o
LEFT JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
) AS item_totals
    ON item_totals.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, SUM(amount) AS payment_total
    FROM payments
    GROUP BY order_id
) AS payment_totals
    ON payment_totals.order_id = o.order_id;
```

Đây là mẫu minh họa cho schema có `order_items` và `payments`; các bảng này không nằm trong fixture ở phần 2. Mỗi derived table chỉ còn tối đa một hàng cho mỗi `order_id`, nên tránh nhân bản do hai quan hệ một-nhiều.

## 7. Kiểm tra điều kiện biên và toán tử

### 7.1. So sánh biên số học

Với điều kiện khoảng, xác định rõ hai đầu có được bao gồm không. `BETWEEN` bao gồm cả hai đầu:

```sql
SELECT order_id, amount
FROM orders
WHERE amount BETWEEN 100.00 AND 150.00
ORDER BY order_id;
```

Điều kiện tương đương là `amount >= 100.00 AND amount <= 150.00`. Hãy thử các giá trị ngay dưới, đúng bằng và ngay trên ngưỡng. Với `DECIMAL`, có thể dùng các giá trị như `99.99`, `100.00`, `100.01` để làm rõ biên.

### 7.2. Kết hợp AND và OR

Không dựa vào trí nhớ hoặc cách đọc tự nhiên để suy ra thứ tự logic. Dùng ngoặc khi điều kiện có nhiều `AND` và `OR`:

```sql
SELECT order_id, status, amount
FROM orders
WHERE status = 'PAID'
  AND (amount = 0 OR amount >= 100.00)
ORDER BY order_id;
```

Fixture giúp xác minh đơn 101, 104, 105 và 106 được chọn; đơn 103 có amount `NULL` không thỏa điều kiện, còn đơn 102 sai status. Thử bỏ ngoặc và so sánh kết quả để nhận diện lỗi ưu tiên toán tử.

### 7.3. LIKE và ký tự wildcard

Trong `LIKE`, `%` khớp chuỗi bất kỳ và `_` khớp một ký tự. Nếu người dùng nhập ký tự wildcard theo nghĩa đen, cần escape chúng:

```sql
SELECT customer_name
FROM customers
WHERE customer_name LIKE 'B%'
ORDER BY customer_id;
```

Khi tìm chuỗi chứa ký tự `%` hoặc `_`, quy định ký tự escape và dùng cùng quy tắc trong truy vấn. Không ghép trực tiếp chuỗi đầu vào vào SQL; dùng `PreparedStatement` và escape wildcard theo yêu cầu tìm kiếm.

## 8. Kiểm tra ngày giờ tại ranh giới

Với cột `DATETIME(6)`, điều kiện “mọi đơn trong ngày 19/11/2026” nên được viết dưới dạng khoảng nửa mở:

```sql
SELECT order_id, placed_at
FROM orders
WHERE placed_at >= '2026-11-19 00:00:00'
  AND placed_at <  '2026-11-20 00:00:00'
ORDER BY placed_at, order_id;
```

Expected result: các đơn 101, 102, 103 và 106. Đơn 101 đúng tại đầu ngày được bao gồm; đơn 103 ở microsecond cuối ngày cũng được bao gồm; đơn 104 đúng tại đầu ngày tiếp theo bị loại.

Không nên viết:

```sql
WHERE placed_at BETWEEN '2026-11-19 00:00:00'
                     AND '2026-11-19 23:59:59'
```

Điều kiện này bỏ sót giá trị có phần microsecond sau `23:59:59.000000`. Cũng không nên dùng `DATE(placed_at) = '2026-11-19'` nếu muốn tận dụng index B-tree thông thường trên `placed_at`; áp dụng hàm lên cột có thể làm điều kiện không sargable.

Nếu cột là `TIMESTAMP`, cần tính ranh giới theo múi giờ nghiệp vụ rồi truyền các thời điểm tương ứng theo cấu hình session. Không lấy nửa đêm UTC làm đầu ngày địa phương nếu yêu cầu là ngày tại một múi giờ khác.

## 9. Kiểm tra ORDER BY, tie và LIMIT

Một truy vấn không có `ORDER BY` không cam kết thứ tự hàng. Thứ tự tình cờ quan sát được trong một lần chạy không phải hợp đồng SQL.

Hai đơn của khách hàng 2 có cùng số tiền. Nếu cần sắp xếp giảm dần theo amount, thêm khóa phân xử duy nhất:

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = 2
ORDER BY amount DESC, order_id ASC;
```

Expected order: 104 trước 105. Nếu chỉ viết `ORDER BY amount DESC`, hai hàng cùng giá trị có thể xuất hiện theo thứ tự khác nhau giữa các kế hoạch thực thi.

Với phân trang:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at ASC, order_id ASC
LIMIT 2 OFFSET 2;
```

Thêm `order_id` giúp thứ tự xác định khi nhiều hàng có cùng `placed_at`. Khi dữ liệu thay đổi giữa các request, offset pagination vẫn có thể bỏ qua hoặc lặp hàng do vị trí hàng dịch chuyển. Với tập dữ liệu lớn hoặc thay đổi thường xuyên, cân nhắc keyset pagination dựa trên cặp khóa sắp xếp cuối cùng.

Hãy kiểm tra các trường hợp `LIMIT 0`, không có hàng, số hàng ít hơn page size, đúng bằng page size và nhiều hơn page size. Xác định rõ offset bắt đầu từ 0 và cách API xử lý page index.

## 10. Kiểm tra GROUP BY và aggregate

Aggregate có quy tắc riêng với `NULL` và tập rỗng:

| Biểu thức | Hành vi cần kiểm tra |
| --- | --- |
| `COUNT(*)` | Đếm hàng, kể cả hàng có cột NULL |
| `COUNT(column)` | Chỉ đếm hàng mà `column` không NULL |
| `SUM(column)` | Bỏ qua NULL; trả NULL nếu không có giá trị nào để cộng |
| `AVG(column)` | Bỏ qua NULL; trả NULL nếu không có giá trị số nào |
| `MIN()` / `MAX()` | Bỏ qua NULL; trả NULL nếu không có giá trị |
| `COUNT(DISTINCT column)` | Đếm giá trị khác nhau, bỏ NULL |

Kiểm tra trên fixture:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(DISTINCT amount) AS distinct_amount_count,
    SUM(amount) AS amount_sum,
    AVG(amount) AS amount_avg,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM orders
WHERE customer_id = 1
  AND status = 'PAID';
```

Expected result: `row_count = 2`, `amount_count = 1`, `distinct_amount_count = 1`, `amount_sum = 100.00`, `amount_avg = 100.00`, `min_amount = 100.00`, `max_amount = 100.00`. Đơn 103 có amount NULL nên không tham gia các phép aggregate trên cột amount.

Với `GROUP BY`, mỗi nhóm chỉ xuất hiện nếu có ít nhất một hàng đầu vào. Nếu tập đầu vào rỗng, truy vấn có `GROUP BY` trả 0 nhóm; truy vấn aggregate không có `GROUP BY` thường trả một hàng tổng hợp. Kiểm tra cả hai trường hợp khi API cần phân biệt “không có nhóm” với “nhóm có tổng bằng 0”.

Trong MySQL, bật `ONLY_FULL_GROUP_BY` giúp phát hiện nhiều truy vấn chọn cột không được nhóm hoặc không phụ thuộc hàm hợp lệ vào cột nhóm. Đừng tắt chế độ này chỉ để truy vấn chạy; hãy xác định cột nào phải aggregate hoặc đưa vào `GROUP BY`.

## 11. So sánh kết quả thực tế với expected result

Với truy vấn quan trọng, có thể lưu expected result thành một bảng fixture rồi đối chiếu hai tập dữ liệu. Cách dưới đây so sánh các giá trị theo khóa chính và dùng `<=>` để so sánh an toàn với `NULL`.

Tạo bảng mong đợi:

```sql
DROP TEMPORARY TABLE IF EXISTS expected_customer_totals;
DROP TEMPORARY TABLE IF EXISTS actual_customer_totals;

CREATE TEMPORARY TABLE expected_customer_totals (
    customer_id INT UNSIGNED NOT NULL,
    paid_order_count INT NOT NULL,
    amount_count INT NOT NULL,
    paid_total DECIMAL(12, 2) NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE actual_customer_totals LIKE expected_customer_totals;

INSERT INTO expected_customer_totals VALUES
(1, 2, 1, 100.00),
(2, 2, 2, 300.00),
(3, 1, 1,   0.00),
(4, 0, 0,    NULL);
```

Đưa kết quả truy vấn cần kiểm chứng vào bảng thực tế:

```sql
INSERT INTO actual_customer_totals
    (customer_id, paid_order_count, amount_count, paid_total)
SELECT
    c.customer_id,
    COUNT(o.order_id),
    COUNT(o.amount),
    SUM(o.amount)
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id;
```

Tìm hàng bị thiếu hoặc có giá trị khác:

```sql
SELECT 'missing_or_different' AS problem, e.customer_id
FROM expected_customer_totals AS e
LEFT JOIN actual_customer_totals AS a
    ON a.customer_id = e.customer_id
WHERE a.customer_id IS NULL
   OR NOT (
       a.paid_order_count <=> e.paid_order_count
       AND a.amount_count <=> e.amount_count
       AND a.paid_total <=> e.paid_total
   )

UNION ALL

SELECT 'unexpected' AS problem, a.customer_id
FROM actual_customer_totals AS a
LEFT JOIN expected_customer_totals AS e
    ON e.customer_id = a.customer_id
WHERE e.customer_id IS NULL
ORDER BY problem, customer_id;
```

Nếu truy vấn không trả hàng nào, hai tập kết quả khớp theo các cột được kiểm tra. Nếu có dòng, cột `problem` cho biết hàng thiếu/khác hoặc hàng không mong đợi.

Phương pháp này phù hợp khi mỗi kết quả có khóa định danh duy nhất. Nếu kết quả có thể chứa nhiều hàng giống hệt nhau và không có khóa phân biệt, cần so sánh cả số lần xuất hiện của từng tổ hợp giá trị (multiset comparison), không chỉ dùng `DISTINCT` hoặc phép anti-join đơn giản.

Với ứng dụng Java, có thể kiểm tra bằng integration test: chạy fixture trong transaction, gọi repository, so sánh danh sách DTO với expected list, kiểm tra thứ tự nếu API cam kết thứ tự và rollback hoặc dọn dữ liệu sau test. Không chỉ assert `list.size()`; hai danh sách cùng số hàng vẫn có thể chứa dữ liệu sai.

## 12. Tách kiểm chứng tính đúng đắn và kiểm tra hiệu năng

Một truy vấn có thể trả kết quả đúng nhưng chạy chậm; ngược lại, một truy vấn nhanh nhưng trả thiếu hoặc nhân bản hàng vẫn là truy vấn sai. Hãy tách hai loại kiểm tra.

**Kiểm chứng tính đúng đắn:**

- Dùng fixture nhỏ có expected result rõ ràng.
- Kiểm tra giá trị từng cột, số hàng, `NULL`, duplicate và thứ tự.
- Thử các đầu vào rỗng, giá trị biên và trường hợp không có quan hệ.
- Kiểm tra cùng truy vấn với các biến thể dữ liệu làm lộ lỗi.

**Kiểm tra hiệu năng:**

- Chạy `EXPLAIN` để xem access type, key, rows ước lượng và Extra.
- Kiểm tra index có phù hợp điều kiện lọc/join/sort không.
- Dùng dữ liệu có quy mô và phân bố gần production để đo.
- Dùng `EXPLAIN ANALYZE` khi chấp nhận việc truy vấn được thực thi thật.
- Đo nhiều lần, quan sát độ biến thiên và tác động cache/tải đồng thời.

Fixture tối thiểu giúp chứng minh logic ở các trường hợp được chọn, nhưng không đủ để kết luận hiệu năng trên hàng triệu bản ghi. Dữ liệu nhỏ thường khiến optimizer chọn table scan; điều đó không tự chứng minh index production không hữu ích.

## 13. Những lỗi kiểm thử thường gặp

| Lỗi kiểm thử | Vì sao không đủ | Cách cải thiện |
| --- | --- | --- |
| Chỉ chạy một truy vấn trên dữ liệu production | Không biết kết quả nào là đúng và khó tái hiện | Tạo fixture nhỏ và expected result |
| Chỉ assert số lượng hàng | Giá trị có thể sai nhưng số hàng vẫn đúng | So sánh khóa và toàn bộ cột quan trọng |
| Không có hàng NULL | Bỏ sót logic ba giá trị của SQL | Thêm NULL và kiểm tra `IS NULL`, aggregate |
| Không có dữ liệu trùng | Không phát hiện nhân bản do JOIN hoặc dùng DISTINCT sai | Thêm hai hàng khác khóa nhưng cùng giá trị |
| Không có hàng cha thiếu con | Không phát hiện lỗi `LEFT JOIN` bị lọc thành `INNER JOIN` | Thêm ít nhất một hàng cha không có hàng con |
| Không có giá trị bằng 0 | Dễ nhầm 0 với NULL hoặc không có hàng | Kiểm tra riêng 0, NULL và tập rỗng |
| Không kiểm tra ranh giới thời gian | Có thể bỏ sót microsecond hoặc ngày kế tiếp | Thử đầu khoảng, cuối khoảng và đầu khoảng kế tiếp |
| Dựa vào thứ tự mặc định | Thứ tự không được bảo đảm nếu thiếu `ORDER BY` | Thêm khóa phân xử duy nhất |
| Chỉ kiểm tra trên dữ liệu nhỏ rồi kết luận tốc độ | Cardinality và phân bố khác production | Benchmark riêng với dữ liệu đại diện |
| Dùng `DISTINCT` để che lỗi JOIN | Có thể che dữ liệu bị nhân bản thay vì sửa nguyên nhân | Kiểm tra cardinality từng quan hệ và aggregate trước khi join |

## 14. Checklist trước khi tin một SELECT

- [ ] Câu hỏi nghiệp vụ và hợp đồng kết quả đã được viết rõ.
- [ ] Fixture có dữ liệu bình thường, biên, `NULL`, 0, duplicate và không có quan hệ khi cần.
- [ ] Expected result được xác định trước khi chạy truy vấn.
- [ ] Điều kiện lọc của bảng bên phải trong `LEFT JOIN` được đặt đúng vị trí.
- [ ] Đếm hàng con bằng cột không nullable, không nhầm `COUNT(*)` với `COUNT(child.id)`.
- [ ] Các aggregate được kiểm tra với tập rỗng và giá trị NULL.
- [ ] Các phép `NOT IN`, `NOT EXISTS`, `IN` và `NULL` được kiểm tra đúng ngữ nghĩa.
- [ ] Điều kiện biên số học và ngày giờ đã được thử.
- [ ] `ORDER BY` có khóa phân xử để thứ tự xác định nếu cần.
- [ ] Phân trang được kiểm tra với dữ liệu có giá trị sort trùng nhau.
- [ ] Kết quả được so sánh theo giá trị, không chỉ số hàng.
- [ ] Kiểm tra hiệu năng bằng `EXPLAIN`/dữ liệu đại diện được tách khỏi kiểm chứng logic.

## 15. Bài tập thực hành

1. Chạy fixture ở phần 2 và ghi expected result của truy vấn tổng hợp trước khi chạy SQL.
2. Đổi điều kiện `o.status = 'PAID'` từ `ON` sang `WHERE`. Ghi nhận khách hàng nào biến mất và giải thích.
3. Thay `COUNT(o.order_id)` bằng `COUNT(*)`. So sánh khách hàng có và không có đơn.
4. Thử `amount = NULL`, `amount IS NULL` và `amount <=> NULL`. Giải thích kết quả từng câu.
5. Thêm `NULL` vào tập loại trừ. So sánh `NOT IN` với `NOT EXISTS`.
6. So sánh tổng tiền dùng `SUM(amount)` với `SUM(DISTINCT amount)` cho khách hàng 2.
7. Thử điều kiện thời gian bằng `BETWEEN` kết thúc ở `23:59:59` và khoảng nửa mở. Xác định đơn bị bỏ sót.
8. Bỏ `order_id` khỏi `ORDER BY amount DESC`. Giải thích vì sao thứ tự giữa đơn 104 và 105 không được bảo đảm.
9. Tạo expected/actual temporary table và chạy truy vấn đối chiếu ở phần 11. Cố ý thay một expected value để xác nhận test phát hiện sai lệch.
10. Chạy `EXPLAIN` trên truy vấn lọc theo `customer_id`, `status` và `placed_at`; xem index tổng hợp trong fixture có được chọn không. Không kết luận hiệu năng production từ fixture nhỏ.

## 16. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể tạo một fixture nhỏ nhưng đủ phân biệt các tình huống quan trọng, viết expected result trước, kiểm tra được NULL/0/tập rỗng/duplicate, phát hiện lỗi do vị trí điều kiện JOIN và phép aggregate, kiểm chứng ranh giới ngày giờ, bảo đảm thứ tự ổn định khi phân trang và đối chiếu kết quả thực tế với expected result. Bạn cũng cần giải thích vì sao kiểm chứng logic bằng dữ liệu tối thiểu và đánh giá hiệu năng bằng dữ liệu đại diện là hai công việc riêng.
