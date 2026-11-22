# Kiểm chứng số lượng dòng và tổng hợp sau khi kết nối nhiều bảng

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Gom nhóm và tập hợp  
> **Mục tiêu:** Kiểm tra đúng số lượng dòng và giá trị tổng hợp sau khi JOIN nhiều bảng; hiểu ảnh hưởng của quan hệ 1:1, 1:N, N:M đến cardinality; nhận diện hiện tượng nhân dòng (fanout), đếm trùng và cộng trùng; chọn cách tổng hợp đúng ở từng cấp dữ liệu, đối soát kết quả và giải thích được vì sao số liệu thay đổi sau khi kết nối bảng.

## 1. Vì sao tổng hợp sau JOIN dễ sai?

Giả sử hệ thống bán hàng có ba bảng:

- `ORDERS`: một dòng cho mỗi đơn hàng.
- `ORDER_ITEMS`: nhiều dòng mặt hàng thuộc một đơn hàng.
- `PAYMENTS`: có thể có nhiều giao dịch thanh toán cho một đơn hàng (thanh toán từng phần, thử lại, hoàn tiền).

Dữ liệu minh họa:

```text
ORDERS
ORDER_ID | CUSTOMER_ID | ORDER_TOTAL
---------+-------------+------------
1001     | 10          | 300
1002     | 20          | 200

ORDER_ITEMS
ITEM_ID | ORDER_ID | QTY | UNIT_PRICE
--------+----------+-----+-----------
1       | 1001     | 1   | 100
2       | 1001     | 2   | 100
3       | 1002     | 1   | 200

PAYMENTS
PAYMENT_ID | ORDER_ID | PAID_AMOUNT
-----------+----------+------------
501        | 1001     | 100
502        | 1001     | 200
503        | 1002     | 200
```

Tổng tiền đơn hàng đúng là:

```text
1001: 300
1002: 200
Toàn bộ: 500
```

Nhưng nếu JOIN cả ba bảng trực tiếp:

```sql
SELECT o.order_id,
       o.order_total,
       SUM(i.qty * i.unit_price) AS item_total,
       SUM(p.paid_amount) AS paid_total
FROM orders o
JOIN order_items i
  ON i.order_id = o.order_id
JOIN payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id, o.order_total;
```

Với đơn 1001, có 2 dòng item và 2 dòng payment. JOIN tạo 2 × 2 = 4 dòng trung gian:

```text
ITEM 1 × PAYMENT 501
ITEM 1 × PAYMENT 502
ITEM 2 × PAYMENT 501
ITEM 2 × PAYMENT 502
```

Vì vậy, item total bị lặp hai lần và payment total cũng bị lặp hai lần. Kết quả cho đơn 1001 có thể thành `600` cho từng tổng, dù dữ liệu nguồn chỉ có `300`. Đơn 1002 chỉ có một item và một payment nên không bộc lộ lỗi.

Đây là **fanout**: số dòng của một phía bị nhân lên bởi nhiều bản ghi ở phía khác. Nó là nguyên nhân phổ biến khiến báo cáo SQL trả tổng tiền, số lượng đơn, số khách hàng hoặc số giao dịch lớn hơn thực tế.

Nguyên tắc quan trọng:

> Trước khi JOIN và GROUP BY, phải biết **một dòng ở mỗi bảng đại diện cho điều gì** và JOIN có thể tạo bao nhiêu dòng cho mỗi khóa.

## 2. Grain: xác định cấp độ của một dòng

**Grain** (mức chi tiết/cấp dữ liệu) mô tả ý nghĩa của một dòng trong tập kết quả hoặc bảng.

Ví dụ:

| Bảng/tập dữ liệu | Grain của một dòng |
|---|---|
| `ORDERS` | Một đơn hàng |
| `ORDER_ITEMS` | Một mặt hàng trong một đơn hàng |
| `PAYMENTS` | Một giao dịch thanh toán |
| `CUSTOMERS` | Một khách hàng |
| JOIN `ORDERS` với `ORDER_ITEMS` | Một mặt hàng của một đơn hàng (đơn hàng lặp theo số item) |
| JOIN cả item và payment | Một cặp item-payment trong cùng đơn hàng |

Một truy vấn có thể đúng ở grain “một dòng cho mỗi cặp item-payment” nhưng sai nếu người viết nghĩ kết quả vẫn là “một dòng cho mỗi đơn hàng”.

### 2.1. Hỏi ba câu trước khi viết JOIN

1. **Đầu ra cần một dòng cho mỗi đối tượng nào?** Mỗi đơn hàng, item, khách hàng, tháng hay từng payment?
2. **Mỗi bảng có bao nhiêu dòng cho một khóa JOIN?** Một, không, một hoặc nhiều, hay nhiều ở cả hai phía?
3. **Các phép tổng hợp cần tính trên bảng nào?** Tổng order_total, item amount hay payment amount?

Nếu không xác định được grain, không nên vội viết `SUM` hoặc `COUNT`.

### 2.2. Grain thay đổi sau JOIN

```text
ORDERS (1 dòng / order)
        |
        | 1:N
        v
ORDER_ITEMS (n dòng / order)
        |
        | mỗi item được ghép với mỗi payment
        v
ITEM × PAYMENT (mỗi cặp / order)
```

Khi kết nối các bảng con độc lập cùng tham chiếu một bảng cha, grain kết quả thường là **tích các tổ hợp con**, không còn là grain của bảng cha hoặc của từng bảng con.

## 3. Cardinality của quan hệ JOIN

Cardinality là số lượng dòng được tạo ra hoặc dự kiến bởi một phép kết nối. Cần phân biệt cardinality của quan hệ dữ liệu với số dòng optimizer ước lượng trong execution plan.

### 3.1. Quan hệ 1:1

Một bản ghi A ghép tối đa với một bản ghi B:

```sql
SELECT e.employee_id,
       e.first_name,
       d.department_name
FROM employees e
JOIN employee_profiles p
  ON p.employee_id = e.employee_id
JOIN departments d
  ON d.department_id = e.department_id;
```

Nếu `EMPLOYEE_PROFILES.EMPLOYEE_ID` có UNIQUE hoặc PRIMARY KEY, một nhân viên không thể nhân thành nhiều dòng do bảng profile. Nếu không có ràng buộc duy nhất, JOIN có thể là 1:N dù người thiết kế nghĩ là 1:1.

