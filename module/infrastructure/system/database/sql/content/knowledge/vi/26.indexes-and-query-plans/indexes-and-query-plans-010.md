# Bội số hàng, ước lượng số hàng và nguyên nhân kết quả trung gian lớn

Một câu SQL có thể chỉ trả về vài chục hàng ở kết quả cuối nhưng vẫn chạy chậm, dùng nhiều bộ nhớ hoặc ghi dữ liệu tạm ra đĩa. Nguyên nhân thường không nằm ở số hàng **đầu ra cuối cùng**, mà ở số hàng **được tạo và xử lý ở giữa kế hoạch thực thi**.

Ví dụ: doanh nghiệp có 6 đơn hàng, 9 giao dịch thanh toán và 8 lượt vận chuyển. Nếu nối cả ba bảng để lấy báo cáo theo đơn, kết quả trung gian có thể là **16 hàng**, không phải 6, 9 hay 8. Sau đó `GROUP BY` có thể thu lại chỉ 6 nhóm, nhưng hệ quản trị đã phải xử lý những hàng được nhân lên.

Khi dữ liệu lớn, việc nhân từ vài hàng thành vài chục triệu hàng có thể làm:

- Tăng chi phí CPU và số vòng lặp của phép nối.
- Tăng dữ liệu phải đưa vào `SORT`, `GROUP BY`, `DISTINCT` hoặc window function.
- Tăng dung lượng hash table, có thể khiến thao tác phải chia batch hoặc tràn sang tệp tạm.
- Khiến query planner chọn chiến lược không phù hợp nếu **ước lượng số hàng** (*cardinality estimate*) khác xa thực tế.
- Quan trọng hơn: tạo **kết quả nghiệp vụ sai** nếu lấy `SUM`, `COUNT` từ hàng đã bị nhân bản.

Bài học thuộc chương **Chỉ mục và kế hoạch** của Database SQL, tập trung vào ba câu hỏi:

1. Vì sao một phép nối tạo ra **nhiều hơn số hàng mong đợi**?
2. Vì sao số hàng **planner ước lượng** có thể khác với số hàng **thực thi thật**?
3. Làm sao kiểm soát **cấp độ hàng (grain)** và giảm kết quả trung gian mà vẫn trả lời đúng câu hỏi nghiệp vụ?

Các ví dụ chính dùng **PostgreSQL**, có bộ dữ liệu cố định để dự đoán số hàng bằng tay và đối chiếu với `EXPLAIN (ANALYZE, BUFFERS)`. Những con số trong bảng ví dụ là kết quả logic của dữ liệu mẫu; kế hoạch vật lý, thời gian và lựa chọn index cụ thể phụ thuộc phiên bản DBMS, thống kê và môi trường chạy.

## 1. Cardinality là số hàng, không phải kích thước byte

Trong ngữ cảnh kế hoạch thực thi, **cardinality** thường chỉ số hàng mà một phép toán tạo ra. Ví dụ:

```text
Scan orders                  → 6 hàng
Join orders × payments       → 9 hàng (INNER JOIN, dữ liệu mẫu)
Join orders × payments ×
shipments                    → 14 hàng (INNER JOIN cả hai)
GROUP BY order_id            → 4 nhóm (với INNER JOIN cả hai)
```

Nếu dùng `LEFT JOIN` để giữ cả những đơn chưa thanh toán hoặc chưa vận chuyển, số hàng ở những bước nối có thể khác. Ta sẽ tính chính xác sau khi tạo dữ liệu.

Phân biệt:

| Khái niệm | Giải thích |
| --- | --- |
| **Cardinality** | Số hàng đi ra khỏi một phép toán |
| **Row width** | Kích thước trung bình của một hàng trong kế hoạch |
| **Intermediate result** | Tập hàng do một bước tạo ra trước bước tiếp theo |
| **Estimated rows** | Số hàng optimizer dự đoán |
| **Actual rows** | Số hàng thực tế mà operator trả trong lúc đo |
| **Selectivity** | Tỷ lệ hàng dự đoán hoặc thực tế còn lại sau điều kiện lọc |
| **Fanout** | Số hàng kết quả trung bình trên mỗi hàng phía đầu vào khi nối/mở rộng |
| **NDV** | Số giá trị phân biệt (*number of distinct values*) của một cột/biểu thức |

Số hàng và số byte liên quan nhưng không đồng nhất. Một triệu hàng chỉ chứa hai số nguyên khác với một triệu hàng chứa JSON hoặc văn bản lớn. Planner cần ước lượng cả số hàng lẫn độ rộng hàng để quyết định chi phí sort, hash, I/O và vận chuyển dữ liệu.

## 2. SQL thường xử lý tập có bội số, không mặc định loại trùng

Trong toán học, **tập hợp** không có phần tử lặp. SQL thông thường làm việc với ngữ nghĩa gần với **multiset/bag**: nhiều hàng có cùng giá trị vẫn có thể xuất hiện nhiều lần trừ khi ta dùng cách loại trùng phù hợp.

```sql
SELECT 1 AS x
UNION ALL
SELECT 1 AS x;
```

Trả **2 hàng** có `x=1`.

```sql
SELECT 1 AS x
UNION
SELECT 1 AS x;
```

Trả **1 hàng** vì `UNION` mặc định loại hàng trùng theo các cột đầu ra.

Tương tự, `JOIN` không tự loại những kết hợp trùng trên cột hiển thị. Nếu một đơn có hai thanh toán, phép nối với bảng thanh toán tạo **hai hàng kết quả mang cùng `order_id`**.

### 2.1. Bội số của hàng khi JOIN

Giả sử khóa `K` xuất hiện:

- \(m_A(K)\) lần trong bảng A.
- \(m_B(K)\) lần trong bảng B.

Với equi-`INNER JOIN` theo K, số hàng kết quả cho khóa K là:

\[
m_{\mathrm{join}}(K)=m_A(K)\times m_B(K)
\]

Tổng số hàng nối là:

\[
|\mathrm{A\ JOIN\ B}| = \sum_K m_A(K)m_B(K)
\]

Ví dụ khóa `ORD-101` xuất hiện một lần ở bảng `orders` và ba lần ở bảng `shipments`:

\[
1\times3 = 3\ \text{hàng}
\]

Nếu cùng khóa xuất hiện **hai lần ở A** và **ba lần ở B**, phép nối tạo:

\[
2\times3=6\ \text{hàng}
\]

Đây là kết quả đúng về mặt SQL, không phải database tự sao chép dữ liệu vì lỗi nội bộ. Lỗi nằm ở **kỳ vọng về grain** nếu người viết muốn một hàng trên mỗi đơn nhưng lại nối nhiều hàng chi tiết.

### 2.2. DISTINCT không sửa được grain sai

`SELECT DISTINCT order_id` có thể giảm nhiều hàng nối về một mã đơn. Nhưng nếu cần `SUM(amount)`, việc dùng `DISTINCT` ngoài cùng có thể không khắc phục tổng bị cộng nhiều lần ở bước trước.

Cũng không được mặc định dùng `SUM(DISTINCT order_total)`: hai đơn **khác nhau có cùng tổng 90** phải được cộng **cả hai**, trong khi `SUM(DISTINCT ...)` chỉ tính giá trị 90 một lần.

**Câu hỏi đầu tiên trước khi JOIN:** “Mỗi hàng của kết quả cuối cần đại diện cho một đối tượng gì?”

## 3. Bộ dữ liệu thực hành PostgreSQL

Các lệnh dưới đây tạo schema riêng `demo_cardinality_331` với năm bảng: khách hàng, đơn hàng, dòng đơn, thanh toán và vận chuyển.

**Chỉ thực hiện trên database học tập/sandbox.** Schema được tạo bằng `CREATE SCHEMA`; không chạy ở một database production nơi có thể đã tồn tại schema cùng tên.

### 3.1. Tạo schema và bảng

```sql
CREATE SCHEMA demo_cardinality_331;

CREATE TABLE demo_cardinality_331.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE demo_cardinality_331.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_cardinality_331.customers(customer_id),
    ordered_on DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    order_total NUMERIC(12,2) NOT NULL
        CHECK (order_total >= 0)
);

CREATE TABLE demo_cardinality_331.order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES demo_cardinality_331.orders(order_id),
    line_amount NUMERIC(12,2) NOT NULL
        CHECK (line_amount >= 0)
);

CREATE TABLE demo_cardinality_331.payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES demo_cardinality_331.orders(order_id),
    paid_amount NUMERIC(12,2) NOT NULL
        CHECK (paid_amount >= 0)
);

CREATE TABLE demo_cardinality_331.shipments (
    shipment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES demo_cardinality_331.orders(order_id),
    shipped_on DATE NOT NULL
);
```

Ràng buộc bảo đảm:

- Mỗi khách có một `customer_id` duy nhất.
- Mỗi đơn có một `order_id` duy nhất.
- Mỗi `order_items`, `payments` và `shipments` tham chiếu một đơn đã tồn tại.
- **Không có `UNIQUE(order_id)` ở ba bảng con**, vì nghiệp vụ cho phép một đơn có nhiều dòng hàng, nhiều thanh toán và nhiều chuyến vận chuyển.

Quan hệ:

```text
customers  1 ──< N orders
orders     1 ──< N order_items
orders     1 ──< N payments
orders     1 ──< N shipments
```

Dấu `1 ──< N` nghĩa là một hàng ở phía cha có thể liên quan nhiều hàng ở phía con.

### 3.2. Thêm bốn khách hàng

```sql
INSERT INTO demo_cardinality_331.customers
    (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');
```

Khách `Dung` không có đơn, để minh họa hàng mở rộng của `LEFT JOIN`.

### 3.3. Thêm sáu đơn hàng

```sql
INSERT INTO demo_cardinality_331.orders
    (order_id, customer_id, ordered_on, status, order_total)
VALUES
    (101, 1, DATE '2025-06-01', 'paid',    120),
    (102, 1, DATE '2025-06-01', 'paid',     50),
    (103, 1, DATE '2025-06-02', 'pending',  20),
    (104, 2, DATE '2025-06-02', 'paid',     90),
    (105, 3, DATE '2025-06-03', 'paid',     60),
    (106, 3, DATE '2025-06-03', 'paid',     90);
```

Tổng tất cả sáu đơn:

\[
120+50+20+90+60+90=430
\]

Tổng **năm đơn `paid`**:

\[
120+50+90+60+90=410
\]

Hai đơn `104` và `106` cùng `order_total=90`, nhằm minh họa vì sao không thể dùng `SUM(DISTINCT order_total)` để “sửa” một phép nối làm nhân hàng.

### 3.4. Thêm 11 dòng đơn

```sql
INSERT INTO demo_cardinality_331.order_items
    (item_id, order_id, line_amount)
VALUES
    (1001, 101, 70),
    (1002, 101, 50),
    (1003, 102, 20),
    (1004, 102, 20),
    (1005, 102, 10),
    (1006, 103, 20),
    (1007, 104, 40),
    (1008, 104, 50),
    (1009, 105, 60),
    (1010, 106, 50),
    (1011, 106, 40);
```

Mỗi đơn có một hoặc nhiều dòng, tổng `line_amount` theo đơn bằng `order_total` trong dữ liệu học tập.

| Đơn | Số dòng | Tổng dòng |
| ---: | ---: | ---: |
| 101 | 2 | 120 |
| 102 | 3 | 50 |
| 103 | 1 | 20 |
| 104 | 2 | 90 |
| 105 | 1 | 60 |
| 106 | 2 | 90 |
| **Tổng** | **11** | **430** |

### 3.5. Thêm 9 thanh toán

```sql
INSERT INTO demo_cardinality_331.payments
    (payment_id, order_id, paid_amount)
VALUES
    (501, 101, 70),
    (502, 101, 50),
    (503, 102, 50),
    (504, 104, 40),
    (505, 104, 50),
    (506, 105, 60),
    (507, 106, 20),
    (508, 106, 30),
    (509, 106, 40);
```

Đơn 103 đang `pending`, chưa có thanh toán. Các đơn paid còn lại có từ một đến ba thanh toán.

### 3.6. Thêm 8 vận chuyển

```sql
INSERT INTO demo_cardinality_331.shipments
    (shipment_id, order_id, shipped_on)
VALUES
    (601, 101, DATE '2025-06-02'),
    (602, 101, DATE '2025-06-03'),
    (603, 101, DATE '2025-06-04'),
    (604, 102, DATE '2025-06-03'),
    (605, 103, DATE '2025-06-04'),
    (606, 104, DATE '2025-06-03'),
    (607, 104, DATE '2025-06-05'),
    (608, 106, DATE '2025-06-05');
```

