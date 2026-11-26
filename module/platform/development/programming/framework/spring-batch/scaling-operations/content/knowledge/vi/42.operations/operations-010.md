# Runbook khi metadata bị lock trong Spring Batch

## 1. Mục đích và phạm vi xử lý

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, Spring Batch được mở rộng để xử lý workload dữ liệu lớn bằng **multi-threaded step**, **parallel steps**, **partitioning** và những mô hình phân tán. Càng nhiều job, step hoặc worker hoạt động đồng thời, **JobRepository** càng nhận nhiều thao tác tạo và cập nhật metadata. Nếu có transaction giữ khóa quá lâu, nhiều lần khởi chạy tranh cùng một JobInstance, kết nối cạn hoặc cơ sở dữ liệu thực hiện migration, quá trình xử lý batch có thể bị chậm, treo hoặc thất bại.

Runbook này hướng dẫn vận hành **khi nghi ngờ metadata của Spring Batch bị lock**: phát hiện, phân loại, tìm session gây chặn, hạn chế tác động, khôi phục an toàn, restart đúng job và ngăn tái diễn. Mục tiêu quan trọng nhất là **giữ tính nhất quán của metadata và dữ liệu nghiệp vụ**, ngay cả khi phải giảm throughput hoặc tạm dừng nhận job mới.

Sau bài học, bạn có thể:

- Phân biệt **database lock wait**, **deadlock**, **optimistic locking conflict**, **JDBC pool exhaustion** và **MySQL metadata lock (MDL)**.
- Xác định job/step/partition và SQL transaction đang bị chặn qua log, metrics, JobRepository và công cụ của database.
- Thực hiện các bước ứng phó có kiểm soát mà không sửa thủ công trạng thái các bảng BATCH_*.
- Đánh giá việc **stop, restart hoặc giữ nguyên để điều tra** dựa trên trạng thái persisted và tác dụng phụ đã commit.
- Thiết lập cảnh báo và cải tiến cấu hình khi scale manager/worker để giảm contention.

**Giới hạn:** Đây là runbook cho môi trường vận hành được ủy quyền. Ví dụ SQL bên dưới chỉ đọc dữ liệu chẩn đoán. Mọi thao tác kết thúc transaction/session, thay đổi cấu trúc bảng hoặc sửa metadata bền vững phải tuân theo quy trình ứng cứu database và được đánh giá tác động trước khi thực hiện.

## 2. "Metadata bị lock" có thể là những sự cố khác nhau

Từ **metadata** trong thực tế có ít nhất hai nghĩa:

1. **Metadata của Spring Batch**: các bản ghi trong những bảng như BATCH_JOB_INSTANCE, BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION và BATCH_*_EXECUTION_CONTEXT. Chúng có thể gặp row-level lock, tranh chấp transaction, deadlock hoặc cập nhật optimistic version thất bại.
2. **Database metadata lock (MDL)**: một kiểu khóa ở tầng schema/object của database, thường được nhắc đến trong MySQL khi câu lệnh ALTER TABLE, DROP hoặc DDL phải đợi transaction khác. Đây là khái niệm **khác** với việc hàng dữ liệu của các bảng BATCH_* bị khóa.

Trong PostgreSQL cũng có lock liên quan relation/DDL và row/transaction; vì vậy cần kiểm tra **loại khóa thực tế**, không kết luận từ tên bảng hoặc một thông báo "timeout" duy nhất.

| Triệu chứng | Khả năng cần xác minh | Dấu hiệu phân biệt |
|---|---|---|
| JDBC statement chờ rồi báo lock timeout | Transaction khác giữ lock trên row/table hoặc chờ DDL | Database xác nhận blocked ↔ blocker, wait event thuộc lock |
| Database trả deadlock victim | Hai hoặc nhiều transaction tạo chu trình chờ khóa | Deadlock log/SQLSTATE và một transaction bị database rollback |
| Spring Batch báo optimistic locking | Version của JobExecution/StepExecution đã đổi trước lần update | Exception liên quan version; có thể **không có DB lock wait** |
| Lấy connection rất lâu rồi timeout | JDBC pool hết connection hoặc DB không chấp nhận thêm kết nối | Pool pending cao; không mặc nhiên là row lock |
| Manager tạo JobExecution thất bại khi khởi chạy trùng | Hai launcher cạnh tranh cùng JobInstance hoặc isolation lúc tạo metadata | Cùng job name và identifying JobParameters; xem transaction và lỗi cụ thể |
| MySQL báo "Waiting for table metadata lock" | MDL liên quan bảng/DDL, đôi khi do transaction dài | performance_schema.metadata_locks có yêu cầu đang PENDING |
| Worker không nhận partition/reply | Broker, routing, timeout, mạng hoặc version mismatch | Không có bằng chứng DB lock dù JobRepository chưa cập nhật |
| Job vẫn STARTED sau khi process chết | Trạng thái persisted chưa được kết thúc vì crash | Không suy ra DB còn giữ lock; cần đối chiếu process và execution |

