# Kiểm thử đồng thời bằng nhiều session và lịch thực thi có kiểm soát

## 1. Mục tiêu của kiểm thử đồng thời

Kiểm thử đồng thời (concurrency testing) xác nhận nhiều transaction có thể cùng truy cập dữ liệu mà vẫn giữ đúng quy tắc nghiệp vụ. Với Oracle Database, mỗi JDBC connection thường tương ứng với một database session riêng trong mô hình dedicated server. Vì vậy, muốn kiểm tra cạnh tranh thật sự, cần dùng nhiều connection/session độc lập và chủ động điều khiển thứ tự thao tác.

Các lỗi thường cần tái hiện gồm:

- **Lost update:** transaction ghi đè thay đổi của transaction khác do cùng đọc một giá trị cũ.
- **Dirty read:** transaction đọc dữ liệu chưa commit của transaction khác. Oracle không cho dirty read theo mô hình đọc thông thường.
- **Non-repeatable read:** cùng một transaction đọc một dòng hai lần và thấy giá trị khác do transaction khác đã commit giữa hai lần đọc.
- **Write/write conflict:** nhiều transaction cùng cập nhật một dòng hoặc một tập dòng.
- **Lock wait/timeout:** transaction phải chờ dòng đang bị session khác khóa.
- **Deadlock:** các transaction chờ lẫn nhau theo một chu trình khóa.
- **Serialization conflict:** transaction chạy ở isolation `SERIALIZABLE` không thể tiếp tục vì thay đổi cạnh tranh khiến snapshot không còn tuần tự hóa được.
- **Queue race:** nhiều worker cùng cố nhận một công việc, dẫn đến xử lý trùng nếu không có cơ chế khóa/claim phù hợp.

Mục tiêu không phải chỉ tạo tải lớn. Một test concurrency có giá trị cần tái hiện được lịch thực thi (execution schedule), xác định điểm đồng bộ giữa các session, dự đoán kết quả và kiểm tra kết quả thực tế sau commit/rollback.

## 2. Session, connection và transaction trong bài test

### 2.1. Mỗi session phải là một kết nối độc lập

Hai cửa sổ SQL Developer không nhất thiết là hai session nếu chúng cùng dùng một connection. Khi kiểm thử, mở hai connection riêng hoặc hai tiến trình SQL*Plus riêng. Xác nhận session bằng:

```sql
SELECT sys_context('USERENV', 'SID') AS sid,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
```

Hai session độc lập phải có SID khác nhau trên cùng instance. Với RAC, SID có thể trùng giữa các instance; khi đó kết hợp `INST_ID` và SID để nhận diện session.

Trong Java, mỗi luồng kiểm thử cần mượn connection riêng từ pool. Không chia sẻ một JDBC `Connection`, `EntityManager` hoặc Hibernate `Session` giữa các thread. Các đối tượng này không được thiết kế để nhiều thread cùng thao tác đồng thời.

### 2.2. Phân biệt session với transaction

Một session có thể chạy nhiều transaction theo thời gian. Trong Oracle, transaction bắt đầu khi session thực hiện thao tác cần transaction và kết thúc khi `COMMIT` hoặc `ROLLBACK`. Một session `INACTIVE` có thể vẫn giữ transaction chưa commit và giữ row lock.

Khi lập lịch kiểm thử, ghi lại rõ:

- Session nào đang thực hiện thao tác.
- Transaction bắt đầu ở thời điểm nào.
- Dòng/tablespace/resource nào đang bị truy cập hoặc khóa.
- Lệnh nào tạo ra wait.
- Điểm nào commit/rollback và giải phóng lock.

Không dùng trạng thái `ACTIVE/INACTIVE` đơn lẻ để kết luận session có đang giữ lock hay không. Cần xem transaction, lock và wait event tương ứng.

## 3. Chuẩn bị môi trường kiểm thử có thể lặp lại

### 3.1. Tạo bảng test riêng

Nên dùng schema hoặc bảng dành riêng cho concurrency test, không chạy kịch bản phá dữ liệu trên bảng nghiệp vụ production.

```sql
CREATE TABLE concurrency_account (
    account_id NUMBER(10) PRIMARY KEY,
    balance    NUMBER(12, 2) NOT NULL,
    version_no NUMBER(10) DEFAULT 0 NOT NULL
);

INSERT INTO concurrency_account(account_id, balance, version_no)
VALUES (1, 1000, 0);

INSERT INTO concurrency_account(account_id, balance, version_no)
VALUES (2, 1000, 0);

COMMIT;
```

