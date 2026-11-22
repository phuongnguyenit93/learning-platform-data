# max_connections, pool kết nối và áp lực bộ nhớ PostgreSQL

Số lượng kết nối PostgreSQL ảnh hưởng trực tiếp đến khả năng phục vụ đồng thời, mức tiêu thụ bộ nhớ và độ ổn định của hệ thống. Tăng `max_connections` có thể giúp ứng dụng vượt qua lỗi “too many connections”, nhưng cũng tạo thêm backend processes, shared-memory requirements và cơ hội để nhiều truy vấn cùng cấp phát bộ nhớ. Nếu connection count tăng nhanh hơn năng lực CPU, I/O và RAM, throughput có thể giảm trong khi latency tăng.

Cách thiết kế thường hiệu quả là giới hạn số backend connections mà PostgreSQL thực sự phải phục vụ, dùng connection pool để tái sử dụng các kết nối đó, và điều tiết lượng request chờ ở tầng ứng dụng hoặc pooler. Mục tiêu không phải đạt một con số kết nối thật lớn; mục tiêu là giữ đủ concurrency để tận dụng tài nguyên database mà không tạo contention và memory pressure.

Bài học thuộc chương **Tối ưu tài nguyên**, tập trung vào:

- Hiểu `max_connections`, backend process và các connection slots dành riêng.
- Phân biệt client connections, server connections và pool connections.
- Ước tính memory theo backend, active queries và các memory-consuming operations.
- Dùng application pool và PgBouncer để tái sử dụng kết nối.
- Chọn session, transaction hoặc statement pooling theo semantics ứng dụng.
- Tính tổng connection budget từ số replicas, workers và pool sizes.
- Điều tiết concurrency, queueing, timeouts và retry behavior.
- Theo dõi connection states, pool wait time, memory, CPU và I/O.
- Xử lý connection storms, leaks, idle transactions và failover.
- Xây dựng runbook sizing và rollout có thể đo lường.

> **Nguyên tắc:** `max_connections` là giới hạn bảo vệ tài nguyên của PostgreSQL. Connection pool quyết định bao nhiêu client được chia sẻ một tập server connections. Bộ nhớ thực tế phụ thuộc cả số backend lẫn số operation đang chạy; `work_mem` không đơn giản là một khoản cấp phát cố định cho mỗi connection.

## 1. PostgreSQL xử lý connection như thế nào?

Trong kiến trúc PostgreSQL truyền thống, mỗi client connection được phục vụ bởi một server backend process riêng. Backend chịu trách nhiệm xử lý protocol, session state, transaction và truy vấn của client đó.

Khi ứng dụng mở connection:

1. Client thiết lập TCP/TLS connection tới PostgreSQL.
2. PostgreSQL xác thực user/database và kiểm tra giới hạn connection.
3. Một backend process phục vụ session.
4. Backend xử lý statements và transaction trong session.
5. Khi client disconnect, backend kết thúc và tài nguyên session được giải phóng.

Một session có thể ở trạng thái `active`, `idle`, `idle in transaction` hoặc chờ một resource. Một backend đang `idle` vẫn chiếm connection slot và giữ một phần tài nguyên, dù không chạy query tại thời điểm đó.

### 1.1. Một connection không đồng nghĩa một query đang chạy

Ứng dụng có thể giữ connection trong pool để tái sử dụng. Tại một thời điểm:

- 500 client connections có thể tồn tại.
- Chỉ 20 client đang thực thi query.
- Các connection còn lại đang idle hoặc chờ ở pool.
- PostgreSQL vẫn phải quản lý backend/session tương ứng với các server connections.

Đây là lý do pooler có thể giúp: hàng trăm hoặc hàng nghìn client connections được multiplex qua một số lượng server connections nhỏ hơn.

### 1.2. Connection và process model

Backend process có chi phí về:

- Process metadata và kernel resources.
- Private memory contexts.
- Stack và session state.
- Socket buffers và network state.
- Transaction state, locks và snapshots khi cần.
- Executor memory khi query chạy.

Ngoài backend client, PostgreSQL còn có các background processes/workers như checkpointer, background writer, WAL writer, autovacuum workers, logical replication workers và parallel query workers. Chúng có cấu hình/capacity riêng và không nên bị nhầm với số client connections mà ứng dụng đang mở.

### 1.3. Vì sao quá nhiều connection làm hệ thống chậm?

Khi số backend tăng:

- Context switching và scheduler overhead có thể tăng.
- Nhiều truy vấn có thể tranh CPU cùng lúc.
- Nhiều backend có thể đọc/ghi cùng storage.
- Memory contexts và per-query memory có thể cộng dồn.
- Lock contention có thể tăng.
- Connection establishment/authentication có thể tạo burst.
- Monitoring và process management phải theo dõi nhiều sessions hơn.

Thêm connection chỉ tăng khả năng concurrency. Nó không tự tăng CPU cores, RAM bandwidth, disk IOPS hay khả năng xử lý lock của database.

## 2. max_connections là gì?

`max_connections` là tham số giới hạn số client connections đồng thời được chấp nhận bởi PostgreSQL. Giá trị được cấu hình ở server level.

Kiểm tra giá trị hiện tại:

```sql
SHOW max_connections;
```

Hoặc:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name = 'max_connections';
```

### 2.1. Thay đổi max_connections

Ví dụ cấu hình:

```conf
max_connections = 250
```

Thay đổi `max_connections` yêu cầu restart PostgreSQL. Trên managed database, thao tác có thể thông qua parameter group và có trạng thái pending reboot.

Không tăng tham số trong production chỉ để xóa lỗi tạm thời. Trước tiên, xác định connection nào đang chiếm slots, vì sao chúng tồn tại và liệu pool/leak/idle transaction có phải nguyên nhân.

### 2.2. max_connections không phải mục tiêu concurrency

Giả sử database được cấu hình:

```conf
max_connections = 300
```

Điều đó không có nghĩa nên cho 300 truy vấn nặng chạy cùng lúc. Nó chỉ đặt trần connection. Số truy vấn active phù hợp có thể nhỏ hơn đáng kể và phải được xác định bằng benchmark, CPU, storage latency, lock waits và workload mix.

### 2.3. Reserved connection slots

PostgreSQL có các slots dành riêng để quản trị viên vẫn có thể kết nối khi connection capacity gần cạn.

- `superuser_reserved_connections`: slots dành cho superusers.
- `reserved_connections`: trên PostgreSQL 16 trở lên, slots dành cho roles có quyền `pg_use_reserved_connections`.
- Các slots còn lại dành cho kết nối thông thường.

Ví dụ kiểm tra:

```sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections'
)
ORDER BY name;
```

`reserved_connections` và predefined role `pg_use_reserved_connections` phụ thuộc phiên bản; trên server cũ hơn, tham số/role này có thể không tồn tại.

Tổng số slots thông thường có thể sử dụng xấp xỉ:

```text
ordinary_slots =
    max_connections
    - superuser_reserved_connections
    - reserved_connections
```

Công thức chỉ áp dụng khi server có tham số `reserved_connections`. Giữ lại các slots quản trị có ý nghĩa vận hành: nếu mọi slots đều bị app chiếm, DBA có thể không đăng nhập được để chẩn đoán.

### 2.4. Quyền sử dụng reserved slots

Trên các version hỗ trợ:

```sql
GRANT pg_use_reserved_connections TO ops_role;
```

Chỉ cấp quyền này cho role vận hành đáng tin cậy. Đây là cơ chế khẩn cấp, không phải cách cấp thêm capacity thường xuyên cho application roles.

### 2.5. Connection limits theo role và database

Ngoài giới hạn toàn server, PostgreSQL cho phép đặt connection limit ở role/database:

```sql
ALTER ROLE app_service CONNECTION LIMIT 80;
ALTER DATABASE appdb CONNECTION LIMIT 120;
```

`-1` nghĩa là không đặt giới hạn riêng. Các giới hạn này có thể hữu ích để tránh một role hoặc database chiếm hết capacity. Chúng không thay thế pooler và cần được tính cùng các kết nối của jobs, migrations, monitoring và administration.

Kiểm tra role limits:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolconnlimit
FROM pg_roles
ORDER BY rolname;
```

Kiểm tra database limits:

```sql
SELECT
    datname,
    datconnlimit
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;
```

## 3. Connection budget trước khi tăng giới hạn

Trước khi chọn `max_connections`, hãy lập inventory tất cả nguồn mở connection tới database.

