# Giai đoạn làm nóng, bộ nhớ đệm nóng/lạnh và trạng thái tác vụ nền

Một nhóm đo tải API đọc sản phẩm dùng Java, Redis và MongoDB. Trong ba phút đầu, p99 khoảng **650 ms**; mười phút sau, cùng chương trình chỉ còn **45 ms**. Nhóm dùng kết quả 45 ms để chứng minh hệ thống đủ nhanh. Nhưng khi triển khai thật, nhiều instances khởi động cùng lúc, Redis thiếu dữ liệu, database bắt đầu compaction/backup, và p99 lại tăng vượt mục tiêu.

Hai kết quả trên đều có thể chính xác. Chúng mô tả **hai trạng thái của cùng một hệ thống**. Sai lầm là công bố một con số mà không nói cache đã nóng hay chưa, client và query engine đã warm-up chưa, background tasks nào đang chạy, và kết quả đó có đại diện cho một thời điểm vận hành bình thường hay sau sự cố hay không.

Khi đo tải NoSQL, ít nhất cần phân biệt:

1. **Giai đoạn làm nóng (warm-up):** những phút hoặc chu kỳ đầu khi code, connections, query metadata và cache còn đang đạt trạng thái ổn định.
2. **Bộ nhớ đệm nóng/lạnh (warm/cold caches):** working set nằm trong tầng nhớ nhanh tới mức nào, từ L1 của ứng dụng qua Redis đến database buffer cache và OS page cache.
3. **Trạng thái tác vụ nền (background work):** flush, compaction, checkpoint, TTL cleanup, backup, repair, replication catch-up, reindex hoặc các job đồng bộ đang cạnh tranh tài nguyên ra sao.

Bài học thuộc chương **Hiệu năng và đo tải**, module **Database No SQL**. Mục tiêu là biết thiết kế benchmark có thể tái lập, nhận diện yếu tố làm số liệu đẹp giả, phân biệt cold-start performance và steady-state throughput, đo sustained capacity khi có background maintenance, đồng thời đưa kết quả vào capacity plan, SLO và runbook production. Các số trong ví dụ là **giả định minh họa**, không phải benchmark thực tế của một nhà cung cấp.

## 1. Một con số benchmark chỉ đúng trong ngữ cảnh

Phát biểu “database đạt 80.000 req/s với p99 20 ms” chưa đủ để ra quyết định nếu không biết:

- Workload là point GET, range query, aggregation hay INSERT/UPDATE/DELETE?
- Dataset có bao nhiêu records, kích thước, indexes và retention?
- Bao nhiêu keys thật sự được truy cập trong cửa sổ đo?
- Read/write mix và phân bố hot keys/tenants?
- JVM, driver connection pool và query plans đã nóng chưa?
- Redis/L1 và database buffer/OS page cache đã chứa bao nhiêu dữ liệu?
- Flush, compaction, backup, repair hoặc shard migration có hoạt động không?
- Client gửi bao nhiêu requests, hoàn tất bao nhiêu và timeout bao nhiêu?
- Latency đo ở client hay chỉ thời gian database xử lý?
- Durability, consistency, replication và topology đã cấu hình thế nào?

**Một benchmark tốt phải đi kèm mô tả điều kiện đã được đo, không chỉ biểu đồ p99 đẹp nhất.**

## 2. Ma trận ba chiều cần gắn nhãn

| Chiều | Các trạng thái | Điều cần nhận biết |
|---|---|---|
| Warm-up | Starting, warming, steady, recovering | Code paths/connections/buffers còn biến đổi mạnh không? |
| Cache | Cold, partially warm, warm, thrashing | Mức cache hit và working set tương quan thế nào? |
| Background tasks | Idle, normal, elevated, maintenance, recovery | Có job nào đang dùng CPU, memory, disk, network? |

Hai tình huống:

~~~yaml
scenario: steady-baseline
warmup: steady
applicationCache: warm
redisCache: warm
databaseCache: warm
background:
  compaction: normal
  backup: inactive
~~~

~~~yaml
scenario: post-failover
warmup: recovering
applicationCache: partially-warm
redisCache: cold
databaseCache: cold
background:
  compaction: elevated
  replicationCatchup: active
~~~

Chúng không thể đại diện cho nhau chỉ vì có cùng HTTP endpoint và cùng số nhân viên gửi tải.

## 3. Nhiều tầng nhớ nhanh trên một đường đọc

~~~mermaid
flowchart TD
    U["Load generator"] --> A["Java API và driver pool"]
    A --> L1["L1 application cache"]
    A --> R["Redis shared cache"]
    A --> D["NoSQL database"]
    D --> Q["Query plan / metadata"]
    D --> B["DB buffer hoặc block cache"]
    B --> OS["OS page cache"]
    OS --> SSD["Physical disk"]
    D --> BG["Flush / compaction / backup / repair"]
    BG --> SSD
~~~

Một GET trúng L1 không tạo query ở Redis hay database. Một miss Redis nhưng hit database buffer cache rẻ hơn đọc SSD. Một query index scan lớn vẫn tốn CPU dù tất cả pages đã nóng. Vì vậy **API throughput, Redis throughput và database throughput là các phép đo khác nhau**.

## 4. Warm-up là gì?

Warm-up là quá trình hệ thống chuyển từ trạng thái mới khởi chạy, mới triển khai hoặc mới nhận workload sang trạng thái tương đối ổn định.

Những việc có thể xảy ra:

~~~text
Khởi tạo class và serializer.
JVM JIT compile các hot methods.
Driver thiết lập DNS/TLS/authentication.
Pool mở thêm connections.
Query engine load schema/index metadata.
Query planner tạo hoặc tái sử dụng execution plans.
Application/Redis/database nạp hot keys/pages.
OS page cache nạp file blocks.
Background recovery hoặc flush hoàn tất một số pha.
~~~

**Không có thời gian warm-up cố định đúng cho mọi workload.** Một dataset nhỏ có thể ổn định sau vài chục giây; dataset lớn hơn cache có thể mãi duy trì một miss ratio đáng kể nhưng vẫn ở trạng thái steady.

## 5. Cold-start và steady-state là hai câu hỏi khác nhau

**Steady-state benchmark** hỏi:

> Sau khi ứng dụng chạy bình thường, hệ xử lý được bao nhiêu requests/giây với latency và error rate trong SLO?

Có thể chạy warm-up trước khi tính cửa sổ đo chính, nhưng phải nêu cách kết thúc warm-up.

