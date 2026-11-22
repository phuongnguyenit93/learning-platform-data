# SERIALIZABLE, READ ONLY và khác biệt về tính nhất quán

Oracle Database hỗ trợ nhiều cách kiểm soát việc một transaction nhìn thấy dữ liệu được thay đổi đồng thời bởi những session khác. Hai chế độ thường cần phân biệt là **SERIALIZABLE** và **READ ONLY**. Cả hai cung cấp snapshot nhất quán ở cấp transaction, nhưng mục tiêu và quyền thao tác khác nhau:

- **SERIALIZABLE** cho phép transaction đọc và ghi, đồng thời giữ một góc nhìn dữ liệu nhất quán từ lúc transaction bắt đầu. Nếu transaction định sửa một hàng đã bị transaction khác thay đổi và COMMIT sau thời điểm snapshot của nó, Oracle có thể báo ORA-08177.
- **READ ONLY** cho phép transaction thực hiện các câu đọc trên cùng một snapshot transaction-level và không cho phép thay đổi dữ liệu. Nó phù hợp với báo cáo gồm nhiều câu SELECT cần nhìn cùng một thời điểm logic.
- **READ COMMITTED**, mức mặc định của Oracle, tạo snapshot riêng cho mỗi câu lệnh đọc. Hai SELECT trong cùng transaction có thể nhìn thấy hai trạng thái đã COMMIT khác nhau nếu transaction khác COMMIT ở giữa.

Điểm cốt lõi là phân biệt **snapshot cấp statement** với **snapshot cấp transaction**. SERIALIZABLE và READ ONLY giúp các lần đọc trong một transaction nhìn cùng một phiên bản dữ liệu đã COMMIT tại thời điểm transaction bắt đầu; READ COMMITTED lấy snapshot mới cho từng statement. Oracle dùng MVCC và UNDO để tái tạo phiên bản dữ liệu phù hợp, nhờ đó reader thông thường không phải đọc thay đổi chưa COMMIT của writer.

Bài học trình bày ngữ nghĩa ba chế độ, kịch bản hai session, cách xử lý ORA-08177, giới hạn của READ ONLY, tác động đến khóa và UNDO, cùng cách cấu hình transaction qua JDBC và Spring.

## 1. Snapshot và read consistency trong Oracle

Một câu SELECT không đơn giản đọc từng block theo trạng thái mới nhất tại đúng thời điểm nó chạm tới block đó. Oracle cung cấp **read consistency**: một câu lệnh đọc dữ liệu theo một snapshot nhất quán, được xác định bằng một System Change Number (SCN) phù hợp.

Khi session khác UPDATE một hàng nhưng chưa COMMIT:
- Session thực hiện UPDATE nhìn thấy thay đổi của chính transaction mình.
- Session đọc thông thường khác không nhìn thấy thay đổi chưa COMMIT.
- Reader có thể sử dụng UNDO để tái tạo phiên bản đã COMMIT trước đó.
- Nếu writer COMMIT giữa lúc một SELECT dài đang chạy, SELECT đó vẫn đọc theo snapshot của chính statement đã bắt đầu.

Cơ chế này thuộc nhóm **multi-version concurrency control (MVCC)**. Thay vì buộc reader và writer luôn chờ nhau, Oracle duy trì thông tin cần thiết để reader có thể nhìn phiên bản dữ liệu phù hợp với snapshot.

### 1.1. Hai khái niệm thời điểm cần phân biệt

**Statement-level snapshot** là mốc nhất quán của một câu SQL. Trong READ COMMITTED, mỗi câu SELECT mới có snapshot mới.

**Transaction-level snapshot** là mốc nhất quán dùng chung cho các câu đọc trong một transaction. SERIALIZABLE và READ ONLY sử dụng cách đọc này.

Ví dụ:

~~~text
Thời gian  ───────────────────────────────────────────────>

Session B (READ COMMITTED):
  SELECT lần 1 ── snapshot S1
                    |
Session A:          UPDATE; COMMIT
                                      |
Session B:                            SELECT lần 2 ── snapshot S2

S2 mới hơn S1, nên B có thể thấy dữ liệu A vừa COMMIT.
~~~

Trong SERIALIZABLE hoặc READ ONLY, các SELECT của B trong cùng transaction tiếp tục dùng snapshot transaction-level ban đầu, dù A COMMIT dữ liệu mới ở giữa.

### 1.2. Snapshot không có nghĩa session nhìn thấy dữ liệu cũ của chính nó

Một transaction luôn nhìn thấy các thay đổi do chính nó thực hiện. Snapshot transaction-level mô tả góc nhìn đối với thay đổi của các transaction khác; nó không che các thao tác chưa COMMIT của chính session.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

SELECT thứ hai trong cùng transaction nhìn thấy số dư sau UPDATE của chính nó, dù các session khác chưa nhìn thấy thay đổi đó.

### 1.3. UNDO giúp đọc phiên bản cũ

Khi một transaction thay đổi dữ liệu, Oracle ghi thông tin UNDO cần thiết để rollback và tái tạo phiên bản trước. Reader có thể dùng UNDO để nhìn trạng thái tại SCN snapshot.

UNDO không phải bản lưu trữ vô hạn:
- Dữ liệu UNDO được tái sử dụng theo cấu hình và áp lực workload.
- Transaction hoặc query chạy lâu có thể cần phiên bản cũ đã bị ghi đè.
- Một câu SELECT dài có thể gặp ORA-01555 nếu Oracle không còn đủ UNDO để tái tạo snapshot cần thiết.

Vì vậy, transaction đọc lâu và báo cáo lớn cũng cần được thiết kế có ý thức về thời gian chạy, lượng DML đồng thời và dung lượng UNDO.

## 2. READ COMMITTED: snapshot riêng cho mỗi statement

READ COMMITTED là isolation level mặc định của Oracle Database. Một câu SELECT nhìn dữ liệu đã COMMIT tại thời điểm statement bắt đầu. Câu SELECT tiếp theo trong cùng transaction có thể nhìn thấy các COMMIT mới hơn.

~~~sql
-- Session B: READ COMMITTED
SELECT balance
FROM accounts
WHERE account_id = 1;

-- Session A UPDATE và COMMIT.

-- Session B chạy một statement mới.
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Nếu A COMMIT giữa hai câu SELECT, câu thứ hai của B có thể thấy giá trị mới.

### 2.1. Non-repeatable read

Một transaction đọc cùng hàng hai lần và nhận hai giá trị khác nhau vì transaction khác COMMIT ở giữa:

~~~text
B: SELECT balance -> 1000
A: UPDATE balance = 900; COMMIT
B: SELECT balance -> 900
~~~

Không có dirty read ở đây. B chỉ thấy giá trị 900 sau khi A đã COMMIT.

### 2.2. Phantom rows

Một câu SELECT đầu tiên trả về một tập hàng. Session khác thêm hàng mới thỏa điều kiện và COMMIT. Câu SELECT thứ hai có thể thấy thêm hàng đó:

~~~text
B: SELECT * FROM orders WHERE status = 'NEW' -> 5 hàng
A: INSERT một đơn NEW; COMMIT
B: SELECT * FROM orders WHERE status = 'NEW' -> 6 hàng
~~~

Mỗi statement vẫn nhất quán tại snapshot riêng của nó. READ COMMITTED không hứa rằng mọi câu SELECT trong cùng transaction sẽ nhìn cùng một tập hàng.

### 2.3. READ COMMITTED không đọc dữ liệu chưa COMMIT

Nếu A UPDATE balance từ 1000 thành 900 nhưng chưa COMMIT, B SELECT thông thường vẫn thấy 1000. Chỉ sau COMMIT của A, một SELECT mới của B mới có thể thấy 900.

Không nên gọi việc B thấy giá trị mới ở statement thứ hai là dirty read. Giá trị đó đã được xác nhận.

## 3. SERIALIZABLE: snapshot nhất quán ở cấp transaction

Bắt đầu transaction SERIALIZABLE bằng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Lệnh này phải được thực hiện ở đầu transaction, trước các câu lệnh khác thuộc transaction. Transaction sau đó:
- Nhìn thấy dữ liệu đã COMMIT trước thời điểm snapshot của nó.
- Nhìn thấy các thay đổi do chính nó thực hiện.
- Không tự động nhìn thấy COMMIT mới từ session khác trong các câu đọc tiếp theo.
- Có thể thực hiện INSERT, UPDATE và DELETE.
- Có thể gặp ORA-08177 nếu muốn ghi một hàng đã bị transaction khác thay đổi sau khi snapshot bắt đầu.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

-- Thực hiện thêm các SELECT và DML trong transaction.
COMMIT;
~~~

Các câu đọc trong transaction sử dụng cùng snapshot transaction-level, cộng với những thay đổi do transaction hiện tại tạo ra.

### 3.1. Ví dụ hai session

Giả sử dữ liệu đã COMMIT ban đầu:

~~~text
ACCOUNT_ID = 1
BALANCE    = 1000
~~~

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

B nhận 1000. Snapshot transaction của B đã được thiết lập.

Session A:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

A COMMIT thành công.

Session B chạy SELECT lần nữa:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

B vẫn nhìn thấy 1000 vì transaction SERIALIZABLE tiếp tục dùng snapshot ban đầu. Session A đã COMMIT 900, nhưng thay đổi đó xảy ra sau snapshot của B.

Nếu B COMMIT hoặc ROLLBACK rồi bắt đầu transaction mới ở READ COMMITTED, một SELECT mới có thể nhìn thấy 900.

### 3.2. SERIALIZABLE không khóa toàn bộ bảng

SERIALIZABLE không có nghĩa các session khác bị cấm đọc hoặc ghi toàn bộ bảng. Session khác vẫn có thể thực hiện transaction riêng. Oracle dùng snapshot và kiểm tra xung đột ghi để bảo vệ tính nhất quán.

Một SELECT thông thường trong transaction SERIALIZABLE không nhất thiết khóa các hàng mà nó đọc. Nếu cần khóa hàng để điều phối cập nhật, hãy xem SELECT FOR UPDATE và thiết kế locking riêng.

### 3.3. DML trong SERIALIZABLE

SERIALIZABLE cho phép transaction ghi. Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

INSERT INTO transfer_log(
    transfer_id,
    account_id,
    amount
)
VALUES (7001, 1, 100);

COMMIT;
~~~

Các câu đọc của transaction dùng snapshot ban đầu, còn các thay đổi do transaction hiện tại thực hiện vẫn nhìn thấy trong chính transaction. Tuy nhiên, nếu hàng mục tiêu đã bị transaction khác thay đổi và COMMIT sau khi snapshot bắt đầu, DML có thể bị từ chối bằng ORA-08177.

## 4. ORA-08177: can't serialize access for this transaction

Lỗi ORA-08177 thường xuất hiện khi transaction SERIALIZABLE cố sửa một hàng đã được transaction khác thay đổi và COMMIT sau khi transaction hiện tại bắt đầu.

Ví dụ:

1. B bắt đầu SERIALIZABLE và đọc hàng ACCOUNT_ID=1 ở balance 1000.
2. A UPDATE hàng đó thành 900 rồi COMMIT.
3. B cố UPDATE cùng hàng theo snapshot cũ.

Session A:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
UPDATE accounts
SET balance = 800
WHERE account_id = 1;
~~~

Oracle có thể trả:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Oracle không cho B ghi theo cách có thể làm mất tính tuần tự của transaction snapshot.

### 4.1. Vì sao không nên chỉ chạy lại câu UPDATE?

Sau ORA-08177, transaction hiện tại có snapshot cũ. Chỉ chạy lại câu UPDATE trong cùng transaction không giải quyết được nguyên nhân snapshot đã lỗi thời. Cách xử lý thông thường:
1. ROLLBACK transaction hiện tại.
2. Bắt đầu một transaction SERIALIZABLE mới.
3. Đọc lại dữ liệu từ snapshot mới.
4. Tính lại quyết định nghiệp vụ.
5. Thực hiện lại toàn bộ đơn vị công việc.
6. COMMIT nếu mọi điều kiện còn hợp lệ.

Không chỉ retry câu SQL cuối cùng nếu các quyết định trước đó dựa trên dữ liệu của snapshot cũ.

### 4.2. Retry phải an toàn

Một transaction có thể được retry nếu thao tác nghiệp vụ có thể thực hiện lại an toàn. Cần:
- Giới hạn số lần retry.
- Có backoff ngắn nếu xung đột liên tục.
- Đảm bảo INSERT không tạo bản ghi trùng khi retry.
- Dùng khóa idempotency hoặc unique constraint cho yêu cầu có thể gửi lặp.
- Không gửi email hoặc gọi dịch vụ ngoài trước khi biết transaction đã COMMIT.
- Ghi log transaction attempt và nguyên nhân retry.

