# Kiểm chứng hành vi sau lỗi, SAVEPOINT và ROLLBACK

Khi một câu SQL thất bại trong transaction, ứng dụng có thể tiếp tục làm việc hay phải hủy toàn bộ transaction? Câu trả lời phụ thuộc vào database engine, loại lỗi và cấu hình transaction.

Một lỗi như vi phạm UNIQUE hoặc CHECK có thể chỉ làm statement hiện tại thất bại ở một số hệ quản trị. Ở hệ quản trị khác, transaction có thể chuyển sang trạng thái lỗi và không chấp nhận thêm câu lệnh cho đến khi rollback. Một số lỗi concurrency như deadlock hoặc serialization failure thường buộc transaction phải được hủy và chạy lại.

Ba lệnh cần hiểu rõ:

- **SAVEPOINT:** đánh dấu một vị trí bên trong transaction để có thể quay lại.
- **ROLLBACK TO SAVEPOINT:** hủy các thay đổi sau savepoint và tiếp tục transaction nếu engine cho phép.
- **ROLLBACK:** hủy toàn bộ transaction chưa commit và kết thúc transaction đó.

Bài thực nghiệm này giúp quan sát:

1. Điều gì xảy ra khi một statement vi phạm constraint.
2. Vì sao MySQL, PostgreSQL và SQL Server có thể phản ứng khác nhau sau cùng một lỗi.
3. Cách dùng savepoint để hủy một phần công việc.
4. Lock và transaction khác bị ảnh hưởng như thế nào sau rollback.
5. Khi nào cần rollback toàn bộ và retry từ đầu.

## 1. Phân biệt lỗi statement với lỗi transaction

Một câu SQL có thể thất bại vì dữ liệu không hợp lệ, vi phạm constraint, hết thời gian chờ lock hoặc deadlock. Không phải mọi lỗi đều có cùng phạm vi rollback.

Cần phân biệt hai khái niệm:

- **Statement failure:** câu SQL hiện tại không hoàn tất. Database có thể hoàn tác những thay đổi do statement đó tạo ra.
- **Transaction failure/abort:** transaction không thể tiếp tục commit theo trạng thái hiện tại. Ứng dụng phải rollback toàn bộ hoặc phục hồi về savepoint nếu engine và loại lỗi cho phép.

Ví dụ, một transaction thực hiện:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

INSERT INTO payments (payment_id, account_id, amount)
VALUES (1001, 10, -100);

COMMIT;
~~~

Nếu cột amount có CHECK constraint yêu cầu giá trị không âm, INSERT thất bại. Kết quả tiếp theo phụ thuộc engine:

- Có engine hoàn tác statement INSERT nhưng transaction vẫn hoạt động. UPDATE số dư vẫn còn là thay đổi chưa commit.
- Có engine đánh dấu transaction ở trạng thái aborted. Mọi statement tiếp theo đều thất bại cho đến khi rollback về savepoint hoặc rollback transaction.
- Có cấu hình khiến lỗi statement làm transaction trở thành uncommittable, chỉ còn có thể rollback toàn bộ.

Vì vậy, không nên thấy một câu SQL báo lỗi rồi mặc định rằng mọi thay đổi trước đó đã tự động bị hủy.

## 2. Chuẩn bị dữ liệu cho thực nghiệm hai phiên

Mở hai kết nối SQL độc lập đến cùng một database. Gọi chúng là:

- **Session A:** thực hiện transaction, tạo savepoint và gây lỗi.
- **Session B:** quan sát trạng thái dữ liệu hoặc thử cập nhật cùng hàng để kiểm tra lock.

Ví dụ dưới đây dùng MySQL InnoDB làm môi trường thực hành chính. Bảng có CHECK constraint và UNIQUE constraint:

~~~sql
DROP TABLE IF EXISTS tx_recovery_lab;

CREATE TABLE tx_recovery_lab (
    id INT NOT NULL PRIMARY KEY,
    balance INT NOT NULL,
    reference_code VARCHAR(30) NOT NULL,
    CONSTRAINT ck_balance_non_negative
        CHECK (balance >= 0),
    CONSTRAINT uq_reference_code
        UNIQUE (reference_code)
) ENGINE = InnoDB;

INSERT INTO tx_recovery_lab (id, balance, reference_code)
VALUES
    (1, 1000, 'REF-A'),
    (2, 2000, 'REF-B');
~~~

Kiểm tra dữ liệu ban đầu:

~~~sql
SELECT *
FROM tx_recovery_lab
ORDER BY id;
~~~

Kết quả:

| id | balance | reference_code |
|---:|---:|---|
| 1 | 1000 | REF-A |
| 2 | 2000 | REF-B |

Các ví dụ giả định MySQL 8.0.16 trở lên để CHECK constraint được thực thi. Các phiên bản MySQL cũ hơn có thể phân tích cú pháp CHECK nhưng không thực thi constraint như mong đợi.

Nếu dùng PostgreSQL hoặc SQL Server, cần tạo bảng tương đương bằng kiểu dữ liệu và cú pháp của engine đó. Không chạy lệnh DROP TABLE hoặc tạo lại bảng trong khi một session còn transaction đang mở.

## 3. Thực nghiệm 1: Statement lỗi vì CHECK constraint

Mục tiêu là kiểm chứng một câu UPDATE vi phạm CHECK có làm mất toàn bộ transaction hay không.

### Bước 1: Session A bắt đầu transaction

~~~sql
START TRANSACTION;

UPDATE tx_recovery_lab
SET balance = balance - 100
WHERE id = 1;
~~~

Thay đổi chưa commit. Trong transaction A, balance của hàng 1 là 900.

### Bước 2: Session A chạy statement gây lỗi

~~~sql
UPDATE tx_recovery_lab
SET balance = -1
WHERE id = 1;
~~~

Database trả lỗi CHECK constraint vì balance không được âm.

### Bước 3: Quan sát Session A

Thử chạy:

~~~sql
SELECT balance
FROM tx_recovery_lab
WHERE id = 1;
~~~