Đơn 105 chưa có vận chuyển. Một đơn có thể giao nhiều lần; `shipments.order_id` **không duy nhất**.

### 3.7. Tổng quan kích thước và bội số theo từng đơn

| Đơn | Khách | Tổng đơn | Số dòng hàng | Số thanh toán | Số vận chuyển |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 120 | 2 | 2 | 3 |
| 102 | 1 | 50 | 3 | 1 | 1 |
| 103 | 1 | 20 | 1 | 0 | 1 |
| 104 | 2 | 90 | 2 | 2 | 2 |
| 105 | 3 | 60 | 1 | 1 | 0 |
| 106 | 3 | 90 | 2 | 3 | 1 |
| **Tổng** | | **430** | **11** | **9** | **8** |

Bảng này là chìa khóa để tự tính số hàng sau mỗi `JOIN` **mà không phụ thuộc vào trình tối ưu**.

## 4. Một quan hệ 1:N làm hàng cha lặp lại

### 4.1. INNER JOIN customers → orders

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_total
FROM demo_cardinality_331.customers AS c
JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả có **6 hàng**:

| Khách | Đơn | Tổng đơn |
| --- | ---: | ---: |
| An | 101 | 120 |
| An | 102 | 50 |
| An | 103 | 20 |
| Binh | 104 | 90 |
| Chi | 105 | 60 |
| Chi | 106 | 90 |

Khách `Dung` không có đơn nên không xuất hiện trong `INNER JOIN`.

Dễ nhận thấy khách `An` có ba đơn nên thông tin khách An xuất hiện **ba lần**. Đó là **fanout 3** từ khách An sang đơn.

### 4.2. LEFT JOIN bảo toàn khách chưa có đơn

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_total
FROM demo_cardinality_331.customers AS c
LEFT JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả **7 hàng**: sáu hàng đơn như trên, cộng một hàng cho Dung với các cột `o` là `NULL`.

Vì sao không phải 6 hay 4?

- Khách An: 3 hàng.
- Binh: 1 hàng.
- Chi: 2 hàng.
- Dung: 1 hàng mở rộng do không có đơn.

Tổng:

\[
3+1+2+1=7
\]

### 4.3. Đếm đúng sau LEFT JOIN

```sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS real_orders,
    COUNT(DISTINCT c.customer_id) AS distinct_customers
FROM demo_cardinality_331.customers AS c
LEFT JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id;
```

Kết quả:

| `joined_rows` | `real_orders` | `distinct_customers` |
| ---: | ---: | ---: |
| 7 | 6 | 4 |

`COUNT(*)` đếm cả hàng mở rộng cho khách chưa có đơn. `COUNT(o.order_id)` không đếm hàng ấy, vì khóa đơn bên phải là `NULL`. `COUNT(DISTINCT c.customer_id)` đếm các khách duy nhất.

Không nên gọi cả ba con số là “số khách” hoặc “số đơn” mà không xác định chính xác grain đang đếm.

## 5. Hai bảng con độc lập làm bội số nhân nhau

Đây là lỗi trung gian lớn thường gặp nhất trong báo cáo: nối **hai quan hệ 1:N khác nhau** vào cùng một bảng cha.

```sql
SELECT
    o.order_id,
    p.payment_id,
    p.paid_amount,
    s.shipment_id
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id
ORDER BY o.order_id, p.payment_id, s.shipment_id;
```

### 5.1. Vì sao đơn 101 tạo sáu hàng?

Đơn 101 có:

```text
Payments: 501, 502       → 2 hàng
Shipments: 601, 602, 603 → 3 hàng
```

Khi cùng nối theo `order_id=101`, mọi thanh toán kết hợp với mọi vận chuyển:

| order_id | payment_id | shipment_id |
| ---: | ---: | ---: |
| 101 | 501 | 601 |
| 101 | 501 | 602 |
| 101 | 501 | 603 |
| 101 | 502 | 601 |
| 101 | 502 | 602 |
| 101 | 502 | 603 |

Số hàng là:

\[
2 \times 3=6
\]

Không có một sự kiện nghiệp vụ “thanh toán 501 thuộc riêng vận chuyển 601” trong schema; SQL chỉ biết cả hai cùng thuộc đơn 101 nên tạo mọi tổ hợp phù hợp với điều kiện nối.

### 5.2. Công thức LEFT JOIN cho mỗi đơn

Nếu một đơn có:

- \(p\) thanh toán.
- \(s\) vận chuyển.

Với hai `LEFT JOIN` độc lập và mỗi bảng con có thể không có hàng, số hàng sinh ra cho đơn đó là:

\[
\max(p,1)\times\max(s,1)
\]

Vì một bên không khớp vẫn có **một hàng mở rộng `NULL`**, không phải 0.

Áp dụng bộ dữ liệu:

| Đơn | `p` | `s` | Số hàng sau hai LEFT JOIN |
| ---: | ---: | ---: | ---: |
| 101 | 2 | 3 | 6 |
| 102 | 1 | 1 | 1 |
| 103 | 0 | 1 | 1 |
| 104 | 2 | 2 | 4 |
| 105 | 1 | 0 | 1 |
| 106 | 3 | 1 | 3 |
| **Tổng** | 9 | 8 | **16** |

Từ **6 đơn** tạo **16 hàng**, fanout trung bình của cả phép nối là \(16/6\approx2{,}67\).

Một số đơn chỉ tạo 1 hàng, nhưng những đơn có nhiều thanh toán **và** nhiều vận chuyển khiến trung gian phình lên.

### 5.3. Đối chiếu từng bước

```sql
SELECT COUNT(*) AS orders_count
FROM demo_cardinality_331.orders;
-- 6

SELECT COUNT(*) AS after_payments
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id;
-- 10: 9 thanh toán thật + 1 đơn chưa có thanh toán

SELECT COUNT(*) AS after_payments_and_shipments
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
-- 16
```

Nếu chỉ nhìn 6 hàng của bảng `orders` rồi 6 hàng của kết quả `GROUP BY order_id`, ta có thể bỏ qua bước trung gian có 16 hàng.

### 5.4. INNER JOIN của hai bảng con

```sql
SELECT COUNT(*) AS joined_rows
FROM demo_cardinality_331.orders AS o
JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

Trả **14 hàng**:

\[
(2\times3)+(1\times1)+(2\times2)+(3\times1)
=6+1+4+3=14
\]

Đơn 103 không có thanh toán, đơn 105 không có vận chuyển nên biến mất khỏi kết quả `INNER JOIN`.

Phép nối này không tạo “mỗi đơn một hàng” mà tạo “mỗi **cặp thanh toán–vận chuyển** có cùng đơn một hàng”. Hãy phân biệt đó là **quan hệ nghiệp vụ mong muốn** hay chỉ là hiệu ứng phụ của SQL.

## 6. Kết quả trung gian lớn có thể làm sai SUM

Sau hai `LEFT JOIN`, mỗi `o.order_total` xuất hiện lặp theo số tổ hợp thanh toán–vận chuyển.

```sql
SELECT
    SUM(o.order_total) AS wrong_order_total,
    SUM(p.paid_amount) AS wrong_payment_total,
    COUNT(s.shipment_id) AS wrong_shipment_count
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

Kết quả:

| Chỉ số | Kết quả sau JOIN | Số đúng ở grain gốc |
| --- | ---: | ---: |
| Tổng `order_total` | 1480 | 430 |
| Tổng `paid_amount` | 740 | 410 |
| Số hàng `shipment_id` | 15 | 8 |

### 6.1. Vì sao tổng đơn từ 430 thành 1480?

Mỗi đơn bị lặp theo cột cuối bảng ở phần 5.2:

```text
101: 120 × 6 = 720
102:  50 × 1 =  50
103:  20 × 1 =  20
104:  90 × 4 = 360
105:  60 × 1 =  60
106:  90 × 3 = 270
------------------
Tổng sai        1480
```

Giá trị của đơn không thay đổi, nhưng **số lần cộng vào tổng đã tăng**.

### 6.2. Vì sao tổng thanh toán từ 410 thành 740?

Mỗi thanh toán bị lặp theo số vận chuyển khớp với đơn:

```text
101: (70 + 50) × 3 = 360
102:  50       × 1 =  50
104: (40 + 50) × 2 = 180
105:  60       × 1 =  60  (không có shipment, LEFT JOIN vẫn giữ một hàng)
106: (20+30+40)× 1 =  90
-----------------------
Tổng sai             740
```

### 6.3. Đừng “sửa” bằng SUM(DISTINCT)

```sql
SELECT
    SUM(DISTINCT o.order_total) AS tempting_but_wrong
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

Kết quả là:

\[
20+50+60+90+120=340
\]

vì hai đơn 104 và 106 đều có tổng tiền 90 nhưng `SUM(DISTINCT ...)` chỉ tính **giá trị 90 một lần**. Tổng đúng là 430.

`DISTINCT` trên **giá trị tiền** không có nghĩa “mỗi đơn một lần”. Muốn cộng mỗi đơn một lần, phải giữ hoặc phục hồi grain **một hàng trên mỗi `order_id`**.

### 6.4. COUNT(DISTINCT) khi nào hợp lý?

Nếu cần đếm số đơn duy nhất trong một kết quả đã JOIN:

```sql
SELECT
    COUNT(DISTINCT o.order_id) AS unique_orders,
    COUNT(DISTINCT p.payment_id) AS unique_payments,
    COUNT(DISTINCT s.shipment_id) AS unique_shipments
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

Trả **6, 9, 8**. Đây là cách đếm các **định danh riêng biệt** hợp lệ cho câu hỏi đếm, nhưng nó không sửa lỗi tổng tiền và cũng **không làm giảm khối lượng join đã xảy ra trước khi DISTINCT được tính**.

Nếu mục tiêu chỉ đếm số đơn, thường không cần join nhiều bảng con ngay từ đầu.

## 7. Giảm kết quả trung gian bằng tổng hợp bảng con trước

Khi cần một hàng trên mỗi đơn với tổng thanh toán và số lần vận chuyển, hãy tổng hợp mỗi bảng con về **đúng grain order_id** trước khi nối.

```sql
WITH
payment_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(paid_amount) AS amount_paid
    FROM demo_cardinality_331.payments
    GROUP BY order_id
),
shipment_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS shipment_count
    FROM demo_cardinality_331.shipments
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_total,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.amount_paid, 0::numeric) AS amount_paid,
    COALESCE(s.shipment_count, 0) AS shipment_count
FROM demo_cardinality_331.orders AS o
LEFT JOIN payment_by_order AS p
    ON p.order_id = o.order_id
LEFT JOIN shipment_by_order AS s
    ON s.order_id = o.order_id
ORDER BY o.order_id;
```

Kết quả:

| Đơn | Tổng đơn | Số thanh toán | Đã thanh toán | Số vận chuyển |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 120 | 2 | 120 | 3 |
| 102 | 50 | 1 | 50 | 1 |
| 103 | 20 | 0 | 0 | 1 |
| 104 | 90 | 2 | 90 | 2 |
| 105 | 60 | 1 | 60 | 0 |
| 106 | 90 | 3 | 90 | 1 |

Có **6 hàng**, một hàng mỗi đơn. Mỗi CTE tổng hợp có **tối đa một hàng trên mỗi order_id**. Hai `LEFT JOIN` không còn nhân nhiều hàng con với nhau.

### 7.1. Vì sao kết quả đúng?

`payment_by_order` có khóa logic `order_id` duy nhất nhờ `GROUP BY`. Với một đơn, phép nối sang CTE đó trả tối đa một hàng.

Tương tự, `shipment_by_order` có tối đa một hàng trên mỗi đơn.

Do đó:

```text
6 đơn
LEFT JOIN payment_by_order  → 6 hàng
LEFT JOIN shipment_by_order → 6 hàng
```

Nếu hàng con không tồn tại, cột tổng hợp bên phải là `NULL`; `COALESCE` chuyển thành 0 theo quy ước “không có thanh toán/vận chuyển”.

**Cẩn trọng với `NULL`:** Trong bảng mẫu, `paid_amount` được khai báo `NOT NULL`, nên giá trị tổng là số biết chắc. Nếu dữ liệu nguồn có amount chưa biết, `SUM` trả `NULL` có thể mang ý nghĩa khác với không có thanh toán; khi đó cần bảo toàn số lượng giá trị biết/không biết thay vì `COALESCE` mọi trường hợp.

