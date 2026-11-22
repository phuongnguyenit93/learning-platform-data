# Ranh giới giao dịch và xử lý lỗi phát sinh trong trigger

Trigger là stored program được MySQL tự động thực thi khi một sự kiện INSERT, UPDATE hoặc DELETE xảy ra trên bảng. Trigger chạy như một phần của câu lệnh đã kích hoạt nó. Vì vậy, trigger không sở hữu một transaction độc lập: các thay đổi transactional do trigger thực hiện tham gia cùng transaction và cùng ranh giới statement với câu lệnh gọi trigger.

Điều này có hệ quả quan trọng khi có lỗi. Nếu một trigger phát sinh lỗi không được xử lý, câu lệnh kích hoạt trigger thất bại. Với InnoDB, MySQL hoàn tác thay đổi của toàn bộ statement đó, bao gồm thay đổi trên bảng gốc và các bảng transactional mà trigger đã ghi. Nếu statement nằm trong một transaction lớn hơn, các statement thành công trước đó vẫn còn trong transaction; caller phải quyết định COMMIT hay ROLLBACK toàn nghiệp vụ.

Bài học thuộc phạm vi DATABASE_MYSQL: hiểu trigger tham gia transaction của caller như thế nào, phân biệt statement rollback với transaction rollback, kiểm soát lỗi ở BEFORE/AFTER trigger, dùng SIGNAL và handler có chủ đích, đồng thời tránh thiết kế side effect không thể hoàn tác.

## 1. Trigger chạy trong ngữ cảnh của câu lệnh kích hoạt

MySQL hỗ trợ trigger theo hai thời điểm và ba sự kiện:

| Thời điểm | Sự kiện | Ý nghĩa |
|---|---|---|
| BEFORE | INSERT | Chạy trước khi hàng mới được ghi |
| AFTER | INSERT | Chạy sau khi hàng mới được ghi thành công |
| BEFORE | UPDATE | Chạy trước khi hàng hiện tại được cập nhật |
| AFTER | UPDATE | Chạy sau khi hàng được cập nhật thành công |
| BEFORE | DELETE | Chạy trước khi hàng bị xóa |
| AFTER | DELETE | Chạy sau khi hàng bị xóa thành công |

Trigger trong MySQL là row-level trigger: mỗi trigger được khai báo FOR EACH ROW. MySQL không có statement-level trigger chạy đúng một lần cho toàn bộ câu lệnh.

Nếu một UPDATE thay đổi 500 hàng, trigger tương ứng có thể được gọi 500 lần. Nếu một hàng trong quá trình xử lý làm trigger phát sinh lỗi không được xử lý, statement có thể thất bại; với InnoDB, thay đổi của toàn statement được hoàn tác.

### 1.1. OLD và NEW

Trigger dùng OLD và NEW để truy cập giá trị hàng:

| Sự kiện | OLD | NEW |
|---|---|---|
| INSERT | Không có hàng cũ | Hàng sắp được thêm |
| UPDATE | Giá trị trước cập nhật | Giá trị sau cập nhật dự kiến |
| DELETE | Hàng sắp bị xóa | Không có hàng mới |

Trong BEFORE INSERT và BEFORE UPDATE, trigger có thể gán giá trị cho NEW.column để chuẩn hóa hoặc áp dụng giá trị mặc định. OLD là chỉ đọc. Trong AFTER trigger, không thể thay đổi hàng đã ghi thông qua NEW.

Ví dụ:

~~~sql
DELIMITER //

CREATE TRIGGER bi_orders_normalize
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    SET NEW.order_code = UPPER(TRIM(NEW.order_code));
END//

DELIMITER ;
~~~

Trigger này chuẩn hóa mã đơn trước khi hàng được ghi. Việc gán NEW là một phần của statement INSERT; không tạo transaction riêng.

### 1.2. Trigger có thể chạy nhiều lần trong một statement

Ví dụ:

~~~sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < NOW(6)
  AND status = 'OPEN';
~~~

Nếu có 10.000 hàng thỏa điều kiện, trigger AFTER UPDATE được gọi cho từng hàng đã cập nhật. Không giả định trigger chạy một lần cho cả câu lệnh.

Điều này ảnh hưởng đến:
- Số lần ghi audit.
- Số lần kiểm tra điều kiện.
- Số lần đọc bảng liên quan.
- Khóa được giữ và thời gian transaction.
- Khả năng một hàng lỗi làm cả statement thất bại.

Hãy giữ trigger ngắn, có index hỗ trợ các lookup và tránh truy vấn lặp lại không cần thiết.

## 2. Trigger không mở transaction riêng

Trigger không được dùng các lệnh điều khiển transaction như:

- START TRANSACTION hoặc BEGIN để mở transaction mới.
- COMMIT.
- ROLLBACK.
- Các thao tác điều khiển transaction không được phép khác trong trigger.

Trigger luôn chạy trong ngữ cảnh transaction của statement gọi nó. Nếu không có transaction tường minh, statement thường tự commit theo autocommit. Nếu caller đã mở transaction, trigger tham gia transaction đó.

Ví dụ trigger ghi audit:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    event_name VARCHAR(40) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_order_audit_order (order_id)
) ENGINE = InnoDB;
~~~

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        event_name,
        recorded_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        NOW(6)
    );
END//

DELIMITER ;
~~~

Khi INSERT vào orders, trigger thêm một dòng order_audit trong cùng transaction. Không có COMMIT riêng bên trong trigger.

## 3. Autocommit và transaction của caller

### 3.1. autocommit = 1