**Tính duy nhất cần được bảo vệ bằng constraint**, không chỉ dựa trên giả định của ứng dụng.

### 3.2. Quan hệ 1:N

Một đơn hàng có nhiều dòng mặt hàng:

```sql
SELECT o.order_id,
       i.item_id,
       i.qty,
       i.unit_price
FROM orders o
JOIN order_items i
  ON i.order_id = o.order_id;
```

Mỗi đơn hàng xuất hiện một lần cho mỗi item. Đây là kết quả đúng nếu muốn xem chi tiết item, nhưng nếu lấy `COUNT(*)` thì đang đếm số item, không phải số đơn hàng.

### 3.3. Quan hệ N:M

Một sinh viên có nhiều môn học và một môn có nhiều sinh viên, thông qua bảng liên kết:

```text
STUDENTS 1 --- N STUDENT_COURSES N --- 1 COURSES
```

Ví dụ:

```sql
SELECT s.student_id,
       s.student_name,
       c.course_id,
       c.course_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
JOIN courses c
  ON c.course_id = sc.course_id;
```

Một sinh viên có thể xuất hiện nhiều lần, một khóa học cũng có thể xuất hiện nhiều lần. Nếu mục tiêu là đếm sinh viên duy nhất theo khóa học, phải xác định rõ grain và phép đếm.

### 3.4. JOIN nhiều bảng con độc lập tạo fanout

Giả sử mỗi order có `m` item và `n` payment. Khi JOIN cả hai bảng theo order_id, số tổ hợp có thể là:

\[
m \times n
\]

Nếu một order có 3 item và 4 payment, JOIN có thể tạo 12 dòng cho order đó. Với nhiều bảng con độc lập, số tổ hợp có thể tiếp tục nhân lên.

Đây là lý do cần kiểm tra cardinality trước khi cộng các measure (số đo) nằm ở những bảng có grain khác nhau.

## 4. Tạo dữ liệu lab để quan sát nhân dòng

Bài lab dùng các bảng riêng, không đụng tới schema ứng dụng. Cần quyền CREATE TABLE và quota phù hợp.

### 4.1. Tạo bảng đơn hàng

```sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2) NOT NULL
);

CREATE TABLE lab_order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    qty NUMBER(8,0) NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT fk_lab_item_order
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);

CREATE TABLE lab_payments (
    payment_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    paid_amount NUMBER(12,2) NOT NULL,
    payment_status VARCHAR2(20 CHAR) NOT NULL,
    CONSTRAINT fk_lab_payment_order
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);
```

### 4.2. Chèn dữ liệu có chủ ý

```sql
INSERT INTO lab_orders VALUES (1001, 10, 300);
INSERT INTO lab_orders VALUES (1002, 20, 200);

INSERT INTO lab_order_items VALUES (1, 1001, 1, 100);
INSERT INTO lab_order_items VALUES (2, 1001, 2, 100);
INSERT INTO lab_order_items VALUES (3, 1002, 1, 200);

INSERT INTO lab_payments VALUES (501, 1001, 100, 'SETTLED');
INSERT INTO lab_payments VALUES (502, 1001, 200, 'SETTLED');
INSERT INTO lab_payments VALUES (503, 1002, 200, 'SETTLED');

COMMIT;
```

### 4.3. Xác nhận grain từng bảng

```sql
SELECT COUNT(*) AS order_rows,
       COUNT(DISTINCT order_id) AS distinct_orders
FROM lab_orders;

SELECT COUNT(*) AS item_rows,
       COUNT(DISTINCT order_id) AS orders_with_items
FROM lab_order_items;

SELECT COUNT(*) AS payment_rows,
       COUNT(DISTINCT order_id) AS orders_with_payments
FROM lab_payments;
```

Kết quả kỳ vọng:

| Tập dữ liệu | Số dòng | Số order_id khác nhau |
|---|---:|---:|
| LAB_ORDERS | 2 | 2 |
| LAB_ORDER_ITEMS | 3 | 2 |
| LAB_PAYMENTS | 3 | 2 |

Bảng item có 3 dòng nhưng chỉ thuộc 2 đơn hàng. Bảng payment cũng có 3 dòng và thuộc 2 đơn. Hai con số này trả lời hai câu hỏi khác nhau.

## 5. COUNT sau JOIN: đang đếm cái gì?

Oracle có các dạng đếm quan trọng:

- `COUNT(*)`: đếm số dòng trong tập kết quả, bao gồm dòng có các cột NULL.
- `COUNT(expr)`: đếm số dòng mà biểu thức không NULL.
- `COUNT(DISTINCT expr)`: đếm số giá trị khác nhau, không tính NULL.
- `COUNT(DISTINCT col1, col2)` không phải cú pháp tổng quát cho nhiều cột theo cách của một số hệ quản trị khác; nếu cần đếm tổ hợp nhiều cột, dùng subquery SELECT DISTINCT theo các cột rồi COUNT.

### 5.1. COUNT(*) trên JOIN 1:N

```sql
SELECT COUNT(*) AS joined_rows
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

Kết quả là 3 vì có 3 dòng item. Không phải 2 đơn hàng.

Muốn đếm số đơn có ít nhất một item:

```sql
SELECT COUNT(DISTINCT o.order_id) AS orders_with_items
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

Kết quả là 2.

Một cách khác tránh tạo nhiều dòng chi tiết:

```sql
SELECT COUNT(*) AS orders_with_items
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_order_items i
    WHERE i.order_id = o.order_id
);
```

`EXISTS` chỉ kiểm tra có ít nhất một dòng phù hợp; mỗi order ở bảng cha chỉ được tính một lần.

### 5.2. COUNT(*) và COUNT(child_id) với LEFT JOIN

