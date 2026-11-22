# autocommit và ranh giới giao dịch ở từng kết nối

MySQL mặc định chạy với `autocommit = 1`. Điều đó có nghĩa là mỗi câu lệnh SQL độc lập được thực hiện như một transaction riêng và được commit khi câu lệnh thành công. Cách này thuận tiện cho thao tác đơn lẻ, nhưng nếu một nghiệp vụ gồm nhiều câu lệnh cần thành công hoặc thất bại cùng nhau, ứng dụng phải mở transaction tường minh bằng `START TRANSACTION` (hoặc API tương ứng của JDBC), rồi kết thúc bằng `COMMIT` hoặc `ROLLBACK`.

Trạng thái `autocommit` và transaction thuộc về từng connection/session. Hai connection tới cùng một MySQL server có thể có chế độ autocommit khác nhau và đang ở các transaction khác nhau. `COMMIT` trên connection A không commit thay đổi của connection B; một transaction cũng không tự trải qua nhiều connection chỉ vì chúng thuộc cùng một request hoặc cùng một connection pool.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là xác định đúng ranh giới transaction trong SQL và JDBC, tránh commit ngoài ý muốn, giữ transaction ngắn và xử lý trạng thái connection an toàn khi dùng pool.

Sau bài học, bạn có thể:

- Giải thích `autocommit = 1` và `autocommit = 0` ở cấp session.
- Phân biệt transaction tự động theo từng statement với transaction nhiều statement.
- Dùng `START TRANSACTION`, `COMMIT` và `ROLLBACK` đúng ranh giới.
- Hiểu sự khác nhau giữa `SET SESSION autocommit` và `SET GLOBAL autocommit`.
- Nhận biết các câu lệnh gây implicit commit và các ngoại lệ quan trọng.
- Hiểu vì sao transaction không thể được chia sẻ giữa hai connection.
- Ánh xạ transaction sang JDBC và quản lý connection pool an toàn.
- Nhận biết giới hạn của rollback với storage engine không hỗ trợ transaction.

## 1. Transaction và autocommit

Transaction là một nhóm thao tác cơ sở dữ liệu được xem như một đơn vị công việc. Với bảng InnoDB, transaction cho phép commit toàn bộ thay đổi hoặc rollback các thay đổi chưa commit. `autocommit` quyết định MySQL tự kết thúc transaction sau từng statement hay để session duy trì transaction cho đến khi client yêu cầu.

Kiểm tra chế độ hiện tại:

```sql
SELECT
    CONNECTION_ID() AS connection_id,
    @@session.autocommit AS session_autocommit,
    @@global.autocommit AS global_autocommit;
```

Trong MySQL, `autocommit` là biến hệ thống có phạm vi `GLOBAL` và `SESSION`. Giá trị mặc định thường là `1`.

| Giá trị | Ý nghĩa |
| --- | --- |
| `autocommit = 1` | Mỗi statement không nằm trong transaction tường minh được commit tự động khi thành công |
| `autocommit = 0` | Session hoạt động ở chế độ transaction liên tục; các statement transactional được gom vào transaction hiện tại cho đến `COMMIT` hoặc `ROLLBACK` |

`autocommit` là cấu hình của connection, không phải thuộc tính của một bảng hoặc một câu SQL riêng lẻ. `@@session.autocommit` là giá trị session đang dùng; `@@global.autocommit` là giá trị mặc định được áp dụng cho connection mới.

## 2. autocommit = 1: mỗi statement là một transaction

Với chế độ mặc định:

```sql
SET SESSION autocommit = 1;

UPDATE accounts_demo
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE accounts_demo
SET balance = balance + 100.00
WHERE account_id = 2;
```

Hai câu `UPDATE` là hai transaction riêng. Nếu câu thứ nhất thành công và câu thứ hai thất bại, thay đổi của câu thứ nhất đã được commit và không thể dùng `ROLLBACK` sau đó để hoàn tác nó.

Điều này phù hợp với thao tác độc lập như đổi một thuộc tính đơn, ghi một bản ghi log hoặc cập nhật một giá trị không phụ thuộc vào statement tiếp theo. Nó không đủ cho nghiệp vụ cần nhiều thao tác cùng thành công, chẳng hạn chuyển tiền giữa hai tài khoản.

