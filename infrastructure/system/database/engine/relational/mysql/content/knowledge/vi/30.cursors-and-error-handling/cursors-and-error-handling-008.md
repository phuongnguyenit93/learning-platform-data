# GET DIAGNOSTICS để đọc thông tin lỗi hoặc số dòng

GET DIAGNOSTICS là câu lệnh SQL dùng để đọc thông tin từ diagnostics area của MySQL sau khi một câu lệnh chạy. Nó cho phép stored program biết câu lệnh trước đó tạo ra bao nhiêu condition, ảnh hưởng bao nhiêu hàng, hoặc lấy SQLSTATE, mã lỗi và thông báo lỗi cụ thể.

Trong stored procedure, GET DIAGNOSTICS thường được dùng để ghi nhận số hàng bị tác động sau INSERT/UPDATE/DELETE và để phân tích lỗi bên trong handler. Khi handler được kích hoạt bởi một lỗi, GET STACKED DIAGNOSTICS giúp đọc condition đã khiến handler chạy, ngay cả khi các câu lệnh bên trong handler tạo ra diagnostics mới.

Trong module **DATABASE_MYSQL**, cursor và error handling giúp xử lý luồng dữ liệu nhiều bước ở phía server. GET DIAGNOSTICS bổ sung khả năng quan sát kết quả và nguyên nhân lỗi để procedure có thể ghi log, trả thông tin phù hợp hoặc phát lại lỗi gốc cho ứng dụng.

## 1. Diagnostics area là gì?

Sau khi MySQL thực thi một câu lệnh, server lưu thông tin chẩn đoán vào diagnostics area. Khu vực này có hai phần chính:

- **Statement information area:** thông tin chung về câu lệnh, gồm số condition và số hàng bị tác động.
- **Condition information area:** thông tin của từng condition phát sinh, như SQLSTATE, MySQL error number, message và thông tin đối tượng liên quan.

Một condition có thể là lỗi, warning hoặc note. Một câu lệnh có thể không tạo condition nào, tạo một condition hoặc tạo nhiều condition.

Ví dụ:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

GET DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;
```

Sau UPDATE, statement information area cho biết số condition được ghi nhận và số hàng bị tác động. Nếu UPDATE không tạo warning/error, NUMBER thường bằng 0; ROW_COUNT phản ánh số hàng được câu lệnh tác động theo semantics của MySQL.

GET DIAGNOSTICS chỉ đọc thông tin chẩn đoán. Nó không thay thế handler và không tự bắt lỗi. Muốn xử lý một lỗi để tiếp tục hoặc thoát khỏi procedure, cần khai báo DECLARE ... HANDLER.

## 2. Cú pháp GET DIAGNOSTICS

Cú pháp có hai dạng chính:

```sql
GET [CURRENT | STACKED] DIAGNOSTICS
    statement_information_item [, statement_information_item] ...;

GET [CURRENT | STACKED] DIAGNOSTICS
    CONDITION condition_number
    condition_information_item [, condition_information_item] ...;
```

Có thể đọc statement information hoặc condition information trong một lần gọi. Không trộn hai nhóm item trong cùng một GET DIAGNOSTICS statement.

Nếu bỏ CURRENT hoặc STACKED, MySQL mặc định dùng CURRENT.

### 2.1. CURRENT

CURRENT là diagnostics area hiện tại. Dùng nó sau một câu lệnh thông thường để lấy số hàng bị tác động hoặc condition vừa phát sinh.

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = 9002;

GET CURRENT DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;
```

CURRENT phù hợp khi chưa ở trong handler hoặc khi cần đọc diagnostics của câu lệnh hiện tại trong luồng xử lý.

### 2.2. STACKED

STACKED là bản diagnostics area được lưu lại khi một handler được kích hoạt. Nó chứa condition đã làm handler chạy.

Trong handler, nên dùng GET STACKED DIAGNOSTICS để đọc lỗi gốc trước khi thực hiện các câu lệnh khác như INSERT log, SET biến hoặc gọi routine hỗ trợ.

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_message = MESSAGE_TEXT;
    RESIGNAL;
