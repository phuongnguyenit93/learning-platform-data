# Chuẩn bị bộ dữ liệu khách hàng, sản phẩm, đơn hàng và chi tiết đơn hàng

Trong phần **Môi trường thực hành** của module **Database SQL**, chúng ta sẽ dựng một cơ sở dữ liệu bán hàng nhỏ để thực hành các lệnh SQL trên dữ liệu có quan hệ với nhau. Bộ dữ liệu gồm bốn bảng: **khách hàng**, **sản phẩm**, **đơn hàng** và **chi tiết đơn hàng**. Sau khi chuẩn bị xong, bạn có thể dùng cùng một bộ dữ liệu để luyện lọc, sắp xếp, kết hợp bảng, thống kê doanh thu và kiểm tra tính toàn vẹn dữ liệu.

Bài hướng dẫn sử dụng **PostgreSQL 15 trở lên** làm hệ quản trị cơ sở dữ liệu mẫu. Các khái niệm về khóa chính, khóa ngoại và quan hệ bảng cũng áp dụng cho MySQL, SQL Server hay SQLite, nhưng cú pháp tạo cơ sở dữ liệu và một số lệnh tiện ích sẽ khác. Toàn bộ tên bảng/cột trong bài dùng tiếng Anh, còn dữ liệu mẫu và giải thích dùng tiếng Việt.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

1. Giải thích vai trò của bốn bảng và mối quan hệ **một–nhiều** giữa chúng.
2. Tạo bảng với kiểu dữ liệu, khóa chính, khóa ngoại và ràng buộc cơ bản.
3. Nạp một bộ dữ liệu giả lập đủ đa dạng để luyện SQL.
4. Kiểm tra số bản ghi, quan hệ giữa các bảng và một số tình huống đặc biệt.
5. Chạy các truy vấn đầu tiên dùng **JOIN**, **LEFT JOIN**, **GROUP BY** và **SUM**.

Đây là dữ liệu **giả lập cho học tập**, không phải thông tin khách hàng thật. Giá sản phẩm được biểu diễn bằng số nguyên theo đơn vị **VND**; ví dụ, 250000 nghĩa là 250.000 đồng.

## 2. Thiết kế mô hình dữ liệu

