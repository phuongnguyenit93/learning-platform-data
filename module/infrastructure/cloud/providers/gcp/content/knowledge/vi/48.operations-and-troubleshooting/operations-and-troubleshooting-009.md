# Chẩn đoán Cloud SQL connection exhaustion và truy vấn chậm

## 1. Mục tiêu và phạm vi bài học

Một ứng dụng Java/Spring Boot chạy trên Cloud Run, GKE hoặc Compute Engine có thể kết nối Google Cloud SQL thành công trong lúc tải thấp, nhưng đột nhiên trả HTTP 500/503 khi traffic tăng. Log ứng dụng đôi khi ghi `Connection is not available, request timed out`; ở trường hợp khác, database trả `too many connections`. Cũng có lúc tất cả kết nối vẫn hoạt động, nhưng một truy vấn tăng từ 20 ms lên 8 giây và chiếm hết các connection trong pool.

Ba hiện tượng này liên quan nhau nhưng **không cùng nguyên nhân**:

1. **Database connection exhaustion:** server đã đạt hoặc gần giới hạn connection/session, không nhận thêm kết nối phù hợp.
2. **Application pool exhaustion:** các connection trong HikariCP đều đang được mượn hoặc chưa trả về; request phải xếp hàng ở ứng dụng dù database có thể vẫn còn slots.
3. **Slow queries / long transactions:** SQL, lock, I/O, CPU hoặc network làm một connection bị giữ lâu. Hệ quả là pool đầy và cuối cùng tạo cảm giác “hết kết nối”.

Bài viết là một **runbook chẩn đoán có thể thực hành** cho module `CLOUD_PROVIDERS_GCP`, nối kiến thức về Cloud SQL, IAM, VPC/private networking, Cloud Run/GKE autoscaling, Java connection pools, observability, reliability và chi phí.

Sau bài học, người học có thể:

- Xác định lỗi ở network/auth, Cloud SQL server, Java pool hay bản thân truy vấn.
- Thu thập bằng chứng theo thời gian sự cố bằng Cloud Monitoring, System Insights, Query Insights và database engine views.
- Thực hiện truy vấn chẩn đoán **read-only** cho PostgreSQL, MySQL hoặc SQL Server.
- Tính connection budget cho nhiều replicas, revisions và background jobs.
- Nhận diện leak, transaction dài, blocking locks, query plan xấu và resource saturation.
- Chọn biện pháp giảm tải ngắn hạn có đánh giá tác động, tránh restart/kill tràn lan.
- Cải thiện Spring Boot/HikariCP, SQL/index, retry và kiểm soát concurrency.
- Lập báo cáo RCA và diễn tập tình huống tương tự trên môi trường được phép.

**Phạm vi an toàn:** các SQL bên dưới chỉ đọc thông tin trạng thái, không chứa lệnh kill session, sửa flags, nâng máy hoặc xóa dữ liệu. Những thay đổi production phải có approval và phương án rollback. Không chạy lệnh trên một instance không thuộc phạm vi được ủy quyền.

## 2. Nhìn nhanh: triệu chứng nào dẫn tới nhánh điều tra nào?

| Triệu chứng quan sát | Giả thuyết đầu tiên | Cần kiểm tra |
|---|---|---|
| PostgreSQL báo `remaining connection slots are reserved` hoặc SQLSTATE `53300` | Server gần `max_connections` | Cloud SQL connections metric, `pg_stat_activity`, reserved slots |
| MySQL báo `Too many connections` (error 1040) | Server hết connection | `Threads_connected`, `max_connections`, processlist |
| Hikari báo `Connection is not available, request timed out` | Pool bị chiếm, leak hoặc DB kết nối chậm | Hikari active/idle/pending, query/transaction duration |
| Cloud Run lỗi chỉ trong lúc scale out | Tổng số pools vượt budget hoặc cold starts dồn dập | Max instances, pool size, các revisions/jobs |
| Một endpoint tăng p99 latency, DB CPU chưa cao | Lock, N+1, network hoặc chờ connection | Query Insights, wait events, app tracing |
| Query latency tăng kèm CPU 90–100% | Thiếu CPU hoặc query plan quá nặng | System Insights, top queries, EXPLAIN |
| Query latency tăng kèm I/O wait cao | Nhiều disk reads/writes, index kém, storage bottleneck | Disk IOPS/throughput, waits, query plans |
| Nhiều session `idle in transaction` | Transaction chưa commit/rollback, connection bị giữ | `pg_stat_activity`, Java `@Transactional`, call graph |
| Timeout trước khi đến DB | VPC, DNS, firewall, IAM, connector/proxy, TLS | Cloud SQL connectivity logs, connector config |
| Sau deploy latency tăng rõ | Thay đổi SQL, migration, pool hoặc concurrency | Deploy timeline, query fingerprints, diff config |

Đừng kết luận chỉ từ một dòng log. Ví dụ lỗi Hikari là **thời gian chờ mượn connection**, không tự chứng minh server đã đạt giới hạn connection. Một pool có 10 active connections bị giữ bởi 10 truy vấn chậm có thể làm request thứ 11 timeout ngay cả khi database còn rất nhiều slots.

## 3. Runbook 0–5 phút: cô lập phạm vi ảnh hưởng

### 3.1. Xác định nguồn sự cố

Trả lời theo thứ tự:

1. Project, Cloud SQL instance, region, database engine/version và environment là gì?
2. Sự cố bắt đầu lúc nào (UTC), trùng deploy, migration, traffic spike hay thay đổi IAM/network nào?
3. Chỉ một service hoặc endpoint bị lỗi, hay mọi workload dùng chung database?
4. Instance primary hay read replica? Chỉ luồng write hay cả read?
5. Số request lỗi/độ trễ so với SLO và mức độ ảnh hưởng người dùng?
6. Có emergency contact, data owner và change freeze đang áp dụng không?

Không tạo hoặc restart nhiều services cùng lúc khi chưa hiểu tình trạng, vì điều đó có thể tạo thêm cơn bão kết nối tới Cloud SQL.

### 3.2. Thu thập bằng chứng tối thiểu

- Ảnh hoặc export metric **Cloud SQL connections**, CPU, memory, disk utilization/I/O.
- App metrics: request rate, p95/p99, 5xx, Hikari active/idle/pending/timeouts.
- Cloud Run instances/concurrency hoặc GKE pods/rollouts và trạng thái jobs.
- Một vài log lỗi đã **loại bỏ credential, PII và SQL literals**.
- Thời gian deployment, config change, schema migration, backup/failover.
- Query Insights snapshot hoặc engine-specific session statistics nếu được phép.

Tăng mức severity/escalation nếu payment/transaction fail liên tục, database không nhận connection quản trị hoặc có nguy cơ data inconsistency.

### 3.3. Lệnh đọc Cloud SQL metadata

Chỉ dùng với project/instance được ủy quyền:

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"
export INSTANCE="YOUR_CLOUD_SQL_INSTANCE"

gcloud auth list
gcloud config get-value project

gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,databaseVersion,region,state,settings.tier,settings.databaseFlags,settings.ipConfiguration)"
~~~

Lệnh này **không** tự kết nối SQL engine, chỉ lấy metadata từ Cloud SQL Admin API. Cần quyền đọc Cloud SQL instance; thiếu quyền không có nghĩa instance không tồn tại.

### 3.4. Bản đồ quyết định nhanh

