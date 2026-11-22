# Đếm thực thể sau JOIN và phòng tránh nhân đôi số liệu trong SQL

Một câu truy vấn có thể chạy thành công, không báo lỗi và vẫn cho **số liệu sai**. Ví dụ, hệ thống có 2 đơn hàng nhưng báo cáo đếm thành 5 “đơn hàng”; doanh thu thực tế là 320.000 đồng nhưng sau khi `JOIN` với chi tiết hàng hóa và thanh toán, tổng bị nâng lên 680.000 đồng.

Nguyên nhân thường không nằm ở hàm `COUNT` hay `SUM`, mà ở **số dòng phát sinh sau phép nối bảng (`JOIN`)**. Khi nối một bản ghi với nhiều bản ghi liên quan, dữ liệu từ phía “một” được lặp lại ở từng dòng kết quả. Nếu tiếp tục nối **hai quan hệ một–nhiều độc lập**, những dòng lặp có thể nhân với nhau.

Bài học này giải thích cách **đếm đúng thực thể** và **tổng hợp đúng số liệu** sau `JOIN`: xác định cấp độ hạt của dữ liệu (*grain*), hiểu `COUNT(*)` và `COUNT(DISTINCT ...)`, dùng `EXISTS` khi chỉ cần kiểm tra sự tồn tại, tiền tổng hợp (*pre-aggregation*) trước khi nối các bảng con, và kiểm tra tác động của `LEFT JOIN`, `WHERE` cùng các điều kiện lọc.

Ví dụ sử dụng **PostgreSQL** để có thể thực hành xuyên suốt. Phần lớn nguyên tắc áp dụng cho MySQL, SQL Server, SQLite và nhiều hệ quản trị SQL khác, dù cú pháp thống kê hoặc một số hàm có thể khác.

## 1. Trước khi COUNT hay SUM, phải biết mình đang đếm cái gì

Xem ba câu hỏi:

1. **Có bao nhiêu khách hàng?**
2. **Có bao nhiêu đơn hàng?**
3. **Có bao nhiêu dòng chi tiết sản phẩm trong đơn hàng?**

Ba câu này có thể được trả lời từ ba cấp độ dữ liệu khác nhau:

| Thực thể | Khóa nhận diện | Một dòng biểu diễn | Đơn vị đếm |
|---|---|---|---|
| Khách hàng | `customer_id` | Một khách hàng | Khách hàng |
| Đơn hàng | `order_id` | Một đơn hàng | Đơn hàng |
| Chi tiết đơn hàng | `item_id` | Một dòng sản phẩm thuộc một đơn | Dòng chi tiết |
| Thanh toán | `payment_id` | Một giao dịch thanh toán | Lần thanh toán |

**Grain** là cấp độ chi tiết mà một dòng biểu diễn. Chẳng hạn bảng `orders` có grain **một dòng trên một đơn hàng**, còn bảng `order_items` có grain **một dòng trên một chi tiết đơn hàng**.

Nếu nối khách hàng với đơn hàng, kết quả thường có grain **một dòng trên một đơn hàng của khách hàng**. Khách hàng có hai đơn sẽ xuất hiện hai lần. Điều này **không phải lỗi JOIN**; phép nối đang biểu diễn đúng quan hệ một–nhiều. Lỗi phát sinh khi ta lấy `COUNT(*)` rồi gọi kết quả đó là “số khách hàng”, hoặc cộng một giá trị ở cấp đơn hàng trên các dòng đã nhân lên.

### 1.1. Đếm dòng khác với đếm thực thể

Ví dụ một bảng kết quả `JOIN`:

| customer_id | customer_name | order_id |
|---:|---|---:|
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Bình | 103 |

Kết quả có **3 dòng**, **2 khách hàng**, **3 đơn hàng**. Vì thế:

- `COUNT(*) = 3`: đếm dòng sau `JOIN`.
- `COUNT(DISTINCT customer_id) = 2`: đếm khách hàng khác nhau.
- `COUNT(order_id) = 3`: đếm giá trị `order_id` khác `NULL`, đúng với số đơn trong ví dụ vì mỗi đơn đang xuất hiện một lần.

Nếu sau đó nối thêm `order_items`, mỗi đơn có thể xuất hiện nhiều lần; `COUNT(order_id)` có thể không còn bằng số đơn thật nữa.

### 1.2. Quan hệ một–một, một–nhiều và nhiều–nhiều

| Quan hệ khi nối | Khả năng thay đổi số dòng | Ví dụ |
|---|---|---|
| Một–một (`1:1`) | Mỗi dòng thường khớp tối đa một dòng bên kia | Đơn hàng ↔ thông tin mở rộng duy nhất |
| Một–nhiều (`1:N`) | Một bản ghi phía một có thể tạo N dòng | Khách hàng ↔ đơn hàng |
| Nhiều–nhiều (`N:M`) | Số dòng có thể tăng đáng kể qua bảng trung gian | Sản phẩm ↔ nhãn sản phẩm |
| Nối các quan hệ `1:N` độc lập | Những bội số có thể nhân với nhau | Đơn hàng ↔ chi tiết và đơn hàng ↔ thanh toán |

Khi mục tiêu là đếm **khách hàng**, số dòng kết quả sau nối với **đơn hàng** không còn tương ứng trực tiếp với số khách hàng. Khi mục tiêu là cộng **tổng tiền đơn hàng**, mỗi `order_total` cũng phải được tính **đúng một lần trên mỗi đơn**, không phải mỗi dòng chi tiết.

## 2. Chuẩn bị bộ dữ liệu thực hành PostgreSQL

Để thấy chính xác nơi số liệu bị nhân, ta tạo bốn bảng có khóa chính và khóa ngoại rõ ràng. Hãy chạy các câu tạo bảng trong **cơ sở dữ liệu thực hành** có quyền tạo đối tượng, một lần cho mỗi lượt thử.

### 2.1. Khách hàng và đơn hàng

```sql
CREATE TABLE lesson167_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE lesson167_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lesson167_customers(customer_id),
    order_total NUMERIC(12, 2) NOT NULL,
    order_status VARCHAR(20) NOT NULL
);

INSERT INTO lesson167_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dũng');

INSERT INTO lesson167_orders (
    order_id, customer_id, order_total, order_status
)
VALUES
    (101, 1, 120000.00, 'CONFIRMED'),
    (102, 1, 200000.00, 'CONFIRMED'),
    (103, 2,  80000.00, 'NEW'),
    (104, 3, 150000.00, 'CONFIRMED');
```

Các khách hàng có số đơn lần lượt:

| Khách hàng | Các đơn | Số đơn | Tổng giá trị đơn |
|---|---|---:|---:|
| An | 101, 102 | 2 | 320.000 |
| Bình | 103 | 1 | 80.000 |
| Chi | 104 | 1 | 150.000 |
| Dũng | Không có | 0 | 0 trong báo cáo có quy tắc thay `NULL` bằng 0 |

Bảng `lesson167_orders` có **4 dòng** và **4 mã `order_id` duy nhất**.

### 2.2. Chi tiết sản phẩm và thanh toán

```sql
CREATE TABLE lesson167_order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lesson167_orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
);

CREATE TABLE lesson167_payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lesson167_orders(order_id),
    paid_amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO lesson167_order_items (
    item_id, order_id, quantity, unit_price
)
VALUES
    (1001, 101, 2, 30000.00),  -- 60.000
    (1002, 101, 1, 60000.00),  -- 60.000
    (1003, 102, 2, 100000.00), -- 200.000
    (1004, 103, 1, 80000.00),  -- 80.000
    (1005, 104, 3, 50000.00);  -- 150.000

INSERT INTO lesson167_payments (
    payment_id, order_id, paid_amount
)
VALUES
    (201, 101, 70000.00),
    (202, 101, 50000.00),
    (203, 102, 200000.00),
    (204, 103, 80000.00);
```