Mỗi lần chạy test, đưa fixture về trạng thái đã biết:

```sql
UPDATE concurrency_account
SET balance = 1000,
    version_no = 0
WHERE account_id IN (1, 2);

COMMIT;
```

Reset dữ liệu trước khi bắt đầu schedule, không reset giữa các bước đang cần quan sát. Nếu nhiều test chạy đồng thời, dùng account ID/test run ID riêng để tránh các test tác động lẫn nhau.

### 3.2. Ghi nhận thông tin phiên bản và môi trường

Trước khi so sánh kết quả giữa các lần chạy, ghi nhận:

```sql
SELECT banner FROM v$version ORDER BY banner;

SELECT name, value
FROM v$parameter
WHERE name IN ('compatible', 'transactions', 'processes', 'sessions');

SELECT name, open_mode, database_role
FROM v$database;
```

Đồng thời ghi lại JDBC driver, JDK, Hibernate/Spring version nếu test từ ứng dụng, isolation level, pool size, service name, RAC instance và cấu hình timeout. Những khác biệt này có thể làm thay đổi hành vi hoặc thời gian chờ.

### 3.3. Tạo log sự kiện của test

Để hiểu lịch thực thi, ghi timestamp, session, transaction step và kết quả. Một bảng log đơn giản:

```sql
CREATE TABLE concurrency_test_log (
    run_id       VARCHAR2(64) NOT NULL,
    step_name    VARCHAR2(100) NOT NULL,
    session_sid  NUMBER,
    event_time   TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL,
    details      VARCHAR2(1000)
);
```

Có thể ghi log từ test harness hoặc ứng dụng. Nếu ghi vào cùng transaction đang kiểm thử, log sẽ rollback theo transaction; điều đó đôi khi hữu ích để kiểm tra atomicity nhưng không phù hợp để giữ lại dấu vết lỗi. Với audit test cần giữ lại cả khi rollback, ghi log qua connection riêng hoặc phía test runner, nhưng phải bảo đảm cách ghi log không làm thay đổi lịch khóa đang đo.

## 4. Thiết kế lịch thực thi có kiểm soát

### 4.1. Lịch thực thi (execution schedule)

Lịch thực thi mô tả thứ tự các thao tác của từng session. Ví dụ hai session cùng đọc một account:

| Thứ tự | Session A | Session B |
|---:|---|---|
| 1 | `SELECT balance` | |
| 2 | | `SELECT balance` |
| 3 | Tính số dư mới từ giá trị đã đọc | |
| 4 | `UPDATE` và `COMMIT` | |
| 5 | | `UPDATE` bằng giá trị cũ đã đọc và `COMMIT` |
| 6 | Kiểm tra số dư cuối | Kiểm tra số dư cuối |

Nếu không xác định thứ tự này, test có thể chạy theo cách khác ở mỗi lần và không tái hiện được race condition.

### 4.2. Dùng barrier thay vì sleep cố định

Trong Java, `CountDownLatch`, `CyclicBarrier` hoặc `Phaser` giúp đồng bộ các thread tại những điểm xác định. Ví dụ:

1. A và B đều đọc xong dữ liệu.
2. Cả hai báo hiệu `readComplete`.
3. Test runner cho A cập nhật và commit.
4. Sau khi A commit, runner mới cho B tiếp tục cập nhật.
5. Kiểm tra kết quả và row count.

Không nên dùng `Thread.sleep(1000)` làm cơ chế đồng bộ chính. Sleep chỉ tạo khoảng chờ tương đối; trên máy chậm hoặc khi scheduler thay đổi, thứ tự mong muốn vẫn có thể không xảy ra. Barrier/latch xác định quan hệ xảy ra-trước rõ ràng và giúp test lặp lại.

Mọi barrier phải có timeout để test không treo vô hạn nếu một thread lỗi trước khi tới điểm đồng bộ. Khi một participant thất bại, test runner cần giải phóng các participant còn lại, rollback transaction và đóng connection.

### 4.3. Tách chuẩn bị, thực thi và xác minh

Một kịch bản có thể chia thành ba pha:

```text
PREPARE
  Reset fixture, tạo dữ liệu, xác nhận schema và session
       |
       v
EXECUTE SCHEDULE
  Chạy từng thao tác theo barrier/latch đã định nghĩa
       |
       v
VERIFY
  Chờ mọi transaction kết thúc, đọc dữ liệu cuối,
  kiểm tra row count, exception, lock và log sự kiện
```

Không đọc kết quả cuối khi transaction liên quan vẫn chưa hoàn tất. Trước khi chạy schedule tiếp theo, bảo đảm tất cả session đã commit/rollback và trả connection về pool.

## 5. Kịch bản 1: tái hiện lost update

### 5.1. Lịch thực thi

Giả sử số dư ban đầu là 1.000. A muốn trừ 100, B muốn trừ 50. Cả hai cùng đọc giá trị cũ trước khi một bên ghi:

| Bước | Session A | Session B |
|---:|---|---|
| 1 | Đọc balance = 1.000 | |
| 2 | | Đọc balance = 1.000 |
| 3 | Tính 900 | Tính 950 |
| 4 | Ghi 900, commit | |
| 5 | | Ghi 950 dựa trên giá trị cũ, commit |

Kết quả cuối là 950, trong khi nghiệp vụ mong đợi 850. Thay đổi của A đã bị B ghi đè.

### 5.2. Thao tác thủ công bằng hai session

Reset fixture trước:

```sql
UPDATE concurrency_account
SET balance = 1000, version_no = 0
WHERE account_id = 1;
COMMIT;
```

**Session A:**

```sql
SELECT balance FROM concurrency_account WHERE account_id = 1;
-- Ghi nhận 1000, chưa update.
```

**Session B:**

```sql
SELECT balance FROM concurrency_account WHERE account_id = 1;
-- Cũng đọc 1000, chưa update.
```

**Session A:**

```sql
UPDATE concurrency_account
SET balance = 900
WHERE account_id = 1;
COMMIT;
```

**Session B:**

```sql
UPDATE concurrency_account
SET balance = 950
WHERE account_id = 1;
COMMIT;
```

Kiểm tra:

```sql
SELECT balance
FROM concurrency_account
WHERE account_id = 1;
```

Kết quả 950 cho thấy B đã ghi giá trị được tính từ snapshot cũ. Cần lưu ý Oracle không có dirty read; cả A và B đọc giá trị đã commit là 1.000. Lost update ở đây đến từ logic read-modify-write của ứng dụng.

### 5.3. Bảo vệ bằng optimistic version check

Reset fixture. Hai session cùng đọc `balance=1000`, `version_no=0`. Sau khi A commit:

**Session A:**

```sql
UPDATE concurrency_account
SET balance = 900,
    version_no = version_no + 1
WHERE account_id = 1
  AND version_no = 0;

-- Kiểm tra SQL%ROWCOUNT = 1, sau đó:
COMMIT;
```

**Session B** dùng version đã đọc trước đó:

```sql
UPDATE concurrency_account
SET balance = 950,
    version_no = version_no + 1
WHERE account_id = 1
  AND version_no = 0;

-- SQL%ROWCOUNT phải bằng 0 vì version hiện tại đã là 1.
ROLLBACK;
```

Ứng dụng phải coi `rowcount=0` là optimistic conflict, không báo cập nhật thành công. Với JPA, `@Version` khiến Hibernate tự sinh điều kiện version và chuyển mismatch thành optimistic locking exception.

### 5.4. Bảo vệ bằng atomic update

Nếu nghiệp vụ chỉ là trừ số dư và không cần quyết định dựa trên một bản đọc phức tạp, có thể đưa phép tính vào một câu SQL:

```sql
UPDATE concurrency_account
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;
```

Kiểm tra `SQL%ROWCOUNT` để biết có dòng được cập nhật hay không. Câu SQL atomic này giúp Oracle thực hiện phép trừ trên giá trị hiện tại theo thứ tự khóa dòng, tránh mô hình đọc số dư cũ rồi ghi lại giá trị tuyệt đối. Vẫn cần transaction và kiểm tra business condition phù hợp.

## 6. Kịch bản 2: quan sát row lock và lock wait

### 6.1. Session A lấy row lock

```sql
SELECT account_id, balance
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE;
```

Session A giữ row lock cho tới khi commit hoặc rollback. Có thể kiểm tra:

```sql
UPDATE concurrency_account
SET balance = balance - 10
WHERE account_id = 1;
-- Chưa commit.
```

### 6.2. Session B thử cập nhật cùng dòng

Trong lúc A chưa commit:

```sql
UPDATE concurrency_account
SET balance = balance - 20
WHERE account_id = 1;
```

B sẽ chờ lock do A giữ. Sau khi A commit/rollback, B có thể tiếp tục theo điều kiện và trạng thái dữ liệu hiện tại. Ghi nhận thời gian B bắt đầu chờ và thời gian A giải phóng lock.

### 6.3. Kiểm tra NOWAIT và WAIT

Trong khi A vẫn giữ lock, Session B chạy:

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE NOWAIT;
```

Oracle trả `ORA-00054` nếu không lấy được lock ngay.

Hoặc:

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE WAIT 3;
```

Oracle chờ tối đa khoảng ba giây rồi báo lỗi nếu lock chưa được giải phóng. Mã lỗi thường gặp khi hết thời gian chờ là `ORA-30006`.

### 6.4. Kiểm tra SKIP LOCKED

Khi A khóa account 1, B chạy:

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

B có thể nhận account 2 và bỏ qua account 1 đang bị khóa. Đây là kỹ thuật hữu ích cho nhiều worker cùng claim dòng queue. Kết quả có thể rỗng nếu tất cả dòng phù hợp đang bị khóa; không được hiểu kết quả rỗng là queue không có công việc.

## 7. Kịch bản 3: tái hiện deadlock có kiểm soát

### 7.1. Chuẩn bị

Reset dữ liệu và commit. Hai session dùng hai dòng khác nhau:

**Session A:**

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE;
```

**Session B:**

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 2
FOR UPDATE;
```

### 7.2. Tạo chu trình chờ

**Session A** yêu cầu dòng 2:

```sql
UPDATE concurrency_account
SET balance = balance + 1
WHERE account_id = 2;
```

A chờ B.

**Session B** yêu cầu dòng 1:

```sql
UPDATE concurrency_account
SET balance = balance + 1
WHERE account_id = 1;
```

B chờ A. Oracle phát hiện deadlock và trả `ORA-00060` cho một statement được chọn để phá chu trình. Statement bị chọn được rollback; transaction còn lại có thể tiếp tục sau khi lock được giải phóng.

Sau khi quan sát, chủ động rollback cả hai session để đưa fixture về trạng thái đã biết. Trong ứng dụng, khi nhận deadlock, rollback transaction lỗi và chỉ retry nếu nghiệp vụ cho phép.

### 7.3. Ngăn deadlock bằng thứ tự khóa thống nhất

Nếu mọi transaction luôn khóa account theo thứ tự tăng dần `ACCOUNT_ID`, A và B sẽ yêu cầu cùng một thứ tự. Một transaction có thể phải chờ transaction kia, nhưng chu trình chờ sẽ khó hình thành hơn.

Đối với nghiệp vụ cập nhật nhiều dòng, xác định thứ tự khóa nhất quán và giữ transaction ngắn. Không dựa vào thứ tự tình cờ của query plan; nếu cần, lấy khóa theo danh sách khóa đã sắp xếp rõ ràng.

## 8. Kịch bản 4: READ COMMITTED và SERIALIZABLE

### 8.1. READ COMMITTED mặc định của Oracle

Oracle mặc định sử dụng `READ COMMITTED`. Mỗi câu SQL nhìn thấy dữ liệu đã commit trước thời điểm statement bắt đầu. Vì vậy, hai câu SELECT trong cùng transaction có thể nhìn thấy hai snapshot khác nhau nếu transaction khác commit ở giữa.

Schedule minh họa:

| Thứ tự | Session A | Session B |
|---:|---|---|
| 1 | `SELECT balance` thấy 1.000 | |
| 2 | | `UPDATE ... SET balance=900; COMMIT;` |
| 3 | `SELECT balance` lần hai thấy 900 | |

Đây là non-repeatable read ở cấp transaction, nhưng mỗi câu SELECT vẫn đọc dữ liệu nhất quán tại thời điểm statement của nó.

### 8.2. SERIALIZABLE

