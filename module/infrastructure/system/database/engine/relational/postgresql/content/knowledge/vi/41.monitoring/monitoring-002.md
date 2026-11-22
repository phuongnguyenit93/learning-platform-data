# pg_stat_activity, trạng thái phiên và truy vấn đang chạy trong PostgreSQL

Khi PostgreSQL chậm, nhiều kết nối tăng bất thường hoặc một câu lệnh bị treo, câu hỏi đầu tiên của người vận hành thường là: **đang có những phiên nào kết nối, mỗi phiên đang làm gì và phiên nào đang chờ tài nguyên?** View hệ thống pg_stat_activity là điểm bắt đầu quan trọng để trả lời những câu hỏi đó.

pg_stat_activity cung cấp một dòng cho mỗi server process, bao gồm các client sessions và nhiều background processes của PostgreSQL. View này cho biết database, user, application, trạng thái phiên, câu truy vấn hiện tại hoặc gần nhất, thời điểm bắt đầu query/transaction và wait event nếu process đang chờ.

View này là ảnh chụp hoạt động tại thời điểm truy vấn. Nó giúp quan sát tình trạng hiện tại, tìm query chạy lâu, phát hiện transaction bị bỏ quên, xác định lock wait và tìm ứng dụng tạo nhiều connections. Nó không phải kho lịch sử đầy đủ của mọi câu lệnh đã chạy; để phân tích lịch sử cần kết hợp logging, pg_stat_statements hoặc hệ thống observability khác.

Bài học này giải thích cách đọc pg_stat_activity, hiểu session states và wait events, đo thời gian query/transaction, tìm blockers, xử lý sessions an toàn và xây các truy vấn giám sát có thể dùng trong vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích pg_stat_activity và quan hệ của view này với PostgreSQL server processes.
2. Phân biệt client backend với background worker.
3. Đọc các cột nhận diện database, user, client, application và process.
4. Phân biệt active, idle, idle in transaction và idle in transaction (aborted).
5. Hiểu state, wait_event_type và wait_event.
6. Đo query age, transaction age và thời gian phiên ở trạng thái hiện tại.
7. Tìm các câu lệnh active chạy lâu và các phiên chờ lock.
8. Dùng pg_blocking_pids để tìm blocker.
9. Phân biệt query đang chạy với query gần nhất của một session idle.
10. Hiểu giới hạn quyền xem activity của user khác.
11. Dùng pg_cancel_backend và pg_terminate_backend đúng tình huống.
12. Kết hợp pg_stat_activity với pg_locks, pg_stat_ssl, pg_stat_progress_* và pg_stat_statements.
13. Xây dashboard, alerts và quy trình troubleshooting.
14. Tránh các sai lầm khi diễn giải dữ liệu giám sát.

## 2. pg_stat_activity là gì?

pg_stat_activity là một statistics/activity view trong schema hệ thống pg_catalog. Mỗi dòng đại diện cho một server process của PostgreSQL tại thời điểm quan sát.

~~~text
PostgreSQL server
    |
    +-- Client backend (application session)
    |
    +-- Client backend (psql session)
    |
    +-- Autovacuum worker
    |
    +-- WAL sender
    |
    +-- Background writer / checkpointer
    |
    +-- Parallel worker
    |
    +-- Other background processes
             |
             v
       pg_stat_activity
             |
             v
       Session, query, state, wait event
~~~

### 2.1. Một dòng không nhất thiết là một người dùng

Một dòng có thể đại diện cho:
- Kết nối từ application server.
- Kết nối từ connection pool.
- Phiên psql hoặc công cụ quản trị.
- Autovacuum worker.
- WAL sender/receiver.
- Background worker hoặc parallel query worker.

Vì vậy, không đếm mọi dòng như số người dùng cuối. Hãy lọc backend_type hoặc các thuộc tính phù hợp với phiên bản.

### 2.2. View hoạt động hiện tại

pg_stat_activity cho biết trạng thái mà PostgreSQL ghi nhận cho process. Nó không lưu một bản ghi riêng cho mọi statement trong quá khứ.

Nếu session đang active, cột query thể hiện câu lệnh hiện tại. Nếu session idle, query thường là câu lệnh gần nhất mà session đã thực thi. Không được đọc query của session idle như thể câu lệnh đó vẫn đang chạy.

### 2.3. Kiểm tra view

~~~sql
SELECT *
FROM pg_stat_activity
LIMIT 5;
~~~

Trong môi trường thực tế, tránh phụ thuộc mù quáng vào SELECT * trong dashboard hoặc automation vì schema view có thể thay đổi theo PostgreSQL major version. Chọn tường minh các cột cần dùng.

## 3. Các cột quan trọng

Một số cột thường dùng:

| Cột | Ý nghĩa |
| --- | --- |
| pid | Process ID của server process |
| datid | OID của database |
| datname | Tên database |
| usesysid | OID của user |
| usename | Tên user |
| application_name | Tên client/application gửi lên |
| client_addr | Địa chỉ IP của client; NULL với một số local/background processes |
| client_hostname | Hostname của client nếu được phân giải |
| client_port | TCP port phía client |
| backend_start | Thời điểm process/session bắt đầu |
| xact_start | Thời điểm transaction hiện tại bắt đầu |
| query_start | Thời điểm query hiện tại bắt đầu nếu active; nếu không active là thời điểm query gần nhất bắt đầu |
| state_change | Thời điểm state thay đổi gần nhất |
| state | Trạng thái phiên |
| wait_event_type | Nhóm loại wait event |
| wait_event | Tên wait event cụ thể |
| backend_type | Loại server process, nếu phiên bản cung cấp |
| backend_xid | Transaction ID của transaction hiện tại nếu có |
| backend_xmin | Oldest xmin được backend giữ trong snapshot nếu có |
| query_id | Identifier của query nếu tính năng query ID được bật và có thể xác định |
| query | Câu lệnh hiện tại hoặc gần nhất, tùy state |
| leader_pid | PID của parallel group leader nếu process là parallel worker |

### 3.1. PID

PID dùng để nhận diện process trong các system views và truyền cho các hàm cancel/terminate. PID có thể thay đổi sau khi reconnect; không lưu PID như định danh lâu dài của application session.

### 3.2. Database và user

datname và usename cho biết session làm việc trong database nào và dưới role nào. Các trường này có thể NULL với một số background processes không gắn với database/user thông thường.

### 3.3. Application name

application_name giúp phân biệt các service hoặc component. Đặt tên rõ trong connection string hoặc session:

~~~sql
SET application_name = 'orders-api';
~~~

Có thể dùng tên như orders-api, billing-worker, reporting-job hoặc migration-runner. Tên nhất quán giúp tìm nguồn tạo connections và query.

### 3.4. Client address

