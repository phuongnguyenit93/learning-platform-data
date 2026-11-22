# Kiểm soát nhân bản hàng khi nối nhiều quan hệ trong PostgreSQL

Một câu `JOIN` có thể đúng cú pháp, trả kết quả nhanh nhưng **sai số tiền hoặc số lượng**. Ví dụ một đơn hàng có hai dòng sản phẩm và hai lần thanh toán. Khi nối cả hai bảng con với bảng đơn hàng, PostgreSQL tạo bốn tổ hợp dòng sản phẩm–thanh toán. Nếu sau đó dùng `SUM` trực tiếp, tiền hàng và tiền thanh toán đều có thể bị tính hai lần.

Bài học thuộc chương **Kết hợp dữ liệu** của module **Database Engine Relational PostgreSQL**. Mục tiêu là hiểu chính xác vì sao các phép nối tạo nhiều hàng, biết khi nào đó là hành vi hợp lệ, và chọn chiến lược SQL phù hợp để giữ đúng **độ hạt của dữ liệu (grain)**.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu thực sự trùng với việc hàng cha được lặp hợp lệ trong quan hệ một-nhiều.
- Dự đoán số hàng khi nối nhiều bảng một-nhiều hoặc nhiều-nhiều.
- Phát hiện fanout làm sai `COUNT`, `SUM` và phép tổng hợp JSON.
- Dùng `EXISTS` khi chỉ kiểm tra có/không có hàng liên quan.
- Tổng hợp các bảng con riêng biệt trước khi nối về grain cha.
- Chọn một hàng con có tiêu chí rõ ràng bằng `DISTINCT ON`, `ROW_NUMBER()` hoặc `LATERAL`.
- Kiểm tra khóa ghép, điều kiện `LEFT JOIN`, ràng buộc `UNIQUE`, phiên bản dữ liệu theo thời gian và dữ liệu đầu vào trùng khóa.
- Đối chiếu số liệu với bảng gốc và quan sát `EXPLAIN` để hỗ trợ phân tích.

## 1. “Nhân bản hàng” có nhất thiết là lỗi?

Giả sử khách hàng số 1 có hai đơn hàng:

~~~text
customer                    sales_order
customer_id | name          order_id | customer_id
------------+--------       ---------+------------
1           | An            1001     | 1
                            1002     | 1
~~~

Một phép nối:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id;
~~~

cho hai hàng:

~~~text
1 | An | 1001
1 | An | 1002
~~~

Khách An xuất hiện hai lần, nhưng hai hàng đại diện cho **hai đơn khác nhau**. Đó là dữ liệu chính xác nếu ta muốn danh sách đơn kèm tên khách.

Nếu bỏ cột `order_id` khỏi `SELECT`, hai hàng có thể trông giống hệt nhau. Việc những giá trị hiển thị trùng không chứng minh PostgreSQL đã nối sai.

**Câu hỏi quan trọng nhất là: một hàng kết quả cần đại diện cho đối tượng gì?** Nếu cần một hàng mỗi khách, không thể lấy nguyên kết quả một-nhiều rồi mặc định nó sẽ có một hàng cho mỗi khách.

## 2. Độ hạt dữ liệu (grain)

Grain mô tả ý nghĩa và mức chi tiết của một hàng.

| Tập dữ liệu | Grain thông thường |
|---|---|
| `customer` | Một khách hàng |
| `sales_order` | Một đơn hàng |
| `order_item` | Một dòng sản phẩm trong đơn |
| `payment` | Một lần thanh toán |
| `shipment` | Một chuyến giao |
| Báo cáo tổng đơn | Một hàng trên mỗi `order_id` |
| Báo cáo tổng khách | Một hàng trên mỗi `customer_id` |
| Danh sách item của đơn | Một hàng trên mỗi `item_id` |
| Ghép mọi item với mọi payment của đơn | Một hàng trên mỗi cặp item–payment |

Grain không chỉ là cách trình bày. Nó quyết định **có được phép cộng một số đo hay không**. Tổng tiền của dòng item có grain `item_id`; tổng số tiền đã trả có grain `payment_id`. Nếu một query biến một item thành nhiều tổ hợp, không thể coi mỗi tổ hợp là một item mới khi tính tiền.

Trước khi viết query, hãy phát biểu một câu như:

> “Tôi cần đúng một hàng cho mỗi đơn, gồm tổng tiền item và tổng payment của đơn đó.”

Tiếp theo, kiểm tra mỗi nguồn nối có duy nhất theo `order_id` hay không.

## 3. Cardinality của quan hệ

| Quan hệ | Ví dụ | Hệ quả đối với JOIN |
|---|---|---|
| Một-một (1:1) | Mỗi đơn có tối đa một bản ghi summary | Không tăng hàng nếu phía phải duy nhất |
| Một-nhiều (1:N) | Một đơn có nhiều item | Một đơn lặp theo số item |
| Nhiều-một (N:1) | Nhiều đơn thuộc một khách | Mỗi đơn khớp tối đa một khách nếu khóa khách duy nhất |
| Nhiều-nhiều (N:M) | Người dùng tham gia nhiều nhóm | Có nhiều cặp người–nhóm |
| Không khớp | Đơn chưa có payment | Bị loại bởi INNER JOIN, được giữ với NULL bởi LEFT JOIN |

Một **foreign key** từ item tới order chỉ bảo đảm item tham chiếu một order hợp lệ. Nó **không bảo đảm mỗi order chỉ có một item**. Cần `UNIQUE` hoặc `PRIMARY KEY` trên khóa phía con nếu nghiệp vụ thực sự yêu cầu một-một.

## 4. Tạo dữ liệu thực hành PostgreSQL

Các ví dụ sau dùng schema `join_lab`. **Chỉ tạo trên database học tập riêng**. Nếu đã có schema cùng tên, hãy dùng môi trường test mới hoặc quy trình quản lý schema; không xóa nhầm dữ liệu thật.

~~~sql
CREATE SCHEMA join_lab;

CREATE TABLE join_lab.customer (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL
);

CREATE TABLE join_lab.sales_order (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES join_lab.customer(customer_id),
    placed_on DATE NOT NULL
);