Một khách hàng có thể đặt nhiều đơn hàng. Mỗi đơn hàng có nhiều dòng chi tiết; mỗi dòng chỉ đến một sản phẩm và ghi số lượng cùng đơn giá tại thời điểm đặt. Một sản phẩm có thể xuất hiện trong nhiều đơn hàng khác nhau.

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "dat"
    ORDERS ||--o{ ORDER_ITEMS : "gom"
    PRODUCTS ||--o{ ORDER_ITEMS : "duoc_mua_trong"

    CUSTOMERS {
        int customer_id PK
        varchar full_name
        varchar email
        varchar city
    }
    PRODUCTS {
        int product_id PK
        varchar sku
        varchar product_name
        numeric unit_price
        int stock_quantity
    }
    ORDERS {
        int order_id PK
        int customer_id FK
        timestamp order_date
        varchar status
    }
    ORDER_ITEMS {
        int order_id PK,FK
        int product_id PK,FK
        int quantity
        numeric unit_price
    }
~~~

| Bảng | Chức năng | Khóa chính | Liên kết |
| --- | --- | --- | --- |
| **customers** | Lưu thông tin người mua | customer_id | Được tham chiếu bởi orders.customer_id |
| **products** | Danh mục hàng hóa và giá hiện tại | product_id | Được tham chiếu bởi order_items.product_id |
| **orders** | Thông tin chung về một lần đặt hàng | order_id | customer_id tham chiếu customers |
| **order_items** | Những sản phẩm và số lượng trong mỗi đơn | (order_id, product_id) | order_id tham chiếu orders; product_id tham chiếu products |

**Vì sao cần bảng order_items?** Một đơn hàng có nhiều sản phẩm, và một sản phẩm có thể thuộc nhiều đơn. Đó là quan hệ **nhiều–nhiều** giữa orders và products; bảng order_items chuyển quan hệ ấy thành hai quan hệ một–nhiều. Khóa chính ghép **(order_id, product_id)** quy định mỗi sản phẩm chỉ có một dòng trong một đơn; muốn mua thêm cùng sản phẩm thì tăng quantity.

Hai cột có tên **unit_price** mang ý nghĩa khác nhau:

- **products.unit_price**: giá niêm yết hiện tại, có thể thay đổi sau này.
- **order_items.unit_price**: giá tại thời điểm khách đặt hàng, cần được giữ lại để tính đúng tiền của những đơn trong quá khứ.

Số tiền của một dòng chi tiết được tính bằng **quantity × order_items.unit_price**. Tổng tiền đơn hàng là tổng số tiền các dòng chi tiết. Chúng ta không lưu thêm cột tổng tiền trong orders để tránh việc hai nơi lưu cùng một con số nhưng có thể bị lệch nhau.

## 3. Chuẩn bị môi trường PostgreSQL

Cần có PostgreSQL đang chạy và một công cụ thực thi SQL, chẳng hạn **psql** (dòng lệnh) hoặc **pgAdmin** (giao diện đồ họa). Tài khoản thực hành phải có quyền tạo cơ sở dữ liệu; nếu không, hãy dùng một cơ sở dữ liệu thực hành đã được cấp sẵn và có quyền tạo schema.

Đầu tiên, kết nối vào cơ sở dữ liệu quản trị mặc định (thường tên là **postgres**) rồi tạo một cơ sở dữ liệu **riêng cho bài thực hành**:

~~~sql
CREATE DATABASE sql_practice_shop;
~~~

Chạy lệnh tạo cơ sở dữ liệu **riêng**, không đặt nó bên trong khối BEGIN/COMMIT. Sau đó mở kết nối đến **sql_practice_shop**. Nếu sử dụng psql, ví dụ:

~~~bash
psql -U postgres -d postgres -c "CREATE DATABASE sql_practice_shop;"
psql -U postgres -d sql_practice_shop
~~~

Nếu sử dụng pgAdmin, tạo database bằng giao diện hoặc Query Tool, rồi mở Query Tool của **sql_practice_shop**. Các phần SQL tiếp theo chạy trong kết nối này.

> **Lưu ý:** Đoạn tạo dữ liệu bên dưới có lệnh xóa schema **shop_lab** cũ để mỗi lần thực hành đều bắt đầu với cùng một kết quả. Chỉ chạy trong database thực hành riêng. Nếu schema shop_lab đang chứa dữ liệu cần giữ, hãy sao lưu hoặc dùng database mới trước khi chạy.

## 4. Tạo bốn bảng và nạp dữ liệu mẫu

Bạn có thể lưu toàn bộ đoạn SQL sau thành tệp **shop_lab.sql** (mã hóa UTF-8) và chạy một lần; hoặc dán nguyên đoạn vào Query Tool của database thực hành. Dữ liệu cố định giúp các truy vấn ví dụ cho cùng kết quả khi chạy lại.

### 4.1. Tạo schema, bảng và các ràng buộc

~~~sql
BEGIN;

-- Chỉ dùng trong database thực hành: đặt lại toàn bộ schema của bài này.
DROP SCHEMA IF EXISTS shop_lab CASCADE;
CREATE SCHEMA shop_lab;

-- 1. Khách hàng
CREATE TABLE shop_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(180) NOT NULL UNIQUE,
    phone VARCHAR(20),
    city VARCHAR(80) NOT NULL,
    created_at DATE NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT chk_customer_name
        CHECK (LENGTH(TRIM(full_name)) > 0)
);

-- 2. Sản phẩm
CREATE TABLE shop_lab.products (
    product_id INTEGER PRIMARY KEY,
    sku VARCHAR(20) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(80) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price > 0),
    stock_quantity INTEGER NOT NULL
        CHECK (stock_quantity >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. Đơn hàng
CREATE TABLE shop_lab.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN (
            'pending', 'paid', 'shipped', 'completed', 'cancelled'
        )),
    shipping_city VARCHAR(80) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES shop_lab.customers (customer_id)
        ON DELETE RESTRICT
);

