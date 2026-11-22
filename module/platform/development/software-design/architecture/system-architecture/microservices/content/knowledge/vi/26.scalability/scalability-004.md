# Xác định giới hạn từ cơ sở dữ liệu và các dịch vụ phụ thuộc

> **Bối cảnh:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Khả năng mở rộng (Scalability)  
> **Mục tiêu:** Biết cách xác định trần năng lực thực của hệ thống khi database, cache, message broker, API nội bộ hoặc dịch vụ bên thứ ba trở thành điểm nghẽn; chuyển giới hạn kỹ thuật thành ngân sách tải, thiết kế bảo vệ và kế hoạch mở rộng có thể kiểm chứng.

## 1. Mở rộng ứng dụng không có nghĩa toàn hệ thống sẽ mở rộng

Giả sử một API đặt hàng chạy trên 4 replica. Khi tải tăng, đội vận hành tăng lên 12 replica. CPU ở từng replica giảm, nhưng độ trễ p99 của API lại tăng, tỷ lệ timeout DB và 429 từ cổng thanh toán nhiều hơn. Điều này có thể xảy ra vì các replica mới cùng đẩy thêm request đến những tài nguyên **không tăng năng lực tương ứng**: database chính, pool kết nối, một bảng/hàng dữ liệu nóng hoặc quota của Payment API.

~~~text
                        Load Balancer
                             |
           +-----------------+-----------------+
           |                 |                 |
        Order A           Order B           Order C      ... N replicas
           |                 |                 |
           +-----------------+-----------------+
                             |
                  +----------+----------+
                  |                     |
                  v                     v
            Primary Database       Payment Provider
            - CPU / IOPS           - Rate limit
            - Connections          - Concurrency limit
            - Locks                - Latency / downtime
            - Replication          - Quota / cost
~~~

Một tầng có thể **scale out** dễ dàng nhưng hiệu suất đầu-cuối vẫn bị giới hạn bởi dependency dùng chung. Nếu số replica tăng mà tổng throughput gần như không đổi, cần tìm điểm nghẽn nằm ở đâu trước khi tăng tiếp.

**Nguyên tắc trung tâm:** năng lực phục vụ có ích của một request path bị giới hạn bởi tài nguyên bắt buộc chạm ngưỡng sớm nhất, không phải số pod hay số vCPU cộng lại. Phải đo được đường đi của request và tải mà từng dependency thực sự nhận.

## 2. Những khái niệm nền tảng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Throughput | Công việc hoàn tất trong đơn vị thời gian | 700 order/s, 1.500 query/s |
| Latency | Thời gian để hoàn thành một thao tác/request | p95 = 280 ms; p99 = 1,2 s |
| Capacity | Mức tải có thể phục vụ trong các điều kiện và SLO cụ thể | 500 request/s dưới p99 mục tiêu |
| Saturation | Mức độ tài nguyên đang đầy hoặc phải xếp hàng | DB connections used/limit |
| Bottleneck | Thành phần giới hạn throughput hoặc SLO của luồng | DB writer CPU hoặc quota Payment |
| Contention | Nhiều công việc tranh chấp cùng tài nguyên | Lock hàng dữ liệu, hot partition |
| Queueing | Công việc phải chờ khi năng lực xử lý không kịp tải tới | Connection pool wait |
| Fan-out | Một request sinh nhiều lời gọi downstream | 1 request → 6 truy vấn DB |
| Headroom | Phần năng lực dự phòng để chịu burst, failure và rollout | Giữ tải bình thường dưới năng lực đo được |
| Load shedding | Từ chối sớm một phần tải để giữ hệ thống còn hoạt động | Trả 429/503 khi quá capacity |
| Dependency budget | Giới hạn được phân bổ cho mỗi service hoặc tài nguyên | 60 Payment calls/s cho Order |
| Scaling ceiling | Điểm tăng thêm tài nguyên ở tầng hiện tại không còn cải thiện kết quả | Tăng pod nhưng DB lock wait tăng |

**Một con số capacity luôn có điều kiện.** Nói “DB chịu được 10.000 QPS” chưa đủ: truy vấn đọc hay ghi, kích thước dữ liệu, tỷ lệ cache hit, isolation level, số connection, phân bố khóa, p99 mục tiêu, vùng mạng và tỷ lệ lỗi đều ảnh hưởng kết luận.

Capacity không đơn thuần là mức tải cao nhất trước khi process crash. Nếu hệ thống vẫn trả HTTP 200 nhưng p99 lớn hơn cam kết 10 lần, đó không phải capacity đạt SLO.

## 3. Từ request người dùng đến áp lực trên dependency

Một request API có thể phát sinh nhiều đơn vị công việc khác nhau:

~~~text
GET /orders/123
  -> Auth Service:            1 call
  -> Order DB:                2 queries
  -> Customer DB/API:         1 call
  -> Cache:                   1 lookup

POST /orders
  -> Inventory Service:       1 call
  -> Payment Provider:        1 call
  -> Order DB:                3 statements + 1 commit
  -> Event Outbox:            1 row write in transaction
~~~

Nếu 1.000 request/s đều gọi DB trung bình 4 lần, tải tiềm năng đã là 4.000 query/s, chưa kể retry, job nền, read replica và N+1 query. Nhưng không thể suy năng lực chỉ từ số query: query 2 ms trong cache và query 2 giây phải quét toàn bảng có nhu cầu CPU/I/O khác nhau.

### 3.1. Lập dependency graph theo luồng nghiệp vụ

Với mỗi endpoint quan trọng, ghi:

1. Thành phần nào là **bắt buộc** để kết quả đúng?
2. Thành phần nào **tùy chọn** hoặc có thể xử lý bất đồng bộ?
3. Mỗi request tạo bao nhiêu lời gọi đến từng dependency ở p50/p95/p99? Có N+1 hoặc fan-out phụ thuộc dữ liệu?
4. Lời gọi thực hiện **tuần tự**, **song song** hay nằm trong một transaction dài?
5. Mỗi lời gọi dùng tài nguyên gì: CPU, I/O, connection, thread, lock, quota?
6. Có retry, timeout, circuit breaker và fallback ở những tầng nào?
7. Có workload khác dùng chung dependency: báo cáo, batch, migration, consumer, analytics?
8. Nếu dependency chậm hoặc lỗi, request sẽ chờ bao lâu và giữ tài nguyên nào?

Một dependency không quan trọng nhưng bị gọi đồng bộ trong đường nóng có thể vô tình trở thành ràng buộc bắt buộc. Cân nhắc loại khỏi critical path, dùng cache hoặc degrade hợp lệ.

### 3.2. Tính áp lực theo fan-out

Với luồng request loại i có tốc độ đến \(\lambda_i\) request/s và số lời gọi trung bình tới dependency d là \(a_{i,d}\):

\[
Q_d \approx \sum_i \lambda_i a_{i,d}
\]

Đây là mức gọi dự kiến **trước khi tính retry hoặc background traffic**. Với các nhánh có retry, có thể bổ sung hệ số attempts trung bình trên một request nguồn.

Ví dụ 400 GET/s × 2 query + 100 POST/s × 5 statement = 1.300 thao tác DB/s, chưa tính consumer và báo cáo. Nếu mỗi GET có thêm truy vấn theo số lượng item trả về, \(a_{i,d}\) không cố định; phải đo phân phối và input lớn nhất được hỗ trợ.

### 3.3. Cần phân biệt đỉnh tải với trung bình

Trung bình ngày 100 request/s không nói được hệ thống chịu được đợt mở bán 3.000 request/s trong 2 phút. Hãy đo:

- Tốc độ 1 phút, 5 phút, theo giờ; peak concurrent requests.
- Tỷ lệ endpoint và kích thước dữ liệu theo từng luồng.
- Số request nội bộ sinh ra từ mỗi request ngoài.
- Lượng công việc async đến sau mỗi burst.
- Thời gian cao điểm, batch chạy lịch, backup, index build, failover.
- Trạng thái warm cache so với cold start.

