# Viết truy vấn báo cáo với JOIN, CTE, tổng hợp và hàm cửa sổ

Một báo cáo PostgreSQL thường phải kết hợp dữ liệu từ nhiều bảng, tính các chỉ số theo nhóm và bổ sung thông tin so sánh theo thời gian hoặc thứ hạng. JOIN đưa các bản ghi liên quan về cùng một tập kết quả; hàm tổng hợp biến nhiều dòng thành chỉ số; CTE chia truy vấn thành các bước có tên; hàm cửa sổ tính toán trên một nhóm dòng mà vẫn giữ lại từng dòng chi tiết.

Khi phối hợp các kỹ thuật này, điều quan trọng nhất là giữ đúng mức chi tiết của dữ liệu. Nếu nối hai bảng quan hệ một-nhiều trước khi tổng hợp, số dòng có thể bị nhân lên và làm sai doanh thu, số đơn hoặc số tiền thanh toán. Bài học này dùng một mô hình bán hàng thống nhất để trình bày cách thiết kế truy vấn, kiểm soát số liệu và cải thiện hiệu năng.

## 1. Mô hình dữ liệu dùng trong bài thực hành

Giả sử hệ thống bán hàng có các bảng:

- customers: khách hàng.
- orders: đơn hàng, mỗi đơn thuộc một khách hàng.
- order_items: các dòng sản phẩm trong đơn hàng.
- products: danh mục sản phẩm.
- payments: các lần thanh toán của đơn hàng. Một đơn có thể được thanh toán nhiều lần.

Quan hệ chính:

~~~text
customers 1 ───── n orders
orders    1 ───── n order_items
products  1 ───── n order_items
orders    1 ───── n payments
~~~

Có thể hình dung schema rút gọn như sau:

~~~sql
CREATE TABLE customers (
    customer_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL,
    region        text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE products (
    product_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name text NOT NULL,
    category     text NOT NULL
);

CREATE TABLE orders (
    order_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    order_date  timestamptz NOT NULL DEFAULT now(),
    status      text NOT NULL,
    channel     text NOT NULL
);

CREATE TABLE order_items (
    order_id        bigint NOT NULL REFERENCES orders(order_id),
    product_id      bigint NOT NULL REFERENCES products(product_id),
    quantity        numeric(12, 2) NOT NULL CHECK (quantity > 0),
    unit_price      numeric(14, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount numeric(14, 2) NOT NULL DEFAULT 0
                    CHECK (discount_amount >= 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   bigint NOT NULL REFERENCES orders(order_id),
    paid_at    timestamptz NOT NULL DEFAULT now(),
    amount     numeric(14, 2) NOT NULL CHECK (amount >= 0),
    status     text NOT NULL
);
~~~

Trong ví dụ, giá trị hàng hóa sau giảm giá được tính theo dòng:

~~~sql
quantity * unit_price - discount_amount
~~~

Giả sử báo cáo chỉ tính những payment có status là 'succeeded'. Quy tắc nghiệp vụ thực tế có thể khác: có hệ thống dùng 'captured', 'settled', hoặc phải trừ refund. Hãy thống nhất định nghĩa chỉ số trước khi viết SQL.

Khóa chính và khóa ngoại cho biết cách nối bảng, nhưng không tự quyết định mức chi tiết của báo cáo. Trước mỗi phép JOIN, hãy xác định một dòng ở mỗi phía đại diện cho điều gì:

| Bảng | Một dòng đại diện cho |
|---|---|
| customers | Một khách hàng |
| orders | Một đơn hàng |
| order_items | Một sản phẩm trong một đơn hàng |
| products | Một sản phẩm trong danh mục |
| payments | Một lần thanh toán |

Việc xác định grain (mức chi tiết) này giúp dự đoán JOIN có thể tạo ra bao nhiêu dòng.

## 2. Kết hợp bảng bằng JOIN

### 2.1. INNER JOIN

INNER JOIN chỉ trả về những dòng có khóa nối khớp ở cả hai phía.

Ví dụ, liệt kê đơn hàng cùng tên khách hàng:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_id,
    c.customer_name,
    c.region
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Do customer_id trong orders là khóa ngoại NOT NULL, mỗi đơn hàng hợp lệ có đúng một khách hàng tương ứng. JOIN này không làm tăng số dòng so với orders.

Khi nối order_items với products, mỗi dòng mặt hàng nhận thêm tên và danh mục sản phẩm:

~~~sql
SELECT
    oi.order_id,
    p.product_id,
    p.product_name,
    p.category,
    oi.quantity,
    oi.unit_price,
    oi.discount_amount,
    oi.quantity * oi.unit_price - oi.discount_amount AS line_total
FROM order_items AS oi
JOIN products AS p
    ON p.product_id = oi.product_id
ORDER BY oi.order_id, p.product_name;
~~~

Vì product_id là khóa chính của products, mỗi dòng order_items khớp tối đa một dòng sản phẩm.

### 2.2. LEFT JOIN để giữ lại dòng không có dữ liệu liên quan

LEFT JOIN giữ tất cả dòng ở bảng bên trái. Nếu không có dòng khớp ở bảng bên phải, các cột bên phải nhận NULL.

Ví dụ, liệt kê mọi khách hàng và đơn gần nhất nếu có:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_date
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_date DESC NULLS LAST;
~~~

Khách hàng chưa có đơn vẫn xuất hiện một lần với các cột đơn hàng là NULL. Khách hàng có nhiều đơn xuất hiện nhiều dòng, một dòng cho mỗi đơn.

Nếu mục tiêu là tìm khách hàng chưa từng đặt hàng, có thể dùng anti-join:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Một cách tương đương, thường dễ diễn đạt ý định, là NOT EXISTS:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

### 2.3. Điều kiện lọc trong ON và WHERE

Với LEFT JOIN, vị trí đặt điều kiện có thể làm thay đổi kết quả.

Giả sử cần liệt kê tất cả khách hàng và chỉ nối các đơn đã hoàn thành:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'completed';
~~~

Điều kiện status nằm trong ON, vì vậy khách hàng không có đơn completed vẫn được giữ lại.

Nếu viết điều kiện ở WHERE:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'completed';
~~~

Các dòng không có đơn có status NULL sẽ bị loại. Kết quả lúc này có hành vi gần như INNER JOIN đối với điều kiện đó.

Quy tắc thực hành:

- Đặt điều kiện xác định dòng nào được phép khớp ở phía JOIN trong ON khi muốn giữ các dòng bên trái.
- Đặt điều kiện lọc kết quả cuối trong WHERE.
- Với INNER JOIN, điều kiện tương đương có thể thường đặt ở ON hoặc WHERE; chọn vị trí dễ đọc.

### 2.4. FULL JOIN và các loại JOIN khác

FULL OUTER JOIN giữ cả dòng chỉ có ở bảng trái lẫn dòng chỉ có ở bảng phải. Nó hữu ích khi đối chiếu hai tập dữ liệu, chẳng hạn danh sách mã sản phẩm từ hệ thống bán hàng và hệ thống kho.

~~~sql
SELECT
    COALESCE(s.product_id, w.product_id) AS product_id,
    s.sold_quantity,
    w.stock_quantity
FROM sales_summary AS s
FULL OUTER JOIN warehouse_summary AS w
    ON w.product_id = s.product_id;
~~~

Câu lệnh trên giả định hai summary đã được tạo trước và mỗi product_id chỉ có một dòng ở mỗi phía.

CROSS JOIN tạo mọi tổ hợp giữa hai tập dòng. Nó có thể hữu ích khi tạo ma trận tháng × khu vực hoặc lịch báo cáo, nhưng số dòng tăng theo tích số lượng hai phía. Chỉ dùng khi thật sự cần tất cả tổ hợp.

## 3. Tránh nhân bản số liệu khi JOIN nhiều bảng một-nhiều

Đây là lỗi phổ biến nhất khi viết báo cáo doanh thu.

Một đơn hàng có 3 dòng order_items và 2 dòng payments. Nếu nối cả hai bảng trực tiếp vào orders, kết quả có thể có 3 × 2 = 6 dòng cho đơn hàng đó. Mỗi dòng mặt hàng bị lặp hai lần và mỗi lần thanh toán bị lặp ba lần.

Ví dụ truy vấn dễ sai:

~~~sql
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS order_total,
    SUM(p.amount) AS paid_total
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN payments AS p
    ON p.order_id = o.order_id
WHERE p.status = 'succeeded'
GROUP BY o.order_id;
~~~

Giả sử đơn hàng có:

- Mặt hàng A: 100.000 đồng.
- Mặt hàng B: 200.000 đồng.
- Thanh toán lần 1: 150.000 đồng.
- Thanh toán lần 2: 150.000 đồng.

Kết quả đúng phải là doanh thu 300.000 đồng và đã thu 300.000 đồng. JOIN trực tiếp tạo 4 dòng; tổng doanh thu thành 600.000 đồng và tổng thanh toán cũng thành 600.000 đồng.

Không nên chữa lỗi này bằng cách thêm SUM(DISTINCT amount) hoặc SUM(DISTINCT line_total). Hai mặt hàng có thể có cùng giá trị, hai lần thanh toán có thể có cùng số tiền; DISTINCT khi đó loại mất giao dịch hợp lệ.

### 3.1. Tổng hợp từng bảng con trước khi JOIN

Cách an toàn là đưa mỗi bảng một-nhiều về cùng mức chi tiết order_id trước khi nối:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total,
        COUNT(*) AS item_line_count
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total,
        COUNT(*) AS payment_count
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.order_total, 0) AS order_total,
    COALESCE(i.item_line_count, 0) AS item_line_count,
    COALESCE(p.paid_total, 0) AS paid_total,
    COALESCE(p.payment_count, 0) AS payment_count
FROM orders AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Sau GROUP BY, mỗi CTE có tối đa một dòng cho mỗi order_id. JOIN vào orders vì thế không nhân bản số liệu. LEFT JOIN giữ đơn chưa có mặt hàng hoặc chưa có thanh toán; COALESCE chuyển giá trị tổng NULL thành 0 khi đó là cách biểu diễn phù hợp với nghiệp vụ.

### 3.2. Kiểm tra grain sau mỗi bước

Trước khi thêm JOIN tiếp theo, tự trả lời:

1. Một dòng của kết quả hiện tại đại diện cho một khách hàng, đơn hàng, mặt hàng hay thanh toán?
2. Khóa nối có duy nhất ở phía đang được nối không?
3. Quan hệ là một-một, một-nhiều hay nhiều-nhiều?
4. Chỉ số đang tính thuộc cấp đơn hàng hay cấp dòng mặt hàng?
5. JOIN có thể làm lặp một giá trị đã được tính ở cấp cao hơn không?

Nếu báo cáo cần chỉ số theo đơn hàng, hãy đưa các bảng con về một dòng mỗi đơn trước. Nếu cần chỉ số theo mặt hàng, hãy xác định rõ khoản thanh toán được phân bổ xuống mặt hàng theo quy tắc nào; không thể tự động gán toàn bộ payment của đơn cho từng dòng sản phẩm.

## 4. Tổng hợp dữ liệu với GROUP BY

Hàm tổng hợp nhận nhiều dòng và tạo một giá trị cho mỗi nhóm. Các hàm thường dùng:

| Hàm | Ý nghĩa |
|---|---|
| COUNT(*) | Đếm số dòng trong nhóm |
| COUNT(column) | Đếm dòng có column khác NULL |
| COUNT(DISTINCT column) | Đếm số giá trị khác nhau, bỏ NULL |
| SUM(column) | Cộng giá trị khác NULL |
| AVG(column) | Trung bình các giá trị khác NULL |
| MIN(column), MAX(column) | Giá trị nhỏ nhất, lớn nhất |
| BOOL_AND(expression) | TRUE nếu mọi giá trị trong nhóm đều TRUE |
| BOOL_OR(expression) | TRUE nếu có ít nhất một giá trị TRUE |
| STRING_AGG(value, delimiter) | Ghép chuỗi trong nhóm |

Ví dụ, số đơn và doanh thu theo khách hàng:

~~~sql
SELECT
    o.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY o.customer_id
ORDER BY revenue DESC NULLS LAST;
~~~

Ở đây kết quả được nhóm theo customer_id. Tuy nhiên, JOIN chỉ có order_items sẽ bỏ các đơn không có dòng mặt hàng. Nếu cần giữ khách hàng hoặc đơn không có mặt hàng, hãy dùng LEFT JOIN hoặc tổng hợp order_items riêng trước khi nối.

### 4.1. GROUP BY nhiều chiều

Báo cáo có thể nhóm theo nhiều thuộc tính, chẳng hạn khu vực, kênh bán và trạng thái:

~~~sql
SELECT
    c.region,
    o.channel,
    o.status,
    COUNT(*) AS order_count
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
GROUP BY
    c.region,
    o.channel,
    o.status
ORDER BY
    c.region,
    o.channel,
    o.status;
~~~

Mỗi tổ hợp giá trị tạo một nhóm riêng. Nếu một cột có NULL, các dòng NULL của cột đó được xếp cùng một nhóm.

### 4.2. COUNT(*) và COUNT(column)

Hai biểu thức này khác nhau khi có NULL:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(p.payment_id) AS rows_with_payment,
    COUNT(DISTINCT p.order_id) AS orders_with_payment
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id;
~~~

LEFT JOIN tạo một dòng có các cột payment NULL cho đơn chưa thanh toán. COUNT(*) vẫn đếm dòng đó; COUNT(p.payment_id) không đếm vì payment_id là NULL.

COUNT(DISTINCT p.order_id) đếm số đơn có ít nhất một dòng payment. Nó hữu ích cho chỉ số đếm đơn, nhưng không nên dùng DISTINCT như cách sửa mọi vấn đề nhân bản JOIN.

### 4.3. SUM, AVG và NULL

SUM và AVG bỏ qua giá trị NULL. Nếu toàn bộ giá trị trong nhóm là NULL, SUM trả về NULL chứ không phải 0. Ví dụ tổng hợp theo từng đơn:

~~~sql
SELECT
    order_id,
    COALESCE(SUM(amount), 0) AS total_amount,
    AVG(amount) AS average_payment
FROM payments
WHERE status = 'succeeded'
GROUP BY order_id;
~~~

Schema mẫu không có customer_id trong payments. Nếu muốn tổng hợp theo khách hàng, cần JOIN qua orders:

~~~sql
SELECT
    o.customer_id,
    COALESCE(SUM(p.amount), 0) AS total_paid
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
   AND p.status = 'succeeded'
GROUP BY o.customer_id;
~~~

Ở truy vấn này, mỗi payment thuộc đúng một order, nhưng một khách hàng có nhiều order và mỗi order có thể nhiều payment. Vì chỉ tổng hợp payment và không nối order_items, tổng tiền không bị nhân theo số mặt hàng.

Dùng COALESCE ở đúng cấp. Nếu cần phân biệt “chưa có thanh toán” với “có thanh toán nhưng số tiền bằng 0”, hãy giữ thêm COUNT(payment_id) thay vì chỉ thay NULL bằng 0.

### 4.4. FILTER để tính nhiều chỉ số trong một lượt nhóm

FILTER cho phép mỗi hàm tổng hợp có điều kiện riêng:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM orders
GROUP BY customer_id;
~~~

Ví dụ tính tổng thanh toán thành công và số lần thanh toán thất bại:

~~~sql
SELECT
    order_id,
    COALESCE(SUM(amount) FILTER (WHERE status = 'succeeded'), 0)
        AS successful_amount,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_attempts
FROM payments
GROUP BY order_id;
~~~

FILTER thường giúp câu SQL dễ đọc hơn nhiều biểu thức CASE lồng nhau. Có thể dùng CASE khi cần tương thích với hệ thống khác hoặc logic phức tạp hơn.

### 4.5. HAVING lọc nhóm sau khi tổng hợp

WHERE lọc các dòng đầu vào trước GROUP BY; HAVING lọc nhóm sau khi tính tổng hợp.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id
HAVING COUNT(*) >= 5
ORDER BY order_count DESC;
~~~

Truy vấn trên chỉ xét đơn từ mốc thời gian đã chọn, sau đó chỉ giữ khách hàng có ít nhất 5 đơn trong tập đó.

Không đặt điều kiện trên kết quả tổng hợp vào WHERE cùng cấp với GROUP BY. Hãy dùng HAVING hoặc tạo CTE/subquery rồi lọc ở truy vấn ngoài.

## 5. Tổng hợp theo ngày, tháng và khoảng thời gian

Báo cáo thời gian thường nhóm bằng date_trunc:

~~~sql
SELECT
    date_trunc('month', order_date) AS month_start,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
GROUP BY date_trunc('month', order_date)
ORDER BY month_start;
~~~

Dùng khoảng nửa mở [from, to): bao gồm thời điểm bắt đầu và loại thời điểm kết thúc. Cách này tránh phải đoán giá trị “cuối ngày” như 23:59:59.999999 và thuận tiện nối các kỳ liên tiếp mà không chồng lấn.

Với cột timestamptz, hãy thống nhất múi giờ báo cáo. date_trunc trên timestamptz phụ thuộc TimeZone của session nếu không chỉ định múi giờ. Nếu báo cáo theo giờ Việt Nam:

~~~sql
SELECT
    date_trunc('month', order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')
        AS local_month,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
GROUP BY local_month
ORDER BY local_month;
~~~

Biểu thức AT TIME ZONE chuyển timestamptz sang timestamp địa phương để gom theo tháng lịch Việt Nam. Phạm vi lọc vẫn so sánh trên cột timestamptz trực tiếp, giúp tận dụng chỉ mục B-tree trên order_date tốt hơn việc bọc cột trong hàm ở WHERE.

Tránh viết:

~~~sql
WHERE date_trunc('day', order_date) = DATE '2026-05-01'
~~~

Biểu thức trên áp dụng hàm lên cột, có thể khiến chỉ mục thông thường trên order_date khó được sử dụng. Nên viết điều kiện khoảng:

~~~sql
WHERE order_date >= TIMESTAMPTZ '2026-05-01 00:00:00+07'
  AND order_date <  TIMESTAMPTZ '2026-05-02 00:00:00+07'
~~~

Nếu cần ngày không có giao dịch vẫn xuất hiện với giá trị 0, GROUP BY trên orders không thể tự sinh ngày còn thiếu. Có thể tạo lịch bằng generate_series rồi LEFT JOIN số liệu:

~~~sql
WITH calendar AS (
    SELECT generate_series(
        DATE '2026-05-01',
        DATE '2026-05-07',
        INTERVAL '1 day'
    )::date AS report_date
),
daily_orders AS (
    SELECT
        (order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS report_date,
        COUNT(*) AS order_count
    FROM orders
    WHERE order_date >= TIMESTAMPTZ '2026-05-01 00:00:00+07'
      AND order_date <  TIMESTAMPTZ '2026-05-08 00:00:00+07'
    GROUP BY (order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    c.report_date,
    COALESCE(d.order_count, 0) AS order_count
FROM calendar AS c
LEFT JOIN daily_orders AS d
    ON d.report_date = c.report_date
ORDER BY c.report_date;
~~~

generate_series tạo một dòng cho từng ngày. LEFT JOIN giữ ngày không có đơn; COALESCE hiển thị 0 thay cho NULL.

## 6. Dùng CTE để chia truy vấn thành các bước

CTE (Common Table Expression) được khai báo bằng WITH và đặt tên cho một kết quả trung gian. Nó giúp tách báo cáo thành các bước có ý nghĩa, giảm lặp logic và làm rõ grain của từng tập dữ liệu.

Cấu trúc cơ bản:

~~~sql
WITH
step_one AS (
    SELECT ...
),
step_two AS (
    SELECT ...
    FROM step_one
)
SELECT ...
FROM step_two;
~~~

Một CTE có thể tham chiếu CTE được khai báo trước đó trong cùng mệnh đề WITH. CTE không tạo bảng vật lý lâu dài; phạm vi tên của nó chỉ tồn tại trong câu lệnh.

### 6.1. Tạo báo cáo nhiều bước

Ta cần báo cáo theo tháng và khu vực, gồm số đơn, số khách hàng, doanh thu hàng hóa và tiền đã thu. Bước đầu tiên tổng hợp mặt hàng và thanh toán riêng ở cấp order_id:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total,
        COUNT(*) AS item_line_count
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.customer_id,
        c.region,
        o.channel,
        o.order_date,
        o.status,
        COALESCE(i.order_total, 0) AS order_total,
        COALESCE(p.paid_total, 0) AS paid_total
    FROM orders AS o
    JOIN customers AS c
        ON c.customer_id = o.customer_id
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
    LEFT JOIN payment_totals AS p
        ON p.order_id = o.order_id
)
SELECT
    date_trunc('month', order_date) AS month_start,
    region,
    channel,
    COUNT(*) AS order_count,
    COUNT(DISTINCT customer_id) AS customer_count,
    SUM(order_total) AS merchandise_total,
    SUM(paid_total) AS collected_total,
    SUM(order_total - paid_total) AS difference_total
FROM order_facts
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
  AND status = 'completed'
GROUP BY
    date_trunc('month', order_date),
    region,
    channel
ORDER BY
    month_start,
    region,
    channel;
~~~

Ý nghĩa từng bước:

1. item_totals: một dòng mỗi order_id, tính giá trị hàng hóa và số dòng mặt hàng.
2. payment_totals: một dòng mỗi order_id, chỉ cộng payment thành công.
3. order_facts: nối thông tin đơn và khách hàng với hai tập đã tổng hợp.
4. Truy vấn cuối: lọc kỳ báo cáo và trạng thái, sau đó nhóm theo tháng, khu vực, kênh.

Vì item_totals và payment_totals đã có tối đa một dòng cho mỗi order_id, hai phép LEFT JOIN không nhân số liệu. order_facts có một dòng cho mỗi đơn hàng đủ điều kiện. COUNT(*) vì vậy đếm đơn; COUNT(DISTINCT customer_id) đếm khách hàng duy nhất trong mỗi nhóm tháng/khu vực/kênh.

Chỉ số difference_total trong ví dụ là chênh lệch giữa giá trị hàng hóa và payment thành công. Nó chỉ có ý nghĩa như số tiền còn phải thu nếu quy tắc nghiệp vụ không có thuế, phí vận chuyển, hoàn tiền, thanh toán thừa, hủy đơn hoặc điều chỉnh khác. Với hệ thống thật, hãy định nghĩa công thức công nợ rõ ràng và bổ sung các thành phần còn thiếu.

### 6.2. CTE có thể làm truy vấn dễ kiểm tra

Khi truy vấn dài, có thể chạy từng CTE bằng cách tạm thay SELECT cuối bằng:

~~~sql
SELECT *
FROM item_totals
ORDER BY order_id
LIMIT 20;
~~~

Sau đó kiểm tra payment_totals, rồi order_facts. Với mỗi bước, kiểm tra số dòng và tính duy nhất của khóa dự kiến:

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM order_facts;
~~~

Nếu order_facts được thiết kế một dòng mỗi đơn, hai số này phải bằng nhau. Nếu không, hãy kiểm tra bảng nối nào tạo thêm dòng.

### 6.3. CTE và tối ưu hóa

CTE là công cụ tổ chức logic, không mặc định đồng nghĩa với bảng tạm được lưu trên đĩa. Từ PostgreSQL 12, nhiều CTE không đệ quy, không có side effect có thể được inline vào truy vấn chính khi bộ tối ưu thấy phù hợp. CTE được tham chiếu nhiều lần, hoặc được chỉ định MATERIALIZED, có thể được tính và lưu kết quả trung gian; điều này đôi khi hữu ích để tránh tính lặp, nhưng cũng có thể tốn bộ nhớ hoặc đĩa và hạn chế đẩy điều kiện lọc.

Có thể chỉ định:

- MATERIALIZED: yêu cầu tính CTE thành kết quả trung gian.
- NOT MATERIALIZED: cho phép planner inline CTE trong các trường hợp được hỗ trợ.

Không thêm hai từ khóa này theo thói quen. Hãy đo bằng EXPLAIN (ANALYZE, BUFFERS) trước và sau, trên dữ liệu đại diện.

## 7. Hàm cửa sổ (window functions)

Hàm tổng hợp với GROUP BY thường gộp nhiều dòng thành một dòng mỗi nhóm. Hàm cửa sổ tính trên một nhóm dòng liên quan đến dòng hiện tại nhưng vẫn trả về một kết quả cho mỗi dòng đầu vào.

Cấu trúc:

~~~sql
function_name(expression) OVER (
    PARTITION BY group_columns
    ORDER BY sort_columns
    frame_clause
)
~~~

Các phần:

- PARTITION BY chia dữ liệu thành các phân vùng độc lập. Không có PARTITION BY nghĩa là toàn bộ tập kết quả thuộc cùng một phân vùng.
- ORDER BY xác định thứ tự dòng trong mỗi phân vùng.
- Frame clause xác định cửa sổ các dòng tham gia tính toán quanh dòng hiện tại.

Ví dụ, đánh số đơn hàng theo từng khách hàng:

~~~sql
SELECT
    order_id,
    customer_id,
    order_date,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
    ) AS order_sequence
FROM orders
ORDER BY customer_id, order_date, order_id;
~~~

Mỗi khách hàng có bộ đếm riêng. order_id được thêm làm tiêu chí phụ để thứ tự ổn định khi nhiều đơn có cùng order_date.

### 7.1. ROW_NUMBER, RANK và DENSE_RANK

Ba hàm này đều xếp thứ tự nhưng xử lý giá trị bằng nhau khác nhau:

| Giá trị sắp xếp | ROW_NUMBER | RANK | DENSE_RANK |
|---|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 100 | 2 | 1 | 1 |
| 90 | 3 | 3 | 2 |
| 80 | 4 | 4 | 3 |

- ROW_NUMBER luôn cấp số thứ tự riêng cho từng dòng.
- RANK cho các dòng đồng hạng cùng thứ hạng và bỏ qua số thứ hạng tiếp theo.
- DENSE_RANK cho các dòng đồng hạng cùng thứ hạng nhưng không bỏ số.

Xếp hạng khách hàng theo doanh thu:

~~~sql
WITH customer_revenue AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    customer_id,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_revenue_rank
FROM customer_revenue
ORDER BY revenue DESC, customer_id;
~~~

Nếu cần giữ đồng hạng theo doanh thu, không đưa customer_id vào ORDER BY bên trong RANK, vì thêm khóa duy nhất sẽ phá các nhóm đồng hạng. Có thể dùng customer_id ở ORDER BY ngoài để hiển thị ổn định.

### 7.2. Lấy N dòng đầu trong mỗi nhóm

Ví dụ, lấy 3 đơn gần nhất của mỗi khách hàng:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        order_date,
        status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY order_date DESC, order_id DESC
        ) AS row_num
    FROM orders
)
SELECT
    order_id,
    customer_id,
    order_date,
    status
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, order_date DESC, order_id DESC;
~~~

Không thể dùng trực tiếp alias row_num trong WHERE cùng cấp vì WHERE được xử lý trước kết quả SELECT và hàm cửa sổ. Đặt hàm trong CTE hoặc subquery rồi lọc ở truy vấn ngoài.

Nếu yêu cầu là lấy 3 mức doanh thu cao nhất kể cả đồng hạng, hãy dùng RANK hoặc DENSE_RANK theo đúng quy tắc nghiệp vụ thay vì ROW_NUMBER.

### 7.3. LAG và LEAD để so sánh kỳ trước/kỳ sau

LAG lấy giá trị từ dòng đứng trước trong cùng phân vùng; LEAD lấy giá trị từ dòng tiếp theo. Chúng hữu ích để tính tăng trưởng theo tháng:

~~~sql
WITH monthly_revenue AS (
    SELECT
        date_trunc('month', o.order_date) AS month_start,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY date_trunc('month', o.order_date)
),
with_previous AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
    FROM monthly_revenue
)
SELECT
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS revenue_change,
    ROUND(
        100.0 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0),
        2
    ) AS growth_percent
