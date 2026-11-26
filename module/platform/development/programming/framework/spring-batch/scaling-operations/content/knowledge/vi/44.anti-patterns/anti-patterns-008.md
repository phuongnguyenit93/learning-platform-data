# Anti-pattern: Scale worker vượt giới hạn database

## 1. Bối cảnh và vấn đề

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, mục tiêu của việc mở rộng Spring Batch là xử lý workload dữ liệu lớn bằng **multi-threaded step**, **parallel steps**, **partitioning** hoặc worker phân tán mà vẫn giữ được thread safety, khả năng retry/restart và tính nhất quán dữ liệu. Một sai lầm phổ biến là **cứ tăng số worker khi job chạy chậm**, trong khi database vốn đã là nút thắt.

Ví dụ, job nhập 20 triệu giao dịch được chia thành partition và chạy trên các pod worker. Ban đầu có 4 worker, throughput tăng đáng kể so với một worker. Khi đội vận hành tăng từ 4 lên 12 worker để “xong nhanh gấp ba”, job lại chậm hơn: thời gian chờ connection tăng, transaction kéo dài, deadlock xuất hiện và nhiều chunk rollback. Một số partition bị retry nhiều lần, tạo thêm truy vấn lên database đang quá tải.

Đây là **anti-pattern “scale worker vượt giới hạn database”**: tăng mức song song ở tầng Batch mà không kiểm soát giới hạn tài nguyên, số kết nối, lock contention và khả năng phục vụ thực tế của database.

Các biểu hiện dễ thấy:

- Số worker/pod tăng nhưng **tổng records/second không tăng** hoặc giảm.
- `HikariPool - Connection is not available, request timed out`, `too many connections`, connection acquisition timeout hoặc pool pending threads tăng.
- DB CPU, IOPS, disk latency, WAL/redo log, checkpoint, lock waits hoặc replication lag tăng mạnh.
- Chunk có thời gian xử lý dài hơn, rollback/retry tăng, job chạy lâu và dễ vượt SLA.
- JobRepository cũng bị quá tải; việc cập nhật `StepExecution` và `ExecutionContext` bắt đầu chậm, khiến restart và quan sát khó khăn.

**Điểm cốt lõi:** số worker tối ưu phụ thuộc vào **nút thắt hiện hành**, không phụ thuộc vào số CPU worker có thể cấp phát. Tăng worker là một thay đổi tải xuống toàn bộ hệ thống, đặc biệt là database dùng chung.

## 2. Cơ chế khiến thêm worker làm hệ thống chậm đi

Một mô hình đơn giản:

```text
                      Manager / JobRepository
                              |
                 phân phát partition/chunk
                              |
              +---------------+---------------+
              |               |               |
           Worker A        Worker B        Worker C ... Worker N
              |               |               |
          JDBC pool       JDBC pool       JDBC pool
              \               |              /
               \              |             /
                 Database (giới hạn chung)
                 - connection slots
                 - CPU / query execution
                 - I/O / WAL / redo log
                 - locks / transaction log
                 - memory / buffer cache
```

Thêm worker đồng thời có thể gây ra các hiệu ứng cộng dồn:

1. **Tranh chấp connection:** mỗi JVM/pod thường có một pool riêng. Tổng giới hạn kết nối tiềm năng tăng gần theo số replica. Khi DB hết slot, những connection mới không thể được tạo; khi pool của worker hết connection trống, các task phải xếp hàng ngay trong ứng dụng.
2. **Tranh chấp CPU, bộ nhớ và I/O:** nhiều truy vấn cạnh tranh cùng CPU, buffer cache, băng thông đĩa; quá nhiều truy vấn đồng thời có thể làm latency tăng dù tổng số truy vấn hoàn thành mỗi giây không tăng.
3. **Tranh chấp lock:** nhiều writer cùng cập nhật hàng hoặc index/hot key tạo lock wait, deadlock và transaction rollback. Transaction giữ lock càng lâu thì contention càng nặng.
4. **Quá tải log và storage:** nhiều commit, index update và ghi WAL/redo log có thể vượt khả năng fsync/IOPS; transaction latency tăng.
5. **Retry storm:** khi request timeout hoặc deadlock, nhiều chunk retry đồng thời, lặp lại cùng tải; retry không có backoff có thể làm DB càng nghẽn.
6. **JobRepository thành điểm nóng:** mỗi step, partition, commit và lần restart có thể làm phát sinh metadata update, sử dụng cùng DB hoặc một DB riêng. Khi database metadata quá tải, quản lý tiến độ cũng chậm theo.

