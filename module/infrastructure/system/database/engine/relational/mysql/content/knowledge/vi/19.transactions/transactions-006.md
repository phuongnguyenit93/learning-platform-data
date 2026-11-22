# DDL implicit commit và các ngoại lệ cần kiểm tra

Transaction của InnoDB cho phép nhóm nhiều thao tác dữ liệu thành một đơn vị: hoặc COMMIT tất cả, hoặc ROLLBACK các thay đổi chưa commit. Tuy nhiên, không phải mọi câu lệnh SQL đều nằm trong transaction theo cách đó. Trong MySQL, nhiều câu lệnh DDL như ALTER TABLE, CREATE TABLE, DROP TABLE, TRUNCATE TABLE và CREATE INDEX gây **implicit commit**. Khi chạy một câu lệnh như vậy trong lúc transaction đang mở, MySQL tự kết thúc transaction hiện tại theo quy tắc của câu lệnh.

Điều này có ảnh hưởng trực tiếp đến migration và vận hành production. Nếu một transaction đã cập nhật dữ liệu rồi mới chạy ALTER TABLE, phần DML trước DDL có thể đã được commit trước khi ALTER TABLE thực thi. Một lệnh ROLLBACK sau đó không thể hoàn tác phần dữ liệu đã commit và cũng không biến DDL thành thao tác có thể rollback như DML thông thường.

Một số ngoại lệ cần hiểu rõ: CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit theo quy tắc thông thường, nhưng bản thân việc tạo hoặc xóa temporary table cũng không được rollback. CREATE TABLE ... SELECT có quy tắc riêng và vẫn gây implicit commit. Ngoài ra, MySQL 8.0 có Atomic DDL cho các thao tác và storage engine được hỗ trợ; Atomic DDL bảo vệ tính toàn vẹn của một câu lệnh khi server gặp sự cố, nhưng không làm cho DDL trở thành một phần có thể rollback trong transaction của người dùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích implicit commit và nhận diện các ranh giới transaction do DDL tạo ra.
- Phân biệt DDL, DML và các câu lệnh quản trị có thể gây implicit commit.
- Nhận biết các câu lệnh DDL phổ biến như ALTER, CREATE, DROP, RENAME, TRUNCATE và CREATE/DROP INDEX.
- Hiểu ngoại lệ của CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE.
- Giải thích vì sao temporary table không rollback được dù thao tác tạo/xóa không commit transaction.
- Phân biệt CREATE TABLE ... SELECT với CREATE TEMPORARY TABLE đơn giản.
- Hiểu khác biệt giữa implicit commit, Atomic DDL và khả năng rollback của InnoDB.
- Dự đoán tác động của DDL lên DML đang chờ commit, SAVEPOINT và ROLLBACK.
- Lập kế hoạch migration có kiểm tra, backup, metadata lock và khả năng phục hồi.
- Biết các thao tác cần xác minh theo phiên bản MySQL và loại storage engine.

## 1. Transaction và DDL giải quyết hai vấn đề khác nhau

Transaction quản lý tính toàn vẹn của các thay đổi dữ liệu. Với InnoDB, các câu lệnh INSERT, UPDATE và DELETE thường có thể được COMMIT hoặc ROLLBACK trong transaction.

Ví dụ:

    START TRANSACTION;

    UPDATE bank_account_demo
    SET balance = balance - 100.00
    WHERE account_id = 1;

    UPDATE bank_account_demo
    SET balance = balance + 100.00
    WHERE account_id = 2;

    COMMIT;

Hai thay đổi số dư được commit cùng nhau. Nếu có lỗi trước COMMIT, ứng dụng có thể ROLLBACK để hoàn tác cả hai thay đổi, với điều kiện các bảng dùng storage engine có hỗ trợ transaction như InnoDB.

DDL thay đổi cấu trúc hoặc đối tượng database, ví dụ:

    ALTER TABLE bank_account_demo
        ADD COLUMN account_label VARCHAR(80) NULL;

    CREATE INDEX idx_bank_account_label
        ON bank_account_demo (account_label);

Các câu lệnh này có quy tắc transaction riêng. Với nhiều DDL trong MySQL, server tự commit transaction đang mở trước khi thực thi. Một số DDL còn kết thúc transaction sau khi hoàn tất. Vì vậy, không thể xem DDL như một câu UPDATE khác và mong ROLLBACK cuối cùng hoàn tác mọi việc.

### 1.1. DDL, DML và câu lệnh quản trị

| Nhóm | Mục đích | Ví dụ | Transaction behavior |
|---|---|---|---|
| DML | Đọc hoặc thay đổi hàng dữ liệu | SELECT, INSERT, UPDATE, DELETE | DML trên InnoDB có thể tham gia transaction |
| DDL | Tạo hoặc thay đổi cấu trúc/đối tượng | CREATE TABLE, ALTER TABLE, DROP TABLE, TRUNCATE | Nhiều câu lệnh gây implicit commit |
| DCL/account management | Quản lý quyền và tài khoản | GRANT, REVOKE, CREATE USER, ALTER USER | Một số câu lệnh gây implicit commit |
| Administrative | Bảo trì hoặc quản lý server/table | ANALYZE TABLE, OPTIMIZE TABLE, FLUSH | Một số câu lệnh gây implicit commit |
| Transaction control | Điều khiển transaction và khóa | START TRANSACTION, COMMIT, ROLLBACK, LOCK TABLES | Có quy tắc kết thúc hoặc mở transaction riêng |

