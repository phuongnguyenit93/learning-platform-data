# Chẩn đoán tranh chấp khóa và điều chỉnh kích thước giao dịch

Một hệ thống có thể còn dư CPU và năng lực lưu trữ nhưng request vẫn chậm vì transaction phải chờ khóa do transaction khác đang giữ. Khi nhiều worker cùng cập nhật một nhóm bản ghi, thời gian giữ khóa dài, thứ tự truy cập khác nhau hoặc một transaction xử lý quá nhiều hàng có thể làm blocking và deadlock tăng lên. Tăng số connection hay worker đôi khi khiến tình trạng nặng hơn vì nhiều transaction cùng tranh giành một tập tài nguyên.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Thực hành tổng hợp** kết nối các kỹ thuật đo lường, phân tích execution plan, thiết kế truy cập dữ liệu và xử lý tranh chấp trong workload thực tế. Bài học này tập trung vào cách chẩn đoán tranh chấp khóa, tìm blocker và deadlock, xác định nguyên nhân khiến khóa bị giữ lâu, rồi điều chỉnh kích thước giao dịch và batch để cải thiện throughput mà vẫn bảo toàn tính toàn vẹn nghiệp vụ.

Sau bài học, người học có thể:

- Phân biệt blocking, deadlock, lock timeout và tranh chấp tài nguyên khác.
- Đọc blocking chain, xác định session đang chặn, session đang chờ và câu lệnh giữ khóa.
- Thu thập wait event, lock resource, transaction age, execution plan và runtime metrics.
- Giải thích tác động của isolation level, access path, index và thứ tự cập nhật.
- Nhận diện transaction quá dài, batch quá lớn, hot row và lock footprint rộng.
- Chọn kích thước batch dựa trên thời gian giữ khóa, log, rollback, memory và throughput.
- Tách xử lý dài thành transaction nhỏ có checkpoint khi nghiệp vụ cho phép.
- Ngăn deadlock bằng thứ tự truy cập nhất quán và retry có giới hạn.
- Chọn timeout, concurrency limit và admission control phù hợp.
- Kiểm chứng thay đổi bằng workload đại diện, dữ liệu đúng và các chỉ số p95/p99, lock wait, deadlock, log và throughput.

## 1. Khóa và tranh chấp khóa trong workload cơ sở dữ liệu

### 1.1. Vì sao DBMS cần khóa?

Khi nhiều transaction đọc và ghi cùng dữ liệu, DBMS cần phối hợp để bảo đảm các thao tác không phá vỡ tính nhất quán. Cơ chế cụ thể khác nhau theo engine, nhưng khóa thường bảo vệ hàng, trang, bảng, metadata hoặc tài nguyên logic trong một khoảng thời gian.

Ví dụ, hai transaction cùng giảm tồn kho của một sản phẩm. Nếu cả hai đọc cùng số lượng rồi ghi đè kết quả dựa trên giá trị cũ, cập nhật có thể bị mất. DBMS dùng khóa hoặc cơ chế concurrency control khác để tuần tự hóa phần xung đột.

Khóa không phải lúc nào cũng là vấn đề. Một transaction ngắn lấy khóa trong thời gian rất nhỏ thường không tạo ra wait đáng kể. Tranh chấp xuất hiện khi nhiều transaction cần cùng tài nguyên và thời gian giữ khóa đủ dài để tạo hàng đợi.

### 1.2. Các loại khóa thường gặp

Tên và granularity phụ thuộc DBMS, nhưng có thể gặp:

- **Row/key lock:** bảo vệ một hàng hoặc khóa index.
- **Page lock:** bảo vệ một page chứa nhiều hàng.
- **Table lock:** bảo vệ phạm vi lớn của bảng.
- **Range/predicate lock:** bảo vệ một khoảng khóa hoặc điều kiện tìm kiếm để ngăn phantom theo isolation semantics.
- **Metadata/schema lock:** bảo vệ thay đổi cấu trúc hoặc metadata.
- **Intent lock:** biểu thị transaction có ý định lấy khóa ở cấp thấp hơn.
- **Advisory/application lock:** khóa logic do ứng dụng hoặc DBMS cung cấp, không nhất thiết gắn với một hàng cụ thể.

Không được giả định mọi engine đều khóa cùng granularity. PostgreSQL thường dùng row-level tuple locks cùng MVCC cho dữ liệu, nhưng vẫn có table-level locks và các khóa nội bộ. SQL Server có key, page, object lock và có thể escalation. InnoDB dùng record, gap và next-key locks tùy isolation và access path. Oracle dùng row-level locks cùng các khóa table/metadata liên quan.

### 1.3. Blocking là gì?

Blocking xảy ra khi một transaction không thể tiếp tục vì tài nguyên nó cần đang bị transaction khác giữ.

Ví dụ:

~~~sql
-- Transaction A
BEGIN;
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42;
-- Chưa COMMIT nên khóa ghi vẫn được giữ.

-- Transaction B
BEGIN;
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 42;
-- Phải chờ Transaction A.
~~~

Transaction A là blocker; Transaction B là waiter. Nếu A commit hoặc rollback, B có thể tiếp tục. Nếu A bị treo trong khi gọi dịch vụ ngoài hoặc chờ người dùng, B có thể chờ rất lâu.

### 1.4. Blocking chain

Blocking chain hình thành khi một session đang chờ session khác, và session chặn nó lại đang chờ session thứ ba.

~~~text
Session C  -- waits for --> Session B
Session B  -- waits for --> Session A
Session A  -- holds lock --> Resource R
~~~

Session A là root blocker trong chuỗi. Chỉ xử lý waiter C không giải quyết nguyên nhân nếu A vẫn giữ khóa. Khi điều tra, cần tìm root blocker và transaction age, không chỉ session có wait time lớn nhất.

Root blocker không nhất thiết đang chạy CPU. Nó có thể ở trạng thái idle in transaction, đã chạy xong câu lệnh nhưng chưa commit, hoặc đang chờ ứng dụng gửi lệnh tiếp theo.

### 1.5. Deadlock khác blocking

Deadlock xảy ra khi các transaction tạo thành chu trình chờ nhau; không transaction nào có thể tiếp tục nếu không có một transaction bị hủy hoặc cơ chế phá deadlock can thiệp.

~~~text
Transaction A giữ khóa hàng 1, chờ hàng 2
Transaction B giữ khóa hàng 2, chờ hàng 1

A -> B -> A
~~~

DBMS thường phát hiện chu trình và chọn một transaction làm victim để rollback. Deadlock thường kết thúc nhanh hơn blocking kéo dài, nhưng retry và rollback vẫn tạo chi phí, lỗi ứng dụng và độ trễ.

### 1.6. Lock timeout và deadlock victim

- **Lock timeout:** request chờ khóa quá thời gian cấu hình và bị hủy hoặc trả lỗi.
- **Deadlock victim:** DBMS chọn một transaction trong chu trình để rollback nhằm phá deadlock.
- **Statement timeout:** câu lệnh vượt thời gian cho phép; nguyên nhân có thể là lock wait hoặc thực thi chậm.
- **Transaction timeout:** giới hạn vòng đời transaction ở framework hoặc engine nếu được hỗ trợ.

Timeout không sửa nguyên nhân tranh chấp. Tăng timeout có thể làm request chờ lâu hơn và giữ nhiều tài nguyên hơn. Giảm timeout quá mạnh có thể tạo lỗi giả trong workload bình thường.

