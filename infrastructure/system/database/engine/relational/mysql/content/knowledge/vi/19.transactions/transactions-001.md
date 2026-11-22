# Đơn vị công việc nghiệp vụ và các thuộc tính ACID

Transaction (giao dịch) là một đơn vị công việc gồm một hoặc nhiều thao tác đọc/ghi dữ liệu được xử lý như một phần thống nhất. Khi giao dịch thành công, các thay đổi được xác nhận bằng `COMMIT`; khi cần hủy trước lúc xác nhận, có thể dùng `ROLLBACK`. Với storage engine hỗ trợ transaction như InnoDB, cơ chế này giúp nhiều thao tác liên quan cùng thành công hoặc cùng bị hủy, đồng thời kiểm soát ảnh hưởng giữa các giao dịch chạy đồng thời.

Một transaction tốt thường tương ứng với một đơn vị nghiệp vụ hoàn chỉnh: chuyển tiền giữa hai tài khoản, tạo đơn hàng cùng các dòng hàng và trừ tồn kho, hoặc ghi nhận thanh toán cùng trạng thái hóa đơn. Các thao tác phải nằm trong cùng transaction nếu hệ thống không được phép để lại trạng thái dở dang khi một bước thất bại.

ACID là bốn thuộc tính nền tảng để mô tả hành vi mong muốn của transaction: Atomicity (tính nguyên tử), Consistency (tính nhất quán), Isolation (tính cô lập) và Durability (tính bền vững). MySQL InnoDB cung cấp các cơ chế quan trọng để thực hiện những thuộc tính này, nhưng ứng dụng vẫn phải xác định đúng ranh giới nghiệp vụ, kiểm tra điều kiện và xử lý lỗi.

## 1. Transaction là một đơn vị công việc nghiệp vụ

Hãy xét thao tác chuyển 100.00 từ tài khoản A sang tài khoản B. Về nghiệp vụ, đây là một hành động duy nhất nhưng cần nhiều thao tác dữ liệu:

1. Kiểm tra hai tài khoản tồn tại và có thể giao dịch.
2. Kiểm tra tài khoản A đủ số dư.
3. Trừ 100.00 khỏi A.
4. Cộng 100.00 vào B.
5. Ghi nhận giao dịch vào sổ lịch sử.

Nếu chỉ trừ tiền A thành công nhưng cộng tiền B thất bại, hệ thống sẽ mất tiền. Nếu cộng tiền B thành công nhưng ghi lịch sử thất bại, dữ liệu đối soát không còn phản ánh đầy đủ giao dịch. Những bước này nên được thực hiện trong một transaction database để cùng commit hoặc rollback.

Ngược lại, không nên gộp mọi thao tác của một quy trình dài vào một transaction duy nhất. Gửi email, gọi cổng thanh toán bên ngoài hoặc chờ người dùng xác nhận có thể kéo dài và không thể rollback bằng `ROLLBACK` của MySQL. Ranh giới transaction nên bao quanh phần thay đổi dữ liệu cần tính nguyên tử trong cùng database.

## 2. Bốn thuộc tính ACID

ACID mô tả bốn đặc tính của một transaction đáng tin cậy:

| Thuộc tính | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Atomicity | Các thay đổi trong transaction được chấp nhận như một đơn vị; lỗi trước commit có thể hủy các thay đổi transactional | Nếu một bước thất bại, có để lại nửa giao dịch không? |
| Consistency | Transaction đưa dữ liệu từ trạng thái hợp lệ sang trạng thái hợp lệ theo các quy tắc đã định nghĩa | Sau giao dịch, các ràng buộc và bất biến nghiệp vụ còn đúng không? |
| Isolation | Các transaction đồng thời không được nhìn thấy những trạng thái trung gian trái với mức cô lập đã chọn | Hai người dùng thao tác cùng dữ liệu có gây kết quả sai không? |
| Durability | Khi commit được xác nhận thành công, thay đổi được bảo vệ trước các sự cố thuộc phạm vi bảo đảm của cấu hình lưu trữ | Sau khi server gặp sự cố, dữ liệu đã commit có còn không? |

ACID không có nghĩa mọi lỗi ứng dụng đều tự được sửa. Database có thể bảo đảm transaction atomic, nhưng ứng dụng vẫn phải kiểm tra số hàng bị ảnh hưởng, xử lý deadlock, xác định quy tắc nghiệp vụ và tránh gửi cùng một yêu cầu nhiều lần mà không có cơ chế idempotency.

## 3. Atomicity: tất cả hoặc không có gì

