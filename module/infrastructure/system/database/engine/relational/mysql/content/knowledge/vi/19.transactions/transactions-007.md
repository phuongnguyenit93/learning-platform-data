# Atomic DDL, implicit commit và giới hạn hoàn tác DDL

Trong MySQL, nhiều câu lệnh thay đổi cấu trúc schema như CREATE TABLE, ALTER TABLE, DROP TABLE và TRUNCATE TABLE là DDL (Data Definition Language). Chúng có quy tắc giao dịch khác với các câu lệnh DML như INSERT, UPDATE và DELETE. Một lệnh DDL thường tạo ranh giới commit ngầm (implicit commit), vì vậy bạn không thể đặt nhiều thay đổi schema vào một transaction rồi dùng ROLLBACK để hoàn tác tất cả.

Từ MySQL 8.0, Atomic DDL bổ sung khả năng thực hiện một số thao tác DDL theo nguyên tắc tất cả hoặc không có gì khi server gặp lỗi hoặc crash. Tuy nhiên, **Atomic DDL không đồng nghĩa với transactional DDL**: nó bảo vệ tính toàn vẹn của chính thao tác DDL trong quá trình thực thi và phục hồi, nhưng không làm cho DDL có thể được hoàn tác bằng ROLLBACK của transaction người dùng.

Bài học thuộc phạm vi DATABASE_MYSQL: hiểu ranh giới transaction, vận hành thay đổi schema, lập kế hoạch migration, giảm rủi ro mất dữ liệu và phân biệt khả năng phục hồi sau crash với khả năng rollback nghiệp vụ.

## 1. DDL, DML và transaction có vai trò khác nhau

### 1.1. DDL thay đổi cấu trúc database

DDL thay đổi đối tượng hoặc metadata của database:

- CREATE TABLE: tạo bảng.
- ALTER TABLE: thay đổi cấu trúc bảng.
- DROP TABLE: xóa bảng.
- RENAME TABLE: đổi tên bảng.
- CREATE INDEX và DROP INDEX: tạo hoặc xóa index.
- TRUNCATE TABLE: xóa toàn bộ hàng bằng thao tác DDL.

Ví dụ:

~~~sql
CREATE TABLE account (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    balance DECIMAL(15, 2) NOT NULL
) ENGINE = InnoDB;

ALTER TABLE account
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';

CREATE INDEX idx_account_status
    ON account(status);
~~~

Các lệnh này thay đổi schema và metadata của bảng.

### 1.2. DML thay đổi dữ liệu trong bảng

DML thao tác trên các hàng:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Với InnoDB, các thay đổi DML trong transaction có thể COMMIT hoặc ROLLBACK. Nếu có lỗi trước COMMIT, ứng dụng có thể rollback để đưa dữ liệu về trạng thái trước transaction.

### 1.3. Không được suy luận DDL có thể rollback giống DML

Ví dụ sau không tạo một transaction bao trọn thay đổi dữ liệu và cấu trúc:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE account_id = 1;

ALTER TABLE account
    ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
~~~

ALTER TABLE gây implicit commit. UPDATE phía trước được commit trước khi DDL thực thi. Sau khi ALTER hoàn tất, ROLLBACK không thể hoàn tác việc thêm cột hoặc lấy lại transaction đã được commit.

Đây là nguyên tắc cần nhớ khi viết migration: không đặt DDL giữa một chuỗi DML rồi giả định một lệnh ROLLBACK cuối cùng sẽ khôi phục mọi thứ.

## 2. Implicit commit là gì?

Implicit commit là việc MySQL tự động kết thúc transaction đang hoạt động mà không cần ứng dụng gọi COMMIT.

Một số câu lệnh gây commit ngầm trước khi thực thi; nhiều câu lệnh còn gây commit sau khi thực thi thành công. Điều này tạo ranh giới transaction mà ứng dụng cần biết.

Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO audit_log(message)
VALUES ('Bắt đầu thay đổi schema');

ALTER TABLE account
    ADD COLUMN source_code VARCHAR(30) NULL;

INSERT INTO audit_log(message)
VALUES ('Đã thêm source_code');

ROLLBACK;
~~~

Giả sử ALTER TABLE thành công:

1. INSERT đầu tiên được commit ngầm trước ALTER TABLE.
2. ALTER TABLE thực hiện và hoàn tất theo quy tắc DDL.
3. INSERT thứ hai thuộc transaction mới (nếu autocommit đang tắt).
4. ROLLBACK cuối cùng chỉ rollback INSERT thứ hai.
5. Dòng audit đầu tiên và thay đổi schema vẫn tồn tại.

Nếu muốn ghi audit và thay đổi schema có cùng vòng đời, cần thiết kế quy trình migration riêng, không dựa vào một transaction SQL duy nhất.

## 3. Những câu lệnh thường gây implicit commit

Các nhóm DDL phổ biến gây implicit commit gồm:

| Nhóm | Ví dụ |
|---|---|
| Database | CREATE DATABASE, ALTER DATABASE, DROP DATABASE |
| Table | CREATE TABLE, ALTER TABLE, DROP TABLE |
| Table name | RENAME TABLE |
| Index | CREATE INDEX, DROP INDEX |
| Table data theo DDL | TRUNCATE TABLE |
| View | CREATE VIEW, ALTER VIEW, DROP VIEW |
| Trigger | CREATE TRIGGER, DROP TRIGGER |
| Stored routine | CREATE PROCEDURE, ALTER PROCEDURE, DROP PROCEDURE; CREATE/DROP FUNCTION |
| Event | CREATE EVENT, ALTER EVENT, DROP EVENT |
| Tablespace/server object | Một số lệnh CREATE/ALTER/DROP TABLESPACE hoặc SERVER |

Danh sách chính xác có thể thay đổi theo phiên bản và nhóm câu lệnh. Ngoài DDL, một số thao tác quản trị cũng tạo ranh giới commit, chẳng hạn LOCK TABLES và một số lệnh bảo trì bảng.

Tra cứu manual của đúng phiên bản trước khi đưa một câu lệnh quản trị vào transaction.

### 3.1. START TRANSACTION và BEGIN cũng có thể kết thúc transaction trước đó

MySQL không hỗ trợ nested transaction theo cách một START TRANSACTION mới tạo transaction con bên trong transaction đang chạy.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 50
WHERE account_id = 1;

START TRANSACTION;

UPDATE account
SET balance = balance + 50
WHERE account_id = 2;

ROLLBACK;
~~~

START TRANSACTION thứ hai kết thúc transaction đang hoạt động trước đó. Vì vậy, UPDATE đầu tiên đã được commit; ROLLBACK chỉ ảnh hưởng transaction thứ hai.

Muốn chia một quy trình thành các điểm quay lui trong cùng transaction, dùng SAVEPOINT thay vì START TRANSACTION lồng nhau:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account
SET balance = balance + 50
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

COMMIT;
~~~

SAVEPOINT chỉ áp dụng cho transaction hỗ trợ rollback. Nó không bảo vệ DDL khỏi implicit commit.

### 3.2. Thay đổi autocommit

Khi autocommit đang tắt và bạn đổi sang bật:

~~~sql
SET autocommit = 0;

UPDATE account
SET balance = balance + 10
WHERE account_id = 1;

SET autocommit = 1;
~~~

Việc chuyển autocommit từ 0 sang 1 gây commit transaction đang hoạt động. Không dùng SET autocommit = 1 như một thao tác cấu hình vô hại ở giữa transaction.

Nếu ứng dụng dùng connection pool, cần quản lý autocommit rõ ràng và khôi phục trạng thái connection trước khi trả connection về pool.

## 4. Ngoại lệ với TEMPORARY TABLE

Hai câu lệnh tạo và xóa temporary table có hành vi đặc biệt:

- CREATE TEMPORARY TABLE không gây implicit commit.
- DROP TEMPORARY TABLE không gây implicit commit.

Tuy nhiên, việc tạo hoặc xóa temporary table **không thể được rollback** như thay đổi DML thông thường.

Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO audit_log(message)
VALUES ('Dòng này có thể rollback');

CREATE TEMPORARY TABLE temp_customer_ids (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
);

ROLLBACK;
~~~

Sau ROLLBACK:
- INSERT audit_log bị rollback.
- Temporary table vẫn tồn tại trong session hiện tại.

Đây là ngoại lệ dễ gây hiểu nhầm: câu lệnh không commit transaction nhưng bản thân thay đổi temporary table vẫn không được rollback.

Temporary table chỉ tồn tại trong connection tạo ra nó và tự biến mất khi session kết thúc. Không dùng temporary table để lưu dữ liệu cần tồn tại lâu dài hoặc làm cơ chế bảo đảm transaction.

Lưu ý: ngoại lệ trên nói về CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE. Các câu lệnh DDL khác tác động lên bảng vẫn phải kiểm tra quy tắc implicit commit của chúng.

## 5. Atomic DDL là gì?

Atomic DDL là khả năng thực hiện một thao tác DDL theo nguyên tắc toàn bộ thao tác được hoàn tất hoặc được phục hồi về trạng thái trước thao tác khi có lỗi/crash thuộc phạm vi được hỗ trợ.

Trước MySQL 8.0, một số thao tác DDL có thể để lại metadata hoặc file trung gian không nhất quán nếu server gặp sự cố ở thời điểm không thuận lợi. MySQL 8.0 đưa vào transactional data dictionary và cơ chế Atomic DDL để phối hợp thay đổi metadata, storage engine và binary log cho các thao tác được hỗ trợ.

Có thể hiểu bằng ví dụ ALTER TABLE:

~~~sql
ALTER TABLE account
    ADD COLUMN loyalty_level INT NOT NULL DEFAULT 0;
~~~

