# Autocommit và ranh giới giao dịch trong công cụ, ứng dụng PostgreSQL

Khi chạy hai câu `UPDATE` liên tiếp trong công cụ SQL, chúng có thể được commit **từng câu một**. Nhưng khi ứng dụng Java đặt `connection.setAutoCommit(false)` rồi chạy chính hai câu đó trên **một connection**, kết quả chỉ được commit khi ứng dụng gọi `commit()`. Nếu một câu thất bại, ứng dụng có thể dùng `rollback()` để hủy cả nhóm.

Sự khác biệt này quyết định tính đúng của nhiều nghiệp vụ. Ví dụ chuyển 100 đơn vị tiền từ tài khoản A sang B:

~~~text
Bước 1: A = A - 100
Bước 2: B = B + 100

Mong muốn:
  Thành công -> CẢ HAI bước được ghi nhận.
  Thất bại   -> KHÔNG bước nào được ghi nhận.
~~~

Nếu bước 1 đã commit riêng rồi kết nối mất trước bước 2, tổng tiền giữa hai tài khoản bị sai. Nếu cả hai nằm trong **cùng transaction**, PostgreSQL có thể bảo vệ tính nguyên tử của thay đổi dữ liệu.

Bài học này tập trung vào **autocommit và ranh giới giao dịch** trong PostgreSQL: statement độc lập, `BEGIN`/`COMMIT`/`ROLLBACK`, hai session khác nhau, cách chạy lệnh trong `psql` và GUI, JDBC, connection pool, Spring, Python và Node.js. Những phần sau giải thích lỗi làm transaction chuyển sang trạng thái aborted, savepoint, DDL, khóa, isolation, sự cố mạng khi commit và cách phát hiện `idle in transaction`.

## 1. Phân biệt statement, transaction, connection và session

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Statement** | Một câu SQL như `UPDATE ...` hoặc `SELECT ...` |
| **Transaction** | Một đơn vị công việc mà PostgreSQL commit hoặc rollback |
| **Connection/session** | Kết nối tới PostgreSQL, có trạng thái transaction riêng |
| **Autocommit** | Chính sách của client/driver để hoàn tất giao dịch cho các statement độc lập |
| **Connection pool** | Nơi ứng dụng mượn và trả connection, không tự gom mọi connection vào một transaction |

Một transaction bình thường của PostgreSQL gắn với **một connection**. Connection A mở transaction không có nghĩa connection B đang tham gia transaction đó.

~~~text
Connection A
    BEGIN
      UPDATE hàng X
      INSERT audit
    COMMIT

Connection B
    SELECT ...
    -- Giao dịch khác; không tự thuộc BEGIN của A.
~~~

Một connection có thể thực hiện nhiều transaction **lần lượt** trong vòng đời của nó. Transaction không đồng nhất với một phiên kết nối.

### 1.1. Ranh giới giao dịch tường minh

~~~sql
BEGIN;

UPDATE some_table SET ... WHERE ...;
INSERT INTO audit_log (...) VALUES (...);

COMMIT;
~~~

Nếu công việc không nên được lưu:

~~~sql
ROLLBACK;
~~~

Sơ đồ:

~~~text
                 BEGIN
                   |
           +-------v--------+
           | SQL 1          |
           | SQL 2          |
           | SQL 3          |
           +-------+--------+
                   |
            +------+------+
            |             |
          COMMIT        ROLLBACK
            |             |
      Lưu thay đổi   Hủy thay đổi
      transaction    chưa commit
~~~

### 1.2. Transaction và ACID

**Atomicity** là trọng tâm bài này: các thay đổi có tính giao dịch trong một transaction được commit cùng nhau hoặc rollback cùng nhau. Ngoài ra, **Consistency** gắn với constraint và quy tắc dữ liệu, **Isolation** kiểm soát tác động giữa các transaction đồng thời, **Durability** gắn với việc PostgreSQL bảo vệ kết quả đã commit theo cấu hình hệ thống.

Tính nguyên tử của transaction **không thay thế** kiểm tra nghiệp vụ: một `UPDATE` thành công nhưng tác động **0 hàng** có thể vẫn khiến một nghiệp vụ thiếu bước quan trọng.

## 2. Autocommit thực sự có nghĩa gì?

Trong nhiều client, **autocommit bật** nghĩa là các câu SQL chạy **riêng lẻ bên ngoài transaction tường minh** được commit khi statement hoàn thành thành công.

~~~text
AUTOCOMMIT ON, ba statement riêng:

UPDATE A;      -> transaction #1 -> COMMIT
UPDATE B;      -> transaction #2 -> COMMIT
INSERT audit;  -> transaction #3 -> COMMIT
~~~

Khi cần cả ba thao tác thuộc cùng đơn vị:

~~~text
BEGIN
  UPDATE A
  UPDATE B
  INSERT audit
COMMIT hoặc ROLLBACK
~~~

### 2.1. Một statement có thể thay đổi nhiều hàng

~~~sql
UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id IN (1, 2, 3);
~~~

Ngay cả khi không viết `BEGIN`, PostgreSQL vẫn thực hiện câu `UPDATE` trong phạm vi **một transaction ngầm** nếu nó là statement độc lập. Không phải mỗi hàng được sửa là một transaction riêng.

Khác biệt cốt lõi là **một statement tác động 3 hàng** so với **3 statement tách rời**.

### 2.2. Autocommit không phải tùy chọn chung của SQL server

Không dùng cú pháp sau làm cách chung để tắt autocommit PostgreSQL:

~~~sql
-- Không phải lệnh PostgreSQL phổ quát để điều khiển autocommit:
SET autocommit = off;
~~~

Chế độ được điều khiển theo công cụ:

| Công cụ/thư viện | Cách quản lý thường gặp |
| --- | --- |
| `psql` | Biến client `\set AUTOCOMMIT on/off` |
| JDBC | `Connection.setAutoCommit(true/false)` |
| Công cụ GUI | Nút/tùy chọn Auto-commit hoặc Manual commit |
| Spring | Transaction manager và `@Transactional` |
| Python psycopg 3 | Thuộc tính autocommit và transaction context |
| Node.js `pg` | `BEGIN`/`COMMIT` trên cùng client |

Thay đổi chế độ trong một công cụ **không tự đổi chế độ cho mọi công cụ khác**.

### 2.3. Autocommit ON vẫn cho phép BEGIN

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 2;
COMMIT;
~~~

Đây vẫn là **một transaction tường minh**, miễn những lệnh được gửi tới đúng cùng session và công cụ không can thiệp ranh giới theo cách khác. Autocommit bật không ép PostgreSQL tự commit giữa các statement của một khối `BEGIN ... COMMIT` hợp lệ.

## 3. Chuẩn bị dữ liệu thực hành

Chỉ chạy các lệnh này trên **database lab**. Các bảng và số dư trong bài đều là dữ liệu giả để học transaction, không phải mô hình thanh toán production.

### 3.1. Tạo schema và hai bảng

~~~sql
CREATE SCHEMA tx_lab;

CREATE TABLE tx_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14, 2) NOT NULL CHECK (balance >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tx_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_account integer NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    to_account integer NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_account <> to_account)
);
~~~

`numeric(14,2)` phù hợp để minh họa phép cộng/trừ số thập phân; `CHECK (balance >= 0)` ngăn lưu số dư âm. Một hệ thống tài chính thật còn cần ledger, quy tắc đồng thời, idempotency và đối soát.

### 3.2. Nạp dữ liệu