### 3.1. Các nguồn kết nối thường gặp

| Nguồn | Ví dụ | Điều cần tính |
| --- | --- | --- |
| Web/API replicas | Nhiều instance của orders-api | Pool size trên mỗi instance |
| Worker processes | Queue consumers, schedulers | Số worker × pool mỗi worker |
| Batch/ETL | Import, export, analytics jobs | Peak concurrency và thời gian chạy |
| Admin tools | psql, IDE, dashboard | Giới hạn và reserve riêng |
| Migration jobs | Schema deployment | Kết nối trong thời gian rollout |
| Monitoring | Exporters, health checks | Có mở session liên tục hay liên tục tạo mới |
| Poolers | PgBouncer server connections | Tổng pool connections tới PostgreSQL |
| Replication clients | Logical subscribers/CDC | Capacity WAL sender/replication và client connection |
| Other services | BI, reporting, integrations | Peak load và owner |

Connection budget cần tính cả deployments đồng thời, rolling updates, autoscaling và failover. Nếu có 10 replicas bình thường nhưng rollout tạm thời chạy 15 replicas, pool tổng có thể tăng 50%.

### 3.2. Công thức tổng pool connections

Nếu mỗi process có một application pool:

```text
application_pool_total =
    app_replicas × processes_per_replica × pool_size_per_process
```

Ví dụ:

- 6 replicas.
- Mỗi replica chạy 2 worker processes.
- Mỗi process có pool tối đa 8 connections.

```text
6 × 2 × 8 = 96 application connections
```

Nếu còn 20 connections cho background jobs, 10 cho monitoring/admin và 15 cho deployment/batch peak, tổng demand có thể lên khoảng 141 server connections nếu kết nối trực tiếp tới PostgreSQL.

Đây là phép tính capacity planning, không phải khuyến nghị mở đủ 141 connections. Nếu dùng PgBouncer, số client connections và server connections là hai đại lượng khác nhau.

### 3.3. Pool size nhân với số replicas

Một lỗi phổ biến là cấu hình pool size theo một process nhưng quên tổng số process.

Ví dụ:

```text
12 app replicas × 4 worker processes × pool_size 15
= 720 potential server connections
```

Một pool size 15 nghe có vẻ nhỏ, nhưng khi nhân với 48 process thì vượt xa capacity của nhiều database.

### 3.4. Dự phòng cho rollout và autoscaling

Tính thêm:

- Số replicas tối đa theo autoscaling.
- Rolling deployment có surge capacity.
- Job chạy theo lịch trùng giờ cao điểm.
- Worker retry khi broker/database gặp sự cố.
- Failover có thể làm client reconnect đồng loạt.
- Admin cần truy cập khi incident xảy ra.

Đặt pool limits và connection limits theo maximum topology có thể xuất hiện, không chỉ theo trạng thái bình thường.

## 4. Áp lực bộ nhớ từ connections

Connection count ảnh hưởng memory theo nhiều lớp. Một mô hình tốt cần phân biệt memory dùng chung, memory riêng của backend và memory chỉ được cấp khi query thực hiện một operation.

### 4.1. Shared memory

Các cấu trúc dùng chung có thể bao gồm:

- `shared_buffers`.
- WAL buffers.
- Lock tables và shared metadata.
- Shared statistics hoặc structures của extensions.
- Các cấu trúc nội bộ phụ thuộc configuration.

Một số shared-memory requirements phụ thuộc `max_connections`, `max_locks_per_transaction`, worker settings và extension configuration. Tăng `max_connections` có thể làm shared-memory requirements tăng và cần restart.

### 4.2. Backend private memory

Mỗi backend có process state và memory contexts riêng. Memory này thay đổi theo session và query:

- Parser/planner/executor state.
- Tuple and expression state.
- Memory contexts cho protocol/session.
- Cấu trúc quản lý transaction.
- Buffers nội bộ và allocations của extensions.
- Memory cho sort/hash operations.

Một backend idle thường dùng ít memory hơn một backend đang chạy query phức tạp, nhưng vẫn có baseline cost.

### 4.3. work_mem không phải memory cố định cho mỗi connection

`work_mem` là giới hạn memory cơ bản cho mỗi sort hoặc hash operation trước khi operation có thể spill ra temporary files. Một query có thể có nhiều operations cùng lúc.

Ví dụ:

- Một query có 2 sorts và 1 hash join.
- Một số operations có thể cùng cần memory.
- Query chạy parallel có thể có workers thực thi các operations tương ứng.
- Hash operations có thể dùng mức dựa trên `hash_mem_multiplier` trên các version hỗ trợ.

Vì vậy, không nên tính memory bằng cách đơn giản `max_connections × work_mem`, cũng không nên bỏ qua khả năng nhiều operations cùng cấp phát.

### 4.4. Ví dụ memory pressure từ work_mem

Giả sử:

- `work_mem = 16MB`.
- 30 queries đang active.
- Trung bình mỗi query có 2 memory-intensive operations cùng lúc.

Ước tính thô:

```text
30 × 2 × 16 MB = 960 MB
```

Đây là envelope minh họa cho sort-like operations. Hash operations có thể dùng `work_mem × hash_mem_multiplier`; parallel workers và các operations khác có thể làm peak lớn hơn. Đây không phải dự đoán chính xác RSS của PostgreSQL.

### 4.5. Các tham số memory khác

| Setting | Phạm vi sử dụng | Lưu ý |
| --- | --- | --- |
| `shared_buffers` | Shared buffer cache | Cấp phát ở mức instance |
| `work_mem` | Mỗi sort/hash operation | Có thể có nhiều operations/query và nhiều queries đồng thời |
| `hash_mem_multiplier` | Hash operation so với work_mem | Có trên các version hỗ trợ |
| `maintenance_work_mem` | Maintenance operations như index build và một số DDL | Có thể có nhiều maintenance tasks |
| `autovacuum_work_mem` | Memory của mỗi autovacuum worker khi được đặt | `-1` thường dùng `maintenance_work_mem` |
| `temp_buffers` | Temporary tables trong session | Cấp phát khi session sử dụng temp tables |
| `logical_decoding_work_mem` | Logical decoding buffering | Có thể ảnh hưởng spill/streaming của decoding |
| `wal_buffers` | WAL write buffering | Shared memory |
| `effective_cache_size` | Planner estimate về cache khả dụng | Không cấp phát memory |

### 4.6. temp_buffers

`temp_buffers` là local buffers cho temporary tables của từng session, được cấp phát khi session cần dùng temporary tables. Nhiều sessions dùng temp tables có thể làm memory footprint tăng.

Không tăng `temp_buffers` toàn cục chỉ vì một query tạo temp table lớn. Xem temp table lifecycle và query design.

### 4.7. maintenance và autovacuum concurrency

Một database có thể đồng thời chạy autovacuum workers, index builds, VACUUM/ANALYZE thủ công và DDL. Các operations này có thể sử dụng memory riêng.

Đặc biệt, nếu `autovacuum_work_mem` không được đặt riêng và dùng `maintenance_work_mem`, số workers đồng thời cần được tính trong memory budget. Không cộng `maintenance_work_mem` chỉ một lần nếu nhiều operations có thể chạy cùng lúc.

### 4.8. Shared buffers và OS page cache

`shared_buffers` không phải toàn bộ cache của database. PostgreSQL còn dựa vào filesystem cache của hệ điều hành. Trên Linux, memory usage cần xem cả shared memory, process private memory và page cache.

Cộng RSS của tất cả backend có thể đếm lặp shared pages. Khi phân tích process memory, ưu tiên PSS/private memory hoặc công cụ phù hợp của OS; không kết luận memory demand bằng cách cộng RSS một cách máy móc.

### 4.9. Memory budget tổng thể

Một mô hình lập ngân sách:

```text
RAM budget =
    PostgreSQL shared memory
  + backend private memory
  + active query operation memory
  + autovacuum/maintenance memory
  + background worker memory
  + OS and filesystem cache
  + monitoring/sidecar/agent memory
  + safety headroom
```

Các thành phần có thể chồng lấp hoặc chia sẻ pages; công thức là khung phân loại để không bỏ sót nguồn tiêu thụ. Cần đo thực tế trên server tương tự production.

## 5. Tại sao tăng max_connections có thể làm giảm throughput?

Một database thường có điểm concurrency tối ưu. Trước điểm đó, tăng số truy vấn active giúp tận dụng CPU/I/O. Sau điểm đó, thêm concurrency chủ yếu tăng contention và queueing.

