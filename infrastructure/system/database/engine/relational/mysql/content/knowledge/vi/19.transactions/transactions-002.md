# START TRANSACTION, BEGIN, COMMIT và ROLLBACK

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích transaction và lý do cần gom nhiều câu SQL thành một đơn vị công việc.
- Bắt đầu transaction bằng `START TRANSACTION` hoặc `BEGIN`.
- Dùng `COMMIT` để xác nhận thay đổi và `ROLLBACK` để hủy thay đổi chưa commit.
- Phân biệt transaction tường minh với chế độ `autocommit` mặc định của MySQL.
- Xác định những thao tác nào thực sự có thể rollback dựa trên storage engine.
- Nhận diện các câu lệnh gây implicit commit và tránh phá vỡ ranh giới transaction.
- Dùng savepoint khi cần rollback một phần công việc.
- Quản lý transaction đúng cách trong Java JDBC và connection pool.
- Thiết kế quy trình ghi dữ liệu có kiểm tra lỗi, khóa và khả năng khôi phục.

## 1. Transaction là gì?

Transaction (giao dịch) là một đơn vị công việc gồm một hoặc nhiều câu lệnh SQL được xử lý như một nhóm. Với bảng dùng storage engine có hỗ trợ transaction như InnoDB, ứng dụng có thể xác nhận toàn bộ thay đổi bằng `COMMIT` hoặc hủy các thay đổi chưa commit bằng `ROLLBACK`.

Ví dụ, chuyển 500.000 đồng từ tài khoản A sang tài khoản B cần ít nhất hai thao tác:

1. Trừ 500.000 đồng khỏi tài khoản A.
2. Cộng 500.000 đồng vào tài khoản B.

Nếu chỉ trừ tiền thành công nhưng thao tác cộng tiền thất bại, dữ liệu sẽ sai. Transaction giúp hai thay đổi được commit cùng nhau hoặc bị rollback cùng nhau, miễn là chúng được thực hiện trên các bảng hỗ trợ transaction trong cùng transaction.

### 1.1. Liên hệ với ACID

Transaction trong InnoDB hỗ trợ các thuộc tính ACID:

| Thuộc tính | Ý nghĩa |
|---|---|
| Atomicity | Các thay đổi trong transaction được xác nhận cùng nhau hoặc bị hủy khi rollback |
| Consistency | Transaction phải đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo các constraint và quy tắc nghiệp vụ được áp dụng |
| Isolation | Các transaction đồng thời được kiểm soát theo isolation level và cơ chế khóa/đọc nhất quán |
| Durability | Sau khi commit thành công, thay đổi được bảo vệ theo cấu hình durability của server và storage |

Transaction không tự đảm bảo mọi quy tắc nghiệp vụ. Ứng dụng vẫn cần kiểm tra số dư, quyền sở hữu, trạng thái đơn hàng và các điều kiện khác. Constraint trong database nên được dùng để bảo vệ những quy tắc có thể diễn đạt ở schema.

## 2. Bắt đầu transaction bằng START TRANSACTION

`START TRANSACTION` bắt đầu một transaction tường minh trên connection hiện tại.

Cú pháp cơ bản:

```sql
START TRANSACTION;

-- Một hoặc nhiều câu lệnh SQL
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100000
WHERE account_id = 202;

COMMIT;
```

Các thay đổi được thực hiện trong transaction cho đến khi câu lệnh kết thúc transaction bằng `COMMIT` hoặc `ROLLBACK`, hoặc một sự kiện implicit commit xảy ra.

Có thể viết:

```sql
START TRANSACTION;
```

Đây là cách rõ ràng và phổ biến khi bắt đầu một nhóm thao tác ghi.

### 2.1. BEGIN là cách viết tương đương

Trong MySQL, `BEGIN` hoặc `BEGIN WORK` có thể dùng để bắt đầu transaction và tương đương `START TRANSACTION` trong ngữ cảnh SQL thông thường:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;