```sql
SELECT o.order_id,
       COUNT(*) AS count_star,
       COUNT(i.item_id) AS item_count
FROM lab_orders o
LEFT JOIN lab_order_items i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Với order có item:

- `COUNT(*)` đếm các dòng sau JOIN.
- `COUNT(i.item_id)` đếm số item có ID không NULL.

Với order không có item, LEFT JOIN vẫn tạo một dòng kết quả với các cột phía item là NULL. Khi đó `COUNT(*)` bằng 1, còn `COUNT(i.item_id)` bằng 0.

Nếu cần đếm số con, nên dùng `COUNT(child_primary_key)` thay cho `COUNT(*)` trong trường hợp LEFT JOIN.

### 5.3. COUNT(DISTINCT) có thể sửa số đếm, nhưng không sửa tổng tiền

Ví dụ:

```sql
SELECT COUNT(DISTINCT o.order_id) AS order_count,
       COUNT(*) AS joined_row_count
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

Cột đầu đếm số order khác nhau, cột sau đếm item rows. Cả hai đều đúng nếu hiểu đúng ý nghĩa.

Nhưng không nên nghĩ có thể sửa mọi phép tổng hợp bằng DISTINCT:

```sql
SELECT SUM(DISTINCT o.order_total)
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

`SUM(DISTINCT order_total)` loại giá trị tiền trùng nhau, không loại bản ghi order trùng theo khóa. Nếu hai đơn khác nhau cùng tổng tiền 300, một đơn có thể bị loại khỏi tổng. Đây là sai về nghiệp vụ.

Để sửa tổng tiền đơn hàng bị fanout, phải khôi phục đúng grain hoặc tổng hợp trước JOIN, không dùng SUM(DISTINCT measure) như một mẹo chung.

### 5.4. Đếm tổ hợp nhiều cột

Muốn đếm số cặp order-item duy nhất trong kết quả, có thể dùng:

```sql
SELECT COUNT(*) AS distinct_order_item_pairs
FROM (
    SELECT DISTINCT o.order_id, i.item_id
    FROM lab_orders o
    JOIN lab_order_items i
      ON i.order_id = o.order_id
);
```

Cách này minh bạch hơn việc nối các cột thành một chuỗi để COUNT DISTINCT, vốn có nguy cơ va chạm do dấu phân cách/format và chuyển kiểu.

## 6. SUM và fanout: lỗi cộng trùng thường gặp

### 6.1. Tổng item sau JOIN payments

Câu truy vấn dễ sai:

```sql
SELECT SUM(i.qty * i.unit_price) AS item_revenue
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id
WHERE p.payment_status = 'SETTLED';
```

Với order 1001 có 2 item và 2 payment, mỗi item bị lặp hai lần. Tổng item sẽ bị nhân lên.

Tương tự, `SUM(p.paid_amount)` cũng bị lặp theo số item.

### 6.2. Kiểm tra bằng số liệu nguồn trước

Tính tổng item trực tiếp từ bảng item:

```sql
SELECT SUM(qty * unit_price) AS source_item_total
FROM lab_order_items;
```

Tính tổng payment trực tiếp từ bảng payment:

```sql
SELECT SUM(paid_amount) AS source_payment_total
FROM lab_payments
WHERE payment_status = 'SETTLED';
```

Tính tổng order_total trực tiếp từ bảng order:

```sql
SELECT SUM(order_total) AS source_order_total
FROM lab_orders;
```

Đây là các baseline độc lập. Với dữ liệu lab:

- Tổng item = 500.
- Tổng payment SETTLED = 500.
- Tổng order_total = 500.

Trong hệ thống thực, ba tổng này không nhất thiết phải bằng nhau vì có thể có giảm giá, thuế, vận chuyển, payment chưa settle, refund, partial payment hoặc quy tắc ghi nhận doanh thu khác nhau. Điều cần làm là hiểu định nghĩa của từng measure.

### 6.3. Tính từng measure ở đúng grain

Tổng hợp item theo order:

```sql
SELECT order_id,
       SUM(qty * unit_price) AS item_total
FROM lab_order_items
GROUP BY order_id;
```

Tổng hợp payment theo order:

```sql
SELECT order_id,
       SUM(paid_amount) AS paid_total
FROM lab_payments
WHERE payment_status = 'SETTLED'
GROUP BY order_id;
```

Mỗi tập kết quả bây giờ có tối đa một dòng cho mỗi order. Khi JOIN hai tập này với orders, các measure đã ở cùng grain:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_total
    FROM lab_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           SUM(paid_amount) AS paid_total
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.order_total,
       NVL(i.item_total, 0) AS item_total,
       NVL(p.paid_total, 0) AS paid_total
FROM lab_orders o
LEFT JOIN item_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Vì mỗi CTE có tối đa một row cho mỗi order_id, JOIN không nhân các measure giữa item và payment.

**Điểm cốt lõi:** tổng hợp từng bảng con về cùng grain của bảng cha trước khi JOIN các bảng con độc lập.

### 6.4. Không dùng NVL trước khi hiểu NULL có nghĩa gì

`NVL(i.item_total, 0)` có nghĩa đơn hàng không có item được hiển thị như tổng item bằng 0. Đây có thể là quy tắc báo cáo phù hợp, nhưng cần phân biệt:

- Không có dòng item.
- Có dòng item nhưng dữ liệu measure NULL.
- Tổng thực sự bằng 0.

Nếu `unit_price` hoặc `qty` nullable, `qty * unit_price` có thể NULL và `SUM` bỏ qua biểu thức NULL. Với dữ liệu giao dịch, thường cần ràng buộc NOT NULL cho các thành phần bắt buộc và xử lý trạng thái thiếu rõ ràng.

## 7. Pre-aggregation: tổng hợp trước rồi mới JOIN

**Pre-aggregation** là tổng hợp dữ liệu ở bảng chi tiết về grain mục tiêu trước khi nối với các bảng khác.

### 7.1. Mô hình tổng hợp theo khóa cha

```text
ORDER_ITEMS
(many rows/order)
      |
      | GROUP BY order_id
      v
ITEM_TOTALS
(at most one row/order)

PAYMENTS
(many rows/order)
      |
      | GROUP BY order_id
      v
PAYMENT_TOTALS
(at most one row/order)

ORDERS
(one row/order)
      |
      +---- LEFT JOIN ITEM_TOTALS
      |
      +---- LEFT JOIN PAYMENT_TOTALS