## 2. Cách transaction tạo và giữ khóa

### 2.1. Thời điểm lấy khóa

Thời điểm lấy khóa phụ thuộc loại lệnh, isolation level, engine và access path. Một UPDATE thường tìm các hàng phù hợp rồi khóa chúng để ghi. SELECT thông thường có thể đọc bằng MVCC mà không chặn writer trong một số engine, nhưng SELECT FOR UPDATE hoặc isolation có locking semantics sẽ lấy khóa.

Một câu SELECT không phải lúc nào cũng hoàn toàn không khóa. Có thể có khóa metadata, predicate/range lock, table lock hoặc khóa phục vụ serializable semantics. Hãy đọc hành vi của DBMS và isolation level đang dùng.

### 2.2. Khóa thường được giữ đến khi transaction kết thúc

Với nhiều loại write lock, commit hoặc rollback mới giải phóng khóa. Vì vậy, thời gian giữ khóa có thể dài hơn thời gian chạy câu SQL tạo khóa.

Ví dụ, ứng dụng mở transaction, cập nhật một hàng, gọi HTTP service, ghi log đồng bộ vào hệ thống khác, chờ người dùng xác nhận rồi mới commit. Dù câu UPDATE chỉ mất 5 ms, transaction có thể giữ khóa hàng chục giây. Hãy rút ngắn phần thời gian nằm giữa lần lấy khóa đầu tiên và commit/rollback.

### 2.3. Transaction duration và lock duration

Hai khái niệm liên quan nhưng không luôn giống nhau:

- Transaction duration: từ lúc transaction bắt đầu đến commit/rollback.
- Lock duration: khoảng thời gian từng khóa được giữ.

Một transaction chỉ đọc có thể không giữ row lock lâu trong MVCC engine, nhưng vẫn giữ snapshot hoặc tài nguyên khác. Một transaction ghi có thể lấy khóa sau khi đã thực hiện một phần công việc. Vì vậy, theo dõi cả transaction age và lock wait/lock duration khi công cụ cung cấp.

### 2.4. Isolation level ảnh hưởng phạm vi và thời gian chờ

Isolation level quyết định cách transaction nhìn thấy thay đổi của transaction khác và loại anomaly được ngăn chặn.

| Isolation | Hành vi khái quát | Tác động cần xem |
|---|---|---|
| Read uncommitted | Có thể đọc dữ liệu chưa commit ở engine hỗ trợ | Có nguy cơ dirty read |
| Read committed | Chỉ đọc dữ liệu đã commit theo semantics engine | Có thể dùng nhiều snapshot hoặc khóa đọc tùy engine |
| Repeatable read | Giữ tính ổn định của lần đọc theo semantics engine | Có thể tăng khóa/range hoặc giữ snapshot lâu |
| Serializable | Ngăn lịch thực thi không thể tuần tự hóa | Có thể tăng blocking, predicate lock hoặc serialization failure |

Không được giả định tên isolation level tạo ra cùng hành vi trên mọi DBMS. PostgreSQL dùng MVCC và semantics riêng cho REPEATABLE READ/SERIALIZABLE; SQL Server có thể dùng lock-based hoặc row-versioning options; InnoDB dùng MVCC cùng record/gap/next-key locks tùy isolation; Oracle có consistent read và serializable semantics riêng.

Không hạ isolation chỉ để giảm lock wait nếu chưa phân tích anomaly nghiệp vụ có thể xuất hiện.

### 2.5. Access path quyết định lock footprint

Một UPDATE có predicate thiếu index phù hợp có thể phải scan nhiều hàng để tìm vài hàng cần sửa. Trong quá trình đó, engine có thể kiểm tra hoặc khóa phạm vi rộng hơn, giữ tài nguyên lâu hơn và làm tăng khả năng tranh chấp.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE account_id = 42
  AND order_id = 9001;
~~~

Nếu index phù hợp là (account_id, order_id) và cặp này xác định một hàng, DBMS có thể tìm đích nhanh. Nếu không có access path phù hợp, query có thể scan nhiều hàng. Tác động khóa cụ thể phụ thuộc engine và isolation, nhưng thời gian tìm kiếm kéo dài thường làm transaction giữ tài nguyên lâu hơn.

### 2.6. Lock escalation và khóa phạm vi lớn

Một số DBMS có thể chuyển nhiều khóa nhỏ thành khóa lớn hơn để giảm overhead quản lý khóa. SQL Server có cơ chế lock escalation; các engine khác có hành vi khác nhau, không nên suy rộng khái niệm này.

Khi escalation xảy ra, transaction có thể chặn nhiều thao tác vốn chỉ cần các hàng khác nhau. Xem lock escalation events, số lượng khóa, object và ngưỡng theo engine. Không tắt escalation toàn cục chỉ vì một query; có thể làm lock memory tăng mạnh.

## 3. Nhận diện nguyên nhân tranh chấp

### 3.1. Transaction quá dài

Dấu hiệu:

- Root blocker có transaction age lớn.
- Session ở trạng thái idle in transaction hoặc ngủ nhưng vẫn mở transaction.
- Một thao tác nghiệp vụ giữ transaction trong khi gọi API, gửi email hoặc chờ file.
- Batch xử lý hàng nghìn hoặc hàng triệu hàng trước khi commit.
- Lock wait tăng vào giờ chạy job hoặc import/export.

Cách xử lý thường là rút ngắn transaction, chuyển công việc ngoài DB ra ngoài transaction, hoặc chia job thành batch có checkpoint nếu nghiệp vụ cho phép.

### 3.2. Hot row hoặc hot key

Hot row là một hàng bị nhiều transaction cùng cập nhật. Ví dụ mọi request đều tăng một counter toàn cục hoặc trừ tồn kho của một sản phẩm bán chạy.

Ngay cả khi mỗi transaction chỉ cập nhật một hàng và rất ngắn, throughput của hot row vẫn bị giới hạn bởi khả năng tuần tự hóa cập nhật trên tài nguyên đó.

Biện pháp có thể gồm:

- Giảm tần suất cập nhật counter bằng batching hoặc aggregation.
- Chia counter thành nhiều shard rồi tổng hợp khi đọc nếu semantics cho phép.
- Dùng queue để điều tiết các thao tác trên một entity.
- Thiết kế reservation hoặc inventory allocation theo lô.
- Giảm critical section và tránh đọc/ghi thêm dữ liệu không cần thiết trong transaction.

Không shard số dư hoặc tồn kho nếu việc chia nhỏ làm mất invariant nghiệp vụ hoặc cho phép oversell.

### 3.3. Truy cập nhiều hàng theo thứ tự không nhất quán

Nếu transaction A khóa hàng theo thứ tự 10 rồi 20, còn transaction B khóa 20 rồi 10, deadlock có thể xảy ra.

Thứ tự nhất quán theo khóa giúp giảm chu trình:

~~~text
Quy tắc:
  lock 10 -> lock 20

Mọi transaction cùng cập nhật nhóm hàng này đều theo thứ tự tăng dần.
~~~

Quy tắc này cần áp dụng cho mọi code path cập nhật cùng nhóm entity, bao gồm trigger, cascade và stored procedure.

### 3.4. Index thiếu hoặc predicate rộng