CREATE TABLE join_lab.order_item (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES join_lab.sales_order(order_id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE join_lab.payment (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES join_lab.sales_order(order_id),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    paid_on DATE NOT NULL
);

CREATE TABLE join_lab.shipment (
    shipment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES join_lab.sales_order(order_id),
    tracking_code TEXT NOT NULL UNIQUE
);
~~~

Nạp dữ liệu cố định:

~~~sql
INSERT INTO join_lab.customer
    (customer_id, full_name)
VALUES
    (1, 'Nguyễn An'),
    (2, 'Trần Bình'),
    (3, 'Lê Chi');

INSERT INTO join_lab.sales_order
    (order_id, customer_id, placed_on)
VALUES
    (1001, 1, DATE '2026-02-01'),
    (1002, 1, DATE '2026-02-02'),
    (1003, 2, DATE '2026-02-03'),
    (1004, 3, DATE '2026-02-04');

INSERT INTO join_lab.order_item
    (item_id, order_id, sku, quantity, unit_price)
VALUES
    (11, 1001, 'BOOK', 2, 100.00),
    (12, 1001, 'MOUSE', 1, 50.00),
    (13, 1002, 'KEYBOARD', 1, 200.00),
    (14, 1003, 'CABLE', 1, 90.00);

INSERT INTO join_lab.payment
    (payment_id, order_id, amount, paid_on)
VALUES
    (21, 1001, 120.00, DATE '2026-02-01'),
    (22, 1001, 130.00, DATE '2026-02-02'),
    (23, 1002, 200.00, DATE '2026-02-02'),
    (24, 1003, 90.00, DATE '2026-02-03');

INSERT INTO join_lab.shipment
    (shipment_id, order_id, tracking_code)
VALUES
    (31, 1001, 'SHIP-A'),
    (32, 1001, 'SHIP-B'),
    (33, 1002, 'SHIP-C');
~~~

Trạng thái dự kiến:

| order_id | Số item | Tổng tiền hàng | Số payment | Tổng thanh toán | Số shipment |
|---:|---:|---:|---:|---:|---:|
| 1001 | 2 | 250.00 | 2 | 250.00 | 2 |
| 1002 | 1 | 200.00 | 1 | 200.00 | 1 |
| 1003 | 1 | 90.00 | 1 | 90.00 | 0 |
| 1004 | 0 | 0.00 | 0 | 0.00 | 0 |

Đơn 1001 có nhiều hàng trên cả ba quan hệ con. Đơn 1004 cố tình không có hàng con để minh họa `LEFT JOIN` và `NULL`.

## 5. Một JOIN một-nhiều là hợp lệ khi grain là hàng con

~~~sql
SELECT
    o.order_id,
    i.item_id,
    i.sku,
    i.quantity * i.unit_price AS line_total
FROM join_lab.sales_order AS o
JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
~~~

Kết quả:

| order_id | item_id | sku | line_total |
|---:|---:|---|---:|
| 1001 | 11 | BOOK | 200.00 |
| 1001 | 12 | MOUSE | 50.00 |
| 1002 | 13 | KEYBOARD | 200.00 |
| 1003 | 14 | CABLE | 90.00 |

Bốn hàng kết quả là đúng vì có bốn item. Đơn 1001 xuất hiện hai lần là đúng. Đơn 1004 bị loại do `INNER JOIN` không tìm thấy item.

Nếu cần giữ cả đơn không có item:

~~~sql
SELECT
    o.order_id,
    i.item_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
~~~

Kết quả có **năm hàng**: hai hàng cho 1001 và mỗi đơn còn lại một hàng; với 1004, `item_id` bằng `NULL`.

**LEFT JOIN không bảo đảm một hàng mỗi hàng bên trái.** Nó chỉ bảo đảm không loại hàng bên trái khi không có hàng bên phải phù hợp.

## 6. Bẫy phổ biến: hai bảng con được nối với cùng bảng cha

Xem truy vấn:

~~~sql
SELECT
    o.order_id,
    i.item_id,
    i.quantity * i.unit_price AS line_total,
    p.payment_id,
    p.amount AS payment_amount
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY i.item_id, p.payment_id;
~~~

Kết quả:

| order_id | item_id | line_total | payment_id | payment_amount |
|---:|---:|---:|---:|---:|
| 1001 | 11 | 200.00 | 21 | 120.00 |
| 1001 | 11 | 200.00 | 22 | 130.00 |
| 1001 | 12 | 50.00 | 21 | 120.00 |
| 1001 | 12 | 50.00 | 22 | 130.00 |

Hình dung:

~~~text
            order 1001
             /      \
       2 item      2 payment
          \          /
           2 x 2 = 4 tổ hợp

 item 11 + payment 21
 item 11 + payment 22
 item 12 + payment 21
 item 12 + payment 22
~~~

PostgreSQL không tạo thêm item hay payment trong bảng gốc. Nó chỉ trả về các **tổ hợp thỏa điều kiện JOIN**. Vì item và payment không có quan hệ trực tiếp trong câu này, mỗi item được ghép với mọi payment cùng order.

Đây là hiện tượng **join fanout**. Trong mô hình báo cáo, lỗi kết hợp nhiều bảng sự kiện một-nhiều quanh cùng một bảng chiều còn được gọi là **chasm trap**.

## 7. Dự đoán số hàng khi có nhiều quan hệ con

Với một đơn có:

- `n_i` item;
- `n_p` payment;
- `n_s` shipment;

nếu nối ba bảng con độc lập qua `order_id` mà không có filter phụ, `INNER JOIN` tạo:

\[
n_i \times n_p \times n_s
\]

hàng cho đơn đó.

Với chuỗi `LEFT JOIN` như ví dụ và các quan hệ con độc lập, số hàng là:

\[
\max(1,n_i)\times\max(1,n_p)\times\max(1,n_s)
\]

Đơn 1001:

- Item × payment = 2 × 2 = **4** hàng.
- Item × payment × shipment = 2 × 2 × 2 = **8** hàng.

Đơn 1004 có 0 item, 0 payment và 0 shipment, nhưng `LEFT JOIN` vẫn trả **một hàng có các trường con NULL**.

Công thức trên mô tả một dạng cấu trúc JOIN cụ thể. Nếu có điều kiện nối trực tiếp giữa các bảng con, điều kiện lọc hoặc ràng buộc khác, số hàng phải được tính theo quan hệ thực tế.

## 8. Một ví dụ SUM sai dù GROUP BY đúng cú pháp

~~~sql
SELECT
    o.order_id,
    COALESCE(
        SUM(i.quantity * i.unit_price), 0
    ) AS item_total,
    COALESCE(
        SUM(p.amount), 0
    ) AS payment_total
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Với đơn 1001:

~~~text
item_total    = 200 + 200 + 50 + 50 = 500
payment_total = 120 + 130 + 120 + 130 = 500
~~~

Tổng đúng phải là **250.00** cho mỗi phía.

`GROUP BY o.order_id` chỉ gom hàng **sau khi JOIN đã nhân**. Nó không biết hai lần xuất hiện của item 11 là cùng một item gốc, nên không tự loại phần tiền bị lặp.

Đáng chú ý: đơn 1002 và 1003 chỉ có một item và một payment, nên kết quả có thể tình cờ đúng. Lỗi có thể chỉ xuất hiện sau khi một khách thanh toán nhiều lần.

## 9. Vì sao SUM(DISTINCT amount) không sửa đúng lỗi?

Một cách chữa sai phổ biến:

~~~sql
-- Không phải cách sửa fanout đáng tin:
SUM(DISTINCT i.quantity * i.unit_price)
~~~

Nếu một đơn có hai item khác nhau, mỗi item đều có số tiền 100.00:

~~~text
item_id | line_total
--------+-----------
11      | 100.00
12      | 100.00
~~~

Tổng đúng là **200.00**. Nhưng `SUM(DISTINCT line_total)` chỉ cộng giá trị 100.00 một lần, trả **100.00**.

`DISTINCT` trên biểu thức tiền chỉ xét **giá trị**, không xét hai item có `item_id` khác nhau. Tương tự, hai payment khác nhau có thể cùng số tiền.

**Quy tắc:** không dùng `SUM(DISTINCT amount)` để thay cho việc kiểm soát grain. Hãy tổng hợp theo đúng thực thể/sự kiện trước khi nối.

## 10. Giải pháp chính: tổng hợp từng quan hệ con trước JOIN

Nếu báo cáo cần **một hàng mỗi đơn**, hãy biến mỗi bảng con thành **tối đa một hàng cho mỗi `order_id`**.

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS item_total
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS payment_total
    FROM join_lab.payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.payment_total, 0) AS payment_total
FROM join_lab.sales_order AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Kết quả kỳ vọng:

| order_id | item_count | item_total | payment_count | payment_total |
|---:|---:|---:|---:|---:|
| 1001 | 2 | 250.00 | 2 | 250.00 |
| 1002 | 1 | 200.00 | 1 | 200.00 |
| 1003 | 1 | 90.00 | 1 | 90.00 |
| 1004 | 0 | 0.00 | 0 | 0.00 |

Mô hình:

~~~text
order_item (n item/order)
          |
       GROUP BY order_id
          v
item_totals (1 row/order) -----+
                               |
                               v
sales_order (1 row/order) ---> kết quả 1 row/order
                               ^
                               |
payment_totals (1 row/order) -+
          ^
       GROUP BY order_id
          |
payment (n payment/order)
~~~

Ý nghĩa chính:

1. `item_totals` chỉ cộng dòng item, không nhìn thấy payment.
2. `payment_totals` chỉ cộng thanh toán, không nhìn thấy item.
3. Mỗi CTE sau `GROUP BY order_id` có tối đa một hàng theo khóa.
4. `LEFT JOIN` giữ đơn không có con.
5. `COALESCE` biến tổng/counter NULL của đơn không có con thành 0 theo yêu cầu báo cáo.

### 10.1. CTE không tự là bảng vật lý

`WITH item_totals AS (...)` giúp biểu diễn logic rõ, nhưng PostgreSQL có thể inline/biến đổi một số CTE khi lập kế hoạch. Điều bảo đảm grain ở đây là **`GROUP BY order_id`**, không phải việc dùng từ khóa `WITH`.

## 11. Correlated subquery: mỗi số đo một nguồn riêng

Một cách khác tránh tích item × payment:

~~~sql
SELECT
    o.order_id,
    COALESCE(
        (
            SELECT SUM(i.quantity * i.unit_price)
            FROM join_lab.order_item AS i
            WHERE i.order_id = o.order_id
        ), 0
    ) AS item_total,
    COALESCE(
        (
            SELECT SUM(p.amount)
            FROM join_lab.payment AS p
            WHERE p.order_id = o.order_id
        ), 0
    ) AS payment_total
FROM join_lab.sales_order AS o
ORDER BY o.order_id;
~~~

Mỗi phép tính chỉ xem bảng con phù hợp với **một order**.

Cách này thường dễ đọc khi chỉ có vài cột số đo và tập order đã được lọc nhỏ. Tuy nhiên trên báo cáo toàn hệ thống, hiệu năng của correlated subquery so với preaggregation còn tùy kế hoạch, index và kích thước dữ liệu.

Không mặc định một cú pháp luôn nhanh hơn. Hãy đảm bảo **đúng kết quả** rồi dùng `EXPLAIN` để đo.

## 12. LEFT JOIN LATERAL: tổng hợp riêng cho từng hàng cha

`LATERAL` cho phép subquery trong `FROM` dùng cột của hàng nguồn đứng trước:

~~~sql
SELECT
    o.order_id,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.payment_total, 0) AS payment_total
