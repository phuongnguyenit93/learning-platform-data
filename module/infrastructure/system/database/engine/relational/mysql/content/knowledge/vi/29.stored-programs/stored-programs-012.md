# Ranh giới COMMIT/ROLLBACK trong procedure so với function/trigger

Bài học thuộc chương **Stored program** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Stored procedure, stored function và trigger đều có thể chạy các câu lệnh SQL, nhưng chúng có quyền kiểm soát transaction khác nhau. Nhầm lẫn ranh giới này có thể khiến một procedure vô tình COMMIT công việc của ứng dụng, một function không tạo được, hoặc trigger làm hỏng tính nguyên tử của statement.

Sau bài này, bạn có thể phân biệt quyền transaction của procedure, function và trigger; hiểu transaction thuộc về session/caller chứ không tự thuộc riêng procedure; nhận diện tác động của START TRANSACTION, COMMIT, ROLLBACK và implicit commit; thiết kế procedure theo mô hình caller-owned hoặc procedure-owned transaction; xử lý lỗi bằng EXIT HANDLER, ROLLBACK và RESIGNAL; dùng SAVEPOINT đúng phạm vi; và kiểm thử kết quả bằng nhiều session.

## 1. Transaction thuộc về session, không thuộc riêng procedure

Trong MySQL, transaction là phạm vi làm việc của một connection/session. Một stored procedure được gọi bằng CALL chạy trong session đang gọi nó. Procedure không tự có một transaction lồng bên trong chỉ vì nó được định nghĩa thành một đối tượng riêng.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

CALL sp_write_transfer_audit(1, 2, 100);

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Nếu sp_write_transfer_audit chỉ INSERT dữ liệu audit và không phát lệnh COMMIT, ROLLBACK hoặc START TRANSACTION, các thay đổi trong procedure thuộc transaction đang mở của caller. COMMIT cuối cùng xác nhận toàn bộ thay đổi transaction-safe trong session.

Có thể hình dung:

~~~text
Connection / Session
└── Transaction T1
    ├── UPDATE accounts (caller)
    ├── CALL procedure
    │   └── INSERT audit_log (procedure)
    └── UPDATE accounts (caller)
        └── COMMIT T1
~~~

CALL không tạo transaction độc lập. Ranh giới transaction do các lệnh điều khiển transaction, autocommit và các câu lệnh gây implicit commit quyết định.

### Procedure có thể tham gia transaction của caller

Nếu caller đã mở transaction, procedure không có transaction control có thể thực hiện DML trong transaction đó:

~~~sql
CREATE PROCEDURE sp_add_audit(
    IN p_action VARCHAR(50),
    IN p_reference_id BIGINT
)
BEGIN
    INSERT INTO audit_log (action_name, reference_id, created_at)
    VALUES (p_action, p_reference_id, CURRENT_TIMESTAMP(6));
END;
~~~

Caller:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

CALL sp_add_audit('ORDER_PAID', 1001);

ROLLBACK;
~~~

Nếu orders và audit_log đều dùng InnoDB, cả UPDATE và INSERT đều bị rollback. Procedure không thể tự quyết định rằng audit phải commit riêng khi caller đã chọn ROLLBACK.

### Procedure cũng có thể tự điều khiển transaction

MySQL cho phép stored procedure chạy START TRANSACTION, COMMIT và ROLLBACK. Điều đó hữu ích khi procedure được thiết kế như một thao tác nghiệp vụ hoàn chỉnh, chẳng hạn đặt hàng hoặc chuyển tiền.

Nhưng quyền này tác động lên transaction của session. Nếu procedure được gọi khi caller đã mở transaction, START TRANSACTION có thể commit transaction đang chờ trước khi bắt đầu transaction mới. COMMIT trong procedure cũng commit transaction hiện tại của session.

Vì vậy, trước khi viết procedure cần xác định rõ ai sở hữu transaction:

- Caller-owned: ứng dụng hoặc procedure bên ngoài mở và kết thúc transaction; procedure con chỉ thực hiện DML.
- Procedure-owned: procedure tự mở, commit hoặc rollback transaction; caller phải biết procedure sẽ kết thúc transaction hiện tại.

Không trộn hai hợp đồng này trong cùng một luồng gọi.

## 2. Quyền transaction của procedure, function và trigger

MySQL áp dụng quy tắc khác nhau cho ba loại stored program.

| Khả năng | Stored procedure | Stored function | Trigger |
|---|---|---|---|
| Thực hiện DML trên bảng phù hợp | Có | Có, trong các giới hạn của function | Có |
| START TRANSACTION | Có | Không | Không |
| COMMIT transaction | Có | Không | Không |
| ROLLBACK toàn transaction | Có | Không | Không |
| Gây implicit commit/rollback | Có thể, nếu câu lệnh được phép trong ngữ cảnh gọi | Không được | Không được |
| ROLLBACK TO SAVEPOINT | Có | Không được dùng theo giới hạn rollback của stored function | Được phép vì không kết thúc transaction |
| Gắn với transaction của caller | Có | Có | Có, thông qua statement kích hoạt trigger |
| Có thể kết thúc transaction của caller | Có | Không | Không |

Các giới hạn quan trọng:

1. Stored procedure được phép chứa transaction-control statement, nhưng procedure được gọi từ stored function hoặc trigger phải tuân thủ các giới hạn của function/trigger.
2. Stored function không được chứa câu lệnh thực hiện explicit hoặc implicit commit/rollback.
3. Trigger không được dùng câu lệnh bắt đầu hoặc kết thúc transaction.
4. Trigger được phép dùng ROLLBACK TO SAVEPOINT vì câu lệnh này chỉ quay về savepoint, không kết thúc transaction.
5. Procedure không tạo nested transaction. Một session tại một thời điểm chỉ có một transaction thông thường đang hoạt động.

### Procedure được gọi từ function hoặc trigger

Một procedure bình thường có thể chứa COMMIT. Nhưng nếu function hoặc trigger gọi procedure đó, các câu lệnh bị cấm trong function/trigger vẫn bị cấm trong call chain.

Ví dụ không được dùng:

~~~sql
CREATE PROCEDURE sp_commit_work()
BEGIN
    UPDATE counters
    SET counter_value = counter_value + 1
    WHERE counter_id = 1;

    COMMIT;
END;
~~~