UPDATE/DELETE với predicate không chọn lọc có thể tác động nhiều hàng. Nếu index không phù hợp, engine có thể đọc phạm vi lớn, kéo dài transaction và tăng số tài nguyên bị tranh chấp.

Kiểm tra:

- Actual execution plan.
- Estimated/actual rows.
- Index seek/scan và số page đọc.
- Predicate có function hoặc implicit conversion không.
- Index có đúng thứ tự cột không.
- Query có cập nhật nhiều hàng ngoài dự kiến không.
- Trigger/cascade có mở rộng phạm vi thay đổi không.

Index bổ sung có thể giảm thời gian tìm hàng nhưng tăng chi phí ghi, storage và maintenance. Cần đo cả read path lẫn write path.

### 3.5. Foreign key, cascade và trigger

Một lệnh UPDATE/DELETE có thể kích hoạt kiểm tra foreign key, cascade hoặc trigger. Ứng dụng có thể tưởng rằng chỉ một bảng bị tác động, trong khi DBMS truy cập thêm nhiều bảng và khóa thêm tài nguyên.

Khi truy vết, xem toàn bộ statement/transaction, trigger, cascade và index trên cột foreign key. Thiếu index ở bảng con có thể làm kiểm tra referential integrity tốn kém tùy engine.

### 3.6. Long-running read và snapshot retention

Trong MVCC engine, transaction đọc lâu có thể giữ snapshot cũ và làm phiên bản dữ liệu chưa được dọn. Điều này không giống blocking row lock trong mọi engine, nhưng vẫn tạo áp lực vận hành:

- PostgreSQL: snapshot lâu có thể giữ xmin cũ và cản vacuum loại tuple dead.
- MySQL InnoDB: read view lâu có thể giữ undo history cần cho consistent read và làm purge chậm.
- Oracle: consistent read phụ thuộc undo; transaction đọc lâu có thể gặp rủi ro snapshot too old nếu undo không còn đủ.
- SQL Server: row versioning có thể giữ version trong version store lâu hơn; lock-based isolation có thể tạo blocking tùy truy vấn.

Phân biệt lock wait với snapshot/version retention. Không kết luận một transaction đọc lâu đang giữ row lock nếu engine dùng MVCC.

### 3.7. Không phải mọi wait đều là lock contention

Wait có thể đến từ CPU scheduler, storage I/O, log flush, memory grant, latch/mutex, network/socket, parallel exchange hoặc application lock. Tên wait/event phụ thuộc DBMS. Hãy đối chiếu wait resource với session state và transaction; một query chậm không tự động đồng nghĩa với lock wait.

## 4. Quy trình chẩn đoán blocking và deadlock

### 4.1. Thu thập bằng chứng trước khi kết thúc session

Khi sự cố đang xảy ra, thu thập:

- Timestamp và thời lượng wait.
- Waiter session/request.
- Blocker session/transaction.
- Lock resource và lock mode.
- SQL đang chạy hoặc câu lệnh gần nhất của blocker.
- Transaction start time và trạng thái session.
- Isolation level.
- Query plan và actual rows nếu có.
- Số hàng bị tác động.
- Application name, request ID hoặc job ID nếu có.
- Deadlock graph hoặc deadlock event nếu xảy ra.

Nếu kill blocker ngay, bằng chứng có thể biến mất và transaction rollback có thể tạo thêm I/O, log và thời gian phục hồi. Trong production, quyết định kết thúc session cần dựa trên tác động và khả năng rollback.

### 4.2. Tìm root blocker

Một chuỗi chờ có thể có nhiều waiter nhưng chỉ một root blocker. Hãy đi ngược từ waiter đến session đang chặn nó, tiếp tục cho đến khi tìm được session không còn bị chặn bởi session khác.

Root blocker có thể đang thực thi UPDATE/DELETE dài, chờ log flush hoặc I/O trong khi giữ khóa, idle in transaction, chờ ứng dụng gửi lệnh tiếp theo, chạy transaction batch hoặc bị bỏ quên bởi ứng dụng.

Cần xác định owner ứng dụng và request liên quan trước khi xử lý.

### 4.3. Phân biệt blocking kéo dài và deadlock

Blocking kéo dài thường có một hướng chờ hoặc một chuỗi tuyến tính. Deadlock có chu trình; deadlock detector thường ghi lại victim và resource involved.

Với deadlock, lấy deadlock graph để xem các transaction tham gia, resource/key/page/table bị tranh chấp, lock mode đang giữ và đang đợi, statement tương ứng, thứ tự thao tác, isolation level và index access path.

Một log chỉ ghi deadlock victim không đủ để sửa nguyên nhân. Cần phân tích graph và đối chiếu code path.

### 4.4. Đo tỷ lệ lock wait

Có thể theo dõi:

\[
LockWaitRatio =
\frac{TimeWaitingForLocks}
{TotalElapsedTime}
\]

Công thức chỉ có ý nghĩa nếu nguồn đo định nghĩa cùng phạm vi thời gian và không cộng trùng wait song song. Nên theo dõi histogram hoặc percentile wait duration, số waiter, số blocker và thời gian transaction.

Các chỉ số bổ sung:

- Deadlocks per minute/hour.
- Lock timeout count.
- Blocked request count.
- Longest blocking duration.
- Root blocker transaction age.
- Lock escalation events nếu engine cung cấp.
- Throughput và p95/p99 trong thời gian có blocking.

### 4.5. Dùng cửa sổ quan sát có chủ đích

Blocking có thể biến mất trước khi dashboard tổng hợp. Dùng sampling hoặc event capture đủ nhanh để lưu trạng thái khi wait vượt ngưỡng. Polling quá dày vào system catalog có thể tạo thêm tải.

Ưu tiên công cụ tích hợp của DBMS, event session hoặc tracing có filter theo wait duration và query fingerprint. Giữ retention phù hợp và bảo vệ SQL/bind values nhạy cảm.

## 5. Công cụ quan sát theo DBMS

Tên view và cột phụ thuộc phiên bản. Chỉ chạy truy vấn giám sát với quyền được cấp; trên production cần xem chi phí của việc lấy plan hoặc đọc catalog.

### 5.1. PostgreSQL

Các điểm quan sát:

- pg_stat_activity: trạng thái session, query, transaction start và wait event.
- pg_blocking_pids(pid): các PID đang chặn một backend.
- pg_locks: lock type, relation, transaction ID, mode và granted.
- pg_stat_statements: query fingerprint và thống kê runtime.
- log_lock_waits và deadlock_timeout: hỗ trợ ghi log lock wait/deadlock theo cấu hình.

Ví dụ tìm session đang chờ và blocker:

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.usename AS waiting_user,
    a.application_name AS waiting_app,
    a.wait_event_type,
    a.wait_event,
    a.xact_start AS waiting_xact_start,
    a.query AS waiting_query,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock';
~~~

Sau khi xác định PID blocker, xem pg_stat_activity của PID đó để biết xact_start, state, query_start, application_name và query gần nhất. Một blocker idle in transaction có thể không có query đang thực thi nhưng vẫn giữ transaction.

PostgreSQL row locks thường được biểu diễn qua tuple/transaction state và có thể không xuất hiện như một row lock đơn giản trong pg_locks; vì vậy cần kết hợp pg_blocking_pids, pg_stat_activity và thông tin transaction.

### 5.2. SQL Server

Các điểm quan sát:

- sys.dm_exec_requests: request đang chạy, blocking_session_id, wait type và wait resource.
- sys.dm_tran_locks: lock resource và mode.
- sys.dm_exec_sessions và sys.dm_exec_connections: session và connection.
- sys.dm_tran_session_transactions: transaction liên kết session.
- Extended Events xml_deadlock_report: deadlock graph.
- Query Store: runtime và plan history.

Ví dụ tìm request đang bị block:

~~~sql
SELECT
    r.session_id,
    r.blocking_session_id,
    r.status,
    r.wait_type,
    r.wait_time,
    r.wait_resource,
    r.command,
    s.host_name,
    s.program_name,
    t.text AS sql_text
FROM sys.dm_exec_requests AS r
JOIN sys.dm_exec_sessions AS s
  ON s.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS t
WHERE r.blocking_session_id <> 0;
~~~

Truy vấn này cho thấy waiter và blocker session ID; cần truy vấn tiếp session blocker, transaction và SQL batch. Một session có thể không còn request active nhưng vẫn giữ transaction mở. DMV yêu cầu quyền phù hợp tùy phiên bản và cấu hình.

### 5.3. MySQL InnoDB

Các điểm quan sát:

- performance_schema.data_locks: lock đang tồn tại.
- performance_schema.data_lock_waits: quan hệ waiter/blocker.
- performance_schema.threads và statement history: ánh xạ thread với statement.
- SHOW ENGINE INNODB STATUS: transaction, latest detected deadlock và thông tin InnoDB.
- information_schema.innodb_trx trên các phiên bản có hỗ trợ.
- Performance Schema statement digest: query workload.

Ví dụ xem quan hệ chờ khóa trên phiên bản hỗ trợ các bảng Performance Schema này:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_TYPE,
    r.LOCK_MODE AS waiting_lock_mode,
    b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Tên cột và khả năng truy vấn thay đổi theo MySQL version. Cần kiểm tra schema thực tế và ánh xạ transaction ID sang thread/session. InnoDB deadlock report thường ghi transaction và index record liên quan; đọc cả câu lệnh và index được sử dụng.

### 5.4. Oracle Database

Các điểm quan sát:

- V$SESSION: session, status, event, wait class, blocking session và SQL ID.
- V$LOCK: lock type, ID, mode held/requested.
- DBA_BLOCKERS và DBA_WAITERS nếu được cấp quyền.
- V$TRANSACTION: transaction state và start information.
- V$SQL và DBMS_XPLAN: SQL và plan.
- Trace/deadlock information trong diagnostic log phù hợp.

Ví dụ tìm session có blocker:

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    blocking_session,
    sql_id,
    prev_sql_id,
    seconds_in_wait
FROM V$SESSION
WHERE blocking_session IS NOT NULL;
~~~

Dùng sid và serial# để xác định session, sau đó xem transaction và SQL hiện tại/trước đó. Một session đang idle có thể vẫn giữ transaction chưa commit. Cần quyền catalog phù hợp; không giả định mọi tài khoản ứng dụng có quyền đọc dynamic performance views.

### 5.5. So sánh nhanh

| Mục tiêu | PostgreSQL | SQL Server | MySQL InnoDB | Oracle |
|---|---|---|---|---|
| Waiter/blocker | pg_stat_activity, pg_blocking_pids | DMVs, blocking_session_id | data_lock_waits | V$SESSION, DBA_WAITERS |
| Lock resource | pg_locks | sys.dm_tran_locks | data_locks | V$LOCK |
| Transaction age | xact_start | transaction DMVs | innodb_trx | V$TRANSACTION |
| Deadlock detail | server log | Extended Events | InnoDB status/error log | trace/diagnostic log |
| Query history | pg_stat_statements | Query Store | Performance Schema | V$SQL/AWR nếu có quyền |

## 6. Điều chỉnh kích thước giao dịch

### 6.1. Transaction size là gì?

Kích thước giao dịch có thể được mô tả bằng:

- Số hàng đọc và ghi.
- Số statement trong transaction.
- Số khóa hoặc tài nguyên bị giữ.
- Lượng log phát sinh.
- Bộ nhớ và temporary workspace.
- Thời gian từ lần lấy khóa đầu tiên đến commit/rollback.
- Khối lượng rollback nếu transaction thất bại.

Không có một số hàng tối ưu áp dụng cho mọi workload. 500 hàng có thể nhỏ với một bảng đơn giản nhưng rất lớn nếu mỗi hàng kích hoạt nhiều trigger, cascade hoặc index maintenance.

### 6.2. Transaction quá lớn

Một transaction lớn có thể:

- Giữ khóa lâu và tạo blocking.
- Tăng deadlock exposure vì giữ nhiều resource cùng lúc.
- Tạo lượng transaction log lớn.
- Làm rollback lâu nếu lỗi xảy ra.
- Giữ snapshot/version cũ.
- Dùng nhiều memory hoặc temporary resources.
- Tăng thời gian phục hồi và khó retry.
- Tạo burst I/O khi commit hoặc flush log.

Transaction lớn vẫn cần thiết khi nghiệp vụ yêu cầu tất cả thay đổi phải atomic. Không được chia nhỏ tùy tiện nếu làm lộ trạng thái trung gian hoặc vi phạm invariant.

### 6.3. Transaction quá nhỏ

Commit quá thường xuyên cũng có chi phí:

- Nhiều log flush hoặc commit round trip.
- Tăng overhead transaction begin/commit.
- Giảm cơ hội batching và group commit.
- Có thể tăng tổng thời gian job.
- Nếu từng batch có checkpoint không đúng, có thể tạo trạng thái dở dang.

Mục tiêu là tìm kích thước đủ nhỏ để giới hạn lock duration và rollback cost, nhưng đủ lớn để giữ throughput hợp lý.

### 6.4. Phân biệt batch size và transaction size

Batch size là số hàng được xử lý trong một nhóm. Transaction size là lượng công việc được commit hoặc rollback cùng nhau. Hai giá trị có thể giống nhau nhưng không bắt buộc.

Ví dụ, ứng dụng có thể fetch 1.000 hàng mỗi batch để giảm memory, nhưng ghi mỗi 100 hàng trong một transaction riêng. Hoặc một transaction nghiệp vụ phải cập nhật ba bảng và 20 hàng như một đơn vị atomic, dù batch xử lý nhiều đơn.

Hãy xác định rõ batch boundary, commit boundary và business transaction boundary.

### 6.5. Chọn batch size theo phép đo

Một quy trình thử nghiệm:

1. Chọn một mức nhỏ làm baseline.
2. Chạy với workload và dữ liệu đại diện.
3. Ghi transaction duration p50/p95/p99.
4. Ghi lock wait, deadlock, rows/second và log bytes.
5. Tăng batch size từng bước.
6. Dừng khi throughput không tăng đáng kể nhưng lock duration, log hoặc rollback cost tăng nhanh.
7. Lặp lại dưới concurrency mục tiêu.
8. Chọn mức có headroom và đáp ứng SLO.

Ví dụ, thử 50, 100, 250, 500 và 1.000 hàng mỗi transaction. Đây chỉ là dãy thử nghiệm minh họa; giá trị thực tế phụ thuộc row width, index, trigger, storage, log và mức concurrency.

### 6.6. Định nghĩa ngưỡng theo thời gian thay vì chỉ số hàng

