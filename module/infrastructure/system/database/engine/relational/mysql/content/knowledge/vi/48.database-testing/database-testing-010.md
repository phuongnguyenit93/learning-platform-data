# Kiểm thử stored procedure/function, trigger và event

## Mục tiêu

Sau bài học này, bạn có thể:

- Xác định hành vi cần kiểm thử của stored procedure, stored function, trigger và event trong MySQL.
- Tạo fixture và dữ liệu kiểm thử có thể lặp lại, đồng thời cô lập tác động giữa các test.
- Kiểm tra kết quả, side effect, lỗi SQLSTATE, quyền thực thi và hành vi transaction.
- Gọi stored procedure có tham số IN, OUT, INOUT từ SQL và Java JDBC.
- Kiểm thử trigger qua thao tác DML làm phát sinh trigger và xác minh dữ liệu audit.
- Kiểm thử event scheduler bằng cách tách logic nghiệp vụ khỏi lịch chạy và kiểm tra trạng thái event.
- Chạy kiểm thử trong MySQL thật ở môi trường cô lập và đưa vào pipeline CI.

## 1. Vì sao phải kiểm thử các đối tượng lưu trữ?

MySQL không chỉ thực thi câu SQL mà ứng dụng gửi trực tiếp. Một database có thể chứa stored procedure, function, trigger và event. Các đối tượng này thực thi logic bên trong server, thường được gọi gián tiếp thông qua một câu lệnh SQL hoặc theo lịch.

Mỗi loại đối tượng có cách kích hoạt và phạm vi trách nhiệm khác nhau:

| Đối tượng | Cách kích hoạt | Điều cần xác minh |
|---|---|---|
| Stored procedure | Ứng dụng hoặc người dùng gọi CALL | Tham số, result set, dữ liệu thay đổi, lỗi và transaction |
| Stored function | Được gọi trong biểu thức SQL | Giá trị trả về, NULL, kiểu dữ liệu, tính xác định và lỗi |
| Trigger | Tự chạy khi có INSERT, UPDATE hoặc DELETE trên bảng | Side effect, dữ liệu audit, quy tắc trước/sau thay đổi và rollback |
| Event | Event Scheduler kích hoạt theo lịch | Lịch, trạng thái, quyền DEFINER, logic được gọi và khả năng chạy lặp |

Một câu CREATE PROCEDURE chạy thành công chỉ chứng minh MySQL chấp nhận định nghĩa tại thời điểm tạo. Nó chưa chứng minh procedure xử lý đúng dữ liệu, trả đúng kết quả hoặc hoạt động với quyền của ứng dụng. Tương tự, trigger có thể được tạo thành công nhưng chưa từng được kích hoạt trong test; event có thể ở trạng thái ENABLED nhưng scheduler đang tắt.

Kiểm thử các đối tượng này cần bao gồm cả **kết quả trực tiếp** và **tác động gián tiếp**. Ví dụ, khi gọi procedure chuyển tiền, phải xác minh số dư hai tài khoản, bản ghi lịch sử, xử lý số tiền không hợp lệ và trạng thái transaction nếu có lỗi.

## 2. Xây dựng môi trường kiểm thử cô lập

Ưu tiên chạy test trên một MySQL instance riêng cho test hoặc một database/schema được tạo riêng cho từng test suite. Không dùng database production hoặc schema dùng chung với dữ liệu người dùng.

Một môi trường kiểm thử tốt có các đặc điểm:

- Dùng đúng major/minor version MySQL dự kiến triển khai, hoặc ghi rõ khác biệt phiên bản.
- Tạo schema từ migration thực tế của dự án.
- Dùng tài khoản có quyền tương tự ứng dụng nhưng chỉ giới hạn trong schema test.
- Dữ liệu fixture được tạo từ trạng thái sạch và có thể tái tạo.
- Không phụ thuộc dữ liệu tồn tại sẵn hoặc thứ tự chạy test.
- Tắt các event không thuộc test để tránh tác động nền ngoài dự kiến.
- Thu thập log, SQLSTATE và kết quả truy vấn khi test thất bại.

Không thay MySQL bằng H2 rồi coi kết quả là kiểm thử tương đương. Cú pháp routine, trigger, event, kiểu dữ liệu, transaction, SQL mode và hành vi locking của MySQL có thể khác. H2 có thể hữu ích cho test repository đơn giản, nhưng các test kiểm chứng đối tượng MySQL phải chạy trên MySQL.

### 2.1. Khởi tạo schema kiểm thử

Ví dụ schema phục vụ bài thực hành:

~~~sql
CREATE DATABASE IF NOT EXISTS routine_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE routine_test;

CREATE TABLE account (
    account_id BIGINT NOT NULL PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    CONSTRAINT chk_account_balance_nonnegative
      CHECK (balance >= 0)
) ENGINE=InnoDB;