-- 4. Chi tiết đơn hàng
CREATE TABLE shop_lab.order_items (
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price > 0),
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES shop_lab.orders (order_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES shop_lab.products (product_id)
        ON DELETE RESTRICT
);

-- Hai chỉ mục phục vụ những hướng JOIN/lọc phổ biến.
CREATE INDEX idx_orders_customer_date
    ON shop_lab.orders (customer_id, order_date);
CREATE INDEX idx_order_items_product
    ON shop_lab.order_items (product_id);
~~~

**Giải thích các lựa chọn quan trọng:**

- **PRIMARY KEY** giúp mỗi khách hàng, sản phẩm, đơn hàng hoặc dòng chi tiết có định danh duy nhất.
- **FOREIGN KEY** ngăn việc thêm đơn hàng cho khách hàng không tồn tại hoặc thêm chi tiết có mã sản phẩm/đơn hàng không tồn tại.
- **NOT NULL**, **UNIQUE** và **CHECK** ngăn thiếu dữ liệu bắt buộc, email/SKU trùng, số lượng âm hoặc trạng thái ngoài danh sách cho phép.
- **NUMERIC(12,2)** phù hợp hơn kiểu số thực dấu phẩy động khi lưu tiền. Giá VND trong bộ dữ liệu này đều là số nguyên, nhưng kiểu cột vẫn cho phép hai chữ số thập phân.
- **ON DELETE RESTRICT** ngăn xóa một bản ghi cha vẫn đang được bản ghi khác tham chiếu, giúp tránh mất lịch sử đơn hàng do xóa nhầm.
- PostgreSQL tự tạo chỉ mục cho khóa chính và ràng buộc UNIQUE; hai chỉ mục bổ sung hỗ trợ tìm đơn theo khách và tra chi tiết theo sản phẩm. Với tập dữ liệu nhỏ, lợi ích tốc độ chưa rõ rệt.

### 4.2. Nạp bảng customers

Các email dùng miền **example.test** dành cho dữ liệu minh họa; một số điện thoại để **NULL** nhằm tạo tình huống thực hành với giá trị thiếu.

~~~sql
INSERT INTO shop_lab.customers
    (customer_id, full_name, email, phone, city, created_at)
VALUES
    (1, 'Nguyễn Minh Anh', 'minh.anh@example.test', '0900000001', 'Hà Nội', '2026-01-10'),
    (2, 'Trần Quốc Bảo', 'quoc.bao@example.test', '0900000002', 'TP. Hồ Chí Minh', '2026-01-12'),
    (3, 'Lê Thu Hà', 'thu.ha@example.test', NULL, 'Đà Nẵng', '2026-01-15'),
    (4, 'Phạm Gia Huy', 'gia.huy@example.test', '0900000004', 'Cần Thơ', '2026-01-18'),
    (5, 'Võ Ngọc Lan', 'ngoc.lan@example.test', '0900000005', 'TP. Hồ Chí Minh', '2026-01-20'),
    (6, 'Đặng Đức Long', 'duc.long@example.test', NULL, 'Hải Phòng', '2026-01-22'),
    (7, 'Bùi Thanh Mai', 'thanh.mai@example.test', '0900000007', 'Huế', '2026-01-24'),
    (8, 'Phan Nhật Nam', 'nhat.nam@example.test', '0900000008', 'Hà Nội', '2026-01-27'),
    (9, 'Hồ Bảo Ngọc', 'bao.ngoc@example.test', NULL, 'Nha Trang', '2026-01-29'),
    (10, 'Đỗ Thảo Vy', 'thao.vy@example.test', '0900000010', 'Đà Lạt', '2026-02-01'),
    (11, 'Nguyễn Khánh Linh', 'khanh.linh@example.test', '0900000011', 'TP. Hồ Chí Minh', '2026-02-02'),
    (12, 'Lý Hoàng Phúc', 'hoang.phuc@example.test', NULL, 'Vũng Tàu', '2026-02-04');