Một batch 100 hàng có thể mất 20 ms trên dữ liệu đơn giản và 8 giây khi trigger gọi nhiều logic. Vì vậy, có thể đặt cả giới hạn số hàng lẫn thời gian:

- Tối đa N hàng mỗi transaction.
- Mục tiêu transaction duration dưới T.
- Giới hạn log bytes hoặc payload.
- Dừng batch khi lock wait vượt ngưỡng.
- Giới hạn số batch chạy đồng thời.

Nếu vượt thời gian mục tiêu, ghi nhận batch và phân tích nguyên nhân thay vì tự động commit giữa một business transaction cần atomicity.

### 6.7. Giảm công việc nằm trong transaction

Một mẫu tốt thường tách phần chuẩn bị không cần khóa khỏi critical section:

~~~text
Ngoài transaction:
  đọc file / gọi API / tính toán thuần / xác thực định dạng

Trong transaction ngắn:
  kiểm tra điều kiện có thể thay đổi
  ghi các thay đổi liên quan
  ghi outbox/checkpoint nếu cần
  COMMIT

Sau transaction:
  phát thông báo / gửi email / cập nhật hệ thống ngoài
~~~

Nếu kết quả API bên ngoài có thể thay đổi giữa lúc chuẩn bị và commit, phải xác minh lại điều kiện quan trọng bên trong transaction. Không chuyển một kiểm tra cần tính nguyên tử ra ngoài mà không có cơ chế bảo vệ.

### 6.8. Chia batch theo khóa ổn định

Khi xử lý tập lớn, chọn một khóa duy nhất hoặc thứ tự ổn định để chia đoạn. Ví dụ dùng ID tăng dần hoặc composite key:

~~~sql
SELECT id
FROM jobs
WHERE status = 'READY'
  AND id > 100000
ORDER BY id
LIMIT 250;
~~~

Sau khi xử lý thành công, lưu checkpoint last_id hoặc trạng thái tương đương. Không dùng OFFSET lớn cho job quét toàn bộ bảng nếu nó khiến DBMS bỏ qua ngày càng nhiều hàng.

Với dữ liệu có thể được thêm trong lúc chạy, cần xác định watermark hoặc cutoff để tránh job chạy vô hạn hay bỏ sót hàng mới.

### 6.9. Claim work an toàn giữa nhiều worker

Nếu nhiều worker cùng lấy job, chỉ đọc batch rồi xử lý ngoài transaction có thể khiến hai worker nhận cùng một hàng. Cần cơ chế claim:

- Cập nhật trạng thái từ READY sang PROCESSING trong transaction.
- Dùng row lock/skip locked nếu engine hỗ trợ và semantics phù hợp.
- Gắn owner/lease và expiry.
- Có heartbeat hoặc timeout để phục hồi worker chết.
- Dùng idempotency key để xử lý lại an toàn.
- Commit claim ngắn trước khi xử lý dài nếu thiết kế cho phép.

SKIP LOCKED có semantics và cú pháp khác nhau theo engine. Nó phù hợp cho một số queue-like workload nhưng có thể bỏ qua hàng đang bị giữ và không bảo đảm thứ tự FIFO nghiêm ngặt.

### 6.10. Checkpoint và phục hồi

Khi chia transaction thành nhiều batch, job không còn atomic trên toàn bộ tập. Cần có checkpoint bền vững và trạng thái job:

- Batch nào đã commit?
- Batch nào đang chạy?
- Worker nào sở hữu?
- Lần retry có thể ghi lặp không?
- Nếu batch lỗi giữa chừng, dữ liệu nào đã commit?
- Có thể resume từ checkpoint mà không bỏ sót hoặc trùng không?

Thiết kế thao tác idempotent hoặc dùng unique constraint/idempotency key để retry an toàn. Ghi checkpoint cùng transaction với thay đổi batch nếu chúng phải đồng bộ.

## 7. Giảm blocking và deadlock trong SQL

### 7.1. Giữ transaction ngắn

- Không gọi HTTP/RPC khi đang giữ write lock nếu có thể.
- Không chờ user input trong transaction.
- Chuẩn bị dữ liệu và validate trước khi mở transaction.
- Đóng cursor/result set và kết thúc transaction sớm.
- Không để connection idle in transaction.
- Dùng transaction timeout hoặc idle-in-transaction timeout theo engine và nghiệp vụ.

### 7.2. Truy cập tài nguyên theo thứ tự nhất quán

Nếu một transaction cập nhật customer rồi account, tất cả code path liên quan nên dùng cùng thứ tự. Khi cập nhật nhiều hàng, sắp xếp ID trước khi khóa hoặc ghi nếu semantics cho phép.

~~~text
Quy tắc:
  lock account theo account_id tăng dần
  sau đó lock ledger theo ledger_id tăng dần

Không có code path nào đảo thứ tự hai nhóm tài nguyên.
~~~

Trigger và cascade cũng phải được xem xét vì chúng có thể lấy khóa ẩn trong quá trình statement chạy.

### 7.3. Giảm phạm vi dữ liệu bị tác động

- Predicate phải xác định đúng hàng.
- Dùng index phù hợp cho điều kiện tìm kiếm.
- Tránh UPDATE không cần thiết nếu giá trị không đổi.
- Tránh transaction cập nhật nhiều hàng hơn yêu cầu.
- Dùng partition pruning khi phù hợp.
- Xem lại trigger/cascade có mở rộng phạm vi không.

UPDATE một cột bằng chính giá trị cũ vẫn có thể tạo log, trigger, lock hoặc index maintenance tùy engine; tránh ghi thừa nếu có thể.

### 7.4. Cẩn thận với SELECT FOR UPDATE

SELECT FOR UPDATE hữu ích khi cần đọc rồi cập nhật cùng một hàng mà không để transaction khác thay đổi giữa hai bước. Nhưng khóa được giữ đến commit/rollback và có thể làm tăng contention.

Nếu có thể, dùng một câu UPDATE có điều kiện nguyên tử:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 1
WHERE product_id = 42
  AND available_qty >= 1;
~~~

Sau đó kiểm tra số hàng bị ảnh hưởng. Nếu một hàng được cập nhật, thao tác thành công; nếu không có hàng nào, có thể không đủ tồn kho hoặc sản phẩm không tồn tại. Cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

### 7.5. Optimistic concurrency

Với dữ liệu ít xung đột, có thể dùng version column:

~~~sql
UPDATE documents
SET body = 'new content',
    version = version + 1
WHERE document_id = 100
  AND version = 7;
~~~

Nếu số hàng cập nhật bằng 0, dữ liệu đã thay đổi kể từ lần đọc; ứng dụng cần reload, merge hoặc báo conflict.

Optimistic concurrency giảm việc giữ khóa trong lúc người dùng chỉnh sửa dài, nhưng vẫn có khóa ngắn trong UPDATE và có thể tăng conflict/retry nếu contention thực tế cao.

### 7.6. Không dùng NOLOCK hoặc dirty read như cách chữa cháy

Đọc dữ liệu chưa commit có thể trả giá trị chưa được xác nhận, hàng bị đọc lặp/bỏ qua hoặc kết quả không nhất quán tùy engine. Nó không sửa blocker cho write transaction và có thể làm báo cáo sai.