~~~sql
INSERT INTO tx_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (1, 'Lan', 1000.00),
    (2, 'Minh', 500.00),
    (3, 'Chi', 200.00);

SELECT account_id, owner_name, balance
FROM tx_lab.accounts
ORDER BY account_id;
~~~

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | Lan | 1000.00 |
| 2 | Minh | 500.00 |
| 3 | Chi | 200.00 |

~~~sql
SELECT SUM(balance) AS total_balance
FROM tx_lab.accounts;
~~~

Tổng ban đầu là **1700.00**. Khi chuyển tiền **chỉ giữa những tài khoản trong lab**, tổng này phải giữ nguyên.

> Các ví dụ có `ROLLBACK` được thiết kế để không lưu thay đổi. Nếu bạn chủ động commit một thí nghiệm, những số dư tiếp theo sẽ thay đổi so với dữ liệu khởi tạo.

## 4. Khi hai UPDATE tự commit độc lập

Giả sử ứng dụng gửi hai câu này **riêng biệt** ở autocommit mode:

~~~sql
UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;
~~~

Tình huống nguy hiểm:

~~~text
UPDATE account 1 -> COMMIT thành công
                  |
             mất kết nối
                  |
UPDATE account 2 -> chưa chạy
~~~

Nếu ứng dụng mất kết nối giữa hai statement, tài khoản Lan đã bị trừ 100 nhưng Minh chưa được cộng. Đây là lỗi **ranh giới giao dịch**.

Không giải quyết bằng cách “retry cả hai câu” vô điều kiện: lệnh trừ có thể **đã commit**, retry sẽ trừ lần nữa.

### 4.1. Đặt cả nghiệp vụ trong transaction

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100,
    updated_at = now()
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100,
    updated_at = now()
WHERE account_id = 2;

INSERT INTO tx_lab.transfers
    (from_account, to_account, amount)
VALUES (1, 2, 100);

ROLLBACK;
~~~

Trong lúc transaction đang mở, chính connection ấy đọc thấy Lan **900.00**, Minh **600.00** và một bản ghi transfer mới. Sau `ROLLBACK`, cả ba thay đổi có tính giao dịch bị hủy.

Để lưu chúng, thay `ROLLBACK` bằng `COMMIT` **sau khi toàn bộ điều kiện nghiệp vụ đã được xác minh**.

### 4.2. Vấn đề “0 rows updated”

~~~sql
UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 999;
~~~

Nếu tài khoản 999 không tồn tại, statement có thể thành công về cú pháp nhưng **không sửa hàng nào**. Transaction không tự biết rằng đây là lỗi nghiệp vụ.

Ứng dụng phải kiểm tra:

- Tài khoản gửi có tồn tại không?
- Số dư có đủ không?
- Tài khoản nhận có tồn tại không?
- Các statement có tác động đúng số hàng dự kiến không?
- Audit/ledger có ghi thành công không?
- Có yêu cầu xử lý trùng/idempotency hay không?

Chỉ **COMMIT** khi tất cả điều kiện hoàn tất.

## 5. BEGIN, COMMIT và ROLLBACK

### 5.1. BEGIN hoặc START TRANSACTION

~~~sql
BEGIN;
~~~

hoặc:

~~~sql
START TRANSACTION;
~~~

Hai cách đều mở transaction block theo ngữ nghĩa PostgreSQL ở trường hợp thông thường.

### 5.2. COMMIT

~~~sql
COMMIT;
~~~

Yêu cầu PostgreSQL kết thúc transaction và ghi nhận các thay đổi có tính giao dịch nếu transaction hợp lệ. **Commit thành công** khác với “câu `UPDATE` trả thành công”.

### 5.3. ROLLBACK

~~~sql
ROLLBACK;
~~~

Hủy những thay đổi chưa commit của transaction hiện tại. Sau khi `COMMIT` đã thành công, gọi `ROLLBACK` ở một transaction mới **không hoàn tác commit trước đó**.

### 5.4. Mẫu giao dịch thử nghiệm an toàn

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = 777
WHERE account_id = 3;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;

ROLLBACK;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

Trong transaction thấy `777.00`, sau rollback thấy lại `200.00` nếu chưa có thay đổi đã commit khác.

## 6. Hai session: thay đổi chưa commit có hiển thị không?

Mở **hai kết nối PostgreSQL độc lập**. Gọi là Session A và Session B.

### Session A

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = 777
WHERE account_id = 3;

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

Session A thấy **777.00**. **Chưa commit.**

### Session B

~~~sql
SELECT balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

Ở `READ COMMITTED` thông thường, Session B vẫn thấy **200.00** vì thay đổi của A chưa commit.

### Session A

~~~sql
ROLLBACK;
~~~

Sau rollback, cả hai connection đều thấy lại giá trị đã commit trước thí nghiệm.

### Thử COMMIT thật

Trong session A, có thể thử:

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = 777 WHERE account_id = 3;
COMMIT;
~~~

Sau khi A commit, một `SELECT` mới của B ở `READ COMMITTED` có thể thấy **777.00**. Chỉ trên lab, trả dữ liệu về trạng thái cũ:

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = 200 WHERE account_id = 3;
COMMIT;
~~~

**Không sửa số dư production để “reset” bằng phép UPDATE thủ công.** Đây là thí nghiệm trong schema giả.

## 7. Autocommit khác isolation level

Hai câu hỏi độc lập:

1. **Ranh giới transaction:** những statement nào được commit/rollback cùng nhau?
2. **Isolation:** transaction nhìn thấy dữ liệu từ transaction khác và xử lý cạnh tranh theo quy tắc nào?

PostgreSQL thường dùng `READ COMMITTED` theo mặc định. Ở mức này, một statement `SELECT` nhìn snapshot phù hợp tại đầu statement. Vì vậy:

~~~text
Session B: SELECT -> balance = 200
Session A: COMMIT balance = 777
Session B: SELECT -> balance = 777
~~~

Hai câu `SELECT` của B **có thể** thấy khác nhau ngay cả khi nằm trong **cùng `BEGIN ISOLATION LEVEL READ COMMITTED`**, vì snapshot đọc được chọn theo statement.

### 7.1. REPEATABLE READ

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
-- Session khác có thể COMMIT thay đổi.
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
COMMIT;
~~~

Ở `REPEATABLE READ` của PostgreSQL, các truy vấn đọc thông thường sử dụng snapshot ổn định của transaction, khác `READ COMMITTED`. Isolation cao hơn cũng có thể tạo lỗi cạnh tranh trong các thao tác ghi. **BEGIN không mặc nhiên đồng nghĩa REPEATABLE READ.**

### 7.2. Isolation không thay atomicity

Ngay cả khi tăng isolation, nếu hai câu `UPDATE` thuộc **hai transaction khác nhau** do autocommit, chúng vẫn có thể commit riêng. Tăng isolation không thay thế việc nhóm thao tác nghiệp vụ trong cùng ranh giới.

## 8. psql: biến AUTOCOMMIT của client

`psql` thường bật autocommit theo mặc định: statement độc lập không nằm trong `BEGIN` được hoàn tất ngay khi chạy thành công.

Xem/thiết lập biến psql:

~~~text
\echo :AUTOCOMMIT
\set AUTOCOMMIT on
\set AUTOCOMMIT off
~~~

Đây là **meta-command của psql**, không phải câu SQL gửi qua JDBC. Không viết chúng trong một statement SQL thông thường.

### 8.1. AUTOCOMMIT on

~~~sql
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
~~~

