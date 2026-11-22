# Tính nguyên tử câu lệnh và tính nguyên tử toàn giao dịch

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Khi cập nhật dữ liệu, cần hiểu hai phạm vi hoàn tác khác nhau: **tính nguyên tử của một câu lệnh** và **tính nguyên tử của toàn giao dịch**.

Với InnoDB, một câu lệnh DML bị lỗi thường được hoàn tác như một đơn vị, nhưng các câu lệnh thành công trước đó trong cùng transaction vẫn còn hiệu lực bên trong transaction. Chỉ ROLLBACK mới hoàn tác toàn bộ thay đổi chưa commit của transaction; COMMIT xác nhận tất cả thay đổi đó. Phân biệt hai phạm vi này giúp xử lý lỗi đúng, tránh commit dữ liệu dở dang và thiết kế luồng retry an toàn.

Các ví dụ thực hành dùng InnoDB và cú pháp MySQL 8.0. Kiểm tra phiên bản server bằng SELECT VERSION(); một số biến trạng thái và hành vi DDL có thể khác giữa các phiên bản.

## 1. Hai phạm vi nguyên tử

**Nguyên tử câu lệnh (statement atomicity)** có nghĩa là một câu lệnh được xử lý như một đơn vị đối với bảng transactional: nếu câu lệnh thất bại, các thay đổi do chính câu lệnh đó thực hiện được hoàn tác. Ví dụ, một câu INSERT nhiều hàng gặp lỗi duplicate key giữa chừng thì InnoDB hoàn tác các hàng mà câu INSERT đó đã chèn.

**Nguyên tử giao dịch (transaction atomicity)** có nghĩa là toàn bộ nhóm câu lệnh trong một transaction được xem là một đơn vị: hoặc tất cả thay đổi được commit, hoặc tất cả thay đổi chưa commit được rollback. Nếu transaction có ba câu lệnh thành công rồi câu lệnh thứ tư thất bại, ba câu lệnh trước không tự động biến mất chỉ vì câu thứ tư lỗi.

| Phạm vi | Đơn vị được bảo vệ | Cách kết thúc |
|---|---|---|
| Statement atomicity | Một câu lệnh SQL | Câu lệnh thành công hoặc thay đổi của câu lệnh được hoàn tác |
| Transaction atomicity | Nhiều câu lệnh thuộc cùng transaction | COMMIT xác nhận tất cả hoặc ROLLBACK hoàn tác tất cả |

Hai phạm vi có liên quan nhưng không thay thế nhau. Statement atomicity bảo vệ từng thao tác; transaction atomicity bảo vệ quy trình nghiệp vụ gồm nhiều thao tác.

## 2. Statement atomicity trong InnoDB

InnoDB là storage engine có hỗ trợ transaction. Khi một câu lệnh thay đổi nhiều hàng và lỗi xảy ra trong quá trình thực thi, InnoDB có thể hoàn tác phần thay đổi của chính câu lệnh đó.

Ví dụ, bảng ledger_entries có khóa chính entry_id. Một câu lệnh chèn hai hàng nhưng hàng thứ hai vi phạm khóa chính:

~~~sql
INSERT INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);
~~~

Giả sử entry_id = 9001 đã tồn tại. Câu lệnh gặp lỗi duplicate key. Với InnoDB, cả câu lệnh được rollback: hàng 9002 không còn được chèn dù nó xuất hiện trước hàng bị lỗi trong danh sách VALUES.

Statement atomicity cũng áp dụng cho những câu lệnh DML nhiều hàng như UPDATE hoặc DELETE. Nếu một lỗi làm câu lệnh thất bại, các thay đổi của câu lệnh trên bảng InnoDB được hoàn tác như một đơn vị.

### 2.1. Lỗi câu lệnh không đồng nghĩa transaction đã kết thúc

Trong một transaction tường minh, một lỗi như duplicate key thường chỉ rollback câu lệnh gây lỗi. Transaction vẫn mở và các câu lệnh thành công trước đó vẫn là thay đổi chưa commit.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

-- Giả sử entry_id = 9001 đã tồn tại.
INSERT INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);

-- Sau lỗi duplicate key, kiểm tra trạng thái trong cùng session.
SELECT account_id, balance
FROM accounts
WHERE account_id = 1;

