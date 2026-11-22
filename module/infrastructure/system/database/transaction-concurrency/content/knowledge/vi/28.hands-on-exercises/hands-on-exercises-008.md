# Tái hiện, chẩn đoán và khắc phục một bế tắc

Deadlock (bế tắc) xảy ra khi các transaction chờ lẫn nhau theo một chu trình. Một transaction đang giữ tài nguyên mà transaction khác cần, đồng thời lại chờ tài nguyên do transaction kia giữ. Không transaction nào trong chu trình có thể tự tiến triển nếu không có một transaction bị hủy hoặc nhả khóa.

Bài tập này dựng một deadlock có thể tái hiện bằng hai session database, lần theo quan hệ chờ, đọc thông tin chẩn đoán của các hệ quản trị phổ biến và sửa nguyên nhân bằng cách lấy khóa theo một thứ tự thống nhất. Trọng tâm là thực hành toàn bộ quy trình: **tạo xung đột có kiểm soát, quan sát bằng chứng, xác định chu trình, sửa cách lấy khóa và chạy lại để xác nhận**.

## 1. Mục tiêu và mô hình thử nghiệm

Ta mô phỏng hai giao dịch chuyển tiền giữa hai tài khoản:

- Tài khoản `1` có số dư ban đầu là 1.000.
- Tài khoản `2` có số dư ban đầu là 1.000.
- Transaction `T1` chuyển 100 từ tài khoản 1 sang tài khoản 2.
- Transaction `T2` chuyển 100 từ tài khoản 2 sang tài khoản 1.

Mỗi giao dịch cần cập nhật cả hai hàng. Nếu hai giao dịch khóa theo thứ tự ngược nhau, chúng có thể tạo deadlock:

```text
T1 giữ khóa tài khoản 1, sau đó cần tài khoản 2
T2 giữ khóa tài khoản 2, sau đó cần tài khoản 1

Wait-for graph:

T1 ─────────▶ T2
 ▲             │
 └─────────────┘
```

`T1` chờ khóa do `T2` giữ; `T2` chờ khóa do `T1` giữ. Đồ thị có chu trình `T1 → T2 → T1`, vì vậy DBMS có thể phát hiện deadlock và chọn một transaction làm nạn nhân.

Bài lab dùng PostgreSQL để tái hiện bằng hai session độc lập. Sau đó, phần chẩn đoán giới thiệu công cụ tương ứng trong PostgreSQL, MySQL/InnoDB, SQL Server và Oracle.

## 2. Chuẩn bị bảng thử nghiệm trong PostgreSQL

Chạy phần setup một lần trong database thử nghiệm dành riêng cho bài lab. Lệnh `DROP TABLE IF EXISTS` xóa bảng cùng dữ liệu hiện có; chỉ chạy nếu `deadlock_lab_accounts` là bảng lab có thể tạo lại. Không chạy phần setup này trên database chứa dữ liệu nghiệp vụ.

```sql
DROP TABLE IF EXISTS deadlock_lab_accounts;

CREATE TABLE deadlock_lab_accounts (
    account_id INTEGER PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO deadlock_lab_accounts (account_id, balance)
VALUES
    (1, 1000.00),
    (2, 1000.00);
```

Kiểm tra dữ liệu:

```sql
SELECT account_id, balance
FROM deadlock_lab_accounts
ORDER BY account_id;
```

Kết quả ban đầu:

| account_id | balance |
|---:|---:|
| 1 | 1000.00 |
| 2 | 1000.00 |

Mở hai cửa sổ SQL hoặc hai kết nối `psql` độc lập. Gọi chúng là **Session A** và **Session B**. Không chạy cả hai luồng trên cùng một connection vì mục tiêu là tạo hai transaction thực sự độc lập.

## 3. Tái hiện deadlock bằng hai session

Hãy chạy từng bước theo đúng thứ tự. Sau mỗi bước, chờ session được chỉ định hoàn tất câu lệnh trước khi chuyển sang bước tiếp theo.

### Bước 1 — Session A khóa tài khoản 1

Trong Session A:

```sql
BEGIN;

UPDATE deadlock_lab_accounts
SET balance = balance - 100
WHERE account_id = 1;
```

Lệnh `UPDATE` hoàn tất và Session A giữ khóa ghi trên hàng tài khoản 1 cho đến khi transaction kết thúc.

### Bước 2 — Session B khóa tài khoản 2

Trong Session B:

```sql
BEGIN;

UPDATE deadlock_lab_accounts
SET balance = balance - 100
WHERE account_id = 2;
```

Session B giữ khóa ghi trên hàng tài khoản 2. Lúc này:

| Session | Đang giữ khóa |
|---|---|
| A / T1 | Hàng tài khoản 1 |
| B / T2 | Hàng tài khoản 2 |

Hai session chưa chờ nhau nên deadlock chưa hình thành.

### Bước 3 — Session A yêu cầu tài khoản 2

Quay lại Session A:

```sql
UPDATE deadlock_lab_accounts
SET balance = balance + 100
WHERE account_id = 2;
```

Lệnh này bị chặn vì Session B đang giữ khóa hàng tài khoản 2. Để nguyên Session A ở trạng thái chờ. Chưa commit hoặc rollback Session B.

Quan hệ chờ hiện tại chỉ có một chiều:

```text
T1 ─────▶ T2
```

Đây mới là blocking thông thường, chưa phải deadlock. Nếu T2 commit ngay, T1 sẽ tiếp tục được.

### Bước 4 — Session B yêu cầu tài khoản 1

Trong khi Session A vẫn chờ, chạy ở Session B:

```sql
UPDATE deadlock_lab_accounts
SET balance = balance + 100
WHERE account_id = 1;
```

Session B phải chờ hàng tài khoản 1 do Session A đang giữ. Lúc này đã hình thành chu trình:

```text
T1 giữ hàng 1, chờ hàng 2 của T2
T2 giữ hàng 2, chờ hàng 1 của T1
```

PostgreSQL phát hiện deadlock sau thời gian kiểm tra được cấu hình và hủy một trong hai transaction. Một session nhận thông báo tương tự:

```text
ERROR: deadlock detected
DETAIL: Process ... waits for ...; blocked by process ...
        Process ... waits for ...; blocked by process ...
HINT: See server log for query details.
```

Thông tin process ID, transaction ID và câu SQL cụ thể thay đổi theo lần chạy. Không dựa vào giả định Session A hay Session B luôn là nạn nhân; DBMS quyết định transaction nào bị hủy.

### Bước 5 — Kết thúc transaction sau deadlock

Trong PostgreSQL, transaction bị lỗi do deadlock chuyển sang trạng thái aborted. Chạy trong session nhận lỗi:

```sql
ROLLBACK;
```

Transaction còn lại thường được giải phóng khỏi trạng thái chờ, hoàn tất câu `UPDATE` đang chờ và có thể commit:

```sql
COMMIT;
```

Nếu session còn lại không tự tiếp tục như mong đợi, kiểm tra trạng thái kết nối và transaction trước khi thực hiện lệnh tiếp theo. Không để một transaction thử nghiệm còn mở sau khi kết thúc lab.

### Bước 6 — Kiểm tra kết quả

Chạy từ một session thứ ba hoặc sau khi cả hai transaction đã kết thúc:

```sql
SELECT account_id, balance
FROM deadlock_lab_accounts
ORDER BY account_id;
```

Chỉ một transaction chuyển tiền hoàn tất; transaction nạn nhân đã rollback toàn bộ thay đổi chưa commit. Vì vậy, kết quả thường là một trong hai trường hợp:

| Transaction thành công | Tài khoản 1 | Tài khoản 2 |
|---|---:|---:|
| T1 chuyển 1 → 2 | 900.00 | 1100.00 |
| T2 chuyển 2 → 1 | 1100.00 | 900.00 |

Tổng số dư vẫn là 2.000. Đây là dấu hiệu transaction nạn nhân đã được rollback cùng thay đổi đầu tiên mà nó thực hiện trước khi deadlock.

Nếu kết quả không khớp, kiểm tra xem có session nào chưa rollback/commit, có câu lệnh nào đã chạy thêm hoặc có dữ liệu cũ từ lần lab trước hay không.

Sau khi cả hai transaction đã kết thúc, có thể đặt lại số dư để chạy lại kịch bản:

```sql
UPDATE deadlock_lab_accounts
SET balance = 1000.00
WHERE account_id IN (1, 2);
```

Chỉ reset sau khi xác nhận không còn session lab nào giữ transaction trên bảng.

## 4. Quan sát blocking trước khi tạo chu trình

Ở bước 3, Session A đang chờ Session B nhưng chưa có deadlock. Đây là thời điểm thuận tiện để dùng một session thứ ba quan sát blocker.

Trong PostgreSQL, chạy:

```sql
SELECT a.pid,
       a.application_name,
       a.state,
       a.wait_event_type,
       a.wait_event,
       pg_blocking_pids(a.pid) AS blocking_pids,
       now() - a.query_start AS query_age,
       now() - a.xact_start AS transaction_age,
       left(a.query, 250) AS query_text
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
```

Kết quả cho biết PID đang bị chặn và PID của session chặn nó. Khi Session A chờ khóa hàng 2, `pg_blocking_pids()` của A thường chứa PID Session B.

Các cột cần đọc:

- `pid`: process ID của backend.
- `state`: session đang `active`, `idle` hay `idle in transaction`.
- `wait_event_type`: nhóm wait, thường là `Lock` trong ví dụ này.
- `wait_event`: loại wait cụ thể do PostgreSQL báo cáo.
- `blocking_pids`: các backend đang chặn session.
- `transaction_age`: tuổi transaction; một transaction mở lâu có thể giữ khóa lâu.
- `query_text`: câu lệnh hiện tại, có thể bị cắt ngắn để dễ xem.