~~~mermaid
flowchart TD
    A[Ứng dụng lỗi DB hoặc latency cao] --> B{Request mở TCP/auth DB được?}
    B -- Không --> C[Kiểm tra VPC / DNS / IAM / connector / TLS]
    B -- Có --> D{Database đã sát connection limit?}
    D -- Có --> E[Phân tích nguồn session, replica count và max_connections]
    D -- Không --> F{Hikari pending và active đều cao?}
    F -- Có --> G[Kiểm tra leak, long transaction, slow query, pool sizing]
    F -- Không --> H{Query latency và waits cao?}
    H -- Có --> I[Query Insights, locks, CPU/IO, EXPLAIN]
    H -- Không --> J[Kiểm tra network latency, thread pools, app errors]
    E --> K[Mitigate theo blast radius nhỏ nhất]
    G --> K
    I --> K
    C --> K
    K --> L[Verify SLO, DB headroom, RCA]
~~~

## 4. Hiểu đường đi của kết nối

Đường đi logic khi Spring Boot dùng Cloud SQL:

~~~mermaid
flowchart LR
    HTTP[HTTP/gRPC request] --> APP[Java/Spring Boot handler]
    APP --> POOL[HikariCP pool]
    POOL --> CONN[Cloud SQL Java Connector / Auth Proxy / direct TCP]
    CONN --> DB[(Cloud SQL PostgreSQL/MySQL/SQL Server)]
    DB --> LOCK[Locks + transactions]
    DB --> CPU[CPU, memory, I/O]
    APP -. traces .-> APM[Application telemetry]
    POOL -. metrics .-> MON[Monitoring]
    DB -. engine stats .-> INSIGHTS[System/Query Insights]
~~~

Một request có thể chờ lâu ở **bất kỳ** tầng nào:

- Đợi lấy connection từ Hikari.
- Đợi connector/proxy tạo kết nối hoặc refresh credential/certificate.
- Đợi mở TCP/TLS và database authentication.
- Đợi CPU/I/O/lock trong engine.
- Đợi transfer nhiều rows qua network hoặc ứng dụng parse kết quả.

**Cloud SQL Auth Proxy và Cloud SQL Java Connector bảo vệ/kết nối tới Cloud SQL; chúng không mặc nhiên thay thế connection pool ứng dụng.** Pooling phải được cấu hình ở HikariCP hoặc một connection pooler chuyên biệt tương thích.

### 4.1. Connection, session và transaction khác nhau

- **Connection:** một đường nối từ client tới DB, thường gắn với server session và tiêu tốn tài nguyên.
- **Session:** trạng thái kết nối SQL engine, có thể chứa session variables, prepared statements hoặc temp objects.
- **Transaction:** chuỗi thao tác commit/rollback; có thể giữ locks trong một phần thời gian của session.
- **Pool checkout:** một request mượn connection từ pool, dùng rồi trả lại; không nên giữ connection xuyên một HTTP call không cần thiết.

Một session `idle` có thể chỉ là pool chờ request, nhưng `idle in transaction` là dấu hiệu đáng điều tra vì transaction vẫn mở.

## 5. Tính connection budget thay vì đoán pool size

Khi một ứng dụng scale out, tổng connection tiềm năng tăng theo **số instance/pod** và số pool trong mỗi process.

### 5.1. Công thức gần đúng

~~~text
Peak DB sessions có thể tạo ≈
  Σ (max số instance của service i × max pool size mỗi instance i)
+ background jobs / migrations / batch clients
+ admin / monitoring / other services
+ overlapping revisions / deployment surge
~~~

Không quên nhiều Java `DataSource` trong một process hoặc mỗi tenant có pool riêng. Một số frameworks tạo connection ngoài pool khi migration/health check; cần ghi nhận thực tế.

### 5.2. Ví dụ định lượng

Giả sử PostgreSQL có `max_connections` thực tế được kiểm tra là **300**. Nhóm vận hành muốn dành **60** slots cho admin, maintenance, monitoring, các service khác và điều kiện bất thường. Một batch job có thể cần **40** connections. Ngân sách còn cho web service là:

~~~text
300 - 60 - 40 = 200 connections
~~~

Nếu Cloud Run có tối đa **20** instances và Hikari `maximumPoolSize=8`:

~~~text
20 × 8 = 160 connections
Tổng dự kiến = 160 + 60 + 40 = 260
Headroom kế hoạch = 300 - 260 = 40
~~~

Nhưng nếu rollout làm hai revisions đồng thời tăng instance, hoặc Autoscaling nâng 20 lên 40 instances:

~~~text
40 × 8 = 320 connections chỉ cho web service
~~~

Vì vậy, `maximumPoolSize=8` có thể phù hợp ở một giới hạn scale nhưng không phù hợp khi max instances thay đổi. Phải tính **toàn bộ fleet callers**, bao gồm staging nếu dùng cùng database (nên tránh), cron/batch, GKE pods và các services khác.

Con số `300` chỉ là dữ liệu giả định để tính, **không phải giới hạn mặc định** của Cloud SQL. PostgreSQL/MySQL/SQL Server có các giới hạn và hành vi riêng theo tier/engine/configuration.

### 5.3. Cloud Run connection limit: đọc đúng phạm vi

Với **built-in Cloud SQL connection** trên Cloud Run, giới hạn được Google Cloud nêu là **100 connection trên mỗi container instance cho mỗi Cloud SQL database**. Giới hạn cụ thể này **không áp dụng y hệt** cho mọi cách kết nối khác như direct IP, sidecar Cloud SQL Auth Proxy hoặc language connectors.

Dù không bị giới hạn built-in ở một số kiểu kết nối, server Cloud SQL vẫn có `max_connections`/resource limits; mở nhiều connection không đồng nghĩa DB có thể xử lý tốt. Không đặt Hikari pool size=100 chỉ vì tài liệu nhắc giới hạn 100.

## 6. Cloud Monitoring và System Insights

### 6.1. Bắt đầu bằng timeline

Mở **Cloud SQL instance → System Insights** hoặc Cloud Monitoring Metrics Explorer. Chọn cùng timezone và time window với lỗi ứng dụng. So sánh trước/sau deploy và đỉnh tải.

Các nhóm chỉ số đáng xem:

| Nhóm | Diễn giải |
|---|---|
| Network/connections và peak connections | Server connection count tăng tới gần giới hạn? |
| CPU utilization | SQL processing/sort/aggregation nặng hoặc instance quá nhỏ |
| Memory utilization / pressure | Cache nhỏ, memory pressure, query memory |
| Disk utilization, IOPS/throughput | Data scans, temporary files, storage capacity |
| Query latency, database load | Query chậm vì CPU, I/O hay lock |
| Errors và restart/failover | Sự cố hạ tầng, cấu hình hoặc quá tải |
| Transactions/QPS và replication lag | Tải thực tế, ảnh hưởng replica |

Metric name thường gặp cho connection count trong Cloud Monitoring là `cloudsql.googleapis.com/database/network/connections`; xác minh exact metric và labels trong Metrics Explorer cho engine/version đang dùng.

**Chú ý:** khi instance quá tải, một số metrics có thể đến trễ hoặc xuất hiện gap; đừng hiểu gap là database đã khỏe hoặc không có tải.

### 6.2. Liên kết app metrics

Ở ứng dụng Spring Boot, nếu có Actuator + Micrometer instrumentation, các Hikari metrics như số active, idle, pending và timeout giúp phân biệt:

- DB connection count cao + nhiều app pools mở: khả năng tổng budget bị vượt.
- DB connection count thấp + Hikari pending tăng: một pool local bị đầy, có thể do leak hoặc query dài.
- DB connection count cao + CPU thấp + nhiều sessions idle: pool giữ nhiều connections hơn cần thiết.
- DB CPU/I/O/lock cao + Hikari active/pending tăng: slow queries đang làm pool bị giữ lâu.

Tên series/prometheus metric có thể thay đổi theo exporter và version, vì vậy phải xác minh chúng được expose trước khi viết alert.

