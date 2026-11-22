# Kiểm thử giao dịch, rollback, autocommit và implicit commit của DDL

Kiểm thử transaction MySQL cần chứng minh dữ liệu được commit hoặc rollback đúng thời điểm, nhiều session nhìn thấy dữ liệu theo isolation level dự kiến, và câu lệnh DDL không làm thay đổi ranh giới transaction ngoài dự tính. Một lỗi phổ biến là viết test với giả định mọi câu SQL trong `START TRANSACTION` đều có thể rollback. Trong MySQL, nhiều câu DDL gây **implicit commit**, vì vậy `ROLLBACK` sau DDL không thể hoàn tác các thay đổi đã commit trước đó hoặc hoàn tác chính DDL.

Bài học này giải thích cách kiểm thử InnoDB transaction, autocommit, savepoint, lỗi statement, DDL implicit commit và khác biệt giữa atomic DDL với rollback transaction. Nội dung thuộc module `DATABASE_MYSQL`, kết nối thiết kế bảng, SQL, kiểm soát đồng thời và kiểm thử ứng dụng dùng MySQL.

Sau bài học, bạn có thể:

- Thiết kế kịch bản kiểm thử commit và rollback bằng nhiều session.
- Phân biệt autocommit với transaction tường minh.
- Kiểm tra savepoint và phạm vi rollback một phần.
- Hiểu vì sao lỗi statement không phải lúc nào cũng rollback toàn transaction.
- Nhận biết các câu lệnh DDL gây implicit commit.
- Phân biệt atomic DDL với khả năng rollback bằng `ROLLBACK`.
- Viết test JDBC/Spring an toàn, tránh để DDL phá vỡ test transaction.
- Xác minh kết quả trên InnoDB thay vì suy luận từ H2 hoặc mock.

## 1. Transaction bảo đảm điều gì?

Transaction gom nhiều thao tác dữ liệu thành một đơn vị công việc. Với InnoDB, các thay đổi DML trong một transaction có thể được commit cùng nhau hoặc rollback nếu transaction bị hủy. Điều này giúp duy trì các bất biến nghiệp vụ như:

- Trừ tiền tài khoản A và cộng tiền tài khoản B phải cùng thành công hoặc cùng thất bại.
- Tạo đơn hàng và các dòng chi tiết phải được ghi nhận nhất quán.
- Giảm tồn kho và ghi nhận giao dịch xuất kho phải thuộc cùng một đơn vị công việc.

ACID mô tả các thuộc tính chính:

| Thuộc tính | Ý nghĩa trong kiểm thử |
|---|---|
| Atomicity | Các thay đổi thuộc transaction được commit cùng nhau hoặc bị rollback theo quy tắc engine |
| Consistency | Ràng buộc và bất biến dữ liệu được duy trì trước và sau transaction |
| Isolation | Các transaction đồng thời không nhìn thấy hoặc can thiệp dữ liệu ngoài mức isolation cho phép |
| Durability | Sau commit thành công, thay đổi được lưu bền vững theo cấu hình MySQL và hạ tầng |

Trong MySQL, khả năng rollback phụ thuộc storage engine. InnoDB hỗ trợ transaction; các engine không hỗ trợ transaction như MyISAM không thể rollback DML theo cách của InnoDB. Vì vậy, trước khi viết test transaction, hãy xác nhận bảng sử dụng InnoDB.

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts', 'orders', 'order_items');
```

## 2. Chuẩn bị schema kiểm thử cô lập

Không chạy kịch bản rollback hoặc DDL thử nghiệm trên bảng production. Dùng schema riêng, database tạm trong CI hoặc MySQL container dành cho test. Chuẩn bị bảng trước khi mở transaction để tránh DDL làm commit test ngoài ý muốn.

Ví dụ tạo bảng thử nghiệm:

```sql
CREATE DATABASE IF NOT EXISTS mysql_tx_lab;
USE mysql_tx_lab;

