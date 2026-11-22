# Xác định phiên giữ khóa và chuỗi phiên đang chờ

Khi một truy vấn bị treo, câu hỏi đầu tiên thường là: **phiên nào đang chặn nó và phiên đó đang giữ tài nguyên gì?** Trong hệ thống có nhiều transaction, câu trả lời không phải lúc nào cũng là session có câu SQL đang chạy lâu nhất. Một session có thể đã chạy xong câu UPDATE, chuyển sang trạng thái Sleep nhưng vẫn giữ transaction chưa commit và tiếp tục giữ lock.

Để chẩn đoán đúng, cần dựng được **chuỗi chờ (blocking chain)**: transaction nào đang chờ, nó chờ session nào, session đó có đang chờ một session khác không, và đâu là phiên giữ khóa ở đầu chuỗi. Cũng cần phân biệt blocking thông thường với deadlock, vì hai tình huống có cách xử lý khác nhau.

Bài này trình bày cách quan sát và điều tra trên MySQL InnoDB, PostgreSQL và SQL Server, cùng một bài thực nghiệm ba session tạo chuỗi A chặn B, B chặn C.

## 1. Các vai trò trong một chuỗi chờ

Một transaction có thể yêu cầu lock không tương thích với lock đang được transaction khác giữ. Khi đó, session yêu cầu phải chờ.

Các thuật ngữ cần phân biệt:

- **Waiter / blocked session:** session đang chờ lấy lock hoặc tài nguyên.
- **Blocker:** session đang giữ tài nguyên khiến waiter không thể tiếp tục.
- **Root blocker:** blocker ở đầu chuỗi, bản thân nó không bị một session khác chặn trong chuỗi đang quan sát.
- **Blocking chain:** chuỗi quan hệ chờ giữa nhiều session.
- **Deadlock:** chu trình chờ khép kín, trong đó mỗi transaction chờ một tài nguyên do transaction khác trong chu trình giữ.

Ví dụ:

~~~text
Session A
  giữ lock trên hàng 1
       |
       v
Session B
  giữ lock trên hàng 2
  đang chờ hàng 1 của A
       |
       v
Session C
  đang chờ hàng 2 của B
~~~

Trong ví dụ này:

- A là root blocker.
- B vừa là waiter của A, vừa là blocker của C.
- C là waiter ở cuối chuỗi.
- Không có chu trình khép kín, nên đây là blocking chain, chưa phải deadlock.

Mũi tên trong sơ đồ biểu thị quan hệ **waiter → blocker**. Khi điều tra, hãy bắt đầu từ session đang bị ảnh hưởng rồi lần ngược chuỗi để tìm root blocker.

## 2. Vì sao session đã Sleep vẫn có thể chặn session khác?

Một transaction không kết thúc chỉ vì câu SQL cuối cùng đã chạy xong. Với transaction tường minh, lock thường được giữ đến khi transaction COMMIT hoặc ROLLBACK, theo quy tắc của database.

Ví dụ:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Ứng dụng chưa COMMIT hoặc ROLLBACK.
-- Connection quay về trạng thái chờ lệnh tiếp theo.
~~~

Sau UPDATE, session có thể không còn câu SQL đang chạy. Nhưng transaction vẫn mở và lock ghi trên hàng account_id = 10 vẫn có thể được giữ.

Nếu ứng dụng mở transaction trước khi gọi HTTP API, chờ người dùng xác nhận, gặp exception rồi bỏ quên rollback, trả connection về pool khi transaction chưa được kết thúc đúng cách, hoặc mở transaction rồi để session idle quá lâu, session đó có thể trở thành blocker kéo dài.

Đây là lý do cần quan sát cả **trạng thái session** và **tuổi transaction**, không chỉ câu SQL hiện tại.

## 3. Phân biệt blocking chain với deadlock

Blocking và deadlock đều liên quan đến lock wait, nhưng cấu trúc của chúng khác nhau.

### Blocking chain

~~~text
A giữ lock X
 |
 +--> B chờ X, nhưng B vẫn giữ lock Y
          |
          +--> C chờ Y
~~~

Nếu A commit, B có thể tiếp tục. Khi B hoàn tất và nhả Y, C có thể tiếp tục. Một blocking chain có thể rất dài nhưng vẫn không phải deadlock.

### Deadlock

~~~text
A giữ X, chờ Y
       |
       v
       B giữ Y, chờ X
       |
       +------> A
~~~

Hai transaction tạo thành chu trình chờ. Không transaction nào có thể tự tiến triển nếu không có một lock được giải phóng. Database thường phát hiện deadlock và chọn một transaction làm victim để rollback.

| Đặc điểm | Blocking | Deadlock |
|---|---|---|
| Cấu trúc | Một hoặc nhiều nhánh chờ có hướng | Có chu trình chờ |
| Có thể tự hết khi blocker commit | Có | Không, nếu chu trình vẫn tồn tại |
| Database có thể tự chọn victim | Thường không cần | Thường có |
| Dấu hiệu | Lock wait, blocked session, blocker | Deadlock graph/report, deadlock error |
| Hướng xử lý | Tìm blocker và rút ngắn transaction giữ lock | Phân tích chu trình, thứ tự lấy lock và retry transaction victim |