Không nên chỉ phân loại câu lệnh theo tên gọi. Khi chạy trong transaction, hãy kiểm tra danh sách implicit commit của đúng phiên bản MySQL và loại thao tác đang dùng.

## 2. Implicit commit hoạt động như thế nào?

Implicit commit là việc MySQL tự kết thúc transaction đang hoạt động mà không cần ứng dụng gửi lệnh COMMIT tường minh. Đối với DDL thông thường, transaction hiện tại được commit trước khi câu lệnh DDL thực thi. Nhiều DDL cũng tạo ranh giới commit sau khi hoàn tất; chi tiết chính xác phụ thuộc loại statement.

Ví dụ:

    START TRANSACTION;

    UPDATE bank_account_demo
    SET balance = balance - 100.00
    WHERE account_id = 1;

    ALTER TABLE bank_account_demo
        ADD COLUMN note VARCHAR(100) NULL;

    ROLLBACK;

Ứng dụng có thể nghĩ ROLLBACK cuối cùng sẽ hoàn tác UPDATE và ALTER TABLE. Thực tế, ALTER TABLE gây implicit commit cho transaction đang mở trước khi chạy. Vì vậy, UPDATE trước ALTER TABLE đã được commit. DDL cũng không được hoàn tác bằng ROLLBACK cuối cùng. ROLLBACK chỉ tác động đến một transaction mới nếu có thay đổi transactional được thực hiện sau ranh giới DDL và transaction đó còn mở.

Sơ đồ:

    START TRANSACTION
           |
           v
    UPDATE account
           |
           v
    ALTER TABLE
           |
           +---- implicit commit transaction trước DDL
           |
           +---- DDL thực thi theo cơ chế riêng
           |
           v
    ROLLBACK
           |
           +---- không hoàn tác UPDATE đã commit
           +---- không hoàn tác ALTER TABLE

### 2.1. Implicit commit xảy ra ngay cả khi DDL thất bại?

Đây là điểm rất quan trọng khi lập kế hoạch. Việc commit transaction trước DDL diễn ra như một phần quy tắc thực thi của statement. Nếu DDL sau đó thất bại vì lỗi schema, quyền, metadata lock timeout hoặc điều kiện khác, phần DML đã được commit trước đó vẫn không tự quay lại.

Ví dụ minh họa trong sandbox:

    START TRANSACTION;

    UPDATE bank_account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    -- Giả sử cột account_id đã tồn tại, câu ALTER này sẽ thất bại.
    ALTER TABLE bank_account_demo
        ADD COLUMN account_id BIGINT NULL;

    ROLLBACK;

Dù ALTER TABLE lỗi do trùng tên cột, UPDATE trước đó đã đi qua ranh giới implicit commit. Không thể dựa vào lỗi DDL để mong transaction trước đó được khôi phục.

### 2.2. ROLLBACK sau DDL không phải undo migration

DDL như ALTER TABLE, CREATE TABLE hoặc DROP TABLE không được đưa vào undo log giao dịch của người dùng theo cách cho phép ROLLBACK khôi phục schema cũ. Cần có kế hoạch migration ngược, bản sao lưu, snapshot hoặc thao tác phục hồi riêng nếu thay đổi cấu trúc gây lỗi.

Không chạy chuỗi DDL và DML trong một transaction rồi xem ROLLBACK cuối cùng là phương án phục hồi chung. Hãy coi mỗi DDL là một ranh giới cần được lập kế hoạch độc lập.

## 3. Các DDL thường gây implicit commit

Các nhóm sau thường gây implicit commit trong MySQL:

### 3.1. CREATE

Các lệnh tạo đối tượng thường gặp:

- CREATE DATABASE
- CREATE TABLE
- CREATE INDEX
- CREATE VIEW
- CREATE TRIGGER
- CREATE PROCEDURE và CREATE FUNCTION
- CREATE EVENT
- CREATE USER và CREATE ROLE

Ví dụ:

    START TRANSACTION;
    INSERT INTO migration_audit_demo (message)
    VALUES ('before create table');

    CREATE TABLE migration_created_demo (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        description VARCHAR(100) NOT NULL
    ) ENGINE = InnoDB;

Transaction đang mở bị kết thúc trước khi CREATE TABLE thực thi. Không nên đặt CREATE TABLE giữa một chuỗi DML mà ứng dụng cần rollback như một đơn vị.

### 3.2. ALTER

Các lệnh ALTER thay đổi cấu trúc hoặc thuộc tính đối tượng:

- ALTER TABLE
- ALTER DATABASE
- ALTER VIEW
- ALTER EVENT
- ALTER USER
- ALTER PROCEDURE hoặc ALTER FUNCTION
- ALTER INSTANCE và một số thao tác quản trị khác

Ví dụ:

    ALTER TABLE migration_created_demo
        ADD COLUMN created_at DATETIME(6) NULL;