CREATE TABLE transfer_audit (
    audit_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    old_balance DECIMAL(15, 2) NOT NULL,
    new_balance DECIMAL(15, 2) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE expired_session (
    session_id BIGINT NOT NULL PRIMARY KEY,
    expires_at DATETIME NOT NULL,
    cleaned_at DATETIME NULL
) ENGINE=InnoDB;
~~~

Đây là schema nhỏ để kiểm thử procedure, function, trigger và event. Trong dự án thực tế, nên lấy DDL từ migration của ứng dụng để test đúng cấu trúc được triển khai.

### 2.2. Fixture và cleanup

Fixture là dữ liệu đầu vào được tạo trước test. Mỗi test nên biết chính xác trạng thái ban đầu:

~~~sql
DELETE FROM transfer_audit;
DELETE FROM account;

INSERT INTO account(account_id, owner_name, balance)
VALUES
  (101, 'Lan', 1000.00),
  (202, 'Minh', 500.00);
~~~

Với test chạy lặp lại, có thể xóa dữ liệu theo khóa định danh riêng của test hoặc rollback transaction nếu đối tượng được kiểm thử không tự commit. Không dùng TRUNCATE như một cách cleanup bên trong transaction cần rollback, vì DDL như TRUNCATE TABLE gây implicit commit trong MySQL.

Test không nên phụ thuộc thứ tự chạy. Nếu test A để lại audit row thì test B không được giả định bảng audit rỗng trừ khi B tự tạo fixture hoặc có cơ chế cleanup rõ ràng.

## 3. Kiểm thử stored procedure

Stored procedure được gọi bằng CALL. Procedure có thể nhận tham số IN, trả giá trị qua OUT/INOUT, trả một hoặc nhiều result set, cập nhật dữ liệu và phát sinh lỗi bằng SIGNAL.

Khi kiểm thử procedure, hãy xác định:

- Tham số đầu vào hợp lệ, biên và không hợp lệ.
- Giá trị OUT/INOUT sau khi thực thi.
- Các result set được trả về, số hàng và nội dung.
- Dữ liệu được INSERT, UPDATE hoặc DELETE.
- Hành vi khi không tìm thấy bản ghi.
- Hành vi khi vi phạm constraint hoặc phát sinh SQL exception.
- Transaction thuộc quyền điều khiển của procedure hay caller.
- Quyền cần thiết của user gọi procedure và DEFINER.

### 3.1. Tạo procedure mẫu

Procedure sau chuyển tiền giữa hai tài khoản. Nó kiểm tra số tiền, tài khoản nguồn/đích và số dư trước khi cập nhật.

~~~sql
DELIMITER //

CREATE PROCEDURE transfer_money(
    IN p_from BIGINT,
    IN p_to BIGINT,
    IN p_amount DECIMAL(15, 2),
    OUT p_result VARCHAR(30)
)
BEGIN
    DECLARE v_from_balance DECIMAL(15, 2);
    DECLARE v_to_balance DECIMAL(15, 2);
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;

    IF p_from IS NULL OR p_to IS NULL THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Account identifiers are required';
    END IF;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Amount must be positive';
    END IF;

    IF p_from = p_to THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Source and destination must differ';
    END IF;

    SET v_not_found = FALSE;
    SELECT balance
      INTO v_from_balance
      FROM account
     WHERE account_id = p_from
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Source account not found';
    END IF;

    SET v_not_found = FALSE;
    SELECT balance
      INTO v_to_balance
      FROM account
     WHERE account_id = p_to
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Destination account not found';
    END IF;

    IF v_from_balance < p_amount THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Insufficient funds';
    END IF;

    UPDATE account
       SET balance = balance - p_amount
     WHERE account_id = p_from;

    UPDATE account
       SET balance = balance + p_amount
     WHERE account_id = p_to;

    SET p_result = 'TRANSFERRED';
END//

DELIMITER ;
~~~

Procedure mẫu không gọi START TRANSACTION, COMMIT hoặc ROLLBACK. Nó chạy trong transaction của caller nếu caller mở transaction; nếu caller dùng autocommit, các thay đổi trong CALL thuộc transaction statement do session quản lý. Để kiểm thử tính nguyên tử, caller nên mở transaction rõ ràng.

Handler CONTINUE FOR NOT FOUND đặt cờ khi SELECT ... INTO không tìm thấy hàng. Procedure kiểm tra cờ sau từng SELECT rồi phát SQLSTATE nghiệp vụ riêng. Với cột balance đã khai báo NOT NULL, cờ này phân biệt rõ trường hợp không có tài khoản với một giá trị balance hợp lệ.

### 3.2. Test trường hợp thành công

Chuẩn bị fixture rồi gọi procedure:

~~~sql
START TRANSACTION;

CALL transfer_money(101, 202, 125.00, @result);

SELECT @result AS transfer_result;

SELECT account_id, balance
FROM account
WHERE account_id IN (101, 202)
ORDER BY account_id;

ROLLBACK;
~~~

Kết quả mong đợi trong transaction:

| account_id | Số dư trước | Số dư sau CALL |
|---:|---:|---:|
| 101 | 1000.00 | 875.00 |
| 202 | 500.00 | 625.00 |

@result phải là TRANSFERRED. Sau ROLLBACK, truy vấn lại trong session khác phải cho thấy số dư vẫn là 1000.00 và 500.00. Test này kiểm tra cả kết quả procedure và việc procedure không tự commit.

### 3.3. Test đầu vào không hợp lệ

Các trường hợp cần có:

| Trường hợp | Input ví dụ | Kết quả mong đợi |
|---|---|---|
| Số tiền bằng 0 | 0.00 | SQLSTATE 45000, không đổi số dư |
| Số tiền âm | -10.00 | SQLSTATE 45000, không đổi số dư |
| Số tiền NULL | NULL | SQLSTATE 45000 |
| Cùng tài khoản | 101 -> 101 | SQLSTATE 45000 |
| Tài khoản nguồn không tồn tại | 999 -> 202 | Lỗi được xử lý theo hợp đồng procedure |
| Tài khoản đích không tồn tại | 101 -> 999 | Lỗi được xử lý theo hợp đồng procedure |
| Không đủ số dư | 101 -> 202, số tiền lớn hơn balance | SQLSTATE 45000 |

Với mỗi trường hợp lỗi, không chỉ kiểm tra exception. Hãy xác minh không có side effect ngoài dự kiến, số dư vẫn đúng và transaction có thể được rollback.

Ví dụ kiểm tra lỗi:

~~~sql
START TRANSACTION;

CALL transfer_money(101, 202, -10.00, @result);

-- Lệnh CALL dự kiến phát sinh SQLSTATE 45000.
-- Client kiểm tra lỗi rồi rollback transaction.
ROLLBACK;
~~~

MySQL client có thể dừng thực thi script ở câu lệnh lỗi tùy chế độ chạy. Trong test automation, hãy bắt lỗi tại client/framework, kiểm tra SQLSTATE và luôn cleanup transaction trong khối finally/teardown.

### 3.4. Kiểm tra transaction và lỗi giữa chừng

Một procedure có thể cập nhật nhiều bảng. Nếu câu lệnh thứ hai lỗi sau khi câu đầu đã chạy, caller phải biết transaction còn hoạt động hay đã bị rollback. Với InnoDB, lỗi SQL thông thường không tự động rollback toàn bộ transaction trong mọi trường hợp.

Thiết kế procedure và test phải làm rõ:

- Procedure có tự mở/commit transaction hay không.
- Procedure có dùng EXIT HANDLER để rollback và RESIGNAL hay không.
- Caller chịu trách nhiệm commit/rollback đến đâu.
- Có thể gọi procedure bên trong transaction lớn hơn không.

Nếu procedure tự quản lý transaction bằng COMMIT/ROLLBACK, không nên gọi nó trong một transaction caller mong muốn rollback toàn bộ. Kiểm thử hợp đồng transaction bằng cách tạo lỗi ở từng bước quan trọng và xác minh dữ liệu sau lỗi.

## 4. Kiểm thử stored function

Stored function trả về một giá trị và có thể được dùng trong biểu thức SQL. Test function thường tập trung vào:

- Giá trị trả về cho input hợp lệ.
- Biên dưới, biên trên, NULL và giá trị không hợp lệ.
- Quy tắc làm tròn và kiểu dữ liệu.
- Tính xác định nếu function được kỳ vọng deterministic.
- Side effect được phép hoặc bị cấm.
- SQL mode, collation và timezone ảnh hưởng đến kết quả.

### 4.1. Tạo function mẫu

Ví dụ function tính phí dịch vụ 2%:

~~~sql
DELIMITER //

CREATE FUNCTION calculate_fee(
    p_amount DECIMAL(15, 2)
)
RETURNS DECIMAL(15, 2)
DETERMINISTIC
CONTAINS SQL
BEGIN
    IF p_amount IS NULL OR p_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Amount must be nonnegative';
    END IF;

    RETURN ROUND(p_amount * 0.02, 2);
END//

DELIMITER ;
~~~

Function khai báo DETERMINISTIC vì cùng input phải tạo cùng output và không đọc trạng thái thay đổi. CONTAINS SQL phù hợp vì phần thân có dùng câu lệnh SIGNAL nhưng không đọc/ghi bảng. Những characteristic này phải phản ánh hành vi thực tế; không khai báo chỉ để làm lệnh CREATE thành công.

### 4.2. Test giá trị và biên

~~~sql
SELECT calculate_fee(100.00) AS fee_100;
SELECT calculate_fee(0.00) AS fee_zero;
SELECT calculate_fee(123.45) AS fee_fraction;
~~~

Kết quả mong đợi:

| Input | Kết quả |
|---:|---:|
| 100.00 | 2.00 |
| 0.00 | 0.00 |
| 123.45 | 2.47 |

Gọi function với NULL hoặc số âm phải tạo SQLSTATE 45000. Khi test số thập phân, dùng kiểu DECIMAL/BigDecimal thay vì FLOAT/DOUBLE để tránh sai số biểu diễn nhị phân.

### 4.4. Giới hạn cần tính khi viết test

Stored function được dùng như một biểu thức SQL nên không thể trả một result set tùy ý như procedure. Function cũng bị giới hạn về transaction control và một số thao tác SQL động. Vì vậy:

- Kiểm tra function qua giá trị trả về trong SELECT, biểu thức WHERE hoặc projection.
- Không thiết kế function để gọi COMMIT/ROLLBACK hoặc trả nhiều result set.
- Nếu logic cần thực hiện nhiều thao tác ghi, trả nhiều kết quả hoặc điều khiển transaction, cân nhắc stored procedure.
- Khi function đọc bảng, kiểm tra quyền, dữ liệu thay đổi đồng thời và chi phí gọi theo từng hàng.

### 4.3. Test function trong truy vấn thực tế

Function có thể đúng khi gọi riêng nhưng tạo hành vi không mong muốn khi dùng trong truy vấn lớn. Kiểm tra cách ứng dụng sử dụng:

~~~sql
SELECT
    account_id,
    balance,
    calculate_fee(balance) AS estimated_fee
FROM account
ORDER BY account_id;
~~~

Đánh giá số lần function được gọi, execution plan và tác động lên truy vấn. Function được gọi cho từng hàng có thể làm tăng CPU hoặc ngăn một số tối ưu hóa. Không đặt logic nặng vào function chỉ để làm câu SQL ngắn hơn.

## 5. Kiểm thử trigger

Trigger tự chạy khi có thao tác DML trên bảng. Trigger có thể được định nghĩa cho BEFORE hoặc AFTER của INSERT, UPDATE, DELETE.

Khi kiểm thử trigger, phải thực hiện DML thực tế lên bảng kích hoạt rồi kiểm tra:

- Giá trị NEW được thay đổi đúng trong BEFORE trigger.
- Side effect được ghi đúng trong AFTER trigger.
- Trigger chạy đúng một lần cho mỗi row event theo ngữ nghĩa row-level của MySQL.
- Trigger xử lý NULL, dữ liệu biên và điều kiện bỏ qua.
- Lỗi trong trigger có làm statement gốc thất bại hay không.
- Transaction rollback có hoàn tác side effect trên bảng InnoDB hay không.
- Trigger có xung đột với foreign key, constraint hoặc trigger khác không.

MySQL trigger là row-level trigger; không có cú pháp statement-level trigger như một số hệ quản trị khác.

### 5.1. Tạo trigger audit

Trigger ghi lại thay đổi số dư:

~~~sql
DELIMITER //

CREATE TRIGGER trg_account_balance_audit
AFTER UPDATE ON account
FOR EACH ROW
BEGIN
    IF NOT (OLD.balance <=> NEW.balance) THEN
        INSERT INTO transfer_audit(
            account_id,
            old_balance,
            new_balance
        )
        VALUES (
            NEW.account_id,
            OLD.balance,
            NEW.balance
        );
    END IF;
END//

DELIMITER ;
~~~

Trigger dùng toán tử <=> để so sánh NULL-safe. Với cột balance đã khai báo NOT NULL, có thể dùng <>, nhưng NULL-safe comparison làm điều kiện rõ ràng hơn nếu schema thay đổi.

### 5.2. Test trigger khi UPDATE

Chuẩn bị dữ liệu và thực hiện update:

~~~sql
DELETE FROM transfer_audit;

UPDATE account
SET balance = balance + 25.00
WHERE account_id = 101;

SELECT account_id, old_balance, new_balance
FROM transfer_audit
WHERE account_id = 101
ORDER BY audit_id;
~~~

Mong đợi có một audit row với old_balance=1000.00 và new_balance=1025.00.

Tiếp theo update cùng giá trị:

~~~sql
UPDATE account
SET balance = balance
WHERE account_id = 101;
~~~

Không nên tạo audit row mới nếu giá trị không đổi. Test này kiểm tra điều kiện trong trigger, không chỉ kiểm tra trigger có tồn tại.

### 5.3. Test rollback side effect

Vì cả account và transfer_audit dùng InnoDB, side effect do trigger tạo ra nằm trong cùng transaction với statement kích hoạt:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance + 10.00
WHERE account_id = 101;

SELECT COUNT(*) AS audit_inside_transaction
FROM transfer_audit
WHERE account_id = 101;

ROLLBACK;
~~~

Trong transaction, audit row đã xuất hiện. Sau rollback, cả balance lẫn audit row phải trở về trạng thái trước transaction. Nếu audit table dùng engine không hỗ trợ transaction, side effect có thể không rollback cùng bảng chính; vì vậy, engine của tất cả bảng liên quan là một phần của hợp đồng cần kiểm thử.

### 5.4. Test trigger làm statement thất bại

Tạo một trigger hoặc điều kiện test khiến trigger phát sinh lỗi:

~~~sql
DELIMITER //

CREATE TRIGGER trg_account_reject_negative
BEFORE UPDATE ON account
FOR EACH ROW
BEGIN
    IF NEW.balance < 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Balance cannot be negative';
    END IF;
END//

DELIMITER ;
~~~

Test:

~~~sql
UPDATE account
SET balance = -1.00
WHERE account_id = 101;
~~~

Mong đợi statement thất bại với SQLSTATE 45000, balance không đổi và không phát sinh audit row. Đây là kiểm thử quan trọng vì lỗi trong trigger có thể khiến thao tác DML của ứng dụng thất bại dù câu SQL bên ngoài có vẻ hợp lệ.

Không tạo nhiều trigger cùng timing/event mà không kiểm tra thứ tự thực thi. MySQL hỗ trợ nhiều trigger cùng thời điểm và event trong các phiên bản hiện đại, nhưng thứ tự cần được khai báo/kiểm tra rõ ràng bằng FOLLOWS hoặc PRECEDES khi có phụ thuộc. Tốt nhất giảm phụ thuộc thứ tự bằng cách thiết kế trigger độc lập.

### 5.5. Những đường đi không kích hoạt trigger

Test cần mô phỏng đúng thao tác thực tế. Trigger được kích hoạt bởi INSERT, UPDATE hoặc DELETE trên bảng tương ứng, nhưng một số cơ chế của MySQL không đi qua trigger như người viết test có thể nghĩ:

- Các hành động cascade do foreign key như ON DELETE CASCADE hoặc ON UPDATE CASCADE không kích hoạt trigger trên bảng con.
- Thao tác trực tiếp trên bảng con vẫn kích hoạt trigger tương ứng.
- Một câu lệnh DML ảnh hưởng nhiều hàng kích hoạt trigger một lần cho mỗi hàng bị tác động.

Nếu audit hoặc nghiệp vụ phụ thuộc vào thay đổi do foreign key cascade, không giả định trigger trên bảng con sẽ ghi nhận các thay đổi đó. Hãy kiểm thử hành vi thực tế và thiết kế audit ở lớp phù hợp.

## 6. Kiểm thử event và Event Scheduler

Event là một đối tượng được MySQL Event Scheduler thực thi theo thời gian hoặc lịch lặp. Event có thể gọi procedure, cập nhật bảng hoặc thực hiện tác vụ bảo trì.

Có hai phần phải kiểm thử riêng:

1. **Logic công việc:** procedure hoặc câu lệnh mà event thực hiện.
2. **Cơ chế lập lịch:** event được tạo đúng, trạng thái ENABLED, scheduler đang bật, thời gian chạy hợp lệ và DEFINER có quyền.

Không nên dùng thời gian chờ thực tế dài trong unit test để chứng minh logic nghiệp vụ. Hãy tách công việc thành stored procedure có thể gọi trực tiếp, test procedure một cách xác định, sau đó có một integration test riêng kiểm tra event scheduler.

### 6.1. Tạo procedure dọn session hết hạn

~~~sql
DELIMITER //

CREATE PROCEDURE clean_expired_sessions()
BEGIN
    UPDATE expired_session
       SET cleaned_at = CURRENT_TIMESTAMP
     WHERE expires_at < CURRENT_TIMESTAMP
       AND cleaned_at IS NULL;
END//

DELIMITER ;
~~~

Procedure có thể được gọi trực tiếp trong test:

~~~sql
UPDATE expired_session
SET cleaned_at = NULL;

CALL clean_expired_sessions();

SELECT session_id, cleaned_at
FROM expired_session
ORDER BY session_id;
~~~

Fixture nên có session đã hết hạn, session chưa hết hạn và session đã được xử lý. Mong đợi chỉ các session hết hạn chưa được cleanup có cleaned_at được gán.

### 6.2. Tạo event

~~~sql
CREATE EVENT ev_clean_expired_sessions
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
ON COMPLETION PRESERVE
ENABLE
DO
    CALL clean_expired_sessions();
~~~

Event được lên lịch mỗi ngày và giữ lại sau khi chạy. Event có thể được đặt DISABLE để tạo trước nhưng chưa chạy, hoặc được enable trong quá trình triển khai. Trạng thái cuối cùng phải khớp với mục tiêu vận hành.

### 6.3. Kiểm tra event metadata

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STATUS,
    LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'routine_test'
  AND EVENT_NAME = 'ev_clean_expired_sessions';
~~~

Kiểm tra:

- Event tồn tại trong đúng schema.
- STATUS là ENABLED khi cần chạy.
- DEFINER tồn tại và có quyền cần thiết.
- Time zone và thời điểm chạy đúng yêu cầu.
- LAST_EXECUTED được cập nhật sau khi event thực sự chạy.

LAST_EXECUTED có thể vẫn NULL trước lần chạy đầu tiên. Event Scheduler không phải bộ lập lịch thời gian thực; thời điểm chạy có thể trễ so với thời gian dự kiến do tải server hoặc scheduler. Không viết test đòi hỏi event chạy chính xác tại một mili giây cụ thể.

### 6.4. Kiểm tra Event Scheduler

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';

SHOW PROCESSLIST;
~~~

Giá trị event_scheduler phải là ON để event được thực thi. Giá trị OFF có nghĩa scheduler không chạy event; DISABLED có nghĩa scheduler bị vô hiệu hóa và không thể bật động theo cách thông thường.

Trong môi trường test dùng chung, không tự ý đổi global event_scheduler vì có thể ảnh hưởng event của schema khác. Dùng MySQL instance riêng cho test. Việc bật scheduler có thể cần quyền quản trị phù hợp và có thể bị giới hạn bởi cấu hình server.

### 6.5. Test event theo cách xác định

Để kiểm tra logic, gọi trực tiếp procedure clean_expired_sessions() và xác minh dữ liệu. Để kiểm tra integration của scheduler:

1. Tạo event test với thời điểm chạy gần hiện tại trên instance riêng.
2. Xác nhận scheduler ON và event ENABLED.
3. Poll trạng thái dữ liệu hoặc LAST_EXECUTED trong một timeout hợp lý.
4. Xác nhận side effect đúng và chỉ xảy ra theo mong đợi.
5. Disable hoặc drop event sau test.

Không dùng DO SLEEP() trong test để chờ event nếu có thể poll theo điều kiện với deadline. Test phải có timeout để không treo CI khi scheduler không hoạt động.

## 7. Kiểm thử quyền DEFINER và SQL SECURITY

Stored routine, view, trigger và event có thể thực thi theo quyền của DEFINER hoặc INVOKER, tùy loại đối tượng và thuộc tính bảo mật.

Đối với procedure/function, SQL SECURITY DEFINER thường thực thi với quyền của tài khoản definer; SQL SECURITY INVOKER thực thi theo quyền người gọi. Trigger và event có ngữ cảnh definer theo cơ chế của MySQL.

Kiểm thử quyền cần có ít nhất:

- Tài khoản ứng dụng có quyền EXECUTE trên procedure cần gọi.
- Tài khoản ứng dụng không có quyền trực tiếp vượt quá thiết kế đối với bảng nhạy cảm nếu procedure là lớp kiểm soát.
- DEFINER tồn tại và có đúng quyền cần thiết.
- User thiếu quyền nhận lỗi dự kiến.
- Không có đối tượng chạy với tài khoản root hoặc quyền rộng không cần thiết.

Ví dụ kiểm tra:

~~~sql
SHOW CREATE PROCEDURE routine_test.transfer_money;
SHOW CREATE FUNCTION routine_test.calculate_fee;
SHOW CREATE TRIGGER routine_test.trg_account_balance_audit;
SHOW CREATE EVENT routine_test.ev_clean_expired_sessions;
~~~

Kết quả SHOW CREATE giúp xác nhận DEFINER, SQL SECURITY, SQL mode lưu cùng routine và định nghĩa thực tế đang triển khai. Khi chạy test với user ứng dụng, hãy mở connection bằng chính user đó thay vì chỉ kiểm thử bằng root.

Một test chạy thành công bằng root không chứng minh ứng dụng có quyền phù hợp. Ngược lại, nếu DEFINER bị thiếu sau khi restore/migration, routine hoặc event có thể lỗi khi thực thi dù định nghĩa vẫn tồn tại.

## 8. Kiểm thử từ Java JDBC và Spring

Các đối tượng lưu trữ thường được gọi từ ứng dụng. Vì vậy, ngoài SQL test trực tiếp, cần kiểm tra driver có đọc đúng OUT parameter, result set và SQLException hay không.

### 8.1. Gọi procedure có OUT parameter bằng JDBC

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement call = connection.prepareCall(
         "{call transfer_money(?, ?, ?, ?)}")) {

    call.setLong(1, 101L);
    call.setLong(2, 202L);
    call.setBigDecimal(3, new BigDecimal("125.00"));
    call.registerOutParameter(4, Types.VARCHAR);

    call.execute();

    String result = call.getString(4);
    assertEquals("TRANSFERRED", result);
}
~~~

