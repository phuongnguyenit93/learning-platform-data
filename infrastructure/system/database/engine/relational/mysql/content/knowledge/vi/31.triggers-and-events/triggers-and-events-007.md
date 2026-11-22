# Giới hạn truy cập bảng đang được thay đổi và nguy cơ đệ quy

Trigger cho phép MySQL tự chạy một khối SQL khi một hàng được INSERT, UPDATE hoặc DELETE. Cơ chế này hữu ích để kiểm tra dữ liệu, chuẩn hóa giá trị của hàng sắp ghi và lưu audit sang bảng khác. Tuy nhiên, trigger có một giới hạn quan trọng: **trigger không được sửa đổi bảng đang được câu lệnh kích hoạt nó sử dụng**. Nếu trigger trực tiếp hoặc thông qua routine cố ghi lại vào chính bảng đó, MySQL có thể từ chối statement với lỗi 1442.

Giới hạn này thường được gọi là mutating-table restriction. Nó giúp tránh việc một câu lệnh đang thay đổi bảng lại gọi trigger để tiếp tục thay đổi cùng bảng trong một luồng thực thi lồng nhau. Vì trigger còn có thể tác động đến bảng khác và kích hoạt trigger của bảng đó, thiết kế thiếu kiểm soát có thể tạo thành chuỗi phụ thuộc vòng, khó dự đoán và khó chẩn đoán.

Trong module **DATABASE_MYSQL**, trigger nên được dùng cho những tác vụ cục bộ, có phạm vi rõ ràng. Bài học này giải thích bảng nào được phép sửa, cách dùng NEW và OLD, vì sao lỗi 1442 xuất hiện, cách nhận diện chuỗi trigger gián tiếp và các mẫu thiết kế thay thế an toàn.

## 1. Trigger hoạt động trong câu lệnh nào?

MySQL hỗ trợ trigger theo từng hàng (FOR EACH ROW). Một trigger được gắn với một bảng, một thời điểm và một sự kiện:

- BEFORE INSERT: chạy trước khi một hàng được chèn.
- AFTER INSERT: chạy sau khi một hàng được chèn.
- BEFORE UPDATE: chạy trước khi một hàng được cập nhật.
- AFTER UPDATE: chạy sau khi một hàng được cập nhật.
- BEFORE DELETE: chạy trước khi một hàng bị xóa.
- AFTER DELETE: chạy sau khi một hàng bị xóa.

MySQL không có statement-level trigger. Nếu một câu UPDATE tác động 1.000 hàng, trigger tương ứng có thể chạy 1.000 lần, một lần cho mỗi hàng.

Ví dụ:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < CURRENT_TIMESTAMP;
```

Nếu câu lệnh tác động 300 hàng, trigger AFTER UPDATE trên orders được gọi cho từng hàng bị cập nhật. Trigger không chạy một lần duy nhất cho toàn bộ statement.

Điều này quan trọng với mutating-table restriction: trong suốt quá trình statement xử lý các hàng và kích hoạt trigger, bảng nguồn vẫn đang được chính statement đó sử dụng.

## 2. Mutating-table restriction và lỗi 1442

MySQL không cho trigger sửa đổi một bảng đang được câu lệnh kích hoạt trigger sử dụng. Ví dụ, một câu UPDATE trên accounts kích hoạt trigger; trigger lại thực hiện UPDATE trên chính accounts. Statement ngoài đang sử dụng accounts, vì vậy thao tác ghi lồng nhau bị từ chối.

Ví dụ bảng:

```sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    balance DECIMAL(14, 2) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE = InnoDB;
```

Trigger sai:

```sql
DELIMITER //

CREATE TRIGGER trg_accounts_after_update
AFTER UPDATE ON accounts
FOR EACH ROW
BEGIN
    UPDATE accounts
    SET updated_at = CURRENT_TIMESTAMP
    WHERE account_id = NEW.account_id;
END//

DELIMITER ;
```

Khi chạy:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42;
```

MySQL từ chối thao tác ghi lồng nhau và trả lỗi thường gặp:

```text
ERROR 1442 (HY000):
Can't update table 'accounts' in stored function/trigger
because it is already used by statement which invoked
this stored function/trigger.
```

Thông báo cụ thể có thể khác đôi chút theo phiên bản và ngữ cảnh, nhưng mã lỗi 1442 biểu thị việc stored function/trigger cố sửa bảng đang được statement gọi nó sử dụng.

### 2.1. Vì sao không thể UPDATE lại bảng nguồn?

Statement ngoài đang điều khiển việc đọc, khóa và thay đổi các hàng trong bảng. Nếu trigger lại phát sinh một statement ghi vào cùng bảng, MySQL sẽ phải phối hợp hai luồng thay đổi lồng nhau trên cùng đối tượng trong một lần thực thi. Quy tắc này ngăn kiểu cập nhật đệ quy đó.

Không thể khắc phục bằng cách:

- Đổi tên alias của bảng.
- Đưa UPDATE vào một stored procedure được gọi từ trigger.
- Đưa UPDATE vào stored function rồi gọi function đó.
- Chia UPDATE thành một câu SQL khác nhưng vẫn chạy bên trong trigger.
- Dùng dynamic SQL để che tên bảng.

Điều được kiểm tra là bảng và đường thực thi thực tế, không phải tên alias hoặc việc câu lệnh được viết trực tiếp trong trigger hay ẩn trong routine.

### 2.2. Phạm vi của giới hạn

Hãy phân biệt hai ý:

1. Trigger có thể đọc OLD và NEW để biết giá trị của hàng đang xử lý.
2. Trigger không được dùng một câu lệnh ghi để sửa bảng đang được statement kích hoạt sử dụng.

Giới hạn cốt lõi là việc sửa đổi bảng đang được statement ngoài sử dụng. Không nên diễn giải lỗi 1442 thành quy tắc rằng trigger không thể tham chiếu bất kỳ cột hay giá trị nào của hàng nguồn; OLD và NEW chính là giao diện được MySQL cung cấp cho mục đích đó.

Nếu cần đọc các hàng khác của bảng nguồn, hãy xem xét ngữ cảnh truy vấn và semantics dữ liệu thật kỹ. Việc một SELECT có thể chạy không biến thao tác ghi cùng bảng thành hợp lệ, cũng không bảo đảm rằng truy vấn nhìn thấy trạng thái trung gian theo cách ứng dụng mong muốn.

## 3. Dùng NEW và OLD để cập nhật chính hàng đang xử lý

Với trigger BEFORE INSERT hoặc BEFORE UPDATE, MySQL cho phép gán giá trị cho các cột của hàng sắp được ghi thông qua NEW.column_name.

Đây là cách đúng để chuẩn hóa dữ liệu của chính hàng hiện tại. Không cần phát sinh UPDATE thứ hai trên bảng nguồn.

Ví dụ bảng:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Trigger hợp lệ:

```sql
DELIMITER //

CREATE TRIGGER trg_products_before_update
BEFORE UPDATE ON products
FOR EACH ROW
BEGIN
    IF NEW.price < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Price cannot be negative';
    END IF;

    SET NEW.updated_at = CURRENT_TIMESTAMP;
END//

DELIMITER ;
```

Khi ứng dụng chạy:

```sql
UPDATE products
SET price = 125000
WHERE product_id = 10;
```

Trigger sửa giá trị NEW.updated_at của hàng đang được cập nhật. Không có câu UPDATE thứ hai trên products, nên không vi phạm mutating-table restriction.

### 3.1. NEW và OLD theo từng loại trigger

| Trigger | NEW | OLD | Có thể gán NEW? |
|---|---|---|---|
| BEFORE INSERT | Giá trị hàng sắp chèn | Không có | Có |
| AFTER INSERT | Giá trị hàng vừa chèn | Không có | Không |
| BEFORE UPDATE | Giá trị mới | Giá trị cũ | Có |
| AFTER UPDATE | Giá trị mới | Giá trị cũ | Không |
| BEFORE DELETE | Không có | Giá trị sắp xóa | Không |
| AFTER DELETE | Không có | Giá trị đã xóa | Không |