CREATE TABLE account_probe (
    account_id BIGINT NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_account_probe_balance CHECK (balance >= 0)
) ENGINE=InnoDB;

CREATE TABLE ddl_probe (
    probe_id BIGINT NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (probe_id)
) ENGINE=InnoDB;

INSERT INTO account_probe (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);
```

Các câu `CREATE DATABASE`, `CREATE TABLE` và `INSERT` khởi tạo này chạy ngoài kịch bản transaction cần kiểm tra. Tạo dữ liệu nền trước, rồi mới mở session kiểm thử. Nếu dùng database CI mới cho từng test suite, việc tạo và xóa database có thể được quản lý ở bước setup/teardown riêng.

## 3. Autocommit mặc định

MySQL thường bật `autocommit` mặc định (`@@autocommit = 1`). Khi không có transaction tường minh, mỗi statement thành công được thực hiện như một transaction riêng và tự commit.

Kiểm tra:

```sql
SELECT @@SESSION.autocommit;
```

Với autocommit bật:

```sql
INSERT INTO account_probe (account_id, balance)
VALUES (3, 250.00);

ROLLBACK;
```

`INSERT` đã được commit khi statement kết thúc. `ROLLBACK` sau đó không xóa hàng vừa thêm vì không còn transaction chưa commit để hoàn tác.

Kiểm tra từ session khác:

```sql
SELECT account_id, balance
FROM account_probe
WHERE account_id = 3;
```

Hàng có thể được đọc ngay sau khi statement đầu tiên hoàn tất. Đây là test cơ bản để xác nhận autocommit đang bật và mỗi DML độc lập được commit.

### 3.1. Tắt autocommit trong một session

```sql
SET SESSION autocommit = 0;

INSERT INTO account_probe (account_id, balance)
VALUES (4, 300.00);
```

Session hiện tại thấy hàng mới, nhưng session khác không thấy thay đổi chưa commit theo isolation thông thường. Sau đó:

```sql
ROLLBACK;
```

Hàng `account_id = 4` bị hủy. Xác nhận từ session khác:

```sql
SELECT COUNT(*)
FROM account_probe
WHERE account_id = 4;
```

Kết quả mong đợi là `0`.

Khi `autocommit=0`, session luôn làm việc trong chế độ transaction tường minh ngầm: sau `COMMIT` hoặc `ROLLBACK`, transaction hiện tại kết thúc và các statement tiếp theo lại bắt đầu một transaction mới. Hãy kết thúc transaction khi test xong và khôi phục cấu hình session nếu connection được tái sử dụng.

### 3.2. Bật lại autocommit có thể commit transaction đang mở

Nếu session đang ở `autocommit=0` và có thay đổi chưa commit, chuyển `autocommit` từ `0` sang `1` sẽ commit transaction hiện tại. Vì vậy, không dùng `SET autocommit = 1` như một thao tác cleanup vô hại khi test đang chờ xác minh rollback.

```sql
SET SESSION autocommit = 0;
INSERT INTO account_probe (account_id, balance)
VALUES (5, 400.00);

-- Lệnh này commit transaction hiện tại.
SET SESSION autocommit = 1;
```

Sau khi chạy lệnh cuối, hàng `5` đã được commit. Nếu muốn hủy thay đổi, phải `ROLLBACK` trước khi bật lại autocommit.

## 4. Transaction tường minh với START TRANSACTION

Với autocommit bật, ứng dụng có thể mở một transaction tường minh:

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE account_probe
SET balance = balance + 100.00
WHERE account_id = 2;

COMMIT;
```

Hai UPDATE thuộc cùng transaction InnoDB. Nếu cả hai thành công và `COMMIT` thành công, thay đổi của cả hai hàng trở nên visible cho transaction khác theo isolation. Nếu thay `COMMIT` bằng `ROLLBACK`, cả hai thay đổi được hoàn tác.