### 7.2. Tổng hợp theo khách hàng sau khi sửa grain

```sql
WITH payment_by_order AS (
    SELECT order_id, SUM(paid_amount) AS amount_paid
    FROM demo_cardinality_331.payments
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_total,
        COALESCE(p.amount_paid, 0::numeric) AS amount_paid
    FROM demo_cardinality_331.orders AS o
    LEFT JOIN payment_by_order AS p
      ON p.order_id = o.order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(f.order_id) AS order_count,
    COALESCE(SUM(f.order_total), 0::numeric) AS all_order_total,
    COALESCE(SUM(f.amount_paid), 0::numeric) AS amount_paid
FROM demo_cardinality_331.customers AS c
LEFT JOIN order_facts AS f
  ON f.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách | Số đơn | Tổng đơn | Đã thanh toán |
| --- | ---: | ---: | ---: |
| An | 3 | 190 | 170 |
| Binh | 1 | 90 | 90 |
| Chi | 2 | 150 | 150 |
| Dung | 0 | 0 | 0 |
| **Tổng** | **6** | **430** | **410** |

Đây là hai lần thay đổi grain có chủ đích:

1. Nối các chỉ số con về **một hàng trên mỗi đơn**.
2. Tổng hợp từ các đơn về **một hàng trên mỗi khách**.

### 7.3. Không cần join dữ liệu không sử dụng

Nếu báo cáo chỉ cần `order_count` và `all_order_total`, không cần tham chiếu bảng `payments` hoặc `shipments`:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.order_total), 0::numeric) AS order_total
FROM demo_cardinality_331.customers AS c
LEFT JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Loại bỏ JOIN không cần thiết thường giảm cả chi phí và rủi ro sai grain. Đây là một cải tiến thiết kế truy vấn, không phụ thuộc mẹo index.

## 8. EXISTS và NOT EXISTS thay cho JOIN khi chỉ cần biết có hay không

Giả sử câu hỏi:

> Khách nào có ít nhất một đơn paid?

Nếu viết:

```sql
SELECT c.customer_id, c.customer_name
FROM demo_cardinality_331.customers AS c
JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
ORDER BY c.customer_id;
```

khách An xuất hiện **hai lần** vì có hai đơn paid. Khách Chi cũng xuất hiện hai lần. Truy vấn trả **5 hàng**, dù chỉ có **3 khách** đáp ứng.

Có thể viết `SELECT DISTINCT`, nhưng nếu chỉ cần **tồn tại** ít nhất một đơn, `EXISTS` diễn đạt trực tiếp hơn:

```sql
SELECT c.customer_id, c.customer_name
FROM demo_cardinality_331.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_cardinality_331.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
)
ORDER BY c.customer_id;
```

Kết quả **3 khách**: An, Binh, Chi. Không có lý do nghiệp vụ để tạo nhiều bản ghi khách khi câu hỏi chỉ kiểm tra tồn tại.

Tương tự, tìm khách chưa có đơn:

```sql
SELECT c.customer_id, c.customer_name
FROM demo_cardinality_331.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_cardinality_331.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả chỉ có **Dung**.

### 8.1. Semi join và anti join

Optimizer có thể thực hiện `EXISTS` như một **semi join**: quan tâm bên trái nào có ít nhất một khớp, không cần trả tất cả tổ hợp ở bên phải.

`NOT EXISTS` thường tương ứng **anti join**: giữ những hàng bên trái không có khớp.

Không nên coi câu `WHERE EXISTS` luôn được tối ưu thành cùng một kế hoạch trên mọi DBMS và mọi truy vấn có hàm phức tạp; nhưng về ngữ nghĩa, nó không nhân hàng phía trái như một phép `INNER JOIN` trả mọi cặp khớp.

### 8.2. Nếu cần dữ liệu từ mỗi thanh toán thì sao?

Khi báo cáo thật sự cần một hàng trên **mỗi giao dịch thanh toán**, JOIN từ orders sang payments là phù hợp:

```sql
SELECT
    p.payment_id,
    p.order_id,
    o.customer_id,
    p.paid_amount
FROM demo_cardinality_331.payments AS p
JOIN demo_cardinality_331.orders AS o
  ON o.order_id = p.order_id
ORDER BY p.payment_id;
```

Truy vấn trả **9 hàng**, đúng grain một hàng trên mỗi payment. Fanout không phải lỗi khi grain đầu ra thực sự là payment.

**Không cố loại trùng đúng dữ liệu chi tiết chỉ để mọi câu SQL trả một hàng trên mỗi đơn.**

## 9. Bội số hàng tăng do JOIN sai khóa

### 9.1. Quên điều kiện JOIN

```sql
-- KHÔNG dùng nếu mục tiêu là ghép khách với đơn của chính họ.
SELECT COUNT(*)
FROM demo_cardinality_331.customers AS c
CROSS JOIN demo_cardinality_331.orders AS o;
```

Có 4 khách × 6 đơn = **24 hàng**. Đây là tích Descartes:

\[
|\mathrm{CROSS\ JOIN}| = |C|\times|O| = 4\times6=24
\]

`CROSS JOIN` có mục đích hợp lệ, ví dụ dựng mọi tổ hợp ngày × cửa hàng. Nó chỉ là lỗi khi người viết **quên điều kiện định danh** mà vẫn kỳ vọng quan hệ khách–đơn.

Câu:

```sql
FROM demo_cardinality_331.customers AS c,
     demo_cardinality_331.orders AS o
```

không có điều kiện nối cũng mang ngữ nghĩa nhân tổ hợp tương tự. Đừng nhầm hai bảng xuất hiện trong `FROM` với việc hệ quản trị tự suy ra khóa ngoại để nối cho đúng.

### 9.2. Nối bằng khóa không duy nhất

Nếu một đơn có nhiều shipment và bạn nối dựa vào `order_id`, không thể kỳ vọng một hàng shipment: `order_id` không unique ở bảng con.

Một chiều sản phẩm hoặc danh mục cũng có thể có **nhiều phiên bản lịch sử** cho cùng mã sản phẩm. Nếu chỉ nối `product_id` mà bỏ điều kiện hiệu lực, một giao dịch có thể khớp nhiều phiên bản dimension, làm nhân doanh thu.

Ví dụ khái niệm:

```sql
-- Chỉ là ví dụ cấu trúc; chưa tạo hai bảng này trong dataset.
SELECT f.sale_id, d.product_category
FROM sales AS f
JOIN product_dimension_history AS d
  ON d.product_id = f.product_id;
```

Nếu `product_dimension_history` có ba bản cho cùng product, một sale có thể xuất hiện ba lần. Thường cần:

```sql
ON d.product_id = f.product_id
AND f.sold_at >= d.valid_from
AND f.sold_at <  d.valid_to
```

và **bảo đảm các khoảng hiệu lực của cùng product không chồng lấn**. Chỉ thêm điều kiện thời gian chưa đủ nếu dimension bản thân có dữ liệu trùng khoảng.

### 9.3. Bỏ một phần của khóa ghép

Giả sử khóa nghiệp vụ là:

```text
(tenant_id, external_order_id)
```

Hai tenant đều có mã `ORD-001`. Nếu JOIN chỉ theo `external_order_id`, các hàng của hai tenant sẽ khớp chéo, làm nhân dữ liệu và có thể gây rò rỉ số liệu giữa tenant.

Cần nối đủ:

```sql
ON t.tenant_id = s.tenant_id
AND t.external_order_id = s.external_order_id
```

Đây là vấn đề **tính đúng đắn dữ liệu**, không chỉ tối ưu hóa. Không thể chữa bằng index nếu điều kiện nối thiếu thành phần định danh.

### 9.4. OR trong điều kiện JOIN

```sql
ON a.primary_key = b.key
OR a.alternate_key = b.key
```

có thể khiến một hàng A khớp **nhiều hàng B**, thậm chí có nhiều đường khớp hợp lệ. Optimizer cũng có thể khó ước lượng selectivity hơn.

Khi cần ưu tiên khóa chính rồi mới khóa phụ, nên mô tả quy tắc một cách tường minh, có thể dùng phân nhánh, một bảng ánh xạ khóa, `LATERAL` với cách chọn ứng viên có thứ tự hoặc bước đối soát. `OR` không tự bảo đảm “chỉ lấy một hàng bên phải”.

## 10. Những nguồn fanout khác ngoài JOIN hai bảng con

### 10.1. JOIN nhiều–nhiều

Một sản phẩm có thể thuộc nhiều chương trình khuyến mãi, và một chương trình có nhiều sản phẩm. Nếu không có grain chuẩn, phép nối qua bảng liên kết có thể tạo nhiều tổ hợp.

Bản chất:

```text
products 1 ──< product_promotions >── 1 promotions
```

Một truy vấn có thể đúng khi muốn **tất cả các quan hệ sản phẩm–khuyến mãi**, nhưng sai khi muốn **một hàng mỗi sản phẩm** và lại lấy `SUM(product_price)` sau nối.

### 10.2. JOIN theo khoảng thời gian hoặc điều kiện bất đẳng thức

```sql
ON e.occurred_at >= w.start_at
AND e.occurred_at < w.end_at
```

Một event có thể nằm trong **nhiều cửa sổ chồng lấn**, nên kết quả là một–nhiều. Với tính toán rolling windows, đó có thể là điều kiện hợp lệ nhưng cần dự đoán số khớp.

Một khoảng rất rộng hoặc chồng lấn dày có thể tạo trung gian lớn dù mỗi bảng riêng không lớn.

### 10.3. UNNEST, jsonb_array_elements và generate_series

Độ lớn trung gian có thể tăng **mà không cần JOIN bảng thường**:

```sql
SELECT
    o.order_id,
    g.n
FROM demo_cardinality_331.orders AS o
CROSS JOIN generate_series(1, 5) AS g(n)
ORDER BY o.order_id, g.n;
```

Sáu đơn × 5 giá trị = **30 hàng**.

Tương tự, `UNNEST` mở một array thành nhiều dòng, `jsonb_array_elements` mở nhiều phần tử JSON. Nếu sau đó JOIN tiếp một bảng con 1:N, số hàng có thể nhân nữa.

### 10.4. Recursive CTE

Một recursive CTE duyệt cây hoặc đồ thị có thể tạo nhiều đường đi tới cùng một nút. Với `UNION ALL`, mỗi đường là một hàng có thể lặp node, đặc biệt nguy hiểm khi đồ thị có chu trình mà truy vấn không kiểm soát điểm dừng.

Độ sâu, số nhánh, điều kiện kết thúc và việc kiểm soát chu trình quyết định số hàng trung gian. Đừng chỉ nhìn số đỉnh cuối cùng rồi suy ra recursive CTE sẽ nhẹ.

### 10.5. UNION ALL

`UNION ALL` cộng tất cả hàng từ các nhánh mà không khử trùng. Nếu mỗi nhánh trả cùng một đối tượng, đầu ra có nhiều bản sao theo ngữ nghĩa bag. `UNION` có thể loại hàng trùng nhưng phải tính chi phí khử trùng và đúng tập cột dùng so sánh.

### 10.6. GROUPING SETS, ROLLUP và CUBE

Một nhóm dữ liệu có thể được tổng hợp theo **nhiều cấp** trong cùng câu SQL. `GROUPING SETS`, `ROLLUP` và `CUBE` tạo nhiều hàng tổng theo các cấp khác nhau; đây là hành vi có mục đích, nhưng nếu ứng dụng tưởng mọi hàng đều ở cùng grain sẽ cộng chồng cả chi tiết lẫn tổng.

Khi kết quả gồm nhiều cấp, cần phân biệt `GROUPING(...)` hoặc nhãn cấp tổng hợp để không tính trùng.

## 11. Ước lượng số hàng là một dự đoán, không phải COUNT(*) thật

Query planner cần chọn thứ tự nối và thuật toán **trước khi thực thi truy vấn**. Nó không thể mặc định chạy mọi tổ hợp JOIN để đo chính xác trước khi quyết định kế hoạch.

Vì vậy, optimizer dùng thống kê, ràng buộc và mô hình chọn lọc để dự đoán:

- Mỗi bảng còn bao nhiêu hàng sau `WHERE`.
- Mỗi giá trị khóa xuất hiện với tần suất như thế nào.
- Mỗi phép JOIN dự kiến tạo bao nhiêu cặp khớp.
- Mỗi `GROUP BY` có bao nhiêu nhóm khác nhau.
- Sort/hash có cần bao nhiêu bộ nhớ.
- Index scan, sequential scan, nested loop, hash join hay merge join có lợi hơn.