~~~

Khách hàng **12** được chủ ý để **chưa có đơn hàng**. Nhờ vậy, khi luyện **LEFT JOIN**, bạn sẽ thấy sự khác biệt giữa lấy tất cả khách hàng và chỉ lấy khách đã mua.

### 4.3. Nạp bảng products

~~~sql
INSERT INTO shop_lab.products
    (product_id, sku, product_name, category, unit_price, stock_quantity, is_active)
VALUES
    (101, 'P001', 'Laptop văn phòng', 'Điện tử', 18990000, 15, TRUE),
    (102, 'P002', 'Chuột không dây', 'Phụ kiện', 250000, 100, TRUE),
    (103, 'P003', 'Bàn phím cơ', 'Phụ kiện', 890000, 40, TRUE),
    (104, 'P004', 'Tai nghe Bluetooth', 'Âm thanh', 1250000, 35, TRUE),
    (105, 'P005', 'Màn hình 24 inch', 'Điện tử', 3250000, 20, TRUE),
    (106, 'P006', 'Webcam Full HD', 'Phụ kiện', 750000, 30, TRUE),
    (107, 'P007', 'Đế tản nhiệt', 'Phụ kiện', 420000, 50, TRUE),
    (108, 'P008', 'Ổ SSD 1 TB', 'Lưu trữ', 1590000, 25, TRUE),
    (109, 'P009', 'USB 64 GB', 'Lưu trữ', 180000, 150, TRUE),
    (110, 'P010', 'Giá đỡ laptop', 'Phụ kiện', 310000, 60, TRUE),
    (111, 'P011', 'Micro USB', 'Âm thanh', 990000, 28, TRUE),
    (112, 'P012', 'Balo laptop', 'Phụ kiện', 650000, 45, TRUE),
    (113, 'P013', 'Bút cảm ứng', 'Phụ kiện', 890000, 0, FALSE);
~~~

Sản phẩm **113** chưa xuất hiện trong bất kỳ dòng chi tiết đơn hàng nào và đang ngừng bán. Đây là trường hợp hữu ích để luyện tìm sản phẩm chưa từng được đặt hàng. Cột **stock_quantity** thể hiện tồn kho giả lập tại thời điểm tạo dữ liệu; phần nạp dữ liệu không tự động trừ kho khi thêm đơn.

### 4.4. Nạp bảng orders

Nạp **orders sau customers** vì mỗi đơn phải tham chiếu đến một khách hàng đã tồn tại.

~~~sql
INSERT INTO shop_lab.orders
    (order_id, customer_id, order_date, status, shipping_city)
VALUES
    (1001, 1, '2026-02-02 09:15:00', 'paid', 'Hà Nội'),
    (1002, 2, '2026-02-04 10:30:00', 'completed', 'TP. Hồ Chí Minh'),
    (1003, 3, '2026-02-07 14:20:00', 'shipped', 'Đà Nẵng'),
    (1004, 4, '2026-02-08 16:45:00', 'pending', 'Cần Thơ'),
    (1005, 1, '2026-02-12 08:40:00', 'completed', 'Hà Nội'),
    (1006, 5, '2026-02-14 11:05:00', 'cancelled', 'TP. Hồ Chí Minh'),
    (1007, 6, '2026-02-18 13:10:00', 'paid', 'Hải Phòng'),
    (1008, 7, '2026-02-19 15:25:00', 'completed', 'Huế'),
    (1009, 8, '2026-02-21 09:50:00', 'shipped', 'Hà Nội'),
    (1010, 9, '2026-02-25 17:00:00', 'completed', 'Nha Trang'),
    (1011, 10, '2026-03-01 10:00:00', 'paid', 'Đà Lạt'),
    (1012, 2, '2026-03-03 12:35:00', 'completed', 'TP. Hồ Chí Minh'),
    (1013, 11, '2026-03-05 18:10:00', 'pending', 'TP. Hồ Chí Minh'),
    (1014, 5, '2026-03-09 08:25:00', 'shipped', 'TP. Hồ Chí Minh'),
    (1015, 3, '2026-03-12 11:55:00', 'completed', 'Đà Nẵng'),
    (1016, 6, '2026-03-15 14:05:00', 'paid', 'Hải Phòng');
