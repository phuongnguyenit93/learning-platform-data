# Xác định điểm nghẽn ở ứng dụng, truy vấn, storage hay mạng trong MongoDB

Một API sử dụng MongoDB có thể chậm dù MongoDB server đang hoạt động bình thường. Ngược lại, một truy vấn chạy nhanh trong mongosh nhưng phản hồi từ ứng dụng vẫn mất nhiều giây. Nguyên nhân có thể nằm ở **ứng dụng**, **truy vấn/cơ chế thực thi MongoDB**, **storage** hoặc **mạng**. Các lớp này tác động qua lại: truy vấn quét nhiều documents có thể gây I/O; I/O cao khiến connection pool ở ứng dụng bị chờ; retry trong ứng dụng lại tăng tải server và làm vấn đề nghiêm trọng hơn.

Bài học thuộc chương **Tối ưu hiệu năng**, module **Database Engine Document MongoDB**, trình bày một phương pháp chẩn đoán có thể lặp lại: **đo đúng nơi phát sinh thời gian, tạo giả thuyết, thu thập chứng cứ từ nhiều lớp và chỉ thay đổi khi biết nút thắt thực sự**.

Nội dung bao gồm:

1. Phân biệt độ trễ, throughput, saturation, queueing và tail latency.
2. Tách thời gian ở ứng dụng, MongoDB driver, truy vấn trên server, storage và network.
3. Sử dụng tracing, metrics, logs, MongoDB explain, profiler và các công cụ quan sát.
4. Đọc các tín hiệu đặc thù như connection checkout wait, COLLSCAN, sort spill, WiredTiger cache pressure, disk latency, replication lag và network RTT.
5. Điều tra những triệu chứng dễ nhầm lẫn, đặc biệt truy vấn nhanh nhưng API chậm hoặc CPU database cao nhưng index không phải nguyên nhân.
6. Ví dụ mongosh, Java Sync Driver, quy trình xử lý sự cố, bài tập và checklist.

**Nguyên tắc quan trọng:** Không tối ưu dựa trên một metric đơn lẻ hoặc chỉ vì tên metric trông bất thường. Cần chứng minh mối liên hệ giữa metric và thời gian người dùng gặp phải. Các lệnh tăng profiling, chạy benchmark nặng, đổi index hoặc cấu hình production phải qua quy trình vận hành được phép; ưu tiên đọc metrics trước, thử thay đổi trong môi trường staging phù hợp.

## 1. Điểm nghẽn là gì?

**Điểm nghẽn (bottleneck)** là tài nguyên hoặc giai đoạn giới hạn khả năng đáp ứng khi hệ thống cần xử lý thêm công việc. Điểm nghẽn có thể là CPU, disk I/O, lock contention, đường mạng, connection pool, thread pool hoặc một truy vấn cụ thể.

Ví dụ:

~~~text
Client
  |
  v
API Gateway
  |
  v
Application
  |-- request queue
  |-- business logic
  |-- driver connection checkout
  |-- BSON serialization
  |
  v
Network
  |
  v
MongoDB
  |-- admission/scheduling
  |-- query planning/execution
  |-- cache
  |-- storage reads/writes
  |-- locks/transactions
  |
  v
Network response
  |
  v
Application mapping/JSON
  |
  v
Client
~~~

Nếu MongoDB thực thi truy vấn trong 20 ms nhưng connection pool checkout phải đợi 900 ms, tạo thêm index có thể không cải thiện thời gian phản hồi.

### 1.1. Bottleneck không nhất thiết là tài nguyên có phần trăm cao nhất

CPU server 80% có thể chấp nhận được nếu hệ thống đáp ứng SLO và không có hàng đợi tăng. Ngược lại CPU 20% vẫn có thể đi kèm I/O wait hoặc network timeout rất cao.

### 1.2. Một bottleneck có thể di chuyển

Sau khi tạo index, thời gian đọc dữ liệu có thể giảm và điểm nghẽn tiếp theo chuyển sang JSON serialization, network transfer hoặc service bên ngoài.

### 1.3. Phân biệt triệu chứng và nguyên nhân

| Triệu chứng | Có thể do |
| --- | --- |
| API p95 tăng | Queue, GC, query, I/O, network hoặc downstream |
| MongoDB CPU tăng | Quét nhiều dữ liệu, aggregation, high QPS, compression |
| Disk utilization cao | Cache miss, write volume, checkpoint, backup |
| Nhiều connections | Pool scaling, leak, connection churn hoặc nhiều instances |
| Request timeout | Server quá tải, pool wait, network, retry, deadline ngắn |
| MongoDB explain nhanh | API có thể chậm ở network, pool, app hoặc data mapping |
| Network bytes cao | Large docs, unbounded results, N+1, backup, replication |
| Write latency tăng | Majority replication, journaling, locks, storage hoặc network |

Không chọn giải pháp chỉ từ một dòng triệu chứng.

## 2. Bốn lớp chẩn đoán chính

### 2.1. Ứng dụng

Bao gồm:

- Request queue và thread/event-loop scheduling.
- Connection pool checkout và tạo kết nối.
- Garbage collection, memory pressure.
- Serialization/deserialization BSON/JSON.
- Mapping objects/ORM và business logic.
- N+1 queries, số database round trips.
- Retries, timeouts, circuit breakers.
- Thread pool cho HTTP, background jobs và driver.
- CPU processing sau khi nhận documents.

### 2.2. Truy vấn MongoDB

Bao gồm:

- Filter không có index phù hợp.
- Sắp xếp ngoài index.
- Aggregation pipeline quét quá nhiều.
- Số documents/keys examined lớn so với returned.
- $lookup, $unwind hoặc $group tốn kém.
- Plan selection và plan cache behavior.
- Shard scatter-gather.
- Transactions dài, contention và write conflicts.
- High-frequency small queries.

### 2.3. Storage và MongoDB engine

Bao gồm:

- Data/index working set lớn hơn cache khả dụng.
- Nhiều cache misses và disk reads.
- Disk IOPS, throughput, latency.
- Dirty pages, checkpoints, journal.
- Compression/decompression.
- Filesystem/snapshot/backup load.
- Oplog và replication disk writes.
- Data growth, fragmentation hoặc thiếu headroom.

### 2.4. Mạng

Bao gồm:

- Client-server round-trip time (RTT).
- Cross-region routing.
- Bandwidth và packet loss.
- DNS/SRV resolution.
- TLS handshake và connection churn.
- Load balancer, firewall, NAT, proxies.
- Large response payload.
- Retransmits và transient disconnections.

Đừng đồng nhất “request đi tới MongoDB chậm” với “MongoDB thực thi query chậm”.

## 3. Các chỉ số nền tảng

### 3.1. Latency

Thời gian từ lúc một operation bắt đầu đến lúc hoàn tất, ví dụ API latency hoặc database command latency.

### 3.2. Throughput

Số requests/operations xử lý trong một đơn vị thời gian:

~~~text
requests/second
queries/second
documents/second
bytes/second
~~~

### 3.3. Utilization

Mức sử dụng tài nguyên: CPU, RAM, disk, network, connection pool.

### 3.4. Saturation

Mức tài nguyên trở nên bão hòa, biểu hiện qua queue depth, wait time, throttling, timeouts, admission control hoặc dropped requests.

### 3.5. Errors

Tỷ lệ timeout, connection errors, write conflicts, retryable errors, rejected requests và application failures.

### 3.6. Tail latency

P50 là median, P95 và P99 mô tả phần đuôi của phân phối. Với API có yêu cầu trải nghiệm người dùng, P95/P99 thường quan trọng hơn average.

| Metric | Ví dụ giả định | Diễn giải |
| --- | --- | --- |
| p50 | 30 ms | Phần lớn requests khá nhanh |
| p95 | 700 ms | 5% requests chậm hơn mức này |
| p99 | 2.200 ms | Đuôi chậm nghiêm trọng |
| Error rate | 1.5% | Một phần requests thất bại |
| QPS | 4.000 | Tải có thể cao hơn baseline |

Tất cả số liệu chỉ minh họa, không phải kết quả đo của hệ thống cụ thể.

## 4. Latency budget end-to-end

Một request có thể chia thành các khoảng thời gian **không chồng nhau** theo thứ tự thực hiện:

~~~text
Total API latency
  |
  +-- HTTP queue / dispatch
  +-- Application logic before DB
  +-- Driver connection checkout
  +-- Connection establishment if needed
  +-- Network request transit
  +-- MongoDB scheduling/query execution/storage waits
  +-- Network response transit
  +-- Driver decode / result iteration
  +-- Application mapping/JSON rendering
  +-- Other dependencies / response sending
~~~

Có thể viết gần đúng:

\[
T_{\mathrm{API}} \approx
T_{\mathrm{queue}}+
T_{\mathrm{app}}+
T_{\mathrm{pool}}+
T_{\mathrm{connect}}+
T_{\mathrm{wire}}+
T_{\mathrm{server}}+
T_{\mathrm{decode}}+
T_{\mathrm{response}}
\]

Đây là mô hình đơn giản cho một chuỗi tuần tự. Nếu xử lý song song, retry, nhiều queries hoặc chồng nhau, phải dùng trace để xác định **critical path**; không cộng các span chồng thời gian một cách mù quáng.

### 4.1. Ví dụ API chậm do pool

~~~text
HTTP queue:                5 ms
Business logic:           20 ms
Pool checkout wait:      780 ms
DB command RTT:           35 ms
Serialization/response:   30 ms
Total:                   870 ms
~~~

Ở đây điểm cần điều tra đầu tiên là **connection pool checkout wait**, chưa phải index.

### 4.2. Ví dụ API chậm do query

~~~text
HTTP queue:                5 ms
Business logic:           10 ms
Pool checkout wait:        2 ms
DB command RTT:         1,100 ms
Serialization/response:   25 ms
Total:                 1,142 ms
~~~