**Quy tắc đầu tiên:** phải chứng minh có session/transaction đang chặn hoặc có deadlock được ghi nhận. Đừng dùng việc "job chạy lâu" hoặc "metadata chưa đổi" làm bằng chứng duy nhất của lock.

## 3. Metadata nào đang chịu tác động?

Spring Batch sử dụng **JobRepository** để lưu danh tính và tiến độ job. Tên và cách tạo bảng có thể khác theo schema prefix hoặc database vendor, nhưng các nhóm dữ liệu thường gặp gồm:

| Nhóm metadata | Vai trò | Rủi ro khi tranh chấp |
|---|---|---|
| BATCH_JOB_INSTANCE | Nhận diện JobInstance theo job name và identifying JobParameters | Khởi chạy cạnh tranh cùng job |
| BATCH_JOB_EXECUTION và BATCH_JOB_EXECUTION_PARAMS | Lần thực thi và tham số của job | Không tạo hoặc cập nhật execution, status bị trễ |
| BATCH_STEP_EXECUTION | Tiến độ, counts, version và trạng thái step | Worker chờ cập nhật hoặc gặp optimistic locking |
| BATCH_JOB_EXECUTION_CONTEXT | State cần lưu cho job | Restart không đọc được state đã commit nếu ghi lỗi |
| BATCH_STEP_EXECUTION_CONTEXT | State checkpoint của step/partition | Worker restart sai vị trí nếu state/transaction không nhất quán |
| Sequence/identity cấp ID | Sinh định danh execution theo schema của vendor | Có thể trở thành điểm tranh chấp trong một số thiết kế |

Khi mở rộng **remote partitioning**, manager và worker thường dùng chung JobRepository logic. Mỗi worker cần cập nhật StepExecution riêng của partition; tăng số partition và worker làm số lần ghi metadata cũng tăng. Với **multi-threaded step**, nhiều task có thể cùng góp phần cập nhật một StepExecution, nên phải xét đúng cơ chế điều phối, transaction và thread safety của Spring Batch.

~~~mermaid
flowchart LR
    L[Scheduler / JobLauncher] --> M[Manager Job]
    M --> R[(JobRepository metadata DB)]
    M --> P[Partition requests / broker]
    P --> W1[Worker 1]
    P --> W2[Worker 2]
    P --> WN[Worker N]
    W1 --> R
    W2 --> R
    WN --> R
    W1 --> D[(Business DB)]
    W2 --> D
    WN --> D
~~~

Nếu **business tables** bị khóa, worker có thể dừng tại writer trong transaction nghiệp vụ trước khi cập nhật metadata. Nếu **BATCH_*** bị khóa, thao tác ghi tiến độ hoặc tạo execution có thể bị chặn dù business DB còn rảnh. Khi hai nhóm bảng nằm chung một database, phải phân biệt chúng bằng **câu SQL bị chặn, transaction và object thực tế**, không chỉ tên datasource.

## 4. Sơ đồ quyết định khi nhận cảnh báo

~~~mermaid
flowchart TD
    A[Cảnh báo: job treo, timeout, lock error] --> B[Giữ job/execution ID và mốc thời gian]
    B --> C{DB có blocked session hoặc deadlock?}
    C -->|Có| D[Truy vết blocker, loại khóa, tuổi transaction]
    C -->|Không| E[Kiểm tra JDBC pool, broker, worker, optimistic version]
    D --> F{Blocker là transaction bình thường sắp kết thúc?}
    F -->|Có| G[Theo dõi có deadline; giảm tải đầu vào]
    F -->|Không hoặc chưa rõ| H[Escalate DBA và owner transaction]
    G --> I[Lock giảm, kiểm tra job state và dữ liệu]
    H --> I
    E --> I
    I --> J{Job được phép restart và state đáng tin?}
    J -->|Có| K[Restart đúng JobInstance, đối soát output]
    J -->|Không hoặc chưa rõ| L[Giữ nguyên state, điều tra và khôi phục có kiểm soát]
~~~

Luồng trên **không tự động cho phép** terminate session hoặc restart một execution đang STARTED. Sự an toàn của hành động phụ thuộc transaction đã commit, worker thực sự còn sống, độ bền của message và idempotency của writer.

## 5. Runbook theo mốc thời gian sự cố

Các mốc sau chỉ là **khung điều phối tham khảo**, không phải SLA cố định. Với workload tài chính hoặc batch cuối ngày có deadline nghiêm ngặt, thời hạn và người chịu trách nhiệm phải được chốt theo SLO riêng.