**Cold-start/recovery benchmark** hỏi:

> Sau restart, deploy hoặc failover, mất bao lâu hệ đạt SLO trở lại và bao nhiêu requests bị chậm hoặc lỗi?

Ở đây không được loại bỏ vài phút đầu vì đó chính là dữ liệu cần đo.

Hệ thống production cần được hiểu ở **cả hai trạng thái**, không chỉ trạng thái có cache nóng.

## 6. Tách cold application khỏi cold database

**Chỉ restart Java API:**

~~~text
JVM/JIT: cold
Application L1 cache: cold
Connection pool: cold
Redis: warm
Database cache: warm
OS page cache tại database host: warm
~~~

**Thay một database node:**

~~~text
JVM/JIT: warm
Redis: warm hoặc một phần
Database buffer cache ở node mới: cold
OS page cache ở node mới: cold hoặc partially warm
Replication catch-up/recovery: có thể active
~~~

Restart ứng dụng không làm lạnh dữ liệu trong Redis; restart database process cũng không nhất thiết làm lạnh OS page cache. **Từ “cold” phải chỉ rõ tầng được kiểm soát.**

## 7. Java và JVM warm-up

Những yếu tố thường ảnh hưởng:

- Class loading/initialization.
- Tiered JIT compilation, optimization và deoptimization.
- JSON/driver codec initialization.
- Thread pools và networking event loops.
- Heap allocation profile, garbage collection.
- Reflection/framework metadata.
- Security/TLS provider initialization.

Một GET đầu có thể bao gồm:

~~~text
Initialize classes.
Create client connection.
Authenticate.
Serialize query.
Send database request.
Deserialize response.
~~~

GET sau có thể chỉ thực hiện phần công việc thường xuyên. Nếu benchmark API end-to-end, cold JVM overhead là chi phí user có thể gặp. Nếu mục tiêu so query engines, phải đo riêng client latency và database execution time để không quy JIT cho engine.

## 8. Microbenchmark Java không thay load test toàn hệ

Microbenchmark đo ví dụ:

~~~text
Serialize Product object.
Parse một key.
Lookup một in-memory map.
~~~

Framework như JMH có thể giúp tránh bẫy JIT/microbenchmark. Nhưng nó không tự đo:

~~~text
HTTP -> auth -> Java service -> Redis
     -> MongoDB -> network -> JSON response.
~~~

| Cấp đo | Mục đích |
|---|---|
| Microbenchmark | Chi phí một hàm/codec |
| Component | Driver + query hoặc cache command |
| Service | API có business logic/caches |
| End-to-end | Trải nghiệm request qua toàn pipeline |

Không suy throughput production của NoSQL từ microbenchmark không có network, data distribution và background work.

## 9. Connection pool cũng cần làm nóng

Giả sử pool mở dần:

~~~text
00:00  2 connections, nhiều requests chờ pool.
00:10  20 connections, TLS handshake tăng.
00:20  60 connections, queue giảm.
00:30  Pool tương đối ổn định.
~~~

Theo dõi **active/idle/pending connections, acquire timeout, connection creation latency, TLS/auth failures và in-flight requests**.

Tăng minimum pool size có thể giảm cold latency nhưng tạo startup burst và dùng thêm tài nguyên ở database. Không mặc định càng nhiều connections càng tốt.

## 10. Query plan cache khác data cache

Trên một query path có:

~~~text
Parse query.
Choose execution plan.
Locate index structures.
Read data pages.
Apply filters/sort.
Build response.
~~~

Một engine/driver có thể cache prepared statements, metadata hoặc query plans theo semantics riêng. Data cache lại chứa pages/blocks. OS cache còn có thể chứa file blocks dù database cache miss.

Khi query chậm lần đầu, cần đo **planning time, query plan, physical reads, driver overhead** trước khi kết luận.

**Plan cache nóng không đồng nghĩa mọi data pages đã nằm trong RAM.**

## 11. Cold, partially warm, warm và thrashing

| Trạng thái | Mô tả | Dấu hiệu |
|---|---|---|
| Cold | Phần lớn working set chưa có trong cache đang xét | Misses/physical reads cao |
| Partially warm | Một số keys/pages đã nạp | Hit ratio tăng dần |
| Warm | Workload và cache đạt trạng thái tương đối ổn định | Miss rate ổn định tương đối |
| Thrashing | Working set quá lớn hoặc churn liên tục | Eviction/miss cao kéo dài |

Cache có thể nóng cho GET theo key nhưng lạnh cho range query mới. Một steady-state miss rate 30% vẫn có thể bình thường nếu working set lớn hơn cache; **warm không có nghĩa hit ratio 100%**.

## 12. Working set mới quyết định mức hưởng lợi cache

Giả sử:

~~~text
Database: 100 triệu products.
80% requests: vào 100.000 hot products.
20% requests: phân tán tới phần còn lại.
~~~

Cache đủ chứa hot products có thể tiết kiệm nhiều source reads.

Cùng số requests nhưng dùng **uniform random** trên toàn 100 triệu records sẽ có hit ratio khác. Dùng **100 keys lặp lại** làm cache cực kỳ nóng dù production truy cập nhiều keys hơn.

Workload manifest nên có:

- Số distinct keys và phân bố phổ biến.
- Hot key/tenant skew và temporal locality.
- Kích thước object, index cardinality.
- Query shape/selectivity.
- Read/write mix và update churn.

**Một benchmark không mô tả phân phối keys khó đại diện cho cache behavior production.**

## 13. Repeated-key benchmark thường chỉ đo cache

~~~text
Tạo 100 product documents.
Lặp GET cùng 100 keys trong 20 phút.
Kết quả API: 100.000 req/s.
~~~

Nếu L1/Redis hit gần 100%, source DB có thể chỉ nhận vài operations/giây.

Khi đánh giá engine:

1. Bảo đảm requests thực sự đi tới engine.
2. Đếm database operations thực.
3. Chọn dataset/working set đại diện.
4. Mô tả caches nào bật, caches nào bypass.
5. Báo kết quả đúng theo phạm vi.

Kết quả API-cache-hit vẫn có giá trị, nhưng không được đổi nhãn thành “database chịu 100.000 GET/s”.

## 14. Database buffer và OS page cache là hai tầng

~~~text
Database query
  -> DB buffer / block cache
     -> OS page cache
        -> SSD / physical storage
~~~

Một miss ở DB cache có thể hit OS page cache, không phải physical I/O. Restart database process không chắc làm sạch OS cache; container restart cũng không bảo đảm page cache của host mất.