Một statement DML thành công trên bảng InnoDB được commit tự động khi kết thúc nếu session đang ở `autocommit = 1` và không có transaction tường minh bao quanh nó. Nếu statement thất bại, MySQL/InnoDB xử lý lỗi ở cấp statement; không có thay đổi thành công nào của statement đó được commit như một thao tác hoàn chỉnh.

## 3. Transaction tường minh với START TRANSACTION

Để gom nhiều statement thành một đơn vị công việc, dùng:

```sql
START TRANSACTION;

-- Các câu lệnh thuộc cùng transaction
UPDATE ...;
INSERT ...;
DELETE ...;

COMMIT;
```

`BEGIN` hoặc `BEGIN WORK` cũng có thể bắt đầu transaction. `START TRANSACTION` thường rõ nghĩa hơn khi đọc code SQL.

- `START TRANSACTION` bắt đầu transaction tường minh trên connection hiện tại.
- `COMMIT` xác nhận các thay đổi transactional trong transaction hiện tại.
- `ROLLBACK` hủy các thay đổi transactional chưa commit trong transaction hiện tại.

Khi transaction tường minh đang mở, `autocommit` có thể vẫn là `1`; các statement nằm giữa `START TRANSACTION` và `COMMIT`/`ROLLBACK` vẫn thuộc cùng transaction. Sau khi transaction kết thúc, session quay lại hành vi autocommit đã cấu hình.

### 3.1. Ví dụ chuyển tiền nguyên tử

Tạo bảng và dữ liệu ban đầu trước khi mở transaction:

```sql
DROP TABLE IF EXISTS accounts_demo;

CREATE TABLE accounts_demo (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_accounts_demo_balance CHECK (balance >= 0)
) ENGINE = InnoDB;

INSERT INTO accounts_demo (account_id, owner_name, balance) VALUES
(1, 'An', 1000.00),
(2, 'Binh', 500.00);
```

Chuyển 100.00 từ tài khoản 1 sang tài khoản 2:

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

UPDATE accounts_demo
SET balance = balance + 100.00
WHERE account_id = 2;

COMMIT;
```

Hai thay đổi thuộc cùng transaction. Nếu ứng dụng xác nhận cả hai thao tác hợp lệ rồi commit, số dư cuối là 900.00 và 600.00. Nếu có lỗi cần hủy nghiệp vụ trước commit, chạy `ROLLBACK` trên cùng connection.

Trong ứng dụng thật, không được chỉ dựa vào việc câu SQL không ném exception. Cần kiểm tra update count của từng câu, ví dụ câu trừ tiền phải cập nhật đúng một hàng. Nếu tài khoản không tồn tại hoặc không đủ tiền, ứng dụng phải rollback thay vì tiếp tục cộng tiền vào tài khoản nhận.

Ví dụ luồng điều khiển ở mức ứng dụng:

```text
START TRANSACTION
       |
       v
Trừ tiền tài khoản gửi
       |
       v
Đúng một hàng được cập nhật?
    /       \
  Không      Có
   |          |
ROLLBACK      v
          Cộng tiền tài khoản nhận
                 |
                 v
          Đúng một hàng được cập nhật?
              /       \
            Không      Có
             |          |
          ROLLBACK    COMMIT
```

Đây là logic nghiệp vụ minh họa. Trong hệ thống cạnh tranh cao, còn phải xử lý deadlock, retry có giới hạn và idempotency của yêu cầu chuyển tiền.

### 3.2. Kiểm tra rollback

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 50.00
WHERE account_id = 1;

SELECT account_id, balance
FROM accounts_demo
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM accounts_demo
ORDER BY account_id;
```

Trong cùng connection, `SELECT` trước `ROLLBACK` nhìn thấy thay đổi chưa commit của chính transaction. Sau `ROLLBACK`, số dư trở lại giá trị đã commit trước transaction. Connection khác không nhìn thấy thay đổi chưa commit đó theo cơ chế đọc nhất quán của InnoDB.

## 4. autocommit = 0: session duy trì transaction

Có thể tắt autocommit cho connection hiện tại:

```sql
SET SESSION autocommit = 0;
SELECT @@session.autocommit;
```

Khi đó, các statement transactional không tự commit sau từng câu. Transaction được bắt đầu ngầm khi session thực hiện thao tác transactional và tiếp tục cho đến khi client chạy `COMMIT` hoặc `ROLLBACK`.

