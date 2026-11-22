# Phân biệt mức chi tiết từng hàng và mức chi tiết từng nhóm

Khi làm báo cáo SQL, một câu hỏi tưởng như đơn giản — “Có bao nhiêu đơn hàng của mỗi khách?”, “Tổng tiền từng đơn là bao nhiêu?”, hay “Doanh thu theo tháng là bao nhiêu?” — có thể dẫn đến những kết quả khác nhau nếu ta không xác định rõ **mỗi hàng trong kết quả đại diện cho điều gì**.

Một bảng `order_lines` có thể lưu **một hàng cho mỗi sản phẩm trong đơn**; bảng `orders` lưu **một hàng cho mỗi đơn**; còn báo cáo `GROUP BY customer_id` trả **một hàng cho mỗi khách hàng**. Ba kết quả đều liên quan đơn hàng nhưng có **mức chi tiết (*grain*)** khác nhau. Nếu đếm đơn trên dữ liệu đã nối với nhiều dòng sản phẩm mà không chú ý grain, ta có thể vô tình đếm một đơn hai lần.

Trong chủ đề **Tổng hợp dữ liệu**, phân biệt **mức chi tiết từng hàng** với **mức chi tiết từng nhóm** là nền tảng để viết `GROUP BY` đúng, đặt `WHERE` và `HAVING` đúng vị trí, chọn hàm tổng hợp phù hợp và tránh lỗi nhân bản dữ liệu khi `JOIN`. Bài học sẽ giải thích khái niệm, dùng một bộ dữ liệu tự chứa, trình bày các lỗi thường gặp và cách giữ mức chi tiết mong muốn bằng truy vấn con, CTE hoặc hàm cửa sổ.

## 1. Grain là gì? Mỗi hàng đang đại diện cho đối tượng nào?

**Grain (mức chi tiết/hạt dữ liệu)** là cách mô tả ý nghĩa của **một hàng** trong bảng hoặc kết quả truy vấn. Một cách tự hỏi hữu ích:

> “Nếu tôi chỉ vào một hàng này, nó đại diện cho **một cái gì**?”

| Mức chi tiết | Một hàng đại diện cho | Khóa nhận diện ví dụ |
|---|---|---|
| **Dòng đơn hàng** (*line-item grain*) | Một sản phẩm trong một đơn | `(order_id, sku)` |
| **Đơn hàng** (*order grain*) | Một đơn hàng | `order_id` |
| **Khách hàng** (*customer grain*) | Một khách hàng | `customer_id` |
| **Khách hàng × trạng thái** | Một tổ hợp khách và trạng thái | `(customer_id, status)` |
| **Tháng** (*monthly grain*) | Một tháng lịch | `year_month` hoặc mốc đầu tháng |
| **Khách hàng × tháng** | Một khách trong một tháng | `(customer_id, month_start)` |

Grain không đồng nghĩa với **số cột**. Một kết quả có 15 cột vẫn có thể là **một hàng mỗi khách**. Ngược lại, một kết quả chỉ có hai cột `order_id` và `sku` lại có **nhiều hàng cho một đơn**.

Grain cũng không nhất thiết trùng với khóa chính của bảng nguồn. Sau `JOIN`, `GROUP BY` hoặc dùng hàm cửa sổ, số hàng và ý nghĩa mỗi hàng có thể thay đổi. Vì vậy cần xác định grain ở **đầu vào, từng bước biến đổi và đầu ra**.

### 1.1. Hai cấp độ thường gặp trong báo cáo

- **Mức chi tiết từng hàng:** tính toán hoặc điều kiện áp dụng cho từng bản ghi đầu vào. Ví dụ `quantity * unit_price` là tiền của **một dòng sản phẩm**.
- **Mức chi tiết từng nhóm:** gom nhiều hàng có cùng khóa nhóm, rồi tính `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`. Ví dụ `SUM(quantity * unit_price) GROUP BY order_id` là tổng tiền **một đơn hàng**.

Điểm quyết định là câu hỏi nghiệp vụ: “Tôi muốn **một hàng cho mỗi dòng sản phẩm**, **một hàng cho mỗi đơn**, hay **một hàng cho mỗi khách**?”. Trả lời câu này **trước khi viết SQL** giúp tránh nhiều lỗi khó thấy.

## 2. Dữ liệu thực hành: khách, đơn và dòng đơn hàng

Các ví dụ dưới đây dùng cú pháp SQL tương thích với PostgreSQL. Hãy tạo bảng trong một **cơ sở dữ liệu học tập riêng**. Một số hàm định dạng ngày ở phần sau là đặc thù PostgreSQL; ý tưởng về grain và `GROUP BY` có thể áp dụng rộng rãi.

### 2.1. Tạo bảng

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    region VARCHAR(20)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    ordered_on DATE NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PAID', 'NEW', 'CANCELLED'))
);

CREATE TABLE order_lines (
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    sku VARCHAR(30) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, sku)
);
```

Quan hệ giữa các bảng:

```text
customers
  customer_id PK
       | 1
       |
       | N
orders
  order_id PK, customer_id FK
       | 1
       |
       | N
order_lines
  (order_id, sku) PK, order_id FK
```

Theo định nghĩa:

- Mỗi khách có thể có nhiều đơn.
- Mỗi đơn thuộc đúng một khách.
- Mỗi đơn có thể có nhiều dòng sản phẩm.
- Trong ví dụ, một `sku` xuất hiện tối đa một lần trong cùng đơn vì khóa chính ghép `(order_id, sku)`.

`unit_price` là đơn giá ghi nhận tại thời điểm mua; `quantity * unit_price` là giá trị của **một dòng**. Khi cần tổng đơn, phải cộng các dòng thuộc cùng `order_id`.

### 2.2. Nạp dữ liệu cố định

```sql
INSERT INTO customers (customer_id, customer_name, region)
VALUES
    (1, 'An',   'HN'),
    (2, 'Binh', 'HCM'),
    (3, 'Chi',  'HN'),
    (4, 'Dung', NULL);

INSERT INTO orders (order_id, customer_id, ordered_on, status)
VALUES
    (101, 1, DATE '2025-01-10', 'PAID'),
    (102, 1, DATE '2025-01-12', 'NEW'),
    (103, 2, DATE '2025-01-12', 'PAID'),
    (104, 2, DATE '2025-02-01', 'PAID'),
    (105, 3, DATE '2025-02-02', 'CANCELLED');

INSERT INTO order_lines (order_id, sku, quantity, unit_price)
VALUES
    (101, 'BOOK', 2, 100000.00),
    (101, 'PEN',  1,  50000.00),
    (102, 'NOTE', 3, 20000.00),
    (103, 'BOOK', 1, 100000.00),
    (103, 'NOTE', 2,  20000.00),
    (104, 'PEN',  4,  50000.00),
    (105, 'NOTE', 1,  20000.00);
