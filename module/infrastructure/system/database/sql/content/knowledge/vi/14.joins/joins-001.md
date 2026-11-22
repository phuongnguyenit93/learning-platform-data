# Quan hệ một-một, một-nhiều, nhiều-nhiều và lực lượng kết quả

## 1. Vì sao hiểu quan hệ chưa đủ để dự đoán số hàng JOIN?

Trong cơ sở dữ liệu quan hệ, bảng thường được kết nối qua **khóa chính (primary key, PK)** và **khóa ngoại (foreign key, FK)**. Để truy vấn đúng, người viết SQL cần phân biệt hai khái niệm:

- **Bội số quan hệ (relationship cardinality):** một bản ghi ở bảng A có thể liên kết với **bao nhiêu** bản ghi ở bảng B theo mô hình dữ liệu? Các dạng thường gặp là **một-một (1:1)**, **một-nhiều (1:N)** và **nhiều-nhiều (N:N)**.
- **Lực lượng kết quả (result cardinality):** một câu truy vấn cụ thể trả về **bao nhiêu hàng** sau `JOIN`, điều kiện `ON`, bộ lọc `WHERE`, tổng hợp và các phép khác?

Hai điều này liên quan với nhau nhưng **không đồng nhất**. Một quan hệ 1:N không nói rằng mọi khách hàng đều có đúng N đơn hàng, và `JOIN` một bảng cha với bảng con không nhất thiết trả một hàng cho mỗi bản ghi cha. Nếu một khách hàng có ba đơn hàng, `INNER JOIN` có thể tạo **ba hàng** mang cùng mã khách hàng.

Một số câu hỏi thường gặp:

1. Tại sao bảng `customers` có bốn người nhưng sau `JOIN orders` chỉ còn ba người và có bốn hàng?
2. Tại sao dùng `LEFT JOIN` vẫn có nhiều hàng hơn bảng bên trái?
3. Tại sao `COUNT(*)` đếm 1 cho khách hàng chưa có đơn hàng?
4. Tại sao tổng tiền tăng gấp đôi khi nối thêm bảng chi tiết đơn?
5. Khi nào `DISTINCT` là đúng nghiệp vụ, và khi nào nó chỉ che lỗi kết nối?

Bài học xây dựng một bộ dữ liệu nhỏ để lần lượt trả lời những câu hỏi này.

## 2. Từ quan hệ nghiệp vụ đến bảng và ràng buộc

Xét hệ thống bán hàng gồm năm bảng:

| Bảng | Ý nghĩa | Khóa chính |
| --- | --- | --- |
| `customers` | Khách hàng | `customer_id` |
| `customer_profiles` | Hồ sơ mở rộng, mỗi khách hàng có tối đa một hồ sơ | `customer_id` |
| `orders` | Đơn hàng, mỗi đơn thuộc một khách hàng | `order_id` |
| `products` | Sản phẩm | `product_id` |
| `order_items` | Những sản phẩm xuất hiện trong từng đơn hàng | `(order_id, product_id)` |

Sơ đồ quan hệ ở mức khái niệm:

~~~text
customers                            customer_profiles
  customer_id (PK)     1 ------ 0..1 customer_id (PK, FK)
  customer_name                      city
         |
         | 1
         |
         | 0..N
         v
      orders
       order_id (PK)
       customer_id (FK)
       status, total_amount
         |
         | 1
         |
         | 0..N
         v
      order_items                        products
       order_id (PK, FK)       0..N -- 1 product_id (PK)
       product_id (PK, FK)                product_name
       quantity                          unit_price
~~~

Đọc sơ đồ:

- Một **khách hàng** có **0 hoặc 1 hồ sơ**, một hồ sơ thuộc đúng một khách hàng.
- Một **khách hàng** có **0, 1 hoặc nhiều đơn hàng**; mỗi đơn hàng phải thuộc đúng một khách hàng.
- Một **đơn hàng** có thể có nhiều dòng sản phẩm; mỗi dòng thuộc đúng một đơn.
- Một **sản phẩm** có thể xuất hiện trong nhiều đơn hàng; mỗi dòng chỉ tham chiếu một sản phẩm.
- Vì thế, **orders ↔ products là quan hệ N:N**, được biểu diễn thông qua bảng `order_items`.

Ký hiệu `0..N` là *khả năng theo ràng buộc hiện tại*, không khẳng định ứng dụng kinh doanh thật sự cho phép hoàn tất đơn rỗng. Ràng buộc “mỗi đơn đã thanh toán phải có ít nhất một dòng hàng” thường cần logic giao dịch hoặc thiết kế bổ sung.

### Tạo bảng thực hành

Các ví dụ sử dụng cú pháp SQL phổ biến, chạy gần như trực tiếp trên PostgreSQL và có thể điều chỉnh nhỏ khi dùng MySQL, SQL Server hoặc SQLite.

~~~sql
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL
);

CREATE TABLE customer_profiles (
    customer_id INTEGER PRIMARY KEY,
    city        VARCHAR(80) NOT NULL,
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
);

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    status       VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT chk_total_amount
        CHECK (total_amount >= 0)
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL,
    unit_price   DECIMAL(12, 2) NOT NULL
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_item_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT fk_item_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT chk_quantity
        CHECK (quantity > 0)
);
~~~

Ở bảng `customer_profiles`, `customer_id` vừa là **khóa chính** vừa là **khóa ngoại**. Do khóa chính không được trùng, một khách hàng có tối đa một hồ sơ. Đây là mẫu **shared primary key** cho quan hệ 1:1.

Ở bảng `orders`, `customer_id` là `NOT NULL` và là khóa ngoại, **nhưng không có `UNIQUE`**, nên nhiều đơn hàng có thể cùng tham chiếu một khách hàng. Đây là quan hệ 1:N.

Ở bảng `order_items`, cặp `(order_id, product_id)` là khóa chính tổng hợp: một sản phẩm không xuất hiện **hai dòng riêng** trong cùng một đơn, nhưng vẫn có thể xuất hiện trong nhiều đơn khác. Bảng trung gian này lưu thêm `quantity`, gọi là **thuộc tính của quan hệ**.

### Thêm dữ liệu mẫu

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO customer_profiles (customer_id, city)
VALUES
    (1, 'Ha Noi'),
    (3, 'Da Nang'),
    (4, 'Hue');

INSERT INTO orders (order_id, customer_id, status, total_amount)
VALUES
    (101, 1, 'PAID',    130000.00),
    (102, 1, 'PAID',    800000.00),
    (103, 2, 'PENDING',  50000.00),
    (104, 4, 'PAID',   1000000.00);

