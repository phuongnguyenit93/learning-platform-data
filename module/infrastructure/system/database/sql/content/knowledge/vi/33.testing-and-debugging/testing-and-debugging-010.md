# Kiểm thử giao dịch bằng nhiều kết nối có thứ tự thực thi

Trong **Database SQL**, một giao dịch có thể chạy đúng khi thử một mình nhưng vẫn cho kết quả sai khi nhiều người dùng hoặc tiến trình thao tác đồng thời. Lỗi thường chỉ xuất hiện khi các câu lệnh từ những kết nối khác nhau xen kẽ theo một thứ tự cụ thể: hai nhân viên cùng trừ tiền, hai worker cùng nhận một công việc, một transaction đọc trong lúc transaction khác cập nhật, hoặc hai giao dịch khóa tài nguyên theo thứ tự ngược nhau.

Muốn kiểm thử những tình huống này, cần mô phỏng **nhiều kết nối database độc lập** và điều khiển thứ tự thực thi của từng câu lệnh. Một bài test chỉ chạy hai câu SQL tuần tự trên cùng một connection không kiểm tra được hành vi đồng thời. Tạo nhiều thread nhưng không điều khiển điểm đồng bộ thường làm test chập chờn: lúc lỗi xuất hiện, lúc không.

Bài học trình bày cách dựng lịch thực thi có chủ đích, quan sát lock và snapshot, tái hiện lost update, non-repeatable read, phantom, write skew và deadlock, rồi xác nhận cách khắc phục. PostgreSQL là môi trường lab chính; phần cuối so sánh SQL Server, Oracle, MySQL/MariaDB và SQLite.

## 1. Vì sao cần nhiều kết nối độc lập?

Một connection thường có session state riêng: transaction đang mở, isolation level, lock đang giữ, temporary table, setting, câu lệnh đang chạy hoặc đang chờ.

Nếu hai thao tác dùng cùng một connection, chúng không đại diện cho hai transaction độc lập. Một bài kiểm thử concurrency tối thiểu cần:

1. Connection A và connection B được mở độc lập tới cùng database.
2. Mỗi connection tự bắt đầu transaction.
3. Test điều khiển câu lệnh nào chạy trước, câu lệnh nào phải chờ.
4. Test quan sát dữ liệu giữa các bước.
5. Mỗi transaction commit hoặc rollback theo lịch.
6. Test kiểm tra kết quả cuối, SQLSTATE/vendor code và lock wait nếu có.

```text
Test runner
  |
  +---- Connection A ---- Transaction A ---- SQL steps A
  |
  +---- Connection B ---- Transaction B ---- SQL steps B
  |
  +---- Assertions: visibility, waits, errors, final state
```

**Nhiều thread không đồng nghĩa nhiều database connection.** Hãy kiểm tra driver/pool thực sự cấp hai connection vật lý khác nhau, không tái sử dụng cùng một connection hoặc transaction context.

## 2. Lịch thực thi (schedule) là gì?

Một schedule mô tả thứ tự thao tác của nhiều transaction. Ví dụ:

```text
A1: BEGIN
A2: SELECT balance
B1: BEGIN
B2: SELECT balance
A3: UPDATE balance
A4: COMMIT
B3: UPDATE balance
B4: COMMIT
```

Ký hiệu thường dùng:

- `rA(x)`: transaction A đọc dữ liệu x.
- `wA(x)`: transaction A ghi dữ liệu x.
- `cA`: A commit.
- `aA`: A abort/rollback.

Schedule giúp trả lời: B đọc trước hay sau khi A commit? B giữ snapshot nào? Khi B update, nó có chờ lock không? Kết quả nào được phép theo isolation level?

Lịch tuần tự thực hiện trọn A rồi mới B. Lịch xen kẽ cho phép A và B tiến triển đan xen. DBMS có thể cho phép lịch xen kẽ nhưng vẫn bảo đảm isolation. **Không phải mọi lịch xen kẽ đều sai.**

## 3. Chuẩn bị môi trường lab PostgreSQL

Các ví dụ dùng schema riêng `sql423`. Chỉ chạy trong database học tập hoặc database test do bạn kiểm soát.

```sql
CREATE SCHEMA sql423;

CREATE TABLE sql423.accounts (
    account_id INTEGER PRIMARY KEY,
    balance NUMERIC(12,2) NOT NULL CHECK (balance >= 0),
    version INTEGER NOT NULL DEFAULT 0
);

INSERT INTO sql423.accounts(account_id, balance)
VALUES (1, 100.00), (2, 100.00);

CREATE TABLE sql423.doctors (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO sql423.doctors(doctor_id, doctor_name, on_call)
VALUES
    (1, 'An', TRUE),
    (2, 'Binh', TRUE);

CREATE TABLE sql423.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY'
        CHECK (status IN ('READY', 'RUNNING', 'DONE')),
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ
);

INSERT INTO sql423.jobs(payload)
VALUES ('job-A'), ('job-B'), ('job-C');

CREATE TABLE sql423.orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL
);

INSERT INTO sql423.orders(order_id, status, amount)
VALUES (1, 'PENDING', 50), (2, 'PAID', 80);
```

Mục đích:

- `accounts`: lost update, atomic update, optimistic locking và deadlock.
- `doctors`: write skew với invariant nhiều hàng.
- `jobs`: queue worker, `FOR UPDATE` và `SKIP LOCKED`.
- `orders`: phantom read.

Reset dữ liệu giữa các lượt thử:

```sql
UPDATE sql423.accounts
SET balance = 100.00, version = 0;

UPDATE sql423.doctors
SET on_call = TRUE;

UPDATE sql423.jobs
SET status = 'READY',
    claimed_by = NULL,
    claimed_at = NULL;

DELETE FROM sql423.orders WHERE order_id = 3;
```

Không reset fixture khi scenario còn transaction mở. Kết thúc/rollback tất cả session trước rồi mới chuẩn bị dữ liệu cho test kế tiếp.

## 4. Mở hai session thực sự độc lập

Mở hai cửa sổ terminal/SQL client, mỗi cửa sổ tạo một kết nối riêng tới cùng database:

- Session A: connection A.
- Session B: connection B.