### 4.1. Kiểm tra rollback bằng hai session

Mở hai kết nối độc lập, gọi là Session A và Session B. Đảm bảo mỗi session có autocommit bật và dùng InnoDB.

Session A:

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 50.00
WHERE account_id = 1;

SELECT balance
FROM account_probe
WHERE account_id = 1;
```

Session A nhìn thấy số dư đã thay đổi bên trong transaction. Trước khi A commit, chạy ở Session B:

```sql
SELECT balance
FROM account_probe
WHERE account_id = 1;
```

Session B vẫn nhìn thấy giá trị đã commit trước đó. Sau đó ở Session A:

```sql
ROLLBACK;
```

Đọc lại từ Session B. Giá trị phải giữ nguyên như trước transaction. Kịch bản này kiểm tra cả khả năng rollback và việc transaction khác không nhìn thấy thay đổi chưa commit.

Để tránh nhầm lẫn do snapshot `REPEATABLE READ` đã được tạo ở Session B trước khi A commit, hãy dùng transaction mới ở B hoặc kết thúc transaction đọc cũ rồi đọc lại. Với bài test visibility đơn giản, có thể đặt `READ COMMITTED` cho Session B trước khi bắt đầu transaction.

### 4.2. `START TRANSACTION` khi transaction cũ chưa kết thúc

Trong MySQL, bắt đầu transaction mới bằng `START TRANSACTION` hoặc `BEGIN` sẽ kết thúc transaction đang hoạt động trước đó bằng implicit commit. Không dùng `START TRANSACTION` lồng nhau để tạo nested transaction.

Nếu cần rollback một phần công việc, dùng `SAVEPOINT` thay vì mở transaction mới bên trong transaction hiện tại.

## 5. Savepoint và rollback một phần

Savepoint đánh dấu một vị trí trong transaction. Ứng dụng có thể rollback về điểm đó mà vẫn giữ các thay đổi trước savepoint.

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 100.00
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account_probe
SET balance = balance + 100.00
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

COMMIT;
```

Sau khi commit:

- Thao tác trừ 100 ở account 1 được giữ.
- Thao tác cộng 100 ở account 2 bị rollback về savepoint.

`ROLLBACK TO SAVEPOINT` không kết thúc transaction. `RELEASE SAVEPOINT` xóa savepoint khi không cần nữa. Savepoint bị loại bỏ khi transaction kết thúc.

DDL gây implicit commit sẽ làm mất khả năng dùng savepoint để rollback xuyên qua ranh giới đó. Vì vậy, không trộn DDL vào kịch bản savepoint nếu mục tiêu là kiểm tra rollback DML.

## 6. Lỗi statement và rollback toàn transaction

Một câu SQL lỗi không phải lúc nào cũng làm toàn bộ transaction rollback. Với InnoDB, nhiều lỗi như duplicate key chỉ làm statement đó thất bại; các statement trước trong transaction vẫn còn hiệu lực và transaction có thể tiếp tục nếu ứng dụng quyết định.

Ví dụ:

```sql
START TRANSACTION;

UPDATE account_probe
SET balance = balance - 25.00
WHERE account_id = 1;

-- Lỗi duplicate primary key; chỉ statement này thất bại.
INSERT INTO account_probe (account_id, balance)
VALUES (1, 999.00);

-- Nếu session tiếp tục và commit, UPDATE đầu vẫn được commit.
COMMIT;
```

Trong test, kiểm tra rõ kết quả từng statement và trạng thái transaction. Ứng dụng có thể chủ động rollback toàn transaction khi bất kỳ bước nghiệp vụ nào thất bại, nhưng không nên giả định MySQL tự làm điều đó cho mọi lỗi.

### 6.1. Deadlock khác lock wait timeout