Thông lượng thường tăng khi có thêm song song đến một ngưỡng, sau đó **bão hòa hoặc giảm** do contention. Đây là lý do tăng CPU/memory của worker không tự động cải thiện năng lực database.

## 3. Phân biệt các giới hạn: connection, throughput và lock

“Database đã hết khả năng” không chỉ có một ý nghĩa. Cần đo riêng:

| Giới hạn | Tín hiệu | Vì sao thêm worker nguy hiểm |
| --- | --- | --- |
| **Số connection/sessions** | Sessions gần trần DB; lỗi kết nối, pool acquire timeout | Worker/pool mới chiếm thêm slot; việc quản trị, monitoring và dịch vụ khác cũng thiếu connection |
| **CPU** | DB CPU gần bão hòa; query latency và run queue tăng | Quá nhiều query cạnh tranh CPU, tăng context switch |
| **Disk / WAL / redo** | IOPS, disk await, log flush latency, replication lag cao | Thêm transaction gây nhiều ghi hơn năng lực storage |
| **Lock / deadlock** | Lock waits, deadlock count, transaction age tăng | Nhiều worker cùng cập nhật hàng/khóa nóng, kéo dài thời gian giữ lock |
| **Memory / buffer cache** | Cache hit giảm, temp file/sort spill tăng, memory pressure | Concurrent queries chiếm thêm working memory, cache bị đẩy ra |
| **Network / DB proxy** | Network saturation, DB proxy queue, timeout | Mở thêm pool khiến queue hoặc throughput giao tiếp bị giới hạn |
| **Metadata Spring Batch** | `BATCH_STEP_EXECUTION`, `BATCH_STEP_EXECUTION_CONTEXT` update chậm | Quá nhiều partition/chunk tạo áp lực lên `JobRepository` |

Không nên coi `maximumPoolSize` là số kết nối đang mở tại mọi thời điểm: nó là **trần số connection trong một pool**. Số connection thực tế còn phụ thuộc `minimumIdle`, đặc tính pool và tải. Khi thiết kế giới hạn an toàn, vẫn phải tính theo **mức tối đa có thể đạt**.

## 4. Anti-pattern trong các mô hình mở rộng Spring Batch

| Mô hình | Cách mắc lỗi | Hướng sửa |
| --- | --- | --- |
| **Multi-threaded step** | Nâng `TaskExecutor` từ 4 lên 32 thread nhưng `DataSource`/DB phục vụ tối đa vài query đồng thời | Đo thời gian chờ pool, giới hạn thread, xem reader/writer có thread-safe |
| **Parallel steps** | Các step chạy cùng lúc đều đọc và ghi một bảng lớn, nhân tải DB | Lập lịch step theo ngân sách chung, tách công đoạn có tranh chấp |
| **Local partitioning** | Tăng `gridSize`/executor vượt khả năng database | Giới hạn concurrency thực tế của executor, chọn kích thước partition và chunk phù hợp |
| **Remote partitioning** | Autoscale worker pod theo queue depth nhưng mỗi pod mở JDBC pool lớn | Ràng buộc `maxReplicas`, consumer concurrency và JDBC pool theo budget tổng |
| **Remote chunking** | Tăng consumer để giảm backlog nhưng DB write trở thành nút thắt | Giới hạn in-flight chunks, prefetch/concurrency, backpressure và retry với backoff |

**Lưu ý:** `gridSize` trong partitioning định hướng số phần chia việc, không bảo đảm chỉ có đúng `gridSize` kết nối hoặc transaction. Concurrency thực tế còn phụ thuộc executor, số replica, worker implementation, connection pool và các step khác. Một worker thread đôi khi cần nhiều connection (DB nghiệp vụ, `JobRepository`, audit hoặc external service); không mặc định “1 thread = 1 connection”.

Nếu nhiều job cùng chạy trên một database, phải tính **tổng tải của tất cả job và ứng dụng**, thay vì tối ưu từng job độc lập.

## 5. Tính ngân sách connection trước khi scale

Giả sử:

- `C_db`: giới hạn connection của database hoặc database proxy.
- `C_reserved`: phần dự phòng cho DBA, failover, monitoring và hệ thống.
- `C_other`: lượng connection tối đa cần giữ cho dịch vụ khác.
- `C_manager`: connection cần cho manager/JobRepository, listener và thành phần điều phối.
- `P_worker`: `maximumPoolSize` mỗi worker replica (cộng các pool khác nếu worker có nhiều `DataSource`).
- `W`: số replica worker đồng thời.

Ngân sách sơ bộ cho các worker:

\[
C_{\text{batch}} = C_{\text{db}} - C_{\text{reserved}} - C_{\text{other}} - C_{\text{manager}}
\]

