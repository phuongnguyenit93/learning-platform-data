# Phân biệt WHERE và HAVING trong Oracle SQL

Khi viết truy vấn có `GROUP BY`, hai mệnh đề `WHERE` và `HAVING` đều có thể dùng để lọc dữ liệu, nhưng chúng lọc ở **hai thời điểm logic khác nhau**. `WHERE` chọn những dòng được phép tham gia vào quá trình gom nhóm; `HAVING` chọn những nhóm đã được tạo sau khi Oracle tính các hàm tổng hợp như `COUNT`, `SUM` hoặc `AVG`.

Nếu đặt điều kiện sai chỗ, truy vấn có thể loại mất khách hàng cần giữ, tính tổng thiếu dòng, hoặc báo lỗi khi đưa hàm tổng hợp vào `WHERE`. Cách hiểu chắc nhất là dùng một bộ dữ liệu nhỏ, tự xác định dòng nào đi qua `WHERE`, nhóm nào được tạo bởi `GROUP BY`, rồi kiểm tra nhóm nào còn lại sau `HAVING`.

Bài học dùng Oracle Database và một ví dụ bán hàng có khách hàng, đơn hàng, trạng thái và ngày phát sinh. Ta sẽ phân tích cú pháp, dự đoán kết quả, chạy các biến thể và nhận diện những trường hợp hai mệnh đề không thể thay thế cho nhau.

## 1. Khác biệt cốt lõi

| Mệnh đề | Lọc đối tượng nào? | Thời điểm logic | Dùng hàm tổng hợp? | Ví dụ |
|---|---|---|---|---|
| `WHERE` | Dòng dữ liệu đầu vào | Sau `FROM/JOIN`, trước `GROUP BY` | Không dùng trực tiếp aggregate của query block hiện tại | `WHERE order_status = 'PAID'` |
| `HAVING` | Nhóm dữ liệu đã gom | Sau `GROUP BY` | Có thể dùng `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` | `HAVING SUM(amount) >= 200` |

Hãy đọc hai câu sau:

~~~sql
-- Giữ các đơn đã thanh toán trước khi gom nhóm.
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_order
WHERE order_status = 'PAID'
GROUP BY customer_id;

-- Chỉ giữ khách có tổng tiền đã thanh toán từ 200 trở lên.
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) >= 200;
~~~

Câu đầu tiên chọn dòng đơn hàng theo trạng thái, sau đó cộng tiền theo khách. Câu thứ hai làm đúng các bước đó, rồi **loại những nhóm có tổng tiền nhỏ hơn 200**.

Một câu ghi nhớ:

- `WHERE`: *Dòng nào được tham gia vào phép tính?*
- `HAVING`: *Sau khi tính xong từng nhóm, nhóm nào được giữ lại?*

## 2. Tạo dữ liệu tối thiểu để kiểm chứng

Ta cần dữ liệu có đủ trường hợp để phân biệt hai mệnh đề:

- Một khách có nhiều đơn đã thanh toán.
- Một khách có đơn bị hủy và đang chờ.
- Một khách chỉ có một đơn đã thanh toán với tổng lớn.
- Một khách không có đơn nào.
- Một khách có đơn nhưng không có đơn đã thanh toán.
- Có đơn nằm ngoài khoảng ngày báo cáo.

### 2.1. Tạo bảng lab

Chạy các câu lệnh trong schema lab của một PDB thực hành. Nếu đã có bảng cùng tên, hãy dùng tên lab khác thay vì ghi đè đối tượng đang tồn tại.

~~~sql
CREATE TABLE lab_wh_customer (
    customer_id   NUMBER(5) PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR) NOT NULL,
    active_flag   CHAR(1 CHAR) NOT NULL,
    CONSTRAINT ck_lab_wh_customer_active
      CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_wh_order (
    order_id     NUMBER(5) PRIMARY KEY,
    customer_id  NUMBER(5) NOT NULL,
    order_status VARCHAR2(20 CHAR) NOT NULL,
    amount       NUMBER(10,2) NOT NULL,
    order_date   DATE NOT NULL,
    CONSTRAINT fk_lab_wh_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_wh_customer (customer_id),
    CONSTRAINT ck_lab_wh_order_status
      CHECK (order_status IN ('PAID', 'CANCELLED', 'PENDING')),
    CONSTRAINT ck_lab_wh_order_amount
      CHECK (amount >= 0)
);
~~~

`LAB_WH_CUSTOMER` lưu khách hàng; `LAB_WH_ORDER` lưu từng đơn. Mỗi đơn thuộc một khách hàng, nhưng một khách có thể có nhiều đơn hoặc chưa có đơn nào.

### 2.2. Chèn khách hàng

~~~sql
INSERT INTO lab_wh_customer VALUES (1, 'An',   'Y');
INSERT INTO lab_wh_customer VALUES (2, 'Binh', 'Y');
INSERT INTO lab_wh_customer VALUES (3, 'Chi',  'N');
INSERT INTO lab_wh_customer VALUES (4, 'Dung', 'Y');
INSERT INTO lab_wh_customer VALUES (5, 'Em',   'Y');
~~~

### 2.3. Chèn đơn hàng

~~~sql
INSERT INTO lab_wh_order VALUES
  (101, 1, 'PAID',      120, DATE '2026-01-03');

INSERT INTO lab_wh_order VALUES
  (102, 1, 'PAID',      130, DATE '2026-01-10');