COMMIT;
```

`START TRANSACTION` thường dễ nhận biết hơn khi đọc mã SQL vì nêu rõ ý định bắt đầu transaction.

Lưu ý: trong stored program, `BEGIN ... END` còn được dùng để mở/đóng một khối lệnh ghép. Khi viết procedure, function hoặc trigger, cần phân biệt cú pháp khối lệnh với câu lệnh điều khiển transaction; không thay thế máy móc mọi `BEGIN` bằng `START TRANSACTION`.

### 2.2. Không có transaction lồng nhau theo cách thông thường

MySQL không hỗ trợ transaction lồng nhau độc lập. Gọi `START TRANSACTION` khi một transaction khác đang mở sẽ kết thúc transaction hiện tại bằng implicit commit rồi bắt đầu transaction mới. Điều này có thể khiến các thay đổi trước đó được commit ngoài dự kiến.

Không dùng `START TRANSACTION` bên trong một transaction với ý nghĩ nó tạo một transaction con. Nếu cần hoàn tác một phần công việc, hãy dùng `SAVEPOINT` và `ROLLBACK TO SAVEPOINT`.

## 3. COMMIT xác nhận thay đổi

`COMMIT` kết thúc transaction hiện tại và xác nhận các thay đổi của transaction.

```sql
START TRANSACTION;

UPDATE products
SET stock_quantity = stock_quantity - 2
WHERE product_id = 501;

INSERT INTO inventory_movements (
    product_id,
    quantity_change,
    movement_type,
    created_at
)
VALUES (
    501,
    -2,
    'SALE',
    CURRENT_TIMESTAMP
);

COMMIT;
```

Nếu các câu lệnh thành công và `COMMIT` thành công, thay đổi được xác nhận. Với InnoDB, transaction kết thúc và các khóa được giữ bởi transaction được giải phóng theo quy tắc engine.

### 3.1. COMMIT không có nghĩa là mọi thao tác trước đó đều đúng nghiệp vụ

MySQL commit những thay đổi đã được thực hiện hợp lệ trong transaction. Nó không tự biết rằng số lượng kho bị âm là sai, rằng tài khoản nguồn và đích phải khác nhau, hay rằng đơn hàng không được thanh toán hai lần.

Ứng dụng phải kiểm tra kết quả từng thao tác trước khi commit. Nếu điều kiện nghiệp vụ không thỏa, hãy rollback.

### 3.2. Commit là ranh giới không thể rollback bằng ROLLBACK thông thường

Sau khi `COMMIT` thành công, một câu `ROLLBACK` tiếp theo không thể hủy transaction đã commit:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 100 WHERE account_id = 101;
COMMIT;

-- Không hoàn tác được thay đổi đã commit ở trên
ROLLBACK;
```

Muốn đảo ngược một nghiệp vụ đã commit, ứng dụng phải thực hiện một transaction bù (compensating transaction), ví dụ ghi một giao dịch hoàn tiền mới. Đây là thay đổi nghiệp vụ mới, không phải rollback transaction cũ.

## 4. ROLLBACK hủy thay đổi chưa commit

`ROLLBACK` kết thúc transaction hiện tại và hủy các thay đổi transactional chưa được commit.

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