client_addr có thể NULL với Unix-domain socket, background process hoặc kết nối không có địa chỉ IP thông thường. Đừng coi NULL tự động là lỗi.

### 3.5. Thời điểm

backend_start đo tuổi của session. xact_start đo tuổi transaction. query_start đo thời điểm bắt đầu query gần nhất/hiện tại theo state. Ba mốc này trả lời các câu hỏi khác nhau.

### 3.6. Query text

query có thể bị cắt ngắn theo track_activity_query_size. Nó cũng có thể chứa literal values nhạy cảm. Hạn chế quyền đọc activity và cân nhắc masking ở application/logging layer.

## 4. Truy vấn xem sessions cơ bản

Một truy vấn hữu ích để xem client sessions:

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    backend_start,
    state_change,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

backend_type có trong các PostgreSQL versions hiện đại; nếu phải hỗ trợ version cũ hơn, kiểm tra schema và điều chỉnh filter.

### 4.1. Loại trừ session đang chạy truy vấn giám sát

Mỗi lần bạn truy vấn pg_stat_activity, chính session quản trị cũng có thể xuất hiện:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid();
~~~

pg_backend_pid() trả PID của session hiện tại.

### 4.2. Xem sessions theo database

~~~sql
SELECT
    datname,
    count(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname
ORDER BY session_count DESC;
~~~

### 4.3. Xem sessions theo user và application

~~~sql
SELECT
    usename,
    application_name,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY usename, application_name
ORDER BY sessions DESC;
~~~

Dùng truy vấn này để tìm application mở quá nhiều connections hoặc không đặt application_name.

## 5. Hiểu session state

Cột state mô tả backend đang làm gì ở mức session/query.

| State | Ý nghĩa |
| --- | --- |
| active | Backend đang thực thi một query |
| idle | Backend đang chờ client gửi query tiếp theo |
| idle in transaction | Backend đang ở trong transaction nhưng không thực thi query |
| idle in transaction (aborted) | Transaction đã lỗi và đang chờ ROLLBACK/đóng transaction |
| fastpath function call | Backend đang thực hiện fast-path function call |
| disabled | Activity tracking bị tắt cho backend |

Tên và các trạng thái cụ thể cần đối chiếu với tài liệu major version đang dùng.

### 5.1. active

Session đang thực thi query. Tuy nhiên, active không có nghĩa query đang dùng CPU liên tục. Nó có thể đang chờ lock, I/O, client hoặc một sự kiện khác.

Để hiểu active session, đọc state cùng wait_event_type và wait_event.

### 5.2. idle

Session đã hoàn thành query gần nhất và đang chờ client gửi lệnh mới. Với connection pool, một số idle sessions là bình thường.

Idle sessions vẫn chiếm connection slots và một phần tài nguyên process. Quá nhiều idle sessions có thể phản ánh pool sizing không hợp lý hoặc ứng dụng mở connections không giới hạn.

### 5.3. idle in transaction

Session đã chạy BEGIN hoặc statement bắt đầu transaction nhưng hiện không chạy query và chưa kết thúc transaction. Đây là trạng thái cần chú ý vì transaction có thể giữ locks, snapshot và ngăn vacuum loại bỏ versions cũ.

Một transaction bỏ quên có thể làm:
- Table/index bloat tăng.
- Autovacuum không dọn được dead tuples cũ.
- Các transaction khác bị block.
- xmin bị giữ lâu.
- Áp lực transaction ID tăng trong trường hợp kéo dài nghiêm trọng.

### 5.4. idle in transaction (aborted)

Một statement trong transaction đã lỗi. Transaction đang ở trạng thái aborted và không thể tiếp tục các statements thông thường cho tới khi ROLLBACK hoặc kết thúc transaction. Ứng dụng cần xử lý lỗi và đóng transaction đúng cách.

### 5.5. idle không phải lỗi

Một pool giữ sẵn vài connections ở trạng thái idle có thể là thiết kế bình thường. Hãy so sánh với pool configuration, max_connections, workload và connection wait time trước khi kết luận.

## 6. State và wait event là hai khái niệm khác nhau

state trả lời backend có đang thực thi query hay không. wait_event_type và wait_event cho biết backend đang chờ loại sự kiện nào.

Ví dụ:
- state=active, wait_event=NULL: query đang hoạt động và tại thời điểm lấy mẫu không báo wait event.
- state=active, wait_event_type=Lock: query đang active nhưng chờ lock.
- state=idle, wait_event_type=Client: backend có thể đang chờ client gửi dữ liệu/lệnh tiếp theo.
- state=idle in transaction: transaction mở nhưng session đang không chạy statement; có thể vẫn giữ locks/snapshot.

### 6.1. Các nhóm wait event

Tùy phiên bản, wait_event_type có thể bao gồm các nhóm như:

| Nhóm | Ý nghĩa tổng quát |
| --- | --- |
| Lock | Chờ heavyweight lock |
| LWLock | Chờ lightweight lock nội bộ |
| BufferPin | Chờ pin trên buffer |
| IO | Chờ I/O |
| Client | Chờ hoạt động từ client/network |
| Activity | Chờ một hoạt động nội bộ hoặc background process |
| IPC | Chờ inter-process communication |
| Timeout | Chờ timeout |
| Extension | Chờ do extension định nghĩa |

Danh sách cụ thể và tên wait_event thay đổi theo phiên bản. Xem catalog documentation hoặc tra cứu wait event tương ứng trong tài liệu PostgreSQL.

### 6.2. Query active nhưng đang chờ

Một query có state=active và wait_event_type=Lock vẫn được coi là active vì statement chưa hoàn tất. Nó không nhất thiết đang tiêu thụ CPU.

### 6.3. Wait event NULL

NULL không có nghĩa query chắc chắn chạy nhanh hoặc không có vấn đề. Nó chỉ có nghĩa backend không báo một wait event tại thời điểm quan sát.

### 6.4. ClientRead

Một session idle chờ client gửi query có thể có wait event thuộc nhóm Client, ví dụ ClientRead. Đây thường là trạng thái bình thường của connection đang chờ lệnh.

## 7. Xem query đang chạy

Dùng truy vấn sau để liệt kê các query active:

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
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

### 7.1. query_age

Đo khoảng thời gian kể từ query_start. Chỉ diễn giải như thời gian chạy của query khi state=active.

### 7.2. transaction_age

Đo thời gian từ xact_start. Một query vừa chạy vài mili giây có thể nằm trong transaction đã mở hàng giờ.

### 7.3. Query gần nhất của session idle

Nếu state không phải active, query thường là câu lệnh gần nhất. Không tính clock_timestamp()-query_start rồi gọi đó là query execution duration cho idle session.

### 7.4. Lọc query lâu hơn ngưỡng

Ví dụ tìm query active hơn 30 giây:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    clock_timestamp() - query_start AS duration,
    wait_event_type,
    wait_event,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start < clock_timestamp() - interval '30 seconds'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

Ngưỡng 30 giây chỉ là ví dụ. Chọn theo workload và SLA; một query analytical chạy 5 phút có thể bình thường trong khi một OLTP query 5 giây có thể đáng điều tra.

## 8. Phân biệt query age, transaction age và session age

Ba chỉ số này thường bị nhầm.

| Chỉ số | Công thức | Trả lời câu hỏi |
| --- | --- | --- |
| Session age | now - backend_start | Connection/process đã tồn tại bao lâu? |
| Transaction age | now - xact_start | Transaction hiện tại đã mở bao lâu? |
| Query age | now - query_start khi active | Statement hiện tại đã chạy bao lâu? |
| State age | now - state_change | Backend ở state hiện tại bao lâu? |

Ví dụ:
- Backend tồn tại 3 giờ.
- Transaction mở 45 phút.
- Query hiện tại chạy 2 giây.
- Session vừa chuyển sang active cách đây 2 giây.

Không thể kết luận transaction chỉ mới mở 2 giây dựa trên query_start.

### 8.1. Truy vấn đầy đủ

~~~sql
SELECT
    pid,
    state,
    clock_timestamp() - backend_start AS session_age,
    clock_timestamp() - xact_start AS transaction_age,
    CASE
        WHEN state = 'active'
        THEN clock_timestamp() - query_start
    END AS active_query_age,
    clock_timestamp() - state_change AS state_age,
    application_name,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY xact_start NULLS LAST, backend_start;
~~~

### 8.2. xact_start NULL

Nếu session không ở trong transaction hiện tại, xact_start có thể NULL. Không chuyển NULL thành 0 mà không giữ rõ semantics.

### 8.3. state_change

state_change cho biết thời điểm state gần nhất thay đổi. Một session idle lâu không có nghĩa query gần nhất vẫn chạy lâu.

## 9. Tìm idle-in-transaction sessions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS idle_duration,
    wait_event_type,
    wait_event,
    left(query, 1000) AS last_query
FROM pg_stat_activity
WHERE state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY xact_start;
~~~

### 9.1. Vì sao phải quan tâm?

Transaction mở lâu có thể giữ row/table locks và snapshot cũ. Điều này làm vacuum không thể reclaim dead tuples mà transaction vẫn có thể nhìn thấy.

### 9.2. Last query không phải query đang chạy

Ở idle-in-transaction, query thường là statement gần nhất. Hãy đọc state để biết backend không còn thực thi statement đó.

### 9.3. Tìm transaction cũ nhất

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 500) AS last_or_current_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 20;
~~~