Atomicity bảo đảm các thay đổi transactional trong một transaction được xử lý như một đơn vị. Nếu transaction rollback, các thay đổi đã thực hiện trong transaction được hủy. Nếu commit thành công, toàn bộ thay đổi được xác nhận.

Ví dụ, tạo đơn hàng cần ghi bảng `orders` và `order_items`:

```sql
START TRANSACTION;

INSERT INTO orders (id, customer_id, total_amount, status)
VALUES (1001, 42, 250000.00, 'pending');

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 10, 2, 75000.00),
    (1001, 11, 1, 100000.00);

COMMIT;
```

Nếu một câu lệnh insert thất bại và ứng dụng quyết định hủy transaction, có thể chạy:

```sql
ROLLBACK;
```

Khi rollback thành công, hàng đơn hàng và các dòng hàng đã ghi trong transaction đều được hủy. Điều này chỉ đúng khi các bảng liên quan dùng storage engine hỗ trợ transaction, chẳng hạn InnoDB, và các thao tác chưa được commit.

Nếu một bảng dùng engine không transactional, thao tác ghi vào bảng đó không được bảo vệ bởi rollback giống InnoDB. Vì vậy, cần kiểm tra engine của các bảng thuộc cùng đơn vị nghiệp vụ.

## 4. Consistency: duy trì quy tắc dữ liệu và nghiệp vụ

Consistency nghĩa là transaction phải đưa database từ một trạng thái thỏa các quy tắc đã định nghĩa sang một trạng thái cũng thỏa các quy tắc đó. Quy tắc có thể được bảo vệ ở nhiều lớp:

- `PRIMARY KEY` và `UNIQUE` bảo đảm định danh hoặc giá trị không trùng theo quy tắc index.
- `FOREIGN KEY` bảo đảm quan hệ tham chiếu hợp lệ.
- `NOT NULL`, `CHECK` và kiểu dữ liệu giới hạn giá trị được phép.
- Logic ứng dụng kiểm tra các bất biến nghiệp vụ mà constraint không thể diễn đạt.
- Transaction gom các thao tác liên quan để không để lộ trạng thái trung gian.

Ví dụ, tài khoản không được có số dư âm. Có thể khai báo `CHECK (balance >= 0)` trên MySQL 8.0.16 trở lên, đồng thời vẫn cần cập nhật số dư có điều kiện và xử lý kết quả câu lệnh. Constraint không thay thế toàn bộ quy tắc chuyển tiền như hạn mức, trạng thái tài khoản hay quyền của người dùng.

Transaction không tự biết một quy tắc nghiệp vụ chưa được khai báo. Nếu ứng dụng quên kiểm tra một điều kiện và schema cũng không có constraint tương ứng, MySQL có thể commit một trạng thái sai theo nghiệp vụ nhưng vẫn hợp lệ theo cấu trúc database.

## 5. Isolation: kiểm soát ảnh hưởng giữa các transaction đồng thời

Nhiều kết nối có thể đọc và ghi cùng dữ liệu tại một thời điểm. Isolation quy định một transaction được phép quan sát dữ liệu của transaction khác ở mức nào và các thao tác cạnh tranh được điều phối ra sao.

Ví dụ, hai nhân viên cùng đặt sản phẩm cuối cùng trong kho. Nếu cả hai cùng đọc tồn kho là 1 rồi đều quyết định bán, hệ thống có thể ghi nhận hai đơn trong khi chỉ còn một sản phẩm. Cần dùng transaction, khóa hoặc cập nhật có điều kiện để bảo vệ bất biến tồn kho.

InnoDB kết hợp MVCC (multi-version concurrency control), khóa bản ghi và khóa phạm vi để thực hiện các mức cô lập. Một truy vấn đọc thông thường có thể đọc snapshot nhất quán mà không khóa các hàng như một locking read; thao tác cập nhật hoặc `SELECT ... FOR UPDATE` có thể lấy khóa để điều phối các transaction cạnh tranh.

## 6. Durability: dữ liệu đã commit được bảo vệ

Durability bảo đảm thay đổi của transaction đã commit được lưu bền vững theo cấu hình và phạm vi bảo đảm của hệ thống. InnoDB dùng redo log để phục hồi các thay đổi đã commit sau sự cố; cơ chế flush log và đồng bộ với hệ điều hành/phần cứng có ảnh hưởng đến mức bảo vệ thực tế.

Với cấu hình thường dùng để ưu tiên độ bền, `innodb_flush_log_at_trx_commit = 1` yêu cầu InnoDB flush và đồng bộ redo log xuống storage tại mỗi lần commit. Nếu đặt giá trị khác, có thể tăng hiệu năng nhưng chấp nhận một cửa sổ mất dữ liệu khi server hoặc hệ điều hành gặp sự cố. Thiết lập này cần được quyết định theo yêu cầu RPO và khả năng của storage.