Với thao tác Atomic DDL được hỗ trợ trên InnoDB:
- Nếu DDL hoàn tất, schema mới được ghi nhận.
- Nếu server crash trong quá trình thao tác, recovery đưa hệ thống về trạng thái nhất quán: thay đổi DDL được hoàn tất hoặc được rollback theo cơ chế atomic.
- Không để bảng ở trạng thái nửa cũ, nửa mới do một phần metadata và một phần dữ liệu đã được áp dụng.

Atomic DDL bảo vệ tính toàn vẹn của thao tác ở cấp server/storage engine. Nó không biến ALTER TABLE thành một câu lệnh có thể ROLLBACK sau khi thành công.

## 6. Atomic DDL không phải transactional DDL

Hai khái niệm này giải quyết hai vấn đề khác nhau:

| Tiêu chí | Atomic DDL | Transactional DDL theo nghĩa người dùng |
|---|---|---|
| Mục tiêu | Bảo đảm một thao tác DDL được thực hiện toàn bộ hoặc phục hồi toàn bộ khi lỗi/crash | Cho phép đưa DDL vào transaction và hoàn tác bằng ROLLBACK |
| Khi DDL thành công | DDL đã hoàn tất và được commit theo ranh giới DDL | Có thể còn chờ COMMIT của transaction |
| ROLLBACK sau DDL | Không hoàn tác DDL đã thành công | Có thể hoàn tác nếu hệ quản trị hỗ trợ transactional DDL |
| Crash recovery | Có bảo đảm atomic cho thao tác được hỗ trợ | Phụ thuộc cơ chế transaction |
| MySQL | Có Atomic DDL cho một số thao tác từ MySQL 8.0 | DDL thông thường vẫn gây implicit commit |

Ví dụ:

~~~sql
START TRANSACTION;

ALTER TABLE account
    ADD COLUMN migration_flag TINYINT NOT NULL DEFAULT 0;

ROLLBACK;
~~~

Nếu ALTER TABLE thành công, cột migration_flag vẫn tồn tại sau ROLLBACK. Atomic DDL không thay đổi quy tắc này.

Ghi nhớ: **Atomic mô tả tính toàn vẹn của một thao tác DDL; ROLLBACK mô tả khả năng hoàn tác một transaction của người dùng.**

## 7. Phạm vi hỗ trợ Atomic DDL

MySQL 8.0 hỗ trợ Atomic DDL cho nhiều thao tác trên đối tượng InnoDB, bao gồm các thao tác thường gặp như:

- CREATE TABLE.
- ALTER TABLE.
- DROP TABLE.
- RENAME TABLE.
- TRUNCATE TABLE.
- CREATE INDEX.
- DROP INDEX.

Khả năng cụ thể phụ thuộc loại câu lệnh, storage engine và đối tượng. Không được suy luận rằng mọi DDL trong MySQL đều atomic chỉ vì server là MySQL 8.x.

### 7.1. Storage engine có vai trò quyết định

InnoDB hỗ trợ transaction và là nền tảng chính cho Atomic DDL trên bảng InnoDB. Các storage engine không có cùng cơ chế transaction/DDL recovery có thể không cung cấp cùng mức bảo đảm.

Ví dụ, không nên mặc định thao tác DDL trên bảng MyISAM có cùng khả năng atomic với InnoDB. Nếu hệ thống còn dùng nhiều engine, hãy lập danh sách bảng và engine trước khi đánh giá kế hoạch migration.

Kiểm tra engine:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
~~~

### 7.2. Temporary table không có cùng bảo đảm

CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE là ngoại lệ đối với implicit commit, nhưng thay đổi temporary table không rollback được. Không áp dụng các kết luận về Atomic DDL của bảng InnoDB thông thường cho temporary table.

### 7.3. Xác minh đúng phiên bản

~~~sql
SELECT VERSION();
~~~

Khi vận hành MySQL 5.7, MySQL 8.0, MySQL 8.4 hoặc dịch vụ tương thích MySQL, phải kiểm tra tài liệu của đúng phiên bản và nhà cung cấp. Cú pháp có thể giống nhau nhưng mức hỗ trợ atomic DDL hoặc hành vi của storage engine có thể khác.

## 8. Điều gì xảy ra khi DDL thất bại?

Có ba tình huống cần phân biệt:

### 8.1. DDL thất bại trước khi hoàn tất

Ví dụ ALTER TABLE không thể thêm unique index vì dữ liệu hiện tại có duplicate:

~~~sql
ALTER TABLE customer
    ADD UNIQUE KEY uq_customer_email (email);
~~~

Nếu có email trùng, MySQL từ chối tạo unique index. Với thao tác Atomic DDL được hỗ trợ, metadata và trạng thái bảng được phục hồi về trạng thái nhất quán trước thao tác. Dữ liệu cũ vẫn ở đó; lệnh ALTER không tạo ra một index nửa hoàn chỉnh.

### 8.2. DDL thành công

Nếu ALTER TABLE thành công, thay đổi schema đã hoàn tất. Một lệnh ROLLBACK sau đó không xóa index hoặc cột vừa tạo.

