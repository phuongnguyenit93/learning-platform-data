# Phân biệt giới hạn ứng dụng, mạng, CPU, bộ nhớ và lưu trữ

Một truy vấn NoSQL chậm **không có nghĩa chắc chắn ổ đĩa chậm**, cũng không có nghĩa “CPU còn thấp nên database chưa quá tải”. Từ khi Java application nhận request đến khi trả kết quả, dữ liệu có thể chờ ở hàng đợi HTTP, chờ permit và connection pool, bị giới hạn bởi network latency, bị nghẽn trên CPU của coordinator, thiếu RAM khiến cache miss, đọc từ storage quá nhiều, hoặc gặp một shard/partition quá nóng. Nhiều trường hợp còn có **nhiều nút thắt nối tiếp hoặc khuếch đại lẫn nhau**.

Bài học này thuộc chương **Hiệu năng và đo tải** của module **Database No SQL**. Mục tiêu không phải học một danh sách “tăng thread, tăng RAM, tăng SSD”, mà là xây dựng **phương pháp xác định giới hạn thật từ số đo**, phân biệt dấu hiệu và nguyên nhân, chọn thí nghiệm đủ để bác bỏ giả thuyết, rồi tối ưu đúng tầng.

> **Nguyên tắc trung tâm:** Đo theo **đường đi của một logical request** và cùng lúc nhìn **arrival rate, useful throughput, latency distribution, queueing, utilization, saturation, errors** của từng tài nguyên. Một chỉ số đơn lẻ, nhất là trung bình CPU hoặc p50, không đủ kết luận bottleneck.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **bottleneck**, **saturation**, **utilization**, **latency**, **throughput**, **service time**, **queue wait** và **retry amplification**.
2. Phân tích độ trễ từ Java client đến NoSQL và trở lại, chia thành thời gian ứng dụng, connection/pool, mạng, server CPU, bộ nhớ/cache và lưu trữ.
3. Dùng mô hình **RED** (*Rate–Errors–Duration*) và **USE** (*Utilization–Saturation–Errors*) để tìm các điểm nghẽn.
4. Dùng **Little’s Law** để liên hệ throughput, mean response time và in-flight work trong **một phạm vi đo xác định**.
5. Nhận diện các dấu hiệu của **application bottleneck**: hàng đợi, blocked threads, pool exhaustion, serialization, connection leak, GC, retry và rate limiting.
6. Nhận diện **network bottleneck**: RTT, bandwidth, packet loss/retransmission, DNS/TLS, TCP congestion và cross-region latency.
7. Phân biệt CPU saturation, lock/contention, CPU quota throttling, skew/hot partitions, executor stall và CPU thấp do chờ I/O.
8. Phân tích memory pressure: heap allocation/GC, RSS, page cache, working set, cache hit/miss, swap, OOM và compaction-memory pressure.
9. Phân tích storage: IOPS, throughput, queue depth, p95/p99 device latency, fsync, WAL, compaction, SSD/NVMe và cold reads.
10. Thiết kế đo tải với workload đại diện, controlled experiments, fault injection, dashboard, runbook và kết luận có bằng chứng.

## 2. Bài toán xuyên suốt: Order API Java truy vấn NoSQL

Một dịch vụ Order API có 16 pods Java, kết nối tới cụm NoSQL 6 nodes. Ở tải thấp, một truy vấn lấy Order theo khóa mất 12–25 ms. Khi có chiến dịch bán hàng, biểu đồ cho thấy:

~~~text
Traffic:
  2,000 HTTP requests/s (ổn định)

Observed:
  GET /orders/{id} p50:  30 ms
  GET /orders/{id} p99: 780 ms
  HTTP error rate:       2.0%
  App CPU average:      42%
  Database CPU average: 38%
  Retry attempts:       tăng mạnh
  Search/cache misses:  tăng
~~~

Đây chỉ là số minh họa. **Câu hỏi:** Có phải thiếu CPU? Có nên tăng pool 50 lên 200? Cần tăng RAM database? Thêm node? Chuyển sang SSD nhanh hơn?

Không thể trả lời chỉ từ các số trên. Ví dụ:

- Chỉ **một CPU core** trên một node đạt 100%, CPU trung bình node vẫn 38%.
- Một **partition key nóng** bị queue sâu, các nodes khác gần như rảnh.
- Connection pool ở Java bị chiếm bởi các cursor/transaction lâu, nhưng database server còn rảnh.
- JVM GC stop-the-world làm p99 tăng, ngoài thời gian server xử lý.
- Network inter-region RTT 200 ms cộng nhiều round trips khiến p99 cao.
- Read pattern mới làm cache hit giảm, dẫn đến storage read latency tăng.
- SDK retry timeout 3 lần khiến 2.000 logical requests/s biến thành 5.000–6.000 DB attempts/s.

Chẩn đoán đúng phải **xác định bước nào tăng thời gian và tại sao**.

### 2.1. Đường đi của request

~~~mermaid
flowchart LR
    U["Caller / Load Generator"] --> LB["Load balancer"]
    LB --> A["Java HTTP server"]
    A --> Q["App queue / bulkhead"]
    Q --> P["NoSQL client pool"]
    P --> N["TCP/TLS / Network"]
    N --> C["NoSQL coordinator"]
    C --> R["Shard / Replica"]
    R --> M["RAM / cache"]
    M --> D["Storage / WAL / LSM"]
    R --> C
    C --> A
~~~

Một truy vấn có thể gọi nhiều replicas, index segments hoặc partitions. Sơ đồ chỉ biểu diễn đường đi khái quát, **không phải mọi engine đều tổ chức coordinator–replica–cache–disk như nhau**.

### 2.2. Một request có thể tạo nhiều DB operations

~~~text
HTTP request #R42
  -> read user session
  -> read Order
  -> read 8 OrderItems
  -> retry Order once on timeout
  -> write audit record
~~~

Độ trễ HTTP phụ thuộc fan-out, execution model (tuần tự/song song), backpressure và retries. **HTTP RPS không đồng nghĩa DB RPC/s**.

## 3. Các khái niệm căn bản: tải, công suất và giới hạn

### 3.1. Throughput có ích khác số attempts

**Logical throughput** là số yêu cầu nghiệp vụ được hoàn thành hợp lệ mỗi giây.

**Attempt throughput** có thể là tổng số DB RPCs được gửi, bao gồm retries/speculative attempts/duplicate requests.

Ví dụ:

~~~text
Logical read operations/s: 1,000
Average attempts/op:      1.8
DB RPC attempts/s:        1,800
Useful read results/s:    930
~~~

Nếu dashboard chỉ có “1.800 DB requests/s”, có thể nhầm hệ đang năng suất cao hơn thực tế, trong khi 800 attempts bổ sung chỉ là retries.

### 3.2. Utilization khác saturation

**Utilization**: Tỷ lệ thời gian hoặc công suất mà tài nguyên đang được dùng, ví dụ một CPU core bận 95% hoặc thiết bị disk busy 90% (cách tính phụ thuộc nguồn metric).

**Saturation**: Nhu cầu vượt khả năng phục vụ ngay, tạo **queueing, throttling, rejection, contention hoặc thời gian chờ tăng**. Một resource có thể bận cao mà chưa có queue rõ; ngược lại, một hệ có **global average utilization thấp nhưng một thành phần nhỏ đã saturated**.

### 3.3. Bottleneck có thể thay đổi khi tối ưu

~~~text
Before:
  Query CPU cost high -> 500 ops/s

After reducing CPU cost:
  Storage becomes saturated -> 750 ops/s

After better cache:
  Network bandwidth becomes limiter -> 1,100 ops/s
~~~

Tối ưu một tầng thường **làm lộ giới hạn tiếp theo**. Không kỳ vọng chỉ một thay đổi giải quyết mọi hệ số tải.

### 3.4. Latency và service time

**Response time** thường bao gồm **queue wait + service time + những overhead trên đường đi**.

Ví dụ:

~~~text
App queue wait:          180 ms
Pool acquire wait:       220 ms
Network round trips:      20 ms
NoSQL server execution:   35 ms
Serialization:             8 ms
Total approximate:       463 ms
~~~

Nếu chỉ đo `server execution=35 ms`, query có thể “nhanh” theo DB metrics nhưng vẫn **chậm đối với người dùng**.

### 3.5. p50, p95 và p99 không phải mean

Nếu p99=800 ms, nghĩa xấp xỉ 1% observations có latency **lớn hơn hoặc bằng vùng percentile đó** theo định nghĩa/phương pháp tính. Nó không có nghĩa tất cả requests mất 800 ms, và không cho biết mean.

Tail latency quan trọng vì API có fan-out nhiều queries:

~~~text
One HTTP request needs 20 independent DB reads in parallel.
Its response completes when the slowest required read completes.
~~~

Trong mô hình độc lập lý tưởng, nếu mỗi subrequest có 1% xác suất vượt ngưỡng \(t\), xác suất ít nhất một trong 20 subrequests vượt \(t\) là:

\[
1-(1-0{,}01)^{20}\approx18{,}2\%
\]

Đây là ví dụ xác suất minh họa; trong hệ thật, latencies có thể **tương quan** do cùng shard, cache, network hoặc GC nên không tự áp công thức độc lập.

## 4. RED và USE: hai lăng kính bổ sung

### 4.1. RED cho services và endpoints

| Signal | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Rate** | Bao nhiêu yêu cầu thực sự đến/hoàn thành? | requests/s, DB operations/s |
| **Errors** | Bao nhiêu yêu cầu thất bại, bị throttle hoặc bị từ chối? | 5xx, timeouts, CAS conflicts |
| **Duration** | Phân phối latency thế nào? | p50, p95, p99, histogram |

RED giúp phát hiện **tác động với người dùng** nhưng không trực tiếp nói tài nguyên nào đã saturated.

### 4.2. USE cho tài nguyên

| Signal | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Utilization** | Tài nguyên bận bao nhiêu | CPU per-core usage, NIC throughput |
| **Saturation** | Có công việc xếp hàng/không đủ capacity không | run queue, pending pool, disk queue |
| **Errors** | Tài nguyên phát sinh lỗi nào | disk I/O errors, TCP retrans, OOM |

USE giúp phát hiện **nút thắt** và kiểm tra giả thuyết về từng loại resource.

### 4.3. Ma trận kết hợp

~~~text
RED tells you:
  GET Order p99 is now 800 ms and error rate rises.

USE tells you:
  App pool pending acquires rise to 500;
  Database CPU has no matching increase;
  Database service time remains 20 ms.

Hypothesis:
  App-side connection acquisition/pool lifecycle is bottleneck.
~~~

Không dừng ở giả thuyết. Cần kiểm tra active connection lifetime, driver topology, cursor leaks, per-server pools và một controlled change.

### 4.4. Chọn đúng scope cho metrics

Mọi metric nên có các dimensions có ý nghĩa:

- Endpoint/operation class: point-read, scan, write, transaction.
- Service instance/pod và version deploy.
- Cluster, region, shard/node hoặc database namespace.
- Read/write consistency và request size.
- Success, timeout, throttle, connection failure.

Không đẩy raw userId, orderId hoặc tenantId vào **time-series metric labels** với cardinality khổng lồ. Chi tiết key nên ở logs/traces có kiểm soát.

## 5. Little’s Law: throughput, mean latency và số việc trong hệ

Trong trạng thái ổn định và cùng một phạm vi quan sát:

\[
L = \lambda W
\]

Trong đó:

- \(L\): Số lượng công việc trung bình trong hệ.
- \(\lambda\): Throughput hoàn thành trung bình (công việc/giây).
- \(W\): Thời gian trung bình một công việc ở trong hệ (giây).

Nếu database xử lý 1.500 logical operations/s, mean time in system là 40 ms:

\[
L=1500\times0{,}040=60
\]

Tức trung bình khoảng 60 operations đang **ở trong phạm vi đo**, có thể gồm đang chờ và đang thực thi.

### 5.1. Không dùng p99 thay mean rồi gọi là định luật

~~~text
Incorrect:
  L = QPS * p99 latency (as "Little's Law")
~~~

Little’s Law cơ bản dùng mean. p99 có thể dùng cho **headroom heuristic** nhưng phải ghi rõ giả định; không được tự biến kết quả thành số connections bắt buộc.

### 5.2. Phạm vi quyết định kết luận

Nếu đo từ HTTP ingress đến response, \(L\) là **average HTTP requests in system**.

Nếu đo thời gian từ DB client operation submit đến completion, \(L\) là **average DB operations in client/driver scope**.

Nếu muốn đo số requests đang chiếm connection, phải biết driver multiplex requests và thời gian giữ connection thực.

### 5.3. Khi hệ quá tải không ổn định

Nếu arrival rate cao hơn capacity lâu dài, queue liên tục tăng; công thức trung bình không tự cho một **capacity tối ưu** từ vài điểm số. Cần load shedding, bounded queues hoặc kiểm soát arrival rate trước khi đo trạng thái ổn định.

## 6. Đặt giả thuyết trước khi chỉnh cấu hình

Một quy trình tốt:

1. **Chỉ rõ triệu chứng:** p99 của endpoint nào, từ lúc nào, bao nhiêu request bị ảnh hưởng?
2. **Tách quãng thời gian:** request queue, acquire connection, network, server, serialize.
3. **Xác định thành phần đầu tiên saturated:** CPU core, pool, link, disk, shard, GC hay admission.
4. **Đặt giả thuyết có thể bác bỏ:** “Pool quá nhỏ” chứ không phải “database chậm”.
5. **Chọn phép đo/experiment:** tăng pool trong một canary trong khi giữ load, quan sát server/queue.
6. **So kết quả với SLO/business throughput:** Có giảm latency thực và errors không? Có tăng backend overload không?
7. **Đóng kết luận theo dữ kiện**, theo dõi giới hạn mới.

### 6.1. Ví dụ giả thuyết bác bỏ được

**Giả thuyết:** Pool max 30 quá nhỏ cho point reads; nhiều requests chờ acquire còn DB rảnh.

**Dự đoán:** Ở load cố định, tăng pool 30→45 làm **pool wait giảm**, DB throughput tăng hoặc giữ tốt, p99 tốt hơn, **DB queues không tăng xấu**.

**Bác bỏ:** Pool wait giảm nhưng DB p99/timeout tăng, active server operations rất cao, hoặc bottleneck vẫn ở shard nóng. Khi đó pool là **hàng đợi nhìn thấy**, nhưng có thể chỉ đang điều tiết một backend đã saturated.

### 6.2. Controlled experiment

Không thay **pool size, query index, CPU request, disk type, retry policy** đồng thời rồi cố gán kết quả cho một nguyên nhân. Ưu tiên thay một nhân tố, giữ workload tương đương, có baseline/canary/rollback.

### 6.3. Môi trường đo

