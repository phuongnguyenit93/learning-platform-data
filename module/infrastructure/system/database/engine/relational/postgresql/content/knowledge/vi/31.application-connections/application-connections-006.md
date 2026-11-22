# Connection pool, giới hạn kết nối và sizing theo tải

Một API Java xử lý hàng nghìn HTTP requests mỗi phút nhưng chỉ cần thực thi SQL trong một phần rất ngắn của mỗi request. Nếu ứng dụng mở kết nối PostgreSQL mới cho từng request, chi phí xác thực, khởi tạo phiên, TLS và backend process tăng mạnh. Nếu giữ **một kết nối riêng cho mỗi request**, cơ sở dữ liệu có thể cạn slot và RAM khi traffic tăng. Nếu cấp pool quá nhỏ, requests chờ lấy connection, timeout dù database vẫn còn CPU rảnh. Ngược lại, pool quá lớn có thể làm nhiều truy vấn tranh CPU, locks và I/O, khiến throughput **giảm** dù số kết nối tăng.

**Connection pool** là cơ chế tái sử dụng các kết nối đã thiết lập, giới hạn lượng công việc đồng thời đi vào PostgreSQL và tạo hàng đợi ngắn tại tầng ứng dụng. **Sizing** là quá trình chọn kích thước dựa trên **workload, số bản sao ứng dụng, thời gian giữ connection, tài nguyên database, truy vấn chậm, ngân sách độ trễ và khả năng phục hồi**, không phải một con số “10/50/100 connection là luôn đúng”.