### 5.1. CPU contention

Nếu nhiều backend runnable cùng lúc trên ít CPU cores:

- Scheduler phải luân phiên nhiều processes.
- Context switches tăng.
- CPU cache locality giảm.
- Query latency tăng.
- Tổng throughput có thể đi ngang hoặc giảm.

### 5.2. I/O contention

Nhiều truy vấn cùng đọc/ghi có thể:

- Đẩy storage queue depth lên cao.
- Tăng disk latency.
- Tạo nhiều random reads.
- Tăng temporary file I/O.
- Làm checkpoint và background writes cạnh tranh với query I/O.

### 5.3. Lock contention

Nhiều connections cùng cập nhật các rows/hot keys có thể chờ locks. Tăng số backend không làm transaction conflict biến mất; nó có thể làm số sessions chờ tăng.

### 5.4. Memory pressure và swapping

Khi tổng memory demand vượt RAM:

- Kernel reclaim memory và evict cache.
- Page faults tăng.
- PostgreSQL có thể bị swap.
- Latency trở nên không ổn định.
- OOM killer có thể kết thúc process trên host/container.

Swapping database backend thường là dấu hiệu capacity đã vượt giới hạn thiết kế. Không nên xem swap như memory reserve bình thường cho workload database.

### 5.5. Connection storms

Sau network outage hoặc failover, hàng trăm ứng dụng có thể reconnect cùng lúc. Mỗi connection mới cần TCP/TLS/authentication và backend setup. Retry không có backoff có thể tạo một cơn bão kết nối đúng lúc database đang hồi phục.

## 6. Connection pooling là gì?

Connection pool giữ một tập connections để tái sử dụng thay vì mở/đóng kết nối cho từng request.

Luồng cơ bản:

1. Request yêu cầu một connection từ pool.
2. Nếu có connection idle, pool cấp cho request.
3. Nếu pool đã đầy, request chờ trong queue hoặc timeout.
4. Khi transaction/session hoàn tất, connection được trả về pool.
5. Request tiếp theo tái sử dụng connection đó.

### 6.1. Lợi ích

- Giảm connection establishment và authentication overhead.
- Giới hạn số server connections.
- Tái sử dụng backend processes.
- Tạo queue/backpressure khi traffic burst.
- Giúp quản lý connection lifetime và health.
- Giảm nguy cơ app replicas mở quá nhiều connections.

### 6.2. Pool không tự sửa query chậm

Nếu một query mất 20 giây, pool chỉ khiến request khác chờ lâu hơn khi slots đã bận. Pooling giúp điều tiết concurrency, nhưng cần tối ưu query và xử lý lock/I/O bottlenecks riêng.

### 6.3. Application pool và external pooler

Có hai lớp phổ biến:

- **Application-side pool:** nằm trong process ứng dụng, ví dụ HikariCP, Npgsql pool, psycopg pool hoặc node-postgres pool.
- **External pooler:** service đứng giữa app và PostgreSQL, ví dụ PgBouncer.

Có thể dùng cả hai. Tuy nhiên, phải tính tổng pool sizes và hiểu mỗi lớp giữ client/server connection nào.

## 7. Session, transaction và statement pooling

External pooler có thể chia sẻ server connections theo các chế độ khác nhau. Chế độ quyết định khi nào một server connection được trả về pool.

### 7.1. Session pooling

Ưu điểm:

- Session state được giữ.
- Temporary tables có thể tồn tại qua nhiều transactions.
- Session-level `SET`, prepared statements, `LISTEN/NOTIFY` và advisory locks có thể hoạt động theo semantics PostgreSQL thông thường.
- Dễ tương thích với ứng dụng legacy.

Nhược điểm:

- Client idle vẫn chiếm server connection.
- Giảm khả năng multiplexing.
- Không giải quyết tốt trường hợp hàng nghìn clients idle.

### 7.2. Transaction pooling

Server connection được cấp cho client trong một transaction và trả lại pool sau COMMIT/ROLLBACK.

Ưu điểm:

- Nhiều client sessions chia sẻ một tập server connections.
- Client idle ngoài transaction không giữ server connection.
- Hữu ích cho web/API request ngắn, transaction độc lập.

Hạn chế:

- Session state không được bảo đảm giữa transactions.
- Session-level `SET`/`RESET`, temporary tables sống qua transaction, session advisory locks, `LISTEN`, session cursors và một số prepared statement patterns có thể không tương thích.
- Connection affinity không được giữ qua nhiều transactions.
- Ứng dụng phải trả connection đúng lúc và không giữ transaction quá lâu.

Một số PgBouncer versions mới hỗ trợ protocol-level prepared statements trong transaction pooling khi cấu hình `max_prepared_statements` phù hợp. Không suy rộng điều này sang mọi kiểu SQL `PREPARE` hoặc session state; xác minh phiên bản và driver.

### 7.3. Statement pooling

Server connection được trả về sau mỗi statement. Đây là chế độ hạn chế nhất.

- Không cho phép multi-statement transaction theo semantics thông thường.
- Không phù hợp với phần lớn ORM/application workflows cần transaction.
- Chỉ cân nhắc cho workload đơn giản, độc lập và đã kiểm thử kỹ.

### 7.4. So sánh

| Hành vi | Session | Transaction | Statement |
| --- | --- | --- | --- |
| Giữ server connection giữa transactions | Có | Không | Không |
| Hỗ trợ multi-statement transaction | Có | Có | Không theo semantics thông thường |
| Session-level settings | Có | Không bảo đảm | Không bảo đảm |
| Temp table qua nhiều transactions | Có | Không bảo đảm | Không phù hợp |
| Session advisory locks | Có | Không bảo đảm | Không phù hợp |
| LISTEN/NOTIFY listener lâu dài | Có | Không phù hợp | Không phù hợp |
| Multiplexing client lớn lên server pool nhỏ | Thấp | Cao | Cao nhất |
| Phù hợp app web stateless | Có | Thường tốt | Chỉ trường hợp đặc biệt |

### 7.5. Dùng SET LOCAL trong transaction pooling

Nếu ứng dụng cần setting theo transaction, có thể dùng `SET LOCAL` bên trong transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SET LOCAL search_path = app, public;

SELECT * FROM app.orders WHERE order_id = 42;

COMMIT;
```

`SET LOCAL` hết hiệu lực khi transaction kết thúc, phù hợp hơn với transaction pooling. Cần kiểm tra ứng dụng/ORM có mở transaction đúng cách và không dựa vào session state sau đó.

## 8. Cấu hình PgBouncer

PgBouncer là connection pooler phổ biến cho PostgreSQL. Nó nhận nhiều client connections và phân phối chúng tới một số lượng server connections được giới hạn.

### 8.1. Cấu trúc cấu hình cơ bản

Ví dụ `pgbouncer.ini`:

```ini
[databases]
appdb = host=127.0.0.1 port=5432 dbname=appdb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432

pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
reserve_pool_size = 5
reserve_pool_timeout = 3

server_idle_timeout = 600
server_lifetime = 3600

auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
```

Đây là ví dụ cấu hình khái niệm. Authentication, TLS, file paths, user management và service supervision phải theo môi trường triển khai thực tế.

### 8.2. max_client_conn

`max_client_conn` giới hạn số client connections tới PgBouncer. Nó không phải số backend connections tới PostgreSQL.

Ví dụ PgBouncer có thể nhận 1.000 clients nhưng chỉ giữ một pool server connections nhỏ hơn nhiều, tùy pool size và database/user combinations.

Cần tính file descriptor limits, socket buffers và memory của PgBouncer khi đặt `max_client_conn` lớn.

### 8.3. default_pool_size

`default_pool_size` là số server connections tối đa cho mỗi pool theo database/user pair, trừ khi có override. Vì vậy, không nhân đơn giản một con số pool size mà bỏ qua số cặp user/database hoạt động.

Nếu có 5 databases và 4 users cùng tạo pools, tổng server connections có thể lớn hơn nhiều so với `default_pool_size`. Dùng `max_db_connections` và `max_user_connections` khi cần giới hạn tổng theo database/user.

### 8.4. reserve_pool_size

`reserve_pool_size` cho phép mở thêm server connections khi client phải chờ lâu hơn `reserve_pool_timeout`. Đây là capacity dự phòng cho burst ngắn, không phải pool size bình thường.

Nếu reserve pool liên tục được dùng, hãy điều tra query duration, pool sizing hoặc DB capacity.

### 8.5. Giới hạn theo database/user

Các options như:

- `max_db_connections`.
- `max_user_connections`.
- `default_pool_size`.
- `reserve_pool_size`.

giúp kiểm soát tổng connections theo scope. Availability và chi tiết semantics tùy PgBouncer version; kiểm tra `SHOW CONFIG` hoặc tài liệu đúng version.

### 8.6. Server connection lifetime

`server_idle_timeout` đóng server connections idle quá thời gian. `server_lifetime` giới hạn tuổi thọ server connection. Các giá trị quá thấp có thể gây connection churn; quá cao có thể giữ connections lâu hơn mong muốn.

Đừng đặt lifetime cực ngắn như một biện pháp mặc định cho connection leaks. Xác định nguyên nhân và dùng pool reset/health policies phù hợp.

### 8.7. Kiểm tra PgBouncer

PgBouncer admin console cung cấp các lệnh:

```sql
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
SHOW CONFIG;
SHOW DATABASES;
```

Tên fields và một số command có thể khác theo version. `SHOW POOLS` thường cho thấy client active/waiting và server active/idle; đây là dữ liệu quan trọng để xác định pool saturation.

## 9. Thiết kế application connection pool

Application pool thường được cấu hình theo process. Nếu service chạy nhiều processes, mỗi process có thể có một pool riêng.

### 9.1. Một pool cho mỗi process

Tránh tạo pool mới cho mỗi HTTP request. Pool nên có vòng đời gắn với application process:

- Tạo khi service startup.
- Dùng lại cho requests.
- Có maximum size.
- Có acquisition timeout.
- Có health validation phù hợp.
- Đóng pool khi process shutdown.

### 9.2. Pool size không bằng số request đồng thời

Nếu app nhận 1.000 HTTP requests đồng thời nhưng chỉ 20 requests cần truy cập database cùng lúc, pool size 1.000 có thể gây hại. Request không dùng database không cần giữ connection.

Thiết kế concurrency theo số database operations đồng thời và thời gian giữ connection.

### 9.3. Ví dụ HikariCP

```properties
maximumPoolSize=12
minimumIdle=2
connectionTimeout=3000
idleTimeout=600000
maxLifetime=1800000
validationTimeout=1000
```

Các giá trị là ví dụ. `maximumPoolSize` là giới hạn pool của một HikariCP instance. Nếu có 10 application instances, tổng potential connections có thể là 120.

### 9.4. Ví dụ node-postgres

```javascript
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 12,
  min: 2,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 3000
});
```

Đảm bảo `pool` là singleton theo process, không tạo instance mới trong mỗi request handler. Luôn release client trong `finally` nếu dùng `pool.connect()`.

### 9.5. Ví dụ psycopg pool

```python
from psycopg_pool import ConnectionPool

pool = ConnectionPool(
    conninfo="postgresql://app_service@db/appdb",
    min_size=2,
    max_size=12,
    timeout=3
)
```

Credential thực tế nên lấy từ secret manager/environment theo policy. Đóng pool trong application shutdown hook.

### 9.6. Pool acquisition timeout

Nếu pool đầy, request chờ. Cần đặt timeout rõ ràng để queue không tăng vô hạn.

Pool timeout nên ngắn hơn request deadline còn lại. Nếu request chỉ có budget 2 giây nhưng chờ connection 10 giây, hệ thống đã vi phạm deadline trước khi query chạy.

### 9.7. Idle timeout và max lifetime

- Idle timeout đóng connections không được dùng trong một khoảng thời gian.
- Max lifetime recycle connection sau tuổi thọ tối đa.
- Validation/keepalive giúp phát hiện connection stale.
- Connection lifetime nên phối hợp với network/load balancer/database timeout.

Recycling quá thường xuyên làm tăng authentication/TLS churn; quá hiếm có thể giữ stale sessions lâu hơn.

## 10. Chọn pool size bằng workload, không bằng phỏng đoán

Không có một pool size đúng cho mọi PostgreSQL instance. Cần đo throughput và latency khi thay đổi concurrency.

### 10.1. Little's Law

Little's Law:

```text
L = λ × W
```

Trong đó:

- `L`: số requests trung bình đang ở trong hệ thống.
- `λ`: throughput/arrival rate trung bình.
- `W`: thời gian trung bình một request ở trong hệ thống.

Ví dụ database xử lý 300 operations/giây, thời gian service trung bình 20 ms:

```text
L = 300 × 0.020 = 6 concurrent operations
```

Con số 6 là concurrency trung bình theo giả định ổn định. Pool size thực tế cần tính burst, variance, tail latency, transaction duration và headroom. Không lấy p99 request time rồi nhân QPS như thể mọi request luôn chiếm connection suốt thời gian đó.

### 10.2. Đo điểm bão hòa

Benchmark lần lượt với server pool sizes, ví dụ 8, 12, 16, 24 và 32. Ở mỗi mức, đo:

- Throughput (transactions/second).
- p50/p95/p99 latency.
- CPU utilization và run queue.
- Storage latency/queue depth.
- Active sessions và lock waits.
- Memory usage và temporary files.
- Pool wait time và timeout rate.

Chọn vùng gần điểm throughput bắt đầu đi ngang nhưng latency chưa tăng mạnh. Giữ headroom cho burst và maintenance.

### 10.3. Không dùng CPU core count như luật cứng

Số CPU cores là một điểm tham chiếu hữu ích, nhưng query mix quyết định concurrency phù hợp. Query CPU-bound, query I/O-bound, OLTP ngắn và analytical scans có behavior khác nhau.

Benchmark workload thật hoặc representative, thay vì đặt pool size bằng `CPU cores × 2` mà không đo.

### 10.4. Tách active concurrency khỏi open connections

Có thể có 200 server connections nhưng chỉ 15 active queries. Pooling giữ số open connections ổn định, trong khi concurrency thực thi được kiểm soát bởi số server connections đang bận và thời gian transaction.

## 11. Transaction duration và connection occupancy

Một connection được giữ trong suốt transaction. Transaction dài làm giảm số lần pool có thể tái sử dụng server connection.

### 11.1. Giữ transaction ngắn

Không giữ transaction mở trong lúc:

- Chờ user input.
- Gọi external HTTP API.
- Chờ message broker.
- Upload/download file.
- Xử lý batch lớn không cần atomicity.
- Chạy tác vụ CPU lâu không tương tác database.

Pattern không tốt:

```text
BEGIN
  UPDATE database
  call external payment service
  wait 8 seconds
  UPDATE database
COMMIT
```

Pattern tốt hơn thường tách external call và database transaction theo state machine/outbox/saga, tùy business consistency requirements.

### 11.2. idle in transaction

Một session `idle in transaction` giữ transaction mở nhưng không thực thi statement. Nó có thể giữ locks, snapshot và ngăn vacuum cleanup một số dead tuples cũ.

Kiểm tra:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    now() - xact_start AS transaction_age,
    now() - state_change AS idle_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS last_query
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
```

### 11.3. idle_in_transaction_session_timeout

Có thể cấu hình để kết thúc sessions idle trong transaction quá lâu:

```conf
idle_in_transaction_session_timeout = '60s'
```

Chọn timeout theo workload và transaction design. Timeout quá ngắn có thể ngắt legitimate long-running application workflow; timeout quá dài cho phép sessions giữ snapshot/locks quá lâu.

### 11.4. idle_session_timeout

`idle_session_timeout` có thể đóng sessions idle ngoài transaction trên các PostgreSQL versions hỗ trợ. Cần thận trọng với poolers: một session bị server đóng bất ngờ có thể khiến pool phải reconnect và gây churn.

### 11.5. statement_timeout và lock_timeout

Có thể dùng:

```conf
statement_timeout = '30s'
lock_timeout = '3s'
```

- `statement_timeout` giới hạn thời gian statement.
- `lock_timeout` giới hạn thời gian chờ lock trước khi statement lỗi.

Các timeout nên phối hợp với application deadline và retry policy. `lock_timeout` quá thấp có thể tạo lỗi lặp lại khi workload contention bình thường.

## 12. Connection leaks và sử dụng connection đúng cách

Connection leak xảy ra khi application lấy connection từ pool nhưng không trả lại.

### 12.1. Pattern an toàn

Pseudo-code:

```javascript
const client = await pool.connect();

try {
  await client.query('BEGIN');
  await client.query('UPDATE app.orders SET status = $1 WHERE order_id = $2', [
    'paid',
    1001
  ]);
  await client.query('COMMIT');
} catch (error) {
  await client.query('ROLLBACK');
  throw error;
} finally {
  client.release();
}
```