SELECT entry_id
FROM ledger_entries
WHERE entry_id = 9002;

ROLLBACK;
~~~

Sau lỗi INSERT:

- Thay đổi của câu INSERT bị hoàn tác; entry_id 9002 không tồn tại.
- UPDATE trước đó vẫn nằm trong transaction; session hiện tại vẫn thấy số dư đã giảm 100.
- Nếu gọi COMMIT, UPDATE trước đó có thể được commit dù câu INSERT thất bại.
- Nếu gọi ROLLBACK, UPDATE trước đó cũng được hoàn tác.

Đây là điểm quan trọng nhất khi xử lý lỗi giữa transaction: không được mặc định rằng lỗi của một câu lệnh đã rollback toàn bộ transaction.

### 2.2. Cơ chế hoàn tác ở mức khái niệm

InnoDB sử dụng undo information để có thể khôi phục trạng thái dữ liệu trước thay đổi. Khi statement cần rollback, engine dùng thông tin hoàn tác để loại bỏ các thay đổi do statement đó tạo ra. Khi transaction rollback, InnoDB hoàn tác tất cả thay đổi chưa commit thuộc transaction.

Chi tiết nội bộ phức tạp hơn một savepoint SQL do người dùng tạo. Có thể hình dung InnoDB đánh dấu phạm vi thay đổi của câu lệnh để hoàn tác đúng phần cần thiết; không cần tự tạo SAVEPOINT trước từng câu DML để có statement atomicity.

## 3. Transaction atomicity: nhiều câu lệnh là một đơn vị

Một quy trình nghiệp vụ thường gồm nhiều thao tác cần cùng thành công. Ví dụ chuyển tiền giữa hai tài khoản:

1. Trừ tiền tài khoản gửi.
2. Cộng tiền tài khoản nhận.
3. Ghi nhận giao dịch.

Nếu chỉ một bước thành công, dữ liệu có thể không còn nhất quán. Transaction gom các bước thành một đơn vị:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

INSERT INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9101, 1, -100.00),
    (9102, 2,  100.00);

COMMIT;
~~~

Nếu tất cả câu lệnh thành công và COMMIT thành công, thay đổi được xác nhận. Nếu phát hiện lỗi nghiệp vụ trước commit, ứng dụng có thể gọi ROLLBACK để hoàn tác cả hai UPDATE và INSERT.

Không chỉ cần kiểm tra lỗi SQL. Ứng dụng còn phải kiểm tra số hàng bị ảnh hưởng. Ví dụ UPDATE theo account_id có thể chạy thành công nhưng cập nhật 0 hàng vì tài khoản không tồn tại; khi đó không có lỗi SQL nhưng quy trình chuyển tiền vẫn không hợp lệ.

## 4. Autocommit và ranh giới transaction

MySQL thường chạy với autocommit = 1. Khi đó, mỗi câu lệnh chạy ngoài transaction tường minh được xem như một transaction riêng và được commit tự động nếu thành công.

Kiểm tra cấu hình session:

~~~sql
SELECT @@SESSION.autocommit;
~~~

Với autocommit bật:

~~~sql
UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 2;
~~~

Hai UPDATE là hai transaction riêng. Nếu câu thứ hai lỗi, câu thứ nhất có thể đã được commit; không thể rollback nó bằng cách gọi ROLLBACK sau đó.

Muốn hai câu lệnh thuộc cùng transaction:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 2;

COMMIT;
~~~

START TRANSACTION mở một transaction tường minh ngay cả khi autocommit đang bật. Khi transaction kết thúc bằng COMMIT hoặc ROLLBACK, session trở lại hành vi autocommit đã cấu hình.

MySQL không hỗ trợ transaction lồng nhau. Gọi START TRANSACTION khi một transaction khác đang mở sẽ kết thúc transaction hiện tại bằng implicit commit trước khi bắt đầu transaction mới. Nếu cần một phạm vi hoàn tác con, dùng SAVEPOINT thay vì gọi START TRANSACTION lần nữa.

### 4.1. Autocommit tắt

Có thể đặt autocommit cho session:

~~~sql
SET SESSION autocommit = 0;
~~~

Khi autocommit tắt, các thay đổi được giữ trong transaction cho đến khi COMMIT hoặc ROLLBACK. Sau khi một transaction kết thúc, session tiếp tục hoạt động với chế độ autocommit tắt và transaction tiếp theo sẽ được mở theo quy tắc của chế độ này.