```

Ta có **4 khách, 5 đơn, 7 dòng sản phẩm**. Khách Dung chưa có đơn nào. Mức chi tiết của ba bảng khác nhau ngay từ đầu.

Các dòng sản phẩm và số tiền:

| order_id | sku | quantity | unit_price | line_amount |
|---:|---|---:|---:|---:|
| 101 | BOOK | 2 | 100.000 | 200.000 |
| 101 | PEN | 1 | 50.000 | 50.000 |
| 102 | NOTE | 3 | 20.000 | 60.000 |
| 103 | BOOK | 1 | 100.000 | 100.000 |
| 103 | NOTE | 2 | 20.000 | 40.000 |
| 104 | PEN | 4 | 50.000 | 200.000 |
| 105 | NOTE | 1 | 20.000 | 20.000 |

Tổng giá trị tất cả các dòng là **670.000**. Đây là tổng số tiền theo dữ liệu mẫu, chưa áp dụng chính sách bỏ đơn `NEW` hoặc `CANCELLED`. Nếu chỉ tính đơn `PAID`, tổng là **590.000**.

## 3. Mức chi tiết từng hàng: tính toán mà không gom nhóm

Truy vấn sau đọc từng dòng sản phẩm rồi tính tiền:

```sql
SELECT
    order_id,
    sku,
    quantity,
    unit_price,
    quantity * unit_price AS line_amount
FROM order_lines
ORDER BY order_id, sku;
```

Kết quả có **7 hàng**, tương ứng đúng 7 dòng sản phẩm ở bảng trên. Biểu thức:

```sql
quantity * unit_price
```

được tính **riêng cho từng hàng**. Nó không gộp hai dòng của đơn 101 lại thành một hàng. Việc tạo thêm một cột tính toán bằng `AS line_amount` không thay đổi grain.

### 3.1. WHERE là bộ lọc ở mức hàng

Ví dụ: chỉ lấy những dòng có số lượng ít nhất 2:

```sql
SELECT order_id, sku, quantity
FROM order_lines
WHERE quantity >= 2
ORDER BY order_id, sku;
```

Kết quả:

| order_id | sku | quantity |
|---:|---|---:|
| 101 | BOOK | 2 |
| 102 | NOTE | 3 |
| 103 | NOTE | 2 |
| 104 | PEN | 4 |

`WHERE` **loại một số hàng** nhưng không tự biến các dòng còn lại thành các nhóm. Kết quả vẫn ở grain **một hàng mỗi dòng sản phẩm được giữ lại**.

Đây là khác biệt căn bản: `WHERE quantity >= 2` không có nghĩa “chọn đơn có tổng số lượng từ 2 trở lên”. Nếu đơn có nhiều dòng mỗi dòng số lượng 1, tổng số lượng của đơn có thể từ 2 trở lên dù không có dòng nào vượt điều kiện `WHERE`.

### 3.2. Chọn ít cột không làm đổi grain

```sql
SELECT order_id
FROM order_lines
ORDER BY order_id;
```

Kết quả vẫn có **7 hàng**:

```text
101
101
102
103
103
104
105
```

Việc chỉ chọn `order_id` không có nghĩa kết quả trở thành “một hàng mỗi đơn”. Hai dòng của đơn 101 vẫn là hai hàng. Để tạo một hàng mỗi đơn, cần **gom nhóm**, hoặc dùng `DISTINCT` khi chỉ muốn liệt kê mã duy nhất.

```sql
SELECT DISTINCT order_id
FROM order_lines
ORDER BY order_id;
-- 101, 102, 103, 104, 105
```

`DISTINCT` loại các bản ghi trùng nhau theo **toàn bộ các biểu thức trong danh sách `SELECT`**; nó không tự tính tổng hay giải quyết mọi vấn đề grain. Nếu thêm `sku` vào `SELECT DISTINCT order_id, sku`, kết quả trở lại 7 cặp khác nhau.

## 4. Mức chi tiết từng nhóm: GROUP BY chuyển nhiều hàng thành một

Để tính tổng tiền **từng đơn**, ta gom các dòng có cùng `order_id`:

```sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM order_lines
GROUP BY order_id
ORDER BY order_id;
```

| order_id | order_total |
|---:|---:|
| 101 | 250000.00 |
| 102 | 60000.00 |
| 103 | 140000.00 |
| 104 | 200000.00 |
| 105 | 20000.00 |

Bây giờ kết quả chỉ có **5 hàng**: mỗi hàng đại diện cho **một đơn hàng**. Cùng dữ liệu nguồn 7 dòng, nhưng `GROUP BY order_id` đã thay đổi grain từ **dòng đơn hàng** sang **đơn hàng**.

Phân tích:

```text
Trước GROUP BY (7 dòng):
101 BOOK  200000 ─┐
101 PEN    50000 ─┴──> 101  250000
102 NOTE   60000 ─────> 102   60000
103 BOOK  100000 ─┐
103 NOTE   40000 ─┴──> 103  140000
104 PEN   200000 ─────> 104  200000
105 NOTE   20000 ─────> 105   20000

Sau GROUP BY order_id (5 nhóm):
một hàng / một order_id
```

### 4.1. GROUP BY định nghĩa khóa của nhóm

Ví dụ:

```sql
GROUP BY order_id
```

nghĩa là tất cả dòng có cùng `order_id` thuộc một nhóm.

Nếu thay bằng:

```sql
GROUP BY order_id, sku
```

thì mỗi **cặp `(order_id, sku)`** là một nhóm. Do bảng có khóa chính ghép cặp này, kết quả vẫn có **7 nhóm**, tức trở lại grain của từng dòng sản phẩm. Thêm cột vào `GROUP BY` có thể **làm mức chi tiết nhỏ hơn**, khiến số nhóm tăng.

Ngược lại:

```sql
GROUP BY sku
```

gộp mọi dòng có cùng mã sản phẩm từ nhiều đơn:

```sql
SELECT sku, SUM(quantity * unit_price) AS value_by_sku
FROM order_lines
GROUP BY sku
ORDER BY sku;
```

| sku | value_by_sku |
|---|---:|
| BOOK | 300000.00 |
| NOTE | 120000.00 |
| PEN | 250000.00 |

Kết quả có **3 hàng**, grain **một hàng mỗi SKU**, không phải mỗi đơn. Tổng vẫn bằng **670.000**, nhưng các hàng phân chia dữ liệu theo một chiều hoàn toàn khác.

### 4.2. Không chọn tùy ý cột ngoài GROUP BY

Giả sử viết:

```sql
-- Sai mục đích và thường không hợp lệ trong PostgreSQL:
SELECT order_id, sku, SUM(quantity * unit_price)
FROM order_lines
GROUP BY order_id;
```

Một đơn có thể có nhiều `sku`. Nếu chỉ nhóm theo `order_id`, SQL không biết phải đưa **sku nào** lên hàng kết quả của đơn 101 (BOOK hay PEN?). Trong PostgreSQL, cột `sku` không được nhóm hay tổng hợp sẽ gây lỗi với trường hợp này.

Cách lựa chọn:

- Muốn **một hàng mỗi đơn**: chỉ chọn các khóa nhóm, giá trị tổng hợp và những biểu thức hợp lệ theo quy tắc grouping của DBMS.
- Muốn **một hàng mỗi dòng sản phẩm** kèm tổng đơn: dùng **hàm cửa sổ** (mục 9).
- Muốn **mỗi SKU trong từng đơn**: thêm `sku` vào `GROUP BY`, chấp nhận grain khác.

Một số DBMS có ngoại lệ theo **phụ thuộc hàm** hoặc chế độ xử lý cột không được nhóm. Đừng dựa vào việc DBMS tự chọn giá trị tùy ý cho cột không nằm trong `GROUP BY` khi dữ liệu có nhiều giá trị khả dĩ.

## 5. Cùng dữ liệu, nhiều cấp độ báo cáo

Mức chi tiết mong muốn phải khớp cách người dùng đặt câu hỏi.

### 5.1. Một hàng cho mỗi đơn

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.status,
    SUM(l.quantity * l.unit_price) AS order_total
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
GROUP BY o.order_id, o.customer_id, o.status
ORDER BY o.order_id;
```