Nếu transaction lỗi, rollback trước khi trả client để connection không quay lại pool trong trạng thái transaction bất thường. Một số thư viện có API transaction wrapper giúp quản lý lifecycle an toàn hơn.

### 12.2. Dấu hiệu leak

- Pool active connections tăng dần và không giảm.
- Idle pool connections ít bất thường.
- Pool acquisition timeout tăng.
- PostgreSQL thấy nhiều sessions `idle` từ một app.
- Connection count tăng sau mỗi request/job.
- App restart làm tình hình tạm thời tốt hơn.

### 12.3. Leak detection

Một số pools hỗ trợ leak detection threshold hoặc logging khi connection bị giữ quá lâu. Bật có mục tiêu trong staging/production canary; log leak có thể tạo volume nếu threshold quá thấp.

### 12.4. Không mở connection trong vòng lặp

Không tạo một connection mới cho mỗi row hoặc mỗi item trong batch. Dùng một connection/transaction phù hợp, batch statements hoặc `COPY` khi cần throughput cao.

## 13. Connection pooling và transaction pooling caveats

Transaction pooling tiết kiệm backend connections nhưng đòi hỏi ứng dụng không dựa vào session affinity.

### 13.1. Session variables

`SET search_path` hoặc `SET timezone` ở session level có thể không còn hiệu lực ở transaction tiếp theo khi client được gán một server connection khác.

Giải pháp:

- Dùng `SET LOCAL` trong transaction.
- Dùng fully qualified object names.
- Cấu hình defaults theo role/database nếu phù hợp.
- Không giả định session state còn sau COMMIT.

### 13.2. Temporary tables

Temporary tables có thể tồn tại theo session. Trong transaction pooling, transaction kế tiếp có thể được cấp một server connection khác, nơi temp table không tồn tại.

Nếu cần temp table, có thể phải thiết kế lại hoặc dùng session pooling. Một số pattern `ON COMMIT DROP` có thể phù hợp với transaction pool trong các trường hợp được hỗ trợ; kiểm tra PgBouncer version và behavior cụ thể.

### 13.3. Prepared statements

Prepared statements có thể phụ thuộc session. PgBouncer có hỗ trợ protocol-level prepared statement tracking ở các versions mới nếu `max_prepared_statements` được cấu hình khác 0. SQL-level `PREPARE` và driver-specific behavior cần được kiểm tra riêng.

### 13.4. Advisory locks

Session-level advisory locks gắn với server session; không phù hợp nếu transaction pooling có thể chuyển client sang backend khác ở transaction sau. Transaction-level advisory locks gắn với transaction và phù hợp hơn trong mô hình này.

### 13.5. LISTEN/NOTIFY

Một listener cần session connection lâu dài để nhận notifications. Dùng dedicated session-pool connection hoặc service listener riêng, không đặt trên transaction pool thông thường.

### 13.6. Cursors và streaming results

Một số cursor/portal workflows yêu cầu session affinity hoặc transaction kéo dài. Kiểm tra driver và pooler mode trước khi sử dụng; streaming result dài cũng giữ connection lâu và ảnh hưởng pool capacity.

## 14. Queueing và backpressure

Pool là nơi tạo queue khi số clients muốn dùng database lớn hơn số server connections có sẵn.

### 14.1. Queue có giới hạn

Một queue hữu ích cần:

- Maximum wait duration.
- Maximum pending requests hoặc bounded queue.
- Timeout khi quá tải.
- Cancellation khi request deadline hết.
- Metrics về queue depth và wait time.

Queue không giới hạn chỉ biến overload thành latency và memory consumption tăng dần.

### 14.2. Pool saturation

Khi pool đầy, client phải chờ. Tăng pool size có thể giảm wait ngắn hạn, nhưng nếu database đã bão hòa thì nó chỉ chuyển queue từ app sang database và làm query latency tăng.

### 14.3. Backpressure ở application

Có thể:

- Giới hạn concurrency theo endpoint/job.
- Dùng bounded worker queues.
- Trả 429/503 hoặc degrade noncritical requests.
- Giảm batch concurrency.
- Pause background jobs trong incident.
- Dùng deadline propagation và cancellation.

### 14.4. Retry storm

Nếu pool timeout hoặc connection refused khiến mọi client retry ngay lập tức, database sẽ nhận burst lớn hơn. Dùng exponential backoff với jitter, retry budget và circuit breaker. Không retry lỗi SQL không transient như constraint violation.

### 14.5. Deadline budget

Một request deadline nên chia thành:

```text
request_budget =
    queue_wait_budget
  + pool_acquire_budget
  + database_execution_budget
  + application_processing_budget
```

Các budget phải nhất quán. Nếu pool acquisition timeout dài hơn request deadline, requests có thể xếp hàng dù caller đã bỏ cuộc.

## 15. Quan sát connections trên PostgreSQL

Cần phân biệt số sessions tồn tại, số query active và số session đang chờ.

### 15.1. Đếm connections theo state

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
```

Query này cần quyền xem các sessions liên quan; users không có quyền phù hợp có thể thấy query text/metadata bị giới hạn.

### 15.2. Tổng số client backends

```sql
SELECT
    count(*) AS total_sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_transaction
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

`backend_type` có trên các PostgreSQL versions hỗ trợ. Trên version cũ, có thể bỏ filter hoặc dùng các cột phù hợp với catalog/view.

### 15.3. Tỷ lệ sử dụng max_connections

```sql
SELECT
    current_connections,
    max_connections,
    round(
        100.0 * current_connections / NULLIF(max_connections, 0),
        1
    ) AS connection_utilization_pct,
    max_connections - current_connections AS nominal_free_slots
FROM (
    SELECT
        count(*) AS current_connections,
        current_setting('max_connections')::int AS max_connections
    FROM pg_stat_activity
) AS s;
```

Đây là tỷ lệ tổng sessions so với configured maximum. Nó không trừ reserved slots và không thay thế kiểm tra các connection limits khác.

### 15.4. Connections theo application

```sql
SELECT
    application_name,
    count(*) AS connections,
    count(*) FILTER (WHERE state = 'active') AS active,
    count(*) FILTER (WHERE state = 'idle') AS idle,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_tx
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY application_name
ORDER BY connections DESC;
```

`application_name` nên được cấu hình nhất quán để query này có giá trị. Nếu tất cả sessions dùng cùng một tên hoặc tên rỗng, khó phân biệt service owners.

### 15.5. Connection age

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    backend_start,
    now() - backend_start AS connection_age,
    state,
    now() - state_change AS state_age
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
```

Connection lâu đời không tự động là lỗi. Dùng age cùng pool policy, state và owner để phát hiện sessions bất thường.

### 15.6. pg_stat_database

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    temp_files,
    temp_bytes
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY numbackends DESC;
```

`numbackends` là số backends hiện đang kết nối tới database. Các counters khác là tích lũy từ lần reset stats hoặc thời điểm khởi tạo; tính delta theo khoảng thời gian để đo rate.

## 16. Quan sát memory và workload

Connection count cần được ghép với memory metrics, không nhìn riêng.

### 16.1. Các nguồn cần theo dõi

- Host/container total memory và available memory.
- PostgreSQL process private memory/PSS.
- Shared memory và shared buffers.
- Swap in/out và major page faults.
- OOM events/container memory limits.
- Active query count và query mix.
- Parallel workers.
- Autovacuum/maintenance concurrency.
- Temporary file bytes.
- Pool server/client connections.

### 16.2. Không cộng RSS một cách ngây thơ

Mỗi backend có thể map shared memory. RSS của nhiều processes có thể tính cùng shared pages nhiều lần. Dùng PSS/private memory hoặc OS metrics phù hợp để tránh đánh giá memory quá cao.

### 16.3. Xem shared_buffers

```sql
SHOW shared_buffers;
```

Đây là cấu hình shared buffer cache của PostgreSQL, không phải toàn bộ memory PostgreSQL sẽ dùng.