~~~

Trạng thái trong dữ liệu có ý nghĩa minh họa:

| Giá trị status | Diễn giải |
| --- | --- |
| pending | Đang chờ xử lý hoặc thanh toán |
| paid | Đã thanh toán |
| shipped | Đang giao |
| completed | Đã hoàn tất |
| cancelled | Đã hủy |

Một khách hàng có thể có nhiều đơn (ví dụ khách **1**, **2**, **3**, **5**, **6**). Một đơn bị hủy vẫn có thể có các dòng order_items để giữ thông tin đã đặt trước khi hủy. Khi tính doanh thu phục vụ bài tập, cần chủ động chọn trạng thái được tính; không cộng mặc định tất cả đơn.

### 4.5. Nạp bảng order_items và hoàn tất giao dịch

Nạp chi tiết **sau orders và products**, vì cả hai khóa ngoại đều phải hợp lệ.

~~~sql
INSERT INTO shop_lab.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 101, 1, 18990000),
    (1001, 102, 2, 250000),
    (1001, 110, 1, 310000),

    (1002, 103, 1, 890000),
    (1002, 104, 1, 1250000),

    (1003, 105, 1, 3250000),
    (1003, 106, 1, 750000),
    (1003, 109, 2, 180000),

    (1004, 112, 1, 650000),
    (1004, 102, 1, 250000),

    (1005, 108, 1, 1590000),
    (1005, 109, 3, 180000),
    (1005, 107, 1, 420000),

    (1006, 101, 1, 18990000),
    (1006, 112, 1, 650000),

    (1007, 105, 2, 3250000),
    (1007, 103, 2, 890000),

    (1008, 104, 1, 1250000),
    (1008, 111, 1, 990000),
    (1008, 102, 1, 250000),

    (1009, 108, 2, 1590000),
    (1009, 110, 2, 310000),

    (1010, 101, 1, 18990000),
    (1010, 106, 1, 750000),

    (1011, 109, 5, 180000),
    (1011, 112, 1, 650000),

    (1012, 105, 1, 3250000),
    (1012, 103, 1, 890000),
    (1012, 111, 1, 990000),

    (1013, 102, 2, 250000),
    (1013, 107, 1, 420000),

    (1014, 104, 2, 1250000),
    (1014, 108, 1, 1590000),

    (1015, 109, 10, 180000),
    (1015, 106, 2, 750000),

    (1016, 112, 1, 650000),
    (1016, 110, 1, 310000),
    (1016, 102, 1, 250000);

COMMIT;
~~~

**BEGIN** và **COMMIT** bao toàn bộ phần tạo schema, bảng và dữ liệu: PostgreSQL sẽ ghi nhận cả khối khi thực thi thành công. Nếu một lệnh trong giao dịch lỗi, giao dịch bị đánh dấu thất bại; hãy dùng **ROLLBACK**, sửa lỗi và chạy lại toàn bộ script. Việc đặt lại schema giúp tránh bản ghi trùng khi thực hành nhiều lần.