Các metric:

- DB cache hit/miss, pages loaded/evicted.
- Disk read bytes, IOPS, latency.
- Memory pressure/page faults.
- File-system cache indicators nếu có.
- Query execution time.

**Đừng chỉ nhìn DB cache miss ratio rồi mặc định toàn bộ misses đều ra disk vật lý.**

## 15. Không tự flush cache production để đo cold

Xóa cache hoặc restart dữ liệu trên production chỉ để tạo phép đo có thể:

- Làm đồng loạt các ứng dụng khác chậm.
- Kích hoạt disk read storm.
- Gây cache miss surge, timeout/retry.
- Mất SLO của người dùng thật.

Hãy dùng **môi trường cô lập**, cache namespace test riêng, dataset mới hoặc node/volume benchmark phù hợp.

Lưu ý dataset mới có thể đồng thời thay đổi disk layout, index state và fragmentation; không coi nó là phép điều khiển duy nhất một biến nếu điều đó chưa được chứng minh.

## 16. Cache warmth khác dữ liệu đúng và mới

Ví dụ:

~~~text
Redis cache hit ratio: 99%.
Cached price version: 18.
Authoritative price version: 20.
~~~

Cache đang rất nóng nhưng chứa bản cũ.

- **Warmth:** có bao nhiêu dữ liệu nằm ở đường nhớ nhanh?
- **Freshness:** bản lưu phản ánh thay đổi nguồn mới tới đâu?
- **Correctness:** có đủ điều kiện dùng cho quyết định nghiệp vụ không?

Khi đo endpoint liên quan giá, tồn kho, quyền truy cập, cần có **version/freshness/invariant metrics**, không chỉ cache hit ratio và p99.

## 17. Khi nào warm-up kết thúc?

Không có quy tắc “chạy chính xác 5 phút” cho mọi hệ. Cần tiêu chí quan sát:

- Completed throughput không còn tăng dần do startup.
- p95/p99 không còn xu hướng giảm mạnh vì cache fill.
- Hit/miss ratio tương đối ổn định.
- Driver pool đạt trạng thái bình thường.
- Physical reads không tiếp tục giảm mạnh.
- JVM JIT/class load startup activity bớt đột biến.
- Background recovery đã qua những pha không muốn gộp vào steady.
- Error rate và load generator rate được đo đầy đủ.

**Ổn định trong workload này** không đồng nghĩa engine sẽ không bao giờ chạy compaction hoặc GC nữa.

## 18. Ví dụ timeline warm-up

Các số giả định:

| Phút | Completed req/s | p99 | Redis hit | Nhận định |
|---|---:|---:|---:|---|
| 1 | 3.200 | 650 ms | 12% | Cold |
| 2 | 5.100 | 420 ms | 34% | Warming |
| 3 | 6.400 | 230 ms | 58% | Warming |
| 4 | 7.100 | 120 ms | 75% | Partially warm |
| 5 | 7.400 | 70 ms | 86% | Near steady |
| 6 | 7.430 | 63 ms | 88% | Near steady |
| 7 | 7.420 | 64 ms | 88% | Near steady |

Nếu chỉ lấy phút 6–7 sẽ bỏ cold startup. Nếu gộp cả bảy phút thành một p99 tổng, sẽ mất thông tin **bao lâu hệ vượt SLO**.

Hãy lưu histogram và time series theo cửa sổ, không chỉ một percentile ở cuối.

## 19. Prewarm có thể gây bão queries

~~~text
100 API instances mới.
Mỗi instance prefetch 10.000 hot keys.
Tổng có thể có 1.000.000 source reads gần đồng thời.
~~~

Prefetch quá mạnh có thể làm nguồn NoSQL chậm ngay lúc cần phục vụ traffic thật.

Giải pháp:

- Staggered startup/rolling deployment.
- Throttled prewarm.
- Ưu tiên hot subset đúng.
- Bounded concurrency.
- Singleflight/request coalescing.
- Traffic ramp sau readiness.
- Source load protection và load shedding.

Prewarm **phải giảm cold-start impact, không tạo một cold-start storm mới**.

## 20. Liveness không đồng nghĩa readiness

~~~text
Process running: yes.
Connection pool: đang mở.
Critical dependency: chưa ready.
Index metadata: đang nạp.
Hot cache subset: chưa có.
~~~

Liveness xác định process có sống hay không. Readiness xác định đã sẵn sàng nhận traffic ở phạm vi định nghĩa.

Không đòi cache phải 100% nóng nếu điều đó bất khả thi; thay vào đó giữ capacity headroom và tăng traffic theo pha. Không cấu hình liveness restart liên tục một instance đang warm-up hợp lệ.

## 21. Background tasks của NoSQL

| Tác vụ | Mục đích | Tài nguyên |
|---|---|---|
| Memtable flush | Đẩy memory writes ra files | Disk, CPU |
| Compaction | Merge/rewrite old versions/files | Disk read/write, CPU |
| Checkpoint | Ghi trạng thái bền | Disk I/O |
| Index build/reindex | Tạo cấu trúc truy cập | CPU, RAM, disk |
| TTL expiration/cleanup | Xử lý data hết hạn | CPU, disk/memory |
| Replication catch-up | Đồng bộ replica chậm | Network, disk |
| Repair/anti-entropy | Đối soát replicas | Network, disk, CPU |
| Backup/snapshot | Tạo bản phục hồi | Disk read, network |
| Shard movement | Chuyển partition/shard | Network, disk |
| CDC/outbox relay | Đẩy change stream | CPU, network, source reads |
| Cache warming | Nạp hot data | Source QPS, memory |

Nếu benchmark không hề chạy cùng các tác vụ production thường xuyên phải làm, nó có thể đo **best-case** chứ không đo điều kiện thông thường.

## 22. Flush và compaction trong LSM

Nhiều NoSQL/storage engines sử dụng LSM hoặc biến thể:

~~~text
Write -> WAL + memtable.
Memtable flush -> SSTable files.
Compaction -> merge/rewrite files.
~~~

Compaction có thể tiêu thụ CPU, đọc/ghi nhiều bytes, tạm tăng disk occupancy và cạnh tranh I/O với foreground queries.

Khi compaction không theo kịp write rate, backlog tăng, có thể xuất hiện write stalls/backpressure.

**Một burst write rất nhanh trong năm phút chưa chứng minh sustained write capacity** nếu những công việc lưu trữ thực sự chưa hoàn thành.

## 23. Compaction debt