Đặt isolation level trước khi transaction thực hiện DML/query:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
```

Transaction nhìn snapshot nhất quán tại thời điểm transaction bắt đầu. Nếu một transaction khác sửa dòng sau snapshot và transaction hiện tại cố sửa cùng dòng, Oracle có thể trả `ORA-08177: can't serialize access for this transaction`.

Lịch kiểm thử:

1. A bắt đầu transaction SERIALIZABLE và đọc account 1.
2. B bắt đầu transaction, cập nhật account 1 và commit.
3. A cập nhật account 1 dựa trên snapshot cũ.
4. Oracle có thể báo `ORA-08177`; A phải rollback và bắt đầu transaction mới nếu retry.

Không chạy `SET TRANSACTION` sau khi transaction đã bắt đầu thao tác dữ liệu. Nếu muốn so sánh isolation level, reset fixture và dùng session mới hoặc transaction mới cho mỗi lượt.

### 8.3. Không nhầm SERIALIZABLE với khóa toàn bộ bảng

Oracle SERIALIZABLE dùng cơ chế read consistency và kiểm tra xung đột serialization; nó không đơn giản là khóa tất cả dòng mà transaction đã đọc. Transaction khác vẫn có thể thực hiện một số thay đổi; xung đột được phát hiện theo quy tắc Oracle khi transaction cố ghi dữ liệu không thể tuần tự hóa.

## 9. Kịch bản 5: nhiều worker claim job bằng SKIP LOCKED

### 9.1. Tạo queue test

```sql
CREATE TABLE concurrency_job (
    job_id       NUMBER(10) PRIMARY KEY,
    status       VARCHAR2(20) NOT NULL,
    payload      VARCHAR2(200),
    claimed_by   VARCHAR2(50),
    claimed_at   TIMESTAMP(6)
);

INSERT INTO concurrency_job(job_id, status, payload)
VALUES (1, 'READY', 'job-one');

INSERT INTO concurrency_job(job_id, status, payload)
VALUES (2, 'READY', 'job-two');

INSERT INTO concurrency_job(job_id, status, payload)
VALUES (3, 'READY', 'job-three');

COMMIT;
```

### 9.2. Worker A khóa và claim một job

```sql
SELECT job_id, payload
FROM concurrency_job
WHERE status = 'READY'
ORDER BY job_id
FETCH FIRST 1 ROW ONLY
FOR UPDATE SKIP LOCKED;
```

Sau khi lấy được job, A cập nhật trạng thái và commit:

```sql
UPDATE concurrency_job
SET status = 'RUNNING',
    claimed_by = 'WORKER_A',
    claimed_at = SYSTIMESTAMP
WHERE job_id = :job_id;

COMMIT;
```

Worker B chạy cùng câu SELECT trong lúc A đang giữ lock. B bỏ qua dòng A đã khóa và có thể lấy job tiếp theo. Sau commit, các worker khác không còn coi job đã claim là `READY`.

### 9.3. Claim và cập nhật phải nằm trong transaction phù hợp

Không đọc job, commit, rồi mới cập nhật trạng thái trong một transaction khác. Khoảng trống giữa hai thao tác cho phép worker khác đọc cùng job và claim trùng. Khóa dòng, cập nhật trạng thái và commit phải được thực hiện trong cùng transaction ngắn.

Trong hệ thống thật, cần thêm lease/heartbeat, retry và xử lý job bị worker chết giữa chừng. `SKIP LOCKED` ngăn nhiều worker cùng lấy dòng đang khóa tại thời điểm claim; nó không tự giải quyết job bị bỏ dở sau khi đã commit trạng thái `RUNNING`.

## 10. Điều phối lịch thực thi từ Java

### 10.1. Dùng connection độc lập cho mỗi worker

Một test Java có thể dùng `ExecutorService` để chạy hai transaction song song và `CountDownLatch` để kiểm soát thứ tự. Ví dụ dưới đây minh họa schedule lost update bằng JDBC thuần:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch aCommitted = new CountDownLatch(1);

Callable<Void> sessionA = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            int oldBalance = readBalance(connection, 1);
            bothRead.countDown();
            await(bothRead, 5, TimeUnit.SECONDS);

            updateBalance(connection, 1, oldBalance - 100);
            connection.commit();
            aCommitted.countDown();
            return null;
        } catch (Exception ex) {
            connection.rollback();
            aCommitted.countDown();
            throw ex;
        }
    }
};