```

### 7.2. CTE làm rõ grain

```sql
WITH
item_totals AS (
    SELECT order_id,
           COUNT(*) AS item_line_count,
           SUM(qty) AS total_units,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS settled_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       o.order_total,
       NVL(i.item_line_count, 0) AS item_line_count,
       NVL(i.total_units, 0) AS total_units,
       NVL(i.item_amount, 0) AS item_amount,
       NVL(p.payment_count, 0) AS payment_count,
       NVL(p.settled_amount, 0) AS settled_amount
FROM lab_orders o
LEFT JOIN item_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Đầu ra một dòng mỗi order, với các chỉ số đã được tổng hợp riêng.

### 7.3. CTE không tự bảo đảm một dòng mỗi khóa

Điều bảo đảm grain ở ví dụ là `GROUP BY order_id`, không phải việc dùng cú pháp WITH. Một CTE không có GROUP BY hoặc DISTINCT phù hợp vẫn có thể chứa nhiều dòng mỗi order_id.

Hãy tự xác nhận:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
)
SELECT order_id, COUNT(*) AS rows_per_order
FROM item_totals
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Kết quả đúng phải không có dòng. Đây là một kiểm chứng cardinality hữu ích trước khi JOIN.

### 7.4. Khi nào không cần pre-aggregation?

Nếu chỉ cần biết order có ít nhất một payment, không cần tổng payment, dùng `EXISTS`:

```sql
SELECT o.order_id, o.order_total
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'SETTLED'
);
```

Nếu cần từng payment detail, JOIN trực tiếp là đúng grain. Pre-aggregation chỉ cần khi mục tiêu đầu ra yêu cầu một dòng mỗi order hoặc khi cần kết hợp nhiều measure có grain độc lập.

## 8. LEFT JOIN và vị trí điều kiện WHERE/ON

Điều kiện lọc bảng con có thể làm thay đổi việc giữ lại dòng cha.

### 8.1. WHERE trên cột bảng con có thể biến LEFT JOIN thành INNER JOIN

Ví dụ:

```sql
SELECT o.order_id,
       p.payment_id,
       p.paid_amount
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
WHERE p.payment_status = 'SETTLED';
```

Điều kiện WHERE loại các hàng có `p.payment_status` NULL, vì thế các order không có payment không còn trong kết quả. Hành vi này gần như INNER JOIN đối với predicate đó.

Nếu muốn giữ mọi order và chỉ ghép các payment SETTLED:

```sql
SELECT o.order_id,
       p.payment_id,
       p.paid_amount
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED';
```

Điều kiện trạng thái nằm trong ON, nên order không có payment SETTLED vẫn xuất hiện với cột payment NULL.

### 8.2. COUNT sau LEFT JOIN

```sql
SELECT o.order_id,
       COUNT(*) AS joined_rows,
       COUNT(p.payment_id) AS settled_payment_count
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED'
GROUP BY o.order_id
ORDER BY o.order_id;
```

Nếu order không có payment phù hợp, LEFT JOIN vẫn tạo một dòng null-extended; do đó COUNT(*) là 1, còn COUNT(payment_id) là 0.

### 8.3. Lọc bảng con trước JOIN bằng CTE

```sql
WITH settled_payments AS (
    SELECT payment_id, order_id, paid_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
)
SELECT o.order_id,
       p.payment_id,
       p.paid_amount
FROM lab_orders o
LEFT JOIN settled_payments p
  ON p.order_id = o.order_id;
```

Cách này làm rõ tập payment được kết nối và dễ tái sử dụng. Về mặt tối ưu, Oracle có thể biến đổi/inline CTE; cách viết dễ đọc không nhất thiết buộc materialize.

## 9. Tổng hợp nhiều bảng: các mẫu đúng theo nhu cầu

### 9.1. Đếm order có ít nhất một payment

```sql
SELECT COUNT(*) AS orders_with_payment
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
);
```

Không cần JOIN tất cả payment detail nếu chỉ hỏi có/không.

### 9.2. Đếm số payment theo order

```sql
SELECT o.order_id,
       COUNT(p.payment_id) AS payment_count
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Mỗi payment là một dòng; COUNT khóa payment không NULL.

### 9.3. Tổng item theo khách hàng

Nếu mỗi khách có nhiều order và mỗi order có nhiều item, tổng hợp item theo order rồi nối order để lấy customer:

```sql
WITH item_by_order AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
)
SELECT o.customer_id,
       SUM(i.item_amount) AS customer_item_amount
FROM lab_orders o
JOIN item_by_order i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Nếu khách có order không có item và vẫn cần xuất hiện với tổng 0, dùng LEFT JOIN và NVL trong SUM theo yêu cầu báo cáo.

### 9.4. Tổng tiền đã thanh toán theo khách hàng

```sql
WITH paid_by_order AS (
    SELECT order_id,
           SUM(paid_amount) AS paid_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.customer_id,
       SUM(p.paid_amount) AS customer_paid_amount
FROM lab_orders o
JOIN paid_by_order p
  ON p.order_id = o.order_id
GROUP BY o.customer_id;
```

Không nối item detail vào query này nếu không cần; nếu nối thêm một bảng con nhiều dòng, payment measure có thể bị nhân lại.

### 9.5. Một truy vấn có nhiều chỉ số từ nhiều grain

```sql
WITH
items AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(qty) AS units,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payments AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS paid_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.order_total) AS booked_total,
       SUM(NVL(i.line_count, 0)) AS line_count,
       SUM(NVL(i.units, 0)) AS units,
       SUM(NVL(i.item_amount, 0)) AS item_amount,
       SUM(NVL(p.payment_count, 0)) AS payment_count,
       SUM(NVL(p.paid_amount, 0)) AS paid_amount
FROM lab_orders o
LEFT JOIN items i
  ON i.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
GROUP BY o.customer_id;
```

Do mỗi CTE có tối đa một dòng mỗi order, các measure không bị nhân giữa hai bảng con. `COUNT(*)` ở truy vấn cuối đếm order vì tập kết quả trước GROUP BY có một dòng mỗi order.

## 10. GROUP BY và lỗi chọn cột không đúng cấp độ

Khi tổng hợp sau JOIN, mọi cột trong SELECT không nằm trong hàm tổng hợp thường phải thuộc GROUP BY (theo cú pháp SQL Oracle).

Ví dụ:

```sql
SELECT o.customer_id,
       SUM(o.order_total) AS total_amount
FROM lab_orders o
GROUP BY o.customer_id;
```