Trong mỗi session, xác nhận danh tính:

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('transaction_isolation') AS isolation_level;
```

Hai giá trị `backend_pid` phải khác nhau. Nếu giống nhau, bạn chưa kiểm tra hai backend độc lập.

Trong test tự động, tạo hai connection bằng hai lần gọi connect riêng. Không truyền một connection object cho hai thread. Nếu dùng connection pool, kiểm tra pool không trả cùng connection đang được giữ bởi worker khác.

### 4.1. Autocommit và transaction tường minh

Autocommit thường khiến mỗi statement độc lập được commit ngay sau khi chạy. Điều đó không phù hợp khi cần tạo schedule gồm nhiều bước trong một transaction.

```sql
BEGIN;
-- Các thao tác của transaction
COMMIT;
```

Hoặc kết thúc bằng `ROLLBACK`. Kiểm tra cấu hình driver: một số thư viện mặc định bật autocommit, một số tự mở transaction ngay khi chạy câu SELECT đầu tiên. Test cần biết chính xác lúc transaction bắt đầu và kết thúc.

## 5. Điều khiển thứ tự thực thi

Có ba cách thường dùng.

**Điều khiển thủ công:** mở hai session, chạy câu lệnh đã đánh số, chờ session kia hoàn thành hoặc xác nhận đang chờ lock. Cách này dễ quan sát và phù hợp học tập, debug.

**Barrier, latch hoặc event trong test runner:** tất cả worker phải tới một điểm rồi mới đi tiếp; hoặc một worker báo đã tới bước để controller cho worker khác chạy. Đây là cách phù hợp để tự động hóa schedule.

Ví dụ logic:

```text
Worker A: đọc số dư -> báo A_READ -> chờ ALLOW_A_WRITE
Worker B: đọc số dư -> báo B_READ -> chờ ALLOW_B_WRITE
Controller: đợi A_READ và B_READ
Controller: cho A ghi và commit
Controller: xác nhận A_COMMITTED
Controller: cho B ghi và commit
Controller: đọc kết quả cuối
```

**Dùng lock làm điểm đồng bộ:** một session cố ý chờ row lock của session khác; sau khi quan sát trạng thái chờ, test runner cho session giữ lock commit/rollback. Cách này kiểm tra lock thật của DBMS, nhưng cần timeout để test không treo.

### 5.1. Vì sao không dùng sleep làm barrier?

```sql
SELECT pg_sleep(2);
```

Có thể hữu ích để minh họa lock wait, nhưng không phải barrier đáng tin cậy. Máy CI, scheduler và database load thay đổi; sleep không xác nhận worker kia đã hoàn thành bước. Dùng barrier/event để xác nhận đúng điểm đồng bộ. Chỉ dùng sleep khi mục tiêu test thực sự liên quan thời gian chờ hoặc timeout.

## 6. Đọc và đặt isolation level

PostgreSQL:

```sql
SHOW transaction_isolation;
SELECT current_setting('transaction_isolation');
```

Đặt isolation khi bắt đầu transaction:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
-- Hoặc:
BEGIN ISOLATION LEVEL REPEATABLE READ;
-- Hoặc:
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

Đặt isolation đúng thời điểm, trước khi transaction thực hiện thao tác không cho phép thay đổi mức cô lập.

Các mức chuẩn thường gặp:

| Mức | Ý nghĩa khái quát |
| --- | --- |
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit ở DBMS hỗ trợ dirty read |
| READ COMMITTED | Chỉ đọc dữ liệu đã commit tại snapshot/statement phù hợp |
| REPEATABLE READ | Các lần đọc lặp lại ổn định theo semantics DBMS |
| SERIALIZABLE | Kết quả tương đương một thứ tự tuần tự hợp lệ; có thể phải abort/retry |

Tên isolation giống nhau không bảo đảm implementation giống nhau. PostgreSQL, SQL Server, Oracle và InnoDB có cơ chế snapshot/locking khác nhau.

## 7. Ví dụ — Lost update do ghi giá trị cũ

Giả sử tài khoản có số dư 100. Hai request muốn rút 10 và 20. Ứng dụng ngây thơ đọc balance, tính balance mới trong application, rồi ghi lại con số tuyệt đối. Cả hai có thể đọc 100 trước khi ai ghi.

Đặt lại:

```sql
UPDATE sql423.accounts
SET balance = 100.00
WHERE account_id = 1;
```

**Session A:**

```sql
BEGIN;
SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
-- 100.00
```

**Session B:**

```sql
BEGIN;
SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
-- 100.00
```

Cho A ghi trước:

```sql
UPDATE sql423.accounts
SET balance = 90.00
WHERE account_id = 1;
COMMIT;
```

Sau đó B ghi giá trị đã tính từ số dư cũ:

```sql
UPDATE sql423.accounts
SET balance = 80.00
WHERE account_id = 1;
COMMIT;
```

Kiểm tra:

```sql
SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
```

Kết quả là 80.00. Nếu hai lần rút đều hợp lệ, số dư đúng phải là 70.00. Cập nhật của A bị ghi đè bởi giá trị cũ mà B tính trước đó. Đây là lost update ở tầng ứng dụng: B chỉ gửi giá trị tuyệt đối sau khi A đã commit.

### 7.1. Cách sửa: atomic update

Đưa phép tính vào chính câu UPDATE:

```sql
UPDATE sql423.accounts
SET balance = balance - 10.00
WHERE account_id = 1
  AND balance >= 10.00;
```

Session còn lại:

```sql
UPDATE sql423.accounts
SET balance = balance - 20.00
WHERE account_id = 1
  AND balance >= 20.00;
```

PostgreSQL khóa hàng khi cập nhật. Nếu hai update cạnh tranh, một lệnh chờ; sau đó điều kiện được kiểm tra lại theo semantics READ COMMITTED. Hai phép trừ được áp dụng tuần tự trên giá trị hiện hành. Kết quả là 70.00.

Kiểm tra số hàng bị ảnh hưởng hoặc dùng RETURNING:

```sql
UPDATE sql423.accounts
SET balance = balance - 20.00
WHERE account_id = 1
  AND balance >= 20.00
RETURNING balance;
```

Không có hàng trả về nghĩa là tài khoản không tồn tại hoặc điều kiện nghiệp vụ không còn đúng; phân biệt hai trường hợp theo yêu cầu sản phẩm.

### 7.2. Cách sửa: SELECT FOR UPDATE

Nếu logic cần đọc nhiều trường rồi mới quyết định, khóa hàng trước khi đọc:

```sql
BEGIN;

SELECT balance
FROM sql423.accounts
WHERE account_id = 1
FOR UPDATE;

-- Tính toán và cập nhật trong cùng transaction.

COMMIT;
```

Transaction thứ hai khi chạy SELECT FOR UPDATE trên cùng hàng sẽ chờ. Sau khi A kết thúc, B tiếp tục và đọc phiên bản hàng phù hợp theo semantics DBMS/isolation level.

### 7.3. Cách sửa: optimistic locking bằng version

```sql
UPDATE sql423.accounts
SET balance = 80.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0
RETURNING balance, version;
```

Nếu transaction khác đã cập nhật version từ 0 lên 1, lệnh cũ không cập nhật hàng nào. Ứng dụng nhận biết conflict và đọc lại/tính lại hoặc báo người dùng. Optimistic locking phù hợp khi xung đột hiếm; vẫn cần transaction ngắn và xử lý retry.

## 8. Ví dụ — Dirty read

Dirty read xảy ra khi transaction đọc dữ liệu mà transaction ghi chưa commit. Nếu transaction ghi rollback, transaction đọc đã nhìn thấy giá trị chưa từng trở thành dữ liệu commit.

Lịch khái niệm:

```text
A: BEGIN
A: UPDATE balance = 50
B: BEGIN
B: SELECT balance -> 50 (chưa commit)
A: ROLLBACK
B: đã sử dụng giá trị 50 không tồn tại trong dữ liệu commit
```

Trong PostgreSQL, đặt READ UNCOMMITTED vẫn có semantics tương đương READ COMMITTED; dirty read không xảy ra.

**Session A:**

```sql
BEGIN;
UPDATE sql423.accounts
SET balance = 50
WHERE account_id = 1;
-- Chưa commit
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
-- Đọc giá trị đã commit trước đó, không thấy 50 chưa commit
COMMIT;
```

**Session A:**

```sql
ROLLBACK;
```

Đây là test xác nhận PostgreSQL không cho dirty read. SQL Server READ UNCOMMITTED/NOLOCK và một số cấu hình MySQL có thể khác. Oracle không cung cấp READ UNCOMMITTED như isolation level thông thường.

## 9. Ví dụ — Non-repeatable read

Non-repeatable read xảy ra khi cùng transaction đọc cùng hàng hai lần và thấy giá trị đã commit khác nhau.

**Session A — READ COMMITTED:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
-- Giả sử 100
```