Cấu trúc dữ liệu quan trọng:

- Đơn **101** có **2 dòng sản phẩm** và **2 lần thanh toán**.
- Đơn **102** có **1 dòng sản phẩm**, **1 lần thanh toán**.
- Đơn **103** có **1 dòng sản phẩm**, **1 lần thanh toán**.
- Đơn **104** có **1 dòng sản phẩm**, **chưa có thanh toán**.
- Khách hàng **Dũng** không có đơn hàng.

Bảng `lesson167_order_items` có 5 dòng; `lesson167_payments` có 4 dòng. Số tiền từng dòng chi tiết khớp với `order_total` trong dữ liệu mô phỏng, nhưng **không nên giả định mọi hệ thống sản xuất luôn có quan hệ khớp này**, do thuế, chiết khấu, hoàn tiền và trạng thái thanh toán.

### 2.3. Đối chiếu trước khi JOIN phức tạp

```sql
SELECT COUNT(*) AS customer_count
FROM lesson167_customers;

SELECT
    COUNT(*) AS order_count,
    SUM(order_total) AS all_order_amount
FROM lesson167_orders;

SELECT COUNT(*) AS item_line_count
FROM lesson167_order_items;

SELECT COUNT(*) AS payment_count
FROM lesson167_payments;
```

Giá trị của bốn phép đếm là **4 khách hàng**, **4 đơn hàng**, **5 dòng chi tiết**, **4 lần thanh toán**; tổng `order_total` của cả 4 đơn là **550.000**. Đây là mốc nghiệp vụ để hiểu những truy vấn `JOIN` tiếp theo.

## 3. JOIN một–nhiều làm tăng số dòng như thế nào?

Bắt đầu bằng việc nối khách hàng với đơn hàng:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_total
FROM lesson167_customers AS c
JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Vì dùng `INNER JOIN`, khách hàng Dũng không có đơn nên **không xuất hiện**. Các dòng kết quả:

| customer_id | customer_name | order_id | order_total |
|---:|---|---:|---:|
| 1 | An | 101 | 120.000 |
| 1 | An | 102 | 200.000 |
| 2 | Bình | 103 | 80.000 |
| 3 | Chi | 104 | 150.000 |

Nếu viết:

```sql
SELECT COUNT(*) AS result_rows
FROM lesson167_customers AS c
JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id;
```

kết quả là **4** — đúng số **dòng sau JOIN** và, trong trường hợp này, cũng bằng số **đơn hàng**, nhưng không phải số khách hàng có đơn.

Đếm số khách hàng đã đặt ít nhất một đơn:

```sql
SELECT
    COUNT(DISTINCT c.customer_id) AS customers_with_orders
FROM lesson167_customers AS c
JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id;
```

Kết quả là **3**: An, Bình, Chi.

**Phân biệt:** `JOIN` không tự biết bạn muốn đếm “bản ghi bên trái” hay “bản ghi bên phải”. Hãy chỉ rõ **khóa của thực thể muốn đếm** và số lượng hàng có thể khớp trong quan hệ.

## 4. COUNT(*), COUNT(column) và COUNT(DISTINCT ...)

Ba cách viết này có ý nghĩa khác nhau:

| Biểu thức | Đếm cái gì? | Xử lý `NULL` |
|---|---|---|
| `COUNT(*)` | Tất cả dòng của tập kết quả | Đếm cả dòng chứa cột `NULL` |
| `COUNT(column)` | Các dòng mà `column` khác `NULL` | Bỏ qua giá trị `NULL` |
| `COUNT(DISTINCT column)` | Các giá trị `column` **khác nhau và khác `NULL`** | Loại trùng và bỏ `NULL` |

### 4.1. LEFT JOIN và “hàng giả” cho thực thể không có quan hệ

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách hàng | joined_rows | order_count |
|---|---:|---:|
| An | 2 | 2 |
| Bình | 1 | 1 |
| Chi | 1 | 1 |
| Dũng | 1 | 0 |

Tại sao Dũng có `joined_rows = 1`? `LEFT JOIN` giữ **một dòng của bảng trái** dù không có bản ghi bên phải khớp, điền các cột bên phải bằng `NULL`. Vì vậy:

- `COUNT(*)` đếm **1 dòng** đó.
- `COUNT(o.order_id)` không đếm vì `o.order_id IS NULL`.

**Quy tắc thực hành:** để đếm số bản ghi con sau `LEFT JOIN` khi chưa phát sinh nhân dòng khác, thường dùng `COUNT(child.primary_key)`, không dùng `COUNT(*)`.

### 4.2. Khi JOIN thêm bảng con, COUNT(column) cũng có thể sai

Nối tiếp với `order_items`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS repeated_order_count,
    COUNT(DISTINCT o.order_id) AS actual_order_count,
    COUNT(i.item_id) AS item_line_count
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Với khách hàng An:

- Đơn 101 có 2 chi tiết, nên `order_id = 101` xuất hiện **2 dòng**.
- Đơn 102 có 1 chi tiết, nên `order_id = 102` xuất hiện **1 dòng**.
- `COUNT(o.order_id) = 3` mặc dù An thực sự chỉ có **2 đơn**.
- `COUNT(DISTINCT o.order_id) = 2`, đúng số đơn.
- `COUNT(i.item_id) = 3`, đúng số dòng chi tiết **trong phép nối này**, vì mỗi `item_id` chỉ xuất hiện một lần khi chưa nối thêm một bảng một–nhiều khác.

Như vậy, `COUNT(column)` chỉ bỏ `NULL`, **không loại các bản sao do JOIN**. `COUNT(DISTINCT entity_id)` là công cụ thường dùng khi cần đếm **thực thể riêng biệt** sau phép nối có thể nhân dòng.

### 4.3. COUNT(DISTINCT) chỉ có ý nghĩa khi chọn đúng khóa

```sql
COUNT(DISTINCT c.customer_id) -- Đếm khách hàng.
COUNT(DISTINCT o.order_id)    -- Đếm đơn hàng.
COUNT(DISTINCT i.item_id)     -- Đếm dòng chi tiết.
COUNT(DISTINCT p.payment_id)  -- Đếm lần thanh toán.
```

Đừng dùng `COUNT(DISTINCT customer_name)` để đếm khách hàng nếu tên có thể trùng; hai người cùng tên vẫn là **hai khách hàng khác nhau**. Tương tự, không đếm đơn hàng theo `order_total` vì nhiều đơn có thể bằng tiền nhau.

Khóa chính/khóa nhận diện nghiệp vụ được thiết kế đúng là cơ sở quan trọng để đếm thực thể.

## 5. JOIN hai bảng một–nhiều có thể tạo tích số dòng

Đây là tình huống dễ làm báo cáo sai nhất: **một đơn hàng có nhiều dòng sản phẩm và nhiều lần thanh toán**.

Xét đơn 101:

| Dòng chi tiết | Thành tiền |
|---|---:|
| 1001 | 60.000 |
| 1002 | 60.000 |

| Thanh toán | Số tiền |
|---|---:|
| 201 | 70.000 |
| 202 | 50.000 |

Nếu nối `orders` với `order_items` rồi nối `payments` **cùng trên `order_id`**, kết quả của đơn 101 là:

```sql
SELECT
    o.order_id,
    i.item_id,
    p.payment_id
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101
ORDER BY i.item_id, p.payment_id;
```

| order_id | item_id | payment_id |
|---:|---:|---:|
| 101 | 1001 | 201 |
| 101 | 1001 | 202 |
| 101 | 1002 | 201 |
| 101 | 1002 | 202 |

Có **2 × 2 = 4 dòng** cho đơn 101. Mỗi dòng chi tiết xuất hiện hai lần (mỗi lần thanh toán một lần), và mỗi giao dịch thanh toán cũng xuất hiện hai lần (mỗi dòng chi tiết một lần).

Đây không phải một phép `CROSS JOIN` độc lập không điều kiện; là kết quả **kết hợp hai quan hệ một–nhiều cùng trỏ về một bản ghi cha**. Trong phạm vi mỗi đơn hàng, các dòng con tạo ra mọi cặp tương ứng, làm **nhân số dòng**.

### 5.1. Phép nhân dòng ảnh hưởng COUNT thế nào?

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(i.item_id) AS repeated_item_rows,
    COUNT(p.payment_id) AS repeated_payment_rows,
    COUNT(DISTINCT i.item_id) AS actual_item_lines,
    COUNT(DISTINCT p.payment_id) AS actual_payments
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101
GROUP BY o.order_id;
```

Kết quả:

| joined_rows | repeated_item_rows | repeated_payment_rows | actual_item_lines | actual_payments |
|---:|---:|---:|---:|---:|
| 4 | 4 | 4 | 2 | 2 |

`COUNT(DISTINCT ...)` giúp **đếm đúng từng thực thể con** khi có khóa duy nhất. Nhưng muốn **cộng số tiền đúng**, phải giải quyết bài toán khác: mỗi số tiền đang nằm ở grain nào?

### 5.2. Số tiền bị nhân theo bảng còn lại

```sql
SELECT
    o.order_id,
    SUM(o.order_total) AS wrong_order_total,
    SUM(i.quantity * i.unit_price) AS wrong_item_total,
    SUM(p.paid_amount) AS wrong_payment_total
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101
GROUP BY o.order_id;
```

Với đơn 101, kết quả từ `JOIN` này là:

| Chỉ số đang tính trên 4 dòng | Giá trị bị nhân |
|---|---:|
| `SUM(o.order_total)` | 480.000 |
| `SUM(i.quantity * i.unit_price)` | 240.000 |
| `SUM(p.paid_amount)` | 240.000 |

Nhưng số liệu ở **bảng gốc** là:

- `order_total` của đơn 101 = **120.000** (một giá trị trên **một đơn**).
- Tổng chi tiết của đơn 101 = **120.000** (60.000 + 60.000).
- Tổng thanh toán = **120.000** (70.000 + 50.000).

Vì `JOIN` có 4 dòng, `o.order_total` bị cộng 4 lần; mỗi dòng chi tiết được nhân bởi 2 thanh toán; mỗi thanh toán bị nhân bởi 2 dòng chi tiết.

**Nguyên tắc:** một phép tổng hợp như `SUM` **không tự biết các dòng nào chỉ là bản sao sinh ra bởi JOIN**. Nó cộng những giá trị xuất hiện trong tập dòng đưa tới hàm.

## 6. Ví dụ sai số liệu khi tổng hợp theo khách hàng

Khi nối cả bốn bảng rồi `GROUP BY` khách hàng:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS repeated_order_rows,
    COUNT(DISTINCT o.order_id) AS distinct_orders,
    COALESCE(SUM(o.order_total), 0) AS wrong_order_sum,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS wrong_item_sum,
    COALESCE(SUM(p.paid_amount), 0) AS wrong_payment_sum
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Với khách hàng **An**, số dòng sau nối gồm:

- Đơn 101: **4 dòng** do 2 chi tiết × 2 thanh toán.
- Đơn 102: **1 dòng** do 1 chi tiết × 1 thanh toán.
- Tổng: **5 dòng** nhưng chỉ có **2 đơn**.

Do đó đối với An:

| Chỉ số | Kết quả truy vấn trên | Giá trị đúng theo bảng gốc |
|---|---:|---:|
| Dòng sau JOIN | 5 | 5 dòng là đúng theo cấu trúc JOIN |
| `COUNT(o.order_id)` | 5 | 2 đơn |
| `COUNT(DISTINCT o.order_id)` | 2 | 2 đơn |
| `SUM(o.order_total)` | 680.000 | 320.000 |
| `SUM(i.quantity * i.unit_price)` | 440.000 | 320.000 |
| `SUM(p.paid_amount)` | 440.000 | 320.000 |

Cụ thể, `SUM(o.order_total)` tính `120.000 × 4 + 200.000 = 680.000`. **`COUNT(DISTINCT o.order_id)` sửa được số đơn, nhưng không tự sửa được các phép `SUM` đang nhân đôi.**

Với khách hàng **Chi** (đơn 104 chưa có thanh toán), `LEFT JOIN` vẫn giữ một dòng có cột thanh toán `NULL`. Vì vậy `SUM(p.paid_amount)` trước `COALESCE` là `NULL`; sau `COALESCE(...,0)` là 0. Điều này cần được hiểu theo **quy tắc báo cáo**, không nhầm với việc thực sự có một lần thanh toán bằng 0.

## 7. Vì sao SUM(DISTINCT amount) không phải thuốc chữa nhân đôi?

Một cách sửa tưởng chừng hợp lý là:

```sql
SUM(DISTINCT o.order_total)
```

Nhưng `DISTINCT` trong `SUM(DISTINCT expression)` loại **các giá trị số trùng nhau**, không loại theo **khóa đơn hàng**. Nếu hai đơn khác nhau có cùng tổng tiền, nó chỉ tính giá trị đó một lần.

Ví dụ độc lập:

```sql
WITH sample_orders (order_id, amount) AS (
    VALUES
        (1, 100000::NUMERIC),
        (2, 100000::NUMERIC),
        (3, 200000::NUMERIC)
)
SELECT
    SUM(amount) AS correct_total,
    SUM(DISTINCT amount) AS incorrect_distinct_total
FROM sample_orders;
```

Kết quả:

| correct_total | incorrect_distinct_total |
|---:|---:|
| 400.000 | 300.000 |

Cả đơn 1 và đơn 2 đều có giá trị 100.000, nhưng là **hai đơn hàng hợp lệ cần cộng cả hai**. `SUM(DISTINCT amount)` không hiểu khóa `order_id`, nên làm mất một khoản 100.000.

Tương tự, `SELECT DISTINCT` ở phía ngoài một truy vấn tổng hợp **không thể đảo ngược việc số tiền đã bị cộng lặp bên trong `SUM`**. Nó chỉ loại các dòng kết quả trùng nhau sau khi giá trị tổng đã được tính.

**Bài học chính:** `COUNT(DISTINCT entity_id)` là một công cụ hợp lý để **đếm thực thể**; **`SUM(DISTINCT amount)` không phải giải pháp tổng quát để cộng đúng theo thực thể**.

## 8. Cách đúng thứ nhất: tổng hợp ở cấp bảng nguồn trước khi JOIN

Nếu muốn **số đơn và tổng `order_total` theo khách hàng**, cách đơn giản nhất là chỉ nối những bảng cần thiết, rồi tổng hợp từ `orders` — nơi mỗi đơn chỉ xuất hiện một lần:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.order_total), 0) AS order_amount
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách hàng | order_count | order_amount |
|---|---:|---:|
| An | 2 | 320.000 |
| Bình | 1 | 80.000 |
| Chi | 1 | 150.000 |
| Dũng | 0 | 0 |

Vì **chưa nối các bảng con khác**, mỗi đơn của khách hàng xuất hiện đúng một lần. `COUNT(o.order_id)` và `SUM(o.order_total)` đều hợp với grain đầu vào.

Chỉ nối `order_items` nếu truy vấn **thực sự cần dữ liệu chi tiết**; chỉ nối `payments` nếu thực sự cần thông tin thanh toán. Giảm số bảng tham gia không chỉ dễ giữ số liệu đúng mà còn có thể tiết kiệm công xử lý.

### 8.1. Tổng hợp theo customer_id trước khi nối thông tin khách hàng

Có thể tổng hợp `orders` trước, rồi mới nối với `customers`:

```sql
WITH orders_by_customer AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(order_total) AS order_amount
    FROM lesson167_orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(o.order_count, 0) AS order_count,
    COALESCE(o.order_amount, 0) AS order_amount