Timeline giả định:

~~~text
0–5 phút: ghi nhanh vào buffers.
5–15 phút: flush tạo nhiều files.
15–30 phút: pending compactions tăng.
30–45 phút: disk bão hòa, write stalls.
~~~

Cần quan sát:

- Pending compaction tasks/bytes.
- Flush queue/memtable pressure.
- SSTable hoặc L0 file counts tùy engine.
- Disk throughput/utilization/latency.
- Write stalls, throttles, rejections.
- Free disk và temporary headroom.

**Sustainable throughput** là mức có thể duy trì mà không tạo backlog tăng không giới hạn và vẫn thỏa SLO, khác với peak ngắn hạn.

## 24. Cassandra: cache, tombstones, repair

Cassandra có những yếu tố cần chú ý:

- Memtables, flush, SSTables, compaction strategies.
- Key cache/row cache tùy config.
- OS page cache.
- TTL/tombstones và số entries phải quét.
- Repair, streaming và bootstrap.
- Replica consistency và node load distribution.

Một partition có 100.000 expired events và vài events còn live có thể vẫn gây query scan overhead dù pages ở trong cache.

Do đó theo dõi **per-query SSTables/tombstones, per-node latency, compaction/repair backlog, disk I/O và partition sizes**.

Không giảm tham số an toàn tombstone GC hay tắt repair để benchmark đẹp hơn.

## 25. RocksDB và storage engines LSM

Các thành phần thường có:

~~~text
Memtable.
WAL.
SSTables.
Block cache.
Bloom filters/index blocks.
Background flush.
Compaction queue.
Write stall.
~~~

Một GET có thể hit memtable/block cache hoặc phải đọc SSTables. Cache nóng chưa chắc cải thiện nếu có nhiều SSTables hoặc compaction đang tạo áp lực disk.

Khi đo, xem **block cache hit/miss, pending flush/compaction, write stalls và disk reads/writes** theo metrics của phiên bản sử dụng.

## 26. MongoDB và WiredTiger

Với MongoDB deployment dùng WiredTiger:

- Engine có cache và eviction behavior.
- Data/index pages được nạp theo access pattern.
- OS filesystem cache có thể bổ sung hiệu ứng.
- Dirty pages/checkpoints tạo background I/O.
- Index builds, replication và backup có thể tranh tài nguyên.

Nếu p99 tăng, kiểm đồng thời:

~~~text
WiredTiger cache occupancy/eviction.
Physical reads và disk latency.
Query execution plan/keys examined.
Checkpoint/index activity.
Replica state/lag.
Driver pool pending.
~~~

Không kết luận “MongoDB cold” từ một query chậm nếu plan vừa đổi hoặc đang có index build.

## 27. Redis cold trong cache-aside

Redis là in-memory data system. Với cache-aside, cold thường có nghĩa hot keys chưa được nạp:

~~~text
Redis miss -> Java API hỏi MongoDB.
MongoDB read -> cache fill -> Redis hit lần sau.
~~~

Các biến quan trọng:

- Redis persistence/restart mode.
- Key population và TTL/eviction.
- Memory pressure.
- Hot keys.
- TLS/connection pool/client CPU.
- Replica sync/failover.

Redis restart có thể phục hồi dataset theo persistence cấu hình, nên **không phải mọi restart đều làm cache rỗng**.

Phân biệt Redis GET hit benchmark với API full-path cache miss benchmark.

## 28. Cache stampede

~~~text
10:00 Redis rỗng sau restart.
10:01 20.000 requests/s cùng hỏi hot products.
10:01 Nhiều misses -> MongoDB chịu đột biến reads.
10:01 Queues/timeouts/retries tăng.
~~~

Có thể dùng:

- Singleflight/request coalescing.
- Throttled prewarm.
- TTL jitter.
- Bounded fallback/rate limiting.
- Circuit breaker và load shedding.
- Stale-while-revalidate nếu business cho phép.

Không dùng cache hit ratio 99% lúc nóng làm bằng chứng source chịu được cold miss surge.

## 29. TTL cleanup và logical expiration

| Hệ | Đặc điểm |
|---|---|
| Redis | Active/lazy key expiration, eviction riêng |
| MongoDB | TTL index cleanup qua background mechanism |
| DynamoDB | TTL deletion bất đồng bộ theo dịch vụ |
| Cassandra | TTL/tombstones, cleanup vật lý liên quan compaction |

Một đợt records cùng hết hạn có thể làm resource profile khác lúc insert. TTL hết hạn logic không nhất thiết bytes được giải phóng ngay.

**Không nhầm công việc dọn data với cache warming** và không giả định mọi hệ TTL đều có cùng thời điểm xóa.

## 30. Backup, reindex, repair và replication catch-up

Một snapshot có thể đọc nhiều bytes và truyền qua network. Reindex có thể scan source, tạo index mới, merge segments và catch up live events. Repair có thể streaming giữa replicas.

Chúng có thể cạnh tranh:

- Disk I/O/IOPS/latency.
- Network bandwidth.
- CPU, memory.
- Cache locality.
- Background task queues.

Benchmark nên có trạng thái **maintenance overlap** để xác định hệ có giữ được SLO khi các công việc thật sự diễn ra hay không.

Không phải mọi tác vụ đều làm giảm hiệu năng cùng mức; cần đo thực tế với topology/engine đang dùng.

## 31. Tail latency thường nhạy với background work

Dữ liệu giả định:

| Trạng thái | Mean | p95 | p99 |
|---|---:|---:|---:|
| Warm, background normal | 12 ms | 25 ms | 45 ms |
| Warm, compaction elevated | 18 ms | 55 ms | 220 ms |

Mean tăng 50%, nhưng p99 tăng gần năm lần. Điều này có thể do những khoảng I/O queue/stall ngắn.

Nên đo p95/p99/p99.9 theo SLO và sample count, đặt cạnh disk latency/background job markers. Một max observed từ sample nhỏ không đại diện chính xác cho tail distribution.

## 32. Offered QPS khác completed throughput

~~~text
Load generator gửi: 50.000 req/s.
Server hoàn tất thành công: 35.000 req/s.
Phần còn lại: error, timeout hoặc pending.
~~~

Không được báo server “đạt 50.000 requests/giây”.

Ghi riêng:

- Offered arrival rate thực.
- Completed successful QPS.
- Errors, timeouts, status codes.
- In-flight, queue size/wait.
- Client scheduling delay.
- Latency của success và failed outcomes.

