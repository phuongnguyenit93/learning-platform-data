# Tra cứu session, giao dịch và tác vụ nền trong PostgreSQL

Quản trị PostgreSQL thường bắt đầu bằng câu hỏi: **đang có những process nào kết nối tới server, chúng đang làm gì, transaction nào còn mở và tác vụ nền nào đang chạy?** Câu trả lời nằm ở các system views, đặc biệt là **pg_stat_activity**, kết hợp với lock views, transaction catalogs, progress views và statistics của replication, WAL, autovacuum, checkpoint.

Cần phân biệt ba khái niệm:

- **Session** là kết nối/phiên làm việc giữa client và PostgreSQL backend. Một session có thể chạy nhiều câu lệnh trong suốt vòng đời.
- **Transaction** là đơn vị công việc có ranh giới BEGIN/COMMIT/ROLLBACK. Một session có thể có transaction đang chạy, đang mở nhưng idle, hoặc không có transaction.
- **Background task/process** là process do PostgreSQL hoặc công cụ bên ngoài tạo để thực hiện công việc như autovacuum, checkpoint, WAL writing, replication, parallel query hoặc scheduled job.

Một session có thể ở trạng thái idle nhưng vẫn giữ transaction mở. Một query có thể đang active nhưng thực tế chờ lock hoặc I/O. Một transaction đã được PREPARE có thể vẫn tồn tại sau khi session ban đầu ngắt kết nối. Vì vậy, tra cứu session chỉ là bước đầu; cần đọc state, timestamps, wait events, locks và loại backend cùng nhau.

~~~text
                     PostgreSQL server
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
          Client          Transaction   Background
          sessions        state         processes
              |             |             |
              v             v             v
       pg_stat_activity  xact_start   backend_type
              |             |             |
              +-------------+-------------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
           Locks         Progress       Replication /
         pg_locks       pg_stat_progress  WAL / vacuum
              |             |             |
              +-------------+-------------+
                            |
                            v
                 Diagnosis and safe action
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Quản trị**, với đề tài **“Tra cứu session, giao dịch và tác vụ nền”**. Nội dung đi từ cách đọc pg_stat_activity tới phân tích transaction age, lock blockers, prepared transactions, background workers, progress views, quyền monitoring và các thao tác quản trị an toàn.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt session, backend process, statement và transaction.
2. Giải thích vai trò của pg_stat_activity.
3. Đọc các cột PID, user, database, application_name, client_addr và backend_type.
4. Phân biệt active, idle, idle in transaction và idle in transaction (aborted).
5. Phân biệt query_start, xact_start, backend_start và state_change.
6. Tìm session đang chạy query lâu.
7. Tìm transaction mở lâu dù session đang idle.
8. Đọc wait_event_type và wait_event.
9. Tìm blocked sessions và blocking sessions bằng pg_blocking_pids.
10. Dùng pg_locks để điều tra lock modes và lock ownership.
11. Nhận biết transaction giữ snapshot và ảnh hưởng tới vacuum.
12. Tra cứu prepared transactions không còn gắn với session đang kết nối.
13. Phân biệt client backend với autovacuum, checkpointer, WAL và replication workers.
14. Theo dõi vacuum, CREATE INDEX, COPY và base backup bằng progress views.
15. Tra cứu replication sender/receiver và logical replication workers.
16. Nhận biết scheduled jobs chạy trong PostgreSQL và jobs chạy bên ngoài database.
17. Hiểu giới hạn của statistics snapshots và query text visibility.
18. Cấp quyền monitoring theo nguyên tắc least privilege.
19. Phân biệt pg_cancel_backend và pg_terminate_backend.
20. Xây dựng quy trình điều tra session/transaction trước khi can thiệp.
21. Theo dõi connection pool, long-running transactions và backend capacity.
22. Thiết kế dashboard và runbook quản trị session.
23. Thực hành tìm blocker, quan sát background work và xử lý session trong lab.
24. Tránh kết thúc nhầm session quan trọng hoặc làm gián đoạn tác vụ bảo trì.

**Phạm vi:** PostgreSQL hiện đại. Một số cột như backend_type, leader_pid, query_id và các progress/statistics views phụ thuộc major version. Trước khi triển khai query monitoring trên nhiều version, kiểm tra schema thực tế của server. Các thao tác cancel/terminate trong bài chỉ thực hiện trên session đã xác minh và theo quyền vận hành.

---

## 2. Session, backend, statement và transaction

Bốn khái niệm này có quan hệ với nhau nhưng không đồng nghĩa.

### 2.1. Session

Session là phiên kết nối của một client tới PostgreSQL. Trong cấu hình thông thường, một client connection được phục vụ bởi một backend process. Session tồn tại từ lúc kết nối thành công tới lúc disconnect hoặc bị terminate.

Session có thể:
- Chờ client gửi query.
- Chạy một statement.
- Chờ lock hoặc I/O.
- Đang ở trong transaction.
- Idle sau khi hoàn tất transaction.
- Bị ngắt do network, timeout hoặc thao tác quản trị.

### 2.2. Backend process

Backend là process PostgreSQL thực hiện công việc cho session hoặc một nhiệm vụ nội bộ. PostgreSQL còn có các process không đại diện cho client session, chẳng hạn checkpointer, background writer, WAL writer, autovacuum launcher và worker.

Trong pg_stat_activity, các loại process có thể được phân biệt qua backend_type trên các phiên bản hỗ trợ.

### 2.3. Statement/query

Statement là câu SQL được gửi để thực thi. Một session có thể chạy nhiều statements. Khi state là active, query thường là statement đang chạy. Khi session idle, query có thể vẫn chứa câu lệnh cuối cùng đã chạy; không được hiểu nó là query đang thực thi.

### 2.4. Transaction

Transaction bao gồm một hoặc nhiều statements và kết thúc bằng COMMIT hoặc ROLLBACK. Một session có thể giữ transaction mở dù không chạy query ở thời điểm snapshot.

Ví dụ:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

-- Client tạm dừng, chưa COMMIT hoặc ROLLBACK.
~~~

Trong khoảng dừng này, session có thể có state `idle in transaction`, nhưng transaction vẫn mở và có thể giữ locks hoặc snapshot.

### 2.5. Một session có thể có nhiều trạng thái theo thời gian

~~~text
CONNECT
   |
   v
idle
   |
   v
active query
   |
   +----> idle
   |
   +----> transaction open
               |
               +----> active query
               |
               +----> idle in transaction
               |
               +----> COMMIT / ROLLBACK
                            |
                            v
                           idle
   |
   v
DISCONNECT
~~~

### 2.6. Vì sao phải tách các khái niệm?

- Query chạy lâu có thể là vấn đề về execution hoặc wait.
- Transaction mở lâu có thể gây vacuum lag dù query hiện tại đã kết thúc.
- Session idle không nhất thiết tiêu tốn CPU, nhưng idle in transaction có thể giữ locks/snapshot.
- Background worker có thể hoạt động dù không có client query tương ứng.

---

## 3. pg_stat_activity: điểm bắt đầu để tra cứu session

pg_stat_activity cung cấp một row cho mỗi server process, gồm thông tin kết nối, trạng thái, query và wait event.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_activity;
~~~

Đây là cách khám phá nhanh schema trên server. Với dashboard hoặc runbook lâu dài, nên chọn rõ các cột cần thiết thay vì phụ thuộc SELECT *, vì schema có thể thay đổi giữa các major versions.

### 3.1. Các cột thường dùng

| Cột | Ý nghĩa |
| --- | --- |
| pid | Process ID của backend/process |
| leader_pid | PID của parallel group leader trên version hỗ trợ |
| backend_type | Loại backend/process trên version hỗ trợ |
| datname | Database đang kết nối |
| usename | Role/user của session |
| application_name | Tên ứng dụng gửi trong connection |
| client_addr | Địa chỉ client, có thể NULL với process nội bộ hoặc Unix socket |
| client_port | Port client nếu có |
| backend_start | Thời điểm backend bắt đầu |
| xact_start | Thời điểm transaction hiện tại bắt đầu |
| query_start | Thời điểm query hiện tại bắt đầu nếu active |
| state_change | Thời điểm state thay đổi gần nhất |
| state | Trạng thái session/process |
| wait_event_type | Nhóm sự kiện đang chờ |
| wait_event | Sự kiện cụ thể đang chờ |
| backend_xid | Transaction ID đã cấp cho backend nếu có |
| backend_xmin | Oldest xmin snapshot mà backend đang giữ nếu có |
| query_id | Query identifier trên version/cấu hình hỗ trợ |
| query | Query text hiện tại hoặc query gần nhất tùy state |