**Session B:**

```sql
BEGIN;
UPDATE sql423.accounts
SET balance = 125
WHERE account_id = 1;
COMMIT;
```

**Session A:**

```sql
SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
-- Có thể thấy 125 trong PostgreSQL READ COMMITTED
COMMIT;
```

Trong PostgreSQL READ COMMITTED, mỗi statement có snapshot mới. Vì vậy SELECT thứ hai có thể nhìn thấy thay đổi B đã commit.

### 9.1. Thử REPEATABLE READ

Reset balance, chạy lại lịch nhưng A bắt đầu:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM sql423.accounts
WHERE account_id = 1;
```

B update và commit như trên. Khi A đọc lần hai, PostgreSQL REPEATABLE READ vẫn nhìn thấy giá trị theo snapshot transaction của A. Điều này không có nghĩa mọi transaction REPEATABLE READ đều an toàn trước mọi anomaly; write skew được minh họa ở phần sau.

## 10. Ví dụ — Phantom read

Phantom là trường hợp truy vấn điều kiện được thực hiện lại và tập hàng thỏa điều kiện thay đổi do transaction khác insert/delete/update.

**Session A — READ COMMITTED:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT count(*)
FROM sql423.orders
WHERE status = 'PENDING';
-- 1
```

**Session B:**

```sql
BEGIN;
INSERT INTO sql423.orders(order_id, status, amount)
VALUES (3, 'PENDING', 75);
COMMIT;
```

**Session A:**

```sql
SELECT count(*)
FROM sql423.orders
WHERE status = 'PENDING';
-- 2 trong PostgreSQL READ COMMITTED
COMMIT;
```

Hàng mới phù hợp điều kiện xuất hiện trong kết quả lần hai. PostgreSQL REPEATABLE READ giữ snapshot transaction ổn định; SERIALIZABLE bổ sung kiểm soát anomaly để đảm bảo serializable execution. DBMS dùng range lock, gap lock hoặc snapshot có thể thể hiện phantom khác nhau.

## 11. Ví dụ — Write skew: mỗi transaction sửa hàng khác nhau

Quy tắc nghiệp vụ: **luôn phải có ít nhất một bác sĩ đang trực**. Ban đầu hai bác sĩ đều trực. Hai transaction cùng đọc số người trực là 2; A cho bác sĩ 1 nghỉ, B cho bác sĩ 2 nghỉ. Mỗi transaction cập nhật một hàng khác nhau nên không có write-write conflict trực tiếp.

Reset:

```sql
UPDATE sql423.doctors SET on_call = TRUE;
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM sql423.doctors WHERE on_call = TRUE;
-- 2
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM sql423.doctors WHERE on_call = TRUE;
-- 2
```

Sau khi cả hai đã đọc:

**Session A:**

```sql
UPDATE sql423.doctors
SET on_call = FALSE
WHERE doctor_id = 1;
COMMIT;
```

**Session B:**

```sql
UPDATE sql423.doctors
SET on_call = FALSE
WHERE doctor_id = 2;
COMMIT;
```

Trong PostgreSQL REPEATABLE READ (snapshot isolation), hai transaction có thể cùng commit vì ghi trên hai hàng khác nhau. Kết quả là không còn ai trực:

```sql
SELECT count(*) FROM sql423.doctors WHERE on_call = TRUE;
-- 0: invariant bị vi phạm
```

### 11.1. Thử SERIALIZABLE

Reset hai bác sĩ trực rồi chạy lại lịch với cả A và B ở SERIALIZABLE. PostgreSQL Serializable Snapshot Isolation (SSI) phát hiện chu trình phụ thuộc không tuần tự hóa được và có thể abort một transaction, thường với SQLSTATE `40001` (serialization failure).

Không dựa vào transaction nào bị abort. Ứng dụng cần retry toàn bộ transaction từ đầu khi gặp lỗi serialization, với giới hạn retry và backoff hợp lý.

## 12. Bảo vệ invariant nhiều hàng

Khi quy tắc nghiệp vụ liên quan nhiều hàng, chỉ khóa hàng đang sửa có thể chưa đủ. Các lựa chọn:

1. **SERIALIZABLE + retry:** phù hợp khi có thể chạy lại transaction và DBMS hỗ trợ semantics serializable.
2. **Khóa hàng cha/guard row:** mọi transaction liên quan cùng khóa một hàng đại diện trước khi đọc invariant.
3. **Advisory lock:** khóa logic do ứng dụng định nghĩa, nếu mọi đường ghi tuân thủ giao thức.
4. **Mô hình dữ liệu lại:** đưa invariant về một hàng/cột có thể bảo vệ bằng CHECK/UNIQUE/FK.
5. **Constraint chuyên dụng:** dùng exclusion/unique constraint nếu quy tắc có thể biểu diễn.

Ví dụ khóa guard row:

```sql
BEGIN;

SELECT 1
FROM sql423.schedule_guard
WHERE guard_id = 1
FOR UPDATE;

-- Sau khi lấy lock, kiểm tra số người trực
-- rồi mới cập nhật trạng thái.

COMMIT;
```

## 13. Ví dụ — Deadlock

Deadlock xảy ra khi hai transaction giữ lock mà transaction kia cần, tạo thành vòng chờ. Dùng hai hàng account 1 và 2.

**Session A:**

```sql
BEGIN;
UPDATE sql423.accounts
SET balance = balance - 1
WHERE account_id = 1;
-- A giữ lock hàng 1
```

**Session B:**

```sql
BEGIN;
UPDATE sql423.accounts
SET balance = balance - 1
WHERE account_id = 2;
-- B giữ lock hàng 2
```

**Session A:**

```sql
UPDATE sql423.accounts
SET balance = balance - 1
WHERE account_id = 2;
-- A chờ lock của B
```

Khi A đang chờ, chạy ở Session B:

```sql
UPDATE sql423.accounts
SET balance = balance - 1
WHERE account_id = 1;
-- B cần lock A đang giữ: tạo chu trình deadlock
```

PostgreSQL phát hiện deadlock và hủy một transaction làm nạn nhân, thường báo SQLSTATE `40P01` (`deadlock_detected`). Transaction còn lại có thể tiếp tục sau khi lock được giải phóng.

**Không giả định A hay B luôn là nạn nhân.** Deadlock victim phụ thuộc thời điểm phát hiện và trạng thái hệ thống. Test nên chấp nhận một trong hai transaction bị abort, nhưng phải xác nhận transaction còn lại hoàn tất đúng và dữ liệu cuối hợp lệ.

## 14. Giảm deadlock bằng thứ tự lock nhất quán

Một cách giảm deadlock phổ biến là mọi transaction khóa các hàng theo cùng một thứ tự, ví dụ tăng dần account_id.

Nếu chuyển tiền giữa hai tài khoản:

```sql
BEGIN;

SELECT account_id, balance
FROM sql423.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Kiểm tra số dư, cập nhật hai tài khoản trong transaction.

COMMIT;
```