Cần xác định DB command RTT cao do server execution, large response hoặc network, rồi mới chọn hướng.

### 4.3. Không trừ sai thành phần

Command monitoring của driver đo một giai đoạn có thể **bao gồm server xử lý và network**, nhưng thường không bao gồm thời gian chờ lấy connection trước khi gửi command. Cũng có thể không bao gồm việc ứng dụng tiêu thụ toàn bộ cursor sau command đầu tiên. Không đồng nhất mọi metric driver với server-only execution time.

## 5. Đo đúng đơn vị công việc

Trước khi bật công cụ chẩn đoán cần chọn:

- Endpoint hoặc business transaction bị chậm.
- Tenant, loại request, dữ liệu đầu vào.
- Read/write operation và query shape.
- Thời điểm, traffic level, region.
- Deployment/driver version.
- Index và query options.
- SLO về latency/throughput/error.

### 5.1. Query shape quan trọng

Hai calls cùng API có thể có điều kiện khác:

~~~javascript
db.orders.find({
  tenantId: "A",
  status: "paid"
});
~~~

và:

~~~javascript
db.orders.find({
  tenantId: "A",
  status: {
    $in: ["paid", "failed", "cancelled"]
  }
});
~~~

Index selectivity và số documents trả về khác nhau. Nếu chỉ đo một mẫu thuận lợi, dễ bỏ sót những request chậm.

### 5.2. Chia theo phân khúc

Nên xem p95 theo:

- Endpoint.
- Query shape.
- Tenant nhỏ/lớn.
- Region.
- MongoDB node/cluster.
- Payload bucket.
- Cache hit/miss.
- Read concern/write concern.
- Thời gian trước/sau deploy.

### 5.3. Ghi baseline

Ví dụ:

~~~text
Endpoint: GET /orders
Baseline p95: 120 ms
Current p95: 680 ms
QPS baseline/current: 500 / 520
MongoDB command p95: 45 / 60 ms
Pool checkout p95: 10 / 480 ms
App CPU baseline/current: 45% / 90%
~~~

Những số giả định này gợi ý ứng dụng/connection pool bão hòa hơn là query server tự đột nhiên chậm 6 lần.

## 6. Phương pháp điều tra theo giả thuyết

Một chu trình có kiểm soát:

1. **Xác định triệu chứng:** endpoint, thời điểm, p95/p99, error rate.
2. **Khoanh phạm vi:** một service, một tenant, một region hay toàn cluster?
3. **Đo các lớp:** app/driver, MongoDB, storage, network.
4. **Tạo giả thuyết:** ví dụ pool wait cao vì nhiều operations giữ cursor.
5. **Tìm bằng chứng phản bác:** command server time có tăng không?
6. **Thử một thay đổi nhỏ có thể đảo ngược.**
7. **Đo trước/sau ở tải tương tự.**
8. **Ghi kết quả và hành động tiếp theo.**

### 6.1. Không bắt đầu bằng thay đổi index

Tạo index có thể tốn storage và write amplification, không sửa được DNS/TLS delay hay thread pool block.

### 6.2. Không thay đổi nhiều biến một lúc

Nếu cùng lúc tăng pool size, đổi index và tăng instance count, rất khó biết thay đổi nào thực sự cải thiện.

### 6.3. Dùng giả thuyết có thể kiểm chứng

Tốt:

~~~text
"Hơn 70% p95 nằm ở connection checkout,
và số connections in use chạm maxPoolSize."
~~~

Kém:

~~~text
"MongoDB có vẻ chậm nên tăng cấu hình."
~~~

## 7. Quan sát từ phía ứng dụng

Các metric quan trọng:

- HTTP request duration theo route.
- Active requests và request queue length.
- Thread pool utilization.
- Event-loop lag nếu là async runtime.
- Heap usage, allocations, GC pause.
- CPU per process/container.
- Connection pool in-use/available/pending checkout.
- Connection creation rate.
- MongoDB command duration/error.
- Result cursor iteration duration.
- JSON serialization/payload bytes.
- Retries và timeout counters.

### 7.1. Tracing theo request ID

Một distributed trace nên chứa:

~~~text
traceId: abc...
  HTTP GET /orders             650 ms
    auth middleware             15 ms
    business preparation         8 ms
    mongo pool checkout        480 ms
    find command round-trip     60 ms
    cursor getMore              30 ms
    json response               40 ms
~~~

Các spans phải có timestamps để nhận biết sequence/overlap. Hệ thống instrumentation thực tế có thể đặt span boundaries khác nhau.

### 7.2. Đừng log raw query values có PII

Khi thu thập command events, query có thể chứa thông tin khách hàng, token hoặc confidential documents. Nên log command name, namespace, duration, safe query shape, traceId và lỗi đã redact.

## 8. Connection pool — nút thắt ứng dụng điển hình

MongoDB drivers duy trì connection pools đến các servers. Một operation có thể cần **checkout** một connection trước khi gửi lệnh.

### 8.1. Pool quá nhỏ hoặc connection bị giữ lâu

~~~text
Max pool connections: 100
Active connections:   100
Pending checkouts:    180
Checkout p95:         700 ms
Server command p95:    20 ms
~~~

Ứng dụng phải đợi mặc dù một command khi đã chạy có thể nhanh.

### 8.2. Không mặc định cứ tăng maxPoolSize

Pool wait cao có thể do:

- Ứng dụng tạo quá nhiều concurrent requests.
- N+1 queries.
- Cursor đọc chậm/không được đóng đúng.
- Long-running transactions.
- Thread pool giữ operation lâu.
- MongoDB server chậm làm connections bị chiếm.
- Spike traffic hoặc retry storm.

Tăng pool size có thể chỉ chuyển nghẽn từ ứng dụng sang MongoDB, tăng connections và CPU.

### 8.3. maxPoolSize và maxConnecting khác nhau

- maxPoolSize giới hạn kích thước pool theo cấu hình.
- maxConnecting giới hạn số kết nối có thể được tạo đồng thời trong một pool, theo driver/version.

Connection storm sau restart có thể liên quan tốc độ tạo kết nối/TLS chứ không chỉ pool size tối đa.

### 8.4. Wait queue timeout

Nếu checkout chờ vượt thời hạn của driver, ứng dụng có thể nhận timeout khi chưa gửi query đến MongoDB. Server profiler sẽ không thấy một truy vấn tương ứng đã chạy.

### 8.5. Dùng một MongoClient tái sử dụng

Trong Java Sync Driver, thông thường nên tạo MongoClient dùng chung theo lifecycle ứng dụng. Tạo client mới cho mỗi HTTP request có thể tạo connection churn, DNS/TLS overhead và áp lực server connections.

## 9. Thread pool, event loop và ứng dụng bị chặn

### 9.1. Java thread pool bão hòa

Nếu API dùng thread pool hữu hạn và tất cả threads đang chờ I/O, request mới vào queue. Có thể thấy HTTP p95 cao trước cả khi MongoDB driver được gọi.

### 9.2. Synchronous driver trong async path

Gọi thao tác blocking trên event loop không phù hợp có thể khiến các requests khác bị giữ. Cần chọn execution model đúng: xử lý blocking trên worker threads hoặc dùng reactive driver phù hợp khi kiến trúc yêu cầu.

### 9.3. Garbage collection

GC pause dài có thể làm toàn bộ ứng dụng ngưng xử lý, tạo p99 spikes dù MongoDB không có spike tương ứng.

Dấu hiệu:

- JVM GC pause logs.
- Heap gần giới hạn.
- Allocation rate tăng.
- JSON/BSON object mapping khối lượng lớn.
- Tăng đột biến sau deploy.

### 9.4. CPU phía ứng dụng

Encryption, compression, custom aggregation in memory, JSON serialization, regex hay dữ liệu mapping nặng có thể chiếm CPU. Một API truy vấn nhanh vẫn chậm nếu phải chuyển hàng chục MB BSON thành JSON.

## 10. N+1 queries và quá nhiều round trips

Ví dụ lấy danh sách 100 bookings rồi thực hiện thêm một query cho từng customer:

~~~text
1 query load 100 bookings
100 queries load customers
--------------------------
101 database round trips
~~~

Nếu RTT trung bình 5 ms và queries chạy tuần tự, chỉ network/command overhead cũng có thể đáng kể.

### 10.1. Dấu hiệu

- Một HTTP request sinh hàng chục/hàng trăm MongoDB commands.
- Mỗi command nhanh nhưng tổng API chậm.
- Server QPS tăng nhanh hơn business request rate.
- Driver monitoring cho thấy nhiều find/getMore.

### 10.2. Giải pháp có điều kiện

- Batch lookup bằng $in với kích thước hợp lý.
- $lookup khi schema/index/plan phù hợp.
- Embed dữ liệu nhỏ thường được đọc cùng nhau.
- Cache có kiểm soát.
- Tránh load các field không cần.

Không gom tất cả dữ liệu vào một document quá lớn; cần cân bằng giới hạn BSON, update patterns và query cardinality.

## 11. Cursor và getMore

Truy vấn find hoặc aggregation có thể trả một cursor theo batches.

~~~text
find -> first batch
     -> getMore
     -> getMore
     -> close cursor
~~~

### 11.1. Vì sao command first response nhanh nhưng API chậm?

Ứng dụng có thể cần nhiều getMore để đọc toàn bộ results. Nếu chỉ đo command find đầu tiên, sẽ bỏ qua các round trips còn lại.

### 11.2. Batch size

Batch size ảnh hưởng số trips và lượng dữ liệu/buffer. Quá nhỏ tăng getMore; quá lớn có thể tăng memory và payload. Chọn theo workload.

### 11.3. Đọc số lượng kết quả

