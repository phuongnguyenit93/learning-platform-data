# Phân tích wait event, lock wait và thời gian thực thi câu lệnh

Khi một câu SQL chạy lâu, chỉ nhìn thời gian tổng thể thường chưa đủ để biết nguyên nhân. Câu lệnh có thể đang dùng CPU để xử lý nhiều hàng, chờ đọc dữ liệu từ đĩa, chờ một transaction khác nhả khóa, chờ ghi log commit, hoặc đã hoàn tất trên database nhưng ứng dụng vẫn đang nhận và xử lý kết quả.

Để chẩn đoán đúng, cần kết hợp ba góc nhìn:

- **Wait event:** session hoặc request đang chờ điều gì tại thời điểm quan sát.
- **Lock wait:** một loại chờ cụ thể xảy ra khi yêu cầu khóa bị xung đột với khóa đang được giữ hoặc được cấp trước đó.
- **Execution time:** thời gian câu lệnh hoặc request đã tiêu tốn, cần tách phần chạy trên CPU, phần chờ bên trong database và phần thời gian ở ngoài database.

Các khái niệm này giúp trả lời ba câu hỏi khác nhau: hệ thống đang làm gì, vì sao chưa thể tiếp tục, và tổng thời gian bị tiêu tốn ở đâu. Tên wait event và công cụ quan sát khác nhau giữa PostgreSQL, Oracle, MySQL và SQL Server, nhưng quy trình phân tích có thể áp dụng chung.

## 1. Thời gian câu lệnh không đồng nghĩa với thời gian dùng CPU

Giả sử một request gọi câu `UPDATE` và mất 8 giây mới trả kết quả. Không thể kết luận database đã dùng CPU liên tục 8 giây.

Thời gian thực tế có thể gồm:

```text
Tổng thời gian ứng dụng quan sát
│
├── Chờ lấy connection từ pool
├── Gửi request qua mạng
├── Parse / lập kế hoạch / thực thi SQL
│   ├── Thời gian CPU
│   ├── Chờ khóa
│   ├── Chờ I/O
│   ├── Chờ log / commit
│   └── Chờ tài nguyên hoặc đồng bộ nội bộ
├── Truyền các hàng kết quả về client
└── Mapping, xử lý và serialize ở ứng dụng
```

Các phần này có thể chồng lấp hoặc được đo ở những tầng khác nhau, nên không phải lúc nào cũng cộng đơn giản được. Tuy nhiên, cách tách này ngăn việc nhầm một truy vấn chờ khóa là truy vấn CPU nặng.

### Các loại thời gian cần phân biệt

| Chỉ số | Ý nghĩa | Câu hỏi được trả lời |
|---|---|---|
| Wall-clock / elapsed time | Thời gian trôi qua từ lúc bắt đầu đến lúc kết thúc | Người dùng phải chờ bao lâu? |
| CPU time | Thời gian CPU được dùng để thực thi công việc | Database thực sự tính toán bao lâu? |
| Wait time | Thời gian session chờ một sự kiện hoặc tài nguyên | Công việc bị giữ lại vì điều gì? |
| Database execution time | Thời gian đo ở tầng database theo định nghĩa của hệ thống | Phần xử lý ở database kéo dài bao lâu? |
| Application response time | Thời gian từ góc nhìn ứng dụng/client | Toàn bộ request mất bao lâu? |

Ví dụ, một câu SQL có elapsed time 8 giây, CPU time 0,2 giây và lock wait 7,5 giây. Trường hợp này cần tìm transaction giữ khóa; tối ưu thuật toán SQL có thể không giải quyết được nguyên nhân chính.

## 2. Wait event là gì?

Một session đang hoạt động có thể luân phiên giữa việc chạy trên CPU và chờ một điều kiện để tiếp tục. Khi không thể tiến triển vì đang chờ, DBMS có thể ghi nhận một **wait event** hoặc một loại wait tương đương.

Ví dụ về những nguyên nhân chờ thường gặp:

- **Lock:** chờ khóa hàng, khóa bảng hoặc tài nguyên bị transaction khác giữ.
- **I/O:** chờ đọc block hoặc ghi dữ liệu.
- **Log/commit:** chờ log được ghi bền vững hoặc hoàn tất thao tác commit.
- **Memory/buffer:** chờ buffer, latch hoặc tài nguyên bộ nhớ dùng chung.
- **Network/client:** chờ client nhận dữ liệu hoặc gửi yêu cầu tiếp theo.
- **Parallel execution:** chờ worker song song hoặc đồng bộ giữa các tiến trình.
- **Internal synchronization:** chờ một cấu trúc nội bộ được bảo vệ bởi latch, mutex hoặc cơ chế đồng bộ khác.

Tên gọi và cách phân loại cụ thể tùy DBMS. Một wait event có tên nghe nghiêm trọng chưa chắc là vấn đề; cần xem thời lượng, tần suất, session nào bị ảnh hưởng và mức độ liên quan đến request chậm.

### Active session và idle session

Trong nhiều hệ thống, session được xem là active nếu đang thực thi công việc hoặc đang chờ một tài nguyên cần cho công việc đó. Một session idle có thể đang chờ client gửi câu lệnh tiếp theo. Chờ idle thường không có nghĩa database đang gặp nghẽn.