-- Phát hiện tài khoản đích không hợp lệ hoặc điều kiện nghiệp vụ thất bại
ROLLBACK;
```

Sau rollback, các thay đổi InnoDB trong transaction này được hoàn tác. Các khóa do transaction giữ cũng được giải phóng.

### 4.1. ROLLBACK không xóa mọi dấu vết của câu lệnh

Rollback không có nghĩa mọi thứ trong hệ thống trở về trạng thái ban đầu ở mọi khía cạnh:

- Các thay đổi trên bảng transactional như InnoDB được hoàn tác.
- Thay đổi trên bảng không hỗ trợ transaction như MyISAM không được hoàn tác.
- Một số bộ đếm hoặc giá trị sinh tự động có thể không quay lại số cũ; không dựa vào việc ID phải liên tục.
- Tác động bên ngoài MySQL như gửi email, gọi API, ghi file hoặc phát thông điệp tới hệ thống khác không được rollback bởi transaction database.
- Các câu lệnh gây implicit commit có thể đã kết thúc transaction trước đó.

Vì vậy, cần kiểm tra storage engine của tất cả bảng tham gia và tránh đặt tác vụ bên ngoài database giữa một nhóm thay đổi mà ứng dụng đang kỳ vọng có thể rollback toàn bộ.

### 4.2. ROLLBACK khi có lỗi

Ứng dụng nên xử lý exception theo nguyên tắc: nếu chưa commit thành công thì rollback transaction trước khi trả connection về pool hoặc kết thúc xử lý.

Không bỏ qua lỗi rollback. Nếu rollback thất bại do connection đã mất hoặc server không còn truy cập được, ứng dụng cần loại bỏ connection khỏi pool và xử lý trạng thái kết quả theo hướng có thể chưa xác định.

## 5. Autocommit trong MySQL

### 5.1. Mặc định autocommit = 1

MySQL thường khởi động với `autocommit` bật:

```sql
SELECT @@SESSION.autocommit;
```

Khi `autocommit = 1`, mỗi câu lệnh SQL độc lập được thực hiện như một transaction riêng nếu storage engine hỗ trợ transaction. Nếu câu lệnh thành công, thay đổi được commit khi câu lệnh kết thúc; nếu câu lệnh thất bại, thay đổi transactional của câu lệnh đó bị hủy.

Ví dụ:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

Nếu không mở transaction tường minh và autocommit đang bật, câu UPDATE trên tự commit khi thành công. Một UPDATE tiếp theo là một transaction khác.

### 5.2. START TRANSACTION tạo transaction tường minh dù autocommit bật

Không cần tắt autocommit để dùng transaction:

```sql
SELECT @@SESSION.autocommit; -- thường là 1

START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;

COMMIT;
```

Hai câu UPDATE nằm trong cùng transaction tường minh và chỉ được xác nhận khi commit. Sau khi transaction kết thúc, session trở lại chế độ autocommit ban đầu.

Đây thường là cách nên dùng cho một đơn vị nghiệp vụ gồm nhiều câu SQL.

### 5.3. Tắt autocommit ở cấp session

Có thể tắt autocommit:

```sql
SET SESSION autocommit = 0;
```

Khi đó, thay đổi không tự commit sau mỗi câu lệnh. Ứng dụng cần chủ động gọi `COMMIT` hoặc `ROLLBACK`. Sau khi transaction kết thúc, các câu lệnh tiếp theo lại thuộc một transaction mới theo chế độ autocommit đang tắt.

Kiểm tra và bật lại:

```sql
SELECT @@SESSION.autocommit;
SET SESSION autocommit = 1;
```

Chuyển `autocommit` từ 0 sang 1 gây commit transaction đang mở. Vì vậy, không bật lại một cách tùy tiện khi còn thay đổi chưa được xác nhận. Hãy commit hoặc rollback rõ ràng trước.

### 5.4. Nên dùng START TRANSACTION hay autocommit = 0?

Trong ứng dụng, transaction tường minh thường dễ kiểm soát hơn:

- Ranh giới bắt đầu/kết thúc hiện rõ trong code.
- Một request có thể dùng transaction cho đúng một nghiệp vụ.
- Giảm nguy cơ connection bị trả về pool khi vẫn còn transaction mở.
- Tránh giữ transaction mở ngoài ý muốn do session autocommit bị tắt.

`autocommit = 0` có thể phù hợp với một số công cụ hoặc quy trình tương tác, nhưng cần quản lý vòng đời session chặt chẽ.

## 6. Storage engine quyết định khả năng rollback

Transaction là khả năng của storage engine, không phải chỉ là một từ khóa SQL.

### 6.1. InnoDB hỗ trợ transaction

InnoDB là storage engine mặc định phổ biến của MySQL và hỗ trợ:

- `START TRANSACTION`, `COMMIT`, `ROLLBACK`.
- Row-level locking và các cơ chế kiểm soát đồng thời.
- Consistent read và nhiều isolation level.
- Foreign key và crash recovery.

Ví dụ kiểm tra engine:

```sql
SHOW TABLE STATUS
WHERE Name IN ('accounts', 'inventory_movements');

SELECT
    TABLE_NAME,
    ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts', 'inventory_movements');