INSERT INTO lab_wh_order VALUES
  (103, 1, 'CANCELLED', 500, DATE '2026-01-11');

INSERT INTO lab_wh_order VALUES
  (104, 1, 'PENDING',    40, DATE '2026-02-02');

INSERT INTO lab_wh_order VALUES
  (201, 2, 'PAID',       80, DATE '2026-01-04');

INSERT INTO lab_wh_order VALUES
  (202, 2, 'PAID',      120, DATE '2026-01-25');

INSERT INTO lab_wh_order VALUES
  (203, 2, 'PAID',      100, DATE '2026-02-02');

INSERT INTO lab_wh_order VALUES
  (301, 3, 'PAID',      400, DATE '2026-01-15');

INSERT INTO lab_wh_order VALUES
  (302, 3, 'CANCELLED',  50, DATE '2026-01-16');

INSERT INTO lab_wh_order VALUES
  (501, 5, 'CANCELLED', 600, DATE '2026-01-18');

INSERT INTO lab_wh_order VALUES
  (502, 5, 'PENDING',    70, DATE '2026-01-20');

COMMIT;
~~~

### 2.4. Xem dữ liệu nguồn

~~~sql
SELECT customer_id, customer_name, active_flag
FROM lab_wh_customer
ORDER BY customer_id;

SELECT order_id, customer_id, order_status, amount, order_date
FROM lab_wh_order
ORDER BY order_id;
~~~

Tóm tắt khách hàng:

| CUSTOMER_ID | CUSTOMER_NAME | ACTIVE_FLAG |
|---:|---|:---:|
| 1 | An | Y |
| 2 | Binh | Y |
| 3 | Chi | N |
| 4 | Dung | Y |
| 5 | Em | Y |

Tóm tắt đơn hàng:

| ORDER_ID | CUSTOMER_ID | STATUS | AMOUNT | ORDER_DATE |
|---:|---:|---|---:|---|
| 101 | 1 | PAID | 120 | 2026-01-03 |
| 102 | 1 | PAID | 130 | 2026-01-10 |
| 103 | 1 | CANCELLED | 500 | 2026-01-11 |
| 104 | 1 | PENDING | 40 | 2026-02-02 |
| 201 | 2 | PAID | 80 | 2026-01-04 |
| 202 | 2 | PAID | 120 | 2026-01-25 |
| 203 | 2 | PAID | 100 | 2026-02-02 |
| 301 | 3 | PAID | 400 | 2026-01-15 |
| 302 | 3 | CANCELLED | 50 | 2026-01-16 |
| 501 | 5 | CANCELLED | 600 | 2026-01-18 |
| 502 | 5 | PENDING | 70 | 2026-01-20 |

Các điểm cần chú ý:

- An có hai đơn PAID trong tháng 1, tổng 250; còn có một đơn CANCELLED và một đơn PENDING.
- Binh có hai đơn PAID trong tháng 1, tổng 200, và một đơn PAID trong tháng 2.
- Chi có đơn PAID 400 trong tháng 1 nhưng đang không hoạt động.
- Dung không có đơn.
- Em có đơn nhưng không có đơn PAID.

Bộ dữ liệu này đủ để quan sát riêng tác động của `WHERE`, `GROUP BY` và `HAVING`.

## 3. WHERE lọc dòng trước khi gom nhóm

Yêu cầu: chỉ lấy những đơn đã thanh toán trong tháng 1 năm 2026.

~~~sql
SELECT
    order_id,
    customer_id,
    amount,
    order_date
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
ORDER BY customer_id, order_id;
~~~

`WHERE` kiểm tra **từng dòng đơn hàng**. Các đơn không thỏa điều kiện bị loại trước khi bất kỳ nhóm nào được tạo.

| ORDER_ID | CUSTOMER_ID | AMOUNT | Giữ lại? | Lý do |
|---:|---:|---:|:---:|---|
| 101 | 1 | 120 | Có | PAID, ngày thuộc tháng 1 |
| 102 | 1 | 130 | Có | PAID, ngày thuộc tháng 1 |
| 103 | 1 | 500 | Không | CANCELLED |
| 104 | 1 | 40 | Không | PENDING và tháng 2 |
| 201 | 2 | 80 | Có | PAID, ngày thuộc tháng 1 |
| 202 | 2 | 120 | Có | PAID, ngày thuộc tháng 1 |
| 203 | 2 | 100 | Không | PAID nhưng tháng 2 |
| 301 | 3 | 400 | Có | PAID, ngày thuộc tháng 1 |
| 302 | 3 | 50 | Không | CANCELLED |
| 501 | 5 | 600 | Không | CANCELLED |
| 502 | 5 | 70 | Không | PENDING |

Sau `WHERE`, còn năm dòng: 101, 102, 201, 202 và 301. Những dòng này mới là đầu vào cho `GROUP BY`.

### 3.1. Vì sao dùng khoảng ngày nửa mở?

Điều kiện:

~~~sql
order_date >= DATE '2026-01-01'
AND order_date < DATE '2026-02-01'
~~~

chọn mọi thời điểm từ đầu ngày 1/1 đến trước đầu ngày 1/2. Kiểu Oracle `DATE` có cả giờ, phút và giây; nếu dùng:

~~~sql
order_date BETWEEN DATE '2026-01-01'
               AND DATE '2026-01-31'
~~~