Khi chạy độc lập, psql không giữ transaction mở để đợi bạn gõ `COMMIT`. Nếu cần nhiều statement:

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 2;
COMMIT;
~~~

### 8.2. AUTOCOMMIT off

~~~text
\set AUTOCOMMIT off
~~~

Ở chế độ này, psql chủ động mở transaction trước các câu SQL phù hợp khi chưa có transaction block, sau đó chờ **`COMMIT` hoặc `ROLLBACK` tường minh**.

~~~sql
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;

SELECT account_id, updated_at
FROM tx_lab.accounts
WHERE account_id = 1;

ROLLBACK;
~~~

Hai statement trước `ROLLBACK` có thể thuộc cùng transaction do chế độ client này.

### 8.3. Chuyển về on không phải thao tác hủy giao dịch

~~~text
\set AUTOCOMMIT on
~~~

Không dùng thay cho `COMMIT` hoặc `ROLLBACK` của transaction đang mở. Chủ động kết thúc transaction trước khi đổi chế độ để không nhầm trạng thái.

### 8.4. Prompt trong psql

Với prompt mặc định, bạn có thể gặp:

~~~text
labdb=>   đang sẵn sàng nhận lệnh
labdb=*>  đang trong transaction block
labdb=!>  transaction đang ở trạng thái lỗi
~~~

Prompt có thể tùy chỉnh, vì vậy đây chỉ là **dấu hiệu hỗ trợ**, không phải API xác minh duy nhất.

## 9. Transaction lỗi và SQLSTATE 25P02

Ví dụ cố ý tạo lỗi:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = -1
WHERE account_id = 1;

-- Vi phạm CHECK (balance >= 0).
SELECT * FROM tx_lab.accounts;
~~~

Sau lỗi CHECK, transaction thông thường chuyển sang trạng thái **aborted**. `SELECT` tiếp theo bị từ chối với thông báo tương tự:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
~~~

SQLSTATE **`25P02`** thường biểu thị transaction đã thất bại; nó **không phải nguyên nhân ban đầu**. Nguyên nhân gốc ở ví dụ là `CHECK` violation.

Kết thúc đúng:

~~~sql
ROLLBACK;
~~~

Không chỉ sửa câu `UPDATE` rồi tiếp tục khi transaction đã aborted; PostgreSQL vẫn yêu cầu khôi phục trạng thái giao dịch.

### 9.1. Một số SQLSTATE quan trọng

| SQLSTATE | Tình huống |
| --- | --- |
| `23505` | Vi phạm UNIQUE |
| `23503` | Vi phạm FOREIGN KEY |
| `23514` | Vi phạm CHECK |
| `25P02` | Transaction đã ở trạng thái failed |
| `40P01` | Deadlock |
| `40001` | Serialization failure |

Lỗi có thể xuất hiện **tại `COMMIT`** khi có constraint trì hoãn được, ngay cả khi các statement DML trước đó trả thành công.

## 10. SAVEPOINT: khôi phục một phần transaction

`SAVEPOINT` cho phép đánh dấu vị trí để rollback một phần mà không nhất thiết hủy các thao tác trước mốc.

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id = 1;

SAVEPOINT before_optional_step;

UPDATE tx_lab.accounts
SET balance = -100
WHERE account_id = 2;

-- Lỗi CHECK; transaction cần phục hồi.
ROLLBACK TO SAVEPOINT before_optional_step;

UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id = 3;

ROLLBACK; -- Hủy tất cả để giữ nguyên lab.
~~~

`ROLLBACK TO SAVEPOINT` hủy các thao tác sau savepoint và cho phép transaction tiếp tục ở trạng thái phù hợp.

### 10.1. RELEASE SAVEPOINT không phải COMMIT

~~~sql
BEGIN;
SAVEPOINT mark1;
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;
RELEASE SAVEPOINT mark1;
ROLLBACK;
~~~

`RELEASE SAVEPOINT` xóa mốc savepoint, không commit transaction bên ngoài. Vì có `ROLLBACK` cuối, `UPDATE` vẫn bị hủy.

### 10.2. BEGIN lồng nhau không tạo hai transaction độc lập

~~~sql
BEGIN;
BEGIN;
~~~

không tạo một nested transaction độc lập theo nghĩa có thể commit riêng. PostgreSQL hỗ trợ savepoints để rollback một phần. Framework có thể mô phỏng “nested” bằng savepoint, nhưng vẫn phải hiểu transaction bao ngoài.

## 11. Chạy file SQL bằng psql

Giả sử file `changes.sql` có nhiều statement:

~~~sql
UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 1;

UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 2;

UPDATE tx_lab.accounts SET updated_at = now()
WHERE account_id = 3;
~~~

Khi chạy `psql -f changes.sql` với autocommit mặc định, các statement độc lập có thể được commit lần lượt. Nếu statement thứ ba lỗi, hai statement đầu có thể đã lưu.

### 11.1. ON_ERROR_STOP không tự tạo transaction

~~~text
psql -X -v ON_ERROR_STOP=1 -d lab_db -f changes.sql
~~~

`ON_ERROR_STOP` yêu cầu `psql` dừng việc đọc tiếp script khi gặp lỗi; nó không biến các statement đã commit riêng thành một khối nguyên tử.

### 11.2. --single-transaction

~~~text
psql -X -v ON_ERROR_STOP=1 --single-transaction -d lab_db -f changes.sql
~~~

Tùy chọn `-1` hoặc `--single-transaction` cho phép `psql` bao các file hoặc các phần command phù hợp trong một transaction. Kết hợp `ON_ERROR_STOP=1` giúp script dừng và rollback khi lỗi thay vì giữ các bước đầu đã commit độc lập.

**Điều kiện:** script không được tự phá ranh giới bằng `COMMIT`/`ROLLBACK` không phù hợp và không chứa những lệnh **bị cấm trong transaction block**.

### 11.3. Chú ý cách client gửi nhiều câu SQL

Nhiều statement gửi trong **một protocol query message** có thể có ngữ nghĩa transaction ngầm khác việc gửi **mỗi statement thành một message riêng**. Vì thế, đừng suy chỉ từ số dấu chấm phẩy trong file hoặc chuỗi `-c` rằng ranh giới luôn giống nhau.

Khi cần bảo đảm nghiệp vụ, dùng `BEGIN ... COMMIT` hoặc một tùy chọn/script transaction đã được xác định rõ và phù hợp công cụ.

## 12. Giao dịch trong công cụ GUI

Các công cụ như pgAdmin, DBeaver hoặc một SQL editor khác thường có lựa chọn **Auto-commit** và **Manual commit**, nhưng hành vi chính xác tùy phiên bản, connection và chế độ Execute Statement/Execute Script.

Quy trình kiểm tra trước khi thao tác dữ liệu thật:

1. Xác định **connection/database** đang sử dụng.
2. Xem công cụ đang ở chế độ autocommit hay manual commit.
3. Chạy một `BEGIN; UPDATE ...; SELECT ...;` trên bảng lab.
4. Đọc cùng hàng ở **một connection khác**.
5. Gọi `ROLLBACK;` trên connection ban đầu.
6. Xác nhận số dư trở về như trước.

### 12.1. Mở nhiều tab không có nghĩa chung transaction

Hai tab có thể dùng connection khác nhau. Bấm Commit ở một tab không bảo đảm commit transaction đang mở ở tab khác.

### 12.2. Đừng bấm Commit chỉ để tắt cảnh báo