```

Các bảng tham gia một nghiệp vụ cần dùng engine hỗ trợ transaction nếu muốn rollback toàn bộ thay đổi.

### 6.2. MyISAM không hỗ trợ rollback

MyISAM không hỗ trợ transaction theo cách của InnoDB. Nếu một transaction cập nhật bảng InnoDB rồi cập nhật bảng MyISAM, sau đó rollback:

- Thay đổi InnoDB được hoàn tác.
- Thay đổi MyISAM có thể vẫn còn.

Đây là lý do không nên trộn bảng transactional và nontransactional trong một nghiệp vụ cần atomicity.

### 6.3. Kiểm tra engine trước khi thiết kế transaction

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

Không chỉ kiểm tra bảng chính. Hãy kiểm tra cả bảng chi tiết, bảng lịch sử, bảng số dư, bảng tồn kho và mọi bảng được ghi trong cùng transaction.

## 7. Ví dụ đầy đủ: chuyển tiền giữa hai tài khoản

### 7.1. Schema minh họa

```sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(150) NOT NULL,
    balance DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_accounts_balance_nonnegative CHECK (balance >= 0)
) ENGINE = InnoDB;

CREATE TABLE account_transfers (
    transfer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    from_account_id BIGINT UNSIGNED NOT NULL,
    to_account_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transfer_id),
    CONSTRAINT chk_transfer_amount_positive CHECK (amount > 0),
    CONSTRAINT chk_transfer_accounts_different
        CHECK (from_account_id <> to_account_id)
) ENGINE = InnoDB;
```

Các `CHECK` constraint được thực thi trong MySQL 8.0.16 trở lên. Nếu dùng phiên bản cũ, cần xác minh hành vi và bổ sung kiểm tra ở ứng dụng hoặc cơ chế tương thích phù hợp.

### 7.2. Bắt đầu transaction và cập nhật có điều kiện

Ví dụ chuyển 500.000 đồng từ tài khoản 101 sang 202:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101
  AND balance >= 500000;

-- Ứng dụng phải kiểm tra ROW_COUNT() = 1.
-- Nếu khác 1: ROLLBACK và báo tài khoản nguồn không tồn tại/không đủ số dư.

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

-- Ứng dụng phải kiểm tra ROW_COUNT() = 1.
-- Nếu khác 1: ROLLBACK vì tài khoản đích không tồn tại.

INSERT INTO account_transfers (
    from_account_id,
    to_account_id,
    amount
)
VALUES (101, 202, 500000);

COMMIT;
```

Đoạn SQL trên mô tả thứ tự thao tác; phần kiểm tra số hàng ảnh hưởng là bắt buộc và phải do client/procedure điều khiển trước khi đi tiếp. Nếu bất kỳ bước nào không đạt điều kiện, transaction phải được rollback thay vì chạy tiếp tới `COMMIT`.

`UPDATE ... WHERE balance >= ...` giúp kiểm tra số dư và trừ tiền trong cùng một thao tác có khóa, tránh mẫu “đọc số dư ở ngoài transaction rồi cập nhật sau” dễ gặp race condition. Cần kiểm tra số hàng ảnh hưởng ngay sau UPDATE tương ứng; `ROW_COUNT()` có thể được dùng trong cùng session để quan sát kết quả câu lệnh vừa chạy.

### 7.3. Khóa hai tài khoản theo thứ tự nhất quán