FROM join_lab.sales_order AS o
LEFT JOIN LATERAL (
    SELECT
        SUM(oi.quantity * oi.unit_price) AS item_total
    FROM join_lab.order_item AS oi
    WHERE oi.order_id = o.order_id
) AS i ON TRUE
LEFT JOIN LATERAL (
    SELECT SUM(pay.amount) AS payment_total
    FROM join_lab.payment AS pay
    WHERE pay.order_id = o.order_id
) AS p ON TRUE
ORDER BY o.order_id;
~~~

Các subquery aggregate **không GROUP BY** ở trên luôn trả một hàng kết quả tổng hợp, kể cả khi không có hàng đầu vào (khi đó `SUM` là NULL). Vì vậy mỗi LATERAL không làm nhân số hàng của order.

`LATERAL` còn hữu ích khi muốn chọn **một** hàng con mới nhất, hoặc **một số lượng giới hạn** hàng con theo một tiêu chí cụ thể.

## 13. Khi chỉ cần biết có hàng con, hãy dùng EXISTS

Yêu cầu:

> “Liệt kê đơn nào có ít nhất một payment, mỗi đơn xuất hiện một lần.”

Dùng `JOIN` trực tiếp:

~~~sql
SELECT o.order_id
FROM join_lab.sales_order AS o
JOIN join_lab.payment AS p
    ON p.order_id = o.order_id;
~~~

đưa đơn 1001 ra **hai hàng** vì có hai payment.

Một cách đúng về grain:

~~~sql
SELECT o.order_id
FROM join_lab.sales_order AS o
WHERE EXISTS (
    SELECT 1
    FROM join_lab.payment AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
~~~

Kết quả: 1001, 1002, 1003, mỗi đơn một lần.

`EXISTS` chỉ kiểm tra **có ít nhất một hàng phù hợp**, không tạo một hàng kết quả cho mỗi payment. PostgreSQL có thể xử lý nó bằng chiến lược **semi join** trong những kế hoạch thích hợp.

### 13.1. NOT EXISTS: tìm đơn chưa có thanh toán

~~~sql
SELECT o.order_id
FROM join_lab.sales_order AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM join_lab.payment AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
~~~

Kết quả: đơn **1004**.

Có thể dùng `LEFT JOIN ... WHERE p.payment_id IS NULL` khi `payment_id` là khóa không NULL. Nhưng `NOT EXISTS` thường mô tả trực tiếp bài toán **không có hàng liên quan** và tránh một số bẫy `NOT IN` khi subquery chứa NULL.

## 14. DISTINCT: đúng khi thật sự cần tập khóa không trùng

~~~sql
SELECT DISTINCT o.order_id
FROM join_lab.sales_order AS o
JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Câu này trả một bản sao của mỗi `order_id` có payment, vì chỉ chọn cột order_id.

Tuy nhiên:

~~~sql
SELECT DISTINCT
    o.order_id,
    p.payment_id
FROM join_lab.sales_order AS o
JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 1001;
~~~

vẫn có **hai hàng**, vì cặp `(order_id, payment_id)` khác nhau.

**DISTINCT không sửa các số đo đã tính sai trong JOIN.** Nó chỉ loại hàng có các biểu thức được chọn bằng nhau theo semantics của PostgreSQL.

Nếu chỉ cần “có tồn tại payment”, `EXISTS` thường rõ ý hơn. Nếu cần tổng thanh toán, phải cộng từ các payment đúng grain.

## 15. DISTINCT ON: chọn một hàng đại diện có tiêu chí

PostgreSQL có `DISTINCT ON` để chọn **hàng đầu tiên theo thứ tự đã định** trong mỗi nhóm.

Lấy payment mới nhất cho từng đơn:

~~~sql
SELECT DISTINCT ON (p.order_id)
    p.order_id,
    p.payment_id,
    p.amount,
    p.paid_on
FROM join_lab.payment AS p
ORDER BY
    p.order_id,
    p.paid_on DESC,
    p.payment_id DESC;
~~~

Với đơn 1001, payment 22 được chọn vì ngày thanh toán mới hơn. Nếu nhiều payment cùng ngày, `payment_id DESC` là tie-breaker làm kết quả xác định hơn.

**Lưu ý:** “payment mới nhất” và “tổng mọi payment” là hai yêu cầu khác nhau. Dùng `DISTINCT ON` trong báo cáo tổng thanh toán sẽ bỏ các payment hợp lệ khác.

### 15.1. Chọn một hàng trước khi JOIN

Có thể tạo CTE chỉ gồm tối đa một payment mỗi order:

~~~sql
WITH latest_payment AS (
    SELECT DISTINCT ON (p.order_id)
        p.order_id,
        p.payment_id,
        p.amount,
        p.paid_on
    FROM join_lab.payment AS p
    ORDER BY p.order_id, p.paid_on DESC, p.payment_id DESC
)
SELECT
    o.order_id,
    p.payment_id,
    p.amount
FROM join_lab.sales_order AS o
LEFT JOIN latest_payment AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Kết quả vẫn có một hàng cho mỗi đơn, bao gồm 1004 với trường payment NULL.

## 16. ROW_NUMBER(): một cách chọn hàng theo nhóm

~~~sql
WITH ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.order_id
            ORDER BY p.paid_on DESC, p.payment_id DESC
        ) AS rn
    FROM join_lab.payment AS p
)
SELECT
    o.order_id,
    p.payment_id,
    p.amount
FROM join_lab.sales_order AS o
LEFT JOIN ranked AS p
    ON p.order_id = o.order_id
   AND p.rn = 1
ORDER BY o.order_id;
~~~

`ROW_NUMBER()` đánh số trong mỗi nhóm order. `rn=1` chọn một hàng; nếu chọn `rn <= 2` thì lại có thể tạo hai hàng cho một đơn theo chủ đích.

Điều kiện `rn=1` ở `ON` giữ nguyên semantics của `LEFT JOIN`. Nếu đặt vào `WHERE p.rn=1`, các đơn không có payment có thể bị loại.

## 17. LATERAL với ORDER BY LIMIT 1

Cùng mục tiêu “payment mới nhất”:

~~~sql
SELECT
    o.order_id,
    p.payment_id,
    p.amount
FROM join_lab.sales_order AS o
LEFT JOIN LATERAL (
    SELECT
        payment_id,
        amount,
        paid_on
    FROM join_lab.payment AS p
    WHERE p.order_id = o.order_id
    ORDER BY paid_on DESC, payment_id DESC
    LIMIT 1
) AS p ON TRUE
ORDER BY o.order_id;
~~~

`LIMIT 1` giới hạn số payment được nối cho mỗi đơn. Nếu có index phù hợp theo `(order_id, paid_on DESC, payment_id DESC)`, một kế hoạch tra cứu từng đơn có thể hiệu quả, đặc biệt khi số đơn đầu vào nhỏ.