```sql
SET SESSION autocommit = 0;

UPDATE accounts_demo
SET balance = balance - 25.00
WHERE account_id = 1;

UPDATE accounts_demo
SET balance = balance + 25.00
WHERE account_id = 2;

COMMIT;
```

`COMMIT` kết thúc transaction hiện tại nhưng không tự đặt lại `autocommit` thành 1. Session vẫn ở chế độ `autocommit = 0`; transaction tiếp theo sẽ bắt đầu ngầm khi session thực hiện statement transactional tiếp theo.

Để bật lại chế độ mặc định:

```sql
SET SESSION autocommit = 1;
```

Nếu thay đổi từ `autocommit = 0` sang `autocommit = 1` khi transaction đang mở, MySQL commit transaction hiện tại. Đây là implicit commit; không dùng lệnh này như một cách “dọn trạng thái” nếu chưa quyết định rõ có muốn giữ thay đổi hay không.

### 4.1. Không trộn SET autocommit=0 và START TRANSACTION một cách tùy tiện

`START TRANSACTION` bắt đầu transaction mới và commit transaction đang mở trước đó. Vì vậy, nếu session đang `autocommit = 0`, đã có thay đổi chưa commit, rồi chạy `START TRANSACTION`, các thay đổi trước đó có thể bị commit ngoài dự kiến.

Hãy chọn một mô hình rõ ràng:

- Dùng `autocommit = 1` và mở từng transaction nhiều statement bằng `START TRANSACTION`/`COMMIT`/`ROLLBACK`.
- Hoặc dùng `autocommit = 0` cho session được quản lý chặt, luôn kết thúc transaction và khôi phục trạng thái trước khi trả connection.

Với ứng dụng web và connection pool, mô hình đầu thường dễ kiểm soát hơn vì ranh giới transaction hiện rõ trong từng đơn vị nghiệp vụ.

## 5. Ranh giới transaction thuộc về từng connection

Mỗi connection tới MySQL có session riêng, bao gồm:

- Giá trị `@@session.autocommit`.
- Transaction đang mở và các thay đổi chưa commit.
- Transaction isolation level của session.
- Session variables, temporary tables và một số trạng thái khác.

Ví dụ kiểm tra hai connection:

**Connection A:**

```sql
SELECT CONNECTION_ID(), @@session.autocommit;
START TRANSACTION;
UPDATE accounts_demo
SET balance = balance - 10.00
WHERE account_id = 1;
```

**Connection B:**

```sql
SELECT CONNECTION_ID(), @@session.autocommit;
SELECT account_id, balance
FROM accounts_demo
WHERE account_id = 1;
```

Connection B có transaction và trạng thái autocommit riêng. Với InnoDB, B không nhìn thấy phần cập nhật chưa commit của A trong một consistent read thông thường; nó đọc phiên bản đã commit theo isolation/snapshot của B. Nếu A chạy `COMMIT`, các lần đọc phù hợp sau đó của B có thể nhìn thấy số dư mới.

`COMMIT` trong connection B không thể commit transaction của A. `ROLLBACK` trong B cũng không hủy thay đổi của A. Transaction không được xác định theo người dùng đăng nhập, thread ứng dụng, HTTP request hay tên database; nó được quản lý trên connection vật lý/session cụ thể.

### 5.1. Một nghiệp vụ cần dùng cùng connection

Nếu một nghiệp vụ gồm ba repository call cần cùng transaction, cả ba call phải sử dụng cùng connection tham gia transaction. Nếu mỗi repository tự lấy một connection độc lập từ pool, chúng có thể chạy trong ba transaction khác nhau dù được gọi trong cùng một method Java.

Trong framework transaction-aware như Spring, transaction manager thường bind connection của datasource vào execution context hiện tại. Các repository phải dùng cùng datasource và cơ chế lấy connection tương thích với transaction manager để tham gia transaction đó.

Không truyền một connection đang có transaction sang thread khác hoặc dùng đồng thời từ nhiều luồng. JDBC `Connection` không được thiết kế để nhiều thread cùng thao tác transaction một cách tùy ý.

## 6. SESSION và GLOBAL autocommit

Kiểm tra hai phạm vi:

```sql
SELECT @@session.autocommit, @@global.autocommit;
```

Đặt cho connection hiện tại:

```sql
SET SESSION autocommit = 0;
-- Hoặc dạng ngắn trong session hiện tại:
SET autocommit = 1;
```

Đặt giá trị mặc định cho các connection mới:

```sql
SET GLOBAL autocommit = 1;
```

`SET GLOBAL` yêu cầu quyền quản trị phù hợp và không thay đổi giá trị session của các connection đang tồn tại. Các connection mới tạo sau đó kế thừa giá trị global tại thời điểm kết nối, trừ khi cấu hình client hoặc ứng dụng ghi đè.

| Thao tác | Ảnh hưởng |
| --- | --- |
| `SET SESSION autocommit = 0` | Chỉ thay đổi connection hiện tại |
| `SET SESSION autocommit = 1` | Chỉ thay đổi connection hiện tại; chuyển 0 → 1 sẽ commit transaction đang mở |
| `SET GLOBAL autocommit = 0` | Thay đổi mặc định cho connection mới; không đổi session đang chạy |
| `SET GLOBAL autocommit = 1` | Thay đổi mặc định cho connection mới; không đổi session đang chạy |

Không nên thay đổi global autocommit để sửa một lỗi cục bộ trong ứng dụng. Hãy kiểm tra connection nào có cấu hình sai và sửa đúng ở connection pool hoặc nơi khởi tạo session.

## 7. COMMIT, ROLLBACK và savepoint

### 7.1. COMMIT

`COMMIT` xác nhận các thay đổi transactional trong transaction hiện tại. Sau commit, thay đổi trở thành dữ liệu đã commit và các lock transaction được giải phóng theo quy tắc InnoDB.

```sql
START TRANSACTION;
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 100;
INSERT INTO inventory_events (product_id, event_type) VALUES (100, 'SALE');
COMMIT;
```

Hai thay đổi thuộc cùng transaction nếu cả hai bảng dùng storage engine hỗ trợ transaction và statement thành công.

### 7.2. ROLLBACK

`ROLLBACK` hủy các thay đổi transactional chưa commit của transaction hiện tại:

```sql
START TRANSACTION;
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 100;
ROLLBACK;
```

Rollback không hoàn tác dữ liệu đã commit trước đó. Nếu session đang `autocommit = 1` và statement trước đã tự commit, một lệnh `ROLLBACK` sau đó không thể đảo ngược statement đó.

### 7.3. SAVEPOINT và ROLLBACK TO SAVEPOINT

Savepoint đánh dấu một vị trí bên trong transaction, cho phép rollback một phần thay đổi sau mốc đó:

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 20.00
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE accounts_demo
SET balance = balance + 20.00
WHERE account_id = 2;

-- Nếu bước sau savepoint cần hủy:
ROLLBACK TO SAVEPOINT after_debit;

-- Có thể tiếp tục thao tác khác rồi commit hoặc rollback toàn bộ.
COMMIT;
```

`ROLLBACK TO SAVEPOINT` chỉ hủy thay đổi sau savepoint, transaction vẫn còn mở. `RELEASE SAVEPOINT` xóa mốc; `COMMIT` hoặc `ROLLBACK` toàn transaction cũng xóa các savepoint.

Savepoint không phải transaction lồng nhau. Không thể dùng savepoint để commit một phần độc lập với transaction bên ngoài.

## 8. Implicit commit: câu lệnh có thể kết thúc transaction ngoài dự kiến

Không phải mọi câu lệnh SQL đều nằm trong transaction theo cách có thể rollback. MySQL có một số câu lệnh gây implicit commit, nghĩa là commit transaction hiện tại trước khi thực hiện câu lệnh đó.

Các nhóm thường gặp gồm:

- DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, `TRUNCATE TABLE`.
- Một số câu lệnh quản trị hoặc thao tác tài khoản như `CREATE USER`, `ALTER USER`, `GRANT`, `REVOKE`.
- `START TRANSACTION` khi transaction trước đó còn mở.
- `SET autocommit = 1` khi chuyển từ 0 sang 1.
- Một số câu lệnh khóa bảng và quản trị khác theo quy tắc của MySQL.

Ví dụ nguy hiểm:

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 100.00
WHERE account_id = 1;

ALTER TABLE accounts_demo
ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
```

`ALTER TABLE` gây implicit commit. Vì vậy, thay đổi số dư trước đó có thể đã được commit trước khi DDL chạy; `ROLLBACK` cuối không thể hoàn tác nó.