Ở đơn **1001**, sản phẩm **101** có số lượng 1, sản phẩm **102** có số lượng 2 và sản phẩm **110** có số lượng 1. Cách lưu này giúp tra được cả thành phần đơn hàng lẫn tổng giá trị đơn.

## 5. Kiểm tra dữ liệu đã được chuẩn bị

### 5.1. Đếm số bản ghi mỗi bảng

Chạy truy vấn sau khi thấy thông báo thực thi thành công:

~~~sql
SELECT 'customers' AS table_name, COUNT(*) AS record_count
FROM shop_lab.customers
UNION ALL
SELECT 'products', COUNT(*) FROM shop_lab.products
UNION ALL
SELECT 'orders', COUNT(*) FROM shop_lab.orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM shop_lab.order_items;
~~~

Với bộ dữ liệu đã cho, kết quả dự kiến:

| table_name | record_count |
| --- | ---: |
| customers | 12 |
| products | 13 |
| orders | 16 |
| order_items | 38 |

### 5.2. Xem các dòng chi tiết cùng tên sản phẩm

~~~sql
SELECT
    oi.order_id,
    p.product_name,
    oi.quantity,
    oi.unit_price AS price_at_order,
    oi.quantity * oi.unit_price AS line_total
FROM shop_lab.order_items AS oi
JOIN shop_lab.products AS p
    ON p.product_id = oi.product_id
WHERE oi.order_id = 1001
ORDER BY p.product_id;
~~~

Truy vấn phải trả về **3 dòng**. Tổng ba dòng của đơn 1001 là **19.800.000 VND** (18.990.000 + 2 × 250.000 + 310.000).

### 5.3. Kiểm tra đơn hàng thiếu chi tiết và chi tiết mồ côi

Khóa ngoại đảm bảo một dòng order_items không thể tham chiếu đơn hàng hoặc sản phẩm không tồn tại. Tuy nhiên, chỉ có khóa ngoại **không tự đảm bảo** mọi đơn hàng đều có ít nhất một dòng chi tiết, nên có thể kiểm tra riêng:

~~~sql
SELECT COUNT(*) AS orders_without_items
FROM shop_lab.orders AS o
LEFT JOIN shop_lab.order_items AS oi
    ON oi.order_id = o.order_id
WHERE oi.order_id IS NULL;
~~~

Kết quả dự kiến là **0**. Có thể kiểm tra thêm liên kết chi tiết:

~~~sql
SELECT COUNT(*) AS orphan_items
FROM shop_lab.order_items AS oi
LEFT JOIN shop_lab.orders AS o
    ON o.order_id = oi.order_id
LEFT JOIN shop_lab.products AS p
    ON p.product_id = oi.product_id
WHERE o.order_id IS NULL OR p.product_id IS NULL;
~~~

Kết quả dự kiến cũng là **0**.

## 6. Dùng bộ dữ liệu cho các truy vấn đầu tiên

### 6.1. Liệt kê đơn hàng kèm tên khách hàng

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.order_date,
    o.status,
    o.shipping_city
FROM shop_lab.orders AS o
JOIN shop_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_date, o.order_id;
~~~

**JOIN** kết nối orders với customers qua customer_id. Mỗi kết quả vẫn đại diện cho **một đơn hàng**; nếu nối thêm order_items, một đơn sẽ xuất hiện ở nhiều dòng tương ứng với các sản phẩm.

### 6.2. Tính tổng tiền của từng đơn

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.status,
    SUM(oi.quantity * oi.unit_price) AS order_total_vnd
FROM shop_lab.orders AS o
JOIN shop_lab.customers AS c
    ON c.customer_id = o.customer_id
JOIN shop_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, c.full_name, o.status
ORDER BY o.order_id;
~~~

**GROUP BY** gom các dòng chi tiết theo đơn. **SUM** cộng giá trị của từng dòng. Truy vấn này cho thấy giá trị của **mọi đơn**, kể cả pending và cancelled; đó là **giá trị đơn hàng đã tạo**, chưa đồng nghĩa với doanh thu được công nhận.