Nếu GUI báo “uncommitted changes”, phải xác định các lệnh đã chạy và dữ liệu đã đạt điều kiện chưa. `COMMIT` là quyết định nghiệp vụ, không phải thao tác đóng hộp thoại.

### 12.3. Đóng connection khi chưa commit

Khi connection PostgreSQL thực sự kết thúc, transaction chưa commit không tự biến thành commit. Nhưng không dùng việc đóng tab làm chiến lược rollback; công cụ có thể giữ connection sống trong pool/session của nó. Hãy gọi `ROLLBACK` rõ ràng.

## 13. JDBC: autocommit trên Connection

Theo hợp đồng JDBC, connection mới thường được tạo với **autocommit true**. Tuy nhiên, pool/framework có thể trả cho ứng dụng connection đã được cấu hình theo chính sách riêng.

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());
}
~~~

Muốn nhóm nhiều câu:

~~~java
connection.setAutoCommit(false);

try {
    // SQL 1, SQL 2, SQL 3 trên cùng connection.
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

Trong code thực tế, phải xử lý cả lỗi rollback và đảm bảo trả connection về pool. Không nên trộn tùy tiện `setAutoCommit(false)` với SQL `BEGIN`/`COMMIT` do framework khác quản lý.

### 13.1. JDBC chuyển tiền có kiểm tra số hàng

Ví dụ dùng Java 15+ text blocks và một `DataSource` đã cấu hình:

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(int from, int to, BigDecimal amount)
            throws SQLException {
        if (from == to || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection conn = dataSource.getConnection()) {
            boolean oldAutoCommit = conn.getAutoCommit();
            conn.setAutoCommit(false);
            try {
                String debitSql = """
                    UPDATE tx_lab.accounts
                    SET balance = balance - ?, updated_at = now()
                    WHERE account_id = ? AND balance >= ?
                    """;

                try (PreparedStatement debit =
                         conn.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setInt(2, from);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new SQLException("No eligible source account");
                    }
                }

                String creditSql = """
                    UPDATE tx_lab.accounts
                    SET balance = balance + ?, updated_at = now()
                    WHERE account_id = ?
                    """;

                try (PreparedStatement credit =
                         conn.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setInt(2, to);
                    if (credit.executeUpdate() != 1) {
                        throw new SQLException("Destination not found");
                    }
                }

                String insertSql = """
                    INSERT INTO tx_lab.transfers
                        (from_account, to_account, amount)
                    VALUES (?, ?, ?)
                    """;

                try (PreparedStatement audit =
                         conn.prepareStatement(insertSql)) {
                    audit.setInt(1, from);
                    audit.setInt(2, to);
                    audit.setBigDecimal(3, amount);
                    audit.executeUpdate();
                }

                conn.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                if (!conn.isClosed()) {
                    conn.setAutoCommit(oldAutoCommit);
                }
            }
        }
    }
}
~~~

Ở đây:

- Mọi `PreparedStatement` sử dụng **cùng conn**.
- `setAutoCommit(false)` chạy trước các lệnh ghi.
- Debit kiểm tra điều kiện `balance >= amount` **trong UPDATE**.
- Ứng dụng kiểm tra số hàng bị ảnh hưởng ở cả debit và credit.
- Chỉ commit sau khi cả hai cập nhật và audit thành công.
- Khi có exception, code cố rollback và ném lại lỗi.

**Đây là mẫu giảng dạy, không phải hệ thống ngân hàng production.** Thực tế còn cần idempotency key, ledger bất biến, khóa/trật tự lock, retry có giới hạn, đối soát và xử lý kết quả commit không chắc chắn.

### 13.2. Cẩn thận với việc bật lại autoCommit

Theo ngữ nghĩa JDBC, chuyển `autoCommit=false` sang `true` **khi transaction đang hoạt động** có thể commit transaction đó. Vì vậy không dùng `setAutoCommit(true)` như cách “hủy thay đổi”. Hãy commit hoặc rollback **trước khi khôi phục trạng thái connection**.

Trong ví dụ, phần `finally` cố khôi phục chế độ cũ. Ở hệ thống thực tế, cleanup cũng có thể ném exception; cần quản lý lỗi thứ cấp để không che khuất lỗi gốc, và tuân thủ hợp đồng connection pool đang dùng.

### 13.3. Lỗi lúc commit

Nếu transaction có constraint trì hoãn, lỗi có thể xuất hiện khi `conn.commit()`. Không chỉ bắt exception quanh `executeUpdate()` rồi báo thành công. Một lỗi kết nối đúng lúc gửi `COMMIT` còn có thể khiến ứng dụng **không chắc commit đã thành công hay chưa**.

## 14. Connection pool: mượn một connection cho một transaction

~~~text
HTTP request
    |
Service method
    |
borrow connection
    |
begin / autoCommit(false)
    |
UPDATE + UPDATE + INSERT
    |
COMMIT hoặc ROLLBACK
    |
return connection to pool
~~~

Ví dụ sai ý định:

~~~java
debitRepository.debit(from, amount);    // connection A
creditRepository.credit(to, amount);   // connection B
auditRepository.record(from, to, amount); // connection C
~~~

Nếu mỗi helper tự mở connection ở autocommit mode mà không có transaction manager phối hợp, ba lệnh này có thể thuộc **ba transaction**.

Hai cách tổ chức đúng hướng:

1. Tự quản lý JDBC: truyền **cùng connection** qua các repository/helper.
2. Dùng transaction manager/framework: bảo đảm các thao tác liên kết với **cùng transaction và DataSource** theo cơ chế của framework.

**Đừng trả connection về pool khi chưa chủ động commit/rollback.** Transaction bỏ dở có thể giữ lock, snapshot và làm các request khác chờ. Không dựa hoàn toàn vào pool tự cleanup.

## 15. Spring @Transactional

Trong Spring với transaction manager phù hợp, `@Transactional` thường xác định **ranh giới của một phương thức nghiệp vụ**:

~~~java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int from, int to, BigDecimal amount) {
        if (from == to || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update("""
            UPDATE tx_lab.accounts
            SET balance = balance - ?
            WHERE account_id = ? AND balance >= ?
            """, amount, from, amount);
        if (debited != 1) {
            throw new IllegalStateException("Insufficient funds");
        }

        int credited = jdbc.update("""
            UPDATE tx_lab.accounts
            SET balance = balance + ?
            WHERE account_id = ?
            """, amount, to);
        if (credited != 1) {
            throw new IllegalStateException("Destination missing");
        }

        jdbc.update("""
            INSERT INTO tx_lab.transfers
                (from_account, to_account, amount)
            VALUES (?, ?, ?)
            """, from, to, amount);
    }
}
~~~

Với Spring transaction infrastructure cấu hình đúng, phương thức được gọi thông qua cơ chế intercept phù hợp có thể chạy trong một transaction: commit khi hoàn tất hoặc rollback khi exception thỏa quy tắc.

### 15.1. Những bẫy thường gặp

- **Self-invocation:** phương thức trong cùng object gọi một phương thức khác có `@Transactional` có thể không đi qua proxy trong cơ chế Spring proxy thông thường.
- **Sai transaction manager/DataSource:** thao tác truy cập DataSource khác có thể không thuộc transaction đang quản lý.
- **Nuốt exception:** nếu code bắt lỗi rồi trả kết quả bình thường, transaction manager có thể coi phương thức thành công và cố commit.
- **Checked exceptions:** quy tắc mặc định thường rollback cho `RuntimeException`/`Error`, không mặc định rollback mọi checked exception trừ khi cấu hình khác.