FROM lesson167_customers AS c
LEFT JOIN orders_by_customer AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Ở đây, `orders_by_customer` có **đúng một dòng trên một `customer_id`**; khi `LEFT JOIN` vào khách hàng, sẽ không nhân số dòng nếu dữ liệu và khóa được xây dựng như dự kiến.

Đây là kỹ thuật **tiền tổng hợp**: biến nguồn nhiều dòng thành kết quả **một dòng theo khóa sẽ JOIN**, sau đó mới ghép vào bảng khác.

## 9. Cách đúng thứ hai: tiền tổng hợp từng bảng con theo khóa đơn hàng

Khi cần trả đồng thời:

- Số đơn hàng và tổng tiền theo đơn.
- Số dòng chi tiết và tổng giá trị chi tiết.
- Số lần thanh toán và tổng tiền đã thanh toán.

Ta không nên nối **hai bảng một–nhiều** ở mức dòng gốc rồi cộng ngay. Hãy tổng hợp **từng bảng con về một dòng trên một đơn hàng** trước.

### 9.1. Tổng hợp order_items và payments riêng

```sql
WITH items_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_amount
    FROM lesson167_order_items
    GROUP BY order_id
),
payments_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(paid_amount) AS paid_amount
    FROM lesson167_payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_total,
    COALESCE(i.item_line_count, 0) AS item_line_count,
    COALESCE(i.item_amount, 0) AS item_amount,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.paid_amount, 0) AS paid_amount
FROM lesson167_orders AS o
LEFT JOIN items_by_order AS i
    ON i.order_id = o.order_id
LEFT JOIN payments_by_order AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Sau hai CTE:

- `items_by_order` có **tối đa một dòng cho một `order_id`**.
- `payments_by_order` cũng có **tối đa một dòng cho một `order_id`**.
- Khi nối với `orders`, mỗi đơn vẫn là **một dòng**.

Kết quả:

| Đơn | order_total | item_line_count | item_amount | payment_count | paid_amount |
|---:|---:|---:|---:|---:|---:|
| 101 | 120.000 | 2 | 120.000 | 2 | 120.000 |
| 102 | 200.000 | 1 | 200.000 | 1 | 200.000 |
| 103 | 80.000 | 1 | 80.000 | 1 | 80.000 |
| 104 | 150.000 | 1 | 150.000 | 0 | 0 |

### 9.2. Tổng hợp tiếp theo khách hàng mà không nhân số liệu

Nếu báo cáo cần một dòng trên một khách hàng, tiếp tục nhóm kết quả **một dòng trên một đơn**:

```sql
WITH items_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_amount
    FROM lesson167_order_items
    GROUP BY order_id
),
payments_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(paid_amount) AS paid_amount
    FROM lesson167_payments
    GROUP BY order_id
),
orders_enriched AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_total,
        COALESCE(i.item_line_count, 0) AS item_line_count,
        COALESCE(i.item_amount, 0) AS item_amount,
        COALESCE(p.payment_count, 0) AS payment_count,
        COALESCE(p.paid_amount, 0) AS paid_amount
    FROM lesson167_orders AS o
    LEFT JOIN items_by_order AS i
        ON i.order_id = o.order_id
    LEFT JOIN payments_by_order AS p
        ON p.order_id = o.order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(e.order_id) AS order_count,
    COALESCE(SUM(e.order_total), 0) AS order_amount,
    COALESCE(SUM(e.item_line_count), 0) AS item_line_count,
    COALESCE(SUM(e.item_amount), 0) AS item_amount,
    COALESCE(SUM(e.payment_count), 0) AS payment_count,
    COALESCE(SUM(e.paid_amount), 0) AS paid_amount
FROM lesson167_customers AS c
LEFT JOIN orders_enriched AS e
    ON e.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Lúc này báo cáo cho An có:

- `order_count = 2`.
- `order_amount = 320000`.
- `item_line_count = 3`.
- `item_amount = 320000`.
- `payment_count = 3`.
- `paid_amount = 320000`.

Khách hàng Dũng vẫn có dòng báo cáo với các chỉ số bằng 0 do `LEFT JOIN` và `COALESCE`. Đây là kết quả đúng theo **quy tắc hiển thị báo cáo mẫu**; trong hệ thống khác, cần xác định liệu số liệu không có dữ liệu nên hiện 0 hay `NULL`.

### 9.3. Grain thay đổi có chủ đích qua từng bước

```text
order_items (một dòng / item_id)
          │
          ▼ GROUP BY order_id
items_by_order (một dòng / order_id)
          │
          ├─────┐
          │     │
payments (một dòng / payment_id)
          │     │
          ▼ GROUP BY order_id
payments_by_order (một dòng / order_id)
          │     │
          └──┬──┘
             ▼ JOIN với orders
orders_enriched (một dòng / order_id)
             │
             ▼ GROUP BY customer_id
customer_summary (một dòng / customer_id)
```

**Điểm quyết định không phải CTE hay bảng tạm, mà là đảm bảo kết quả của mỗi bảng con có grain phù hợp trước khi JOIN.** CTE là cách viết dễ đọc; cùng chiến lược có thể dùng truy vấn con hoặc bảng tạm được quản lý rõ ràng.

## 10. Cách đúng thứ ba: dùng EXISTS khi chỉ cần biết có quan hệ hay không

Nếu câu hỏi là “Có bao nhiêu khách hàng đã từng đặt ít nhất một đơn?”, không nhất thiết phải nối tất cả đơn vào khách hàng.

Một giải pháp với `EXISTS`:

```sql
SELECT COUNT(*) AS customers_with_orders
FROM lesson167_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson167_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Kết quả: **3**.

`EXISTS` trả đúng/sai theo việc truy vấn con có **ít nhất một dòng**. Nó không sinh một dòng mới cho mỗi đơn của khách hàng, nên không làm nhân khách hàng trong tập ngoài.

Để liệt kê những khách hàng có đơn:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson167_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson167_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Truy vấn trả **An, Bình, Chi** mỗi người một lần.

### 10.1. Tìm khách hàng chưa từng đặt đơn với NOT EXISTS

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson167_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson167_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Kết quả là **Dũng**.

`NOT EXISTS` thường biểu đạt rõ ý định “không có bản ghi con phù hợp”. Với các cột khóa có thể chứa `NULL`, cách viết `NOT IN` có thể chịu ảnh hưởng của logic ba giá trị và cho kết quả bất ngờ; `NOT EXISTS` thường dễ dùng hơn để kiểm tra sự vắng mặt của bản ghi liên quan.

### 10.2. Khi nào EXISTS không thay thế JOIN?

Nếu cần:

- Tổng tiền các đơn.
- Tên từng sản phẩm trong các đơn.
- Số giao dịch thanh toán.
- Các cột cụ thể từ bảng liên quan.

thì `EXISTS` đơn thuần không trả những số liệu đó. Nó phù hợp khi mục tiêu là **lọc một thực thể theo sự tồn tại của thực thể khác**, không phải thay thế mọi phép nối.

## 11. Đếm có điều kiện sau JOIN

Nhu cầu: đếm số **đơn CONFIRMED** và **NEW** của mỗi khách hàng, kể cả người chưa có đơn.

Vì bảng `lesson167_orders` có **mỗi đơn một dòng**, có thể nhóm trực tiếp:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS all_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'CONFIRMED'
    ) AS confirmed_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'NEW'
    ) AS new_orders
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

`FILTER (WHERE ...)` là cú pháp PostgreSQL (và các DBMS có hỗ trợ tương ứng) để lọc đầu vào của một hàm tổng hợp.

Kết quả:

| Khách hàng | all_orders | confirmed_orders | new_orders |
|---|---:|---:|---:|
| An | 2 | 2 | 0 |
| Bình | 1 | 0 | 1 |
| Chi | 1 | 1 | 0 |
| Dũng | 0 | 0 | 0 |

### 11.1. Viết bằng CASE để phù hợp nhiều DBMS

```sql
SELECT
    c.customer_id,
    c.customer_name,
    SUM(
        CASE
            WHEN o.order_status = 'CONFIRMED' THEN 1
            ELSE 0
        END
    ) AS confirmed_orders
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Với **một dòng trên một đơn**, `SUM(CASE ... THEN 1 ELSE 0 END)` đếm được số đơn đã xác nhận. Nhưng nếu nối thêm `order_items` và `payments` trước phép `SUM`, mỗi đơn có thể xuất hiện nhiều lần; khi ấy `SUM(CASE...)` **lại bị nhân dòng**.

Một cách đếm đơn duy nhất sau JOIN nhiều bảng con là:

```sql
COUNT(DISTINCT CASE
    WHEN o.order_status = 'CONFIRMED' THEN o.order_id
END)
```

Nó đếm **mã đơn đã xác nhận khác nhau**, không phải số dòng. Trong PostgreSQL cũng có thể viết `COUNT(DISTINCT o.order_id) FILTER (WHERE o.order_status = 'CONFIRMED')`.

**Với các chỉ số bằng tiền, vẫn phải tổng hợp theo grain thích hợp**; không dùng `SUM(DISTINCT order_total)` như cách sửa chung.

### 11.2. COUNT(CASE ... ELSE 0 END) có thể đếm nhầm

```sql
COUNT(
    CASE
        WHEN o.order_status = 'CONFIRMED' THEN 1
        ELSE 0
    END
)
```

`COUNT(expression)` đếm mọi giá trị **khác `NULL`**; cả 1 và 0 đều khác `NULL`. Vì vậy, câu trên đếm **mọi dòng**, kể cả những đơn không `CONFIRMED` và dòng giữ lại của `LEFT JOIN`.

Khi dùng `COUNT` có điều kiện, mẫu thích hợp hơn:

```sql
COUNT(
    CASE
        WHEN o.order_status = 'CONFIRMED' THEN o.order_id
    END
)
```

Nhưng nhớ: nếu cùng một `order_id` xuất hiện nhiều lần sau JOIN, mẫu đó **vẫn đếm lặp**. Khi cần số đơn duy nhất, dùng `DISTINCT` với đúng khóa đơn hoặc đổi chiến lược tổng hợp.

## 12. Đặt điều kiện WHERE hay ON với LEFT JOIN

Một nguyên nhân khác khiến báo cáo “mất khách hàng” là vị trí điều kiện lọc trên bảng bên phải của `LEFT JOIN`.

Giả sử muốn **hiển thị tất cả khách hàng** và đếm riêng các đơn `CONFIRMED`.

### 12.1. Đặt điều kiện trong ON để giữ khách hàng không khớp

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS confirmed_orders
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách hàng | confirmed_orders |
|---|---:|
| An | 2 |
| Bình | 0 |
| Chi | 1 |
| Dũng | 0 |

Điều kiện `o.order_status = 'CONFIRMED'` nằm trong `ON` nghĩa là **chỉ các đơn CONFIRMED được xem là khớp**, nhưng khách hàng không có đơn phù hợp vẫn được `LEFT JOIN` giữ lại.

### 12.2. Đưa điều kiện sang WHERE có thể bỏ mất khách hàng

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS confirmed_orders
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Lúc này **Bình** (chỉ có đơn `NEW`) và **Dũng** (không có đơn) bị loại khỏi tập kết quả. Vì `WHERE` lọc sau `JOIN`, những dòng có `o.order_status` không đúng hoặc `NULL` không được giữ lại.

Không phải câu thứ hai luôn sai: nếu yêu cầu là **chỉ liệt kê khách hàng có đơn CONFIRMED**, nó có thể phù hợp. Nhưng nếu yêu cầu là **tất cả khách hàng, kể cả số đơn bằng 0**, phải bảo toàn các dòng không khớp, chẳng hạn bằng điều kiện trong `ON` hoặc dùng tiền tổng hợp.

### 12.3. Chọn điều kiện lọc đúng cấp dữ liệu

Nếu muốn tổng số đơn năm 2026 và cả các khách hàng chưa có đơn, nên lọc thời gian của bảng đơn trong `ON` (hoặc trong CTE trước `LEFT JOIN`), thay vì lọc bảng bên phải ở `WHERE` làm mất các khách hàng không có đơn.

Ví dụ giả định có thêm cột `created_at` trong `lesson167_orders`:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS orders_in_period
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
   AND o.created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
   AND o.created_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
GROUP BY c.customer_id;
```

**Đây là truy vấn minh họa thiết kế**, không chạy trực tiếp với bảng mẫu vì bảng mẫu chưa có cột `created_at`. Nó thể hiện mục tiêu **giữ đủ khách hàng** và chỉ tính các đơn trong khoảng thời gian chọn.

## 13. Đếm theo nhiều cột và xử lý dữ liệu có thể trùng khóa

`COUNT(DISTINCT order_id)` hoạt động tốt nếu `order_id` là định danh toàn cục duy nhất. Một số hệ thống lại dùng **khóa ghép**, chẳng hạn một mã hóa đơn chỉ duy nhất **trong từng cửa hàng**:

```text
store_id | invoice_number
---------+---------------
10       | 1001
10       | 1002
20       | 1001
```

Nếu dùng `COUNT(DISTINCT invoice_number)` trên toàn hệ thống, bạn chỉ được **2**, trong khi thực tế có **3 hóa đơn**.

Trong PostgreSQL, có thể đếm các cặp duy nhất bằng row expression:

```sql
WITH invoices (store_id, invoice_number) AS (
    VALUES (10, 1001), (10, 1002), (20, 1001)
)
SELECT
    COUNT(DISTINCT (store_id, invoice_number)) AS invoice_count