Callable<Void> sessionB = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            int oldBalance = readBalance(connection, 1);
            bothRead.countDown();
            await(bothRead, 5, TimeUnit.SECONDS);
            await(aCommitted, 5, TimeUnit.SECONDS);

            updateBalance(connection, 1, oldBalance - 50);
            connection.commit();
            return null;
        } catch (Exception ex) {
            connection.rollback();
            throw ex;
        }
    }
};

Future<Void> a = executor.submit(sessionA);
Future<Void> b = executor.submit(sessionB);
try {
    a.get(15, TimeUnit.SECONDS);
    b.get(15, TimeUnit.SECONDS);
} finally {
    executor.shutdownNow();
}
```

`readBalance`, `updateBalance` và `await` là helper do test định nghĩa; `await` phải ném lỗi nếu timeout hoặc thread bị interrupt. Ví dụ chỉ nhằm minh họa điều phối: cần bổ sung import, exception handling và bảo đảm latch được giải phóng trong mọi nhánh lỗi. Với test thực tế, nên dùng `try/finally` để luôn đếm latch/đóng executor, và đặt timeout ở cả `Future.get` lẫn barrier.

Điểm quan trọng:

- Hai callable lấy hai connection riêng từ `DataSource`.
- Cả hai đọc xong trước khi A ghi.
- B chỉ ghi sau khi A đã commit.
- B ghi giá trị tuyệt đối đã tính từ dữ liệu cũ để cố ý tái hiện lost update.
- Test xác nhận số dư cuối là 950 ở kịch bản lỗi, sau đó chạy lại với version check để xác nhận B bị từ chối.

### 10.2. Không dùng một EntityManager cho nhiều thread

`EntityManager` và Hibernate `Session` không thread-safe. Mỗi thread/transaction cần persistence context riêng. Nếu test dùng Spring `@Transactional` ở method test, transaction đó thường gắn với thread test; các thread worker không tự tham gia transaction này. Cần tạo transaction riêng trong từng worker và commit fixture trước khi bắt đầu.

Với Spring, có thể dùng `TransactionTemplate` trong từng worker hoặc gọi service qua Spring proxy để tạo transaction thực sự. Nếu cần `REQUIRES_NEW`, tránh self-invocation trong cùng bean vì proxy có thể không được gọi.

### 10.3. Barrier ở nhiều giai đoạn

Một schedule phức tạp có thể dùng nhiều barrier:

```text
Barrier 1: tất cả session đã kết nối và xác nhận SID
Barrier 2: tất cả session đã đọc dữ liệu đầu vào
Gate A: cho phép session A ghi/commit
Gate B: chỉ mở sau khi A commit
Barrier 3: tất cả session đã hoàn tất hoặc nhận lỗi
Verify: test runner đọc kết quả cuối
```

Ghi timestamp bằng `System.nanoTime()` cho thời lượng trong cùng JVM; dùng timestamp database như `SYSTIMESTAMP` khi cần đối chiếu phía Oracle. Không so sánh trực tiếp `nanoTime` giữa JVM khác nhau vì nó không phải đồng hồ tuyệt đối.

## 11. Điều phối session thủ công bằng SQL Developer/SQL*Plus

### 11.1. Chuẩn bị hai cửa sổ session

1. Mở hai connection riêng tới cùng service/PDB.
2. Chạy truy vấn SID ở cả hai cửa sổ và xác nhận khác nhau.
3. Reset fixture từ một session quản trị, commit.
4. Thực hiện từng bước theo bảng schedule, không chạy toàn bộ script A trước rồi mới script B nếu lịch yêu cầu xen kẽ.
5. Ghi thời điểm bắt đầu/kết thúc và kết quả từng lệnh.
6. Sau khi kết thúc, commit/rollback cả hai session và xác nhận không còn transaction/lock.

Trong SQL*Plus, có thể dùng `PROMPT` để đánh dấu bước và chạy lệnh theo từng đoạn. Lệnh `PAUSE` phù hợp cho script tương tác, nhưng không tự đồng bộ hai process; người kiểm thử vẫn phải điều khiển thứ tự giữa các cửa sổ.

### 11.2. Kiểm tra session identity

```sql
SELECT sid,
       serial#,
       username,
       status,
       module,
       action,
       client_identifier