### 11.1. Selectivity

Nếu bảng có một triệu đơn, điều kiện:

```sql
WHERE status = 'paid'
```

ước lượng giữ lại 80% số hàng, thì:

\[
\text{rows sau lọc}
\approx 1\,000\,000 \times 0.8
=800\,000
\]

Giá trị **0.8** phải đến từ thống kê/mô hình thích hợp, không phải đoán một cách tùy tiện. Nếu tỷ lệ paid thực tế là 99%, planner dự đoán 800.000 thay vì 990.000; sai số này có thể lan tới các phép JOIN sau.

### 11.2. Ước lượng JOIN equi theo số giá trị phân biệt

Một mô hình đơn giản trong điều kiện phân bố tương đối đều và không có các yếu tố phức tạp:

\[
|A\bowtie B|
\approx
\frac{|A|\times|B|}
{\max(NDV(A.k), NDV(B.k))}
\]

Đây là **công thức trực giác**, không phải thuật toán duy nhất của PostgreSQL. Nó không tự tính đúng cho outer join, NULL, dữ liệu lệch, nhiều điều kiện, ràng buộc đặc biệt hoặc sự phụ thuộc giữa cột.

Áp dụng bảng `orders` và `payments` trong dữ liệu mẫu:

- `orders` có 6 hàng và 6 giá trị `order_id` khác nhau.
- `payments` có 9 hàng và 5 giá trị `order_id` khác nhau.
- `9/6` không phải số thanh toán cố định trên mỗi đơn vì có đơn 0, đơn 3.

Ước lượng đơn giản:

\[
\frac{6\times9}{\max(6,5)}=9
\]

Với `INNER JOIN orders–payments`, kết quả **thực tế cũng là 9 hàng** vì mỗi thanh toán tham chiếu đúng một đơn hợp lệ. Nhưng đây không phải bảo đảm mọi phép JOIN khác đều được ước lượng chính xác.

### 11.3. Dữ liệu lệch có thể phá vỡ giả định phân bố đều

Xét một hệ sản xuất:

```text
10.000 khách
1.000.000 đơn
```

Số đơn trung bình là 100/khách. Nhưng có thể có:

```text
1 khách doanh nghiệp lớn: 400.000 đơn
9.999 khách còn lại: 600.000 đơn
```

Nếu lọc đúng khách doanh nghiệp lớn, dự đoán “khoảng 100 đơn” sẽ sai cực lớn. Index scan với một chiến lược tốt cho khách ít đơn có thể kém hiệu quả với khách hàng trăm nghìn đơn.

Các giá trị xuất hiện đặc biệt thường xuyên được gọi là **most common values (MCV)**. Thống kê tốt cần nhận ra độ lệch ấy khi có thể.

### 11.4. Nhiều điều kiện lọc có thể tương quan

Giả sử trong hệ thống:

- Phần lớn đơn `status='cancelled'` là đơn rất cũ.
- Phần lớn đơn mới đều `status='pending'`.

Câu:

```sql
WHERE ordered_on >= DATE '2025-06-01'
  AND status = 'cancelled'
```

không nhất thiết có selectivity bằng:

\[
P(\text{đơn mới})\times P(\text{cancelled})
\]

vì hai điều kiện **có tương quan**. Nếu planner giả sử độc lập, nó có thể ước lượng số hàng sau lọc sai đáng kể.

Cần phân biệt:

- **Độ lệch một cột:** một giá trị rất phổ biến.
- **Tương quan nhiều cột:** biết giá trị cột A giúp dự đoán cột B.
- **Tương quan giữa các bảng:** bản ghi khớp thường tập trung vào một số khóa hoặc cặp điều kiện; khó mô hình hóa hơn.
- **Thống kê cũ:** dữ liệu đã thay đổi nhiều sau lần `ANALYZE` gần nhất.

## 12. Đọc estimated rows và actual rows từ EXPLAIN

PostgreSQL có công cụ:

```sql
EXPLAIN
SELECT
    o.order_id,
    p.payment_id,
    s.shipment_id
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

`EXPLAIN` không chạy truy vấn chỉ đọc này mà trình bày **kế hoạch được dự đoán**: các node scan, join, sort/aggregate; `rows=...` và `width=...` dự kiến; chi phí `cost=...`.

Để đo số hàng **thực tế**, dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    p.payment_id,
    s.shipment_id
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

Với dữ liệu mẫu, số hàng logic đầu ra của **phép nối cuối** là **16**, nhưng dạng plan cụ thể (hash/nested loop/merge), estimated rows và thời gian tùy DBMS/phiên bản/thống kê.

### 12.1. Một ví dụ đọc plan mang tính minh họa

Đây là **sơ đồ giả lập**, không phải stdout thực tế cố định của PostgreSQL:

```text
Hash Left Join  (cost=... rows=12 width=...)
  (actual time=... rows=16 loops=1)
  Hash Cond: ...
  -> Hash Left Join  (... rows=9 ...)
       (actual ... rows=10 loops=1)
       -> Seq Scan on orders (...)
            (actual ... rows=6 loops=1)
       -> Hash ...
            -> Seq Scan on payments (...)
                 (actual ... rows=9 loops=1)
  -> Hash ...
       -> Seq Scan on shipments (...)
            (actual ... rows=8 loops=1)
```

Những giá trị `actual rows=6,9,8,10,16` phù hợp với kích thước bộ dữ liệu và thứ tự nối được minh họa. Planner có thể chọn thứ tự nối khác, vẫn trả 16 hàng cuối.

### 12.2. Những trường plan cần đọc

| Trường | Ý nghĩa |
| --- | --- |
| `cost=startup..total` | Chi phí tương đối do optimizer ước lượng, không phải mili giây |
| `rows=...` | Số hàng **ước lượng** node sẽ xuất ra mỗi lần thực thi |
| `width=...` | Độ rộng hàng trung bình ước lượng, tính bằng byte |
| `actual time=...` | Thời gian đo được khi `ANALYZE` thực thi |
| `actual rows=...` | Số hàng trung bình node trả **mỗi lần chạy** |
| `loops=...` | Số lần node được thực thi |
| `Rows Removed by Filter` | Hàng bị loại ở điều kiện filter của node |
| `Buffers: shared hit/read ...` | Thống kê truy cập buffer/khối dữ liệu |
| `Sort Method` | Cách sort, bộ nhớ hoặc đĩa tạm được sử dụng |
| `Hash Batches` / `Memory Usage` | Thông tin việc tạo hash và phân chia batch nếu có |

`cost` là đơn vị nội bộ để so sánh kế hoạch. Nó **không phải tiền**, không phải số hàng, cũng không phải một giá trị thời gian thật.

### 12.3. Actual rows và loops: bẫy rất quan trọng

Với node chạy một lần:

```text
actual rows=16 loops=1
```

ta có 16 hàng đầu ra từ node ấy.

Nhưng với nested loop, một node bên trong có thể chạy nhiều lần:

```text
Index Scan on payments (... actual rows=2 loops=1000)
```

`actual rows` là **bình quân trên mỗi loop**, không phải tổng số hàng của tất cả các loop. Để suy ra gần đúng tổng số hàng node phát ra, nhân:

\[
\text{actual rows per loop}\times\text{loops}
\]

Ở ví dụ trên: khoảng \(2\times1000=2000\) hàng. Một số giá trị trong plan được làm tròn nên đây có thể chỉ là gần đúng.

**Không so sánh máy móc `actual rows=2` của node bên trong với `rows=2` rồi kết luận toàn phép nối rẻ**: 1.000 vòng lặp vẫn có thể tốn nhiều I/O hoặc CPU.

### 12.4. Nhìn nơi số hàng phình lên

Một cách đọc kế hoạch hữu ích:

```text
Scan orders:            6 hàng
Left join payments:    10 hàng
Left join shipments:   16 hàng
Aggregate by order:     6 hàng
```

Kết quả cuối có 6 nhóm nhưng đã có 16 hàng trước aggregate. Với bảng lớn, tỷ số này có thể lớn hơn rất nhiều.

Khi plan có nhiều tầng, hãy tìm node đầu tiên mà `actual rows` tăng bất ngờ so với input/so với grain mong muốn, hoặc nơi `actual rows` lệch xa `rows` ước lượng. Đây thường là nơi cần điều tra điều kiện JOIN, thống kê và cách truy vấn trả lời câu hỏi nghiệp vụ.

### 12.5. EXPLAIN ANALYZE thực sự chạy câu SQL

`EXPLAIN (ANALYZE)` **thực thi truy vấn** để đo. Đối với `SELECT` đọc, nó tiêu tốn tài nguyên nhưng không chủ động sửa dữ liệu. Đối với `INSERT`, `UPDATE`, `DELETE` hoặc `MERGE`, nó **có thể thay đổi dữ liệu**.

Không dùng `EXPLAIN ANALYZE UPDATE ...` trên production chỉ để “xem plan” mà chưa kiểm soát transaction, trigger và side effect. Với thao tác ghi, nếu chỉ cần kế hoạch dự đoán, dùng `EXPLAIN` không `ANALYZE` hoặc thử trong môi trường an toàn theo quy trình riêng.

### 12.6. Nếu node chạy song song?

Trong parallel plan, `loops`, worker, `Gather` và thống kê từng worker làm việc cộng/trừ hàng cần thận trọng hơn. Không cộng tùy ý số hàng của tất cả các node vì một hàng có thể đi qua nhiều node và bị đếm nhiều lần theo từng tầng.

Mục tiêu là biết **dòng dữ liệu ở mỗi bước**, không phải cộng toàn bộ `actual rows` của mọi node thành “tổng hàng truy vấn”.

## 13. Nested Loop, Hash Join và Merge Join vẫn phải tạo đủ hàng khớp

Một phép JOIN có thể được thực thi bằng nhiều thuật toán vật lý. Tuy nhiên, **thuật toán không được làm thay đổi ngữ nghĩa của câu SQL**: nếu hai phía có 2 và 3 hàng cùng khóa, một equi-join cần trả 6 kết hợp theo ngữ nghĩa bag, trừ khi câu SQL có điều kiện hoặc phép toán loại bớt.

### 13.1. Nested Loop Join

Mô hình trực giác:

```text
for mỗi hàng outer:
    tìm tất cả hàng inner thỏa điều kiện JOIN
    phát từng cặp khớp
```

Khi phía ngoài nhỏ và phía trong có index phù hợp, nested loop có thể rất hiệu quả. Nhưng nếu planner ước lượng outer chỉ 100 hàng mà thực tế 100.000, inner scan có thể bị gọi hàng trăm nghìn lần.

Ví dụ plan giả lập:

```text
Nested Loop (...)
  -> Seq Scan on filtered_orders (... actual rows=100000 loops=1)
  -> Index Scan on payments (... actual rows=3 loops=100000)
