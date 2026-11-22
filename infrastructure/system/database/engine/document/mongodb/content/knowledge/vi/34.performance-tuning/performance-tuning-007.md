# Kiểm soát mức song song, connection pool và hàng đợi yêu cầu

Một ứng dụng MongoDB có thể hoạt động rất nhanh với 50 người dùng đồng thời nhưng trở nên chậm, timeout hàng loạt khi lượng request tăng lên 500 hoặc 5.000. Phản ứng thường gặp là **tăng số threads và `maxPoolSize`**, với hy vọng “nhiều kết nối hơn thì throughput cao hơn”. Trong thực tế, khi database đã bão hòa CPU, I/O, locks hoặc storage-engine resources, nhiều truy vấn chạy song song hơn có thể **kéo dài thời gian chờ, tăng memory, tạo retry storm và làm p99 latency tệ hơn**.

Bài học **“Kiểm soát mức song song, connection pool và hàng đợi yêu cầu”** thuộc chương **Tối ưu hiệu năng** của module *Database Engine Document MongoDB* tập trung vào ba lớp liên quan nhưng khác nhau:

1. **Concurrency/admission control:** Có bao nhiêu yêu cầu/operation được phép bắt đầu hoặc cùng lúc tiêu thụ tài nguyên?
2. **Connection pool:** Có bao nhiêu kết nối mạng MongoDB driver giữ và cho các thao tác mượn tại một thời điểm?
3. **Queue/backpressure:** Khi số yêu cầu đến vượt khả năng xử lý, nên chờ bao lâu, từ chối khi nào, và làm sao để không tạo hàng đợi vô hạn?

Mục tiêu cuối không phải tối đa hóa mọi chỉ số, mà là đạt **throughput bền vững**, **latency p95/p99 có giới hạn**, **hệ thống không sụp đổ khi tải tăng**, và **khôi phục được sau spikes/failover**.

> **Phạm vi và phiên bản:** Các ví dụ Java chủ yếu dùng **MongoDB Java Sync Driver 5.x** và MongoDB Server hiện đại. Tên API/timeout thay đổi giữa 4.x, 5.x và từng patch; đặc biệt **client-side operation timeout (CSOT) `timeoutMS` hiện được MongoDB đánh dấu experimental** và các option timeout cũ có quy tắc tương tác/deprecation riêng. Hãy kiểm tra đúng driver/server/framework version trước triển khai. Các số lượng connection, thời gian và biểu đồ tải trong bài chỉ là tình huống **minh họa**, không phải benchmark trên một cluster thật.

## 1. Triệu chứng: vì sao tăng connection pool có thể làm hệ thống chậm hơn?

Giả sử API tìm đơn hàng theo khách hàng:

~~~text
HTTP request
    |
    v
Application worker/thread
    |
    v
Admission gate (cho phép có giới hạn)
    |
    v
MongoDB driver chọn server
    |
    v
Checkout connection từ pool
    |
    v
MongoDB server nhận command
    |
    v
Query execution / storage / network
    |
    v
Return connection -> Return HTTP response
~~~

Các giai đoạn có thể chờ ở nơi khác nhau:

- Chờ **HTTP worker/queue** trước khi handler chạy.
- Chờ **semaphore/bulkhead** do application chủ động giới hạn.
- Chờ **MongoDB server selection** khi chưa tìm được primary/secondary phù hợp.
- Chờ **connection checkout** khi pool không còn connection sẵn.
- Chờ **tạo kết nối** nếu pool mới khởi động và `maxConnecting` hạn chế số kết nối tạo đồng thời.
- Chờ **MongoDB thực thi command** do CPU, disk, locks, cache misses, transaction conflicts, aggregation memory hoặc cluster routing.
- Chờ network/response/cursor `getMore`; trong một số use cases streaming, connection có thể được giữ hoặc mượn lại theo cursor/batch semantics.

**Kết luận quan trọng:** “Request đang chờ” không cho biết **nó đang chờ ở đâu**. Nếu server saturated mà chỉ tăng pool từ 100 lên 1.000, request có thể chuyển từ **pool wait queue** sang **server execution queue**, tổng latency không tốt hơn.

### 1.1. Bảng triệu chứng và hướng kiểm tra

| Triệu chứng | Có thể do | Bằng chứng cần lấy |
|---|---|---|
| Connection checkout wait p95 tăng | Pool bận hoặc tạo connection chậm. | CMAP driver events, checked-out/in-use, waiters, `maxConnecting`. |
| `MongoTimeoutException` khi chọn server | Primary không khả dụng/topology/network. | Server selection exception, topology view, failover status. |
| Connections nhiều, throughput không tăng | DB CPU/IOPS/locks bão hòa, query chậm. | `serverStatus`, profiler, query plan, CPU/IOPS, p95 command execution. |
| CPU app tăng, GC pauses | Quá nhiều futures/threads/queued requests. | Heap, GC logs, executor queue depth, thread dumps. |
| Scaling pods làm DB chậm đột ngột | Mỗi pod có pool riêng và cùng tạo kết nối. | Pool count × pod count, connection creation rate, server connections. |
| Sau failover tất cả requests timeout | Server selection, pool clear/reconnect, retry storm. | SDAM/CMAP events, network, exponential backoff. |
| Query đơn lẻ nhanh nhưng HTTP p99 cao | Chờ HTTP queue, admission, pool, network. | Distributed tracing theo từng stage. |
| `maxTimeMS` timeout trong DB | Query tốn nhiều server execution time. | `explain`, index, aggregation, workload saturation. |

### 1.2. Ba mục tiêu dễ xung đột

1. **Tận dụng tài nguyên:** Không để DB thường xuyên idle khi còn yêu cầu hợp lệ.
2. **Giới hạn tail latency:** Không đẩy 10.000 requests vào nơi chờ chỉ có năng lực xử lý 100 yêu cầu/giây.
3. **Công bằng và khả dụng:** Một tenant/report nặng không lấy hết tài nguyên của API đăng nhập hoặc checkout đơn hàng.

Thiết kế tốt thường chọn **concurrency limit + bounded queue + timeout + load shedding**, sau đó mới tinh chỉnh pool theo workload thực.

## 2. Bốn tầng song song cần phân biệt

### 2.1. Concurrency từ người dùng/HTTP

`concurrentRequests` là số request đang được service xử lý hoặc chờ xử lý, không bằng số threads và cũng không luôn bằng số MongoDB connections. Một HTTP request có thể:

- Không đụng MongoDB.
- Chạy 1 query rồi gọi service khác.
- Chạy 3 queries nối tiếp.
- Chạy 3 queries song song bằng futures/reactive code.
- Duy trì cursor hoặc change stream lâu dài.

Do đó **1 request không tương đương 1 MongoDB connection** ở mọi thời điểm.

### 2.2. Application concurrency / worker pool

Java Servlet thread pool, `ExecutorService`, virtual threads, Spring Reactor scheduler hoặc job worker điều khiển **bao nhiêu task chạy đồng thời**. Một thread bị block đợi connection vẫn có thể chiếm tài nguyên JVM và một slot HTTP worker.

Nếu dùng asynchronous driver, nhiều operations có thể **in-flight mà không cần mỗi operation có một Java thread riêng**; tuy nhiên MongoDB/database concurrency vẫn phải được kiểm soát. Async không đồng nghĩa vô hạn capacity.

### 2.3. Driver connection pool

**MongoClient giữ pool riêng cho mỗi server** mà driver giao tiếp theo topology, cùng với monitoring sockets không thuộc giới hạn pool thao tác. Pool là **cache/reuse transport connections**, không phải hệ thống scheduling thay thế mọi queue.

Khi driver cần một connection mà các pooled connections đều đang dùng và pool đã đạt `maxPoolSize`, thread/request có thể **chờ checkout** theo timeout tương ứng.

### 2.4. MongoDB server execution concurrency

Ngay cả khi 200 connections đồng thời gửi commands đến primary, server không nhất thiết xử lý 200 commands “nhanh như khi chỉ có 20”. MongoDB chịu giới hạn:

- CPU cores, cgroup CPU quotas và context switching.
- WiredTiger cache/eviction và disk IOPS/throughput.
- Lock contention và write conflicts.
- Storage engine concurrent tickets/admission.
- Query plan, indexes, sorting/aggregation, memory limits.
- Replication/write concern, sharding network/mongos.

**Pool size không phải throughput quota của server.** Một server có thể có rất nhiều TCP connections idle, nhưng chỉ một phần có operations đang chạy.

### 2.5. Sơ đồ hàng đợi nhiều tầng

~~~text
Incoming requests (rate λ)
    |
    v
HTTP ingress / load balancer
    |    [queue 1]
    v
Application admission gate
    |    [queue 2: bounded]
    v
Worker / async operation
    |    [wait for server selection]
    v
MongoDB driver pool
    |    [queue 3: connection checkout wait]
    v
mongod / mongos
    |    [internal scheduling/locks/tickets]
    v
Storage engine / disk
~~~

Nếu một request chờ mỗi tầng 100 ms thì dù query thực thi chỉ 10 ms, HTTP latency vẫn có thể cao hàng trăm ms. **Thêm hàng đợi không tạo thêm năng lực xử lý**.

## 3. Nền tảng định lượng: Little's Law và năng lực xử lý

### 3.1. Little's Law

Trong hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số lượng trung bình công việc **đang ở trong hệ thống** (bao gồm đang phục vụ và đang chờ nếu phạm vi đo có queue).
- \(\lambda\): throughput thực tế, requests/giây.
- \(W\): thời gian trung bình mỗi request ở trong cùng phạm vi, giây.

Ví dụ service xử lý được 400 MongoDB operations/giây và mỗi operation giữ connection trung bình 0,025 giây:

\[
L \approx 400 \times 0.025 = 10
\]

Ở thời điểm ổn định, trung bình khoảng **10 operations đồng thời giữ connection**. Điều này **không** có nghĩa nên đặt `maxPoolSize=10` cho mọi trường hợp; p95/p99, burstiness, multi-request operations, retries và server routing tạo peaks cao hơn trung bình.

### 3.2. Concurrency budget từ latency budget

Một API có SLO p95 200 ms, phần logic ngoài DB chiếm 80 ms. Còn khoảng **120 ms** cho waiting + MongoDB work:

~~~text
HTTP SLO p95:           200 ms
  Auth/validation:        20 ms
  Business/network:       60 ms
  DB selection/queue/run: 120 ms
~~~

Đừng đặt `waitQueueTimeoutMS=30s` cho một HTTP request có SLO 200 ms mà không có reason; request sẽ hết hạn ở client trước khi DB pool trả connection. **Deadline phải được truyền từ đầu đến cuối**.

### 3.3. Service capacity và queue growth

Nếu DB xử lý bền vững được 500 operations/giây nhưng app gửi tới 800 operations/giây:

\[
\Delta Q/\Delta t \approx 800 - 500 = 300 \ \text{operations/giây}
\]

Sau 10 giây có thể có ~3.000 operations chờ **nếu không có admission/rejection và giả định rate không đổi**. Khi đó latency trong queue tăng; client timeout rồi retry, tiếp tục tăng incoming rate. Đây là **overload feedback loop**.

### 3.4. Vì sao 100% utilization nguy hiểm?

Với workload arrival/service biến thiên, khi utilization \(\rho\) tiến gần 1, thời gian chờ có xu hướng tăng nhanh trong các mô hình queue phổ biến. **Không nên** thiết kế hệ thống để DB CPU luôn đúng 100% hoặc pool luôn 100% checked-out rồi coi đó là tối ưu.

Mốc “giữ utilization dưới 70–80%” chỉ là **heuristic để bắt đầu đo**, không phải hằng số MongoDB. Workload có query times khác nhau, I/O, locks và scheduling thực; chọn threshold bằng load test và p95/p99.

### 3.5. M/M/c là mô hình, không phải MongoDB thật

Mô hình queue \(M/M/c\) với Poisson arrivals, exponential service, \(c\) servers có thể minh họa quan hệ capacity–wait. Nhưng MongoDB có phân phối query duration **đuôi dài**, cache effects, indexes, replication và resource sharing; \(c\) không nhất thiết bằng `maxPoolSize`.

Do đó **không** suy “pool 100 ⇒ 100 parallel queries hoàn toàn độc lập” rồi áp công thức M/M/100 để ra cấu hình production. Dùng mô hình để hiểu xu hướng, **benchmark để chọn số**.

### 3.6. Throughput khác concurrency

| Thuật ngữ | Ví dụ | Đơn vị |
|---|---|---|
| Arrival rate | API nhận 1.000 requests/s. | req/s |
| Completed throughput | DB thực tế hoàn thành 600 operations/s. | op/s |
| In-flight | Có 80 commands đang chờ/chạy. | operations |
| Pool occupancy | 50 connections đang checked out. | connections |
| Queue depth | 200 tasks đợi permit. | tasks |
| Latency p95 | 95% requests hoàn tất trong ≤250 ms. | milliseconds |
| Utilization | CPU 75% hoặc pool 90% in-use. | % |

**Những metrics này không thay thế nhau.** Chỉ nhìn connection count và throughput có thể bỏ qua queue depth và tail latency.

## 4. MongoDB Java Driver connection pool hoạt động ra sao?

Theo hướng dẫn MongoDB Java Sync Driver hiện hành, **mỗi `MongoClient` có một pool cho từng server** trong topology mà client cần kết nối. Các connections được mở **theo nhu cầu**, được checkout khi operation cần transport và trả lại để tái sử dụng.

### 4.1. Pool theo server, không phải một “giỏ chung toàn cluster”

Giả sử một replica set có 3 members và client:

~~~text
                     One MongoClient
                       |
           +-----------+-----------+
           |           |           |
           v           v           v
        Primary      Secondary1  Secondary2
         Pool P        Pool S1     Pool S2
       maxSize=100   maxSize=100 maxSize=100
~~~

Con số `maxPoolSize=100` là **giới hạn mỗi pool theo server**, không nhất thiết 100 TCP sockets trên toàn cluster. Với mặc định read preference primary, application thường gửi read/write operations tới primary, trong khi secondary pools có thể nhỏ/không mở connections cho operations nếu không được dùng.

Driver cũng duy trì **monitoring sockets** để quan sát topology, thường **hai sockets thêm trên mỗi server** theo tài liệu Java Driver hiện hành; chúng nằm ngoài `maxPoolSize` của application operations.

### 4.2. Quy mô connections khi scale horizontally

Nếu 20 application pods, mỗi pod dùng 1 MongoClient với `maxPoolSize=100`, và phần lớn operations dùng primary:

\[
20 \times 100 = 2{,}000
\]

Đó là **giới hạn tiềm năng của application connections tới primary**, **không phải số chắc chắn đang mở**. Còn monitoring sockets, administrative clients, backup nodes và connections của services khác.

Nếu mỗi pod sai lầm tạo **5 MongoClient instances** riêng, giới hạn có thể nhân lên:

\[
20 \text{ pods} \times 5 \text{ clients/pod} \times 100
= 10{,}000 \text{ app connections tới một server}
\]

Đây là một **trần cấu hình**, không đồng nghĩa server luôn có 10.000 active commands; nhưng mở quá nhiều connections có thể tiêu thụ file descriptors, memory và tăng handshake/TLS/authentication cost.

### 4.3. Sharded cluster với nhiều `mongos`

Nếu MongoClient nhìn thấy 3 `mongos` endpoints, nó có thể có **pool riêng đến từng router**. `maxPoolSize=100` có nghĩa tối đa 100 pooled connections **trên mỗi router** cho client, không phải tổng 100 trải đều 3 routers.