### 3.2. PID không phải định danh bền vững

PID có thể được tái sử dụng sau khi process kết thúc. Khi ghi incident hoặc chuẩn bị terminate, nên ghi thêm backend_start, user, database, application_name và query sample để tránh nhầm session.

### 3.3. application_name rất hữu ích

Đặt application_name theo service hoặc job role giúp phân biệt:
- API service.
- Background worker.
- Migration tool.
- Reporting service.
- Admin console.
- Replication client.

Không đặt UUID/request ID duy nhất vào application_name nếu điều đó làm monitoring cardinality tăng không kiểm soát.

### 3.4. client_addr có thể NULL

Process nội bộ, Unix-domain socket hoặc một số kết nối đặc biệt có thể không có địa chỉ TCP client. NULL không tự động có nghĩa session lỗi.

### 3.5. Query text có thể bị giới hạn quyền

User thường thấy đầy đủ query của session mình. Để xem query text và thông tin đầy đủ của sessions khác, cần quyền monitoring thích hợp như pg_read_all_stats/pg_monitor hoặc superuser theo version.

---

## 4. Liệt kê session theo database và trạng thái

### 4.1. Đếm session theo state

~~~sql
SELECT
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY state
ORDER BY sessions DESC NULLS LAST;
~~~

Kết quả giúp thấy bao nhiêu session active, idle hoặc idle in transaction.

### 4.2. Đếm theo database, user và application

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC NULLS LAST;
~~~

### 4.3. Xem session client

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    client_port,
    backend_start,
    state,
    state_change
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

Nếu server version không có backend_type, bỏ điều kiện này hoặc dùng schema phù hợp.

### 4.4. Xem session theo application_name

~~~sql
SELECT
    application_name,
    count(*) AS total_sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_transaction_sessions
FROM pg_catalog.pg_stat_activity
GROUP BY application_name
ORDER BY total_sessions DESC;
~~~

### 4.5. Không nhầm session count với throughput

Một session idle có thể tồn tại hàng giờ. Số session cho biết connection usage, không cho biết số queries/transactions mỗi giây.

---

## 5. Hiểu các state của session

Các state phổ biến trong pg_stat_activity:

| State | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| active | Backend đang thực thi query | Có thể đang chạy CPU hoặc đang chờ wait event |
| idle | Đang chờ client gửi query mới | Thường bình thường với connection pool |
| idle in transaction | Transaction còn mở nhưng không có query đang chạy | Có thể giữ locks/snapshot |
| idle in transaction (aborted) | Transaction đã lỗi nhưng chưa được rollback/cleanup | Client cần ROLLBACK hoặc kết thúc session |
| fastpath function call | Đang thực hiện fast-path function call trên version hỗ trợ | Thường là trạng thái ngắn |
| disabled | Statistics state tracking bị vô hiệu hóa theo cấu hình/version | Cần xem setting |

### 5.1. active không đồng nghĩa đang dùng CPU

Một backend có state active và wait_event_type='Lock' đang chạy query nhưng chờ lock. Một backend active có thể chờ IO, Client, LWLock hoặc IPC.

### 5.2. idle thường không phải vấn đề

Connection pool thường giữ một số session idle để tái sử dụng. Chỉ riêng idle session count cao chưa đủ để kết luận có leak.

### 5.3. idle in transaction cần chú ý

Session đã chạy BEGIN và chưa COMMIT/ROLLBACK. Nó có thể:
- Giữ row/table locks.
- Giữ snapshot cũ.
- Ngăn vacuum loại bỏ dead tuples.
- Làm tăng bloat.
- Làm các session khác bị block.

### 5.4. idle in transaction (aborted)

Một statement trong transaction bị lỗi, ví dụ constraint violation. Transaction đã ở trạng thái aborted nhưng session vẫn mở. Các statements tiếp theo có thể nhận lỗi cho tới khi client rollback.

### 5.5. state và wait event là hai chiều khác nhau

State mô tả backend đang hoạt động hay idle. Wait event mô tả backend đang chờ điều gì. Cần đọc cả hai để hiểu tình trạng.

---

## 6. Tra cứu query đang chạy lâu

### 6.1. Danh sách active queries

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
~~~

### 6.2. Lọc query quá ngưỡng

~~~sql
SELECT
    pid,
    application_name,
    usename,
    datname,
    clock_timestamp() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state = 'active'
  AND query_start < clock_timestamp() - interval '30 seconds'
ORDER BY query_start;
~~~

30 giây chỉ là ví dụ. Ngưỡng phù hợp phụ thuộc workload và SLO.

### 6.3. Query age khác transaction age

Một transaction có thể chạy nhiều queries. Query cuối cùng chỉ mất 10 ms nhưng transaction đã mở 30 phút. Vì vậy phải xem cả query_start và xact_start.

### 6.4. query_start khi session idle

Nếu state không phải active, query_start có thể biểu thị thời điểm query gần nhất bắt đầu, không phải query hiện đang chạy. Không dùng query_age để cảnh báo idle session như một active query.

### 6.5. query text có thể bị truncate

track_activity_query_size quyết định lượng query text được giữ trong activity view. Query rất dài có thể chỉ hiện một phần. Không giả định query sample luôn đầy đủ.

---

## 7. Tra cứu transaction mở lâu

Transaction age thường quan trọng hơn query age khi điều tra vacuum, lock và connection leaks.

### 7.1. Tìm transaction đang mở

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - query_start AS query_age,
    backend_xid,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 7.2. Tìm transaction idle lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    client_addr,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS idle_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
~~~

### 7.3. Vì sao transaction mở lâu nguy hiểm?

- Row/table locks có thể giữ tới COMMIT/ROLLBACK.
- Snapshot cũ có thể giữ lại dead tuples.
- Autovacuum có thể không reclaim được các row versions còn visible với snapshot đó.
- Transaction ID age có thể tăng.
- Connection pool mất một connection hữu ích.
- Các query khác có thể chờ blocker.

### 7.4. backend_xmin

backend_xmin thể hiện xmin horizon mà backend đang giữ, khi có. Một xmin cũ có thể cản vacuum cleanup. Không phải mọi session có transaction age lớn đều giữ xmin theo cùng cách; cần đọc trạng thái và snapshot thực tế.

### 7.5. Transaction read-only vẫn có thể ảnh hưởng vacuum

Một transaction SELECT dài có thể giữ snapshot cũ, làm các dead tuples chưa thể bị loại bỏ. Không chỉ write transactions mới gây vacuum retention.

### 7.6. Kiểm tra oldest xmin

Có thể quan sát tuổi của các backend xmin:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    age(backend_xmin) AS xmin_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 160) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
~~~

Đây là tín hiệu điều tra, không phải một phép đo duy nhất để quyết định terminate.

---

## 8. Phân biệt query age, transaction age và session age

| Tuổi | Cách tính | Câu hỏi |
| --- | --- | --- |
| Query age | current time - query_start | Query hiện tại chạy bao lâu? |
| Transaction age | current time - xact_start | Transaction mở bao lâu? |
| Session age | current time - backend_start | Connection tồn tại bao lâu? |
| State age | current time - state_change | Session ở state hiện tại bao lâu? |

### 8.1. Ví dụ

Một session được tạo 4 giờ trước, bắt đầu transaction 20 phút trước, chạy query cuối 19 phút trước và hiện idle in transaction 18 phút.

- Session age: 4 giờ.
- Transaction age: 20 phút.
- Query age: không phải active query age; đó là timestamp của query gần nhất.
- State age: 18 phút.

### 8.2. Dùng clock_timestamp trong truy vấn giám sát