Điều kiện tối thiểu về số connection:

\[
W \times P_{\text{worker}} \le C_{\text{batch}}
\qquad\Longrightarrow\qquad
W_{\max} \le \left\lfloor \frac{C_{\text{batch}}}{P_{\text{worker}}} \right\rfloor
\]

Với nhiều nhóm worker hoặc nhiều pool:

\[
\sum_{i=1}^{n} W_i\,P_i + C_{\text{manager}}
+ C_{\text{other}} + C_{\text{reserved}} \le C_{\text{db}}
\]

Đây là **điều kiện bảo vệ connection**, **không phải công thức dự đoán throughput tối ưu**. CPU, I/O, lock, băng thông và giới hạn pool DB thực tế có thể khiến số worker tối ưu thấp hơn rất nhiều. Với nhiều node DB/shard, tính riêng theo endpoint/nút chịu tải, không cộng khả năng của toàn cluster một cách máy móc.

### Ví dụ tính toán

Giả sử một database có các giả định vận hành sau:

| Thành phần | Số connection |
| --- | ---: |
| DB cho phép (`C_db`) | 180 |
| Dự phòng vận hành và headroom (`C_reserved`) | 20 |
| Dịch vụ trực tuyến khác (`C_other`) | 60 |
| Manager/metadata (`C_manager`) | 10 |
| **Còn lại cho worker** | **90** |

Mỗi pod worker cấu hình `maximumPoolSize=12`:

- 10 worker có thể yêu cầu tối đa **120** connection, vượt ngân sách worker 90.
- Trần sơ bộ là `floor(90 / 12) = 7` worker, nhưng 7 worker chỉ còn **6 slot** trong ngân sách worker.
- Bắt đầu kiểm thử từ **4–6 worker** sẽ có khoảng dự phòng tốt hơn; ví dụ 6 worker dùng tối đa 72 connection theo giả định này.

Điều kiện trên chỉ xét một pool worker. Nếu mỗi worker có **hai pool** (business DB và Batch metadata DB), cần tính theo đúng **database đích của từng pool**. Nếu cùng trỏ tới một endpoint, cộng cả hai. Nếu khác endpoint, phân bổ ngân sách riêng.

**Sai lầm dễ mắc:** giảm `maximumPoolSize` ở worker xuống rất thấp để ép tổng slot rồi tăng worker không giới hạn. Điều này có thể tạo hàng đợi chờ pool ngay trong mỗi pod, tăng timeout mà không cải thiện throughput. Cần điều chỉnh đồng thời số worker, concurrency mỗi worker, pool size và thông lượng database.

## 6. Dấu hiệu xác thực: thêm worker nhưng throughput giảm

Đừng chỉ nhìn “CPU worker còn trống” hoặc “queue backlog còn lớn”. Cần theo dõi throughput và latency end-to-end cùng tải trên DB.

Bảng sau là **số liệu minh họa**, không phải kết quả benchmark thật:

| Worker đang chạy | Throughput records/s | p95 thời gian chunk | Pool acquire p95 | DB CPU | Rollback/phút |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 1.100 | 0,8 s | 5 ms | 35% | 0 |
| 4 | 2.000 | 1,0 s | 8 ms | 55% | 0 |
| 6 | 2.550 | 1,3 s | 20 ms | 72% | 1 |
| 8 | 2.650 | 2,6 s | 160 ms | 91% | 4 |
| 12 | 2.200 | 5,5 s | 1.800 ms | 98% | 27 |

Tại 8 worker, tăng lên 12 không giúp job hoàn thành sớm; throughput giảm trong khi thời gian chờ và rollback tăng. Điểm vận hành hợp lý có thể là 6–8 worker, nhưng phải đánh giá thêm SLA và headroom cho tải trực tuyến.

### Các metric nên đặt cạnh nhau

**Ở Spring Batch:**
- `JobExecution`/`StepExecution` status, duration, read/write/commit/rollback/skip count.
- Records/s và commits/s theo **cửa sổ thời gian**, không chỉ tổng đếm.
- Số partition đang chạy, chờ, hoàn tất, thất bại; chênh lệch kích thước partition.
- Retry count, chunk latency p50/p95/p99, lỗi JDBC, timeout và deadlock.

**Ở ứng dụng/connection pool:**
- Hikari active, idle, pending, total connections; thời gian chờ lấy connection.
- Số worker pod, thread pool active/queue/rejected; lượng message/chunk in flight.
- JVM heap, GC pause, CPU; thread dump khi các worker cùng kẹt.