INSERT INTO products (product_id, product_name, unit_price)
VALUES
    (10, 'So tay',   50000.00),
    (20, 'But bi',   10000.00),
    (30, 'Ban phim', 750000.00),
    (40, 'Chuot',    250000.00),
    (50, 'May in',  1500000.00);

INSERT INTO order_items (order_id, product_id, quantity)
VALUES
    (101, 10, 2),
    (101, 20, 3),
    (102, 10, 1),
    (102, 30, 1),
    (103, 20, 5),
    (104, 30, 1),
    (104, 40, 1);
~~~

Các số lượng để ghi nhớ:

| Bảng | Số hàng | Chi tiết đáng chú ý |
| --- | ---: | --- |
| `customers` | 4 | An, Binh, Chi, Dung |
| `customer_profiles` | 3 | Binh chưa có hồ sơ |
| `orders` | 4 | An có 2 đơn, Chi không có đơn |
| `products` | 5 | May in chưa từng xuất hiện trong đơn |
| `order_items` | 7 | Các đơn 101, 102, 104 có 2 dòng; đơn 103 có 1 dòng |

Trong ví dụ, `orders.total_amount` là tổng tiền đã ghi nhận cho đơn. Các giá trị được chọn nhất quán với giá và số lượng mẫu, nhưng trong hệ thống thật giá sản phẩm hiện tại có thể khác giá tại thời điểm đặt đơn. Khi phân tích lịch sử cần lưu giá bán tại thời điểm giao dịch ở dòng đơn nếu nghiệp vụ yêu cầu.

## 3. Quan hệ một-một (1:1): mỗi bên nhiều nhất một hàng khớp

### 3.1. Cách biểu diễn bằng khóa ngoại duy nhất

Quan hệ `customers → customer_profiles` là:

~~~text
Khách hàng 1 (An)   ───── Hồ sơ 1 (Ha Noi)
Khách hàng 2 (Binh) ───── [chưa có hồ sơ]
Khách hàng 3 (Chi)  ───── Hồ sơ 3 (Da Nang)
Khách hàng 4 (Dung) ───── Hồ sơ 4 (Hue)
~~~

Điều kiện `customer_profiles.customer_id` là `PRIMARY KEY` đảm bảo **một khách hàng không thể có hai hồ sơ**. Khóa ngoại đảm bảo một hồ sơ không trỏ tới khách hàng không tồn tại. Nhưng schema **không bắt buộc mọi khách hàng phải có hồ sơ**: Binh hoàn toàn hợp lệ khi chưa có bản ghi `customer_profiles`.

Cần phân biệt:

- **1:0..1:** mỗi khách hàng có 0 hoặc 1 hồ sơ, như ví dụ.
- **1:1 bắt buộc cả hai phía:** mỗi khách hàng cũng phải có hồ sơ và ngược lại. Khóa ngoại duy nhất trong một bảng **chưa tự đảm bảo** phía khách hàng bắt buộc có bản ghi tương ứng. Muốn ràng buộc hai phía phải có thiết kế và quy trình ghi phù hợp, hoặc mô hình dữ liệu khác.

### 3.2. INNER JOIN: chỉ các cặp có mặt ở cả hai bảng

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    p.city
FROM customers AS c
INNER JOIN customer_profiles AS p
    ON p.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | city |
| ---: | --- | --- |
| 1 | An | Ha Noi |
| 3 | Chi | Da Nang |
| 4 | Dung | Hue |

**Lực lượng kết quả: 3 hàng.** Binh không có hồ sơ nên không có cặp khớp và bị loại khỏi `INNER JOIN`.

Với quan hệ 1:1 được ràng buộc đúng, mỗi hàng ở phía khách hàng tạo **tối đa một cặp khớp**. Do đó phép nối này không thể làm tăng số hàng vượt quá bốn hàng khách hàng chỉ bằng việc ghép với hồ sơ. Nhưng nó có thể **giảm** số hàng vì các khách hàng không có hồ sơ.

### 3.3. LEFT JOIN: giữ cả khách hàng không có hồ sơ

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    p.city
FROM customers AS c
LEFT JOIN customer_profiles AS p
    ON p.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | city |
| ---: | --- | --- |
| 1 | An | Ha Noi |
| 2 | Binh | NULL |
| 3 | Chi | Da Nang |
| 4 | Dung | Hue |

**Lực lượng kết quả: 4 hàng.** `LEFT JOIN` giữ mọi khách hàng; ở hàng Binh, các cột từ phía hồ sơ có giá trị `NULL` vì không có bản ghi khớp.

Một truy vấn để tìm người **chưa có hồ sơ**:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
LEFT JOIN customer_profiles AS p
    ON p.customer_id = c.customer_id
WHERE p.customer_id IS NULL
ORDER BY c.customer_id;
-- 2, Binh
~~~

`p.customer_id` là khóa chính không `NULL` trong bản ghi hồ sơ thật, nên điều kiện `IS NULL` ở đây nhận biết hàng bên phải không khớp. Mẫu tương đương về mục đích thường là `NOT EXISTS`.

## 4. Quan hệ một-nhiều (1:N): hàng cha có thể lặp trong kết quả

### 4.1. Một khách hàng có nhiều đơn

~~~text
An   (customer_id = 1) ──► 101
                         └─► 102
Binh (customer_id = 2) ──► 103
Chi  (customer_id = 3) ──► [không có đơn]
Dung (customer_id = 4) ──► 104
~~~

Mỗi đơn chỉ có một `customer_id`, nhưng một mã khách hàng có thể xuất hiện trong nhiều dòng của bảng `orders`. Cách đặt `FOREIGN KEY` đảm bảo giá trị tham chiếu hợp lệ, **không giới hạn số đơn mỗi khách hàng**.

### 4.2. INNER JOIN: một hàng cho mỗi cặp khách hàng–đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

| customer_id | customer_name | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 101 | PAID |
| 1 | An | 102 | PAID |
| 2 | Binh | 103 | PENDING |
| 4 | Dung | 104 | PAID |

**Lực lượng kết quả: 4 hàng**, dù chỉ có **3 khách hàng khác nhau** trong kết quả.

- An xuất hiện hai lần vì có hai đơn.
- Binh và Dung mỗi người xuất hiện một lần.
- Chi không xuất hiện vì không có đơn.

Đây **không phải dữ liệu bị trùng sai**: mỗi hàng có `order_id` khác nhau và biểu diễn một quan hệ khách hàng–đơn hàng thực tế.

### 4.3. LEFT JOIN không có nghĩa “mỗi khách hàng đúng một hàng”

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

| customer_id | customer_name | order_id |
| ---: | --- | ---: |
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Binh | 103 |
| 3 | Chi | NULL |
| 4 | Dung | 104 |

