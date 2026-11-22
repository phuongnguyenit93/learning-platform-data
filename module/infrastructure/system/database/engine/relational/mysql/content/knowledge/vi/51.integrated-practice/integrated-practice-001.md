# Xây dựng schema đơn hàng với khóa ngoại, CHECK và dữ liệu mẫu

Bài thực hành này thuộc module **DATABASE_MYSQL**. Mục tiêu là xây dựng một schema đơn hàng nhỏ nhưng có đủ các quan hệ và quy tắc dữ liệu thường gặp trong ứng dụng bán hàng: khách hàng, sản phẩm, đơn hàng và dòng hàng. Ta sẽ dùng khóa chính, khóa duy nhất, khóa ngoại, CHECK constraint, kiểu dữ liệu phù hợp và dữ liệu mẫu để kiểm chứng thiết kế.

Một schema tốt cần bảo vệ những quy tắc quan trọng ngay tại database. Ứng dụng có thể kiểm tra dữ liệu trước khi ghi, nhưng nhiều service, job nền hoặc tác vụ import vẫn có thể ghi trực tiếp. PRIMARY KEY, UNIQUE, FOREIGN KEY và CHECK giúp MySQL từ chối những trạng thái dữ liệu không hợp lệ ngay cả khi một luồng ứng dụng bỏ sót validation.

Bài thực hành sử dụng InnoDB và MySQL 8.0.16 trở lên để CHECK constraint được thực thi. Nếu dùng phiên bản cũ hơn, cần lưu ý rằng MySQL trước 8.0.16 phân tích cú pháp CHECK nhưng không thực thi điều kiện đó. Hãy xác nhận phiên bản trước khi dựa vào CHECK để bảo vệ dữ liệu production.

## 1. Mô hình nghiệp vụ và phạm vi

Ta xây dựng bốn thực thể:

- **customers:** thông tin khách hàng.
- **products:** danh mục sản phẩm và giá bán hiện tại.
- **orders:** phần đầu đơn hàng, gồm khách hàng, trạng thái, thời điểm và tổng tiền.
- **order_items:** từng sản phẩm, số lượng, đơn giá tại thời điểm đặt và chiết khấu dòng hàng.

Quan hệ:

~~~text
customers 1 -------- N orders
                       |
                       |
                       1
                       |
                       N
                  order_items
                       N
                       |
                       1
                    products
~~~

Một khách hàng có thể có nhiều đơn hàng. Một đơn hàng có nhiều dòng hàng. Mỗi dòng hàng tham chiếu một sản phẩm. Một sản phẩm có thể xuất hiện trong nhiều đơn hàng.

Trong mô hình này, đơn giá trong order_items là **giá chụp tại thời điểm mua**. Không lấy giá hiện tại từ products để tính lại đơn cũ, vì giá sản phẩm có thể thay đổi sau khi khách đã đặt hàng. Tương tự, thông tin khách hàng có thể được lưu thêm dưới dạng snapshot trên đơn hàng nếu nghiệp vụ cần giữ nguyên địa chỉ giao hàng hoặc tên người nhận tại thời điểm mua.

Phạm vi bài thực hành:

1. Tạo database và bảng theo đúng thứ tự phụ thuộc khóa ngoại.
2. Chọn kiểu dữ liệu, primary key, unique key và index.
3. Khai báo foreign key với hành vi xóa/cập nhật có chủ đích.
4. Thêm CHECK constraint cho giá, số lượng, trạng thái và tổng tiền.
5. Chèn dữ liệu mẫu trong transaction.
6. Truy vấn đơn hàng bằng JOIN và tổng hợp.
7. Thử các trường hợp hợp lệ và không hợp lệ.
8. Kiểm tra metadata và đối chiếu tính nhất quán.

Ta chưa xây dựng đầy đủ tồn kho, thanh toán, vận chuyển, thuế, hoàn tiền hoặc lịch sử trạng thái. Các phần đó có thể được bổ sung sau khi schema cốt lõi đã rõ ràng.

## 2. Chọn kiểu dữ liệu và quy tắc khóa

Trước khi viết DDL, cần thống nhất các lựa chọn.

| Thuộc tính | Lựa chọn | Lý do |
|---|---|---|
| ID nội bộ | BIGINT UNSIGNED AUTO_INCREMENT | Phạm vi lớn, không âm, dễ tham chiếu |
| Email | VARCHAR(254) | Giới hạn độ dài phù hợp cho địa chỉ email |
| SKU | VARCHAR(64) | Mã sản phẩm có thể chứa chữ và dấu phân cách |
| Giá và tiền | DECIMAL(p,2) | Tránh sai số nhị phân của FLOAT/DOUBLE |
| Số lượng | INT UNSIGNED | Số lượng hàng không âm |
| Trạng thái | VARCHAR có CHECK | Dễ đọc và có thể kiểm soát tập giá trị |
| Thời điểm | DATETIME(6) | Giữ thời điểm cùng phần microsecond theo quy ước ứng dụng |
| Engine | InnoDB | Hỗ trợ transaction, foreign key và khóa hàng |
| Charset | utf8mb4 | Hỗ trợ Unicode đầy đủ |