Nếu nghiệp vụ cần đọc thông tin hai tài khoản trước khi cập nhật, có thể khóa các hàng bằng `SELECT ... FOR UPDATE` trong transaction:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng xác minh đủ hai tài khoản, số dư và quy tắc nghiệp vụ.
-- Sau đó thực hiện UPDATE/INSERT và COMMIT; nếu không hợp lệ thì ROLLBACK.
```

Sắp xếp khóa theo cùng một thứ tự ở các luồng chuyển tiền giúp giảm nguy cơ deadlock khi hai giao dịch chuyển tiền ngược chiều. Đây không phải bảo đảm không có deadlock; ứng dụng vẫn phải xử lý lỗi deadlock và thử lại transaction phù hợp.

### 7.4. Vì sao không gửi COMMIT bất kể kết quả?

Nếu tài khoản nguồn không đủ tiền, UPDATE đầu tiên có thể ảnh hưởng 0 hàng. Nếu ứng dụng vẫn cộng tiền vào tài khoản đích rồi commit, hệ thống tạo tiền không có nguồn. Vì vậy, commit chỉ được gọi sau khi tất cả bước đã thành công và các điều kiện nghiệp vụ đều được xác nhận.

## 8. Savepoint: rollback một phần transaction

Savepoint đánh dấu một vị trí bên trong transaction. Có thể rollback về savepoint để hủy những thay đổi sau mốc đó mà vẫn giữ các thay đổi trước mốc.

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 5
WHERE product_id = 100;

SAVEPOINT after_inventory_update;

INSERT INTO shipment_items (shipment_id, product_id, quantity)
VALUES (9001, 100, 5);

-- Nếu bước ghi shipment item thất bại theo nghiệp vụ:
ROLLBACK TO SAVEPOINT after_inventory_update;

-- Có thể tiếp tục xử lý trong transaction, hoặc rollback toàn bộ.
COMMIT;
```

Trong ví dụ, `ROLLBACK TO SAVEPOINT` hủy thay đổi sau savepoint nhưng giữ cập nhật tồn kho trước savepoint. Điều đó chỉ đúng nếu nghiệp vụ thực sự muốn giữ cập nhật tồn kho; trong quy trình xuất kho thông thường, hai thay đổi thường phải đi cùng nhau, vì vậy lỗi ở bước thứ hai có thể cần `ROLLBACK` toàn bộ.

Các lệnh liên quan:

```sql
SAVEPOINT savepoint_name;
ROLLBACK TO SAVEPOINT savepoint_name;
RELEASE SAVEPOINT savepoint_name;
```

`COMMIT` hoặc `ROLLBACK` toàn transaction xóa các savepoint. Savepoint không tạo transaction lồng nhau và không thể rollback phần thay đổi đã commit.

## 9. Những câu lệnh gây implicit commit

Một số câu lệnh trong MySQL tự commit transaction hiện tại trước khi thực hiện hoặc theo quy tắc implicit commit. Điều này đặc biệt quan trọng khi trộn DDL và DML.

Ví dụ nguy hiểm:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