### 9.4. Nguyên nhân trong ứng dụng

- Mở transaction trước khi gọi một API bên ngoài.
- Quên COMMIT/ROLLBACK trong exception path.
- Connection pool trả connection về pool khi transaction vẫn mở.
- Interactive client giữ transaction trong lúc người dùng suy nghĩ.
- Job batch xử lý từng phần nhưng không đóng transaction.
- Code dùng BEGIN nhưng không có finally/cleanup.

### 9.5. Cấu hình timeout

Có thể cân nhắc:
- idle_in_transaction_session_timeout: kết thúc session idle trong transaction quá lâu.
- idle_session_timeout: giới hạn session idle, cần cân nhắc connection pools.
- statement_timeout: giới hạn thời gian thực thi statement.
- lock_timeout: giới hạn thời gian chờ lock.

Đặt timeout theo role/database/application và workload. Không dùng một giá trị chung cho mọi session mà không kiểm thử.

## 10. Tìm query đang chờ lock

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    clock_timestamp() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND wait_event_type = 'Lock'
ORDER BY query_start;
~~~

### 10.1. Lock wait không tự giải thích blocker

pg_stat_activity cho biết session đang chờ lock. Để tìm backend đang chặn, dùng pg_blocking_pids(pid) và đối chiếu PID với pg_stat_activity.

### 10.2. Không chỉ nhìn query age

Một query có query_age lớn có thể đang chạy CPU-intensive, chờ I/O hoặc chờ lock. Kết hợp wait events và execution plan/metrics để tìm nguyên nhân.

### 10.3. Query bị block có thể kéo theo nhiều session

Một transaction giữ lock có thể block một query, rồi query đó lại giữ tài nguyên khiến nhiều sessions khác xếp hàng. Tìm blocker gốc thay vì cancel tất cả blocked queries.

## 11. Tìm blocking sessions bằng pg_blocking_pids

pg_blocking_pids(pid) trả về PID của các sessions đang block backend được truyền vào.

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocked.wait_event,
    left(blocked.query, 500) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 500) AS blocker_last_or_current_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocked.query_start;
~~~

### 11.1. Đọc kết quả

- blocked_pid: process đang chờ.
- blocker_pid: process giữ lock hoặc đứng trước trong hàng đợi lock.
- blocker_state: blocker có thể active hoặc idle in transaction.
- blocker_xact_age: transaction của blocker đã mở bao lâu.
- blocker_last_or_current_query: query hiện tại nếu active, hoặc query gần nhất nếu idle.

### 11.2. Blocker idle in transaction

Đây là tình huống đáng chú ý. Session có thể không chạy query nào nhưng vẫn giữ transaction/locks. Câu query hiển thị có thể là statement cuối cùng trước khi session trở thành idle in transaction.

### 11.3. Nhiều blockers

Một backend có thể có nhiều blocking PIDs. Query trên tạo một dòng cho mỗi cặp blocked/blocker. Kiểm tra toàn bộ nhóm trước khi quyết định cancel/terminate.

### 11.4. Blocking tree

Với incident phức tạp, dựng đồ thị blocked_pid → blocker_pid và tìm node chặn nhiều session nhất. Đừng chỉ sort theo query age; blocker gốc có thể có state idle.

## 12. Kết hợp pg_stat_activity với pg_locks

pg_locks hiển thị locks mà các processes đang giữ hoặc đang yêu cầu.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 500) AS query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
ORDER BY l.granted, a.pid;
~~~

### 12.1. granted

- true: lock đã được cấp.
- false: backend đang chờ lock.

### 12.2. relation

relation có thể NULL với lock không gắn trực tiếp với relation cụ thể. Ép regclass giúp đọc tên bảng khi có OID hợp lệ.

### 12.3. Lock modes

Các lock modes như AccessShareLock, RowShareLock, RowExclusiveLock, ShareLock và AccessExclusiveLock có semantics khác nhau. Không kết luận chỉ từ tên lock; kiểm tra conflict matrix và operation đang thực hiện.

### 12.4. pg_locks không thay pg_blocking_pids

