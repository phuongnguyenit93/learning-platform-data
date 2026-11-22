# Phân biệt chặn do khóa, bế tắc và giao dịch chạy chậm

Khi một câu SQL mất nhiều thời gian, nguyên nhân không nhất thiết là truy vấn xử lý quá nhiều dữ liệu. Nó có thể đang chờ một transaction khác nhả khóa, có thể là nạn nhân trong một bế tắc (deadlock), hoặc thật sự đang chạy chậm do CPU, I/O, kế hoạch truy vấn hay khối lượng công việc. Một transaction cũng có thể chạy xong câu SQL cuối cùng nhưng vẫn chưa commit, tiếp tục giữ khóa và chặn các phiên khác.

Ba tình huống này cần cách chẩn đoán và xử lý khác nhau:

- **Chặn do khóa (blocking / lock wait):** một phiên cần tài nguyên đang được phiên khác giữ. Nếu phiên giữ khóa kết thúc, phiên chờ có thể tiếp tục.
- **Bế tắc (deadlock):** các transaction tạo thành một vòng chờ; mỗi transaction cần khóa do transaction khác trong vòng đang giữ. Không transaction nào có thể tự tiến lên nếu không có một transaction bị hủy hoặc được can thiệp.
- **Giao dịch hoặc truy vấn chạy chậm (slow query / long-running transaction):** công việc chưa hoàn tất trong thời gian dự kiến. Nó có thể đang tính toán, đọc dữ liệu, chờ I/O, chờ khóa hoặc nằm idle trong khi transaction vẫn mở.

Một truy vấn chậm có thể là nguyên nhân khiến phiên khác bị chặn. Một lock wait cũng làm thời gian truy vấn trông như rất dài. Vì vậy, cần xác định phiên đang chờ, phiên đang giữ khóa, trạng thái transaction và loại wait event trước khi kết luận.

Các ví dụ chẩn đoán trong bài sử dụng MySQL InnoDB và PostgreSQL. Tên trạng thái, view hệ thống và hành vi rollback có khác biệt theo hệ quản trị và phiên bản.

## 1. Ba tình huống nhìn từ phía ứng dụng

Giả sử ứng dụng cập nhật hàng `accounts` có `id = 10`.

### Chặn do khóa

Session A cập nhật hàng và chưa commit:

```sql
-- Session A
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

-- Giữ transaction mở.
```

Session B cũng muốn cập nhật cùng hàng:

```sql
-- Session B
UPDATE accounts
SET balance = balance + 50
WHERE id = 10;
```

Session B phải chờ khóa mà A đang giữ. Khi A commit hoặc rollback, B có thể tiếp tục. Đây là blocking, chưa phải deadlock vì chỉ có một quan hệ chờ một chiều.

### Bế tắc

Hai session khóa hai hàng theo thứ tự ngược nhau:

```sql
-- Session A
START TRANSACTION;
UPDATE accounts SET balance = balance - 100 WHERE id = 10;
-- Sau đó sẽ cập nhật id = 20.
```

```sql
-- Session B
START TRANSACTION;
UPDATE accounts SET balance = balance - 50 WHERE id = 20;
-- Sau đó sẽ cập nhật id = 10.
```

Khi A cần hàng 20, A chờ B. Khi B cần hàng 10, B chờ A. Hai transaction tạo thành một chu trình chờ. Database phát hiện deadlock và chọn một transaction làm nạn nhân để phá vòng.

### Truy vấn hoặc transaction chạy chậm

Một câu `SELECT` có thể chạy lâu vì quét nhiều hàng, dùng kế hoạch kém, đọc từ storage chậm hoặc xử lý lượng dữ liệu lớn. Không có phiên nào giữ khóa khiến nó phải chờ, và nó cũng không tạo chu trình deadlock.

Một trường hợp khác khó nhận ra hơn:

```sql
-- Session A
START TRANSACTION;
SELECT * FROM accounts WHERE id = 10;

-- Ứng dụng xử lý kết quả rất lâu nhưng chưa COMMIT/ROLLBACK.
```