Nếu thêm `o.order_id` vào SELECT mà không đưa vào GROUP BY hoặc một aggregate hợp lệ, Oracle báo lỗi như `ORA-00979: not a GROUP BY expression`.

Nhưng việc thêm mọi cột vào GROUP BY để “cho query chạy” có thể thay đổi grain và làm số dòng tăng. Cần hỏi:

- Đầu ra muốn một dòng mỗi customer hay mỗi order?
- Có thật sự cần hiển thị order_id không?
- Nếu cần một ví dụ order, phải xác định quy tắc chọn (MIN/MAX, analytic ranking, list aggregation...) thay vì tùy tiện GROUP BY.

Ví dụ muốn tổng theo customer, không đưa order_id vào GROUP BY:

```sql
SELECT o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.order_total) AS total_amount
FROM lab_orders o
GROUP BY o.customer_id;
```

## 11. DISTINCT: dùng đúng nơi, không che lỗi JOIN

`DISTINCT` loại các dòng trùng nhau theo **toàn bộ danh sách biểu thức SELECT**. Nó không biết khóa nghiệp vụ nào xác định một thực thể.

### 11.1. DISTINCT không sửa measure bị nhân

```sql
SELECT DISTINCT o.order_id,
       SUM(p.paid_amount)
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

SUM đã bị tính trên tập join nhân dòng; DISTINCT áp dụng sau đó không khôi phục được tổng đúng.

### 11.2. COUNT(DISTINCT key) cho câu hỏi đếm thực thể

```sql
SELECT COUNT(DISTINCT o.order_id) AS order_count
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

Đây là lựa chọn đúng khi câu hỏi là “có bao nhiêu order khác nhau xuất hiện trong kết quả JOIN?”. Tuy nhiên, nếu cần tổng order_total, phải tránh fanout hoặc tổng hợp về order trước.

### 11.3. DISTINCT có thể che dữ liệu trùng không mong muốn

Nếu một bảng được kỳ vọng một dòng mỗi customer nhưng JOIN tạo nhiều dòng vì bảng dimension có duplicate key, dùng DISTINCT có thể che lỗi chất lượng dữ liệu. Nên tìm khóa bị trùng:

```sql
SELECT customer_id,
       COUNT(*) AS rows_per_customer
FROM customer_profiles
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Sau đó xử lý constraint/dữ liệu nguồn thay vì che bằng DISTINCT ở mọi truy vấn.

## 12. Kiểm chứng cardinality trước khi tổng hợp

Một quy trình thực tế là đo số dòng từng bảng và số dòng sau từng bước JOIN.

### 12.1. Đếm bảng nguồn

```sql
SELECT 'ORDERS' AS source_name, COUNT(*) AS row_count
FROM lab_orders
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*)
FROM lab_order_items
UNION ALL
SELECT 'PAYMENTS', COUNT(*)
FROM lab_payments;
```

### 12.2. Đếm số dòng sau từng JOIN

```sql
SELECT COUNT(*) AS order_item_rows
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;

SELECT COUNT(*) AS order_payment_rows
FROM lab_orders o
JOIN lab_payments p
  ON p.order_id = o.order_id;

SELECT COUNT(*) AS item_payment_rows
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id;
```

Trong dữ liệu lab:

| Tập kết quả | Số dòng |
|---|---:|
| Orders | 2 |
| Items | 3 |
| Payments | 3 |
| Orders JOIN Items | 3 |
| Orders JOIN Payments | 3 |
| Orders JOIN Items JOIN Payments | 5 |

Vì order 1001 tạo 4 tổ hợp item-payment, order 1002 tạo 1 tổ hợp, tổng là 5.

### 12.3. Đếm theo từng khóa cha để tìm nơi fanout

```sql
SELECT o.order_id,
       COUNT(*) AS joined_rows,
       COUNT(DISTINCT i.item_id) AS item_count,
       COUNT(DISTINCT p.payment_id) AS payment_count
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Đơn 1001 có 4 joined rows, 2 item và 2 payment. Đơn 1002 có 1 joined row, 1 item và 1 payment. Đây là cách nhận diện fanout theo khóa, không chỉ nhìn tổng số dòng.

## 13. Kiểm tra quan hệ bằng constraint và truy vấn dữ liệu

### 13.1. PRIMARY KEY và UNIQUE

Nếu một bảng dimension được kỳ vọng một dòng mỗi customer, phải có ràng buộc:

```sql
ALTER TABLE customer_profiles
ADD CONSTRAINT uq_customer_profiles_customer
UNIQUE (customer_id);
```

Điều này chỉ phù hợp nếu nghiệp vụ thật sự một profile mỗi customer. Nếu bảng lưu nhiều phiên bản profile, cần xác định grain là một dòng mỗi customer-version và chọn bản hiệu lực bằng quy tắc thời gian.

### 13.2. FOREIGN KEY

Foreign key giúp đảm bảo khóa tham chiếu tồn tại ở bảng cha, nhưng **không đảm bảo một khóa cha chỉ có một dòng con**. Một FK từ ORDER_ITEMS.ORDER_ID đến ORDERS.ORDER_ID vẫn cho phép nhiều item cùng order.

### 13.3. Kiểm tra khóa con trùng

Nếu item_id là primary key thì không trùng item_id, nhưng một đơn có thể có nhiều dòng cùng product_id. Nếu nghiệp vụ không cho phép trùng sản phẩm trong một đơn, cần constraint khác:

```sql
ALTER TABLE order_items
ADD CONSTRAINT uq_order_product
UNIQUE (order_id, product_id);
```

Chỉ đặt unique khi quy tắc nghiệp vụ cho phép. Nhiều đơn hàng có thể chứa cùng product ở nhiều dòng vì khác giá, khuyến mãi hoặc lô hàng.

### 13.4. Kiểm tra quan hệ kỳ vọng 1:1 bằng SQL