thì đầu mút 31/1 tương đương 31/1 lúc `00:00:00`, có thể bỏ các đơn phát sinh trong phần còn lại của ngày 31/1. Khoảng nửa mở thường dễ dùng cho báo cáo theo ngày/tháng và tránh phụ thuộc vào việc tự tạo “giây cuối cùng” của ngày.

Literal `DATE 'YYYY-MM-DD'` cũng tránh việc chuỗi ngày bị diễn giải theo `NLS_DATE_FORMAT` của session.

## 4. GROUP BY tạo nhóm như thế nào?

Sau khi `WHERE` giữ lại năm dòng, ta gom theo khách hàng:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
ORDER BY customer_id;
~~~

Oracle tạo một nhóm cho mỗi `CUSTOMER_ID` xuất hiện trong tập dòng đã lọc:

| CUSTOMER_ID | ORDER_ID trong nhóm | COUNT(*) | SUM(AMOUNT) |
|---:|---|---:|---:|
| 1 | 101, 102 | 2 | 250 |
| 2 | 201, 202 | 2 | 200 |
| 3 | 301 | 1 | 400 |

Không có nhóm cho khách 4 hoặc 5 vì truy vấn đang lấy bảng đơn hàng và `WHERE` không giữ dòng nào của hai khách đó. `GROUP BY` không tự tạo nhóm cho một khách chưa có đơn.

### 4.1. Quy tắc SELECT khi có GROUP BY

Trong một query block có `GROUP BY`, biểu thức trong `SELECT` thường phải thuộc một trong các loại:

- Là biểu thức được liệt kê trong `GROUP BY`.
- Là biểu thức tổng hợp như `COUNT(*)`, `SUM(amount)`, `AVG(amount)`.
- Là biểu thức hợp lệ được tạo từ các biểu thức nhóm và aggregate theo quy tắc SQL của Oracle.

Ví dụ hợp lệ:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
GROUP BY customer_id;
~~~

Ví dụ không hợp lệ:

~~~sql
SELECT customer_id, order_id, SUM(amount)
FROM lab_wh_order
GROUP BY customer_id;
~~~

`ORDER_ID` không được gom nhóm và cũng không nằm trong hàm tổng hợp. Một nhóm khách có nhiều order_id nên Oracle không biết phải chọn order_id nào đại diện. Câu lệnh có thể gặp `ORA-00979: not a GROUP BY expression`.

## 5. HAVING lọc nhóm sau khi đã tính aggregate

Yêu cầu tiếp theo: chỉ giữ những khách có **ít nhất hai đơn PAID trong tháng 1**.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

`HAVING COUNT(*) >= 2` được đánh giá trên **từng nhóm đã tạo**:

| CUSTOMER_ID | COUNT(*) | Điều kiện HAVING | Giữ nhóm? |
|---:|---:|---|:---:|
| 1 | 2 | 2 >= 2 | Có |
| 2 | 2 | 2 >= 2 | Có |
| 3 | 1 | 1 >= 2 | Không |

Kết quả:

| CUSTOMER_ID | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---:|---:|
| 1 | 2 | 250 |
| 2 | 2 | 200 |

Điểm quan trọng: `HAVING` không xóa riêng một đơn trong nhóm. Nó quyết định **giữ hay loại cả nhóm**. Chi có đơn PAID 400, nhưng nhóm của Chi chỉ có một đơn nên bị loại bởi điều kiện “ít nhất hai đơn”.

### 5.1. Lọc theo tổng tiền

Nếu yêu cầu là khách có tổng tiền PAID tháng 1 ít nhất 220:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
HAVING SUM(amount) >= 220
ORDER BY paid_total DESC;
~~~

Kết quả:

| CUSTOMER_ID | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---:|---:|
| 3 | 1 | 400 |
| 1 | 2 | 250 |

Chi có tổng 400 và An có tổng 250; Binh có 200 nên không đạt ngưỡng. Điều kiện này kiểm tra **tổng tiền của nhóm**, không kiểm tra từng đơn có amount từ 220 trở lên.

### 5.2. Kết hợp nhiều điều kiện HAVING

Có thể kết hợp điều kiện trên số dòng và tổng:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 220
ORDER BY paid_total DESC;
~~~

Kết quả chỉ có An: An có hai đơn và tổng 250; Binh có hai đơn nhưng tổng 200; Chi có tổng 400 nhưng chỉ có một đơn. Cả hai điều kiện đều phải TRUE để nhóm được giữ.

## 6. Đặt điều kiện ở WHERE hay HAVING?

Một số điều kiện có thể viết ở cả hai vị trí về mặt cú pháp, nhưng ngữ nghĩa và hiệu quả có thể khác.

### 6.1. Điều kiện lọc dòng: đặt trong WHERE

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id;
~~~

Đây là cách đúng khi ý định là **chỉ cộng những dòng PAID**. Điều kiện trạng thái được áp dụng trước khi tính tổng.

### 6.2. Điều kiện lọc nhóm: đặt trong HAVING

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) >= 200;
~~~

Ý định là **cộng các dòng PAID của từng khách rồi chỉ giữ khách có tổng đạt ngưỡng**.

### 6.3. Điều kiện trên cột nhóm có thể đặt ở WHERE

Nếu chỉ muốn xem khách số 1:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND customer_id = 1
GROUP BY customer_id;
~~~