Không dùng `LIMIT 1` để **che** một vi phạm tính duy nhất mà nghiệp vụ không cho phép. Nếu bảng “hồ sơ hiện hành” được yêu cầu có đúng tối đa một hàng mỗi khách, nên có ràng buộc kiểm soát điều đó.

## 18. LEFT JOIN và WHERE có thể đổi ngữ nghĩa

~~~sql
SELECT o.order_id, p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
WHERE p.amount > 0;
~~~

Đơn không có payment có `p.amount = NULL` và bị loại do điều kiện `WHERE` không là TRUE.

Nếu muốn **giữ mọi đơn** nhưng chỉ nối những payment dương:

~~~sql
SELECT o.order_id, p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
   AND p.amount > 0
ORDER BY o.order_id, p.payment_id;
~~~

Cách này giữ đơn 1004 với payment_id NULL. Tuy nhiên, nếu một đơn có nhiều payment dương, kết quả **vẫn có nhiều hàng**, không tự chuyển thành một hàng mỗi order.

Nếu cần một hàng mỗi đơn, vẫn phải dùng tổng hợp hoặc một phép kiểm tra tồn tại.

## 19. COUNT(*) và COUNT(child_id) sau LEFT JOIN

~~~sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(i.item_id) AS item_count
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Với đơn 1004:

- `COUNT(*) = 1` vì `LEFT JOIN` tạo một hàng giữ order.
- `COUNT(i.item_id) = 0` vì cột item_id NULL ở hàng không khớp.

Với đơn 1001, riêng phép nối item cho `COUNT(i.item_id) = 2`.

Nhưng nếu nối thêm payment, mỗi item lặp hai lần và `COUNT(i.item_id)` trở thành 4. Khi đó `COUNT(DISTINCT i.item_id)` vẫn đếm đúng **2 item riêng biệt**, nhưng phép `SUM` tiền hàng trên cùng kết quả vẫn có thể sai.

### 19.1. COUNT(DISTINCT) không tự thay cho preaggregation

Nếu mục tiêu chỉ là đếm item khác nhau theo item_id, `COUNT(DISTINCT i.item_id)` có nghĩa đúng. Nhưng `COUNT(DISTINCT i.sku)` có thể sai nếu hai dòng item khác nhau cùng SKU.

Và một query có `COUNT(DISTINCT item_id)` đúng không đảm bảo `SUM(payment.amount)` trong query đó đúng.

## 20. Tổng hợp ba bảng con cùng lúc