**Ở database:**
- Active sessions, sessions waiting, max sessions; CPU, I/O throughput/latency.
- Query latency p95/p99, transaction age, lock waits/deadlocks.
- WAL/redo generation, log flush, replication lag, disk space và connection authentication failures.
- Tải của các dịch vụ khác (để nhận biết batch gây ảnh hưởng dây chuyền).

Metrics tên cụ thể phụ thuộc Micrometer, Spring Boot Actuator, HikariCP, loại DB và cấu hình monitoring. **Phân biệt pool acquire timeout với lỗi DB hết slot:** pool timeout có thể xảy ra dù DB còn connection, do các request trong cùng pod giữ connection quá lâu hoặc `maximumPoolSize` của pool quá nhỏ.

## 7. Truy vấn quan sát trên PostgreSQL

Ví dụ sử dụng PostgreSQL; với MySQL, SQL Server hoặc Oracle phải dùng view/command tương ứng. Các truy vấn sau **chỉ đọc** và nên chạy trên môi trường có quyền quan sát phù hợp.

### 7.1. Xem trần và số session

```sql
SHOW max_connections;

SELECT
    application_name,
    state,
    wait_event_type,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state, wait_event_type
ORDER BY sessions DESC;
```

Để phân biệt manager và worker, cấu hình `application_name` hoặc nhãn kết nối phù hợp; tránh suy đoán toàn bộ session là do một job duy nhất.

### 7.2. Tìm query chờ và transaction kéo dài

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    NOW() - xact_start AS transaction_age,
    NOW() - query_start AS query_age,
    LEFT(query, 180) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY xact_start NULLS LAST;
```

Cần xác định session đang chờ lock, I/O hay đang chạy query đắt đỏ; đừng chỉ đọc tổng số connection. Truy vấn chứa SQL nghiệp vụ có thể mang thông tin nhạy cảm nên giới hạn quyền và thời gian lưu log.

### 7.3. Đối chiếu metadata Spring Batch

```sql
SELECT
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = ?
ORDER BY STEP_EXECUTION_ID;
```

Dấu `?` là placeholder cho prepared statement. So sánh các partition trong cùng `JOB_EXECUTION_ID`. Nếu tất cả đều rollback và mất thời gian commit, cần kiểm tra DB/pool dùng chung. Nếu chỉ một partition kẹt trong khi các partition khác chạy tốt, có thể do **data skew**, một nhóm khóa nóng, dữ liệu lỗi hoặc truy vấn riêng của partition đó.

Giá trị `LAST_UPDATED`, nếu truy vấn thêm, **không phải heartbeat liên tục**; nó phản ánh lúc Batch metadata được ghi. Kết luận worker chết cần xác minh thêm runtime, log và metric tiến triển.

## 8. Cấu hình giới hạn concurrency trên worker

Cấu hình cần được xem ở **ba tầng**: số worker replica, số task đồng thời mỗi worker và số connection mỗi pool.

### 8.1. Ví dụ cấu hình pool cho Spring Boot

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 8
      minimum-idle: 2
      connection-timeout: 30000

# Các giá trị trên chỉ minh họa, phải điều chỉnh bằng đo tải.
```

`maximum-pool-size` là trần của một `HikariDataSource`, không phải quota chung cho cả cluster. Ví dụ 8 pod cùng pool tối đa 8 có thể cùng tạo **64 connection** đến database nếu cùng một `DataSource`. Nếu có thêm pool riêng cho `JobRepository` hoặc audit DB, phải cộng nhu cầu của chúng.

`connection-timeout` là thời gian chờ lấy connection từ pool. Tăng timeout có thể làm lỗi xuất hiện muộn hơn nhưng **không tăng năng lực DB**.

### 8.2. Giới hạn task executor trong local partitioning

```java
@Configuration
class BatchConcurrencyConfig {

    @Bean
    ThreadPoolTaskExecutor batchPartitionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-partition-");
        executor.initialize();
        return executor;
    }
}
```

Khi gắn executor này vào partition step, tối đa khoảng 4 task executor thực thi cùng lúc trong pool này; các task khác có thể xếp hàng trong giới hạn queue. Nếu tổng số task có thể vượt cả capacity, cần xử lý chính sách rejected task và số partition được phát. Đừng ngầm hiểu `gridSize=16` thì database sẽ chịu tải tương đương đúng 16 connection.

Với **multi-threaded chunk step**, cũng cần giới hạn `TaskExecutor` và xác minh `ItemReader`/`ItemWriter` thread-safe. Tùy phiên bản Spring Batch và cách khai báo, cơ chế throttling/mức tối đa concurrency của step thay đổi; ưu tiên executor có capacity rõ ràng và kiểm thử hành vi runtime.