### 6.3. Log Cloud SQL và Cloud Run

Ví dụ xem logs Cloud SQL gần nhất:

~~~bash
gcloud logging read \
  'resource.type="cloudsql_database" AND severity>=WARNING' \
  --project="$PROJECT_ID" \
  --limit=100
~~~

Đối với Cloud Run, tìm logs của revision liên quan theo service name/labels và time range. Không đưa query text có PII, username, mật khẩu hoặc connection string chứa secret vào ticket không được bảo vệ.

## 7. PostgreSQL: chẩn đoán hết connection

Các lệnh sau chạy trong `psql` bằng database account có quyền xem thống kê phù hợp. Account thường chỉ thấy thông tin giới hạn của các session khác; nếu thiếu quyền, nhờ DBA thực hiện dưới sự phê duyệt.

### 7.1. Giới hạn và số kết nối hiện tại

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;

SELECT count(*) AS all_connections,
       count(*) FILTER (WHERE state = 'active') AS active,
       count(*) FILTER (WHERE state = 'idle') AS idle,
       count(*) FILTER (WHERE state = 'idle in transaction')
         AS idle_in_transaction
FROM pg_stat_activity;
~~~

**Đừng lấy `max_connections - count(*)` làm số slots chắc chắn cấp được cho user mới.** PostgreSQL dành một số connection slots cho vai trò đặc biệt/administration; có thể có các cấu hình reserved slots bổ sung theo version và Cloud SQL.

### 7.2. Phân nhóm theo database, user, app, state

~~~sql
SELECT datname,
       usename,
       application_name,
       state,
       count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC
LIMIT 30;
~~~

`application_name` hữu ích để phân biệt `orders-api`, `billing-worker` và `migration-job`. Hãy gắn application name khi cấu hình JDBC để giảm thời gian RCA.

### 7.3. Tìm transaction lâu và session chờ

~~~sql
SELECT pid,
       usename,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST
LIMIT 30;
~~~

Cần phân biệt `query_age` với thời gian một transaction đã mở, và trạng thái `active` với `idle in transaction`. Khi `query_start` cũ nhưng state idle, nó có thể phản ánh query gần nhất, không nhất thiết query vẫn chạy.

Tránh in toàn bộ cột `query` chứa SQL literal/PII khi không được phép; các query phía trên cố ý không lấy raw SQL.

### 7.4. Tìm blocking sessions

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE array_length(pg_blocking_pids(pid), 1) > 0
ORDER BY transaction_age DESC NULLS LAST
LIMIT 30;
~~~

Nếu nhiều sessions đang chờ cùng một blocker, giải quyết nguồn lock có thể trả lại nhiều Hikari connections. Không tự `pg_terminate_backend` một session chỉ vì lâu: có thể là migration, import, backup hoặc transaction lớn đang chuẩn bị commit.

### 7.5. PostgreSQL và `pg_stat_statements`

Khi extension được hỗ trợ/kích hoạt, `pg_stat_statements` tổng hợp số lần chạy, tổng thời gian, trung bình, rows và I/O của những normalized queries. Kiểm tra cấu hình/version/permission trước khi dùng.

Tùy version:

~~~sql
SELECT queryid,
       calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Câu lệnh này chỉ hợp lệ khi extension đã được bật và schema/column names tương thích phiên bản PostgreSQL. Không kích hoạt extension hoặc đổi database flags giữa P0 mà không đánh giá tác động và approval.

## 8. MySQL: chẩn đoán connection và slow queries

Chạy những truy vấn dưới đây bằng tài khoản MySQL có quyền xem performance status. `SHOW FULL PROCESSLIST` có thể hiển thị query text nhạy cảm; chỉ dùng trong hệ thống quan sát được kiểm soát.

### 8.1. Connection capacity và activity

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';

SHOW FULL PROCESSLIST;
~~~

- `Threads_connected` là tổng client connections hiện tại.
- `Threads_running` phản ánh số threads đang thực thi/không ngủ.
- `Max_used_connections` giúp thấy đỉnh từ khi server ghi nhận counter.
- `Sleep` là thread idle; nhiều Sleep từ các app pods có thể phản ánh pool quá lớn.

Nếu MySQL trả error **1040 Too many connections**, phải xem nguồn connections, tần suất kết nối mới và database flags, không lập tức nâng `max_connections`.

### 8.2. Nhóm user/client

Trên phiên bản MySQL được hỗ trợ và khi có quyền:

~~~sql
SELECT USER, HOST, COUNT(*) AS sessions
FROM information_schema.PROCESSLIST
GROUP BY USER, HOST
ORDER BY sessions DESC
LIMIT 30;
~~~

Host có thể bị NAT hoặc đi qua connector/proxy, nên không luôn ánh xạ một-một tới một Cloud Run instance. Dùng database user riêng, connection attributes/telemetry và deploy timeline để bổ sung.

### 8.3. Performance Schema query digest

Nếu `performance_schema` đã bật và quyền phù hợp:

~~~sql
SELECT DIGEST,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 2)
         AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000, 2)
         AS avg_milliseconds,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Performance Schema timer thường đo bằng picoseconds; kiểm tra units và phiên bản trước khi so số liệu. Dựa vào digest thay vì dán raw SQL literals vào ticket. Một câu truy vấn nhiều lần chạy với latency trung bình vừa phải vẫn có thể tạo tổng database load rất lớn.

### 8.4. Slow query log

Cloud SQL MySQL có thể ghi slow queries khi cấu hình `slow_query_log=on`, `log_output=FILE` và threshold `long_query_time` thích hợp. Log được đưa vào Cloud Logging và có storage/logging cost.

Không bật general log hoặc đặt `long_query_time=0` kéo dài trong lúc production quá tải: có thể tăng I/O/storage và chi phí. Thay đổi database flags cần xác minh có restart, ảnh hưởng SLA hoặc database maintenance.

## 9. SQL Server: active requests và wait types

Cloud SQL for SQL Server dùng hệ thống dynamic management views (DMVs). Các quyền như `VIEW SERVER STATE` hoặc những permission tương đương theo version/edition có thể cần để xem phiên làm việc của người khác.

### 9.1. Đếm user sessions

~~~sql
SELECT COUNT(*) AS user_sessions
FROM sys.dm_exec_sessions
WHERE is_user_process = 1;
~~~

### 9.2. Xem request đang chạy

~~~sql
SELECT TOP (30)
       r.session_id,
       r.status,
       r.command,
       r.cpu_time,
       r.total_elapsed_time,
       r.wait_type,
       r.wait_time,
       r.blocking_session_id
FROM sys.dm_exec_requests AS r
WHERE r.session_id <> @@SPID
ORDER BY r.total_elapsed_time DESC;
~~~

Các giá trị elapsed/wait time thường là milliseconds. Không dùng `KILL` chỉ vì session chạy lâu; một transaction rollback lớn có thể tiếp tục giữ tài nguyên.

### 9.3. Phân loại waits

Một số nhóm thường gặp:

- `LCK_M_*`: chờ lock; kiểm tra transaction gây block.
- `PAGEIOLATCH_*`: chờ đọc pages từ storage, có thể liên quan I/O hoặc cache.
- `WRITELOG`: chờ log flush, có thể liên quan transaction/log throughput.
- `SOS_SCHEDULER_YIELD` và CPU-heavy queries: có thể liên quan CPU pressure và query plan.
- Network-related waits: có thể do client nhận rows chậm, không phải luôn do server thiếu CPU.

Wait type là **gợi ý điều tra**, không phải kết luận nhân quả duy nhất. Query Insights và active queries trong Cloud SQL for SQL Server bổ sung phân tích, nhưng tính năng và quyền terminate session có thể phụ thuộc edition, đặc biệt Enterprise Plus.