```sql
SELECT employee_id,
       COUNT(*) AS profile_rows
FROM employee_profiles
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

Nếu kết quả có dòng, giả định 1:1 không đúng với dữ liệu hiện tại. Hãy tìm nguồn duplicate và quy tắc chọn bản ghi thay vì để JOIN âm thầm nhân dòng.

## 14. Tổng hợp có điều kiện và vị trí lọc

### 14.1. Conditional aggregation

Để đếm payment theo trạng thái:

```sql
SELECT order_id,
       COUNT(*) AS all_payment_count,
       SUM(CASE WHEN payment_status = 'SETTLED'
                THEN 1 ELSE 0 END) AS settled_count,
       SUM(CASE WHEN payment_status = 'FAILED'
                THEN 1 ELSE 0 END) AS failed_count,
       SUM(CASE WHEN payment_status = 'SETTLED'
                THEN paid_amount ELSE 0 END) AS settled_amount
FROM lab_payments
GROUP BY order_id;
```

Đây là tổng hợp trên đúng grain payment, nên mỗi payment chỉ được tính một lần.

### 14.2. Đừng lọc trạng thái sau khi đã JOIN fanout

Nếu tổng payment được tính sau khi JOIN item detail, cùng một payment có thể xuất hiện nhiều lần. Điều kiện `payment_status = 'SETTLED'` chỉ loại payment không settled; nó không ngăn payment settled bị lặp theo số item.

Lọc và tổng hợp trong bảng payment trước khi nối với item/order.

### 14.3. COUNT có điều kiện với NULL

Ví dụ:

```sql
COUNT(CASE WHEN payment_status = 'SETTLED'
           THEN payment_id END)
```

đếm số payment SETTLED vì các dòng không phù hợp trả NULL và COUNT bỏ qua NULL. Có thể dùng SUM(CASE...) như ví dụ trên. Chọn cách viết dễ đọc và đảm bảo xử lý NULL đúng.

## 15. Đối soát số liệu (reconciliation)

Một truy vấn báo cáo nên có cách kiểm chứng độc lập với nguồn dữ liệu.

### 15.1. So sánh tổng theo từng cấp

Tổng order:

```sql
SELECT SUM(order_total) AS order_total_sum
FROM lab_orders;
```

Tổng item:

```sql
SELECT SUM(qty * unit_price) AS item_total_sum
FROM lab_order_items;
```

Tổng payment theo trạng thái:

```sql
SELECT payment_status,
       COUNT(*) AS payment_count,
       SUM(paid_amount) AS payment_sum
FROM lab_payments
GROUP BY payment_status;
```

Đây là ba measure khác nhau. Chỉ so sánh khi định nghĩa nghiệp vụ cho biết chúng phải bằng nhau. Nếu order_total đã gồm thuế/ship nhưng item total chưa gồm, không thể kết luận lệch chỉ vì hai tổng khác nhau.

### 15.2. Đối soát theo từng order

```sql
WITH
items AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payments AS (
    SELECT order_id,
           SUM(CASE WHEN payment_status = 'SETTLED'
                    THEN paid_amount ELSE 0 END) AS settled_amount
    FROM lab_payments
    GROUP BY order_id
)
SELECT o.order_id,
       o.order_total,
       NVL(i.item_amount, 0) AS item_amount,
       NVL(p.settled_amount, 0) AS settled_amount,
       o.order_total - NVL(i.item_amount, 0) AS order_item_diff,
       o.order_total - NVL(p.settled_amount, 0) AS order_paid_diff
FROM lab_orders o
LEFT JOIN items i
  ON i.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Nếu quy tắc yêu cầu order_total bằng item_amount và payment đã settled, có thể lọc các sai lệch:

```sql
WITH
items AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payments AS (
    SELECT order_id,
           SUM(CASE WHEN payment_status = 'SETTLED'
                    THEN paid_amount ELSE 0 END) AS settled_amount
    FROM lab_payments
    GROUP BY order_id
)
SELECT o.order_id
FROM lab_orders o
LEFT JOIN items i
  ON i.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
WHERE o.order_total <> NVL(i.item_amount, 0)
   OR o.order_total <> NVL(p.settled_amount, 0);
```

Trong hệ thống thật, phép đối soát cần xét refund, chargeback, payment pending, discount, tax, shipping và quy tắc ghi nhận doanh thu. Không mặc định mọi order phải được thanh toán đủ ngay lập tức.

### 15.3. Kiểm tra missing rows

Tìm order không có item:

```sql
SELECT o.order_id
FROM lab_orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_order_items i
    WHERE i.order_id = o.order_id
);
```

Tìm item mồ côi nếu dữ liệu được nạp vào staging không có FK:

```sql
SELECT i.item_id, i.order_id
FROM lab_order_items_stage i
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.order_id = i.order_id
);
```

Tìm orphan/missing giúp phân biệt tổng sai do fanout với tổng sai do dữ liệu nguồn thiếu.

## 16. AVG, MIN, MAX và các phép tổng hợp khác sau JOIN

Fanout không chỉ ảnh hưởng SUM và COUNT.

### 16.1. AVG có thể bị thay đổi trọng số

Giả sử muốn tính trung bình order_total theo customer. Nếu JOIN order với item rồi tính:

```sql
SELECT o.customer_id,
       AVG(o.order_total) AS avg_order_total
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Mỗi order được lặp theo số item. Kết quả là **trung bình có trọng số theo số dòng item**, không còn là trung bình mỗi order.

Cách đúng nếu muốn mỗi order có trọng số bằng nhau:

```sql
SELECT customer_id,
       AVG(order_total) AS avg_order_total