Session A có thể ở trạng thái `Sleep` hoặc `idle in transaction`. Câu `SELECT` đã kết thúc, nhưng transaction vẫn mở và có thể tiếp tục giữ khóa hoặc snapshot tùy hệ quản trị và loại truy cập. Một session khác có thể bị chặn bởi A dù A không có câu SQL nào đang chạy.

## 2. So sánh dấu hiệu và cách xử lý

| Tiêu chí | Chặn do khóa | Deadlock | Truy vấn/transaction chạy chậm |
|---|---|---|---|
| Bản chất | Một phiên chờ khóa do phiên khác giữ | Một vòng chờ giữa nhiều transaction | Công việc chưa hoàn tất trong thời gian dự kiến |
| Có chu trình chờ không? | Không nhất thiết | Có | Không nhất thiết |
| Dấu hiệu thường gặp | Lock wait, blocking session, wait event loại Lock | Deadlock error, deadlock report/log | Query/transaction age lớn, CPU/I/O cao hoặc session idle trong transaction |
| Có tự tiếp tục không? | Có thể tiếp tục khi blocker nhả khóa | Database thường phải hủy ít nhất một transaction để phá vòng | Tiếp tục khi công việc hoàn tất hoặc tài nguyên được cải thiện |
| Hành động chính | Tìm blocker và lý do khóa chưa được nhả | Tìm chu trình và giảm khả năng tạo vòng chờ; retry nạn nhân an toàn | Tìm phần tốn thời gian, tối ưu truy vấn hoặc rút ngắn transaction |

Không thể phân loại chỉ dựa vào thời gian chạy. Một truy vấn mất 30 giây có thể là truy vấn thật sự tốn 30 giây, có thể là truy vấn chạy 2 mili giây nhưng chờ khóa gần 30 giây, hoặc có thể là transaction đã mở 30 phút nhưng hiện không chạy câu SQL nào.

## 3. Blocking: một phiên giữ khóa, phiên khác phải chờ

Database dùng khóa để bảo vệ các thay đổi đồng thời. Khi một transaction lấy khóa không tương thích với yêu cầu của transaction khác, yêu cầu sau phải chờ. Các đối tượng bị khóa có thể là hàng, khoảng khóa, bảng, metadata hoặc tài nguyên khác tùy hệ quản trị.

Một quan hệ blocking cơ bản:

```text
Session B (waiting)
    |
    | cần khóa trên accounts.id = 10
    v
Session A (blocking)
    |
    | đang giữ khóa trên accounts.id = 10
    v
COMMIT hoặc ROLLBACK
    |
    v
Session B được tiếp tục
```

Phiên chặn có thể đang chạy câu `UPDATE`, nhưng cũng có thể đã chạy xong câu lệnh và đang idle trong transaction. Do đó, truy vấn tìm blocker phải xem cả transaction đang hoạt động lẫn transaction không có SQL hiện tại.

### Những loại khóa có thể tạo blocking

- **Row/record lock:** hai transaction truy cập cùng hàng theo mode không tương thích.
- **Gap hoặc next-key lock:** một transaction bảo vệ khoảng chỉ mục; thao tác chèn hoặc range access khác có thể phải chờ.
- **Table lock:** thao tác yêu cầu khóa ở cấp bảng có thể chặn các truy cập không tương thích.
- **Metadata lock:** DDL có thể chờ transaction đang sử dụng metadata của bảng kết thúc.
- **Advisory/application lock:** ứng dụng hoặc database dùng khóa logic để phối hợp công việc.

Một truy vấn chờ metadata lock không nhất thiết xuất hiện trong view theo dõi row lock. Với MySQL, cần xem `performance_schema.metadata_locks` hoặc trạng thái `Waiting for table metadata lock`; `performance_schema.data_lock_waits` chủ yếu mô tả chờ khóa dữ liệu InnoDB.

## 4. Deadlock: chu trình trong đồ thị chờ

Database có thể biểu diễn các quan hệ chờ bằng đồ thị. Một transaction là một nút; cạnh A → B có nghĩa A đang chờ tài nguyên do B giữ.

Ví dụ:

```text
T1 ──chờ khóa──> T2
 ^               |
 |               |
 └──chờ khóa─────┘
```

Chu trình T1 → T2 → T1 là deadlock. Với ba transaction, chu trình có thể dài hơn:

```text
T1 → T2 → T3 → T1
```