Vì `CUSTOMER_ID` là điều kiện chọn dòng đầu vào, đặt ở `WHERE` là tự nhiên và thường giúp giảm số dòng cần gom nhóm. Nếu viết điều kiện trên cột nhóm trong `HAVING`, Oracle có thể chấp nhận khi biểu thức phù hợp với quy tắc GROUP BY:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING customer_id = 1;
~~~

Hai câu có thể cho cùng kết quả trong trường hợp này. Tuy nhiên, điều kiện chỉ phụ thuộc vào giá trị từng dòng như `customer_id = 1` thường nên đặt trong `WHERE`, còn `HAVING` dành cho điều kiện thực sự phụ thuộc vào nhóm hoặc aggregate. Cách viết này giúp ý định rõ và có thể giảm dữ liệu đầu vào.

### 6.4. Một điều kiện không thể chuyển vị trí mà vẫn giữ nguyên kết quả

So sánh:

**A — lọc từng đơn có amount từ 100 trở lên, rồi cộng:**

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
  AND amount >= 100
GROUP BY customer_id
ORDER BY customer_id;
~~~

Với Binh, đơn 201 có amount 80 bị loại trước khi nhóm. Chỉ đơn 202 amount 120 còn lại, nên tổng của Binh là 120.

**B — cộng tất cả đơn PAID tháng 1, rồi chỉ giữ nhóm có tổng từ 100 trở lên:**

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING SUM(amount) >= 100
ORDER BY customer_id;
~~~

Với Binh, cả 80 và 120 đều tham gia tổng, nên tổng là 200. Điều kiện `amount >= 100` ở A và điều kiện `SUM(amount) >= 100` ở B **không tương đương**:

| Truy vấn | Binh tham gia tính tổng | Kết quả Binh |
|---|---|---:|
| A: lọc amount trong WHERE | Chỉ đơn 202 = 120 | 120 |
| B: lọc SUM trong HAVING | Đơn 201 = 80 và 202 = 120 | 200 |

Đây là ví dụ quan trọng để tránh chuyển một điều kiện từ WHERE sang HAVING chỉ vì cả hai đều có thể “lọc”.

## 7. Vì sao không đặt SUM hoặc COUNT trong WHERE?

Ví dụ sau không hợp lệ:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
WHERE SUM(amount) >= 200
GROUP BY customer_id;
~~~

`WHERE` lọc dòng trước khi nhóm; ở thời điểm logic đó, `SUM(amount)` của mỗi nhóm chưa được tính. Oracle thường báo:

~~~text
ORA-00934: group function is not allowed here
~~~

Hãy chuyển điều kiện aggregate sang `HAVING`:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
GROUP BY customer_id
HAVING SUM(amount) >= 200;
~~~

Tương tự, không dùng `WHERE COUNT(*) >= 2` trong cùng query block. `COUNT(*)` là aggregate của nhóm, vì vậy điều kiện thuộc `HAVING`.

Nếu cần lọc kết quả aggregate ở một lớp truy vấn bên ngoài, có thể dùng inline view hoặc CTE:

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM lab_wh_order
    WHERE order_status = 'PAID'
    GROUP BY customer_id
)
SELECT customer_id, total_amount
FROM customer_totals
WHERE total_amount >= 200;
~~~

Ở query ngoài, `TOTAL_AMOUNT` đã là một cột của tập kết quả CTE, không còn là aggregate chưa tính. Về ý nghĩa, điều kiện này lọc **các dòng kết quả nhóm**. Với ví dụ đơn giản, `HAVING SUM(amount) >= 200` thường gọn hơn; CTE hữu ích khi cần tái sử dụng kết quả tổng hợp hoặc thực hiện nhiều bước.

## 8. HAVING có thể dùng khi không có GROUP BY

Oracle cho phép dùng hàm tổng hợp trên toàn bộ tập dòng còn lại như một nhóm duy nhất, ngay cả khi không viết `GROUP BY`. Khi đó `HAVING` có thể lọc nhóm duy nhất này.

~~~sql
SELECT COUNT(*) AS paid_order_count,
       SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
HAVING COUNT(*) >= 5;
~~~

Trong dữ liệu lab có sáu đơn PAID (An 2, Binh 3, Chi 1), nên kết quả:

| PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---:|
| 6 | 950 |

Nếu đổi điều kiện thành `HAVING COUNT(*) >= 7`, nhóm duy nhất không được giữ và câu SELECT trả **không có dòng kết quả**.

Một điểm cần nhớ: nếu không có `GROUP BY`, các hàm aggregate trong SELECT vẫn có thể tạo một dòng kết quả trên tập rỗng. Ví dụ:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'NOT_A_STATUS';
~~~

Khi không có dòng đầu vào, `COUNT(*)` trả 0 còn `SUM(amount)` trả NULL. Nếu thêm `HAVING COUNT(*) > 0`, nhóm duy nhất bị loại và kết quả không còn dòng.

## 9. WHERE, HAVING và NULL

NULL ảnh hưởng cả điều kiện lọc dòng lẫn aggregate:

- Trong `WHERE`, điều kiện có kết quả UNKNOWN không giữ dòng.
- `COUNT(*)` đếm dòng; `COUNT(expression)` chỉ đếm biểu thức khác NULL.
- `SUM`, `AVG`, `MIN`, `MAX` bỏ qua giá trị NULL.
- Nếu một nhóm không có giá trị khác NULL cho biểu thức SUM, kết quả SUM là NULL.

Ví dụ với bảng riêng có số tiền nullable:

~~~sql
CREATE TABLE lab_wh_nullable_amount (
    group_id NUMBER NOT NULL,
    amount   NUMBER(10,2)
);