Trong ứng dụng, nên quản lý ranh giới transaction rõ ràng và khôi phục cấu hình session khi trả connection về connection pool. Một connection bị giữ ở autocommit = 0 có thể khiến các thao tác sau vô tình nằm trong transaction chưa kết thúc.

## 5. So sánh rollback một statement và rollback cả transaction

Giả sử transaction thực hiện ba câu lệnh:

~~~sql
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;

INSERT INTO order_items (item_id, product_id, quantity)
VALUES (1001, 10, 1);

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 500;
~~~

Nếu câu INSERT gặp duplicate key:

- Statement INSERT bị rollback.
- UPDATE inventory trước đó vẫn còn trong transaction.
- UPDATE orders sau lỗi có thể tiếp tục chạy nếu ứng dụng chủ động tiếp tục và transaction vẫn hợp lệ.
- COMMIT có thể xác nhận những câu lệnh thành công trước và sau lỗi.
- ROLLBACK hoàn tác mọi thay đổi chưa commit của cả ba câu lệnh.

Ứng dụng thường nên dừng luồng nghiệp vụ và rollback khi một bước bắt buộc thất bại. Việc tiếp tục transaction sau lỗi chỉ phù hợp khi logic đã xác định rõ lỗi đó có thể bỏ qua.

## 6. SAVEPOINT: hoàn tác một phần transaction

SAVEPOINT cho phép đánh dấu một vị trí trong transaction để có thể rollback một phần thay đổi:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 50.00
WHERE account_id = 1;

SAVEPOINT after_debit;

INSERT INTO transaction_notes (transaction_id, note)
VALUES (9100, 'Transfer note');

-- Nếu chỉ phần ghi chú không hợp lệ:
ROLLBACK TO SAVEPOINT after_debit;

-- Các thay đổi trước savepoint vẫn còn.
COMMIT;
~~~

ROLLBACK TO SAVEPOINT hoàn tác các thay đổi sau savepoint và giữ transaction mở. Nó không commit phần trước savepoint.

### 6.1. SAVEPOINT không thay thế transaction

Nếu chuyển tiền đã trừ tài khoản gửi trước savepoint và sau đó rollback đến savepoint, khoản trừ vẫn còn. Nếu nghiệp vụ yêu cầu hoàn tác cả khoản trừ, phải rollback toàn transaction hoặc rollback đến một savepoint đặt trước khoản trừ.

Có thể xóa savepoint khi không cần nữa:

~~~sql
RELEASE SAVEPOINT after_debit;
~~~

COMMIT hoặc ROLLBACK toàn transaction sẽ kết thúc phạm vi các savepoint thuộc transaction đó.

### 6.2. Dùng savepoint để xử lý bước tùy chọn

Savepoint hữu ích khi transaction có một phần bắt buộc và một phần tùy chọn. Ví dụ, tạo đơn hàng và trừ tồn kho là bắt buộc; ghi một ghi chú phụ có thể được phép thất bại mà vẫn giữ đơn hàng. Chỉ áp dụng khi nghiệp vụ cho phép phần tùy chọn không tồn tại và ứng dụng xử lý lỗi có chủ đích.

Không dùng savepoint để che lỗi toàn vẹn dữ liệu ở bước cốt lõi. Nếu trừ kho hoặc ghi chi tiết đơn hàng thất bại, toàn transaction cần rollback.

## 7. Các lỗi có thể ảnh hưởng phạm vi rollback khác nhau

Không phải mọi lỗi đều có cùng hành vi. Cần nhận biết loại lỗi và cấu hình InnoDB.

### 7.1. Lỗi constraint thông thường

Ví dụ duplicate key hoặc vi phạm foreign key trong một câu DML InnoDB thường khiến câu lệnh đó bị rollback. Transaction tường minh vẫn mở để ứng dụng quyết định tiếp tục, rollback hoặc xử lý lỗi.

~~~sql
START TRANSACTION;

INSERT INTO lab_parent (parent_id) VALUES (1);

-- Nếu khóa ngoại không tồn tại, statement INSERT này thất bại.
INSERT INTO lab_child (child_id, parent_id)
VALUES (10, 999);