Ví dụ:

- Session `active` chờ `Lock`: có một yêu cầu SQL đang bị chặn.
- Session `active` chờ `IO`: câu lệnh đang cần dữ liệu từ storage.
- Session `idle` chờ client: ứng dụng giữ connection nhưng chưa gửi SQL mới.
- Session `idle in transaction`: ứng dụng đã mở transaction nhưng hiện không gửi câu lệnh; transaction có thể vẫn giữ khóa và gây ảnh hưởng cho session khác.

Đặc biệt, một session không chạy SQL trong thời điểm chụp ảnh vẫn có thể là blocker vì transaction của nó chưa commit hoặc rollback.

## 3. Lock wait là một loại wait có nguyên nhân từ xung đột khóa

Khi transaction yêu cầu một chế độ khóa không tương thích với khóa đang được giữ, DBMS phải trì hoãn yêu cầu cho đến khi xung đột được giải quyết.

Ví dụ:

```text
T1: BEGIN
T1: UPDATE accounts SET balance = balance - 100 WHERE id = 7
    → giữ khóa ghi trên hàng account 7

T2: BEGIN
T2: UPDATE accounts SET balance = balance + 50 WHERE id = 7
    → cần khóa xung đột trên cùng hàng, phải chờ T1

T1: COMMIT
T2: được tiếp tục
```

Session T2 có thể xuất hiện với trạng thái đang chờ khóa. Session T1 là blocker trực tiếp. Nếu T1 lại đang chờ một session khác, cần lần theo chuỗi chờ để tìm **root blocker** (session gốc đang giữ tài nguyên khiến cả chuỗi bị dừng).

### Blocking không đồng nghĩa deadlock

Blocking xảy ra khi một session phải chờ session khác. Nếu blocker tiếp tục và commit, hàng đợi có thể được giải phóng.

Deadlock xảy ra khi các session chờ lẫn nhau tạo thành một chu trình. Ví dụ:

```text
T1 giữ khóa A, chờ khóa B
T2 giữ khóa B, chờ khóa A

Wait-for graph:
T1 ─────▶ T2
▲         │
└─────────┘
```

Deadlock detector có thể chọn một transaction làm nạn nhân và rollback. Với blocking thông thường, DBMS không nhất thiết tự hủy blocker; session chờ có thể tiếp tục chờ cho đến khi khóa được nhả hoặc timeout xảy ra.

### Lock wait không nhất thiết là lỗi của câu SQL đang chờ

Một câu `UPDATE` có thể rất đơn giản và có execution plan tốt, nhưng vẫn mất nhiều giây vì transaction khác giữ khóa quá lâu. Câu lệnh bị chờ là nạn nhân của xung đột; nguyên nhân gốc có thể là transaction giữ khóa, logic ứng dụng hoặc thứ tự lấy khóa.

## 4. Đọc thông tin blocker và blocked session

Khi thấy lock wait, hãy ghi nhận ít nhất:

- Session/request đang chờ.
- Session đang giữ khóa hoặc chặn yêu cầu.
- Tài nguyên bị tranh chấp: hàng, bảng, key, page, metadata hoặc loại tài nguyên khác.
- Chế độ khóa đang giữ và chế độ khóa đang yêu cầu.
- Thời điểm bắt đầu chờ và thời gian đã chờ.
- SQL hiện tại của cả blocked session và blocker.
- Transaction bắt đầu từ khi nào, đã thay đổi dữ liệu nào và có commit/rollback hay chưa.

### Chuỗi blocker

Ví dụ:

```text
T3 chờ T2
T2 chờ T1
T1 không chờ ai, nhưng đang giữ khóa A

Root blocker = T1
```

Nếu chỉ xử lý T3, T3 có thể tiếp tục chờ vì nguyên nhân gốc vẫn còn. Hãy đi ngược chuỗi cho đến session không bị chặn hoặc đang giữ tài nguyên gốc.

### Hàng đợi khóa và nhiều waiter

Một blocker có thể chặn nhiều session. Một session cũng có thể yêu cầu nhiều loại tài nguyên. Vì vậy, số lượng waiter và số session bị ảnh hưởng có thể quan trọng hơn thời gian chờ của một câu SQL riêng lẻ.

Không nên chỉ nhìn một dòng lock wait rồi kết luận toàn bộ database bị nghẽn. Cần xác định phạm vi ảnh hưởng: một hàng, một bảng, một nhóm transaction, hay nhiều truy vấn trong toàn hệ thống.

## 5. Quy trình phân tích một câu lệnh chạy lâu

Một quy trình thực tế có thể đi theo thứ tự sau:

1. **Xác định phạm vi:** request nào chậm, bắt đầu lúc nào, kéo dài bao lâu, chỉ một lần hay lặp lại.
2. **Lấy dấu vết câu lệnh:** SQL text hoặc query ID/hash, session ID, transaction ID, ứng dụng/endpoint và thời điểm bắt đầu.
3. **Xem trạng thái hiện tại:** session đang chạy CPU hay chờ; nếu chờ thì wait type/event nào.
4. **Nếu là lock wait:** tìm blocker, lần theo chuỗi chờ và xem transaction blocker đã mở bao lâu.
5. **Nếu không phải lock wait:** xem wait category như I/O, log, memory hoặc parallelism; xác định tài nguyên nào bị giới hạn.
6. **Xem execution plan:** số hàng ước lượng và thực tế, index, join, sort, scan và thay đổi plan.
7. **Đối chiếu lịch sử:** so sánh với lần chạy bình thường, tần suất, p95/p99 và thời điểm bắt đầu chậm.
8. **Đưa ra giả thuyết và xác minh:** thay đổi một yếu tố có kiểm soát, đo lại và kiểm tra tác động lên workload khác.

Điều quan trọng là lấy dữ liệu trong lúc sự cố đang diễn ra. Nếu chỉ xem log sau khi blocker đã commit, quan hệ chờ có thể đã biến mất.

## 6. Phân tích theo loại wait

### Lock wait

Tập trung vào blocker, transaction age, lock mode, tài nguyên và thứ tự thao tác. Câu hỏi hữu ích:

- Blocker có đang mở transaction mà không chạy SQL không?
- Blocker có gọi API hoặc chờ người dùng trong khi giữ khóa không?
- Có transaction batch cập nhật quá nhiều hàng không?
- Các luồng có lấy nhiều khóa theo thứ tự khác nhau không?
- Có index phù hợp để giảm phạm vi hàng bị khóa hoặc thời gian giữ khóa không?

### I/O wait

Một session chờ I/O có thể đang đọc nhiều block, truy cập storage chậm hoặc chờ ghi. Hãy kiểm tra:

- Số lần đọc logic và vật lý.
- Số hàng cần xử lý và lượng dữ liệu trả về.
- Execution plan có full scan không phù hợp, join lớn hoặc sort spill không.
- Latency và queue depth của storage.
- Nhiều truy vấn cùng tranh chấp I/O hay chỉ một truy vấn.

Không phải mọi full table scan đều xấu; với bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu, scan có thể là lựa chọn tốt hơn index lookup.

### CPU-bound

Nếu session dùng CPU nhiều và ít wait, cần xem execution plan và khối lượng công việc:

- Số hàng thực tế lớn hơn nhiều so với ước lượng.
- Join order hoặc join method không phù hợp.
- Hàm hoặc biểu thức tính toán đắt trên nhiều hàng.
- Sort/hash aggregation xử lý tập dữ liệu lớn.
- Plan regression sau thay đổi thống kê, bind value hoặc phiên bản.

CPU time cao là dấu hiệu truy vấn đang tính toán nhiều, nhưng chưa tự xác định được toán tử gây tốn CPU. Cần đọc plan và số liệu actual.

### Log/commit wait

Nếu thời gian commit tăng, có thể session đang chờ log được flush hoặc cơ chế đồng bộ ghi bền vững. Cần kiểm tra tốc độ commit, nhóm transaction, storage log và cấu hình durability. Không nên tùy tiện giảm mức bảo đảm durability chỉ để giảm wait.

### Network/client wait

Database có thể đã tạo kết quả nhưng client đọc chậm hoặc giữ cursor lâu. Hãy xem số hàng trả về, kích thước payload, fetch size, tốc độ mạng và thời gian ứng dụng mapping dữ liệu. Tối ưu SQL không giải quyết được nếu phần chậm nằm ở client tiêu thụ kết quả.

## 7. Thời gian thực thi: một lần chạy hay số liệu tổng hợp?

Một câu lệnh có thể có nhiều lần thực thi. Khi xem thống kê tổng hợp, phải biết chỉ số là tổng, trung bình hay percentile.

Ví dụ:

| Query | Executions | Tổng elapsed | Trung bình mỗi lần |
|---|---:|---:|---:|
| Q1 | 1 | 5 giây | 5 giây |
| Q2 | 10.000 | 100 giây | 10 ms |
| Q3 | 100 | 80 giây | 800 ms |

Q1 có một lần chạy rất chậm. Q2 mỗi lần rất nhanh nhưng tổng thời gian database tiêu tốn lớn do tần suất cao. Q3 có thể là ứng viên cần tối ưu vì mỗi lần tốn gần một giây và có 100 lần chạy.

Các chỉ số nên xem cùng nhau:

- Số lần thực thi (`executions` hoặc request count).
- Tổng elapsed time.
- Elapsed time trung bình mỗi lần.
- CPU time và wait time nếu có.
- Số hàng trả về hoặc cập nhật.
- Logical reads, physical reads, writes.
- p50, p95, p99 latency theo request hoặc query fingerprint.
- Tỷ lệ lỗi, timeout và retry.

Trung bình có thể che giấu tail latency. Nếu 99% request mất 20 ms nhưng 1% mất 8 giây, người dùng bị ảnh hưởng vẫn đáng kể. Hãy dùng percentile và histogram khi hệ thống hỗ trợ.

## 8. Execution plan giúp giải thích phần thực thi

Wait event cho biết session đang chờ điều gì tại thời điểm quan sát; execution plan cho biết database dự định hoặc đã thực hiện truy vấn bằng cách nào.

Khi xem plan, chú ý:

- Table/index scan và số hàng được đọc.
- Join method và thứ tự join.
- Estimated rows so với actual rows.
- Sort, hash, aggregation và spill ra temporary storage.
- Predicate có dùng index hiệu quả không.
- Bind parameter có làm plan khác nhau không.
- Plan hash/query plan có thay đổi so với lúc truy vấn chạy tốt không.

Một plan có vẻ hợp lý nhưng vẫn có thể chậm vì lock wait. Ngược lại, không có lock wait không có nghĩa plan tốt; câu lệnh có thể đang chạy CPU hoặc I/O quá nhiều.

### Cẩn thận với EXPLAIN ANALYZE

Một số công cụ như `EXPLAIN ANALYZE` thực sự thực thi câu lệnh để thu thập số liệu actual. Với `SELECT`, việc chạy có thể tạo tải đáng kể; với DML, câu lệnh có thể thay đổi dữ liệu. Chỉ chạy trên môi trường phù hợp và hiểu rõ tác động. Với DML trong PostgreSQL, có thể dùng transaction rồi rollback cho mục đích thử nghiệm trong những trường hợp phù hợp, nhưng không nên giả định rollback đảo ngược được mọi side effect bên ngoài database.

## 9. PostgreSQL: xem wait event và blocker

PostgreSQL cung cấp `pg_stat_activity` để xem trạng thái session, câu lệnh hiện tại và wait event. `pg_blocking_pids()` giúp tìm PID đang chặn một backend.

### Xem session đang active và wait event

```sql
SELECT pid,
       usename,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - query_start AS query_age,
       now() - xact_start AS transaction_age,
       left(query, 300) AS query_text
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
```

Các trường quan trọng:

- `state`: trạng thái backend như `active`, `idle` hoặc `idle in transaction`.
- `wait_event_type`: nhóm wait, ví dụ `Lock`, `IO`, `Client` hoặc `LWLock` tùy phiên bản.
- `wait_event`: tên sự kiện cụ thể.
- `query_start`: thời điểm câu lệnh hiện tại bắt đầu.
- `xact_start`: thời điểm transaction bắt đầu.
- `application_name`: giúp liên hệ session với service/worker.

`query_start` của session idle có thể vẫn là thời điểm câu lệnh gần nhất, không có nghĩa câu lệnh đó đang chạy. Cần đọc `state` cùng các trường thời gian.

### Tìm blocker của session đang chờ

```sql
SELECT blocked.pid AS blocked_pid,
       blocked.application_name AS blocked_app,
       now() - blocked.query_start AS blocked_query_age,
       blocker.pid AS blocker_pid,
       blocker.application_name AS blocker_app,
       blocker.state AS blocker_state,
       now() - blocker.xact_start AS blocker_xact_age,
       left(blocker.query, 300) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
  ON TRUE
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
```

Nếu blocker ở trạng thái `idle in transaction`, hãy tìm trong ứng dụng vì sao transaction chưa kết thúc. Nó có thể đã thực hiện UPDATE rồi chờ xử lý khác trước khi commit.

### Xem lock đang giữ và đang chờ

```sql
SELECT a.pid,
       a.state,
       l.locktype,
       l.mode,
       l.granted,
       l.relation::regclass AS relation_name,
       a.wait_event_type,
       a.wait_event
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

`pg_locks` có thể biểu diễn nhiều loại lock, không chỉ row lock. PostgreSQL thường dùng tuple-level conflict information kết hợp với transaction ID lock; vì vậy không phải mọi row lock đang giữ đều xuất hiện như một bản ghi đơn giản trong `pg_locks`. Dùng `pg_blocking_pids()` để tìm quan hệ blocker thường trực tiếp hơn.

### Thống kê câu lệnh với pg_stat_statements

Nếu extension `pg_stat_statements` đã được cài và bật, có thể xem các câu lệnh tiêu tốn thời gian:

```sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows,
       shared_blks_hit,
       shared_blks_read,
       left(query, 250) AS query_text
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Đây là số liệu tích lũy từ thời điểm thống kê được reset hoặc instance khởi động theo cấu hình. Muốn biết mức tăng trong một khoảng, nên lấy hai snapshot rồi tính delta; đừng coi tổng tích lũy là thời gian của một request cụ thể.

## 10. MySQL InnoDB: data lock wait và statement timing

MySQL 8.0 với InnoDB cung cấp thông tin lock qua Performance Schema. Các bảng thường dùng gồm `data_locks`, `data_lock_waits`, `events_statements_current` và các bảng history nếu được bật.

### Xem quan hệ đang chờ khóa

```sql
SELECT w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
       r.OBJECT_SCHEMA,
       r.OBJECT_NAME,
       r.INDEX_NAME,
       r.LOCK_TYPE AS waiting_lock_type,
       r.LOCK_MODE AS waiting_lock_mode,
       b.ENGINE_TRANSACTION_ID AS blocking_trx_id,
       b.LOCK_TYPE AS blocking_lock_type,
       b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Tên cột và quyền truy cập có thể thay đổi theo phiên bản MySQL/MariaDB; câu truy vấn trên hướng tới MySQL 8.0 Performance Schema. Dùng `SHOW ENGINE INNODB STATUS` để xem thêm thông tin transaction và deadlock gần đây khi cần.

### Xem statement đang chạy

```sql
SELECT THREAD_ID,
       EVENT_ID,
       SQL_TEXT,
       TIMER_WAIT,
       LOCK_TIME,
       ROWS_EXAMINED,
       ROWS_SENT