Với MySQL InnoDB, lỗi constraint thông thường làm statement hiện tại thất bại và hoàn tác thay đổi của statement đó. Transaction thường vẫn hoạt động; SELECT tiếp theo có thể thấy balance = 900 trong transaction A.

Tuy nhiên, hành vi này không thể áp dụng cho mọi loại lỗi. Deadlock, lock wait timeout và một số lỗi khác có quy tắc rollback riêng.

### Bước 4: Session B kiểm tra dữ liệu đã commit

Trong Session B:

~~~sql
SELECT balance
FROM tx_recovery_lab
WHERE id = 1;
~~~

Session B vẫn thấy 1000 vì UPDATE của A chưa commit.

Sự khác biệt:

| Session | Giá trị quan sát |
|---|---:|
| A, bên trong transaction chưa commit | 900 |
| B, transaction khác | 1000 |

Session A đang nhìn thấy thay đổi của chính transaction mình. Session B chỉ nhìn thấy dữ liệu đã commit.

### Bước 5: Quyết định commit hoặc rollback

Nếu nghiệp vụ cho phép giữ thay đổi đầu tiên, A có thể:

~~~sql
COMMIT;
~~~

Sau commit, Session B đọc lại sẽ thấy 900.

Nếu toàn bộ thao tác phải được hủy khi một bước thất bại, A cần:

~~~sql
ROLLBACK;
~~~

Khi đó balance trở về 1000.

Điểm quan trọng: MySQL InnoDB thường không tự động rollback toàn bộ transaction chỉ vì CHECK violation của một statement. Ứng dụng phải quyết định transaction có còn hợp lệ về mặt nghiệp vụ hay không.

## 4. Thực nghiệm 2: Dùng SAVEPOINT để phục hồi một phần công việc

Savepoint đánh dấu vị trí bên trong transaction. Nếu một bước sau đó thất bại hoặc không còn cần thiết, ứng dụng có thể quay về điểm đã đánh dấu.

Đặt dữ liệu ban đầu về trạng thái đã biết:

~~~sql
UPDATE tx_recovery_lab
SET balance = 1000
WHERE id = 1;
~~~

Trong Session A:

~~~sql
START TRANSACTION;

-- Bước nghiệp vụ bắt buộc.
UPDATE tx_recovery_lab
SET balance = balance - 100
WHERE id = 1;

-- Đánh dấu trạng thái sau bước bắt buộc.
SAVEPOINT after_debit;

-- Bước tùy chọn.
UPDATE tx_recovery_lab
SET balance = balance - 500
WHERE id = 1;

-- Hủy riêng bước tùy chọn.
ROLLBACK TO SAVEPOINT after_debit;

-- Kiểm tra trong transaction.
SELECT balance
FROM tx_recovery_lab
WHERE id = 1;
~~~

Kết quả trong Session A là 900:

| Thao tác | Giá trị balance |
|---|---:|
| Ban đầu | 1000 |
| Trừ 100 | 900 |
| Trừ thêm 500 | 400 |
| Rollback về after_debit | 900 |

Thay đổi trừ 500 bị hủy, nhưng thay đổi trừ 100 trước savepoint vẫn còn.

Nếu nghiệp vụ chấp nhận kết quả này, A có thể:

~~~sql
COMMIT;
~~~

Session B sau đó sẽ thấy balance = 900.

Nếu A thực hiện ROLLBACK thay vì COMMIT, cả thay đổi trừ 100 trước savepoint cũng bị hủy và balance trở về 1000.

### Savepoint không phải transaction độc lập

SAVEPOINT không commit phần dữ liệu trước nó. Các thay đổi trước savepoint vẫn thuộc transaction bên ngoài và chưa được transaction khác nhìn thấy như dữ liệu đã commit.

Có thể hình dung:

~~~text
BEGIN
  |
  +-- UPDATE bắt buộc
  |
  +-- SAVEPOINT S1
  |
  +-- UPDATE tùy chọn
  |
  +-- ROLLBACK TO S1
  |       |
  |       +-- Hủy thay đổi sau S1
  |       +-- Giữ thay đổi trước S1
  |
  +-- Tiếp tục transaction
  |
  +-- COMMIT hoặc ROLLBACK toàn bộ
~~~

Một savepoint không tạo transaction độc lập và không thể commit riêng phần công việc trước nó. Chỉ transaction bên ngoài mới quyết định commit hoặc rollback cuối cùng.

## 5. Thực nghiệm 3: Lỗi xảy ra sau SAVEPOINT

Savepoint đặc biệt hữu ích khi một statement gây lỗi làm transaction không thể tiếp tục bình thường.

Có thể dùng lại bảng thực nghiệm. Đảm bảo Session A không còn transaction trước đó.

### MySQL InnoDB

~~~sql
START TRANSACTION;

UPDATE tx_recovery_lab
SET balance = balance - 100
WHERE id = 1;

SAVEPOINT before_optional_step;

-- Gây lỗi CHECK.
UPDATE tx_recovery_lab
SET balance = -1
WHERE id = 1;
~~~

Sau lỗi, MySQL InnoDB thường chỉ rollback statement vi phạm constraint. Transaction vẫn có thể tiếp tục:

~~~sql
SELECT balance
FROM tx_recovery_lab
WHERE id = 1;
~~~

Kết quả trong transaction A là 900.

Có thể tiếp tục một thao tác hợp lệ:

~~~sql
UPDATE tx_recovery_lab
SET reference_code = 'REF-A-UPDATED'
WHERE id = 1;

COMMIT;
~~~

Savepoint không bắt buộc phải được dùng sau mọi statement error ở InnoDB. Nó có ích khi muốn chủ động hủy một chuỗi thay đổi tùy chọn hoặc phục hồi về một mốc trước đó.

### PostgreSQL

PostgreSQL xử lý statement error khác. Nếu một statement thất bại trong transaction block mà không nằm trong subtransaction có thể phục hồi, transaction chuyển sang trạng thái aborted. Các statement tiếp theo thường nhận lỗi dạng:

~~~text
current transaction is aborted,
commands ignored until end of transaction block
~~~

Có thể dùng savepoint trước bước có khả năng thất bại:

~~~sql
BEGIN;

UPDATE tx_recovery_lab
SET balance = balance - 100
WHERE id = 1;

SAVEPOINT before_optional_step;

-- Gây lỗi CHECK.
UPDATE tx_recovery_lab
SET balance = -1
WHERE id = 1;
~~~

Sau lỗi, cần rollback về savepoint:

~~~sql
ROLLBACK TO SAVEPOINT before_optional_step;

SELECT balance
FROM tx_recovery_lab
WHERE id = 1;

COMMIT;
~~~

Sau ROLLBACK TO SAVEPOINT, transaction có thể tiếp tục. Thay đổi trước savepoint vẫn còn; statement lỗi và các thay đổi sau savepoint bị hủy.

Nếu không có savepoint, ứng dụng phải rollback toàn bộ transaction trước khi bắt đầu transaction mới.

### So sánh

| Hành vi sau CHECK violation | MySQL InnoDB | PostgreSQL |
|---|---|---|
| Statement lỗi được hoàn tác | Có | Có |
| Transaction thường còn sử dụng được ngay | Có, với lỗi constraint thông thường | Không, transaction block chuyển sang trạng thái aborted |
| Có thể dùng ROLLBACK TO SAVEPOINT để phục hồi | Có | Có |
| Có thể tiếp tục sau khi phục hồi | Thường có | Có |
| Nếu không có savepoint | Có thể tiếp tục theo chính sách ứng dụng | Phải rollback transaction |

Đây là khác biệt quan trọng khi viết code dùng chung cho nhiều database. Một chiến lược bắt exception rồi tiếp tục chạy SQL có thể hoạt động ở MySQL nhưng thất bại ở PostgreSQL nếu không phục hồi transaction về savepoint.

## 6. SAVEPOINT, ROLLBACK TO SAVEPOINT và RELEASE SAVEPOINT

Ba thao tác thường được dùng cùng nhau:

~~~sql
SAVEPOINT optional_work;

-- Thực hiện các câu SQL.

ROLLBACK TO SAVEPOINT optional_work;

-- Hoặc nếu muốn giữ các thay đổi sau savepoint:
RELEASE SAVEPOINT optional_work;
~~~

### SAVEPOINT

Tạo một mốc có tên trong transaction:

~~~sql
SAVEPOINT before_shipping;
~~~

Từ thời điểm này, ứng dụng có thể rollback các thay đổi sau mốc đó.

### ROLLBACK TO SAVEPOINT

Quay lại mốc đã tạo:

~~~sql
ROLLBACK TO SAVEPOINT before_shipping;
~~~

Các thay đổi sau savepoint bị hoàn tác. Transaction bên ngoài vẫn còn hoạt động nếu engine cho phép tiếp tục.

Trong PostgreSQL, savepoint vẫn còn tồn tại sau ROLLBACK TO SAVEPOINT và có thể được sử dụng lại cho các thao tác tiếp theo. Nếu muốn loại bỏ nó, dùng RELEASE SAVEPOINT.

### RELEASE SAVEPOINT

Loại bỏ savepoint mà không rollback các thay đổi:

~~~sql
RELEASE SAVEPOINT before_shipping;
~~~

Release không commit transaction. Những thay đổi trước và sau savepoint vẫn thuộc transaction bên ngoài.

### COMMIT hoặc ROLLBACK toàn transaction

~~~sql
COMMIT;
~~~

Commit toàn bộ thay đổi còn lại trong transaction.

~~~sql
ROLLBACK;
~~~

Hủy toàn bộ thay đổi chưa commit và kết thúc transaction.

Bảng tóm tắt:

| Lệnh | Tác dụng | Kết thúc transaction? |
|---|---|---|
| SAVEPOINT S | Tạo mốc phục hồi | Không |
| ROLLBACK TO S | Hủy thay đổi sau S | Không |
| RELEASE S | Bỏ mốc S, giữ thay đổi | Không |
| COMMIT | Commit toàn bộ thay đổi còn lại | Có |
| ROLLBACK | Hủy toàn bộ thay đổi chưa commit | Có |

Cú pháp savepoint có khác biệt nhỏ giữa các hệ quản trị. MySQL, PostgreSQL và SQL Server đều hỗ trợ savepoint nhưng cách đặt tên, lồng savepoint và xử lý lỗi cần xem theo engine.

## 7. Thực nghiệm hai phiên: quan sát lock sau SAVEPOINT và ROLLBACK TO

Rollback một phần thay đổi dữ liệu không đồng nghĩa transaction đã kết thúc. Vì transaction vẫn mở, Session B có thể tiếp tục phải chờ tài nguyên mà Session A đang giữ.

Thử nghiệm dưới đây dùng hai hàng khác nhau.

Đặt lại dữ liệu:

~~~sql
UPDATE tx_recovery_lab
SET balance = 1000
WHERE id = 1;

UPDATE tx_recovery_lab
SET balance = 2000
WHERE id = 2;
~~~

### Bước 1: Session A khóa hàng 1 trước savepoint

~~~sql
START TRANSACTION;

UPDATE tx_recovery_lab
SET balance = balance - 100
WHERE id = 1;

SAVEPOINT after_row_1;
~~~

A đã cập nhật hàng 1 và giữ lock ghi trong transaction.

### Bước 2: Session A cập nhật hàng 2 sau savepoint

~~~sql
UPDATE tx_recovery_lab
SET balance = balance - 200
WHERE id = 2;
~~~

A hiện có thay đổi chưa commit trên cả hàng 1 và hàng 2.

### Bước 3: Session B thử cập nhật hàng 2

Trong Session B:

~~~sql
UPDATE tx_recovery_lab
SET balance = balance + 50
WHERE id = 2;
~~~

B có thể phải chờ vì A đang giữ lock xung đột trên hàng 2.

### Bước 4: Session A rollback về savepoint

Trong Session A:

~~~sql
ROLLBACK TO SAVEPOINT after_row_1;
~~~