| Pha | Việc làm | Bằng chứng phải giữ |
|---|---|---|
| 0–5 phút: phát hiện | Ghi incident ID, thời gian, job name, jobExecutionId, stepExecutionId, release và môi trường; xác định diện ảnh hưởng | Log lỗi đầu tiên, metrics JDBC và database, job status |
| 5–15 phút: phân loại | Kiểm tra blocked/blocker, tuổi transaction, bảng liên quan, pool pending, broker backlog, worker heartbeat | SQL đang chờ, session, lock mode, timestamp, trace |
| 15–30 phút: khoanh vùng | Giảm/tạm ngừng launch mới hoặc retry gây bão hòa; liên hệ owner/DBA của blocker; xác định việc đang commit | Số job/partition đang chạy, transaction state và danh sách thao tác |
| Sau khi hết khóa | Xác minh JobRepository cập nhật bình thường, transaction thất bại có rollback, xác định job FAILED/STOPPED/STARTED | Tình trạng persisted của từng execution và output |
| Phục hồi | Restart khi đủ điều kiện; đối soát record và side effect; mở lại tải theo từng mức | Result reconciliation, metric sau phục hồi, timeline |
| Sau sự cố | Phân tích nguyên nhân, điều chỉnh concurrency/transaction/isolation/query/cảnh báo | RCA, thay đổi được thử và runbook cập nhật |

Trong suốt sự cố, thông tin gửi cho nhóm vận hành nên trả lời: **job nào đang bị ảnh hưởng, dữ liệu đã commit đến đâu, có người/transaction nào đang chặn, hành động nào đã được phép thực hiện và tiêu chí nào cho phép mở lại workload**.

## 6. Thu thập bằng chứng mà không làm xáo trộn trạng thái

### 6.1. Ở Spring Batch và ứng dụng

Tối thiểu cần đối chiếu:

- Job name, **identifying JobParameters**, JobInstance ID, JobExecution ID, StepExecution ID và tên partition/worker.
- BatchStatus và ExitStatus, thời gian start/end/last updated, số lần **commit/rollback**, read/write/filter/skip count.
- Exception chain và SQLSTATE/vendor error code, tên datasource/connection pool, thời điểm xảy ra statement timeout hoặc deadlock.
- Phiên bản ứng dụng/JDK/Spring Batch, số manager/worker replica và cấu hình task executor, grid size, chunk size, concurrency.
- Số active/pending/idle JDBC connections, thời gian lấy connection, CPU, GC, queue depth, broker lag và retry rate.
- Log có correlation ID giữa manager → worker → JobRepository; tránh ghi toàn bộ JobParameters, ExecutionContext hoặc payload nếu chứa dữ liệu nhạy cảm.

Nếu có Actuator/Micrometer, đối chiếu metric datasource pool, transaction, JVM và Spring Batch đã bật sẵn. Tên metric và nhãn thay đổi theo phiên bản; đừng suy ra lỗi locking chỉ từ một giá trị pool utilization cao.

### 6.2. Ở database

Thu thập trong **cùng cửa sổ thời gian**:

1. Session **đang bị chặn** và session **đang chặn**, cùng SQL/transaction state.
2. Loại lock, object (bảng/index/row/transaction) và thời gian bắt đầu chờ.
3. Transaction tuổi cao, đặc biệt session **idle in transaction**.
4. Chỉ số deadlock/lock timeout, replication lag, CPU/IO và connection utilization.
5. Liệu blocker đến từ **batch**, ứng dụng khác, truy vấn DBA hay migration/DDL.

**Cẩn trọng với quyền và dữ liệu:** Các view chẩn đoán có thể yêu cầu quyền giám sát riêng. SQL text có thể chứa giá trị nhạy cảm; chỉ chia sẻ bản đã làm sạch. Chụp kết quả bằng truy vấn chỉ đọc và giới hạn phạm vi/time window.

## 7. Chẩn đoán trên PostgreSQL

### 7.1. Tìm blocked session và session đang chặn

Ví dụ dưới đây chỉ đọc các view hệ thống và dùng hàm **pg_blocking_pids** để xác định PID đang giữ hoặc đứng trước trong hàng chờ khóa:

~~~sql
SELECT
    waiting.pid                  AS waiting_pid,
    waiting.application_name     AS waiting_app,
    waiting.state                AS waiting_state,
    waiting.wait_event_type,
    waiting.wait_event,
    waiting.query_start          AS waiting_query_start,
    blocker.pid                  AS blocker_pid,
    blocker.application_name     AS blocker_app,
    blocker.state                AS blocker_state,
    blocker.xact_start           AS blocker_xact_start,
    blocker.wait_event_type      AS blocker_wait_type,
    waiting.query                AS waiting_sql,
    blocker.query                AS blocker_last_sql
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(
    pg_blocking_pids(waiting.pid)
) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid
WHERE waiting.datname = current_database()
ORDER BY waiting.query_start NULLS LAST;
~~~

**Cách đọc:**