FROM performance_schema.events_statements_current
WHERE SQL_TEXT IS NOT NULL;
```

`TIMER_WAIT` được ghi theo đơn vị thời gian của Performance Schema (thường là picosecond trong MySQL 8.0). Khi trình bày, cần đổi đơn vị đúng cách. `LOCK_TIME` trong statement event không thay thế việc điều tra toàn bộ lock wait graph của InnoDB; hãy dùng `data_lock_waits` để xác định blocker cụ thể.

Có thể xem các statement lịch sử nếu consumer và history instrumentation đã được bật. Không phải mọi hệ thống đều thu thập mọi event; nếu bảng rỗng, kiểm tra cấu hình Performance Schema và quyền truy cập trước khi kết luận không có wait.

## 11. SQL Server: wait_type và blocking_session_id

SQL Server cung cấp Dynamic Management Views (DMV) để xem request đang chạy, wait task, lock và plan.

### Xem request đang chạy và blocker

```sql
SELECT r.session_id,
       r.status,
       r.command,
       r.wait_type,
       r.wait_time,
       r.wait_resource,
       r.blocking_session_id,
       r.cpu_time,
       r.total_elapsed_time,
       r.logical_reads,
       r.reads,
       r.writes,
       DB_NAME(r.database_id) AS database_name,
       SUBSTRING(
           txt.text,
           (r.statement_start_offset / 2) + 1,
           ((CASE r.statement_end_offset
               WHEN -1 THEN DATALENGTH(txt.text)
               ELSE r.statement_end_offset
             END - r.statement_start_offset) / 2) + 1
       ) AS current_statement
FROM sys.dm_exec_requests AS r
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE r.session_id <> @@SPID
ORDER BY r.total_elapsed_time DESC;
```

Các trường đáng chú ý:

- `wait_type`: loại wait hiện tại của request.
- `wait_time`: thời gian request đã chờ wait hiện tại theo đơn vị DMV quy định.
- `blocking_session_id`: session đang chặn request nếu có.
- `cpu_time`: CPU time tích lũy của request.
- `total_elapsed_time`: elapsed time tích lũy của request.
- `logical_reads`, `reads`, `writes`: chỉ số I/O và truy cập dữ liệu.

Một request có `blocking_session_id` khác 0 cần được lần theo session blocker. Blocker có thể không còn request đang chạy trong `sys.dm_exec_requests` nếu session đang idle nhưng transaction vẫn mở; khi đó xem `sys.dm_exec_sessions`, `sys.dm_tran_session_transactions` và lock DMV.

### Xem lock đang chờ

```sql
SELECT request_session_id,
       resource_type,
       request_mode,
       request_status,
       resource_associated_entity_id
FROM sys.dm_tran_locks
WHERE request_status = 'WAIT';
```

Kết hợp `sys.dm_os_waiting_tasks`, `sys.dm_exec_requests` và `sys.dm_tran_locks` để tìm quan hệ chờ, session liên quan và resource. DMV cần quyền server state phù hợp; quyền cụ thể thay đổi theo phiên bản SQL Server.

### Query Store

Query Store lưu lịch sử query, plan và runtime statistics trong các khoảng thời gian. Nó hữu ích để phát hiện plan regression và so sánh thời gian chạy trước/sau một thay đổi. Query Store giúp nhìn xu hướng lịch sử; để xác định blocker tức thời, vẫn cần DMV snapshot trong lúc sự cố xảy ra.

## 12. Oracle: wait event, session và SQL statistics

Oracle ghi nhận wait event ở session và cung cấp các dynamic performance views để chẩn đoán.

### Xem session đang chờ

```sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       sql_id,
       prev_sql_id
FROM v$session
WHERE username IS NOT NULL
ORDER BY seconds_in_wait DESC;
```

Các trường hữu ích:

- `EVENT`: wait event hiện tại hoặc gần nhất theo trạng thái session.
- `WAIT_CLASS`: nhóm wait như Application, Concurrency, User I/O, System I/O, Commit hoặc Network.
- `STATE`: cho biết session đang chờ hay không; cần đọc cùng event.
- `SECONDS_IN_WAIT`: thời gian chờ được ghi nhận cho trạng thái hiện tại/last wait tùy `STATE`.
- `BLOCKING_SESSION`: session blocker nếu Oracle xác định được.
- `SQL_ID` và `PREV_SQL_ID`: SQL hiện tại và SQL trước đó.

Không nên xếp mọi session theo `SECONDS_IN_WAIT` rồi coi hàng đầu là nguyên nhân. Hãy xem `STATE`, `EVENT`, `WAIT_CLASS` và blocker cùng nhau; một session không còn chờ có thể giữ giá trị wait gần nhất.

### Xem lock

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

`LMODE` biểu diễn chế độ khóa đang giữ; `REQUEST` là chế độ đang yêu cầu. `ID1` và `ID2` định danh tài nguyên theo loại lock, cần diễn giải theo `TYPE`. Không phải mọi loại khóa đều là khóa hàng; Oracle dùng nhiều loại enqueue và lock nội bộ.

### Xem thống kê SQL

```sql
SELECT sql_id,
       child_number,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