INSERT INTO lab_wh_nullable_amount VALUES (1, 100);
INSERT INTO lab_wh_nullable_amount VALUES (1, NULL);
INSERT INTO lab_wh_nullable_amount VALUES (2, NULL);
INSERT INTO lab_wh_nullable_amount VALUES (2, NULL);
COMMIT;
~~~

Truy vấn:

~~~sql
SELECT
    group_id,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM lab_wh_nullable_amount
GROUP BY group_id
ORDER BY group_id;
~~~

Kết quả:

| GROUP_ID | ROW_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT |
|---:|---:|---:|---:|
| 1 | 2 | 1 | 100 |
| 2 | 2 | 0 | NULL |

Nếu viết:

~~~sql
HAVING SUM(amount) > 0
~~~

nhóm 1 được giữ, nhóm 2 bị loại vì `NULL > 0` là UNKNOWN chứ không phải TRUE.

Nếu muốn loại các dòng NULL **trước khi tính**, dùng `WHERE amount IS NOT NULL`. Nếu muốn chỉ giữ nhóm có ít nhất một giá trị amount, có thể dùng `HAVING COUNT(amount) > 0`. Hai điều kiện có thể tạo kết quả tổng hợp tương tự trong một số truy vấn, nhưng vị trí của chúng diễn đạt hai ý khác nhau: điều kiện đầu lọc dòng; điều kiện sau kiểm tra nhóm.

Không tự động đổi mọi NULL thành 0. “Chưa có dữ liệu” và “đã có dữ liệu bằng 0” có thể là hai trạng thái nghiệp vụ khác nhau.

## 10. COUNT, SUM, AVG và điều kiện HAVING

### 10.1. Đếm số dòng trong nhóm

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_order
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

Mỗi nhóm là một khách có ít nhất hai đơn trong toàn bộ bảng. Trạng thái đơn không được lọc ở WHERE, nên cả PAID, CANCELLED và PENDING đều được đếm.

### 10.2. Đếm giá trị khác NULL

~~~sql
SELECT group_id, COUNT(amount) AS known_amount_count
FROM lab_wh_nullable_amount
GROUP BY group_id
HAVING COUNT(amount) > 0;
~~~

Chỉ nhóm có ít nhất một amount khác NULL được giữ.

### 10.3. Tổng tiền và giá trị trung bình

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING AVG(amount) >= 150;
~~~

Điều kiện trên `AVG` lọc theo **giá trị trung bình của nhóm**, không phải lọc từng đơn có amount từ 150. Với khách An, trung bình hai đơn PAID tháng 1 là 125; Binh có trung bình theo cả ba đơn PAID là 100; Chi có 400. Nếu muốn trung bình chỉ trong tháng 1, phải thêm điều kiện ngày vào WHERE.

### 10.4. MIN và MAX

~~~sql
SELECT
    customer_id,
    MIN(amount) AS smallest_order,
    MAX(amount) AS largest_order
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING MAX(amount) >= 300;
~~~

Điều kiện này giữ khách có ít nhất một đơn PAID từ 300 trở lên. Nó không đồng nghĩa tổng tiền của khách từ 300 trở lên.

## 11. Kết hợp WHERE và HAVING trong báo cáo thực tế

Truy vấn sau đáp ứng một yêu cầu báo cáo cụ thể:

> “Trong tháng 1/2026, lấy các đơn đã thanh toán của khách đang hoạt động. Chỉ hiển thị khách có ít nhất hai đơn và tổng tiền đã thanh toán từ 220 trở lên. Sắp xếp tổng tiền giảm dần, nếu bằng nhau thì theo mã khách.”

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    SUM(o.amount) AS paid_total
FROM lab_wh_customer c
JOIN lab_wh_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
  AND o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) >= 2
   AND SUM(o.amount) >= 220
ORDER BY paid_total DESC, c.customer_id ASC;
~~~

Đọc theo từng giai đoạn:

1. `FROM` và `JOIN`: nối khách hàng với đơn hàng theo khóa.
2. `WHERE`: chỉ giữ khách active và đơn PAID trong tháng 1.
3. `GROUP BY`: tạo một nhóm cho mỗi khách còn dữ liệu.
4. `HAVING`: giữ nhóm có ít nhất hai đơn và tổng ít nhất 220.
5. `SELECT`: trả tên khách, số đơn và tổng tiền.
6. `ORDER BY`: sắp xếp theo tổng tiền và mã khách.

Kết quả dự kiến:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---|---:|---:|
| 1 | An | 2 | 250 |

Binh có hai đơn nhưng tổng chỉ 200; Chi có tổng 400 nhưng không hoạt động và bị WHERE loại; Dung không có đơn nên bị INNER JOIN loại; Em không có đơn PAID nên bị WHERE loại. Những lý do này khác nhau dù cuối cùng các khách đều không xuất hiện.

### 11.1. Nếu cần giữ khách chưa có đơn PAID

Thay `JOIN` bằng `LEFT JOIN`, đưa điều kiện trạng thái/ngày của đơn vào `ON`, và quyết định điều kiện HAVING phù hợp:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    NVL(SUM(o.amount), 0) AS paid_total
FROM lab_wh_customer c
LEFT JOIN lab_wh_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
 AND o.order_date >= DATE '2026-01-01'
 AND o.order_date <  DATE '2026-02-01'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id, c.customer_name