```

Inner scan có trung bình 3 hàng trên mỗi vòng, nhưng **100.000 vòng lặp** nghĩa là khoảng 300.000 hàng từ inner và nhiều lần tra cứu index. Không nên chỉ nhìn `actual rows=3` và kết luận node nhỏ.

Nested loop có thể đúng cả khi dữ liệu lớn, nếu mỗi tra cứu rất nhanh và điều kiện chọn lọc tốt. Cần đọc `loops`, thời gian, buffer và số hàng ra.

### 13.2. Hash Join

Hash join thường xây dựng một bảng băm từ một phía rồi tra khóa từ phía còn lại. Với khóa trùng, hash join vẫn tạo mọi tổ hợp khớp.

Nếu bên xây hash quá lớn so với tài nguyên, PostgreSQL có thể phân nhiều batch và dùng tệp tạm. Khi đọc `EXPLAIN (ANALYZE, BUFFERS)`, chú ý `Buckets`, `Batches`, `Memory Usage` và các chỉ số temp read/write nếu xuất hiện.

Hash join không tự `DISTINCT`, không tự cộng tiền theo một order và không sửa fanout nhiều–nhiều.

### 13.3. Merge Join

Merge join thường có lợi khi hai đầu vào đã được sắp theo khóa hoặc có thể sort với chi phí hợp lý. Khi gặp nhóm khóa trùng ở cả hai bên, nó vẫn phải tạo các cặp tương ứng.

Nếu A có 100 hàng khóa HOT và B có 200 hàng khóa HOT, kết quả hợp lệ của riêng nhóm đó là **20.000 cặp**. Cả merge join và hash join đều phải tính tới bội số ấy.

### 13.4. Chọn thuật toán theo loại công việc

| Thuật toán | Thường hữu ích khi | Rủi ro cần xem trong plan |
| --- | --- | --- |
| Nested Loop | Outer nhỏ, inner lookup qua index hiệu quả | Nhiều `loops`, lookup lặp, fanout mỗi khóa |
| Hash Join | Equi-join trên lượng dữ liệu đáng kể | Bộ nhớ hash, nhiều batches, tệp tạm |
| Merge Join | Hai đầu vào có thứ tự phù hợp | Chi phí sort, nhiều bản cùng khóa |
| Semi/Anti Join | Chỉ cần tồn tại hoặc không tồn tại | Không thay được JOIN khi cần mọi hàng chi tiết |

**Đổi thuật toán không chữa được một phép nối có kết quả logic sai.** Trước tiên phải xác định grain đúng, sau đó mới tối ưu đường thực thi.

## 14. Sai lệch ước lượng có thể lan rộng qua nhiều node

Planner chọn phương án dựa trên **ước lượng** trước khi chạy. Nếu một phép scan hoặc filter bị đánh giá sai, kết quả ước lượng ấy trở thành đầu vào để tính chi phí của những JOIN tiếp theo.

Tình huống giả định:

```text
Node                 Estimated rows     Actual rows
---------------------------------------------------
Scan/filter A              100             10.000
Join với B                 200            100.000
Join tiếp C                400          2.000.000
GroupAggregate              50                500
```

Cuối cùng chỉ có 500 nhóm nhưng query đã xử lý đến 2 triệu hàng trước aggregate.

### 14.1. Ước lượng thấp gây hệ quả gì?

Planner có thể:

- Chọn nested loop vì nghĩ phía ngoài chỉ vài hàng, trong khi thực tế rất nhiều.
- Đánh giá thấp số hàng phải sort hoặc hash.
- Chọn thứ tự nối làm phình kết quả sớm.
- Dự tính sai số nhóm `GROUP BY`, chi phí `DISTINCT` hoặc window function.
- Dự kiến không cần nhiều bộ nhớ, nhưng thao tác thực phải dùng batch hoặc tệp tạm.

Ước lượng cao quá mức cũng có thể gây bất lợi: planner có thể chọn scan/hash với chi phí chuẩn bị cao khi thực tế chỉ cần tra vài khóa bằng index.

### 14.2. Hệ số sai lệch

Với cả hai giá trị dương:

\[
\text{error factor}=
\max\left(
\frac{\text{actual rows}}{\text{estimated rows}},
\frac{\text{estimated rows}}{\text{actual rows}}
\right)
\]

Nếu `rows=100` nhưng `actual rows=50.000 loops=1`, sai số là khoảng **500 lần**.

Nếu `loops` lớn, cần đặt số hàng ước lượng/thực tế về cùng cơ sở **mỗi lần chạy** trước khi so. Trường hợp actual 0 phải xử lý riêng, không chia cho 0.

### 14.3. Sai ở đâu thì điều tra ở đó

| Biểu hiện | Nguyên nhân có thể |
| --- | --- |
| Filter một cột sai | Thống kê cũ hoặc tần suất giá trị không đồng đều |
| Filter nhiều cột sai | Tương quan giữa các cột, thiếu thống kê kết hợp |
| JOIN tăng hàng bất thường | Quan hệ 1:N/N:M, khóa nóng, thiếu phần khóa JOIN |
| Một node có inner loops cực lớn | Outer lớn hơn dự kiến hoặc inner lookup quá nhiều |
| Hash/Sort dùng disk | Số hàng, width, giới hạn bộ nhớ hoặc độ lệch |
| Cột output cuối vẫn ít | Aggregate/DISTINCT chỉ giảm hàng **sau** khi xử lý trung gian |

Không mặc định mỗi khi SQL chạy chậm là “thiếu index”: có thể query logic đang sinh ra hàng triệu tổ hợp đúng theo những gì bạn đã viết.

## 15. Dữ liệu lệch có thể làm ước lượng JOIN sai hàng trăm lần

Công thức dựa trên NDV và giả định phân bố đều chỉ là cách xấp xỉ. Hãy xét hai bảng A và B đều có **10.000 hàng**:

- Mỗi bảng có **9.000 hàng** cùng `key='HOT'`.
- 1.000 hàng còn lại của mỗi bảng có những khóa khác nhau, khớp nhau một–một.
- Mỗi bảng có **1.001 khóa phân biệt**.

Số hàng JOIN thực tế:

\[
9.000\times9.000 + 1.000 = 81.001.000
\]

Nếu áp dụng công thức đồng đều giản lược:

\[
\frac{10.000\times10.000}{1.001}\approx99.900
\]

Ước lượng sẽ thấp hơn thực tế khoảng **811 lần**.

Dữ liệu này có một **khóa nóng** (*hot key*) chiếm 90% ở cả hai bảng. Tích của hai nhóm lớn tạo đến 81 triệu hàng, dù mỗi bảng chỉ có 10 nghìn.

### 15.1. MCV có thể giúp planner hiểu phân bố

PostgreSQL có thống kê những giá trị xuất hiện thường xuyên (*most common values*, MCV) để planner không phải luôn giả định đồng đều.

Nếu khóa HOT được ghi nhận với tần suất đủ chính xác, planner có thể chọn kế hoạch tốt hơn. Nhưng **thống kê không loại bỏ 81 triệu cặp thật** nếu SQL thực sự đòi liệt kê toàn bộ cặp.

Nếu mục tiêu chỉ hỏi “những khóa nào xuất hiện ở cả A và B”, một semi join hoặc tổng hợp theo khóa có thể tránh phát mọi cặp; nếu mục tiêu là liệt kê mọi cặp HOT, chi phí tạo chúng là bản chất bài toán.

### 15.2. Tương quan giữa nhiều điều kiện

Ví dụ với dữ liệu sản xuất, đơn `status='cancelled'` chủ yếu có ngày rất cũ. Điều kiện:

```sql
WHERE status = 'cancelled'
  AND ordered_on >= DATE '2025-06-01'
```

không thể luôn được ước lượng bằng tích hai tỷ lệ độc lập. Nếu hai cột phụ thuộc nhau, công thức độc lập có thể dự đoán sai.

Phân biệt **skew một cột**, **tương quan các cột trong cùng bảng** và **phụ thuộc giữa hai bảng**; chúng không có một cách sửa thống kê chung cho mọi trường hợp.

## 16. Thống kê PostgreSQL: ANALYZE, pg_stats và extended statistics

### 16.1. Thu thập thống kê cho bộ dữ liệu thực hành

```sql
ANALYZE demo_cardinality_331.customers;
ANALYZE demo_cardinality_331.orders;
ANALYZE demo_cardinality_331.order_items;
ANALYZE demo_cardinality_331.payments;
ANALYZE demo_cardinality_331.shipments;
```

`ANALYZE` thu thập thông tin thống kê phục vụ planner. Nó không sửa dữ liệu đơn hàng, nhưng có chi phí I/O/CPU và cần được quản lý trên bảng rất lớn.

Trong PostgreSQL, autovacuum/autoanalyze thường cập nhật thống kê theo những ngưỡng và cấu hình nhất định. Sau một đợt nạp lớn làm thay đổi mạnh số hàng hoặc phân bố, có thể cần xem liệu thống kê đã đủ mới chưa.

### 16.2. Xem thống kê một cột

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'demo_cardinality_331'
  AND tablename = 'orders'
ORDER BY attname;
```

Các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `null_frac` | Tỷ lệ giá trị NULL ước lượng |
| `n_distinct` | Số giá trị phân biệt ước lượng theo quy ước PostgreSQL |
| `most_common_vals` | Các giá trị phổ biến được ghi nhận |
| `most_common_freqs` | Tần suất của những giá trị phổ biến |
| `histogram_bounds` | Ranh giới histogram dùng cho nhiều phép lọc khoảng |
| `correlation` | Tương quan thứ tự logic của cột với thứ tự vật lý của các hàng trong bảng |

`n_distinct` có thể âm theo quy ước biểu diễn một tỷ lệ phụ thuộc số hàng, không phải “số giá trị distinct âm”.

**Lưu ý:** `pg_stats.correlation` **không** phải hệ số tương quan giữa `status` và `ordered_on`. Nó chủ yếu mô tả mức tương quan giữa thứ tự cột với vị trí vật lý, ảnh hưởng một số ước lượng chi phí index scan.

### 16.3. Xem trạng thái thống kê của bảng

```sql
SELECT
    schemaname,
    tablename,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'demo_cardinality_331'
ORDER BY tablename;
```

`n_live_tup` là một **ước lượng**, không phải `COUNT(*)` đúng tuyệt đối tại mọi thời điểm. `n_mod_since_analyze` và thời điểm analyze giúp nhận diện tình huống dữ liệu có thể đã thay đổi nhiều so với thống kê planner dùng.

### 16.4. Extended statistics cho nhiều cột

PostgreSQL hỗ trợ thống kê đa cột:

```sql
CREATE STATISTICS demo_331_orders_customer_status
    (dependencies, mcv, ndistinct)
ON customer_id, status
FROM demo_cardinality_331.orders;

ANALYZE demo_cardinality_331.orders;
```

Các loại:

- `dependencies`: mô hình phụ thuộc hàm thống kê.
- `mcv`: tổ hợp giá trị xuất hiện thường gặp.
- `ndistinct`: số tổ hợp giá trị phân biệt.

Chúng có thể giúp ước lượng một số điều kiện lọc kết hợp hoặc `GROUP BY` trên **cùng bảng**, tùy câu truy vấn và phiên bản PostgreSQL.

**Giới hạn quan trọng:** thống kê đa cột trên một bảng không tự mô hình hóa đầy đủ sự tương quan **giữa các bảng**. Không được kết luận cứ chạy `CREATE STATISTICS` là mọi join estimate sẽ chính xác.

### 16.5. Tăng mục tiêu thống kê một cột

```sql
ALTER TABLE demo_cardinality_331.orders
ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE demo_cardinality_331.orders;
```

Con số 500 chỉ minh họa cú pháp. Mục tiêu cao hơn có thể cho thống kê chi tiết hơn đối với dữ liệu phân bố phức tạp, nhưng tăng chi phí thu thập/bảo quản. Trên bảng mẫu 6 hàng, nó không có ý nghĩa hiệu năng rõ.

Nếu lỗi nằm ở **điều kiện JOIN thiếu tenant**, bổ sung thống kê không phải phương án sửa; phải sửa chính câu JOIN.

## 17. Index cải thiện tra cứu, không tự biến 1:N thành 1:1

PostgreSQL không mặc định tạo index trên mọi cột **phía tham chiếu khóa ngoại** chỉ vì có `FOREIGN KEY`. Ta có thể bổ sung:

```sql
CREATE INDEX idx_demo331_orders_customer
ON demo_cardinality_331.orders (customer_id);

CREATE INDEX idx_demo331_items_order
ON demo_cardinality_331.order_items (order_id);

CREATE INDEX idx_demo331_payments_order
ON demo_cardinality_331.payments (order_id);

CREATE INDEX idx_demo331_shipments_order
ON demo_cardinality_331.shipments (order_id);
```

Các index này có thể giúp join và tìm hàng con theo khóa, đặc biệt khi outer nhỏ và inner được tra nhiều lần.

Nhưng đơn 101 vẫn có 2 payments × 3 shipments = 6 tổ hợp. Hai `LEFT JOIN` vẫn trả **16 hàng** và tổng tiền tính sai nếu cộng `order_total` sau fanout.

### 17.1. Index unique khác index thường

`PRIMARY KEY(orders.order_id)` đảm bảo một hàng trên mỗi đơn. Index thường trên `payments(order_id)` không cấm nhiều thanh toán cho một đơn.

Không thêm `UNIQUE(payments.order_id)` chỉ để “tối ưu” khi nghiệp vụ cho phép thanh toán nhiều lần. Thay vì đó, tạo một tập **đã tổng hợp theo order_id**, có tối đa một hàng mỗi khóa.

### 17.2. Partial index cho truy vấn lọc

Ví dụ:

```sql
CREATE INDEX idx_demo331_paid_orders_date
ON demo_cardinality_331.orders (ordered_on, order_id)
WHERE status = 'paid';
```