ALTER TABLE có thể dùng thuật toán INSTANT, INPLACE hoặc COPY tùy thay đổi và phiên bản. Dù DDL có thể thực hiện online hoặc giảm mức khóa, điều đó không biến nó thành thao tác transactional có thể rollback.

### 3.3. DROP

Các lệnh DROP xóa đối tượng:

- DROP TABLE
- DROP DATABASE
- DROP INDEX
- DROP VIEW
- DROP TRIGGER
- DROP PROCEDURE và DROP FUNCTION
- DROP EVENT
- DROP USER hoặc DROP ROLE

Ví dụ:

    DROP TABLE migration_created_demo;

DROP TABLE là DDL và không thể được khôi phục bằng ROLLBACK của transaction người dùng. Cần xác minh đúng schema, đúng bảng, backup và phụ thuộc trước khi thực thi.

### 3.4. RENAME và TRUNCATE

RENAME TABLE đổi tên đối tượng:

    RENAME TABLE old_customer TO customer_archive;

TRUNCATE TABLE xóa toàn bộ hàng bằng thao tác DDL:

    TRUNCATE TABLE staging_import_demo;

TRUNCATE thường nhanh hơn DELETE không có WHERE trên bảng lớn, nhưng có semantics khác:

- TRUNCATE là DDL và gây implicit commit.
- TRUNCATE không thể được hoàn tác bằng ROLLBACK của transaction người dùng.
- TRUNCATE thường đặt lại bộ đếm AUTO_INCREMENT của bảng.
- DELETE là DML; với InnoDB, DELETE có thể rollback nếu transaction chưa commit.
- DELETE có thể dùng WHERE để xóa một phần dữ liệu; TRUNCATE xóa toàn bộ hàng của bảng.

So sánh:

    START TRANSACTION;
    DELETE FROM staging_import_demo;
    ROLLBACK;

Với bảng InnoDB, các hàng bị DELETE có thể được khôi phục bởi ROLLBACK.

    START TRANSACTION;
    TRUNCATE TABLE staging_import_demo;
    ROLLBACK;

TRUNCATE đã tạo ranh giới implicit commit; ROLLBACK không khôi phục các hàng đã truncate.

### 3.5. CREATE INDEX và DROP INDEX

Tạo hoặc xóa index cũng là DDL:

    CREATE INDEX idx_order_created_at
    ON sales_order (created_at);

    DROP INDEX idx_order_created_at
    ON sales_order;

Index online hoặc thao tác thêm index với LOCK=NONE nếu được hỗ trợ vẫn có quy tắc implicit commit. Online DDL mô tả mức độ cho phép đọc/ghi đồng thời trong quá trình thay đổi; nó không có nghĩa DDL nằm trong transaction có thể rollback.

## 4. Các câu lệnh không phải DDL thuần nhưng có thể commit

Không phải chỉ DDL mới gây implicit commit. Một số câu lệnh điều khiển transaction, quản lý tài khoản và quản trị server cũng có thể kết thúc transaction đang mở.

### 4.1. START TRANSACTION và BEGIN

START TRANSACTION hoặc BEGIN bắt đầu một transaction mới. Nếu session đang có transaction hoạt động, lệnh bắt đầu transaction mới sẽ kết thúc transaction hiện tại trước.

    START TRANSACTION;
    UPDATE account_demo SET balance = balance - 5 WHERE account_id = 1;

    START TRANSACTION;

Lệnh START TRANSACTION thứ hai không tạo transaction lồng nhau. Transaction đầu tiên được kết thúc trước khi transaction mới bắt đầu.

MySQL không hỗ trợ nested transaction theo kiểu START TRANSACTION bên trong START TRANSACTION. Nếu cần điểm quay lui trong một transaction, dùng SAVEPOINT.

### 4.2. SET autocommit

Kiểm tra chế độ:

    SELECT @@SESSION.autocommit;

Nếu session đang có autocommit = 0 và đổi thành 1:

    SET autocommit = 1;

thì thay đổi từ 0 sang 1 gây commit transaction đang mở. Đặt autocommit = 0 không có cùng tác động commit này.

Không đổi autocommit giữa một luồng xử lý mà không hiểu trạng thái transaction hiện tại. Trong ứng dụng connection pool, phải bảo đảm session được trả về pool với trạng thái đã được chuẩn hóa.

### 4.3. LOCK TABLES và UNLOCK TABLES

LOCK TABLES gây implicit commit trước khi khóa bảng. UNLOCK TABLES có thể commit nếu session đang giữ table lock được tạo bằng LOCK TABLES. Hành vi cụ thể phụ thuộc loại lock và cơ chế khóa được dùng.

Ví dụ:

    LOCK TABLES sales_order WRITE;
    -- thao tác trong lúc giữ lock
    UNLOCK TABLES;

Đây là cơ chế khóa bảng, không thay thế transaction row-level locking của InnoDB. Không dùng LOCK TABLES như cách tạo transaction lồng hoặc gom DDL/DML thành một đơn vị rollback.

### 4.4. Account management và quyền

Các câu lệnh quản lý tài khoản/quyền có thể gây implicit commit:

- CREATE USER
- ALTER USER
- DROP USER
- RENAME USER
- GRANT
- REVOKE
- SET PASSWORD