Nếu API chỉ cần 20 bản ghi, dùng limit và projection đúng thay vì đọc hàng chục nghìn documents rồi cắt trong Java.

### 11.4. Đóng cursor

Cursor không được đóng hoặc iterators bị giữ có thể tốn resources. Dùng try-with-resources khi phù hợp và không materialize lượng dữ liệu không giới hạn.

## 12. Retries, timeouts và retry storms

### 12.1. Retry giúp chịu lỗi nhưng có chi phí

Nếu MongoDB/network chậm, mỗi request tự retry nhiều lần có thể nhân tải lên, khiến sự cố kéo dài.

### 12.2. Dấu hiệu

- Số attempts/request tăng.
- Error rate tăng trước throughput.
- MongoDB ops/sec tăng dù traffic người dùng ổn định.
- Pool wait và server latency cùng tăng.
- Timeouts xảy ra gần cùng một deadline.

### 12.3. Retry có backoff/jitter

Cần phân loại lỗi retryable, giới hạn attempts, deadline tổng và idempotency cho writes. Không retry tùy tiện thao tác không idempotent.

### 12.4. Phân biệt thời gian timeout

- HTTP request timeout.
- Connection checkout timeout.
- Connection establishment timeout.
- Socket read timeout.
- Server-side maxTimeMS.
- Transaction timeout.

Cùng tên “timeout” nhưng gợi ý lớp lỗi khác nhau.

## 13. MongoDB query execution — bắt đầu từ đâu?

Với query chậm, cần xem:

1. Query shape và bind values thực.
2. Index inventory.
3. Explain plan.
4. Documents/keys examined.
5. Sort/aggregation stages.
6. Output count/payload size.
7. Server resource metrics tương ứng.
8. Kế hoạch trên từng shard khi sharded.

### 13.1. Explain trên truy vấn đại diện

~~~javascript
use rental

db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

### 13.2. explain không đo toàn bộ ứng dụng

Explain giúp hiểu query planner/execution trên server. Nó không bao gồm HTTP serialization, pool checkout hoặc toàn bộ latency network ở client.

### 13.3. Tải và cache ảnh hưởng số liệu

Một explain trên dataset staging nhỏ/cold hoặc production warm có thể khác. Ghi điều kiện thử nghiệm, query values và data distribution.

## 14. Đọc executionStats

Những field thường hữu ích:

- **nReturned**: số documents/rows được trả tại giai đoạn tương ứng.
- **totalDocsExamined**: documents examined.
- **totalKeysExamined**: index keys examined.
- **executionTimeMillis**: thời gian execution theo phép đo của explain, không đồng nhất client latency.
- **winningPlan** và stages: cách server thực thi.
- Stage-specific metrics như sort spill/disk usage khi phiên bản hỗ trợ.

### 14.1. Ví dụ kém hiệu quả

~~~text
nReturned         = 20
totalDocsExamined = 500000
totalKeysExamined = 0
winningPlan       = COLLSCAN
~~~

Một phép đọc lấy 20 kết quả nhưng quét 500.000 documents có khả năng gây tải lớn.

### 14.2. Ví dụ index hiệu quả hơn

~~~text
nReturned         = 20
totalDocsExamined = 20
totalKeysExamined = 20
winningPlan       = IXSCAN + FETCH
~~~

Không phải mọi query tốt đều có tỷ lệ đúng 1:1; ranges và selectivity có thể khiến keysExamined cao hơn nReturned một cách hợp lý.

### 14.3. Covered query

Một query được phục vụ từ index có thể không cần FETCH documents, khi field được truy vấn và projection nằm trong index theo điều kiện phù hợp. Vì vậy totalDocsExamined có thể bằng 0.

### 14.4. Không so field mà quên limit

Một query có limit 20 có thể dừng sau 20 hits; một query quét toàn bộ dữ liệu để tính tổng cần loại đánh giá khác. Chọn metrics theo mục tiêu query.

## 15. COLLSCAN không phải luôn sai

Collection scan có thể hợp lý khi:

- Collection rất nhỏ.
- Query phải đọc phần lớn dữ liệu.
- Không có index hữu ích cho filter.
- Query là batch/analytics có thời hạn khác.
- Index lookup sẽ tốn hơn scan trong tình huống cụ thể.

### 15.1. Khi nào COLLSCAN đáng nghi?

- Trên collection lớn.
- Query chạy thường xuyên.
- Return ít documents.
- CPU/disk tăng cùng slow queries.
- Explain cho thấy totalDocsExamined rất cao.

### 15.2. Đừng tạo index cho mọi filter đơn lẻ

Nhiều indexes tăng chi phí writes, storage và cache. Thiết kế index dựa trên query patterns, compound predicates, sort/projection và selectivity.

## 16. Index không phù hợp và sort

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20);
~~~

Một index đáng cân nhắc:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

**Đây chỉ là ví dụ thiết kế**, không phải lệnh phải chạy ngay trên production. Cần kiểm tra query patterns, cardinality, write costs và explain trước khi tạo.

### 16.1. ESR heuristic

Trong nhiều trường hợp, thứ tự equality, sort, range có thể là gợi ý cho compound index, nhưng không phải một quy tắc tuyệt đối cho mọi truy vấn hoặc distribution.

### 16.2. Blocking sort

Nếu MongoDB không thể trả documents đã có thứ tự từ index, stage SORT có thể tốn memory/CPU và có thể spill ra disk khi operation và server settings hỗ trợ.

### 16.3. Sort kết quả nhỏ chưa chắc cần index mới

Nếu collection nhỏ hoặc sort được giới hạn số documents thích hợp, việc thêm index có thể không đáng chi phí.

### 16.4. Kiểm chứng sau thay đổi

So docs examined, keys examined, latency/CPU dưới tải tương tự và write throughput. Không chỉ xem có xuất hiện IXSCAN là tuyên bố thành công.

## 17. Aggregation pipeline có thể là nguồn nghẽn

Một pipeline:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "confirmed"
    }
  },
  {
    $group: {
      _id: "$customerId",
      total: { $sum: "$amount" }
    }
  },
  {
    $sort: {
      total: -1
    }
  },
  {
    $limit: 20
  }
]);
~~~

### 17.1. Đặt $match sớm khi hợp lệ

Giảm tập ứng viên trước những stages tốn CPU/memory, nhưng phải giữ semantics và cho query planner tối ưu.

### 17.2. $unwind làm tăng cardinality

Một document có 100 items khi unwind có thể thành 100 records tạm. Sau nhiều stages, intermediate rows có thể lớn hơn collection ban đầu nhiều lần.

### 17.3. $lookup

Có thể gây nhiều lookups hoặc đọc nhiều dữ liệu ở collection khác; cần index trên join keys và kiểm tra explain/plan cho execution path thực tế.

### 17.4. $group và $sort

Các stages blocking có thể cần memory lớn hoặc spill. Quan sát profiler/explain và resource metrics; không mặc định mọi aggregation đều stream được.

### 17.5. allowDiskUse là trade-off

Cho phép spill có thể giúp operation hoàn tất khi memory giới hạn, nhưng có thể chuyển nghẽn sang disk I/O. Không bật như giải pháp duy nhất mà bỏ qua pipeline design.

## 18. Query planner và plan cache

MongoDB chọn plan dựa trên query shape, indexes, data distribution và engine/version. Plan từng nhanh có thể chậm hơn khi dữ liệu thay đổi.

### 18.1. Triệu chứng

- Một số query shapes chậm đột ngột.
- Index inventory không đổi.
- Query values có selectivity rất khác.
- Explain/winning plan khác so baseline.
- Latency tăng sau data growth hoặc deploy.

### 18.2. Không hint index ngay như giải pháp lâu dài

Hint có thể giúp thử nghiệm, nhưng ép một plan có thể không phù hợp với mọi query values. Cần xác định nguyên nhân và đánh giá representative workloads.

### 18.3. Query plan metrics có thể thay đổi theo engine

Classic execution và Slot-Based Execution (SBE) có cấu trúc explain khác nhau. Đọc stages dựa trên version thực tế, không viết parser phụ thuộc một đường JSON duy nhất.

## 19. Dữ liệu lớn trả về là bottleneck

Một truy vấn có thể dùng index đúng nhưng trả hàng chục MB dữ liệu:

~~~javascript
db.events.find({
  tenantId: "tenant-a"
});
~~~

Nếu API thật chỉ cần ID và timestamp, nên projection:

~~~javascript
db.events.find(
  {
    tenantId: "tenant-a"
  },
  {
    _id: 1,
    eventType: 1,
    createdAt: 1
  }
).limit(100);
~~~

### 19.1. Index tốt không thay payload reduction

Server có thể tìm đúng documents nhanh nhưng vẫn cần đọc/serialize, truyền mạng và parse toàn bộ field lớn nếu client yêu cầu.

### 19.2. Pagination

Tránh trả vô hạn. Với data lớn, keyset pagination theo index có thể tốt hơn skip rất sâu, tùy API semantics.

### 19.3. BSON size limit

Giới hạn 16 MiB áp dụng cho một document BSON, không có nghĩa API response chỉ tối đa 16 MiB. Cursor nhiều batches có thể chuyển nhiều bytes.

## 20. Writes chậm không chỉ do index

Một write đi qua nhiều giai đoạn:

~~~text
Application
    |
    v
Network
    |
    v
MongoDB write execution
    |
    +-- validation
    +-- document/index update
    +-- conflict/locking
    +-- journal/storage work
    +-- replication/acknowledgement policy
    |
    v
Acknowledgement to application
~~~

### 20.1. Index overhead

Mỗi insert/update có thể phải cập nhật nhiều indexes. Thêm index để tăng tốc reads có thể làm writes tốn CPU/storage hơn.

### 20.2. Unique constraints

