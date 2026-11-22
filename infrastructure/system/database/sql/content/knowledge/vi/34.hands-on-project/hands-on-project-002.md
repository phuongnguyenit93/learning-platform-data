# Nạp dữ liệu mẫu có NULL, bản sao và quan hệ thiếu

## 1. Mục tiêu bài thực hành

Khi nạp dữ liệu từ CSV, API, hệ thống cũ hoặc nhiều nguồn khác nhau, dữ liệu thường không hoàn hảo. Một tập dữ liệu mẫu tốt cần có cả trường hợp bình thường lẫn dữ liệu biên để kiểm tra cách ứng dụng xử lý:

- Cột tùy chọn có SQL NULL;
- Bản ghi trùng hoàn toàn;
- Cùng một khóa nghiệp vụ nhưng nội dung khác nhau;
- Khóa ngoại bị bỏ trống;
- Mã tham chiếu không tồn tại ở bảng cha;
- Mã sản phẩm không tồn tại;
- Số lượng hoặc đơn giá không hợp lệ;
- Bản ghi con tham chiếu tới bản ghi cha bị loại khỏi quá trình nạp.

Bài này xây dựng một lab nhỏ về khách hàng, sản phẩm, đơn hàng và dòng hàng. Dữ liệu đầu vào được nạp vào các bảng staging để giữ cả hàng lỗi. Sau đó ta phân loại NULL, phát hiện bản sao, tìm quan hệ thiếu, chọn bản ghi hợp lệ và đưa chúng vào các bảng đích có ràng buộc PK/FK/UNIQUE/CHECK.

Mục tiêu không phải xóa mọi hàng bất thường. Mục tiêu là **nhận diện, giữ dấu vết, xử lý theo quy tắc đã công bố và xác minh kết quả**.

~~~text
Nguồn CSV / API / hệ thống cũ
             |
             v
       STAGING TABLES
       - NULL
       - duplicate
       - missing key
       - orphan reference
       - invalid values
             |
             v
       DATA PROFILING
       - counts
       - duplicate groups
       - NULL checks
       - anti-joins
             |
             v
       CLASSIFY / QUARANTINE
       - valid
       - duplicate superseded
       - missing relation
       - invalid value
             |
             v
       CLEAN + PROMOTE
       - choose canonical row
       - load parent first
       - load child next
             |
             v
       TARGET TABLES
       PK / FK / UNIQUE / CHECK
             |
             v
       VERIFY COUNTS + INTEGRITY
~~~

Các câu lệnh dùng SQL phổ biến. Một số kiểu dữ liệu và cách bật khóa ngoại phụ thuộc DBMS; phần cuối nêu các khác biệt quan trọng.

## 2. Quy tắc dữ liệu của lab

Mô hình:

- Một khách hàng có thể có nhiều đơn hàng.
- Một đơn hàng thuộc về một khách hàng.
- Một đơn hàng có nhiều dòng hàng.
- Mỗi dòng hàng tham chiếu một sản phẩm.
- Một SKU xác định một sản phẩm.
- Email và điện thoại là thông tin tùy chọn.
- Đơn hàng chỉ được nhận nếu có mã đơn, khách hàng hợp lệ và trạng thái thuộc miền cho phép.
- Dòng hàng chỉ được nhận nếu có đơn hàng, sản phẩm, số lượng dương và đơn giá không âm.

~~~text
customers 1 -------- N orders
                         |
                         | 1
                         |
                         N
                     order_items
                         N
                         |
                         | 1
                         |
                      products
~~~

| Trường hợp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| NULL tùy chọn | email = NULL | Chưa có hoặc không cung cấp email |
| NULL khóa nghiệp vụ | customer_code = NULL | Không thể xác định khách hàng bằng mã nguồn |
| Duplicate exact | Hai dòng cùng mã và cùng nội dung | Một sự kiện bị nhập lặp |
| Duplicate conflict | Cùng mã nhưng email/trạng thái khác nhau | Cần quy tắc chọn bản chuẩn hoặc review |
| Missing relation key | order.customer_code = NULL | Không có mã khách hàng để liên kết |
| Orphan reference | customer_code = C999 nhưng không có C999 | Có mã nhưng bảng cha không có bản ghi |
| Invalid value | quantity = 0 hoặc NULL | Vi phạm quy tắc dòng hàng |
| Downstream orphan | Dòng hàng thuộc đơn không được nạp | Quan hệ con bị thiếu vì bản ghi cha bị loại |

**NULL và quan hệ thiếu không giống nhau.** NULL nghĩa là khóa tham chiếu không được cung cấp. Orphan nghĩa là có một giá trị tham chiếu nhưng không tìm thấy bản ghi tương ứng.

## 3. Tạo schema đích có ràng buộc

Các bảng đích lưu dữ liệu đã được chấp nhận. Dùng khóa chính, khóa ngoại, unique key và check constraint để database bảo vệ tính toàn vẹn.

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    customer_code VARCHAR(30) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NULL,
    phone VARCHAR(30) NULL,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_code UNIQUE (customer_code)
);

CREATE TABLE products (
    product_id BIGINT NOT NULL,
    sku VARCHAR(30) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price CHECK (unit_price >= 0)
);

CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    order_code VARCHAR(30) NOT NULL,
    customer_id BIGINT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_code UNIQUE (order_code),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id),
    CONSTRAINT ck_orders_status
        CHECK (order_status IN ('NEW', 'PENDING', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_items (
    item_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (item_id),
    CONSTRAINT uq_order_items_line UNIQUE (order_id, line_no),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id),
    CONSTRAINT ck_items_line CHECK (line_no > 0),
    CONSTRAINT ck_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_items_price CHECK (unit_price >= 0)
);
~~~

Ý nghĩa:

- **PRIMARY KEY:** mỗi hàng đích có định danh duy nhất.
- **UNIQUE:** không cho hai khách hàng dùng cùng customer_code, hai sản phẩm dùng cùng SKU hoặc hai dòng hàng cùng line_no trong một đơn.
- **FOREIGN KEY:** không cho dòng hàng trỏ tới đơn/sản phẩm không tồn tại.
- **NOT NULL:** cấm giá trị thiếu ở trường bắt buộc.
- **CHECK:** giới hạn miền giá trị.

DDL trên là mẫu logic gần chuẩn SQL. Oracle thường dùng NUMBER(19) thay BIGINT và VARCHAR2 thay VARCHAR; SQLite dùng type affinity và cần bật foreign key enforcement; SQL Server/MySQL có quy tắc kiểu dữ liệu và constraint theo version. Điều chỉnh kiểu vật lý theo DBMS đích.

## 4. Tạo bảng staging để giữ dữ liệu nguồn

Bảng staging cố ý không có foreign key, unique key nghiệp vụ hoặc check constraint. Nếu đặt FK ngay trên staging, những dòng tham chiếu C999 hoặc SKU không tồn tại sẽ bị từ chối trước khi ta có thể kiểm tra và báo cáo.

Mỗi hàng staging có source_row_id riêng để không làm mất các dòng trùng từ nguồn.

~~~sql
CREATE TABLE stg_customers (
    source_row_id BIGINT NOT NULL PRIMARY KEY,
    source_customer_id BIGINT NULL,
    customer_code VARCHAR(30) NULL,
    full_name VARCHAR(100) NULL,
    email VARCHAR(255) NULL,
    phone VARCHAR(30) NULL,
    source_version INTEGER NULL
);

CREATE TABLE stg_orders (
    source_row_id BIGINT NOT NULL PRIMARY KEY,
    source_order_id BIGINT NULL,
    order_code VARCHAR(30) NULL,
    customer_code VARCHAR(30) NULL,
    order_status VARCHAR(20) NULL,
    source_version INTEGER NULL
);

CREATE TABLE stg_order_lines (
    source_row_id BIGINT NOT NULL PRIMARY KEY,
    source_item_id BIGINT NULL,
    order_code VARCHAR(30) NULL,
    line_no INTEGER NULL,
    sku VARCHAR(30) NULL,
    quantity INTEGER NULL,
    unit_price DECIMAL(12, 2) NULL,
    source_version INTEGER NULL
);
~~~

source_version là số phiên bản do nguồn cung cấp trong lab này. Nếu nguồn thực tế có timestamp cập nhật đáng tin cậy, có thể thay bằng timestamp. Khi hai bản ghi cùng business key, ta dùng version mới nhất; source_row_id là tie-breaker để kết quả luôn xác định.

Staging vẫn giữ NULL và dòng tham chiếu không tồn tại. Không dùng source_row_id làm business key; nó chỉ định danh lần xuất hiện của hàng trong lần import.

## 5. Nạp dữ liệu mẫu

### 5.1. Dữ liệu khách hàng

Dữ liệu có một khách hàng bị nhập lặp hoàn toàn, một khách hàng có hai phiên bản và một hàng thiếu mã khách hàng.

~~~sql
INSERT INTO stg_customers
(source_row_id, source_customer_id, customer_code, full_name, email, phone, source_version)
VALUES (1, 1, 'C001', 'An Nguyen', 'an@example.test', '0901000001', 1);

INSERT INTO stg_customers
(source_row_id, source_customer_id, customer_code, full_name, email, phone, source_version)
VALUES (2, 2, 'C002', 'Binh Tran', NULL, '0901000002', 1);

INSERT INTO stg_customers
(source_row_id, source_customer_id, customer_code, full_name, email, phone, source_version)
VALUES (3, 3, 'C003', 'Chi Le', 'chi@example.test', NULL, 1);

INSERT INTO stg_customers
(source_row_id, source_customer_id, customer_code, full_name, email, phone, source_version)
VALUES (4, 1, 'C001', 'An Nguyen', 'an@example.test', '0901000001', 1);

INSERT INTO stg_customers
(source_row_id, source_customer_id, customer_code, full_name, email, phone, source_version)
VALUES (5, 2, 'C002', 'Binh Tran', 'binh.new@example.test', '0901000002', 2);

INSERT INTO stg_customers
(source_row_id, source_customer_id, customer_code, full_name, email, phone, source_version)
VALUES (6, 4, NULL, 'Khong co ma', NULL, NULL, 1);
~~~

Quan sát:

- C001 xuất hiện hai lần với nội dung giống nhau.
- C002 xuất hiện hai lần; version 2 có email mới.
- C003 không có phone; đây là NULL hợp lệ vì phone tùy chọn.
- Hàng 6 không có customer_code nên chưa thể ánh xạ sang khóa nghiệp vụ khách hàng.

### 5.2. Dữ liệu sản phẩm hợp lệ

Trong lab, danh mục sản phẩm đã được xác nhận từ một nguồn chuẩn khác nên nạp trực tiếp vào bảng đích:

~~~sql
INSERT INTO products
(product_id, sku, product_name, unit_price)
VALUES (10, 'SKU-A', 'Ban phim', 10.00);

INSERT INTO products
(product_id, sku, product_name, unit_price)
VALUES (11, 'SKU-B', 'Chuot', 25.00);

INSERT INTO products
(product_id, sku, product_name, unit_price)
VALUES (12, 'SKU-C', 'Man hinh', 100.00);
~~~

Các dòng hàng có SKU không nằm trong danh mục này sẽ được xem là tham chiếu sản phẩm thiếu.

### 5.3. Dữ liệu đơn hàng

~~~sql
INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (1, 100, 'O-100', 'C001', 'PAID', 1);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (2, 101, 'O-101', 'C002', 'PENDING', 1);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (3, 102, 'O-102', 'C999', 'PAID', 1);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (4, 103, 'O-103', NULL, 'NEW', 1);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (5, 100, 'O-100', 'C001', 'PAID', 1);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (6, 101, 'O-101', 'C002', 'CANCELLED', 2);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (7, 104, 'O-104', 'C003', 'NEW', 1);

INSERT INTO stg_orders
(source_row_id, source_order_id, order_code, customer_code, order_status, source_version)
VALUES (8, 105, 'O-105', 'C003', 'UNKNOWN', 1);
~~~

Có các trường hợp:

- O-100 bị lặp giống hệt.
- O-101 có hai phiên bản trạng thái; version 2 là CANCELLED.
- O-102 có customer_code C999 nhưng không có khách hàng C999.
- O-103 có customer_code NULL.
- O-105 có trạng thái ngoài miền cho phép.

### 5.4. Dữ liệu dòng hàng

~~~sql
INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (1, 1001, 'O-100', 1, 'SKU-A', 2, 10.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (2, 1002, 'O-100', 2, 'SKU-B', 1, 25.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (3, 1003, 'O-101', 1, 'SKU-A', 1, 10.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (4, 1003, 'O-101', 1, 'SKU-A', 1, 10.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (5, 1004, 'O-100', 3, 'SKU-X', 1, 50.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (6, 1005, 'O-999', 1, 'SKU-A', 1, 10.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (7, 1006, 'O-100', 4, 'SKU-B', NULL, 25.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (8, 1007, 'O-102', 1, 'SKU-C', 1, 100.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (9, 1008, 'O-100', 5, NULL, 1, 10.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (10, 1009, 'O-100', 6, 'SKU-A', 0, 10.00, 1);

INSERT INTO stg_order_lines
(source_row_id, source_item_id, order_code, line_no, sku, quantity, unit_price, source_version)
VALUES (11, 1010, 'O-100', 7, 'SKU-A', 1, NULL, 1);
~~~

Ta có:

- Dòng O-101 line 1 bị lặp hoàn toàn.
- SKU-X chưa có trong products.
- O-999 chưa có trong orders.
- O-102 sẽ không được nạp vì đơn này tham chiếu khách hàng C999 không tồn tại; dòng con O-102 cũng không thể được nạp.
- Một dòng thiếu quantity, một dòng thiếu SKU, một dòng quantity bằng 0 và một dòng thiếu unit_price.

## 6. Kiểm tra tổng quan trước khi làm sạch

### 6.1. Đếm số hàng staging

~~~sql
SELECT 'customers' AS source_name, COUNT(*) AS row_count
FROM stg_customers
UNION ALL
SELECT 'orders', COUNT(*)
FROM stg_orders
UNION ALL
SELECT 'order_lines', COUNT(*)
FROM stg_order_lines;
~~~

Kết quả mong đợi:

| Nguồn | Số hàng |
| --- | ---: |
| stg_customers | 6 |
| stg_orders | 8 |
| stg_order_lines | 11 |

Đếm trước khi xử lý giúp có số liệu đối chiếu sau khi nạp. Không nên chỉ nhìn số hàng cuối mà không biết bao nhiêu hàng đã được giữ, loại, gộp hoặc đưa vào quarantine.

### 6.2. Đếm NULL theo cột

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN customer_code IS NULL THEN 1 ELSE 0 END)
        AS missing_customer_code,
    SUM(CASE WHEN email IS NULL THEN 1 ELSE 0 END)
        AS missing_email,
    SUM(CASE WHEN phone IS NULL THEN 1 ELSE 0 END)
        AS missing_phone
FROM stg_customers;
~~~

Đếm NULL ở dòng hàng:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN order_code IS NULL THEN 1 ELSE 0 END)
        AS missing_order_code,
    SUM(CASE WHEN sku IS NULL THEN 1 ELSE 0 END)
        AS missing_sku,
    SUM(CASE WHEN quantity IS NULL THEN 1 ELSE 0 END)
        AS missing_quantity,
    SUM(CASE WHEN unit_price IS NULL THEN 1 ELSE 0 END)
        AS missing_unit_price
FROM stg_order_lines;
~~~

COUNT(column) chỉ đếm giá trị không NULL. Có thể dùng để đối chiếu:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(email) AS rows_with_email,
    COUNT(phone) AS rows_with_phone
FROM stg_customers;
~~~

Trong lab, email NULL và phone NULL không nhất thiết là lỗi. Phải dựa vào quy tắc nghiệp vụ: khóa định danh và tên là bắt buộc; email/phone là tùy chọn.

### 6.3. NULL không phải chuỗi rỗng

Để kiểm tra NULL, dùng:

~~~sql
SELECT *
FROM stg_customers
WHERE email IS NULL;
~~~

Không dùng email = NULL. Phép so sánh thông thường với NULL cho kết quả UNKNOWN.

PostgreSQL, MySQL, SQL Server và SQLite phân biệt chuỗi rỗng với NULL; Oracle coi chuỗi character độ dài 0 là NULL trong các kiểu character thông thường. Vì vậy, nếu cần kiểm tra chuỗi rỗng, phải xét semantics của DBMS đích. Lab này dùng NULL tường minh và không dựa vào empty string.

## 7. Phát hiện bản sao

### 7.1. Tìm duplicate theo khóa nghiệp vụ

Khách hàng được định danh bằng customer_code:

~~~sql
SELECT
    customer_code,
    COUNT(*) AS source_rows
FROM stg_customers
WHERE customer_code IS NOT NULL
GROUP BY customer_code
HAVING COUNT(*) > 1;
~~~

Đơn hàng dùng order_code:

~~~sql
SELECT
    order_code,
    COUNT(*) AS source_rows
FROM stg_orders
WHERE order_code IS NOT NULL
GROUP BY order_code
HAVING COUNT(*) > 1;
~~~

Dòng hàng dùng cặp order_code + line_no:

~~~sql
SELECT
    order_code,
    line_no,
    COUNT(*) AS source_rows
FROM stg_order_lines
WHERE order_code IS NOT NULL
  AND line_no IS NOT NULL
GROUP BY order_code, line_no
HAVING COUNT(*) > 1;
~~~

Kết quả chỉ cho biết khóa bị lặp. Nó chưa nói các hàng giống nhau hay xung đột.

### 7.2. Phân biệt duplicate exact và duplicate conflict

Để tìm nhóm khách hàng trùng hoàn toàn theo các trường nghiệp vụ:

~~~sql
SELECT
    customer_code,
    source_customer_id,
    full_name,
    email,
    phone,
    source_version,
    COUNT(*) AS copies
FROM stg_customers
WHERE customer_code IS NOT NULL
GROUP BY
    customer_code,
    source_customer_id,
    full_name,
    email,
    phone,
    source_version
HAVING COUNT(*) > 1;
~~~

GROUP BY gom các NULL cùng nhóm trong nhiều DBMS. Vì vậy hai hàng có email NULL và các trường khác giống nhau sẽ được nhận diện cùng nhóm.

Để xem mọi phiên bản của một khóa:

~~~sql
SELECT *
FROM stg_customers
WHERE customer_code IN (
    SELECT customer_code
    FROM stg_customers
    WHERE customer_code IS NOT NULL
    GROUP BY customer_code
    HAVING COUNT(*) > 1
)
ORDER BY customer_code, source_version, source_row_id;
~~~

Cách đọc:

- C001 có hai hàng cùng nội dung: duplicate exact.
- C002 có cùng customer_code nhưng email/version khác nhau: duplicate conflict theo business key.
- Cùng một mã không có nghĩa hai hàng có thể bị xóa tùy tiện.

### 7.3. Chọn bản ghi chuẩn có quy tắc xác định

Trong lab, nguồn cam kết source_version cao hơn là bản cập nhật mới hơn. Nếu version bằng nhau, chọn source_row_id lớn hơn làm tie-breaker.

~~~sql
SELECT
    source_row_id,
    source_customer_id,
    customer_code,
    full_name,
    email,
    phone,
    source_version,
    ROW_NUMBER() OVER (
        PARTITION BY customer_code
        ORDER BY source_version DESC, source_row_id DESC
    ) AS row_rank
FROM stg_customers
WHERE customer_code IS NOT NULL;
~~~

Hàng có row_rank = 1 là ứng viên canonical. Các hàng có rank lớn hơn là bản sao cũ hơn theo chính sách đã định nghĩa.

Áp dụng tương tự cho đơn hàng:

~~~sql
SELECT
    source_row_id,
    order_code,
    customer_code,
    order_status,
    source_version,
    ROW_NUMBER() OVER (
        PARTITION BY order_code
        ORDER BY source_version DESC, source_row_id DESC
    ) AS row_rank
FROM stg_orders
WHERE order_code IS NOT NULL;
~~~

Và dòng hàng:

~~~sql
SELECT
    source_row_id,
    order_code,
    line_no,
    sku,
    quantity,
    unit_price,
    ROW_NUMBER() OVER (
        PARTITION BY order_code, line_no
        ORDER BY source_version DESC, source_row_id DESC
    ) AS row_rank
FROM stg_order_lines
WHERE order_code IS NOT NULL
  AND line_no IS NOT NULL;
~~~

ROW_NUMBER có trong các phiên bản hiện đại của PostgreSQL, MySQL 8+, SQL Server, Oracle và SQLite 3.25+. Nếu phải hỗ trợ phiên bản cũ, cần chiến lược thay thế.

**Không dùng ROW_NUMBER để âm thầm xóa xung đột.** Quy tắc chọn bản mới nhất chỉ hợp lệ nếu source_version có ý nghĩa và nguồn bảo đảm nó. Nếu không có quy tắc nguồn đáng tin cậy, hãy đưa toàn bộ nhóm duplicate conflict vào review/quarantine. Duplicate exact có thể gộp theo khóa và nội dung; duplicate conflict cần quyết định nghiệp vụ.

## 8. Phát hiện quan hệ thiếu và orphan

### 8.1. Đơn hàng thiếu customer_code

~~~sql
SELECT *
FROM stg_orders
WHERE customer_code IS NULL;
~~~

Đây là missing relationship key. Không có mã để tra cứu khách hàng.

### 8.2. Đơn hàng tham chiếu khách hàng không tồn tại

~~~sql
SELECT s.*
FROM stg_orders AS s
WHERE s.customer_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.customer_code = s.customer_code
  );
~~~

Truy vấn này kiểm tra với danh mục khách hàng đã được nạp. C999 là orphan reference vì có mã nhưng không có customer tương ứng.

Kiểm tra target sau khi chọn canonical còn giúp phát hiện trường hợp bản ghi cha bị loại do lỗi khác.

### 8.3. Dòng hàng tham chiếu đơn không tồn tại

~~~sql
SELECT l.*
FROM stg_order_lines AS l
WHERE l.order_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.order_code = l.order_code
  );
~~~

O-999 không có trong orders. O-102 cũng không có trong target vì đơn này tham chiếu khách hàng C999 không tồn tại.

Đây là ví dụ quan trọng: một bản ghi con có thể trỏ tới mã cha từng xuất hiện trong file nguồn nhưng cha không được nạp vào bảng đích.

### 8.4. Dòng hàng tham chiếu SKU không tồn tại

~~~sql
SELECT l.*
FROM stg_order_lines AS l
WHERE l.sku IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM products AS p
      WHERE p.sku = l.sku
  );
~~~

SKU-X không có trong products. Hàng này không thể được promote thành order_items có FK hợp lệ.

### 8.5. Dùng LEFT JOIN để xem rõ quan hệ thiếu

~~~sql
SELECT
    l.source_row_id,
    l.order_code,
    o.order_id,
    l.sku,
    p.product_id
FROM stg_order_lines AS l
LEFT JOIN orders AS o
    ON o.order_code = l.order_code
LEFT JOIN products AS p
    ON p.sku = l.sku
ORDER BY l.source_row_id;
~~~

Các cột o.order_id hoặc p.product_id bằng NULL cho thấy không tìm thấy hàng tương ứng. Tuy nhiên, nếu khóa nguồn vốn NULL, cần phân biệt với trường hợp khóa có giá trị nhưng không match.

### 8.6. LEFT JOIN và điều kiện ở WHERE

Một lỗi thường gặp là:

~~~sql
SELECT l.*
FROM stg_order_lines AS l
LEFT JOIN orders AS o
    ON o.order_code = l.order_code
WHERE o.order_status = 'PAID';
~~~

Điều kiện WHERE loại các hàng mà o.order_status là NULL, khiến kết quả gần như INNER JOIN. Nếu muốn giữ cả dòng chưa có order và đánh dấu tình trạng, hãy đặt điều kiện phù hợp trong ON hoặc dùng biểu thức CASE.

## 9. Kiểm tra giá trị không hợp lệ

### 9.1. Kiểm tra trạng thái đơn hàng

~~~sql
SELECT *
FROM stg_orders
WHERE order_status IS NULL
   OR order_status NOT IN ('NEW', 'PENDING', 'PAID', 'CANCELLED');
~~~

O-105 có status UNKNOWN nên không được nạp vào target.

### 9.2. Kiểm tra quantity và unit_price

~~~sql
SELECT *
FROM stg_order_lines
WHERE quantity IS NULL
   OR quantity <= 0
   OR unit_price IS NULL
   OR unit_price < 0;
~~~

NULL trong phép so sánh quantity <= 0 tạo UNKNOWN; vì vậy phải kiểm tra IS NULL riêng. CHECK constraint ở bảng đích cũng không thay thế NOT NULL: CHECK thường không từ chối UNKNOWN do NULL.

### 9.3. Kiểm tra khóa thiếu

~~~sql
SELECT *
FROM stg_order_lines
WHERE order_code IS NULL
   OR line_no IS NULL
   OR sku IS NULL
   OR source_item_id IS NULL;
~~~

Một khóa thiếu phải có reason code rõ. Không thay mọi NULL bằng 0 hoặc chuỗi rỗng để ép insert.

## 10. Tạo bảng quarantine để lưu lý do loại

Không nên xóa hàng lỗi khỏi staging ngay khi phát hiện. Ta lưu nguồn, số hàng và lý do:

~~~sql
CREATE TABLE data_quarantine (
    source_entity VARCHAR(30) NOT NULL,
    source_row_id BIGINT NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    CONSTRAINT pk_data_quarantine
        PRIMARY KEY (source_entity, source_row_id, reason_code)
);
~~~

Một hàng có thể có nhiều lỗi nên khóa chính gồm entity, source row và reason code.

| Entity | Reason code | Ý nghĩa |
| --- | --- | --- |
| stg_customers | MISSING_CUSTOMER_CODE | Không có khóa nghiệp vụ |
| stg_customers | DUPLICATE_SUPERSEDED | Bản cũ bị bản chuẩn thay thế |
| stg_customers | INVALID_CANONICAL_ROW | Bản mới nhất thiếu ID hoặc tên |
| stg_orders | MISSING_ORDER_CODE | Không có mã đơn |
| stg_orders | MISSING_CUSTOMER_CODE | Không có mã khách hàng |
| stg_orders | CUSTOMER_NOT_FOUND | Mã khách hàng không tồn tại |
| stg_orders | INVALID_STATUS | Trạng thái ngoài miền |
| stg_orders | DUPLICATE_SUPERSEDED | Bản cũ bị thay thế |
| stg_order_lines | MISSING_ORDER_CODE | Không có mã đơn |
| stg_order_lines | ORDER_NOT_LOADED | Đơn không tồn tại trong target |
| stg_order_lines | MISSING_SKU | Không có mã sản phẩm |
| stg_order_lines | PRODUCT_NOT_FOUND | SKU không có trong products |
| stg_order_lines | INVALID_QUANTITY | Số lượng NULL hoặc không dương |
| stg_order_lines | INVALID_UNIT_PRICE | Đơn giá NULL hoặc âm |
| stg_order_lines | DUPLICATE_SUPERSEDED | Dòng lặp đã được xử lý |

Quarantine là audit trail của lần nạp. Trong hệ thống thật, có thể bổ sung batch_id, imported_at, raw_payload, source_file và operator.

## 11. Ghi nhận bản sao bị thay thế

### 11.1. Khách hàng

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_customers', ranked.source_row_id, 'DUPLICATE_SUPERSEDED'
FROM (
    SELECT
        source_row_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_code
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_customers
    WHERE customer_code IS NOT NULL
) AS ranked
WHERE ranked.row_rank > 1;
~~~

### 11.2. Đơn hàng

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_orders', ranked.source_row_id, 'DUPLICATE_SUPERSEDED'
FROM (
    SELECT
        source_row_id,
        ROW_NUMBER() OVER (
            PARTITION BY order_code
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_orders
    WHERE order_code IS NOT NULL
) AS ranked
WHERE ranked.row_rank > 1;
~~~

### 11.3. Dòng hàng

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', ranked.source_row_id, 'DUPLICATE_SUPERSEDED'
FROM (
    SELECT
        source_row_id,
        ROW_NUMBER() OVER (
            PARTITION BY order_code, line_no
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_order_lines
    WHERE order_code IS NOT NULL
      AND line_no IS NOT NULL
) AS ranked
WHERE ranked.row_rank > 1;
~~~

Các câu trên chọn đúng một hàng canonical cho mỗi khóa. Nếu nguồn không cam kết source_version là phiên bản mới nhất, thay chính sách này bằng quarantine cả nhóm conflict để người có thẩm quyền xử lý.

## 12. Ghi nhận NULL và lỗi quan hệ

### 12.1. Khách hàng thiếu mã

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_customers', source_row_id, 'MISSING_CUSTOMER_CODE'
FROM stg_customers
WHERE customer_code IS NULL;
~~~

### 12.2. Bản khách hàng canonical thiếu trường bắt buộc

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_customers', ranked.source_row_id, 'INVALID_CANONICAL_ROW'
FROM (
    SELECT
        source_row_id,
        source_customer_id,
        full_name,
        customer_code,
        ROW_NUMBER() OVER (
            PARTITION BY customer_code
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_customers
    WHERE customer_code IS NOT NULL
) AS ranked
WHERE ranked.row_rank = 1
  AND (
      ranked.source_customer_id IS NULL
      OR ranked.full_name IS NULL
  );
~~~

### 12.3. Đơn hàng thiếu mã hoặc mã khách hàng

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_orders', source_row_id, 'MISSING_ORDER_CODE'
FROM stg_orders
WHERE order_code IS NULL;

INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_orders', source_row_id, 'MISSING_CUSTOMER_CODE'
FROM stg_orders
WHERE customer_code IS NULL;
~~~

### 12.4. Đơn hàng tham chiếu khách hàng không tồn tại

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_orders', s.source_row_id, 'CUSTOMER_NOT_FOUND'
FROM stg_orders AS s
WHERE s.customer_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.customer_code = s.customer_code
  );
~~~

### 12.5. Đơn hàng có trạng thái không hợp lệ

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_orders', ranked.source_row_id, 'INVALID_STATUS'
FROM (
    SELECT
        source_row_id,
        order_status,
        ROW_NUMBER() OVER (
            PARTITION BY order_code
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_orders
    WHERE order_code IS NOT NULL
) AS ranked
WHERE ranked.row_rank = 1
  AND (
      ranked.order_status IS NULL
      OR ranked.order_status NOT IN (
          'NEW', 'PENDING', 'PAID', 'CANCELLED'
      )
  );
~~~

Chỉ đánh giá trạng thái của hàng canonical. Nếu version mới nhất không hợp lệ, không tự quay lại dùng bản cũ hơn nếu source_version đã được xác định là thứ tự cập nhật có thẩm quyền. Hãy quarantine bản mới nhất và xử lý theo chính sách nguồn.

### 12.6. Dòng hàng thiếu hoặc không tìm thấy đơn

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', source_row_id, 'MISSING_ORDER_CODE'
FROM stg_order_lines
WHERE order_code IS NULL;

INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', l.source_row_id, 'ORDER_NOT_LOADED'
FROM stg_order_lines AS l
WHERE l.order_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.order_code = l.order_code
  );
~~~

### 12.7. Dòng hàng thiếu SKU hoặc sản phẩm không tồn tại

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', source_row_id, 'MISSING_SKU'
FROM stg_order_lines
WHERE sku IS NULL;

INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', l.source_row_id, 'PRODUCT_NOT_FOUND'
FROM stg_order_lines AS l
WHERE l.sku IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM products AS p
      WHERE p.sku = l.sku
  );
~~~

### 12.8. Dòng hàng có số lượng/đơn giá không hợp lệ

~~~sql
INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', source_row_id, 'INVALID_QUANTITY'
FROM stg_order_lines
WHERE quantity IS NULL OR quantity <= 0;

INSERT INTO data_quarantine
(source_entity, source_row_id, reason_code)
SELECT 'stg_order_lines', source_row_id, 'INVALID_UNIT_PRICE'
FROM stg_order_lines
WHERE unit_price IS NULL OR unit_price < 0;
~~~

Một dòng có thể có nhiều reason code. Ví dụ nếu vừa thiếu order_code vừa thiếu SKU, cả hai lỗi đều được ghi lại.

## 13. Promote dữ liệu hợp lệ theo thứ tự quan hệ

Nguyên tắc: nạp bảng cha trước bảng con. Trong mô hình này:

1. customers;
2. products đã được nạp;
3. orders;
4. order_items.

Mỗi bước chỉ chọn hàng canonical và thỏa các điều kiện nghiệp vụ.

### 13.1. Nạp khách hàng canonical

~~~sql
INSERT INTO customers
(customer_id, customer_code, full_name, email, phone)
SELECT
    ranked.source_customer_id,
    ranked.customer_code,
    ranked.full_name,
    ranked.email,
    ranked.phone
FROM (
    SELECT
        source_row_id,
        source_customer_id,
        customer_code,
        full_name,
        email,
        phone,
        ROW_NUMBER() OVER (
            PARTITION BY customer_code
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_customers
    WHERE customer_code IS NOT NULL
) AS ranked
WHERE ranked.row_rank = 1
  AND ranked.source_customer_id IS NOT NULL
  AND ranked.full_name IS NOT NULL;
~~~

Kết quả:

| customer_id | customer_code | full_name | email |
| ---: | --- | --- | --- |
| 1 | C001 | An Nguyen | an@example.test |
| 2 | C002 | Binh Tran | binh.new@example.test |
| 3 | C003 | Chi Le | chi@example.test |

Email của C002 lấy từ version 2. Phone NULL của C003 vẫn được giữ vì là trường tùy chọn.

### 13.2. Nạp đơn hàng có khách hàng hợp lệ

~~~sql
INSERT INTO orders
(order_id, order_code, customer_id, order_status)
SELECT
    ranked.source_order_id,
    ranked.order_code,
    c.customer_id,
    ranked.order_status
FROM (
    SELECT
        source_row_id,
        source_order_id,
        order_code,
        customer_code,
        order_status,
        ROW_NUMBER() OVER (
            PARTITION BY order_code
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_orders
    WHERE order_code IS NOT NULL
) AS ranked
JOIN customers AS c
    ON c.customer_code = ranked.customer_code
WHERE ranked.row_rank = 1
  AND ranked.source_order_id IS NOT NULL
  AND ranked.order_status IN (
      'NEW', 'PENDING', 'PAID', 'CANCELLED'
  );
~~~

INNER JOIN chỉ nhận đơn có customer_code khớp một khách hàng đã được nạp. Các dòng có customer_code NULL hoặc C999 không qua được phép join. O-105 không qua điều kiện trạng thái.

Kết quả:

| order_id | order_code | customer_id | order_status |
| ---: | --- | ---: | --- |
| 100 | O-100 | 1 | PAID |
| 101 | O-101 | 2 | CANCELLED |
| 104 | O-104 | 3 | NEW |

O-101 dùng version 2, nên trạng thái canonical là CANCELLED.

### 13.3. Nạp dòng hàng có đủ đơn và sản phẩm

~~~sql
INSERT INTO order_items
(item_id, order_id, line_no, product_id, quantity, unit_price)
SELECT
    ranked.source_item_id,
    o.order_id,
    ranked.line_no,
    p.product_id,
    ranked.quantity,
    ranked.unit_price
FROM (
    SELECT
        source_row_id,
        source_item_id,
        order_code,
        line_no,
        sku,
        quantity,
        unit_price,
        ROW_NUMBER() OVER (
            PARTITION BY order_code, line_no
            ORDER BY source_version DESC, source_row_id DESC
        ) AS row_rank
    FROM stg_order_lines
    WHERE order_code IS NOT NULL
      AND line_no IS NOT NULL
) AS ranked
JOIN orders AS o
    ON o.order_code = ranked.order_code
JOIN products AS p
    ON p.sku = ranked.sku
WHERE ranked.row_rank = 1
  AND ranked.source_item_id IS NOT NULL
  AND ranked.line_no > 0
  AND ranked.quantity > 0
  AND ranked.unit_price IS NOT NULL
  AND ranked.unit_price >= 0;
~~~

Kết quả:

| item_id | order_code | line_no | SKU | quantity | unit_price |
| ---: | --- | ---: | --- | ---: | ---: |
| 1001 | O-100 | 1 | SKU-A | 2 | 10.00 |
| 1002 | O-100 | 2 | SKU-B | 1 | 25.00 |
| 1003 | O-101 | 1 | SKU-A | 1 | 10.00 |

Dòng trùng O-101 line 1 chỉ được chọn một lần. Các dòng có order không tồn tại, SKU thiếu, quantity NULL/0 hoặc unit_price NULL đều bị loại khỏi bước promote và có thể được tra cứu trong staging/quarantine.

## 14. Xác minh dữ liệu sau khi nạp

### 14.1. Đếm bản ghi từng bảng

~~~sql
SELECT 'customers' AS table_name, COUNT(*) AS row_count
FROM customers
UNION ALL
SELECT 'products', COUNT(*)
FROM products
UNION ALL
SELECT 'orders', COUNT(*)
FROM orders
UNION ALL
SELECT 'order_items', COUNT(*)
FROM order_items;
~~~

Kết quả mong đợi:

| Bảng | Số hàng |
| --- | ---: |
| customers | 3 |
| products | 3 |
| orders | 3 |
| order_items | 3 |

### 14.2. Kiểm tra NULL ở trường bắt buộc

~~~sql
SELECT *
FROM customers
WHERE customer_id IS NULL
   OR customer_code IS NULL
   OR full_name IS NULL;

SELECT *
FROM orders
WHERE order_id IS NULL
   OR order_code IS NULL
   OR customer_id IS NULL
   OR order_status IS NULL;

SELECT *
FROM order_items
WHERE item_id IS NULL
   OR order_id IS NULL
   OR line_no IS NULL
   OR product_id IS NULL
   OR quantity IS NULL
   OR unit_price IS NULL;
~~~

Các truy vấn phải trả 0 hàng nếu schema và promote đã đúng.

### 14.3. Kiểm tra orphan bằng anti-join

~~~sql
SELECT oi.*
FROM order_items AS oi
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.order_id = oi.order_id
);
~~~

~~~sql
SELECT oi.*
FROM order_items AS oi
WHERE NOT EXISTS (
    SELECT 1
    FROM products AS p
    WHERE p.product_id = oi.product_id
);
~~~

Cả hai phải trả 0 hàng.

### 14.4. Kiểm tra duplicate business key trong target

~~~sql
SELECT customer_code, COUNT(*) AS copies
FROM customers
GROUP BY customer_code
HAVING COUNT(*) > 1;

SELECT order_code, COUNT(*) AS copies
FROM orders
GROUP BY order_code
HAVING COUNT(*) > 1;

SELECT order_id, line_no, COUNT(*) AS copies
FROM order_items
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Các truy vấn phải trả 0 hàng. Unique constraints cũng bảo vệ điều này, nhưng query kiểm tra giúp phát hiện vấn đề nếu constraint chưa được tạo hoặc bị vô hiệu hóa trong quá trình nạp.

### 14.5. Xem quarantine theo lý do

~~~sql
SELECT
    source_entity,
    reason_code,
    COUNT(*) AS affected_rows
FROM data_quarantine
GROUP BY source_entity, reason_code
ORDER BY source_entity, reason_code;
~~~

Xem chi tiết các hàng bị quarantine:

~~~sql
SELECT *
FROM data_quarantine
ORDER BY source_entity, source_row_id, reason_code;
~~~

Trong hệ thống thật, cần nối source_row_id về bảng staging tương ứng để hiển thị payload gốc cho người xử lý.

## 15. Xử lý duplicate conflict đúng cách

Quy tắc source_version DESC trong lab chỉ an toàn vì ta giả định nguồn cam kết version mới hơn là bản cập nhật có thẩm quyền. Nếu không có cam kết đó, không được tự động chọn hàng có source_row_id lớn nhất chỉ vì nó xuất hiện sau trong file.

Cách phát hiện các nhóm conflict:

~~~sql
SELECT customer_code, COUNT(*) AS copies
FROM stg_customers
WHERE customer_code IS NOT NULL
GROUP BY customer_code
HAVING COUNT(*) > 1;
~~~

Sau đó truy vấn toàn bộ nội dung của các nhóm này và phân loại:

- **Exact duplicate:** mọi thuộc tính nghiệp vụ giống nhau; có thể giữ một hàng và ghi audit số hàng gộp.
- **Newer version:** nguồn có version/timestamp đáng tin cậy; chọn phiên bản mới theo chính sách.
- **Conflicting duplicate:** không biết hàng nào đúng; quarantine toàn nhóm để review.
- **Duplicate do khác chuẩn hóa:** ví dụ mã C001 và c001, hoặc có whitespace; phải định nghĩa normalization/collation trước khi quyết định có cùng khóa hay không.

Không dùng MAX(source_row_id) như một quy tắc nghiệp vụ nếu source row ID chỉ là số thứ tự nhập file. Thứ tự xuất hiện không chứng minh bản ghi nào mới hơn.

## 16. Transaction và khả năng chạy lại

### 16.1. Chạy promote trong transaction

Nếu DBMS và thao tác cho phép, gom bước promote vào một transaction:

~~~sql
-- Pseudocode transaction control:
-- BEGIN TRANSACTION;

-- Promote customers.
-- Promote orders.
-- Promote order_items.
-- Run integrity checks.

-- COMMIT;
-- Nếu một bước bắt buộc thất bại: ROLLBACK.
~~~

Trong JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        promoteCustomers(connection);
        promoteOrders(connection);
        promoteOrderItems(connection);
        verifyTarget(connection);

        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

Không giữ transaction mở trong lúc chờ người dùng review thủ công. Tách bước review thành workflow riêng, sau đó chạy promote trong transaction ngắn.

### 16.2. Làm cho batch có thể chạy lại

Các câu INSERT trong ví dụ không tự động idempotent. Nếu chạy lại, primary key hoặc unique constraint có thể báo lỗi. Có hai cách:

1. Dùng database lab riêng, xóa dữ liệu theo thứ tự phụ thuộc trước mỗi lần seed;
2. Dùng batch_id và trạng thái xử lý để chỉ nạp một batch một lần, đồng thời có chiến lược upsert rõ ràng.

Với lab dùng riêng, có thể reset theo thứ tự con trước cha:

~~~sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;

DELETE FROM data_quarantine;
DELETE FROM stg_order_lines;
DELETE FROM stg_orders;
DELETE FROM stg_customers;
~~~

**Chỉ chạy reset trên database lab dùng riêng.** Không chạy các lệnh DELETE này trên database có dữ liệu người dùng hoặc môi trường dùng chung.

Không thêm ON CONFLICT DO NOTHING hoặc cú pháp tương đương một cách máy móc để che lỗi. Nếu một batch chạy hai lần, cần biết đó là lần chạy lại hợp lệ hay dữ liệu nguồn đã xung đột.

### 16.3. Gắn batch_id trong hệ thống thật

Khi vận hành nhiều lần nạp, nên có:

- batch_id duy nhất;
- source_file/source_system;
- imported_at;
- số hàng đọc;
- số hàng hợp lệ;
- số hàng duplicate;
- số hàng orphan;
- số hàng invalid;
- trạng thái batch: RECEIVED, VALIDATED, PROMOTED, FAILED;
- người hoặc service khởi tạo batch.

Nhờ đó có thể truy vết dữ liệu và chạy lại đúng batch mà không trộn lẫn các lần import.

## 17. Khác biệt giữa DBMS cần lưu ý

### 17.1. Kiểu dữ liệu

| DBMS | Số nguyên lớn | Chuỗi | Decimal |
| --- | --- | --- | --- |
| PostgreSQL | BIGINT | VARCHAR/TEXT | NUMERIC/DECIMAL |
| MySQL | BIGINT | VARCHAR/TEXT | DECIMAL |
| SQL Server | BIGINT | VARCHAR/NVARCHAR | DECIMAL |
| Oracle | NUMBER(19) | VARCHAR2 | NUMBER |
| SQLite | INTEGER | TEXT | NUMERIC affinity |

SQLite dùng type affinity và có cách lưu kiểu động. Không giả định VARCHAR(30) luôn giới hạn đúng 30 ký tự như các DBMS khác; vẫn cần validation.

### 17.2. Multi-row INSERT

Lab dùng từng câu INSERT một hàng để dễ đọc và tương thích rộng. PostgreSQL, MySQL, SQL Server và SQLite hỗ trợ nhiều bộ VALUES trong một INSERT. Oracle có thể dùng INSERT ALL hoặc các câu INSERT riêng tùy nhu cầu/version.

### 17.3. Window functions

ROW_NUMBER được hỗ trợ ở các phiên bản hiện đại:

- PostgreSQL;
- MySQL 8+;
- SQL Server;
- Oracle;
- SQLite 3.25+.

Nếu cần hỗ trợ engine cũ hơn, dùng staging và xử lý canonical trong ứng dụng hoặc viết chiến lược anti-join phù hợp. Luôn có tie-breaker duy nhất trong ORDER BY để kết quả xác định.

### 17.4. Foreign key enforcement

SQLite cần bật:

~~~sql
PRAGMA foreign_keys = ON;
~~~

Cấu hình này cần áp dụng trên từng connection phù hợp với driver. MySQL nên dùng engine hỗ trợ foreign key như InnoDB. Một số hệ thống có thể tạm tắt constraint trong bulk load; sau đó phải kiểm tra dữ liệu orphan và bật lại constraint trước khi hoàn tất.

Không tắt FK để nạp dữ liệu lỗi rồi quên bật lại. Staging không có FK là nơi thích hợp để giữ raw input.

### 17.5. CHECK constraint

MySQL chỉ thực thi CHECK constraint từ 8.0.16 trở lên. Với bản cũ, cần validation bổ sung hoặc cơ chế constraint khác. Kiểm tra phiên bản thật thay vì giả định DDL được chấp nhận đồng nghĩa constraint đang hoạt động.

### 17.6. Case sensitivity và collation

Mã C001 và c001 có thể được coi là bằng nhau hoặc khác nhau tùy collation. Trước khi phát hiện duplicate, hãy định nghĩa business key có phân biệt hoa/thường không. Nếu không phân biệt, normalize mã ở một tầng thống nhất và tạo unique index phù hợp.

## 18. Checklist vận hành một lần nạp dữ liệu

**Trước khi nạp**

1. Xác định nguồn, batch_id và số hàng dự kiến.
2. Xác định business key của từng loại bản ghi.
3. Xác định trường bắt buộc và trường nullable.
4. Xác định nguồn nào là authoritative khi có version conflict.
5. Nạp raw vào staging, không loại hàng trùng ngay khi import.

**Trong khi kiểm tra**

6. Đếm tổng hàng và NULL theo cột.
7. Phân biệt duplicate exact và duplicate conflict.
8. Tìm missing key và orphan reference.
9. Kiểm tra miền giá trị, precision/scale và format.
10. Ghi reason code vào quarantine.

**Khi promote**

11. Chọn canonical row bằng quy tắc xác định.
12. Nạp bảng cha trước bảng con.
13. Dùng PK/FK/UNIQUE/CHECK để bảo vệ target.
14. Chạy transaction ngắn và rollback khi bước bắt buộc thất bại.

**Sau khi promote**

15. Đối chiếu số hàng staging, target và quarantine.
16. Kiểm tra NULL ở trường bắt buộc.
17. Kiểm tra duplicate business key.
18. Kiểm tra orphan bằng anti-join.
19. Lưu log batch và reason code.
20. Chỉ đánh dấu batch hoàn tất khi các kiểm tra bắt buộc đạt.

## 19. Bài tập thực hành có đáp án

### Bài 1 — Phân biệt NULL và orphan

Một order có customer_code NULL. Đây là orphan hay missing key?

**Đáp án:** missing key. Không có giá trị để tìm khách hàng. Orphan là trường hợp có mã, ví dụ C999, nhưng không có khách hàng tương ứng.

### Bài 2 — Duplicate business key

Viết truy vấn tìm customer_code xuất hiện nhiều hơn một lần trong staging.

**Đáp án:**

~~~sql
SELECT customer_code, COUNT(*) AS copies
FROM stg_customers
WHERE customer_code IS NOT NULL
GROUP BY customer_code
HAVING COUNT(*) > 1;
~~~

### Bài 3 — Duplicate exact

Vì sao chỉ GROUP BY customer_code chưa đủ để kết luận hai hàng là bản sao giống hệt?

**Đáp án:** vì cùng business key có thể chứa tên/email/phone khác nhau. Cần so sánh các thuộc tính nghiệp vụ hoặc review toàn bộ nhóm.

### Bài 4 — Chọn phiên bản mới

Dùng ROW_NUMBER chọn bản customer có source_version lớn nhất, nếu hòa chọn source_row_id lớn nhất.

**Đáp án:**

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_code
    ORDER BY source_version DESC, source_row_id DESC
)
~~~

Giữ hàng có rank 1, với điều kiện source_version thực sự có ý nghĩa thứ tự.

### Bài 5 — Tìm khách hàng không tồn tại

Viết truy vấn tìm đơn có customer_code nhưng không có trong customers.

**Đáp án:**

~~~sql
SELECT s.*
FROM stg_orders AS s
WHERE s.customer_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.customer_code = s.customer_code
  );
~~~

### Bài 6 — Tìm đơn hàng không tồn tại

Tìm dòng hàng tham chiếu order_code không có trong orders.

**Đáp án:**

~~~sql
SELECT l.*
FROM stg_order_lines AS l
WHERE l.order_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.order_code = l.order_code
  );
~~~

### Bài 7 — Tìm SKU không có trong danh mục

**Đáp án:**

~~~sql
SELECT l.*
FROM stg_order_lines AS l
WHERE l.sku IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM products AS p
      WHERE p.sku = l.sku
  );
~~~

### Bài 8 — NULL và phép so sánh

Vì sao quantity <= 0 không tìm thấy hàng có quantity NULL?

**Đáp án:** phép so sánh với NULL cho UNKNOWN, không phải TRUE. Dùng quantity IS NULL OR quantity <= 0.

### Bài 9 — Kiểm tra quantity

**Đáp án:**

~~~sql
SELECT *
FROM stg_order_lines
WHERE quantity IS NULL OR quantity <= 0;
~~~

### Bài 10 — Kiểm tra trạng thái

Tìm order có trạng thái không thuộc NEW, PENDING, PAID, CANCELLED, đồng thời bắt NULL.

**Đáp án:**

~~~sql
SELECT *
FROM stg_orders
WHERE order_status IS NULL
   OR order_status NOT IN ('NEW', 'PENDING', 'PAID', 'CANCELLED');
~~~

### Bài 11 — Vì sao staging không có FK?

**Đáp án:** để giữ raw rows có quan hệ thiếu, phân tích và ghi quarantine trước khi promote. Bảng đích mới áp dụng FK.

### Bài 12 — Vì sao nạp parent trước child?

**Đáp án:** child cần tham chiếu đến khóa cha đã tồn tại. Nạp customers trước orders, orders và products trước order_items giúp FK được thỏa mãn.

### Bài 13 — Tại sao O-102 không được nạp?

**Đáp án:** O-102 tham chiếu C999 nhưng customers không có customer_code C999. INNER JOIN với customers loại đơn này; dòng hàng O-102 sau đó cũng không thể promote.

### Bài 14 — Tại sao O-101 có trạng thái CANCELLED?

**Đáp án:** hai bản ghi cùng order_code O-101; source_version 2 cao hơn version 1 và lab quy định version cao hơn là bản mới nhất.

### Bài 15 — Duplicate conflict

Nếu hai hàng cùng customer_code nhưng email khác nhau và không có source_version đáng tin cậy, nên làm gì?

**Đáp án:** quarantine nhóm conflict để review hoặc dùng quy tắc nghiệp vụ được phê duyệt. Không chọn tùy tiện hàng cuối file.

### Bài 16 — ROW_NUMBER tie-breaker

Vì sao cần source_row_id trong ORDER BY của ROW_NUMBER?

**Đáp án:** khi source_version bằng nhau, tie-breaker làm thứ tự xác định và kết quả có thể tái lập.

### Bài 17 — Unique key

Vì sao target cần UNIQUE(customer_code) dù đã deduplicate staging?

**Đáp án:** để database bảo vệ invariant cuối cùng trước lỗi code, import đồng thời hoặc một luồng ghi khác.

### Bài 18 — NULL ở email

Email NULL có nhất thiết là lỗi không?

**Đáp án:** không nếu email là trường tùy chọn. Phải phân biệt nullable hợp lệ với NULL ở khóa hoặc trường bắt buộc.

### Bài 19 — Quarantine nhiều lý do

Một dòng hàng vừa thiếu SKU vừa có quantity bằng 0. Có thể lưu hai reason code không?

**Đáp án:** có. Khóa quarantine gồm source_entity, source_row_id và reason_code cho phép một hàng có nhiều lỗi.

### Bài 20 — LEFT JOIN và WHERE

Vì sao thêm WHERE parent.id IS NOT NULL sau LEFT JOIN khiến các hàng thiếu quan hệ biến mất?

**Đáp án:** điều kiện WHERE loại các hàng có cột parent NULL, khiến kết quả gần tương đương INNER JOIN.

### Bài 21 — Kiểm tra orphan sau promote

**Đáp án:**

~~~sql
SELECT oi.*
FROM order_items AS oi
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.order_id = oi.order_id
);
~~~

### Bài 22 — CHECK và NULL

CHECK(quantity > 0) có tự ngăn quantity NULL không?

**Đáp án:** không phải lúc nào cũng vậy; UNKNOWN do NULL thường không bị CHECK từ chối. Kết hợp NOT NULL.

### Bài 23 — Chạy lại batch

Vì sao không nên chạy lại INSERT seed một cách mù quáng?

**Đáp án:** primary key/unique constraint có thể báo duplicate hoặc tạo dữ liệu sai nếu không có khóa. Dùng batch_id/idempotency hoặc reset riêng trong lab dùng một lần.

### Bài 24 — Thứ tự DELETE reset

Nếu reset bảng đích có FK, xóa bảng nào trước?

**Đáp án:** xóa bảng con trước: order_items, rồi orders, sau đó customers và products. Chỉ thực hiện trên database lab.

### Bài 25 — Oracle empty string

Có thể dùng empty string để phân biệt “chưa cung cấp” với NULL trên Oracle VARCHAR2 không?

**Đáp án:** không. Oracle xem chuỗi character độ dài 0 như NULL. Nếu cần phân biệt, lưu thêm trạng thái riêng.

### Bài 26 — SQLite foreign keys

Điều gì cần làm để SQLite thực thi FK?

**Đáp án:** bật PRAGMA foreign_keys = ON trên connection phù hợp; không giả định constraint tự được thực thi nếu chưa bật.

### Bài 27 — MySQL CHECK

Có thể giả định CHECK được thực thi trên mọi phiên bản MySQL không?

**Đáp án:** không. MySQL thực thi CHECK từ 8.0.16; phải xác minh version tối thiểu.

### Bài 28 — Đối chiếu số hàng

Staging có 11 dòng hàng nhưng target có 3. Có thể kết luận mất dữ liệu không?

**Đáp án:** chưa. Cần đối chiếu số hàng được promote, duplicate superseded, missing relation và invalid values. Mỗi hàng phải có trạng thái xử lý hoặc lý do rõ.

## 20. Tổng kết

Nạp dữ liệu mẫu có NULL, bản sao và quan hệ thiếu cần một quy trình có thể giải thích và kiểm chứng:

- **Staging** giữ nguyên dữ liệu nguồn, kể cả NULL, duplicate và orphan.
- **Profiling** đếm hàng, NULL và nhóm trùng trước khi làm sạch.
- **Deduplication** phải dựa trên business key và quy tắc chọn bản chuẩn có thẩm quyền.
- **Anti-join/NOT EXISTS** tìm quan hệ thiếu; phân biệt khóa NULL với mã tham chiếu không tồn tại.
- **Quarantine** giữ source row và reason code để truy vết.
- **Promotion** nạp bảng cha trước bảng con, dùng PK/FK/UNIQUE/CHECK để bảo vệ target.
- **Verification** đối chiếu số hàng, NULL, duplicate và orphan sau khi nạp.
- **Transaction và batch_id** giúp kiểm soát rollback, audit và khả năng chạy lại.

Nguyên tắc cốt lõi: **không xóa dữ liệu lỗi trước khi hiểu nó, không tự đoán cách giải quyết duplicate conflict, và không bỏ qua quan hệ thiếu chỉ để INSERT thành công**. Một lần nạp dữ liệu tốt phải giải thích được mỗi hàng đã được chấp nhận, gộp, quarantine hay từ chối vì lý do nào.