Ví dụ khai báo chính sách khác:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importBatch() throws Exception {
    // ...
}
~~~

### 15.2. REQUIRED và REQUIRES_NEW

| Propagation | Ý nghĩa khái quát |
| --- | --- |
| `REQUIRED` | Tham gia transaction hiện có hoặc tạo mới nếu chưa có |
| `REQUIRES_NEW` | Dùng một transaction độc lập mới, có thể tạm ngưng transaction ngoài |

Nếu bước audit dùng `REQUIRES_NEW`, audit có thể **commit riêng** dù transaction nghiệp vụ ngoài rollback. Đây có thể là thiết kế có chủ đích, nhưng **không còn cùng một đơn vị atomicity**.

### 15.3. JPA flush không phải commit

ORM/JPA có thể gửi SQL khi `flush()` trước khi transaction kết thúc. Session khác vẫn có thể chưa thấy dữ liệu; lỗi về sau có thể rollback. Phân biệt **trạng thái entity**, **flush SQL** và **commit PostgreSQL**.

## 16. Node.js với pg

Với Node.js `pg`, cần mượn **một client** rồi dùng nó cho toàn bộ transaction:

~~~javascript
const client = await pool.connect();

try {
  await client.query("BEGIN");

  const debit = await client.query(
    "UPDATE tx_lab.accounts " +
    "SET balance = balance - $1 " +
    "WHERE account_id = $2 AND balance >= $1",
    [100, 1]
  );
  if (debit.rowCount !== 1) {
    throw new Error("Debit failed");
  }

  const credit = await client.query(
    "UPDATE tx_lab.accounts " +
    "SET balance = balance + $1 WHERE account_id = $2",
    [100, 2]
  );
  if (credit.rowCount !== 1) {
    throw new Error("Credit failed");
  }

  await client.query(
    "INSERT INTO tx_lab.transfers " +
    "(from_account, to_account, amount) VALUES ($1, $2, $3)",
    [1, 2, 100]
  );

  await client.query("COMMIT");
} catch (error) {
  try {
    await client.query("ROLLBACK");
  } catch (rollbackError) {
    // Log lỗi cleanup, connection có thể không dùng lại được.
  }
  throw error;
} finally {
  client.release();
}
~~~

Không dùng:

~~~javascript
// Sai cách tổ chức nếu muốn cùng transaction:
await pool.query("BEGIN");
await pool.query("UPDATE ...");
await pool.query("COMMIT");
~~~

Mỗi `pool.query` có thể sử dụng connection khác nhau. Không thể dựa vào đó để giữ cùng transaction.

## 17. Python psycopg 3

Mặc định của **psycopg 3** là `autocommit=False`, khác với default JDBC. Một câu `SELECT` có thể bắt đầu transaction và để session mở nếu ứng dụng chưa commit/rollback.

~~~python
import psycopg

dsn = "postgresql://app_user:secret@localhost:5432/lab_db"

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tx_lab.accounts " +
            "SET updated_at = now() WHERE account_id = %s",
            (1,),
        )
    # Rời connection context bình thường: commit.
    # Nếu có exception: rollback theo cơ chế context manager.
~~~

Ví dụ mở transaction block tường minh trên connection autocommit:

~~~python
with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tx_lab.accounts "
                "SET updated_at = now() WHERE account_id = %s",
                (1,),
            )
~~~

Khi một transaction đã mở, block transaction lồng nhau có thể dùng savepoint tùy trạng thái/semantics của thư viện. Không suy rằng mỗi context `conn.transaction()` luôn tạo transaction database độc lập.

### So sánh nhanh các môi trường

| Môi trường | Cần ghi nhớ |
| --- | --- |
| psql | AUTOCOMMIT thường on |
| JDBC | Connection theo JDBC thường autocommit true |
| psycopg 3 | Connection mặc định autocommit false |
| Node pg | Transaction tường minh cần một client duy nhất |
| Spring | Transaction manager, proxy, propagation và exception policy quyết định |

**Đừng sao chép giả định autocommit giữa các ngôn ngữ.**

## 18. SELECT FOR UPDATE cần một transaction còn mở

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Xác minh điều kiện và cập nhật tại cùng connection.
UPDATE tx_lab.accounts
SET updated_at = now()
WHERE account_id = 1;

COMMIT;
~~~

`SELECT FOR UPDATE` khóa hàng để điều phối cạnh tranh. Khóa phù hợp được giữ tới cuối transaction.

### Nếu autocommit mỗi statement

~~~text
SELECT ... FOR UPDATE;  -> transaction kết thúc, khóa được thả
Ứng dụng tính toán
UPDATE ...;             -> transaction mới
~~~

Trong cách này, khóa của `SELECT` không tiếp tục bảo vệ bước `UPDATE` phía sau. Hãy đặt cả quá trình trong một transaction khi cần giữ khóa xuyên nhiều statement.

### 18.1. Không phải mọi nghiệp vụ đều cần SELECT FOR UPDATE riêng

Một cập nhật có điều kiện:

~~~sql
UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;
~~~

cũng dùng cơ chế khóa/cập nhật của PostgreSQL và thường có thể bảo vệ điều kiện số dư ngay tại statement. Cần xem workload thực tế, isolation level và những thao tác cạnh tranh chứ không tự thêm khóa quá rộng.

### 18.2. Giảm deadlock bằng thứ tự khóa

Nếu giao dịch A khóa tài khoản 1 rồi 2, còn B khóa 2 rồi 1, có thể có deadlock. Thường cần thống nhất **thứ tự lấy khóa**, ví dụ tăng theo ID, và xử lý/retry transaction bị hủy khi phù hợp.

## 19. DDL trong transaction

PostgreSQL hỗ trợ rollback nhiều thay đổi schema:

~~~sql
BEGIN;

CREATE TABLE tx_lab.temporary_demo (
    id integer PRIMARY KEY
);

INSERT INTO tx_lab.temporary_demo(id)
VALUES (1);

ROLLBACK;
~~~

Sau rollback, bảng `temporary_demo` không tồn tại nếu trước đó chưa tồn tại. Tuy nhiên, **không phải mọi lệnh PostgreSQL đều được chạy trong transaction block**.

Ví dụ:

~~~sql
-- Những lệnh có hạn chế transaction block:
CREATE DATABASE some_database;
VACUUM tx_lab.accounts;
CREATE INDEX CONCURRENTLY idx_accounts_owner
    ON tx_lab.accounts(owner_name);
~~~

`CREATE INDEX CONCURRENTLY` có cơ chế tránh một số chặn ghi so với index thông thường nhưng **không được thực thi trong transaction block thông thường**. Migration tool tự bọc cả script bằng transaction có thể khiến lệnh này lỗi.

### 19.1. TRUNCATE cũng cần thận trọng

PostgreSQL có thể rollback `TRUNCATE` trong transaction phù hợp, nhưng nó giữ khóa mạnh và có những đặc điểm visibility khác `DELETE`. Không coi “có thể rollback” là lý do chạy `TRUNCATE` tùy tiện trên production.

### 19.2. Ranh giới của migration

Trước khi deploy migration, cần biết:

1. Tool có tự mở transaction quanh từng file không?
2. Nếu câu thứ năm lỗi, bốn câu đầu đã commit chưa?
3. Script có `COMMIT`/`ROLLBACK` riêng không?
4. Có lệnh cần chạy ngoài transaction block không?
5. Có thể chạy lại khi bị ngắt giữa chừng không?

## 20. Điều gì không được rollback như bảng dữ liệu?