Cả hai transaction chuyển 1 → 2 và 2 → 1 đều khóa account 1 trước account 2. Điều này giảm khả năng tạo chu trình chờ do thứ tự đảo ngược.

Các nguyên tắc khác:

- Giữ transaction ngắn.
- Không chờ người dùng hoặc gọi mạng khi đang giữ lock.
- Cập nhật đúng phạm vi hàng.
- Bắt lỗi deadlock và retry toàn bộ transaction nếu thao tác có thể retry.
- Đặt timeout hợp lý.
- Giữ thứ tự truy cập bảng/hàng nhất quán trong mọi code path.

Không thể bảo đảm không có deadlock chỉ bằng cách thêm timeout. Timeout giới hạn thời gian chờ; thiết kế thứ tự lock mới giảm nguyên nhân.

## 15. Lock wait, NOWAIT và SKIP LOCKED

Một session khóa hàng:

**Session A:**

```sql
BEGIN;

SELECT *
FROM sql423.jobs
WHERE job_id = 1
FOR UPDATE;
```

**Session B:**

```sql
BEGIN;

SELECT *
FROM sql423.jobs
WHERE job_id = 1
FOR UPDATE NOWAIT;
```

Trong PostgreSQL, B không chờ; nếu hàng đang bị khóa không tương thích, câu lệnh lỗi với SQLSTATE `55P03` (`lock_not_available`). Kết thúc/rollback transaction B theo trạng thái lỗi rồi tiếp tục.

Với `SKIP LOCKED`:

```sql
SELECT *
FROM sql423.jobs
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Nếu job đầu tiên đang bị worker khác khóa, session hiện tại bỏ qua nó và có thể lấy job READY tiếp theo.

`SKIP LOCKED` phù hợp cho queue worker, nhưng kết quả **không phải snapshot đầy đủ và nhất quán của mọi hàng**. Nó cố ý bỏ qua hàng đang khóa; không dùng cho báo cáo cần thấy tất cả bản ghi.

## 16. Kiểm thử queue worker bằng nhiều connection

Một mẫu claim job trong PostgreSQL:

```sql
BEGIN;

WITH next_job AS (
    SELECT job_id
    FROM sql423.jobs
    WHERE status = 'READY'
    ORDER BY job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE sql423.jobs AS j
SET status = 'RUNNING',
    claimed_by = 'worker-A',
    claimed_at = clock_timestamp()
FROM next_job AS n
WHERE j.job_id = n.job_id
RETURNING j.*;

COMMIT;
```

Hai worker chạy cùng câu lệnh qua hai connection riêng:

- Worker A khóa và claim một job.
- Worker B bỏ qua job A đang khóa và claim job khác.
- Sau commit, mỗi job chỉ có một worker claim trong cùng thời điểm theo transaction protocol này.

Để kiểm thử, xác nhận hai connection có backend PID khác nhau; hai worker cùng chạy claim trong lịch đồng bộ; không có cùng job_id được trả về cho cả hai; trạng thái RUNNING và claimed_by đúng worker; có lease/recovery nếu worker chết sau claim.

`SKIP LOCKED` không tự giải quyết job retry, lease expiry hay exactly-once side effect. Nó chỉ giúp worker không chờ hàng đang bị khóa.

## 17. Kiểm thử optimistic locking bằng version

Dùng cột version trong bảng account. Hai client cùng đọc:

```sql
SELECT balance, version
FROM sql423.accounts
WHERE account_id = 1;
-- Ví dụ: 100.00, version 0
```

Cả hai cùng tính giá trị mới nhưng chỉ một cập nhật được version cũ:

```sql
UPDATE sql423.accounts
SET balance = 90.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0
RETURNING balance, version;
```

Transaction còn lại thử cập nhật với version 0:

```sql
UPDATE sql423.accounts
SET balance = 80.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0
RETURNING balance, version;
```

Lần thứ hai trả 0 hàng vì version hiện tại đã thay đổi. Ứng dụng phải coi đây là conflict, đọc lại và quyết định retry hoặc trả lỗi xung đột.

Không coi “UPDATE chạy không lỗi” là thành công; cần kiểm tra row count/RETURNING.

## 18. Kiểm thử lock timeout

Đặt giới hạn chờ lock để test không bị treo:

```sql
SET lock_timeout = '2s';
SET statement_timeout = '5s';
```

`lock_timeout` giới hạn thời gian chờ lock; `statement_timeout` giới hạn tổng thời gian statement. Chúng có mục đích khác nhau.

Trong PostgreSQL, lock timeout thường phát sinh SQLSTATE `55P03`; statement timeout thường là `57014` (`query_canceled`). Test cần phân biệt lỗi mong đợi với lỗi không mong đợi.

Đặt timeout ở session test riêng. Không copy setting tùy tiện vào production connection pool mà không hiểu tác động.

## 19. Quan sát session đang chờ trong PostgreSQL

Xem hoạt động của các backend:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Các trường hữu ích:

- `pid`: backend process ID.
- `state`: active, idle, idle in transaction...
- `wait_event_type`: loại sự kiện đang chờ, ví dụ Lock.
- `wait_event`: chi tiết sự kiện.
- `pg_blocking_pids(pid)`: PID đang chặn backend.
- `query`: câu lệnh hiện tại hoặc gần nhất tùy state.

Để xem lock:

```sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation_name,
    mode,
    granted
FROM pg_locks
WHERE pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE datname = current_database()
)
ORDER BY pid, granted, locktype;
```

`granted = false` thường cho biết lock đang chờ. `pg_locks` có nhiều loại lock không gắn relation; cột relation có thể NULL.

Không kết luận mọi lock đều là vấn đề. PostgreSQL dùng nhiều lock nội bộ bình thường. Hãy ghép PID, query, wait event và blocking PID để tìm đúng chuỗi chặn.

## 20. Ghi nhận thứ tự và thời điểm trong log

Khi debug concurrency, log chỉ có timestamp ứng dụng đôi khi chưa đủ. Ghi tối thiểu:

- Test case ID / run ID.
- Connection label (A/B/worker-1).
- Backend PID hoặc session ID.
- Transaction begin/commit/rollback.
- Tên bước trong schedule.
- Thời điểm bắt đầu/kết thúc statement.
- SQLSTATE/vendor error code.
- Số hàng đọc/ghi và version nếu có.

Không ghi giá trị nhạy cảm hoặc toàn bộ dữ liệu tài khoản vào log chỉ để debug. Có thể log account ID test, transaction ID và trạng thái.

Trong PostgreSQL, `application_name` giúp phân biệt session:

```sql
SET application_name = 'sql423-session-A';
SHOW application_name;
```

Session B đặt tên khác. Khi xem `pg_stat_activity`, test runner dễ nhận diện backend hơn.

## 21. Kiểm thử bằng hai terminal: runbook có thể lặp lại

Một scenario thủ công nên ghi thành quy trình:

1. Reset dữ liệu khi không còn transaction cũ.
2. Mở session A/B, ghi PID và isolation level.
3. Đặt lock/statement timeout.
4. Chạy bước A1.
5. Chạy bước B1.
6. Chạy bước A2 và ghi rõ nếu đang chờ.
7. Chạy bước B2 để tạo điều kiện giải phóng/chặn.
8. Commit/rollback theo lịch.
9. Query kết quả cuối từ connection thứ ba hoặc sau khi mọi transaction kết thúc.
10. Ghi kết quả mong đợi, kết quả thực tế và lỗi.

Không dùng cùng một script tuần tự duy nhất để giả lập hai transaction nếu script không giữ hai session mở đồng thời.

## 22. Tự động hóa bằng hai connection và barrier

Test runner có thể mở hai connection riêng và dùng barrier/event để điều khiển. Ví dụ Python với driver psycopg 3:

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import psycopg

DSN = "dbname=testdb user=test_user host=localhost"
both_have_read = Barrier(2)

def stale_withdraw(amount):
    # Mỗi lần gọi tạo connection vật lý độc lập.
    with psycopg.connect(DSN) as conn:
        with conn.transaction():
            old_balance = conn.execute(
                """
                SELECT balance
                FROM sql423.accounts
                WHERE account_id = 1
                """
            ).fetchone()[0]

            # Chỉ cho phép ghi sau khi cả hai đã đọc.
            both_have_read.wait(timeout=5)

            conn.execute(
                """
                UPDATE sql423.accounts
                SET balance = %s
                WHERE account_id = 1
                """,
                (old_balance - amount,)
            )

with ThreadPoolExecutor(max_workers=2) as pool:
    f1 = pool.submit(stale_withdraw, 10)
    f2 = pool.submit(stale_withdraw, 20)
    f1.result(timeout=10)
    f2.result(timeout=10)
```