Sau router, request còn được routing tới một/một số shards. Tăng app-to-mongos connections không tự làm shard hotspot bớt nóng nếu shard key/query pattern vẫn dồn lên một shard.

### 4.4. Load balancer, SRV và DNS

Với Atlas URI `mongodb+srv://...` hoặc topology có load balancer, số endpoints nhìn thấy và cách pooling/routing tùy cấu hình driver/deployment. Đừng lấy một phép nhân đơn giản từ danh sách hostnames trong URI rồi khẳng định số connections vật lý tới mọi `mongod`. **Xem driver pool metrics và server-side connections thực**, cộng với load-balancer metrics.

### 4.5. Kết nối đang mở không có nghĩa đang dùng

Các trạng thái thường gặp:

- **Created/open:** TCP/TLS/authenticated connection đang tồn tại.
- **Idle/available in pool:** Không có operation hiện tại sử dụng; có thể checkout ngay.
- **Checked out/in use:** Được operation mượn; có thể đang gửi command, nhận response hoặc chờ ở nơi khác trong lifecycle.
- **Connecting:** Đang được driver mở/handshake; chịu giới hạn `maxConnecting`.
- **Checkout waiting:** Operation đang đợi một connection available.
- **Closed/cleared:** Connection không còn dùng do idle/lifetime, network error, stepdown, pool clear.

Không dùng `connections.current` của server để thay thế số **checked-out** trong Java Driver; một server có thể có nhiều connections idle nhưng query vẫn chậm vì DB saturated.

## 5. Các tham số quan trọng của connection pool

Hướng dẫn MongoDB Java Sync Driver 5.x hiện hành mô tả:

| Cấu hình | Ý nghĩa | Giá trị mặc định được docs Java 5.x nêu | Tác động |
|---|---|---|---|
| `maxPoolSize` / `maxSize()` | Số pooled connections tối đa **mỗi server**. | 100 | Giới hạn số operations có thể checkout đồng thời qua pool đó. |
| `minPoolSize` / `minSize()` | Mức connections tối thiểu driver duy trì theo semantics. | 0 | Có thể làm pool ấm; tăng connections idle. |
| `maxConnecting` / `maxConnecting()` | Số connections **đang mở đồng thời** trên một pool. | 2 | Giới hạn tốc độ pool tăng khi cold start/burst. |
| `maxIdleTimeMS` | Lifetime tối đa khi connection idle trước khi đóng. | 0 (không giới hạn) | Chống stale idle sockets, giảm footprint khi tải giảm. |
| `maxLifeTimeMS` | Lifetime tối đa cho pooled connection. | 0 (không giới hạn) | Chủ động recycle connections; có thể tạo churn nếu quá thấp. |
| `waitQueueTimeoutMS` / `maxWaitTime()` | Thời gian tối đa chờ connection available. | Docs Java 5.x mô tả 2 phút, **deprecated** khi dùng CSOT. | Giới hạn checkout wait theo kiểu legacy. |

**Chú ý về mặc định:** MongoDB **Server Manual** ghi các default mang tính tổng quát theo driver, có thể khác docs **Java Driver**; hãy chọn docs của **driver/version đang chạy**. Đặc biệt, với **CSOT `timeoutMS`** được cấu hình, một số timeout options cũ (gồm `waitQueueTimeoutMS`) bị ignore/override theo docs Java hiện hành. Đừng suy rằng cả hai timeout luôn cộng dồn hoặc cái nhỏ hơn luôn thắng.

### 5.1. `maxPoolSize`: đừng điều chỉnh chỉ vì số HTTP threads

Giả sử app có 250 HTTP worker threads nhưng chỉ 20 threads trung bình đang thao tác DB, do phần còn lại đợi API khác hoặc xử lý logic. `maxPoolSize=250` có thể không cần thiết. Ngược lại, 50 async workers có thể tạo 200 in-flight MongoDB operations nếu mỗi request chạy nhiều branches song song.

Chọn `maxPoolSize` dựa trên **measured checked-out concurrency, checkout wait, tail latency và server capacity**, không lấy thread count làm phép gán cứng.

### 5.2. `minPoolSize`: tránh hiểu là “luôn mở đúng N”

`minPoolSize` hướng driver duy trì ít nhất một số connections theo pool lifecycle và background maintenance; không bảo đảm tất cả connections warm/sẵn sàng tức thì ở thời điểm pod vừa start. Nếu đặt `minPoolSize=100` cho 100 pods, có thể tạo **connection storm khi deploy**.

Ứng dụng nên có **readiness gate/warmup có kiểm soát** thay vì chờ tất cả pods đồng thời tranh tạo hundreds TLS connections.

### 5.3. `maxConnecting`: cold start và reconnect storms

Theo MongoDB, mặc định `maxConnecting=2` giới hạn số **connection establishments đồng thời trên một pool**. Nếu `maxPoolSize=100` nhưng pool rỗng, 100 operations mới tới không có nghĩa 100 sockets cùng mở ngay; chỉ một lượng giới hạn được tạo song song.

Tăng `maxConnecting` có thể giúp pool mở nhanh hơn, **nhưng** làm tăng handshake/TLS/auth load và nguy cơ connection storm. Cân nhắc tăng **rất có kiểm soát** với metrics ở cả driver và server.

### 5.4. `maxIdleTimeMS` và idle connections qua firewall

Một firewall/NAT có thể đóng idle TCP sockets sau 5 phút. Nếu driver giữ connection idle 30 phút, request đầu sau một giai đoạn nghỉ có thể gặp stale socket. Có thể đặt `maxIdleTimeMS` thấp hơn idle timeout của network/proxy và đo reconnect cost. Đừng đặt quá thấp đến mức liên tục mở lại connections, tăng CPU/TLS overhead.

### 5.5. `maxLifeTimeMS` và recycle đồng loạt

Một lifetime quá ngắn có thể làm driver recycle nhiều sockets khi traffic đang cao. Nếu nhiều pods restart cùng lúc, churn có thể đồng bộ và tăng tail latency. Đây là lý do phải quan sát **created/closed rate**, không chỉ active connections.

### 5.6. `waitQueueTimeoutMS` không tự giới hạn độ dài queue

Một timeout chờ connection **không phải** hard cap số requests được phép xếp hàng. Nếu 10.000 operations bắt đầu checkout cùng lúc và timeout 120 giây, có thể có rất nhiều threads/futures chờ, sử dụng memory và giữ request context.

Muốn queue bounded, phải đặt **admission control/worker queue** ở tầng ứng dụng hoặc use-case phù hợp. Với Java 5.x mới, cân nhắc **`timeoutMS` end-to-end** thay vì chỉ dựa vào `waitQueueTimeoutMS` legacy.

### 5.7. `maxPoolSize` nhỏ không thay thế queue policy

Một pool 10 connections giúp không có hơn ~10 checked-out operations qua pool đó cùng lúc, nhưng nếu 50.000 threads chờ 2 phút thì hệ thống vẫn dễ OOM. Pool cap là một dạng giới hạn transport concurrency; **rejection/timeout/queue depth còn phải được quản lý**.

## 6. Chọn MongoClient đúng vòng đời

### 6.1. Một MongoClient dùng chung cho service

**Sai lầm điển hình:**

~~~java
// BAD: tạo MongoClient cho từng HTTP request.
public Document getOrderBad(String id) {
    try (MongoClient c = MongoClients.create(mongoUri)) {
        return c.getDatabase("shop")
            .getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();
    }
}
~~~

Mỗi lần tạo client có thể phải tạo topology monitoring/connection pools, handshake và TLS/auth, rồi đóng ngay; nếu 500 requests/s, có nguy cơ bùng nổ sockets, CPU và connection creation/closure.

**Nên:** giữ một MongoClient thread-safe lâu dài theo application lifecycle:

~~~java
public final class MongoResources implements AutoCloseable {
    private final MongoClient client;
    private final MongoCollection<Document> orders;

    public MongoResources(String uri) {
        this.client = MongoClients.create(uri);
        this.orders = client.getDatabase("shop")
            .getCollection("orders");
    }

    public Document getOrder(String id) {
        return orders.find(Filters.eq("_id", id)).first();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

*Ví dụ giả định có imports `com.mongodb.client.MongoClient`, `MongoClients`, `MongoCollection`, `org.bson.Document` và `com.mongodb.client.model.Filters`.* Trong Spring Boot, nên để framework/DI quản lý singleton MongoClient và đóng khi application shutdown, không tự tạo client trong controller.

### 6.2. Trường hợp có nhiều clients là hợp lệ

Có thể có **hai MongoClient có mục đích riêng** (ví dụ latency-critical orders và background analytics) với connection pool/resource budgets khác nhau, hoặc kết nối tới **hai clusters** thật sự khác. Đây là **bulkhead bằng client/pool isolation**, nhưng phải tính **tổng connection budget**.

Không tạo client riêng cho từng tenant/request trừ khi có lý do kiến trúc rất rõ và chấp nhận được chi phí; đa tenant thường dùng logical auth/filter và admission fairness, không nhân hàng nghìn pools.

### 6.3. MongoClient thread-safe, session không chia bừa

MongoClient được thiết kế để chia sẻ giữa threads. **ClientSession** có lifecycle riêng, không nên truyền một session giữa nhiều tác vụ song song tùy ý; MongoDB Java Driver không hỗ trợ chạy concurrent operations trên **cùng một ClientSession** như thể đó là object thread-safe chung.

Với transactions, mỗi operation/sequence trong transaction phải giữ đúng session và timeout, đồng thời **transaction có thể giữ resource lâu hơn** so với một query đơn. Dùng pool metrics để thấy ảnh hưởng của transactions dài.

### 6.4. Đừng quên shutdown

Khi service dừng:

1. Readiness chuyển sang không nhận requests mới.
2. Drain in-flight operations trong thời hạn.
3. Hủy/cancel những tasks vượt deadline theo semantics framework/driver.
4. Đóng MongoClient và các executors sau khi worker hoàn tất hoặc timeout.

Đóng MongoClient **mỗi request** là sai, nhưng **không bao giờ đóng** khi process lifecycle phức tạp/redeploy classloader cũng có thể gây leaks.

## 7. Thời gian chờ: phân biệt năm loại timeout

Một request có thể thất bại do **không có server**, **chưa có connection**, **không mở được socket**, **server chạy query quá lâu** hoặc **deadline tổng đã hết**. Gán chung tất cả thành “MongoDB timeout” sẽ dẫn đến cách xử lý sai.

| Loại timeout | Phạm vi cơ bản | Điều cần nhớ |
|---|---|---|
| `serverSelectionTimeoutMS` | Chờ driver chọn server phù hợp (primary/secondary/mongos). | Có thể fail dù pool còn connection nếu không có primary phù hợp. |
| `connectTimeoutMS` | Thời gian mở một TCP connection. | Không phải thời gian checkout connection idle từ pool. |
| `waitQueueTimeoutMS` hoặc Java `maxWaitTime()` (legacy) | Chờ một pooled connection available. | Không có hard queue capacity; bị thay thế/bỏ qua khi có CSOT. |
| `socketTimeoutMS` (legacy) | Chờ network send/receive theo socket semantics. | Không nên coi là công cụ chuẩn giới hạn server operation runtime. |
| `maxTimeMS` | Giới hạn server execution time của một số operations. | Không tính toàn bộ application queue/pool wait và không là kill tức thì tuyệt đối. |
| `timeoutMS` (CSOT trong Java 5.x hiện hành) | **Deadline client-side cho operation**, gồm server selection, checkout và execution. | Experimental; nếu set thì có thể ignore những timeout legacy theo docs. |

### 7.1. Server selection khác pool checkout

Ví dụ error:

~~~text
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
~~~

Driver không chọn được primary hợp lệ. Tăng `maxPoolSize` thường **không giúp**; kiểm tra replica set election/network/SDAM/authorization/DNS. Ngược lại, pool checkout timeout thường nói đến **chờ connection available** dù server selection đã thành công.

### 7.2. Connection establishment khác connection reuse

`connectTimeoutMS` áp dụng khi mở một connection mới, gồm network establishment theo driver semantics. Nếu server selection xong nhưng pool có 100 connections idle tốt, operation có thể checkout mà không cần mở socket mới.

Khi cold start, `maxConnecting` hạn chế các kết nối mới tạo song song, nên thời gian checkout có thể tăng dù `maxPoolSize` chưa đạt.

### 7.3. `maxTimeMS` không bao trùm HTTP deadline

~~~javascript
// Ví dụ giới hạn thời gian server thực hiện find.
db.orders.find({ tenantId: "A", status: "OPEN" }).maxTimeMS(500)
~~~

`maxTimeMS` là server-side operation limit; **không bao gồm** thời gian request nằm trong HTTP queue, application semaphore hay driver pool checkout. MongoDB kiểm tra interruption ở những điểm thích hợp, không bảo đảm cắt CPU đúng từng mili-giây.

Đừng dùng `socketTimeoutMS` rất thấp để thay `maxTimeMS`; client có thể ngắt kết nối trong khi server còn đang xử lý/cleanup operation, tạo retry/connection churn.

### 7.4. CSOT: deadline tổng cho Java Driver

MongoDB Java Sync Driver 5.x docs mô tả **Client-Side Operation Timeout (CSOT)** qua `timeoutMS` / `MongoClientSettings.Builder.timeout()`. Nó bao gồm:

~~~text
Start MongoDB operation
  |
  +-- server selection
  +-- connection checkout / possible connection creation
  +-- command execution and response
  |
  v
Deadline timeoutMS
~~~

Ví dụ:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(mongoUri))
    .timeout(500L, TimeUnit.MILLISECONDS)
    .build();

MongoClient client = MongoClients.create(settings);
~~~

**Lưu ý:** CSOT hiện được tài liệu Java Driver gọi là **experimental**; syntax/version compatibility và inheritance cần đối chiếu branch cụ thể. Không sao chép ví dụ này vào mọi project Java 4.x rồi kỳ vọng method `timeout()` tồn tại.

### 7.5. CSOT và legacy timeout options

Theo Java 5.x docs, khi set `timeoutMS`, những timeout cũ như `waitQueueTimeoutMS`, `socketTimeoutMS`, `wTimeoutMS`, `maxTimeMS` và `maxCommitTimeMS` có thể bị **ignore** theo quy tắc CSOT. Vì vậy, một URI như:

~~~text
mongodb://host:27017/?timeoutMS=500&waitQueueTimeoutMS=10000
~~~

không nên được diễn giải là “pool chờ tối đa 10 giây nhưng operation tổng tối đa 500 ms”. Client-level `timeoutMS` điều khiển deadline theo docs, và có thể override ở database/collection/operation/transaction scope. **Kiểm tra docs driver version thực tế**.

Nếu không dùng CSOT, bộ timeout legacy vẫn có vai trò riêng; nhưng nên thiết kế chúng thống nhất với **HTTP request deadline** và application admission timeout.

### 7.6. Timeout của tầng ứng dụng

~~~text
HTTP deadline:          1.000 ms
  admission wait:         100 ms maximum
  MongoDB operation:      500 ms maximum
  transform/response:     100 ms
  reserve/retry margin:   300 ms
~~~

Đây là **budget minh họa**. Nếu request đã chờ 700 ms ở HTTP queue, không thể tiếp tục trao nguyên budget 500 ms cho MongoDB mà vẫn hứa deadline HTTP 1.000 ms. Cần **remaining deadline** truyền xuống mỗi stage, và từ chối sớm khi hết budget.

### 7.7. Timeout không chứng minh operation đã rollback

Client timeout có thể xảy ra sau khi server **đã ghi thành công** nhưng response không về kịp (đặc biệt trong network partition/election). Với writes, **không retry mù** theo kiểu “timeout => chưa ghi”.

Cần:

- Retryable writes/transactions theo hỗ trợ driver/operation.
- Stable idempotency keys hoặc unique business identifiers.
- Kiểm tra trạng thái commit khi kết quả không rõ ràng.
- Không retry vô hạn khi server đang quá tải.

Admission control giúp hạn chế **số attempts**, còn idempotency giúp bảo vệ **business semantics**.

## 8. Cấu hình Java Sync Driver 5.x theo một resource budget

Ví dụ một service có 4 application instances và một replica set. Ta đặt các giá trị **khởi đầu để đo**, không phải default tốt nhất:

~~~text
App instances:     4
MongoClient/pod:   1
Pool max per node: 64
Pool min per node: 4
maxConnecting:     4
Connection idle:   30 s
Operation CSOT:    750 ms
~~~

Nếu phần lớn traffic chọn primary, **trần application connections tới primary khoảng 4×64=256** (chưa kể monitors và clients khác). Không có nghĩa primary sẽ có 256 active operations liên tục.

### 8.1. Java cấu hình trực tiếp

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {

    public static MongoClient create(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applicationName("orders-api")
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .minSize(4)
                .maxConnecting(4)
                .maxConnectionIdleTime(30, TimeUnit.SECONDS)
            )
            // Java Driver 5.x CSOT: check exact version and support.
            .timeout(750L, TimeUnit.MILLISECONDS)
            .build();

        return MongoClients.create(settings);
    }
}
~~~