now()/transaction_timestamp() cố định tại thời điểm bắt đầu transaction. Trong một transaction monitoring chạy lâu, các phép tính now() - query_start không tiếp tục tăng. clock_timestamp() trả thời gian hiện tại tại lúc hàm được gọi, phù hợp hơn cho snapshot age.

### 8.3. Không so sánh timestamps khác ý nghĩa

backend_start đo tuổi connection, query_start đo query, xact_start đo transaction. Alert cần chọn đúng mốc theo failure mode.

---

## 9. Wait events: session đang chờ gì?

Các cột wait_event_type và wait_event giúp phân biệt query đang tiêu thụ CPU với query đang chờ một tài nguyên.

### 9.1. Một số nhóm wait event

| Wait event type | Ý nghĩa tổng quát | Ví dụ điều tra |
| --- | --- | --- |
| Lock | Chờ heavyweight lock | Tìm blocking PID |
| LWLock | Chờ lightweight lock nội bộ | Điều tra contention trong shared structures |
| IO | Chờ I/O | Kiểm tra storage latency/queue |
| Client | Chờ client gửi/nhận dữ liệu | Client đọc chậm hoặc giữ connection |
| IPC | Chờ phối hợp giữa processes | Parallel query hoặc background process |
| BufferPin | Chờ buffer pin được giải phóng | Query/scan giữ buffer lâu |
| Activity | Chờ một hoạt động nội bộ | Background worker coordination |
| Timeout | Chờ timer | Timeout/retry logic |
| Extension | Chờ sự kiện do extension cung cấp | Xem extension cụ thể |

Tập wait event cụ thể phụ thuộc version và workload.

### 9.2. Đếm session theo wait events

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

### 9.3. Active nhưng đang chờ

Một query có state = 'active' và wait_event_type = 'Lock' vẫn là active query, nhưng nó đang chờ lock. Đếm active sessions như CPU-running sessions sẽ gây hiểu nhầm.

### 9.4. Chờ client

Một backend có thể chờ client đọc kết quả hoặc gửi dữ liệu. Nếu ứng dụng đọc chậm, server process có thể bị giữ lâu dù database execution đã gần xong.

### 9.5. Wait event là snapshot

Query monitoring chỉ nhìn thấy trạng thái tại thời điểm lấy snapshot. Wait ngắn có thể không xuất hiện trong poll interval; dùng logs, tracing hoặc sampling phù hợp nếu cần bắt sự kiện ngắn.

---

## 10. Tìm blocked sessions và blocking sessions

### 10.1. Dùng pg_blocking_pids

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_application,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocked.wait_event_type,
    blocked.wait_event,
    blocker.pid AS blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_application,
    blocker.state AS blocking_state,
    clock_timestamp() - blocker.xact_start AS blocking_xact_age,
    left(blocked.query, 180) AS blocked_query,
    left(blocker.query, 180) AS blocking_query
FROM pg_catalog.pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(blocked.pid)
) AS blocker_pid(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
    ON blocker.pid = blocker_pid.pid
WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocked.query_start;
~~~

### 10.2. Vì sao blocker có thể idle?

Một transaction có thể đã chạy UPDATE rồi chuyển sang idle in transaction nhưng vẫn giữ row lock. Session khác chờ lock trong khi blocker không chạy query nào tại thời điểm đó.

### 10.3. Blocker có thể chặn nhiều sessions

Một transaction blocker có thể tạo hàng loạt blocked sessions. Ưu tiên tìm root blocker thay vì xử lý từng waiter.

### 10.4. pg_blocking_pids

Hàm trả về PID của các sessions đang chặn backend được chỉ định. Nó thường là cách thuận tiện để xác định blocker trực tiếp mà không phải tự suy luận toàn bộ lock graph.

### 10.5. Prepared transactions

Prepared transactions không có backend PID đang hoạt động như session thông thường. Nếu lock bị giữ bởi prepared transaction, cần kiểm tra pg_prepared_xacts và pg_locks để xác định nguyên nhân.

---

## 11. Tra cứu lock bằng pg_locks

pg_locks hiển thị các locks mà PostgreSQL đang giữ hoặc đang chờ.

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation,
    CASE
        WHEN l.relation IS NOT NULL
        THEN l.relation::regclass::text
    END AS relation_name,
    l.transactionid,
    l.virtualxid
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY l.granted, l.pid;
~~~

### 11.1. granted

- true: lock đã được cấp.
- false: backend đang chờ lock.

### 11.2. mode

Lock mode cho biết mức xung đột/đồng thời. Không phải mọi lock đều là table lock; có row-level, transaction ID, virtual transaction và các lock nội bộ khác.

### 11.3. relation

Khi lock gắn với relation, có thể cast OID sang regclass để hiển thị tên relation. Không phải mọi lock đều có relation.

### 11.4. Row locks

Row-level locks thường được biểu diễn qua tuple metadata và transaction locks; pg_locks không nhất thiết liệt kê một row-level lock đơn giản như một row riêng cho từng tuple đang bị khóa. Dùng pg_blocking_pids và lock graph để điều tra.

### 11.5. Lock graph phức tạp

Có thể có nhiều waiter, nhiều blocker hoặc deadlock cycle. Một snapshot có thể thay đổi khi transaction commit/rollback. Thu thập thông tin nhanh và ghi timestamp.

---

## 12. Deadlock và lock timeout

### 12.1. Lock wait

Một session chờ lock vì session khác đang giữ lock xung đột. Chờ có thể kết thúc khi blocker commit/rollback.

### 12.2. Deadlock

Deadlock xảy ra khi các transactions tạo vòng chờ lẫn nhau. PostgreSQL phát hiện deadlock sau deadlock_timeout và abort một transaction để phá vòng.

### 12.3. Deadlock counter

~~~sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
~~~

Đây là counter tích lũy; lấy delta để tính deadlocks trong một khoảng thời gian.

### 12.4. log_lock_waits

Có thể bật log_lock_waits để ghi các lock waits vượt ngưỡng deadlock_timeout. Điều chỉnh theo log volume và nhu cầu điều tra.

### 12.5. lock_timeout

lock_timeout giới hạn thời gian một statement chờ lock trước khi bị hủy. Có thể đặt ở session/transaction/role/database scope tùy policy.

### 12.6. statement_timeout

statement_timeout giới hạn tổng thời gian statement. Nó bao gồm execution và waits, không chỉ lock wait.

### 12.7. Chọn timeout có chủ đích

Timeout quá thấp có thể làm workload bình thường thất bại. Timeout quá cao có thể để waiter tồn tại lâu. Chọn theo SLO và transaction semantics.

---

## 13. Prepared transactions và pg_prepared_xacts

Prepared transaction là transaction đã chạy PREPARE TRANSACTION trong two-phase commit, chờ COMMIT PREPARED hoặc ROLLBACK PREPARED.

### 13.1. Session gốc có thể đã biến mất

Sau PREPARE TRANSACTION, transaction tồn tại độc lập với session ban đầu. Vì vậy có thể không tìm thấy PID tương ứng trong pg_stat_activity.

### 13.2. Tra cứu prepared transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
~~~

### 13.3. Vì sao cần quan tâm?

Prepared transaction có thể giữ locks và làm vacuum cleanup bị trì hoãn. Nếu transaction bị bỏ quên, nó có thể ảnh hưởng lâu dài.

### 13.4. Không tự ý commit/rollback

Chỉ quyết định COMMIT PREPARED hoặc ROLLBACK PREPARED sau khi xác định transaction coordinator, distributed transaction outcome và owner. Hành động sai có thể tạo dữ liệu không nhất quán giữa các hệ thống.

### 13.5. Monitoring

Alert prepared transactions tồn tại lâu hơn ngưỡng. Ghi gid, owner, database, prepared timestamp và escalation owner.

---

## 14. Backend types và background processes

Trên các PostgreSQL version có backend_type, cột này giúp phân biệt client backends và các process nội bộ.

### 14.1. Client backend

Process phục vụ kết nối client thông thường.

### 14.2. Autovacuum launcher/worker

Launcher quản lý việc khởi chạy autovacuum workers; worker thực hiện VACUUM/ANALYZE tự động.

### 14.3. Background writer

Ghi dirty buffers theo cơ chế background writing.

### 14.4. Checkpointer

Thực hiện checkpoint và đồng bộ các pages cần thiết.

### 14.5. WAL writer

Ghi WAL buffers xuống WAL files theo lịch và điều kiện phù hợp.

### 14.6. WAL sender/receiver

WAL sender phục vụ replication clients ở primary; WAL receiver nhận WAL trên standby.

### 14.7. Parallel workers

Các worker được dùng bởi parallel query hoặc một số tác vụ song song. Có thể liên hệ leader_pid với parallel group trên version hỗ trợ.

### 14.8. Logical replication workers

Launcher và workers xử lý logical replication subscriptions, apply và các hoạt động liên quan.

### 14.9. Background workers của extension

Extensions có thể đăng ký background workers riêng. Tên/backend type và behavior phụ thuộc extension.

### 14.10. Xem process theo backend_type

~~~sql
SELECT
    backend_type,
    state,
    wait_event_type,
    wait_event,
    count(*) AS processes
FROM pg_catalog.pg_stat_activity
GROUP BY backend_type, state, wait_event_type, wait_event
ORDER BY processes DESC;
~~~

Nếu backend_type không tồn tại trong version cũ, dùng các columns có sẵn hoặc kiểm tra pg_stat_activity schema.

---

## 15. Theo dõi autovacuum

Autovacuum giúp reclaim dead tuples, cập nhật planner statistics và bảo vệ transaction ID wraparound.

### 15.1. Tìm autovacuum workers

~~~sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 240) AS task
FROM pg_catalog.pg_stat_activity
WHERE backend_type LIKE '%autovacuum%'
ORDER BY query_start;
~~~