### 8.1. Ngoại lệ của temporary table

`CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` không gây implicit commit như DDL thông thường. Tuy nhiên, thao tác tạo/xóa temporary table không được rollback: nếu transaction rollback, temporary table vẫn tồn tại hoặc vẫn bị xóa tùy thao tác đã thực hiện.

Các DDL khác trên temporary table, ví dụ `ALTER TABLE`, vẫn có thể gây implicit commit theo quy tắc tương ứng. Đừng suy luận rằng mọi thao tác với temporary table đều an toàn trong transaction.

### 8.2. Atomic DDL không có nghĩa DDL là transactional

MySQL 8.0 có atomic DDL cho nhiều thao tác DDL được hỗ trợ: thay đổi metadata và data dictionary của chính DDL được bảo đảm hoàn tất hoặc phục hồi như một đơn vị khi có sự cố. Điều đó không có nghĩa DDL tham gia transaction DML của ứng dụng hoặc có thể được hủy bằng `ROLLBACK` sau khi statement thành công.

Hãy chạy migration/schema change ở quy trình riêng, ngoài transaction nghiệp vụ cần rollback toàn bộ.

## 9. Transaction chỉ bảo vệ storage engine có hỗ trợ transaction

InnoDB hỗ trợ transaction, commit, rollback và các cơ chế khóa/đọc nhất quán. MyISAM không hỗ trợ transaction theo cách của InnoDB.

Nếu transaction cập nhật một bảng InnoDB và một bảng MyISAM, `ROLLBACK` chỉ có thể hoàn tác thay đổi ở bảng InnoDB; thay đổi ở MyISAM không được hoàn tác.