Bài này dùng PostgreSQL, Java/JDBC, HikariCP và PgBouncer làm ví dụ. Các tham số và output là minh họa có chú thích, không thay cho số đo của server cụ thể.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả lifecycle của kết nối PostgreSQL và vì sao nhiều backend sessions tốn tài nguyên.
2. Phân biệt **client connection**, **server connection**, **physical JDBC connection**, **logical connection lease** và **active SQL query**.
3. Hiểu `max_connections`, reserved connection slots và giới hạn do server/proxy/managed service áp dụng.
4. Lập ngân sách kết nối cho nhiều service, replicas, background jobs, admin và các ứng dụng khác.
5. Ước lượng concurrency bằng `L = λ × W` (Little's Law) với các đơn vị phù hợp.
6. Phân biệt pool size, request concurrency, DB-active time, transaction duration và connection hold time.
7. Cấu hình HikariCP cơ bản, close connection đúng cách, xử lý acquisition timeout và connection leak.
8. Phân biệt PgBouncer **session pooling**, **transaction pooling** và các giới hạn session state.
9. Chọn timeout ở application, JDBC, pooler và PostgreSQL không mâu thuẫn.
10. Đọc `pg_stat_activity`, `pg_stat_database`, `pg_locks` và metric pool để xác định bottleneck.
11. Thiết kế load test, chọn pool size qua latency/throughput/saturation thay vì chỉ nhìn số kết nối.
12. Xử lý overload, connection storms, failover, autoscaling, transaction kéo dài và SQL chậm.
13. Thiết kế bảo mật, giới hạn per-role/per-database, health checks và readiness.
14. Áp dụng một quy trình sizing có số liệu, công thức, phép thử và checklist triển khai.

> **Lưu ý về phiên bản:** PostgreSQL có các tham số reserved connection slots được bổ sung/thay đổi theo phiên bản (ví dụ `reserved_connections` ở các phiên bản mới); một số managed services có thêm reserved slots riêng. HikariCP/PgBouncer cũng có hành vi thay đổi theo phiên bản và cấu hình. Luôn kiểm tra tài liệu tương ứng với phiên bản đang chạy trước khi áp dụng một giá trị cụ thể.

## 2. Vì sao mở kết nối mới rất đắt?

Với một phiên kết nối PostgreSQL thông thường:

```text
Client TCP/TLS
      │
      ▼
 PostgreSQL server
      │
      ├── authentication / access checks
      ├── backend process cho session
      ├── session state và memory context
      ├── transaction state
      ├── prepared statements / cursors / temp objects
      └── câu SQL và phản hồi
```

PostgreSQL dùng **process-per-connection** cho các client sessions thông thường. Mỗi session có chi phí thiết lập và một phần bộ nhớ/tài nguyên; có thêm backend process không đồng nghĩa server có thêm CPU cores.

Nếu mỗi request đều mở/đóng connection:

- Tăng số lần TCP/TLS/authentication.
- Tăng process startup/teardown.
- Tăng độ trễ cold path.
- Tạo burst CPU/memory khi traffic đột biến.
- Có thể đụng `max_connections` dù SQL mỗi request rất ngắn.

Pool giữ một số physical connections sẵn sàng và **cho nhiều request mượn tuần tự**. Một connection tại một thời điểm không thể đồng thời phục vụ hai giao dịch độc lập như hai session khác nhau.

## 3. Định nghĩa chính xác các loại kết nối

| Khái niệm | Ý nghĩa |
|---|---|
| HTTP request | Một yêu cầu vào API; có thể không cần SQL |
| JDBC `Connection` | Đối tượng client đại diện một session/connection hoặc wrapper do pool cấp |
| Physical connection | Kết nối mạng thực tới PostgreSQL hoặc pooler |
| Pool lease / borrowed connection | Khoảng thời gian application giữ một connection từ pool |
| Idle pool connection | Connection đang rảnh trong pool ứng dụng và có thể tái sử dụng |
| Active pool connection | Đang được ứng dụng mượn, **không chắc đang chạy SQL** |
| PostgreSQL backend | Process/session server tương ứng một physical server connection |
| Active SQL query | Backend đang thực thi một command, không đồng nghĩa mọi leased connection |
| Waiting query | SQL bị chặn bởi locks, I/O, client hoặc resource khác |
| PgBouncer client connection | Connection từ app tới PgBouncer |
| PgBouncer server connection | Connection từ PgBouncer tới PostgreSQL |

### Một điểm then chốt

**Pool active ≠ PostgreSQL query active.** Một thread có thể mượn connection, chờ gọi HTTP khác, chờ lock hoặc xử lý dữ liệu trong Java. Nó vẫn chiếm pool lease trong khi database có thể không làm việc hữu ích.

## 4. Bốn đại lượng concurrency khác nhau

Để sizing, cần tách:

1. **Request concurrency**: bao nhiêu HTTP requests cùng đang xử lý.
2. **Connection checkout concurrency**: bao nhiêu requests/tasks đang giữ connection.
3. **Database active query concurrency**: bao nhiêu backend thực thi SQL.
4. **PostgreSQL server connection count**: bao nhiêu sessions được mở, kể cả idle.

Ví dụ:

```text
200 HTTP requests đang xử lý
 ├── 150 đang CPU/HTTP/cache/JSON, chưa mượn DB
 ├── 30 đang chờ connection pool
 └── 20 đang mượn connection
       ├── 8 chạy SQL
       ├── 6 chờ lock
       └── 6 xử lý trong Java trước commit
```

Đây chỉ là một ví dụ minh họa. Không thể suy ra nên đặt `maximumPoolSize=200` từ request concurrency=200.

## 5. Một mô hình request lý tưởng

```text
request
  │
  ├── validate input / authorize
  │
  ├── borrow DB connection
  │      ├── BEGIN
  │      ├── SQL 1
  │      ├── SQL 2
  │      └── COMMIT / ROLLBACK
  │
  ├── return connection to pool
  │
  └── serialize response / return HTTP
```

**Giữ connection càng ngắn càng tốt**, nhưng phải đáp ứng tính đúng đắn transaction. Đừng mượn kết nối quá sớm hoặc giữ nó trong lúc gọi external HTTP, ngủ chờ, tính toán CPU nặng nếu các bước đó không cần giữ DB transaction.

## 6. Connection pool làm được và không làm được gì?

Pool giúp:

- Tái sử dụng connections.
- Chặn tổng lượng connection mỗi process/instance.
- Giới hạn concurrency đi vào database.
- Cho requests chờ theo timeout có kiểm soát.
- Quản lý lifecycle/health/retirement.
- Expose metrics active/idle/pending.

Pool **không** tự:

- Tăng CPU/RAM của PostgreSQL.
- Chữa SQL thiếu index hay truy vấn giữ lock lâu.
- Bảo đảm transaction không rò.
- Cấp quyền tenant.
- Giữ transaction sống an toàn qua connection bị failover.
- Bảo đảm mọi server connection đều đang làm việc hữu ích.
- Tự biết pool size tốt nhất trên toàn cluster.

Thậm chí một pool quá lớn có thể làm tail latency tăng do lock contention, scheduler thrash và I/O queue.

## 7. PostgreSQL max_connections

Kiểm tra:

```sql
SHOW max_connections;

SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name = 'max_connections';
```

`max_connections` đặt giới hạn số **kết nối đồng thời** PostgreSQL chấp nhận theo cơ chế server; không nên coi đó là target số backend mong muốn sử dụng thường xuyên.

### Điều không nên làm

Không thấy lỗi `too many connections` rồi lập tức nâng `max_connections` lên 1000. Nếu server chỉ có vài cores và RAM hạn chế, lượng backend lớn có thể gây:

- Chi phí memory/scheduler cao.
- Tăng số truy vấn tranh tài nguyên.
- Giảm khả năng dành connection cho vận hành.
- Tăng nguy cơ memory pressure khi nhiều queries đồng thời.

Thay đổi `max_connections` thường cần **restart PostgreSQL** và nên được kiểm soát cùng cấu hình tài nguyên/managed service.

## 8. Reserved connection slots

Trong PostgreSQL có các slot ưu tiên để một số roles có thể kết nối khi những clients thông thường đã chiếm gần hết giới hạn.

Thử xem các tham số hiện có trên server:

```sql
SELECT name, setting, context
FROM pg_catalog.pg_settings
WHERE name IN (
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections'
)
ORDER BY name;
```

`superuser_reserved_connections` dành phần kết nối ưu tiên cho superusers theo ngưỡng server.

Ở phiên bản có `reserved_connections`, có thêm nhóm reserved slots cho roles có quyền thích hợp như `pg_use_reserved_connections`, tách với nhóm dành riêng superuser.

### Đừng suy luận availability chỉ từ 100 - 3

Các managed providers, replication clients, monitor sessions và vai trò ứng dụng có thể tạo thêm giới hạn. Ngay cả khi `max_connections=100`, “ứng dụng luôn có thể dùng 97 kết nối” là giả định nguy hiểm.

Hãy chừa **operational headroom**, không cố ép pool chiếm gần sát ngưỡng.

## 9. Giới hạn theo role và database

PostgreSQL có thể áp giới hạn kết nối cho role hoặc database:

```sql
-- Chỉ chạy với quyền phù hợp, trên role tồn tại.
-- ALTER ROLE app_user CONNECTION LIMIT 20;
-- ALTER DATABASE application_db CONNECTION LIMIT 80;
```

Các giới hạn này khác `max_connections`, áp dụng theo quy tắc cho role/database và có thể khiến client bị từ chối **trước khi global max_connections đầy**.

### Kiểm tra metadata

```sql
SELECT
    rolname,
    rolcanlogin,
    rolconnlimit
FROM pg_catalog.pg_roles
ORDER BY rolname;

SELECT
    datname,
    datconnlimit,
    datallowconn
FROM pg_catalog.pg_database
ORDER BY datname;
```

`-1` thường biểu thị không đặt giới hạn riêng ở cấp thuộc tính này. Dù thế, global/server/provider constraints vẫn tồn tại.

## 10. Ngân sách kết nối không chỉ có ứng dụng chính

Một server có thể phục vụ:

```text
                      PostgreSQL
                         ▲
        ┌────────────────┼────────────────┐
        │                │                │
    API service      Background jobs    BI / admin
      replicas        workers/pools      scripts
        │                │                │
     HikariCP          pool              psql
        │                │                │
        └────────────────┼────────────────┘
                         │
                monitoring / ops
```

Ngoài HTTP APIs còn có scheduled jobs, migration tools, ETL, BI, administrator, poolers, failover monitoring và những client khác.

Nếu nhiều ứng dụng dùng chung server, phải tính **tổng physical server connections** dưới tải và khi autoscale, không chỉ maximumPoolSize của một pod.

## 11. Công thức ngân sách cơ bản

Giả sử:

- `Cmax`: `max_connections`.
- `Creserve`: slots cần để dành cho roles ưu tiên/khẩn cấp theo cấu hình.
- `Cother`: mức budget cho các kết nối không thuộc ứng dụng đang sizing.
- `Cheadroom`: dự phòng hữu dụng cho burst, vận hành và rủi ro sai số.

Ngân sách sơ bộ cho ứng dụng:

\[
C_{\mathrm{app,budget}}
= C_{\max} - C_{\mathrm{reserve}}
- C_{\mathrm{other}} - C_{\mathrm{headroom}}
\]

Nếu có `N` replicas, mỗi replica có pool tối đa `P`, cần:

\[
N \times P \le C_{\mathrm{app,budget}}
\]

Với nhiều services:

\[
\sum_{i=1}^{k} N_iP_i
+ C_{\mathrm{jobs}}
\le C_{\mathrm{app,budget}}
\]

Đây là **upper-bound budgeting** cho các pool trực tiếp mở server connections, chưa phải công thức chọn số kết nối **tối ưu throughput**. Nếu có PgBouncer transaction pooling, phải tính cả pool phía PgBouncer và mọi đường kết nối bypass pooler.

## 12. Ví dụ tính budget cho nhiều replicas

Giả sử PostgreSQL có ngân sách thiết kế:

| Thành phần | Số connections |
|---|---:|
| `max_connections` | 120 |
| Slots ưu tiên/khẩn cấp dự kiến | 5 |
| Monitor, BI, admin và client khác | 20 |
| Headroom tránh hoạt động sát trần | 20 |
| **Budget còn cho API** | **75** |

Nếu API có **5 replicas**, mức pool trần theo budget:

\[
P \le \left\lfloor \frac{75}{5} \right\rfloor = 15
\]

Nếu chọn `maximumPoolSize=12`:

\[
5 \times 12 = 60
\]

Ứng dụng dùng tối đa 60 server connections trong giả định **mỗi pod chỉ có một pool và kết nối trực tiếp database**; còn 15 connections trong phần budget API và các khoản dự phòng đã tách.

### Tại sao không tự chọn 15?

15 chỉ là **trần budget** của một cách phân bổ. Nếu benchmark cho thấy throughput tối ưu ở 8–10 và 12 gây queueing tại database, hãy chọn pool nhỏ hơn.

### Khi autoscale lên 8 replicas

`8 × 12 = 96`, vượt budget API 75. Pool size/pod phải được tính với **max replicas cho phép**, hoặc có cơ chế điều chỉnh ngân sách tổng khi scale, không chỉ lúc hiện có 5 replicas.

## 13. Điểm nguy hiểm: nhiều pools trong một process

Một Spring Boot service có thể có:

- Một `DataSource` primary.
- Một `DataSource` read replica.
- Một pool cho background jobs.
- Một pool do thư viện khác tạo riêng.
- Một pool khác trong test/health tooling.

Không đủ nói “mỗi pod Hikari maximumPoolSize=10” nếu thực tế có ba HikariDataSources, mỗi pool max 10.

### Kiểm tra

Liệt kê tất cả datasource/pool instances theo:

```text
service / deployment / pod
  ├── primary DB pool maximum
  ├── replica DB pool maximum
  ├── batch DB pool maximum
  └── external processes connecting same DB
```

Budget theo từng **database endpoint**; nếu primary và replica là hai server khác nhau, đừng cộng sai mọi pool vào một giới hạn, nhưng vẫn phải tính riêng mỗi server.

## 14. Connection count không phải active work

Quan sát:

```sql
SELECT
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY state;
```

Các trạng thái thường gặp:

- `active`: backend đang thực thi query, có thể đồng thời chờ I/O/lock.
- `idle`: chờ lệnh tiếp theo từ client.
- `idle in transaction`: transaction mở nhưng không chạy query ở thời điểm quan sát.
- `idle in transaction (aborted)`: transaction lỗi còn mở, cần rollback.
- `state IS NULL`: có thể do quyền/đối tượng/version hoặc thông tin không sẵn.

### Không suy diễn “idle là xấu”

Idle sessions trong pool là bình thường: đó là các physical connections được giữ để reuse. Điều đáng quan tâm là quá nhiều idle connections làm cạn slot, hoặc `idle in transaction` giữ transaction/snapshot/locks và gây vacuum/lock issues.

## 15. Mỗi connection tốn bao nhiêu RAM?

Không có một số MB cố định, dùng chung mọi phiên bản/server/workload.

Chi phí liên quan:

- Backend process và memory contexts.
- Session/query state.
- Prepared statements, portal/cursors, temporary data.
- Executor memory cho sort/hash/aggregate khi query chạy.
- Backend-local caches và extension state.
- Shared memory được dùng chung, không cộng nguyên `shared_buffers` cho mỗi backend.

### Sai lầm với work_mem

Không tính đơn giản:

`total_RAM = max_connections × work_mem`

rồi kết luận đó là toàn bộ memory. `work_mem` là budget cho **mỗi operation** như sort/hash trong một query, và một query/plan có thể có nhiều operations, cùng parallel workers và những memory allocations khác. Thực tế peak memory dưới concurrency cần đo theo workload.

### Nhưng cũng không bỏ qua work_mem

Khi tăng số query chạy đồng thời, tổng memory cho executor operations có thể tăng mạnh. Cùng một `work_mem` có thể hợp lý ở 8 active queries nhưng gây pressure khi 100 queries chạy song song.

## 16. Little's Law: công thức nền tảng

Trong một hệ thống ổn định, công thức:

\[
L = \lambda W
\]

với:

- `L`: số công việc **trung bình đang ở trong hệ thống**.
- `λ`: throughput đến/hoàn thành trung bình theo đơn vị công việc mỗi giây.
- `W`: thời gian trung bình một công việc ở trong **phạm vi đang đo**, tính theo giây.

Nếu đo riêng thời gian application **giữ DB connection**:

\[
\text{avg leased connections}
\approx
\text{DB-using requests per second}
\times
\text{mean connection hold time}
\]

Chỉ áp dụng đúng nếu `λ` và `W` đo trên **cùng tập công việc và cùng ranh giới**, hệ thống tương đối ổn định. Nếu một request mượn connection nhiều lần, phải đếm các **leases/second** hoặc tổng thời gian giữ phù hợp, không chỉ requests/second rồi nhân nhầm.

## 17. Ví dụ Little's Law

Giả sử một API:

- 120 requests/second cần DB.
- Mỗi request **mượn connection đúng một lần**.
- Mean hold time 50 ms = 0,05 s.

Khi ổn định:

\[
L \approx 120 \times 0.05 = 6
\]

Nghĩa là trung bình khoảng **6 leased connections** trên toàn scope của traffic được đo.

### Không lập tức đặt pool=6

Con số 6 **không phản ánh**:

- Burst và variability.
- Tail latency (p95/p99 hold time).
- Locks và slow queries.
- Headroom cho jobs.
- Tác động khi 1 pod nhận traffic không đều.
- Khả năng server xử lý khi tăng concurrent queries.

Sizing cần thử 8, 12, 16... theo benchmark và traffic phân phối thực tế. Không suy ra một hệ số an toàn cố định từ công thức trên.

## 18. Nếu request giữ connection 500 ms?

Vẫn 120 requests/second, nhưng mean hold time tăng từ 50 ms lên 500 ms:

\[
L = 120 \times 0.5 = 60
\]

Chỉ một transaction giữ connection lâu hơn 10 lần đã làm nhu cầu leased connections trung bình tăng 10 lần, nếu throughput giữ nguyên.

### Cách xử lý tốt hơn việc tăng pool

Hỏi **vì sao connection được giữ nửa giây?**

- SQL chậm?
- Chờ row lock?
- Query trả quá nhiều rows và Java stream chậm?
- Application gọi HTTP bên trong transaction?
- Framework mở transaction quá sớm?
- Có `idle in transaction`?

Đôi khi giảm hold time từ 500ms xuống 100ms làm tăng khả năng phục vụ hơn tăng pool từ 20 lên 100.

## 19. Mean, p95 và tail latency

Một workload có 99% transactions giữ connection 10ms và 1% giữ 5 giây có thể có mean không quá lớn nhưng tail/queueing rất khác.

Các số nên đo:

- Mean/p50/p95/p99 **connection acquisition time**.
- Mean/p95/p99 **connection hold time**.
- SQL query duration và wait events.
- Pool active/idle/pending.
- Database CPU/I/O/lock waits.
- Error/timeout rate.

### Little's Law không tự chọn p99 pool size

Little's Law dùng **mean**, không phải công thức lấy p99 hold time nhân throughput rồi lập luận sẽ đáp ứng p99 latency. Để xét tail, cần load test với distribution, burst và service-time variability.

## 20. Queueing là một cơ chế bảo vệ, không chỉ là lỗi

Nếu pool có 12 connections và 30 requests cùng lúc cần connection:

```text
12 được cấp connection
18 đợi trong acquisition queue
  ├── có slot trả về trước deadline → tiếp tục
  └── vượt connectionTimeout → trả lỗi
```

Chờ có kiểm soát giúp không dồn toàn bộ 30 queries vào database trong cùng thời điểm.

### Nhưng queue quá dài là tín hiệu quá tải

Hàng đợi chờ lâu có thể khiến HTTP requests chiếm threads, memory và thời gian. Cần đặt:

- Pool acquisition timeout.
- HTTP request deadline.
- Queue/request concurrency limit.
- Retry/backpressure policy.

Pool không nên là **hàng đợi vô hạn** để che một database bị nghẽn.

## 21. Pool size và throughput: không đơn điệu

Hình dung ba trường hợp:

| Pool size | Có thể xảy ra | Cần đo |
|---|---|---|
| Quá nhỏ | Requests chờ pool dù DB có tài nguyên | Pending, acquisition latency, CPU DB |
| Vừa đủ | DB đủ bận, queue ngắn, throughput tốt | Throughput, p95/p99, saturation |
| Quá lớn | SQL cạnh tranh CPU/I/O/locks; tail tăng | CPU, wait events, lock waits, TPS |

**Đừng coi “nhiều connections hơn” đồng nghĩa “nhanh hơn”.** Nếu bottleneck là disk hoặc row lock, tăng pool chỉ làm thêm workers chờ cùng tài nguyên.

## 22. Quá tải được biểu hiện ở tầng nào?

| Tầng | Triệu chứng | Giải pháp thường xem trước |
|---|---|---|
| HTTP | Request queue, thread exhaustion | Concurrency limits, backpressure |
| Application pool | Pending tăng, connection timeout | Hold time, pool size và budget |
| PgBouncer | Client waiting, thiếu server slots | Server pool sizing, long transactions |
| PostgreSQL sessions | `too many connections` | Tổng pool budgets, reserved slots |
| CPU | 100% CPU, latency tăng | SQL optimization, active concurrency |
| I/O | Read/write wait, temp spills | Indexes, memory plan, disk capacity |
| Locks | Long waiting queries | Transaction scope, indexing, contention |
| WAL | Write/fsync pressure | Batch design, write workload tuning |

Một phép tăng `maximumPoolSize` chỉ có ích nếu nó xử lý **đúng bottleneck**, đồng thời không làm nghẽn tầng sau.

## 23. HikariCP: application-side JDBC pool

HikariCP là một JDBC connection pool phổ biến trong Java/Spring.

Ví dụ tạo `HikariDataSource`:

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig config = new HikariConfig();
config.setPoolName("orders-primary");
config.setJdbcUrl(
    "jdbc:postgresql://db.internal:5432/ordersdb"
);
config.setUsername(System.getenv("DB_USER"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(12);
config.setMinimumIdle(4);
config.setConnectionTimeout(2_000);
config.setIdleTimeout(600_000);
config.setMaxLifetime(1_800_000);

HikariDataSource dataSource = new HikariDataSource(config);

// Trong ứng dụng thật, lifecycle của DataSource do DI/container quản lý.
// dataSource.close() lúc ứng dụng shutdown.
```

Các giá trị trên **chỉ để minh họa**. URL/credentials/timing cần cấu hình theo triển khai, TLS, proxy, network timeout và load test. Không ghi password thật vào source code hoặc logs.

## 24. Các tham số HikariCP quan trọng

| Property | Vai trò | Sai lầm phổ biến |
|---|---|---|
| `maximumPoolSize` | Trần physical connections trong pool | Cấp 100 cho mỗi pod rồi nhân nhiều pods |
| `minimumIdle` | Mức idle mà pool cố duy trì theo cấu hình | Dùng lớn không cần thiết, chiếm slots khi rảnh |
| `connectionTimeout` | Thời gian tối đa chờ mượn connection từ pool | Nhầm với timeout chạy SQL |
| `idleTimeout` | Quản lý retirement của idle connections khi cấu hình cho phép | Mong nó giảm fixed-size pool ngay |
| `maxLifetime` | Tuổi thọ tối đa của physical connection trong pool | Đặt dài hơn giới hạn network/server dẫn đến stale connections |
| `keepaliveTime` | Tùy cấu hình, kiểm tra/giữ sống các idle connections | Nhầm với long-running query timeout |
| `validationTimeout` | Giới hạn thời gian validation | Dùng như request deadline |
| `leakDetectionThreshold` | Cảnh báo connection bị giữ lâu | Coi log là bằng chứng leak chắc chắn |

**Lưu ý:** HikariCP khuyến nghị mô hình pool kích thước ổn định trong nhiều trường hợp; `minimumIdle` mặc định có thể khiến pool hoạt động gần fixed-size tùy version và configuration. Khi tối ưu, hiểu rõ sự khác nhau giữa **max** và **min idle** thay vì chỉ nhìn tên property.

## 25. Connection.close() với pool có nghĩa gì?

Với connection lấy từ Hikari:

```java
try (Connection conn = dataSource.getConnection()) {
    // Dùng conn trong phạm vi cần thiết.
}
```

`conn.close()` trên đối tượng connection wrapper của pool **thường trả lease về pool**, không bắt buộc đóng TCP socket vật lý. Pool quyết định khi nào physical connection được tạo lại hoặc retirement.

### Cách nguy hiểm

```java
Connection conn = dataSource.getConnection();
executeBusinessLogic(conn);
// Quên close trong nhánh exception.
```

Nếu không trả connection, pool sẽ dần hết slot, pending tăng và mọi request sau timeout.

### Cách đúng

Sử dụng `try-with-resources` hoặc transaction management của framework, bảo đảm close/rollback trong mọi nhánh.

## 26. JDBC transaction và vòng đời connection

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (PreparedStatement ps = conn.prepareStatement(
                "UPDATE orders SET status = ? WHERE order_id = ?"
        )) {
            ps.setString(1, "PAID");
            ps.setLong(2, 42L);
            ps.executeUpdate();
        }

        conn.commit();
    } catch (SQLException | RuntimeException ex) {
        conn.rollback();
        throw ex;
    }
}
```

Tên bảng `orders` ở đây giả định ứng dụng thật có schema tương ứng; trên lab có thể thay bằng tên qualified của bảng bạn đã tạo ở bài khác. Ví dụ tập trung vào **borrow, transaction, commit/rollback và return**.

### Cảnh báo transaction state

Nếu application quên commit/rollback rồi trả connection, hành vi reset có thể phụ thuộc pool/driver nhưng không nên dựa vào đó như thiết kế bình thường. Framework/pool có thể thực hiện cleanup, nhưng nghiệp vụ phải quản lý transaction boundary rõ ràng.

Đừng giữ connection trong một try block bao trùm việc gọi API bên ngoài lâu hàng giây nếu không cần giữ transaction.

## 27. Connection acquisition timeout khác query timeout

Ví dụ:

```text
Hikari connectionTimeout = 2s
PostgreSQL statement_timeout = 5s
HTTP request deadline = 8s
```

Các timeout này áp vào những bước khác nhau:

- **Pool acquisition:** chờ lấy connection.
- **Statement/query:** SQL đang thực thi; PostgreSQL có thể hủy statement khi quá thời gian.
- **Request:** tổng thời gian xử lý, gồm queue/network/DB.

Không suy rằng HTTP deadline 8 giây chắc chắn được đảm bảo chỉ vì đặt statement_timeout 5 giây: request có thể chờ pool 2 giây, gọi nhiều statements, hoặc bị ảnh hưởng network/app processing.

### Cần thiết kế ngân sách thời gian

Phải tính phần thời gian chờ và các bước ngoài DB. Một request có thể thực thi ba SQL statements, mỗi statement 5 giây, nên `statement_timeout=5s` không tự giới hạn toàn request ở 5 giây.

## 28. PostgreSQL statement_timeout

Kiểm tra:

```sql
SHOW statement_timeout;

SELECT current_setting('statement_timeout');
```

Trong transaction thực hành:

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';

SELECT pg_sleep(3);
-- Có thể bị hủy vì quá statement_timeout.

ROLLBACK;
```

### Ý nghĩa

`statement_timeout` giới hạn thời gian statement theo cơ chế PostgreSQL và phiên bản/protocol; khi bị hủy, transaction hiện tại có thể chuyển sang trạng thái lỗi và cần rollback.

Nên đặt timeout **theo workload/endpoint**, tránh một giá trị quá nhỏ cho mọi job migration/analytics hoặc quá lớn cho API latency-sensitive.

## 29. lock_timeout và idle_in_transaction_session_timeout

`lock_timeout` hạn chế thời gian chờ **một lock**; không phải tổng query time.

`idle_in_transaction_session_timeout` có thể kết thúc session đang ở trạng thái `idle in transaction` quá lâu; đây là một biện pháp phòng vệ khi ứng dụng quên kết thúc transaction.

Ví dụ:

```sql
BEGIN;
SET LOCAL lock_timeout = '750ms';
SET LOCAL statement_timeout = '4s';

-- Câu SQL tiếp theo chịu các giới hạn trong transaction.
SELECT 1;

COMMIT;
```

### Tránh cấu hình mâu thuẫn

Nếu `lock_timeout` lớn hơn hoặc bằng `statement_timeout`, nó có thể không có tác dụng thực tế cho một statement đã bị statement_timeout trước đó. Và nếu idle-in-transaction timeout cắt session đang bị giữ bởi client, pool/application phải xử lý connection bị đóng.

## 30. Connection lifetime và network idle timeouts

Một physical connection có thể bị đóng bởi:

- PostgreSQL backend/server restart.
- Network device/load balancer/firewall.
- Managed proxy hoặc pooler idle/server lifetime settings.
- TLS/network disruptions.
- Pool quyết định retire connection.

### Hikari maxLifetime

Khi cấu hình `maxLifetime`, thường nên đặt **ngắn hơn một giới hạn lifetime upstream đã biết**, với khoảng dự phòng phù hợp, để pool chủ động retire/recreate connection.

Nhưng giảm lifetime quá thấp sẽ gây connection churn, tăng TLS/authentication và tốn CPU. Không đặt một giá trị cực nhỏ để “cứ tái kết nối là an toàn”.

### Keepalive

Một keepalive/validation có thể phát hiện connection rảnh đã bị cắt, nhưng không cứu được transaction đang chạy trong failover. Tùy network và driver, có nhiều tầng TCP keepalive, pool keepalive và server-side timeout cần phối hợp.

## 31. PgBouncer: pooler phía database

HikariCP quản lý connections ở **process Java**. PgBouncer là một **connection pooler/proxy** thường được đặt giữa clients và PostgreSQL:

```text
       API pod A           API pod B           Batch workers
         Hikari              Hikari               Hikari
            \                  |                    /
             \                 |                   /
              └───────────── PgBouncer ──────────┘
                               |
                       server pool nhỏ hơn
                               |
                           PostgreSQL
```

Nếu có 200 client connections vào PgBouncer nhưng tại một thời điểm chỉ cần 30 server transactions đồng thời, **transaction pooling** có thể dùng ít server connections hơn nhiều, với điều kiện các transactions ngắn và workload tương thích.

### Quan trọng

Một PgBouncer instance cũng cần được sizing. Nếu triển khai **nhiều PgBouncer instances**, mỗi instance giữ server connections riêng. Không xem `default_pool_size=20` là giới hạn **20 server connections trên toàn cluster** khi có năm pooler nodes và nhiều database/user combinations.

## 32. Client pool và server pool khác nhau

| Tầng | Giới hạn thường thấy | Đo cái gì? |
|---|---|---|
| HikariCP pod | `maximumPoolSize` | Số physical connections từ pod tới endpoint |
| PgBouncer | `max_client_conn` | Số client connections PgBouncer chấp nhận |
| PgBouncer | `default_pool_size` và các giới hạn database/user | Số server connections cho một pool tương ứng |
| PostgreSQL | `max_connections` và reserved slots | Tổng server sessions có thể mở |

**`max_client_conn` không phải `max_connections` của PostgreSQL.** PgBouncer có thể chấp nhận nhiều client connections nhưng chỉ cấp số server connections thấp hơn để multiplex, tùy pooling mode.

### Kịch bản không có lợi ích multiplex

Nếu mọi ứng dụng mở transaction dài và giữ server connection hàng chục giây, PgBouncer transaction pooling không thể “nhả backend giữa transaction”. Server connections vẫn bị chiếm, client wait tăng.

## 33. Ba chế độ pooling của PgBouncer

| Pool mode | Khi nào server connection được gắn với client? | Tính tương thích |
|---|---|---|
| `session` | Trong suốt client session | Tương thích với nhiều session features hơn, multiplex kém |
| `transaction` | Trong thời gian transaction; trả lại sau ranh giới transaction | Multiplex tốt khi transactions ngắn, hạn chế session state |
| `statement` | Cho từng statement | Hạn chế mạnh, không phù hợp multi-statement transactions |

### Session pooling

Gần với cách PostgreSQL direct connection hoạt động. Các đặc tính gắn session như temporary tables, session settings, session-level advisory locks, LISTEN/NOTIFY có thể cần mode này hoặc kết nối trực tiếp.

### Transaction pooling

Một client có thể dùng server backend X trong transaction 1 và backend Y trong transaction 2. **Không giả định session state còn nguyên** khi chuyển ranh giới transaction.

### Statement pooling

Server connection được tái dùng giữa statements. Do không giữ backend cho một multi-statement transaction tùy ý, mode này rất hạn chế; không chọn làm mặc định chỉ vì nghe tối ưu hơn.

## 34. Ví dụ cấu hình PgBouncer

Đoạn dưới là **cấu hình minh họa**, không phải file production hoàn chỉnh:

```ini
[databases]
ordersdb = host=postgres.internal port=5432 dbname=ordersdb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 500
default_pool_size = 30
reserve_pool_size = 5
reserve_pool_timeout = 5
server_idle_timeout = 600
```

### Cảnh báo cấu hình

- Các giá trị, authentication source, TLS và đường dẫn phải điều chỉnh theo hạ tầng.
- `default_pool_size` thường áp dụng theo **pool key** (database/user, tùy cách cấu hình kết nối), không phải tổng server connections của toàn PgBouncer instance.
- `reserve_pool_size` có thể mở thêm server connections khi điều kiện chờ được đáp ứng; **cũng cần tính vào budget**.
- Nếu có hai PgBouncer instances, mỗi instance có thể tạo server pool riêng.
- `max_client_conn` cũng tác động đến file descriptors/memory của pooler.

Không copy cấu hình này ra production mà bỏ TLS, mạng riêng, quyền file auth và high-availability policy.

## 35. Tính tổng PgBouncer server connections

Giả sử hai PgBouncer instances, mỗi instance phục vụ:

- Hai database/user pools.
- Mỗi pool có `default_pool_size=20`.
- Có thể thêm `reserve_pool_size=5` khi tải tăng.

Trần thiết kế sơ bộ:

\[
2 \times 2 \times (20+5) = 100
\]

Đây là **budget giả định** nếu cả hai pool keys và cả hai PgBouncer instances cùng mở tới maximum tương ứng. Giới hạn theo database/user và các cài đặt khác có thể cắt mức thực tế.

### Sai lầm rất phổ biến

Đặt `default_pool_size=20` ở mỗi pooler rồi bảo “PostgreSQL chỉ có 20 connections”. Nếu nhiều users/database pools, pooler nodes, PgBouncer reserve slots và direct clients cùng tồn tại, tổng server sessions có thể cao hơn nhiều.

## 36. Transaction pooling và prepared statements

Nhiều JDBC drivers dùng **server-side prepared statements** để giảm parse/plan overhead sau số lần thực thi nhất định. Trong transaction pooling, transaction tiếp theo có thể chạy trên **backend PostgreSQL khác**, nơi prepared statement ở session trước chưa tồn tại.

### Phân biệt hai loại

- **SQL-level `PREPARE name AS ...`**: state gắn với backend session, thường không tương thích khi phụ thuộc tồn tại qua transactions trong PgBouncer transaction pooling.
- **Protocol-level named prepared statements**: PgBouncer các phiên bản mới có thể hỗ trợ **theo dõi/ánh xạ** khi cấu hình `max_prepared_statements` phù hợp; phải kiểm tra đúng phiên bản và tính năng.

### Không đưa ra quy tắc lỗi thời “mọi prepared statement đều không dùng được”

Với PgBouncer mới, một số protocol-level prepared statements có thể hoạt động trong transaction mode khi tính năng hỗ trợ được bật. Nhưng điều đó **không** khiến mọi session feature tương thích; SQL `PREPARE`, temporary tables, session locks hoặc LISTEN vẫn có semantics khác.

### Thiết kế tích hợp

Kiểm tra phiên bản pgJDBC, PgBouncer và cấu hình chuẩn bị statement; test cả:

1. Một connection chạy nhiều prepared queries.
2. Reconnect/failover.
3. Thay backend giữa transactions.
4. Schema migration làm plan stale.
5. Heavy concurrency và error/retry.

## 37. Transaction pooling và trạng thái session

Những tính năng cần đặc biệt chú ý:

| Feature | Vấn đề với transaction pooling |
|---|---|
| Session `SET` / session GUC | Giá trị có thể không còn trên backend của transaction kế |
| Temporary tables | Sống theo backend session, không bảo đảm gắn với cùng client |
| Session-level advisory locks | Lock gắn backend, không thể xem là lock của client qua nhiều transactions |
| `LISTEN/NOTIFY` subscription | LISTEN là session state; cần session affinity |
| Open cursors sống qua commit | Không thể giả định cùng backend ở transaction kế |
| SQL `PREPARE` | Prepared name thuộc backend session |
| Session-level role/search_path | Cần policy rõ để tránh state không nhất quán |

### Một khác biệt quan trọng

**Transaction-scoped state** như `SET LOCAL` trong một transaction có thể phù hợp với transaction pooling khi mọi lệnh liên quan chạy trong cùng transaction. **Session-scoped state** không được coi là bền vững giữa các transactions.

## 38. SET LOCAL và tenant context

Nếu ứng dụng dùng custom setting cho RLS/audit:

```sql
BEGIN;

SELECT set_config(
    'app.tenant_id',
    '10',
    true
);

SELECT *
FROM public.orders
WHERE tenant_id = 10;

COMMIT;
```

`true` của `set_config` chọn phạm vi **local to current transaction**.

### Vì sao cần BEGIN?

Nếu autocommit bật và câu `set_config(..., true)` được gửi riêng như một statement độc lập, transaction của statement đó kết thúc ngay; local setting không tự sống sang SELECT kế tiếp. Điều này dễ gây lỗi khi dùng PgBouncer transaction pooling hoặc dù kết nối trực tiếp.

### Quyền

`app.tenant_id` do client có thể đặt **không tự chứng minh tenant đã xác thực**. RLS/authorization phải được thiết kế dựa trên nguồn quyền đáng tin. Custom GUC không phải một chữ ký chống giả mạo danh tính.

## 39. LISTEN/NOTIFY và pool mode

Một service nhận PostgreSQL notifications thường dùng:

```sql
LISTEN order_events;
```

Lệnh này đăng ký listener trên **một backend session**. Nếu PgBouncer transaction pooling chuyển backend cho client giữa transactions, listener không còn là một session ổn định như application trông đợi.

### Khuyến nghị

Dùng **kết nối trực tiếp hoặc session pooling riêng** cho listener lâu dài. Không dùng connection thuộc pool request thông thường rồi giữ lease mãi chỉ để LISTEN mà không tính capacity.

Một listener cần reconnect/resubscribe sau failover và xử lý thông báo có thể bị mất; LISTEN/NOTIFY không phải durable message queue đảm bảo delivery.

## 40. Temporary tables và session affinity

Nếu một quy trình:

```sql
CREATE TEMP TABLE tmp_ids (...);
COMMIT;

SELECT * FROM tmp_ids;
```

trông đợi temporary table tồn tại trên **cùng PostgreSQL backend** ở transaction sau, nó không phù hợp với PgBouncer transaction mode.

### Các hướng khác

- Giữ cả quy trình trong một transaction khi semantics cho phép (cẩn thận `ON COMMIT` behavior).
- Dùng regular staging table với request_id/batch_id và cleanup.
- Chọn session pooling/direct connection cho workflow thật sự cần temp session state.
- Tái thiết kế query để dùng CTE, array, `unnest` hoặc set-based SQL.

Không vì temp table mà giữ transaction mở hàng phút nếu việc đó làm server pooler nghẽn.

## 41. Advisory locks và pooling

PostgreSQL có **session-level advisory locks** và **transaction-level advisory locks**.

Session-level lock sống theo backend session, không phù hợp khi client có thể chuyển backend sau mỗi transaction.

Transaction-level advisory lock gắn transaction, nên có semantics phù hợp hơn với transaction pooling **khi khóa và công việc liên quan diễn ra trong cùng transaction**.

### Chú ý

Advisory locks không tự bảo vệ tính đúng đắn nếu cùng tài nguyên có đường ghi khác không lấy lock. Đảm bảo lock key ổn định, transaction boundary hợp lý và timeout/deadlock strategy.

Không dùng `pg_advisory_lock` session-level qua transaction pool rồi nghĩ client có thể chắc chắn unlock ở transaction tiếp theo.

## 42. HikariCP phía trước PgBouncer: hai hàng đợi

Một kiến trúc có thể có:

```text
HTTP requests
   ↓
Hikari pending queue
   ↓
Hikari connection to PgBouncer
   ↓
PgBouncer client wait queue
   ↓
PgBouncer server connection
   ↓
PostgreSQL locks / CPU / I/O queue
```

Nếu pending tăng ở Hikari, chưa biết server có thiếu connection không: có thể toàn bộ Hikari connections đang bị kẹt trong hàng đợi PgBouncer.

### Cần theo dõi đồng thời

- Hikari `active / idle / pending`.
- Hikari acquisition latency.
- PgBouncer client waiters và server available.
- PostgreSQL active/idle/lock states.
- SQL latency và transaction hold time.

Một tầng queue báo lỗi có thể là **hậu quả** từ tầng sâu hơn, không phải nguyên nhân.

## 43. Có nên bỏ Hikari nếu đã có PgBouncer?

Không có câu trả lời duy nhất.

Giữ application pool có lợi:

- Giới hạn concurrency theo pod.
- Tái sử dụng connections tới PgBouncer.
- Hỗ trợ JDBC DataSource/transaction integration.
- Expose acquisition metrics.

Nhưng hai tầng pool có thể:

- Tăng số idle client connections.
- Thêm timeout/queueing layers.
- Tạo sự khác biệt giữa app-side connection và backend PG session.

### Điều quan trọng

Khi có PgBouncer transaction pooling, **Hikari maxPoolSize** là giới hạn connections **tới PgBouncer**, không trực tiếp là số backend postgres mà toàn hệ thống có thể mở. Server budget khi đó chủ yếu do PgBouncer pool settings và các kết nối trực tiếp quyết định.

Tuy nhiên, Hikari maxPoolSize vẫn giới hạn lượng công việc đồng thời từ mỗi pod và cần sizing theo workload.

## 44. Quan sát PgBouncer bằng console quản trị

Trên kết nối tới PgBouncer administrative database (khi tài khoản có quyền):

```sql
SHOW POOLS;
SHOW STATS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW CONFIG;
```

Các lệnh này thuộc **PgBouncer admin console**, không phải SQL trên PostgreSQL database thông thường.

### Cần chú ý ở SHOW POOLS

Tùy version, có các nhóm thông tin như:

- Client active/waiting.
- Server active/idle/used.
- Pool database/user.
- Waiting time statistics.

Tên cột/metrics có thể thay đổi theo PgBouncer version; đọc output schema của phiên bản đang dùng.

### Điểm điều tra

Nếu client waiting lớn nhưng PostgreSQL CPU thấp, có thể PgBouncer server pool size quá nhỏ, server connections bị giữ bởi transactions dài, hoặc một pool key bị giới hạn riêng.

## 45. Kiểm tra connections trong PostgreSQL

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY
    datname, usename, application_name, state
ORDER BY sessions DESC, datname, application_name;
```

### Vì sao application_name quan trọng?

Giúp phân biệt:

- API primary.
- Reporting service.
- Migration tool.
- BI/dashboard.
- PgBouncer backend connection.

Với transaction pooling, PostgreSQL có thể nhìn thấy kết nối server-side từ PgBouncer; cách application_name được chuyển tiếp/theo dõi tùy cấu hình. Không mặc định mọi PostgreSQL session đều map 1:1 một HTTP pod.

## 46. Các phiên đang giữ transaction quá lâu

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    now() - state_change AS time_in_state,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
  AND xact_start IS NOT NULL
ORDER BY transaction_age DESC NULLS LAST
LIMIT 30;
```

### Đọc kết quả

`idle in transaction` với transaction_age rất lớn là dấu hiệu cần điều tra. Transaction mở có thể giữ locks và snapshot, ảnh hưởng vacuum và tài nguyên; thời gian giữ connection thường cũng tăng.

### Cẩn thận khi chẩn đoán

Không tự `pg_terminate_backend` các sessions production chỉ vì chúng đứng đầu danh sách. Kiểm tra owner, loại job, migration/backup, business transaction và rollback impact trước khi hành động.

Một query active lâu có thể chờ lock, không phải chạy CPU liên tục.

## 47. Quan sát wait events

```sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

Một số nhóm:

- `Lock`: đang chờ lock; tăng pool có thể tăng số chờ.
- `IO`: chờ I/O theo event của phiên bản.
- `Client`: chờ client/đọc ghi network.
- `LWLock`: chờ lightweight lock nội bộ.

### Không quy đồng “active” với dùng CPU

Một backend `state='active'` có thể đồng thời có `wait_event_type='Lock'`. Đừng suy từ 50 active sessions rằng database đang tận dụng 50 CPU cores.

## 48. pg_stat_database: kết nối và transaction activity

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    deadlocks,
    temp_files,
    temp_bytes
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

`numbackends` cho số backend hiện tại kết nối tới database theo thống kê view; các bộ đếm khác thường là tích lũy từ lần reset thống kê.

### Không biến cumulative counters thành TPS

Muốn lấy transactions/second, cần đo **delta giữa hai thời điểm** rồi chia khoảng thời gian phù hợp, đồng thời kiểm tra có statistics reset không. Không lấy nguyên `xact_commit` rồi gọi nó là “TPS hiện tại”.

## 49. Connection pool metrics nên export

| Metric | Ý nghĩa |
|---|---|
| Pool active | Connections đang được borrow |
| Pool idle | Connections rảnh |
| Pool total | Active + idle tại một thời điểm |
| Pool pending/waiting | Threads/requests đang chờ connection |
| Acquisition time p50/p95/p99 | Thời gian chờ lấy connection |
| Connection usage/hold time p50/p95/p99 | Thời gian borrow trước khi return |
| Acquisition timeout count | Số request không lấy được connection đúng hạn |
| Connection creation/error count | Churn/DB auth/network issues |
| Pool capacity/max | Trần đã cấu hình |
| JDBC transaction duration | Có đang giữ connection lâu không? |

Với Spring Boot/Micrometer, tên metric có thể theo conventions của instrumentation/version, chẳng hạn các metric dưới namespace `hikaricp.connections.*`. Hãy xác nhận tên/labels thực tế trong deployment; không hard-code tên metric đoán được vào alert mà chưa có dữ liệu.

### Kết hợp metrics

**Pending tăng + DB CPU thấp** có thể do pool nhỏ/connection leak hoặc waiting ở PgBouncer/locks.

**Pending tăng + DB CPU cao + slow SQL** có thể do database saturation, tăng pool thường không phải lựa chọn đầu.

## 50. Leak detection: bằng chứng hay tín hiệu?

HikariCP có cấu hình `leakDetectionThreshold` để log khi connection bị borrow lâu hơn ngưỡng, nếu tính năng được bật.

Nhưng một transaction thật sự kéo dài có thể bị gắn cờ **false positive**. Ngược lại, một connection leak dưới ngưỡng ban đầu có thể chưa hiện ngay.

### Quy trình điều tra

1. Xem stack trace tại lúc borrow và thời gian giữ.
2. Tìm nhánh thiếu close/rollback.
3. Kiểm tra HTTP/network call trong transaction.
4. Kiểm tra streaming ResultSet, cursor, lazy ORM loading.
5. So với `pg_stat_activity`, `xact_start` và lock waits.
6. Tăng/giảm ngưỡng chỉ sau khi hiểu workload.

**Leak detection log không thay cơ chế resource management** như try-with-resources.

## 51. Connection lease có thể kéo dài dù SQL rất nhanh

Một anti-pattern:

```java
try (Connection conn = dataSource.getConnection()) {
    beginTransaction(conn);
    updateRow(conn);
    callSlowPaymentGateway();  // Ví dụ 4 giây mạng ngoài.
    commit(conn);
}
```

SQL `updateRow` có thể chỉ 10ms, nhưng connection bị giữ suốt 4 giây chờ payment gateway, đồng thời transaction có thể giữ locks.

### Hướng thiết kế

- Giảm transaction scope.
- Tách external calls khỏi DB transaction nếu nghiệp vụ cho phép.
- Dùng saga/outbox/idempotency cho quy trình nhiều hệ thống.
- Chỉ mở transaction khi thực sự cần.
- Không đặt lời gọi mạng ngoài trong critical section giữ lock nếu có thể tránh.

Một giao dịch tài chính đa hệ thống cần thiết kế nhất quán riêng; không tự tách transaction tùy tiện khiến nghiệp vụ mất atomicity mà không có phương án bù.

## 52. ORM và transaction bị mở quá sớm

Trong Spring/Hibernate:

```java
@Transactional
public Response handle(Request req) {
    validate(req);
    callExternalService();
    repository.save(...);
    renderLargeResponse();
    return response;
}
```

Không phải mọi framework đều borrow physical connection ngay đầu method; thời điểm checkout phụ thuộc transaction manager/ORM/connection acquisition mode. Nhưng nếu connection đã được lấy và giữ đến cuối transaction, external call/serialization có thể làm hold time tăng đáng kể.

### Cách tốt hơn

Xác định ranh giới transaction **tại đoạn DB cần atomicity**, đo thời gian thực tế mượn connection, và kiểm tra lazy loading có khiến SQL chạy muộn lúc view serialization không.

### Open Session in View

Một số cấu hình web ORM giữ persistence context qua phần render; điều này có thể tạo truy vấn DB ngoài phạm vi dự tính. Phải đo và quyết định policy, tránh leak hay N+1 queries, nhưng không đồng nhất mọi persistence session với một physical connection đang được borrow liên tục.

## 53. Long-running analytics dùng pool khác?

Một BI query vài phút có nhu cầu khác API OLTP 50ms.

Nếu dùng chung pool:

- Một số analytics tasks giữ tất cả connections lâu.
- API requests chờ pool dù query nghiệp vụ ngắn.
- Độ trễ p99 tăng mạnh.

### Giải pháp khả dĩ

- Separate pool/role cho reporting với concurrency thấp.
- Read replica cho workload đọc nếu chấp nhận replication lag.
- Queue/background processing cho reports.
- Statement timeout riêng.
- Materialized views/pre-aggregation theo requirements.

### Không phải miễn phí

Tách thành hai pools không tạo thêm capacity cho cùng một PostgreSQL primary. Vẫn cộng cả hai vào **server connection budget** và đo CPU/I/O chung.

## 54. Connection storms sau deploy/restart

Giả sử 30 pods cùng khởi động, mỗi pod cố tạo 20 idle connections:

\[
30 \times 20 = 600
\]

Nếu PostgreSQL chỉ cho phép khoảng 150 application sessions, nhiều kết nối thất bại ngay khi deployment đang warming.

### Biện pháp

- Budget trên max replicas **và thời điểm rollout overlap** (old + new pods).
- Giảm `minimumIdle` hoặc warm-up concurrency khi phù hợp.
- Jitter/backoff khi reconnect; tránh retry đồng bộ.
- Cấu hình startup/readiness không tạo connection storm.
- Dùng PgBouncer server pooling khi phù hợp.
- Dự trù kết nối của jobs/migrations cũng có thể chạy lúc deploy.

### Một điểm dễ quên

Rolling deployment có lúc **old pods chưa tắt nhưng new pods đã khởi động**. Nếu budget chỉ đủ cho steady-state 20 pods, overlap có thể vượt connection limit.

## 55. Autoscaling và giới hạn database

Autoscaler dựa trên CPU/HTTP queue có thể tăng pods khi traffic tăng. Nhưng nếu bottleneck là PostgreSQL, tăng pods:

1. Tăng tổng pool max.
2. Tăng số queries đồng thời.
3. Làm DB chậm hơn.
4. Khiến requests tiếp tục chậm.
5. Autoscaler lại tăng pods.

Đây là một **feedback loop bất lợi**.

### Các nguyên tắc

- Tính budget ở `maxReplicas`.
- Có concurrency/admission controls tổng thể.
- Điều chỉnh pool size theo scale policy hoặc dùng pooler server cap.
- Đo database saturation cùng HTTP service metrics.
- Autoscale không được xem là thay cho tối ưu SQL/index/transactions.

Thêm app replicas có thể giúp CPU Java, nhưng không tự tăng throughput của một primary PostgreSQL đã hết tài nguyên.

## 56. Chọn pool size bằng load test

Một quy trình thực tế:

1. **Xác định workload:** tỷ lệ read/write, queries/request, transaction duration, payload size, tenant mix.
2. **Đo baseline:** app metrics, pool metrics, `pg_stat_activity`, CPU, memory, I/O, lock waits.
3. **Xác định budget:** `max_connections`, reserved slots, other pools, max replicas và rollout overlap.
4. **Chọn các candidates:** ví dụ `maximumPoolSize=4, 8, 12, 16, 24`.
5. **Tạo tải đại diện:** warm-up, steady, burst, long-tail queries và jobs nền.
6. **Đo cùng SLO:** throughput thành công, p95/p99 latency, timeouts, errors, DB saturation.
7. **Chọn điểm cân bằng:** không tối đa hóa connections hoặc CPU.
8. **Kiểm thử failure:** restart DB, PgBouncer unavailable, mất network, deploy đồng thời.
9. **Đặt cảnh báo và rollback criteria:** nếu latency/timeout/DB load vượt ngưỡng.

### Không đo bằng một SQL SELECT 1 duy nhất

`SELECT 1` kiểm tra kết nối, không đại diện workload có JOIN, index scan, writes, lock contention và row count thực. Benchmark pool bằng SQL giả quá nhẹ có thể chọn pool rất lớn, thất bại ngay trên dữ liệu production.

## 57. Bảng kết quả giả định của một phép thử

Giả sử một API có SLO p95 ≤ 150ms. Bảng sau là **số liệu giả định để luyện cách quyết định**, không phải benchmark PostgreSQL thực:

| Pool/pod | Successful req/s | API p95 | DB CPU | Pending pool |
|---:|---:|---:|---:|---|
| 4 | 400 | 180ms | 45% | Cao |
| 8 | 650 | 95ms | 75% | Thấp |
| 12 | 700 | 100ms | 90% | Thấp |
| 24 | 680 | 260ms | 100% | Trung bình |

### Phân tích

- Pool 4 không đáp ứng SLO, còn DB chưa sử dụng nhiều: có thể thiếu concurrency từ ứng dụng.
- Pool 8 đạt độ trễ tốt và throughput khá, DB còn một phần headroom.
- Pool 12 có throughput cao hơn một chút nhưng CPU DB cao, cần đánh giá độ an toàn khi burst.
- Pool 24 làm CPU/latency xấu đi; tăng pool không cải thiện throughput.

Nếu yêu cầu tối đa chỉ 600 req/s, pool 8 có thể hợp lý hơn pool 12. Nếu cần 700 req/s liên tục, phải đánh giá thêm khả năng chịu burst/failover và có thể tối ưu SQL, tăng database capacity hoặc điều chỉnh workload.

### Không đọc “DB CPU 90%” như một kết luận tuyệt đối

Mức CPU phù hợp còn phụ thuộc SLO, I/O, headroom và contention. Với một hệ thống cần failover/peak traffic, 90% sustained CPU có thể quá sát ngưỡng; nhưng không có ngưỡng cố định dùng chung mọi nơi.

## 58. Một phương pháp thử sizing lặp lại được

Giữ cố định:

- Database instance/CPU/RAM/storage và cấu hình.
- Dữ liệu và phân bố tenants.
- App replicas và HTTP worker settings.
- SQL/index versions.
- Request mix và arrival pattern.
- Network path và PgBouncer settings.

Chỉ thay **pool size** một yếu tố tại một thời điểm, sau đó đo:

```text
throughput, successful/failed requests
request p50/p95/p99
pool acquire p50/p95/p99
pool lease/hold p50/p95/p99
pool active/idle/pending
DB active sessions/CPU/IO/locks
timeouts, WAL, transaction rollback
```

### Warm-up

Pool creation, JIT trong Java, caches, query plan caches và filesystem cache có thể ảnh hưởng giai đoạn đầu. Cần có warm-up hợp lý trước khi so sánh steady-state; đồng thời **đừng bỏ qua cold-start performance** khi sản phẩm thường xuyên scale/restart.

### Kết quả phải có tính tái lập

Chạy nhiều vòng và báo variation. Nếu hai ứng viên chênh 2% throughput nhưng độ nhiễu đo 10%, chưa thể kết luận ứng viên nào tốt hơn.

## 59. Phải kiểm tra nơi tạo tải có đủ mạnh

Một load generator yếu có thể không gửi đủ traffic để saturate ứng dụng/database. Khi đó pool size 8 và 24 cho kết quả gần giống nhau vì không hề có nhu cầu dùng trên 8 connections.

### Kiểm tra

- Load generator CPU/network.
- Actual arrivals vs requested target rate.
- Request timeouts/retries ở client.
- Connection reuse của HTTP client.
- Error handling và backpressure của load tool.

Một bài đo bị nghẽn bởi **công cụ tạo tải** không thể dùng để kết luận pool/database đang tốt.

## 60. Open-loop và closed-loop load generation

Hai cách phát sinh request:

- **Closed-loop:** một số clients gửi request tiếp theo sau khi request trước hoàn thành.
- **Open-loop:** gửi theo arrival rate mục tiêu dù latency thay đổi, trong khả năng load tool.

Khi hệ thống chậm, closed-loop có thể tự giảm request arrivals và làm kết quả có vẻ ổn hơn thực tế peak traffic. Open-loop có thể bộc lộ hàng đợi/timeout dưới arrival pressure nhưng cần load tool đủ mạnh.

### Ý nghĩa cho sizing

Để quyết định maximumPoolSize cho API có burst, phải đo arrival patterns gần thực tế, không chỉ một con số “100 concurrent users” với thời gian chờ nhân tạo không được kiểm soát.

## 61. Pool exhaustion và backlog

Giả sử Hikari có 12 connections:

```text
pool active = 12
pool idle = 0
pool pending = 45
connection acquisition p99 = 1900ms
connectionTimeout = 2000ms
```

Điều này nói ứng dụng đang **chờ để được cấp connection**. Nhưng chưa cho biết có nên tăng pool hay không.

### Hai khả năng

**A. DB CPU thấp, queries nhanh, nhiều request đồng thời:** pool có thể quá nhỏ so với mức server cho phép.

**B. DB CPU cao/lock waits lớn, transaction giữ connection lâu:** tăng pool có thể làm nhiều queries vào DB cùng lúc và latency xấu hơn.

Phải kết hợp pool metrics với `pg_stat_activity` và DB resource metrics trước khi quyết định.

## 62. Tính thời gian chờ và thời gian giữ tách biệt

Một request có thể có:

```text
200 ms chờ connection
 50 ms chạy SQL
 10 ms xử lý kết quả trong transaction
-----------------------------
260 ms phần liên quan DB
```

Nếu chỉ đo `SQL duration=50ms`, bạn có thể bỏ sót phần chờ pool 200ms, khiến API p95 xấu dù query nhanh.

### Cần đo đúng boundaries

- Chờ trước khi `getConnection()` trả về.
- Hold từ lúc borrow đến lúc close/return.
- Thời gian query và lock waits.
- Tổng request duration.

Không gọi `pool active time` là query time. Đặc biệt trong ORM, một connection có thể được mượn nhưng không thực thi SQL trong một phần thời gian.

## 63. Ưu tiên giảm thời gian giữ connection

Trước khi tăng pool, cân nhắc:

- Chỉ checkout khi sắp thực thi SQL.
- Trả connection trước khi làm việc CPU/network không cần DB.
- Index và tối ưu slow SQL.
- Giảm N+1 queries/round trips.
- Batch SQL phù hợp.
- Giảm lock contention/transaction duration.
- Tránh streaming result quá lâu trên connection OLTP.
- Tách long analytics sang resource pool riêng.

### Ví dụ định lượng

Với 200 DB leases/s:

- Mean hold 100ms → khoảng 20 concurrent leases.
- Mean hold 40ms → khoảng 8 concurrent leases.

Cải thiện duration giảm hơn một nửa nhu cầu connections trung bình **mà không tăng max_connections**, nếu throughput không đổi và giả định Little's Law phù hợp.

## 64. Query optimization trước connection scaling

Một query:

```sql
SELECT *
FROM orders
WHERE customer_id = $1
ORDER BY created_at DESC
LIMIT 50;
```

nếu thiếu index phù hợp có thể quét/sort nhiều dữ liệu.

Với bảng/sort thực, cân nhắc index:

```sql
-- Chỉ minh họa, sau khi xác nhận schema/workload:
-- CREATE INDEX ix_orders_customer_created
-- ON orders(customer_id, created_at DESC);
```

### Tác động gián tiếp đến pool

Nếu query giảm từ 400ms xuống 40ms, connection hold time và active DB demand có thể giảm, khiến một pool nhỏ hơn đủ dùng.

Không tạo index chỉ vì một ví dụ SQL: cần đo `EXPLAIN (ANALYZE, BUFFERS)` và write overhead trên dữ liệu thực. Query chạy ít vẫn có thể không đáng chi phí index.

## 65. Read replica và pool budgeting

Một số ứng dụng tách:

```text
Write pool → PostgreSQL primary
Read pool  → PostgreSQL replica
```

Ưu điểm có thể gồm:

- Chuyển một số read-only workload khỏi primary.
- Cô lập reports với OLTP writes.
- Có các pool budgets theo endpoint.

### Không quên consistency

Read replica có thể có **replication lag**, nên một request vừa ghi primary rồi đọc replica có thể chưa thấy dữ liệu mới. Cần routing, read-your-writes policy và fallback phù hợp.

### Connection counts

Primary và mỗi replica có giới hạn riêng. Pool đọc quá lớn vẫn có thể làm replica cạn memory/CPU, không chỉ là giải pháp “miễn phí” để giảm áp lực primary.

## 66. Multi-tenant fairness

Một tenant lớn có nhiều requests có thể chiếm đa số pool leases, khiến tenant nhỏ bị timeout dù tổng load còn có thể được điều tiết hợp lý.

Các cách:

- Per-tenant request rate/concurrency limits.
- Queue/admission control có fairness.
- Separate worker pools cho workload cực nặng.
- Query limits/timeouts theo lớp dịch vụ.
- Isolation ở database/replica khi thực sự cần.

### Một điểm quan trọng

Tạo **một Hikari pool cho mỗi tenant** có thể phá budget khi có hàng trăm tenants. Cần thiết kế phù hợp tenancy architecture và số endpoints; đừng dùng nhiều pools như phương án fairness mặc định.

## 67. Những lỗi PostgreSQL thường gặp khi quá tải kết nối

Một số SQLSTATE cần phân biệt:

| SQLSTATE | Tình huống |
|---|---|
| `53300` | `too_many_connections` |
| `08001` | `sqlclient_unable_to_establish_sqlconnection` |
| `08006` | `connection_failure` |
| `57P01` | `admin_shutdown` |
| `57014` | `query_canceled` (ví dụ statement timeout) |
| `40P01` | `deadlock_detected` |
| `40001` | `serialization_failure` |

### Không retry mọi lỗi giống nhau

- Connection failure khi transaction chưa commit có thể cần retry **toàn bộ operation** theo idempotency policy.
- Deadlock/serialization failure thường retry toàn transaction với backoff và giới hạn.
- Query canceled do timeout có thể phản ánh SQL quá chậm; retry tức thì có thể gây overload nặng hơn.
- Too many connections nên kích hoạt backpressure và xử lý capacity/pool budgeting, không tạo vòng reconnect storm.

Không dùng SQLSTATE để quyết định retry khi chưa hiểu liệu thao tác đã commit hay chưa.

## 68. Unknown commit outcome khi mất kết nối

Một request:

```text
BEGIN
UPDATE account
COMMIT
connection drops before client receives COMMIT result
```

Client không thể kết luận chắc chắn “giao dịch đã rollback” chỉ vì không nhận ACK của COMMIT. Server có thể đã commit rồi connection mới mất.

### Hệ quả cho retry

Đối với thao tác như “trừ tiền” hoặc “tạo đơn”, cần:

- Idempotency key.
- Unique business constraint.
- Cách tra lại kết quả theo request ID.
- Transaction retry policy có giới hạn.

Connection pool có thể thay connection hỏng, **nhưng không thể giải quyết ambiguity của commit outcome**.

## 69. Failover: pool cần phục hồi thế nào?

Khi primary PostgreSQL đổi node:

1. Existing physical connections có thể bị đóng.
2. Transactions đang mở thất bại; cần rollback/retry theo policy.
3. Connection pool phải phát hiện/evict stale connections.
4. DNS/proxy/endpoint routing chuyển sang node mới.
5. Nhiều clients có thể cùng reconnect.
6. Readiness của application cần phản ánh dependency khi phù hợp.

### Không giả định Hikari tự replay SQL

Pool làm nhiệm vụ quản lý kết nối, **không replay một giao dịch nghiệp vụ** đã chạy dở một cách an toàn. Retry chỉ ở tầng application với idempotency/authorization/transaction semantics đúng.

### Tránh connection storm sau failover

Backoff/jitter, warm-up có kiểm soát và max replicas budget giúp giảm áp lực vào primary mới.

## 70. Readiness vs liveness

Trong hệ thống container:

- **Liveness**: tiến trình ứng dụng có bị treo/không thể tự phục hồi hay không.
- **Readiness**: instance có thể nhận traffic một cách an toàn ở thời điểm hiện tại không.

Nếu readiness probe mỗi giây mở một PostgreSQL physical connection mới mà không qua pool hoặc khởi tạo toàn bộ datasource, nó có thể tạo thêm tải.

### Khuyến nghị

- Probe rẻ, có timeout và không tạo kết nối mới không cần thiết.
- Health checks dùng datasource/pool đang tồn tại theo cách phù hợp.
- Tránh mọi pods cùng thay đổi readiness liên tục chỉ vì một vài lần DB timeout.
- Phân biệt DB outage thực và một endpoint reporting chậm.

Không đánh đồng “PostgreSQL reachable” với “ứng dụng có đủ capacity cho traffic hiện tại”.

## 71. Khi PostgreSQL trả too many connections

Runbook:

1. Ghi thời điểm, application/service và SQLSTATE.
2. Đọc `max_connections`, reserved slots, role/database limits.
3. Xem số sessions theo `application_name`/`usename`.
4. Kiểm tra replicas hiện tại, rollout overlap, jobs, BI và pool max.
5. Kiểm tra idle vs idle-in-transaction vs active.
6. Xem PgBouncer pool keys/server connections nếu có.
7. Tìm service mới deploy hoặc pool thứ hai bị tạo ngoài ý muốn.
8. Áp dụng giảm concurrency/rollout/backpressure khi cần.
9. Chỉ tăng PostgreSQL limit sau khi tính CPU/RAM và restart impact.
10. Đặt alert để phát hiện budget vượt trước khi cạn slots.

### Không kết thúc sessions mù quáng

`pg_terminate_backend(pid)` có thể rollback giao dịch kinh doanh, gây retry storm hoặc ảnh hưởng migrations. Chỉ dùng khi đã xác định đúng đối tượng, quyền và blast radius.

## 72. Khi pool pending cao nhưng DB CPU thấp

Những nguyên nhân khả dĩ:

- Pool max quá nhỏ cho workload.
- Application giữ connection khi không chạy SQL.
- Pool leak hoặc transaction mở quá lâu.
- PgBouncer server pool bị giới hạn, dù DB CPU thấp.
- Kết nối chưa tạo đủ do network/authentication errors.
- Lock waits trên một nhóm row dù tổng CPU còn rảnh.
- Client-side thread/queue bottleneck.

### Cách phân biệt

Kiểm tra Hikari hold-time, stack traces, PgBouncer pools, `pg_stat_activity.state/wait_event`, số transactions chờ lock và connection creation errors.

**Không thể kết luận duy nhất từ CPU thấp rằng cứ tăng pool sẽ tốt.**

## 73. Khi DB CPU cao và pool không đầy

Nếu Hikari:

```text
active 6 / max 20
pending 0
```

nhưng PostgreSQL CPU 100%, có thể chỉ sáu queries đã đủ saturate server.

### Bước điều tra

- Top queries và execution plans.
- Index scans vs sequential scans.
- CPU-intensive operators: sorts, hash, JSON processing.
- N+1 SQL calls.
- Autovacuum/maintenance contention theo tình huống.
- CPU quotas/throttling của VM/container.

Tăng pool từ 20 lên 40 không giải quyết nguyên nhân này; thậm chí workload sau tăng có thể nặng hơn.

## 74. Khi Hikari báo connection leak

Runbook:

1. Kiểm tra logs có leak stack trace.
2. Xem connection lease duration.
3. Kiểm tra code paths thiếu try-with-resources.
4. Kiểm tra transaction bắt đầu trước external calls.
5. Kiểm tra ResultSet/Statement/cursor chưa được đóng.
6. So với `pg_stat_activity` idle-in-transaction và locks.
7. Thử tái hiện bằng integration test và dependency failure.
8. Sửa lifecycle, không chỉ tăng maximumPoolSize.

### Một cảnh báo false-positive

Một report hợp lệ giữ connection 2 phút trong khi leak threshold 30s có thể bị báo “leak”. Cần đặt đúng metric threshold và phân biệt job types.

## 75. Dùng retry/backoff khi pool bị nghẽn

Không có retry là mọi transient error đều thất bại, nhưng retry vô hạn/lập tức có thể **khuếch đại** overload.

### Thiết kế retry

- Retry **chỉ lỗi phù hợp**; không retry validation/authorization errors.
- Giới hạn số lần và deadline tổng.
- Exponential backoff với jitter.
- Ghi nhận circuit breaker/open state khi dependency outage.
- Với writes, cần idempotency key để tránh double execution.
- Giảm request concurrency khi database đã saturated.

### Một ví dụ nguy hiểm

1000 requests bị pool timeout, mỗi request retry 5 lần ngay lập tức: hệ thống nhận thêm tới 5000 attempts trong thời gian ngắn. Khi DB vừa phục hồi, chúng có thể tạo storm và khiến outage kéo dài.

## 76. Circuit breaker và admission control

Một service có thể giới hạn số requests được phép vào đoạn cần database:

```text
Incoming requests
        │
        ▼
  admission / bulkhead
     ├── admitted → pool → PostgreSQL
     └── rejected/queued briefly → controlled error
```

Đây là một cơ chế **backpressure** trước khi mọi request cùng chờ pool.

### Chọn mức giới hạn

Không đặt admission concurrency cao hơn nhiều so với khả năng hoàn thành của tầng DB, nếu mục tiêu là bảo vệ latency. Cần test cả:

- Burst ngắn.
- Sustained overload.
- DB failover.
- Một tenant dùng quá nhiều.
- Long transaction và lock contention.

Một lỗi overload được trả nhanh đôi khi tốt hơn giữ hàng nghìn HTTP threads chờ rồi cùng timeout.

## 77. Budget khi rolling deployment

Giả sử steady state:

```text
12 pods × 8 connections = 96
```

Một deployment có `maxSurge=25%` có thể tạm có thêm 3 pods:

```text
15 pods × 8 connections = 120
```

Nếu budget API chỉ 100 server connections, steady state đúng nhưng rollout có thể làm cạn slots.

### Giải pháp

- Điều chỉnh maxSurge/maxUnavailable theo khả năng phục vụ.
- Đặt max pool/pod với surge budget.
- Không warm toàn bộ connections quá nhanh.
- Có PgBouncer server pool hard cap nếu hợp kiến trúc.
- Dùng graceful shutdown và drain requests/transactions.

Sizing theo **steady replicas** mà bỏ qua surge là một lỗi phổ biến khi chuyển lên Kubernetes.

## 78. Startup và graceful shutdown

Khi pod dừng:

1. Ngừng nhận requests mới.
2. Chờ các requests đang xử lý hoàn thành theo timeout.
3. Kết thúc/rollback transactions đúng cách.
4. Close datasource/pool.
5. Đảm bảo server connections được giải phóng.

### Nếu tắt đột ngột

PostgreSQL sẽ xử lý connection mất và rollback transactions chưa commit. Nhưng requests có thể đang chờ commit acknowledgment; application phải xử lý unknown outcome ở tầng nghiệp vụ.

### Không giữ pool qua vòng đời không rõ

Một service vô tình tạo HikariDataSource mới mỗi lần gọi method có thể rò pools và mở nhiều physical connections. DataSource thường nên là đối tượng **shared có lifecycle quản lý**, không tạo lại cho mỗi request.

## 79. Spring Boot: cấu hình HikariCP

Ví dụ file `application.yml`:

```yaml
spring:
  datasource:
    hikari:
      pool-name: orders-primary
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 2000
      idle-timeout: 600000
      max-lifetime: 1800000
      validation-timeout: 1000
```

Đây chỉ là **phần cấu hình pool**, chưa gồm JDBC URL, TLS, username và password. Hãy cung cấp secrets từ secret manager/env/credential provider đáng tin của deployment thay vì commit vào Git.

### Chọn theo resource budgets

Với 5 replicas và một DataSource/pod, `maximum-pool-size=12` có tổng trần 60 application-side connections. Nếu endpoint là direct PostgreSQL, khoảng này cũng là upper bound physical connections từ những pool đó; nếu endpoint là PgBouncer transaction pooling, số server backends tới PostgreSQL do PgBouncer quyết định theo pooling settings.

### Cẩn thận milliseconds

Các duration của Hikari trong code và Spring properties thường được cấu hình theo **milliseconds** cho những properties trên. `connection-timeout: 2000` nghĩa là 2 giây, không phải 2000 giây.

## 80. ApplicationName để tra cứu từng service

Một cách cấu hình JDBC PostgreSQL:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:postgresql://db.internal:5432/ordersdb");
config.setUsername(System.getenv("DB_USER"));
config.setPassword(System.getenv("DB_PASSWORD"));
config.addDataSourceProperty("ApplicationName", "orders-api");
config.setMaximumPoolSize(12);
```

Trong PostgreSQL:

```sql
SELECT
    application_name,
    count(*) AS session_count
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY application_name
ORDER BY session_count DESC;
```

### Khi có PgBouncer

ApplicationName qua pooler có thể chịu rules của pooler/connection negotiation. Khi multiplex transactions, **server connection không nhất thiết có mapping đơn giản tới một pod cụ thể**. Kết hợp PgBouncer client metrics và application tracing, không cố đếm replicas chỉ từ `pg_stat_activity.application_name`.

## 81. Bảo mật credentials và TLS

Một pool thường dùng credentials cho nhiều sessions. Khi credentials bị lộ, attacker có thể dùng chúng để tạo hàng loạt kết nối, đọc dữ liệu hoặc gây cạn slots.

### Các biện pháp

- Database role với quyền tối thiểu.
- TLS và xác minh server identity phù hợp, ví dụ pgJDBC `sslmode=verify-full` cùng trust configuration cần thiết.
- Secret manager và rotation.
- Không để password trong source/log/plaintext diagnostics.
- Network policy chỉ cho services cần thiết tới DB/PgBouncer.
- Authentication trên PgBouncer và PostgreSQL tương thích.
- Không cho application role là superuser hoặc chủ mọi bảng khi không cần.

### Credential rotation

Kết nối đã xác thực có thể tiếp tục tồn tại trong một số tình huống dù credential đổi; pool cần retire/reconnect theo rollout policy. Không giả định đổi password lập tức thu hồi mọi session cũ đã được thiết lập.

## 82. Read-only workload và readonly transaction

Nếu một pool chỉ để báo cáo:

```sql
BEGIN READ ONLY;
SELECT count(*) FROM some_reporting_table;
COMMIT;
```

`READ ONLY` làm PostgreSQL chặn nhiều loại thao tác ghi trong transaction theo semantics của nó, nhưng không thay **GRANT SELECT** và quyền đọc dữ liệu.

### Vì sao cần cả hai?

- Role privileges bảo vệ dài hạn.
- Read-only transaction giúp phát hiện lỗi ghi ngoài ý định trong một transaction.
- Replica routing có thể giảm tải primary, nhưng cần chấp nhận lag.

Không tin một cờ `readOnly=true` của Java như cơ chế cấp quyền không thể vượt qua.

## 83. Connection limit như một hàng rào, không phải capacity plan

`ALTER ROLE ... CONNECTION LIMIT` hữu ích để một role không vô tình chiếm hết server slots, nhưng nó cũng có thể khiến role bị từ chối nếu tổng pool across replicas lớn hơn limit.

### Ví dụ

Nếu `app_user` có limit 30:

```text
4 pods × 12 pool max = 48 potential connections
role connection limit = 30
```

Pool budget và role limit mâu thuẫn. Một số pods có thể mở đủ connections, pods khác không thể, khiến hiệu năng không đồng đều.

### Điều chỉnh

Giải quyết trong một bản tính tổng thể gồm `max_connections`, role/database limits, poolers, replicas, surge, batch jobs và operational headroom.

Role connection limit **không chia đều connection slots** cho các pods; nó chỉ áp giới hạn tổng theo cơ chế role.

## 84. Admission limit tổng thể vs pool per pod

Per-pod `maximumPoolSize` không tự tạo **cluster-wide fairness**. Khi traffic bị load balancer chia không đều, một pod có thể pending cao trong khi pod khác còn idle.

### Các lựa chọn

- Load balancing hợp lý.
- Horizontal pod sizing cùng concurrency settings.
- Application-level bulkhead.
- Central rate limiting cho nhóm workload/tenant.
- PgBouncer server pool cap để bảo vệ primary.
- Monitoring per-pod distribution, không chỉ trung bình toàn service.

### Tại sao average metric nguy hiểm?

Nếu 10 pods có 9 pods pending=0 và 1 pod pending=100, trung bình pending=10 không cho biết pod đang lỗi nghiêm trọng. Monitor theo pod và aggregate tail/maximum khi cần.

## 85. Ví dụ budget có rollout và jobs

Giả sử:

| Thành phần | Giá trị |
|---|---:|
| PostgreSQL `max_connections` | 140 |
| Ngân sách reserved/ưu tiên | 5 |
| BI, monitoring, admin | 15 |
| Headroom vận hành | 20 |
| **Budget cho app + batch** | **100** |
| API steady replicas | 8 |
| API maximum khi rollout overlap | 10 |
| Batch jobs max DB connections | 8 |

Suy ra:

\[
10P + 8 \le 100
\]

\[
P \le \left\lfloor \frac{92}{10} \right\rfloor = 9
\]

`P=9` cho tối đa 90 connections từ API khi surge; cộng 8 batch thành 98, vẫn trong budget 100.

### Đây chưa phải optimum

Nếu PostgreSQL chỉ xử lý tốt 40 active queries, dùng 98 server connections **không làm nó xử lý tốt 98 queries đồng thời**. Budget chỉ ngăn chạm trần slots; việc chọn `P=5`, 7 hay 9 phải dựa trên latency/throughput và khả năng xử lý thực.

### Kiểm tra nền tảng

Nếu app giao tiếp qua PgBouncer, công thức server pool phải được sửa để phản ánh **PgBouncer server connections** chứ không lấy đơn giản `10P` làm số connections PostgreSQL. Dù thế, `10P` vẫn là mức client connections Hikari có thể mở tới pooler.

## 86. Tính toán từ traffic burst

Giả sử traffic thường 100 requests/s, nhưng có burst 300 requests/s trong 20 giây. Mean connection hold 40ms và mỗi request có một DB lease:

```text
Normal:
100 × 0.04 = 4 leased connections trung bình

Burst:
300 × 0.04 = 12 leased connections trung bình
```

### Vì sao không chỉ cấp 12 slots?

- Các requests không đến đều.
- Hold time có variability.
- Có jobs/tenants khác.
- Nếu DB chậm trong burst, hold time tăng và concurrency demand tăng.
- Nếu DB đã saturated, cần queue/backpressure chứ không nhận vô hạn.

### Đề xuất test

Chạy burst với shape thật; đo thời gian chờ pool, latency p99, error rate, DB CPU/locks và thời gian phục hồi sau burst. Chọn size/queue policy thỏa SLO chứ không chỉ vừa khớp trung bình 12.

## 87. Query fan-out trong một request

Một request có thể thực thi:

```text
Query A rồi Query B rồi Query C (tuần tự)
```

hoặc:

```text
Query A, B, C (song song qua ba connections)
```

Nếu fan-out query song song, một request có thể mượn **nhiều connections đồng thời**. Công thức requests/s × một connection hold time không còn đúng nếu bỏ qua nhiều leases.

### Cách đo

- Số checkout operations/request.
- Số concurrent checkouts/request.
- Tổng connection-seconds/request.
- Transaction boundaries.

Đừng tăng asynchronous JDBC calls vô hạn rồi mong connection pool tự xử lý fairness cho mọi request.

## 88. Reactive application và R2DBC

Các ứng dụng reactive có thể dùng R2DBC hoặc một client model khác JDBC. Điều này **không loại bỏ giới hạn physical server connections**:

- Vẫn có connections tới PostgreSQL/pooler.
- Vẫn có concurrent DB operations.
- Vẫn cần backpressure/timeouts.
- Vẫn cần quản lý transaction scope.

Không chuyển sang reactive chỉ vì gặp `too many connections` rồi cho rằng nhu cầu database capacity đã biến mất.

### So sánh

Một mô hình ít threads hơn có thể giảm tài nguyên **application**, nhưng throughput của một PostgreSQL primary vẫn bị giới hạn bởi CPU/I/O/locks và SQL workload.

## 89. Một công cụ đo local pool usage

Trong HikariCP có thể tiếp cận MXBean để quan sát số connections:

```java
import com.zaxxer.hikari.HikariPoolMXBean;

HikariPoolMXBean metrics = dataSource.getHikariPoolMXBean();

int active = metrics.getActiveConnections();
int idle = metrics.getIdleConnections();
int total = metrics.getTotalConnections();
int waiting = metrics.getThreadsAwaitingConnection();

System.out.printf(
    "active=%d idle=%d total=%d waiting=%d%n",
    active, idle, total, waiting
);
```

### Không thay monitoring thực tế

Đây là một snapshot trong process, không phải histogram p95/p99 và không thay telemetry của nhiều pods. Tùy app, expose metrics qua Micrometer/Prometheus/OpenTelemetry phù hợp và kiểm tra security của endpoint metrics.

## 90. Lấy số sessions và pool budget từ server

Một truy vấn quản trị:

```sql
WITH params AS (
    SELECT
        current_setting('max_connections')::integer
            AS max_connections
),
connections AS (
    SELECT
        count(*) FILTER (
            WHERE backend_type = 'client backend'
        ) AS client_backends
    FROM pg_catalog.pg_stat_activity
)
SELECT
    p.max_connections,
    c.client_backends,
    p.max_connections - c.client_backends
        AS arithmetic_difference
FROM params AS p
CROSS JOIN connections AS c;
```

### Cảnh báo cách đọc

`arithmetic_difference` **không phải số connection slots app role chắc chắn còn dùng được**: reserved slots, role/database limits và client classes khác có thể tác động. Nó chỉ là phép tính sơ bộ giữa một limit và số sessions loại `client backend` được đếm.

Theo dõi thêm các connection types và metrics của provider/pooler khi sizing nghiêm túc.

## 91. PgBouncer không phải một primary database replica

PgBouncer là proxy/pooler, **không phải nơi lưu dữ liệu** và không tự nhân bản tables/WAL.

### Những thứ PgBouncer có thể hỗ trợ

- Giảm số server connections thông qua multiplex.
- Queue clients khi server slots ít.
- Thực thi một số giới hạn per database/user pool.
- Quản lý connection lifecycle tới PostgreSQL.

### Những thứ nó không tự làm

- Tăng năng lực xử lý CPU của PostgreSQL.
- Tự giải quyết read-after-write lag.
- Tự đảm bảo HA failover seamless cho đang chạy transaction.
- Biến session-scoped features thành transaction-scoped.
- Tự cho phép connection count toàn cluster vượt PostgreSQL capacity mà không có hậu quả.

Deployment nhiều PgBouncer instances cần HA routing và budget server connections riêng, không có lợi ích “vô hạn connections” chỉ vì đặt proxy.

## 92. Mối quan hệ giữa query plans và pool size

Một pool lớn có thể làm số queries đồng thời tăng, từ đó:

- Gây nhiều sort/hash operations dùng memory.
- Tăng temp file spills.
- Tăng lock contention.
- Tăng buffer cache pressure.
- Tăng CPU context switching.

**Query plan** không do pool size quyết định trực tiếp, nhưng workload concurrency thay đổi môi trường runtime của plan. Một plan nhanh khi thử đơn lẻ có thể chậm khi 50 queries chạy đồng thời.

### Benchmark phải có concurrency

Đừng chỉ chạy `EXPLAIN ANALYZE` cho một SQL rồi suy rằng 100 executions đồng thời vẫn có cùng latency. Cần load test với concurrency thật, cùng plan/statistics và đo resource contention.

## 93. Case study: 1 pod và 10 pods

Một service ban đầu chạy 1 pod, Hikari max=20:

```text
1 × 20 = 20 potential DB connections
```

Sau scaling lên 10 pods, giữ nguyên cấu hình:

```text
10 × 20 = 200 potential DB connections
```

Nếu PostgreSQL `max_connections=150` và còn các clients khác, cấu hình này có rủi ro cao khi các pools mở gần trần.

### Những lựa chọn

1. Giảm per-pod maximum để nằm trong ngân sách, rồi benchmark throughput.
2. Dùng PgBouncer transaction pooling nếu workload tương thích.
3. Giảm connection hold time/SQL latency để ít cần concurrency.
4. Tách workload nặng sang replica/service riêng.
5. Nâng database capacity có kế hoạch nếu bottleneck thực sự là tài nguyên.

Không có một phép thay đổi duy nhất phù hợp mọi tình huống; cần đánh giá cả **budget và performance**.

## 94. Case study: pool size cao nhưng idle nhiều

Giả sử 8 pods, mỗi pod pool max 30 và minIdle 25:

```text
8 × 25 = 200 idle connections có thể được duy trì
```

Traffic ban đêm chỉ cần vài truy vấn mỗi giây. Nếu connections đi trực tiếp PostgreSQL, số backend idle lớn chiếm slots và một phần tài nguyên mà không mang lại throughput.

### Hướng xử lý

- Đánh giá lại minimumIdle và fixed-size strategy.
- Cân nhắc PgBouncer server pooling.
- Giữ lượng connections phù hợp với cold-start latency và server headroom.
- Không đặt idleTimeout rồi mong fixed-size pool với minIdle=max tự shrink xuống ít connections.

Đây không phải lý do luôn đặt minimumIdle=0. Nếu traffic burst cần kết nối sẵn và TLS/DB startup đắt, giữ idle hợp lý có thể đáng giá.

## 95. Case study: connection timeout là hậu quả của lock

Giả sử một transaction giữ lock trên hàng `accounts.id=1` trong 45 giây; nhiều workers khác cùng cố UPDATE row ấy.

```text
DB: 15 sessions waiting for row lock
Hikari: active 15, idle 0, pending 30
API: connection acquisition timeout
```

Tăng Hikari max từ 15 lên 40 có thể chỉ làm 40 sessions chờ lock, không giúp unlock nhanh hơn.

### Phân tích

Xem `pg_stat_activity.wait_event_type='Lock'`, transaction ages, blocking queries và business transaction scope. Cải thiện lock duration/ordering, index phù hợp và ứng dụng retry đúng semantics.

**Pool saturation có thể do lock bottleneck**, không phải thiếu physical connections trên server.

## 96. Case study: request giữ connection lúc gọi API ngoài

```text
DB SQL = 20ms
Payment HTTP = 900ms
DB COMMIT = 10ms
Connection lease = 930ms
```

Với 100 requests/s:

\[
L \approx 100 \times 0.93 = 93
\]

Nhu cầu 93 leased connections trung bình là hậu quả của **transaction/lease scope**, không phải 100 SQL queries/second luôn cần 93 active DB workers.

Nếu thiết kế hợp lệ có thể đưa external HTTP ra khỏi đoạn giữ connection, mean lease có thể giảm mạnh; nhưng phải bảo toàn idempotency/atomicity của nghiệp vụ qua saga/outbox.

Không chỉ tăng pool lên 100 và bỏ qua nguyên nhân giữ connection lâu.

## 97. Một bảng tính sizing tối thiểu

Ghi các giá trị sau cho từng môi trường:

| Input cần thu thập | Ví dụ giả định |
|---|---:|
| PostgreSQL max_connections | 120 |
| Reserved/admin/other/headroom | 45 |
| App budget | 75 |
| Max API replicas, kể cả surge | 5 |
| Number of direct-DB pools/pod | 1 |
| Hard upper bound/pod theo budget | 15 |
| DB-using request arrival rate | 120/s toàn service |
| Mean DB lease duration | 50ms |
| Little's Law average leases | 6 toàn service |
| Candidate pool sizes | 6, 8, 12, 15 |
| SLO | API p95 dưới 150ms |
| Test được chấp nhận | Có peak/burst/lock/rollback cases |

### Cách dùng

**Bước 1:** budget xác định mức trần; không để pools có thể vượt toàn server khi scale.

**Bước 2:** Little's Law đưa ra mức active trung bình ước tính.

**Bước 3:** load test và metrics cho biết pool size cần để đáp ứng SLO mà không làm DB saturation.

**Bước 4:** thử rollout/failover, vì cấu hình steady-state đẹp có thể thất bại lúc hệ thống chuyển trạng thái.

### Chú ý ngữ cảnh

Trong ví dụ, 6 average leases là toàn service, không tự chia đều cho 5 pods trong mọi thời điểm. Load balancing, per-pod bursts và skew quyết định local pool sizing.

## 98. Những nguyên tắc hay bị hiểu nhầm

**“Một request cần một connection suốt request.”** Không bắt buộc; chỉ mượn khi cần DB.

**“Pool size bằng số HTTP threads.”** Không; nhiều threads có thể không dùng DB cùng lúc.

**“Pool size bằng max_connections.”** Không; phải tính tất cả services, replicas và headroom.

**“Có 10 pods và mỗi pod max 20 thì chỉ có 20 DB sessions.”** Không; trực tiếp DB có thể tới 200.

**“PostgreSQL max_connections càng lớn thì TPS càng cao.”** Không; server có thể quá tải.

**“work_mem là giới hạn RAM trên mỗi connection.”** Không; executor có thể có nhiều operations/worker.

**“Pool active nghĩa là query đang chạy CPU.”** Không; connection có thể chờ lock hoặc app.

**“Pool idle luôn là leak.”** Không; idle là phần bình thường của connection reuse.

**“Pool pending tăng thì chắc chắn tăng maximumPoolSize.”** Không; cần xem DB/locks/hold time.

**“Little's Law cho p99 pool size chính xác.”** Không; công thức dùng mean trong hệ thống ổn định.

**“Cứ lấy p99 query time nhân RPS là đủ.”** Không; phải đo đúng connection lease và arrival variance.

**“Pool timeout giống statement timeout.”** Không; một bên chờ mượn connection, một bên hủy query.

**“SET LOCAL có tác dụng qua nhiều transactions.”** Không; local tới transaction.

**“Session state giữ nguyên qua PgBouncer transaction pooling.”** Không.

**“PgBouncer default_pool_size=20 nghĩa toàn cluster có đúng 20 server connections.”** Không; có nhiều pool keys/nodes và reserve.

**“PgBouncer max_client_conn tăng là tăng PostgreSQL server capacity.”** Không.

**“Mọi prepared statements đều không tương thích PgBouncer transaction mode.”** Không đúng với mọi phiên bản/cấu hình; cần phân biệt protocol vs SQL PREPARE.

**“LISTEN hoạt động qua bất kỳ pool mode nào.”** Không; cần session affinity.

**“Connection.close() luôn đóng physical TCP socket.”** Không khi thông qua pool proxy.

**“Hikari leak detection chứng minh code rò connection.”** Không; long legitimate transactions có thể bị cảnh báo.

**“Failover rồi pool tự retry transaction an toàn.”** Không; cần application retry/idempotency.

**“Nâng max_connections là cách đầu tiên xử lý lỗi 53300.”** Không; đầu tiên điều tra budget và workload.

**“Read replica không cần tính connection budget.”** Không; replica có giới hạn riêng.

**“Autoscale nhiều pods chắc chắn tăng DB throughput.”** Không; có thể tạo feedback loop quá tải.

**“Đã TLS giữa app và PgBouncer thì PgBouncer→PostgreSQL luôn mã hóa.”** Không; cần cấu hình từng hop.

**“Một lần load test SELECT 1 đủ sizing production.”** Không; workload phải đại diện.

**“Query nhanh khi chạy một mình vẫn nhanh với 100 concurrent queries.”** Không; contention là yếu tố lớn.

**“Request thất bại khi COMMIT ACK mất nghĩa là rollback.”** Không; outcome có thể không rõ.

**“Pool max là số connections thực tế luôn được mở.”** Không; phụ thuộc minimumIdle, nhu cầu và pool lifecycle.

**“Connection limit role tự chia đều slot cho các pods.”** Không; nó là giới hạn tổng theo role, không phải fairness scheduler.

## 99. Runbook tổng hợp: chọn hành động theo tín hiệu

| Tín hiệu | Câu hỏi đầu tiên | Hướng điều tra/điều chỉnh |
|---|---|---|
| Pool active=max, pending cao, CPU DB thấp | Connection đang làm gì? | Hold time, locks, pooler waiting, leaks |
| Pool active=max, pending cao, CPU DB cao | DB đã saturated? | SQL, CPU/IO, concurrency limit, slow transactions |
| Many `idle in transaction` | Ai giữ transaction? | Framework scope, rollback/timeout, external calls |
| Many `idle` và server sát giới hạn | Ai duy trì idle sessions? | MinimumIdle, pools per pod, PgBouncer |
| PgBouncer `cl_waiting` cao | Server pool nào bị chặn? | Pool key limits, long transactions, backend availability |
| PostgreSQL SQLSTATE `53300` | Budget ở đâu bị vượt? | Replicas, surge, jobs, roles, reserved headroom |
| CPU/IO high nhưng Hikari active thấp | Query đã đủ nặng chưa? | EXPLAIN, waits, write amplification |
| Timeout sau deploy | Connection storm? | Pool initialization, overlap, jitter |
| Nhiều JDBC connection failure sau failover | Connections cũ đã bị đóng? | Endpoint routing, pool retire, transaction retry |
| Reports chiếm toàn pool | Có workload dài chung OLTP không? | Separate pool/replica/jobs |
| p99 cao nhưng average thấp | Có long-tail SQL/hold time không? | Histograms, lock waits, traffic skew |
| Hikari leak logs | Thực sự quên close? | Stack traces, time-held, ORM transaction scope |

### Cách ra quyết định

Đừng chỉnh cùng lúc `max_connections`, Hikari maximumPoolSize, PgBouncer default_pool_size, work_mem và statement_timeout rồi không biết yếu tố nào đã giúp hoặc làm xấu hệ thống. Thay đổi có kiểm soát, đo trước/sau và có rollback.

## 100. Quy trình triển khai cấu hình pool mới

1. Ghi cấu hình hiện tại và nguồn (app properties, environment, PgBouncer, PostgreSQL, managed service).
2. Tính tổng connection budget theo max replicas, surge, pools và jobs.
3. Xác nhận các limit ở role/database/server/pooler không mâu thuẫn.
4. Chạy load test với traffic profile đại diện.
5. Chốt candidate đáp ứng SLO và có headroom.
6. Kiểm tra feature compatibility với PgBouncer pool_mode.
7. Đặt timeout order và retry budget, kể cả HTTP deadlines.
8. Kiểm tra quyền và TLS của mọi hop.
9. Triển khai canary với metrics và cảnh báo.
10. Quan sát pool pending/acquisition/hold, DB CPU/locks và error rates.
11. Thử restart/failover, rollout surge, batch jobs.
12. Nếu vượt ngưỡng, rollback cấu hình thay vì nâng thêm connection limits tùy tiện.

### Một cấu hình tốt là cấu hình có bằng chứng

Tài liệu vận hành nên lưu:

- `max_connections` và slots dành cho admin.
- Tổng pool budgets và những assumptions về replica count.
- Cách chọn maximumPoolSize (kết quả benchmark).
- SLO và overload behavior.
- Timeout và retry policy.
- PgBouncer modes/compatibility findings.
- Metrics dashboard/runbook và chủ sở hữu.

Khi ứng dụng hoặc workloads thay đổi, các con số sizing cần được đánh giá lại.

## 101. Bài tập thực hành

### Bài 1 — Vì sao cần pool?

Giải thích vì sao mở một PostgreSQL connection mới cho mỗi HTTP request gây chi phí. Nêu ít nhất ba lợi ích và ba giới hạn của connection pool.

### Bài 2 — Phân biệt các loại concurrency

Một service có 150 HTTP requests đang xử lý, Hikari active=12, PostgreSQL active queries=6. Vì sao ba số không bằng nhau?

### Bài 3 — Quan sát max_connections

Chạy `SHOW max_connections` và truy vấn `pg_settings`. Phân biệt cấu hình server limit với số connections đang mở.

### Bài 4 — Reserved slots

Truy vấn `superuser_reserved_connections` và `reserved_connections` (nếu phiên bản có). Vì sao application không nên tiêu thụ mọi slot còn lại?

### Bài 5 — Giới hạn theo role/database

Đọc `rolconnlimit` và `datconnlimit`. Một role bị giới hạn 20 trong khi server còn 80 slots có thể kết nối 30 sessions không? Giải thích.

### Bài 6 — Budget một service

`max_connections=100`, dự phòng ưu tiên 3, client khác 17, headroom 15. Tính ngân sách còn cho API.

### Bài 7 — Budget nhiều replicas

Từ bài 6, API có 5 replicas, mỗi pod một pool. Tính upper bound pool/pod theo budget và giải thích vì sao đó chưa phải optimum.

### Bài 8 — Budget hai services

Server còn app budget 90. Service A có 4 replicas max 12, service B có 3 replicas max 10, batch jobs 8 connections. Tổng có vượt budget không?

### Bài 9 — Rollout surge

Service chạy 8 pods × pool 10. Rolling deployment có thể tạm 11 pods. Tính peak potential connections và điều chỉnh kế hoạch triển khai nếu budget chỉ 100.

### Bài 10 — Nhiều DataSources

Mỗi pod có pool primary max 12 và reporting max 8, chạy 6 pods. Tính direct connections tối đa tới từng endpoint và khi nào cần cộng vào cùng một budget.

### Bài 11 — Little's Law

120 DB leases/s, hold time mean 50ms. Tính leased connections trung bình, nêu điều kiện ổn định và boundary áp dụng.

### Bài 12 — Giảm hold time

Giữ 120 leases/s, giảm mean hold time từ 200ms xuống 40ms. So sánh số leased connections trung bình trước/sau và ý nghĩa đối với pool.

### Bài 13 — Tail latency

99% transactions giữ connection 10ms, 1% giữ 5s. Vì sao chỉ lấy mean không đủ để dự báo p99 acquisition wait?

### Bài 14 — Pool quá nhỏ

Hikari active=max, pending tăng, PostgreSQL CPU thấp, không có lock waits. Nêu những điều cần kiểm tra trước khi tăng maximumPoolSize.

### Bài 15 — Pool quá lớn

Tăng Hikari max từ 12 lên 50 khiến throughput giảm và DB CPU 100%. Giải thích cơ chế có thể gây ra và đề xuất cách đo.

### Bài 16 — Hikari cấu hình

Tạo `HikariDataSource` với max=12, minIdle=4, connectionTimeout=2000ms và maxLifetime theo upstream policy. Bảo đảm close datasource khi shutdown.

### Bài 17 — try-with-resources

Viết JDBC method mượn connection, thực thi SELECT và trả connection ở cả trường hợp success/exception.

### Bài 18 — Transaction lifecycle

Viết JDBC transaction thực thi hai câu UPDATE; commit nếu thành công, rollback nếu lỗi, đóng connection trong mọi nhánh.

### Bài 19 — Phân loại timeout

So sánh Hikari connectionTimeout, PostgreSQL statement_timeout, lock_timeout và HTTP deadline. Với request có ba SQL statements, vì sao timeout mỗi statement không giới hạn tổng request?

### Bài 20 — Idle-in-transaction

Chạy query `pg_stat_activity` lọc state `idle in transaction` và xact_start cũ. Nêu ba nguyên nhân và ba rủi ro vận hành.

### Bài 21 — PgBouncer modes

So sánh session, transaction và statement pooling. Một app có multi-statement transactions và temporary table qua nhiều transactions nên chọn mode nào hoặc phải đổi kiến trúc ra sao?

### Bài 22 — PgBouncer budget

Ba PgBouncer instances, mỗi instance có hai pool keys, default_pool_size=15 và reserve_pool_size=5. Tính tổng trần server connections từ các pools trong giả định mọi pool mở hết.

### Bài 23 — Prepared statements

Giải thích sự khác nhau giữa `SQL PREPARE` và protocol-level prepared statements. Vì sao tính tương thích với PgBouncer transaction pooling phụ thuộc version/config?

### Bài 24 — Transaction-local setting

Trong transaction, đặt `app.tenant_id` bằng `set_config(...,true)` rồi thực thi SELECT. Điều gì xảy ra nếu gọi set_config trong autocommit statement riêng và hy vọng SELECT kế thừa giá trị?

### Bài 25 — LISTEN/NOTIFY

Một background listener cần duy trì `LISTEN` nhiều giờ. Vì sao Hikari request pool kết hợp PgBouncer transaction pooling không phải thiết kế phù hợp mặc định?

### Bài 26 — Session advisory lock

So sánh session-level và transaction-level advisory locks khi đi qua PgBouncer transaction mode. Điều gì có thể xảy ra nếu unlock ở transaction sau trên backend khác?

### Bài 27 — Quan sát backend

Viết SQL group `pg_stat_activity` theo `application_name`/`state` và đếm sessions. Vì sao `idle` không mặc định là leak?

### Bài 28 — Wait events

Truy vấn `state`, `wait_event_type`, `wait_event`. Với 20 sessions `active` nhưng phần lớn đang chờ `Lock`, tăng pool có giúp không?

### Bài 29 — Cumulative metrics

Đọc `pg_stat_database.xact_commit` tại hai thời điểm cách nhau 60s. Viết cách tính TPS và nêu rủi ro khi statistics được reset.

### Bài 30 — Leak detection

Hikari báo một connection giữ 90s. Phân biệt leak do thiếu close với một report hợp lệ giữ cursor lâu; cần những metrics nào?

### Bài 31 — Lock bottleneck

Một transaction giữ row lock 30s, 15 writers khác chờ. Giải thích vì sao Hikari pending tăng dù DB CPU thấp và cách xử lý ở tầng SQL/transaction.

### Bài 32 — Load test

Lập kế hoạch thử pool size 4/8/12/16/24. Chọn input workload, warm-up, success req/s, API p95/p99, acquisition time, hold time, CPU và lock waits.

### Bài 33 — Đọc bảng benchmark

Một phép thử giả định: pool 8 đạt 650 req/s p95=95ms, pool 12 đạt 700 req/s p95=100ms, pool 24 đạt 680 req/s p95=260ms. Với SLO p95≤150ms và target 600 req/s, lựa chọn nào có thể phù hợp nhất? Nêu điều kiện cần kiểm chứng.

### Bài 34 — Connection storm

30 pods khởi động đồng thời, mỗi pod tạo 20 idle sessions. Tính số connections có thể được mở và đề xuất cách tránh cạn slots.

### Bài 35 — Failover

PostgreSQL primary failover trong lúc một transaction gửi COMMIT và connection mất. Tại sao không thể mặc định xem giao dịch đã rollback? Đề xuất idempotency.

### Bài 36 — Error SQLSTATE

Phân loại `53300`, `08006`, `57014`, `40001` và `40P01`. Những lỗi nào thường cần retry toàn transaction, và khi nào retry gây overload?

### Bài 37 — Read replica

Thiết kế two-datasource primary/replica cho một app đọc nhiều. Tính budget theo từng server và xử lý read-after-write consistency.

### Bài 38 — Spring transaction scope

Một `@Transactional` method gọi HTTP service 2s trước khi UPDATE. Điều gì cần đo để biết physical connection có bị giữ suốt 2s không, và cách giảm thời gian giữ hợp lý?

### Bài 39 — Multi-tenant fairness

Một tenant chiếm 80% DB leases khiến tenant nhỏ timeout. Đề xuất concurrency/rate limiting và giải thích vì sao một pool cho mỗi tenant có thể phá connection budget.

### Bài 40 — Thiết kế tổng hợp

Một nền tảng PostgreSQL có:

- `max_connections=160`, cần giữ 8 reserved/ops slots đặc biệt và 25 slots cho monitoring/BI, 20 slots headroom.
- API có 6 pods steady, 9 pods khi rollout surge.
- Background workers có tổng pool tối đa 12.
- API đạt 240 DB leases/s, mean hold time 45ms.
- API p95 SLO dưới 200ms.
- Một số jobs dùng temp tables, listener dùng LISTEN và OLTP dùng prepared statements.
- Trước đây thỉnh thoảng có SQLSTATE `53300` khi autoscale.

Hãy thiết kế và giải thích:

1. Ngân sách còn cho API sau khi trừ reserved/ops, BI và headroom, background jobs.
2. Upper bound Hikari pool/pod với 9 pods surge.
3. Little's Law average leased connections toàn service.
4. Vì sao upper bound và average không trực tiếp là optimum.
5. Những candidates pool sizes cần benchmark và metrics bắt buộc.
6. Khi nào dùng PgBouncer transaction pooling và pool keys/server budgets.
7. Xử lý riêng LISTEN/temporary tables/prepared statements theo compatibility.
8. Đặt các timeout, retry, idempotency và network TLS policy.
9. Giám sát `pg_stat_activity`, PgBouncer, Hikari và long transactions.
10. Kế hoạch canary/rollback/failover/burst test để tránh lỗi `too many connections`.

## Kết luận

**Connection pool là công cụ kiểm soát concurrency và tái sử dụng kết nối, không phải cách tạo ra thêm CPU cho PostgreSQL.** Cấu hình tốt bắt đầu từ việc đo **connection lease time**, arrival rate, pool pending/acquisition latency và active queries, chứ không mặc định pool bằng số HTTP threads hoặc số người dùng online.

**`max_connections` là trần kỹ thuật** với reserved slots và các giới hạn role/database, không phải mục tiêu cần dùng hết. Khi có nhiều replicas, service pools, batch jobs và rolling deployments, phải tính **tổng số physical server connections có thể mở**; autoscale mà không kiểm soát budget có thể biến một API bottleneck thành lỗi toàn database.

**Little's Law `L=λW`** giúp ước lượng số leased connections trung bình nếu đo đúng ranh giới và workload ổn định. Nhưng sizing thực tế vẫn phải đo p95/p99 latency, lock waits, DB CPU/I/O, throughput và burst variability. Pool quá nhỏ khiến request chờ; pool quá lớn khiến PostgreSQL xử lý nhiều tác vụ cạnh tranh hơn và có thể giảm throughput.

**HikariCP** là pool phía Java application; **PgBouncer** có thể multiplex client sessions thành số server connections nhỏ hơn, đặc biệt ở transaction pooling. Đổi lại, phải hiểu rõ session state, prepared statements, temp tables, advisory locks, LISTEN và mỗi pool key/instance có ngân sách riêng.

Cuối cùng, ưu tiên **giảm thời gian giữ connection, tối ưu SQL, giới hạn các truy vấn đồng thời, timeout/retry có kiểm soát và vận hành có số liệu**. Một cấu hình pool đúng không phải một con số được sao chép từ internet; đó là kết quả của **ngân sách kết nối, đo tải thật, ranh giới transaction rõ ràng, bảo vệ ứng dụng trước overload và kiểm thử failover/rollout**.