**Lực lượng kết quả: 5 hàng**, lớn hơn số khách hàng là 4.

`LEFT JOIN` đảm bảo mỗi hàng bên trái được bảo toàn **ít nhất một hàng đầu ra** trước khi áp dụng bộ lọc tiếp theo. Nếu một khách hàng có hai đơn, khách hàng đó vẫn tạo hai hàng đầu ra; nếu không có đơn, nó tạo một hàng bổ sung với các cột đơn hàng là `NULL`.

### 4.4. Đếm đúng số đơn theo khách hàng

Một mục tiêu khác là **mỗi khách hàng đúng một hàng kết quả**, kèm số đơn. Khi đó phải **gom nhóm**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | order_count |
| ---: | --- | ---: |
| 1 | An | 2 |
| 2 | Binh | 1 |
| 3 | Chi | 0 |
| 4 | Dung | 1 |

**Vì sao `COUNT(o.order_id)` mà không phải `COUNT(*)`?**

Với Chi, `LEFT JOIN` tạo **một hàng có `o.order_id = NULL`**:

- `COUNT(*)` đếm hàng kết quả, nên trả **1**.
- `COUNT(o.order_id)` chỉ đếm giá trị `order_id` **khác `NULL`**, nên trả **0**.

Khi đếm số bản ghi bên phải trong một `LEFT JOIN`, hãy đếm **một cột không `NULL` của bản ghi thật bên phải**, thường là khóa chính.

## 5. Quan hệ nhiều-nhiều (N:N): cần bảng trung gian

Một đơn có thể chứa nhiều sản phẩm; một sản phẩm có thể nằm trong nhiều đơn. Nếu chỉ đặt `product_id` duy nhất vào `orders`, mỗi đơn sẽ bị giới hạn tối đa một sản phẩm. Nếu đặt danh sách mã sản phẩm như chuỗi `'10,20,30'` trong một ô, truy vấn, ràng buộc và cập nhật trở nên khó khăn.

Thiết kế quan hệ chuẩn dùng **bảng trung gian** `order_items`:

~~~text
orders          order_items               products
  101 ──────► (101, 10, 2) ───────────► 10: So tay
       └────► (101, 20, 3) ───────────► 20: But bi

  102 ──────► (102, 10, 1) ───────────► 10: So tay
       └────► (102, 30, 1) ───────────► 30: Ban phim

  103 ──────► (103, 20, 5) ───────────► 20: But bi

  104 ──────► (104, 30, 1) ───────────► 30: Ban phim
       └────► (104, 40, 1) ───────────► 40: Chuot

  Không đơn nào ──────────────────────► 50: May in
~~~

Hai quan hệ 1:N với bảng trung gian tạo thành một quan hệ N:N:

~~~text
orders 1 ─── 0..N order_items N..0 ─── 1 products
                 ↑
      mỗi hàng: một đơn + một sản phẩm
~~~

Cặp khóa chính `(order_id, product_id)` ngăn hai dòng cho cùng sản phẩm trong cùng đơn. Nó **không** ngăn sản phẩm xuất hiện ở nhiều đơn, vì `order_id` khác nhau.

### 5.1. JOIN ba bảng tạo một hàng cho mỗi dòng đơn

~~~sql
SELECT
    o.order_id,
    p.product_id,
    p.product_name,
    oi.quantity
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
ORDER BY o.order_id, p.product_id;
~~~

| order_id | product_id | product_name | quantity |
| ---: | ---: | --- | ---: |
| 101 | 10 | So tay | 2 |
| 101 | 20 | But bi | 3 |
| 102 | 10 | So tay | 1 |
| 102 | 30 | Ban phim | 1 |
| 103 | 20 | But bi | 5 |
| 104 | 30 | Ban phim | 1 |
| 104 | 40 | Chuot | 1 |

**Lực lượng kết quả: 7 hàng** — đúng bằng số dòng `order_items` vì mỗi dòng có một đơn và một sản phẩm tương ứng theo khóa ngoại hợp lệ.

Không phải `4 đơn + 5 sản phẩm = 9 hàng`, cũng không phải `4 × 5 = 20 hàng`. Số hàng JOIN phụ thuộc **bao nhiêu cặp thực sự thỏa điều kiện nối**.

### 5.2. Khách hàng mua sản phẩm: hai khách hàng có thể mua cùng một loại

Nối thêm `customers`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    p.product_id,
    p.product_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
ORDER BY c.customer_id, o.order_id, p.product_id;
~~~

Truy vấn trả **7 hàng**, một hàng cho mỗi **dòng đơn**. An mua `So tay` ở cả đơn 101 lẫn đơn 102, nên cặp `(An, So tay)` xuất hiện hai lần. Điều này đúng nếu câu hỏi là **“mỗi lần khách hàng đặt một sản phẩm trong đơn nào?”**

Nếu câu hỏi đổi thành **“khách hàng đã từng mua những loại sản phẩm nào?”**, cần loại trùng **cặp khách hàng–sản phẩm**:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.customer_name,
    p.product_id,
    p.product_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
ORDER BY c.customer_id, p.product_id;
~~~

Kết quả có **6 cặp khách hàng–sản phẩm khác nhau**:

| customer_id | customer_name | product_id | product_name |
| ---: | --- | ---: | --- |
| 1 | An | 10 | So tay |
| 1 | An | 20 | But bi |
| 1 | An | 30 | Ban phim |
| 2 | Binh | 20 | But bi |
| 4 | Dung | 30 | Ban phim |
| 4 | Dung | 40 | Chuot |

`DISTINCT` ở đây **phù hợp nghiệp vụ** vì câu hỏi chỉ quan tâm tập loại sản phẩm mỗi khách hàng đã mua, không quan tâm mỗi loại xuất hiện trong bao nhiêu đơn.

### 5.3. Nếu cần số lượng mua, đừng chỉ dùng DISTINCT

Với An, `So tay` được mua tổng cộng **3 quyển**: 2 ở đơn 101 và 1 ở đơn 102. Một truy vấn chỉ dùng `DISTINCT` sẽ mất thông tin số lượng từng đơn.

Muốn tổng hợp số lượng theo loại sản phẩm và khách hàng:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    p.product_id,
    p.product_name,
    SUM(oi.quantity) AS total_units
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
GROUP BY
    c.customer_id,
    c.customer_name,
    p.product_id,
    p.product_name
ORDER BY c.customer_id, p.product_id;
~~~

Kết quả vẫn có **6 hàng**, nhưng cột `total_units` cho biết lượng mua:

| Khách hàng | Sản phẩm | total_units |
| --- | --- | ---: |
| An | So tay | 3 |
| An | But bi | 3 |
| An | Ban phim | 1 |
| Binh | But bi | 5 |
| Dung | Ban phim | 1 |
| Dung | Chuot | 1 |