Sau khi reset balance về 100, hai worker đều đọc cùng số dư cũ rồi mới ghi. Kết quả cuối sẽ là một trong các giá trị stale 90 hoặc 80 tùy thứ tự update, chứ không phải kết quả cộng dồn 70.

Đây là ví dụ minh họa barrier. Test production cần xử lý timeout, broken barrier, exception của worker và rollback rõ ràng. Dùng fixture riêng cho từng test để không có test khác đồng thời sửa cùng dữ liệu.

### 22.1. Test atomic update

Thay phần SELECT/tính/ghi bằng một statement:

```python
conn.execute(
    """
    UPDATE sql423.accounts
    SET balance = balance - %s
    WHERE account_id = 1
      AND balance >= %s
    """,
    (amount, amount)
)
```

Khi cả hai transaction cùng chạy, database tuần tự hóa cập nhật trên hàng. Test kiểm tra tổng số tiền bị trừ, row count và CHECK constraint. Nếu một lần rút không còn đủ số dư, không có hàng cập nhật.

## 23. Test runner phải assert điều gì?

Một test concurrency tốt không chỉ assert kết quả cuối:

| Loại assertion | Ví dụ |
| --- | --- |
| Danh tính connection | PID A khác PID B |
| Isolation | Session đang ở READ COMMITTED hay SERIALIZABLE |
| Visibility | A có thấy dữ liệu B chưa commit không? |
| Lock wait | B có chờ A không? |
| Ordering | B chỉ chạy sau tín hiệu A đã tới bước |
| Row count | UPDATE có cập nhật đúng một hàng? |
| Error code | Có 40001, 40P01 hoặc lock timeout như dự kiến? |
| Final invariant | Số dư không âm, luôn có bác sĩ trực |
| Idempotency | Job không bị claim hai lần |
| Retry | Retry toàn bộ transaction có tạo side effect trùng không? |

Ghi rõ assertion nào bắt buộc và assertion nào phụ thuộc DBMS/version. Không yêu cầu một kết quả duy nhất khi thứ tự nạn nhân deadlock vốn không được bảo đảm.

## 24. Retry transaction: lỗi nào cần thử lại?

Các lỗi concurrency thường gặp trong PostgreSQL:

| SQLSTATE | Ý nghĩa | Cách xử lý thường gặp |
| --- | --- | --- |
| `40001` | Serialization failure | Rollback và retry toàn bộ transaction |
| `40P01` | Deadlock detected | Rollback; có thể retry transaction |
| `55P03` | Lock not available | Xử lý NOWAIT/lock timeout theo chính sách |
| `57014` | Query canceled/statement timeout | Xem nguyên nhân; không retry mù quáng |

Retry phải chạy **toàn bộ transaction từ đầu**, vì các lần đọc và quyết định cũ có thể không còn đúng. Không chỉ chạy lại statement cuối.

Retry cần giới hạn số lần, backoff có jitter khi phù hợp, chỉ retry lỗi được xác định là tạm thời, không lặp side effect ngoài database vô điều kiện, và dùng idempotency key/outbox nếu transaction còn gửi message, thanh toán hoặc gọi dịch vụ ngoài.

## 25. Side effect bên ngoài và transaction retry

Giả sử transaction cập nhật đơn hàng rồi gửi email ngay trước commit. Nếu commit thất bại vì serialization, retry transaction có thể gửi email hai lần.

Không đặt side effect không idempotent bên trong transaction retry tùy tiện. Pattern thường dùng là **transactional outbox**:

1. Trong transaction, cập nhật nghiệp vụ và insert một outbox event.
2. Commit.
3. Worker riêng đọc outbox và gửi message.
4. Worker đánh dấu đã xử lý bằng khóa/idempotency.
5. Retry gửi message phải được xử lý idempotent ở consumer hoặc nhà cung cấp.
## 26. Tạo guard row để tuần tự hóa invariant

Ví dụ ở mục 12 dùng bảng `schedule_guard` làm hàng khóa đại diện. Tạo bảng và hàng guard trước khi chạy scenario:

```sql
CREATE TABLE sql423.schedule_guard (
    guard_id INTEGER PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO sql423.schedule_guard(guard_id, description)
VALUES (1, 'On-call roster invariant');
```

Mọi transaction có thể thay đổi lịch trực phải khóa cùng hàng guard trước khi đếm và cập nhật:

```sql
BEGIN;

SELECT guard_id
FROM sql423.schedule_guard
WHERE guard_id = 1
FOR UPDATE;

SELECT count(*)
FROM sql423.doctors
WHERE on_call = TRUE;

-- Chỉ cập nhật nếu invariant vẫn đúng.

COMMIT;
```

Transaction thứ hai phải chờ lock guard; sau khi transaction đầu commit, nó mới kiểm tra invariant trên dữ liệu mới. Cơ chế này chỉ đúng nếu mọi đường ghi đều tuân thủ cùng giao thức. Nên cân nhắc SERIALIZABLE hoặc constraint nếu phù hợp hơn với mô hình.

## 27. SQL Server: locking, RCSI và SNAPSHOT

SQL Server có những khác biệt đáng chú ý:

- READ COMMITTED mặc định có thể dùng locking read hoặc row-versioning tùy database option.
- READ_COMMITTED_SNAPSHOT (RCSI) làm READ COMMITTED đọc version theo statement thay vì giữ shared lock theo cách truyền thống.
- SNAPSHOT isolation cần bật ALLOW_SNAPSHOT_ISOLATION.
- SERIALIZABLE sử dụng key-range lock để bảo vệ phạm vi truy vấn trong trường hợp phù hợp.
- READ UNCOMMITTED/NOLOCK có thể đọc dữ liệu chưa commit và có thể quan sát dữ liệu không nhất quán.

Kiểm tra database option:

```sql
SELECT
    name,
    is_read_committed_snapshot_on,
    snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
```

Đặt isolation:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRANSACTION;

SELECT *
FROM dbo.Orders
WHERE Status = 'PENDING';