Atomicity của một PostgreSQL transaction không bao trùm mọi tác dụng bên ngoài.

### 20.1. Sequence và identity có thể có khoảng trống

Trong `tx_lab.transfers`, `transfer_id` dùng identity/sequence.

~~~sql
BEGIN;

INSERT INTO tx_lab.transfers
    (from_account, to_account, amount)
VALUES (1, 2, 1)
RETURNING transfer_id;

ROLLBACK;
~~~

Hàng được insert bị rollback, nhưng sequence đã cấp số **không rollback như hàng dữ liệu**. Vì vậy ID có thể có khoảng trống. Đừng coi dãy ID liên tục là một invariant cần đảm bảo bằng transaction.

### 20.2. Email, HTTP, filesystem

~~~text
BEGIN
  UPDATE orders SET status='PAID'
  Gửi email "thanh toán thành công" -> đã gửi!
  INSERT audit -> thất bại
ROLLBACK
~~~

Rollback PostgreSQL **không thu hồi email**, không tự hủy HTTP request thành công và không rollback file ngoài database.

Một thiết kế thường dùng là **transactional outbox**:

~~~text
BEGIN
  UPDATE dữ liệu nghiệp vụ
  INSERT hàng outbox event
COMMIT
        |
        v
  Worker gửi email/message
  và retry theo cơ chế idempotent
~~~

### 20.3. Commit không rõ kết quả khi mất kết nối

Nếu ứng dụng gửi `COMMIT` rồi mất mạng trước khi nhận phản hồi, có thể xảy ra:

1. Server chưa xử lý commit; transaction bị rollback khi connection chấm dứt.
2. Server đã commit thành công nhưng response không tới ứng dụng.

Ứng dụng không thể chỉ nhìn exception mạng để phân biệt chắc chắn. Với nghiệp vụ có tiền hoặc thao tác không idempotent, cần **mã request duy nhất, bảng trạng thái, tra cứu và đối soát**, không retry trừ tiền mù quáng.

## 21. Phát hiện idle in transaction

Một session có transaction đang mở nhưng không chạy SQL có thể ở trạng thái **`idle in transaction`**. Tình trạng kéo dài có thể:

- Giữ lock, gây chờ cho session khác.
- Kéo dài snapshot/transaction horizon, ảnh hưởng VACUUM và bloat.
- Chiếm connection của pool.
- Tạo hành vi khó chẩn đoán khi transaction bị bỏ dở.

### 21.1. Quan sát pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN (
      'idle in transaction',
      'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST;
~~~

Quyền đọc chi tiết session của người khác có thể bị giới hạn. `xact_start` và thời lượng transaction giúp tìm session cần điều tra.

### 21.2. Timeout phù hợp

~~~sql
SHOW idle_in_transaction_session_timeout;
~~~

Trong môi trường lab hoặc với chính sách vận hành cho phép:

~~~sql
SET idle_in_transaction_session_timeout = '30s';
~~~

Tham số này có thể ngắt session idle trong transaction quá lâu. **Không áp dụng 30 giây mặc định cho mọi production workload**; timeout có thể hủy connection đang làm việc và ứng dụng phải xử lý.

| Tham số | Mục tiêu |
| --- | --- |
| `statement_timeout` | Giới hạn thời gian thực thi statement |
| `lock_timeout` | Giới hạn thời gian chờ lock |
| `idle_in_transaction_session_timeout` | Giới hạn thời gian session idle khi đang có transaction |

Timeout là biện pháp an toàn bổ sung, **không thay** commit/rollback đúng trong code.

## 22. Giữ transaction ngắn và đúng phạm vi

Ví dụ có vấn đề:

~~~text
BEGIN
  UPDATE DB
  gọi HTTP ngoài (mất 20 giây)
  render file (mất 15 giây)
  gửi email
  UPDATE DB
COMMIT
~~~

Transaction có thể giữ tài nguyên trong khi chờ side effects bên ngoài; những side effects đó cũng không rollback cùng DB.

Tổ chức tốt hơn:

1. Validate và chuẩn bị dữ liệu trước transaction khi có thể.
2. Mở transaction ngay trước các thao tác DB cần atomicity.
3. Ghi dữ liệu nghiệp vụ và outbox trong cùng transaction.
4. Commit/rollback càng sớm càng hợp lý.
5. Thực hiện email, message, file, HTTP ngoài transaction qua cơ chế xử lý tin cậy và idempotent.

**Transaction dài không làm nghiệp vụ an toàn hơn chỉ vì nó chứa nhiều bước hơn.**

## 23. Ranh giới cho các tình huống ứng dụng

### 23.1. Đặt hàng

~~~text
BEGIN
  Kiểm tra và giữ tồn kho với cập nhật/khóa an toàn
  INSERT orders
  INSERT order_items
  INSERT outbox "OrderCreated"
COMMIT
~~~

Những thay đổi PostgreSQL cần đi cùng nhau nằm trong một transaction; worker outbox có thể gửi thông báo sau commit.

### 23.2. Đổi trạng thái đơn

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 123
  AND status = 'PENDING';

-- Phải kiểm tra đúng một hàng bị cập nhật.
INSERT INTO order_status_history (...) VALUES (...);

COMMIT;
~~~

Mẫu này minh họa ý tưởng; tên bảng/cột chưa được tạo trong lab. Nếu `UPDATE` tác động 0 hàng, logic phải quyết định rollback/conflict/idempotent thay vì mặc nhiên ghi audit thành công.

### 23.3. Batch import

Một batch 100.000 hàng trong một transaction nghĩa là **hoặc toàn bộ batch commit hoặc rollback**. Chia thành 100 transaction mỗi nhóm 1.000 hàng giúp checkpoint/resume nhưng nếu batch 73 lỗi thì 72 batch trước có thể đã commit.

Phải chọn ranh giới theo yêu cầu toàn vẹn, chi phí lock/WAL, khả năng resume và kết quả người dùng kỳ vọng.

### 23.4. Stored procedure

Trong PostgreSQL, function thông thường không tự gọi `COMMIT`/`ROLLBACK` như client. Procedure gọi bằng `CALL` có thể thực hiện transaction control **trong những bối cảnh được phép**, nhưng bị giới hạn bởi cấu trúc lời gọi và transaction block bên ngoài. Không giả định một procedure luôn được phép commit khi nó được gọi bên trong `BEGIN` của ứng dụng.

## 24. Những lỗi thường gặp

### Lỗi 1. Tắt autocommit rồi quên commit/rollback

Connection giữ transaction, có thể chiếm lock và trở thành `idle in transaction`. Mọi đường ra khỏi hàm cần cleanup rõ.

### Lỗi 2. Hai UPDATE độc lập cho một nghiệp vụ

Một câu có thể commit trước khi câu sau lỗi. Gom trong một transaction và kiểm tra số hàng bị ảnh hưởng.

### Lỗi 3. BEGIN trên connection A, COMMIT trên B

Hai connection có trạng thái transaction riêng. Không thể commit transaction của A thông qua B.

### Lỗi 4. Đọc thấy thay đổi của chính mình rồi tưởng đã commit

Session có thể đọc thay đổi chưa commit của nó. Session khác mới giúp kiểm tra khả năng nhìn thấy từ bên ngoài.

### Lỗi 5. Cố tiếp tục khi transaction đã aborted

Sau lỗi, `25P02` thường xuất hiện cho tới khi rollback hoặc phục hồi tới savepoint hợp lệ.