Nếu trigger gọi procedure trên, trigger không thể dùng procedure như một cách gián tiếp để COMMIT. MySQL áp dụng giới hạn theo ngữ cảnh gọi.

Quy tắc thiết kế: procedure dùng trong trigger/function nên là routine không điều khiển transaction. Nếu cần thao tác commit theo nghiệp vụ, hãy gọi procedure đó trực tiếp từ ứng dụng hoặc một procedure điều phối ở tầng ngoài.

## 3. START TRANSACTION khác BEGIN ... END trong stored program

Trong SQL thông thường, BEGIN WORK có thể được dùng như alias của START TRANSACTION. Nhưng trong stored program, parser hiểu BEGIN [WORK] là mở compound statement BEGIN ... END.

Do đó, để bắt đầu transaction trong stored procedure hoặc event, dùng:

~~~sql
START TRANSACTION;
~~~

Không viết:

~~~sql
BEGIN WORK;
~~~

để mong bắt đầu transaction bên trong procedure. Trong stored program, BEGIN mở block mã.

Ví dụ:

~~~sql
CREATE PROCEDURE sp_example()
BEGIN
    START TRANSACTION;

    UPDATE counters
    SET counter_value = counter_value + 1
    WHERE counter_id = 1;

    COMMIT;
END;
~~~

Ở đây:

- BEGIN mở thân procedure.
- END đóng thân procedure.
- START TRANSACTION mở transaction.
- COMMIT kết thúc transaction.

START TRANSACTION không được phép trong stored function hoặc trigger.

## 4. START TRANSACTION có thể commit transaction đang mở

Đây là điểm quan trọng nhất khi procedure có transaction riêng.

Trong MySQL, bắt đầu một transaction mới làm transaction đang chờ trong session được commit trước. Transaction không thể lồng nhau.

Ví dụ caller:

~~~sql
START TRANSACTION;

UPDATE wallet
SET balance = balance - 50
WHERE wallet_id = 1;

CALL sp_process_payment(1001);

ROLLBACK;
~~~

Giả sử sp_process_payment có nội dung:

~~~sql
CREATE PROCEDURE sp_process_payment(IN p_order_id BIGINT)
BEGIN
    START TRANSACTION;

    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id;

    COMMIT;
END;
~~~

Trình tự thực tế:

1. Caller mở transaction T1.
2. Caller trừ 50 khỏi wallet trong T1.
3. CALL procedure.
4. START TRANSACTION bên trong procedure kết thúc T1 bằng implicit commit.
5. Procedure bắt đầu transaction T2.
6. Procedure cập nhật order và COMMIT T2.
7. Procedure trả về caller.
8. Caller chạy ROLLBACK nhưng T1 và T2 đã kết thúc; thay đổi wallet đã được commit ở bước 4, thay đổi order đã được commit ở bước 6.

ROLLBACK cuối cùng không thể khôi phục thay đổi wallet.

Sơ đồ:

~~~text
Caller                         Procedure
  |                                |
  | START TRANSACTION (T1)         |
  | UPDATE wallet                  |
  |                                |
  | CALL ------------------------> |
  |                         START TRANSACTION
  |                         implicit COMMIT T1
  |                         START T2
  |                         UPDATE orders
  |                         COMMIT T2
  | <-------------------------- RETURN
  | ROLLBACK
  | (không còn T1/T2 để rollback)
~~~

Không gọi procedure tự START TRANSACTION từ một transaction do caller quản lý nếu caller mong muốn rollback toàn bộ công việc.

### COMMIT trong procedure cũng commit transaction của caller

Ngay cả khi procedure không chạy START TRANSACTION, COMMIT vẫn kết thúc transaction hiện tại của session.

~~~sql
CREATE PROCEDURE sp_update_and_commit()
BEGIN
    UPDATE settings
    SET setting_value = 'enabled'
    WHERE setting_name = 'feature_x';

    COMMIT;
END;
~~~

Nếu caller đã chạy START TRANSACTION trước CALL, COMMIT trên kết thúc transaction của caller, bao gồm cả các thay đổi trước khi gọi procedure.

Một procedure có COMMIT vì vậy phải công bố rõ hợp đồng transaction cho người gọi.

## 5. Autocommit và nhiều câu DML trong procedure

Mặc định MySQL bật autocommit. Mỗi statement sử dụng transactional engine được thực hiện như một transaction riêng nếu session không mở transaction tường minh.

Kiểm tra:

~~~sql
SELECT @@SESSION.autocommit;
~~~

Khi autocommit = 1:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 1
WHERE product_id = 10;
~~~

Nếu không có transaction tường minh, statement thành công sẽ được commit tự động.

Một procedure chứa nhiều câu DML nhưng không START TRANSACTION/COMMIT không tự biến toàn bộ thân procedure thành một transaction duy nhất. Khi không có transaction của caller và autocommit đang bật, mỗi statement DML tuân theo quy tắc autocommit của session.

Ví dụ:

~~~sql
CREATE PROCEDURE sp_two_updates()
BEGIN
    UPDATE account_summary
    SET amount = amount - 100
    WHERE account_id = 1;

    UPDATE account_summary
    SET amount = amount + 100
    WHERE account_id = 2;
END;
~~~

Nếu không có transaction bao quanh, không được mặc định hai UPDATE cùng rollback khi statement thứ hai lỗi. Để hai thay đổi thuộc cùng một đơn vị nguyên tử, caller phải mở transaction hoặc procedure phải được thiết kế sở hữu transaction.

Nếu autocommit = 0, transaction tiếp tục tồn tại cho đến COMMIT hoặc ROLLBACK. Cần đặc biệt cẩn thận với connection pool vì trạng thái session có thể tồn tại khi connection được tái sử dụng.

Không thay đổi autocommit trong procedure dùng chung mà không có hợp đồng rõ ràng. SET autocommit = 1 khi giá trị hiện tại là 0 gây implicit commit.

## 6. Stored function không được điều khiển transaction

Stored function được gọi trong biểu thức SQL, ví dụ SELECT, WHERE, ORDER BY hoặc biểu thức DML. Vì function có thể được thực thi trong ngữ cảnh một statement, MySQL không cho function tự kết thúc transaction bao quanh caller.

Ví dụ function đọc số lượng tồn:

~~~sql
CREATE FUNCTION fn_available_stock(
    p_product_id BIGINT UNSIGNED
)
RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_available INT DEFAULT NULL;

    SELECT available_qty
    INTO v_available
    FROM inventory
    WHERE product_id = p_product_id;

    RETURN v_available;