Khi autocommit bật và không có transaction tường minh, một statement INSERT/UPDATE/DELETE cùng toàn bộ trigger được thực thi như một đơn vị. Nếu statement thành công, thay đổi transactional của bảng gốc và trigger được commit cùng nhau. Nếu statement thất bại, thay đổi của statement được rollback.

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'OPEN', 250.00);
~~~

Nếu trigger AFTER INSERT ghi audit thành công, cả hàng orders và order_audit được commit. Nếu trigger lỗi, cả statement thất bại và thay đổi transactional của statement bị hoàn tác.

### 3.2. Caller mở transaction tường minh

~~~sql
START TRANSACTION;

INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'OPEN', 250.00);

-- Trigger ai_orders_audit đã ghi audit trong cùng transaction.

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = LAST_INSERT_ID();

ROLLBACK;
~~~

Sau ROLLBACK, cả hàng orders và dòng order_audit được trigger tạo ra đều biến mất vì cả hai bảng dùng InnoDB và cùng tham gia transaction. UPDATE cũng được hoàn tác.

Trigger không thể tự commit phần audit để giữ lại khi caller rollback. Đây là hành vi cần thiết để dữ liệu nghiệp vụ và audit transactional không lệch nhau.

### 3.3. Trigger không quyết định thời điểm COMMIT

Trigger không biết toàn bộ quy trình nghiệp vụ của ứng dụng. Nó chỉ biết statement hiện tại và dữ liệu OLD/NEW. Transaction có thể chứa:
- Nhiều statement từ ứng dụng.
- Một hoặc nhiều procedure được gọi.
- Nhiều lần kích hoạt trigger.
- Các thay đổi trên nhiều bảng.

Caller là nơi quyết định commit toàn bộ hoặc rollback toàn bộ transaction, trừ khi procedure được thiết kế sở hữu transaction. Trigger không được tự quyết định kết thúc transaction đó.

## 4. Statement rollback khi trigger phát sinh lỗi

Với InnoDB, statement DML và các thao tác transactional mà trigger thực hiện là một đơn vị nguyên tử. Nếu trigger phát sinh lỗi không được xử lý, statement kích hoạt trigger thất bại và thay đổi của statement bị hoàn tác.

Điều này áp dụng cả khi lỗi xảy ra trong BEFORE trigger hoặc AFTER trigger.

### 4.1. Lỗi trong BEFORE trigger

BEFORE trigger chạy trước khi hàng được ghi. Nếu trigger phát SIGNAL hoặc một câu lệnh trong trigger lỗi:
- Hàng mới không được thêm hoặc hàng cũ không được cập nhật/xóa.
- Các thay đổi transactional của statement được hoàn tác.
- Caller nhận lỗi nếu condition không được handler xử lý.

Ví dụ:

~~~sql
DELIMITER //

CREATE TRIGGER bi_orders_validate
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF NEW.total_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order amount must be positive';
    END IF;
END//

DELIMITER ;
~~~

Thử:

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'OPEN', 0);
~~~

Statement thất bại vì điều kiện nghiệp vụ. Hàng không được ghi.

### 4.2. Lỗi trong AFTER trigger

AFTER trigger chạy sau thao tác hàng gốc, nhưng vẫn trong cùng statement. Nếu AFTER trigger lỗi, với InnoDB thay đổi hàng gốc và các thay đổi transactional đã thực hiện bởi trigger thuộc statement đó bị rollback.

Ví dụ thay đổi trigger audit để cố ý từ chối một trạng thái:

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        event_name,
        recorded_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        NOW(6)
    );

    IF NEW.status = 'REJECTED' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Rejected orders cannot be inserted';
    END IF;
END//

DELIMITER ;
~~~

Thử:

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'REJECTED', 250.00);
~~~

Mặc dù trigger đã chạy INSERT vào order_audit trước khi SIGNAL, cả INSERT orders và INSERT order_audit đều bị rollback nếu hai bảng dùng InnoDB. AFTER nghĩa là sau thao tác hàng ở cấp trigger, không có nghĩa statement đã commit.

### 4.3. Trigger lỗi không nhất thiết rollback toàn transaction

Nếu statement nằm trong transaction tường minh, lỗi thông thường trong trigger làm rollback statement. Các statement thành công trước đó trong transaction vẫn còn hiệu lực chưa commit.

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 50
WHERE account_id = 1;

-- INSERT này kích hoạt trigger và trigger phát lỗi.
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'REJECTED', 250.00);

-- Transaction vẫn có thể còn hoạt động sau lỗi statement thông thường.
SELECT balance
FROM account
WHERE account_id = 1;

-- Caller quyết định:
ROLLBACK;
~~~

UPDATE account trước đó không tự động mất chỉ vì INSERT thất bại. Nếu toàn nghiệp vụ yêu cầu không giữ thay đổi trừ tiền, caller phải ROLLBACK transaction.

Ngoại lệ quan trọng là deadlock: InnoDB có thể rollback toàn bộ transaction được chọn làm deadlock victim. Lock wait timeout mặc định thường chỉ rollback statement đang chờ, trừ khi cấu hình innodb_rollback_on_timeout thay đổi hành vi.

## 5. Multi-row statement và lỗi ở một hàng

Vì trigger là row-level, một statement nhiều hàng có thể gọi trigger nhiều lần.

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES
    (1001, 'OPEN', 100.00),
    (1002, 'OPEN', 200.00),
    (1003, 'REJECTED', 300.00),
    (1004, 'OPEN', 400.00);