- **waiting_pid** là session bị chặn, **blocker_pid** là session đang chặn. Một waiting session có thể có nhiều blocker.
- **blocker_xact_start** cũ bất thường gợi ý transaction giữ khóa lâu; trạng thái **idle in transaction** đáng kiểm tra.
- **waiting_sql** cho biết câu lệnh bị kẹt có đụng tới BATCH_* hay bảng nghiệp vụ không. Chỉ nhìn thấy tên BATCH_* trong một query khác không đủ để kết luận.
- **blocker_last_sql** chỉ là câu query hiện tại/gần nhất của session theo view, **không nhất thiết là câu lệnh đã lấy khóa**. Phải đối chiếu transaction history/log/trace trước khi quy trách nhiệm.
- Quyền xem toàn bộ SQL của session khác phụ thuộc cấu hình/role database; kết quả thiếu SQL không chứng minh không có blocker.

Trong PostgreSQL, một phiên chờ **transactionid** cũng có thể xuất phát từ row lock; đừng đòi hỏi view nhất thiết hiện tên bảng BATCH_* cho mọi tình huống. Có thể đào sâu bằng **pg_locks**, relation OID và transaction timeline cùng DBA nếu cần.

### 7.2. Đối chiếu các transaction dài

~~~sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 30;
~~~

Các session dài **chưa chắc** sai. Transaction có thể đang làm việc hợp lệ, đặc biệt khi còn commit hoặc xử lý dữ liệu lớn. Cần xem owner, business transaction, quyền và trạng thái trước khi cân nhắc can thiệp.

### 7.3. Bằng chứng deadlock

Database thường phát hiện và phá chu trình deadlock bằng cách rollback một transaction. Khi log Java báo lỗi deadlock, kết hợp SQLSTATE, log PostgreSQL và transaction timeline để phân biệt **deadlock thực sự** với việc chờ lâu. Deadlock đã được database giải quyết có thể **không còn xuất hiện** trong ảnh chụp pg_stat_activity ở thời điểm điều tra.

Không chạy hàng loạt câu lệnh chẩn đoán tốn tài nguyên trong vòng lặp cực ngắn khi database đang quá tải. Ưu tiên một vài snapshot có timestamp và metric DB đã thu thập sẵn.

## 8. Chẩn đoán trên MySQL 8+

### 8.1. Row lock wait trên bảng JobRepository

Nếu dùng InnoDB/MySQL 8 có bật các bảng Performance Schema tương ứng, có thể truy vấn **data_lock_waits** và **data_locks**:

~~~sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    req.OBJECT_SCHEMA          AS object_schema,
    req.OBJECT_NAME            AS object_name,
    req.LOCK_TYPE              AS waiting_lock_type,
    req.LOCK_MODE              AS waiting_mode,
    blk.LOCK_MODE              AS blocking_mode,
    req.LOCK_STATUS            AS waiting_status,
    blk.LOCK_STATUS            AS blocking_status
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
ORDER BY req.OBJECT_SCHEMA, req.OBJECT_NAME;
~~~

Nếu **object_name** trỏ tới BATCH_JOB_EXECUTION hoặc BATCH_STEP_EXECUTION, metadata Spring Batch có thể đang chịu lock wait. Cần điều tra thêm transaction và SQL statement của các thread liên quan, với quyền giám sát phù hợp. Khi bảng performance_schema không được bật hoặc không có quyền, nhờ DBA dùng công cụ tương đương thay vì suy đoán.

### 8.2. MySQL metadata lock (MDL) trên object

Nếu thông báo lỗi nói rõ **"Waiting for table metadata lock"**, kiểm tra **metadata_locks** (khác với data_locks):

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
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, LOCK_STATUS, OWNER_THREAD_ID;
~~~

**PENDING** có thể là câu lệnh đang đợi MDL, ví dụ migration muốn ALTER một bảng đang có transaction sử dụng; các lock **GRANTED** cần được truy vết tới owner thread và transaction để tìm blocker thật. Không coi mọi dòng GRANTED là sự cố và không tự động kill session từ danh sách.

Nếu đang migration schema JobRepository trong lúc batch vẫn chạy, có thể cần **quiesce/drain workload**, sau đó hoàn tất migration theo kế hoạch đã được phê duyệt. Việc khóa là hậu quả tương tác giữa DDL và transaction, không nhất thiết là lỗi cấu hình Spring Batch.

### 8.3. SQL dialect và phiên bản

PostgreSQL, MySQL, Oracle và SQL Server có cách biểu diễn lock, error code và mức isolation khác nhau. Các ví dụ trên **không phải SQL dùng chung cho mọi database**. Khi vận hành trên DB khác, dùng view giám sát tương ứng, tài liệu DBA nội bộ và quyền truy cập chỉ đọc phù hợp.

## 9. Đối chiếu JobRepository để xác định execution bị ảnh hưởng

Sau khi tìm được lock, gắn nó với **execution cụ thể**. Ví dụ SQL logic dưới đây dùng **named bind parameter** của công cụ truy vấn/ứng dụng, không phải lệnh có thể dán nguyên xi vào mọi SQL console:

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED,
    je.VERSION
FROM BATCH_JOB_EXECUTION AS je
JOIN BATCH_JOB_INSTANCE AS ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = :job_execution_id;

SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.JOB_EXECUTION_ID,
    se.STATUS,
    se.START_TIME,
    se.END_TIME,
    se.LAST_UPDATED,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.VERSION
FROM BATCH_STEP_EXECUTION AS se
WHERE se.JOB_EXECUTION_ID = :job_execution_id
ORDER BY se.STEP_EXECUTION_ID;
~~~

Nếu dự án dùng **table prefix riêng**, schema thật hoặc DB version khác, thay tên đối tượng và cột tương ứng. Ưu tiên **JobExplorer** hoặc API đọc metadata hiện có nếu SQL trực tiếp không nằm trong quy trình vận hành cho phép.

**Đừng chỉ nhìn STATUS = STARTED.** Một JobExecution có thể vẫn mang trạng thái STARTED sau crash do chưa thể cập nhật metadata; đó không chứng minh worker còn chạy hoặc còn lock. Ngược lại, một worker có thể còn thực hiện tác dụng phụ ngay khi manager mất liên lạc. Cần đối chiếu **process sống, broker in-flight, DB transaction, timestamp và checkpoint**.

Nếu thấy VERSION đổi liên tục nhưng không có session chờ khóa, đây có thể là **concurrent update/optimistic locking**, không phải database row lock kéo dài. Việc đổi thủ công VERSION nhằm bỏ qua lỗi sẽ phá cơ chế bảo vệ consistency.

## 10. Những nguyên nhân gốc thường gặp

### 10.1. Nhiều launcher cùng khởi chạy một JobInstance

Hai scheduler/manager hoặc nhiều replica cùng gọi JobLauncher với **cùng job name và identifying JobParameters** có thể tranh nhau tạo JobInstance/JobExecution. Spring Batch có cơ chế bảo đảm tính nhất quán khi tạo metadata; tùy cách cấu hình JobRepository, mức isolation cho thao tác tạo có thể tương đối nghiêm ngặt và làm tăng contention.

Đừng xử lý bằng cách tự thêm một tham số thời gian khác cho mỗi lần retry: điều đó có thể tạo **JobInstance mới** và khiến cùng dữ liệu được xử lý lần thứ hai. Cần điều phối **single launcher/distributed scheduling lock** hoặc định nghĩa chính sách identity rõ ràng, đồng thời để JobRepository kiểm tra việc khởi chạy trùng.

### 10.2. Transaction hoặc callback giữ khóa quá lâu

Một transaction dài có thể giữ lock trên row metadata hoặc bảng nghiệp vụ, đặc biệt khi:

- Reader/processor/writer thực hiện I/O mạng lâu **trong** transaction.
- Chunk size quá lớn tạo transaction lớn, commit chậm và rollback đắt.
- Listener hoặc custom component mở transaction bao phủ thao tác chờ bên ngoài.
- Migration/DDL chạy cùng lúc job đang dùng bảng liên quan.
- JobRepository và business DB dùng chung datasource/transaction theo cách khiến transaction giữ tài nguyên lâu.

Không được mặc nhiên kết luận một phương thức writer dài là **thủ phạm khóa BATCH_***: cần xác minh statement lấy khóa và phạm vi transaction thật.

### 10.3. Scale vượt năng lực metadata database

Khi tăng worker, partition và số job đồng thời:

- Số lần tạo/cập nhật StepExecution tăng.
- Connection pool tổng cộng trên nhiều replica có thể vượt năng lực DB.
- Các transaction tranh cùng index/row khi chạy trùng job hoặc cập nhật shared state.
- Queue và retry làm backlog tăng, tạo các đợt ghi dồn vào JobRepository.

Giới hạn executor/task concurrency, số partition **đang chạy** và connection pool phải được đo cùng CPU/IO của database. **Grid size** không đồng nghĩa với số worker thực tế; điều quan trọng là lượng transaction đồng thời và tần suất cập nhật metadata.

### 10.4. Lỗi optimistic locking

JobExecution và StepExecution có **version** để phát hiện việc cập nhật state lỗi thời. Optimistic lock exception nghĩa là bản ghi đã bị tiến trình/luồng khác thay đổi trước khi một update dùng version cũ được ghi. Nó không đồng nghĩa một session DB đang giữ pessimistic lock gây treo.

Trong ứng dụng tự viết listener, cập nhật metadata hoặc dùng một stateful component không thread-safe giữa nhiều thread, optimistic conflict có thể xuất hiện. Hãy điều tra owner cập nhật và cách dùng API Spring Batch, thay vì tắt kiểm tra version hoặc ép cập nhật SQL trực tiếp.

### 10.5. Pool exhaustion hoặc lock ở hệ thống khác

Nếu HikariCP/JDBC pool không còn connection, JobRepository có thể chờ lấy connection và biểu hiện như "metadata đứng yên". Một lỗi AMQP broker, network hoặc database nghiệp vụ cũng có thể khiến worker không tiến triển. Chẩn đoán cần dùng metric **active/idle/pending connection** và lỗi cụ thể để tách các nguyên nhân.

