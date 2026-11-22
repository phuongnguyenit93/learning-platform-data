# Kiểm tra bội số hàng và tránh cộng lặp số liệu

Khi kết nối nhiều bảng bằng `JOIN`, một hàng ở bảng bên trái có thể khớp **không hàng, một hàng hoặc nhiều hàng** ở bảng bên phải. Đây là hành vi tự nhiên của quan hệ một-nhiều và nhiều-nhiều trong SQL. Tuy nhiên, nếu tiếp tục `COUNT`, `SUM` hoặc tính các chỉ số trên kết quả JOIN mà không biết **mỗi hàng kết quả đang đại diện cho điều gì**, báo cáo có thể đếm trùng đơn hàng, cộng doanh thu nhiều lần hoặc đánh giá sai số lượng thực thể.

Ví dụ: một đơn hàng có hai dòng sản phẩm và hai bản ghi thanh toán. Kết nối đồng thời bảng đơn với bảng dòng sản phẩm và bảng thanh toán theo `order_id` có thể tạo **4 hàng**, vì mỗi dòng sản phẩm khớp với mỗi bản ghi thanh toán. Nếu cộng `item_amount` trực tiếp trên 4 hàng đó, số tiền sản phẩm sẽ bị cộng **hai lần**; nếu cộng `payment_amount`, số tiền thanh toán lại bị cộng **hai lần**. Truy vấn có thể chạy thành công, không báo lỗi, nhưng KPI tài chính sai.

Để ngăn lỗi, cần hiểu **bội số hàng (row multiplicity)**, **độ hạt dữ liệu (grain)**, **fanout của JOIN**, khóa duy nhất, quan hệ giữa các bảng con, và cách kiểm tra kết quả **trước khi tổng hợp**. Các kỹ thuật quan trọng là tổng hợp trước theo đúng khóa, tách các nhánh dữ liệu một-nhiều, dùng `EXISTS` khi chỉ cần sự tồn tại, đặt `COUNT(DISTINCT ...)` đúng ngữ nghĩa và tuyệt đối không coi `SUM(DISTINCT amount)` là cách sửa mọi lỗi cộng lặp.

Bài học thuộc chủ đề **Database SQL**, chương **Kết nối bảng**. Các ví dụ thực hành chính dùng **PostgreSQL** với bảng tạm tự chứa; nguyên lý bội số hàng áp dụng cho các DBMS quan hệ nói chung. Những cú pháp riêng như `FILTER` và `LATERAL` sẽ được ghi rõ nơi sử dụng.

## 1. Trước JOIN, hãy xác định “một hàng” nghĩa là gì

Giả sử hệ thống bán hàng có các bảng:

| Bảng | Mỗi hàng đại diện cho | Khóa định danh | Quan hệ |
| --- | --- | --- | --- |
| `customers` | Một khách hàng | `customer_id` | Một khách có thể có nhiều đơn |
| `orders` | Một đơn hàng | `order_id` | Một đơn thuộc một khách |
| `order_items` | Một dòng sản phẩm trong đơn | `item_id` | Một đơn có nhiều dòng |
| `payments` | Một lần ghi nhận/đề nghị thanh toán | `payment_id` | Một đơn có thể có nhiều lần thanh toán |

**Độ hạt (grain)** của bảng là câu trả lời cho câu hỏi: **một hàng mô tả một đối tượng/sự kiện ở mức chi tiết nào?**

- Ở `orders`, một hàng là **một đơn**.
- Ở `order_items`, một hàng là **một dòng sản phẩm**, không phải một đơn.
- Ở `payments`, một hàng là **một bản ghi thanh toán**, không phải một đơn và cũng không phải một dòng sản phẩm.

Khi `JOIN orders` với `order_items`, độ hạt của kết quả thường trở thành **một hàng cho mỗi dòng sản phẩm gắn với đơn**. Khi tiếp tục nối `payments` độc lập theo cùng `order_id`, kết quả có thể trở thành **một hàng cho mỗi cặp `(item, payment)`**. Đây là nguồn gốc của việc nhân số liệu.

### 1.1. Khóa chính của bảng không làm JOIN tự một-một

`orders.order_id` là khóa chính, nên một `order_id` chỉ có một hàng trong `orders`. Nhưng cột `order_items.order_id` là **khóa ngoại**; nhiều dòng sản phẩm hợp lệ có thể cùng tham chiếu một đơn.

```text
orders
  101
    |
    +------ order_items 1001
    |
    +------ order_items 1002
```

`JOIN` theo `order_id` tạo hai hàng kết quả cho đơn 101. Không có hàng nào sai hoặc trùng dữ liệu nguồn; đó là bội số đúng theo mô hình một-nhiều. Lỗi chỉ xuất hiện khi ta **quên rằng đơn 101 giờ được đại diện bởi hai hàng trong tập kết quả** rồi tính một chỉ số vốn phải tính một lần trên mỗi đơn.

### 1.2. Bội số là tính chất của điều kiện JOIN

Hai bảng có thể có khóa chính hoàn toàn hợp lệ mà JOIN vẫn nhân hàng, nếu **cột hoặc tổ hợp cột được dùng để JOIN không duy nhất ở phía khớp**. Vì thế, khi xem một câu JOIN, hãy tự hỏi:

1. Mỗi hàng ở bảng trái có thể khớp **bao nhiêu hàng ở bảng phải**?
2. Cột JOIN có thật sự là khóa duy nhất ở phía được kỳ vọng chỉ có một hàng không?
3. Có điều kiện JOIN nào bị thiếu, ví dụ tenant, phiên bản hiệu lực hoặc loại sự kiện?
4. Khi ghép nhiều bảng con, chúng có quan hệ **với nhau** hay chỉ cùng thuộc một bảng cha?
5. Sau JOIN, một hàng đại diện cho **đơn**, **dòng hàng**, **thanh toán** hay **cặp dòng hàng–thanh toán**?

## 2. Tạo dữ liệu PostgreSQL có thể kiểm chứng bằng mắt

Tạo các bảng tạm trong cùng một phiên kết nối PostgreSQL:

```sql
CREATE TEMP TABLE demo_join_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TEMP TABLE demo_join_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_join_customers(customer_id),
    order_status TEXT NOT NULL,
    created_on DATE NOT NULL
);

CREATE TEMP TABLE demo_join_order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES demo_join_orders(order_id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);

CREATE TEMP TABLE demo_join_payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES demo_join_orders(order_id),
    payment_status TEXT NOT NULL,
    payment_amount NUMERIC(12, 2) NOT NULL
        CHECK (payment_amount >= 0),
    recorded_at TIMESTAMPTZ NOT NULL
);

INSERT INTO demo_join_customers (customer_id, customer_name)
VALUES (1, 'An'), (2, 'Binh'), (3, 'Chi');

INSERT INTO demo_join_orders
    (order_id, customer_id, order_status, created_on)
VALUES
    (101, 1, 'PAID',    DATE '2026-09-01'),
    (102, 1, 'PENDING', DATE '2026-09-02'),
    (103, 2, 'PAID',    DATE '2026-09-03'),
    (104, 2, 'DRAFT',   DATE '2026-09-04');

INSERT INTO demo_join_order_items
    (item_id, order_id, sku, quantity, unit_price)
VALUES
    (1001, 101, 'PEN',     1, 25.00), -- 25
    (1002, 101, 'NOTE',    5,  5.00), -- 25
    (1003, 102, 'BAG',     1, 40.00), -- 40
    (1004, 103, 'BOOK',    3, 15.00); -- 45

INSERT INTO demo_join_payments
    (payment_id, order_id, payment_status, payment_amount, recorded_at)
VALUES
    (501, 101, 'COMPLETED', 30.00,
        TIMESTAMPTZ '2026-09-01 10:00:00+07'),
    (502, 101, 'COMPLETED', 20.00,
        TIMESTAMPTZ '2026-09-01 11:00:00+07'),
    (503, 102, 'PENDING',   10.00,
        TIMESTAMPTZ '2026-09-02 12:00:00+07'),
    (504, 103, 'COMPLETED', 45.00,
        TIMESTAMPTZ '2026-09-03 13:00:00+07');
```

Mô hình có:

- **3 khách**: An có đơn 101–102; Binh có đơn 103–104; Chi chưa có đơn.
- **4 đơn**: đơn 101 có hai dòng hàng và hai thanh toán hoàn tất; đơn 102 có một dòng và một đề nghị thanh toán còn PENDING; đơn 103 có một dòng và một thanh toán hoàn tất; đơn 104 chưa có dòng hàng hoặc thanh toán.
- **4 dòng hàng** và **4 bản ghi thanh toán**, với trạng thái thanh toán tách riêng khỏi trạng thái đơn.
- Hai dòng sản phẩm của đơn 101 **cùng có thành tiền 25**, dù là hai dòng hợp lệ khác nhau. Đây là trường hợp dùng để phát hiện bẫy `SUM(DISTINCT ...)`.

### 2.1. Các số đúng theo từng bảng nguồn

Thành tiền một dòng:

```sql
quantity * unit_price
```

| order_id | Các dòng hàng | Tổng thành tiền dòng hàng | Thanh toán COMPLETED | Tổng tiền đã hoàn tất |
| ---: | --- | ---: | --- | ---: |
| 101 | 25 + 25 | **50.00** | 30 + 20 | **50.00** |
| 102 | 40 | **40.00** | Không; có 10 PENDING | **0.00** |
| 103 | 45 | **45.00** | 45 | **45.00** |
| 104 | Chưa có dòng | **0.00** theo quy ước tổng không phát sinh | Không có | **0.00** |

Tổng thành tiền sản phẩm ở các dòng thật: **50 + 40 + 45 = 135.00**. Tổng thanh toán `COMPLETED`: **50 + 45 = 95.00**. Hai chỉ số này **không bắt buộc phải bằng nhau** vì có đơn chưa thanh toán và có thể tồn tại hoàn tiền, công nợ hoặc dòng chưa định giá tùy hệ thống thực.

Các câu kiểm tra trực tiếp trên nguồn:

```sql
SELECT SUM(quantity * unit_price) AS actual_item_total
FROM demo_join_order_items;
-- 135.00

SELECT SUM(payment_amount) AS actual_completed_payment_total
FROM demo_join_payments
WHERE payment_status = 'COMPLETED';
-- 95.00

SELECT
    (SELECT COUNT(*) FROM demo_join_orders) AS order_rows,
    (SELECT COUNT(*) FROM demo_join_order_items) AS item_rows,
    (SELECT COUNT(*) FROM demo_join_payments) AS payment_rows;
-- 4, 4, 4
```

Đây là các mốc đối chiếu trên **đúng bảng nguồn của từng chỉ số**. Trong bài toán thật, trước khi tổng hợp qua một JOIN phức tạp, cần biết mốc độc lập tương đương để phát hiện trường hợp kết quả bị nhân.

## 3. JOIN một-nhiều: vì sao một đơn xuất hiện nhiều lần?

Nối đơn với dòng sản phẩm:

```sql
SELECT
    o.order_id,
    i.item_id,
    i.quantity,
    i.unit_price,
    i.quantity * i.unit_price AS line_amount
FROM demo_join_orders AS o
JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
```

Kết quả:

| order_id | item_id | line_amount |
| ---: | ---: | ---: |
| 101 | 1001 | 25.00 |
| 101 | 1002 | 25.00 |
| 102 | 1003 | 40.00 |
| 103 | 1004 | 45.00 |

Có **4 hàng** kết quả theo đúng 4 dòng sản phẩm. Đơn 101 xuất hiện hai lần do có hai dòng. Đơn 104 không xuất hiện vì `INNER JOIN` chỉ giữ đơn có ít nhất một dòng sản phẩm.

### 3.1. Mỗi hàng của bảng cha bị lặp là bình thường

Nếu chọn thêm `o.order_status` hoặc `o.created_on`, chúng cũng lặp lại trên từng dòng sản phẩm:

```sql
SELECT o.order_id, o.order_status, i.item_id
FROM demo_join_orders AS o
JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id;
```

Đối với đơn 101, `order_status = 'PAID'` được lặp hai lần. Không thể cộng một trường **ở cấp đơn** trên kết quả này như thể mỗi hàng vẫn là một đơn. Cần xác định độ hạt trước khi làm `COUNT(*)`, `SUM(...)` hoặc tính tỷ lệ.

### 3.2. LEFT JOIN giữ đơn không có dòng, nhưng không loại bội số

```sql
SELECT
    o.order_id,
    i.item_id
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
```

Đơn 104 được giữ với `item_id = NULL`, nhưng đơn 101 vẫn có hai hàng. LEFT JOIN **bổ sung hàng cho trường hợp không có khớp**, không biến quan hệ một-nhiều thành một-một.

Vì vậy, đổi `JOIN` sang `LEFT JOIN` **không sửa** hiện tượng nhân số liệu; nó chỉ thay đổi quy tắc giữ hàng không khớp.

## 4. Fanout: hai bảng con độc lập nhân số hàng như thế nào?

Bây giờ nối **cả** dòng hàng và thanh toán:

```sql
SELECT
    o.order_id,
    i.item_id,
    i.quantity * i.unit_price AS line_amount,
    p.payment_id,
    p.payment_status,
    p.payment_amount
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id, i.item_id, p.payment_id;
```

Các hàng của đơn 101:

| order_id | item_id | line_amount | payment_id | payment_amount |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1001 | 25.00 | 501 | 30.00 |
| 101 | 1001 | 25.00 | 502 | 20.00 |
| 101 | 1002 | 25.00 | 501 | 30.00 |
| 101 | 1002 | 25.00 | 502 | 20.00 |

**Hai dòng hàng × hai thanh toán = bốn hàng JOIN.** Không phải đơn 101 đã bán 4 dòng hoặc thu 100.00; SQL chỉ đang biểu diễn **mọi cặp khớp giữa hai nhánh con độc lập theo cùng order_id**.

```text
                  orders: 101
                  /         \
                 /           \
       order_items            payments
       item 1001              payment 501
       item 1002              payment 502
                 \           /
                  \         /
            Kết quả hai LEFT JOIN
            (1001, 501)
            (1001, 502)
            (1002, 501)
            (1002, 502)
```

Trong trường hợp **hai nhánh con độc lập được LEFT JOIN theo cùng khóa cha**, nếu một đơn có `m` dòng và `n` thanh toán, số hàng JOIN cho riêng đơn đó thường là:

\[
\max(m,1)\times\max(n,1)
\]

Số `1` xuất hiện ở trường hợp không có bản ghi con vì LEFT JOIN giữ một hàng bù có các cột phía con là NULL. Công thức này giả định không có điều kiện ghép chéo hoặc điều kiện lọc khác làm thay đổi tập khớp và mỗi bản ghi con khớp đúng một đơn. Với `INNER JOIN` cả hai nhánh trong cùng mô hình đơn giản, số cặp khớp là `m × n`, và nếu một nhánh có 0 thì đơn biến mất khỏi kết quả.

### 4.1. Bội số của từng đơn trong bộ dữ liệu mẫu

| order_id | Số dòng hàng thật `m` | Số thanh toán thật `n` | Hàng sau hai LEFT JOIN |
| ---: | ---: | ---: | ---: |
| 101 | 2 | 2 | **4** |
| 102 | 1 | 1 | **1** |
| 103 | 1 | 1 | **1** |
| 104 | 0 | 0 | **1** |
| **Tổng** | **4** | **4** | **7** |

Kết quả có 7 hàng dù bảng orders chỉ có 4, bảng items có 4 và bảng payments có 4. **Số hàng kết quả không bằng một trong các số hàng nguồn**, vì độ hạt đã thay đổi.

### 4.2. Truy vấn đếm để nhìn thấy fanout

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(i.item_id) AS item_mentions_after_join,
    COUNT(p.payment_id) AS payment_mentions_after_join,
    COUNT(DISTINCT i.item_id) AS distinct_items,
    COUNT(DISTINCT p.payment_id) AS distinct_payments
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Kết quả có ý nghĩa:

| order_id | joined_rows | item_mentions_after_join | payment_mentions_after_join | distinct_items | distinct_payments |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 4 | 4 | 4 | 2 | 2 |
| 102 | 1 | 1 | 1 | 1 | 1 |
| 103 | 1 | 1 | 1 | 1 | 1 |
| 104 | 1 | 0 | 0 | 0 | 0 |

`COUNT(i.item_id)` đếm **số lần ID dòng hàng xuất hiện sau JOIN**, không phải số dòng hàng gốc nếu dòng đó bị ghép với nhiều thanh toán. `COUNT(DISTINCT i.item_id)` cho số dòng hàng **duy nhất**, ở đây là 2 cho đơn 101. Tương tự với payment_id.

`COUNT(*)` của đơn 104 bằng 1 vì một hàng bù vẫn tồn tại; `COUNT(i.item_id)` và `COUNT(p.payment_id)` bằng 0 vì cột từ bảng con là NULL.