END;
```

STACKED chỉ dùng được trong phạm vi handler đang hoạt động. Gọi GET STACKED DIAGNOSTICS bên ngoài handler sẽ phát sinh lỗi vì không có stacked diagnostics area hợp lệ.

### 2.3. Khác biệt giữa CURRENT và STACKED

| Ngữ cảnh | Nên đọc | Lý do |
|---|---|---|
| Ngay sau UPDATE/INSERT/DELETE bình thường | CURRENT | Đọc diagnostics của câu lệnh vừa chạy |
| Trong handler, cần lỗi đã kích hoạt handler | STACKED | Giữ thông tin condition ban đầu |
| Trong handler, cần condition do câu lệnh mới bên trong handler tạo ra | CURRENT | Đọc diagnostics hiện tại của handler |
| Ngoài handler nhưng cố đọc STACKED | Không hợp lệ | Không có stacked area đang hoạt động |

Một handler có thể thực thi nhiều câu lệnh. Các câu lệnh đó có thể làm thay đổi diagnostics area hiện tại. Vì vậy, hãy chụp thông tin lỗi gốc từ STACKED ngay đầu handler.

## 3. Đọc statement information: NUMBER và ROW_COUNT

Statement information area có hai item quan trọng.

| Item | Ý nghĩa |
|---|---|
| NUMBER | Số condition được ghi trong diagnostics area của câu lệnh |
| ROW_COUNT | Số hàng bị tác động theo câu lệnh trước đó |

Có thể đọc cả hai trong cùng một câu:

```sql
UPDATE orders
SET status = 'PAID'
WHERE tenant_id = 42
  AND status = 'PENDING';

GET DIAGNOSTICS
    @number_of_conditions = NUMBER,
    @rows_affected = ROW_COUNT;

SELECT
    @number_of_conditions AS condition_count,
    @rows_affected AS rows_affected;
```

NUMBER không phải số hàng. ROW_COUNT không phải số condition. Không hoán đổi hai item này.

### 3.1. NUMBER

NUMBER cho biết diagnostics area có bao nhiêu condition. Ví dụ một câu INSERT IGNORE có thể tạo warning khi một số hàng bị bỏ qua hoặc giá trị được điều chỉnh.

```sql
INSERT IGNORE INTO users (user_id, email)
VALUES
    (101, 'a@example.com'),
    (101, 'duplicate@example.com');

GET DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;
```

Giá trị cụ thể phụ thuộc dữ liệu, constraint và warning do server phát ra. Nếu NUMBER bằng 0, không có condition nào được ghi nhận cho câu lệnh đó. Nếu lớn hơn 0, có thể đọc từng condition bằng phần CONDITION.

### 3.2. ROW_COUNT

ROW_COUNT hữu ích ngay sau câu lệnh DML:

```sql
DELETE FROM sessions
WHERE expires_at < CURRENT_TIMESTAMP;

GET DIAGNOSTICS @deleted_rows = ROW_COUNT;
```

Nên đọc ROW_COUNT ngay sau câu lệnh cần đo. Nếu chạy một câu SQL khác trước khi lấy diagnostics, thông tin có thể phản ánh câu lệnh mới thay vì câu lệnh mà bạn muốn kiểm tra.

ROW_COUNT không phải bộ đếm tổng quát cho mọi hàng mà một SELECT có thể trả về. Với truy vấn SELECT thông thường, giá trị row count có semantics riêng và thường không dùng như số hàng kết quả. Nếu cần đếm hàng phù hợp với điều kiện, dùng COUNT(*) hoặc xử lý result set/cursor theo mục tiêu.

### 3.3. UPDATE không tìm thấy hàng và UPDATE không làm thay đổi giá trị

Ví dụ:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 999999;

GET DIAGNOSTICS @rows = ROW_COUNT;
```

Nếu không có order_id tương ứng, ROW_COUNT bằng 0. Tuy nhiên, khi UPDATE tìm thấy hàng nhưng gán lại đúng giá trị hiện tại, số hàng báo cáo có thể phụ thuộc semantics affected rows và cờ CLIENT_FOUND_ROWS của client. Vì vậy, không luôn diễn giải ROW_COUNT = 0 là "không có hàng thỏa WHERE" nếu ứng dụng bật chế độ trả về matched rows.

Nếu nghiệp vụ cần phân biệt "không tồn tại" với "đã tồn tại nhưng không thay đổi", cần truy vấn hoặc kiểm tra bổ sung với transaction/locking phù hợp, không dựa riêng vào ROW_COUNT.