OLD chỉ dùng để đọc. NEW có thể được gán trong BEFORE INSERT và BEFORE UPDATE; trong AFTER trigger, hàng đã được ghi nên không thể thay đổi NEW.

Ví dụ kiểm tra thay đổi trạng thái:

```sql
DELIMITER //

CREATE TRIGGER trg_orders_before_update
BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        SET NEW.updated_at = CURRENT_TIMESTAMP;
    END IF;
END//

DELIMITER ;
```

Toán tử <=> là phép so sánh bằng an toàn với NULL. Nó trả TRUE khi hai vế đều NULL, giúp so sánh giá trị cũ và mới rõ ràng hơn so với = trong trường hợp có NULL.

### 3.2. BEFORE và AFTER có mục đích khác nhau

Dùng BEFORE khi cần:

- Kiểm tra giá trị sắp ghi.
- Chuẩn hóa hoặc gán giá trị cho NEW.
- Từ chối dữ liệu bằng SIGNAL.

Dùng AFTER khi cần:

- Ghi audit sang bảng riêng.
- Ghi nhận sự kiện sau khi hàng nguồn đã được ghi.
- Cập nhật một bảng tổng hợp khác nếu thiết kế và transaction semantics cho phép.

Không dùng AFTER trigger để phát sinh UPDATE lên chính bảng vừa thay đổi. Nếu cần cập nhật một cột của cùng hàng, hãy cân nhắc BEFORE trigger và gán NEW.column.

## 4. Ví dụ audit đúng cách: ghi sang bảng khác

Một nhu cầu phổ biến là lưu lịch sử thay đổi trạng thái đơn hàng. Trigger có thể ghi OLD và NEW sang bảng audit riêng.

Tạo bảng nguồn:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Tạo bảng audit:

```sql
CREATE TABLE order_status_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_audit_order_changed (order_id, changed_at)
) ENGINE = InnoDB;
```

Trigger hợp lệ:

```sql
DELIMITER //

CREATE TRIGGER trg_orders_after_status_update
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO order_status_audit (
            order_id,
            old_status,
            new_status
        )
        VALUES (
            NEW.order_id,
            OLD.status,
            NEW.status
        );
    END IF;
END//

DELIMITER ;
```

Trigger chỉ INSERT vào order_status_audit, không UPDATE lại orders. Vì vậy, nó không cố sửa bảng nguồn đang được statement ngoài sử dụng.

Kiểm tra:

```sql
UPDATE orders
SET status = 'PAID',
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = 9001;

SELECT *
FROM order_status_audit
WHERE order_id = 9001
ORDER BY audit_id;
```

Với InnoDB, thao tác ghi bảng nguồn và audit cùng tham gia transaction của statement gọi trigger. Nếu trigger lỗi, statement thất bại và thay đổi transactional trong statement được rollback. Đây là một ưu điểm khi cần bảo đảm cập nhật nghiệp vụ và audit đi cùng nhau.

Bảng audit phải được thiết kế để không tạo một đường trigger ngược trở lại bảng orders. Nếu bảng audit có trigger khác, hãy kiểm tra toàn bộ chuỗi tác động.

## 5. Nguy cơ đệ quy trực tiếp và gián tiếp

Một trigger không nên được xem như một workflow engine có thể tự do gọi lại chính nó. Nguy cơ đệ quy xuất hiện khi trigger sửa bảng khác, thao tác đó kích hoạt trigger tiếp theo, rồi chuỗi tác động quay lại bảng hoặc luồng đang thực thi.

Ví dụ quan hệ phụ thuộc:

- UPDATE orders
- Trigger AFTER UPDATE trên orders
- INSERT order_audit
- Trigger AFTER INSERT trên order_audit
- UPDATE orders

Trigger đầu tiên ghi vào order_audit. Trigger của order_audit lại cố cập nhật orders. Đây là một thiết kế vòng. Khi đường thực thi cố sửa bảng vẫn đang được statement ban đầu sử dụng, MySQL có thể từ chối với lỗi 1442. Kể cả khi một chuỗi trigger không chạm ngay giới hạn đó, chuỗi phụ thuộc vòng vẫn làm hành vi khó theo dõi và dễ phát sinh nhiều lần ghi ngoài dự kiến.