Thay đổi balance của hàng 2 bị hoàn tác. Hàng 1 vẫn giữ thay đổi trừ 100 trong transaction A.

Sau đó quan sát Session B:

- Nếu B tiếp tục được, lock liên quan đến thay đổi sau savepoint đã được giải phóng theo hành vi của engine.
- Nếu B vẫn chờ, engine có thể tiếp tục giữ một số lock đến khi transaction kết thúc hoặc lock đó được giải phóng theo quy tắc riêng.
- Không suy luận rằng rollback về savepoint luôn giải phóng tất cả lock được lấy sau mốc đó.

Chi tiết giải phóng lock sau partial rollback khác nhau theo engine và loại lock. Cần kiểm tra tài liệu phiên bản database đang chạy và xác nhận bằng lock monitoring.

### Bước 5: Kết thúc transaction A

Trong Session A:

~~~sql
COMMIT;
~~~

Sau khi A commit, mọi lock transaction còn giữ được giải phóng. Session B có thể tiếp tục nếu đang chờ lock của A.

Có thể lặp lại thử nghiệm bằng ROLLBACK toàn transaction:

~~~sql
ROLLBACK;
~~~

Rollback toàn bộ chắc chắn hủy thay đổi chưa commit của A và kết thúc transaction. Các lock transaction còn giữ được giải phóng theo cơ chế của engine.

### Điều cần quan sát

| Thời điểm | Session A | Session B |
|---|---|---|
| A cập nhật hàng 1 | Giữ lock hàng 1 | Có thể đọc dữ liệu đã commit cũ |
| A tạo savepoint | Transaction vẫn mở | Không thay đổi |
| A cập nhật hàng 2 | Giữ lock hàng 1 và hàng 2 | UPDATE hàng 2 có thể chờ |
| A rollback về savepoint | Thay đổi hàng 2 bị hoàn tác | Trạng thái chờ phụ thuộc lock release của engine |
| A COMMIT hoặc ROLLBACK | Transaction kết thúc, lock còn giữ được giải phóng | Có thể tiếp tục |

Bài thực nghiệm này giúp phân biệt **rollback dữ liệu về savepoint** với **kết thúc transaction và giải phóng toàn bộ lock**.

## 8. ROLLBACK toàn transaction giải phóng những gì?

Khi transaction rollback toàn bộ, database hủy các thay đổi chưa commit trong transaction đó. Các thay đổi này không được transaction khác nhìn thấy như dữ liệu đã commit.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE tx_recovery_lab
SET balance = balance - 100
WHERE id = 1;

UPDATE tx_recovery_lab
SET balance = balance + 100
WHERE id = 2;

ROLLBACK;
~~~

Sau rollback:

- Balance của hàng 1 trở về giá trị trước transaction.
- Balance của hàng 2 trở về giá trị trước transaction.
- Các row lock hoặc lock transaction liên quan được giải phóng theo quy tắc của engine.
- Transaction kết thúc.
- Ứng dụng cần mở transaction mới nếu muốn tiếp tục công việc.

Với InnoDB, undo log được dùng để hoàn tác thay đổi. Với PostgreSQL, tuple mới hoặc thay đổi trong transaction aborted không trở thành dữ liệu commit nhìn thấy được; việc dọn dẹp vật lý diễn ra theo cơ chế MVCC và VACUUM. SQL Server sử dụng transaction log để phục hồi thay đổi.

Rollback không nhất thiết xóa ngay mọi dấu vết vật lý hoặc dữ liệu nội bộ. Nó bảo đảm trạng thái logic của transaction được hoàn tác theo ACID.

## 9. SAVEPOINT có giải phóng lock không?

Đây là câu hỏi quan trọng khi dùng savepoint trong hệ thống nhiều transaction.

Không nên mặc định rằng ROLLBACK TO SAVEPOINT có cùng tác dụng giải phóng lock trên mọi database.

- **PostgreSQL:** tài liệu PostgreSQL quy định lock được lấy sau savepoint sẽ được giải phóng khi rollback về savepoint, theo phạm vi lock mà PostgreSQL quản lý trong subtransaction.
- **SQL Server:** rollback về savepoint có thể giải phóng một số lock được lấy sau savepoint, nhưng lock escalation và lock conversion không nhất thiết được hoàn tác theo cách tương tự.
- **MySQL InnoDB:** rollback về savepoint hoàn tác thay đổi dữ liệu sau mốc. Việc giải phóng lock phụ thuộc loại lock và cơ chế nội bộ; không nên suy ra từ việc giá trị dữ liệu đã quay lại. Cần quan sát lock thực tế trên phiên bản đang dùng.

Điểm chung an toàn khi thiết kế là:

1. SAVEPOINT không kết thúc transaction.
2. ROLLBACK TO SAVEPOINT không commit phần dữ liệu trước mốc.
3. Transaction vẫn có thể giữ lock từ các thao tác trước savepoint.
4. ROLLBACK toàn bộ hoặc COMMIT mới kết thúc transaction.
5. Nếu Session B đang chờ, phải xác định lock cụ thể thay vì chỉ dựa trên việc Session A đã rollback về savepoint.

Một transaction có thể rollback một bước nhưng vẫn tiếp tục giữ lock trên các hàng đã cập nhật trước savepoint. Vì vậy, dùng savepoint không thay thế việc giữ transaction ngắn.

## 10. Deadlock và lock timeout có phạm vi rollback khác nhau

Không phải mọi lỗi lock đều có thể phục hồi bằng ROLLBACK TO SAVEPOINT.

### Deadlock

Deadlock xảy ra khi các transaction chờ tài nguyên theo chu trình. Database phát hiện chu trình và chọn một transaction làm victim.

- MySQL InnoDB thường rollback toàn bộ transaction được chọn làm victim.
- PostgreSQL hủy transaction bị chọn; transaction ở trạng thái aborted và thông thường ứng dụng phải rollback rồi chạy lại transaction.
- SQL Server rollback transaction được chọn làm deadlock victim, thường trả error 1205.