Nếu binary log được dùng cho replication hoặc point-in-time recovery, `sync_binlog` cũng ảnh hưởng độ bền của binary log. Đồng bộ redo log và binary log là hai phần khác nhau; cần cấu hình nhất quán với yêu cầu khôi phục. Commit thành công trên primary cũng không tự động có nghĩa mọi replica bất đồng bộ đã nhận và áp dụng transaction.

Durability không thay thế backup, kiểm thử restore, replication hoặc kế hoạch khôi phục thảm họa. Nó bảo vệ transaction đã commit theo cơ chế lưu trữ, không bảo vệ khỏi người dùng xóa nhầm dữ liệu bằng một transaction hợp lệ rồi commit.

## 7. Điều kiện cần: dùng storage engine hỗ trợ transaction

Trong MySQL, transaction được thực hiện ở cấp storage engine. InnoDB hỗ trợ transaction, commit, rollback, savepoint, khóa và phục hồi sau sự cố. Các engine không transactional như MyISAM không cung cấp cùng bảo đảm rollback cho thao tác ghi.

Kiểm tra engine của bảng:

```sql
SHOW TABLE STATUS
WHERE Name IN ('orders', 'order_items');
```

Hoặc:

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('orders', 'order_items');
```

Với dữ liệu nghiệp vụ cần ACID, nên dùng InnoDB cho các bảng tham gia cùng transaction. Chỉ một bảng dùng engine không transactional cũng có thể làm hỏng kỳ vọng “tất cả hoặc không có gì” của toàn bộ quy trình.

## 8. Autocommit và transaction tường minh

MySQL thường bật `autocommit` theo mặc định. Khi `autocommit = 1`, mỗi câu lệnh SQL thành công được thực thi như một transaction riêng và tự commit nếu không có transaction tường minh đang mở.

Kiểm tra trạng thái:

```sql
SELECT @@SESSION.autocommit;
```

Với autocommit bật, hai câu lệnh sau là hai transaction độc lập:

```sql
UPDATE accounts SET balance = balance - 100 WHERE account_id = 101;
UPDATE accounts SET balance = balance + 100 WHERE account_id = 202;
```

Nếu câu lệnh thứ hai thất bại, câu lệnh đầu tiên đã commit và không thể rollback bằng một lệnh `ROLLBACK` sau đó. Đây là lý do phải mở transaction tường minh khi nhiều thao tác cùng tạo thành một đơn vị nghiệp vụ.

Có thể bắt đầu transaction bằng:

```sql
START TRANSACTION;
-- hoặc
BEGIN;
```

Sau đó kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Trong thời gian transaction tường minh đang mở, các câu lệnh tiếp theo trên cùng connection tham gia transaction đó, cho đến khi transaction kết thúc.

## 9. Vòng đời cơ bản: START TRANSACTION, COMMIT và ROLLBACK

Một transaction tường minh thường có cấu trúc:

```sql
START TRANSACTION;

-- Đọc dữ liệu cần thiết
SELECT ...;

-- Ghi một hoặc nhiều thay đổi liên quan
INSERT ...;
UPDATE ...;
DELETE ...;

-- Chỉ xác nhận khi tất cả điều kiện nghiệp vụ đều đạt
COMMIT;
```

Nếu bất kỳ bước nào không đạt điều kiện và ứng dụng quyết định hủy:

```sql
ROLLBACK;
```

`COMMIT` xác nhận các thay đổi của transaction. `ROLLBACK` hủy các thay đổi transactional chưa commit. Sau khi commit thành công, không thể dùng rollback để hoàn tác transaction đã kết thúc; muốn sửa cần thực hiện một transaction bù (compensating transaction) hoặc thao tác nghiệp vụ mới.

Luôn xử lý cả lỗi SQL lẫn lỗi ở tầng ứng dụng. Nếu ứng dụng phát hiện một bước không hợp lệ, nó cần chủ động rollback trước khi trả connection về pool.

## 10. Ví dụ đầy đủ: chuyển tiền giữa hai tài khoản

Tạo bảng tài khoản và sổ giao dịch:

```sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(120) NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE account_transfers (
    transfer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    from_account_id BIGINT UNSIGNED NOT NULL,
    to_account_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transfer_id),
    CONSTRAINT fk_transfers_from_account
        FOREIGN KEY (from_account_id) REFERENCES accounts (account_id),
    CONSTRAINT fk_transfers_to_account
        FOREIGN KEY (to_account_id) REFERENCES accounts (account_id)
) ENGINE=InnoDB;
```

Thêm dữ liệu mẫu:

```sql
INSERT INTO accounts (account_id, owner_name, balance)
VALUES
    (101, 'Lan', 1000.00),
    (202, 'Minh', 500.00);
