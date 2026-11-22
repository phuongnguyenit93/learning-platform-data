# Cannot add/update/delete child row và lỗi khóa ngoại

Lỗi khóa ngoại thường xuất hiện khi ứng dụng thêm hoặc sửa một bản ghi con nhưng bản ghi cha được tham chiếu không tồn tại, hoặc khi ứng dụng xóa/sửa bản ghi cha trong lúc vẫn còn bản ghi con phụ thuộc. Trong MySQL InnoDB, hai lỗi phổ biến nhất là `ERROR 1452` (không thể thêm/cập nhật hàng con) và `ERROR 1451` (không thể xóa/cập nhật hàng cha).

Khóa ngoại bảo vệ tính toàn vẹn tham chiếu ở database. Khi gặp lỗi, cần xác định chính xác bảng con, bảng cha, constraint, các cột tham gia và dữ liệu tại thời điểm câu lệnh thất bại. Không nên tắt kiểm tra khóa ngoại chỉ để câu lệnh chạy qua: việc đó có thể tạo dữ liệu mồ côi và MySQL không tự kiểm tra lại các hàng đã ghi khi bật kiểm tra trở lại.

Bài học sử dụng MySQL 8.4 và InnoDB. Các ví dụ minh họa quan hệ khách hàng, đơn hàng và chi tiết đơn hàng; hãy thay tên bảng/cột bằng schema thực tế khi điều tra.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt lỗi 1452 ở bảng con với lỗi 1451 ở bảng cha.
- Đọc tên constraint và xác định đúng cột tham chiếu.
- Kiểm tra dữ liệu cha/con, kiểu dữ liệu, index và cấu hình khóa ngoại.
- Hiểu hành vi `RESTRICT`, `NO ACTION`, `CASCADE` và `SET NULL`.
- Xử lý thứ tự ghi dữ liệu, import, migration và giao dịch liên quan đến khóa ngoại.
- Phát hiện dữ liệu mồ côi nếu kiểm tra khóa ngoại từng bị tắt.
- Chọn cách khắc phục bảo toàn nghiệp vụ thay vì xóa hoặc bỏ qua dữ liệu tùy tiện.

## 1. Hai lỗi khóa ngoại thường gặp

Giả sử schema có ba bảng:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;

CREATE TABLE purchase_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE = InnoDB;

CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (id),
    KEY idx_items_order_id (order_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders (id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE
) ENGINE = InnoDB;
```

`purchase_orders.customer_id` là cột con tham chiếu `customers.id`. `order_items.order_id` là cột con tham chiếu `purchase_orders.id`.

### 1.1. ERROR 1452: Cannot add or update a child row

Lỗi 1452 xảy ra khi `INSERT` hoặc `UPDATE` tạo ra giá trị khóa ngoại ở bảng con nhưng không tìm thấy hàng cha tương ứng.

Ví dụ, khách hàng `9001` không tồn tại:

```sql
INSERT INTO purchase_orders (customer_id, created_at)
VALUES (9001, NOW());
```

MySQL trả về lỗi có dạng:

```text
ERROR 1452 (23000): Cannot add or update a child row:
a foreign key constraint fails
```

Thông điệp thường kèm tên database, bảng con và constraint, ví dụ `fk_orders_customer`. Nguyên nhân trực tiếp là `purchase_orders.customer_id = 9001` không tham chiếu đến `customers.id` hợp lệ.

Lỗi tương tự xảy ra khi cập nhật một hàng con:

```sql
UPDATE purchase_orders
SET customer_id = 9001
WHERE id = 100;
```

Nếu khách hàng 9001 không tồn tại, câu `UPDATE` bị từ chối. Nếu cột khóa ngoại cho phép `NULL`, đặt giá trị thành `NULL` có thể hợp lệ vì không còn yêu cầu tham chiếu đến hàng cha; đây phải là quyết định đúng với nghiệp vụ.

### 1.2. ERROR 1451: Cannot delete or update a parent row

Lỗi 1451 xảy ra khi `DELETE` hoặc `UPDATE` làm thay đổi khóa được tham chiếu ở bảng cha, trong khi vẫn còn hàng con và hành động của constraint không cho phép thay đổi đó.

Ví dụ khách hàng 10 vẫn có đơn hàng:

```sql
DELETE FROM customers
WHERE id = 10;
```

Nếu `purchase_orders` còn hàng có `customer_id = 10` và constraint dùng `RESTRICT`/`NO ACTION`, MySQL từ chối thao tác:

```text
ERROR 1451 (23000): Cannot delete or update a parent row:
a foreign key constraint fails
```

Lỗi này cũng có thể xuất hiện khi cập nhật `customers.id` sang giá trị khác. Hãy kiểm tra cả thao tác xóa lẫn cập nhật khóa chính; không phải chỉ câu `DELETE` mới gây lỗi 1451.

### 1.3. Phân biệt nhanh

| Mã lỗi | Bảng bị thao tác | Điều kiện gây lỗi | Hướng điều tra đầu tiên |
|---|---|---|---|
| 1452 | Bảng con | Giá trị khóa ngoại mới không có hàng cha phù hợp | Tìm hàng cha theo toàn bộ khóa tham chiếu |
| 1451 | Bảng cha | Còn hàng con tham chiếu và hành động FK không cho phép | Tìm các hàng con đang tham chiếu |

`SQLSTATE 23000` là nhóm lỗi integrity constraint violation. Không chỉ dựa vào SQLSTATE để kết luận nguyên nhân; đọc mã lỗi, tên constraint và câu lệnh cụ thể.

## 2. Quy trình điều tra lỗi 1452

### 2.1. Đọc tên constraint từ thông báo lỗi

Ví dụ lỗi có đoạn:

```text
CONSTRAINT `fk_orders_customer`
FOREIGN KEY (`customer_id`)
REFERENCES `customers` (`id`)
```

Thông tin này cho biết:

- Bảng con: `purchase_orders`.
- Cột con: `customer_id`.
- Bảng cha: `customers`.
- Cột được tham chiếu: `id`.
- Constraint: `fk_orders_customer`.

Nếu thông báo ứng dụng đã rút gọn, chạy:

```sql
SHOW CREATE TABLE purchase_orders\G
```

Không đoán constraint chỉ từ tên cột. Một bảng có thể có nhiều foreign key hoặc một foreign key gồm nhiều cột.

### 2.2. Kiểm tra hàng cha có tồn tại không

Với giá trị đang gây lỗi:

```sql
SELECT id, full_name
FROM customers
WHERE id = 9001;
```

Nếu không có kết quả, kiểm tra ứng dụng có đang truyền nhầm ID, dùng ID từ môi trường khác, hoặc tạo hàng cha chưa thành công hay không. Xác nhận database/schema mà connection đang dùng:

```sql
SELECT DATABASE() AS current_database,
       @@hostname AS server_host,
       @@port AS server_port,
       @@autocommit AS autocommit_mode;
```

Một lỗi phổ biến là ứng dụng tạo customer ở database A nhưng tạo order ở database B, hoặc đọc ID từ môi trường staging rồi ghi vào production. Luôn xác minh connection thực tế, không chỉ dựa vào cấu hình được cho là đang dùng.

### 2.3. Kiểm tra toàn bộ khóa nếu là composite foreign key

Ví dụ constraint gồm hai cột:

```sql
FOREIGN KEY (tenant_id, account_id)
REFERENCES accounts (tenant_id, id)
```

Hàng cha phải khớp đồng thời cả `tenant_id` và `account_id`. Kiểm tra chỉ `account_id` là chưa đủ:

```sql
SELECT tenant_id, id
FROM accounts
WHERE tenant_id = 7
  AND id = 9001;
```

Thứ tự cột trong foreign key và index liên quan cũng cần khớp. Không tự đảo vị trí các cột khi đọc constraint hoặc viết truy vấn chẩn đoán.

### 2.4. Kiểm tra NULL và quy tắc dữ liệu

Nếu cột con cho phép `NULL`, giá trị `NULL` không cần một hàng cha tương ứng. Nếu cột là `NOT NULL`, `NULL` có thể gây lỗi ràng buộc `NOT NULL` trước hoặc cùng quá trình kiểm tra dữ liệu tùy câu lệnh.

Kiểm tra định nghĩa:

```sql
SHOW CREATE TABLE purchase_orders\G

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'purchase_orders'
  AND COLUMN_NAME = 'customer_id';
```

Không dùng `NULL` để né lỗi nếu mỗi đơn hàng bắt buộc phải thuộc một khách hàng. Khi quan hệ là bắt buộc, hãy tạo hoặc xác định đúng hàng cha trước khi ghi hàng con.

## 3. Quy trình điều tra lỗi 1451

### 3.1. Tìm các hàng con đang tham chiếu

Nếu định xóa khách hàng 10:

```sql
SELECT id, customer_id, created_at
FROM purchase_orders
WHERE customer_id = 10;
```

Nếu có kết quả, các hàng đó đang tham chiếu đến khách hàng. Tùy nghiệp vụ, có thể:

- Từ chối xóa khách hàng và giữ lịch sử đơn hàng.
- Chuyển quan hệ sang một khách hàng hợp lệ khác nếu nghiệp vụ cho phép.
- Lưu trữ hoặc xóa các hàng con theo quy trình đã phê duyệt.
- Dùng `ON DELETE CASCADE` nếu xóa cha thực sự phải xóa toàn bộ dữ liệu con.

Không xóa hàng con chỉ để làm cho câu `DELETE` chạy thành công. Đơn hàng, hóa đơn và lịch sử giao dịch thường phải được giữ lại vì yêu cầu kiểm toán hoặc nghiệp vụ.

### 3.2. Kiểm tra chuỗi quan hệ nhiều cấp

Trong ví dụ, khách hàng có đơn hàng, đơn hàng có item. Xóa khách hàng có thể bị chặn bởi `purchase_orders`; xóa đơn hàng có thể kích hoạt cascade sang `order_items` theo constraint đã khai báo.

Truy vấn toàn bộ dữ liệu liên quan trước khi thay đổi:

```sql
SELECT
    c.id AS customer_id,
    p.id AS order_id,
    i.id AS item_id,
    i.product_name
FROM customers AS c
LEFT JOIN purchase_orders AS p
    ON p.customer_id = c.id
LEFT JOIN order_items AS i
    ON i.order_id = p.id
WHERE c.id = 10
ORDER BY p.id, i.id;
```

Truy vấn này giúp hiểu phạm vi dữ liệu bị ảnh hưởng. Với hệ thống nhiều tầng, tiếp tục lần theo các foreign key từ bảng cha xuống bảng con và kiểm tra tất cả hành động cascade.

### 3.3. Cập nhật khóa cha

Nếu thay đổi khóa chính hoặc khóa được tham chiếu, kiểm tra rule `ON UPDATE`:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME = 'customers'
  AND REFERENCED_COLUMN_NAME = 'id';
```

Trong thiết kế thông thường, khóa chính định danh như `id` ít khi cần thay đổi. Nếu cần đổi một mã nghiệp vụ, cân nhắc giữ surrogate primary key ổn định và cập nhật cột mã nghiệp vụ riêng. Cách này tránh phải cập nhật hàng loạt khóa ngoại.

## 4. Xác minh định nghĩa khóa ngoại và kiểu dữ liệu

### 4.1. Đọc SHOW CREATE TABLE ở cả hai phía

Chạy cho bảng con và bảng cha:

```sql
SHOW CREATE TABLE customers\G
SHOW CREATE TABLE purchase_orders\G
```

So sánh:

- Storage engine của hai bảng; InnoDB hỗ trợ foreign key.
- Kiểu dữ liệu của cột tham chiếu và cột được tham chiếu.
- Độ dài và signedness đối với kiểu số nguyên.
- Charset/collation của cột chuỗi.
- Thứ tự các cột trong khóa ghép.
- Index trên cột được tham chiếu và cột con.
- Rule `ON DELETE` và `ON UPDATE`.

Ví dụ lỗi thiết kế thường gặp:

```sql
-- Không tương thích về signedness:
-- customers.id là BIGINT UNSIGNED
-- purchase_orders.customer_id là BIGINT có dấu
```

Với kiểu số nguyên, kích thước và signedness phải tương thích. Với kiểu chuỗi, charset/collation của hai cột cần tương thích theo yêu cầu của InnoDB. Khi tạo foreign key, hãy định nghĩa cột con cùng kiểu với cột cha thay vì trông chờ MySQL tự chuyển đổi.

### 4.2. Kiểm tra metadata constraint

Tra cứu constraint và các cột tham gia:

```sql
SELECT
    k.CONSTRAINT_NAME,
    k.TABLE_NAME AS child_table,
    k.COLUMN_NAME AS child_column,
    k.ORDINAL_POSITION,
    k.REFERENCED_TABLE_NAME AS parent_table,
    k.REFERENCED_COLUMN_NAME AS parent_column
FROM information_schema.KEY_COLUMN_USAGE AS k
WHERE k.CONSTRAINT_SCHEMA = DATABASE()
  AND k.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION;
```

Tra cứu rule xóa/cập nhật:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();
```

Các truy vấn này giúp xác định đúng tên và hành vi constraint trong database hiện tại. Nếu dùng nhiều schema, thêm điều kiện `CONSTRAINT_SCHEMA` cụ thể thay vì dựa vào `DATABASE()`.

### 4.3. Index và khóa ghép

InnoDB cần index phù hợp cho cột được tham chiếu ở bảng cha; trong thiết kế nên tham chiếu primary key hoặc unique key. Cột con cũng cần index để kiểm tra và thực hiện các thao tác tham chiếu hiệu quả; InnoDB có thể tự tạo index cần thiết khi tạo foreign key nếu chưa có index phù hợp.

Với khóa ghép `(tenant_id, account_id)`, index phải bắt đầu bằng các cột theo đúng thứ tự cần thiết. Kiểm tra index:

```sql
SHOW INDEX FROM accounts;
SHOW INDEX FROM purchase_orders;
```

Không tạo index trùng lặp một cách máy móc. Kiểm tra index hiện có có cùng prefix và thứ tự cột phù hợp hay không.

## 5. Hành vi ON DELETE và ON UPDATE

Hành động tham chiếu quyết định MySQL xử lý ra sao khi hàng cha bị xóa hoặc khóa được tham chiếu thay đổi.

| Rule | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `RESTRICT` | Từ chối thay đổi cha nếu còn hàng con tham chiếu | Muốn bảo vệ dữ liệu con và buộc ứng dụng xử lý rõ ràng |
| `NO ACTION` | Với InnoDB, tương đương `RESTRICT`; kiểm tra ngay, không trì hoãn đến cuối transaction | Cần thể hiện rõ không cho phép thay đổi cha khi còn con |
| `CASCADE` | Xóa/cập nhật hàng con tương ứng theo thay đổi ở cha | Dữ liệu con phụ thuộc hoàn toàn vào vòng đời của cha |
| `SET NULL` | Đặt cột khóa ngoại ở hàng con thành `NULL` | Quan hệ là tùy chọn và cột con cho phép NULL |

Nếu không chỉ định rule, mặc định là hành vi hạn chế thay đổi cha (`NO ACTION`/`RESTRICT` theo ngữ nghĩa InnoDB).

### 5.1. RESTRICT và NO ACTION

Hai rule này không cho phép xóa/cập nhật cha khi vẫn còn hàng con. Trong InnoDB, kiểm tra được thực hiện ngay khi câu lệnh chạy; MySQL không hỗ trợ deferred constraint checking để đợi đến `COMMIT`.

### 5.2. CASCADE

Ví dụ xóa đơn hàng thì tự động xóa item:

```sql
CONSTRAINT fk_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders (id)
    ON DELETE CASCADE
```

Khi xóa một hàng `purchase_orders`, các hàng `order_items` tương ứng bị xóa theo. Đây là hành động mạnh: xóa nhầm một hàng cha có thể xóa nhiều hàng con. Chỉ dùng cascade khi vòng đời dữ liệu và chính sách lưu trữ cho phép.

### 5.3. SET NULL

Ví dụ quan hệ người quản lý là tùy chọn:

```sql
CREATE TABLE employees (
    id BIGINT UNSIGNED PRIMARY KEY,
    manager_id BIGINT UNSIGNED NULL,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees (id)
        ON DELETE SET NULL
) ENGINE = InnoDB;
```

Khi xóa manager, `manager_id` của nhân viên trực thuộc được đặt thành `NULL`. Cột `manager_id` phải cho phép `NULL`; nếu cột là `NOT NULL`, thiết kế này không phù hợp.

### 5.4. Không đổi rule chỉ để né lỗi

Thay `RESTRICT` bằng `CASCADE` để bỏ qua lỗi 1451 có thể xóa dữ liệu ngoài dự kiến. Thay bằng `SET NULL` có thể làm mất quan hệ cần thiết. Trước khi thay rule, xác nhận:

1. Quan hệ có bắt buộc hay không.
2. Dữ liệu con có cần tồn tại độc lập sau khi xóa cha không.
3. Có yêu cầu audit, retention hoặc soft delete không.
4. Số lượng hàng bị cascade hoặc set null là bao nhiêu.
5. Ứng dụng và báo cáo có chấp nhận hành vi mới không.

## 6. Thứ tự ghi dữ liệu và transaction

### 6.1. Tạo cha trước, tạo con sau

Khi tạo customer và order trong cùng transaction, ghi hàng cha trước:

```sql
START TRANSACTION;

INSERT INTO customers (full_name)
VALUES ('Nguyen An');

SET @customer_id = LAST_INSERT_ID();

INSERT INTO purchase_orders (customer_id, created_at)
VALUES (@customer_id, NOW());

COMMIT;
```

Trong ứng dụng, nên lấy generated key từ JDBC/JPA hoặc dùng ID đã tạo rõ ràng. Nếu bước tạo cha thất bại, rollback transaction và không tiếp tục tạo hàng con với ID giả định.

### 6.2. Xóa con trước, xóa cha sau

Nếu rule là `RESTRICT`, muốn xóa cả cây dữ liệu theo nghiệp vụ thì xóa hàng con trước:

```sql
START TRANSACTION;

DELETE FROM order_items
WHERE order_id IN (
    SELECT id
    FROM purchase_orders
    WHERE customer_id = 10
);

DELETE FROM purchase_orders
WHERE customer_id = 10;

DELETE FROM customers
WHERE id = 10;

COMMIT;
```

Đây chỉ là ví dụ kỹ thuật; không dùng quy trình này nếu đơn hàng hoặc item cần được lưu giữ. Với dữ liệu lớn, cần chia batch, kiểm soát lock và đánh giá thời gian transaction. Các thao tác DML InnoDB có thể rollback nếu chưa commit; không áp dụng giả định này cho DDL.

### 6.3. Kiểm tra trước rồi ghi không thay thế khóa ngoại

Một pattern dễ mắc là:

1. `SELECT` kiểm tra parent có tồn tại.
2. Nếu có, chạy `INSERT` vào child.

Giữa hai bước, transaction khác có thể xóa hoặc thay đổi parent. Đây là race condition nếu chỉ dựa vào truy vấn kiểm tra. Foreign key là lớp bảo vệ cuối cùng và InnoDB phối hợp khóa để duy trì tính toàn vẹn khi có concurrent transaction.

Ứng dụng vẫn có thể kiểm tra trước để trả thông báo thân thiện, nhưng phải xử lý lỗi 1452/1451 ở thao tác ghi thực tế. Không coi kết quả `SELECT` trước đó là bảo đảm parent sẽ còn tồn tại.

## 7. Import, migration và dữ liệu mồ côi

### 7.1. Import đúng thứ tự

Khi nạp dữ liệu từ CSV hoặc dump:

1. Tạo schema và các bảng theo dependency.
2. Nạp dữ liệu bảng cha trước.
3. Nạp dữ liệu bảng con sau.
4. Đối chiếu số hàng, khóa và dữ liệu tham chiếu.
5. Chỉ chuyển ứng dụng sang dùng dữ liệu sau khi kiểm chứng hoàn tất.

Nếu dùng công cụ dump/restore, kiểm tra cách công cụ sắp xếp thứ tự bảng, trigger và constraint. Một file dữ liệu riêng lẻ của bảng con có thể không thể import độc lập nếu chưa có bảng cha tương ứng.

### 7.2. foreign_key_checks

MySQL cho phép tắt kiểm tra khóa ngoại trong session:

```sql
SELECT @@SESSION.foreign_key_checks;
SET SESSION foreign_key_checks = 0;
-- Thao tác import có kiểm soát.
SET SESSION foreign_key_checks = 1;
```

Đây là cơ chế đặc biệt dành cho các quy trình import/restore đã được kiểm soát, không phải cách sửa lỗi 1452 hoặc 1451 trong ứng dụng. Khi tắt `foreign_key_checks`, MySQL có thể chấp nhận hàng con không có hàng cha. Bật lại biến không quét và xác thực lại dữ liệu đã nạp trong thời gian tắt kiểm tra.

Nếu đã từng tắt kiểm tra, phải chủ động tìm orphan rows trước khi tin rằng dữ liệu hợp lệ. Cũng cần bảo đảm biến được bật lại trong đúng session; biến session không tự động thay đổi các connection khác.

### 7.3. Tìm dữ liệu mồ côi

Với quan hệ `purchase_orders.customer_id -> customers.id`:

```sql
SELECT p.id, p.customer_id
FROM purchase_orders AS p
LEFT JOIN customers AS c
    ON c.id = p.customer_id
WHERE p.customer_id IS NOT NULL
  AND c.id IS NULL
LIMIT 100;
```

Đếm tổng số orphan:

```sql
SELECT COUNT(*) AS orphan_count
FROM purchase_orders AS p
LEFT JOIN customers AS c
    ON c.id = p.customer_id
WHERE p.customer_id IS NOT NULL
  AND c.id IS NULL;
```

Với foreign key ghép, nối trên tất cả cột theo đúng cặp tham chiếu. Nếu một thành phần được phép `NULL`, xử lý theo semantics của khóa ghép và quy tắc nghiệp vụ; không chỉ nối một cột rồi kết luận dữ liệu mồ côi.

### 7.4. Sửa orphan rows

Không tự động xóa orphan. Các cách xử lý có thể gồm:

- Khôi phục hàng cha từ nguồn dữ liệu đáng tin cậy.
- Ánh xạ khóa con sang hàng cha đúng nếu có bằng chứng nghiệp vụ.
- Đưa bản ghi lỗi vào vùng cách ly để chủ dữ liệu xác minh.
- Xóa bản ghi con chỉ khi chính sách lưu trữ cho phép và có phê duyệt.
- Giữ bản ghi trong bảng staging, không chuyển vào bảng nghiệp vụ cho đến khi quan hệ hợp lệ.

Lưu lại số lượng, khóa bị ảnh hưởng và hành động sửa để có thể kiểm toán. Sau khi sửa, chạy lại truy vấn orphan và kiểm tra toàn bộ quan hệ liên quan.

## 8. Chẩn đoán sâu bằng InnoDB và Performance Schema

### 8.1. SHOW ENGINE INNODB STATUS

Sau lỗi khóa ngoại, chạy:

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm phần `LATEST FOREIGN KEY ERROR`. Phần này thường ghi thời điểm, transaction, câu lệnh và constraint liên quan đến lỗi khóa ngoại gần nhất mà InnoDB ghi nhận. Đây là thông tin hữu ích khi log ứng dụng không hiển thị đầy đủ thông báo.

Lưu ý: đây là lỗi gần nhất được ghi nhận trên instance, có thể bị một lỗi khác ghi đè. Thu thập thông tin ngay sau khi tái hiện lỗi; không xem nó là lịch sử đầy đủ cho mọi transaction.

### 8.2. Xem transaction và lock

Khi lỗi chỉ xảy ra dưới tải đồng thời, xem transaction đang chạy và lock:

```sql
SELECT *
FROM information_schema.INNODB_TRX
ORDER BY trx_started;

SELECT *
FROM performance_schema.data_locks;

SELECT *
FROM performance_schema.data_lock_waits;
```

Các bảng này giúp tìm transaction dài, lock đang chờ và quan hệ giữa transaction giữ lock với transaction bị chặn. Quyền đọc Performance Schema/Information Schema có thể phụ thuộc tài khoản; chỉ cấp quyền quan sát phù hợp cho người trực vận hành.

### 8.3. Đối chiếu constraint với dữ liệu thực

Đối với một lỗi 1452, ghi lại giá trị khóa ngoại của câu lệnh thất bại, sau đó truy vấn đúng bảng cha. Đối với 1451, truy vấn bảng con theo đúng khóa cha. Nếu dữ liệu thay đổi liên tục, điều tra trong cùng transaction/snapshot phù hợp hoặc tái hiện trong môi trường kiểm thử; kết quả truy vấn chạy sau lỗi có thể khác trạng thái tại thời điểm lỗi.

## 9. Ví dụ xử lý một tình huống thực tế

Ứng dụng tạo đơn hàng nhưng thỉnh thoảng nhận lỗi 1452:

```text
Cannot add or update a child row:
a foreign key constraint fails
(`shop`.`purchase_orders`, CONSTRAINT `fk_orders_customer`
FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`))
```

Quy trình xử lý:

1. Ghi lại `customer_id` mà request gửi đến và xác định database/schema của connection.
2. Chạy `SHOW CREATE TABLE purchase_orders` và xác nhận `fk_orders_customer` tham chiếu `customers.id`.
3. Truy vấn `customers` theo ID đó. Nếu không có hàng, tìm nguồn tạo ID: request, cache, service tạo khách hàng hoặc transaction trước.
4. Nếu khách hàng được tạo trong transaction khác, xác nhận transaction đó đã commit thành công trước khi order được ghi.
5. Nếu customer và order được tạo trong cùng luồng, tạo parent trước child trong cùng transaction và dùng generated ID thực tế.
6. Nếu lỗi chỉ xảy ra khi có concurrent request, kiểm tra race condition, transaction rollback và log của thao tác tạo parent.
7. Sau khi sửa, theo dõi tỷ lệ lỗi và đối chiếu orphan rows.

Ví dụ khác: thao tác xóa khách hàng nhận lỗi 1451. Truy vấn tất cả đơn hàng của khách hàng, xác định chính sách retention, rồi chọn từ chối xóa, soft delete, chuyển quan hệ hoặc xóa theo cascade đã được phê duyệt. Không thay `RESTRICT` thành `CASCADE` chỉ để loại bỏ thông báo lỗi.

## 10. Các nguyên nhân thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Insert child báo 1452 | Parent chưa tồn tại hoặc ID truyền sai | Kiểm tra ID và tạo parent trước child |
| Update child báo 1452 | Đổi FK sang parent không tồn tại | Xác minh parent đích và mapping |
| Delete parent báo 1451 | Còn hàng con tham chiếu | Tìm child rows và áp dụng chính sách nghiệp vụ |
| Update khóa cha báo 1451 | Khóa cha đang được child tham chiếu, rule không cho cascade | Giữ khóa định danh ổn định hoặc thiết kế update rule phù hợp |
| Chỉ lỗi trên một môi trường | Sai database, dữ liệu seed thiếu hoặc lệch môi trường | Xác nhận `DATABASE()`, host và dữ liệu cha |
| Lỗi khi import | Nạp child trước parent hoặc dump thiếu bảng cha | Sắp xếp thứ tự import và đối chiếu khóa |
| Tạo FK thất bại | Kiểu, signedness, charset/collation hoặc index không tương thích | So sánh `SHOW CREATE TABLE` hai phía |
| Bật lại foreign_key_checks nhưng vẫn có orphan | MySQL không tự validate lại dữ liệu cũ | Chạy truy vấn orphan và sửa dữ liệu |
| Lỗi chỉ xuất hiện dưới tải | Race condition giữa thao tác parent/child hoặc transaction rollback | Kiểm tra transaction, lock và xử lý lỗi tại thao tác ghi |
| Xóa cha làm mất nhiều dữ liệu | `ON DELETE CASCADE` không phù hợp vòng đời dữ liệu | Xem lại retention, soft delete và rule FK |

## 11. Checklist xử lý lỗi khóa ngoại

- [ ] Ghi lại mã lỗi đầy đủ (1451/1452), SQLSTATE và câu lệnh gây lỗi.
- [ ] Xác định database/schema thực tế của connection.
- [ ] Đọc tên constraint, bảng con, bảng cha và tất cả cột tham gia.
- [ ] Kiểm tra hàng cha tồn tại (1452) hoặc hàng con đang tham chiếu (1451).
- [ ] Với composite FK, kiểm tra toàn bộ cặp cột theo đúng thứ tự.
- [ ] So sánh kiểu, signedness, charset/collation và index ở hai bảng.
- [ ] Kiểm tra `ON DELETE`, `ON UPDATE`, nullability và thứ tự transaction.
- [ ] Xem `LATEST FOREIGN KEY ERROR` nếu cần chẩn đoán InnoDB sâu hơn.
- [ ] Kiểm tra import, migration, concurrent transaction và khả năng rollback.
- [ ] Nếu từng tắt `foreign_key_checks`, tìm và xử lý orphan rows.
- [ ] Chọn cách khắc phục theo nghiệp vụ, giữ lại bằng chứng và theo dõi sau sửa.

## 12. Bài tập tự kiểm tra

1. `ERROR 1452` xảy ra ở bảng cha hay bảng con? Điều kiện nào gây ra lỗi?
2. `ERROR 1451` có thể xuất hiện khi cập nhật khóa chính của bảng cha không?
3. Với foreign key ghép `(tenant_id, account_id)`, vì sao chỉ kiểm tra `account_id` là chưa đủ?
4. `RESTRICT` khác `CASCADE` như thế nào khi xóa parent?
5. Vì sao `SET NULL` yêu cầu cột foreign key cho phép NULL?
6. Tắt rồi bật lại `foreign_key_checks` có khiến MySQL xác thực các hàng đã nạp không?
7. Khi import dữ liệu có quan hệ cha/con, nên nạp bảng nào trước?
8. Vì sao truy vấn kiểm tra parent tồn tại trước `INSERT` không thay thế được foreign key?
9. Lệnh nào giúp xem phần `LATEST FOREIGN KEY ERROR` của InnoDB?
10. Khi xóa khách hàng có đơn hàng, cần xác định điều gì trước khi cân nhắc cascade?

**Gợi ý đáp án:** (1) Bảng con; giá trị FK mới không tìm thấy hàng cha tương ứng. (2) Có, nếu còn hàng con và `ON UPDATE` không cho phép thay đổi. (3) Vì tất cả thành phần của khóa phải khớp cùng một hàng cha theo đúng thứ tự. (4) `RESTRICT` chặn xóa cha khi còn con; `CASCADE` tự xóa hàng con phụ thuộc. (5) Vì MySQL phải đặt FK ở hàng con thành NULL khi xóa cha. (6) Không; phải tự truy vấn tìm orphan rows. (7) Bảng cha trước, bảng con sau. (8) Parent có thể bị xóa giữa hai bước; FK bảo vệ tính toàn vẹn tại thời điểm ghi. (9) `SHOW ENGINE INNODB STATUS`. (10) Chính sách retention, audit, vòng đời dữ liệu và số lượng hàng con bị ảnh hưởng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.4/en/innodb-foreign-key-constraints.html)
- [MySQL 8.4 Reference Manual: FOREIGN KEY Constraint Differences](https://dev.mysql.com/doc/refman/8.4/en/ansi-diff-foreign-keys.html)
- [MySQL 8.4 Reference Manual: INFORMATION_SCHEMA KEY_COLUMN_USAGE](https://dev.mysql.com/doc/refman/8.4/en/information-schema-key-column-usage-table.html)
- [MySQL 8.4 Reference Manual: INFORMATION_SCHEMA REFERENTIAL_CONSTRAINTS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-referential-constraints-table.html)
- [MySQL 8.4 Reference Manual: InnoDB Standard Monitor and Lock Monitor](https://dev.mysql.com/doc/refman/8.4/en/innodb-standard-monitor.html)