## 10. Phân biệt database exhaustion với HikariCP exhaustion

### 10.1. Hikari pool có ba nhóm trạng thái quan trọng

- **Active:** connection đang được mượn.
- **Idle:** connection đang chờ trong pool.
- **Pending:** threads đang chờ connection.

Ví dụ:

~~~text
Cloud SQL sessions: 110 / max_connections 300
Hikari maximumPoolSize: 10
Hikari active: 10
Hikari idle: 0
Hikari pending: 45
~~~

Database **chưa** hết slots, nhưng service này **đã hết connection trong pool**. Nguyên nhân có thể là 10 transaction chậm, leak connection, giữ connection khi gọi HTTP bên ngoài, hoặc pool quá nhỏ so với concurrency thực tế.

Ngược lại:

~~~text
Cloud SQL sessions: ~298 / max_connections 300
Hikari active: 4, idle: 6, pending: 0 (mỗi instance)
Cloud Run instances: 40
~~~

Có thể quá nhiều **những pool nhỏ ở nhiều instances**, mỗi pool giữ idle connections. Tăng `maximumPoolSize` lúc này sẽ làm tình hình xấu hơn.

### 10.2. Connection leak phổ biến trong Java

Một số nguyên nhân:

- `Connection`, `Statement` hoặc `ResultSet` không được close.
- `@Transactional` bao trùm HTTP/gRPC calls sang dịch vụ khác.
- Streaming query/result được giữ qua request lâu hoặc không close.
- Thread chết hoặc exception path bỏ qua cleanup.
- ORM/Open Session in View kéo dài phạm vi session không cần thiết.
- Một số datasource được tạo lặp khi mỗi request khởi tạo bean/client.
- Background tasks chiếm pool nhưng dashboard chỉ nhìn HTTP traffic.