Nếu cần giảm read/write blocking, hãy đánh giá row-versioning/MVCC hoặc snapshot isolation theo DBMS, dung lượng version store, semantics và tác động đến transaction dài.

### 7.7. Retry deadlock có giới hạn

Deadlock victim thường có thể retry nếu thao tác có tính idempotent hoặc transaction được thiết kế để chạy lại an toàn.

Quy tắc:

- Retry toàn bộ transaction đã rollback, không chỉ statement cuối.
- Giới hạn số lần retry.
- Dùng exponential backoff và jitter.
- Không retry lỗi validation hoặc constraint không thể tự hết.
- Dùng idempotency key cho thao tác có side effect.
- Ghi metric deadlock và retry count.
- Nếu deadlock lặp lại, sửa thứ tự truy cập hoặc access path.

Retry vô hạn có thể biến deadlock thành retry storm.

## 8. Deadlock: phân tích và phòng ngừa

### 8.1. Đọc deadlock graph

Deadlock graph thường biểu diễn:

- Process/session tham gia.
- Resource bị tranh chấp.
- Lock mode đang giữ.
- Lock mode đang yêu cầu.
- Statement và transaction context.
- Victim được chọn.

Vẽ thành chu trình và xác định mỗi transaction đã giữ gì trước khi yêu cầu resource tiếp theo. Sau đó ánh xạ về code path, thứ tự cập nhật, trigger và index.

### 8.2. Deadlock không chỉ do hai UPDATE đối xứng

Deadlock có thể xuất hiện giữa:

- UPDATE và SELECT FOR UPDATE.
- Hai bảng có foreign key/cascade.
- Transaction cập nhật parent/child theo thứ tự ngược nhau.
- Range lock và insert vào cùng khoảng.
- Index maintenance và thao tác ghi.
- Application lock kết hợp với row lock.
- DDL/metadata lock và query đang chạy.

Phân tích toàn bộ transaction và tài nguyên, không chỉ statement xuất hiện ở dòng cuối log.

### 8.3. Giảm khả năng deadlock

- Chuẩn hóa thứ tự truy cập bảng và hàng.
- Giữ transaction ngắn.
- Dùng index để tìm đúng tập hàng.
- Tránh range lock rộng nếu không cần isolation semantics đó.
- Không mở rộng transaction sang nhiều dịch vụ.
- Hạn chế batch size khi deadlock tăng theo số resource bị giữ.
- Dùng retry có backoff cho victim.
- Phân tách workload nóng nếu nghiệp vụ cho phép.

Không thể bảo đảm deadlock bằng không trong mọi hệ thống có concurrency phức tạp. Mục tiêu là giảm xác suất, giảm chi phí victim và bảo đảm retry an toàn.

## 9. Tình huống thực tế: job cập nhật tồn kho gây blocking

### 9.1. Bối cảnh

Một hệ thống bán hàng có job đồng bộ tồn kho từ nhà cung cấp. Job đọc file gồm 120.000 dòng, mở một transaction duy nhất, cập nhật từng sản phẩm rồi commit khi hoàn tất.

Trong giờ cao điểm:

- API đặt hàng thường xuyên cập nhật cùng bảng inventory.
- p95 của thao tác reserve tăng từ 45 ms lên 2,8 giây.
- Blocking chain kéo dài, root blocker là connection của job import.
- Một số deadlock xảy ra giữa import và reserve.
- Transaction log tăng nhanh và rollback mất nhiều phút khi job bị hủy.

### 9.2. Thu thập bằng chứng

Nhóm vận hành ghi nhận:

- Job import giữ transaction khoảng 11 phút.
- Một số product_id có tần suất cập nhật cao.
- Import duyệt sản phẩm theo thứ tự file; API reserve cập nhật theo thứ tự request.
- Index lookup cho từng dòng có chi phí khác nhau.
- Transaction import giữ nhiều khóa cùng lúc.
- Job gọi dịch vụ xác thực nhà cung cấp trong khi transaction vẫn mở.
- Deadlock graph cho thấy hai đường code khóa product và warehouse theo thứ tự ngược nhau.

### 9.3. Giả thuyết

1. Transaction import quá dài làm tăng thời gian giữ khóa.
2. Batch 120.000 dòng giữ lock footprint quá lớn.
3. Thứ tự truy cập product/warehouse không nhất quán tạo deadlock.
4. Gọi dịch vụ ngoài transaction kéo dài critical section.
5. Một số product nóng khiến nhiều worker cùng tranh chấp.
6. Index chưa phù hợp làm tăng thời gian tìm và cập nhật hàng.

### 9.4. Thay đổi thử nghiệm

- Đọc và xác thực file trước transaction.
- Chuẩn hóa thứ tự xử lý theo warehouse_id rồi product_id.
- Chia import thành batch 250 dòng, mỗi batch là transaction riêng nếu nghiệp vụ cho phép.
- Ghi checkpoint và trạng thái batch cùng transaction.
- Dùng idempotency key để retry batch không ghi lặp.
- Giới hạn hai import worker đồng thời.
- Dùng một câu UPDATE có điều kiện cho thao tác reserve.
- Bổ sung/điều chỉnh index sau khi kiểm tra workload ghi.
- Retry deadlock tối đa ba lần với backoff và jitter.
- Không gọi dịch vụ ngoài khi đang giữ khóa.

Batch size 250 chỉ là giá trị thử nghiệm trong ví dụ; cần benchmark theo kích thước hàng và môi trường thật.

### 9.5. Kết quả minh họa

| Chỉ số | Trước | Sau thử nghiệm |
|---|---:|---:|
| Transaction duration p95 | 11 phút | 420 ms |
| Reserve API p95 | 2.800 ms | 68 ms |
| Deadlock | 18 lần/giờ | 1 lần/giờ |
| Longest blocking chain | 74 giây | 1,2 giây |
| Import throughput | 1.900 dòng/giây | 1.650 dòng/giây |
| Rollback tối đa | Nhiều phút | Dưới 1 giây mỗi batch |

Số liệu chỉ minh họa. Import throughput giảm nhẹ vì worker bị giới hạn và commit nhiều lần, nhưng API tương tác ổn định hơn, rollback nhỏ hơn và sự cố dễ phục hồi hơn. Nếu nghiệp vụ yêu cầu toàn bộ file phải atomic, cần một thiết kế staging/version switch hoặc quy trình publish sau khi load hoàn tất thay vì commit từng phần trực tiếp vào bảng đang phục vụ.

### 9.6. Điều kiện chấp nhận

- Không bỏ sót hoặc áp dụng trùng dòng import.
- Có thể resume sau khi worker chết.
- Trạng thái batch và checkpoint nhất quán.
- Reserve không oversell và giữ đúng invariant tồn kho.
- p95/p99 API tương tác đạt SLO.
- Deadlock/lock wait giảm dưới tải hỗn hợp.
- Log, memory và rollback nằm trong ngân sách.
- Các query khác trên inventory không bị regression.
- Có cơ chế dừng job và rollback/compensate theo nghiệp vụ.

## 10. Thiết kế transaction cho batch job

### 10.1. Mẫu xử lý theo batch

~~~text
while còn dữ liệu:
    đọc một batch theo khóa ổn định
    xác thực và chuẩn bị ngoài transaction

    BEGIN
      claim batch hoặc xác minh checkpoint
      cập nhật các hàng theo thứ tự ổn định
      ghi kết quả và checkpoint
    COMMIT

    phát metric và tiếp tục batch kế tiếp