### 3.4. INSERT ... ON DUPLICATE KEY UPDATE

Với INSERT ... ON DUPLICATE KEY UPDATE, affected-row count có thể biểu diễn insert, update hoặc không đổi. Theo semantics MySQL thông thường, mỗi hàng có thể được tính là 1 khi insert, 2 khi update và 0 khi update nhưng giá trị không đổi; cờ CLIENT_FOUND_ROWS có thể làm thay đổi trường hợp không đổi.

```sql
INSERT INTO account_balance (account_id, balance)
VALUES (42, 1000)
ON DUPLICATE KEY UPDATE
    balance = VALUES(balance);

GET DIAGNOSTICS @affected_rows = ROW_COUNT;
```

Không dùng một con số duy nhất để suy ra chính xác nhánh nghiệp vụ nếu statement xử lý nhiều hàng hoặc có cờ client ảnh hưởng affected rows. Nếu cần biết từng hàng được insert hay update, thiết kế API/logic rõ ràng hơn.

## 4. Đọc condition information

Condition information mô tả một condition cụ thể trong diagnostics area.

Các item thường dùng:

| Item | Ý nghĩa |
|---|---|
| RETURNED_SQLSTATE | SQLSTATE gồm 5 ký tự |
| MYSQL_ERRNO | Mã lỗi riêng của MySQL |
| MESSAGE_TEXT | Thông báo lỗi hoặc warning |
| CLASS_ORIGIN | Nguồn gốc SQLSTATE class |
| SUBCLASS_ORIGIN | Nguồn gốc SQLSTATE subclass |
| CONSTRAINT_SCHEMA | Schema của constraint liên quan |
| CONSTRAINT_NAME | Tên constraint liên quan |
| TABLE_NAME | Tên bảng liên quan nếu có |
| COLUMN_NAME | Tên cột liên quan nếu có |
| CURSOR_NAME | Tên cursor liên quan nếu có |

Một số item có thể NULL hoặc rỗng nếu condition không liên quan đến bảng, cột hoặc constraint cụ thể.

Ví dụ đọc condition đầu tiên:

```sql
GET DIAGNOSTICS CONDITION 1
    @state = RETURNED_SQLSTATE,
    @errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;

SELECT
    @state AS sqlstate_code,
    @errno AS mysql_error_number,
    @message AS diagnostic_message;
```

Có thể đọc thêm thông tin constraint:

```sql
GET DIAGNOSTICS CONDITION 1
    @state = RETURNED_SQLSTATE,
    @constraint_schema = CONSTRAINT_SCHEMA,
    @constraint_name = CONSTRAINT_NAME,
    @table_name = TABLE_NAME,
    @column_name = COLUMN_NAME;
```

Đừng giả định mọi lỗi đều có đủ tên constraint, bảng và cột. Hãy xử lý NULL trong code hoặc khi ghi log.

### 4.1. SQLSTATE và MYSQL_ERRNO khác nhau

SQLSTATE là mã trạng thái chuẩn hóa gồm 5 ký tự, ví dụ:

- 23000: integrity constraint violation.
- 02000: no data.
- 01000: warning.
- 45000: trạng thái do ứng dụng tự phát bằng SIGNAL.

MYSQL_ERRNO là mã lỗi cụ thể do MySQL định nghĩa. Nó hữu ích khi cần phân biệt lỗi cụ thể của server, nhưng thường ít portable hơn SQLSTATE.

MESSAGE_TEXT là thông điệp dành cho chẩn đoán. Không nên dùng chuỗi message làm khóa logic chính vì nội dung có thể thay đổi theo phiên bản, ngôn ngữ hoặc ngữ cảnh. Nếu cần xử lý theo loại lỗi, ưu tiên SQLSTATE hoặc MYSQL_ERRNO.

### 4.2. CONDITION 1 không có nghĩa là lúc nào cũng đủ

Một câu lệnh có thể tạo nhiều condition, ví dụ một statement phát nhiều warning. Hãy đọc NUMBER trước để biết có bao nhiêu condition.

```sql
GET DIAGNOSTICS @condition_count = NUMBER;
```

Sau đó đọc condition cần xem:

```sql
GET DIAGNOSTICS CONDITION 1
    @state_1 = RETURNED_SQLSTATE,
    @errno_1 = MYSQL_ERRNO,
    @message_1 = MESSAGE_TEXT;
```