- Khi InnoDB phát hiện deadlock, nó chọn một transaction làm victim và rollback toàn bộ transaction đó. Ứng dụng thường cần retry toàn bộ transaction theo chính sách có giới hạn.
- Khi chờ khóa vượt `innodb_lock_wait_timeout`, mặc định InnoDB thường rollback statement đang chờ, không nhất thiết rollback toàn transaction. Biến `innodb_rollback_on_timeout` có thể thay đổi hành vi để rollback toàn transaction.

Đây là khác biệt quan trọng khi viết test lỗi. Không viết test giả định lock wait timeout và deadlock có cùng phạm vi rollback. Hãy kiểm tra cấu hình server thực tế và đọc trạng thái transaction sau lỗi.

## 7. DDL gây implicit commit

Nhiều câu DDL trong MySQL gây implicit commit. Nhóm thường gặp gồm:

- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`.
- `CREATE INDEX`, `DROP INDEX`.
- `TRUNCATE TABLE`.
- `RENAME TABLE`.
- Nhiều câu lệnh tạo hoặc xóa database, view, routine, trigger và event.
- `CREATE USER`, `ALTER USER`, `DROP USER` và nhiều câu lệnh quản trị quyền.

Phần lớn các câu lệnh này commit transaction đang hoạt động trước khi thực thi; nhiều câu còn kết thúc bằng commit sau khi thực thi. Danh sách đầy đủ phụ thuộc loại câu lệnh và phiên bản, vì vậy cần tra tài liệu MySQL cho từng statement.

### 7.1. Thử nghiệm DDL làm commit DML trước đó

Chuẩn bị bảng `ddl_probe` trước khi bắt đầu:

```sql
START TRANSACTION;

INSERT INTO ddl_probe (probe_id, note)
VALUES (1, 'insert before alter');

ALTER TABLE ddl_probe
    ADD COLUMN category VARCHAR(30) NULL;

ROLLBACK;
```

Kết quả cần xác minh:

- `INSERT` được commit ngầm trước khi `ALTER TABLE` chạy.
- `ALTER TABLE` thực hiện như một thao tác DDL riêng và không thể bị `ROLLBACK` bằng lệnh cuối.
- Sau `ROLLBACK`, hàng `probe_id = 1` vẫn tồn tại và cột `category` vẫn tồn tại.

Kiểm tra:

```sql
SELECT *
FROM ddl_probe
WHERE probe_id = 1;