FROM lab_orders
GROUP BY customer_id;
```

Hoặc tổng hợp ở grain order trước, rồi mới nối các dimension có quan hệ tối đa 1:1.

### 16.2. MIN/MAX đôi khi không đổi nhưng vẫn không chứng minh query đúng

Lặp lại cùng một giá trị nhiều lần thường không làm thay đổi MIN hoặc MAX. Tuy nhiên, nếu JOIN làm mất dòng (INNER JOIN) hoặc điều kiện lọc loại dữ liệu, kết quả vẫn có thể sai.

Đừng dùng việc MIN/MAX “trông đúng” làm bằng chứng rằng cardinality JOIN đúng.

### 16.3. COUNT và SUM có tính chất khác nhau

- `COUNT(DISTINCT order_id)` có thể đếm thực thể duy nhất trong tập JOIN.
- `SUM(DISTINCT amount)` khử các giá trị số trùng nhau, không khử bản ghi trùng theo khóa.
- `AVG(DISTINCT amount)` tính trung bình các giá trị khác nhau, không phải trung bình mỗi thực thể.
- `MIN`/`MAX` ít nhạy với lặp giá trị nhưng vẫn nhạy với mất dòng/lọc sai.

Luôn xác định đơn vị được tính trước khi chọn aggregate.

## 17. Execution plan và cardinality estimate

Oracle optimizer ước lượng số dòng trung gian của từng bước JOIN. Những ước lượng này ảnh hưởng đến thứ tự join, join method và access path.

### 17.1. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT o.order_id,
       i.item_id,
       p.payment_id
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Trong plan, chú ý:

- `E-Rows`: số dòng optimizer ước lượng.
- `A-Rows`: số dòng thực tế trong plan runtime khi dùng nguồn thống kê thực thi phù hợp.
- `Starts`: số lần một operation được khởi chạy.
- `Buffers`/I/O: lượng công việc đọc liên quan.

`EXPLAIN PLAN` thường cho plan ước tính; để xem actual rows, cần thực thi truy vấn với thu thập thống kê phù hợp và đọc cursor plan qua `DBMS_XPLAN.DISPLAY_CURSOR` khi có quyền.

### 17.2. Cardinality estimate sai không đồng nghĩa SQL tổng hợp sai

Có hai vấn đề riêng:

1. **Sai số liệu logic:** JOIN fanout khiến SUM/COUNT không phản ánh nghiệp vụ.
2. **Ước lượng optimizer sai:** E-Rows khác xa A-Rows, có thể khiến execution plan kém hiệu quả.

Một truy vấn có thể đúng logic nhưng chạy chậm vì estimate sai. Một truy vấn có plan rất nhanh vẫn có thể trả tổng tiền sai vì fanout. Cần kiểm tra cả hai.

### 17.3. Thống kê và constraint hỗ trợ optimizer

Primary key, unique constraint, foreign key và statistics cung cấp thông tin về quan hệ/cardi­nality. Tuy nhiên, optimizer chỉ có thể ước lượng dựa trên metadata và statistics có sẵn; nó không thay thế việc người thiết kế hiểu grain.

Nếu dữ liệu phân bố lệch hoặc có tương quan giữa các cột, histogram/extended statistics có thể giúp ước lượng trong những trường hợp phù hợp. Chỉ thu thập/thay đổi statistics theo quy trình DBA và workload.

## 18. Các lỗi thiết kế thường gặp

### 18.1. JOIN hai bảng con rồi cộng cả hai measure

**Vấn đề:** item và payment độc lập cùng liên kết tới order; các dòng nhân chéo.

**Sửa:** aggregate từng bảng con theo order trước khi JOIN.

### 18.2. Dùng COUNT(*) để đếm bảng cha sau JOIN 1:N

**Vấn đề:** đang đếm dòng chi tiết, không phải thực thể cha.

**Sửa:** COUNT DISTINCT khóa cha, EXISTS, hoặc aggregate child trước.

### 18.3. Dùng SUM(DISTINCT amount) để loại dòng trùng

**Vấn đề:** hai thực thể khác nhau có thể có cùng amount; một giá trị bị loại sai.

**Sửa:** loại fanout theo khóa/grain, không theo giá trị measure.

### 18.4. Đưa cột chi tiết vào GROUP BY để hết lỗi

**Vấn đề:** thay đổi grain, tạo thêm nhóm và làm số dòng tăng.

**Sửa:** quyết định grain đầu ra, tổng hợp ở cấp đúng; dùng analytic/list aggregation nếu thực sự cần chi tiết.

### 18.5. Dùng LEFT JOIN nhưng lọc child ở WHERE

**Vấn đề:** dòng cha không có child bị loại.

**Sửa:** chuyển điều kiện phù hợp vào ON hoặc lọc child trong CTE/subquery trước JOIN.

### 18.6. Không ràng buộc uniqueness của dimension

**Vấn đề:** giả định 1:1 nhưng bảng lookup có duplicate key.

**Sửa:** kiểm tra dữ liệu và áp dụng UNIQUE/PRIMARY KEY nếu nghiệp vụ yêu cầu.

### 18.7. So sánh các tổng không cùng định nghĩa

**Vấn đề:** order total, item subtotal và settled payment có thể khác vì thuế, giảm giá, ship, refund hoặc trạng thái giao dịch.

**Sửa:** viết định nghĩa measure và trạng thái được tính trước khi đối soát.

### 18.8. Tin CTE tự loại dòng trùng

**Vấn đề:** WITH chỉ đặt tên cho một query block; không tự đảm bảo unique grain.

**Sửa:** GROUP BY/DISTINCT/constraint phù hợp và kiểm tra số dòng mỗi khóa.

## 19. Quy trình kiểm chứng một truy vấn tổng hợp nhiều bảng

Có thể áp dụng tuần tự trước khi đưa báo cáo vào production:

1. **Ghi grain mong muốn của đầu ra.** Ví dụ một dòng mỗi order hoặc mỗi customer-tháng.
2. **Ghi grain của từng bảng nguồn.** Một dòng mỗi order, item, payment hay event.
3. **Xác định quan hệ JOIN.** Khóa PK/FK, unique hay không, quan hệ 1:1/1:N/N:M.
4. **Đếm số dòng nguồn và số khóa khác nhau.** Dùng COUNT(*), COUNT(DISTINCT key).
5. **Đếm số dòng sau từng JOIN.** Tìm bước cardinality tăng bất thường.
6. **Kiểm tra fanout theo khóa cha.** So sánh child count của từng bảng.
7. **Xác định measure thuộc bảng/grain nào.** Order total, item amount, payment amount không mặc nhiên cộng chung.
8. **Pre-aggregate bảng con độc lập.** GROUP BY khóa cha để có tối đa một dòng mỗi khóa.
9. **JOIN tập đã tổng hợp.** Dùng LEFT/INNER theo quy tắc giữ dòng cha.
10. **Chọn aggregate đúng.** COUNT(*) hay COUNT(child_key), SUM/AVG ở grain thích hợp.
11. **Đối soát độc lập.** So sánh tổng nguồn, tổng sau JOIN và chênh lệch theo từng khóa.
12. **Xem execution plan.** Tách vấn đề correctness khỏi vấn đề performance.
13. **Kiểm thử dữ liệu biên.** Cha không có con, một con, nhiều con, nhiều bảng con cùng lúc, giá trị NULL và duplicate key.

## 20. Bài thực hành tổng hợp

### Bài 1 — Tìm fanout

Dùng ba bảng `LAB_ORDERS`, `LAB_ORDER_ITEMS`, `LAB_PAYMENTS` ở mục 4.

Viết truy vấn trả về:

- Số dòng order.
- Số dòng item.
- Số dòng payment.
- Số dòng order-item.
- Số dòng order-payment.
- Số dòng order-item-payment.

Giải thích vì sao số dòng cuối là 5 dù chỉ có 2 order.

### Bài 2 — Tổng item và payment bị nhân

Viết truy vấn JOIN ba bảng rồi tính cả:

- `SUM(qty * unit_price)`.
- `SUM(paid_amount)`.

So sánh với tổng trực tiếp từ từng bảng nguồn. Xác định order nào tạo fanout và số nhân tương ứng.

### Bài 3 — Sửa bằng pre-aggregation

Viết CTE `item_totals` và `payment_totals`, mỗi CTE có một dòng tối đa trên mỗi order_id. JOIN hai CTE với `LAB_ORDERS`. Chứng minh bằng query GROUP BY/HAVING rằng không có khóa nào xuất hiện nhiều lần trong từng CTE.

### Bài 4 — Phân biệt COUNT(*), COUNT(key), COUNT(DISTINCT key)

Thêm một order không có item và một order không có payment (nếu điều chỉnh bảng lab). Dùng LEFT JOIN để tính ba dạng COUNT. Giải thích tại sao COUNT(*) có thể bằng 1 dù số item bằng 0.

### Bài 5 — Kiểm tra AVG bị đổi trọng số

Tạo hai order cho cùng một customer:

- Order A có tổng 100 và một item.
- Order B có tổng 300 và ba item.

Tính AVG(order_total) trực tiếp từ orders, sau đó JOIN items và tính lại. Giải thích vì sao hai kết quả khác nhau và truy vấn nào phản ánh trung bình mỗi order.

### Bài 6 — LEFT JOIN và predicate

Viết hai câu:

1. LEFT JOIN payments rồi lọc `payment_status = 'SETTLED'` ở WHERE.
2. Đưa predicate trạng thái vào ON.

Thêm một order chưa có payment và giải thích câu nào vẫn giữ order đó.

### Bài 7 — Kiểm tra duplicate ở bảng được kỳ vọng 1:1

Tạo staging profile có hai dòng cho cùng employee_id. Viết query GROUP BY/HAVING tìm duplicate. Đề xuất constraint phù hợp nếu nghiệp vụ thực sự chỉ có một profile mỗi nhân viên.

### Bài 8 — Đối soát theo order

Tính order_total, item_amount và settled_amount theo từng order. Trả về các order có chênh lệch theo quy tắc được định nghĩa. Giải thích vì sao trong hệ thống thực không thể tự kết luận payment phải bằng order_total nếu có refund, pending hoặc thanh toán từng phần.

## 21. Sơ đồ lựa chọn cách JOIN và tổng hợp

```text
Mục tiêu đầu ra là gì?
|
+-- Một dòng cho mỗi bản ghi cha?
|      |
|      +-- Chỉ cần biết có con?
|      |      └── EXISTS / NOT EXISTS
|      |
|      +-- Cần đếm hoặc cộng một bảng con?
|      |      └── GROUP BY child theo parent key
|      |
|      +-- Cần measure từ nhiều bảng con độc lập?
|             └── Pre-aggregate từng child
|                 rồi JOIN với parent
|
+-- Một dòng cho mỗi bản ghi chi tiết?
|      |
|      └── JOIN trực tiếp theo grain chi tiết;
|          không cộng measure cha lặp lại
|
+-- Một dòng cho mỗi customer/tháng/nhóm?
       |
       └── Xác định grain nguồn -> tổng hợp đúng cấp
           -> JOIN dimension có cardinality được kiểm soát
           -> GROUP BY grain cuối cùng