### 16.4. Xem memory settings

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'hash_mem_multiplier',
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'temp_buffers',
    'logical_decoding_work_mem',
    'max_connections'
)
ORDER BY name;
```

Không phải mọi tham số đều có trên mọi major version. Dùng query có điều kiện hoặc bỏ những tên chưa tồn tại trong automation đa phiên bản.

### 16.5. Query memory contexts

Các PostgreSQL versions hỗ trợ cung cấp view/hàm để quan sát memory contexts của backend hiện tại hoặc ghi memory contexts của một backend theo quyền thích hợp. Chúng hữu ích khi điều tra một query/backend tăng memory bất thường, nhưng không phải dashboard thay thế host-level memory metrics.

## 17. Sizing max_connections và pool bằng ví dụ

Giả sử một PostgreSQL instance có 16 vCPU và 64 GiB RAM, phục vụ một ứng dụng OLTP.

### 17.1. Xác định connection demand

Topology peak:

| Component | Replicas/processes | Pool max mỗi process | Potential connections |
| --- | ---: | ---: | ---: |
| Orders API | 6 × 2 processes | 8 | 96 |
| Billing API | 3 × 2 processes | 6 | 36 |
| Background workers | 10 processes | 2 | 20 |
| Reporting jobs | 3 jobs | 2 | 6 |
| Admin/monitoring reserve | — | — | 10 |
| **Tổng potential direct connections** | | | **168** |

Nếu tất cả app processes kết nối trực tiếp, database cần capacity cho peak 168 plus operational headroom và reserved slots. Nhưng nếu PgBouncer multiplexes clients, server connections có thể nhỏ hơn đáng kể.

### 17.2. Xác định active query concurrency

Giả sử workload peak có 400 DB operations/s và thời gian service trung bình 15 ms:

```text
L = 400 × 0.015 = 6 average active operations
```

Đây là average concurrency lý thuyết trong điều kiện ổn định. Burst, tail latency và transactions dài có thể làm peak lớn hơn. Benchmark có thể cho thấy pool 16–24 đủ throughput, trong khi pool 100 chỉ làm contention tăng.

### 17.3. Chọn server pool budget

Ví dụ kế hoạch thử nghiệm:

- Application client connections tới PgBouncer: tối đa 500.
- PgBouncer server pool tới PostgreSQL cho appdb: 24.
- Reporting pool riêng: 4.
- Admin/monitoring/direct maintenance: 10.
- Dự phòng slots cho incident và reserved roles.

Các con số chỉ minh họa. Phải cộng server pools của tất cả PgBouncer instances và mọi direct connections; nếu có nhiều PgBouncer nodes, mỗi node có thể mở pool riêng.

### 17.4. Memory envelope

Giả sử 24 active server connections, mỗi query trung bình có 2 memory-intensive operations, `work_mem=16MB`:

```text
24 × 2 × 16 MB = 768 MB
```

Nếu một phần operations là hash, memory allowance có thể cao hơn theo `hash_mem_multiplier`. Parallel workers, maintenance, autovacuum và backend baseline cần tính riêng.

### 17.5. Chọn max_connections

Một giá trị `max_connections` phải đủ cho tổng server connections đã dự trù, bao gồm pooler nodes và direct clients, cộng các slots reserved. Nó không cần bằng số client connections mà PgBouncer nhận.

Trong ví dụ này, database có thể chỉ cần vài chục hoặc một số ít hơn một trăm server slots, tùy topologies thực tế. Benchmark và kiểm tra memory/latency quyết định con số cuối.

## 18. PgBouncer metrics và cách diễn giải

PgBouncer cung cấp metrics để biết clients đang chờ hay server connections đang được sử dụng.

### 18.1. SHOW POOLS

Các trường thường hữu ích gồm:

- `cl_active`: clients đang gắn với server connection.
- `cl_waiting`: clients đang chờ server connection.
- `sv_active`: server connections đang được dùng.
- `sv_idle`: server connections idle trong pool.
- `maxwait`: thời gian client chờ lâu nhất trong pool, theo semantics/version.
- `pool_mode`: chế độ pooling nếu được hiển thị.

Kiểm tra tên cột đúng phiên bản PgBouncer.

### 18.2. SHOW STATS

Thống kê có thể bao gồm transactions, queries, bytes received/sent, average query time, average transaction time và wait time. Dùng delta giữa hai lần scrape để tính rate.

### 18.3. Pool wait time

Nếu `cl_waiting` thường xuyên lớn hơn 0 và `sv_active` chạm pool limit:

- Query/transaction có thể giữ server connection quá lâu.
- Pool size có thể quá nhỏ cho workload.
- Database có thể chậm do CPU/I/O/locks.
- Có thể có transaction leak hoặc client không trả connection.

Tăng pool size chỉ khi database còn headroom và benchmark cho thấy throughput cải thiện.

### 18.4. Server idle nhưng client vẫn chờ?

Kiểm tra pool key (database/user), pool mode, per-database/user caps, paused/suspended databases và limits toàn cục. Có thể server connections idle ở pool khác nhưng không thể được dùng bởi pool đang chờ vì pools được phân tách theo scope.

## 19. Connection limits và workload isolation

Connection limits có thể bảo vệ database khỏi một service chiếm hết capacity.

### 19.1. Role connection limit

```sql
ALTER ROLE reporting_user CONNECTION LIMIT 8;
ALTER ROLE batch_user CONNECTION LIMIT 4;
ALTER ROLE app_service CONNECTION LIMIT 40;
```

Các giới hạn này phải phối hợp với pooler. Nếu PgBouncer dùng một user chung cho server connections, PostgreSQL nhìn thấy role server-side đó chứ không phải từng end-user client identity trong mọi cấu hình.

### 19.2. Database connection limit

```sql
ALTER DATABASE analytics CONNECTION LIMIT 12;
```

Có thể giới hạn reporting/analytics database để bảo vệ OLTP database, nhưng cần tính maintenance, migration và monitoring.

### 19.3. Workload isolation

Các chiến lược khác:

- Dùng role riêng cho batch/reporting.
- Dùng pool riêng và caps riêng.
- Chạy analytical workload trên replica/warehouse.
- Giới hạn concurrency ở job scheduler.
- Dùng statement/lock timeout phù hợp.
- Tách maintenance windows nếu cần.

### 19.4. Connection limit không phải resource governance đầy đủ

Role/database connection limit không giới hạn CPU time, I/O, memory per query hoặc query cost. Một connection duy nhất vẫn có thể chạy query rất nặng. Kết hợp query governance, timeout, workload routing và monitoring.

## 20. Connection storms và reconnect behavior

Connection storm thường xảy ra khi nhiều clients reconnect đồng thời sau một sự cố.

### 20.1. Nguyên nhân

- Database restart/failover.
- Network load balancer reset connections.
- PgBouncer restart.
- Secret/certificate rotation.
- Deployment rolling restart.
- Connection lifetime của mọi clients hết hạn gần cùng lúc.
- Autoscaler tăng replicas nhanh.

### 20.2. Jitter và exponential backoff

Retry policy nên có:

- Exponential backoff.
- Random jitter.
- Maximum retry interval.
- Retry budget.
- Deadline-aware cancellation.
- Circuit breaker hoặc load shedding.

Không cho hàng nghìn clients retry mỗi 100 ms vô hạn.

### 20.3. Warmup có kiểm soát

Khi service startup, không nhất thiết mở ngay toàn bộ pool max size. Có thể khởi tạo min idle thấp rồi tăng theo demand. Điều này giảm connection burst khi rollout nhiều replicas.

### 20.4. Health checks

Health check không nên tạo connection mới cho mỗi lần kiểm tra nếu có thể dùng pool hiện có hoặc health signal thích hợp. Tránh health-check interval quá dày làm chính nó tạo tải.

## 21. Pooler high availability và topology

PgBouncer cũng là một service cần được vận hành.

### 21.1. Nhiều PgBouncer instances

Nếu có N PgBouncer nodes, mỗi node có thể tạo server pools riêng. Tổng server connections có thể xấp xỉ:

```text
total_server_connections =
    sum(server_connections_from_each_pooler)