~~~sql
WITH
item_counts AS (
    SELECT order_id, COUNT(*) AS item_count
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_counts AS (
    SELECT order_id, COUNT(*) AS payment_count
    FROM join_lab.payment
    GROUP BY order_id
),
shipment_counts AS (
    SELECT order_id, COUNT(*) AS shipment_count
    FROM join_lab.shipment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(s.shipment_count, 0) AS shipment_count
FROM join_lab.sales_order AS o
LEFT JOIN item_counts AS i ON i.order_id = o.order_id
LEFT JOIN payment_counts AS p ON p.order_id = o.order_id
LEFT JOIN shipment_counts AS s ON s.order_id = o.order_id
ORDER BY o.order_id;
~~~

Các CTE đều có **tối đa một hàng trên mỗi order_id**, nên sau khi nối vẫn có một hàng theo order.

Nếu cần cả số tiền, thêm tổng tiền vào CTE của từng nhánh; **không** thêm bảng con gốc vào query cuối chỉ để tính một chỉ số khác.

## 21. Tổng hợp hai cấp: order rồi customer

Yêu cầu: một hàng cho mỗi khách với tổng tiền item của các đơn.

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM join_lab.order_item
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(SUM(ot.item_total), 0) AS total_item_amount
FROM join_lab.customer AS c
LEFT JOIN join_lab.sales_order AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_totals AS ot
    ON ot.order_id = o.order_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | full_name | total_item_amount |
|---:|---|---:|
| 1 | Nguyễn An | 450.00 |
| 2 | Trần Bình | 90.00 |
| 3 | Lê Chi | 0.00 |

Luồng grain:

~~~text
item_id -- GROUP BY order_id --> order_id
order_id -- JOIN customer --> nhiều order/customer
customer_id -- GROUP BY customer_id --> một hàng/customer
~~~

Việc mỗi khách có nhiều đơn là **đúng**, nhưng số đo đã được gom về order trước, nên không bị nhân bởi payment hoặc shipment.

## 22. Nhiều-nhiều hợp lệ và bảng cầu nối

Một người có thể thuộc nhiều nhóm; một nhóm có thể có nhiều thành viên.

~~~sql
WITH membership(user_id, group_id) AS (
    VALUES
        (1, 10),
        (1, 20),
        (2, 10)
)
SELECT user_id, group_id
FROM membership
ORDER BY user_id, group_id;
~~~

Người dùng 1 xuất hiện hai lần là chính xác: hai membership khác nhau.

Trong bảng thật, có thể dùng khóa ghép:

~~~sql
CREATE TABLE join_lab.membership_demo (
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, group_id)
);
~~~

Khóa ghép ngăn một **cặp người–nhóm** bị ghi trùng, nhưng vẫn cho phép người dùng thuộc nhiều nhóm.

Nếu nối membership với bảng tag có nhiều tag cho một nhóm, số hàng của người dùng có thể tăng theo tag. Muốn đếm **số nhóm khác nhau**, phải tính theo `group_id` hoặc grain membership phù hợp, không dùng `COUNT(*)` sau mọi phép nối.

## 23. JOIN thiếu ON hoặc điều kiện quá yếu

~~~sql
SELECT c.customer_id, o.order_id
FROM join_lab.customer AS c
CROSS JOIN join_lab.sales_order AS o;
~~~

Có 3 khách × 4 đơn = **12 tổ hợp**. Nếu mục tiêu tạo mọi cặp khách–đơn để test, đó là đúng. Nếu mục tiêu nối khách với đơn thực sự, đó là sai quan hệ.

Một `JOIN ... ON TRUE` cũng tạo tích như vậy.

### 23.1. Thiếu một phần khóa ghép

Giả sử các bảng multi-tenant có khóa logic `(tenant_id, order_id)`. Hai tenant có thể cùng dùng `order_id=1001`.

Sai:

~~~sql
-- Ví dụ khái niệm:
-- ON payment.order_id = orders.order_id
~~~

Đúng theo khóa composite:

~~~sql
-- Ví dụ khái niệm:
SELECT ...
FROM tenant_orders AS o
JOIN tenant_payments AS p
    ON p.tenant_id = o.tenant_id
   AND p.order_id = o.order_id;
~~~

Nếu thiếu `tenant_id`, một payment tenant B có thể khớp với order tenant A và tạo nhiều hàng sai.

**Điều kiện nối phải dựa trên toàn bộ khóa có ý nghĩa**, không chỉ vài cột có tên giống nhau.

## 24. Nối sai hai bảng con khi đã có quan hệ trực tiếp

Giả sử mỗi refund gắn với **một payment** qua `payment_id`.

Nối đúng:

~~~sql
-- Ví dụ khái niệm:
SELECT
    p.payment_id,
    r.refund_id
FROM payment AS p
LEFT JOIN refund AS r
    ON r.payment_id = p.payment_id;
~~~

Nếu nối refund với payment bằng **chung order_id** thay vì `payment_id`, mọi refund của một đơn có thể bị ghép với các payment không sở hữu refund đó.

Trong tình huống này, không nhất thiết phải preaggregate. Trước tiên cần **sửa khóa nối thực tế** giữa các quan hệ.

## 25. JOIN theo thời gian có thể có nhiều bản ghi hiệu lực

Giả sử bảng lịch sử giá có nhiều khoảng thời gian. Một đơn được đặt vào ngày mà hai khoảng giá chồng nhau:

~~~sql
WITH
orders(order_id, sku, ordered_on) AS (
    VALUES
        (1, 'A'::TEXT, DATE '2026-02-10')
),
price_history(price_id, sku, valid_from, valid_to, price) AS (
    VALUES
        (101, 'A'::TEXT,
            DATE '2026-02-01', DATE '2026-03-01', 110.00::NUMERIC),
        (102, 'A'::TEXT,
            DATE '2026-02-05', DATE '2026-02-20', 115.00::NUMERIC)
)
SELECT
    o.order_id,
    h.price_id,
    h.price
FROM orders AS o
JOIN price_history AS h
    ON h.sku = o.sku
   AND o.ordered_on >= h.valid_from
   AND o.ordered_on < h.valid_to
ORDER BY h.price_id;
~~~

Kết quả có **hai hàng giá cho một đơn**, vì hai khoảng đều bao phủ ngày 10/02.

Có thể chọn bản giá có `valid_from` mới nhất bằng `LATERAL ... LIMIT 1` nếu **nghiệp vụ xác nhận** quy tắc đó. Nhưng nếu các khoảng không được phép chồng lấn, việc chọn tùy một dòng sẽ che lỗi dữ liệu.

Giải pháp bền vững:

- Dùng khoảng nửa mở `[from,to)`.
- Quy định một thời điểm chỉ thuộc tối đa một phiên bản cho mỗi khóa.
- Kiểm tra nhập liệu có khoảng chồng.
- Cân nhắc range types và exclusion constraints thích hợp nếu cần PostgreSQL thực thi quy tắc không chồng lấn.

## 26. NULL trong khóa nối có thể gây bất ngờ

Với điều kiện:

~~~sql
ON a.optional_key = b.optional_key
~~~

hai giá trị `NULL` không được xem là bằng nhau theo semantics dấu bằng SQL.

PostgreSQL có `IS NOT DISTINCT FROM` để so sánh có ý nghĩa “NULL bằng NULL” khi nghiệp vụ thực sự cần:

~~~sql
ON a.optional_key IS NOT DISTINCT FROM b.optional_key
~~~

Nhưng nếu A có hai hàng NULL và B có ba hàng NULL, điều kiện này có thể tạo **2 × 3 = 6** tổ hợp.

Ví dụ:

~~~sql
WITH
a(id, k) AS (
    VALUES (1, NULL::INTEGER), (2, NULL::INTEGER)
),
b(id, k) AS (
    VALUES
        (10, NULL::INTEGER),
        (11, NULL::INTEGER),
        (12, NULL::INTEGER)
)
SELECT a.id AS a_id, b.id AS b_id
FROM a
JOIN b ON a.k IS NOT DISTINCT FROM b.k
ORDER BY a.id, b.id;
~~~

Không biến NULL (thường nghĩa là “chưa biết”) thành một mã nhóm chung rồi vô tình nối mọi bản ghi chưa biết với nhau.

## 27. Unique constraint là hợp đồng cardinality

Nếu một bảng `shipping_summary` được thiết kế chứa **tối đa một hàng mỗi đơn**, schema nên diễn đạt điều đó:

~~~sql
CREATE TABLE join_lab.shipping_summary_demo (
    order_id INTEGER PRIMARY KEY
        REFERENCES join_lab.sales_order(order_id),
    latest_tracking_code TEXT
);
~~~

Khi nối bảng summary theo `order_id`, phía bên phải có tối đa một hàng khớp. Điều đó đáng tin hơn việc dựa vào trạng thái hiện tại “có vẻ mỗi đơn chỉ có một hàng”.

Cần phân biệt:

- `PRIMARY KEY/UNIQUE(order_id)` trên bảng summary → một-một theo order.
- `FOREIGN KEY(order_id) REFERENCES sales_order` trên payment → nhiều payment có thể thuộc một order.

Một quan hệ được thiết kế duy nhất nhưng **không có constraint** có thể bị lỗi nhập liệu làm nhân hàng về sau.

### 27.1. Uniqueness của biểu thức nối cũng quan trọng

Ví dụ cột `email` có unique constraint, nhưng query nối bằng `lower(email)` có thể khớp nhiều hàng nếu nguồn có email chỉ khác chữ hoa/thường mà constraint không kiểm soát giá trị sau `lower`.

Nếu nghiệp vụ yêu cầu duy nhất theo biểu thức chuẩn hóa, cần xem xét expression unique index hoặc một mô hình chuẩn hóa dữ liệu tương ứng.

## 28. Chọn quan hệ gốc đúng với mục tiêu

Nếu báo cáo cần **mọi đơn**, bắt đầu từ `sales_order` rồi `LEFT JOIN` các summary.

Nếu báo cáo cần **mọi dòng item**, bắt đầu từ `order_item` và nối `sales_order` để lấy thông tin cha.

Nếu báo cáo cần **mọi khách**, bắt đầu từ `customer`, sau đó nối số liệu tổng hợp theo customer.

Nếu báo cáo cần có cả những **ngày không phát sinh giao dịch**, có thể bắt đầu từ calendar/date series rồi nối tổng giao dịch theo ngày.

Bảng nào đứng ở vị trí “driving set” ảnh hưởng việc hàng không có quan hệ con được giữ hay mất. Chọn sai từ đầu có thể đổi grain và số lượng hàng dù các điều kiện nối sau đó đều hợp lệ.

## 29. UNION ALL có thể đúng hơn JOIN

Giả sử mục tiêu là một dòng cho **mỗi sự kiện**, bao gồm item và payment. Không cần tạo mọi cặp item–payment. Có thể xếp các sự kiện nối tiếp nhau:

~~~sql
SELECT
    order_id,
    'item'::TEXT AS event_type,
    item_id AS event_id
FROM join_lab.order_item

UNION ALL

SELECT
    order_id,
    'payment'::TEXT AS event_type,
    payment_id AS event_id
FROM join_lab.payment

ORDER BY order_id, event_type, event_id;
~~~

`UNION ALL` cộng số hàng của hai nguồn. `JOIN` ghép các cột của những hàng khớp trên cùng một dòng kết quả, có thể tạo tích tổ hợp.

Nếu cần một event timeline tổng hợp, `UNION ALL` thường phản ánh yêu cầu tốt hơn một phép JOIN.

## 30. JSON aggregation và fanout

Một API có thể cần một object order chứa hai array độc lập:

~~~json
{
  "order_id": 1001,
  "items": [
    {"item_id": 11, "sku": "BOOK"},
    {"item_id": 12, "sku": "MOUSE"}
  ],
  "payments": [
    {"payment_id": 21, "amount": 120},
    {"payment_id": 22, "amount": 130}
  ]
}
~~~

Nếu nối item × payment rồi gọi `jsonb_agg`, mỗi item có thể xuất hiện hai lần và mỗi payment xuất hiện hai lần.

Cách đúng là tạo array **riêng từng nguồn** rồi nối:

~~~sql
WITH
item_json AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'item_id', item_id,
                'sku', sku,
                'quantity', quantity
            )
            ORDER BY item_id
        ) AS items
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_json AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'payment_id', payment_id,
                'amount', amount
            )
            ORDER BY paid_on, payment_id
        ) AS payments
    FROM join_lab.payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.items, '[]'::jsonb) AS items,
    COALESCE(p.payments, '[]'::jsonb) AS payments
FROM join_lab.sales_order AS o
LEFT JOIN item_json AS i ON i.order_id = o.order_id
LEFT JOIN payment_json AS p ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Mỗi CTE trả tối đa một hàng trên mỗi order, nên hai array không bị nhân chéo.

`jsonb_agg(DISTINCT ...)` đôi khi loại các giá trị trùng trong JSON, nhưng nó có thể bỏ những sự kiện khác nhau có cùng nội dung và không giải quyết mọi vấn đề số đo. Preaggregation giữ đúng ngữ nghĩa hơn.

## 31. UPDATE ... FROM cũng cần nguồn duy nhất theo khóa

Fanout không chỉ làm báo cáo sai. Với `UPDATE ... FROM`, nếu một hàng đích khớp nhiều hàng nguồn, PostgreSQL không bảo đảm **hàng nguồn nào** sẽ quyết định giá trị cập nhật.

Ví dụ nguồn patch có hai giá trị cho cùng order:

~~~sql
-- Ví dụ không nên chạy trên dữ liệu thật:
-- UPDATE join_lab.sales_order AS o
-- SET placed_on = patch.new_date
-- FROM (
--     VALUES
--         (1001, DATE '2026-02-10'),
--         (1001, DATE '2026-02-11')
-- ) AS patch(order_id, new_date)
-- WHERE o.order_id = patch.order_id;
~~~

Một cách xử lý nếu nghiệp vụ **chủ động chọn ngày lớn nhất**:

~~~sql
BEGIN;

WITH patch(order_id, new_date) AS (
    VALUES
        (1001, DATE '2026-02-10'),
        (1001, DATE '2026-02-11')
),
resolved AS (
    SELECT
        order_id,
        MAX(new_date) AS new_date
    FROM patch
    GROUP BY order_id
)
UPDATE join_lab.sales_order AS o
SET placed_on = r.new_date
FROM resolved AS r
WHERE o.order_id = r.order_id
RETURNING o.order_id, o.placed_on;

ROLLBACK;
~~~

`ROLLBACK` dùng để minh họa an toàn trong database test. `MAX` chỉ đúng nếu thực sự được nghiệp vụ chọn làm quy tắc; với nguồn có giá trị mâu thuẫn không được phép, phải **từ chối patch** thay vì tự chọn.

## 32. Chẩn đoán: đếm số hàng tại từng tầng JOIN

Thay vì chỉ nhìn tổng số hàng cuối cùng, hãy đếm số hàng sau từng bước.

~~~sql
SELECT
    'orders' AS stage,
    COUNT(*) AS row_count
FROM join_lab.sales_order

UNION ALL

SELECT
    'orders + items',
    COUNT(*)
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id

UNION ALL

SELECT
    'orders + items + payments',
    COUNT(*)
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id

UNION ALL

SELECT
    'orders + items + payments + shipments',
    COUNT(*)
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
LEFT JOIN join_lab.shipment AS s
    ON s.order_id = o.order_id;
~~~

Với dữ liệu mẫu, các số lần lượt là **4, 5, 7, 11**.

Tại sao?

- `orders`: 4 hàng.
- `orders + items`: hai hàng cho 1001, mỗi đơn khác một hàng (kể cả 1004 không có item): 5.
- `orders + items + payments`: 1001 tạo 4 tổ hợp, 1002/1003/1004 mỗi đơn một hàng: 7.
- Thêm shipment: 1001 có hai shipment nên 4 tổ hợp trước đó trở thành 8; cộng 1+1+1 từ các đơn khác: 11.

Đếm tại từng tầng giúp tìm phép JOIN bắt đầu gây fanout không mong muốn.

## 33. Chẩn đoán: COUNT theo từng khóa

Đếm quan hệ con:

~~~sql
SELECT
    order_id,
    COUNT(*) AS item_rows
FROM join_lab.order_item
GROUP BY order_id
ORDER BY item_rows DESC, order_id;

SELECT
    order_id,
    COUNT(*) AS payment_rows
FROM join_lab.payment
GROUP BY order_id
ORDER BY payment_rows DESC, order_id;
~~~

Đếm các hàng kết quả theo order:

~~~sql
WITH joined AS (
    SELECT
        o.order_id,
        i.item_id,
        p.payment_id
    FROM join_lab.sales_order AS o
    LEFT JOIN join_lab.order_item AS i
        ON i.order_id = o.order_id
    LEFT JOIN join_lab.payment AS p
        ON p.order_id = o.order_id
)
SELECT
    order_id,
    COUNT(*) AS joined_rows
FROM joined
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY joined_rows DESC, order_id;
~~~

Đơn 1001 có bốn hàng nên xuất hiện. Các đơn còn lại có một hàng và bị lọc bởi `HAVING`.

**Không đánh giá cứ `COUNT(*) > 1` là lỗi.** Nó chỉ là dấu hiệu cần kiểm tra khi grain kỳ vọng là order.

### 33.1. Đếm DISTINCT có ích cho chẩn đoán

~~~sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT i.item_id) AS distinct_items,
    COUNT(DISTINCT p.payment_id) AS distinct_payments
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Đối với 1001, kết quả là `joined_rows = 4`, `distinct_items = 2`, `distinct_payments = 2`. Đây là bằng chứng về fanout từ hai nguồn.

## 34. Kiểm tra tổng trực tiếp từ các bảng sự kiện

Một con số đối chiếu nên được tính **trực tiếp từ bảng gốc**, không qua JOIN gây fanout:

~~~sql
SELECT
    (
        SELECT SUM(quantity * unit_price)
        FROM join_lab.order_item
    ) AS all_item_amount,
    (
        SELECT SUM(amount)
        FROM join_lab.payment
    ) AS all_payment_amount;
~~~

Với dữ liệu mẫu, cả hai tổng là:

\[
250.00 + 200.00 + 90.00 = 540.00
\]

Đây là phép đối chiếu hữu ích với các bảng summary sau khi JOIN.

Tuy nhiên, trong hệ thống thật tổng tiền hàng và tiền thanh toán **không nhất thiết bằng nhau**: đơn có thể chưa trả đủ, được hoàn tiền hoặc đang chờ quyết toán. Bất biến tài chính phải xuất phát từ quy tắc nghiệp vụ thật.

## 35. Kiểm tra EXPLAIN và row estimates

PostgreSQL planner tính toán nhiều chiến lược JOIN, chẳng hạn:

- `Nested Loop`.
- `Hash Join`.
- `Merge Join`.
- `Hash Left Join`.
- Các node `Sort` và `Aggregate`.

Có thể quan sát kế hoạch:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    i.item_id,
    p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id;
~~~

Trên database test, có thể so sánh số hàng ước tính với thực tế:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    i.item_id,
    p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id;
~~~

`ANALYZE` **thực thi query** để đo. Ví dụ này là SELECT; không tùy tiện dùng `EXPLAIN ANALYZE` trên `UPDATE`/`DELETE` production vì nó sẽ thực hiện thao tác ghi.

Số hàng ước tính có thể khác thực tế vì thống kê, độ lệch dữ liệu hoặc các điều kiện tương quan. Nhưng dù planner ước tính rất chính xác, một câu SQL cộng tiền trên phép JOIN bị nhân vẫn cho **kết quả sai về logic**.

**Đúng semantics trước, tối ưu hiệu năng sau.**

## 36. Index và fanout là hai vấn đề khác nhau

Các cột khóa ngoại thường được JOIN:

~~~sql
CREATE INDEX idx_sales_order_customer
ON join_lab.sales_order (customer_id);

CREATE INDEX idx_order_item_order
ON join_lab.order_item (order_id);

CREATE INDEX idx_payment_order
ON join_lab.payment (order_id);

CREATE INDEX idx_shipment_order
ON join_lab.shipment (order_id);
~~~

Index có thể giúp truy vấn nhanh hơn khi lọc theo `order_id` hoặc `customer_id`, tùy dữ liệu và kế hoạch.

PostgreSQL **không tự tạo index cho mọi cột khóa ngoại ở bảng con**. Với bảng rất nhỏ, sequential scan có thể tối ưu hơn index scan.

Dù có index, đơn 1001 vẫn có **2 item × 2 payment = 4** tổ hợp nếu SQL nối như vậy. Index không thay đổi semantics JOIN.

Tương tự, extended statistics có thể hỗ trợ planner ước lượng cardinality trong một số tình huống, nhưng **không tự sửa số đo đã bị nhân**.

## 37. Các lỗi tư duy thường gặp

### Lỗi 1 — Không xác định grain

Báo cáo cần một hàng mỗi order, nhưng SQL trả item-level rows.

**Cách xử lý:** viết rõ khóa duy nhất đầu ra, ví dụ `order_id`.

### Lỗi 2 — Nghĩ có FOREIGN KEY thì một-một

Một đơn có thể có nhiều item/payment.

**Cách xử lý:** kiểm tra cả `UNIQUE`/`PRIMARY KEY` phía con.

### Lỗi 3 — GROUP BY sau khi nối nhiều fact tables

Tổng tiền đã bị nhân trước khi group.

**Cách xử lý:** tổng hợp từng fact table về grain chung trước JOIN.

### Lỗi 4 — Dùng SUM(DISTINCT amount)

Có thể bỏ sự kiện hợp lệ cùng số tiền.