Nếu dùng autoscaling, đừng chỉ tính tải trên mỗi instance khi đủ replica; cần tính cả khoảng giữa lúc burst bắt đầu và lúc replica mới ready.

## 4. Nhận diện điểm nghẽn bằng tín hiệu thực

Một thành phần trở thành bottleneck khi thêm tải khiến **độ trễ chờ, saturation hoặc tỷ lệ lỗi** tăng nhanh trong khi throughput hữu ích tăng chậm hoặc ngừng tăng.

### 4.1. CPU, I/O, memory và kết nối không đồng nghĩa

| Tín hiệu | Có thể cho biết | Cần kiểm tra thêm |
|---|---|---|
| CPU DB cao | Query tốn tính toán, parse, sort, index maintenance | Query plan, workload mix, lock, CPU quota |
| Disk IOPS / latency cao | Nhiều random reads/writes, cache miss, log flush | Storage throughput, buffer cache, checkpoint |
| DB connection used gần limit | Nhiều client, pool quá lớn, connection rò rỉ | Active vs idle, pool wait, transaction duration |
| Lock wait / deadlock tăng | Hot row, transaction giữ khóa lâu | Transaction boundaries, index, access ordering |
| Memory/heap hoặc cache pressure | Dataset vượt cache, sort/hash, page churn | Query memory, cache hit, swap/OOM |
| Replica lag tăng | Follower không theo kịp writes hoặc network | Read consistency và khả năng failover |
| Network egress chạm trần | Payload lớn, fan-out cao, cross-region | Bytes/request, compression, topology |
| 429/QuotaExceeded | Dependency áp rate/quota limit | Limit là toàn cụm, per client hay per key? |
| 503/timeout downstream | Dependency quá tải hoặc lỗi | In-flight, queue, retry amplification |
| Queue depth và age tăng | Arrival > service rate, hoặc consumer stuck | Retry/DLQ, partition skew, DB dependency |

**CPU thấp không chứng minh còn capacity.** Database có thể đang chờ lock hoặc storage, thread của ứng dụng có thể đang chờ pool, và API bên thứ ba có thể áp quota ở mức rất thấp trong khi CPU của ta nhàn rỗi.

### 4.2. Quan sát tại cả caller và callee

Caller nhìn thấy: downstream latency, timeout, pool wait, retry, breaker-open, fallback, in-flight.

Callee nhìn thấy: accepted requests, queue, processing duration, resources, reject rate, error causes.

Một API thấy p99 Payment = 3 giây có thể là thời gian chờ lấy HTTP connection 2,5 giây + network 100 ms + provider processing 400 ms. Nếu chỉ đo thời gian phía provider, đội vận hành có thể kết luận sai rằng Payment khỏe nên lỗi không liên quan.

Phải đặt telemetry tại ranh giới:

~~~text
Request accepted
   -> waiting for worker slot
   -> waiting for client connection
   -> DNS/TLS/network
   -> downstream queue
   -> downstream processing
   -> result / retry / error
   -> transaction commit
   -> response delivered
~~~

Không bắt buộc mỗi thư viện cho phép tách mọi mốc; ghi rõ metric có bao gồm connection acquisition, queue và retry hay không.

## 5. Little's Law: tại sao latency cao làm cạn tài nguyên

Trong điều kiện hệ thống ổn định, định luật Little:

\[
L = \lambda W
\]

Trong đó \(L\) là số công việc trung bình đang ở trong hệ thống, \(\lambda\) là tốc độ hoàn tất/đến trung bình (khi ổn định), \(W\) là thời gian trung bình một công việc ở trong hệ thống.

Giả sử Checkout nhận 400 request/s:

- Nếu mỗi request tồn tại trung bình 0,25 giây, số request đồng thời khoảng \(400 \times 0{,}25 = 100\).
- Nếu dependency chậm khiến thời gian tăng lên 1,5 giây mà tải vẫn 400 request/s, nhu cầu đồng thời khoảng \(400 \times 1{,}5 = 600\).

Nếu HTTP worker pool và connection pool chỉ chứa được 150 công việc đồng thời, hệ thống sẽ xếp hàng hoặc từ chối thêm, khiến latency xấu hơn. Đây là cơ chế khiến lỗi tại DB hoặc Payment lan ngược lên các service phía trên.

Giới hạn áp dụng: đây là quan hệ trung bình của hệ thống ổn định; không suy p99 trực tiếp từ công thức, không dùng để giả định backlog luôn hữu hạn khi arrival rate lớn hơn khả năng xử lý.

### 5.1. Utilization cao làm tail latency nhạy cảm

Khi một hàng đợi tiến gần mức sử dụng 100%, thời gian chờ thường tăng mạnh và biến động, đặc biệt khi service time không đồng đều. Đừng chọn capacity mục tiêu ngay sát throughput cực đại đo được.

Ví dụ một DB đạt 2.000 thao tác/s ở p99 3 giây nhưng 1.500 thao tác/s ở p99 180 ms. Nếu SLO yêu cầu p99 dưới 250 ms, capacity hữu ích gần với mức tải thứ hai hơn, dù máy chưa lỗi khi chạy 2.000 thao tác/s.

Headroom còn giúp chịu:
- Bursts và retry.
- Replica chết và traffic chuyển sang nơi còn lại.
- Phần tài nguyên bị dùng cho backup/migration.
- Thay đổi query mix.
- Chi phí giám sát, replication và failover.
- Rollout có cả phiên bản cũ và mới cùng kết nối DB.

Không có một tỷ lệ utilization mục tiêu phổ quát; chọn theo đường cong latency-load thực tế và yêu cầu rủi ro.

## 6. Database: những giới hạn thường gặp

### 6.1. Kết nối (connection limit và pool)

Database thường có số connection giới hạn bởi cấu hình, memory, CPU và kiến trúc kết nối. Connection không phải khả năng xử lý tương đương một query/s; nhiều connection có thể chỉ đang idle, trong khi vài query nặng đã làm DB quá tải.

Cần đo:

- Active connections, idle connections và total connections ở database.
- Waiting threads, connection acquisition timeout và leak ở app pool.
- Thời gian giữ connection, transaction duration, pool pending.
- Max connection, connection reserve cho vận hành, replication, admin.
- Pool limit của tất cả service, job, migration và autoscaling maxReplicas.

Ví dụ database giới hạn 500 connection, giữ 80 cho vận hành và thành phần khác; ngân sách app còn 420. Có 20 replica Orders và 10 replica Reporting, phân bổ dự kiến:

~~~text
Orders:   20 replicas x 12 connections = 240
Reporting:10 replicas x  8 connections =  80
Other services and reserve           = 100
Total planned                        = 420
~~~

Các con số chỉ minh họa phép lập ngân sách. Phải dùng số replica **tối đa** khi autoscaling/rollout, không chỉ số pod đang chạy bình thường. Trong rolling update, maxSurge có thể làm tăng đồng thời số pod và connection. Connection pooler/proxy có thể giúp quản lý kết nối, nhưng không tự tăng năng lực CPU/I/O của database.

**Anti-pattern:** mỗi Pod có maxPoolSize=50, HPA tăng từ 6 lên 30 Pod → tối đa 1.500 connection chỉ từ một service, trong khi DB có 500 connection. Tăng Pod vừa làm API tốn tài nguyên vừa làm DB chậm.

### 6.2. CPU và query execution plan

Một truy vấn không dùng index hợp lý có thể scan hàng triệu row, sort lớn, join tốn memory hoặc tạo temporary data. Khi số request tăng, DB CPU và I/O tăng nhanh hơn kỳ vọng.

Ví dụ API liệt kê đơn theo tenant và trạng thái:

~~~sql
SELECT id, customer_id, total_amount, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT 50;
~~~