Mọi truy vấn phải bắt đầu từ việc xác định **“một hàng kết quả đại diện cho cái gì?”**: khách hàng, đơn hàng, dòng đơn, cặp khách hàng–sản phẩm, hay một nhóm đã tổng hợp?

## 6. Lực lượng kết quả của JOIN: quy tắc đếm chính xác

### 6.1. INNER JOIN đếm các cặp hàng khớp, không tự cộng số hàng hai bảng

Xét:

~~~sql
SELECT ...
FROM A
INNER JOIN B ON <dieu_kien>;
~~~

Mỗi cặp hàng `(a, b)` thỏa điều kiện `ON` tạo một hàng kết quả. Nếu một hàng A khớp **3 hàng B**, nó tạo **3 hàng**. Nếu không khớp, nó tạo **0 hàng**.

Với một bảng A cố định, gọi `m(a)` là số hàng B khớp với hàng `a`, thì:

~~~text
Số hàng A INNER JOIN B = tổng m(a), qua mọi hàng a thuộc A.
~~~

Ví dụ `customers INNER JOIN orders`:

| Khách hàng | Số đơn khớp `m(a)` | Số hàng đóng góp |
| --- | ---: | ---: |
| An | 2 | 2 |
| Binh | 1 | 1 |
| Chi | 0 | 0 |
| Dung | 1 | 1 |
| **Tổng** | **4** | **4** |

Nếu điều kiện `ON` là phép bằng theo khóa ngoại trỏ tới khóa chính duy nhất, **một hàng con khớp tối đa một hàng cha**. Khi FK được kiểm tra, khác `NULL` và không có bộ lọc loại cha, nối từ bảng con về bảng cha thường giữ **đúng số hàng con**. Nhưng nối từ cha sang con có thể nhân hàng.

### 6.2. LEFT JOIN đếm tối thiểu một hàng cho mỗi hàng bên trái

Trong `A LEFT JOIN B`, một hàng A khớp `m(a)` hàng B sẽ đóng góp:

- `m(a)` hàng nếu `m(a) > 0`;
- **1 hàng chứa phần bên phải `NULL`** nếu `m(a) = 0`.

Có thể biểu diễn:

~~~text
Số hàng A LEFT JOIN B = tổng max(1, m(a)), qua mọi a thuộc A.
~~~

Áp dụng cho `customers LEFT JOIN orders`:

| Khách hàng | `m(a)` | Số hàng đóng góp |
| --- | ---: | ---: |
| An | 2 | 2 |
| Binh | 1 | 1 |
| Chi | 0 | 1 |
| Dung | 1 | 1 |
| **Tổng** | **4** | **5** |

**Quan trọng:** đây là số hàng **trước những điều kiện lọc `WHERE` đặt ở bên ngoài JOIN**. Một `WHERE` sau đó có thể loại cả những hàng do `LEFT JOIN` giữ lại.

### 6.3. Với nhiều JOIN, số hàng có thể tăng qua từng bước

Khi nối liên tiếp:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    oi.product_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
ORDER BY c.customer_id, o.order_id, oi.product_id;
~~~

Số hàng đầu ra là **8 hàng**:

- An: đơn 101 có 2 dòng, đơn 102 có 2 dòng → **4 hàng**.
- Binh: đơn 103 có 1 dòng → **1 hàng**.
- Chi: không có đơn → **1 hàng `NULL`**.
- Dung: đơn 104 có 2 dòng → **2 hàng**.

Tổng `4 + 1 + 1 + 2 = 8`. Đây là một ví dụ rõ ràng rằng **hai `LEFT JOIN` có thể làm lực lượng kết quả lớn hơn cả bảng gốc lẫn số đơn**.

Trong SQL có nhiều quan hệ 1:N độc lập, mỗi JOIN có thể tiếp tục nhân số kết hợp. Tránh dự đoán số hàng chỉ bằng số bảng tham gia.

### 6.4. CROSS JOIN: tích Descartes

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
CROSS JOIN orders AS o
ORDER BY c.customer_id, o.order_id;
~~~

`customers` có 4 hàng, `orders` có 4 hàng; `CROSS JOIN` tạo **4 × 4 = 16 hàng**. Mọi khách hàng được ghép với mọi đơn, **không kiểm tra** `o.customer_id = c.customer_id`.

`CROSS JOIN` hợp lệ khi muốn tạo mọi tổ hợp (ví dụ mọi ngày × mọi chi nhánh), nhưng là một nguyên nhân phổ biến khiến truy vấn trả quá nhiều hàng khi người viết quên điều kiện nối hoặc vô tình viết phép nối không hạn chế.

## 7. Vị trí điều kiện ON và WHERE ảnh hưởng mạnh đến kết quả

Với `INNER JOIN` đơn giản, việc chuyển một điều kiện lọc phù hợp giữa `ON` và `WHERE` thường giữ cùng kết quả logic. Với **`LEFT JOIN`**, hai vị trí này có ý nghĩa khác nhau.

### 7.1. Lọc trong ON: vẫn giữ mọi khách hàng

Muốn hiển thị mọi khách hàng, kèm các đơn **đã thanh toán** nếu có:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

| Khách hàng | order_id | status |
| --- | ---: | --- |
| An | 101 | PAID |
| An | 102 | PAID |
| Binh | NULL | NULL |
| Chi | NULL | NULL |
| Dung | 104 | PAID |

**5 hàng.** Binh có đơn 103 nhưng không có đơn `PAID` nên ở phép nối này Binh được coi là **không có hàng bên phải khớp điều kiện `ON`**, và vẫn được giữ.

### 7.2. Lọc trong WHERE: loại khách hàng không có đơn PAID

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Truy vấn chỉ còn **3 hàng**: `(An, 101)`, `(An, 102)`, `(Dung, 104)`.

Vì ở các hàng không có đơn `o.status` là `NULL`, điều kiện `o.status = 'PAID'` cho `UNKNOWN` và `WHERE` loại chúng. Trên dữ liệu này, kết quả tương đương `INNER JOIN` các đơn `PAID`.

Nếu mục tiêu là **đếm số đơn PAID của mọi khách hàng**, đặt điều kiện trong `ON` và dùng `COUNT(o.order_id)`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả: An **2**, Binh **0**, Chi **0**, Dung **1**.

Đừng tự ý thay bằng `WHERE o.status = 'PAID' OR o.order_id IS NULL` để “giữ lại khách hàng không có đơn”: khách hàng **chỉ có đơn PENDING** như Binh sẽ không có hàng `o.order_id IS NULL` ở phép nối chưa lọc, nên vẫn bị loại. Muốn giữ mọi khách hàng, điều kiện chọn đơn phù hợp nên nằm trong `ON` hoặc trong nguồn con được lọc từ trước.