### 5.1. Chuỗi trigger qua nhiều bảng

Giả sử:

- Trigger trên orders ghi vào order_audit.
- Trigger trên order_audit cập nhật customer_summary.
- Trigger trên customer_summary cập nhật lại orders.

Đây là chuỗi A → B → C → A. Khi thiết kế, hãy coi mọi trigger action và routine mà nó gọi là một phần của đồ thị phụ thuộc. Một vòng trong đồ thị có thể dẫn đến việc quay lại sửa bảng đang được statement ngoài sử dụng hoặc tạo một chuỗi xử lý không thể kiểm soát.

Không chỉ kiểm tra câu lệnh trong trigger đầu tiên. Cần truy vết cả:

- Trigger trên bảng được ghi.
- Stored procedure được gọi từ trigger.
- Stored function được dùng trong biểu thức.
- Trigger của bảng audit hoặc bảng tổng hợp.
- Các câu lệnh phát sinh từ những routine đó.

### 5.2. Trigger gián tiếp qua stored procedure/function

Đưa câu UPDATE vào procedure không làm mất giới hạn.

Ví dụ về đường gọi:

```sql
-- Trigger trên orders gọi routine này.
CALL refresh_order_row(NEW.order_id);
```

Nếu refresh_order_row thực hiện UPDATE orders, nó vẫn đang cố sửa bảng nguồn trong lúc statement trên orders kích hoạt trigger. Việc tách câu UPDATE sang routine chỉ làm đường gọi dài hơn; không thay đổi quy tắc MySQL.

Tương tự, nếu một stored function được gọi từ statement hoặc trigger và function cố sửa bảng đang được statement đó sử dụng, lỗi tương ứng vẫn có thể xảy ra.

## 6. Trigger theo từng hàng và hiệu ứng khuếch đại

Vì MySQL trigger chạy FOR EACH ROW, một statement lớn có thể kích hoạt rất nhiều lần.

Ví dụ:

```sql
UPDATE order_items
SET status = 'ARCHIVED'
WHERE created_at < '2024-01-01';
```

Nếu statement tác động 500.000 hàng, trigger AFTER UPDATE trên order_items có thể thực thi 500.000 lần. Nếu mỗi lần trigger ghi nhiều bảng, số thao tác phụ tăng theo số hàng.

Các rủi ro:

- Thời gian statement tăng mạnh.
- Nhiều lần ghi index và phát sinh I/O.
- Khóa trên bảng phụ được giữ trong transaction lâu hơn.
- Tăng khả năng deadlock khi các transaction ghi nhiều bảng theo thứ tự khác nhau.
- Audit table hoặc summary table tăng nhanh.
- Chuỗi trigger nhiều tầng khiến độ trễ khó dự đoán.

Trigger không có cơ chế statement-level để gom một lần xử lý cho toàn bộ tập hàng. Nếu cần tổng hợp theo batch, cân nhắc xử lý trong stored procedure hoặc job riêng với câu SQL set-based.

### 6.1. Không dùng trigger để thay thế xử lý batch

Ví dụ, thay vì mỗi hàng được cập nhật lại một summary row bằng trigger, có thể thực hiện:

```sql
UPDATE customer_summary AS s
JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS x
    ON x.customer_id = s.customer_id
SET s.paid_total = x.total_amount;
```

Câu lệnh set-based có thể tính lại nhiều khách hàng trong một lần. Cần chọn cách refresh phù hợp với kích thước dữ liệu, tần suất cập nhật và độ mới dữ liệu cần bảo đảm.

## 7. Giới hạn khác cần biết khi thiết kế trigger

Ngoài mutating-table restriction, trigger còn có một số giới hạn ảnh hưởng đến kiến trúc:

- Trigger chỉ chạy theo từng hàng, không có statement-level trigger.
- Trigger không được bắt đầu transaction hoặc COMMIT/ROLLBACK độc lập; nó tham gia transaction của statement gọi.
- Trigger không thể trả result set trực tiếp cho client.
- Stored procedure được gọi từ trigger phải tuân thủ các hạn chế của stored program trong ngữ cảnh trigger, ví dụ không trả result set cho client hoặc dùng dynamic SQL không được phép trong đường gọi đó.
- Trigger không được sửa bảng đang được statement gọi nó sử dụng.
- Một trigger không thể tự thay đổi OLD; chỉ có thể gán NEW trong BEFORE INSERT/UPDATE.
- Các hành động ON DELETE CASCADE hoặc ON UPDATE CASCADE của foreign key trong InnoDB không kích hoạt trigger tương ứng.

Điểm cuối rất quan trọng với audit. Nếu một hàng con bị xóa do foreign key cascade, không nên giả định trigger DELETE trên bảng con sẽ được gọi để ghi audit. Nếu cần audit cascade, phải thiết kế cơ chế khác hoặc thực hiện thao tác xóa qua quy trình có kiểm soát.

## 8. Trigger và transaction

Trigger không sở hữu transaction riêng. Các câu INSERT/UPDATE/DELETE mà trigger thực hiện tham gia transaction của statement hoặc transaction do caller mở.

Ví dụ:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

-- Trigger AFTER UPDATE ghi order_status_audit.

COMMIT;
```

Nếu trigger INSERT audit thất bại trên InnoDB, UPDATE ngoài cũng thất bại. Trong một transaction rõ ràng, caller cần xử lý lỗi và quyết định ROLLBACK theo transaction contract.

Với bảng dùng storage engine không hỗ trợ transaction, không thể giả định mọi thay đổi đã thực hiện sẽ được hoàn tác. Muốn có tính nguyên tử giữa bảng nguồn và bảng audit, hãy dùng transactional engine như InnoDB cho các bảng liên quan.

### 8.1. Trigger lỗi làm statement thất bại

Nếu trigger phát SIGNAL, vi phạm constraint hoặc gặp lỗi SQL khác, statement kích hoạt trigger bị lỗi. Với InnoDB, thay đổi transactional do statement đó thực hiện được rollback.

Ví dụ kiểm tra dữ liệu:

```sql
DELIMITER //

CREATE TRIGGER trg_products_validate_insert
BEFORE INSERT ON products
FOR EACH ROW
BEGIN
    IF NEW.price < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Price must be non-negative';
    END IF;
END//