ALTER TABLE accounts ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
```

`ALTER TABLE` là DDL gây implicit commit trong MySQL. Thay đổi UPDATE trước đó có thể đã được commit trước khi ALTER thực thi; câu ROLLBACK sau đó không thể hủy UPDATE đã commit.

### 9.1. Một số nhóm câu lệnh cần chú ý

Các lệnh thường gây implicit commit gồm:

- DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, `TRUNCATE TABLE`.
- Các thao tác schema/database/index như `CREATE DATABASE`, `DROP DATABASE`, `CREATE INDEX`, `DROP INDEX`.
- Một số lệnh quản trị và khóa bảng như `LOCK TABLES`.
- `SET autocommit = 1` khi giá trị thay đổi từ 0 sang 1.
- `START TRANSACTION` khi đã có transaction đang mở sẽ kết thúc transaction hiện tại trước khi bắt đầu transaction mới.

Danh sách chính xác có ngoại lệ và khác biệt theo câu lệnh/phiên bản; hãy kiểm tra tài liệu MySQL của phiên bản triển khai trước khi thiết kế migration.

### 9.2. Temporary table là ngoại lệ cần hiểu đúng

`CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` không gây implicit commit theo cách của DDL thông thường. Tuy nhiên, thao tác tạo/xóa temporary table không thể được rollback như thay đổi dữ liệu InnoDB thông thường. Vì vậy, “không implicit commit” không có nghĩa “có thể rollback hoàn toàn”.

### 9.3. Tách migration khỏi transaction nghiệp vụ

Không đặt DDL schema migration vào giữa transaction xử lý đơn hàng, chuyển tiền hoặc tồn kho. Nên chạy migration theo quy trình triển khai riêng, có kiểm tra tương thích, backup và đánh giá metadata lock.

## 10. Transaction và connection

Transaction gắn với connection/session MySQL. Mọi câu lệnh thuộc một transaction phải chạy trên cùng một connection vật lý.

Ví dụ sai về mặt ý tưởng:

1. Connection A chạy `START TRANSACTION`.
2. Connection B chạy `UPDATE`.
3. Connection A chạy `COMMIT`.

UPDATE ở connection B không thuộc transaction của connection A. `COMMIT` chỉ kết thúc transaction trên connection A.

Điều này đặc biệt quan trọng khi dùng connection pool. Không được lấy một connection để bắt đầu transaction, trả nó về pool, rồi lấy connection khác để tiếp tục các câu lệnh.

### 10.1. Kết nối bị đóng khi transaction chưa commit

Nếu connection kết thúc khi InnoDB transaction còn mở, server rollback transaction chưa commit khi session được dọn dẹp. Ứng dụng không nên dựa vào việc đóng connection như cách điều khiển transaction bình thường; hãy commit hoặc rollback tường minh.

### 10.2. Mất kết nối trong lúc COMMIT

Nếu client mất kết nối đúng lúc gửi `COMMIT`, ứng dụng có thể không biết server đã commit hay chưa. Không nên mặc định rằng “không nhận được phản hồi” đồng nghĩa transaction đã rollback.

Với nghiệp vụ có thể retry như tạo đơn hoặc chuyển tiền, hãy thiết kế idempotency key hoặc mã giao dịch duy nhất để truy vấn trạng thái sau khi kết nối lại, tránh thực hiện nghiệp vụ hai lần.

## 11. Transaction trong Java JDBC

JDBC cung cấp `Connection.setAutoCommit(false)`, `commit()` và `rollback()` để quản lý transaction.

Ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean originalAutoCommit = connection.getAutoCommit();
    boolean transactionClean = false;
    Throwable failure = null;

    try {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE accounts "
                  + "SET balance = balance - ? "
                  + "WHERE account_id = ? AND balance >= ?")) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccountId);
                debit.setBigDecimal(3, amount);

                if (debit.executeUpdate() != 1) {
                    throw new IllegalStateException(
                        "Tài khoản nguồn không tồn tại hoặc không đủ số dư");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? "
                  + "WHERE account_id = ?")) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccountId);

                if (credit.executeUpdate() != 1) {
                    throw new IllegalStateException(
                        "Tài khoản đích không tồn tại");
                }
            }

            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO account_transfers "
                  + "(from_account_id, to_account_id, amount) "
                  + "VALUES (?, ?, ?)")) {
                insert.setLong(1, fromAccountId);
                insert.setLong(2, toAccountId);
                insert.setBigDecimal(3, amount);
                insert.executeUpdate();
            }

            connection.commit();
            transactionClean = true;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
                transactionClean = true;
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    } catch (SQLException | RuntimeException ex) {
        failure = ex;
        throw ex;
    } finally {
        if (transactionClean) {
            try {
                connection.setAutoCommit(originalAutoCommit);
            } catch (SQLException resetError) {
                // Không tái sử dụng connection nếu việc reset trạng thái thất bại.
                if (failure != null) {
                    failure.addSuppressed(resetError);
                } else {
                    // Invalidate connection bằng API của pool trước khi close.
                    throw resetError;
                }
            }
        } else {
            // Trạng thái transaction không xác định: evict connection bằng API của pool.
        }
    }
}
```

Ví dụ minh họa cách quản lý transaction trên cùng connection:

- Tắt autocommit trước khi thực hiện nhóm câu lệnh.
- Dùng prepared statement cho giá trị đầu vào.
- Kiểm tra số hàng cập nhật ở cả tài khoản nguồn và đích.
- Chỉ commit sau khi mọi thao tác thành công.
- Rollback khi gặp lỗi SQL hoặc lỗi nghiệp vụ.
- Khôi phục trạng thái autocommit trước khi connection được trả về pool.

Trong code production, nếu rollback hoặc reset autocommit thất bại, connection có trạng thái không xác định và phải được loại khỏi pool bằng API invalidate/evict của pool đang dùng. JDBC chuẩn không cung cấp một API evict chung cho mọi connection pool; không trả connection lỗi về pool để tái sử dụng. Nếu reset autocommit thất bại, hãy giữ lỗi đó cùng exception gốc bằng suppressed exception hoặc cơ chế logging phù hợp.