Một blocker có thể ở trạng thái `idle in transaction`: câu SQL cuối đã chạy xong nhưng ứng dụng chưa commit hoặc rollback. Session đó vẫn có thể giữ khóa.

## 5. Quan sát chu trình và lock trong PostgreSQL

Khi chạy Bước 4, deadlock detector thường giải quyết chu trình khá nhanh. Nếu muốn quan sát hàng đợi trước khi detector xử lý, cần môi trường lab được phép điều chỉnh `deadlock_timeout` hoặc chụp dữ liệu ngay trong cửa sổ ngắn trước khi lỗi xuất hiện. Không thay đổi tham số hệ thống production chỉ để quan sát.

Truy vấn các lock đang chờ:

```sql
SELECT a.pid,
       a.state,
       l.locktype,
       l.mode,
       l.granted,
       CASE
           WHEN l.relation IS NOT NULL
           THEN l.relation::regclass::text
       END AS relation_name,
       a.wait_event_type,
       a.wait_event,
       left(a.query, 200) AS query_text
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE NOT l.granted
   OR a.pid IN (
       SELECT unnest(pg_blocking_pids(pid))
       FROM pg_stat_activity
   )
ORDER BY a.pid;
```

`pg_locks` biểu diễn nhiều loại khóa và tài nguyên. Không phải mọi row lock đang giữ đều hiện ra như một bản ghi row lock đơn giản; PostgreSQL thường phối hợp tuple lock với transaction ID lock. `pg_blocking_pids()` là cách tiện để lần theo blocker trực tiếp.

### Ghi log deadlock

Trong môi trường thử nghiệm, DBA có thể bật `log_lock_waits` và xem `deadlock_timeout` để ghi nhận những lần chờ đủ lâu và deadlock. Ví dụ cấu hình ở mức hệ thống:

```sql
SHOW deadlock_timeout;
SHOW log_lock_waits;
```

Việc thay đổi các tham số logging có yêu cầu quyền và cách reload/restart tùy cấu hình. Sau khi bật, xem PostgreSQL server log để đọc chi tiết process chờ, process chặn, loại khóa và câu SQL liên quan.

Log deadlock giúp dựng lại chu trình ngay cả khi deadlock đã được phát hiện và các quan hệ chờ không còn xuất hiện trong view hiện tại.

## 6. Cách đọc wait-for graph

Khi có báo cáo deadlock, chuyển thông tin thành các cạnh giữa transaction:

```text
T1 đang giữ lock L1
T1 yêu cầu lock L2, do T2 giữ
          ⇒ T1 → T2

T2 đang giữ lock L2
T2 yêu cầu lock L1, do T1 giữ
          ⇒ T2 → T1

Chu trình: T1 → T2 → T1
```

Với nhiều transaction, chu trình có thể dài hơn:

```text
T1 → T2 → T3 → T4 → T1
```

Đừng chỉ ghi nhận session nào bị hủy. Cần tìm tất cả transaction trong chu trình, mỗi transaction đang giữ tài nguyên nào và yêu cầu tài nguyên nào. Điều đó cho biết thứ tự lấy khóa nào đã tạo ra vòng chờ.

### Blocker trực tiếp và root blocker

Trong blocking thông thường có thể có chuỗi:

```text
T3 chờ T2
T2 chờ T1
T1 không chờ ai
```

`T1` là root blocker. Với deadlock, không có một root blocker duy nhất theo nghĩa đó; các transaction trong chu trình chặn lẫn nhau. Cần phá chu trình bằng cách hủy một transaction hoặc thay đổi thứ tự khóa để chu trình không thể hình thành.

## 7. Chẩn đoán trong MySQL/InnoDB

MySQL InnoDB tự phát hiện deadlock và thường rollback toàn bộ transaction được chọn làm nạn nhân. Có thể bắt đầu điều tra bằng:

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm phần `LATEST DETECTED DEADLOCK`. Phần này thường cho biết:

- Các transaction tham gia.
- Câu lệnh đang thực thi.
- Index và record bị khóa.
- Chế độ lock đang giữ và đang yêu cầu.
- Transaction được chọn làm nạn nhân.

Trong MySQL 8.0, Performance Schema cung cấp các bảng lock wait:

```sql
SELECT *
FROM performance_schema.data_lock_waits;
```

Có thể nối `data_lock_waits` với `data_locks` để đọc object, index, lock mode và transaction ID đang yêu cầu/đang giữ khóa. Quyền xem Performance Schema phụ thuộc cấu hình và quyền tài khoản.

Nếu cần ghi mọi deadlock vào error log, DBA có thể cân nhắc `innodb_print_all_deadlocks`. `SHOW ENGINE INNODB STATUS` chủ yếu cho biết deadlock gần nhất; log đầy đủ hữu ích khi sự cố xảy ra nhiều lần.

Lưu ý: InnoDB có thể dùng record lock, gap lock hoặc next-key lock tùy isolation level, chỉ mục và điều kiện truy vấn. Deadlock không chỉ xảy ra khi hai câu `UPDATE` cùng sửa một hàng; các thao tác insert, foreign key, unique index và khóa khoảng cũng có thể tham gia chu trình.