Nếu workload thường lọc paid theo khoảng ngày, index này có thể giúp. Nhưng index không tự hữu ích trên bảng rất nhỏ; PostgreSQL có thể chọn sequential scan vì rẻ hơn.

Lựa chọn index thực tế cần căn cứ câu `WHERE`/`JOIN`, kích thước bảng, phân bố, tần suất ghi và kế hoạch đo trên dữ liệu đại diện.

### 17.3. Đừng dùng tùy chọn planner làm phương án sửa lâu dài

PostgreSQL có cấu hình như `enable_nestloop`, `enable_hashjoin`, `enable_mergejoin` để nghiên cứu phương án kế hoạch. Vô hiệu hóa một loại JOIN chỉ để ép kế hoạch khác có thể che vấn đề thống kê hoặc câu SQL sai grain.

Hướng sửa bền vững: **SQL đúng → thống kê mới → index phù hợp → đo plan**, thay vì chỉ thay cờ optimizer.

## 18. Lọc sớm, nhưng phải giữ ngữ nghĩa OUTER JOIN

### 18.1. Lọc tập đơn cần báo cáo

Ví dụ chỉ lấy đơn paid từ 01/06 đến trước 03/06:

```sql
WITH filtered_orders AS (
    SELECT *
    FROM demo_cardinality_331.orders
    WHERE status = 'paid'
      AND ordered_on >= DATE '2025-06-01'
      AND ordered_on <  DATE '2025-06-03'
)
SELECT o.order_id, p.payment_id
FROM filtered_orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id, p.payment_id;
```

Tập đơn lọc gồm **101, 102, 104** (3 đơn). `LEFT JOIN payments` trả **2+1+2=5 hàng**, ít hơn 10 hàng khi dùng cả 6 đơn.

Điều này diễn tả lợi ích **giới hạn phạm vi đầu vào**. Nhưng việc đặt CTE không tự bảo đảm PostgreSQL phải vật hóa bảng lọc trước; optimizer có thể inline hoặc đẩy lọc tùy ngữ nghĩa. Dùng `EXPLAIN` để biết kế hoạch vật lý thật.

### 18.2. WHERE trên bảng phải sau LEFT JOIN có thể làm mất hàng cha

Muốn giữ mọi đơn, kể cả đơn không có khoản thanh toán >=50:

```sql
SELECT o.order_id, p.payment_id, p.paid_amount
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
 AND p.paid_amount >= 50
ORDER BY o.order_id, p.payment_id;
```

Điều kiện trong `ON` quyết định payment nào khớp, còn `LEFT JOIN` giữ đơn bên trái.

Nếu chuyển sang:

```sql
-- Ngữ nghĩa khác: loại đơn không có payment đạt điều kiện.
SELECT o.order_id, p.payment_id, p.paid_amount
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
WHERE p.paid_amount >= 50
ORDER BY o.order_id, p.payment_id;
```

các hàng mở rộng `NULL` bị loại. Đây là **lỗi nghĩa SQL** nếu ứng dụng cần giữ mọi đơn, không chỉ là vấn đề hiệu năng.

### 18.3. Lọc không tự xóa fanout còn lại

Giả sử chỉ giữ đơn 101. Nó vẫn có hai payment và ba shipment, nên hai LEFT JOIN vẫn tạo sáu hàng. Nếu báo cáo chỉ cần tổng tiền thanh toán và số vận chuyển, **preaggregate** hoặc **chọn grain phù hợp** mới là cách xử lý số hàng trung gian đúng đắn.

## 19. Khi chỉ cần một hàng con: LATERAL hoặc ROW_NUMBER

Một bài toán khác hẳn với “đếm mọi shipment” là:

> Mỗi đơn chỉ cần thông tin **lượt giao hàng mới nhất**.

Khi đó một hàng trên mỗi đơn là đúng nghiệp vụ, và ta có thể chọn một shipment theo quy tắc minh bạch.

### 19.1. PostgreSQL LEFT JOIN LATERAL

```sql
SELECT
    o.order_id,
    recent.shipment_id,
    recent.shipped_on
FROM demo_cardinality_331.orders AS o
LEFT JOIN LATERAL (
    SELECT
        s.shipment_id,
        s.shipped_on
    FROM demo_cardinality_331.shipments AS s
    WHERE s.order_id = o.order_id
    ORDER BY
        s.shipped_on DESC,
        s.shipment_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY o.order_id;
```

Kết quả **6 hàng**, một mỗi đơn:

| order_id | shipment_id mới nhất |
| ---: | ---: |
| 101 | 603 |
| 102 | 604 |
| 103 | 605 |
| 104 | 607 |
| 105 | `NULL` |
| 106 | 608 |

`LIMIT 1` nằm **trong subquery phụ thuộc từng đơn**, vì vậy chọn tối đa một shipment cho **mỗi** `o.order_id`. `ORDER BY shipped_on DESC, shipment_id DESC` có tie-breaker để lựa chọn có tính xác định khi nhiều shipment cùng ngày.

### 19.2. ROW_NUMBER trên bảng con

```sql
WITH ranked_shipments AS (
    SELECT
        shipment_id,
        order_id,
        shipped_on,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY shipped_on DESC, shipment_id DESC
        ) AS rn
    FROM demo_cardinality_331.shipments
)
SELECT
    o.order_id,
    s.shipment_id,
    s.shipped_on
FROM demo_cardinality_331.orders AS o
LEFT JOIN ranked_shipments AS s
  ON s.order_id = o.order_id
 AND s.rn = 1
ORDER BY o.order_id;
```

Cũng trả 6 hàng. Đặt `s.rn=1` trong `ON` giúp giữ đơn 105 chưa có shipment.

### 19.3. Những điều KHÔNG nên làm

- `LIMIT 1` ở **cuối** toàn bộ phép JOIN chỉ lấy một hàng **của toàn truy vấn**, không phải một hàng trên mỗi đơn.
- `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY random())` chọn ngẫu nhiên có thể làm báo cáo không ổn định và bỏ hàng hợp lệ.
- Chọn một payment bất kỳ trước khi tính tổng sẽ làm mất những khoản thanh toán khác của đơn.

**Chỉ lựa chọn một hàng con khi nghiệp vụ thật sự chỉ cần một hàng**. Nếu cần tổng tiền mọi payment, hãy tổng hợp tất cả payments theo `order_id` trước khi JOIN.

## 20. DISTINCT, GROUP BY và Window Function không xóa chi phí trung gian đã phát sinh

Một truy vấn có thể kết thúc bằng **4 hàng khách**, dù các phép nối đã tạo nhiều hàng hơn.

```sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count
FROM demo_cardinality_331.customers AS c
LEFT JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Kết quả cuối có **4 hàng**, nhưng ở cấp logic:

- Sáu đơn qua hai bảng con tạo **16 hàng**.
- Khách Dung không có đơn vẫn được giữ bằng một hàng mở rộng `NULL`.
- Tổng trước aggregate theo khách là **17 hàng**.

Trong hệ thống thật, 17 có thể trở thành hàng chục triệu. `COUNT(DISTINCT)` vẫn có thể phải xử lý một lượng lớn giá trị trung gian.

### 20.1. Bỏ JOIN không phục vụ chỉ số

Nếu chỉ hỏi số đơn mỗi khách:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM demo_cardinality_331.customers AS c
LEFT JOIN demo_cardinality_331.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Giờ đầu vào aggregate theo khách chỉ có **7 hàng** thay vì 17. Kết quả vẫn là 4 khách với số đơn **3, 1, 2, 0**.

Bỏ hai JOIN không cần thiết thường tốt hơn việc thêm `DISTINCT` vào một truy vấn vốn mang quá nhiều dữ liệu.

### 20.2. Window Function hoạt động trên grain đã JOIN

```sql
SELECT
    o.order_id,
    p.payment_id,
    s.shipment_id,
    COUNT(*) OVER (
        PARTITION BY o.order_id
    ) AS rows_for_order
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id
ORDER BY o.order_id, p.payment_id, s.shipment_id;
```

Kết quả có **16 hàng**. `rows_for_order` bằng 6 ở mọi dòng của đơn 101, bằng 4 ở đơn 104, bằng 3 ở đơn 106, và bằng 1 ở ba đơn còn lại.

Window function **không tự gom hàng**. Nếu viết `SUM(p.paid_amount) OVER (PARTITION BY o.order_id)` sau phép nối hai bảng con, tổng thanh toán của đơn 101 bị cộng lặp theo số shipment.

### 20.3. Hàng trung gian lớn có thể khiến Sort/HashAggregate dùng disk

Các phép toán `ORDER BY`, `DISTINCT`, `GROUP BY` hoặc window function thường phải xử lý hàng trung gian. Khi dữ liệu quá lớn so với bộ nhớ dành cho operator, plan PostgreSQL có thể có:

```text
Sort Method: external merge  Disk: ...
HashAggregate  Batches: ...
Buffers: temp read=... written=...
```

Không phải mọi sort đều tràn disk, cũng không phải mọi hash aggregate đều tạo temp files. Các chỉ số này là **dấu hiệu khi chúng thực sự xuất hiện trong plan**.

Tăng `work_mem` bừa bãi không phải lời giải chung: mỗi phiên và nhiều operator có thể tiêu thụ bộ nhớ cùng lúc. Hãy giảm fanout và row width không cần thiết trước, rồi điều chỉnh cấu hình bằng số liệu đo và chính sách vận hành.

## 21. Quy trình tìm nơi hàng trung gian phình lên

Khi truy vấn chậm hoặc tổng tiền bị tăng bất thường, đi theo một chuỗi câu hỏi có thể kiểm chứng.

### 21.1. Bước 1 — Nêu grain đầu ra

Ví dụ:

> Một hàng của báo cáo phải đại diện cho đúng **một `order_id`**.

Nếu câu hỏi là “liệt kê mọi thanh toán”, grain phải là `payment_id`. Không thể đánh giá số hàng JOIN đúng hay sai khi chưa nói rõ mỗi hàng có ý nghĩa gì.

### 21.2. Bước 2 — Đo bội số của từng khóa

```sql
SELECT
    order_id,
    COUNT(*) AS payment_count
FROM demo_cardinality_331.payments
GROUP BY order_id
ORDER BY payment_count DESC, order_id;
```

```sql
SELECT
    order_id,
    COUNT(*) AS shipment_count
FROM demo_cardinality_331.shipments
GROUP BY order_id
ORDER BY shipment_count DESC, order_id;
```

Chúng cho thấy khóa nào có nhiều thanh toán và nhiều vận chuyển. Những đơn như 101/104 gây fanout lớn khi nối hai bảng con.

### 21.3. Bước 3 — Đo số hàng sau từng phép nối

```sql
SELECT COUNT(*) AS orders_count
FROM demo_cardinality_331.orders;

SELECT COUNT(*) AS after_payments
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id;

SELECT COUNT(*) AS after_both
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id;
```

Kết quả **6 → 10 → 16**.

Trên production có hàng tỷ hàng, chạy `COUNT(*)` cho mọi tổ hợp có thể rất tốn tài nguyên. Có thể kiểm tra trên một tenant, một dải ngày hoặc khóa đại diện, kết hợp `EXPLAIN`/`EXPLAIN ANALYZE` theo quy trình an toàn.

### 21.4. Bước 4 — Tìm những khóa làm bội số tăng mạnh nhất

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT p.payment_id) AS payment_count,
    COUNT(DISTINCT s.shipment_id) AS shipment_count
FROM demo_cardinality_331.orders AS o
LEFT JOIN demo_cardinality_331.payments AS p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments AS s
  ON s.order_id = o.order_id
GROUP BY o.order_id
ORDER BY joined_rows DESC, o.order_id;
```

| Đơn | Joined rows | Payments | Shipments |
| ---: | ---: | ---: | ---: |
| 101 | 6 | 2 | 3 |
| 104 | 4 | 2 | 2 |
| 106 | 3 | 3 | 1 |
| 102 | 1 | 1 | 1 |
| 103 | 1 | 0 | 1 |
| 105 | 1 | 1 | 0 |

### 21.5. Bước 5 — Kiểm tra điều kiện JOIN, khóa và dữ liệu

Các câu hỏi:

- Có thiếu thành phần `tenant_id`, `source_system` hoặc `line_id` trong khóa không?
- Phía dimension có thực sự unique theo khóa dùng JOIN không?
- Bảng lịch sử có nhiều phiên bản cùng mã mà thiếu điều kiện hiệu lực không?
- Có JOIN hai bảng 1:N độc lập không?
- Có `OR`, điều kiện khoảng chồng lấn, CROSS JOIN hoặc hàm mở rộng mảng/JSON không?
- Bộ lọc trong `WHERE` sau `LEFT JOIN` có đổi ngữ nghĩa không?
- Có đang cộng amount thuộc bảng cha trên tập đã nhân không?

### 21.6. Bước 6 — Đọc EXPLAIN và thống kê

Chú ý node đầu tiên có:

- `actual rows` tăng bất thường.
- `estimated rows` lệch xa `actual rows`.
- `loops` rất cao.
- Hash/sort dùng temp files.
- Filter loại quá nhiều hàng sau khi đã nối.
- Row width quá lớn so với nhu cầu đầu ra.

Xem thời điểm `ANALYZE`, MCV, NDV, độ lệch và tương quan. Nếu SQL sai khóa thì sửa SQL **trước**, không kỳ vọng thống kê mới làm query đúng.

### 21.7. Bước 7 — Chọn phép biến đổi đúng ngữ nghĩa

| Mục tiêu | Kỹ thuật phù hợp |
| --- | --- |
| Chỉ biết có hàng con | `EXISTS` |
| Chỉ biết không có hàng con | `NOT EXISTS` |
| Tổng/count hàng con theo mỗi cha | `GROUP BY child.parent_id` trước JOIN |
| Lấy hàng con mới nhất | `LATERAL ... ORDER BY ... LIMIT 1` hoặc `ROW_NUMBER` |
| Chỉ lấy đơn trong kỳ | Lọc phạm vi và dùng index phù hợp |
| Ghép dimension có lịch sử | Điều kiện hiệu lực và kiểm tra khoảng không chồng lấn |
| Báo cáo một hàng/khách | Đưa chỉ số về grain khách sau khi sửa grain các bảng con |

Không ép mọi query xuống một hàng/cha nếu nghiệp vụ cần từng dòng chi tiết. Cần giảm **những hàng không phục vụ câu hỏi**, không loại bớt dữ liệu hợp lệ một cách tùy tiện.

## 22. Ước lượng ảnh hưởng đến thứ tự JOIN và memory

Planner có thể xem xét các kế hoạch khác nhau cho phép nối nhiều bảng. Trong những trường hợp có thể biến đổi tương đương, nó sẽ tìm cách hạn chế chi phí ước lượng, ví dụ áp dụng bộ lọc chọn lọc trước khi nối bảng lớn.

Một sơ đồ giả định:

```text
A có 1.000.000 hàng
B có 10 hàng sau filter
C có 5.000.000 hàng

Phương án X: JOIN A với C trước → trung gian rất lớn
Phương án Y: lọc/nối B với A trước → trung gian nhỏ hơn, rồi JOIN C
```

Nếu planner ước lượng B còn 900.000 hàng thay vì 10, nó có thể đánh giá sai lợi ích của phương án Y.

Tuy nhiên, với `LEFT JOIN` và các phép toán không giao hoán tùy tiện, không phải mọi thứ tự JOIN đều bảo toàn ngữ nghĩa. Optimizer chỉ được phép chọn trong những biến đổi hợp lệ.

### 22.1. CTE có bảo đảm thực thi từ trên xuống không?

Không mặc định. PostgreSQL hiện đại có thể inline các CTE không yêu cầu vật hóa, hoặc dùng materialization theo điều kiện thích hợp.

`WITH payment_by_order AS (...)` trong phần 7 giúp thể hiện một **ràng buộc grain logic**: kết quả `GROUP BY order_id` có tối đa một hàng trên mỗi khóa. Nhưng plan thực tế có thể khác cách đọc từng dòng câu SQL.

Nếu cần khảo sát materialization, các phiên bản PostgreSQL hỗ trợ `MATERIALIZED`/`NOT MATERIALIZED` cho CTE trong những trường hợp thích hợp. Đây là công cụ tối ưu hóa cần đo, không phải cách chữa fanout sai.

### 22.2. Có nên biến mọi subquery thành JOIN?

Không. Với `EXISTS`, optimizer có thể dùng semi join, tránh tạo mọi hàng con. Viết lại thành `JOIN` thường rồi `DISTINCT` bên ngoài có thể làm tăng hàng trung gian mà không có lợi.

Đừng dùng một khẩu quyết “JOIN luôn nhanh hơn subquery”; hãy so sánh SQL đúng ngữ nghĩa và kế hoạch thực tế.

## 23. Công cụ tương ứng trên các DBMS khác

Bội số hàng và grain không phụ thuộc PostgreSQL, nhưng tên công cụ và cách biểu diễn plan có khác biệt.

| Hệ quản trị | Công cụ kiểm tra plan và thống kê | Điểm cần lưu ý |
| --- | --- | --- |
| PostgreSQL | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)`, `ANALYZE`, `pg_stats` | `actual rows` bình quân theo `loops` |
| MySQL 8.0+ | `EXPLAIN` và `EXPLAIN ANALYZE` trong phiên bản hỗ trợ | Định dạng kế hoạch và chỉ số thời gian khác PostgreSQL |
| SQL Server | Estimated/Actual Execution Plan, statistics, `SET STATISTICS IO ON` | Cần nhìn actual vs estimated row counts, memory grants, cached/parameter-sensitive plan |
| Oracle Database | Execution plan, thống kê optimizer, `DBMS_XPLAN` với runtime stats phù hợp | Cách thu thập và hiển thị actual rows tùy cấu hình |
| SQLite | `EXPLAIN QUERY PLAN`, `ANALYZE` | Không có cùng định dạng rows/loops như PostgreSQL |

### 23.1. Parameter-sensitive plans

Một truy vấn theo `customer_id` có thể chạy rất nhanh cho khách chỉ có 1 đơn nhưng rất chậm cho khách có 400.000 đơn.

Khi DBMS tái sử dụng một kế hoạch được tạo cho bộ tham số có phân bố khác, lựa chọn join/scan có thể không phù hợp. SQL Server thường thảo luận hiện tượng này trong ngữ cảnh parameter sniffing; PostgreSQL cũng có các lựa chọn generic/custom plan cho prepared statements trong những tình huống tương ứng.

Giải pháp phụ thuộc engine/phiên bản, có thể liên quan thống kê, SQL, chiến lược kế hoạch và cách phân chia workload. Không có một mẹo cưỡng ép kế hoạch dùng chung cho mọi hệ.

### 23.2. Kết quả logic không thay đổi theo engine

Nếu đơn 101 có **2 payments và 3 shipments**, phép nối đòi mọi kết hợp sẽ tạo **6 hàng** dù chạy PostgreSQL, MySQL hay SQL Server. Các optimizer khác nhau về chi phí, không được tự bỏ các hàng hợp lệ để “tối ưu”.

## 24. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi SQL mặc định loại trùng | Không hiểu hàng cha lặp khi JOIN | Nắm bag semantics và grain |
| Chỉ nhìn số hàng đầu ra cuối | Bỏ qua trung gian rất lớn trước GROUP BY | Đọc row flow trên plan |
| Thiếu điều kiện JOIN | CROSS JOIN ngoài ý muốn | Viết đầy đủ điều kiện |
| Chỉ JOIN theo một phần khóa ghép | Nhân chéo tenant/source | Nối đúng business key |
| Nối nhiều bảng con rồi SUM thuộc tính cha | Tổng tiền tăng giả | Tổng hợp con trước, giữ grain cha |
| `SUM(DISTINCT order_total)` để sửa lặp | Gộp cả hai đơn có giá trị tiền bằng nhau | Dedupe theo ID, không theo amount |
| `COUNT(*)` sau LEFT JOIN để đếm con | Đếm cả hàng mở rộng NULL | `COUNT(child_pk)` |
| Dùng `COUNT(DISTINCT)` cho mọi báo cáo | Join lớn vẫn đã xảy ra | EXISTS hoặc bỏ JOIN dư |
| Lấy một bản ghi con tùy tiện | Mất payment/shipment hợp lệ | Chọn theo quy tắc rõ ràng |
| `LIMIT 1` cuối query để lấy một con/cha | Chỉ lấy một hàng của toàn bộ query | LATERAL hoặc ROW_NUMBER theo cha |
| Hiểu `LEFT JOIN` như `INNER JOIN` | Đếm sai hàng không khớp | Tính max(count,1) cho hàng cha |
| Lọc cột phía phải ở WHERE khi muốn giữ cha | Hàng NULL bị loại | Lọc trong ON hoặc CTE đúng nghĩa |
| Cho rằng index làm JOIN trả ít hàng hơn | Số cặp khớp vẫn như cũ | Sửa grain/điều kiện, index chỉ cải thiện truy cập |
| Thống kê cũ sau bulk load | Cardinality estimate sai | ANALYZE và kiểm tra planner stats |
| Tin extended statistics sửa mọi JOIN | Không mô hình hóa mọi tương quan liên bảng | Phân tích giới hạn và dữ liệu |
| Bỏ qua khóa nóng | Tích cặp nhiều–nhiều cực lớn | MCV/skew analysis, chỉnh nghĩa query nếu có thể |
| Đọc `actual rows` mà bỏ `loops` | Đánh giá thấp inner scan work | Xem per-loop × loops |
| Cộng `actual rows` của mọi node | Đếm cùng dữ liệu qua nhiều tầng | Theo dõi dòng dữ liệu từng node |
| Tăng `work_mem` không hạn chế | Tổng bộ nhớ có thể vượt dự kiến | Giảm trung gian trước, tune có đo |
| `EXPLAIN ANALYZE` DML trên production | Câu lệnh thật sự được thực thi | EXPLAIN dự đoán hoặc môi trường an toàn |
| JOIN dimension lịch sử chỉ theo ID | Một fact khớp nhiều phiên bản | Điều kiện hiệu lực và kiểm tra dữ liệu chồng lấn |
| Window SUM trên tập đã nhân | Tổng lũy kế/tổng partition cũng sai | Sửa grain trước khi window |

## 25. Bài tập thực hành có đáp án

Các câu dùng dữ liệu `demo_cardinality_331` sau phần 3 trừ khi nêu ví dụ giả định. Nên dự đoán kết quả bằng tay rồi chạy SQL.

### Bài 1 — Số hàng nguồn

Có bao nhiêu khách, đơn, dòng đơn, thanh toán và vận chuyển?

**Đáp án:** 4 customers, 6 orders, 11 order_items, 9 payments, 8 shipments.

### Bài 2 — INNER JOIN khách và đơn

```sql
SELECT COUNT(*)
FROM demo_cardinality_331.customers c
JOIN demo_cardinality_331.orders o
  ON o.customer_id = c.customer_id;
```

**Đáp án:** **6 hàng**, vì mọi đơn đều có khách. Khách Dung không có đơn nên không xuất hiện.

### Bài 3 — LEFT JOIN khách và đơn

Đổi thành `LEFT JOIN` trả bao nhiêu hàng?

**Đáp án:** **7 hàng**: sáu hàng đơn và một hàng mở rộng cho Dung.

### Bài 4 — COUNT(*) và COUNT(order_id)

```sql
SELECT COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS order_rows
FROM demo_cardinality_331.customers c
LEFT JOIN demo_cardinality_331.orders o
  ON o.customer_id = c.customer_id;
```

**Đáp án:** `joined_rows=7`, `order_rows=6`. `COUNT(*)` đếm cả hàng khách Dung không khớp đơn.

### Bài 5 — Đơn 101 sinh bao nhiêu tổ hợp?

Đơn 101 có 2 payments và 3 shipments. Khi nối cả hai bảng con độc lập theo order_id, số hàng cho đơn này?

**Đáp án:** \(2\times3=6\).

### Bài 6 — LEFT JOIN hai bảng con

```sql
SELECT COUNT(*)
FROM demo_cardinality_331.orders o
LEFT JOIN demo_cardinality_331.payments p
  ON p.order_id = o.order_id
LEFT JOIN demo_cardinality_331.shipments s
  ON s.order_id = o.order_id;
```

**Đáp án:** **16 hàng**, theo từng đơn 6+1+1+4+1+3.

### Bài 7 — Đơn 103 không có payment

Đơn 103 có 0 payment và 1 shipment. Vì sao vẫn có một hàng sau hai LEFT JOIN?

**Đáp án:** LEFT JOIN tạo hàng `NULL` cho payment không khớp. `max(0,1)×max(1,1)=1`.

### Bài 8 — Đơn 105 không có shipment

Đơn 105 có 1 payment và 0 shipment. Số hàng?

**Đáp án:** `max(1,1)×max(0,1)=1`, shipment là `NULL`.

### Bài 9 — INNER JOIN cả payments và shipments

```sql
SELECT COUNT(*)
FROM demo_cardinality_331.orders o
JOIN demo_cardinality_331.payments p
  ON p.order_id = o.order_id