### 15.2. Progress vacuum

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_vacuum;
~~~

View này cho biết vacuum đang ở phase nào và các counters tiến độ trên các version hỗ trợ.

### 15.3. Table vacuum history

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 15.4. Autovacuum launcher khác worker

Launcher điều phối; worker thực hiện công việc cụ thể. Không thấy worker tại một thời điểm không có nghĩa autovacuum bị tắt.

### 15.5. Vì sao vacuum chạy lâu?

- Table lớn hoặc nhiều dead tuples.
- Storage I/O chậm.
- Long-running transaction giữ xmin.
- Replication slot/standby feedback ảnh hưởng cleanup horizon.
- Autovacuum cost delay và worker capacity.
- Workload liên tục tạo updates/deletes.

### 15.6. Không terminate autovacuum tùy tiện

Dừng worker có thể khiến dead tuples tích tụ, tăng bloat và tăng rủi ro wraparound. Trước khi can thiệp, xác định table, phase, blockers, resource bottleneck và XID age.

---

## 16. Theo dõi checkpoint, background writer và WAL writer

### 16.1. Liệt kê process

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    backend_start
FROM pg_catalog.pg_stat_activity
WHERE backend_type IN (
    'background writer',
    'checkpointer',
    'walwriter'
)
ORDER BY backend_type;
~~~

Tên backend_type và process list phụ thuộc PostgreSQL version.

### 16.2. Checkpoint statistics

Ở các phiên bản hiện đại, xem pg_stat_checkpointer nếu có; trước PostgreSQL 17, nhiều checkpoint/background writer counters được đặt trong pg_stat_bgwriter.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_checkpointer;
~~~

Trên version không có view này, kiểm tra pg_stat_bgwriter và catalog tương ứng.

### 16.3. WAL statistics

~~~sql
SELECT *
FROM pg_catalog.pg_stat_wal;
~~~

Theo dõi WAL bytes, records, full-page images và buffer pressure theo schema version.

### 16.4. Không nhầm background writer với checkpointer

Background writer ghi dirty buffers theo hoạt động nền. Checkpointer chịu trách nhiệm checkpoint consistency. Vai trò khác nhau dù cả hai có thể ghi data pages.

### 16.5. Theo dõi duration và throughput

Kết hợp process activity với checkpoint write/sync time, WAL generation, storage latency và disk queue. Chỉ nhìn process tồn tại không cho biết nó đang bị nghẽn.

---

## 17. Tra cứu replication processes

### 17.1. Primary: WAL senders

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
~~~

### 17.2. Standby: WAL receiver

~~~sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
~~~

### 17.3. Replication slots

~~~sql
SELECT *
FROM pg_catalog.pg_replication_slots;
~~~

### 17.4. Logical replication workers

Có thể quan sát các worker qua pg_stat_activity/backend_type và các views như pg_stat_subscription, pg_stat_subscription_stats trên version hỗ trợ.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_subscription;
~~~

### 17.5. Phân biệt connection với replication health

WAL sender đang connected không tự chứng minh standby đã replay tới current WAL. Cần xem sent/write/flush/replay LSN, lag và slot retention.

### 17.6. Cascading replication

Primary chỉ hiển thị các standby kết nối trực tiếp. Muốn thấy downstream workers, cần query trên từng upstream standby tương ứng.

---

## 18. Progress views cho tác vụ dài

PostgreSQL cung cấp progress views cho nhiều hoạt động. Chúng cho biết tác vụ đang ở phase nào và đã xử lý bao nhiêu công việc.

| View | Tác vụ |
| --- | --- |
| pg_stat_progress_vacuum | VACUUM |
| pg_stat_progress_analyze | ANALYZE |
| pg_stat_progress_create_index | CREATE INDEX / REINDEX |
| pg_stat_progress_cluster | CLUSTER / một số rewrite operations |
| pg_stat_progress_copy | COPY |
| pg_stat_progress_basebackup | Base backup |

Tên, columns và availability cần kiểm tra theo major version.

### 18.1. Vacuum

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_vacuum;
~~~

### 18.2. CREATE INDEX

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_create_index;
~~~

### 18.3. COPY

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_copy;
~~~

### 18.4. Base backup

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_basebackup;
~~~

### 18.5. Progress không phải ETA chính xác

Một phase có thể có tốc độ khác nhau. Tỷ lệ blocks processed không nhất thiết tuyến tính với thời gian còn lại. Dùng progress movement và workload/resource metrics.

### 18.6. Tác vụ lâu không nhất thiết bị treo

Index build trên table lớn có thể chạy lâu nhưng vẫn tiến triển. Cần kiểm tra phase, progress, waits và logs trước khi kết luận stuck.

---

## 19. Scheduled jobs và tác vụ ngoài PostgreSQL

Không phải mọi background task đều là PostgreSQL internal process.

### 19.1. pg_cron

Nếu dùng pg_cron, job đang chạy thường tạo database sessions và có thể thấy qua pg_stat_activity với application_name tương ứng. Extension cũng có catalog riêng như cron.job và cron.job_run_details.

### 19.2. Scheduler bên ngoài database

Cron, systemd timers, Windows Task Scheduler, Kubernetes CronJobs, Airflow hoặc orchestration tools chỉ xuất hiện trong pg_stat_activity khi job đang mở connection tới PostgreSQL. Job đang chờ lịch chạy không nhất thiết có backend session.

### 19.3. ETL và batch workers

Gắn application_name có ý nghĩa, ví dụ `etl_orders` hoặc `nightly_maintenance`, để nhận diện session. Không dùng tên chung `psql` cho mọi automation nếu có thể phân biệt.

### 19.4. Job history

Session view chỉ cho biết trạng thái hiện tại. Để biết lịch sử success/failure, cần scheduler/job history, application logs hoặc extension catalogs.

### 19.5. External task không phải database backend

Một backup process có thể đọc database qua pg_basebackup hoặc storage snapshot nhưng process quản trị chạy ngoài host. Để điều tra cần xem OS process, job scheduler và backup tool logs.

---

## 20. Tìm session theo user, database hoặc client

### 20.1. Theo database

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    clock_timestamp() - backend_start AS session_age,
    left(query, 180) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE datname = 'appdb'
ORDER BY backend_start;
~~~

### 20.2. Theo user

~~~sql
SELECT
    pid,
    datname,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - xact_start AS transaction_age
FROM pg_catalog.pg_stat_activity
WHERE usename = 'app_user'
ORDER BY xact_start NULLS LAST;
~~~

