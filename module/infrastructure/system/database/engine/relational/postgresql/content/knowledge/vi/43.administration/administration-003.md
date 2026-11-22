# Hủy truy vấn, kết thúc phiên và đánh giá ảnh hưởng trong PostgreSQL

## 1. Vì sao cần phân biệt hủy truy vấn và kết thúc phiên?

Khi PostgreSQL có một query chạy quá lâu, giữ lock hoặc làm cạn tài nguyên, người vận hành thường cần can thiệp để khôi phục dịch vụ. PostgreSQL cung cấp hai hàm quản trị quan trọng:

- `pg_cancel_backend(pid)` gửi tín hiệu yêu cầu hủy câu lệnh đang chạy trong backend.
- `pg_terminate_backend(pid)` gửi tín hiệu kết thúc backend session, làm connection bị đóng và transaction đang mở bị rollback.

Hai hành động có phạm vi và tác động khác nhau. Hủy query thường giữ connection để ứng dụng có thể tiếp tục sau khi xử lý lỗi. Kết thúc session mạnh hơn: mọi công việc chưa commit trong session bị hủy, locks được giải phóng khi backend kết thúc, nhưng ứng dụng phải xử lý connection failure và có thể phải reconnect.

Một quyết định thiếu thông tin có thể làm gián đoạn giao dịch hợp lệ, khiến ứng dụng retry hàng loạt, làm mất công việc chưa commit hoặc tạo ra trạng thái commit không rõ đối với client. Trước khi gửi tín hiệu, cần xác định đúng PID, owner, query, transaction age, wait event, blockers và business impact.

```text
Incident / slow query / lock contention
                 |
                 v
          Inspect pg_stat_activity
                 |
                 v
       Identify exact backend and impact
                 |
                 v
        Is a query actively running?
             /           \
           Yes            No
            |              |
            v              v
    pg_cancel_backend   Inspect idle transaction,
            |           pool and session ownership
            v
      Did query stop?
         /       \
       Yes        No / session still harmful
        |                    |
        v                    v
  Check transaction     Re-evaluate target and
  state and locks       pg_terminate_backend
        |                    |
        +---------+----------+
                  |
                  v
       Verify rollback, locks, app recovery,
       latency and service health
```

**Nguyên tắc vận hành:** chọn hành động nhỏ nhất có thể giải quyết sự cố, xác minh kết quả và đánh giá tác động tới transaction cũng như ứng dụng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `pg_cancel_backend` và `pg_terminate_backend`.
2. Đọc `pg_stat_activity` để xác định backend cần xử lý.
3. Phân tích lock blockers bằng `pg_blocking_pids`.
4. Đánh giá query age, transaction age và wait events.
5. Hiểu transaction ở trạng thái aborted sau query cancellation.
6. Xác định khi nào cancel không giải phóng được locks.
7. Hiểu rollback và commit ambiguity khi terminate session.
8. Kiểm tra quyền `pg_signal_backend` và giới hạn superuser.
9. Xử lý an toàn query chạy song song và connection pool.
10. Đặt `statement_timeout`, `lock_timeout` và idle transaction timeout.
11. Đánh giá ảnh hưởng tới DDL, index build, maintenance và replication.
12. Ghi audit và theo dõi kết quả can thiệp.
13. Thiết kế runbook, alert và retry policy.
14. Tránh cancel/terminate nhầm backend hoặc tạo retry storm.
15. Xác minh dịch vụ đã phục hồi sau khi can thiệp.

---

## 2. Backend session và query trong PostgreSQL

Một client connection thường được phục vụ bởi một PostgreSQL backend process. Backend giữ session state, transaction state, prepared statements, locks và các tài nguyên liên quan.

Một session có thể:
- Đang chạy một query.
- Đang chờ lock hoặc I/O.
- Đang idle giữa các câu lệnh.
- Đang idle nhưng vẫn ở trong transaction.
- Đang ở trạng thái transaction aborted sau lỗi.
- Đang thực hiện một lệnh quản trị hoặc thao tác dài.

### 2.1. Một session có thể chạy nhiều query theo thời gian

Khi query kết thúc, connection có thể tiếp tục được dùng cho câu lệnh khác. Vì vậy query cancellation không đồng nghĩa connection bị đóng.

### 2.2. Transaction có thể dài hơn query

Ứng dụng có thể mở transaction, chạy nhiều statements rồi để session idle. Query hiện tại không còn active nhưng transaction vẫn giữ snapshot/locks.

### 2.3. Backend PID là mục tiêu của hàm quản trị

`pg_stat_activity.pid` xác định process đang phục vụ session/backend. Cần xác nhận PID, user, database, application_name và backend_start trước khi gửi tín hiệu.

### 2.4. Không phải mọi process trong pg_stat_activity là client session

View có thể hiển thị background workers, WAL sender, autovacuum và process nội bộ. Runbook thông thường nên giới hạn mục tiêu vào client backends trừ khi có quy trình chuyên biệt.

## 3. pg_cancel_backend là gì?

`pg_cancel_backend(pid)` gửi tín hiệu query-cancel tới backend được chỉ định.

Ví dụ:

```sql
SELECT pg_cancel_backend(12345);
```

Nếu tín hiệu được gửi thành công, function trả về true. Điều đó chỉ cho biết tín hiệu đã được gửi; không chứng minh query đã dừng tại thời điểm function trả về.

### 3.1. Connection vẫn tồn tại

Cancel yêu cầu backend hủy câu lệnh đang thực thi. Backend session thường tiếp tục tồn tại và có thể nhận query khác sau khi transaction state được xử lý.

### 3.2. Query đang chạy mới là mục tiêu

Nếu session đang idle, không có statement active để hủy. Nếu session ở idle in transaction, vấn đề có thể là transaction mở chứ không phải query đang chạy.

### 3.3. Query cancellation được xử lý tại interrupt points

Backend xử lý tín hiệu tại các điểm kiểm tra interrupt. Một thao tác có thể không dừng ngay lập tức nếu đang ở đoạn code hoặc trạng thái chưa xử lý tín hiệu. Theo dõi trạng thái sau khi gửi.

### 3.4. SQLSTATE thường gặp

Client thường nhận lỗi query canceled với SQLSTATE `57014`. Driver/framework có thể biểu diễn exception khác nhau; cần kiểm tra cả SQLSTATE và application logs.

## 4. pg_terminate_backend là gì?

`pg_terminate_backend(pid)` gửi tín hiệu kết thúc backend process/session.

Ví dụ:

```sql
SELECT pg_terminate_backend(12345);
```

Backend bị kết thúc, connection đóng và transaction chưa commit của session bị rollback khi PostgreSQL xử lý backend exit.

### 4.1. Session bị đóng

Ứng dụng sẽ thấy connection bị mất hoặc lỗi kết nối. Pool thường phải loại connection đó và tạo connection mới.

### 4.2. Transaction đang mở bị rollback

Mọi thay đổi chưa commit trong transaction bị hủy. Những transaction đã commit trước đó không bị undo bởi thao tác terminate.

### 4.3. Locks được giải phóng khi backend kết thúc

Khi transaction/backend kết thúc, locks và transaction resources của session được giải phóng. Các sessions đang chờ có thể tiếp tục, nhưng cũng có thể tạo một đợt tải mới ngay sau đó.

### 4.4. Client có thể không biết COMMIT đã thành công hay chưa

Nếu connection bị mất đúng lúc COMMIT đang xử lý, client có thể không biết transaction đã commit trước khi backend bị terminate hay chưa. Phải reconcile bằng business operation ID/idempotency key.

## 5. So sánh cancel và terminate

| Tiêu chí | pg_cancel_backend | pg_terminate_backend |
|---|---|---|
| Mục tiêu | Query đang chạy | Backend session |
| Connection | Thường được giữ | Bị đóng |
| Query hiện tại | Bị yêu cầu hủy | Bị dừng khi backend kết thúc |
| Transaction explicit | Có thể chuyển sang aborted state | Transaction chưa commit bị rollback khi backend kết thúc |
| Locks | Có thể còn giữ tới khi transaction kết thúc | Được giải phóng khi backend/transaction kết thúc |
| Client | Thường nhận query-canceled error | Thường nhận connection error |
| Reconnect | Không cần nếu session còn tốt | Pool/client thường phải reconnect |
| Mức tác động | Hẹp hơn | Rộng hơn |
| Trường hợp phù hợp | Query runaway, statement quá lâu | Session treo, idle transaction giữ locks, cancel không đủ |