Một index tổng hợp có thể được cân nhắc theo engine và phân bố dữ liệu:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Không tự khẳng định index trên luôn tối ưu. Cần xem selectivity, cardinality, tần suất ghi, index-only coverage, plan thực tế và khối lượng dữ liệu. Index thêm cũng làm write/index maintenance tốn tài nguyên.

Phân tích bằng explain/actual execution plan theo khả năng DB (ví dụ EXPLAIN ANALYZE) trong phạm vi kiểm soát; đừng chạy truy vấn nặng trên production chỉ để lấy bằng chứng rồi gây sự cố.

### 6.3. N+1 query và ORM

Ví dụ màn hình trả 100 đơn, ORM đọc danh sách rồi truy vấn từng đơn để lấy payment status:

~~~text
1 query lấy 100 orders
+ 100 queries lấy payment records
= 101 queries cho 1 HTTP request
~~~

Khi 200 request/s, riêng màn hình này có thể phát sinh khoảng 20.200 query/s nếu hành vi trên giữ nguyên. Giải pháp tùy use case: fetch/batch hợp lý, projection đọc, join có kiểm soát hoặc precomputed view. Không dùng join khổng lồ làm nổ số row trả về mà không đo lường.

**Chỉ số cần có:** query count per request, total DB time per request, query p95/p99, slow query digest, rows scanned/returned, buffer/cache hit, plan regressions.

### 6.4. Lock contention và transaction dài

Transaction giữ khóa khi gọi downstream hoặc chờ người dùng có thể chặn hàng loạt thao tác khác. Ví dụ:

~~~text
BEGIN
  UPDATE inventory SET reserved = reserved + 1 WHERE sku = ...
  CALL external payment (đợi 2 giây)
COMMIT
~~~

Nếu DB transaction giữ lock trong lúc gọi Payment, nhiều request cùng SKU có thể xếp hàng. Kiến trúc thường nên giới hạn transaction cục bộ vào phần thao tác DB và dùng state machine/saga cho bước bên ngoài khi đúng nghiệp vụ.

Một hot row như counter toàn hệ thống, inventory SKU nóng hoặc khóa “global tenant state” có thể giới hạn write throughput dù có nhiều replica và index tốt. Cân nhắc phân vùng, atomic operation phù hợp, optimistic concurrency, hàng đợi theo key hoặc redesign data model. Mọi giải pháp phải giữ correctness, đặc biệt chống oversell.

### 6.5. I/O, WAL/redo log và write amplification

Ghi dữ liệu không chỉ là ghi một row: database có thể phải cập nhật index, log giao dịch, replication, fsync, backup/CDC và kiểm tra constraint. Khả năng write scaling có thể bị giới hạn bởi WAL throughput, storage latency hoặc leader serialization.

Đo latency commit, log flush, replication apply lag, disk queue depth, bytes written và hiệu suất checkpoint. Đừng suy write capacity từ benchmark SELECT chỉ đọc dữ liệu đã nằm trong RAM.

### 6.6. Read replicas và replication lag

Read replica có thể san bớt truy vấn đọc nếu hệ thống chấp nhận độ trễ đồng bộ, nhưng:
- Replica không làm tăng write capacity của primary một cách trực tiếp.
- Replica có thể lag khi primary write nhiều hoặc query nặng.
- Đọc ngay sau khi ghi từ replica có thể thấy dữ liệu cũ.
- Failover có thể gây đổi endpoint, connection reset hoặc trạng thái không nhất quán tạm thời.

Với nghiệp vụ cần read-your-writes, chọn primary read, version/watermark hoặc consistency contract phù hợp. Không chuyển mọi read sang replica chỉ vì muốn scale mà bỏ qua semantics dữ liệu.

### 6.7. Sharding và partitioning

Sharding chia dữ liệu/workload thành nhiều đơn vị có thể mở rộng, hữu ích khi một primary đã gần giới hạn CPU/I/O/dung lượng hoặc nhiều tenant có thể cô lập.

Nhưng giới hạn vẫn tồn tại:
- Hot shard/hot key giữ phần lớn tải.
- Cross-shard join/transaction phức tạp và tốn chi phí.
- Rebalance, re-sharding, schema migration và backup khó hơn.
- Chọn shard key theo user/tenant có thể gây lệch tải.
- Global sequence, uniqueness hoặc aggregate cần hợp đồng mới.

**Đánh giá sharding sau khi hiểu access pattern**, không dùng nó như bước đầu tiên thay cho sửa query, lock, pool và transaction.

## 7. Dịch vụ phụ thuộc: những giới hạn ngoài database

### 7.1. HTTP/gRPC service nội bộ

Một downstream API cũng có:
- Max requests/s hoặc active requests.
- Thread/event-loop/connection pool.
- CPU, memory, socket, outbound network.
- Queue capacity và request deadline.
- Shared database hoặc cache riêng.
- Limits từ gateway/service mesh.

Một request Orders gọi Inventory, Fraud và Payment; nếu Fraud p99 tăng, Orders có thể chờ dù Inventory và Payment khỏe. Khi nhiều nhánh chạy song song và phải chờ tất cả, tail latency của request bị chi phối bởi nhánh chậm nhất; nếu tuần tự, latency cộng theo critical path.

Cần đo **latency của từng dependency từ góc nhìn caller**, tần suất gọi, timeout, in-flight, rejection và upstream availability.

### 7.2. Dịch vụ bên thứ ba và quota

Payment provider, SMS, email, geocoding, AI inference hay dịch vụ thuế thường áp giới hạn:

- Requests/s trên API key, account, tenant, region hoặc endpoint.
- Số request đồng thời.
- Token/minute, bytes/day, transaction/day hoặc tổng quota.
- Throttling có cửa sổ burst.
- Cost, budget, quyền truy cập và rate-limits thay đổi theo gói.
- Retry-After hoặc chính sách retry riêng.

**Phải biết limit áp ở phạm vi nào.** Nếu Payment cho 120 call/s **toàn account**, 20 Pod Orders không thể mỗi Pod tự cho phép 120 call/s. Tổng 2.400 call/s sẽ bị 429. Cần limiter chia sẻ hoặc phân bổ ngân sách có kiểm soát; limiter cục bộ chỉ phù hợp khi đảm bảo tổng không vượt trần.

Nếu provider thông báo quota nhưng không bảo đảm hiệu suất tại mọi thời điểm, capacity dùng trong planning nên có dự phòng và kiểm chứng bằng tải được phép.

### 7.3. Message broker và consumer

Async tách thời điểm request khỏi xử lý nền nhưng không xóa giới hạn:
- Producer publish rate, broker throughput và storage.
- Consumer partitions/concurrency.
- Message size, serialization/deserialization.
- Retry queue, poison messages và DLQ.
- Downstream DB do consumer sử dụng.
- Backlog age, retry storm và thời gian giải phóng backlog.

Nếu broker nhận 10.000 message/s nhưng consumer xử lý bền vững 6.000 message/s, backlog tăng 4.000 message/s. Sau 15 phút có khoảng 3,6 triệu message tồn nếu tốc độ ổn định. Cần tính thời gian drain, dung lượng storage và SLO xử lý nền, không coi “publish thành công” là nghiệp vụ hoàn tất.

### 7.4. Cache và giới hạn riêng

Cache giúp giảm tải DB khi key có reuse và policy nhất quán phù hợp. Tuy nhiên, nó có:
- Memory limit, eviction rate, network bandwidth.
- Hot key contention, cluster shard skew.
- Connection count, single-threaded work tùy engine.
- TTL expiration đồng loạt, cache stampede.
- Consistency và invalidation risk.

Cache hit rate toàn cục 95% vẫn có thể che endpoint quan trọng hit rate 20%, hoặc một hot key chiếm phần lớn traffic. Khi cache lỗi hoặc lạnh, toàn bộ cache misses có thể đổ về DB và vượt giới hạn DB. Dùng request coalescing, TTL jitter, stale-while-revalidate khi hợp đồng cho phép, warmup và circuit/bulkhead để tránh stampede.