-- Câu INSERT lỗi đã bị rollback; câu trước vẫn là thay đổi chưa commit.
ROLLBACK;
~~~

### 7.2. Deadlock

Khi InnoDB phát hiện deadlock, engine chọn một transaction làm nạn nhân và rollback toàn bộ transaction đó để giải phóng khóa. Ứng dụng nhận lỗi deadlock (thường là error 1213 / SQLSTATE 40001) và phải thực hiện lại toàn bộ transaction nếu nghiệp vụ vẫn cần.

Không chỉ chạy lại câu SQL vừa lỗi. Các câu lệnh trước đó của transaction nạn nhân đã bị rollback; cần bắt đầu một transaction mới và thực hiện lại toàn bộ quy trình.

### 7.3. Lock wait timeout

Khi chờ khóa vượt thời gian cho phép, InnoDB mặc định rollback statement đang chờ, không nhất thiết rollback toàn transaction. Biến innodb_rollback_on_timeout có thể thay đổi hành vi để rollback toàn transaction khi lock wait timeout xảy ra.

Kiểm tra:

~~~sql
SELECT @@SESSION.innodb_lock_wait_timeout;
SELECT @@GLOBAL.innodb_rollback_on_timeout;
~~~

Nếu ứng dụng tiếp tục sau lock wait timeout, phải biết chính xác transaction còn mở hay đã bị rollback toàn bộ. Không suy luận phạm vi rollback chỉ từ việc nhận một lỗi timeout.

### 7.4. Lỗi kết nối và mất phản hồi

Nếu connection bị đóng khi transaction chưa commit, MySQL rollback transaction đang mở khi session kết thúc. Tuy nhiên, nếu client mất kết nối đúng lúc gửi COMMIT, client có thể không biết server đã commit hay chưa.

Trong tình huống mất phản hồi sau COMMIT, không nên gửi lại thao tác nghiệp vụ một cách mù quáng. Hãy thiết kế idempotency key, mã giao dịch duy nhất hoặc bước truy vấn xác nhận trạng thái để tránh ghi nhận hai lần.

## 8. Câu lệnh có thể không rollback toàn bộ như mong đợi

Statement atomicity và transaction atomicity phụ thuộc storage engine và loại câu lệnh.

### 8.1. Storage engine không hỗ trợ transaction

InnoDB hỗ trợ COMMIT và ROLLBACK. MyISAM không hỗ trợ transaction; thay đổi trên bảng MyISAM không được hoàn tác bằng ROLLBACK.

Ví dụ về rủi ro:

~~~sql
START TRANSACTION;

UPDATE innodb_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE myisam_audit
SET event_count = event_count + 1
WHERE event_id = 10;

ROLLBACK;
~~~

Thay đổi trên innodb_accounts được hoàn tác; thay đổi trên myisam_audit không được rollback. Vì vậy, không thể bảo đảm một transaction nguyên tử xuyên qua các bảng dùng engine không hỗ trợ transaction.

Đối với quy trình cần atomicity, các bảng tham gia nên dùng transactional engine như InnoDB. Kiểm tra engine:

~~~sql
SHOW TABLE STATUS
WHERE Name IN ('innodb_accounts', 'myisam_audit');
~~~

### 8.2. INSERT IGNORE và các câu lệnh biến lỗi thành warning

INSERT IGNORE có thể bỏ qua một số hàng vi phạm constraint hoặc lỗi dữ liệu và tiếp tục chèn những hàng hợp lệ. Khi lỗi được chuyển thành warning, statement không còn thất bại theo cách thông thường nên không rollback toàn bộ statement.

~~~sql
INSERT IGNORE INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);

SHOW WARNINGS;
~~~

Nếu 9001 đã tồn tại, hàng xung đột có thể bị bỏ qua trong khi hàng 9002 vẫn được chèn. Đây là hành vi có chủ đích của IGNORE, không phải vi phạm statement atomicity. Hãy kiểm tra warning và số hàng bị ảnh hưởng nếu dùng IGNORE.

Tương tự, các biến thể như UPDATE IGNORE có thể bỏ qua một số hàng gây lỗi. Không thêm IGNORE chỉ để câu lệnh "chạy qua"; cần xác định dữ liệu bị bỏ qua có chấp nhận được không.

### 8.3. DDL và implicit commit