## 5. Lỗi cộng lặp: SUM hợp lệ cú pháp nhưng sai nghĩa

Một câu báo cáo tưởng như đúng:

```sql
SELECT
    o.order_id,
    SUM(i.quantity * i.unit_price) AS item_total,
    SUM(
        CASE
            WHEN p.payment_status = 'COMPLETED'
            THEN p.payment_amount
            ELSE 0
        END
    ) AS completed_payment_total
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Hai phép `SUM` chạy **sau khi JOIN**, trên các hàng đã nhân. Với đơn 101:

```text
item_total sai:
25 + 25 + 25 + 25 = 100
Đúng theo hai item thật:
25 + 25 = 50

completed_payment_total sai:
30 + 20 + 30 + 20 = 100
Đúng theo hai payment thật:
30 + 20 = 50
```

| order_id | item_total tính trên JOIN | item_total đúng | completed_payment_total tính trên JOIN | completed_payment_total đúng |
| ---: | ---: | ---: | ---: | ---: |
| 101 | **100.00** | 50.00 | **100.00** | 50.00 |
| 102 | 40.00 | 40.00 | 0.00 | 0.00 |
| 103 | 45.00 | 45.00 | 45.00 | 45.00 |
| 104 | NULL | 0.00 theo quy ước | 0.00 | 0.00 |

Tổng item tính trực tiếp trên JOIN là **185.00**, so với **135.00** từ item gốc. Tổng thanh toán COMPLETED tính trực tiếp trên JOIN là **145.00**, so với **95.00** từ payment gốc.

**Hàm `SUM` không bị lỗi**; nó cộng đúng các hàng đã nhận. Lỗi nằm ở **độ hạt của đầu vào**: mỗi dòng hàng và mỗi thanh toán bị nhân khi nối hai nhánh độc lập. Đổi `GROUP BY` sang `GROUP BY o.order_id, o.customer_id` cũng không sửa được nếu phép SUM vẫn cộng trên những hàng nhân bản.

### 5.1. COUNT cũng có thể sai

```sql
SELECT
    o.order_id,
    COUNT(*) AS row_count,
    COUNT(i.item_id) AS item_count,
    COUNT(p.payment_id) AS payment_count
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Với đơn 101, cả ba phép COUNT đều trả 4, dù chỉ có 2 item và 2 payment thật. Với đơn 104, `COUNT(*)` bằng 1 dù **không có item và payment**. Khi đếm thực thể con, dùng `COUNT(child_primary_key)` hoặc `COUNT(DISTINCT child_primary_key)` tùy độ hạt nguồn và số nhánh JOIN.

### 5.2. CASE hoặc FILTER không tự loại fanout

```sql
-- PostgreSQL: cú pháp đúng nhưng số tiền vẫn bị lặp.
SELECT
    o.order_id,
    SUM(p.payment_amount)
        FILTER (WHERE p.payment_status = 'COMPLETED') AS completed_amount
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id;
```

FILTER chỉ giữ những hàng JOIN có payment COMPLETED. Nó **không biết hai lần xuất hiện của payment 501 đến từ hai item khác nhau**. Đổi FILTER sang `SUM(CASE WHEN ... THEN payment_amount END)` cũng không khôi phục được bội số gốc.

**Đúng điều kiện tổng hợp** và **đúng độ hạt đầu vào** là hai yêu cầu riêng; cả hai đều cần được thỏa.

## 6. Vì sao `SUM(DISTINCT amount)` không phải thuốc chữa?

Một phản ứng thường gặp trước dữ liệu bị nhân:

```sql
SELECT
    o.order_id,
    SUM(DISTINCT i.quantity * i.unit_price) AS item_total
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Với đơn 101, các giá trị `line_amount` sau JOIN là **25, 25, 25, 25**. `SUM(DISTINCT ...)` chỉ giữ **một giá trị số 25**, nên trả **25.00**. Nhưng đơn 101 có **hai item thật**, mỗi item trị giá 25, tổng đúng là **50.00**.

Hàm DISTINCT trong SUM phân biệt **giá trị biểu thức**, không phân biệt **bản ghi hay ID dòng hàng**.

```text
Hai item hợp lệ:
  item 1001 -> line_amount 25
  item 1002 -> line_amount 25

SUM(DISTINCT line_amount) -> 25    (sai)
SUM(line_amount trên hai item) -> 50 (đúng)
```

Tương tự, nếu hai đơn khác nhau cùng có doanh thu 100, `SUM(DISTINCT order_total)` sẽ chỉ cộng một lần số 100, dù có **hai đơn độc lập**. Không thể dùng DISTINCT trên giá trị đo lường để thay thế việc xác định khóa duy nhất của đơn vị được đo.

### 6.1. Khi nào COUNT DISTINCT có thể đúng?

```sql
COUNT(DISTINCT i.item_id)
```

đếm **số item khác nhau** khi `item_id` là khóa duy nhất và có ý nghĩa đếm item. Điều này có thể cho kết quả đúng dù JOIN làm item lặp. Nhưng không được suy từ việc `COUNT(DISTINCT id)` đúng mà cho rằng `SUM(DISTINCT amount)` cũng đúng.

Nếu cần tổng một lần trên **mỗi ID bản ghi**, phải thiết kế lại tập đầu vào để mỗi ID xuất hiện **đúng một lần trước khi SUM**. Đó là lý do kỹ thuật tổng hợp trước theo khóa thường đáng tin cậy hơn mẹo DISTINCT trên số tiền.

## 7. Giải pháp chủ lực: tổng hợp riêng từng bảng con trước khi JOIN

Nếu báo cáo cần **một hàng trên mỗi đơn**, hãy tạo kết quả **một hàng trên mỗi `order_id`** từ bảng item và payment **trước khi nối chúng với nhau**.

### 7.1. Tổng hợp dòng hàng thành một hàng mỗi đơn

```sql
SELECT
    order_id,
    COUNT(*) AS item_line_count,
    SUM(quantity * unit_price) AS item_total
FROM demo_join_order_items
GROUP BY order_id
ORDER BY order_id;
```

Kết quả:

| order_id | item_line_count | item_total |
| ---: | ---: | ---: |
| 101 | 2 | 50.00 |
| 102 | 1 | 40.00 |
| 103 | 1 | 45.00 |

Đơn 104 chưa có item nên **không có nhóm nào ở kết quả này**. Khi LEFT JOIN với orders, ta có thể chọn hiển thị số 0 bằng `COALESCE(...)` nếu quy tắc “chưa có dòng thì tổng hiện tại bằng 0” được xác nhận.

### 7.2. Tổng hợp thanh toán thành một hàng mỗi đơn

Trong PostgreSQL:

```sql
SELECT
    order_id,
    COUNT(*) FILTER (
        WHERE payment_status = 'COMPLETED'
    ) AS completed_payment_count,
    COALESCE(
        SUM(payment_amount) FILTER (
            WHERE payment_status = 'COMPLETED'
        ),
        0
    ) AS completed_payment_total
FROM demo_join_payments
GROUP BY order_id
ORDER BY order_id;
```

Kết quả:

| order_id | completed_payment_count | completed_payment_total |
| ---: | ---: | ---: |
| 101 | 2 | 50.00 |
| 102 | 0 | 0.00 |
| 103 | 1 | 45.00 |

Đơn 102 vẫn có **một payment PENDING**, nhưng không có payment COMPLETED nên tổng thanh toán đã hoàn tất bằng 0 theo quy tắc báo cáo. Nếu cần thêm số payment PENDING, có thể tính một chỉ số riêng trên **cùng bảng payments** trước JOIN.

Với DBMS không hỗ trợ `FILTER`, dùng CASE trong COUNT/SUM:

```sql
SELECT
    order_id,
    COUNT(CASE
        WHEN payment_status = 'COMPLETED' THEN 1
    END) AS completed_payment_count,
    SUM(CASE
        WHEN payment_status = 'COMPLETED' THEN payment_amount
        ELSE 0
    END) AS completed_payment_total
FROM demo_join_payments
GROUP BY order_id;
```

Nếu bảng payment nguồn cho phép `payment_amount NULL`, cần quyết định có được tính là 0 hay phải ghi nhận lỗi dữ liệu. Trong bộ mẫu, `payment_amount NOT NULL`, nên các giá trị hiện có rõ ràng.

### 7.3. Nối hai tập đã giảm về đúng một hàng mỗi đơn

```sql
WITH items_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_total
    FROM demo_join_order_items
    GROUP BY order_id
),
payments_by_order AS (
    SELECT
        order_id,
        COUNT(*) FILTER (
            WHERE payment_status = 'COMPLETED'
        ) AS completed_payment_count,
        SUM(payment_amount) FILTER (
            WHERE payment_status = 'COMPLETED'
        ) AS completed_payment_total
    FROM demo_join_payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    COALESCE(i.item_line_count, 0) AS item_line_count,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.completed_payment_count, 0)
        AS completed_payment_count,
    COALESCE(p.completed_payment_total, 0)
        AS completed_payment_total