### 8.3. Client mất kết nối hoặc timeout khi DDL đang chạy

Nếu client timeout hoặc mất kết nối, không thể kết luận chỉ từ phía ứng dụng rằng DDL đã thất bại. Server có thể đã hoàn thành thao tác nhưng phản hồi không tới client.

Hãy kiểm tra trạng thái thật:

~~~sql
SHOW CREATE TABLE customer\G
~~~

Hoặc xem metadata:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer'
ORDER BY ORDINAL_POSITION;
~~~

Trước khi gửi lại DDL, xác minh cột/index đã tồn tại hay chưa. Nếu migration được retry mù quáng, ứng dụng có thể gặp lỗi “duplicate column name” hoặc “duplicate key name”.

Atomic DDL giúp trạng thái database nhất quán sau crash; nó không đảm bảo client luôn biết kết quả cuối cùng của request đã gửi.

## 9. TRUNCATE, DELETE và DROP có giới hạn rollback khác nhau

Ba câu lệnh có vẻ đều làm mất dữ liệu nhưng semantics rất khác nhau.

| Câu lệnh | Loại | Có thể rollback bằng transaction InnoDB? | Tác động |
|---|---|---|---|
| DELETE FROM table | DML | Có, trước COMMIT | Xóa các hàng thỏa điều kiện; có thể dùng WHERE |
| TRUNCATE TABLE table | DDL | Không | Xóa toàn bộ hàng, thường đặt lại AUTO_INCREMENT |
| DROP TABLE table | DDL | Không | Xóa cả cấu trúc và dữ liệu của bảng |

### 9.1. DELETE có thể rollback

~~~sql
START TRANSACTION;

DELETE FROM audit_log
WHERE created_at < '2024-01-01';

-- Kiểm tra kết quả trước khi quyết định.
ROLLBACK;
~~~

Với InnoDB, nếu chưa COMMIT, ROLLBACK có thể phục hồi các hàng đã xóa.

### 9.2. TRUNCATE gây implicit commit

~~~sql
START TRANSACTION;

INSERT INTO audit_log(message)
VALUES ('Trước truncate');

TRUNCATE TABLE staging_import;

ROLLBACK;
~~~

TRUNCATE gây implicit commit. INSERT trước đó được commit trước khi TRUNCATE thực thi; ROLLBACK không thể phục hồi staging_import.

TRUNCATE thường nhanh hơn DELETE không có WHERE vì không xóa từng hàng theo cách DML thông thường. Tuy nhiên, nó là thao tác DDL, có thể reset AUTO_INCREMENT và bị giới hạn khi bảng đang được tham chiếu bởi foreign key.

### 9.3. DROP TABLE không phải cách xóa dữ liệu có thể hoàn tác

~~~sql
DROP TABLE old_import;
~~~

DROP TABLE xóa đối tượng bảng. Với thao tác Atomic DDL được hỗ trợ, server bảo đảm tính toàn vẹn của thao tác khi phục hồi; nhưng sau khi DROP thành công, ROLLBACK không thể khôi phục bảng.

Muốn phục hồi cần backup, point-in-time recovery, bản sao hoặc quy trình tái tạo schema và dữ liệu.

## 10. SAVEPOINT không vượt qua được implicit commit

SAVEPOINT giúp quay lại một phần transaction DML:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT before_second_update;

UPDATE account
SET balance = balance + 20
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT before_second_update;

COMMIT;
~~~

Nhưng nếu chèn DDL:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT before_schema_change;

ALTER TABLE account
    ADD COLUMN remark VARCHAR(100) NULL;

ROLLBACK TO SAVEPOINT before_schema_change;
~~~

ALTER TABLE gây implicit commit. Transaction và savepoint trước đó không còn hiệu lực. ROLLBACK TO SAVEPOINT sẽ báo lỗi vì savepoint đã bị giải phóng hoặc không còn thuộc transaction hiện tại.

Không dùng SAVEPOINT để cố gắng biến DDL thành transactional.

## 11. DDL và metadata lock

Ngay cả khi DDL atomic, nó vẫn có thể phải chờ metadata lock (MDL).

Khi một transaction truy cập bảng, MySQL có thể giữ metadata lock trên bảng đến khi transaction kết thúc. DDL như ALTER TABLE cần metadata lock độc quyền ở một số giai đoạn. Nếu transaction khác đang giữ lock tương thích nhưng chưa kết thúc, ALTER TABLE có thể phải chờ.

Ví dụ:

**Connection A**

~~~sql
START TRANSACTION;

SELECT *
FROM account
WHERE account_id = 1;

-- Giữ transaction mở.
~~~

**Connection B**

~~~sql
ALTER TABLE account
    ADD COLUMN note VARCHAR(100) NULL;
~~~

Connection B có thể chờ metadata lock của Connection A. Nếu có nhiều truy vấn tiếp tục xếp hàng phía sau DDL đang chờ, độ trễ ứng dụng có thể tăng.