## 11. Cách giảm tác động ngay trong sự cố

Ưu tiên hành động theo thứ tự ít rủi ro:

1. **Đóng bớt nguồn việc mới:** tạm dừng scheduler/trigger của job bị ảnh hưởng, chặn retry liên tục và giảm concurrency tạo thêm transaction chờ. Ghi rõ thời điểm và trạng thái trước khi thay đổi.
2. **Giữ nguyên công việc đã commit:** không xóa execution, không purge queue, không sửa trực tiếp các bảng BATCH_*.
3. **Xác minh blocker:** tìm session/transaction, loại khóa, object, statement và owner; phân biệt transaction bình thường với transaction treo.
4. **Trao đổi với DBA và owner:** nếu blocker có khả năng tự commit trong thời gian chấp nhận được, theo dõi theo deadline đã thống nhất. Nếu cần can thiệp, người có thẩm quyền phải đánh giá transaction rollback, ảnh hưởng tới ứng dụng khác và khả năng tạo lại trạng thái đúng.
5. **Ổn định kết nối:** khắc phục DB/broker/network hoặc pool ở tầng phù hợp. Tránh restart đồng loạt nhiều worker khi broker và database vừa hồi phục vì có thể gây thác lũ reconnect/retry.
6. **Xác minh lock đã hết:** đo lại blocked session và metrics; chạy một thao tác đọc metadata/canary phù hợp trước khi mở rộng tải.

**Không sử dụng mặc định các lệnh terminate/kill backend** để "mở khóa cho nhanh". Kết thúc session có thể rollback transaction lớn, bỏ dở tác vụ kinh doanh hoặc kích hoạt retry trùng. Một số session đang chặn thuộc ứng dụng khác cùng database; quyết định cần theo quy trình incident với DBA.

### Vì sao không nên đổi isolation ngay lúc cháy?

Spring Batch có cơ chế thiết lập **isolation level cho các thao tác tạo JobInstance/JobExecution**. Việc giảm isolation có thể thay đổi hành vi khi nhiều launcher tạo cùng JobInstance. Điều chỉnh này là thay đổi về **tính nhất quán**, phải đánh giá với DB vendor, schema và concurrency, sau đó thử cả race condition trước khi triển khai. Không thay isolation, tắt locking hay bỏ transaction như một biện pháp chữa cháy khi chưa chứng minh được nguyên nhân.

## 12. Quyết định stop và restart sau khi metadata thông suốt

Sau sự cố, xác định **trạng thái persisted** của từng execution, tiến trình thực tế và dữ liệu đã ghi:

| Trạng thái/hoàn cảnh | Hướng xử lý |
|---|---|
| Job vẫn chạy, metadata tiếp tục cập nhật, không còn blocker | Tiếp tục theo dõi và đối soát sau hoàn tất; tránh khởi chạy trùng |
| Job ở FAILED hoặc STOPPED, được cấu hình restartable | Xác minh checkpoint, resource đã phục hồi rồi restart **JobInstance** theo API/cơ chế Spring Batch |
| Job đã COMPLETED | Không chạy lại cùng dữ liệu một cách tùy tiện; nếu muốn reprocess phải có quy trình riêng |
| Job vẫn STARTED nhưng process đã chết | Đánh giá trạng thái stale/in-flight và quy trình recovery được hệ thống hỗ trợ; **không** tự gán FAILED trong SQL |
| Job ở STOPPING lâu | Kiểm tra worker/transaction còn sống, cơ chế graceful stop, DB/broker timeout; stop request có thể chưa hoàn tất |
| Job ở UNKNOWN hoặc state không nhất quán | Dừng thao tác tự động, điều tra trạng thái commit và có kế hoạch phục hồi riêng |
| Manager chết nhưng worker/broker còn việc | Đối chiếu worker in-flight, ack/reply, partition state trước khi kích hoạt manager khác |

**Điểm phân biệt API:** yêu cầu stop thường mang tính **graceful** và không bảo đảm job dừng tức thì, đặc biệt khi đang chờ DB lock hoặc I/O. Tùy Spring Batch version và cơ chế vận hành có thể dùng JobOperator/JobExplorer và công cụ quản trị đã tích hợp. Đừng mặc định crash tự động chuyển execution sang FAILED hoặc có thể restart ngay.

Khi restart, cố gắng giữ **cùng identifying JobParameters** để Spring Batch tiếp tục đúng JobInstance. Không dùng RunIdIncrementer hoặc timestamp mới một cách vô thức để "lách" lỗi JobExecutionAlreadyRunning/JobInstanceAlreadyComplete.

### Đối soát sau phục hồi

Ít nhất kiểm tra:

- Số bản ghi đầu vào đủ điều kiện, số item filter/skip hợp lệ, số bản ghi đầu ra đã commit.
- Khóa nghiệp vụ duy nhất, tổng tiền/checksum nếu có; so sánh với baseline hoặc nguồn sự thật.
- Các side effect bên ngoài transaction DB (gửi API, xuất file, publish message) có idempotency hoặc đối soát riêng.
- StepExecution commitCount, rollbackCount, writeCount và ExecutionContext checkpoint tương thích với reader/writer.
- Không còn partition mất tích, job stuck, message unacked bất thường hoặc retry tăng không kiểm soát.

**Một job báo COMPLETED chưa đủ chứng minh dữ liệu chính xác** nếu logic writer đã bị gọi lại sau rollback, mất reply hoặc restart không đúng checkpoint.

## 13. Phòng ngừa lock contention khi mở rộng workload

| Vùng cải tiến | Việc nên làm | Cần kiểm chứng |
|---|---|---|
| Scheduler/launch | Đảm bảo quy tắc **một lần launch cho một JobInstance**; phối hợp nhiều replica | Race test khi hai launcher tạo cùng job/params |
| Chunk và transaction | Rút ngắn transaction, tránh I/O ngoài kéo dài trong transaction, chọn commit interval theo benchmark | p95 transaction duration, rollback cost, counts |
| Partitioning | Giới hạn số worker/partition đang chạy; không scale chỉ theo gridSize | Metadata write rate và JDBC pending khi tăng concurrency |
| Connection pool | Tính tổng connection của các instance, dự phòng JobRepository và workload khác | Pool acquisition latency, DB max connections, lock wait |
| Database schema | Dùng schema/index chính thức cho đúng Spring Batch version và vendor; migration có lịch rõ | Query plan, lock DDL, rollback compatibility |
| Retry/backoff | Retry có phân loại lỗi, giới hạn attempts, backoff và jitter khi DB bận | Không có retry storm hoặc duplicate output |
| Telemetry | Gắn job/step ID với SQL session, trace và release/worker identity | Có thể truy từ alert tới blocker nhanh |
| Isolation | Giữ mức bảo vệ cần thiết; chỉ tune khi có bằng chứng và test concurrent launch | Cùng JobInstance không bị tạo/ghi sai |

### Ví dụ: khống chế nguồn áp lực theo tài nguyên

Giả sử hệ thống có **2 manager**, **12 worker replicas** và mỗi worker có JDBC pool tối đa **10 connection**. Nếu mọi pool có thể mở tối đa cùng lúc, chỉ riêng worker đã có **120 connection tiềm năng**. Còn phải cộng connection của manager, JobRepository, health check và các ứng dụng cùng DB. Tổng này có thể vượt quota hoặc làm DB quá tải dù mỗi worker riêng lẻ đều thấy pool "đủ".

Một cấu hình executor có queue lớn có thể nhận hàng trăm task chờ và tạo burst ghi metadata sau khi DB hồi phục. Vì vậy cần cân bằng **worker concurrency, queue capacity, prefetch, chunk size và connection pool** với throughput bền vững của database. Nếu cần scale xa hơn, hãy xem cách giảm contention dữ liệu, tách job theo thời điểm hoặc nâng năng lực hạ tầng thay vì chỉ tăng số replica.

## 14. Giám sát và ngưỡng cảnh báo

Ngưỡng phải dựa trên baseline của từng hệ thống; các giá trị ở đây là **ví dụ về cách đặt chính sách**, không phải SLO mặc định của Spring Batch.

| Chỉ số | Cách sử dụng |
|---|---|
| Số session bị chặn và lock wait duration | Phát hiện khi số blocked session tăng hoặc chờ lâu bất thường |
| Transaction age và idle-in-transaction | Phát hiện transaction giữ khóa lâu, cần gắn owner |
| Deadlocks/lock timeouts mỗi khoảng thời gian | Nhận diện thay đổi bất thường sau deploy/scale |
| JDBC active/pending/acquisition time | Phân biệt thiếu connection với database locking |
| Thời gian không cập nhật StepExecution | Phát hiện execution có nguy cơ stuck; cần đối chiếu worker |
| Số JobExecution/StepExecution ở STARTED lâu | Phát hiện job kéo dài hơn dự kiến, không đồng nghĩa có lock |
| Commit/rollback/retry rate, chunk p95/p99 | Nhận diện contention làm chậm tiến độ |
| Broker in-flight, unacked, queue depth | Kiểm tra manager/worker đang chờ message thay vì DB |
| CPU/IO của metadata DB | Phân biệt nghẽn tài nguyên tổng thể với một blocker cụ thể |

Ví dụ cảnh báo: **lock wait vượt ngưỡng SLO trong vài phút**, kèm hơn một StepExecution không tiến triển và JDBC pending tăng. Khi dùng composite alert như vậy, dashboard phải cho phép xem lại nguyên nhân riêng từng chiều. Không thiết lập auto-restart hoặc auto-kill session chỉ dựa trên một alert.

## 15. Diễn tập sự cố trên staging