END;
~~~

Có thể gọi:

~~~sql
SELECT fn_available_stock(10);
~~~

Function trên chỉ đọc dữ liệu và không mở/commit/rollback transaction.

Các dạng sau không hợp lệ trong stored function:

~~~sql
START TRANSACTION;
COMMIT;
ROLLBACK;
~~~

Function cũng không được thực hiện câu lệnh có implicit commit/rollback. Ví dụ DDL như ALTER TABLE, CREATE TABLE hoặc TRUNCATE TABLE không được dùng như cách gián tiếp điều khiển transaction từ function.

### Function vẫn chạy trong transaction của caller

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = available_qty - 1
WHERE product_id = 10;

SELECT fn_available_stock(10);

ROLLBACK;
~~~

Function đọc trạng thái dữ liệu theo transaction/read view của session. Function không commit thay đổi inventory. ROLLBACK của caller vẫn quyết định kết quả transaction.

Stored function có thể thực hiện DML trong những giới hạn của MySQL, nhưng DML đó không làm function trở thành chủ sở hữu transaction. Nó vẫn chịu transaction của statement/caller. Ngoài ra, function không được sửa một bảng đang được statement gọi function sử dụng để đọc hoặc ghi.

### Procedure được gọi từ function

Nếu function gọi procedure, procedure đó cũng không được thực hiện những câu lệnh bị cấm trong function.

Ví dụ một procedure có COMMIT có thể chạy độc lập bằng CALL, nhưng không thể được gọi từ function để lách giới hạn transaction.

## 7. Trigger không được bắt đầu hoặc kết thúc transaction

Trigger được kích hoạt trong quá trình INSERT, UPDATE hoặc DELETE trên bảng gắn trigger. Nó là một phần của statement kích hoạt.

Ví dụ:

~~~sql
CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        action_name,
        created_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        CURRENT_TIMESTAMP(6)
    );
END;
~~~

Khi ứng dụng INSERT một đơn hàng, trigger thêm bản ghi audit trong cùng ngữ cảnh transaction của statement.

~~~sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, status)
VALUES (1001, 42, 'NEW');

ROLLBACK;
~~~

Nếu orders và order_audit đều dùng InnoDB, cả hàng order và hàng audit đều bị rollback.

### Không COMMIT hoặc ROLLBACK trong trigger

Trigger không được dùng các câu lệnh bắt đầu hoặc kết thúc transaction:

~~~sql
START TRANSACTION;
COMMIT;
ROLLBACK;
~~~

Trigger không được kết thúc transaction của ứng dụng vì nó là một phần của statement đang thực thi.

Nếu trigger gọi stored procedure, procedure đó cũng không được chứa câu lệnh gây explicit/implicit commit hoặc rollback.

### ROLLBACK TO SAVEPOINT là ngoại lệ

Trigger được phép dùng ROLLBACK TO SAVEPOINT vì câu lệnh này không kết thúc transaction.

~~~sql
SAVEPOINT sp_trigger_work;

INSERT INTO audit_detail (...);

ROLLBACK TO SAVEPOINT sp_trigger_work;
~~~

Đây chỉ là ví dụ về ngữ nghĩa savepoint, không phải mẫu trigger nên dùng thường xuyên. Savepoint được tạo trong phạm vi trigger có level riêng; khi trigger kết thúc, savepoint của level đó được giải phóng và savepoint ở level trước được khôi phục.

Không nhầm ROLLBACK TO SAVEPOINT với ROLLBACK:

| Câu lệnh | Kết quả |
|---|---|
| ROLLBACK | Kết thúc transaction và hoàn tác toàn bộ thay đổi transactional chưa commit |
| ROLLBACK TO SAVEPOINT x | Hoàn tác thay đổi sau savepoint x, transaction vẫn tiếp tục |
| RELEASE SAVEPOINT x | Xóa savepoint, không commit hoặc rollback transaction |

### Lỗi trong trigger và rollback của statement

Nếu trigger phát sinh lỗi, statement kích hoạt trigger thất bại.

Với bảng transactional như InnoDB, thay đổi do statement đó thực hiện được rollback cùng thay đổi transactional do trigger thực hiện. Transaction lớn hơn của caller vẫn có thể còn mở; caller quyết định tiếp tục hay rollback toàn transaction.

Với bảng nontransactional, MySQL không thể hoàn tác những thay đổi đã ghi trước khi lỗi xảy ra. Vì vậy, các thao tác cần tính nguyên tử nên dùng transactional storage engine.

## 8. Implicit commit: procedure có thể commit mà không viết COMMIT

Không phải chỉ COMMIT mới kết thúc transaction. Một số câu lệnh tự động commit transaction đang mở trước khi thực thi; nhiều câu còn commit sau khi thực thi.

Ví dụ thường gặp:

| Nhóm | Ví dụ |
|---|---|
| DDL | CREATE TABLE, ALTER TABLE, DROP TABLE |
| Index | CREATE INDEX, DROP INDEX |
| View/routine/trigger | CREATE VIEW, ALTER VIEW, CREATE PROCEDURE, CREATE FUNCTION, CREATE TRIGGER |
| Quản trị database | CREATE DATABASE, DROP DATABASE |
| Xóa dữ liệu kiểu DDL | TRUNCATE TABLE |
| Quyền người dùng | GRANT, REVOKE, CREATE USER, ALTER USER |
| Điều khiển transaction/lock | START TRANSACTION, BEGIN, LOCK TABLES, một số trường hợp SET autocommit = 1 |

Procedure có thể chứa một số DDL, nhưng không có nghĩa DDL nằm trong transaction và rollback được.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE account_summary
SET amount = amount - 100
WHERE account_id = 1;

ALTER TABLE audit_log
ADD COLUMN source_name VARCHAR(50);

ROLLBACK;
~~~

ALTER TABLE gây implicit commit trước khi thực thi. UPDATE trước đó đã được commit; ROLLBACK sau ALTER không thể khôi phục UPDATE.

### Temporary table có ngoại lệ nhưng không có atomic rollback

CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit như CREATE/DROP TABLE thông thường. Tuy nhiên, các thay đổi này cũng không được rollback như DML.

Ví dụ:

~~~sql
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_work (
    id INT PRIMARY KEY
);

ROLLBACK;
~~~