Chỉ một phiên chờ một phiên khác chưa đủ để kết luận deadlock. Cần có đường đi quay lại transaction ban đầu. Một chuỗi dài T1 chờ T2, T2 chờ T3 nhưng T3 không chờ lại T1 là blocking chain, không phải deadlock.

### Vì sao thứ tự truy cập không nhất quán tạo deadlock?

Nếu một nghiệp vụ cập nhật hai tài khoản, transaction A khóa tài khoản 10 rồi 20, còn transaction B khóa 20 rồi 10, chúng có thể tạo vòng chờ. Cả hai đều thực hiện các câu SQL hợp lệ; vấn đề nằm ở thứ tự lấy khóa không thống nhất.

Một cách giảm nguy cơ là sắp xếp các khóa theo cùng một thứ tự trong mọi luồng:

```sql
-- Cả hai luồng đều cập nhật id nhỏ trước, id lớn sau.
UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE id = 20;
```

Thứ tự nhất quán làm giảm khả năng tạo chu trình, dù không thể loại bỏ mọi deadlock. Các trigger, khóa ngoại, index phụ và thao tác trên nhiều bảng cũng có thể tạo thêm thứ tự lấy khóa mà ứng dụng không nhìn thấy trực tiếp.

### Database xử lý deadlock như thế nào?

Các hệ quản trị thường phát hiện chu trình và chọn một transaction làm nạn nhân. Transaction nạn nhân bị rollback để giải phóng khóa, cho phép transaction còn lại tiếp tục. Việc chọn nạn nhân có thể dựa trên chi phí rollback hoặc quy tắc nội bộ; ứng dụng không nên dựa vào giả định rằng một transaction cụ thể luôn bị chọn.

Deadlock là kết quả của cạnh tranh đồng thời, không nhất thiết là lỗi dữ liệu hay lỗi cú pháp. Ứng dụng cần xử lý lỗi deadlock và có thể retry toàn bộ transaction nếu thao tác an toàn để chạy lại.

## 5. Truy vấn chậm và transaction dài là hai khái niệm khác nhau

**Slow query** nói về thời gian một câu SQL thực thi. **Long-running transaction** nói về thời gian transaction tồn tại từ khi bắt đầu đến khi commit hoặc rollback. Hai khoảng thời gian này có thể khác nhau đáng kể.

Ví dụ:

```text
Transaction bắt đầu
       |
       v
SELECT chạy 50 ms
       |
       v
Ứng dụng xử lý 5 phút
       |
       v
UPDATE chạy 20 ms
       |
       v
Ứng dụng chờ một dịch vụ khác 2 phút
       |
       v
COMMIT
```

Không câu SQL nào chạy lâu, nhưng transaction tồn tại hơn 7 phút. Trong suốt khoảng đó, nó có thể giữ khóa và snapshot, tùy loại thao tác và hệ quản trị.

Ngược lại, một câu `SELECT` chạy 10 phút trong transaction autocommit có thể chưa hoàn tất nên transaction và các tài nguyên gắn với câu lệnh vẫn tồn tại 10 phút. Sau khi câu lệnh kết thúc, transaction autocommit kết thúc theo.

### Các nguyên nhân phổ biến của slow query

- Thiếu index hoặc chọn index không phù hợp.
- Quét nhiều hàng, join trên tập dữ liệu lớn hoặc sort/hash lớn.
- Thống kê optimizer cũ hoặc dữ liệu phân bố lệch.
- I/O chậm, cache miss, storage quá tải hoặc network chậm.
- Chờ tài nguyên khác như CPU, memory, temporary space hoặc connection pool.
- Truy vấn trả về quá nhiều dữ liệu và ứng dụng đọc kết quả chậm.

### Các nguyên nhân phổ biến của long-running transaction

- Mở transaction trước khi gọi HTTP/RPC hoặc thực hiện công việc ngoài database.
- Chờ người dùng thao tác trong khi transaction vẫn mở.
- Quên commit/rollback ở một nhánh xử lý lỗi.
- Connection pool trả lại kết nối trong trạng thái transaction còn mở.
- Batch xử lý quá nhiều bản ghi trong một transaction.
- Cursor hoặc result set chưa được đóng, khiến transaction và snapshot tiếp tục tồn tại.