### 11.1. Không gọi commit trên connection khác

Tất cả prepared statement trong transaction phải được tạo và thực thi trên cùng `Connection`. Mở một connection mới bên trong service để chạy một câu lệnh phụ sẽ đưa câu lệnh đó ra khỏi transaction hiện tại.

### 11.2. Đừng giữ transaction mở trong lúc chờ người dùng

Không mở transaction rồi chờ người dùng xác nhận trên giao diện, chờ nhập OTP hoặc chờ một HTTP request khác. Transaction dài giữ khóa và snapshot, làm tăng nguy cơ lock wait, deadlock và undo history lớn. Hãy tách bước xác nhận thành quy trình nghiệp vụ phù hợp, dùng trạng thái trung gian hoặc cơ chế reservation khi cần.

## 12. Isolation, khóa và transaction ngắn

`COMMIT` và `ROLLBACK` xác định ranh giới transaction; isolation level quyết định cách các transaction đồng thời nhìn thấy dữ liệu và tương tác với nhau.

Kiểm tra isolation level:

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation;
```

Tên biến và giá trị được hỗ trợ phụ thuộc phiên bản MySQL. Các isolation level InnoDB thường gặp gồm `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`.

Ví dụ khóa hàng để cập nhật:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Kiểm tra điều kiện và thực hiện cập nhật trong cùng transaction.

COMMIT;
```

`FOR UPDATE` là locking read trên InnoDB. Khóa được giữ tới khi transaction kết thúc. Cần có index phù hợp để tránh khóa phạm vi rộng ngoài dự kiến.

Một transaction nên:

- Chỉ bao gồm những thao tác cần atomicity cùng nhau.
- Giữ thời gian ngắn nhất có thể.
- Truy cập các hàng theo thứ tự nhất quán ở các luồng cạnh tranh.
- Có index cho điều kiện lọc và khóa.
- Xử lý deadlock bằng cách rollback và retry toàn bộ đơn vị nghiệp vụ khi phù hợp.

Không dùng `COMMIT` sớm chỉ để giải phóng khóa nếu điều đó phá vỡ atomicity của nghiệp vụ. Hãy thiết kế lại ranh giới transaction nếu transaction quá dài.

## 13. Deadlock và lỗi trong transaction

Hai transaction có thể giữ khóa mà transaction kia cần, tạo thành chu trình chờ (deadlock). InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback.

Khi gặp deadlock:

1. Bắt lỗi từ MySQL/JDBC.
2. Coi transaction bị chọn làm nạn nhân đã thất bại.
3. Rollback/đảm bảo connection ở trạng thái sạch.
4. Nếu nghiệp vụ có thể retry, bắt đầu transaction mới và thử lại toàn bộ thao tác với giới hạn số lần và backoff phù hợp.
5. Ghi log khóa, câu lệnh và định danh nghiệp vụ để điều tra.

Không chỉ chạy lại câu SQL cuối cùng trong transaction đã thất bại. Cần lặp lại toàn bộ đơn vị công việc vì trạng thái đọc và các thay đổi trước đó có thể không còn hiệu lực.

Lock wait timeout khác deadlock. Tùy cấu hình `innodb_rollback_on_timeout`, timeout có thể chỉ rollback câu lệnh hiện tại hoặc rollback toàn transaction. Ứng dụng cần xử lý rõ ràng bằng rollback toàn transaction trước khi tái sử dụng connection, thay vì giả định mọi lỗi đều có cùng phạm vi rollback.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách làm đúng |
|---|---|---|
| Mỗi câu UPDATE luôn cần START TRANSACTION | Với autocommit bật, một câu lệnh InnoDB đã là transaction riêng | Chỉ mở transaction tường minh khi nhiều thao tác cần cùng commit/rollback |
| BEGIN tạo transaction lồng nhau | MySQL không hỗ trợ nested transaction thông thường | Dùng savepoint cho rollback một phần |
| ROLLBACK hoàn tác mọi thứ | Chỉ hoàn tác thay đổi transactional chưa commit; không hoàn tác external side effect hoặc bảng MyISAM | Kiểm tra engine và tách tác vụ bên ngoài |
| COMMIT có thể được rollback sau đó | Commit đã kết thúc transaction; ROLLBACK tiếp theo không đảo ngược nó | Dùng transaction bù nếu cần đảo nghiệp vụ |
| DDL có thể chạy giữa transaction rồi rollback | Nhiều DDL gây implicit commit | Tách schema migration khỏi transaction nghiệp vụ |
| Tắt autocommit là cách duy nhất để dùng transaction | START TRANSACTION hoạt động khi autocommit bật | Dùng transaction tường minh theo từng đơn vị công việc |
| Transaction có thể tiếp tục trên connection khác | Transaction gắn với session/connection | Dùng cùng connection vật lý tới COMMIT/ROLLBACK |
| Mất phản hồi COMMIT nghĩa là rollback | Trạng thái commit có thể không xác định với client | Thiết kế idempotency và kiểm tra trạng thái giao dịch |
| Deadlock chỉ cần chạy lại câu lệnh cuối | Transaction nạn nhân đã bị rollback | Retry toàn bộ transaction theo chính sách |