## 8. Chẩn đoán trong SQL Server

SQL Server thường chọn một transaction làm deadlock victim và trả lỗi 1205. Extended Events session `system_health` thường thu thập event `xml_deadlock_report`.

Có thể xem target ring buffer của session `system_health` bằng:

```sql
WITH system_health AS (
    SELECT CAST(t.target_data AS XML) AS target_data
    FROM sys.dm_xe_session_targets AS t
    JOIN sys.dm_xe_sessions AS s
      ON s.address = t.event_session_address
    WHERE s.name = N'system_health'
      AND t.target_name = N'ring_buffer'
)
SELECT event_node.query('.') AS deadlock_report
FROM system_health
CROSS APPLY target_data.nodes(
    '//event[@name="xml_deadlock_report"]'
) AS x(event_node);
```

Nếu ring buffer đã ghi đè event cũ hoặc không có kết quả, hãy cấu hình Extended Events session lưu event vào event file trong môi trường phù hợp. Có thể dùng giao diện SSMS để mở deadlock graph và xem trực quan:

- Process list: các session/transaction tham gia.
- Resource list: key, page, object hoặc tài nguyên bị tranh chấp.
- Victim process: transaction được chọn làm nạn nhân.
- Execution stack/input buffer: câu SQL và call stack liên quan.

DMV có thể hỗ trợ quan sát blocking hiện tại:

```sql
SELECT r.session_id,
       r.status,
       r.wait_type,
       r.wait_time,
       r.wait_resource,
       r.blocking_session_id,
       r.cpu_time,
       r.total_elapsed_time,
       s.open_transaction_count
FROM sys.dm_exec_requests AS r
JOIN sys.dm_exec_sessions AS s
  ON s.session_id = r.session_id
WHERE r.blocking_session_id <> 0;
```

DMV là ảnh chụp trạng thái hiện tại; deadlock graph từ Extended Events hữu ích hơn để phân tích chu trình đã xảy ra và transaction bị chọn làm victim.

## 9. Chẩn đoán trong Oracle

Oracle thường báo lỗi:

```text
ORA-00060: deadlock detected while waiting for resource
```

Oracle ghi thông tin deadlock graph vào trace file và thường có dấu vết trong alert log. DBA dùng trace để xác định:

- Session tham gia.
- Loại enqueue/resource bị tranh chấp.
- Lock mode đang giữ và đang yêu cầu.
- Câu SQL liên quan.
- Các đối tượng và hàng/index liên quan nếu trace cung cấp.

Có thể xem blocking session hiện tại qua `V$SESSION`:

```sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_session,
       sql_id,
       prev_sql_id,
       seconds_in_wait
FROM v$session
WHERE blocking_session IS NOT NULL
   OR event = 'enq: TX - row lock contention';
```

Để xem enqueue lock đang chờ hoặc đang giữ:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.event,
       s.blocking_session,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.request > 0
   OR l.block = 1;
```

`V$SESSION` và `V$LOCK` giúp xem blocking hiện tại; trace deadlock là bằng chứng quan trọng khi chu trình đã được Oracle phát hiện và giải quyết. Quyền truy cập các dynamic performance views thường cần quyền DBA hoặc quyền đọc tương ứng.

Oracle có thể rollback statement gây deadlock và trả `ORA-00060`; ứng dụng cần xử lý transaction còn lại theo trạng thái và quy tắc của Oracle, thường nên rollback về ranh giới an toàn rồi retry toàn bộ đơn vị nghiệp vụ. Không mặc định rollback scope giống PostgreSQL, InnoDB hoặc SQL Server.

## 10. Xác định nguyên nhân gốc từ deadlock graph

Khi đã có graph hoặc trace, đừng dừng ở kết luận “hai câu UPDATE bị deadlock”. Hãy trả lời các câu hỏi sau:

1. Mỗi transaction đã lấy khóa nào trước?
2. Mỗi transaction yêu cầu khóa nào tiếp theo?
3. Các hàng hoặc index key đó thuộc đối tượng nào?
4. Vì sao hai luồng lấy tài nguyên theo thứ tự khác nhau?
5. Có trigger, foreign key, cascade hoặc index duy nhất tạo thêm khóa ngoài câu SQL nhìn thấy không?
6. Transaction có giữ khóa trong lúc gọi API, xử lý file hoặc chờ người dùng không?
7. Câu truy vấn có thiếu index khiến phạm vi scan/lock rộng hơn cần thiết không?
8. Có thao tác nâng cấp lock từ shared sang exclusive hoặc nhiều lần đọc rồi ghi không?

Ví dụ hai đường code:

```text
Transfer A → B:
  khóa A
  khóa B
  cập nhật

Transfer B → A:
  khóa B
  khóa A
  cập nhật