Ví dụ dùng `timeout()` theo Java Driver hiện hành và một URI được truyền từ cấu hình bảo mật; không hardcode secrets. Với Java Driver 4.x hoặc nơi chưa dùng CSOT, chọn API/connection options tương ứng, không pha hai mô hình timeout vô thức.

### 8.2. URI thay cho Builder

~~~text
mongodb://mongohost:27017/?appName=orders-api&maxPoolSize=64&minPoolSize=4&maxConnecting=4&maxIdleTimeMS=30000
~~~

Thêm `timeoutMS=750` khi driver/version hỗ trợ và đã chọn CSOT. Với Atlas `mongodb+srv`, không dùng hostname placeholder `mongohost` ngoài lab; giữ TLS/auth options do deployment yêu cầu.

### 8.3. Spring Boot và framework ownership

Trong Spring Boot/Spring Data MongoDB, nên để dependency injection tạo **một MongoClient managed bean**, thường qua `spring.data.mongodb.uri` hoặc config class, thay vì tạo client ở từng repository/service. Ví dụ cấu hình:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://db-host:27017/shop?maxPoolSize=64&maxConnecting=4"
~~~

Đây là một **ví dụ cấu hình Spring Boot**, phụ thuộc phiên bản starter/config. Với Atlas URI, đặt connection string có credentials trong secret store và không commit secret vào YAML. Nếu ứng dụng cần customization bằng `MongoClientSettingsBuilderCustomizer`, phải kiểm tra **auto-configuration precedence** để không vô tình tạo hai MongoClients.

### 8.4. Cấu hình pool theo từng loại workload

Thay vì mọi request dùng cùng shared pool, có thể tách:

~~~text
HTTP orders API:
  MongoClient A
  maxPoolSize 50
  admission limit 40
  short timeout

Background analytics:
  MongoClient B
  maxPoolSize 10
  admission limit 4
  longer timeout
~~~

Đây là **bulkhead** để reporting không làm checkout queue của orders API tăng đột ngột. Đổi lại, một JVM có **hai clients × per-server pools**, cần tính vào connection budget và quản lý đóng cả hai. **Mỗi pool không tự bảo đảm CPU isolation ở DB**; workload analytics vẫn có thể tiêu thụ IOPS/cache, nên còn cần query optimization, scheduling và server-side resource strategy.

### 8.5. Tính budget trước khi tăng pool

Một bảng tính kiến trúc:

| Biến | Giá trị giả định |
|---|---:|
| Pods | 12 |
| MongoClients/pod | 2 |
| `maxPoolSize`/client/server | 80 |
| App connections tối đa tới **một server** nếu cả hai clients dùng nó | 1.920 |
| Monitoring sockets và other clients | Thêm ngoài trần trên |

\[
12 \times 2 \times 80 = 1{,}920
\]

Nếu cluster chỉ cho phép/khuyến nghị một giới hạn connections thấp hơn, config này có thể nguy hiểm dù **mỗi pod** nhìn “chỉ 80”. Khi tăng autoscaling replicas từ 12 lên 40, tổng trần tăng theo; cần **global connection budget** và admission ở tầng ứng dụng.

## 9. Admission control: chủ động giới hạn in-flight DB operations

Một **admission gate** trước MongoDB giúp chỉ cho tối đa \(C\) operations đồng thời đi vào DB path. Phần vượt giới hạn được **chờ ngắn có hạn** hoặc **từ chối sớm**. Đó là cách quản lý tài nguyên rõ ràng hơn để 5.000 requests cùng đợi trong pool.

### 9.1. Sơ đồ bounded admission

~~~text
Incoming HTTP traffic
      |
      v
   Queue cap Q=80
      |
      +--- full? --> HTTP 429/503 / Retry-After / degrade
      |
      v
   Permits C=40
      |
      v
MongoDB driver
  Pool maxSize=64
      |
      v
 MongoDB server
~~~

Nếu gate cap 40 và một operation sử dụng tối đa một connection tại một thời điểm, thường sẽ có ít hơn hoặc bằng ~40 checked-out connections do nhóm operation này tạo ra. **Nhưng** một request có thể spawn nhiều DB calls, change streams/transactions giữ connections lâu, và có traffic khác không đi qua gate; phải xác định phạm vi kiểm soát trước khi dùng phép so đơn giản.