Một hệ backlog tăng không giới hạn chưa đạt sustained capacity dù chưa bị lỗi ngay.

## 33. Closed-loop và open-loop load models

**Closed-loop:**

~~~text
Gửi request.
Chờ response.
Gửi request tiếp.
~~~

Khi server chậm, client tự giảm tốc độ gửi. Có thể phù hợp một số interaction models nhưng che overload khi mục tiêu là external arrivals cố định.

**Open-loop:**

~~~text
Phát request theo arrival schedule đã định.
Không tự giảm arrivals chỉ vì response chậm,
trong giới hạn công cụ và tài nguyên.
~~~

Open-loop cần đủ load-generator capacity và đo actual offered QPS, in-flight, queue. Không có loại nào mặc nhiên đúng mọi tình huống: **chọn theo câu hỏi cần đo**.

## 34. Coordinated omission

Server pause 2 giây vì I/O. Closed-loop client đang chờ một response nên không gửi thêm requests trong khoảng pause. Nhưng người dùng mới thực tế có thể vẫn đến.

Nếu histogram chỉ chứa requests được gửi, nó có thể bỏ sót độ trễ của các arrivals lẽ ra xuất hiện. Đây là một dạng **coordinated omission**.

Cách giảm sai lệch:

- Dùng mô hình arrival đại diện.
- Đo scheduled arrival, actual send và response time khi phù hợp.
- Dùng histogram/tool có hỗ trợ correction đúng semantics cần đo.
- Không tùy tiện tự cộng độ trễ “tưởng tượng”.

Phải công bố phép đo có hay không tính request scheduling/queue delay.

## 35. Định nghĩa độ trễ tại client

Có ba mốc:

~~~text
t_scheduledArrival
t_actualSend
t_responseReceived
~~~

Trong mô hình user arrivals:

\[
L_{\mathrm{observed}}
=t_{\mathrm{response}}-t_{\mathrm{scheduledArrival}}
\]

Nếu chỉ đo từ lúc gửi:

\[
L_{\mathrm{inFlight}}
=t_{\mathrm{response}}-t_{\mathrm{actualSend}}
\]

Hai phép đo phục vụ các câu hỏi khác nhau. Chúng có thể lệch lớn khi load generator hoặc queue quá tải.

## 36. Little's Law để sanity-check

Ở trạng thái ổn định, với cùng ranh giới:

\[
L=\lambda W
\]

Trong đó \(L\) là lượng requests trung bình trong hệ, \(\lambda\) là throughput trung bình và \(W\) là thời gian trung bình.

Nếu:

~~~text
Throughput = 2.000 req/s.
Mean latency = 0,05 s.
~~~

thì:

\[
L\approx 2.000\times0{,}05=100
\]

Tức có khoảng 100 requests in-flight trung bình theo phạm vi mô hình. Nếu telemetry chỉ có 2, phải kiểm scope, time windows và cách thu thập.

Little's Law giúp kiểm tra tính nhất quán, **không tự chứng minh SLO hay hiệu năng của database**.

## 37. SLO-compliant capacity thay vì peak QPS

Một ví dụ:

| Offered QPS | Completed success QPS | p99 | Error rate |
|---|---:|---:|---:|
| 3.000 | 3.000 | 60 ms | 0% |
| 5.000 | 4.995 | 110 ms | 0,1% |
| 7.000 | 6.930 | 290 ms | 1% |
| 9.000 | 7.200 | 1.100 ms | 20% |

Nếu SLO p99 không quá 200 ms và error rate có ngưỡng thấp, **peak completed 7.200 req/s không phải năng lực được phép thiết kế**.

Cần tìm mức tải cao nhất thỏa đồng thời latency, errors, durability/correctness và các ràng buộc liên quan.

## 38. Percentile và cửa sổ thời gian

Cần biết:

- p99 từ sample nào, có đủ số lượng không?
- Histograms có resolution đủ?
- Errors/timeouts được thống kê ra sao?
- Có gộp endpoints và payload sizes khác nhau?
- Có lặp test và xem variability?

Không lấy trung bình p99 của các phút rồi nói đó là p99 toàn run. Muốn percentile chung phải merge raw samples hoặc compatible histograms với weights thích hợp.

Một p99 tính trên toàn 30 phút cũng có thể che **một phút spike**; giữ per-window plots và markers.

## 39. Mixed workload quan trọng

Production có thể:

~~~text
80% point GET.
10% range queries.
10% writes.
~~~

Writes có thể:

- Invalidate cache.
- Tạo WAL/flush/compaction.
- Thay đổi index pages.
- Gây replication lag.
- Tạo tombstones/TTL cleanup.

GET-only warm benchmark có thể đánh giá quá lạc quan so với workload có writes và maintenance. Nếu có batch writes theo giờ, cần thử overlap với reads.

## 40. Hot partitions không được sửa bằng cache warm

Nếu 70% writes đi vào cùng một tenant/partition, bottleneck có thể nằm ở shard leader/coordinator, transaction contention hoặc conditional update retries.

Ngay cả khi Redis hit ratio cao trên reads, writes vẫn phải vào nguồn có thẩm quyền.

Nên đo **per-node/per-partition QPS, CPU, queue, latency, retry/conflict rates** thay vì chỉ xem trung bình toàn cluster.

## 41. Load generator cũng có thể cold hoặc quá tải

Load generator có thể:

- Khởi động JVM/threads.
- Initialize driver, TLS, connections.
- Load key distributions/test fixture.
- Bị CPU/network bottleneck.
- Không gửi kịp schedule.

Ghi **planned offered QPS, actual attempted QPS, completed QPS, generator CPU/network và scheduling lag**. Nếu generator đã bão hòa, không được quy trần throughput cho NoSQL server.

## 42. Dữ liệu benchmark phải đại diện

Dataset 100.000 records đều 1 KB rất khác production 20 triệu records, p99 size 20 KB, nhiều tenants và hot keys.

Chọn synthetic/anonymized data giữ:

- Kích thước object và distribution.
- Index cardinality/selectivity.
- Tenant/partition skew.
- Query shape và pagination.
- TTL/delete churn.
- Read/write mix.

Không copy PII production vào môi trường test thiếu quyền bảo vệ.

## 43. Memory pressure và cache thrashing

Nên thử ít nhất:

~~~text
Working set nhỏ hơn cache.
Working set gần bằng cache.
Working set lớn hơn cache.
~~~

Khi memory pressure tăng, có thể xảy ra evictions, OS page cache thu hẹp, GC nhiều hơn, OOM/throttling và compaction thiếu buffers.