Kiểm tra engine:

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts_demo', 'inventory');
```

Với nghiệp vụ cần tính nguyên tử, các bảng tham gia phải dùng engine transactional phù hợp, thường là InnoDB. Cũng cần lưu ý các thao tác bên ngoài database như gửi email, gọi API thanh toán hoặc ghi file không được MySQL transaction tự rollback; chúng cần cơ chế phối hợp riêng như transactional outbox hoặc saga.

## 10. Transaction trong JDBC

JDBC `Connection` mặc định ở chế độ auto-commit. Muốn gom nhiều statement, đặt `setAutoCommit(false)`, thực hiện công việc trên cùng connection, rồi gọi `commit()` hoặc `rollback()`.

Đoạn minh họa dưới đây được đặt trong một method khai báo `throws SQLException`:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        try (PreparedStatement debit = connection.prepareStatement(
                "UPDATE accounts_demo " +
                "SET balance = balance - ? " +
                "WHERE account_id = ? AND balance >= ?")) {
            debit.setBigDecimal(1, new BigDecimal("100.00"));
            debit.setLong(2, 1L);
            debit.setBigDecimal(3, new BigDecimal("100.00"));

            int debited = debit.executeUpdate();
            if (debited != 1) {
                throw new SQLException("Debit failed: account missing or insufficient balance");
            }
        }

        try (PreparedStatement credit = connection.prepareStatement(
                "UPDATE accounts_demo SET balance = balance + ? WHERE account_id = ?")) {
            credit.setBigDecimal(1, new BigDecimal("100.00"));
            credit.setLong(2, 2L);

            int credited = credit.executeUpdate();
            if (credited != 1) {
                throw new SQLException("Credit failed: destination account not found");
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Ví dụ dùng `BigDecimal` cho tiền và kiểm tra update count của từng bước. Trong ứng dụng thật, cần xử lý retry deadlock, logging, exception mapping và trường hợp kết quả commit không xác định do mất kết nối.

### 10.1. setAutoCommit(true) có thể commit transaction hiện tại

Theo JDBC, nếu gọi `setAutoCommit(true)` khi connection đang ở chế độ auto-commit false và có transaction đang mở, driver commit transaction hiện tại. Vì vậy, không gọi lệnh này để “reset” connection khi chưa quyết định transaction có được commit hay không.

Thứ tự dọn dẹp an toàn thường là:

1. Nếu nghiệp vụ thất bại trước commit, gọi `rollback()`.
2. Khôi phục trạng thái connection theo hợp đồng của pool/framework.
3. Đóng connection logic để trả lại pool.

`commit()` hoặc `rollback()` chỉ hợp lệ khi connection đang ở chế độ transaction thủ công theo JDBC; gọi chúng khi auto-commit đang bật có thể gây `SQLException` tùy driver.

### 10.2. Dùng try-with-resources không thay thế rollback

`try-with-resources` bảo đảm đóng resource, nhưng code vẫn phải quyết định commit hay rollback. Không giả định `Connection.close()` luôn rollback theo cách ứng dụng mong muốn, đặc biệt khi `close()` trên pooled connection chỉ trả connection logic về pool.

Nếu không commit và connection vật lý thực sự bị đóng, MySQL sẽ rollback transaction InnoDB chưa commit. Nhưng trong pool, connection vật lý vẫn sống; transaction hoặc session state có thể ảnh hưởng request tiếp theo nếu pool không reset đúng. Hãy rollback rõ ràng khi có lỗi và tuân theo transaction manager.

## 11. Connection pool và trạng thái session

Connection pool tái sử dụng connection vật lý để giảm chi phí mở kết nối. Vì `autocommit` là session state, cấu hình và cleanup của pool có ảnh hưởng trực tiếp đến ranh giới transaction.

Các rủi ro thường gặp:

- Một request gọi `setAutoCommit(false)` rồi trả connection về pool mà không commit/rollback.
- Request sau nhận lại connection có trạng thái `autocommit = 0` hoặc transaction chưa được dọn.
- Một repository tự lấy connection mới thay vì dùng connection đang được transaction manager quản lý.
- Code gọi `setAutoCommit(true)` khi còn thay đổi chưa commit và vô tình commit chúng.
- Session variables hoặc isolation level bị thay đổi rồi rò rỉ sang lần mượn tiếp theo.

Nguyên tắc:

- Để pool quản lý cấu hình mặc định; không tùy tiện đổi `GLOBAL autocommit` từ code nghiệp vụ.
- Bắt đầu và kết thúc transaction trong cùng phạm vi quản lý connection.
- Luôn commit khi thành công hoặc rollback khi thất bại.
- Khôi phục `autoCommit`, isolation level, read-only và các session state khác nếu code đã thay đổi chúng và pool/framework không tự đảm nhận.
- Dùng transaction manager hoặc API lấy connection có nhận biết transaction.
- Giữ transaction ngắn; không chờ người dùng, gọi dịch vụ bên ngoài hoặc thực hiện công việc lâu trong lúc giữ lock.

Một số pool có cơ chế reset trạng thái khi connection được trả về. Đây là lớp bảo vệ bổ sung, không thay thế trách nhiệm đóng transaction đúng cách trong code.

## 12. Transaction boundary và lỗi ứng dụng

### 12.1. Statement lỗi không phải lúc nào cũng rollback toàn transaction

Trong explicit transaction, một statement lỗi thường được rollback ở cấp statement; transaction có thể vẫn còn mở. Không nên giả định mọi `SQLException` đều tự động rollback toàn bộ transaction. Ứng dụng cần quyết định rollback transaction khi nghiệp vụ không thể tiếp tục.

Một ngoại lệ quan trọng là deadlock: InnoDB chọn một transaction làm nạn nhân và rollback transaction đó để giải phóng deadlock. Ứng dụng phải retry toàn bộ transaction theo chính sách có giới hạn, không chỉ retry câu lệnh cuối cùng.

Lock wait timeout thường chỉ rollback statement gây timeout theo mặc định, trừ khi cấu hình `innodb_rollback_on_timeout` thay đổi hành vi. Sau lỗi lock timeout, ứng dụng nên rollback toàn transaction nếu không có logic phục hồi rõ ràng.

### 12.2. Mất kết nối khi COMMIT

Nếu client mất kết nối ngay khi gửi `COMMIT`, ứng dụng có thể không biết server đã commit hay chưa. Không thể kết luận transaction chắc chắn rollback chỉ vì client nhận timeout hoặc lỗi mạng.

Với thao tác có thể được gửi lại, hãy thiết kế idempotency key, mã giao dịch duy nhất hoặc bảng ghi nhận request để kiểm tra kết quả trước khi retry. Không retry mù một thao tác trừ tiền/cộng tiền có thể gây ghi nhận hai lần nếu lần commit đầu đã thành công.

### 12.3. Không giữ transaction quá lâu

Transaction dài có thể giữ row locks, làm tăng contention, giữ read view cũ, trì hoãn purge undo và làm tăng dung lượng undo history. Hãy đọc/validate dữ liệu cần thiết, mở transaction sát thời điểm ghi, thực hiện nhanh các thao tác database rồi commit/rollback.

Không mở transaction trước khi người dùng xác nhận trên giao diện hoặc trước một HTTP call có thời gian phản hồi không xác định.

## 13. Các lệnh và trạng thái cần nhớ

| Lệnh | Tác dụng chính | Lưu ý |
| --- | --- | --- |
| `SET SESSION autocommit = 1` | Bật tự commit cho connection hiện tại | Chuyển từ 0 sang 1 có thể commit transaction đang mở |
| `SET SESSION autocommit = 0` | Tắt tự commit cho connection hiện tại | Session cần kết thúc transaction bằng COMMIT/ROLLBACK |
| `SET GLOBAL autocommit = 1` | Đổi mặc định cho connection mới | Không đổi session đang tồn tại |
| `START TRANSACTION` | Bắt đầu transaction tường minh | Commit transaction đang mở trước đó; không hỗ trợ nested transaction |
| `COMMIT` | Commit transaction hiện tại | Không reset autocommit mode |
| `ROLLBACK` | Hủy thay đổi chưa commit | Không thể đảo ngược thay đổi đã commit hoặc thao tác trên engine không transactional |
| `SAVEPOINT name` | Tạo mốc trong transaction | Không phải transaction lồng nhau |
| `ROLLBACK TO SAVEPOINT name` | Hủy phần sau mốc | Transaction vẫn mở |
| `RELEASE SAVEPOINT name` | Xóa mốc | Không commit transaction |

Kiểm tra trạng thái trong session:

```sql
SELECT
    CONNECTION_ID(),
    @@session.autocommit,
    @@session.transaction_isolation;