### 2.1. PRIMARY KEY

Mỗi bảng có một primary key ổn định. ID nội bộ không nên phụ thuộc email, SKU hoặc số đơn hàng vì các giá trị nghiệp vụ có thể thay đổi theo chính sách.

Các cột được tham chiếu bởi foreign key phải có index phù hợp; trong bài này, khóa chính của bảng cha đáp ứng yêu cầu đó.

### 2.2. UNIQUE

Ta dùng unique key cho:

- Email khách hàng.
- SKU sản phẩm.
- Số đơn hàng.
- Cặp order_id và product_id trong order_items.

Unique key trên cặp order_id/product_id có nghĩa một sản phẩm chỉ xuất hiện một dòng trong một đơn hàng. Nếu nghiệp vụ cần nhiều dòng riêng cho cùng sản phẩm, chẳng hạn các lô hàng hoặc mức giá khác nhau, hãy bỏ unique key này hoặc thêm thuộc tính phân biệt vào khóa.

Email trong ví dụ dùng collation không phân biệt hoa thường ở cấp database. Điều đó có thể khiến hai email chỉ khác kiểu chữ được xem là trùng. Hãy xác định quy tắc chuẩn hóa email của sản phẩm trước khi áp dụng trong hệ thống thực tế.

### 2.3. FOREIGN KEY

Foreign key bảo đảm hàng con tham chiếu tới hàng cha đang tồn tại. Kiểu dữ liệu của hai phía cần tương thích, bao gồm kích thước và thuộc tính UNSIGNED.

Ta chọn hành vi:

- Không xóa khách hàng nếu còn đơn hàng: ON DELETE RESTRICT.
- Không xóa sản phẩm đã được tham chiếu bởi dòng đơn hàng: ON DELETE RESTRICT.
- Khi xóa một đơn hàng trong môi trường demo, các dòng hàng của nó được xóa theo: ON DELETE CASCADE.

Trong hệ thống bán hàng thực tế, thường không xóa đơn hàng đã phát sinh nghiệp vụ; có thể dùng trạng thái hủy hoặc lưu trữ. CASCADE ở đây minh họa quan hệ sở hữu giữa order và order_items. Chỉ dùng khi việc xóa cha thực sự đồng nghĩa xóa con theo quy tắc nghiệp vụ.

### 2.4. CHECK

CHECK kiểm tra điều kiện trên hàng đang ghi:

- Giá sản phẩm không âm.
- Cờ active chỉ nhận 0 hoặc 1.
- Trạng thái đơn hàng thuộc tập cho phép.
- Số lượng dòng hàng lớn hơn 0.
- Chiết khấu không âm và không lớn hơn thành tiền trước chiết khấu.
- Tổng tiền đơn hàng bằng subtotal trừ discount cộng shipping fee.

CHECK không thay thế foreign key và không thể kiểm tra tổng SUM của các dòng hàng trong bảng khác. Quy tắc liên bảng phải được bảo đảm trong transaction của ứng dụng, trigger hoặc quy trình dữ liệu phù hợp.

## 3. Tạo database

Chạy trong môi trường thực hành:

~~~sql
CREATE DATABASE mysql_order_lab
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE mysql_order_lab;
~~~

Nếu database đã tồn tại, không chạy lại CREATE DATABASE như một bước reset. Hãy dùng database test riêng hoặc chủ động kiểm tra dữ liệu trước khi tạo lại schema.

Kiểm tra phiên bản server:

~~~sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution,
       @@default_storage_engine AS default_engine,
       @@sql_mode AS sql_mode;
~~~

Bài thực hành yêu cầu InnoDB. DDL sẽ khai báo ENGINE=InnoDB tường minh để không phụ thuộc cấu hình mặc định.

## 4. Tạo bảng customers

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(30) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Giải thích:

- customer_id là khóa chính tự tăng.
- email là bắt buộc và duy nhất.
- full_name là bắt buộc.
- phone có thể NULL vì khách hàng có thể chưa cung cấp số điện thoại.
- created_at lưu thời điểm tạo bản ghi với microsecond precision.

Không dùng email làm primary key. Email có thể thay đổi; ID nội bộ giúp các bảng liên quan giữ tham chiếu ổn định.

Nếu nghiệp vụ cho phép nhiều khách hàng dùng cùng email ở các tenant khác nhau, unique key cần bao gồm tenant_id. Schema này đang mô hình một cửa hàng đơn lẻ, email duy nhất toàn bảng.

## 5. Tạo bảng products

~~~sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(13,2) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT chk_products_unit_price CHECK (unit_price >= 0.00),
    CONSTRAINT chk_products_is_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Giải thích:

- SKU là mã nghiệp vụ duy nhất.
- unit_price dùng DECIMAL(13,2) vì tiền không nên lưu bằng FLOAT/DOUBLE.
- is_active cho phép ngừng bán sản phẩm mà vẫn giữ lịch sử đơn hàng.
- CHECK bảo vệ giá không âm và cờ trạng thái hợp lệ.
- updated_at được cập nhật khi hàng thay đổi.

Không xóa sản phẩm chỉ vì ngừng bán. Dòng đơn hàng cũ vẫn cần tham chiếu tới sản phẩm để báo cáo và kiểm toán. Ta dùng is_active = 0 để ngừng bán.

### 5.1. Vì sao giá trong order_items vẫn cần lưu riêng?

products.unit_price là giá hiện tại. Khi sản phẩm tăng giá từ 100.000 lên 120.000, đơn hàng được tạo trước đó vẫn phải giữ đơn giá 100.000. Vì vậy order_items có cột unit_price riêng làm snapshot.

Không tạo truy vấn lịch sử bằng cách JOIN order_items với products rồi lấy products.unit_price để tính tiền đơn cũ. Cột giá trong order_items mới là giá giao dịch.

## 6. Tạo bảng orders

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_number VARCHAR(32) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    currency CHAR(3) NOT NULL DEFAULT 'VND',
    ordered_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    subtotal DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    discount_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    shipping_fee DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_number UNIQUE (order_number),

    KEY idx_orders_customer_ordered_at (customer_id, ordered_at),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CONSTRAINT chk_orders_status
        CHECK (status IN (
            'PENDING',
            'CONFIRMED',
            'PAID',
            'CANCELLED',
            'FULFILLED'
        )),

    CONSTRAINT chk_orders_amounts
        CHECK (
            subtotal >= 0.00
            AND discount_amount >= 0.00
            AND shipping_fee >= 0.00
            AND total_amount >= 0.00
            AND discount_amount <= subtotal
            AND total_amount = subtotal - discount_amount + shipping_fee
        )
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Giải thích:

- order_number là mã đơn hàng hiển thị cho người dùng, có unique key.
- customer_id tham chiếu customers.
- status bị giới hạn bởi CHECK để tránh các giá trị tùy tiện.
- currency lưu mã tiền tệ ba ký tự; ví dụ dùng VND.
- subtotal là tổng tiền hàng trước chiết khấu.
- discount_amount là tổng chiết khấu.
- shipping_fee là phí vận chuyển.
- total_amount phải bằng subtotal - discount_amount + shipping_fee.

Index idx_orders_customer_ordered_at phục vụ truy vấn đơn theo khách hàng và sắp xếp theo thời điểm. Cột customer_id đứng đầu index cũng hỗ trợ tra cứu khóa ngoại.

Các tổng tiền trên header là dữ liệu tổng hợp. CHECK chỉ xác minh công thức giữa các cột cùng hàng; nó không tự tính SUM từ order_items. Ứng dụng phải cập nhật các cột này cùng transaction với các dòng hàng.

### 6.1. Vì sao không xóa khách hàng có đơn hàng?

ON DELETE RESTRICT ngăn xóa khách hàng khi còn orders tham chiếu. Đây là lựa chọn phù hợp khi lịch sử đơn hàng cần được giữ lại. Nếu cần ẩn hoặc vô hiệu hóa khách hàng, có thể thêm cột trạng thái thay vì xóa hàng.

## 7. Tạo bảng order_items

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13,2) NOT NULL,
    discount_amount DECIMAL(13,2) NOT NULL DEFAULT 0.00,

    line_total DECIMAL(15,2)
        GENERATED ALWAYS AS (
            quantity * unit_price - discount_amount
        ) STORED,

    PRIMARY KEY (order_item_id),

    CONSTRAINT uq_order_items_order_product
        UNIQUE (order_id, product_id),

    KEY idx_order_items_product_id (product_id),

    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CONSTRAINT chk_order_items_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_order_items_amounts
        CHECK (
            unit_price >= 0.00
            AND discount_amount >= 0.00
            AND discount_amount <= quantity * unit_price
        )
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
~~~

Giải thích:

- order_id tham chiếu đơn hàng.
- product_id tham chiếu sản phẩm.
- quantity phải lớn hơn 0.
- unit_price là giá chụp tại thời điểm mua.
- discount_amount là chiết khấu cho dòng hàng.
- line_total là generated column được tính từ số lượng, đơn giá và chiết khấu.

Unique key (order_id, product_id) ngăn cùng một sản phẩm xuất hiện nhiều dòng trong cùng đơn. Nếu cần nhiều dòng cho một sản phẩm, ví dụ chia theo lô hoặc khuyến mãi khác nhau, hãy điều chỉnh khóa duy nhất theo mô hình đó.

Index idx_order_items_product_id hỗ trợ tra cứu tất cả đơn hàng có chứa một sản phẩm và giúp MySQL kiểm tra foreign key từ products. Unique index bắt đầu bằng order_id đã hỗ trợ phần tham chiếu orders.