CONDITION 1 là condition đầu tiên theo số thứ tự trong diagnostics area. Khi có nhiều condition, không nên chỉ lấy một condition rồi kết luận đã hiểu toàn bộ statement. Có thể đọc thêm CONDITION 2, CONDITION 3... theo số lượng thực tế.

Cần phân biệt condition đầu tiên với nguyên nhân nghiệp vụ mà ứng dụng quan tâm. Một statement có thể tạo warning bổ sung bên cạnh lỗi hoặc warning chính. Kiểm tra các condition cần thiết thay vì chỉ dựa vào message đầu tiên.

## 5. Đọc số hàng bị tác động trong stored procedure

GET DIAGNOSTICS thường được dùng để trả số hàng đã cập nhật cho ứng dụng hoặc quyết định nhánh xử lý tiếp theo.

Ví dụ:

```sql
DELIMITER //

CREATE PROCEDURE mark_order_paid(
    IN p_order_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_rows BIGINT DEFAULT 0;

    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id
      AND status = 'PENDING';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    SELECT v_rows AS affected_rows;
END//

DELIMITER ;
```

Procedure chỉ cập nhật đơn hàng đang PENDING. Giá trị v_rows được chụp ngay sau UPDATE nên không bị ảnh hưởng bởi SELECT trả kết quả ở cuối.

Nếu v_rows = 1, statement đã tác động một hàng theo affected-row semantics. Nếu bằng 0, không có hàng nào được tính là thay đổi; có thể do đơn không tồn tại, trạng thái không còn PENDING hoặc hàng đã có trạng thái khác. Nếu cần phân biệt các trường hợp, phải bổ sung logic kiểm tra.

### 5.1. Không đặt câu lệnh khác giữa DML và GET DIAGNOSTICS

Tránh:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

SELECT CURRENT_TIMESTAMP;

GET DIAGNOSTICS v_rows = ROW_COUNT;
```

Ở đây diagnostics cần đọc phải được lấy ngay sau UPDATE. Câu SELECT xen giữa có thể thay đổi diagnostics area hiện tại. Mẫu rõ ràng:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

GET DIAGNOSTICS v_rows = ROW_COUNT;

SELECT CURRENT_TIMESTAMP;
```

Hãy chụp giá trị cần thiết vào local variable trước khi chạy câu lệnh khác.

## 6. GET DIAGNOSTICS trong SQLWARNING handler

Có thể dùng handler để xử lý warning và đọc condition đã kích hoạt handler.

```sql
DELIMITER //

CREATE PROCEDURE inspect_warning()
BEGIN
    DECLARE v_state CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message TEXT;

    DECLARE CONTINUE HANDLER FOR SQLWARNING
    BEGIN
        GET STACKED DIAGNOSTICS CONDITION 1
            v_state = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        SELECT
            v_state AS warning_sqlstate,
            v_errno AS warning_errno,
            v_message AS warning_message;
    END;

    INSERT IGNORE INTO users (user_id, email)
    VALUES (101, 'duplicate@example.com');
END//

DELIMITER ;
```

Handler CONTINUE xử lý warning rồi tiếp tục sau câu lệnh gây warning. Handler EXIT sẽ rời khỏi compound statement hiện tại sau khi handler kết thúc.

Trong ứng dụng thực tế, không nên mặc định một câu INSERT IGNORE chỉ tạo một warning. Có thể có nhiều condition. Nếu cần đầy đủ thông tin, lấy NUMBER và đọc từng condition phù hợp.

## 7. GET STACKED DIAGNOSTICS trong SQLEXCEPTION handler

Khi một lỗi xảy ra, handler có thể đọc SQLSTATE, mã lỗi và message rồi phát lại lỗi gốc bằng RESIGNAL.

Ví dụ:

```sql
DELIMITER //

CREATE PROCEDURE create_order(
    IN p_order_id BIGINT UNSIGNED,
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message TEXT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET STACKED DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        -- Có thể ghi nhận các biến chẩn đoán ở đây theo chính sách log.
        RESIGNAL;
    END;

    INSERT INTO orders (
        order_id,
        customer_id,
        status
    )
    VALUES (
        p_order_id,
        p_customer_id,
        'PENDING'
    );
END//

DELIMITER ;
```