Nếu transaction đã tạo side effect bên ngoài database, ROLLBACK không thể thu hồi side effect đó. Thiết kế outbox hoặc cơ chế bù trừ để đồng bộ trạng thái.

### 4.3. Không phải mọi lỗi đều là ORA-08177

Một transaction SERIALIZABLE vẫn có thể gặp:
- Lỗi constraint.
- Deadlock.
- Timeout khóa.
- ORA-01555 do UNDO không đủ cho consistent read.
- Lỗi dữ liệu hoặc lỗi ứng dụng.

Chỉ retry những lỗi được xác định là tạm thời và có chính sách rõ ràng. Không retry vô hạn mọi SQLException.

## 5. READ ONLY: transaction chỉ đọc với snapshot transaction-level

Bắt đầu transaction READ ONLY:

~~~sql
SET TRANSACTION READ ONLY;
~~~

READ ONLY cung cấp snapshot nhất quán ở cấp transaction, tương tự góc nhìn đọc của SERIALIZABLE. Điểm khác biệt quan trọng là READ ONLY không cho phép transaction thay đổi dữ liệu.

Ví dụ báo cáo cần đọc nhiều bảng và tính nhiều chỉ số:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT SUM(amount) AS revenue
FROM orders;

SELECT COUNT(*) AS customer_count
FROM customers;

COMMIT;
~~~

Các câu SELECT thuộc cùng transaction READ ONLY nhìn cùng snapshot. Nếu session khác COMMIT một đơn hàng mới giữa câu SELECT thứ nhất và thứ hai, báo cáo hiện tại vẫn dùng snapshot ban đầu.

### 5.1. READ ONLY không phải chỉ là một SELECT

Một câu SELECT đơn lẻ trong READ COMMITTED đã có statement-level consistency. READ ONLY hữu ích khi cần nhiều câu SELECT riêng biệt mà vẫn muốn chúng nhìn cùng một snapshot.

Ví dụ:
- Báo cáo tổng số đơn.
- Báo cáo tổng doanh thu.
- Báo cáo số khách hàng.
- Đối chiếu tổng giữa các bảng.

Nếu mỗi câu SELECT chạy ở một transaction READ COMMITTED riêng hoặc cùng transaction nhưng mỗi statement có snapshot mới, các con số có thể phản ánh những thời điểm khác nhau. READ ONLY giúp các câu đọc trong cùng transaction nhất quán theo một mốc.

### 5.2. READ ONLY không cho phép DML

Trong transaction READ ONLY, không thực hiện INSERT, UPDATE hoặc DELETE:

~~~sql
SET TRANSACTION READ ONLY;

SELECT *
FROM accounts;

-- Không hợp lệ trong READ ONLY transaction:
UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;
~~~

Oracle từ chối thao tác thay đổi dữ liệu. Nếu cần vừa đọc vừa ghi, dùng READ COMMITTED hoặc SERIALIZABLE theo yêu cầu.

### 5.3. READ ONLY không phải khóa bảng cho session khác

Trong khi transaction READ ONLY đang chạy:
- Session khác vẫn có thể INSERT/UPDATE/DELETE và COMMIT.
- Transaction READ ONLY không nhìn thấy các thay đổi COMMIT sau snapshot của nó.
- Reader không khóa toàn bộ dữ liệu chỉ vì dùng READ ONLY.
- DML ở session khác không phải chờ transaction READ ONLY kết thúc chỉ để thay đổi hàng được đọc thông thường.

Đây là lý do READ ONLY phù hợp cho báo cáo đồng thời với workload ghi.

### 5.4. Kết thúc READ ONLY transaction

COMMIT hoặc ROLLBACK đều kết thúc transaction READ ONLY. Không có DML của transaction để xác nhận hay hủy, nhưng kết thúc transaction giải phóng snapshot và tài nguyên liên quan.

~~~sql
SET TRANSACTION READ ONLY;

SELECT SUM(amount) FROM orders;
SELECT COUNT(*) FROM customers;

COMMIT;
~~~

Sau COMMIT, câu SELECT tiếp theo bắt đầu transaction mới và có thể nhìn thấy các thay đổi đã COMMIT gần đây.

## 6. So sánh READ COMMITTED, SERIALIZABLE và READ ONLY

| Tiêu chí | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Mặc định Oracle | Có | Không | Không |
| Snapshot | Mỗi statement | Cấp transaction | Cấp transaction |
| Dirty read | Không | Không | Không |
| Câu SELECT mới thấy COMMIT mới của session khác | Có thể thấy | Không trong transaction hiện tại | Không trong transaction hiện tại |
| Nhìn thấy thay đổi của chính transaction | Có | Có | Không có DML |
| Cho phép INSERT/UPDATE/DELETE | Có | Có | Không |
| Có thể gặp ORA-08177 do xung đột ghi | Không theo cơ chế SERIALIZABLE | Có | Không có ghi của chính transaction |
| Phù hợp | Giao dịch ứng dụng thông thường | Giao dịch cần snapshot ổn định và có ghi | Báo cáo nhiều câu SELECT cùng snapshot |

### 6.1. READ COMMITTED

Dùng khi:
- Mỗi câu lệnh có thể đọc trạng thái mới nhất đã COMMIT tại lúc bắt đầu.
- Transaction không yêu cầu mọi câu SELECT nhìn cùng một snapshot.
- Muốn mức mặc định cho ứng dụng OLTP.
- Chấp nhận non-repeatable read/phantom giữa các statement.

### 6.2. SERIALIZABLE

Cân nhắc khi:
- Một đơn vị công việc cần đọc nhiều lần trên cùng snapshot.
- Các quyết định ghi phụ thuộc vào trạng thái đã đọc.
- Ứng dụng có thể xử lý ORA-08177 bằng cách rollback và retry toàn transaction.
- Transaction đủ ngắn và có thể kiểm soát xung đột.

### 6.3. READ ONLY

Cân nhắc khi:
- Một báo cáo cần chạy nhiều câu SELECT.
- Các tổng số cần đối chiếu theo cùng một thời điểm logic.
- Transaction không cần DML.
- Có thể kết thúc transaction đọc sau khi hoàn thành báo cáo.

Không dùng SERIALIZABLE chỉ vì muốn một báo cáo đọc nhất quán nếu không cần ghi. READ ONLY diễn đạt đúng hơn ý định chỉ đọc.

## 7. So sánh qua timeline hai session

Giả sử bảng ACCOUNT có số dư ban đầu là 1000 đã COMMIT.