pg_locks cho chi tiết lock objects/modes; pg_blocking_pids thường là cách thuận tiện để tìm sessions đang block một PID. Dùng kết hợp khi cần phân tích sâu.

## 13. Xem session theo application và client

### 13.1. Connections theo application

~~~sql
SELECT
    COALESCE(application_name, '(unset)') AS application,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY COALESCE(application_name, '(unset)'), state
ORDER BY application, state;
~~~

### 13.2. Connections theo client address

~~~sql
SELECT
    client_addr,
    application_name,
    usename,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY client_addr, application_name, usename
ORDER BY sessions DESC;
~~~

### 13.3. Sessions theo database và state

~~~sql
SELECT
    datname,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, state
ORDER BY datname, state;
~~~

### 13.4. Không có application_name

Nếu nhiều sessions có application_name NULL hoặc rỗng, bổ sung tên cho từng service. Việc này cải thiện khả năng quy trách nhiệm khi điều tra.

### 13.5. Connection pool

Pool có thể giữ connections idle để tái sử dụng. Theo dõi số connections từ mỗi application instance, pool max size, active/idle pool clients và queue wait. PostgreSQL chỉ nhìn thấy server-side connections, không nhất thiết biết số request đang đợi bên trong pooler.

## 14. Xem backend types

Trên các phiên bản có cột backend_type:

~~~sql
SELECT
    backend_type,
    state,
    count(*) AS processes
FROM pg_stat_activity
GROUP BY backend_type, state
ORDER BY backend_type, state;
~~~

Một số loại process có thể gồm:
- client backend.
- autovacuum worker.
- background writer.
- checkpointer.
- WAL sender.
- WAL receiver.
- logical replication worker.
- parallel worker.
- background worker khác.

Danh sách phụ thuộc version và extensions. Background process không phải client session; query text có thể khác hoặc NULL.

## 15. Xem session đang dùng SSL

pg_stat_activity không chứa đầy đủ thông tin TLS. Join với pg_stat_ssl:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.bits
FROM pg_stat_activity AS a
LEFT JOIN pg_stat_ssl AS s
  ON s.pid = a.pid
WHERE a.backend_type = 'client backend'
ORDER BY a.pid;
~~~

### 15.1. SSL false

Một kết nối không dùng SSL có thể vẫn hợp lệ nếu policy cho phép, ví dụ Unix socket hoặc network nội bộ có kiểm soát. Đánh giá theo security policy, không chỉ nhìn boolean.

### 15.2. TLS configuration

Kết hợp pg_stat_ssl với ssl=on, pg_hba.conf và application connection settings. Xác minh client certificate requirements nếu sử dụng mutual TLS.

## 16. Query ID và liên kết với thống kê query

Một số PostgreSQL versions cung cấp query_id trong pg_stat_activity khi query identifier computation được bật và query có thể được nhận diện.

~~~sql
SELECT
    pid,
    query_id,
    state,
    clock_timestamp() - query_start AS query_age,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
~~~

### 16.1. query_id có thể NULL

Query ID có thể NULL nếu tính năng không được bật, query không có identifier hoặc version/configuration không cung cấp giá trị.

### 16.2. compute_query_id

Setting compute_query_id điều khiển việc tính query identifiers ở các versions hỗ trợ. Kiểm tra SHOW compute_query_id và documentation của major version.

### 16.3. pg_stat_statements

pg_stat_statements tổng hợp thống kê theo query identity, ví dụ số lần gọi và thời gian thực thi tích lũy. Nó bổ sung góc nhìn lịch sử workload, trong khi pg_stat_activity tập trung vào sessions đang tồn tại và trạng thái hiện tại.

### 16.4. Query ID không phải định danh toàn cầu vĩnh viễn

Không dùng query_id làm ID duy nhất xuyên version, database hoặc môi trường mà không xem xét semantics. Kết hợp database, user, version và query fingerprint khi cần correlation.

## 17. pg_stat_activity và lịch sử truy vấn

pg_stat_activity không phải query log.

| Công cụ | Mục đích |
| --- | --- |
| pg_stat_activity | Sessions và query hiện tại/gần nhất |
| pg_stat_statements | Thống kê tổng hợp theo query |
| PostgreSQL logs | Lịch sử sự kiện/statement theo cấu hình logging |
| auto_explain | Ghi execution plans cho các query đáp ứng cấu hình |
| pg_stat_progress_* | Tiến độ một số operations đang chạy |

### 17.1. Bật logging có chủ đích

Các setting như log_min_duration_statement, log_line_prefix, log_lock_waits và log_temp_files giúp điều tra. Chọn threshold và retention để tránh log volume quá lớn.

### 17.2. log_line_prefix

Đưa PID, user, database, application_name và client address vào log prefix để liên kết log lines với sessions.

### 17.3. Query text có thể nhạy cảm

Query literals có thể chứa email, tokens hoặc dữ liệu nghiệp vụ. Cân nhắc parameterization, access control, log retention và masking.

### 17.4. Không dùng polling dày đặc

Query pg_stat_activity quá thường xuyên từ nhiều monitors có thể tạo overhead và noise. Chọn sampling interval phù hợp và tránh dashboard mở hàng trăm panels cùng lúc.

## 18. Permissions và visibility

Không phải mọi user đều có thể xem đầy đủ thông tin của mọi session.

### 18.1. User thông thường

Một user thường xem đầy đủ thông tin về các sessions thuộc chính mình. Với sessions của user khác, một số trường nhạy cảm như query text và query identifiers có thể bị ẩn hoặc NULL.

### 18.2. pg_read_all_stats

Role predefined pg_read_all_stats cho phép xem thống kê và activity details rộng hơn. Cấp role này đồng nghĩa cấp khả năng xem query/activity của nhiều users; đánh giá theo least privilege.

~~~sql
GRANT pg_read_all_stats TO monitoring_reader;
~~~

### 18.3. pg_monitor

pg_monitor là role tiện ích để cấp quyền monitoring rộng hơn, bao gồm các predefined monitoring roles như pg_read_all_stats và quyền xem nhiều settings/statistics. Đọc documentation đúng version và chỉ cấp cho monitoring principals cần thiết.

### 18.4. Không cấp superuser cho dashboard

Dashboard thường không cần superuser. Dùng role chuyên biệt với quyền SELECT/monitoring phù hợp.

### 18.5. Signal privileges

Việc cancel/terminate backend của user khác cần quyền signal phù hợp, thường là superuser hoặc role có pg_signal_backend; superuser-owned backends có giới hạn bảo vệ riêng. Xác minh policy/version trước khi cấp.

## 19. Hủy một query bằng pg_cancel_backend

pg_cancel_backend(pid) gửi tín hiệu cancel tới query hiện tại của backend.

~~~sql
SELECT pg_cancel_backend(12345);
~~~