Một waiter có thể chờ rất lâu mà không tạo deadlock. Ngược lại, deadlock có thể xảy ra nhanh và biến mất ngay sau khi database rollback victim, nên nếu chỉ truy vấn trạng thái hiện tại thì có thể không còn thấy nó. Cần xem deadlock log hoặc event history.

## 4. Bài thực nghiệm: tạo chuỗi A chặn B, B chặn C bằng MySQL InnoDB

Thực nghiệm dùng ba kết nối độc lập đến cùng MySQL server:

- **Session A:** giữ lock trên hàng 1.
- **Session B:** giữ lock trên hàng 2, sau đó chờ hàng 1.
- **Session C:** chờ hàng 2.
- **Observer:** một kết nối thứ tư dùng để xem wait graph và transaction.

### 4.1. Chuẩn bị bảng

Chạy một lần khi không có transaction thực nghiệm nào đang mở:

~~~sql
DROP TABLE IF EXISTS blocking_lab;

CREATE TABLE blocking_lab (
    id INT NOT NULL PRIMARY KEY,
    value INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO blocking_lab (id, value)
VALUES (1, 100), (2, 200);
~~~

### 4.2. Session A khóa hàng 1

Chạy ở Session A và để transaction mở:

~~~sql
START TRANSACTION;

UPDATE blocking_lab
SET value = value + 1
WHERE id = 1;
~~~

A đã cập nhật hàng 1 và giữ lock ghi đến khi transaction kết thúc.

### 4.3. Session B khóa hàng 2 rồi chờ hàng 1

Chạy ở Session B:

~~~sql
START TRANSACTION;

UPDATE blocking_lab
SET value = value + 1
WHERE id = 2;

UPDATE blocking_lab
SET value = value + 1
WHERE id = 1;
~~~

Câu UPDATE đầu tiên hoàn tất, nên B giữ lock trên hàng 2. Câu UPDATE thứ hai phải chờ A vì A đang giữ lock hàng 1. Giữ Session B ở trạng thái chờ, chưa hủy hoặc commit.

### 4.4. Session C chờ hàng 2

Chạy ở Session C:

~~~sql
START TRANSACTION;

UPDATE blocking_lab
SET value = value + 10
WHERE id = 2;
~~~

C phải chờ B vì B đang giữ lock hàng 2.

Wait graph lúc này có dạng:

~~~text
A (giữ hàng 1)
      |
      v
B (giữ hàng 2, chờ hàng 1 của A)
      |
      v
C (chờ hàng 2 của B)
~~~

### 4.5. Quan sát rồi giải phóng chuỗi

Trong Observer, chạy truy vấn chẩn đoán ở phần tiếp theo.

Sau khi đã quan sát, quay lại Session A:

~~~sql
COMMIT;
~~~

B có thể tiếp tục UPDATE hàng 1. Khi B hoàn tất câu lệnh, chạy:

~~~sql
COMMIT;
~~~

C sau đó có thể tiếp tục UPDATE hàng 2. Chạy:

~~~sql
COMMIT;
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT *
FROM blocking_lab
ORDER BY id;
~~~

Giá trị cuối phụ thuộc đúng vào số lần mỗi UPDATE đã hoàn tất. Mục tiêu thực nghiệm là quan sát quan hệ chờ, không phải tạo một kết quả nghiệp vụ cụ thể.

Nếu một session báo lỗi hoặc timeout trong lúc thực nghiệm, kết thúc transaction còn lại bằng ROLLBACK trước khi chạy lại. Không để session chờ hoặc transaction cũ tồn tại rồi làm sai kết quả lần thử tiếp theo.

## 5. MySQL 8: xem waiter và blocker bằng Performance Schema

MySQL 8 cung cấp các bảng Performance Schema để quan sát lock đang được cấp và lock đang chờ:

- **performance_schema.data_locks:** các lock đang tồn tại.
- **performance_schema.data_lock_waits:** quan hệ giữa lock đang yêu cầu và lock đang chặn.
- **performance_schema.threads:** ánh xạ thread nội bộ sang connection ID và thông tin session.
- **information_schema.innodb_trx:** thông tin transaction InnoDB, gồm thời điểm bắt đầu và câu SQL hiện tại nếu có.

Truy vấn sau dựng từng cạnh trong blocking chain:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    wt.PROCESSLIST_USER AS waiting_user,
    wt.PROCESSLIST_COMMAND AS waiting_command,
    wt.PROCESSLIST_TIME AS waiting_state_seconds,
    wt.PROCESSLIST_INFO AS waiting_current_sql,

    req.OBJECT_SCHEMA AS locked_schema,
    req.OBJECT_NAME AS locked_table,
    req.INDEX_NAME AS locked_index,
    req.LOCK_TYPE AS requested_lock_type,
    req.LOCK_MODE AS requested_lock_mode,
    req.LOCK_DATA AS requested_lock_data,

    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    bt.PROCESSLIST_USER AS blocking_user,
    bt.PROCESSLIST_COMMAND AS blocking_command,
    bt.PROCESSLIST_TIME AS blocking_state_seconds,
    bt.PROCESSLIST_INFO AS blocking_current_sql,

    btrx.trx_started AS blocking_trx_started,
    TIMESTAMPDIFF(SECOND, btrx.trx_started, NOW())
        AS blocking_trx_age_seconds,
    btrx.trx_query AS blocking_trx_current_sql,

    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data

FROM performance_schema.data_lock_waits AS w

LEFT JOIN performance_schema.threads AS wt
    ON wt.THREAD_ID = w.REQUESTING_THREAD_ID

LEFT JOIN performance_schema.threads AS bt
    ON bt.THREAD_ID = w.BLOCKING_THREAD_ID

LEFT JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID

LEFT JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID

LEFT JOIN information_schema.innodb_trx AS btrx
    ON btrx.trx_mysql_thread_id = bt.PROCESSLIST_ID

ORDER BY blocking_trx_started, waiting_connection_id;
~~~

Mỗi dòng biểu diễn một quan hệ waiter/blocker. Với chuỗi thực nghiệm, một dòng cho thấy B chờ A và một dòng cho thấy C chờ B.

Các cột quan trọng:

| Cột | Cách sử dụng |
|---|---|
| waiting_connection_id | Connection đang bị chặn; dùng để đối chiếu PROCESSLIST |
| blocking_connection_id | Connection đang giữ lock gây chặn |
| locked_table / locked_index | Bảng và index liên quan |
| requested_lock_mode | Lock waiter đang yêu cầu |
| blocking_lock_mode | Lock blocker đang giữ |
| blocking_trx_started | Thời điểm transaction blocker bắt đầu |
| blocking_trx_age_seconds | Tuổi transaction, hữu ích khi blocker đã Sleep |
| blocking_current_sql | Câu SQL hiện đang chạy, có thể NULL nếu session đang idle |

PROCESSLIST_TIME là thời gian session ở trạng thái hiện tại, không phải tuổi transaction. Muốn biết transaction đã mở bao lâu, xem trx_started.

Nếu blocker đang Sleep, PROCESSLIST_INFO và trx_query có thể là NULL vì không còn statement đang chạy. Điều đó không có nghĩa session không giữ lock. Hãy xem transaction age, trạng thái connection và log câu SQL trước đó.

### 5.1. Dùng sys schema nếu đã được cài đặt

MySQL thường cung cấp view **sys.innodb_lock_waits** để trình bày lock wait dễ đọc hơn:

~~~sql
SELECT *
FROM sys.innodb_lock_waits;
~~~

View này thường có các trường như waiting_pid, blocking_pid, wait_age, locked_table, locked_index, waiting_query, blocking_query và tuổi transaction blocker. Tên/cột cụ thể phụ thuộc phiên bản và sys schema được cài đặt.

### 5.2. Xem transaction đang mở kể cả khi không còn câu SQL chạy

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_mysql_thread_id AS connection_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Một transaction có trx_query NULL vẫn có thể đang mở và giữ lock. Hãy đối chiếu connection_id với SHOW PROCESSLIST hoặc Performance Schema.

## 6. Xác định root blocker trong wait graph

Để tìm root blocker, cần xem session nào đang xuất hiện ở vai trò blocker nhưng không xuất hiện ở vai trò waiter trong các cạnh đang quan sát.

Với MySQL 8, có thể dựng danh sách cạnh từ data_lock_waits:

~~~sql
WITH waits AS (
    SELECT
        REQUESTING_THREAD_ID AS waiter_thread_id,
        BLOCKING_THREAD_ID AS blocker_thread_id
    FROM performance_schema.data_lock_waits
)
SELECT DISTINCT
    t.PROCESSLIST_ID AS root_blocker_connection_id,
    t.PROCESSLIST_USER AS root_blocker_user,
    t.PROCESSLIST_COMMAND AS root_blocker_command,
    t.PROCESSLIST_INFO AS root_blocker_current_sql
FROM waits AS w
JOIN performance_schema.threads AS t
    ON t.THREAD_ID = w.blocker_thread_id
WHERE NOT EXISTS (
    SELECT 1
    FROM waits AS next_wait
    WHERE next_wait.waiter_thread_id = w.blocker_thread_id
);
~~~

Trong chuỗi A → B → C, A là root blocker vì A chặn B nhưng bản thân A không chờ một thread khác trong graph.

Đây là cách tìm ứng viên root blocker trong snapshot hiện tại. Nếu có nhiều bảng, nhiều loại lock hoặc quyền quan sát không đầy đủ, kết quả có thể chưa phản ánh toàn bộ hệ thống. Một blocker cũng có thể đang chờ tài nguyên ngoài phạm vi query đang xem.

## 7. PostgreSQL: tìm blocker trực tiếp bằng pg_blocking_pids

PostgreSQL cung cấp hàm **pg_blocking_pids(pid)** để trả về PID của các session đang chặn một backend.

Truy vấn sau dựng quan hệ waiter/blocker và kèm thông tin session:

~~~sql
SELECT
    blocked.pid AS waiting_pid,
    blocked.usename AS waiting_user,
    blocked.application_name AS waiting_application,
    blocked.client_addr AS waiting_client,
    blocked.state AS waiting_state,
    now() - blocked.query_start AS waiting_query_age,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.query AS waiting_query,

    blocker.pid AS blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_application,
    blocker.client_addr AS blocking_client,
    blocker.state AS blocking_state,
    blocker.xact_start AS blocking_xact_started,
    now() - blocker.xact_start AS blocking_xact_age,
    blocker.query AS blocking_current_or_last_query

FROM pg_stat_activity AS blocked

CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)

JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid

WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocker.xact_start NULLS LAST, blocked.pid;
~~~

Cách đọc:

- waiting_pid: backend đang chờ.
- blocking_pid: backend đang chặn.
- wait_event_type và wait_event: loại sự kiện chờ.
- waiting_query: câu SQL đang chờ.
- blocking_state: blocker đang active hay idle.
- blocking_xact_started và blocking_xact_age: thời điểm và tuổi transaction blocker.
- blocking_current_or_last_query: query hiện tại hoặc query gần nhất tùy trạng thái backend.

Một blocker ở trạng thái idle in transaction có thể không có câu SQL đang chạy nhưng vẫn giữ lock. Hãy xem xact_start, state và query gần nhất để hiểu nó đã làm gì trước khi trở nên idle.

### 7.1. Xem các transaction kéo dài

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Truy vấn này hữu ích để tìm transaction lâu, đặc biệt session idle in transaction. Không phải mọi transaction lâu đều đang chặn session khác; cần ghép với pg_blocking_pids hoặc pg_locks.

### 7.2. Xem lock chưa được cấp

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    l.waitstart,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE NOT l.granted
ORDER BY l.waitstart;
~~~

pg_locks cho biết lock đang được giữ hoặc yêu cầu. Để biết backend nào thực sự chặn backend nào, pg_blocking_pids thường dễ dùng và chính xác hơn việc tự ghép mọi lock mode bằng tay.