Cache đã warm nhưng working set quá lớn vẫn có miss/eviction rates cao.

## 44. Ma trận kịch bản

| Mã | App/JVM | Cache | Background | Mục đích |
|---|---|---|---|---|
| S1 | Warm | Warm | Normal | Baseline thường ngày |
| S2 | Cold | Warm | Normal | Rolling API restart |
| S3 | Warm | Cold Redis | Normal | Cache loss |
| S4 | Warm | Warm | Elevated compaction | Sustained writes |
| S5 | Cold | Cold | Recovery | Failover worst-case có cơ sở |
| S6 | Warm | Warm | Backup/reindex | Maintenance overlap |

Không nhất thiết chạy toàn bộ tổ hợp nếu quá đắt; ưu tiên trạng thái production có xác suất/tác động cao. Mỗi trạng thái phải có cách tạo và metrics xác nhận.

## 45. Manifest cho một benchmark

~~~yaml
benchmarkId: nosql-read-2026-11
question: "Cold Redis cache effect on product API"
workload:
  pointReadPercent: 80
  rangeReadPercent: 10
  writePercent: 10
  offeredQps: 8000
  keyDistribution: "production-inspired skew"
  distinctKeys: 2000000
dataset:
  records: 20000000
  sampleVersion: "synthetic-v4"
topology:
  appInstances: 8
  redisNodes: 3
  databaseNodes: 3
warmState:
  api: warm
  redis: cold
  database: warm
  osPageCache: not-reset
background:
  compaction: observed-normal
  backup: inactive
measurement:
  warmup: "observed stabilization criteria"
  durationMinutes: 20
  trials: 3
~~~

Các trường mang tính minh họa. Kèm engine/driver versions, replication/consistency, load script, metrics và phương pháp xác nhận trạng thái.

## 46. Tạo cold/warm state có kiểm soát

**Cold application:** restart API trong môi trường test, giữ Redis và DB nguyên.

**Cold Redis:** cache namespace mới chưa nạp hoặc cache instance cô lập, đo source miss surge.

**Cold database pages:** dùng node/volume/dataset chưa truy cập trong môi trường an toàn; đo physical I/O.

**Warm database:** chạy workload đại diện và theo dõi hit/miss, disk reads, latency tới khi ổn định tương đối.

Không cho rằng dataset mới chỉ thay cache; nó cũng có thể thay fragmentation, index layout, replica state.

## 47. Thứ tự A/B có thể sai lệch

Nếu luôn A chạy trước B, B có thể hưởng JVM/cache nóng hơn; hoặc chịu compaction debt do A tạo.

Nên:

- Lặp run nhiều lần.
- Đảo thứ tự hoặc randomized blocks khi hợp lý.
- Giữ workload/config tương đương.
- Gắn nhãn cache/background state.
- So phân bố và confidence, không cherry-pick best run.

Nếu state không thể reset hoàn toàn, hãy công bố khác biệt và kết luận giới hạn.

## 48. Benchmark đủ dài cho chu kỳ nền

Test 30 giây có thể chưa thấy:

- Periodic checkpoint.
- GC/heap aging.
- Flush/compaction debt.
- TTL cleanup.
- Backup/snapshot.
- Repair/rebalance.

Nhưng chạy một giờ cũng không giúp gì nếu workload không tạo điều kiện cho những job muốn đo.

Nên chia:

1. Correctness smoke test.
2. Cold-start phase.
3. Warm-up until stabilization.
4. Steady-state window.
5. Sustained/soak test.
6. Maintenance/recovery scenario.

Độ dài phải dựa trên engine/workload và các chu kỳ cần quan sát.

## 49. Đừng cắt bỏ pha xấu khỏi báo cáo

~~~text
0–3 phút: cold.
3–8 phút: warming.
8–28 phút: steady.
28–32 phút: compaction spike.
32–37 phút: recovery.
~~~

Có thể báo p99 steady riêng cho phút 8–28, nhưng phải giữ **cold p99, time-to-SLO, background spike, errors, recovery duration và complete time-series**.

Không dùng một percentile sau warm-up làm cam kết cho toàn bộ vòng đời.

## 50. Gắn task timeline vào biểu đồ

Ví dụ giả định:

~~~text
12:00  p99=45ms, Redis hit=95%, disk util=35%.
12:05  Cache invalidation, hit=40%.
12:05  Source reads tăng, p99=220ms.
12:06  Compaction active, disk util=95%.
12:06  p99=650ms.
12:08  Cache hit=90%, compaction active, p99=180ms.
12:10  Compaction kết thúc, p99=48ms.
~~~

Cần đồng bộ timestamp giữa generator/API/cache/DB, ghi task markers và dùng traces. **Tương quan không tự là bằng chứng quan hệ nhân quả**; nên có controlled tests để phân biệt.

## 51. Cold penalty và time-to-SLO

\[
\mathrm{ColdPenalty}_{p99}
=\frac{p99_{\mathrm{cold}}}{p99_{\mathrm{warm}}}
\]

Nếu cold p99 600 ms, warm p99 60 ms, tỷ số là **10 lần** trong workload đó.

Định nghĩa:

\[
\mathrm{TimeToSLO}
=t_{\mathrm{first\ sustained\ compliance}}-t_{\mathrm{start}}
\]

Cần định nghĩa “sustained” theo nhiều cửa sổ và error/latency SLO; một giây đẹp đơn lẻ chưa chứng minh phục hồi.

## 52. Failover: HTTP 200 chưa phải hồi phục SLO

Mốc nên lưu:

~~~text
t_failure
t_detection
t_failover
t_firstSuccessfulRequest
t_SLO_restored
t_replicationCatchup_complete
t_backgroundRecovery_complete
~~~

Node mới có cache lạnh và đang catch-up có thể trả một số HTTP 200 trong khi p99 vẫn cao.

RTO cần nói rõ mốc nào được xem là recovered; đo riêng startup/recovery latency và business correctness.

## 53. Cold miss budget trong capacity planning

Giả sử Redis warm hit 85%, source nhận 15% read traffic. Nếu Redis mất, source có thể phải nhận gần 100%.

Tỷ số lý tưởng:

\[
\frac{100\%}{15\%}\approx6{,}67
\]

Trên thực tế retries, coalescing, load shedding, errors và TTL có thể làm khác.

Thiết kế cold-state capacity:

- Rate-limit source fallback.
- Coalesce hot key misses.
- Staggered recovery/prewarm.
- Degraded mode.
- Capacity/headroom theo failure model.