~~~

Giả sử trigger AFTER INSERT phát lỗi khi NEW.status = 'REJECTED'. Với InnoDB:
- Trigger chạy cho các hàng theo quá trình statement xử lý.
- Khi hàng REJECTED gây lỗi không được xử lý, statement INSERT thất bại.
- Các hàng đã thêm trước đó trong cùng statement bị rollback.
- Các dòng audit transactional đã ghi bởi trigger trong cùng statement cũng bị rollback.
- Không có phần thành công một phần của statement được giữ lại.

Không thiết kế dựa trên giả định “ba hàng đầu thành công thì vẫn giữ, hàng lỗi bị bỏ qua” khi dùng một statement InnoDB nhiều hàng. Nếu muốn chấp nhận từng hàng độc lập, hãy tách thành các statement riêng hoặc xử lý từng hàng trong transaction theo chính sách rõ ràng.

### 5.1. Một statement nhiều hàng không phải nhiều transaction

Với autocommit bật, một INSERT nhiều hàng vẫn là một statement và một transaction tự động. Trigger được gọi nhiều lần nhưng tất cả lần gọi đó thuộc cùng statement transaction.

Nếu cần mỗi hàng có kết quả độc lập, ứng dụng có thể:
- Gửi từng INSERT riêng với autocommit bật.
- Dùng batch theo nhóm nhỏ có ranh giới transaction rõ.
- Dùng staging table, kiểm tra dữ liệu trước rồi mới chuyển sang bảng đích.
- Dùng stored procedure xử lý từng hàng với savepoint/handler nếu phù hợp.

Mỗi lựa chọn có chi phí round trip, throughput và semantics lỗi khác nhau.

## 6. Handler trong trigger

Trigger là stored program và có thể khai báo condition handler trong compound block. Handler có thể xử lý một condition rồi CONTINUE hoặc EXIT khỏi block theo quy tắc handler.

Tuy nhiên, handler không tạo transaction mới và không thể COMMIT/ROLLBACK. Vì trigger thuộc statement gọi nó, quyết định xử lý lỗi phải giữ được hợp đồng của statement.

### 6.1. Handler không nên nuốt lỗi dữ liệu

Ví dụ một handler CONTINUE bắt mọi SQLEXCEPTION:

~~~sql
DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    SET @trigger_error = TRUE;
~~~

Nếu dùng kiểu này để nuốt lỗi khi ghi audit, statement gốc có thể tiếp tục và commit trong khi audit không được ghi. Điều đó tạo ra trạng thái nghiệp vụ không đúng nếu audit là bắt buộc.

Không bắt mọi lỗi rồi âm thầm tiếp tục. Chỉ dùng CONTINUE khi nghiệp vụ xác định rõ condition đó có thể bỏ qua và caller có cách nhận biết kết quả.

### 6.2. EXIT handler và RESIGNAL

Có thể dùng EXIT handler để phát lại lỗi, giúp condition truyền tới statement caller:

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    INSERT INTO order_audit (
        order_id,
        event_name,
        recorded_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        NOW(6)
    );
END//

DELIMITER ;
~~~

Handler trên không thay đổi phạm vi transaction. Nó chỉ phát lại lỗi. Khi lỗi thoát khỏi trigger, statement INSERT bên ngoài thất bại; với InnoDB, statement rollback.

Nếu không cần bổ sung xử lý, để lỗi tự truyền ra cũng là lựa chọn rõ ràng. Không thêm handler chỉ để có thêm code.

### 6.3. GET DIAGNOSTICS trong handler

Khi cần phân loại lỗi hoặc bổ sung thông tin, handler có thể đọc diagnostics:

~~~sql
DECLARE v_sqlstate CHAR(5);
DECLARE v_errno INT;
DECLARE v_message TEXT;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    RESIGNAL;
END;
~~~

GET DIAGNOSTICS nên được gọi trước khi thực hiện statement khác có thể thay đổi diagnostics area. Nếu cần ghi log vào bảng InnoDB trong handler rồi RESIGNAL, bản ghi log đó cũng thuộc transaction và có thể bị rollback cùng statement. Không kỳ vọng log transactional vẫn còn sau khi statement rollback.

## 7. SIGNAL: từ chối thao tác theo quy tắc nghiệp vụ

SIGNAL cho phép trigger chủ động phát condition. SQLSTATE 45000 thường được dùng cho lỗi do ứng dụng định nghĩa.

Ví dụ ngăn giảm giá vượt giới hạn:

~~~sql
DELIMITER //

CREATE TRIGGER bu_order_item_validate_discount
BEFORE UPDATE ON order_item
FOR EACH ROW
BEGIN
    IF NEW.discount_percent < 0
       OR NEW.discount_percent > 50 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Discount must be between 0 and 50';
    END IF;
END//

DELIMITER ;
~~~

Khi UPDATE vi phạm quy tắc:
- Trigger phát lỗi.
- Statement UPDATE thất bại.
- Thay đổi transactional của statement được rollback.
- Caller nhận SQLSTATE 45000 và message.

### 7.1. Chọn lỗi nghiệp vụ hay constraint

Dùng SIGNAL khi cần biểu đạt quy tắc nghiệp vụ không thể mô hình hóa trực tiếp bằng CHECK, FOREIGN KEY hoặc UNIQUE constraint.

Ưu tiên constraint cho quy tắc dữ liệu đơn giản và phổ quát vì constraint được database bảo vệ ở mọi đường ghi. Trigger phù hợp cho logic cần tham chiếu OLD/NEW, tạo audit hoặc phối hợp bảng khác. Không dùng trigger để thay thế mọi constraint.