### 20.3. Theo client IP

~~~sql
SELECT
    client_addr,
    application_name,
    usename,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE client_addr IS NOT NULL
GROUP BY client_addr, application_name, usename, state
ORDER BY sessions DESC;
~~~

### 20.4. Tìm connection không có application_name

~~~sql
SELECT
    pid,
    usename,
    datname,
    client_addr,
    backend_start,
    state
FROM pg_catalog.pg_stat_activity
WHERE COALESCE(application_name, '') = ''
ORDER BY backend_start;
~~~

Đây có thể là admin tools hoặc client không cấu hình application_name. Xác định owner trước khi yêu cầu thay đổi.

---

## 21. Connection capacity và session pooling

### 21.1. So sánh số backend với max_connections

~~~sql
SELECT
    count(*) AS current_backends
FROM pg_catalog.pg_stat_activity;
~~~

~~~sql
SHOW max_connections;
~~~

Số backend hiện tại không nhất thiết bằng số client requests đang xử lý.

### 21.2. Theo dõi reserved slots

PostgreSQL có thể cấu hình reserved connection slots cho superusers hoặc roles phù hợp. Cần tính theo version và cấu hình thực tế; đừng chờ tới khi hết mọi slots mới điều tra.

### 21.3. Pooling

Connection pooler như PgBouncer có thể giữ ít server connections hơn số client connections. Khi đó pg_stat_activity hiển thị server-side sessions tới PostgreSQL, không phải toàn bộ client requests đang chờ ở pooler.

### 21.4. Pool waiters

Để hiểu user đang chờ, cần metrics từ application/pooler:
- Active/idle pool connections.
- Waiting clients.
- Acquisition latency.
- Queue timeout.
- Server connection errors.

### 21.5. Connection leak

Một application có thể mở connection rồi không trả về pool. Dấu hiệu có thể là session count tăng, idle duration dài và pool acquisition wait tăng. Xác minh qua application metrics và logs.

### 21.6. Không tăng max_connections một cách máy móc

Mỗi backend có memory/process overhead. Tăng giới hạn có thể làm memory pressure nặng hơn khi concurrency cao. Tuning pool/concurrency thường cần được xem cùng.

---

## 22. Statistics snapshots và tính nhất quán khi đọc

### 22.1. Activity view và cumulative stats khác nhau

pg_stat_activity phản ánh hoạt động process hiện tại. Các cumulative statistics views như pg_stat_database/pg_stat_user_tables có semantics snapshot/cache riêng.

### 22.2. Stats snapshot trong transaction

Một transaction có thể giữ statistics snapshot theo stats_fetch_consistency. Nếu lặp query trong cùng transaction, số liệu có thể không thay đổi như mong đợi.

### 22.3. Làm mới snapshot

Có thể dùng pg_stat_clear_snapshot() để xóa snapshot statistics đang cache trong session, tùy semantics version.

~~~sql
SELECT pg_catalog.pg_stat_clear_snapshot();
~~~

### 22.4. now() cố định trong transaction

now() trả transaction start timestamp. Khi cần elapsed time tại thời điểm query, dùng clock_timestamp().

### 22.5. Poll interval

Poll quá dày có thể tạo overhead và nhiều snapshot gần giống nhau. Chọn interval phù hợp với thời gian phát hiện sự cố và monitoring load.

### 22.6. Không dùng polling để thay logs

Một lock wait ngắn hoặc process khởi chạy thoáng qua có thể biến mất giữa hai lần scrape. Logs/progress history cần bổ sung cho snapshot metrics.

---

## 23. Quyền xem session và query text

### 23.1. Quyền mặc định

User thường có thể xem đầy đủ activity của session thuộc chính mình. Query text và thông tin của sessions khác có thể bị giới hạn.

### 23.2. pg_monitor

Role pg_monitor là role monitoring tiện ích, cấp quyền xem nhiều statistics và monitoring views phù hợp. Cần đánh giá phạm vi quyền theo version.

Ví dụ cấp quyền bởi administrator:

~~~sql
GRANT pg_monitor TO monitoring_user;
~~~

### 23.3. pg_read_all_stats

Role này cho phép đọc statistics của mọi sessions theo phạm vi PostgreSQL quy định. Không cấp rộng nếu chỉ cần một phần thông tin.

### 23.4. pg_signal_backend

Role này cho phép gửi signals tới backend không thuộc superuser theo các giới hạn bảo mật. Superuser backend vẫn được bảo vệ.

### 23.5. Least privilege

Tách role:
- Monitoring reader.
- Operator có quyền cancel/terminate phù hợp.
- Database owner.
- Superuser/break-glass account.

Không dùng superuser cho dashboard chỉ đọc nếu không cần.

### 23.6. Query text là dữ liệu nhạy cảm

Query có thể chứa identifiers, schema/table names hoặc literals. Hạn chế quyền xem, masking và log retention theo policy.

---

## 24. Cancel query và terminate session

Đây là hai hành động khác nhau. Phải xác minh đúng PID và owner trước khi thực hiện.

### 24.1. Cancel query

~~~sql
SELECT pg_catalog.pg_cancel_backend(12345);
~~~

Hàm gửi cancel signal tới query đang chạy của backend. Session vẫn tồn tại.

### 24.2. Terminate session

~~~sql
SELECT pg_catalog.pg_terminate_backend(12345);
~~~

Hàm gửi terminate signal tới backend. Session bị đóng; transaction đang mở sẽ rollback khi backend kết thúc.

### 24.3. So sánh

| Hành động | Kết quả | Khi cân nhắc |
| --- | --- | --- |
| pg_cancel_backend | Hủy query hiện tại, giữ session | Query chạy quá lâu hoặc cần dừng statement |
| pg_terminate_backend | Kết thúc backend/session | Session gây vấn đề và cần đóng connection |

### 24.4. Cancel trong explicit transaction

Nếu query bị cancel trong transaction explicit, transaction có thể chuyển sang aborted state và client cần ROLLBACK. Session vẫn còn.

### 24.5. Terminate có thể gây rollback lớn

Một transaction ghi lớn bị terminate có thể cần rollback, tạo I/O và làm session/locks tiếp tục tồn tại trong lúc rollback. Không phải lúc nào terminate cũng giải phóng tài nguyên ngay tức thì.

### 24.6. Quyền

Thường cần là owner của backend, thành viên pg_signal_backend hoặc superuser theo quy tắc PostgreSQL. Không thể signal superuser-owned backend chỉ bằng pg_signal_backend.

### 24.7. Quy trình xác minh trước khi terminate

1. Lấy snapshot pg_stat_activity.
2. Ghi PID và backend_start.
3. Xác định database, user, application_name, client_addr.
4. Xác định query, transaction age, state và wait event.
5. Tìm các session đang bị blocker.
6. Liên hệ owner/on-call theo runbook.
7. Chọn cancel hay terminate.
8. Kiểm tra kết quả và side effects.

### 24.8. Không terminate theo PID cũ

PID có thể được tái sử dụng sau khi backend kết thúc. Chạy lại truy vấn xác nhận session ngay trước thao tác.

---

## 25. Các timeout liên quan session và transaction

### 25.1. statement_timeout

Giới hạn tổng thời gian statement. Hữu ích để ngăn query chạy vô hạn, nhưng cần chọn theo workload.

### 25.2. lock_timeout

Giới hạn thời gian chờ lock. Có thể dùng để tránh request bị block quá lâu.

### 25.3. idle_in_transaction_session_timeout

Tự động kết thúc session ở trạng thái idle in transaction quá thời gian cấu hình. Giúp hạn chế transaction bị bỏ quên, nhưng có thể ảnh hưởng ứng dụng hợp lệ nếu đặt quá thấp.

### 25.4. idle_session_timeout

Có thể đóng session idle quá lâu trên các version hỗ trợ. Cần xem pooler/client behavior để tránh connection churn ngoài ý muốn.

### 25.5. transaction_timeout

Một số PostgreSQL versions mới hỗ trợ giới hạn tổng thời gian transaction. Kiểm tra version và semantics trước khi dùng.