FROM v$session
WHERE audsid = SYS_CONTEXT('USERENV', 'SESSIONID');
```

Ghi lại SID/SERIAL# cho từng cửa sổ. Với RAC, dùng `GV$SESSION` và thêm `INST_ID`.

## 12. Quan sát blocking session và lock trong Oracle

### 12.1. Xem session đang chờ và blocker

```sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session_status,
       blocking_instance,
       blocking_session,
       final_blocking_session,
       module,
       action
FROM v$session
WHERE username IS NOT NULL
ORDER BY seconds_in_wait DESC;
```

Các cột `BLOCKING_SESSION` và `FINAL_BLOCKING_SESSION` giúp nhận diện session gây chặn khi Oracle xác định được blocker. `EVENT` cho biết session đang chờ loại tài nguyên nào; không phải mọi wait đều là row lock.

### 12.2. Xem lock TX/TM

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.event,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
ORDER BY s.sid, l.type;
```

Các lock type thường gặp:

- `TX`: transaction enqueue, thường liên quan đến transaction/row-level contention.
- `TM`: DML enqueue trên đối tượng/table.

`LMODE` là mode đang giữ; `REQUEST` là mode đang yêu cầu. Giá trị mode là mã số Oracle quy định, cần đối chiếu tài liệu `V$LOCK` để diễn giải chính xác.

### 12.3. Xem transaction đang mở

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.start_time;
```

Session có transaction lâu thường là ứng viên cần điều tra nếu đang giữ lock. Kiểm tra application module/action, SQL hiện tại và thời điểm bắt đầu transaction trước khi yêu cầu kết thúc session.

### 12.4. Đánh dấu module/action từ ứng dụng

Ứng dụng có thể gắn tên nghiệp vụ vào session:

```sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'ConcurrencyTest',
    action_name => 'SessionA_UpdateAccount'
  );
  DBMS_SESSION.SET_IDENTIFIER('TEST_RUN_2026_001');
END;
/
```

Các giá trị này giúp DBA ghép session trong `V$SESSION` với test case và bước thực thi. Khi connection được trả về pool, cần reset module/action/client identifier để request sau không mang nhãn cũ.

## 13. Timeout và dọn dẹp sau test

### 13.1. Timeout của test runner

Đặt timeout cho:

- Chờ lấy connection từ pool.
- Chờ barrier/latch.
- `Future.get()` hoặc task completion.
- Query/statement.
- Transaction.
- Chờ lock nếu kịch bản có chủ đích.

Timeout của test runner không tự động rollback transaction phía database nếu thread bị hủy giữa lúc JDBC call đang chạy. Trong `finally`, cố gắng rollback, đóng ResultSet/Statement/Connection và giải phóng latch. Nếu connection bị mất, kiểm tra session/transaction ở Oracle trước khi chạy lại.

### 13.2. Dọn dẹp dữ liệu

Sau test:

```sql
ROLLBACK;