**Cách xử lý:** cộng theo các hàng sự kiện gốc, không distinct giá trị.

### Lỗi 5 — Dùng JOIN chỉ để kiểm tra tồn tại

Một đơn có nhiều payment bị lặp.

**Cách xử lý:** `EXISTS`/`NOT EXISTS`.

### Lỗi 6 — Dùng DISTINCT để giấu kết quả sai

Có thể loại hàng trông giống nhau nhưng không sửa SUM.

**Cách xử lý:** tìm nguyên nhân fanout, thay đổi grain hoặc điều kiện nối.

### Lỗi 7 — Chọn latest row mà không có tie-breaker

Khi hai bản ghi cùng ngày, kết quả không xác định rõ.

**Cách xử lý:** thêm tiêu chí ổn định như primary key trong `ORDER BY`.

### Lỗi 8 — LEFT JOIN nhưng lọc cột phải trong WHERE

Đơn không có con bị loại.

**Cách xử lý:** đặt filter đúng trong `ON` nếu cần giữ hàng trái.

### Lỗi 9 — COUNT(*) sau LEFT JOIN để đếm hàng con

Đơn không có con vẫn đóng góp một hàng.

**Cách xử lý:** `COUNT(child_pk)` hoặc summary ở grain con.

### Lỗi 10 — Thiếu thành phần khóa ghép

Dữ liệu tenant khác bị nối nhầm.

**Cách xử lý:** JOIN bằng đủ khóa logic, không chỉ một cột trùng tên.

### Lỗi 11 — JOIN theo biểu thức không duy nhất

`lower(email)` hoặc ngày làm tròn có thể khiến nhiều hàng khớp.

**Cách xử lý:** xem uniqueness của chính biểu thức và miền dữ liệu.

### Lỗi 12 — JOIN theo khoảng thời gian chồng nhau

Một giao dịch khớp nhiều giá lịch sử.

**Cách xử lý:** kiểm soát khoảng hiệu lực hoặc định nghĩa quy tắc chọn rõ ràng.

### Lỗi 13 — Tính JSON arrays sau JOIN đã nhân

Mỗi item xuất hiện nhiều lần theo payment.

**Cách xử lý:** `jsonb_agg` riêng từng nguồn rồi JOIN summaries.

### Lỗi 14 — Dùng UPDATE FROM với patch trùng khóa

Một hàng đích khớp nhiều giá trị patch.

**Cách xử lý:** kiểm tra hoặc resolve patch thành một hàng cho mỗi khóa.

### Lỗi 15 — Dựa vào tên view

Tên `one_order_summary` không bảo đảm view có một hàng mỗi order.

**Cách xử lý:** kiểm tra SQL định nghĩa, keys và `GROUP BY order_id HAVING COUNT(*) > 1`.

### Lỗi 16 — Tập trung vào index trước tính đúng

Một query chạy nhanh nhưng tổng tiền sai vẫn sai.

**Cách xử lý:** đối soát với bảng gốc, sau đó mới dùng `EXPLAIN` để tối ưu.

## 38. Quy trình xử lý fanout trong truy vấn lớn

Khi query có nhiều bảng trả số hàng hoặc số tiền bất thường:

**Bước 1 — Ghi grain đầu ra.** Ví dụ mỗi `order_id` xuất hiện một lần.

**Bước 2 — Liệt kê grain từng nguồn.** `customer_id`, `order_id`, `item_id`, `payment_id`, `shipment_id`.

**Bước 3 — Đọc khóa và constraints.** Xác định quan hệ nào 1:1, 1:N hoặc N:M.

**Bước 4 — Đếm từng nguồn.** Dùng `GROUP BY join_key HAVING COUNT(*) > 1`.

**Bước 5 — Nối từng tầng và đếm lại.** Xác định phép nối bắt đầu làm tăng hàng.

**Bước 6 — Xem lại `ON`.** Có thiếu `tenant_id`, `line_no`, `payment_id`, phiên bản hoặc khoảng thời gian không?

**Bước 7 — Đổi cấu trúc theo mục đích.** Tồn tại → `EXISTS`; tổng → preaggregate; mới nhất → `DISTINCT ON`/`ROW_NUMBER`/`LATERAL`.

**Bước 8 — Giữ hàng không khớp đúng ý.** Kiểm tra `INNER JOIN`/`LEFT JOIN` và filter trong `ON`/`WHERE`.

**Bước 9 — Đối soát.** Tổng hợp trực tiếp từ từng fact table và so với báo cáo.

**Bước 10 — Thử edge cases.** Không có con, một con, nhiều con, hai payment cùng amount, khóa trùng, NULL và khoảng hiệu lực chồng nhau.

**Bước 11 — Tối ưu.** `EXPLAIN`, index và thống kê trên dữ liệu đại diện.

Quy trình này giúp phân biệt **lỗi nghiệp vụ trong kết quả** với **vấn đề hiệu năng**.

## 39. Báo cáo tổng hợp đầy đủ: đúng một hàng cho mỗi đơn

Yêu cầu gồm:

- ID đơn và tên khách.
- Số item, tổng tiền hàng.
- Số payment, tổng thanh toán.
- Số shipment.
- Có payment hay chưa.

~~~sql
WITH
item_summary AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS item_total
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_summary AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS payment_total
    FROM join_lab.payment
    GROUP BY order_id
),
shipment_summary AS (
    SELECT
        order_id,
        COUNT(*) AS shipment_count
    FROM join_lab.shipment
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.full_name,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.payment_total, 0) AS payment_total,
    COALESCE(s.shipment_count, 0) AS shipment_count,
    COALESCE(p.payment_count, 0) > 0 AS has_payment
FROM join_lab.sales_order AS o
JOIN join_lab.customer AS c
    ON c.customer_id = o.customer_id
LEFT JOIN item_summary AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_summary AS p
    ON p.order_id = o.order_id
LEFT JOIN shipment_summary AS s
    ON s.order_id = o.order_id
ORDER BY o.order_id;
~~~

Kết quả:

| order_id | full_name | item_count | item_total | payment_count | payment_total | shipment_count | has_payment |
|---:|---|---:|---:|---:|---:|---:|---|
| 1001 | Nguyễn An | 2 | 250.00 | 2 | 250.00 | 2 | true |
| 1002 | Nguyễn An | 1 | 200.00 | 1 | 200.00 | 1 | true |
| 1003 | Trần Bình | 1 | 90.00 | 1 | 90.00 | 0 | true |
| 1004 | Lê Chi | 0 | 0.00 | 0 | 0.00 | 0 | false |

### 39.1. Vì sao báo cáo có đúng bốn hàng?

- `sales_order` là tập điều khiển, một hàng mỗi `order_id`.
- `customer` có khóa duy nhất, nên mỗi order ghép tối đa một customer.
- Mỗi summary có một hàng cho mỗi order, nên không tạo tích con.
- `LEFT JOIN` giữ order 1004.
- `COALESCE` biểu diễn số đếm và tổng thiếu thành 0.

### 39.2. “Có thanh toán” khác “đã thanh toán đủ”

`has_payment = true` chỉ có nghĩa tồn tại ít nhất một payment row. Trong hệ thống thật, payment có thể thất bại, bị hoàn, đang xử lý hoặc chưa đủ giá trị. Cần định nghĩa những trạng thái nghiệp vụ trước khi tính doanh thu.

## 40. Bài tập tự luyện

### Bài 1 — Grain

Một khách có ba đơn. `JOIN customer → sales_order` trả mấy hàng nếu không lọc?

**Gợi ý:** ba hàng, đúng khi grain là đơn.

### Bài 2 — Hai bảng con

Một đơn có 3 item và 4 payment. JOIN cả hai chỉ bằng order_id tạo bao nhiêu hàng?

**Gợi ý:** 12 hàng.

### Bài 3 — Ba bảng con

Một đơn có 2 item, 3 payment và 2 shipment. JOIN ba nhánh tạo bao nhiêu tổ hợp nếu tất cả cùng khớp một order?

**Gợi ý:** 12.

### Bài 4 — LEFT JOIN và dữ liệu rỗng

Đơn không có item và payment. LEFT JOIN cả hai vẫn có bao nhiêu hàng?