### 25.6. Xem setting hiện tại

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'idle_session_timeout',
    'transaction_timeout',
    'deadlock_timeout'
)
ORDER BY name;
~~~

Cột hoặc setting có thể không tồn tại trên version cũ. Query monitoring cần tương thích server.

### 25.7. Timeout không thay thế quản lý transaction

Timeout giúp giới hạn thời gian, nhưng ứng dụng vẫn cần luôn COMMIT/ROLLBACK, đóng cursor và trả connection về pool.

---

## 26. Tác động của session lên vacuum và bloat

### 26.1. MVCC giữ nhiều row versions

PostgreSQL dùng MVCC. UPDATE/DELETE tạo row versions mới/cũ; VACUUM chỉ reclaim các versions không còn cần thiết cho bất kỳ snapshot nào.

### 26.2. Long transaction giữ snapshot

Một transaction lâu có thể giữ xmin cũ, làm VACUUM không loại bỏ các dead tuples mà snapshot đó vẫn có thể cần.

### 26.3. Idle in transaction là dấu hiệu quan trọng

Session idle in transaction có thể giữ snapshot mà không thực hiện query nào. Đây là lý do phải giám sát transaction age chứ không chỉ query duration.

### 26.4. Replication slots và standby feedback

Replication slots hoặc hot_standby_feedback có thể giữ xmin/WAL retention. Điều tra vacuum lag cần xem cả pg_stat_activity, pg_replication_slots và standby state.

### 26.5. Theo dõi database XID age

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

Đây là metric quan trọng để quản lý transaction ID wraparound. Ngưỡng cảnh báo phải theo version, autovacuum policy và quy mô cluster.

### 26.6. Không chỉ nhìn dead tuples

n_dead_tup là estimate. Kết hợp XID age, last_autovacuum, vacuum progress, long transactions, replication horizon và table growth.

---

## 27. Tác vụ nền không phải lúc nào cũng có session client

### 27.1. PostgreSQL internal workers

Có thể xuất hiện trong pg_stat_activity dưới backend_type riêng. Chúng không nhất thiết có user/application_name như client sessions.

### 27.2. Background tasks của extension

Extension có thể chạy background workers với tên riêng. Tài liệu extension là nguồn để hiểu lifecycle và cách can thiệp.

### 27.3. Scheduler bên ngoài

Cron/systemd/Kubernetes/Airflow có thể chỉ mở database connection trong lúc chạy. Khi job không chạy, không có session tương ứng.

### 27.4. OS process

Một số công việc như file copy, archive uploader hoặc backup agent chạy ngoài PostgreSQL. Cần kiểm tra process list, service manager và logs ở OS.

### 27.5. Job history

pg_stat_activity chỉ là snapshot hiện tại. Muốn biết job đã chạy thành công/thất bại, phải xem scheduler history, application logs hoặc extension job catalog.

---

## 28. Runbook: điều tra query chậm

### Bước 1: Xác định phạm vi

Hỏi query nào, database nào, application nào, bắt đầu từ lúc nào và có ảnh hưởng người dùng không.

### Bước 2: Liệt kê active sessions

Dùng pg_stat_activity để xem query age, wait events, user, application và client.

### Bước 3: Phân biệt execution với waiting

Nếu active và không có wait event, kiểm tra CPU/query plan. Nếu wait event có giá trị, drill down theo Lock, IO, Client, LWLock hoặc IPC.

### Bước 4: Kiểm tra blockers

Dùng pg_blocking_pids và pg_locks. Xác định root blocker và transaction age của blocker.

### Bước 5: Kiểm tra query history

Dùng pg_stat_statements để xem calls, total/mean execution time, rows và buffer/temp activity.

### Bước 6: Kiểm tra resource

CPU, memory, storage latency, queue depth, network, connection pool wait và disk capacity.

### Bước 7: Chọn hành động

Có thể điều chỉnh query/index, xử lý blocker theo owner, điều tiết workload hoặc cancel statement. Không terminate trước khi hiểu transaction và tác động.

### Bước 8: Xác minh

Theo dõi latency, throughput, waiters, error rate và query progress sau thay đổi.

---

## 29. Runbook: transaction mở lâu và idle in transaction

### Bước 1: Liệt kê transaction age

Tìm xact_start cũ, state, application_name, user và backend_xmin.

### Bước 2: Phân loại

- Active query chạy lâu.
- Active query chờ lock/I/O.
- Idle in transaction.
- Idle in transaction (aborted).
- Prepared transaction.

### Bước 3: Xác định owner

Dùng application_name, client_addr, user và application logs để tìm service/job sở hữu connection.

### Bước 4: Kiểm tra lock impact

Tìm blocked sessions và locks do transaction giữ.

### Bước 5: Kiểm tra vacuum impact

Đối chiếu backend_xmin, n_dead_tup, XID age, vacuum progress và replication horizon.

### Bước 6: Liên hệ owner theo policy

Ưu tiên để ứng dụng COMMIT/ROLLBACK đúng cách. Nếu cần can thiệp, đánh giá cancel/terminate và rollback cost.

### Bước 7: Theo dõi sau xử lý

Xác nhận session kết thúc, blockers được giải phóng, vacuum tiếp tục và connection pool ổn định.

---

## 30. Runbook: background task chạy lâu

### Bước 1: Xác định backend type

Dùng pg_stat_activity để phân biệt autovacuum, checkpointer, background writer, replication và client.

### Bước 2: Tìm progress view tương ứng

- VACUUM: pg_stat_progress_vacuum.
- CREATE INDEX: pg_stat_progress_create_index.
- COPY: pg_stat_progress_copy.
- Base backup: pg_stat_progress_basebackup.

### Bước 3: Kiểm tra wait và resource

Xem wait_event, CPU, I/O, disk, locks và transaction blockers.

### Bước 4: Kiểm tra logs

Đọc PostgreSQL logs hoặc tool/scheduler logs để xác định phase, retry và failure.

### Bước 5: Xác định expected duration

So với table size, workload, maintenance window và baseline. Không kết luận stuck chỉ vì thời gian dài.

### Bước 6: Can thiệp theo task owner

Không dừng autovacuum, checkpoint, replication hoặc backup worker chỉ để làm biến mất một process khỏi dashboard. Dùng cơ chế quản trị của task tương ứng.

---

## 31. Monitoring dashboard cho sessions và transactions

Một dashboard quản trị nên có các panel sau.

### 31.1. Session overview

- Total sessions.
- Active/idle/idle in transaction.
- Sessions theo database/user/application.
- Backend types.
- Connection usage so với capacity.

### 31.2. Long-running work

- Longest active query age.
- Longest transaction age.
- Longest idle-in-transaction age.
- Active queries theo wait_event_type.
- Sessions có backend_xmin cũ.

### 31.3. Locks

- Number of blocked sessions.
- Root blocker PIDs.
- Lock wait age.
- Deadlocks/s.
- Lock timeout errors.

### 31.4. Background tasks

- Autovacuum workers và progress.
- CREATE INDEX/COPY/base backup progress.
- Checkpoint/WAL activity.
- Replication sender/receiver state.
- Logical replication workers.
- Scheduled job state từ scheduler.

### 31.5. Pooling

- Application pool active/idle/waiters.
- Acquisition latency.
- Server connections.
- Queue timeout.
- Connection creation/recycle rate.

### 31.6. Alert có owner và runbook

Mỗi alert nên nêu database/cluster, application_name, PID/backend_start, age, wait event, blocker nếu có, user impact và bước kiểm tra tiếp theo. Tránh đưa raw query hoặc user identifiers vào labels không giới hạn.

---

## 32. Version compatibility và khám phá schema

PostgreSQL statistics views thay đổi theo major version. Không giả định query viết cho một server sẽ chạy trên mọi server.

### 32.1. Xác định version

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

### 32.2. Khám phá pg_stat_activity columns

~~~sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name = 'pg_stat_activity'
ORDER BY ordinal_position;
~~~

### 32.3. Khám phá progress views

~~~sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name LIKE 'pg_stat_progress_%'
ORDER BY table_name, ordinal_position;
~~~

### 32.4. Cột có thể khác