### 5.1. Cancel trước, terminate sau

Trong nhiều incident, cancel query là bước đầu tiên hợp lý nếu mục tiêu là một statement cụ thể. Nếu transaction vẫn giữ locks hoặc session không tự rollback/thoát transaction, cần đánh giá terminate.

### 5.2. Không phải quy tắc tuyệt đối

Một session idle in transaction không có query để cancel. Khi đó cần xử lý transaction/session theo policy, thường là yêu cầu application rollback hoặc terminate sau khi xác minh.

### 5.3. Quyết định dựa trên tác động

Nếu query là một batch quan trọng gần hoàn tất, cancel có thể lãng phí công việc. Nếu query đang block hàng nghìn requests, tiếp tục chờ có thể gây thiệt hại lớn hơn.

## 6. Đọc pg_stat_activity trước khi hành động

Query tổng quan:

```sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    backend_start,
    xact_start,
    query_start,
    state_change,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
```

### 6.1. pid

PID dùng làm đối số cho hàm cancel/terminate. Không chọn PID chỉ từ một ảnh chụp dashboard cũ.

### 6.2. application_name

Giúp xác định service, job hoặc tool sở hữu connection. Ứng dụng nên đặt application_name ổn định và có ý nghĩa.

### 6.3. state

Các trạng thái thường gặp gồm active, idle, idle in transaction và idle in transaction (aborted). Ý nghĩa trạng thái quyết định có nên cancel query hay xử lý session/transaction.

### 6.4. wait_event_type và wait_event

Cho biết backend đang chờ loại sự kiện nào, ví dụ Lock hoặc IO. Một backend active không nhất thiết đang dùng CPU; nó có thể đang chờ.

### 6.5. query_start và xact_start

query_start cho biết statement hiện tại bắt đầu lúc nào. xact_start cho biết transaction bắt đầu lúc nào. Transaction age có thể lớn hơn query age rất nhiều.

### 6.6. backend_type

Trên các version có cột này, lọc backend_type = 'client backend' giúp tập trung vào client sessions. Kiểm tra view columns trên version đang chạy trước khi dùng query monitoring cố định.

## 7. Tìm query chạy lâu

Ví dụ chỉ xem active client backends chạy hơn 5 phút:

```sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 400) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
  AND query_start < clock_timestamp() - interval '5 minutes'
ORDER BY query_start;
```

### 7.1. Thời gian dài không đồng nghĩa query xấu

Một report, backup coordination hoặc maintenance operation có thể chạy lâu theo thiết kế. So với workload class và SLO.

### 7.2. Query active nhưng đang chờ

Nếu wait_event_type = 'Lock', query có thể đang chờ blocker. Nếu wait event là I/O, CPU thấp không có nghĩa query không gây impact.

### 7.3. Query age không đo thời gian CPU

Đây là elapsed time từ query_start. Nó gồm thời gian chờ lock, I/O và các wait khác.

### 7.4. Không chỉ dựa vào query text

Query text có thể bị truncate hoặc bị ẩn theo quyền. Kết hợp PID, application_name, user, database, wait event và logs.

## 8. Tìm idle in transaction

Query:

```sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    state,
    now() - xact_start AS transaction_age,
    state_change,
    wait_event_type,
    wait_event,
    left(query, 300) AS last_query
FROM pg_stat_activity
WHERE state IN (
    'idle in transaction',
    'idle in transaction (aborted)'
)
ORDER BY xact_start;
```

### 8.1. Idle in transaction

Session đang chờ client gửi statement tiếp theo nhưng transaction vẫn mở. Nó có thể giữ locks và snapshot.

### 8.2. Idle in transaction (aborted)

Một statement đã lỗi/canceled trong explicit transaction. Transaction đang aborted và cần ROLLBACK hoặc kết thúc session.

### 8.3. pg_cancel_backend không giải quyết session idle

Nếu session không chạy query, cancel không có statement hữu ích để dừng. Cần application rollback hoặc terminate sau khi xác định owner/impact.

### 8.4. Tác động vacuum

Transaction snapshot cũ có thể ngăn vacuum loại bỏ dead tuples, làm table/index bloat tăng theo thời gian.

## 9. Tìm blocker trước khi cancel

Một query chậm có thể là nạn nhân của lock contention. Tìm blockers:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    blocker.state AS blocker_state,
    left(blocked.query, 250) AS blocked_query,
    left(blocker.query, 250) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid))
    AS p(blocker_pid) ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
ORDER BY blocker.xact_start NULLS LAST;
```

### 9.1. Cancel nạn nhân có thể không sửa blocker

Nếu query đang chờ lock bị cancel, blocker vẫn giữ lock. Các requests khác tiếp tục chờ.

### 9.2. Blocker có thể idle

Một blocker ở idle in transaction có thể giữ transaction-level locks dù không có query active. Cancel blocker không đủ; cần transaction rollback hoặc terminate session.

### 9.3. Root blocker quan trọng hơn danh sách nạn nhân

Một transaction duy nhất có thể block hàng trăm sessions. Xác định root blocker trước khi gửi tín hiệu.

### 9.4. Kiểm tra blocker owner

Xác định service, user, client address, transaction age và business operation. Một migration hoặc payment transaction có thể cần phối hợp owner trước khi terminate.

## 10. Hiểu lock state và lock lifetime

PostgreSQL giữ nhiều loại locks theo transaction hoặc statement lifetime.

### 10.1. Transaction-level locks

Nhiều locks được giữ tới khi transaction kết thúc. Nếu statement trong explicit transaction bị cancel và transaction chuyển sang aborted state, locks có thể vẫn được giữ cho tới ROLLBACK.

### 10.2. Statement-level effects

Một số locks/tuples có lifetime gắn với statement hoặc savepoint behavior. Không giả định mọi lock đều được giải phóng ngay khi query cancel.

### 10.3. Savepoint

Ứng dụng có thể dùng SAVEPOINT để rollback một phần transaction. Nếu error được xử lý đúng qua savepoint, transaction ngoài có thể tiếp tục; behavior phụ thuộc nơi lỗi xảy ra và application control flow.

### 10.4. Termination

Khi session bị terminate, transaction kết thúc bất thường và PostgreSQL rollback phần chưa commit, sau đó giải phóng locks/resources.

## 11. Điều gì xảy ra sau khi cancel trong autocommit?

Nếu ứng dụng chạy một statement độc lập trong autocommit:
1. PostgreSQL bắt đầu transaction ngầm cho statement.
2. Statement đang thực thi bị cancel.
3. Statement thất bại và transaction ngầm bị rollback.
4. Connection thường vẫn mở.
5. Ứng dụng nhận lỗi query canceled.
6. Statement tiếp theo có thể chạy trên connection nếu driver không đóng nó vì lý do riêng.

### 11.1. Dữ liệu chưa commit bị hủy

Các thay đổi của statement bị rollback. Transaction trước đó đã commit vẫn tồn tại.

### 11.2. Không giả định side effects ngoài database được rollback

Function/extension có thể gọi hệ thống bên ngoài. PostgreSQL rollback không thể tự undo email, HTTP request hoặc thao tác file đã xảy ra ngoài transaction.

### 11.3. Application phải xử lý SQLSTATE

Client cần bắt query-canceled exception, quyết định retry/return error và không tiếp tục giả định statement thành công.

### 11.4. Connection pool

Pool có thể giữ connection nếu session còn khỏe. Nếu driver đánh dấu connection lỗi, pool phải loại nó. Theo dõi pool metrics thay vì giả định.

## 12. Điều gì xảy ra sau khi cancel trong explicit transaction?

Ví dụ:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42;

-- Một statement tiếp theo bị cancel.

SELECT pg_sleep(120);

COMMIT;
```