COMMIT TRANSACTION;
```

Không giả định READ COMMITTED trên SQL Server có cùng lock/snapshot behavior với PostgreSQL READ COMMITTED. Ghi lại database option và isolation thực tế trong test report.

## 28. SQL Server: kiểm tra lock và deadlock

DMV hữu ích:

```sql
SELECT
    session_id,
    status,
    command,
    wait_type,
    wait_time,
    blocking_session_id
FROM sys.dm_exec_requests
WHERE database_id = DB_ID();
```

Xem lock:

```sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status
FROM sys.dm_tran_locks;
```

Deadlock victim thường nhận error 1205. SQL Server có thể ghi deadlock graph qua Extended Events/system_health tùy cấu hình. Lưu graph để xác định resource và thứ tự lock; không chỉ tăng timeout mà bỏ qua nguyên nhân.

Nếu dùng RCSI/SNAPSHOT, cần kiểm tra version store và tác động tới workload. Snapshot không miễn phí về storage/cleanup.

## 29. Oracle: read consistency và transaction isolation

Oracle mặc định READ COMMITTED với read consistency ở mức statement: một câu SELECT nhìn dữ liệu nhất quán tại thời điểm statement bắt đầu. Các câu SELECT khác trong cùng transaction có thể thấy commit mới hơn.

Oracle SERIALIZABLE cung cấp transaction-level consistency; transaction có thể gặp lỗi `ORA-08177` khi không thể serialize do thay đổi cạnh tranh.

Oracle không cung cấp READ UNCOMMITTED như isolation level tiêu chuẩn. Đọc không khóa thông thường không chặn writer theo cùng cách nhiều hệ lock-based; Oracle dùng undo để dựng phiên bản nhất quán.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 1;

-- Các thao tác transaction tiếp theo

COMMIT;
```

Khóa hàng:

```sql
SELECT *
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

Kiểm thử cần ghi nhận ORA code, isolation, thời điểm snapshot và hành vi SELECT FOR UPDATE. Không áp nguyên kết luận từ PostgreSQL sang Oracle chỉ vì tên isolation giống nhau.

## 30. MySQL/MariaDB InnoDB: consistent read và locking read

InnoDB thường dùng REPEATABLE READ làm mặc định trong MySQL. Cần phân biệt:

- **Consistent nonlocking read:** đọc snapshot theo cơ chế MVCC.
- **Locking read:** SELECT FOR UPDATE hoặc FOR SHARE, đọc theo semantics khóa/current read.
- **Gap/next-key locks:** có thể khóa khoảng index để ngăn insert phù hợp phạm vi trong một số isolation/query plan.
- **READ COMMITTED:** snapshot mới cho từng consistent read và hành vi gap lock khác REPEATABLE READ.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM orders
WHERE status = 'PENDING';

COMMIT;
```

Locking read:

```sql
START TRANSACTION;

SELECT *
FROM orders
WHERE order_id = 10
FOR UPDATE;

COMMIT;
```

Không giả định SELECT thường và SELECT FOR UPDATE đọc cùng snapshot/semantics trong mọi trường hợp. Test phantom cần ghi rõ isolation, index, predicate và loại read.

MySQL InnoDB deadlock thường trả error 1213; lock wait timeout thường trả 1205. Ứng dụng cần rollback đúng transaction và retry theo chính sách. MariaDB có nhiều điểm tương tự nhưng phải xác nhận phiên bản, engine và cấu hình.

## 31. SQLite: concurrency khác DBMS server

SQLite thường dùng file database và có mô hình writer hạn chế: nhiều reader có thể cùng hoạt động, nhưng chỉ một writer tại một thời điểm. WAL mode cho phép reader tiếp tục đọc trong khi writer ghi theo cơ chế WAL, nhưng không biến SQLite thành hệ nhiều writer song song như PostgreSQL.

```sql
PRAGMA journal_mode = WAL;
```

Có thể bắt đầu transaction ghi sớm:

```sql
BEGIN IMMEDIATE;

UPDATE accounts
SET balance = balance - 10
WHERE account_id = 1;

COMMIT;
```

`BEGIN IMMEDIATE` yêu cầu quyền ghi sớm, giúp xác định tranh chấp writer ở đầu transaction. Nếu không lấy được lock, ứng dụng có thể nhận SQLITE_BUSY hoặc lỗi liên quan theo tình huống/timeout.

Khi test SQLite, cần dùng nhiều connection tới cùng file database, không dùng hai database in-memory độc lập rồi nghĩ chúng chia sẻ dữ liệu. Với `:memory:`, mỗi connection thường có database riêng trừ khi dùng URI/shared-cache đúng cách. Đây là lỗi setup test phổ biến.

SQLite phù hợp nhiều workload embedded, nhưng không dùng kết quả concurrency của SQLite để suy ra PostgreSQL/SQL Server sẽ xử lý lock như thế nào.

## 32. Ma trận khác biệt giữa DBMS

| Chủ đề | PostgreSQL | SQL Server | Oracle | MySQL/MariaDB InnoDB | SQLite |
| --- | --- | --- | --- | --- | --- |
| Snapshot đọc | Statement ở READ COMMITTED | Locking hoặc RCSI tùy option | Statement-level consistency | MVCC consistent read | Theo transaction/journal mode |
| Dirty read | Không; READ UNCOMMITTED như READ COMMITTED | Có READ UNCOMMITTED/NOLOCK | Không hỗ trợ thông thường | Có READ UNCOMMITTED tùy engine | Không phải mục tiêu hỗ trợ |
| Serializable | SSI, có thể abort 40001 | Range lock/locking | Serializable, có thể ORA-08177 | Locking/gap/next-key theo engine | Writer serialization và file locking |
| Deadlock code | 40P01 | 1205 | ORA-00060 | 1213 (InnoDB) | Thường SQLITE_BUSY/locked |
| Skip locked | FOR UPDATE SKIP LOCKED | READPAST trong một số queue pattern | FOR UPDATE SKIP LOCKED | SKIP LOCKED ở phiên bản hỗ trợ | Không tương đương tổng quát |
| Quan sát lock | pg_locks, pg_stat_activity | DMVs, Extended Events | V$ views/ASH tùy quyền | performance_schema | Busy timeout/log ứng dụng |

Đây là bản đồ khái niệm. Phiên bản, storage engine, database options và transaction settings có thể làm thay đổi hành vi. Khi migrate, chuyển test scenario và expected behavior, không chỉ chuyển cú pháp SQL.

## 33. Thiết kế test suite concurrency có thể lặp lại

Mỗi test case nên khai báo:

- Fixture ban đầu.
- Số connection.
- Isolation level của từng transaction.
- Schedule từng bước.
- Barrier/event tại điểm đồng bộ.
- Thời gian timeout tối đa.
- Kết quả visibility mong đợi.
- Lỗi/SQLSTATE mong đợi.
- Kết quả cuối và invariant.
- Cách reset fixture.

Ví dụ test lost update:

```text
Fixture: account 1 balance = 100
Connections: A, B
Isolation: READ COMMITTED
Schedule:
  1. A reads 100
  2. B reads 100
  3. A writes 90 and commits
  4. B writes stale 80 and commits
Assertion:
  final balance = 80 (reproduces bug)
Corrected implementation:
  atomic decrement by 10 and 20
Assertion:
  final balance = 70
```

Cố ý assert giá trị sai trong test tái hiện bug là hợp lý nếu mục tiêu là chứng minh lỗi. Sau khi sửa, regression test phải assert invariant đúng.