backend_type, leader_pid, query_id và các progress fields phụ thuộc version. Một số view không tồn tại trên major version cũ.

### 32.5. Exporter nên version-aware

Monitoring collector cần kiểm tra server version hoặc có SQL queries tương thích. Một query lỗi có thể làm collector bỏ mất cả nhóm metrics.

### 32.6. Không dùng SELECT * làm contract lâu dài

SELECT * tiện khám phá trong lab, nhưng dashboard/runbook ổn định nên chọn columns rõ ràng và có fallback theo version.

---

## 33. Lab 1: xem session và state

Dùng database lab hoặc môi trường development.

### 33.1. Mở hai connections

Mở hai psql terminals hoặc hai sessions từ SQL client.

### 33.2. Session A chạy query

~~~sql
SELECT pg_sleep(45);
~~~

### 33.3. Session B xem activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 120) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

### 33.4. Quan sát state

Session A có state active trong thời gian pg_sleep chạy. Wait event có thể cho thấy nó đang chờ timer.

### 33.5. Kết thúc query

Đợi query kết thúc hoặc cancel từ chính client. Không cần terminate session để kết thúc một lab query thông thường.

### 33.6. Kết luận

Một query active không nhất thiết tiêu thụ CPU; wait event giúp giải thích.

---

## 34. Lab 2: quan sát idle in transaction

### 34.1. Tạo bảng lab

~~~sql
CREATE TABLE IF NOT EXISTS public.session_lab (
    id INTEGER PRIMARY KEY,
    value INTEGER NOT NULL
);

INSERT INTO public.session_lab(id, value)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
~~~

### 34.2. Session A

~~~sql
BEGIN;
UPDATE public.session_lab
SET value = value + 1
WHERE id = 1;
-- Chưa commit/rollback.
~~~

### 34.3. Session B kiểm tra

~~~sql
SELECT
    pid,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS state_age,
    application_name,
    left(query, 120) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%';
~~~

### 34.4. Session B thử update cùng row

~~~sql
UPDATE public.session_lab
SET value = value + 1
WHERE id = 1;
~~~

Session B có thể chờ row lock do Session A giữ.

### 34.5. Session A rollback hoặc commit

Quan sát Session B tiếp tục sau khi blocker kết thúc.

### 34.6. Kết luận

Transaction có thể giữ lock dù session không chạy query tại thời điểm quan sát.

---

## 35. Lab 3: tìm blocked session và blocker

### 35.1. Tạo blocker/waiter

Dùng hai sessions và một row trong bảng lab. Session A BEGIN và UPDATE; Session B UPDATE cùng row.

### 35.2. Query blocker graph

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.application_name AS blocked_app,
    blocker.application_name AS blocker_app,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age