Thứ tự quan trọng:

1. Handler được kích hoạt do SQLEXCEPTION.
2. GET STACKED DIAGNOSTICS đọc condition đã kích hoạt handler.
3. Các giá trị được chụp vào local variable.
4. Có thể thực hiện xử lý bổ sung.
5. RESIGNAL phát lại lỗi gốc cho caller.

Nếu dùng GET CURRENT DIAGNOSTICS sau khi đã chạy câu lệnh khác trong handler, có thể đọc diagnostics của câu lệnh trong handler thay vì lỗi ban đầu. STACKED được thiết kế cho tình huống này.

### 7.1. RESIGNAL và SIGNAL

- RESIGNAL phát lại condition đã kích hoạt handler, có thể giữ nguyên lỗi gốc hoặc thay đổi một số thuộc tính theo cú pháp.
- SIGNAL tạo một condition mới, thường dùng SQLSTATE ứng dụng như 45000.
- GET DIAGNOSTICS chỉ đọc thông tin; nó không phát lỗi và không thay thế RESIGNAL/SIGNAL.

Ví dụ phát lỗi nghiệp vụ:

```sql
IF p_amount <= 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Amount must be greater than zero';
END IF;
```

Nếu một handler bắt condition này, GET STACKED DIAGNOSTICS có thể đọc SQLSTATE 45000 và message đã đặt.

## 8. Ghi log lỗi mà không làm mất lỗi gốc

Một stored procedure có thể ghi thông tin lỗi vào bảng log. Tuy nhiên, phải hiểu transaction boundary trước khi thiết kế.

Ví dụ bảng log:

```sql
CREATE TABLE database_error_log (
    log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    routine_name VARCHAR(128) NOT NULL,
    sqlstate_code CHAR(5),
    mysql_errno INT,
    message_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id)
) ENGINE = InnoDB;
```

Trong handler có thể chụp diagnostics rồi ghi log:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    INSERT INTO database_error_log (
        routine_name,
        sqlstate_code,
        mysql_errno,
        message_text
    )
    VALUES (
        'create_order',
        v_sqlstate,
        v_errno,
        v_message
    );

    RESIGNAL;
END;
```

Đây là mẫu minh họa, cần điều chỉnh theo transaction policy của ứng dụng. Nếu log table dùng InnoDB và INSERT log nằm trong cùng transaction với nghiệp vụ, log có thể bị rollback cùng transaction. Một số lỗi như deadlock có thể khiến transaction hiện tại bị rollback hoàn toàn. Vì vậy, không được giả định rằng ghi log trong handler luôn tạo ra bản ghi bền vững.

Nếu cần log lỗi tồn tại sau rollback, cân nhắc ghi log ở tầng ứng dụng sau khi nhận lỗi/rollback, dùng hệ thống logging bên ngoài hoặc thiết kế kênh log có transaction boundary riêng. MySQL stored program không có autonomous transaction tổng quát để tự commit độc lập trong cùng connection.

### 8.1. Bảo vệ lỗi gốc khi thao tác log thất bại

Nếu INSERT log trong handler cũng lỗi, lỗi mới có thể che lấp lỗi ban đầu hoặc làm thay đổi luồng xử lý. Các phương án:

- Bắt riêng lỗi phát sinh khi ghi log bằng nested handler.
- Không để logging làm hỏng transaction nghiệp vụ.
- Giữ các giá trị SQLSTATE/errno/message gốc trong local variable trước khi ghi log.
- Dùng RESIGNAL sau khi xử lý log theo chính sách đã định.
- Với yêu cầu audit bền vững, cân nhắc ghi nhận ở ứng dụng hoặc hệ thống log độc lập.

Không dùng MESSAGE_TEXT làm dữ liệu tin cậy để ghép vào dynamic SQL. Message có thể chứa nội dung từ dữ liệu hoặc môi trường; xử lý như dữ liệu log và giới hạn quyền truy cập.

## 9. Đọc nhiều condition

Một statement có thể phát sinh nhiều warning. GET DIAGNOSTICS có thể đọc từng condition theo số thứ tự.

Ví dụ minh họa đọc hai condition đầu:

```sql
GET DIAGNOSTICS @condition_count = NUMBER;