FROM demo_join_orders AS o
LEFT JOIN items_by_order AS i
    ON i.order_id = o.order_id
LEFT JOIN payments_by_order AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Kết quả đúng:

| order_id | item_line_count | item_total | completed_payment_count | completed_payment_total |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 2 | 50.00 | 2 | 50.00 |
| 102 | 1 | 40.00 | 0 | 0.00 |
| 103 | 1 | 45.00 | 1 | 45.00 |
| 104 | 0 | 0.00 | 0 | 0.00 |

**Vì sao cách này không nhân số liệu?** `items_by_order` đã bảo đảm **tối đa một hàng trên mỗi order_id** nhờ GROUP BY. `payments_by_order` cũng bảo đảm tối đa một hàng trên mỗi order_id. Mỗi đơn JOIN vào **nhiều nhất một hàng** của mỗi nhánh. Không còn phép kết hợp mọi cặp item–payment.

Một nguyên tắc thực tế là: **mỗi nhánh con phải được đưa về cùng độ hạt với bảng cha trước khi các nhánh được JOIN để lấy KPI theo cha**.

### 7.4. Vì sao GROUP BY sau JOIN không tương đương GROUP BY trước JOIN?

Hai thứ tự xử lý tạo tập đầu vào khác nhau:

```text
KHÔNG AN TOÀN (các nhánh đều 1:N):

orders -- JOIN items -- JOIN payments -- GROUP BY order_id -- SUM
                    |
                    +-- item và payment nhân chéo trước khi SUM

AN TOÀN CHO KPI THEO ĐƠN:

items ---- GROUP BY order_id -> one row/order --+
                                               +-- JOIN orders -> one row/order
payments - GROUP BY order_id -> one row/order --+
```

DBMS tối ưu hóa có thể thay đổi kế hoạch thực thi, nhưng câu SQL phải **diễn đạt đúng ngữ nghĩa** ngay từ đầu. Việc đặt `GROUP BY order_id` ở **cuối** không tự đảo ngược những số tiền đã bị lặp trong phép JOIN.

## 8. Tổng hợp tiếp theo khách hàng mà không nhân lại số tiền

Từ các tập một hàng mỗi đơn, có thể tính chỉ số **một hàng mỗi khách**:

```sql
WITH items_by_order AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM demo_join_order_items
    GROUP BY order_id
),
payments_by_order AS (
    SELECT
        order_id,
        SUM(payment_amount) FILTER (
            WHERE payment_status = 'COMPLETED'
        ) AS completed_payment_total
    FROM demo_join_payments
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(i.item_total), 0) AS merchandise_total,
    COALESCE(SUM(p.completed_payment_total), 0)
        AS completed_payment_total
FROM demo_join_customers AS c
LEFT JOIN demo_join_orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN items_by_order AS i
    ON i.order_id = o.order_id
LEFT JOIN payments_by_order AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | order_count | merchandise_total | completed_payment_total |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 2 | 90.00 | 50.00 |
| 2 | Binh | 2 | 45.00 | 45.00 |
| 3 | Chi | 0 | 0.00 | 0.00 |

An có hai đơn: tổng sản phẩm `50 + 40 = 90`; đã hoàn tất thanh toán 50. Binh có đơn 103 trị giá 45 và đơn nháp 104 chưa có dòng: tổng sản phẩm 45, đã hoàn tất thanh toán 45. Chi chưa có đơn: số đơn bằng 0, tổng hiện tại được hiển thị 0 theo quy tắc `COALESCE`.

**Lưu ý về chỉ số:** `merchandise_total` ở đây là tổng các dòng sản phẩm của **mọi trạng thái đơn**, không mặc định là **doanh thu ghi nhận**. Nếu kinh doanh chỉ coi đơn PAID là doanh thu, cần lọc hoặc tính điều kiện theo `order_status` **trên độ hạt đơn đã tổng hợp**, không chỉ đổi tên cột.

## 9. Đếm chính xác: `COUNT(*)`, `COUNT(key)`, `COUNT(DISTINCT key)`

Ba phép đếm gần giống nhau về cú pháp nhưng trả lời câu hỏi khác nhau.

| Biểu thức | Đếm gì? | Cảnh báo |
| --- | --- | --- |
| `COUNT(*)` | Mọi hàng của tập kết quả hiện tại | Sau JOIN, hàng có thể đã bị nhân; LEFT JOIN có hàng bù |
| `COUNT(child.id)` | Số lần `child.id` khác NULL xuất hiện sau JOIN | ID con có thể xuất hiện nhiều lần nếu bị JOIN với nhánh khác |
| `COUNT(DISTINCT child.id)` | Số **ID con khác nhau**, bỏ NULL | Chỉ đúng nếu id thật sự định danh đơn vị muốn đếm |

### 9.1. Trường hợp không có bản ghi con

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(i.item_id) AS real_item_rows
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
WHERE o.order_id = 104
GROUP BY o.order_id;
```

Kết quả `joined_rows = 1`, `real_item_rows = 0`. Chỉ số đếm **dòng hàng thật** nên dùng khóa con khác NULL, không dùng COUNT(*) sau LEFT JOIN.

### 9.2. Đếm đơn trong khách hàng

```sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count
FROM demo_join_customers AS c
LEFT JOIN demo_join_orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

COUNT DISTINCT order_id bảo đảm mỗi đơn được đếm một lần dù có nhiều item. Trong **truy vấn này**, JOIN với items không cần cho việc đếm đơn nếu không có điều kiện lọc theo item; bỏ JOIN không cần thiết thường đơn giản hơn:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM demo_join_customers AS c
LEFT JOIN demo_join_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Cả hai diễn đạt cùng câu hỏi đếm đơn, nhưng truy vấn thứ hai có ít quan hệ hơn, tránh nhân hàng không cần thiết.

### 9.3. DISTINCT không thay thế việc xác định độ hạt

```sql
SELECT DISTINCT o.order_id, o.order_status
FROM demo_join_orders AS o
JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id;
```

Kết quả có một hàng mỗi đơn có item, vì cặp `(order_id, order_status)` phụ thuộc vào khóa order_id. Nhưng nếu SELECT thêm `i.item_id`, các hàng lại khác nhau và DISTINCT không loại chúng. Hơn nữa, DISTINCT trên đầu ra **không sửa lại số tiền đã SUM sai trong một phép tổng hợp trước đó**.

Hãy dùng DISTINCT khi thực sự cần loại giá trị trùng của **tập kết quả đang yêu cầu**, không dùng như lớp che mọi lỗi JOIN.

## 10. Khi chỉ cần biết có dữ liệu: dùng `EXISTS` thay vì JOIN

Giả sử muốn **danh sách đơn có ít nhất một thanh toán COMPLETED**. Nếu JOIN:

```sql
SELECT o.order_id
FROM demo_join_orders AS o
JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
WHERE p.payment_status = 'COMPLETED';
```

Đơn 101 xuất hiện **hai lần** vì có payment 501 và 502. Nếu mục tiêu chỉ là câu hỏi **“có ít nhất một payment hoàn tất hay không?”**, JOIN đang mang thêm bội số không cần thiết.

Dùng `EXISTS`:

```sql
SELECT
    o.order_id,
    o.order_status