FROM invoices;
```

Kết quả là **3**.

Nếu muốn cách diễn đạt tương thích tốt hơn giữa các DBMS, hãy tạo tập **cặp khóa duy nhất** trước rồi đếm:

```sql
WITH invoices (store_id, invoice_number) AS (
    VALUES (10, 1001), (10, 1002), (20, 1001)
),
unique_invoices AS (
    SELECT DISTINCT store_id, invoice_number
    FROM invoices
)
SELECT COUNT(*) AS invoice_count
FROM unique_invoices;
```

Chú ý **cú pháp `COUNT(DISTINCT a, b)`, biểu thức hàng và xử lý `NULL` trong khóa ghép khác nhau giữa DBMS**. Khi khóa nhận diện thực thể có nhiều cột, hãy xác định rõ tính duy nhất và giá trị `NULL` được cho phép hay không, tránh tự ghép hai trường thành chuỗi đơn giản vì có thể gây va chạm, ví dụ `(1, 23)` và `(12, 3)` nếu nối chuỗi không có phân tách an toàn.

## 14. JOIN sai điều kiện cũng tạo thêm dòng

Không phải mọi dòng nhân lên đều do quan hệ một–nhiều hợp lệ. Hai vấn đề khác:

### 14.1. Nối trên cột không duy nhất

Giả sử hai bảng đều có cột `customer_name`, nhưng tên không duy nhất. Nếu `JOIN` bằng tên thay vì `customer_id`, một khách hàng có thể ghép với **nhiều người trùng tên**.

```sql
-- Không nên nếu customer_name không phải khóa duy nhất phù hợp.
SELECT *
FROM lesson167_orders AS o
JOIN lesson167_customers AS c
    ON c.customer_name = 'An';
```

Đoạn minh họa này còn thiếu điều kiện liên hệ `o.customer_id = c.customer_id`, nên mọi đơn có thể ghép với khách hàng tên An — một dạng nối sai nghiệp vụ, có thể tạo nhiều dòng và sai số liệu.

Đúng:

```sql
SELECT
    o.order_id,
    c.customer_name
FROM lesson167_orders AS o
JOIN lesson167_customers AS c
    ON c.customer_id = o.customer_id;
```

### 14.2. Quên một phần khóa ghép

Nếu khóa bảng chi tiết là `(store_id, order_id)` nhưng truy vấn chỉ nối bằng `order_id`, đơn có cùng mã ở nhiều cửa hàng có thể bị ghép chéo.

Mẫu nguyên tắc:

```sql
-- Giả định cả hai bảng có store_id và order_id.
JOIN order_items AS i
    ON i.store_id = o.store_id
   AND i.order_id = o.order_id
```

Phải dùng đủ các cột mô tả quan hệ. `COUNT(DISTINCT ...)` không phải cách thay thế cho **điều kiện JOIN đúng**. Nếu nối sai, kết quả có thể không chỉ bị nhân dòng mà còn **liên kết sai thực thể**.

## 15. Cách chẩn đoán một truy vấn báo cáo nghi ngờ nhân đôi

Trước khi sửa bằng `DISTINCT`, hãy xác định nơi row fanout xuất hiện.

### Bước 1: Ghi rõ grain mong muốn của kết quả

Ví dụ: “Mỗi dòng báo cáo là **một khách hàng**”, hoặc “mỗi dòng là **một đơn hàng**”.

Tập kết quả cần có khóa nhận diện ở grain đó. Nếu cần một dòng trên `order_id`, hãy kiểm tra truy vấn có thật sự tạo tối đa một dòng cho mỗi `order_id` trước khi tổng hợp.

### Bước 2: Xem từng JOIN thêm bao nhiêu dòng

```sql
-- Một đơn có một dòng trong bảng nguồn.
SELECT COUNT(*) AS base_orders
FROM lesson167_orders;

-- Sau khi nối với chi tiết.
SELECT COUNT(*) AS order_item_rows
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id;

-- Sau khi nối thêm thanh toán.
SELECT COUNT(*) AS order_item_payment_rows
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id;
```

Với dữ liệu mẫu:

- Bảng `orders` có **4 dòng**.
- Sau `LEFT JOIN order_items` có **5 dòng**.
- Sau `LEFT JOIN payments` có **7 dòng**: đơn 101 tạo 4 dòng; 102, 103, 104 mỗi đơn 1 dòng.

Nếu nối thêm `customers` ở phía trái, giữ cả Dũng không có đơn, tổng dòng sau phép nối đầy đủ sẽ là **8**. Việc đo **từng bước** giúp xác định nơi số liệu bắt đầu tăng.

### Bước 3: So sánh số dòng và số khóa duy nhất theo từng nhóm

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT i.item_id) AS distinct_items,
    COUNT(DISTINCT p.payment_id) AS distinct_payments
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY joined_rows DESC, o.order_id;
```

Đơn 101 có `joined_rows = 4`, `distinct_items = 2`, `distinct_payments = 2`. Những đơn có số dòng sau `JOIN` cao bất thường là nơi nên kiểm tra quan hệ và điều kiện nối.

### Bước 4: Xem cột nào đang bị lặp trước SUM

```sql
SELECT
    o.order_id,
    o.order_total,
    i.item_id,
    i.quantity * i.unit_price AS item_line_amount,
    p.payment_id,
    p.paid_amount
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101
ORDER BY i.item_id, p.payment_id;
```

Nếu `order_total` xuất hiện bốn lần và bị `SUM` bốn lần, nguyên nhân đã rõ: **grain của giá trị là một đơn, nhưng grain của dòng đầu vào hàm tổng hợp đã trở thành một cặp item–payment**.

### Bước 5: Sửa theo grain thay vì chỉ che dấu kết quả

Một trong các cách sửa:

- Bỏ những `JOIN` không cần thiết.
- Dùng `EXISTS` nếu chỉ cần kiểm tra có bản ghi liên quan.
- Tiền tổng hợp các bảng con theo khóa chung trước `JOIN`.
- Dùng `COUNT(DISTINCT entity_key)` nếu thực sự cần đếm số thực thể duy nhất sau nối.
- Sửa điều kiện nối thiếu khóa hoặc nối nhầm cột.

### Bước 6: Đối chiếu số liệu với các bảng gốc

```sql
SELECT SUM(order_total) AS expected_order_amount
FROM lesson167_orders;
```

Kết quả 550.000 là tổng theo bảng `orders`. Nếu báo cáo sau `JOIN` cho tổng khác dù không có điều kiện lọc thêm, cần xem logic có đang thay đổi tập đơn hoặc nhân giá trị hay không.

**Đối chiếu phải dựa trên cùng điều kiện nghiệp vụ.** Nếu một báo cáo chỉ tính đơn `CONFIRMED`, hãy đối chiếu với tổng đơn `CONFIRMED` trong bảng nguồn; không so trực tiếp với tổng mọi trạng thái rồi kết luận báo cáo sai.

## 16. COUNT(DISTINCT) có luôn là lựa chọn tốt nhất?

Không. `COUNT(DISTINCT ...)` rất hữu ích khi cần số thực thể duy nhất trên tập dòng đã nối, nhưng có giới hạn:

1. Nó **không sửa các phép tổng hợp khác** như `SUM(amount)` hoặc `AVG(amount)`.
2. Phải chọn **đúng định danh**. Đếm tên, trạng thái hoặc tiền không tương đương đếm thực thể.
3. Với dữ liệu lớn, việc loại trùng có thể cần sắp xếp hoặc bảng băm, tiêu tốn bộ nhớ và tài nguyên.
4. Nếu điều kiện `JOIN` sai, `COUNT(DISTINCT ...)` có thể che bớt số dòng lặp mà không sửa được quan hệ dữ liệu sai.
5. Nếu grain kết quả đã đúng ngay từ đầu, dùng `COUNT(*)` hoặc `COUNT(child_id)` đơn giản và thường rõ ràng hơn.

