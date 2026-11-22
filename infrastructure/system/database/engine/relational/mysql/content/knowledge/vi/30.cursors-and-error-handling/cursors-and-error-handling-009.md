# Xử lý lỗi từng câu lệnh so với hoàn tác toàn nghiệp vụ

Khi một câu lệnh SQL thất bại trong MySQL, có hai phạm vi hoàn tác cần phân biệt:

- **Statement rollback**: InnoDB hoàn tác các thay đổi của chính câu lệnh thất bại. Các câu lệnh thành công trước đó trong cùng transaction vẫn còn hiệu lực chưa commit.
- **Transaction rollback**: MySQL/InnoDB hoàn tác toàn bộ thay đổi transactional kể từ đầu transaction, hoặc kể từ SAVEPOINT nếu dùng \`ROLLBACK TO SAVEPOINT\`.

Hai phạm vi này quyết định cách viết stored procedure, handler và quy trình xử lý dữ liệu theo lô. Một handler \`CONTINUE\` có thể cho phép bỏ qua một lỗi của từng câu lệnh và tiếp tục xử lý; một handler \`EXIT\` có thể dừng block. Nhưng handler không tự quyết định transaction phải commit hay rollback. Muốn hoàn tác toàn bộ nghiệp vụ, code phải có ranh giới transaction rõ ràng và thực hiện ROLLBACK đúng nơi.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: thiết kế xử lý lỗi trong stored program, phân biệt lỗi câu lệnh với lỗi toàn transaction, dùng \`DECLARE HANDLER\`, \`RESIGNAL\`, \`GET DIAGNOSTICS\` và \`SAVEPOINT\`, đồng thời bảo đảm thao tác nhiều bảng có kết quả nhất quán.

## 1. Hai cấp độ atomicity

Atomicity có thể được nhìn ở hai phạm vi.

### 1.1. Atomicity của một statement

Với bảng InnoDB, một câu lệnh DML là một đơn vị thực thi nguyên tử. Nếu statement thất bại do vi phạm constraint hoặc lỗi SQL, InnoDB thường hoàn tác những thay đổi do chính statement đó tạo ra.

Ví dụ:

~~~sql
CREATE TABLE account_statement_demo (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account_statement_demo (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);
~~~

Bắt đầu transaction và chạy hai statement:

~~~sql
START TRANSACTION;

UPDATE account_statement_demo
SET balance = balance - 100
WHERE account_id = 1;

-- Giả sử account_id=2 đã tồn tại, INSERT này thất bại.
INSERT INTO account_statement_demo (account_id, balance)
VALUES (2, 999.00);
~~~

Statement INSERT bị lỗi duplicate primary key. Với InnoDB, các thay đổi của INSERT thất bại được hoàn tác. UPDATE trước đó vẫn còn trong transaction hiện tại, chưa bị hoàn tác chỉ vì INSERT thất bại.

Có thể kiểm tra trong cùng session:

~~~sql
SELECT *
FROM account_statement_demo
ORDER BY account_id;

SELECT @@session.in_transaction;
~~~

Nếu sau đó gọi COMMIT, UPDATE đầu tiên vẫn được commit. Nếu gọi ROLLBACK, UPDATE đầu tiên mới bị hoàn tác.

### 1.2. Atomicity của toàn transaction

Transaction gom nhiều statement thành một đơn vị nghiệp vụ:

~~~sql
START TRANSACTION;

UPDATE account_statement_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_statement_demo
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Nếu bước thứ hai thất bại và ứng dụng quyết định toàn nghiệp vụ không thể hoàn thành, phải ROLLBACK transaction:

~~~sql
ROLLBACK;
~~~

Với InnoDB, ROLLBACK hoàn tác các thay đổi transactional chưa commit của toàn transaction. Đây là phạm vi thường cần cho chuyển tiền, đặt đơn, trừ tồn kho kèm ghi nhận giao dịch hoặc cập nhật nhiều bảng có quan hệ nghiệp vụ.

### 1.3. So sánh nhanh

| Phạm vi | Cái gì được hoàn tác? | Transaction còn hoạt động? |
|---|---|---|
| Statement rollback | Thay đổi của statement thất bại | Thường còn, nếu lỗi không khiến InnoDB rollback toàn transaction |
| ROLLBACK TO SAVEPOINT | Thay đổi sau savepoint trong transaction | Có |
| ROLLBACK | Tất cả thay đổi transactional chưa commit trong transaction | Không; transaction kết thúc |
| Deadlock victim rollback | Toàn bộ transaction bị InnoDB chọn làm nạn nhân | Không; phải chạy lại transaction nếu phù hợp |

Không suy luận rằng “có lỗi SQL” luôn đồng nghĩa toàn transaction đã bị rollback. Loại lỗi và cấu hình InnoDB quyết định phạm vi xử lý.

## 2. Autocommit ảnh hưởng đến phạm vi quan sát

### 2.1. autocommit = 1

Mặc định MySQL bật autocommit. Một statement độc lập thành công thường tự commit khi hoàn tất:

~~~sql
UPDATE account_statement_demo
SET balance = balance + 10
WHERE account_id = 1;
~~~

Nếu statement thất bại, statement đó không commit các thay đổi của nó. Vì không có các statement trước nằm trong cùng transaction độc lập, thường không có phần thay đổi nghiệp vụ trước đó để giữ lại.

### 2.2. Transaction tường minh

Ngay cả khi autocommit đang bật, có thể gom nhiều statement:

~~~sql
START TRANSACTION;

UPDATE account_statement_demo
SET balance = balance - 10
WHERE account_id = 1;

UPDATE account_statement_demo
SET balance = balance + 10
WHERE account_id = 2;

COMMIT;
~~~

Nếu statement thứ hai lỗi, transaction vẫn có thể còn mở sau statement rollback thông thường. Caller phải quyết định tiếp tục, sửa lỗi, dùng savepoint hoặc ROLLBACK toàn transaction.

### 2.3. autocommit = 0

Khi tắt autocommit, các statement transactional tiếp theo thuộc transaction cho tới COMMIT hoặc ROLLBACK:

~~~sql
SET autocommit = 0;

UPDATE account_statement_demo
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;
~~~

Tắt autocommit không tự tạo chính sách hoàn tác toàn nghiệp vụ. Ứng dụng vẫn phải xử lý lỗi và kết thúc transaction đúng lúc. Transaction bị bỏ quên có thể giữ khóa và read view quá lâu.

## 3. Các nhóm condition trong MySQL

Stored program có thể xử lý condition bằng handler. MySQL hỗ trợ các lớp condition thường gặp:

| Condition | Ý nghĩa |
|---|---|
| \`SQLWARNING\` | SQLSTATE class 01: cảnh báo |
| \`NOT FOUND\` | SQLSTATE class 02: không tìm thấy hàng hoặc hết dữ liệu cursor |
| \`SQLEXCEPTION\` | Các SQLSTATE class khác ngoài 00, 01 và 02 |
| SQLSTATE cụ thể | Ví dụ \`'45000'\` cho lỗi do ứng dụng chủ động phát ra |
| MySQL error code | Ví dụ mã lỗi cụ thể như duplicate key |

Một handler có thể bắt một condition cụ thể hoặc cả một lớp condition.

### 3.1. Duplicate key

Ví dụ lỗi duplicate primary key thường có MySQL error 1062 và SQLSTATE \`23000\`. Nếu không có handler phù hợp, lỗi được trả về caller.

Có thể khai báo handler theo mã lỗi hoặc SQLSTATE:

~~~sql
DECLARE CONTINUE HANDLER FOR 1062
    SET v_duplicate_found = TRUE;
~~~

Hoặc:

~~~sql
DECLARE CONTINUE HANDLER FOR SQLSTATE '23000'
    SET v_constraint_error = TRUE;
~~~

SQLSTATE class 23 bao gồm nhiều lỗi integrity constraint, không chỉ duplicate key. Nếu chỉ muốn xử lý duplicate, bắt mã lỗi 1062 cụ thể thường rõ ràng hơn.

### 3.2. NOT FOUND

\`NOT FOUND\` thường xuất hiện khi:
- \`FETCH\` cursor đã đi qua hàng cuối.
- \`SELECT ... INTO\` không tìm thấy hàng.

Ví dụ:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Trong vòng lặp cursor, handler này thường đặt cờ để vòng lặp kết thúc. Cần chú ý phạm vi block vì cùng handler cũng có thể bắt một SELECT ... INTO không có hàng nếu câu lệnh đó nằm trong cùng scope.

### 3.3. SQLEXCEPTION

\`SQLEXCEPTION\` bắt các lỗi SQL không thuộc nhóm SQLWARNING và NOT FOUND. Đây là condition thường dùng cho handler rollback toàn transaction:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
~~~

Handler trên rollback transaction hiện tại rồi phát lại lỗi cho caller. Chỉ dùng mẫu này khi procedure thực sự sở hữu transaction; nếu transaction thuộc caller, ROLLBACK có thể hủy cả công việc trước đó của caller.

### 3.4. SIGNAL tạo lỗi nghiệp vụ

Có thể chủ động phát condition:

~~~sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Insufficient balance';
~~~

SQLSTATE class 45 là exception do ứng dụng định nghĩa. Nó cho phép báo lỗi nghiệp vụ như số lượng không hợp lệ, tài khoản không tồn tại hoặc trạng thái đơn hàng không cho phép chuyển bước.

Nếu lỗi được phát trong một statement thuộc transaction InnoDB, statement thất bại; phạm vi rollback rộng hơn phụ thuộc handler và transaction contract.

## 4. DECLARE HANDLER: CONTINUE và EXIT

Cú pháp:

~~~sql
DECLARE { CONTINUE | EXIT } HANDLER
FOR condition_value
statement;
~~~

MySQL có hai loại handler thông dụng:

- \`CONTINUE\`: xử lý condition rồi tiếp tục thực thi ở statement ngay sau statement gây condition.
- \`EXIT\`: xử lý condition rồi thoát khỏi compound block (\`BEGIN ... END\`) nơi handler được khai báo.

MySQL không hỗ trợ handler kiểu \`UNDO\`.

### 4.1. CONTINUE

Ví dụ đánh dấu duplicate và tiếp tục:

~~~sql
DELIMITER //

CREATE PROCEDURE insert_customer_if_new(
    IN p_customer_id BIGINT UNSIGNED,
    IN p_email VARCHAR(254),
    OUT p_inserted BOOLEAN
)
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    SET p_inserted = FALSE;

    INSERT INTO customer (customer_id, email)
    VALUES (p_customer_id, p_email);

    IF v_duplicate = FALSE THEN
        SET p_inserted = TRUE;
    END IF;
END//

DELIMITER ;
~~~

Khi INSERT gặp duplicate key:
1. InnoDB hoàn tác statement INSERT thất bại.
2. Handler CONTINUE đặt cờ.
3. Thực thi tiếp sau INSERT.
4. Procedure trả \`p_inserted = FALSE\`.

Handler không rollback transaction hiện tại. Nếu có statement thành công trước đó trong transaction, các thay đổi đó vẫn còn.

Ví dụ này chỉ minh họa điều khiển luồng. Nếu bảng có nhiều unique key, cần phân biệt duplicate nào đã xảy ra và có thể cần bắt lỗi cụ thể hơn hoặc dùng upsert có chủ đích.

### 4.2. EXIT

Ví dụ:

~~~sql
DELIMITER //

CREATE PROCEDURE validate_order(
    IN p_quantity INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET @routine_failed = TRUE;
        RESIGNAL;
    END;

    IF p_quantity <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be positive';
    END IF;

    INSERT INTO order_validation_log(quantity)
    VALUES (p_quantity);
END//

DELIMITER ;
~~~

Khi SIGNAL phát lỗi:
- Handler EXIT được gọi.
- Handler thực thi RESIGNAL.
- Block chứa handler kết thúc do condition được phát lại.
- Caller nhận lỗi.

Handler EXIT không tự động rollback transaction. Nếu routine đã thực hiện các statement transactional trước lỗi, caller vẫn cần quyết định transaction sẽ được commit hay rollback, trừ khi handler chủ động làm điều đó.

### 4.3. Phạm vi block quyết định nơi EXIT dừng

Handler khai báo trong block lồng nhau chỉ EXIT khỏi block đó:

~~~sql
BEGIN
    -- block ngoài
    BEGIN
        DECLARE EXIT HANDLER FOR SQLEXCEPTION
            SET v_failed = TRUE;

        INSERT INTO target_table(id) VALUES (1);
    END;

    -- Nếu handler xử lý lỗi bên trong, block ngoài có thể tiếp tục.
    SET v_after_inner_block = TRUE;
END;
~~~

Dùng block lồng nhau để cô lập lỗi từng hàng hoặc từng bước. Đừng giả định EXIT luôn thoát khỏi toàn bộ procedure; nó thoát khỏi block chứa handler.

## 5. Handler không tự quyết định rollback

Đây là nguyên tắc quan trọng nhất của bài học.

~~~sql
DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    SET v_error_seen = TRUE;
~~~

Handler trên chỉ thay đổi biến. Nó không gọi ROLLBACK.

Tương tự:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    SET v_error_seen = TRUE;
END;
~~~

Handler EXIT dừng block nhưng transaction vẫn có thể còn hoạt động. Nếu procedure kết thúc mà không COMMIT/ROLLBACK, connection có thể giữ transaction mở.

Một handler chỉ điều khiển luồng và thực hiện các statement mà người viết đặt trong thân handler. Muốn rollback phải viết rõ \`ROLLBACK\` hoặc \`ROLLBACK TO SAVEPOINT\`.

### 5.1. Ba chính sách lỗi khác nhau

| Chính sách | Handler/transaction | Kết quả |
|---|---|---|
| Ghi nhận lỗi statement và tiếp tục | CONTINUE; không rollback toàn transaction | Statement lỗi bị rollback; các bước khác tiếp tục |
| Dừng routine nhưng để caller quyết định | EXIT hoặc RESIGNAL; không tự rollback | Routine dừng; transaction thuộc caller vẫn được caller quản lý |
| Hoàn tác toàn nghiệp vụ | EXIT handler gọi ROLLBACK rồi RESIGNAL | Toàn bộ thay đổi InnoDB chưa commit trong transaction bị hoàn tác |

Hãy chọn chính sách theo nghiệp vụ. Ví dụ nhập dữ liệu theo từng dòng có thể chấp nhận bỏ qua một dòng sai; chuyển tiền thường phải rollback toàn bộ nếu một bước thất bại.

## 6. Statement rollback khi xử lý dữ liệu theo từng dòng

Giả sử có bảng staging và bảng đích:

~~~sql
CREATE TABLE import_stage (
    source_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE imported_customer (
    source_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE import_error_log (
    source_id BIGINT UNSIGNED NOT NULL,
    mysql_errno INT NOT NULL,
    returned_sqlstate CHAR(5) NOT NULL,
    message_text VARCHAR(1024) NOT NULL,
    logged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE = InnoDB;
~~~

Nếu một dòng có email đã tồn tại, INSERT của dòng đó có thể thất bại vì unique key. Trong một quy trình xử lý từng dòng:
- Dòng hợp lệ được ghi vào imported_customer.
- Dòng lỗi được ghi thông tin vào import_error_log.
- Các dòng tiếp theo vẫn được xử lý.
- Cuối batch, các dòng thành công có thể được COMMIT cùng nhau.

Đây là chính sách “bỏ qua lỗi ở cấp dòng/statement” chứ không phải rollback toàn batch.

### 6.1. Cursor với handler cục bộ cho từng INSERT

~~~sql
DELIMITER //

CREATE PROCEDURE import_customers_continue_on_row_error()
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_source_id BIGINT UNSIGNED;
    DECLARE v_email VARCHAR(254);
    DECLARE v_display_name VARCHAR(150);
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message VARCHAR(1024);

    DECLARE cur_import CURSOR FOR
        SELECT source_id, email, display_name
        FROM import_stage
        ORDER BY source_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    OPEN cur_import;

    read_loop: LOOP
        FETCH cur_import
        INTO v_source_id, v_email, v_display_name;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        BEGIN
            DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
            BEGIN
                GET DIAGNOSTICS CONDITION 1
                    v_sqlstate = RETURNED_SQLSTATE,
                    v_errno = MYSQL_ERRNO,
                    v_message = MESSAGE_TEXT;

                INSERT INTO import_error_log (
                    source_id,
                    mysql_errno,
                    returned_sqlstate,
                    message_text
                )
                VALUES (
                    v_source_id,
                    v_errno,
                    v_sqlstate,
                    v_message
                );
            END;

            INSERT INTO imported_customer (
                source_id,
                email,
                display_name
            )
            VALUES (
                v_source_id,
                v_email,
                v_display_name
            );
        END;
    END LOOP;

    CLOSE cur_import;
    COMMIT;
END//

DELIMITER ;
~~~

Cách hoạt động:

1. Procedure mở transaction để batch có một điểm commit cuối.
2. Cursor đọc từng dòng staging.
3. Mỗi INSERT được đặt trong một block con có CONTINUE handler riêng.
4. Nếu INSERT thành công, vòng lặp chuyển sang dòng tiếp theo.
5. Nếu INSERT thất bại, InnoDB rollback statement INSERT đó.
6. Handler đọc diagnostics và ghi lỗi vào import_error_log.
7. Handler CONTINUE kết thúc, vòng lặp tiếp tục với dòng tiếp theo.
8. Nếu có lỗi không được handler cục bộ xử lý, EXIT handler bên ngoài rollback toàn transaction và RESIGNAL.
9. Nếu mọi bước ngoài lỗi từng dòng hoàn tất, procedure COMMIT các dòng thành công và các log lỗi.

**Điều kiện của ví dụ:** tất cả ba bảng phải dùng InnoDB; procedure sở hữu transaction và chỉ được gọi khi caller không có transaction đang mở. \`START TRANSACTION\` trong MySQL kết thúc transaction đang hoạt động trước đó, nên nếu caller đang có công việc chưa commit, procedure này có thể commit công việc đó ngoài ý muốn. Trong ứng dụng thực tế, chọn rõ transaction contract như mục 10.

Nếu INSERT vào import_error_log cũng thất bại, lỗi phát sinh trong handler cục bộ không được handler đó tự bắt lại. Nó có thể đi tới handler EXIT bên ngoài, khiến toàn batch rollback. Đây là lựa chọn an toàn hơn việc âm thầm bỏ mất cả dữ liệu lẫn dấu vết lỗi.

### 6.2. Vì sao dùng block lồng nhau?

Handler được khai báo trong block con chỉ áp dụng cho statement thuộc block đó. Nhờ vậy:
- Lỗi của INSERT một dòng có thể được xử lý cục bộ.
- Lỗi khi FETCH cursor vẫn được xử lý theo handler NOT FOUND ở block ngoài.
- Lỗi ngoài phạm vi từng dòng có thể kích hoạt EXIT handler cấp batch.

Đặt một CONTINUE handler cho SQLEXCEPTION ở toàn procedure có thể vô tình nuốt cả lỗi nghiêm trọng như lỗi mở cursor, lỗi ghi log hoặc lỗi cập nhật trạng thái batch. Scope nhỏ giúp chính sách rõ ràng hơn.

## 7. Hoàn tác toàn nghiệp vụ bằng EXIT handler

Với nghiệp vụ chuyển tiền, không thể bỏ qua một bước thất bại rồi vẫn commit bước trước. Nếu trừ tiền thành công nhưng cộng tiền vào tài khoản đích thất bại, toàn bộ transaction phải rollback.

Ví dụ procedure sở hữu transaction:

~~~sql
DELIMITER //

CREATE PROCEDURE transfer_funds(
    IN p_from_account BIGINT UNSIGNED,
    IN p_to_account BIGINT UNSIGNED,
    IN p_amount DECIMAL(12, 2)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_from_account = p_to_account THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source and destination must differ';
    END IF;

    IF p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transfer amount must be positive';
    END IF;

    START TRANSACTION;

    UPDATE account
    SET balance = balance - p_amount
    WHERE account_id = p_from_account
      AND balance >= p_amount;

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source account missing or insufficient balance';
    END IF;

    UPDATE account
    SET balance = balance + p_amount
    WHERE account_id = p_to_account;

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Destination account not found';
    END IF;

    INSERT INTO transfer_audit (
        from_account,
        to_account,
        amount,
        created_at
    )
    VALUES (
        p_from_account,
        p_to_account,
        p_amount,
        NOW(6)
    );

    COMMIT;
END//

DELIMITER ;
~~~

Giải thích:
- Procedure bắt đầu transaction trước các thao tác ghi.
- UPDATE nguồn trừ tiền có điều kiện balance đủ.
- Nếu không cập nhật đúng một hàng, SIGNAL phát lỗi nghiệp vụ.
- UPDATE đích cộng tiền.
- Nếu tài khoản đích không tồn tại, SIGNAL.
- Nếu INSERT audit thất bại, lỗi cũng đi vào EXIT handler.
- EXIT handler ROLLBACK toàn transaction rồi RESIGNAL để caller biết thao tác thất bại.

Nếu tất cả bảng là InnoDB và không có tác dụng phụ ngoài transaction, hoặc tất cả thay đổi được rollback cùng transaction, số dư nguồn, số dư đích và audit sẽ cùng thành công hoặc cùng thất bại.

### 7.1. Hợp đồng procedure sở hữu transaction

Ví dụ trên dùng \`START TRANSACTION\`, \`COMMIT\` và \`ROLLBACK\`. Nó giả định procedure sở hữu transaction. Không gọi procedure này khi caller đang có transaction chưa commit cần giữ lại, vì START TRANSACTION mới có thể kết thúc transaction đang hoạt động.

Tài liệu ứng dụng nên ghi rõ:
- Caller phải gọi trên connection không có transaction đang mở.
- Procedure tự mở và kết thúc transaction.
- Lỗi được RESIGNAL để caller nhận biết.
- Caller không gọi COMMIT/ROLLBACK để thay đổi kết quả đã được procedure commit.

## 8. Transaction caller-owned: procedure chỉ báo lỗi

Một thiết kế khác là để ứng dụng sở hữu transaction. Procedure chỉ thực hiện các statement và phát lỗi; không tự START TRANSACTION, COMMIT hoặc ROLLBACK.

Ví dụ:

~~~sql
DELIMITER //

CREATE PROCEDURE apply_order_changes(
    IN p_order_id BIGINT UNSIGNED
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM orders
        WHERE order_id = p_order_id
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order does not exist';
    END IF;

    UPDATE orders
    SET status = 'PROCESSING'
    WHERE order_id = p_order_id;

    INSERT INTO order_audit(order_id, event_name, created_at)
    VALUES (p_order_id, 'PROCESSING', NOW(6));
END//

DELIMITER ;
~~~

Ứng dụng:

~~~sql
START TRANSACTION;

CALL apply_order_changes(1001);

-- Chỉ COMMIT khi toàn bộ nghiệp vụ phía caller hoàn tất.
COMMIT;
~~~

Nếu CALL báo lỗi, caller bắt exception và quyết định ROLLBACK:

~~~sql
ROLLBACK;
~~~

Nếu procedure có handler CONTINUE và nuốt lỗi, caller có thể không biết thao tác đã thất bại. Vì vậy, với transaction caller-owned, procedure thường nên để lỗi truyền ra hoặc dùng EXIT handler với RESIGNAL nhưng không tự rollback transaction của caller.

### 8.1. Handler EXIT và RESIGNAL không nhất thiết rollback

Có thể ghi nhận hoặc bổ sung thông tin rồi phát lại lỗi:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    SET v_failed = TRUE;
    RESIGNAL;
END;
~~~

Không có ROLLBACK trong handler. Caller nhận lỗi và sở hữu quyết định transaction.

Đây là mẫu phù hợp khi một service layer điều phối nhiều procedure trong cùng transaction.

## 9. SAVEPOINT: hoàn tác một phần mà vẫn giữ transaction

SAVEPOINT tạo điểm đánh dấu trong transaction:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account
SET balance = balance + 20
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

-- Transaction vẫn còn hoạt động.
COMMIT;
~~~

Sau \`ROLLBACK TO SAVEPOINT after_debit\`:
- Thay đổi sau savepoint bị hoàn tác.
- Thay đổi trước savepoint vẫn còn trong transaction.
- Transaction không kết thúc.
- Có thể tiếp tục chạy statement và COMMIT/ROLLBACK sau đó.

### 9.1. Dùng savepoint cho từng đơn vị công việc

Có thể dùng savepoint trong batch khi muốn rollback phần xử lý một nhóm nhưng vẫn giữ các nhóm trước:

~~~sql
START TRANSACTION;

SAVEPOINT batch_item_1;
-- Xử lý item 1.

SAVEPOINT batch_item_2;
-- Xử lý item 2.

-- Nếu item 2 lỗi:
ROLLBACK TO SAVEPOINT batch_item_2;

-- Tiếp tục item 3.
COMMIT;
~~~

Trong stored program, có thể đặt SAVEPOINT trước block xử lý và dùng handler để rollback về savepoint. Tuy nhiên, phải quản lý tên savepoint, scope và lỗi khi tạo/rollback savepoint. Savepoint chỉ có ý nghĩa khi đã có transaction đang hoạt động.

### 9.2. SAVEPOINT không phải transaction con

MySQL không hỗ trợ nested transaction theo cách một transaction con có COMMIT độc lập. Savepoint chỉ đánh dấu một vị trí trong transaction hiện tại.

- COMMIT kết thúc toàn transaction và xóa các savepoint.
- ROLLBACK toàn transaction xóa tất cả thay đổi và savepoint.
- ROLLBACK TO SAVEPOINT không kết thúc transaction.
- RELEASE SAVEPOINT xóa điểm đánh dấu nhưng không rollback dữ liệu.

Không dùng SAVEPOINT để tạo một phần công việc có thể commit độc lập khỏi transaction cha.

### 9.3. DDL và implicit commit

Nhiều DDL như ALTER TABLE, CREATE TABLE, DROP TABLE và TRUNCATE TABLE gây implicit commit. DDL có thể làm transaction và savepoint trước đó mất hiệu lực. Không dùng SAVEPOINT để mong rollback DDL.

## 10. Lỗi trong procedure: ai sở hữu transaction?

Một stored procedure có thể được thiết kế theo hai hợp đồng.

| Hợp đồng | Procedure | Caller |
|---|---|---|
| Procedure-owned | START TRANSACTION, COMMIT và ROLLBACK | Gọi trên connection không có transaction cần giữ; nhận lỗi nếu thất bại |
| Caller-owned | Không tự START/COMMIT/ROLLBACK | Mở transaction, gọi một hoặc nhiều procedure, quyết định COMMIT/ROLLBACK |

### 10.1. Không trộn hai hợp đồng

Một lỗi phổ biến là procedure tự START TRANSACTION và COMMIT, trong khi ứng dụng nghĩ nó đang kiểm soát transaction lớn hơn.

Ví dụ:
1. Ứng dụng START TRANSACTION.
2. Cập nhật bảng A.
3. Gọi procedure.
4. Procedure START TRANSACTION và COMMIT.
5. Transaction của ứng dụng có thể đã bị kết thúc trước đó.

Khi procedure commit, ứng dụng không thể rollback lại thay đổi trước procedure như dự định.

### 10.2. Function và trigger không quản lý transaction

Stored function và trigger có giới hạn khác procedure:
- Không được START TRANSACTION, COMMIT hoặc ROLLBACK.
- Chạy trong ngữ cảnh statement/transaction của caller.
- Lỗi trong function/trigger có thể làm statement gọi chúng thất bại.
- Thay đổi transactional do function/trigger thực hiện (nếu được phép) tham gia vào transaction của caller.

Vì vậy, không đặt transaction ownership vào function hoặc trigger. Dùng procedure hoặc tầng ứng dụng khi cần điều phối transaction nhiều bước.

## 11. Deadlock và lock wait timeout: hai phạm vi rollback khác nhau

Không phải mọi lỗi concurrency có cùng phạm vi rollback.

### 11.1. Deadlock

Khi InnoDB phát hiện deadlock, nó chọn một transaction làm nạn nhân và rollback toàn bộ transaction đó để phá vòng chờ.

Ứng dụng thường nhận lỗi deadlock (MySQL error 1213, SQLSTATE 40001). Cách xử lý:
1. Bắt lỗi.
2. Xem transaction đã bị rollback toàn bộ.
3. Retry toàn bộ transaction từ đầu nếu thao tác có thể retry an toàn.
4. Dùng backoff và giới hạn số lần retry.
5. Giữ thứ tự truy cập hàng nhất quán để giảm deadlock.

Không chỉ chạy lại statement cuối cùng của transaction đã bị deadlock rollback.

### 11.2. Lock wait timeout

Khi một statement chờ khóa quá thời gian, InnoDB mặc định thường rollback statement đang chờ, không rollback toàn transaction.

Biến \`innodb_rollback_on_timeout\` có thể thay đổi hành vi này. Kiểm tra:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout,
    @@GLOBAL.innodb_rollback_on_timeout;
~~~

Nếu \`innodb_rollback_on_timeout = 0\`, statement timeout thường bị rollback, còn transaction vẫn hoạt động. Nếu bật, timeout có thể khiến toàn transaction bị rollback.

Sau lock wait timeout, ứng dụng phải biết cấu hình thực tế và quyết định:
- Retry statement trong transaction còn hợp lệ.
- ROLLBACK toàn transaction rồi thử lại.
- Trả lỗi cho caller.

Với nghiệp vụ nhiều bước, rollback toàn transaction rồi retry từ đầu thường dễ bảo đảm tính nhất quán hơn, nhưng cần cân nhắc idempotency và tác dụng phụ.

### 11.3. Bảng so sánh lỗi

| Tình huống | Hành vi InnoDB thường gặp | Hành động ứng dụng |
|---|---|---|
| Duplicate key trong INSERT | Rollback statement thất bại | Sửa dữ liệu, xử lý duplicate hoặc rollback transaction theo nghiệp vụ |
| Vi phạm CHECK/FOREIGN KEY | Rollback statement thất bại | Xử lý lỗi; transaction thường vẫn mở |
| SIGNAL trong stored program | Statement chứa lỗi thất bại | Handler/caller quyết định phạm vi transaction |
| Lock wait timeout, mặc định | Rollback statement đang chờ | Quyết định tiếp tục hay rollback transaction |
| Deadlock victim | Rollback toàn transaction | Retry toàn transaction nếu an toàn |
| Lỗi kết nối trước khi biết COMMIT đã hoàn tất chưa | Kết quả có thể không rõ với client | Đọc trạng thái/idempotency trước khi retry |

Hành vi có thể phụ thuộc storage engine, loại statement và cấu hình server. Không áp dụng quy tắc rollback của InnoDB cho mọi engine.

## 12. Bảng không hỗ trợ transaction và tác dụng phụ ngoài database

Statement rollback và transaction rollback chỉ bảo vệ thay đổi transactional của storage engine.

### 12.1. MyISAM không rollback như InnoDB

Ví dụ bảng:

~~~sql
CREATE TABLE legacy_counter (
    counter_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    value_count BIGINT NOT NULL
) ENGINE = MyISAM;
~~~

Thay đổi trên MyISAM không được hoàn tác bằng ROLLBACK như InnoDB. Nếu transaction cập nhật cả InnoDB và MyISAM, ROLLBACK chỉ có thể hoàn tác phần transactional của InnoDB; thay đổi MyISAM có thể vẫn còn.

Với nghiệp vụ cần atomicity, các bảng tham gia nên dùng InnoDB.

### 12.2. Side effect ngoài database

Một transaction SQL không tự hoàn tác được:
- Email đã gửi.
- HTTP request đã gọi.
- File đã ghi.
- Message đã gửi vào hệ thống bên ngoài.
- Thao tác trên dịch vụ không tham gia cùng transaction.

Nếu ứng dụng thực hiện side effect trước COMMIT rồi transaction rollback, hệ thống ngoài vẫn có thể đã nhận tác động.

Dùng transactional outbox:
1. Ghi thay đổi nghiệp vụ và một outbox event trong cùng transaction InnoDB.
2. COMMIT.
3. Worker đọc outbox và gửi message/email/API.
4. Đánh dấu event đã xử lý bằng cơ chế idempotent.
5. Retry khi dịch vụ ngoài tạm thời lỗi.

Đây là cách tách transaction database khỏi tác dụng phụ ngoài hệ thống mà vẫn có thể phục hồi.

## 13. GET DIAGNOSTICS: đọc nguyên nhân lỗi

Handler có thể dùng GET DIAGNOSTICS để lấy thông tin condition vừa xảy ra.

Ví dụ:

~~~sql
DECLARE v_sqlstate CHAR(5);
DECLARE v_errno INT;
DECLARE v_message TEXT;

DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;
END;
~~~

Các item hữu ích:

| Item | Ý nghĩa |
|---|---|
| RETURNED_SQLSTATE | SQLSTATE của condition |
| MYSQL_ERRNO | Mã lỗi MySQL |
| MESSAGE_TEXT | Nội dung lỗi |
| ROW_COUNT | Số hàng bị tác động của statement liên quan trong diagnostics context |

GET DIAGNOSTICS nên được gọi sớm trong handler, trước khi chạy thêm statement có thể làm thay đổi diagnostics area. Nếu cần lưu lỗi, sao chép thông tin vào biến cục bộ rồi mới INSERT log.

### 13.1. RESIGNAL giữ lỗi gốc

Nếu handler chỉ ghi nhận lỗi rồi kết thúc bằng CONTINUE, lỗi có thể bị nuốt và caller tưởng thao tác thành công.

Dùng RESIGNAL để phát lại condition hiện tại:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    INSERT INTO routine_error_audit (
        sqlstate_value,
        mysql_errno,
        message_text,
        logged_at
    )
    VALUES (
        v_sqlstate,
        v_errno,
        v_message,
        NOW(6)
    );

    RESIGNAL;
END;
~~~

Nếu INSERT audit nằm trong cùng transaction và sau đó caller rollback, dòng audit cũng bị rollback. Nếu cần lưu dấu vết lỗi bền vững sau rollback, hãy ghi log ở tầng ứng dụng hoặc thiết kế một kênh log/transaction riêng; không giả định log InnoDB trong transaction thất bại sẽ tự tồn tại.

### 13.2. RESIGNAL có thể thay đổi condition

Có thể dùng RESIGNAL để phát lại condition hoặc thay đổi một số thuộc tính như SQLSTATE/message theo cú pháp được MySQL hỗ trợ. Khi cần giữ nguyên lỗi gốc, dùng \`RESIGNAL;\` không kèm thông tin thay thế.

Không phát một lỗi mới che mất nguyên nhân ban đầu nếu caller cần phân loại deadlock, duplicate key hoặc constraint violation.

## 14. Handler cho cursor và NOT FOUND

Trong cursor loop, \`NOT FOUND\` thường biểu thị đã FETCH hết hàng. Nó không phải lỗi nghiệp vụ và không nên bị nhầm với SQLEXCEPTION.

Ví dụ khung:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_id BIGINT UNSIGNED;

DECLARE cur CURSOR FOR
    SELECT source_id
    FROM import_stage
    ORDER BY source_id;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;

OPEN cur;

read_loop: LOOP
    FETCH cur INTO v_id;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Xử lý hàng hiện tại.
END LOOP;

CLOSE cur;
~~~

### 14.1. Scope của NOT FOUND handler

Nếu cùng block vừa FETCH cursor vừa dùng SELECT ... INTO, một SELECT ... INTO không có hàng cũng có thể kích hoạt handler NOT FOUND và đặt v_done = TRUE. Vòng lặp sau đó có thể kết thúc sớm ngoài ý muốn.

Cách tránh:
- Dùng block lồng nhau với handler NOT FOUND riêng cho SELECT ... INTO.
- Dùng cờ riêng cho từng mục đích.
- Thiết kế SELECT có khóa duy nhất và xử lý no-row rõ ràng.
- Không đặt một handler quá rộng cho nhiều thao tác không liên quan.

### 14.2. Lỗi từng hàng trong cursor loop

Có thể dùng block con với CONTINUE HANDLER FOR SQLEXCEPTION cho statement xử lý một hàng, như ví dụ import ở mục 6. Điều này cho phép:
- Lỗi của một INSERT được ghi nhận.
- Vòng lặp tiếp tục.
- Lỗi nghiêm trọng ngoài block con đi tới handler cấp batch.

Không đặt CONTINUE handler toàn cục cho mọi SQLEXCEPTION nếu không phân biệt lỗi dữ liệu có thể bỏ qua với lỗi hạ tầng cần dừng batch.

## 15. Xử lý lỗi trong Java JDBC

Nếu transaction do ứng dụng sở hữu, JDBC cần rollback khi bất kỳ bước nghiệp vụ nào thất bại.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debitAccount(connection, fromAccountId, amount);
        creditAccount(connection, toAccountId, amount);
        insertTransferAudit(connection, fromAccountId, toAccountId, amount);

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

### 15.1. Không chỉ rollback statement khi nghiệp vụ cần atomicity

Nếu một statement trong transaction thất bại, MySQL/InnoDB có thể chỉ rollback statement. JDBC không tự động đảm bảo toàn transaction đã rollback. Nếu nghiệp vụ yêu cầu tất cả bước cùng thành công, catch exception và gọi connection.rollback().

### 15.2. Savepoint trong JDBC

~~~java
Savepoint savepoint = connection.setSavepoint("beforeOptionalStep");

try {
    runOptionalStep(connection);
} catch (SQLException ex) {
    connection.rollback(savepoint);
    // Quyết định tiếp tục hoặc ném lỗi tùy hợp đồng nghiệp vụ.
}
~~~

Savepoint cho phép bỏ phần việc tùy chọn và tiếp tục transaction. Không dùng nó nếu lỗi thực tế đã làm InnoDB rollback toàn transaction, ví dụ deadlock victim. Trong trường hợp transaction đã bị rollback, savepoint không còn tồn tại.

### 15.3. Retry deadlock

Nếu nhận lỗi deadlock:
- Rollback transaction (nếu server chưa rollback toàn bộ thì rollback cũng an toàn).
- Tạo transaction mới.
- Chạy lại toàn bộ thao tác từ đầu.
- Giới hạn retry và thêm backoff.
- Bảo đảm request có idempotency key nếu client có thể gửi lại sau timeout.

Không retry duy nhất câu SQL cuối cùng khi các statement trước đã bị rollback cùng transaction.

## 16. Các mẫu xử lý nên và không nên dùng

| Tình huống | Mẫu phù hợp | Tránh |
|---|---|---|
| Một dòng dữ liệu lỗi nhưng batch vẫn xử lý dòng khác | Block con + CONTINUE handler + ghi lỗi | Handler toàn procedure nuốt mọi lỗi |
| Chuyển tiền nhiều bước | Transaction + EXIT handler ROLLBACK + RESIGNAL | Bỏ qua lỗi bước cộng tiền |
| Procedure nằm trong transaction lớn của service | Caller-owned; procedure RESIGNAL, không COMMIT/ROLLBACK | Procedure tự START/COMMIT làm mất transaction cha |
| Chỉ rollback một bước tùy chọn | SAVEPOINT và ROLLBACK TO SAVEPOINT | Giả định savepoint là transaction con |
| Deadlock | Retry toàn transaction | Chỉ retry statement cuối |
| Gửi email sau ghi dữ liệu | Outbox sau COMMIT | Gửi email trong function rồi mong ROLLBACK thu hồi |
| Lỗi cursor hết hàng | NOT FOUND handler có scope rõ | Xem NOT FOUND như lỗi SQL chung |
| Log lỗi sau full rollback | Application log hoặc transaction log riêng được thiết kế rõ | Ghi log InnoDB rồi rollback và kỳ vọng log còn |

## 17. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Statement lỗi làm mất toàn bộ transaction | Nhầm statement rollback với transaction rollback | Kiểm tra transaction state và loại lỗi |
| Handler CONTINUE tự rollback | Handler chỉ điều khiển luồng | Viết ROLLBACK rõ ràng nếu cần |
| Handler EXIT luôn thoát procedure | EXIT thoát block nơi khai báo | Đặt handler đúng scope |
| Handler nuốt lỗi làm caller tưởng thành công | CONTINUE kết thúc mà không báo trạng thái | Trả OUT status hoặc RESIGNAL |
| Duplicate key làm rollback UPDATE trước đó | UPDATE trước vẫn nằm trong transaction | Caller quyết định COMMIT hay ROLLBACK |
| Deadlock chỉ rollback statement cuối | InnoDB rollback toàn transaction victim | Retry toàn transaction |
| Lock timeout luôn rollback toàn transaction | Mặc định thường rollback statement; biến cấu hình có thể đổi hành vi | Kiểm tra innodb_rollback_on_timeout |
| ROLLBACK không xóa thay đổi MyISAM | MyISAM không transactional | Dùng InnoDB cho dữ liệu cần atomicity |
| Audit log biến mất sau lỗi | Log nằm trong cùng transaction bị rollback | Ghi log ngoài transaction hoặc thiết kế riêng |
| NOT FOUND làm cursor dừng sớm | SELECT ... INTO cùng scope kích hoạt handler | Tách block và handler |
| SAVEPOINT bị mất sau DDL | DDL gây implicit commit | Không đặt DDL trong transaction cần rollback |
| Procedure rollback công việc của caller | Procedure tự sở hữu transaction nhưng caller cũng đang có transaction | Chọn caller-owned hoặc procedure-owned contract |
| Retry deadlock tạo tác dụng phụ lặp | Side effect ngoài database không idempotent | Outbox và idempotency key |
| Dùng INSERT IGNORE để “bỏ qua mọi lỗi” | IGNORE thay đổi semantics lỗi thành warning/partial acceptance trong một số trường hợp | Bắt lỗi có chủ đích và kiểm tra warning |

## 18. Quy trình thiết kế chính sách rollback

Trước khi viết handler, trả lời các câu hỏi:

1. Đơn vị nghiệp vụ là một statement, một hàng, một batch hay toàn transaction?
2. Nếu một hàng lỗi, có được phép xử lý các hàng còn lại không?
3. Nếu bước thứ hai lỗi, bước thứ nhất có được giữ lại không?
4. Transaction do procedure hay caller sở hữu?
5. Các bảng có cùng dùng InnoDB không?
6. Có DDL hoặc thao tác implicit commit trong quy trình không?
7. Handler nào xử lý SQLEXCEPTION, SQLWARNING và NOT FOUND?
8. CONTINUE có thực sự phù hợp hay cần EXIT?
9. Có cần RESIGNAL để caller nhận lỗi không?
10. Có cần SAVEPOINT cho phần việc tùy chọn không?
11. Lỗi deadlock và lock timeout được retry như thế nào?
12. Log lỗi có cần tồn tại sau rollback không?
13. Có side effect ngoài database không?
14. Retry có thể tạo dữ liệu hoặc tác dụng phụ trùng lặp không?
15. Có kiểm thử bằng hai session và lỗi constraint thực tế không?

## 19. Bài tập thực hành

### Bài 1: Statement rollback

Mở transaction, UPDATE một hàng, sau đó INSERT một primary key đã tồn tại. Kiểm tra hàng sau lỗi. Xác nhận UPDATE trước đó vẫn còn trong transaction.

### Bài 2: Transaction rollback

Lặp lại Bài 1 nhưng gọi ROLLBACK sau lỗi. Kiểm tra UPDATE trước đó đã được hoàn tác.

### Bài 3: CONTINUE handler

Viết procedure bắt duplicate key bằng CONTINUE handler, đặt cờ và trả OUT parameter cho caller. Xác nhận procedure tiếp tục sau statement lỗi.

### Bài 4: EXIT handler

Viết procedure dùng EXIT handler cho SQLEXCEPTION. Phát SIGNAL trong block lồng nhau và xác định block nào kết thúc.

### Bài 5: Rollback toàn nghiệp vụ

Tạo procedure chuyển tiền với transaction InnoDB. Cố ý làm bước cộng tiền thất bại, xác nhận số dư nguồn không bị trừ sau ROLLBACK.

### Bài 6: Caller-owned transaction

Viết procedure không START/COMMIT/ROLLBACK. Gọi nó trong transaction của JDBC hoặc SQL client; gây lỗi rồi để caller rollback toàn bộ.

### Bài 7: SAVEPOINT

Thực hiện ba bước ghi, đặt savepoint trước bước thứ hai, rollback về savepoint rồi commit. Xác định chính xác bước nào được giữ.

### Bài 8: Cursor và NOT FOUND

Viết cursor loop có CONTINUE HANDLER FOR NOT FOUND. Thêm một SELECT ... INTO không có hàng trong cùng scope, quan sát cờ done. Sau đó chuyển SELECT vào block con có handler riêng.

### Bài 9: Batch tiếp tục khi một hàng lỗi

Dùng import_stage và imported_customer. Để một email trùng, dùng handler cục bộ cho từng INSERT và ghi lỗi. Xác nhận hàng hợp lệ được commit, hàng lỗi không được chèn.

### Bài 10: Deadlock và lock timeout

Dùng hai session khóa hai hàng theo thứ tự ngược nhau để tạo deadlock trong lab. Ghi lại lỗi và xác nhận transaction victim bị rollback toàn bộ. Sau đó thử lock wait timeout và kiểm tra innodb_rollback_on_timeout.

### Bài 11: InnoDB và MyISAM

Tạo hai bảng khác engine, cập nhật cả hai trong một transaction rồi ROLLBACK. So sánh phần dữ liệu được hoàn tác.

### Bài 12: Error logging và RESIGNAL

Viết EXIT handler dùng GET DIAGNOSTICS để ghi lỗi rồi RESIGNAL. Gây lỗi, rollback transaction và kiểm tra vì sao log transactional có thể biến mất cùng transaction.

## 20. Checklist trước khi triển khai

- [ ] Đã phân biệt statement rollback, savepoint rollback và transaction rollback.
- [ ] Đã xác định transaction do procedure hay caller sở hữu.
- [ ] Đã dùng InnoDB cho các bảng cần atomicity.
- [ ] Đã hiểu autocommit và transaction tường minh.
- [ ] Đã chọn CONTINUE hoặc EXIT theo chính sách nghiệp vụ.
- [ ] Đã khai báo handler trong đúng scope.
- [ ] Đã xử lý NOT FOUND riêng cho cursor và SELECT ... INTO.
- [ ] Đã không để handler nuốt lỗi mà không trả trạng thái.
- [ ] Đã dùng RESIGNAL khi caller cần nhận lỗi gốc.
- [ ] Đã dùng GET DIAGNOSTICS để thu thập SQLSTATE, mã lỗi và message khi cần.
- [ ] Đã gọi ROLLBACK rõ ràng khi cần hoàn tác toàn nghiệp vụ.
- [ ] Đã dùng SAVEPOINT chỉ trong transaction đang hoạt động.
- [ ] Đã hiểu DDL gây implicit commit và làm mất savepoint.
- [ ] Đã phân biệt deadlock rollback toàn transaction với lock timeout mặc định rollback statement.
- [ ] Đã kiểm tra innodb_rollback_on_timeout.
- [ ] Đã xử lý retry toàn transaction và idempotency.
- [ ] Đã xác định log lỗi có bị rollback cùng transaction không.
- [ ] Đã tránh side effect ngoài database trước COMMIT hoặc dùng outbox.
- [ ] Đã kiểm thử lỗi ở từng bước và xác minh trạng thái dữ liệu sau rollback.

## 21. Kết luận

Với InnoDB, một statement DML thất bại thường chỉ làm rollback những thay đổi của statement đó; các statement thành công trước đó trong transaction vẫn còn cho tới khi caller COMMIT hoặc ROLLBACK. Đây là statement rollback. Muốn bảo đảm toàn nghiệp vụ nhiều bước cùng thành công hoặc cùng thất bại, phải rollback toàn transaction khi một bước bắt buộc lỗi.

Handler chỉ quyết định cách stored program phản ứng với condition: CONTINUE để tiếp tục sau statement, EXIT để thoát block, RESIGNAL để chuyển lỗi lên caller. Handler không tự rollback nếu thân handler không gọi ROLLBACK. SAVEPOINT hỗ trợ hoàn tác một phần trong transaction. Deadlock là trường hợp đặc biệt InnoDB rollback toàn transaction victim; lock wait timeout mặc định thường rollback statement, trừ khi cấu hình thay đổi. Cuối cùng, transaction chỉ bảo vệ thay đổi transactional của engine tham gia; MyISAM và side effect ngoài database không tự được hoàn tác. Hãy xác định transaction owner, storage engine, phạm vi handler và chính sách retry trước khi triển khai.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Condition Handling](https://dev.mysql.com/doc/refman/8.4/en/condition-handling.html)
- [MySQL 8.4 Reference Manual – DECLARE ... HANDLER](https://dev.mysql.com/doc/refman/8.4/en/declare-handler.html)
- [MySQL 8.4 Reference Manual – GET DIAGNOSTICS](https://dev.mysql.com/doc/refman/8.4/en/get-diagnostics.html)
- [MySQL 8.4 Reference Manual – RESIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/resignal.html)
- [MySQL 8.4 Reference Manual – SIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/signal.html)
- [MySQL 8.4 Reference Manual – Cursor Restrictions](https://dev.mysql.com/doc/refman/8.4/en/cursor-restrictions.html)
- [MySQL 8.4 Reference Manual – InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html)
- [MySQL 8.4 Reference Manual – InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual – InnoDB Parameters: innodb_rollback_on_timeout](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual – SAVEPOINT, ROLLBACK TO SAVEPOINT](https://dev.mysql.com/doc/refman/8.4/en/savepoint.html)
- [MySQL 8.4 Reference Manual – Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual – InnoDB and Transaction Management](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual – MyISAM Storage Engine](https://dev.mysql.com/doc/refman/8.4/en/myisam-storage-engine.html)