Khi transaction đã bị engine rollback toàn bộ, savepoint cũ không còn là điểm phục hồi để tiếp tục transaction đó.

### Lock wait timeout trong MySQL InnoDB

Với InnoDB, lock wait timeout mặc định thường chỉ rollback statement bị timeout, không nhất thiết rollback toàn bộ transaction. Tuy nhiên, biến cấu hình innodb_rollback_on_timeout có thể thay đổi hành vi để rollback toàn transaction.

Ví dụ kiểm tra cấu hình:

~~~sql
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW VARIABLES LIKE 'innodb_rollback_on_timeout';
~~~

Không nên mặc định timeout và deadlock có cùng phạm vi rollback.

### PostgreSQL

PostgreSQL thường đưa transaction block vào trạng thái aborted sau lock timeout hoặc lỗi statement. Nếu lỗi xảy ra trong phạm vi savepoint và transaction có thể phục hồi về savepoint, ứng dụng có thể dùng ROLLBACK TO SAVEPOINT. Với deadlock hoặc serialization failure, cách xử lý an toàn phổ biến là rollback transaction và retry toàn bộ.

### SQL Server

SQL Server có thể giữ transaction ở trạng thái committable hoặc chuyển sang uncommittable tùy loại lỗi và cấu hình như SET XACT_ABORT.

Dùng XACT_STATE() để kiểm tra:

- 1: có transaction đang hoạt động và có thể commit.
- -1: transaction đang hoạt động nhưng không thể commit; chỉ có thể rollback toàn bộ.
- 0: không có transaction đang hoạt động.

Không nên giả định savepoint luôn cho phép phục hồi sau mọi lỗi SQL Server.

## 11. Kiểm tra transaction state trong SQL Server

SQL Server cung cấp XACT_STATE() và @@TRANCOUNT để kiểm tra trạng thái transaction.

Ví dụ:

~~~sql
SET XACT_ABORT OFF;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.Accounts
    SET Balance = Balance - 100
    WHERE AccountId = 10;

    SAVE TRANSACTION BeforeOptionalStep;

    -- Thực hiện một thao tác có thể phát sinh lỗi.

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    SELECT
        XACT_STATE() AS transaction_state,
        @@TRANCOUNT AS transaction_count,
        ERROR_NUMBER() AS error_number,
        ERROR_MESSAGE() AS error_message;

    IF XACT_STATE() = 1
    BEGIN
        -- Transaction còn committable.
        ROLLBACK TRANSACTION BeforeOptionalStep;

        -- Có thể tiếp tục xử lý nếu nghiệp vụ cho phép.
        COMMIT TRANSACTION;
    END
    ELSE IF XACT_STATE() = -1
    BEGIN
        -- Transaction không thể commit hoặc rollback về savepoint.
        ROLLBACK TRANSACTION;
    END
    ELSE
    BEGIN
        -- Không còn transaction đang hoạt động.
    END;
END CATCH;
~~~

Đây là khung minh họa cho xử lý lỗi. Trong code thực tế, phải bảo đảm savepoint đã được tạo trước khi dùng nó và nhánh xử lý phù hợp với loại lỗi.

Nếu bật:

~~~sql
SET XACT_ABORT ON;
~~~

một số lỗi runtime làm transaction bị hủy hoặc chuyển sang trạng thái không thể commit. XACT_STATE() vẫn là cách kiểm tra trạng thái hiện tại thay vì đoán từ loại exception ở tầng ứng dụng.

@@TRANCOUNT cho biết số mức BEGIN TRANSACTION chưa được cân bằng, nhưng không cho biết transaction có còn committable hay không. Dùng kết hợp hai hàm khi xử lý lỗi.

## 12. Deadlock và serialization failure thường cần retry toàn bộ

Savepoint hữu ích khi một phần công việc có thể bị bỏ qua mà transaction chính vẫn hợp lệ. Nó không thay thế retry toàn transaction đối với các lỗi concurrency làm mất hiệu lực quyết định đã đọc.

Ví dụ hai transaction cùng đọc số lượng tồn kho:

~~~text
T1 đọc quantity = 10
T2 đọc quantity = 10

T1 cập nhật quantity = 8
T2 cập nhật quantity = 7

Một transaction có thể bị hủy hoặc cập nhật có thể xung đột.
~~~

Nếu database báo serialization failure hoặc deadlock victim, các lần đọc trước đó có thể không còn phù hợp với trạng thái hiện tại. Chạy lại câu UPDATE cuối cùng không đủ.

Quy trình retry:

1. Kết thúc transaction cũ bằng rollback nếu driver chưa tự làm việc đó.
2. Bắt đầu transaction mới.
3. Đọc lại dữ liệu cần thiết.
4. Kiểm tra lại điều kiện nghiệp vụ.
5. Tính lại các thay đổi.
6. Ghi dữ liệu và commit.
7. Giới hạn số lần retry và dùng backoff có jitter.

Pseudocode:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    BEGIN NEW TRANSACTION

    read current state
    validate business rules
    calculate changes
    write changes

    COMMIT
    return SUCCESS

catch deadlock_or_serialization_failure:
    ROLLBACK
    if attempt == MAX_ATTEMPTS:
        return TEMPORARY_CONFLICT
    wait with bounded backoff and jitter
~~~

Không retry vô hạn. Nếu cùng một tài nguyên liên tục bị tranh chấp, retry có thể làm tăng tải và độ trễ. Cần điều tra thứ tự lock, transaction duration, index và mức độ cạnh tranh.

## 13. Cách dùng SAVEPOINT trong nghiệp vụ nhiều bước

Savepoint phù hợp khi transaction có một phần công việc tùy chọn hoặc có thể phục hồi độc lập, nhưng các bước trước đó vẫn có giá trị nếu bước tùy chọn thất bại.

Ví dụ xử lý đơn hàng:

~~~sql
BEGIN;

-- Bước bắt buộc: tạo đơn hàng.
INSERT INTO orders (order_id, status, total_amount)
VALUES (1001, 'PENDING', 500000);