### 11.1. Cách giảm rủi ro metadata lock

- Tránh transaction dài hoặc transaction idle trong lúc migration.
- Kiểm tra connection đang giữ transaction trước khi chạy DDL.
- Thử migration trên bản sao có kích thước gần production.
- Chọn thời điểm ít tải nếu thao tác có thể cần lock mạnh.
- Đặt thời gian chờ phù hợp và theo dõi process list/metadata lock.
- Có kế hoạch hủy hoặc xử lý DDL chờ quá lâu theo quy trình vận hành.

Kiểm tra các transaction đang hoạt động:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Kiểm tra metadata lock nếu Performance Schema được bật:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, LOCK_STATUS;
~~~

Atomic DDL bảo vệ trạng thái sau lỗi/crash, không loại bỏ metadata lock hoặc bảo đảm ALTER TABLE luôn chạy không chặn.

## 12. Online DDL không đồng nghĩa transactional DDL

Một số thao tác ALTER TABLE hỗ trợ các thuật toán hoặc mức khóa khác nhau:

| Tùy chọn | Ý nghĩa khái quát |
|---|---|
| ALGORITHM=INSTANT | Thay đổi metadata tức thời cho các thao tác được hỗ trợ |
| ALGORITHM=INPLACE | Storage engine thực hiện thay đổi tại chỗ; có thể vẫn rebuild hoặc dùng tài nguyên đáng kể |
| ALGORITHM=COPY | Tạo/copy dữ liệu sang cấu trúc mới, thường tốn thời gian và I/O hơn |
| LOCK=NONE | Cho phép DML đồng thời trong các giai đoạn được hỗ trợ |
| LOCK=SHARED | Cho phép đọc nhưng hạn chế ghi trong phạm vi thao tác |
| LOCK=EXCLUSIVE | Yêu cầu khóa mạnh hơn, có thể chặn đọc và ghi |

Ví dụ yêu cầu một thay đổi chỉ được chạy nếu MySQL hỗ trợ thuật toán không khóa ghi:

~~~sql
ALTER TABLE account
    ADD COLUMN source_tag VARCHAR(30) NULL,
    ALGORITHM=INSTANT,
    LOCK=NONE;
~~~

Không phải mọi thay đổi đều hỗ trợ INSTANT hoặc LOCK=NONE. Nếu yêu cầu không được hỗ trợ, MySQL có thể trả lỗi thay vì âm thầm dùng thuật toán khác. Đây là cách hữu ích để tránh vô tình chạy một DDL nặng ngoài dự kiến.

### 12.1. Online không có nghĩa không có lock

Ngay cả online DDL vẫn cần metadata lock ở một số thời điểm, thường lúc bắt đầu và hoàn tất. Nó cũng có thể tạo tải I/O, CPU, redo/undo, dung lượng tạm và ảnh hưởng replication.

### 12.2. Atomic và online là hai trục độc lập

Một DDL có thể:
- Atomic nhưng cần lock mạnh.
- Online ở phần lớn thời gian nhưng vẫn cần metadata lock ngắn.
- Không thể chạy online với thuật toán mong muốn.
- Atomic ở cấp crash recovery nhưng không thể rollback sau khi hoàn thành.

Hãy đánh giá riêng:
1. Thao tác có atomic DDL không?
2. Nó gây implicit commit không?
3. Có hỗ trợ ALGORITHM/LOCK nào?
4. Có thể chặn truy vấn bao lâu?
5. Có đủ dung lượng tạm và tài nguyên không?

## 13. Vì sao ROLLBACK không khôi phục được DDL đã commit?

Một thao tác DDL thường làm thay đổi nhiều thành phần:
- Metadata của database.
- Định nghĩa cột, index, constraint.
- Cấu trúc vật lý của bảng và index.
- Các file/tablespace liên quan.
- Thông tin trong data dictionary và binary log.

Atomic DDL phối hợp các thành phần này để server không để lại trạng thái dở dang khi crash. Sau khi thao tác hoàn thành, nó được ghi nhận là thay đổi schema đã commit.

ROLLBACK của transaction người dùng chỉ hoàn tác các thay đổi transactional còn nằm trong transaction hiện tại. Nó không quay ngược một DDL đã hoàn tất và không tự khôi phục dữ liệu đã bị DROP hoặc TRUNCATE.

Ví dụ:

~~~sql
ALTER TABLE customer
    DROP COLUMN legacy_secret;
~~~

Sau khi câu lệnh thành công, legacy_secret và dữ liệu trong cột bị loại bỏ. ROLLBACK không thể tái tạo nội dung cột. Muốn phục hồi cần nguồn dữ liệu khác như backup, binlog hoặc bản sao.

Vì vậy, trước DDL phá hủy dữ liệu, cần xác nhận:
- Cột/bảng có còn được ứng dụng sử dụng không.
- Dữ liệu cần lưu trữ hoặc chuyển đổi trước khi xóa không.
- Backup có thể restore và đã được kiểm chứng không.
- Có thể triển khai theo nhiều bước expand-and-contract không.