### 6.3. Tính giá trị đơn đã thanh toán, đang giao hoặc hoàn tất

Trong phạm vi bài thực hành, quy ước các trạng thái paid, shipped và completed là các đơn hợp lệ để phân tích giá trị bán hàng:

~~~sql
SELECT
    DATE_TRUNC('month', o.order_date)::DATE AS order_month,
    SUM(oi.quantity * oi.unit_price) AS sales_value_vnd
FROM shop_lab.orders AS o
JOIN shop_lab.order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status IN ('paid', 'shipped', 'completed')
GROUP BY DATE_TRUNC('month', o.order_date)::DATE
ORDER BY order_month;
~~~

Đây là **quy ước phân tích cho dữ liệu mẫu**, không phải nguyên tắc kế toán chung. Hệ thống thực tế cần xác định rõ thời điểm ghi nhận doanh thu, hoàn tiền, thuế và phí vận chuyển.

### 6.4. Tìm khách hàng chưa từng đặt hàng

~~~sql
SELECT c.customer_id, c.full_name
FROM shop_lab.customers AS c
LEFT JOIN shop_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
~~~

Kết quả dự kiến là khách hàng **12 – Lý Hoàng Phúc**. **LEFT JOIN** giữ toàn bộ hàng từ customers, kể cả khi không tìm thấy đơn tương ứng.

### 6.5. Tìm sản phẩm chưa xuất hiện trong đơn nào

~~~sql
SELECT p.product_id, p.product_name, p.is_active
FROM shop_lab.products AS p
LEFT JOIN shop_lab.order_items AS oi
    ON oi.product_id = p.product_id
WHERE oi.product_id IS NULL
ORDER BY p.product_id;
~~~

Kết quả dự kiến là sản phẩm **113 – Bút cảm ứng**. Ví dụ minh họa rằng không nên dùng JOIN thông thường nếu câu hỏi cần giữ cả những bản ghi **không có quan hệ**.

### 6.6. Thống kê số lượng đã đặt theo sản phẩm

~~~sql
SELECT
    p.product_id,
    p.product_name,
    SUM(oi.quantity) AS units_ordered
FROM shop_lab.products AS p
JOIN shop_lab.order_items AS oi
    ON oi.product_id = p.product_id
JOIN shop_lab.orders AS o
    ON o.order_id = oi.order_id
WHERE o.status IN ('paid', 'shipped', 'completed')
GROUP BY p.product_id, p.product_name
ORDER BY units_ordered DESC, p.product_id
LIMIT 5;
~~~

Điều kiện trạng thái giúp bỏ qua sản phẩm trong đơn đang chờ hoặc bị hủy. **LIMIT 5** chọn năm sản phẩm đứng đầu theo tổng số lượng đặt ở các đơn hợp lệ.

## 7. Những quy tắc cần hiểu khi sử dụng dữ liệu

| Tình huống | Cách hiểu đúng |
| --- | --- |
| Khách hàng chưa có đơn | Vẫn nằm trong customers; dùng LEFT JOIN để tìm |
| Sản phẩm chưa được mua | Vẫn nằm trong products; không xuất hiện trong order_items |
| Một đơn chứa nhiều sản phẩm | Đơn có nhiều dòng order_items |
| Một sản phẩm được mua nhiều lần | Xuất hiện trong nhiều đơn hàng khác nhau |
| Giá niêm yết thay đổi | Đơn cũ vẫn giữ giá đã mua trong order_items.unit_price |
| Đơn bị hủy | Có thể còn chi tiết để lưu lịch sử; cần lọc status khi tính chỉ tiêu |
| Số điện thoại thiếu | NULL nghĩa là chưa có dữ liệu, khác chuỗi rỗng |
| Tồn kho hiện tại | Không suy ra trực tiếp từ tổng order_items trong dataset này |