Kết quả có **5 hàng**. Đầu vào sau `JOIN` có 7 hàng vì đơn 101 và 103 mỗi đơn có hai dòng; `GROUP BY` đưa trở lại grain **một hàng mỗi đơn**. Các cột `customer_id` và `status` được thêm vào khóa nhóm để trình bày tường minh và dễ chuyển sang nhiều DBMS.

### 5.2. Một hàng cho mỗi khách

Nếu muốn tổng giá trị mọi đơn theo khách, ta có thể nhóm theo khách trực tiếp sau khi nối bảng:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
LEFT JOIN order_lines AS l ON l.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | total_amount |
|---:|---|---:|
| 1 | An | 310000.00 |
| 2 | Binh | 340000.00 |
| 3 | Chi | 20000.00 |
| 4 | Dung | 0 |

**Grain của kết quả là một hàng mỗi khách**. Dung vẫn xuất hiện nhờ `LEFT JOIN` dù chưa có đơn. Tổng `SUM(...)` trên khách Dung là `NULL` vì không có giá trị dòng đơn nào; `COALESCE(..., 0)` chuyển nó sang 0 **trong báo cáo**.

Ở đây cộng tiền trực tiếp vẫn phù hợp vì mỗi dòng `order_lines` đóng góp đúng một lần cho một khách, và hai `LEFT JOIN` không có một nhánh nhiều-nhiều khác gây nhân bản. Nhưng việc đếm đơn trực tiếp trên kết quả nối ấy có thể sai; xem mục 7.

### 5.3. Một hàng cho mỗi cặp khách × trạng thái

```sql
SELECT
    o.customer_id,
    o.status,
    COUNT(*) AS order_count
FROM orders AS o
GROUP BY o.customer_id, o.status
ORDER BY o.customer_id, o.status;
```

Kết quả:

| customer_id | status | order_count |
|---:|---|---:|
| 1 | NEW | 1 |
| 1 | PAID | 1 |
| 2 | PAID | 2 |
| 3 | CANCELLED | 1 |

Khách An có **hai hàng** vì có đơn ở hai trạng thái. Đây không phải lỗi trùng khách: grain của truy vấn là **mỗi tổ hợp khách và trạng thái**. Dung không hiện vì không có đơn trong bảng `orders` làm đầu vào.

### 5.4. Một hàng cho mỗi tháng

Với PostgreSQL:

```sql
SELECT
    DATE_TRUNC('month', ordered_on)::DATE AS month_start,
    COUNT(*) AS order_count
FROM orders
GROUP BY DATE_TRUNC('month', ordered_on)::DATE
ORDER BY month_start;
```

| month_start | order_count |
|---|---:|
| 2025-01-01 | 3 |
| 2025-02-01 | 2 |

Kết quả giờ có **2 hàng**, grain **một hàng mỗi tháng**. `DATE_TRUNC('month', ...)` đưa mọi ngày trong cùng tháng về cùng mốc đầu tháng; cú pháp `::DATE` là cách ép kiểu của PostgreSQL. Các DBMS khác có hàm tháng hoặc cách biểu diễn khác.

Lưu ý: nếu chỉ nhóm theo **số tháng** (`EXTRACT(MONTH FROM ordered_on)`) mà dữ liệu có nhiều năm, tháng 1 của năm 2025 và năm 2026 có thể bị gộp vào cùng một nhóm. Cần đưa cả **năm** vào khóa nhóm, hoặc dùng giá trị đại diện **năm-tháng**.

## 6. WHERE và HAVING: lọc hàng khác lọc nhóm

Hai mệnh đề phục vụ **hai cấp độ điều kiện**:

| Mệnh đề | Thời điểm logic | Đối tượng lọc | Ví dụ |
|---|---|---|---|
| **`WHERE`** | Trước `GROUP BY` | Hàng đầu vào | Chỉ xét đơn `PAID` |
| **`HAVING`** | Sau `GROUP BY` | Nhóm đã tổng hợp | Chỉ giữ khách có từ 2 đơn `PAID` |

### 6.1. Lọc đơn trước, rồi mới đếm theo khách

```sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count
FROM orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
ORDER BY o.customer_id;
```

Kết quả:

| customer_id | paid_order_count |
|---:|---:|
| 1 | 1 |
| 2 | 2 |

`WHERE` loại đơn 102 (`NEW`) và 105 (`CANCELLED`) **trước khi nhóm**. Dung và Chi không xuất hiện trong kết quả vì không có hàng `PAID` ở đầu vào sau lọc.

### 6.2. Chỉ giữ những nhóm có ít nhất hai đơn PAID

```sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count
FROM orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY o.customer_id;
```

Kết quả chỉ có **khách 2 (Binh), 2 đơn**. `HAVING COUNT(*) >= 2` đánh giá **số hàng của từng nhóm sau khi lọc trạng thái**.

Không viết `WHERE COUNT(*) >= 2` để lọc nhóm: `WHERE` hoạt động trước `GROUP BY`, khi giá trị `COUNT(*)` của nhóm chưa được tạo ra. Dùng `HAVING` hoặc tính tổng hợp trong CTE rồi dùng `WHERE` bên ngoài.

### 6.3. Lọc một phần dữ liệu có thể đổi ý nghĩa số đo

So sánh:

```sql
-- A: tổng tiền của các dòng có quantity >= 2 trong từng đơn
SELECT order_id,
       SUM(quantity * unit_price) AS selected_lines_total
FROM order_lines
WHERE quantity >= 2
GROUP BY order_id
ORDER BY order_id;
```

Truy vấn A **chỉ cộng những dòng có quantity >= 2**. Đơn 101 chỉ còn dòng BOOK (200.000), mất dòng PEN (50.000), nên số tiền hiển thị cho đơn 101 là **200.000**, không phải tổng đơn **250.000**.

Nếu yêu cầu là **“chọn các đơn mà tổng số lượng sản phẩm ít nhất 2, rồi báo tổng tiền đầy đủ của đơn”**, phải nhóm toàn bộ dòng của mỗi đơn trước:

```sql
SELECT
    order_id,
    SUM(quantity) AS total_units,
    SUM(quantity * unit_price) AS order_total
FROM order_lines
GROUP BY order_id
HAVING SUM(quantity) >= 2
ORDER BY order_id;
```

Kết quả gồm đơn 101 (3 sản phẩm, 250.000), 102 (3, 60.000), 103 (3, 140.000), 104 (4, 200.000). Đơn 105 có tổng số lượng 1 nên bị loại. Đây là khác biệt giữa:

- **Lọc dòng** có số lượng từ 2 trở lên.
- **Lọc đơn** có **tổng** số lượng từ 2 trở lên.

Không phải vấn đề chỉ về cú pháp: hai truy vấn đang trả lời **hai câu hỏi khác nhau**.