GET DIAGNOSTICS CONDITION 1
    @state_1 = RETURNED_SQLSTATE,
    @errno_1 = MYSQL_ERRNO,
    @message_1 = MESSAGE_TEXT;

GET DIAGNOSTICS CONDITION 2
    @state_2 = RETURNED_SQLSTATE,
    @errno_2 = MYSQL_ERRNO,
    @message_2 = MESSAGE_TEXT;
```

Chỉ chạy phần đọc CONDITION 2 nếu NUMBER ít nhất bằng 2. Nếu yêu cầu đọc nhiều condition, kiểm tra số lượng trước để tránh truy cập condition không tồn tại.

Trong cú pháp MySQL, condition_number được viết trong câu GET DIAGNOSTICS. Các ví dụ dùng số thứ tự cụ thể để thể hiện rõ condition đang đọc. Không giả định có thể thay nó bằng một biến local trong mọi phiên bản/cú pháp.

Không phải mọi ứng dụng đều cần đọc toàn bộ warning. Chọn thông tin có giá trị vận hành, ví dụ SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT; chỉ đọc metadata constraint khi lỗi liên quan đến constraint.

## 10. Phân biệt NOT FOUND với lỗi SQL

Trong stored program, NOT FOUND thường được dùng cho SQLSTATE class 02, ví dụ SELECT ... INTO không tìm thấy hàng hoặc FETCH cursor đã hết dữ liệu.

Ví dụ cursor:

```sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_order_id BIGINT UNSIGNED;

DECLARE order_cursor CURSOR FOR
    SELECT order_id
    FROM orders
    ORDER BY order_id;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

NOT FOUND không đồng nghĩa với SQLEXCEPTION. Khi cursor hết dữ liệu, handler NOT FOUND thường đặt cờ kết thúc vòng lặp. Nếu muốn ghi nhận SQLSTATE hoặc message của condition NOT FOUND, có thể dùng GET STACKED DIAGNOSTICS bên trong handler tương ứng.

Một procedure có thể có nhiều handler cho các class khác nhau. Chọn handler đúng với mục tiêu:

| Condition | Cách xử lý thường gặp |
|---|---|
| NOT FOUND | Đặt cờ kết thúc cursor hoặc xử lý không có hàng |
| SQLWARNING | Ghi nhận/cảnh báo rồi tiếp tục nếu phù hợp |
| SQLEXCEPTION | Thoát, rollback theo transaction contract hoặc RESIGNAL |
| SQLSTATE cụ thể | Xử lý một loại condition nghiệp vụ hoặc lỗi đặc biệt |

Handler precedence và phạm vi block ảnh hưởng handler nào được chọn. Đặt handler ở đúng compound block và tránh để một NOT FOUND handler vô tình bắt kết quả SELECT ... INTO không liên quan.

## 11. Kết hợp GET DIAGNOSTICS với cursor

GET DIAGNOSTICS không thay thế cursor. Cursor dùng để duyệt từng hàng trong result set; diagnostics dùng để đọc trạng thái câu lệnh và condition.

Ví dụ sau khi FETCH, handler NOT FOUND có thể xác định cursor đã hết:

```sql
DELIMITER //

CREATE PROCEDURE list_order_ids()
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE order_cursor CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN order_cursor;

    read_loop: LOOP
        FETCH order_cursor INTO v_order_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SELECT v_order_id AS order_id;
    END LOOP;

    CLOSE order_cursor;
END//

DELIMITER ;
```

Nếu muốn đọc condition đã kích hoạt NOT FOUND, thay handler đơn giản bằng block handler:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_message = MESSAGE_TEXT;
    SET v_done = TRUE;
END;
```

Lưu ý handler được khai báo sau các biến, condition và cursor trong cùng block. Không đặt DECLARE HANDLER sau câu lệnh thực thi trong block.

## 12. Phân biệt GET DIAGNOSTICS với ROW_COUNT(), SHOW WARNINGS và SIGNAL

| Công cụ | Mục đích |
|---|---|
| GET DIAGNOSTICS | Đọc statement/condition information từ diagnostics area |
| ROW_COUNT() | Hàm trả affected-row count của statement trước |
| SHOW WARNINGS | Hiển thị các warning/note/error của statement trong client |
| DECLARE ... HANDLER | Định nghĩa hành vi khi condition xảy ra |
| SIGNAL | Phát một condition mới |
| RESIGNAL | Phát lại condition từ handler |

Ví dụ ROW_COUNT():

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

SELECT ROW_COUNT();
```