### 7.5. Hệ thống nhận dạng và bảo mật

Authorization server, token introspection, policy engine và key retrieval có thể là dependency trên mọi request. Nếu mỗi API call đồng bộ introspection, số request xác thực cũng scale theo lưu lượng của hệ thống. Cache có điều kiện, local token verification cho token phù hợp và high-availability identity service có thể giảm bottleneck; không bỏ kiểm tra issuer, audience hoặc quyền chỉ để tăng throughput.

## 8. Xác định trần throughput của request path

Một mô hình đơn giản: request bắt buộc tiêu thụ \(q_d\) đơn vị công việc ở dependency d và dependency có công suất bền vững \(C_d\) đơn vị/giây. Khi tải và chi phí mỗi request ổn định:

\[
R_{\max} \lesssim \min_d \frac{C_d}{q_d}
\]

Dấu “xấp xỉ giới hạn trên” vì retry, queue, lock, shared workload, overhead và SLO tail latency có thể làm năng lực thực thấp hơn.

### 8.1. Ví dụ tổng hợp

Một API “Create Order” cần:
- Database: 5 DB operations/order.
- Inventory: 1 call/order.
- Payment: 1 call/order.

Các capacity đã đo trong workload tương ứng:

| Dependency | Công suất bền vững minh họa | Nhu cầu mỗi order | Trần suy ra |
|---|---:|---:|---:|
| Database | 3.000 operation/s | 5 | 600 order/s |
| Inventory | 800 call/s | 1 | 800 order/s |
| Payment | 250 call/s | 1 | 250 order/s |

Trần lý thuyết của luồng này gần **250 order/s**, vì Payment là giới hạn nhỏ nhất. Nếu đội ngũ muốn giữ 20% headroom trên ngân sách Payment, mục tiêu tải bình thường có thể khoảng 200 order/s. Đây là ví dụ thiết kế dưới giả định một call/order và không có traffic từ service khác.

Tăng từ 8 lên 24 Pod Order không nâng Payment quota từ 250 lên 750. Nếu hệ thống phải nhận 500 đơn/s, cần thay đổi hợp đồng xử lý, năng lực provider, phân bổ quota hoặc kiến trúc nghiệp vụ, chứ không chỉ tăng Pod.

### 8.2. Bài toán nhiều loại request

Với GET và POST dùng chung database, dùng ngân sách:

~~~text
Total DB demand per second
  = GET rate x queries per GET
  + POST rate x DB operations per POST
  + Background workers
  + Report/batch jobs
  + Retry/replay operations
~~~

Mỗi loại thao tác có chi phí CPU/I/O khác nhau, nên phép cộng “operation count” chỉ đủ nếu các thao tác tương đối tương đương hoặc được đổi sang đơn vị tải được benchmark. Một truy vấn scan lớn có thể tiêu tốn nhiều tài nguyên hơn hàng trăm index lookup.

### 8.3. Bottleneck thay đổi khi tối ưu

Nếu Payment được nâng quota lên 1.000 call/s, database 600 operation-equivalent orders/s trở thành bottleneck tiếp theo. Nếu DB được tối ưu lên 1.200 order/s, Inventory 800 call/s lại giới hạn.

Vì vậy capacity planning là quá trình lặp: **đo → tìm giới hạn → thay đổi có chủ đích → đo lại**. Không giả định giải một bottleneck đồng nghĩa hệ thống đã scale tuyến tính vô hạn.

## 9. Amdahl, fan-out và giới hạn của scale ngang

**Amdahl's Law** minh họa một phần công việc không thể song song hóa sẽ giới hạn speedup dù tăng số worker. Với tỷ lệ \(s\) của công việc bắt buộc tuần tự và \(N\) đơn vị xử lý song song:

\[
Speedup(N) \le \frac{1}{s + \frac{1-s}{N}}
\]

Ví dụ 10% công việc buộc tuần tự, ngay cả khi N rất lớn, trần speedup xấp xỉ 10 lần theo giả định mô hình. Với hệ thống thật, overhead, mạng, lock và phối hợp giữa dịch vụ còn tạo chi phí khác.

Không nên dùng công thức này như capacity forecast chính xác cho microservices; mục đích là nhận diện phần không scale được: single leader, global lock, central coordination, một shard nóng hoặc một downstream có quota cố định.

### 9.1. Fan-out và xác suất request thất bại

Khi một request bắt buộc 8 dependency **độc lập**, mỗi dependency đáp ứng thành công với xác suất 99,9% trong cùng điều kiện:

~~~text
P(tất cả thành công) = 0,999 ^ 8 ≈ 99,2%
~~~

Đây là minh họa theo giả định độc lập, không phải công thức SLO chung. Thực tế dependency thường có failure correlation vì dùng chung DB, region hoặc mạng.

Càng nhiều dependency bắt buộc, đường nóng càng có nhiều nơi làm tăng latency hoặc failure. Với lời gọi tùy chọn, thiết kế fallback/cache/async có thể làm giảm diện tích failure domain.

### 9.2. Phân biệt concurrency và throughput

Một service xử lý 200 request đồng thời không đồng nghĩa chịu 200 request/s; còn phụ thuộc thời gian mỗi request. Tương tự, 100 connection DB không đảm bảo 100 transaction/s và 100 partition Kafka không đảm bảo 100 consumer có tác dụng khi số worker, key distribution hoặc DB yếu hơn.

Đo công suất bằng **completed useful work per second dưới latency/error SLO**, đồng thời ghi concurrency đã sử dụng tại điểm đó.

## 10. Timeouts, retry và khả năng khuếch đại tải

Nếu downstream đang chậm, retry liên tiếp có thể tăng tải đúng lúc nó ít khả năng xử lý nhất. Một request có tối đa 2 retry có thể tạo 3 attempts. Khi 300 request/s cùng timeout, downstream có thể thấy tới 900 attempts/s trong giai đoạn retry dồn.

Nếu Gateway, Orders và PaymentClient đều retry, attempts có thể nhân giữa nhiều tầng. Đây là một nguyên nhân khiến capacity đo trong benchmark ổn định không tương ứng với sự cố production.

### 10.1. Thiết kế retry budget

- Retry chỉ với lỗi có khả năng phục hồi và thao tác **idempotent** hoặc đã có idempotency key/dedup.
- Giới hạn số attempts và tổng thời gian.
- Exponential backoff có jitter để tránh thundering herd.
- Tôn trọng Retry-After/429 theo chính sách downstream và deadline.
- Tránh nhiều tầng đồng thời retry cùng một command.
- Có retry budget toàn caller và theo dependency; khi quá tải thì shed load.
- Quan sát attempts/original requests và số retries bị bỏ vì hết deadline.

Với Payment, khi timeout không biết provider đã xử lý hay chưa, cần truy vấn trạng thái bằng transaction/idempotency key trước khi thử lại side effect. Không dùng retry như cơ chế sửa mọi lỗi.

### 10.2. Phân bổ deadline đầu-cuối

Giả sử SLO API đặt hàng yêu cầu hoàn thành trong 900 ms. Một budget minh họa:

~~~text
Authentication:     80 ms
Inventory:         180 ms
Payment:           300 ms
Order DB commit:   180 ms
Network + queue:   160 ms
Total:             900 ms
~~~

Nếu Orders đặt timeout Payment=5 giây trong khi Gateway đóng request sau 900 ms, request đang chờ sẽ giữ connection/thread thừa và có thể commit sau khi client đã bỏ cuộc. Truyền **remaining deadline** qua lời gọi downstream và giới hạn cả thời gian chờ pool, connect, read và tổng operation.

Trong đường fan-out song song, tính theo critical path thay vì cộng mọi nhánh một cách máy móc. Timeout là lớp bảo vệ thời gian; nó không tự giới hạn lượng công việc đang chạy. Cần concurrency limit hoặc bulkhead để bảo vệ tài nguyên.

