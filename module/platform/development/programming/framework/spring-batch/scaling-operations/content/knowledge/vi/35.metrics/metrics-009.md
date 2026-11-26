# Database connection usage khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Hiểu **database connection usage** là gì trong một job Spring Batch và phân biệt kết nối vật lý, kết nối đang được mượn từ pool, phiên giao dịch, truy vấn đang chạy và hàng đợi chờ connection.
- Giải thích ý nghĩa của các metric **active, idle, pending, total, max, timeout** của HikariCP, cùng những giới hạn của chúng khi suy luận hiệu năng.
- Tính **ngân sách tổng connection ở cấp cluster** cho manager, multi-threaded steps, parallel steps, local/remote partitioning, `JobRepository`, nguồn đọc và nguồn ghi.
- Chỉ ra tại sao `JdbcCursorItemReader`, chunk transactions, writer JDBC, retry và long-running transactions có thể giữ connection lâu hơn dự kiến.
- Đo tình trạng pool bằng **Micrometer / Spring Boot Actuator / Prometheus** và đối chiếu với `pg_stat_activity`, lock wait và các thống kê PostgreSQL.
- Cấu hình các tham số HikariCP có chủ đích, gồm `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `maxLifetime` và `leakDetectionThreshold`; biết tham số nào **không sửa được bottleneck DB**.
- Dùng ví dụ **Java 17 / Spring Batch 5.x** để thiết kế reader `@StepScope`, writer, bounded worker executor và điểm quan sát connection pressure.
- Thực hiện thử nghiệm scaling/load dài hạn, chẩn đoán timeouts, connection leaks, pool starvation và đề xuất giới hạn concurrency có kiểm chứng.
- Đảm bảo retry/restart, snapshot ổn định, thread safety và business correctness ngay cả khi database quá tải.

## 1. Tình huống: CPU còn trống nhưng tăng worker lại làm job chậm

Module **SPRING_BATCH_SCALING_OPERATIONS** hướng tới mở rộng Spring Batch trên workload lớn qua multi-threaded step, parallel steps, partitioning và kiến trúc phân tán; điều kiện đi kèm là đo nút thắt, an toàn luồng, retry/restart và sử dụng tài nguyên thực tế.

Giả sử ứng dụng nhập **24 triệu đơn hàng** từ PostgreSQL sang một bảng kết quả. Khi có bốn worker, throughput đạt `5.000 item/s`. Sau khi tăng lên 16 worker, CPU trung bình vẫn dưới 50%, nhưng:

- Throughput giảm về `3.100 item/s`.
- Thời gian chờ JDBC connection tăng mạnh.
- HikariCP báo `active` sát `maximumPoolSize` và `pending > 0`.
- PostgreSQL có nhiều session `idle in transaction` hoặc đang chờ lock.
- Một vài chunk timeout rồi retry, làm số lần ghi thử tăng hơn số bản ghi commit thực tế.

Vấn đề không hẳn do thiếu CPU; **connection acquisition, transaction latency hoặc database contention** có thể đã là nút thắt.

~~~mermaid
flowchart LR
    M["Manager / Parallel Steps"] --> E["TaskExecutor: bounded threads"]
    E --> W1["Worker 1"]
    E --> W2["Worker 2"]
    E --> WN["Worker N"]
    W1 --> P["HikariCP: active / idle / pending"]
    W2 --> P
    WN --> P
    P --> DB["PostgreSQL: sessions / locks / IO"]
    M --> JR["JobRepository"]
    JR --> DB
    DB --> O["Business output commits"]
~~~

**Điểm quan trọng:** tăng số thread/pod không làm database tự tạo thêm công suất. Nếu DB đã bão hòa, thêm connection có thể tăng tranh chấp, giữ transaction lâu hơn và khiến **goodput** giảm.

## 2. Khái niệm chính: một connection không chỉ là “một query”

Một ứng dụng JDBC với connection pool có những khái niệm khác nhau:

| Khái niệm | Nghĩa | Điều không thể suy ra trực tiếp |
| --- | --- | --- |
| **Physical connection** | Kết nối thực từ pool tới DB/server/proxy | Không phải một JVM thread hay một query |
| **Logical connection handle** | Đối tượng `Connection` mà code mượn từ `DataSource` | Không nhất thiết tạo socket vật lý mới |
| **Pool active** | Connection pool đã cho code mượn, chưa được trả | Không có nghĩa CPU DB đang thực thi truy vấn cho tất cả |
| **Pool idle** | Connection vật lý trong pool, sẵn sàng được mượn | Không đồng nghĩa database không phải cấp tài nguyên session |
| **Pool pending** | Thread đang đợi pool cấp connection | Không có nghĩa DB đang xử lý truy vấn chậm, chỉ cho thấy cầu > khả năng cấp tức thời |
| **Pool total** | Connection vật lý hiện có trong pool theo gauge | Có thể nhỏ hơn max vì tạo dần, DB fail hoặc pool đang co giãn |
| **Pool maximum** | Giới hạn connection mà **pool đó** có thể giữ | Không phải giới hạn toàn cluster hoặc toàn PostgreSQL |
| **DB session** | Phiên kết nối nhìn thấy từ database | Có thể qua proxy; không luôn 1:1 với application pool |
| **DB active query** | PostgreSQL backend đang thực thi công việc | Không phải số Hikari active |
| **Transaction open** | Giao dịch chưa commit/rollback | Có thể không chạy query và vẫn giữ locks/snapshot |

Trong mô hình phổ biến, một Hikari connection vật lý tương ứng một PostgreSQL backend session, nhưng PgBouncer ở **transaction pooling** hoặc proxy khác có thể làm quan hệ giữa client connection và backend connection khác 1:1.

### Vì sao active không bằng query đang chạy?

Khi code mượn connection rồi gọi API HTTP ngoài trước khi trả connection, Hikari có thể báo `active=1` suốt thời gian network wait, dù PostgreSQL không thực thi query nào. Nếu transaction vẫn mở, session có thể là `idle in transaction`, còn giữ lock hoặc snapshot gây ảnh hưởng cho transaction khác.

Ngược lại, một câu SQL chậm có thể giữ một connection active rất lâu, làm `pending` tăng trong khi số active chỉ bằng giới hạn pool — cần phân biệt **query latency** với **thời gian code giữ connection**.

## 3. Đời sống của connection trong một chunk Spring Batch

Với chunk-oriented processing, Step thường thực hiện đọc → xử lý → ghi → cập nhật state → commit. Những kết nối liên quan có thể đến từ **nhiều DataSource**.

~~~mermaid
sequenceDiagram
    participant W as Worker Step
    participant R as ItemReader
    participant X as Chunk Tx Manager
    participant P as Hikari Pool
    participant DB as Database
    participant J as JobRepository
    W->>R: open(ExecutionContext)
    R->>P: Mở connection/cursor nếu cần
    P->>DB: Tạo hoặc tái sử dụng DB session
    loop Mỗi chunk
      X->>P: Mượn transaction connection
      W->>R: read items
      W->>W: process items
      W->>DB: writer dùng connection theo tx
      W->>R: ItemStream.update(context)
      W->>J: Persist StepExecution/context
      X->>DB: Commit hoặc rollback
      X->>P: Trả transaction connection
    end
    W->>R: close()
    R->>P: Đóng cursor, trả connection khi phù hợp
~~~

Sơ đồ là **mô hình logic**; thứ tự và phạm vi kết nối chính xác tùy reader, writer, transaction manager, cấu hình `JobRepository` và việc đọc/ghi cùng hay khác DataSource.

### Reader không giống nhau về connection lifetime

- `JdbcCursorItemReader` có thể mở connection/cursor khi `ItemStream.open` và giữ nó cho tới `close` trong suốt Step, tùy `useSharedExtendedConnection` và cách DataSource được cấu hình. Do đó **một reader có thể giữ connection lâu qua nhiều chunk**.
- `JdbcPagingItemReader` thường gọi query theo trang; vòng đời checkout của connection phụ thuộc DAO/JDBC/transaction và không mặc định giữ một cursor riêng lâu như cursor reader.
- File reader không cần DB connection để đọc input, nhưng writer hoặc `JobRepository` vẫn có thể dùng JDBC.
- Reader từ HTTP/broker có resource lifetime và backpressure khác JDBC; đừng cộng một source JDBC connection nếu thực tế source không dùng JDBC.

### Chunk transaction và JobRepository

Khi writer cùng dùng một DataSource và cùng transaction manager với chunk, nó có thể tái sử dụng connection gắn với transaction trong thread. Nếu `JobRepository` dùng DataSource khác, metadata write có thể cần **connection từ pool khác**; nếu dùng cùng DB nhưng transaction propagation khác, cần đo cấu hình thực tế.

**Không áp công thức “mỗi worker đúng một connection”.** Một worker có cursor reader connection **và** connection ghi theo transaction, trong khi metadata repository có thể dùng connection khác. Một số connection được mượn tuần tự, một số chồng thời gian. Cần quan sát high-water mark thực tế.

### Rủi ro với remote workers

Khi mỗi JVM có một `HikariDataSource`, connection pools là **riêng biệt** theo process. Manager có pool riêng, worker-A pool riêng, worker-B pool riêng. `maximumPoolSize=20` ở từng pod không đồng nghĩa tổng hệ thống chỉ tối đa 20 kết nối.

## 4. Công thức ngân sách connection ở cấp cluster

Nếu có `m` application instances, mỗi instance có `p` pools, giới hạn kết nối **khả dĩ**:

~~~text
configured_pool_connection_ceiling
    = SUM(all process instances, all applicable pools, maxPoolSize)

total_possible_DB_client_sessions
    ≈ configured_pool_connection_ceiling
      + admin / reporting / migration / other apps
~~~

Chỉ cộng các pool thực sự kết nối tới cùng database/server/quota đang xét; nếu các pool trỏ về các DB server khác nhau, cần tính ngân sách riêng. Nếu có PgBouncer hoặc DB proxy, phải phân biệt **client pool limit**, **proxy connection limit** và **backend server connection limit**.

### Ví dụ số học

Giả định PostgreSQL `max_connections=200`; đội DBA giữ ngân sách 40 connection cho admin, app khác, monitoring và nhu cầu dự phòng. Phần có thể cân nhắc cho batch tối đa:

~~~text
C_DB_configured       = 200
C_reserved_by_policy  = 40
C_available_for_batch = 160
~~~

Topology:

| Thành phần | Số instance | Max pool/instance | Trần kết nối |
| --- | ---: | ---: | ---: |
| Manager | 2 | 12 | 24 |
| Worker | 12 | 10 | 120 |
| Admin/utility batch | 1 | 8 | 8 |
| **Tổng batch ceiling** | | | **152** |

`152 < 160`, nhưng **đây mới là điều kiện ngân sách sơ bộ**. Không có nghĩa DB chịu tải tốt khi 152 connection đều query cùng bảng. Ngoài ra phải tính topology failover: nếu rolling deploy tạo thêm 4 worker trong thời gian overlap, trần có thể tăng thêm 40 và vượt ngân sách.

### Không dùng max_connections làm mục tiêu hiệu năng

`max_connections` là một ngưỡng giới hạn session; PostgreSQL cũng tiêu thụ memory và quản lý transaction/locks theo concurrency. Connection nhiều hơn có thể làm throughput giảm do CPU scheduling, IO, lock wait hoặc buffer contention.

Một mục tiêu tốt thường là **số connection đủ cho sustained goodput dưới mức độ tranh chấp chấp nhận được**, với headroom cho failover và quản trị, chứ không tối đa hóa số session.

## 5. Ngân sách theo vai trò: reader, writer, repository

Một mô hình xấp xỉ để lập kế hoạch:

~~~text
C_source ≈ live_cursor_readers
           + noncursor_source_operations_in_flight
           + source_admin / audit

C_target ≈ simultaneous_writer_transactions
           + other_target_operations_in_flight

C_repository ≈ concurrent_metadata_operations
               + launcher / explorer / management overhead
~~~

Đây là **nhu cầu concurrent checkout**, không phải số connection vật lý luôn phải có. `C_source` và `C_target` có thể trùng nhau khi dùng cùng pool; một transaction có thể reuse connection. Vì vậy **không cộng các dòng một cách máy móc nếu chúng cùng transaction/pool**.

### Bảng ước lượng minh họa

Giả sử local partitioning có 8 worker concurrent trên cùng JVM:

- Mỗi worker dùng `JdbcCursorItemReader` giữ tối đa một input connection.
- Mỗi worker có một business chunk transaction concurrent có thể cần thêm connection nếu cursor reader dùng connection riêng.
- `JobRepository` dùng pool riêng và cập nhật metadata theo chunk boundary.
- Manager/validation bước khác có thể mượn kết nối để kiểm tra status.

Ngân sách **thận trọng cho hai nguồn riêng** là source pool chịu được khoảng 8 cursor lâu sống, target pool chịu được khoảng 8 writer transactions concurrently, thêm headroom; repository pool được sized theo metadata traffic. Nếu cả source và target cùng một pool, peak checkout có thể gần `8+8` trong cấu hình cursor riêng, **không mặc định bằng 8**.

Nhưng con số thật phụ thuộc cách lifecycle/transaction wiring. Hãy đo `active`/`pending` và PostgreSQL sessions khi **8 worker đồng thời chạy**, thay vì suy từ lý thuyết một cách cứng nhắc.

### Nếu dùng multi-threaded step

Một `StepExecution` có nhiều threads cùng xử lý chunk có thể tạo nhiều transaction connections. Shared reader/writer có thể không thread-safe; vấn đề connection usage không được tách khỏi **thread safety** và semantics checkpoint.

### Nếu dùng parallel steps

Nhiều step khác nghiệp vụ cùng mở nguồn hoặc ghi cùng DB. Pool budget cần tính **tổng concurrency của các step đang overlap**, không theo step chậm nhất hoặc theo từng step riêng biệt.

## 6. HikariCP: hiểu đúng sáu metric nền tảng

Với Spring Boot sử dụng HikariCP và Micrometer, thường có metric các dạng sau, tùy registry/naming convention:

| Ý nghĩa | Tên Prometheus thường gặp | Cách đọc |
| --- | --- | --- |
| Active connections | `hikaricp_connections_active` | Đang được mượn từ pool |
| Idle connections | `hikaricp_connections_idle` | Đang sẵn sàng, chưa được mượn |
| Total connections | `hikaricp_connections` | Tổng physical connections được quản lý |
| Pending threads | `hikaricp_connections_pending` | Thread chờ `getConnection()` |
| Max configured connections | `hikaricp_connections_max` | Capacity ceiling của pool |
| Min configured idle | `hikaricp_connections_min` | Giá trị minimumIdle cấu hình |
| Connection acquisition time | `hikaricp_connections_acquire_seconds` hoặc timer tương ứng | Thời gian chờ lấy connection |
| Connection usage time | `hikaricp_connections_usage_seconds` hoặc timer tương ứng | Thời gian mượn tới lúc trả connection |
| Connection timeout count | `hikaricp_connections_timeout_total` | Số lần không lấy được connection trước deadline |

**Tên metric chính xác phải kiểm tra trên `/actuator/prometheus`** của ứng dụng/phiên bản registry. Một số timer xuất thành các series `_seconds_count`, `_seconds_sum` hoặc `_seconds_bucket` nếu bật histogram; các suffix phụ thuộc cách exporter xuất dữ liệu.

### Quan hệ giữa active, idle và total

Ở một thời điểm pool ổn định:

~~~text
total_connections ≈ active_connections + idle_connections

0 <= active_connections <= configured_max
0 <= idle_connections <= configured_max

pending_threads có thể > 0 ngay cả khi
total_connections < configured_max (pool đang tạo connection,
DB không nhận kết nối, network chậm hoặc trạng thái chuyển tiếp)
~~~

Các gauge là ảnh chụp không đồng bộ, nên không bảo đảm `active+idle=total` tuyệt đối tại mọi sample. Không tạo alert dựa vào một sai lệch 1 connection trong một lần scrape.

### Diễn giải mẫu

~~~text
Pool=source: active=8, idle=0, pending=12, max=8
Pool=target: active=3, idle=5, pending=0, max=8
~~~

Source pool đang có áp lực cấp phát nghiêm trọng; target pool còn rảnh. Tăng target pool không giải quyết việc source chờ connection. Nhưng trước khi tăng source max, cần biết connection đang bị giữ vì **cursor sống lâu, transaction/lock, query chậm hay leak**.

### Khi active=max nhưng pending=0

Pool hoạt động hết công suất **không nhất thiết là sự cố** nếu không có chờ, acquisition p95 thấp và throughput/latency đạt yêu cầu. Ngược lại, pending tăng, timeout tăng hoặc throughput giảm liên tục là tín hiệu mạnh hơn của thiếu capacity hoặc checkout quá lâu.

## 7. Spring Boot + Hikari: cấu hình có giới hạn và có tên pool

Ví dụ application YAML cho **một DataSource** (số giả định, phải benchmark):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: batch_app
    password: change-me-via-secret-manager
    hikari:
      pool-name: batch-orders
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 10000
      validation-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 300000
      leak-detection-threshold: 30000

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: spring-batch-orders
~~~

**Không đưa password thật vào Git**; ví dụ dùng placeholder có tính minh họa. Production nên đưa credential qua cơ chế secret injection an toàn và giới hạn quyền endpoint metrics; `/actuator/prometheus` có thể tiết lộ thông tin vận hành.

### Ý nghĩa các setting

- `maximumPoolSize=12`: tại một thời điểm Hikari không cấp vượt số connection cho pool này; không phải limit toàn cluster.
- `minimumIdle=4`: mục tiêu số idle connection; `minimumIdle` mặc định bằng `maximumPoolSize` nếu không cấu hình, tạo kiểu fixed-size pool trong nhiều trường hợp.
- `connectionTimeout=10000` (ms): thời gian tối đa chờ lấy connection từ pool trước khi ném exception; **không phải** timeout chạy SQL hay timeout commit.
- `validationTimeout=3000` (ms): timeout validate connection; phải nhỏ hơn `connectionTimeout` trong ràng buộc cấu hình HikariCP.
- `idleTimeout=600000`: kết nối idle có thể được retire theo cơ chế housekeeper khi vượt `minimumIdle`, không phải cam kết đóng đúng millisecond.
- `maxLifetime=1740000`: vòng đời tối đa của một physical connection trong pool. Hikari không chủ động đóng connection **đang được mượn** giữa một transaction dài; khi trả về pool, connection quá tuổi sẽ bị retire.
- `keepaliveTime=300000`: cho phép keepalive trên **idle** connection để tránh các thiết bị mạng đóng phiên nhàn rỗi; cần nhỏ hơn `maxLifetime` và đáp ứng ràng buộc phiên bản.
- `leakDetectionThreshold=30000`: log cảnh báo khi connection bị giữ lâu hơn ngưỡng; **không tự đóng connection** hoặc chữa leak.

Các giá trị trên là điểm khởi đầu, không phải cấu hình được khuyến nghị cho mọi hệ. Cần tương thích với DB/network idle timeout, transaction timeouts và nhu cầu cursor lâu sống. `maxLifetime` nên được chọn tương quan với lifetime do hạ tầng cấp dưới áp đặt; tránh đặt quá thấp gây connection churn.

### Leak detection: false positive của cursor dài

Một `JdbcCursorItemReader` có thể giữ connection hàng phút nếu cả step chạy lâu. `leakDetectionThreshold=30s` có thể ghi cảnh báo “apparent connection leak” dù connection được trả đúng khi step kết thúc. Đừng coi mọi leak detection warning là một memory leak thật; kiểm tra stack trace, borrow duration, step lifecycle và việc `close()` có xảy ra sau failure không.

### Các timeout khác nhau

- JDBC checkout timeout: chờ pool cấp connection.
- SQL statement/query timeout: giới hạn thời gian thực thi truy vấn theo driver/DB.
- Transaction timeout: giới hạn thời gian transaction nếu transaction manager/framework áp dụng.
- Network/socket timeout: hành vi đọc/ghi trên kết nối TCP.
- Database lock timeout: chờ lock theo policy DB.
- Application-level chunk timeout: quy tắc do ứng dụng đặt.

Tăng `connectionTimeout` chỉ làm thread chờ lâu hơn khi pool đang nghẽn; không tự tăng throughput.

## 8. Quan sát ở hai đầu: pool metrics và PostgreSQL sessions

Một metric Hikari cho biết **checkout bên JVM**; `pg_stat_activity` cho biết **các backend session hiện tại** ở PostgreSQL. Đối chiếu cả hai mới xác định connection bị giữ do code hay DB.

Ví dụ query PostgreSQL:

~~~sql
SELECT
    application_name,
    usename,
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, usename, state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Một phiên `state='active'` có thể vẫn đợi lock hoặc IO, vì trạng thái “active” không mặc nhiên có nghĩa query đang sử dụng CPU. Cần xem cả `wait_event_type` và `wait_event`.

### Tìm transaction bị giữ quá lâu

~~~sql
SELECT
    pid,
    application_name,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS current_query_age,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 30;
~~~

Phân quyền truy cập `pg_stat_activity` có thể hạn chế thông tin query của session khác; sử dụng role có quyền quan sát phù hợp. Không đưa query chứa PII, raw SQL parameters hoặc credential vào log/ticket không được bảo vệ.

### `idle in transaction` rất đáng chú ý

Khi connection mở transaction rồi ngừng chạy SQL mà không commit/rollback, PostgreSQL có thể báo `idle in transaction`. Nó có thể giữ snapshot, lock hoặc gây trở ngại cho vacuum và hoạt động của transaction khác.

Nhưng đừng đánh đồng `state='idle'` (không có transaction mở) với `idle in transaction`. Một connection idle trong pool là trạng thái thường gặp và **không tự là leak**.

### Kiểm tra max_connections và reservation

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
SHOW reserved_connections;
~~~

`reserved_connections` có ở các phiên bản PostgreSQL hỗ trợ tham số này; trên phiên bản cũ có thể không tồn tại. Chỉ số hiển thị là giới hạn cấu hình, cần thêm ngân sách cho các role/app khác và các server thực tế. Trong managed database, nhà cung cấp có thể áp dụng thêm giới hạn/connection proxy; kiểm tra theo hạ tầng đang dùng.

## 9. Kiểm tra DB locks khi số connection tăng

Pool pending có thể tăng vì các worker giữ connection khi đợi lock. Một transaction lock chậm khiến connection bị mượn lâu hơn, kéo theo nhiều thread phải chờ pool.

~~~mermaid
flowchart LR
    A["Nhiều writers đồng thời"] --> L["Row/table lock contention"]
    L --> T["Transaction duration tăng"]
    T --> C["Connection usage duration tăng"]
    C --> P["Hikari active=max, pending tăng"]
    P --> R["Timeout / retry"]
    R --> A
~~~

Vòng lặp này đặc biệt nguy hiểm khi retry ngay lập tức mà không có backoff.

### PostgreSQL: session đang chờ sự kiện

~~~sql
SELECT
    pid, application_name, state,
    wait_event_type, wait_event,
    now() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type IS NOT NULL
ORDER BY query_start NULLS LAST;
~~~

### Tìm ai đang chặn ai

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    pg_blocking_pids(blocked.pid) AS blocking_pids,
    now() - blocked.query_start AS blocked_query_age,
    left(blocked.query, 160) AS blocked_query
FROM pg_stat_activity blocked
WHERE blocked.datname = current_database()
  AND cardinality(pg_blocking_pids(blocked.pid)) > 0
ORDER BY blocked.query_start NULLS LAST;
~~~

Chạy trên PostgreSQL hỗ trợ `pg_blocking_pids`; cần quyền quan sát phù hợp và cẩn trọng chi phí khi nhiều session. Nếu không có blocker nhưng DB I/O saturates, cũng có thể khiến active connection lâu và pending tăng.

**Không sửa triệu chứng chỉ bằng tăng `maximumPoolSize`** khi gốc rễ là transaction lock. Cần xác định key hot, phạm vi transaction, isolation, index, batch write và concurrency theo partition.

## 10. Prometheus/PromQL: theo dõi saturation, waiting và timeouts

Ví dụ giả định HikariCP metrics đã được export từ Spring Boot Actuator và Micrometer. **Xác nhận tên thật trên endpoint** vì version và naming có thể khác.

### Mức pool active so với max

~~~promql
hikaricp_connections_active
/
clamp_min(hikaricp_connections_max, 1)
~~~

Đặt nhãn `pool`/`application`/`instance` sao cho tử số và mẫu số tương ứng **cùng một pool trên cùng một process**. Không cộng active của mọi pod rồi chia cho max của một pod.

### Tổng pending threads

~~~promql
sum by (pool) (hikaricp_connections_pending)
~~~

Khi gộp theo `pool`, nên xem cả instance breakdown; một instance pending cao có thể bị che bởi trung bình cluster.

### Connection timeout rate 5 phút

~~~promql
sum by (pool) (
  rate(hikaricp_connections_timeout_total[5m])
)
~~~

### Thời gian chờ lấy connection

Nếu registry export timer Hikari acquisition thành `hikaricp_connections_acquire_seconds_sum` và `_count`:

~~~promql
sum by (pool) (
  rate(hikaricp_connections_acquire_seconds_sum[5m])
)
/
clamp_min(
  sum by (pool) (
    rate(hikaricp_connections_acquire_seconds_count[5m])
  ), 0.000001
)
~~~

Nếu bật histogram buckets, có thể tính percentile tương ứng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, pool) (
    rate(hikaricp_connections_acquire_seconds_bucket[5m])
  )
)
~~~

Nếu không bật histogram distribution, series `_bucket` có thể không tồn tại. Khi đó đừng khẳng định percentile p95 chỉ từ `sum/count` vì đó là **mean**, không phải p95.

### Biểu đồ nên đặt cạnh nhau

- Hikari `active`/`idle`/`pending`/`max` theo từng pool/instance.
- Acquisition p95, usage duration và timeout rate.
- PostgreSQL `active query`, `idle in transaction`, lock wait, IO wait.
- Step `readCount`/`writeCount`/`commitCount`/`rollbackCount` và business goodput.
- Worker active threads, executor queue, heap/GC, CPU throttling.
- Chunk duration, DB transaction duration, retry/backoff, DLQ nếu dùng broker.

Một biểu đồ `active/max=100%` trong 20 giây không tự cho biết hệ thống cần tăng pool; **pending + acquisition latency + timeout + throughput trend** tạo bức tranh đáng tin cậy hơn.

## 11. Java 17 / Spring Batch 5.x: reader cursor có state riêng theo partition

Ví dụ job đọc đơn hàng đã được chụp vào snapshot bất biến. Mỗi partition có `StepExecution` riêng với khoảng `[startInclusive,endExclusive)`; cách này cho phép reader mở lại đúng dữ liệu khi restart.

### 11.1. Schema nguồn và kết quả

~~~sql
CREATE TABLE batch_order_snapshot (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);

CREATE TABLE batch_order_result (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

Trong production cần thêm capture protocol để snapshot bất biến sau READY, retention cho restart và quản lý output theo business contract. Hai bảng dùng cùng DB trong ví dụ để minh họa; nếu đọc/ghi ở hai database khác nhau, pool/transaction/consistency phải thiết kế riêng.

### 11.2. Reader `@StepScope`

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRow(
        String snapshotId,
        long orderId,
        long sourceVersion,
        String payload) {}

@Configuration
class ConnectionAwareReaderConfig {

    @Bean("orderCursorReader")
    @StepScope
    JdbcCursorItemReader<OrderRow> orderCursorReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['snapshotId']}")
                String snapshotId,
            @Value("#{stepExecutionContext['startInclusive']}")
                Long startInclusive,
            @Value("#{stepExecutionContext['endExclusive']}")
                Long endExclusive) {

        if (snapshotId == null || snapshotId.isBlank()
                || startInclusive == null || endExclusive == null
                || startInclusive >= endExclusive) {
            throw new IllegalArgumentException(
                    "Invalid partition ExecutionContext");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("orderCursorReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT order_id, source_version, payload
                    FROM batch_order_snapshot
                    WHERE snapshot_id = ?
                      AND order_id >= ?
                      AND order_id < ?
                    ORDER BY order_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startInclusive);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                    snapshotId,
                    rs.getLong("order_id"),
                    rs.getLong("source_version"),
                    rs.getString("payload")))
                .fetchSize(500)
                .saveState(true)
                .build();
    }
}
~~~

**Ý nghĩa connection usage:**

- Một `JdbcCursorItemReader` thường mở JDBC connection/cursor trong `open()` và đóng ở `close()`. Nếu một partition chạy 30 phút, reader có thể giữ một connection từ pool trong khoảng thời gian dài, tùy cấu hình shared/extended connection.
- `fetchSize(500)` là **hint cho driver** về cách lấy dữ liệu, không phải cam kết cursor server-side hoặc 500 record/connection. Với PostgreSQL JDBC, behavior streaming còn phụ thuộc auto-commit và các điều kiện driver/transaction; cần thử trên phiên bản đang dùng.
- `ORDER BY order_id` cùng primary key đảm bảo thứ tự deterministic trong snapshot, cần cho state-based restart.
- `saveState(true)` cho phép `ItemStream` lưu tiến độ, **không có nghĩa** connection cũ sống qua JVM crash: node mới phải mở connection/cursor mới và khôi phục từ checkpoint.
- `@StepScope` đảm bảo bean được resolve theo `StepExecution` của mỗi partition; nó **không** biến một singleton reader dùng chung trong multi-threaded step thành thread-safe.

### Đừng tăng thread pool mà bỏ qua cursor connection

Nếu 24 local/remote partitions đang chạy đồng thời và mỗi cursor giữ một source connection, source pool cần chịu được khoảng 24 checkout lâu sống **nếu tất cả dùng một pool**. Với nhiều JVM, mỗi process giữ số connection riêng. Nếu target writer cũng cần connection từ cùng pool, `maximumPoolSize=24` có thể không đủ để 24 cursor và 24 writer transactions đồng thời tiến hành.

Đó là một **tình huống sizing cần đo**: một số cấu hình reader dùng shared extended connection, một số transaction/repository reuse connection, nhưng tuyệt đối không mặc định rằng “24 workers chỉ cần 24 JDBC connections”.

## 12. Writer JDBC theo chunk và mối quan hệ với connection pool

Trong Spring Batch, writer chạy trong chunk transaction (khi cấu hình phù hợp). Ví dụ dùng `JdbcTemplate.batchUpdate` để tránh gọi một SQL round-trip cho từng item.

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
class ConnectionAwareWriterConfig {

    @Bean("orderResultWriter")
    ItemWriter<OrderRow> orderResultWriter(
            JdbcTemplate jdbcTemplate) {

        return chunk -> {
            var items = chunk.getItems();
            if (items.isEmpty()) {
                return;
            }

            jdbcTemplate.batchUpdate("""
                INSERT INTO batch_order_result(
                    snapshot_id, order_id, source_version, payload
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (snapshot_id, order_id)
                DO UPDATE SET
                    source_version = EXCLUDED.source_version,
                    payload = EXCLUDED.payload
                WHERE (
                    batch_order_result.source_version,
                    batch_order_result.payload
                ) IS DISTINCT FROM (
                    EXCLUDED.source_version,
                    EXCLUDED.payload
                )
                """,
                items,
                200,
                (ps, row) -> {
                    ps.setString(1, row.snapshotId());
                    ps.setLong(2, row.orderId());
                    ps.setLong(3, row.sourceVersion());
                    ps.setString(4, row.payload());
                });
        };
    }
}
~~~

**Giải thích:**

- `JdbcTemplate` mượn connection theo transaction context do Spring quản lý, nếu nó được cấu hình với đúng `DataSource`/`PlatformTransactionManager`.
- Batch update có thể giảm round-trip, nhưng **không** tự làm transaction ngắn: chunk size lớn hoặc lock contention vẫn giữ connection lâu.
- `ON CONFLICT` giúp replay cùng snapshot không làm sai trạng thái hàng cuối, nhưng side effect như email, thanh toán, trigger audit hoặc event publish cần idempotency riêng.
- Kết quả từ `batchUpdate` là update counts của JDBC driver; với `ON CONFLICT DO UPDATE ... WHERE`, không thể suy `writeCount == số new unique business rows`. Cần business goodput/audit riêng.
- `.batchUpdate(...,200,...)` là kích thước batch JDBC minh họa; step chunk size có thể khác. Chọn bằng thử nghiệm p95 transaction latency, memory và DB contention.

**Cảnh báo về pool wiring:** nếu reader và writer trỏ tới hai `DataSource` khác nhau nhưng Step chỉ dùng một transaction manager, chúng **không tự chung một transaction nguyên tử**. Với repository ở một DB thứ ba, càng cần quan tâm failure window commit–checkpoint và writer idempotent.

## 13. Local partition manager/worker và trần executor

Khi dùng local partitioning, ta có thể giới hạn số worker bằng một `ThreadPoolTaskExecutor`. Ví dụ Spring Batch 5.x:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class ConnectionBudgetJobConfig {

    @Bean("demoPartitioner")
    Partitioner demoPartitioner() {
        return gridSize -> {
            // Ví dụ: manifest đã chốt, 4 khoảng deterministic.
            long[] bounds = {1L, 1001L, 2001L, 3001L, 4001L};
            var result = new LinkedHashMap<
                    String, ExecutionContext>();

            for (int i = 0; i < bounds.length - 1; i++) {
                var context = new ExecutionContext();
                context.putString("snapshotId", "orders-demo-snapshot");
                context.putLong("startInclusive", bounds[i]);
                context.putLong("endExclusive", bounds[i + 1]);
                result.put(
                        String.format("partition%04d", i),
                        context);
            }

            return result;
        };
    }

    @Bean("budgetedWorker")
    Step budgetedWorker(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("orderCursorReader")
                JdbcCursorItemReader<OrderRow> reader,
            @Qualifier("orderResultWriter")
                ItemWriter<OrderRow> writer) {

        return new StepBuilder("budgetedWorker", repository)
                .<OrderRow, OrderRow>chunk(200, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean("budgetedExecutor")
    ThreadPoolTaskExecutor budgetedExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("budgeted-batch-");
        executor.initialize();
        return executor;
    }

    @Bean("budgetedManager")
    Step budgetedManager(
            JobRepository repository,
            @Qualifier("budgetedWorker") Step worker,
            @Qualifier("demoPartitioner") Partitioner partitioner,
            @Qualifier("budgetedExecutor")
                ThreadPoolTaskExecutor executor) {

        return new StepBuilder("budgetedManager", repository)
                .partitioner("budgetedWorker", partitioner)
                .step(worker)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean("budgetedJob")
    Job budgetedJob(
            JobRepository repository,
            @Qualifier("budgetedManager") Step manager) {

        return new JobBuilder("budgetedJob", repository)
                .start(manager)
                .build();
    }
}
~~~

### Giới hạn của ví dụ

- `demoPartitioner` tạo **bốn range cố định cho một snapshot minh họa**, không đọc source live, không phải thuật toán partitioning tổng quát. Trong production phải tạo và validate manifest trước, lưu bất biến qua restart.
- `gridSize=4` chỉ là hint theo semantics của partitioner/handler; executor bốn thread tạo **giới hạn concurrency** trong local JVM minh họa.
- Input thực cần chụp sẵn đúng các ID và version; không biến `snapshotId` thành biến mới ngẫu nhiên trong mỗi lần restart.
- `JobRepository`, `DataSource`, transaction manager, JDBC schema và connection pool đã được ứng dụng cung cấp bên ngoài đoạn code.
- Tại một JVM, nếu một pool chung chỉ có bốn connections và bốn cursor readers giữ bốn connections trong suốt Step, writer có thể bị **starvation** khi mượn connection cho transaction.
- Khi remote partitioning, mỗi worker JVM có executor và pool riêng; không lấy limit executor ở manager để suy tổng DB connection ceiling.

### Bảng budget cho ví dụ

| Thành phần | Concurrency minh họa | Cần tính |
| --- | ---: | --- |
| Cursor readers | Tối đa 4 | Connection giữ dài khi cursor mở |
| Writer transactions | Tối đa 4 | Connection mượn để commit chunk |
| JobRepository operations | Tùy metadata transaction | Pool và peak checkout riêng/cùng DB |
| Manager validation | Có thể xảy ra trước/khi dispatch | Connection ngắn hạn, không mặc định 0 |
| Monitoring/admin | Song song với job | Headroom vận hành |

Đừng cấu hình `maximumPoolSize=4` chỉ vì `gridSize=4`. Cần thử thực tế về cách reader, writer và repo dùng connection, đồng thời bảo đảm DB không quá tải khi mở rộng.

## 14. Phân tách source, target và JobRepository pools

Với workload lớn, có thể tách DataSource để:

- Giới hạn read cursor không chiếm hết connection dành cho writer.
- Đặt Hikari metrics có tên riêng theo source, target, repository.
- Áp dụng credentials/quotas riêng, thậm chí physical databases khác nhau.
- Theo dõi metadata bottleneck độc lập với business query.

~~~mermaid
flowchart LR
    W["Worker Step"] --> S["Source Hikari Pool"]
    W --> T["Target Hikari Pool"]
    W --> R["Repository Hikari Pool"]
    S --> SD["Source PostgreSQL"]
    T --> TD["Target PostgreSQL"]
    R --> RD["JobRepository PostgreSQL"]
~~~

**Đây là sơ đồ logic, không phải yêu cầu phải có ba DB vật lý.** Nhiều ứng dụng Spring Batch dùng chung một DataSource/transaction manager cho business và metadata. Nếu tách thành ba DataSource, phải tự cấu hình routing, `JobRepository`, transaction managers, `JdbcTemplate` và bean qualifiers đúng; Spring Boot không tự biết chọn pool nào cho từng thành phần.

### Quy tắc giao dịch khi tách pool

Ví dụ một reader source pool và writer target pool:

- Source reader mở connection/cursor theo lifecycle riêng, có thể giữ qua nhiều chunk.
- Writer target transaction commit output.
- `JobRepository` ghi checkpoint qua repository pool.
- Một commit target thành công và repository commit lỗi có thể dẫn đến **replay**.

Muốn exactly-once ở nghiệp vụ, không đủ chỉ chọn ba pool nhỏ. Cần **writer idempotent**, ổn định snapshot/partition, business key/operation ID và reconciliation. Nếu yêu cầu atomic cross-DB cần thiết kế transaction/distributed protocol đúng, không giả định Spring Batch tự đảm bảo atomicity qua ba pools.

### Không nhân số kết nối vô tình

Nếu có ba pools trong **mỗi** worker JVM, mỗi pool `maximumPoolSize=10` và 10 JVM:

~~~text
10 JVM * 3 pools/JVM * 10 max/pool
= 300 possible physical connections
~~~

Nếu cả ba pool kết nối tới cùng một PostgreSQL instance, trần khả dĩ là 300 (chưa tính manager, services khác). Pool tách theo logic không tạo ra thêm quota DB. Nếu ba pool trỏ tới ba máy DB khác nhau, tính ngân sách riêng theo từng máy.

## 15. Khi sử dụng cursor, paging hay file reader?

Không có reader phù hợp nhất cho mọi workload. Connection usage là một yếu tố quan trọng trong quyết định:

| Reader | Mẫu connection | Lợi thế | Rủi ro |
| --- | --- | --- | --- |
| `JdbcCursorItemReader` | Có thể giữ cursor/connection xuyên Step | Đọc tuần tự, memory thấp nếu driver stream đúng | Occupancy dài, snapshot/transaction, failover/reopen |
| `JdbcPagingItemReader` | Truy vấn từng trang; checkout theo JDBC/tx | Không giữ một cursor lâu như cursor reader trong nhiều cấu hình | Paging order cần unique key, offset lớn có thể tốn chi phí |
| File reader | Không dùng JDBC cho input | Tiết kiệm source pool | IO/storage throughput, checkpoint path/version |
| API reader | Dùng HTTP client thay JDBC source | Không tốn source DB connections | API quota, timeout, retry, idempotency |
| Broker reader | Dùng consumer/broker session | Phù hợp streaming/chunk messages | Ack, redelivery, ordering, backlog |

### Cursor và Spring transaction

`JdbcCursorItemReader` mặc định có connection riêng của cursor tùy cấu hình Spring Batch. Nếu muốn cursor dùng **shared extended connection** cùng chunk transaction, cần cấu hình `ExtendedConnectionDataSourceProxy` và driver hỗ trợ holdability theo yêu cầu của API; việc thay đổi này ảnh hưởng **connection ownership, cursor lifetime và restart behavior** nên phải có integration test trên DB/driver thật.

**Đừng bật một option “share connection” chỉ để giảm active count** mà chưa thử rollback/restart và khả năng writer sử dụng cùng transaction.

### Paging cũng không miễn phí

Một paging reader với `pageSize=1000` và hàng chục worker vẫn tạo truy vấn source nhiều lần. Nếu database phải thực hiện scan/sort lớn ở mỗi page, read latency tăng và checkout duration cũng tăng. Cần index theo `(snapshotId,partitionKey,stableSortKey)` và dùng thứ tự deterministic. Với cursor hoặc paging, immutable snapshot là điều kiện quan trọng cho restart chính xác.

### Đừng sử dụng Hibernate/JPA tùy tiện trong batch lớn

Khi reader/processor giữ entity graph, lazy loading gây N+1 queries và mỗi item vô tình mở thêm JDBC operations, application có thể tăng connection usage và memory. Với workload đơn giản, JDBC row mapping và explicit batch writes thường dễ đo hơn. Nếu dùng JPA, cần kiểm soát persistence context/flush-clear và isolation, không mặc định Hibernate cache giải quyết giới hạn DB.

## 16. Sizing bằng Little's Law — áp dụng đúng đơn vị

Một kỹ thuật ước lượng nhu cầu connection checkout là Little's Law trong hệ ổn định:

~~~text
L ≈ λ * W

L = số connection được mượn trung bình
λ = tốc độ checkout hoàn thành, đơn vị borrow/giây
W = thời gian trung bình một lần borrow, đơn vị giây
~~~

**Quan trọng:** `λ` ở đây là **connection borrow/s**, không nhất thiết là business item/s. Một chunk mượn một connection có thể ghi 200 item, hoặc reader cursor mượn một lần cho toàn Step dài 30 phút. Thay `λ` bằng items/s mà không hiểu số checkout/item sẽ cho sizing sai.

### Ví dụ

Giả sử 500 checkout/s được hoàn thành khi workload ổn định, mỗi connection được giữ trung bình 0,020 giây:

~~~text
L = 500 borrow/s * 0,020 s/borrow
  = 10 active connections trung bình
~~~

Pool max 10 **không nhất thiết đủ** vì đây là mean. Burst, p95/p99 usage, GC pause và lock contention có thể làm active vượt 10; cần đo pending/acquisition timeouts và chọn headroom dựa vào phân phối thật.

### Ví dụ về cursor reader

Một reader cursor mượn connection **một lần trong 20 phút**, nên `borrow/s` thấp nhưng `W` rất lớn. Số connection active trung bình vẫn có thể xấp xỉ số reader mở đồng thời. Đây là lý do sizing dựa trên query/s hoặc borrow/s một mình không đủ.

### Bài toán ngân sách trong đợt rollout

Giả sử PostgreSQL được cấp ngân sách cho batch `C_budget=160` connections:

~~~text
2 managers * 10 maximumPoolSize = 20
12 workers * 10 maximumPoolSize = 120

Steady-state possible ceiling = 140
Remaining budget = 20
~~~

Nếu deploy rolling update tạm có thêm 4 worker:

~~~text
4 new workers * 10 max = 40
Temporary ceiling = 140 + 40 = 180
Budget = 160
Excess = 20
~~~

Ngay cả khi một số pod cũ sắp bị drain, một giai đoạn overlap có thể vượt quota. Cần giới hạn `maxSurge`/replica rollout, pool size, worker scale hoặc headroom; đừng đợi `too many connections` xuất hiện rồi mới tính.

### JUnit 5 cho ngân sách connections

Một phép tính thuần Java 17 giúp phát hiện sai cấu hình trước deployment:

~~~java
import java.util.List;

record PoolAllocation(
        String role, int instances, int maxPerInstance) {

    long ceiling() {
        if (instances < 0 || maxPerInstance < 0) {
            throw new IllegalArgumentException(
                    "Pool allocations must be non-negative");
        }
        return Math.multiplyExact(
                (long) instances, (long) maxPerInstance);
    }
}

final class ConnectionBudget {

    static long totalCeiling(
            List<PoolAllocation> allocations) {
        return allocations.stream()
                .mapToLong(PoolAllocation::ceiling)
                .reduce(0L, Math::addExact);
    }

    static void requireWithinBudget(
            long allowedForBatch,
            List<PoolAllocation> allocations) {

        if (allowedForBatch < 0
                || totalCeiling(allocations) > allowedForBatch) {
            throw new IllegalStateException(
                    "Batch connection ceiling exceeds budget");
        }
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class ConnectionBudgetTest {

    @Test
    void acceptsNormalTopology() {
        var pools = List.of(
                new PoolAllocation("manager", 2, 10),
                new PoolAllocation("worker", 12, 10));

        assertEquals(140L,
                ConnectionBudget.totalCeiling(pools));
        assertDoesNotThrow(() ->
                ConnectionBudget.requireWithinBudget(160, pools));
    }

    @Test
    void rejectsRollingSurge() {
        var pools = List.of(
                new PoolAllocation("manager", 2, 10),
                new PoolAllocation("workers-old", 12, 10),
                new PoolAllocation("workers-new", 4, 10));

        assertEquals(180L,
                ConnectionBudget.totalCeiling(pools));
        assertThrows(IllegalStateException.class,
                () -> ConnectionBudget.requireWithinBudget(
                        160, pools));
    }
}
~~~

Code tính **trần có thể xảy ra**, chưa khẳng định thực tế 100% connection được mở, cũng không thay kiểm thử database saturation và failure recovery.

## 17. Vì sao pending cao? Chẩn đoán theo causal chain

Cần đặt metric pool và DB trên cùng time axis.

| Dấu hiệu | Giả thuyết | Kiểm chứng tiếp |
| --- | --- | --- |
| Active=max, pending tăng, acquisition p95 tăng | Pool starvation | Connection usage timer, cursor count, DB query/transaction age |
| Active=max, DB lock wait cao | Giao dịch đang chờ locks | `pg_blocking_pids`, hot keys, commit duration |
| Active=max, CPU DB thấp, `idle in transaction` nhiều | Giữ transaction không thực hiện công việc | Query/transaction age, code path, HTTP call trong transaction |
| Total<max, pending tăng, lỗi tạo connection | DB không cấp thêm session/network hoặc pool đang khởi tạo | Hikari exception log, `max_connections`, network/TLS, proxy quota |
| Idle nhiều, active thấp, job chậm | Bottleneck không nằm ở pool đó | CPU/GC, source pool khác, broker, input cạn |
| Timeout tăng ngay sau rolling deploy | Tổng pool ceiling tăng đột biến | Pod surge/replicas và sessions theo `application_name` |
| Source pool full, target pool nhàn | Reader cursor giữ connections hoặc source query chậm | Step lifecycle, reader type, fetch size, source IO |
| Target pool full, source pool nhàn | Writer/DB target transaction bottleneck | Batch SQL, indexes, locks, WAL/IO |
| JobRepository pool full, business pools bình thường | Metadata contention/commit frequency | Chunk size, partition counts, repository DB lock/IO |
| Hikari leak warnings nhưng active hạ sau Step | Cursor giữ connection lâu theo thiết kế | Borrow stack, `open/close`, query latency |
| Hikari leak warnings không bao giờ hạ | Connection thực sự chưa được trả | Raw JDBC path, exception cleanup, resource leak profiling |

### Thứ tự điều tra gợi ý

1. Xác định tên pool thực sự gây pending/timeout, không dựa vào dashboard tổng.
2. Kiểm tra active/idle/total/max và connection acquisition p95.
3. Xem usage duration và thread stack: connection bị giữ vì cursor, transaction hay HTTP/network?
4. Đối chiếu `pg_stat_activity`/`pg_blocking_pids` để tìm slow SQL, lock hoặc `idle in transaction`.
5. Đo nguồn đọc, writer commit duration, `JobRepository` metadata latency và throughput hữu ích.
6. Kiểm tra tăng worker mới, rollout overlap, autoscaler, cron jobs hoặc các ứng dụng khác dùng chung DB.
7. Chỉ sau đó mới cân nhắc thay pool max, chunk size, reader strategy, index hoặc concurrency.

**Nguyên tắc:** đừng tăng `maximumPoolSize` như phản xạ đầu tiên. Nếu DB đã saturated, pool lớn hơn thường chỉ chuyển hàng đợi **từ application pool sang database locks/CPU/IO**, làm timeout và tail latency khó dự đoán hơn.

## 18. Connection leak thật, connection bị giữ lâu và lỗi transaction boundary

Hai sự cố có biểu hiện Hikari active tăng nhưng cách sửa khác nhau:

- **Connection leak:** code mượn connection và không trả lại vì thiếu `close()`/cleanup, nhất là trên exception path. Khi job dừng, active vẫn có thể không hạ về mức bình thường.
- **Long-held connection:** code giữ connection có chủ đích nhưng lâu hơn mức pool budget cho phép; ví dụ cursor reader mở suốt Step hoặc transaction chứa một lời gọi HTTP chậm. Không nhất thiết có leak, nhưng vẫn gây starvation.

### Anti-pattern: mượn JDBC connection rồi không đóng

~~~java
import javax.sql.DataSource;
import java.sql.Connection;

final class BrokenDao {

    private final DataSource dataSource;

    BrokenDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void process() throws Exception {
        Connection connection = dataSource.getConnection();
        // Nếu query/mapper ném exception:
        // connection.close() không được gọi.
        connection.prepareStatement("SELECT 1").execute();
        // Thiếu finally/try-with-resources.
    }
}
~~~

Với code JDBC thuần không nằm trong transaction do Spring quản lý, cần dùng try-with-resources cho connection, statement, result set:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

final class SafeRawJdbcDao {

    private final DataSource dataSource;

    SafeRawJdbcDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    int readOne() throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps =
                     connection.prepareStatement("SELECT 1");
             ResultSet rs = ps.executeQuery()) {

            if (!rs.next()) {
                throw new SQLException("No result");
            }
            return rs.getInt(1);
        }
    }
}
~~~

**Ranh giới quan trọng:** bên trong `@Transactional` do Spring quản lý, tự gọi `dataSource.getConnection()` và `close()` không phải lúc nào cũng khớp connection bound vào transaction. Ưu tiên `JdbcTemplate`/Spring Data hoặc `DataSourceUtils` theo contract của Spring thay vì tự quản lý thô trong transaction.

### Anti-pattern: làm HTTP I/O khi giữ transaction JDBC

~~~java
// Mô hình nguy hiểm: giữ transaction quá lâu.
// @Transactional
// void processOne(Order order) {
//     jdbc.update("UPDATE ...");
//     paymentClient.callRemoteApi(order);  // Có thể đợi 30 giây.
//     jdbc.update("UPDATE ...");
// }
~~~

Nếu transaction đã mượn connection, HTTP call có thể kéo dài connection usage, giữ locks, làm `active=max` và `pending` tăng. Cách sửa có thể là tách external call khỏi transaction, dùng outbox, hoặc lập state machine rõ với idempotency — nhưng phải giữ business consistency, không đơn giản bỏ transaction.

### Phân biệt bằng dữ liệu

| Kiểm tra | Leak thật | Long-held hợp lệ nhưng gây áp lực |
| --- | --- | --- |
| Active hạ sau job/step hoàn tất? | Thường không hạ nếu connection chưa trả | Thường hạ khi `ItemStream.close()`/transaction kết thúc |
| Hikari leak warning? | Có thể có | Cũng có thể có |
| Query/transaction age | Có thể dài hoặc không | Thường thấy long transaction/cursor/lock |
| Thử giảm concurrency | Đỡ triệu chứng | Đỡ triệu chứng |
| Fix gốc | Đóng đúng resource trên mọi path | Rút transaction, đổi reader hoặc tăng capacity có đo lường |

`leakDetectionThreshold` hỗ trợ điều tra nhưng **không** thu hồi resource cho ứng dụng. Đừng đặt threshold thấp đến mức log của cursor reader hợp lệ trở thành nhiễu lớn và che mất leak thật.

## 19. Pool starvation do checkout lồng nhau

Một dạng deadlock/starvation tinh vi xảy ra khi các thread **đã mượn connection A**, sau đó mỗi thread tiếp tục cần connection B từ **chính cùng pool** trong khi không trả A.

Giả sử pool có max 4:

~~~text
Thread 1: giữ Connection A1, chờ Connection B1
Thread 2: giữ Connection A2, chờ Connection B2
Thread 3: giữ Connection A3, chờ Connection B3
Thread 4: giữ Connection A4, chờ Connection B4

Pool max = 4
Active = 4
Idle = 0
Pending = 4

Không thread nào hoàn thành để trả A.
~~~

Tình huống này có thể xuất hiện do:

- Mở cursor với connection riêng rồi cần writer connection từ cùng pool.
- Transaction lồng nhau, nhất là `PROPAGATION_REQUIRES_NEW` có thể đòi connection thứ hai khi outer transaction vẫn giữ connection đầu.
- DAO A gọi DAO B dùng một `DataSource` khác trỏ về cùng DB và pool wiring không được hiểu đúng.
- Application giữ connection trong request/tasklet rồi tạo asynchronous task cũng cần connection và chờ task đó hoàn tất.

### Hướng thiết kế

1. **Tránh checkout lồng nhau** khi có thể; giảm thời gian giữ connection.
2. Tách source/target pool hoặc sử dụng reader strategy khác khi hai vai trò cạnh tranh nhau.
3. Sizing pool dựa trên **maximum simultaneous connections per thread** cùng lịch thực thi xấu nhất, không theo một connection/thread.
4. Không dùng `REQUIRES_NEW` trong mọi item chỉ để “chắc chắn có commit”: nó tăng transaction/connection pressure và có thể phá atomicity.
5. Nếu một task đang giữ DB connection, không block chờ một task khác cũng cần cùng pool mà không có capacity đủ.
6. Luôn thử high-load và restart/crash khi nhiều worker mở cursor/transaction đồng thời.

Pool starvation không nhất thiết hiển thị `pg_stat_activity` có nhiều query đang chạy: phần lớn connection có thể ở trạng thái idle/transaction, còn thread Java đang chờ pool. Vì vậy cần thread dump, Hikari pending và DB session state.

## 20. Retry, restart, failover và kết nối tăng đột biến

Trong scaling Spring Batch, một failure không chỉ thay đổi `StepExecution`; nó còn thay đổi demand trên DB connections.

### Khi một worker chết

- Connection vật lý của node cũ thường sẽ được DB/OS/proxy phát hiện đóng sau các timeout tương ứng; thời điểm giải phóng DB session không phải lúc nào trùng chính xác với lúc pod biến mất.
- Pod mới có thể khởi tạo pool mới và mở connections trước khi DB kịp dọn session cũ.
- Nếu manager redeliver partition/chunk do mất reply, hai worker có thể cùng cố ghi, tăng connection demand và lock contention.
- `JobExecution` có thể còn `STARTED` khi process chết; phải khôi phục metadata theo quy trình đúng, không sửa tùy tiện bảng `BATCH_*`.
- Reader cursor mới phải mở lại từ **durable checkpoint** trên cùng snapshot/partition; connection cũ không di chuyển sang node mới.

### Retry storm làm pool cạn thế nào?

~~~mermaid
flowchart TD
    A["DB transaction chậm"] --> B["Active gần max"]
    B --> C["Pending / timeout"]
    C --> D["Nhiều chunk FAILED hoặc retry"]
    D --> E["Nhiều attempts / thêm connections cần mượn"]
    E --> B
    B --> F["Business goodput giảm"]
~~~

Các biện pháp cần kết hợp:

- Retry có **backoff và jitter**, giới hạn attempts; tránh retry tức thời với cùng hot row/locked resource.
- Bounded executor và rate limiter để không vượt DB budget.
- Không scale-out số pod chỉ vì queue depth tăng nếu pool/DB đã bão hòa.
- Phân biệt `connectionTimeout` với lỗi SQL business. Retry mọi `SQLException` vô hạn có thể che bug, data constraint hoặc deadlock thiết kế.
- Ưu tiên idempotent writer, giữ input snapshot bất biến để replay không làm sai output.

### Rolling deploy có thể làm pool ceiling vượt ngân sách

Kubernetes/ASG có thể tạo instance mới trước khi xóa instance cũ. Nếu mỗi worker pod có pool max 12, từ 8 pod tăng tạm lên 12 pod làm ceiling của riêng worker tăng từ 96 lên 144. Cần tính cả manager, JobRepository, sidecars, migration và các workload khác.

**Đừng tăng `max_connections` trên DB như thao tác chữa cháy duy nhất.** Nó có thể tăng memory/session overhead và đẩy bottleneck sang CPU/IO. Xác minh nguyên nhân, lập rollback plan, kiểm tra reserved sessions và capacity thật.

## 21. Benchmark connection usage và fault injection có kiểm soát

Đo connection usage trên cùng **snapshot/version** và workload đại diện, không chỉ chạy job nhỏ vài chục giây rồi kết luận về peak pool.

### Kế hoạch thí nghiệm

1. Chốt snapshot có phân phối ID, payload và xử lý tương đương production.
2. Chạy baseline `1 worker`, đo `goodput`, p95 chunk duration, Hikari `active/idle/pending` và DB sessions/locks.
3. Tăng số worker theo từng mức `1 → 2 → 4 → 8 → 12`; giữ pool configs và DB quota nhất quán trừ khi đó là biến đang thử.
4. Ở mỗi mức, giữ steady-state đủ lâu để quan sát lock, GC, connection lifetime và retry sau warm-up.
5. Benchmark nhiều chunk sizes `100/200/500/1000`, không đổi đồng thời cả worker count lẫn chunk size nếu muốn tìm nguyên nhân.
6. So sánh `JdbcCursorItemReader` và `JdbcPagingItemReader` trên cùng input, có restart test.
7. Kiểm tra `pg_stat_activity` và connection usage timer khi load đã ổn định.
8. Gây lỗi PostgreSQL tạm thời hoặc tăng lock wait **trong staging**; quan sát pool timeout/retry/recovery.
9. Kill một worker giữa chunk; restart cùng identifying parameters, giữ partition mapping và đối soát output.
10. Giả lập rolling deploy có surge để phát hiện vượt connection budget.
11. Đối soát source–target business keys/version và các side effects theo contract.
12. Lặp lại test nhiều lần, lưu cấu hình và time series, không chỉ báo một throughput peak.

### Ma trận kỳ vọng

| Tình huống | Triệu chứng quan sát | Điều cần xác minh |
| --- | --- | --- |
| Pool size quá nhỏ so với checkout demand | Pending/acquisition tăng | Bottleneck thực ở pool, DB còn headroom |
| DB đã đạt trần dù pool còn chỗ | Lock/IO/CPU DB tăng | Tăng pool không cải thiện goodput |
| Cursor lâu sống | Source active cao kéo dài | Connection đóng khi step kết thúc/failed |
| Paging đọc theo offset lớn | Source query latency tăng về cuối | Index, page/order và connection usage |
| Retry storm | Timeout/rollback tăng | Backoff/rate limit không làm bùng lượng attempts |
| Pod rolling surge | DB sessions tăng khi pod overlap | Topology budget tính cả old+new |
| Worker crash khi writer đã commit | Chunk có thể replay | Unique business key, output đúng |
| JobRepository chậm | Metadata writes/commit latency tăng | Chunk size và repository pool phù hợp |
| External API chậm trong transaction | Pool active cao nhưng DB không chạy SQL | Thu gọn transaction và outbox |
| Connection leak thật | Active không hạ sau cleanup | Tài nguyên được đóng đúng exception path |

### Tiêu chí PASS

Một cấu hình chỉ được xem là tốt khi:

- Business goodput và end-to-end job SLA đạt, không phải chỉ `readCount/s`.
- `pending`/acquisition latency/timeouts nằm trong ngưỡng vận hành đã công bố, kể cả trong recovery.
- Không vượt DB connection budget trong steady-state, burst và rolling deployment.
- Không tăng bất thường `idle in transaction` hoặc long-lived locks.
- Output sau restart/retry đầy đủ, đúng version, không double side effect.
- Sử dụng CPU/IO và p95/p99 latency còn headroom cho workload khác.

## 22. Alert và dashboard: nhìn đúng resource tại đúng mức

Một dashboard tốt nên cho phép drill-down theo **pool → JVM/pod → database server → StepExecution/business output**.

| Tín hiệu | Mức xem | Khi nào đáng cảnh báo |
| --- | --- | --- |
| `active/max` | Pool/instance | Bám sát max kéo dài **và** có queue/latency tăng |
| `pending` | Pool/instance | Liên tục >0 dưới tải thực, tăng qua nhiều cửa sổ |
| Acquisition p95 | Pool | Vượt ngưỡng cho phép của chunk, không chỉ một spike |
| Connection timeouts/min | Pool | Có timeout lặp trong vài phút |
| Connection usage duration p95 | Pool | Tăng không tương xứng với workload hoặc step lifecycle |
| `pg_stat_activity` sessions | DB/application | Tiệm cận ngân sách đã cấp, đặc biệt lúc rollout |
| `idle in transaction` count/age | DB | Transaction treo qua ngưỡng đã thống nhất |
| DB lock wait/deadlocks | DB | Cùng thời điểm goodput giảm và retry tăng |
| `JobRepository` commit latency | Repository pool/DB | Metadata trở thành bottleneck |
| Writer unique commits/s | Business output | Throughput hữu ích suy giảm kéo dài |
| Worker/pod count | Cluster | Autoscaler/rollout làm connection ceiling tăng |
| Retry/DLQ count | Job/broker | Backlog và failure amplification |

### Alert minh họa bằng PromQL

Cảnh báo pool có pending kéo dài (chỉ minh họa biểu thức; labels/threshold phải điều chỉnh):

~~~promql
max_over_time(
  hikaricp_connections_pending{pool="batch-orders"}[5m]
) > 0
~~~

Đây là điều kiện **từng có pending trong 5 phút**, chưa đủ nói pending **duy trì liên tục**. Nếu muốn đo pending tồn tại suốt cửa sổ, xét:

~~~promql
min_over_time(
  hikaricp_connections_pending{pool="batch-orders"}[5m]
) > 0
~~~

Cần lưu ý time series vắng mặt/scrape gaps, metric label khác nhau giữa exporter và tần suất scrape. Một alert vận hành tốt thường kết hợp pending lâu, acquisition p95 và timeout rate, thay vì tự động cấp thêm 10 pods khi thấy một pending thread.

### Tránh high-cardinality metrics

Không đặt `orderId`, `customerId`, `chunkId` hay `JobExecutionId` vào nhãn metric Prometheus nếu mỗi run sinh giá trị mới không giới hạn. Dùng labels có cardinality thấp như `application`, `pool`, `workerRole`, `environment`; các ID cụ thể đi vào log/tracing có phân quyền.

## 23. Runbook khi Hikari pending và JDBC timeouts tăng

Khi người vận hành thấy `SQLTransientConnectionException`, “Connection is not available” hoặc `pending > 0` liên tục:

1. **Nhận diện pool bị tác động:** source, target, repository hay pool ứng dụng khác? Kiểm tra pool name và instance labels.
2. **Xác nhận metric và timeline:** active/idle/total/max/pending, acquisition latency, timeout rate và thời điểm bắt đầu.
3. **Kiểm tra concurrency thực:** số pod/JVM, worker threads, parallel steps, partition counts, rollout surge và các job chạy chung DB.
4. **Đối chiếu DB sessions:** `pg_stat_activity`, `state`, `wait_event_type`, `xact_start`, `pg_blocking_pids`; xác định locks, long transactions hoặc source query chậm.
5. **Tìm long-held connection:** `JdbcCursorItemReader`, transaction giữ khi gọi API, raw JDBC không đóng, `REQUIRES_NEW` lồng nhau, cursor/file stream.
6. **Kiểm tra DB còn headroom?** CPU, IOPS, WAL, lock waits, memory, server-side connection quota và các app khác.
7. **Xem `JobRepository`:** nhiều chunk commit nhỏ, metadata contention, `StepExecution` trạng thái thiếu hoặc retry.
8. **Giảm áp lực an toàn nếu cần:** tạm hạn chế dispatch, giảm worker slots, tắt retry storm, áp backoff; không giết DB session tùy tiện.
9. **Chọn điều chỉnh theo nguyên nhân:** sửa leak, rút transaction, đổi reader strategy, tăng index effectiveness, tăng pool **nếu DB thực sự còn capacity**, hoặc phân bổ lại connection budgets.
10. **Triển khai có kiểm soát:** một canary hoặc staging workload đại diện, theo dõi steady-state và failure/recovery.
11. **Đối soát đầu ra:** nếu job đã fail/restart, kiểm tra missing/extra/version mismatch và business side effects.
12. **Ghi lại RTO, root cause, saturation point và thay đổi cần thiết** vào runbook và regression test.

### Những việc không nên làm

- Tăng `maximumPoolSize` trên mọi pod cùng lúc mà không nhân với số replicas.
- Bật autoscaling worker theo backlog khi database đã bão hòa.
- Nâng `connectionTimeout` từ 10 giây lên 2 phút rồi coi sự cố đã hết.
- Tự động `pg_terminate_backend` mọi session `idle in transaction` mà không hiểu business transaction và recovery.
- Đóng DataSource singleton trong lúc Step vẫn chạy để “giải phóng” connection.
- Chỉnh bảng `BATCH_*` hoặc xóa checkpoint để ép restart sau pool outage.
- Coi `Hikari active == PostgreSQL active query` và tối ưu sai tầng.
- Giữ HTTP call chậm trong JDBC transaction rồi chỉ tăng pool để che vấn đề.

## 24. Bài tập tình huống: 12 worker, ba pools và một đợt rolling deploy

Một hệ Spring Batch local/remote partitioning có topology:

~~~text
PostgreSQL max_connections = 180
DBA reserved by policy for others/admin = 35
Batch connection budget = 145

Manager: 2 JVM, each maxPoolSize = 10
Workers: 10 JVM, each maxPoolSize = 10
Utilities: 1 JVM, maxPoolSize = 8

During deployment: 4 new worker JVM start
before 4 old worker JVM stop.
~~~

Trong một test steady-state, Hikari metrics trên một worker điển hình:

~~~text
Source pool:
  active = 10, idle = 0, pending = 7, max = 10

Target pool:
  active = 3, idle = 7, pending = 0, max = 10

PostgreSQL:
  many long-running reads and a few locks
  database CPU = 45%
  output goodput trending down
~~~

*Lưu ý quan trọng:* topology đầu nói “mỗi JVM có maxPoolSize 10” như **một pool chung**, trong khi bảng metric minh họa bên dưới lại có **source và target pools riêng**. Đây là hai giả định khác nhau cần phát hiện và làm rõ khi tính ngân sách.

**Câu hỏi:**

1. Nếu mỗi instance chỉ có đúng **một pool**, trần kết nối của batch trước rollout là bao nhiêu?
2. Trong cùng giả định một pool, trần kết nối khi thêm bốn worker tạm thời là bao nhiêu? Có vượt budget 145 không?
3. Nếu mỗi worker thực tế có **hai pool riêng** max 10, còn manager/utilities giữ một pool như cũ, phải tính lại trần steady-state thế nào?
4. Với worker source `active=10,pending=7` và target `active=3,pending=0`, nên tăng source pool ngay không?
5. CPU DB 45% có chứng minh DB đang còn 55% capacity để tạo thêm query không?
6. `JdbcCursorItemReader` có thể làm source pool active cao suốt Step dù source đang không có query chạy không?
7. Vì sao tăng `connectionTimeout` không sửa được nguồn gốc contention?
8. Nếu worker crash rồi pod mới mở pool trước khi DB giải phóng session cũ, điều gì có thể xảy ra?
9. Sau một JDBC timeout làm step FAILED, restart có cần snapshot/partition ổn định và idempotent writer không?
10. Hãy đề xuất hai metric từ Hikari, hai query/metric DB và một phép đo business để quyết định concurrency phù hợp.
11. Nếu `idle in transaction` tăng mạnh, nên xem code pattern nào trước?
12. Nếu worker chuyển từ cursor sang paging, bạn sẽ đo những gì để chứng minh thay đổi tốt hơn?

### Gợi ý đáp án

- **(1)** `2*10 + 10*10 + 1*8 = 128` connections ceiling.
- **(2)** `128 + 4*10 = 168`, vượt batch budget `145` là **23**, dù nhỏ hơn cấu hình `max_connections=180`. Budget dành riêng cho batch vẫn phải tôn trọng.
- **(3)** `2*10 + 10*(10+10) + 1*8 = 228`, vượt ngân sách **83** trước cả rollout. Không lấy pool max của một DataSource làm trần toàn JVM.
- **(4)** Chưa đủ bằng chứng; kiểm tra connection usage duration, cursor lifecycle, slow SQL, locks và DB quota; có thể giảm concurrency hay đổi reader thay vì tăng max.
- **(5)** Không. DB có thể đã bão hòa I/O, locks, connections, memory hoặc index hot spot dù CPU thấp.
- **(6)** Có, connection được giữ bởi reader/cursor mà không tương đương query đang sử dụng CPU liên tục.
- **(7)** Chỉ làm thread chờ lâu hơn, không tăng số transaction/query DB có thể hoàn tất.
- **(8)** Connection ceiling/session usage tăng tạm thời, dễ gặp `too many connections` hoặc timeouts.
- **(9)** Có. Checkpoint cần input/reader order ổn định; replay khi business commit và metadata khác transaction cần idempotency.
- **(10)** Hikari: `pending` và acquisition p95; DB: `pg_stat_activity` transaction age và `pg_blocking_pids`/lock waits; business: unique committed items/s và reconciliation.
- **(11)** Transaction mở xuyên HTTP call, raw connection không trả, blocking operation khi đang giữ JDBC resource hoặc xử lý ngoại lệ thiếu rollback.
- **(12)** Đo peak/steady active+pending, acquisition duration, source query p95, DB read IO, CPU, heap, goodput, correctness/restart và connection usage khi có nhiều worker.

## 25. Checklist trước production

- [ ] Đã xác định tên và vai trò **tất cả** JDBC pools: source, target, JobRepository, manager, worker, utility.
- [ ] Tính trần connection theo **số instance × số pool × maxPoolSize**, gồm rollout surge và failover.
- [ ] Giữ quota/headroom cho app khác, admin, monitoring và DB server limits; không coi `max_connections` là target performance.
- [ ] Hiểu `active`, `idle`, `total`, `pending`, `max`, timeout, acquisition/usage duration và các hạn chế của gauge.
- [ ] Xác minh tên metric thật của HikariCP/Micrometer trên endpoint đã bảo vệ.
- [ ] Có dashboard theo **pool và instance**, nối với `pg_stat_activity`, lock waits, DB I/O, `JobRepository` và business goodput.
- [ ] Reader type, connection lifetime, cursor/`fetchSize` và cách đóng `ItemStream` đã được kiểm thử.
- [ ] Không tự khẳng định một worker chỉ cần đúng một connection; đã đo peak checkout theo concurrency.
- [ ] Thread safety được kiểm tra nếu dùng multi-threaded step; `@StepScope`/partition context ổn định nếu partitioning.
- [ ] Writer transaction manager, JDBC DataSource và metadata repository wiring được hiểu rõ.
- [ ] Nếu có nhiều DataSource, failure window giữa business commit và repository checkpoint có writer idempotency.
- [ ] `connectionTimeout`, `validationTimeout`, `maxLifetime`, `keepaliveTime`, `minimumIdle` có cấu hình phù hợp hạ tầng.
- [ ] Leak warnings được phân biệt với connection hợp lệ nhưng lâu sống.
- [ ] Không có raw JDBC resource leak, transaction mở xuyên HTTP call hoặc checkout lồng nhau vượt capacity.
- [ ] Đã benchmark nhiều worker counts, chunk sizes, cursor/paging, long soak và test lúc DB/locks chậm.
- [ ] Có bounded concurrency, retry backoff, không autoscale vô hạn khi DB saturates.
- [ ] Đã thử worker crash, manager restart, rolling deploy và double-side-effect prevention.
- [ ] Metrics có cardinality thấp, quyền xem DB query/Actuator endpoints được quản lý.
- [ ] Runbook chỉ dẫn phân loại **pool starvation vs DB saturation vs connection leak**.
- [ ] Kết quả nghiệp vụ được reconcile; `COMPLETED` và throughput graph không thay thế correctness.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps và partitioning.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobExecution`, `StepExecution`, `ExecutionContext` và restart state.
- [Spring Batch Reference – Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk transaction và commit.
- [Spring Batch Reference – JDBC Cursor Item Reader](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): cursor vs paging, driver hints và reader lifecycle.
- [Spring Batch Reference – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` và checkpoint.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): Batch observability.
- [Spring Batch 5.2 Reference](https://docs.spring.io/spring-batch/reference/5.2/index.html): builder APIs và cấu hình dòng 5.x.
- [HikariCP README](https://github.com/brettwooldridge/HikariCP): ý nghĩa pool settings, lifecycle, timeout và sizing.
- [Spring Boot – Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC DataSource, HikariCP và connection configuration.
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, JDBC pool metrics và endpoint.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/concepts.html): counter, timer, gauge và tags.
- [Prometheus Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase` và `histogram_quantile`.
- [PostgreSQL – Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, waits và database statistics.
- [PostgreSQL – Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): `max_connections` và reservation.
- [PostgreSQL – Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock waits, deadlocks và blockers.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries, resource management và propagation.

## Ghi nhớ

**Database connection usage phải được đo ở cả ứng dụng lẫn database, trên toàn cụm chứ không chỉ một pool của một pod.** Khi scale Spring Batch, hãy phân biệt Hikari **active/idle/pending/max/timeouts**, PostgreSQL **session/transaction/lock state** và **business goodput**. Số worker, số pool, cursor reader giữ connection lâu, chunk transaction, `JobRepository` và rolling deploy cùng ảnh hưởng tới ngân sách. **Thêm JDBC connections không tương đương tăng DB capacity**; nếu locks, IO, transaction lifetime hoặc leak là nút thắt, pool lớn hơn có thể làm hệ kém ổn định. Duy trì snapshot/partition/checkpoint đúng cho restart, writer idempotent và bounded concurrency; chọn pool size từ benchmark + headroom, rồi kiểm chứng lại end-to-end output. **Scaling thành công là đạt throughput bền vững với connection usage kiểm soát được và dữ liệu nghiệp vụ chính xác.**