JOIN demo_cardinality_331.shipments s
  ON s.order_id = o.order_id;
```

**Đáp án:** **14 hàng**, từ đơn 101 (6), 102 (1), 104 (4), 106 (3).

### Bài 10 — Tổng đơn sau JOIN sai thế nào?

Nếu dùng `SUM(o.order_total)` sau hai LEFT JOIN, kết quả bao nhiêu?

**Đáp án:** **1480**, trong khi tổng đúng từ bảng orders chỉ **430**.

### Bài 11 — SUM(DISTINCT) có sửa lỗi không?

`SUM(DISTINCT o.order_total)` trả bao nhiêu?

**Đáp án:** **340**, vì hai đơn 104 và 106 đều có tổng 90 nhưng `DISTINCT` chỉ tính 90 một lần. Tổng đúng 430.

### Bài 12 — Tổng thanh toán bị nhân

Sau hai LEFT JOIN, `SUM(p.paid_amount)` là bao nhiêu? Tổng payment gốc là bao nhiêu?

**Đáp án:** Tổng sau JOIN **740**; tổng payment gốc **410**.

### Bài 13 — COUNT shipment bị nhân

`COUNT(s.shipment_id)` sau hai LEFT JOIN là bao nhiêu? `COUNT(DISTINCT s.shipment_id)`?

**Đáp án:** Lần lượt **15** và **8**.

### Bài 14 — Tổng theo từng khách

Sau khi tổng hợp payments đúng grain rồi nối orders, các kết quả là gì?

| Khách | Số đơn | Tổng đơn | Đã thanh toán |
| --- | ---: | ---: | ---: |
| An | 3 | 190 | 170 |
| Binh | 1 | 90 | 90 |
| Chi | 2 | 150 | 150 |
| Dung | 0 | 0 | 0 |

**Đáp án:** Tổng số đơn 6, tổng `order_total` 430 và tổng thanh toán 410. Có thể dùng mẫu truy vấn ở phần 7.2.

### Bài 15 — CROSS JOIN

4 customers × 6 orders tạo bao nhiêu hàng nếu không có điều kiện định danh?

**Đáp án:** **24 hàng**.

### Bài 16 — EXISTS thay JOIN

Khách nào có ít nhất một đơn `paid`?

**Đáp án:** **An, Binh, Chi** (3 khách). Nếu dùng JOIN thường không DISTINCT, có 5 hàng do An và Chi có hai đơn paid mỗi người.

### Bài 17 — NOT EXISTS tìm khách không có đơn

```sql
SELECT c.customer_id, c.customer_name
FROM demo_cardinality_331.customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_cardinality_331.orders o
    WHERE o.customer_id = c.customer_id
);
```

**Đáp án:** **Dung**.

### Bài 18 — Chọn shipment mới nhất

`LEFT JOIN LATERAL` với `ORDER BY shipped_on DESC, shipment_id DESC LIMIT 1` trả bao nhiêu hàng? Đơn 101 chọn shipment nào?

**Đáp án:** **6 hàng**; đơn 101 chọn shipment **603**, đơn 105 không có shipment nên cột phía phải là `NULL`.

### Bài 19 — SELECT chỉ đơn paid trong phạm vi

Lọc đơn `status='paid'`, ngày từ 01/06 đến trước 03/06 rồi LEFT JOIN payment. Có bao nhiêu đơn và hàng kết quả?

**Đáp án:** Đơn 101, 102, 104 (3 đơn), với số payment 2,1,2 nên JOIN trả **5 hàng**.

### Bài 20 — Selectivity

Một bảng có 1.000.000 hàng và selectivity điều kiện là 2%. Ước lượng hàng qua filter?

**Đáp án:** Khoảng **20.000 hàng** nếu mô hình selectivity phù hợp.

### Bài 21 — NDV và equi-join

A có 6 hàng, 6 giá trị key. B có 9 hàng, 5 giá trị key. Công thức gần đúng \( |A||B|/\max(NDV_A,NDV_B)\) cho bao nhiêu?

**Đáp án:** \(6\times9/6=9\) hàng; đây là xấp xỉ, không phải bảo đảm tổng quát.

### Bài 22 — Khóa HOT

Hai bảng đều có 9.000 hàng `HOT`. Chỉ các cặp `HOT` tạo bao nhiêu hàng?

**Đáp án:** **81.000.000 cặp**.

### Bài 23 — Actual rows và loops

Node có `actual rows=3 loops=2000`. Tổng hàng phát ra gần đúng?

**Đáp án:** Khoảng **6.000 hàng**; giá trị per-loop có thể đã được làm tròn.

### Bài 24 — Ước lượng sai

Node có `rows=100` nhưng `actual rows=50.000 loops=1`. Đánh giá thấp bao nhiêu lần?

**Đáp án:** **500 lần**.

### Bài 25 — ANALYZE có sửa số tổ hợp không?

Đơn 101 vẫn có 2 payment và 3 shipment. Sau `ANALYZE`, JOIN vẫn tạo sáu hàng cho đơn 101 chứ?

**Đáp án:** Đúng. Thống kê giúp optimizer ước lượng, không thay đổi ngữ nghĩa các cặp khớp.

### Bài 26 — Index có làm mất fanout không?

Tạo index cho `payments(order_id)` và `shipments(order_id)`. JOIN hai bảng con có tự giảm từ 16 xuống 6 hàng?

**Đáp án:** Không. Index giúp đường truy cập, không tự tổng hợp nhiều hàng con về một hàng/cha.

### Bài 27 — COUNT DISTINCT ở cuối

Query tạo 10 triệu hàng trung gian rồi đếm 10 nghìn ID bằng `COUNT(DISTINCT id)`. Có thể coi query chỉ phải xử lý 10 nghìn hàng không?

**Đáp án:** Không. Các JOIN và bước DISTINCT vẫn có thể phải xử lý rất nhiều hàng; nên xem có thể dùng EXISTS, bỏ JOIN dư hoặc tổng hợp trước không.

### Bài 28 — Row width

Hai kế hoạch đều có 1 triệu hàng trung gian nhưng `width` lần lượt 16 và 512 byte. Chi phí sort/hash có chắc tương đương không?

**Đáp án:** Không. Độ rộng hàng ảnh hưởng bộ nhớ và I/O; phải xét cả rows, width, thuật toán và tài nguyên.

### Bài 29 — WHERE và ON sau LEFT JOIN

Muốn giữ mọi đơn kể cả đơn không có payment >=50, điều kiện `p.paid_amount >= 50` đặt ở đâu?

**Đáp án:** Trong `ON` của LEFT JOIN. Nếu đặt trong `WHERE`, đơn không có payment đạt điều kiện bị loại.

### Bài 30 — Điều tra plan nhiều vòng lặp

Plan có outer 100.000 hàng, inner index scan `actual rows=20 loops=100000` và HashAggregate dùng disk. Hướng điều tra?

**Đáp án:** Ước lượng có khoảng **2 triệu hàng phát ra từ inner scans**. Xác định grain, khóa/điều kiện JOIN, bội số từng khóa, estimated–actual, thống kê, cần thiết của JOIN, cơ hội preaggregate hoặc EXISTS; sau đó mới cân nhắc index, memory và thuật toán theo đo đạc.

## 26. Checklist trước khi tối ưu một SQL có nhiều JOIN

1. **Mỗi hàng đầu ra có grain gì?** Khách, đơn, payment, shipment hay cặp sự kiện?
2. **Quan hệ giữa các bảng là 1:1, 1:N hay N:M?** Đừng đoán từ tên cột.
3. **Mọi điều kiện JOIN đã dùng đủ khóa định danh chưa?** Bao gồm tenant/source và hiệu lực theo thời gian nếu cần.
4. **Bảng bên phải có unique trên khóa dùng JOIN không?** Nếu không, có thể có nhiều hàng khớp.
5. **Có hai hoặc nhiều bảng con độc lập của cùng một cha không?** Fanout có thể nhân nhau.
6. **Có CROSS JOIN, OR, range join, UNNEST, JSON expansion hoặc recursive CTE không?** Ước lượng số hàng mở rộng.
7. **Số hàng tăng tại bước nào?** Xem từ scan đến từng JOIN, không chỉ output cuối.
8. **Có tính SUM trên cột cha sau JOIN 1:N không?** Có thể cộng lặp.
9. **COUNT(*) sau LEFT JOIN có đếm hàng NULL mở rộng không?** Dùng khóa PK bên phải nếu cần đếm hàng thật.
10. **DISTINCT có đang che vấn đề grain không?** `SUM(DISTINCT amount)` không thay dedup theo ID.
11. **Chỉ cần biết có hàng hay cần mọi hàng chi tiết?** `EXISTS`/`NOT EXISTS` có thể phù hợp hơn JOIN.
12. **Có thể preaggregate bảng con theo khóa cha trước khi nối không?**
13. **Nếu chỉ chọn một hàng con, đã có tiêu chí mới nhất/ưu tiên và tie-breaker chưa?**
14. **Điều kiện `WHERE` có làm sai OUTER JOIN không?** Xác định rõ lọc ở `ON` hay `WHERE`.
15. **Estimated rows và actual rows lệch bao nhiêu?** Đọc cả `loops`.
16. **Khóa nóng hoặc dữ liệu lệch có làm tích cặp lớn không?**
17. **Các điều kiện lọc có tương quan không?** Thống kê một cột có đủ không?
18. **Thống kê có còn mới sau bulk load không?** Cân nhắc `ANALYZE`.
19. **Extended statistics có áp dụng đúng loại điều kiện không?** Không giả định chữa mọi JOIN.
20. **Index có hỗ trợ đường lọc và JOIN không?** Đo thực tế; index không sửa ngữ nghĩa.
21. **Hash/sort có dùng temp I/O không?** Xem Buffers, Batches và Sort Method.
22. **Width của hàng có quá lớn không?** Chỉ mang những cột cần thiết qua các bước nặng.
23. **Có nested loop inner scan quá nhiều lần không?** Nhân rows per loop với loops.
24. **Đã kiểm tra tổng tiền, số ID và số nhóm sau khi sửa SQL chưa?**
25. **Đã phân biệt công cụ EXPLAIN dự đoán và ANALYZE thật chưa?** Tránh chạy DML đo plan trên production.
26. **Đã đo trên dữ liệu đại diện và đúng DBMS/phiên bản chưa?**

## 27. Dọn bộ dữ liệu thử nghiệm

Nếu muốn xóa các bảng mẫu, chỉ thực hiện trên **database sandbox** đã tạo schema cho bài:

```sql
DROP SCHEMA demo_cardinality_331 CASCADE;
```

`CASCADE` có thể xóa toàn bộ đối tượng phụ thuộc trong schema. Chỉ dùng khi đã xác nhận schema này **dành riêng cho bài thực hành**, không chứa dữ liệu của người khác. Nếu muốn chạy lại bài, có thể dùng một database/sandbox mới thay vì xóa schema đang được chia sẻ.

## 28. Tổng kết

**Bội số hàng** mô tả bao nhiêu kết hợp được tạo ra theo từng khóa. Một JOIN 1:N có thể lặp hàng cha, hai JOIN 1:N độc lập có thể tạo tích bội số, và một kết quả chỉ có vài hàng sau `GROUP BY` vẫn có thể từng đi qua hàng triệu hàng trung gian.

**Ước lượng số hàng** giúp planner chọn thứ tự nối, thuật toán và chi phí bộ nhớ trước khi thực thi; `EXPLAIN (ANALYZE)` cho thấy hàng thực tế đã đi qua các bước. Thống kê cũ, khóa nóng, cột tương quan và điều kiện JOIN phức tạp có thể làm estimated rows lệch xa actual rows.

Để câu SQL **đúng và nhanh**, hãy xác định grain, kiểm tra khóa và bội số, loại JOIN không cần thiết, dùng `EXISTS` cho câu hỏi tồn tại, **tổng hợp bảng con về đúng grain trước khi JOIN**, và quan sát `actual rows` cùng `loops`. Index và thống kê giúp thực thi tốt hơn, nhưng **không thể thay thế một phép JOIN đúng nghĩa nghiệp vụ**.