### 9.2. Semaphore trong Java Sync Driver service

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BoundedOrderLookup {
    private final MongoCollection<Document> orders;
    private final Semaphore permits = new Semaphore(32, true);

    public BoundedOrderLookup(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Document findById(String id) throws InterruptedException {
        // Wait at most 50 ms for local admission.
        boolean admitted = permits.tryAcquire(50, TimeUnit.MILLISECONDS);
        if (!admitted) {
            throw new OverloadedException("MongoDB lookup at capacity");
        }

        try {
            return orders.find(Filters.eq("_id", id))
                .maxTime(400, TimeUnit.MILLISECONDS)
                .first();
        } finally {
            permits.release();
        }
    }

    public static final class OverloadedException extends RuntimeException {
        public OverloadedException(String message) { super(message); }
    }
}
~~~

**Ý nghĩa:** có tối đa 32 calls trong đoạn MongoDB path của instance và mỗi caller chờ permit không quá 50 ms. `Semaphore(32,true)` cố gắng fairness theo thứ tự chờ, nhưng **không tạo hard cap số threads đang chờ permit**. Cần HTTP/request limit hoặc bounded executor ở ngoài để tránh 100.000 callers cùng đợi 50 ms.

### 9.3. Khác biệt giữa `maxTime` và CSOT

Trong ví dụ trên, `.maxTime(400, TimeUnit.MILLISECONDS)` là giới hạn execution time phía server của find; thời gian checkout connection còn phụ thuộc timeout driver. Nếu dùng **CSOT** (Java 5.x), cần chọn deadline phù hợp tổng request; không tưởng rằng `maxTime` cũng giới hạn toàn bộ admission + checkout.

### 9.4. Permit scope phải bao toàn bộ operation

Nếu code:

~~~java
permits.acquire();
MongoCursor<Document> cursor = collection.find(filter).iterator();
permits.release();
while (cursor.hasNext()) {
    consume(cursor.next());
}
~~~

thì permit đã được thả **trước khi toàn bộ cursor được xử lý**, nên concurrency gate không còn đúng. Với cursor dài/streaming, nên:

- Dùng try-with-resources đóng cursor đúng hạn.
- Giữ permit theo thời gian task thực sự tiêu thụ DB resources.
- Có page/batch-size và total deadline.
- Tránh giữ permit khi downstream consumer đang chờ rất lâu không cần thiết; có thể chuyển sang paging/buffering có giới hạn.

### 9.5. Semaphore fairness có giá

Fairness `true` có thể giảm starvation nhưng tăng scheduling overhead và giảm throughput trong vài workload. Không chọn fairness theo cảm giác: đo tail latency theo tenant/priority và retry behavior. Nếu cần QoS cho requests quan trọng, **bulkhead/priority queues** thường rõ ràng hơn một semaphore toàn cục.

## 10. Bounded queue và backpressure: từ chối có kiểm soát

Semaphore giới hạn số **running tasks**, nhưng một hàng đợi không giới hạn phía trước nó vẫn có thể làm JVM thiếu memory. Mô hình production cần xác định **số tasks đang phục vụ + đang đợi**, và chính sách xử lý khi đã đầy.

### 10.1. Unbounded queue là anti-pattern

~~~java
// KHÔNG NÊN cho workload có thể tăng đột biến:
ExecutorService executor = Executors.newFixedThreadPool(32);
~~~

`Executors.newFixedThreadPool(32)` dùng một **unbounded work queue** phía sau 32 threads. Khi 50.000 tasks đến nhanh hơn khả năng xử lý, queue có thể lớn vô hạn về logic, kéo theo heap pressure, GC pauses và timeout hàng loạt.

**Pool threads có giới hạn không có nghĩa queue có giới hạn.**

### 10.2. Bounded `ThreadPoolExecutor`

~~~java
import java.util.concurrent.*;

ThreadPoolExecutor dbExecutor = new ThreadPoolExecutor(
    16,                         // corePoolSize
    16,                         // maximumPoolSize
    0L,
    TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(64), // Queue cap 64
    new ThreadPoolExecutor.AbortPolicy() // Fail fast on saturation
);
~~~

Khi 16 tasks đang chạy và 64 đang chờ, task mới bị `RejectedExecutionException` thay vì nằm vô hạn. Controller/service nên **map lỗi overload** sang response có chủ đích, log metric và giữ deadline phù hợp; không trả stack trace nội bộ cho người dùng.

### 10.3. Đừng vô tình block HTTP thread không giới hạn

~~~java
// Pseudocode cho request handler dùng executor riêng:
try {
    Future<Document> job = dbExecutor.submit(
        () -> orders.find(Filters.eq("_id", orderId)).first()
    );
    return job.get(500, TimeUnit.MILLISECONDS);
} catch (RejectedExecutionException overloaded) {
    // Translate to 503 Service Unavailable or 429 with retry policy.
    throw new ServiceOverloadedException();
} catch (TimeoutException tooSlow) {
    // Timeout HTTP waiting; cancellation is best effort.
    job.cancel(true);
    throw new ServiceDeadlineException();
}
~~~

**Mẫu trên là pseudocode, không phải method Java hoàn chỉnh:** biến `job` phải được khai báo ngoài `try` nếu dùng trong `catch`, và các exception checked/cleanup cần xử lý ở code thực. Điểm học là **không để request vượt deadline chỉ vì đã được đưa vào queue**.

Thậm chí một bounded executor có thể làm HTTP thread bị giữ đến timeout khi gọi `Future.get`. Với API có nhiều I/O, cân nhắc async stack hoặc admission tại ingress (load balancer/API gateway), nhưng vẫn giữ **bounded in-flight operations**.

### 10.4. Dùng `CallerRunsPolicy` có tốt không?

`CallerRunsPolicy` sẽ cho caller thread chạy task khi queue đầy, truyền backpressure bằng cách làm caller chậm lại. Tuy nhiên với HTTP servlet thread, nó có thể **giữ nguyên request thread quá lâu**, khiến ingress thread pool cũng nghẽn; trong event-loop/reactive app, **chạy blocking DB operation trên event loop** là đặc biệt nguy hiểm.

Không chọn `CallerRunsPolicy` chỉ vì nó “không mất request”. Khi deadline ngắn và tải rất cao, **reject sớm** có thể bảo vệ toàn hệ thống tốt hơn.

### 10.5. Bounded queue không nhất thiết luôn FIFO

FIFO thường dễ hiểu nhưng không đủ khi:

- Một tenant gửi hàng nghìn reports, trong khi tenant khác chỉ cần xem một đơn hàng.
- Background jobs tốn 10 giây nằm trước request đăng nhập cần 30 ms.
- Retry requests lặp liên tục khiến original traffic chờ.

Cần policy như **per-tenant caps, priority classes, short/long queues, quotas hoặc weighted fair queuing**. Tránh starvation: ưu tiên cao mãi mãi sẽ làm tác vụ khác không có tiến triển.

### 10.6. Chọn queue length từ wait budget

Một ước lượng đơn giản: service xử lý \(\mu=100\) operations/giây và cho phép **queue wait tối đa 0,1 giây**, thì số đang đợi theo mức trung bình nên gần hoặc dưới:

\[
Q \approx \mu \times W_q = 100 \times 0.1 = 10
\]

Đây là **ước lượng heuristic từ Little's Law**, không là bảo đảm latency p95. Với service times biến thiên và burst, queue length 10 vẫn có thể khiến các request chờ lâu hơn 100 ms. Dùng **queue wait timeout** và đo các percentiles thay vì chỉ Q.

### 10.7. Chính sách khi queue đầy

| Phản ứng | Khi nào phù hợp | Rủi ro |
|---|---|---|
| Trả `HTTP 429` | Client vượt quota/rate limit có thể retry sau. | Retry storm nếu không có `Retry-After`/jitter. |
| Trả `HTTP 503` | Service overload/tạm không thể xử lý. | Cần health/alert và không làm load balancer tháo hết instances vô ích. |
| Giảm chức năng | Bỏ enrichment/report phụ, trả cached hoặc tối giản. | Dữ liệu stale, phải nói rõ SLA/freshness. |
| Queue ngắn có timeout | Spike ngắn, service còn headroom. | Queue quá lớn làm tăng tail latency. |
| Chuyển async job | Report/export không cần response đồng bộ. | Cần durable queue, idempotency, trạng thái job. |
| Drop telemetry non-critical | Khi business cho phép mất mẫu và đã định nghĩa policy. | Không áp dụng cho thanh toán/đơn hàng. |

### 10.8. Rejection phải có observability

Với `ThreadPoolExecutor`, giám sát ít nhất:

- `getActiveCount()` — số threads active gần thời điểm đọc.
- `getQueue().size()` — queue depth.
- `getCompletedTaskCount()` — tasks đã hoàn tất.
- `getTaskCount()` — task count tổng theo executor.
- Counter **rejected tasks** qua custom rejection handler/metrics.
- Latency khi chờ queue và execution time (đo tách riêng).

Không dùng một số đo tại một thời điểm làm kết luận đủ; xem time series p95/p99 trong peak.

## 11. Bulkheads: tách workloads để không tranh hết một pool

Một MongoDB cluster thường phục vụ nhiều loại requests: point lookup nhanh, cập nhật đơn hàng, aggregation dashboard, exports, backfills, transaction dài. Nếu chúng cùng gate, cùng queue và cùng pool, một load nặng có thể làm toàn API hết connection.

### 11.1. Ví dụ hai lớp dịch vụ

~~~text
                    MongoDB Cluster
                       |
          +------------+-------------+
          |                          |
          v                          v
  Interactive API                 Reporting Jobs
  - gate=40                       - gate=4
  - queue=40                      - queue=8
  - pool=64                       - pool=12
  - deadline=500ms                - deadline=20s
  - high priority                 - low priority
~~~

Các số chỉ minh họa. Tách gates/pools giúp reporting không ăn hết application connections của API; **nhưng cả hai vẫn chia sẻ DB CPU/cache/disk** nếu cùng cluster. Với reports rất nặng, có thể cần scheduling, indexes/materialized views hoặc workload isolation ở **cluster/shard tier** thay vì chỉ client-side.

### 11.2. Per-tenant quotas

Một tenant có 10.000 requests/giây không nên khiến 100 tenants còn lại hoàn toàn không có cơ hội. Có thể dùng:

~~~text
Global in-flight cap:       120
Per-tenant in-flight cap:    12
Per-tenant rate limit:       negotiated by plan
Reserved critical capacity:  20
~~~

Nhưng nếu có nhiều **application instances**, một cap 12 trong mỗi pod không phải global cap 12. Với 20 pods, tenant có thể có tới 240 in-flight qua local gates. Để có **global quota**, dùng load balancer/API gateway, distributed token bucket hoặc cơ chế điều phối có tính đến partition/failure.

### 11.3. Weighted fair queuing và starvation

Khi nhiều tenants cùng tranh một resource:

- Chia theo tenant/priority class, cấp quota có trọng số.
- Đặt hard deadline cho tasks quá cũ.
- Không cho task ít ưu tiên bị bỏ đói vô hạn.
- Có reserve cho health checks, auth và critical writes.
- Giới hạn query complexity của tenant/report, không chỉ request count.

Nếu một report chiếm 20 giây server CPU còn một lookup chiếm 10 ms, rate limit **theo requests/giây** đơn thuần không công bằng về consumption. Cân nhắc **cost-aware admission** (ước lượng query complexity hoặc compute budget).

### 11.4. Đừng chia quá nhiều pools

Nếu tạo MongoClient cho mỗi endpoint, tenant hoặc HTTP request, số pools/monitor sockets sẽ tăng theo \(N\), làm quá nhiều connections idle/handshake. **Bulkheads ít nhưng có chủ đích** thường tốt hơn hàng nghìn client instances.

### 11.5. Thực thi fairness trong Java

Một cách đơn giản:

- Gate global (ví dụ 80 permits).
- Gate riêng mỗi tenant (ví dụ 8 permits) với LRU/lifecycle cho tenants không hoạt động.
- Gate riêng báo cáo nền (ví dụ 4 permits).
- Khi request vào, **thử lấy permits theo một thứ tự cố định**, nếu thất bại thả tất cả đã lấy.
- Tạo bounded queue/deadline ở ingress.

Không giữ global permit trong lúc **chờ** per-tenant permit hàng giây: có thể làm cả hệ thống bị block bởi tenant đang bão hòa. Chọn acquire ordering có chủ đích hoặc thử nonblocking rồi rollback permit nếu thất bại.

## 12. Rate limiting khác concurrency limiting

### 12.1. Hai công cụ bảo vệ hai rủi ro khác nhau

**Rate limiter** hạn chế số arrivals theo thời gian, ví dụ 100 req/s. **Concurrency limiter** hạn chế số đang được phục vụ cùng lúc, ví dụ 20 operations.

Một rate 100 req/s không ngăn được 100 requests **cùng đến trong 10 ms** (nếu burst token cho phép). Một concurrency cap 20 cũng không ngăn một tenant gửi 10.000 requests liên tục rồi bị reject hết, gây overhead ingress/logging.

Thường cần **cả hai**:

~~~text
Ingress rate limit / token bucket
           |
           v
Deadline-aware bounded queue
           |
           v
Concurrency limiter / bulkhead
           |
           v
MongoDB driver pool
~~~

### 12.2. Token bucket

Token bucket có capacity \(B\) và refill rate \(r\) tokens/s:

- Mỗi request tiêu một token.
- Khi bucket đủ tokens, burst ngắn được phép.
- Khi hết token, request chờ có hạn hoặc bị reject.
- Một token đơn vị **request count** không phản ánh query cost; có thể tính cost weight theo endpoint/query class.

Ví dụ `r=100 req/s, B=200` có thể cho burst 200 rồi quay về 100 req/s. Nếu mỗi request đồng thời chạy 3 MongoDB operations, tải DB có thể lớn hơn nhiều so với request rate.

### 12.3. Adaptive concurrency control

Giới hạn cố định \(C=40\) có thể không hợp lý khi query mix thay đổi. **Adaptive concurrency** theo latency/queue signals có thể tăng/giảm \(C\) với guardrails:

~~~text
Nếu latency thấp, error thấp, DB có headroom:
  tăng C chậm.

Nếu p95/p99, queue wait, timeout tăng:
  giảm C nhanh hơn, bật load shedding.

Giữ C trong [C_min, C_max].
~~~

Đây là một chiến lược control loop, không phải “cứ p95 tăng là giảm tất cả”. Latency có thể tăng vì network, index missing, failover hoặc service khác; cần phân tích bottleneck và tránh oscillation.

### 12.4. Autoscaling có thể làm overload nặng hơn

Giả sử DB đã saturated, HPA tăng pods từ 10 lên 30 vì HTTP CPU cao. Mỗi pod mới mở pools, tăng tổng requests chạy song song; database **không tăng capacity theo** và latency tiếp tục xấu.

Trong mô hình này:

- Scale ứng dụng chỉ giúp xử lý phần **application-bound**.
- DB-bound workload cần admission/global budget và tối ưu database.
- Scale MongoDB hardware/sharding/indexes khi thực sự cần.
- Cần startup throttling để tránh connection storm.

**HPA và pool limits phải được thiết kế cùng nhau**, nhất là trong triển khai autoscaling theo request count.

## 13. Java Reactive/Async và virtual threads: không có “concurrency miễn phí”

### 13.1. Async I/O không đổi năng lực MongoDB

Một application dùng Java Reactive Streams Driver có thể xử lý 10.000 publishers/subscriptions với ít worker threads hơn một thiết kế blocking. Nhưng nếu tất cả subscriptions gọi `find()` đến cùng primary, server vẫn phải thực thi hàng nghìn commands.

~~~text
Blocking model:
  N tasks -> N Java threads blocked waiting for DB (up to pool/worker limits)

Reactive/async model:
  N tasks -> small number of event-loop threads
           -> still N in-flight or queued DB operations
~~~

Giảm số blocked threads không tự tăng CPU/IOPS của MongoDB. **Reactive stack vẫn cần concurrency cap, bounded buffers và backpressure**.

### 13.2. Không gọi Sync Driver trên event-loop thread

~~~java
// ANTI-PATTERN minh họa trong reactive handler:
Mono.fromCallable(() ->
    syncCollection.find(Filters.eq("_id", id)).first()
);
~~~

Chỉ tạo `Mono.fromCallable` không bảo đảm execution chuyển khỏi event loop; nếu được subscribe và chạy trên event-loop scheduler, call blocking có thể chặn cả loop. Nếu buộc dùng Sync Driver trong Reactor, cần chuyển sang scheduler dành cho blocking I/O **và giới hạn concurrency**:

~~~java
Mono.fromCallable(() ->
        syncCollection.find(Filters.eq("_id", id)).first()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

**Điều kiện:** cần imports và dependencies Reactor tương ứng; `boundedElastic` là bounded ở thread resource nhưng vẫn có thể queue tasks, vì vậy **không** lấy nó làm toàn bộ backpressure policy. Phương án native là dùng **Reactive Streams Driver** với concurrency controls.

### 13.3. Giới hạn `flatMap` concurrency

~~~java
// Pseudocode Reactor, dùng Reactive MongoDB repository được cấu hình:
Flux.fromIterable(orderIds)
    .flatMap(
        id -> repository.findById(id),
        16 // tối đa khoảng 16 inner publishers được subscribe đồng thời
    );
~~~

`flatMap(...,16)` là một mức giới hạn **trong pipeline này**, không phải global cap cho toàn service. Nếu 100 HTTP requests cùng chạy pipeline tương tự, tổng có thể lên tới khoảng 1.600 inner subscriptions. Cần gate ở level request/tenant hoặc trên data access layer khi cần tổng budget.

### 13.4. Backpressure không tự sửa server bottleneck

Reactive backpressure cho phép downstream yêu cầu dữ liệu với tốc độ phù hợp; nhưng:

- Không phải mọi upstream MongoDB command đã gửi đều có thể “unsend”.
- Một subscription có thể giữ cursor và yêu cầu `getMore` nhiều lần.
- Một stage `buffer()` hoặc `collectList()` quá rộng có thể gom toàn bộ dữ liệu vào memory.
- Một stage `parallel()` thiếu giới hạn có thể tạo quá nhiều concurrent writes.

Nên dùng batch/page limits, `limitRate`/concurrency theo semantics của thư viện, deadlines và bounded buffers thay vì tin rằng “non-blocking” tự bảo vệ DB.

### 13.5. Java virtual threads

Java virtual threads giúp rẻ hơn khi nhiều tasks **blocked I/O**, nhưng chúng không thay đổi:

- `maxPoolSize` của MongoDB driver.
- Thời gian thực thi query.
- DB CPU/IOPS/locks/tickets.
- Tổng số requests có thể xếp hàng.

10.000 virtual threads cùng chờ pool 100 connections vẫn là 10.000 pending tasks (dù chi phí thread thấp hơn platform threads). **Dùng semaphore/bounded queue/deadline** ngay cả khi Java code có virtual threads.

### 13.6. Async cancellation và release

Khi client HTTP ngắt kết nối hoặc timeout:

- Propagate cancellation tới DB operation khi driver/framework hỗ trợ.
- Đóng cursor/subscription/session theo lifecycle.
- Release semaphore permits/queue slots trong mọi đường lỗi.
- Tránh double-release khi futures complete/timeout đồng thời.
- Không cho request đã hết deadline tiếp tục chiếm resource vô thời hạn.

Không khẳng định `Future.cancel(true)` luôn lập tức dừng server-side query; cancellation/interrupt có semantics tùy driver, network state và server operation. Dùng deadline và giới hạn thực thi được hỗ trợ, theo dõi các ops còn active.

## 14. Driver telemetry: đo đúng connection checkout

MongoDB Java Driver hỗ trợ **Connection Monitoring and Pooling (CMAP)** events, **Command Monitoring** và **Server Discovery and Monitoring (SDAM)** events. Đây là nguồn có giá trị để phân biệt timeout do pool, do server selection hay do command execution.

### 14.1. Các loại CMAP events cần theo dõi

| Event/metric | Điều nó phản ánh | Cảnh báo |
|---|---|---|
| Pool created/ready/cleared/closed | Lifecycle của pool theo server. | Pool clear liên tục khi network/failover. |
| Connection created/ready/closed | Socket establishment và churn. | Creation storm hoặc close due to errors. |
| Check-out started | Một operation cần mượn connection. | Starts tăng đột biến theo traffic. |
| Check-out succeeded | Connection được mượn. | In-use gần cap trong thời gian dài. |
| Check-out failed | Không lấy được connection. | Pool timeout / closed / error reason. |
| Checked in | Connection được trả pool. | Không có tương ứng với checkout -> nghi leak/long ops. |
| Check-out wait time | Từ started đến success/fail. | p95/p99 tăng dù command execution ổn. |
| In-use connections | Số connections đã checkout. | Chạm maxSize liên tục. |

**Phân biệt:** pool wait là thời gian **trước command**, còn command latency đo **sau khi command gửi**. Đo riêng giúp tránh tăng pool khi thực ra queries đang giữ connection quá lâu.

### 14.2. Một `ConnectionPoolListener` Java đơn giản

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import java.util.concurrent.atomic.LongAdder;

public final class PoolMonitoringExample {

    static class PoolCounters implements ConnectionPoolListener {
        final LongAdder checkedOut = new LongAdder();
        final LongAdder checkoutFailures = new LongAdder();

        @Override
        public void connectionCheckedOut(ConnectionCheckedOutEvent event) {
            checkedOut.increment();
        }

        @Override
        public void connectionCheckOutFailed(ConnectionCheckOutFailedEvent event) {
            checkoutFailures.increment();
        }
    }

    public static MongoClient newClient(String uri, PoolCounters counters) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .addConnectionPoolListener(counters))
            .build();
        return MongoClients.create(settings);
    }
}
~~~

**Đây là ví dụ ghi tổng số events**, không phải implementation metrics hoàn chỉnh. `checkedOut` đang **đếm số checkout successes tích lũy**, **không phải current in-use count**. Để tính current in-use, cần listener `connectionCheckedIn` để decrement counter hoặc dùng JMX/gauges. Khi ghi metrics production, đừng đặt nhãn `inUse` cho một counter tích lũy.

### 14.3. JMX Pool Listener

MongoDB Java Driver cung cấp `JMXConnectionPoolListener` để lấy JMX MXBeans per server với các thuộc tính như:

- `clusterId`, `host`, `port`.
- `minSize`, `maxSize`.
- `size` — pooled connections hiện có.
- `checkedOutCount` — pooled connections đang được sử dụng.

Có thể đăng ký listener theo MongoDB docs rồi xuất dữ liệu qua JMX exporter/Micrometer/Prometheus theo stack giám sát. Không cần expose remote JMX unauthenticated ra Internet.

### 14.4. CommandListener để đo execution

MongoDB Java Driver có `CommandStartedEvent`, `CommandSucceededEvent`, `CommandFailedEvent`. Dùng chúng để đo:

- Các lệnh `find`, `aggregate`, `update`, `insert`.
- Command duration và failures.
- Query shape/collection ở dạng đã **ẩn PII**, không log full payload mặc định.
- Phân biệt latency do MongoDB với latency tại HTTP/queue.

**Cẩn trọng:** Command monitoring không tự quan sát tất cả thời gian application **đợi permit hoặc checkout**. Phải có spans/gauges ở các giai đoạn đó riêng.

### 14.5. SDAM để giải thích server selection

Theo dõi events khi topology đổi:

~~~text
Primary fails
    |
    v
SDAM discovers no eligible primary
    |
    v
Requests wait on server selection
    |
    v
Election/new primary
    |
    v
Pools clear/reconnect, operations retry
~~~

Trong failover, `serverSelectionTimeoutMS` có thể chi phối lỗi. **Tăng `maxPoolSize` không tạo ra primary**, và quá nhiều retries sau election có thể làm primary mới quá tải.

### 14.6. Một trace request hoàn chỉnh

~~~text
traceId=ORD-1001
  HTTP request parse       4 ms
  Auth validation          7 ms
  Admission queue wait    18 ms
  Mongo server selection   2 ms
  Pool checkout wait      34 ms
  MongoDB command         21 ms
  Business transform       5 ms
  HTTP response            3 ms
--------------------------------
  Total                  94 ms
~~~

Số liệu giả định. Nếu `pool checkout` tăng từ 34 lên 180 ms, cần xem pool saturation/churn/cold start. Nếu `command` tăng từ 21 lên 300 ms, cần kiểm index/query/server; tăng pool lúc đó có thể làm tình trạng tệ hơn.

### 14.7. Đặt labels có cardinality thấp

Không gắn `requestId`, `userId` hoặc toàn bộ `queryText` vào label Prometheus — cardinality sẽ bùng nổ và tốn memory/storage. Nên dùng `service`, `deployment`, `cluster`, `serverAddress` ở mức cho phép, `commandName`, `endpointClass`, `outcome`; giữ traceId trong tracing/logs có retention phù hợp.

## 15. MongoDB server-side metrics: nhìn phần DB thật sự

Trên `mongosh` có quyền quan sát server:

~~~javascript
const admin = db.getSiblingDB("admin")
const status = admin.runCommand({ serverStatus: 1 })

printjson(status.connections)
printjson(status.opcounters)
printjson(status.globalLock)
~~~

`serverStatus` có nhiều fields, một số thay đổi theo MongoDB version/Atlas tier. Không assume mọi field đều có trên mọi cluster, và không xuất toàn bộ dữ liệu metrics nhạy cảm vào logs public.

### 15.1. `connections` không đồng nghĩa driver pool wait

Theo MongoDB Manual:

- `connections.current`: số incoming connections hiện tại (bao gồm application, monitors và các nguồn khác).
- `connections.available`: số incoming connections server còn có thể chấp nhận theo giới hạn hiện hành.
- `connections.totalCreated`: counter tổng số connections được tạo từ khi server start.
- `connections.active`: incoming client connections đang có operations in progress (theo version).
- `connections.rejected`: connections bị từ chối; field có mốc phiên bản riêng.

Một server có `current=2.000` nhưng `active=80` có thể chứa nhiều **idle sockets**. Không suy CPU/IOPS đang quá tải chỉ từ `current`; cũng không suy server khỏe chỉ vì `available` còn cao.

### 15.2. `globalLock.currentQueue`

~~~javascript
const st = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 })

printjson(st.globalLock?.currentQueue)
~~~

`globalLock.currentQueue.readers/writers` cung cấp thông tin về operations chờ lock. **Đây không phải hàng đợi driver connection checkout** và không đại diện mọi queue nội bộ MongoDB. Nếu `globalLock.currentQueue` nhỏ mà app pool checkout p99 tăng, bottleneck có thể nằm ở **client**, không nhất thiết là global lock.

### 15.3. MongoDB 8.0+ có các chỉ số admission queues

MongoDB Manual 8.x mô tả các metrics `serverStatus.queues` liên quan ingress/execution admission, cùng các trường version-dependent như `queues.ingress.normalPriority.queueLength` hoặc `queues.execution.read/write`. Mốc thêm và semantics có thể khác giữa patch versions. Những chỉ số này cho thấy **server-side queueing**, nhưng không thay CMAP checkout wait của Java Driver.

Không tự viết monitoring bắt buộc field `queues.ingressSessionEstablishment` nếu deployment chưa tới version được docs giới thiệu (ví dụ một số trường từ MongoDB 8.2).

### 15.4. `db.currentOp()` và `$currentOp`

Với quyền phù hợp, có thể quan sát các operations đang chạy:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  { $match: { active: true } },
  { $project: {
      ns: 1,
      op: 1,
      secs_running: 1,
      waitingForLock: 1,
      appName: 1,
      command: 1
  }}
])
~~~

**Cẩn trọng bảo mật:** `command` có thể chứa query filters hoặc dữ liệu nhạy cảm. Trong production, projection nên hạn chế fields và quyền; không gửi raw output vào nơi không kiểm soát. Output `currentOp` tùy version/topology; lệnh có thể yêu cầu elevated privileges.

### 15.5. Query profiler và `explain`

Khi command duration tăng, trước khi tăng `maxPoolSize` hãy xem:

~~~javascript
db.orders.explain("executionStats").find({
  tenantId: "tenant-a",
  status: "OPEN"
}).sort({ createdAt: -1 }).limit(20)
~~~

Đọc `totalDocsExamined`, `totalKeysExamined`, index scan/collscan và sort stage. Một query quét 1 triệu documents để trả 20 rows **không trở nên rẻ** chỉ vì driver có thêm 100 TCP connections.

Profiler có overhead và quyền riêng; bật theo hướng dẫn và lấy mẫu, không log mọi query production vô hạn.

### 15.6. MongoDB server tickets không bằng `maxPoolSize`

MongoDB/WiredTiger có cơ chế admission/tickets cho read/write operations. Một số server parameters và metrics đổi tên/cách điều chỉnh giữa MongoDB 6.x, 7.x và 8.x (trong 7.x còn có dynamic tuning). **Không tự đặt “storage engine concurrent tickets = pool size”** hoặc thay đổi server parameter nội bộ chỉ để làm con số khớp. Đây là server-side control cần theo release docs/support và thử nghiệm.

### 15.7. Mở nhiều connections có thể làm bệnh nặng hơn

Ví dụ DB bị:

~~~text
High CPU 95%
WiredTiger cache eviction pressure
Slow collection scan
Disk IOPS near limit
~~~

Tăng pool có thể làm thêm commands được gửi tới server, gây contention và làm **command latency tăng**. Tối ưu query/index/data model hoặc tăng server capacity trước; dùng admission gate giữ load trong giới hạn đến khi nguyên nhân được giải quyết.

## 16. Connection storms, failover và retry amplification

Mức tải nguy hiểm nhất không nhất thiết xuất hiện ở steady state. Nó thường xảy ra khi **cả hệ thống phải kết nối lại** sau một sự cố hoặc deploy.

### 16.1. Cold start của hàng chục pods

~~~text
Rolling deploy turns into near-simultaneous restart:

  30 new application pods
    x 1 MongoClient/pod
    x 3 mongos endpoints
    x minPoolSize 20
  = up to 1.800 warm pooled connections intended across routers

  Plus monitoring sockets, admin/services, retries.
~~~

Các con số là **trần/ước lượng**, không chứng minh 1.800 sockets mở đồng thời. Nhưng việc lập một lúc hàng nghìn TLS/auth handshakes có thể tăng CPU/network, kéo dài `maxConnecting` queue và làm HTTP readiness fail.

Biện pháp:

- **Rolling/canary deploy** thay vì restart tất cả pods cùng lúc.
- Warmup có rate limit/jitter.
- Không đặt `minPoolSize` cao hơn nhu cầu thực.
- Điều chỉnh `maxConnecting` có kiểm soát, không tự tăng vô hạn.
- Phân biệt liveness/readiness để không tạo vòng lặp restart.
- Quan sát connection created/closed rate, không chỉ pool size.

### 16.2. Replica set primary election

~~~text
Primary A fails
     |
     +--> Driver SDAM detects topology change
     +--> Pending writes wait for a writable primary
     +--> Pools may clear/reconnect
     +--> New primary B elected
     +--> Backlogged clients retry simultaneously
                |
                v
        Secondary bottleneck becomes new primary bottleneck
~~~

Tăng `serverSelectionTimeoutMS` có thể làm request **chờ lâu hơn** để vượt failover ngắn, nhưng nếu HTTP deadline chỉ 500 ms thì việc chờ 30 giây không giúp trải nghiệm. Ngược lại, timeout cực ngắn có thể tạo fail rate cao trong những elections bình thường. Cần đặt **business deadline**, có fallback/degrade và jitter.

### 16.3. Retry storm

Giả sử DB chịu 800 operations/s nhưng capacity chỉ 600. Nếu 10% requests timeout và clients retry 3 lần, arrival rate hiệu dụng còn có thể cao hơn:

~~~text
Original arrivals:       800 req/s
Retries from timed out:  can add hundreds of req/s
Total DB attempts:       > original rate
~~~

Retries có thể làm overload **tự khuếch đại**. Nên:

- Chỉ retry **lỗi có khả năng hồi phục** và **operation có semantics idempotent/retryable**.
- Giới hạn số attempts + total deadline.
- Dùng **exponential backoff with jitter** (với client yêu cầu tự retry).
- Không retry nếu admission gate đã xác định service đang full.
- Đo **attempt rate** và **original request rate** riêng.
- Có circuit breaker khi dependency unavailable.

### 16.4. Idempotency cho writes

Một request `POST /orders` timeout sau khi database đã insert order nhưng response bị mất. Nếu client retry ngay với ID mới, có thể tạo **hai đơn hàng**. Hãy dùng stable `requestId`/`idempotencyKey` và unique index/transaction phù hợp để xác định kết quả.

~~~javascript
// Minh họa mẫu document có stable business key.
{
  _id: "ORDER-10001",
  tenantId: "tenant-a",
  requestId: "REQ-abc-20261114",
  status: "CREATED"
}
~~~

Không mặc định rằng mọi `updateMany`, aggregate write hoặc multi-step workflow đều được retry an toàn; kiểm tra retryable writes/transactions docs và design của nghiệp vụ.

### 16.5. Network partitions và half-open connections

Nếu firewall/NAT đóng idle sockets, pool có thể chứa stale connections. Request mới checkout rồi gặp network error, driver clear pool/reconnect. Quan sát `connectionClosed` reasons, `maxIdleTimeMS`, `connectTimeoutMS`, server selection timeouts và mạng; không chữa bằng tăng pool mà bỏ qua root cause.

### 16.6. Circuit breaker khác semaphore

| Cơ chế | Quyết định |
|---|---|
| Semaphore/bulkhead | Có permit để chạy cùng lúc không? |
| Rate limiter | Có vượt số request được phép trong khoảng thời gian không? |
| Circuit breaker | Dependency có đang lỗi liên tục đến mức nên dừng gọi tạm không? |
| Timeout/deadline | Operation còn đủ thời gian để hoàn tất hữu ích không? |
| Retry/backoff | Có nên thử lại sau lỗi thoáng qua không? |
| Cache/fallback | Có thể đáp ứng giảm chức năng mà vẫn đúng policy không? |

Các cơ chế bổ sung nhau, không thay thế nhau. Circuit breaker mở không làm MongoDB query đã chạy bị rollback; cancel/cleanup vẫn cần.

### 16.7. Readiness sau reconnect

Readiness check quá nặng (ví dụ mỗi pod chạy aggregation lớn mỗi giây) có thể tạo thêm tải đúng lúc hệ thống phục hồi. Dùng health checks phù hợp với service, không dùng **đường query thật đắt** làm liveness. Tránh kill/restart pod chỉ vì DB failover vài giây; điều đó có thể tạo connection storm lần nữa.

## 17. Load test: tìm “knee point” thay vì đo peak QPS một lần

Mục tiêu load test là tìm vùng nơi **throughput bắt đầu bão hòa nhưng latency/rejections tăng mạnh** (knee point). Đây là mức phù hợp để đặt budget và alarm, không nhất thiết là QPS lớn nhất lúc hệ thống bắt đầu mất requests.

### 17.1. Tạo workload đại diện

Một workload API thường gồm:

| Operation class | Tỷ trọng giả định | Đặc điểm |
|---|---:|---|
| Find order by ID | 55% | Indexed point lookup, read nhanh. |
| Find recent orders | 20% | Equality + sort, cần compound index. |
| Create/update order | 15% | Writes/unique keys, writeConcern. |
| Dashboard aggregate | 8% | Có thể sort/group tốn CPU/IOPS. |
| Export/report | 2% | Cursor lâu, đọc nhiều batches. |

Nếu benchmark 100% `findOne({_id:...})` trong RAM, kết quả không đại diện hệ thống có `aggregate` và write contention. Cần dữ liệu đúng kích cỡ, indexes, document sizes, hot/cold keys, read/write ratios và sharded routing.

### 17.2. Tăng tải từng bước

Ví dụ phương án:

~~~text
Stage A:  100 req/s for 5 min
Stage B:  200 req/s for 5 min
Stage C:  400 req/s for 5 min
Stage D:  600 req/s for 5 min
Stage E:  800 req/s for 5 min
Cool down and observe recovery
~~~

Đây là **kịch bản minh họa**. Test phải chạy trên môi trường có capacity/được phép; đừng gây tải trên production nếu chưa có kế hoạch/guardrails. Chọn thời gian đủ để cache warm, pool ramp, GC và indexes thể hiện trạng thái steady.

### 17.3. Những biểu đồ cần vẽ

- Arrival RPS và completed RPS trên cùng timeline.
- HTTP p50/p95/p99 latency và error/timeout rates.
- MongoDB command p50/p95/p99 theo operation class.
- Driver checkout wait p95/p99; checked-out pool connections.
- New connection creation/closed rate, pool clears.
- Executor queue depth, admission in-flight/reject counters.
- MongoDB CPU/IOPS/cache, active ops, queues/locks.
- JVM CPU/heap/GC, thread counts/event-loop lag.
- Retry attempts vs original requests.

Không chỉ nhìn p50; p99 có thể xấu đi hàng chục lần trong khi p50 gần như không đổi.

### 17.4. Load test mở (open-loop) và đóng (closed-loop)

**Closed-loop**: mỗi virtual user chờ response rồi mới gửi tiếp. Khi server chậm, client tự gửi ít hơn, có thể **che giấu overload** (coordinated omission). **Open-loop**: generator gửi theo lịch arrival rate cố định, giúp nhìn rõ queue growth/rejections khi capacity thiếu.

Nên cân nhắc cả hai:

- Open-loop để test overload control và deadline behavior.
- Closed-loop để mô phỏng user sessions/think time.
- Ghi rõ metric dùng request arrival time hay completion time.
- Tránh generator itself CPU/network saturated làm lệch kết quả.

### 17.5. Tìm knee point bằng hai metric

Giả sử:

| Incoming RPS | Completed RPS | HTTP p95 | Rejected |
|---:|---:|---:|---:|
| 100 | 100 | 60 ms | 0% |
| 300 | 300 | 75 ms | 0% |
| 500 | 500 | 120 ms | 0% |
| 700 | 620 | 650 ms | 4% |
| 900 | 625 | 2.500 ms | 15% |

Các số là **dữ liệu giả định**. Ở khoảng 620 completed RPS, throughput gần như không tăng nhưng p95 và rejection tăng mạnh; đây là dấu hiệu capacity saturation. Một admission gate có thể **giữ latency của accepted requests có giới hạn** bằng cách từ chối sớm phần vượt tải, nhưng phải tính **availability SLO** và hành vi clients.

### 17.6. Thử các giá trị pool và gate có kiểm soát

Thực hiện một grid thử nghiệm, chẳng hạn:

~~~text
Pool maxSize:  32, 64, 128
Gate C:        16, 32, 48
Queue Q:       0, 32, 64
~~~

Không cần brute-force mọi tổ hợp trên production; chọn subset có căn cứ và giữ indexes/corpus/traffic distribution ổn định. Với mỗi tổ hợp đo **throughput bền vững, p95/p99, error/rejection, pool checkout wait, DB CPU/IOPS**.

### 17.7. Tuning `maxConnecting` riêng

Thử cold-start/reconnect traffic và đo:

- Thời gian đưa pool lên mức occupancy cần thiết.
- Connection establishment p95/p99.
- Server handshake/TLS/auth CPU.
- Tốc độ connections created và rejected.
- Ảnh hưởng tới request p99 sau deploy/failover.

Một `maxConnecting` cao giúp khởi động nhanh hơn trong vài trường hợp nhưng cũng tạo connection storm. Tuning `maxPoolSize` không tự tối ưu connection ramp-up.

### 17.8. Phải có overload test và recovery test

Đừng chỉ test tải tăng rồi dừng. Hãy mô phỏng:

1. Load cao ngắn 10–30 giây.
2. Một service instance mất kết nối tạm.
3. Primary election trên replica set lab.
4. Traffic giảm trở lại bình thường.
5. Xác nhận queue **drains**, retries giảm và latency hồi phục.

Hệ thống tốt không chỉ chống overload mà còn **thoát khỏi overload** khi traffic đã giảm.

## 18. Query optimization có thể thay thế việc mở rộng pool

### 18.1. Mỗi query giữ connection càng ngắn, throughput có thể càng tốt

Nếu một `find` mất 100 ms và pool có 20 connections, số operations/s lý thuyết nếu không có wait/overhead là khoảng:

\[
\frac{20}{0.100}=200 \text{ ops/s}
\]