## 11. Biến capacity thành ngân sách vận hành

### 11.1. Global budget và per-replica budget

Giả sử Payment quota toàn account là 180 request/s. Muốn giữ 20% headroom, ngân sách khai thác tối đa khoảng 144 request/s. Nếu Order có 12 replica, chia đều tương ứng khoảng 12 call/s/replica, nhưng lưu lượng thực tế có thể lệch pod.

Một limiter cục bộ trên mỗi replica chỉ là ước lượng khi:
- Replica count thay đổi.
- Routing lệch traffic.
- Retry và background workers cũng dùng quota.
- Nhiều service khác sử dụng cùng API key/quota.

Với quota chung, cần coordinated rate limiting hoặc cơ chế phân bổ token/budget theo tenant, service và replica. Nếu bộ điều phối limiter gặp lỗi, chính sách fail-open/fail-closed phải được xác định theo nghiệp vụ; không ngầm cho phép vượt quota.

### 11.2. Concurrency limit

Concurrency limit bảo vệ số yêu cầu đồng thời và thường phản ánh saturation tốt khi latency biến động.

Ví dụ DB có ngân sách 240 connection cho Orders và HPA tối đa 20 pod, pool limit mỗi pod khoảng 12 connection trong một phân bổ đơn giản. Nhưng **pool size không phải mục tiêu cần luôn sử dụng đầy**. Nếu DB xử lý tốt nhất ở 120 active queries, cho phép 240 active queries có thể làm throughput giảm vì tranh chấp và context switching.

Dùng số đo pool wait, active DB queries, CPU/I/O/lock wait và load test để xác định mức concurrency hữu ích. Nếu quá hạn, từ chối sớm hoặc xếp hàng **có giới hạn** với deadline, không tạo queue vô hạn.

### 11.3. Bulkhead theo chức năng

Giả sử API Search, Checkout và Reporting cùng dùng DB. Reporting có job scan lớn dễ chiếm toàn bộ connection pool, khiến Checkout timeout. Có thể tách pool/concurrency budget, dùng read replica phù hợp, ưu tiên admission control hoặc chuyển reporting sang workload riêng.

~~~text
DB Capacity Budget
   |
   +-- Checkout critical quota
   +-- Read API quota
   +-- Batch/Reporting limited quota
   +-- Reserved operational capacity
~~~

Bulkhead chỉ có tác dụng nếu tài nguyên chia ranh giới thật. Tách executor của app nhưng vẫn dùng cùng pool DB không giới hạn có thể không bảo vệ được DB.

### 11.4. Rate limit, load shedding và backpressure

- **Rate limit:** giới hạn tần suất request theo source/tenant/endpoint.
- **Concurrency control:** giới hạn công việc đang chạy.
- **Load shedding:** chủ động từ chối tải ít ưu tiên khi sắp bão hòa.
- **Backpressure:** điều tiết producer dựa trên năng lực consumer, thường quan trọng với streaming và queue.
- **Bounded queue:** giữ số việc chờ có trần; khi đầy có hành vi rõ.
- **Circuit breaker:** dừng gọi liên tiếp một dependency đang lỗi hoặc quá chậm, có trạng thái half-open để dò hồi phục.

Từ chối nhanh một tỷ lệ nhỏ request có thể bảo vệ p99 và khả năng thành công cho phần còn lại. Cần trả trạng thái có ý nghĩa, ví dụ 429 cho quota/rate limit hoặc 503 cho mất khả dụng tạm thời theo hợp đồng. Đối với thao tác có side effect, client phải biết cách retry an toàn.

## 12. Giảm nhu cầu thay vì chỉ tăng nguồn lực

Có ít nhất bốn nhóm biện pháp:

### 12.1. Giảm số thao tác trên mỗi request

- Loại N+1 query.
- Batch các lookup có tính đúng đắn phù hợp.
- Tối ưu query/index, cắt payload thừa, paginate.
- Cache dữ liệu được phép chấp nhận stale.
- Gom những request trùng lặp (request coalescing).
- Giảm fan-out qua projection/read model khi thực sự cần.

Nếu giảm từ 5 DB operations xuống 2 operations/order trong cùng workload, trần DB tính theo phép chia đơn giản có thể tăng khoảng 2,5 lần; thực tế còn tùy chi phí mỗi query và contention mới.

### 12.2. Di chuyển khỏi đường đồng bộ

Các tác vụ email, analytics, cập nhật search index hoặc recommendations có thể không cần chặn phản hồi tạo đơn. Transactional outbox + broker cho phép xử lý sau, với điều kiện message được lưu và consumer có idempotency.

Điều này **chuyển** tải sang pipeline async; capacity của consumer, queue retention, backlog age và SLO cuối cùng vẫn phải được quản lý. Không đánh đồng “API trả nhanh” với “toàn bộ nghiệp vụ hoàn tất nhanh”.

### 12.3. Tách read/write hoặc workload

Read replica, CQRS projection, analytical store hoặc cache có thể giảm áp lực read lên primary. Nhưng phải thiết kế consistency, replication lag, invalidation, backfill và cutover.

Tách batch/reporting khỏi transaction workload giúp tránh lock và I/O cạnh tranh. Với dữ liệu nhạy cảm, phân vùng theo tenant có thể tăng isolation nhưng thêm chi phí vận hành.

### 12.4. Tăng năng lực đúng nơi

Nếu giới hạn thật là:
- DB CPU: tối ưu query, resize DB, phân phối read/write workload.
- DB lock hot row: thay data model/transaction hoặc serialize hợp lý theo key.
- DB connection: chỉnh pool/replica budget, cân nhắc pooler; không chỉ tăng max_connections.
- Payment quota: thương lượng capacity, thay mô hình workflow hoặc điều tiết.
- Kafka partition hot: xem key distribution và partitioning; tăng consumer đơn thuần không đủ.
- Cache hot key: request coalescing, replication phù hợp hoặc phân phối lại.

Mỗi thay đổi cần đo sau triển khai vì bottleneck tiếp theo có thể nằm ở nơi khác.

## 13. Một quy trình xác định giới hạn có thể lặp lại

### Bước 1 — Định nghĩa SLO và luồng ưu tiên

Ví dụ:
- Create Order: p99 dưới 900 ms, tỷ lệ thành công ít nhất mức đã thỏa thuận.
- Read Order: p99 dưới 250 ms.
- Projection freshness: 99% cập nhật hiện lên trong 5 giây.
- Payment request: tuân thủ quota và không tạo giao dịch trùng.

Không benchmark theo một con số RPS chung khi workload GET/POST và hậu quả nghiệp vụ khác nhau.

### Bước 2 — Vẽ dependency graph và lập bảng demand

Ghi endpoint, downstream, calls/request, tính bắt buộc, thời gian, retry, loại query, volume dữ liệu và giới hạn công khai/đo được. Bao gồm worker async, migration, analytics và workload cùng giờ cao điểm.

### Bước 3 — Thu thập baseline production

Trong phạm vi quan sát được: throughput thực, p50/p95/p99, error rate, saturation, pool wait, DB connection, slow query, lock wait, broker backlog và quota rejection. Gắn mốc phiên bản release/config để biết thay đổi nào làm biến động capacity.

### Bước 4 — Dự đoán giới hạn đầu tiên

Dùng công thức demand/capacity ở mức đơn giản và kiểm tra:
- DB CPU/IOPS hay connection?
- Hot row/partition?
- Throughput của dependent service?
- Quota theo account?
- Consumer processing rate?
- Network bandwidth?
- Thread pool và queue?

Không đổ mọi triệu chứng vào “DB chậm” nếu caller thực ra chờ lấy connection.

### Bước 5 — Load test có kiểm soát

Tăng tải theo từng nấc, giữ mỗi nấc đủ ổn định để đo; sử dụng data volume, key skew và transaction mix tương ứng. Thu thập metric từ API và dependency, không chỉ kết quả của load generator.