### 8.3. Giới hạn remote worker

Với Kubernetes, có thể đặt trần số replica và consumer concurrency để tổng số transaction không vượt budget, ví dụ:

```yaml
# Một phần cấu hình ứng dụng (minh họa), không phải API Spring Batch mặc định.
batch:
  worker:
    consumer-concurrency: 2
    max-inflight-chunks: 4
```

Các key trên **phải được ứng dụng/broker listener thực sự hỗ trợ**. Chúng không tự động giới hạn bất cứ thứ gì nếu chỉ thêm vào `application.yml`.

Nếu sử dụng HPA/KEDA dựa vào queue depth, cần trần `maxReplicas` và chính sách scaling hợp lý; backlog có thể tăng vì DB chậm, nên scaling chỉ theo backlog sẽ làm quá tải nặng thêm. Có thể phối hợp queue lag với CPU/DB pool latency hoặc một chỉ số capacity phù hợp, tùy hệ thống.

## 9. Backpressure và retry: không biến lỗi tải thành bão truy vấn

**Backpressure** là cơ chế hạn chế lượng công việc đang xử lý khi downstream (database) không kịp đáp ứng. Với batch phân tán, có thể triển khai tại nhiều điểm:

- Manager giới hạn số partition hoạt động đồng thời; phần còn lại được chờ xử lý.
- Consumer giới hạn số message in flight/prefetch, mức concurrency và tốc độ lấy batch.
- Executor dùng queue có giới hạn, có cơ chế từ chối hoặc hoãn phát task khi đầy.
- Reader/writer giới hạn số request DB đồng thời; dùng bulk operation nếu giao dịch và DB cho phép.
- Autoscaler dùng cả ngân sách DB và mức độ quá tải, thay vì chỉ nhìn queue backlog.

**Retry đúng mục đích:** với deadlock/timeout tạm thời, có thể retry giới hạn số lần, backoff tăng dần và jitter để tránh nhiều worker thử lại cùng lúc. Nhưng với lỗi hệ thống thiếu connection do quá tải kéo dài, retry liên tục chỉ tạo thêm áp lực. Sau ngưỡng lỗi, cần giảm concurrency hoặc tạm hoãn đọc thêm dữ liệu.

Ví dụ logic chính sách (pseudocode, không phải API có sẵn):

```text
when transientDatabaseFailure:
    if retryCount < maxRetries and dbIsHealthyEnough:
        wait exponentialBackoffWithJitter(retryCount)
        retry current chunk
    else:
        stop accepting new work
        fail/park current unit for controlled recovery
```

Không retry lỗi dữ liệu không thể hồi phục (vi phạm schema/constraint cố định, dữ liệu sai) như thể đó là lỗi DB tạm thời. Việc retry chunk sau rollback phải dựa vào tính transaction-safe và idempotency của writer; API ngoài DB có thể đã nhận request dù transaction trong DB rollback.

## 10. Chọn chunk size và transaction boundaries

Chunk size ảnh hưởng trực tiếp đến tần suất commit, thời gian giữ lock, số lần ghi metadata và độ lớn của công việc phải làm lại sau failure.

| Chunk | Lợi ích tiềm năng | Rủi ro khi DB là nút thắt |
| --- | --- | --- |
| **Rất nhỏ** | Transaction ngắn, rollback ít record | Nhiều round-trip/commit/metadata update; overhead cao |
| **Vừa phải** | Cân bằng commit frequency và batch writing | Cần đo theo loại SQL và workload |
| **Rất lớn** | Giảm overhead commit trên mỗi record trong một số trường hợp | Lock giữ lâu, memory tăng, transaction log lớn, rollback tốn kém |

Không có giá trị chunk size “tốt nhất” cho mọi database. Thử nghiệm các giá trị như 100, 500, 1.000 trong staging là điểm bắt đầu, **không phải khuyến nghị mặc định**. Đo throughput, p95 commit latency, memory, lock và rollback.

Các cải tiến hữu ích trước khi thêm worker:

1. Dùng index phù hợp cho predicate của reader và lookup/upsert writer; xác minh bằng `EXPLAIN` và kế hoạch thực thi.
2. Đọc theo keyset/ID hoặc partition range có chỉ mục thay vì quét lặp lại cùng một bảng lớn.
3. Bật JDBC batching/bulk operations nơi thích hợp, giữ idempotency và kiểm soát transaction.
4. Tránh mỗi item phát sinh nhiều query kiểu N+1; cache dữ liệu tham chiếu khi hợp lý.
5. Giảm update lên cùng hot row/aggregate; phân chia partition theo khóa tránh contention.
6. Tách read replicas nếu mô hình đọc cho phép và chấp nhận được replication lag; writer vẫn phải tuân thủ năng lực primary.
7. Chỉ cân nhắc shard/replica/vertical scaling DB sau khi có số đo và biết chi phí consistency/migration.