Sau ROLLBACK, temporary table vẫn tồn tại. Điều đó có nghĩa transaction không thể khôi phục toàn bộ trạng thái session như thể câu CREATE TEMPORARY TABLE chưa từng xảy ra.

Một số thao tác khác trên temporary table, chẳng hạn ALTER TABLE hoặc CREATE INDEX, vẫn có thể gây implicit commit.

### Không dùng DDL làm bước giữa của transaction nghiệp vụ

Nếu procedure thực hiện:

1. UPDATE số dư.
2. CREATE TABLE hoặc TRUNCATE bảng.
3. INSERT dữ liệu nghiệp vụ.
4. ROLLBACK khi có lỗi.

thì bước DDL có thể đã commit phần UPDATE trước đó. Thiết kế đúng là tách DDL khỏi transaction nghiệp vụ hoặc dùng bảng staging được chuẩn bị trước.

## 9. Chọn mô hình caller-owned hay procedure-owned

Đây là quyết định thiết kế quan trọng nhất.

### Mô hình caller-owned transaction

Procedure chỉ chứa DML và không phát START TRANSACTION, COMMIT hoặc ROLLBACK toàn transaction.

~~~sql
CREATE PROCEDURE sp_change_order_status(
    IN p_order_id BIGINT,
    IN p_new_status VARCHAR(20)
)
BEGIN
    UPDATE orders
    SET status = p_new_status
    WHERE order_id = p_order_id;
END;
~~~

Caller:

~~~sql
START TRANSACTION;

CALL sp_change_order_status(1001, 'PAID');

INSERT INTO order_audit (
    order_id,
    action_name,
    created_at
)
VALUES (
    1001,
    'STATUS_CHANGED',
    CURRENT_TIMESTAMP(6)
);

COMMIT;
~~~

Ưu điểm:

- Ứng dụng quyết định ranh giới transaction.
- Có thể gộp nhiều procedure và DML vào một transaction.
- Procedure dễ tái sử dụng trong nhiều workflow.
- Caller có thể rollback toàn bộ nếu bước sau thất bại.

Nhược điểm:

- Caller phải hiểu procedure không tự commit.
- Nếu gọi procedure ngoài transaction với autocommit bật, các statement DML tuân theo autocommit riêng.
- Hợp đồng transaction cần được ghi rõ trong tài liệu API.

Dùng mô hình này khi ứng dụng cần phối hợp nhiều thao tác và muốn tự quyết định khi nào commit.

### Mô hình procedure-owned transaction

Procedure tự mở và kết thúc transaction.