```

Đây là nguyên nhân rõ ràng: thứ tự khóa phụ thuộc hướng chuyển tiền. Sửa bằng cách chuẩn hóa thứ tự khóa, không phải chỉ tăng timeout.

## 11. Khắc phục 1: lấy khóa theo thứ tự nhất quán

Quy tắc quan trọng nhất để tránh deadlock do nhiều transaction cần cùng tập tài nguyên là **mọi transaction phải lấy khóa theo cùng một thứ tự toàn cục**.

Với tài khoản có ID số, có thể luôn khóa ID nhỏ hơn trước, rồi đến ID lớn hơn, bất kể chiều chuyển tiền.

### PostgreSQL: khóa từng hàng theo thứ tự cố định

```sql
BEGIN;

-- Ứng dụng xác định first_id = LEAST(from_id, to_id)
-- và second_id = GREATEST(from_id, to_id).

SELECT account_id, balance
FROM deadlock_lab_accounts
WHERE account_id = 1
FOR UPDATE;

SELECT account_id, balance
FROM deadlock_lab_accounts
WHERE account_id = 2
FOR UPDATE;

-- Sau khi đã khóa cả hai hàng, kiểm tra số dư và cập nhật.
UPDATE deadlock_lab_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE deadlock_lab_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Ví dụ trên minh họa transaction chuyển từ tài khoản 1 sang 2. Với chiều ngược lại, ứng dụng vẫn khóa hàng 1 trước, hàng 2 sau; chỉ thay đổi hàng nào bị trừ và hàng nào được cộng.

Trong ứng dụng tổng quát, tạo danh sách hai ID, loại bỏ ID trùng nếu cần, sắp xếp tăng dần rồi khóa lần lượt. Không dựa vào thứ tự input của client.

### Java/Spring: sắp xếp ID trước khi khóa

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    List<Long> lockOrder = Stream.of(fromId, toId)
        .distinct()
        .sorted()
        .toList();

    Map<Long, Account> locked = new HashMap<>();
    for (Long id : lockOrder) {
        Account account = accountRepository.findByIdForUpdate(id)
            .orElseThrow(() -> new AccountNotFoundException(id));
        locked.put(id, account);
    }

    Account source = locked.get(fromId);
    Account destination = locked.get(toId);

    if (source.getBalance().compareTo(amount) < 0) {
        throw new InsufficientFundsException();
    }

    source.debit(amount);
    destination.credit(amount);
}
```

`findByIdForUpdate` cần được triển khai bằng cơ chế khóa phù hợp với DBMS, chẳng hạn `SELECT ... FOR UPDATE`. Toàn bộ thao tác phải chạy trong cùng transaction. Nếu hai ID giống nhau, nghiệp vụ cần xử lý riêng trước khi debit/credit.

### Vì sao thứ tự cố định phá chu trình?

Khi mọi transaction luôn khóa tài khoản 1 trước tài khoản 2:

1. T1 lấy khóa tài khoản 1.
2. T2 yêu cầu tài khoản 1 và chờ, chưa giữ khóa tài khoản 2.
3. T1 lấy khóa tài khoản 2, cập nhật và commit.
4. T2 lấy được khóa tài khoản 1, sau đó khóa tài khoản 2.
5. T2 cập nhật và commit.

T2 chỉ chờ T1; T1 không chờ T2. Không có cạnh quay ngược để tạo chu trình.

## 12. Khắc phục 2: rút ngắn transaction và thời gian giữ khóa

Transaction càng lâu, khóa càng có nhiều thời gian chặn session khác. Hãy:

- Không chờ người dùng nhập liệu sau khi đã lấy khóa.
- Không gọi HTTP API, email provider hoặc dịch vụ vận chuyển trong lúc giữ khóa nếu có thể tách ra.
- Không thực hiện xử lý CPU dài hoặc đọc file lớn trong transaction.
- Chỉ lấy connection và bắt đầu transaction gần thời điểm cần ghi.
- Commit/rollback ngay khi hoàn tất phần dữ liệu cần atomic.
- Tránh giữ transaction mở trong khi worker chờ queue hoặc retry.

Ví dụ, thay vì:

```text
BEGIN
  khóa order
  gọi API giao hàng (3 giây)
  ghi trạng thái
COMMIT
```

có thể:

```text
BEGIN
  cập nhật order
  ghi outbox event
COMMIT

Worker sau commit:
  đọc outbox
  gọi API giao hàng với idempotency key
  ghi kết quả bằng transaction riêng