Generated column giúp tránh việc ứng dụng tự ghi line_total không khớp với quantity, unit_price và discount_amount. Nếu phiên bản hoặc mô hình cần tương thích không hỗ trợ generated column theo cách này, có thể lưu line_total do ứng dụng tính nhưng phải kiểm tra trong transaction.

### 7.1. Vì sao ON DELETE CASCADE chỉ đặt ở order_items.order_id?

Một dòng hàng thuộc về một đơn hàng. Khi xóa đơn hàng trong database thực hành, xóa dòng hàng theo là quan hệ sở hữu rõ ràng.

Sản phẩm không sở hữu dòng hàng lịch sử; đơn hàng cần giữ tham chiếu tới sản phẩm đã mua. Vì vậy product_id dùng ON DELETE RESTRICT. Thực tế thường đánh dấu sản phẩm ngừng bán thay vì xóa.

## 8. Kiểm tra schema sau khi tạo

Đọc DDL thực tế:

~~~sql
SHOW CREATE TABLE customers\G
SHOW CREATE TABLE products\G
SHOW CREATE TABLE orders\G
SHOW CREATE TABLE order_items\G
~~~

Kiểm tra index:

~~~sql
SHOW INDEX FROM customers;
SHOW INDEX FROM products;
SHOW INDEX FROM orders;
SHOW INDEX FROM order_items;
~~~

Kiểm tra foreign key và CHECK constraint trong metadata:

~~~sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_TYPE, CONSTRAINT_NAME;
~~~

Có thể xem chi tiết cột và kiểu dữ liệu:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
~~~

Đừng chỉ dựa vào file migration để kết luận schema đã đúng. SHOW CREATE TABLE và metadata phản ánh cấu trúc mà server thực sự đang dùng.

## 9. Chèn dữ liệu mẫu

Ta dùng ID tường minh để các ví dụ dễ đọc. Trong ứng dụng thông thường, AUTO_INCREMENT sẽ sinh ID và code lấy giá trị được tạo từ JDBC hoặc ORM.

Chèn khách hàng và sản phẩm:

~~~sql
INSERT INTO customers
    (customer_id, email, full_name, phone)
VALUES
    (1, 'lan@example.com', 'Nguyen Mai Lan', '0901000001'),
    (2, 'minh@example.com', 'Tran Quoc Minh', '0901000002');

INSERT INTO products
    (product_id, sku, product_name, unit_price, is_active)
VALUES
    (101, 'COFFEE-01', 'Ca phe hat 500g', 100000.00, 1),
    (102, 'MUG-01', 'Ly su 350ml', 150000.00, 1),
    (103, 'TEA-01', 'Tra xanh 200g', 75000.00, 1);
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT * FROM customers ORDER BY customer_id;
SELECT * FROM products ORDER BY product_id;
~~~

### 9.1. Tạo đơn hàng và các dòng hàng trong một transaction

Giả sử khách hàng 1 mua:

- Hai gói cà phê, đơn giá 100.000 mỗi gói.
- Một ly sứ, đơn giá 150.000.
- Chiết khấu 10.000 trên dòng ly sứ.
- Phí vận chuyển 20.000.

Subtotal trước chiết khấu là 350.000. Tổng chiết khấu là 10.000. Tổng thanh toán là 350.000 - 10.000 + 20.000 = 360.000.

Ta tạo header trước, thêm các dòng hàng, tính tổng từ các dòng rồi cập nhật header trước khi commit:

~~~sql
START TRANSACTION;

INSERT INTO orders (
    order_number,
    customer_id,
    status,
    currency,
    subtotal,
    discount_amount,
    shipping_fee,
    total_amount
)
VALUES (
    'ORD-2026-0001',
    1,
    'PENDING',
    'VND',
    0.00,
    0.00,
    20000.00,
    20000.00
);

SET @new_order_id = LAST_INSERT_ID();

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price,
    discount_amount
)
VALUES
    (@new_order_id, 101, 2, 100000.00, 0.00),
    (@new_order_id, 102, 1, 150000.00, 10000.00);

SELECT
    COALESCE(SUM(quantity * unit_price), 0.00),
    COALESCE(SUM(discount_amount), 0.00)
INTO @subtotal, @discount
FROM order_items
WHERE order_id = @new_order_id;

UPDATE orders
SET subtotal = @subtotal,
    discount_amount = @discount,
    total_amount = @subtotal - @discount + shipping_fee
WHERE order_id = @new_order_id;

COMMIT;
~~~

Trong ví dụ, header được tạo với subtotal và discount bằng 0 để thỏa CHECK trong lúc tạo. Toàn bộ thao tác nằm trong một transaction; connection khác không nhìn thấy trạng thái chưa commit theo isolation mặc định của InnoDB.

Nếu bất kỳ bước nào thất bại, ứng dụng phải ROLLBACK thay vì COMMIT một đơn chưa hoàn chỉnh. Trong code Java/Spring, dùng transaction boundary rõ ràng, ví dụ một service method có @Transactional, và để exception làm transaction rollback theo chính sách đã định.