Ví dụ GET DIAGNOSTICS:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

GET DIAGNOSTICS @changed = ROW_COUNT;
```

Hai cách đều có thể đọc affected-row count. GET DIAGNOSTICS hữu ích khi cần đọc thêm NUMBER hoặc condition metadata trong cùng cơ chế diagnostics.

SHOW WARNINGS phù hợp để quan sát từ client sau một statement. Trong stored program, GET DIAGNOSTICS có thể đưa các giá trị vào local variable để xử lý tiếp.

## 13. Quy trình chẩn đoán lỗi trong stored procedure

Khi một câu SQL trong procedure lỗi:

1. Xác định statement gây lỗi.
2. Kiểm tra có handler nào trong block bắt condition đó không.
3. Trong handler, dùng GET STACKED DIAGNOSTICS trước các câu lệnh phụ.
4. Lấy RETURNED_SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT.
5. Nếu cần, lấy thêm CONSTRAINT_NAME, TABLE_NAME hoặc COLUMN_NAME.
6. Quyết định lỗi có thể xử lý tiếp hay cần EXIT.
7. Nếu muốn caller nhận lỗi gốc, dùng RESIGNAL.
8. Nếu chuyển thành lỗi nghiệp vụ, dùng SIGNAL với SQLSTATE và message rõ.
9. Xác định transaction có bị rollback một phần hay toàn bộ.
10. Kiểm tra nơi ghi log có sống sót sau rollback hay không.

Mẫu handler tối thiểu:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET STACKED DIAGNOSTICS CONDITION 1
        v_state = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    RESIGNAL;
END;
```

Mẫu này giữ nguyên lỗi gốc và cho phép MySQL trả lỗi về caller. Khi cần logging hoặc chuyển đổi lỗi, thêm logic có kiểm soát nhưng luôn chụp diagnostics trước.

## 14. Những lỗi và hiểu nhầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng GET DIAGNOSTICS để thay thế handler | Lỗi vẫn làm statement/procedure thất bại | Kết hợp DECLARE HANDLER khi cần xử lý lỗi |
| Dùng CURRENT trong handler để đọc lỗi gốc sau khi đã chạy câu lệnh khác | Có thể đọc condition của câu lệnh bên trong handler | Dùng STACKED ngay đầu handler |
| Dùng STACKED bên ngoài handler | Phát sinh lỗi vì không có stacked area | Chỉ dùng STACKED khi handler đang hoạt động |
| Nhầm NUMBER với ROW_COUNT | Đọc sai số condition hoặc số hàng | NUMBER đếm condition; ROW_COUNT đo affected rows |
| Chạy SELECT trước khi lấy ROW_COUNT | Diagnostics có thể không còn thuộc DML cần đo | Chụp ROW_COUNT ngay sau DML |
| Cho rằng ROW_COUNT = 0 luôn có nghĩa không có hàng thỏa WHERE | UPDATE không đổi giá trị và CLIENT_FOUND_ROWS có thể làm cách hiểu khác | Xem affected-row semantics và kiểm tra bổ sung |
| Chỉ đọc CONDITION 1 khi có nhiều warning | Bỏ sót condition khác | Đọc NUMBER và các condition cần thiết |
| Giả định mọi condition đều có TABLE_NAME/CONSTRAINT_NAME | Giá trị có thể NULL hoặc rỗng | Xử lý giá trị không có metadata |
| Dùng MESSAGE_TEXT làm mã lỗi | Logic phụ thuộc nội dung message dễ thay đổi | Dùng SQLSTATE hoặc MYSQL_ERRNO |
| Ghi log trong transaction rồi cho rằng log luôn bền vững | Log có thể rollback cùng nghiệp vụ | Đặt logging ở transaction boundary phù hợp |
| Handler ghi log lỗi rồi làm mất lỗi gốc | Caller nhận sai nguyên nhân | Chụp STACKED trước, bảo vệ logging và RESIGNAL |
| Nhầm NOT FOUND với SQLEXCEPTION | Cursor kết thúc bị xử lý như lỗi tổng quát | Khai báo handler theo đúng condition class |