## 8. Bẫy lớn: tổng và số đếm bị nhân sau JOIN

### 8.1. Đếm đơn trong một phép nối gồm cả dòng đơn

Xem câu SQL:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả `order_count` bị **phóng đại** cho những khách hàng có đơn nhiều dòng:

| customer_id | COUNT(o.order_id) | Số đơn thật |
| ---: | ---: | ---: |
| 1 | 4 | 2 |
| 2 | 1 | 1 |
| 3 | 0 | 0 |
| 4 | 2 | 1 |

Vì `o.order_id` xuất hiện lặp lại **theo từng dòng `order_items`**, `COUNT(o.order_id)` đang đếm **số dòng đã nối**, không còn đếm số đơn duy nhất.

Khi vẫn cần nối bảng chi tiết, có thể đếm:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(oi.product_id) AS item_line_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| Khách hàng | order_count | item_line_count |
| --- | ---: | ---: |
| An | 2 | 4 |
| Binh | 1 | 1 |
| Chi | 0 | 0 |
| Dung | 1 | 2 |

`COUNT(DISTINCT o.order_id)` đếm **đơn khác nhau**, còn `COUNT(oi.product_id)` đếm **dòng đơn**. Hai con số trả lời hai câu hỏi khác nhau.

`COUNT(DISTINCT ...)` phù hợp khi yêu cầu số khóa duy nhất và có thể tốn thêm chi phí loại trùng. Nó không phải giải pháp chung cho mọi phép tổng hợp.

### 8.2. SUM của bảng cha bị cộng lặp

Tổng tiền đơn hàng thực tế:

~~~sql
SELECT SUM(total_amount) AS correct_total
FROM orders;
-- 1.980.000
~~~

Chi tiết:

| order_id | total_amount | Số dòng chi tiết |
| ---: | ---: | ---: |
| 101 | 130000.00 | 2 |
| 102 | 800000.00 | 2 |
| 103 | 50000.00 | 1 |
| 104 | 1000000.00 | 2 |

Nếu nối với `order_items` rồi cộng cột ở bảng `orders`:

~~~sql
-- SAI nếu muốn tổng tiền của mỗi đơn đúng một lần.
SELECT SUM(o.total_amount) AS inflated_total
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id;
-- 3.910.000
~~~

Vì `order_id = 101` xuất hiện hai dòng chi tiết, `130000` bị cộng **hai lần**. Tương tự các đơn 102 và 104:

~~~text
130.000 × 2 + 800.000 × 2 + 50.000 × 1 + 1.000.000 × 2
= 3.910.000
~~~

Đây là **fanout**: một giá trị ở phía “một” bị lặp khi JOIN sang phía “nhiều”.

Không nên “sửa” bằng:

~~~sql
-- KHÔNG đúng một cách tổng quát.
SELECT SUM(DISTINCT o.total_amount)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id;
~~~

`SUM(DISTINCT o.total_amount)` khử trùng theo **giá trị số tiền**, không theo **mã đơn**. Nếu hai đơn khác nhau cùng có số tiền `130000`, phép tổng trên chỉ cộng `130000` một lần, làm mất giá trị của một đơn thật.

### 8.3. Cách sửa: tổng hợp ở đúng mức hạt dữ liệu

Nếu chỉ cần tổng tiền đơn hàng, **không nối bảng dòng đơn**:

~~~sql
SELECT SUM(total_amount) AS total_order_amount
FROM orders;
~~~

Nếu cần một hàng cho mỗi khách hàng, tổng hợp trước ở cấp **khách hàng–đơn hàng**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.total_amount), 0) AS total_order_amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| Khách hàng | total_order_amount |
| --- | ---: |
| An | 930000.00 |
| Binh | 50000.00 |
| Chi | 0.00 |
| Dung | 1000000.00 |

Nếu báo cáo cần **cả tổng tiền đơn và số dòng sản phẩm**, tính hai chỉ số ở các nguồn tổng hợp riêng rồi nối về khách hàng:

~~~sql
WITH order_totals AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
),
item_totals AS (
    SELECT
        o.customer_id,
        COUNT(*) AS item_line_count,
        SUM(oi.quantity) AS total_units
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(ot.order_count, 0) AS order_count,
    COALESCE(ot.total_amount, 0) AS total_order_amount,
    COALESCE(it.item_line_count, 0) AS item_line_count,
    COALESCE(it.total_units, 0) AS total_units
FROM customers AS c
LEFT JOIN order_totals AS ot
    ON ot.customer_id = c.customer_id
LEFT JOIN item_totals AS it
    ON it.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Mỗi CTE chỉ trả **tối đa một hàng cho mỗi khách hàng** nhờ `GROUP BY customer_id`. Khi nối hai tập tổng hợp này về `customers`, không còn hiện tượng một đơn nhân đôi tổng tiền vì dòng sản phẩm.

Kết quả dự kiến:

| Khách hàng | order_count | total_order_amount | item_line_count | total_units |
| --- | ---: | ---: | ---: | ---: |
| An | 2 | 930000.00 | 4 | 7 |
| Binh | 1 | 50000.00 | 1 | 5 |
| Chi | 0 | 0.00 | 0 | 0 |
| Dung | 1 | 1000000.00 | 2 | 2 |

**Nguyên tắc mức hạt (grain):** trước khi JOIN để tính tổng, phải biết **một hàng mỗi nguồn đại diện cho cái gì**. Nếu một bên là đơn hàng, một bên là dòng đơn, đừng cộng giá trị tiền của đơn sau khi đã mở rộng thành nhiều dòng.

## 9. Hai quan hệ một-nhiều độc lập có thể nhân chéo

Không chỉ bảng trung gian mới khiến số hàng tăng. Nếu từ một bảng cha nối với **hai tập con độc lập**, các tổ hợp con có thể nhân nhau.

Ví dụ cố ý tự nối bảng `orders` hai lần để xem mọi cặp đơn của An:

~~~sql
SELECT
    c.customer_id,
    o1.order_id AS first_order,
    o2.order_id AS second_order
FROM customers AS c
JOIN orders AS o1
    ON o1.customer_id = c.customer_id
JOIN orders AS o2
    ON o2.customer_id = c.customer_id
WHERE c.customer_id = 1
ORDER BY o1.order_id, o2.order_id;
~~~

An có hai đơn: 101 và 102. Kết quả có **2 × 2 = 4 hàng**:

| customer_id | first_order | second_order |
| ---: | ---: | ---: |
| 1 | 101 | 101 |
| 1 | 101 | 102 |
| 1 | 102 | 101 |
| 1 | 102 | 102 |

Nếu mục đích là tạo **cặp hai đơn khác nhau, không xét chiều**, cần thêm ràng buộc:

~~~sql
WHERE c.customer_id = 1
  AND o1.order_id < o2.order_id
~~~

Khi đó chỉ còn cặp `(101, 102)`.

Trong báo cáo thực tế, lỗi tương tự có thể xảy ra khi nối đồng thời **orders**, **addresses**, **payments**, **tickets** hay các bảng con khác cùng dựa vào một khách hàng mà không xử lý đúng mức hạt. Nếu mỗi khách hàng có 3 đơn và 2 địa chỉ, phép nối độc lập có thể tạo **6 tổ hợp**, rồi nhân các chỉ số `SUM`/`COUNT` không mong muốn.

## 10. Các cách lấy “một hàng cho mỗi đối tượng” mà không làm nổ số hàng

### 10.1. EXISTS: hỏi “có ít nhất một bản ghi liên quan không?”

Nếu chỉ cần **danh sách khách hàng có đơn `PAID`**, không cần thông tin từng đơn:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả có **2 hàng**: An và Dung. `EXISTS` kiểm tra **có hay không có** hàng khớp, không tạo hai hàng An vì An có hai đơn đã thanh toán.

Nếu viết `INNER JOIN orders` rồi `DISTINCT`, kết quả có thể giống trong bài toán nhỏ, nhưng `EXISTS` thường biểu đạt ý nghĩa “ít nhất một” rõ hơn và có thể được DBMS tối ưu như phép nối bán phần (*semi-join*).

### 10.2. NOT EXISTS: tìm đối tượng chưa có bản ghi liên quan

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
-- 3, Chi
~~~

Mẫu này thích hợp khi câu hỏi là **không tồn tại bản ghi con**, không cần lấy cột từ bản ghi con. Nó cũng tránh một số bẫy `NOT IN` khi dữ liệu có `NULL`.

### 10.3. GROUP BY: một hàng cho mỗi nhóm

~~~sql
SELECT
    customer_id,
    COUNT(*) AS number_of_orders,
    SUM(total_amount) AS amount
FROM orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Truy vấn trên trả **3 hàng**, một hàng cho mỗi khách hàng **có đơn**. Nếu muốn giữ khách hàng không có đơn, nối kết quả tổng hợp này với bảng `customers` bằng `LEFT JOIN`.

### 10.4. ROW_NUMBER: chọn một bản ghi con theo quy tắc

Nếu yêu cầu là “lấy **đơn có mã lớn nhất** của mỗi khách hàng”, dùng hàm cửa sổ:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.order_id DESC
        ) AS rn
    FROM orders AS o
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id,
    r.status
FROM customers AS c
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
~~~

Kết quả có **4 hàng**: An–102, Binh–103, Chi–`NULL`, Dung–104.

`ROW_NUMBER()` chọn một bản ghi trong nhóm theo thứ tự đã viết. **Đơn có mã lớn nhất chưa chắc là đơn mới nhất theo thời gian** trong mọi hệ thống. Nếu yêu cầu “mới nhất”, hãy dùng cột thời gian thích hợp và khóa duy nhất phá hòa, ví dụ `ORDER BY ordered_at DESC, order_id DESC` khi schema có `ordered_at`.

## 11. Ràng buộc dữ liệu quyết định bội số thật của quan hệ

### 11.1. Khóa chính và UNIQUE hạn chế số cặp khớp

Một khóa chính đảm bảo mỗi giá trị khóa xác định **tối đa một hàng** trong bảng. Vì thế khi `orders.customer_id` trỏ tới `customers.customer_id`, mỗi đơn khớp tối đa một khách hàng.

Một cột `FOREIGN KEY` được thêm `UNIQUE` có thể hạn chế phía con từ 1:N về 1:0..1:

~~~sql
-- Ví dụ một thiết kế hồ sơ với cột riêng:
CREATE TABLE customer_settings (
    settings_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL UNIQUE,
    language_code VARCHAR(10) NOT NULL,
    FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
);
~~~

Ở đây mỗi khách hàng có tối đa một `customer_settings` vì `customer_id` là `UNIQUE`. Nếu bỏ `UNIQUE`, nhiều hàng settings có thể cùng trỏ một khách hàng, trở thành 1:N.

Trong thực tế, quy tắc xử lý `NULL` trong cột `UNIQUE` khác nhau giữa DBMS. Ví dụ dùng `NOT NULL` để tránh nhập nhằng về ý nghĩa tham gia quan hệ.

### 11.2. Khóa ngoại không tự tạo dữ liệu con

`FOREIGN KEY` đảm bảo **dữ liệu tham chiếu hợp lệ** khi constraint thực sự được DBMS thực thi. Nó **không tự sinh** đơn hàng cho mỗi khách hàng. Do đó tồn tại Chi mà không có đơn là bình thường.

Ràng buộc 1:N không nói tất cả hàng cha phải có ít nhất một con. Nếu nghiệp vụ bắt buộc, cần quy trình cập nhật hoặc cơ chế ràng buộc bổ sung; một FK đơn giản chỉ kiểm tra hướng tham chiếu từ con về cha.

### 11.3. Khóa nối sai hoặc thiếu ràng buộc tạo kết quả bất thường

Nếu JOIN dùng cột **không duy nhất** ở phía mong đợi “một”, số hàng có thể tăng ngoài dự đoán. Ví dụ nối theo tên khách hàng thay vì mã duy nhất có thể kết hợp nhầm những người trùng tên.

Nên thiết kế và sử dụng khóa **ổn định, phù hợp ràng buộc**, không chỉ dựa vào dữ liệu mẫu hiện tại. Điều kiện nối thường xuất phát từ FK–PK hoặc khóa ứng viên (candidate key) có `UNIQUE`.

Cũng không nên viết:

~~~sql
-- Không nêu quan hệ giữa đơn và khách hàng:
SELECT c.customer_name, o.order_id
FROM customers AS c
CROSS JOIN orders AS o;
~~~

chỉ vì kết quả có đủ cả hai loại thông tin. Cột xuất hiện cạnh nhau trong một hàng **không có nghĩa quan hệ nghiệp vụ giữa chúng đúng**.

## 12. Cardinality ước lượng và hiệu năng truy vấn

DBMS phải ước lượng số hàng qua từng bước JOIN để chọn thứ tự nối, thuật toán và bộ nhớ. Trong kế hoạch thực thi thường có khái niệm **estimated rows** và, ở những công cụ hỗ trợ, **actual rows**.

Với PostgreSQL, có thể xem ví dụ:

~~~sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id,
    oi.product_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id;
~~~

Hoặc đo bằng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    o.order_id,
    oi.product_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id;
~~~

`ANALYZE` thực sự chạy truy vấn. Với `SELECT` này chỉ là đọc; với câu `INSERT`, `UPDATE`, `DELETE` phải cẩn trọng về tác động nếu phân tích thực thi.

Nếu bộ tối ưu ước lượng sai bội số do dữ liệu phân bố lệch, cột tương quan hoặc thống kê cũ, kế hoạch JOIN có thể không hiệu quả. Dù tối ưu thế nào, kết quả đúng vẫn tuân theo ngữ nghĩa của điều kiện JOIN và các phép lọc.

Các chỉ mục thường hữu ích cho khóa nối:

~~~sql
CREATE INDEX idx_orders_customer_id
    ON orders (customer_id);

CREATE INDEX idx_items_product_id
    ON order_items (product_id);
~~~

`order_items` đã có khóa chính tổng hợp `(order_id, product_id)`; nhiều DBMS tạo chỉ mục tương ứng với khóa chính, có thể hỗ trợ tìm các dòng theo `order_id`. Tuy nhiên đường truy vấn từ **product_id** sang các dòng `order_items` có thể cần chỉ mục bắt đầu bằng `product_id`.

**Không phải DBMS nào cũng tự tạo chỉ mục ở cột FK của bảng con.** PostgreSQL không mặc định tạo chỉ mục riêng cho `orders.customer_id` chỉ vì có FK; các engine khác có hành vi riêng. Việc thêm chỉ mục cần cân nhắc khối lượng dữ liệu, độ chọn lọc, chi phí ghi và kế hoạch thực thi thay vì áp dụng mọi nơi một cách máy móc.

## 13. Tính khả chuyển và các tình huống dễ hiểu sai

### 13.1. Các loại JOIN cơ bản

`INNER JOIN`, `LEFT JOIN`, `CROSS JOIN` và cú pháp `JOIN ... ON` được hỗ trợ rộng rãi trong các hệ SQL phổ biến. Tuy nhiên `RIGHT JOIN`/`FULL OUTER JOIN` không được hỗ trợ đồng nhất ở mọi DBMS hoặc phiên bản.

Khái niệm bội số không phụ thuộc dialect: khi một hàng khớp N hàng, `INNER JOIN` tạo N cặp; khi không khớp và dùng `LEFT JOIN`, hàng bên trái được bảo toàn theo quy tắc hàng `NULL` bên phải.

### 13.2. NULL trong điều kiện nối

~~~sql
ON a.some_code = b.some_code
~~~

Nếu một hoặc cả hai mã bằng `NULL`, phép so sánh `=` thường cho `UNKNOWN`, **không tạo cặp khớp**. Nếu nghiệp vụ muốn coi hai mã cùng `NULL` là khớp, có thể phải dùng so sánh an toàn `IS NOT DISTINCT FROM` hoặc biểu thức tương ứng theo DBMS.

Nhưng cẩn thận: coi mọi hàng chưa biết mã là cùng một nhóm có thể tạo **rất nhiều tổ hợp giả**. Khóa FK/PK thường được thiết kế tránh nhập nhằng này bằng `NOT NULL` khi bản ghi bắt buộc liên kết với cha.

### 13.3. LEFT JOIN rồi WHERE có thể không còn giữ bên trái

`LEFT JOIN` chỉ giữ hàng bên trái trong **bước nối**. Một điều kiện `WHERE` tiếp theo kiểm tra cột bên phải có thể loại các hàng `NULL`. Vì vậy “có `LEFT JOIN`” không phải là bằng chứng truy vấn cuối có đủ mọi khách hàng.

### 13.4. Không phải mọi hàng giống nhau đều là “duplicate cần xóa”

SQL mặc định cho phép các hàng kết quả trùng ở những cột được chọn, và một câu truy vấn có thể tạo các bản sao vì nhiều bản ghi quan hệ khác nhau. Ví dụ:

~~~sql
SELECT c.customer_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_name;
~~~

Tên An xuất hiện **hai lần** vì có hai đơn. Nếu câu hỏi là “một tên cho mỗi đơn” thì đây đúng. Nếu câu hỏi là “tên những khách hàng có đơn” thì `DISTINCT`, `EXISTS` hoặc tổng hợp có thể phù hợp. Nhưng nếu chỉ lấy tên, **hai khách hàng khác nhau cũng có thể trùng tên**; muốn khử trùng theo **khách hàng**, cần giữ khóa `customer_id` trong logic thay vì chỉ nhìn chữ hiển thị.

### 13.5. Luôn xác định mức hạt trước khi lấy dữ liệu

Bảng tư duy:

| Câu hỏi nghiệp vụ | Một hàng kết quả đại diện cho | Mẫu truy vấn phù hợp |
| --- | --- | --- |
| Mỗi khách hàng có hồ sơ ở đâu? | Khách hàng | `customers LEFT JOIN customer_profiles` |
| Liệt kê từng đơn và người đặt | Đơn hàng | `orders JOIN customers` |
| Liệt kê từng dòng trong đơn | Dòng đơn | `order_items JOIN orders JOIN products` |
| Mỗi khách hàng có bao nhiêu đơn? | Khách hàng | `GROUP BY customer_id` hoặc preaggregate |
| Khách hàng đã từng mua sản phẩm nào? | Cặp khách hàng–sản phẩm | `SELECT DISTINCT customer_id, product_id` |
| Khách hàng đã mua bao nhiêu chiếc theo sản phẩm? | Cặp khách hàng–sản phẩm | `SUM(quantity) GROUP BY ...` |
| Khách hàng có đơn PAID không? | Khách hàng | `EXISTS` |
| Mỗi khách hàng có đơn mã lớn nhất nào? | Khách hàng | `ROW_NUMBER()` + lọc một hàng |

Trước khi viết phép JOIN, xác định **khóa phân biệt một hàng đầu ra**. Khi các bảng ở nhiều mức hạt khác nhau, hãy tổng hợp hoặc chọn một bản ghi trước khi nối để tránh nhân số liệu.

## 14. Bài tập thực hành

Dùng toàn bộ dữ liệu mẫu ở mục 2. Nếu đã sửa dữ liệu trong quá trình học, hãy khởi tạo lại dữ liệu để so sánh kết quả.

### Bài 1 — Nhận diện quan hệ

Từ các ràng buộc:

~~~sql
customer_profiles.customer_id PRIMARY KEY
customer_profiles.customer_id REFERENCES customers(customer_id)

orders.customer_id NOT NULL
orders.customer_id REFERENCES customers(customer_id)