**Gợi ý:** một hàng NULL phía con.

### Bài 5 — COUNT(*)

Vì sao `COUNT(*)` trên LEFT JOIN không phải số item của đơn 1004?

**Gợi ý:** một hàng giữ order vẫn tồn tại, `COUNT(item_id)=0`.

### Bài 6 — Sai SUM

Tính bằng tay giá trị sai do JOIN item × payment cho order 1001.

**Gợi ý:** 500.00 cho mỗi phía thay vì 250.00.

### Bài 7 — SUM(DISTINCT)

Hai item khác nhau đều có line_total 100.00. `SUM(DISTINCT line_total)` cho bao nhiêu?

**Gợi ý:** 100.00, không phải tổng đúng 200.00.

### Bài 8 — Preaggregation

Viết CTE tổng item theo order_id trước khi JOIN với order.

**Gợi ý:** `GROUP BY order_id`.

### Bài 9 — Tổng payment

Viết CTE tổng amount theo order rồi nối với item summary mà không nhân số tiền.

**Gợi ý:** mỗi summary tối đa một hàng/order.

### Bài 10 — EXISTS

Tìm các đơn có ít nhất một shipment, mỗi đơn một hàng.

**Gợi ý:** `WHERE EXISTS`.

### Bài 11 — NOT EXISTS

Tìm đơn chưa có payment trong dữ liệu mẫu.

**Gợi ý:** 1004.

### Bài 12 — DISTINCT

`SELECT DISTINCT o.order_id, p.payment_id` có loại mất payment thứ hai của order 1001 không?

**Gợi ý:** không, vì payment_id khác nhau.

### Bài 13 — DISTINCT ON

Lấy payment mới nhất mỗi order, dùng ngày thanh toán và payment_id làm tie-breaker.

**Gợi ý:** `DISTINCT ON(order_id) ... ORDER BY order_id, paid_on DESC, payment_id DESC`.

### Bài 14 — ROW_NUMBER

Viết phiên bản dùng `ROW_NUMBER()` cho bài 13.

**Gợi ý:** `PARTITION BY order_id` và `rn=1`.

### Bài 15 — LATERAL

Lấy tối đa một shipment mới nhất mỗi order nhưng vẫn giữ order không có shipment.

**Gợi ý:** `LEFT JOIN LATERAL (...) ON TRUE`.

### Bài 16 — Filter của LEFT JOIN

Vì sao `WHERE p.amount > 0` làm mất order 1004?

**Gợi ý:** NULL không thỏa điều kiện.

### Bài 17 — Khóa ghép

Một bảng order duy nhất theo `(tenant_id,order_id)`. Vì sao JOIN chỉ theo `order_id` nguy hiểm?

**Gợi ý:** có thể ghép sai tenant.

### Bài 18 — Khoảng hiệu lực

Một giao dịch khớp hai bảng giá lịch sử. Điều gì có thể sai trong điều kiện thời gian hoặc dữ liệu nguồn?

**Gợi ý:** khoảng hiệu lực chồng nhau.

### Bài 19 — REFUND

Refund tham chiếu payment_id. Nếu JOIN payment và refund chỉ theo order_id sẽ ra sao?

**Gợi ý:** refund ghép sai với các payment khác cùng đơn.

### Bài 20 — JSON

Muốn một order chứa item array và payment array, nên aggregate ở đâu?

**Gợi ý:** từng bảng con riêng trước JOIN.

### Bài 21 — UPDATE FROM

Patch có hai giá trị khác nhau cho một order_id. Có nên cập nhật trực tiếp?

**Gợi ý:** không; phải kiểm tra và resolve nguồn.

### Bài 22 — Đếm từng tầng

Đếm số hàng cho bốn mức JOIN của schema mẫu.

**Gợi ý:** 4, 5, 7, 11.

### Bài 23 — Tổng theo khách

Tính tổng item theo customer sau khi tổng hợp về order.

**Gợi ý:** khách 1 có 450.00; khách 2 có 90.00; khách 3 có 0.00.

### Bài 24 — UNION ALL

Khi muốn một dòng mỗi item hoặc payment như các sự kiện, vì sao UNION ALL phù hợp hơn JOIN?

**Gợi ý:** xếp hàng thay vì tạo các cặp tổ hợp.

### Bài 25 — Index

Tạo index payment(order_id) có thể giúp điều gì và không thể sửa điều gì?

**Gợi ý:** tăng hiệu quả truy cập; không sửa phép SUM bị fanout.

### Bài 26 — Constraint

Nếu bảng summary phải có một hàng mỗi order, nên dùng ràng buộc nào?

**Gợi ý:** `PRIMARY KEY(order_id)` hoặc `UNIQUE(order_id)` theo mô hình.

## 41. Bảng quyết định

| Mục tiêu | Công cụ thích hợp | Grain kết quả |
|---|---|---|
| Mọi item kèm thông tin order | JOIN item–order | Item |
| Mọi payment kèm thông tin order | JOIN payment–order | Payment |
| Đơn có payment | EXISTS | Order |
| Đơn chưa có payment | NOT EXISTS | Order |
| Tổng item và payment | Preaggregate từng nhánh rồi JOIN | Order |
| Tổng tiền theo khách | Order summary rồi GROUP BY customer | Customer |
| Payment mới nhất | DISTINCT ON / ROW_NUMBER / LATERAL | Một payment/order |
| Array item và payment | jsonb_agg riêng từng nhánh | Order |
| Mọi cặp item–payment | JOIN trực tiếp nếu đúng yêu cầu | Cặp item–payment |
| Các sự kiện item/payment | UNION ALL | Sự kiện |
| Nguồn UPDATE nhiều dòng | Resolve/validate khóa trước UPDATE FROM | Một giá trị nguồn/khóa đích |
| Nối lịch sử giá | Khóa + khoảng hiệu lực nhất quán | Thực thể tại thời điểm |

## 42. Tổng kết

- **Hàng cha lặp sau JOIN không tự là lỗi**: nó có thể phản ánh quan hệ một-nhiều hợp lệ.
- **Grain** quyết định ý nghĩa của từng hàng và cách tính số đo.
- Nối nhiều bảng con độc lập có thể tạo **tích số hàng**, như 2 item × 2 payment = 4 tổ hợp.
- `GROUP BY` ở cuối không tự biết số đo nào đã bị nhân; `SUM(DISTINCT amount)` cũng có thể loại sự kiện hợp lệ cùng tiền.
- **Tổng hợp mỗi bảng con ở grain chung trước JOIN** là giải pháp chủ đạo cho báo cáo một hàng mỗi order/customer.
- **`EXISTS` và `NOT EXISTS`** phù hợp với yêu cầu có/không có quan hệ con.
- **`DISTINCT ON`, `ROW_NUMBER()` và `LATERAL LIMIT 1`** giúp chọn một hàng con theo tiêu chí xác định; không dùng để thay cho SUM.
- `LEFT JOIN` vẫn có thể nhân hàng; filter ở `WHERE` có thể làm mất hàng cha không khớp.
- **Foreign key không có nghĩa một-một**; ràng buộc `UNIQUE` hoặc `PRIMARY KEY` cần phản ánh tính duy nhất thực sự.
- Khóa ghép, tenant, biểu thức chuẩn hóa, phiên bản và khoảng hiệu lực phải được đưa vào điều kiện JOIN khi phù hợp.
- Có thể chẩn đoán bằng **đếm theo khóa và theo từng tầng**, đối chiếu tổng từ bảng gốc và quan sát `EXPLAIN`.
- Đối với cập nhật dữ liệu, **`UPDATE ... FROM` phải có nguồn duy nhất theo khóa đích** hoặc quy tắc resolve được xác định rõ.

Một truy vấn kết hợp nhiều quan hệ đáng tin không chỉ là query chạy được. Nó phải bảo đảm **mỗi hàng kết quả đại diện đúng thực thể, mỗi số đo chỉ được tính từ những sự kiện thật đúng một lần và mọi phép nối sử dụng đúng quan hệ nghiệp vụ**. Khi xác định grain trước khi viết `JOIN`, bạn có thể tránh phần lớn lỗi nhân bản hàng khó phát hiện trong PostgreSQL.