**Tình huống:** Một hệ thống import 6 triệu bản ghi chạy remote partitioning với 16 partition, 8 worker đồng thời và hai replica manager. Cùng lúc, scheduler gửi hai yêu cầu launch có cùng identifying JobParameters, trong khi có một transaction database giữ khóa lâu tại thời điểm cập nhật metadata.

Hãy tổ chức diễn tập trong **môi trường test cô lập**, với dữ liệu có thể đối soát:

1. Ghi baseline một lần chạy bình thường: thời gian, read/write/commit/rollback count, CPU, DB lock wait và số connection.
2. Tạo tình huống tranh chấp **có kiểm soát** bằng transaction test đối với dữ liệu test hoặc mô phỏng concurrent launch; đặt timeout và cơ chế tự giải phóng, tuyệt đối không khóa bảng dùng chung production.
3. Quan sát log Java/SQLSTATE, pg_stat_activity hoặc Performance Schema tương ứng, JDBC pool pending và trạng thái StepExecution.
4. Dùng runbook phân biệt: database lock wait, optimistic version conflict, job launch trùng và connection pool exhaustion.
5. Dừng launch bổ sung, xử lý blocker bằng cách kết thúc **transaction test do nhóm sở hữu**, rồi xác minh các câu lệnh metadata hoạt động lại.
6. Xác định execution FAILED/STOPPED hoặc còn STARTED, thực hiện restart chỉ khi thỏa điều kiện và bảo đảm không có worker cũ đang ghi dữ liệu.
7. Đối soát kết quả bằng khóa nghiệp vụ duy nhất, số lượng bản ghi và tổng giá trị; chứng minh không mất/trùng dữ liệu.
8. Lặp lại với số worker thấp hơn hoặc lịch launch được phối hợp; so sánh lock wait, throughput, số rollback và thời gian hoàn tất.

### Câu hỏi tự kiểm tra

- Một log báo **OptimisticLockingFailureException** có đủ chứng minh bảng BATCH_STEP_EXECUTION đang bị row lock không? Vì sao?
- Trong PostgreSQL, một blocker ở trạng thái **idle in transaction** với transaction age lớn cần được xác minh những gì trước khi terminate?
- Vì sao hai launcher không nên dùng JobParameters mới để "vượt" lỗi concurrent execution?
- MySQL **metadata_locks** và **data_locks** trả lời hai loại câu hỏi khác nhau nào?
- Nếu manager chết nhưng worker có thể đã commit, hành động restart ngay có thể gây vấn đề gì?
- Khi tăng số partition từ 8 lên 32 mà JDBC pending và lock wait cùng tăng, cần thay đổi/thử nghiệm biến nào trước khi nâng max connections?

## 16. Checklist dùng tại thời điểm incident

- [ ] Ghi incident ID, environment, job name, identifying parameters, execution ID, release và mốc bắt đầu lỗi.
- [ ] Phân biệt DB row/table lock, DB deadlock, optimistic version, pool exhaustion, MySQL MDL và broker wait.
- [ ] Thu thập blocked/blocker PID/thread, transaction age, SQL, lock type, object và owner từ công cụ database phù hợp.
- [ ] Xác định BATCH_* hay bảng nghiệp vụ đang bị tác động, đồng thời kiểm tra mọi ứng dụng dùng chung DB.
- [ ] Giảm/tạm dừng launcher và retry tạo thêm tải, nhưng giữ nguyên job metadata và dữ liệu đã commit.
- [ ] Không trực tiếp UPDATE/DELETE BATCH_*; không kill session, bỏ transaction hoặc thay isolation khi chưa được đánh giá và phê duyệt.
- [ ] Xác minh JobRepository, datasource/broker, process manager/worker và in-flight message sau khi lock hết.
- [ ] Restart đúng JobInstance khi status, checkpoint và chính sách xử lý cho phép; tránh tạo bản sao bằng JobParameters mới.
- [ ] Đối soát số record, khóa nghiệp vụ, side effect, commit/rollback và tất cả partition còn tồn đọng.
- [ ] Mở lại tải có kiểm soát, theo dõi lock wait, JDBC pending, throughput, rollback và queue/retry.
- [ ] Ghi RCA gồm nguyên nhân, câu SQL/transaction thực tế, bước phục hồi, ngưỡng cảnh báo và thay đổi phòng ngừa.

## 17. Ghi nhớ

**Runbook khi metadata bị lock** phải bắt đầu bằng **chẩn đoán đúng loại nghẽn**. Database lock wait, MySQL metadata lock, optimistic version conflict và JDBC pool timeout có cách xử lý khác nhau. Trong Spring Batch scaling, JobRepository được nhiều manager/worker truy cập nên việc tăng concurrency cần đi cùng đo lock wait, transaction duration và giới hạn connection. Giữ nguyên metadata đã commit, tìm blocker thật, giảm tải đầu vào, phối hợp DBA khi cần, sau đó **restart đúng JobInstance và đối soát dữ liệu** là chuỗi hành động cốt lõi để khôi phục batch job an toàn.