Nếu statement trong transaction bị cancel, transaction thường chuyển sang trạng thái aborted. Các statements tiếp theo thường nhận lỗi:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
```

### 12.1. Cần ROLLBACK

Client phải gửi ROLLBACK để kết thúc transaction aborted và giải phóng transaction-level locks.

### 12.2. Không gửi COMMIT để “cứu” transaction aborted

COMMIT trong trạng thái aborted không làm các thay đổi trước đó trở thành committed. PostgreSQL kết thúc transaction theo trạng thái rollback.

### 12.3. Savepoint là ngoại lệ có kiểm soát

Nếu application đã đặt SAVEPOINT và xử lý lỗi bằng ROLLBACK TO SAVEPOINT trong flow phù hợp, transaction ngoài có thể tiếp tục. Không giả định framework tự làm điều đó nếu chưa kiểm tra.

### 12.4. Nếu client bỏ connection ở trạng thái aborted

Session có thể tiếp tục tồn tại idle in transaction (aborted), giữ resources cho tới khi client rollback hoặc session bị kết thúc/timeout.

## 13. Khi nào cancel không giải phóng locks?

Một trường hợp điển hình:
1. Session A mở transaction.
2. A thực hiện UPDATE và giữ row/table locks.
3. A chạy statement dài tiếp theo.
4. Operator cancel statement đó.
5. Transaction A chuyển sang aborted.
6. Client không gửi ROLLBACK.
7. A vẫn idle in transaction (aborted), locks từ transaction chưa được giải phóng.

```text
Session A
  BEGIN
    |
  UPDATE row X
    |
  holds transaction locks
    |
  long SELECT / statement
    |
  pg_cancel_backend(A)
    |
  statement aborted
    |
  transaction remains aborted/open
    |
  locks may remain until ROLLBACK
```

### 13.1. Kiểm tra state sau cancel

Đọc lại pg_stat_activity. Nếu state là idle in transaction (aborted), chờ application rollback trong khoảng thời gian ngắn theo runbook.

### 13.2. Phối hợp application owner

Nếu client có cơ chế cleanup transaction, để nó rollback có thể giữ connection reuse và ghi nhận exception đúng cách.

### 13.3. Terminate nếu session tiếp tục gây hại

Nếu transaction không rollback và tiếp tục block workload, terminate session có thể cần thiết sau khi đánh giá business impact.

### 13.4. Đừng cancel blocker rồi kết luận incident đã hết

Xác minh lock waiters thực sự tiến triển và blocker transaction đã kết thúc.

## 14. Điều gì xảy ra khi terminate session?

Khi backend bị terminate:
- Connection bị đóng.
- Query đang chạy không thể tiếp tục.
- Transaction chưa commit bị rollback.
- Locks/transaction resources được giải phóng khi backend kết thúc.
- Client nhận lỗi connection.
- Pool/client có thể reconnect hoặc retry.
- Công việc đã commit trước đó không bị rollback.

### 14.1. Rollback không phải khôi phục mọi side effect

External systems không nằm trong PostgreSQL transaction có thể đã nhận side effects. Dùng outbox/idempotency để quản lý các tác động này.

### 14.2. Large transaction

Một transaction ghi rất lớn có thể đã tạo WAL và dead tuples/cleanup work. Terminate không xóa lịch sử WAL; vacuum/recovery và storage vẫn phải xử lý các hậu quả liên quan.

### 14.3. Client commit outcome

Nếu terminate xảy ra quanh COMMIT, client không thể suy ra chắc chắn outcome chỉ từ connection error. Reconcile bằng request key hoặc business record trên primary hiện tại.

### 14.4. Connection pool churn

Terminating nhiều sessions có thể làm pool tạo connection mới hàng loạt, tăng authentication/startup overhead và tải lên postmaster.

## 15. Kiểm tra đúng backend trước khi gửi tín hiệu

Trước khi can thiệp, lấy snapshot:

```sql
SELECT
    pid,
    backend_start,
    datname,
    usename,
    application_name,
    client_addr,
    backend_type,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE pid = 12345;
```

Xác nhận:
- PID vẫn tồn tại.
- User/database đúng.
- Application/client đúng.
- Query/transaction đúng incident.
- Backend type là client backend nếu runbook chỉ cho phép client sessions.
- Trạng thái chưa thay đổi theo hướng query đã hoàn tất.
- Không phải PID của monitoring/admin connection cần giữ.

### 15.1. PID có thể biến mất

Query có thể hoàn tất giữa lúc inspect và cancel. Function có thể trả false nếu process không còn tồn tại hoặc không thể gửi signal.

### 15.2. PID không phải business identity

Ghi thêm application_name, client_addr, query_start, backend_start và request/incident context. PID có thể được tái sử dụng sau khi process kết thúc.

### 15.3. Kiểm tra lại ngay trước action

Không dùng PID copy từ alert cũ. Refresh pg_stat_activity trước khi thực hiện.

### 15.4. Exclude current backend

Không gửi tín hiệu tới PID của chính session đang chạy câu lệnh quản trị; dùng `pg_backend_pid()` để loại trừ.

## 16. Hủy query cụ thể bằng pg_cancel_backend

Sau khi xác minh PID và mục tiêu:

```sql
SELECT pg_cancel_backend(12345) AS signal_sent;
```

### 16.1. Kết quả true

True cho biết tín hiệu cancel đã được gửi thành công. Query vẫn có thể chưa dừng ngay tại thời điểm trả kết quả.

### 16.2. Kết quả false

Có thể backend đã kết thúc, PID không hợp lệ hoặc tín hiệu không được gửi. Kiểm tra lại pg_stat_activity và quyền.

### 16.3. Xác minh sau cancel

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid = 12345;
```

Nếu query đã kết thúc, có thể không còn state active. Nếu session còn idle in transaction (aborted), cần xử lý transaction.

### 16.4. Cancel có thể race với query completion

Query có thể hoàn tất trước khi backend xử lý tín hiệu. Luôn xác minh outcome thay vì suy ra từ boolean duy nhất.

## 17. Kết thúc session bằng pg_terminate_backend

Khi đã xác nhận cần kết thúc session:

```sql
SELECT pg_terminate_backend(12345) AS signal_sent;
```

### 17.1. Boolean return

Không có timeout argument, true cho biết tín hiệu terminate đã được gửi thành công; không nên hiểu đơn giản là mọi cleanup phía client đã hoàn tất.

### 17.2. Timeout argument ở các version hỗ trợ

Các PostgreSQL versions mới có overload nhận timeout milliseconds:

```sql
SELECT pg_terminate_backend(12345, 5000) AS terminated_within_timeout;
```

Kiểm tra đúng server version/function signature. Với version không hỗ trợ overload timeout, dùng dạng một đối số và polling pg_stat_activity để xác nhận backend đã biến mất.

### 17.3. Timeout không phải query timeout

Timeout argument của pg_terminate_backend (nếu có) là thời gian chờ backend exit sau khi gửi signal. Nó không phải giới hạn execution time của SQL statement.

### 17.4. Xác minh backend đã kết thúc

```sql
SELECT pid, backend_start, state, application_name
FROM pg_stat_activity
WHERE pid = 12345;
```

Không có row có thể cho biết backend đã thoát. Kết hợp logs và application connection status để xác minh đầy đủ.

## 18. Quyền thực hiện cancel và terminate

Các hàm signal backend bị giới hạn quyền.

Thông thường:
- Superuser có thể signal các backend, nhưng việc signal backend thuộc superuser vẫn chỉ dành cho superuser.
- User có thể signal backend thuộc cùng role theo quyền sở hữu tương ứng.
- Role được cấp predefined role `pg_signal_backend` có thể signal backend thuộc role khác, trong giới hạn không phải superuser.

### 18.1. Least privilege

Không cấp superuser cho monitoring/application chỉ để cancel query. Tạo role vận hành có quyền phù hợp theo chính sách.

### 18.2. pg_signal_backend

Ví dụ cấp role:

```sql
GRANT pg_signal_backend TO ops_operator;
```

Chỉ cấp cho operator được ủy quyền và theo dõi membership. Role này có quyền mạnh vì có thể ảnh hưởng sessions khác.

### 18.3. Kiểm tra quyền

Nếu function trả false hoặc báo permission denied, xác minh role membership và ownership. Không tìm cách vượt quyền bằng một service account không được phê duyệt.

### 18.4. Nội dung query có thể bị ẩn

Một role không có quyền xem đầy đủ statistics có thể không thấy query text của session khác. Role monitoring có thể cần pg_read_all_stats theo policy riêng.

## 19. Tìm blocker và chọn đúng PID để cancel

Một query bị block không phải lúc nào cũng là query nên cancel. Ví dụ SELECT chờ một transaction UPDATE giữ row lock; cancel SELECT chỉ loại bỏ một waiter, không giải phóng blocker.

### 19.1. Xác định blocked sessions