Nếu test cần xác minh transaction rollback, hãy cấu hình connection.setAutoCommit(false), gọi procedure, đọc lại dữ liệu trong cùng connection rồi rollback. Sau đó dùng connection khác để xác minh dữ liệu đã trở về trạng thái ban đầu.

### 8.2. Gọi function bằng JDBC

Function có thể được gọi qua câu SELECT:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT calculate_fee(?)")) {

    statement.setBigDecimal(1, new BigDecimal("123.45"));

    try (ResultSet resultSet = statement.executeQuery()) {
        assertTrue(resultSet.next());
        assertEquals(
            0,
            new BigDecimal("2.47").compareTo(
                resultSet.getBigDecimal(1)
            )
        );
    }
}
~~~

So sánh BigDecimal bằng compareTo() khi muốn so giá trị số mà không phụ thuộc scale. equals() cũng so sánh scale, vì vậy 2.0 và 2.00 không bằng nhau theo equals dù giá trị số tương đương.

### 8.3. Kiểm tra SQLException

Khi procedure/function/trigger phát SIGNAL, Connector/J chuyển lỗi thành SQLException. Test nên kiểm tra SQLState thay vì chỉ so sánh message vì thông điệp có thể thay đổi:

~~~java
SQLException error = assertThrows(
    SQLException.class,
    () -> call.execute()
);