CPU frequency scaling, JIT warm-up, JVM GC, cache warm-up, network path và dataset size đều ảnh hưởng kết quả. Một truy vấn 1.000 lần trên 100 rows toàn cache không đại diện cho production hàng trăm triệu records và hot partitions.

## 7. Tổng quan các giới hạn và dấu hiệu

| Giới hạn chủ đạo | Triệu chứng nổi bật | Chỉ số cần đối chiếu | Tăng gì **không chắc giúp** |
| --- | --- | --- | --- |
| Ứng dụng/hàng đợi/pool | Queue wait, pending acquire, blocked threads | App in-flight, executor queue, pool wait | Tăng DB RAM |
| Mạng/RTT | Latency theo region, retrans, TCP timeout | RTT, loss, bandwidth, per-hop trace | Tăng DB CPU |
| CPU | Per-core high, run queue, CPU throttling | CPU usage/quota, cycles, flame graph | Chỉ tăng connections |
| Bộ nhớ/cache | GC pauses, page faults, cache misses, swapping | Heap/GC, RSS, cache hit, RSS vs limits | Chỉ tăng threads |
| Lưu trữ | Disk read/write queues, high fsync latency, compaction stalls | IOPS, MB/s, await, p99 device latency | Chỉ tăng connection pool |
| Hot partition | Một shard saturated, các node khác idle | Per-key/per-shard distribution | Scale node đồng đều mà không repartition |
| Lock/transaction contention | Abort/conflict/retry tăng | Conflict count, lock wait, CAS/LWT latency | Nâng số connections |
| Retry storm | Attempts/s tăng nhanh hơn logical ops/s | Attempts per operation, timeout classes | Tăng retry count |

### 7.1. Các giới hạn thường có liên hệ dây chuyền

~~~text
Index miss -> more disk IO
   -> slower DB response
      -> more connections held
         -> pool wait grows
            -> HTTP timeout
               -> retry amplification
                  -> more disk IO
~~~

Nếu chỉ nhìn **pool wait**, có thể chữa sai vào nơi cuối cùng chuỗi. Cần theo dõi **thời gian xuất hiện** và quan hệ cause/effect ở từng tầng.

## 8. Giới hạn phía ứng dụng Java: đừng nhầm client bottleneck với database

Trong Java, một số hàng đợi có thể tồn tại đồng thời:

~~~text
HTTP accept backlog
  -> framework request queue
  -> application business executor
  -> semaphore / bulkhead
  -> SDK asynchronous pending queue
  -> connection pool acquire
  -> network
  -> NoSQL server
~~~

Nếu **trang thái chờ đầu tiên** xuất hiện trong JVM, database chưa chắc là thủ phạm. Ngược lại, DB server bị chậm có thể khiến những tài nguyên phía ứng dụng **bị giữ lâu**, tạo queue ở JVM như hệ quả thứ cấp.

### 8.1. Connection pool hết chỗ

Dấu hiệu:

- `activeConnections` gần max trong thời gian dài.
- `pendingAcquires` và `acquireWaitP99` tăng.
- Nhiều threads ở trạng thái WAITING/TIMED_WAITING trên pool.
- Tốc độ tạo/đóng connection tăng khi autoscaling/failover.

Những nguyên nhân:

1. Pool thực sự nhỏ hơn concurrency cần thiết.
2. DB operation chậm làm giữ connection lâu.
3. Cursor/session/transaction chưa đóng.
4. Async task fan-out tạo quá nhiều pending requests.
5. Driver có **pool theo server**, một server đang saturated dù pool tổng chưa đầy.

**Không tăng max pool trước khi phân biệt năm khả năng này.**

### 8.2. Thread/executor saturation

Giả sử executor có 16 workers và một queue 5.000 tasks:

~~~text
activeThreads = 16 / 16
queuedTasks   = 4,500
DB server CPU = low
~~~

Nếu task đang block do gọi external API hoặc chờ lock application, tăng DB connection pool không giúp. Thêm workers có thể giảm queue nếu backend còn capacity; nhưng nếu chính workers đều chờ DB đã quá tải, thêm workers lại tạo thêm pressure.

### 8.3. Event loop bị block

Trong Netty/WebFlux, một blocking database driver hoặc `Future.get()` gọi trực tiếp trên event-loop thread có thể khiến **nhiều HTTP connections** chậm dù database vẫn trả lời nhanh. Dấu hiệu:

- Event loop lag tăng.
- CPU thấp/trung bình.
- Thread dump cho thấy event loop chờ socket/monitor/synchronous call.
- Số active requests tăng nhưng DB operation count không tăng tương ứng.

Giải pháp là dùng **async driver thật** hoặc offload blocking call vào bounded executor; không đặt một executor vô hạn để che lỗi.

### 8.4. Serialization/JSON mapping là chi phí CPU và heap

Một truy vấn trả 10 MB document có thể nhanh trên DB nhưng Java tốn CPU để:

~~~text
decode BSON/JSON/protobuf
  -> build object graph
  -> mapping/validation
  -> filter fields
  -> encode HTTP JSON
~~~

So sánh **DB response received → HTTP response ready** với **DB server time**. Dùng CPU profiling/allocations để kiểm tra Jackson/Gson/codec có chiếm CPU hoặc tạo nhiều temporary objects không.

### 8.5. N+1 queries

Một API đọc 1 Order rồi gọi 100 queries cho 100 OrderItems:

~~~text
1 HTTP request
  -> 1 Order lookup
  -> 100 item lookups
~~~

Ngay cả khi mỗi query chỉ 3 ms, tuần tự 101 round trips có thể thành hàng trăm ms. Đổi data model, batch read hoặc embedded document khi phù hợp có thể giảm tải **cả app, network và DB**.

Trong NoSQL, thiết kế access pattern theo query thường quan trọng hơn cố thay CPU hay network ở hạ tầng.

### 8.6. Application lock contention

Ví dụ code có một `synchronized` global lock quanh mọi call DB:

~~~java
public synchronized Order findOrder(String orderId) {
    return repository.findById(orderId);
}
~~~

Chỉ một request được phép vào method trên **một service instance**, dù pool có 100 connections. CPU thấp không có nghĩa có nhiều capacity; threads có thể chờ lock.

Nếu bỏ synchronization, phải đảm bảo repository/client và mutable state đúng thread safety. Không bỏ lock bảo vệ tính đúng chỉ để tăng throughput mà không thay cơ chế đồng bộ.

### 8.7. Semaphore và bulkhead local

Nếu có giới hạn 20 in-flight DB operations mỗi pod, load vượt ngưỡng sẽ gây **rejection hoặc waiting** theo policy. Đó có thể là **hành vi cố ý** bảo vệ DB, không phải “pool bị lỗi”.

Phải ghi metrics riêng:

~~~text
admission_rejected
bulkhead_wait_time
bulkhead_inflight
driver_pool_wait_time
db_server_latency
~~~

Nếu `bulkhead_rejected` tăng nhưng server còn rảnh, limit có thể quá chặt; nếu server đã throttling, đây có thể là hành vi đúng.

### 8.8. Một client lâu dài, nhiều resources ngắn hạn

Sai:

~~~java
public Order handle(String id) {
    MongoClient client = MongoClients.create(uri);
    return readOrder(client, id);
}
~~~

Client per request tạo pool, TLS handshake, threads và monitor work liên tục. Nên tạo driver client ứng dụng cấp cao **một lần theo vòng đời component**, đóng khi shutdown và release cursors/explicit sessions đúng cách.

### 8.9. Client-side throttling không phải server throttling

Một SDK/cloud provider có thể có retry quota, adaptive rate limiter và HTTP max concurrency. Khi client từ chối do local limiter, metrics DB server có thể không tăng. Khi server trả throttling, client có thể retry. Cần phân biệt **ai đã từ chối** và đếm số attempts.

## 9. Mẫu chẩn đoán giới hạn ứng dụng bằng Java

### 9.1. Thời gian từng stage

Một wrapper khái niệm:

~~~java
long start = System.nanoTime();
Permit permit = admission.tryAcquire();
long afterAdmission = System.nanoTime();

ConnectionLease lease = pool.acquire();
long afterAcquire = System.nanoTime();

Order order = repository.findByIdUsing(lease, id);
long afterDb = System.nanoTime();

return serialize(order);
// Use finally/AutoCloseable for permit and lease
~~~

Đây là pseudocode để giải thích các mốc, **không phải mẫu JDBC/NoSQL SDK có thể chạy trực tiếp**; đa số NoSQL driver quản lý connection lease nội bộ và không cho application gọi `pool.acquire()` theo cách này.

Trong implementation thực tế, sử dụng **driver metrics/listeners, tracing spans, stopwatch monotonic** và đo số liệu qua SDK-supported hooks.

### 9.2. Đọc thread dumps có ngữ cảnh

Các trạng thái Java:

- `RUNNABLE`: Có thể đang chạy CPU hoặc đang thực hiện native/socket operation tùy platform/JVM; không suy 100% CPU từ RUNNABLE.
- `BLOCKED`: Chờ Java monitor.
- `WAITING`: Chờ không thời hạn tại một synchronization primitive.
- `TIMED_WAITING`: Chờ có timeout.

Thu nhiều thread dumps cách nhau một khoảng để phân biệt một stack ngắn ngủi với **kẹt thường trực**, rồi đối chiếu CPU profiler và pool metrics.

### 9.3. GC pause vs app blocked

Nếu tất cả request latencies cùng tăng vào những đợt 200 ms trong khi Java GC log báo pause 200 ms, đây là dấu hiệu memory/GC; không nên kết luận mạng chậm vì HTTP socket response đến trễ.

### 9.4. Không đo timestamp thiếu monotonicity

§System.nanoTime()§ phù hợp cho elapsed time trong một JVM. Dùng §Instant.now()§/wall-clock cho timestamp audit và cross-service traces, nhưng phải xử lý clock skew; không lấy chênh lệch giữa hai node độc lập làm RTT chính xác khi clocks chưa đồng bộ.

## 10. Giới hạn mạng: RTT, bandwidth, packet loss và connection setup

Một NoSQL request không chỉ cần CPU backend. Nó phải **đi qua mạng** giữa application, load balancer, database coordinator, replicas và có thể storage service trong cloud.

### 10.1. RTT đặt một mức nền

Một request-response đơn giản cần ít nhất một **network round trip** giữa caller và endpoint sau khi kết nối đã sẵn. Nếu app ở region A và database ở region B với RTT 70 ms, một chuỗi 5 round trips tuần tự có thể có **ít nhất khoảng 350 ms network RTT contribution** trước khi tính DB execution, TLS setup và application.

Đây là xấp xỉ theo topology và protocol; pipelining, multiplexing và parallelism có thể đổi số round trips trên critical path.

### 10.2. Latency vs bandwidth

**Latency** ảnh hưởng nhanh/chậm khi request nhỏ và tuần tự.

**Bandwidth** ảnh hưởng khi chuyển payload lớn hoặc stream khối lượng cao.

Ví dụ truyền 100 MiB qua đường truyền 100 Mbit/s, bỏ qua mọi overhead và khi dùng đủ bandwidth:

\[
100\ \mathrm{MiB}\times8/(100\ \mathrm{Mbit/s})
\approx8{,}39\ \mathrm{s}
\]

Ở đây dùng \(100\ \mathrm{MiB}=104\,857\,600\) bytes và \(100\ \mathrm{Mbit/s}=100\,000\,000\) bits/s. Thời gian thực thường lớn hơn vì TCP, congestion, giới hạn nguồn/đích.

### 10.3. RTT cao nhưng bandwidth dư

Point lookup trả 2 KiB vẫn chậm nếu inter-region RTT lớn, dù NIC sử dụng 3%. Thêm SSD nhanh hơn không giúp đáng kể nếu network RTT là thành phần chính.

### 10.4. Bandwidth saturation

Một scan 8 GiB hoặc CDC bulk replication có thể làm NIC egress đạt giới hạn. Dấu hiệu:

- Bytes/s áp sát mức network provisioned.
- Queue/drops ở network interface hoặc vSwitch.
- Truyền document lớn/scan cùng lúc với point reads.
- Latency tăng theo payload size hoặc concurrent transfers.

Phải phân biệt egress hạn mức cloud instance, load balancer/network appliance, private link, NAT gateway và DB node NIC.

### 10.5. Packet loss và TCP retransmission

Ngay cả khi bandwidth danh nghĩa còn, packet loss/retransmission có thể khiến TCP giảm congestion window, tăng tail latency. Dấu hiệu:

- TCP retransmission count tăng.
- RTT variance/jitter tăng.
- Timeouts, reset/connection errors.
- Một số AZ/region/host bị nặng hơn.

Không suy mọi retransmission là hạ tầng mạng lỗi; host CPU, NIC buffers, retransmission policy và application burst có thể liên quan.

### 10.6. DNS, TCP và TLS setup

Khi service tạo client mới mỗi request hoặc reconnect hàng loạt, latency có thể bao gồm:

~~~text
DNS resolution
TCP handshake
TLS handshake / auth
server protocol negotiation
first query
~~~

Mỗi phần có riêng overhead; cache/reuse client và connection pool thường giảm connection churn. Nhưng không giữ stale connections vô hạn nếu firewall/LB cắt idle sockets.

### 10.7. Nagle, buffering và message framing

Với nhiều small writes, buffering, Nagle/delayed ACK hoặc application flush strategy có thể ảnh hưởng latency trong một số protocol. Chỉ tuning socket flags khi trace chứng minh tầng đó là vấn đề; không đặt `TCP_NODELAY` như giải pháp mặc định cho mọi NoSQL driver.

### 10.8. Cross-AZ/cross-region replication

Một write có consistency level yêu cầu xác nhận từ nhiều replicas có thể chờ **network path tới replica chậm**. Tăng app-side CPU không giảm được RTT cross-region. Đổi consistency/quorum để lấy latency tốt hơn có thể thay **durability/availability semantics**; không làm mà không kiểm tra yêu cầu dữ liệu.

## 11. Chẩn đoán mạng bằng phép đo có giới hạn

### 11.1. So sánh cùng truy vấn từ nhiều vị trí

Ví dụ:

| Nơi chạy client | p50 | p99 | Gợi ý |
| --- | ---: | ---: | --- |
| Cùng AZ với DB | 12 ms | 28 ms | Đường gần ổn |
| AZ khác | 15 ms | 45 ms | Thêm RTT/variance |
| Region khác | 110 ms | 260 ms | Network path đáng nghi |

Các giá trị là **giả định minh họa**, không phải SLA thực tế.

Nếu DB server execution time như nhau nhưng client p99 tăng theo vùng, hãy kiểm tra mạng, TLS/setup, routing, proxy và retry.

### 11.2. Ping không phải đo DB request