### 7.2. Thông điệp lỗi ổn định

Ứng dụng nên phân loại lỗi bằng SQLSTATE hoặc mã lỗi nghiệp vụ ổn định, không parse chuỗi message tùy tiện. Message có thể được chỉnh sửa khi triển khai; SQLSTATE và quy ước lỗi cần được quản lý như một phần contract.

## 8. Các thay đổi trong trigger có rollback cùng statement không?

Câu trả lời phụ thuộc storage engine của các bảng mà trigger tác động.

### 8.1. Tất cả bảng dùng InnoDB

Nếu bảng gốc và bảng audit đều là InnoDB:
- Thay đổi hàng gốc.
- INSERT/UPDATE/DELETE do trigger thực hiện.
- Thay đổi transactional từ các routine được phép gọi.

đều tham gia cùng transaction. Khi statement thất bại, các thay đổi transactional của statement bị rollback. Khi caller rollback transaction, tất cả thay đổi chưa commit cũng bị rollback.

### 8.2. Có bảng không hỗ trợ transaction

Nếu trigger ghi vào bảng MyISAM trong khi bảng gốc là InnoDB, không thể kỳ vọng ROLLBACK khôi phục thay đổi MyISAM.

Ví dụ:

~~~sql
CREATE TABLE order_audit_nontransactional (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    event_name VARCHAR(40) NOT NULL
) ENGINE = MyISAM;
~~~

Nếu trigger INSERT vào bảng MyISAM rồi sau đó phát lỗi:
- Thay đổi InnoDB của statement có thể được rollback.
- Thay đổi MyISAM không có bảo đảm rollback tương ứng và có thể vẫn còn.
- Audit có thể ghi nhận sự kiện mà hàng nghiệp vụ không tồn tại.

Với audit cần nhất quán, dùng InnoDB cho cả bảng gốc và bảng audit. Tránh trộn engine transactional và nontransactional trong cùng nghiệp vụ cần atomicity.

### 8.3. Side effect bên ngoài database

Transaction MySQL không thể tự thu hồi:
- Email đã gửi.
- HTTP request đã thực hiện.
- File đã ghi.
- Message đã đẩy vào broker ngoài transaction.
- Tác động của một hệ thống khác không tham gia cùng transaction.

Trigger không phải nơi phù hợp để thực hiện side effect ngoài database. Nếu cần gửi thông báo khi đơn hàng được tạo, hãy ghi một outbox event trong cùng transaction InnoDB rồi để worker gửi sau COMMIT.

## 9. Thiết kế audit trigger có tính nhất quán

Một audit trigger thường ghi lại trạng thái cũ và mới của hàng. Ví dụ:

~~~sql
CREATE TABLE order_status_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_order_status_audit_order_time (order_id, changed_at)
) ENGINE = InnoDB;
~~~

~~~sql
DELIMITER //

CREATE TRIGGER au_orders_status_audit
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO order_status_audit (
            order_id,
            old_status,
            new_status,
            changed_at
        )
        VALUES (
            NEW.order_id,
            OLD.status,
            NEW.status,
            NOW(6)
        );
    END IF;
END//

DELIMITER ;
~~~

Toán tử NULL-safe equality <=> giúp so sánh an toàn khi cột có thể NULL. Trong ví dụ status là NOT NULL, nhưng mẫu so sánh này hữu ích khi áp dụng cho cột nullable.

Nếu UPDATE thất bại sau khi trigger ghi audit, cả thay đổi order và audit của statement đều rollback khi dùng InnoDB. Nếu caller rollback transaction lớn hơn, audit cũng rollback.

### 9.1. Audit trigger không thay thế audit bảo mật toàn diện

Trigger ghi nhận thay đổi hàng ở cấp database, nhưng có thể không biết:
- Người dùng cuối thực sự là ai nếu ứng dụng dùng chung một database account.
- Lý do nghiệp vụ của thay đổi.
- Request ID hoặc trace ID từ tầng API.
- Thông tin xác thực ngoài database.

Nếu cần các thông tin này, ứng dụng có thể truyền metadata qua một cơ chế được kiểm soát hoặc ghi audit ở tầng ứng dụng. Tránh dựa vào user variable session mà không quản lý connection pool và ranh giới request.

## 10. Lỗi trong BEFORE và AFTER trigger: khác nhau ở thời điểm, giống nhau ở transaction

| Nội dung | BEFORE | AFTER |
|---|---|---|
| Thời điểm | Trước khi thay đổi hàng được hoàn tất | Sau thao tác hàng ở cấp trigger |
| Có thể gán NEW | Có với INSERT/UPDATE | Không thể sửa hàng qua NEW |
| Mục đích phổ biến | Validate, normalize, thiết lập giá trị | Audit, cập nhật bảng phụ |
| Khi SIGNAL | Statement thất bại trước khi hoàn tất thay đổi hàng | Statement thất bại dù hàng đã đi qua bước thao tác |
| Rollback InnoDB | Statement rollback | Statement rollback, gồm cả thay đổi audit transactional |

Không nhầm AFTER với “đã commit”. AFTER chỉ mô tả thứ tự trigger so với thao tác hàng. COMMIT thuộc transaction của caller và có thể xảy ra sau đó.

## 11. Trigger và các câu lệnh tác động nhiều hàng

Các lệnh sau có thể kích hoạt trigger theo từng hàng:
- INSERT nhiều hàng.
- INSERT ... SELECT.
- LOAD DATA.
- UPDATE nhiều hàng.
- DELETE nhiều hàng.
- REPLACE theo các hàng được xử lý.