## 15. Bộ truy vấn kiểm tra nhanh

```sql
-- Kiểm tra autocommit và isolation level
SELECT
    @@SESSION.autocommit AS session_autocommit,
    @@SESSION.transaction_isolation AS session_isolation;

-- Bắt đầu transaction và cập nhật dữ liệu thử nghiệm
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

-- Kiểm tra thay đổi trong chính transaction
SELECT product_id, quantity
FROM inventory
WHERE product_id = 100;

-- Chọn một trong hai lệnh kết thúc:
-- COMMIT;
-- ROLLBACK;

-- Kiểm tra storage engine
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE();
```

Các truy vấn dùng `inventory` và `product_id` làm ví dụ. Chỉ chạy phần cập nhật trên dữ liệu thử nghiệm và phải chọn rõ `COMMIT` hoặc `ROLLBACK` trước khi kết thúc session.

## 16. Checklist trước khi đưa transaction vào production

- [ ] Đã xác định chính xác các thao tác phải commit hoặc rollback cùng nhau.
- [ ] Tất cả bảng tham gia đều dùng storage engine hỗ trợ transaction, thường là InnoDB.
- [ ] Đã kiểm tra `@@SESSION.autocommit` và không giả định cấu hình session.
- [ ] Transaction được bắt đầu và kết thúc tường minh.
- [ ] Mọi câu lệnh trong transaction dùng cùng một connection.
- [ ] Đã kiểm tra số hàng ảnh hưởng và điều kiện nghiệp vụ trước COMMIT.
- [ ] Không đặt DDL gây implicit commit giữa transaction.
- [ ] Savepoint chỉ dùng khi rollback một phần thực sự đúng nghiệp vụ.
- [ ] Transaction ngắn, có index cho điều kiện lọc/khóa và thứ tự truy cập hàng nhất quán.
- [ ] Có xử lý deadlock, lock wait timeout và lỗi rollback.
- [ ] Có idempotency hoặc cách xác minh trạng thái khi mất kết nối trong lúc COMMIT.
- [ ] Connection được reset hoặc loại khỏi pool nếu trạng thái transaction không xác định.
- [ ] External side effect được điều phối riêng, không giả định ROLLBACK có thể hoàn tác chúng.

## 17. Kết luận

`START TRANSACTION` hoặc `BEGIN` mở một transaction tường minh; `COMMIT` xác nhận thay đổi; `ROLLBACK` hủy thay đổi transactional chưa commit. Với `autocommit = 1`, mỗi câu lệnh độc lập thường tự commit, nhưng nhiều câu lệnh vẫn có thể được gom vào cùng transaction mà không cần tắt autocommit.

Khả năng rollback phụ thuộc storage engine. InnoDB hỗ trợ transaction; MyISAM không cung cấp rollback tương đương. Một số DDL gây implicit commit, transaction gắn với một connection và không thể rollback tác động bên ngoài database. Hãy xác định ranh giới nghiệp vụ rõ ràng, kiểm tra mọi bước trước khi commit, xử lý lỗi/deadlock và giữ transaction ngắn để dữ liệu vừa nhất quán vừa vận hành ổn định.