Ví dụ:

    GRANT SELECT ON reporting_db.* TO 'report_reader'@'%';

Không chạy GRANT hoặc ALTER USER giữa transaction dữ liệu và kỳ vọng ROLLBACK sẽ hoàn tác thay đổi quyền hoặc phục hồi DML trước đó.

### 4.5. Một số lệnh quản trị

Các lệnh như ANALYZE TABLE, OPTIMIZE TABLE, REPAIR TABLE, FLUSH, CACHE INDEX, LOAD INDEX INTO CACHE và RESET có thể có quy tắc implicit commit. Danh sách và chi tiết có thể thay đổi theo phiên bản và loại thao tác.

Khi viết migration hoặc script vận hành, hãy kiểm tra danh sách statement gây implicit commit trong tài liệu của đúng phiên bản MySQL. Không giả định một lệnh là “chỉ đọc” hoặc “chỉ bảo trì” thì sẽ không ảnh hưởng transaction.

## 5. Ngoại lệ: CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE

MySQL có ngoại lệ quan trọng: CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit theo quy tắc thông thường.

Ví dụ:

    START TRANSACTION;

    UPDATE account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    CREATE TEMPORARY TABLE tmp_account_check (
        account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        observed_balance DECIMAL(14,2) NOT NULL
    ) ENGINE = InnoDB;

    ROLLBACK;

Transaction vẫn có thể rollback phần UPDATE vì CREATE TEMPORARY TABLE không commit transaction đang hoạt động. Tuy nhiên, bảng tạm đã được tạo vẫn tồn tại trong session sau ROLLBACK.

Đây là điểm dễ nhầm:

- CREATE TEMPORARY TABLE không implicit commit.
- Nhưng thao tác tạo temporary table không được rollback.
- ROLLBACK hoàn tác DML transactional chưa commit, không xóa bảng tạm vừa tạo.
- Temporary table tự biến mất khi session kết thúc hoặc khi được DROP.

Tương tự, DROP TEMPORARY TABLE không gây implicit commit nhưng việc xóa bảng tạm không thể được khôi phục bằng ROLLBACK.

### 5.1. Temporary table không phải bảng transactional có thể rollback DDL