Một số lock là relation-level, transaction ID, advisory lock hoặc loại tài nguyên khác; không phải tất cả đều là row lock.

## 8. SQL Server: tìm session bị chặn và blocker

SQL Server cung cấp các dynamic management views (DMVs) để quan sát request đang chạy, session và lock wait.

Truy vấn sau tìm các request có blocker trực tiếp:

~~~sql
SELECT
    r.session_id AS waiting_session_id,
    r.blocking_session_id,
    r.status AS waiting_request_status,
    r.wait_type,
    r.wait_time AS wait_time_ms,
    r.wait_resource,
    DB_NAME(r.database_id) AS database_name,
    s.login_name AS waiting_login,
    s.host_name AS waiting_host,
    s.program_name AS waiting_program,
    waiting_sql.text AS waiting_sql,

    blocker_session.status AS blocker_session_status,
    blocker_session.open_transaction_count AS blocker_open_tran_count,
    blocker_session.login_name AS blocker_login,
    blocker_session.host_name AS blocker_host,
    blocker_session.program_name AS blocker_program,
    blocker_input.event_info AS blocker_last_input

FROM sys.dm_exec_requests AS r

JOIN sys.dm_exec_sessions AS s
    ON s.session_id = r.session_id

LEFT JOIN sys.dm_exec_sessions AS blocker_session
    ON blocker_session.session_id = r.blocking_session_id

OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS waiting_sql

OUTER APPLY sys.dm_exec_input_buffer(
    r.blocking_session_id,
    NULL
) AS blocker_input

WHERE r.blocking_session_id > 0
ORDER BY r.wait_time DESC;
~~~

Các cột cần xem:

- waiting_session_id: session đang chờ.
- blocking_session_id: session đang chặn.
- wait_type: loại wait, ví dụ LCK_M_X hoặc LCK_M_S.
- wait_resource: tài nguyên đang chờ.
- wait_time_ms: thời gian chờ hiện tại.
- blocker_session_status: blocker có thể đang sleeping.
- blocker_open_tran_count: số transaction mở theo session.
- blocker_last_input: input gần nhất được ghi nhận cho blocker.

Nếu blocker không có request đang chạy, nó sẽ không xuất hiện như một request trong sys.dm_exec_requests. Vì vậy, chỉ truy vấn DMV này có thể không cho thấy câu SQL đã lấy lock trước đó. Hãy kiểm tra session, transaction và input buffer.

### 8.1. Xem transaction đang mở và tuổi transaction

~~~sql
SELECT
    s.session_id,
    s.status AS session_status,
    s.login_name,
    s.host_name,
    s.program_name,
    s.open_transaction_count,
    act.transaction_begin_time,
    DATEDIFF(SECOND, act.transaction_begin_time, SYSDATETIME())
        AS transaction_age_seconds,
    ib.event_info AS last_input