FROM demo_join_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM demo_join_payments AS p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'COMPLETED'
)
ORDER BY o.order_id;
```

Kết quả chỉ có đơn **101 và 103**, mỗi đơn **một lần** vì mỗi hàng orders được đánh giá điều kiện EXISTS một lần. `EXISTS` không mang các payment ra để nhân số dòng.

### 10.1. `NOT EXISTS` cho trường hợp không có bản ghi khớp

Muốn lấy đơn **chưa có payment COMPLETED**:

```sql
SELECT o.order_id
FROM demo_join_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_join_payments AS p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'COMPLETED'
)
ORDER BY o.order_id;
```

Kết quả **102 và 104**. Đơn 102 có payment PENDING nhưng không có COMPLETED; đơn 104 chưa có payment. Cả hai đều phù hợp yêu cầu *không tồn tại thanh toán đã hoàn tất*.

Không mặc định `NOT IN (SELECT order_id ...)` tương đương mọi trường hợp với `NOT EXISTS`: nếu cột của truy vấn con có thể NULL, logic ba giá trị của `NOT IN` có thể làm bỏ hết kết quả ngoài ý muốn. `NOT EXISTS` diễn đạt trực tiếp việc không có hàng phù hợp.

### 10.2. Chọn JOIN hay EXISTS?

- **Cần thông tin chi tiết từng dòng con**: JOIN có thể đúng, chấp nhận nhiều hàng theo độ hạt con.
- **Chỉ cần có/không có bản ghi con**: `EXISTS` hoặc `NOT EXISTS` thường rõ nghĩa hơn.
- **Cần tổng giá trị của bản ghi con**: tổng hợp bảng con trước rồi JOIN kết quả, hoặc dùng subquery tổng hợp phù hợp.
- **Cần đúng một bản ghi con theo tiêu chí như mới nhất**: chọn bản ghi theo `ROW_NUMBER()` hoặc mẫu có thứ tự xác định; đây là nghiệp vụ chọn một bản ghi, không phải sửa lỗi bội số.

## 11. Chọn một bản ghi con: nghiệp vụ “mới nhất” khác tổng mọi bản ghi

Một API có thể cần **thanh toán gần nhất** của từng đơn, thay vì **tổng các thanh toán**. Khi đó điều đúng là *chọn chính xác một payment theo thứ tự*, không phải tổng hợp tiền.

```sql
WITH ranked_payments AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.order_id
            ORDER BY p.recorded_at DESC, p.payment_id DESC
        ) AS rn
    FROM demo_join_payments AS p
)
SELECT
    o.order_id,
    p.payment_id AS latest_payment_id,
    p.payment_status AS latest_payment_status,
    p.payment_amount AS latest_payment_amount
FROM demo_join_orders AS o
LEFT JOIN ranked_payments AS p
    ON p.order_id = o.order_id
   AND p.rn = 1
ORDER BY o.order_id;
```

Với đơn 101, thanh toán gần nhất là payment **502**, amount **20.00**, nhưng tổng hai payment COMPLETED là **50.00**. Hai kết quả khác nhau vì câu hỏi nghiệp vụ khác nhau. Với đơn 104, các cột payment là NULL vì chưa có payment.

**Chỉ nên dùng `ROW_NUMBER() = 1` khi mục tiêu là chọn một bản ghi**, ví dụ payment cuối, phiên bản hồ sơ hiệu lực hoặc sự kiện gần nhất. Nếu nghiệp vụ cần **tổng tất cả payment**, chọn một payment để “loại trùng” sẽ **bỏ mất dữ liệu thật**.

### 11.1. Cần thứ tự duy nhất

`recorded_at` có thể trùng giữa các payment. Thêm `payment_id DESC` là khóa phụ duy nhất để kết quả chọn hàng có thứ tự xác định. Không nên dùng `MAX(payment_id)` làm đại diện thời gian một cách mặc định nếu hệ thống không cam kết ID phản ánh thời điểm sự kiện.

## 12. Mối nối nhiều-nhiều và bảng cầu

Không phải fanout nào cũng xuất phát từ việc JOIN hai bảng con của một đơn. Ví dụ:

- Một sinh viên đăng ký nhiều môn học.
- Một môn có nhiều sinh viên.
- Một sản phẩm thuộc nhiều danh mục.
- Một chương trình khuyến mãi áp dụng cho nhiều sản phẩm.

Quan hệ nhiều-nhiều thường được biểu diễn qua **bảng cầu (bridge/junction table)**. Giả sử:

```text
students --< enrollments >-- courses
              |
              +-- (student_id, course_id) là cặp đăng ký
```

Nếu JOIN students với enrollments rồi courses, một sinh viên có ba môn sẽ xuất hiện **ba hàng**. Đây là kết quả đúng cho báo cáo **danh sách môn theo sinh viên**, nhưng sai nếu đọc `COUNT(*)` là số sinh viên duy nhất.

### 12.1. Thêm bảng nhiều-nhiều vào báo cáo tiền

Nếu một đơn có ba tag và hai item, JOIN cả `order_tags` và `order_items` có thể tạo **3 × 2 = 6 hàng cho cùng đơn**. Cộng tiền item trực tiếp trên tập đó sẽ nhân ba doanh thu theo dòng.

Để báo cáo theo tag, phải quyết định cách **phân bổ** số tiền:

1. **Đếm đủ doanh thu cho từng tag** nếu một đơn có nhiều tag — tổng doanh thu theo tag sẽ **không cộng gộp** về tổng toàn hệ thống.
2. **Phân bổ tỷ trọng** giữa các tag — phải định nghĩa trọng số và quy tắc phân bổ sao cho tổng tỷ trọng theo đơn phù hợp.
3. **Chọn tag chính** — chỉ hợp lệ khi nghiệp vụ có thuộc tính tag chính duy nhất.

Không có câu lệnh DISTINCT nào tự quyết định đúng chính sách phân bổ tài chính khi một giao dịch thuộc nhiều nhóm.

### 12.2. Mối quan hệ hợp lệ không có nghĩa mọi phép cộng đều cộng được

Một bảng phân tích dữ liệu có thể cần hiển thị doanh thu theo **sản phẩm**, **khu vực**, **chiến dịch**. Nếu một đơn được gắn nhiều sản phẩm và nhiều chiến dịch, không thể cộng số tiền cấp đơn một cách vô điều kiện trên mọi kết hợp sản phẩm–chiến dịch. Đây là loại lỗi thường được gọi là **fan trap/chasm trap** trong thiết kế báo cáo: nhiều quan hệ hợp lệ khi JOIN lại tạo bội số làm sai measure.

Giải pháp phụ thuộc **grain của measure** và **cách phân bổ measure sang dimension**, không chỉ phụ thuộc cú pháp JOIN.

## 13. Thiếu điều kiện JOIN cũng có thể tạo bội số không mong muốn

Một lỗi khác với fanout hợp lệ là **JOIN thiếu cột khóa**.

Giả sử hệ thống nhiều tổ chức có bảng hóa đơn:

```text
invoices:
  (tenant_id=1, invoice_no='INV-001')
  (tenant_id=2, invoice_no='INV-001')

invoice_lines:
  (tenant_id=1, invoice_no='INV-001', line_no=1)
  (tenant_id=2, invoice_no='INV-001', line_no=1)
```

Nếu chỉ JOIN bằng `invoice_no`:

```sql
-- Sai khi invoice_no chỉ duy nhất trong từng tenant:
SELECT i.tenant_id, i.invoice_no, l.line_no
FROM invoices AS i
JOIN invoice_lines AS l
    ON l.invoice_no = i.invoice_no;
```

Mỗi hóa đơn có thể khớp cả dòng của tenant khác, làm sinh bội số và **lẫn dữ liệu giữa tổ chức**. Cần nối bằng **đầy đủ khóa định danh**:

```sql
SELECT i.tenant_id, i.invoice_no, l.line_no
FROM invoices AS i
JOIN invoice_lines AS l
    ON l.tenant_id = i.tenant_id
   AND l.invoice_no = i.invoice_no;
```

Hai đoạn trên minh họa mô hình bảng giả định, không dùng bảng tạm của mục 2. Ngoài đúng số liệu, một điều kiện JOIN thiếu tenant có thể tạo **lỗi bảo mật và rò rỉ dữ liệu**; ứng dụng phải có cơ chế phân quyền độc lập chứ không chỉ dựa vào JOIN đúng.

### 13.1. Điều kiện thời gian hiệu lực trong bảng lịch sử

Một bảng giá hoặc địa chỉ có lịch sử nhiều phiên bản:

```text
product_price_history:
  product_id, valid_from, valid_to, unit_price
```

JOIN theo `product_id` đơn thuần sẽ ghép một giao dịch với **mọi phiên bản giá trong quá khứ**. Nếu mục tiêu là giá tại thời điểm giao dịch, cần thêm điều kiện thời gian:

```sql
-- Mẫu minh họa, cần quy ước khoảng hiệu lực nửa mở.
SELECT
    s.sale_id,
    s.product_id,
    h.unit_price
FROM sales AS s
JOIN product_price_history AS h
    ON h.product_id = s.product_id
   AND s.sold_at >= h.valid_from
   AND s.sold_at <  h.valid_to;