Nhiều câu lệnh DDL như CREATE TABLE, ALTER TABLE và DROP TABLE gây implicit commit. Chúng có thể commit transaction hiện tại trước khi thực thi và có thể tạo ranh giới commit riêng theo quy tắc MySQL.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10
WHERE account_id = 1;

CREATE TABLE lab_marker (
    marker_id INT PRIMARY KEY
);

ROLLBACK;
~~~

Không giả định ROLLBACK cuối sẽ hoàn tác UPDATE trước DDL. DDL có thể đã commit transaction trước đó. MySQL 8.0 có atomic DDL cho nhiều thao tác DDL được hỗ trợ, nghĩa là thao tác DDL có khả năng crash-safe như một đơn vị; điều này không biến DDL thành một phần có thể rollback trong transaction DML của người dùng.

Một số ngoại lệ như CREATE TEMPORARY TABLE không gây implicit commit nhưng thao tác tạo bảng tạm vẫn không được rollback theo cách thông thường. Khi thiết kế transaction nghiệp vụ, tránh trộn DDL vào giữa các bước DML.

### 8.4. Bảng transactional và tác động ngoài cơ sở dữ liệu

ROLLBACK chỉ hoàn tác các thay đổi transactional mà MySQL quản lý trong transaction. Nó không tự thu hồi email đã gửi, HTTP request đã gọi sang dịch vụ khác, file đã ghi hoặc thao tác ở một hệ thống ngoài. Nếu ứng dụng thực hiện side effect trước COMMIT rồi transaction rollback, hai hệ thống có thể không còn đồng bộ.

Với nghiệp vụ tích hợp, cân nhắc transactional outbox: ghi sự kiện cần gửi vào bảng InnoDB trong cùng transaction với dữ liệu nghiệp vụ, commit cả hai, sau đó một tiến trình riêng gửi sự kiện và đánh dấu đã xử lý. Cách này gắn việc phát sinh sự kiện với transaction dữ liệu; việc gửi vẫn cần cơ chế retry và idempotency.

## 9. Atomicity không đồng nghĩa với mọi thuộc tính ACID

Atomicity là một thành phần của ACID:

| Thuộc tính | Ý nghĩa |
|---|---|
| Atomicity | Các thay đổi của transaction được commit cùng nhau hoặc rollback cùng nhau |
| Consistency | Transaction phải đưa dữ liệu từ trạng thái hợp lệ sang trạng thái hợp lệ theo constraint và quy tắc nghiệp vụ |
| Isolation | Các transaction đồng thời không quan sát hoặc can thiệp lẫn nhau ngoài mức isolation đã chọn |
| Durability | Sau khi commit được xác nhận theo cấu hình đảm bảo, dữ liệu được duy trì qua sự cố theo cam kết của hệ thống |

Statement atomicity giúp bảo vệ một câu lệnh. Transaction atomicity giúp bảo vệ chuỗi câu lệnh. Nhưng chỉ atomicity không bảo đảm quy tắc nghiệp vụ đúng, không tự ngăn race condition và không thay thế durability.

Ví dụ, một transaction có thể atomically trừ tiền hai tài khoản nhưng vẫn sai nghiệp vụ nếu không kiểm tra số dư trước khi trừ. Tương tự, một transaction commit thành công nhưng cấu hình durability không phù hợp có thể có cam kết khác với kỳ vọng vận hành. Cần thiết kế đầy đủ constraint, isolation, locking và cấu hình lưu bền.

## 10. Thiết kế transaction để không commit dữ liệu dở dang

Một luồng transaction an toàn thường có cấu trúc:

1. Bắt đầu transaction.
2. Đọc và khóa dữ liệu cần bảo vệ nếu nghiệp vụ yêu cầu.
3. Kiểm tra điều kiện trước khi ghi.
4. Thực hiện các thay đổi bắt buộc.
5. Kiểm tra số hàng bị ảnh hưởng và kết quả nghiệp vụ.
6. Commit khi mọi bước hợp lệ.
7. Rollback khi một bước bắt buộc thất bại.

Ví dụ chuyển tiền có kiểm tra số dư:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Ứng dụng xác nhận tài khoản tồn tại và balance >= 100.00.
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

-- Ứng dụng phải xác nhận UPDATE vừa tác động đúng 1 hàng.
UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