### 7.1. READ COMMITTED

Session B:

~~~sql
-- READ COMMITTED mặc định.
SELECT balance FROM account WHERE account_id = 1;
-- 1000
~~~

Session A:

~~~sql
UPDATE account
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
SELECT balance FROM account WHERE account_id = 1;
-- 900
~~~

Hai SELECT của B dùng hai snapshot statement khác nhau.

### 7.2. SERIALIZABLE

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance FROM account WHERE account_id = 1;
-- 1000
~~~

Session A:

~~~sql
UPDATE account
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

Session B:

~~~sql
SELECT balance FROM account WHERE account_id = 1;
-- Vẫn 1000 trong transaction hiện tại.
~~~

Sau khi B kết thúc transaction:

~~~sql
COMMIT;

SELECT balance FROM account WHERE account_id = 1;
-- Transaction mới trong READ COMMITTED có thể thấy 900.
~~~

### 7.3. READ ONLY

Session B:

~~~sql
SET TRANSACTION READ ONLY;

SELECT balance FROM account WHERE account_id = 1;
-- 1000
~~~

Session A UPDATE 900 và COMMIT. Session B SELECT lại vẫn thấy 1000. B không thể UPDATE hàng đó trong transaction READ ONLY. Sau COMMIT của B, một SELECT mới có thể thấy 900.

### 7.4. Bảng tổng hợp

| Thời điểm | Session A | B READ COMMITTED | B SERIALIZABLE | B READ ONLY |
| --- | --- | ---: | ---: | ---: |
| Ban đầu | Không thay đổi | 1000 | 1000 | 1000 |
| A UPDATE 900, chưa COMMIT | 900 | 1000 | 1000 | 1000 |
| A COMMIT | 900 | SELECT mới: 900 | SELECT tiếp: 1000 | SELECT tiếp: 1000 |
| B kết thúc transaction và SELECT mới | 900 | 900 | 900 | 900 |

Các cột của B giả định mỗi SELECT được bắt đầu sau sự kiện tương ứng. Nếu B đang chạy một statement từ trước khi A COMMIT, statement đó vẫn giữ snapshot riêng của nó ngay cả trong READ COMMITTED.

## 8. Thiết lập isolation level đúng thời điểm

Oracle yêu cầu SET TRANSACTION được dùng ở đầu transaction. Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT ...
UPDATE ...
COMMIT;
~~~

Hoặc:

~~~sql
SET TRANSACTION READ ONLY;

SELECT ...
SELECT ...
COMMIT;
~~~

Không chạy một SELECT hoặc DML trước rồi mới SET TRANSACTION cho cùng transaction:

~~~sql
SELECT COUNT(*) FROM orders;

-- Không đặt isolation level ở giữa transaction.
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Nếu transaction đã bắt đầu, câu SET TRANSACTION có thể báo lỗi vì không còn ở đầu transaction.

### 8.1. Transaction bắt đầu khi nào?

Trong SQL client, transaction DML thường bắt đầu khi session thực hiện thao tác thuộc transaction. Với SERIALIZABLE/READ ONLY, SET TRANSACTION thiết lập chế độ cho transaction kế tiếp và phải được chạy trước các câu lệnh khác của transaction.

Trong ứng dụng JDBC, setAutoCommit(false) thường cấu hình connection để nhiều statement nằm trong transaction; transaction thực tế được database bắt đầu khi statement đầu tiên được gửi. Vì vậy, hãy cấu hình isolation/READ ONLY trước câu SQL nghiệp vụ đầu tiên.

### 8.2. Không trộn DDL với transaction cần giữ snapshot

Oracle DDL có quy tắc implicit commit. CREATE, ALTER, DROP và TRUNCATE có thể kết thúc transaction trước đó. Không chạy DDL giữa một transaction SERIALIZABLE/READ ONLY mà muốn giữ nguyên snapshot và khả năng rollback.

Thực hiện DDL trong bước triển khai/schema migration riêng, ngoài transaction nghiệp vụ.

## 9. READ ONLY và SELECT FOR UPDATE

SELECT FOR UPDATE đọc hàng và yêu cầu khóa để session có thể cập nhật an toàn sau đó:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

Đây là thao tác đọc có khóa, không phải câu SELECT thông thường. Nó không phù hợp với transaction READ ONLY vì transaction đó không được phép thay đổi dữ liệu và không được dùng để lấy khóa ghi theo cách này.

Trong SERIALIZABLE, SELECT FOR UPDATE vẫn là cơ chế khóa tường minh; cần hiểu tương tác với transaction isolation và xung đột. Không dùng SELECT FOR UPDATE cho một báo cáo chỉ cần snapshot nhất quán.

### 9.1. Khi cần khóa hàng, dùng transaction ghi

Ví dụ kiểm tra số dư rồi trừ tiền:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;

COMMIT;
~~~

Khóa hàng giúp transaction khác không đồng thời cập nhật cùng hàng trước khi transaction hiện tại kết thúc. Trong ứng dụng thực tế, phải kiểm tra số hàng UPDATE để xác nhận giao dịch được thực hiện.

### 9.2. Khi chỉ cần báo cáo nhất quán, không khóa từng hàng

Nếu mục tiêu chỉ là đọc tổng doanh thu, tổng đơn và số khách hàng cùng một snapshot, READ ONLY phù hợp hơn. Không cần khóa từng bảng bằng SELECT FOR UPDATE chỉ để ngăn số liệu thay đổi giữa các câu SELECT.

## 10. SERIALIZABLE và lỗi xung đột ghi

SERIALIZABLE giữ snapshot transaction-level nhưng vẫn cho phép ghi. Khi hai transaction cùng cập nhật dữ liệu, phải xét thời điểm bắt đầu và COMMIT của từng transaction.

### 10.1. Cùng đọc một giá trị, cùng muốn cập nhật

Giả sử:
- A bắt đầu SERIALIZABLE, đọc balance 1000.
- B bắt đầu READ COMMITTED, UPDATE balance thành 900 và COMMIT.
- A cố UPDATE balance thành 800.

A đang làm việc trên snapshot cũ. Oracle có thể báo ORA-08177 vì hàng đã bị thay đổi sau snapshot của A.

### 10.2. Retry toàn bộ nghiệp vụ

Luồng xử lý:

~~~text
Bắt đầu transaction SERIALIZABLE
          |
Đọc trạng thái và kiểm tra điều kiện
          |
Thực hiện DML
          |
     COMMIT thành công?
       /          \
     Có            Không
     |               |