FROM sys.dm_tran_session_transactions AS st
JOIN sys.dm_tran_active_transactions AS act
    ON act.transaction_id = st.transaction_id
JOIN sys.dm_exec_sessions AS s
    ON s.session_id = st.session_id
OUTER APPLY sys.dm_exec_input_buffer(s.session_id, NULL) AS ib
ORDER BY act.transaction_begin_time;
~~~

Truy vấn giúp tìm session có transaction mở lâu, kể cả khi session không có request active.

### 8.2. Tìm root blocker trong danh sách request đang chờ

~~~sql
WITH waiting AS (
    SELECT
        session_id,
        blocking_session_id
    FROM sys.dm_exec_requests
    WHERE blocking_session_id > 0
)
SELECT DISTINCT
    w.blocking_session_id AS root_blocker_candidate
FROM waiting AS w
WHERE NOT EXISTS (
    SELECT 1
    FROM waiting AS next_wait
    WHERE next_wait.session_id = w.blocking_session_id
);
~~~

Đây là root blocker trong phạm vi các request được quan sát. Một số giá trị âm của blocking_session_id là mã đặc biệt, không phải session_id thông thường. Ví dụ -2 có thể chỉ transaction phân tán mồ côi; các giá trị khác biểu thị tình trạng tài nguyên đặc biệt. Không join chúng như session ID dương.

### 8.3. Xem lock trong SQL Server

~~~sql
SELECT
    request_session_id,
    resource_type,
    resource_database_id,
    resource_associated_entity_id,
    request_mode,
    request_status,
    request_owner_type
FROM sys.dm_tran_locks
ORDER BY request_session_id, resource_type;
~~~

DMV này cho biết lock được yêu cầu và trạng thái GRANT/WAIT. Cần ghép với request, session, transaction và execution plan để xác định chính xác blocker.

Một số DMV yêu cầu quyền như VIEW SERVER STATE hoặc quyền tương ứng theo phiên bản SQL Server.

## 9. Cách lần ngược blocking chain

Khi nhận được danh sách waiter/blocker, hãy xử lý theo thứ tự:

1. Chọn session bị ảnh hưởng có thời gian chờ hoặc mức độ ưu tiên cao.
2. Tìm blocker trực tiếp của session đó.
3. Kiểm tra blocker có đang chờ session khác không.
4. Nếu có, tiếp tục lần ngược.
5. Dừng ở blocker không bị chặn trong graph hiện tại.
6. Kiểm tra transaction age, trạng thái session, câu SQL hiện tại hoặc câu SQL gần nhất.
7. Xác định tài nguyên đang bị giữ và công việc nghiệp vụ liên quan.
8. Tìm lý do transaction chưa commit hoặc rollback.

Ví dụ bảng quan hệ:

| Waiter | Blocker | Tài nguyên | Ý nghĩa |
|---|---|---|---|
| B | A | accounts row 1 | B cần hàng 1 mà A giữ |
| C | B | accounts row 2 | C cần hàng 2 mà B giữ |

Đừng chỉ đếm số waiter của một session. Một root blocker có thể chặn nhiều nhánh:

~~~text
              A
          (root blocker)
           /        \
          v          v
          B          C
         / \          \
        v   v          v
        D   E          F
~~~

Nếu A kết thúc transaction, nhiều session có thể được giải phóng cùng lúc. Tuy nhiên, B hoặc C có thể tiếp tục giữ lock và trở thành blocker mới cho các session phía dưới. Vì vậy, sau khi root blocker được giải phóng, hãy quan sát lại graph nếu ứng dụng vẫn còn wait.

## 10. Phân biệt blocker gốc với session chỉ đang chuyển tiếp lock wait

Một session nằm giữa chuỗi có hai vai trò:

- Nó đang chờ một session phía trên.
- Nó vẫn có thể giữ lock đã lấy trước khi bắt đầu chờ, từ đó chặn session phía dưới.

Trong thực nghiệm:

- B chờ A trên hàng 1.
- B vẫn giữ lock hàng 2 đã lấy trước đó.
- C chờ B trên hàng 2.

Nếu chỉ nhìn C, người điều tra có thể kết luận B là nguyên nhân. Nhưng B cũng đang bị A chặn. Giải phóng B bằng cách xử lý đúng root blocker A có thể làm cả chuỗi tiến triển.

Ngược lại, nếu B có transaction mở lâu do ứng dụng giữ lock hàng 2 rồi gọi dịch vụ ngoài, B có thể là nguyên nhân chính khiến C chờ, dù B đang đồng thời bị một session khác chặn. Phải xem toàn bộ chuỗi và thời gian transaction để xác định nguyên nhân gốc.

## 11. Session đang Sleep hoặc idle in transaction cần được chú ý

Một blocker không có câu SQL hiện tại là tình huống phổ biến trong production.

### MySQL