-- Chỉ commit sau khi đã xác minh tất cả bước và ghi ledger thành công.
COMMIT;
~~~

Đây là khung minh họa; ứng dụng phải xử lý nhánh tài khoản không tồn tại, số dư không đủ, tài khoản nhận không tồn tại và lỗi khi ghi ledger bằng ROLLBACK. SELECT ... FOR UPDATE giữ khóa cần thiết đến khi transaction kết thúc trong InnoDB, giúp tránh một số race condition khi nhiều giao dịch cùng cập nhật tài khoản.

Không giữ transaction mở trong khi chờ người dùng nhập liệu hoặc gọi dịch vụ mạng. Transaction kéo dài làm khóa tồn tại lâu, tăng nguy cơ deadlock và giảm khả năng đồng thời.

## 11. Retry sau lỗi và tính idempotent

Một số lỗi như deadlock là lỗi tạm thời có thể thử lại. Cách retry đúng:

- Nhận diện lỗi có thể retry, ví dụ deadlock.
- Đảm bảo transaction cũ đã bị rollback hoặc kết thúc.
- Bắt đầu transaction mới.
- Chạy lại toàn bộ thao tác nghiệp vụ từ đầu.
- Giới hạn số lần retry và có backoff phù hợp.
- Bảo đảm thao tác có idempotency hoặc khóa nghiệp vụ để không tạo tác động trùng.

Không retry riêng câu lệnh cuối trong transaction bị deadlock vì toàn transaction đã bị rollback. Với lỗi duplicate key, trước khi retry cần xác định đó là xung đột dữ liệu, thao tác đã thực hiện trước đó hay một mã idempotency đã tồn tại.

### 11.1. Mã giao dịch duy nhất

Có thể dùng một khóa idempotency để ngăn cùng yêu cầu nghiệp vụ được xử lý hai lần:

~~~sql
CREATE TABLE transfer_requests (
    request_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (request_id)
) ENGINE=InnoDB;
~~~

Ứng dụng ghi request_id duy nhất trong cùng transaction với thay đổi số dư và ledger. Nếu client gửi lại cùng request_id, khóa chính giúp nhận diện yêu cầu đã tồn tại. Ứng dụng cần đọc trạng thái giao dịch hiện có để trả kết quả phù hợp, không tự động thực hiện lại chuyển tiền.

### 11.2. Mất kết nối khi COMMIT

Nếu server commit xong nhưng phản hồi bị mất trên mạng, client có thể nhận lỗi kết nối dù giao dịch đã được commit. Gửi lại một lệnh trừ tiền mới mà không kiểm tra request_id có thể tạo giao dịch thứ hai. Idempotency key và ledger có mã duy nhất giúp phân biệt "chưa được xử lý" với "đã xử lý nhưng client chưa nhận phản hồi".

## 12. Kiểm tra trạng thái transaction và dữ liệu

Trong lúc phát triển, có thể dùng các câu lệnh sau để quan sát:

~~~sql
SELECT @@SESSION.autocommit;
SELECT @@SESSION.in_transaction;
SELECT @@SESSION.transaction_isolation;
~~~

@@SESSION.in_transaction cho biết session có đang ở trong transaction hay không trên các phiên bản hỗ trợ biến này. Nếu biến không có trên phiên bản đang chạy, hãy dựa vào trạng thái client/driver và cách quản lý transaction của ứng dụng.

Kiểm tra engine của bảng:

~~~sql
SHOW CREATE TABLE accounts;
~~~

Kiểm tra constraint, khóa chính, khóa ngoại và engine trước khi dựa vào rollback. Không giả định mọi bảng trong một câu SQL đều là InnoDB chỉ vì database chính dùng InnoDB.

## 13. Ví dụ tổng hợp: phân biệt statement rollback và transaction rollback

Tạo dữ liệu lab:

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    owner_name VARCHAR(80) NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE lab_ledger (
    entry_id INT NOT NULL,
    account_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (entry_id),
    CONSTRAINT fk_lab_ledger_account
      FOREIGN KEY (account_id)
      REFERENCES lab_accounts (account_id)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, owner_name, balance)
VALUES (1, 'An', 1000.00), (2, 'Binh', 500.00);

INSERT INTO lab_ledger (entry_id, account_id, amount)
VALUES (9001, 2, 25.00);
~~~