SAVEPOINT optional_discount;

-- Bước tùy chọn: áp dụng mã giảm giá.
UPDATE orders
SET total_amount = total_amount - 50000
WHERE order_id = 1001;

-- Nếu mã giảm giá không hợp lệ:
ROLLBACK TO SAVEPOINT optional_discount;

-- Đơn hàng vẫn được tạo ở trạng thái PENDING.
COMMIT;
~~~

Ví dụ này chỉ minh họa phạm vi rollback. Logic xác thực mã giảm giá và cập nhật giá thực tế cần được thiết kế theo quy tắc nghiệp vụ.

Một số trường hợp phù hợp:

- Thử áp dụng một lựa chọn phụ, nếu thất bại thì bỏ lựa chọn đó.
- Thực hiện một nhóm cập nhật tùy chọn trong transaction lớn hơn.
- Phục hồi transaction sau lỗi constraint nếu engine cho phép savepoint recovery.
- Thực hiện import nhiều nhóm dữ liệu, muốn rollback một nhóm nhưng giữ các nhóm hợp lệ trước đó trong cùng transaction.

Những trường hợp không phù hợp:

- Một quy trình mà mọi bước phải thành công hoặc thất bại cùng nhau.
- Một lỗi concurrency đã hủy toàn bộ transaction.
- Một thao tác bên ngoài database đã xảy ra và không thể rollback bằng SQL.
- Một transaction quá dài, giữ lock trong lúc chờ dịch vụ hoặc người dùng.

Không nên dùng savepoint để che giấu lỗi nghiệp vụ. Nếu một bước bắt buộc thất bại, commit phần còn lại có thể tạo ra trạng thái không hợp lệ.

## 14. SAVEPOINT trong Java JDBC

JDBC cung cấp API savepoint qua Connection.

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debitRequiredStep(connection);

        Savepoint optionalStep =
            connection.setSavepoint("optional_step");

        try {
            applyOptionalChange(connection);
            connection.releaseSavepoint(optionalStep);
        } catch (SQLException optionalFailure) {
            connection.rollback(optionalStep);

            // Chỉ tiếp tục nếu lỗi tùy chọn được phép bỏ qua.
            // Có thể ghi nhận lỗi để trả kết quả phù hợp.
        }

        connection.commit();
    } catch (Exception failure) {
        connection.rollback();
        throw failure;
    }
}
~~~

Các phương thức quan trọng:

- setSavepoint() hoặc setSavepoint(name): tạo savepoint.
- rollback(savepoint): rollback đến savepoint.
- releaseSavepoint(savepoint): giải phóng savepoint.
- rollback(): rollback toàn bộ transaction.
- commit(): commit toàn bộ transaction còn lại.

Cần lưu ý:

- Auto-commit phải được tắt để quản lý transaction nhiều statement.
- Driver và database phải hỗ trợ savepoint.
- Sau lỗi SQL, trạng thái transaction phụ thuộc engine. JDBC không tự biến một transaction aborted thành transaction có thể tiếp tục.
- Nếu rollback(savepoint) thất bại, không nên tiếp tục dùng connection như thể transaction đã phục hồi.
- Cần rollback toàn bộ trong nhánh xử lý lỗi không thể phục hồi.
- Luôn trả connection về pool ở trạng thái sạch; transaction chưa kết thúc có thể làm ảnh hưởng request tiếp theo.

Nếu dùng connection pool, transaction manager thường quản lý commit/rollback. Không nên trộn JDBC thủ công với transaction do framework quản lý mà không hiểu cách lấy đúng connection gắn với transaction hiện tại.

## 15. SAVEPOINT trong JPA và Spring

JPA không cung cấp một API savepoint độc lập, chuẩn hóa giống JDBC Connection.setSavepoint(). Savepoint thường được quản lý ở tầng JDBC hoặc transaction manager.

Spring có Propagation.NESTED trong một số transaction manager. Với transaction manager dựa trên JDBC, nested transaction có thể được triển khai bằng savepoint nếu driver và transaction manager hỗ trợ.

Ví dụ khái niệm:

~~~java
@Transactional
public void processOrder() {
    createRequiredOrderData();

    try {
        optionalStepService.applyOptionalChange();
    } catch (OptionalStepException ex) {
        recordOptionalFailure(ex);
    }
}
~~~

Nếu optionalStepService dùng propagation NESTED và transaction manager hỗ trợ savepoint, phần công việc nested có thể được rollback riêng. Tuy nhiên, việc bắt exception trong code không tự tạo savepoint.

Cần phân biệt:

- **REQUIRED:** tham gia transaction hiện tại nếu có.
- **REQUIRES_NEW:** tạm ngưng transaction hiện tại và tạo transaction độc lập mới.
- **NESTED:** có thể dùng savepoint trong transaction hiện tại nếu transaction manager hỗ trợ.

REQUIRES_NEW không tương đương savepoint. Transaction mới có thể commit độc lập ngay cả khi transaction ngoài rollback. Điều đó có thể phù hợp với audit log trong một số thiết kế, nhưng cũng có thể tạo trạng thái không nhất quán nếu dùng sai.

Với Hibernate/JPA, một exception khi flush có thể làm persistence context hoặc transaction bị đánh dấu rollback-only. Dù database có thể phục hồi về savepoint ở tầng JDBC, ORM không nhất thiết cho phép tiếp tục sử dụng các entity đã quản lý như chưa có lỗi. Cần tuân theo transaction manager và provider; sau lỗi nghiêm trọng, rollback transaction và tạo persistence context mới thường là lựa chọn an toàn hơn.

## 16. Lệnh DDL và implicit commit

Một nguyên nhân làm savepoint biến mất là các lệnh SQL có implicit commit.

MySQL có nhiều câu lệnh DDL hoặc quản trị gây implicit commit, chẳng hạn một số dạng:

- CREATE TABLE.
- ALTER TABLE.
- DROP TABLE.
- CREATE INDEX hoặc các thay đổi schema tương ứng.
- Một số lệnh quản trị transaction hoặc cấu hình.