## 34. Cô lập dữ liệu giữa các test

Test concurrency dễ nhiễu nếu nhiều test cùng sửa một hàng. Các lựa chọn:

1. Tạo database/schema riêng cho mỗi worker test.
2. Dùng test ID để tạo account/order riêng.
3. Reset fixture sau khi chắc chắn transaction cũ đã kết thúc.
4. Dùng transaction rollback cho test đơn giản, nhưng nhớ hai connection độc lập không tự chia sẻ transaction rollback của connection cha.
5. Chạy test tuần tự nếu chúng cố ý tranh chấp cùng fixture.
6. Dọn dữ liệu trong finally/teardown để không để lock còn sót.

Không để một test kết thúc sớm nhưng connection vẫn idle in transaction. Đây là nguồn lock wait và test flaky phổ biến.

## 35. Phân biệt race condition với test sai

Khi test concurrency thất bại, xác minh:

- Có đúng hai connection backend không?
- Có thực sự hai transaction cùng tồn tại không?
- Autocommit có vô tình commit sớm không?
- Một connection có bị pool tái sử dụng không?
- Barrier có đặt đúng sau bước đọc/ghi không?
- Test có chờ đúng tín hiệu không?
- Timeout có cancel statement trước khi schedule hoàn tất không?
- Fixture có bị test khác thay đổi không?
- Expected behavior có phù hợp isolation level và DBMS/version không?

Một test không điều khiển được schedule có thể thất bại vì race condition thật hoặc chỉ vì test runner sắp xếp bước khác dự kiến. Log PID, step và barrier giúp phân biệt.

## 36. Deterministic test khác stress test

**Deterministic test** cố tình tạo schedule cụ thể để tái hiện anomaly hoặc lock conflict. Nó dễ debug và thích hợp regression.

**Stress test** chạy nhiều worker, nhiều vòng và schedule biến thiên để tìm lỗi hiếm, deadlock, throughput hoặc contention. Nó hữu ích bổ sung nhưng khó tái hiện failure nếu không ghi lại seed, schedule và log.

Quy trình tốt:

1. Dùng deterministic test để chứng minh bug.
2. Sửa logic và thêm regression test.
3. Chạy stress test với workload đại diện.
4. Ghi lại schedule/seed khi thất bại.
5. Thu nhỏ schedule để tạo test deterministic mới.

Không thay deterministic test bằng hàng nghìn vòng ngẫu nhiên mà không có cách tái hiện.

## 37. Timeout và dọn dẹp khi test bị treo

Đặt timeout ở nhiều lớp:

- Timeout chờ barrier trong test runner.
- Query/statement timeout.
- Lock timeout nếu DBMS hỗ trợ.
- Timeout tổng của test case.
- Timeout lấy connection từ pool.

Khi test timeout:

1. Ngừng phát lệnh mới.
2. Cancel statement đang chạy nếu phù hợp.
3. Rollback transaction.
4. Đóng connection.
5. Xác nhận backend không còn active/idle in transaction.
6. Thu thập log/lock snapshot trước khi reset fixture nếu cần.

Không kill session như bước đầu tiên khi chưa xác định owner. Trong môi trường chia sẻ, hủy session của người khác có thể gây mất công việc.

## 38. Kiểm thử invariant và trường hợp biên

Ngoài anomaly kinh điển, kiểm tra:

- Hai request cùng tạo một unique key.
- Hai worker cùng claim một job.
- Hai transaction chuyển tiền ngược chiều.
- Một transaction xóa hàng trong khi transaction khác update.
- Update hàng làm thay đổi predicate của transaction đang scan.
- Hạn mức tổng thể bị vượt do hai transaction đọc cùng tổng cũ.
- Retry sau deadlock có tạo giao dịch lặp không.
- Transaction rollback sau khi ghi outbox.
- Một transaction timeout giữa chừng.
- Client mất kết nối ngay sau commit và retry request.

Mỗi scenario phải nêu invariant: tổng số dư hai tài khoản không đổi, balance không âm, job chỉ có một claimant đang hoạt động, luôn có ít nhất một bác sĩ trực hoặc unique business key không trùng.

## 39. Bài tập thực hành

Các bài tập dùng schema `sql423`. Chạy từng scenario trong database học tập, mở hai session độc lập và reset dữ liệu trước khi bắt đầu.

### Bài 1 — Xác nhận connection

Mở hai session PostgreSQL và truy vấn `pg_backend_pid()`. Vì sao hai PID phải khác nhau? Nếu dùng chung connection object trong hai thread thì test có vấn đề gì?

### Bài 2 — Tái hiện lost update

Thực hiện lịch A đọc 100, B đọc 100, A ghi 90 commit, B ghi 80 commit. Kết quả cuối là bao nhiêu? Nếu hai lần rút là 10 và 20, kết quả đúng phải là bao nhiêu?

### Bài 3 — Atomic update

Viết hai câu UPDATE giảm balance 10 và 20 ngay trong SQL, mỗi câu có điều kiện balance đủ tiền. Vì sao cách này không dùng giá trị cũ tính ở application?

### Bài 4 — SELECT FOR UPDATE

Cho A khóa hàng account 1 bằng SELECT FOR UPDATE. B cũng chạy SELECT FOR UPDATE trên hàng đó. B sẽ làm gì khi A chưa kết thúc transaction? Cần quan sát gì để xác nhận?

### Bài 5 — Dirty read

Trong PostgreSQL, đặt B ở READ UNCOMMITTED, A update nhưng chưa commit. B có nhìn thấy giá trị mới chưa commit không? Vì sao?

### Bài 6 — Non-repeatable read

A READ COMMITTED đọc balance, B update và commit, A đọc lại. Kết quả có thể thay đổi không? Thử lại với REPEATABLE READ.

### Bài 7 — Phantom

A đếm số order PENDING, B insert một order PENDING và commit, A đếm lại. Hành vi dự kiến trong PostgreSQL READ COMMITTED là gì?

### Bài 8 — Write skew

Hai bác sĩ đều trực. A và B cùng đọc count = 2 ở REPEATABLE READ, sau đó mỗi người tắt trạng thái trực của một bác sĩ khác nhau. Vì sao cả hai có thể commit? Điều gì thay đổi ở SERIALIZABLE?

### Bài 9 — Deadlock

Tạo lịch A khóa account 1, B khóa account 2, A yêu cầu account 2, B yêu cầu account 1. SQLSTATE nào thường báo deadlock trong PostgreSQL? Có thể dự đoán transaction nào bị hủy không?

### Bài 10 — NOWAIT và SKIP LOCKED

A khóa job đầu tiên. B chạy SELECT FOR UPDATE NOWAIT rồi thử SKIP LOCKED. Hai chế độ khác nhau thế nào?

### Bài 11 — Queue worker

Viết câu lệnh claim một job READY bằng CTE, FOR UPDATE SKIP LOCKED, UPDATE status thành RUNNING và RETURNING job. Hai worker đồng thời có thể claim cùng job không theo protocol này?

### Bài 12 — Optimistic locking

Hai client cùng đọc version 0. Viết UPDATE có điều kiện version = 0 và tăng version. Làm sao biết client thứ hai bị conflict?

### Bài 13 — Barrier

Giải thích cách dùng barrier để bảo đảm hai worker đều đọc xong trước khi worker nào được ghi. Vì sao sleep(1) không thay thế barrier?