## 7. Sai lầm phổ biến: JOIN làm số hàng nhân lên trước khi tổng hợp

Khi nối bảng `orders` (một hàng mỗi đơn) với `order_lines` (nhiều hàng mỗi đơn), mỗi đơn được lặp theo số dòng sản phẩm.

```sql
SELECT
    o.order_id,
    o.customer_id,
    l.sku
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
ORDER BY o.order_id, l.sku;
```

Kết quả có **7 hàng**, không phải 5. Đơn 101 xuất hiện **hai lần** vì có BOOK và PEN; đơn 103 cũng hai lần. Grain đã chuyển sang **dòng sản phẩm của đơn**.

### 7.1. COUNT(order_id) sau JOIN có thể đếm số dòng, không phải số đơn

Đây là truy vấn dễ nhầm:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS wrong_order_count
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
LEFT JOIN order_lines AS l ON l.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | wrong_order_count |
|---:|---|---:|
| 1 | An | 3 |
| 2 | Binh | 3 |
| 3 | Chi | 1 |
| 4 | Dung | 0 |

Đây **không phải số đơn thực tế** của khách:

- An có **2 đơn** (101, 102), nhưng tổng số dòng sản phẩm của hai đơn là **3**.
- Binh có **2 đơn** (103, 104), nhưng tổng số dòng sản phẩm là **3**.
- Chi có 1 đơn với 1 dòng.
- Dung không có đơn; `COUNT(o.order_id)` trả 0 vì hàng mở rộng của `LEFT JOIN` có `o.order_id = NULL`.

Sau `JOIN`, `COUNT(o.order_id)` đang đếm **số hàng của kết quả nối có `order_id` không `NULL`**, chứ không bảo đảm mỗi đơn chỉ được đếm một lần.

### 7.2. COUNT(DISTINCT ...) xử lý đếm khóa duy nhất