ICMP ping có thể bị lọc/ưu tiên thấp và không đo network path/port/TLS/DB protocol thật. Dùng driver operation-level metrics, TCP RTT/network instrumentation và synthetic probes **qua cùng network path** để có tín hiệu phù hợp.

### 11.3. Dùng các công cụ đúng quyền

Trên môi trường có quyền và được phép quan sát:

~~~text
ss -tin             # TCP socket state/RTT, Linux
sar -n DEV 1         # network interface throughput
sar -n TCP,ETCP 1    # TCP retransmission/errors
ip -s link           # interface counters
~~~

Tính khả dụng và cú pháp phụ thuộc OS/kernel/container; trong cloud managed services thường dùng metrics provider. Không tự capture toàn bộ packets chứa dữ liệu khách hàng ở production mà không có quyền/quy định bảo mật.

### 11.4. Network timeouts ở đâu?

Nên phân biệt:

- DNS resolution timeout.
- TCP connect timeout.
- TLS handshake timeout.
- Connection reset/idle eviction.
- Socket read timeout.
- DB client operation deadline.
- Database query timeout.

Một `SocketTimeoutException` không chứng minh packet loss; DB server chậm có thể làm client không nhận response trong thời hạn.

## 12. Giới hạn CPU: tổng CPU thấp vẫn có một lõi hoặc shard bị nghẽn

CPU xử lý:

- Parse/serialize requests.
- Query planning/execution.
- Document decoding/encoding, compression/encryption.
- Index maintenance.
- Hashing, filter/sort/aggregation.
- Compaction orchestration.
- Replication/consensus.
- JVM GC/JIT và scheduler overhead.

### 12.1. CPU utilization theo từng core

Máy 16 cores có tổng CPU utilization 30% nhưng một thread tuần tự sử dụng **một core 100%**:

~~~text
Core 0: 100%
Core 1–15: mostly idle
Average CPU: can still look low
~~~

Nếu một critical event loop hoặc lock owner đơn luồng saturated, thêm connections không làm nó chạy song song.

### 12.2. CPU quota và throttling trong containers

Pod có CPU limit 1 vCPU trên node 32 cores. Node-level CPU average rất thấp, nhưng pod có thể bị **CFS bandwidth throttling** vì sử dụng hết quota.

Dấu hiệu:

- Container CPU gần limit.
- `container_cpu_cfs_throttled_*` metrics tăng theo cgroup mode.
- p99 tăng trùng throttling periods.
- Host còn nhiều cores rảnh.

**CPU 40% của node không bác bỏ CPU saturation trong một container.**

### 12.3. Runnable queues

Một OS run queue dài và CPU cores đều bận là dấu hiệu CPU demand vượt khả năng phục vụ. Nhưng load average trên Linux có thể gồm cả tasks chờ uninterruptible I/O, không thuần CPU. Cần đo thêm per-core utilization và scheduler/cgroup data.

### 12.4. CPU cao trong Java client hay DB server?

Nếu app CPU cao và DB server CPU thấp:

- JSON mapping/serialization.
- Regex/validation.
- DTO conversion.
- Compression.
- Query result sorting/filtering phía Java.
- Excessive retries/tracing/logging.

Nếu DB CPU cao nhưng app thấp:

- Scan/filter không có index.
- Many small queries.
- Aggregations/sort.
- Hot partition/coordinator.
- Read/write amplification.
- Replica/consensus work.

Xác định **process và stack** nào ăn CPU trước khi chỉnh cluster size.

### 12.5. Flame graph và CPU profiler

Java Flight Recorder (JFR) hoặc async-profiler (nếu môi trường cho phép) có thể chỉ ra hot methods. Linux `perf`/profiler của database có thể giúp bên server, với giới hạn quyền truy cập trên managed service.

Một flame graph biểu diễn **chi phí CPU trong samples**, không tự cho biết thời gian chờ I/O. Nếu request chậm vì blocked socket, CPU flame graph có thể ít tín hiệu; cần latency tracing và off-CPU profiling.

### 12.6. Tăng CPU không sửa query plan sai

Một query không có index trả 10 rows nhưng quét 20 triệu documents có thể ngốn CPU lớn; thêm CPU tăng throughput phần nào nhưng vẫn lãng phí resources. Thiết kế index/access pattern/partitioning thường mang lại hiệu quả lớn hơn scale CPU thuần.

### 12.7. Garbage collection cũng dùng CPU

GC có hai mặt:

- **Pause time:** Request threads bị dừng hoặc delay.
- **CPU time:** Collector tiêu thụ cycles/bandwidth, giảm capacity cho business work.

Muốn phân tích cần logs JFR/GC, allocation rate, heap occupancy và collection frequency, không chỉ CPU usage tổng.

## 13. Giới hạn CPU vì contention và hot partition

Không phải cứ CPU cao là cần nhiều cores. Một coordinator/hot partition có thể serial hóa writes theo khóa:

~~~text
1,000 clients -> key "inventory:sku-1"
                     |
               one hot partition
                     |
               CAS/lock/commit bottleneck
~~~

Những gì cần đo:

- Per-key/partition request distribution.
- LWT/CAS/transaction conflicts.
- Lock wait time.
- Server-side queue depth.
- p99 theo partition/node.
- Retries sau conflicts.

### 13.1. Một shard nóng làm cluster average “đẹp”

Giả sử 8 shards, chỉ một shard 100% CPU, bảy shard 20%:

\[
\text{Average}=\frac{100+7\times20}{8}=30\%
\]

CPU trung bình 30% nhưng những keys ở shard nóng có thể timeout hàng loạt.

### 13.2. Cách tối ưu phụ thuộc bất biến

- Hash/salt partition key phù hợp nếu không cần atomicity trên một key.
- Sharded counters nếu aggregate eventual value được phép.
- Batch updates hoặc rate limit theo hot key.
- Tối ưu index/sort và tránh fan-out.
- Một authoritative queue/serialization khi cần strict ordering.

Nếu inventory cuối cùng chỉ còn một sản phẩm, không được sharding một counter thành 100 eventual counters rồi coi đó là bảo đảm **không oversell**.

### 13.3. Tăng concurrency có thể giảm throughput

Một số requests có thể phải tranh lock, compaction, memory bandwidth hoặc storage. Tăng concurrency từ 100→1.000 có thể làm throughput hữu ích giảm vì context switching/retry/abort, dù attempts/s cao hơn.

### 13.4. CPU thấp không loại trừ lock contention

Nếu nhiều threads chờ một lock, CPU có thể thấp nhưng latency rất cao. Đo lock/monitor contention và transaction conflicts; đừng suy “thêm CPU” luôn giúp.

## 14. Giới hạn bộ nhớ: heap, cache, page cache và working set

RAM có nhiều vai trò trong pipeline NoSQL:

- Heap Java dành cho objects, buffers, caches và async tasks.
- Off-heap/direct memory dành cho network buffers, compression hoặc data structures.
- OS page cache giữ các pages/index/data đã đọc.
- Database-managed caches/buffer pools.
- Write buffers/memtables, compaction buffers, transaction metadata.
- Memory cho background replication, query execution, indexes.

**“Server có 64 GB RAM” không nói workload thật cần bao nhiêu.** Tốc độ truy cập dữ liệu phụ thuộc *working set* (dữ liệu được dùng tích cực), cache policy, truy vấn và kích thước footprint sau encoding.

### 14.1. Resident memory, heap và page cache không phải một

| Khái niệm | Ý nghĩa | Sai lầm dễ gặp |
| --- | --- | --- |
| JVM heap | Vùng objects do GC quản lý | Coi heap là toàn bộ RSS của Java |
| Off-heap/direct buffers | Memory ngoài Java heap | Bỏ sót khi phân tích OOM/container |
| RSS | Physical pages resident của process | Coi RSS cao là leak chắc chắn |
| OS page cache | File-backed cached pages | Coi “used RAM” luôn xấu |
| Database buffer cache | Cache do engine quản lý | Coi DB cache hit = toàn bộ index hit |
| Working set | Những bytes truy cập thường xuyên trong cửa sổ workload | Chỉ dựa tổng database size |
| Swap | Memory pages bị chuyển ra disk/other backing | Tin swap không ảnh hưởng tail latency |

Một process RSS 12 GB với Java heap 8 GB có thể hợp lý do direct buffers/metaspace/thread stacks/native memory; không nhất thiết có memory leak. Cần phân tích **memory breakdown**.

### 14.2. Working set quyết định cache effectiveness

Ví dụ:

~~~text
Database logical size: 2 TB
Frequently accessed hot set: 20 GB
Usable cache/page cache: 32 GB
~~~

Trong workload point reads có locality tốt, phần lớn requests có thể phục vụ bằng RAM dù dữ liệu tổng 2 TB.

Nhưng nếu chiến dịch làm hot set tăng lên 150 GB, cache miss tăng và storage I/O trở thành bottleneck. **Thêm CPU có thể không giúp** nếu CPU chủ yếu chờ disk/page faults.

### 14.3. Cache hit ratio cần hiểu denominator

Giả sử:

\[
\text{Cache hit ratio}=\frac{\text{cache hits}}{\text{hits + misses}}
\]

Tỷ lệ 99% nghe tốt, nhưng với 100.000 lookups/s thì **1.000 cache misses/s** có thể là đủ để làm disk random IOPS saturated. Cần nhìn **misses/s, latency của miss, read amplification, working set**, không chỉ phần trăm hit.

### 14.4. Database quá nhiều RAM cũng không cứu query shape xấu

Một query cần scan 20 triệu documents có thể tiêu thụ CPU/memory bandwidth rất lớn dù dữ liệu nằm trong RAM. Có thể cần index phù hợp, partition pruning, pagination hoặc thay access pattern, không chỉ tăng cache.

### 14.5. Cache thrashing

Nếu hai workloads dùng hai hot sets khác nhau và tổng lớn hơn cache:

~~~text
Interactive Order lookup hot set: 20 GB
Background full scan working set: 150 GB
Usable OS page cache:          32 GB
~~~

Background scan có thể đẩy những pages interactive vừa dùng ra khỏi cache. Kết quả interactive p99 tăng dù backend CPU trung bình không đổi.

Throttling/tách lịch scan, read-replica phù hợp và cache-aware scan policy có thể tốt hơn nâng pool size.

## 15. JVM memory pressure và garbage collection

Java application có thể tăng latency dù database thực thi nhanh.

### 15.1. Heap allocation rate

Ví dụ response trả 100.000 Orders rồi map thành hàng trăm nghìn temporary DTOs:

~~~text
Allocation rate: 2 GiB/s
Young GC: frequent
Old heap occupancy: rising
p99 pause spikes: 300 ms
~~~

Nếu request latency tăng trùng GC logs, cần giảm allocations/response fan-out, kiểm tra object retention và heap sizing; không phải chỉ tăng DB threads.

### 15.2. Memory leak khác tải cao tạm thời

Một memory leak có dấu hiệu:

- Live set sau GC tăng liên tục theo thời gian.
- Heap usage không trở về baseline sau traffic giảm.
- Retained objects tăng qua heap dumps/profiling.
- Off-heap/netty buffer usage tăng dù in-flight về 0.

Một spike bộ nhớ trong lúc chạy batch lớn có thể là **memory demand hợp lệ**, nhưng vẫn cần bounds. Đừng gọi mọi heap cao là leak.

### 15.3. Java heap không được chiếm hết container memory

Nếu pod limit 4 GiB, đặt `-Xmx4g` có thể không chừa chỗ cho:

- Metaspace.
- Thread stacks.
- Direct buffers.
- JIT/code cache.
- Native libraries.
- Kernel/container accounting.

Cgroup OOM killer có thể kill pod dù heap chưa báo Java `OutOfMemoryError`.

### 15.4. Phân biệt Java OOME và container OOMKilled

| Dấu hiệu | Gợi ý |
| --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | Heap không đủ/retained objects |
| `OutOfMemoryError: Direct buffer memory` | Direct memory pressure |
| Container terminated as `OOMKilled` | Tổng memory dưới cgroup/host limit vượt ngưỡng |
| High GC pause time but heap not exhausted | Allocation/collector pressure |
| Page faults/swap activity high | OS memory pressure/cold pages |

Việc xác nhận cần OS/Kubernetes/JVM metrics và logs cùng thời điểm.

### 15.5. Java Flight Recorder/JFR

Trong môi trường được phép, Java Flight Recorder có thể thu allocations, GC pauses, thread contention và socket I/O. Phải cấu hình profile/retention để không làm công cụ quan sát tạo thêm quá nhiều overhead hoặc thu dữ liệu nhạy cảm.

### 15.6. Garbage collector tuning đến sau profiling

Đổi G1/ZGC, heap size, pause target có thể hợp lý sau khi đo; nhưng nếu ứng dụng tạo 10 triệu objects vì N+1 queries và map quá nhiều kết quả, **sửa shape và allocations** thường bền hơn chỉ tinh chỉnh GC.

## 16. Memory trên NoSQL server: cache, memtables và compaction

NoSQL engine có thể dựa vào RAM để:

- Cache các index/data pages.
- Giữ memtables trước khi flush.
- Buffer writes trước commit/flush theo durability contract.
- Duy trì Bloom filters/metadata.
- Lưu aggregation/sort working sets.
- Thực thi compaction và compression.

### 16.1. Cache miss biến thành disk I/O

~~~text
Working set grows
  -> cache hit ratio declines
  -> more random reads
  -> disk read queue increases
  -> DB response latency rises
  -> app connections held longer
  -> pool wait increases
~~~

Ở đây dấu hiệu app pool wait **không phải nguyên nhân ban đầu**. Nếu tăng connection pool, bạn có thể tạo thêm random reads và làm disk tệ hơn.

### 16.2. Memory pressure gây compaction/write stalls

Với LSM-based databases, write buffers/memtables cần flush ra SSTables. Nếu flush/compaction không theo kịp tốc độ writes, engine có thể throttle/stall writes. Triệu chứng có thể hiện như memory pressure, disk I/O hoặc CPU compaction tùy stage.

### 16.3. Query spill

Một aggregation/sort lớn có thể vượt memory quota và spill xuống disk, làm p99 tăng mạnh. Nếu engine hỗ trợ disk spill, chỉ tăng RAM có thể giúp nhưng cũng cần **giảm cardinality, thêm index, pre-aggregate hoặc giới hạn query**.

### 16.4. Không cộng cache như thể tất cả dùng chung

Hai pods Java mỗi pod có cache 2 GiB không tự biến thành shared 4 GiB cache có locality tối ưu; cache fragmentation/coherence và invalidation có thể khiến hiệu quả thấp. Tương tự, database replica caches có thể giữ các hot keys khác nhau.

### 16.5. Native memory bên database

Nếu engine viết bằng Java/C++/Rust, cách quản lý heap/native memory khác nhau. Không lấy một chỉ số `heap used` làm bộ nhớ toàn bộ database. Cassandra có JVM heap và off-heap/OS page cache; MongoDB có WiredTiger cache và OS memory; Redis chú trọng in-memory datasets và eviction; mỗi sản phẩm có metrics riêng.