Trong SHOW PROCESSLIST, session có thể hiện Command = Sleep. Nhưng information_schema.innodb_trx vẫn có transaction đang mở với trx_started cũ.

Điều tra connection ID, transaction start time, rows locked và rows modified, query gần nhất trong application log hoặc general/audit log nếu có, application name, host và user, cùng request trace đã mở transaction.

### PostgreSQL

pg_stat_activity.state = 'idle in transaction' cho biết backend không chạy câu lệnh nhưng transaction vẫn mở.

Các trường quan trọng:

- xact_start: thời điểm transaction bắt đầu.
- state_change: thời điểm trạng thái thay đổi.
- query: câu lệnh hiện tại hoặc gần nhất.
- application_name: ứng dụng kết nối.
- client_addr: địa chỉ client.

idle in transaction kéo dài có thể giữ row lock và ngăn VACUUM loại bỏ một số tuple cũ cần thiết.

### SQL Server

Một session có thể không có request active nhưng vẫn có transaction mở. Xem open_transaction_count, sys.dm_tran_session_transactions và sys.dm_tran_active_transactions.

Nếu session thuộc connection pool, cần tìm request hoặc thread ứng dụng đã mượn connection và không kết thúc transaction đúng cách.

## 12. Xác định tài nguyên thực sự bị chặn

Một wait không phải lúc nào cũng là row lock. Cần xem loại tài nguyên:

- Row/key lock.
- Page lock.
- Table/object lock.
- Key-range/gap/next-key lock.
- Metadata lock.
- Transaction ID lock.
- Advisory/application lock.
- Schema stability/modification lock.
- Latch hoặc tài nguyên nội bộ khác.

Ví dụ, MySQL có thể chờ record/gap/next-key lock hoặc metadata lock; PostgreSQL có row-level, relation-level, transaction ID và advisory lock; SQL Server có KEY, RID, PAGE, OBJECT, METADATA và nhiều loại lock khác.

Nếu wait event không phải lock, các truy vấn tìm blocker theo row lock có thể không giải thích được sự cố. Hãy xem wait type/event cụ thể và công cụ tương ứng của engine.

## 13. Metadata lock có thể chặn cả truy vấn tưởng như không liên quan

Ở MySQL, DDL như ALTER TABLE cần metadata lock. Một transaction đang sử dụng bảng có thể giữ metadata lock cho đến khi transaction kết thúc. Khi DDL chờ, những truy vấn mới trên bảng cũng có thể bị xếp hàng phía sau DDL đang chờ, tùy tình huống.

Ví dụ:

~~~text
Session A:
    START TRANSACTION
    SELECT ... FROM orders
    -- Chưa kết thúc transaction

Session B:
    ALTER TABLE orders ADD COLUMN note VARCHAR(100)
    -- Chờ metadata lock

Session C:
    SELECT ... FROM orders
    -- Có thể bị ảnh hưởng bởi DDL đang chờ
~~~

Khi thấy nhiều query cùng chờ trên một bảng, đừng mặc định có một row UPDATE đang chặn tất cả. Kiểm tra metadata lock và DDL đang chờ.

MySQL 8 có thể quan sát metadata lock qua performance_schema.metadata_locks nếu instrument phù hợp được bật. Ví dụ:

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING'
   OR LOCK_STATUS = 'GRANTED';
~~~

Ghép OWNER_THREAD_ID với performance_schema.threads để tìm connection ID. Không phải mọi metadata lock đều là nguyên nhân chặn; hãy tập trung vào lock PENDING và các lock GRANTED tương ứng trên cùng object.

## 14. Khi nào nên hủy session blocker?

Hủy session có thể giải phóng chuỗi chờ, nhưng cũng có thể làm rollback một transaction lớn hoặc hủy một công việc nghiệp vụ đang hợp lệ. Không nên kill chỉ dựa trên việc session có nhiều waiter.

Trước khi can thiệp, xác định chủ sở hữu connection và service, transaction đang làm nghiệp vụ gì, transaction đã thay đổi bao nhiêu dữ liệu, nó có đang thực hiện công việc không thể lặp an toàn không, có thể yêu cầu ứng dụng hoàn tất hoặc rollback có kiểm soát không, ảnh hưởng của rollback đến thời gian và tải database, và có maintenance hoặc batch job đang chạy hợp lệ không.

### MySQL

- **KILL QUERY connection_id** dừng statement hiện tại, nhưng không nhất thiết kết thúc transaction hoặc giải phóng tất cả lock.
- **KILL CONNECTION connection_id** đóng connection; transaction chưa commit sẽ được InnoDB rollback, việc rollback có thể mất thời gian.

### PostgreSQL

- **pg_cancel_backend(pid)** yêu cầu hủy query hiện tại. Trong explicit transaction, transaction có thể chuyển sang trạng thái aborted và vẫn cần ROLLBACK để kết thúc.
- **pg_terminate_backend(pid)** kết thúc backend và database rollback transaction chưa commit.

### SQL Server