Nếu mục tiêu chỉ là đếm đơn khác nhau sau phép nối, có thể viết:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(DISTINCT o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
LEFT JOIN order_lines AS l ON l.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | order_count |
|---:|---|---:|
| 1 | An | 2 |
| 2 | Binh | 2 |
| 3 | Chi | 1 |
| 4 | Dung | 0 |

`COUNT(DISTINCT o.order_id)` đếm mỗi **mã đơn** một lần trong từng nhóm khách. Với bài toán đếm khóa duy nhất, đây là cách diễn đạt đúng.

Tuy nhiên, **`DISTINCT` không sửa mọi sai lầm do JOIN nhân hàng**. Ví dụ, nếu nối thêm một bảng giao hàng gồm nhiều sự kiện cho một đơn, cả dòng sản phẩm lẫn sự kiện giao hàng có thể nhân lẫn nhau. Khi ấy:

- `COUNT(DISTINCT order_id)` vẫn có thể đếm đúng đơn.
- `SUM(l.quantity * l.unit_price)` có thể bị **nhân tiền** lên theo số sự kiện giao hàng.
- `SUM(DISTINCT l.quantity * l.unit_price)` **không phải giải pháp chung** vì hai dòng có cùng số tiền hợp lệ có thể bị gộp thành một.

Muốn tổng hợp đáng tin cậy, cần **chọn grain của dữ liệu trước khi JOIN**.

### 7.3. Một cách an toàn: tính tổng ở mức đơn trước khi nối sang khách

Dùng CTE (*common table expression*) để tạo chính xác **một hàng cho mỗi đơn**:

```sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(ot.order_total), 0) AS total_amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_totals AS ot
    ON ot.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | order_count | total_amount |
|---:|---|---:|---:|
| 1 | An | 2 | 310000.00 |
| 2 | Binh | 2 | 340000.00 |
| 3 | Chi | 1 | 20000.00 |
| 4 | Dung | 0 | 0 |

Luồng mức chi tiết:

```text
order_lines  (7 hàng, một hàng / dòng sản phẩm)
    |
    | GROUP BY order_id + SUM
    v
order_totals (5 hàng, một hàng / đơn)
    |
    | JOIN orders (cũng một hàng / đơn)
    v
theo đơn    (5 đơn; giữ các khách không có đơn bằng LEFT JOIN)
    |
    | GROUP BY customer_id, customer_name
    v
theo khách  (4 hàng, một hàng / khách)
```

Vì `order_totals` có **tối đa một hàng cho một `order_id`**, phép nối từ `orders` sang nó không làm nhân đơn. Điều này cho phép vừa `COUNT(o.order_id)` vừa `SUM(ot.order_total)` trong cùng truy vấn mà không nhầm số dòng với số đơn. Nếu nghiệp vụ cho phép đơn chưa có dòng sản phẩm, cần quyết định xem tổng tiền đơn đó là 0 hay chưa xác định và xử lý `NULL` một cách rõ ràng.

Đây là kỹ thuật **pre-aggregation (tổng hợp trước khi nối)**, đặc biệt hữu ích khi có các quan hệ một-nhiều ở nhiều nhánh khác nhau.

## 8. LEFT JOIN, COUNT(*) và số nhóm bằng 0

Muốn báo cáo bao gồm cả khách chưa có đơn, ta thường dùng `LEFT JOIN`. Nhưng `COUNT(*)` và `COUNT(o.order_id)` có ý nghĩa khác nhau.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS rows_after_join,
    COUNT(o.order_id) AS actual_order_count
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | rows_after_join | actual_order_count |
|---:|---|---:|---:|
| 1 | An | 2 | 2 |
| 2 | Binh | 2 | 2 |
| 3 | Chi | 1 | 1 |
| 4 | Dung | 1 | 0 |

Tại sao Dung có `COUNT(*) = 1`? Vì `LEFT JOIN` giữ **một hàng đại diện cho khách Dung** và điền `NULL` vào các cột của bảng `orders` khi không tìm thấy đơn. `COUNT(*)` đếm **hàng đầu ra của JOIN**, kể cả hàng đại diện này. Trong khi đó, `COUNT(o.order_id)` bỏ qua `NULL`, nên trả 0.

Quy tắc:

- **`COUNT(*)`:** đếm toàn bộ hàng đầu vào của phép tổng hợp, kể cả hàng chứa `NULL` ở các cột.
- **`COUNT(column)`:** chỉ đếm những hàng mà biểu thức cột **không phải `NULL`**.
- **`COUNT(DISTINCT column)`:** đếm các giá trị khác nhau không `NULL`.

Khi đếm bản ghi con qua `LEFT JOIN`, hãy dùng **khóa không `NULL` của bảng con**, chẳng hạn `COUNT(o.order_id)`, thay vì `COUNT(*)`.

### 8.1. Đặt điều kiện trạng thái ở ON hay WHERE?

Muốn **mọi khách đều hiện, kèm số đơn PAID**, hãy đặt điều kiện trên bảng phải trong `ON`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả: **An 1, Binh 2, Chi 0, Dung 0**.

Nếu thay bằng:

```sql
-- Khác ý nghĩa: WHERE loại các hàng không có đơn PAID.
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

chỉ còn **An và Binh**. Chi và Dung bị loại vì không có hàng nối nào có `o.status = 'PAID'`. Khi thiết kế báo cáo, việc “khách có 0 đơn PAID” và “khách không xuất hiện trong báo cáo” không phải một ý nghĩa.

## 9. Hàm cửa sổ: biết số liệu nhóm nhưng vẫn giữ từng hàng

Không phải lúc nào cần số liệu tổng của nhóm ta cũng muốn **làm mất hàng chi tiết**. Ví dụ một màn hình cần hiển thị từng sản phẩm trong đơn, nhưng bên cạnh mỗi dòng vẫn hiện tổng tiền của đơn đó.

Nếu dùng `GROUP BY order_id` thì kết quả chỉ còn 5 hàng và không còn `sku` từng dòng. PostgreSQL và nhiều DBMS hiện đại hỗ trợ **hàm cửa sổ (*window functions*)** để tính số liệu theo nhóm logic **mà không gộp các hàng đầu vào của truy vấn**.

```sql
SELECT
    order_id,
    sku,
    quantity * unit_price AS line_amount,
    SUM(quantity * unit_price)
        OVER (PARTITION BY order_id) AS order_total
FROM order_lines
ORDER BY order_id, sku;
```

| order_id | sku | line_amount | order_total |
|---:|---|---:|---:|
| 101 | BOOK | 200000.00 | 250000.00 |
| 101 | PEN | 50000.00 | 250000.00 |
| 102 | NOTE | 60000.00 | 60000.00 |
| 103 | BOOK | 100000.00 | 140000.00 |
| 103 | NOTE | 40000.00 | 140000.00 |
| 104 | PEN | 200000.00 | 200000.00 |
| 105 | NOTE | 20000.00 | 20000.00 |

Số hàng vẫn là **7**, grain đầu ra vẫn **một hàng mỗi dòng sản phẩm**. `PARTITION BY order_id` chia các dòng thành những cửa sổ tính toán theo đơn, nhưng không thay thế chúng bằng một hàng tổng hợp.

So sánh trực tiếp:

| Cách tính | Số hàng đầu ra | Grain | Tổng tiền đơn hiển thị thế nào? |
|---|---:|---|---|
| `GROUP BY order_id` + `SUM(...)` | 5 | Một hàng mỗi đơn | Mỗi đơn một lần |
| `SUM(...) OVER (PARTITION BY order_id)` | 7 | Một hàng mỗi dòng sản phẩm | Lặp trên mọi dòng thuộc đơn |

**Cảnh báo:** Vì `order_total` xuất hiện hai lần trên hai dòng của đơn 101, nếu lấy kết quả cửa sổ rồi `SUM(order_total)` toàn bộ 7 hàng, tổng sẽ bị **đếm lặp**. Một cột là số liệu mức đơn không trở thành “số tiền từng dòng” chỉ vì nó được hiển thị bên cạnh từng dòng.

### 9.1. Thống kê theo khách trong khi vẫn hiển thị từng đơn

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.status,
    COUNT(*) OVER (PARTITION BY o.customer_id) AS orders_by_customer,
    ROW_NUMBER() OVER (
        PARTITION BY o.customer_id
        ORDER BY o.ordered_on DESC, o.order_id DESC
    ) AS newest_first
FROM orders AS o
ORDER BY o.customer_id, newest_first;
```

| order_id | customer_id | status | orders_by_customer | newest_first |
|---:|---:|---|---:|---:|
| 102 | 1 | NEW | 2 | 1 |
| 101 | 1 | PAID | 2 | 2 |
| 104 | 2 | PAID | 2 | 1 |
| 103 | 2 | PAID | 2 | 2 |
| 105 | 3 | CANCELLED | 1 | 1 |

`COUNT(*) OVER (PARTITION BY customer_id)` hiển thị số đơn của khách **trên từng hàng đơn**. `ROW_NUMBER` đánh số thứ tự từng đơn trong khách, đơn mới nhất trước. Kết quả vẫn có **5 hàng**, không phải 3 nhóm khách. Dung không có đơn nên không hiện trong bảng `orders`; nếu muốn hiện cả khách không có đơn, cần bắt đầu từ `customers` và thiết kế `JOIN` phù hợp.

**Hàm cửa sổ không tự sửa dữ liệu đã bị nhân hàng bởi JOIN.** Nếu thực hiện một `JOIN` một-nhiều trước rồi mới tính `COUNT(*) OVER (...)`, số đếm có thể là số **hàng sau JOIN**, không phải số bản ghi gốc. Chọn grain đầu vào đúng vẫn là bước đầu tiên.

## 10. AVG: trung bình ở mức dòng có thể khác trung bình ở mức đơn

Đây là lỗi khó nhận ra hơn `COUNT` sai sau `JOIN`.

Giả sử muốn tính **giá trị trung bình của mỗi đơn**. Có hai phép tính trông giống nhau:

**A — Trung bình của từng dòng sản phẩm:**

```sql
SELECT AVG(quantity * unit_price) AS average_line_amount
FROM order_lines;
```

Có **7 dòng**, tổng giá trị 670.000, nên:

```text
average_line_amount = 670000 / 7 ≈ 95714.29
```

**B — Trung bình của tổng tiền từng đơn:**

```sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
)
SELECT AVG(order_total) AS average_order_amount
FROM order_totals;
```

Có **5 đơn**, cùng tổng 670.000:

```text
average_order_amount = 670000 / 5 = 134000
```

Hai con số **khác nhau** vì mẫu số là số **dòng sản phẩm** ở A nhưng là số **đơn hàng** ở B. Cả hai phép tính đều có thể hợp lệ, nhưng đang trả lời hai câu hỏi khác nhau:

- **A:** Một dòng sản phẩm có giá trị trung bình bao nhiêu?
- **B:** Một đơn hàng có tổng giá trị trung bình bao nhiêu?

Nếu lấy `AVG(order_total)` sau khi đã nối mỗi đơn với các dòng sản phẩm và làm lặp tổng đơn, các đơn nhiều dòng sẽ nhận **trọng số lớn hơn** một cách vô tình. Không nên chữa bằng `AVG(DISTINCT order_total)`, vì hai đơn khác nhau nhưng có tổng tiền bằng nhau vẫn phải được tính như **hai đơn**.

### 10.1. Trung bình của các nhóm không luôn là trung bình toàn bộ

Giả sử tính **giá trị trung bình mỗi đơn theo khách**, rồi lấy trung bình không trọng số của những con số đó. Kết quả có thể khác trung bình của **tất cả đơn**, vì mỗi khách có số đơn khác nhau.

Trong dữ liệu mẫu: An có trung bình đơn `(250000 + 60000)/2 = 155000`; Binh có `(140000 + 200000)/2 = 170000`; Chi có `20000`. Trung bình ba giá trị ấy:

```text
(155000 + 170000 + 20000) / 3 = 115000
```

Trong khi trung bình 5 đơn là **134.000**. Không con số nào “tự động đúng” cho mọi yêu cầu:

- **Mỗi khách có trọng số bằng nhau:** có thể lấy trung bình của trung bình theo khách (trên các khách có đơn).
- **Mỗi đơn có trọng số bằng nhau:** phải tính trên từng đơn hoặc lấy tổng tiền chia tổng số đơn.

Trước khi dùng `AVG` ở nhiều cấp độ, hãy xác định **đơn vị cần lấy trung bình** và **mỗi đơn vị được tính trọng số thế nào**.

## 11. GROUP BY với NULL và nhóm không tồn tại

Một khóa nhóm có thể là `NULL`. Trong bảng `customers`, khách Dung chưa có `region`:

```sql
SELECT
    region,
    COUNT(*) AS customer_count