```

`@@session.transaction_isolation` cho biết isolation level của session. Isolation level ảnh hưởng đến cách các transaction nhìn thấy dữ liệu, nhưng không thay đổi nguyên tắc rằng transaction và autocommit thuộc về từng connection.

## 14. Quy trình kiểm chứng trong hai session

Thực hành sau giúp nhìn rõ transaction boundary:

1. Mở hai connection A và B tới cùng schema.
2. Trên A, xác nhận `@@session.autocommit = 1`, bắt đầu transaction và cập nhật một tài khoản.
3. Trên A, đọc lại hàng để xác nhận session thấy thay đổi của chính nó.
4. Trên B, đọc cùng hàng; B chỉ thấy dữ liệu đã commit theo isolation/snapshot của B.
5. Trên A, chạy `ROLLBACK`; xác nhận B tiếp tục thấy giá trị cũ.
6. Lặp lại nhưng thay `ROLLBACK` bằng `COMMIT`; thực hiện một lần đọc mới phù hợp trên B để thấy giá trị đã commit.
7. Trên A, đặt `autocommit = 0`; thực hiện update rồi đọc `CONNECTION_ID()` và `@@session.autocommit` trên cả A lẫn B để xác nhận session state không chia sẻ.
8. Kết thúc transaction trên A và bật lại `autocommit = 1` trước khi trả connection nếu đây là connection được tái sử dụng.

Không chạy các bước thử nghiệm trên tài khoản hoặc dữ liệu production. Dùng bảng lab InnoDB riêng và khôi phục dữ liệu sau bài thực hành.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ autocommit là cấu hình toàn server duy nhất | Hiểu sai trạng thái giữa các connection | Kiểm tra `@@session.autocommit` và `@@global.autocommit` |
| Chạy nhiều DML với autocommit=1 và nghĩ chúng cùng transaction | Statement trước có thể đã commit dù statement sau lỗi | Dùng `START TRANSACTION` cho nghiệp vụ nhiều bước |
| Quên COMMIT hoặc ROLLBACK khi autocommit=0 | Transaction/lock tồn tại lâu và ảnh hưởng connection tái sử dụng | Kết thúc transaction trên mọi nhánh code |
| Nghĩ COMMIT bật lại autocommit | Session vẫn ở `autocommit=0` | Đặt lại session state có chủ đích |
| Gọi START TRANSACTION khi transaction cũ còn mở | Transaction cũ bị implicit commit | Không giả định có nested transaction; dùng savepoint nếu cần mốc nội bộ |
| Chạy DDL giữa transaction DML | Implicit commit làm mất khả năng rollback toàn bộ | Tách migration khỏi transaction nghiệp vụ |
| Cho rằng ROLLBACK đảo ngược mọi engine | MyISAM và thao tác ngoài database không được rollback | Dùng InnoDB và thiết kế phối hợp cho side effect |
| Mỗi repository tự lấy connection riêng | Các thao tác không nằm trong cùng transaction | Chia sẻ connection do transaction manager quản lý |
| Dùng setAutoCommit(true) để cleanup | Có thể commit thay đổi chưa quyết định | Rollback hoặc commit rõ ràng trước khi đổi mode |
| Retry mù khi mất kết nối lúc COMMIT | Có thể thực hiện nghiệp vụ hai lần | Dùng idempotency và kiểm tra trạng thái giao dịch |

## 16. Bài tập thực hành

1. Kiểm tra `@@session.autocommit` và `@@global.autocommit` trên connection mới.
2. Chạy hai câu `UPDATE` với `autocommit = 1`; cố ý làm câu thứ hai thất bại và xác minh câu thứ nhất đã commit.
3. Chạy lại trong `START TRANSACTION`; khi câu thứ hai thất bại, rollback và xác minh cả hai thay đổi được hủy.
4. Đặt `autocommit = 0`, thực hiện một update rồi `COMMIT`. Kiểm tra chế độ autocommit vẫn là 0.
5. Chuyển từ `autocommit = 0` sang 1 khi còn transaction mở trong môi trường lab. Xác minh implicit commit và giải thích rủi ro.
6. Mở hai connection. Trên A cập nhật nhưng chưa commit; trên B đọc cùng hàng. Sau đó commit hoặc rollback trên A và quan sát lại trên B.
7. Tạo savepoint, thực hiện hai cập nhật, rollback về savepoint và commit phần còn lại.
8. Thử `ALTER TABLE` giữa transaction DML trong bảng lab. Quan sát vì sao rollback sau đó không hủy được thay đổi DML trước DDL.
9. So sánh rollback trên bảng InnoDB và một bảng MyISAM trong môi trường lab.
10. Viết JDBC service chuyển tiền với cùng một connection, kiểm tra update count, commit khi thành công và rollback khi có exception.
11. Mô phỏng connection pool: thay đổi autoCommit rồi trả connection; kiểm tra cơ chế reset của pool và bảo đảm request sau nhận trạng thái đúng.

## 17. Checklist trước khi đưa transaction vào production

- [ ] Đã xác định các statement nào phải thành công/thất bại cùng nhau.
- [ ] Đã xác nhận `autocommit` trên connection thực thi.
- [ ] Transaction nhiều statement có `START TRANSACTION`/`setAutoCommit(false)` rõ ràng.
- [ ] Mọi nhánh thành công đều commit; mọi nhánh lỗi đều rollback.
- [ ] Các bảng tham gia dùng storage engine transactional phù hợp, thường là InnoDB.
- [ ] Không có DDL hoặc câu lệnh implicit commit trong transaction nghiệp vụ.
- [ ] Tất cả repository trong cùng nghiệp vụ dùng cùng connection được quản lý bởi transaction manager.
- [ ] Connection pool reset autocommit và session state theo hợp đồng đã xác minh.
- [ ] Transaction được giữ ngắn và không bao gồm thời gian chờ người dùng/dịch vụ ngoài.
- [ ] Deadlock và lock timeout được xử lý có chủ đích.
- [ ] Retry có giới hạn và thao tác không bị lặp nhờ idempotency khi cần.
- [ ] Có cách đối soát khi client mất kết nối trong lúc commit.

## 18. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích được chế độ autocommit ở từng connection, phân biệt một statement tự commit với transaction nhiều statement, dùng đúng `START TRANSACTION`/`COMMIT`/`ROLLBACK`, nhận biết implicit commit và giới hạn của storage engine, đồng thời triển khai transaction JDBC trên cùng connection và trả connection pool về trạng thái sạch. Bạn cũng cần giải thích vì sao transaction không chia sẻ giữa hai connection và cách xử lý khi commit bị gián đoạn bởi lỗi mạng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — autocommit, Commit, and Rollback](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual — Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual — Transactional and Locking Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-transactional-statements.html)
- [MySQL 8.4 Reference Manual — InnoDB and Transactions](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