Lưu ý: SQL client có thể tiếp tục thực thi các câu lệnh sau lỗi tùy chế độ. Khi chạy thủ công, nếu một statement trong transaction thất bại, hãy kiểm tra trạng thái và chủ động ROLLBACK trước khi chạy lại toàn bộ ví dụ.

### 9.2. Không dùng giá sản phẩm hiện tại để tính lại đơn cũ

Giá trong order_items đã được chụp tại thời điểm mua. Nếu products.unit_price thay đổi, order_items.unit_price vẫn giữ nguyên. Đây là lý do dữ liệu đơn hàng cần lưu snapshot của giá giao dịch.

## 10. Truy vấn đơn hàng bằng JOIN

Lấy chi tiết một đơn:

~~~sql
SELECT
    o.order_number,
    o.status,
    o.ordered_at,
    c.full_name,
    c.email,
    p.sku,
    p.product_name,
    oi.quantity,
    oi.unit_price,
    oi.discount_amount,
    oi.line_total
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
WHERE o.order_number = 'ORD-2026-0001'
ORDER BY oi.order_item_id;
~~~

Đây là truy vấn đọc theo quan hệ:

- orders xác định header.
- customers cung cấp thông tin khách hàng.
- order_items cung cấp dòng hàng.
- products cung cấp SKU và tên sản phẩm.

Với đơn hàng chưa có dòng hàng, INNER JOIN sẽ không trả header. Nếu báo cáo cần hiển thị cả đơn chưa có dòng, dùng LEFT JOIN từ orders sang order_items.

### 10.1. Báo cáo tổng tiền theo đơn

~~~sql
SELECT
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount,
    COALESCE(SUM(oi.line_total), 0.00) AS item_net_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount
ORDER BY o.ordered_at DESC;
~~~

Trong mô hình này, item_net_total là tổng các dòng sau chiết khấu. Với đơn ví dụ, kết quả là 340.000; cộng phí vận chuyển 20.000 thành total_amount 360.000.

### 10.2. Tìm đơn có tổng tiền header lệch với dòng hàng

Ta có thể dùng truy vấn đối soát:

~~~sql
SELECT
    o.order_id,
    o.order_number,
    o.subtotal,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0.00)
        AS calculated_subtotal,
    o.discount_amount,
    COALESCE(SUM(oi.discount_amount), 0.00)
        AS calculated_discount,
    o.total_amount,
    COALESCE(SUM(oi.line_total), 0.00) + o.shipping_fee
        AS calculated_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount
HAVING
    o.subtotal <> calculated_subtotal
    OR o.discount_amount <> calculated_discount
    OR o.total_amount <> calculated_total;
~~~

Nếu không có hàng nào, các tổng header đang khớp với dòng hàng theo mô hình bài thực hành. Truy vấn này hữu ích cho job đối soát định kỳ.

Trong hệ thống thực tế có thể có chiết khấu cấp đơn, thuế, voucher, phí đóng gói hoặc làm tròn. Khi đó cần mở rộng công thức và mô hình snapshot tương ứng; không ép mọi nghiệp vụ vào một phép tính đơn giản.

## 11. Kiểm thử FOREIGN KEY

Foreign key phải ngăn tham chiếu tới hàng cha không tồn tại.

Thử thêm đơn hàng với customer_id không có:

~~~sql
INSERT INTO orders (
    order_number,
    customer_id,
    status,
    currency
)
VALUES (
    'ORD-INVALID-CUSTOMER',
    999999,
    'PENDING',
    'VND'
);
~~~

Kỳ vọng: MySQL từ chối do vi phạm fk_orders_customer.

Thử thêm dòng hàng với product_id không tồn tại:

~~~sql
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES (
    (SELECT order_id FROM orders
     WHERE order_number = 'ORD-2026-0001'),
    999999,
    1,
    10000.00
);
~~~

Kỳ vọng: MySQL từ chối do vi phạm fk_order_items_product. Subquery lấy order_id từ số đơn mẫu để ví dụ không phụ thuộc vào giá trị AUTO_INCREMENT cụ thể.

### 11.1. Kiểm thử UNIQUE

Thử chèn email đã tồn tại:

~~~sql
INSERT INTO customers (email, full_name)
VALUES ('lan@example.com', 'Lan Duplicate');
~~~

Kỳ vọng: MySQL trả lỗi duplicate key cho uq_customers_email. Tương tự, SKU và order_number cũng phải duy nhất theo các unique key đã khai báo.

Thử xóa khách hàng đã có đơn hàng:

~~~sql
DELETE FROM customers
WHERE customer_id = 1;
~~~

Kỳ vọng: bị từ chối do ON DELETE RESTRICT.

Thử xóa sản phẩm đã có dòng hàng:

~~~sql
DELETE FROM products
WHERE product_id = 101;
~~~