Ví dụ: nếu chỉ cần đếm đơn theo khách hàng, hãy dùng `orders GROUP BY customer_id` thay vì nối mọi chi tiết sản phẩm, mọi thanh toán rồi mới `COUNT(DISTINCT order_id)`.

### 16.1. Tổng hợp trước JOIN có giúp hiệu năng không?

Tiền tổng hợp có thể giảm mạnh số dòng cần nối. Ví dụ hai bảng con có hàng nghìn dòng cho mỗi đơn có thể sinh số cặp lớn, trong khi tổng hợp trước cho mỗi bảng con về **một dòng trên một đơn** sẽ tránh phép nhân không cần thiết.

Tuy nhiên:

- CTE/truy vấn con không phải lúc nào cũng được vật hóa thành bảng tạm; bộ tối ưu hóa có thể biến đổi kế hoạch.
- Tập dữ liệu, thống kê, chỉ mục và điều kiện lọc quyết định hiệu năng.
- Nhiều phép `GROUP BY` cũng có chi phí riêng.

Trong PostgreSQL, có thể xem kế hoạch truy vấn bằng `EXPLAIN`:

```sql
EXPLAIN
SELECT
    o.customer_id,
    COUNT(*) AS order_count
FROM lesson167_orders AS o
GROUP BY o.customer_id;
```

Khi dùng `EXPLAIN ANALYZE`, truy vấn được **thực thi thật**; chỉ sử dụng trong môi trường và tác vụ phù hợp. Mục tiêu đầu tiên luôn là **số liệu đúng**, sau đó mới tối ưu hiệu năng.

## 17. Những sai lầm thường gặp

### Lỗi 1: Dùng COUNT(*) sau LEFT JOIN để đếm bản ghi con

```sql
SELECT
    c.customer_id,
    COUNT(*) AS wrong_order_count
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Khách hàng không có đơn vẫn được đếm là 1. Dùng `COUNT(o.order_id)` khi mỗi đơn chỉ xuất hiện một lần, hoặc `COUNT(DISTINCT o.order_id)` khi đã nối thêm quan hệ có thể nhân dòng.

### Lỗi 2: Lấy COUNT(order_id) làm số đơn sau khi nối chi tiết

Sau `JOIN order_items`, một `order_id` xuất hiện theo số dòng chi tiết. `COUNT(o.order_id)` trở thành **số dòng chứa mã đơn**, không phải số đơn duy nhất.

### Lỗi 3: Dùng SUM(DISTINCT amount) để chống nhân đôi

Hai đơn khác nhau có thể có cùng tổng tiền. `SUM(DISTINCT amount)` loại theo **giá trị**, làm mất khoản tiền hợp lệ. Phải tổng hợp tại grain **một dòng trên một đơn**, hoặc sử dụng thiết kế đảm bảo giá trị được cộng đúng một lần theo khóa.

### Lỗi 4: JOIN đồng thời hai bảng con một–nhiều rồi SUM trực tiếp

```sql
SELECT
    o.order_id,
    SUM(i.quantity * i.unit_price) AS items_total,
    SUM(p.paid_amount) AS payments_total
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Đơn 101 cho hai tổng bị nhân. Giải pháp là **tiền tổng hợp items và payments riêng theo `order_id`**, rồi mới nối vào `orders`.

### Lỗi 5: Đặt điều kiện bảng phải trong WHERE rồi làm mất hàng LEFT JOIN

`WHERE o.order_status = 'CONFIRMED'` bỏ khách hàng không có đơn phù hợp. Nếu cần giữ mọi khách hàng, đặt điều kiện vào `ON` hoặc tiền tổng hợp các đơn đủ điều kiện rồi `LEFT JOIN`.

### Lỗi 6: COUNT(DISTINCT name) thay cho COUNT(DISTINCT id)

Tên có thể trùng hoặc thay đổi. Dùng khóa nhận diện thực thể đúng, ví dụ `customer_id`.

### Lỗi 7: Dùng COUNT(CASE ... ELSE 0 END) để đếm nhánh TRUE

`COUNT` đếm cả giá trị 0 vì 0 không phải `NULL`. Dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` nếu grain từng dòng đúng, hoặc `COUNT(DISTINCT CASE WHEN ... THEN entity_id END)` nếu cần chống đếm lặp thực thể.

### Lỗi 8: Dùng DISTINCT cuối SELECT để “chữa” tổng tiền

Nếu `SUM` đã cộng mỗi giá trị nhiều lần, `SELECT DISTINCT` ở ngoài không thay đổi cách `SUM` thực hiện trước đó.

### Lỗi 9: Không dùng đủ thành phần khóa trong JOIN

Nếu bảng có khóa ghép hoặc khóa ngoại ghép, điều kiện nối thiếu cột có thể tạo cặp sai và nhân dòng. Không để `DISTINCT` che một điều kiện `ON` thiếu khóa.

### Lỗi 10: Không xác định phạm vi của chỉ số

“Doanh thu theo khách hàng” có thể là tổng giá trị đơn, tổng số tiền đã thanh toán, tổng tiền sau hoàn, hoặc giá trị sản phẩm theo dòng. Mỗi chỉ số có **nguồn dữ liệu và grain riêng**. Trước khi viết `SUM`, xác định chính xác đang cộng đại lượng nào.

## 18. Bài tập thực hành có lời giải

Các bài sử dụng những bảng `lesson167_...` đã tạo ở phần 2. Hãy tự dự đoán kết quả và kiểm tra bằng câu SQL trên database thực hành.

### Bài 1. Đếm khách hàng và đơn hàng

**Yêu cầu:** trả về số khách hàng trong bảng và số đơn hàng trong bảng, không cần nối các bảng.

```sql
SELECT
    (SELECT COUNT(*) FROM lesson167_customers)
        AS customer_count,
    (SELECT COUNT(*) FROM lesson167_orders)
        AS order_count;
```

**Đáp án:** 4 khách hàng, 4 đơn. Khi câu hỏi chỉ cần số dòng ở mỗi bảng và khóa chính đại diện một thực thể, không cần `JOIN`.

### Bài 2. Vì sao khách hàng Dũng có COUNT(*) bằng 1?

```sql
SELECT
    c.customer_id,
    COUNT(*) AS row_count,
    COUNT(o.order_id) AS order_count
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 4
GROUP BY c.customer_id;
```

**Đáp án:** `row_count = 1`, `order_count = 0`. `LEFT JOIN` giữ một dòng của Dũng dù không có đơn; `order_id` của dòng đó là `NULL` nên `COUNT(o.order_id)` không đếm.

### Bài 3. Đếm số đơn sau JOIN với chi tiết

**Yêu cầu:** lấy số đơn **duy nhất** theo khách hàng sau khi đã nối với `order_items`.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(DISTINCT o.order_id) AS order_count
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

**Đáp án:** An 2, Bình 1, Chi 1, Dũng 0. `DISTINCT` đặt trên `order_id` chứ không phải trên tên khách hàng hoặc số tiền.

### Bài 4. Dự đoán số dòng của đơn 101 sau hai JOIN

```sql
SELECT COUNT(*) AS joined_rows
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101;
```

**Đáp án:** **4 dòng** = 2 chi tiết × 2 thanh toán.

### Bài 5. Tính đúng tổng tiền đơn theo khách hàng

**Yêu cầu:** liệt kê đủ cả khách hàng chưa có đơn.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.order_total), 0) AS total_amount
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

**Đáp án:** An 320.000; Bình 80.000; Chi 150.000; Dũng 0. Mỗi đơn được cộng đúng một lần vì chưa thêm hai bảng một–nhiều khác.

### Bài 6. Vì sao SUM(DISTINCT order_total) không đáng tin?

```sql
WITH t (order_id, amount) AS (
    VALUES (1, 50000), (2, 50000), (3, 100000)
)
SELECT
    SUM(amount) AS actual_amount,
    SUM(DISTINCT amount) AS distinct_amount