Ghi điểm bắt đầu vi phạm latency/error SLO và điểm throughput plateau. Giới hạn thử nghiệm để không gây áp lực ngoài dự kiến lên payment/third-party hoặc dữ liệu thật.

### Bước 6 — Thử tình huống suy giảm

Bên cạnh steady-state:
- Một replica DB/read replica mất.
- Một Pod app bị rút lúc tải cao.
- Cache miss đột biến.
- Dependency tăng latency 10 lần.
- Provider trả 429/503.
- Kafka consumer bị chậm.
- Nhiều client đồng thời retry.
- Rolling update có maxSurge.
- Một tenant/partition nóng đột biến.

Các tình huống giúp biết **capacity khi lỗi**, không chỉ khi mọi thành phần khỏe.

### Bước 7 — Chọn guardrail và rollout

Thiết lập global/per-tenant rate limit, pool limit, bulkhead, deadline, bounded queue, retry budget và alert theo nguồn giới hạn. Canary thay đổi, so sánh độ trễ/throughput/error, tăng dần traffic và giữ cơ chế rollback.

### Bước 8 — Đo lại sau tối ưu

Tối ưu một điểm nghẽn có thể chuyển bottleneck sang nơi khác. Cập nhật dependency budget, runbook và capacity model bằng bằng chứng đo mới.

## 14. Kiểm thử capacity: thiết kế dữ liệu và loại tải

Một bài kiểm thử dễ bị lệch nếu dùng dữ liệu khác production:

- Dữ liệu ít khiến toàn bộ bảng nằm trong RAM.
- Test chỉ một tenant và một SKU không đại diện key distribution.
- Client luôn gọi cùng URL khiến cache hit gần 100%.
- Không có background jobs và CDC.
- Không có hot row/hot partition như đợt flash sale.
- Chỉ chạy 30 giây, không đủ để phát hiện GC, cache churn, replication lag.
- Không có rate limit thật của provider; mock trả nhanh mọi request.
- Chỉ đo average response time, bỏ qua p99, timeout và failed operations.
- Load generator tự nghẽn, khiến kết luận server còn dư capacity sai.

Các kiểu thử thường dùng:

| Loại | Mục đích |
|---|---|
| Baseline load | Đo đường cong latency/throughput ở tải dự kiến |
| Step/ramp load | Xác định ngưỡng saturation và nơi throughput plateau |
| Stress test | Quan sát hành vi khi vượt capacity và cơ chế từ chối |
| Spike test | Kiểm tra burst, queue, autoscaling và cache stampede |
| Soak test | Phát hiện leak, replication lag, backlog và degradation dài hạn |
| Dependency impairment | Xác định tác động khi DB/API chậm hoặc trả lỗi |
| Scale/failover test | Kiểm chứng khi mất pod/zone, chuyển traffic |
| Mixed workload test | Đánh giá cạnh tranh giữa reads, writes, batch và consumers |

Cần đặt điểm dừng an toàn, môi trường phù hợp và quota test đã được phép, đặc biệt khi tích hợp API có phí hoặc side effect ngoài thế giới thực.

## 15. Ví dụ capacity budget cho một hệ thống đặt hàng

**Giả định minh họa:**

- Orders có 15 Pod bình thường, HPA tối đa 24 Pod.
- Database giới hạn 600 connections; 120 dành cho admin, reporting và service khác.
- Orders muốn chiếm tối đa 288 connections kể cả scale tối đa.
- Payment giới hạn account 300 call/s; mục tiêu có 20% headroom.
- Mỗi order mới gọi Payment đúng một lần khi không retry.
- Database chịu được khoảng 2.000 DB operations/s dưới p99 mục tiêu cho loại workload đang đo.
- Mỗi order phát sinh trung bình 5 DB operations.

Tính ngân sách:

~~~text
Orders DB pool cap per Pod
  = 288 / 24 = 12 connections/Pod (upper bound phân bổ)

Payment planned budget
  = 300 x 0,80 = 240 calls/s

DB operation-equivalent cap for Create Order
  = 2.000 / 5 = 400 orders/s

Initial Create Order throughput planning ceiling
  = min(240, 400) = 240 orders/s
~~~

**Kết luận theo giả định:** Payment giới hạn workload này trước database; tăng Pod đơn thuần không giúp phục vụ 500 Create Order/s đồng bộ. Tuy nhiên, 240 order/s vẫn chỉ là **ngân sách ban đầu**, vì Payment có latency, concurrency và retry; DB còn nhận reads/jobs, còn pool wait và contention.

Các câu hỏi tiếp theo:
- Payment 300/s được tính theo cửa sổ nào và có giới hạn concurrent calls?
- Những service khác cùng account Payment có tiêu quota không?
- Có bao nhiêu retry và lệnh gọi Payment trên mỗi loại order?
- Orders DB có query mix nào khác? Peak reads có làm giảm write capacity?
- Khi mất 1/3 Pod, remaining Pod có đủ throughput và pool hợp lệ?
- Nếu Payment latency tăng từ 200 ms lên 2 giây, có bao nhiêu request đồng thời và cần bao nhiêu connection/worker?
- Có đường nghiệp vụ cho trạng thái PENDING_PAYMENT và xử lý async không?

### 15.1. Tính concurrency Payment từ Little's Law

Nếu duy trì 240 Payment calls/s và thời gian giữ một call trung bình 0,2 giây:

~~~text
Expected concurrent Payment calls ≈ 240 x 0,2 = 48
~~~

Nếu provider chậm lên 2 giây trong khi vẫn nhận 240 calls/s:

~~~text
Expected concurrent Payment calls ≈ 240 x 2 = 480
~~~

Chỉ số concurrency tăng 10 lần trong giả định ổn định; nhưng 480 calls in-flight có thể vượt giới hạn thực, khiến queue, timeout và retry. Vì vậy phải có concurrency limiter, deadline và cách ứng xử khi vượt capacity. Không dùng phép tính này để bảo đảm hệ thống thật có thể duy trì 240 calls/s trong khi provider đã chậm: provider có thể giảm năng lực hoặc trả 429.

### 15.2. Đường ứng xử khi chạm giới hạn

Một thiết kế có thể:
1. Giữ quota cho chức năng đặt hàng quan trọng.
2. Từ chối sớm hoặc chuyển trạng thái có chủ đích khi không có slot.
3. Nếu nghiệp vụ cho phép, nhận đơn PENDING_PAYMENT và xử lý với durable queue.
4. Dùng idempotency key để không nhân đôi Payment khi retry.
5. Hiển thị trạng thái nghiệp vụ thật, không trả “thanh toán thành công” khi chưa có xác nhận.
6. Đo backlog, tuổi công việc, tỷ lệ terminal và thời gian hoàn tất ngoài HTTP SLO.

Async giúp API hấp thụ burst nhưng không làm tăng quota bên thứ ba; backlog và thời gian hoàn tất vẫn phải nằm trong giới hạn chấp nhận.

## 16. Cấu hình mẫu Spring Boot và cơ chế bảo vệ

Một cấu hình minh họa cho pool và thời gian gọi dependency:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 5000

payment:
  client:
    connect-timeout: 200ms
    request-timeout: 800ms
  bulkhead:
    max-concurrent-calls: 16
  retry:
    max-attempts: 1
~~~

Các property dưới payment.* là **schema tùy biến của ứng dụng**, chỉ có hiệu lực khi có code bind và thực thi. Giá trị Hikari ở đây minh họa cấu hình connection pool và đơn vị milliseconds cho connection-timeout; không phải default nên áp dụng cho mọi dự án.