- **KILL session_id** kết thúc session và rollback transaction. Rollback có thể tiếp tục trong nền và có thể kéo dài nếu transaction đã thay đổi nhiều dữ liệu.

Ưu tiên xử lý từ ứng dụng hoặc chủ sở hữu transaction khi có thể. Nếu cần can thiệp, ghi nhận session ID, SQL, transaction age, lý do và thời điểm trước khi thực hiện. Sau khi hủy, theo dõi rollback và xác nhận lock wait đã biến mất.

## 15. Vì sao không nên chỉ kill waiter?

Kill waiter thường chỉ hủy request đang chờ. Root blocker vẫn giữ lock, nên những session khác tiếp tục bị chặn.

Ví dụ:

~~~text
A giữ lock
 |
 +--> B chờ A
 |
 +--> C chờ A
~~~

Nếu kill B, C vẫn chờ A. Nếu A là transaction bị bỏ quên, xử lý B không giải quyết nguyên nhân.

Tuy nhiên, đôi khi cần hủy waiter nếu request đã hết deadline, client đã ngắt kết nối hoặc công việc không còn cần thiết. Quyết định phải dựa trên ownership và semantics của request.

## 16. Dấu hiệu root blocker có thể là nguyên nhân ứng dụng

Một số mẫu thường gặp:

### Transaction mở lâu nhưng session idle

Có thể ứng dụng bắt đầu transaction rồi chờ HTTP, xử lý logic hoặc quên commit/rollback.

### Một câu UPDATE nhỏ chặn rất nhiều session

Có thể đó là hàng nóng (hot row), tài khoản tổng hợp, bộ đếm, trạng thái đơn hàng hoặc một record được nhiều request cập nhật.

### DDL đang chờ metadata lock

Có thể transaction cũ đang dùng bảng và giữ metadata lock; DDL chờ khiến truy vấn sau cũng bị ảnh hưởng.

### Blocking xuất hiện theo đợt

Có thể batch job cập nhật nhiều hàng, transaction quá dài, plan regression hoặc lượng request tăng đột ngột.

### Blocker có nhiều rows locked

Có thể transaction đang chạy batch lớn hoặc dùng truy vấn thiếu index khiến phạm vi truy cập rộng. Cần kiểm tra execution plan và số lock thực tế.

### Blocker là session từ công cụ quản trị

Có thể người vận hành đã mở transaction trong SQL client và quên commit/rollback sau khi thử UPDATE.

Các dấu hiệu chỉ giúp định hướng. Cần ghép wait graph với SQL, transaction age, lock resource và log ứng dụng trước khi kết luận.

## 17. Phân tích một blocking incident theo trình tự

Khi hệ thống báo request timeout hoặc latency tăng do database lock wait, quy trình điều tra nên đi từ triệu chứng đến root cause:

1. **Xác định waiter:** lấy session ID, câu SQL, thời gian chờ, database và resource.
2. **Tìm blocker trực tiếp:** dùng Performance Schema, pg_blocking_pids hoặc DMV.
3. **Lần ngược chuỗi:** xác định blocker nào đang chờ session khác.
4. **Tìm root blocker:** session giữ lock nhưng không bị chặn trong graph hiện tại.
5. **Kiểm tra transaction age:** phân biệt câu SQL chạy lâu với transaction mở lâu.
6. **Xác định trạng thái blocker:** active, sleeping, idle in transaction hoặc đang chờ tài nguyên khác.
7. **Xác định resource và lock mode:** record/key, range/gap, page, table, metadata hay advisory.
8. **Tìm câu lệnh đã lấy lock:** blocker có thể không còn query hiện tại; dùng log, trace và application correlation ID.
9. **Đánh giá phạm vi ảnh hưởng:** số waiter, nhánh của graph, thời gian chờ và workload bị ảnh hưởng.
10. **Chọn hành động:** chờ transaction hoàn tất, yêu cầu ứng dụng rollback, hủy query/session có kiểm soát hoặc xử lý lỗi ở tầng nghiệp vụ.
11. **Xác nhận phục hồi:** kiểm tra graph sau can thiệp, transaction đã kết thúc và request tiếp tục.
12. **Khắc phục nguyên nhân:** rút ngắn transaction, sửa thứ tự lock, thêm index phù hợp, giảm hot-row contention hoặc sửa connection lifecycle.

Trong incident, nên lưu lại kết quả chẩn đoán trước khi blocker biến mất. Lock wait là trạng thái động; sau khi transaction commit hoặc rollback, các hàng trong Performance Schema/DMV có thể không còn phản ánh sự cố vừa xảy ra.

## 18. Theo dõi liên tục thay vì chỉ chạy truy vấn khi có sự cố

Một truy vấn chẩn đoán thủ công là snapshot tại thời điểm chạy. Đối với hệ thống quan trọng, nên theo dõi các chỉ số:

- Số session đang chờ lock.
- Tổng thời gian lock wait.
- Tuổi transaction lâu nhất.
- Số transaction idle in transaction.
- Số waiter theo từng blocker.
- Bảng/index/resource thường xuyên xuất hiện trong wait.
- Deadlock count và deadlock graph.
- Tỷ lệ request timeout do database.
- Transaction duration p95/p99.
- Số lần retry và tỷ lệ retry thành công.