FROM t;
```

**Đáp án:** `actual_amount = 200000` nhưng `distinct_amount = 150000`. Hai đơn 1 và 2 cùng 50.000 nhưng phải được cộng **hai lần**, vì đó là **hai thực thể khác nhau**.

### Bài 7. Đếm khách hàng có đơn CONFIRMED mà không sinh dòng lặp

```sql
SELECT COUNT(*) AS customers_with_confirmed_orders
FROM lesson167_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson167_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'CONFIRMED'
);
```

**Đáp án:** **2 khách hàng**, gồm An và Chi. `EXISTS` kiểm tra sự tồn tại, không nhân khách hàng theo số đơn.

### Bài 8. Đếm số đơn CONFIRMED của mọi khách hàng

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS confirmed_order_count
FROM lesson167_customers AS c
LEFT JOIN lesson167_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** theo `customer_id` 1, 2, 3, 4 lần lượt là **2, 0, 1, 0**. Đặt điều kiện trong `ON` để giữ khách hàng không có đơn phù hợp.

### Bài 9. Đếm thanh toán đúng khi JOIN cùng chi tiết

**Yêu cầu:** lấy số giao dịch thanh toán trên mỗi đơn, ngay cả khi đơn có nhiều dòng sản phẩm.

```sql
SELECT
    o.order_id,
    COUNT(DISTINCT p.payment_id) AS payment_count
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

**Đáp án:** đơn 101 có 2; 102 có 1; 103 có 1; 104 có 0. `DISTINCT` trên `payment_id` loại bản sao do việc nối thêm `order_items`.

### Bài 10. Tổng tiền thanh toán của đơn 101

**Yêu cầu:** tính đúng tổng các lần thanh toán, không bị nhân bởi dòng chi tiết.

```sql
SELECT
    o.order_id,
    COALESCE(p.total_paid, 0) AS total_paid
FROM lesson167_orders AS o
LEFT JOIN (
    SELECT
        order_id,
        SUM(paid_amount) AS total_paid
    FROM lesson167_payments
    GROUP BY order_id
) AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 101;
```

**Đáp án:** **120.000**, vì bảng thanh toán được tổng hợp thành một dòng trên một đơn trước khi nối. Không cần nối `order_items` cho bài toán này.

### Bài 11. Kiểm tra mức độ nhân dòng

**Yêu cầu:** tìm các đơn có nhiều dòng hơn số dòng chi tiết sau khi nối cả chi tiết và thanh toán.

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT i.item_id) AS item_lines,
    COUNT(DISTINCT p.payment_id) AS payments
FROM lesson167_orders AS o
LEFT JOIN lesson167_order_items AS i
    ON i.order_id = o.order_id
LEFT JOIN lesson167_payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
HAVING COUNT(*) > COUNT(DISTINCT i.item_id)
ORDER BY o.order_id;
```

**Đáp án với dữ liệu mẫu:** chỉ đơn **101** có `joined_rows = 4` lớn hơn `item_lines = 2`. Lưu ý: tiêu chí `HAVING` này chỉ giúp quan sát fanout trong ví dụ, không phải một quy tắc tổng quát để phát hiện mọi loại nối sai, nhất là khi bảng con không có dòng hoặc nguồn có quan hệ phức tạp khác.

### Bài 12. Chọn chiến lược truy vấn

Chọn cách làm hợp lý nhất cho mỗi yêu cầu:

1. Đếm số khách hàng có ít nhất một đơn.
2. Tổng giá trị đơn hàng theo khách hàng.
3. Tổng số tiền thanh toán và tổng giá trị dòng chi tiết theo từng đơn.
4. Đếm số đơn duy nhất trên một tập kết quả đã nối nhiều bảng để phục vụ phân tích.

**Gợi ý:**

1. `EXISTS` hoặc `COUNT(DISTINCT customer_id)` sau `INNER JOIN` nếu thật sự cần nối; `EXISTS` thường biểu đạt đúng mục tiêu lọc theo sự tồn tại.
2. Tổng hợp trực tiếp `orders GROUP BY customer_id`, rồi nối với `customers` nếu cần giữ người chưa có đơn.
3. Tiền tổng hợp **payments** và **order_items** riêng theo `order_id` rồi nối các kết quả, bảo đảm mỗi đơn một dòng.
4. `COUNT(DISTINCT order_id)` là lựa chọn hợp lý nếu khóa duy nhất đúng và ý định thực sự là đếm số đơn khác nhau; không mở rộng giải pháp này thành `SUM(DISTINCT amount)`.

## 19. Quy tắc áp dụng nhanh khi viết báo cáo SQL

| Bạn muốn tính | Grain cần đảm bảo | Cách viết thường phù hợp |
|---|---|---|
| Tổng số khách hàng trong bảng | Một dòng/khách hàng | `COUNT(*) FROM customers` |
| Số khách hàng có đơn | Một dòng/khách hàng | `WHERE EXISTS (...)` hoặc `COUNT(DISTINCT customer_id)` |
| Số đơn theo khách hàng | Một dòng/đơn trước khi nhóm | `COUNT(o.order_id)` khi chỉ nối khách hàng–đơn; hoặc `COUNT(DISTINCT o.order_id)` nếu có fanout |
| Tổng tiền đơn theo khách hàng | Mỗi `order_total` một lần/đơn | Tổng hợp `orders` trước khi nối nhiều bảng con |
| Tổng chi tiết sản phẩm | Một dòng/`item_id` trước khi cộng | `GROUP BY order_id` trong `order_items` rồi nối |
| Tổng tiền đã thanh toán | Một dòng/`payment_id` trước khi cộng | `GROUP BY order_id` trong `payments` rồi nối |
| Đếm dữ liệu con sau LEFT JOIN | Một dòng/đơn vị muốn đếm | `COUNT(child_id)` khi không có fanout; nếu fanout thì xác định lại grain |
| Đếm thực thể với khóa ghép | Một cặp/bộ khóa duy nhất | `SELECT DISTINCT key1, key2 ...` rồi `COUNT(*)`, hoặc cú pháp thích hợp của DBMS |
| Giữ các thực thể không có dữ liệu con | Một dòng trên thực thể phía trái | `LEFT JOIN`, điều kiện bảng con trong `ON` khi cần |
| Báo cáo nhiều chỉ số từ nhiều quan hệ `1:N` | Mỗi nguồn đã tổng hợp về đúng khóa chung | CTE/subquery pre-aggregation trước `JOIN` |

**Cách tư duy đáng nhớ nhất:** mỗi khi thêm một `JOIN`, hãy hỏi **“một dòng bên trái có thể khớp bao nhiêu dòng bên phải?”**. Mỗi khi thêm một `COUNT` hoặc `SUM`, hãy hỏi **“tôi đang đếm/cộng thực thể nào, và giá trị đó có bị lặp trong tập dòng hiện tại không?”**.

Nếu giữ đúng **grain** của từng chỉ số, chọn đúng **khóa nhận diện**, và **tổng hợp mỗi quan hệ một–nhiều trước khi ghép các tổng với nhau**, báo cáo SQL sẽ tránh được phần lớn lỗi **đếm lặp thực thể** và **nhân đôi doanh thu, số lượng hoặc thanh toán** sau `JOIN`.