Dùng `try-with-resources` khi thao tác JDBC trực tiếp:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(String orderId) throws SQLException {
        String sql =
            "SELECT 1 FROM orders WHERE order_id = ? LIMIT 1";
        try (Connection c = dataSource.getConnection();
             PreparedStatement statement =
                 c.prepareStatement(sql)) {
            statement.setString(1, orderId);
            statement.setQueryTimeout(2);
            try (ResultSet rs = statement.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

Ví dụ SQL `LIMIT 1` phù hợp PostgreSQL/MySQL, **không phải SQL Server** (SQL Server dùng `TOP (1)`). Đoạn này minh họa kết nối được trả về pool ngay cả khi exception, không phải một query mẫu chạy được trên mọi engine.

### 10.3. Transaction không nên bao trùm external HTTP call

Không nên:

~~~java
@Transactional
public void processOrder(String id) {
    repository.updateStatus(id, "PROCESSING");
    paymentApi.callRemoteService(id); // có thể timeout lâu
    repository.updateStatus(id, "DONE");
}
~~~

Nếu transaction mở qua external call, DB connection và locks có thể bị giữ lâu. Thay bằng quy trình có ranh giới transaction ngắn hơn, idempotency/outbox/saga nếu cần đảm bảo workflow phân tán. Không tự tách transaction nếu nghiệp vụ đòi consistency mà chưa thiết kế cơ chế thay thế.

## 11. Cấu hình HikariCP cho Spring Boot

Ví dụ **minh họa, phải dựa trên connection budget đo thực tế**:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-db
      maximum-pool-size: 8
      minimum-idle: 0
      connection-timeout: 10000
      validation-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
  jpa:
    open-in-view: false
~~~

Ý nghĩa:

- `maximum-pool-size`: giới hạn connection của **mỗi Hikari pool trong một process**, không phải toàn deployment.
- `minimum-idle: 0`: giảm việc giữ idle connections ở môi trường scale rộng; có trade-off cold checkout latency.
- `connection-timeout`: tối đa chờ mượn connection từ pool, không phải timeout SQL query.
- `validation-timeout`: thời gian cho việc xác minh kết nối.
- `idle-timeout`: đóng connection idle theo chính sách của Hikari khi điều kiện áp dụng.
- `max-lifetime`: đổi connection theo chu kỳ; thường đặt ngắn hơn server/network timeout để giảm stale connections.
- `open-in-view: false`: giảm nguy cơ giữ persistence context ngoài transaction khi trả response.

HikariCP `connectionTimeout` tính bằng **milliseconds**. Đừng nhầm với PostgreSQL `statement_timeout`, MySQL statement execution limit hay HTTP request timeout.

### 11.1. Các cấu hình khác đáng kiểm tra

- Connector/driver connect timeout, socket/read timeout, TLS.
- Hikari `keepaliveTime`, `maxLifetime` và server idle timeout để tránh stale connection.
- `spring.datasource.hikari.leak-detection-threshold` chỉ nên bật tạm với threshold hợp lý; transaction hợp lệ chạy lâu cũng có thể báo false positive và in stack trace nhạy cảm.
- JDBC `application_name` (PostgreSQL) hoặc connection attributes hỗ trợ để nhận diện nguồn.
- Cloud SQL Java Connector refresh strategy thích hợp cho serverless; một số hướng dẫn dùng `cloudSqlRefreshStrategy=lazy` để tránh background refresh threads bị CPU throttling.
- Spring `@Transactional(readOnly = true)` là một tín hiệu tối ưu/mục đích; **không tự bảo đảm** mọi write sẽ bị database từ chối.

Không thay đồng thời 10 flags rồi tìm nguyên nhân. Chọn một thay đổi, ghi baseline và theo dõi metrics.

## 12. Cloud Run/GKE autoscaling tạo cơn bão kết nối

Một triển khai serverless có thể hoạt động khi chỉ có 2 containers nhưng vượt giới hạn database khi scale lên 50 containers.

### 12.1. Cloud Run

Các yếu tố cần kiểm tra:

1. `max instances` của service và revision.
2. `min instances` giữ các pools sống sẵn.
3. Request concurrency per instance.
4. Cold start và việc tạo Hikari pool/connector đồng thời.
5. Hai revisions cùng nhận traffic khi rollout.
6. Cloud Run jobs/batch workers dùng chung DB.
7. CPU throttling của request-based billing có thể trì hoãn pool maintenance ở idle container.
8. Cloud SQL built-in connection limit khác với Java connector/sidecar/direct IP.

Đừng chỉ giảm `maximumPoolSize` mà không xem concurrency: nếu mỗi instance xử lý 80 requests đồng thời nhưng pool có 5 connections, request có thể queue lớn. Ngược lại, tăng pool size trên từng instance làm đỉnh tổng database connections tăng.

Các công cụ cân bằng gồm max instances, concurrency, request queue policy, pooled connections, autoscaling của workload nền và admission control. Cần chọn theo p95/p99 latency, transaction duration và database capacity.

### 12.2. GKE

Với GKE, tổng pool ≈ replicas × pools per pod. Kiểm tra HPA scale-up, rolling updates với `maxSurge`, CronJobs và worker concurrency. Nhiều pod cùng restart có thể cố kết nối đồng thời. Node autoscaling không trực tiếp tạo session nhưng tạo điều kiện số pod tăng.

Kết hợp readiness/liveness checks hợp lý: health check liên tục mở JDBC connection mới khi DB đã kiệt quệ sẽ làm tình hình tệ hơn. Readiness có thể phản ánh khả năng phục vụ mà không dùng một transaction nặng.

## 13. Query Insights: tìm SQL tạo database load lớn

Cloud SQL **Query Insights** giúp xem top queries theo thời gian, load, latency, CPU/I/O/lock waits và trong một số edition các query plans/active queries.

Trình tự hiệu quả:

1. Chọn instance và thời điểm sự cố, so với khoảng ổn định.
2. Xem tổng database load và CPU capacity.
3. Lọc theo database, user, client address hoặc application tag khi có.
4. Chọn query fingerprint/digest có **total time** hoặc p95/p99 tăng cao.
5. Phân biệt query chạy nhiều lần với mỗi lần nhanh nhưng tổng tải lớn, và query hiếm nhưng rất chậm.
6. Xem wait breakdown: CPU, I/O, lock.
7. Xem query plan sample/historical plan nếu được hỗ trợ.
8. Đối chiếu commit, index migration, dữ liệu tăng và app trace.

Lưu ý: Query Insights mặc định thường tổng hợp **completed queries**; khi cần thấy query đang treo chưa kết thúc, chuyển sang **Active queries** hoặc engine views. Các tính năng nâng cao và retention phụ thuộc Enterprise/Enterprise Plus edition, engine và version.

### 13.1. Khi nào không bật thêm telemetry giữa incident?

Bật hoặc thay đổi Query Insights/database flags có thể ảnh hưởng instance, tạo thêm chi phí, lưu SQL text và trong một số trường hợp tạm ngưng operations/restart. Nếu hiện chưa bật, ưu tiên các chỉ số và SQL views đang có trước. Xin approval theo quy trình change management trước khi thay đổi cấu hình giám sát production.

### 13.2. Lưu ý quyền và dữ liệu nhạy cảm

Raw SQL có thể chứa literals: email, token, PII, thông tin đơn hàng. Dùng normalized query fingerprint khi có thể; giới hạn quyền xem, thời gian giữ và xuất log. Không dán full SQL text/parameters vào ticket công khai.

## 14. Đọc query plans mà không tạo rủi ro production

### 14.1. PostgreSQL

~~~sql
EXPLAIN
SELECT order_id, status
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

Ví dụ có giá trị `123` giả định; dùng tham số trong ứng dụng. `EXPLAIN` không có `ANALYZE` cho plan dự kiến, hữu ích để xem scan, join, sort và index selection.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**CẢNH BÁO:** `EXPLAIN ANALYZE` **thực thi truy vấn**. Không chạy không kiểm soát trên production, nhất là với DML, query tốn tài nguyên hoặc dữ liệu thật. Ưu tiên replica/sandbox với dữ liệu đại diện, thời gian giới hạn và approval.

### 14.2. MySQL

~~~sql
EXPLAIN
SELECT order_id, status
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

Xem access type, estimated rows, key được dùng và extra operations. MySQL `EXPLAIN ANALYZE` trên version hỗ trợ cũng **thực thi** statement; tránh chạy trong giờ cao điểm nếu chưa đánh giá chi phí.

### 14.3. SQL Server

Dùng **estimated execution plan** trong công cụ được ủy quyền. Actual execution plan cần chạy query thật và có thể gây tải. Xem index scans/seeks, cardinality estimates, joins, memory grants, spills và blocking; kiểm tra permission trước khi xem plans của sessions khác.

### 14.4. Một query chậm có thể do nhiều nguyên nhân

| Plan/metric | Diễn giải khả dĩ | Cách kiểm tra |
|---|---|---|
| Full table scan, rows examined lớn | Thiếu index hoặc filter không selective | Index, cardinality, statistics |
| Sort/temp file lớn | ORDER BY/GROUP BY tốn memory/I/O | Index order, work memory, pagination |
| Nested loop lặp nhiều | Join sai plan/cardinality | Statistics, indexes, join keys |
| Rows trả về quá nhiều | Query/endpoint trả nhiều data | Pagination, projections, network |
| Lock wait lớn | DML/transaction giữ lock | Blocking sessions và transaction duration |
| CPU cao và query tốn CPU | Expression, join/aggregate nặng | EXPLAIN, optimized SQL |
| I/O wait lớn | Data reads/writes hoặc storage throughput | IOPS, cache hit, disk metrics |

Đừng áp dụng mọi index gợi ý ngay lập tức: index mới có chi phí storage và write overhead, có thể cần build online/maintenance window và có thể gây lock theo engine/version.

## 15. Locks, deadlocks và long transactions

Một query không có plan xấu vẫn chậm nếu đang chờ transaction khác.

### 15.1. PostgreSQL

Dùng `pg_blocking_pids(pid)` để tìm blockers, `pg_stat_activity` để xem `wait_event_type` và transaction age. Đặc biệt chú ý `idle in transaction` lâu: connection đã ngừng chạy SQL nhưng transaction vẫn có thể giữ lock và ngăn vacuum hoạt động hiệu quả.

### 15.2. MySQL

Quan sát processlist và InnoDB transaction/lock views theo quyền và engine version. Với MySQL 8, `performance_schema.data_locks` và `data_lock_waits` có thể giúp liên kết blocking và waiting transactions.

~~~sql
SELECT OBJECT_SCHEMA,
       OBJECT_NAME,
       LOCK_TYPE,
       LOCK_MODE,
       LOCK_STATUS
FROM performance_schema.data_locks
LIMIT 30;
~~~

Truy vấn trên chỉ trả thống kê lock và có thể trống nếu không có dữ liệu/permission phù hợp; điều tra blocking chains bằng `performance_schema.data_lock_waits` ở môi trường có quyền.

### 15.3. SQL Server

Từ `sys.dm_exec_requests`, xem `blocking_session_id` và `wait_type`. Các nhóm `LCK_M_*` phản ánh lock waits. Không dùng `KILL` khi chưa kiểm tra session owner và có plan rollback.

### 15.4. Mitigation an toàn

1. Xác nhận blocker và owner, xác định đó là migration, DDL hay transaction ứng dụng.
2. Giảm concurrency/traffic mới đối với query liên quan.
3. Kiểm tra transaction có thể hoàn tất tự nhiên không.
4. Nếu buộc phải can thiệp, dùng **quy trình phê duyệt** để cancel query hoặc terminate session cụ thể.
5. Dự đoán rollback duration và tác động dữ liệu.
6. Quan sát lock waits và pool recovery sau hành động.

Không restart database chỉ vì thấy một lock. Restart có thể gây thêm downtime và connection storm sau khi instance trở lại.

## 16. CPU, memory và I/O saturation

### 16.1. CPU

CPU cao thường gắn với QPS tăng, query plan scan/sort nặng hoặc quá nhiều concurrent queries. Cần nhìn **database load theo query** và request rate, không nâng machine tier ngay nếu một query regression từ deploy có thể được rollback.

### 16.2. Memory

Nhiều connections tiêu tốn memory; PostgreSQL còn có per-backend process overhead. Heavy sorts/hash joins, caching và prepared statements ảnh hưởng memory. Instance memory pressure hoặc OOM có thể làm connection thất bại và metrics gap.

Tăng `max_connections` mà không có memory headroom có thể làm database **kém ổn định hơn**. Thường nên giảm pool over-allocation/long transactions trước.

### 16.3. Disk I/O

Full scans, missing indexes, temporary files và large writes làm IOPS/throughput tăng. Cloud SQL instance tier, storage technology và disk configuration ảnh hưởng giới hạn I/O. Đối chiếu I/O wait trong Query Insights với disk metrics, không chẩn đoán từ p95 latency đơn độc.

### 16.4. Network

Client đặt xa region DB có thêm round-trip latency. Một query nhỏ chạy nhiều lần theo N+1 pattern có thể chậm dù mỗi query riêng nhanh. Kết nối cross-region, VPC routing, proxy và DNS cũng tạo overhead; phân biệt thời gian **chờ connection**, **query execution**, và **nhận kết quả**.

## 17. Sửa chậm do ứng dụng và SQL

Một số hướng cải thiện bền vững:

- Thêm index đúng thứ tự predicate/join/sort sau khi xác minh query plan.
- Tránh N+1 ORM fetch, dùng join/batch load có kiểm soát.
- Dùng pagination/limit, không lấy toàn bộ result set vào memory.
- Tránh SELECT `*` khi chỉ cần vài columns.
- Cập nhật statistics/maintenance đúng engine.
- Rút ngắn transaction; không giữ DB transaction khi gọi API ngoài.
- Tách analytical/reporting queries ra khỏi primary khi phù hợp.
- Dùng cache với TTL và invalidation đúng nghiệp vụ.
- Chạy batch theo chunks, tránh một transaction khổng lồ.
- Đặt query timeout theo SLO, có retry phù hợp và idempotency.

**Read replica** giúp giảm một số read load trên primary nhưng không chữa một query plan tệ và có replication lag. Các request cần read-after-write consistency phải được route đúng. Đừng chuyển payment/order writes sang replica.

## 18. Có nên dùng connection pooler trung gian?

### 18.1. Client-side pool

HikariCP giảm chi phí tạo connection mới và tái sử dụng sessions trong mỗi JVM. Phù hợp phần lớn Java services.

Nhưng nếu có hàng trăm serverless instances, mỗi instance giữ một pool riêng, tổng connection vẫn có thể cao.

### 18.2. Managed Connection Pooling cho Cloud SQL PostgreSQL

Cloud SQL for PostgreSQL có **Managed Connection Pooling** trên các cấu hình được hỗ trợ (ví dụ Enterprise Plus, network architecture và maintenance version phù hợp). Pooler trung gian có thể tái sử dụng server connections và hấp thụ spikes từ nhiều clients.

Các điểm cần kiểm tra trước khi bật:

- Khả năng áp dụng cho **Cloud SQL PostgreSQL**, edition/region, networking và connector/proxy version.
- Việc enable có thể **restart database**.
- Pool mode `transaction` có thể không hỗ trợ một số tính năng dựa vào session state, `LISTEN`, session advisory locks, temp tables, hoặc kiểu prepared statements cụ thể.
- Workload có transaction dài có thể không hưởng lợi nhiều.
- `max_connections` của database vẫn giới hạn server connections ở phía pooler.
- Java/JDBC/Hibernate driver, transaction boundaries và session settings phải được test tương thích.

Không bật pooler giữa incident mà chưa có assessment/rollback. Trong một số workload dài hạn, kết nối trực tiếp hoặc session pooling phù hợp hơn transaction pooling.

### 18.3. Cloud SQL Auth Proxy không phải pooler

Cloud SQL Auth Proxy đơn giản hóa kết nối bảo mật và IAM, **không tự thực hiện pooling** như Hikari/PgBouncer/Managed Connection Pooling. Một container dùng proxy vẫn có thể mở nhiều database sessions. Đây là hiểu lầm phổ biến khi Cloud Run dùng Cloud SQL connector.

## 19. Runbook xử lý P0/P1: mitigation với blast radius nhỏ nhất

Ưu tiên **giữ dữ liệu nhất quán** và khôi phục khả năng phục vụ. Trước khi thay đổi, xác định symptom chính và độ tin cậy của giả thuyết.

### 19.1. Những biện pháp tương đối an toàn để cân nhắc

| Tình huống | Mitigation đầu tiên | Cần quan sát |
|---|---|---|
| Sau rollout pool connections tăng đột ngột | Dừng rollout/rollback service theo approval | Số instances, sessions, 5xx |
| Batch job đột ngột tạo 100 connections | Pause job hoặc giảm worker concurrency | DB headroom, backlog |
| Hikari pending cao do query chậm | Giảm request concurrency, xử lý query/blocker | Pending, p95, lock waits |
| Một query mới chiếm CPU/I/O | Rollback feature/query path hoặc rate-limit | CPU/I/O, top queries |
| Connection churn trong Cloud Run | Giảm max instances, tune pool/minIdle | Connection count, error rate |
| DB instance thiếu capacity thật | Lập kế hoạch scale tier/HA phù hợp | Restart/downtime, CPU, latency |
| Data migration khóa bảng lâu | Dừng hoặc xử lý migration theo runbook | Lock wait, schema state |

**Không tăng `max_connections` thành một phản xạ.** Giới hạn cao hơn có thể khiến RAM bị cạn và quá tải nặng hơn.

### 19.2. Can thiệp session là biện pháp cuối

`pg_cancel_backend`, `pg_terminate_backend`, MySQL `KILL QUERY/CONNECTION` hoặc SQL Server `KILL` có thể hủy transaction của user, tạo rollback lâu, làm mất phiên làm việc hoặc ảnh hưởng dữ liệu đang xử lý. Bài này không hướng dẫn chạy các lệnh đó. Nếu cần, DBA phải xác định PID/session, owner, mục đích và được phê duyệt theo incident protocol.

### 19.3. Đừng tạo connection storm sau khắc phục

Sau khi restart/rescale/failover, hàng trăm pods có thể reconnect cùng lúc. Dùng jitter, exponential backoff, cap concurrency và pool initialization phù hợp để tránh vòng lặp “DB vừa sống lại → kết nối ào tới → lại quá tải”.

## 20. Phân biệt lỗi connectivity với exhaustion

Không phải lỗi mở connection nào cũng do giới hạn số lượng.

| Lỗi hoặc dấu hiệu | Nhánh điều tra |
|---|---|
| DNS resolution failed | Tên host, private DNS, connector config |
| TCP timeout / connection refused | Network route, firewall, private IP, instance state |
| IAM permission denied | `cloudsql.instances.connect`, service account, IAM DB auth nếu dùng |
| Invalid DB user/password | Database user, Secret Manager, rotation |
| TLS/CA verification failed | Certificates, connector/driver version |
| Cloud SQL Auth Proxy Admin API quota | Cloud SQL Admin API quota khi scale, connector logs |
| Connection pool acquisition timeout | Hikari active/idle/pending và long transactions |
| Server too many connections | Engine sessions vs max connections |
| Query deadline exceeded | Slow SQL, lock, CPU/I/O hoặc client timeout |

Tách **Google Cloud IAM** với **database authentication**: `roles/cloudsql.client` giúp kết nối qua connector/proxy theo điều kiện dịch vụ, nhưng database user vẫn phải được phép đăng nhập (password/IAM DB authentication). VPC chỉ giải quyết reachability, không cấp SQL permissions.

Với private IP, cần Cloud Run Direct VPC egress/Serverless VPC Access hoặc GKE/VPC path phù hợp. Với Cloud SQL Java Connector, kiểm tra instance connection name `PROJECT:REGION:INSTANCE` và configuration, không nhầm với database name.

## 21. Thiết kế alert và dashboard phòng ngừa

Một dashboard tối thiểu:

1. Cloud SQL current/peak connections và tỷ lệ so với giới hạn thực tế.
2. CPU, memory, disk, I/O và engine errors.
3. Query Insights load/top normalized queries, lock waits.
4. Java Hikari active/idle/pending, connection acquire timeouts.
5. Cloud Run/GKE instance/pod counts, concurrency, request rate.
6. HTTP/gRPC 5xx, p95/p99 latency và database dependency span latency.
7. Cloud SQL connector/proxy errors, reauthentication/refresh failures.
8. Thay đổi deployment, database flags, schema migration và autoscaling.

Ví dụ **ngưỡng minh họa**:

| Alert | Mục tiêu |
|---|---|
| Peak DB connections trên 75% giới hạn nhiều phút | Cảnh báo sớm để điều tra |
| Trên 90% cùng 5xx hoặc acquire timeout | Ưu tiên sự cố cao |
| Hikari pending tăng liên tục | Phát hiện pool pressure trước timeout |
| p99 SQL tăng gấp 3 baseline | Phát hiện slow query regression |
| Lock waits tăng và nhiều transactions dài | Phát hiện blocker sớm |
| Cloud Run instance count tăng trong khi DB headroom giảm | Cảnh báo nguy cơ connection storm |

Không triển khai ngưỡng chung cho mọi database. Lấy baseline từng engine/instance/tier, đảm bảo metric có đúng nhãn instance và có logic chống false positives. Alert chỉ có giá trị nếu có owner/on-call và runbook.

## 22. Diễn tập lab an toàn

Trong **sandbox project/database** được cho phép, tạo dữ liệu giả và chuẩn bị hai bài thử độc lập. Không gây quá tải trên Cloud SQL production.

### 22.1. Bài thử A — pool exhaustion tại ứng dụng

Thiết lập một Spring Boot service có Hikari `maximumPoolSize=2` trên database sandbox. Cho hai request cùng chạy một transaction chậm có kiểm soát, request thứ ba cần checkout connection.

Quan sát:

- Hikari active=2, idle=0, pending tăng.
- Request thứ ba chờ tối đa `connectionTimeout` rồi timeout.
- Database có thể vẫn **rất xa** `max_connections`.
- Khi hai transaction kết thúc, pool phục hồi.

Sau thử nghiệm, khôi phục cấu hình và đóng test connections. Không tạo memory leak thực hoặc giữ transaction vô hạn.

### 22.2. Bài thử B — slow query

Tạo bảng dữ liệu thử nghiệm không chứa PII, chạy một truy vấn thiếu index trong sandbox và dùng Query Insights/EXPLAIN để so sánh trước/sau index.

Quan sát:

- Query latency và rows examined thay đổi.
- CPU/I/O và query plan có thay đổi rõ không.
- Hikari active/pending có giảm khi query ngắn hơn không.
- Index mới có làm write cost tăng không.

Dùng mức dữ liệu nhỏ, giới hạn timeout và không chạy `EXPLAIN ANALYZE` trên bảng production.

### 22.3. Bài thử C — server connection budget

Dùng **tính toán và metric** để mô phỏng 5, 20, 40 Cloud Run instances với pool sizes 5/8/10. Không thật sự mở hàng trăm connections tới database chia sẻ. Xem khi nào tổng lý thuyết vượt giới hạn và đề xuất max instances/concurrency.

## 23. Case study: Orders API chậm và báo lỗi Hikari

### 23.1. Hiện trạng

Một ứng dụng Java/Spring Boot trên Cloud Run dùng Cloud SQL PostgreSQL. Các thông số **giả định**:

- Database instance có `max_connections=300`.
- 20 Cloud Run instances ở giờ cao điểm.
- Hikari `maximumPoolSize=10`, `minimumIdle=10`.
- Một job báo cáo định kỳ tạo thêm 40 sessions.
- Incident xảy ra ngay sau một release thêm truy vấn tra cứu đơn hàng.

Sau release, p99 của `GET /orders` tăng từ 150 ms lên 6 giây, Hikari pending tăng và HTTP 503 xuất hiện.

### 23.2. Điều tra

1. Database đang có 250 connections, **chưa** vượt 300.
2. Hikari của nhiều instances có active=10, idle=0 và pending lớn.
3. Query Insights cho thấy một normalized query mới chiếm phần lớn thời gian.
4. `pg_stat_activity` có nhiều active sessions chờ I/O, ít lock waits.
5. EXPLAIN trong sandbox cho thấy scan nhiều rows vì thiếu composite index và trả quá nhiều cột.
6. Release mới đồng thời tăng Cloud Run max instances, khiến tổng số pool connections tăng.

**Kết luận:** root cause là query regression + connection amplification. Hikari timeout là triệu chứng phía ứng dụng, không phải bằng chứng duy nhất rằng PostgreSQL đã hết slots.

### 23.3. Mitigation và fix

- Ngắn hạn: rollback release theo approval, giảm request burst/max instances nếu phù hợp và theo dõi Hikari pending/5xx.
- Trung hạn: tối ưu query, index/pagination theo query plan và dữ liệu đại diện; test lại p95/p99.
- Dài hạn: pool sizing theo budget, `minimumIdle` thấp hơn cho serverless nếu phù hợp, alert theo peak connections + Hikari pending, review concurrency khi thay autoscaling.
- Kiểm tra ranh giới transaction và ứng dụng có giữ connection xuyên outbound HTTP không.

Sau rollback, cần đo **thời gian ứng dụng phục vụ bình thường**, không chỉ số connections giảm.

### 23.4. Bảng RCA mẫu

~~~text
Incident: INC-2026-EXAMPLE
Started at (UTC): YYYY-MM-DD HH:MM
Affected: orders-api GET /orders, Cloud SQL PostgreSQL
Symptoms: p99 increase, Hikari pending, 503
Customer impact: [measured request failures / duration]

Evidence:
- Cloud Run revision and scale timeline
- DB connection count, CPU/IO charts
- Hikari active/idle/pending
- Query Insights normalized fingerprint
- Read-only DB session checks

Root cause:
- Query plan regression + amplified concurrency

Contributing factors:
- Hikari minimumIdle/maximumPoolSize not re-budgeted
- No alert on pending checkouts

Mitigation:
- Approved rollback / rate limit

Long-term actions:
- Index/query optimization
- Pool budget and autoscaling guardrail
- Regression load test
- Runbook/alerts update

Verification:
- 5xx back to baseline
- p95/p99 within SLO
- DB sessions with headroom
- No pending pool timeouts
Owner: [team]
Follow-up date: [date]
~~~

## 24. Những anti-pattern thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Tăng `max_connections` ngay khi thấy Hikari timeout | Có thể thêm memory pressure mà không giải quyết leak | Kiểm tra app pool và DB sessions riêng |
| Dùng chung một pool size cho mọi service | Budget không phản ánh concurrency/tải | Tính theo workload/replicas |
| Không tính Cloud Run revisions và jobs | Connection storms lúc rollout | Headroom + rollout policy |
| Cloud SQL Auth Proxy được coi là pooler | Nhiều sessions phía DB không bị giới hạn | Cấu hình Hikari hoặc pooler được hỗ trợ |
| Đọc `Threads_connected` nhưng bỏ `Threads_running` | Không phân biệt idle/active | Xem processlist và query latency |
| `@Transactional` bao quanh HTTP calls | Giữ connection và locks lâu | Rút ngắn transaction / saga |
| Debug bằng raw SQL chứa PII | Rò rỉ dữ liệu | Normalized queries, redact logs |
| `EXPLAIN ANALYZE` trên DML production | Thực thi và thay đổi dữ liệu | Dùng EXPLAIN hoặc sandbox |
| Kill tất cả idle sessions | Phá connection pools và gây reconnect storm | Identify owner, controlled drain |
| Restart DB khi có một blocker | Downtime không cần thiết | Lock diagnostics và targeted mitigation |
| Tăng Cloud Run max instances mà không xem DB | Vượt connection budget | Quản lý concurrency và pools |
| Dùng pooler transaction mode cho session state tùy tiện | Query/app behavior sai | Compatibility test, session mode nếu cần |
| Chỉ nhìn CPU, không nhìn lock/I/O | Chẩn đoán thiếu | Query Insights + wait breakdown |
| Có Query Insights nhưng chỉ xem queries đã hoàn tất | Bỏ sót query đang treo | Active queries và engine views |
| Retry không giới hạn | Gây thêm tải lúc DB lỗi | Backoff, jitter, retry budgets |
| Chỉ xác nhận DB “up” sau mitigation | 5xx/latency vẫn cao | SLO + business-flow verification |

## 25. Checklist chẩn đoán production

### A. Phạm vi và bằng chứng

- [ ] Xác định project/instance/engine/version/region và người chịu trách nhiệm.
- [ ] Ghi thời điểm UTC, release/migration gần nhất và business impact.
- [ ] Thu thập Cloud SQL connections/CPU/memory/I/O, app 5xx/p99.
- [ ] Thu thập Hikari active/idle/pending/timeouts.
- [ ] Có dashboard/logs/trace được lọc PII và credential.

### B. Đúng nhánh lỗi

- [ ] Phân biệt network/auth với pool checkout hoặc server connection limit.
- [ ] Xác minh `max_connections`/giới hạn engine thực tế, reserved slots.
- [ ] Kiểm tra số sessions theo app/db/user và concurrent workloads.
- [ ] Kiểm tra transaction dài, blockers, CPU/I/O waits.
- [ ] Xác minh query fingerprint, plan/index và biến động QPS.
- [ ] Tính connection budget cho tất cả replicas/revisions/jobs.

### C. Mitigation và prevention

- [ ] Mọi thay đổi có approval và rollback path.
- [ ] Không kill sessions/restart DB khi chưa hiểu tác động.
- [ ] Đã cân nhắc giảm concurrency, rollback query/deploy hoặc pause batch.
- [ ] Hikari pool size/minIdle/lifetime được kiểm tra theo budget.
- [ ] Retry/backoff và idempotency phù hợp.
- [ ] Database flags/pooler thay đổi được thử trên staging trước.
- [ ] Dashboard và alerts có owner/on-call.

### D. Xác nhận phục hồi

- [ ] 5xx trở về mức bình thường.
- [ ] Request p95/p99 theo SLO.
- [ ] DB còn headroom, không phát sinh connection storm mới.
- [ ] Hikari pending và acquire timeout giảm.
- [ ] Không còn blocking transaction bất thường.
- [ ] Không có mất dữ liệu hoặc side effect trùng.
- [ ] Đã lập RCA và action items có deadline.

## 26. Bài tập thực hành

### Bài tập 1 — Phân biệt hai loại exhaustion

Cho dữ liệu sau:

~~~text
Cloud SQL PostgreSQL connections: 80 / 300
Hikari maximumPoolSize: 6
Hikari active: 6
Hikari idle: 0
Hikari pending: 21
HTTP 5xx: 8%
~~~

Hỏi: đã có đủ bằng chứng rằng server hết kết nối chưa? Cần những metric/query nào tiếp theo? Nêu ít nhất ba giả thuyết.

### Bài tập 2 — Connection budget

Một Cloud SQL có giới hạn connection thực tế 400, cần giữ 80 slots cho maintenance/other apps, có 25 Cloud Run instances và 10 GKE pods dùng cùng database. Hãy chọn pool size cho mỗi loại sao cho tổng dự kiến còn headroom, sau đó thử kịch bản Cloud Run scale lên 50 instances.

### Bài tập 3 — Query Insights

Một normalized query được gọi 50.000 lần/giờ, trung bình 40 ms, tổng thời gian 2.000 giây; một query khác gọi 10 lần/giờ, mỗi lần 3 giây, tổng thời gian 30 giây. Hãy giải thích vì sao chỉ tối ưu query có p99 cao nhất có thể bỏ qua nguồn database load lớn.

### Bài tập 4 — Long transaction

Một session PostgreSQL `idle in transaction` 12 phút, nhiều sessions khác bị `Lock` wait. Hãy trình bày chuỗi chẩn đoán **read-only**, điều kiện escalation và các rủi ro khi terminate session.

### Bài tập 5 — Cloud Run deployment

Trước deploy, service có 10 instances, Hikari pool size 8; release mới có thể mở đến 40 instances, và có job dùng 50 DB connections. Hãy tính budget, lập release guardrail và giải thích vì sao rollout hai revisions đồng thời phải được tính.

### Bài tập 6 — Đề xuất RCA

Viết RCA gồm timeline, symptom, root cause, contributing factors, mitigation, verification và các action item tránh tái phát. Chỉ sử dụng SQL digests/metrics đã loại dữ liệu nhạy cảm.

## 27. Câu hỏi tự kiểm tra

1. Hikari connection acquisition timeout có chứng minh Cloud SQL đã đạt `max_connections` không?
2. `Threads_connected` và `Threads_running` khác nhau ra sao?
3. Vì sao nhiều PostgreSQL sessions `idle in transaction` nguy hiểm hơn idle bình thường?
4. Query Insights top queries khác active queries ở điểm nào?
5. Vì sao một query có trung bình nhanh vẫn có thể chiếm nhiều database load?
6. Khi nào PostgreSQL `EXPLAIN ANALYZE` có rủi ro?
7. Vì sao Cloud SQL Auth Proxy không thay thế connection pool?
8. Làm sao Cloud Run max instances ảnh hưởng tổng số sessions?
9. Vì sao tăng `max_connections` có thể làm database kém ổn định?
10. Transaction giữ trong lúc gọi payment API ngoài hệ thống gây ra vấn đề gì?
11. Vì sao lỗi network/IAM phải được phân biệt khỏi pool exhaustion?
12. Khi nào nên thử Managed Connection Pooling trên PostgreSQL?
13. Transaction pooling có thể làm hỏng những tính năng dựa trên session nào?
14. Query lock waits và CPU saturation có cùng cách sửa không?
15. Vì sao slow query log cần cân nhắc chi phí và dữ liệu nhạy cảm?
16. Tại sao retry sau timeout của một payment write phải có idempotency?
17. Những metrics nào chứng minh incident đã thực sự được xử lý?
18. Một RCA tốt phải ghi nguyên nhân và phòng ngừa khác symptom như thế nào?

## Tài liệu tham khảo

- [Cloud SQL for PostgreSQL: Diagnose issues](https://docs.cloud.google.com/sql/docs/postgres/diagnose-issues)
- [Cloud SQL for PostgreSQL: Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL for PostgreSQL: Debug connection issues](https://docs.cloud.google.com/sql/docs/postgres/debugging-connectivity)
- [Cloud SQL for PostgreSQL: System Insights](https://docs.cloud.google.com/sql/docs/postgres/use-system-insights)
- [Cloud SQL for PostgreSQL: Query Insights](https://docs.cloud.google.com/sql/docs/postgres/using-query-insights)
- [Cloud SQL for PostgreSQL: Active queries](https://docs.cloud.google.com/sql/docs/postgres/monitor-active-queries)
- [Cloud SQL for PostgreSQL: Managed Connection Pooling](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling)
- [Cloud SQL for PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud SQL: Quotas and limits](https://docs.cloud.google.com/sql/docs/quotas)
- [Cloud SQL for MySQL: Debug connection issues](https://docs.cloud.google.com/sql/docs/mysql/debugging-connectivity)
- [Cloud SQL for MySQL: Query Insights](https://docs.cloud.google.com/sql/docs/mysql/using-query-insights)
- [Cloud SQL for MySQL: Database flags and slow query log](https://docs.cloud.google.com/sql/docs/mysql/flags)
- [Cloud SQL for SQL Server: Query Insights](https://docs.cloud.google.com/sql/docs/sqlserver/using-query-insights)
- [Cloud SQL for SQL Server: Active queries](https://docs.cloud.google.com/sql/docs/sqlserver/monitor-active-queries)
- [HikariCP configuration](https://github.com/brettwooldridge/HikariCP)
- [Spring Boot: Data SQL/JDBC](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [PostgreSQL monitoring statistics](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [MySQL Performance Schema reference](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html)
- [SQL Server sys.dm_exec_requests](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-requests-transact-sql)