Tăng `lock_timeout` hay `connectionTimeout` để che triệu chứng không giải quyết query plan xấu hoặc lock hot spot.

## 11. Benchmark để tìm điểm scale tối ưu

Benchmark nên được thiết kế như một phép thử có kiểm soát, không chỉ chạy một lần ở worker count lớn nhất.

### Điều kiện đo

- Dùng dataset và phân bố khóa đại diện production (bao gồm hot keys, bản ghi lớn, partition lệch).
- Giữ cố định query, index, schema, JVM/GC settings, chunk size, isolation và pool size ở mỗi lượt **trừ một biến đang thử**.
- Chạy trên tài nguyên DB có mức tải tương đương; nếu DB đang phục vụ ứng dụng khác, ghi nhận baseline.
- Chỉ so sánh sau warmup hợp lý, tránh ảnh hưởng cache và dữ liệu đầu vào giữa các lượt.
- Với rerun, dùng dữ liệu có thể reset hoặc đảm bảo thao tác idempotent để lần thứ hai không “nhanh hơn” chỉ vì đã xử lý trước.

### Dải thử nghiệm

Ví dụ chạy tuần tự với 1, 2, 4, 6, 8, 10 worker. Tại mỗi mức, ghi:

| Biến đo | Mục đích |
| --- | --- |
| Records/s, thời gian hoàn thành job | Biết scaling có thực sự đem lại lợi ích |
| DB CPU, disk latency, WAL/redo flush, pool pending | Xác định giới hạn nguồn lực |
| p95/p99 query/commit latency, deadlocks, timeout | Phát hiện contention trước khi lỗi lớn |
| Rollback/retry count, step failure rate | Đo cái giá của parallelism |
| Tải trực tuyến, DB headroom, replica lag | Tránh tối ưu batch gây hại hệ thống khác |
| Chi phí pod/DB cho một triệu bản ghi | Đánh giá hiệu quả kinh tế |

Có thể tính **speedup** và **parallel efficiency** để nhận biết lợi ích giảm dần:

\[
S(W)=\frac{T(1)}{T(W)}, \qquad E(W)=\frac{S(W)}{W}
\]

Trong đó `T(W)` là thời gian hoàn thành cùng workload với `W` worker. Nếu `T(8)` chỉ cải thiện 10% so với `T(6)`, nhưng DB latency tăng gấp đôi, mức 8 worker có thể không đạt mục tiêu vận hành.

Chọn số worker **cao nhất vẫn đáp ứng SLA, mức ổn định và headroom**, không nhất thiết là số worker mang throughput tuyệt đối cao nhất trong test đơn lẻ. Ghi kết quả và cấu hình đã đo để operator có thể lặp lại.

## 12. Tình huống thực tế: tăng pod làm Batch và API cùng chậm

**Bối cảnh:** một hệ thống nightly import đơn hàng dùng remote partitioning. Worker đọc dữ liệu từ DB nguồn và ghi vào DB nghiệp vụ cũng phục vụ REST API. Manager/worker dùng `JdbcJobRepository`. Mỗi worker có Hikari pool tối đa 12 kết nối.

**Triệu chứng:** tăng từ 4 lên 12 pod sau khi thấy queue backlog lớn. Sau 10 phút, import records/s giảm; API latency tăng; một số pod log lỗi `Connection is not available, request timed out`; bước Batch có `ROLLBACK_COUNT` tăng.

**Điều tra theo bằng chứng:**

1. So sánh số pod, connections của từng pool và tổng sessions trên DB trước/sau scaling.
2. Phát hiện số session đang chờ lock và p95 DB query tăng, cùng với cache miss và WAL flush latency.
3. Tìm một số partition ghi cùng hot order-group row; update contention tạo chuỗi lock waits.
4. Kiểm tra rollback/retry: các chunk timeout được thử lại đồng loạt, làm DB càng tải nặng.
5. Đối chiếu API latency tăng cùng khoảng thời gian; đây là tác động từ DB dùng chung, dù API không thay đổi code.

**Xử lý:**

- Hạ số worker về mức ổn định đã đo (ví dụ 4 hoặc 6), dừng phát thêm partition/chunk vượt budget.
- Giảm consumer concurrency hoặc in-flight chunks, giới hạn retry và backoff với jitter.
- Tối ưu query/index và sửa partition key để giảm write conflict; thử JDBC batching nếu phù hợp.
- Giữ trần worker/pool theo ngân sách connection và benchmark lại từng mức.
- Xác minh job restart đúng, không mất record hoặc tạo side effect trùng trước khi tăng tải lại.