Kết quả boolean cho biết tín hiệu đã được gửi thành công, không phải cam kết query đã kết thúc và transaction đã được xử lý theo cách mong muốn.

### 19.1. Khi nào dùng?

- Query chạy quá lâu và được xác nhận là không cần tiếp tục.
- Query đang gây tải bất thường.
- Cần dừng một statement bị block.
- Cần giải phóng tài nguyên mà vẫn giữ session kết nối.

### 19.2. Transaction behavior

Nếu query lỗi do cancel trong transaction, transaction có thể chuyển sang trạng thái aborted và cần ROLLBACK. Ứng dụng phải xử lý lỗi và kết thúc transaction.

### 19.3. Không cancel chỉ vì query age lớn

Một query dài có thể là báo cáo hợp lệ. Kiểm tra owner, application, business impact, wait events và execution plan trước khi cancel.

## 20. Kết thúc session bằng pg_terminate_backend

pg_terminate_backend(pid) yêu cầu server kết thúc session/process.

~~~sql
SELECT pg_terminate_backend(12345);
~~~

### 20.1. Tác động

- Session bị ngắt.
- Transaction đang mở bị rollback khi backend kết thúc.
- Client phải reconnect nếu muốn tiếp tục.
- Application có thể nhận connection error và retry.

### 20.2. Khi nào dùng?

Chỉ dùng khi có lý do rõ ràng, ví dụ session idle in transaction giữ locks lâu và owner không thể xử lý, hoặc session gây incident cần chấm dứt sau khi đánh giá.

### 20.3. Vì sao nguy hiểm?

Terminate có thể làm application request thất bại, rollback transaction lớn và kích hoạt retry storm. Nếu terminate blocker, nhiều queries đang chờ có thể cùng thức dậy và tạo tải mới.

### 20.4. Xác minh PID trước khi hành động

PID có thể kết thúc và được tái sử dụng. Chụp lại PID, user, database, application_name, client_addr, state, xact_start và query ngay trước khi signal.

### 20.5. Không terminate process hệ thống tùy tiện

Không kill autovacuum, WAL sender/receiver, checkpointer hoặc background workers chỉ vì thấy chúng trong view. Xác định loại backend và mục đích vận hành trước.

## 21. Runbook xử lý query chạy lâu

1. Lấy danh sách sessions active.
2. Xác định database, user, application_name và client.
3. Đo query age và transaction age.
4. Đọc wait_event_type/wait_event.
5. Nếu Lock, tìm blockers bằng pg_blocking_pids.
6. Nếu I/O hoặc CPU, xem metrics và execution plan phù hợp.
7. Xác nhận query có phải workload hợp lệ.
8. Liên hệ owner/application team theo incident process.
9. Thử cancel query nếu được phê duyệt và phù hợp.
10. Chỉ terminate session khi cancel không đủ hoặc session idle-in-transaction gây vấn đề.
11. Theo dõi hậu quả: transaction rollback, lock release, retry và application errors.
12. Ghi incident timeline và root cause.

## 22. Runbook xử lý lock contention

### Bước 1: Tìm blocked sessions

Lọc state active và wait_event_type Lock.

### Bước 2: Tìm blockers

Dùng pg_blocking_pids và join ngược về pg_stat_activity.

### Bước 3: Xác định blocker gốc

Xem blocker state, xact_start, application_name, query và locks. Một blocker idle in transaction thường cần được chú ý.

### Bước 4: Hiểu transaction

Xác định transaction đang giữ lock có thể commit/rollback an toàn hay không. Đừng tự gửi COMMIT thay application.

### Bước 5: Giải phóng có kiểm soát

Yêu cầu application owner kết thúc transaction hoặc cancel/terminate theo quyền và incident policy.

### Bước 6: Theo dõi queue

Sau khi blocker kết thúc, theo dõi blocked sessions, latency và retry behavior. Lock release có thể làm nhiều queries chạy đồng thời.

## 23. Runbook xử lý idle-in-transaction

1. Tìm các sessions idle in transaction.
2. Sort theo transaction age.
3. Xác định application_name, user, client và last query.
4. Tìm blockers mà session đó gây ra.
5. Xem application logs/request ID nếu có.
6. Liên hệ owner để commit/rollback đúng logic.
7. Nếu cần, cancel/terminate theo quy trình.
8. Kiểm tra autovacuum và bloat impact.
9. Đặt idle_in_transaction_session_timeout nếu phù hợp.
10. Sửa code path để mọi transaction được đóng trong success/error paths.

## 24. Giám sát connection capacity

### 24.1. Số connections theo state

~~~sql
SELECT
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY sessions DESC;
~~~

### 24.2. Tổng connections theo database

~~~sql
SELECT
    datname,
    count(*) AS sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_transaction_sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname
ORDER BY sessions DESC;
~~~

### 24.3. So sánh max_connections

~~~sql
SHOW max_connections;

SELECT count(*) AS client_backends
FROM pg_stat_activity
WHERE backend_type = 'client backend';
~~~

max_connections là giới hạn cấu hình cho concurrent connections, không phải mục tiêu phải sử dụng hết. Một số reserved slots/connections và backend types có thể ảnh hưởng phép so sánh; kiểm tra version và settings.

### 24.4. Pool sizing

Tổng số connections từ tất cả application instances, workers, schedulers và admin tools phải nằm trong budget. Một pool có max_size 20 chạy trên 30 instances có thể tạo tới 600 connections nếu tất cả pools đều mở tối đa.

### 24.5. Connection churn

Theo dõi backend_start và connection rate. Quá nhiều connect/disconnect có thể gây overhead authentication, process startup và TLS handshake.

## 25. Monitoring tiến độ operations

pg_stat_activity cho biết query/state, còn các progress views cung cấp chi tiết cho một số operations.

Ví dụ:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

Các views khác tùy version/operation có thể theo dõi CREATE INDEX, ANALYZE, COPY, CLUSTER, BASEBACKUP hoặc các tác vụ khác.

### 25.1. Vì sao kết hợp?

Một query active có thể chỉ cho thấy câu lệnh VACUUM đang chạy. pg_stat_progress_vacuum có thể cho biết phase, heap blocks scanned/vacuumed và index vacuum progress.

### 25.2. Không phải mọi query đều có progress view

Một SELECT thông thường không có progress view tổng quát. Dùng query age, wait events, EXPLAIN/metrics và logs.

### 25.3. Version differences

Tên view và cột phụ thuộc major version. Kiểm tra pg_catalog và tài liệu của server đang chạy.

## 26. Monitoring vacuum và transaction horizons

pg_stat_activity giúp phát hiện transaction/snapshot cũ có thể ảnh hưởng vacuum.

### 26.1. backend_xmin