Unique indexes cần kiểm tra tính duy nhất; nếu workload contention cao trên một key/record, retries có thể xuất hiện.

### 20.3. Write concern

Write concern ảnh hưởng thời điểm acknowledged, ví dụ w:1 và majority có khác biệt. Không hạ write concern chỉ để giảm latency mà bỏ yêu cầu durability/consistency.

### 20.4. Journal và fsync

Độ trễ storage có thể ảnh hưởng commit/checkpoint/journaling theo engine/settings. Cần xem metrics database và disk, không chỉ explain của read query.

### 20.5. Replication lag

Nếu writes majority phải đợi acknowledgements từ các members phù hợp, network/IO của secondary có thể ảnh hưởng latency. Quan sát health và lag theo topology.

## 21. Lock contention và transactions

MongoDB có cơ chế concurrency control; không phải mỗi query chậm đều do global lock.

### 21.1. Khi nào nghi contention?

- Nhiều writes cùng record hoặc nhóm keys.
- Write conflicts tăng.
- Transactions kéo dài.
- Operations chờ tài nguyên.
- Latency tăng theo concurrency nhưng CPU/disk chưa đầy.

### 21.2. Long-running transactions

Có thể giữ resources, tăng cache pressure và gây write conflicts. Đặt transaction scope ngắn, tránh gọi API ngoài trong transaction khi không cần.

### 21.3. Retry transaction an toàn

Phân loại transient transaction errors, retry theo driver guidance, nhưng cần idempotency với side effects bên ngoài.

### 21.4. Quan sát lock metrics

serverStatus và currentOp có thể cho tín hiệu liên quan waits/locks theo version. Không suy “locks cao” bằng một con số tổng mà thiếu thời gian, operation mix và workload baseline.

## 22. MongoDB profiler và slow operations

Khi cần tìm queries chậm thực tế, có thể dùng profiler hoặc Atlas query insights/real-time metrics theo khả năng deployment.

### 22.1. Kiểm tra profiling status

~~~javascript
db.getProfilingStatus();
~~~

### 22.2. system.profile

Khi profiling đang được bật và dữ liệu được ghi, có thể quan sát:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    ns: 1,
    op: 1,
    millis: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({
  ts: -1
}).limit(20);
~~~

Field names/availability phụ thuộc version/operation.

### 22.3. Cẩn thận khi bật profiler

Ví dụ sau **chỉ dành cho môi trường đã được phê duyệt**, không tự chạy trên production:

~~~javascript
db.setProfilingLevel(1, {
  slowms: 100
});
~~~

Profiling có overhead, có thể lưu query details nhạy cảm và hoạt động khác nhau theo triển khai, đặc biệt managed services. Cần cân nhắc threshold/sampling/retention và permissions.

### 22.4. Slow log không bao gồm mọi request chậm

Một HTTP request có thể chậm do pool wait hoặc network trước khi command được gửi. Không thấy slow query trong profiler không chứng minh ứng dụng không chậm vì database-related resource waits.

## 23. currentOp: xem operations đang chạy

Khi có quyền thích hợp, có thể dùng:

~~~javascript
db.currentOp();
~~~

Hoặc aggregation trên admin với $currentOp theo deployment và permissions.

### 23.1. currentOp là snapshot

Nó phản ánh những operations đang diễn ra tại thời điểm quan sát, không phải lịch sử đầy đủ của những requests đã kết thúc.

### 23.2. Những câu hỏi hữu ích

- Có operation chạy lâu không?
- Có nhiều operations cùng query shape không?
- Có cursor/getMore giữ tài nguyên?
- Có lock waits hoặc transaction kéo dài?
- Có một aggregation đang scan rất lớn?

### 23.3. Cẩn thận với thông tin nhạy cảm

Thông tin currentOp có thể chứa command/filter values. Giới hạn quyền, sanitize logs/screenshots và không lưu raw query của khách hàng bừa bãi.

### 23.4. Không killOp tùy tiện

Dừng operation có thể phá công việc hợp lệ hoặc làm ứng dụng retry. Chỉ dùng quy trình sự cố đã được phê duyệt khi thực sự cần.

## 24. serverStatus và metrics MongoDB

Ví dụ:

~~~javascript
db.serverStatus();
~~~

Kết quả có thể chứa nhiều nhóm metrics:

- opcounters.
- connections.
- network bytes/requests.
- WiredTiger cache/transactions.
- globalLock/locks.
- metrics liên quan operations.
- Mem/process/replication theo cấu hình.

### 24.1. serverStatus là dữ liệu kỹ thuật, không phải API ổn định từng field

Cấu trúc field phụ thuộc MongoDB version, storage engine và topology. Không viết dashboard chỉ dựa trên một ví dụ JSON bất biến.

### 24.2. Counters khác rates

Một metric tăng từ khi process khởi động không tự là QPS. Phải tính delta trong khoảng thời gian:

\[
rate \approx
\frac{counter(t_2)-counter(t_1)}
{t_2-t_1}
\]

### 24.3. Quan sát theo node

Primary/secondary có workload khác nhau. Nếu chỉ xem cluster-level average có thể che một node đang nghẽn.

### 24.4. Atlas metrics

Nếu dùng Atlas, các biểu đồ cluster/process về operation execution, disk IOPS/latency, connections, CPU, cache và network có thể hữu ích; tên và khả năng có thể thay đổi theo phiên bản/tier.

## 25. Storage engine và working set

MongoDB thường dùng WiredTiger. Truy vấn có thể đọc dữ liệu/index từ cache hoặc cần truy xuất disk.

### 25.1. Working set

Là phần dữ liệu/index đang được workload truy cập thường xuyên. Nếu working set không phù hợp cache khả dụng, hệ thống có thể liên tục phải nạp trang từ disk.

### 25.2. Dấu hiệu cache pressure

- Cache eviction hoạt động mạnh.
- Tăng disk reads/cache misses.
- Disk read latency tăng.
- Query p95 tăng khi dữ liệu/phạm vi truy vấn lớn.
- CPU có thể không đạt 100%.

### 25.3. Không nhìn cache hit ratio một mình

Một số workload analytic chủ động scan dữ liệu lớn; cache miss không nhất thiết là lỗi cần nâng RAM. Cần xem working set, query design và storage throughput cùng nhau.

### 25.4. Compression và CPU

Compression giảm bytes trên disk/network storage nhưng có chi phí CPU. Nếu hệ thống CPU-bound, compression/decompression có thể góp phần vào tải.

## 26. WiredTiger cache và eviction

Các biểu đồ quan trọng có thể gồm:

- Bytes currently in cache.
- Dirty bytes.
- Pages read into cache.
- Pages written/evicted.
- Eviction activity.
- Cache pressure metrics.

Tên field cụ thể thay đổi theo version; dùng tài liệu của release thực tế.

### 26.1. Cache đầy có phải luôn nghẽn?

Một cache được thiết kế sử dụng RAM tích cực. **Tỷ lệ dùng cache cao không tự là sự cố**. Cần xem eviction latency, pages read, disk I/O và query tail latency.

### 26.2. Eviction gây độ trễ

Khi dirty pages hoặc cache pressure lớn, application threads có thể chịu chi phí eviction/writes theo engine behavior. Chẩn đoán bằng metrics chuỗi thời gian và workload tương quan.

### 26.3. Đừng tăng cache size không cân nhắc

Hệ điều hành, filesystem cache và các process khác cũng cần memory. Thay đổi cache settings có thể gây swapping/OOM hoặc chuyển nghẽn, cần thử nghiệm có kiểm soát.

## 27. Disk IOPS, throughput và latency

Ba thông số khác nhau:

- **IOPS:** số I/O operations mỗi giây.
- **Throughput:** bytes/giây.
- **Latency:** thời gian mỗi I/O chờ hoàn tất.

### 27.1. IOPS cao chưa chắc disk nghẽn

Nếu disk đáp ứng IOPS với latency thấp và không có queue, utilization cao có thể vẫn ổn.

### 27.2. Dấu hiệu storage bottleneck

- Read/write latency tăng mạnh.
- Disk queue depth tăng.
- IOPS chạm provisioned limit.
- I/O throttling/credits cạn.
- Query latency tăng đồng thời.
- Cache misses hoặc checkpoints trùng thời điểm.
- CPU server tương đối thấp nhưng throughput không tăng.

### 27.3. Storage tier và burst credits

Trong cloud, disk performance có thể phụ thuộc capacity/provisioned IOPS/burst behavior. Khi credits cạn, workload không đổi nhưng latency tăng.

### 27.4. Phân biệt bandwidth và IOPS

Nhiều random small reads thường bị giới hạn IOPS; file scans/large sequential operations có thể bị giới hạn throughput.

## 28. Checkpoint, journal và background I/O

Không phải mọi disk activity đều đến từ query user.

Nguồn khác:

- WiredTiger checkpoints.
- Journaling.
- Index builds.
- TTL deletes.
- Backups/snapshots.
- Compaction/maintenance.
- Oplog writes và replication.
- Data migration/rebalancing.

### 28.1. Chậm theo chu kỳ

Nếu p95 tăng đều theo chu kỳ trong khi QPS ổn định, kiểm tra checkpoint, backup, scheduled jobs hoặc TTL sweeps.

### 28.2. Không dừng backup chỉ vì latency tăng

Backup là một phần của yêu cầu phục hồi. Nếu gây contention, xem scheduling, resource provisioning hoặc backup strategy thay vì vô hiệu hóa không kiểm soát.

### 28.3. Index build cạnh tranh I/O

Tạo index lớn trên production có thể tăng CPU/disk. Lập kế hoạch và quan sát theo phiên bản/size để không làm ảnh hưởng SLA.

## 29. Storage capacity và fragmentation

Khi disk gần đầy:

- Write failures hoặc thiếu headroom.
- Compaction/index build không có chỗ.
- Restore/migration khó thực hiện.
- Filesystem behavior suy giảm.
- Autoscaling không đáp ứng đủ nhanh.

### 29.1. Data size khác storage size

MongoDB dataSize, storageSize, indexSize và filesystem usage là các chỉ số khác nhau. Không lấy một con số của một collection để suy toàn disk.

### 29.2. Chỉ tăng disk không sửa query design

Nếu một truy vấn luôn scan vài triệu records, cấp disk lớn hơn có thể tạm giảm độ trễ nhưng chưa giải quyết nguyên nhân.

### 29.3. Dữ liệu tăng làm working set đổi

Một index phù hợp hôm qua có thể vẫn đúng logic nhưng working set nay vượt cache. Cần theo dõi growth và access patterns.

## 30. Replication và secondary bottleneck

Replica set có thể có primary xử lý writes và secondaries nhận oplog/replay.

### 30.1. Majority write latency

Nếu một secondary cần thiết để đạt majority có disk/network chậm, acknowledgement có thể chậm hơn dù primary CPU thấp.

### 30.2. Secondary reads

Nếu ứng dụng cấu hình read preference đến secondary, tail latency có thể khác giữa members. Một secondary quá tải có thể gây chỉ một nhóm requests chậm.

### 30.3. Replication lag

Lag tăng có thể do write throughput, network hoặc disk/CPU phía secondary. Phải phân biệt nguyên nhân theo metrics từng member.

### 30.4. Không hạ majority chỉ để giảm p95

Read/write concern là lựa chọn về durability/consistency. Thay đổi vì performance cần được duyệt theo yêu cầu nghiệp vụ.

## 31. Sharded cluster và routing

MongoDB sharding bổ sung:

~~~text
Application
    |
    v
mongos
    |
    +--> shard A
    +--> shard B
    +--> shard C
~~~

### 31.1. Targeted query vs scatter-gather

Nếu filter chứa shard key phù hợp, mongos có thể định tuyến đến ít shards. Query thiếu shard key có thể phải gửi tới nhiều shards.

### 31.2. Dấu hiệu

- Nhiều shards tham gia một query đơn giản.
- Latency bằng hoặc vượt shard chậm nhất.
- Network bytes giữa routers/shards tăng.
- Một shard bị hotspot.
- Migrations hoặc balancing gây I/O/network tải.

### 31.3. Explain qua mongos

Dùng explain trên endpoint giống ứng dụng để thấy target shards và execution. Không chỉ kiểm tra trực tiếp một shard.

### 31.4. Không shard để chữa một query thiếu index

Sharding tăng độ phức tạp và có thể thêm network fan-out. Trước tiên xác định index/query design và bottleneck thực.

## 32. Network RTT và khoảng cách địa lý

Độ trễ giữa ứng dụng và MongoDB có thể bị chi phối bởi physical distance và network routing.

### 32.1. Ví dụ số round trips

Giả sử RTT gần đúng 70 ms và API cần 15 database commands tuần tự:

\[
15 \times 70\ \mathrm{ms}=1050\ \mathrm{ms}
\]

Chưa tính server processing và payload. Đây là minh họa cho **N+1/round-trip amplification**.

### 32.2. Đặt service gần database

Nếu workload cần nhiều database calls, đặt application cùng region hoặc gần network topology MongoDB thường giúp giảm RTT. Nhưng cân bằng với availability, compliance và cross-region DR.

### 32.3. Không đồng nhất ping RTT với MongoDB command time

ICMP có thể bị chặn hoặc route/prioritize khác TCP. Dùng application-to-database measurements, TCP/TLS monitoring và driver command spans để kiểm chứng.

### 32.4. Cross-region writes

Majority acknowledgements hoặc cross-region replicas có thể thêm latency tùy topology và write concern; không tự suy tất cả writes luôn bị ràng buộc bởi xa nhất replica.

## 33. Bandwidth, packet loss và retransmits

### 33.1. Large payload

Một query trả 30 MB dữ liệu có thể chậm ngay cả khi MongoDB tìm documents nhanh, nhất là trên đường mạng bandwidth thấp.

### 33.2. Packet loss

Loss/retransmit làm tail latency biến động. Dấu hiệu có thể là p99 spikes, timeouts và throughput thực giảm.

### 33.3. Network saturation

Outbound bytes hoặc NIC utilization chạm giới hạn gây queues; kiểm tra metrics ở app, routers và database nodes.

### 33.4. Compression

Wire compression có thể giảm bandwidth nhưng tiêu tốn CPU và cần hai phía cấu hình/driver hỗ trợ. Không bật/đổi compression như giải pháp chung trước khi biết CPU-bound hay bandwidth-bound.

## 34. DNS, TLS và connection establishment

Một request có thể chậm **trước khi command được gửi**:

~~~text
DNS/SRV lookup
    |
    v
TCP connect
    |
    v
TLS handshake
    |
    v
Authentication
    |
    v
Connection ready
    |
    v
MongoDB command
~~~

### 34.1. Connection churn

Tạo MongoClient mỗi request sẽ liên tục chịu chi phí này. Dùng MongoClient tái sử dụng giúp pool giữ connections theo driver policy.

### 34.2. SRV records và DNS

MongoDB connection strings dạng mongodb+srv có DNS lookup. DNS failures hoặc resolver chậm có thể gây kết nối chậm, nhưng không kết luận chỉ từ một lần nslookup.

### 34.3. TLS certificates

Sai hostname/CA hoặc expiry có thể gây errors. Cần xem exception chính xác; không vô hiệu hóa certificate validation để “tăng tốc”.

### 34.4. Load balancer/NAT idle timeout

Một proxy cắt idle connections có thể gây reconnect hoặc transient errors, đặc biệt sau khoảng thời gian ít traffic. Kiểm tra middlebox settings và driver connection lifecycle.

## 35. Phân biệt network và server latency

Một phương pháp là đối chiếu:

- API latency.
- Driver checkout time.
- Driver command duration.
- MongoDB server observed operation duration.
- Response bytes.
- RTT/loss metrics.

Ví dụ giả định:

~~~text
API p95:                 850 ms
Pool checkout p95:         5 ms
Driver command p95:      800 ms
MongoDB server op p95:    35 ms
Response bytes:        120 KiB
Network RTT:            70 ms
~~~

Sự chênh lệch lớn cần điều tra network/wire, connection behavior, result cursor, instrumentation differences và server timing semantics, không tự kết luận ngay “mạng lỗi”.

### 35.1. Cần so cùng operation

Một p95 aggregate của command events và một p95 profiler theo query khác không thể trực tiếp lấy hiệu hai số rồi khẳng định network = phần chênh.

### 35.2. Correlation ID

Liên kết request/command/trace, timestamps và query shape. Nếu không có correlation, so aggregate chỉ mang tính gợi ý.

### 35.3. Múi giờ và đồng bộ clock

Cross-system timestamps cần UTC và time synchronization để đối chiếu incident windows. Duration trong cùng process thường đáng tin hơn phép trừ hai clocks chưa đồng bộ.

## 36. Một bảng quyết định nhanh

| Bằng chứng nổi bật | Lớp đáng điều tra trước | Cần xác minh thêm |
| --- | --- | --- |
| API p95 cao, DB command p95 thấp, pool wait cao | Ứng dụng/pool | Active pool, concurrency, cursor |
| API queue tăng, chưa gọi DB | Ứng dụng | Threads, CPU, GC |
| totalDocsExamined rất lớn, nReturned nhỏ | Truy vấn | Index/filter/selectivity |
| Sort spill, aggregation memory cao | Truy vấn/storage | Pipeline, spill, disk metrics |
| Disk read latency và cache misses cùng tăng | Storage | Working set, IO limits |
| Write p95 tăng, secondary lag tăng | Replication/storage/network | Member metrics, write concern |
| Server operation nhanh, driver duration cao | Mạng/wire/result handling | RTT, bytes, getMore |
| P99 chỉ tăng sau app deploy | Ứng dụng/driver | Connection lifecycle, changes |
| Một tenant chậm hơn các tenant khác | Query/data skew | Cardinality, shard placement |
| Sau tạo index reads nhanh nhưng writes chậm | Index/write path | Index maintenance, write metrics |
| Chỉ chậm theo chu kỳ backup | Storage/background | IOPS, checkpoint, schedule |
| Tạo nhiều MongoClient liên tục | Ứng dụng/mạng | TLS/DNS/connect rate |

Đây là bảng **ưu tiên kiểm tra**, không phải chẩn đoán chắc chắn.

## 37. Java Sync Driver: MongoClient tái sử dụng

Một mẫu kết nối:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoProvider {

    private final MongoClient client;

    public MongoProvider(String uri) {
        ConnectionString connectionString =
                new ConnectionString(uri);

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                connectionString
                        )
                        .build();

        this.client = MongoClients.create(settings);
    }

    public MongoClient client() {
        return client;
    }

    public void close() {
        client.close();
    }
}
~~~

### 37.1. Lifecycle

Khởi tạo ở application startup, inject/tái sử dụng client và close ở shutdown. Không tạo mới trong mỗi HTTP handler.

### 37.2. Configuration

Các pool, timeout, readPreference, readConcern/writeConcern và TLS options phải dựa trên yêu cầu. Không sao chép một cấu hình maxPoolSize quá lớn sang mọi services.

### 37.3. Không log URI có mật khẩu

Dùng secret manager hoặc environment variable. Nếu diagnostic cần in host/cluster, phải redact username/password.

## 38. Java Sync Driver: command monitoring

CommandListener giúp quan sát duration/error của database commands mà client thực sự gửi.

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.concurrent.TimeUnit;

public class MongoCommandMetrics {