Tạo bảng tạm và insert dữ liệu vào bảng tạm là hai thao tác khác nhau:

    START TRANSACTION;

    CREATE TEMPORARY TABLE tmp_work (
        id INT NOT NULL PRIMARY KEY,
        note VARCHAR(100) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO tmp_work (id, note)
    VALUES (1, 'temporary row');

    ROLLBACK;

Sau ROLLBACK:

- Bảng tmp_work vẫn tồn tại trong session vì CREATE TEMPORARY TABLE không bị rollback.
- Hàng được INSERT vào tmp_work có thể bị rollback vì bảng tạm dùng InnoDB và DML tham gia transaction.

Điều này minh họa rằng vòng đời đối tượng bảng tạm và dữ liệu transactional trong bảng là hai lớp khác nhau.

### 5.2. Temporary table có phạm vi session

Temporary table chỉ nhìn thấy trong connection đã tạo nó. Connection khác không thể truy cập bảng tạm cùng tên trong session hiện tại. Khi connection đóng, MySQL tự xóa các temporary table của session đó.

Với connection pool, một connection có thể được tái sử dụng. Nếu ứng dụng tạo temporary table rồi không DROP, lần mượn connection sau có thể gặp lỗi table already exists hoặc vô tình dùng dữ liệu tạm còn sót trong cùng session. Nên DROP TEMPORARY TABLE khi hoàn tất hoặc dùng tên và quy trình quản lý có kiểm soát.

### 5.3. Ngoại lệ không áp dụng cho mọi DDL trên temporary table

Đừng suy rộng rằng mọi thao tác trên temporary table đều không commit. Ngoại lệ được nêu cho CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE. Các lệnh DDL khác như ALTER TABLE vẫn có quy tắc implicit commit cần kiểm tra, kể cả khi đối tượng bị thay đổi là temporary table.

Ví dụ, không giả định ALTER TABLE tmp_work có thể chạy giữa transaction mà vẫn giữ nguyên ranh giới transaction. Hãy kiểm tra đúng statement trong tài liệu MySQL và thử trong sandbox.

### 5.4. CREATE TEMPORARY TABLE ... SELECT là trường hợp đặc biệt

CREATE TABLE ... SELECT có quy tắc implicit commit riêng. Không nên suy luận từ ngoại lệ của CREATE TEMPORARY TABLE đơn giản rằng mọi biến thể có SELECT đều không commit. CREATE TABLE ... SELECT gây implicit commit theo quy tắc của statement này; hãy kiểm tra tài liệu phiên bản và dùng một cách tách bước rõ ràng nếu transaction boundary quan trọng.

Ví dụ tạo bảng tạm từ truy vấn:

    CREATE TEMPORARY TABLE tmp_paid_orders AS
    SELECT order_id, customer_id, amount
    FROM sales_order
    WHERE order_status = 'PAID';

Khi dùng dạng này, không dựa vào giả định rằng transaction trước đó vẫn được giữ nguyên. Nếu cần giữ transaction boundary, hãy kiểm thử trên đúng phiên bản và tách thao tác tạo cấu trúc với INSERT ... SELECT theo quy tắc đã xác minh.

## 6. Atomic DDL trong MySQL 8.0 không đồng nghĩa transactional DDL

MySQL 8.0 giới thiệu Atomic DDL cho các thao tác và storage engine được hỗ trợ. Atomic DDL phối hợp thay đổi data dictionary, thao tác storage engine và ghi binary log liên quan để một câu lệnh DDL có tính nguyên tử khi server gặp sự cố.

Về mặt vận hành, điều đó có nghĩa khi server crash giữa một DDL được hỗ trợ, quá trình recovery sẽ đưa thao tác về trạng thái hoàn tất hoặc chưa áp dụng theo cơ chế Atomic DDL. Nó tránh một số trạng thái nửa chừng của metadata và storage engine.

Nhưng Atomic DDL **không** có nghĩa:

- Có thể đặt ALTER TABLE trong transaction rồi ROLLBACK để quay lại schema cũ.
- Có thể nhóm nhiều DDL và DML thành một transaction duy nhất.
- Một DDL thất bại sẽ tự hoàn tác DML đã được implicit commit trước đó.
- Mọi statement, mọi storage engine và mọi thao tác quản trị đều có Atomic DDL.

Phân biệt:

| Khái niệm | Bảo vệ điều gì? | ROLLBACK của người dùng có hoàn tác được không? |
|---|---|---|
| Transactional DML của InnoDB | Nhóm thay đổi hàng dữ liệu | Có, trước COMMIT |
| Implicit commit | Kết thúc transaction đang mở theo quy tắc statement | Không thể quay lại phần đã commit |
| Atomic DDL | Tính toàn vẹn của một DDL được hỗ trợ khi thực thi/recovery | Không; không phải transactional DDL |
| Backup/restore hoặc migration ngược | Khả năng phục hồi sau thay đổi schema/dữ liệu | Phụ thuộc quy trình phục hồi |

Vì vậy, Atomic DDL làm DDL an toàn hơn trước crash nhưng không thay đổi quy tắc transaction mà ứng dụng cần tuân thủ.

## 7. SAVEPOINT không bảo vệ được DDL

SAVEPOINT tạo điểm quay lui bên trong một transaction. Nó hữu ích cho DML:

    START TRANSACTION;

    UPDATE account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    SAVEPOINT after_debit;

    UPDATE account_demo
    SET balance = balance + 10.00
    WHERE account_id = 2;

    ROLLBACK TO SAVEPOINT after_debit;
    COMMIT;

Lệnh ROLLBACK TO SAVEPOINT hoàn tác các thay đổi sau savepoint nhưng giữ các thay đổi trước đó trong transaction.

Nếu chạy DDL sau SAVEPOINT:

    START TRANSACTION;
    UPDATE account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    SAVEPOINT before_ddl;

    ALTER TABLE account_demo
        ADD COLUMN audit_note VARCHAR(100) NULL;

Implicit commit kết thúc transaction và xóa các savepoint của transaction đó. Sau DDL, SAVEPOINT before_ddl không còn tồn tại; ROLLBACK TO SAVEPOINT sẽ báo lỗi savepoint không tồn tại.

Không đặt DDL giữa một chuỗi thao tác đang dựa vào SAVEPOINT. Hãy chia quy trình thành các giai đoạn có ranh giới rõ.

## 8. DDL và storage engine

Khả năng rollback của DML phụ thuộc storage engine. InnoDB hỗ trợ transaction; MyISAM không hỗ trợ transaction theo cách của InnoDB.

Kiểm tra engine của bảng:

    SHOW TABLE STATUS LIKE 'account_demo';

Hoặc:

    SELECT
        TABLE_NAME,
        ENGINE
    FROM information_schema.tables
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'account_demo';

Nếu một transaction cập nhật bảng InnoDB và bảng MyISAM, ROLLBACK không thể hoàn tác thay đổi đã ghi vào MyISAM. Đừng suy luận rằng chỉ cần START TRANSACTION thì mọi bảng đều trở nên transactional.

Với bảng production, hãy kiểm tra engine trước khi thiết kế rollback, backup, migration và quy trình phục hồi.

## 9. TRUNCATE TABLE và DELETE: khác nhau ở ranh giới transaction

DELETE xóa hàng theo điều kiện và là DML:

    START TRANSACTION;

    DELETE FROM session_event
    WHERE created_at < '2025-01-01';

    -- Kiểm tra số hàng và dữ liệu còn lại
    ROLLBACK;

Nếu session_event dùng InnoDB, thao tác DELETE có thể được hoàn tác trước COMMIT.

TRUNCATE xóa toàn bộ hàng và là DDL:

    TRUNCATE TABLE session_event;

Nó gây implicit commit và không thể được hoàn tác bằng ROLLBACK. Ngoài ra, TRUNCATE thường reset AUTO_INCREMENT. Trước khi dùng, xác nhận đúng bảng, schema, phụ thuộc khóa ngoại, quyền và backup.

| Tiêu chí | DELETE | TRUNCATE |
|---|---|---|
| Nhóm câu lệnh | DML | DDL |
| WHERE | Có | Không |
| Có thể xóa một phần hàng | Có | Không |
| InnoDB rollback trong transaction | Có, trước COMMIT | Không |
| Implicit commit | Không theo quy tắc DDL | Có |
| AUTO_INCREMENT | Không tự reset về đầu theo cách truncate | Thường được reset |
| Trigger DELETE | Kích hoạt trigger DELETE cho hàng bị xóa | Không chạy trigger DELETE theo từng hàng |

Chọn DELETE khi cần transaction, điều kiện lọc hoặc trigger theo từng hàng. Chọn TRUNCATE khi muốn làm rỗng toàn bảng và đã chấp nhận semantics DDL.

## 10. DDL, metadata lock và thời gian triển khai

DDL có thể cần metadata lock (MDL) để bảo đảm schema không thay đổi trong khi câu lệnh đang chạy. Một truy vấn dài hoặc transaction đang giữ metadata lock có thể khiến ALTER TABLE phải chờ. Ngược lại, DDL đang chờ có thể làm các truy vấn khác xếp hàng theo tùy tình huống.

Trước migration, kiểm tra:

- Transaction dài đang mở trên bảng mục tiêu.
- Truy vấn đang chạy hoặc session giữ metadata lock.
- Dung lượng bảng và index.
- Thuật toán ALTER có thể dùng: INSTANT, INPLACE hoặc COPY.
- Khả năng đọc/ghi trong lúc DDL chạy.
- Thời gian thực hiện và ảnh hưởng đến replication.
- Dung lượng tạm và I/O cần thiết nếu phải rebuild bảng.

Ví dụ yêu cầu thuật toán/lock nếu phiên bản và thao tác hỗ trợ:

    ALTER TABLE sales_order
        ADD COLUMN source_code VARCHAR(30) NULL,
        ALGORITHM = INSTANT;

Không phải mọi thay đổi đều hỗ trợ INSTANT. Nếu server từ chối, hãy xem thông báo lỗi và tài liệu phiên bản; không tự động hạ xuống COPY trên production khi chưa đánh giá thời gian khóa và dung lượng.

Online DDL không loại bỏ implicit commit. Nó chỉ thay đổi cách MySQL thực hiện thao tác schema và mức độ đồng thời có thể duy trì.

## 11. Thiết kế migration an toàn

Một migration production nên được thiết kế như một quy trình có nhiều bước, thay vì một transaction giả định bao trùm DDL và DML.

### 11.1. Trước khi chạy DDL

1. Xác định chính xác database, table, cột và index cần thay đổi.
2. Đọc SHOW CREATE TABLE và kiểm tra phiên bản MySQL.
3. Xác định câu lệnh có implicit commit hay ngoại lệ nào áp dụng.
4. Kiểm tra engine và transaction đang hoạt động.
5. Xác minh transaction dài, metadata lock và tải hệ thống.
6. Kiểm tra backup/restore và khả năng migration ngược.
7. Thử trên staging với kích thước dữ liệu gần production.
8. Ước lượng thời gian, dung lượng và ảnh hưởng replication.
9. Xác định cách ứng dụng tương thích với schema trước, trong và sau migration.

### 11.2. Chia migration thành các giai đoạn

Một chiến lược phổ biến khi thêm cột mới:

1. Thêm cột nullable hoặc có default phù hợp bằng DDL.
2. Triển khai ứng dụng có thể đọc/ghi schema mới nhưng vẫn tương thích trong giai đoạn chuyển tiếp.
3. Backfill dữ liệu theo lô bằng DML có thể theo dõi và kiểm soát.
4. Kiểm tra số hàng đã backfill, giá trị NULL còn lại và tính nhất quán.
5. Thêm constraint hoặc index ở một bước DDL riêng sau khi dữ liệu đạt yêu cầu.
6. Triển khai ứng dụng loại bỏ đường tương thích cũ khi mọi node đã cập nhật.

Mỗi bước DDL là một ranh giới riêng. Backfill DML có thể chia transaction theo lô để giới hạn undo log, lock duration và thời gian rollback.

### 11.3. Migration ngược không phải ROLLBACK SQL

Nếu migration thêm cột và ứng dụng gặp lỗi, migration ngược có thể là ALTER TABLE DROP COLUMN. Nhưng thao tác đó là một DDL mới, cũng có thể gây implicit commit và có rủi ro riêng.

Nếu migration đã ghi dữ liệu vào cột mới, DROP COLUMN có thể làm mất dữ liệu. Vì vậy, rollback ứng dụng và rollback schema cần được thiết kế riêng. Có trường hợp an toàn hơn là giữ cột mới, khôi phục phiên bản ứng dụng tương thích và xử lý dữ liệu sau.

## 12. Thực hành quan sát transaction boundary

Các ví dụ dưới đây nên chạy trên database sandbox, không chạy trên production.

### 12.1. Tạo bảng kiểm thử

    CREATE TABLE tx_ddl_demo (
        account_id INT NOT NULL PRIMARY KEY,
        balance DECIMAL(12,2) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO tx_ddl_demo (account_id, balance)
    VALUES (1, 100.00), (2, 200.00);

### 12.2. DML có thể rollback

    START TRANSACTION;

    UPDATE tx_ddl_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    SELECT * FROM tx_ddl_demo ORDER BY account_id;

    ROLLBACK;

    SELECT * FROM tx_ddl_demo ORDER BY account_id;

Sau ROLLBACK, số dư của account 1 trở lại 100.00.

### 12.3. DDL commit DML trước đó

    START TRANSACTION;

    UPDATE tx_ddl_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    ALTER TABLE tx_ddl_demo
        ADD COLUMN note VARCHAR(100) NULL;

    ROLLBACK;

    SELECT * FROM tx_ddl_demo ORDER BY account_id;

Sau ALTER TABLE, UPDATE trước đó đã được commit. ROLLBACK cuối không đưa balance về giá trị cũ và cũng không xóa cột note.

### 12.4. Temporary table không commit nhưng không rollback việc tạo

    START TRANSACTION;

    UPDATE tx_ddl_demo
    SET balance = balance - 5.00
    WHERE account_id = 1;

    CREATE TEMPORARY TABLE tmp_tx_check (
        account_id INT NOT NULL PRIMARY KEY,
        observed_balance DECIMAL(12,2) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO tmp_tx_check (account_id, observed_balance)
    SELECT account_id, balance
    FROM tx_ddl_demo;

    ROLLBACK;

    SHOW TABLES LIKE 'tmp_tx_check';
    SELECT * FROM tmp_tx_check;
    SELECT * FROM tx_ddl_demo ORDER BY account_id;

Sau ROLLBACK, tmp_tx_check vẫn tồn tại nhưng INSERT vào bảng tạm thuộc transaction đã rollback nên hàng vừa chèn không còn. UPDATE trên tx_ddl_demo cũng được rollback vì CREATE TEMPORARY TABLE không commit transaction.

Dọn dẹp:

    DROP TEMPORARY TABLE IF EXISTS tmp_tx_check;

### 12.5. Temporary table và CREATE TABLE ... SELECT

Thử nghiệm riêng CREATE TEMPORARY TABLE ... SELECT trong sandbox nếu cần xác nhận behavior của phiên bản triển khai. Không gộp phép thử này vào transaction chứa dữ liệu quan trọng; dạng ... SELECT có quy tắc implicit commit riêng so với CREATE TEMPORARY TABLE rỗng.

## 13. Kiểm tra session và trạng thái transaction

Một số thông tin hữu ích:

    SELECT
        VERSION() AS mysql_version,
        @@SESSION.autocommit AS autocommit_mode,
        @@SESSION.sql_mode AS session_sql_mode;

Có thể xem transaction InnoDB đang hoạt động:

    SELECT *
    FROM information_schema.innodb_trx;

Bảng metadata này hữu ích để phát hiện transaction chạy lâu, nhưng quyền xem và chi tiết có thể phụ thuộc phiên bản. Với MySQL 8.0, Performance Schema cũng cung cấp thông tin về thread, statement và lock; công cụ giám sát nên dùng các nguồn phù hợp với quyền hiện có.

Trước khi chạy DDL, kiểm tra:

- Session hiện tại có transaction đang mở không?
- Có DML chưa commit cần giữ trong transaction không?
- DDL có gây implicit commit không?
- Có session khác đang giữ metadata lock trên đối tượng không?
- Sau DDL, ứng dụng có đang giả định transaction cũ vẫn hoạt động không?

Không chỉ kiểm tra transaction của session chạy migration. Transaction dài từ session khác cũng có thể ảnh hưởng metadata lock và thời gian hoàn thành DDL.

## 14. Các trường hợp cần xác minh theo phiên bản

Danh sách statement gây implicit commit và các ngoại lệ được MySQL mô tả trong tài liệu theo phiên bản. Trước khi đưa một lệnh vào migration tự động, xác minh:

- Phiên bản MySQL server thực tế, không chỉ phiên bản client.
- Storage engine của bảng.
- Statement chính xác, bao gồm TEMPORARY hoặc SELECT nếu có.
- DDL có nằm trong nhóm Atomic DDL được hỗ trợ hay không.
- Thuật toán DDL và mức lock có được hỗ trợ cho cấu trúc cụ thể không.
- Câu lệnh có bị cấm trong XA transaction hoặc stored program hiện tại không.
- Hành vi có khác giữa MySQL Community, các phiên bản cũ và dịch vụ tương thích MySQL không.

Các quy tắc nên đặc biệt kiểm tra:

| Statement/tình huống | Điểm cần xác minh |
|---|---|
| CREATE TABLE / DROP TABLE | DDL thường gây implicit commit |
| CREATE TEMPORARY TABLE / DROP TEMPORARY TABLE | Ngoại lệ không implicit commit; bản thân tạo/xóa không rollback được |
| CREATE TABLE ... SELECT | Có quy tắc implicit commit riêng; không suy rộng ngoại lệ temporary table |
| ALTER TABLE trên bảng thường | DDL gây implicit commit |
| ALTER TABLE trên temporary table | Không suy rộng ngoại lệ CREATE/DROP TEMPORARY; kiểm tra quy tắc ALTER |
| CREATE INDEX / DROP INDEX | DDL, gây implicit commit |
| TRUNCATE TABLE | DDL, không rollback như DELETE |
| START TRANSACTION khi transaction đang mở | Kết thúc transaction trước khi bắt đầu transaction mới |
| SET autocommit = 1 khi đổi từ 0 | Commit transaction đang mở |
| LOCK TABLES / UNLOCK TABLES | Có quy tắc commit trước/đến lúc unlock tùy lock |
| GRANT / REVOKE / account management | Có thể gây implicit commit |
| ANALYZE / OPTIMIZE / FLUSH | Kiểm tra theo statement và phiên bản |

Đây là checklist cho các trường hợp phổ biến, không phải bản sao đầy đủ của tài liệu tham chiếu. Với lệnh ít gặp hoặc thay đổi theo phiên bản, hãy tra danh sách chính thức trước khi triển khai.

## 15. DDL trong XA transaction

XA transaction điều phối transaction phân tán giữa nhiều resource manager. Các statement gây implicit commit không được phép thực thi trong trạng thái XA ACTIVE theo các quy tắc XA của MySQL; server có thể từ chối statement thay vì âm thầm cho phép transaction tiếp tục.

Nếu ứng dụng dùng XA, không đặt DDL hoặc account-management statement có implicit commit trong nhánh xử lý XA. Thực hiện migration ngoài vòng đời XA và phối hợp với hệ thống điều phối transaction.

Không nhầm XA với transaction InnoDB thông thường. XA có trạng thái và giao thức prepare/commit riêng; lỗi statement trong XA cần được xử lý theo trạng thái XA và cơ chế recovery của coordinator.

## 16. Những lỗi thường gặp

- Đặt ALTER TABLE giữa START TRANSACTION và ROLLBACK rồi nghĩ mọi thay đổi sẽ được hoàn tác.
- Nghĩ DDL thất bại thì DML đã commit trước đó cũng tự rollback.
- Nhầm Atomic DDL với transactional DDL.
- Nghĩ online DDL hoặc ALGORITHM=INPLACE/INSTANT không gây implicit commit.
- Nghĩ CREATE TEMPORARY TABLE không commit đồng nghĩa việc tạo bảng tạm có thể rollback.
- Nghĩ DROP TEMPORARY TABLE có thể được ROLLBACK để khôi phục bảng.
- Suy rộng ngoại lệ temporary table cho mọi ALTER hoặc CREATE ... SELECT.
- Dùng TRUNCATE khi cần khả năng rollback như DELETE.
- Dùng SAVEPOINT để bảo vệ các thay đổi trước DDL.
- Giả định START TRANSACTION tạo transaction lồng nhau.
- Đổi autocommit từ 0 sang 1 mà không biết transaction đang mở sẽ được commit.
- Chạy GRANT, REVOKE hoặc ALTER USER giữa transaction dữ liệu.
- Chỉ kiểm tra session migration mà bỏ qua transaction dài và metadata lock từ session khác.
- Cho rằng tất cả bảng đều transactional dù có thể dùng MyISAM hoặc engine khác.
- Triển khai DDL production mà không có backup, kế hoạch migration ngược và kiểm thử tương thích.

## 17. Checklist trước khi chạy DDL trong hệ thống có transaction

- Đã xác định statement là DDL, DML, account management, administrative hay transaction control.
- Đã kiểm tra statement có implicit commit trước hoặc sau thực thi không.
- Đã xác định ngoại lệ có áp dụng chính xác cho cú pháp đang dùng hay không.
- Đã kiểm tra phiên bản MySQL và storage engine.
- Đã xác nhận không có DML chưa commit mà ứng dụng mong muốn rollback sau DDL.
- Đã hiểu SAVEPOINT sẽ bị mất khi transaction bị implicit commit.
- Đã phân biệt Atomic DDL với rollback của transaction người dùng.
- Đã kiểm tra metadata lock, transaction dài và tải hệ thống.
- Đã đánh giá thuật toán DDL, lock, dung lượng và replication.
- Đã có backup/restore hoặc phương án migration ngược phù hợp.
- Đã thử trên staging với schema và dữ liệu gần production.
- Đã chia DDL và backfill DML thành các giai đoạn có ranh giới rõ.
- Đã xác định cách ứng dụng tương thích trong suốt quá trình migration.
- Đã xác minh các ngoại lệ CREATE/DROP TEMPORARY và CREATE TABLE ... SELECT nếu có.
- Đã kiểm thử kết quả và kiểm tra schema sau migration.

Implicit commit là ranh giới quan trọng giữa transaction dữ liệu và thay đổi cấu trúc trong MySQL. Nhiều DDL như ALTER, CREATE, DROP, RENAME, TRUNCATE và CREATE/DROP INDEX sẽ kết thúc transaction đang mở; một số lệnh quản trị, quản lý quyền và điều khiển transaction cũng có thể làm điều tương tự. CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE là ngoại lệ về implicit commit nhưng thao tác tạo/xóa bảng tạm không rollback được; CREATE TABLE ... SELECT cần được xem xét riêng. Atomic DDL trong MySQL 8.0 tăng độ an toàn của một câu lệnh khi crash nhưng không biến DDL thành transactional DDL. Hãy xem mỗi DDL là một ranh giới migration độc lập, kiểm tra đúng phiên bản và engine, bảo vệ DML chưa commit, kiểm soát metadata lock và chuẩn bị phương án phục hồi trước khi triển khai.