Pool size=12 được chọn theo ví dụ 24 Pod × 12 = 288 connection, nhưng không thay thế phép đo capacity thực. Một số điểm:
- Nếu Pod tối đa thay đổi, ngân sách cần tính lại.
- Minimum idle không nhất thiết càng cao càng tốt.
- Connection acquisition timeout phải nằm trong deadline của caller.
- SQL statement/query timeout và transaction timeout phải được cấu hình theo workload, không chỉ connection acquisition.
- Pool không bảo vệ được DB khỏi query đắt hoặc hot lock khi số active query nhỏ.
- Nếu cùng code khởi tạo nhiều pool DataSource/consumer, phải cộng tất cả kết nối.
- Micrometer/Hikari metrics giúp đo pending, active, idle, timeout và thời gian chờ.

### 16.1. Một bulkhead đơn giản cho dependency tùy chọn

~~~java
import java.util.concurrent.Semaphore;

public final class OptionalFeatureGateway {
    private final Semaphore permits = new Semaphore(16);

    public String getSuggestions() {
        if (!permits.tryAcquire()) {
            return "[]"; // Fallback hợp lệ nếu nghiệp vụ cho phép.
        }

        try {
            return callSuggestionsApiWithBoundedTimeout();
        } catch (ExpectedTemporaryDependencyFailure ex) {
            return "[]";
        } finally {
            permits.release();
        }
    }

    private String callSuggestionsApiWithBoundedTimeout() {
        // Sử dụng HTTP client có connect/request deadline.
        // Ví dụ chỉ minh họa ranh giới tài nguyên.
        throw new UnsupportedOperationException("Illustrative only");
    }

    static final class ExpectedTemporaryDependencyFailure
            extends RuntimeException {}
}
~~~

Đoạn trên trình bày ý tưởng admission control, không phải một client tích hợp có thể chạy nguyên vẹn trong dự án. Limit 16 là **mỗi instance**, nên phải xét max replicas và trần downstream. Fallback rỗng chỉ chấp nhận cho tính năng phụ; Payment/Authorization/Inventory cần hành vi an toàn theo hợp đồng.

Không catch mọi exception rồi trả thành công giả cho giao dịch quan trọng. Với timeout Payment, cần trạng thái “chưa xác định” và reconciliation thay vì tự xác nhận đã thanh toán.

### 16.2. Chi phí của một lệnh retry

Nếu API gọi Payment với 1 attempt, demand = 1 Payment call/order. Khi thêm 2 retries, trong tình huống xấu demand có thể = 3 attempts/order. Để giữ trần 240 Payment attempts/s, số order thực có thể giảm mạnh.

Cân nhắc retry budget, backoff + jitter, circuit breaker và trạng thái nguồn thay vì giả định retry miễn phí.

## 17. Quan sát và cảnh báo để phát hiện giới hạn sớm

Một dashboard cấp request path nên có:

| Nhóm | Các tín hiệu chính |
|---|---|
| API edge | Request rate, p50/p95/p99, 4xx/5xx, in-flight, queue/rejections |
| Downstream HTTP | Call rate, p99, timeout, 429, 503, retries, limiter rejects, breaker state |
| DB pool | Active/idle/pending, acquisition latency, timeout, pool limit |
| DB engine | CPU, I/O latency, slow query, lock wait, commits/s, replication lag |
| Cache | Hit/miss theo use case, eviction, hot key, command p99, memory |
| Broker/worker | Producer/consumer rate, lag, oldest age, retry/DLQ, processing p99 |
| Scaling | Replica ready/max, pod CPU/memory, rollout surge, startup/warmup |
| Business | Completed orders/s, duplicate-prevention, successful payments, async completion |
| Revision | Release version, config revision, feature flag/limit change |

Không thể lấy “API throughput tăng” làm thành công duy nhất nếu tỷ lệ đơn bị thanh toán trùng hoặc mức dữ liệu stale tăng. Cần metric tính đúng đắn và kết quả nghiệp vụ.

### 17.1. Phát hiện bottleneck bằng chuỗi tín hiệu

**DB pool chạm trần:**
- Pool pending tăng; acquisition wait p99 tăng.
- DB connections có thể vẫn còn hoặc query bị giữ lâu.
- Xem active vs idle, transaction duration và leak.

**DB CPU/I/O giới hạn:**
- Query p99, CPU hoặc I/O latency tăng.
- Throughput hữu ích plateau.
- App tăng pod nhưng DB không cải thiện.

**Hot lock:**
- CPU không nhất thiết quá cao.
- Lock wait/deadlock và transaction duration tăng theo một tập key/row.
- Dùng tracing/query fingerprint và phân bố key để khoanh vùng.

**Payment quota:**
- 429 tăng ở mức call attempts/giây gần quota.
- Retry tăng và end-to-end success giảm.
- Cần budget toàn account, không chỉ per Pod.

**Consumer không theo kịp:**
- Backlog và oldest pending age tăng liên tục.
- Process rate thấp hơn arrival rate.
- Phân tích partition skew, retry, DB writes và downstream saturation.

### 17.2. Chỉ số “có thể mở rộng” phải theo SLO

Một SLI ví dụ:

~~~text
Good request ratio =
  số request hoàn tất đúng nghiệp vụ và trong deadline
  / số request hợp lệ đủ điều kiện
~~~

Một báo cáo capacity có thể chỉ ra mức cao nhất đạt đồng thời:
- Throughput tối thiểu mong muốn.
- p99 dưới deadline.
- Error rate dưới ngưỡng.
- Retry/429 và queue age trong ngân sách.
- Không vi phạm correctness hoặc consistency contract.
- Còn headroom để mất một replica hoặc giảm capacity dependency.

Tránh lấy 100% CPU là mục tiêu vận hành lý tưởng; CPU cao có thể hợp lý ở một batch worker, nhưng trong API latency-sensitive nó có thể làm tail latency xấu.

## 18. Xử lý bottleneck trong tình huống sự cố

**Tình huống:** sau khi mở chiến dịch bán hàng, Checkout p99 tăng từ 300 ms lên 4 giây; HPA tăng Pod từ 8 lên 24; DB connection timeout và Payment 429 đồng thời tăng.

Một runbook thực dụng:

1. **Khoanh vùng:** endpoint, khu vực, tenant, thời điểm chiến dịch; đối chiếu release/config revision.
2. **Xác định critical path:** Payment, Inventory, DB, cache và event queue; ghi in-flight và timeout ở từng hop.
3. **Tách giới hạn:** DB pool pending cao vì active queries tốn thời gian, hay DB max connections quá thấp? Payment 429 do quota account hay loại endpoint cụ thể?
4. **Giảm khuếch đại:** hạn chế retry và fan-out, bật circuit breaker khi đúng điều kiện, ngừng batch/reporting ít ưu tiên.
5. **Bảo vệ correctness:** không retry Payment mù; dùng idempotency/reconciliation cho kết quả không xác định.
6. **Áp admission control:** limit theo tenant/endpoint, từ chối sớm hoặc đưa việc thích hợp sang queue bền vững.
7. **Khôi phục năng lực:** sửa slow query/lock, điều chỉnh pool theo DB budget, làm việc với provider về quota hoặc đổi kiến trúc workflow.
8. **Kiểm chứng:** p99, error, completed orders, DB lock/pool, Payment attempts/s, backlog age và duplicate rate quay lại mức chấp nhận.
9. **Ngăn tái diễn:** benchmark burst, quota budget chung, autoscaling guardrail, alert theo saturation và runbook tiếp theo.

Không vội tăng thêm 50 Pod khi DB đang hết connection; điều đó có thể làm mọi thứ tệ hơn. Cũng không đơn giản giảm timeout xuống vài mili giây để “cắt lỗi”, vì có thể khiến nhiều giao dịch chuyển sang trạng thái không xác định, tăng retry và mất kết quả.

## 19. Các anti-pattern thường gặp

**“Thêm Pod là tăng throughput tuyến tính.”** Shared database, global lock, quota provider và network chung tạo trần. Mỗi Pod mới còn tiêu thêm connection và tải kiểm soát.

**“DB có 1.000 connections thì cho 1.000 query đồng thời là tốt.”** Connection count là giới hạn kỹ thuật; mức active query tối ưu thường thấp hơn tùy workload và contention.