    public static MongoClient create(String uri) {
        CommandListener listener = new CommandListener() {

            @Override
            public void commandStarted(
                    CommandStartedEvent event
            ) {
                System.out.println(
                        "Mongo command started: "
                        + event.getCommandName()
                );
            }

            @Override
            public void commandSucceeded(
                    CommandSucceededEvent event
            ) {
                long ms = event.getElapsedTime(
                        TimeUnit.MILLISECONDS
                );

                System.out.println(
                        event.getCommandName()
                        + " succeeded in " + ms + " ms"
                );
            }

            @Override
            public void commandFailed(
                    CommandFailedEvent event
            ) {
                long ms = event.getElapsedTime(
                        TimeUnit.MILLISECONDS
                );

                System.out.println(
                        event.getCommandName()
                        + " failed in " + ms + " ms"
                );
            }
        };

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri)
                        )
                        .addCommandListener(listener)
                        .build();

        return MongoClients.create(settings);
    }
}
~~~

### 38.1. Ghi metrics thay vì System.out trong production

Ví dụ in ra console để dễ thấy API. Production nên gửi histogram/counters qua telemetry framework, có sampling và không block hot path.

### 38.2. Không log raw commands

Command documents có thể chứa query values, authentication-related data hoặc PII. Chỉ ghi các field an toàn như command name, namespace và elapsed time.

### 38.3. Command time không phải toàn bộ HTTP request

Command duration không tự bao gồm pool checkout, business logic hoặc JSON serialization. Kết hợp với traces cấp application.

### 38.4. Cursor nhiều batches

Nếu response cần getMore, command listener có thể thấy nhiều commands; API latency là tổng critical path chứ không chỉ duration một find command.

## 39. Java Sync Driver: đo thời gian application-level

Ví dụ phân tách bước gọi database và bước mapping:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class OrderReadExample {

    public static List<Document> loadRecentOrders(
            MongoCollection<Document> collection,
            String tenantId
    ) {
        long start = System.nanoTime();

        List<Document> result =
                collection.find(
                        new Document("tenantId", tenantId)
                ).limit(100).into(new ArrayList<>());

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start
        );

        System.out.println(
                "DB find + cursor iteration: "
                + elapsedMs + " ms"
        );

        return result;
    }
}
~~~

### 39.1. Đo đúng cursor iteration

Một find() thường tạo Iterable; việc đọc kết quả diễn ra khi iteration. Đo từ lúc tạo cursor đến sau .into(...) giúp thấy thời gian cấp application cho toàn bộ kết quả.

### 39.2. Kết hợp với driver spans

Nếu application-level DB section là 500 ms nhưng sum các command durations thấp, cần điều tra pool/iteration/transform/scheduling, không tự coi MongoDB execution bằng 500 ms.

### 39.3. Benchmark với System.nanoTime

Dùng monotonic clock để đo duration trong process, thay vì trừ timestamps lấy từ hai máy có thể lệch giờ.

## 40. ConnectionPoolListener và các sự kiện hữu ích

MongoDB Java driver hỗ trợ connection pool monitoring. Các event types có thể liên quan:

~~~text
ConnectionCheckOutStarted
ConnectionCheckedOut
ConnectionCheckOutFailed
ConnectionCheckedIn
ConnectionCreated
ConnectionReady
ConnectionClosed
ConnectionPoolCleared
~~~

Tên Java classes/listener methods phụ thuộc driver version, cần kiểm tra API tương ứng.

### 40.1. Checkout histogram

Đo từ checkOutStarted tới checkedOut hoặc failed cho mỗi checkout event để có p50/p95/p99 wait.

### 40.2. Pool sizing cần theo server address

Một MongoClient có thể có pools tới nhiều servers. Đừng cộng tất cả rồi diễn giải thành một pool duy nhất có giới hạn maxPoolSize chung.

### 40.3. Command monitoring bổ sung, không thay thế pool monitoring

Nếu operation chờ connection trước khi gửi command, commandStarted chưa xuất hiện. Đây là một trong những lý do cần cả hai.

## 41. MongoDB profiler: truy vấn chậm có chọn lọc

Đầu tiên xem trạng thái:

~~~javascript
db.getProfilingStatus();
~~~

Khi đã có dữ liệu và quyền đọc:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    ns: 1,
    op: 1,
    millis: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({
  ts: -1
}).limit(20);
~~~

Chỉ trong môi trường được phép, việc thay mức profiler có dạng:

~~~javascript
db.setProfilingLevel(1, {
  slowms: 100
});
~~~

### 41.1. Cảnh báo overhead và PII

Profiler có thể lưu command details nhạy cảm và tăng chi phí. Managed services có cơ chế monitoring riêng, không phải mọi deployment cho phép chỉnh theo cách giống nhau.

### 41.2. Không chỉ xem một slow operation

Một operation 5 giây xuất hiện một lần mỗi ngày có thể ít ảnh hưởng hơn một query 80 ms chạy 100.000 lần/phút. Cần xét latency × frequency × business criticality.

## 42. MongoDB explain: ví dụ so index

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Giả sử ban đầu:

~~~text
COLLSCAN
nReturned = 20
totalDocsExamined = 450000
executionTimeMillis = 850
~~~

Sau khi **đánh giá và thử** một compound index phù hợp trong môi trường được phép:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Kết quả giả định:

~~~text
IXSCAN + FETCH
nReturned = 20
totalDocsExamined = 20
totalKeysExamined = 20
executionTimeMillis = 8
~~~

### 42.1. Không phải phép đo ngoài đời

Các con số minh họa logic: ít examined records thường giúp giảm CPU/I/O. Kết quả thực phải đo trên dữ liệu và traffic của hệ thống.

### 42.2. Kiểm tra write costs

Một index mới có thể tăng storage và write maintenance. Đánh giá cả read/write SLO trước khi quyết định giữ.

## 43. OS và cloud metrics bổ trợ

Ở lớp host/VM/container có thể theo dõi:

- CPU utilization và load.
- CPU throttling của container.
- Memory/RSS/page faults.
- Disk read/write IOPS.
- Disk latency, queue length.
- Filesystem free space.
- Network throughput/errors/retransmits.
- TCP connections.
- Process restarts/OOM kills.

### 43.1. Container CPU throttling

CPU limit của container có thể khiến latency tăng dù host CPU chưa bão hòa. Kiểm tra cgroup/container metrics theo nền tảng triển khai.

### 43.2. Swap và memory pressure

Nếu host bắt đầu swapping, query latency có thể tăng rõ dù app không thay code. Tránh chỉ nhìn JVM heap hoặc MongoDB cache mà quên OS memory.

### 43.3. Disk burst credits

Trong cloud, disk throttling có thể xuất hiện sau một thời gian tải cao; app slow không nhất thiết bắt đầu ngay khi traffic tăng.

### 43.4. Đừng đo một node rồi áp cho cluster

Trong replica set/sharded cluster, một shard hoặc secondary có thể có I/O chậm riêng. Dashboard cần cho phép breakdown theo node.

## 44. Load test để phân biệt saturation

Chạy load test **trên môi trường được phép**, tăng tải từng bước:

~~~text
100 RPS
  |
  v
200 RPS
  |
  v
400 RPS
  |
  v
600 RPS
~~~

Quan sát throughput thực, p50/p95/p99 latency, errors, queue depth, CPU, disk, connections và network.

### 44.1. Đường cong saturation

~~~text
Load tăng -> throughput tăng gần tuyến tính
Load tiếp tục tăng -> throughput bắt đầu phẳng
Load tăng nữa -> latency/queue/errors tăng nhanh
~~~

Khi throughput không tăng nhưng latency tăng, thường đã chạm một giới hạn tài nguyên hoặc cơ chế điều tiết.

### 44.2. Tạo tải gần workload thật

Phải có read/write mix, document sizes, tenant skew, concurrency, batch size và cache behavior giống ứng dụng. Một vòng for gửi cùng query nhỏ từ local máy không đại diện production.

### 44.3. Bảo vệ hạ tầng

Không dùng load test để đánh “thử” vào production đang có sự cố nếu chưa được phê duyệt và giới hạn rủi ro.

## 45. Little's Law và hàng đợi

Một quan hệ hữu ích cho hệ thống tương đối ổn định:

\[
L = \lambda W
\]

Trong đó:

- L là số công việc trung bình trong hệ thống.
- \(\lambda\) là throughput (công việc/giây).
- W là thời gian trung bình một công việc ở trong hệ thống.

### 45.1. Ví dụ

Nếu throughput = 200 requests/s và latency trung bình = 0,2 s:

\[
L = 200 \times 0,2 = 40
\]

Trung bình có khoảng 40 requests đang ở trong hệ thống.

### 45.2. Ứng dụng chẩn đoán

Nếu throughput không tăng mà số requests đang chờ tăng, W phải tăng hoặc hệ thống không còn steady-state. Queue growth là tín hiệu saturation.

### 45.3. Không dùng Little's Law cho một snapshot bất kỳ

Quan hệ hữu ích dưới giả định ổn định và cùng ranh giới đo. Không nhân p95 latency với average arrival rate rồi coi đó là L chính xác.

## 46. Case study A — ứng dụng chậm do pool

**Triệu chứng giả định:**

~~~text
API p95:             950 ms
MongoDB command p95:  25 ms
Pool checkout p95:   790 ms
DB CPU:               35%
Disk latency:         low
~~~

### 46.1. Giả thuyết

Connections đang bị giữ hoặc số operations concurrent vượt khả năng pool/application.

### 46.2. Bước kiểm tra

- Active/in-use connections.
- Pending checkout queue.
- Long-running cursor/transactions.
- Số MongoClients được tạo.
- Thread pool và retry count.
- Load spike sau deploy.

### 46.3. Hướng khắc phục tùy kết quả