SHOW CREATE TABLE ddl_probe\G
```

Kịch bản này chứng minh `ROLLBACK` cuối không thể đảo ngược DDL và cũng không thể hoàn tác DML đã bị commit bởi implicit commit trước DDL.

### 7.2. `TRUNCATE TABLE` không giống `DELETE`

`DELETE FROM table_name` là DML và có thể rollback nếu bảng dùng InnoDB, transaction chưa commit và không có ranh giới implicit commit chen vào.

`TRUNCATE TABLE` là DDL trong MySQL và gây implicit commit. Không dùng `TRUNCATE` trong một transaction với kỳ vọng có thể rollback để phục hồi các hàng đã xóa.

Ví dụ kiểm thử an toàn trên bảng tạm:

```sql
START TRANSACTION;
DELETE FROM ddl_probe WHERE probe_id = 1;
ROLLBACK;
```

Hàng được khôi phục. Nếu thay `DELETE` bằng `TRUNCATE TABLE ddl_probe`, thao tác truncate sẽ commit theo quy tắc DDL và không thể hoàn tác bằng `ROLLBACK`.

### 7.3. Ngoại lệ với TEMPORARY TABLE

`CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` là ngoại lệ: chúng không gây implicit commit theo cách của các câu tạo/xóa bảng thông thường. Tuy nhiên, hiệu ứng tạo hoặc xóa temporary table bản thân nó không thể rollback. Ngoại lệ này không có nghĩa mọi DDL trên temporary table đều an toàn trong transaction; các thao tác như `ALTER TABLE` vẫn cần được xem xét theo quy tắc implicit commit tương ứng.

## 8. Atomic DDL không có nghĩa rollback được DDL

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác được hỗ trợ. Atomic DDL giúp một câu DDL được xử lý nguyên tử trước các sự cố như server crash: sau khi phục hồi, metadata và thay đổi storage engine tương ứng ở trạng thái hoàn tất hoặc không hoàn tất theo hỗ trợ của thao tác đó.

Atomic DDL khác với transactional DDL:

| Khái niệm | Điều bảo đảm | Có thể `ROLLBACK` bằng transaction ứng dụng? |
|---|---|---|
| Transactional DML của InnoDB | Nhiều thay đổi dữ liệu có thể commit/rollback cùng nhau | Có, trước commit |
| Atomic DDL | Một DDL được bảo vệ nguyên tử trước crash trong phạm vi hỗ trợ | Không |
| Implicit commit | Kết thúc transaction hiện tại tại ranh giới của statement | Không thể rollback qua ranh giới đã commit |

Ví dụ, `ALTER TABLE` có thể là atomic DDL trong MySQL 8.0 nhưng vẫn gây implicit commit. Nếu `ALTER TABLE` thành công, một `ROLLBACK` sau đó không đưa schema về trạng thái trước ALTER.

Không phải mọi câu DDL, engine hoặc thao tác đều có cùng mức atomic DDL. Hãy kiểm tra tài liệu theo phiên bản và câu lệnh cụ thể.

## 9. Các câu lệnh khác có thể thay đổi ranh giới transaction

Ngoài DDL, cần chú ý một số thao tác:

- `SET autocommit = 1` khi chuyển từ `0` sang `1` commit transaction hiện tại.
- `START TRANSACTION`/`BEGIN` khi đã có transaction đang hoạt động kết thúc transaction trước đó.
- `LOCK TABLES` có thể gây implicit commit; `UNLOCK TABLES` có hành vi phụ thuộc loại lock được giữ.
- Nhiều câu lệnh quản trị account/privilege hoặc thao tác hệ thống có implicit commit.
- Một số statement không được phép hoặc có hành vi đặc biệt trong stored program.

Trước khi thêm statement vào một transaction nghiệp vụ, tra danh sách implicit commit trong tài liệu MySQL. Đừng giả định cú pháp chạy được bên trong `START TRANSACTION` đồng nghĩa với việc nó tham gia transaction đó.

## 10. Kiểm thử bằng JDBC

JDBC cung cấp `Connection.setAutoCommit(false)`, `commit()` và `rollback()` để quản lý transaction. Ví dụ:

```java
String sql = "UPDATE account_probe "
           + "SET balance = balance - ? WHERE account_id = ?";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setBigDecimal(1, new BigDecimal("25.00"));
        statement.setLong(2, 1L);
        int updated = statement.executeUpdate();

        if (updated != 1) {
            throw new IllegalStateException("Không tìm thấy account cần cập nhật");
        }

        connection.commit();
    } catch (Exception exception) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            exception.addSuppressed(rollbackFailure);
        }
        throw exception;
    }
}
```

Khi `setAutoCommit(false)`, JDBC connection không tự commit từng statement. Sau khi commit hoặc rollback, ứng dụng cần quản lý transaction tiếp theo rõ ràng. Khi đổi autocommit về `true`, JDBC có thể commit transaction hiện tại theo hợp đồng JDBC; không thực hiện việc này trước khi xác nhận rollback/commit đã hoàn tất.

### 10.1. DDL qua JDBC vẫn có implicit commit

Việc gọi DDL qua `Statement.execute()` không làm DDL trở thành transactional. Ví dụ:

```java
connection.setAutoCommit(false);