## 14. Thiết kế migration an toàn với DDL

Không thể dựa vào một transaction để bao trọn DDL, vì vậy migration cần được tổ chức theo từng bước có thể quan sát và phục hồi.

### 14.1. Giai đoạn chuẩn bị

1. Xác định schema hiện tại và schema đích.
2. Kiểm tra phiên bản MySQL, storage engine và khả năng Atomic DDL.
3. Kiểm tra duplicate, NULL, foreign key và dữ liệu không hợp lệ.
4. Ước lượng thời gian, dung lượng và tác động lock.
5. Backup và kiểm thử restore.
6. Chạy thử migration trên môi trường gần production.
7. Xác định điều kiện dừng, retry và phương án phục hồi.

### 14.2. Giai đoạn triển khai

- Dừng hoặc điều phối các migration chạy đồng thời.
- Kiểm tra transaction dài và metadata lock.
- Chạy từng DDL độc lập.
- Xác minh trạng thái schema sau mỗi bước.
- Thực hiện backfill bằng DML theo batch nếu cần.
- Theo dõi lỗi, replication lag và tải hệ thống.
- Chỉ chuyển ứng dụng sang dùng cấu trúc mới sau khi xác minh.

### 14.3. Expand-and-contract

Khi thay đổi lớn có nguy cơ ảnh hưởng ứng dụng, có thể triển khai nhiều phiên bản tương thích:

**Expand**
- Thêm cột hoặc bảng mới.
- Giữ cấu trúc cũ để phiên bản ứng dụng hiện tại vẫn hoạt động.
- Backfill dữ liệu từ cũ sang mới theo batch.

**Migrate**
- Ứng dụng ghi đồng thời hoặc chuyển dần sang cấu trúc mới.
- So sánh dữ liệu giữa hai cấu trúc.
- Chuyển truy vấn đọc sang cột/bảng mới.

**Contract**
- Sau khi xác nhận không còn phiên bản ứng dụng phụ thuộc cấu trúc cũ, mới xóa cột hoặc bảng cũ trong một migration riêng.

Mỗi DDL vẫn là ranh giới commit riêng. Ưu điểm của quy trình là có thời gian kiểm chứng và chuyển đổi, không phải khả năng rollback DDL.

## 15. Rollback migration và forward fix

Vì DDL đã commit không thể được ROLLBACK như DML, khái niệm rollback migration thường là chạy một migration mới để đưa schema về cấu trúc gần trước đó.

Ví dụ:
- Migration A thêm cột status.
- Migration B đổi tên cột.
- Migration C xóa cột cũ.

Nếu B có vấn đề, có thể viết migration mới đổi tên ngược lại nếu dữ liệu và ứng dụng cho phép. Nhưng nếu C đã xóa dữ liệu, việc tạo lại cột không tự khôi phục giá trị cũ.

### 15.1. Reverse migration không luôn mất dữ liệu

Một số thay đổi có thể đảo ngược tương đối an toàn:
- Thêm index rồi xóa index.
- Thêm cột nullable rồi xóa cột nếu chưa có dữ liệu quan trọng.
- Thêm constraint rồi gỡ constraint.

Một số thay đổi có thể mất dữ liệu:
- DROP COLUMN.
- DROP TABLE.
- TRUNCATE TABLE.
- Thu hẹp kiểu dữ liệu làm mất độ chính xác hoặc cắt giá trị.
- Chuyển đổi charset/collation làm thay đổi dữ liệu hoặc gây xung đột.

### 15.2. Forward fix

Trong môi trường production, đôi khi cách an toàn hơn là sửa tiếp schema bằng migration mới:
- Giữ dữ liệu đã được ghi.
- Sửa định nghĩa cột/index/constraint.
- Cập nhật ứng dụng theo phiên bản tương thích.
- Tránh restore toàn bộ database nếu chỉ có một thay đổi schema sai và dữ liệu mới vẫn hợp lệ.

Quyết định rollback hay forward fix phụ thuộc vào việc dữ liệu đã bị thay đổi/mất hay chưa và khả năng khôi phục.

## 16. Ví dụ thực hành: DML trước DDL và ROLLBACK

Tạo bảng:

~~~sql
CREATE TABLE transaction_demo (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    amount DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO transaction_demo (id, amount)
VALUES (1, 100.00), (2, 200.00);
~~~

Thực hiện:

~~~sql
START TRANSACTION;

UPDATE transaction_demo
SET amount = amount + 10
WHERE id = 1;

ALTER TABLE transaction_demo
    ADD COLUMN note VARCHAR(100) NULL;

UPDATE transaction_demo
SET amount = amount + 20
WHERE id = 2;

ROLLBACK;
~~~

Kiểm tra:

~~~sql
SELECT *
FROM transaction_demo
ORDER BY id;

SHOW CREATE TABLE transaction_demo\G
~~~

Kết quả mong đợi:
- Hàng id = 1 có amount = 110.00 vì UPDATE đầu đã được commit ngầm trước ALTER.
- Cột note vẫn tồn tại vì ALTER đã hoàn tất.
- Hàng id = 2 vẫn có amount = 200.00 vì UPDATE sau ALTER thuộc transaction mới và bị ROLLBACK.

Thực hành này minh họa trực tiếp rằng implicit commit chia một chuỗi lệnh thành nhiều transaction độc lập.

## 17. Ví dụ thực hành: Temporary table và ROLLBACK

~~~sql
START TRANSACTION;

INSERT INTO transaction_demo (id, amount)
VALUES (3, 300.00);

CREATE TEMPORARY TABLE temp_ids (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY
);

INSERT INTO temp_ids (id)
VALUES (1), (2);

ROLLBACK;
~~~

Sau ROLLBACK:
- Hàng id = 3 trong transaction_demo không tồn tại.
- Temporary table temp_ids vẫn tồn tại trong session.
- Dữ liệu đã INSERT vào temp_ids cũng không được hoàn tác như một thay đổi schema transactional; các thao tác DML trên temporary table cần được xem xét theo engine và transaction đang dùng.

Để xóa temporary table:

~~~sql
DROP TEMPORARY TABLE temp_ids;
~~~

DROP TEMPORARY TABLE không gây implicit commit nhưng bản thân thao tác drop không được rollback.

## 18. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| UPDATE trước ALTER bị ROLLBACK nhưng dữ liệu vẫn còn | ALTER TABLE đã implicit commit transaction trước đó | Tách DDL khỏi transaction DML |
| ROLLBACK không xóa cột vừa thêm | DDL đã hoàn tất và commit | Dùng migration ngược hoặc forward fix |
| Nghĩ Atomic DDL là transactional DDL | Nhầm crash atomicity với rollback người dùng | Phân biệt hai khái niệm |
| Nghĩ mọi DDL đều atomic | Atomic DDL chỉ áp dụng cho thao tác/engine được hỗ trợ | Kiểm tra manual và storage engine |
| Temporary table vẫn tồn tại sau ROLLBACK | CREATE/DROP TEMPORARY TABLE không commit nhưng không rollback | Quản lý vòng đời temporary table riêng |
| TRUNCATE không phục hồi được | TRUNCATE là DDL, gây implicit commit | Dùng DELETE trong transaction nếu cần rollback |
| DDL chờ rất lâu | Metadata lock từ transaction khác | Tìm transaction giữ lock, rút ngắn transaction |
| Online DDL vẫn gây chặn | Online không loại bỏ metadata lock | Kiểm tra LOCK/ALGORITHM và MDL |
| Client timeout nhưng schema đã đổi | Server có thể hoàn tất trước khi phản hồi mất | Đọc lại SHOW CREATE TABLE trước retry |
| Migration rollback tạo cột nhưng không có dữ liệu | DDL đảo ngược không phục hồi dữ liệu đã DROP | Backup, binlog, expand-and-contract |
| START TRANSACTION thứ hai làm mất savepoint | MySQL không hỗ trợ nested transaction | Dùng SAVEPOINT trong cùng transaction |
| AUTO_INCREMENT bị reset sau TRUNCATE | TRUNCATE có thể đặt lại bộ đếm | Không dùng TRUNCATE nếu cần giữ sequence |

## 19. Quy trình kiểm tra trước và sau DDL

### Trước khi chạy

~~~sql
SELECT VERSION();

SHOW CREATE TABLE account\G

SELECT
    TABLE_NAME,
    ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'account';
~~~

Tiếp theo:
- Kiểm tra dữ liệu có vi phạm constraint mới không.
- Kiểm tra transaction dài và metadata lock.
- Ước lượng dung lượng và thời gian.
- Xác minh backup/restore.
- Chọn ALGORITHM và LOCK nếu thao tác hỗ trợ.

### Sau khi chạy

~~~sql
SHOW CREATE TABLE account\G

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'account'
ORDER BY ORDINAL_POSITION;
~~~

Nếu thêm index:

~~~sql
SHOW INDEX FROM account;
~~~

Nếu thay đổi constraint:

~~~sql
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM information_schema.table_constraints
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'account';
~~~

Đối chiếu schema thực tế với migration mong đợi trước khi cho ứng dụng sử dụng.

## 20. Checklist vận hành Atomic DDL và implicit commit

- [ ] Đã phân biệt DDL với DML.
- [ ] Đã biết câu lệnh nào gây implicit commit.
- [ ] Đã kiểm tra transaction có đang hoạt động trước khi chạy DDL.
- [ ] Đã hiểu DDL thành công không thể được ROLLBACK như DML.
- [ ] Đã phân biệt Atomic DDL với transactional DDL.
- [ ] Đã xác minh phiên bản MySQL và storage engine.
- [ ] Đã kiểm tra thao tác cụ thể có hỗ trợ Atomic DDL không.
- [ ] Đã biết ngoại lệ CREATE/DROP TEMPORARY TABLE.
- [ ] Đã phân biệt DELETE, TRUNCATE và DROP.
- [ ] Đã kiểm tra metadata lock và transaction dài.
- [ ] Đã đánh giá ALGORITHM và LOCK cho Online DDL.
- [ ] Đã có backup và kiểm thử restore.
- [ ] Đã thử migration trên dữ liệu đại diện.
- [ ] Đã xác minh trạng thái schema sau DDL.
- [ ] Đã chuẩn bị reverse migration hoặc forward fix.
- [ ] Đã tránh retry mù quáng khi client timeout.
- [ ] Đã có quy trình xử lý replication lag, lock timeout và deadlock nếu migration liên quan.

## 21. Bài tập thực hành

### Bài 1: Quan sát implicit commit

Tạo bảng demo, START TRANSACTION, INSERT một hàng, sau đó ALTER TABLE thêm cột và chạy ROLLBACK. Kiểm tra hàng INSERT và schema. Giải thích phần nào đã commit.

### Bài 2: DDL và SAVEPOINT

Tạo transaction, UPDATE một hàng, đặt SAVEPOINT, chạy ALTER TABLE rồi thử ROLLBACK TO SAVEPOINT. Ghi lại lỗi và giải thích vì sao savepoint không còn hiệu lực.

### Bài 3: Temporary table

Trong transaction, INSERT vào bảng InnoDB và CREATE TEMPORARY TABLE. Chạy ROLLBACK, sau đó kiểm tra hàng InnoDB và temporary table. Giải thích ngoại lệ implicit commit nhưng không rollback của temporary table.

### Bài 4: DELETE so với TRUNCATE

Tạo hai bảng InnoDB có dữ liệu. Chạy DELETE trong transaction rồi ROLLBACK. Chạy TRUNCATE trong transaction khác rồi ROLLBACK. So sánh kết quả và AUTO_INCREMENT.

### Bài 5: Atomic DDL khi lỗi constraint

Tạo bảng có dữ liệu trùng, thử ALTER TABLE thêm UNIQUE index. Xác minh lệnh thất bại và schema vẫn nhất quán. Xử lý duplicate rồi chạy lại.

### Bài 6: Metadata lock

Mở hai connection. Connection A bắt đầu transaction và đọc một bảng nhưng chưa commit. Connection B chạy ALTER TABLE trên bảng đó. Quan sát thời gian chờ và metadata_locks. Commit Connection A rồi xem DDL tiếp tục.

### Bài 7: Online DDL

Thử thêm cột bằng ALGORITHM=INSTANT trên phiên bản hỗ trợ. Sau đó thử một thay đổi không hỗ trợ INSTANT và ghi nhận lỗi. Giải thích vì sao cần kiểm tra thuật toán trước production.

### Bài 8: Client timeout

Trên môi trường lab, mô phỏng client mất kết nối trong khi DDL chạy. Kết nối lại, dùng SHOW CREATE TABLE và INFORMATION_SCHEMA để xác định trạng thái trước khi quyết định retry.

### Bài 9: Expand-and-contract

Thiết kế migration đổi tên cột email thành contact_email mà không làm phiên bản ứng dụng cũ ngừng hoạt động ngay lập tức. Chia thành các bước thêm cột, backfill, dual-write, chuyển đọc và xóa cột cũ.

## 22. Kết luận

DDL trong MySQL thường gây implicit commit, vì vậy không thể gom CREATE, ALTER, DROP hoặc TRUNCATE vào một transaction rồi dùng ROLLBACK để hoàn tác. DML trên InnoDB có thể rollback khi transaction chưa commit; DDL đã hoàn tất thì không.

Atomic DDL từ MySQL 8.0 bảo đảm một số thao tác DDL được hoàn tất hoặc phục hồi về trạng thái nhất quán khi server gặp lỗi/crash. Nó không biến DDL thành transactional DDL. Khi thiết kế migration, hãy xác minh engine và phiên bản, hiểu implicit commit, kiểm tra metadata lock, đánh giá online DDL, backup và chuẩn bị reverse migration hoặc forward fix. Đặc biệt, khi client timeout, hãy đọc lại schema thực tế trước khi chạy lại câu lệnh.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual – Atomic Data Definition Statement Support](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)
- [MySQL 8.4 Reference Manual – Atomic DDL](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)
- [MySQL 8.4 Reference Manual – InnoDB and Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html)
- [MySQL 8.4 Reference Manual – Online DDL Performance and Concurrency](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-performance.html)
- [MySQL 8.4 Reference Manual – Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual – InnoDB and Transaction Management](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual – TRUNCATE TABLE](https://dev.mysql.com/doc/refman/8.4/en/truncate-table.html)
- [MySQL 8.4 Reference Manual – CREATE TEMPORARY TABLE](https://dev.mysql.com/doc/refman/8.4/en/create-temporary-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Recovery](https://dev.mysql.com/doc/refman/8.4/en/innodb-recovery.html)