FROM customers
GROUP BY region
ORDER BY region NULLS LAST;
```

Kết quả PostgreSQL:

| region | customer_count |
|---|---:|
| HCM | 1 |
| HN | 2 |
| `NULL` | 1 |

**`GROUP BY` gom các giá trị `NULL` vào cùng một nhóm** theo ngữ nghĩa grouping SQL. Điều này khác với phép so sánh `NULL = NULL` trong `WHERE`, vốn cho `UNKNOWN`. Nếu nhiều khách chưa có khu vực, họ nằm trong **một nhóm `NULL`**.

Trong truy vấn:

```sql
SELECT region,
       COUNT(*) AS total_customers,
       COUNT(region) AS known_regions
FROM customers
GROUP BY region
ORDER BY region NULLS LAST;
```

nhóm `region IS NULL` có `COUNT(*) = 1` nhưng `COUNT(region) = 0`, vì hàm `COUNT(region)` bỏ qua giá trị `NULL`.

**Nhóm không tồn tại** là một chuyện khác. Nếu bắt đầu từ `orders` rồi nhóm theo `customer_id`, khách Dung hoàn toàn **không có hàng đầu vào**, nên không có nhóm “Dung với 0 đơn” được sinh ra. Muốn hiển thị cả các nhóm có số đo 0, phải bắt đầu từ **danh mục đầy đủ của chiều báo cáo** như bảng `customers` và `LEFT JOIN` đến dữ liệu thực tế, hoặc dùng một bảng lịch khi báo cáo theo các tháng không phát sinh đơn.

## 12. Mức chi tiết trong báo cáo nhiều chiều

Báo cáo có thể cần kết hợp nhiều khóa nhóm, ví dụ:

```sql
SELECT
    o.customer_id,
    DATE_TRUNC('month', o.ordered_on)::DATE AS month_start,
    COUNT(*) AS order_count
FROM orders AS o
GROUP BY
    o.customer_id,
    DATE_TRUNC('month', o.ordered_on)::DATE
ORDER BY o.customer_id, month_start;
```

Kết quả:

| customer_id | month_start | order_count |
|---:|---|---:|
| 1 | 2025-01-01 | 2 |
| 2 | 2025-01-01 | 1 |
| 2 | 2025-02-01 | 1 |
| 3 | 2025-02-01 | 1 |

Grain là **mỗi cặp khách × tháng**, không phải “mỗi khách” hay “mỗi tháng” đơn thuần. Khách 2 xuất hiện hai lần do có đơn ở hai tháng. Khách 4 không có đơn nên không xuất hiện.

Nếu chỉ `GROUP BY o.customer_id`, tháng bị gộp. Nếu chỉ `GROUP BY DATE_TRUNC('month', ...)`, khách bị gộp. **Danh sách khóa `GROUP BY` chính là danh sách chiều xác định nhóm**.

### 12.1. Phân biệt chiều báo cáo và thước đo

Khi xây dựng báo cáo, thường có hai loại trường:

- **Chiều (*dimension*):** thông tin dùng để chia nhóm, như `customer_id`, `status`, `month_start`, `region`.
- **Thước đo (*measure*):** giá trị cần tính theo nhóm, như tổng tiền `SUM`, số đơn `COUNT`, giá trung bình `AVG` hoặc tỷ lệ.

Không phải mọi measure đều có thể cộng từ cấp thấp lên cấp cao theo cùng một cách:

- **Tổng số tiền của các dòng không bị nhân bản** có thể cộng từ dòng lên đơn, rồi từ đơn lên khách.
- **Số đơn duy nhất** cần đếm `order_id` ở mức thích hợp; không cộng số đếm đã bị lặp qua nhiều nhóm không tách rời.
- **Trung bình** không thể lấy trung bình của các trung bình một cách tùy ý; thường cần cả tổng và số quan sát.
- **Tỷ lệ**, chẳng hạn “tỷ lệ đơn đã thanh toán”, cần xác định tử số và mẫu số ở cùng phạm vi; không nên cộng trực tiếp các tỷ lệ giữa các nhóm.
- **Số dư tại một thời điểm** hoặc **tồn kho cuối tháng** không thể luôn cộng dọc theo thời gian như doanh thu; phải xác định phép tổng hợp phù hợp với thước đo.

Ví dụ tỷ lệ đơn đã thanh toán theo khách:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN o.status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN o.status = 'PAID' THEN 1 ELSE 0 END)
        * 1.0 / COUNT(*) AS paid_ratio
FROM orders AS o
GROUP BY o.customer_id
ORDER BY o.customer_id;
```

Kết quả:

| customer_id | all_orders | paid_orders | paid_ratio |
|---:|---:|---:|---:|
| 1 | 2 | 1 | 0.5 |
| 2 | 2 | 2 | 1.0 |
| 3 | 1 | 0 | 0.0 |

Ở đây **một hàng `orders` là một đơn**, nên `COUNT(*)` thực sự đếm số đơn; nếu thực hiện công thức này sau khi nối `order_lines`, các đơn có nhiều dòng sẽ vô tình có trọng số lớn hơn. `* 1.0` được dùng để diễn đạt phép chia thập phân thay vì phụ thuộc phép chia số nguyên của DBMS. Dung không có hàng trong bảng `orders` nên không xuất hiện; muốn hiện tỷ lệ cho khách chưa có đơn, phải quyết định nó nên là `NULL` (không có mẫu số) hay một giá trị hiển thị khác theo nghiệp vụ.

## 13. Tóm tắt thứ tự xử lý logic của truy vấn tổng hợp

Một cách nhìn trực quan hữu ích cho truy vấn `SELECT` có `JOIN` và `GROUP BY`:

```text
FROM / JOIN
    ↓  xác định các hàng đầu vào, có thể làm nhân hàng
WHERE
    ↓  loại các hàng không đạt điều kiện
GROUP BY
    ↓  tạo nhóm theo các khóa được chọn
Hàm tổng hợp / HAVING
    ↓  tính SUM, COUNT, AVG... và lọc nhóm
SELECT
    ↓  tạo các cột kết quả
ORDER BY
    ↓  sắp xếp kết quả
LIMIT / OFFSET (nếu có)
    ↓  chọn phần kết quả cần hiển thị
```

Đây là **mô hình thứ tự xử lý logic để học và suy luận**, không phải cam kết thứ tự chạy vật lý của DBMS: bộ tối ưu có thể biến đổi kế hoạch thực thi miễn giữ nguyên ngữ nghĩa. Hàm cửa sổ được tính trên tập hàng tại giai đoạn tương ứng của truy vấn (sau lọc/nhóm ở cùng cấp truy vấn), rồi kết quả có thể được sắp xếp ở cuối.

Từ sơ đồ, có thể thấy:

1. `JOIN` có thể tăng số hàng **trước khi** `COUNT` hoặc `SUM` hoạt động.
2. `WHERE` loại những hàng **trước khi** nhóm, nên ảnh hưởng cả tử số, mẫu số hoặc tổng tiền.
3. `GROUP BY` định nghĩa grain của kết quả tổng hợp.
4. `HAVING` lựa chọn nhóm theo các giá trị tổng hợp.
5. `ORDER BY` chỉ sắp thứ tự; nó không sửa grain.