Nếu index cải thiện để operation chỉ mất 10 ms:

\[
\frac{20}{0.010}=2{,}000 \text{ ops/s}
\]

Các số là **giới hạn lý tưởng minh họa**, không phải capacity thật, vì DB CPU/IOPS và requests overhead còn ảnh hưởng. Nhưng xu hướng đúng: **giảm service time** thường đáng giá hơn tăng connections khi server đang bão hòa.

### 18.2. Đặt indexes phù hợp query shape

~~~javascript
// Query thường gặp:
db.orders.find({
  tenantId: "tenant-a",
  status: "OPEN"
}).sort({ createdAt: -1 }).limit(20)

// Index candidate cần kiểm thử:
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
})
~~~

Khi DB dùng index tốt, thời gian giữ connection giảm, CMAP checkout wait có thể giảm **mà không tăng pool size**. Tuy nhiên index có write amplification/storage cost; cần `explain` và benchmark trước.

### 18.3. Tránh N+1 queries

Giả sử HTTP handler đọc 100 order IDs bằng 100 calls nối tiếp:

~~~javascript
// Ý tưởng không tối ưu:
for (const id of ids) {
  db.orders.findOne({ _id: id })
}
~~~

Có thể gom:

~~~javascript
db.orders.find({ _id: { $in: ids } })
~~~

Nếu business constraints cho phép, một batch query giảm network roundtrips và checkout events. Nhưng `$in` quá lớn cũng có thể đắt, vượt limits/response size; nên có **bounded batch size** và backpressure.

### 18.4. Pagination/cursors

Một report trả 2 triệu documents có thể chiếm memory và connection resources lâu. Nên:

- Dùng projection chỉ các fields cần.
- Chia batches/pages theo index stable key.
- Tránh offset pagination `skip` quá lớn khi có thể dùng keyset pagination.
- Đóng cursor đúng hạn, `try-with-resources`.
- Dùng async jobs/streaming với bounded buffers.

**Không** coi một cursor đang mở là một connection luôn bị giữ trong suốt đời trong mọi driver mode; lifecycle checkout có thể khác giữa initial query, `getMore` và transaction. Đo CMAP events để biết actual resource usage.

### 18.5. Bulk writes

Nhiều single inserts có thể tạo nhiều roundtrips/overhead. `insertMany`/`bulkWrite` với **batch size có giới hạn** có thể tăng throughput, nhưng:

- Large batches có thể tăng peak memory và max latency.
- Ordered vs unordered operations có semantics lỗi khác nhau.
- Retry/idempotency cần đúng nghiệp vụ.
- Không để one huge bulk chiếm toàn budget của online API.

Tối ưu bulk writes và admission cho background jobs cùng lúc.

### 18.6. Thay đổi schema/data distribution

Nếu một tenant hoặc shard key quá nóng, tăng pool không chia được hotspot. Có thể cần chọn shard key hợp lý, tách workloads, cache read-only data hoặc thiết kế materialized summaries. Đây là vấn đề **data modeling/routing**, không chỉ transport.

## 19. Ba tình huống thiết kế thực tế

### 19.1. API tìm đơn hàng có p99 tăng theo giờ cao điểm

**Hiện trạng giả định:**

~~~text
10 app pods
1 MongoClient/pod
maxPoolSize=100
HTTP request worker threads/pod=200
Average MongoDB command=18 ms
MongoDB checkout wait p99=420 ms
HTTP p99=650 ms
DB CPU=55%, disk utilization=45%
~~~

Từ các số liệu, có vẻ DB còn một phần headroom, nhưng **checkout wait** cao. Các giả thuyết cần kiểm chứng:

1. App có đang giữ connections lâu vì long cursors/transactions?
2. Có thật 100 connections checked-out liên tục mỗi pod?
3. `maxConnecting` đang làm cold start chậm sau deployment?
4. Có 10 MongoClients khác bị tạo trong mỗi pod mà metrics chưa bao quát?
5. Một số requests gửi 10 queries song song khiến per-request fan-out lớn?
6. Có server selection/churn khiến thời gian checkout bị cộng vào latency?

**Không vội tăng pool**. Nếu CMAP cho thấy checked-out 100/100 và server còn headroom, có thể thử nâng maxSize lên 128 **kèm admission cap, monitoring và rollback**. Nếu checked-out chỉ 20/100 nhưng checkout p99 cao, cần điều tra pool creation/churn/failover thay vì tăng trần.

### 19.2. Report dashboard khiến checkout API timeout

**Hiện trạng giả định:**

~~~text
One shared MongoClient
Pool maxSize=60

Interactive API:
  ~40 short queries concurrent

Dashboard export:
  50 long aggregations concurrently

Observed:
  pool checked-out=60
  waiting API requests=hundreds
  command p99=several seconds
~~~

**Hướng xử lý:**

- Tách **reporting gate C=4 hoặc C=8** và bounded job queue.
- Có thể dùng riêng reporting MongoClient/pool cap nhỏ; tính tổng connections.
- Tối ưu aggregation, indexes và materialized rollups.
- Đưa report lớn thành async job có user status.
- Đặt SLO nhanh cho API và timeout dài có giới hạn cho report.
- Xác minh DB CPU/IOPS vẫn còn đủ cho interactive traffic.

Chỉ chia pools mà **report queries vẫn chiếm toàn CPU/IOPS** thì API có thể vẫn chậm. Cần kiểm soát **server resource consumption** bằng scheduling/tối ưu query/cluster capacity.

### 19.3. HPA tăng pods làm database bị “ngộp”

**Giả định:**

~~~text
5 pods initially
maxPoolSize=100 per pod
Potential primary pool cap=500

Traffic spike -> HPA to 30 pods
Potential primary pool cap=3,000
~~~

Ngay cả khi mỗi pod giữ đúng 100, toàn deployment đã tăng trần 6 lần. Nếu server capacity giữ nguyên, thêm connections có thể chuyển queue sang phía DB, tăng context switching/cache pressure.

**Hướng xử lý:**

1. Đặt **global request/concurrency budget** tại gateway hoặc distributed limiter.
2. Giới hạn per-pod gate theo số pods/HPA range, có capacity planning.
3. Điều chỉnh minPoolSize/warmup/maxConnecting để giảm connect storm.
4. Theo dõi DB bottleneck, không dùng HPA application làm công cụ chữa DB-bound saturation.
5. Nếu nhu cầu bền vững tăng, lên kế hoạch scale MongoDB (CPU/storage/sharding/query design) có kiểm soát.

## 20. Runbook chẩn đoán một incident overload

### Bước 1 — Xác định phạm vi và thời điểm

- API nào bị ảnh hưởng? Read, write, reports hay toàn cluster?
- Lỗi bắt đầu sau deploy, traffic spike, index change, failover hay HPA?
- Có bao nhiêu app pods và MongoClients? Topology replica set hay mongos?
- HTTP p95/p99, error rate, completed QPS thay đổi ra sao?
- MongoDB server có CPU/disk/memory/lock pressure không?

**Không kết luận ngay từ `MongoTimeoutException` rằng pool thiếu kết nối.**

### Bước 2 — Xem theo tầng chờ

~~~text
HTTP latency high?
  |
  +-- HTTP worker queue high?
  |     -> ingress threads, executor, admission
  |
  +-- Admission wait high?
  |     -> concurrency gate too small OR DB slow
  |
  +-- Server selection timeout?
  |     -> topology, primary, network, election
  |
  +-- Pool checkout wait high?
  |     -> in-use near max OR connection creation/churn
  |
  +-- Command duration high?
  |     -> query plan, CPU, I/O, locks/tickets
  |
  +-- Response processing slow?
        -> huge payload, app CPU, GC, network
~~~

### Bước 3 — Kiểm tra driver pool

1. CMAP `connectionCheckOutStarted/CheckedOut/CheckOutFailed`.
2. Current pool size và checked-out count (JMX).
3. Checkout wait p50/p95/p99.
4. Connection created/closed rate, pool-cleared events.
5. `maxConnecting` và min/max pool settings thực tế **sau khi framework overrides**.
6. Số MongoClient instances mỗi process và toàn deployment.

### Bước 4 — Kiểm tra MongoDB server

1. `serverStatus.connections.current/active/available/rejected` theo version.
2. CPU/IOPS/cache/eviction.
3. `globalLock.currentQueue` và `queues` nếu có.
4. `currentOp` để xác định long-running commands.
5. Slow query logs/profiler và `explain` cho query shapes nặng.
6. Replication lag/elections/shard targeting.

Không bật profiler mức tối đa vô thời hạn trên production và không log full confidential queries.

### Bước 5 — Chọn biện pháp khẩn cấp theo bottleneck

| Nếu thấy | Có thể làm |
|---|---|
| DB CPU/IOPS saturated, nhiều long queries | Giảm admission cho reports, giới hạn expensive endpoints, tối ưu query, scale DB sau khi đánh giá. |
| Pool maxed nhưng DB còn headroom | Kiểm long operations, cân nhắc tăng maxSize nhỏ và đo lại, giữ bounded queue. |
| Pool chưa full, created rate cao, checkout slow | Kiểm maxConnecting, minPool warmup, DNS/TLS/network, pool clear/reconnect. |
| No primary/SDAM failover | Kiểm cluster health; tạm degrade/reject và retry có jitter. |
| HTTP threads exhausted | Giảm sync fan-out, dùng executor bounded/async, reject early. |
| Reports gây starvation | Tách reporting bulkhead/queue, schedule jobs. |
| Retry rate cao hơn original traffic | Giới hạn retry, exponential backoff, circuit breaker. |
| New deployment nhân MongoClient instances | Reuse singleton, hạ min pools, rollout từ từ. |

### Bước 6 — Xác minh phục hồi

- Completed throughput có trở về mức ổn định không?
- HTTP p95/p99 và pool checkout p99 giảm chưa?
- Rejected rate có hợp lý, clients có retry có kiểm soát không?
- MongoDB connections/current/active và CPU/IOPS có ổn định không?
- Hàng đợi có **drain** sau khi traffic giảm không?
- Database writes có bị duplicate/mất do retry không?

### Bước 7 — Ngăn lặp lại

1. Ghi incident timeline và bottleneck evidence.
2. Bổ sung alerts cho queue depth, checkout wait và retry amplification.
3. Benchmark query mix + peak traffic trên staging.
4. Điều chỉnh global connection budget/HPA/admission policy.
5. Chỉnh indexes/query plans/data model nếu cần.
6. Test failover/rolling deploy để kiểm reconnect storms.
7. Rollout cấu hình mới bằng canary/feature flags, giữ rollback.

## 21. Một thiết kế reference cho API MongoDB có giới hạn tải

~~~text
                    HTTP clients
                         |
                         v
                    API Gateway
               - rate quota per tenant
               - max body/request size
                         |
                         v
                   App Instances
          +--------------+--------------+
          |              |              |
          v              v              v
     Auth/validation  Deadline context  Tracing
          |
          v
    Per-tenant admission gate
          |
          v
    Global in-flight gate + bounded queue
          |
          +-- capacity exceeded --> 429/503 + bounded retry guidance
          |
          v
      Operation class router
          |
          +-- interactive  -> MongoClient A (small/fast budget)
          |
          +-- background   -> MongoClient B (smaller C, long budget)
          |
          v
       MongoDB cluster
          |
          v
  Driver CMAP/SDAM + Command metrics
  ServerStatus/Profiler/Atlas monitoring
          |
          v
   SLO-aware tuning and alerts
~~~

### 21.1. Những ràng buộc bất biến

- **Một MongoClient ổn định** cho một class workload, không per request.
- **Deadline end-to-end**, không chờ vô hạn ở nhiều tầng.
- **Bounded queue** và rejection policy rõ ràng.
- **Per-tenant/global concurrency** phù hợp với topology/pod count.
- **Pool size theo measured concurrency**, không theo thread count.
- **Query plan/indexes** phải được tối ưu; transport tuning không cứu collection scans.
- **Retry idempotent + capped attempts + jitter**.
- **Observability** phân tách HTTP/queue/checkout/command/server.
- **Canary/rollback** cho thay đổi pool/timeouts/bulkheads.

### 21.2. Số default không phải SLA

MongoDB Java Driver docs hiện hành nêu `maxPoolSize=100` và `maxConnecting=2`. Những số đó **không phải đề xuất nên dùng cho mọi sản phẩm** và cũng không mang ý nghĩa “MongoDB xử lý tối ưu 100 operations đồng thời”. Chúng là defaults được driver thiết kế để hoạt động trong nhiều tình huống, còn cần đo workload thật.

### 21.3. Lưu ý cho multi-cluster/multi-region

Nếu requests có thể đi tới nhiều MongoDB clusters theo region/tenant, phải đặt budget **theo destination cluster/server**. Một global admission cap 100 trên application không ngăn một destination nhận 95 requests nặng trong khi destination khác chỉ nhận 5. Dùng partitioned gates và monitoring theo cluster để phát hiện hotspot.

### 21.4. Bảo vệ đường admin/health

Giữ capacity tối thiểu cho **health checks, essential admin queries và incident diagnostics**. Nhưng không mở API admin với quyền cao qua Internet chỉ để có đường “bypass rate limiting”. Dùng authentication, authorization, network controls và reserved admission riêng cho operations được phép.

## 22. Những hiểu lầm thường gặp