Cần kiểm tra trigger có chi phí tuyến tính phù hợp với số hàng hay không. Một truy vấn trong trigger cho mỗi hàng có thể biến một bulk operation thành hàng nghìn hoặc hàng triệu lookup.

### 11.1. Tránh truy vấn không có index trong trigger

Nếu trigger kiểm tra:

~~~sql
SELECT COUNT(*)
INTO v_count
FROM customer_order
WHERE customer_id = NEW.customer_id;
~~~

hãy bảo đảm customer_id có index phù hợp. Nếu không, mỗi hàng kích hoạt trigger có thể quét bảng liên quan.

### 11.2. Không cập nhật lại bảng đang được statement sử dụng

MySQL hạn chế trigger/function sửa một bảng đang được statement gọi nó sử dụng. Ví dụ một UPDATE orders kích hoạt trigger rồi trigger lại UPDATE orders có thể gây lỗi 1442.

Không dùng trigger để cập nhật đệ quy chính bảng đã kích hoạt trigger. Với BEFORE INSERT/UPDATE, hãy gán NEW.column để điều chỉnh hàng hiện tại. Với logic cập nhật nhiều hàng, viết rõ trong statement hoặc procedure ở ngoài trigger.

### 11.3. Foreign key cascade không kích hoạt trigger

Các thao tác do ON DELETE CASCADE hoặc ON UPDATE CASCADE của foreign key thực hiện không kích hoạt trigger trên các bảng bị cascade. Nếu cần audit cả thay đổi cascade, không giả định trigger ở bảng con sẽ chạy. Hãy thiết kế audit theo cơ chế khác và kiểm thử với quan hệ khóa ngoại thực tế.

TRUNCATE TABLE cũng không tương đương DELETE từng hàng và không kích hoạt DELETE trigger. Nếu cần trigger audit cho từng hàng bị xóa, dùng DELETE theo điều kiện phù hợp.

## 12. Deadlock và lock wait do trigger

Trigger có thể đọc hoặc ghi thêm bảng, vì vậy nó mở rộng tập khóa mà statement cần.

Ví dụ:
- Transaction A cập nhật orders rồi trigger ghi order_audit.
- Transaction B cập nhật order_audit rồi sau đó cập nhật orders.
- Hai transaction khóa theo thứ tự ngược nhau và có thể tạo deadlock.

Để giảm rủi ro:
- Giữ trigger ngắn.
- Truy cập bảng liên quan theo thứ tự nhất quán.
- Tạo index cho các điều kiện tìm hàng trong trigger.
- Tránh gọi logic lặp hoặc cập nhật nhiều bảng không cần thiết.
- Không giữ transaction mở trong lúc ứng dụng chờ người dùng.
- Xử lý deadlock bằng retry toàn transaction ở caller.

### 12.1. Deadlock khác lỗi trigger thông thường

Nếu trigger phát SIGNAL, thường statement thất bại và statement rollback. Nếu InnoDB phát hiện deadlock, toàn transaction victim có thể bị rollback. Caller cần phân biệt mã lỗi và không chỉ chạy lại statement cuối.

### 12.2. Lock wait timeout

Lock wait timeout mặc định thường rollback statement đang chờ, còn transaction có thể vẫn mở. Cấu hình innodb_rollback_on_timeout có thể thay đổi hành vi thành rollback toàn transaction. Kiểm tra cấu hình thực tế:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout,
    @@GLOBAL.innodb_rollback_on_timeout;
~~~

Với nghiệp vụ nhiều bước, chính sách an toàn thường là rollback toàn transaction và retry từ đầu nếu thao tác idempotent.

## 13. DDL tạo hoặc xóa trigger và implicit commit

CREATE TRIGGER và DROP TRIGGER là các câu lệnh DDL có thể gây implicit commit. Không đặt chúng giữa các thao tác DML rồi mong ROLLBACK hoàn tác cả dữ liệu và định nghĩa trigger.

Ví dụ không nên coi là một transaction có thể rollback:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
INSERT INTO order_audit(order_id, event_name, recorded_at)
VALUES (NEW.order_id, 'ORDER_CREATED', NOW(6));

ROLLBACK;
~~~

DDL có thể commit transaction trước khi thực thi. Thay đổi trigger sau khi tạo thành công không được ROLLBACK như DML. Migration trigger nên được triển khai như một bước schema riêng, có kế hoạch xác minh và khôi phục định nghĩa.

Trước khi DROP hoặc CREATE trigger trong production:
- Kiểm tra trigger hiện có bằng SHOW TRIGGERS.
- Lưu định nghĩa bằng SHOW CREATE TRIGGER.
- Xác định ứng dụng có đang ghi vào bảng không.
- Xem xét metadata lock và thời gian triển khai.
- Kiểm tra trigger sau khi migration hoàn tất.

## 14. Trigger và replication

Trigger có thể ảnh hưởng cách thay đổi dữ liệu được ghi vào binary log.

- Với statement-based replication, statement được chạy lại trên replica và trigger tương ứng có thể chạy trên replica.
- Với row-based replication, các thay đổi hàng do source trigger tạo ra được ghi thành row events; replica áp dụng các row events và không chạy lại trigger cho các row event đó.
- Với MIXED, server có thể chọn định dạng phù hợp cho từng statement theo quy tắc logging.