Transaction dài có thể là blocker dù không phải slow query. Nó cũng có thể ghim snapshot, làm PostgreSQL vacuum không thu hồi dead tuples hoặc làm InnoDB purge không dọn được undo history.

## 6. Phân biệt bằng thời gian và trạng thái

Khi xem một phiên, hãy phân biệt ít nhất ba mốc:

- **Query age:** câu SQL hiện tại đã chạy bao lâu.
- **Transaction age:** transaction đã mở bao lâu.
- **Lock wait age:** phiên đã chờ khóa bao lâu.

Một session có query age nhỏ nhưng transaction age lớn có thể đang idle trong transaction giữa hai câu lệnh. Một session có query age lớn và wait event là Lock có thể dành phần lớn thời gian để chờ. Một session có query age lớn nhưng không chờ khóa có thể đang thực sự xử lý dữ liệu hoặc chờ I/O.

Trong PostgreSQL, `pg_stat_activity` cung cấp `query_start`, `xact_start`, `state`, `wait_event_type` và `wait_event`. Trong MySQL, `information_schema.innodb_trx` cung cấp thời điểm bắt đầu transaction; `SHOW FULL PROCESSLIST` hiển thị trạng thái và thời gian phiên ở trạng thái hiện tại. Hãy dùng các mốc đúng ngữ nghĩa, không coi một cột `Time` hoặc `query_start` là tuổi của transaction.

## 7. Chẩn đoán blocking trong MySQL InnoDB

### Bước 1: tìm phiên đang chờ

```sql
SHOW FULL PROCESSLIST;
```

Tìm trạng thái như `Waiting for ... lock` hoặc `Waiting for table metadata lock`. Ghi lại connection id, user, host, database, trạng thái và câu SQL. `Time` trong process list biểu thị thời gian thread ở trạng thái hiện tại; với một query đang chạy, nó thường tương ứng khoảng thời gian query đã ở trạng thái đó, nhưng không phải tuổi transaction tổng thể.

### Bước 2: xem quan hệ chờ row lock

Trong MySQL 8.0, `performance_schema.data_lock_waits` liên kết lock đang chờ với lock đang chặn:

```sql
SELECT
    waiting_thread.PROCESSLIST_ID AS waiting_connection,
    waiting_thread.PROCESSLIST_USER AS waiting_user,
    waiting_thread.PROCESSLIST_TIME AS waiting_state_seconds,
    waiting_thread.PROCESSLIST_INFO AS waiting_sql,
    blocking_thread.PROCESSLIST_ID AS blocking_connection,
    blocking_thread.PROCESSLIST_USER AS blocking_user,
    blocking_thread.PROCESSLIST_TIME AS blocking_state_seconds,
    blocking_thread.PROCESSLIST_INFO AS blocking_sql,
    requested.OBJECT_SCHEMA,
    requested.OBJECT_NAME,
    requested.INDEX_NAME,
    requested.LOCK_MODE AS requested_lock_mode,
    blocking.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS requested
  ON requested.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS waiting_thread
  ON waiting_thread.THREAD_ID = waits.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS blocking_thread
  ON blocking_thread.THREAD_ID = waits.BLOCKING_THREAD_ID;
```

Kết quả giúp nối phiên chờ với phiên chặn, đồng thời cho biết bảng, index và mode khóa liên quan. Có thể cần quyền đọc Performance Schema. Tên cột và chi tiết view phụ thuộc phiên bản MySQL.

### Bước 3: tìm transaction đang mở lâu

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_wait_started,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Đối chiếu connection id với process list và `performance_schema.threads`. `trx_query` có thể rỗng nếu kết nối đang idle giữa các câu lệnh; transaction vẫn có thể giữ khóa.

### Bước 4: xem metadata lock nếu DDL bị chặn

```sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_TIME AS state_seconds,
    t.PROCESSLIST_STATE AS process_state,
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    t.PROCESSLIST_INFO AS current_sql
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS = 'PENDING'
   OR (
       ml.OBJECT_SCHEMA = DATABASE()
       AND ml.OBJECT_NAME = 'accounts'
   )
ORDER BY ml.LOCK_STATUS, t.PROCESSLIST_TIME DESC;
```