**“Chỉ xem CPU DB.”** Lock wait, I/O, connection pool, replica lag và API quota có thể nghẽn ngay khi CPU còn thấp.

**“Dùng QPS benchmark đơn giản cho mọi truy vấn.”** Query mix, row scanned, write amplification, cache state và consistency requirement thay đổi năng lực rất lớn.

**“Retry giúp chống lỗi nên phải bật nhiều tầng.”** Retry amplification làm nghẽn dependency đang yếu; cần ngân sách, backoff và idempotency.

**“Circuit breaker tự tạo thêm capacity.”** Circuit breaker giảm tác động của dependency đang lỗi, không làm provider xử lý được nhiều hơn khi khỏe.

**“Đưa sang queue sẽ hết bottleneck.”** Queue giúp đệm burst, nhưng nếu arrival > processing lâu dài, backlog tăng vô hạn và SLO cuối sẽ thất bại.

**“Cache hit 99% nghĩa là DB nhẹ.”** Hot key, cache miss sau TTL và read/write consistency vẫn có thể gây DB storm; cần phân tích theo use case.

**“Read replica tăng khả năng ghi.”** Replica thường giúp reads; write serialization trên primary vẫn là giới hạn.

**“Sharding sẽ sửa mọi slow query.”** Chọn shard key sai gây hot shard; cross-shard transaction làm hệ thống phức tạp hơn.

**“Không nhận được 429 thì chưa tới quota.”** Provider có thể tăng latency, xếp hàng hoặc giảm hiệu suất trước khi trả 429. Quan sát cả latency/in-flight và công bố limits.

**“Chỉ cần benchmark trung bình.”** Tải đỉnh, p99, tenant skew, background job và failure mode mới bộc lộ giới hạn người dùng thực gặp.

**“Một service có metric đẹp nghĩa là toàn workflow khỏe.”** API có thể trả 202 nhanh nhưng consumer queue, projection và saga chậm, khiến người dùng chờ nghiệp vụ.

## 20. Bài tập tình huống có lời giải gợi ý

Một hệ thống bán hàng có:
- 10 replica Order API; HPA max 30 replica.
- Database cho phép tối đa 700 connections, trong đó 100 dành cho admin/backup và 150 dành cho service khác.
- Mỗi Pod Order dự kiến dùng pool tối đa 20 connections.
- Payment quota 180 calls/s cho toàn account.
- Mỗi POST /orders thực hiện 1 Payment call và 4 DB operations.
- Database trong workload được đo đạt 1.200 DB operations/s dưới SLO.
- Tải bình thường 150 POST/s, chiến dịch tăng lên 350 POST/s.
- Retry policy hiện cho tối đa 3 attempts với Payment.

**Câu hỏi:**

1. Nếu HPA lên 30 Pod, tổng trần connection Order là bao nhiêu? Có vượt ngân sách DB còn lại không?
2. Với DB capacity trên, trần Order/s suy ra từ DB là bao nhiêu?
3. Payment giới hạn bao nhiêu Order/s nếu không retry?
4. Khi tăng retries và provider bắt đầu timeout, vì sao traffic nội bộ có thể tăng vượt quota?
5. Có nên tiếp tục tăng Pod không? Cần guardrail gì?
6. Nếu chuyển Payment sang bước async, điều gì được cải thiện và điều gì vẫn bị giới hạn?
7. Chỉ số nào chứng minh chiến dịch vẫn đạt SLO và không nhân đôi thanh toán?

**Tính minh họa:**

~~~text
DB connections available for Order
  = 700 - 100 - 150 = 450

30 pods x 20 pool connections
  = 600 (vượt 450 connection budget nếu tất cả mở tới max)

DB-derived POST cap
  = 1.200 / 4 = 300 orders/s

Payment-derived POST cap without retry
  = 180 / 1 = 180 orders/s

Initial synchronous path bound
  = min(300, 180) = 180 orders/s (trước headroom)
~~~

Kết luận theo giả định: Payment là giới hạn đầu tiên, DB pool còn có nguy cơ vượt ngân sách khi autoscale. 350 POST/s không thể đạt bằng cách chỉ tăng Pod. Cần áp giới hạn tốc độ/đồng thời toàn account, điều chỉnh pool max theo maxReplicas, giới hạn retry, bảo vệ idempotency và cân nhắc quy trình PENDING_PAYMENT/queue nếu nghiệp vụ cho phép.

Nếu Payment xử lý async, API có thể tiếp nhận/ghi nhận đơn nhanh hơn nhưng trạng thái Payment chưa hoàn tất vẫn phải rõ ràng; consumer chỉ có thể giải quyết theo quota và backlog age sẽ tăng nếu arrival vượt khả năng lâu dài. Phải đo thành công cuối cùng, thời gian hoàn tất và số giao dịch duplicate.

## 21. Checklist khi đánh giá khả năng mở rộng

1. **SLO rõ ràng:** throughput hữu ích, p95/p99, error rate, data freshness và completion target.
2. **Dependency graph:** liệt kê tất cả API/DB/cache/broker bắt buộc và tùy chọn của từng request.
3. **Demand per request:** query/transaction/call count, bytes, duration, retries và fan-out.
4. **Global capacity:** DB CPU/IOPS/connection/locks, service concurrency, provider quota/account limits.
5. **Autoscaling cap:** số Pod tối đa, maxSurge, pool/connection budget khi rollout/failover.
6. **Tail latency:** đo queue wait, pool wait, downstream p99, transaction duration, critical path.
7. **Shared workload:** batch, reporting, outbox relay, consumer, backup, migration và traffic tenant khác.
8. **Failure mode:** burst, cache miss, retry storm, node loss, dependency slow và quota reduction.
9. **Guardrails:** bounded queue, admission control, backpressure, bulkhead, circuit breaker, deadlines.
10. **Correctness:** transaction, idempotency, read consistency, replay, workflow completion.
11. **Optimization:** loại N+1, index đúng, transaction ngắn, cache hợp lệ, async thích hợp, shard chỉ khi cần.
12. **Telemetry:** metric và trace tại caller/callee, config revision, alert theo SLO/saturation.
13. **Benchmark:** dữ liệu và query mix tương đương thực tế, ramp/spike/soak/failure tests.
14. **Operational plan:** mức headroom, capacity budget ownership, canary/rollback và runbook.
15. **Re-evaluation:** đo lại bottleneck sau mỗi thay đổi, cập nhật capacity model và giới hạn vận hành.

## 22. Những điều cần nhớ

- **Khả năng mở rộng đầu-cuối bị giới hạn bởi dependency bắt buộc chạm ngưỡng sớm nhất.** Số replica của ứng dụng không thể vượt quota bên thứ ba hay năng lực của database dùng chung.
- **Đo năng lực dưới SLO**, không chỉ mức RPS lớn nhất trước khi hệ thống crash. p99, saturation, 429 và correctness đều quan trọng.
- **Database có nhiều trần khác nhau:** query plan, I/O, locks, connections, write log, hot keys, replication và consistency. Tăng connection không đồng nghĩa tăng throughput.
- **Mỗi request có thể khuếch đại tải** qua fan-out, N+1 và retry. Lập ngân sách theo calls/operations trên mỗi request cùng peak workload.
- **Little's Law giải thích vì sao downstream chậm làm in-flight tăng**, khiến thread/connection/queue đầy dù traffic không tăng.
- **Quota và concurrency phải được quản lý theo đúng phạm vi áp dụng**, nhất là global account/shared DB khi autoscaling và rollout.
- **Bảo vệ bằng deadlines, bulkheads, rate limiting, bounded queues, backpressure và idempotency.** Cache/async có thể giảm hoặc dời tải, nhưng không biến mất giới hạn.
- **Capacity planning là vòng lặp đo → xác định bottleneck → thay đổi → đo lại.** Mục tiêu là kết quả nghiệp vụ đúng, ổn định và có khả năng phục hồi khi dependency suy giảm.