## 17. Quan sát bộ nhớ và paging

Một bộ chỉ số hữu ích:

~~~text
JVM:
  heap used/committed/max
  allocation rate
  GC pause time/count
  old-generation occupancy
  direct buffer usage
  thread count / stacks

Host/container:
  cgroup memory current/limit
  RSS
  page cache
  swap in/out
  major page faults
  OOM events

Database:
  cache hits/misses per second
  eviction rate
  dirty pages / write buffer size
  memory stalls / flush backlog
  query spill count
~~~

### 17.1. Linux commands để điều tra

Các lệnh minh họa trên host Linux có quyền quan sát:

~~~bash
free -h
vmstat 1
cat /proc/meminfo
ps -eo pid,rss,vsz,comm --sort=-rss
~~~

Giải thích:

- `free` báo cache/buffers, không chỉ còn RAM “free”.
- `vmstat` có thể cho thấy swap in/out, runnable và blocked tasks.
- RSS không tính toàn bộ shared memory/virtual address space theo một cách đơn giản.
- Metrics container/cloud có thể khác host.

### 17.2. Swap không phải cứ bằng 0 mới khỏe

Một chút swap sử dụng trong quá khứ chưa chứng minh hiện tại bị memory pressure. Điều quan trọng là **swap-in/out đang xảy ra khi tải cao**, major page faults và latency. Với database latency-critical, active swap thrashing có thể rất tệ.

### 17.3. OOM và retry storm

Nếu một pod OOM do buffer futures, Kubernetes restart nó; các requests lỗi bị gateway retry sang pods còn lại, làm chúng quá tải tiếp. Đây là dây chuyền **memory → application availability → retry → backend load**, không chỉ một lỗi heap cục bộ.

## 18. Giới hạn lưu trữ: IOPS, MB/s, queue depth và latency

Storage là nơi database lưu persistent data, indexes, WAL/commit log, SSTables/segments hoặc snapshots. Hiệu năng storage không chỉ có “SSD hay HDD”, mà gồm:

- **Random IOPS**: operations/s với kích thước request phù hợp.
- **Sequential throughput**: MB/s hoặc GiB/s.
- **Per-operation latency**: p50/p95/p99 của read/write/fsync.
- **Queue depth**: Số I/O đang chờ/thực thi tại các tầng.
- **Read/write amplification**: Một logical operation tạo bao nhiêu physical I/O.
- **Tail latency**: Variability do GC của SSD, compaction, snapshot và noisy neighbors.
- **Durability cost**: WAL append/fsync, quorum acknowledgment.

### 18.1. IOPS và throughput là hai giới hạn khác nhau

Một thiết bị có giới hạn 20.000 IOPS và 400 MiB/s:

Với I/O 4 KiB:

\[
20\,000\times4\ \mathrm{KiB}
=78{,}125\ \mathrm{MiB/s}
\]

Đạt 20.000 IOPS nhưng throughput mới khoảng 78 MiB/s.

Với I/O 256 KiB:

\[
20\,000\times256\ \mathrm{KiB}
=5000\ \mathrm{MiB/s}
\]

nhưng thiết bị chỉ cho 400 MiB/s, nên throughput limit chạm trước IOPS. **IOPS advertised không đảm bảo throughput vô hạn với request lớn**.

### 18.2. Random read vs sequential scan

Point lookup không có cache có thể cần random I/O tới index/data pages. Full scan đọc data tuần tự có thể bị giới hạn bởi MB/s nhiều hơn IOPS.

Hai workloads cùng “100 GB đọc” nhưng có latency/capacity rất khác vì **I/O size, locality, queue depth và cache hit rate**.

### 18.3. Queue depth và concurrency

Với storage device, một số queue depth có thể giúp khai thác parallelism; quá cao có thể làm tail latency tăng vì nhiều requests chờ. Không kết luận disk đang nghẽn chỉ từ một giá trị queue depth nếu chưa so latency và throughput.

### 18.4. Disk utilization là tín hiệu, không phải phép chứng minh một mình

`iostat %util≈100%` có ý nghĩa khác nhau trên HDD một queue so với NVMe nhiều queues. Cần nhìn cùng:

~~~text
read/write ops/s
MB/s
avg request size
await / read await / write await
queue depth
device saturation / throttling metrics
~~~

Không đọc `%util` đơn độc rồi kết luận disk “đã chạy hết 100% công suất” với mọi loại thiết bị.

### 18.5. Cloud storage có provisioned limits

Managed block storage có thể giới hạn:

- Volume IOPS.
- Volume throughput.
- Instance bandwidth tới volume.
- Burst credits.
- Per-volume queue depth.

Một volume được cấu hình 20.000 IOPS nhưng VM có giới hạn bandwidth nhỏ hơn vẫn không đạt số đã provisioned. Dùng metrics provider để xác định limit thực.

## 19. WAL, fsync và độ bền của write

Một write có thể gồm:

~~~text
Receive mutation
   -> validate/condition
   -> append WAL / commit log
   -> optional fsync / durable log confirmation
   -> update memory structures
   -> send ACK
   -> background flush/compaction
~~~

**Thứ tự và ACK contract khác nhau theo engine và write concern/durability mode**. Không suy mọi write ACK đều đã fsync xuống local SSD và được nhân bản tới quorum.

### 19.1. Fsync latency ảnh hưởng p99 write

Nếu một durability mode yêu cầu synchronous fsync, tail latency của storage có thể đi thẳng vào write response. CPU/heap thấp vẫn có writes chậm.

### 19.2. Group commit giảm chi phí bình quân

Một số engines gom nhiều log writes cho một fsync/group commit. Throughput có thể tăng khi batching, nhưng batch interval và sync behavior cũng ảnh hưởng latency. Không thay durability setting chỉ để benchmark nhanh hơn nếu làm mất yêu cầu dữ liệu.

### 19.3. RAID/replication không miễn phí

Write amplification có thể đến từ replication/quorum, indexes, WAL và compaction. Ba replicas không có nghĩa đúng 3 lần local disk I/O trong mọi schema/engine, nhưng **logical write thường làm nhiều physical work hơn một lần ghi đơn giản**.

### 19.4. Disk latency và network quorum

Write quorum chậm có thể do một replica có disk fsync chậm **hoặc** network path tới replica ấy chậm. Cần phân tích mỗi replica trong critical path; coordinator p99 tự nó không phân biệt được.

## 20. LSM trees và compaction: vì sao write nhanh rồi bất ngờ chậm

Nhiều NoSQL databases dùng LSM-like structures. Một write ban đầu có thể ghi vào memory/log nhanh, rồi background flush tạo sorted files; compaction hợp nhất files và dọn dữ liệu cũ.

~~~mermaid
flowchart LR
    W["Writes"] --> WAL["WAL / commit log"]
    W --> MEM["Memtable / write buffer"]
    MEM --> FLUSH["Flush to SSTables"]
    FLUSH --> L0["L0 files"]
    L0 --> CMP["Compaction"]
    CMP --> L1["Lower levels"]
    CMP --> IO["Read + write IO / CPU"]
~~~

### 20.1. Write amplification

Một logical 1 KiB write có thể khiến nhiều bytes được ghi theo thời gian vì WAL, SSTable flush, index maintenance và compactions. **Write amplification factor** cần được hiểu theo metrics/engine cụ thể; không mặc định một số cố định.

### 20.2. Read amplification

Nếu dữ liệu trải nhiều files/levels và cache không đủ, point lookup có thể phải kiểm tra nhiều file/block/index structures. Bloom filters/index metadata giúp giảm phần I/O trong nhiều engines nhưng không loại bỏ hoàn toàn.

### 20.3. Compaction backlog

Dấu hiệu:

- Pending compaction tasks tăng.
- SSTable/file count/L0 files tăng.
- Disk read/write throughput cao.
- p99 writes tăng hoặc hệ throttle writes.
- CPU compaction threads bận.
- Storage free space giảm tạm trong compaction.

### 20.4. Tombstones và TTL

Delete/TTL trong hệ LSM có thể tạo tombstones chứ không xóa ngay mọi bản cũ trên disk. Range queries quét nhiều tombstones có thể tốn CPU và I/O. Repair/compaction/retention phải phối hợp với consistency để tránh resurrect dữ liệu bị xóa.

### 20.5. Không tắt compaction vì “nó ăn I/O”

Compaction backlog kéo dài có thể làm read amplification và write stalls tệ hơn. Điều tiết rate/threads/schedule cần dựa vào measurements và product docs; tắt hoàn toàn để benchmark ngắn có thể che debt bùng phát sau đó.

## 21. Storage capacity, free space và snapshot/backup

Không phải lúc nào disk chỉ bị giới hạn bởi tốc độ. Một số tình huống:

- Volume gần đầy làm compaction/snapshot không còn space làm việc.
- Backup/chụp snapshot gây read/write pressure.
- WAL/CDC retention giữ logs lâu vì consumer lag.
- Disk fragmentation hoặc filesystem housekeeping.
- Networked storage đang throttled.

### 21.1. Capacity và performance ảnh hưởng nhau

Một SSD/managed volume gần giới hạn dung lượng hoặc quota có thể giảm hiệu năng tùy sản phẩm. LSM compaction có thể cần **temporary free space** vượt dung lượng logical live data. Không chỉ tính tổng record bytes.

### 21.2. Backup chạy trong giờ cao điểm

Nếu p99 tăng đúng lúc snapshot/backup, xem:

- Read/write bandwidth bị chia sẻ.
- Page cache thrashing.
- Copy-on-write overhead.
- Compaction overlap.
- Network egress.

Không mặc định “backup chỉ đọc nên không ảnh hưởng write latency”.

### 21.3. Chia lưu trữ theo loại I/O

Một số hệ đặt WAL/commit log riêng với SSTables/data để giảm contention, nhưng còn tùy engine/operational complexity. Trước khi đổi volume, xác minh **hot path đang nghẽn ở loại I/O nào**.

## 22. Quan sát storage trong Linux và cloud

Ví dụ công cụ ở môi trường Linux có quyền:

~~~bash
iostat -x 1
pidstat -d 1
vmstat 1
df -h
~~~

Những thứ cần nhìn:

- `r/s`, `w/s` hoặc tương đương.
- `rkB/s`, `wkB/s`.
- `await`, `r_await`, `w_await`.
- Queue depth và device stats.
- Per-process I/O nếu khả dụng.
- Disk space và inode capacity.
- Cloud volume IOPS/throughput/throttling metrics.

Các cột/cách tính phụ thuộc bản `sysstat`, kernel và loại storage; ở container có thể không thấy đúng device chứa persistent volume. **Kết hợp thông số block-device với DB metrics**, không chẩn đoán chỉ từ một `iostat`.

### 22.1. Phân biệt page cache read và disk read

Application thấy 100.000 logical reads/s nhưng disk chỉ 100 IOPS có thể là do cache hit tốt. Nếu cache miss tăng, disk IOPS có thể tăng đột ngột mà logical QPS không đổi.

### 22.2. Storage nhanh hơn không giảm mọi latency

Nếu DB query CPU-bound do parse/filter hoặc app pool wait 400 ms, nâng SSD giảm server disk I/O 2 ms có thể không tạo thay đổi đáng kể cho HTTP p99.

### 22.3. Managed NoSQL không luôn có số liệu disk trực tiếp

Với cloud database ẩn storage layer, dịch vụ có thể chỉ công bố **consumed read/write units, throttled operations, service latency, partition hotness, storage quota**. Cần suy từ các counters được hỗ trợ, không giả định có quyền `iostat` trên managed nodes.

## 23. Chẩn đoán NoSQL phải nhìn theo kiến trúc từng engine

Cùng hiện tượng “read p99 tăng”, các engine có **đường truy cập dữ liệu và chỉ số khác nhau**. Không áp máy móc bộ metrics của MongoDB sang Redis hoặc DynamoDB.

### 23.1. MongoDB: query plan, cache, pool và replication

Những tín hiệu nên xem:

- Slow operations và profiler metrics theo query shape.
- `explain()` / execution stats: số keys/docs được xét so với số trả về.
- Index usage, blocking sort, aggregation/spill behavior.
- WiredTiger cache statistics, eviction pressure (khi phù hợp).
- Server CPU/per-core và disk I/O.
- Connections/current operations trên server.
- Java driver connection pool wait/check-out timing.
- Replica read preference, majority/read/write concerns.

Ví dụ `keysExamined=1.000.000`, `docsExamined=1.000.000`, `nReturned=10` là dấu hiệu query shape/index có vấn đề; nhưng cần xem semantics của pipeline, sort/filter/index để chọn giải pháp.

**Không kết luận** chỉ vì `docsExamined/nReturned` lớn thì bắt buộc thêm index: aggregation/fan-out/analytics scans có thể có mục đích hợp lệ.

Nếu chỉ một collection/shard nóng, tăng toàn cluster pool connections có thể đẩy thêm công việc vào cùng shard.

### 23.2. Cassandra/ScyllaDB: partition distribution, tombstones và compaction

Những tín hiệu:

- Read/write latency theo node/coordinator.
- Pending compactions, flush backlog, SSTable distribution.
- Tombstone scanning/counters.
- Read repair/consistency overhead theo version.
- Hot partition/key distribution, token ownership.
- Pending requests, request timeout/retry/speculative execution.
- JVM heap/GC và off-heap/memory pressure (nếu engine dùng JVM).
- Disk I/O và network cross-node.

Một CQL query không cung cấp đủ partition key có thể gây fan-out/range scan không phù hợp với access pattern; một partition khổng lồ có thể tạo read amplification và load imbalance.

Đổi consistency level hoặc bật speculative execution để “giảm p99” có thể **tăng số RPC attempts, network traffic và work ở replicas**. Đọc chính xác policy/driver version trước khi chỉnh.

### 23.3. Redis: in-memory không có nghĩa mọi operation O(1)

Redis thường lưu active dataset trong memory, nhưng:

- Một command trên collection/key lớn có thể dùng CPU lâu và ảnh hưởng latency của commands khác tùy execution model/version.
- Network bandwidth có thể trở thành bottleneck khi trả payload lớn.
- Eviction hoặc expiration work có thể tạo CPU/memory overhead.
- Persistence AOF/RDB có thể tiêu thụ I/O, CPU và bộ nhớ copy-on-write.
- Slow clients, output buffers và Pub/Sub/blocking modes có thể tiêu hao memory/connection resources.
- Cluster hot key có thể nghẽn một shard dù tổng cluster nhẹ.

Không suy “Redis nhanh nên DB latency không bao giờ là lỗi”. Theo dõi command latency, slowlog, key size, memory fragmentation, eviction, connected clients, network, persistence stats và per-shard distribution.