### Bài 14 — Retry

Khi gặp SQLSTATE 40001 hoặc 40P01, vì sao nên retry toàn bộ transaction thay vì chỉ chạy lại statement cuối? Side effect gửi email cần xử lý ra sao?

### Bài 15 — Quan sát lock

Viết query dùng pg_stat_activity và pg_blocking_pids để xác định backend đang chờ và backend đang chặn nó.

### Bài 16 — Chuyển DBMS

Nêu khác biệt cần xem lại khi chạy test phantom hoặc snapshot giữa PostgreSQL, SQL Server RCSI/SNAPSHOT, Oracle READ COMMITTED, MySQL InnoDB REPEATABLE READ và SQLite.

### Bài 17 — Test idempotency

Client gửi request chuyển tiền, database commit thành công nhưng kết nối bị mất trước khi client nhận response. Nếu client retry, thiết kế nào giúp tránh chuyển tiền hai lần?

### Bài 18 — Test fixture

Vì sao không được reset bảng accounts khi một transaction test vẫn đang mở? Nêu cách cô lập fixture để nhiều test không tranh chấp dữ liệu.

## 40. Gợi ý đáp án

**Bài 1.** Hai session độc lập phải có PID backend khác nhau. Dùng chung connection khiến transaction/session state không độc lập; driver có thể serialize lệnh hoặc không cho phép dùng đồng thời.

**Bài 2.** Kết quả cuối là 80.00 vì B ghi giá trị stale; kết quả đúng theo hai phép rút hợp lệ là 70.00.

**Bài 3.**

```sql
UPDATE sql423.accounts
SET balance = balance - 10
WHERE account_id = 1 AND balance >= 10;

UPDATE sql423.accounts
SET balance = balance - 20
WHERE account_id = 1 AND balance >= 20;
```

Database áp dụng phép trừ trên giá trị hàng hiện hành và tuần tự hóa cập nhật xung đột.

**Bài 4.** B chờ row lock đến khi A commit/rollback hoặc timeout. Quan sát PID, wait_event_type, pg_blocking_pids và lock granted trong pg_locks.

**Bài 5.** Không. PostgreSQL xử lý READ UNCOMMITTED như READ COMMITTED, nên B không thấy dữ liệu chưa commit.

**Bài 6.** READ COMMITTED có thể thấy giá trị B đã commit ở câu SELECT thứ hai. REPEATABLE READ giữ snapshot transaction nên vẫn thấy giá trị cũ.

**Bài 7.** Câu SELECT thứ hai của A có thể đếm thêm hàng mới vì mỗi statement READ COMMITTED dùng snapshot mới.

**Bài 8.** Snapshot isolation không phát hiện write-write conflict vì A và B sửa hai hàng khác nhau. SERIALIZABLE phát hiện phụ thuộc không tuần tự hóa được và có thể abort một transaction với 40001.

**Bài 9.** PostgreSQL thường trả 40P01. Không thể dự đoán A hay B là victim; phải xử lý cả hai khả năng.

**Bài 10.** NOWAIT lỗi ngay nếu hàng bị khóa; SKIP LOCKED bỏ qua hàng đang khóa và tiếp tục lấy hàng khác.

**Bài 11.**

```sql
WITH next_job AS (
    SELECT job_id
    FROM sql423.jobs
    WHERE status = 'READY'
    ORDER BY job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE sql423.jobs AS j
SET status = 'RUNNING',
    claimed_by = 'worker-A',
    claimed_at = clock_timestamp()
FROM next_job AS n
WHERE j.job_id = n.job_id
RETURNING j.*;
```

Với transaction và protocol claim đúng, hai worker không claim cùng hàng đang được khóa. Cần thêm lease/recovery nếu worker chết sau claim.

**Bài 12.** UPDATE với `WHERE version = 0` và `version = version + 1`. Nếu RETURNING không có hàng hoặc row count bằng 0, version đã đổi và client gặp conflict.

**Bài 13.** Barrier chỉ cho worker đi tiếp khi cả hai đã tới điểm đồng bộ. Sleep chỉ trì hoãn theo thời gian ước lượng, không xác nhận worker khác đã hoàn tất bước.

**Bài 14.** Kết quả đọc/điều kiện cũ có thể không còn hợp lệ; phải chạy lại từ đầu. Email/side effect nên phát qua transactional outbox và consumer idempotent.

**Bài 15.**

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database();
```

**Bài 16.** PostgreSQL READ COMMITTED snapshot theo statement, RR snapshot transaction, SSI ở SERIALIZABLE; SQL Server phụ thuộc RCSI/SNAPSHOT option và range locks; Oracle statement consistency và ORA-08177; InnoDB RR có consistent read và next-key/gap locks; SQLite chỉ một writer và mô hình locking file/WAL.

**Bài 17.** Dùng idempotency key/transaction ID duy nhất, lưu kết quả request trong cùng transaction và trả lại kết quả cũ khi retry cùng key. Không chỉ dựa vào client timeout.

**Bài 18.** Reset có thể chờ lock, thay đổi dữ liệu mà transaction khác đang đọc hoặc làm kết quả test sai. Dùng schema/database riêng, khóa fixture theo test ID hoặc tuần tự hóa test có chủ đích; chỉ teardown khi mọi connection đã commit/rollback và đóng.

## 41. Dọn dữ liệu lab

Sau khi hoàn thành, xác nhận schema `sql423` chỉ chứa đối tượng do bài học tạo. Trong database thử nghiệm, có thể xóa:

```sql
DROP SCHEMA sql423 CASCADE;
```

Lệnh xóa bảng và đối tượng phụ thuộc trong schema. Không chạy trên schema dùng chung hoặc production khi chưa kiểm tra dependency.

## 42. Kết luận

Kiểm thử giao dịch đồng thời phải dùng **nhiều connection vật lý độc lập**, mỗi connection giữ transaction và session state riêng. Một schedule được điều khiển bằng barrier, latch hoặc các bước thủ công giúp tái hiện chính xác thứ tự đọc, ghi, chờ lock, commit và rollback. Hãy xác nhận PID, isolation level, autocommit và timeout trước khi kết luận về hành vi DBMS.

Các scenario quan trọng gồm lost update, dirty read, non-repeatable read, phantom, write skew, deadlock và lock wait. Mỗi DBMS có semantics khác nhau: PostgreSQL dùng snapshot theo statement/transaction và SSI; SQL Server phụ thuộc locking, RCSI và SNAPSHOT; Oracle dùng read consistency; InnoDB kết hợp MVCC với gap/next-key locks; SQLite có mô hình một writer. Vì vậy expected result phải gắn với engine, version, isolation và cấu hình cụ thể.

Một test đáng tin cần assert **thứ tự thực thi, dữ liệu nhìn thấy, lock wait, mã lỗi, row count và invariant cuối**. Dùng constraint để bảo vệ dữ liệu, atomic update hoặc row lock để xử lý cạnh tranh, version để phát hiện stale write, SERIALIZABLE khi invariant cần tuần tự hóa và retry toàn bộ transaction khi DBMS báo lỗi có thể retry. Với side effect ngoài database, dùng idempotency và transactional outbox. **Concurrency không thể được kiểm tra chỉ bằng một kết quả cuối tình cờ; phải điều khiển và ghi lại lịch thực thi đã tạo ra kết quả đó.**