DELIMITER ;
```

INSERT có giá âm sẽ thất bại; hàng không được chèn vào bảng InnoDB. Ứng dụng nên xử lý SQLSTATE và message theo hợp đồng lỗi đã thiết kế.

## 9. Các mẫu thiết kế thay thế an toàn

Khi gặp yêu cầu "trigger cần cập nhật lại chính bảng nguồn", hãy xác định mục tiêu thật sự rồi chọn cách phù hợp.

### 9.1. Cập nhật cột của hàng hiện tại bằng NEW

Nếu chỉ cần chuẩn hóa hoặc tính giá trị cho chính hàng đang ghi, dùng BEFORE trigger:

```sql
CREATE TRIGGER trg_orders_before_insert
BEFORE INSERT ON orders
FOR EACH ROW
SET NEW.created_at = COALESCE(
    NEW.created_at,
    CURRENT_TIMESTAMP
);
```

Đây là một assignment trên hàng mới, không phải UPDATE bảng nguồn.

### 9.2. Ghi audit sang bảng riêng

Nếu cần lịch sử thay đổi, dùng AFTER trigger để INSERT vào audit table. Đảm bảo bảng audit không tạo trigger quay lại cập nhật bảng nguồn.

### 9.3. Dùng stored procedure làm điểm điều phối

Nếu nghiệp vụ cần cập nhật nhiều bảng và có thứ tự rõ ràng, để ứng dụng gọi một procedure điều phối:

1. Kiểm tra điều kiện.
2. Cập nhật bảng nguồn.
3. Đọc số hàng bị tác động nếu cần.
4. Cập nhật bảng liên quan bằng câu lệnh set-based.
5. Ghi outbox hoặc audit.
6. Commit theo transaction contract.

Các câu lệnh điều phối được thực hiện tuần tự ở cấp procedure, sau khi từng statement hoàn tất. Không đặt việc sửa lại bảng nguồn bên trong trigger đang được statement trên bảng đó kích hoạt.

### 9.4. Dùng generated column hoặc constraint

Nếu giá trị có thể được biểu diễn bằng biểu thức trên cùng một hàng, cân nhắc generated column. Nếu yêu cầu là ràng buộc một hàng, dùng CHECK, NOT NULL, UNIQUE hoặc khóa phù hợp khi MySQL hỗ trợ.

Ví dụ:

```sql
CREATE TABLE order_lines (
    line_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    PRIMARY KEY (line_id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

line_total được tính từ cột cùng hàng; không cần trigger UPDATE lại order_lines.

### 9.5. Dùng outbox cho xử lý hậu kỳ

Nếu thay đổi nguồn cần kích hoạt một workflow khác, ghi một event vào outbox cùng transaction với dữ liệu nghiệp vụ. Worker bên ngoài đọc outbox và thực hiện công việc sau commit.

Mẫu này phù hợp khi:

- Cần gọi dịch vụ bên ngoài.
- Cần xử lý tổng hợp lớn.
- Cần retry độc lập.
- Không muốn chuỗi trigger kéo dài transaction nghiệp vụ.

Outbox cần khóa idempotency, trạng thái xử lý và chiến lược retry rõ ràng để tránh xử lý trùng.

## 10. Cách truy vết lỗi 1442

Khi statement báo lỗi 1442, hãy tìm đường ghi vào bảng nguồn theo thứ tự:

1. Xác định statement ngoài đang chạy trên bảng nào.
2. Liệt kê trigger của bảng đó.
3. Đọc toàn bộ trigger body bằng SHOW CREATE TRIGGER.
4. Tìm INSERT/UPDATE/DELETE trực tiếp lên bảng nguồn.
5. Kiểm tra routine được trigger gọi.
6. Kiểm tra function được dùng trong biểu thức hoặc câu lệnh.
7. Truy vết trigger trên những bảng phụ mà trigger đầu tiên ghi vào.
8. Xác định đường phụ thuộc có quay lại bảng nguồn hay không.
9. Thay thao tác ghi cùng hàng bằng SET NEW.column nếu phù hợp.
10. Chuyển workflow nhiều bước sang procedure/application/outbox.

Xem trigger trong schema hiện tại:

```sql
SHOW TRIGGERS
FROM sales;
```

Xem định nghĩa chi tiết:

```sql
SHOW CREATE TRIGGER sales.trg_orders_after_status_update;
```

Tra cứu metadata:

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_SCHEMA,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_STATEMENT,
    DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'sales'
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION;
```

Metadata giúp lập danh sách trigger theo bảng và thời điểm. Sau đó đọc từng ACTION_STATEMENT hoặc dùng SHOW CREATE TRIGGER để kiểm tra nội dung và đường gọi routine.

### 10.1. Dựng đồ thị phụ thuộc trigger

Có thể ghi lại đường đi theo dạng:

| Trigger nguồn | Hành động | Trigger tiếp theo | Rủi ro |
|---|---|---|---|
| orders AFTER UPDATE | INSERT order_audit | order_audit AFTER INSERT | Có thể mở chuỗi lồng |
| order_audit AFTER INSERT | UPDATE customer_summary | customer_summary trigger | Tăng số tầng và khóa |
| customer_summary AFTER UPDATE | UPDATE orders | orders trigger | Vòng phụ thuộc quay về bảng nguồn |

Một chuỗi chỉ có hướng một chiều dễ hiểu và dễ kiểm thử hơn. Nếu đồ thị có chu trình, hãy xem lại trách nhiệm của trigger và chuyển điều phối ra một tầng có kiểm soát.

## 11. Ví dụ hoàn chỉnh: thay trigger tự cập nhật nguồn bằng BEFORE trigger

Yêu cầu: mỗi lần cập nhật sản phẩm, updated_at phải phản ánh thời điểm mới. Cách sai là AFTER UPDATE trigger chạy UPDATE products. Cách đúng là BEFORE UPDATE gán NEW.updated_at.

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Trigger đúng:

```sql
DELIMITER //

CREATE TRIGGER trg_products_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
BEGIN
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END//

DELIMITER ;
```

Thử:

```sql
UPDATE products
SET price = price + 1000
WHERE product_id = 10;

SELECT product_id, price, updated_at
FROM products
WHERE product_id = 10;
```

Cột updated_at được đặt trong cùng thao tác cập nhật hàng. Không có statement UPDATE lồng nhau.

## 12. Ví dụ hoàn chỉnh: audit một chiều

Mô hình audit an toàn nên giữ đường ghi một chiều từ bảng nghiệp vụ sang bảng audit.

```sql
CREATE TABLE payment (
    payment_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (payment_id)
) ENGINE = InnoDB;

CREATE TABLE payment_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payment_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_payment_audit_payment (payment_id, audit_id)
) ENGINE = InnoDB;
```

Trigger:

```sql
DELIMITER //

CREATE TRIGGER trg_payment_audit
AFTER UPDATE ON payment
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO payment_audit (
            payment_id,
            old_status,
            new_status
        )
        VALUES (
            NEW.payment_id,
            OLD.status,
            NEW.status
        );
    END IF;
END//

DELIMITER ;
```

Đường thực thi:

1. UPDATE payment.
2. AFTER UPDATE trigger chạy.
3. Trigger INSERT vào payment_audit.
4. Statement kết thúc.

Không có trigger trên payment_audit ghi ngược vào payment. Nếu cần xử lý thêm sau khi audit được ghi, dùng worker/outbox hoặc procedure do ứng dụng gọi.

## 13. Những hiểu nhầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| AFTER UPDATE trigger chạy UPDATE lại bảng nguồn | Lỗi 1442 | Dùng BEFORE và gán NEW nếu chỉ sửa hàng hiện tại |
| Đưa UPDATE vào stored procedure để né giới hạn | Vẫn vi phạm nếu procedure sửa bảng đang được statement dùng | Truy vết toàn bộ call chain |
| Cho rằng đổi alias sẽ tránh lỗi | MySQL vẫn nhận diện cùng bảng | Thay đổi thiết kế thao tác ghi |
| Dùng trigger làm workflow nhiều tầng | Khó kiểm soát thứ tự, khóa và retry | Dùng procedure/application/outbox |
| Tạo trigger A ghi B, trigger B ghi lại A | Có chu trình phụ thuộc và có thể chạm mutating-table restriction | Giữ đồ thị trigger một chiều |
| Nghĩ trigger chạy một lần cho statement | Multi-row DML có thể kích hoạt trigger rất nhiều lần | Đánh giá chi phí FOR EACH ROW |
| Dùng AFTER trigger để sửa NEW | Không thể gán NEW trong AFTER | Gán NEW trong BEFORE |
| Ghi audit rồi quên transaction | Audit và dữ liệu nguồn có thể không cùng tính nguyên tử nếu engine khác nhau | Dùng InnoDB cho các bảng liên quan |
| Nghĩ foreign key cascade sẽ gọi trigger | InnoDB cascade không kích hoạt trigger | Thiết kế audit riêng cho cascade |
| Chỉ xem trigger trực tiếp | Lỗi có thể nằm trong procedure/function hoặc trigger của bảng phụ | Truy vết toàn bộ dependency |
| Không kiểm thử batch | Trigger có thể làm statement lớn chậm đáng kể | Test với số hàng gần workload thật |

## 14. Checklist thiết kế trigger an toàn

**Trước khi tạo trigger:**

- Xác định sự kiện INSERT, UPDATE hay DELETE.
- Chọn BEFORE hay AFTER theo mục tiêu.
- Nếu cần sửa chính hàng hiện tại, dùng NEW.column trong BEFORE trigger.
- Xác định bảng nào statement ngoài đang sử dụng.
- Không thiết kế trigger ghi lại vào bảng nguồn.
- Kiểm tra procedure/function mà trigger có thể gọi.
- Lập đồ thị phụ thuộc giữa các bảng và trigger.
- Loại bỏ chu trình A → B → ... → A.
- Đánh giá trigger chạy theo từng hàng và chi phí với batch.

**Khi ghi sang bảng khác:**

- Dùng bảng audit/outbox riêng.
- Không tạo trigger trên bảng phụ quay lại sửa bảng nguồn.
- Dùng InnoDB cho các bảng cần cùng transaction.
- Xác định thứ tự truy cập bảng nhất quán để giảm deadlock.
- Kiểm thử lỗi constraint, SIGNAL và rollback.
- Xác nhận foreign key cascade có thể không kích hoạt trigger.

**Khi vận hành:**

- Dùng SHOW TRIGGERS và SHOW CREATE TRIGGER để kiểm tra.
- Tra cứu INFORMATION_SCHEMA.TRIGGERS.
- Ghi nhận mã lỗi 1442 và statement gây lỗi.
- Truy vết cả stored routine và trigger lồng nhau.
- Kiểm thử single-row và multi-row DML.
- Đo thời gian statement và lượng ghi phụ.
- Đưa thay đổi trigger vào migration có review và rollback plan.

## 15. Ghi nhớ

- MySQL trigger chạy FOR EACH ROW, không có statement-level trigger.
- Trigger không được sửa đổi bảng đang được statement kích hoạt nó sử dụng; lỗi thường gặp là 1442.
- Đưa câu UPDATE vào stored procedure/function không né được mutating-table restriction.
- OLD và NEW cung cấp giá trị hàng cũ/mới; OLD chỉ đọc.
- Có thể gán NEW.column trong BEFORE INSERT và BEFORE UPDATE để sửa giá trị của chính hàng hiện tại.
- AFTER trigger phù hợp để ghi audit sang bảng khác, không dùng để UPDATE lại bảng nguồn.
- Trigger có thể tạo chuỗi tác động qua bảng phụ; thiết kế chu trình A → B → A rất khó kiểm soát và có thể gặp lỗi 1442.
- Trigger chạy nhiều lần với multi-row DML, nên chi phí phụ tăng theo số hàng.
- Trigger tham gia transaction của statement gọi; không có transaction độc lập để tự COMMIT.
- Với InnoDB, lỗi trigger làm statement thất bại và thay đổi transactional của statement được rollback.
- Foreign key cascade trong InnoDB không kích hoạt trigger tương ứng.
- Nếu cần workflow nhiều bước, tổng hợp hoặc xử lý bất đồng bộ, cân nhắc stored procedure, application service hoặc outbox.
- Dùng SHOW CREATE TRIGGER và INFORMATION_SCHEMA.TRIGGERS để truy vết toàn bộ đường thực thi.

Thiết kế trigger tốt giữ hành động ngắn, cục bộ và có hướng phụ thuộc rõ ràng. Khi cần sửa hàng đang xử lý, gán NEW trong BEFORE trigger; khi cần ghi lịch sử, ghi sang bảng audit riêng; khi cần điều phối nhiều bảng hoặc nhiều bước, đưa logic vào một tầng orchestration có transaction contract rõ ràng.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Restrictions on Stored Programs: https://dev.mysql.com/doc/refman/8.0/en/stored-program-restrictions.html
- MySQL 8.0 Reference Manual — Trigger Syntax and Examples: https://dev.mysql.com/doc/refman/8.0/en/trigger-syntax.html
- MySQL 8.0 Reference Manual — Using Triggers: https://dev.mysql.com/doc/refman/8.0/en/triggers.html
- MySQL 8.0 Reference Manual — CREATE TRIGGER Statement: https://dev.mysql.com/doc/refman/8.0/en/create-trigger.html
- MySQL 8.0 Reference Manual — The TRIGGERS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-triggers-table.html
- MySQL 8.0 Reference Manual — InnoDB and FOREIGN KEY Constraints: https://dev.mysql.com/doc/refman/8.0/en/create-table-foreign-keys.html