backend_xmin thể hiện xmin mà backend đang giữ nếu có. Một snapshot cũ có thể ngăn vacuum loại bỏ tuple versions mà snapshot còn cần.

### 26.2. Transaction age

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 26.3. Replication slots

Logical/physical slots cũng có thể giữ WAL hoặc catalog history; chúng không xuất hiện như một client transaction thông thường. Kết hợp pg_replication_slots và vacuum monitoring.

### 26.4. XID wraparound

Transaction lâu đời và vacuum bị chặn kéo dài có thể góp phần làm transaction ID age tăng. Theo dõi database age/freeze metrics riêng; đừng chỉ nhìn xact_start.

## 27. Kết hợp với pg_stat_database

pg_stat_database cung cấp thống kê ở cấp database như commits, rollbacks, blocks read/hit, tuples returned/fetched/inserted/updated/deleted và conflicts.

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted
FROM pg_stat_database
ORDER BY datname;
~~~

Đây là counters tích lũy kể từ lần reset thống kê hoặc thời điểm khởi động tùy loại. Chuyển counters thành rates bằng cách lấy chênh lệch qua hai lần scrape; không coi giá trị tuyệt đối là tốc độ hiện tại.

## 28. Kết hợp với pg_stat_statements

pg_stat_statements tổng hợp thống kê execution của normalized queries khi extension được cài/cấu hình.

Ví dụ:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 500) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Tên cột có thể khác giữa versions. Kiểm tra extension version và view definition trước khi dùng trong automation.

### 28.1. Hai góc nhìn

- pg_stat_activity: query nào đang chạy ngay bây giờ, session nào chờ.
- pg_stat_statements: query patterns nào tiêu tốn tổng thời gian nhiều trong một khoảng thống kê.

### 28.2. Không nhầm total time với current duration

total_exec_time là tổng thời gian tích lũy theo query entry, không phải thời gian chạy của một session hiện tại.

## 29. Kết hợp với application observability

Database PID và query text hữu ích hơn khi liên kết với:
- application_name.
- Request ID hoặc trace ID.
- Job ID.
- Service instance/hostname.
- User/tenant context theo policy.
- Application logs.
- Distributed tracing.

Không nhét thông tin nhạy cảm vào application_name hoặc query comments. Dùng identifiers có giới hạn và kiểm soát.

## 30. Dashboard giám sát đề xuất

Một dashboard vận hành có thể có các panels:

| Panel | Nguồn | Câu hỏi |
| --- | --- | --- |
| Connections by state | pg_stat_activity | Bao nhiêu active/idle/idle-in-transaction? |
| Connections by app | pg_stat_activity | Service nào mở nhiều connections? |
| Long active queries | pg_stat_activity | Query nào vượt ngưỡng? |
| Old transactions | pg_stat_activity | Transaction nào mở lâu? |
| Lock waiters/blockers | pg_stat_activity + pg_blocking_pids | Ai đang block ai? |
| Wait events | pg_stat_activity | Backend đang chờ điều gì? |
| Query workload | pg_stat_statements | Query pattern nào tiêu tốn thời gian? |
| Database rates | pg_stat_database | Commit/read/write trends ra sao? |
| Operation progress | pg_stat_progress_* | Vacuum/index/copy đang ở phase nào? |
| SSL connections | pg_stat_ssl | Connections có dùng TLS theo policy? |

### 30.1. Sampling interval

Chọn interval dựa trên incident response needs và monitoring overhead. Không cần scrape từng giây mọi cột query text trên một cluster rất lớn nếu không có lý do.

### 30.2. Alert thresholds

Thiết lập threshold theo baseline:
- Số idle-in-transaction vượt ngưỡng.
- Transaction age vượt SLA.
- Lock wait duration tăng.
- Active query age vượt workload threshold.
- Connection usage gần capacity.
- Wait events bất thường.
- Query cancellation/error rate tăng.

### 30.3. Alert context

Alert nên gồm PID, database, user, application_name, client address, state, wait event, xact age và query sample đã được bảo vệ. Không gửi toàn bộ query literals nhạy cảm tới kênh công khai.

## 31. Các giới hạn và bẫy khi đọc pg_stat_activity

### 31.1. Query text có thể bị truncate

track_activity_query_size giới hạn kích thước query text được lưu. Query dài có thể bị cắt; đừng coi phần hiển thị là toàn bộ statement.

### 31.2. Query text có thể là câu lệnh trước đó

Với session không active, query thường là statement gần nhất. Đọc cùng state và query_start.

### 31.3. Sampling là tức thời

Một query ngắn có thể bắt đầu và kết thúc giữa hai lần scrape. Nếu cần lịch sử, dùng logs/tracing/pg_stat_statements.

### 31.4. Wait event có thể thay đổi liên tục

Một backend có thể chuyển từ Lock sang IO hoặc không wait trong thời gian rất ngắn. Một snapshot không mô tả toàn bộ query lifetime.

### 31.5. Permissions che dữ liệu

Query của user khác có thể không hiện đầy đủ nếu monitoring role thiếu quyền. NULL không luôn có nghĩa query không tồn tại.

### 31.6. View columns thay đổi

Các cột mới có thể được thêm trong major versions. Automation nên kiểm tra compatibility hoặc pin schema theo version.

### 31.7. Không phải mọi backend đều là application connection

Lọc backend_type hoặc nhận diện background processes trước khi thống kê client sessions.

## 32. Cấu hình activity tracking

### 32.1. track_activities

Setting này điều khiển thu thập thông tin command/activity cho các sessions. Nếu tắt, state có thể là disabled và query details không có như mong đợi.

~~~sql
SHOW track_activities;
~~~

### 32.2. track_activity_query_size

Giới hạn kích thước query text được thu thập. Giá trị lớn hơn có thể tăng memory overhead; cân nhắc nhu cầu điều tra và kích thước câu lệnh.

~~~sql
SHOW track_activity_query_size;
~~~

### 32.3. compute_query_id

Nếu cần query_id, kiểm tra compute_query_id và version. Một số integrations/pg_stat_statements có thể yêu cầu cấu hình bổ sung.

### 32.4. Logging settings

~~~sql
SHOW log_min_duration_statement;
SHOW log_lock_waits;
SHOW log_line_prefix;
~~~

Chọn logging policy để có đủ evidence mà không tạo quá nhiều logs hoặc lộ dữ liệu nhạy cảm.

## 33. An toàn khi thao tác với sessions

Trước khi cancel hoặc terminate:
1. Xác nhận PID và session identity.
2. Xác nhận database/user/application.
3. Xác định state và wait event.
4. Kiểm tra query và transaction age.
5. Tìm blockers/dependents.
6. Đánh giá rollback và retry impact.
7. Thông báo owner theo incident policy.
8. Chọn cancel trước nếu chỉ cần dừng query.
9. Chỉ terminate khi có lý do rõ ràng.
10. Theo dõi hậu quả và ghi audit.