```

Quy trình chuyển tiền 100.00:

```sql
START TRANSACTION;

-- Khóa hai tài khoản theo thứ tự account_id để giảm nguy cơ deadlock
SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng kiểm tra: có đúng hai tài khoản, amount > 0,
-- tài khoản nguồn đủ số dư và cả hai tài khoản được phép giao dịch.

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 101
  AND balance >= 100.00;

-- Ứng dụng phải kiểm tra affected rows = 1; nếu không thì ROLLBACK.

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 202;

-- Ứng dụng phải kiểm tra affected rows = 1; nếu không thì ROLLBACK.

INSERT INTO account_transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 202, 100.00);

COMMIT;
```

Đoạn SQL trên mô tả thứ tự thao tác; các dòng chú thích “ứng dụng kiểm tra” là bước bắt buộc của chương trình gọi database. Nếu số hàng cập nhật không đúng, tài khoản không tồn tại, không đủ số dư hoặc insert lịch sử thất bại, ứng dụng phải chạy `ROLLBACK` thay vì commit.

Sau khi commit, kiểm tra:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id;

SELECT *
FROM account_transfers
ORDER BY transfer_id DESC
LIMIT 1;
```

Số dư tổng của hai tài khoản không đổi do chuyển tiền chỉ di chuyển giá trị giữa hai tài khoản. Sổ giao dịch ghi nhận một lần chuyển tương ứng.

## 11. Vì sao cần khóa hàng khi đọc rồi mới cập nhật?

Nếu hai transaction cùng đọc số dư trước khi cập nhật, cả hai có thể cùng đưa ra quyết định dựa trên một giá trị cũ. Đây là tình huống race condition.

`SELECT ... FOR UPDATE` là locking read. Trong transaction InnoDB, nó lấy khóa trên các hàng được đọc theo access path và giữ khóa đến khi transaction commit hoặc rollback. Transaction khác muốn cập nhật hoặc lấy khóa xung đột trên các hàng đó phải chờ hoặc có thể gặp deadlock.

Ví dụ:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Ứng dụng kiểm tra số dư và thực hiện UPDATE phù hợp.

COMMIT;
```

Khóa cần được lấy trong cùng transaction với thao tác kiểm tra và cập nhật. Nếu đọc ở một connection, kết thúc transaction, rồi cập nhật ở connection khác, khóa không còn bảo vệ bước sau.

Với các thao tác cần khóa nhiều hàng, cố gắng truy cập hàng theo một thứ tự nhất quán, ví dụ tăng dần theo primary key. Điều này không loại bỏ mọi deadlock nhưng giúp giảm khả năng hai transaction khóa cùng tập hàng theo thứ tự ngược nhau.

## 12. Các mức cô lập transaction trong InnoDB

MySQL InnoDB hỗ trợ bốn mức cô lập chuẩn:

| Isolation level | Đặc điểm chính | Lưu ý |
| --- | --- | --- |
| `READ UNCOMMITTED` | Có thể đọc thay đổi chưa commit của transaction khác (dirty read) | Mức cô lập thấp nhất; hiếm khi phù hợp với nghiệp vụ cần dữ liệu đáng tin cậy |
| `READ COMMITTED` | Mỗi consistent read thông thường lấy snapshot mới tại thời điểm câu lệnh bắt đầu; không đọc dữ liệu chưa commit | Một transaction có thể thấy dữ liệu commit mới ở câu SELECT sau |
| `REPEATABLE READ` | Các consistent read thông thường trong transaction dùng cùng snapshot được tạo ở lần consistent read đầu tiên | Là mức mặc định phổ biến của InnoDB; locking read có ngữ nghĩa khác consistent read |
| `SERIALIZABLE` | Mức nghiêm ngặt hơn, biến các thao tác đọc thông thường thành hành vi khóa phù hợp khi transaction đang mở | Có thể tăng chờ khóa và giảm concurrency |

Kiểm tra mức cô lập hiện tại:

```sql
SELECT @@SESSION.transaction_isolation;
```

Trong MySQL InnoDB, mặc định thường là `REPEATABLE-READ`, nhưng cấu hình có thể thay đổi theo server hoặc session. Hãy kiểm tra thay vì giả định.

### 12.1. Dirty read

Dirty read xảy ra khi transaction đọc một thay đổi chưa được transaction khác commit. Nếu transaction ghi sau đó rollback, transaction đọc đã quan sát một giá trị không bao giờ trở thành dữ liệu đã xác nhận.

`READ UNCOMMITTED` có thể cho phép dirty read. Các mức `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` của InnoDB không cho consistent read thông thường nhìn thấy thay đổi chưa commit.

### 12.2. Non-repeatable read

Non-repeatable read xảy ra khi cùng một transaction đọc lại một hàng nhưng thấy giá trị khác vì transaction khác đã commit một cập nhật giữa hai lần đọc.

Ở `READ COMMITTED`, mỗi consistent read có snapshot mới nên hiện tượng này có thể xảy ra. Ở `REPEATABLE READ`, các consistent read thông thường trong cùng transaction đọc cùng snapshot nên không thấy thay đổi commit sau snapshot đó.

### 12.3. Phantom read

Phantom read là khi cùng một điều kiện truy vấn phạm vi trả về tập hàng khác nhau do transaction khác thêm hoặc xóa hàng phù hợp.

InnoDB `REPEATABLE READ` dùng snapshot cho consistent reads và dùng next-key/gap locking trong các locking read phù hợp để bảo vệ phạm vi. Không nên suy ra mọi truy vấn đọc đều khóa phạm vi; consistent read thông thường và locking read có cơ chế khác nhau.

## 13. MVCC và consistent read

InnoDB dùng MVCC để cho phép nhiều transaction đọc các phiên bản dữ liệu nhất quán mà không phải khóa mọi hàng đang đọc. Một `SELECT` thông thường trong transaction ở mức cô lập hỗ trợ consistent read có thể đọc snapshot, thay vì chờ mọi transaction ghi hoàn tất.

Ví dụ ở `REPEATABLE READ`:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101;

-- Một connection khác cập nhật balance và COMMIT.

SELECT balance
FROM accounts
WHERE account_id = 101;

COMMIT;
```