## 15. Checklist dùng GET DIAGNOSTICS trong production

**Sau DML:**

- Đặt GET DIAGNOSTICS ngay sau INSERT/UPDATE/DELETE.
- Lưu ROW_COUNT vào local variable trước khi chạy statement khác.
- Hiểu khác biệt giữa matched rows và changed rows.
- Không dùng ROW_COUNT thay COUNT(*) cho result set SELECT.
- Nếu cần phát hiện warning, đọc NUMBER.

**Trong handler:**

- Dùng GET STACKED DIAGNOSTICS để đọc condition kích hoạt handler.
- Chụp SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT trước câu lệnh phụ.
- Đọc CONDITION 1 và thêm condition khác nếu NUMBER cho thấy cần thiết.
- Phân biệt NOT FOUND, SQLWARNING và SQLEXCEPTION.
- Dùng RESIGNAL nếu cần giữ lỗi gốc.
- Dùng SIGNAL khi muốn phát lỗi nghiệp vụ mới.

**Về logging và transaction:**

- Xác định log cùng transaction hay độc lập.
- Không giả định INSERT log InnoDB sẽ sống sót sau rollback.
- Bảo vệ handler khỏi lỗi phụ khi ghi log.
- Không đưa message lỗi vào dynamic SQL.
- Giới hạn quyền đọc bảng log và dữ liệu nhạy cảm.
- Kiểm thử deadlock, constraint violation, warning và no-data path.

## 16. Ghi nhớ

- Diagnostics area lưu thông tin câu lệnh và condition mà MySQL phát sinh.
- GET DIAGNOSTICS đọc statement information hoặc condition information.
- NUMBER là số condition; ROW_COUNT là số hàng bị tác động theo statement.
- CONDITION n đọc SQLSTATE, MYSQL_ERRNO, MESSAGE_TEXT và metadata liên quan.
- CURRENT đọc diagnostics area hiện tại; STACKED đọc snapshot của condition kích hoạt handler.
- STACKED chỉ hợp lệ trong handler; dùng nó sớm để giữ lỗi gốc.
- SQLSTATE là mã 5 ký tự; MYSQL_ERRNO là mã cụ thể của MySQL; MESSAGE_TEXT phục vụ chẩn đoán.
- Đọc ROW_COUNT ngay sau DML và hiểu affected-row semantics.
- Một statement có thể tạo nhiều condition; đọc NUMBER trước khi lấy các condition tiếp theo.
- GET DIAGNOSTICS không tự bắt lỗi; kết hợp DECLARE HANDLER.
- RESIGNAL giữ và phát lại condition gốc; SIGNAL tạo condition mới.
- Log InnoDB trong cùng transaction có thể bị rollback cùng nghiệp vụ.
- NOT FOUND thường phục vụ cursor exhaustion hoặc no-data path; không đồng nhất với SQLEXCEPTION.

GET DIAGNOSTICS giúp stored program biết điều gì vừa xảy ra và vì sao một câu SQL thất bại. Hãy đọc ROW_COUNT ngay sau DML, dùng STACKED trong handler, giữ SQLSTATE và mã lỗi để chẩn đoán, rồi chọn rõ ràng giữa tiếp tục, phát lỗi nghiệp vụ hoặc RESIGNAL lỗi gốc.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — GET DIAGNOSTICS Statement: https://dev.mysql.com/doc/refman/8.0/en/get-diagnostics.html
- MySQL 8.0 Reference Manual — The Diagnostics Area: https://dev.mysql.com/doc/refman/8.0/en/diagnostics-area.html
- MySQL 8.0 Reference Manual — Condition Handling: https://dev.mysql.com/doc/refman/8.0/en/condition-handling.html
- MySQL 8.0 Reference Manual — DECLARE ... HANDLER Statement: https://dev.mysql.com/doc/refman/8.0/en/declare-handler.html
- MySQL 8.0 Reference Manual — RESIGNAL Statement: https://dev.mysql.com/doc/refman/8.0/en/resignal.html
- MySQL 8.0 Reference Manual — SIGNAL Statement: https://dev.mysql.com/doc/refman/8.0/en/signal.html
- MySQL 8.0 Reference Manual — ROW_COUNT() Function: https://dev.mysql.com/doc/refman/8.0/en/information-functions.html#function_row-count