### 33.1. Không dùng script kill tất cả query lâu

Query age đơn thuần không đủ. Một báo cáo dài hợp lệ, VACUUM hoặc migration có thể cần chạy lâu.

### 33.2. Không terminate theo application_name một cách mù quáng

Một application có thể có cả request quan trọng, background jobs và session đang giữ transaction. Lọc PID cụ thể và xác minh.

### 33.3. Không chạy COMMIT/ROLLBACK từ session khác

PostgreSQL không cho session quản trị commit transaction của session client khác bằng một lệnh SQL thông thường. Hãy yêu cầu owner xử lý hoặc terminate theo policy.

## 34. Troubleshooting: database báo too many connections

1. Đếm client backends theo database/user/application.
2. So sánh với max_connections và reserved connection capacity.
3. Xác định pools có mở quá nhiều connections hay không.
4. Kiểm tra idle sessions và connection churn.
5. Xem connection leak hoặc retry storm.
6. Cân nhắc pooler như PgBouncer nếu kiến trúc phù hợp.
7. Điều chỉnh pool sizes và timeout.
8. Chỉ terminate sessions đã xác định rõ và được phê duyệt.

Tăng max_connections không phải giải pháp mặc định; mỗi backend tiêu thụ tài nguyên và có thể làm vấn đề memory/scheduler nặng hơn.

## 35. Troubleshooting: query chậm nhưng không thấy lock wait

Nếu state=active và wait_event_type không phải Lock:
- Kiểm tra wait event khác như IO, LWLock hoặc Client.
- Xem CPU saturation và storage latency.
- Lấy EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp; ANALYZE thực thi query nên cần cẩn trọng.
- So sánh query với pg_stat_statements.
- Kiểm tra plan changes, statistics và indexes.
- Kiểm tra network/client consumption nếu server chờ gửi dữ liệu.
- Kiểm tra parallel workers và resource contention.

Không kết luận query đang dùng CPU chỉ vì wait_event NULL.

## 36. Troubleshooting: idle-in-transaction tăng

Nguyên nhân thường gặp:
- Application quên commit/rollback.
- Transaction mở trong lúc chờ network/API.
- Pooler trả connection khi transaction chưa đóng.
- Interactive user để transaction mở.
- Exception handler không rollback.

Hướng xử lý:
- Xác định owner bằng application_name/client.
- Xem transaction age và blocker relationships.
- Sửa application transaction lifecycle.
- Cân nhắc idle_in_transaction_session_timeout.
- Theo dõi vacuum/bloat và oldest transaction horizons.

## 37. Troubleshooting: lock wait tăng đột biến

1. Xác định blocked sessions.
2. Tìm blocker bằng pg_blocking_pids.
3. Nhóm theo application/database/relation.
4. Đọc transaction age của blockers.
5. Kiểm tra DDL, bulk updates, migrations hoặc long transactions.
6. Chọn cancel/terminate có kiểm soát.
7. Kiểm tra retry storm sau khi lock được giải phóng.
8. Xem xét lock_timeout và transaction design.

## 38. Troubleshooting: dashboard hiển thị query NULL

Các khả năng:
- User giám sát không có quyền xem query của session khác.
- Backend không có query text thông thường.
- track_activities bị tắt.
- Query text không được cung cấp cho backend type đó.
- Query đã kết thúc và dữ liệu activity thay đổi giữa các lần quan sát.
- Version/view semantics khác.

Kiểm tra quyền monitoring, SHOW track_activities và backend_type. Không mặc định query NULL là lỗi database.

## 39. Bài tập thực hành PostgreSQL

Thực hiện trong lab hoặc staging. Các thao tác cancel/terminate nên dùng sessions thử nghiệm do bạn tạo.