Thay schema và tên bảng theo sự cố. `PENDING` là yêu cầu đang chờ; `GRANTED` là khóa đã được cấp. Chờ metadata lock là một loại blocking riêng, không nên chỉ xem `data_lock_waits` rồi kết luận không có blocker.

## 8. Chẩn đoán deadlock trong MySQL

MySQL InnoDB thường phát hiện deadlock và rollback một transaction nạn nhân. Ứng dụng thường nhận lỗi:

- Error `1213`, SQLSTATE `40001`: deadlock found when trying to get lock.
- Error `1205`: lock wait timeout exceeded. Đây là timeout chờ khóa, không tự động có nghĩa đã xảy ra deadlock.

Để xem deadlock gần nhất:

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần `LATEST DETECTED DEADLOCK`, xem:

- Hai hoặc nhiều transaction tham gia.
- Các câu SQL đã lấy khóa và câu SQL đang chờ.
- Bảng, index, record hoặc khoảng khóa liên quan.
- Transaction được chọn làm nạn nhân và kết quả rollback.

Đây thường là báo cáo deadlock gần nhất được lưu trong trạng thái InnoDB. Nếu cần lưu nhiều sự kiện hơn, có thể cân nhắc cấu hình `innodb_print_all_deadlocks` để ghi từng deadlock vào error log; cần quản lý dung lượng log và chính sách vận hành.

Không nhầm deadlock với lock wait timeout. Deadlock có chu trình chờ và được deadlock detector phát hiện. Lock wait timeout có thể chỉ là một phiên chờ quá lâu vì blocker chưa kết thúc. Timeout có thể xảy ra mà không có chu trình nào.

## 9. Chẩn đoán blocking và transaction dài trong PostgreSQL

### Tìm phiên chờ và blocker

PostgreSQL cung cấp `pg_blocking_pids()` để lấy PID của các phiên đang chặn một backend:

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.usename AS waiting_user,
    waiting.application_name AS waiting_application,
    waiting.state AS waiting_state,
    waiting.wait_event_type,
    waiting.wait_event,
    now() - waiting.query_start AS query_age,
    now() - waiting.xact_start AS transaction_age,
    left(waiting.query, 200) AS waiting_query,
    blocker.pid AS blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_application,
    blocker.state AS blocking_state,
    now() - blocker.xact_start AS blocking_transaction_age,
    left(blocker.query, 200) AS blocking_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocking_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocking_pid