```sql
SELECT
    pid,
    application_name,
    now() - query_start AS wait_age,
    pg_blocking_pids(pid) AS blockers,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

### 19.2. Xem blocker state

Blocker có thể active, idle in transaction hoặc đang chờ một resource khác. Tìm root blocker và chuỗi dependency.

### 19.3. Cancel blocker query

Nếu blocker đang chạy một query dài và transaction có thể được rollback tự động bởi application, cancel có thể đủ. Xác minh transaction state và lock release.

### 19.4. Terminate blocker session

Nếu blocker idle in transaction, bị bỏ quên hoặc không thể rollback qua application, terminate có thể giải phóng transaction locks. Đánh giá uncommitted work trước.

## 20. Parallel query và worker processes

Parallel query có leader backend và một hoặc nhiều parallel workers. Khi query leader bị cancel, PostgreSQL điều phối việc hủy execution của query song song.

### 20.1. Xác định leader

Một số PostgreSQL versions có cột leader_pid trong pg_stat_activity để liên hệ worker với leader. Kiểm tra view version đang chạy.

### 20.2. Hủy backend client sở hữu query

Ưu tiên xử lý PID của client/leader session được xác định trong pg_stat_activity. Không tự chọn và terminate từng worker PID chỉ vì thấy nhiều process.

### 20.3. Worker không phải client session thông thường

Parallel worker là process nội bộ. Terminate nhầm worker có thể gây lỗi query và không giải quyết đúng transaction owner.

### 20.4. Kiểm tra cleanup

Sau cancel/terminate, theo dõi cả leader, workers và connection pool. Xác minh worker processes liên quan đã thoát và tài nguyên được giải phóng.

## 21. Cancel và terminate với DDL

DDL có thể giữ locks mạnh, ảnh hưởng nhiều sessions và có thời gian thực thi dài.

Ví dụ:
- ALTER TABLE.
- CREATE INDEX.
- REINDEX.
- DROP TABLE.
- VACUUM FULL.
- Partition maintenance.

### 21.1. Xác định DDL owner

Kiểm tra migration tool, deployment ID, application_name và change window. Một DDL có thể là migration hợp lệ.

### 21.2. Cancel DDL

Cancel statement thường làm statement thất bại/rollback theo transaction semantics. Nhưng một số DDL có behavior đặc biệt và có thể để lại artifacts cần kiểm tra.

### 21.3. CREATE INDEX CONCURRENTLY

Nếu CREATE INDEX CONCURRENTLY thất bại hoặc bị hủy, có thể để lại index ở trạng thái invalid. Kiểm tra pg_index.indisvalid/indisready và xử lý index theo runbook trước khi chạy lại.

### 21.4. Không terminate migration chỉ vì query age cao

Đánh giá lock impact, progress view, application traffic và rollback/cleanup implications trước.

## 22. Cancel maintenance operations

VACUUM, ANALYZE, REINDEX và các maintenance tasks có thể chạy lâu và tiêu thụ I/O.

### 22.1. Xem progress views

Dùng các progress views phù hợp như pg_stat_progress_vacuum, pg_stat_progress_create_index hoặc pg_stat_progress_analyze tùy operation/version.

### 22.2. Autovacuum worker

Không terminate autovacuum chỉ vì nó active hoặc chạy lâu. Autovacuum bảo vệ table health và transaction ID freezing.

### 22.3. Manual VACUUM

Nếu cần dừng manual VACUUM, hiểu tác động tới vacuum coverage, dead tuples và lịch bảo trì. Không coi cancel là đã hoàn tất maintenance.

### 22.4. REINDEX và index validity

Sau khi cancel/restart các index operations, xác minh index state và application query plans.

## 23. Cancel query bị lock wait

Nếu query đang chờ lock quá lâu, có thể cancel query waiter để giải phóng client/request capacity.

Ví dụ:

```sql
SELECT
    pid,
    application_name,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
  AND pid <> pg_backend_pid();
```

Sau đó, chỉ cancel waiter đã được xác nhận:

```sql
SELECT pg_cancel_backend(12345);
```

### 23.1. Query cancellation không sửa lock root cause

Nếu nhiều waiters cùng chờ một blocker, cần điều tra blocker. Chỉ cancel waiters có thể làm request errors tăng mà contention vẫn còn.

### 23.2. Lock timeout có thể phù hợp hơn

`lock_timeout` giới hạn thời gian một statement chờ lock. Nó giúp fail fast cho future statements, nhưng không tự giải quyết blocker đã tồn tại.

### 23.3. Statement timeout

`statement_timeout` giới hạn tổng thời gian statement, gồm cả thời gian chờ lock. Chọn giá trị phù hợp với endpoint/query class.

### 23.4. Đừng retry ngay lập tức không backoff

Nếu application retry liên tục trong khi blocker chưa được xử lý, nó có thể làm queue và load tăng thêm.

## 24. statement_timeout: phòng ngừa query quá lâu

`statement_timeout` tự động hủy statement vượt thời gian cấu hình.

Ví dụ:

```sql
SET statement_timeout = '30s';

SELECT *
FROM orders
WHERE customer_id = 42;
```

### 24.1. Phạm vi

SET áp dụng cho session hiện tại. Có thể đặt default theo role/database hoặc dùng SET LOCAL cho transaction.

### 24.2. Không đặt một giá trị cho mọi query

Một endpoint OLTP có thể cần timeout ngắn; report/ETL cần budget dài hơn. Chọn theo workload class.

### 24.3. Server-side và application deadline

Application deadline và statement_timeout cần phối hợp. Nếu client timeout trước, connection có thể bị bỏ lại trong lúc query vẫn chạy nếu driver không cancel đúng cách.

### 24.4. SET LOCAL

```sql
BEGIN;
SET LOCAL statement_timeout = '10s';

SELECT ...
;