Trả kết quả      ORA-08177?
                     |
               ROLLBACK toàn bộ
                     |
             Retry có giới hạn
                     |
             Đọc lại snapshot mới
                     |
             Tính lại quyết định
~~~

Khi retry, phải đọc lại các dữ liệu đầu vào và tính lại quyết định nghiệp vụ. Không tái sử dụng kết quả tính từ snapshot cũ.

### 10.3. Không gửi side effect trước COMMIT

Ví dụ không an toàn:

~~~text
SERIALIZABLE transaction
  UPDATE order
  Gửi email "đã xác nhận"
  COMMIT -> ORA-08177
~~~

Database rollback được, nhưng email đã gửi. Người dùng nhận thông báo xác nhận cho một giao dịch chưa được xác nhận.

Một cách thiết kế là ghi sự kiện cần gửi vào bảng OUTBOX trong cùng transaction với đơn hàng; một worker khác đọc các outbox row đã COMMIT rồi gửi thông báo. Cách này giúp trạng thái database và sự kiện được ghi cùng transaction, đồng thời worker có thể retry gửi theo idempotency key.

## 11. SERIALIZABLE, READ ONLY và UNDO

Snapshot transaction-level có thể tồn tại lâu hơn snapshot statement-level. Trong thời gian đó, các transaction khác vẫn tiếp tục DML và tạo UNDO.

Một báo cáo READ ONLY chạy nhiều giờ có thể cần Oracle tái tạo dữ liệu ở SCN cũ. Nếu UNDO cần thiết đã bị ghi đè, truy vấn có thể gặp:

~~~text
ORA-01555: snapshot too old
~~~

### 11.1. Nguyên nhân thường gặp

- Query đọc quá lâu.
- Transaction đọc mở quá lâu.
- DML đồng thời lớn làm UNDO bị tái sử dụng nhanh.
- UNDO tablespace/retention không đáp ứng workload.
- Câu truy vấn xử lý nhiều dữ liệu hoặc có plan kém hiệu quả.

### 11.2. Hướng xử lý

- Rút ngắn thời gian transaction READ ONLY.
- Chạy báo cáo trên replica/reporting database nếu kiến trúc cho phép.
- Tối ưu truy vấn, lọc đúng dữ liệu và xem execution plan.
- Phối hợp DBA đánh giá UNDO tablespace và retention.
- Tránh giữ transaction chỉ đọc mở trong khi ứng dụng chờ người dùng hoặc xử lý ngoài database.
- Nếu nghiệp vụ cho phép, chia báo cáo thành các đơn vị đọc độc lập và chấp nhận snapshot riêng; nếu cần cùng snapshot thì không chia tùy tiện.

Không tăng UNDO_RETENTION một cách máy móc mà không đánh giá dung lượng, retention guarantee và workload. Đây là cấu hình vận hành cần DBA xem xét.

## 12. SERIALIZABLE không thay thế mọi quy tắc khóa và constraint

Một số nghiệp vụ cần bảo đảm điều kiện trên nhiều hàng, ví dụ:
- Không cho phép tổng phân bổ vượt hạn mức.
- Không cho phép hai lịch đặt trùng thời gian.
- Không cho phép tồn kho âm.
- Chỉ cho một yêu cầu giữ một tài nguyên.

SERIALIZABLE giúp các lần đọc trong transaction dùng snapshot ổn định và kiểm tra xung đột ghi trên hàng bị sửa. Nhưng không nên dùng isolation level như một sự thay thế cho:
- PRIMARY KEY và UNIQUE constraint.
- CHECK constraint.
- Foreign key.
- Khóa tường minh khi cần điều phối một hàng.
- Thiết kế dữ liệu để biểu diễn invariant nghiệp vụ.

Hãy đặt invariant quan trọng ở database bằng constraint khi có thể. Nếu điều kiện phụ thuộc nhiều hàng hoặc một khoảng thời gian, cần thiết kế locking/serialization phù hợp và kiểm thử concurrency thực tế.

### 12.1. Ví dụ bảo vệ số dư không âm

Có thể thêm CHECK constraint:

~~~sql
ALTER TABLE accounts
ADD CONSTRAINT ck_accounts_balance_nonnegative
CHECK (balance >= 0);
~~~

Sau đó UPDATE:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Constraint bảo vệ invariant ở tầng database ngay cả khi nhiều ứng dụng cùng truy cập.

### 12.2. Không dựa vào SELECT rồi UPDATE mà thiếu điều kiện

Nếu ứng dụng SELECT số dư, kiểm tra đủ tiền rồi UPDATE sau đó trong READ COMMITTED, một transaction khác có thể thay đổi số dư ở giữa. Có thể dùng UPDATE có điều kiện và kiểm tra row count, hoặc khóa hàng phù hợp.

SERIALIZABLE có thể là một phần của thiết kế, nhưng không thay thế việc xác định chính xác điều kiện cập nhật và cách retry.

## 13. JDBC: thiết lập SERIALIZABLE

JDBC hỗ trợ isolation level SERIALIZABLE thông qua Connection API:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

public final class TransactionSetup {
    public static void beginSerializable(Connection connection)
            throws SQLException {
        connection.setAutoCommit(false);
        connection.setTransactionIsolation(
            Connection.TRANSACTION_SERIALIZABLE
        );
    }
}
~~~

Cấu hình phải được thực hiện trước câu SQL nghiệp vụ đầu tiên trong transaction. Driver và pool cần được cấu hình đúng để connection được mượn có isolation mong muốn.

### 13.1. Ví dụ transaction SERIALIZABLE

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountService {
    private final DataSource dataSource;

    public AccountService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void withdraw(long accountId, BigDecimal amount)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            connection.setTransactionIsolation(
                Connection.TRANSACTION_SERIALIZABLE
            );

            try {
                BigDecimal balance;

                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT balance FROM accounts WHERE account_id = ?")) {
                    ps.setLong(1, accountId);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException("Account not found");
                        }
                        balance = rs.getBigDecimal("BALANCE");
                    }
                }

                if (balance.compareTo(amount) < 0) {
                    throw new SQLException("Insufficient balance");
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE accounts " +
                        "SET balance = balance - ? " +
                        "WHERE account_id = ?")) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, accountId);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Account update failed");
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
    }
}
~~~

Đây là ví dụ minh họa transaction boundary. Một triển khai production cần quyết định rõ cách xử lý ORA-08177, retry, idempotency, logging và quy tắc số dư. Có thể dùng UPDATE có điều kiện hoặc SELECT FOR UPDATE nếu đó là cơ chế concurrency phù hợp hơn.