ORDER BY waiting.query_start;
```

`wait_event_type = 'Lock'` là dấu hiệu backend đang chờ một loại lock. `pg_blocking_pids()` cho biết PID chặn trực tiếp; nếu có nhiều lớp chờ, hãy tiếp tục truy vết blocker của blocker để tìm gốc chuỗi.

### Tìm transaction idle lâu

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    query_start,
    state_change,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Chú ý `idle in transaction` và `idle in transaction (aborted)`. Một backend idle trong transaction không có query đang thực thi nhưng transaction chưa kết thúc. Nó có thể giữ row/table lock và snapshot. `backend_xmin` cũ cũng có thể khiến vacuum phải giữ lại các phiên bản hàng.

### Xem lock đang tồn tại

```sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    a.state,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 160) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
ORDER BY l.granted, l.pid;
```

`pg_locks` hiển thị các lock request và trạng thái đã được cấp (`granted`) hay chưa. Không phải mọi lock đều gắn với một relation; advisory lock hoặc transaction ID lock có thể có `relation` rỗng. Dùng `pg_blocking_pids()` để xác định quan hệ chặn thay vì chỉ suy luận từ hai dòng trong `pg_locks`.

## 10. Nhận biết deadlock trong PostgreSQL

PostgreSQL phát hiện deadlock sau khoảng thời gian `deadlock_timeout` và hủy một transaction để phá chu trình. Ứng dụng thường nhận SQLSTATE `40P01` (`deadlock_detected`).

Các nguồn điều tra gồm:

- PostgreSQL server log: deadlock report thường ghi các process tham gia, lock type, tài nguyên và câu lệnh liên quan.
- `pg_stat_database.deadlocks`: bộ đếm deadlock tích lũy theo database kể từ lần reset statistics gần nhất.
- `pg_locks` và `pg_stat_activity`: trạng thái lock và transaction tại thời điểm sự cố còn đang diễn ra.

Ví dụ xem bộ đếm:

```sql
SELECT datname, deadlocks
FROM pg_stat_database
ORDER BY deadlocks DESC;
```

Bộ đếm cho biết số lần xảy ra trong khoảng thống kê, không cung cấp đầy đủ chu trình hay câu SQL. Muốn biết nguyên nhân, cần giữ server log có deadlock detail và đối chiếu với log ứng dụng.

## 11. Quy trình phân loại một truy vấn đang chậm

Khi nhận được báo cáo “truy vấn bị treo”, hãy làm theo trình tự:

1. **Xác định phiên:** lấy connection id hoặc PID, database, user, application name và câu SQL hiện tại.
2. **Kiểm tra wait event:** phiên đang chờ lock, I/O, client, network hay đang chạy mà không có wait event rõ ràng?
3. **Tìm blocker:** dùng `data_lock_waits`/metadata locks ở MySQL hoặc `pg_blocking_pids()` ở PostgreSQL.
4. **Truy vết chuỗi chặn:** blocker có đang chờ một phiên khác không? Nếu đường chờ quay lại nút đầu, đó là deadlock; nếu không, đó là blocking chain.
5. **Đo tuổi transaction:** so sánh query age với transaction age. Tìm phiên idle trong transaction.
6. **Xem tài nguyên:** nếu không bị khóa, kiểm tra execution plan, rows examined, CPU, I/O, memory, temp spill và lượng dữ liệu trả về.
7. **Xác định phạm vi tác động:** bảng, tenant, nghiệp vụ hoặc nhóm kết nối nào bị ảnh hưởng? Có bao nhiêu phiên đang chờ theo sau?
8. **Chọn hành động:** để blocker commit/rollback, hủy truy vấn chờ, xử lý deadlock bằng retry hoặc tối ưu truy vấn thật sự chậm.
9. **Xác nhận phục hồi:** các phiên chờ đã tiếp tục, transaction đã kết thúc, số lượng kết nối giảm và lỗi không tiếp tục lặp lại.

Sơ đồ quyết định:

```text
Truy vấn hoặc thao tác đang chậm
              |
              v
      Có đang chờ lock không?
          /         \
        Có           Không
        |              |
        v              v
   Tìm blocker     Kiểm tra CPU/I/O/plan
        |              |
        v              v
 Có chu trình chờ?  Query/transaction dài?
    /       \          /        \
  Có         Không    Có         Không
  |            |       |            |
  v            v       v            v