COMMIT;
```

Local setting tự hết hiệu lực khi transaction kết thúc.

## 25. lock_timeout: giới hạn thời gian chờ lock

`lock_timeout` chỉ giới hạn thời gian chờ để acquire lock. Nếu vượt, statement bị hủy với lỗi.

```sql
SET lock_timeout = '2s';
```

### 25.1. Nên nhỏ hơn statement_timeout

Nếu cả hai được cấu hình, lock_timeout nên thấp hơn statement_timeout để statement fail vì lock wait trước khi tổng deadline hết.

### 25.2. Không thay thế statement_timeout

Query có thể chạy CPU/I/O lâu sau khi đã lấy được lock; lock_timeout không giới hạn thời gian đó.

### 25.3. DDL migrations

Một lock_timeout ngắn có thể giúp migration fail fast thay vì block traffic lâu. Migration tooling cần retry/backoff phù hợp.

### 25.4. Transaction state

Trong explicit transaction, lock timeout error làm transaction chuyển sang aborted state trừ khi lỗi được xử lý qua savepoint/exception flow phù hợp.

## 26. idle_in_transaction_session_timeout

`idle_in_transaction_session_timeout` kết thúc session để transaction idle quá lâu không tiếp tục giữ tài nguyên.

```sql
SHOW idle_in_transaction_session_timeout;
```

Ví dụ cấu hình theo role:

```sql
ALTER ROLE api_user
SET idle_in_transaction_session_timeout = '60s';
```

### 26.1. Đây là session termination

Khác statement_timeout, setting này kết thúc session khi nó idle trong transaction vượt ngưỡng. Client phải xử lý connection loss và transaction rollback.

### 26.2. Ngăn transaction bị bỏ quên

Hữu ích khi application có lỗi không rollback/commit sau request.

### 26.3. Chọn threshold

Không đặt quá thấp nếu ứng dụng hợp lệ có think time trong transaction. Thiết kế transaction ngắn thường tốt hơn.

### 26.4. Theo dõi logs

Ghi nhận sessions bị timeout và service owner để sửa connection/transaction lifecycle.

## 27. idle_session_timeout và connection pools

`idle_session_timeout` có thể kết thúc sessions idle ngoài transaction. Tuy nhiên pooler/application có thể mong giữ connections idle để tái sử dụng.

### 27.1. Tác động tới pool

Nếu timeout server ngắn hơn connection lifetime/health checks của pool, client có thể gặp stale connections hoặc reconnect churn.

### 27.2. Không áp dụng tùy tiện

Đánh giá pool behavior, keepalive, health check và session reuse trước khi bật.

### 27.3. Khác idle in transaction

Idle session không có transaction mở thường ít nguy hiểm hơn idle in transaction, dù vẫn tiêu thụ connection slot.

### 27.4. Role-specific policy

Có thể áp dụng khác nhau cho interactive users, API pool và reporting jobs.

## 28. Timeout precedence và transaction handling

Một query có thể chịu nhiều deadline:
- Application request timeout.
- Connection pool acquire timeout.
- Statement timeout.
- Lock timeout.
- Transaction/session idle timeout.
- Proxy/network timeout.

### 28.1. Lock timeout

Áp dụng cho thời gian chờ lock của statement.

### 28.2. Statement timeout

Áp dụng cho thời gian thực thi statement, gồm wait time.

### 28.3. Application deadline

Có thể kết thúc request nhưng không nhất thiết tự cancel backend. Driver cần gửi cancel hoặc đóng connection theo behavior đã được test.

### 28.4. Đồng bộ budget

Thiết kế timeout theo thứ tự và margin rõ ràng để database không tiếp tục chạy query lâu sau khi client đã bỏ request.

## 29. Tác động tới connection pool

Cancel và terminate ảnh hưởng pool khác nhau.

### 29.1. Sau cancel

Connection có thể tiếp tục được dùng nếu driver xác nhận backend/session còn khỏe và transaction state đã được xử lý. Trong explicit transaction, cần ROLLBACK.

### 29.2. Sau terminate

Connection bị đóng; pool phải loại connection và tạo connection mới. Connection churn có thể tăng.

### 29.3. Pool reset

Nếu session state có SET, temp tables hoặc prepared statements, pool reset policy cần phù hợp. Không tái sử dụng connection bị terminate.

### 29.4. Retry storm

Nhiều clients cùng nhận cancellation/connection errors có thể retry đồng loạt. Dùng exponential backoff, jitter, idempotency và retry budget.

## 30. Tác động tới application và business operation

Trước khi terminate, xác định query đang thực hiện việc gì:
- Thanh toán hoặc cập nhật số dư.
- Tạo đơn hàng.
- Batch import.
- Migration.
- Báo cáo.
- Job cleanup.
- Query tương tác của người dùng.

### 30.1. Giao dịch tài chính

Nếu transaction chưa commit, terminate sẽ rollback phần database chưa commit. Nếu commit outcome không rõ với client, cần tra idempotency key/business reference.

### 30.2. Batch jobs

Cancel có thể làm job dừng giữa batch. Xác định checkpoint và khả năng resume/idempotency.

### 30.3. Reporting

Một report có thể được retry an toàn hơn transaction ghi, nhưng vẫn có thể đang giữ snapshot/locks hoặc tiêu thụ I/O đáng kể.

### 30.4. External side effects

Nếu function/extension gọi API, gửi message hoặc ghi file, rollback PostgreSQL không nhất thiết hoàn tác side effect ngoài database.

## 31. Tác động tới WAL, vacuum và storage

Query cancellation không xóa WAL đã được tạo trước đó.

### 31.1. DML đã chạy một phần

Trong transaction rollback, thay đổi chưa commit không trở thành dữ liệu visible. WAL đã ghi vẫn là một phần lịch sử vật lý; PostgreSQL không xóa các WAL records chỉ vì transaction abort.

### 31.2. Dead tuples

Các tuple được tạo bởi transaction abort có thể cần vacuum cleanup sau này. Theo dõi dead tuples và autovacuum nếu workload lớn.

### 31.3. Replication

WAL của aborted transactions vẫn có thể được xử lý bởi physical replication/recovery. Logical replication không phát transaction đã rollback như một committed change set.

### 31.4. Không dùng terminate để giảm WAL directory

Terminating backend không phải phương pháp dọn WAL/slot retention. Tìm nguyên nhân WAL growth riêng.

## 32. Tác động tới replication và background processes

Một backend hiển thị trong pg_stat_activity có thể là WAL sender, logical replication worker hoặc background worker.

### 32.1. Không terminate replication process tùy tiện

Terminating walsender/receiver hoặc logical apply worker có thể làm replication disconnect/lag, giữ WAL và ảnh hưởng HA/CDC.

### 32.2. Dùng đúng runbook

Nếu replication bị lỗi, kiểm tra pg_stat_replication, pg_stat_wal_receiver, pg_stat_subscription và logs. Dùng cơ chế quản trị replication phù hợp.

### 32.3. Autovacuum

Không cancel autovacuum để giải phóng CPU một cách phản xạ. Hiểu table bloat và XID age trước.

### 32.4. Background workers

Chỉ can thiệp khi biết extension/service sở hữu worker và có quy trình stop/restart chính thức.

## 33. Permission, RLS và thông tin query

Quyền đọc statistics và quyền signal backend là hai vấn đề riêng.

### 33.1. Đọc pg_stat_activity

Role có thể thấy một phần thông tin nhưng không xem query text/details của sessions khác nếu thiếu quyền stats phù hợp.

### 33.2. Signal permission

pg_signal_backend cho phép signal backend trong phạm vi quyền được tài liệu hóa. Nó không cấp quyền superuser.

### 33.3. RLS không phải cơ chế bảo vệ pg_stat_activity

Row-level security trên application tables không thay quyền quản trị process. Bảo vệ monitoring/admin roles riêng.

### 33.4. Query text có thể nhạy cảm

Không copy raw query text chứa literals/PII/secrets vào incident ticket công khai. Redact trước khi chia sẻ.

## 34. Audit hành động cancel/terminate

Mỗi lần can thiệp nên ghi:
- Thời điểm.
- Người thực hiện/automation identity.
- Cluster/database.
- PID và backend_start.
- User/application_name/client.
- Query/transaction context đã được redacted.
- Lý do và incident/change ID.
- Action: cancel hay terminate.
- Function result.
- Trạng thái sau action.
- Locks/latency/error impact.
- Owner đã được thông báo theo quy trình.

### 34.1. Log PostgreSQL

Cấu hình log_line_prefix với PID, user, database, application_name và timestamp để liên kết logs. log_min_error_statement/log_lock_waits hỗ trợ điều tra theo policy.

### 34.2. Admin audit

Không giả định mọi lời gọi function quản trị được ghi đầy đủ vào server logs với cấu hình mặc định. Ghi audit ở hệ thống vận hành hoặc cơ chế audit đã được phê duyệt.

### 34.3. Tránh log quá rộng

Logging toàn bộ statement/parameters có thể tăng volume và lộ dữ liệu. Chỉ thu thập context cần thiết.

### 34.4. Before/after evidence

Lưu snapshot trước action và xác minh sau action. Điều này giúp đánh giá hiệu quả và điều tra nếu impact bất ngờ.

## 35. Quy trình quyết định: cancel hay terminate?

Một cây quyết định:

```text
1. Is the target a client backend?
       |
       +-- No -> Use owner-specific runbook
       |
       +-- Yes
             |
2. Is a query currently active?
       |
       +-- Yes
       |     |
       |     +-- Query itself is harmful?
       |            |
       |            +-- Yes -> Consider CANCEL
       |            |
       |            +-- No  -> Find blocker/resource cause
       |
       +-- No
             |
3. Is session idle in open transaction?
       |
       +-- Yes -> Ask/allow rollback; terminate if policy requires
       |
       +-- No -> Check pool/connection ownership
             
4. After CANCEL:
       |
       +-- Query stopped and transaction closed -> Verify
       |
       +-- Transaction aborted but still open -> ROLLBACK or TERMINATE