Cần tránh polling quá dày bằng truy vấn nặng trên catalog hoặc lock manager. Chọn tần suất phù hợp và ưu tiên công cụ monitoring/event có sẵn.

Với MySQL, có thể dùng Performance Schema và sys schema. Với PostgreSQL, có thể theo dõi pg_stat_activity, pg_locks, pg_stat_database và log lock wait. Với SQL Server, có thể dùng Extended Events, Query Store và DMVs.

Cần bảo vệ thông tin nhạy cảm trong SQL text và bind parameter khi lưu log. Quyền đọc metadata hệ thống cũng nên được cấp theo nguyên tắc tối thiểu.

## 19. Những nhầm lẫn thường gặp

**“Session có query chạy lâu nhất chắc chắn là blocker.”**

Không. Query lâu có thể chỉ là waiter. Phải xem quan hệ lock wait và session đang giữ lock.

**“Blocker phải đang chạy SQL.”**

Không. Session Sleep hoặc idle in transaction vẫn có thể giữ lock từ statement trước đó.

**“Session chặn C là nguyên nhân gốc.”**

Chưa chắc. Nó có thể đang bị A chặn và đồng thời giữ lock khiến C phải chờ. Hãy lần ngược toàn bộ chain.

**“Blocking chain dài là deadlock.”**

Không. Deadlock cần chu trình chờ khép kín. Chain một chiều có thể chỉ kết thúc khi root blocker commit/rollback.

**“Kill waiter sẽ giải phóng blocker.”**

Không. Kill waiter thường chỉ hủy request đang chờ; blocker vẫn giữ tài nguyên.

**“KILL QUERY tương đương rollback transaction.”**

Không. Dừng statement không nhất thiết kết thúc transaction. Kiểm tra transaction state và lock còn giữ sau khi hủy query.

**“Không thấy blocker query nghĩa là không có blocker.”**

Không. Session có thể idle, query text có thể NULL hoặc quyền quan sát không đủ. Kiểm tra transaction và session metadata.

**“Một lock wait luôn là row lock.”**

Không. Có thể là key-range, gap, metadata, advisory hoặc lock trên tài nguyên khác.

**“Chỉ cần tăng lock timeout là hết sự cố.”**

Không. Tăng timeout chỉ khiến request chờ lâu hơn. Nó không loại bỏ nguyên nhân giữ lock hoặc chuỗi chờ.

## 20. Checklist chẩn đoán nhanh

Khi nhận một incident blocking, ghi lại:

| Câu hỏi | Bằng chứng cần thu thập |
|---|---|
| Ai đang chờ? | Session ID, SQL, wait duration, wait resource |
| Ai chặn trực tiếp? | Blocking session ID hoặc PID |
| Có chuỗi nhiều tầng không? | Danh sách waiter → blocker |
| Root blocker là ai? | Blocker không bị chặn trong graph hiện tại |
| Transaction mở bao lâu? | Transaction start time và tuổi transaction |
| Blocker đang làm gì? | Current/last SQL, state, application/host |
| Lock nào xung đột? | Object, index, resource, lock mode |
| Đây là blocking hay deadlock? | Wait graph hoặc deadlock graph |
| Có phải session idle? | Sleep/idle in transaction/open transaction count |
| Hành động nào an toàn? | Owner, business operation, rollback impact |
| Đã phục hồi chưa? | Wait graph biến mất, request tiếp tục, transaction kết thúc |
| Nguyên nhân lâu dài là gì? | Transaction scope, hot row, index, plan, lock ordering, connection lifecycle |

## Kết luận

Muốn xác định phiên giữ khóa, hãy dựng quan hệ waiter → blocker và lần ngược blocking chain đến root blocker. Một session có thể vừa chờ session phía trên vừa giữ lock chặn session phía dưới; vì vậy chỉ xử lý blocker trực tiếp của request cuối chuỗi có thể không giải quyết được sự cố. Session Sleep hoặc idle in transaction vẫn có thể giữ lock dù không còn câu SQL đang chạy.

MySQL 8 có performance_schema.data_lock_waits và data_locks; PostgreSQL có pg_blocking_pids, pg_stat_activity và pg_locks; SQL Server có sys.dm_exec_requests, sys.dm_exec_sessions, sys.dm_tran_locks và các transaction DMV. Hãy kết hợp các nguồn này với tuổi transaction, trạng thái session, SQL hiện tại hoặc gần nhất và tài nguyên bị khóa.

Blocking chain là chuỗi chờ có hướng; deadlock là chu trình chờ. Khi xử lý, cần phân biệt hai tình huống, xác định root blocker và hiểu tác động của việc hủy query hoặc session. Sau khi giải phóng blocker, hãy kiểm tra lại graph và sửa nguyên nhân ở tầng ứng dụng hoặc database để tránh sự cố lặp lại.