SELECT account_id, balance, version_no
FROM concurrency_account
ORDER BY account_id;
```

`ROLLBACK` chỉ tác động transaction của session hiện tại. DBA/test runner phải xác nhận các session khác đã kết thúc và dữ liệu fixture được reset bằng transaction riêng. Không xóa bảng test khi còn session đang giữ lock hoặc transaction chưa hoàn tất.

### 13.3. Không kill session như bước cleanup mặc định

`ALTER SYSTEM KILL SESSION` hoặc terminate process chỉ nên dùng khi session thực sự bị treo và đã xác định tác động. Kill session có thể dẫn tới rollback dài, ảnh hưởng user khác và tạo thêm tải undo. Ưu tiên rollback/đóng connection từ test harness; nếu cần DBA can thiệp, ghi lại SID, SERIAL#, INST_ID và lý do.

## 14. Các lỗi thiết kế test khiến kết quả không đáng tin

### 14.1. Chạy cùng một connection trên nhiều thread

Các thao tác không thực sự độc lập; kết quả không đại diện cho hai session Oracle. Dùng connection riêng cho từng worker và xác minh SID.

### 14.2. Dùng sleep thay barrier

Lịch thực thi phụ thuộc tốc độ máy và tải. Dùng latch/barrier hoặc điều khiển thủ công theo từng bước.

### 14.3. Test method có transaction bao ngoài

Các thread worker có thể không nhìn thấy fixture chưa commit từ transaction test; transaction của thread chính cũng không bao trùm transaction của worker. Commit fixture trước khi chạy và quản lý transaction riêng trong từng worker.

### 14.4. Không kiểm tra row count hoặc final state

Một statement không ném exception chưa chứng minh nghiệp vụ đúng. Với optimistic update, phải kiểm tra số dòng cập nhật. Với queue, phải kiểm tra mỗi job chỉ được claim một lần. Với lost update, tính giá trị cuối mong đợi từ các thao tác nghiệp vụ.

### 14.5. Dữ liệu test không tạo ra tranh chấp

Nếu mỗi session cập nhật một account khác nhau, test không kiểm tra được row lock hoặc lost update. Cần chủ động cho các session cùng truy cập key/dòng mục tiêu, nhưng cô lập test bằng ID riêng.

### 14.6. Không kiểm tra transaction còn mở

Một session có thể vẫn giữ lock sau khi test kết thúc nếu code quên commit/rollback. Luôn xác nhận transaction đã kết thúc và connection đã trả về pool.

## 15. Quy trình kiểm thử đồng thời có kiểm soát

1. Viết rõ invariant nghiệp vụ và lỗi cần tái hiện, ví dụ không mất cập nhật, tồn kho không âm hoặc mỗi job chỉ được một worker claim.
2. Tạo fixture riêng và commit trạng thái ban đầu; ghi lại Oracle release, isolation, schema, service và driver.
3. Mở nhiều connection độc lập; xác nhận SID/SERIAL#/INST_ID và gắn `MODULE`, `ACTION`, `CLIENT_IDENTIFIER`.
4. Mô tả schedule thành các bước có thứ tự; chỉ rõ session nào đọc, ghi, chờ, commit hoặc rollback.
5. Dùng barrier/latch trong Java hoặc điều khiển thủ công giữa SQL Developer/SQL*Plus; tránh sleep làm cơ chế đồng bộ.
6. Đặt timeout cho mọi điểm chờ và bảo đảm mọi nhánh lỗi đều rollback/đóng resource.
7. Chạy các kịch bản lost update, optimistic version conflict, pessimistic lock wait, NOWAIT/WAIT/SKIP LOCKED, deadlock và SERIALIZABLE khi phù hợp.
8. Quan sát `V$SESSION`, `V$LOCK`, `V$TRANSACTION` và event/blocker để xác nhận database thực sự có wait/lock như dự kiến.
9. Kiểm tra row count, exception, final state và log sự kiện sau khi tất cả transaction hoàn tất.
10. Reset fixture và chạy lặp lại; giữ lại schedule, kết quả và thông số môi trường để tái hiện regression.

## 16. Nguyên tắc cần ghi nhớ

- Kiểm thử concurrency cần nhiều Oracle session thật; hai thread dùng chung một connection không phải hai database session độc lập.
- Lịch thực thi phải được xác định rõ; dùng barrier/latch thay vì dựa vào `sleep`.
- Commit fixture trước khi chạy worker; mỗi worker có connection, transaction và persistence context riêng.
- Oracle READ COMMITTED không cho dirty read, nhưng vẫn có thể có lost update do logic read-modify-write và non-repeatable read giữa các statement.
- `@Version`/version predicate giúp phát hiện lost update; `SELECT FOR UPDATE` giữ row lock tới commit/rollback.
- `NOWAIT`, `WAIT n` và `SKIP LOCKED` có hành vi khác nhau; cần kiểm tra lỗi và tập dòng được trả về.
- Deadlock cần được tái hiện bằng thứ tự khóa đối nghịch; giảm rủi ro bằng thứ tự khóa nhất quán và transaction ngắn.
- `SERIALIZABLE` có thể phát sinh `ORA-08177`; retry phải bắt đầu transaction mới.
- Quan sát blocker, wait event, TX/TM lock và transaction age để xác nhận nguyên nhân, không chỉ dựa vào thời gian test.
- Dọn dẹp bằng rollback/close có kiểm soát; không kill session hoặc xóa fixture khi chưa xác nhận transaction đã kết thúc.

## Tài liệu Oracle và Java tham khảo

- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html)
- [Oracle Database 19c SQL Language Reference — SELECT and FOR UPDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html)
- [Oracle Database 19c Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html)
- [Oracle Database 19c Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html)
- [Oracle Database 19c Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html)
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