```

### 35.1. Cancel là bước đầu cho active statement

Nếu một query cụ thể gây hại, cancel thường có blast radius nhỏ hơn.

### 35.2. Terminate khi session là vấn đề

Session idle in transaction, không rollback hoặc không thể tiếp tục cleanup có thể cần terminate.

### 35.3. Phối hợp owner khi business impact lớn

Migration, batch ghi lớn hoặc giao dịch quan trọng cần owner/runbook rõ ràng.

### 35.4. Có stop condition

Nếu không xác định được PID/owner/transaction hoặc chưa hiểu commit state, không thực hiện hành động diện rộng. Thu thập thêm evidence.

## 36. Runbook: hủy query chạy quá lâu

1. Ghi incident ID và user impact.
2. Lấy pg_stat_activity snapshot.
3. Xác định PID, backend_start, database, user, application_name.
4. Xem query_start, xact_start, wait_event và query text đã redacted.
5. Kiểm tra pg_blocking_pids để phân biệt query chậm và blocked query.
6. Xác định query có phải batch/report/migration hợp lệ không.
7. Thông báo owner theo policy.
8. Gọi pg_cancel_backend cho đúng PID.
9. Kiểm tra function result và refresh pg_stat_activity.
10. Nếu session còn explicit transaction aborted, yêu cầu client rollback.
11. Nếu session tiếp tục giữ locks và không cleanup, đánh giá terminate.
12. Xác minh waiters, API latency, error rate và pool health.
13. Ghi action/result và corrective action.

### 36.1. Không chỉ dựa trên query age

Một query 10 phút có thể bình thường; một query 2 giây có thể block critical write path. Ưu tiên impact.

### 36.2. Theo dõi query sau cancel

Nếu query vẫn active, signal có thể chưa được xử lý hoặc PID/state đã thay đổi. Reinspect trước khi lặp action.

### 36.3. Retry application

Xác nhận retry không tạo duplicate writes hoặc retry storm.

## 37. Runbook: blocker idle in transaction

1. Tìm sessions idle in transaction và age.
2. Xem application_name, user, client_addr và xact_start.
3. Xác định locks/blocked sessions bằng pg_blocking_pids.
4. Tìm root blocker và transaction owner.
5. Liên hệ application/service owner theo incident process.
6. Nếu client có thể rollback nhanh, yêu cầu cleanup.
7. Nếu không thể và impact vượt ngưỡng, terminate đúng session.
8. Xác nhận backend biến mất và waiters được giải phóng.
9. Kiểm tra transaction rollback/commit ambiguity.
10. Theo dõi vacuum, dead tuples và pool reconnect.
11. Sửa application transaction lifecycle và thêm timeout guardrail.

### 37.1. Vì sao cancel không đủ?

Session idle không có active query; vấn đề nằm ở transaction mở. Terminate hoặc client rollback mới kết thúc transaction.

### 37.2. Đừng terminate cả application

Chỉ target PID đã xác minh. Terminate mọi sessions của service có thể làm outage rộng.

## 38. Runbook: cancel không giải quyết được lock contention

1. Lấy blocked/blocker mapping.
2. Xác định root blocker.
3. Kiểm tra blocker active hay idle in transaction.
4. Xem blocker transaction age và business operation.
5. Kiểm tra DDL/migration/maintenance.
6. Nếu active harmful query, cancel blocker query.
7. Kiểm tra transaction state và locks.
8. Nếu transaction còn mở, yêu cầu rollback hoặc terminate theo policy.
9. Xác nhận blocked sessions tiến triển.
10. Giảm retry/concurrency nếu queue vẫn tăng.
11. Sửa lock ordering, transaction duration hoặc migration strategy.

## 39. Runbook: connection bị terminate và client không rõ COMMIT outcome

1. Ghi request/business operation ID.
2. Kiểm tra application log quanh thời điểm COMMIT.
3. Xác định server/backend và incident timeline.
4. Kiểm tra connection termination logs.
5. Trên primary hiện tại, truy vấn idempotency/deduplication record.
6. Nếu record tồn tại, trả lại kết quả đã commit.
7. Nếu không tồn tại, đánh giá retry theo business semantics.
8. Dùng cùng idempotency key khi retry.
9. Kiểm tra external side effects/outbox.
10. Ghi kết quả reconcile và thông báo client/service owner.

### 39.1. Không retry non-idempotent write một cách mù quáng

Client connection error không chứng minh transaction rollback.

### 39.2. Dùng durable business key

Một unique operation key giúp xác định operation đã được commit hay chưa.

### 39.3. Failover thêm yếu tố timeline

Nếu terminate đi cùng failover, xác minh transaction có tồn tại trên promoted primary và history đã được reconcile.

## 40. Thiết kế timeout mặc định theo workload

Ví dụ policy minh họa:

| Workload | statement_timeout | lock_timeout | Ghi chú |
|---|---:|---:|---|
| OLTP read | 2–5 s | 500 ms–1 s | Endpoint latency ngắn |
| OLTP write | 5–15 s | 1–2 s | Theo business transaction |
| Reporting | 1–5 min | 2–5 s | Pool/concurrency riêng |
| Batch | Theo job SLA | Theo migration/job | Có checkpoint/resume |
| DDL migration | Theo operation | Thường ngắn để fail fast | Kế hoạch lock riêng |

Đây là giá trị minh họa, không phải cấu hình mặc định phù hợp mọi hệ thống.

### 40.1. Đặt theo role hoặc transaction

Role-specific defaults giúp phân tách workload. SET LOCAL phù hợp cho request/job có budget riêng.

### 40.2. Cân nhắc application timeout

Application deadline nên phối hợp với database timeout để tránh client bỏ request trong khi server vẫn chạy.

### 40.3. Retry policy

Timeout/retry cần backoff, jitter, maximum attempts và idempotency.

### 40.4. Review theo metrics

Điều chỉnh dựa trên timeout rate, p95/p99, lock waits và business completion rate.

## 41. Monitoring cho cancellation và termination

Nên thu thập:
- Số query cancel theo thời gian.
- Số session terminate theo thời gian.
- Cancel/terminate theo application_name/workload class.
- SQLSTATE 57014 count.
- Connection failures/reconnect rate.
- Idle-in-transaction sessions và age.
- Lock waiters/blocker age.
- Query timeout rate.
- Transaction rollback/error rate.
- Pool acquire wait và connection churn.
- Request retry rate và idempotency conflicts.

### 41.1. Không phải tất cả counters đều có built-in view

Một số sự kiện cần thu thập từ application, logs hoặc audit layer. Không giả định pg_stat_database có counter tổng cho mọi backend cancellation.

### 41.2. Cancellation rate cao

Có thể cho biết timeout quá thấp, query regression, lock contention hoặc retry behavior sai.

### 41.3. Termination rate cao

Có thể phản ánh application transaction leak, session management lỗi hoặc operational process phải can thiệp thường xuyên.

### 41.4. Theo dõi user impact

Đặt cancel/terminate counts cạnh request success, latency, TPS và pool metrics.

## 42. Logging hỗ trợ điều tra

Các cấu hình/logging liên quan:
- log_line_prefix.
- log_min_duration_statement.
- log_min_error_statement.
- log_lock_waits.
- deadlock_timeout.
- application_name.

### 42.1. log_line_prefix

Nên có PID, user, database, application_name, client address và timestamp theo policy để nối log với pg_stat_activity.

### 42.2. log_lock_waits

Ghi nhận lock waits vượt ngưỡng deadlock_timeout theo cấu hình, hữu ích để tìm contention kéo dài.

### 42.3. Slow statement logs

log_min_duration_statement giúp ghi query vượt ngưỡng. Đặt threshold theo workload và bảo vệ query text.

### 42.4. Không bật log_statement = all tùy tiện

Logging mọi câu lệnh có thể tăng volume và lộ literals/secrets. Dùng mức logging có mục tiêu.

## 43. Những tình huống không nên terminate ngay

- PID thuộc superuser/DBA đang xử lý incident.
- Backend là autovacuum hoặc replication process chưa hiểu rõ.
- Query là migration đang giữ lock nhưng gần hoàn tất và có plan.
- Transaction ghi quan trọng có thể gây commit ambiguity.
- Không xác định được owner/application.
- PID được lấy từ snapshot cũ.
- Chưa xác minh đây là root blocker.
- Chưa đánh giá tác động của rollback hoặc external side effects.
- Session đang thực hiện maintenance cần progress/cleanup.
- Có nguy cơ terminate đồng loạt làm connection pool reconnect storm.

### 43.1. Tạm dừng để thu thập evidence

Một phút kiểm tra PID, owner và transaction state có thể tránh một outage lớn hơn.

### 43.2. Dùng cancel khi phù hợp

Nếu chỉ cần dừng statement, cancel thường có blast radius thấp hơn terminate.

### 43.3. Terminate có chủ đích

Ghi rõ lý do, target, expected rollback và cách verify.

## 44. Các lỗi vận hành phổ biến

1. **Cancel query nhưng quên transaction vẫn aborted.** Client cần rollback.
2. **Cancel idle-in-transaction session.** Không có query active; transaction vẫn mở.
3. **Cho rằng cancel luôn giải phóng locks.** Transaction-level locks có thể còn tới rollback.
4. **Terminate nhầm PID từ dashboard cũ.** PID có thể đã biến mất hoặc được tái sử dụng.
5. **Chọn waiter thay vì blocker.** Lock contention không được giải quyết.
6. **Terminate mọi sessions của application.** Blast radius quá rộng.
7. **Không xác minh query đã dừng.** Boolean true chỉ báo signal được gửi.
8. **Retry ngay sau cancellation.** Có thể tạo retry storm.
9. **Không xử lý commit ambiguity.** Có thể tạo duplicate business operations.
10. **Không kiểm tra external side effects.** Rollback database không undo hệ thống ngoài.
11. **Terminate replication worker.** Có thể làm replication lag/WAL retention tăng.
12. **Kill autovacuum để giảm CPU.** Có thể làm bloat/XID risk nặng hơn.
13. **Không đặt statement_timeout.** Query runaway có thể tiếp tục lặp.
14. **Dùng lock_timeout như tổng query timeout.** Nó chỉ giới hạn lock waiting.
15. **Đặt idle_session_timeout quá thấp với pool.** Tạo connection churn.
16. **Không audit admin actions.** Khó giải thích incident và trách nhiệm.
17. **Không redacted query text.** Có thể lộ dữ liệu nhạy cảm.
18. **Không kiểm tra index validity sau cancel concurrent index build.** Có thể để lại invalid index.
19. **Không theo dõi pool health sau terminate.** Application có thể tiếp tục lỗi.
20. **Coi terminate là cách dọn WAL.** Nó không giải quyết slot/archive retention.

## 45. Ví dụ thực hành: điều tra một blocker

Giả sử API orders tăng latency. Nhiều requests đang chờ Lock.

Bước 1: tìm waiters.

```sql
SELECT
    pid,
    application_name,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