Kỳ vọng: bị từ chối do ON DELETE RESTRICT.

Các câu lệnh kiểm thử lỗi nên chạy riêng, không đặt vào cùng script seed tự động nếu công cụ dừng toàn bộ script khi gặp lỗi.

## 12. Kiểm thử CHECK constraint

Với MySQL 8.0.16 trở lên, thử chèn giá âm:

~~~sql
INSERT INTO products (
    sku,
    product_name,
    unit_price,
    is_active
)
VALUES (
    'BAD-PRICE',
    'San pham gia am',
    -1000.00,
    1
);
~~~

Kỳ vọng: bị từ chối bởi chk_products_unit_price.

Thử số lượng bằng 0:

~~~sql
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES (
    (SELECT order_id FROM orders
     WHERE order_number = 'ORD-2026-0001'),
    103,
    0,
    75000.00
);
~~~

Kỳ vọng: bị từ chối bởi chk_order_items_quantity. Subquery lấy order_id từ đơn mẫu đã tạo.

Thử trạng thái không hợp lệ:

~~~sql
UPDATE orders
SET status = 'UNKNOWN'
WHERE order_number = 'ORD-2026-0001';
~~~

Kỳ vọng: bị từ chối bởi chk_orders_status.

Thử tổng tiền không đúng công thức:

~~~sql
UPDATE orders
SET total_amount = 1.00
WHERE order_number = 'ORD-2026-0001';
~~~

Kỳ vọng: bị từ chối bởi chk_orders_amounts.

Nếu các câu lệnh trên lại thành công, hãy kiểm tra phiên bản MySQL. MySQL trước 8.0.16 không thực thi CHECK constraint; một số hệ quản trị tương thích MySQL cũng có quy tắc riêng. Đừng kết luận CHECK hoạt động chỉ vì SHOW CREATE TABLE hiển thị biểu thức.

## 13. Kiểm tra tính toàn vẹn bằng truy vấn

### 13.1. Tìm dòng hàng không có đơn hàng

Foreign key phải ngăn tình huống này, nhưng truy vấn kiểm tra hữu ích sau migration hoặc khi audit dữ liệu:

~~~sql
SELECT oi.*
FROM order_items AS oi
LEFT JOIN orders AS o
    ON o.order_id = oi.order_id
WHERE o.order_id IS NULL;
~~~

### 13.2. Tìm dòng hàng không có sản phẩm

~~~sql
SELECT oi.*
FROM order_items AS oi
LEFT JOIN products AS p
    ON p.product_id = oi.product_id
WHERE p.product_id IS NULL;
~~~

### 13.3. Kiểm tra trạng thái và giá trị bất thường

~~~sql
SELECT order_id, order_number, status, total_amount
FROM orders
WHERE status NOT IN (
    'PENDING',
    'CONFIRMED',
    'PAID',
    'CANCELLED',
    'FULFILLED'
)
OR total_amount < 0.00;
~~~

Các truy vấn này là kiểm tra bổ sung. Khi constraint được thực thi và không bị vô hiệu hóa, chúng thường không trả kết quả. Tuy nhiên, dữ liệu import, phiên bản cũ hoặc thay đổi schema có thể khiến việc kiểm tra độc lập vẫn cần thiết.

## 14. Index và cách kiểm tra truy vấn

Các index trong schema được chọn theo quan hệ và truy vấn dự kiến:

| Index | Mục đích |
|---|---|
| PRIMARY KEY trên mỗi bảng | Định danh và tra cứu hàng |
| UNIQUE customers.email | Ngăn email trùng và tra cứu khách bằng email |
| UNIQUE products.sku | Ngăn SKU trùng và tra cứu sản phẩm |
| UNIQUE orders.order_number | Ngăn số đơn trùng và tra cứu đơn |
| idx_orders_customer_ordered_at | Lấy đơn theo khách và thời điểm |
| UNIQUE order_items(order_id, product_id) | Ngăn sản phẩm trùng trong một đơn, hỗ trợ tìm dòng theo đơn |
| idx_order_items_product_id | Tìm đơn có chứa một sản phẩm và hỗ trợ FK |

Dùng EXPLAIN để xem kế hoạch truy vấn:

~~~sql
EXPLAIN
SELECT order_id, order_number, ordered_at
FROM orders
WHERE customer_id = 1
ORDER BY ordered_at DESC;
~~~

Kiểm tra:

- key: index MySQL dự định sử dụng.
- type: phương thức truy cập.
- rows: số hàng ước lượng.
- Extra: thông tin bổ sung như Using filesort hoặc Using index.

Index không miễn phí. Mỗi index tăng dung lượng lưu trữ và chi phí INSERT/UPDATE/DELETE. Không thêm index cho mọi cột chỉ vì cột đó xuất hiện trong WHERE. Hãy dựa vào truy vấn thực tế, cardinality, selectivity và EXPLAIN ANALYZE trên phiên bản hỗ trợ.

## 15. Transaction và thứ tự ghi dữ liệu