### 23.4. DynamoDB: hot partition và capacity throttling

Với managed DynamoDB, những giới hạn thường thể hiện qua **throttling**, consumed read/write capacity, partition key distribution và SDK client transport:

- Table/index capacity mode và provisioned/on-demand contract.
- Hot partition key.
- Query vs Scan: Scan có thể đọc nhiều data hơn cần thiết.
- Strong vs eventually consistent reads theo API.
- Transaction write cost.
- Item size và request count.
- SDK retry attempts/HTTP pending acquisition.
- Per-operation p99/server-side latency metrics.

Tăng `maxConcurrency` của HTTP client khi table/index đang throttled có thể chỉ tăng attempts và tail latency. Cần tìm **throttling reason, hot key, query shape và capacity/quota**.

### 23.5. Elasticsearch/OpenSearch như NoSQL search engine

Đối với read model/search workload:

- Search/query thread pool rejections và queues.
- Lucene segments, merge/refresh work.
- JVM heap, shard/cache, fielddata/aggregation memory.
- Disk watermark/free space.
- Hot shards hoặc quá nhiều small shards.
- Search vs indexing workload contention.

Thêm shards không luôn tăng throughput; quá nhiều shards có thể tăng coordination/heap overhead. Tùy nhu cầu, sửa mappings, shard sizing, refresh policy hoặc query design.

### 23.6. Cosmos DB / managed document stores

Các dịch vụ có thể công bố request units (RU), throttling, partition hotness và latency thay vì disk IOPS thực:

- RU consumption vs allocated budget.
- 429 throttles và SDK retry delay.
- Logical partition key skew.
- Cross-partition queries.
- Indexing policy và payload size.
- Client network region placement.

Khi trả 429/threshold pressure, phải xem **công việc nào tiêu hao budget** và client retry semantics, không suy server CPU/disk theo cách ứng dụng tự quản.

## 24. Phân biệt saturation theo vị trí bằng độ trễ phân rã

Một trace có thể ghi:

~~~text
Trace R100:
  request_received                    t=0ms
  admission_granted                   t=5ms
  driver_call_submitted               t=7ms
  connection_acquired                 t=287ms
  request_sent                        t=289ms
  first_response_byte                 t=306ms
  entire_response_received            t=318ms
  http_response_serialized            t=322ms
~~~

Khoảng đáng chú ý là **driver submitted → connection acquired = 280 ms**. Nhưng cần xác định pool wait do:

- Pool cấu hình nhỏ.
- Connection leak.
- Một replica/pool bất thường.
- Network connect hoặc auth stall.
- DB operations giữ connection lâu.

Một trace cho thấy **điểm chờ**, chưa tự chứng minh nguyên nhân sâu hơn.

### 24.1. Tracing mẫu

~~~mermaid
flowchart LR
    HTTP["HTTP span: 322ms"] --> AD["Admission: 5ms"]
    HTTP --> SDK["DB client span: 311ms"]
    SDK --> POOL["Pool wait: 280ms"]
    SDK --> RPC["RPC/network+server: 29ms"]
    HTTP --> SER["Serialize: 4ms"]
~~~

Con số chỉ minh họa; spans có thể **chồng thời gian**, không phải mọi span durations cộng lại đúng HTTP duration. Ví dụ async tasks, retries hay fan-out làm một đoạn trace có nhiều branches song song.

### 24.2. Một quy tắc phân tích latency khi có parallel operations

Nếu request chạy:

~~~text
DB call A: 100ms
DB call B: 300ms
DB call C: 200ms
~~~

cùng lúc, critical path đóng góp khoảng **300 ms**, không phải 600 ms, nếu tất cả bắt đầu và kết thúc trong cùng cửa sổ, không có blocking dependencies.

Nếu sequential, tổng có thể gần 600 ms. Do đó phải xem **dependency graph**, không cộng mọi span.

### 24.3. Histogram và percentile aggregations

Đừng lấy trung bình của p99 từ 10 pods để gọi đó là p99 toàn service. Percentile không cộng/tính trung bình đơn giản. Cần histogram/quantiles được tính từ **phân phối gộp có trọng số** hoặc một hệ đo hỗ trợ aggregation đúng.

### 24.4. Metrics source-to-source cần clock sync

Nếu app và DB ở các hosts khác nhau, so `timestamp end - timestamp start` có thể sai do clock skew. Ưu tiên elapsed durations đo trong một process, trace spans có clock correction/uncertainty và đối chiếu cùng source progress.

## 25. Benchmark đúng: workload phải đại diện

Một benchmark đo “100.000 operations/s” có thể không mang ý nghĩa cho ứng dụng nếu:

- Dataset chỉ 10.000 documents, tất cả nằm trong cache.
- Request dùng một key cố định nhưng production có skew phức tạp.
- Chỉ đo point GET, không có writes, transaction hay scans.
- Không tính retries/errors hoặc latency timeout.
- Load generator bị CPU saturated và không tạo đủ arrivals.
- Mỗi client dùng `maxPoolSize` khác production.
- Benchmark chạy trong cùng AZ còn production cross-region.
- Dữ liệu không có TTL/tombstones, indexes và compaction debt như thực.

### 25.1. Các chiều phải mô tả

| Chiều | Ví dụ |
| --- | --- |
| Workload mix | 70% point read, 20% write, 10% range read |
| Key distribution | Uniform, Zipf-like, hot tenants |
| Record sizes | 1 KiB median, p99 100 KiB |
| Dataset footprint | 1 TB logical, 50 GB hot set |
| Concurrency/arrival | 100→5.000 requests/s |
| Consistency | Quorum/majority/eventual theo operation |
| Read/write ratios | Khác giờ cao điểm |
| Retry behavior | SDK retry modes và max attempts |
| Number of client pods | Có rollout overlap |
| Topology | Single AZ, multi-AZ, cross-region |
| Target SLO | Useful throughput, p99, error budget |
| Durability | WAL/fsync/ack contract |

### 25.2. Synthetic workload và production traces

Synthetic workload tốt để kiểm soát biến, nhưng production traffic có cache locality, key skew và burst patterns khó mô phỏng. Có thể phân tích traces đã **ẩn danh/giảm dữ liệu nhạy cảm** để xây test distribution.

### 25.3. Không đưa dữ liệu cá nhân vào load test

Chạy synthetic/anonymized data ở môi trường được cấp phép. Production replay cần kiểm soát privacy, side effects và access rights; không cho load generator phát lại lệnh thanh toán/đặt hàng thật một cách vô ý.

## 26. Open-loop và closed-loop load generation

Hai cách tạo tải có bản chất khác:

### 26.1. Closed-loop

Client có N workers; worker gửi request, chờ response rồi gửi request tiếp:

~~~text
send -> wait -> receive -> send -> wait ...
~~~

Khi server chậm, mỗi worker gửi requests **ít hơn**. Arrival rate tự giảm, có thể che saturation và tạo biểu đồ “p99 không quá tệ” vì số requests đến đã giảm.

### 26.2. Open-loop

Load generator phát requests theo một **arrival schedule độc lập tương đối với completion**, đến một giới hạn an toàn của test:

~~~text
Every 1ms schedule request
regardless of previous requests' completion
~~~

Khi server chậm, hàng đợi/saturation/rejection thể hiện rõ. Cần giới hạn tài nguyên generator, number in-flight và test stop conditions để không gây outage ngoài phạm vi kiểm soát.

### 26.3. Coordinated omission

Nếu generator chỉ đo một request sau khi request trước kết thúc, nó có thể **bỏ qua những thời điểm lẽ ra yêu cầu phải được phát nhưng bị trì hoãn vì hệ chậm**. Đây là vấn đề **coordinated omission**, làm latency histogram trông tốt hơn trải nghiệm arrivals thực.

Khi dùng workload generator, cần biết nó:

- Tạo arrivals theo schedule nào.
- Ghi latency từ lúc scheduled hay chỉ lúc thực sự send.
- Xử lý timeout và requests không hoàn thành ra sao.
- Có correction/explicit queue wait recording không.

### 26.4. Không biến benchmark thành DDoS nội bộ

Open-loop test phải có approvals, quota, bounded inflight và rollback, đặc biệt với managed cloud services. Mục tiêu là đo **capacity và failure mode**, không phá service production.

## 27. Warm-up, cold cache và đo đúng thời gian

Một hệ mới khởi động có thể chậm do:

- JVM JIT compilation.
- Driver topology discovery/TLS connections.
- Empty application cache.
- Cold DB buffer cache/page cache.
- Cold remote storage caches.
- Background index/cache population.

Một hệ chạy lâu có thể chậm vì:

- Compaction backlog.
- Heap leak/GC.
- Data growth.
- Hot partition shifts.
- Network congestion.

### 27.1. Hai phép đo bổ sung

**Cold benchmark:** Trạng thái vừa khởi động hoặc cache cold theo thủ tục tái lập được.

**Warm steady-state benchmark:** Sau khi warm-up kết thúc và throughput/latency ổn định.

Phải báo rõ kết quả thuộc trường hợp nào; không lấy warm-cache p99 làm cam kết cho recovery sau failover.

### 27.2. Soak test

Chạy tải trong thời gian đủ dài để lộ:

- LSM compaction debt.
- Log accumulation/TTL.
- Memory leak.
- Connection leak.
- Long-period GC.
- Storage burst-credit depletion.

Benchmark 30 giây có thể trông tốt nhờ cache và credits, rồi p99 xấu sau 30 phút.

### 27.3. Concurrency sweep

Giữ dataset/query mix/consistency cố định, thử nhiều mức in-flight:

~~~text
8, 16, 32, 64, 128, 256 operations
~~~

Ghi:

- Useful throughput.
- p50/p95/p99.
- Error/retry rate.
- Pool wait.
- DB CPU per-core.
- Disk read/write queue.
- Network usage.

Tìm “đầu gối” nơi throughput không tăng tương xứng nhưng latency/errors tăng nhanh.

### 27.4. Bảng thí nghiệm minh họa

| In-flight limit | Useful ops/s | p99 | Errors |
| ---: | ---: | ---: | ---: |
| 8 | 500 | 32 ms | 0% |
| 16 | 850 | 45 ms | 0% |
| 32 | 1.120 | 65 ms | 0% |
| 64 | 1.180 | 180 ms | 0.5% |
| 128 | 1.160 | 630 ms | 3% |
| 256 | 1.010 | 2.100 ms | 9% |

Giả sử các số minh họa cùng workload, limit 32 có thể phù hợp hơn 64–256 nếu SLO p99 nhỏ hơn 100 ms. **Tối ưu useful throughput trong SLO**, không tối đa attempts hoặc in-flight.

## 28. Có nhiều bottleneck: kiểm tra bằng thay đổi một biến

Giả sử:

~~~text
Normal:
  DB p99 = 60ms
  App pool wait p99 = 10ms

Peak:
  DB p99 = 300ms
  App pool wait p99 = 500ms
~~~

Bạn cần biết DB chậm làm pool wait tăng, hay pool quá nhỏ khiến requests chờ rồi DB metrics p99 khác.

### 28.1. Thí nghiệm A — Giảm tải ứng dụng 30%

Nếu DB p99 giảm từ 300→70 ms, disk queue giảm và pool wait giảm 500→20 ms, đây là bằng chứng **backend saturation** đang gây chuỗi chậm.

### 28.2. Thí nghiệm B — Tăng pool trong giới hạn an toàn

Nếu pool wait giảm nhưng DB p99 tăng 300→700 ms, useful throughput không tăng, tức pool cũ đang vô tình làm backpressure; tăng pool làm backend quá tải hơn.

### 28.3. Thí nghiệm C — Giảm query fan-out

Nếu thay 100 per-item lookups thành một batch/query phù hợp làm RTT trips giảm 10 lần và CPU/IO giảm, nguyên nhân có thể là **application access pattern** gây áp lực cả mạng/backend.

### 28.4. Thí nghiệm D — Đọc đúng từ cache

Nếu point reads chậm khi data cold nhưng nhanh rõ khi warm, cùng CPU/RTT, và storage queue tăng ở cold state, nghi vấn nằm ở **memory/cache–storage interaction**.

### 28.5. Không đánh đồng tương quan với nguyên nhân

CPU tăng cùng latency có thể vì **retry storm do network** (CPU chỉ là hệ quả); disk IO tăng cùng latency có thể vì **cache miss do scan job**. Cần trace thứ tự xuất hiện, controlled test và throughput ở critical path.

## 29. Baseline và cách báo cáo kết quả đo

Một báo cáo nên nêu:

~~~yaml
experiment:
  purpose: "Find useful throughput under p99 SLO"
  environment: "staging-like topology"
  applicationPods: 8
  clientDriverVersion: "recorded in run metadata"
  databaseVersion: "recorded in run metadata"
  consistencyMode: "documented"
  requestMix:
    pointReadPercent: 75
    writePercent: 20
    rangeReadPercent: 5
  dataset:
    logicalSizeGiB: 500
    hotSetGiB: 40
    keyDistribution: "zipf-like"
  load:
    mode: "open-loop bounded"
    targetArrivalRatePerSecond: 2000
  durationMinutes: 30
  metrics:
    - usefulThroughput
    - p50
    - p95
    - p99
    - timeouts
    - retries
    - poolWait
    - cpuPerCore
    - memoryGc
    - diskIoLatency
    - networkRetrans
~~~

Đây là **mẫu metadata**, không phải config chạy được của một tool cụ thể.

### 29.1. Không bỏ lỗi khỏi histogram

Một benchmark có 10% requests timeout sau 3 giây nhưng chỉ tính latency của 90% successes có thể cho p99 trông đẹp. Báo success latency và timeout distribution **cùng error rate**, ghi rõ treatment của requests không hoàn tất.

### 29.2. Sample count

p99 dựa trên ít observations sẽ nhiễu. Nếu chỉ 100 requests, p99 gần cực trị và khó suy tail. Chạy thời gian đủ dài, lặp trials và báo độ biến thiên/độ tin cậy phù hợp; không khẳng định khác biệt 2 ms giữa hai p99 là chắc chắn khi noise lớn.

### 29.3. Benchmark đang chạy có ảnh hưởng không?

Metrics collection, debug logging, heavy profiler, verbose tracing cũng có overhead. Khi cần profile sâu, dùng canary/sampling và ghi rõ cấu hình đã bật; không đo throughput production trong cùng lúc bật logging từng document mà không tính chi phí.

## 30. Runbook: p99 đột ngột tăng, bắt đầu ở đâu?

Giả sử lúc 14:20, Order API p99 tăng từ 120 ms lên 1.400 ms, errors từ 0,1% lên 4%.

### Bước 1 — Xác nhận phạm vi ảnh hưởng

Hỏi:

- Chỉ một endpoint hay tất cả routes?
- Chỉ writes hay reads, một tenant hay toàn bộ?
- Một region/AZ hay nhiều nơi?
- Một phiên bản app vừa deploy hay database cũng thay đổi?
- p50 tăng hay chỉ p99? Có timeout, 429 hoặc 503 không?
- Logical QPS tăng thật hay chỉ **DB attempts/s** tăng?

Không vội tăng pool/timeout khi chưa biết mẫu ảnh hưởng.

### Bước 2 — Tách thời gian ở ứng dụng

Đo:

~~~text
HTTP ingress -> admission
admission -> executor start
executor start -> DB call submit
DB call submit -> connection acquired
connection acquired -> DB response
DB response -> serialized HTTP response
~~~

Nếu HTTP latency cao mà DB server execution vẫn thấp, nghi application queue/pool/serialization hoặc network trước; không suy database server là bottleneck.

### Bước 3 — Nhìn RED và USE cùng lúc

Lập bảng theo giai đoạn before/after:

| Chỉ số | Trước | Sau | Giả thuyết |
| --- | ---: | ---: | --- |
| Useful requests/s | 2.000 | 1.650 | Capacity hữu ích giảm |
| DB RPC attempts/s | 2.100 | 4.700 | Retry amplification |
| HTTP p99 | 120 ms | 1.400 ms | Tail tăng mạnh |
| App pool pending | 5 | 300 | Queue ở client |
| DB disk read p99 | 6 ms | 90 ms | Storage/cache pressure |
| Server CPU average | 40% | 45% | Không bác bỏ hot shard |

Các giá trị minh họa cho thấy cần kiểm tra **cache miss/storage trước**, không chỉ nới pool.

### Bước 4 — Tìm tài nguyên bão hòa đầu tiên

Xem timeline:

~~~text
14:18 Cache miss rate rises.
14:19 Disk read queue rises.
14:20 DB p99 rises.
14:20 App pool wait rises.
14:21 SDK retries rise.
14:22 HTTP errors rise.
~~~

Thứ tự này **ủng hộ** giả thuyết dữ liệu cold/cache thrash dẫn tới storage saturation rồi lan lên app. Vẫn cần xác minh workload nào làm miss rate tăng, chứ không kết luận tuyệt đối từ tương quan.

### Bước 5 — Giảm tải an toàn

Tùy nghiệp vụ:

- Tạm dừng/throttle background scans và reindex.
- Giảm SDK retries hoặc dùng circuit breaker với budget.
- Hạn chế concurrency tại ứng dụng để bảo vệ backend.
- Bật bounded admission/load shedding, tránh queue vô hạn.
- Không retry mù writes có unknown outcome.
- Giữ các critical operations theo priority/tenant quota đã công bố.

### Bước 6 — Xác minh recovery

Sau can thiệp:

- Useful throughput phục hồi.
- DB p99, disk queue và app pool wait giảm.
- Error/retry rate trở lại baseline.
- Không xuất hiện bottleneck mới, ví dụ network egress.
- Các writes bị timeout đã được đối soát theo idempotency/ledger.

### Bước 7 — Hậu kiểm có thể hành động

Ghi rõ **root cause có bằng chứng**, trigger, contributing factors, hành động ngắn hạn, fix dài hạn, dashboard/test thiếu gì và phương án rollback.

## 31. Cây quyết định chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["HTTP p99 / timeouts increase"] --> B{"DB client submitted? "}
    B -->|No| C["App queue, lock, executor, GC, serialization"]
    B -->|Yes| D{"Pool acquire wait high?"}
    D -->|Yes| E["Check pool sizing, leaked cursors, DB slow-held connections"]
    D -->|No| F{"Server execution time high?"}
    F -->|No| G["Network RTT, TLS, response size, tracing gaps"]
    F -->|Yes| H{"CPU hot per-core / quota?"}
    H -->|Yes| I["Query plan, CPU profiler, hot partition, contention"]
    H -->|No| J{"Cache miss / memory pressure?"}
    J -->|Yes| K["Working set, GC, page cache, eviction"]
    J -->|No| L["Disk IO queue, fsync, compaction, replica/network quorum"]
~~~

**Giới hạn:** Đây là sơ đồ **định hướng đo tiếp**, không phải thuật toán xác định root cause. Ví dụ DB server CPU thấp + disk queue thấp vẫn có thể bị lock contention, quotas, network replication hoặc managed-service throttling.

### 31.1. Đừng quyết định từ một metric snapshot

Một scrape 15 giây có thể bỏ những spike 100 ms gây p99. Histogram/trace samples với độ phân giải thích hợp giúp nhìn tail; hãy đối chiếu metric aggregation window và sampling.

### 31.2. Nhiều nguyên nhân đồng thời

Một service có thể vừa thiếu CPU quota trong pod vừa gặp storage compaction trên DB. Tối ưu một bên có thể chưa giảm p99 dưới SLO. Mục tiêu là tìm **critical path** và throughput hữu ích, không ép chọn chỉ một nhãn.

## 32. Case study A — Pool wait cao nhưng DB còn rảnh

**Bối cảnh:** 10 pods Java, mỗi pod pool max 20. Mỗi HTTP request gọi một point query trả 1 KiB, DB server median execution 4 ms.

~~~text
HTTP p99:                   600 ms
Driver pool acquire p99:   520 ms
DB server p99:              12 ms
DB CPU and disk:            low
Active client connections:  at configured max
Open cursors:               continuously increasing
~~~

### 32.1. Giả thuyết

Resource leak hoặc long-held cursors/sessions làm connections không trở về pool. Pool quá nhỏ là giả thuyết khác; cần phân biệt.

### 32.2. Kiểm tra

- Kiểm tra số cursors/sessions và tuổi đời.
- Đối chiếu thread dumps/driver checkout latency.
- Tìm code path không close iterator/transaction khi exception.
- Canaried fix close resources, giữ maxPoolSize không đổi.

### 32.3. Dự kiến kết quả nếu đúng

Open cursors trở về mức ổn định, pool pending giảm, HTTP p99 giảm trong khi DB server metrics gần như không đổi.

### 32.4. Điều không nên làm

Chỉ tăng pool max 20→200 mà không sửa resource lifecycle sẽ làm sự cố đến muộn hơn, đồng thời tăng số sockets lên database.

## 33. Case study B — Cross-region network latency

**Bối cảnh:** Java client được chuyển sang region khác; point reads vẫn dùng cùng query/index.

~~~text
Before:
  Client-DB RTT:   3 ms
  DB execution:    8 ms
  HTTP p99:       38 ms

After:
  Client-DB RTT:  85 ms
  DB execution:    9 ms
  HTTP p99:      280 ms
~~~

### 33.1. Giả thuyết

Round-trip count trên critical path hoặc thêm proxy/TLS connection setup qua region mới làm tăng client latency.

### 33.2. Thí nghiệm

- Chạy cùng query từ một canary gần DB và một canary xa DB.
- Ghi số DB RPCs/HTTP request và tách sequential vs parallel.
- Giữ query mix, dataset, server health và driver pool config tương đương.
- Kiểm tra retransmission/TCP RTT, connection reuse.

### 33.3. Thay đổi phù hợp

Đặt latency-sensitive service gần source hoặc thiết kế read model/replica phù hợp, giảm N+1 sequential calls, dùng batching khi domain cho phép. Đổi replication/read consistency phải đánh giá correctness.

### 33.4. Không làm

Nâng disk IOPS nếu server disk latency không thay đổi và 85 ms RTT mới là thành phần chính.

## 34. Case study C — CPU trung bình 30%, một shard timeout

**Bối cảnh:** 8 shards, 95% writes hướng về cùng tenant/key range.

~~~text
Cluster CPU average: 30%
Hot shard CPU:       100% per constrained core
Hot shard p99:       1,200 ms
Other shards p99:    15 ms
~~~

**Giả thuyết:** Hot partition hoặc single-core/lock serialization.

Kiểm tra partition-key distribution, query CPU/locks, per-core utilization, coordinator routing và retries.

**Biện pháp có điều kiện:** Partition redesign/salt/sharded counter nếu business cho phép, per-key rate limit, batching, aggregate ownership, tách hot tenants. **Không chỉ thêm random cluster nodes** nếu hot key không được phân tán và vẫn cùng một serialization point.

## 35. Case study D — Cold cache gây storage bottleneck

**Bối cảnh:** Sau khi import dữ liệu mới và chạy full scan, cache hit giảm.

~~~text
Before:
  Cache miss/s:       200
  Disk read IOPS:     400
  Disk await p99:      8 ms
  HTTP p99:           80 ms

After:
  Cache miss/s:     4,500
  Disk read IOPS:   8,000
  Disk await p99:     90 ms
  HTTP p99:        1,100 ms
~~~

**Giả thuyết:** Working set vượt cache hoặc scan thrashing gây random disk queue.

Kiểm tra recent workload mix, cache evictions, scan duration, per-shard read I/O, page faults và disk throughput/IOPS limits.

**Biện pháp:** Throttle/bypass cache cho scan nếu engine hỗ trợ đúng, tách analytics reads, tăng cache hữu dụng sau đo, index/access pattern tối ưu, nâng IOPS khi thật sự cần.

**Không nhầm:** Caches có thể ấm trở lại khiến issue giảm tạm; phải hiểu trigger để ngăn tái diễn.

## 36. Case study E — p99 tăng do GC trong Java

~~~text
DB server p99: 20ms -> 22ms
App Java GC pause p99: 10ms -> 350ms
App allocation rate: 0.4GiB/s -> 2.5GiB/s
HTTP p99: 80ms -> 480ms
~~~

Sự thay đổi gần như ở Java application. Kiểm tra:

- Endpoint mới trả quá nhiều rows.
- DTO object graph/JSON serializer.
- Heap live-set vs allocation.
- JVM GC logs/JFR.
- Async queues chứa nhiều large payloads.

Giảm response bytes/pagination, streaming có bounds, tránh tạo object vô ích, sau đó mới xem heap/collector tuning.

## 37. Case study F — Write p99 do WAL fsync và compaction

**Bối cảnh:** Bulk imports trong cùng giờ cao điểm.

~~~text
Write p99:                1,500 ms
WAL fsync latency p99:      280 ms
Pending compactions:        rising
Disk write throughput:      near provisioned cap
CPU average:                45%
~~~

**Giả thuyết:** Storage write throughput/fsync tail hoặc compaction debt.

Kiểm tra disk queue/await, dirty memtables, compaction pending, disk free, I/O limits, batch size và write concern.

**Biện pháp:** Điều tiết import, tăng write capacity phù hợp, chia giờ compaction/backup, tối ưu index/write amplification hoặc data model. Không nới write durability ACK để “sửa latency” mà không xét mất dữ liệu.

## 38. Case study G — Retry storm làm hệ tự gây quá tải

~~~text
Normal:
  logical operations/s:    2,000
  attempts per operation:  1.02
  DB attempts/s:          ~2,040

Failure:
  logical operations/s:    2,000
  attempts per operation:  2.8
  DB attempts/s:          ~5,600
~~~

Một số requests timeout ban đầu do network; SDK retry, service retry và gateway retry khuếch đại tải. Sau đó CPU/network/storage saturated và nhiều request timeout tiếp.

**Dấu hiệu:** Attempts/s tăng nhanh hơn logical QPS, errors/latency tăng, retry budget token bị cạn, upstream 5xx/503.

**Biện pháp:** Deadline shared, số attempts có giới hạn, backoff+jitter, circuit breaker/load shedding, phân loại lỗi transient vs business, idempotency cho writes.

### 38.1. Timeout sau write là unknown outcome

Client timeout không chứng minh DB không commit. Nếu write là `increment`, `decrement inventory` hoặc `capture payment`, retry mù có thể lặp side effect. Hiệu năng không thể tách khỏi **tính đúng dữ liệu** khi xét retry.

## 39. Case study H — Băng thông mạng chạm ngưỡng do scans/CDC

~~~text
NIC egress capacity:       2 Gbit/s
Observed egress:           near 2 Gbit/s
CDC transfer:              1.4 Gbit/s
Bulk export:               0.7 Gbit/s attempted
Point-read p99:            increases
DB CPU:                    moderate
~~~

Điều này gợi ý **egress/network bottleneck**, không phải CPU. Cần xem link/provider metrics, queue/drops, TCP retransmits và traffic classes.

**Biện pháp:** Throttle bulk exports, CDC compression/batching theo sản phẩm, traffic shaping hoặc tăng network provisioned bandwidth; xác minh CPU compression overhead không trở thành bottleneck mới.

## 40. Fault injection có kiểm soát

Một bộ thí nghiệm dùng dữ liệu giả và cluster/staging được cấp quyền:

| Thí nghiệm | Thay đổi có chủ đích | Quan sát | Kết luận mong đợi |
| --- | --- | --- | --- |
| Pool pressure | Giảm max pool của canary | Pending acquire, HTTP p99 | Phân biệt client queue với DB |
| App CPU quota | Giảm CPU limit canary | CPU throttling, event-loop lag | Phát hiện container CPU |
| GC stress | Tăng temporary allocations trong test | GC pause, allocation, p99 | Tách memory/JVM |
| Network RTT | Dùng network emulator trong lab | RTT, client p99, server execution | Tách round trips |
| Packet loss | Controlled packet loss lab | Retransmits, timeouts | Xác minh network resilience |
| Disk read throttle | Giảm storage IOPS lab | Disk queue, cache misses | Nhận diện storage |
| Compaction pressure | Bulk writes có giới hạn | Compaction queue/write stalls | Thấy sustained-load debt |
| Hot partition | Tập trung requests vào một key | Per-shard metrics | Nhận diện skew |
| Retry storm | Giả lập transient errors | Attempts/logical ops | Kiểm tra retry budget |
| Pod autoscale | Tăng pods trong lab | Pool sockets, DB throughput | Phân bổ global budget |
| Long-running scan | Chạy backup/reindex có hạn mức | Cache misses, bandwidth | Background interference |
| DB replica failover | Theo test topology | Reconnect, quorum p99 | High-availability behavior |

### 40.1. Không thử trên production tùy tiện

Fault injection với disk/network/node failure có thể ảnh hưởng nhiều tenants và gây mất availability. Dùng staging/dedicated test hoặc canary được phê duyệt, có phạm vi, thời gian và rollback rõ.

### 40.2. Phải thu cả thời gian phục hồi

Một hệ chịu lỗi tốt không chỉ có p99 lúc fault; quan trọng là **sau fault, retry backlog/compaction debt/pending queues có tiêu hết không**, resource leaks có xuất hiện không và dữ liệu có đúng không.

### 40.3. Data correctness trong benchmark write

Một benchmark write báo throughput 10.000/s nhưng 5% conditional conflicts bị tính là success có thể sai mục tiêu. Ghi rõ:

~~~text
accepted commands
successful committed mutations
conditional business conflicts
unknown outcomes
timeouts
retries
duplicates
~~~