### 13.1. Bước 1 — Tạo một thay đổi trước câu lệnh lỗi

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 100.00
WHERE account_id = 1;
~~~

Đọc số dư trong cùng session:

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

Session hiện tại thấy tài khoản 1 còn 900.00. Thay đổi này chưa được commit.

### 13.2. Bước 2 — Gây lỗi trong một statement nhiều hàng

Chạy riêng câu lệnh sau. Nó cố chèn một entry mới 9002 và một entry 9001 đã tồn tại:

~~~sql
INSERT INTO lab_ledger (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);
~~~

MySQL báo duplicate key. Với InnoDB, cả statement bị rollback. Kiểm tra:

~~~sql
SELECT *
FROM lab_ledger
WHERE entry_id IN (9001, 9002);
~~~

Chỉ entry 9001 ban đầu tồn tại; entry 9002 không được giữ lại.

### 13.3. Bước 3 — Quan sát transaction vẫn còn thay đổi

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1;

SELECT @@SESSION.in_transaction;
~~~

Trong cùng session, balance vẫn là 900.00 và transaction vẫn mở. Lỗi INSERT không tự rollback UPDATE trước đó.

### 13.4. Bước 4 — Rollback toàn transaction

~~~sql
ROLLBACK;

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

Balance tài khoản 1 trở lại 1000.00. UPDATE trước đó được hoàn tác vì thuộc transaction đã rollback.

### 13.5. Bước 5 — Thử commit sau lỗi statement

Lặp lại trong một transaction mới:

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 100.00
WHERE account_id = 1;
~~~

Chạy lại câu INSERT có duplicate key và nhận lỗi. Nếu ứng dụng vẫn gọi:

~~~sql
COMMIT;
~~~

UPDATE trừ 100 có thể được commit dù statement INSERT lỗi. Đây là lý do ứng dụng cần chủ động rollback toàn transaction khi một bước bắt buộc thất bại.

### 13.6. Bước 6 — Dọn bảng lab

~~~sql
DROP TABLE lab_ledger;
DROP TABLE lab_accounts;
~~~

Nếu chỉ thực hiện bài thực hành chính, xóa hai bảng lab vừa tạo theo thứ tự bảng con trước bảng cha. Nếu muốn tiếp tục phần mở rộng ở mục 14, hãy giữ hai bảng lại và chỉ dọn sau khi hoàn thành mục đó. Nếu còn transaction đang mở, kết thúc transaction trước khi dọn.

**Kết quả cần đạt:** giải thích được vì sao câu INSERT lỗi không giữ hàng nào của chính nó nhưng UPDATE trước đó vẫn tồn tại trong transaction; chứng minh được ROLLBACK hoàn tác UPDATE; và hiểu vì sao COMMIT sau lỗi có thể lưu một phần quy trình nghiệp vụ nếu ứng dụng xử lý sai.

## 14. Bài thực hành mở rộng: SAVEPOINT và IGNORE

### 14.1. Thử rollback đến savepoint

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 20.00
WHERE account_id = 1;

SAVEPOINT before_optional_note;

INSERT INTO lab_ledger (entry_id, account_id, amount)
VALUES (9201, 1, -20.00);

ROLLBACK TO SAVEPOINT before_optional_note;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1;

SELECT *
FROM lab_ledger
WHERE entry_id = 9201;

ROLLBACK;
~~~

Sau rollback đến savepoint, ledger entry 9201 không còn, nhưng khoản trừ 20 vẫn còn trong transaction. ROLLBACK cuối cùng hoàn tác cả khoản trừ.

### 14.2. Thử INSERT IGNORE

~~~sql
INSERT IGNORE INTO lab_ledger (entry_id, account_id, amount)
VALUES
    (9301, 1, -10.00),
    (9001, 2,  10.00);

SHOW WARNINGS;

SELECT *
FROM lab_ledger
WHERE entry_id IN (9001, 9301);
~~~

Nếu 9001 đã tồn tại, hàng 9301 có thể được chèn còn hàng trùng bị bỏ qua với warning. Quan sát số hàng và warning để phân biệt một câu lệnh thất bại bị rollback với một câu lệnh IGNORE hoàn thành một phần theo quy tắc của nó.