**Bài học:** giảm số worker có thể làm **job hoàn thành sớm hơn** và bảo vệ các dịch vụ online khi DB bị bão hòa. Điều này không có nghĩa hệ thống luôn cần ít worker; cần chọn mức concurrency sau khi đo đúng nút thắt.

## 13. Runbook xử lý sự cố database quá tải do worker

Nếu production đang quá tải, ưu tiên khôi phục trạng thái ổn định và bảo toàn dữ liệu.

**Giai đoạn khoanh vùng**

1. Ghi `jobExecutionId`, `stepExecutionId`, tên partition, thời điểm tăng replica/concurrency và thông số pool hiện tại.
2. So sánh throughput, DB resource metrics, pool wait, lock wait và lỗi theo cùng khoảng thời gian.
3. Xác định DB nào bị ảnh hưởng (business DB, source DB, `JobRepository` hay nhiều DB); tránh gom mọi database thành một.
4. Kiểm tra tải ứng dụng khác và mức ưu tiên SLA; quan sát số connection thực và session đang chờ.

**Giai đoạn giảm tải**

1. Dừng tăng số replica tự động hoặc điều chỉnh trần scaling về mức đã được đánh giá an toàn.
2. Giảm task/consumer concurrency hoặc ngừng tiếp nhận batch mới theo cơ chế vận hành của hệ thống.
3. Với worker đang xử lý, ưu tiên stop có kiểm soát khi có thể; tránh kill hàng loạt làm nhiều chunk redelivery cùng lúc.
4. Hạn chế retry storm bằng backoff/circuit breaker hoặc delay queue theo kiến trúc; quan sát rollback/timeout giảm dần.
5. **Không sửa `BATCH_*` metadata bằng SQL**, không xóa queue và không ép status `COMPLETED` để dập cảnh báo.

**Giai đoạn phục hồi**

1. Chẩn đoán query/hot lock/IO/pool gây nghẽn; sửa nguyên nhân trước khi mở rộng lại.
2. Xác định chunk/partition đã commit và tác dụng phụ ngoài transaction; kiểm tra idempotency.
3. Restart job theo cơ chế Spring Batch khi điều kiện cho phép, kiểm soát worker cũ đã dừng để tránh cùng dải dữ liệu bị chạy song song.
4. Tăng tải từng mức, theo dõi throughput cùng pool wait và DB latency; dừng tăng khi lợi ích bão hòa.
5. Đối soát số bản ghi, kết quả nghiệp vụ và tác động lên ứng dụng khác; cập nhật ngưỡng cảnh báo, cấu hình autoscaler và tài liệu vận hành.

Nếu cần dừng khẩn cấp để bảo vệ DB dùng chung, operator phải cân nhắc rủi ro các transaction đang chạy: hủy pod cưỡng bức có thể gây rollback và redelivery, đặc biệt với remote chunking. Kế hoạch khôi phục cần xác định ack, retry, restart và output consistency.

## 14. Các lỗi suy luận thường gặp

| Kết luận sai | Vì sao sai | Hướng đánh giá đúng |
| --- | --- | --- |
| “Queue dài thì thêm worker.” | Queue cũng dài khi DB không xử lý kịp; tăng worker làm nghẽn hơn | Kiểm tra DB capacity, lag, pool wait và giới hạn inflight |
| “DB max_connections=500 nên có thể mở 500 worker.” | Mỗi worker có nhiều connection; tài nguyên DB còn bị giới hạn bởi CPU/I/O/lock | Tính pool total và benchmark |
| “Hikari pool mỗi pod 10 là ít.” | 30 pod có thể mở 300 connection; manager và service khác cũng dùng DB | Tính tổng theo endpoint và thời điểm peak |
| “DB CPU chưa 100% nên chưa nghẽn.” | I/O, lock, WAL, proxy hoặc connection có thể là nút thắt trước CPU | Phân tích wait events và query latency |
| “Tăng timeout sẽ hết lỗi.” | Chỉ kéo dài thời gian chờ; queue có thể càng đầy | Hạn chế concurrency và xử lý nguồn gây chậm |
| “Retry hết lỗi tạm thời.” | Retry không kiểm soát khuếch đại tải; lỗi cố định không tự hồi phục | Chia loại lỗi, giới hạn backoff và đặt ngưỡng dừng |
| “Chỉ giảm pool là xong.” | Pool quá nhỏ gây chờ nội bộ; tổng throughput có thể vẫn thấp | Điều chỉnh đồng bộ pool, worker, thread, chunk và query |
| “Bản ghi `COMPLETED` là đủ.” | Side effect ngoài DB có thể bị gửi lặp, data skew có thể che giấu lỗi | Đối soát dữ liệu đầu ra và idempotency |