## 14. Một quy trình thiết kế truy vấn từ câu hỏi nghiệp vụ

Khi nhận yêu cầu làm báo cáo, thử làm theo các bước:

**Bước 1 — Viết rõ grain đầu ra.** Ví dụ “mỗi khách một hàng” hoặc “mỗi khách trong từng tháng một hàng”. Nếu không thể viết một câu như vậy, yêu cầu báo cáo có thể chưa đủ rõ.

**Bước 2 — Xác định grain của các bảng nguồn.** Bảng `orders` có một hàng mỗi đơn; bảng `order_lines` có một hàng mỗi dòng sản phẩm; bảng `customers` có một hàng mỗi khách.

**Bước 3 — Liệt kê quan hệ JOIN và số lượng hàng có thể tạo.** JOIN một-nhiều có thể nhân hàng. JOIN hai nhánh một-nhiều có thể tạo tổ hợp chéo trong cùng một khóa cha, làm lặp thước đo.

**Bước 4 — Chọn thước đo và đơn vị đếm.** `COUNT(*)` đếm hàng của grain hiện tại; `COUNT(DISTINCT order_id)` đếm đơn duy nhất; `SUM(line_amount)` cộng tiền của dòng. Không gọi mọi phép đếm đều là “số đơn”.

**Bước 5 — Quyết định lọc hàng hay lọc nhóm.** “Chỉ tính đơn PAID” là lọc hàng `WHERE status = 'PAID'`; “chỉ những khách có ít nhất hai đơn PAID” là lọc nhóm `HAVING COUNT(*) >= 2` sau khi lọc.

**Bước 6 — Tổng hợp tại mức chi tiết đúng trước khi JOIN nếu cần.** Có thể tạo CTE một hàng mỗi đơn rồi nối sang khách; mỗi CTE nên có grain được xác định rõ trong tên và khóa.

**Bước 7 — Chọn GROUP BY hay hàm cửa sổ.** Nếu chỉ cần một hàng mỗi nhóm, dùng `GROUP BY`. Nếu cần giữ từng hàng nhưng hiển thị số liệu của nhóm, dùng `OVER (PARTITION BY ...)` với chú ý không cộng lại số liệu nhóm đã lặp.

**Bước 8 — Xem kết quả những trường hợp biên.** Khách không có đơn; đơn có nhiều dòng; hai đơn cùng giá trị; giá trị `NULL`; nhóm có số đếm 0; nhiều bản ghi cùng thời điểm.

### Mẫu câu hỏi trước khi viết SQL

| Câu hỏi tự kiểm tra | Vì sao quan trọng |
|---|---|
| Một hàng kết quả đại diện cho gì? | Xác định grain mục tiêu |
| Tập nguồn có một hay nhiều hàng cho mỗi đối tượng? | Tránh nhầm đơn với dòng đơn |
| JOIN có làm nhân hàng không? | Tránh `COUNT`/`SUM` bị phóng đại |
| Tôi muốn đếm hàng, mã duy nhất hay số lượng đơn vị? | Chọn `COUNT(*)`, `COUNT(DISTINCT ...)` hay `SUM(quantity)` |
| Điều kiện áp vào dòng hay vào nhóm? | Chọn `WHERE` hoặc `HAVING` |
| Có cần hiện nhóm không có dữ liệu không? | Chọn bảng chiều và `LEFT JOIN` thích hợp |
| Có cần giữ chi tiết lẫn số liệu nhóm? | Xem xét hàm cửa sổ |
| Trung bình trên đơn hay trên dòng? | Xác định mẫu số đúng |

## 15. Những lỗi thường gặp

### Lỗi 1 — Nhìn thấy order_id rồi nghĩ mỗi hàng là một đơn

`order_id` có thể lặp ở `order_lines` và ở kết quả `JOIN`. Cần kiểm tra khóa **duy nhất của tập hàng hiện tại**, không chỉ tên cột xuất hiện.

### Lỗi 2 — COUNT(*) trên LEFT JOIN rồi kết luận khách chưa có đơn có một đơn

`LEFT JOIN` vẫn tạo một hàng với các cột bên phải `NULL`. `COUNT(*)` đếm hàng này; `COUNT(o.order_id)` mới phù hợp để đếm đơn khi `o.order_id` là khóa không `NULL`.

### Lỗi 3 — Chọn thêm cột vào GROUP BY mà không nhận ra đổi grain

`GROUP BY customer_id` là một hàng mỗi khách. Thêm `status` thành `GROUP BY customer_id, status` khiến một khách có thể có nhiều hàng. Đây là thay đổi **mức chi tiết**, không chỉ thêm thông tin trình bày.

### Lỗi 4 — Lấy SUM(DISTINCT amount) để khử tiền bị nhân

Hai đơn khác nhau có thể có **cùng số tiền**; `SUM(DISTINCT amount)` sẽ chỉ cộng giá trị đó một lần dù nghiệp vụ cần cộng cả hai đơn. Phải sửa quan hệ JOIN hoặc tổng hợp đúng grain trước.

### Lỗi 5 — Lọc một phần dòng trước khi tính tổng đơn

`WHERE quantity >= 2` làm mất những dòng có số lượng 1 trước `SUM`. Nếu mục tiêu là chọn **đơn có tổng số lượng ít nhất 2**, hãy dùng `GROUP BY order_id HAVING SUM(quantity) >= 2`.

### Lỗi 6 — Dùng AVG ở mức sai

`AVG(line_amount)` là trung bình dòng sản phẩm; không phải trung bình tổng tiền đơn. `AVG` của các nhóm cũng có thể cần trọng số để tính lại toàn bộ dữ liệu.

### Lỗi 7 — Quên rằng window function giữ các hàng chi tiết

`SUM(line_amount) OVER (PARTITION BY order_id)` lặp tổng tiền đơn trên nhiều dòng. Đừng cộng lần nữa cột đó mà không đưa về **một hàng mỗi đơn**.

### Lỗi 8 — Cho rằng GROUP BY tạo nhóm cho mọi khóa có thể tồn tại

`GROUP BY` chỉ tạo nhóm từ **hàng đầu vào đã có**. Khách chưa có đơn không tạo nhóm khi truy vấn chỉ từ `orders`. Muốn có các giá trị 0, phải nối với danh mục đầy đủ khách hoặc lịch báo cáo.

### Lỗi 9 — Dùng ORDER BY để tưởng rằng đã nhóm

`ORDER BY customer_id` chỉ đặt các hàng cùng khách gần nhau; nó **không cộng tiền và không biến nhiều hàng thành một**. Để tổng hợp theo khách phải dùng `GROUP BY customer_id` hoặc một cách tổng hợp tương ứng.

### Lỗi 10 — Không xác định rõ phạm vi của một chỉ số

“Tổng tiền khách” có thể gồm mọi đơn, chỉ đơn `PAID`, trừ đơn `CANCELLED`, hoặc chỉ trong tháng báo cáo. Cùng một grain đầu ra nhưng **điều kiện và phạm vi** khác nhau vẫn cho số đo khác nhau. Tên measure cần có ý nghĩa nghiệp vụ rõ ràng.