```

Không cấu hình mỗi node theo toàn bộ database connection budget. Chia budget theo số pooler nodes và dự phòng khi một node fail.

### 21.2. Failover

Khi PostgreSQL failover, server connections cũ có thể mất. Pooler/app phải phát hiện và reconnect. Kiểm tra DNS/service discovery, primary routing và stale connections.

### 21.3. Transaction retry

Không retry transaction có side effects một cách mù quáng nếu không biết transaction đã commit hay chưa. Thiết kế idempotency keys hoặc transaction outcome reconciliation cho các thao tác nghiệp vụ quan trọng.

### 21.4. TLS và authentication

Xác định TLS giữa client→PgBouncer và PgBouncer→PostgreSQL. Hai chặng là hai kết nối riêng. Bảo vệ credentials, certificate rotation và authentication file theo policy.

## 22. Connection pooling với ORM và driver

ORM/driver thường có pool mặc định hoặc pool config riêng.

### 22.1. Không có một pool toàn process nếu framework tạo nhiều clients

Một số frameworks tạo database client theo module/worker. Nếu mỗi module tạo một ORM client mới, tổng pool connections có thể nhân lên.

Dùng singleton hoặc dependency lifecycle đúng framework. Ghi lại số pool instances trong một process.

### 22.2. Serverless và short-lived workers

Serverless functions có thể scale lên hàng trăm instances trong thời gian ngắn. Mỗi instance có pool riêng sẽ tạo connection storm.

Các lựa chọn:

- External pooler/proxy.
- Pool size nhỏ hoặc single connection per instance.
- Reuse execution environment khi có thể.
- Giới hạn concurrency của function.
- Dùng managed connection proxy phù hợp.

### 22.3. Driver timeout settings

Kiểm tra riêng:

- Connection timeout.
- Pool acquisition timeout.
- Socket/read timeout.
- Query/statement timeout.
- Idle timeout.
- Max lifetime.
- Validation timeout.

Không dùng một timeout duy nhất cho mọi giai đoạn.

### 22.4. Pool validation

Validation query quá thường xuyên có thể tạo overhead. Dùng driver-supported connection validation hoặc keepalive phù hợp. Nếu connection đã stale, loại khỏi pool và reconnect thay vì liên tục trả lỗi cho request.

## 23. Capacity planning theo memory

Đặt `max_connections` mà không tính memory có thể gây OOM khi workload peak.

### 23.1. Phân loại memory

| Nhóm | Cách ước tính |
| --- | --- |
| OS reserve | Memory cần cho kernel, agents và host |
| PostgreSQL shared memory | shared_buffers, WAL buffers, lock/shared structures |
| Backend baseline | Đo private memory khi backend idle |
| Active query memory | Số operations đồng thời × work_mem/hash allowance |
| Maintenance | Autovacuum workers, index builds, VACUUM/DDL |
| Parallel workers | Memory và process overhead của workers |
| Other services | PgBouncer, monitoring, backup agents |
| Headroom | Dành cho burst, allocator fragmentation và uncertainty |

### 23.2. Đo backend baseline

Dùng process metrics trên môi trường đại diện để đo private memory của backend idle và active. Tránh lấy một con số cố định từ một server khác vì extensions, libc, build, workload và OS khác nhau.

### 23.3. Đo peak query memory

Chọn workload có:

- Sort lớn.
- Hash joins/aggregates.
- Parallel query.
- Temp table usage.
- DML với triggers.
- Concurrent maintenance.

Theo dõi host/container memory, temp files và latency trong lúc chạy.

### 23.4. Không overcommit memory bằng cấu hình

Một công thức envelope minh họa:

```text
estimated_peak =
    shared_memory
  + backend_baseline × server_connections
  + active_operations × operation_memory_budget
  + maintenance_peak
  + worker_peak
  + OS_and_other_services