```

Điều kiện trên đúng khi `valid_to` luôn có giá trị và lịch sử được thiết kế bằng khoảng hiệu lực nửa mở, không chồng lấn; nếu `valid_to NULL` biểu thị vô hạn, cần quy tắc bổ sung. Nếu các khoảng thời gian **chồng lấn**, một giao dịch vẫn có thể khớp nhiều giá và nhân hàng. Phải bảo vệ **tính duy nhất theo thời gian** bằng thiết kế và ràng buộc thích hợp.

### 13.2. Không dùng CROSS JOIN khi không chủ định

Thiếu điều kiện nối có thể dẫn tới tích Descartes:

```sql
-- Mỗi khách ghép với mọi đơn, không xét quan hệ khách–đơn.
SELECT c.customer_id, o.order_id
FROM demo_join_customers AS c
CROSS JOIN demo_join_orders AS o;
```

3 khách × 4 đơn = **12 hàng**. CROSS JOIN là phép hợp lệ khi muốn tạo mọi tổ hợp (ví dụ lịch × danh mục), nhưng khi cần quan hệ khách–đơn phải dùng JOIN có ON đúng:

```sql
SELECT c.customer_id, o.order_id
FROM demo_join_customers AS c
JOIN demo_join_orders AS o
    ON o.customer_id = c.customer_id;
```

## 14. Bộ câu hỏi chẩn đoán bội số hàng

Khi một báo cáo có số tiền hoặc số lượng “cao bất thường”, nên xác minh ở nhiều cấp.

### 14.1. Đếm hàng trước và sau từng JOIN

```sql
-- Số đơn gốc.
SELECT COUNT(*) AS orders_before_join
FROM demo_join_orders;
-- 4

-- Sau JOIN một bảng con.
SELECT COUNT(*) AS rows_after_item_join
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id;
-- 5: hai hàng đơn 101, ba đơn còn lại mỗi đơn một hàng (kể cả 104)

-- Sau JOIN cả hai bảng con.
SELECT COUNT(*) AS rows_after_both_joins
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id;
-- 7
```

Số hàng tăng **không luôn là lỗi**, nhưng là tín hiệu cần giải thích theo quan hệ. Nếu báo cáo chỉ mong **một hàng mỗi đơn**, số hàng tăng từ 4 lên 5 rồi 7 nghĩa là **độ hạt kết quả đã khác yêu cầu**.

### 14.2. Xem bội số trên khóa cha

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_row_count
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
HAVING COUNT(*) > 1
ORDER BY joined_row_count DESC, o.order_id;
```

Với dữ liệu mẫu, chỉ đơn **101** có hơn một hàng sau JOIN. Truy vấn này định vị **nơi bội số xuất hiện**, chứ không mặc định các hàng của đơn 101 là dữ liệu nguồn bị trùng.

### 14.3. Kiểm tra tính duy nhất ở phía được kỳ vọng một hàng

Giả sử JOIN đến bảng `customer_profiles` và thiết kế kỳ vọng **tối đa một hồ sơ trên mỗi customer_id**. Kiểm tra:

```sql
-- Mẫu kiểm tra trên bảng nghiệp vụ giả định:
SELECT customer_id, COUNT(*) AS occurrences
FROM customer_profiles
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Nếu có hàng, dữ liệu có thể vi phạm kỳ vọng một-một hoặc thiết kế thiếu điều kiện chọn bản ghi hiệu lực. Nên bổ sung `UNIQUE(customer_id)` nếu thực sự có quy tắc một hồ sơ trên mỗi khách; nếu hồ sơ có lịch sử phiên bản, khóa duy nhất cần phản ánh đúng phạm vi và điều kiện chọn phiên bản.

**Không áp dụng kiểm tra ấy để kết luận `order_items.order_id` bị lỗi:** một đơn có nhiều dòng là hợp lệ. Tính duy nhất phải được xác định theo **mô hình dữ liệu**, không phải theo mong muốn báo cáo.

### 14.4. Đối chiếu chỉ số với nguồn độc lập

```sql
WITH source_totals AS (
    SELECT
        (SELECT SUM(quantity * unit_price)
         FROM demo_join_order_items) AS item_total,
        (SELECT SUM(payment_amount)
         FROM demo_join_payments
         WHERE payment_status = 'COMPLETED') AS completed_total
),
joined_totals AS (
    SELECT
        SUM(i.quantity * i.unit_price) AS item_total,
        SUM(CASE
            WHEN p.payment_status = 'COMPLETED'
            THEN p.payment_amount ELSE 0
        END) AS completed_total
    FROM demo_join_orders AS o
    LEFT JOIN demo_join_order_items AS i
        ON i.order_id = o.order_id
    LEFT JOIN demo_join_payments AS p
        ON p.order_id = o.order_id
)
SELECT
    s.item_total AS source_item_total,
    j.item_total AS joined_item_total,
    s.completed_total AS source_completed_total,
    j.completed_total AS joined_completed_total
FROM source_totals AS s
CROSS JOIN joined_totals AS j;
```

Kỳ vọng theo dữ liệu mẫu là **135 so với 185** và **95 so với 145**. Đây là cách quan sát sự chênh lệch **khi JOIN làm thay đổi bội số**, không phải câu lệnh sửa dữ liệu.

Trong hệ thống thật, cần chắc chắn hai bên đối chiếu có cùng điều kiện ngày, trạng thái, tenant, đơn vị tiền và quy ước hoàn tiền; nếu phạm vi không giống nhau, chênh lệch không nhất thiết do JOIN.

### 14.5. Xem hàng chi tiết của một khóa bất thường

```sql
SELECT
    o.order_id,
    i.item_id,
    p.payment_id,
    i.quantity * i.unit_price AS line_amount,
    p.payment_amount
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101
ORDER BY i.item_id, p.payment_id;
```

Việc nhìn từng cặp `(item_id, payment_id)` thường cho thấy ngay **các bản ghi có bị ghép chéo hay không**. Đừng chỉ nhìn tổng số tiền sai rồi thêm `DISTINCT` mà không xác định bản ghi nào lặp và vì sao.

## 15. Lưu ý về GROUP BY, DISTINCT và kết quả nhiều nhóm

### 15.1. GROUP BY đúng khóa không đủ nếu đầu vào đã sai grain

```sql
SELECT
    o.customer_id,
    SUM(i.quantity * i.unit_price) AS item_total
FROM demo_join_orders AS o
JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
JOIN demo_join_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.customer_id;
```

Khách An bị cộng lặp giá trị của đơn 101 vì đơn có hai payment. Group theo customer_id làm kết quả **một hàng mỗi khách**, nhưng phép SUM vẫn nhận những dòng item bị lặp. **Một hàng kết quả sau GROUP BY không chứng minh phép đo đã được tổng hợp đúng từ nguồn**.

### 15.2. DISTINCT trên toàn hàng không xử lý được phần lớn fanout

```sql
SELECT DISTINCT
    o.order_id,
    i.item_id,
    p.payment_id
FROM demo_join_orders AS o
JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
JOIN demo_join_payments AS p
    ON p.order_id = o.order_id;
```

Với đơn 101, bốn cặp `(order_id,item_id,payment_id)` đều **khác nhau**, nên DISTINCT vẫn giữ bốn hàng. Nếu bỏ payment_id khỏi SELECT, DISTINCT có thể làm mỗi item chỉ xuất hiện một lần, nhưng điều đó **đổi cấu trúc và ý nghĩa kết quả**; có thể bỏ mất dữ liệu payment cần thiết cho báo cáo.

Không nên thay đổi danh sách SELECT chỉ để DISTINCT vô tình cho ra số hàng mong muốn; hãy xác định trước mức chi tiết đúng và thiết kế bước JOIN/tổng hợp phù hợp.

### 15.3. Đếm duy nhất và đo lường là hai bài toán

`COUNT(DISTINCT order_id)` trả số đơn duy nhất trong tập hàng đã JOIN. Nhưng `SUM(DISTINCT payment_amount)` không trả tổng tiền đã thu đúng khi nhiều thanh toán hợp lệ có cùng số tiền. Một số tiền **không phải khóa định danh**; không thể phân biệt giao dịch bằng giá trị tiền đơn thuần.

Trong hệ thống kế toán, thường cần một đơn vị đo rõ như payment_id, ledger_entry_id hoặc line_item_id, cùng các điều kiện trạng thái nghiệp vụ đúng. Tổng hợp phải dựa trên **các bản ghi đo lường duy nhất**, không chỉ những giá trị số khác nhau.

## 16. Bảng chiều, dữ liệu lịch sử và kỳ vọng một-một

Một JOIN từ fact sang dimension **không nhất thiết làm nhân hàng** nếu phía dimension có đúng một hàng cho mỗi khóa:

```text
orders (nhiều hàng)
    |
    +-- customer_id -> customers.customer_id (PRIMARY KEY)