assertEquals("45000", error.getSQLState());
~~~

Mã vendor error và message có thể hữu ích để chẩn đoán, nhưng SQLSTATE thường là phần hợp đồng ổn định hơn cho lỗi nghiệp vụ tùy chỉnh.

### 8.4. Kiểm tra nhiều result set

Stored procedure có thể trả nhiều result set. Khi gọi bằng CallableStatement, cần duyệt các kết quả bằng execute(), getResultSet(), getMoreResults() và kiểm tra update count theo JDBC contract. Đừng chỉ gọi executeQuery() nếu procedure có thể trả nhiều loại kết quả.

Nếu dùng Spring JdbcTemplate hoặc SimpleJdbcCall, kiểm tra rõ mapping tên tham số, kiểu SQL, OUT parameter và result set mapper. Metadata discovery có thể khác nhau theo driver/server; trong test ổn định, khai báo tham số rõ ràng khi cần.

## 9. Kiểm thử lỗi, handler và diagnostics

Stored program có thể khai báo DECLARE ... HANDLER để xử lý condition. Test cần bao gồm cả đường thành công và đường handler.

Ví dụ procedure có handler:

~~~sql
DELIMITER //

CREATE PROCEDURE insert_account(
    IN p_id BIGINT,
    IN p_name VARCHAR(100),
    IN p_balance DECIMAL(15, 2)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO account(account_id, owner_name, balance)
    VALUES (p_id, p_name, p_balance);

    COMMIT;
END//

DELIMITER ;
~~~

Procedure này tự quản lý transaction. Không gọi nó trong một transaction caller muốn giữ quyền rollback, vì START TRANSACTION/COMMIT bên trong làm thay đổi transaction context của session. Đây là ví dụ để kiểm tra handler và không nên áp dụng máy móc cho mọi procedure.

Test các trường hợp:

- Insert thành công.
- Trùng primary key.
- Vi phạm CHECK constraint.
- Giá trị NULL ở cột NOT NULL.
- Lỗi ở bước sau khi đã có thay đổi trước đó.
- Handler rollback và RESIGNAL trả lỗi về caller.

Nếu handler nuốt lỗi mà không RESIGNAL, ứng dụng có thể nhận kết quả thành công giả. Test cần xác nhận hợp đồng lỗi mà ứng dụng dựa vào.

## 10. Kiểm tra metadata và trạng thái đối tượng

Có thể dùng information_schema để xác nhận đối tượng đã được tạo:

~~~sql
SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE,
       DEFINER, SECURITY_TYPE, SQL_DATA_ACCESS
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'routine_test'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;

SELECT TRIGGER_SCHEMA, TRIGGER_NAME, EVENT_MANIPULATION,
       EVENT_OBJECT_TABLE, ACTION_TIMING, DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'routine_test'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;

SELECT EVENT_SCHEMA, EVENT_NAME, STATUS, DEFINER, LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'routine_test'
ORDER BY EVENT_NAME;
~~~

Metadata test phù hợp để kiểm tra migration hoặc deployment đã tạo đúng đối tượng. Tuy nhiên, metadata tồn tại không thay thế behavior test. Một procedure có thể đúng tên và đúng DEFINER nhưng logic bên trong sai.

So sánh SHOW CREATE hoặc metadata với phiên bản schema mong muốn trong migration. Nếu dùng checksum định nghĩa, chuẩn hóa whitespace hoặc metadata không ổn định trước khi so sánh; không coi khác biệt định dạng là khác biệt logic.

## 11. Test migration thay đổi stored object

Stored object là một phần của schema version. Khi thay đổi routine, trigger hoặc event, cần kiểm tra:

- Migration có thể chạy từ database trống.
- Migration nâng cấp từ version trước có thay thế đúng object.
- DROP ... IF EXISTS và CREATE không để lại khoảng thời gian ứng dụng gọi object không tồn tại nếu deploy online.
- DEFINER và quyền được giữ đúng trên môi trường đích.
- SQL mode, character set và collation của routine phù hợp.
- Rollback hoặc forward migration được xác định rõ.

MySQL DDL thường gây implicit commit. Không giả định có thể rollback một loạt DROP PROCEDURE, CREATE PROCEDURE, CREATE TRIGGER như một transaction dữ liệu thông thường. Với thay đổi đang phục vụ traffic, hãy thiết kế thứ tự triển khai để ứng dụng tương thích trong suốt khoảng thay object.

Ví dụ kiểm tra sau migration:

~~~sql
SELECT ROUTINE_NAME
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'routine_test'
  AND ROUTINE_NAME = 'transfer_money';

SHOW CREATE PROCEDURE routine_test.transfer_money;
~~~

Sau đó chạy behavior test thành công và thất bại để xác nhận logic mới thực sự hoạt động.

## 12. Kiểm thử concurrency và tính lặp lại

Stored procedure và trigger thường được gọi đồng thời từ nhiều connection. Test đơn luồng có thể bỏ sót race condition, deadlock hoặc mất cập nhật.

Các tình huống nên kiểm tra:

- Hai transaction cùng chuyển tiền từ một tài khoản.
- Hai request đồng thời cập nhật cùng một hàng.
- Hai transaction cập nhật nhiều hàng theo thứ tự khóa khác nhau.
- Trigger ghi vào bảng audit có index/unique constraint.
- Event chạy cùng lúc với tác vụ ứng dụng cập nhật bảng đích.
- Procedure được gọi lặp lại sau timeout khi caller không biết lần trước đã commit hay chưa.

Ví dụ kiểm thử đồng thời không đủ chỉ dùng hai câu UPDATE trong một session. Cần hai connection riêng, đồng bộ thời điểm bắt đầu và xác minh kết quả cuối cùng sau khi cả hai hoàn tất.

Trong procedure chuyển tiền mẫu, hai transaction chuyển tiền ngược chiều có thể khóa tài khoản theo thứ tự khác nhau và tạo deadlock. Có thể giảm rủi ro bằng cách khóa các tài khoản theo thứ tự account_id nhất quán, đồng thời ứng dụng phải xử lý deadlock (ví dụ lỗi MySQL 1213) bằng cách rollback và retry toàn bộ transaction với giới hạn/backoff. Không retry riêng câu UPDATE cuối cùng.

Nếu một procedure đại diện thao tác nghiệp vụ có thể được retry, hãy thiết kế idempotency key hoặc bảng request ledger. Test gọi cùng request hai lần và xác minh không tạo side effect trùng.

Với trigger audit, xác định audit row được tạo cho mỗi thay đổi thực tế hay cho mỗi câu lệnh. Trong MySQL row-level trigger chạy theo từng hàng bị tác động; câu UPDATE ảnh hưởng 100 hàng có thể tạo 100 audit row.

## 13. Kiểm thử event không tạo side effect ngoài dự kiến

Event có thể chạy tự động ngay khi được enable. Trong test và triển khai:

- Dùng tên event riêng cho test.
- Đặt lịch ngắn nhưng có timeout kiểm thử.
- Chỉ chạy trên instance/schema test.
- Chuẩn bị dữ liệu có khóa định danh riêng.
- Xác minh số hàng được tác động và điều kiện lọc.
- Disable/drop event trong teardown.
- Không để event test tồn tại sau khi pipeline kết thúc.

Một event lặp lại phải được kiểm tra tính idempotent. Nếu job chạy hai lần, dữ liệu có bị xử lý trùng không? Nếu lần đầu thất bại giữa chừng, lần tiếp theo có thể tiếp tục an toàn không?

Event Scheduler là cơ chế chạy bên trong MySQL Server. Nếu server restart, scheduler và event behavior phụ thuộc cấu hình server và trạng thái event đã lưu. Cần kiểm tra sau restart trong integration test hoặc deployment test, thay vì chỉ kiểm tra ngay sau CREATE EVENT.

## 14. Tổ chức test suite

Một bộ test hữu ích có thể chia thành các lớp:

| Lớp test | Phạm vi | Ví dụ |
|---|---|---|
| SQL behavior test | Logic procedure/function/trigger | Input hợp lệ, biên, side effect, SQLSTATE |
| JDBC integration test | Cách ứng dụng gọi stored object | CallableStatement, OUT param, result set, exception |
| Permission test | Quyền INVOKER/DEFINER | App user gọi được procedure nhưng không đọc trực tiếp bảng |
| Migration test | Định nghĩa sau deploy | Object tồn tại, signature, DEFINER, SQL mode |
| Scheduler test | Event Scheduler | Event enabled, chạy, cập nhật LAST_EXECUTED và cleanup |
| Concurrency test | Nhiều session | Deadlock, lost update, idempotency, side effect trùng |

Không cần mọi test suite chạy cùng tần suất. Test logic và JDBC có thể chạy mỗi pull request trên MySQL container. Test scheduler, concurrency tải lớn hoặc nâng cấp phiên bản có thể chạy trong pipeline integration/nightly phù hợp.

### 14.1. Dùng Testcontainers hoặc MySQL instance riêng

Với Java, Testcontainers có thể khởi chạy MySQL thật cho integration test. Ví dụ phụ thuộc Maven minh họa:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mysql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ JUnit 5:

~~~java
@Testcontainers
class StoredProcedureIT {
    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("routine_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void procedureTransfersMoney() throws Exception {
        // Chạy migration/schema fixture trên container.
        // Gọi procedure qua JDBC.
        // Assert kết quả và side effect.
    }
}
~~~

Tag image phải được pin theo phiên bản cần kiểm thử; không dùng tag latest trong CI vì kết quả có thể thay đổi bất ngờ. Tài khoản test và mật khẩu minh họa chỉ dùng trong container dùng một lần, không tái sử dụng cho môi trường thật.

Một số test event cần quyền hoặc cấu hình global đặc biệt. Kiểm tra image và cấu hình container có cho phép bật Event Scheduler hay không. Nếu test không thể bật scheduler, vẫn có thể kiểm thử procedure mà event gọi và dùng một integration environment riêng để xác nhận scheduler.

### 14.2. Fixture qua migration

Test nên áp dụng migration tạo routine, function, trigger và event giống quá trình triển khai thật. Có thể dùng script SQL riêng cho test data nhưng không nên copy lại định nghĩa object bằng một bản khác, vì khi đó test không còn xác minh artifact được deploy.

Khi test tạo object bằng script, chú ý DELIMITER là lệnh của MySQL client, không phải câu lệnh SQL gửi qua JDBC. Với JDBC, gửi nguyên câu CREATE PROCEDURE ... BEGIN ... END như một statement phù hợp, không thêm lệnh DELIMITER.

## 15. Các lỗi kiểm thử thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Procedure test pass bằng root nhưng fail ở ứng dụng | Quyền EXECUTE, DEFINER hoặc quyền bảng khác nhau | Chạy test bằng account ứng dụng và kiểm tra SHOW GRANTS |
| Trigger không chạy trong test | Test chỉ kiểm tra metadata hoặc thao tác sai bảng/event | Thực hiện INSERT/UPDATE/DELETE thật trên bảng kích hoạt |
| Audit row vẫn còn sau rollback | Bảng side effect dùng engine nontransactional hoặc test đã commit | Dùng InnoDB và xác định ranh giới transaction |
| Event không chạy | Event Scheduler OFF/DISABLED, event DISABLED hoặc DEFINER lỗi | Kiểm tra global variable, metadata và log server |
| Event test không ổn định | Test yêu cầu thời gian chạy chính xác hoặc scheduler bị tải | Dùng timeout, poll điều kiện và tách logic khỏi lịch |
| JDBC không đọc được OUT parameter | Chưa register đúng SQL type hoặc gọi procedure sai cách | Dùng CallableStatement và đăng ký OUT trước execute |
| So sánh DECIMAL thất bại | Dùng BigDecimal.equals() và scale khác nhau | Dùng compareTo() hoặc assert theo scale mong muốn |
| Test phụ thuộc thứ tự | Fixture/cleanup không độc lập | Reset dữ liệu theo test ID hoặc dùng schema riêng |
| Migration pass nhưng logic sai | Chỉ kiểm tra CREATE thành công | Chạy behavior test sau migration |
| Script dừng ở DELIMITER khi chạy JDBC | Gửi lệnh client như SQL server | Bỏ DELIMITER trong JDBC; giữ delimiter trong script chạy bằng mysql client |

## 16. Checklist kiểm thử trước production

### Stored procedure và function

- [ ] Kiểm tra input hợp lệ, biên, NULL và dữ liệu không hợp lệ.
- [ ] Kiểm tra OUT/INOUT, result set và giá trị trả về.
- [ ] Kiểm tra SQLSTATE, handler và RESIGNAL.
- [ ] Xác định rõ ai quản lý transaction và commit/rollback.
- [ ] Kiểm tra hiệu năng khi gọi trong truy vấn nhiều hàng.

### Trigger

- [ ] Thực hiện DML thật để kích hoạt từng trigger.
- [ ] Kiểm tra OLD/NEW và điều kiện thay đổi.
- [ ] Xác minh audit/side effect chính xác.
- [ ] Kiểm tra rollback trên các bảng transactional.
- [ ] Kiểm tra lỗi trigger làm statement gốc thất bại đúng cách.
- [ ] Kiểm tra thứ tự nếu có nhiều trigger cùng event/timing.

### Event

- [ ] Kiểm tra event metadata, lịch, timezone, trạng thái và DEFINER.
- [ ] Xác nhận Event Scheduler đang ON trong môi trường mục tiêu.
- [ ] Test procedure được event gọi bằng cách gọi trực tiếp.
- [ ] Có integration test xác minh event thực sự được scheduler thực thi.
- [ ] Kiểm tra event chạy lặp, restart và cleanup.

### Ứng dụng và vận hành

- [ ] Chạy test trên MySQL version tương thích production.
- [ ] Gọi routine qua đúng JDBC/Spring API ứng dụng sử dụng.
- [ ] Chạy bằng account ứng dụng, không chỉ bằng root.
- [ ] Kiểm tra migration và SHOW CREATE sau deploy.
- [ ] Có fixture độc lập, cleanup và timeout.
- [ ] Không để test event hoặc dữ liệu nền tồn tại sau suite.
- [ ] Thu thập log/SQLSTATE mà không ghi secret hoặc dữ liệu nhạy cảm.

## 17. Bài tập thực hành

Một hệ thống bán hàng có:

- Procedure transfer_money chuyển tiền giữa hai tài khoản.
- Function calculate_fee tính phí.
- Trigger ghi audit khi số dư thay đổi.
- Event ev_clean_expired_sessions chạy hàng ngày để đánh dấu session hết hạn.

Hãy xây bộ test cho bốn đối tượng:

1. Tạo MySQL test instance riêng và chạy migration tạo schema/object.
2. Viết test procedure với số tiền hợp lệ, bằng 0, âm, không đủ số dư và tài khoản không tồn tại.
3. Xác minh OUT parameter, số dư hai tài khoản và rollback khi test kết thúc.
4. Viết test function cho số tiền 0, số thập phân, NULL và số âm; kiểm tra SQLSTATE.
5. Viết test trigger bằng UPDATE, update không đổi giá trị và update tạo lỗi; kiểm tra audit row.
6. Rollback transaction có trigger rồi xác minh cả bảng chính và audit table không còn thay đổi.
7. Gọi procedure cleanup trực tiếp với fixture expired/not-expired/already-cleaned.
8. Tạo event test chạy gần hiện tại, xác nhận Event Scheduler, STATUS và LAST_EXECUTED, rồi cleanup event.
9. Chạy test quyền bằng user ứng dụng và kiểm tra DEFINER.
10. Tích hợp test vào CI, pin MySQL image và thu log khi thất bại.

**Câu hỏi tự kiểm tra:**

1. Vì sao kiểm tra CREATE PROCEDURE thành công chưa đủ?
2. Cần xác minh những gì với procedure có OUT parameter?
3. Tại sao test trigger phải thực hiện DML thật trên bảng?
4. Vì sao side effect của trigger InnoDB được rollback cùng transaction?
5. Function khác procedure ở cách gọi và giá trị trả về như thế nào?
6. Vì sao nên tách logic event thành procedure có thể gọi trực tiếp?
7. event_scheduler=OFF khác DISABLED ở điểm nào?
8. Vì sao test bằng root có thể che giấu lỗi quyền của ứng dụng?
9. Tại sao không nên dùng DELIMITER trong câu lệnh JDBC?
10. Làm thế nào kiểm tra event chạy lặp mà không tạo side effect trùng?

## Kết luận

Kiểm thử stored procedure, function, trigger và event phải xác minh cả kết quả lẫn side effect trong ngữ cảnh MySQL thật. Procedure cần được kiểm tra tham số, OUT/result set, lỗi và transaction; function cần kiểm tra giá trị và các trường hợp biên; trigger cần được kích hoạt bằng DML và kiểm tra rollback; event cần kiểm tra cả logic công việc lẫn scheduler, lịch và DEFINER. Dùng fixture cô lập, chạy bằng quyền tương tự ứng dụng, kiểm tra migration sau deploy và đưa các test phù hợp vào CI sẽ giúp phát hiện lỗi trước khi stored object ảnh hưởng đến dữ liệu production.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Stored Objects](https://dev.mysql.com/doc/refman/8.4/en/stored-objects.html)
- [MySQL 8.4 Reference Manual — Stored Procedure Syntax](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual — Stored Function Syntax](https://dev.mysql.com/doc/refman/8.4/en/create-function.html)
- [MySQL 8.4 Reference Manual — Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/8.4/en/triggers.html)
- [MySQL 8.4 Reference Manual — Event Scheduler](https://dev.mysql.com/doc/refman/8.4/en/event-scheduler.html)
- [MySQL 8.4 Reference Manual — CREATE EVENT](https://dev.mysql.com/doc/refman/8.4/en/create-event.html)
- [MySQL Connector/J Developer Guide — CallableStatement](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html)