1. **Khám phá:** truy vấn pg_stat_activity và xác định PID của session hiện tại.
2. **Nhận diện:** liệt kê datname, usename, application_name và client_addr.
3. **Client backends:** lọc backend_type = client backend.
4. **Background:** liệt kê các backend_type khác nhau.
5. **State:** đếm sessions theo state.
6. **Active:** chạy một query đủ lâu trong lab và quan sát state=active.
7. **Idle:** mở psql không chạy query và quan sát state=idle.
8. **Transaction:** BEGIN rồi chờ, quan sát idle in transaction.
9. **Aborted:** tạo lỗi trong transaction và quan sát idle in transaction (aborted).
10. **Query text:** so sánh query column của active và idle sessions.
11. **Query age:** tính query age cho active statements.
12. **Transaction age:** tính tuổi transaction từ xact_start.
13. **Session age:** tính tuổi connection từ backend_start.
14. **State age:** tính thời gian state hiện tại từ state_change.
15. **Application name:** SET application_name và lọc session theo tên.
16. **Database counts:** nhóm connections theo database.
17. **User counts:** nhóm connections theo user.
18. **Client counts:** nhóm sessions theo client_addr.
19. **Long query:** tìm query active lâu hơn một ngưỡng.
20. **Idle transaction:** tìm idle-in-transaction sessions lâu hơn 1 phút.
21. **Old transaction:** sắp xếp sessions theo xact_start.
22. **Wait event:** tạo lock wait trong hai sessions và quan sát wait_event_type.
23. **Lock blocker:** dùng pg_blocking_pids để tìm blocker.
24. **Blocking tree:** tạo nhiều blocked sessions và dựng quan hệ PID.
25. **pg_locks:** join pg_locks với pg_stat_activity.
26. **Lock mode:** quan sát các lock modes do SELECT/UPDATE/DDL tạo ra.
27. **Cancel:** gọi pg_cancel_backend trên query lab dài.
28. **Terminate:** gọi pg_terminate_backend trên session lab và quan sát client reconnect.
29. **Rollback:** xác minh transaction bị rollback khi backend bị terminate.
30. **Permissions:** thử xem activity bằng role thường và role pg_read_all_stats.
31. **Monitoring role:** cấp pg_monitor cho role lab và kiểm tra visibility.
32. **Signal role:** nghiên cứu pg_signal_backend và quyền signal process.
33. **SSL:** join pg_stat_activity với pg_stat_ssl.
34. **Query ID:** kiểm tra query_id và compute_query_id nếu version hỗ trợ.
35. **pg_stat_statements:** so sánh query hiện tại với thống kê tích lũy.
36. **Progress:** chạy VACUUM hoặc CREATE INDEX trong lab và quan sát progress view tương ứng.
37. **Connection pool:** mô phỏng nhiều application connections và đếm sessions theo application_name.
38. **Pool sizing:** tính tổng connection budget từ nhiều application instances.
39. **Churn:** tạo/release connections liên tục và quan sát backend_start.
40. **Timeout:** cấu hình statement_timeout và quan sát query bị cancel.
41. **Lock timeout:** cấu hình lock_timeout và tạo lock conflict.
42. **Idle transaction timeout:** cấu hình idle_in_transaction_session_timeout trong lab.
43. **Idle session timeout:** kiểm tra idle_session_timeout và tác động tới pool.
44. **track_activities:** kiểm tra setting và tìm hiểu state disabled.
45. **Query size:** kiểm tra track_activity_query_size và query text truncation.
46. **Log prefix:** cấu hình log_line_prefix có PID, user, database và application.
47. **Slow query logs:** thử log_min_duration_statement trên lab.
48. **Lock logs:** bật log_lock_waits và tạo lock wait.
49. **Wait sampling:** lấy nhiều snapshots để quan sát wait event thay đổi.
50. **ClientRead:** quan sát session idle chờ client.
51. **IO wait:** tạo workload I/O và tìm wait events phù hợp với version.
52. **LWLock:** đọc tài liệu về một LWLock wait event được quan sát.
53. **Parallel query:** chạy query parallel và tìm leader_pid/parallel workers.
54. **Autovacuum:** quan sát autovacuum worker trong pg_stat_activity.
55. **WAL sender:** tạo physical replication lab và nhận diện WAL sender.
56. **Logical worker:** tạo logical subscription và nhận diện apply/sync workers.
57. **backend_xmin:** tìm sessions giữ xmin lâu.
58. **Vacuum horizon:** mô phỏng transaction snapshot cũ và quan sát vacuum impact trong lab.
59. **Database stats:** join insight với pg_stat_database.
60. **Query rate:** lấy hai snapshots của counters và tính delta/rate.
61. **NULL query:** kiểm tra visibility khi thiếu pg_read_all_stats.
62. **Sensitive query:** tạo query có literal thử nghiệm và đánh giá quyền truy cập query text.
63. **Dashboard:** xây panel connections by state.
64. **Dashboard:** xây panel connections by application.
65. **Dashboard:** xây panel long-running queries.
66. **Dashboard:** xây panel idle-in-transaction age.
67. **Dashboard:** xây panel lock waiters và blockers.
68. **Alert:** tạo alert khi idle-in-transaction vượt ngưỡng.
69. **Alert:** tạo alert khi connection usage gần capacity.
70. **Alert:** tạo alert khi lock wait duration tăng.
71. **Troubleshooting:** điều tra too many connections trong lab.
72. **Troubleshooting:** điều tra một query active lâu nhưng không có Lock wait.
73. **Troubleshooting:** điều tra blocker đang idle in transaction.
74. **Troubleshooting:** điều tra query text NULL.
75. **Incident:** viết runbook cancel một query gây tải cao.
76. **Incident:** viết runbook terminate một session giữ lock.
77. **Security:** thiết kế monitoring role không dùng superuser.
78. **Observability:** liên kết PID/application_name với application request logs.
79. **History:** thiết kế logging/pg_stat_statements để bổ sung lịch sử mà pg_stat_activity không lưu.
80. **Thiết kế tổng hợp:** xây dashboard và runbook PostgreSQL theo dõi session states, long queries, lock blockers, transaction age, connection capacity, permissions, cancel/terminate safety và incident evidence.

## 40. Checklist vận hành

### Quan sát sessions

- [ ] Lọc đúng client backend và background processes.
- [ ] Xác định database, user, application_name và client.
- [ ] Đọc state cùng wait_event_type/wait_event.
- [ ] Chỉ tính query age cho active sessions.
- [ ] Phân biệt query age, transaction age và session age.
- [ ] Xác định query text có thể là statement gần nhất.

### Điều tra chậm/lock

- [ ] Tìm active queries vượt ngưỡng.
- [ ] Tìm idle-in-transaction sessions.
- [ ] Dùng pg_blocking_pids để tìm blockers.
- [ ] Đối chiếu pg_locks khi cần.
- [ ] Kết hợp metrics, progress views và logs.
- [ ] Xác định owner/application trước khi can thiệp.

### Can thiệp

- [ ] Xác minh PID và session identity.
- [ ] Ưu tiên cancel query khi chỉ cần dừng statement.
- [ ] Chỉ terminate khi đánh giá rollback/retry impact.
- [ ] Không kill background processes tùy tiện.
- [ ] Theo dõi hậu quả sau signal.

### Monitoring và bảo mật

- [ ] Application_name được đặt nhất quán.
- [ ] Monitoring role có quyền tối thiểu.
- [ ] Query text và logs được bảo vệ.
- [ ] Connection capacity được so sánh với pool budgets.
- [ ] Slot/vacuum/transaction horizons được theo dõi cùng activity.
- [ ] Sampling interval không tạo overhead quá mức.
- [ ] Dashboard/automation tương thích PostgreSQL version.

## 41. Tổng kết

pg_stat_activity là cửa sổ quan trọng để quan sát các server processes và sessions đang tồn tại trong PostgreSQL. Nó cho biết ai đang kết nối, backend thuộc loại nào, session đang active hay idle, query hiện tại/gần nhất là gì và process đang chờ sự kiện nào.

Những nguyên tắc quan trọng:

- **Một dòng đại diện cho một server process**, không nhất thiết là một người dùng cuối.
- **state và wait_event bổ sung cho nhau.** Active không có nghĩa đang dùng CPU; query có thể đang chờ lock hoặc I/O.
- **Query text của session idle thường là câu lệnh gần nhất.** Chỉ diễn giải query_start như execution duration khi state=active.
- **Transaction age khác query age và session age.** Idle-in-transaction kéo dài có thể giữ locks/snapshots và ảnh hưởng vacuum.
- **pg_blocking_pids giúp tìm blocker.** Kết hợp pg_locks và pg_stat_activity để hiểu lock contention.
- **pg_cancel_backend dừng query; pg_terminate_backend kết thúc session.** Cả hai cần xác minh PID, owner và tác động trước khi thực hiện.
- **pg_stat_activity là trạng thái hiện tại, không phải lịch sử đầy đủ.** Dùng logs, pg_stat_statements và tracing cho phân tích lịch sử.
- **Quyền monitoring ảnh hưởng visibility.** Cấp pg_read_all_stats/pg_monitor có chủ đích và bảo vệ query text.
- **Kết hợp activity với progress views, database stats và application telemetry** để xác định nguyên nhân thay vì chỉ nhìn một snapshot.

Khi được dùng cùng application_name, wait events, lock diagnostics và logging phù hợp, pg_stat_activity giúp DBA phát hiện sớm session bất thường, xác định nguồn gây nghẽn và xử lý incident có kiểm soát mà không làm gián đoạn workload ngoài dự kiến.