Vì vậy, không thiết kế trigger để giả định nó luôn chạy một lần trên mỗi server trong topology. Đặc biệt, nếu dùng statement-based replication, trigger phải có hành vi xác định và dữ liệu cần thiết phải nhất quán.

Kiểm tra:

~~~sql
SELECT
    @@GLOBAL.binlog_format AS binlog_format,
    @@GLOBAL.log_bin AS log_bin;
~~~

Nếu trigger ghi audit, kiểm tra dữ liệu audit trên source và replica theo replication format đang dùng. Không thêm một job ở replica để ghi lại cùng audit row nếu row event đã chứa thay đổi do source trigger tạo ra, nếu không có thể ghi trùng.

## 15. Bảo mật và quyền thực thi trigger

Trigger có DEFINER. Khi trigger chạy, MySQL thực thi với quyền của definer theo cơ chế stored object security. Người tạo trigger cần quyền TRIGGER trên bảng và các quyền cần thiết cho thao tác trong thân trigger.

Vận hành an toàn:
- Dùng definer riêng có quyền tối thiểu.
- Không dùng root làm definer.
- Kiểm tra definer còn tồn tại sau migration/restore.
- Kiểm tra quyền trên các bảng audit hoặc bảng phụ mà trigger truy cập.
- Rà soát SHOW CREATE TRIGGER khi điều tra quyền.
- Không cấp quyền sửa trigger cho tài khoản ứng dụng thông thường.

Ví dụ xem trigger:

~~~sql
SHOW TRIGGERS
FROM app_db
LIKE 'orders';
~~~

~~~sql
SHOW CREATE TRIGGER app_db.ai_orders_audit;
~~~

Có thể xem metadata:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_STATEMENT,
    DEFINER
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION;
~~~

## 16. Gọi trigger từ ứng dụng: transaction contract

Ứng dụng không gọi trigger trực tiếp. Nó thực thi INSERT/UPDATE/DELETE trên bảng; MySQL tự chạy trigger. Vì vậy, transaction contract của ứng dụng phải tính cả các thay đổi phụ do trigger tạo ra.