Khi một câu lệnh gây implicit commit, transaction hiện tại có thể bị commit trước khi lệnh chạy hoặc sau khi lệnh hoàn tất theo quy tắc của MySQL. Savepoint đã tạo có thể không còn tồn tại.

Ví dụ không nên giả định đoạn sau có thể rollback schema change bằng savepoint:

~~~sql
START TRANSACTION;

SAVEPOINT before_ddl;

ALTER TABLE tx_recovery_lab
ADD COLUMN note VARCHAR(100);

ROLLBACK TO SAVEPOINT before_ddl;
~~~

DDL trong MySQL thường gây implicit commit; ROLLBACK TO SAVEPOINT có thể báo savepoint không tồn tại hoặc không thể khôi phục schema change như mong đợi.

PostgreSQL hỗ trợ transaction cho nhiều loại DDL hơn, nhưng vẫn có những lệnh không thể chạy trong transaction block hoặc có giới hạn riêng. SQL Server có quy tắc transactional DDL khác tùy statement.

Không dùng savepoint để giả định mọi loại thay đổi đều có thể rollback. Cần kiểm tra lệnh cụ thể và engine.

## 17. Transaction rollback không hoàn tác side effect bên ngoài

ROLLBACK chỉ hoàn tác các thay đổi nằm trong transaction database mà engine quản lý. Nó không tự hoàn tác:

- Email đã gửi.
- HTTP request đã được dịch vụ bên ngoài xử lý.
- Tiền đã được payment provider thu.
- Message đã được publish lên broker độc lập.
- File đã ghi lên filesystem.
- Tác vụ đã được gửi đến hệ thống khác.

Ví dụ:

~~~text
BEGIN DATABASE TRANSACTION
    |
    +-- UPDATE orders
    |
    +-- Gọi Payment API -> thanh toán thành công
    |
    +-- INSERT payment record -> lỗi
    |
    +-- ROLLBACK
~~~

Database rollback đơn hàng, nhưng khoản thanh toán ở provider có thể vẫn tồn tại. Savepoint cũng không thể hoàn tác khoản thanh toán đó.

Với quy trình nhiều hệ thống, có thể dùng:

- Transactional Outbox để ghi ý định phát event cùng transaction.
- Idempotency key để retry lời gọi dịch vụ ngoài an toàn.
- Saga và compensating action khi cần bù trừ một side effect đã xảy ra.
- Trạng thái PENDING/UNKNOWN để đối soát khi kết quả HTTP không xác định.

Không giữ row lock hoặc savepoint trong lúc chờ HTTP API. Transaction dài làm tăng lock contention và rủi ro timeout.

## 18. Bảng so sánh hành vi sau lỗi theo database

Cùng một lỗi statement có thể tạo trạng thái transaction khác nhau:

| Tình huống | MySQL InnoDB | PostgreSQL | SQL Server |
|---|---|---|---|
| CHECK/UNIQUE violation thông thường | Thường rollback statement; transaction có thể tiếp tục | Transaction block bị đánh dấu aborted nếu không phục hồi về savepoint | Phụ thuộc loại lỗi và XACT_ABORT; có thể còn committable hoặc bị uncommittable |
| ROLLBACK TO SAVEPOINT | Hủy thay đổi sau mốc, transaction tiếp tục | Phục hồi transaction về savepoint | ROLLBACK TRANSACTION savepoint nếu transaction còn phù hợp |
| Deadlock victim | Thường rollback toàn transaction | Transaction bị hủy | Transaction victim bị rollback |
| Lock timeout | Thường rollback statement theo mặc định; cấu hình có thể rollback toàn transaction | Statement lỗi làm transaction block aborted nếu không phục hồi | Phụ thuộc statement, timeout và XACT_ABORT |
| Full ROLLBACK | Hủy toàn bộ thay đổi chưa commit | Hủy transaction | Hủy transaction |
| DDL | Nhiều DDL gây implicit commit | Nhiều DDL transactional, có ngoại lệ | Nhiều DDL có thể transactional, tùy statement |

Bảng là hướng dẫn khái quát. Phiên bản, engine lưu trữ, cấu hình session, driver và loại lỗi cụ thể có thể thay đổi kết quả. Khi code phụ thuộc vào hành vi sau lỗi, hãy kiểm chứng trên đúng môi trường production tương đương.

## 19. Cách kiểm tra transaction state và lock

### MySQL InnoDB

Xem transaction đang hoạt động:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx;
~~~

Xem lock đang được giữ hoặc chờ trên MySQL 8:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks;
~~~

Xem quan hệ giữa transaction chờ và transaction chặn:

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Kiểm tra cấu hình lock timeout:

~~~sql
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW VARIABLES LIKE 'innodb_rollback_on_timeout';
~~~

### PostgreSQL

Xem trạng thái session và transaction:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database();
~~~

Xem lock:

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid IS NOT NULL;
~~~

Sau một statement error, thử chạy SELECT tiếp theo trong cùng transaction để quan sát lỗi transaction aborted. Sau đó chạy ROLLBACK TO SAVEPOINT nếu đã tạo savepoint trước statement lỗi.

### SQL Server

Kiểm tra transaction state trong cùng session:

~~~sql
SELECT
    XACT_STATE() AS transaction_state,
    @@TRANCOUNT AS transaction_count;
~~~

Kiểm tra request đang chờ và blocker:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    status,
    wait_type,
    wait_time,
    command
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Cần có quyền phù hợp để đọc một số DMV. Dùng Extended Events hoặc công cụ quan sát tương đương khi cần phân tích deadlock.

## 20. Những nhầm lẫn thường gặp

**“Một statement lỗi thì database luôn rollback toàn transaction.”**

Không đúng. MySQL InnoDB thường rollback statement với lỗi constraint thông thường. PostgreSQL thường đánh dấu transaction block aborted. SQL Server phụ thuộc lỗi và cấu hình.

**“Một statement lỗi thì transaction luôn tiếp tục được.”**