### Lỗi 6. Dùng setAutoCommit(true) để “hủy”

Trong JDBC, việc chuyển từ false sang true khi đang có transaction hoạt động có thể commit. Phải rollback tường minh.

### Lỗi 7. pool.query từng statement trong Node pg

Pool có thể cấp connection khác nhau. Dùng `pool.connect()` và giữ một client tới khi kết thúc.

### Lỗi 8. Tin @Transactional luôn có tác dụng

Self-invocation, sai transaction manager/DataSource hoặc exception bị nuốt có thể dẫn đến ranh giới sai.

### Lỗi 9. Cho rằng JPA flush = commit

SQL được flush có thể vẫn chưa commit, và lỗi sau đó có thể rollback transaction.

### Lỗi 10. SELECT FOR UPDATE ở statement riêng

Khóa thả sau khi statement tự commit, không bảo vệ bước UPDATE sau đó.

### Lỗi 11. Script có ON_ERROR_STOP nhưng không có transaction

Dừng sớm không rollback các statement đã commit trước. Dùng `-1` hoặc ranh giới tường minh khi phù hợp.

### Lỗi 12. Đưa lệnh cấm trong transaction vào script -1

`CREATE DATABASE`, `VACUUM`, `CREATE INDEX CONCURRENTLY` có hạn chế transaction block.

### Lỗi 13. Coi rollback sẽ hoàn tác email và sequence

Rollback áp dụng cho dữ liệu có tính giao dịch của PostgreSQL; side effects bên ngoài và sequence có quy tắc khác.

### Lỗi 14. Retry mù quáng sau lỗi mạng ở COMMIT

Kết quả commit có thể không rõ. Dùng idempotency key và đối soát.

### Lỗi 15. Transaction dài bao network call

Giữ lock và connection lâu, tạo bloat/rủi ro waiting. Cân nhắc outbox và ranh giới ngắn.

## 25. Bài tập thực hành

Thực hiện trên `tx_lab`. Với bài cố ý thay đổi số dư, dùng `ROLLBACK` để giữ dữ liệu mẫu hoặc reset lab có kiểm soát.

### Bài 1. Autocommit

Giải thích vì sao hai statement `UPDATE` chạy riêng trong `psql` với AUTOCOMMIT on không tự thành một transaction.

### Bài 2. Một câu sửa nhiều hàng

`UPDATE accounts SET updated_at=now() WHERE account_id IN (1,2)` có tạo một transaction cho mỗi hàng không?

### Bài 3. BEGIN/ROLLBACK

Viết transaction đổi số dư tài khoản 3 thành 777, đọc trong transaction rồi rollback. Dự đoán giá trị sau rollback.

### Bài 4. Chuyển tiền

Viết hai `UPDATE` và một `INSERT` audit trong cùng transaction chuyển 100 từ tài khoản 1 sang 2. Nêu những điều kiện cần kiểm tra trước commit.

### Bài 5. Hai session

Session A chưa commit một UPDATE. Session B ở READ COMMITTED thấy giá trị cũ hay mới? Khi nào B có thể thấy giá trị mới?

### Bài 6. Isolation

Hai SELECT trong cùng transaction READ COMMITTED có thể cho kết quả khác nhau không? Còn REPEATABLE READ thì sao đối với snapshot đọc thông thường?

### Bài 7. psql autocommit

Viết meta-command bật/tắt AUTOCOMMIT và SQL command dùng để hủy transaction.

### Bài 8. Chạy SQL file

Viết lệnh chạy `changes.sql` qua psql, dừng khi lỗi và thực hiện một transaction cho script nếu hợp lệ.

### Bài 9. 25P02

Vì sao một SELECT sau UPDATE vi phạm CHECK bị từ chối trong cùng transaction? Làm gì để tiếp tục?

### Bài 10. SAVEPOINT

Viết transaction có savepoint, cố ý vi phạm `balance>=0`, rollback đến savepoint, tiếp tục cập nhật hợp lệ rồi rollback toàn bộ lab.

### Bài 11. JDBC

API JDBC nào tắt autocommit? Vì sao ba PreparedStatement phải dùng cùng Connection?

### Bài 12. setAutoCommit(true)

Vì sao không dùng thao tác này thay cho rollback khi transaction còn mở?

### Bài 13. Connection pool

Vì sao ba helper cùng dùng một DataSource nhưng mỗi helper tự lấy connection vẫn có thể commit độc lập?

### Bài 14. Spring

Nêu hai tình huống làm `@Transactional` không áp dụng như tưởng tượng. Nếu code bắt lỗi và trả success, có rủi ro gì?

### Bài 15. Node.js

Viết skeleton `pool.connect()` → `BEGIN` → SQL → `COMMIT`/`ROLLBACK` trên một client.

### Bài 16. SELECT FOR UPDATE

Khóa của SELECT FOR UPDATE còn giữ tới câu UPDATE tiếp theo không nếu mỗi statement tự commit?

### Bài 17. Transactional DDL

CREATE TABLE có thể rollback không? Nêu ít nhất hai lệnh không được chạy trong transaction block thông thường.

### Bài 18. Sequence

Vì sao một transfer_id có thể bị bỏ qua dù INSERT đã rollback?

### Bài 19. Email và outbox

Email gửi trong transaction có tự bị thu hồi khi rollback không? Đề xuất thiết kế khác.

### Bài 20. Idle in transaction

Viết truy vấn `pg_stat_activity` tìm những session idle trong transaction, hiển thị tuổi transaction. Nêu hai rủi ro.

### Bài 21. Commit không chắc chắn

Ứng dụng gửi COMMIT rồi mất mạng; có nên retry chuyển tiền vô điều kiện không?

### Bài 22. Thiết kế ranh giới

Một API tạo đơn, giữ tồn kho, ghi audit và gửi email. Những bước nào nên cùng PostgreSQL transaction, bước nào nên tách sau commit?

## 26. Gợi ý lời giải

### Bài 1–2

Khi autocommit bật, các statement độc lập ngoài BEGIN thường được commit riêng. Tuy nhiên, một UPDATE sửa nhiều hàng vẫn là **một statement** có tính nguyên tử, không phải mỗi hàng một commit.

### Bài 3

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = 777 WHERE account_id = 3;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
ROLLBACK;
~~~

Sau rollback, số dư lại là **200.00** nếu chưa có thay đổi đã commit khác.

### Bài 4

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1 AND balance >= 100;
-- Phải xác nhận 1 hàng bị cập nhật.

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;
-- Phải xác nhận 1 hàng bị cập nhật.

INSERT INTO tx_lab.transfers
    (from_account, to_account, amount)
VALUES (1, 2, 100);

ROLLBACK; -- Thí nghiệm: không ghi số dư thật vào lab.
~~~

Khi triển khai, thay `ROLLBACK` bằng `COMMIT` **chỉ nếu code đã kiểm tra đầy đủ hai UPDATE, audit và điều kiện nghiệp vụ**. SQL trên không tự kiểm tra rows affected.

### Bài 5–6

Session B ở READ COMMITTED chưa thấy thay đổi chưa commit của A. Sau A commit, statement đọc mới có thể thấy. Với READ COMMITTED, hai SELECT trong cùng transaction cũng có thể thấy khác nhau; với REPEATABLE READ, snapshot đọc thông thường ổn định hơn trong transaction.

### Bài 7

~~~text
\set AUTOCOMMIT on
\set AUTOCOMMIT off
~~~

Hủy transaction bằng `ROLLBACK;`.

### Bài 8