**Thứ tự nạp dữ liệu** phải tuân theo phụ thuộc khóa ngoại: **customers và products → orders → order_items**. Khi cần xóa thủ công, thường phải xử lý bảng con trước bảng cha do ràng buộc ON DELETE RESTRICT.

**Mô hình này đã được đơn giản hóa cho SQL cơ bản.** Cửa hàng thực tế có thể cần thêm địa chỉ giao hàng, lịch sử chuyển trạng thái, thanh toán, khuyến mãi, thuế, phí giao hàng, biến động tồn kho và thông tin hoàn trả. Những phần đó không cần thiết để bắt đầu thực hành truy vấn quan hệ.

## 8. Lỗi thường gặp khi chuẩn bị dữ liệu

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Database chưa tồn tại | Chưa chạy CREATE DATABASE hoặc đang kết nối sai server | Tạo database thực hành và kết nối đúng database |
| relation does not exist | Chưa chạy script hoặc thiếu tiền tố schema | Kiểm tra bảng trong shop_lab; dùng tên đầy đủ như shop_lab.orders |
| duplicate key value violates unique constraint | Nạp lại dữ liệu vào các bảng chưa được đặt lại | Chạy lại toàn bộ script từ đầu trong database thực hành |
| violates foreign key constraint | order_id, customer_id hoặc product_id tham chiếu bản ghi chưa tồn tại | Kiểm tra mã và thứ tự nạp dữ liệu |
| violates check constraint | Số lượng/giá không hợp lệ hoặc status sai danh sách | Đối chiếu điều kiện CHECK khi tạo bảng |
| current transaction is aborted | Một lệnh trong BEGIN/COMMIT đã lỗi | Chạy ROLLBACK, sửa lệnh lỗi rồi chạy lại |
| Chữ tiếng Việt hiển thị sai | File SQL hoặc kết nối dùng mã hóa không phù hợp | Lưu UTF-8 và sử dụng kết nối/cơ sở dữ liệu hỗ trợ UTF-8 |

Để xem cấu trúc một bảng trong PostgreSQL, bạn có thể tra cứu metadata bằng SQL:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'shop_lab'
  AND table_name = 'order_items'
ORDER BY ordinal_position;
~~~

Trong psql, lệnh **\d shop_lab.order_items** cũng hiển thị cột, khóa chính và khóa ngoại. Đây là lệnh riêng của **psql**, không phải câu lệnh SQL chuẩn dùng trong mọi ứng dụng.

## 9. Bài tập tiếp theo

Khi bốn bảng đã sẵn sàng, hãy thử trả lời các câu hỏi dưới đây bằng SQL. Bạn có thể sử dụng các truy vấn ở phần 6 làm điểm bắt đầu:

1. Có bao nhiêu khách hàng tại **TP. Hồ Chí Minh**?
2. Sản phẩm nào có **giá niêm yết trên 1.000.000 VND** và vẫn đang bán?
3. Mỗi khách hàng đã tạo bao nhiêu đơn, **kể cả khách chưa đặt lần nào**?
4. Những đơn nào chứa **ít nhất ba loại sản phẩm**?
5. Tổng giá trị từng đơn có trạng thái **completed** là bao nhiêu?
6. Trong các đơn **paid**, **shipped**, **completed**, sản phẩm nào có tổng số lượng bán cao nhất?
7. Tìm các sản phẩm **chưa từng xuất hiện trong order_items** và các khách hàng **chưa từng đặt hàng**.
8. So sánh tổng giá trị đơn theo **tháng 02/2026 và 03/2026**, nhớ nêu rõ trạng thái đơn được tính.

Sau bước này, bạn đã có một cơ sở dữ liệu gồm **4 bảng liên kết**, có cả bản ghi đã phát sinh giao dịch lẫn bản ghi chưa phát sinh giao dịch, nhiều trạng thái đơn và nhiều mức giá để dùng xuyên suốt các bài thực hành SQL tiếp theo.