- Reuse MongoClient.
- Đóng cursor đúng.
- Giảm N+1 queries.
- Giới hạn concurrency/backpressure.
- Tuning pool size có benchmark và theo dõi server impact.

**Không:** tạo index ngẫu nhiên hoặc nâng disk IOPS khi chưa có bằng chứng.

## 47. Case study B — truy vấn quét collection

**Triệu chứng giả định:**

~~~text
API p95:               2.0 s
MongoDB command p95:   1.8 s
Server CPU:             95%
Disk latency:           normal
Explain: COLLSCAN
Docs examined:          900000
Docs returned:          15
~~~

### 47.1. Giả thuyết

Query thiếu index/filter dẫn tới scan tốn CPU.

### 47.2. Bước kiểm tra

- Query shape và selectivity.
- Required sort/projection.
- Current indexes.
- Explain on representative values.
- Frequency và write overhead.

### 47.3. Thử nghiệm

Đánh giá compound index phù hợp ở môi trường được phép, đo docs examined, CPU, p95 và write latency.

### 47.4. Không chỉ nhìn CPU

CPU cao là hậu quả có thể có của scan, nhưng cần explain để xác định plan thực tế.

## 48. Case study C — storage/cache pressure

**Triệu chứng giả định:**

~~~text
Query p95:               1.2 s
Docs examined:           200
Server CPU:              40%
Disk read latency p95:   90 ms
Cache misses:            increased
IO queue depth:          high
Working set:             larger than effective cache
~~~

### 48.1. Giả thuyết

Query cần đọc nhiều pages từ disk do working set/caching, hoặc disk đã chạm IOPS/throughput limit.

### 48.2. Bước kiểm tra

- WiredTiger cache and eviction trends.
- Disk read/write IOPS và latency.
- Filesystem free space.
- Backups/checkpoints/index build timing.
- Data/index growth.
- Read pattern theo query.

### 48.3. Hướng cải thiện

- Tối ưu query để giảm data accessed.
- Projection/covered indexes khi có lợi.
- Cân nhắc RAM/cache/storage tier theo workload.
- Điều phối background I/O.
- Kiểm tra scale architecture.

**Không:** mặc định tăng maxPoolSize vì checkout wait cũng có thể là hệ quả của I/O chậm.

## 49. Case study D — mạng/cross-region

**Triệu chứng giả định:**

~~~text
API p95:                820 ms
Pool checkout p95:       5 ms
Server operation p95:   12 ms
Driver command p95:    150 ms
API DB calls:            5 sequential calls
RTT:                    70 ms
Network loss:            occasional
~~~

### 49.1. Giả thuyết

Nhiều round trips và đường mạng xa/không ổn định chiếm thời gian đáng kể.

### 49.2. Bước kiểm tra

- Service/database region.
- Routing path, TCP/TLS metrics.
- Payload size.
- Number of sequential commands.
- DNS/connection churn.
- Differences between driver and server timing.

### 49.3. Hướng cải thiện

- Giảm N+1 calls.
- Batch operations.
- Đặt service gần database khi hợp lý.
- Reuse connections.
- Tối ưu payload/projection.
- Điều tra packet loss/routing.

Không gộp các latency p95 rời rạc thành tổng tuyệt đối; đo critical path bằng tracing.

## 50. Case study E — writes chậm do replication

**Triệu chứng giả định:**

~~~text
Read p95:                  40 ms
Majority write p95:       700 ms
Primary CPU:               45%
Secondary disk latency:  high
Replication lag:         growing
~~~

### 50.1. Giả thuyết

Một hoặc nhiều secondaries bị giới hạn I/O hoặc network khiến acknowledgement/replication bị chậm.

### 50.2. Kiểm tra

- Replica member health.
- Lag per member.
- Write concern thực tế.
- Secondary disk/CPU/network.
- Oplog behavior.
- Load và backup trên secondary.

### 50.3. Hướng xử lý

Khắc phục member/storage/network hoặc sizing, không tự hạ write concern để giấu latency nếu ứng dụng cần majority durability.

## 51. Case study F — N+1 queries sau deploy

**Triệu chứng giả định:**

~~~text
Before deploy: 3 Mongo commands / HTTP request
After deploy:  120 Mongo commands / HTTP request
Each command p50: 4 ms
API p95: 900 ms
MongoDB QPS increased 30x
~~~

### 51.1. Giả thuyết

Một đoạn code đã đổi từ batch fetch sang đọc từng related entity.

### 51.2. Bước kiểm tra

- Distributed traces.
- Driver commands per request.
- Query shapes.
- ORM/mapping code.
- Latency by request payload cardinality.

### 51.3. Giải pháp

Batch lookup hoặc thay data model/query path, rồi đo API latency và QPS. Tăng connection pool có thể chỉ che triệu chứng.

## 52. Case study G — slow API nhưng explain rất nhanh

**Triệu chứng giả định:**

~~~text
MongoDB explain execution:     5 ms
Driver first find command:    12 ms
Cursor total read:           500 ms
JSON response:               300 ms
API total:                  850 ms
Response payload:            18 MB
~~~

### 52.1. Giả thuyết

Vấn đề nằm ở lượng dữ liệu trả, getMore, mapping/serialization và network, không phải filter/index.

### 52.2. Bước kiểm tra

- Number of documents returned.
- Projection.
- Batch size/getMore count.
- Payload bytes.
- JSON serialization timings.
- Client bandwidth.
- Pagination semantics.

### 52.3. Hướng cải thiện

Limit/pagination, projection, streaming nếu phù hợp, nén payload có kiểm soát, tránh build JSON cực lớn trong RAM.

## 53. Quy trình incident triage thực tế

Một bảng runbook:

| Bước | Việc thực hiện | Bằng chứng |
| --- | --- | --- |
| 1 | Xác nhận p95/p99/error và thời điểm | Dashboard/traces |
| 2 | Xác định route/query/tenant/region | Request metadata |
| 3 | So app wait/driver command/server time | Trace spans |
| 4 | Xem pool/threads/GC/retries | App metrics |
| 5 | Xem slow operations/explain | MongoDB metrics |
| 6 | Xem CPU/cache/disk/replication | Server/cloud metrics |
| 7 | Xem RTT/packet loss/payload/TLS | Network metrics |
| 8 | Chọn một giả thuyết và phép thử | Hypothesis note |
| 9 | Thử thay đổi có rollback | Change record |
| 10 | Đo before/after cùng tải | SLO comparison |
| 11 | Ghi root cause/corrective actions | Incident report |

### 53.1. Dùng khoảng thời gian đồng bộ

Không so app p95 trong 09:00–09:10 với server disk IOPS của 10:00–10:10. Time alignment là điều kiện tối thiểu.

### 53.2. Phân biệt correlation và causation

Disk latency và API latency tăng cùng lúc là gợi ý, nhưng cần xác định queries có đọc disk, mức tải và các yếu tố khác.

### 53.3. Theo dõi sau khắc phục

Một thay đổi có thể cải thiện p50 nhưng làm p99 hoặc write rate tệ hơn. Quan sát đủ các SLO và resource budgets.

## 54. Những anti-pattern cần tránh

| Hành động sai | Vì sao sai |
| --- | --- |
| Thấy API chậm là tạo index | Có thể nghẽn pool/network/app |
| Thấy cache dùng nhiều là tăng RAM | Cache cao có thể bình thường |
| Thấy connections nhiều là tăng maxPoolSize | Có thể tạo thêm áp lực server |
| Chỉ dùng mongosh explain để đo API latency | Bỏ app/pool/network/serialization |
| Chỉ xem trung bình latency | Che p95/p99 spikes |
| So p95 của các tập khác nhau bằng phép trừ | Không đo cùng critical path |
| Bật profiler mức cao lâu trên production | Overhead/PII |
| Chạy load test không giới hạn | Gây sự cố thật |
| Hạ write concern để cải thiện p95 | Thay durability semantics |
| Tắt TLS để “tăng tốc” | Rủi ro bảo mật |
| Hạ maxTimeMS tùy ý | Chuyển chậm thành lỗi, không sửa nguyên nhân |
| Coi mọi COLLSCAN là vấn đề | Scan có thể hợp lý |
| Tạo quá nhiều indexes | Tăng storage/write overhead |
| Ignore query shape/tenant skew | Đánh giá không đại diện |
| Không đo getMore | Bỏ phần lớn thời gian cursor |
| Tạo MongoClient mỗi request | DNS/TLS/connection churn |
| Retry vô hạn | Retry storm |
| Không đo secondary metrics | Bỏ nghẽn replication |
| Coi serverStatus counters là rates | Sai đơn vị |
| Không kiểm tra disk credits | Bỏ throttling |
| Chỉ đo một node/shard | Che hotspot |
| Thay nhiều biến cùng lúc | Không xác định root cause |
| Không rollback plan | Khó khôi phục khi tuning sai |

## 55. Bài tập: phân loại điểm nghẽn

### Bài 1 — Pool wait

HTTP p95 = 900 ms, checkout wait p95 = 750 ms, DB command p95 = 20 ms. Lớp nào đáng điều tra trước? Những metric nào xác nhận?

### Bài 2 — Query scan

Explain cho thấy nReturned=10, totalDocsExamined=800000, COLLSCAN, CPU cao. Nêu các bước thiết kế/kiểm chứng index.

### Bài 3 — Storage

P95 tăng cùng disk read latency và cache misses, nhưng CPU server 30%. Vì sao tăng CPU instances chưa chắc giúp?

### Bài 4 — Network

Application ở region A, database region B, RTT 80 ms, một request thực hiện 12 commands tuần tự. Ước lượng thành phần RTT tối thiểu trong mô hình lý tưởng và đề xuất cách giảm.

### Bài 5 — Large payload