Các thao tác tạo đơn cần có tính nguyên tử:

1. Tạo order header.
2. Tạo các order_items.
3. Tính subtotal và discount từ các dòng.
4. Cập nhật total_amount.
5. Commit.

Nếu một bước thất bại, rollback toàn bộ để không có đơn hàng dở dang.

Ví dụ Java/Spring ở mức khái niệm:

~~~java
@Service
public class OrderService {

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(
            Order.pendingFor(command.customerId(), command.shippingFee())
        );

        for (CreateOrderLine line : command.lines()) {
            Product product = productRepository.findById(line.productId())
                .orElseThrow(ProductNotFoundException::new);

            if (!product.isActive()) {
                throw new ProductNotAvailableException();
            }

            orderItemRepository.save(
                OrderItem.snapshot(
                    order,
                    product,
                    line.quantity(),
                    product.getUnitPrice(),
                    line.discountAmount()
                )
            );
        }

        orderTotalsService.recalculate(order.getId());
        return order.getId();
    }
}
~~~

Đây là phác thảo để thể hiện transaction boundary và giá snapshot. Code production cần xác định rõ cách tính tiền, làm tròn, concurrency khi thay đổi giá, kiểm tra tồn kho và thời điểm flush. Không gọi dịch vụ bên ngoài không có tính idempotent bên trong transaction database kéo dài.

### 15.1. Vì sao kiểm tra sản phẩm active chưa đủ?

Ứng dụng có thể đọc is_active = 1 rồi một transaction khác ngừng bán sản phẩm trước khi đơn commit. Nếu quy tắc yêu cầu không bán sản phẩm sau thời điểm bị ngừng bán, cần xác định chiến lược đồng bộ: khóa hàng sản phẩm bằng SELECT ... FOR UPDATE, kiểm tra trạng thái trong transaction và ghi đơn theo thứ tự nhất quán.

Tương tự, nếu có tồn kho, phải kiểm tra và cập nhật số lượng bằng thao tác nguyên tử hoặc khóa phù hợp để tránh bán vượt tồn. Schema hiện tại chưa có bảng inventory nên không thể đảm bảo quy tắc tồn kho.

## 16. Quy tắc ON DELETE và ON UPDATE

Các lựa chọn referential action cần phản ánh vòng đời dữ liệu.

| Quan hệ | ON DELETE | Lý do |
|---|---|---|
| customers → orders | RESTRICT | Không xóa khách có lịch sử đơn |
| orders → order_items | CASCADE | Dòng hàng thuộc đơn trong mô hình demo |
| products → order_items | RESTRICT | Giữ tham chiếu lịch sử sản phẩm |

ON UPDATE RESTRICT được dùng cho tất cả khóa. ID nội bộ nên ổn định và hiếm khi thay đổi. Nếu khóa cha thay đổi, cần migration có kiểm soát thay vì dựa vào cập nhật cascade trên một khóa định danh.

Không dùng ON DELETE CASCADE một cách mặc định cho mọi quan hệ. Xóa một customer có thể kéo theo hàng triệu đơn và dữ liệu thanh toán nếu cascade lan rộng; hành vi này có thể gây lock lâu, log lớn và mất lịch sử nghiệp vụ.

## 17. Mở rộng schema theo nhu cầu thực tế

Sau khi schema cốt lõi chạy đúng, có thể bổ sung:

- **order_addresses:** snapshot địa chỉ nhận hàng tại thời điểm đặt.
- **payments:** giao dịch thanh toán, provider reference, trạng thái và idempotency key.
- **order_status_history:** lịch sử thay đổi trạng thái.
- **inventory:** tồn kho theo sản phẩm/kho và reservation.
- **shipments:** đơn giao hàng, mã vận đơn và trạng thái.
- **taxes/promotions:** quy tắc thuế và khuyến mãi.
- **audit log:** người thao tác, thời điểm và nguồn thay đổi.

Mỗi bảng mới cần xác định primary key, foreign key, unique constraint, CHECK, index và chính sách lưu/xóa dữ liệu. Không thêm quan hệ chỉ vì có thể; thêm khi có quy tắc nghiệp vụ và truy vấn cụ thể.

### 17.1. Lịch sử giá và snapshot đơn hàng

Nếu cần biết giá sản phẩm đã thay đổi thế nào theo thời gian, tạo bảng product_price_history có effective_from/effective_to hoặc lưu các sự kiện thay đổi. Nhưng order_items vẫn cần lưu giá đã áp dụng cho giao dịch cụ thể. Lịch sử giá và giá snapshot phục vụ hai mục tiêu khác nhau.

### 17.2. Tiền tệ và làm tròn

DECIMAL(13,2) phù hợp ví dụ VND theo mô hình hai chữ số thập phân, nhưng VND trong nghiệp vụ thường được xử lý theo đơn vị đồng. Hãy quyết định precision/scale theo tiền tệ hỗ trợ. Nếu có nhiều currency, không giả định mọi currency đều có cùng số chữ số thập phân. Quy tắc rounding cần thống nhất ở ứng dụng và được kiểm thử với các giá trị biên.