Deadlock    Blocking  Tối ưu      Kiểm tra wait
victim      chain      hoặc đóng   event khác,
retry       xử lý      transaction connection,
an toàn     blocker    đúng lúc     network
```

## 12. Xử lý sự cố mà không làm tăng thiệt hại

### Khi chỉ có blocking

Xác định transaction giữ khóa lâu nhất và chủ sở hữu ứng dụng. Nếu transaction đang thực hiện nghiệp vụ hợp lệ, có thể chờ nó kết thúc hoặc phối hợp với chủ dịch vụ để commit/rollback. Nếu phiên chặn bị bỏ quên, đánh giá tác động của việc hủy kết nối và rollback trước khi can thiệp.

Hủy phiên chờ có thể giải phóng một kết nối ứng dụng nhưng không làm blocker nhả khóa. Muốn loại bỏ nguyên nhân, cần xử lý transaction giữ khóa hoặc câu lệnh đã lấy khóa.

### Khi deadlock xảy ra

Database thường đã rollback transaction nạn nhân. Ứng dụng nên:

- Bắt đúng loại lỗi/SQLSTATE.
- Rollback và chạy lại **toàn bộ transaction**, không chỉ câu SQL cuối cùng.
- Giới hạn số lần retry và dùng backoff ngắn có jitter khi phù hợp.
- Bảo đảm transaction có thể chạy lại an toàn, không lặp email, thanh toán hoặc tác dụng phụ ngoài database.
- Ghi log transaction id nghiệp vụ, câu lệnh và số lần retry để nhận diện deadlock lặp lại.

Nếu deadlock xảy ra thường xuyên, sửa nguyên nhân bằng cách thống nhất thứ tự truy cập tài nguyên, giảm thời gian giữ khóa, thêm index để giảm số record phải khóa và chia nhỏ transaction.

### Khi truy vấn thật sự chạy chậm

Nếu không có blocker và không có wait event khóa, hãy phân tích execution plan, số hàng đọc, join, sort, index, I/O và lượng dữ liệu trả về. Tối ưu câu SQL hoặc schema theo bằng chứng đo được. Không `KILL` một query chỉ vì thời gian chạy lớn nếu chưa hiểu nó đang làm gì và có phải batch nghiệp vụ quan trọng hay không.

### Hủy query hay kết thúc connection?

Hai hành động có tác động khác nhau:

- Hủy câu lệnh hiện tại thường để connection tồn tại. Transaction có thể vẫn mở và cần rollback hoặc commit theo trạng thái sau lỗi.
- Kết thúc connection sẽ đóng phiên và thường khiến transaction chưa commit phải rollback. Rollback có thể mất thời gian, đặc biệt với transaction ghi nhiều dữ liệu.

Trong MySQL, `KILL QUERY <connection_id>` hủy câu lệnh hiện tại; `KILL CONNECTION <connection_id>` kết thúc connection. Trong PostgreSQL, `pg_cancel_backend(pid)` yêu cầu hủy query hiện tại; `pg_terminate_backend(pid)` kết thúc backend. Các thao tác này cần quyền phù hợp và phải xác nhận đúng PID/connection trước khi dùng.

Không nhầm hủy câu SQL chờ với giải phóng khóa của blocker. Cũng không kết thúc một phiên chỉ vì nó ở trạng thái `Sleep` hoặc `idle in transaction`; trước hết cần xác định transaction nào đang mở và tác động rollback.

## 13. Timeout không đồng nghĩa deadlock

Timeout là giới hạn thời gian chờ hoặc chạy. Khi hết thời gian, database hủy câu lệnh hoặc trả lỗi theo cấu hình. Deadlock là chu trình chờ được phát hiện bằng đồ thị khóa. Một phiên có thể timeout dù không có deadlock.

| Database | Trường hợp | Dấu hiệu thường gặp |
|---|---|---|
| MySQL InnoDB | Deadlock | Error 1213, SQLSTATE `40001` |
| MySQL InnoDB | InnoDB lock wait timeout | Error 1205; `innodb_lock_wait_timeout` điều khiển thời gian chờ row lock |
| MySQL | Metadata lock wait timeout | `lock_wait_timeout` liên quan thời gian chờ metadata lock |
| PostgreSQL | Deadlock | SQLSTATE `40P01` |
| PostgreSQL | `NOWAIT` không lấy được lock | SQLSTATE `55P03` (`lock_not_available`) |
| PostgreSQL | Statement timeout | SQLSTATE `57014` (`query_canceled`) |

Với MySQL, `innodb_lock_wait_timeout` điều khiển chờ khóa InnoDB; nó không phải timeout cho metadata lock. Mặc định, InnoDB lock wait timeout thường rollback statement hiện tại; nếu `innodb_rollback_on_timeout` được bật, toàn transaction có thể bị rollback. Hãy kiểm tra cấu hình và xử lý transaction tương ứng thay vì giả định trạng thái sau lỗi.

PostgreSQL `statement_timeout` giới hạn thời gian câu lệnh. Nếu query bị hủy trong transaction tường minh, transaction thường ở trạng thái failed cho đến khi rollback hoặc rollback về savepoint phù hợp. Ứng dụng cần đóng transaction đúng cách.

## 14. Phòng ngừa blocking và deadlock

### Giữ transaction ngắn

- Mở transaction ngay trước nhóm thao tác cần tính nguyên tử.
- Commit hoặc rollback ngay sau khi hoàn tất.
- Không chờ HTTP/RPC, email, người dùng hoặc file trong khi đang giữ row lock.
- Đóng cursor/result set và trả connection về pool ở trạng thái sạch.
- Đặt timeout hợp lý cho query, transaction và trạng thái idle trong transaction.

### Dùng thứ tự lấy khóa thống nhất

Nếu một nghiệp vụ cập nhật nhiều hàng hoặc bảng, xác định thứ tự cố định và tuân thủ trong mọi code path. Ví dụ, luôn khóa tài khoản theo id tăng dần hoặc luôn truy cập bảng cha trước bảng con nếu mô hình nghiệp vụ cho phép.

### Thiết kế index để giảm số hàng phải quét

Một câu `UPDATE` thiếu index có thể quét và khóa nhiều record hơn cần thiết. Index phù hợp giúp engine tìm nhanh các hàng mục tiêu, giảm thời gian giữ khóa và xác suất xung đột. Sau khi thêm index, xác nhận execution plan thực tế.

### Chia nhỏ batch

Thay vì cập nhật hàng triệu bản ghi trong một transaction, cân nhắc chia thành các lô có ranh giới commit rõ ràng. Điều này giảm thời gian giữ khóa và chi phí rollback. Cần bảo đảm nghiệp vụ chấp nhận cập nhật từng phần và có cách tiếp tục an toàn khi batch bị gián đoạn.

### Retry có kiểm soát

Deadlock có thể vẫn xảy ra trong hệ thống có cạnh tranh cao. Retry là một phần của thiết kế ứng dụng, nhưng phải retry toàn bộ transaction, có giới hạn và idempotent. Không retry vô hạn hoặc retry một câu lệnh riêng lẻ khi các bước trước đã thay đổi trạng thái.

## 15. Checklist phân loại sự cố

Khi một thao tác database chậm hoặc bị treo, ghi lại:

1. Connection id/PID, user, application, host và câu SQL.
2. Query age, transaction age và lock wait age.
3. Wait event hoặc processlist state hiện tại.
4. Phiên đang chờ và phiên đang giữ khóa trực tiếp.
5. Chuỗi blocker có tạo chu trình hay không.
6. Bảng/index/record hoặc metadata object liên quan.
7. Isolation level, autocommit và trạng thái transaction.
8. Execution plan và tài nguyên tiêu thụ nếu không phải lock wait.
9. Hành động đã thực hiện, lỗi trả về và trạng thái rollback.
10. Kết quả sau xử lý: blocker đã kết thúc, phiên chờ tiếp tục và lỗi có tái diễn không.

## 16. Tự kiểm tra

**Một transaction B chờ transaction A commit. Đây có phải deadlock không?**

Chưa. Đây là blocking một chiều. Chỉ khi có chu trình chờ quay lại transaction ban đầu mới là deadlock.

**Một session `Sleep` có thể chặn session khác không?**

Có. Nếu connection đang giữ transaction chưa commit hoặc rollback, nó có thể giữ khóa dù không chạy câu SQL nào tại thời điểm quan sát.

**Vì sao query age và transaction age cần được xem riêng?**

Vì một câu SQL có thể chạy rất ngắn trong transaction mở lâu, hoặc một câu SQL có thể chạy lâu trong transaction autocommit. Hai mốc này cho biết hai loại thời gian khác nhau.

**Lock wait timeout có chứng minh deadlock không?**

Không. Timeout chỉ cho biết thời gian chờ đã vượt giới hạn. Deadlock cần một chu trình chờ và thường được database phát hiện riêng.

**Khi nhận deadlock error, nên retry câu SQL cuối cùng hay toàn bộ transaction?**

Thông thường phải rollback và chạy lại toàn bộ transaction để các lần đọc và ghi được thực hiện trên một trạng thái nhất quán mới. Retry chỉ an toàn khi tác dụng phụ được kiểm soát.

**Nếu truy vấn chậm nhưng không có lock wait thì nên làm gì?**

Kiểm tra execution plan, số hàng đọc, CPU, I/O, memory, sort/join và lượng dữ liệu trả về. Khi đó, tối ưu truy vấn hoặc tài nguyên có thể phù hợp hơn việc can thiệp vào transaction khác.

Khi điều tra đồng thời, hãy xác định rõ **ai đang chờ, ai đang giữ khóa, có chu trình chờ hay không và transaction đã tồn tại bao lâu**. Những dữ kiện này phân biệt được blocking có thể giải phóng, deadlock cần phá vòng và công việc thực sự chạy chậm cần tối ưu.