~~~

Nếu transaction lỗi, rollback chỉ ảnh hưởng batch hiện tại. Các batch đã commit được giữ lại và job có thể resume từ checkpoint.

### 10.2. Xử lý dữ liệu mới trong khi job đang chạy

Nếu nguồn tiếp tục nhận dữ liệu mới, cần xác định tập đầu vào của job:

- Snapshot ID hoặc watermark.
- Cutoff timestamp.
- Range ID đã chốt.
- Version của file/import.
- Partition hoặc batch manifest.

Không dùng điều kiện ID lớn hơn last_id mà không xem xét ID có thể được cấp phát trước nhưng commit sau; trong một số hệ thống, thứ tự ID không đồng nghĩa thứ tự commit. Dùng manifest hoặc watermark theo semantics nguồn để tránh bỏ sót.

### 10.3. Exactly-once và idempotency

Trong hệ thống phân tán, retry có thể khiến một batch được gửi nhiều lần. Thực tế thường xây dựng xử lý at-least-once với thao tác idempotent thay vì giả định exactly-once toàn hệ thống.

Có thể dùng:

- Unique key cho source event hoặc import row.
- Idempotency key.
- Upsert có điều kiện theo version.
- Processed-event table.
- Checkpoint cập nhật cùng transaction với dữ liệu.
- Outbox để phát event sau commit.

Nếu side effect nằm ngoài DBMS, cần transactional outbox, deduplication hoặc saga/compensation phù hợp.

### 10.4. Giới hạn concurrency của batch worker

Thêm worker chỉ giúp tăng throughput đến khi DBMS hoặc tài nguyên nóng đạt giới hạn. Sau điểm đó, thêm worker làm lock wait, log contention, CPU và I/O tăng.

Thử concurrency 1, 2, 4, 8 theo workload đại diện. Với mỗi mức, đo:

- Rows/second.
- Transaction duration.
- Lock wait p95/p99.
- Deadlocks.
- Log bytes/second.
- CPU, I/O và storage latency.
- API OLTP p95/p99.
- Retry count.

Chọn concurrency tối đa vẫn giữ SLO cho workload tương tác và có headroom cho traffic bất thường.

## 11. Timeout, cancellation và xử lý lỗi

### 11.1. Phân biệt timeout

- **Lock timeout:** giới hạn thời gian chờ khóa.
- **Statement timeout:** giới hạn thời gian thực thi câu lệnh.
- **Transaction timeout:** giới hạn vòng đời transaction nếu framework/engine hỗ trợ.
- **Connection/pool timeout:** giới hạn thời gian chờ lấy connection.
- **Request timeout:** giới hạn thời gian ở tầng ứng dụng.

Các timeout cần được phối hợp. Request timeout xảy ra trước statement timeout có thể khiến client bỏ request trong khi DBMS vẫn chạy nếu cancellation không được truyền xuống.

### 11.2. Khi timeout xảy ra

Ứng dụng cần:

1. Hủy statement nếu driver hỗ trợ.
2. Xác định transaction còn active hay đã bị rollback.
3. Rollback transaction nếu cần.
4. Đóng cursor/statement.
5. Trả connection về pool chỉ khi session ở trạng thái sạch.
6. Ghi lại wait resource, query fingerprint và transaction age.
7. Phân loại lỗi có thể retry và lỗi không thể retry.

Không giữ connection trong pool khi transaction còn mở hoặc trạng thái session không rõ.

### 11.3. Cancellation trong batch

Nếu người vận hành dừng job:

- Ngừng claim batch mới.
- Cho batch hiện tại hoàn tất hoặc rollback theo chính sách.
- Lưu checkpoint của batch đã commit.
- Giải phóng lock và connection.
- Ghi trạng thái job là PAUSED, FAILED hoặc CANCELLED phù hợp.
- Khi resume, kiểm tra idempotency và version trước khi xử lý lại.

Không hủy tùy tiện một transaction đang cập nhật trạng thái liên quan nếu chưa biết cách phục hồi.

### 11.4. Retry phải có phân loại lỗi

Có thể retry deadlock victim hoặc lỗi tạm thời nếu transaction đã rollback và thao tác idempotent. Không nên retry vô hạn cho:

- Vi phạm constraint do dữ liệu đầu vào sai.
- Lỗi authorization.
- Validation thất bại.
- Conflict nghiệp vụ cần người dùng giải quyết.
- Lỗi schema hoặc kiểu dữ liệu.

Dùng exponential backoff và jitter để tránh nhiều worker retry cùng lúc. Ghi lại số lần retry, nguyên nhân, thời gian chờ và kết quả cuối.

## 12. Đo hiệu quả sau điều chỉnh

### 12.1. Nhóm chỉ số khóa

- Số lock wait và tổng lock wait time.
- p50/p95/p99 của wait duration.
- Số waiter và blocker đồng thời.
- Longest blocking chain.
- Deadlocks theo thời gian.
- Lock timeout count.
- Transaction age và duration.
- Lock escalation hoặc lock memory nếu engine cung cấp.

### 12.2. Nhóm chỉ số transaction và log

- Rows/transaction.
- Statements/transaction.
- Transaction duration p50/p95/p99.
- Log bytes/transaction và log bytes/second.
- Commit rate và commit latency.
- Rollback count và rollback duration.
- Retry count.
- Checkpoint lag hoặc replication lag nếu có.

### 12.3. Nhóm chỉ số toàn hệ thống

- Throughput theo loại workload.
- API p95/p99.
- CPU, memory, storage IOPS và latency.
- Query logical/physical reads.
- Connection pool active/pending.
- Temp usage và spill.
- Error rate và timeout.
- Tính đúng đắn dữ liệu sau retry/resume.

Không đánh giá chỉ bằng số deadlock. Một thay đổi có thể giảm deadlock nhưng tăng blocking kéo dài hoặc làm throughput giảm.

### 12.4. Benchmark hỗn hợp

Một benchmark phù hợp nên có:

- OLTP request đọc/ghi thông thường.
- Một hoặc nhiều batch worker.
- Key nóng và key phân bố đều.
- Transaction ngắn và transaction dài đại diện.
- Dữ liệu gần kích thước production.
- Concurrency tăng từng bước.
- Thời lượng đủ để quan sát commit, log flush, checkpoint và retry.

So sánh trước/sau trên cùng workload mix. Không chỉ chạy batch một mình vì contention thường chỉ xuất hiện khi batch chạy đồng thời với traffic thật.

### 12.5. Kiểm tra correctness

Sau thay đổi, xác minh:

- Tổng số hàng đã xử lý.
- Không mất hoặc trùng event.
- Tổng tồn kho/số dư vẫn đúng invariant.
- Checkpoint khớp với batch đã commit.
- Retry không nhân đôi side effect.
- Thứ tự trạng thái nghiệp vụ hợp lệ.
- Không có transaction mở bất thường.
- Không còn session idle in transaction vượt ngưỡng.

Hiệu năng tốt nhưng dữ liệu sai là kết quả không thể chấp nhận.

## 13. Checklist điều tra và quyết định

Khi gặp blocking hoặc deadlock, đi theo thứ tự:

1. Xác định request/job bị ảnh hưởng và SLO.
2. Lấy waiter, blocker, root blocker và lock resource.
3. Ghi transaction age, statement và application/request ID.
4. Phân biệt blocking, deadlock, timeout và wait khác.
5. Thu deadlock graph nếu có.
6. Kiểm tra isolation level, access path, index và số hàng thực tế.
7. Tìm transaction dài, idle in transaction, hot row hoặc thứ tự khóa ngược.
8. Xác định batch size, transaction boundary và lượng log.
9. Đưa ra một giả thuyết có thể kiểm chứng.
10. Thử thay đổi nhỏ: rút ngắn critical section, chuẩn hóa thứ tự, index, batch size hoặc concurrency.
11. Benchmark workload hỗn hợp và đo cả API lẫn batch.
12. Kiểm tra dữ liệu, retry, checkpoint và rollback.
13. Triển khai theo phạm vi nhỏ và theo dõi.
14. Cập nhật runbook, cảnh báo và ngưỡng vận hành.

### 13.1. Ma trận triệu chứng và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần tìm |
|---|---|---|
| Nhiều request chờ một session | Root blocker dài hoặc idle in transaction | Transaction age, session state, SQL gần nhất |
| Deadlock lặp lại giữa hai luồng | Thứ tự khóa ngược nhau | Deadlock graph, resource order |
| Wait tăng khi batch chạy | Batch quá lớn hoặc concurrency cao | Rows/transaction, lock duration, worker count |
| Một sản phẩm thường xuyên bị chặn | Hot row/hot key | Lock resource và tần suất cập nhật theo key |
| UPDATE chậm và đọc nhiều | Index thiếu hoặc predicate rộng | Actual plan, rows scanned, logical reads |
| Batch rollback rất lâu | Transaction/log quá lớn | Log bytes, transaction duration, rollback time |
| Read transaction lâu gây bloat/version pressure | Snapshot giữ lâu | Transaction age, vacuum/undo/version metrics |
| Thêm worker làm throughput giảm | Contention hoặc resource saturation | Lock wait, CPU, log, I/O, queue depth |

### 13.2. Tiêu chí chấp nhận thay đổi

Chỉ chấp nhận khi:

- Blocking duration và deadlock giảm theo mục tiêu.
- Transaction duration nằm trong ngân sách.
- Throughput tổng thể đạt hoặc cải thiện.
- API OLTP p95/p99 không bị ảnh hưởng xấu.
- Log, rollback và resource usage có headroom.
- Batch resume và retry an toàn.
- Invariant dữ liệu được bảo toàn.
- Không phát sinh lỗi hoặc starvation cho nhóm request khác.
- Có rollback và runbook rõ ràng.

## 14. Những sai lầm thường gặp

**Chỉ kill session đang chặn.**  
Nếu không sửa nguyên nhân, blocking sẽ tái diễn; rollback còn có thể gây tải bổ sung.

**Tăng connection pool hoặc worker count.**  
Nhiều transaction hơn có thể cùng tranh chấp hot row và làm lock wait tăng.

**Chỉ giảm batch size mà không đo.**  
Batch quá nhỏ làm tăng commit overhead; cần benchmark để tìm điểm cân bằng.

**Chia nhỏ business transaction cần atomicity.**  
Có thể làm lộ trạng thái trung gian hoặc vi phạm invariant.

**Gọi dịch vụ ngoài trong transaction.**  
Tăng thời gian giữ khóa và làm DB phụ thuộc vào latency mạng.

**Dùng NOLOCK/dirty read để né blocking.**  
Có thể trả dữ liệu chưa commit hoặc không nhất quán.

**Retry deadlock vô hạn.**  
Có thể tạo retry storm và che giấu thứ tự khóa sai.

**Bỏ qua trigger và foreign key.**  
Một statement có thể khóa thêm tài nguyên ở bảng khác.

**Chỉ nhìn query đang chạy.**  
Root blocker có thể idle in transaction và không có request active.

**Đánh giá bằng deadlock count duy nhất.**  
Blocking duration, throughput, p95/p99 và correctness cũng quan trọng.

**Tạo index mới mà không đo write cost.**  
Index giúp tìm hàng nhanh hơn nhưng tăng chi phí insert/update/delete và maintenance.

**Commit batch nhưng không có checkpoint.**  
Job có thể bỏ sót hoặc xử lý lặp sau khi restart.

## 15. Kết luận

Tranh chấp khóa là kết quả của nhiều transaction cùng cần tài nguyên trong khi transaction khác chưa giải phóng chúng. Muốn xử lý đúng, cần xác định root blocker, lock resource, transaction age, wait type và thứ tự truy cập dữ liệu. Deadlock cần deadlock graph để tìm chu trình; blocking kéo dài thường cần rút ngắn transaction hoặc xử lý session giữ khóa.

Điều chỉnh kích thước giao dịch là một bài toán cân bằng. Transaction quá lớn giữ nhiều khóa lâu, tạo log và rollback lớn; transaction quá nhỏ tăng commit overhead. Chọn batch size và concurrency bằng benchmark dưới workload hỗn hợp, đặt checkpoint/idempotency khi chia job, và giữ nguyên business atomicity ở những nơi nghiệp vụ yêu cầu.

Một thay đổi chỉ có giá trị khi giảm lock wait mà vẫn giữ throughput, SLO và tính đúng đắn dữ liệu. Theo dõi transaction duration, deadlock, blocker chain, log, retry và p95/p99 giúp phát hiện sớm khi dữ liệu hoặc traffic thay đổi.

## Câu hỏi tự kiểm tra

1. Blocking và deadlock khác nhau ở cấu trúc chờ như thế nào?
2. Vì sao root blocker có thể là session idle in transaction?
3. Transaction duration khác lock duration ra sao?
4. Access path không phù hợp có thể làm tăng lock footprint như thế nào?
5. Vì sao cùng một bảng có thể gặp hot row dù mỗi transaction rất ngắn?
6. Hãy mô tả cách thứ tự truy cập hai hàng có thể tạo deadlock.
7. Isolation level ảnh hưởng blocking và snapshot theo những cách nào?
8. Khi nào cần giữ một business transaction nguyên tử dù nó lớn?
9. Batch size và transaction size khác nhau như thế nào?
10. Cần đo những chỉ số nào để chọn batch size?
11. Vì sao chia batch cần checkpoint và idempotency?
12. Khi nào SELECT FOR UPDATE phù hợp và khi nào UPDATE có điều kiện là lựa chọn đơn giản hơn?
13. Vì sao NOLOCK không phải giải pháp tổng quát cho blocking?
14. Deadlock retry cần những giới hạn và điều kiện gì?
15. Hãy thiết kế benchmark chạy đồng thời OLTP và batch worker, nêu metric trước/sau.
16. Một batch job cập nhật tồn kho bị blocking: bạn sẽ thu thập bằng chứng và thay đổi theo thứ tự nào?
17. Làm thế nào xác minh sau khi chia transaction rằng không mất, trùng hoặc đảo thứ tự dữ liệu?

Khi gặp tranh chấp khóa, hãy lần theo chuỗi: session nào đang chờ, ai đang chặn, khóa nào bị giữ, transaction đã mở bao lâu, vì sao nó chưa kết thúc và lượng công việc nào thực sự cần nằm trong cùng một commit. Trả lời được các câu hỏi đó sẽ giúp chọn đúng điểm cắt transaction và cải thiện concurrency mà vẫn bảo toàn nghiệp vụ.