ORDER BY paid_total DESC, c.customer_id;
~~~

Truy vấn này giữ Dung và Em với số đơn 0, tổng 0. Nếu thêm `HAVING COUNT(o.order_id) >= 2`, hai khách đó lại bị loại theo đúng yêu cầu lọc nhóm. `HAVING` có thể lọc cả nhóm được tạo từ dòng NULL mở rộng của LEFT JOIN.

Nếu yêu cầu vừa muốn giữ khách chưa có đơn vừa muốn chỉ giữ nhóm có ít nhất hai đơn **hoặc** không có đơn, có thể diễn đạt:

~~~sql
HAVING COUNT(o.order_id) >= 2
    OR COUNT(o.order_id) = 0
~~~

Không nên tự thêm điều kiện này nếu yêu cầu nghiệp vụ không nói như vậy. Hãy chuyển mô tả thành logic rõ ràng trước.

## 12. HAVING không thay thế WHERE trong mọi trường hợp

Có thể viết điều kiện trên cột nhóm trong HAVING:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
GROUP BY customer_id
HAVING customer_id IN (1, 2);
~~~

Nhưng nếu mục tiêu là giảm tập dòng đầu vào theo customer_id, cách dễ đọc thường là:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
WHERE customer_id IN (1, 2)
GROUP BY customer_id;
~~~

Với điều kiện trên cột không phải aggregate và không làm thay đổi ý nghĩa nhóm, đưa điều kiện xuống WHERE thường có lợi vì giảm số dòng cần gom. Optimizer Oracle cũng có thể biến đổi/đẩy một số predicate khi an toàn, nhưng người viết nên đặt điều kiện ở vị trí đúng ngữ nghĩa trước.

Ngược lại, điều kiện như `SUM(amount) >= 200` hoặc `COUNT(*) >= 2` không thể chuyển thành WHERE cùng query block vì nó chỉ có ý nghĩa sau khi nhóm được tính.

## 13. HAVING với ROLLUP và các nhóm tổng hợp

Trong báo cáo nâng cao, `GROUP BY ROLLUP` tạo cả nhóm chi tiết và dòng tổng phụ/tổng chung. `HAVING` có thể lọc các nhóm này. Hàm `GROUPING` giúp nhận biết một giá trị NULL xuất hiện do tổng hợp hay là NULL thật trong dữ liệu.

Ví dụ tổng tiền PAID theo khách và có tổng chung:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS paid_total,
    GROUPING(customer_id) AS is_grand_total
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY ROLLUP(customer_id)
ORDER BY GROUPING(customer_id), customer_id;
~~~

Với `ROLLUP(customer_id)`, Oracle tạo nhóm theo từng khách và một nhóm tổng chung. `GROUPING(customer_id) = 1` đánh dấu dòng tổng hợp nơi customer_id bị lược khỏi cấp nhóm; `0` đánh dấu nhóm chi tiết.

Nếu chỉ muốn các nhóm khách, loại dòng tổng chung bằng HAVING:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY ROLLUP(customer_id)
HAVING GROUPING(customer_id) = 0
ORDER BY customer_id;
~~~

Đây là một ví dụ cho thấy `HAVING` có thể lọc **loại nhóm được sinh ra bởi cấu trúc GROUP BY**, không chỉ lọc ngưỡng tổng tiền. Trong báo cáo có `ROLLUP`, `CUBE` hoặc `GROUPING SETS`, cần phân biệt NULL thật với NULL đại diện cho mức tổng hợp.

## 14. Thứ tự xử lý logic của SELECT

Để hiểu WHERE và HAVING, hãy ghi nhớ thứ tự logic phổ biến:

~~~text
FROM
  |
  v
JOIN / ON
  |
  v
WHERE        <-- lọc dòng
  |
  v
GROUP BY     <-- tạo nhóm
  |
  v
HAVING       <-- lọc nhóm
  |
  v
SELECT       <-- tạo biểu thức đầu ra
  |
  v
DISTINCT
  |
  v
ORDER BY
  |
  v
OFFSET / FETCH FIRST (nếu có)
~~~

Đây là **thứ tự logic để giải thích ngữ nghĩa**, không phải cam kết optimizer phải thực thi vật lý đúng từng bước như sơ đồ. Oracle có thể đẩy predicate, đổi thứ tự join hoặc biến đổi biểu thức nếu vẫn bảo toàn kết quả.

Một vài hệ quả thực hành:

- Không dùng aggregate của query block trong WHERE.
- WHERE lọc dòng trước khi nhóm; HAVING lọc nhóm sau khi nhóm.
- Điều kiện trên cột nhóm có thể viết trong HAVING, nhưng thường nên đặt ở WHERE nếu ý định là lọc dòng đầu vào.
- Không dựa vào thứ tự vật lý của dòng; cần `ORDER BY` khi muốn kết quả có thứ tự xác định.
- Alias trong SELECT có thể dùng trong ORDER BY theo quy tắc Oracle, nhưng không nên dựa vào alias SELECT để viết điều kiện WHERE/HAVING trong cùng query block; dùng biểu thức gốc để tương thích rõ ràng.