Hai `SELECT` thông thường trong cùng transaction có thể nhìn thấy cùng phiên bản snapshot, dù connection khác đã commit một giá trị mới sau lần đọc đầu. Đây là đặc điểm của consistent read trong `REPEATABLE READ`.

Nếu cần đọc phiên bản hiện hành và khóa hàng để chuẩn bị cập nhật, hãy cân nhắc locking read như `SELECT ... FOR UPDATE`. Đừng trộn lẫn kỳ vọng của consistent read với locking read; chúng phục vụ mục đích khác nhau.

## 14. SET TRANSACTION: chọn mức cô lập

Có thể đặt mức cô lập cho transaction tiếp theo:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

-- Các thao tác của transaction

COMMIT;
```

Hoặc đặt cho session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Thay đổi session ảnh hưởng các transaction tiếp theo trên connection đó. Đặt global ảnh hưởng mặc định của các connection mới và cần quyền quản trị phù hợp. Với connection pool, phải cấu hình isolation cho từng connection hoặc transaction theo cách có kiểm soát.

Không nên hạ isolation chỉ để làm giảm lock wait nếu chưa hiểu bất biến nghiệp vụ. Đôi khi giải pháp đúng là thêm index, rút ngắn transaction, cập nhật có điều kiện hoặc khóa đúng hàng thay vì thay đổi toàn bộ mức cô lập.

## 15. SAVEPOINT: rollback một phần transaction

`SAVEPOINT` tạo một mốc trong transaction. Có thể rollback về mốc đó mà vẫn giữ các thay đổi trước mốc trong transaction:

```sql
START TRANSACTION;

INSERT INTO orders (id, customer_id, total_amount, status)
VALUES (2001, 42, 150000.00, 'pending');

SAVEPOINT after_order;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (2001, 10, 2, 75000.00);

-- Nếu cần hủy phần thao tác sau savepoint:
ROLLBACK TO SAVEPOINT after_order;

-- Có thể tiếp tục thao tác khác rồi kết thúc transaction.
COMMIT;
```

`ROLLBACK TO SAVEPOINT` không kết thúc toàn transaction. Các thay đổi trước savepoint vẫn còn và chỉ được xác nhận khi commit. Có thể xóa mốc không còn cần bằng `RELEASE SAVEPOINT after_order`.

Savepoint không phải transaction lồng nhau. MySQL/InnoDB không cung cấp nested transaction độc lập; một transaction chỉ có một commit/rollback cuối cùng, còn savepoint cho phép quay lui một phần.

## 16. DDL và implicit commit

Không phải mọi câu lệnh đều có thể được rollback như DML trên InnoDB. Nhiều câu lệnh DDL và câu lệnh quản trị gây implicit commit, nghĩa là chúng kết thúc transaction đang mở trước hoặc sau khi thực hiện theo quy tắc của câu lệnh.

Các ví dụ thường gặp gồm:

- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`.
- `TRUNCATE TABLE`.
- `RENAME TABLE`.
- Một số câu lệnh quản lý user, quyền và cấu hình server.