Bước 2: tìm blocker sessions và transaction age.

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS xact_age,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid = 12345;
```

Bước 3: xác định blocker là active hay idle in transaction. Nếu active, cân nhắc cancel statement. Nếu idle in transaction, phối hợp application rollback hoặc terminate theo incident policy.

Bước 4: xác minh:
- Backend đã kết thúc/rollback chưa?
- Blocked sessions có tiến triển không?
- API p95/error rate có phục hồi không?
- Pool có reconnect storm không?
- Có batch/job cần resume không?

Không chọn action chỉ dựa trên một con số query age.

## 46. Ví dụ thực hành: cancel một query report

Một reporting query đang external sort 30 GB temp data và làm volume dùng chung với OLTP gần đầy.

1. Xác định PID, application_name và owner.
2. Kiểm tra temp filesystem free space và query plan/logs.
3. Xác định query có thể restart/resume hay không.
4. Kiểm tra nó có nằm trong explicit transaction không.
5. Thông báo owner và ghi incident context.
6. Gửi pg_cancel_backend.
7. Kiểm tra statement dừng và transaction state.
8. Nếu session aborted/idle in transaction, yêu cầu rollback.
9. Xác minh temp files được cleanup và disk headroom phục hồi.
10. Giới hạn reporting concurrency và sửa query/job.

### 46.1. Temp file cleanup

Temporary files liên quan tới query thường được cleanup khi executor/backend xử lý kết thúc phù hợp. Xác minh filesystem và logs; không xóa file thủ công trong pgsql_tmp khi server còn hoạt động.

### 46.2. Nếu cancel không dừng

Reinspect process/state, đừng gửi lặp vô hạn. Nếu session tiếp tục gây hại, cân nhắc terminate có kiểm soát.

### 46.3. Sau incident

Đặt job concurrency, statement timeout/temp capacity và query optimization plan.

## 47. Bài tập thực hành có đáp án

### Bài 1. pg_cancel_backend làm gì?

**Đáp án:** Gửi tín hiệu yêu cầu backend hủy query đang chạy.

### Bài 2. pg_terminate_backend làm gì?

**Đáp án:** Gửi tín hiệu kết thúc backend session, đóng connection và rollback transaction chưa commit khi backend kết thúc.

### Bài 3. Cancel có đóng connection không?

**Đáp án:** Thông thường không. Connection có thể tiếp tục sử dụng sau khi transaction state được xử lý.

### Bài 4. Terminate có giữ connection không?

**Đáp án:** Không. Backend session kết thúc và connection bị đóng.

### Bài 5. Boolean true của pg_cancel_backend có nghĩa query đã dừng?

**Đáp án:** Không. Nó cho biết tín hiệu cancel đã được gửi; phải kiểm tra lại backend.

### Bài 6. SQLSTATE thường gặp khi query bị cancel?

**Đáp án:** 57014, query_canceled.

### Bài 7. Query cancellation trong explicit transaction có thể gây gì?

**Đáp án:** Transaction chuyển sang aborted state và cần ROLLBACK hoặc xử lý qua savepoint.

### Bài 8. Error 25P02 có nghĩa gì?

**Đáp án:** Current transaction is aborted; commands bị bỏ qua cho tới khi transaction block kết thúc.

### Bài 9. Cancel query có luôn giải phóng transaction locks?

**Đáp án:** Không. Locks có thể còn tới khi transaction rollback/kết thúc.

### Bài 10. Session idle in transaction có query active không?

**Đáp án:** Không nhất thiết. Session đang chờ client nhưng transaction vẫn mở.

### Bài 11. pg_cancel_backend có giải quyết idle in transaction không?

**Đáp án:** Không có statement active để cancel; cần rollback từ client hoặc terminate theo policy.

### Bài 12. Terminate session giải phóng locks khi nào?

**Đáp án:** Khi backend/transaction kết thúc và cleanup hoàn tất.

### Bài 13. Transaction đã commit trước terminate có bị rollback?

**Đáp án:** Không. Chỉ phần chưa commit của session bị rollback.

### Bài 14. Client mất connection lúc COMMIT có biết outcome chắc chắn không?

**Đáp án:** Không. Có thể commit outcome ambiguous; cần reconcile bằng idempotency/business key.

### Bài 15. pg_stat_activity dùng để làm gì?

**Đáp án:** Quan sát backend sessions, query, state, transaction age và wait events.

### Bài 16. query_start và xact_start khác gì?

**Đáp án:** query_start là lúc statement hiện tại bắt đầu; xact_start là lúc transaction bắt đầu.

### Bài 17. wait_event_type = Lock gợi ý gì?

**Đáp án:** Backend đang chờ lock, cần tìm blocker.

### Bài 18. pg_blocking_pids dùng để làm gì?

**Đáp án:** Trả về PID của sessions đang block backend được chỉ định.

### Bài 19. Vì sao nên cancel blocker thay vì waiter?

**Đáp án:** Waiter chỉ là nạn nhân; blocker giữ lock gây ảnh hưởng cho nhiều sessions.

### Bài 20. Nếu blocker idle in transaction thì xử lý thế nào?

**Đáp án:** Yêu cầu client rollback hoặc terminate session sau khi xác minh owner/impact.

### Bài 21. Backend PID có thể được tái sử dụng không?

**Đáp án:** Có. Kiểm tra lại PID cùng backend_start/application/user trước action.

### Bài 22. Vì sao loại trừ pg_backend_pid()?

**Đáp án:** Tránh gửi tín hiệu tới chính session đang chạy lệnh quản trị.

### Bài 23. Role nào hỗ trợ signal backend theo quyền được cấp?

**Đáp án:** Predefined role pg_signal_backend trong phạm vi không vượt quyền superuser restrictions.

### Bài 24. pg_signal_backend có thể signal superuser backend?

**Đáp án:** Không; chỉ superuser mới được signal backend thuộc superuser.

### Bài 25. Query cancel có thể bị xử lý chậm vì sao?

**Đáp án:** Backend xử lý tín hiệu tại interrupt points; có thể chưa tới điểm kiểm tra ngay.

### Bài 26. Terminate một parallel worker riêng có phải cách chuẩn?

**Đáp án:** Không. Xác định client/leader session sở hữu query và dùng runbook phù hợp.

### Bài 27. CREATE INDEX CONCURRENTLY bị cancel có thể để lại gì?

**Đáp án:** Có thể để lại index invalid; kiểm tra pg_index.indisvalid/indisready.

### Bài 28. Có nên terminate autovacuum để giảm CPU?

**Đáp án:** Không theo phản xạ; đánh giá table health, XID age và maintenance impact trước.

### Bài 29. statement_timeout giới hạn gì?

**Đáp án:** Tổng thời gian thực thi statement, bao gồm cả thời gian chờ lock.

### Bài 30. lock_timeout giới hạn gì?

**Đáp án:** Thời gian một statement chờ để acquire lock.

### Bài 31. lock_timeout có thay statement_timeout không?

**Đáp án:** Không. Nó không giới hạn phần query chạy sau khi lock đã được lấy.

### Bài 32. idle_in_transaction_session_timeout làm gì?

**Đáp án:** Kết thúc session idle trong transaction vượt ngưỡng, giải phóng transaction resources.

### Bài 33. idle_session_timeout có rủi ro với pool không?

**Đáp án:** Có. Nó có thể gây stale connections và connection churn nếu pool không phối hợp timeout.

### Bài 34. SET LOCAL có phạm vi nào?

**Đáp án:** Transaction hiện tại; tự hết hiệu lực khi COMMIT/ROLLBACK.

### Bài 35. pg_terminate_backend timeout argument có ở mọi version?

**Đáp án:** Không. Overload có timeout chỉ có ở các version hỗ trợ; kiểm tra function signature trước.

### Bài 36. Terminate có rollback external HTTP request không?

**Đáp án:** Không. Side effects bên ngoài database không tự rollback theo transaction.

### Bài 37. Cancel một query DML đã ghi một phần có thể để lại dữ liệu commit một phần?

**Đáp án:** Trong một transaction statement atomic, statement bị hủy sẽ rollback thay đổi chưa commit; external side effects vẫn cần xem riêng.

### Bài 38. Cancel có xóa WAL đã ghi không?

**Đáp án:** Không. WAL records đã được ghi không bị xóa chỉ vì transaction abort.

### Bài 39. Vì sao cần theo dõi pool sau terminate?

**Đáp án:** Pool phải loại connection và reconnect; nhiều terminate có thể tạo connection storm.

### Bài 40. Vì sao không retry ngay sau cancellation?

**Đáp án:** Có thể tạo retry storm và lặp lại nguyên nhân lock/resource contention.

### Bài 41. Query age 10 phút có luôn phải cancel?

**Đáp án:** Không. Cần xét workload class, owner, wait event và user impact.

### Bài 42. Khi nào terminate hợp lý hơn cancel?

**Đáp án:** Khi session không rollback, idle in transaction giữ locks hoặc cần kết thúc toàn bộ session theo policy.

### Bài 43. Cần audit những gì khi terminate?

**Đáp án:** Người thực hiện, PID/backend identity, owner, lý do, incident ID, action result và tác động sau đó.

### Bài 44. pg_stat_activity có hiển thị mọi query text cho mọi user?

**Đáp án:** Không. Quyền statistics có thể giới hạn thông tin chi tiết.

### Bài 45. log_lock_waits giúp gì?

**Đáp án:** Ghi log các lock waits vượt ngưỡng cấu hình, hỗ trợ điều tra contention.

### Bài 46. Cancel query report có thể ảnh hưởng temp files không?

**Đáp án:** Có. Temporary files của query thường được cleanup khi executor/backend xử lý kết thúc; phải xác minh disk state.

### Bài 47. Nếu cancel xong session ở idle in transaction (aborted), bước tiếp theo?

**Đáp án:** Yêu cầu client ROLLBACK; nếu không cleanup và tiếp tục gây hại, đánh giá terminate.

### Bài 48. Làm sao xử lý commit ambiguity sau connection loss?

**Đáp án:** Tra idempotency/business operation key trên primary hiện tại, reconcile rồi mới quyết định retry.

### Bài 49. Một cancellation dashboard nên có gì?

**Đáp án:** Cancel/terminate counts, SQLSTATE 57014, connection failures, idle transaction age, lock waiters, pool wait, retries và user latency.

### Bài 50. Khi nào incident được coi là đã xử lý?

**Đáp án:** Query/session mục tiêu đã được xử lý, locks được giải phóng, ứng dụng/pool ổn định, latency/errors phục hồi và action được audit.

## 48. Checklist trước và sau khi can thiệp

| Giai đoạn | Câu hỏi |
|---|---|
| Target | PID có đúng backend và còn tồn tại? |
| Identity | User, database, application_name, client_addr đúng? |
| State | Active, idle, idle in transaction hay aborted? |
| Age | Query age và transaction age bao lâu? |
| Wait | Đang chờ Lock, IO hay resource khác? |
| Blocking | Đây là blocker hay waiter? |
| Owner | Service/job/migration owner là ai? |
| Business | Có transaction quan trọng hoặc external side effects? |
| Action | Cancel statement hay terminate session? |
| Permission | Role có quyền signal đúng backend? |
| Transaction | Sau cancel có cần ROLLBACK? |
| Locks | Blocked sessions đã tiến triển? |
| Pool | Connection bị loại/reconnect đúng? |
| Retry | Có backoff/idempotency? |
| Logs | SQLSTATE, PID và incident context đã lưu? |
| DDL | Index/migration state có cần kiểm tra? |
| Replication | Có vô tình ảnh hưởng worker/slot/replica? |
| Impact | Latency, errors, TPS, pool wait có phục hồi? |
| Audit | Operator, lý do và outcome đã ghi? |
| Prevention | Timeout/transaction lifecycle có cần sửa? |
| Closure | Business operation/commit outcome đã reconcile? |

## 49. Tài liệu PostgreSQL chính thức

- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — pg_cancel_backend, pg_terminate_backend và backend signaling.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html) — pg_stat_activity và activity monitoring.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — session state, wait events và statistics views.
- [Predefined Roles](https://www.postgresql.org/docs/current/predefined-roles.html) — pg_signal_backend và monitoring roles.
- [Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) — statement_timeout, lock_timeout và idle transaction/session timeouts.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes và lock lifetime.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — transaction behavior và snapshots.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — concurrent index build behavior và invalid indexes.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — progress views cho vacuum/index operations.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — SQLSTATE 57014 và transaction errors.

Function signatures, pg_stat_activity columns, timeout parameters và progress views có thể thay đổi theo PostgreSQL major version. Trước khi chuẩn hóa runbook, kiểm tra server_version, function signatures, pg_settings và tài liệu đúng phiên bản đang vận hành.

## 50. Tổng kết: xác định đúng backend, chọn đúng tín hiệu, kiểm tra tác động

```text
pg_stat_activity
    |
    v