```

## 22. Ghi nhớ khi vận hành

- **Grain** mô tả một dòng đại diện cho điều gì; phải xác định trước khi JOIN và aggregate.
- **1:N** làm dòng cha lặp theo số con; JOIN nhiều bảng con độc lập có thể tạo tích số dòng.
- **COUNT(*)** đếm dòng kết quả JOIN, không tự đếm thực thể nghiệp vụ.
- **COUNT(child_key)** hữu ích với LEFT JOIN để đếm số dòng con không NULL.
- **COUNT(DISTINCT parent_key)** đếm thực thể cha khác nhau trong tập kết quả.
- **SUM(DISTINCT amount)** không phải cách sửa tổng bị nhân; nó có thể loại các giao dịch hợp lệ có cùng giá trị.
- **Pre-aggregation** từng bảng con về cùng grain trước khi JOIN là cách phổ biến để tránh fanout.
- **EXISTS** phù hợp khi chỉ cần kiểm tra có bản ghi liên quan.
- Điều kiện child ở **WHERE** có thể loại dòng null-extended của LEFT JOIN; cân nhắc ON hoặc CTE.
- **CTE không tự đảm bảo uniqueness**; GROUP BY/DISTINCT/constraint mới xác định cardinality.
- Đối soát phải so sánh các measure có định nghĩa nghiệp vụ tương thích.
- Phân biệt **sai số liệu logic** với **cardinality estimate/hiệu năng** trong execution plan.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Joins, aggregate functions, GROUP BY, HAVING, subqueries, EXISTS và analytic functions.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Constraints, primary/foreign keys, unique keys và optimizer.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Cardinality estimates, join methods, execution plans và optimizer statistics.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — Fact/dimension grain, measures và aggregation trong báo cáo.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_XPLAN và công cụ đọc execution plan.

Các ví dụ dùng cú pháp SQL phổ biến trong Oracle Database. Quy mô bảng, statistics, index, phiên bản và dữ liệu thực tế có thể làm execution plan khác nhau; luôn kiểm chứng số liệu ở grain nghiệp vụ và đo plan trên workload đại diện.

