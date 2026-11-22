# REPLACE và ảnh hưởng xóa/chèn đến khóa ngoại, trigger, định danh

Bài học thuộc chương **Thay đổi dữ liệu** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Lệnh `REPLACE` thường được gọi là thao tác “ghi đè nếu đã tồn tại”, nhưng cách MySQL thực hiện có thể gây ra nhiều tác động hơn một câu UPDATE.

Sau bài này, bạn có thể giải thích chính xác cách REPLACE xử lý xung đột khóa chính và khóa UNIQUE, hiểu vì sao một hàng cũ bị xóa rồi hàng mới được chèn, dự đoán ảnh hưởng đến giá trị mặc định, AUTO_INCREMENT, khóa ngoại và trigger, đồng thời chọn REPLACE hay một phương án cập nhật an toàn hơn.

## 1. REPLACE là gì?

`REPLACE` là phần mở rộng của MySQL để chèn một hàng mới. Nếu hàng mới xung đột với khóa PRIMARY KEY hoặc một unique index, MySQL xóa hàng cũ gây xung đột rồi chèn hàng mới.

Về ý nghĩa, có thể hình dung:

~~~sql
-- Mô tả khái niệm, không phải cú pháp thay thế trực tiếp
DELETE FROM target_table
WHERE primary_or_unique_key_conflicts;

INSERT INTO target_table (...)
VALUES (...);
~~~

Điểm quan trọng: **REPLACE không cập nhật hàng cũ tại chỗ. Nó thực hiện xóa và chèn.**

Nếu không có xung đột khóa duy nhất, REPLACE hoạt động như INSERT thông thường.

Chỉ PRIMARY KEY và unique index tạo điều kiện xung đột cho REPLACE; một index thông thường không UNIQUE không làm hàng cũ bị thay thế. Ngay cả khi các giá trị mới giống hệt hàng cũ, nhánh xung đột vẫn có ngữ nghĩa xóa rồi chèn, không tự biến thành UPDATE không thay đổi.

Ví dụ:

~~~sql
CREATE TABLE products (
    product_id INT NOT NULL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO products (product_id, sku, product_name)
VALUES (1, 'KB-001', 'Keyboard');

REPLACE INTO products (product_id, sku, product_name)
VALUES (1, 'KB-001', 'Keyboard Pro');
~~~

Sau câu REPLACE, hàng có `product_id = 1` chứa tên mới. Nhưng về mặt xử lý, hàng cũ đã bị xóa và một hàng mới được chèn.

Sự khác biệt này ảnh hưởng đến:

- Khóa ngoại tham chiếu đến hàng cũ.
- Trigger DELETE và INSERT.
- Cột AUTO_INCREMENT.
- Cột không được nêu trong danh sách INSERT.
- Giá trị mặc định và biểu thức DEFAULT.
- Số hàng bị ảnh hưởng và logic ứng dụng.

## 2. Cú pháp REPLACE

MySQL hỗ trợ một số dạng chính.

### Dạng VALUES

~~~sql
REPLACE INTO table_name (column1, column2, column3)
VALUES (value1, value2, value3);
~~~

Có thể chèn nhiều hàng trong một câu lệnh:

~~~sql
REPLACE INTO products (product_id, sku, product_name)
VALUES
    (1, 'KB-001', 'Keyboard Pro'),
    (2, 'MS-002', 'Wireless Mouse');
~~~

Mỗi hàng được xử lý theo quy tắc REPLACE. Một hàng có thể được chèn mới, hàng khác có thể thay thế hàng cũ do xung đột khóa.

### Dạng SET

~~~sql
REPLACE INTO products
SET
    product_id = 1,
    sku = 'KB-001',
    product_name = 'Keyboard Pro';
~~~

Dạng SET thuận tiện khi muốn gán từng cột theo tên.

### Dạng SELECT

Có thể chèn dữ liệu từ truy vấn khác:

~~~sql
REPLACE INTO product_snapshot
    (product_id, sku, product_name)
SELECT
    product_id,
    sku,
    product_name
FROM products_staging;
~~~

Mỗi hàng của SELECT được xử lý như một hàng đầu vào của REPLACE. Nếu dữ liệu nguồn xung đột với khóa duy nhất trong bảng đích, hàng đích xung đột có thể bị xóa trước khi chèn hàng mới.

REPLACE không có mệnh đề WHERE để chọn hàng đích cần cập nhật. Việc xác định xung đột dựa trên PRIMARY KEY và các unique index.

## 3. MySQL xác định hàng nào bị xóa?

Một hàng đầu vào của REPLACE có thể xung đột với:

- PRIMARY KEY.
- Một unique index.
- Nhiều unique index cùng lúc.

Nếu không có xung đột, MySQL chèn hàng mới.

Nếu có một hàng cũ xung đột, MySQL xóa hàng đó rồi chèn hàng mới.

Nếu hàng mới xung đột với nhiều hàng cũ khác nhau thông qua các unique index khác nhau, MySQL có thể xóa **tất cả các hàng cũ xung đột** rồi chèn một hàng mới.

Đây là tình huống rất nguy hiểm khi bảng có nhiều khóa UNIQUE độc lập.

### Xung đột với khóa chính

~~~sql
CREATE TABLE demo_replace (
    id INT NOT NULL PRIMARY KEY,
    value_text VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO demo_replace (id, value_text)
VALUES (1, 'old value');

REPLACE INTO demo_replace (id, value_text)
VALUES (1, 'new value');

SELECT * FROM demo_replace;
~~~

Khóa chính `id = 1` đã tồn tại. Hàng cũ bị thay thế bằng hàng mới.

### Xung đột với unique index

~~~sql
CREATE TABLE account_demo (
    account_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account_demo
    (account_id, email, display_name)
VALUES
    (10, 'an@example.test', 'An');

REPLACE INTO account_demo
    (account_id, email, display_name)
VALUES
    (20, 'an@example.test', 'An Nguyen');
~~~

Không có xung đột PRIMARY KEY vì 20 chưa tồn tại. Nhưng email đã được dùng bởi hàng có account_id 10. MySQL xóa hàng đó rồi chèn hàng mới với account_id 20.

Do đó, REPLACE có thể làm thay đổi định danh chính của một thực thể chỉ vì một unique key phụ bị trùng.

### Một hàng mới xung đột với hai hàng cũ

Đây là ví dụ cần đặc biệt chú ý:

~~~sql
CREATE TABLE account_keys (
    account_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (1, 'an@example.test', 'an_login', 'An'),
    (2, 'binh@example.test', 'binh_login', 'Binh');

REPLACE INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (3, 'an@example.test', 'binh_login', 'New account');
~~~

Hàng mới có:

- Email trùng hàng 1.
- Login name trùng hàng 2.
- Account ID 3 chưa tồn tại.

MySQL có thể xóa cả hàng 1 và hàng 2, sau đó chèn hàng 3. Kết quả chỉ còn một hàng mới trong bảng.

Không nên xem các unique index là những “điều kiện tìm hàng để cập nhật”. Chúng là các ràng buộc duy nhất; REPLACE xử lý xung đột bằng cách xóa các hàng cũ.

## 4. Cột không được chỉ định sẽ nhận giá trị mặc định

Vì REPLACE chèn một hàng mới, các cột không có trong danh sách cột sẽ nhận giá trị DEFAULT, NULL nếu cho phép, hoặc giá trị mặc định ngầm theo quy tắc SQL mode và định nghĩa cột.

MySQL không giữ nguyên giá trị cũ của những cột bị bỏ qua.

Ví dụ:

~~~sql
CREATE TABLE inventory (
    product_id INT NOT NULL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    note VARCHAR(200) NULL DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO inventory
    (product_id, sku, product_name, stock_quantity, note)
VALUES
    (1, 'KB-001', 'Keyboard', 25, 'Imported in January');

REPLACE INTO inventory
    (product_id, sku, product_name)
VALUES
    (1, 'KB-001', 'Keyboard Pro');

SELECT * FROM inventory;
~~~

Hàng sau REPLACE có:

| Cột | Giá trị sau REPLACE |
|---|---|
| product_id | 1 |
| sku | KB-001 |
| product_name | Keyboard Pro |
| stock_quantity | 0 |
| note | NULL |

Số lượng tồn kho 25 và ghi chú cũ đã mất. Chúng được thay bằng DEFAULT vì không được truyền trong hàng mới.

Đây là một trong những nguyên nhân phổ biến khiến REPLACE làm mất dữ liệu dù ứng dụng chỉ muốn thay tên hoặc đồng bộ một vài cột.

Nếu cần giữ các cột cũ, hãy dùng UPDATE hoặc `INSERT ... ON DUPLICATE KEY UPDATE` với danh sách cột cập nhật rõ ràng.

## 5. Ảnh hưởng đến AUTO_INCREMENT và định danh

REPLACE có thể tạo một giá trị AUTO_INCREMENT mới nếu hàng được chèn không cung cấp giá trị cho cột này.

Ví dụ:

~~~sql
CREATE TABLE customer_identity (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(200) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An');

SELECT * FROM customer_identity;
~~~

Giả sử hàng được cấp `customer_id = 1`.

Tiếp theo:

~~~sql
REPLACE INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An Nguyen');

SELECT * FROM customer_identity;
~~~

Email xung đột với hàng cũ. Hàng cũ bị xóa và hàng mới được chèn. Vì câu REPLACE không cung cấp customer_id, MySQL cấp một giá trị AUTO_INCREMENT mới, thường là 2.

Định danh đã thay đổi dù email vẫn giống nhau.

Nếu REPLACE cung cấp rõ giá trị khóa chính hiện tại, ví dụ:

~~~sql
REPLACE INTO customer_identity
    (customer_id, email, full_name)
VALUES
    (1, 'an@example.test', 'An Updated');
~~~

thì hàng mới dùng giá trị customer_id được chỉ định. Tuy vậy, thao tác vẫn là xóa/chèn và vẫn có các tác động của DELETE.

### Hệ quả đối với hệ thống tham chiếu ID

Nếu các bảng khác lưu `customer_id`, việc ID thay đổi có thể:

- Làm mất liên kết nếu khóa ngoại không được thiết kế phù hợp.
- Kích hoạt ON DELETE CASCADE và xóa các hàng con.
- Bị từ chối bởi ON DELETE RESTRICT.
- Làm thay đổi ID được trả về cho ứng dụng hoặc hệ thống đồng bộ.
- Làm sai lịch sử audit hoặc tham chiếu từ hệ thống bên ngoài không được bảo vệ bằng khóa ngoại.

Với thực thể có định danh ổn định, không dùng REPLACE chỉ để cập nhật thuộc tính.

## 6. Khóa ngoại: REPLACE có thể xóa dữ liệu ở bảng con

Vì REPLACE xóa hàng cha xung đột trước khi chèn hàng mới, hành động ON DELETE của khóa ngoại được áp dụng như với một thao tác DELETE.

Ba hành vi quan trọng:

| ON DELETE | Khi REPLACE xóa hàng cha |
|---|---|
| CASCADE | Hàng con tham chiếu có thể bị xóa theo |
| SET NULL | Cột khóa ngoại ở hàng con được đặt NULL nếu cấu hình cho phép |
| RESTRICT / NO ACTION | Việc xóa hàng cha bị từ chối nếu còn hàng con tham chiếu |

### Ví dụ ON DELETE CASCADE

~~~sql
CREATE TABLE customers (
    customer_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    order_total DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An');

INSERT INTO orders (order_id, customer_id, order_total)
VALUES
    (1001, 1, 500.00),
    (1002, 1, 250.00);
~~~

Thực hiện REPLACE:

~~~sql
REPLACE INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Nguyen');
~~~

MySQL xóa hàng customer cũ. Do khóa ngoại dùng ON DELETE CASCADE, các đơn hàng tham chiếu customer_id 1 bị xóa theo. Sau đó hàng customer mới được chèn lại.

Kiểm tra:

~~~sql
SELECT * FROM customers;
SELECT * FROM orders;
~~~

Bảng customers có hàng mới, nhưng các đơn hàng 1001 và 1002 đã bị xóa.

Đây là rủi ro nghiêm trọng: nhìn vào bảng cha có thể tưởng rằng khách hàng chỉ được cập nhật tên, trong khi dữ liệu con đã bị xóa.

### Ví dụ ON DELETE RESTRICT

Nếu khóa ngoại dùng RESTRICT:

~~~sql
CREATE TABLE departments (
    department_id INT NOT NULL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE employees (
    employee_id INT NOT NULL PRIMARY KEY,
    department_id INT NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES departments (department_id)
        ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

Nếu một phòng ban đang được nhân viên tham chiếu, REPLACE phòng ban với cùng khóa có thể thất bại vì bước xóa hàng cũ bị khóa ngoại từ chối.

Không thể giả định rằng chèn lại cùng khóa chính sẽ làm cho khóa ngoại “không nhận ra” việc xóa. Ràng buộc được kiểm tra trong quá trình thực thi, và hành vi DELETE xảy ra trước INSERT.

### SET NULL

Với `ON DELETE SET NULL`, các hàng con có thể được giữ lại nhưng cột khóa ngoại được đặt NULL. Cột đó phải cho phép NULL. Nếu không, thao tác xóa có thể thất bại.

### Khóa ngoại nhiều tầng

Nếu hàng cha có nhiều tầng dữ liệu con và các khóa ngoại dùng CASCADE, một REPLACE ở bảng cha có thể dẫn đến chuỗi xóa ở nhiều bảng. Hãy kiểm tra toàn bộ đồ thị khóa ngoại trước khi chạy trên dữ liệu thật.

## 7. Trigger DELETE và INSERT đều có thể chạy

REPLACE được xử lý như một thao tác xóa hàng cũ và chèn hàng mới. Vì vậy, các trigger DELETE và INSERT có thể được kích hoạt.

- Trigger DELETE xử lý hàng cũ bị xóa.
- Trigger INSERT xử lý hàng mới được chèn.
- Trigger UPDATE không được kích hoạt chỉ vì REPLACE thay thế một hàng.

Điều này ảnh hưởng đến:

- Bảng audit.
- Lịch sử thay đổi.
- Bảng thống kê được cập nhật bằng trigger.
- Hệ thống ghi sự kiện.
- Các thủ tục kiểm tra hoặc tạo dữ liệu phụ.

Ví dụ bảng audit:

Đoạn `DELIMITER` dưới đây là lệnh của client dòng lệnh `mysql`, dùng để thay dấu kết thúc câu lệnh khi định nghĩa trigger có nhiều câu SQL. Nếu dùng một công cụ quản trị khác, hãy dùng cơ chế tạo trigger tương ứng của công cụ đó.

~~~sql
CREATE TABLE customer_events (
    event_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(20) NOT NULL,
    customer_id INT NOT NULL,
    email VARCHAR(200) NOT NULL,
    event_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

DELIMITER //

CREATE TRIGGER customers_after_delete
AFTER DELETE ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_events
        (event_type, customer_id, email)
    VALUES
        ('DELETE', OLD.customer_id, OLD.email);
END//

CREATE TRIGGER customers_after_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_events
        (event_type, customer_id, email)
    VALUES
        ('INSERT', NEW.customer_id, NEW.email);
END//

DELIMITER ;
~~~

Khi REPLACE một khách hàng đã tồn tại, trigger DELETE và INSERT có thể ghi nhận hai sự kiện tương ứng.

Nếu dùng trigger UPDATE để ghi lịch sử, trigger đó sẽ không thay thế được hai nhánh DELETE/INSERT của REPLACE. Hãy thiết kế audit theo đúng loại thao tác thực tế.

**Lưu ý về cascade:** InnoDB thực hiện hành động khóa ngoại theo cơ chế riêng; các thao tác cascade không kích hoạt trigger trên bảng con. Không nên dựa vào trigger của bảng con để ghi nhận đầy đủ mọi hàng bị xóa do ON DELETE CASCADE. Nếu cần audit đầy đủ, hãy thiết kế cơ chế ghi nhận ở tầng ứng dụng hoặc quy trình dữ liệu phù hợp.

## 8. Số hàng bị ảnh hưởng không giống UPDATE

REPLACE có thể báo số hàng bị ảnh hưởng khác nhau tùy thao tác:

- Nếu không có hàng cũ xung đột và một hàng mới được chèn, số hàng bị ảnh hưởng thường là 1.
- Nếu một hàng cũ bị xóa và một hàng mới được chèn, số hàng bị ảnh hưởng thường là 2.
- Nếu nhiều hàng cũ bị xóa do xung đột với nhiều unique key, số hàng bị ảnh hưởng có thể lớn hơn.

Đừng diễn giải số hàng bị ảnh hưởng như số thực thể nghiệp vụ được “cập nhật”. REPLACE có thể xóa nhiều hàng cũ và chỉ chèn một hàng mới.

Nếu ứng dụng cần biết chính xác thực thể nào bị tác động, hãy kiểm tra bằng khóa duy nhất và audit rõ ràng thay vì chỉ dựa vào affected rows.

### LAST_INSERT_ID và AUTO_INCREMENT

Nếu REPLACE chèn hàng với giá trị AUTO_INCREMENT được cấp mới, connector có thể nhận giá trị sinh ra theo cơ chế thông thường của MySQL. Hãy đọc giá trị do driver trả về hoặc `LAST_INSERT_ID()` ngay trong cùng connection khi cần.

Không giả định rằng giá trị ID cũ được giữ lại khi REPLACE chỉ truyền unique key phụ như email hoặc SKU.

## 9. REPLACE trong transaction và storage engine

Với bảng InnoDB, các thao tác xóa và chèn thuộc cùng câu lệnh REPLACE. Nếu câu lệnh thất bại do constraint hoặc lỗi khác, InnoDB có thể rollback thay đổi của câu lệnh theo tính nguyên tử của statement.

Ví dụ:

~~~sql
START TRANSACTION;

REPLACE INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Updated');

-- Kiểm tra các bảng liên quan trong cùng transaction.

ROLLBACK;
~~~

ROLLBACK hoàn tác thay đổi của transaction InnoDB chưa COMMIT, bao gồm cả thay đổi do REPLACE.

Tuy nhiên, không nên dựa vào điều này cho bảng dùng storage engine không hỗ trợ transaction. Với engine không transactional, lỗi trong câu lệnh nhiều hàng có thể để lại một phần thay đổi tùy loại lỗi và thời điểm lỗi.

### Auto-increment không nhất thiết quay lại giá trị cũ

Ngay cả khi transaction rollback, giá trị AUTO_INCREMENT đã cấp có thể không được tái sử dụng. Khoảng trống trong dãy ID là hành vi bình thường; không dùng ID làm bộ đếm liên tục không có khoảng trống.

### Quyền cần thiết

REPLACE cần quyền INSERT và DELETE trên bảng đích. Nếu thiếu một trong hai quyền, câu lệnh có thể bị từ chối.

Vì thao tác có thể xóa dữ liệu, quyền DELETE là điểm cần kiểm tra trong thiết kế tài khoản ứng dụng. Một tài khoản chỉ được phép INSERT có thể không đủ quyền chạy REPLACE.

## 10. So sánh REPLACE với UPDATE và INSERT ... ON DUPLICATE KEY UPDATE

Ba lựa chọn này có ngữ nghĩa khác nhau.

| Tiêu chí | REPLACE | UPDATE | INSERT ... ON DUPLICATE KEY UPDATE |
|---|---|---|---|
| Không có hàng trùng | Chèn hàng mới | Không cập nhật hàng nào | Chèn hàng mới |
| Có hàng trùng | Xóa hàng xung đột rồi chèn hàng mới | Sửa hàng được WHERE chọn | Cập nhật hàng xung đột |
| Giữ các cột không nêu | Không; dùng DEFAULT/NULL theo định nghĩa | Có, trừ cột được SET | Có, trừ cột được cập nhật |
| Giữ định danh hiện có | Không bảo đảm, nhất là khi xung đột unique phụ và AUTO_INCREMENT | Có nếu không sửa khóa | Thường giữ khóa của hàng được cập nhật |
| Tác động FK ON DELETE | Có thể kích hoạt | Không có thao tác xóa hàng | Không có thao tác xóa hàng |
| Trigger | DELETE và INSERT | UPDATE | INSERT/UPDATE theo nhánh thực thi |
| Phù hợp | Chủ đích thay toàn bộ hàng theo semantics xóa/chèn | Sửa một hàng đã biết | Chèn mới hoặc cập nhật các cột xác định khi trùng |

### Dùng UPDATE khi hàng đã tồn tại

Nếu biết khóa chính:

~~~sql
UPDATE inventory
SET
    product_name = 'Keyboard Pro'
WHERE product_id = 1;
~~~

Các cột stock_quantity và note vẫn giữ nguyên.

### Dùng INSERT ... ON DUPLICATE KEY UPDATE

Nếu muốn chèn khi chưa có, cập nhật một số cột khi trùng:

~~~sql
INSERT INTO inventory
    (product_id, sku, product_name, stock_quantity, note)
VALUES
    (1, 'KB-001', 'Keyboard Pro', 25, 'Imported in February')
ON DUPLICATE KEY UPDATE
    product_name = 'Keyboard Pro',
    stock_quantity = 25,
    note = 'Imported in February';
~~~

Nhánh duplicate thực hiện UPDATE. Hàng cũ không bị xóa, vì vậy không kích hoạt hành vi ON DELETE của khóa ngoại chỉ vì câu lệnh này.

Chỉ nêu những cột thực sự cần cập nhật. Nếu bỏ `stock_quantity` khỏi phần UPDATE, giá trị tồn kho cũ được giữ lại.

Nếu bảng có nhiều unique index, hãy kiểm tra trường hợp một hàng đầu vào xung đột với nhiều hàng khác nhau. ON DUPLICATE KEY UPDATE cũng có thể gặp lỗi unique key nếu cập nhật hàng xung đột tạo ra một vi phạm khác. Thiết kế unique key cần bảo đảm các xung đột tương ứng với cùng một thực thể nghiệp vụ.

### Khi nào REPLACE thực sự phù hợp?

REPLACE có thể phù hợp nếu:

- Hàng đích là một bản ghi độc lập, không có dữ liệu con cần giữ.
- Mọi cột của hàng mới được cung cấp hoặc DEFAULT đã được xác định rõ.
- Việc xóa rồi chèn là chủ đích nghiệp vụ.
- Trigger DELETE/INSERT và audit đã được thiết kế đúng.
- Không có tác động khóa ngoại ngoài ý muốn.
- Việc thay đổi AUTO_INCREMENT hoặc định danh đã được chấp nhận.

Ví dụ, một bảng staging/cache không có tham chiếu phụ thuộc có thể phù hợp hơn một bảng khách hàng lõi được nhiều bảng khác tham chiếu.

## 11. Quy trình an toàn trước khi chạy REPLACE

Trước khi chạy REPLACE trên production:

1. **Kiểm tra khóa:** liệt kê PRIMARY KEY và tất cả unique index có thể xung đột.
2. **Tìm hàng hiện có:** dùng SELECT để xem hàng nào đang sở hữu các khóa sẽ được chèn.
3. **Kiểm tra nhiều xung đột:** xác định liệu các unique key có thể trỏ tới những hàng cũ khác nhau không.
4. **Kiểm tra cột bị bỏ qua:** xem các cột đó sẽ nhận DEFAULT, NULL hay giá trị ngầm nào.
5. **Kiểm tra AUTO_INCREMENT:** xác định ID cũ có được giữ hay có thể sinh ID mới.
6. **Kiểm tra khóa ngoại:** xem hành vi CASCADE, SET NULL, RESTRICT và các quan hệ nhiều tầng.
7. **Kiểm tra trigger:** xem trigger DELETE/INSERT đang làm gì và audit có phản ánh đúng không.
8. **Kiểm tra quyền:** tài khoản thực thi cần INSERT và DELETE.
9. **Chạy thử trong transaction hoặc môi trường staging:** xác minh dữ liệu trước khi COMMIT.
10. **Đối chiếu sau thao tác:** kiểm tra bảng đích, bảng con, audit và các tham chiếu bên ngoài.

Một mẫu kiểm tra khóa trước khi thay:

~~~sql
SELECT *
FROM inventory
WHERE product_id = 1
   OR sku = 'KB-001';
~~~

Nếu hai điều kiện tìm ra các hàng khác nhau, dừng lại để xác định dữ liệu nào là chủ sở hữu hợp lệ. Không chạy REPLACE chỉ vì câu lệnh có thể “tự xử lý” xung đột.

## 12. Bài thực hành: quan sát các tác động của REPLACE

Thực hiện trong database lab riêng.

### Bước 1: tạo database và bảng sản phẩm

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_replace_lab;
USE mysql_replace_lab;

CREATE TABLE inventory (
    product_id INT NOT NULL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    note VARCHAR(200) NULL DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO inventory
    (product_id, sku, product_name, stock_quantity, note)
VALUES
    (1, 'KB-001', 'Keyboard', 25, 'Imported in January');
~~~

### Bước 2: quan sát cột bị đặt lại DEFAULT

~~~sql
REPLACE INTO inventory
    (product_id, sku, product_name)
VALUES
    (1, 'KB-001', 'Keyboard Pro');

SELECT * FROM inventory;
~~~

Ghi lại stock_quantity và note. Giải thích vì sao chúng không còn là 25 và ghi chú cũ.

### Bước 3: quan sát xung đột unique key phụ làm thay đổi ID

~~~sql
CREATE TABLE customer_identity (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(200) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An');

SELECT * FROM customer_identity;

REPLACE INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An Nguyen');

SELECT * FROM customer_identity;
~~~

So sánh customer_id trước và sau REPLACE. Giải thích vì sao email giữ nguyên nhưng định danh có thể thay đổi.

### Bước 4: quan sát xóa nhiều hàng do nhiều unique key

~~~sql
CREATE TABLE account_keys (
    account_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (1, 'an@example.test', 'an_login', 'An'),
    (2, 'binh@example.test', 'binh_login', 'Binh');

SELECT * FROM account_keys ORDER BY account_id;

REPLACE INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (3, 'an@example.test', 'binh_login', 'New account');

SELECT * FROM account_keys ORDER BY account_id;
~~~

Quan sát vì sao hai hàng cũ có thể biến mất dù câu REPLACE chỉ chèn một hàng.

### Bước 5: quan sát khóa ngoại CASCADE

~~~sql
CREATE TABLE customers (
    customer_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    order_total DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An');

INSERT INTO orders (order_id, customer_id, order_total)
VALUES
    (1001, 1, 500.00),
    (1002, 1, 250.00);

REPLACE INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Updated');

SELECT * FROM customers;
SELECT * FROM orders;
~~~

Xác nhận hàng khách hàng mới còn tồn tại nhưng các đơn hàng cũ đã bị xóa do CASCADE.

### Bước 6: thử phương án cập nhật

Ở bước 5, các đơn hàng đã bị xóa bởi CASCADE. Chèn lại dữ liệu con để có thể so sánh rõ hành vi của UPDATE và ON DUPLICATE KEY UPDATE:

~~~sql
INSERT INTO orders (order_id, customer_id, order_total)
VALUES
    (1001, 1, 500.00),
    (1002, 1, 250.00);

UPDATE customers
SET display_name = 'An Updated Safely'
WHERE customer_id = 1;

SELECT * FROM orders;
~~~

Và:

~~~sql
INSERT INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Updated Safely')
ON DUPLICATE KEY UPDATE
    display_name = 'An Updated Safely';

SELECT * FROM orders;
~~~

Kiểm tra bảng orders. Hai cách cập nhật không thực hiện DELETE hàng cha, vì vậy không kích hoạt ON DELETE CASCADE như REPLACE.

### Bước 7: dọn dẹp

~~~sql
DROP DATABASE mysql_replace_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh sẽ xóa toàn bộ bảng, trigger và dữ liệu thực hành trong database đó.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mất giá trị ở cột không được truyền | REPLACE chèn hàng mới và áp dụng DEFAULT/NULL | Truyền đầy đủ cột hoặc dùng UPDATE/ON DUPLICATE KEY UPDATE |
| ID AUTO_INCREMENT thay đổi | Xung đột unique phụ và câu lệnh không truyền ID cũ | Dùng UPDATE hoặc ODKU nếu cần giữ định danh |
| Bảng con biến mất | REPLACE xóa hàng cha và ON DELETE CASCADE chạy | Kiểm tra FK trước; dùng UPDATE nếu chỉ sửa thuộc tính |
| REPLACE thất bại vì foreign key | Hàng con đang tham chiếu và FK dùng RESTRICT/NO ACTION | Dùng UPDATE hoặc xử lý quan hệ con theo nghiệp vụ |
| Audit ghi DELETE và INSERT thay vì UPDATE | REPLACE kích hoạt trigger theo hành vi xóa/chèn | Thiết kế trigger và audit theo đúng semantics |
| Nhiều tài khoản biến mất sau một REPLACE | Các unique index khác nhau xung đột với các hàng khác nhau | Kiểm tra tất cả unique key trước khi thực thi |
| Số hàng affected lớn hơn 1 | Có hàng cũ bị xóa rồi hàng mới được chèn | Không coi affected rows là số bản ghi được cập nhật |
| Thiếu quyền khi chạy REPLACE | Tài khoản không có quyền DELETE hoặc INSERT | Cấp quyền tối thiểu đúng nhu cầu hoặc chọn câu lệnh phù hợp |
| Dữ liệu audit bảng con không ghi nhận cascade | InnoDB cascade không kích hoạt trigger trên bảng con | Thiết kế audit ở tầng ứng dụng hoặc cơ chế phù hợp |
| REPLACE nhiều hàng cho kết quả khó đoán | Mỗi hàng đầu vào có thể xung đột với nhiều hàng hiện có | Kiểm tra dữ liệu nguồn, unique key và chạy thử trước |

## 14. Checklist trước khi dùng REPLACE

- [ ] Đã xác nhận nghiệp vụ thực sự muốn xóa và chèn lại hàng.
- [ ] Đã liệt kê PRIMARY KEY và tất cả unique index.
- [ ] Đã kiểm tra một hàng đầu vào có thể xung đột với nhiều hàng cũ.
- [ ] Đã kiểm tra cột bị bỏ qua sẽ nhận DEFAULT hoặc NULL nào.
- [ ] Đã xác định AUTO_INCREMENT có thể cấp ID mới hay không.
- [ ] Đã rà soát khóa ngoại và các hành động CASCADE, SET NULL, RESTRICT.
- [ ] Đã kiểm tra trigger DELETE và INSERT.
- [ ] Đã hiểu các trigger trên bảng con không được kích hoạt bởi thao tác cascade của InnoDB.
- [ ] Đã kiểm tra tài khoản có quyền INSERT và DELETE.
- [ ] Đã thử trên staging hoặc transaction có thể rollback.
- [ ] Đã kiểm tra bảng đích, bảng con, audit và các tham chiếu sau khi chạy.
- [ ] Đã cân nhắc UPDATE hoặc INSERT ... ON DUPLICATE KEY UPDATE nếu mục tiêu là sửa hàng hiện có.

## 15. Nguyên tắc cần ghi nhớ

1. REPLACE là thao tác xóa hàng xung đột rồi chèn hàng mới, không phải UPDATE.
2. Xung đột có thể đến từ PRIMARY KEY hoặc bất kỳ unique index nào.
3. Một hàng mới có thể làm nhiều hàng cũ bị xóa nếu các unique key xung đột với các hàng khác nhau.
4. Cột không được chỉ định nhận DEFAULT/NULL theo định nghĩa, không giữ giá trị cũ.
5. AUTO_INCREMENT có thể sinh định danh mới khi xung đột xảy ra trên unique key phụ.
6. Xóa hàng cha có thể kích hoạt ON DELETE CASCADE, SET NULL hoặc bị RESTRICT từ chối.
7. Trigger DELETE và INSERT được kích hoạt; trigger UPDATE không thay thế hai hành vi đó.
8. InnoDB cascade không kích hoạt trigger trên bảng con.
9. REPLACE cần quyền INSERT và DELETE.
10. Dùng UPDATE hoặc INSERT ... ON DUPLICATE KEY UPDATE khi muốn sửa hàng hiện có và giữ quan hệ dữ liệu.
11. Luôn kiểm tra unique key, khóa ngoại, trigger và cột mặc định trước khi dùng REPLACE trên production.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [REPLACE Statement](https://dev.mysql.com/doc/refman/9.7/en/replace.html): cú pháp, quy tắc xung đột khóa, xóa nhiều hàng, quyền và affected rows.
2. [INSERT ... ON DUPLICATE KEY UPDATE Statement](https://dev.mysql.com/doc/refman/9.7/en/insert-on-duplicate.html): so sánh với thao tác cập nhật khi trùng khóa.
3. [InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/9.7/en/innodb-foreign-key-constraints.html): RESTRICT, CASCADE, SET NULL và hành vi khóa ngoại.
4. [Using Triggers](https://dev.mysql.com/doc/refman/9.7/en/triggers.html): loại trigger và thao tác kích hoạt trigger.
5. [Foreign Key Constraints](https://dev.mysql.com/doc/refman/9.7/en/create-table-foreign-keys.html): định nghĩa khóa ngoại và hành động tham chiếu.
6. [InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/9.7/en/innodb-auto-increment-handling.html): cấp phát và quản lý giá trị AUTO_INCREMENT.
7. [Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): quyền INSERT và DELETE cần cho thao tác dữ liệu.