Cache nóng giảm tải nguồn nhưng **không làm đường cache miss biến mất khỏi kiến trúc**.

## 54. Báo cáo benchmark cần những mục nào?

~~~markdown
## Mục tiêu
- Workload nào? SLO nào?
- Phạm vi database, service hay end-to-end?

## Môi trường
- Engine/driver/JVM version.
- Nodes, CPU, RAM, disks, network.
- Replication, durability, consistency.
- Dataset, index, key distribution.
- Cache layers và memory limits.

## Phương pháp
- Offered QPS, mix, arrival model.
- Warm-up procedure và exit criteria.
- Cold/warm background states.
- Duration, repetitions, latency histograms.

## Kết quả
- Completed QPS, error/timeout rate.
- p50/p95/p99 theo time windows.
- Cache miss/disk I/O/background markers.
- Cold penalty, time-to-SLO, backlog.

## Giới hạn
- Các trạng thái chưa test.
- Khác biệt production.
- Metrics nội bộ không quan sát được.
~~~

Không lấy một con số QPS cuối cùng tách khỏi toàn bộ metadata để quyết định production capacity.

## 55. Runbook: p99 tăng sau deploy

1. Xác định instances restart và tốc độ traffic ramp.
2. Kiểm JVM JIT/class loading, GC, threads.
3. Kiểm driver pool pending/connection creation.
4. Kiểm L1/Redis hit ratio và eviction.
5. Kiểm source QPS tăng do misses.
6. Kiểm database buffer misses và physical disk reads.
7. Kiểm compaction, backup, repair, index build trùng lúc.
8. Kiểm errors, timeouts, retries, queue và CPU throttling.
9. Áp dụng bounded prewarm, giảm ramp hoặc load shedding nếu nguồn quá tải.
10. Theo dõi time-to-SLO rồi bổ sung cold tests cho rollout lần sau.

Không mặc định tăng TTL hoặc RAM khi bottleneck thực nằm ở pool startup hay maintenance I/O.

## 56. Runbook: writes nhanh lúc đầu nhưng chậm sau 30 phút

1. Xem memtable flush queue, WAL pressure.
2. Kiểm pending compactions/SSTables và write stalls.
3. Đối chiếu disk read/write utilization và latency.
4. Kiểm tombstone/TTL churn.
5. Kiểm replication lag/repair/network.
6. Kiểm GC/heap/memory pressure.
7. So offered vs completed throughput và queue trend.
8. Xác định sustainable write rate.
9. Thử throttling, data model/partition hoặc scale trong môi trường an toàn.
10. Không tắt compaction/repair production để giữ số benchmark đẹp.

## 57. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| Warm-up luôn 5 phút | Phụ thuộc working set và tầng cache | Tiêu chí ổn định |
| Restart API là database cold | Redis/DB có thể vẫn warm | Nhãn theo tầng |
| Restart DB làm OS cache cold | OS page cache có thể còn | Đo physical reads |
| Cache hit cao nghĩa dữ liệu mới | Warmth không phải freshness | Source versions |
| Query plan cache và data cache giống nhau | Metadata khác pages | Đo riêng |
| GET 100 keys chứng minh database QPS | Phần lớn có thể hit Redis | Đếm DB operations |
| Dataset bé đại diện dataset lớn | Cache/disk/index khác | Data đại diện |
| Tắt compaction tăng throughput bền | Debt/stalls chưa xuất hiện | Soak test |
| GET-only đủ để dự đoán writes | Writes tạo flush/compaction | Mixed workload |
| Cache warm giúp mọi query | CPU/scan/lock vẫn tốn | Query analysis |
| Backup luôn làm chậm cố định | Tùy topology và engine | Đo overlap |
| TTL hết nghĩa bytes đã xóa | Cleanup bất đồng bộ | Logical vs physical |
| HTTP 200 sau failover là recovered | SLO có thể chưa phục hồi | Time-to-SLO |
| Offered QPS bằng completed | Có timeouts/errors/queue | Completed QPS |
| Closed-loop luôn phản ánh arrivals thật | Có coordinated omission | Arrival model rõ |
| Trung bình p99 mỗi phút là p99 chung | Sai thống kê | Merge raw histograms |
| Một run đẹp là đủ | State drift và variance | Repeated trials |
| Run B sau A luôn công bằng | Cache có thể nóng hơn | Đảo thứ tự |
| Flush cache production là cách cold test | Gây rủi ro outage | Môi trường cô lập |
| Peak throughput là production capacity | Có thể vượt p99/error SLO | SLO-compliant capacity |
| Runner không thể là bottleneck | Runner CPU/network giới hạn | Runner telemetry |

## 58. Bài tập thực hành

### Bài tập 1 — Cold và warm

API p99 650 ms trong phút đầu, 45 ms sau mười phút. Liệt kê ít nhất tám nguyên nhân và cách dùng JVM/pool/cache/disk/background metrics phân biệt.

### Bài tập 2 — Tầng nào cold?

Chỉ restart Java API, giữ Redis và MongoDB. Phân loại JVM/JIT, L1, pool, Redis, DB buffer và OS page cache.

### Bài tập 3 — Working set

Database có 100 triệu records, 80% requests vào 100.000 keys. So sánh benchmark skewed với uniform và ảnh hưởng hit ratio.

### Bài tập 4 — Source QPS sau Redis loss

20.000 requests/s, Redis hit 95%. Tính source reads lý tưởng khi cache warm và khi Redis rỗng. Nêu tác động retries/coalescing.

### Bài tập 5 — JVM warm-up

100 calls Java repository đầu chậm hơn các calls sau. Thiết kế phép đo tách JIT, TLS, pool và DB query execution.

### Bài tập 6 — Micro vs end-to-end

Vì sao JMH đo serialization nhanh không chứng minh API đạt 100.000 req/s? Thiết kế phép đo bổ sung.

### Bài tập 7 — Connection pool

Pool tăng từ 2 lên 100 connections. Vẽ timeline p99/connection waits và đề xuất readiness gate.

### Bài tập 8 — Query plan và disk cache

Query đầu chậm nhưng physical I/O gần như không đổi. Nêu giả thuyết và telemetry cần kiểm.

### Bài tập 9 — OS page cache

Restart database nhưng host không reboot. Vì sao OS cache có thể còn? Đề xuất cold test an toàn.

### Bài tập 10 — Warm-up exit criteria