FROM with_previous
ORDER BY month_start;
~~~

NULLIF(previous_revenue, 0) trả NULL khi kỳ trước bằng 0, tránh lỗi chia cho 0. Kỳ đầu tiên cũng có previous_revenue NULL vì không có dòng trước. Có thể dùng COALESCE để hiển thị giá trị mặc định, nhưng không nên tự coi thiếu kỳ trước là doanh thu 0 nếu báo cáo cần phân biệt “không có dữ liệu” với “không phát sinh doanh thu”.

Truy vấn này chỉ có những tháng phát sinh đơn. Nếu cần so sánh liên tục cả tháng không phát sinh, hãy tạo calendar bằng generate_series, LEFT JOIN doanh thu tháng, điền 0 có chủ đích rồi mới áp dụng LAG.

### 7.4. Tổng lũy kế với SUM OVER

Tổng lũy kế cộng giá trị từ đầu phân vùng đến dòng hiện tại:

~~~sql
WITH daily_revenue AS (
    SELECT
        (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sales_day,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    sales_day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY sales_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_revenue
ORDER BY sales_day;
~~~

ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW nêu rõ cửa sổ từ dòng đầu tiên đến dòng hiện tại. Đây là cách viết phù hợp cho tổng lũy kế theo từng dòng.

Nếu có nhiều dòng cùng giá trị ORDER BY, frame mặc định có thể gom các dòng peer vào cùng frame. Hãy thêm khóa sắp xếp duy nhất hoặc chỉ định frame rõ ràng khi cần thứ tự từng dòng.

### 7.5. Tổng theo nhóm nhưng vẫn giữ từng dòng

Có thể dùng SUM OVER để hiển thị doanh thu toàn khách hàng cạnh từng đơn:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total
    FROM order_items
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        COALESCE(i.order_total, 0) AS order_total
    FROM orders AS o
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
)
SELECT
    order_id,
    customer_id,
    order_date,
    SUM(order_total) OVER (
        PARTITION BY customer_id
    ) AS customer_lifetime_total
FROM order_facts
ORDER BY customer_id, order_date, order_id;
~~~

Ở đây giả sử order_facts có một dòng mỗi đơn. Khác với GROUP BY customer_id, hàm cửa sổ không gộp các đơn thành một dòng; tổng của khách hàng được lặp trên mỗi đơn thuộc khách hàng đó.

### 7.6. Trung bình trượt (moving average)

ROWS BETWEEN 6 PRECEDING AND CURRENT ROW tính trên tối đa 7 dòng, không nhất thiết là 7 ngày lịch nếu ngày không có dữ liệu bị thiếu:

~~~sql
WITH daily_revenue AS (
    SELECT
        (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sales_day,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS daily_revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    sales_day,
    daily_revenue,
    AVG(daily_revenue) OVER (
        ORDER BY sales_day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_average_7_rows
FROM daily_revenue;
~~~

Để đúng nghĩa trung bình 7 ngày lịch, trước hết phải tạo calendar đầy đủ, LEFT JOIN doanh thu mỗi ngày và chuyển ngày không có giao dịch thành 0. Khi đó 7 dòng liên tiếp mới tương ứng 7 ngày liên tiếp.

## 8. Kết hợp GROUP BY và window functions

Một mẫu rất thường gặp là tổng hợp trước, sau đó tính thứ hạng hoặc tỷ trọng trên kết quả tổng hợp. PostgreSQL không cho đặt trực tiếp hàm cửa sổ trong GROUP BY cùng cấp; hãy dùng CTE hoặc subquery.

Ví dụ: doanh thu từng danh mục theo tháng, thứ hạng danh mục trong mỗi tháng và tỷ trọng so với toàn tháng:

~~~sql
WITH category_month AS (
    SELECT
        date_trunc('month', o.order_date) AS month_start,
        p.category,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    JOIN products AS p
        ON p.product_id = oi.product_id
    WHERE o.status = 'completed'
    GROUP BY
        date_trunc('month', o.order_date),
        p.category
),
ranked AS (
    SELECT
        month_start,
        category,
        revenue,
        RANK() OVER (
            PARTITION BY month_start
            ORDER BY revenue DESC
        ) AS category_rank,
        SUM(revenue) OVER (
            PARTITION BY month_start
        ) AS month_revenue
    FROM category_month
)
SELECT
    month_start,
    category,
    revenue,
    category_rank,
    ROUND(100.0 * revenue / NULLIF(month_revenue, 0), 2)
        AS revenue_share_percent
FROM ranked
ORDER BY month_start, category_rank, category;
~~~

CTE category_month có một dòng mỗi tháng và danh mục. CTE ranked tính thứ hạng và tổng doanh thu tháng trên các dòng đó. Truy vấn ngoài tính tỷ trọng và định dạng kết quả.

Doanh thu tháng trong ví dụ là tổng doanh thu của những đơn completed có dòng mặt hàng. Nếu cần hiển thị danh mục không phát sinh doanh thu, phải tạo danh sách tháng và danh mục đầy đủ rồi LEFT JOIN số liệu.

## 9. GROUPING SETS, ROLLUP và CUBE

Khi báo cáo cần nhiều cấp tổng hợp, PostgreSQL hỗ trợ tạo nhiều grouping set trong một truy vấn.

Ví dụ, cần tổng doanh thu theo khu vực và kênh, theo riêng khu vực, theo riêng kênh và tổng toàn bộ:

~~~sql
SELECT
    c.region,
    o.channel,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue,
    GROUPING(c.region) AS region_is_total,
    GROUPING(o.channel) AS channel_is_total
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY GROUPING SETS (
    (c.region, o.channel),
    (c.region),
    (o.channel),
    ()
)
ORDER BY
    region_is_total,
    c.region,
    channel_is_total,
    o.channel;
~~~

GROUPING(column) trả 1 khi cột bị bỏ khỏi grouping set hiện tại và 0 khi cột tham gia nhóm. Điều này giúp phân biệt NULL do tổng phụ với NULL thật trong dữ liệu.

ROLLUP(region, channel) tạo tổng chi tiết theo (region, channel), subtotal theo region và grand total. CUBE(region, channel) tạo mọi tổ hợp nhóm, bao gồm subtotal theo từng chiều. Số grouping set tăng nhanh theo số chiều, vì vậy chỉ dùng CUBE khi thực sự cần tất cả tổ hợp.

## 10. Tổ chức truy vấn báo cáo hoàn chỉnh

Một truy vấn báo cáo dễ bảo trì thường có các lớp:

1. Lọc phạm vi dữ liệu và trạng thái nghiệp vụ.
2. Tổng hợp bảng con ở grain phù hợp.
3. Kết hợp dimension như khách hàng, sản phẩm, khu vực.
4. Tổng hợp theo chiều báo cáo.
5. Tính thứ hạng, lũy kế, chênh lệch hoặc tỷ trọng bằng window function.
6. Định dạng và sắp xếp kết quả.

Ví dụ, bảng xếp hạng doanh thu tháng theo từng khu vực:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total
    FROM order_items
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.order_date,
        c.region,
        COALESCE(i.order_total, 0) AS order_total
    FROM orders AS o
    JOIN customers AS c
        ON c.customer_id = o.customer_id
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
      AND o.order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
      AND o.order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
),
monthly_region AS (
    SELECT
        date_trunc('month', order_date) AS month_start,
        region,
        SUM(order_total) AS revenue,
        COUNT(*) AS order_count
    FROM order_facts
    GROUP BY date_trunc('month', order_date), region
),
ranked AS (
    SELECT
        month_start,
        region,
        revenue,
        order_count,
        RANK() OVER (
            PARTITION BY month_start
            ORDER BY revenue DESC
        ) AS region_rank,
        SUM(revenue) OVER (
            PARTITION BY month_start
        ) AS month_total
    FROM monthly_region
)
SELECT
    month_start,
    region,
    revenue,
    order_count,
    region_rank,
    ROUND(100.0 * revenue / NULLIF(month_total, 0), 2)
        AS revenue_share_percent
FROM ranked
ORDER BY month_start, region_rank, region;
~~~

Truy vấn này thể hiện rõ các grain:

- item_totals: một dòng mỗi đơn.
- order_facts: một dòng mỗi đơn hoàn thành.
- monthly_region: một dòng mỗi tháng và khu vực.
- ranked: vẫn một dòng mỗi tháng và khu vực, bổ sung thứ hạng và tỷ trọng.

Nếu cần kết quả chỉ có 3 khu vực đứng đầu mỗi tháng, thêm CTE hoặc truy vấn ngoài lọc region_rank. Dùng RANK <= 3 nếu muốn giữ mọi khu vực đồng hạng ở vị trí thứ ba; dùng ROW_NUMBER <= 3 nếu cần đúng tối đa ba dòng và có tiêu chí phá hòa ổn định.

## 11. Thứ tự xử lý logic của SELECT và các giới hạn thường gặp

Một cách nhớ hữu ích về thứ tự logic khái quát:

~~~text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY
    ↓
HAVING
    ↓
SELECT (aggregate và window expression)
    ↓
DISTINCT
    ↓
ORDER BY
    ↓
LIMIT / OFFSET
~~~

Đây là thứ tự logic để hiểu kết quả, không phải cam kết PostgreSQL thực thi vật lý đúng từng bước như sơ đồ.

Hệ quả quan trọng:

- WHERE không thể lọc kết quả của hàm tổng hợp cùng cấp; dùng HAVING.
- WHERE và HAVING cùng cấp không thể dùng kết quả window function; bọc truy vấn rồi lọc ở ngoài.
- Window function được tính trên tập dòng sau FROM, WHERE, GROUP BY và HAVING.
- ORDER BY cuối quyết định thứ tự hiển thị; ORDER BY trong OVER chỉ quyết định thứ tự tính cửa sổ.
- LIMIT giới hạn kết quả cuối, không giới hạn số dòng được dùng để tính tổng hoặc thứ hạng trước đó.

Ví dụ lọc thứ hạng:

~~~sql
WITH product_revenue AS (
    SELECT
        oi.product_id,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM order_items AS oi
    JOIN orders AS o
        ON o.order_id = oi.order_id
    WHERE o.status = 'completed'
    GROUP BY oi.product_id
),
ranked_products AS (
    SELECT
        product_id,
        revenue,
        ROW_NUMBER() OVER (ORDER BY revenue DESC, product_id) AS rn
    FROM product_revenue
)
SELECT
    product_id,
    revenue,
    rn
FROM ranked_products
WHERE rn <= 10
ORDER BY rn;
~~~

## 12. Kiểm tra tính đúng đắn của số liệu

Trước khi đưa báo cáo vào dashboard hoặc gửi cho người dùng, hãy kiểm tra số liệu ở từng cấp.

### 12.1. Đối chiếu tổng trước và sau JOIN

Nếu tổng hợp payment ở cấp order_id, số tiền toàn tập trước và sau khi nối vào orders phải bằng nhau (nếu không có filter bổ sung làm thay đổi tập đơn):

~~~sql
WITH payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY order_id
)
SELECT
    (SELECT COALESCE(SUM(amount), 0)
     FROM payments
     WHERE status = 'succeeded') AS source_total,
    (SELECT COALESCE(SUM(p.paid_total), 0)
     FROM orders AS o
     LEFT JOIN payment_totals AS p
        ON p.order_id = o.order_id) AS joined_total;
~~~

Nếu có payment tham chiếu order không tồn tại (thường không thể xảy ra khi foreign key được bật và hợp lệ), hoặc lọc đơn theo ngày/trạng thái ở truy vấn sau, hai tập so sánh có thể khác. Hãy làm cho phạm vi đối chiếu giống nhau.

### 12.2. Kiểm tra tính duy nhất của grain

Nếu order_facts được lưu thành view hoặc bảng tạm để kiểm tra riêng, có thể chạy:

~~~sql
SELECT
    order_id,
    COUNT(*) AS rows_per_order
FROM order_facts
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Nếu order_facts phải có một dòng mỗi đơn, truy vấn này phải không trả về dòng nào. Nếu order_facts chỉ là CTE trong một câu lệnh, hãy ghép phép kiểm tra này vào cùng câu lệnh WITH vì phạm vi CTE kết thúc sau câu lệnh đó.

### 12.3. Kiểm tra NULL và dữ liệu thiếu

Đặt câu hỏi:

- Khách hàng chưa có khu vực được đưa vào nhóm NULL hay bị loại?
- Đơn không có mặt hàng có cần xuất hiện không?
- Payment pending, failed, refunded có được tính không?
- Giá trị NULL có ý nghĩa là chưa biết, không áp dụng hay bằng 0?
- Ngày không có giao dịch có cần hiển thị hay không?

Không tự động chuyển mọi NULL thành 0. NULL thường biểu thị thiếu hoặc không xác định; 0 là một giá trị thực. Chỉ dùng COALESCE khi quy tắc báo cáo định nghĩa rõ cách diễn giải.

### 12.4. Kiểm tra các trường hợp biên

Thử báo cáo với:

- Không có dòng dữ liệu trong kỳ.
- Chỉ có một khách hàng hoặc một đơn.
- Một đơn có nhiều mặt hàng và nhiều payment.
- Hai mặt hàng hoặc payment có giá trị bằng nhau.
- Một tháng không phát sinh giao dịch.
- Một khách hàng có nhiều đơn cùng timestamp.
- Giao dịch đúng thời điểm bắt đầu và đúng thời điểm kết thúc kỳ.
- Dữ liệu có NULL trong dimension như region hoặc category.

Các trường hợp này thường phát hiện lỗi JOIN, lỗi đếm, sai thứ hạng hoặc thiếu ngày trong báo cáo.

## 13. Cải thiện hiệu năng báo cáo

Một truy vấn đúng nhưng chậm vẫn cần được tối ưu. Bắt đầu bằng việc xem kế hoạch thực thi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

EXPLAIN ANALYZE thực sự chạy câu SQL. Với truy vấn báo cáo lớn, cần cân nhắc tải và thời gian trước khi chạy trên production. BUFFERS cho biết hoạt động đọc/cache của PostgreSQL ở các node kế hoạch; nó không thay thế metrics ở tầng storage.

Một số hướng tối ưu:

### 13.1. Tạo chỉ mục theo điều kiện lọc và khóa JOIN

Ví dụ:

~~~sql
CREATE INDEX idx_orders_order_date
    ON orders (order_date);

CREATE INDEX idx_orders_customer_date
    ON orders (customer_id, order_date);

CREATE INDEX idx_order_items_order
    ON order_items (order_id);

CREATE INDEX idx_payments_success_order
    ON payments (order_id)
    WHERE status = 'succeeded';
~~~

Một số chỉ mục đã có thể được tạo bởi PRIMARY KEY hoặc UNIQUE constraint. Ví dụ order_items có primary key (order_id, product_id), nên đã có B-tree index bắt đầu bằng order_id; chỉ mục idx_order_items_order có thể dư thừa trong schema mẫu và không cần tạo thêm. Luôn kiểm tra chỉ mục hiện có trước khi bổ sung.

Chỉ mục một phần trên payments có thể hữu ích khi báo cáo thường xuyên chỉ đọc payment thành công. Điều kiện truy vấn cần tương thích với predicate của index để planner sử dụng được.

### 13.2. Lọc sớm và chỉ lấy cột cần thiết

Đưa điều kiện thời gian, trạng thái và tenant vào bước đầu phù hợp để giảm lượng dòng đi qua JOIN và aggregate. Không dùng SELECT * cho báo cáo lớn nếu chỉ cần vài cột.

Tuy nhiên, khi dùng LEFT JOIN, hãy đặt điều kiện đúng vị trí để không vô tình biến phép nối thành INNER JOIN. Tối ưu bằng cách đẩy filter cần giữ ngữ nghĩa sang ON hoặc CTE phía phải khi phù hợp.

### 13.3. Không lạm dụng DISTINCT

DISTINCT có chi phí sort hoặc hash và có thể che giấu lỗi nhân bản do JOIN sai. Trước khi thêm DISTINCT, xác định vì sao có dòng trùng. Nếu mục tiêu là một dòng mỗi order_id, hãy tổng hợp hoặc chọn một dòng bằng quy tắc rõ ràng.

### 13.4. Kiểm tra thống kê và kế hoạch

ANALYZE cập nhật thống kê để planner ước lượng số dòng và chọn join strategy. Bảng thay đổi nhiều có thể cần thống kê mới. Hãy xem estimated rows và actual rows trong EXPLAIN ANALYZE; chênh lệch lớn có thể dẫn đến kế hoạch JOIN hoặc aggregate không phù hợp.

Không mặc định hash join luôn nhanh hơn nested loop hoặc merge join. Lựa chọn phụ thuộc kích thước tập dữ liệu, chỉ mục, thứ tự và phân bố giá trị.

### 13.5. Tránh tạo quá nhiều chỉ mục

Mỗi index chiếm dung lượng và làm tăng chi phí INSERT, UPDATE, DELETE, VACUUM và backup. Chỉ tạo index dựa trên truy vấn thường chạy và số liệu thực tế; kiểm tra mức sử dụng trước khi thêm.

## 14. Quy trình thực hành đề xuất

Khi nhận một yêu cầu báo cáo, có thể làm theo trình tự:

1. Viết định nghĩa nghiệp vụ của từng chỉ số: doanh thu, tiền thu, số đơn, khách hàng hoạt động.
2. Xác định grain của kết quả cuối: một dòng mỗi ngày, mỗi tháng/khu vực, mỗi khách hàng hay mỗi sản phẩm.
3. Liệt kê bảng nguồn, khóa JOIN và quan hệ một-một/một-nhiều.
4. Xác định các bảng con phải tổng hợp trước để tránh fan-out.
5. Viết truy vấn JOIN và kiểm tra số dòng sau từng bước.
6. Thêm GROUP BY và các hàm tổng hợp; xác định rõ cách xử lý NULL.
7. Dùng CTE đặt tên cho từng bước nghiệp vụ.
8. Thêm window functions sau khi đã có tập dữ liệu đúng grain.
9. Kiểm tra kỳ thời gian, múi giờ, thứ hạng đồng hạng và ngày không có dữ liệu.
10. Đối chiếu tổng số liệu với truy vấn nguồn hoặc báo cáo đã được xác nhận.
11. Chạy EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp và tối ưu dựa trên số liệu.
12. Lưu lại định nghĩa chỉ số và ví dụ dữ liệu để người khác có thể tái kiểm tra.

## 15. Bài tập thực hành

Dùng schema bán hàng ở đầu bài để tự viết các truy vấn sau. Mỗi bài nên xác định grain trước khi viết SQL.

**Bài 1 — Đơn hàng theo khách hàng**

Liệt kê mỗi khách hàng, số đơn đã hoàn thành và tổng giá trị hàng hóa. Khách hàng chưa có đơn hoàn thành vẫn phải xuất hiện với số đơn bằng 0.

Gợi ý: bắt đầu từ customers, LEFT JOIN tập đơn đã tổng hợp hoặc dùng CTE tổng hợp orders và order_items ở grain customer_id. Đặt điều kiện status sao cho không loại khách hàng không có đơn.

**Bài 2 — Kênh bán theo tháng**

Tính số đơn, doanh thu hàng hóa và số khách hàng duy nhất theo tháng và channel. Chỉ tính đơn completed trong năm báo cáo.

Gợi ý: tổng hợp mặt hàng ở cấp order_id trước khi nối, sau đó nhóm theo tháng và channel.

**Bài 3 — Đối chiếu doanh thu và tiền đã thu**

Tính order_total, paid_total và phần chênh lệch cho từng đơn. Đơn chưa có payment vẫn phải có trong kết quả.

Gợi ý: tạo item_totals và payment_totals riêng, mỗi CTE một dòng mỗi order_id.

**Bài 4 — Top 5 sản phẩm theo danh mục**

Tính doanh thu mỗi sản phẩm trong từng category, sau đó xếp hạng sản phẩm theo doanh thu trong danh mục. Hiển thị 5 sản phẩm đầu mỗi danh mục.

Gợi ý: GROUP BY category và product_id trong CTE, rồi dùng ROW_NUMBER hoặc RANK ở truy vấn ngoài.

**Bài 5 — So sánh doanh thu tháng trước**

Tính doanh thu từng tháng, doanh thu tháng trước và tỷ lệ tăng trưởng phần trăm. Xử lý an toàn trường hợp tháng trước có doanh thu bằng 0 hoặc không có dữ liệu.

Gợi ý: tổng hợp theo tháng, tạo calendar nếu cần tháng trống, rồi dùng LAG và NULLIF.

**Bài 6 — Tổng lũy kế theo khu vực**

Tính doanh thu từng ngày và tổng lũy kế trong mỗi khu vực. Ngày không có đơn phải hiển thị 0 và không làm đứt chuỗi ngày.

Gợi ý: tạo calendar ngày, danh sách khu vực, tạo tổ hợp ngày × khu vực, LEFT JOIN daily aggregate rồi dùng SUM OVER PARTITION BY region ORDER BY day với frame ROWS rõ ràng.

**Bài 7 — Kiểm tra lỗi fan-out**

Tạo một đơn có ít nhất hai dòng mặt hàng và hai lần thanh toán. So sánh tổng doanh thu và tổng payment khi JOIN trực tiếp với kết quả tổng hợp từng bảng con trước khi JOIN.

Gợi ý: đếm số dòng kết quả ở cấp order_id và giải thích vì sao số dòng bằng tích số dòng của hai bảng con.

## Kết luận

JOIN kết hợp dữ liệu liên quan; GROUP BY và các hàm tổng hợp tính chỉ số theo nhóm; CTE chia báo cáo thành các bước có tên; window functions bổ sung thứ hạng, so sánh kỳ, tỷ trọng và tổng lũy kế mà không làm mất từng dòng.

Hãy luôn xác định grain trước khi nối bảng. Tổng hợp các nhánh một-nhiều trước khi kết hợp nếu chỉ số thuộc cấp cao hơn, dùng điều kiện JOIN đúng vị trí, xử lý NULL và thời gian theo quy tắc nghiệp vụ, rồi mới thêm window functions. Cuối cùng, kiểm tra số dòng và đối chiếu tổng số liệu để bảo đảm báo cáo đúng trước khi tối ưu hiệu năng.