order_items PRIMARY KEY(order_id, product_id)
order_items.order_id REFERENCES orders(order_id)
order_items.product_id REFERENCES products(product_id)
~~~

Hãy xác định quan hệ giữa:

1. `customers` và `customer_profiles`.
2. `customers` và `orders`.
3. `orders` và `products`.

**Gợi ý đáp án:** (1) 1:0..1, vì khóa tham chiếu ở profiles là duy nhất và khách hàng có thể thiếu hồ sơ; (2) 1:0..N, vì nhiều đơn có thể cùng khách hàng; (3) N:N qua `order_items`, được triển khai bằng hai quan hệ 1:N.

### Bài 2 — Dự đoán lực lượng kết quả

Cho các phép nối sau (không thêm `WHERE`):

~~~sql
-- A
FROM customers c JOIN customer_profiles p
    ON p.customer_id = c.customer_id

-- B
FROM customers c LEFT JOIN customer_profiles p
    ON p.customer_id = c.customer_id

-- C
FROM customers c JOIN orders o
    ON o.customer_id = c.customer_id

-- D
FROM customers c LEFT JOIN orders o
    ON o.customer_id = c.customer_id

-- E
FROM orders o JOIN order_items oi
    ON oi.order_id = o.order_id

-- F
FROM products p LEFT JOIN order_items oi
    ON oi.product_id = p.product_id
~~~

**Đáp án:** A = **3**, B = **4**, C = **4**, D = **5**, E = **7**, F = **8**. Với F, có bảy dòng đơn khớp năm sản phẩm theo quan hệ sản phẩm–dòng đơn, còn `May in` chưa được mua nên được bổ sung một hàng có cột dòng đơn bằng `NULL`.

### Bài 3 — Đếm đúng đơn và dòng đơn

Viết câu truy vấn trả mỗi khách hàng một hàng, có tên, `order_count` và `item_line_count`.

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(oi.product_id) AS item_line_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả theo An/Binh/Chi/Dung lần lượt là `(2, 4)`, `(1, 1)`, `(0, 0)`, `(1, 2)`.

### Bài 4 — Sửa phép tổng bị nhân

Phân tích tại sao:

~~~sql
SELECT SUM(o.total_amount)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id;
~~~

trả **3.910.000** thay vì **1.980.000**.

**Đáp án:** `total_amount` là giá trị **một lần mỗi đơn**, còn sau JOIN mỗi đơn lặp theo số dòng trong `order_items`. Để tính tổng tiền các đơn, dùng trực tiếp `SUM(total_amount) FROM orders` hoặc preaggregate ở cấp đơn/khách hàng trước khi nối với những bảng chi tiết khác.

### Bài 5 — Khách hàng có ít nhất một đơn đã thanh toán

Viết truy vấn chỉ trả **một hàng cho mỗi khách hàng** có ít nhất một đơn `PAID`, không dùng `DISTINCT` để che hàng lặp.

**Đáp án:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả là An và Dung.

### Bài 6 — Hiểu ON khác WHERE trong LEFT JOIN

So sánh hai câu:

~~~sql
-- A
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';

-- B
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

**Đáp án:** A trả **5 hàng**, giữ cả Binh và Chi dưới dạng không có đơn PAID. B trả **3 hàng**, loại Binh và Chi do `WHERE` chỉ giữ các hàng có `o.status = 'PAID'` là TRUE.

### Bài 7 — Khách hàng đã từng mua những sản phẩm nào?

Viết truy vấn một hàng cho mỗi cặp `(customer_id, product_id)`, không bao gồm thông tin đơn hàng riêng lẻ. Bao nhiêu hàng được trả về?

**Gợi ý:**

~~~sql
SELECT DISTINCT
    c.customer_id,
    p.product_id,
    p.product_name
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
ORDER BY c.customer_id, p.product_id;
~~~

**Đáp án:** **6 hàng**. An mua `So tay` ở hai đơn nhưng cặp khách hàng–sản phẩm chỉ còn một hàng.

### Bài 8 — Tìm sản phẩm chưa xuất hiện trong đơn

Dùng `NOT EXISTS` hoặc `LEFT JOIN ... IS NULL` để tìm sản phẩm chưa có dòng `order_items`.

**Đáp án gợi ý:**

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
)
ORDER BY p.product_id;
~~~

Kết quả: `(50, 'May in')`.

### Bài 9 — Tự nối một bảng 1:N

Vì sao phép nối sau trả bốn hàng cho khách hàng An?

~~~sql
SELECT o1.order_id, o2.order_id
FROM orders o1
JOIN orders o2 ON o2.customer_id = o1.customer_id
WHERE o1.customer_id = 1;
~~~

**Đáp án:** An có hai đơn ở alias `o1` và hai đơn ở alias `o2`, nên có **2 × 2 = 4 cặp**. Nếu chỉ muốn một cặp hai đơn khác nhau, thêm `o1.order_id < o2.order_id`; khi đó còn một cặp `(101, 102)`.

## 15. Kết luận

**Một-một, một-nhiều và nhiều-nhiều** mô tả **số bản ghi có thể liên kết** giữa các bảng. Chúng được triển khai thông qua khóa chính, khóa ngoại, `UNIQUE` và bảng trung gian. Khi viết `JOIN`, **mỗi cặp hàng thỏa điều kiện nối có thể tạo một hàng kết quả**; vì vậy số hàng sau JOIN phụ thuộc cả dữ liệu thực tế, bội số, loại JOIN và bộ lọc.

Hãy ghi nhớ bốn nguyên tắc:

1. **`INNER JOIN` chỉ giữ các cặp khớp; `LEFT JOIN` giữ hàng trái không khớp nhưng vẫn có thể nhân hàng.**
2. **`COUNT(*)`, `COUNT(cột)` và `COUNT(DISTINCT khóa)` đếm các đối tượng khác nhau.**
3. **Tính tổng ở đúng mức hạt dữ liệu**; đừng cộng giá trị bảng cha sau khi nó bị nhân theo dòng chi tiết.
4. **Chọn cấu trúc theo câu hỏi nghiệp vụ:** `EXISTS` cho điều kiện tồn tại, `GROUP BY` cho một hàng mỗi nhóm, `ROW_NUMBER()` cho một bản ghi con được chọn và `DISTINCT` khi thật sự muốn các cặp giá trị duy nhất.

Câu hỏi nên đặt ra trước mọi phép nối là: **“Một hàng kết quả phải đại diện cho đối tượng nào, và một hàng ở mỗi bảng sẽ khớp bao nhiêu hàng ở bảng còn lại?”** Trả lời được hai điều này giúp dự đoán đúng lực lượng kết quả, tránh sai thống kê và thiết kế truy vấn dễ mở rộng.
