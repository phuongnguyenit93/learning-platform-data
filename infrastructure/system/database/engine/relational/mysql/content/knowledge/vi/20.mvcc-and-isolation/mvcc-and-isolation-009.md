# Ảnh hưởng của autocommit đến mức cô lập quan sát được

Trong MySQL, \`autocommit\` và transaction isolation level là hai cấu hình khác nhau nhưng phối hợp với nhau để quyết định ứng dụng quan sát dữ liệu như thế nào.

- \`autocommit\` quyết định ranh giới transaction: mỗi câu lệnh tự commit hay nhiều câu lệnh cùng nằm trong một transaction.
- Isolation level quyết định cách transaction nhìn thấy thay đổi của transaction khác, cũng như mức khóa cần dùng để bảo vệ thao tác đọc/ghi.

Với InnoDB, isolation level mặc định thường là \`REPEATABLE READ\`. Tuy nhiên, nếu \`autocommit=1\`, mỗi câu SELECT độc lập là một transaction riêng. Vì vậy, hai câu SELECT liên tiếp có thể nhìn thấy hai snapshot khác nhau dù isolation level vẫn là REPEATABLE READ. Khi đặt nhiều câu SELECT trong cùng một transaction, REPEATABLE READ mới giữ cùng read view cho các consistent read trong transaction đó.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: hiểu MVCC, transaction và mức cô lập; kiểm soát ranh giới commit, dự đoán dữ liệu mà mỗi câu truy vấn quan sát được, thiết kế thao tác nhiều bước an toàn và xử lý trạng thái connection trong ứng dụng.

## 1. Hai cấu hình khác nhau: autocommit và isolation level

### 1.1. Autocommit quyết định transaction kết thúc khi nào

MySQL có biến hệ thống \`autocommit\`:

~~~sql
SELECT @@session.autocommit;
~~~

Giá trị thường gặp:

| Giá trị | Ý nghĩa |
|---:|---|
| 1 | Bật autocommit. Mỗi statement chạy như một transaction riêng nếu không có transaction tường minh đang mở. |
| 0 | Tắt autocommit. Session duy trì transaction cho các câu lệnh tiếp theo cho đến khi COMMIT hoặc ROLLBACK. |

Với \`autocommit=1\`, câu lệnh thay đổi dữ liệu trên InnoDB tự commit khi thành công nếu không nằm trong transaction tường minh:

~~~sql
UPDATE account
SET balance = balance + 100
WHERE account_id = 1;
~~~

Sau câu lệnh, thay đổi đã được commit. Một câu lệnh tiếp theo không thuộc cùng transaction.

Với \`autocommit=0\`, thay đổi chưa được commit tự động:

~~~sql
SET autocommit = 0;

UPDATE account
SET balance = balance + 100
WHERE account_id = 1;

-- Thay đổi vẫn thuộc transaction hiện tại.
COMMIT;
~~~

Nếu chạy ROLLBACK thay cho COMMIT trước khi transaction kết thúc, thay đổi InnoDB sẽ bị hoàn tác.

### 1.2. Isolation level quyết định cách đọc dữ liệu

InnoDB hỗ trợ bốn mức cô lập chuẩn:

| Isolation level | Đặc điểm chính |
|---|---|
| READ UNCOMMITTED | Có thể đọc thay đổi chưa commit của transaction khác (dirty read). |
| READ COMMITTED | Mỗi consistent read lấy snapshot mới tại đầu câu SELECT; có thể thấy commit mới giữa hai lần đọc trong cùng transaction. |
| REPEATABLE READ | Các consistent read trong cùng transaction dùng cùng read view được tạo ở lần consistent read đầu tiên, trừ khi yêu cầu snapshot riêng. |
| SERIALIZABLE | Mức nghiêm ngặt nhất; với transaction nhiều câu lệnh, SELECT thông thường được chuyển thành locking read trong các điều kiện InnoDB quy định. |

Kiểm tra isolation level:

~~~sql
SELECT
    @@session.transaction_isolation AS session_isolation,
    @@global.transaction_isolation AS global_default;
~~~

Isolation level không tự quyết định transaction kết thúc khi nào. Autocommit không tự thay đổi isolation level. Hai biến trả lời hai câu hỏi riêng:

- Autocommit: các câu lệnh nào thuộc cùng transaction?
- Isolation: các câu lệnh đọc trong transaction nhìn thấy phiên bản dữ liệu nào?

## 2. Vì sao autocommit ảnh hưởng tới mức cô lập quan sát được?

MVCC của InnoDB cho phép consistent read đọc phiên bản dữ liệu phù hợp với read view (snapshot) mà không cần khóa các hàng đang được đọc theo cách locking read thông thường.

Với \`REPEATABLE READ\`:

- Trong một transaction, consistent read đầu tiên tạo read view.
- Các consistent read tiếp theo trong cùng transaction tiếp tục dùng read view đó.
- Commit của transaction khác sau thời điểm tạo read view không làm thay đổi kết quả của các consistent read tiếp theo trong transaction hiện tại.

Khi \`autocommit=1\`, một câu SELECT độc lập thường kết thúc transaction ngay sau khi thực thi. SELECT tiếp theo bắt đầu transaction mới và tạo read view mới. Vì vậy, mỗi câu SELECT có thể nhìn thấy commit mới từ transaction khác.

Khi \`autocommit=0\` hoặc dùng \`START TRANSACTION\`, nhiều câu SELECT có thể thuộc cùng transaction. Với REPEATABLE READ, chúng có thể nhìn thấy cùng snapshot, dù transaction khác đã commit dữ liệu mới.

Đây là lý do hai session có thể quan sát kết quả khác nhau dù cùng dùng REPEATABLE READ: ranh giới transaction của chúng khác nhau.

## 3. Autocommit bật: mỗi SELECT độc lập có thể thấy snapshot mới

Giả sử bảng tài khoản:

~~~sql
CREATE TABLE account_mvcc_demo (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account_mvcc_demo (account_id, balance)
VALUES (1, 1000.00);
~~~

Session A cấu hình:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Kết quả đầu tiên là 1000.00. Vì autocommit đang bật và không có transaction tường minh, câu SELECT kết thúc transaction đọc của nó.

Trong lúc đó, Session B cập nhật và commit:

~~~sql
START TRANSACTION;

UPDATE account_mvcc_demo
SET balance = balance + 200
WHERE account_id = 1;

COMMIT;
~~~

Session A chạy lại cùng câu SELECT:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Kết quả lần này là 1200.00.

Điều này không vi phạm REPEATABLE READ. Hai SELECT nằm trong hai transaction độc lập, mỗi transaction có read view riêng. REPEATABLE READ bảo đảm khả năng lặp lại của consistent read trong cùng transaction, không giữ snapshot xuyên qua các transaction đã kết thúc.

### 3.1. Ý nghĩa đối với báo cáo nhiều câu truy vấn

Giả sử một màn hình báo cáo chạy hai câu:

~~~sql
SELECT SUM(balance)
FROM account_mvcc_demo;

SELECT COUNT(*)
FROM account_mvcc_demo;
~~~

Nếu autocommit=1, mỗi câu là transaction riêng. Một transaction khác có thể commit giữa hai câu. Khi đó tổng số dư và số tài khoản được tính từ hai snapshot khác nhau.

Nếu báo cáo cần các chỉ số nhất quán tại cùng một thời điểm logic, hãy gom chúng vào một transaction REPEATABLE READ hoặc dùng một câu SELECT tổng hợp phù hợp.

## 4. Autocommit bật nhưng có transaction tường minh

Bật autocommit không có nghĩa là không thể tạo transaction nhiều câu lệnh. \`START TRANSACTION\` mở transaction tường minh; các câu lệnh tiếp theo thuộc transaction đó cho tới COMMIT hoặc ROLLBACK.

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;

START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Giả sử kết quả là 1000.00 và consistent read đầu tiên đã tạo read view.

Session B cập nhật rồi commit:

~~~sql
START TRANSACTION;

UPDATE account_mvcc_demo
SET balance = balance + 200
WHERE account_id = 1;

COMMIT;
~~~

Session A đọc lại trong transaction đang mở:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Kết quả vẫn là 1000.00 vì consistent read tiếp tục dùng read view của transaction A.

Sau đó A commit:

~~~sql
COMMIT;
~~~

SELECT tiếp theo của A là transaction mới, vì autocommit vẫn bật. Nó có thể thấy 1200.00.

Điểm cần nhớ: \`autocommit=1\` chỉ có nghĩa các statement độc lập tự commit. Khi đã mở transaction tường minh, các statement bên trong vẫn được gom thành một transaction.

## 5. Autocommit tắt: nhiều statement dùng chung transaction

Với \`autocommit=0\`, session duy trì transaction cho các câu lệnh tiếp theo cho tới khi COMMIT hoặc ROLLBACK. Khi transaction kết thúc, session tiếp tục ở trạng thái autocommit tắt và transaction kế tiếp được bắt đầu khi có statement cần transaction.

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 0;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Giả sử kết quả là 1000.00. Đây là consistent read đầu tiên trong transaction và tạo read view.

Session B cập nhật balance thành 1200.00 rồi COMMIT.

Session A đọc lại:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Kết quả vẫn là 1000.00 vì transaction A chưa kết thúc và vẫn dùng snapshot cũ.

Kết thúc transaction A:

~~~sql
COMMIT;
~~~

Câu SELECT tiếp theo của A thuộc transaction mới:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Kết quả có thể là 1200.00 vì transaction mới tạo read view mới.

### 5.1. Autocommit=0 không đồng nghĩa snapshot được tạo ngay lúc SET

Một hiểu nhầm thường gặp là vừa chạy:

~~~sql
SET autocommit = 0;
~~~

thì snapshot đã được chụp ngay tại thời điểm đó. Với REPEATABLE READ, read view của consistent read thông thường được tạo khi transaction thực hiện consistent read đầu tiên, không nhất thiết ngay khi đổi biến autocommit.

Nếu cần tạo snapshot nhất quán ngay khi bắt đầu transaction, MySQL/InnoDB hỗ trợ:

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;
~~~

Tùy chọn này có ý nghĩa với InnoDB ở REPEATABLE READ; ở isolation level khác, MySQL có thể bỏ qua tùy chọn và phát cảnh báo. Hãy kiểm tra warning và tài liệu phiên bản đang chạy.

## 6. So sánh REPEATABLE READ và READ COMMITTED trong cùng transaction

Để thấy isolation level quan trọng như thế nào, giữ nguyên transaction nhiều câu lệnh và chỉ thay isolation level.

### 6.1. REPEATABLE READ

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B cập nhật và commit balance.

Session A SELECT lại trong cùng transaction. Với consistent read thông thường, A vẫn thấy giá trị trong snapshot đã tạo ở lần đọc đầu tiên.

### 6.2. READ COMMITTED

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B cập nhật và commit balance.

Session A SELECT lại:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Ở READ COMMITTED, mỗi consistent read lấy snapshot mới tại đầu câu SELECT. Vì vậy, lần đọc thứ hai có thể thấy giá trị B vừa commit, dù transaction A vẫn đang mở.

### 6.3. Bảng so sánh quan sát

Giả sử ban đầu balance=1000; B commit balance=1200 giữa hai lần đọc của A:

| Cấu hình của A | Transaction A | Lần đọc 1 | Lần đọc 2 |
|---|---|---:|---:|
| autocommit=1, REPEATABLE READ | Hai transaction riêng | 1000 | 1200 |
| autocommit=1, READ COMMITTED | Hai transaction riêng | 1000 | 1200 |
| autocommit=0, REPEATABLE READ | Một transaction | 1000 | 1000 |
| START TRANSACTION, REPEATABLE READ | Một transaction | 1000 | 1000 |
| autocommit=0, READ COMMITTED | Một transaction | 1000 | 1200 |

Bảng này giả định cả hai lần đọc là consistent read thông thường, B đã commit trước lần đọc thứ hai và không có thay đổi khác.

Với autocommit=1, sự khác nhau giữa REPEATABLE READ và READ COMMITTED thường không thể hiện qua hai SELECT độc lập, vì mỗi SELECT đã ở một transaction riêng. Sự khác biệt rõ ràng nhất xuất hiện khi nhiều SELECT nằm trong cùng transaction.

## 7. Bốn isolation level và vai trò của autocommit

### 7.1. READ UNCOMMITTED

Ở mức này, consistent read có thể đọc thay đổi chưa commit của transaction khác. Đây là dirty read.

Autocommit không loại bỏ dirty read. Nếu một SELECT chạy với READ UNCOMMITTED trong khi transaction khác đang cập nhật nhưng chưa commit, nó có thể quan sát giá trị chưa commit. Khi transaction kia ROLLBACK, giá trị từng nhìn thấy không còn tồn tại.

Không dùng READ UNCOMMITTED cho số dư, tồn kho, thanh toán hoặc dữ liệu cần độ tin cậy cao chỉ để giảm chờ khóa.

### 7.2. READ COMMITTED

Mỗi consistent read lấy snapshot mới tại đầu statement. Trong một transaction nhiều câu lệnh, lần đọc sau có thể thấy commit mới của transaction khác.

Autocommit=1 cũng tạo snapshot mới cho mỗi SELECT, nhưng đây là do mỗi statement thuộc transaction riêng. Với READ COMMITTED, snapshot mới được lấy cho từng consistent read ngay cả khi nhiều SELECT ở trong một transaction.

### 7.3. REPEATABLE READ

Đây là mức mặc định phổ biến của InnoDB. Các consistent read trong cùng transaction dùng cùng read view, tạo hành vi đọc lặp lại ổn định.

Khi autocommit=1 và mỗi SELECT là một transaction riêng, tính lặp lại không kéo dài qua hai SELECT độc lập. Dùng START TRANSACTION hoặc autocommit=0 khi cần cùng snapshot qua nhiều câu đọc.

### 7.4. SERIALIZABLE

SERIALIZABLE áp dụng quy tắc nghiêm ngặt hơn và có thể tăng khóa/chờ.

Trong InnoDB, khi transaction nhiều câu lệnh đang mở (autocommit tắt hoặc đã START TRANSACTION), SELECT thông thường ở SERIALIZABLE được xử lý như locking read kiểu shared lock theo quy tắc của engine. Khi autocommit=1, một SELECT độc lập là transaction chỉ có một statement và có thể được xử lý như consistent read.

Không chọn SERIALIZABLE chỉ để “chắc chắn hơn” mà không kiểm tra tác động khóa. Nó có thể làm giảm concurrency và tăng deadlock hoặc lock wait.

## 8. Consistent read và locking read không giống nhau

Tác động của autocommit còn thể hiện qua thời gian tồn tại của khóa.

### 8.1. Consistent read thông thường

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Với InnoDB ở READ COMMITTED hoặc REPEATABLE READ, đây thường là consistent nonlocking read. Nó đọc phiên bản phù hợp với read view và không đặt row lock chỉ để đọc.

### 8.2. Locking read với FOR UPDATE

~~~sql
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1
FOR UPDATE;

-- Thực hiện kiểm tra và cập nhật dựa trên hàng đã khóa.

COMMIT;
~~~

FOR UPDATE là locking read. InnoDB lấy khóa cần thiết để bảo vệ hàng được đọc cho tới khi transaction kết thúc.

Nếu chạy một câu SELECT FOR UPDATE trong autocommit=1 mà không mở transaction tường minh, không có transaction dài để giữ khóa cho một câu lệnh sau. Muốn khóa bảo vệ chuỗi đọc rồi ghi, hãy dùng START TRANSACTION hoặc autocommit=0.

### 8.3. FOR SHARE

~~~sql
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1
FOR SHARE;

COMMIT;
~~~

FOR SHARE lấy shared lock theo quy tắc InnoDB. Các transaction khác vẫn có thể đọc tương thích, nhưng thao tác ghi cần khóa xung đột có thể phải chờ.

Dùng locking read khi nghiệp vụ cần kiểm tra dữ liệu và giữ khóa trước khi thực hiện thao tác tiếp theo. Đừng thay mọi SELECT bằng FOR UPDATE vì sẽ tạo contention không cần thiết.

### 8.4. Locking read là current read

Locking read và các thao tác UPDATE/DELETE là current read, khác với consistent snapshot read thông thường. Chúng đọc phiên bản hiện hành phù hợp với quy tắc khóa của InnoDB thay vì chỉ đọc read view cũ.

Vì vậy, trong một transaction REPEATABLE READ, một SELECT thường có thể thấy snapshot cũ trong khi SELECT ... FOR UPDATE có thể thấy trạng thái hiện hành và khóa hàng. Không trộn hai loại đọc mà không hiểu sự khác biệt.

## 9. Tác động của autocommit tới thao tác nhiều bước

### 9.1. Chuyển tiền cần transaction tường minh

Ví dụ chuyển 100 từ tài khoản 1 sang tài khoản 2:

~~~sql
UPDATE account_mvcc_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_mvcc_demo
SET balance = balance + 100
WHERE account_id = 2;
~~~

Nếu autocommit=1 và hai UPDATE là hai statement riêng, UPDATE đầu có thể commit trước khi UPDATE thứ hai chạy. Nếu câu thứ hai thất bại, số tiền đã trừ ở tài khoản 1 vẫn được lưu.

Cách an toàn:

~~~sql
START TRANSACTION;

UPDATE account_mvcc_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_mvcc_demo
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Nếu một bước thất bại, ứng dụng ROLLBACK để cả hai thay đổi cùng được hoàn tác. Cần kiểm tra số hàng bị tác động và quy tắc không cho số dư âm theo nghiệp vụ.

### 9.2. Autocommit=0 có thể giữ transaction quá lâu

Tắt autocommit không tự động làm ứng dụng an toàn hơn. Nếu quên COMMIT hoặc ROLLBACK:
- Transaction có thể giữ row lock lâu.
- Consistent read view có thể giữ các phiên bản undo cần thiết, làm chậm purge.
- Connection idle nhưng transaction vẫn mở.
- Các transaction khác có thể bị chặn hoặc tăng nguy cơ deadlock.
- Metadata lock từ câu lệnh đã truy cập bảng có thể tồn tại lâu hơn mong muốn.

Vì vậy, với ứng dụng web, thường nên giữ autocommit mặc định và mở transaction tường minh đúng phạm vi nghiệp vụ. Tắt autocommit ở session chỉ phù hợp khi ứng dụng chủ động quản lý transaction và luôn bảo đảm kết thúc transaction.

### 9.3. Một SELECT dài và nhiều SELECT ngắn

Một câu SELECT duy nhất với autocommit=1 có một read view trong suốt statement. Nếu dữ liệu được cập nhật trong lúc câu SELECT đang chạy, consistent read vẫn dùng snapshot của statement đó.

Ngược lại, nhiều SELECT độc lập có autocommit=1 tạo nhiều transaction và nhiều read view. Kết quả tổng hợp từ nhiều câu lệnh có thể không đại diện cho cùng một thời điểm.

## 10. Cấu hình isolation level đúng phạm vi

MySQL hỗ trợ thiết lập isolation level ở các phạm vi khác nhau.

### 10.1. Kiểm tra hiện trạng

~~~sql
SELECT
    @@session.autocommit,
    @@session.transaction_isolation,
    @@global.transaction_isolation;
~~~

- SESSION là cấu hình của connection hiện tại.
- GLOBAL là mặc định được áp dụng cho connection mới, không tự thay đổi cấu hình session đã mở.

### 10.2. Đặt isolation level cho session

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
~~~

Thiết lập này áp dụng cho các transaction tiếp theo trong session. Nó không thay đổi isolation level của transaction đang chạy.

### 10.3. Đặt isolation level cho transaction kế tiếp

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

-- Các câu lệnh của transaction này dùng READ COMMITTED.

COMMIT;
~~~

Không ghi SESSION/GLOBAL thì SET TRANSACTION áp dụng cho transaction kế tiếp của session. Sau transaction đó, session quay lại isolation level mặc định hiện tại của nó.

### 10.4. Đặt mặc định toàn server

~~~sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

Cấu hình GLOBAL ảnh hưởng các session mới; các session hiện tại giữ giá trị session của chúng. Thao tác này cần quyền quản trị phù hợp và không nhất thiết tồn tại qua lần restart nếu không dùng cơ chế cấu hình persistent.

Không thay đổi GLOBAL chỉ để thử một truy vấn. Trong môi trường ứng dụng, ưu tiên cấu hình ở phạm vi session hoặc transaction để tránh ảnh hưởng connection khác.

## 11. SET autocommit và ranh giới transaction

### 11.1. Chuyển từ 1 sang 0

~~~sql
SET autocommit = 0;
~~~

Lệnh này tắt tự commit cho các statement tiếp theo của session. Nó không phải cách mở transaction con và không tạo snapshot consistent read ngay lập tức.

### 11.2. Chuyển từ 0 sang 1

~~~sql
SET autocommit = 1;
~~~

Nếu transaction đang hoạt động, chuyển autocommit từ 0 sang 1 sẽ commit transaction đó. Đây là thao tác có tác động dữ liệu, không chỉ là thay đổi cấu hình.

Trước khi bật lại autocommit, hãy quyết định rõ transaction đang mở phải COMMIT hay ROLLBACK. Không để câu lệnh cấu hình vô tình commit dữ liệu chưa được xác nhận.

### 11.3. START TRANSACTION khi autocommit=0

MySQL không hỗ trợ nested transaction. Gọi START TRANSACTION khi một transaction khác đang hoạt động sẽ kết thúc transaction hiện tại trước khi bắt đầu transaction mới. Dùng SAVEPOINT để tạo điểm quay lui trong cùng transaction, không dùng START TRANSACTION lồng nhau.

### 11.4. DDL và implicit commit

Nhiều DDL như ALTER TABLE, CREATE TABLE, DROP TABLE và TRUNCATE TABLE gây implicit commit. Nếu autocommit=0, DDL vẫn có thể kết thúc transaction đang hoạt động. Không dựa vào ROLLBACK để hoàn tác DDL đã thành công.

## 12. Autocommit trong JDBC và connection pool

JDBC thường tạo Connection với autocommit bật theo cấu hình mặc định của driver. Ứng dụng có thể kiểm tra:

~~~java
boolean autoCommit = connection.getAutoCommit();
int isolation = connection.getTransactionIsolation();
~~~

Để thực hiện một transaction nhiều câu lệnh:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    connection.setAutoCommit(false);

    try {
        // Các câu SQL trong cùng transaction.
        debitAccount(connection, fromAccountId, amount);
        creditAccount(connection, toAccountId, amount);

        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Ví dụ chỉ minh họa cấu trúc. Trong code thực tế cần:
- Kiểm tra số hàng cập nhật và các điều kiện nghiệp vụ.
- Rollback khi bất kỳ bước nào thất bại.
- Bảo đảm exception trong rollback không che mất lỗi gốc.
- Không giữ connection lâu hơn phạm vi transaction cần thiết.

### 12.1. Khôi phục trạng thái connection

Connection pool tái sử dụng connection vật lý. Nếu một request thay đổi autocommit hoặc isolation level mà không khôi phục, request sau có thể nhận connection với trạng thái khác mong đợi, tùy cách pool reset connection.

Mẫu quản lý rõ ràng:

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean originalAutoCommit = connection.getAutoCommit();
    int originalIsolation = connection.getTransactionIsolation();

    try {
        connection.setTransactionIsolation(
            Connection.TRANSACTION_REPEATABLE_READ
        );
        connection.setAutoCommit(false);

        // Thực hiện các thao tác thuộc một transaction.
        performBusinessOperation(connection);

        connection.commit();
    } catch (Exception ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        // Chỉ khôi phục sau khi transaction đã commit/rollback.
        connection.setAutoCommit(originalAutoCommit);
        connection.setTransactionIsolation(originalIsolation);
    }
}
~~~

Nếu \`originalAutoCommit=true\`, gọi setAutoCommit(true) khi transaction còn mở có thể commit transaction. Vì vậy, luôn commit hoặc rollback trước khi khôi phục autocommit. Trong hệ thống dùng pool, hãy xác minh pool có tự reset trạng thái và tuân thủ một quy ước thống nhất.

### 12.2. Đặt isolation trước khi bắt đầu transaction

JDBC:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
connection.setAutoCommit(false);
~~~

Đặt isolation trước khi transaction bắt đầu giúp tránh thay đổi cấu hình giữa transaction đang chạy. Không nên thay isolation level ở giữa một quy trình đọc/ghi rồi giả định snapshot hiện tại được tạo lại.

## 13. Các tình huống quan sát dễ nhầm

### 13.1. REPEATABLE READ nhưng hai SELECT vẫn khác nhau

Nguyên nhân: hai SELECT thuộc hai transaction khác nhau vì autocommit=1.

Cách xử lý: dùng START TRANSACTION nếu cần cùng read view qua nhiều câu đọc.

### 13.2. READ COMMITTED nhưng transaction vẫn mở

READ COMMITTED không tự commit transaction sau mỗi SELECT. Với autocommit=0 hoặc transaction tường minh, transaction vẫn mở cho tới COMMIT/ROLLBACK; chỉ có read view được làm mới cho từng consistent read.

### 13.3. REPEATABLE READ nhưng SELECT FOR UPDATE thấy giá trị khác

SELECT thông thường có thể là consistent read dùng snapshot cũ; SELECT FOR UPDATE là locking/current read. Hai loại đọc có semantics khác nhau.

### 13.4. Autocommit=0 nhưng đọc không thấy commit mới

Nếu transaction đã tạo read view ở REPEATABLE READ, các consistent read sau tiếp tục dùng snapshot đó. COMMIT hoặc ROLLBACK để kết thúc transaction, sau đó đọc lại trong transaction mới.

### 13.5. Autocommit=1 nhưng hai UPDATE không nguyên tử

Mỗi UPDATE là transaction riêng. Dùng START TRANSACTION để gom cả hai thay đổi thành một đơn vị nguyên tử.

## 14. Bảng quyết định theo nhu cầu

| Nhu cầu | Cấu hình/thiết kế phù hợp |
|---|---|
| Mỗi câu lệnh độc lập, không cần transaction nhiều bước | autocommit=1 |
| Nhiều SELECT cần cùng snapshot | START TRANSACTION + REPEATABLE READ |
| Mỗi SELECT trong một transaction cần thấy commit mới | READ COMMITTED |
| Chuyển tiền hoặc cập nhật nhiều bảng phải cùng thành công | START TRANSACTION, COMMIT/ROLLBACK |
| Đọc hàng rồi cập nhật dựa trên giá trị vừa đọc | Transaction + SELECT ... FOR UPDATE phù hợp |
| Muốn bảo vệ dữ liệu khỏi dirty read | Không dùng READ UNCOMMITTED |
| Chỉ cần isolation khác cho một transaction | SET TRANSACTION trước transaction |
| Ứng dụng dùng connection pool | Quản lý và reset autocommit/isolation rõ ràng |

Không có cấu hình tốt nhất cho mọi ứng dụng. Chọn isolation level và ranh giới transaction theo yêu cầu nhất quán, mức concurrency, thời gian transaction và chi phí khóa.

## 15. Quan sát trạng thái transaction đang mở

Khi autocommit=0, một session có thể giữ transaction lâu mà ứng dụng không nhận ra. Có thể xem các transaction InnoDB:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Tìm connection theo thread ID:

~~~sql
SHOW PROCESSLIST;
~~~

Các dấu hiệu cần chú ý:
- Transaction có thời gian bắt đầu quá lâu.
- Transaction đang idle nhưng chưa commit.
- Truy vấn giữ khóa hoặc chờ khóa.
- Một read view cũ tồn tại lâu, cản trở purge undo history.

Không phải transaction dài nào cũng sai; một báo cáo cần snapshot nhất quán có thể chạy lâu. Nhưng cần giới hạn thời gian, số hàng và tài nguyên để không ảnh hưởng hệ thống.

## 16. Quy trình chẩn đoán khi kết quả đọc khác kỳ vọng

Khi hai câu SELECT trả kết quả khác nhau, kiểm tra theo thứ tự:

1. Hai SELECT có chạy trên cùng connection không?
2. \`@@session.autocommit\` đang là 0 hay 1?
3. Có transaction tường minh đang mở không?
4. Isolation level của session là gì?
5. Hai câu SELECT có phải consistent read thông thường hay locking read?
6. Transaction khác đã COMMIT ở thời điểm nào?
7. Read view được tạo ở lần consistent read nào?
8. Có DDL hoặc lệnh gây implicit commit xen giữa không?
9. Có thay đổi isolation level cho transaction kế tiếp hay session không?
10. Connection pool có trả lại connection với trạng thái session cũ không?

Các truy vấn kiểm tra nhanh:

~~~sql
SELECT
    CONNECTION_ID() AS connection_id,
    @@session.autocommit AS autocommit,
    @@session.transaction_isolation AS isolation_level,
    @@session.in_transaction AS in_transaction;
~~~

\`@@session.in_transaction\` cho biết session có đang ở trong transaction hay không trên các phiên bản MySQL hỗ trợ biến này. Nếu phiên bản đích không hỗ trợ, kiểm tra trạng thái qua công cụ quản trị và \`information_schema.innodb_trx\`.

## 17. Bài thực hành hai session

Các bài sau dùng bảng \`account_mvcc_demo\` ở mục 3. Chạy trên môi trường thử nghiệm và đặt lại balance sau mỗi bài để kết quả dễ so sánh.

### Bài 1: Autocommit=1 và REPEATABLE READ

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B:
~~~sql
UPDATE account_mvcc_demo
SET balance = balance + 100
WHERE account_id = 1;
~~~

Session A chạy SELECT lần nữa. Ghi lại vì sao lần đọc thứ hai thấy thay đổi.

### Bài 2: Autocommit=1 với transaction tường minh

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B cập nhật và commit. Session A đọc lại trước COMMIT. So sánh kết quả với Bài 1. Sau đó COMMIT và SELECT lại.

### Bài 3: Autocommit=0

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 0;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B cập nhật và commit. Session A đọc lại, sau đó COMMIT và đọc lần nữa. Xác định thời điểm snapshot thay đổi.

### Bài 4: READ COMMITTED

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B cập nhật và commit. Session A đọc lại trong cùng transaction. Giải thích vì sao lần đọc thứ hai có thể thấy giá trị mới.

### Bài 5: Consistent read và locking read

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1
FOR UPDATE;
~~~

Trong lúc A đang mở transaction, Session B thử UPDATE cùng hàng. Quan sát giá trị đọc và thời gian chờ khóa. Sau bài thực hành, COMMIT hoặc ROLLBACK cả hai session.

### Bài 6: Chuyển autocommit từ 0 sang 1

Session A:
~~~sql
SET autocommit = 0;

UPDATE account_mvcc_demo
SET balance = balance + 50
WHERE account_id = 1;

SET autocommit = 1;
~~~

Session B đọc balance. Xác nhận thay đổi đã được commit khi autocommit chuyển từ 0 sang 1.

### Bài 7: Báo cáo nhiều câu SELECT

Tạo transaction B cập nhật hai nhóm dữ liệu và commit giữa hai SELECT của Session A. So sánh:
- Hai SELECT riêng với autocommit=1.
- Hai SELECT trong một transaction REPEATABLE READ.
- Hai SELECT trong một transaction READ COMMITTED.

Ghi lại trường hợp nào cần dùng khi báo cáo phải nhất quán tại cùng một snapshot.

## 18. Checklist trước khi triển khai

- [ ] Đã phân biệt autocommit với transaction isolation level.
- [ ] Đã biết autocommit=1 làm mỗi statement độc lập tự commit.
- [ ] Đã biết START TRANSACTION vẫn tạo transaction nhiều statement khi autocommit=1.
- [ ] Đã biết autocommit=0 giữ transaction cho đến COMMIT/ROLLBACK.
- [ ] Đã hiểu snapshot REPEATABLE READ được tạo ở consistent read đầu tiên.
- [ ] Đã phân biệt REPEATABLE READ với READ COMMITTED trong cùng transaction.
- [ ] Đã phân biệt consistent read với locking/current read.
- [ ] Đã hiểu FOR UPDATE/FOR SHARE cần transaction phù hợp để giữ khóa qua nhiều statement.
- [ ] Đã không dùng SERIALIZABLE mà chưa đánh giá lock contention.
- [ ] Đã biết cách đặt isolation level ở SESSION hoặc cho transaction kế tiếp.
- [ ] Đã hiểu chuyển autocommit từ 0 sang 1 có thể commit transaction đang mở.
- [ ] Đã tránh transaction dài khi autocommit=0.
- [ ] Đã dùng transaction tường minh cho thao tác nhiều bước cần atomicity.
- [ ] Đã quản lý trạng thái connection trong JDBC và connection pool.
- [ ] Đã kiểm thử với hai session trên InnoDB và đúng phiên bản MySQL.
- [ ] Đã kiểm tra transaction đang mở và read view lâu khi chẩn đoán vận hành.

## 19. Kết luận

Autocommit và isolation level giải quyết hai khía cạnh khác nhau của giao dịch. Autocommit xác định ranh giới transaction; isolation level xác định cách transaction nhìn thấy dữ liệu và phối hợp khóa. Vì vậy, REPEATABLE READ không bảo đảm hai SELECT độc lập luôn thấy cùng dữ liệu khi autocommit=1: mỗi SELECT là một transaction mới với read view riêng.

Nếu cần nhiều câu đọc cùng snapshot, hãy dùng transaction tường minh hoặc autocommit=0 với quản lý COMMIT/ROLLBACK rõ ràng. Nếu dùng READ COMMITTED, mỗi consistent read có thể thấy commit mới ngay cả trong transaction đang mở. Khi cần đọc rồi ghi dựa trên cùng hàng, cân nhắc locking read trong transaction. Cuối cùng, quản lý connection pool cẩn thận vì autocommit và isolation là trạng thái theo session; một connection không được reset có thể làm request tiếp theo quan sát dữ liệu khác kỳ vọng.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – InnoDB Autocommit, Commit, and Rollback](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual – SET TRANSACTION Statement](https://dev.mysql.com/doc/refman/8.4/en/set-transaction.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [MySQL 8.4 Reference Manual – Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual – Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
- [MySQL 8.4 Reference Manual – InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/8.4/en/innodb-multi-versioning.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual – System Variable autocommit](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_autocommit)
- [MySQL 8.4 Reference Manual – Transaction Isolation System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_transaction_isolation)