```

Outbox giúp không giữ khóa database trong lúc chờ mạng; idempotency giúp worker retry an toàn khi kết quả call không rõ.

## 13. Khắc phục 3: giảm phạm vi khóa bằng truy vấn và index phù hợp

Một câu SQL có thể khóa hoặc kiểm tra phạm vi rộng hơn dự kiến nếu thiếu index hoặc điều kiện lọc không chọn lọc. Phạm vi khóa phụ thuộc DBMS, isolation level và kế hoạch thực thi.

Ví dụ, một truy vấn tìm đơn hàng theo `customer_id` nhưng không có index phù hợp có thể phải scan nhiều dữ liệu. Trong InnoDB, cách truy cập và isolation level còn ảnh hưởng gap/next-key locks. Trong SQL Server, lock escalation có thể thay đổi phạm vi khóa. Trong PostgreSQL, row-level lock và các khóa quan hệ có hành vi khác.

Hãy:

- Kiểm tra execution plan và số hàng thực tế được đọc.
- Tạo index cho predicate/join phù hợp nếu có lợi.
- Tránh cập nhật nhiều hàng hơn cần thiết.
- Chọn isolation level theo bất biến nghiệp vụ.
- Xem trigger và foreign key vì chúng có thể truy cập thêm bảng/hàng.

Không thêm index một cách máy móc. Index mới làm tăng chi phí ghi và có thể tạo thêm unique-key contention; hãy xác minh bằng workload thật.

## 14. Khắc phục 4: giảm nâng cấp khóa và thiết kế thao tác nguyên tử

Một số deadlock hình thành khi nhiều transaction cùng đọc bằng khóa chia sẻ rồi cùng cố nâng cấp lên khóa độc quyền. Nếu biết chắc một hàng sẽ được cập nhật, cân nhắc lấy khóa ghi phù hợp ngay từ đầu.

Ví dụ với PostgreSQL:

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

COMMIT;
```

Nếu quy tắc có thể biểu diễn trong một câu lệnh, conditional update cũng có thể giảm khoảng cách giữa đọc và ghi:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42
  AND available >= 1;
```

Ứng dụng kiểm tra số hàng bị cập nhật. Một hàng nghĩa là trừ thành công; không hàng nào nghĩa là không đủ điều kiện hoặc không tìm thấy sản phẩm. Câu lệnh nguyên tử không giải quyết mọi bất biến nhiều hàng, nhưng có thể tránh một số chuỗi đọc–kiểm tra–ghi không cần thiết.

## 15. Khắc phục 5: retry transaction nạn nhân an toàn

Ngay cả khi đã chuẩn hóa thứ tự khóa, deadlock vẫn có thể xảy ra do trigger, foreign key, các bảng khác hoặc luồng ghi chưa được sửa hết. Ứng dụng phải xử lý lỗi deadlock như lỗi có thể retry trong phạm vi phù hợp.

Quy trình an toàn:

1. Nhận diện đúng lỗi deadlock theo mã lỗi/SQLSTATE của DBMS.
2. Rollback transaction hiện tại hoặc đưa nó về trạng thái hợp lệ theo yêu cầu của DBMS.
3. Chờ một khoảng ngắn với exponential backoff và jitter.
4. Bắt đầu transaction mới.
5. Đọc lại dữ liệu và chạy lại toàn bộ logic nghiệp vụ.
6. Giới hạn số lần retry và tổng thời gian retry.
7. Nếu hết retry, trả lỗi có thể xử lý hoặc đưa công việc vào hàng đợi phù hợp.

Không chỉ chạy lại câu SQL cuối. Các bước đọc/kiểm tra trước đó có thể đã dựa trên trạng thái không còn đúng.

### Mã lỗi thường gặp

| DBMS | Dấu hiệu lỗi deadlock phổ biến | Lưu ý |
|---|---|---|
| PostgreSQL | SQLSTATE `40P01` | Transaction bị abort; cần rollback trước khi retry |
| MySQL/InnoDB | Error `1213`, SQLSTATE `40001` | InnoDB thường rollback toàn bộ transaction nạn nhân |
| SQL Server | Error `1205` | Transaction nạn nhân bị rollback |
| Oracle | `ORA-00060` | Xem trace; xử lý transaction theo rollback scope và trạng thái của Oracle |

Driver có thể bọc lỗi trong exception khác. Nên kiểm tra vendor error code hoặc SQLSTATE cụ thể, không dò chuỗi message.

### Pseudocode retry

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return transactionTemplate.execute(status -> {
            // Đọc lại dữ liệu, kiểm tra điều kiện,
            // khóa theo thứ tự cố định và cập nhật.
            return transferOnce(command);
        });
    } catch (RuntimeException ex) {
        if (!isDeadlock(ex) || attempt == maxAttempts) {
            throw ex;
        }

        sleepWithExponentialBackoffAndJitter(attempt);
    }
}
```

Đoạn code minh họa cách tổ chức retry bên ngoài ranh giới transaction. `transactionTemplate.execute` cần tạo transaction mới cho mỗi lần thử; không bắt lỗi rồi tiếp tục dùng một transaction đã bị đánh dấu rollback-only.

### Không retry side effect ngoài một cách mù quáng

Nếu transaction vừa ghi database vừa gửi email hoặc gọi payment provider, retry toàn bộ method có thể gửi lại email hoặc charge lần nữa. Hãy đưa side effect ra ngoài transaction bằng outbox, dùng idempotency key ở provider và deduplicate ở consumer.

## 16. Kiểm tra lại sau khi sửa

Sau khi sửa thứ tự khóa và transaction boundary, chạy lại cùng kịch bản hai session.