```

Trong mô hình trên, JOIN từ một đơn đến đúng một khách theo khóa ngoại có thể giữ **một hàng mỗi đơn**. Nhưng nếu nối sang bảng lịch sử nhiều phiên bản `customer_address_history`, cùng customer_id có thể khớp nhiều địa chỉ. Khi đó:

1. Phải định nghĩa **địa chỉ nào** ứng với đơn: địa chỉ tại lúc đặt hàng, địa chỉ hiện tại, địa chỉ giao hàng hay mọi địa chỉ từng dùng?
2. Dùng khóa hoặc điều kiện thời gian để chọn đúng bản ghi liên quan.
3. Nếu chỉ cần kiểm tra có địa chỉ hợp lệ, có thể dùng EXISTS.
4. Nếu cần báo cáo theo địa chỉ, xác định xem một đơn có thể thuộc nhiều địa chỉ không và cách phân bổ chỉ số.

**Tên bảng chứa chữ “dimension” hoặc “lookup” không tự bảo đảm tính duy nhất.** Cần đọc khóa, ràng buộc, phạm vi hiệu lực và tính ổn định của dữ liệu.

## 17. Hiệu năng: giảm fanout thường giúp cả tính đúng lẫn chi phí

JOIN tạo kết quả trung gian rộng hoặc nhiều hàng có thể tăng:

- Số hàng cần chuyển giữa các bước thực thi;
- Chi phí hash join, sort, GROUP BY hoặc DISTINCT;
- Lượng bộ nhớ dùng cho bảng băm và nhóm;
- I/O, spill xuống đĩa hoặc trao đổi dữ liệu trong hệ phân tán;
- Chi phí truyền dữ liệu nếu ứng dụng thực sự lấy kết quả chi tiết.

Tổng hợp trước từng bảng con **có thể** giảm số hàng phải JOIN, nhất là khi số dòng con lớn. Tuy nhiên, không có quy tắc tuyệt đối rằng mọi pre-aggregation đều nhanh hơn: nếu truy vấn chỉ cần một tập cha rất nhỏ, việc quét/tổng hợp toàn bộ bảng con trước có thể kém hơn một chiến lược dùng index và điều kiện lọc hiệu quả.

### 17.1. Đưa bộ lọc đúng chỗ trước khi tổng hợp

Nếu báo cáo chỉ quan tâm **đơn của một khách** hoặc **một tháng**, có thể lọc tập orders trước rồi giới hạn phạm vi item/payment cần tổng hợp:

```sql
WITH selected_orders AS (
    SELECT order_id, customer_id
    FROM demo_join_orders
    WHERE customer_id = 1
),
items_for_selected_orders AS (
    SELECT
        i.order_id,
        SUM(i.quantity * i.unit_price) AS item_total
    FROM demo_join_order_items AS i
    JOIN selected_orders AS s
        ON s.order_id = i.order_id
    GROUP BY i.order_id
)
SELECT
    s.order_id,
    COALESCE(i.item_total, 0) AS item_total
FROM selected_orders AS s
LEFT JOIN items_for_selected_orders AS i
    ON i.order_id = s.order_id
ORDER BY s.order_id;
```

Vì `selected_orders.order_id` là duy nhất theo bảng orders và điều kiện không tạo trùng, JOIN item với selected_orders trước GROUP BY **không nhân item vì có nhiều hàng cha**. Ở đây chưa JOIN payments, nên không có sản phẩm Descartes giữa hai nhánh con.

Đây là một mẫu tổ chức truy vấn; bộ tối ưu có thể biến đổi hoặc đẩy lọc theo cách khác. Hiệu năng cuối cùng cần được đo bằng kế hoạch thực thi và dữ liệu đại diện.

### 17.2. Chỉ mục cho khóa ngoại JOIN

Trong PostgreSQL, khai báo FOREIGN KEY **không mặc nhiên tạo chỉ mục cho cột tham chiếu ở bảng con**. Với truy vấn tìm item/payment theo order_id thường xuyên, có thể cân nhắc:

```sql
CREATE INDEX idx_demo_join_items_order
ON demo_join_order_items (order_id);

CREATE INDEX idx_demo_join_payments_order
ON demo_join_payments (order_id);
```

Chỉ mục có thể giúp truy cập các dòng con theo khóa cha, nhưng không làm thay đổi số lượng hàng **đúng ngữ nghĩa** của JOIN. Một JOIN 2 item × 2 payment vẫn tạo bốn hàng dù cả hai bảng có index. **Index tối ưu cách tìm**, còn **grain và các điều kiện JOIN quyết định cách ghép**.

Trước khi thêm index vào hệ thống thật, xem tần suất truy vấn, kích thước bảng, độ chọn lọc và chi phí cập nhật/ghi.

### 17.3. EXPLAIN để quan sát số hàng tăng qua JOIN

```sql
EXPLAIN
SELECT
    o.order_id,
    i.item_id,
    p.payment_id
FROM demo_join_orders AS o
LEFT JOIN demo_join_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN demo_join_payments AS p
    ON p.order_id = o.order_id;
```

Trên PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` thực sự thực thi truy vấn và ghi số hàng quan sát tại từng node, thời gian và buffer. Khi xem kế hoạch:

- Xem **số hàng ước lượng** và **thực tế** của các node JOIN.
- So sánh số hàng tăng sau mỗi nhánh.
- Kiểm tra điều kiện JOIN có đầy đủ khóa và bộ lọc không.
- Đọc xem Aggregate/HashAggregate nằm trước hay sau các bước ghép theo kế hoạch.
- Không kết luận một bảng demo có vài hàng sẽ có cùng kế hoạch với dữ liệu sản xuất lớn.

Một chỉ số sai do bội số **không được sửa bởi kế hoạch nhanh hơn**. Ưu tiên đúng ngữ nghĩa, sau đó tối ưu chi phí.

## 18. Quy trình thiết kế truy vấn nhiều bảng đáng tin cậy

Khi cần báo cáo tổng hợp từ nhiều bảng, có thể làm theo quy trình:

1. **Ghi rõ KPI:** đang đếm đơn, đếm dòng, đếm payment hay cộng tiền nào? Có tính đơn chưa trả tiền, hoàn tiền và thanh toán thất bại không?
2. **Chỉ định grain đích:** một hàng mỗi đơn, mỗi khách, mỗi tháng, mỗi cặp sản phẩm–kênh hay mỗi payment?
3. **Chỉ định grain của từng nguồn:** bảng nào một hàng mỗi đơn, bảng nào nhiều dòng mỗi đơn? Có lịch sử phiên bản hay nhiều-tenant không?
4. **Xác nhận khóa JOIN:** có đầy đủ tenant, khóa ghép và điều kiện thời gian không? Có unique constraint ở phía kỳ vọng một hàng không?
5. **Chẩn đoán bội số:** đo COUNT trước/sau JOIN, GROUP BY khóa cha để thấy số lần xuất hiện.
6. **Đưa từng nhánh đo lường về grain chung:** GROUP BY order_id đối với item và payment nếu KPI theo đơn.
7. **Chọn kỹ thuật đúng mục đích:** `EXISTS` cho kiểm tra có/không; `ROW_NUMBER` khi thật sự chọn bản ghi gần nhất; `COUNT(DISTINCT key)` cho đếm thực thể duy nhất.
8. **Kết hợp và tổng hợp tiếp:** nối các tập một hàng mỗi đơn, rồi GROUP BY khách/tháng nếu cần.
9. **Xử lý nhóm thiếu và NULL:** phân biệt không có bản ghi con, có bản ghi nhưng số tiền NULL và khoản tiền đúng bằng 0.
10. **Đối chiếu trên bảng nguồn:** tổng tiền và số lượng phải phù hợp phạm vi, trạng thái, loại tiền và ngày báo cáo.
11. **Đo hiệu năng khi truy vấn đã đúng:** EXPLAIN, chỉ mục trên khóa ngoại, điều kiện lọc sớm và dữ liệu thực tế.

Đặc biệt với báo cáo tài chính, **tính đúng của KPI quan trọng hơn việc truy vấn trả một con số không lỗi hoặc chạy rất nhanh**.

## 19. Bài tập thực hành

Các bài sử dụng các bảng tạm ở mục 2. Hãy dự đoán bội số hàng và số liệu trước khi tự chạy SQL, để phân biệt đúng **trùng dữ liệu nguồn** và **lặp bản ghi do JOIN**.

### Bài 1 — Hai item và hai payment