try (Statement statement = connection.createStatement()) {
    statement.executeUpdate(
        "INSERT INTO ddl_probe (probe_id, note) VALUES (10, 'before ddl')"
    );

    statement.execute("ALTER TABLE ddl_probe ADD COLUMN source_tag VARCHAR(20)");

    connection.rollback();
}
```

Sau khi DDL thành công, transaction trước đó đã bị implicit commit theo quy tắc MySQL. `connection.rollback()` không xóa hàng `probe_id = 10` và không loại bỏ cột `source_tag`. Đây là lý do setup schema và test DML rollback nên được tách thành hai giai đoạn.

## 11. Kiểm thử với Spring và JPA

Spring TestContext có thể mở test-managed transaction cho test method được đánh dấu `@Transactional`. Mặc định, transaction test được rollback sau khi test hoàn tất, trừ khi cấu hình `@Commit`, `@Rollback(false)` hoặc điều khiển bằng API test transaction.

Ví dụ:

```java
@SpringBootTest
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void updateIsRolledBackAfterTest() {
        Account account = accountRepository.findById(1L).orElseThrow();
        account.setBalance(new BigDecimal("900.00"));

        entityManager.flush();

        Account reloaded = entityManager.find(Account.class, 1L);
        assertEquals(new BigDecimal("900.00"), reloaded.getBalance());
    }
}
```

Test transaction được rollback khi kết thúc test theo cấu hình mặc định. `flush()` giúp gửi SQL xuống database để phát hiện lỗi constraint và kiểm tra hành vi database; nó không commit transaction. `find()` ở cùng persistence context có thể trả entity đang được quản lý, vì vậy nếu cần kiểm tra dữ liệu đọc lại từ database, có thể gọi `entityManager.clear()` trước khi reload.

### 11.1. Không chạy DDL trong test transaction cần rollback

Nếu test gọi `ALTER TABLE`, `CREATE TABLE` hoặc `TRUNCATE TABLE` bên trong test-managed transaction, implicit commit của MySQL có thể commit dữ liệu test trước đó. Khi test kết thúc, Spring cố rollback transaction nhưng các thay đổi đã commit vẫn tồn tại.

Vì vậy:

- Tạo schema và bảng bằng migration/setup trước khi test transaction bắt đầu.
- Giữ test rollback chỉ cho DML transactional trên InnoDB.
- Dùng database/schema riêng cho mỗi suite hoặc container để cô lập DDL.
- Nếu test cần kiểm tra DDL, chạy test đó riêng và tự dọn dẹp bằng teardown có kiểm soát.
- Không dựa vào `@Transactional` của test để tự động dọn mọi thay đổi schema.

### 11.2. Test qua nhiều connection

Một test có thể dùng hai connection độc lập để xác minh visibility, locking và commit. Đảm bảo chúng không vô tình tham gia cùng một transaction Spring hoặc dùng chung connection được bind vào thread.

Nếu dùng `JdbcTemplate` trong test có transaction Spring, nó thường lấy connection gắn với transaction hiện tại. Để kiểm tra hành vi giữa hai session, cần tạo hai transaction/connection thực sự độc lập và điều khiển commit/rollback rõ ràng.

## 12. Kiểm thử rollback với isolation và visibility

Khi xác minh dữ liệu giữa hai session, isolation level ảnh hưởng tới kết quả đọc. Một session B ở `REPEATABLE READ` có thể giữ snapshot cũ nếu đã thực hiện consistent read trước khi Session A commit.

Kịch bản rõ ràng:

1. Session B đặt `READ COMMITTED` hoặc bắt đầu transaction mới sau khi A commit.
2. Session A mở transaction, cập nhật một hàng.
3. Session B đọc trước commit và không thấy thay đổi chưa commit.
4. Session A commit.
5. Session B đọc lại trong `READ COMMITTED` và thấy giá trị mới.
6. Lặp lại kịch bản với Session A rollback; Session B không thấy thay đổi.

SQL chuẩn bị Session B:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Nếu muốn kiểm tra `REPEATABLE READ`, hãy chủ động tạo read view và xác minh Session B tiếp tục nhìn thấy snapshot cũ trong cùng transaction. Không kết luận commit thất bại chỉ vì một session vẫn đọc snapshot trước đó.

## 13. Test deadlock và lock wait

Kiểm thử đồng thời nên tạo ra tình huống tranh chấp có thể lặp lại. Ví dụ hai session cập nhật hai hàng theo thứ tự ngược nhau:

Session A:

```sql
START TRANSACTION;
UPDATE account_probe SET balance = balance - 10 WHERE account_id = 1;
-- Chờ Session B cập nhật hàng 2.
UPDATE account_probe SET balance = balance + 10 WHERE account_id = 2;
```

Session B:

```sql
START TRANSACTION;
UPDATE account_probe SET balance = balance - 20 WHERE account_id = 2;
-- Sau khi B giữ khóa hàng 2, thử cập nhật hàng 1.
UPDATE account_probe SET balance = balance + 20 WHERE account_id = 1;
```

Điều phối hai session để mỗi bên giữ một khóa trước khi yêu cầu khóa còn lại. InnoDB có thể phát hiện deadlock và rollback một transaction. Kiểm tra lỗi trả về, transaction victim và trạng thái dữ liệu sau đó.

Để xem thông tin deadlock gần nhất:

```sql
SHOW ENGINE INNODB STATUS\G
```

Khi kiểm thử lock wait timeout, đặt giá trị session phù hợp trong lab:

```sql
SET SESSION innodb_lock_wait_timeout = 3;
```

Giữ khóa ở Session A rồi yêu cầu Session B cập nhật cùng hàng. Khi B timeout, xác minh statement bị rollback và transaction B còn hoạt động hay không theo cấu hình `innodb_rollback_on_timeout`. Kết thúc cả hai transaction sau test.

## 14. Những sai lầm thường gặp trong test transaction

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Gọi `ROLLBACK` sau INSERT khi autocommit bật và kỳ vọng xóa hàng | INSERT đã commit khi statement kết thúc | Tắt autocommit hoặc dùng `START TRANSACTION` trước DML |
| Chạy `ALTER TABLE` rồi rollback | DDL gây implicit commit | Tách DDL khỏi transaction DML cần rollback |
| Dùng MyISAM để kiểm tra rollback | Engine không hỗ trợ transaction | Dùng InnoDB và xác minh `ENGINE` |
| Cho rằng mọi lỗi SQL rollback toàn transaction | Nhiều lỗi chỉ rollback statement; deadlock và lock timeout có quy tắc riêng | Kiểm tra trạng thái transaction sau từng loại lỗi |
| Dùng `START TRANSACTION` lồng nhau | MySQL không hỗ trợ nested transaction theo cách này | Dùng savepoint hoặc thiết kế transaction riêng |
| Dùng `@Transactional` test để dọn DDL | Implicit commit có thể làm dữ liệu tồn tại sau test | Tạo schema riêng và teardown rõ ràng |
| Kiểm tra lại entity mà không clear persistence context | JPA có thể trả object đang được quản lý thay vì đọc DB | Flush rồi clear/reload khi cần xác minh database |
| Chỉ test bằng H2 | Semantics DDL, lock, isolation và SQL khác MySQL | Chạy integration test với MySQL thật hoặc container đúng phiên bản |

## 15. Quy trình kiểm thử transaction có thể lặp lại

1. **Tạo môi trường cô lập:** schema hoặc MySQL container riêng cho test suite.
2. **Chuẩn bị schema:** chạy migration/setup trước khi mở transaction test.
3. **Xác minh engine:** đảm bảo bảng cần rollback dùng InnoDB.
4. **Ghi baseline:** lưu dữ liệu ban đầu và session variables liên quan.
5. **Kiểm tra autocommit:** xác nhận `@@SESSION.autocommit` và điều chỉnh trong session test.
6. **Kiểm tra DML:** thực hiện commit và rollback bằng ít nhất một transaction tường minh.
7. **Kiểm tra visibility:** dùng hai connection độc lập với isolation đã xác định.
8. **Kiểm tra savepoint/lỗi:** xác nhận rollback một phần, statement error, deadlock và lock timeout.
9. **Kiểm tra DDL riêng:** xác minh implicit commit bằng bảng thử nghiệm; không gộp với test rollback DML.
10. **Kiểm tra ứng dụng:** xác minh JDBC/Spring/JPA dùng đúng connection và transaction boundary.
11. **Cleanup:** kết thúc transaction, đóng connection, xóa dữ liệu test và khôi phục session settings.
12. **Lưu bằng chứng:** SQL đã chạy, kết quả trước/sau, isolation, engine, cấu hình autocommit và log lỗi.

## 16. Tình huống thực hành

Một ứng dụng bán hàng cần kiểm tra thao tác chuyển 100 đơn vị tiền từ account 1 sang account 2. Nhóm phát triển muốn chắc chắn rằng lỗi ở bước thứ hai không làm mất tiền, đồng thời muốn kiểm tra một migration thêm cột ghi chú vào bảng account.

Thực hiện trong môi trường lab:

1. Tạo schema riêng và hai bảng InnoDB có dữ liệu nền.
2. Chạy hai UPDATE trong một transaction, commit và xác minh tổng số dư không đổi.
3. Chạy lại nhưng phát sinh lỗi trước commit; rollback và xác minh cả hai số dư trở lại baseline.
4. Bật autocommit và thực hiện một UPDATE; gọi rollback sau đó để chứng minh statement đã commit.
5. Tắt autocommit, cập nhật dữ liệu rồi rollback; xác minh thay đổi không tồn tại.
6. Dùng savepoint để rollback riêng bước cộng tiền nhưng giữ bước trừ tiền, sau đó commit để quan sát kết quả.
7. Tạo duplicate key trong transaction và kiểm tra statement thất bại nhưng transaction vẫn có thể tiếp tục.
8. Thực hiện INSERT rồi `ALTER TABLE` trong cùng transaction, gọi rollback và xác minh INSERT cùng DDL vẫn tồn tại do implicit commit.
9. Viết một integration test Spring có `@Transactional`, gọi `flush()` và kiểm tra dữ liệu sau khi clear persistence context.
10. Chạy DDL test riêng trên schema dùng một lần và dọn dẹp sau test.

**Câu hỏi tự đánh giá:**

- Khi `autocommit=1`, vì sao `ROLLBACK` sau một INSERT thành công không xóa hàng?
- `SET autocommit=1` có thể ảnh hưởng transaction chưa commit như thế nào?
- `ROLLBACK TO SAVEPOINT` khác `ROLLBACK` ở điểm nào?
- Vì sao duplicate key thường không tự rollback toàn bộ transaction InnoDB?
- Deadlock và lock wait timeout có phạm vi rollback giống nhau không?
- Vì sao `ALTER TABLE` có thể commit DML trước đó dù được gọi giữa `START TRANSACTION` và `ROLLBACK`?
- Atomic DDL khác transactional DDL như thế nào?
- Vì sao `@Transactional` trên test method không bảo đảm dọn được thay đổi DDL?
- Làm thế nào kiểm tra visibility giữa hai session mà không nhầm với snapshot `REPEATABLE READ`?

## Kết luận

Kiểm thử transaction MySQL phải xác định rõ storage engine, autocommit, isolation và ranh giới commit. DML trên InnoDB có thể rollback khi còn trong transaction; savepoint cho phép rollback một phần; lỗi statement không phải lúc nào cũng hủy toàn transaction. Nhiều câu DDL gây implicit commit, và atomic DDL chỉ bảo vệ tính nguyên tử của một thao tác trước sự cố chứ không cho phép `ROLLBACK` DDL. Hãy tách setup schema khỏi test DML, dùng connection độc lập để kiểm tra visibility và chạy integration test trên MySQL/InnoDB thật.