Ví dụ không nên kỳ vọng lệnh sau có thể rollback cả DDL:

```sql
START TRANSACTION;

INSERT INTO audit_notes (note)
VALUES ('Chuẩn bị thay đổi schema');

ALTER TABLE orders ADD COLUMN source_code VARCHAR(30) NULL;

ROLLBACK;
```

`ALTER TABLE` có thể gây implicit commit; do đó `ROLLBACK` sau đó không nhất thiết hủy insert trước DDL và không hoàn tác thay đổi schema. Hãy chạy migration DDL như một bước triển khai riêng, có kế hoạch backup/rollback schema, thay vì gộp vào transaction DML với kỳ vọng atomic.

Các chi tiết implicit commit có ngoại lệ theo loại câu lệnh và phiên bản. Trước khi đưa DDL vào quy trình giao dịch, hãy kiểm tra tài liệu chính thức của đúng phiên bản MySQL.

MySQL có khái niệm atomic DDL ở các phiên bản hiện đại: một thao tác DDL được bảo vệ để khi server gặp sự cố trong lúc thực thi, metadata và dữ liệu dictionary không rơi vào trạng thái dở dang. Điều này không có nghĩa DDL trở thành một phần có thể rollback cùng transaction DML của người dùng. DDL vẫn có thể gây implicit commit theo quy tắc của nó.

## 17. Transaction thuộc về connection

Transaction được quản lý trên một connection/session MySQL. Các câu lệnh cần nằm trong cùng connection để cùng tham gia một transaction.

Một lỗi thường gặp ở ứng dụng dùng connection pool:

1. Connection A chạy `START TRANSACTION`.
2. Ứng dụng gửi câu `UPDATE` tiếp theo nhưng pool cấp connection B.
3. Câu update trên B chạy trong transaction khác hoặc autocommit riêng.
4. Ứng dụng gọi `COMMIT` trên A và tưởng rằng cả hai câu lệnh đã được xác nhận cùng nhau.

Kết quả là transaction boundary bị phá vỡ. Hãy mượn một connection từ pool, bắt đầu transaction trên connection đó, thực hiện toàn bộ thao tác và commit/rollback trên chính connection đó rồi mới trả connection về pool.

Khi transaction thất bại, ứng dụng phải rollback trước khi tái sử dụng connection. Không để một connection có transaction đang mở quay lại pool trong trạng thái không rõ ràng.

## 18. Deadlock, lock wait timeout và retry

Deadlock xảy ra khi các transaction giữ khóa mà transaction khác cần, tạo thành chu trình chờ. Ví dụ:

- Transaction A khóa hàng 1 rồi chờ hàng 2.
- Transaction B khóa hàng 2 rồi chờ hàng 1.
- Không transaction nào có thể tiếp tục nếu không có một bên nhả khóa.

InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback. Ứng dụng cần bắt lỗi deadlock, sau đó có thể retry **toàn bộ transaction** với giới hạn số lần và backoff phù hợp. Không chỉ chạy lại câu lệnh cuối vì các thao tác trước đó trong transaction đã bị rollback.

Lock wait timeout xảy ra khi một transaction chờ khóa quá thời gian cấu hình. Tùy cấu hình và loại lỗi, ứng dụng cần xác định transaction còn hoạt động hay đã bị rollback; cách an toàn thường là rollback rõ ràng rồi retry toàn bộ đơn vị nghiệp vụ nếu có thể.

Trong InnoDB, khi hết thời gian chờ khóa, mặc định chỉ câu lệnh đang chờ bị rollback; transaction có thể vẫn còn mở. Nếu `innodb_rollback_on_timeout` được bật, toàn bộ transaction sẽ bị rollback. Ngược lại, khi InnoDB phát hiện deadlock, transaction được chọn làm nạn nhân thường bị rollback toàn bộ. Vì hành vi khác nhau, ứng dụng nên xử lý lỗi theo loại lỗi, rollback rõ ràng khi cần và không giả định mọi lỗi SQL đều tự kết thúc transaction.