Cho đơn 101 có item 1001, 1002 và payment 501, 502. Viết một LEFT JOIN từ orders sang cả hai bảng con, liệt kê `(order_id, item_id, payment_id)`. Có bao nhiêu hàng? Vì sao không thể xem số hàng đó là số item hoặc số payment?

Gợi ý: **4 hàng**, tương ứng mọi cặp item–payment.

### Bài 2 — Đếm trước và sau JOIN

Viết ba câu COUNT:

1. Đếm số đơn gốc trong demo_join_orders.
2. Đếm số hàng sau LEFT JOIN item.
3. Đếm số hàng sau LEFT JOIN cả item và payment.

Giải thích vì sao kết quả lần lượt là **4, 5, 7**, dù dữ liệu nguồn có 4 đơn, 4 item và 4 payment.

### Bài 3 — SUM sai nhưng không báo lỗi

Viết phép cộng `i.quantity * i.unit_price` trên kết quả JOIN cả item và payment. Giải thích vì sao tổng là **185.00** thay vì **135.00**. Hãy chỉ rõ đơn nào làm tăng tổng và tăng bao nhiêu.

Gợi ý: đơn 101 có item_total thật 50 nhưng bị cộng thành 100, tăng **50.00**.

### Bài 4 — Tổng payment sai

Viết `SUM(CASE WHEN payment_status='COMPLETED' THEN payment_amount ELSE 0 END)` sau hai LEFT JOIN. Vì sao ra **145.00** thay vì **95.00**? Đổi CASE sang FILTER của PostgreSQL có sửa bội số không?

### Bài 5 — `SUM(DISTINCT ...)` làm thiếu tiền

Hai item 1001 và 1002 đều có line_amount = 25. Tại sao `SUM(DISTINCT line_amount)` chỉ trả **25.00** cho đơn 101, trong khi tổng đúng là 50? Khi nào `COUNT(DISTINCT item_id)` lại có thể là cách đếm đúng?

### Bài 6 — Tổng hợp trước rồi JOIN

Tạo CTE `items_by_order` gồm `order_id`, `item_line_count`, `item_total`; CTE `payments_by_order` gồm `order_id`, `completed_payment_count`, `completed_payment_total`. LEFT JOIN hai CTE với orders. Kiểm tra bốn hàng kết quả có tổng item **135** và tổng payment COMPLETED **95**.

### Bài 7 — Giữ cả khách chưa có đơn

Từ CTE tổng hợp theo order, JOIN tiếp sang customers rồi GROUP BY customer_id. Trả `customer_name`, `order_count`, `item_total`, `completed_payment_total`. Khách Chi cần có **0 đơn**, không phải 1. Vì sao `COUNT(*)` sau LEFT JOIN customers–orders có thể sai cho Chi?

### Bài 8 — EXISTS thay cho JOIN

Viết câu truy vấn lấy danh sách đơn có ít nhất một payment COMPLETED bằng JOIN và bằng EXISTS. Vì sao câu JOIN chưa DISTINCT có thể trả đơn 101 hai lần, còn EXISTS trả một lần? Dùng NOT EXISTS để lấy những đơn không có payment COMPLETED và dự đoán kết quả.

Gợi ý: NOT EXISTS trả **102, 104**.

### Bài 9 — Payment mới nhất không phải tổng payment

Viết ROW_NUMBER partition theo order_id, sắp theo recorded_at DESC và payment_id DESC, chọn rn=1. Với đơn 101, payment mới nhất có ID và amount nào? Vì sao lấy amount của payment mới nhất thay cho SUM các payment COMPLETED sẽ cho sai chỉ số “tổng đã thu”?

### Bài 10 — Khóa ghép và multi-tenant

Một bảng hóa đơn dùng `(tenant_id, invoice_no)` để định danh, trong đó invoice_no có thể trùng giữa tenant. Giải thích vì sao JOIN chỉ bằng invoice_no có thể ghép nhầm và nhân dữ liệu. Viết lại điều kiện ON đầy đủ và nêu rủi ro phân quyền nếu bỏ tenant_id.

### Bài 11 — Báo cáo theo tag

Một đơn có 2 item và 3 tag. Truy vấn JOIN cả item và tag trả bao nhiêu hàng cho đơn đó nếu mọi tổ hợp được phép? Nếu cần báo cáo doanh thu theo từng tag, có thể cộng toàn bộ doanh thu đơn cho mỗi tag rồi cộng các tag thành doanh thu hệ thống không? Hãy đề xuất một chính sách phân bổ hoặc nêu rõ KPI không cộng gộp được.

### Bài 12 — Khi nào một hàng con là dữ liệu trùng thật?

Một bảng `customer_profiles` được kỳ vọng có đúng một hồ sơ hiện hành cho mỗi customer_id nhưng câu kiểm tra `GROUP BY customer_id HAVING COUNT(*)>1` trả kết quả. Hãy phân biệt:

- Dữ liệu sai vì thiếu UNIQUE hoặc thiếu quy tắc chọn hồ sơ hiệu lực;
- Dữ liệu lịch sử hợp lệ với nhiều phiên bản;
- Dữ liệu hợp lệ có nhiều dòng như order_items.

Chỉ sau khi xác định mô hình mới quyết định sửa constraint, sửa JOIN hay sửa cách chọn phiên bản.

### Bài 13 — Chỉ số tiền và trạng thái nghiệp vụ

Đơn 102 có một payment PENDING = 10.00 nhưng chưa có payment COMPLETED. Tại sao không được tự cộng 10.00 vào chỉ số “tiền đã thu”? Nếu hệ thống có REFUNDED/FAILED, cần thiết kế quy tắc trạng thái và dấu tiền ra sao để báo cáo phản ánh sổ cái chính xác?

### Bài 14 — Chọn lại grain để tối ưu

Một dashboard chỉ xem đơn của khách 1 trong 30 ngày. So sánh việc tổng hợp toàn bộ item/payment của mọi khách trước rồi lọc, với việc lọc `selected_orders` trước khi tổng hợp từng bảng con. Hai cách có thể khác hiệu năng thế nào? Khi nào chỉ mục `order_items(order_id)` hoặc `payments(order_id)` giúp ích? Vì sao không thể tối ưu nếu JOIN vẫn sai ngữ nghĩa?

## 20. Kết luận: kiểm tra grain trước khi cộng

Hãy ghi nhớ sơ đồ:

```text
Tập dữ liệu nguồn
       |
       +-- orders:       1 hàng / order_id
       +-- order_items:  N hàng / order_id
       +-- payments:     M hàng / order_id
       |
       +-- JOIN tất cả trực tiếp
       |       |
       |       +-- Có thể N x M hàng / order_id
       |       +-- COUNT/SUM trên kết quả dễ bị nhân
       |
       +-- Tổng hợp từng nhánh trước
               |
               +-- items_by_order:     1 hàng / order_id
               +-- payments_by_order:  1 hàng / order_id
               |
               +-- JOIN orders -> 1 hàng / order_id
               |
               +-- GROUP BY khách / tháng nếu cần
                       |
                       +-- KPI không bị cộng lặp do hai nhánh con
```

**JOIN không có trách nhiệm tự bảo toàn số hàng hoặc số tiền của bảng nguồn.** Nó tạo các tổ hợp hàng đúng theo điều kiện ghép; vì vậy quan hệ 1:N, nhiều-nhiều hoặc JOIN thiếu khóa có thể khiến một thực thể xuất hiện nhiều lần. `COUNT(*)`, `SUM`, `CASE`, `FILTER` và DISTINCT đều làm việc trên **tập hàng thực tế mà chúng nhận được**; không có hàm nào tự biết số tiền nên được cộng một lần trên mỗi đơn hay mỗi thanh toán.

Để tránh cộng lặp, hãy **xác định đơn vị đo, kiểm tra bội số trước/sau JOIN, dùng đầy đủ khóa, tổng hợp từng nhánh ở độ hạt thích hợp, và đối chiếu kết quả với nguồn độc lập**. Dùng `EXISTS` khi chỉ cần biết có hàng con, dùng `COUNT(DISTINCT key)` khi đếm thực thể duy nhất, và dùng `ROW_NUMBER` khi thật sự muốn chọn một bản ghi theo thứ tự. Tuyệt đối không dựa vào `SUM(DISTINCT amount)` để sửa một phép cộng sai do JOIN.

Một báo cáo đáng tin cậy không chỉ “chạy được SQL”; nó phải trả lời chính xác **mỗi hàng đại diện cho điều gì và mỗi giá trị đang được tính bao nhiêu lần**.