FROM pg_catalog.pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(blocked.pid)
) AS b(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
    ON blocker.pid = b.pid
WHERE blocked.wait_event_type = 'Lock';
~~~

### 35.3. Xem pg_locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation
FROM pg_catalog.pg_locks
WHERE pid IN (SELECT pid FROM pg_catalog.pg_stat_activity)
ORDER BY pid, granted;
~~~

### 35.4. Giải phóng blocker

COMMIT hoặc ROLLBACK Session A và quan sát waiter tiếp tục.

### 35.5. Kết luận

Xác định root blocker trước khi xử lý hàng loạt waiters.

---

## 36. Lab 4: theo dõi autovacuum và progress

### 36.1. Tạo bảng churn

~~~sql
CREATE TABLE IF NOT EXISTS public.vacuum_lab (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

INSERT INTO public.vacuum_lab(id, payload)
SELECT g, repeat('x', 300)
FROM generate_series(1, 100000) AS g;
~~~

### 36.2. Tạo dead tuples

~~~sql
UPDATE public.vacuum_lab
SET payload = repeat('y', 300)
WHERE id % 2 = 0;

DELETE FROM public.vacuum_lab
WHERE id % 5 = 0;
~~~

### 36.3. Chạy VACUUM trong lab

~~~sql
VACUUM (ANALYZE) public.vacuum_lab;
~~~

### 36.4. Quan sát progress

Trong một session khác, query pg_stat_progress_vacuum và pg_stat_activity. Tác vụ có thể hoàn tất nhanh; tăng kích thước dữ liệu lab nếu cần quan sát lâu hơn.

### 36.5. Quan sát table stats

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE relname = 'vacuum_lab';
~~~

### 36.6. Kết luận

Progress view mô tả công việc đang chạy; table stats giúp quan sát kết quả theo thời gian.

---

## 37. Lab 5: phân biệt session và prepared transaction

Lab cần cấu hình max_prepared_transactions phù hợp và một môi trường thử nghiệm. Không bật two-phase commit trên production chỉ để thực hành.

### 37.1. Bắt đầu transaction

~~~sql
BEGIN;
UPDATE public.session_lab
SET value = value + 1
WHERE id = 1;
PREPARE TRANSACTION 'session_lab_tx_1';
~~~

### 37.2. Kiểm tra pg_stat_activity

Session thực hiện PREPARE TRANSACTION có thể kết thúc transaction session context, nhưng prepared transaction vẫn tồn tại.

### 37.3. Kiểm tra pg_prepared_xacts

~~~sql
SELECT *
FROM pg_catalog.pg_prepared_xacts
WHERE gid = 'session_lab_tx_1';
~~~

### 37.4. Kết thúc prepared transaction

Trong lab, chọn đúng kết quả coordinator và chạy:

~~~sql
COMMIT PREPARED 'session_lab_tx_1';
~~~

Hoặc ROLLBACK PREPARED nếu kịch bản yêu cầu hủy.

### 37.5. Kết luận

Không phải transaction nào còn tồn tại cũng có PID trong pg_stat_activity. Prepared transactions cần catalog riêng và owner/coordinator rõ ràng.

---

## 38. Bài tập thực hành

### Bài 1 — Khái niệm

Phân biệt session, backend process, statement và transaction bằng một ví dụ.

### Bài 2 — pg_stat_activity

Viết query liệt kê PID, user, database, application_name, client address, state và wait event.

### Bài 3 — Session state

Giải thích active, idle, idle in transaction và idle in transaction (aborted).

### Bài 4 — Query age

Tìm các active queries chạy hơn 60 giây. Giải thích vì sao query_start không đại diện transaction age.

### Bài 5 — Transaction age

Tìm transactions mở hơn 10 phút, bao gồm cả sessions đang idle.

### Bài 6 — Session age

Viết query tìm các sessions tồn tại lâu nhất và nêu vì sao tuổi connection không tự chứng minh connection leak.

### Bài 7 — Application name

Thiết kế application_name convention cho API, ETL, migration và reporting jobs.

### Bài 8 — Wait events

Một session active có wait_event_type='Lock'. Giải thích trạng thái và viết bước điều tra blocker.

### Bài 9 — Blocker graph

Viết query dùng pg_blocking_pids để tìm blocked PID và blocking PID.

### Bài 10 — pg_locks

Giải thích granted, locktype, mode và relation. Vì sao không phải mọi lock đều có relation?

### Bài 11 — Idle blocker

Một blocker đang idle in transaction. Vì sao nó vẫn có thể giữ locks?

### Bài 12 — Deadlock

Phân biệt lock wait với deadlock. Nêu vai trò deadlock_timeout và deadlocks counter.

### Bài 13 — Long read transaction

Một SELECT transaction chạy lâu làm vacuum không reclaim dead tuples. Giải thích MVCC snapshot và backend_xmin.

### Bài 14 — Prepared transaction

Vì sao prepared transaction có thể tồn tại mà không có session PID trong pg_stat_activity?

### Bài 15 — Cancel

Giải thích pg_cancel_backend và trạng thái transaction sau khi statement bị cancel trong explicit transaction.

### Bài 16 — Terminate

Giải thích pg_terminate_backend và tác động rollback. Nêu thông tin cần xác minh trước khi terminate.

### Bài 17 — Permissions

Thiết kế role monitoring dùng pg_monitor hoặc pg_read_all_stats với least privilege.

### Bài 18 — Backend types

Phân biệt client backend, autovacuum worker, checkpointer, WAL writer, WAL sender và parallel worker.

### Bài 19 — Autovacuum

Viết query tìm autovacuum workers và progress của vacuum đang chạy.

### Bài 20 — Checkpoint

Tìm process checkpoint/background writer và nêu các statistics cần xem để hiểu write pressure.

### Bài 21 — Replication

Tra cứu WAL senders trên primary và WAL receiver trên standby. Vì sao connection state chưa đủ để kết luận replica khỏe?

### Bài 22 — Logical replication

Nêu các worker và statistics views cần xem khi subscription không apply changes.

### Bài 23 — Progress views

Chọn view tương ứng cho VACUUM, CREATE INDEX, COPY và base backup.

### Bài 24 — Scheduled jobs

Phân biệt pg_cron session với Kubernetes CronJob đang chờ lịch. Tại sao pg_stat_activity không thể hiện mọi scheduled tasks?

### Bài 25 — Connection pool

Pool waiters tăng nhưng database sessions phần lớn idle. Đề xuất các nguồn metrics cần kiểm tra.

### Bài 26 — Connection capacity

So sánh current backend count với max_connections. Vì sao không nên tăng max_connections ngay khi chạm ngưỡng?

### Bài 27 — Timeout

Phân biệt statement_timeout, lock_timeout và idle_in_transaction_session_timeout.

### Bài 28 — Stats snapshot

Giải thích vì sao now() có thể không tăng trong một transaction monitoring kéo dài và khi nào dùng clock_timestamp().

### Bài 29 — Version compatibility

Viết query khám phá columns của pg_stat_activity và progress views trên các major versions khác nhau.

### Bài 30 — Background task stuck

Một CREATE INDEX chạy 40 phút. Thiết kế quy trình xem progress, locks, wait events, I/O và expected duration.

### Bài 31 — Vacuum horizon

Long transaction và replication slot cùng tồn tại. Nêu các kiểm tra cần làm trước khi kết luận nguyên nhân vacuum lag.

### Bài 32 — Root blocker

Một blocker chặn 80 sessions. Xây dựng quy trình tìm owner, đánh giá transaction và chọn cancel/terminate.

### Bài 33 — PID reuse

Vì sao phải kiểm tra backend_start ngay trước khi gửi signal tới PID đã lưu từ incident snapshot?

### Bài 34 — Query visibility

Một monitoring user thấy query của chính mình nhưng query text của user khác là NULL. Giải thích quyền cần xem xét.

### Bài 35 — Transaction rollback

Một transaction ghi hàng triệu rows bị terminate. Những tác động về rollback, I/O và lock duration cần dự kiến?

### Bài 36 — Autovacuum safety

Vì sao terminate autovacuum worker có thể làm tình trạng bloat/XID risk tệ hơn?

### Bài 37 — Dashboard

Thiết kế dashboard gồm session state, long transactions, wait events, blockers, prepared transactions và background progress.

### Bài 38 — Incident runbook

Một API bị timeout, database CPU thấp, 60 sessions chờ lock và một idle-in-transaction session giữ blocker. Viết trình tự điều tra và hành động.

### Bài 39 — Two-phase commit

Một prepared transaction tồn tại nhiều giờ. Nêu thông tin cần thu thập từ coordinator trước khi COMMIT PREPARED hoặc ROLLBACK PREPARED.

### Bài 40 — End-to-end administration

Một cluster có primary, hai standby, PgBouncer, pg_cron và autovacuum. Sau deploy, connection pool wait tăng, một transaction idle 25 phút, 30 queries chờ lock, autovacuum chậm và replication replay lag tăng. Thiết kế trình tự đọc views, xác định root cause, phân quyền hành động, xử lý session và xác minh phục hồi.

---

## 39. Checklist tra cứu session, transaction và background task

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| PostgreSQL version | Major version và columns có sẵn |
| Session identity | PID, backend_start, user, database |
| Application identity | application_name, client_addr |
| Backend type | Client hay internal worker |
| Session state | active/idle/idle in transaction/aborted |
| Query age | query_start và state |
| Transaction age | xact_start |
| Session age | backend_start |
| State age | state_change |
| Query visibility | Quyền monitoring phù hợp |
| Wait event | wait_event_type và wait_event |
| Active CPU vs wait | Không chỉ đếm state active |
| Blocked sessions | pg_blocking_pids |
| Root blocker | Blocking PID và transaction age |
| Lock details | pg_locks, mode, granted |
| Deadlocks | pg_stat_database delta và logs |
| Prepared transactions | pg_prepared_xacts |
| Old snapshots | backend_xmin/xmin horizon |
| Vacuum impact | dead tuples, XID age, vacuum progress |
| Autovacuum | Launcher/worker và progress |
| Checkpointer | Process và checkpoint stats |
| WAL writer | WAL statistics |
| Replication | Sender/receiver, LSN và sync state |
| Logical replication | Subscription workers/stats |
| Progress tasks | Vacuum/index/copy/basebackup |
| Scheduled jobs | pg_cron hoặc scheduler history |
| External jobs | OS/Kubernetes/orchestrator logs |
| Connection pool | Active/idle/waiters/acquisition latency |
| Connection capacity | Current backends và max_connections |
| Timeout policy | statement/lock/idle transaction |
| Cancel/terminate | Owner, permission, impact và rollback |
| PID safety | Recheck PID/backend_start trước signal |
| Post-action verification | Blockers, query, pool và application health |
| Audit trail | Incident time, action, operator và result |

## Kết luận

Tra cứu session, transaction và tác vụ nền trong PostgreSQL cần kết hợp pg_stat_activity với locks, prepared transactions, progress views và các statistics chuyên biệt. Một session active có thể đang chờ; một session idle có thể giữ transaction và snapshot; một background worker chạy lâu có thể đang làm đúng công việc cần thiết. Đọc đúng các mốc thời gian, wait events và backend types giúp phân biệt tình trạng bình thường với vấn đề cần can thiệp.

Những nguyên tắc cần nhớ:

1. **Session không đồng nghĩa transaction.** Một session có thể giữ transaction mở dù không chạy query.
2. **Query age khác transaction age.** Dùng query_start để xem statement và xact_start để xem transaction.
3. **Active không đồng nghĩa đang dùng CPU.** Luôn đọc wait_event_type và wait_event.
4. **Idle in transaction có thể gây ảnh hưởng lớn.** Nó có thể giữ locks, snapshot và cản vacuum.
5. **pg_blocking_pids giúp tìm blocker.** Xác định root blocker trước khi xử lý nhiều waiters.
6. **pg_locks cho biết lock state.** Đọc granted, mode, locktype và relation trong đúng ngữ cảnh.
7. **Prepared transactions có catalog riêng.** Chúng có thể tồn tại sau khi session ban đầu biến mất.
8. **Background workers có nhiệm vụ riêng.** Autovacuum, checkpointer, WAL và replication không phải client sessions thông thường.
9. **Progress views giúp phân biệt chậm với stuck.** Theo dõi phase và tiến triển thay vì chỉ nhìn duration.
10. **Scheduled jobs có thể nằm ngoài PostgreSQL.** Dùng scheduler logs và application_name để liên kết.
11. **Monitoring cần quyền phù hợp.** Dùng pg_monitor/pg_read_all_stats theo least privilege và bảo vệ query text.
12. **Cancel khác terminate.** Cancel dừng query; terminate đóng session và có thể gây rollback.
13. **Xác minh PID ngay trước khi signal.** PID có thể được tái sử dụng.
14. **Không dừng tác vụ nền tùy tiện.** Đặc biệt autovacuum, checkpoint, backup và replication cần được xử lý theo runbook.
15. **Xác minh sau can thiệp.** Kiểm tra blockers, transaction state, pool, vacuum, replication và application health.

Một quy trình quản trị tốt bắt đầu bằng snapshot có đủ định danh và thời gian, xác định session đang làm gì hoặc chờ gì, tìm transaction/lock/background task liên quan, rồi mới chọn hành động phù hợp. Sau mỗi thay đổi, cần xác nhận blocker đã được giải phóng, transaction kết thúc đúng cách và dịch vụ trở lại trạng thái ổn định.