Không đúng. PostgreSQL yêu cầu rollback transaction hoặc rollback về savepoint sau lỗi. SQL Server có thể chuyển transaction sang trạng thái uncommittable. Deadlock có thể khiến engine rollback toàn bộ transaction.

**“SAVEPOINT là transaction con có thể commit độc lập.”**

Không. Savepoint chỉ là mốc phục hồi bên trong transaction. COMMIT vẫn áp dụng cho toàn transaction bên ngoài.

**“ROLLBACK TO SAVEPOINT giải phóng mọi lock sau savepoint.”**

Không thể khẳng định cho mọi engine và mọi loại lock. Cần kiểm tra semantics cụ thể và quan sát lock thực tế.

**“Rollback về savepoint có nghĩa transaction đã kết thúc.”**

Không. Transaction vẫn mở và có thể giữ lock từ các thao tác trước savepoint.

**“Bắt exception trong Java là transaction tự phục hồi.”**

Không. Exception chỉ là cách ứng dụng nhận lỗi. Database transaction có thể đã aborted hoặc rollback-only. Phải dùng transaction manager và API phục hồi phù hợp.

**“Có thể rollback email hoặc payment bằng ROLLBACK SQL.”**

Không. Side effect ngoài database cần idempotency, Outbox, Saga hoặc đối soát.

**“Deadlock có thể giải quyết bằng cách rollback về savepoint.”**

Không nên dựa vào cách đó. Deadlock victim thường bị rollback toàn transaction. Cần bắt lỗi, tạo transaction mới và retry toàn bộ nghiệp vụ nếu còn hợp lệ.

## 21. Quy trình xử lý lỗi transaction trong ứng dụng

Khi một câu SQL thất bại, ứng dụng nên xác định phạm vi lỗi trước khi quyết định tiếp tục:

1. Lấy SQLSTATE, vendor error code và thông tin constraint nếu có.
2. Xác định lỗi thuộc nhóm constraint, deadlock, lock timeout, serialization failure, connection failure hay lỗi khác.
3. Kiểm tra transaction còn hoạt động và có thể commit hay không theo engine.
4. Nếu lỗi thuộc bước tùy chọn và transaction có thể phục hồi, rollback về savepoint đã tạo trước bước đó.
5. Nếu transaction đã bị abort hoặc uncommittable, rollback toàn bộ.
6. Nếu lỗi concurrency có thể retry, mở transaction mới, đọc lại dữ liệu và chạy lại toàn bộ logic.
7. Chỉ commit khi các bất biến nghiệp vụ vẫn thỏa.
8. Không phát side effect bên ngoài trước commit nếu chưa có cơ chế idempotency hoặc bù trừ.
9. Ghi log mã lỗi, transaction attempt, thời gian chờ và correlation ID để điều tra.

Một bảng quyết định:

| Loại lỗi | Hướng xử lý thường phù hợp |
|---|---|
| UNIQUE/CHECK violation ở bước tùy chọn | Rollback statement hoặc savepoint theo engine; xử lý quy tắc nghiệp vụ |
| UNIQUE/CHECK violation ở bước bắt buộc | Rollback transaction hoặc trả lỗi nghiệp vụ |
| Deadlock victim | Rollback toàn bộ và retry có giới hạn nếu an toàn |
| Serialization failure | Rollback toàn bộ, đọc lại snapshot và retry |
| Lock timeout | Kiểm tra transaction state; quyết định retry hoặc báo tài nguyên đang bận |
| Connection lost trong lúc COMMIT | Kết quả có thể không xác định; tra cứu bằng idempotency/reference ổn định |
| External API timeout | Không đoán thành công/thất bại; tra cứu hoặc retry bằng idempotency key |

## 22. Checklist thực nghiệm

Khi chạy bài thực nghiệm hai phiên, hãy ghi nhận:

- Database engine và phiên bản.
- Isolation level của Session A và B.
- Autocommit đang bật hay tắt.
- Loại statement gây lỗi.
- SQLSTATE hoặc vendor error code.
- Session A còn chạy SELECT được sau lỗi không?
- Session A có thể COMMIT không?
- Có cần ROLLBACK TO SAVEPOINT để phục hồi không?
- Session B nhìn thấy dữ liệu nào trước khi A commit?
- Session B có bị chặn khi A giữ lock không?
- Sau ROLLBACK TO SAVEPOINT, Session B còn chờ không?
- Sau full ROLLBACK, lock được giải phóng như thế nào?
- Thay đổi trước savepoint còn tồn tại sau partial rollback không?
- Có side effect ngoài database nào đã xảy ra không?

Thực hiện từng thử nghiệm riêng biệt. Trước khi chạy lại, kết thúc transaction ở cả hai session và đưa dữ liệu về trạng thái ban đầu. Nếu một câu lệnh đang chờ lock, phải quay lại session đang giữ lock để commit hoặc rollback; đừng mở thêm transaction không cần thiết.

## Kết luận

Một statement thất bại không nhất thiết làm transaction thất bại hoàn toàn. MySQL InnoDB, PostgreSQL và SQL Server có hành vi khác nhau về trạng thái transaction sau lỗi. Vì vậy, ứng dụng phải biết lỗi nào chỉ rollback statement, lỗi nào làm transaction aborted và lỗi nào buộc rollback toàn bộ.

SAVEPOINT cho phép đánh dấu một vị trí để hủy một phần công việc trong transaction. ROLLBACK TO SAVEPOINT không commit dữ liệu trước mốc và cũng không kết thúc transaction. ROLLBACK toàn bộ mới hủy mọi thay đổi chưa commit và giải phóng các lock transaction còn giữ theo quy tắc của engine.

Khi xử lý lỗi, hãy phân loại bằng SQLSTATE hoặc vendor code, kiểm tra transaction state, chỉ phục hồi về savepoint khi engine cho phép và retry toàn bộ transaction đối với deadlock hoặc serialization failure. Với Java/JDBC/JPA, cần phối hợp đúng transaction manager và persistence context. Các side effect ngoài database phải được bảo vệ riêng bằng idempotency, Outbox, Saga hoặc đối soát.