| Hiểu lầm | Vì sao không đúng | Cách làm phù hợp |
|---|---|---|
| “Tăng `maxPoolSize` luôn tăng throughput.” | DB có thể đã bão hòa CPU/I/O/locks. | Đo checkout + command latency + server resource trước. |
| “Pool=100 nghĩa là tối đa 100 connections trên toàn cluster.” | Giới hạn **theo server và MongoClient**. | Tính pods × clients × per-server pool cap. |
| “Mỗi HTTP request cần một MongoClient.” | Tạo nhiều pools, topology monitors và TLS handshakes. | Reuse singleton/client theo workload. |
| “100 worker threads thì pool phải bằng 100.” | Không phải mọi thread đang dùng DB; fan-out thay đổi. | Đo concurrent checked-out connections. |
| “Có 2.000 connections.current thì DB có 2.000 queries active.” | Nhiều sockets idle/monitor. | Xem `connections.active`, CMAP và currentOp. |
| “`maxConnecting=100` chắc chắn nhanh hơn 2.” | Tạo connection storms/TLS/auth load. | Tuning cold start có kiểm soát. |
| “`minPoolSize=100` làm tất cả pods ready tức thì.” | Pool warmup vẫn chịu connection establishment. | Rollout/warmup rate-limited, readiness. |
| “`maxIdleTimeMS=0` luôn tốt nhất.” | Stale sockets và idle footprint có thể cao. | So với NAT/firewall idle timeout và churn. |
| “`waitQueueTimeoutMS` giới hạn queue size.” | Chỉ giới hạn thời gian chờ (legacy), không giới hạn số waiters. | Bounded ingress queue/admission. |
| “`waitQueueTimeoutMS` và CSOT `timeoutMS` luôn hoạt động cùng lúc.” | Tùy Java Driver version, CSOT có thể ignore legacy options. | Chọn mô hình deadline theo docs. |
| “`maxTimeMS` tính cả thời gian request chờ pool.” | Server-side execution limit không bao trùm client wait. | End-to-end deadline/CSOT khi phù hợp. |
| “`socketTimeoutMS` là cách tốt để chặn query chậm.” | Socket timeout không phải giới hạn server execution chuẩn. | Query plan + `maxTimeMS` hoặc CSOT. |
| “Server selection timeout là do pool thiếu.” | Không có primary phù hợp hoặc topology/network issue. | SDAM/replica set diagnostics. |
| “`MongoTimeoutException` nghĩa là write chưa ghi.” | Response có thể bị mất sau khi server commit. | Idempotency/retryable write semantics. |
| “Semaphore 20 tự giới hạn waiting threads=20.” | Có thể vô hạn callers đang chờ permit. | Bounded HTTP/executor queue, short admission wait. |
| “Fixed thread pool 32 có hàng đợi 32.” | `newFixedThreadPool` mặc định dùng unbounded queue. | `ThreadPoolExecutor` + bounded queue. |
| “`CallerRunsPolicy` luôn an toàn.” | Có thể block HTTP/event loop. | Chọn rejection/async policy phù hợp. |
| “Reactive không có backpressure problem.” | Async vẫn tạo nhiều in-flight DB operations. | `flatMap` concurrency + global gate. |
| “Virtual threads giải quyết DB bottleneck.” | Chỉ giảm chi phí blocking thread. | Giới hạn in-flight/queue và tối ưu MongoDB. |
| “Càng nhiều parallel requests thì p99 càng thấp.” | Queueing/contension tăng ở gần saturation. | Tìm knee point và headroom. |
| “HTTP QPS=DB operation QPS.” | Một request có thể làm 0, 1 hoặc nhiều DB calls. | Đo MongoDB command rate riêng. |
| “Rate limit 100/s đủ để chặn burst 100 req cùng lúc.” | Token bucket có burst capacity. | Thêm concurrency cap. |
| “Concurrency limit 20 đồng nghĩa rate tối đa 20/s.” | Mỗi slot có thể xử lý nhiều req/s khi nhanh. | Phân biệt in-flight và arrivals/s. |
| “Global limit 10 trong mỗi pod là limit 10 của service.” | 20 pods có thể tạo tới 200 in-flight. | Distributed/global quota hoặc ngân sách theo replicas. |
| “Chia pool A/B bảo đảm reports không làm DB chậm.” | Cùng chia CPU/IOPS/cache ở server. | Server resource budgeting/query optimization. |
| “Tăng HPA luôn chữa latency.” | DB-bound load có thể nặng hơn vì pools tăng. | Global budget + DB scale strategy. |
| “Rerun timeout requests vô hạn sẽ hồi phục.” | Retry amplification đẩy DB quá tải hơn. | Deadline/backoff/jitter/circuit breaker. |
| “Nếu command time thấp, HTTP latency luôn thấp.” | Queue/admission/checkout/network/GC cộng thêm. | Distributed traces từng tầng. |
| “`globalLock.currentQueue` là hàng đợi pool driver.” | Đây là server-side lock queue, không phải CMAP wait. | Tách client và server metrics. |
| “Pool checkedOut counter tích lũy là current in-use.” | Cần checked-in events/gauge. | Dùng gauges/JMX đúng nghĩa. |
| “Mọi `serverStatus` fields có trên mọi version/tier.” | Fields/version/Atlas tiers có thể khác. | Kiểm docs/version và handle missing fields. |
| “Load test chỉ cần đo QPS đỉnh.” | QPS có thể dừng tăng khi p99/errors bùng nổ. | Đo sustained throughput + latency + error rate. |
| “Load generator closed-loop cho biết đúng overload.” | Nó giảm arrivals khi responses chậm. | Bổ sung open-loop workload/test. |
| “Đổi index không liên quan connection pool.” | Query nhanh hơn giữ connection ngắn hơn. | Ưu tiên query optimization. |
| “Cursor dài phải được load toàn bộ vào List.” | Có thể gây memory spike và giữ resource. | Batch/page/cursor lifecycle. |
| “Hết timeout thì phải tăng lên 2 phút.” | Có thể che backlog và vi phạm SLO. | Chẩn đoán stage trước, deadline theo business. |
| “Autoscaling pods có pool=100 vẫn giữ DB connection cap=100.” | Mỗi pod/client có pool riêng. | Capacity planning cho maximum replicas. |

### 22.1. Năm câu hỏi khi review cấu hình

1. **Mỗi application instance có bao nhiêu MongoClient và bao nhiêu pools trên mỗi topology?**
2. **In-flight operations và queue depth được giới hạn ở tầng nào?**
3. **Deadline tổng của request là bao nhiêu?** Admission wait, pool checkout và server execution có phù hợp không?
4. **DB thực sự bão hòa ở đâu?** CPU, I/O, indexes, locks, storage tickets, shard hotspot?
5. **Khi quá tải, hệ thống làm gì?** Reject/degrade, retry có giới hạn, drain và recover thế nào?

## 23. Bài tập thực hành và đáp án

Các bài dùng môi trường giả định; khi có yêu cầu thử thực tế, dùng **replica set/Atlas lab được phép**, dataset tạo riêng và giới hạn tải. Các con số QPS/latency là để học cách suy luận, **không phải benchmarks đã chạy**.

### Bài 1 — Per-server pool

**Đề:** Một MongoClient kết nối replica set 3 members, `maxPoolSize=100`. Có phải tổng trần pooled connections của client vào toàn replica set là 100?

**Đáp án:** Không. Driver duy trì **pool theo server**, mỗi pool có trần 100. Traffic thực phụ thuộc read preference/topology; còn monitoring sockets ngoài pool. Không phải 300 connections chắc chắn mở ngay.

### Bài 2 — Nhiều pods

**Đề:** Có 12 pods, mỗi pod 1 MongoClient, `maxPoolSize=50`, phần lớn traffic tới primary. Trần application pooled connections tới primary là bao nhiêu?

**Đáp án:** \(12\times50=600\), chưa kể monitoring sockets, admin/services, và chỉ là **trần cấu hình** chứ không phải số sockets nhất định đang mở.

### Bài 3 — Nhiều MongoClient

**Đề:** Mỗi pod tạo 4 MongoClients, có 25 pods, pool max 80/server/client. Trần app connections tới một primary nếu cả bốn clients dùng server đó?

**Đáp án:** \(25\times4\times80=8{,}000\). Đây là lý do không tạo MongoClient trong request và phải tính tổng pool budget.

### Bài 4 — Little's Law

**Đề:** 600 MongoDB operations/s, trung bình mỗi operation giữ connection 20 ms. Ước lượng số operations đang dùng connection trung bình?

**Đáp án:** \(L=600\times0.020=12\). Không lấy số 12 làm pool size tối ưu vì cần headroom cho peaks và phân phối latency.

### Bài 5 — Service time giảm

**Đề:** Một query trung bình giảm từ 100 ms xuống 25 ms nhờ index. Trong điều kiện lý tưởng, cùng 20 connections có khả năng phục vụ thay đổi thế nào?

**Đáp án:** \(20/0.1=200\) ops/s so với \(20/0.025=800\) ops/s; throughput tiềm năng tăng 4 lần nếu các bottleneck khác không cản. Không khẳng định DB thật sẽ đạt đúng 800 ops/s.

### Bài 6 — Arrival vượt capacity

**Đề:** DB phục vụ bền vững 400 ops/s, ứng dụng gửi 650 ops/s và không có rejection. Queue có thể tăng nhanh cỡ nào?

**Đáp án:** \(650-400=250\) ops/s trong mô hình đơn giản. Sau 8 giây có thể tồn khoảng 2.000 pending ops nếu điều kiện giữ nguyên, làm timeout/retries tăng. Cần admission/queue cap.

### Bài 7 — Threads và pool

**Đề:** Server có 300 HTTP threads, nhưng p95 đồng thời chỉ 25 MongoDB calls. `maxPoolSize=300` có chắc hợp lý?

**Đáp án:** Không. Thread count không bằng DB concurrency. Chọn pool theo checked-out metrics, checkout wait, peaks và server capacity; 300 có thể tạo trần quá lớn.

### Bài 8 — `maxConnecting`

**Đề:** Pool max=100, min=0, `maxConnecting=2`. Sau restart, 100 requests cùng query. 100 sockets có mở ngay cùng lúc không?

**Đáp án:** Không; tối đa số connections **đang establishment đồng thời** trên pool theo `maxConnecting`. Others có thể chờ; cold-start latency sẽ phụ thuộc handshake/network và connection reuse.

### Bài 9 — `minPoolSize`

**Đề:** 50 pods cùng đặt min=40, kết nối một primary. Ít nhất mức target pooled connections được duy trì là bao nhiêu khi đã warm?

**Đáp án:** Về cấu hình, khoảng \(50\times40=2{,}000\) pooled connections tới primary khi mỗi client/pool được duy trì ở mức min; không bảo đảm tất cả đã mở tức thì. Cân nhắc handshake storm và footprint.

### Bài 10 — Pool đã đạt max

**Đề:** Pool max=20, tất cả 20 connections checked out, request mới tới. Điều gì xảy ra?

**Đáp án:** Driver đợi connection available/checkout theo timeout/deadline, không tạo connection thứ 21 vượt max chỉ cho request đó. Nếu hết thời gian, có thể phát sinh checkout timeout exception.

### Bài 11 — `waitQueueTimeoutMS`

**Đề:** `waitQueueTimeoutMS=5000` có giới hạn queue tối đa 5.000 entries không?

**Đáp án:** Không. Đây là thời gian chờ connection tối đa theo legacy semantics, **không** giới hạn queue length. Cần bounded admission/executor queue.

### Bài 12 — CSOT + legacy wait

**Đề:** Java Driver 5.x cấu hình `timeoutMS=250` và `waitQueueTimeoutMS=5000`. Có nên kỳ vọng checkout chờ tối đa 5 giây không?

**Đáp án:** Không. Theo docs CSOT hiện hành, `timeoutMS` áp deadline operation và có thể ignore legacy timeout options khi đã set. Kiểm chính xác version/inheritance.

### Bài 13 — `serverSelectionTimeoutMS`

**Đề:** Lỗi “no primary found” xảy ra trong replica set election, pool chưa full. Tăng `maxPoolSize` có giải quyết không?

**Đáp án:** Không; lỗi ở **server selection/topology**, không phải thiếu pooled connections. Kiểm SDAM, election, network và deadline/retry policy.

### Bài 14 — `maxTimeMS`

**Đề:** Query có `maxTimeMS=100` nhưng chờ 800 ms trong HTTP executor trước khi vào DB. Request có hoàn tất trong 100 ms không?

**Đáp án:** Không. `maxTimeMS` giới hạn server execution theo support, không bao gồm application queue/checkout. Cần end-to-end deadline và admission wait budget.

### Bài 15 — Cấu hình timeout dài hơn SLA

**Đề:** HTTP SLO 250 ms, nhưng pool wait timeout 120 giây. Có hợp lý không?

**Đáp án:** Thường không. Deadline nên thống nhất và từ chối sớm khi không còn thời gian phục vụ; không giữ hàng nghìn requests đang chờ vô ích.

### Bài 16 — MongoClient per request

**Đề:** API tạo một MongoClient trong mỗi request rồi đóng ngay. Tại sao latency và connections tăng?

**Đáp án:** Repeated topology monitoring, pool creation, TLS/auth handshakes và socket churn. Reuse một MongoClient thread-safe theo application lifecycle.

### Bài 17 — Semaphore

**Đề:** `Semaphore(16)` bao 1 call MongoDB; 200 callers chờ `acquire()` không timeout. Hệ thống có bị queue overload không?

**Đáp án:** Có thể. Semaphore giới hạn 16 running nhưng **không giới hạn waiting callers**. Dùng `tryAcquire(timeout)` và bounded HTTP/executor queue.

### Bài 18 — Executor fixed

**Đề:** `Executors.newFixedThreadPool(20)` có nghĩa chỉ 20 tasks được gửi vào hệ thống cùng lúc?

**Đáp án:** Không. Chỉ giới hạn 20 worker threads; queue mặc định **unbounded**. Dùng `ThreadPoolExecutor` với `ArrayBlockingQueue` và rejection handler.

### Bài 19 — CallerRunsPolicy

**Đề:** Khi executor queue đầy, `CallerRunsPolicy` cho HTTP/event-loop thread tự chạy blocking MongoDB query. Luôn tốt?

**Đáp án:** Không. Có thể block request thread/event loop và lan overload sang upstream. Chọn rejection/degrade hoặc async strategy phù hợp SLO; đừng gọi blocking code trên event loop.

### Bài 20 — Reactive `flatMap`

**Đề:** Mỗi request Reactor dùng `flatMap(...,16)`. 100 requests đồng thời có thể tạo bao nhiêu inner operations?

**Đáp án:** Có thể gần 1.600 subscriptions nếu tất cả đều chạy và mỗi request có đủ items; `16` chỉ là **local concurrency**, không là global cap. Cần global/per-tenant admission khi cần.

### Bài 21 — Virtual threads

**Đề:** Service chuyển từ platform threads sang Java virtual threads, cùng MongoDB Sync Driver. Có thể bỏ giới hạn 64 in-flight queries không?

**Đáp án:** Không. Virtual threads giảm chi phí blocking nhưng DB/connection pool/CPU/IOPS không có capacity vô hạn. Cần bounded admission, deadline và đo query duration.

### Bài 22 — Global vs per-pod limit

**Đề:** Mỗi pod có gate 10 permits, hệ thống có 30 pods. Tenant A không có quota ở gateway. Có thể có tối đa bao nhiêu operations cùng lúc theo các gate đó?

**Đáp án:** Về trần local, tổng gần \(30\times10=300\) operations trên toàn deployment (nếu tất cả dành cho A). Cần distributed/per-tenant global quota nếu business chỉ cho A=10.

### Bài 23 — Rate limiting

**Đề:** Token bucket refill 100 req/s, burst capacity 250. Có thể có 250 requests đến gần như cùng lúc không?

**Đáp án:** Có nếu bucket đầy. Rate limiting không thay **concurrency limiting**; cần gate để bảo vệ DB khỏi simultaneous burst.

### Bài 24 — Retry storm

**Đề:** DB đang quá tải, 20% requests timeout, application retry ngay 3 lần. Điều gì có thể xảy ra?

**Đáp án:** Request attempts tăng mạnh, cạnh tranh tài nguyên cao hơn, tạo feedback loop khiến overload kéo dài. Giới hạn retries/deadline, exponential backoff + jitter, load shedding và idempotent writes.

### Bài 25 — Timeout write không rõ kết quả

**Đề:** Client gọi `insertOne` rồi timeout trước khi nhận response. Có thể retry với `_id` mới mà không kiểm tra không?

**Đáp án:** Không. Server có thể đã ghi thành công. Dùng stable business ID/idempotency key, retryable write semantics và kiểm tra trạng thái trước khi tạo thao tác mới; nếu không có thể tạo duplicate.

### Bài 26 — Read preference secondary

**Đề:** Chuyển read sang secondary có chắc giảm pool wait và tăng throughput không?

**Đáp án:** Không chắc. Driver sẽ cần pools tới secondaries, có thể giảm áp lực primary nhưng gặp replication lag/consistency tradeoffs; secondary CPU/IOPS cũng có giới hạn. Phải đo và tuân thủ read consistency business.

### Bài 27 — 2 mongos routers

**Đề:** Mỗi MongoClient kết nối hai mongos, `maxPoolSize=80`. Có phải mỗi client chỉ có 80 pooled connections tổng?

**Đáp án:** Không, pool áp dụng **per server/router** mà driver sử dụng. Có thể có hai pools với trần 80 mỗi router, tùy topology/traffic. Còn monitoring sockets và clients khác.

### Bài 28 — Pool metrics