Phần mở rộng sử dụng hai bảng lab_accounts và lab_ledger được tạo ở mục 13. Nếu đã xóa chúng ở bước 13.6, hãy tạo lại bảng và dữ liệu mẫu theo mục 13 trước khi tiếp tục. Sau khi hoàn thành, dọn bảng:

~~~sql
DROP TABLE lab_ledger;
DROP TABLE lab_accounts;
~~~

Chỉ xóa các bảng lab do bạn vừa tạo.

## 15. Quy trình xử lý lỗi transaction trong ứng dụng

Khi một câu lệnh trong transaction báo lỗi, ứng dụng nên thực hiện quy trình rõ ràng:

1. Ghi nhận mã lỗi, SQLSTATE và bước nghiệp vụ đang chạy.
2. Phân loại lỗi: constraint, deadlock, lock timeout, mất kết nối hay lỗi không thể tiếp tục.
3. Xác định engine của các bảng tham gia và hành vi rollback của loại lỗi.
4. Nếu bước bắt buộc thất bại, rollback toàn transaction khi session vẫn còn hoạt động.
5. Nếu transaction đã bị InnoDB rollback do deadlock, bắt đầu transaction mới trước khi retry.
6. Nếu timeout chỉ rollback statement, quyết định rõ có tiếp tục transaction hay rollback toàn bộ.
7. Chỉ retry lỗi có thể phục hồi; dùng idempotency key để tránh tác động trùng.
8. Không gọi dịch vụ ngoài hoặc gửi thông báo không thể thu hồi trước khi transaction dữ liệu được xác nhận; cân nhắc transactional outbox.
9. Kết thúc transaction trước khi trả connection về pool.

Trong code ứng dụng, nên đặt transaction trong một khối try/catch/finally hoặc cơ chế tương đương của framework. Nhánh thành công gọi commit; nhánh lỗi gọi rollback; finally bảo đảm connection được trả về pool trong trạng thái sạch. Cần tránh để exception bị nuốt rồi vẫn commit.

## 16. Nguyên tắc cần ghi nhớ

- Statement atomicity bảo vệ thay đổi của một câu lệnh trên transactional engine; transaction atomicity bảo vệ tất cả câu lệnh trong một transaction.
- Với InnoDB, lỗi DML thông thường như duplicate key thường rollback statement gây lỗi, không tự rollback mọi câu lệnh trước đó.
- Sau lỗi statement, transaction có thể vẫn mở; ứng dụng phải quyết định tiếp tục, COMMIT hay ROLLBACK.
- COMMIT sau một statement lỗi có thể lưu các statement thành công trước đó; nếu bước lỗi là bắt buộc, phải rollback toàn transaction.
- Khi autocommit bật, mỗi statement độc lập ngoài transaction tường minh được commit riêng; nhiều statement cần START TRANSACTION để cùng atomic.
- SAVEPOINT và ROLLBACK TO SAVEPOINT chỉ hoàn tác một phần transaction, không commit phần còn lại.
- Deadlock khiến InnoDB rollback toàn bộ transaction nạn nhân; retry phải chạy lại toàn transaction.
- Lock wait timeout mặc định rollback statement đang chờ; innodb_rollback_on_timeout có thể thay đổi phạm vi rollback.
- MyISAM không hỗ trợ transaction; ROLLBACK không hoàn tác thay đổi của bảng MyISAM.
- INSERT IGNORE và UPDATE IGNORE có thể bỏ qua hàng lỗi và tiếp tục, nên không có cùng hành vi với statement thất bại thông thường.
- Nhiều câu DDL gây implicit commit; atomic DDL không đồng nghĩa DDL có thể rollback cùng transaction DML.
- ROLLBACK không thu hồi side effect ngoài MySQL; dùng idempotency và transactional outbox khi tích hợp dịch vụ.
- Atomicity không thay thế consistency, isolation hoặc durability; cần kiểm tra điều kiện nghiệp vụ, khóa, engine và cấu hình.

Khi phân biệt được ranh giới của statement và transaction, bạn sẽ xử lý lỗi đúng phạm vi, biết khi nào cần rollback toàn bộ và tránh commit một phần quy trình nghiệp vụ ngoài ý muốn. Hãy luôn xác định storage engine, autocommit, loại lỗi và ranh giới commit trước khi xây dựng logic retry.