Identify PID + owner + state + query + xact age
    |
    v
Find blockers / wait events / business impact
    |
    +------------------------------+
    |                              |
    v                              v
Active harmful query         Idle in transaction
    |                              |
    v                              v
pg_cancel_backend           Client ROLLBACK
    |                       or controlled terminate
    v                              |
Check query stopped                |
    |                              |
    v                              v
Check transaction state and lock release
    |
    v
Verify application, pool, latency, errors and audit
```

Những nguyên tắc cần nhớ:

1. **pg_cancel_backend hủy statement; pg_terminate_backend kết thúc session.** Hai hành động có blast radius khác nhau.
2. **Boolean true không chứng minh query/session đã hoàn tất cleanup.** Kiểm tra lại pg_stat_activity và logs.
3. **Cancel trong explicit transaction có thể để transaction ở trạng thái aborted.** Client cần ROLLBACK.
4. **Locks có thể còn giữ sau query cancellation.** Transaction phải kết thúc mới giải phóng transaction-level locks.
5. **Idle in transaction không có query active để cancel.** Xử lý transaction/session theo owner và policy.
6. **Terminate rollback phần chưa commit và đóng connection.** Client phải reconnect và có thể cần reconcile commit outcome.
7. **Xác định blocker trước khi cancel waiter.** Xử lý đúng root cause giúp phục hồi nhiều requests cùng lúc.
8. **PID cần được xác minh ngay trước action.** Kết hợp backend_start, application_name, user và database.
9. **Không terminate background/replication/maintenance processes theo phản xạ.** Dùng runbook riêng.
10. **Timeouts phòng ngừa sự cố tốt hơn can thiệp thủ công lặp lại.** Chọn statement_timeout, lock_timeout và idle transaction timeout theo workload.
11. **Retry phải có backoff và idempotency.** Tránh tạo duplicate operations hoặc retry storm.
12. **Audit và kiểm tra sau hành động là bắt buộc trong vận hành.** Đánh giá locks, pool, latency, errors và business outcome.

**Một câu để nhớ:** *Hủy query để dừng một statement; kết thúc session để dừng toàn bộ backend và transaction chưa commit; trước khi chọn, hãy xác định blocker, transaction state và hậu quả đối với ứng dụng.*