Explain 6 ms nhưng API trả 25 MB và mất 1 giây. Đề xuất cách đo cursor/getMore, serialization và network.

## 56. Bài tập: truy vấn MongoDB

### Bài 6 — Filter + sort

Cho query find theo tenantId/status, sort createdAt giảm dần, limit 20. Đề xuất compound index và nói khi nào index không hữu ích.

### Bài 7 — Aggregation spill

Một $group/$sort có disk spill. So sánh tối ưu $match sớm, giảm cardinality, điều chỉnh index và allowDiskUse.

### Bài 8 — $lookup

Một aggregation join customers bằng customerId chậm. Kiểm tra foreign index, cardinality và explain thế nào?

### Bài 9 — Sharding

Query trên sharded collection không có shard key gây scatter-gather. Làm sao nhận biết bằng explain qua mongos?

### Bài 10 — Covered query

Một query có docsExamined=0 và keysExamined=100. Điều này gợi ý gì? Có chắc nó nhanh end-to-end không?

## 57. Bài tập: ứng dụng và driver

### Bài 11 — MongoClient lifecycle

Trong Java API, mỗi request tạo MongoClient mới. Hậu quả về connections, TLS, DNS và latency là gì? Thiết kế lifecycle phù hợp.

### Bài 12 — Command events

Viết CommandListener ghi commandName, duration và success/failure mà không log raw query chứa PII.

### Bài 13 — Pool events

Thiết kế histogram cho checkout wait, phân biệt checkout timeout với server maxTimeMS timeout.

### Bài 14 — Cursor

Một find trả 10.000 documents qua nhiều batches. Vì sao đo duration của find command đầu tiên không đủ?

### Bài 15 — GC

API p99 spikes sau deploy, heap allocations và GC pauses tăng nhưng MongoDB profiler không đổi. Cách xác nhận nguyên nhân?

### Bài 16 — N+1

Một endpoint gọi 1 find + 100 queries theo customer. Đề xuất batch query/$lookup/schema change và so round trips.

## 58. Bài tập: storage, replication và mạng

### Bài 17 — Majority write

Read p95 bình thường, majority write p95 tăng, secondary disk latency cao. Điều tra topology thế nào?

### Bài 18 — Disk IOPS

IOPS chạm provisioned limit, disk queue tăng và latency cao. Phân biệt nâng storage tier với tối ưu query pattern.

### Bài 19 — Backup contention

Latency chỉ tăng vào giờ backup. Những metrics và giải pháp an toàn cần cân nhắc?

### Bài 20 — DNS/TLS

Requests chậm sau app restart, connection created/sec tăng và TLS handshake lâu. Điều tra gì trước khi thêm index?

### Bài 21 — Container throttling

Host CPU 50% nhưng container bị CPU throttling. Vì sao app chậm dù database CPU thấp?

### Bài 22 — Packet loss

MongoDB server operation nhanh nhưng client p99 rất cao, network retransmits tăng. Cách thu thập bằng chứng theo cùng trace?

## 59. Bài tập: đo lường và quyết định

### Bài 23 — Latency budget

Một request gồm queue=10ms, logic=20ms, pool=300ms, command=40ms, serialization=30ms. Tổng khoảng bao nhiêu nếu tuần tự? Không áp dụng phép cộng này khi nào?

### Bài 24 — Little's Law

Throughput 250 requests/s, average latency 0.2s. Ước lượng số requests trung bình trong hệ thống. Điều kiện giả định?

### Bài 25 — SLO trước/sau

Sau tạo index, API p95 giảm 20% nhưng write p99 tăng 300%. Có nên chấp nhận? Cần thêm dữ liệu gì?

### Bài 26 — Causal experiment

Thiết kế thử nghiệm phân biệt query scan và network latency, bảo đảm chỉ đổi một yếu tố có rollback.

### Bài 27 — Incident timeline

App p95 tăng lúc 09:10, Atlas disk latency tăng từ 09:30. Có thể kết luận disk là nguyên nhân ban đầu không? Vì sao cần điều chỉnh time windows?

### Bài 28 — Metric mismatch

Profiler query p95 30 ms, driver command p95 200 ms nhưng là những query shapes khác nhau. Vì sao không thể kết luận network =170 ms?

### Bài 29 — Retry amplification

Traffic 300 RPS, mỗi request retry trung bình 2 lần sau lỗi. Database QPS thay đổi thế nào nếu mọi lần thử đều gửi command? Thiết kế backoff và cap.

### Bài 30 — Runbook

Soạn runbook phân loại: application queue, pool, explain, cache/disk, replication và network, gồm evidence và stop conditions.

## 60. Checklist chẩn đoán hiệu năng

### Xác định vấn đề

1. Đã xác nhận endpoint, SLO và khoảng thời gian sự cố.
2. Có p50/p95/p99, throughput và error rate.
3. Đã phân đoạn theo tenant/query/region và payload.
4. Có baseline trước sự cố hoặc deploy.
5. Có correlation ID/trace đủ nối app tới database.
6. Không log secrets/PII.

### Ứng dụng

7. Đã đo HTTP queue và thread/event-loop delay.
8. Đã đo CPU, heap, GC pause/throttling.
9. Đã đo MongoClient/pool checkout wait.
10. Đã kiểm tra connection churn và DNS/TLS.
11. Đã kiểm tra N+1, retries và timeouts.
12. Đã đo cursor/getMore và result mapping.
13. Đã đo response serialization và bytes.

### MongoDB truy vấn

14. Đã kiểm tra query shape/plan với explain.
15. Đã đối chiếu nReturned/docsExamined/keysExamined.
16. Đã kiểm tra sort, $lookup, $group, $unwind và spills.
17. Đã kiểm tra index definitions, order, partial/collation.
18. Đã cân nhắc plan cache/selectivity.
19. Đã kiểm tra query frequency, không chỉ single slow query.
20. Đã kiểm tra write concern/transactions/contention.
21. Với sharding, đã kiểm tra mongos targeting.

### Storage/cluster

22. Đã kiểm tra WiredTiger cache, eviction và data growth.
23. Đã kiểm tra disk IOPS, throughput, latency, queue/credits.
24. Đã xem checkpoint/backup/index-build timing.
25. Đã kiểm tra filesystem capacity/headroom.
26. Đã kiểm tra primary/secondary CPU, disk và replication lag.
27. Đã phân biệt per-node metrics với cluster averages.

### Network

28. Đã xác định app/database region và route.
29. Đã đo RTT, packet loss/retransmits.
30. Đã kiểm tra bandwidth và response payload.
31. Đã kiểm tra DNS, TLS, proxy, NAT và reconnect behavior.
32. Không dùng ICMP ping làm bằng chứng duy nhất.

### Khắc phục và xác nhận

33. Mỗi thay đổi có giả thuyết và expected outcome.
34. Có môi trường/giới hạn thử nghiệm được phép.
35. Có rollback plan.
36. Không đổi nhiều biến cùng lúc nếu không cần.
37. Đo trước/sau ở workload đại diện.
38. Xem cả read/write latency, throughput, errors và cost.
39. Ghi root cause với bằng chứng và giới hạn kết luận.
40. Đặt monitoring/alert để phát hiện tái diễn.

## 61. Mẫu biên bản điều tra

~~~yaml
incidentId: PERF-2026-11-14-01
affectedEndpoint: GET /orders
environment: example-staging
startUtc: "2026-11-14T09:10:00Z"
symptom:
  apiP95Ms: 850
  baselineApiP95Ms: 120
  qps: 500
observations:
  poolCheckoutP95Ms: 600
  driverCommandP95Ms: 60
  mongoQueryPlan: IXSCAN
  docsExamined: 25
  serverCpuPct: 40
  diskLatencyMs: 3
  networkRttMs: 5
hypothesis:
  description: "App pool saturated by too many concurrent reads"
  confidence: "needs verification"
experiment:
  change: "Reduce per-request N+1 operations on staging"
  successMetric: "pool checkout wait and API p95 drop"
rollback: "Restore old request path"
result: "PENDING"
owner: "service-team"
~~~

Số liệu ví dụ không mô tả một môi trường thực. Biên bản tốt phân biệt **quan sát**, **giả thuyết**, **thử nghiệm** và **kết luận**.

## 62. Kết luận

Chẩn đoán MongoDB chậm không nên bắt đầu bằng câu hỏi “tạo index nào?” mà bằng câu hỏi **“thời gian thực sự được tiêu thụ ở đâu, dưới tải nào, và bằng chứng nào nối nguyên nhân với triệu chứng?”**.

- Nếu HTTP p95 cao nhưng MongoDB command nhanh, hãy xem application queue, connection pool, N+1, cursor, GC và serialization.
- Nếu server query time cao và explain cho thấy quét quá nhiều, hãy đánh giá filter/index/sort/aggregation.
- Nếu latency tăng cùng disk wait/cache misses, kiểm tra WiredTiger working set, storage IOPS/throughput, checkpoint và background workload.
- Nếu driver time lớn hơn server time ở cùng request, xem network RTT, connection establishment, result payload, getMore và khác biệt boundaries đo.
- Nếu writes chậm, đừng bỏ qua replication, write concern, transaction conflicts và secondary disk/network.
- Nếu sharded cluster có scatter-gather hoặc hotspot, kiểm tra routing/shard key trước khi chỉ nâng cấu hình.

**Một điểm nghẽn được xác định khi có đủ bằng chứng về queue, saturation hoặc lượng công việc quá lớn tại một lớp; một biện pháp tối ưu chỉ được công nhận khi cải thiện SLO thực tế mà không làm suy giảm không chấp nhận được về correctness, durability hay lớp tài nguyên khác.**

## Tài liệu tham khảo

- [MongoDB Manual — Analyze Query Performance](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — db.currentOp](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — WiredTiger](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Atlas — Monitor Cluster Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/)