### 13.2. Đặt isolation trước khi transaction bắt đầu

Nếu connection đã thực hiện câu SQL trong transaction, thay đổi isolation level có thể bị driver/database từ chối hoặc không có hiệu lực như mong đợi. Hãy cấu hình ngay sau khi lấy connection và trước statement nghiệp vụ đầu tiên.

Với pool, isolation level có thể được reset hoặc tái sử dụng theo cấu hình. Kiểm tra pool reset connection state khi trả connection, tránh để SERIALIZABLE rò sang request tiếp theo.

## 14. JDBC: transaction READ ONLY

JDBC có phương thức Connection.setReadOnly(boolean), nhưng đây là một **hint** cho driver/DBMS về ý định chỉ đọc. Không nên mặc định rằng gọi setReadOnly(true) luôn tương đương chính xác với câu Oracle SQL SET TRANSACTION READ ONLY và luôn được server cưỡng chế.

Nếu cần transaction READ ONLY thực sự theo ngữ nghĩa Oracle, phải thiết lập bằng cơ chế mà Oracle server hỗ trợ, trước statement đầu tiên:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (var statement = connection.createStatement()) {
        statement.execute("SET TRANSACTION READ ONLY");
    }

    try {
        // Các SELECT báo cáo dùng cùng connection/transaction.
        // Không thực hiện DML ở đây.

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
~~~

Điểm cần nhớ:
- Dùng cùng một Connection cho toàn bộ các câu SELECT trong báo cáo.
- SET TRANSACTION READ ONLY phải là lệnh đầu tiên thuộc transaction.
- Không trả connection về pool trước khi transaction kết thúc.
- Không thực hiện DML hoặc SELECT FOR UPDATE trong transaction này.
- Kết thúc bằng COMMIT hoặc ROLLBACK.
- Kiểm thử với đúng Oracle JDBC driver và transaction manager của ứng dụng.

### 14.1. Vì sao setReadOnly(true) chưa đủ để khẳng định?

JDBC API định nghĩa read-only connection như một gợi ý tối ưu hóa cho driver. Mức thực thi phụ thuộc driver và database. Nếu ứng dụng cần bảo đảm database từ chối DML trong transaction, hãy kiểm tra cách driver/transaction manager ánh xạ thuộc tính đó hoặc sử dụng SET TRANSACTION READ ONLY theo đúng thứ tự.

Không gọi setReadOnly giữa một transaction đang mở rồi giả định snapshot của transaction hiện tại thay đổi thành READ ONLY.

## 15. Spring và transaction isolation

Spring quản lý transaction qua PlatformTransactionManager. Có thể yêu cầu SERIALIZABLE bằng annotation:

~~~java
@Service
public class ReportAwareService {

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void performConsistentUpdate() {
        // Đọc và ghi trong cùng transaction.
    }
}
~~~

Với transaction READ COMMITTED mặc định, có thể không cần chỉ định isolation.

### 15.1. @Transactional(readOnly = true) là gì?

~~~java
@Transactional(readOnly = true)
public ReportSummary buildReport() {
    // Nhiều câu SELECT.
}
~~~

Thuộc tính readOnly biểu đạt ý định phương thức chỉ đọc và có thể giúp framework/driver tối ưu. Tuy nhiên, **không mặc định đồng nhất thuộc tính Spring readOnly với lệnh Oracle SET TRANSACTION READ ONLY**. Tùy transaction manager, JDBC driver và cấu hình, readOnly có thể chỉ là hint hoặc được xử lý theo cách khác.

Nếu yêu cầu nghiệp vụ là Oracle server phải cưỡng chế transaction chỉ đọc và giữ snapshot transaction-level, cần xác minh cơ chế tích hợp cụ thể hoặc chủ động thực hiện SET TRANSACTION READ ONLY ở đầu transaction qua cùng connection.

### 15.2. @Transactional kết hợp isolation

~~~java
@Transactional(
    isolation = Isolation.SERIALIZABLE,
    rollbackFor = Exception.class
)
public void performSerializableWork() throws Exception {
    // Đơn vị công việc có thể retry toàn bộ khi ORA-08177.
}
~~~

Spring isolation setting có hiệu lực khi transaction manager tạo transaction mới. Nếu phương thức tham gia một transaction đã tồn tại, isolation khai báo trên phương thức tham gia có thể không được áp dụng như một transaction mới; cần xem propagation và validateExistingTransaction nếu muốn phát hiện mismatch.

### 15.3. Self-invocation và proxy

Trong cấu hình Spring proxy phổ biến, gọi một phương thức @Transactional từ phương thức khác trong cùng instance có thể không đi qua proxy. Khi đó annotation có thể không được áp dụng như dự kiến.

Thiết kế service boundary rõ ràng, kiểm thử transaction thực tế và xem log transaction manager thay vì chỉ nhìn annotation.

### 15.4. Không tự COMMIT bên trong phương thức do Spring quản lý

Nếu Spring transaction manager sở hữu transaction, không gọi commit/rollback trực tiếp trên connection được framework quản lý. Để transaction manager kết thúc transaction theo ranh giới phương thức hoặc theo propagation.

## 16. READ ONLY cho báo cáo nhiều câu SELECT

Giả sử báo cáo cần ba con số:
- Tổng đơn hàng.
- Tổng doanh thu.
- Số khách hàng đã mua hàng.

Nếu chạy từng SELECT trong READ COMMITTED và có đơn hàng mới COMMIT giữa các câu, ba con số có thể phản ánh các snapshot khác nhau. Một transaction READ ONLY có thể giữ cùng snapshot:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT SUM(amount) AS revenue
FROM orders;

SELECT COUNT(DISTINCT customer_id) AS buyer_count
FROM orders;

COMMIT;
~~~

Các con số trong cùng transaction nhìn cùng mốc dữ liệu đã COMMIT.

### 16.1. Báo cáo và thời gian chạy

READ ONLY không làm câu truy vấn tự động nhanh hơn. Nó cung cấp tính nhất quán ở cấp transaction. Hiệu năng vẫn phụ thuộc:
- Plan của từng câu SELECT.
- Index và partition pruning.
- Số lượng dữ liệu đọc.
- PGA/TEMP.
- UNDO retention và tốc độ DML đồng thời.
- Thời gian transaction được giữ mở.

Một báo cáo cần cùng snapshot nhưng chạy nhiều giờ có thể gây áp lực UNDO. Cần phối hợp DBA và cân nhắc reporting replica hoặc snapshot/reporting pipeline.

### 16.2. Một SELECT đơn lẻ có cần READ ONLY không?

Không nhất thiết. Một SELECT đơn lẻ trong READ COMMITTED đã có statement-level read consistency. Chỉ cần READ ONLY khi cần nhiều câu SELECT trong cùng transaction dùng chung snapshot hoặc cần transaction chỉ đọc được cưỡng chế.

### 16.3. Không giữ transaction báo cáo trong lúc chờ người dùng

Không mở READ ONLY transaction, chạy vài SELECT, rồi để connection chờ người dùng bấm nút tiếp tục. Snapshot transaction-level và tài nguyên liên quan vẫn được giữ. Hãy chạy toàn bộ báo cáo trong một khoảng thời gian hữu hạn, trả kết quả rồi COMMIT.

## 17. DDL và các sự kiện kết thúc transaction

Oracle DDL như CREATE, ALTER, DROP và TRUNCATE có quy tắc implicit commit. Vì vậy:
- Không chạy DDL giữa transaction SERIALIZABLE đang cần giữ snapshot.
- Không chạy DDL giữa transaction READ ONLY đang mở.
- Không dùng ROLLBACK để kỳ vọng hủy DDL đã thành công.
- Thực hiện schema migration trong quy trình riêng.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM orders;

CREATE TABLE temp_report(id NUMBER);

-- DDL có thể kết thúc transaction trước đó bằng implicit commit.
~~~

Không dùng mẫu này trong ứng dụng nghiệp vụ. DDL không phải một bước đọc/ghi thông thường trong cùng transaction.

Sequence cũng không tuân theo rollback như dữ liệu bảng. NEXTVAL đã cấp không được trả lại khi transaction rollback; khoảng trống trong số sequence là bình thường.

## 18. Bộ dữ liệu thực hành: hai session và ba isolation mode

Tạo bảng sandbox:

~~~sql
CREATE TABLE isolation_demo (
    id      NUMBER(6) PRIMARY KEY,
    balance NUMBER(12,2) NOT NULL
);

INSERT INTO isolation_demo VALUES (1, 1000);
INSERT INTO isolation_demo VALUES (2, 500);
COMMIT;
~~~

Mở hai connection riêng biệt, gọi là A và B.

### 18.1. Thử READ COMMITTED

Session B:

~~~sql
SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Nhận 1000.

Session A:

~~~sql
UPDATE isolation_demo
SET balance = 900
WHERE id = 1;

COMMIT;
~~~

Session B chạy SELECT mới:

~~~sql
SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Nhận 900.

### 18.2. Thử SERIALIZABLE

Đặt lại dữ liệu trong transaction riêng nếu cần:

~~~sql
UPDATE isolation_demo
SET balance = 1000
WHERE id = 1;

COMMIT;
~~~

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Nhận 1000.

Session A:

~~~sql
UPDATE isolation_demo
SET balance = 900
WHERE id = 1;

COMMIT;
~~~

Session B:

~~~sql
SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Vẫn nhận 1000 trong transaction hiện tại. B kết thúc transaction:

~~~sql
COMMIT;
~~~

Sau đó SELECT mới trong B có thể nhận 900.

### 18.3. Thử ORA-08177

Đặt lại balance 1000 và COMMIT.

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Session A:

~~~sql
UPDATE isolation_demo
SET balance = 900
WHERE id = 1;

COMMIT;
~~~

Session B:

~~~sql
UPDATE isolation_demo
SET balance = 800
WHERE id = 1;
~~~

Oracle có thể trả ORA-08177. Nếu lỗi xảy ra, B ROLLBACK toàn transaction trước khi thử lại bằng transaction mới.

### 18.4. Thử READ ONLY

Đặt lại dữ liệu và COMMIT. Session B:

~~~sql
SET TRANSACTION READ ONLY;

SELECT balance
FROM isolation_demo
WHERE id = 1;
~~~

Session A cập nhật và COMMIT. Session B SELECT lại vẫn thấy snapshot ban đầu. Nếu B thử UPDATE, Oracle từ chối vì transaction chỉ đọc.

B kết thúc:

~~~sql
COMMIT;
~~~

Sau đó SELECT mới có thể thấy dữ liệu mới nhất đã COMMIT.

### 18.5. Dọn bảng sandbox

~~~sql
DROP TABLE isolation_demo PURGE;
~~~

Chỉ xóa bảng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP TABLE là DDL và có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 19. Những nhầm lẫn thường gặp

**SERIALIZABLE và READ ONLY là cùng một chế độ.** Không đúng. Cả hai có snapshot transaction-level, nhưng SERIALIZABLE cho phép DML và có thể gặp ORA-08177; READ ONLY cấm thay đổi dữ liệu.

**READ COMMITTED giữ cùng snapshot cho cả transaction.** Không đúng. Mỗi statement đọc có snapshot riêng.

**SERIALIZABLE khóa toàn bộ bảng để giữ snapshot.** Không đúng. Oracle dùng MVCC/UNDO và kiểm tra xung đột ghi; nó không khóa toàn bộ bảng chỉ vì transaction dùng SERIALIZABLE.

**READ ONLY ngăn session khác UPDATE.** Không đúng. Session khác vẫn có thể ghi và COMMIT; transaction READ ONLY tiếp tục nhìn snapshot của nó.

**READ ONLY chỉ có ích cho một SELECT.** Không đúng. Một SELECT đơn đã có statement consistency trong READ COMMITTED; READ ONLY hữu ích khi nhiều SELECT cần cùng snapshot transaction-level.

**SELECT FOR UPDATE là một SELECT chỉ đọc thông thường.** Không đúng. Nó yêu cầu khóa hàng và không phù hợp với transaction READ ONLY.

**SERIALIZABLE không thể có lỗi vì nó đã bảo đảm tuần tự.** Không đúng. Khi có xung đột ghi, Oracle có thể báo ORA-08177 và ứng dụng phải xử lý.

**Sau ORA-08177 chỉ cần chạy lại câu UPDATE.** Không đúng. Snapshot transaction đã cũ; thường phải ROLLBACK và retry toàn bộ đơn vị công việc.

**Transaction READ ONLY không cần kết thúc.** Không đúng. Cần COMMIT/ROLLBACK để kết thúc và trả tài nguyên.

**Connection.setReadOnly(true) luôn tương đương SET TRANSACTION READ ONLY.** Không đúng. JDBC định nghĩa đây là hint; cần xác minh driver/DBMS hoặc dùng cơ chế Oracle rõ ràng khi cần cưỡng chế.

**@Transactional(readOnly = true) luôn phát lệnh SET TRANSACTION READ ONLY.** Không đúng. Thuộc tính Spring có thể là hint tùy transaction manager và driver.

**SERIALIZABLE loại bỏ mọi nhu cầu constraint.** Không đúng. UNIQUE, CHECK, foreign key và điều kiện UPDATE vẫn cần thiết để bảo vệ invariant nghiệp vụ.

**READ ONLY không dùng UNDO.** Không đúng. Snapshot cũ có thể cần UNDO để tái tạo phiên bản dữ liệu; transaction đọc lâu có thể gặp ORA-01555.

**COMMIT của session khác làm transaction SERIALIZABLE chuyển sang snapshot mới.** Không đúng. Snapshot transaction-level được giữ cho đến khi transaction hiện tại kết thúc.

## 20. Quy trình chọn isolation level

Trước khi chọn isolation cho một nghiệp vụ, hãy trả lời:

1. Mỗi câu SELECT có thể nhìn trạng thái mới nhất đã COMMIT tại thời điểm chạy không?
2. Nhiều câu SELECT trong cùng transaction có cần cùng một snapshot không?
3. Transaction có cần thực hiện DML không?
4. Nếu có DML, xung đột ghi có thể xảy ra thường xuyên không?
5. Ứng dụng có thể ROLLBACK và retry toàn bộ transaction không?
6. Transaction có dài và đọc nhiều dữ liệu không?
7. Có side effect ngoài database trước COMMIT không?
8. Có thể bảo vệ invariant bằng constraint hoặc UPDATE có điều kiện không?
9. Có cần SELECT FOR UPDATE để khóa một số hàng cụ thể không?
10. Có đủ UNDO cho thời gian snapshot dự kiến không?

Gợi ý:

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| OLTP thông thường, mỗi statement đọc snapshot mới | READ COMMITTED |
| Nhiều câu đọc cần cùng snapshot, không ghi | READ ONLY |
| Nhiều câu đọc cần cùng snapshot và transaction vẫn phải ghi | SERIALIZABLE, có xử lý ORA-08177 |
| Đọc hàng rồi khóa để cập nhật | READ COMMITTED hoặc SERIALIZABLE kết hợp SELECT FOR UPDATE khi phù hợp |
| Bảo vệ số dư không âm | CHECK constraint và UPDATE có điều kiện; isolation bổ sung theo thiết kế |
| Báo cáo dài, nhiều bảng, cần cùng thời điểm logic | READ ONLY hoặc reporting snapshot/replica, có đánh giá UNDO |

Không chọn isolation level chỉ vì tên nghe mạnh hơn. Chọn theo ngữ nghĩa đọc, quyền ghi, khả năng retry, độ dài transaction và tải thực tế.

## 21. Bài tập tự luyện

1. Giải thích khác biệt giữa statement-level snapshot và transaction-level snapshot.
2. Trong READ COMMITTED, hai câu SELECT trong cùng transaction có thể trả giá trị khác nhau không? Mô tả timeline hai session.
3. Vì sao một SELECT đang chạy vẫn nhìn thấy snapshot cũ dù session khác COMMIT giữa lúc truy vấn chạy?
4. Viết kịch bản chứng minh session B không đọc được UPDATE chưa COMMIT của session A.
5. Viết kịch bản READ COMMITTED cho thấy B nhìn thấy thay đổi sau COMMIT của A.
6. Viết cùng kịch bản bằng SERIALIZABLE và giải thích vì sao SELECT thứ hai của B vẫn thấy giá trị cũ.
7. READ ONLY và SERIALIZABLE giống nhau ở điểm nào?
8. Vì sao READ ONLY không thể thay thế SERIALIZABLE cho transaction cần UPDATE?
9. Vì sao SERIALIZABLE không thể thay thế READ ONLY nếu mục tiêu là cưỡng chế transaction chỉ đọc?
10. Một báo cáo có bốn câu SELECT cần đối chiếu số liệu tại cùng một thời điểm. Vì sao READ ONLY phù hợp?
11. Nếu session khác INSERT hàng mới rồi COMMIT giữa hai câu SELECT trong READ ONLY, câu thứ hai có thấy hàng mới không?
12. ORA-08177 xảy ra trong tình huống cạnh tranh nào?
13. Sau ORA-08177, vì sao cần ROLLBACK và retry toàn bộ đơn vị công việc?
14. Tại sao retry phải tính lại quyết định từ snapshot mới?
15. Vì sao không gửi email xác nhận trước khi transaction SERIALIZABLE COMMIT thành công?
16. Connection.setReadOnly(true) khác SET TRANSACTION READ ONLY thế nào?
17. Trong JDBC, phải thiết lập autoCommit và isolation trước hay sau statement đầu tiên?
18. Spring @Transactional(readOnly = true) có mặc định tương đương lệnh Oracle READ ONLY không?
19. Khi nào một transaction SERIALIZABLE có thể cần SELECT FOR UPDATE?
20. Vì sao SELECT FOR UPDATE không phù hợp với transaction READ ONLY?
21. ORA-01555 liên quan thế nào đến snapshot transaction-level và UNDO?
22. DDL giữa transaction có thể ảnh hưởng snapshot và rollback như thế nào?
23. Một ứng dụng dùng SERIALIZABLE nhưng không có unique constraint cho khóa nghiệp vụ. Isolation có thay thế constraint không?
24. Thiết kế một bài test hai session để so sánh READ COMMITTED, SERIALIZABLE và READ ONLY.
25. Một transaction READ ONLY chạy nhiều giờ. Những rủi ro vận hành nào cần DBA đánh giá?

**READ COMMITTED tạo snapshot cho từng statement; SERIALIZABLE và READ ONLY giữ snapshot ở cấp transaction.** SERIALIZABLE cho phép ghi nhưng cần xử lý xung đột bằng ROLLBACK và retry khi gặp ORA-08177. READ ONLY chỉ cho phép đọc và phù hợp với báo cáo nhiều câu SELECT cần cùng một thời điểm logic. Chọn đúng chế độ, giữ transaction ngắn, bảo vệ invariant bằng constraint và quản lý UNDO giúp nhiều session làm việc đồng thời mà vẫn giữ được tính nhất quán của dữ liệu.