## 16. Bài tập thực hành

Hãy dự đoán kết quả bằng dữ liệu đã tạo ở mục 2, sau đó mới chạy SQL để đối chiếu.

### Bài 1 — Xác định grain

Với mỗi câu truy vấn sau, hãy nêu **một hàng kết quả đại diện cho gì** và dự đoán **số hàng**:

```sql
-- A
SELECT order_id, sku FROM order_lines;

-- B
SELECT order_id, SUM(quantity * unit_price)
FROM order_lines
GROUP BY order_id;

-- C
SELECT sku, SUM(quantity * unit_price)
FROM order_lines
GROUP BY sku;

-- D
SELECT customer_id, status, COUNT(*)
FROM orders
GROUP BY customer_id, status;
```

**Đáp án:**

- A: **một hàng mỗi dòng sản phẩm**, 7 hàng.
- B: **một hàng mỗi đơn**, 5 hàng.
- C: **một hàng mỗi SKU**, 3 hàng.
- D: **một hàng mỗi cặp khách × trạng thái**, 4 hàng.

### Bài 2 — Phân biệt số dòng, số lượng sản phẩm và số đơn

Viết câu SQL tính cho mỗi đơn:

- Số dòng sản phẩm (`line_count`).
- Tổng số đơn vị hàng (`total_units`).
- Tổng tiền (`order_total`).

Gợi ý:

```sql
SELECT
    order_id,
    COUNT(*) AS line_count,
    SUM(quantity) AS total_units,
    SUM(quantity * unit_price) AS order_total
FROM order_lines
GROUP BY order_id
ORDER BY order_id;
```

**Đáp án cho đơn 101:** `line_count = 2`, `total_units = 3`, `order_total = 250000`. Ba chỉ số đều hợp lệ nhưng đếm **ba thứ khác nhau**.

### Bài 3 — Đếm đơn theo khách

Viết truy vấn trả về **An: 2, Binh: 2, Chi: 1, Dung: 0**. Không nối `order_lines` nếu chỉ cần đếm đơn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Tại sao `COUNT(*)` sẽ khiến khách Dung có kết quả 1?

### Bài 4 — WHERE và HAVING

Yêu cầu: tìm những khách có **ít nhất hai đơn đã thanh toán**. Viết câu SQL không tính đơn `NEW` hoặc `CANCELLED`:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count
FROM orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY o.customer_id;
```

**Đáp án:** chỉ **customer_id = 2**, có 2 đơn `PAID`.

### Bài 5 — Tổng tiền từng đơn và trung bình từng đơn

Hãy tính tổng tiền từng đơn trong CTE, rồi lấy `AVG(order_total)`. So sánh với `AVG(quantity * unit_price)` trực tiếp trên `order_lines`.

**Đáp án:** trung bình từng **đơn** = **134.000**; trung bình từng **dòng** ≈ **95.714,29**. Hai phép tính khác mẫu số.

### Bài 6 — Giữ chi tiết bằng hàm cửa sổ

Viết câu SQL trả 7 hàng, gồm `order_id`, `sku`, `line_amount` và `order_total`. Trong đó `order_total` lặp trên những dòng cùng đơn mà không `GROUP BY`:

```sql
SELECT
    order_id,
    sku,
    quantity * unit_price AS line_amount,
    SUM(quantity * unit_price)
        OVER (PARTITION BY order_id) AS order_total
FROM order_lines
ORDER BY order_id, sku;
```

Giải thích vì sao kết quả vẫn 7 hàng và vì sao không nên cộng lại `order_total` trên cả 7 hàng.

### Bài 7 — Một khách trong một tháng

Viết truy vấn đếm đơn theo **khách và tháng**, dùng `DATE_TRUNC('month', ordered_on)::DATE` nếu đang dùng PostgreSQL.

**Đáp án:** bốn nhóm: khách 1 tháng 1 (2 đơn), khách 2 tháng 1 (1), khách 2 tháng 2 (1), khách 3 tháng 2 (1). Vì sao khách 2 xuất hiện hai dòng và khách 4 không xuất hiện?

### Bài 8 — Phát hiện JOIN nhân sai tổng tiền

Giả sử bảng mới `order_events` chứa **nhiều sự kiện** trên mỗi đơn. Một người viết:

```sql
-- Minh họa ý tưởng; bảng order_events chưa được tạo trong bài này.
SELECT o.customer_id, SUM(l.quantity * l.unit_price)
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
JOIN order_events AS e ON e.order_id = o.order_id
GROUP BY o.customer_id;
```

Giải thích vì sao tổng tiền có thể bị nhân lên khi một đơn có nhiều sự kiện. Hãy đề xuất cách **tổng hợp `order_lines` thành một hàng mỗi đơn trước**, sau đó nếu chỉ muốn lọc “đơn từng có sự kiện loại X”, cân nhắc `EXISTS` để tránh JOIN tạo nhiều hàng.

Ví dụ cách lọc tồn tại sự kiện (giả sử bảng có cột `event_type`):

```sql
WITH order_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
)
SELECT o.customer_id, SUM(t.order_total) AS total_amount
FROM orders AS o
JOIN order_totals AS t ON t.order_id = o.order_id
WHERE EXISTS (
    SELECT 1
    FROM order_events AS e
    WHERE e.order_id = o.order_id
      AND e.event_type = 'SHIPPED'
)
GROUP BY o.customer_id;
```

`EXISTS` chỉ kiểm tra **có ít nhất một sự kiện khớp**, không nhân bản đơn theo số sự kiện. Đây là ví dụ thiết kế truy vấn; muốn chạy cần tạo bảng `order_events` theo mô hình ứng dụng riêng.

## Kết luận

Trong truy vấn tổng hợp, điều cần xác định trước tiên không phải `SUM` hay `COUNT`, mà là **grain — mỗi hàng đầu vào và đầu ra đại diện cho gì**.

- **Tính toán từng hàng** (như `quantity * unit_price`) không tự đổi grain.
- **`WHERE`** lọc các hàng trước khi nhóm.
- **`GROUP BY`** chuyển các hàng thành **một hàng mỗi tổ hợp khóa nhóm**; `SUM`, `COUNT`, `AVG` tính thước đo trên những nhóm ấy.
- **`HAVING`** lọc nhóm đã tổng hợp.
- **`JOIN`** có thể làm nhân hàng, nên phải kiểm tra grain trước khi đếm hoặc cộng; pre-aggregation và `COUNT(DISTINCT key)` giải quyết những mục đích khác nhau.
- **Hàm cửa sổ** giúp hiển thị số liệu nhóm mà **giữ lại các hàng chi tiết**, nhưng phải tránh cộng lặp số liệu đã được nhân ra.

Mỗi khi kết quả SQL trông đáng ngờ, hãy kiểm tra theo thứ tự: **một hàng đang đại diện cho gì → JOIN đã làm thay đổi số hàng chưa → đang lọc hàng hay lọc nhóm → thước đo được tính ở đúng grain chưa**. Tư duy này giúp báo cáo theo đơn, khách, trạng thái, tháng và nhiều chiều khác trở nên dễ kiểm chứng, có ý nghĩa nghiệp vụ và đáng tin cậy hơn.