Một trường hợp khác là kết nối bị đứt ngay trong lúc gửi `COMMIT`. Ứng dụng có thể không biết server đã commit hay chưa vì phản hồi bị mất trên đường truyền. Không nên gửi lại một thao tác không idempotent một cách mù quáng. Dùng mã yêu cầu duy nhất có ràng buộc `UNIQUE`, bảng ghi nhận yêu cầu hoặc cơ chế idempotency để kiểm tra kết quả trước khi thử lại.

Giảm nguy cơ deadlock bằng cách:

- Truy cập nhiều hàng theo cùng thứ tự ở mọi luồng xử lý.
- Tạo index phù hợp để tránh khóa phạm vi rộng ngoài ý muốn.
- Giữ transaction ngắn và chỉ khóa các hàng cần thiết.
- Không chờ network, người dùng hoặc dịch vụ ngoài khi đang giữ transaction mở.
- Xử lý lỗi và retry có giới hạn, có idempotency khi cần.

Deadlock không nhất thiết là lỗi thiết kế nghiêm trọng; trong hệ thống đồng thời, ứng dụng vẫn cần có chiến lược xử lý deadlock đúng cách.

## 19. Thiết kế transaction ngắn và an toàn

Một transaction nên bao quanh các thao tác cần cùng thành công hoặc cùng thất bại. Một số nguyên tắc:

1. Mở transaction càng gần thời điểm bắt đầu thao tác dữ liệu càng tốt.
2. Hoàn tất kiểm tra đầu vào không cần khóa trước khi mở transaction.
3. Lấy khóa theo thứ tự nhất quán khi cần nhiều hàng.
4. Chỉ đọc/ghi các hàng cần thiết; bảo đảm điều kiện lọc có index phù hợp.
5. Không gọi HTTP, gửi email, chờ người dùng hoặc thực hiện công việc nặng trong lúc giữ khóa.
6. Commit hoặc rollback sớm, không để transaction treo qua nhiều bước xử lý ứng dụng.
7. Xử lý lỗi, deadlock và retry ở cấp toàn transaction.
8. Dùng idempotency key hoặc ràng buộc unique khi client có thể gửi lại yêu cầu sau timeout.
9. Ghi log định danh transaction nghiệp vụ để đối soát, không nhầm log ứng dụng với cơ chế rollback.

Transaction dài giữ undo history và có thể làm chậm purge, giữ khóa lâu, tăng lock wait và gây áp lực lên storage. Theo dõi transaction mở lâu trong vận hành, đặc biệt khi một connection bị bỏ quên mà không commit hoặc rollback.

## 20. Transaction trong hệ thống có dịch vụ bên ngoài

Một transaction MySQL không thể tự rollback một thao tác đã xảy ra ở hệ thống khác. Ví dụ, nếu transaction cập nhật đơn hàng rồi gọi API thanh toán, `ROLLBACK` chỉ hủy dữ liệu trong MySQL; nó không thể tự hoàn tiền hoặc hủy giao dịch ở cổng thanh toán.

Với quy trình nhiều dịch vụ, cần thiết kế phối hợp phù hợp:

- Ghi trạng thái và outbox event trong cùng transaction database.
- Worker đọc outbox và gửi sự kiện sau commit.
- Dịch vụ nhận xử lý idempotent để tránh áp dụng trùng khi message được gửi lại.
- Dùng saga/compensating action cho các bước phân tán cần hành động bù.

Đây là các mẫu kiến trúc ở cấp hệ thống; ACID của một transaction InnoDB vẫn chỉ bảo vệ dữ liệu thuộc transaction đó. Không giữ transaction database mở trong khi chờ dịch vụ ngoài phản hồi.

## 21. Kiểm tra transaction và cấu hình liên quan

Một số truy vấn giúp quan sát trạng thái và cấu hình:

```sql
SELECT
    @@SESSION.autocommit AS autocommit_mode,
    @@SESSION.transaction_isolation AS isolation_level;
```

Kiểm tra engine của bảng:

```sql
SELECT TABLE_NAME, ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE';
```