```

Đây là ước lượng bảo thủ; shared pages và allocator behavior làm thực tế phức tạp hơn. Dùng benchmark và memory telemetry để hiệu chỉnh.

## 24. Tối ưu connections bằng workload design

Không phải mọi query đều cần một connection riêng lâu dài.

### 24.1. Batch statements

Thay vì gọi database hàng trăm lần cho từng row, dùng batch insert/update hoặc `COPY` khi phù hợp. Giảm round trips và connection occupancy.

### 24.2. Giảm transaction duration

Tách external calls khỏi transaction. Tránh chờ user hoặc queue trong transaction.

### 24.3. Cache hợp lý

Cache read-heavy data có thể giảm query rate. Nhưng cần invalidation/consistency strategy và theo dõi cache stampede.

### 24.4. Read replicas

Read replicas có thể tách một số read workloads khỏi primary. Cần chấp nhận replication lag và đảm bảo query phù hợp với consistency requirements.

### 24.5. Async jobs

Đưa các công việc không cần trả kết quả đồng bộ vào bounded worker queues. Giới hạn worker concurrency để không tạo một pool mới quá lớn.

## 25. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `too many clients already` | Server slots đã đầy | Xem pg_stat_activity, pool totals và reserved slots |
| Pool acquisition timeout | Pool saturation hoặc query giữ connection lâu | Xem queue wait, query duration, transaction age |
| Nhiều idle sessions | Pool quá lớn hoặc app giữ session | Giảm pool, dùng transaction pooling nếu tương thích |
| Nhiều idle in transaction | App quên commit/rollback hoặc transaction quá dài | Sửa lifecycle, timeout và tracing |
| Memory tăng khi connections tăng | Backend baseline và active operation memory | Đo private memory, giới hạn concurrency, tính work_mem |
| CPU cao sau tăng max_connections | Quá nhiều active backends/context switching | Hạ server pool và benchmark |
| Swap/OOM | Memory overcommit hoặc query burst | Giảm concurrency, query memory và maintenance overlap |
| Client chờ nhưng server pool idle | Pool key/cap/mode mismatch | Kiểm tra SHOW POOLS/CONFIG/DATABASES |
| Reconnect storm sau failover | Retry đồng loạt và pool warmup | Backoff jitter, bounded warmup |
| Temp files tăng | Sort/hash spill hoặc query lớn | Đọc plan, xem work_mem và query design |
| Connection count tăng theo thời gian | Leak hoặc nhiều pool instances | Kiểm tra pool lifecycle và release paths |
| Reporting làm chậm OLTP | Shared connection/resource budget | Pool riêng, role caps, replica/warehouse |

## 26. Runbook điều tra connection saturation

**Bước 1 — Xác nhận impact.** Ghi thời điểm, database, application, error rate, pool timeout và user impact.

**Bước 2 — Đếm PostgreSQL sessions.** Dùng `pg_stat_activity` để nhóm theo database, role, application name và state.

**Bước 3 — Phân loại sessions.** Xác định active, idle, idle in transaction, waiting và sessions thuộc admin/monitoring.

**Bước 4 — Đối chiếu max_connections.** Kiểm tra reserved slots, role/database limits và remaining capacity.

**Bước 5 — Kiểm tra pooler.** Xem `SHOW POOLS`, `SHOW CLIENTS`, `SHOW SERVERS` và `SHOW STATS`; tìm client waiters và server saturation.

**Bước 6 — Kiểm tra query/transaction duration.** Xem slow logs, pg_stat_activity, blocking PIDs và transaction ages.

**Bước 7 — Kiểm tra tài nguyên.** Đối chiếu CPU, memory, swap, disk latency, temp files và parallel workers.

**Bước 8 — Giảm tải có kiểm soát.** Pause batch/reporting jobs, giảm app concurrency hoặc giới hạn endpoint không thiết yếu. Tránh kill sessions hàng loạt khi chưa biết transaction owner.

**Bước 9 — Khôi phục pool.** Sửa leak, transaction dài, retry storm hoặc pool topology. Chỉ tăng server pool khi database có headroom và benchmark chứng minh cần thiết.

**Bước 10 — Theo dõi sau incident.** Xác nhận pool wait, active sessions, latency, memory và error rate đã về baseline. Ghi nguyên nhân và capacity action.

## 27. Checklist thiết kế pool

Trước production, trả lời được:

- Có bao nhiêu application replicas ở peak?
- Mỗi replica chạy bao nhiêu processes/workers?
- Mỗi process có bao nhiêu pool instances?
- Tổng client connections tới pooler là bao nhiêu?
- Tổng server connections từ tất cả pooler nodes là bao nhiêu?
- Có direct connections bypass pooler không?
- Pool mode nào được dùng và session features nào phụ thuộc?
- Pool acquisition timeout có phù hợp request deadline không?
- Queue có giới hạn và backpressure không?
- Retry có exponential backoff và jitter không?
- Connection leak có thể phát hiện không?
- Transaction có được commit/rollback và release chắc chắn không?
- Memory budget đã tính work_mem operations và maintenance chưa?
- Có reserve slots cho administration không?
- Failover/reconnect đã được thử nghiệm chưa?
- Metrics nào cảnh báo pool saturation và memory pressure?

## 28. Bài thực hành

Thực hiện trên PostgreSQL lab và PgBouncer test instance. Không tăng `max_connections`, terminate sessions hoặc thay đổi pool production chỉ để thử.

### Bài 1 — Đọc max_connections

Chạy `SHOW max_connections` và giải thích vì sao đây là server limit chứ không phải target concurrency.

### Bài 2 — Xem reserved slots

Kiểm tra `superuser_reserved_connections` và, nếu version hỗ trợ, `reserved_connections`. Tính số slots ordinary còn lại.

### Bài 3 — Connection limits

Đặt role/database connection limits trong lab. Thử mở nhiều sessions và quan sát lỗi khi vượt giới hạn.

### Bài 4 — Đếm sessions

Dùng `pg_stat_activity` đếm active, idle và idle-in-transaction sessions. Nhóm theo application_name.

### Bài 5 — Connection age

Mở sessions trong các khoảng thời gian khác nhau. Tìm backend_start và state_change.

### Bài 6 — Pool size multiplication

Giả lập 8 replicas × 3 processes × pool size 10. Tính potential server connections và đề xuất budget.

### Bài 7 — Application pool lifecycle

Tạo một application pool singleton. Gửi nhiều requests và xác nhận số server sessions không tăng theo từng request.

### Bài 8 — Connection leak

Cố ý không release một client trong lab. Quan sát pool active count và acquisition timeout, sau đó sửa bằng finally/release.

### Bài 9 — Pool acquisition timeout

Làm query giữ connection lâu và tạo requests cạnh tranh. Đo pool wait time.

### Bài 10 — Transaction duration

Mở transaction rồi chờ một khoảng thời gian. Quan sát idle-in-transaction state và transaction age.

### Bài 11 — idle_in_transaction_session_timeout

Cấu hình timeout trong lab. Xác nhận session idle trong transaction bị kết thúc và application xử lý disconnect.

### Bài 12 — statement_timeout và lock_timeout

Tạo query chờ lock trong lab. So sánh behavior của hai timeout.

### Bài 13 — PgBouncer session pooling

Cấu hình session mode. Thử session-level SET và temp table qua nhiều transactions.

### Bài 14 — PgBouncer transaction pooling

Chuyển sang transaction mode. Thử session-level settings và giải thích vì sao không được giả định backend affinity.

### Bài 15 — SET LOCAL

Dùng SET LOCAL trong transaction. Xác nhận setting hết hiệu lực sau COMMIT.

### Bài 16 — Prepared statements

Thử driver prepared statements với PgBouncer transaction mode. Kiểm tra `max_prepared_statements` và version compatibility.

### Bài 17 — Advisory locks

So sánh session-level và transaction-level advisory locks qua transaction pooling trong lab.

### Bài 18 — LISTEN/NOTIFY

Tạo listener lâu dài. Xác định vì sao nó cần dedicated session connection.

### Bài 19 — max_client_conn

Tăng số client connections tới PgBouncer nhưng giữ server pool nhỏ. Quan sát `SHOW CLIENTS` và `SHOW POOLS`.

### Bài 20 — default_pool_size

Tạo nhiều database/user pools. Quan sát tổng server connections và giải thích vì sao pool size có thể được áp dụng theo pool key.

### Bài 21 — reserve pool

Cấu hình `reserve_pool_size` và `reserve_pool_timeout`. Tạo burst client waiters và xem reserve pool được dùng khi nào.

### Bài 22 — max_db_connections

Đặt cap database-level trong PgBouncer. Thử nhiều user pools cùng database.

### Bài 23 — Little's Law

Tạo workload với throughput và mean service time đã biết. Ước tính average concurrency và so với số active sessions.

### Bài 24 — Throughput saturation

Benchmark pool sizes 8, 16, 24 và 32. So throughput, p95 latency, CPU và lock waits.

### Bài 25 — work_mem pressure

Tạo query có nhiều sort/hash operations. Thử work_mem ở các mức khác nhau và quan sát memory/temp files.

### Bài 26 — Parallel query

Chạy query parallel trong lab. Quan sát worker processes và ảnh hưởng tới concurrency/memory envelope.

### Bài 27 — Maintenance overlap

Chạy index build hoặc VACUUM cùng workload query. Theo dõi memory, CPU và I/O.

### Bài 28 — Connection storm

Mô phỏng nhiều clients reconnect đồng thời. So sánh retry ngay lập tức với exponential backoff và jitter.

### Bài 29 — Pooler failover

Restart một PgBouncer test node. Quan sát client reconnect, server pool warmup và error rate.

### Bài 30 — Connection budget

Tạo bảng inventory app replicas, process count, pool sizes, direct connections và reserve. Tính peak capacity.

### Bài 31 — Memory budget

Ước tính shared memory, backend baseline, active operations, maintenance, workers và OS headroom. So với telemetry lab.

### Bài 32 — Role isolation

Đặt connection limit khác nhau cho app/reporting/batch roles. Kiểm tra workload reporting không chiếm toàn bộ budget.

### Bài 33 — Monitoring dashboard

Tạo dashboard connections, pool waiters, active/idle states, idle-in-transaction age, memory, swap và temp bytes.

### Bài 34 — Saturation incident

Tạo pool saturation có kiểm soát. Dùng runbook để tìm bottleneck và khôi phục bằng concurrency limits.

### Bài 35 — Production pool runbook

Viết runbook gồm topology, max_connections/reserved slots, app pool sizing, PgBouncer mode, memory budget, timeout/retry policy, metrics, failover và rollback.

## 29. Tổng kết

Những điểm cốt lõi khi thiết kế **max_connections, pool kết nối và áp lực bộ nhớ**:

1. `max_connections` giới hạn server connections; nó không xác định concurrency tối ưu.
2. Mỗi PostgreSQL client connection có backend/session cost ngay cả khi idle.
3. Giữ reserved slots để DBA/operations có thể truy cập khi hệ thống gần cạn connections.
4. Tính connection budget từ replicas × processes × pool size và mọi direct clients.
5. Pooler tách số client connections khỏi số server connections.
6. Session, transaction và statement pooling có semantics khác nhau; transaction pooling cần ứng dụng tránh phụ thuộc session state.
7. `work_mem` được dùng theo sort/hash operations, không phải một khoản cố định duy nhất cho mỗi connection.
8. Parallel queries, maintenance và autovacuum có thể làm memory peak tăng.
9. Tăng connections quá mức có thể gây CPU contention, I/O queueing, lock waits và swapping.
10. Chọn pool size bằng throughput/latency benchmark và Little's Law như công cụ ước lượng concurrency.
11. Giữ transactions ngắn, release connections chắc chắn và phát hiện leaks.
12. Dùng bounded queues, acquisition timeouts, deadline propagation và retry jitter để xử lý overload.
13. Theo dõi `pg_stat_activity`, PgBouncer pools, memory, temp files, CPU, I/O và connection wait time.
14. Cộng server connections từ tất cả pooler nodes; đừng cấu hình mỗi node theo toàn bộ database budget.
15. Chỉ tăng `max_connections` khi có bằng chứng về capacity và memory headroom.

Một hệ thống PostgreSQL ổn định giữ số server connections trong giới hạn mà database có thể phục vụ hiệu quả. Pooling, queueing và memory budgeting giúp hấp thụ traffic burst mà không biến mỗi request mới thành một backend process và một phần áp lực tài nguyên mới.

## 30. Tài liệu tham khảo chính thức

- [PostgreSQL Connection Settings](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [PostgreSQL Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html)
- [PostgreSQL Memory Configuration](https://www.postgresql.org/docs/current/runtime-config-resource.html#RUNTIME-CONFIG-RESOURCE-MEMORY)
- [PostgreSQL Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)
- [Role Attributes and Connection Limits](https://www.postgresql.org/docs/current/role-attributes.html)
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html)
- [ALTER DATABASE](https://www.postgresql.org/docs/current/sql-alterdatabase.html)
- [Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [EXPLAIN and Query Memory](https://www.postgresql.org/docs/current/using-explain.html)
- [PgBouncer Documentation](https://www.pgbouncer.org/config.html)
- [PgBouncer Features and Pool Modes](https://www.pgbouncer.org/features.html)
- [PgBouncer Administration Console](https://www.pgbouncer.org/usage.html)
- [PgBouncer FAQ](https://www.pgbouncer.org/faq.html)

Các liên kết `current` trỏ tới tài liệu PostgreSQL hiện hành. Reserved connections, memory settings, statistics views và PgBouncer prepared-statement behavior phụ thuộc version. Trước khi triển khai, kiểm tra `SHOW server_version`, `pg_settings`, `SHOW CONFIG` của PgBouncer và tài liệu đúng phiên bản.