## 15. Checklist trước khi scale worker

- [ ] Đã xác định **database nào** là nút thắt và pool nào đang sử dụng endpoint đó.
- [ ] Có số đo baseline của throughput, latency, CPU, I/O, lock wait, pool pending và retry.
- [ ] Đã tính tổng giới hạn connection tiềm năng của manager, worker replicas, các DataSource khác và dịch vụ online.
- [ ] Đã chừa headroom cho monitoring, admin, failover và workload bất thường.
- [ ] Đã đo concurrency của `TaskExecutor`, partition handler, consumer/broker và HPA/KEDA.
- [ ] Đã biết DB chịu tải tối đa theo **kết quả benchmark**, không suy ra chỉ từ `max_connections`.
- [ ] Đã kiểm tra thread safety, partition data skew, SQL plan, index và khóa nóng.
- [ ] Có bounded queue/backpressure và retry có giới hạn, backoff phù hợp.
- [ ] Có ngưỡng dừng scaling khi DB latency, lock waits hoặc pool wait vượt mức.
- [ ] Đã kiểm tra restart, tính nhất quán output, chống trùng và ảnh hưởng đến ứng dụng khác.
- [ ] Đã xác định rollback plan và quyền vận hành để giảm tải nhanh khi cần.

## 16. Bài tập tự kiểm tra

**Bài tập 1 — Ngân sách connection**

Một PostgreSQL instance cho tối đa 160 kết nối; cần dự phòng 20, dịch vụ online cần tối đa 70, manager cần 10. Mỗi worker có một pool tối đa 10 kết nối.

- Ngân sách dành cho worker = `160 - 20 - 70 - 10 = 60` kết nối.
- Trần lý thuyết theo connection = `floor(60 / 10) = 6` worker.
- Vì 6 worker dùng hết ngân sách dự kiến, **4–5 worker** thường là các mức cần đo đầu tiên; kết quả cuối phụ thuộc benchmark CPU/I/O/locks và mức dự phòng.
- Nếu worker có thêm pool riêng 4 connection vào **cùng DB**, phải tính 14 connection/worker, đưa trần sơ bộ xuống `floor(60 / 14) = 4` worker.

**Bài tập 2 — Đọc biểu đồ**

Một job tăng từ 6 lên 10 worker: records/s tăng 3%, nhưng p95 query tăng 90%, pool pending tăng từ 0 lên 25 và số rollback gấp bốn. Bạn có tăng lên 14 worker nữa không? **Không nên tăng trước khi điều tra**: throughput đã gần bão hòa; cần xem DB wait/lock/IO và giảm hoặc giữ concurrency, sau đó tối ưu truy vấn và kiểm thử lại.

**Bài tập 3 — Đánh giá an toàn**

Một job remote chunking có writer gọi API ngoài DB và insert DB. Khi DB timeout, broker gửi lại message. Để bảo đảm restart/retry không sinh đơn hàng trùng, cần định danh nghiệp vụ ổn định cho từng đơn hàng, unique constraint/upsert hoặc idempotency key cho side effect; phối hợp ack và commit theo thiết kế của pipeline. Chỉ tăng pool hoặc số worker không giải quyết được nguy cơ duplicate.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, parallel steps, partitioning và remote chunking.
- [Spring Batch Reference — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job.html): vòng đời job, execution, restart và JobRepository.
- [Spring Batch Reference — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): status và điều kiện chuyển step.
- [HikariCP — Configuration Knobs](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): `maximumPoolSize`, `minimumIdle`, `connectionTimeout`.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, wait events và số liệu DB.
- [PostgreSQL — Connection Settings](https://www.postgresql.org/docs/current/runtime-config-connection.html): `max_connections` và quản lý kết nối.

**Nguyên tắc áp dụng:** đối với Spring Batch chạy song song, quy mô worker phải được điều khiển bởi **năng lực phục vụ của hệ thống chậm nhất**. Hãy dùng ngân sách connection để đặt giới hạn an toàn sơ bộ, dùng throughput/latency/lock/I/O để tìm điểm tối ưu và dùng backpressure để bảo vệ database khi tải vượt dự kiến. Việc scale đúng phải cải thiện tốc độ hoàn thành job **mà không đánh đổi tính nhất quán, khả năng restart và SLA của các dịch vụ khác**.