Ví dụ JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO orders(customer_id, status, total_amount) VALUES (?, ?, ?)")) {
        ps.setLong(1, customerId);
        ps.setString(2, "OPEN");
        ps.setBigDecimal(3, totalAmount);
        ps.executeUpdate();

        // Trigger ghi order_audit trong cùng transaction.
        connection.commit();
    } catch (SQLException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Nếu trigger phát lỗi, executeUpdate ném SQLException. Ứng dụng rollback transaction để bảo đảm các statement trước đó trong cùng nghiệp vụ cũng được hoàn tác nếu contract yêu cầu.

Nếu chỉ có một INSERT và autocommit bật, statement cùng trigger được commit hoặc rollback như một đơn vị. Nếu connection đang tham gia transaction lớn hơn, lỗi trigger không tự quyết định toàn bộ transaction phải rollback.

### 16.1. Không để connection pool giữ transaction lỗi

Sau exception:
- Xác định transaction còn hoạt động hay không.
- Rollback nếu caller sở hữu transaction và nghiệp vụ thất bại.
- Khôi phục autocommit/isolation nếu ứng dụng đã thay đổi.
- Chỉ trả connection về pool sau khi trạng thái được làm sạch theo quy tắc pool.

Đừng giả định mọi trigger error đều tự rollback toàn transaction. Deadlock và một số lỗi đặc biệt có hành vi khác statement rollback thông thường.

## 17. Ghi outbox thay vì side effect bên ngoài trigger

Nếu cần phát sự kiện khi đơn hàng được tạo, trigger có thể ghi một outbox row transactional:

~~~sql
CREATE TABLE event_outbox (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    aggregate_type VARCHAR(40) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (event_id),
    KEY idx_outbox_unpublished (published_at, event_id)
) ENGINE = InnoDB;
~~~

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_outbox
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO event_outbox (
        aggregate_type,
        aggregate_id,
        event_type,
        payload,
        created_at
    )
    VALUES (
        'ORDER',
        NEW.order_id,
        'ORDER_CREATED',
        JSON_OBJECT(
            'orderId', NEW.order_id,
            'customerId', NEW.customer_id,
            'totalAmount', NEW.total_amount
        ),
        NOW(6)
    );
END//

DELIMITER ;
~~~

Khi INSERT orders commit, outbox row cũng commit. Nếu transaction rollback, cả hai đều không tồn tại. Một worker bên ngoài đọc outbox sau commit và gửi message.

Worker cần idempotency vì có thể gửi lại khi crash giữa lúc gửi và đánh dấu published. Dùng event_id làm khóa idempotency ở consumer hoặc hệ thống nhận. Trigger chỉ ghi dữ liệu nội bộ, không gọi dịch vụ ngoài.

## 18. Các lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| AFTER trigger nghĩa là dữ liệu đã commit | AFTER chỉ là thời điểm sau thao tác hàng, trước COMMIT | Hiểu trigger chạy trong statement/transaction của caller |
| Trigger có transaction riêng | Trigger không thể START/COMMIT/ROLLBACK | Caller sở hữu transaction |
| Lỗi trigger chỉ rollback phần audit | Với InnoDB, toàn statement rollback | Thiết kế theo statement atomicity |
| Lỗi trigger luôn rollback toàn transaction | Lỗi statement thông thường không nhất thiết rollback transaction | Caller quyết định ROLLBACK toàn nghiệp vụ |
| CONTINUE handler nuốt lỗi audit | Handler cho statement tiếp tục | Chỉ bắt condition có thể bỏ qua; audit bắt buộc phải fail statement |
| Ghi log trong handler rồi RESIGNAL thì log luôn còn | Log InnoDB cùng transaction có thể rollback | Dùng application log hoặc kênh riêng nếu cần log bền vững |
| MyISAM audit rollback cùng InnoDB | MyISAM không transactional | Dùng InnoDB cho bảng audit |
| Trigger sửa lại bảng đã kích hoạt nó | Giới hạn mutating table, thường lỗi 1442 | Gán NEW trong BEFORE hoặc chuyển logic ra ngoài |
| Một INSERT nhiều hàng cho phép giữ hàng hợp lệ trước hàng lỗi | Statement InnoDB là đơn vị atomic | Tách statement hoặc xử lý từng hàng có chủ đích |
| Trigger chạy khi FK cascade xóa hàng con | FK cascade không kích hoạt trigger | Thiết kế audit riêng cho cascade |
| TRUNCATE chạy DELETE trigger | TRUNCATE là DDL, không xóa từng hàng theo DELETE | Dùng DELETE nếu cần trigger theo hàng |
| CREATE TRIGGER có thể rollback | DDL gây implicit commit | Triển khai trigger qua migration riêng |
| Trigger ghi email rồi transaction rollback sẽ thu hồi email | Side effect ngoài DB không tham gia transaction | Dùng transactional outbox |
| Trigger làm replication ghi audit hai lần | Nhầm row-based và statement-based behavior | Kiểm tra binlog format và topology |
| Mỗi trigger chỉ chạy một lần cho statement | Trigger MySQL là FOR EACH ROW | Ước lượng chi phí theo số hàng bị tác động |

## 19. Quy trình thiết kế trigger có xử lý lỗi an toàn

1. Xác định sự kiện INSERT, UPDATE hay DELETE và thời điểm BEFORE/AFTER.
2. Xác định trigger chạy một lần cho mỗi hàng và ước lượng số hàng tối đa của statement.
3. Dùng constraint cho quy tắc dữ liệu có thể biểu diễn bằng PRIMARY KEY, UNIQUE, CHECK hoặc FOREIGN KEY.
4. Dùng BEFORE để validate hoặc chuẩn hóa NEW khi phù hợp.
5. Dùng AFTER cho audit hoặc bảng phụ cần phản ánh hàng đã được ghi.
6. Bảo đảm bảng gốc và bảng phụ quan trọng đều dùng InnoDB.
7. Không dùng START TRANSACTION, COMMIT hoặc ROLLBACK trong trigger.
8. Xác định lỗi nào phải làm statement thất bại; dùng SIGNAL với SQLSTATE/message ổn định.
9. Chỉ dùng CONTINUE handler cho condition thực sự có thể bỏ qua.
10. Dùng RESIGNAL khi lỗi cần truyền tới caller.
11. Không sửa bảng đang được statement kích hoạt trigger sử dụng.
12. Tạo index cho mọi lookup trong trigger.
13. Tránh side effect ngoài database; dùng outbox sau commit.
14. Đánh giá deadlock và thứ tự khóa giữa bảng gốc/bảng phụ.
15. Kiểm tra binlog_format và hành vi trên replica.
16. Kiểm tra DEFINER và quyền tối thiểu.
17. Triển khai CREATE/DROP TRIGGER như migration DDL riêng.
18. Kiểm thử statement rollback, transaction rollback và multi-row failure.
19. Kiểm tra JDBC/caller rollback và connection pool cleanup.
20. Theo dõi độ trễ statement, lock wait và số lần trigger được kích hoạt.

## 20. Bài tập thực hành

### Bài 1: Trigger và autocommit

Tạo orders và order_audit đều dùng InnoDB. Tạo AFTER INSERT trigger ghi audit. Chạy INSERT với autocommit bật rồi kiểm tra hai bảng. Xác nhận hai thay đổi được commit cùng nhau.

### Bài 2: Rollback transaction

Mở START TRANSACTION, INSERT một order, kiểm tra audit rồi ROLLBACK. Xác nhận cả hàng orders và order_audit biến mất.

### Bài 3: BEFORE trigger phát SIGNAL

Tạo BEFORE INSERT trigger từ chối total_amount <= 0. Thử INSERT sai và xác nhận hàng không tồn tại. Đọc SQLSTATE và message ở client.

### Bài 4: AFTER trigger phát lỗi

Trong AFTER INSERT trigger, ghi audit rồi phát SIGNAL khi status = 'REJECTED'. Thử INSERT và kiểm tra cả hàng gốc lẫn audit đều không tồn tại với InnoDB.

### Bài 5: Statement rollback và transaction rollback

Mở transaction, UPDATE một bảng trước. Sau đó chạy INSERT kích hoạt trigger lỗi. Kiểm tra UPDATE trước còn trong transaction; cuối cùng ROLLBACK và xác nhận UPDATE cũng biến mất.

### Bài 6: Multi-row INSERT

Gửi một INSERT nhiều hàng, trong đó một hàng làm trigger phát lỗi. Xác nhận toàn statement bị rollback với InnoDB. Lặp lại bằng các INSERT riêng để so sánh phạm vi atomicity.

### Bài 7: Handler và RESIGNAL

Thêm EXIT handler trong trigger để RESIGNAL lỗi. Kiểm tra caller vẫn nhận lỗi. Thử CONTINUE handler có chủ đích cho một condition tùy chọn và đánh giá liệu việc bỏ qua có phá tính nhất quán không.

### Bài 8: InnoDB và MyISAM

Cho trigger ghi audit vào MyISAM rồi phát lỗi. Quan sát sự khác nhau giữa thay đổi bảng gốc InnoDB và audit MyISAM. Chuyển audit sang InnoDB và chạy lại.

### Bài 9: Mutating table

Tạo trigger cố UPDATE lại bảng đã kích hoạt trigger. Quan sát lỗi 1442. Viết lại bằng cách gán NEW trong BEFORE trigger.

### Bài 10: Foreign key cascade và TRUNCATE

Tạo quan hệ cha-con với ON DELETE CASCADE và trigger DELETE trên bảng con. Xóa hàng cha rồi kiểm tra trigger con có chạy không. Thử TRUNCATE và so sánh với DELETE.

### Bài 11: Deadlock qua trigger

Dùng hai session cập nhật bảng gốc và bảng audit theo thứ tự ngược nhau. Quan sát deadlock, xác định transaction victim và thiết kế thứ tự truy cập nhất quán.

### Bài 12: Outbox

Tạo trigger ghi event_outbox khi đơn hàng mới được thêm. Rollback transaction và xác nhận outbox không còn. Commit transaction rồi dùng worker giả lập đọc và đánh dấu event đã gửi.

### Bài 13: Replication

Trên môi trường lab, kiểm tra binlog_format. So sánh hành vi trigger với statement-based và row-based replication. Xác nhận audit không bị ghi lặp trên replica.

## 21. Checklist trước khi triển khai

- [ ] Đã xác định trigger BEFORE/AFTER và INSERT/UPDATE/DELETE.
- [ ] Đã hiểu trigger là FOR EACH ROW, không phải statement-level.
- [ ] Đã xác định trigger tham gia transaction của statement caller.
- [ ] Không có START TRANSACTION, COMMIT hoặc ROLLBACK trong trigger.
- [ ] Đã phân biệt AFTER với COMMIT.
- [ ] Đã kiểm thử lỗi ở cả BEFORE và AFTER.
- [ ] Đã xác nhận statement rollback trên InnoDB.
- [ ] Đã phân biệt statement rollback với transaction rollback.
- [ ] Đã xác định caller hay procedure sở hữu transaction.
- [ ] Đã kiểm tra multi-row statement và lỗi ở một hàng.
- [ ] Đã bảo đảm các bảng cần atomicity đều dùng InnoDB.
- [ ] Không ghi audit bắt buộc vào engine không transactional.
- [ ] Handler không nuốt lỗi bắt buộc.
- [ ] SIGNAL dùng SQLSTATE và message có chủ đích.
- [ ] RESIGNAL được dùng khi caller cần nhận lỗi.
- [ ] Không sửa bảng đang được statement kích hoạt trigger sử dụng.
- [ ] Đã kiểm tra FK cascade và TRUNCATE không kích hoạt trigger như DELETE thường.
- [ ] Đã tạo index cho lookup trong trigger.
- [ ] Đã đánh giá deadlock và lock wait.
- [ ] Không thực hiện side effect ngoài DB trực tiếp trong trigger.
- [ ] Đã cân nhắc transactional outbox.
- [ ] Đã kiểm tra binlog format và replication.
- [ ] Đã kiểm tra DEFINER và quyền tối thiểu.
- [ ] CREATE/DROP TRIGGER được triển khai qua migration riêng.
- [ ] Đã kiểm thử caller/JDBC rollback và connection pool cleanup.

## 22. Kết luận

Trigger chạy như một phần của statement INSERT, UPDATE hoặc DELETE đã kích hoạt nó. Trigger không có transaction độc lập và không thể tự COMMIT hoặc ROLLBACK. Với InnoDB, nếu trigger phát sinh lỗi không được xử lý, toàn bộ statement thất bại và các thay đổi transactional do statement cùng trigger thực hiện được hoàn tác. Nếu statement nằm trong transaction lớn hơn, các statement thành công trước đó vẫn còn cho đến khi caller quyết định COMMIT hoặc ROLLBACK toàn nghiệp vụ.

Thiết kế trigger an toàn cần thống nhất storage engine, giới hạn side effect, dùng SIGNAL để từ chối dữ liệu sai và dùng handler có chủ đích. Không nuốt lỗi bắt buộc, không ghi audit transactional vào MyISAM, không gửi email/API từ trigger và không cập nhật lại bảng đang được statement sử dụng. Với tác dụng phụ cần thực hiện sau commit, hãy ghi outbox row trong cùng transaction rồi xử lý ở worker. Triển khai CREATE/DROP TRIGGER như migration riêng vì DDL có implicit commit.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html)
- [MySQL 8.4 Reference Manual – Trigger Restrictions](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html#trigger-restrictions)
- [MySQL 8.4 Reference Manual – CREATE TRIGGER Statement](https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html)
- [MySQL 8.4 Reference Manual – SIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/signal.html)
- [MySQL 8.4 Reference Manual – Condition Handling](https://dev.mysql.com/doc/refman/8.4/en/condition-handling.html)
- [MySQL 8.4 Reference Manual – GET DIAGNOSTICS](https://dev.mysql.com/doc/refman/8.4/en/get-diagnostics.html)
- [MySQL 8.4 Reference Manual – RESIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/resignal.html)
- [MySQL 8.4 Reference Manual – InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html)
- [MySQL 8.4 Reference Manual – InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual – Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual – Replication Formats](https://dev.mysql.com/doc/refman/8.4/en/replication-formats.html)
- [MySQL 8.4 Reference Manual – Stored Object Access Control](https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html)