Từ time-series p99, completed QPS, cache hit và disk I/O, hãy định nghĩa tiêu chí steady-state có thể tái lập.

### Bài tập 11 — Hot key distribution

So 90% traffic vào 1.000 keys với uniform 100.000 keys. Dự báo cache hit và hot partition contention.

### Bài tập 12 — Redis restart

Redis rỗng ở giờ cao điểm. Thiết kế singleflight, throttled prewarm, jitter, fallback/rate limiting để bảo vệ MongoDB.

### Bài tập 13 — Redis persistence

Phân biệt restart Redis có dataset được phục hồi với cache hoàn toàn trống. Các metrics xác minh?

### Bài tập 14 — Cassandra compaction

Write throughput giảm sau 45 phút vì flush/compaction. Chọn metrics xác định sustained throughput.

### Bài tập 15 — Cassandra tombstones

Một partition có nhiều TTL-expired rows. Vì sao warm cache chưa bảo đảm query nhanh?

### Bài tập 16 — MongoDB WiredTiger

Lập dashboard gồm DB cache, eviction, disk I/O, query plans, checkpoint và driver pool để debug cold latency.

### Bài tập 17 — Index build

Vì sao không so performance lúc index đang build với sau khi hoàn tất mà không ghi background/cache state?

### Bài tập 18 — Backup overlap

Thiết kế A/B experiment với và không có backup; giữ workload/cache state tương đương và đo p99, throughput, disk/network.

### Bài tập 19 — TTL cleanup

So logical TTL expiration và physical cleanup trong Redis, MongoDB, Cassandra. Tại sao có thể ảnh hưởng p99?

### Bài tập 20 — Failover

Đo t_failure, first HTTP 200, t_SLO_restored và replica catch-up. Vì sao các mốc khác nhau?

### Bài tập 21 — Arrival model

Server pause 2 giây; closed-loop client giảm arrival. Giải thích coordinated omission và cách chọn open-loop.

### Bài tập 22 — Offered vs completed

Generator phát 50.000 req/s, hoàn thành 35.000 success/s. Bạn sẽ báo capacity/error/queue thế nào?

### Bài tập 23 — Little's Law

Throughput 2.000 req/s và mean latency 50 ms. Tính average in-flight ở steady state và nêu giới hạn.

### Bài tập 24 — Percentiles

Hai phút có p99 50 ms và 300 ms, sample counts khác nhau. Vì sao không được lấy trung bình 175 ms làm p99 chung?

### Bài tập 25 — Cold penalty

p99 cold 600 ms, warm 60 ms. Tính tỷ số; định nghĩa time-to-SLO có cửa sổ ổn định.

### Bài tập 26 — Maintenance matrix

Thiết kế sáu scenarios app cold/warm, Redis cold/warm, compaction/backup/repair; nêu cách xác nhận trạng thái.

### Bài tập 27 — Task timeline

Backup phút 10–15 và compaction phút 14–20, p99 tăng phút 14–17. Những metrics nào cần có để tìm nguyên nhân?

### Bài tập 28 — Memory pressure

Working set vừa đủ cache ở benchmark nhưng production tăng gấp đôi. Thiết kế test thrashing và capacity headroom.

### Bài tập 29 — Load generator

Generator CPU 100%, attempted QPS thấp hơn planned rate. Kiểm và sửa giới hạn generator thế nào?

### Bài tập 30 — So sánh engine A/B

A luôn chạy trước B; B p99 thấp hơn 20%. Hãy lập kế hoạch repeated trials, randomized order, cache/background controls.

### Bài tập 31 — Production runbook

API p99 tăng 500 ms sau rolling deploy. Viết runbook kiểm JVM, pools, Redis misses, source I/O, background tasks và time-to-SLO.

### Bài tập 32 — Sustainable capacity

Engine đạt 70.000 writes/s trong 30 giây nhưng sau 45 phút chỉ còn 20.000 vì compaction debt. Nêu capacity nào phù hợp để lập kế hoạch và vì sao.

### Bài tập 33 — Thiết kế benchmark tổng hợp

Một hệ gồm Java API, Redis cache-aside, MongoDB lưu products, Cassandra lưu events, search index; peak 30.000 req/s. Hãy thiết kế:

1. Workload, key/tenant distribution và dataset đại diện.
2. Cold app, cold Redis, cold database và warm steady scenarios.
3. JVM/connection pool/query plan/DB/OS cache instrumentation.
4. Sustained writes kích hoạt flush/compaction.
5. Backup, repair, reindex, TTL cleanup overlap.
6. Arrival model, coordinated omission, generator capacity.
7. Completed throughput, p99, errors và backlog.
8. Repetitions, manifest và raw histograms.
9. Recovery, cold penalty, time-to-SLO.
10. Headroom, readiness, rollout và runbook.

### Bài tập 34 — Phản biện báo cáo sai

Một báo cáo viết:

~~~text
100.000 GET/s.
Chạy 2 phút với 100 keys.
JVM và Redis đã warm sẵn.
Database nhận rất ít requests.
Không có writes, compaction hoặc backup.
Không thống kê errors/timeouts.
Chỉ chụp p99 của 30 giây cuối.
~~~

Hãy chỉ ra từng giới hạn, viết lại kết luận trung thực về **điều đã thực sự đo**, và đề xuất những cold, mixed-workload, soak và recovery tests còn thiếu.

---

**Kết luận:** Hiệu năng NoSQL là kết quả của **workload cộng với trạng thái hệ thống**, không chỉ của engine hay cấu hình phần cứng. **Warm-up** liên quan JVM/JIT, connections, query metadata và cache population; **cache nóng/lạnh** phụ thuộc working set, phân bố truy cập và memory pressure; **background work** như flush, compaction, checkpoint, backup, repair, TTL cleanup và reindex có thể làm throughput và tail latency thay đổi mạnh. Một benchmark đáng tin phải **gắn nhãn trạng thái từng tầng**, đo cả cold start lẫn steady state, thử sustained mixed workload và maintenance overlap, dùng arrival model đúng, báo completed throughput cùng errors/p99 theo thời gian và lưu manifest để tái lập. **Không bỏ phút xấu không giải thích, không coi cache hit là dữ liệu đúng, không lấy initial burst làm sustained capacity và không lấy peak throughput vượt SLO làm năng lực production.** Mục tiêu là tìm **SLO-compliant capacity, time-to-SLO và kế hoạch vận hành an toàn** ngay cả khi cache lạnh, dịch vụ mới khởi động hoặc hệ đang làm tác vụ nền.