Kiểm tra các biến liên quan durability:

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'sync_binlog';
```

Trong môi trường vận hành, DBA có thể xem transaction và lock đang hoạt động qua các bảng hệ thống phù hợp, chẳng hạn `performance_schema` và `information_schema.innodb_trx` tùy phiên bản. Không truy vấn hoặc thay đổi các bảng hệ thống nội bộ tùy tiện; dùng công cụ giám sát và quyền tối thiểu cần thiết.

## 22. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Nhiều câu UPDATE liên tiếp tự thành một transaction | Với autocommit bật, mỗi câu lệnh riêng lẻ có thể tự commit | Dùng `START TRANSACTION` khi các bước thuộc cùng đơn vị nghiệp vụ |
| ROLLBACK có thể hoàn tác mọi thứ | Chỉ hủy thay đổi transactional chưa commit; DDL có thể implicit commit | Tách migration DDL khỏi transaction DML |
| MySQL tự bảo đảm mọi quy tắc nghiệp vụ | Database chỉ bảo vệ quy tắc đã được khai báo và logic được thực thi | Thiết kế constraint và validation đầy đủ |
| Mọi storage engine đều hỗ trợ ACID | Engine như MyISAM không có rollback transactional như InnoDB | Dùng InnoDB cho bảng tham gia transaction |
| SELECT thông thường luôn khóa hàng | Consistent read của InnoDB thường dùng MVCC snapshot | Dùng locking read khi cần bảo vệ bước đọc-sửa |
| REPEATABLE READ có nghĩa mọi SELECT đều nhìn dữ liệu mới nhất | Consistent read có thể dùng snapshot; locking read có ngữ nghĩa khác | Phân biệt consistent read và `FOR UPDATE` |
| START TRANSACTION lồng nhau tạo nested transaction | MySQL không hỗ trợ nested transaction độc lập | Dùng SAVEPOINT cho rollback một phần |
| Commit thành công trên primary nghĩa replica đã áp dụng | Replica bất đồng bộ có thể còn độ trễ | Xác định yêu cầu replication consistency riêng |
| Deadlock chỉ cần chạy lại câu lệnh cuối | InnoDB có thể rollback toàn transaction nạn nhân | Retry toàn bộ transaction có giới hạn |
| Có thể giữ transaction mở khi gọi API ngoài | Khóa bị giữ lâu và rollback không thể hoàn tác dịch vụ ngoài | Dùng outbox/saga hoặc xử lý ngoài transaction |

## 23. Bài tập thực hành

1. Tạo hai bảng InnoDB `accounts` và `account_transfers`; thực hiện chuyển tiền trong một transaction.
2. Thử rollback sau khi trừ tiền nhưng trước khi cộng tiền; xác minh số dư không thay đổi.
3. Bật autocommit và chạy hai UPDATE riêng; quan sát vì sao lệnh thứ hai thất bại không hoàn tác lệnh thứ nhất.
4. Dùng `START TRANSACTION`, cập nhật hai bảng và commit; kiểm tra tất cả thay đổi cùng xuất hiện.
5. Mở hai connection và thử cập nhật cùng một tài khoản; so sánh consistent read với `SELECT ... FOR UPDATE`.
6. Thử `READ COMMITTED` và `REPEATABLE READ` trong hai session để quan sát snapshot khác nhau.
7. Tạo `SAVEPOINT`, thực hiện hai thay đổi, rollback về savepoint rồi commit; xác định thay đổi nào còn lại.
8. Quan sát một DDL như `ALTER TABLE` trong lúc transaction đang mở ở môi trường lab; xác minh implicit commit và không dùng dữ liệu quan trọng.
9. Tạo tình huống deadlock có kiểm soát trên hai connection; đọc lỗi và xây dựng logic retry toàn transaction.
10. Kiểm tra `@@SESSION.autocommit`, isolation level, engine của bảng và các biến durability.
11. Thiết kế ranh giới transaction cho nghiệp vụ tạo đơn hàng có trừ kho và gửi thông báo sau commit.

## 24. Ghi nhớ

Transaction là đơn vị công việc nghiệp vụ cần được commit hoặc rollback như một phần thống nhất. ACID gồm Atomicity (các thay đổi cùng thành công hoặc cùng bị hủy), Consistency (duy trì các quy tắc dữ liệu), Isolation (kiểm soát tương tác đồng thời) và Durability (bảo vệ thay đổi đã commit theo cấu hình lưu trữ).

Với MySQL, dùng InnoDB cho các bảng cần transaction. `autocommit` thường bật mặc định nên nhiều câu lệnh riêng lẻ không tự trở thành một đơn vị nghiệp vụ chung; dùng `START TRANSACTION`, `COMMIT` và `ROLLBACK` cho quy trình nhiều bước. Hiểu mức cô lập, MVCC và locking read để xử lý cạnh tranh; dùng `SAVEPOINT` cho rollback một phần; tránh giả định DDL có thể rollback; giữ transaction ngắn, xử lý deadlock bằng retry toàn transaction và nhớ transaction chỉ thuộc một connection. ACID là nền tảng cho dữ liệu đáng tin cậy, nhưng vẫn cần thiết kế constraint, logic ứng dụng, backup, giám sát và quy trình xử lý lỗi phù hợp.