## 18. Checklist hoàn thành schema

- [ ] Đã tạo database với charset utf8mb4.
- [ ] Tất cả bảng dùng InnoDB.
- [ ] Đã tạo customers và products trước các bảng tham chiếu.
- [ ] Mỗi bảng có PRIMARY KEY ổn định.
- [ ] Email, SKU và order number có UNIQUE phù hợp.
- [ ] Kiểu dữ liệu khóa ngoại khớp kiểu của khóa được tham chiếu.
- [ ] Đã khai báo foreign key với ON DELETE/ON UPDATE có chủ đích.
- [ ] Đã có index hỗ trợ truy vấn và foreign key.
- [ ] Giá và tổng tiền dùng DECIMAL.
- [ ] Số lượng có CHECK lớn hơn 0.
- [ ] Trạng thái có CHECK giới hạn giá trị.
- [ ] Tổng tiền header thỏa công thức cùng hàng.
- [ ] Đã xác minh MySQL version thực thi CHECK.
- [ ] Dữ liệu mẫu được ghi trong transaction.
- [ ] Đơn giá dòng hàng là snapshot tại thời điểm mua.
- [ ] Đã thử lỗi foreign key, unique và CHECK.
- [ ] Đã kiểm tra SHOW CREATE TABLE, SHOW INDEX và metadata.
- [ ] Đã chạy truy vấn JOIN, tổng hợp và đối soát.
- [ ] Đã xem EXPLAIN cho truy vấn quan trọng.
- [ ] Đã xác định quy trình rollback khi một bước tạo đơn thất bại.

## 19. Bài tập thực hành mở rộng

1. Thêm bảng order_addresses để lưu địa chỉ giao hàng snapshot. Chọn ON DELETE phù hợp và giải thích vì sao không nên chỉ tham chiếu địa chỉ hiện tại của khách hàng.
2. Thêm bảng payments với provider_reference duy nhất và CHECK cho amount lớn hơn 0.
3. Thêm order_status_history để lưu mọi lần chuyển trạng thái; xác định index cho truy vấn lịch sử theo order_id và thời gian.
4. Thêm cột tenant_id vào customers và orders, rồi thay unique email bằng unique (tenant_id, email).
5. Thay đổi mô hình để một sản phẩm có thể xuất hiện nhiều dòng trong một đơn. Chọn khóa duy nhất mới.
6. Viết truy vấn tìm top 10 sản phẩm theo tổng số lượng đã bán.
7. Viết truy vấn tính doanh thu theo ngày trong tháng.
8. Dùng EXPLAIN để so sánh truy vấn đơn hàng theo customer_id trước và sau khi thêm index phù hợp.
9. Tạo một bản ghi có product_id không tồn tại và ghi lại lỗi foreign key.
10. Thử chèn giá âm trên MySQL 8.0.16+ và so sánh với môi trường MySQL cũ không thực thi CHECK.
11. Mô phỏng hai transaction cùng tạo một order_number để quan sát unique constraint.
12. Thiết kế transaction tạo đơn có kiểm tra tồn kho và cập nhật inventory mà không bán vượt số lượng còn lại.

## 20. Tự kiểm tra

1. Vì sao order_items cần lưu unit_price thay vì luôn đọc giá từ products?
2. Vì sao foreign key customer_id nên tham chiếu PRIMARY KEY của customers?
3. Unique key (order_id, product_id) bảo đảm điều gì và giới hạn trường hợp nghiệp vụ nào?
4. Vì sao products dùng ON DELETE RESTRICT trong khi order_items dùng ON DELETE CASCADE với orders?
5. CHECK có thể kiểm tra tổng SUM của order_items để xác minh orders.total_amount không?
6. Vì sao tổng tiền phải được cập nhật trong cùng transaction với các dòng hàng?
7. Tại sao DECIMAL phù hợp hơn FLOAT cho tiền?
8. Vì sao MySQL trước 8.0.16 không thể dựa vào CHECK để bảo vệ dữ liệu?
9. Index nào hỗ trợ truy vấn đơn hàng theo khách hàng và thời gian?
10. Khi thêm tồn kho, cần xử lý concurrency thế nào để tránh bán vượt số lượng?

Sau bài thực hành, schema có thể bảo vệ các quy tắc cốt lõi ngay tại MySQL: định danh duy nhất, quan hệ cha-con hợp lệ, giá trị hàng không âm, số lượng dương và trạng thái đơn nằm trong tập cho phép. Transaction kết nối các bước tạo header, dòng hàng và tính tổng thành một đơn vị công việc. Khi mở rộng sang thanh toán, tồn kho và vận chuyển, hãy tiếp tục thiết kế constraint theo quy tắc nghiệp vụ và kiểm chứng bằng dữ liệu mẫu cùng các trường hợp cố ý vi phạm.