~~~sql
CREATE PROCEDURE sp_record_payment(
    IN p_order_id BIGINT,
    IN p_payment_ref VARCHAR(100)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id;

    INSERT INTO payments (
        order_id,
        payment_ref,
        created_at
    )
    VALUES (
        p_order_id,
        p_payment_ref,
        CURRENT_TIMESTAMP(6)
    );

    COMMIT;
END;
~~~

Ưu điểm:

- Toàn bộ nghiệp vụ được đóng gói trong một routine.
- Procedure tự rollback nếu lỗi trước commit.
- Caller chỉ cần gọi một thao tác nghiệp vụ.

Nhược điểm:

- Procedure có thể commit transaction đang mở của caller nếu chạy START TRANSACTION.
- Không thể ghép an toàn vào một transaction lớn do caller quản lý.
- Procedure khó phối hợp với workflow nhiều bước bên ngoài.
- Phải kiểm soát implicit commit trong mọi câu lệnh bên trong.

Dùng mô hình này khi procedure là đơn vị nghiệp vụ độc lập và caller chấp nhận rằng procedure sở hữu transaction của session.

### Không trộn hai mô hình

Không nên viết procedure có lúc tự COMMIT, lúc lại chờ caller COMMIT dựa trên một tham số boolean hoặc trạng thái session không rõ ràng. Cách đó khiến người gọi khó dự đoán transaction đã kết thúc hay chưa.

Một convention rõ ràng:

- Procedure hậu tố/nhóm *_in_tx: không điều khiển transaction, caller sở hữu transaction.
- Procedure nghiệp vụ độc lập: tự quản lý transaction và ghi rõ không gọi trong transaction đang mở.
- Trigger/function: không điều khiển transaction; chỉ thực hiện logic nằm trong transaction của caller.

Tên routine chỉ là convention; cần tài liệu hóa và review nội dung thực tế.

## 10. Xử lý lỗi trong procedure-owned transaction

Khi procedure sở hữu transaction, cần bảo đảm lỗi không để lại transaction đang mở.

Mẫu phổ biến:

~~~sql
CREATE PROCEDURE sp_atomic_operation()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Các câu DML của nghiệp vụ
    UPDATE ...;
    INSERT ...;

    COMMIT;
END;
~~~

Ý nghĩa:

- EXIT HANDLER được gọi khi có SQLEXCEPTION.
- ROLLBACK hoàn tác transaction hiện tại.
- RESIGNAL phát lại lỗi để caller biết thao tác thất bại.
- Nếu không có lỗi, COMMIT xác nhận toàn bộ thay đổi.

### Vì sao cần RESIGNAL?

Nếu handler chỉ ROLLBACK rồi kết thúc mà không RESIGNAL, caller có thể không nhận được lỗi gốc theo cách mong muốn. RESIGNAL chuyển lỗi đang xử lý ra ngoài để ứng dụng hoặc procedure cha quyết định bước tiếp theo.

Không bắt lỗi rồi âm thầm bỏ qua nếu caller cần biết giao dịch thất bại.

### EXIT HANDLER khác CONTINUE HANDLER

| Handler | Hành vi |
|---|---|
| EXIT | Kết thúc block BEGIN...END nơi handler được khai báo sau khi chạy handler |
| CONTINUE | Chạy handler rồi tiếp tục sau statement gây lỗi |
| UNDO | Không được MySQL hỗ trợ |

Handler cho transaction thường dùng EXIT để tránh tiếp tục chạy các bước nghiệp vụ sau khi một câu lệnh thất bại.

### Khai báo handler đúng vị trí

Trong block stored program, khai báo biến và condition trước handler; mọi DECLARE phải nằm trước câu lệnh thực thi.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    UPDATE inventory
    SET available_qty = available_qty - 1
    WHERE product_id = 10;
    COMMIT;
END
~~~

### NOT FOUND không phải SQLEXCEPTION

SQLSTATE class 02 là NOT FOUND, không thuộc SQLEXCEPTION. Một SELECT ... INTO không tìm thấy hàng có thể kích hoạt NOT FOUND và tiếp tục nếu không có handler phù hợp.

Ví dụ:

~~~sql
DECLARE v_available INT DEFAULT NULL;

SELECT available_qty
INTO v_available
FROM inventory
WHERE product_id = p_product_id
FOR UPDATE;

IF v_available IS NULL THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Product does not exist';
END IF;
~~~

Vì biến ban đầu là NULL và cột available_qty được khai báo NOT NULL, trường hợp không tìm thấy hàng có thể được phát hiện qua giá trị NULL. SIGNAL tạo exception class 45 để EXIT HANDLER FOR SQLEXCEPTION xử lý.

## 11. SAVEPOINT: rollback một phần mà không kết thúc transaction

SAVEPOINT tạo mốc trong transaction. ROLLBACK TO SAVEPOINT hoàn tác những thay đổi sau mốc đó nhưng giữ transaction tiếp tục.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

SAVEPOINT before_optional_audit;

INSERT INTO audit_log (
    order_id,
    action_name,
    created_at
)
VALUES (
    1001,
    'PROCESSING',
    CURRENT_TIMESTAMP(6)
);

ROLLBACK TO SAVEPOINT before_optional_audit;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

COMMIT;
~~~

Kết quả:

- UPDATE đầu tiên vẫn được giữ.
- INSERT audit sau savepoint bị hoàn tác.
- UPDATE cuối cùng vẫn được thực hiện.
- COMMIT kết thúc transaction.

### SAVEPOINT trong procedure

Procedure có thể sử dụng savepoint của transaction hiện tại nếu có transaction đang hoạt động. Nó không tạo transaction mới.

~~~sql
CREATE PROCEDURE sp_optional_step()
BEGIN
    SAVEPOINT sp_optional_step;

    INSERT INTO audit_log (
        order_id,
        action_name,
        created_at
    )
    VALUES (
        1001,
        'OPTIONAL_STEP',
        CURRENT_TIMESTAMP(6)
    );

    -- Khi cần hủy riêng bước tùy chọn:
    ROLLBACK TO SAVEPOINT sp_optional_step;

    RELEASE SAVEPOINT sp_optional_step;
END;
~~~

Procedure này phải được gọi trong transaction có chủ đích nếu cần savepoint tồn tại cùng các bước khác. Nếu không có transaction bao quanh, autocommit có thể làm mỗi statement kết thúc ngay; không được coi savepoint là transaction độc lập.

Tên savepoint được quản lý trong transaction. Tạo savepoint cùng tên sẽ thay thế savepoint cũ có tên đó.

### SAVEPOINT không giải phóng mọi row lock

ROLLBACK TO SAVEPOINT không nhất thiết giải phóng tất cả row lock được lấy sau savepoint. InnoDB giữ lại một số lock đã lưu trong bộ nhớ cho đến khi transaction kết thúc.

Vì vậy, rollback một phần không đồng nghĩa tài nguyên khóa đã được trả hết.

### SAVEPOINT trong function và trigger

MySQL tạo savepoint level riêng khi stored function được gọi hoặc trigger được kích hoạt. Savepoint ở level trước tạm thời không thể truy cập từ level mới; savepoint được tạo trong level đó sẽ được giải phóng khi function/trigger kết thúc. Quy tắc scope này không cấp quyền COMMIT hoặc ROLLBACK toàn transaction cho function/trigger. Riêng trigger được tài liệu cho phép ROLLBACK TO SAVEPOINT; stored function vẫn chịu giới hạn đối với câu lệnh rollback.

Đối với trigger, MySQL cho phép ROLLBACK TO SAVEPOINT vì nó không kết thúc transaction. Điều này khác hoàn toàn với ROLLBACK toàn transaction vốn bị cấm trong trigger.

## 12. DDL và implicit commit trong stored procedure

Procedure được phép chứa một số DDL, nhưng DDL không tự trở thành transactional chỉ vì nó nằm trong BEGIN ... END.

Ví dụ:

~~~sql
CREATE PROCEDURE sp_bad_migration()
BEGIN
    START TRANSACTION;

    UPDATE settings
    SET setting_value = 'new'
    WHERE setting_name = 'mode';

    TRUNCATE TABLE staging_data;

    ROLLBACK;
END;
~~~

TRUNCATE TABLE gây implicit commit. UPDATE settings trước đó có thể đã được commit trước TRUNCATE. ROLLBACK cuối procedure không thể khôi phục nó.

Các câu lệnh thường gây implicit commit gồm:

- CREATE/ALTER/DROP TABLE.
- CREATE/DROP INDEX.
- CREATE/ALTER/DROP VIEW.
- CREATE/ALTER/DROP PROCEDURE hoặc FUNCTION.
- CREATE/DROP TRIGGER.
- TRUNCATE TABLE.
- CREATE/DROP DATABASE.
- GRANT/REVOKE và một số thao tác quản trị user.

Một số ngoại lệ có phạm vi hẹp như CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không implicit commit, nhưng bản thân việc tạo/xóa temporary table không thể rollback như DML. Các thao tác ALTER hoặc CREATE INDEX trên temporary table vẫn có thể implicit commit.

Trước khi thêm DDL vào procedure, kiểm tra tài liệu implicit-commit của đúng phiên bản MySQL. Trong workflow nghiệp vụ, nên chuẩn bị schema/staging trước khi mở transaction DML.

## 13. Storage engine quyết định rollback có hiệu lực đến đâu

COMMIT/ROLLBACK chỉ có ý nghĩa đầy đủ với bảng dùng transactional storage engine.

Với InnoDB:

- INSERT/UPDATE/DELETE trong transaction có thể commit hoặc rollback.
- Trigger thay đổi bảng InnoDB được kích hoạt trong cùng statement/transaction.
- Khi statement lỗi, thay đổi transactional của statement được rollback.
- Khi transaction rollback hoàn chỉnh, các row lock do transaction giữ được giải phóng.

Với bảng nontransactional:

- Thay đổi có thể đã ghi ngay.
- ROLLBACK không hoàn tác các thay đổi đó.
- Nếu statement hoặc trigger lỗi, dữ liệu đã ghi trước thời điểm lỗi có thể vẫn tồn tại.

Ví dụ nguy hiểm:

~~~sql
CREATE TABLE business_data (
    id INT PRIMARY KEY,
    value_num INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE legacy_log (
    id INT PRIMARY KEY,
    message_text VARCHAR(100)
) ENGINE=MyISAM;
~~~

Một procedure cập nhật business_data rồi ghi legacy_log. Nếu transaction rollback, business_data có thể được hoàn tác nhưng legacy_log vẫn giữ thay đổi.

Để bảo đảm atomicity nghiệp vụ, ưu tiên các bảng liên quan dùng cùng một transactional engine, thường là InnoDB.

## 14. Trigger error không đồng nghĩa rollback toàn bộ transaction

Cần phân biệt rollback statement với rollback transaction.

Giả sử caller:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

INSERT INTO orders (...); -- Trigger phát sinh lỗi

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Nếu trigger làm INSERT thất bại trên bảng InnoDB, statement INSERT bị rollback. Transaction của caller có thể vẫn còn mở. UPDATE đầu tiên không tự động bị rollback chỉ vì statement thứ hai thất bại.

Ứng dụng cần quyết định:

- Tiếp tục transaction nếu lỗi statement có thể xử lý và nghiệp vụ cho phép.
- ROLLBACK toàn transaction nếu đơn vị nghiệp vụ phải nguyên tử.
- Hoặc dùng handler ở procedure điều phối để rollback và RESIGNAL.

Không giả định mọi lỗi SQL đều tự rollback toàn transaction. Hành vi phụ thuộc loại lỗi, storage engine và cấu hình InnoDB.

Đặc biệt:

- Deadlock thường khiến InnoDB rollback toàn bộ transaction được chọn làm nạn nhân.
- Lock wait timeout mặc định thường rollback statement bị timeout, không nhất thiết rollback toàn transaction.
- Handler có thể chủ động ROLLBACK transaction nếu procedure sở hữu nó.

## 15. Thiết kế mẫu: procedure đặt hàng sở hữu transaction

Bài toán: trừ tồn kho và tạo đơn hàng trong cùng một transaction. Nếu không đủ hàng hoặc INSERT thất bại, phải rollback toàn bộ.

### Bước 1: tạo bảng InnoDB

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    available_qty INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;
~~~

### Bước 2: tạo trigger ghi audit

~~~sql
DELIMITER //

CREATE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        action_name,
        created_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        CURRENT_TIMESTAMP(6)
    );
END//

DELIMITER ;
~~~

Trigger không COMMIT. INSERT audit tham gia cùng statement INSERT order và transaction hiện tại.

### Bước 3: tạo procedure tự quản lý transaction

~~~sql
DELIMITER //

CREATE PROCEDURE sp_place_order(
    IN p_product_id BIGINT UNSIGNED,
    IN p_quantity INT
)
BEGIN
    DECLARE v_available INT DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be positive';
    END IF;

    SELECT available_qty
    INTO v_available
    FROM inventory
    WHERE product_id = p_product_id
    FOR UPDATE;

    IF v_available IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Product does not exist';
    END IF;

    IF v_available < p_quantity THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Insufficient inventory';
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id;

    INSERT INTO orders (
        product_id,
        quantity,
        status,
        created_at
    )
    VALUES (
        p_product_id,
        p_quantity,
        'NEW',
        CURRENT_TIMESTAMP(6)
    );

    COMMIT;
END//

DELIMITER ;
~~~

Điểm quan trọng:

- Procedure sở hữu transaction.
- Caller không được mở transaction trước khi CALL nếu muốn giữ các thay đổi chưa commit khác.
- SELECT ... FOR UPDATE khóa hàng tồn kho trong transaction.
- SIGNAL khi dữ liệu không hợp lệ tạo exception.
- EXIT HANDLER rollback và RESIGNAL.
- INSERT vào orders kích hoạt trigger; audit nằm trong transaction.
- COMMIT cuối cùng xác nhận tồn kho, order và audit cùng lúc.

### Bước 4: gọi procedure

~~~sql
INSERT INTO inventory (product_id, available_qty)
VALUES (10, 20);

CALL sp_place_order(10, 3);
~~~

Kiểm tra:

~~~sql
SELECT *
FROM inventory
WHERE product_id = 10;

SELECT *
FROM orders
ORDER BY order_id DESC;

SELECT *
FROM order_audit
ORDER BY audit_id DESC;
~~~

Kết quả mong đợi:

- available_qty giảm từ 20 xuống 17.
- Một order mới được tạo.
- Một bản ghi audit ORDER_CREATED được tạo.

### Bước 5: thử lỗi để quan sát rollback

~~~sql
CALL sp_place_order(10, 1000);
~~~

Procedure phát lỗi Insufficient inventory. EXIT HANDLER chạy ROLLBACK rồi RESIGNAL.

Kiểm tra lại:

~~~sql
SELECT available_qty
FROM inventory
WHERE product_id = 10;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT COUNT(*) AS audit_count
FROM order_audit;
~~~

Không có order hoặc audit mới; tồn kho giữ nguyên.

### Bước 6: thử procedure khi caller đã có transaction

Trong một session thử nghiệm:

~~~sql
START TRANSACTION;

INSERT INTO inventory (product_id, available_qty)
VALUES (20, 50);

CALL sp_place_order(10, 1);

ROLLBACK;
~~~

START TRANSACTION bên trong sp_place_order kết thúc transaction đang mở của caller. Vì vậy, INSERT inventory product_id=20 có thể đã được commit trước khi procedure bắt đầu transaction của nó. ROLLBACK cuối caller không thể undo INSERT đó.

Chỉ thực hiện thử nghiệm này trên database lab. Đây là minh họa cho hợp đồng procedure-owned transaction.

## 16. Thiết kế mẫu: procedure để caller sở hữu transaction

Nếu ứng dụng cần kết hợp nhiều bước nghiệp vụ, procedure nên chỉ thực hiện DML.

~~~sql
DELIMITER //

CREATE PROCEDURE sp_change_stock(
    IN p_product_id BIGINT UNSIGNED,
    IN p_delta INT
)
BEGIN
    UPDATE inventory
    SET available_qty = available_qty + p_delta
    WHERE product_id = p_product_id;
END//

DELIMITER ;
~~~

Caller:

~~~sql
START TRANSACTION;

CALL sp_change_stock(10, -2);

INSERT INTO order_audit (
    order_id,
    action_name,
    created_at
)
VALUES (
    0,
    'MANUAL_STOCK_CHANGE',
    CURRENT_TIMESTAMP(6)
);

ROLLBACK;
~~~

Vì procedure không COMMIT/ROLLBACK, cả UPDATE inventory và INSERT audit tham gia transaction của caller. ROLLBACK hoàn tác cả hai nếu bảng đều dùng InnoDB.

Đây là mô hình phù hợp cho ứng dụng có transaction orchestration ở service layer.

## 17. Kiểm thử ranh giới transaction bằng hai session

Dùng hai connection độc lập để quan sát transaction của caller và procedure.

### Bài thử A: procedure không commit

Session A:

~~~sql
START TRANSACTION;

CALL sp_change_stock(10, -1);

SELECT available_qty
FROM inventory
WHERE product_id = 10;
~~~

Session B, trước khi Session A commit:

~~~sql
SELECT available_qty
FROM inventory
WHERE product_id = 10;
~~~

Với InnoDB và isolation mặc định REPEATABLE READ, Session B không nhìn thấy thay đổi chưa commit của Session A. Sau khi Session B chạy xong, quay lại Session A:

~~~sql
ROLLBACK;
~~~

Session B tiếp tục nhìn thấy giá trị cũ sau khi Session A rollback.

### Bài thử B: procedure tự COMMIT

Tạo bảng kiểm thử và procedure chỉ để minh họa:

~~~sql
CREATE TABLE transaction_probe (
    probe_id INT NOT NULL PRIMARY KEY,
    value_num INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO transaction_probe (probe_id, value_num)
VALUES (1, 0);
~~~

~~~sql
DELIMITER //

CREATE PROCEDURE sp_commit_marker()
BEGIN
    UPDATE transaction_probe
    SET value_num = value_num + 1
    WHERE probe_id = 1;

    COMMIT;
END//

DELIMITER ;
~~~

Session A:

~~~sql
START TRANSACTION;

UPDATE transaction_probe
SET value_num = value_num + 10
WHERE probe_id = 1;

CALL sp_commit_marker();

ROLLBACK;
~~~

Session B đọc lại transaction_probe. Cả thay đổi +10 của caller và +1 của procedure đã được commit bởi COMMIT trong procedure. ROLLBACK cuối Session A không còn tác dụng với transaction đã kết thúc.

### Bài thử C: trigger tham gia statement

Tạo trigger ghi audit trên bảng InnoDB, sau đó:

~~~sql
START TRANSACTION;

INSERT INTO orders (
    product_id,
    quantity,
    status,
    created_at
)
VALUES (
    10,
    1,
    'NEW',
    CURRENT_TIMESTAMP(6)
);

ROLLBACK;
~~~

Kiểm tra cả orders và audit. Cả hai thay đổi đều phải bị rollback nếu statement thành công và transaction sau đó rollback.

## 18. Theo dõi transaction đang mở và xác định ai đã commit

Khi procedure hoặc trigger được gọi từ ứng dụng, cần điều tra session nào đang giữ transaction.

Xem transaction InnoDB:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_rows_modified,
    trx_rows_locked,
    trx_query
FROM INFORMATION_SCHEMA.INNODB_TRX
ORDER BY trx_started;
~~~

Xem session:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
ORDER BY TIME DESC;
~~~

Đối chiếu trx_mysql_thread_id với PROCESSLIST.ID.

Performance Schema có các bảng transaction event để xem transaction gắn với statement và stored program event. Có thể dùng:

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    STATE,
    AUTOCOMMIT,
    ISOLATION_LEVEL,
    ACCESS_MODE,
    TIMER_START,
    TIMER_END
FROM performance_schema.events_transactions_history_long
ORDER BY THREAD_ID, EVENT_ID;
~~~

Bảng history có giới hạn dung lượng và phụ thuộc consumer/instrument được bật. Không mặc định mọi transaction đều còn trong history.

Khi điều tra procedure gây commit ngoài dự kiến:

1. Kiểm tra source procedure và mọi procedure được gọi lồng nhau.
2. Tìm START TRANSACTION, COMMIT, ROLLBACK, SET autocommit.
3. Tìm DDL và statement gây implicit commit.
4. Kiểm tra caller có mở transaction trước CALL không.
5. Kiểm tra autocommit của session.
6. Đối chiếu transaction event và thời điểm commit.
7. Kiểm tra trigger/function được gọi gián tiếp từ statement.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Function không tạo được vì COMMIT | Stored function không được điều khiển transaction | Bỏ transaction-control statement khỏi function |
| Trigger báo lỗi khi COMMIT | Trigger không được kết thúc transaction | Để caller/procedure điều phối transaction |
| Procedure commit dữ liệu của caller | COMMIT tác động transaction hiện tại của session | Chọn caller-owned hoặc procedure-owned rõ ràng |
| START TRANSACTION trong procedure làm mất thay đổi trước CALL | START TRANSACTION implicit commit transaction đang chờ | Không gọi procedure-owned trong transaction của caller |
| Nghĩ BEGIN trong procedure mở transaction | BEGIN được parser hiểu là block BEGIN...END | Dùng START TRANSACTION |
| Procedure nhiều DML nhưng lỗi giữa chừng vẫn giữ bước trước | Không có transaction bao quanh và autocommit bật | Mở transaction ở caller hoặc procedure |
| ROLLBACK không hoàn tác TRUNCATE | TRUNCATE gây implicit commit và không rollback như DML | Dùng DELETE trong transaction hoặc staging |
| Handler rollback nhưng caller không nhận lỗi | Handler nuốt lỗi | Dùng RESIGNAL sau ROLLBACK |
| Handler SQLEXCEPTION không bắt NOT FOUND | SQLSTATE class 02 không thuộc SQLEXCEPTION | Khai báo NOT FOUND handler hoặc kiểm tra biến SELECT INTO |
| Trigger lỗi nhưng transaction vẫn còn mở | Statement bị rollback, transaction lớn hơn chưa chắc kết thúc | Caller quyết định ROLLBACK toàn transaction |
| ROLLBACK không khôi phục bảng MyISAM | Nontransactional engine không hỗ trợ rollback | Dùng InnoDB cho dữ liệu cần atomicity |
| ROLLBACK TO SAVEPOINT vẫn giữ lock | InnoDB không giải phóng mọi row lock sau savepoint rollback | Kết thúc transaction nếu cần giải phóng toàn bộ lock |
| Procedure gọi từ trigger không chạy được COMMIT | Procedure lồng phải tuân thủ hạn chế của trigger | Tách phần transaction-control ra ngoài call chain |
| Procedure chạy trong connection pool để lại transaction mở | Thiếu COMMIT/ROLLBACK hoặc lỗi không được xử lý | Handler, kiểm tra autocommit và cleanup connection |
| DDL trong procedure commit sớm | DDL gây implicit commit | Tách migration DDL khỏi transaction DML |

## 20. Checklist thiết kế transaction cho stored program

- [ ] Đã xác định transaction thuộc caller hay procedure.
- [ ] Đã ghi rõ hợp đồng transaction cho mỗi procedure.
- [ ] Procedure caller-owned không chứa START TRANSACTION, COMMIT hoặc ROLLBACK toàn transaction.
- [ ] Procedure-owned chỉ được gọi khi caller không có transaction cần giữ.
- [ ] Đã hiểu START TRANSACTION có thể commit transaction đang chờ.
- [ ] Không giả định MySQL hỗ trợ nested transaction.
- [ ] Đã phân biệt BEGIN ... END với START TRANSACTION.
- [ ] Function không có explicit/implicit commit hoặc rollback.
- [ ] Trigger không có statement bắt đầu/kết thúc transaction.
- [ ] Procedure được gọi từ function/trigger tuân thủ giới hạn call context.
- [ ] Đã hiểu ROLLBACK TO SAVEPOINT không kết thúc transaction.
- [ ] Đã khai báo EXIT HANDLER cho SQLEXCEPTION khi procedure sở hữu transaction.
- [ ] Handler rollback rồi RESIGNAL nếu cần thông báo lỗi cho caller.
- [ ] Đã xử lý riêng NOT FOUND nếu dùng SELECT ... INTO.
- [ ] Đã kiểm tra DDL và implicit commit.
- [ ] Các bảng cần atomicity dùng transactional engine như InnoDB.
- [ ] Đã kiểm tra trigger error và rollback statement.
- [ ] Đã thử transaction trong hai session.
- [ ] Đã kiểm tra autocommit và trạng thái session khi dùng connection pool.
- [ ] Không chạy Content QA/refactor hoặc migration production trong bước viết bài này.

## 21. Nguyên tắc cần ghi nhớ

1. Transaction là phạm vi của session, không phải transaction riêng tự động của procedure.
2. Stored procedure có thể START TRANSACTION, COMMIT và ROLLBACK.
3. COMMIT/ROLLBACK trong procedure tác động transaction hiện tại của session, bao gồm thay đổi do caller thực hiện.
4. START TRANSACTION kết thúc transaction đang chờ trước khi mở transaction mới; MySQL không hỗ trợ nested transaction thông thường.
5. Trong stored program, BEGIN mở block BEGIN...END; dùng START TRANSACTION để mở transaction trong procedure/event.
6. Stored function không được thực hiện explicit hoặc implicit commit/rollback.
7. Trigger không được bắt đầu hoặc kết thúc transaction; ROLLBACK TO SAVEPOINT là ngoại lệ vì không kết thúc transaction.
8. Procedure được gọi từ function/trigger phải tuân thủ các giới hạn của ngữ cảnh gọi.
9. Function và trigger tham gia transaction của statement/caller, không tự quyết định commit.
10. Lỗi trigger làm statement thất bại; với InnoDB thay đổi transactional của statement được rollback, nhưng transaction lớn hơn có thể vẫn mở.
11. EXIT HANDLER FOR SQLEXCEPTION kết hợp ROLLBACK và RESIGNAL là mẫu xử lý lỗi phổ biến cho procedure-owned transaction.
12. NOT FOUND không thuộc SQLEXCEPTION; phải xử lý theo SQLSTATE class 02 khi cần.
13. SAVEPOINT chỉ tạo mốc trong transaction hiện tại, không tạo transaction mới.
14. DDL như TRUNCATE, ALTER TABLE và CREATE INDEX có thể implicit commit; không đặt giữa transaction nghiệp vụ nếu cần rollback.
15. ROLLBACK chỉ bảo đảm đầy đủ với transactional storage engine; InnoDB là lựa chọn thông dụng.
16. Hãy kiểm thử transaction boundary với cả caller, procedure, function, trigger và nhiều session.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual**:

1. [Restrictions on Stored Programs](https://dev.mysql.com/doc/refman/9.7/en/stored-program-restrictions.html): giới hạn transaction-control trong function/trigger và giới hạn procedure được gọi từ function/trigger.
2. [START TRANSACTION, COMMIT, and ROLLBACK Statements](https://dev.mysql.com/doc/refman/9.7/en/commit.html): transaction session, autocommit, START TRANSACTION, COMMIT, ROLLBACK và việc bắt đầu transaction commit transaction đang chờ.
3. [Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/9.7/en/implicit-commit.html): DDL, TRUNCATE, quyền người dùng và câu lệnh implicit commit.
4. [Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/9.7/en/trigger-syntax.html): giới hạn transaction trong trigger, ROLLBACK TO SAVEPOINT và xử lý lỗi trigger.
5. [SAVEPOINT, ROLLBACK TO SAVEPOINT, and RELEASE SAVEPOINT](https://dev.mysql.com/doc/refman/9.7/en/savepoint.html): rollback một phần, row lock và savepoint level trong function/trigger.
6. [DECLARE ... HANDLER Statement](https://dev.mysql.com/doc/refman/9.7/en/declare-handler.html): EXIT, CONTINUE, SQLSTATE, SQLEXCEPTION, NOT FOUND và việc UNDO không được hỗ trợ.
7. [Performance Schema Transaction Tables](https://dev.mysql.com/doc/refman/9.7/en/performance-schema-transaction-tables.html): quan hệ giữa transaction event và stored procedure/function/trigger event.
8. [InnoDB autocommit, Commit, and Rollback](https://dev.mysql.com/doc/refman/9.7/en/innodb-autocommit-commit-rollback.html): autocommit và transaction nhiều statement trong InnoDB.
9. [CREATE PROCEDURE and CREATE FUNCTION Statements](https://dev.mysql.com/doc/refman/9.7/en/create-procedure.html): khác biệt về transaction statement giữa procedure và function.