### Kịch bản đã sửa

Session A và Session B đều khóa tài khoản theo thứ tự tăng dần:

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock_lab_accounts
WHERE account_id = 1
FOR UPDATE;

SELECT account_id, balance
FROM deadlock_lab_accounts
WHERE account_id = 2
FOR UPDATE;

-- Thực hiện debit/credit theo hướng giao dịch.

COMMIT;
```

Trong cả hai session, luôn lấy khóa hàng 1 trước rồi hàng 2. Nếu A lấy khóa hàng 1 trước, B sẽ chờ ngay tại bước lấy hàng 1 và chưa giữ hàng 2. Sau khi A commit, B lấy lần lượt hai khóa và hoàn tất. Không có chu trình chờ.

### Assertions cần kiểm tra

- Hai transaction có thể hoàn tất tuần tự mà không tạo deadlock trong kịch bản này.
- Số dư không âm và tổng số dư được bảo toàn.
- Không có thay đổi một phần từ transaction thất bại.
- Không còn transaction mở hoặc session idle-in-transaction sau lab.
- Nếu một transaction vẫn bị deadlock bởi luồng khác, log và graph mới cho biết chu trình còn lại ở đâu.

Để kiểm tra kỹ hơn, chạy nhiều giao dịch chuyển tiền với cặp tài khoản đảo chiều và cùng quy tắc khóa. Sau mỗi đợt, xác nhận tổng số dư không đổi và không có tài khoản âm. Stress test bổ sung cho kịch bản xác định nhưng không thay thế việc kiểm tra deadlock graph.

## 17. Kiểm tra deadlock có thực sự biến mất không?

Không nên kết luận đã sửa chỉ vì một lần chạy không gặp lỗi. Hãy so sánh trước/sau bằng cùng workload và quan sát trong khoảng thời gian đủ dài.

| Chỉ số | Trước sửa | Sau sửa cần quan sát |
|---|---|---|
| Deadlock count | Có tăng theo workload | Giảm về 0 trong kịch bản đã sửa hoặc giảm rõ rệt trong workload thực |
| Lock wait duration | Có waiter chờ theo chu trình | Chờ một chiều có thể còn, nhưng chu trình do thứ tự khóa đảo phải biến mất |
| Transaction duration | Có transaction giữ khóa lâu | Giảm nếu đã rút ngắn transaction |
| Retry count | Có thể tăng do deadlock | Giảm; retry còn lại phải nằm trong giới hạn |
| Throughput | Có thể mất công việc do rollback/retry | Ổn định hơn ở cùng mức tải |
| p95/p99 latency | Có spike khi deadlock | Giảm spike do deadlock, nhưng vẫn cần theo dõi nguyên nhân khác |

Nếu deadlock vẫn xuất hiện, lấy graph mới và tìm đối tượng/transaction khác. Một fix cho cặp tài khoản không tự sửa deadlock do trigger, khóa metadata, bảng khác hoặc thứ tự khóa ở một luồng ghi khác.

## 18. Checklist điều tra khi gặp deadlock trong production

Khi nhận cảnh báo deadlock:

1. Ghi thời điểm, request ID, session ID và DBMS error code.
2. Lưu deadlock graph/trace trước khi dữ liệu chẩn đoán bị xoay vòng.
3. Xác định transaction victim và các transaction còn lại trong chu trình.
4. Ghi lại tài nguyên và lock mode của từng cạnh.
5. Liên hệ SQL với endpoint, worker, batch hoặc trigger.
6. So sánh thứ tự lấy khóa giữa các code path.
7. Kiểm tra index, predicate, foreign key và trigger có tạo thêm lock không.
8. Chọn fix phù hợp: thứ tự khóa, transaction ngắn hơn, index hoặc mô hình ghi khác.
9. Bảo đảm ứng dụng retry toàn bộ transaction với giới hạn và idempotency.
10. Chạy lại integration/load test và theo dõi deadlock count, wait time, throughput và tail latency.

Không nên kill session ngẫu nhiên hoặc tăng timeout chỉ để làm mất cảnh báo. Deadlock detector đã chọn nạn nhân để phá chu trình; điều cần sửa là nguyên nhân khiến các transaction lấy tài nguyên theo thứ tự tạo vòng chờ.

## 19. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Một session chờ khóa là deadlock | Chờ một chiều là blocking; deadlock cần chu trình chờ |
| Session bị hủy luôn là transaction gây lỗi | Victim được chọn để phá chu trình; các transaction khác cũng góp phần tạo chu trình |
| Tăng `lock_timeout` hoặc `deadlock_timeout` sửa được deadlock | Timeout chỉ thay đổi thời gian chờ/kiểm tra; không sửa thứ tự khóa gây chu trình |
| Hai câu UPDATE cùng bảng chắc chắn deadlock | Chỉ deadlock khi quan hệ giữ/yêu cầu khóa tạo thành chu trình |
| Chỉ cần khóa hàng con đang cập nhật | Nếu nhiều transaction cần nhiều hàng, phải lấy khóa theo thứ tự thống nhất |
| Một lần test không deadlock chứng minh đã sửa xong | Cần kiểm thử nhiều thứ tự và workload, đồng thời xem deadlock graph/log |
| Chỉ retry câu SQL bị lỗi là đủ | Thường phải rollback và chạy lại toàn bộ đơn vị nghiệp vụ |
| Retry toàn method luôn an toàn | Side effect ngoài có thể lặp; cần outbox và idempotency |
| Tăng connection pool làm deadlock biến mất | Nhiều connection hơn có thể làm cạnh tranh tăng; cần sửa thứ tự khóa và transaction |

## 20. Tự kiểm tra

**Tình huống 1:** T1 giữ khóa hàng A và chờ hàng B do T2 giữ. T2 không chờ khóa nào khác. Đây đã là deadlock chưa?

**Đáp án:** Chưa. Chỉ có cạnh `T1 → T2`; nếu T2 commit và nhả B thì T1 tiếp tục. Cần một cạnh quay lại từ T2 để tạo chu trình.

**Tình huống 2:** T1 khóa A rồi B; T2 khóa B rồi A. Wait-for graph có dạng gì?

**Đáp án:** `T1 → T2 → T1`. T1 chờ B do T2 giữ, T2 chờ A do T1 giữ. Đây là deadlock.

**Tình huống 3:** Vì sao không thể khẳng định Session A luôn là victim trong lab?

**Đáp án:** DBMS chọn victim theo thuật toán và chi phí nội bộ. Session gửi câu lệnh cuối tạo chu trình không nhất thiết luôn bị hủy; kết quả có thể khác giữa lần chạy và DBMS.

**Tình huống 4:** Hai giao dịch chuyển tiền theo hai hướng ngược nhau. Quy tắc khóa nào giúp tránh chu trình do thứ tự đảo?

**Đáp án:** Khóa cả hai tài khoản theo thứ tự ID tăng dần, bất kể tài khoản nguồn hay đích. Mọi code path phải dùng cùng thứ tự.

**Tình huống 5:** PostgreSQL báo SQLSTATE `40P01`. Ứng dụng nên retry phần nào?

**Đáp án:** Rollback transaction đã bị abort, bắt đầu transaction mới, đọc lại dữ liệu, kiểm tra lại điều kiện và chạy lại toàn bộ đơn vị nghiệp vụ. Không chỉ chạy lại câu lệnh cuối.

**Tình huống 6:** Sau khi sửa, T2 vẫn chờ T1 tại hàng tài khoản 1 nhưng deadlock không còn. Điều đó có thể đúng không?

**Đáp án:** Có. T2 chờ một chiều vì T1 lấy khóa trước; nếu T1 không chờ ngược lại T2 và commit, T2 tiếp tục. Đây là blocking thông thường, không phải deadlock.

**Tình huống 7:** Deadlock graph cho thấy câu lệnh bị chặn cập nhật bảng `orders`, nhưng blocker có SQL hiện tại là `SELECT`. Có thể kết luận SELECT đó đã lấy khóa không?

**Đáp án:** Không thể chỉ dựa vào SQL hiện tại. Blocker có thể đã chạy một câu DML trước đó rồi trở thành idle hoặc chạy câu khác trong cùng transaction. Cần xem transaction, SQL trước đó và lock graph.

**Tình huống 8:** Một transaction bị deadlock sau khi đã gọi payment provider. Retry toàn transaction có an toàn không?

**Đáp án:** Không nếu provider có thể đã thực hiện charge và không nhận diện retry. Dùng idempotency key ổn định ở provider, lưu intent và tách side effect qua outbox/saga; đối soát trạng thái trước khi thực hiện lại.

Khi xử lý deadlock, hãy tái hiện bằng hai session độc lập, xác nhận quan hệ chờ tạo thành chu trình, lưu graph/trace và lần theo thứ tự lấy khóa. Sửa nguyên nhân bằng một thứ tự khóa thống nhất, transaction ngắn và phạm vi truy vấn phù hợp; sau đó chạy lại kịch bản và đo cả deadlock, blocking, retry lẫn latency. Một deadlock được giải quyết bởi detector chỉ là sự cố đã được phục hồi; mục tiêu của bài tập là loại bỏ chu trình có thể tái tạo và bảo đảm ứng dụng phục hồi an toàn khi xung đột vẫn có thể xảy ra.

## Tài liệu tham khảo

- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [MySQL 8.0 — InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.0/en/innodb-deadlocks.html)
- [MySQL 8.0 — Performance Schema Data Lock Waits](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-data-lock-waits-table.html)
- [SQL Server — Deadlocks Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-deadlocks-guide)
- [SQL Server — system_health Extended Events Session](https://learn.microsoft.com/en-us/sql/relational-databases/extended-events/use-the-system-health-session)
- [Oracle Database — ORA-00060](https://docs.oracle.com/en/error-help/db/ora-00060/)