```

Các thời gian trong `V$SQL` là số liệu tích lũy của cursor, không phải elapsed time của một lần chạy duy nhất. Có thể so sánh hai lần chụp số liệu để tính delta và chia cho số executions tăng thêm. Cần xét child cursor vì cùng `SQL_ID` có thể có nhiều child cursor/plan.

Oracle ASH/AWR có thể hỗ trợ phân tích lịch sử session active, SQL ID và wait event. Các tính năng và dữ liệu này có yêu cầu phiên bản, cấu hình và điều kiện cấp phép riêng; cần xác nhận quyền sử dụng trước khi dựa vào chúng trong môi trường production.

## 13. Vì sao phải xem cả blocker lẫn câu SQL bị chặn?

Giả sử request T2 mất 20 giây và báo lock wait. SQL của T2 chỉ cập nhật một hàng theo primary key, thường chạy trong vài mili giây. Blocker T1 đã cập nhật hàng đó rồi giữ transaction mở trong khi gọi một API bên ngoài mất 20 giây.

Nếu chỉ tối ưu SQL của T2, vấn đề không biến mất. Hướng xử lý là rút ngắn transaction của T1, tránh giữ khóa khi gọi mạng hoặc chờ người dùng, và thiết kế lại ranh giới transaction.

Khi phân tích, cần xem:

- **Blocked SQL:** câu lệnh nào đang chờ và cần khóa gì?
- **Blocking SQL:** câu lệnh nào đã lấy khóa? Nó còn đang chạy hay transaction đã idle?
- **Transaction context:** transaction bắt đầu khi nào, có nhiều câu lệnh trước đó không, đã thay đổi bao nhiêu hàng?
- **Application context:** request/worker nào mở transaction, có chờ I/O ngoài database hay không?

SQL hiện tại của blocker có thể là câu lệnh khác với câu đã lấy khóa trước đó. Vì vậy, cần xem cả SQL hiện tại, SQL trước đó, transaction age và lịch sử log/tracing nếu có.

## 14. Phân biệt lock wait, latch/mutex wait và I/O wait

Tên gọi có thể khác nhau giữa DBMS, nhưng ba nhóm này có nguyên nhân khác nhau:

| Nhóm chờ | Tài nguyên | Ví dụ hướng điều tra |
|---|---|---|
| Lock wait | Tài nguyên dữ liệu/metadata được điều phối theo transaction | Tìm blocker, lock mode, transaction age, thứ tự lấy khóa |
| Latch/mutex/internal synchronization | Cấu trúc nội bộ dùng chung trong engine | Xem contention trên buffer/cache/metadata, mức song song và workload |
| I/O wait | Storage hoặc thiết bị I/O | Xem block reads/writes, storage latency, plan và queue |

Không nên dùng từ “lock” cho mọi loại wait. Một session chờ latch nội bộ không nhất thiết bị transaction khác chặn; kill một session bất kỳ có thể không giải quyết đúng vấn đề.

## 15. Đo thời gian ở tầng ứng dụng và database

Để phân biệt database chậm với ứng dụng chậm, nên ghi nhận các mốc thời gian có correlation ID:

```text
request_received
connection_acquired
sql_sent
first_row_received
last_row_received
transaction_committed
response_sent
```

Từ các mốc này có thể tính:

- Thời gian chờ connection pool.
- Thời gian từ lúc gửi SQL đến khi nhận hàng đầu tiên.
- Thời gian đọc hết result set.
- Thời gian commit.
- Thời gian mapping/serialize và gửi response.

Ví dụ:

| Giai đoạn | Thời gian |
|---|---:|
| Chờ connection | 1.500 ms |
| Database execute đến hàng đầu tiên | 80 ms |
| Fetch 50.000 hàng | 4.000 ms |
| Mapping và serialize | 2.000 ms |
| Tổng response | 7.580 ms |

Trong ví dụ này, execution ban đầu chỉ 80 ms. Phần chậm lớn nằm ở fetch nhiều hàng, xử lý kết quả và chờ connection. Chỉ tối ưu plan có thể không cải thiện đáng kể trải nghiệm.

### Instrumentation an toàn

- Gắn request ID/trace ID vào log ứng dụng.
- Ghi database session ID hoặc connection metadata khi có thể.
- Ghi query fingerprint/SQL ID thay vì log dữ liệu nhạy cảm.
- Ghi thời gian bắt đầu, kết thúc và số hàng xử lý.
- Tránh log password, token, số thẻ hoặc bind value nhạy cảm.
- Dùng sampling hoặc giới hạn log để tránh instrumentation tự tạo tải lớn.

## 16. Snapshot tại thời điểm sự cố và thống kê theo khoảng

Một ảnh chụp DMV/view cho biết session đang ở đâu tại đúng thời điểm truy vấn. Nếu blocker đã commit trước khi bạn chụp, wait có thể biến mất.

Đối với sự cố lặp lại, nên thu thập định kỳ hoặc dùng công cụ lịch sử để xem:

- Wait event nào tăng nhiều trong khoảng thời gian chậm.
- Query fingerprint nào tăng elapsed/CPU/read.
- Lock wait tập trung vào bảng hoặc key nào.
- Session nào thường xuyên là blocker.
- Thời gian transaction tăng cùng thời điểm nào.
- p95/p99 latency có thay đổi sau deploy hoặc thay đổi dữ liệu không.

Số liệu tổng hợp thường là counter tích lũy. Hãy tính delta giữa hai snapshot có cùng phạm vi và khoảng thời gian, đồng thời lưu ý reset counter khi restart hoặc reset extension.

## 17. Ví dụ phân tích một sự cố từ đầu đến cuối

Giả sử API cập nhật trạng thái đơn hàng đôi khi mất 15 giây.

### Quan sát ban đầu

- API p95 tăng từ 100 ms lên 15 giây.
- Database session của request có wait category `Lock`.
- Một session khác đang giữ khóa trên hàng `orders` tương ứng.
- Blocker ở trạng thái idle nhưng transaction age đã 18 giây.

### Lần theo blocker

Log ứng dụng cho thấy blocker đã chạy `UPDATE orders`, sau đó gọi dịch vụ giao hàng trước khi commit. Trong khoảng gọi dịch vụ, transaction giữ khóa trên hàng đơn hàng.

### Nguyên nhân

Transaction giữ khóa lâu hơn cần thiết vì công việc mạng bên ngoài nằm bên trong transaction database.

### Thay đổi thiết kế

1. Trong transaction ngắn, cập nhật đơn hàng và ghi một outbox event.
2. Commit transaction để giải phóng khóa.
3. Worker đọc outbox và gọi dịch vụ giao hàng sau commit.
4. Worker xử lý retry/idempotency để tránh gửi cùng yêu cầu nhiều lần.

### Đo lại

- Lock wait trên hàng đơn hàng giảm.
- Transaction age ngắn hơn.
- API latency trở về gần mức bình thường.
- Thời gian xử lý giao hàng được đo riêng ở worker.

Ví dụ này cho thấy chẩn đoán phải nối wait event với transaction và luồng ứng dụng. Chỉ nhìn tên SQL hoặc chỉ số elapsed time không đủ xác định nguyên nhân.

## 18. Quyết định xử lý sau khi tìm ra nguyên nhân

| Phát hiện | Hướng xử lý thường phù hợp |
|---|---|
| Một blocker giữ khóa quá lâu | Rút ngắn transaction, kết thúc transaction sớm, bỏ chờ ngoài DB trong khi giữ khóa |
| Nhiều transaction khóa tài nguyên theo thứ tự ngược nhau | Chuẩn hóa thứ tự lấy khóa; xử lý deadlock và retry |
| Truy vấn đọc quá nhiều block | Xem lại filter, index, partition pruning và execution plan |
| CPU cao với ít wait | Xem actual rows, join, sort, biểu thức và plan regression |
| Commit/log wait cao | Điều tra log I/O, tốc độ commit, storage và batching phù hợp |
| Connection pool wait cao nhưng DB không bận | Xem leak connection, pool size, transaction duration và concurrency ứng dụng |
| Fetch/network/client wait cao | Giảm số hàng/cột, phân trang, fetch size và xử lý kết quả ở client |
| Chỉ p99 tăng | Phân tích outlier, lock chain, parameter skew và tail latency thay vì chỉ nhìn average |

Không nên tăng connection pool, timeout hoặc số worker một cách máy móc. Nếu database đã bị nghẽn lock hoặc CPU, tăng concurrency có thể làm số waiter tăng thêm và khiến hệ thống tệ hơn.

## 19. Khi nào cần hủy blocker?

Hủy session hoặc transaction có thể giải phóng khóa, nhưng cũng có thể kích hoạt rollback lớn, kéo dài thêm thời gian chờ và làm mất công việc đã thực hiện. Trước khi hủy, cần xác định:

- Session nào thực sự là root blocker?
- Transaction có phải giao dịch nghiệp vụ đang xử lý hợp lệ không?
- Rollback dự kiến có lớn không?
- Ứng dụng có thể nhận lỗi và retry an toàn không?
- Session có đang chạy migration, batch hoặc thao tác quản trị quan trọng không?
- Có phương án để transaction kết thúc tự nhiên hoặc yêu cầu owner xử lý không?

Nếu phải hủy, dùng đúng cơ chế của DBMS và theo quy trình vận hành. Ví dụ PostgreSQL có `pg_cancel_backend()` để hủy câu lệnh và `pg_terminate_backend()` để kết thúc backend; hai thao tác có tác động khác nhau. SQL Server có `KILL` session và rollback có thể mất thời gian. Oracle có lệnh quản trị session riêng. Không chạy lệnh kill chỉ vì một session có thời gian chạy dài mà chưa hiểu trạng thái transaction.

## 20. Những lỗi chẩn đoán thường gặp

| Lỗi | Vì sao sai | Cách làm tốt hơn |
|---|---|---|
| Thấy elapsed time cao và kết luận SQL dùng CPU nhiều | Elapsed bao gồm thời gian chờ | So sánh CPU, wait time và application timing |
| Thấy lock wait rồi chỉ tối ưu câu SQL bị chặn | Nguyên nhân có thể ở blocker | Tìm blocker và root blocker, xem transaction context |
| Xem session idle và cho rằng không liên quan | `idle in transaction` vẫn có thể giữ khóa | Kiểm tra transaction age và lock đang giữ |
| Coi mọi wait event là bất thường | Nhiều wait là bình thường trong workload | Xem thời lượng, tỷ lệ, tần suất và tác động |
| Coi lock wait là deadlock | Blocking một chiều không có chu trình | Dựng wait-for graph để xác định chu trình |
| Chỉ xem average query time | Average che giấu outlier | Xem p95/p99, histogram và số lần thực thi |
| Dùng số liệu counter tích lũy như số liệu một request | Counter có thể tích lũy từ lúc reset | Tính delta theo khoảng và phạm vi rõ ràng |
| Chạy EXPLAIN ANALYZE trên production mà không cân nhắc | Công cụ có thể thực thi SQL và tạo tải/thay đổi dữ liệu | Xác minh tác động, dùng môi trường phù hợp và plan capture an toàn |
| Kill session có thời gian chạy lâu nhất | Session đó có thể không phải blocker | Xác định root blocker và đánh giá rollback trước khi hủy |
| Tăng timeout hoặc connection pool ngay lập tức | Có thể che giấu hoặc làm tăng nghẽn | Tìm nguyên nhân gốc rồi điều chỉnh có đo lường |

## 21. Tự kiểm tra

**Tình huống 1:** Một câu SQL mất 10 giây, CPU time 100 ms và lock wait 9 giây. Nên điều tra điều gì trước?

**Đáp án:** Tìm blocker, tài nguyên bị khóa và transaction đang giữ khóa. Câu SQL bị chặn có thể đã có plan tốt; phần lớn thời gian là chờ khóa.

**Tình huống 2:** T1 chặn T2, nhưng T1 không chờ tài nguyên nào của T2. Đây có phải deadlock không?

**Đáp án:** Không. Đây là blocking một chiều. T2 có thể tiếp tục khi T1 commit/rollback hoặc khi timeout/hủy xảy ra. Deadlock cần chu trình chờ.

**Tình huống 3:** Một session PostgreSQL ở trạng thái `idle in transaction` nhưng đang chặn nhiều session khác. Vì sao?

**Đáp án:** Session đã mở transaction và có thể đã lấy khóa trước đó, nhưng hiện không gửi câu lệnh. Khóa vẫn được giữ cho đến khi transaction kết thúc.

**Tình huống 4:** Một query fingerprint có 20.000 executions, tổng elapsed 200 giây và average 10 ms. Có nên bỏ qua query này vì mỗi lần chạy nhanh?

**Đáp án:** Không nhất thiết. Tổng thời gian tiêu tốn lớn do tần suất cao. Cần xem CPU, I/O, số hàng, tần suất và khả năng giảm số lần gọi.

**Tình huống 5:** SQL Server báo `blocking_session_id` cho một request. Bạn nên lấy thêm thông tin nào?

**Đáp án:** Xem session blocker, transaction age, SQL hiện tại/trước đó, lock resource và chuỗi blocker. Blocker có thể idle nhưng transaction chưa commit.

**Tình huống 6:** API mất 8 giây nhưng database execute chỉ mất 100 ms. Những phần nào cần đo tiếp?

**Đáp án:** Chờ connection pool, gửi request, fetch result set, network, mapping/serialize và xử lý ứng dụng. Cần correlation ID để nối các mốc thời gian.

**Tình huống 7:** Có nên chạy `EXPLAIN ANALYZE` cho một câu `DELETE` đang chậm trên production không?

**Đáp án:** Không nên chạy một cách tùy tiện vì `EXPLAIN ANALYZE` thực thi câu lệnh. Cần hiểu tác động, dùng bản sao/môi trường phù hợp hoặc một cách thu thập plan an toàn theo DBMS.

Khi chẩn đoán câu lệnh chậm, hãy tách elapsed time thành CPU, wait và thời gian ngoài database; xác định wait event cụ thể; nếu là lock wait, tìm root blocker và transaction giữ khóa; sau đó đối chiếu execution plan, số hàng và thống kê theo khoảng. Một kết luận tốt phải chỉ ra session nào bị ảnh hưởng, tài nguyên nào đang chờ, nguyên nhân gốc nằm ở đâu và số liệu nào chứng minh thay đổi đã cải thiện thời gian thực thi.

## Tài liệu tham khảo theo DBMS

- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
- [MySQL 8.0 — Performance Schema Data Lock Tables](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-data-locks-table.html)
- [MySQL 8.0 — Performance Schema Statement Event Tables](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-statement-tables.html)
- [SQL Server — sys.dm_exec_requests](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-requests-transact-sql)
- [SQL Server — sys.dm_tran_locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-tran-locks-transact-sql)
- [Oracle Database — Managing Performance](https://docs.oracle.com/en/database/oracle/oracle-database/)