**Đề:** Counter `checkedOut` tích lũy tăng 100.000 trong 5 phút. Có phải đang có 100.000 connections in use?

**Đáp án:** Không. Đó là **số lần checkout successes**, không là current in-use gauge. Dùng checked-in events/JMX `checkedOutCount` để biết hiện trạng.

### Bài 29 — Driver wait vs server wait

**Đề:** Checkout wait p99=200 ms, command execution p99=10 ms, DB CPU=30%. Nên kiểm tra gì đầu tiên?

**Đáp án:** Pool occupancy, maxConnecting/cold start, connection churn, MongoClient count và queue ở app. Tăng DB CPU capacity chưa chắc giải quyết. Chỉ tăng maxPoolSize khi evidence cho thấy pool cap thực sự là bottleneck và server còn headroom.

### Bài 30 — DB saturated

**Đề:** MongoDB CPU=97%, disk IOPS near limit, command p99=1.200 ms, pool max=100, current checked-out=95. Có nên tăng pool lên 1.000?

**Đáp án:** Thường không. Thêm commands có thể làm contention tệ hơn. Giảm admission/expensive reports, tối ưu query/index/sharding/storage hoặc scale DB; đo trước/sau.

### Bài 31 — `serverStatus.connections.current`

**Đề:** `connections.current=1500` nhưng `connections.active=70`. Có thể kết luận có 1.500 operations đang chạy không?

**Đáp án:** Không. `current` gồm idle sockets và sources khác; `active` gần hơn với connections có operations in progress (theo version). Dùng CMAP, currentOp và CPU/IOPS để kiểm bottleneck.

### Bài 32 — Lock queue

**Đề:** `globalLock.currentQueue.writers` tăng, nhưng Java CMAP checkout wait thấp. Điều này nói gì?

**Đáp án:** Bottleneck có thể nằm ở **server lock/admission contention**, không phải connection pool checkout. Điều tra long transactions, DDL, query patterns và server resource; không tăng pool theo phản xạ.

### Bài 33 — MongoDB 8.x queues

**Đề:** Monitoring code truy cập `serverStatus.queues.ingressSessionEstablishment` trên MongoDB 7.0 và field không tồn tại. Có phải server hỏng?

**Đáp án:** Không; nhiều fields trong `queues` có **version/patch gates**. Xây dashboard version-aware, không giả định mọi cluster trả cùng schema `serverStatus`.

### Bài 34 — HPA scale

**Đề:** 8 pods × pool100 tăng lên 40 pods × pool100, primary không scale. Trần app connections tăng bao nhiêu lần?

**Đáp án:** Từ 800 lên 4.000, **5 lần**. Tăng connection cap không tăng DB execution capacity. Cần global admission budget và scaling strategy.

### Bài 35 — Bounded queue từ Little's Law

**Đề:** Service hoàn thành 200 operations/s, muốn queue wait trung bình khoảng 50 ms. Queue length trung bình tương ứng khoảng bao nhiêu?

**Đáp án:** \(Q\approx200\times0.05=10\) items. Đây là **heuristic trung bình**, không bảo đảm p95; cần max wait/queue cap và load tests.

### Bài 36 — Load test closed-loop

**Đề:** 100 virtual users gửi request tiếp theo chỉ khi request trước trả về. Khi latency tăng, incoming RPS giảm. Vì sao benchmark có thể che overload?

**Đáp án:** Closed-loop làm arrivals tự giảm theo response time (**coordinated omission**), không đo đúng hành vi khi external demand cố định. Thử thêm open-loop fixed arrival rate để quan sát queue growth/rejections.

### Bài 37 — Knee point

**Đề:** Completed RPS tăng từ 100 lên 620 khi incoming tăng, sau đó giữ ~625 dù incoming lên 900, trong khi p95 từ 120 ms lên 2.500 ms. Kết luận?

**Đáp án:** Hệ thống có dấu hiệu bão hòa quanh ~620 ops/s với workload giả định. Cần đặt headroom, bounded admission và điều tra server bottleneck; không xem 900 incoming RPS là throughput thành công.

### Bài 38 — N+1 query

**Đề:** Mỗi request cần lấy 100 orders, code gọi 100 `findOne` nối tiếp. Làm sao giảm pressure lên pool/network?

**Đáp án:** Cân nhắc batch `find({_id:{$in:ids}})` với bounded IDs/projection/response size và index phù hợp. Không dùng một `$in` khổng lồ; kiểm required consistency và pagination.

### Bài 39 — Cursor dài

**Đề:** Một report mở cursor rồi chuyển dữ liệu từng row lên client rất chậm, trong khi interactive API đang đợi connection. Hướng xử lý?

**Đáp án:** Tách reporting bulkhead/queue, giới hạn batch/page, đóng cursor đúng lúc, tối ưu query, đưa export thành async job. Theo dõi CMAP để biết cursor làm giữ/mượn connection ra sao, không mặc định mọi cursor luôn pin một socket.

### Bài 40 — Thiết kế admission cho một API

**Đề:** Có 15 pods, mỗi pod 1 MongoClient pool max64/server; hai loại workload: orders API phải p95 dưới 300 ms, reports có thể mất 15 giây. Đưa ra một phương án **có thể kiểm chứng**, không chỉ nêu cấu hình.

**Đáp án gợi ý:**

1. Inventory read/write traffic và query shapes, đo command latency, in-use pools và checkout wait.
2. Tính trần connections tới primary: \(15\times64=960\) pooled app connections (chưa tính monitors/clients khác), không đồng nghĩa 960 operations đang chạy.
3. Giữ MongoClient singleton cho orders; cân nhắc report client/queue riêng với cap nhỏ.
4. Đặt rate limit ở gateway và gate cho interactive operations, có short bounded queue và reject 429/503 khi full.
5. Đưa reports dài thành async jobs, gate riêng C nhỏ và queue có capacity.
6. Chọn deadline end-to-end theo 300 ms SLO orders; report deadline dài nhưng có giới hạn, không cộng hàng chờ 2 phút vô thức.
7. Đặt CMAP/JMX metrics, SDAM failover, command p95/p99, MongoDB CPU/IOPS/queues, HPA/pod count.
8. Load test open-loop với mix thật, tìm knee point, so các gate/pool settings và chọn headroom.
9. Canary triển khai, đo rejected rate, error rate, database pressure và API p95/p99.
10. Test failover/reconnect storms, retries có jitter/idempotency và drain queues khi load giảm.

Đáp án tốt phải chứng minh **vì sao** chọn cap, queue và timeout bằng measurements; không được tuyên bố “pool64 là tối ưu” khi chưa biết workload.

## 24. Bảng quyết định nhanh: điều chỉnh ở tầng nào?

| Dấu hiệu đáng tin | Đừng vội làm | Ưu tiên điều tra |
|---|---|---|
| Checkout wait p99 cao, checked-out sát `maxPoolSize`, DB còn headroom | Tăng maxPoolSize lên gấp 10 ngay. | Long operations, client count, cap vừa phải + gate + canary. |
| Checkout wait cao, pool còn nhiều available sockets | Tăng maxPoolSize. | CMAP timing, pool clear, stale sockets, `maxConnecting`, topology. |
| Server selection timeout | Tăng pool. | Primary/secondary eligibility, election, DNS/TLS/network. |
| Command p99 cao, CPU/IOPS sát giới hạn | Tăng pool. | Indexes, scans, expensive aggregations, admission, DB capacity. |
| HPA scale tăng và connections.totalCreated tăng vọt | Nâng minPoolSize mọi pod. | Singleton client, stagger rollout, warmup, global connection budget. |
| HTTP p99 cao nhưng Mongo command p99 thấp | Nâng DB hardware. | Ingress queue, admission wait, checkout, GC/network. |
| Report làm API hết slots | Cho reports dùng pool chung lớn hơn. | Separate bulkhead/async jobs/query optimization. |
| Hàng đợi tăng liên tục khi traffic vượt capacity | Tăng queue vô hạn. | Bounded queue, rejection/degrade, rate/concurrency limit. |
| 429/503 tăng trong spike nhưng accepted-request latency ổn | Xóa admission limit. | Đánh giá product availability SLO, quotas, capacity, client retry behavior. |
| Write timeout sau network event | Retry tạo ID mới vô điều kiện. | Retryable write semantics, stable idempotency key, verify outcome. |
| P99 xấu sau failover | Restart toàn bộ pods đồng thời. | SDAM, reconnect storm, retry jitter, gradual recovery. |
| Chỉ một tenant làm chậm hệ thống | Tăng maxPoolSize cho mọi tenant. | Per-tenant limits, expensive query quotas, fairness. |

### 24.1. Checklist triển khai cấu hình mới

1. Ghi lại **server/driver/framework version** và thông số hiện tại thực tế.
2. Chọn metric/SLO cần cải thiện: checkout p99, HTTP p95, throughput, retry rate, error budget.
3. Xác định bottleneck bằng tracing/CMAP/command/server metrics.
4. Đưa ra **một giả thuyết**: ví dụ pool max đang thấp **và DB còn capacity**.
5. Chọn thay đổi nhỏ, tính connection budget khi HPA đạt max pods.
6. Chạy load test với mix query thực tế, bao gồm burst/recovery.
7. Canary rollout, giữ metrics và rollback.
8. Không tự động tăng mọi pool/timeout cùng lúc vì sẽ không biết yếu tố nào tạo thay đổi.

### 24.2. Các biến nên lưu trong bảng cấu hình vận hành

~~~text
service = orders-api
environment = production
driver_version = 5.x.y
server_version = <cluster version>
mongo_clients_per_pod = 1
max_pods = 30
read_preference = primary
max_pool_size_per_server = 64
min_pool_size_per_server = 4
max_connecting_per_pool = 4
application_in_flight_limit_per_pod = 40
application_queue_capacity_per_pod = 40
admission_wait_budget_ms = 50
mongo_operation_deadline_ms = 600
http_deadline_ms = 900
retry_max_attempts = 2
retry_backoff = exponential_with_jitter
~~~

Đây là một **mẫu manifest minh họa**, không phải các giá trị được khuyến nghị chung. Trong production, cần bổ sung actual pod count, query mix, pool/SDAM metrics, server capacity và SLO/thresholds.

## 25. Tài liệu MongoDB chính thức

Những trang dưới đây là nguồn đối chiếu cú pháp và semantics. **Ưu tiên tài liệu đúng MongoDB Java Driver version**, vì các defaults và timeout options có thể thay đổi giữa các dòng.

### 25.1. Java Driver connection pool và timeout

1. [Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — per-server pools, `maxSize`, `minSize`, `maxConnecting`, `maxWaitTime`, lifecycle.
2. [Java Sync Driver — Client-side Operation Timeout (CSOT)](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — `timeoutMS`, Builder `timeout()`, inheritance và các legacy timeouts bị ignore.
3. [Java Sync Driver — Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/) — `connectTimeoutMS` và `socketTimeoutMS`.
4. [Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — `serverSelectionTimeoutMS`, `localThresholdMS`.
5. [Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/) — server selection errors, network, unavailable primary, pool behavior.
6. [MongoDB Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — URI options, version-specific timeout semantics và client pooling configuration.
7. [MongoDB Connection Pool Overview](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/) — pool options/defaults ở mức manual, `maxConnecting` và monitor sockets; cần đối chiếu driver-specific docs.

### 25.2. Monitoring

8. [Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — CMAP `ConnectionPoolListener`, CommandListener, SDAM/JMX metrics.
9. [`serverStatus` Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server connections, `globalLock`, `queues` theo version, storage engine statistics.
10. [`currentOp` Command](https://www.mongodb.com/docs/manual/reference/command/currentOp/) — active operations, waitingForLock, progress, per-namespace metrics.
11. [`$currentOp` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/) — xem operations ở server/cluster theo quyền và version.
12. [Analyze MongoDB Performance](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/) — connection counts, locks, slow queries và phần mềm/OS bottlenecks.
13. [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — đọc execution plan, scans, sort và query optimization.

### 25.3. Concurrency, transactions và query performance

14. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — session/transaction resources, lifetime và error handling.
15. [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — cache/concurrency/storage engine hoạt động.
16. [MongoDB Server Parameters](https://www.mongodb.com/docs/manual/reference/parameters/) — storage-engine concurrent tickets/limits thay đổi theo version; không tự chỉnh nếu chưa có hướng dẫn.
17. [MongoDB Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/) — giảm thời gian query, chọn index phù hợp.
18. [`maxTimeMS` Operation](https://www.mongodb.com/docs/manual/reference/method/cursor.maxTimeMS/) — server-side time limits, khác client queue/CSOT.
19. [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry semantics và idempotency considerations.
20. [Connection Pool Monitoring Specification (MongoDB Drivers)](https://github.com/mongodb/specifications/blob/master/source/connection-monitoring-and-pooling/connection-monitoring-and-pooling.md) — CMAP events và ý nghĩa của checkout/checked-in/pool clear.

### 25.4. Cách đối chiếu tài liệu theo phiên bản

- **MongoDB Java Driver 5.x:** các ví dụ sử dụng `MongoClientSettings.builder()`, CSOT và connection pool settings.
- **MongoDB Java Driver 4.x:** nhiều option tương tự nhưng một số methods/semantics mới có thể không có hoặc khác.
- **MongoDB Server 6.x/7.x/8.x/9.x:** `serverStatus` và storage-engine admission metrics có thay đổi; không assume dashboard schema cố định.
- **Spring Boot/Spring Data MongoDB:** auto-configuration và URI property settings phụ thuộc starter/framework version.
- **Atlas/free/shared tiers:** metrics và quyền admin commands có thể bị hạn chế; dùng Atlas monitoring API/dashboards khi thích hợp.

Trước khi chọn thông số, trả lời: **đang dùng version nào, topology nào, application có bao nhiêu MongoClients, có bao nhiêu pods, cần SLO gì và bottleneck đã đo nằm ở đâu?**

## 26. Kết luận

**Kiểm soát mức song song, connection pool và hàng đợi yêu cầu** là bài toán **điều tiết năng lực xử lý từ đầu vào tới database**, chứ không phải tìm một số `maxPoolSize` càng lớn càng tốt.

Ba nguyên tắc cần ghi nhớ:

1. **Pool điều khiển transport concurrency, không tạo capacity cho server.** MongoDB Java Driver duy trì **pool theo từng server và từng MongoClient**, còn monitoring sockets/clients khác nằm ngoài phép đếm đơn giản. Cần tính cả pods, HPA và số MongoClient instances.
2. **Queue và deadline phải có giới hạn thật.** `maxPoolSize` hoặc `waitQueueTimeoutMS` không đặt hard cap cho tất cả pending requests. Dùng **admission gate, bounded executor/queue, rate limit, bulkhead, timeout end-to-end và rejection/fallback policy** theo SLA, tránh overload feedback.
3. **Đo trước khi chỉnh.** Tách HTTP queue, admission wait, server selection, pool checkout, command duration và server CPU/IOPS/locks. Khi query/index hoặc DB đã saturated, tăng pool thường không giúp; khi checkout là bottleneck và server còn headroom, mới cân nhắc điều chỉnh pool có kiểm soát.

Một hệ thống vận hành tốt không phải hệ thống **không bao giờ từ chối request**, mà là hệ thống giữ **throughput bền vững, p95/p99 có thể dự đoán, lỗi có thể phục hồi, writes không bị nhân đôi do retry** và tiếp tục hoạt động khi tải vượt thiết kế. **Hãy chọn giới hạn dựa trên dữ liệu đo, kiểm chứng bằng load test và diễn tập failover, rồi rollout dần cùng monitoring và rollback plan.**