## 15. Lỗi thường gặp và cách đọc nguyên nhân

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-00934: group function is not allowed here` | Đưa `SUM`, `COUNT`, `AVG` vào WHERE hoặc vị trí không cho phép aggregate | Chuyển điều kiện aggregate sang HAVING hoặc query ngoài |
| `ORA-00979: not a GROUP BY expression` | SELECT/HAVING tham chiếu biểu thức không được nhóm và không aggregate theo quy tắc | Kiểm tra danh sách GROUP BY và grain mong muốn |
| Tổng tiền nhỏ hơn dự kiến | WHERE loại dòng trước khi SUM; predicate trạng thái/ngày quá chặt | Liệt kê dòng sau WHERE trước khi GROUP BY |
| Số khách ít hơn dự kiến | Dùng INNER JOIN hoặc predicate trên bảng phải đặt ở WHERE sau LEFT JOIN | Xem lại loại JOIN và vị trí điều kiện |
| Khách không có đơn bị đếm thành 1 | Dùng COUNT(*) trên LEFT JOIN | Đếm khóa phía phải bằng COUNT(order_id) |
| HAVING lọc mất cả nhóm | Ngưỡng aggregate hoặc điều kiện AND quá chặt | Tính aggregate từng nhóm trước khi áp điều kiện |
| Nhóm có tổng NULL bị loại | `SUM(...) > ...` cho kết quả UNKNOWN khi SUM NULL | Xác định NULL có nghĩa gì; dùng COUNT/COALESCE nếu phù hợp |
| Kết quả thay đổi theo thời gian | Dữ liệu đầu vào hoặc khoảng ngày không cố định | Dùng ngày bind/literal rõ ràng và dataset kiểm thử cố định |

### 15.1. Cách gỡ lỗi theo từng tầng

Khi kết quả không đúng, đừng sửa ngay câu SQL cuối. Hãy tách thành các truy vấn nhỏ:

**Tầng 1 — kiểm tra dòng nguồn:**

~~~sql
SELECT order_id, customer_id, order_status, amount, order_date
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
ORDER BY customer_id, order_id;
~~~

**Tầng 2 — kiểm tra nhóm chưa có HAVING:**

~~~sql
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
ORDER BY customer_id;
~~~

**Tầng 3 — thêm HAVING:**

~~~sql
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

So sánh tầng 2 và tầng 3 cho biết chính xác nhóm nào bị HAVING loại. So sánh tầng 1 và tầng 2 giúp xác định số dòng đầu vào đã được cộng như thế nào.

## 16. Hiệu năng: vì sao nên lọc dòng sớm khi đúng ngữ nghĩa?

Giả sử bảng đơn hàng có 100 triệu dòng nhưng báo cáo chỉ cần đơn PAID trong tháng 1. Điều kiện `WHERE order_status = 'PAID'` và khoảng ngày có thể giảm tập dữ liệu trước khi nhóm; điều này thường giúp giảm số dòng phải xử lý ở các bước sau.

Một số nguyên tắc:

- Đưa điều kiện lọc dòng độc lập với aggregate vào WHERE khi đúng ngữ nghĩa.
- Dùng kiểu dữ liệu đúng và bind đúng kiểu; tránh implicit conversion trên cột lọc.
- Chọn khoảng ngày nửa mở thay vì bọc cột ngày bằng `TO_CHAR` trong WHERE nếu có thể.
- Kiểm tra index và statistics trên dữ liệu đại diện; không tạo index chỉ dựa trên bảng lab vài dòng.
- Nếu điều kiện thực sự phụ thuộc tổng/đếm, dùng HAVING; không cố viết lại thành WHERE để “tăng tốc” vì có thể đổi kết quả.

Ví dụ tránh:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-01'
~~~

Vì hàm được áp dụng lên cột, index thông thường trên `ORDER_DATE` có thể khó được sử dụng trực tiếp. Cách viết khoảng ngày:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
~~~

thường thân thiện hơn với range scan trên index phù hợp. Tuy nhiên, kế hoạch cuối cùng còn phụ thuộc thống kê, phân bố dữ liệu, partitioning và các điều kiện khác.

### 16.1. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho kế hoạch ước lượng trong ngữ cảnh phân tích; nó không tự chứng minh truy vấn đúng hay cung cấp đầy đủ thống kê runtime. Khi có quyền và truy vấn đã thực thi, `DBMS_XPLAN.DISPLAY_CURSOR` cùng thống kê thực tế có thể giúp xem số dòng ước lượng/thực tế và chi phí. Trước tiên phải xác nhận ngữ nghĩa WHERE/HAVING; tối ưu một truy vấn trả sai kết quả không phải là tối ưu.

## 17. Kiểm chứng kết quả bằng expected output

Một bài học SQL tốt nên cho phép người khác kiểm tra lại kết quả. Với truy vấn tháng 1, ta có thể ghi tập expected:

| CUSTOMER_ID | ORDER_COUNT | TOTAL_AMOUNT | Lý do |
|---:|---:|---:|---|
| 1 | 2 | 250 | Hai đơn PAID tháng 1, đạt cả hai điều kiện HAVING |

Sau đó chạy:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 220
ORDER BY customer_id;
~~~

Để kiểm tra tự động, có thể so sánh kết quả thực tế với tập expected bằng `MINUS` hai chiều:

~~~sql
WITH expected AS (
    SELECT 1 AS customer_id, 2 AS order_count, 250 AS total_amount
    FROM dual
),
actual AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM lab_wh_order
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-01-01'
      AND order_date < DATE '2026-02-01'
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
       AND SUM(amount) >= 220
)
SELECT 'EXPECTED_NOT_ACTUAL' AS difference,
       customer_id, order_count, total_amount
FROM (
    SELECT * FROM expected
    MINUS
    SELECT * FROM actual
)
UNION ALL
SELECT 'ACTUAL_NOT_EXPECTED',
       customer_id, order_count, total_amount
FROM (
    SELECT * FROM actual
    MINUS
    SELECT * FROM expected
)
ORDER BY difference, customer_id;
~~~

Nếu không có dòng khác biệt, hai tập kết quả giống nhau trên các cột được so sánh. `MINUS` có ngữ nghĩa tập hợp loại trùng; nếu cần kiểm tra số lần xuất hiện của từng dòng trong một kết quả có thể trùng, cần so sánh thêm số lượng theo nhóm.

## 18. Bài tập tự kiểm tra

### Bài 1 — Chỉ lọc dòng

Viết truy vấn lấy tất cả đơn PAID trong tháng 1/2026, không gom nhóm.

**Đáp án gợi ý:**

~~~sql
SELECT order_id, customer_id, amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01';
~~~

### Bài 2 — Lọc nhóm theo số đơn

Tìm khách có ít nhất hai đơn PAID trong toàn bộ dữ liệu, không giới hạn tháng.

**Đáp án gợi ý:**

~~~sql
SELECT customer_id, COUNT(*) AS paid_count
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

### Bài 3 — Lọc nhóm theo tổng tiền

Tìm khách có tổng tiền PAID trong tháng 1 từ 300 trở lên.

**Đáp án gợi ý:** dùng WHERE để chọn đơn PAID và ngày tháng; GROUP BY customer_id; HAVING SUM(amount) >= 300. Chi có 400 nên xuất hiện, An 250 và Binh 200 nên không.

### Bài 4 — Giải thích kết quả khác nhau

Với Binh, vì sao câu dùng `WHERE amount >= 100` trả tổng 120, còn câu dùng `HAVING SUM(amount) >= 100` trả tổng 200?

**Đáp án:** WHERE loại đơn 80 trước khi nhóm; HAVING cộng cả 80 và 120 rồi chỉ kiểm tra tổng nhóm.

### Bài 5 — Sửa lỗi ORA-00934

Sửa truy vấn:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
WHERE SUM(amount) >= 200
GROUP BY customer_id;
~~~

**Đáp án:** chuyển điều kiện `SUM(amount) >= 200` sang HAVING.

### Bài 6 — Giữ khách chưa có đơn

Viết truy vấn hiển thị mọi khách active và tổng tiền PAID tháng 1; khách chưa có đơn PAID vẫn phải hiện với tổng 0.

**Đáp án định hướng:** bắt đầu từ `LAB_WH_CUSTOMER`, dùng LEFT JOIN; đặt điều kiện PAID và khoảng ngày trong ON; lọc active trong WHERE; dùng `COUNT(o.order_id)` và `NVL(SUM(o.amount), 0)`.

### Bài 7 — HAVING không có GROUP BY

Viết câu trả về tổng số đơn PAID trong toàn bảng nếu số đơn ít nhất là 5; nếu ít hơn 5 thì không trả dòng.

**Đáp án:**

~~~sql
SELECT COUNT(*) AS paid_count
FROM lab_wh_order
WHERE order_status = 'PAID'
HAVING COUNT(*) >= 5;
~~~

### Bài 8 — Tách điều kiện

Một báo cáo cần “các đơn PAID trong quý 1, chỉ giữ khách có trung bình đơn từ 500 trở lên”. Hãy xác định:

- Điều kiện nào ở WHERE?
- Điều kiện nào ở HAVING?

**Đáp án định hướng:** trạng thái PAID và khoảng ngày quý 1 là điều kiện trên từng dòng, đặt trong WHERE. `AVG(amount) >= 500` là điều kiện trên nhóm khách, đặt trong HAVING.

## 19. Quy trình quyết định WHERE hay HAVING

Khi gặp một điều kiện mới, hãy tự hỏi:

1. Điều kiện này có thể đánh giá độc lập trên **một dòng nguồn** không?
2. Nó có cần kết quả của `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` hoặc một nhóm đã tạo không?
3. Nếu loại dòng trước khi nhóm, kết quả tổng hợp có thay đổi không?
4. Nếu loại nhóm sau khi nhóm, có giữ nguyên các dòng đóng góp vào aggregate không?
5. Có LEFT JOIN hoặc NULL khiến việc đặt điều kiện ở WHERE loại mất dòng cần giữ không?

Sơ đồ:

~~~text
Điều kiện đang kiểm tra điều gì?
              |
       +------+------+
       |             |
       v             v
   Một dòng       Một nhóm đã gom
       |             |
       v             v
     WHERE         HAVING
       |             |
       v             v
 Lọc đầu vào     Lọc kết quả nhóm
       |             |
       +------+------+
              |
              v
      Kết quả SELECT cuối
~~~

`WHERE` và `HAVING` cùng phục vụ việc lọc nhưng không cùng nhiệm vụ. Hãy dùng `WHERE` để xác định **những dòng được tham gia tính toán**, dùng `HAVING` để quyết định **nhóm nào đạt điều kiện sau khi tính toán**. Khi kết hợp hai mệnh đề, hãy tự tính một vài nhóm trên dữ liệu tối thiểu và so sánh với kết quả Oracle; cách đó làm rõ ngay điều kiện đang loại dòng hay loại cả nhóm, giúp truy vấn đúng nghiệp vụ và dễ giải thích cho người khác.