~~~text
psql -X -v ON_ERROR_STOP=1 -1 -d lab_db -f changes.sql
~~~

`ON_ERROR_STOP` dừng script ở lỗi; `-1` bao script bằng transaction nếu script/lệnh hỗ trợ.

### Bài 9

Sau một statement lỗi, transaction thường bị đánh dấu failed; `25P02` xuất hiện ở lệnh sau. Dùng `ROLLBACK;` hoặc `ROLLBACK TO SAVEPOINT` đã tạo trước lỗi.

### Bài 10

~~~sql
BEGIN;
SAVEPOINT before_bad;

UPDATE tx_lab.accounts SET balance=-1 WHERE account_id=1;
-- Lỗi CHECK.

ROLLBACK TO SAVEPOINT before_bad;
UPDATE tx_lab.accounts SET updated_at=now() WHERE account_id=2;
ROLLBACK;
~~~

### Bài 11–13

JDBC `setAutoCommit(false)`, `commit()`, `rollback()`. Các statement phải cùng connection. Chuyển `autoCommit=false` sang true khi transaction đang hoạt động có thể commit, nên **rollback trước**. Ba helper lấy ba connection có thể có ba transaction độc lập dù dùng chung một pool.

### Bài 14

Ví dụ self-invocation không qua proxy, hoặc thao tác trên DataSource khác transaction manager. Nếu exception bị nuốt, framework có thể coi phương thức thành công rồi commit.

### Bài 15

~~~javascript
const client = await pool.connect();
try {
  await client.query("BEGIN");
  await client.query(
    "UPDATE tx_lab.accounts SET updated_at=now() WHERE account_id=$1",
    [1]
  );
  await client.query("COMMIT");
} catch (e) {
  try { await client.query("ROLLBACK"); } catch (_) {}
  throw e;
} finally {
  client.release();
}
~~~

### Bài 16

Không. Nếu transaction của statement SELECT đã commit, khóa không bảo vệ câu UPDATE riêng sau đó.

### Bài 17

PostgreSQL có transactional DDL; nhiều lệnh `CREATE TABLE` có thể rollback. `CREATE DATABASE`, `VACUUM`, `CREATE INDEX CONCURRENTLY` không được chạy trong transaction block thông thường.

### Bài 18

Sequence/identity đã cấp số không rollback giống hàng INSERT; ID có thể có khoảng trống.

### Bài 19

Email không tự rollback. Ghi nghiệp vụ và outbox event trong cùng DB transaction; worker gửi email sau commit với cơ chế idempotency.

### Bài 20

~~~sql
SELECT
    pid, application_name, state,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
~~~

Rủi ro gồm lock lâu, VACUUM/bloat và connection pool bị chiếm.

### Bài 21

Không retry vô điều kiện. Server có thể đã commit nhưng response bị mất; cần request ID/idempotency, truy vấn trạng thái và đối soát.

### Bài 22

Tạo đơn, điều chỉnh tồn kho, ghi audit/outbox nên nằm trong một transaction PostgreSQL khi cần atomicity. Email bên ngoài DB được gửi sau commit qua worker/outbox thay vì gửi trực tiếp trong transaction.

## 27. Bảng tra cứu nhanh

| Nhu cầu | Cú pháp/API |
| --- | --- |
| Mở transaction | `BEGIN;` hoặc `START TRANSACTION;` |
| Commit | `COMMIT;` |
| Hủy transaction | `ROLLBACK;` |
| Tạo mốc phục hồi | `SAVEPOINT mark;` |
| Rollback tới mốc | `ROLLBACK TO SAVEPOINT mark;` |
| Xóa mốc | `RELEASE SAVEPOINT mark;` |
| Chọn isolation | `BEGIN ISOLATION LEVEL READ COMMITTED;` |
| psql bật/tắt autocommit | `\set AUTOCOMMIT on/off` |
| psql dừng script khi lỗi | `-v ON_ERROR_STOP=1` |
| psql một transaction cho script | `-1` / `--single-transaction` |
| JDBC bắt đầu quản lý thủ công | `connection.setAutoCommit(false)` |
| JDBC kết thúc | `connection.commit()` / `connection.rollback()` |
| JDBC đọc chế độ | `connection.getAutoCommit()` |
| Spring transaction | `@Transactional` + transaction manager phù hợp |
| Node pg | `pool.connect()` và cùng một `client` |
| psycopg 3 | `with conn.transaction():` |
| Khóa hàng | `SELECT ... FOR UPDATE` trong transaction phù hợp |
| Quan sát session | `pg_stat_activity`, `state`, `xact_start` |
| Timeout idle in transaction | `idle_in_transaction_session_timeout` |

## 28. Checklist trước khi đưa vào vận hành

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Đơn vị nghiệp vụ cần commit cùng nhau là gì? | Xác định transaction boundary |
| Client/driver mặc định autocommit thế nào? | Tránh commit ngoài ý muốn |
| Các statement dùng cùng connection? | PostgreSQL transaction gắn với session |
| Ai quản lý commit/rollback? | Tránh chồng chéo SQL, JDBC và framework |
| Code kiểm tra rows affected chưa? | Tránh commit nghiệp vụ thiếu bước |
| Exception có kích hoạt rollback? | Tránh framework commit khi nuốt lỗi |
| Có xử lý lỗi ở COMMIT không? | Constraint deferred và lỗi mạng có thể xuất hiện muộn |
| Có lưu mã idempotency? | Tránh xử lý trùng khi retry |
| Có giữ lock phù hợp? | Tránh race/deadlock |
| Có DDL không hỗ trợ transaction block? | Tránh migration hỏng giữa chừng |
| Có gửi email/HTTP trong transaction? | DB rollback không hủy side effects |
| Transaction có quá dài? | Giảm lock, MVCC bloat và pool exhaustion |
| Có theo dõi idle in transaction? | Phát hiện connection bỏ dở |
| Đã kiểm tra bằng hai session? | Xác nhận thay đổi chưa commit không bị nhầm là đã commit |

## 29. Tổng kết

**Autocommit** mô tả cách công cụ hoặc driver hoàn tất những statement độc lập; **ranh giới giao dịch** quyết định những thao tác PostgreSQL nào phải được **commit hoặc rollback cùng nhau**. PostgreSQL vẫn xử lý từng statement trong một ngữ cảnh transaction, nhưng điều đó không có nghĩa nhiều statement được gửi riêng tự thành một nghiệp vụ nguyên tử.

Ba điểm cần nhớ:

1. **Một đơn vị nghiệp vụ cần atomicity phải chạy trên một transaction và đúng connection.** Dùng `BEGIN ... COMMIT` trong SQL, `setAutoCommit(false)` trong JDBC hoặc transaction manager phù hợp trong framework.
2. **Chỉ commit khi toàn bộ điều kiện nghiệp vụ thỏa.** Kiểm tra số hàng cập nhật, constraints, lỗi concurrency và cả exception lúc commit; rollback khi cần hủy.
3. **Transaction PostgreSQL không bao trùm mọi hệ thống ngoài database.** Email, HTTP, filesystem và sequence có hành vi khác; dùng outbox, idempotency và đối soát để xử lý an toàn.

Khi thiết kế một workflow, hãy hỏi: **“Nếu bước sau thất bại, bước trước có được phép giữ lại hay không?”**. Nếu câu trả lời là **không**, các thay đổi PostgreSQL liên quan cần được đặt trong cùng transaction và cùng connection, có đường rollback rõ ràng và không giữ transaction mở lâu hơn cần thiết.