Đối soát với database/ledger, đặc biệt sau failover hoặc ACK loss.

## 41. Mẫu dashboard và tracing cho Java–NoSQL

Một dashboard hữu ích nên có ít nhất bốn hàng:

### 41.1. Hàng A — Tác động đến người dùng (RED)

~~~text
HTTP logical RPS
Successful business ops/s
HTTP p50/p95/p99 by endpoint and status
5xx, 429, 503, timeouts, canceled requests
~~~

### 41.2. Hàng B — Ứng dụng và connection (USE)

~~~text
App CPU per pod + CPU quota throttling
JVM heap/direct memory + GC pause time
HTTP/executor queue depth, queue wait
Bulkhead in-flight / rejected
Driver pool active/idle/pending, acquire wait
DB attempts per logical operation
~~~

### 41.3. Hàng C — Mạng

~~~text
Client-DB RTT / connection setup latency
TCP retransmissions/reset/timeout
NIC bytes/s and drops
Cross-AZ/region traffic
Network egress credits or quotas if applicable
~~~

### 41.4. Hàng D — NoSQL backend

~~~text
Server throughput/latency by node/shard/partition
CPU per core / quota
Cache hits + misses/s
Heap / RSS / page cache pressure
Disk read/write IOPS, MB/s, queue and p99 latency
Compaction/flush backlog
Replication lag/quorum timeouts
Hot keys, read/write throttling and conflicts
~~~

### 41.5. Correlation between panels

Phải có cùng time range, deployment marker và source/region dimensions. Một biểu đồ `DB p99 tăng` và một biểu đồ `GC pause tăng` nhưng **lấy từ hai ứng dụng khác nhau** không đủ để kết luận causal link.

### 41.6. Tối thiểu các span

Một trace mẫu:

~~~text
HTTP GET /orders/{id}
 ├─ auth/session validation
 ├─ application queue/bulkhead
 ├─ DB client operation
 │   ├─ pool acquisition
 │   ├─ request attempt #1
 │   └─ optional retry attempt #2
 ├─ DTO mapping
 └─ HTTP serialization
~~~

Gắn `db.system`, operation type, source region, request attempt, retry reason, pool wait và result status theo chính sách OpenTelemetry/driver. Không nhét raw SQL/CQL chứa PII hoặc full document vào traces mặc định.

## 42. Công thức capacity planning: đừng nhân số pool một cách máy móc

Giả sử:

~~~text
NoSQL backend useful connection budget = 1,200
Reserved for batch/admin/monitoring     =   240
Application budget                     =   960
Maximum pods during rolling deploy     =    24
~~~

Một mốc phân bổ sơ bộ:

\[
\text{Per-pod budget}\le\left\lfloor\frac{960}{24}\right\rfloor=40
\]

Đó **không phải** khẳng định `maxPoolSize=40` là đúng trong mọi driver, vì:

- Driver có thể tạo pool **per server**, nhiều sockets/connection categories.
- HTTP/2 hoặc CQL multiplex cho phép nhiều operations trên một connection.
- Workload fan-out có thể gửi nhiều queries/shards.
- Một pod có nhiều client instances/SDKs.
- Deployment overlap có thể lớn hơn 24 pods.
- Connection limit không bằng IOPS/CPU/partition capacity.

### 42.1. Sizing in-flight theo Little’s Law

Nếu cần 3.000 useful DB operations/s và operation mean duration 20 ms:

\[
L=3000\times0{,}020=60
\]

Khoảng 60 operations in-flight trung bình trong **toàn scope đo**. Nếu 24 pods chia đều và workload không skew, mean per pod ~2,5 operations, nhưng peaks/tail/fan-out có thể cao hơn nhiều.

### 42.2. Sizing bandwidth theo payload

2.000 reads/s, mỗi response trung bình 64 KiB:

\[
2000\times65536=131\,072\,000\text{ bytes/s}
\]

Tương đương khoảng **1,05 Gbit/s** payload thô theo đơn vị decimal, trước overhead, retries và replication. Một NIC/link 1 Gbit/s có thể là bottleneck dù CPU và disk còn rảnh.

### 42.3. Sizing IOPS theo cache misses

50.000 logical point reads/s, 2% dẫn đến một random disk I/O 4 KiB:

\[
50\,000\times0{,}02=1000\ \mathrm{IOPS}
\]

Đây là đơn giản hóa; index/data layout có thể cần nhiều hơn một physical read mỗi miss. Nếu read amplification 5 I/O/miss:

\[
50\,000\times0{,}02\times5=5000\ \mathrm{IOPS}
\]

IOPS tính từ miss rate và amplification có thể hữu ích hơn chỉ nhìn database logical QPS.

### 42.4. Sizing CPU theo service demand

Một operation cần trung bình 0,5 ms CPU **trên một loại CPU/core tương đương**, 10.000 operations/s:

\[
10\,000\times0{,}0005=5\text{ CPU-seconds/second}
\]

Nghĩa là trung bình có **nhu cầu khoảng 5 cores bận liên tục**, giả sử hoàn toàn song song hóa được, không contention, overhead và đúng cách đo CPU time. Trong hệ thật cần headroom, per-core hot spots và CPU quotas.

### 42.5. Sizing retry traffic

2.000 logical DB operations/s, trung bình 1,5 attempts mỗi operation:

\[
2000\times1{,}5=3000\text{ attempts/s}
\]

Khi retry tăng, network/CPU/IO demand có thể tăng dù logical user traffic không đổi.

## 43. Bài tập thực hành

### Bài 1 — Dấu hiệu đầu tiên

Bạn có:

~~~text
HTTP p99:                 900ms
Pool acquire p99:        700ms
DB server p99:            20ms
DB CPU:                  15%
Open cursors:          rising
~~~

1. Bottleneck quan sát được ở đâu?
2. Ít nhất ba nguyên nhân cần kiểm tra?
3. Vì sao tăng storage IOPS chưa có cơ sở?
4. Thí nghiệm nào phân biệt pool quá nhỏ với resource leak?

### Bài 2 — Tính Little’s Law

Một source hoàn thành 3.500 operations/s, mean operation time in system là 24 ms.

1. Average operations trong scope đó?
2. Nếu p99=180 ms, có được thay 24 ms bằng 180 ms và gọi là Little’s Law không?
3. Nếu 40% thời gian là queue wait, có bao nhiêu work trung bình thực sự đang phục vụ, với các giả định đơn giản?
4. Khi queue tăng liên tục, cần thay đổi cách phân tích thế nào?

### Bài 3 — Logical throughput và retry

API tạo 1.200 logical DB reads/s, trung bình 2,4 attempts/read:

1. Tính DB attempts/s.
2. Nếu chỉ 900 reads/s thành công, useful throughput là bao nhiêu?
3. Có nên tăng retry limit từ 3 lên 10 không?
4. Những metrics nào chứng minh retry đang khuếch đại saturation?

### Bài 4 — CPU trung bình che hot core

Một node 16 cores có 1 core 100%, 15 cores 10%:

1. CPU trung bình?
2. Điều gì có thể khiến chỉ một core saturated?
3. Flame graph có giới hạn gì nếu bottleneck là off-CPU wait?
4. Vì sao tăng connection pool không giải quyết serialized critical path?

### Bài 5 — Container quota

Pod Java có CPU limit 1 vCPU trên host 32 cores. Host average CPU 20%, pod bị throttled nhiều.

1. Pod có thể CPU-saturated không?
2. Cần xem metrics nào?
3. Vì sao tăng host cores chưa chắc giúp?
4. Tại sao cần so p99 với throttling periods?

### Bài 6 — Round trips

Một endpoint thực hiện 5 DB calls tuần tự, mỗi call có một RTT khoảng 60 ms, DB execution mỗi call 5 ms:

1. Ước lượng tối thiểu thời gian network RTT?
2. Tổng thời gian chưa tính serialization/queue?
3. Nếu 5 calls song song, latency critical path thay đổi thế nào dưới giả định không có contention?
4. Nếu cần consistency mạnh, có thể bỏ một replica hop tùy ý không?

### Bài 7 — Bandwidth

Một CDC pipeline chuyển 20.000 events/s, mỗi event trung bình 8 KiB:

1. Tính raw bytes/s.
2. Chuyển sang Gbit/s.
3. NIC 1 Gbit/s có đủ cho payload raw chưa tính overhead không?
4. Nếu compression giảm bytes 50% nhưng tăng CPU 30%, cần đo gì?

### Bài 8 — RTT vs bandwidth

Point GET trả 1 KiB mất 200 ms khi cross-region, link chỉ dùng 5% bandwidth.

- Vì sao bandwidth không phải bottleneck hiển nhiên?
- Đề xuất synthetic test gần/xa database.
- Đường đi nào có thể thêm network hops?
- Có nên nâng SSD khi server execution vẫn 6 ms không?

### Bài 9 — Packet loss

Network retransmission tăng 10 lần, client timeouts tăng, DB CPU và disk ổn định.

1. Giả thuyết mạng nào hợp lý?
2. Vì sao ICMP ping chưa đủ?
3. Nên thu RTT, TCP retrans, NIC drops hay application spans thế nào?
4. Nếu socket timeout, có chắc network lỗi không?

### Bài 10 — Working set và cache

Database logical size 2 TB. Hot set tăng 30 GB→180 GB, usable cache 64 GB.

1. Vì sao cache misses có thể tăng dù DB size không đổi?
2. CPU có thể giảm/không tăng trong khi p99 tăng vì sao?
3. Muốn chứng minh storage pressure cần metrics nào?
4. Có giải pháp nào ngoài tăng RAM?

### Bài 11 — Cache hit ratio

100.000 logical reads/s, cache hit 99,5%. Mỗi miss tạo trung bình 4 physical random reads.

1. Tính cache misses/s.
2. Tính physical IOPS do misses.
3. Nếu cache hit giảm còn 95%, IOPS mới?
4. Vì sao cache hit ratio đơn lẻ che severity?

### Bài 12 — JVM memory

Pod memory limit 4 GiB, Java `-Xmx4g`, app dùng direct buffers và nhiều threads:

1. Vì sao có thể OOMKilled dù heap chưa đầy?
2. Khác biệt RSS, heap, off-heap?
3. Những metrics/logs nào cần?
4. Tại sao tăng connection pool có thể làm memory pressure nặng thêm?

### Bài 13 — Disk IOPS vs throughput

Volume cho 20.000 IOPS và 300 MiB/s:

1. 4 KiB random reads bị giới hạn nào trước ở 20.000 IOPS?
2. 256 KiB reads bị giới hạn nào trước?
3. Có thể suy tối đa operations/s từ throughput limit cho request 256 KiB không?
4. Vì sao disk `%util` không đủ để kết luận với NVMe?

### Bài 14 — WAL fsync

Write p99 tăng khi volume write latency p99 tăng, server CPU 40%, memory ổn.

1. Những đường nào đi qua WAL/fsync?
2. Tại sao CPU thấp không bác bỏ storage bottleneck?
3. `writeConcern`/durability ảnh hưởng ACK thế nào?
4. Có nên giảm durability chỉ để benchmark nhanh hơn?

### Bài 15 — Compaction

LSM store nhận bulk insert 100.000 writes/s trong 10 phút:

~~~text
Pending compactions: grows steadily
L0 SSTable count:      increases
Write p99:             rises after 5 minutes
~~~

1. Vì sao benchmark 30 giây có thể bỏ sót vấn đề?
2. Compaction dùng tài nguyên nào?
3. Vì sao tắt compaction lâu dài có thể làm read/write xấu hơn?
4. Có thể throttle import như thế nào?

### Bài 16 — Hot shard

Cụm 10 shards, một shard nhận 70% traffic; cluster CPU trung bình 25%.

1. Tại sao p99 một nhóm keys vẫn cao?
2. Những metrics theo partition cần có?
3. Thay partition key/hash có thể giúp gì?
4. Khi nào không thể phân tán write vì business invariant?

### Bài 17 — Open-loop và coordinated omission

Benchmark có 100 workers, mỗi worker gửi request mới ngay sau khi response trước về.

1. Đây là open-loop hay closed-loop?
2. Khi DB chậm 10 lần, arrival rate sẽ thay đổi thế nào?
3. Tại sao histogram có thể đánh giá thấp downtime?
4. Thiết kế một open-loop benchmark có stop conditions.

### Bài 18 — Concurrency sweep

Cho bảng:

| Concurrency | Useful ops/s | p99 |
| ---: | ---: | ---: |
| 16 | 700 | 40 ms |
| 32 | 1.050 | 65 ms |
| 64 | 1.100 | 180 ms |
| 128 | 1.020 | 600 ms |

SLO p99 <100 ms.

1. Điểm nào phù hợp nhất trong các mức đã đo?
2. Vì sao không chọn 128?
3. Vì sao phải xem errors/retries ngoài throughput?
4. Nếu workload mix đổi, có cần đo lại?

### Bài 19 — Phân tích critical path

Một HTTP request chạy ba DB calls song song: A=80 ms, B=200 ms, C=140 ms.

1. Nếu bắt đầu đồng thời, critical-path latency khoảng bao nhiêu?
2. Nếu chạy tuần tự thì tổng bao nhiêu?
3. Vì sao cộng mọi tracing spans có thể sai?
4. Nếu call B có pool wait 150 ms, nên đặt giả thuyết gì?

### Bài 20 — Thí nghiệm một biến

Team cùng lúc:

~~~text
maxPoolSize: 30 -> 200
DB volume: 3,000 -> 10,000 IOPS
JVM Xmx: 4GiB -> 8GiB
Retry count: 2 -> 5
~~~

Sau deploy p99 giảm 10%. Có thể kết luận thành phần nào giúp không?

Hãy thiết kế lại một canary experiment kiểm soát:

- Workload.
- Version deploy.
- Dataset/cache state.
- Thời gian đo và trials.
- p99/error/retries/useful throughput.
- Rollback threshold.

### Bài 21 — Managed NoSQL

DynamoDB/Cosmos-like service có throttled requests tăng nhưng ứng dụng không có quyền xem disk.

1. Dùng service metrics nào?
2. Vì sao tăng HTTP max concurrency có thể làm tệ hơn?
3. Hot partition khác global capacity thiếu ra sao?
4. Retry mode/SDK client metrics cần đo gì?

### Bài 22 — Case study tổng hợp

Trên 8 pods Java và 4 DB nodes:

~~~text
HTTP RPS stable:            1500
HTTP p99:                 1300ms
App CPU:                    35%
DB CPU avg:                 28%
One DB node CPU:           100%
Driver pool pending:       high
DB disk latency:           low
Retry amplification:       2.3
Top key accounts:          78% of writes
~~~

Hãy:

1. Nêu 3 giả thuyết theo thứ tự ưu tiên.
2. Chỉ ra chỉ số nào giúp loại trừ disk là nút thắt chính.
3. Vẽ chuỗi cause/effect từ hot key đến retries.
4. Đề xuất hai biện pháp ngắn hạn và hai biện pháp dài hạn.
5. Nêu cách bảo vệ business invariant khi repartition.

### Bài 23 — Phân biệt GC và network

Trước deploy:

~~~text
HTTP p99 = 120ms, GC pause p99 = 10ms, RTT=8ms
~~~

Sau deploy:

~~~text
HTTP p99 = 500ms, GC pause p99 = 380ms, RTT=9ms
~~~

1. Giả thuyết ưu tiên?
2. Metrics allocations/heap nào kiểm tra thêm?
3. Vì sao không nâng bandwidth trước?
4. Nếu GC pause giảm mà HTTP p99 không giảm, bước tiếp theo?

### Bài 24 — Storage write amplification

Một logical write 2 KiB có average physical write amplification 8× trong một LSM workload:

1. Ước lượng bytes ghi vật lý trung bình cho mỗi logical write trong phạm vi định nghĩa.
2. Với 10.000 writes/s, xấp xỉ physical write bytes/s?
3. Vì sao amplification có thể đổi theo compaction, indexes và retention?
4. Thử nghiệm nào kiểm tra backlog sau 60 phút?

### Bài 25 — Runbook thực tế

Bạn là on-call lúc 02:00, p99 tăng và timeout rate 5%:

1. Những dashboards cần mở đầu tiên?
2. Làm sao phân biệt network vs DB CPU vs storage vs app queue?
3. Khi nào nên giảm retries/limit concurrent operations?
4. Những thao tác nào cần approval vì thay durability/consistency?
5. Khi system hồi phục, đo lường gì trước khi đóng incident?

## 44. Lời giải mẫu và phương pháp suy luận

Các lời giải sau minh họa cách **tính và xác định dấu hiệu**, không thay thế phân tích hệ thống thực. Trong production, số đo phải đến từ cùng một workload, topology và khoảng thời gian.

### 44.1. Bài 2 — Little’s Law

\[
L=3500\times0{,}024=84
\]

Trung bình có khoảng **84 operations trong phạm vi đo**. Không thay 24 ms mean bằng 180 ms p99 rồi gọi là đúng Little’s Law.

Nếu 40% mean duration là queue wait và giả định tỷ lệ throughput tương ứng, mean service portion khoảng 60% × 24 ms = 14,4 ms. Số đang thực sự phục vụ bình quân xấp xỉ:

\[
3500\times0{,}0144=50{,}4
\]

Khoảng 33,6 operations còn lại tương ứng phần queue theo mô hình phân chia thời gian đơn giản. Phép tách này chỉ hợp lệ nếu các stages/scope được đo nhất quán và không double count parallel work.

### 44.2. Bài 3 — Retry amplification

\[
1200\times2{,}4=2880\text{ attempts/s}
\]

Nếu chỉ 900 logical reads hoàn thành có ích mỗi giây thì useful throughput là **900 reads/s**, không phải 2.880. Tăng retry vô điều kiện có thể làm backend tệ hơn; kiểm tra retry causes, response time và attempt budget.

### 44.3. Bài 4 — CPU trung bình

\[
\frac{100+15\times10}{16}=15{,}625\%
\]

CPU tổng thấp không bác bỏ một critical core/event loop nóng. Cần per-core usage, single-thread flame graph, lock contention và scheduling. Nếu 15 cores còn rảnh nhưng một serialized bottleneck không scale theo threads, tăng connections không có ích.

### 44.4. Bài 6 — Nhiều RTT tuần tự

Năm requests tuần tự, một RTT 60 ms mỗi request:

\[
5\times60=300\text{ ms RTT contribution}
\]

Thêm mỗi DB execution 5 ms:

\[
5\times(60+5)=325\text{ ms}
\]

Chưa tính queue, TLS/setup và serialization. Nếu năm requests có thể chạy song song độc lập, critical path lý tưởng gần **65 ms**, nhưng backend contention, pool limits và data dependencies có thể khiến con số thực lớn hơn.

### 44.5. Bài 7 — Network bandwidth

\[
20\,000\times8192
=163\,840\,000\text{ bytes/s}
\]

Quy đổi sang decimal Gbit/s:

\[
163\,840\,000\times8/10^9
\approx1{,}31\ \mathrm{Gbit/s}
\]

Vượt 1 Gbit/s trước khi thêm protocol overhead, vì vậy NIC/link 1 Gbit/s **không đủ** cho lưu lượng payload chưa nén này nếu không có batching/compression/đổi network capacity.

### 44.6. Bài 11 — IOPS từ misses

100.000 reads/s × 0,5% cache miss = **500 misses/s**.

Nếu mỗi miss sinh 4 physical reads:

\[
500\times4=2000\text{ physical read IOPS}
\]

Khi hit giảm còn 95%, misses/s = 5.000, nên:

\[
5000\times4=20\,000\text{ physical read IOPS}
\]

Chỉ giảm 4,5 điểm phần trăm cache hit mà IOPS tăng **10 lần**, giải thích vì sao nhìn hit rate một mình dễ đánh giá thấp nguy cơ.

### 44.7. Bài 13 — IOPS vs throughput

20.000 × 4 KiB = khoảng **78,1 MiB/s**, thấp hơn 300 MiB/s, nên **IOPS limit** đến trước ở 4 KiB.

Với request 256 KiB:

\[
300\ \mathrm{MiB/s}\div0{,}25\ \mathrm{MiB}
=1200\text{ operations/s}
\]

Trong mô hình đơn giản, throughput limit đến trước 20.000 IOPS. Kết quả thực có thể còn phụ thuộc latency/queue depth và storage service constraints.

### 44.8. Bài 18 — Chọn concurrency

Trong các mức đã đo, concurrency **32** đạt ~1.050 useful ops/s với p99 65 ms, thỏa SLO p99 <100 ms. Concurrency 64 đạt thêm ~50 useful ops/s nhưng p99 180 ms vượt SLO. Concurrency 128 vừa chậm hơn vừa không tăng useful throughput.

Vẫn phải báo error rate/retry/load profile và lặp benchmark trước khi dùng 32 làm production setting.

### 44.9. Bài 19 — Parallel critical path

Ba calls 80, 200, 140 ms nếu hoàn toàn song song và cùng bắt đầu có critical path khoảng **200 ms**; nếu tuần tự thì tổng **420 ms**. Các spans chồng thời gian không thể cộng mù. Nếu B có pool wait 150 ms thì cần kiểm tra per-server pool, held connections và downstream slowness.

### 44.10. Bài 24 — Write amplification

Logical write 2 KiB với amplification 8×:

\[
2\times8=16\text{ KiB physical write-equivalent/logical write}
\]

Với 10.000 writes/s:

\[
16\times10\,000=160\,000\text{ KiB/s}
\approx156{,}25\text{ MiB/s}
\]

Đây là xấp xỉ theo **định nghĩa amplification của workload**; không tự cộng WAL/index lần nữa nếu measurement amplification đã bao gồm những bytes ấy.

## 45. Checklist thực hành: phân biệt giới hạn ứng dụng, mạng, CPU, RAM và disk

### 45.1. Xác định workload và tác động

1. Endpoint/query shape cụ thể nào chậm?
2. Có phân biệt **logical requests/s** và **DB attempts/s** không?
3. p50/p95/p99/error rate được đo trên cùng khoảng thời gian không?
4. Có tính timeout, canceled requests và rejections vào báo cáo không?
5. Dataset, key distribution, data sizes và consistency mode có đại diện production không?
6. Có nhìn useful throughput cùng p99 thay vì chỉ số requests gửi không?
7. Có phân biệt benchmark cold cache, warm cache và soak test không?

### 45.2. Ứng dụng/Java

8. HTTP admission queue và executor queue depth có tăng không?
9. Bulkhead permits/connection pool pending acquires có saturated không?
10. Driver pool size có scope per-server/endpoint không?
11. Có connection/session/cursor leak sau khi traffic giảm không?
12. Thread dump cho thấy blocked lock, socket wait hay CPU work?
13. Event-loop thread có gọi blocking API không?
14. `async`/virtual threads có tạo lượng work vô hạn không?
15. JSON/DTO serialization, compression hoặc logging có chiếm CPU/heap không?
16. SDK và gateway có retries ẩn trong số đo không?
17. Timeout/deadline và cancellation có chung budget không?

### 45.3. Mạng

18. Network RTT và jitter ở cùng route có tăng không?
19. Packet loss/retransmission/reset có thay đổi không?
20. NIC/egress throughput có gần giới hạn không?
21. Có khác biệt theo AZ/region/route/proxy không?
22. DNS/TCP/TLS connection setup có phát sinh quá nhiều không?
23. Client driver có tái sử dụng connections đúng không?
24. Query critical path có quá nhiều round trips tuần tự/N+1 không?
25. Có phân biệt socket timeout với DB server execution timeout không?

### 45.4. CPU và contention

26. CPU được xem **per core, per pod và per node**, không chỉ average chứ?
27. Container CPU quota/throttling có hiện tượng gì?
28. OS run queue và CPU profiling cho thấy hot threads/methods nào?
29. Có hot partition/key khiến một shard 100% không?
30. Query planner/index có scan quá nhiều dữ liệu không?
31. Lock/transaction/CAS conflicts có tăng không?
32. Có retries/speculative requests làm tăng CPU demand không?
33. CPU cao là nguyên nhân hay hệ quả của network retry/compaction?

### 45.5. Bộ nhớ và cache

34. JVM heap, RSS/off-heap và cgroup memory được phân biệt không?
35. GC pause time và allocation rate có trùng latency spike không?
36. Working set có vượt cache/page cache không?
37. Cache misses/s (không chỉ cache hit %) có tăng không?
38. Có swap/major page faults/OOM events không?
39. Background scans có đẩy hot pages khỏi cache không?
40. Query/aggregation có spill ra disk không?
41. Memtable/write buffer/flush backlog có tăng không?

### 45.6. Lưu trữ và NoSQL topology

42. Storage IOPS, MB/s, queue depth và p99 latency có đo đủ không?
43. Cloud volume/instance quotas và burst credits có bị chạm không?
44. WAL/fsync hoặc compaction có chặn writes không?
45. Read/write amplification có tăng do indexes/tombstones/LSM levels không?
46. Backup/CDC/snapshot jobs có tranh I/O/network không?
47. Disk free space có đủ cho compaction/recovery không?
48. Có per-shard/node latency và hot key distribution không?
49. Quorum/read preference/replication làm critical path đi qua replica chậm nào?
50. Có phân biệt total cluster capacity và capacity một partition không?

### 45.7. Thí nghiệm và vận hành

51. Đã đặt **giả thuyết có thể bác bỏ** trước khi đổi config chưa?
52. Có thử một biến tại một thời điểm và giữ workload ổn định không?
53. Có canary và rollback threshold không?
54. Có kiểm tra load generator không bị saturated/coordinated omission không?
55. Có chạy spike, step, soak và fault/reconnect tests không?
56. Có xác minh business correctness của writes sau timeouts/retries không?
57. Có dashboard cùng time range và deployments markers không?
58. Có ghi rõ khi p99 cải thiện nhưng error rate/consistency xấu đi không?
59. Có báo bottleneck mới sau khi tối ưu bottleneck cũ không?
60. Có cập nhật runbook/alerts theo nguyên nhân đã xác minh không?

## 46. Tóm tắt theo câu hỏi quyết định

| Nếu câu hỏi là… | Nên bắt đầu ở… |
| --- | --- |
| “DB CPU rảnh nhưng HTTP p99 cao?” | App queue/pool/GC, network RTT, hot shard |
| “Một node rất chậm, các node khác rảnh?” | Hot partitions, per-node CPU, storage/replica path |
| “DB service time thấp mà client p99 cao?” | Pool acquisition, network setup, serialization |
| “Traffic không đổi mà disk IOPS tăng?” | Cache misses, query plan, compaction, background scan |
| “Có nhiều RAM nhưng p99 write cao?” | WAL/fsync, transaction locks, network quorum |
| “Tăng connections làm p99 tệ hơn?” | Backend saturation, admission/backpressure |
| “p50 đẹp nhưng p99 rất xấu?” | Tail events: GC, disk stall, retries, hot keys |
| “Tăng pods làm database chậm hơn?” | Total in-flight, connection budget, retry amplification |
| “CPU thấp nhưng latency cao?” | I/O waits, locks, network, throttling theo pod/core |
| “Benchmark rất nhanh nhưng production chậm?” | Dataset/hot set, workload mix, warm cache, error accounting |
| “Snapshot/CDC làm point reads chậm?” | Shared disk/network/CPU/cache budgets |
| “Managed NoSQL trả 429/limit errors?” | Capacity/quota/hot partition, SDK retry behavior |

## Kết luận

Trong hệ thống NoSQL, **giới hạn ứng dụng, mạng, CPU, bộ nhớ và lưu trữ phải được phân biệt bằng dấu hiệu đo được**, không bằng cảm tính hoặc một con số CPU trung bình. Cùng một triệu chứng “request chậm” có thể xuất phát từ những nơi rất khác nhau:

- **Ứng dụng:** Queue, thread/executor, connection pool, serialization, GC, resource leaks hoặc retry amplification.
- **Mạng:** RTT, số round trips tuần tự, packet loss/retransmission, TLS/setup, bandwidth và cross-region paths.
- **CPU:** Core nóng, CPU quota throttling, query plan kém, serialization, index maintenance, locks hoặc hot partitions.
- **Bộ nhớ:** JVM heap/off-heap pressure, GC pauses, working set vượt cache, page faults, eviction, swap hoặc memory-bound query.
- **Lưu trữ:** Random IOPS, MB/s, queue/device latency, WAL/fsync, compaction, tombstones, backups và volume quotas.

Một cách làm đáng tin cậy là:

1. Xác định **logical workload và SLO**.
2. Đo **RED** để biết người dùng chịu ảnh hưởng thế nào.
3. Đo **USE** theo từng tài nguyên và per-shard/per-pod scope.
4. Tách **queue wait, pool wait, network, server execution và serialization** trên critical path.
5. Đặt giả thuyết có thể bác bỏ, làm một thí nghiệm kiểm soát.
6. Chọn giới hạn/thiết kế mang lại **useful throughput trong SLO**, không tối đa số connections hay retries.
7. Xác minh tính đúng và khả năng hồi phục sau khi tối ưu.

Câu hỏi cần giữ trong mọi lần chẩn đoán là: **“Yêu cầu này đang chờ ở đâu, tài nguyên nào thực sự đã bão hòa, và bằng chứng nào cho thấy tối ưu tài nguyên đó sẽ giảm thời gian hoàn thành mà không làm tăng lỗi hoặc phá bất biến dữ liệu?”**
